import type {
  FeedResponse,
  Instruction,
  PipelineRun,
  Proposal,
  Rating,
  Source,
} from "./types";

async function j<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = `${res.status}`;
    try {
      const body = await res.json();
      if (body.detail) detail = body.detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  return res.json();
}

const post = (url: string, body?: unknown) =>
  fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });

const patch = (url: string, body: unknown) =>
  fetch(url, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

export const api = {
  feed: () => fetch("/api/feed").then((r) => j<FeedResponse>(r)),
  setState: (id: number, state: "read" | "dismissed") =>
    post(`/api/items/${id}/state`, { state }).then((r) => j<{ ok: boolean }>(r)),
  rate: (id: number, rating: Rating, note?: string) =>
    post(`/api/items/${id}/rating`, { rating, note }).then((r) => j<{ ok: boolean }>(r)),

  sources: () => fetch("/api/sources").then((r) => j<Source[]>(r)),
  addSource: (url: string, name?: string) =>
    post("/api/sources", { url, name }).then((r) => j<Source>(r)),
  patchSource: (id: number, body: Partial<Source>) =>
    patch(`/api/sources/${id}`, body).then((r) => j<Source>(r)),

  proposals: () => fetch("/api/proposals").then((r) => j<Proposal[]>(r)),
  decideProposal: (id: number, decision: "approve" | "reject") =>
    post(`/api/proposals/${id}/${decision}`).then((r) => j<{ ok: boolean }>(r)),

  instructions: () => fetch("/api/instructions").then((r) => j<Instruction[]>(r)),
  addInstruction: (text: string, kind: "quest" | "standing") =>
    post("/api/instructions", { text, kind }).then((r) => j<Instruction>(r)),
  patchInstruction: (id: number, body: { status?: string; text?: string }) =>
    patch(`/api/instructions/${id}`, body).then((r) => j<Instruction>(r)),

  runPipeline: () => post("/api/pipeline/run").then((r) => j<{ run_id: number }>(r)),
  runs: (limit = 1) =>
    fetch(`/api/pipeline/runs?limit=${limit}`).then((r) => j<PipelineRun[]>(r)),
};
