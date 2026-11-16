"""Unit tests for enterprise monoagent runtime kernel, memory, MCP router, and telemetry."""

import asyncio
from monoagent.core.task import LongRunningTask, TaskState
from monoagent.memory.shared_memory import HierarchicalMemory
from monoagent.mcp.router import MCPToolRouter
from monoagent.telemetry.tracer import AgentTelemetryTracer


def test_task_checkpointing():
    task = LongRunningTask(
        task_id="task-test-01",
        title="Check system logs",
        initiator_id="usr_admin",
        tenant_id="tenant_alpha",
    )
    assert task.current_step == 0
    assert len(task.checkpoints) == 0

    cp = task.save_checkpoint(
        scratchpad={"current_pid": 1234},
        history=[{"role": "user", "content": "analyze logs"}],
    )
    assert task.current_step == 1
    assert len(task.checkpoints) == 1
    assert cp.scratchpad["current_pid"] == 1234


def test_hierarchical_memory():
    mem = HierarchicalMemory(tenant_id="tenant_alpha")
    mem.register_knowledge("database_policy", "Always terminate idle connections > 300s.")
    assert "Always terminate" in mem.lookup_knowledge("database_policy")

    mem.record_episode("task-99", "Successfully migrated database schema", "SUCCESS")
    episodes = mem.search_episodes("migrated database")
    assert len(episodes) == 1
    assert episodes[0].metadata["outcome"] == "SUCCESS"


def test_mcp_circuit_breaker():
    async def _run():
        router = MCPToolRouter(failure_threshold=2)

        def failing_tool():
            raise RuntimeError("External API 500 Server Error")

        router.register_tool(
            name="flaky_service",
            description="Fails consistently",
            handler=failing_tool,
            parameters_schema={"type": "object"},
        )

        # Call 1: failure
        res1 = await router.invoke_tool("flaky_service", {})
        assert res1["status"] == "error"
        assert router.circuit_breakers["flaky_service"].is_tripped is False

        # Call 2: failure -> trips circuit breaker
        res2 = await router.invoke_tool("flaky_service", {})
        assert res2["status"] == "error"
        assert router.circuit_breakers["flaky_service"].is_tripped is True

        # Call 3: blocked by circuit breaker
        res3 = await router.invoke_tool("flaky_service", {})
        assert res3["status"] == "circuit_tripped"

    asyncio.run(_run())


def test_telemetry_cost_calculation():
    tracer = AgentTelemetryTracer(
        task_id="task-otel-1",
        tenant_id="tenant_alpha",
        user_id="usr_100",
        model="gpt-4o",
    )
    tracer.record_step(
        step_index=1,
        prompt_tokens=1000,
        completion_tokens=200,
        duration_ms=150.0,
    )
    trace = tracer.finish(status="COMPLETED")
    assert trace.total_prompt_tokens == 1000
    assert trace.total_completion_tokens == 200
    assert trace.total_cost_usd > 0.0
    assert trace.total_duration_ms > 0.0
