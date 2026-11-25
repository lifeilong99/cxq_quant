#!/usr/bin/env python3
"""
陈小群战法量化工具 —— 选股 + 买卖信号 + 模拟盘（命令行）

用法示例：
  python main.py status --scene ferment            # 查看情绪周期判定
  python main.py scan   --scene ferment            # 选股打分排行
  python main.py signals --scene ferment           # 生成买卖信号（不执行）
  python main.py run    --scene ferment            # 生成信号并在模拟盘执行
  python main.py run    --scene ebb --date 20251121
  python main.py account                           # 查看模拟账户
  python main.py history                           # 查看历史成交/平仓
  python main.py reset                             # 重置模拟账户

数据源：
  --source demo      内置示例数据（离线可跑，默认）
  --source akshare   东方财富真实数据（需联网；东财接口限制时可能失败）

⚠️ 本工具仅模拟盘运行，不连接任何真实资金账户，不构成投资建议。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

# 保证从任意目录运行都能导入本地模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import DEFAULT
from data.feed import get_feed
from data.models import Signal
from strategy.emotion import judge_emotion, position_for_emotion, EMOTION_LABEL
from strategy.picker import detect_mainline, pick_leaders
from strategy.signals import generate_signals
from broker.simulator import Simulator

HOLD_FILE = "hold_days.json"


# ---------------- 工具函数 ----------------

def _feed(args):
    kwargs = {}
    if args.source == "demo":
        kwargs["scene"] = args.scene
        kwargs["seed"] = args.seed
    return get_feed(args.source, **kwargs)


def _load_hold_days() -> dict:
    if os.path.exists(HOLD_FILE):
        try:
            with open(HOLD_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _update_hold_days(hold: dict, signals: list, sim: Simulator, date: str):
    """持仓天数递增；新买入置 0；卖出清除"""
    for code in list(hold.keys()):
        if code in sim.account.positions:
            hold[code] = hold.get(code, 0) + 1
        else:
            hold.pop(code, None)
    for sig in signals:
        if sig.action == "BUY" and sig.code in sim.account.positions:
            hold[sig.code] = 0
        elif sig.action == "SELL":
            hold.pop(sig.code, None)
    with open(HOLD_FILE, "w", encoding="utf-8") as f:
        json.dump(hold, f, ensure_ascii=False, indent=2)


def _prices(feed, cands, date: str) -> dict:
    return {c.code: (c.price or feed.price_of(c.code, date)) for c in cands}


# ---------------- 命令 ----------------

def cmd_status(args):
    feed = _feed(args)
    b = feed.market_breadth(args.date)
    stage, score, note = judge_emotion(b)
    pos = position_for_emotion(stage)
    print("=" * 56)
    print(f"  市场情绪宽度 · {b.date}  [source={args.source}]")
    print("=" * 56)
    print(f"  涨停家数      : {b.limit_up}")
    print(f"  跌停家数      : {b.limit_down}")
    print(f"  炸板家数      : {b.broken}  (炸板率 {b.break_rate:.1%})")
    print(f"  最高连板      : {b.max_streak} 板")
    print(f"  连板家数      : {b.streak_count}  (晋级率 {b.promotion:.1%})")
    print(f"  情绪热度评分  : {score}/100")
    print("-" * 56)
    print(f"  判定阶段      : {EMOTION_LABEL[stage]}")
    print(f"  判定依据      : {note}")
    print(f"  建议目标仓位  : {pos:.0%}")
    print("=" * 56)


def cmd_scan(args):
    feed = _feed(args)
    b = feed.market_breadth(args.date)
    cands = feed.candidates(args.date)
    stage, score, _ = judge_emotion(b)
    mainline, drive = detect_mainline(cands)
    ranked = pick_leaders(cands)

    print("=" * 78)
    print(f"  选股打分排行 · {b.date} · 情绪 {EMOTION_LABEL[stage]} · 主线【{mainline}】")
    print("=" * 78)
    print(f"{'排名':<4}{'代码':<9}{'名称':<10}{'题材':<10}{'连板':<5}{'带动':<5}{'评分':<5}{'亮点'}")
    print("-" * 78)
    for i, (c, sc, reasons) in enumerate(ranked, 1):
        print(f"{i:<4}{c.code:<9}{c.name:<10}{c.board_reason:<10}{c.streak:<5}{c.driven:<5}{sc:<5}{reasons[0] if reasons else ''}")
    print("=" * 78)


def cmd_signals(args):
    feed = _feed(args)
    b = feed.market_breadth(args.date)
    cands = feed.candidates(args.date)
    sim = Simulator()
    prices = _prices(feed, cands, args.date)
    hold = _load_hold_days()
    sigs = generate_signals(b, cands, sim.account.positions, prices, hold)
    _print_signals(sigs, b.date)


def _print_signals(sigs: list, date: str):
    print("=" * 78)
    print(f"  买卖信号 · {date}  （仅策略参考，模拟盘执行）")
    print("=" * 78)
    if not sigs:
        print("  无信号")
        print("=" * 78)
        return
    icon = {"BUY": "🔴 买入", "SELL": "🟢 卖出", "WATCH": "👀 观察"}
    for s in sigs:
        tag = icon.get(s.action, s.action)
        size = f"｜建议仓位 {s.size:.0%}" if s.action == "BUY" else ""
        print(f"  {tag}  {s.code} {s.name}  @{s.price:.2f}{size}")
        print(f"        强度 {s.strength}｜{s.reason}")
    print("=" * 78)


def cmd_run(args):
    feed = _feed(args)
    b = feed.market_breadth(args.date)
    cands = feed.candidates(args.date)
    stage, score, note = judge_emotion(b)

    sim = Simulator()
    prices = _prices(feed, cands, args.date)
    sim.update_peaks(prices)
    hold = _load_hold_days()

    sigs = generate_signals(b, cands, sim.account.positions, prices, hold)
    print("=" * 78)
    print(f"  模拟盘运行 · {b.date} · 情绪 {EMOTION_LABEL[stage]}（{note}）")
    print("=" * 78)
    _print_signals(sigs, b.date)

    # 卖出优先，再买入
    executed = []
    for s in sorted(sigs, key=lambda x: 0 if x.action == "SELL" else 1):
        if s.action in ("BUY", "SELL"):
            # 仓位已在 generate_signals 中按情绪目标仓位与槽位分配
            executed.append(sim.execute(s, prices.get(s.code, s.price), args.date))

    _update_hold_days(hold, sigs, sim, args.date)
    sim.save()

    print("\n  执行结果：")
    for line in executed:
        print(f"    - {line}")

    val = sim.valuation(prices)
    weights = sim.position_weights(prices)
    print("\n" + "-" * 78)
    print(f"  账户估值：总资产 {val.total:,.2f} 元｜现金 {val.cash:,.2f} 元｜"
          f"持仓市值 {val.market_value:,.2f} 元｜累计收益 {val.returns_pct:+.2%}")
    print(f"  当前持仓：{len(sim.account.positions)} 只｜"
          + ("、".join(f"{p.name}({w:.0%})" for c, p in sim.account.positions.items()
                      for w in [weights.get(c, 0)]) or "空仓"))
    print("=" * 78)
    print("  ⚠️ 模拟盘，不涉及真实资金；信号仅供参考，不构成投资建议。")


def cmd_account(args):
    sim = Simulator()
    feed = _feed(args)
    cands = feed.candidates(args.date)
    prices = _prices(feed, cands, args.date)
    # 用账户中记录的成本兜底估值
    for code, pos in sim.account.positions.items():
        if code not in prices:
            prices[code] = pos.cost
    val = sim.valuation(prices)

    print("=" * 66)
    print("  模拟账户")
    print("=" * 66)
    print(f"  初始资金  : {sim.account.init_cash:,.2f} 元")
    print(f"  现金      : {sim.account.cash:,.2f} 元")
    print(f"  持仓市值  : {val.market_value:,.2f} 元")
    print(f"  总资产    : {val.total:,.2f} 元")
    print(f"  累计收益  : {val.returns_pct:+.2%}")
    print(f"  已平仓交易: {len(sim.account.trades)} 笔")
    print("-" * 66)
    if sim.account.positions:
        print(f"{'代码':<9}{'名称':<10}{'股数':<7}{'成本':<9}{'现价':<9}{'盈亏':<9}")
        for code, p in sim.account.positions.items():
            px = prices.get(code, p.cost)
            print(f"{code:<9}{p.name:<10}{p.shares:<7}{p.cost:<9.2f}{px:<9.2f}{p.pnl(px):<9.1%}")
    else:
        print("  当前空仓")
    print("=" * 66)


def cmd_history(args):
    sim = Simulator()
    print("=" * 78)
    print(f"  历史成交 / 平仓记录（共 {len(sim.account.orders)} 笔委托，{len(sim.account.trades)} 笔平仓）")
    print("=" * 78)
    if sim.account.trades:
        wins = sum(1 for t in sim.account.trades if t.pnl > 0)
        total_pnl = sum(t.pnl for t in sim.account.trades)
        print(f"  胜率 {wins}/{len(sim.account.trades)} = {wins/len(sim.account.trades):.0%}｜"
              f"累计盈亏 {total_pnl:+,.0f} 元")
        print("-" * 78)
        for t in sim.account.trades:
            print(f"  {t.code} {t.name}｜{t.open_date}→{t.close_date}｜"
                  f"{t.pnl:+,.0f}元({t.pnl_pct:+.1%})｜{t.reason[:28]}")
    else:
        print("  暂无平仓记录")
    print("=" * 78)


def cmd_reset(args):
    sim = Simulator()
    sim.reset()
    if os.path.exists(HOLD_FILE):
        os.remove(HOLD_FILE)
    print(f"✅ 模拟账户已重置：资金 {sim.account.init_cash:,.2f} 元，持仓与记录清空。")


def build_parser() -> argparse.ArgumentParser:
    desc = "陈小群战法量化工具：选股 + 买卖信号 + 模拟盘（不构成投资建议）"

    # 公共参数同时挂到主解析器与每个子命令，兼容
    # `python main.py --scene ferment status` 与 `python main.py status --scene ferment` 两种写法。
    def add_common(target):
        target.add_argument("--source", choices=["demo", "akshare"], default="demo",
                            help="数据源：demo=内置示例(默认)，akshare=东财真实数据")
        target.add_argument("--scene", choices=["freeze", "ferment", "climax", "ebb", "auto"],
                            default="ferment", help="demo 场景：情绪周期（默认 ferment）")
        target.add_argument("--date", default="20251121", help="交易日 YYYYMMDD")
        target.add_argument("--seed", type=int, default=20261125, help="示例数据随机种子")
        target.add_argument("--account", default=DEFAULT.account_file, help="模拟账户文件路径")

    p = argparse.ArgumentParser(description=desc,
                                formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    add_common(p)

    sub = p.add_subparsers(dest="cmd")
    for name, help_text in [
        ("status", "查看情绪周期判定"), ("scan", "选股打分排行"),
        ("signals", "生成买卖信号（不执行）"), ("run", "生成信号并在模拟盘执行"),
        ("account", "查看模拟账户"), ("history", "查看成交/平仓记录"),
        ("reset", "重置模拟账户"),
    ]:
        sp = sub.add_parser(name, help=help_text,
                            formatter_class=argparse.RawDescriptionHelpFormatter)
        add_common(sp)
    return p


def main():
    args = build_parser().parse_args()
    DEFAULT.account_file = args.account
    global HOLD_FILE
    HOLD_FILE = os.path.join(os.path.dirname(os.path.abspath(args.account)) or ".", "hold_days.json")

    dispatch = {
        "status": cmd_status, "scan": cmd_scan, "signals": cmd_signals,
        "run": cmd_run, "account": cmd_account, "history": cmd_history,
        "reset": cmd_reset,
    }
    if not args.cmd:
        build_parser().print_help()
        return
    try:
        dispatch[args.cmd](args)
    except Exception as e:
        print(f"❌ 执行失败：{type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
