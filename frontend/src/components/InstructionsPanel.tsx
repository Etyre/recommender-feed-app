import { useEffect, useState } from "react";
import { api } from "../api";
import type { Instruction } from "../types";

export function InstructionsPanel() {
  const [instructions, setInstructions] = useState<Instruction[]>([]);
  const [text, setText] = useState("");
  const [kind, setKind] = useState<"quest" | "standing">("quest");

  const load = () => {
    api.instructions().then(setInstructions).catch(() => {});
  };
  useEffect(load, []);

  const add = async () => {
    if (!text.trim()) return;
    await api.addInstruction(text.trim(), kind);
    setText("");
    load();
  };

  const setStatus = (id: number, status: string) =>
    api.patchInstruction(id, { status }).then(load);

  const active = instructions.filter((i) => i.status === "active");
  const resolved = instructions.filter((i) => i.status !== "active");

  return (
    <section className="panel instructions">
      <h2>Instruct your feed</h2>
      <div className="instruction-form">
        <textarea
          placeholder={
            kind === "quest"
              ? 'e.g. "Find anything relevant to the recent Hugging Face event not covered by my sources."'
              : 'e.g. "This is giving me too much interpretability research."'
          }
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={2}
        />
        <div className="instruction-controls">
          <label>
            <input
              type="radio"
              checked={kind === "quest"}
              onChange={() => setKind("quest")}
            />
            Short-term quest
          </label>
          <label>
            <input
              type="radio"
              checked={kind === "standing"}
              onChange={() => setKind("standing")}
            />
            Standing preference
          </label>
          <button onClick={add} disabled={!text.trim()}>
            Add
          </button>
        </div>
      </div>
      {active.length > 0 && (
        <ul className="instruction-list">
          {active.map((i) => (
            <li key={i.id} className={`chip chip-${i.kind}`}>
              <span className="chip-kind">{i.kind === "quest" ? "quest" : "standing"}</span>
              <span className="chip-text">{i.text}</span>
              {i.agent_status_note && (
                <span className="agent-note" title={i.agent_status_note}>
                  🤖 {i.agent_status_note.slice(0, 80)}
                  {i.kind === "quest" && (
                    <button onClick={() => setStatus(i.id, "satisfied")}>confirm done</button>
                  )}
                </span>
              )}
              <button
                className="chip-close"
                title={i.kind === "quest" ? "Mark satisfied" : "Archive"}
                onClick={() => setStatus(i.id, i.kind === "quest" ? "satisfied" : "archived")}
              >
                ✕
              </button>
            </li>
          ))}
        </ul>
      )}
      {resolved.length > 0 && (
        <details className="resolved-instructions">
          <summary>{resolved.length} resolved</summary>
          <ul className="instruction-list">
            {resolved.map((i) => (
              <li key={i.id} className="chip chip-resolved">
                <span className="chip-kind">{i.status}</span>
                <span className="chip-text">{i.text}</span>
                <button className="chip-close" onClick={() => setStatus(i.id, "archived")}>
                  ✕
                </button>
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}
