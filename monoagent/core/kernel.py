"""Monoagent Kernel: Coordinates memory, MCP tools, playbooks, and execution checkpoints."""

import asyncio
from typing import Any, Callable, Dict, List, Optional
from monoagent.core.task import LongRunningTask, TaskState
from monoagent.memory.shared_memory import HierarchicalMemory
from monoagent.mcp.router import MCPToolRouter
from monoagent.telemetry.tracer import AgentTelemetryTracer, ToolSpan
from monoagent.skills.loader import PlaybookRegistry, ReusablePlaybook


class MonoagentKernel:
    """Production runtime kernel managing stateful multi-turn execution."""

    def __init__(
        self,
        tenant_id: str,
        memory: Optional[HierarchicalMemory] = None,
        tool_router: Optional[MCPToolRouter] = None,
        playbook_registry: Optional[PlaybookRegistry] = None,
    ):
        self.tenant_id = tenant_id
        self.memory = memory or HierarchicalMemory(tenant_id=tenant_id)
        self.tool_router = tool_router or MCPToolRouter()
        self.playbooks = playbook_registry or PlaybookRegistry()

    async def execute_task_step(
        self,
        task: LongRunningTask,
        user_input: str,
        tracer: AgentTelemetryTracer,
        step_handler: Callable[[LongRunningTask, str, List[Dict[str, Any]]], Any],
    ) -> Dict[str, Any]:
        """Executes a single step of a long-running task with checkpointing and telemetry."""
        if task.state in (TaskState.COMPLETED, TaskState.FAILED):
            return {"status": "already_terminated", "state": task.state}

        task.state = TaskState.RUNNING

        # 1. Match relevant operational playbooks
        matched_playbook = self.playbooks.find_playbook_for_intent(user_input)

        # 2. Retrieve organizational context from memory
        org_context = self.memory.lookup_knowledge("incident_policies")

        # 3. Execute step handler
        step_start = asyncio.get_event_loop().time()
        tool_specs = self.tool_router.get_tool_specs()

        try:
            handler_result = await step_handler(task, user_input, tool_specs)

            # Record telemetry span
            duration_ms = (asyncio.get_event_loop().time() - step_start) * 1000
            tracer.record_step(
                step_index=task.current_step + 1,
                prompt_tokens=handler_result.get("prompt_tokens", 850),
                completion_tokens=handler_result.get("completion_tokens", 65),
                tool_spans=handler_result.get("tool_spans", []),
                duration_ms=duration_ms,
            )

            # Save durable checkpoint
            task.save_checkpoint(
                scratchpad=self.memory.working_scratchpad,
                history=[{"role": "user", "content": user_input}, {"role": "assistant", "content": handler_result.get("response")}],
            )

            if handler_result.get("is_complete"):
                task.state = TaskState.COMPLETED
                task.result = handler_result.get("response")
                self.memory.record_episode(
                    task_id=task.task_id,
                    summary=f"Resolved: {user_input[:80]}",
                    outcome="SUCCESS",
                )

            return {
                "status": "success",
                "task_state": task.state,
                "current_step": task.current_step,
                "response": handler_result.get("response"),
                "playbook_applied": matched_playbook.name if matched_playbook else None,
            }

        except Exception as e:
            task.state = TaskState.FAILED
            task.error = str(e)
            return {"status": "error", "error": str(e), "task_state": task.state}
