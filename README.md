# 陈小群战法量化工具（cxq_quant）

把「陈小群炒股战法」转译成一套**可执行的选股 + 买卖信号 + 模拟盘**命令行工具。

> ⚠️ **合规与安全声明**：本工具**只在模拟盘运行**，不连接任何券商交易接口、不接触真实资金账户。所有信号均为策略逻辑演示，**不构成任何投资建议或个股推荐**。战法参数来自公开整理，网络口径未经本人核实，属策略假设而非精确规则。投资有风险，决策需谨慎。

---

## 战法 → 代码映射

| 战法要素 | 代码实现 | 位置 |
|---|---|---|
| 情绪周期四阶段（冰点/发酵/高潮/退潮） | 打分 + 否决项判定；用「昨日涨停基数」区分退潮与冰点 | `strategy/emotion.py` |
| 情绪定仓位（10-20% / 50-70% / ≤20% / 空仓） | 阶段 → 目标仓位；按可用槽位均分给个股 | `strategy/emotion.py` `signals.py` |
| 龙头四重标准（带动性/逻辑硬/身位/合力） | 候选股 0-100 打分，识别主线题材 | `strategy/picker.py` |
| 弱转强买点（前日烂板→竞价高开放量） | 竞价涨幅 2%-5% + 竞价量比 ≥5% 触发 BUY | `strategy/signals.py` |
| 止损铁律（单笔亏 3%-5% 无条件离场） | 最高优先级卖出信号（强度100） | `strategy/signals.py` |
| 退潮强制空仓 / 两日未达预期 / 高潮一致止盈 | 卖出规则（含移动止盈） | `strategy/signals.py` |
| 单票不超三成、最多 3 只 | 仓位约束 | `config.py` `broker/simulator.py` |

---

## 安装

```bash
cd cxq_quant
pip install -r requirements.txt   # akshare + pandas（demo 模式其实不需要）
```

## 快速开始（离线 demo，无需联网）

```bash
# 1) 看情绪周期判定
python main.py status --scene ferment

# 2) 选股打分排行
python main.py scan --scene ferment

# 3) 生成买卖信号（不执行）
python main.py signals --scene ferment

# 4) 在模拟盘执行一轮：开仓 → 记账 → 估值
python main.py reset                 # 先清空账户
python main.py run --scene ferment   # 发酵期开仓
python main.py run --scene ebb --date 20251124   # 退潮期清仓
python main.py account               # 查看账户
python main.py history               # 查看平仓记录
```

四种情绪场景：`freeze`(冰点) / `ferment`(发酵主升) / `climax`(高潮) / `ebb`(退潮) / `auto`(按日期轮动)。

## 用真实数据（akshare / 东方财富）

```bash
python main.py status --source akshare --date 20251121
python main.py scan   --source akshare --date 20251121
python main.py run    --source akshare --date 20251121
```

说明：
- 涨停池/炸板池/跌停池接口仅提供**最近 30 个交易日**数据，日期太旧会返回空。
- 东财接口偶发 `ConnectionError`，适配器内置 2 次重试；仍失败会明确报错（不静默吞错）。
- 东财不直接提供「带动跟风数 / 封单比 / 竞价量比 / 前日烂板」等字段，这些在真实模式下保留默认值 0，选股打分会相应偏低——这是接口能力边界，不是 bug。若要完整复刻战法打分，需接入 Level-2 逐笔或第三方盘口数据源。

---

## 项目结构

```
cxq_quant/
├── config.py              # 战法参数集中配置（情绪阈值/仓位/止损/费用）
├── main.py                # CLI 入口（status/scan/signals/run/account/history/reset）
├── data/
│   ├── models.py          # 数据模型（市场宽度/候选/信号/持仓/成交/账户）
│   └── feed.py            # 可插拔数据层：DataFeed + DemoFeed + AkShareFeed
├── strategy/
│   ├── emotion.py         # 情绪周期判定 + 仓位映射
│   ├── picker.py          # 主线识别 + 龙头打分
│   └── signals.py         # 买卖信号生成（风控优先）
├── broker/
│   └── simulator.py       # 模拟盘撮合/记账/估值/持久化
├── tests/
│   └── test_strategy.py   # 单元测试（9 项）
├── requirements.txt
└── README.md
```

## 运行测试

```bash
python -m unittest discover -s tests -v
```

## 账户数据

模拟账户保存在 `account.json`，持仓天数保存在 `hold_days.json`（与账户同目录）。`python main.py reset` 可一键重置。可通过 `--account path/to/acc.json` 指定独立账户文件（便于多策略并行测试）。

## 设计边界与已知限制

1. **纯模拟盘**：无真实下单能力；这是刻意的安全边界，避免误触真实资金。
2. **T+1 简化**：同一 `run` 内先卖后买；持仓天数由 `hold_days.json` 跨运行日累加。示例数据跨日价格仅小幅漂移，实盘以数据源为准。
3. **信号≠成交价**：模拟盘以快照价成交，未建模滑点、涨跌停封板买不到的情形；一字板已在选股中扣分规避。
4. **参数非精确规则**：所有阈值来自公开战法整理，需自行回测校准，切勿直接用于实盘。
5. **数据接口依赖**：akshare 字段与可用性随版本/网络变化，真实模式失败时请用 demo 验证逻辑或更新适配器。
