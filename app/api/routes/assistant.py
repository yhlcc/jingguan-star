from __future__ import annotations

import json
import logging
import queue
import sqlite3
import threading
from collections.abc import Iterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.agent.cancel import AgentCancelled
from app.agent.checkpointer import delete_session_checkpoints, list_run_checkpoints
from app.agent.context import AgentContext
from app.agent.graph import resume_agent, run_agent
from app.api.schemas import ApprovalRequest, MessageRequest, SessionCreate
from app.core.database import connect, get_db
from app.core.errors import BusinessError
from app.repositories.conversations import add_message, create_session, delete_session, get_messages, history, list_sessions
from app.repositories.runs import delete_session_runs, get_run, list_session_runs
from app.repositories.settings import get_app_config, get_llm_config
from app.services.llm import LlmClient
from app.services.query_gateway import QueryGateway


router = APIRouter(tags=["assistant"])
Db = Annotated[sqlite3.Connection, Depends(get_db)]
logger = logging.getLogger(__name__)


@router.get("/qa/sessions")
def sessions(conn: Db, keyword: str | None = None) -> dict:
    return {"items": list_sessions(conn, keyword)}


@router.post("/qa/sessions")
def new_session(payload: SessionCreate, conn: Db) -> dict:
    return create_session(conn, payload.title)


@router.get("/qa/sessions/{session_id}/messages")
def messages(session_id: int, conn: Db) -> dict:
    return get_messages(conn, session_id)


@router.delete("/qa/sessions/{session_id}")
def remove_session(session_id: int, conn: Db) -> dict:
    delete_session_checkpoints(session_id)
    delete_session_runs(conn, session_id)
    return delete_session(conn, session_id)


def _build_context(conn: sqlite3.Connection, session_id: int, emit, *, require_approval: bool, cancel_event: threading.Event | None = None) -> AgentContext:
    model = LlmClient(get_llm_config(conn, reveal=True))
    ui = get_app_config(conn)
    return AgentContext(
        conn=conn,
        llm=model,
        gateway=QueryGateway(conn),
        emit=emit,
        next_suggestions_count=ui["nextSuggestionsCount"] if ui["nextSuggestionsEnabled"] else 0,
        require_approval=require_approval,
        cancel_event=cancel_event,
    )


def _execute(conn: sqlite3.Connection, session_id: int, content: str, emit, *, require_approval: bool = False, cancel_event: threading.Event | None = None) -> dict[str, Any]:
    if not content.strip(): raise BusinessError("VALIDATION_ERROR", "消息内容不能为空")
    logger.info("Agent execution started session_id=%s require_approval=%s", session_id, require_approval)
    add_message(conn, session_id, "user", content.strip())
    current_history = history(conn, session_id)
    process: list[dict[str, Any]] = []
    streamed = {"value": False}

    def observed_emit(name: str, data: dict[str, Any]) -> None:
        if name == "delta":
            streamed["value"] = True
        item = _process_item(name, data)
        if item:
            process.append(item)
        emit(name, data)

    context = _build_context(conn, session_id, observed_emit, require_approval=require_approval, cancel_event=cancel_event)
    result = run_agent(
        context,
        session_id=session_id,
        question=content.strip(),
        history=current_history,
        require_approval=require_approval,
    )
    return _finalize(conn, session_id, result, process, observed_emit, streamed)


def _execute_resume(
    conn: sqlite3.Connection,
    session_id: int,
    *,
    run_id: str,
    resume_value: Any,
    emit,
    cancel_event: threading.Event | None = None,
) -> dict[str, Any]:
    run = get_run(conn, session_id, run_id)
    if run["status"] == "completed":
        raise BusinessError("RUN_ALREADY_COMPLETED", "该运行已经完成，无需恢复。")
    logger.info("Agent resume started session_id=%s run_id=%s", session_id, run_id)
    process: list[dict[str, Any]] = []
    streamed = {"value": False}

    def observed_emit(name: str, data: dict[str, Any]) -> None:
        if name == "delta":
            streamed["value"] = True
        item = _process_item(name, data)
        if item:
            process.append(item)
        emit(name, data)

    context = _build_context(conn, session_id, observed_emit, require_approval=True, cancel_event=cancel_event)
    result = resume_agent(
        context,
        session_id=session_id,
        run_id=run_id,
        resume_value=resume_value,
    )
    return _finalize(conn, session_id, result, process, observed_emit, streamed, run_id=run_id)


