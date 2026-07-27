import type { PipelineRun } from "../types";

export function RunStatus({ run }: { run: PipelineRun | null }) {
  if (!run) return <span className="run-status">no runs yet</span>;
  if (run.status === "running") {
    return (
      <span className="run-status running">
        running: {run.stage ?? "starting"}…
      </span>
    );
  }
  const when = run.finished_at ? new Date(run.finished_at + "Z") : null;
  const cost = run.stats?.llm?.est_cost_usd;
  return (
    <span
      className={`run-status ${run.status}`}
      title={run.error ?? undefined}
    >
      last run: {run.status}
      {when && !isNaN(when.getTime()) ? ` · ${when.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}` : ""}
      {cost != null ? ` · ~$${cost.toFixed(2)}` : ""}
    </span>
  );
}
