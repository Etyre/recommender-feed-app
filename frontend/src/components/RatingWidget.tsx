import { useRef, useState } from "react";
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
  initialReadingNotes,
}: {
  itemId: number;
  initialRating: Rating | null;
  initialNote: string | null;
  initialReadingNotes?: string | null;
}) {
  const [rating, setRating] = useState<Rating | null>(initialRating);
  const [note, setNote] = useState(initialNote ?? "");
  const [readingNotes, setReadingNotes] = useState(initialReadingNotes ?? "");
  const [saveState, setSaveState] = useState<"idle" | "saving" | "saved">("idle");
  const lastSaved = useRef({ note: initialNote ?? "", readingNotes: initialReadingNotes ?? "" });

  const dirty =
    note !== lastSaved.current.note || readingNotes !== lastSaved.current.readingNotes;

  const save = (nextRating: Rating) => {
    setSaveState("saving");
    api
      .rate(itemId, nextRating, note.trim() || undefined, readingNotes.trim() || undefined)
      .then(() => {
        lastSaved.current = { note, readingNotes };
        setSaveState("saved");
      })
      .catch(() => setSaveState("idle"));
  };

  const choose = (value: Rating) => {
    setRating(value);
    save(value);
  };

  const saveNotes = () => {
    if (!rating || !dirty) return;
    save(rating);
  };

  const blurOnCmdEnter = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
      (e.target as HTMLTextAreaElement).blur();
    }
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
        <>
          <textarea
            className="note-box"
            rows={3}
            placeholder="Your reading notes (optional) — paste whatever you wrote while reading; the AI infers what mattered to you from them."
            value={readingNotes}
            onChange={(e) => setReadingNotes(e.target.value)}
            onBlur={saveNotes}
            onKeyDown={blurOnCmdEnter}
          />
          <textarea
            className="note-box"
            rows={2}
            placeholder="To the AI (optional) — tell it directly what was or wasn't valuable here."
            value={note}
            onChange={(e) => setNote(e.target.value)}
            onBlur={saveNotes}
            onKeyDown={blurOnCmdEnter}
          />
          <div className="note-actions">
            <button className="save-notes" onClick={saveNotes} disabled={!dirty}>
              {saveState === "saving" ? "Saving…" : "Save notes"}
            </button>
            {saveState === "saved" && !dirty && (
              <span className="saved-indicator">✓ saved</span>
            )}
          </div>
        </>
      )}
    </div>
  );
}
