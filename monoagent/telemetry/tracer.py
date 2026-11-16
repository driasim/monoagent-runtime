"""OpenTelemetry-compatible cost & execution tracing for agent runs."""

import time
import uuid
from typing import Any, Dict, List, Optional
from datetime import datetime
from pydantic import BaseModel, Field


class ToolSpan(BaseModel):
    span_id: str
    tool_name: str
    arguments: Dict[str, Any]
    result_preview: Optional[str] = None
    duration_ms: float
    error: Optional[str] = None


class AgentTraceSpan(BaseModel):
    span_id: str
    step_index: int
    prompt_tokens: int = 0
    completion_tokens: int = 0
    step_cost_usd: float = 0.0
    tool_spans: List[ToolSpan] = Field(default_factory=list)
    duration_ms: float = 0.0
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class AgentExecutionTrace(BaseModel):
    trace_id: str
    task_id: str
    tenant_id: str
    user_id: str
    model: str
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_cost_usd: float = 0.0
    total_duration_ms: float = 0.0
    spans: List[AgentTraceSpan] = Field(default_factory=list)
    status: str = "IN_PROGRESS"


class AgentTelemetryTracer:
    """Instruments agent turns and computes cost attribution across tenants."""

    # Default pricing per million tokens
    RATES = {
        "gpt-4o": (2.50, 10.00),
        "claude-3-5-sonnet": (3.00, 15.00),
        "gemini-1.5-pro": (1.25, 5.00),
        "default": (2.00, 8.00),
    }

    def __init__(self, task_id: str, tenant_id: str, user_id: str, model: str = "gpt-4o"):
        self.trace = AgentExecutionTrace(
            trace_id=f"trace-{uuid.uuid4().hex[:12]}",
            task_id=task_id,
            tenant_id=tenant_id,
            user_id=user_id,
            model=model,
        )
        self.start_time = time.perf_counter()

    def record_step(
        self,
        step_index: int,
        prompt_tokens: int,
        completion_tokens: int,
        tool_spans: Optional[List[ToolSpan]] = None,
        duration_ms: float = 0.0,
    ) -> AgentTraceSpan:
        prompt_rate, comp_rate = self.RATES.get(self.trace.model, self.RATES["default"])
        cost = (prompt_tokens / 1_000_000 * prompt_rate) + (completion_tokens / 1_000_000 * comp_rate)

        span = AgentTraceSpan(
            span_id=f"span-{uuid.uuid4().hex[:8]}",
            step_index=step_index,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            step_cost_usd=round(cost, 6),
            tool_spans=tool_spans or [],
            duration_ms=round(duration_ms, 2),
        )

        self.trace.spans.append(span)
        self.trace.total_prompt_tokens += prompt_tokens
        self.trace.total_completion_tokens += completion_tokens
        self.trace.total_cost_usd = round(self.trace.total_cost_usd + cost, 6)
        return span

    def finish(self, status: str = "COMPLETED") -> AgentExecutionTrace:
        self.trace.total_duration_ms = round((time.perf_counter() - self.start_time) * 1000, 2)
        self.trace.status = status
        return self.trace
