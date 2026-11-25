"""
全局配置：把陈小群战法的关键参数集中在此，便于调参。

参数来源均为公开战法整理，网络口径未经本人核实 —— 属策略假设，非精确规则。
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class EmotionConfig:
    """情绪周期判定参数（战法：冰点/发酵/高潮/退潮四阶段）"""

    # 涨停家数分档
    limit_up_freeze: int = 20        # 低于此值 = 冰点
    limit_up_hot: int = 60           # 高于此值 = 情绪偏热
    # 连板高度
    max_streak_low: int = 3          # 最高板 <= 此值 = 无高度
    max_streak_high: int = 7         # 最高板 >= 此值 = 高度打开
    # 炸板率（炸板数 / (涨停数+炸板数)）
    break_rate_high: float = 0.40    # 高于此值 = 亏钱效应
    # 跌停家数
    limit_down_high: int = 15       # 高于此值 = 退潮特征
    # 晋级率（连板数 / 昨日涨停数）
    promotion_low: float = 0.15      # 低于此值 = 接力意愿弱


@dataclass
class PositionConfig:
    """仓位参数（战法：情绪定仓位）"""

    freeze_pos: float = 0.15         # 冰点试错仓位 10-20%
    ferment_pos: float = 0.60        # 发酵主升仓位 50-70%
    climax_pos: float = 0.20         # 高潮降至 20% 以内
    ebb_pos: float = 0.00            # 退潮空仓
    max_single_stock: float = 0.30   # 单票仓位不超过三成
    max_holdings: int = 3            # 最多持有标的数


@dataclass
class SignalConfig:
    """买卖信号参数"""

    # 止损
    stop_loss: float = 0.05          # 单笔亏损超 5% 无条件离场
    stop_loss_strict: float = 0.03   # 严格版 3%
    # 持有预期
    max_hold_days: int = 2           # 买入两日内未达预期平仓
    # 弱转强买点
    weak_to_strong_open_min: float = 0.02   # 竞价高开 >= 2%
    weak_to_strong_open_max: float = 0.05   # 竞价高开 <= 5%
    auction_vol_ratio: float = 0.05  # 竞价量 >= 前日成交 5%
    # 卖出：一致（止盈）
    take_profit: float = 0.15        # 一致阶段分批兑现参考
    # 龙头带动性门槛
    min_driven_stocks: int = 5       # 带动至少 5 只跟风涨停


@dataclass
class BacktestConfig:
    """回测/模拟盘参数"""

    init_cash: float = 1_000_000.0   # 初始资金
    commission: float = 0.0003      # 佣金万三
    stamp_duty: float = 0.001       # 印花税千一（卖出）
    min_commission: float = 5.0     # 最低佣金 5 元
    lot_size: int = 100             # 一手 100 股


@dataclass
class Config:
    emotion: EmotionConfig = field(default_factory=EmotionConfig)
    position: PositionConfig = field(default_factory=PositionConfig)
    signal: SignalConfig = field(default_factory=SignalConfig)
    backtest: BacktestConfig = field(default_factory=BacktestConfig)
    # 数据源：demo（内置示例，离线可跑） / akshare（需联网）
    data_source: str = "demo"
    # 模拟账户持久化路径
    account_file: str = "account.json"


DEFAULT = Config()
