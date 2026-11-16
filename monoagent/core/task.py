"""Task model and durable state machine for long-running agent workflows."""

from enum import Enum
from typing import Any, Dict, List, Optional
from datetime import datetime
from pydantic import BaseModel, Field


class TaskState(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    WAITING_FOR_TOOL = "WAITING_FOR_TOOL"
    SUSPENDED = "SUSPENDED"  # e.g., human-in-the-loop or rate limit wait
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class Checkpoint(BaseModel):
    checkpoint_id: str
    task_id: str
    step_number: int
    state: TaskState
    scratchpad: Dict[str, Any] = Field(default_factory=dict)
    conversation_history: List[Dict[str, Any]] = Field(default_factory=list)
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class LongRunningTask(BaseModel):
    task_id: str
    title: str
    initiator_id: str
    tenant_id: str
    state: TaskState = TaskState.QUEUED
    current_step: int = 0
    max_steps: int = 25
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    checkpoints: List[Checkpoint] = Field(default_factory=list)
    result: Optional[Any] = None
    error: Optional[str] = None

    def save_checkpoint(self, scratchpad: Dict[str, Any], history: List[Dict[str, Any]]) -> Checkpoint:
        self.current_step += 1
        self.updated_at = datetime.utcnow().isoformat()
        cp = Checkpoint(
            checkpoint_id=f"cp-{self.task_id}-{self.current_step}",
            task_id=self.task_id,
            step_number=self.current_step,
            state=self.state,
            scratchpad=scratchpad.copy(),
            conversation_history=history.copy(),
        )
        self.checkpoints.append(cp)
        return cp

    def restore_latest_checkpoint(self) -> Optional[Checkpoint]:
        if not self.checkpoints:
            return None
        return self.checkpoints[-1]
