"""Anthropic client wrapper: model constants, structured outputs, usage/cost accounting,
refusal handling. Every LLM stage goes through here."""
from __future__ import annotations

import json
import re
from typing import Any, Type, TypeVar

import anthropic
from pydantic import BaseModel

# USD per million tokens (input, output)
PRICES = {
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-opus-5": (5.0, 25.0),
}

T = TypeVar("T", bound=BaseModel)


class LLMRefusal(Exception):
    pass


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


def _check_refusal(resp: Any) -> None:
    if resp.stop_reason == "refusal":
        detail = getattr(resp, "stop_details", None)
        raise LLMRefusal(str(detail) if detail else "model refused the request")


def parse_structured_messages(
    *,
    model: str,
    system: Any,
    messages: list,
    output_model: Type[T],
    max_tokens: int = 4000,
    usage: UsageTracker | None = None,
) -> T:
    resp = get_client().messages.parse(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=messages,
        output_format=output_model,
    )
    if usage is not None:
        usage.add(model, resp.usage)
    _check_refusal(resp)
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
    resp = get_client().messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user_content}],
    )
    if usage is not None:
        usage.add(model, resp.usage)
    _check_refusal(resp)
    return "".join(b.text for b in resp.content if b.type == "text")


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
    tools = [{"type": "web_search_20260209", "name": "web_search", "max_uses": max_uses}]
    messages: list[dict] = [{"role": "user", "content": user_content}]
    resp = None
    for _ in range(max_continuations + 1):
        resp = get_client().messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
            tools=tools,
        )
        if usage is not None:
            usage.add(model, resp.usage)
        if resp.stop_reason == "pause_turn":
            messages = messages + [{"role": "assistant", "content": resp.content}]
            continue
        break
    assert resp is not None
    _check_refusal(resp)
    return "".join(b.text for b in resp.content if b.type == "text")


def extract_json_object(text: str) -> dict:
    """Pull a JSON object out of model text output (```json fence preferred)."""
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if m:
        return json.loads(m.group(1))
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        return json.loads(text[start : end + 1])
    raise ValueError("no JSON object found in model output")
