"""规则策略数据存储与执行（对齐 wealthlive /api/rule/*）。"""

from __future__ import annotations

import json
import re
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

from core.sop_rule_engine import evaluate_expression

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "rule_system.json"

_EXPR_EXT = re.compile(
    r"^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*(>=|<=|!=|==|>|<|=)\s*([^\s]+)\s*$"
)


def eval_rule_expr(expr: str, data: dict[str, Any]) -> bool:
    """支持 max_drawdown > 5 与 product_id=aaaa。"""
    expr = (expr or "").strip()
    if not expr:
        return False
    m = _EXPR_EXT.match(expr)
    if not m:
        return evaluate_expression(expr, data)
    field, op, raw = m.group(1), m.group(2), m.group(3)
    if op == "=":
        op = "=="
    val = data.get(field)
    if val is None and field not in data:
        return False
    try:
        threshold = float(raw)
        return evaluate_expression(f"{field} {op} {threshold}", data)
    except ValueError:
        fn_map = {
            "==": lambda a, b: str(a) == str(b),
            "!=": lambda a, b: str(a) != str(b),
        }
        fn = fn_map.get(op)
        if fn:
            return fn(val, raw)
        return False


class RuleSystemService:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or DATA_FILE

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        with open(self.path, encoding="utf-8") as f:
            return json.load(f)

    def _save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def biz_type_label(self, code: str) -> str:
        for bt in self._load().get("biz_types") or []:
            if bt.get("code") == code:
                return bt.get("name") or code
        return code

    # ── 规则配置 ─────────────────────────────────────────────

    def list_rules(self) -> list[dict[str, Any]]:
        return list(self._load().get("rules") or [])

    def add_rule(self, body: dict[str, Any]) -> dict[str, Any]:
        data = self._load()
        rules = data.setdefault("rules", [])
        rid = max((r.get("id", 0) for r in rules), default=0) + 1
        now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        row = {
            "id": rid,
            "rule_code": body["rule_code"],
            "rule_name": body["rule_name"],
            "rule_expr": body["rule_expr"],
            "biz_type": body.get("biz_type", "product_drawdown"),
            "status": int(body.get("status", 1)),
            "short_circuit": int(body.get("short_circuit", 1)),
            "remark": body.get("remark", ""),
            "create_time": now,
            "update_time": now,
        }
        rules.append(row)
        self._save(data)
        return row

    def update_rule(self, rule_id: int, body: dict[str, Any]) -> dict[str, Any] | None:
        data = self._load()
        for r in data.get("rules") or []:
            if r.get("id") == rule_id:
                r.update({k: v for k, v in body.items() if k != "id"})
                r["update_time"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
                self._save(data)
                return r
        return None

    def delete_rule(self, rule_id: int) -> bool:
        data = self._load()
        rules = data.get("rules") or []
        new_rules = [r for r in rules if r.get("id") != rule_id]
        if len(new_rules) == len(rules):
            return False
        data["rules"] = new_rules
        self._save(data)
        return True

    def toggle_rule(self, rule_id: int, enable: bool) -> dict[str, Any] | None:
        return self.update_rule(rule_id, {"status": 1 if enable else 0})

    # ── 指标 ─────────────────────────────────────────────────

    def list_metrics(self) -> list[dict[str, Any]]:
        return list(self._load().get("metrics") or [])

    def add_metric(self, body: dict[str, Any]) -> dict[str, Any]:
        data = self._load()
        metrics = data.setdefault("metrics", [])
        mid = max((m.get("id", 0) for m in metrics), default=0) + 1
        row = {
            "id": mid,
            "metric_code": body["metric_code"],
            "metric_name": body["metric_name"],
            "biz_type": body.get("biz_type", "product_drawdown"),
            "value_field": body["value_field"],
            "remark": body.get("remark", ""),
        }
        metrics.append(row)
        self._save(data)
        return row

    def delete_metric(self, metric_id: int) -> bool:
        data = self._load()
        metrics = data.get("metrics") or []
        new_m = [m for m in metrics if m.get("id") != metric_id]
        if len(new_m) == len(metrics):
            return False
        data["metrics"] = new_m
        self._save(data)
        return True

    # ── 规则分组（biz-type）──────────────────────────────────

    def list_biz_types(self, include_disabled: bool = False) -> list[dict[str, Any]]:
        rows = list(self._load().get("biz_types") or [])
        if not include_disabled:
            rows = [r for r in rows if r.get("status", 1) == 1]
        return sorted(rows, key=lambda x: x.get("sort", 0))

    def add_biz_type(self, body: dict[str, Any]) -> dict[str, Any]:
        data = self._load()
        bts = data.setdefault("biz_types", [])
        bid = max((b.get("id", 0) for b in bts), default=0) + 1
        now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        row = {
            "id": bid,
            "code": body["code"],
            "name": body["name"],
            "remark": body.get("remark", ""),
            "sort": int(body.get("sort", 0)),
            "status": int(body.get("status", 1)),
            "short_circuit": int(body.get("short_circuit", 1)),
            "create_time": now,
            "update_time": now,
        }
        bts.append(row)
        self._save(data)
        return row

    def update_biz_type(self, bid: int, body: dict[str, Any]) -> dict[str, Any] | None:
        data = self._load()
        for b in data.get("biz_types") or []:
            if b.get("id") == bid:
                b.update({k: v for k, v in body.items() if k not in ("id", "code")})
                b["update_time"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
                self._save(data)
                return b
        return None

    def delete_biz_type(self, bid: int) -> bool:
        data = self._load()
        bts = data.get("biz_types") or []
        new_b = [b for b in bts if b.get("id") != bid]
        if len(new_b) == len(bts):
            return False
        data["biz_types"] = new_b
        self._save(data)
        return True

    # ── 事件日志 ─────────────────────────────────────────────

    def list_events(
        self,
        *,
        page: int = 1,
        page_size: int = 15,
        biz_type: str | None = None,
    ) -> dict[str, Any]:
        rows = list(self._load().get("events") or [])
        rows = sorted(rows, key=lambda r: r.get("id", 0), reverse=True)
        if biz_type:
            rows = [r for r in rows if r.get("biz_type") == biz_type]
        total = len(rows)
        start = (page - 1) * page_size
        items = rows[start : start + page_size]
        return {"page": page, "page_size": page_size, "total": total, "items": items}

    def list_run_details(
        self,
        *,
        page: int = 1,
        page_size: int = 15,
        biz_type: str | None = None,
        is_hit: str | None = None,
        rule_code: str | None = None,
    ) -> dict[str, Any]:
        rows = list(self._load().get("run_details") or [])
        rows = sorted(rows, key=lambda r: r.get("id", 0), reverse=True)
        if biz_type:
            rows = [r for r in rows if r.get("biz_type") == biz_type]
        if is_hit not in (None, ""):
            want = int(is_hit)
            rows = [r for r in rows if int(r.get("is_hit", 0)) == want]
        if rule_code:
            rows = [r for r in rows if rule_code in (r.get("rule_code") or "")]
        total = len(rows)
        start = (page - 1) * page_size
        items = rows[start : start + page_size]
        return {"page": page, "page_size": page_size, "total": total, "items": items}

    # ── 出入配置 ─────────────────────────────────────────────

    def list_io_triggers(self) -> list[dict[str, Any]]:
        return list(self._load().get("io_triggers") or [])

    def list_io_actions(self) -> list[dict[str, Any]]:
        return list(self._load().get("io_actions") or [])

    def save_io_trigger(self, body: dict[str, Any], tid: int | None = None) -> dict[str, Any]:
        data = self._load()
        triggers = data.setdefault("io_triggers", [])
        if tid:
            for t in triggers:
                if t.get("id") == tid:
                    t.update(body)
                    self._save(data)
                    return t
        new_id = max((t.get("id", 0) for t in triggers), default=0) + 1
        row = {"id": new_id, **body}
        triggers.append(row)
        self._save(data)
        return row

    def save_io_action(self, body: dict[str, Any], aid: int | None = None) -> dict[str, Any]:
        data = self._load()
        actions = data.setdefault("io_actions", [])
        if aid:
            for a in actions:
                if a.get("id") == aid:
                    a.update(body)
                    self._save(data)
                    return a
        new_id = max((a.get("id", 0) for a in actions), default=0) + 1
        row = {"id": new_id, **body}
        actions.append(row)
        self._save(data)
        return row

    def delete_io_trigger(self, tid: int) -> bool:
        data = self._load()
        triggers = [t for t in data.get("io_triggers") or [] if t.get("id") != tid]
        if len(triggers) == len(data.get("io_triggers") or []):
            return False
        data["io_triggers"] = triggers
        self._save(data)
        return True

    def delete_io_action(self, aid: int) -> bool:
        data = self._load()
        actions = [a for a in data.get("io_actions") or [] if a.get("id") != aid]
        if len(actions) == len(data.get("io_actions") or []):
            return False
        data["io_actions"] = actions
        self._save(data)
        return True

    # ── 执行 / 测试 ──────────────────────────────────────────

    def execute_rules(
        self, biz_type: str, biz_no: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        data = self._load()
        rules = [
            r
            for r in data.get("rules") or []
            if r.get("biz_type") == biz_type and r.get("status", 1) == 1
        ]
        rules.sort(key=lambda r: r.get("id", 0))
        metrics = dict(payload)
        details: list[dict[str, Any]] = []
        hit_any = False
        hit_rule: dict[str, Any] | None = None
        now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

        for i, rule in enumerate(rules):
            hit = eval_rule_expr(rule.get("rule_expr", ""), metrics)
            msg = (
                f"规则「{rule['rule_name']}」命中，表达式成立"
                if hit
                else ("开始校验" if not hit_any else None)
            )
            details.append(
                {
                    "rule_id": rule["id"],
                    "rule_code": rule["rule_code"],
                    "rule_name": rule["rule_name"],
                    "rule_expr": rule["rule_expr"],
                    "sort": i + 1,
                    "hit": hit,
                    "message": msg,
                }
            )
            if hit and not hit_any:
                hit_any = True
                hit_rule = rule
            if hit and rule.get("short_circuit", 1):
                break

        run_id = int(data.get("next_run_id") or 1)
        event_id = int(data.get("next_event_id") or 1)
        run_detail_rows: list[dict[str, Any]] = []

        for d in details:
            run_detail_rows.append(
                {
                    "id": len(data.get("run_details") or []) + len(run_detail_rows) + 1,
                    "run_id": run_id,
                    "rule_id": d["rule_id"],
                    "rule_code": d["rule_code"],
                    "rule_name": d["rule_name"],
                    "rule_expr": d["rule_expr"],
                    "biz_no": biz_no,
                    "biz_type": biz_type,
                    "is_hit": 1 if d["hit"] else 0,
                    "short_circuit": 1,
                    "sort": d["sort"],
                    "trigger_msg": d["message"] or "",
                    "hit_snapshot": None,
                    "trigger_time": now,
                    "create_time": now,
                }
            )

        if hit_rule:
            evt = {
                "id": event_id,
                "rule_code": hit_rule["rule_code"],
                "biz_type": biz_type,
                "rule_id": hit_rule["id"],
                "trigger_msg": f"规则'{hit_rule['rule_name']}'命中，表达式成立",
                "biz_no": biz_no,
                "trigger_data": deepcopy(metrics),
                "trigger_time": now,
            }
            data.setdefault("events", []).insert(0, evt)
            data["next_event_id"] = event_id + 1

        data.setdefault("run_details", []).insert(0, *reversed(run_detail_rows))
        data["next_run_id"] = run_id + 1
        self._save(data)

        message = (
            f"规则'{hit_rule['rule_name']}'命中，表达式成立"
            if hit_rule
            else "无规则命中"
        )
        return {
            "hit": hit_any,
            "hit_count": sum(1 for d in details if d["hit"]),
            "total_count": len(details),
            "message": message,
            "event_id": event_id if hit_rule else None,
            "run_id": run_id,
            "details": details,
            "action_count": 1 if hit_any else 0,
            "actions": (
                [
                    {
                        "rule_id": hit_rule["id"],
                        "action": "CREATE_EVENT",
                        "result": {"ok": True, "event_id": event_id},
                    }
                ]
                if hit_rule
                else []
            ),
            "legacy": {"triggered": hit_any},
        }

    def test_expression(self, expr: str, test_data: dict[str, Any]) -> dict[str, Any]:
        try:
            result = eval_rule_expr(expr, test_data)
            return {"result": result, "expr": expr, "test_data": test_data}
        except Exception as e:
            return {"result": False, "error": str(e), "expr": expr}
