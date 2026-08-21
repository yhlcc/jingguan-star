from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable
from typing import Any

from langgraph.errors import GraphBubbleUp
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from app.agent.cancel import AgentCancelled, ensure_not_cancelled
from app.agent.checkpointer import get_checkpointer, thread_config
from app.agent.context import AgentContext
from app.agent.nodes.answer_generation import answer_generation
from app.agent.nodes.data_validation import data_validation
from app.agent.nodes.intent_recognition import intent_recognition
from app.agent.nodes.multi_interface_execute import multi_interface_execute
from app.agent.nodes.query_planning import query_planning
from app.agent.nodes.skill_matching import skill_matching
from app.agent.nodes.whitelist_approval import whitelist_approval
from app.agent.state import AgentState, NODE_LABELS
from app.repositories.runs import create_run, update_run_status


Node = Callable[[AgentContext, AgentState], dict[str, Any]]
logger = logging.getLogger(__name__)


def build_agent_graph(context: AgentContext, *, require_approval: bool = False, checkpointer=None):
    builder = StateGraph(AgentState)
    nodes: list[tuple[str, Node]] = [
        ("intent_recognition", intent_recognition),
        ("skill_matching", skill_matching),
        ("query_planning", query_planning),
        ("whitelist_approval", whitelist_approval),
        ("multi_interface_execute", multi_interface_execute),
        ("data_validation", data_validation),
        ("answer_generation", answer_generation),
    ]
    for name, node in nodes:
        builder.add_node(name, _observed(context, name, node))
    builder.add_edge(START, "intent_recognition")
    builder.add_conditional_edges(
        "intent_recognition",
        _route_after_intent,
        {"direct_chat": "answer_generation", "business_query": "skill_matching"},
    )
    for left, right in [
        ("skill_matching", "query_planning"),
        ("query_planning", "whitelist_approval"),
        ("whitelist_approval", "multi_interface_execute"),
        ("multi_interface_execute", "data_validation"),
        ("data_validation", "answer_generation"),
    ]:
        builder.add_edge(left, right)
    builder.add_edge("answer_generation", END)
    return builder.compile(checkpointer=checkpointer)


def _route_after_intent(state: AgentState) -> str:
    return "direct_chat" if state.get("intent") == "direct_chat" else "business_query"


def _observed(context: AgentContext, name: str, node: Node):
    def run(state: AgentState) -> dict[str, Any]:
        started = time.perf_counter(); label = NODE_LABELS[name]
        ensure_not_cancelled(context)
        context.emit("node_started", {"node": name, "label": label, "traceId": state["trace_id"]})
        try:
            update = node(context, state)
        except GraphBubbleUp:
            raise
        except AgentCancelled:
            context.emit("cancelled", {"traceId": state["trace_id"], "message": "已取消本次回答"})
            raise
        except Exception as exc:
            logger.exception(
                "Agent node failed trace_id=%s session_id=%s node=%s error=%s",
                state.get("trace_id"),
                state.get("session_id"),
                name,
                exc,
            )
            context.emit("node_failed", {"node": name, "label": label, "traceId": state["trace_id"], "message": str(exc)})
            raise
        ensure_not_cancelled(context)
        context.emit("node_completed", {"node": name, "label": label, "traceId": state["trace_id"], "durationMs": round((time.perf_counter()-started)*1000)})
        return update
    return run


def run_agent(
    context: AgentContext,
    *,
    session_id: int,
    question: str,
    history: list[dict[str, str]],
    require_approval: bool = False,
) -> AgentState:
    """Run the agent graph once; state is checkpointed per run for crash recovery and replay."""
    run_id = str(uuid.uuid4())
    thread = thread_config(session_id, run_id)
    create_run(context.conn, session_id, run_id, thread["configurable"]["thread_id"], question)
    initial: AgentState = {"trace_id": run_id, "session_id": session_id, "question": question, "history": history}
    graph = build_agent_graph(context, require_approval=require_approval, checkpointer=get_checkpointer())
    logger.info("Agent graph invoke started session_id=%s run_id=%s require_approval=%s", session_id, run_id, require_approval)
    try:
        result = graph.invoke(initial, thread)
    except AgentCancelled as exc:
        update_run_status(context.conn, run_id, "cancelled", str(exc))
        logger.info("Agent graph cancelled session_id=%s run_id=%s", session_id, run_id)
        raise
    except Exception as exc:
        update_run_status(context.conn, run_id, "failed", str(exc))
        logger.exception("Agent graph invoke failed session_id=%s run_id=%s error=%s", session_id, run_id, exc)
        raise
    if result.get("__interrupt__"):
        update_run_status(context.conn, run_id, "interrupted")
        logger.info("Agent graph interrupted session_id=%s run_id=%s", session_id, run_id)
    else:
        update_run_status(context.conn, run_id, "completed")
        logger.info("Agent graph completed session_id=%s run_id=%s", session_id, run_id)
    return result


def resume_agent(
    context: AgentContext,
    *,
    session_id: int,
    run_id: str,
    resume_value: Any = None,
) -> AgentState:
    """Resume an interrupted run (human approval) from its persisted checkpoint."""
    thread = thread_config(session_id, run_id)
    graph = build_agent_graph(context, require_approval=True, checkpointer=get_checkpointer())
    update_run_status(context.conn, run_id, "running")
    logger.info("Agent graph resume invoke started session_id=%s run_id=%s has_resume_value=%s", session_id, run_id, resume_value is not None)
    try:
        if resume_value is None:
            # Crash recovery: continue from the last persisted checkpoint without new input.
            result = graph.invoke(None, thread)
        else:
            result = graph.invoke(Command(resume=resume_value), thread)
    except AgentCancelled as exc:
        update_run_status(context.conn, run_id, "cancelled", str(exc))
        logger.info("Agent graph resume cancelled session_id=%s run_id=%s", session_id, run_id)
        raise
    except Exception as exc:
        update_run_status(context.conn, run_id, "failed", str(exc))
        logger.exception("Agent graph resume invoke failed session_id=%s run_id=%s error=%s", session_id, run_id, exc)
        raise
    update_run_status(context.conn, run_id, "completed" if not result.get("__interrupt__") else "interrupted")
    logger.info("Agent graph resume invoke finished session_id=%s run_id=%s interrupted=%s", session_id, run_id, bool(result.get("__interrupt__")))
    return result
