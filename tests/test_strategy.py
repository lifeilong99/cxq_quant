"""
单元测试：情绪判定、选股、信号、模拟盘。
运行：python -m unittest discover -s tests -v
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import DEFAULT
from data.feed import get_feed, DemoFeed
from data.models import MarketBreadth, Candidate, Position, Signal
from strategy.emotion import judge_emotion, position_for_emotion
from strategy.picker import detect_mainline, pick_leaders, score_candidate
from strategy.signals import should_buy, should_sell, generate_signals
from broker.simulator import Simulator


class TestEmotion(unittest.TestCase):
    def test_four_scenes(self):
        feed = DemoFeed("ferment")
        cases = {
            "freeze": "freeze",
            "ferment": "ferment",
            "climax": "climax",
            "ebb": "ebb",
        }
        for scene, expect in cases.items():
            feed.scene = scene
            b = feed.market_breadth("20251121")
            stage, score, note = judge_emotion(b)
            self.assertEqual(stage, expect, f"{scene} 期望 {expect}，实际 {stage}（分{score}：{note}）")

    def test_position_mapping(self):
        self.assertEqual(position_for_emotion("ebb"), 0.0)
        self.assertGreater(position_for_emotion("ferment"), 0.5)
        self.assertLess(position_for_emotion("climax"), 0.3)


class TestPicker(unittest.TestCase):
    def test_mainline(self):
        feed = DemoFeed("ferment")
        cands = feed.candidates("20251121")
        mainline, drive = detect_mainline(cands)
        self.assertEqual(mainline, "AI算力")
        ranked = pick_leaders(cands)
        self.assertGreater(ranked[0][1], ranked[-1][1])

    def test_one_word_penalty(self):
        c = Candidate(code="1", name="t", board_reason="AI算力", driven=8, streak=5,
                      seal_ratio=0.08, is_one_word=True)
        c2 = Candidate(code="2", name="t2", board_reason="AI算力", driven=8, streak=5,
                       seal_ratio=0.08, is_one_word=False)
        s1, _ = score_candidate(c, "AI算力")
        s2, _ = score_candidate(c2, "AI算力")
        self.assertLess(s1, s2)


class TestSignals(unittest.TestCase):
    def test_no_buy_in_ebb(self):
        feed = DemoFeed("ebb")
        b = feed.market_breadth("20251121")
        cands = feed.candidates("20251121")
        sigs = generate_signals(b, cands, {}, {}, {})
        self.assertFalse([s for s in sigs if s.action == "BUY"])

    def test_stop_loss(self):
        pos = Position(code="1", name="t", shares=100, cost=10.0, open_date="20251120")
        sig = should_sell(pos, 9.4, "ferment", 1)  # -6%
        self.assertIsNotNone(sig)
        self.assertEqual(sig.action, "SELL")
        self.assertIn("止损", sig.reason)

    def test_buy_in_ferment(self):
        feed = DemoFeed("ferment")
        b = feed.market_breadth("20251121")
        cands = feed.candidates("20251121")
        sigs = generate_signals(b, cands, {}, {}, {})
        self.assertTrue(any(s.action == "BUY" for s in sigs))


class TestSimulator(unittest.TestCase):
    def test_buy_sell_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            acc_file = os.path.join(d, "acc.json")
            sim = Simulator(account_file=acc_file)
            buy = Signal("600001", "测试股", "BUY", "test", 90, 10.0, 0.3)
            res = sim.execute(buy, 10.0, "20251121")
            self.assertIn("买入", res)
            self.assertEqual(len(sim.account.positions), 1)
            pos = sim.account.positions["600001"]
            # T+1：模拟次日卖出
            sell = Signal("600001", "测试股", "SELL", "test", 90, 11.0)
            res = sim.execute(sell, 11.0, "20251124")
            self.assertIn("卖出", res)
            self.assertEqual(len(sim.account.positions), 0)
            self.assertEqual(len(sim.account.trades), 1)
            self.assertGreater(sim.account.trades[0].pnl, 0)
            self.assertGreater(sim.valuation({"600001": 11.0}).total, 0)

    def test_reset(self):
        with tempfile.TemporaryDirectory() as d:
            acc_file = os.path.join(d, "acc.json")
            sim = Simulator(account_file=acc_file)
            sim.execute(Signal("1", "t", "BUY", "t", 90, 10, 0.3), 10, "20251121")
            sim.reset()
            self.assertEqual(len(sim.account.positions), 0)
            self.assertEqual(sim.account.cash, sim.account.init_cash)


if __name__ == "__main__":
    unittest.main()
