"""对客话术口吻转换。"""

from core.sop_client_voice import contains_advisor_voice, to_client_voice


class TestSopClientVoice:
    def test_yield_fixed_income_advisor_phrase(self):
        raw = "固收类产品收益短期波动常见，建议与客户沟通收益偏离原因并跟踪后续修复情况。"
        out = to_client_voice(raw)
        assert "建议与客户" not in out
        assert "与客户沟通" not in out
        assert not contains_advisor_voice(out)

    def test_high_level_drawdown_advisor_phrase(self):
        raw = "建议与客户充分沟通回撤原因，短期以安抚为主，暂不主动建议大幅调仓。"
        out = to_client_voice(raw)
        assert "建议与客户" not in out
        assert "您" in out
