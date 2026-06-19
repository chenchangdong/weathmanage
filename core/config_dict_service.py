"""可视化数据字典 — 读取 / 保存 config 模块。"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from core.config_dict_registry import CONFIG_DICT_TREE, MODULE_META
from core.config_loader import CONFIG_DIR, reload_all_configs


def _load_file(name: str) -> Dict[str, Any]:
    path = CONFIG_DIR / name
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _save_file(name: str, data: Dict[str, Any]) -> None:
    path = CONFIG_DIR / name
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    reload_all_configs()


def _get_nested(data: Dict[str, Any], dotted: str) -> Any:
    cur: Any = data
    for part in dotted.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _set_nested(data: Dict[str, Any], dotted: str, value: Any) -> None:
    parts = dotted.split(".")
    cur = data
    for part in parts[:-1]:
        if part not in cur or not isinstance(cur[part], dict):
            cur[part] = {}
        cur = cur[part]
    cur[parts[-1]] = value


def _split_csv(text: Any) -> List[str]:
    if text is None or text == "":
        return []
    if isinstance(text, list):
        return [str(x).strip() for x in text if str(x).strip()]
    return [x.strip() for x in str(text).split(",") if x.strip()]


def get_tree() -> List[Dict[str, Any]]:
    return copy.deepcopy(CONFIG_DICT_TREE)


def get_module_meta(module_id: str) -> Dict[str, Any]:
    if module_id not in MODULE_META:
        raise ValueError(f"未知配置模块: {module_id}")
    meta = copy.deepcopy(MODULE_META[module_id])
    meta["module_id"] = module_id
    return meta


def _load_table_rows(module_id: str) -> List[Dict[str, Any]]:
    if module_id == "four_money_categories":
        cats = _load_file("four_money_rule.yaml").get("categories", {})
        return [
            {
                "code": code,
                "name": info.get("name", ""),
                "icon": info.get("icon", ""),
                "description": info.get("description", ""),
                "priority": info.get("priority", 0),
            }
            for code, info in cats.items()
        ]

    if module_id == "asset_type_alias":
        aliases = _load_file("four_money_mapping.yaml").get("asset_alias", {})
        return [{"code": k, "name": v} for k, v in aliases.items()]

    if module_id == "category_code_map":
        m = _load_file("four_money_mapping.yaml").get("category_code_map", {})
        return [{"four_money_key": k, "engine_code": v} for k, v in m.items()]

    if module_id == "four_money_asset_bind":
        rules = _load_file("four_money_mapping.yaml").get("four_money_rule", {})
        rows = []
        for key, rule in rules.items():
            rows.append(
                {
                    "key": key,
                    "asset_types": ", ".join(rule.get("asset_type", [])),
                    "threshold_aggregate": rule.get("threshold_aggregate", ""),
                }
            )
        return rows

    if module_id == "allocation_view_profiles":
        profiles = _load_file("allocation_view.yaml").get("view_profiles", {})
        rows = []
        for name, prof in profiles.items():
            rows.append(
                {
                    "profile_name": name,
                    "view_mode": prof.get("view_mode", "four_money"),
                    "card_keys": ", ".join(prof.get("card_keys", [])),
                    "excluded_asset_types": ", ".join(prof.get("excluded_asset_types", []) or []),
                }
            )
        return rows

    if module_id == "category_card_labels":
        cards = _load_file("four_money_page.yaml").get("category_cards", {})
        return [
            {"category": cat, "title": info.get("title", ""), "subtitle": info.get("subtitle", "")}
            for cat, info in cards.items()
        ]

    raise ValueError(f"模块不支持 table 视图: {module_id}")


def _load_form_values(module_id: str) -> Dict[str, Any]:
    meta = MODULE_META[module_id]
    file_name = meta["file"]
    data = _load_file(file_name)
    values: Dict[str, Any] = {}

    for section in meta.get("sections", []):
        prefix = section.get("prefix", "")
        for field in section.get("fields", []):
            fk = field["key"]
            path = f"{prefix}.{fk}" if prefix else fk
            val = _get_nested(data, path)
            if field.get("list"):
                values[path] = ", ".join(str(x) for x in (val or []))
            elif field.get("type") == "boolean":
                values[path] = bool(val)
            else:
                values[path] = val if val is not None else ""

    return values


def load_module(module_id: str) -> Dict[str, Any]:
    meta = get_module_meta(module_id)
    payload: Dict[str, Any] = {
        "module_id": module_id,
        "view_type": meta["view_type"],
        "file": meta["file"],
        "desc": meta.get("desc", ""),
    }
    if meta["view_type"] == "table":
        payload["columns"] = meta.get("columns", [])
        payload["id_key"] = meta.get("id_key", "code")
        payload["rows"] = _load_table_rows(module_id)
    else:
        payload["sections"] = meta.get("sections", [])
        payload["values"] = _load_form_values(module_id)
    return payload


def _save_table_rows(module_id: str, rows: List[Dict[str, Any]]) -> None:
    if module_id == "four_money_categories":
        data = _load_file("four_money_rule.yaml")
        categories: Dict[str, Any] = {}
        for row in rows:
            code = (row.get("code") or "").strip()
            if not code:
                continue
            categories[code] = {
                "code": code,
                "name": row.get("name", ""),
                "icon": row.get("icon", ""),
                "description": row.get("description", ""),
                "priority": int(row.get("priority") or 0),
            }
        data["categories"] = categories
        _save_file("four_money_rule.yaml", data)
        return

    if module_id == "asset_type_alias":
        data = _load_file("four_money_mapping.yaml")
        data["asset_alias"] = {r["code"]: r["name"] for r in rows if r.get("code")}
        _save_file("four_money_mapping.yaml", data)
        return

    if module_id == "category_code_map":
        data = _load_file("four_money_mapping.yaml")
        data["category_code_map"] = {
            r["four_money_key"]: r["engine_code"] for r in rows if r.get("four_money_key")
        }
        _save_file("four_money_mapping.yaml", data)
        return

    if module_id == "four_money_asset_bind":
        data = _load_file("four_money_mapping.yaml")
        rules: Dict[str, Any] = {}
        for row in rows:
            key = (row.get("key") or "").strip()
            if not key:
                continue
            item: Dict[str, Any] = {"asset_type": _split_csv(row.get("asset_types"))}
            agg = (row.get("threshold_aggregate") or "").strip()
            if agg:
                item["threshold_aggregate"] = agg
            rules[key] = item
        data["four_money_rule"] = rules
        _save_file("four_money_mapping.yaml", data)
        return

    if module_id == "allocation_view_profiles":
        data = _load_file("allocation_view.yaml")
        profiles: Dict[str, Any] = {}
        for row in rows:
            name = (row.get("profile_name") or "").strip()
            if not name:
                continue
            prof: Dict[str, Any] = {
                "view_mode": row.get("view_mode") or "four_money",
                "card_keys": _split_csv(row.get("card_keys")),
            }
            excluded = _split_csv(row.get("excluded_asset_types"))
            if excluded:
                prof["excluded_asset_types"] = excluded
            profiles[name] = prof
        data["view_profiles"] = profiles
        _save_file("allocation_view.yaml", data)
        return

    if module_id == "category_card_labels":
        data = _load_file("four_money_page.yaml")
        cards = data.get("category_cards", {})
        for row in rows:
            cat = (row.get("category") or "").strip()
            if not cat:
                continue
            if cat not in cards:
                cards[cat] = {}
            cards[cat]["title"] = row.get("title", "")
            cards[cat]["subtitle"] = row.get("subtitle", "")
        data["category_cards"] = cards
        _save_file("four_money_page.yaml", data)
        return

    raise ValueError(f"模块不支持 table 保存: {module_id}")


def _save_form_values(module_id: str, values: Dict[str, Any]) -> None:
    meta = MODULE_META[module_id]
    file_name = meta["file"]
    data = _load_file(file_name)

    for section in meta.get("sections", []):
        prefix = section.get("prefix", "")
        for field in section.get("fields", []):
            if field.get("readonly"):
                continue
            fk = field["key"]
            path = f"{prefix}.{fk}" if prefix else fk
            if path not in values:
                continue
            raw = values[path]
            ftype = field.get("type", "text")
            if field.get("list"):
                val: Any = _split_csv(raw)
            elif ftype == "boolean":
                val = bool(raw)
            elif ftype == "number":
                try:
                    val = float(raw) if "." in str(raw) else int(raw)
                except (TypeError, ValueError):
                    val = raw
            else:
                val = raw
            _set_nested(data, path, val)

    if module_id == "solver_params":
        _save_file("four_money_rule.yaml", data)
    elif module_id == "page_constraint":
        _save_file("page_constraint.yaml", data)
    elif module_id == "page_header_health":
        _save_file("four_money_page.yaml", data)
    elif module_id == "llm_config":
        _save_file("llm_config.yaml", data)
    else:
        _save_file(file_name, data)


def save_module(module_id: str, body: Dict[str, Any]) -> Dict[str, Any]:
    meta = MODULE_META.get(module_id)
    if not meta:
        raise ValueError(f"未知配置模块: {module_id}")

    if meta["view_type"] == "table":
        rows = body.get("rows")
        if not isinstance(rows, list):
            raise ValueError("缺少 rows 数组")
        _save_table_rows(module_id, rows)
    else:
        values = body.get("values")
        if not isinstance(values, dict):
            raise ValueError("缺少 values 对象")
        _save_form_values(module_id, values)

    return load_module(module_id)
