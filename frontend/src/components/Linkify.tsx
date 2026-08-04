import React from "react";

const URL_SPLIT = /(https?:\/\/[^\s<>()"'\]]+)/g;
const MD_LINK = /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g;

function bareUrls(text: string, keyBase: string): React.ReactNode[] {
  return text.split(URL_SPLIT).map((part, i) =>
    i % 2 === 1 ? (
      <a
        key={`${keyBase}-${i}`}
        href={part.replace(/[.,;:!?]+$/, "")}
        target="_blank"
        rel="noreferrer"
      >
        {part}
      </a>
    ) : (
      part
    )
  );
}

/** Render text with markdown links and bare URLs as clickable links (new window). */
export function Linkify({ text }: { text: string }) {
  const nodes: React.ReactNode[] = [];
  const re = new RegExp(MD_LINK);
  let last = 0;
  let k = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) {
      nodes.push(...bareUrls(text.slice(last, m.index), `p${k++}`));
    }
    nodes.push(
      <a key={`md${k++}`} href={m[2]} target="_blank" rel="noreferrer">
        {m[1]}
      </a>
    );
    last = m.index + m[0].length;
  }
  nodes.push(...bareUrls(text.slice(last), `p${k++}`));
  return <>{nodes}</>;
}
