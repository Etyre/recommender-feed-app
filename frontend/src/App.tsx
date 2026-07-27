import { useCallback, useState } from "react";
import { usePipeline } from "./hooks/usePipeline";
import { FeedPage } from "./pages/FeedPage";
import { SourcesPage } from "./pages/SourcesPage";
import { InstructionsPanel } from "./components/InstructionsPanel";
import { RunStatus } from "./components/RunStatus";

export default function App() {
  const [tab, setTab] = useState<"feed" | "instructions" | "sources">("feed");
  const [feedVersion, setFeedVersion] = useState(0);
  const onFinished = useCallback(() => setFeedVersion((v) => v + 1), []);
  const { latestRun, running, trigger } = usePipeline(onFinished);

  return (
    <div className="app">
      <header className="topbar">
        <h1>Reading Feed</h1>
        <nav>
          <button
            className={tab === "feed" ? "tab active" : "tab"}
            onClick={() => setTab("feed")}
          >
            Feed
          </button>
          <button
            className={tab === "instructions" ? "tab active" : "tab"}
            onClick={() => setTab("instructions")}
          >
            Instructions
          </button>
          <button
            className={tab === "sources" ? "tab active" : "tab"}
            onClick={() => setTab("sources")}
          >
            Sources
          </button>
        </nav>
        <div className="run-controls">
          <RunStatus run={latestRun} />
          <button className="refresh" onClick={trigger} disabled={running}>
            {running ? "Running…" : "↻ Refresh"}
          </button>
        </div>
      </header>
      {tab === "feed" && <FeedPage version={feedVersion} />}
      {tab === "instructions" && (
        <main>
          <InstructionsPanel />
        </main>
      )}
      {tab === "sources" && <SourcesPage />}
    </div>
  );
}
