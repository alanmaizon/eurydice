"""
Generic tool registry: register tools with declarations and executors,
dispatch by name.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class ToolEntry:
    name: str
    declaration: dict[str, Any]
    executor: Callable[..., Any]
    mock_executor: Callable[..., Any] | None = None


class ToolRegistry:
    """Register and dispatch tool calls by name."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolEntry] = {}

    def register(
        self,
        name: str,
        declaration: dict[str, Any],
        executor: Callable[..., Any],
        mock_executor: Callable[..., Any] | None = None,
    ) -> None:
        self._tools[name] = ToolEntry(
            name=name,
            declaration=declaration,
            executor=executor,
            mock_executor=mock_executor,
        )

    def get_declarations(self) -> list[dict[str, Any]]:
        """Return tool declarations in the format expected by LLM APIs."""
        return [entry.declaration for entry in self._tools.values()]

    def execute(self, name: str, args: dict[str, Any], use_mock: bool = False) -> Any:
        entry = self._tools.get(name)
        if entry is None:
            return {"error": f"Unknown tool: {name}"}
        if use_mock and entry.mock_executor is not None:
            return entry.mock_executor(args)
        return entry.executor(args)

    def has_tool(self, name: str) -> bool:
        return name in self._tools

    @property
    def tool_names(self) -> list[str]:
        return list(self._tools.keys())
