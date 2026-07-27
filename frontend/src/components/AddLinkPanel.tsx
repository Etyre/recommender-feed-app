import { useState } from "react";
import { api } from "../api";
import type { FeedItem } from "../types";

/** Save an arbitrary URL into the feed. Lives on the Instructions page. */
export function AddLinkPanel() {
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [added, setAdded] = useState<FeedItem[]>([]);
  const [error, setError] = useState<string | null>(null);

  const add = async () => {
    if (!url.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      const item = await api.addLink(url.trim());
      setAdded((prev) => [item, ...prev]);
      setUrl("");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="panel">
      <h2>Add a link</h2>
      <p className="hint" style={{ marginTop: 0 }}>
        Save any URL into your feed. It ranks near the top until you read it, and
        rating it teaches the system like any other item.
      </p>
      <div className="add-source-fields">
        <input
          placeholder="https://example.com/some-article"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && add()}
        />
        <button onClick={add} disabled={busy || !url.trim()}>
          {busy ? "Fetching…" : "Add"}
        </button>
      </div>
      {error && <p className="error">{error}</p>}
      {added.map((item) => (
        <p key={item.id} className="hint">
          ✓ Added to feed: <strong>{item.title}</strong>
          {item.summary ? " — summarized and queued for ranking." : ""}
        </p>
      ))}
    </section>
  );
}
