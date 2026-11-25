"""
选股打分 —— 龙头四重标准 + 弱转强。

战法龙头四标准：
  ①带动性（带板块）②逻辑硬（题材）③身位压制（连板高度）④合力验证（封单）
弱化项：一字板买不到、开板次数多、孤庄票（无带动）。
"""
from __future__ import annotations

from collections import Counter
from typing import Dict, List, Tuple

from config import DEFAULT, SignalConfig
from data.models import Candidate


def detect_mainline(cands: List[Candidate]) -> Tuple[str, int]:
    """
    识别主线题材：统计各题材的带动总数 + 高度，取最强题材。
    返回 (主线题材, 该题材带动总数)。战法：远离杂毛、聚焦主线。
    """
    if not cands:
        return "", 0
    theme_drive: Dict[str, int] = Counter()
    theme_streak: Dict[str, int] = {}
    for c in cands:
        theme = c.board_reason or "其他"
        theme_drive[theme] += c.driven
        theme_streak[theme] = max(theme_streak.get(theme, 0), c.streak)
    # 主线 = 带动总数最高（同分比高度）
    theme = max(theme_drive, key=lambda t: (theme_drive[t], theme_streak.get(t, 0)))
    return theme, theme_drive[theme]


def score_candidate(c: Candidate, mainline: str, cfg: SignalConfig = None) -> Tuple[int, List[str]]:
    """
    对单只候选股打分 0-100，返回 (分数, 命中理由列表)。
    分数用于排序；是否触发买点由 signals.should_buy 决定。
    """
    cfg = cfg or DEFAULT.signal
    score = 0
    reasons: list[str] = []

    # ① 带动性（最高 25）
    if c.driven >= cfg.min_driven_stocks:
        score += 25
        reasons.append(f"带动 {c.driven} 只跟风（达标）")
    elif c.driven >= 3:
        score += 12
        reasons.append(f"带动 {c.driven} 只")
    else:
        reasons.append(f"带动弱（{c.driven} 只，疑孤庄）")

    # ② 逻辑硬 / 主线卡位（最高 25）
    if c.board_reason == mainline and mainline:
        score += 25
        reasons.append(f"主线题材：{mainline}")
    elif c.board_reason and c.board_reason != "无明确题材":
        score += 10
        reasons.append(f"支线题材：{c.board_reason}")
    else:
        reasons.append("无明确题材（杂毛）")

    # ③ 身位压制（连板高度，最高 20）
    if c.streak >= 4:
        score += 20
        reasons.append(f"高度 {c.streak} 板（身位）")
    elif c.streak >= 2:
        score += 12
        reasons.append(f"{c.streak} 板")
    else:
        score += 3
        reasons.append("首板")

    # ④ 合力验证（封单比，最高 15）
    if c.seal_ratio >= 0.06:
        score += 15
        reasons.append(f"封单比 {c.seal_ratio:.1%}（合力强）")
    elif c.seal_ratio >= 0.03:
        score += 8
        reasons.append(f"封单比 {c.seal_ratio:.1%}")
    else:
        reasons.append("封单偏弱")

    # ⑤ 弱转强加分（最高 15）
    if c.prev_broken and cfg.weak_to_strong_open_min <= c.auction_change <= cfg.weak_to_strong_open_max:
        score += 10
        reasons.append("前日烂板+竞价高开（弱转强）")
    if c.auction_vol_ratio >= cfg.auction_vol_ratio:
        score += 5
        reasons.append("竞价放量")

    # —— 减分项 ——
    if c.is_one_word:
        score -= 15
        reasons.append("一字板（难买入，扣分）")
    if c.broken_times >= 2:
        score -= 8
        reasons.append(f"开板 {c.broken_times} 次（分歧大）")

    score = max(0, min(100, score))
    return score, reasons


def pick_leaders(cands: List[Candidate], cfg: SignalConfig = None) -> List[Tuple[Candidate, int, List[str]]]:
    """
    综合选股：先识别主线，再对全部候选打分，按分数降序返回。
    返回 [(候选, 分数, 理由), ...]
    """
    mainline, _ = detect_mainline(cands)
    scored = [(c, *score_candidate(c, mainline, cfg)) for c in cands]
    scored.sort(key=lambda x: -x[1])
    return scored
