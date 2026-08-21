from __future__ import annotations

from app.agent.context import AgentContext


class AgentCancelled(Exception):
    """Raised when the client cancels an in-flight Agent run."""


def ensure_not_cancelled(context: AgentContext) -> None:
    if context.cancelled():
        raise AgentCancelled("用户已取消本次回答。")
