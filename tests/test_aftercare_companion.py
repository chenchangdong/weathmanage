"""投后陪伴体系 — 监测与话术生成测试。"""

from core.aftercare_companion_service import AftercareCompanionService
from core.aftercare_monitor_service import AftercareMonitorService
from core.config_loader import load_aftercare_system


def test_aftercare_system_config_loads():
    cfg = load_aftercare_system()
    assert len(cfg.get("research_driven", {}).get("rules", [])) == 10
    assert len(cfg.get("product_driven", {}).get("rules", [])) == 17
    assert cfg.get("tag_legend", {}).get("warning")
    assert cfg.get("companion", {}).get("stream_enabled") is True


def test_research_alerts_one_or_two():
    svc = AftercareMonitorService()
    a1 = svc.detect_research_alerts()
    a2 = svc.detect_research_alerts()
    assert a1 == a2
    assert 1 <= len(a1) <= 2


def test_product_alerts_one_or_two():
    svc = AftercareMonitorService()
    alerts = svc.detect_product_alerts("C20250602001")
    assert 1 <= len(alerts) <= 2


def test_companion_generate_item_field():
    monitor = AftercareMonitorService().detect_all("C20250602001")
    alert = monitor["research_alerts"][0]
    result = AftercareCompanionService().generate_item_field(
        "C20250602001", "research", alert["rule_id"], "customer_script"
    )
    assert result["content"]
    assert result["field"] == "customer_script"
