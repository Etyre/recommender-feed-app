import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { ChatMessage } from "../types";

export function ChatPage({ onSeen }: { onSeen: () => void }) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.conversation().then(setMessages).catch(() => {});
  }, []);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy]);

  const send = async (text: string | null) => {
    if (busy) return;
    setBusy(true);
    setError(null);
    if (text) {
      // optimistic echo while the agent thinks
      setMessages((m) => [
        ...m,
        { id: -1, role: "user", content: text, created_at: "", proposals: [] },
      ]);
      setInput("");
    }
    try {
      const all = await api.sendChat(text);
      setMessages(all);
      onSeen();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const addProposal = async (messageId: number, index: number) => {
    const all = await api.acceptProposal(messageId, index);
    setMessages(all);
  };

  return (
    <main className="chat">
      <p className="hint">
        A conversation with the agent that curates your feed. It asks; you answer; it
        follows up. Clear preferences become one-click instruction chips.
      </p>
      <div className="chat-messages">
        {messages.length === 0 && !busy && (
          <div className="chat-empty">
            <button onClick={() => send(null)}>Have the agent interview you</button>
          </div>
        )}
        {messages.map((m, i) => (
          <div key={m.id === -1 ? `tmp-${i}` : m.id} className={`bubble bubble-${m.role}`}>
            <div className="bubble-content">{m.content}</div>
            {m.proposals.length > 0 && (
              <div className="proposal-chips">
                {m.proposals.map((p, j) => (
                  <button
                    key={`${m.id}-${j}`}
                    className="proposal-chip"
                    disabled={!!p.added}
                    onClick={() => addProposal(m.id, j)}
                  >
                    {p.added ? `✓ added ${p.kind}: ${p.text}` : `+ ${p.kind}: ${p.text}`}
                  </button>
                ))}
              </div>
            )}
          </div>
        ))}
        {busy && <div className="bubble bubble-agent thinking">thinking…</div>}
        <div ref={bottom} />
      </div>
      {error && <p className="error">{error}</p>}
      <div className="chat-input">
        <textarea
          rows={2}
          placeholder="Answer, or tell it anything about what you want to read…"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              if (input.trim()) send(input.trim());
            }
          }}
        />
        <button disabled={busy || !input.trim()} onClick={() => send(input.trim())}>
          Send
        </button>
      </div>
    </main>
  );
}
