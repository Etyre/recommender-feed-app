import { useState } from "react";
import { api } from "../api";

export function AddSourceForm({ onAdded }: { onAdded: () => void }) {
  const [url, setUrl] = useState("");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const add = async () => {
    if (!url.trim()) return;
    setBusy(true);
    setMessage(null);
    try {
      const source = await api.addSource(url.trim(), name.trim() || undefined);
      setMessage(
        source.kind === "rss"
          ? `Added — found feed: ${source.feed_url}`
          : "Added — no RSS feed found; the page will be scanned for new links each run."
      );
      setUrl("");
      setName("");
      onAdded();
    } catch (e) {
      setMessage(`Failed: ${e instanceof Error ? e.message : e}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="add-source">
      <div className="add-source-fields">
        <input
          placeholder="https://example.com/blog"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && add()}
        />
        <input
          placeholder="Name (optional)"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <button onClick={add} disabled={busy || !url.trim()}>
          {busy ? "Probing…" : "Add"}
        </button>
      </div>
      {message && <p className="hint">{message}</p>}
    </div>
  );
}
