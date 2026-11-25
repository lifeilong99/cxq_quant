"""
可插拔数据层。

- DataFeed：抽象基类，定义取数契约
- DemoFeed：内置示例数据（离线可跑，用于验证策略逻辑）
- AkShareFeed：真实数据源适配器（需联网，东财接口）

CLI 通过 --source demo|akshare 切换。
"""
from __future__ import annotations

import random
from abc import ABC, abstractmethod
from typing import List, Tuple

from .models import MarketBreadth, Candidate


class DataFeed(ABC):
    """数据源抽象基类"""

    @abstractmethod
    def market_breadth(self, date: str) -> MarketBreadth:
        """获取市场情绪宽度（涨停/跌停/炸板/连板高度等）"""
        raise NotImplementedError

    @abstractmethod
    def candidates(self, date: str) -> List[Candidate]:
        """获取候选个股快照（涨停/强势股池）"""
        raise NotImplementedError

    @abstractmethod
    def price_of(self, code: str, date: str) -> float:
        """获取个股收盘价（模拟盘估值用）"""
        raise NotImplementedError


class DemoFeed(DataFeed):
    """
    内置示例数据源：构造覆盖四种情绪周期的场景，用于离线验证策略。

    scene 参数：
      freeze  冰点 / ferment 发酵主升 / climax 高潮 / ebb 退潮 / auto 轮动
    """

    SCENES = {
        # 冰点：昨日涨停基数本就低（非高热骤降），跌停多、无高度
        "freeze": dict(limit_up=12, limit_down=28, broken=18, max_streak=2,
                       streak_count=3, prev_limit_up=18, turnover=8200),
        "ferment": dict(limit_up=72, limit_down=4, broken=16, max_streak=6,
                        streak_count=24, prev_limit_up=55, turnover=11800),
        "climax": dict(limit_up=105, limit_down=3, broken=42, max_streak=8,
                       streak_count=38, prev_limit_up=88, turnover=15600),
        "ebb": dict(limit_up=22, limit_down=45, broken=38, max_streak=4,
                    streak_count=6, prev_limit_up=95, turnover=9800),
    }

    STOCK_POOL = [
        # code, name, 题材, 基准连板, 带动数, 封单比, 竞价涨幅, 竞价量比, 前日烂板, 换手, 流通市值
        ("600XXX", "主线总龙", "AI算力", 5, 9, 0.08, 0.035, 0.09, False, 12.0, 120),
        ("001XXX", "中位活口", "AI算力", 3, 5, 0.05, 0.028, 0.07, True, 18.0, 80),
        ("300XXX", "低位补涨", "AI算力", 2, 6, 0.04, 0.022, 0.06, True, 22.0, 55),
        ("002XXX", "新题材龙", "机器人", 3, 7, 0.06, 0.032, 0.08, False, 15.0, 95),
        ("603XXX", "孤庄票", "无明确题材", 4, 1, 0.02, 0.010, 0.02, False, 8.0, 40),
        ("000XXX", "跟风杂毛", "AI算力", 1, 2, 0.01, 0.008, 0.01, False, 30.0, 35),
        ("688XXX", "科创龙头", "半导体", 3, 6, 0.05, 0.026, 0.07, True, 14.0, 110),
        ("605XXX", "弱转强标的", "机器人", 2, 5, 0.045, 0.031, 0.065, True, 20.0, 60),
    ]

    def __init__(self, scene: str = "ferment", seed: int = 20261125):
        self.scene = scene
        self.seed = seed
        self._price_cache: dict = {}
        # 按 code 生成稳定基准价，保证跨日期连续（避免演示中出现不合理跳变）
        self._base_price: dict = {}

    def _stable_price(self, code: str, date: str) -> float:
        """基准价由 code 决定，日期只带来小幅漂移（±3%），跨日连续"""
        if code not in self._base_price:
            rng = random.Random(self.seed + sum(ord(c) * (i + 1) for i, c in enumerate(code)))
            self._base_price[code] = round(10 + rng.random() * 30, 2)
        base = self._base_price[code]
        rng = random.Random(self.seed + int(date or "0") + sum(ord(c) for c in code))
        drift = rng.uniform(-0.03, 0.03)
        return round(base * (1 + drift), 2)

    def _scene_key(self, date: str) -> str:
        if self.scene == "auto":
            # 按日期末位轮动场景，保证同一日期结果稳定
            scenes = list(self.SCENES.keys())
            digit = int((date or "0")[-1]) if (date or "0")[-1].isdigit() else 0
            return scenes[digit % len(scenes)]
        return self.scene if self.scene in self.SCENES else "ferment"

    def market_breadth(self, date: str) -> MarketBreadth:
        key = self._scene_key(date)
        d = dict(self.SCENES[key])
        return MarketBreadth(date=date, **d)

    def candidates(self, date: str) -> List[Candidate]:
        rng = random.Random(self.seed + int(date or "0"))
        key = self._scene_key(date)
        decay = key in ("freeze", "ebb")   # 弱势场景降低带动与封单
        out: List[Candidate] = []
        for code, name, theme, streak, driven, seal, auc, aucv, prevbr, turn, mv in self.STOCK_POOL:
            if decay:
                driven = max(1, driven // 2)
                seal = round(seal * 0.5, 3)
                auc = round(auc * 0.3, 3)
                aucv = round(aucv * 0.4, 3)
            price = self._stable_price(code, date)
            self._price_cache[code] = price
            out.append(Candidate(
                code=code, name=name, price=price,
                change_pct=round(0.03 + rng.random() * 0.07, 4),
                streak=streak, driven=driven, board_reason=theme,
                is_one_word=(rng.random() < 0.15),
                broken_times=rng.randint(0, 2),
                seal_ratio=seal, auction_change=auc, auction_vol_ratio=aucv,
                prev_broken=prevbr, turnover=turn, float_mv=mv,
            ))
        return out

    def price_of(self, code: str, date: str) -> float:
        return self._stable_price(code, date)


class AkShareFeed(DataFeed):
    """
    真实数据源适配器（akshare / 东方财富）。

    注意：
    1. 东财接口偶发 ConnectionError，调用方应设置重试；
    2. 涨停池/炸板池/跌停池仅提供最近 30 个交易日数据；
    3. 候选股的「带动数/封单比/竞价量比/前日烂板」等字段东财不直接提供，
       此处尽力映射，缺失字段保留默认值 0/False，由策略层按缺失处理。
    """

    def __init__(self, retry: int = 2):
        self.retry = retry
        self._price_cache: dict = {}

    def _call(self, fn, *args, **kwargs):
        import akshare as ak  # 延迟导入，demo 模式无需安装
        last = None
        for i in range(self.retry):
            try:
                return fn(*args, **kwargs)
            except Exception as e:  # 明确向东财重试，不吞错
                last = e
        raise RuntimeError(f"akshare 接口调用失败（已重试 {self.retry} 次）: {last}") from last

    @staticmethod
    def _to_int(v) -> int:
        try:
            return int(float(v))
        except (TypeError, ValueError):
            return 0

    def market_breadth(self, date: str) -> MarketBreadth:
        import akshare as ak
        zt = self._call(ak.stock_zt_pool_em, date=date)
        dt = self._call(ak.stock_zt_pool_dtgc_em, date=date)
        zb = self._call(ak.stock_zt_pool_zbgc_em, date=date)
        prev = self._call(ak.stock_zt_pool_previous_em, date=date)

        streak_series = zt["连板数"] if "连板数" in zt.columns else None
        return MarketBreadth(
            date=date,
            limit_up=len(zt),
            limit_down=len(dt),
            broken=len(zb),
            max_streak=self._to_int(streak_series.max()) if streak_series is not None and len(zt) else 0,
            streak_count=int((streak_series >= 2).sum()) if streak_series is not None else 0,
            prev_limit_up=len(prev),
            turnover=0.0,
        )

    def candidates(self, date: str) -> List[Candidate]:
        import akshare as ak
        zt = self._call(ak.stock_zt_pool_em, date=date)
        if zt.empty:
            return []
        out: List[Candidate] = []
        # 题材采用所属行业做粗分类（东财涨停池无概念题材字段）；
        # 真正的概念主线需另取板块数据，此处以行业近似，避免把「涨停统计 3/3」误当题材。
        for _, r in zt.iterrows():
            code = str(r.get("代码", "")).zfill(6)
            price = self._to_int(r.get("最新价") * 100) / 100 if r.get("最新价") else 0.0
            self._price_cache[code] = price
            # 封单比 = 封板资金 / 流通市值（合力验证代理指标）
            float_mv = float(r.get("流通市值", 0)) if r.get("流通市值") else 0.0
            seal_fund = float(r.get("封板资金", 0)) if r.get("封板资金") else 0.0
            seal_ratio = seal_fund / float_mv if float_mv > 0 else 0.0
            # 一字板近似：首次封板=最后封板=09:25 且炸板次数为 0
            t0 = str(r.get("首次封板时间", ""))
            t1 = str(r.get("最后封板时间", ""))
            is_one_word = (t0 == "092500" and t1 == "092500"
                           and self._to_int(r.get("炸板次数")) == 0)
            out.append(Candidate(
                code=code,
                name=str(r.get("名称", "")),
                price=price,
                change_pct=float(r.get("涨跌幅", 0)) / 100 if r.get("涨跌幅") else 0.0,
                streak=self._to_int(r.get("连板数")),
                driven=0,  # 东财不提供带动数，策略层按缺失处理
                board_reason=str(r.get("所属行业", "")) or "其他",
                is_one_word=is_one_word,
                broken_times=self._to_int(r.get("炸板次数")),
                seal_ratio=seal_ratio,
                auction_change=0.0,   # 东财涨停池无竞价字段，保留默认
                auction_vol_ratio=0.0,
                prev_broken=False,
                turnover=float(r.get("换手率", 0)) if r.get("换手率") else 0.0,
                float_mv=float_mv / 1e8 if float_mv else 0.0,
            ))
        return out

    def price_of(self, code: str, date: str) -> float:
        if code in self._price_cache:
            return self._price_cache[code]
        # 兜底：用当日历史行情取收盘价
        import akshare as ak
        hist = self._call(ak.stock_zh_a_hist, symbol=code, period="daily",
                          start_date=date, end_date=date, adjust="qfq")
        price = float(hist.iloc[-1]["收盘"]) if hist is not None and len(hist) else 0.0
        if price:
            self._price_cache[code] = price
        return price


def get_feed(source: str, **kwargs) -> DataFeed:
    """工厂方法"""
    source = (source or "demo").lower()
    if source == "demo":
        return DemoFeed(**kwargs)
    if source in ("akshare", "ak", "real"):
        return AkShareFeed(**kwargs)
    raise ValueError(f"未知数据源: {source}（可选 demo / akshare）")
