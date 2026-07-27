import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import { usePipeline } from "./hooks/usePipeline";
import { ChatPage } from "./pages/ChatPage";
import { FeedPage } from "./pages/FeedPage";
import { SourcesPage } from "./pages/SourcesPage";
import { InstructionsPanel } from "./components/InstructionsPanel";
import { AddLinkPanel } from "./components/AddLinkPanel";
import { CostWidget } from "./components/CostWidget";
import { RunStatus } from "./components/RunStatus";

export default function App() {
  const [tab, setTab] = useState<"feed" | "instructions" | "sources" | "chat">("feed");
  const [feedVersion, setFeedVersion] = useState(0);
  const [chatPending, setChatPending] = useState(false);
  const onFinished = useCallback(() => setFeedVersion((v) => v + 1), []);
  const { latestRun, running, trigger } = usePipeline(onFinished);

  useEffect(() => {
    // dot on the Chat tab while the agent's latest question is unanswered
    api
      .conversation()
      .then((m) => setChatPending(m.length > 0 && m[m.length - 1].role === "agent"))
      .catch(() => {});
  }, [feedVersion]);

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
          <button
            className={tab === "chat" ? "tab active" : "tab"}
            onClick={() => setTab("chat")}
          >
            Chat{chatPending && <span className="tab-dot" title="The agent has a question for you" />}
          </button>
        </nav>
        <div className="run-controls">
          <CostWidget runVersion={feedVersion} />
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
          <AddLinkPanel />
        </main>
      )}
      {tab === "sources" && <SourcesPage />}
      {tab === "chat" && <ChatPage onSeen={() => setChatPending(false)} />}
    </div>
  );
}
