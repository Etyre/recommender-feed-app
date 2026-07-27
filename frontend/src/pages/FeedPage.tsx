import { useEffect, useState } from "react";
import { api } from "../api";
import type { FeedResponse } from "../types";
import { FeedItemCard } from "../components/FeedItemCard";

export function FeedPage({ version }: { version: number }) {
  const [data, setData] = useState<FeedResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .feed()
      .then((d) => {
        setData(d);
        setError(null);
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, [version]);

  const removeItem = (id: number) =>
    setData((d) => (d ? { ...d, items: d.items.filter((it) => it.id !== id) } : d));

  return (
    <main>
      {error && <p className="error">Could not load feed: {error}</p>}
      {data?.mode === "chronological" && data.items.length > 0 && (
        <p className="hint">
          No ranked run yet — showing newest first. Hit ↻ Refresh to fetch and rank.
        </p>
      )}
      {data && data.items.length === 0 && (
        <p className="hint">
          Feed is empty. Hit ↻ Refresh to fetch from your sources.
        </p>
      )}
      {data?.items.map((item) => (
        <FeedItemCard key={item.id} item={item} onDismiss={removeItem} />
      ))}
    </main>
  );
}
