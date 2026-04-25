"""
PurityCheck — PurityConfig 驱动的纯规则文本质量检查引擎
对应 WORKFLOW.md STEP 4 + docs/05_code_design.md §2.5
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ── 内置排比/套话正则（全局生效，不可被 novel 覆盖）────────────────────────
BUILTIN_BANNED_PATTERNS: list[tuple[str, str]] = [
    (r"[^。！？.!?]{5,}，[^。！？.!?]{5,}，[^。！？.!?]{5,}，", "三连排比句"),
    (r"(一方面|另一方面).{0,50}(一方面|另一方面)", "废话结构（一方面/另一方面）"),
    (r"此刻，?此时此刻", "时间套话（此刻/此时此刻）"),
    (r"不禁[想觉感]", "心理套话（不禁想/觉/感）"),
    (r"道不清.{0,10}说不明", "虚浮描写（道不清说不明）"),
    (r"忽然间.{0,5}忽然", "副词重复"),
    (r"[心情|心中|内心]{2,}", "心理直白叠用"),
]

# ── 心理描写匹配正则 ─────────────────────────────────────────────────────────
PSYCH_PATTERN = re.compile(
    r'（[^）]{2,}）'          # 括号内心理
    r'|心想[^，。]{0,30}'
    r'|感到[^，。]{0,30}'
    r'|觉得[^，。]{0,30}'
    r'|暗想[^，。]{0,30}'
    r'|脑海中[^，。]{0,30}'
    r'|内心[^，。]{0,20}'
    r'|心中[^，。]{0,20}'
)


@dataclass
class PurityConfig:
    """
    可配置的 Purity Check 规则集。
    每本小说可独立配置，可通过 WritingPreset 批量导入。
    """
    # 全局禁词文件列表（相对于 writing-styles/ 目录）
    banned_word_files: list[str] = field(
        default_factory=lambda: ["配件-禁词表-通用.md"]
    )
    # 额外禁词（小说级追加）
    extra_banned_words: list[str] = field(default_factory=list)
    # 额外排比正则（小说级追加，格式同 BUILTIN_BANNED_PATTERNS）
    extra_banned_patterns: list[tuple[str, str]] = field(default_factory=list)
    # 全局心理描写上限
    max_psych_ratio: float = 0.15
    # 场景类型覆盖（只需填写差异项）
    scene_overrides: dict[str, dict] = field(default_factory=lambda: {
        "combat":     {"max_psych_ratio": 0.10},
        "romance":    {"max_psych_ratio": 0.30},
        "introspect": {"max_psych_ratio": 0.40},
    })
    # 各检查项开关
    check_banned_words:    bool = True
    check_banned_patterns: bool = True
    check_psych_ratio:     bool = True
    check_chapter_hook:    bool = True
    check_ability_cap:     bool = True


# 默认配置单例
DEFAULT_PURITY_CONFIG = PurityConfig()


def _load_banned_words(files: list[str], styles_dir: Path) -> list[str]:
    """从 writing-styles/ 目录读取禁词（换行分隔，忽略 # 注释行）"""
    result = []
    for fname in files:
        path = styles_dir / fname
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and not line.startswith("-"):
                result.append(line)
    return result


def purity_check(
    text: str,
    config: PurityConfig,
    styles_dir: Path,
    scene_type: str = "normal",
    check_hook: bool = False,
    ability_cap: Optional[dict] = None,
) -> dict:
    """
    执行 STEP 4 Purity Check。

    Args:
        text:        生成的正文
        config:      PurityConfig 实例
        styles_dir:  writing-styles 目录路径
        scene_type:  场景类型标记（影响 psych 阈值）
        check_hook:  章节固化时传 True，额外检查章末钩子
        ability_cap: 主角能力上限 dict（含 tier 字段）

    Returns:
        {passed: bool, violations: list[str], stats: dict}
    """
    override = config.scene_overrides.get(scene_type, {})
    max_psych = override.get("max_psych_ratio", config.max_psych_ratio)

    violations: list[str] = []
    stats: dict = {"scene_type": scene_type}

    # 1. 禁词扫描
    if config.check_banned_words:
        banned = _load_banned_words(config.banned_word_files, styles_dir)
        banned.extend(config.extra_banned_words)
        for word in banned:
            if word in text:
                violations.append(f"禁词: 「{word}」")

    # 2. 套话排比检测（内置 + 自定义）
    if config.check_banned_patterns:
        all_patterns = BUILTIN_BANNED_PATTERNS + config.extra_banned_patterns
        for pattern, label in all_patterns:
            matches = re.findall(pattern, text)
            if matches:
                snippet = str(matches[0])[:30]
                violations.append(f"排比/套话（{label}）: 「{snippet}...」")

    # 3. 心理描写占比（场景自适应阈值）
    if config.check_psych_ratio:
        total_chars = max(1, len(text))
        psych_chars = sum(
            len(m.group())
            for m in PSYCH_PATTERN.finditer(text)
        )
        psych_ratio = psych_chars / total_chars
        stats["psych_ratio"] = round(psych_ratio, 3)
        stats["psych_limit"] = max_psych
        if psych_ratio > max_psych:
            violations.append(
                f"心理描写占比 {psych_ratio:.1%} 超过 {max_psych:.0%} 上限"
                f"（场景类型: {scene_type}）"
            )

    # 4. 章末钩子（仅固化时检查）
    if config.check_chapter_hook and check_hook:
        last_paras = [p for p in text.split("\n") if p.strip()][-2:]
        hook_keywords = ["？", "...", "…", "却", "然而", "突然", "但", "竟", "没想到"]
        has_hook = any(kw in p for p in last_paras for kw in hook_keywords)
        if not has_hook:
            violations.append("章末缺少悬念钩子（最后2段未检测到转折/疑问结构）")

    # 5. 能力边界验证
    if config.check_ability_cap and ability_cap:
        cap_tier = ability_cap.get("tier", 99)
        tier_tags = re.findall(r'<system_grant[^>]*tier="(\d+)"', text)
        for t in tier_tags:
            if int(t) > cap_tier:
                violations.append(
                    f"能力超出边界：正文包含 {t}★ 效果（主角当前上限 {cap_tier}★）"
                )

    return {
        "passed": len(violations) == 0,
        "violations": violations,
        "stats": stats,
    }
