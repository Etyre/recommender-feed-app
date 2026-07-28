import { useRef, useState } from "react";
import { api } from "../api";
import type { Rating } from "../types";

export const RATING_LABELS: Record<Rating, string> = {
  critical: "Critical",
  worth_it: "Worth it",
  fine: "Fine",
  not_worth: "Not worth it",
  didnt_finish: "Didn't finish",
};

const OPTIONS: { value: Rating; title: string }[] = [
  { value: "critical", title: "Absolutely critical to have read" },
  { value: "worth_it", title: "Worth my time to find and read" },
  { value: "fine", title: "Fine, but wouldn't have missed much" },
  { value: "not_worth", title: "Not worth reading" },
  { value: "didnt_finish", title: "Opened it but didn't read the whole thing" },
];

export function RatingWidget({
  itemId,
  initialRating,
  initialNote,
  initialReadingNotes,
  startExpanded,
  onSaved,
}: {
  itemId: number;
  initialRating: Rating | null;
  initialNote: string | null;
  initialReadingNotes?: string | null;
  startExpanded?: boolean;
  onSaved?: () => void;
}) {
  const [rating, setRating] = useState<Rating | null>(initialRating);
  const [note, setNote] = useState(initialNote ?? "");
  const [readingNotes, setReadingNotes] = useState(initialReadingNotes ?? "");
  const [expanded, setExpanded] = useState(startExpanded ?? !initialRating);
  const [saveState, setSaveState] = useState<"idle" | "saving" | "saved">("idle");
  const lastSaved = useRef({ note: initialNote ?? "", readingNotes: initialReadingNotes ?? "" });

  const dirty =
    note !== lastSaved.current.note || readingNotes !== lastSaved.current.readingNotes;

  const save = (nextRating: Rating, collapseAfter = false) => {
    setSaveState("saving");
    api
      .rate(itemId, nextRating, note.trim() || undefined, readingNotes.trim() || undefined)
      .then(() => {
        lastSaved.current = { note, readingNotes };
        setSaveState("saved");
        if (collapseAfter) {
          setExpanded(false);
          onSaved?.();
        }
      })
      .catch(() => setSaveState("idle"));
  };

  const choose = (value: Rating) => {
    setRating(value);
    save(value);
  };

  const finish = () => {
    if (!rating) return;
    if (dirty) {
      save(rating, true);
    } else {
      setExpanded(false);
      onSaved?.();
    }
  };

  const blurOnCmdEnter = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
      finish();
    }
  };

  if (!expanded) {
    return (
      <div className="rating rating-collapsed">
        {rating && <span className={`rate-badge r-${rating}`}>{RATING_LABELS[rating]}</span>}
        {(note.trim() || readingNotes.trim()) && (
          <span className="collapsed-note-hint">· notes saved</span>
        )}
        <button className="link-btn" onClick={() => setExpanded(true)}>
          edit rating
        </button>
      </div>
    );
  }

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
            {RATING_LABELS[o.value]}
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
            onKeyDown={blurOnCmdEnter}
          />
          <textarea
            className="note-box"
            rows={2}
            placeholder="To the AI (optional) — tell it directly what was or wasn't valuable here."
            value={note}
            onChange={(e) => setNote(e.target.value)}
            onKeyDown={blurOnCmdEnter}
          />
          <div className="note-actions">
            <button
              className="save-notes"
              onClick={finish}
              disabled={saveState === "saving"}
            >
              {saveState === "saving" ? "Saving…" : "Save notes"}
            </button>
          </div>
        </>
      )}
    </div>
  );
}
