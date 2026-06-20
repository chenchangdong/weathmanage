"""6.2.4 对客话术 — 将投研/经理向表述转为可直接转发客户的口吻。"""

from __future__ import annotations

import re

# 明显面向理财经理的措辞（出现在对客话术中即需改写）
_ADVISOR_MARKERS = (
    "建议与客户",
    "与客户沟通",
    "向客户说明",
    "客户沟通",
    "理财经理",
    "一线触达",
)

_REPLACEMENTS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"建议与客户充分沟通[^，。；\n]*，?"),
        "",
    ),
    (
        re.compile(r"建议与客户沟通[^，。；\n]*，?"),
        "我们会及时向您说明相关情况，",
    ),
    (
        re.compile(r"与客户充分沟通[^，。；\n]*，?"),
        "",
    ),
    (
        re.compile(r"与客户沟通"),
        "向您说明",
    ),
    (
        re.compile(r"跟踪后续修复情况"),
        "持续跟踪产品后续表现",
    ),
    (
        re.compile(r"短期以安抚为主，暂不主动建议大幅调仓"),
        "建议您先保持持有观察，如有需要我们再与您沟通调仓安排",
    ),
    (
        re.compile(r"短期以持有观察为主"),
        "建议您短期保持持有观察",
    ),
    (
        re.compile(r"建议持有观察"),
        "建议您保持持有观察",
    ),
    (
        re.compile(r"建议评估是否超出产品风险收益特征"),
        "建议您关注是否仍在产品正常的波动区间内",
    ),
    (
        re.compile(r"建议关注回撤是否超出产品历史波动区间"),
        "建议您关注当前波动是否仍在产品历史常见范围内",
    ),
]


def contains_advisor_voice(text: str) -> bool:
    t = text or ""
    return any(m in t for m in _ADVISOR_MARKERS)


def to_client_voice(text: str) -> str:
    """将投研 recommendation 等经理向文案转为对客可直接转发的表述。"""
    out = (text or "").strip()
    if not out:
        return out

    for pattern, repl in _REPLACEMENTS:
        out = pattern.sub(repl, out)

    out = re.sub(r"\s{2,}", " ", out)
    out = re.sub(r"。{2,}", "。", out)
    out = re.sub(r"，{2,}", "，", out)
    out = out.strip("，； ")

    # 句首衔接：若仍以「，」开头则去掉
    if out.startswith("，"):
        out = out[1:].strip()

    if out and out[-1] not in "。！？":
        out += "。"

    return out
