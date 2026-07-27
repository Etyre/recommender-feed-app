import { useState } from "react";
import { api } from "../api";
import type { FeedItem } from "../types";
import { RatingWidget } from "./RatingWidget";

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
        Save any URL into your feed — it ranks near the top until you read it.
        Already read it? Rate it right here and it goes straight into the
        training data instead of the unread queue.
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
        <div key={item.id} className="added-link">
          <p className="hint">
            ✓ Added: <strong>{item.title}</strong>
          </p>
          <RatingWidget
            itemId={item.id}
            initialRating={item.rating}
            initialNote={item.note}
          />
        </div>
      ))}
    </section>
  );
}
