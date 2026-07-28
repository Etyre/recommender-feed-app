import { useEffect, useState } from "react";
import { api } from "../api";
import type { RatingEntry } from "../types";
import { RATING_LABELS, RatingWidget } from "../components/RatingWidget";

function fmt(iso: string): string {
  const d = new Date(iso.replace(" ", "T") + "Z");
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

export function HistoryPage() {
  const [q, setQ] = useState("");
  const [rows, setRows] = useState<RatingEntry[]>([]);
  const [editing, setEditing] = useState<number | null>(null);

  const load = (query: string) =>
    api.ratingHistory(query).then(setRows).catch(() => {});

  useEffect(() => {
    const t = setTimeout(() => load(q), 250);
    return () => clearTimeout(t);
  }, [q]);

  return (
    <main>
      <input
        className="history-search"
        placeholder="Search your ratings — titles, reading notes, feedback…"
        value={q}
        onChange={(e) => setQ(e.target.value)}
      />
      {rows.length === 0 && (
        <p className="hint">{q ? "No ratings match." : "No ratings yet."}</p>
      )}
      {rows.map((r) => (
        <div key={r.item_id} className="history-entry">
          <div className="history-head">
            <span className={`rate-badge r-${r.rating}`}>{RATING_LABELS[r.rating]}</span>
            <a href={r.url} target="_blank" rel="noreferrer" className="history-title">
              {r.title}
            </a>
            <span className="meta">
              {r.source ? `${r.source} · ` : ""}
              {fmt(r.rated_at)}
            </span>
            {editing !== r.item_id && (
              <button className="link-btn" onClick={() => setEditing(r.item_id)}>
                edit
              </button>
            )}
          </div>
          {editing === r.item_id ? (
            <div className="history-editor">
              <RatingWidget
                itemId={r.item_id}
                initialRating={r.rating}
                initialNote={r.note}
                initialReadingNotes={r.reading_notes}
                startExpanded
                onSaved={() => {
                  setEditing(null);
                  load(q);
                }}
              />
              <button className="link-btn" onClick={() => setEditing(null)}>
                cancel
              </button>
            </div>
          ) : (
            <>
              {r.reading_notes && (
                <details className="history-notes">
                  <summary>reading notes ({r.reading_notes.length} chars)</summary>
                  <pre>{r.reading_notes}</pre>
                </details>
              )}
              {r.note && <p className="history-note">→ to the AI: {r.note}</p>}
            </>
          )}
        </div>
      ))}
    </main>
  );
}
