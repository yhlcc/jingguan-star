from __future__ import annotations

import logging
import time
import uuid

from app.agent.cancel import AgentCancelled, ensure_not_cancelled
from app.agent.context import AgentContext
from app.agent.state import AgentState
from app.agent.step_ops import apply_transform, resolve_params
from app.repositories.audits import write_audit


logger = logging.getLogger(__name__)


def multi_interface_execute(context: AgentContext, state: AgentState) -> dict:
    results, errors = [], []
    step_outputs: dict[str, dict[str, Any]] = {}
    for call in state.get("approved_calls", []):
        ensure_not_cancelled(context)
        step_id = str(call.get("stepId") or call.get("callId") or f"step{len(step_outputs) + 1}")
        action = str(call.get("action") or "interface")
        missing = [item for item in call.get("dependsOn", []) if item not in step_outputs]
        if missing:
            errors.append({"callId": call.get("callId"), "stepId": step_id, "message": f"前置步骤尚未完成：{', '.join(missing)}"})
            continue
        if action in {"derive", "transform"}:
            try:
                ensure_not_cancelled(context)
                derived = apply_transform(step_id, dict(call.get("transform") or {}), step_outputs)
                derived["callId"] = call.get("callId")
                derived["purpose"] = call.get("purpose")
                step_outputs[step_id] = derived
                results.append(derived)
                context.emit("result", {"callId": call.get("callId"), **derived})
            except AgentCancelled:
                raise
            except Exception as exc:
                errors.append({"callId": call.get("callId"), "stepId": step_id, "message": str(exc)})
                logger.exception("Skill transform failed session_id=%s trace_id=%s step_id=%s error=%s", state.get("session_id"), state.get("trace_id"), step_id, exc)
            continue
        code = str(call["interfaceCode"]); started = time.perf_counter(); request_id = str(uuid.uuid4()); params: dict[str, Any] = {}
        try:
            ensure_not_cancelled(context)
            params = context.gateway.approve(code, resolve_params(call, state, step_outputs))
            context.emit("interface", {"callId": call.get("callId"), "stepId": step_id, "interfaceCode": code, "params": params, "purpose": call.get("purpose")})
            ensure_not_cancelled(context)
            result = context.gateway.execute(code, params); result["callId"] = call.get("callId"); result["stepId"] = step_id; result["purpose"] = call.get("purpose"); request_id = result["requestId"]
            step_outputs[step_id] = result
            results.append(result)
            write_audit(context.conn, request_id=request_id, session_id=state.get("session_id"), interface_code=code, params=params, row_count=len(result.get("rows", [])), duration_ms=result["trace"]["durationMs"], status="成功")
            logger.info("Interface executed session_id=%s trace_id=%s interface_code=%s request_id=%s row_count=%s duration_ms=%s", state.get("session_id"), state.get("trace_id"), code, request_id, len(result.get("rows", [])), result["trace"]["durationMs"])
            context.emit("result", {"callId": call.get("callId"), **result})
        except AgentCancelled:
            raise
        except Exception as exc:
            duration = round((time.perf_counter() - started) * 1000)
            errors.append({"callId": call.get("callId"), "stepId": step_id, "interfaceCode": code, "message": str(exc)})
            write_audit(context.conn, request_id=request_id, session_id=state.get("session_id"), interface_code=code, params=params, row_count=0, duration_ms=duration, status="失败", error=str(exc))
            logger.exception("Interface execution failed session_id=%s trace_id=%s interface_code=%s request_id=%s duration_ms=%s error=%s", state.get("session_id"), state.get("trace_id"), code, request_id, duration, exc)
    return {"execution_results": results, "execution_errors": errors, "step_outputs": step_outputs}
