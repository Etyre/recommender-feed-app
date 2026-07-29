export type Rating = "critical" | "worth_it" | "fine" | "not_worth" | "didnt_finish";

export interface FeedItem {
  id: number;
  title: string;
  url: string;
  source: string | null;
  published_at: string | null;
  summary: string | null;
  topics: string[];
  state: string;
  rating: Rating | null;
  note: string | null;
  reading_notes: string | null;
  rank: number | null;
  score: number | null;
  rationale: string | null;
  redundant_with_rank: number | null;
}

export interface FeedResponse {
  mode: "ranked" | "chronological";
  run: { id: number; status: string; started_at: string; finished_at: string | null } | null;
  items: FeedItem[];
}

export interface Source {
  id: number;
  name: string;
  kind: string;
  url: string;
  feed_url: string | null;
  origin: "default" | "user" | "agent";
  status: "active" | "paused";
  filter_note: string | null;
  last_fetched_at: string | null;
  last_fetch_status: string | null;
  last_fetch_error: string | null;
}

export interface Proposal {
  id: number;
  name: string | null;
  url: string;
  feed_url: string | null;
  rationale: string;
  sample_item_urls: string[];
}

export interface Instruction {
  id: number;
  text: string;
  kind: "quest" | "standing";
  status: string;
  expires_at: string | null;
  agent_status_note: string | null;
}

export interface RatingEntry {
  item_id: number;
  title: string;
  url: string;
  source: string | null;
  rating: Rating;
  note: string | null;
  reading_notes: string | null;
  rated_at: string;
}

export interface ChatMessage {
  id: number;
  role: "agent" | "user";
  content: string;
  created_at: string;
  proposals: { text: string; kind: string; added?: boolean }[];
}

export interface DailyUsage {
  day: string; // YYYY-MM-DD (local)
  runs: number;
  cost_usd: number;
  input_tokens: number;
  output_tokens: number;
}

export interface PipelineRun {
  id: number;
  trigger: string;
  status: "running" | "success" | "partial" | "error";
  started_at: string;
  finished_at: string | null;
  stage: string | null;
  error: string | null;
  stats: Record<string, unknown> & {
    llm?: { calls: number; input_tokens: number; output_tokens: number; est_cost_usd: number };
  };
}