def _finalize(
    conn: sqlite3.Connection,
    session_id: int,
    result: dict[str, Any],
    process: list[dict[str, Any]],
    emit,
    streamed: dict[str, bool],
    *,
    run_id: str | None = None,
) -> dict[str, Any]:
    interrupted = result.get("__interrupt__") is not None
    run_id = run_id or str(result.get("trace_id") or "")
    if interrupted:
        interrupts = result.get("__interrupt__") or ()
        pending = {}
        if interrupts:
            value = interrupts[0].value if hasattr(interrupts[0], "value") else {}
            if isinstance(value, dict):
                pending = value
        return {
            "interrupted": True,
            "runId": run_id,
            "pendingCalls": pending.get("calls", []),
            "pendingMessage": pending.get("message", "查询计划等待人工审批"),
            "streamed": streamed["value"],
        }
    calls = [{"stepId": item.get("stepId"), "interfaceCode": item.get("interfaceCode"), "requestId": item.get("requestId"), "rowCount": len(item.get("rows", []))} for item in result.get("validated_results", [])]
    result["answer_payload"]["process"] = process
    message_id = add_message(conn, session_id, "assistant", result["final_answer"], calls, result["answer_payload"])
    return {"messageId": message_id, "content": result["final_answer"], "answerPayload": result["answer_payload"],
            "interfaceCalls": calls, "traceId": result["trace_id"], "runId": run_id,
            "suggestions": result["answer_payload"].get("nextSuggestions", []), "streamed": streamed["value"]}


@router.post("/qa/sessions/{session_id}/messages")
def send(session_id: int, payload: MessageRequest, conn: Db) -> dict:
    result = _execute(conn, session_id, payload.content, lambda *_: None, require_approval=payload.requireApproval)
    conn.commit()
    return result


