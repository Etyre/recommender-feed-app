const URL_SPLIT = /(https?:\/\/[^\s<>()"'\]]+)/g;

/** Render text with bare URLs as clickable links (new window). */
export function Linkify({ text }: { text: string }) {
  const parts = text.split(URL_SPLIT);
  return (
    <>
      {parts.map((part, i) =>
        i % 2 === 1 ? (
          <a key={i} href={part.replace(/[.,;:!?]+$/, "")} target="_blank" rel="noreferrer">
            {part}
          </a>
        ) : (
          part
        )
      )}
    </>
  );
}
