import { api } from "../api";
import type { Source } from "../types";

const ORIGIN_LABEL = { default: "default", user: "added by you", agent: "found by agent" };

export function SourceRow({
  source,
  onChanged,
}: {
  source: Source;
  onChanged: () => void;
}) {
  const toggle = () =>
    api
      .patchSource(source.id, {
        status: source.status === "active" ? "paused" : "active",
      })
      .then(onChanged);

  const health =
    source.last_fetch_status === "ok"
      ? "✓"
      : source.last_fetch_status === "error"
        ? "⚠"
        : "–";

  return (
    <div className={`source-row ${source.status}`}>
      <span
        className={`health ${source.last_fetch_status ?? ""}`}
        title={source.last_fetch_error ?? `last fetch: ${source.last_fetched_at ?? "never"}`}
      >
        {health}
      </span>
      <div className="source-main">
        <a href={source.url} target="_blank" rel="noreferrer">
          {source.name}
        </a>
        <span className="meta">
          {source.kind === "rss" ? "RSS" : "page scan"} ·{" "}
          <span className={`origin origin-${source.origin}`}>
            {ORIGIN_LABEL[source.origin]}
          </span>
          {source.filter_note && (
            <span title={source.filter_note}> · filtered</span>
          )}
        </span>
        {source.last_fetch_status === "error" && (
          <span className="fetch-error">{source.last_fetch_error}</span>
        )}
      </div>
      <button onClick={toggle}>
        {source.status === "active" ? "Pause" : "Resume"}
      </button>
    </div>
  );
}