@router.post("/qa/sessions/{session_id}/messages/stream")
def stream(session_id: int, payload: MessageRequest) -> StreamingResponse:
    events: queue.Queue[tuple[str, dict[str, Any]] | None] = queue.Queue()
    cancel_event = threading.Event()

    def emit(name: str, data: dict[str, Any]) -> None:
        events.put((name, data))

    def worker() -> None:
        conn = connect()
        try:
            emit("status", {"message": "正在初始化 Agent 工作流"})
            if payload.resumeRunId:
                result = _execute_resume(conn, session_id, run_id=payload.resumeRunId, resume_value=None, emit=emit, cancel_event=cancel_event)
            else:
                result = _execute(conn, session_id, payload.content, emit, require_approval=payload.requireApproval, cancel_event=cancel_event)
            conn.commit()
            emit("run", {"runId": result.get("runId", "")})
            if result.get("interrupted"):
                logger.info("Agent execution interrupted session_id=%s run_id=%s", session_id, result["runId"])
                emit("pending_approval", {
                    "runId": result["runId"],
                    "message": result["pendingMessage"],
                    "calls": result["pendingCalls"],
                })
                return
            _emit_answer_stream(emit, result)
            emit("done", {"messageId": result["messageId"], "traceId": result["traceId"], "runId": result["runId"], "answerPayload": result["answerPayload"]})
            logger.info("Agent execution completed session_id=%s run_id=%s message_id=%s", session_id, result["runId"], result["messageId"])
        except AgentCancelled as exc:
            logger.info("Agent execution cancelled session_id=%s resume_run_id=%s", session_id, payload.resumeRunId or "")
            conn.commit()
            emit("cancelled", {"message": str(exc) or "已取消本次回答"})
        except BusinessError as exc:
            logger.warning("Agent business error session_id=%s code=%s message=%s", session_id, exc.code, exc.message)
            conn.commit(); emit("error", {"code": exc.code, "message": exc.message})
        except Exception as exc:
            logger.exception("Agent execution failed session_id=%s resume_run_id=%s error=%s", session_id, payload.resumeRunId or "", exc)
            conn.commit(); emit("error", {"code": "AGENT_EXECUTION_FAILED", "message": "Agent 执行失败，请查看服务端日志。"})
        finally:
            conn.close(); events.put(None)

    threading.Thread(target=worker, daemon=True).start()

    def generate() -> Iterator[str]:
        try:
            while True:
                item = events.get()
                if item is None: break
                name, data = item
                yield f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"
        finally:
            cancel_event.set()

    return StreamingResponse(generate(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/qa/sessions/{session_id}/approve")
def approve(session_id: int, payload: ApprovalRequest) -> StreamingResponse:
    events: queue.Queue[tuple[str, dict[str, Any]] | None] = queue.Queue()
    cancel_event = threading.Event()

    def emit(name: str, data: dict[str, Any]) -> None:
        events.put((name, data))

    def worker() -> None:
        conn = connect()
        try:
            emit("status", {"message": "正在继续执行已审批的查询计划"})
            result = _execute_resume(
                conn,
                session_id,
                run_id=payload.runId,
                resume_value={"approved": payload.approve, "callIds": payload.callIds},
                emit=emit,
                cancel_event=cancel_event,
            )
            conn.commit()
            emit("run", {"runId": result.get("runId", "")})
            _emit_answer_stream(emit, result)
            emit("done", {"messageId": result["messageId"], "traceId": result["traceId"], "runId": result["runId"], "answerPayload": result["answerPayload"]})
            logger.info("Agent approval resume completed session_id=%s run_id=%s message_id=%s", session_id, result["runId"], result["messageId"])
        except AgentCancelled as exc:
            logger.info("Agent approval resume cancelled session_id=%s run_id=%s", session_id, payload.runId)
            conn.commit()
            emit("cancelled", {"message": str(exc) or "已取消本次回答"})
        except BusinessError as exc:
            logger.warning("Agent approval business error session_id=%s run_id=%s code=%s message=%s", session_id, payload.runId, exc.code, exc.message)
            conn.commit()
            if exc.code == "QUERY_PLAN_REJECTED":
                message_id = add_message(
                    conn, session_id, "assistant", exc.message, [],
                    {"type": "directAnswer", "nextSuggestions": [], "process": []},
                )
                conn.commit()
                emit("delta", {"content": exc.message})
                emit("answer", {"type": "directAnswer", "nextSuggestions": [], "process": []})
                emit("done", {"messageId": message_id, "answerPayload": {"type": "directAnswer", "nextSuggestions": [], "process": []}})
            else:
                emit("error", {"code": exc.code, "message": exc.message})
        except Exception as exc:
            logger.exception("Agent approval resume failed session_id=%s run_id=%s error=%s", session_id, payload.runId, exc)
            conn.commit()
            emit("error", {"code": "AGENT_EXECUTION_FAILED", "message": "Agent 恢复执行失败，请查看服务端日志。"})
        finally:
            conn.close()
            events.put(None)

    threading.Thread(target=worker, daemon=True).start()

    def generate() -> Iterator[str]:
        try:
            while True:
                item = events.get()
                if item is None:
                    break
                name, data = item
                yield f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"
        finally:
            cancel_event.set()

    return StreamingResponse(generate(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/qa/sessions/{session_id}/runs")
def runs(session_id: int, conn: Db) -> dict:
    return {"items": list_session_runs(conn, session_id)}


@router.get("/qa/sessions/{session_id}/runs/{run_id}")
def run_detail(session_id: int, run_id: str, conn: Db) -> dict:
    return get_run(conn, session_id, run_id)


@router.get("/qa/sessions/{session_id}/runs/{run_id}/checkpoints")
def run_checkpoints(session_id: int, run_id: str, conn: Db) -> dict:
    get_run(conn, session_id, run_id)
    return {"runId": run_id, "items": list_run_checkpoints(session_id, run_id)}


def _process_item(name: str, data: dict[str, Any]) -> dict[str, Any] | None:
    if name == "skill":
        if data.get("matched"):
            return {"type": "skill", "title": f"命中 Skill：{data.get('name')}", "detail": data.get("description"), "code": data.get("code")}
        return {"type": "skill", "title": "未命中固定 Skill", "detail": data.get("message")}
    if name == "plan":
        calls = data.get("calls") if isinstance(data.get("calls"), list) else []
        return {"type": "plan", "title": "生成查询计划", "detail": data.get("rationale"), "calls": [
            {"stepId": item.get("stepId"), "action": item.get("action", "interface"), "interfaceCode": item.get("interfaceCode"), "purpose": item.get("purpose"), "params": item.get("params", {}), "paramSources": item.get("paramSources", {})}
            for item in calls if isinstance(item, dict)
        ]}
    if name == "interface":
        return {"type": "interface", "title": f"调用接口：{data.get('interfaceCode')}", "detail": data.get("purpose"), "stepId": data.get("stepId"), "params": data.get("params", {})}
    if name == "result":
        return {"type": "result", "title": f"步骤返回：{data.get('interfaceCode')}", "stepId": data.get("stepId"), "rowCount": len(data.get("rows", []) or []), "requestId": data.get("requestId")}
    if name == "node_completed":
        return {"type": "node", "title": f"完成节点：{data.get('label')}", "durationMs": data.get("durationMs")}
    return None


def _emit_answer_stream(emit, result: dict[str, Any]) -> None:
    payload = result["answerPayload"]
    if payload.get("type") == "structuredAnswer":
        _emit_structured_answer(emit, payload)
        return
    text = result["content"]
    if not result.get("streamed"):
        for index in range(0, len(text), 24):
            emit("delta", {"content": text[index:index + 24]})
    emit("answer", payload)


def _emit_structured_answer(emit, payload: dict[str, Any]) -> None:
    cumulative: dict[str, Any] = {
        key: payload[key]
        for key in ("type", "version", "dataFound", "source", "derivedMetrics")
        if key in payload
    }
    if payload.get("process"):
        cumulative["process"] = payload["process"]
        emit("answer", dict(cumulative))
    if payload.get("dataFindings"):
        cumulative["dataFindings"] = payload["dataFindings"]
        emit("answer", dict(cumulative))
    table = payload.get("table") if isinstance(payload.get("table"), dict) else None
    if table and table.get("rows"):
        cumulative["table"] = table
        emit("answer", dict(cumulative))
    if payload.get("resultSets"):
        cumulative["resultSets"] = payload["resultSets"]
        emit("answer", dict(cumulative))
    if payload.get("stats"):
        cumulative["stats"] = payload["stats"]
        emit("answer", dict(cumulative))
    if payload.get("visualization"):
        cumulative["visualization"] = payload["visualization"]
        emit("answer", dict(cumulative))
    if payload.get("nextSuggestions"):
        cumulative["nextSuggestions"] = payload["nextSuggestions"]
    emit("answer", dict(cumulative))
