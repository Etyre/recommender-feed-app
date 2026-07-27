import { api } from "../api";
import type { Proposal } from "../types";

export function ProposalCard({
  proposal,
  onDecided,
}: {
  proposal: Proposal;
  onDecided: () => void;
}) {
  const decide = (decision: "approve" | "reject") =>
    api.decideProposal(proposal.id, decision).then(onDecided);

  return (
    <div className="proposal">
      <div className="proposal-body">
        <a href={proposal.url} target="_blank" rel="noreferrer">
          <strong>{proposal.name ?? proposal.url}</strong>
        </a>
        <p>{proposal.rationale}</p>
        {proposal.sample_item_urls.length > 0 && (
          <ul className="samples">
            {proposal.sample_item_urls.slice(0, 3).map((u) => (
              <li key={u}>
                <a href={u} target="_blank" rel="noreferrer">
                  {u}
                </a>
              </li>
            ))}
          </ul>
        )}
      </div>
      <div className="proposal-actions">
        <button className="approve" onClick={() => decide("approve")}>
          Approve
        </button>
        <button className="reject" onClick={() => decide("reject")}>
          Reject
        </button>
      </div>
    </div>
  );
}
