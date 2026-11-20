"""Anthropic client wrapper: model constants, structured outputs, usage/cost accounting,
refusal handling. Every LLM stage goes through here.

This is also where the agent-coding LLM standard is enforced for every call site:
the shared preamble (shared/llm-system-prompt-preamble.md) is prepended to every
system prompt, the `contact_eli` and `note_to_eli` tools are offered on every call, a `contact_eli` call is
followed by one question, send or keep working (llm_contact.with_confirm), and every response is
checked with llm_contact.check(). If the model contacts Eli, LLMContacted is raised and
the caller must stop the task it was doing (no retry, no pushing past it).
A `note_to_eli` call does not stop anything: the note is recorded, the call is answered and the
model is asked again for its answer (llm_contact.with_notes, in _confirmed)."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Type, TypeVar

import anthropic
from pydantic import BaseModel

SHARED_DIR = Path.home() / "Documents/agent-coding/shared"
if str(SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_DIR))
import llm_contact  # noqa: E402  (shared/llm_contact.py, standard library only)

APP_NAME = "recommender-feed"
CONTACT_TOOL = llm_contact.CONTACT_TOOL
CONTACT_TOOLS = llm_contact.CONTACT_TOOLS  # contact_eli (stops the task) and note_to_eli (task carries on)

# USD per million tokens (input, output)
PRICES = {
    "claude-haiku-5-5": (0.10, 0.50),  # prompts up to 100K tokens; every call here is far below that
    "claude-opus-5-5": (4.0, 20.0),
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-opus-5": (5.0, 25.0),
}

# Opus 5.5 defaults to medium effort; Opus 5, which these prompts were tuned on, ran at high. Keep high.
# Haiku 5.5 is left at its default (medium).
EFFORT = {"claude-opus-5-5": "high"}


def _effort(model: str) -> dict:
    return {"output_config": {"effort": EFFORT[model]}} if model in EFFORT else {}

T = TypeVar("T", bound=BaseModel)


class LLMRefusal(Exception):
    pass


class LLMContacted(Exception):
    """The model used `contact_eli` or wrote an `@ELI:` line. The contact has already been
    recorded in the LLM inbox and Eli notified; whatever task triggered this call must stop."""

    def __init__(self, record: dict):
        self.record = record
        super().__init__(
            f"the model asked to talk to Eli (llm-inbox show {record.get('id')}): "
            f"{str(record.get('message', ''))[:200]}"
        )


class UsageTracker:
    def __init__(self) -> None:
        self.by_model: dict[str, dict[str, int]] = {}
        self.calls = 0

    def add(self, model: str, usage: Any) -> None:
        self.calls += 1
        d = self.by_model.setdefault(model, {"input_tokens": 0, "output_tokens": 0})
        d["input_tokens"] += (getattr(usage, "input_tokens", 0) or 0)
        d["input_tokens"] += (getattr(usage, "cache_creation_input_tokens", 0) or 0)
        d["input_tokens"] += (getattr(usage, "cache_read_input_tokens", 0) or 0)
        d["output_tokens"] += (getattr(usage, "output_tokens", 0) or 0)

    def summary(self) -> dict:
        total_in = sum(d["input_tokens"] for d in self.by_model.values())
        total_out = sum(d["output_tokens"] for d in self.by_model.values())
        cost = 0.0
        for model, d in self.by_model.items():
            p_in, p_out = PRICES.get(model, (5.0, 25.0))
            cost += d["input_tokens"] / 1e6 * p_in + d["output_tokens"] / 1e6 * p_out
        return {
            "calls": self.calls,
            "input_tokens": total_in,
            "output_tokens": total_out,
            "est_cost_usd": round(cost, 4),
        }


_client: anthropic.Anthropic | None = None


def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


def with_preamble(system: Any) -> Any:
    """Prepend the shared preamble, word for word, to a system prompt given either as a
    string or as a list of text blocks (the first block keeps its cache_control)."""
    if isinstance(system, str):
        return llm_contact.system_prompt(system)
    if isinstance(system, list) and system:
        first = dict(system[0])
        first["text"] = llm_contact.system_prompt(first.get("text", ""))
        return [first] + list(system[1:])
    return llm_contact.system_prompt("")


def _plain_response(resp: Any) -> Any:
    """SDK response -> JSON dict. messages.parse() results carry Pydantic generics that make the
    default serializer print a wall of warnings; dump them quietly and drop the parsed copy."""
    try:
        return resp.model_dump(mode="json", warnings=False, exclude={"parsed_output"})
    except Exception:  # noqa: BLE001 - fall back to whatever llm_contact can make of it
        return resp


def _after_response(model: str, system: Any, messages: list, resp: Any, tools: list) -> None:
    record = llm_contact.check(
        app=APP_NAME, model=model, system=system, messages=messages,
        response=_plain_response(resp), tools=tools,
    )
    if record:
        raise LLMContacted(record)


def _confirmed(model: str, system: Any, tools: list, messages: list, call: Any,
               usage: "UsageTracker | None") -> tuple[list, Any]:
    """Make the call. If the model only leaves a note (note_to_eli), record it, answer the tool call and ask
    again, so a note never stops the task and is never taken for its answer. If the model calls contact_eli, ask it once whether it meant to reach Eli or was remarking
    on the task (shared confirm step, active only for the models in llm_contact.CONFIRM_MODELS: Haiku 4.5 otherwise uses the tool for routine remarks on JSON-only calls).
    `call(messages)` is the real call. Returns (messages, response) for _after_response; every call is counted."""
    def counted(msgs: list, decide: bool = False) -> Any:
        if decide:
            r = get_client().messages.create(model=model, system=system, messages=msgs,
                                             **llm_contact.decision_kwargs(tools))
        else:
            r = call(msgs)
        if usage is not None:
            usage.add(model, r.usage)
        return r
    messages, resp = llm_contact.with_notes(APP_NAME, model, system, messages, counted(messages), counted, tools)
    return llm_contact.with_confirm(APP_NAME, model, messages, resp, counted)


def _said_before(turns: list) -> str:
    """Text the model wrote in the turns _confirmed added (before a note_to_eli call, say). A model that gives
    its answer and leaves a note in the same reply may not repeat the answer when asked again, so keep it."""
    return "".join(
        b["text"] + "\n"
        for m in turns if m.get("role") == "assistant" and isinstance(m.get("content"), list)
        for b in m["content"] if isinstance(b, dict) and b.get("type") == "text"
    )


def _check_refusal(resp: Any) -> None:
    if resp.stop_reason == "refusal":
        detail = getattr(resp, "stop_details", None)
        raise LLMRefusal(str(detail) if detail else "model refused the request")


def _check_truncated(resp: Any) -> None:
    """Thinking and the reply share max_tokens, so a reply can stop mid-sentence. A cut-off
    taste profile would be stored and then read by every later triage and ranking call."""
    if resp.stop_reason == "max_tokens":
        raise ValueError("output truncated at max_tokens — increase the budget")


def parse_structured_messages(
    *,
    model: str,
    system: Any,
    messages: list,
    output_model: Type[T],
    max_tokens: int = 4000,
    usage: UsageTracker | None = None,
) -> T:
    system = with_preamble(system)
    tools = list(CONTACT_TOOLS)
    messages, resp = _confirmed(model, system, tools, messages, lambda msgs: get_client().messages.parse(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=msgs,
        tools=tools,
        output_format=output_model,
        **_effort(model),
    ), usage)
    _after_response(model, system, messages, resp, tools)
    _check_refusal(resp)
    if resp.stop_reason == "max_tokens":
        # Thinking + output share max_tokens; a truncated grammar-constrained reply
        # can look "valid" while being garbage. Never return it.
        raise ValueError("output truncated at max_tokens — increase the budget")
    parsed = resp.parsed_output
    if parsed is None:
        raise ValueError("model output did not match the expected schema")
    return parsed


def parse_structured(
    *,
    model: str,
    system: Any,
    user_content: Any,
    output_model: Type[T],
    max_tokens: int = 4000,
    usage: UsageTracker | None = None,
) -> T:
    return parse_structured_messages(
        model=model,
        system=system,
        messages=[{"role": "user", "content": user_content}],
        output_model=output_model,
        max_tokens=max_tokens,
        usage=usage,
    )


def generate_text(
    *,
    model: str,
    system: Any,
    user_content: Any,
    max_tokens: int = 8000,
    usage: UsageTracker | None = None,
) -> str:
    system = with_preamble(system)
    tools = list(CONTACT_TOOLS)
    messages = [{"role": "user", "content": user_content}]
    asked = len(messages)
    messages, resp = _confirmed(model, system, tools, messages, lambda msgs: get_client().messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=msgs,
        tools=tools,
        **_effort(model),
    ), usage)
    _after_response(model, system, messages, resp, tools)
    _check_refusal(resp)
    _check_truncated(resp)
    return _said_before(messages[asked:]) + "".join(b.text for b in resp.content if b.type == "text")


def run_with_web_search(
    *,
    model: str,
    system: Any,
    user_content: str,
    max_uses: int,
    max_tokens: int = 16000,
    usage: UsageTracker | None = None,
    max_continuations: int = 3,
) -> str:
    """Agentic call with the server-side web_search tool. Returns final text output.
    Handles pause_turn continuation (server-side search loop hit its iteration cap)."""
    system = with_preamble(system)
    tools = [
        *CONTACT_TOOLS,
        {"type": "web_search_20260209", "name": "web_search", "max_uses": max_uses},
    ]
    messages: list[dict] = [{"role": "user", "content": user_content}]
    resp = None
    said = ""
    for _ in range(max_continuations + 1):
        asked = len(messages)
        messages, resp = _confirmed(model, system, tools, messages, lambda msgs: get_client().messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=msgs,
            tools=tools,
            **_effort(model),
        ), usage)
        _after_response(model, system, messages, resp, tools)
        said += _said_before(messages[asked:])
        if resp.stop_reason == "pause_turn":
            messages = messages + [{"role": "assistant", "content": resp.content}]
            continue
        break
    assert resp is not None
    _check_refusal(resp)
    _check_truncated(resp)
    return said + "".join(b.text for b in resp.content if b.type == "text")


def extract_json_object(text: str) -> dict:
    """Pull a JSON object out of model text output (```json fence preferred)."""
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if m:
        return json.loads(m.group(1))
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        return json.loads(text[start : end + 1])
    raise ValueError("no JSON object found in model output")
