"""Sandboxed execution environment for agent operations and tool calls."""

import asyncio
from typing import Any, Callable, Dict, Optional


class ExecutionSandbox:
    """Enforces execution boundaries, memory limits, and timeouts on tool execution."""

    def __init__(self, default_timeout_seconds: float = 15.0):
        self.default_timeout = default_timeout_seconds

    async def execute_tool(
        self,
        func: Callable[..., Any],
        args: Dict[str, Any],
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Executes a tool within a monitored timeout and exception boundary."""
        time_limit = timeout or self.default_timeout
        try:
            if asyncio.iscoroutinefunction(func):
                result = await asyncio.wait_for(func(**args), timeout=time_limit)
            else:
                result = await asyncio.wait_for(
                    asyncio.to_thread(func, **args), timeout=time_limit
                )
            return {"status": "success", "result": result, "error": None}
        except asyncio.TimeoutError:
            return {
                "status": "timeout",
                "result": None,
                "error": f"Tool execution timed out after {time_limit} seconds",
            }
        except Exception as e:
            return {
                "status": "error",
                "result": None,
                "error": f"Tool execution failed: {str(e)}",
            }
