"""
模拟盘撮合引擎。

重要：本模块完全不涉及真实资金账户与券商下单接口，
仅按信号在虚拟账户中模拟成交、记账与估值，用于验证策略逻辑。
"""
from __future__ import annotations

import json
import math
import os
from dataclasses import asdict
from typing import Dict, List

from config import DEFAULT, BacktestConfig, PositionConfig
from data.models import Account, Order, Position, Signal, Trade
from strategy.emotion import position_for_emotion


class Valuation:
    """账户估值结果"""

    def __init__(self, cash: float, market_value: float, market_returns: float):
        self.cash = cash
        self.market_value = market_value
        self.total = cash + market_value
        self.returns = market_returns
        self.returns_pct = (self.total / market_returns - 1) if market_returns else 0.0


class Simulator:
    """模拟盘：按信号执行虚拟买卖，持久化账户到 JSON 文件。"""

    def __init__(self, account_file: str = None, bt: BacktestConfig = None,
                 pos_cfg: PositionConfig = None):
        self.file = account_file or DEFAULT.account_file
        self.bt = bt or DEFAULT.backtest
        self.pos_cfg = pos_cfg or DEFAULT.position
        self.account = self._load()

    # ---------- 持久化 ----------
    def _load(self) -> Account:
        if os.path.exists(self.file):
            try:
                with open(self.file, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                acc = Account(
                    cash=float(raw.get("cash", self.bt.init_cash)),
                    init_cash=float(raw.get("init_cash", self.bt.init_cash)),
                    updated_at=raw.get("updated_at", ""),
                )
                for k, v in raw.get("positions", {}).items():
                    acc.positions[k] = Position(**v)
                acc.orders = [Order(**o) for o in raw.get("orders", [])]
                acc.trades = [Trade(**t) for t in raw.get("trades", [])]
                return acc
            except Exception as e:
                raise RuntimeError(f"账户文件解析失败：{self.file}（{e}）。请检查或删除后重试。") from e
        return Account(cash=self.bt.init_cash, init_cash=self.bt.init_cash)

    def save(self):
        os.makedirs(os.path.dirname(os.path.abspath(self.file)) or ".", exist_ok=True)
        raw = {
            "cash": self.account.cash,
            "init_cash": self.account.init_cash,
            "updated_at": self.account.updated_at,
            "positions": {k: asdict(v) for k, v in self.account.positions.items()},
            "orders": [asdict(o) for o in self.account.orders],
            "trades": [asdict(t) for t in self.account.trades],
        }
        with open(self.file, "w", encoding="utf-8") as f:
            json.dump(raw, f, ensure_ascii=False, indent=2)

    def reset(self):
        self.account = Account(cash=self.bt.init_cash, init_cash=self.bt.init_cash)
        if os.path.exists(self.file):
            os.remove(self.file)

    # ---------- 交易 ----------
    @staticmethod
    def _lot(shares: int) -> int:
        return int(math.floor(shares / 100) * 100)

    def _fee(self, amount: float, side: str) -> float:
        commission = max(amount * self.bt.commission, self.bt.min_commission)
        duty = amount * self.bt.stamp_duty if side == "SELL" else 0.0
        return round(commission + duty, 2)

    def execute(self, sig: Signal, price: float, date: str) -> str:
        """执行单条信号，返回执行结果描述"""
        if price <= 0:
            return f"跳过 {sig.code}：价格无效"

        if sig.action == "BUY":
            return self._buy(sig, price, date)
        if sig.action == "SELL":
            return self._sell(sig, price, date)
        return f"忽略 {sig.code}：{sig.action}"

    def _buy(self, sig: Signal, price: float, date: str) -> str:
        if sig.code in self.account.positions:
            return f"跳过买入 {sig.name}：已持有"
        if len(self.account.positions) >= self.pos_cfg.max_holdings:
            return f"跳过买入 {sig.name}：持仓已满（{self.pos_cfg.max_holdings}）"

        # 单票仓位上限
        alloc = min(sig.size or self.pos_cfg.max_single_stock, self.pos_cfg.max_single_stock)
        budget = self.account.cash * alloc
        shares = self._lot(budget / price)
        if shares < 100:
            return f"跳过买入 {sig.name}：资金不足一手"

        amount = round(shares * price, 2)
        fee = self._fee(amount, "BUY")
        total = amount + fee
        if total > self.account.cash:
            shares -= 100
            if shares < 100:
                return f"跳过买入 {sig.name}：费用后资金不足"
            amount = round(shares * price, 2)
            fee = self._fee(amount, "BUY")
            total = amount + fee

        self.account.cash = round(self.account.cash - total, 2)
        cost = round(total / shares, 4)
        self.account.positions[sig.code] = Position(
            code=sig.code, name=sig.name, shares=shares, cost=cost,
            open_date=date, peak_price=price,
        )
        self.account.orders.append(Order(
            code=sig.code, name=sig.name, side="BUY", price=price, shares=shares,
            amount=amount, fee=fee, reason=sig.reason, date=date,
        ))
        return f"买入 {sig.name} {shares}股 @{price:.2f}（{sig.reason[:20]}）"

    def _sell(self, sig: Signal, price: float, date: str) -> str:
        pos = self.account.positions.get(sig.code)
        if not pos:
            return f"跳过卖出 {sig.code}：无持仓"

        shares = pos.shares
        amount = round(shares * price, 2)
        fee = self._fee(amount, "SELL")
        net = amount - fee
        self.account.cash = round(self.account.cash + net, 2)

        pnl = round((price - pos.cost) * shares - fee, 2)
        pnl_pct = pos.pnl(price)
        self.account.trades.append(Trade(
            code=pos.code, name=pos.name, open_date=pos.open_date, close_date=date,
            open_price=pos.cost, close_price=price, shares=shares,
            pnl=pnl, pnl_pct=round(pnl_pct, 4), reason=sig.reason,
        ))
        self.account.orders.append(Order(
            code=pos.code, name=pos.name, side="SELL", price=price, shares=shares,
            amount=amount, fee=fee, reason=sig.reason, date=date,
        ))
        del self.account.positions[sig.code]
        return f"卖出 {pos.name} {shares}股 @{price:.2f}，盈亏 {pnl:+.0f}元（{sig.reason[:20]}）"

    def update_peaks(self, prices: Dict[str, float]):
        """更新持仓峰值价（移动止盈用）"""
        for code, pos in self.account.positions.items():
            px = prices.get(code, 0.0)
            if px > pos.peak_price:
                pos.peak_price = px

    # ---------- 估值 ----------
    def valuation(self, prices: Dict[str, float]) -> Valuation:
        mv = 0.0
        for code, pos in self.account.positions.items():
            mv += pos.shares * prices.get(code, pos.cost)
        return Valuation(self.account.cash, round(mv, 2), self.account.init_cash)

    def position_weights(self, prices: Dict[str, float]) -> Dict[str, float]:
        """各持仓占总资产比例"""
        val = self.valuation(prices)
        if val.total <= 0:
            return {}
        return {
            code: round(pos.shares * prices.get(code, pos.cost) / val.total, 4)
            for code, pos in self.account.positions.items()
        }
