from __future__ import annotations

import sqlite3
import time
import uuid
from collections.abc import Callable
from typing import Any

from app.core.errors import BusinessError
from app.repositories.catalog import allowed_fields, allowed_params, get_interface
from app.repositories.common import clamp_page_size, loads
from app.services.interface_registry import EXECUTABLE_INTERFACE_CODES


DATA_AS_OF = "2026-05-31"


class QueryGateway:
    """The only component allowed to dispatch business-data queries."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.handlers: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
            "biz.dashboard.summary": self._dashboard,
            "biz.unitAchievement.query": self._unit_achievement,
            "biz.productLine.analysis": self._product_lines,
            "biz.productModel.breakdown": self._product_models,
            "biz.industryAchievement.query": self._industries,
            "biz.keyUnitProduct.analysis": self._key_unit_products,
            "ledger.pplRisk.summary": self._ppl_risk,
            "ledger.commercial.aggregate": self._commercial_aggregate,
            "ledger.commercial.detail": self._commercial_detail,
            "ledger.ppl.detail": self._ppl_detail,
            "ledger.goal.query": self._goals,
        }

    def approve(self, code: str, params: dict[str, Any]) -> dict[str, Any]:
        self.ensure_executable(code)
        specs = allowed_params(self.conn, code)
        clean: dict[str, Any] = {}
        merged = dict(params)
        filters = merged.get("filters", {})
        if isinstance(filters, dict) and "filters" not in specs:
            merged.pop("filters", None)
            merged = {**filters, **merged}
        forbidden = [key for key in merged if key not in specs and key not in {"pageSize", "sessionId"}]
        if forbidden:
            raise BusinessError("PARAM_NOT_ALLOWED", f"接口 {code} 不允许参数：{', '.join(forbidden)}")
        for name, spec in specs.items():
            value = merged.get(name, spec.get("defaultValue"))
            if spec.get("required") and value in (None, "", []):
                if name == "year": value = 2026
                else: raise BusinessError("MISSING_REQUIRED_PARAM", f"接口 {code} 缺少必填参数 {name}")
            if value not in (None, "", []):
                clean[name] = validate_param_value(code, name, value, spec)
        clean["pageSize"] = clamp_page_size(merged.get("pageSize", 50))
        if "sessionId" in merged: clean["sessionId"] = merged["sessionId"]
        return clean

    def ensure_executable(self, code: str) -> None:
        detail = get_interface(self.conn, code)
        if detail["status"] != "启用":
            raise BusinessError("INTERFACE_DISABLED", f"接口 {code} 未启用")
        if code not in EXECUTABLE_INTERFACE_CODES or code not in self.handlers:
            raise BusinessError("INTERFACE_NOT_IMPLEMENTED", f"接口 {code} 没有注册查询处理器")

    def execute(self, code: str, params: dict[str, Any]) -> dict[str, Any]:
        started = time.perf_counter()
        result = self.handlers[code](params)
        result.update({"requestId": str(uuid.uuid4()), "interfaceCode": code, "dataAsOf": DATA_AS_OF})
        result["trace"] = {"durationMs": round((time.perf_counter() - started) * 1000), "rowCount": len(result.get("rows", []))}
        return result

    def _columns(self, code: str) -> list[dict[str, Any]]:
        return allowed_fields(self.conn, code)

    @staticmethod
    def _list(value: Any) -> list[str]:
        if isinstance(value, list): return [str(x) for x in value if str(x)]
        if isinstance(value, str): return [x.strip() for x in value.split(",") if x.strip()]
        return []

    @staticmethod
    def _in(values: list[Any]) -> str:
        return ",".join("?" for _ in values)

    def _dashboard(self, params: dict[str, Any]) -> dict[str, Any]:
        year = int(params.get("year", 2026))
        units = self.conn.execute("SELECT * FROM rpt_unit_achievement WHERE year=? ORDER BY income_amount DESC", (year,)).fetchall()
        target = sum(float(x["target_amount"]) for x in units); income = sum(float(x["income_amount"]) for x in units); old = sum(float(x["old_income_amount"]) for x in units)
        risk = self.conn.execute("SELECT COUNT(*) FROM ledger_ppl_pipeline WHERE risk_level='高'").fetchone()[0]
        row = {"metric": "经营总览", "totalTargetAmount": round(target, 2), "totalIncomeAmount": round(income, 2),
               "completionRate": round(income / target * 100, 2) if target else 0, "yoyRate": round((income-old)/old*100, 2) if old else 0, "riskProjectCount": risk}
        products = [dict(x) for x in self.conn.execute("SELECT product_line_name name,amount value,yoy_rate yoyRate FROM rpt_product_line_summary WHERE year=? ORDER BY amount DESC", (year,)).fetchall()]
        industries = [dict(x) for x in self.conn.execute("SELECT industry_name name,income_amount value,yoy_rate yoyRate FROM rpt_industry_achievement WHERE year=? ORDER BY income_amount DESC LIMIT 5", (year,)).fetchall()]
        return {"columns": self._columns("biz.dashboard.summary"), "rows": [row], "summary": row,
                "charts": {"productLineMix": products, "industryTop": industries, "unitRank": [{"name": x["org_unit_name"], "value": x["income_amount"], "rate": x["completion_rate"]} for x in units[:8]]}}

    def _unit_achievement(self, params: dict[str, Any]) -> dict[str, Any]:
        year = int(params.get("year", 2026)); names = self._list(params.get("unitNames")); values: list[Any] = [year]
        sql = "SELECT * FROM rpt_unit_achievement WHERE year=?"
        if names: sql += f" AND org_unit_name IN ({self._in(names)})"; values.extend(names)
        rows = self.conn.execute(sql + " ORDER BY income_amount DESC", values).fetchall()
        data = [{"orgUnitName": x["org_unit_name"], "targetAmount": x["target_amount"], "incomeAmount": x["income_amount"], "yoyRate": x["yoy_rate"], "completionRate": x["completion_rate"], "productLineMix": loads(x["product_line_mix"], [])} for x in rows]
        return {"columns": self._columns("biz.unitAchievement.query"), "rows": data, "summary": {"totalTargetAmount": round(sum(float(x["targetAmount"]) for x in data), 2), "totalIncomeAmount": round(sum(float(x["incomeAmount"]) for x in data), 2)}}

    def _product_lines(self, params: dict[str, Any]) -> dict[str, Any]:
        year = int(params.get("year", 2026)); names = self._list(params.get("productLines")); values: list[Any] = [year]
        sql = "SELECT * FROM rpt_product_line_summary WHERE year=?"
        if names: sql += f" AND product_line_name IN ({self._in(names)})"; values.extend(names)
        rows = self.conn.execute(sql + " ORDER BY amount DESC", values).fetchall()
        data = [{"productLine": x["product_line_name"], "amount": x["amount"], "compareAmount": x["compare_amount"], "yoyRate": x["yoy_rate"], "modelBreakdown": []} for x in rows]
        return {"columns": self._columns("biz.productLine.analysis"), "rows": data, "summary": {"totalAmount": sum(float(x["amount"]) for x in data)}}

    def _product_models(self, params: dict[str, Any]) -> dict[str, Any]:
        year = int(params.get("year", 2026)); lines = self._list(params.get("productLines")); models = self._list(params.get("modelNames")); values: list[Any] = [year]
        sql = "SELECT * FROM rpt_product_model_breakdown WHERE year=?"
        if lines: sql += f" AND product_line_name IN ({self._in(lines)})"; values.extend(lines)
        if models: sql += f" AND product_model_name IN ({self._in(models)})"; values.extend(models)
        rows = self.conn.execute(sql + " ORDER BY amount DESC", values).fetchall(); total = sum(float(x["amount"]) for x in rows)
        data = [{"productLine": x["product_line_name"], "modelName": x["product_model_name"], "amount": x["amount"], "compareAmount": x["compare_amount"], "shareRate": round(float(x["amount"])/total*100,2) if total else 0} for x in rows]
        return {"columns": self._columns("biz.productModel.breakdown"), "rows": data, "summary": {"totalAmount": total}}

    def _industries(self, params: dict[str, Any]) -> dict[str, Any]:
        year = int(params.get("year", 2026)); names = self._list(params.get("industryNames")); values: list[Any] = [year]
        sql = "SELECT * FROM rpt_industry_achievement WHERE year=?"
        if names: sql += f" AND industry_name IN ({self._in(names)})"; values.extend(names)
        rows = self.conn.execute(sql + " ORDER BY income_amount DESC", values).fetchall()
        data = [{"industryName": x["industry_name"], "incomeAmount": x["income_amount"], "yoyRate": x["yoy_rate"], "forecastAmount": x["q2_forecast_amount"], "productLineRatio": {"通用计算": x["general_compute_amount"], "智能计算": x["intelligent_compute_amount"], "商业解决方案": x["business_solution_amount"]}} for x in rows]
        return {"columns": self._columns("biz.industryAchievement.query"), "rows": data, "summary": {"totalIncomeAmount": sum(float(x["incomeAmount"]) for x in data)}}

    def _key_unit_products(self, params: dict[str, Any]) -> dict[str, Any]:
        year = int(params.get("year", 2026)); units = self._list(params.get("unitNames")); lines = self._list(params.get("productLines")); values: list[Any] = [year]
        sql = "SELECT * FROM rpt_key_unit_product_analysis WHERE year=?"
        if units: sql += f" AND org_unit_name IN ({self._in(units)})"; values.extend(units)
        if lines: sql += f" AND product_line_name IN ({self._in(lines)})"; values.extend(lines)
        rows = self.conn.execute(sql + " ORDER BY amount DESC", values).fetchall()
        data = [{"unitName": x["org_unit_name"], "productLine": x["product_line_name"], "amount": x["amount"], "yoyRate": x["yoy_rate"], "analysisText": x["analysis_text"]} for x in rows]
        return {"columns": self._columns("biz.keyUnitProduct.analysis"), "rows": data, "summary": {"totalAmount": sum(float(x["amount"]) for x in data)}}

    def _ppl_risk(self, params: dict[str, Any]) -> dict[str, Any]:
        risks = self._list(params.get("riskLevels")); units = self._list(params.get("unitNames")); stages = self._list(params.get("projectStages")); where = ["1=1"]; values: list[Any] = []
        for column, items in [("risk_level", risks), ("org_unit_name", units), ("project_stage", stages)]:
            if items: where.append(f"{column} IN ({self._in(items)})"); values.extend(items)
        rows = self.conn.execute(f"""SELECT risk_level,project_stage,org_unit_name,COUNT(*) project_count,SUM(amount) amount FROM ledger_ppl_pipeline
                                   WHERE {' AND '.join(where)} GROUP BY risk_level,project_stage,org_unit_name ORDER BY amount DESC LIMIT ?""", (*values, params["pageSize"])).fetchall()
        data = [{"riskLevel": x["risk_level"], "projectCount": x["project_count"], "amount": x["amount"], "stage": x["project_stage"], "unitName": x["org_unit_name"]} for x in rows]
        return {"columns": self._columns("ledger.pplRisk.summary"), "rows": data, "summary": {"projectCount": sum(x["projectCount"] for x in data), "amount": sum(float(x["amount"] or 0) for x in data)}}

    def _commercial_aggregate(self, params: dict[str, Any]) -> dict[str, Any]:
        dimensions = self._list(params.get("dimensions")) or ["unitName"]
        dimension_map = {"unitName": "org_unit_name", "industryName": "industry_name", "productLine": "product_line_code", "province": "province", "customerLevel": "customer_level"}
        metric_map = {"incomeAmount": "SUM(recognized_amount)", "orderAmount": "SUM(order_amount)", "receivedAmount": "SUM(collected_amount)", "unreceivedAmount": "SUM(uncollected_amount)", "recordCount": "COUNT(*)"}
        if any(x not in dimension_map for x in dimensions): raise BusinessError("PARAM_NOT_ALLOWED", "存在不受支持的聚合维度")
        metrics = self._list(params.get("metrics")) or ["incomeAmount", "orderAmount", "receivedAmount", "recordCount"]
        if any(x not in metric_map for x in metrics): raise BusinessError("PARAM_NOT_ALLOWED", "存在不受支持的聚合指标")
        filters = params.get("filters") if isinstance(params.get("filters"), dict) else {}
        where = ["year=?"]; values: list[Any] = [int(params.get("year", 2026))]
        filter_map = {"unitNames": "org_unit_name", "industryNames": "industry_name", "productLines": "product_line_code"}
        for key, column in filter_map.items():
            items = self._list(filters.get(key))
            if items:
                where.append(f"{column} IN ({self._in(items)})")
                values.extend(items)
        keyword = str(filters.get("keyword") or "").strip()
        if keyword:
            where.append("(contract_name LIKE ? OR buyer_name LIKE ? OR contract_no LIKE ?)")
            values.extend([f"%{keyword}%"] * 3)
        cols = [dimension_map[x] for x in dimensions]; selects = cols + [f"{metric_map[x]} AS {x}" for x in metrics]
        rows = self.conn.execute(f"SELECT {','.join(selects)} FROM ledger_commercial_contract WHERE {' AND '.join(where)} GROUP BY {','.join(cols)} ORDER BY 1 LIMIT ?", (*values, params["pageSize"])).fetchall()
        data = [{"dimensionValues": {name: row[column] for name, column in zip(dimensions, cols)}, **{metric: row[metric] for metric in metrics}} for row in rows]
        return {"columns": self._columns("ledger.commercial.aggregate"), "rows": data, "summary": {"groupCount": len(data)}}

    def _commercial_detail(self, params: dict[str, Any]) -> dict[str, Any]:
        where = ["year=?"]; values: list[Any] = [int(params.get("year", 2026))]
        for param, column in [("unitNames", "org_unit_name"), ("industryNames", "industry_name"), ("productLines", "product_line_code")]:
            items = self._list(params.get(param))
            if items:
                where.append(f"{column} IN ({self._in(items)})")
                values.extend(items)
        keyword = str(params.get("keyword") or "").strip()
        if keyword:
            where.append("(contract_no LIKE ? OR contract_name LIKE ? OR buyer_name LIKE ?)")
            values.extend([f"%{keyword}%"] * 3)
        rows = self.conn.execute(f"SELECT contract_no,contract_name,buyer_name,recognized_amount,order_amount,collected_amount FROM ledger_commercial_contract WHERE {' AND '.join(where)} ORDER BY recognized_amount DESC LIMIT ?", (*values, params["pageSize"])).fetchall()
        data = [{"contractNo": x[0], "contractName": x[1], "buyerName": mask_name(x[2]), "incomeAmount": x[3], "orderAmount": x[4], "collectedAmount": x[5]} for x in rows]
        return {"columns": self._columns("ledger.commercial.detail"), "rows": data, "summary": {"rowCount": len(data)}}

    def _ppl_detail(self, params: dict[str, Any]) -> dict[str, Any]:
        where = ["1=1"]; values: list[Any] = []
        for param, column in [("unitNames", "org_unit_name"), ("riskLevels", "risk_level"), ("projectStages", "project_stage")]:
            items = self._list(params.get(param))
            if items:
                where.append(f"{column} IN ({self._in(items)})")
                values.extend(items)
        keyword = str(params.get("keyword") or "").strip()
        if keyword:
            where.append("(project_name LIKE ? OR contract_no LIKE ? OR final_customer_name LIKE ?)")
            values.extend([f"%{keyword}%"] * 3)
        rows = self.conn.execute(f"SELECT project_name,org_unit_name,risk_level,amount,project_stage,progress_risk_desc FROM ledger_ppl_pipeline WHERE {' AND '.join(where)} ORDER BY amount DESC LIMIT ?", (*values, params["pageSize"])).fetchall()
        data = [{"projectName": x[0], "unitName": x[1], "riskLevel": x[2], "amount": x[3], "stage": x[4], "riskDesc": x[5]} for x in rows]
        return {"columns": self._columns("ledger.ppl.detail"), "rows": data, "summary": {"rowCount": len(data)}}

    def _goals(self, params: dict[str, Any]) -> dict[str, Any]:
        names = self._list(params.get("unitNames")); values: list[Any] = [int(params.get("year", 2026))]
        where = ["year=?"]
        if names:
            where.append(f"org_unit_name IN ({self._in(names)})")
            values.extend(names)
        rows = self.conn.execute(f"SELECT org_unit_name,commercial_target_amount,solution_target_amount FROM ledger_goal_target WHERE {' AND '.join(where)} ORDER BY commercial_target_amount DESC LIMIT ?", (*values, params["pageSize"])).fetchall()
        data = [{"unitName": x[0], "commercialTargetAmount": x[1], "solutionTargetAmount": x[2]} for x in rows]
        return {"columns": self._columns("ledger.goal.query"), "rows": data, "summary": {"rowCount": len(data)}}


def mask_name(value: Any) -> str:
    text = str(value or "")
    return f"{text[:1]}***{text[-1:]}" if len(text) > 2 else "***"


def validate_param_value(code: str, name: str, value: Any, spec: dict[str, Any]) -> Any:
    param_type = str(spec.get("type") or "string")
    try:
        if param_type == "int":
            value = int(value)
            if name == "year" and not 2000 <= value <= 2100:
                raise ValueError
        elif param_type == "boolean":
            value = _coerce_bool(value)
        elif param_type == "object":
            if not isinstance(value, dict):
                raise ValueError
        elif param_type.endswith("[]"):
            value = QueryGateway._list(value)
        elif param_type == "string":
            value = str(value).strip()
    except (TypeError, ValueError):
        raise BusinessError("PARAM_TYPE_INVALID", f"接口 {code} 参数 {name} 类型应为 {param_type}")

    enum_values = spec.get("enumJson")
    if isinstance(enum_values, list) and enum_values:
        candidates = value if isinstance(value, list) else [value]
        invalid = [item for item in candidates if item not in enum_values]
        if invalid:
            raise BusinessError("PARAM_ENUM_INVALID", f"接口 {code} 参数 {name} 存在非法取值：{', '.join(map(str, invalid))}")
    if name == "riskLevels":
        invalid = [item for item in QueryGateway._list(value) if item not in {"高", "中", "低"}]
        if invalid:
            raise BusinessError("PARAM_ENUM_INVALID", f"接口 {code} 参数 {name} 存在非法取值：{', '.join(invalid)}")
    return value


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, str) and value.lower() in {"true", "false", "1", "0"}:
        return value.lower() in {"true", "1"}
    raise ValueError
