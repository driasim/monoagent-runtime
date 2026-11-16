"""Runnable demonstration of the Monoagent Runtime in action."""

import asyncio
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from monoagent.core.kernel import MonoagentKernel
from monoagent.core.task import LongRunningTask
from monoagent.memory.shared_memory import HierarchicalMemory
from monoagent.mcp.router import MCPToolRouter
from monoagent.telemetry.tracer import AgentTelemetryTracer, ToolSpan
from monoagent.skills.loader import PlaybookRegistry

console = Console()


# Simulated MCP tool handlers
def check_pg_locks(db_cluster: str) -> dict:
    return {
        "cluster": db_cluster,
        "blocked_pids": [10822],
        "blocking_pid": 9411,
        "locktype": "exclusive",
    }


def terminate_backend(pid: int) -> dict:
    return {"status": "terminated", "pid": pid, "reclaimed_resources": True}


async def main():
    console.print(Panel.fit("[bold green]Enterprise Monoagent Runtime Demo[/bold green]\nSimulating internal SRE monoagent handling long-running incident remediation."))

    # 1. Initialize Memory & Knowledge
    memory = HierarchicalMemory(tenant_id="corp-finance-sre")
    memory.register_knowledge(
        "incident_policies",
        "P1/P2 database lockups require automated termination if blocking transaction exceeds 180s.",
    )

    # 2. Register MCP Tools
    router = MCPToolRouter(failure_threshold=3)
    router.register_tool(
        name="check_pg_locks",
        description="Inspect Postgres active table locks",
        handler=check_pg_locks,
        parameters_schema={"type": "object", "properties": {"db_cluster": {"type": "string"}}, "required": ["db_cluster"]},
    )
    router.register_tool(
        name="terminate_backend_connection",
        description="Terminate blocking PostgreSQL backend PID",
        handler=terminate_backend,
        parameters_schema={"type": "object", "properties": {"pid": {"type": "integer"}}, "required": ["pid"]},
    )

    # 3. Load Reusable Company Playbooks
    registry = PlaybookRegistry()
    playbook_file = Path(__file__).parent / "company_playbooks" / "database_incident.yaml"
    playbook = registry.load_from_file(str(playbook_file))
    console.print(f"[bold cyan]Loaded Reusable Playbook:[/bold cyan] {playbook.name} (v{playbook.version})")

    # 4. Initialize Kernel and Task
    kernel = MonoagentKernel(
        tenant_id="corp-finance-sre",
        memory=memory,
        tool_router=router,
        playbook_registry=registry,
    )

    task = LongRunningTask(
        task_id="task-db-incident-402",
        title="PostgreSQL production lock contention remediation",
        initiator_id="usr_pagerduty_webhook",
        tenant_id="corp-finance-sre",
    )

    tracer = AgentTelemetryTracer(
        task_id=task.task_id,
        tenant_id=task.tenant_id,
        user_id=task.initiator_id,
        model="gpt-4o",
    )

    # Step Handler simulating LLM orchestrator
    async def step_1_handler(t, user_msg, tool_specs):
        # Monoagent calls check_pg_locks
        res = await router.invoke_tool("check_pg_locks", {"db_cluster": "primary-eu-west-1"})
        span = ToolSpan(
            span_id="tsp-001",
            tool_name="check_pg_locks",
            arguments={"db_cluster": "primary-eu-west-1"},
            result_preview=str(res["result"]),
            duration_ms=45.2,
        )
        return {
            "prompt_tokens": 780,
            "completion_tokens": 40,
            "tool_spans": [span],
            "response": "Found blocking PID 9411 holding exclusive table lock on orders table.",
            "is_complete": False,
        }

    async def step_2_handler(t, user_msg, tool_specs):
        # Monoagent terminates PID 9411
        res = await router.invoke_tool("terminate_backend_connection", {"pid": 9411})
        span = ToolSpan(
            span_id="tsp-002",
            tool_name="terminate_backend_connection",
            arguments={"pid": 9411},
            result_preview=str(res["result"]),
            duration_ms=62.8,
        )
        return {
            "prompt_tokens": 920,
            "completion_tokens": 55,
            "tool_spans": [span],
            "response": "Successfully terminated blocking backend PID 9411. Database latency restored to baseline 12ms.",
            "is_complete": True,
        }

    # Execute Step 1
    console.print("\n[bold yellow]-- Executing Step 1: Diagnose Lock Contention --[/bold yellow]")
    s1 = await kernel.execute_task_step(task, "high db load detected on primary-eu-west-1", tracer, step_1_handler)
    console.print(f"Task Step {s1['current_step']} Checkpointed | Playbook: {s1['playbook_applied']}")
    console.print(f"Agent: {s1['response']}")

    # Execute Step 2
    console.print("\n[bold yellow]-- Executing Step 2: Mitigate and Resolve Incident --[/bold yellow]")
    s2 = await kernel.execute_task_step(task, "terminate blocking transaction to restore latency", tracer, step_2_handler)
    console.print(f"Task Step {s2['current_step']} Checkpointed | Status: [green]{s2['task_state']}[/green]")
    console.print(f"Agent: {s2['response']}")

    # Finalize Telemetry Trace
    final_trace = tracer.finish(status="COMPLETED")

    table = Table(title="Telemetry & Cost Audit Trace")
    table.add_column("Field", style="bold")
    table.add_column("Value", style="cyan")

    table.add_row("Trace ID", final_trace.trace_id)
    table.add_row("Task ID", final_trace.task_id)
    table.add_row("Total Spans", str(len(final_trace.spans)))
    table.add_row("Total Prompt Tokens", str(final_trace.total_prompt_tokens))
    table.add_row("Total Completion Tokens", str(final_trace.total_completion_tokens))
    table.add_row("Total Cost (USD)", f"${final_trace.total_cost_usd:.6f}")
    table.add_row("Total Duration", f"{final_trace.total_duration_ms}ms")
    table.add_row("Checkpoints Stored", str(len(task.checkpoints)))

    console.print("\n")
    console.print(table)
    console.print("\n[bold green]✓ Long-running task completed with full audit trail and zero regressions.[/bold green]")


if __name__ == "__main__":
    asyncio.run(main())
