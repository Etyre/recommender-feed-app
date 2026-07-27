import { useState } from "react";
import { api } from "../api";
import type { Rating } from "../types";

const OPTIONS: { value: Rating; label: string; title: string }[] = [
  { value: "critical", label: "Critical", title: "Absolutely critical to have read" },
  { value: "worth_it", label: "Worth it", title: "Worth my time to find and read" },
  { value: "fine", label: "Fine", title: "Fine, but wouldn't have missed much" },
  { value: "not_worth", label: "Not worth it", title: "Not worth reading" },
  { value: "didnt_finish", label: "Didn't finish", title: "Opened it but didn't read the whole thing" },
];

export function RatingWidget({
  itemId,
  initialRating,
  initialNote,
}: {
  itemId: number;
  initialRating: Rating | null;
  initialNote: string | null;
}) {
  const [rating, setRating] = useState<Rating | null>(initialRating);
  const [note, setNote] = useState(initialNote ?? "");
  const [savedNote, setSavedNote] = useState(initialNote ?? "");

  const choose = (value: Rating) => {
    setRating(value);
    api.rate(itemId, value, note || undefined).catch(() => {});
  };

  const saveNote = () => {
    if (!rating || note === savedNote) return;
    api
      .rate(itemId, rating, note || undefined)
      .then(() => setSavedNote(note))
      .catch(() => {});
  };

  return (
    <div className="rating">
      <div className="rating-buttons">
        {OPTIONS.map((o) => (
          <button
            key={o.value}
            title={o.title}
            className={`rate r-${o.value} ${rating === o.value ? "selected" : ""}`}
            onClick={() => choose(o.value)}
          >
            {o.label}
          </button>
        ))}
      </div>
      {rating && (
        <textarea
          className="note-box"
          rows={2}
          placeholder="Why? (optional — helps the system learn. Saves when you click away; ⌘↵ to save.)"
          value={note}
          onChange={(e) => setNote(e.target.value)}
          onBlur={saveNote}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
              (e.target as HTMLTextAreaElement).blur();
            }
          }}
        />
      )}
    </div>
  );
}
