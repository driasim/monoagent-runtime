"""Resilient Model Context Protocol (MCP) tool router with circuit breaker."""

from typing import Any, Callable, Dict, List, Optional
import inspect
from pydantic import BaseModel, Field
from monoagent.core.sandbox import ExecutionSandbox


class ToolDefinition(BaseModel):
    name: str
    description: str
    parameters_schema: Dict[str, Any]
    is_idempotent: bool = True
    timeout_seconds: float = 10.0


class CircuitBreakerStatus(BaseModel):
    tool_name: str
    failure_count: int = 0
    consecutive_empty_count: int = 0
    is_tripped: bool = False
    tripped_reason: Optional[str] = None


class MCPToolRouter:
    """Dispatches tool calls to registered MCP servers and internal APIs with safety boundaries."""

    def __init__(self, failure_threshold: int = 3, sandbox: Optional[ExecutionSandbox] = None):
        self.tools: Dict[str, Callable] = {}
        self.definitions: Dict[str, ToolDefinition] = {}
        self.circuit_breakers: Dict[str, CircuitBreakerStatus] = {}
        self.failure_threshold = failure_threshold
        self.sandbox = sandbox or ExecutionSandbox()

    def register_tool(
        self,
        name: str,
        description: str,
        handler: Callable,
        parameters_schema: Dict[str, Any],
        is_idempotent: bool = True,
        timeout_seconds: float = 10.0,
    ):
        self.tools[name] = handler
        self.definitions[name] = ToolDefinition(
            name=name,
            description=description,
            parameters_schema=parameters_schema,
            is_idempotent=is_idempotent,
            timeout_seconds=timeout_seconds,
        )
        self.circuit_breakers[name] = CircuitBreakerStatus(tool_name=name)

    def get_tool_specs(self) -> List[Dict[str, Any]]:
        """Returns standard OpenAI/MCP-compatible function calling schemas."""
        specs = []
        for defn in self.definitions.values():
            specs.append({
                "type": "function",
                "function": {
                    "name": defn.name,
                    "description": defn.description,
                    "parameters": defn.parameters_schema,
                },
            })
        return specs

    async def invoke_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Routes tool invocation through safety circuit breaker and sandbox."""
        cb = self.circuit_breakers.get(name)
        if not cb:
            return {"status": "error", "error": f"Tool '{name}' is not registered on this MCP surface."}

        if cb.is_tripped:
            return {
                "status": "circuit_tripped",
                "error": f"Circuit breaker tripped for tool '{name}': {cb.tripped_reason}",
            }

        handler = self.tools[name]
        defn = self.definitions[name]

        # Execute inside execution sandbox
        result = await self.sandbox.execute_tool(
            func=handler,
            args=arguments,
            timeout=defn.timeout_seconds,
        )

        if result["status"] != "success":
            cb.failure_count += 1
            if cb.failure_count >= self.failure_threshold:
                cb.is_tripped = True
                cb.tripped_reason = f"Exceeded consecutive failure threshold ({self.failure_threshold})"
        else:
            # Check for empty response loop trap
            output = result["result"]
            if output == [] or output == {} or output is None:
                cb.consecutive_empty_count += 1
                if cb.consecutive_empty_count >= self.failure_threshold:
                    cb.is_tripped = True
                    cb.tripped_reason = f"Exceeded consecutive empty response threshold ({self.failure_threshold})"
            else:
                # Reset counters on success
                cb.failure_count = 0
                cb.consecutive_empty_count = 0

        return result
