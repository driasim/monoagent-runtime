"""Tiered shared memory system for enterprise monoagents."""

from typing import Any, Dict, List, Optional
from datetime import datetime
from pydantic import BaseModel, Field


class MemoryEntry(BaseModel):
    key: str
    content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    tenant_id: str
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class HierarchicalMemory:
    """Manages organizational knowledge, episodic task memory, and working scratchpads."""

    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id
        # In-memory stores (in production backed by PostgreSQL + pgvector and Redis)
        self.working_scratchpad: Dict[str, Any] = {}
        self.episodic_history: List[MemoryEntry] = []
        self.organizational_facts: Dict[str, MemoryEntry] = {}

    # 1. Working scratchpad (ephemeral task state)
    def set_scratchpad(self, key: str, value: Any):
        self.working_scratchpad[key] = value

    def get_scratchpad(self, key: str, default: Any = None) -> Any:
        return self.working_scratchpad.get(key, default)

    # 2. Episodic memory (historical agent runs)
    def record_episode(self, task_id: str, summary: str, outcome: str):
        entry = MemoryEntry(
            key=task_id,
            content=summary,
            metadata={"outcome": outcome, "task_id": task_id},
            tenant_id=self.tenant_id,
        )
        self.episodic_history.append(entry)

    def search_episodes(self, query: str, limit: int = 3) -> List[MemoryEntry]:
        """Simple keyword/semantic filter across past completed task runs."""
        q_lower = query.lower()
        matches = [
            e for e in self.episodic_history
            if q_lower in e.content.lower() or any(q_lower in str(v).lower() for v in e.metadata.values())
        ]
        return matches[:limit]

    # 3. Shared Organizational Knowledge (playbooks, infrastructure, policies)
    def register_knowledge(self, topic: str, content: str, source: str = "wiki"):
        self.organizational_facts[topic] = MemoryEntry(
            key=topic,
            content=content,
            metadata={"source": source},
            tenant_id=self.tenant_id,
        )

    def lookup_knowledge(self, topic: str) -> Optional[str]:
        entry = self.organizational_facts.get(topic)
        return entry.content if entry else None
