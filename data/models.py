"""
核心数据模型（dataclass）。
所有价格为 float，涨跌幅为小数（0.05 = 5%）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class MarketBreadth:
    """市场情绪宽度快照 —— 情绪周期判定的输入"""

    date: str                       # 交易日 YYYYMMDD
    limit_up: int = 0               # 涨停家数（非一字/非ST，口径见数据源）
    limit_down: int = 0             # 跌停家数
    broken: int = 0                 # 炸板家数
    max_streak: int = 0             # 市场最高连板高度
    streak_count: int = 0           # 连板（>=2）家数
    prev_limit_up: int = 0          # 昨日涨停家数
    turnover: float = 0.0           # 两市成交额（亿元），0 表示未知

    @property
    def break_rate(self) -> float:
        """炸板率"""
        denom = self.limit_up + self.broken
        return self.broken / denom if denom else 0.0

    @property
    def promotion(self) -> float:
        """晋级率：今日连板数 / 昨日涨停数"""
        return self.streak_count / self.prev_limit_up if self.prev_limit_up else 0.0


@dataclass
class Candidate:
    """候选个股快照 —— 选股打分的输入"""

    code: str
    name: str
    price: float = 0.0
    change_pct: float = 0.0         # 当日涨跌幅
    streak: int = 0                 # 当前连板数
    driven: int = 0                 # 带动跟风涨停数（龙头带动性）
    board_reason: str = ""          # 涨停/异动原因（题材）
    is_one_word: bool = False       # 是否一字板
    broken_times: int = 0           # 开板次数
    seal_ratio: float = 0.0         # 封单额/流通市值 比（合力验证）
    auction_change: float = 0.0     # 集合竞价涨幅
    auction_vol_ratio: float = 0.0  # 竞价量/前日成交 比
    prev_broken: bool = False       # 前一日是否烂板/炸板（弱转强前提）
    turnover: float = 0.0           # 换手率
    float_mv: float = 0.0           # 流通市值（亿元）


@dataclass
class Signal:
    """买卖信号"""

    code: str
    name: str
    action: str                     # BUY / SELL / WATCH
    reason: str                     # 触发原因
    strength: int = 0               # 信号强度 0-100
    price: float = 0.0              # 参考价
    size: float = 0.0               # 建议仓位比例（占总资金）
    timestamp: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


@dataclass
class Order:
    """模拟委托/成交"""

    code: str
    name: str
    side: str                       # BUY / SELL
    price: float
    shares: int
    amount: float
    fee: float
    reason: str
    date: str
    status: str = "FILLED"          # 模拟盘直接成交


@dataclass
class Position:
    """持仓"""

    code: str
    name: str
    shares: int
    cost: float                     # 成本价（含费用摊薄）
    open_date: str
    peak_price: float = 0.0         # 持仓期最高价（移动止盈用）

    def pnl(self, price: float) -> float:
        return (price - self.cost) / self.cost if self.cost else 0.0


@dataclass
class Trade:
    """已平仓交易记录"""

    code: str
    name: str
    open_date: str
    close_date: str
    open_price: float
    close_price: float
    shares: int
    pnl: float                      # 盈亏金额
    pnl_pct: float                  # 盈亏比例
    reason: str                     # 平仓原因


@dataclass
class Account:
    """模拟账户"""

    cash: float
    positions: dict = field(default_factory=dict)   # code -> Position
    orders: List[Order] = field(default_factory=list)
    trades: List[Trade] = field(default_factory=list)
    init_cash: float = 0.0
    updated_at: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
