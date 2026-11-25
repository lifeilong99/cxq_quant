"""
情绪周期判定 —— 战法的总引擎。

战法核心：冰点 → 发酵主升 → 高潮分歧 → 退潮，情绪定仓位。
判定采用「打分 + 否决项」的确定性规则（非黑箱）：
  - 先看否决项（退潮特征：跌停潮/高标断板/晋级率崩塌）
  - 再按 scored 分档定位阶段
"""
from __future__ import annotations

from typing import Tuple

from config import DEFAULT, EmotionConfig, PositionConfig
from data.models import MarketBreadth


def _score_heat(b: MarketBreadth, c: EmotionConfig) -> int:
    """情绪热度打分 0-100"""
    score = 0
    # 涨停家数
    if b.limit_up >= c.limit_up_hot:
        score += 25
    elif b.limit_up >= c.limit_up_freeze:
        score += 15
    else:
        score += 3
    # 连板高度
    if b.max_streak >= c.max_streak_high:
        score += 20
    elif b.max_streak > c.max_streak_low:
        score += 12
    else:
        score += 2
    # 炸板率（低为好）
    if b.break_rate < 0.20:
        score += 20
    elif b.break_rate < c.break_rate_high:
        score += 10
    else:
        score += 0
    # 晋级率
    if b.promotion >= 0.30:
        score += 20
    elif b.promotion >= c.promotion_low:
        score += 12
    else:
        score += 3
    # 跌停（少为好）
    if b.limit_down <= 5:
        score += 15
    elif b.limit_down <= c.limit_down_high:
        score += 7
    else:
        score += 0
    return score


def judge_emotion(b: MarketBreadth, cfg: EmotionConfig = None) -> Tuple[str, int, str]:
    """
    返回 (阶段, 热度分, 判定说明)
    阶段 ∈ freeze / ferment / climax / ebb
    """
    cfg = cfg or DEFAULT.emotion
    score = _score_heat(b, cfg)
    notes: list[str] = []

    # —— 退潮否决项 ——（战法：高标断板 A 杀、跌停潮、炸板潮 → 强制空仓）
    # 关键：退潮 = 从高热骤降；冰点 = 已在低位钝化。二者都「跌停多、炸板高」，
    # 必须用「昨日基数」区分，否则冰点会被误判成退潮。
    was_hot = b.prev_limit_up >= cfg.limit_up_hot
    ebb_votes = 0
    if was_hot and b.limit_up < b.prev_limit_up * 0.5 and b.max_streak <= cfg.max_streak_low + 1:
        ebb_votes += 2   # 高位骤降+高度断层，退潮的强特征
        notes.append(f"高位骤降：昨停 {b.prev_limit_up}→今停 {b.limit_up}，高度 {b.max_streak}")
    if was_hot and b.limit_down >= cfg.limit_down_high:
        ebb_votes += 1
        notes.append(f"退潮跌停潮 {b.limit_down} 家")
    if was_hot and b.promotion < cfg.promotion_low:
        ebb_votes += 1
        notes.append(f"接力意愿崩塌：晋级率 {b.promotion:.0%}")

    if ebb_votes >= 2:
        return "ebb", score, "退潮特征（" + "；".join(notes) + "）"

    # —— 正常分档 ——
    if score >= 78 and b.max_streak >= cfg.max_streak_high:
        return "climax", score, "高潮一致：涨停与高度双高，注意兑现"
    if score >= 55:
        return "ferment", score, "发酵主升：主线扩散、梯队完整，重仓总龙"
    if score < 30:
        return "freeze", score, "冰点：亏钱效应弥漫，仅小仓试错"

    # 30~55 之间：偏冰点，若高度低则冰点，否则弱发酵
    if b.max_streak <= cfg.max_streak_low:
        return "freeze", score, "冰点/启动：无高度，轻仓试错"
    return "ferment", score, "弱发酵：情绪修复中，控仓参与"


def position_for_emotion(stage: str, cfg: PositionConfig = None) -> float:
    """情绪阶段 → 目标总仓位（战法：情绪定仓位）"""
    cfg = cfg or DEFAULT.position
    return {
        "freeze": cfg.freeze_pos,
        "ferment": cfg.ferment_pos,
        "climax": cfg.climax_pos,
        "ebb": cfg.ebb_pos,
    }.get(stage, 0.0)


# 兼容别名
cycle_target_pos = position_for_emotion


EMOTION_LABEL = {
    "freeze": "🥶 冰点/启动",
    "ferment": "🔥 发酵主升",
    "climax": "🌡️ 高潮分歧",
    "ebb": "🌊 退潮",
}
