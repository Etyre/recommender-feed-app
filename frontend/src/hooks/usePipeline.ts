import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { PipelineRun } from "../types";

/** Polls the latest pipeline run; calls onFinished when a running run completes. */
export function usePipeline(onFinished: () => void) {
  const [latestRun, setLatestRun] = useState<PipelineRun | null>(null);
  const prevRunning = useRef(false);
  const onFinishedRef = useRef(onFinished);
  onFinishedRef.current = onFinished;

  useEffect(() => {
    let alive = true;
    const tick = async () => {
      try {
        const runs = await api.runs(1);
        if (!alive) return;
        const run = runs[0] ?? null;
        setLatestRun(run);
        const running = run?.status === "running";
        if (prevRunning.current && !running) onFinishedRef.current();
        prevRunning.current = running;
      } catch {
        /* server not up yet — keep polling */
      }
    };
    tick();
    const id = setInterval(tick, 3000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, []);

  const trigger = async () => {
    try {
      await api.runPipeline();
      prevRunning.current = true;
    } catch (e) {
      alert(`Could not start run: ${e instanceof Error ? e.message : e}`);
    }
  };

  return { latestRun, running: latestRun?.status === "running", trigger };
}
