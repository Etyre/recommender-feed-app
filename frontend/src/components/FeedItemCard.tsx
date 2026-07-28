import { api } from "../api";
import type { FeedItem } from "../types";
import { RatingWidget } from "./RatingWidget";

function fmtDate(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

export function FeedItemCard({
  item,
  onDismiss,
}: {
  item: FeedItem;
  onDismiss: (id: number) => void;
}) {
  const markRead = () => {
    // fire-and-forget; the link opens regardless
    api.setState(item.id, "read").catch(() => {});
  };

  return (
    <article className="card">
      <div className="rank">{item.rank ?? "•"}</div>
      <div className="card-body">
        <a href={item.url} target="_blank" rel="noreferrer" onClick={markRead}>
          <h3>{item.title}</h3>
        </a>
        <div className="meta">
          {item.source && <span className="source">{item.source}</span>}
          {item.published_at && <span> · {fmtDate(item.published_at)}</span>}
          {item.topics.map((t) => (
            <span key={t} className="tag">
              {t}
            </span>
          ))}
        </div>
        {item.summary && <p className="summary">{item.summary}</p>}
        {item.rationale && (
          <details className="rationale">
            <summary>
              Why it's here
              {item.redundant_with_rank != null && (
                <span className="overlap"> · overlaps #{item.redundant_with_rank}</span>
              )}
            </summary>
            <p>{item.rationale}</p>
          </details>
        )}
        <RatingWidget
          itemId={item.id}
          initialRating={item.rating}
          initialNote={item.note}
          initialReadingNotes={item.reading_notes}
        />
      </div>
      <button
        className="dismiss"
        title="Not interested — remove from feed"
        onClick={() => {
          api.setState(item.id, "dismissed").catch(() => {});
          onDismiss(item.id);
        }}
      >
        ✕
      </button>
    </article>
  );
}
