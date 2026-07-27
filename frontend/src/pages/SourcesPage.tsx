import { useEffect, useState } from "react";
import { api } from "../api";
import type { Proposal, Source } from "../types";
import { AddSourceForm } from "../components/AddSourceForm";
import { ProposalCard } from "../components/ProposalCard";
import { SourceRow } from "../components/SourceRow";

export function SourcesPage() {
  const [sources, setSources] = useState<Source[]>([]);
  const [proposals, setProposals] = useState<Proposal[]>([]);

  const load = () => {
    api.sources().then(setSources).catch(() => {});
    api.proposals().then(setProposals).catch(() => {});
  };
  useEffect(load, []);

  return (
    <main>
      {proposals.length > 0 && (
        <section className="panel">
          <h2>Proposed sources (agent found these — approve to add permanently)</h2>
          {proposals.map((p) => (
            <ProposalCard key={p.id} proposal={p} onDecided={load} />
          ))}
        </section>
      )}
      <section className="panel">
        <h2>Add a source</h2>
        <AddSourceForm onAdded={load} />
      </section>
      <section className="panel">
        <h2>Sources</h2>
        {sources.map((s) => (
          <SourceRow key={s.id} source={s} onChanged={load} />
        ))}
      </section>
    </main>
  );
}
