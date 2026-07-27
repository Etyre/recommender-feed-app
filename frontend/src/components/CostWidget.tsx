import { useEffect, useRef, useState } from "react";
import type { DailyUsage } from "../types";
import { api } from "../api";

/** Unobtrusive daily-spend indicator; click for a per-day breakdown. */
export function CostWidget({ runVersion }: { runVersion: number }) {
  const [days, setDays] = useState<DailyUsage[]>([]);
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.usageDaily().then(setDays).catch(() => {});
  }, [runVersion]);

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  const today = new Date().toLocaleDateString("sv"); // YYYY-MM-DD, local
  const todayCost = days.find((d) => d.day === today)?.cost_usd ?? 0;

  return (
    <div className="cost-widget" ref={ref}>
      <button className="cost-toggle" onClick={() => setOpen((o) => !o)} title="LLM spend — click for daily breakdown">
        ≈${todayCost.toFixed(2)} today
      </button>
      {open && (
        <div className="cost-popover">
          <div className="cost-header">LLM spend (est.)</div>
          {days.length === 0 && <div className="cost-row">no runs yet</div>}
          {days.slice(0, 14).map((d) => (
            <div key={d.day} className="cost-row">
              <span>{d.day === today ? "today" : d.day.slice(5)}</span>
              <span className="cost-runs">{d.runs} run{d.runs === 1 ? "" : "s"}</span>
              <span className="cost-amt">${d.cost_usd.toFixed(2)}</span>
            </div>
          ))}
          {days.length > 0 && (
            <div className="cost-row cost-total">
              <span>last {Math.min(days.length, 30)} days</span>
              <span className="cost-amt">
                ${days.reduce((a, d) => a + d.cost_usd, 0).toFixed(2)}
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
