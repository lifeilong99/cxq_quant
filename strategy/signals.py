"""
买卖信号生成 —— 把战法的买点/卖点规则化。

买入：仅在非退潮 + 弱转强/主线龙头达标 + 仓位允许时给出 BUY。
卖出：止损 / 断板 / 退潮清仓 / 两日未达预期 / 一致止盈。
注意：所有信号仅为策略参考，不构成投资建议，默认模拟盘执行。
"""
from __future__ import annotations

from typing import Dict, List, Optional

from config import DEFAULT, SignalConfig
from data.models import Candidate, MarketBreadth, Position, Signal
from .emotion import judge_emotion, position_for_emotion
from .picker import detect_mainline, score_candidate


def should_buy(c: Candidate, stage: str, score: int, mainline: str,
               cfg: SignalConfig = None) -> Optional[Signal]:
    """判定单只个股是否触发买入信号"""
    cfg = cfg or DEFAULT.signal

    # 退潮期禁止开仓（战法铁律）
    if stage == "ebb":
        return None

    # 高潮期仓位收紧：只认最高分主线总龙
    need = 78 if stage == "climax" else (60 if stage == "ferment" else 70)
    if score < need:
        return None

    # 主线卡位要求
    if not mainline or c.board_reason != mainline:
        return None

    # 一字板买不到
    if c.is_one_word:
        return None

    reasons: list[str] = []
    strong = False
    # 弱转强买点
    if c.prev_broken and cfg.weak_to_strong_open_min <= c.auction_change <= cfg.weak_to_strong_open_max \
            and c.auction_vol_ratio >= cfg.auction_vol_ratio:
        strong = True
        reasons.append("弱转强：前日烂板→竞价高开放量")
    # 发酵期主线总龙打板/接力
    if stage == "ferment" and c.streak >= 2 and c.driven >= cfg.min_driven_stocks:
        strong = True
        reasons.append("发酵期主线总龙/中位接力")

    if not strong:
        return None

    return Signal(
        code=c.code, name=c.name, action="BUY",
        reason="；".join(reasons) + f"｜评分{score}",
        strength=score, price=c.price,
        size=DEFAULT.position.max_single_stock,
    )


def should_sell(pos: Position, price: float, stage: str, hold_days: int,
                cfg: SignalConfig = None) -> Optional[Signal]:
    """判定持仓是否触发卖出信号"""
    cfg = cfg or DEFAULT.signal
    pnl = pos.pnl(price)

    # ① 止损（最高优先级，战法铁律）
    if pnl <= -cfg.stop_loss:
        return Signal(pos.code, pos.name, "SELL",
                      f"止损：亏损 {pnl:.1%} ≤ -{cfg.stop_loss:.0%}", 100, price)

    # ② 退潮清仓
    if stage == "ebb":
        return Signal(pos.code, pos.name, "SELL",
                      f"退潮清仓：当前盈亏 {pnl:+.1%}", 95, price)

    # ③ 两日未达预期平仓
    if hold_days >= cfg.max_hold_days and pnl < 0.02:
        return Signal(pos.code, pos.name, "SELL",
                      f"持有 {hold_days} 日未达预期（{pnl:+.1%}）", 70, price)

    # ④ 一致止盈（高潮阶段 + 有盈利）
    if stage == "climax" and pnl >= 0.05:
        return Signal(pos.code, pos.name, "SELL",
                      f"高潮一致：分批兑现（{pnl:+.1%}）", 80, price)

    # ⑤ 移动止盈：从峰值回撤超过止损线且仍有盈利
    if pos.peak_price > 0 and price < pos.peak_price * (1 - cfg.stop_loss) and pnl > 0:
        return Signal(pos.code, pos.name, "SELL",
                      f"移动止盈：峰值回撤破 {cfg.stop_loss:.0%}（{pnl:+.1%}）", 75, price)

    return None


def generate_signals(breadth: MarketBreadth, cands: List[Candidate],
                     positions: Dict[str, Position], prices: Dict[str, float],
                     hold_days: Dict[str, int], cfg: SignalConfig = None) -> List[Signal]:
    """
    生成全部买卖信号（主入口）。
    - 先处理持仓卖出（风控优先）
    - 再处理开仓买入（受情绪仓位约束）
    """
    cfg = cfg or DEFAULT.signal
    stage, _, _ = judge_emotion(breadth)
    mainline, _ = detect_mainline(cands)
    out: List[Signal] = []

    # —— 卖出：持仓风控 ——
    for code, pos in positions.items():
        px = prices.get(code, 0.0) or pos.cost
        sig = should_sell(pos, px, stage, hold_days.get(code, 0), cfg)
        if sig:
            out.append(sig)

    # —— 买入：开仓选股 ——
    sell_codes = {s.code for s in out if s.action == "SELL"}
    available_slots = DEFAULT.position.max_holdings - (len(positions) - len(sell_codes))
    if available_slots > 0 and stage != "ebb":
        # 目标总仓位按情绪阶段确定，均分给可开仓位，且不超过单票上限
        target_pos = position_for_emotion(stage)
        per_stock = min(target_pos / max(available_slots, 1), DEFAULT.position.max_single_stock)
        scored = [(c, *score_candidate(c, mainline, cfg)) for c in cands]
        scored.sort(key=lambda x: -x[1])
        added = 0
        for c, score, _ in scored:
            if c.code in positions or c.code in sell_codes:
                continue
            sig = should_buy(c, stage, score, mainline, cfg)
            if sig:
                sig.size = round(per_stock, 4)
                out.append(sig)
                added += 1
                if added >= available_slots:
                    break

    # WATCH：打分最高但未触发买点的主线标的，供观察
    if len([s for s in out if s.action == "BUY"]) == 0:
        scored = [(c, *score_candidate(c, mainline, cfg)) for c in cands]
        scored.sort(key=lambda x: -x[1])
        for c, score, _ in scored[:2]:
            if c.code in positions:
                continue
            out.append(Signal(c.code, c.name, "WATCH",
                              f"候选观察｜评分{score}｜主线{mainline}", score, c.price))
            break

    return out
