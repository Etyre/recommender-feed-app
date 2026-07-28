"""Pydantic models for LLM structured outputs and API request bodies.

Note: Optional[...] (not `X | None`) — the app runs on Python 3.9.
"""
from typing import Optional

from pydantic import BaseModel

# ---------- LLM structured outputs ----------


class TriageResult(BaseModel):
    summary: str
    topics: list[str]
    relevance: int  # 0-10 expected value for this reader
    passes_source_filter: bool
    filter_reason: Optional[str] = None


class ListingItem(BaseModel):
    url: str
    title: str
    published: Optional[str] = None


class ListingResult(BaseModel):
    items: list[ListingItem]


class RankingEntry(BaseModel):
    item_id: int
    score: float
    rationale: str
    redundant_with_item_id: Optional[int] = None


class RankingResult(BaseModel):
    rankings: list[RankingEntry]


class DiscoveredItem(BaseModel):
    url: str
    title: str
    why_relevant: str
    for_instruction_id: Optional[int] = None


class SourceProposalOut(BaseModel):
    url: str
    name: str
    rationale: str
    feed_url: Optional[str] = None
    sample_item_urls: list[str] = []


class QuestUpdate(BaseModel):
    instruction_id: int
    suggestion: str
    note: str = ""


class ProposedInstruction(BaseModel):
    text: str
    kind: str  # 'quest' | 'standing'


class InterviewTurn(BaseModel):
    reply: str
    proposed_instructions: list[ProposedInstruction] = []


class DiscoveryResult(BaseModel):
    found_items: list[DiscoveredItem] = []
    source_proposals: list[SourceProposalOut] = []
    quest_updates: list[QuestUpdate] = []


# ---------- API request bodies ----------


class StateIn(BaseModel):
    state: str  # 'read' | 'dismissed'


class LinkIn(BaseModel):
    url: str


class RatingIn(BaseModel):
    rating: str  # 'critical' | 'worth_it' | 'fine' | 'not_worth' | 'didnt_finish'
    note: Optional[str] = None  # direct feedback to the AI
    reading_notes: Optional[str] = None  # raw notes taken while reading


class SourceIn(BaseModel):
    url: str
    name: Optional[str] = None
    filter_note: Optional[str] = None


class SourcePatch(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = None  # 'active' | 'paused'
    filter_note: Optional[str] = None
    feed_url: Optional[str] = None
    kind: Optional[str] = None


class InstructionIn(BaseModel):
    text: str
    kind: str  # 'quest' | 'standing'


class InstructionPatch(BaseModel):
    text: Optional[str] = None
    status: Optional[str] = None  # 'active' | 'satisfied' | 'expired' | 'archived'


class ProfileIn(BaseModel):
    content_md: str


class ChatIn(BaseModel):
    message: Optional[str] = None  # None/empty = "agent, ask me something"
