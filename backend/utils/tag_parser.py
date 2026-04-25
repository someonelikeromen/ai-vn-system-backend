"""
<system_grant> / <narrative_seed> 结构化标签提取器
对应 WORKFLOW.md Phase 2 的正则解析管线。
"""
from __future__ import annotations

import re
from typing import Optional


# ── system_grant 正则 ────────────────────────────────────────────────────────
# 匹配如：<system_grant type="xp" school="云体风身" amount="20" context="vs_stronger"/>
_GRANT_PATTERN = re.compile(
    r'<system_grant\s+([^/\>]+?)/?>', re.DOTALL
)

# ── narrative_seed 正则 ─────────────────────────────────────────────────────
# 匹配如：<narrative_seed id="hook_xxx" text="李四的眼神"/>
_SEED_PATTERN = re.compile(
    r'<narrative_seed\s+([^/\>]+?)/?>', re.DOTALL
)

# ── 属性解析辅助 ────────────────────────────────────────────────────────────
_ATTR_PATTERN = re.compile(r'(\w+)=["\']([^"\']*)["\']')


def _parse_attrs(raw: str) -> dict[str, str]:
    """解析 XML 属性字符串 → dict"""
    return {k: v for k, v in _ATTR_PATTERN.findall(raw)}


def _try_num(val: str):
    """尝试将字符串转换为数字"""
    try:
        if "." in val:
            return float(val)
        return int(val)
    except (ValueError, TypeError):
        return val


# ════════════════════════════════════════════════════════════════════════════
# 主提取函数
# ════════════════════════════════════════════════════════════════════════════

def extract_system_grants(text: str) -> list[dict]:
    """
    从正文中提取所有 <system_grant> 标签，返回结构化列表。

    支持的 type 及附属字段：
      xp    — school, amount, context
      kill  — tier, tier_sub, kill_type
      stat  — attr, delta
      energy— pool, delta
      points— amount
      item  — item_key, quantity
      hp_damage — amount
      status_effect — name, duration, effect, action
    """
    grants = []
    for match in _GRANT_PATTERN.finditer(text):
        attrs = _parse_attrs(match.group(1))
        tag = {"_raw": match.group(0)}

        t = attrs.get("type", "")
        tag["type"] = t

        if t == "xp":
            tag["school"] = attrs.get("school", "")
            tag["amount"] = _try_num(attrs.get("amount", 0))
            tag["context"] = attrs.get("context", "vs_equal")

        elif t == "kill":
            tag["tier"] = _try_num(attrs.get("tier", 0))
            tag["tier_sub"] = attrs.get("tier_sub", "M")
            tag["kill_type"] = attrs.get("kill_type", "defeat")
            tag["enemy_category"] = attrs.get("category", f"tier{tag['tier']}")

        elif t == "stat":
            tag["attr"] = attrs.get("attr", "")
            tag["delta"] = _try_num(attrs.get("delta", 0))

        elif t == "energy":
            tag["pool"] = attrs.get("pool", "")
            tag["delta"] = _try_num(attrs.get("delta", 0))

        elif t == "points":
            tag["amount"] = _try_num(attrs.get("amount", 0))

        elif t == "item":
            tag["item_key"] = attrs.get("item_key", "")
            tag["quantity"] = _try_num(attrs.get("quantity", 1))

        elif t == "hp_damage":
            tag["amount"] = _try_num(attrs.get("amount", 0))

        elif t == "status_effect":
            tag["name"] = attrs.get("name", "未知状态")
            tag["duration"] = attrs.get("duration", "")
            tag["effect"] = attrs.get("effect", "")
            tag["action"] = attrs.get("action", "add")  # "add" | "remove"

        else:
            # 未知类型，保存原始属性
            tag.update({k: _try_num(v) for k, v in attrs.items()})

        grants.append(tag)

    return grants


def extract_narrative_seeds(text: str) -> list[dict]:
    """
    从正文提取所有 <narrative_seed> 标签。
    返回格式：[{id, text, urgency?, category?}]
    """
    seeds = []
    for match in _SEED_PATTERN.finditer(text):
        attrs = _parse_attrs(match.group(1))
        seeds.append({
            "id":       attrs.get("id", ""),
            "text":     attrs.get("text", ""),
            "urgency":  attrs.get("urgency", "low"),
            "category": attrs.get("category", "general"),
            "_raw":     match.group(0),
        })
    return seeds


def strip_grants_from_text(text: str) -> str:
    """从正文中移除所有结构化标签（返回纯净正文用于展示）"""
    text = _GRANT_PATTERN.sub("", text)
    text = _SEED_PATTERN.sub("", text)
    # 清理可能残留的多余换行
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def classify_grants(grants: list[dict]) -> dict[str, list[dict]]:
    """按类型分组，供 STEP 5 分队列结算"""
    result: dict[str, list[dict]] = {
        "xp": [], "kill": [], "stat": [], "energy": [],
        "points": [], "item": [], "hp_damage": [], "status_effect": [], "other": [],
    }
    for g in grants:
        t = g.get("type", "other")
        result.setdefault(t, []).append(g)
    return result


def parse_scene_tags(text: str) -> dict:
    """
    提取正文头部的场景注释标记：
      <!-- scene: combat --> <!-- style: 零度写作+节奏大师 -->
    """
    scene_match = re.search(r'<!--\s*scene:\s*(\S+)\s*-->', text)
    style_match  = re.search(r'<!--\s*style:\s*(.+?)\s*-->', text)
    return {
        "scene_type": scene_match.group(1) if scene_match else "normal",
        "style_atoms": style_match.group(1).split("+") if style_match else [],
    }
