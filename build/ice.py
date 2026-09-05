# -*- coding: utf-8 -*-
"""洲际交易所（ICE）月度经营指标 —— 网页看板生成器。

本页 2026-09 从声明式（`build/specs/ice.py` + 通用底座 `build/single.py`）改写成手写，
与 `build/cme.py` / `build/cboe.py` 同构。改写的判据是三条**引擎做不到**的事，不是审美：

  1. 引擎画不了派生列 —— `single.py:1425-1440` 硬失败于任何不在 CSV 里的列名，
     而本页的隐含交易收入、指数化的单位经济、A+B+C matched 合计都是派生的；
  2. 引擎发不了 `bridge_bar`，而量价分解是本页的落点；
  3. 引擎的图题与图注全在底座内部拼装（`:2145` `:2258` `:2301` `:3013`，
     `COL_KEYS` / `GROUP_KEYS` 里既没有 `note` 也没有 `title`），
     而本页每一张图都要说清自己的口径与代价。

⚠️ 改写**丢掉了底座的六族护栏**（口径判据 / 同比账本 / 近零与数据形状 / 图型排版 /
   mix / 散文与写出）。本文件的对策不是各抄一份，而是 **`import single as SG` 复用判据本身**：
   `SG.col_is_ratio` / `col_is_money_ratio` / `rhs_ylab2` / `money_diff_txt` / `ratio_diff_txt`
   吃的就是 `COL` 里那种列字典，所以本页保留**与引擎完全同形的列元数据表**再喂给它。
   实测（本文件 COL 断言表每次构建现验）：
       rpc_energy_usd                 ratio=True  money=True  'USD/contract, y/y 差（单月）'
       rpc_nyse_us_cash_usd_per100sh  ratio=True  money=True  'USD/100 shares, y/y 差（单月）'
       share_nyse_tapeA_matched       ratio=True  money=False 'pp y/y（单月）'
       oi_rates_kcontracts            ratio=False money=False '% y/y（单月）'   ← 见下
   最后一条是 `yoy.classify()` 的假阳性（列名里有 `rates` 就判成比率，它其实是存量），
   今天挡住它的**只有** unit 串 `k contracts`。⇒ **`unit` 是承重的，改一个字判定就会翻掉且不报错。**
   `build/pctile.py` 模块头记的那条教训在这里逐字适用：各写各的，正是同一条序列在两页被判定相反的原因。

⚠️ 删掉 `build/specs/ice.py` 是本次改写的**必要一步**，不是顺手清理：
   `single.py --all` 的反向守卫判据是「`build/<t>.py` 里有没有 mrbase 字样」，本文件没有 ——
   spec 只要还在，任何人跑一次那条命令（两份文档都在教）就会把 data/ice.js **静默**覆盖回旧图列。
   本轮同时把那道守卫改成了「`build/<t>.py` 存在就跳过」，与 `monthly_run.builder()` 同源。

━━ 页面在论证什么 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
**一张合约不是一块钱。**头条那个数把每张 1.9 美元的大宗商品合约与每张 0.5 美元的欧洲
短端利率合约相加，所以它本身信息量很低。图序因此是一条因果链而不是分类目录：
  ① 规模（Ex2-3）→ ② 一张合约不是一块钱（Ex4）→ ③ 把量翻译成钱（Ex5-9）
  → ④ 能源特许经营（Ex10-12）→ ⑤ 另一半公司 NYSE：问题不是单价而是还剩多少市场（Ex13-17）
  → ⑥ 这个恒等式看不见的那一块（Ex18）
两条头条列**刻意分开**：Ex2 起「一张合约值多少钱」，Ex15 起「还剩多少市场」——
并排放在页首等于宣称它们是同一个问题的两半。页顶数据条仍然两条都给（那是数据条不是 exhibit）。

━━ 收入块为什么是季度 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ICE 不披露成交金额，也不按月披露分部收入，但它按月给 ADV 与 RPC，而 RPC 的官方定义就是
`交易收入 ÷ 合约量`。于是：
    季度收入 = Σ_{季内三月}(ADV × 该腿的交易日列) × **季末月** RPC ÷ 换算因子
之所以取季末月：RPC 是**滚动三月均**，季末月那一格的窗口恰好覆盖该季度 —— 这不是近似，
是把官方定义反读回去。六个能与 ICE Key Metrics 对账的点上，本形式全部落在 ±1.02% 内，
而逐月形式一律偏低 0.57–2.15%。⚠️ 但**不许**因此宣称「逐月形式系统性低估」：
全样本 62 季 × 6 腿实测中位 0.000%、区间 −10.14%~+19.82%，那是一句会被下季度证伪的话。

⚠️ 交易日配对是本页最容易翻车的一处：工作表行名写着 "COMMODITIES & OTHER FINANCIALS"，
   但**金融四条腿全部用 `trading_days_rates`**（已用 10-K FY2025 合约数双向证伪）。
⚠️ NYSE 现货那条腿的换算因子是 **÷100 不是 ÷1000**（RPC 是每 100 股）。用错低估 10 倍。
⚠️ 桥只覆盖**衍生品四腿**：六腿凑不出单一的量（四条衍生品腿与期权腿是千张、现货腿是百万股）。
   期权腿单独的桥也放弃 —— 它的费率只有 2 位小数而量程 0.04–0.18，低端一格就是 25%。

━━ 本文件的来历 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
分十二段并线写成（载入 / 列元数据与口径 / 护栏 / 图注现算 / 收入 / 桥 / 构图库 /
汇总表 / 释义 / 页尾 / brief / 核对表），装配时的裁决规则是**宁可留重复，不许静默换语义**：
同名且实现相同或实测行为等价的塌成一份，其余一律改名保留（`<名字>__<段名>`）。
"""
import os, sys, re, json, math
import numpy as np
import pandas as pd
import single as SG
import yoy as YOY
import payload_guard
import pctile
import mrwin
import axisfmt
import chartscale
import glossary as gloss
import os, sys, re, math
import csv
import os
import sys
import math
import re
import itertools
import brief as B
import os, sys, json, re



# ==========================================================================
# 【loader】
# ==========================================================================

# -*- coding: utf-8 -*-
"""build/ice.py 的【载入层 + 格式化层】—— 合并时整段搬进 build/ice.py 的开头。

本文件是分段草稿：底部的 `if __name__ == '__main__':` 自测块**合并时删掉**，
其余（导入、常量、COL、load()、格式化函数、窗口、col()）逐行进正式文件。

它负责的三件事，别的段一件都不许重做：
  1. **唯一的读盘口**：`load()` 是 series/ice.csv 进入本页的唯一入口，
     所有结构性校验（列齐不齐、月份连不连续、能不能转成数）都在它里面响。
  2. **唯一的列元数据表 `COL`**：ICE 的口径判定（同比该印百分数、百分点还是美元差）
     全部由 `unit` 字符串决定，而这个字符串在 build/specs/ice.py 里是**承重的**
     （见 specs/ice.py:560、:587-589）。手写页没有引擎那套 spec 校验，
     所以这张表必须与 specs 逐字一致，并在构建期把 build/single.py 的判据现跑一遍。
  3. **唯一的窗口定义**：本页有四个互不相同的窗口（月度图窗 / 全历史 / 核对表 /
     季度收入块），每个都在下面各自的注释里交代它服务哪几张图、为什么不能共用。
"""

HERE = os.path.dirname(os.path.abspath(__file__))

# ── 分段草稿期的 ROOT 修正 ───────────────────────────────────────────────
# 正式文件里 HERE 是 <repo>/build，ROOT 就是仓库根，`ROOT = os.path.dirname(HERE)`
# 一行到位。草稿在 scratchpad 下跑，两行只在这里存在，**合并时连同这段注释一起删**，
# 换回冻结契约里那两行（`ROOT = os.path.dirname(HERE)` + `sys.path.insert(0, HERE)`）。
_REPO = '/Users/hzhan/Documents/monthly-op-dashboards/.claude/worktrees/cboe-page-redesign-dc42f8'

ROOT = _REPO

sys.path.insert(0, os.path.join(ROOT, 'build'))

CSV = os.path.join(ROOT, 'series', 'ice.csv')

OUT = os.path.join(ROOT, 'data', 'ice.js')

SERIES = os.path.join(ROOT, 'series')

SRC = ('Source: ICE Monthly Statistics Tracking spreadsheet (ir.theice.com ContentAsset feed, '
       'file hosted on s2.q4cdn.com); format after Goldman Sachs GIR')

# ══════════════════════════ 发布日台账（按路径加载）══════════════════════════
def _source_dates():
    """按路径加载仓库根的 source_dates.py。

    理由与 build/cme.py:53-57、build/cboe.py:120-129 完全相同、那两处都写了：
    本文件是 `python3 build/ice.py` 跑起来的，sys.path 上只有 build/，
    而 source_dates.py 躺在仓库根，裸 `import source_dates` 会 ModuleNotFoundError。
    调用方式：`source_dates.lookup(SERIES, 'ice', str(CUR))`（同 cme.py:2840）。
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        'source_dates', os.path.join(ROOT, 'source_dates.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

source_dates = _source_dates()

# ══════════════════ 列元数据表 COL —— 全页口径判定的唯一入口 ══════════════════
#
# 手写页没有 build/single.py 那套 spec 驱动，但**口径判据必须还是它那一套**：
# `SG.col_is_ratio()` / `SG.col_is_money_ratio()` / `SG.rhs_ylab2()` /
# `SG.money_diff_txt()` / `SG.ratio_diff_txt()` / `SG.chg_txt()` 吃的都是
# 「一个带 col/zh/unit/fmt 的字典」（见 single.py:218-232 的签名）。
# 所以这里保留**与引擎完全同形的列字典**，再把 single.py 的判据直接喂给它。
# build/pctile.py 的模块头记着这条教训：各写各的判据，正是同一条序列在两页被
# 判定相反的原因。本页因此一处自写判据都没有。
#
# ⚠️ **`unit` 字符串是承重的**（specs/ice.py:560 与 :587-589 逐条写了为什么）：
#   · `oi_rates_kcontracts` 的列名里有 `rates`，`yoy.classify()` 把它误判成比率 ——
#     挡住这个假阳性的**只有** unit `k contracts`（不是比率量纲）。把它改写成
#     「千张未平仓」之类的中文，次轴当场从「% y/y」翻成「pp y/y」，而且不报错。
#   · `USD/contract` / `USD/100 shares` 走 `unit_is_money_ratio()`（single.py:202），
#     它们的同比差是**钱**不是百分点；改写成 `$/contract` 也许还认得出，
#     改成「元/张」就认不出了，NYSE 期权 RPC 从 0.05 跌到 0.04（跌五分之一）
#     会被印成「−1bp」（single.py:180-186 记的就是这次事故）。
# ⇒ 合法 unit 只有下面这七个串，逐字来自 build/specs/ice.py，别为了排版好看改写。
#    下面 `_UNIT_WHITELIST` 在构建期现验，改一个字当场停机。
_UNIT_WHITELIST = {'k contracts/day', 'k contracts', 'USD/contract',
                   'USD/100 shares', 'mn shares/day', 'USD bn/month', '%'}

#: 三条交易日列。**不进 COL** —— 它们是归一化的除数，一张图都不上，
#: 也没有一个合法 unit 能描述它们（'days' 不在白名单里）。
#: ICE 有**三套**交易日，各条 ADV 各归一各的；总 ADV 横跨商品与美股两侧，
#: 没有哪一套日历能代表它 ⇒ 谁都不许把总 ADV 乘回成当月合计。
TRADING_DAYS = ('trading_days_commod', 'trading_days_rates', 'trading_days_us_equities')

COL = {
    # ── 能源：六个子项 + 合计。官方已四舍五入到整千张，六项之和 == 合计只在
    #    一部分月份精确成立 ⇒ 不是恒等式，别拿它当校验（也是 Ex10 不能用
    #    gs_bar stacks 的原因：那个图型要求逐格闭合，容差 1e-6，会硬 ERROR）。
    'adv_energy_kcontracts':         {'col': 'adv_energy_kcontracts',         'zh': '能源合计',           'unit': 'k contracts/day', 'fmt': 'f0c'},
    'adv_brent_kcontracts':          {'col': 'adv_brent_kcontracts',          'zh': 'Brent 原油',         'unit': 'k contracts/day', 'fmt': 'f0c'},
    'adv_gasoil_kcontracts':         {'col': 'adv_gasoil_kcontracts',         'zh': 'Gasoil 柴油',        'unit': 'k contracts/day', 'fmt': 'f0c'},
    'adv_otheroil_kcontracts':       {'col': 'adv_otheroil_kcontracts',       'zh': '其他原油与成品油',   'unit': 'k contracts/day', 'fmt': 'f0c'},
    'adv_natgas_kcontracts':         {'col': 'adv_natgas_kcontracts',         'zh': '天然气（含 TTF）',   'unit': 'k contracts/day', 'fmt': 'f0c'},
    'adv_power_kcontracts':          {'col': 'adv_power_kcontracts',          'zh': '电力',               'unit': 'k contracts/day', 'fmt': 'f0c'},
    'adv_environmentals_kcontracts': {'col': 'adv_environmentals_kcontracts', 'zh': '环境权益与其他',     'unit': 'k contracts/day', 'fmt': 'f0c'},

    # ── 农产品与金属 + 大宗商品合计
    'adv_ag_metals_kcontracts':       {'col': 'adv_ag_metals_kcontracts',       'zh': '农产品与金属合计',       'unit': 'k contracts/day', 'fmt': 'f0c'},
    'adv_sugar_kcontracts':           {'col': 'adv_sugar_kcontracts',           'zh': '糖',                     'unit': 'k contracts/day', 'fmt': 'f0c'},
    'adv_otherags_metals_kcontracts': {'col': 'adv_otherags_metals_kcontracts', 'zh': '其他农产品与金属',       'unit': 'k contracts/day', 'fmt': 'f0c'},
    'adv_commodities_kcontracts':     {'col': 'adv_commodities_kcontracts',     'zh': '大宗商品合计（能源+农金）', 'unit': 'k contracts/day', 'fmt': 'f0c'},

    # ── 金融：ICE 的利率腿是**欧洲曲线**（Euribor / SONIA / Gilts）。
    #    `adv_single_stock_kcontracts` 官方明说已从 TOTAL FINANCIALS 剔除；
    #    `adv_fx_credit_kcontracts` 行名写 CREDIT 但**不含信用**（specs/ice.py 第 7 条）。
    'adv_financials_kcontracts':      {'col': 'adv_financials_kcontracts',      'zh': '金融合计（不含单股）', 'unit': 'k contracts/day', 'fmt': 'f0c'},
    'adv_stir_kcontracts':            {'col': 'adv_stir_kcontracts',            'zh': '短期利率',             'unit': 'k contracts/day', 'fmt': 'f0c'},
    'adv_mltir_kcontracts':           {'col': 'adv_mltir_kcontracts',           'zh': '中长期利率',           'unit': 'k contracts/day', 'fmt': 'f0c'},
    'adv_equity_index_kcontracts':    {'col': 'adv_equity_index_kcontracts',    'zh': '股指',                 'unit': 'k contracts/day', 'fmt': 'f0c'},
    'adv_fx_credit_kcontracts':       {'col': 'adv_fx_credit_kcontracts',       'zh': 'FX 与 USDX',           'unit': 'k contracts/day', 'fmt': 'f0c'},
    'adv_single_stock_kcontracts':    {'col': 'adv_single_stock_kcontracts',    'zh': '单股（已剔出合计）',   'unit': 'k contracts/day', 'fmt': 'f0c'},
    'adv_futures_options_kcontracts': {'col': 'adv_futures_options_kcontracts', 'zh': '期货与期权总计',       'unit': 'k contracts/day', 'fmt': 'f0c'},

    # ── OI：月末净未平仓，**存量**（stock=True）。同比是点对点，不是「单月同比」。
    #    单位 `k contracts` 与 series/cme.csv 的 oi_*_contracts（裸张）差 1000 倍 ——
    #    横截面上最容易翻车的一处。官方**没有 TOTAL OI 行**。
    'oi_commodities_kcontracts':      {'col': 'oi_commodities_kcontracts',      'zh': '大宗商品',     'unit': 'k contracts', 'fmt': 'f0c', 'stock': True},
    'oi_energy_kcontracts':           {'col': 'oi_energy_kcontracts',           'zh': '能源',         'unit': 'k contracts', 'fmt': 'f0c', 'stock': True},
    'oi_ag_metals_kcontracts':        {'col': 'oi_ag_metals_kcontracts',        'zh': '农产品与金属', 'unit': 'k contracts', 'fmt': 'f0c', 'stock': True},
    'oi_financials_kcontracts':       {'col': 'oi_financials_kcontracts',       'zh': '金融',         'unit': 'k contracts', 'fmt': 'f0c', 'stock': True},
    # ⚠️ 见文件头：这一列是 unit 承重的活样本，`k contracts` 五个字符挡住了
    #    `yoy.classify()` 的假阳性。下面 _UNIT_LOAD_BEARING 每次构建都现验一遍。
    'oi_rates_kcontracts':            {'col': 'oi_rates_kcontracts',            'zh': '利率',         'unit': 'k contracts', 'fmt': 'f0c', 'stock': True},
    'oi_other_financials_kcontracts': {'col': 'oi_other_financials_kcontracts', 'zh': '股指与 FX',    'unit': 'k contracts', 'fmt': 'f0c', 'stock': True},

    # ── RPC：**滚动三月均**的费率，不是成交价，也**不能乘单月量当单月收入**。
    #    ICE 的 RPC **不滞后**（与 Cboe 相反）—— Cboe 那边空白 RPC 是滞后，
    #    这边空白就是真缺。六列都是「分子是钱」的比率，同比差的单位是 USD/contract。
    'rpc_commodities_usd':      {'col': 'rpc_commodities_usd',      'zh': '大宗商品',     'unit': 'USD/contract', 'fmt': 'f2'},
    'rpc_energy_usd':           {'col': 'rpc_energy_usd',           'zh': '能源',         'unit': 'USD/contract', 'fmt': 'f2'},
    'rpc_ag_metals_usd':        {'col': 'rpc_ag_metals_usd',        'zh': '农产品与金属', 'unit': 'USD/contract', 'fmt': 'f2'},
    'rpc_financials_usd':       {'col': 'rpc_financials_usd',       'zh': '金融',         'unit': 'USD/contract', 'fmt': 'f2'},
    'rpc_rates_usd':            {'col': 'rpc_rates_usd',            'zh': '利率',         'unit': 'USD/contract', 'fmt': 'f2'},
    'rpc_other_financials_usd': {'col': 'rpc_other_financials_usd', 'zh': '股指与 FX',    'unit': 'USD/contract', 'fmt': 'f2'},

    # ── NYSE 美股期权：`adv_us_equity_options_industry_kcontracts` 是**全行业分母**，
    #    全仓最值钱的几列之一（NYSE / Cboe multilist / MIAX 才能同分母算份额）。
    'adv_us_equity_options_industry_kcontracts': {'col': 'adv_us_equity_options_industry_kcontracts', 'zh': '全美股票/ETF 期权行业总量', 'unit': 'k contracts/day', 'fmt': 'f0c'},
    'adv_nyse_equity_options_kcontracts':        {'col': 'adv_nyse_equity_options_kcontracts',        'zh': 'NYSE 两所合计',            'unit': 'k contracts/day', 'fmt': 'f0c'},
    'share_nyse_equity_options':                 {'col': 'share_nyse_equity_options',                 'zh': 'NYSE 份额（官方直接给）',  'unit': '%', 'fmt': 'pct1', 'scale': 100},
    # ⚠️ 这一列只有 2 位小数而量程 0.04–0.18，低端一格 = 25% ——
    #    它是「期权腿单独的 bridge 必须放弃」的根因，别在这里给它加位数。
    'rpc_nyse_equity_options_usd':               {'col': 'rpc_nyse_equity_options_usd',               'zh': 'NYSE 期权 RPC',            'unit': 'USD/contract', 'fmt': 'f2'},

    # ── NYSE 美股现货：`adv_tape{A,B,C}_consolidated_mnsh` 是**全市场**合并量，
    #    不是 NYSE 自己的 —— 这个分母只有 ICE 披露。
    #    三条 Tape 份额的分母是**该带自己**的合并量；
    #    `share_nyse_us_cash_matched` 才是三带之和 ÷ 三带之和。
    'adv_nyse_us_cash_handled_mnsh':  {'col': 'adv_nyse_us_cash_handled_mnsh',  'zh': 'NYSE Group handled ADV',  'unit': 'mn shares/day', 'fmt': 'f0c'},
    'share_nyse_us_cash_matched':     {'col': 'share_nyse_us_cash_matched',     'zh': 'NYSE 全美 matched 份额',  'unit': '%', 'fmt': 'pct1', 'scale': 100},
    # ⚠️ 量纲 USD/**100 shares** —— 隐含收入那条腿的换算因子是 1/100，不是 1/1000。
    #    用错成 ÷1000 会把现货收入低估 10 倍。
    'rpc_nyse_us_cash_usd_per100sh':  {'col': 'rpc_nyse_us_cash_usd_per100sh',  'zh': '现货 RPC（每 100 股）',   'unit': 'USD/100 shares', 'fmt': 'f3'},

    'adv_tapeA_consolidated_mnsh':    {'col': 'adv_tapeA_consolidated_mnsh',    'zh': 'Tape A 全市场',        'unit': 'mn shares/day', 'fmt': 'f0c'},
    'adv_nyse_tapeA_matched_mnsh':    {'col': 'adv_nyse_tapeA_matched_mnsh',    'zh': 'Tape A · NYSE matched', 'unit': 'mn shares/day', 'fmt': 'f0c'},
    'adv_nyse_tapeA_handled_mnsh':    {'col': 'adv_nyse_tapeA_handled_mnsh',    'zh': 'Tape A · NYSE handled', 'unit': 'mn shares/day', 'fmt': 'f0c'},
    'share_nyse_tapeA_matched':       {'col': 'share_nyse_tapeA_matched',       'zh': 'Tape A 份额',          'unit': '%', 'fmt': 'pct1', 'scale': 100},
    'adv_tapeB_consolidated_mnsh':    {'col': 'adv_tapeB_consolidated_mnsh',    'zh': 'Tape B 全市场',        'unit': 'mn shares/day', 'fmt': 'f0c'},
    'adv_nyse_tapeB_matched_mnsh':    {'col': 'adv_nyse_tapeB_matched_mnsh',    'zh': 'Tape B · NYSE matched', 'unit': 'mn shares/day', 'fmt': 'f0c'},
    'adv_nyse_tapeB_handled_mnsh':    {'col': 'adv_nyse_tapeB_handled_mnsh',    'zh': 'Tape B · NYSE handled', 'unit': 'mn shares/day', 'fmt': 'f0c'},
    'share_nyse_tapeB_matched':       {'col': 'share_nyse_tapeB_matched',       'zh': 'Tape B 份额',          'unit': '%', 'fmt': 'pct1', 'scale': 100},
    'adv_tapeC_consolidated_mnsh':    {'col': 'adv_tapeC_consolidated_mnsh',    'zh': 'Tape C 全市场',        'unit': 'mn shares/day', 'fmt': 'f0c'},
    'adv_nyse_tapeC_matched_mnsh':    {'col': 'adv_nyse_tapeC_matched_mnsh',    'zh': 'Tape C · NYSE matched', 'unit': 'mn shares/day', 'fmt': 'f0c'},
    'adv_nyse_tapeC_handled_mnsh':    {'col': 'adv_nyse_tapeC_handled_mnsh',    'zh': 'Tape C · NYSE handled', 'unit': 'mn shares/day', 'fmt': 'f0c'},
    'share_nyse_tapeC_matched':       {'col': 'share_nyse_tapeC_matched',       'zh': 'Tape C 份额',          'unit': '%', 'fmt': 'pct1', 'scale': 100},

    # ── CDS：ICE Clear Credit 当月清算名义**总额，不是日均**（表标题里没有 daily）。
    #    2013-01 才起步，比其余列晚两年 —— 全表唯一一处有缺值的地方，
    #    这也是 load() 必须逐列 `to_numeric(errors='coerce')`、不许 `astype(float)` 的原因。
    'cds_total_notional_usdbn':     {'col': 'cds_total_notional_usdbn',     'zh': '合计',     'unit': 'USD bn/month', 'fmt': 'f0c'},
    'cds_client_notional_usdbn':    {'col': 'cds_client_notional_usdbn',    'zh': '客户盘',   'unit': 'USD bn/month', 'fmt': 'f0c'},
    'cds_nonclient_notional_usdbn': {'col': 'cds_nonclient_notional_usdbn', 'zh': '非客户盘', 'unit': 'USD bn/month', 'fmt': 'f0c'},
}

# ── COL 的构建期自检（三道，都是「改了不报错」的那一类事故）──────────────────
# ① 字典 key 必须 == 它自己的 'col'。这张表全页靠 `COL['x']` 取用，
#    key 与 col 一旦分叉，取到的是另一列的量纲，而画出来的图完全合理。
_col_key_bad = [k for k, c in COL.items() if k != c['col']]

if _col_key_bad:
    raise SystemExit(f'COL 的 key 与 col 对不上：{_col_key_bad}')

# ② unit 白名单。判据的三级里第 ③ 级完全靠 unit（single.py:223-232），
#    写一个白名单外的串不会报错，只会静默换掉次轴单位。
_unit_bad = sorted({c['unit'] for c in COL.values()} - _UNIT_WHITELIST)

if _unit_bad:
    raise SystemExit(f'COL 里出现了白名单外的 unit：{_unit_bad}；'
                     f'合法值只有 {sorted(_UNIT_WHITELIST)}，逐字来自 build/specs/ice.py')

# ③ **承重样本现验**：拿 single.py 的判据跑五条代表列，对上就放行、对不上当场停机。
#    这五条各代表一类：钱比率 / 每百股 / 百分点比率 / 存量假阳性 / 纯量。
#    这不是「测试」，是闸门 —— 上游 single.py 哪天改了判据，本页四张图的次轴单位
#    会在无人察觉的情况下翻掉，而 payload 照样写得出来。
_UNIT_LOAD_BEARING = {
    'rpc_energy_usd':                (True,  True,  'USD/contract, y/y 差（单月）'),
    'rpc_nyse_us_cash_usd_per100sh': (True,  True,  'USD/100 shares, y/y 差（单月）'),
    'share_nyse_tapeA_matched':      (True,  False, 'pp y/y（单月）'),
    'oi_rates_kcontracts':           (False, False, '% y/y（单月）'),
    'adv_energy_kcontracts':         (False, False, '% y/y（单月）'),
}

_lb_bad = []

for _k, _want in _UNIT_LOAD_BEARING.items():
    _c = COL[_k]
    _got = (SG.col_is_ratio(_c), SG.col_is_money_ratio(_c), SG.rhs_ylab2(_c, mom=True))
    if _got != _want:
        _lb_bad.append((_k, _want, _got))

if _lb_bad:
    raise SystemExit(
        f'口径判据与基线不符（COL 的 unit 被改写，或上游 build/single.py 改了判据）：'
        f'{_lb_bad}。基线是实测的，不是猜的；改 unit 之前先读本文件 COL 上方那段。')

# ══════════════════════════ 格式化层 ══════════════════════════
MONTHS = ('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
          'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec')

def mlab(p):
    """与 gsx.mlab / cme.mlab 一致：Period('2026-07') → 'Jul-26'。

    显式查表而不用 `p.strftime('%b-%y')`：strftime 的 %b 吃 locale，
    构建机上一旦 LC_TIME 不是 C，横轴会变成本地化月名（cme.py:190-192 同）。
    """
    return f'{MONTHS[p.month - 1]}-{p.year % 100:02d}'

def qlab(q):
    """季度 Period → '2026-Q2'（抄 cme.py:197-202，连理由一起）。

    pandas 的 `str(Period)` 给的是 '2026Q2'，与 series/fee_rates.csv 的 period
    写法差一个连字符。本页的季度收入块（隐含收入 / 对账 / 结构 / 分解 / 页中表）
    满篇都在报季度号，读者要能拿着这个号回 CSV 里直接 grep，所以统一成带连字符的写法。
    """
    return f'{q.year}-Q{q.quarter}'

def nz(v, dec):
    """消掉负零（抄 build/cboe.py:136 的语义）。

    `round(-0.04, 1)` 是 -0.0，f-string 会照实印成「-0.0」——读者看到的是一个
    不存在的负数（复查在 exchanges 热力矩阵与 tsm 上都抓到过）。
    ⚠️ 语义是**只归零、不舍入**：舍入后等于 0 才把符号去掉，否则返回**原值**，
    让调用方的 f-string 自己去舍入。写成 `return round(v, dec)` 会在中间环节
    提前截断精度，与 cboe 那边分叉。
    """
    if v is None or not np.isfinite(v):
        return v
    r = round(float(v), dec)
    return 0.0 if r == 0 else float(v)

def num(v, dec=0):
    """表格数值：缺失印全角破折号（抄 cme.py:205-208）。

    与下面的 `comma()` 的**唯一**区别是缺失时的落笔：表格里的空格子必须看得出
    「这一格没有数」，所以是 '—'；图注句子里的缺失只能整句不写，所以是 ''。
    两个都留是因为本页两种场合都有（页中表 Ex9 + 大量图注）。
    """
    if v is None or not np.isfinite(v):
        return '—'
    return f'{nz(v, dec):,.{dec}f}'

def comma(v, dec=0, money=''):
    """千分位 + 固定小数位 + 货币前缀（抄 cboe.py:139-143）。

    `money` 这个参数在本页是必需的：ICE 同页要印 `$930.4mn`（隐含收入）与
    `USD bn`（CDS 名义额）两种钱，而 CDS 那种的记号跟在数**后面**。
    ⇒ 前缀走 money=，后缀由调用方自己拼，别在这里加 suffix 参数（加了就会
    出现「$ … bn」这种两头都挂记号的写法）。
    """
    if v is None or not np.isfinite(v):
        return ''
    return f'{money}{nz(v, dec):,.{dec}f}'

def pctf(x, dec=0):
    """百分比变化，**入参是比值**（0.123 → '+12%'）。抄 cboe.py:150-155。

    ⚠️ 全文只许留这一种入参约定。cme.py:218 的 `pct()` 入参相反（已经是百分数），
    两种约定同页共存过一次，结果是同一个同比在两处差 100 倍且两处都印得出来。
    本页因此**没有** `pct()` 这个名字 —— 想印百分数差的，走 SG.chg_txt / SG.ratio_diff_txt。
    """
    if x is None or not np.isfinite(x):
        return ''
    return f'{nz(x * 100, dec):+.{dec}f}%'

def pp(x):
    """自适应位数的百分比（抄 cboe.py:158-163 / gsx._pp）：小变化 1 位，大变化 0 位。

    ⚠️ **名字是历史包袱，它印的是 `%` 不是 `pp`。** 入参同样是比值。
    「小变化给 1 位」是为了别把 +0.4% 印成 +0%（读者会当成没变）。
    真正的**百分点差**（份额三条 Tape、NYSE 份额）不走这里 ——
    那是口径判定，一律 `SG.ratio_diff_txt()` / `SG.chg_txt()`，
    本页一处自写的比率判据都没有（理由见 build/pctile.py 模块头）。
    """
    if x is None or not np.isfinite(x):
        return ''
    v = x * 100
    return f'{nz(v, 1):+.1f}%' if abs(v) < 2 else f'{nz(v, 0):+.0f}%'

def L(a):
    """序列 → JSON 安全的 float 列表（逐字抄 cme.py:232 / cboe.py:168，两页实现相同）。

    非有限值一律写 None：payload_guard 拒收 NaN/Infinity（CONTRACT §5.5），
    而 JSON 里的 null 到了 charts.js 就是断点／表格里的「—」，正是想要的效果。
    round(…, 6) 是为了幂等：同一份 CSV 重复跑，输出逐字节相同。
    """
    return [None if (v is None or not np.isfinite(float(v))) else round(float(v), 6)
            for v in a]

# ══════════════════════════ 读数据 ══════════════════════════
def load():
    """series/ice.csv → DataFrame（PeriodIndex('M')，已排序、已转数）。

    本页**唯一**的读盘口。四道结构性校验都在这里响，一道都不许挪到调用方：
    校验散到调用方，就会出现「某一张图自己检查过了、别的图没有」的局面。
    """
    if not os.path.exists(CSV):
        raise SystemExit(f'找不到数据文件: {CSV}')
    df = pd.read_csv(CSV)
    if 'month' not in df.columns:
        raise SystemExit(f'{CSV} 没有 month 列')
    df['month'] = pd.PeriodIndex(df['month'], freq='M')
    df = df.set_index('month').sort_index()

    # ── ① 逐列 to_numeric(errors='coerce')。**不许用 cme.py:257 的 astype(float)** ──
    # ICE 的 CDS 三列 2013-01 才起步，前 24 个月在 CSV 里是空串；
    # `astype(float)` 遇到空串是 ValueError，整页当场炸 —— 而这不是错误，
    # 是这三列真实的起始日。coerce 把它们变成 NaN，L() 再变成 null，
    # 图上就是一段空白，正是应该呈现的样子。（cboe.py:350-351 同样的处理、同样的理由。）
    for c in df.columns:
        df[c] = pd.to_numeric(df[c], errors='coerce')

    # ── ② 必需列存在性 ──
    # 判据是 COL 的全部 key + 三条交易日列 = ICE 全表 55 个数据列。
    # 不写一份手抄的 `need` 清单：手抄清单与 COL 会分叉，而分叉的表现是
    # 「某一列悄悄消失，只有用到它的那张图变成空图」，不是停机。
    need = list(COL) + list(TRADING_DAYS)
    missing = [c for c in need if c not in df.columns]
    if missing:
        raise SystemExit(f'series/ice.csv 缺列: {missing}')
    # 反向：CSV 里有而 COL / TRADING_DAYS 都不认的列。这不是错误（上游可能新增了
    # 一列），但必须让人看见 —— 静默忽略等于新列永远上不了页面。
    extra = [c for c in df.columns if c not in set(need)]
    if extra:
        print(f'⚠️ series/ice.csv 有 {len(extra)} 列不在 COL 里，本页不会画它们：{extra}')

    # ── ③ 月份逐月连续（抄 cme.py:247-251 的 set(gaps) != {1}）──
    # 断月会让时序窗口、同比 lag、季度分桶**同时**错位，而且三者都不会报错：
    # 少一个月，「12 期之前」指的就是 13 个月前，同比全页整体偏移一格。
    if len(df) < 2:
        raise SystemExit(f'series/ice.csv 只有 {len(df)} 行，画不出任何时序图')
    gaps = [(df.index[i] - df.index[i - 1]).n for i in range(1, len(df))]
    if set(gaps) != {1}:
        bad = [f'{df.index[i - 1]}→{df.index[i]}' for i in range(1, len(df))
               if (df.index[i] - df.index[i - 1]).n != 1]
        raise SystemExit(f'series/ice.csv 月份不连续，断在 {bad}')

    # ── ④ 缺值形态：允许**前导**缺失（新列晚起步），不允许**中间**缺洞 ──
    # 本页没有一列可以做全列非空校验（CDS 三列前 24 个月本来就是空的），
    # 但「中间缺一格」是另一回事：Ex18 的堆叠柱、Ex12 的堆叠 OI 一旦中间断格，
    # 段与段会各断各的，图上看着像是某一段真的归零了。
    # 全列皆空则是抓取坏了（列在、数没了），必须停机而不是画一张空图。
    holes, dead = [], []
    for c in need:
        ok = df[c].notna().values
        if not ok.any():
            dead.append(c)
            continue
        i0, i1 = int(ok.argmax()), len(ok) - 1 - int(ok[::-1].argmax())
        n_hole = int((~ok[i0:i1 + 1]).sum())
        if n_hole:
            holes.append((c, n_hole, str(df.index[i0]), str(df.index[i1])))
    if dead:
        raise SystemExit(f'series/ice.csv 这些列整列为空，抓取多半坏了：{dead}')
    if holes:
        raise SystemExit(f'series/ice.csv 这些列中间有缺洞（前导缺失是允许的，中间不行）：{holes}')

    return df

#: 各列的有效区间 —— `{列名: (首个非空月, 末个非空月, 非空期数)}`。
#: 由 load() 的第 ④ 道顺手落下来，给图注写「本列自 2013-01 起」这类句子用：
#: **不许把起始月写成字面量**（CDS 的 2013-01 是数据事实，但它是从数据里读出来的，
#: 不是背下来的；上游哪天回补到 2012，写死的那句就变成假话）。
def col_span(df):
    out = {}
    for c in df.columns:
        ok = df[c].notna().values
        if not ok.any():
            continue
        i0, i1 = int(ok.argmax()), len(ok) - 1 - int(ok[::-1].argmax())
        out[c] = (df.index[i0], df.index[i1], int(ok.sum()))
    return out

df = load()

SPAN = col_span(df)

ALL = list(df.index)

LATEST = ALL[-1]          # 数据最新月

CUR = LATEST              # 汇总表 / 抬头的「本月」。ICE 全表同一个 xlsx、同一天发布、

                          # RPC **不滞后**（与 Cboe 相反）⇒ 没有第二个「最新月」的概念。
PRV = ALL[-2]

YAG = ALL[-13] if len(ALL) >= 13 else None

#: 月度图窗的左端。与 build/single.py 的 WIN_FROM、build/cme.py:181、
#: build/cboe.py:52 同一个口径同一个理由：数据回补到 2016 而窗口停在近两年，
#: 等于回补给谁看。序列比它短就用序列自己的起点（只往右让、不往左借）。
WIN_FROM = '2016-01'

#: **末尾核对表**的行数 —— 这是**表**的窗口，不是任何一张图的窗口。
#: ⚠️ 这个常量**只**给核对表用。build/cboe.py:55-60 记着翻车经过：
#: 那边曾经让一张图的图注也吃这个常量去说「原 deck 的窗口有多长」，
#: 于是核对表行数一改，那张图就跟着宣称一个历史事实变了，同页两句当场打架。
#: 本页任何一张图、任何一句图注都不许读它。
WIN_TABLE = 13

# ── 窗口 1：月度图窗 W25 / XL25 ──────────────────────────────────────────
# 服务：Ex2 Ex3 Ex4 Ex10 Ex12 Ex13 Ex14 Ex15 Ex16 Ex17 Ex18（全部月度图）。
# 名字里的「25」是从 cme.py:424 / cboe.py:983 沿用的**历史名**（旧窗口是近 25 个月），
# 三个文件读起来一致比名字好听重要；真实长度一律读 WIN_LINE，不读名字。
_I0 = next((i for i, p in enumerate(ALL)
            if f'{p.year}-{p.month:02d}' >= WIN_FROM), 0)

W25 = ALL[_I0:]

WIN_LINE = len(W25)           # 图注里那句「N 个月」跟着它走，不写字面量

XL25 = [mlab(p) for p in W25]

# ── 窗口 2：全历史 XL_LONG ───────────────────────────────────────────────
# 服务：需要看满 2011-01 起全貌的图，以及页尾「本页序列覆盖多长」那句。
# ⚠️ Ex11（热力矩阵，近 24 个月）**不吃这个窗口**，也不吃 W25 —— 它自带一个
# 「近 N 个月」的短窗，横轴是 cols 不是 xlabels。它的窗口由画它那一段自己定，
# 这里不替它准备，免得又出现「一个窗口被三张图借用、改一处炸两处」。
XL_LONG = [mlab(p) for p in ALL]

# ── 窗口 3：核对表 W_TBL / XL_TBL ────────────────────────────────────────
# 服务：**只有** Ex19 末尾核对表。表是拿着它和公司披露逐行对的，
# 全序列 188 行没人对得完，所以它停在 WIN_TABLE 行。
W_TBL = ALL[-WIN_TABLE:]

XL_TBL = [mlab(p) for p in W_TBL]

# ── 窗口 4：季度收入块 ───────────────────────────────────────────────────
# 服务：Ex5（隐含收入柱）、Ex6（对账）、Ex7（收入结构）、Ex8（量价 bridge）、
#       Ex9（近 8 个完整季页中表）—— 这五张连成整块，块内不插月度图。
#
# 为什么隐含收入**只能按季度**：ICE 的 rpc_* 是滚动三月均，季末月那一格的窗口
# 恰好覆盖该季度 ⇒ 季度收入 = Σ(季内 3 个月 ADV × 该腿的交易日) × **季末月**的 RPC。
# 拿单月量乘滚动三月均费率当单月收入是错的（specs/ice.py 的 RPC 那一组写了）。
#
# Q_FROM 是**换算**得到的，不写字面量 '2016Q1'（照 cme.py:426-428 / cboe.py:986-988）：
# WIN_FROM 哪天再动，季度图跟着一起动；写死就会出现月度图挪了、季度图没挪。
Q_FROM = pd.Period(WIN_FROM, freq='M').asfreq('Q')

#: 「完整季」= 该季度的 3 个月在 df.index 里一个不缺。
#: 2026Q3 只有 7、8 两个月（CSV 到 2026-08）⇒ **不完整，不画**，
#: 也**不用 partial_months** —— 未装满的桶回答的是「到目前为止 vs 去年同期」，
#: 与完整桶不可比（cboe.py:965-970 那条口径说明的同一件事）。
_qcnt = pd.Series(1, index=pd.PeriodIndex(ALL, freq='M')).groupby(
    pd.PeriodIndex(ALL, freq='M').asfreq('Q')).sum()

QALL = [q for q, n in _qcnt.items() if n == 3]        # 全历史完整季（收入构造 / 对账用）

QW = [q for q in QALL if q >= Q_FROM]                 # 季度块五张图的横轴

XLQ = [qlab(q) for q in QW]

#: 季度轴也要「不许缺季」：中间缺一季，柱与柱之间会静默并拢，
#: 读者读到的是一条连续的季度序列，而它其实跳过了一季（cme.py:1731-1733 同款闸门）。
_qgap = [str(QW[i]) for i in range(1, len(QW)) if (QW[i] - QW[i - 1]).n != 1]

if _qgap:
    raise SystemExit(f'季度收入块：{qlab(Q_FROM)} 起不许缺季，断在 {_qgap}')

if not QW:
    raise SystemExit(f'季度收入块：{qlab(Q_FROM)} 起一个完整季都没有')

def col(name, win):
    """取一列在给定窗口上的值（float ndarray）。

    走 `reindex(win)` 而不是 cme.py 那种「取末 N 个」的尾部计数（抄 cboe.py:1085-1086）：
    reindex 是**按标签**对齐，窗口里若出现 df 没有的月份，拿到的是 NaN（画成断点），
    而尾部计数会**静默错位**——切片长度对得上，只是每一格都是隔壁月份的数。
    """
    if name not in df.columns:
        raise SystemExit(f'col(): series/ice.csv 没有列 {name}')
    return df[name].reindex(pd.PeriodIndex(win, freq='M')).values.astype(float)

def qcol(name, qwin, how='sum'):
    """把一条月度列按季度聚合到 qwin 上。收入块的量腿用它。

    ⚠️ `how='sum'` 只对**已经乘过交易日的当月合计**有意义。
    ADV 是日均，直接按季求和等于「三个月日均之和」，那不是任何一个量；
    ICE 更有**三套**交易日（commod / rates / us_equities），各条 ADV 各归一各的
    ⇒ 调用方必须先自己乘对交易日列，再送进来。这里不替它选交易日，
    因为选错哪一套是本页最容易翻车的一处（金融四条腿全部用 trading_days_rates，
    工作表行名 "COMMODITIES & OTHER FINANCIALS" 是陷阱）。
    `how='last'` 取季内最后一个月的值 —— RPC 那一侧走这条（季末月的滚动三月均）。
    """
    s = df[name]
    g = s.groupby(pd.PeriodIndex(s.index, freq='M').asfreq('Q'))
    agg = g.sum(min_count=3) if how == 'sum' else g.last()
    return agg.reindex(pd.PeriodIndex(qwin, freq='Q')).values.astype(float)

# ==========================================================================
# 【colmeta】
# ==========================================================================

# -*- coding: utf-8 -*-
"""build/ice.py 的【COL 列元数据表 + 口径层】—— 本文件是这一段的独立可跑版本。

合并进 build/ice.py 时：删掉文件底部的 `if __name__ == '__main__':` 自测块，
以及下面 import 段里那三行标着「⚠️ 自测垫片」的路径改写；其余逐行原样搬。

━━ 这一段为什么是全文件最承重的一段 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
手写页没有 `build/single.py` 那套「读 spec → 推 unit → 推口径」的自动流水线，
于是「这一列的同比是百分数、百分点、还是美元差」这件事在手写页里**没有主人**。
本段就是那个主人：

  ① `COL` 保留**与引擎完全同形的列字典**（键集 ⊆ `SG.COL_KEYS`），
     `zh` / `unit` / `fmt` 逐字抄自 `build/specs/ice.py` 的 `headline` / `groups`
     （那里已经对着官方表头逐字核过，重新措辞等于凭空造一个第二权威）；
  ② 判据一律转发 `SG.col_is_ratio` / `SG.col_is_money_ratio` / `SG.rhs_ylab2` /
     `SG.money_diff_txt` / `SG.ratio_diff_txt` / `SG.chg_txt`，本文件**一行判据都不自己写**
     —— `build/pctile.py` 模块头记着这条教训：各页各写各的，正是同一条序列
     在两页被判定相反的根因；
  ③ `COL_EXPECT` 是**手写的真源**：每一列「应该」被判成什么，import 期逐条对
     `SG` 的实际判定，不符停机。它替代的是引擎那一族 A1/A2/A10 护栏 ——
     手写页把护栏一起丢了，就等于把 ② 的转发变成一句无人复核的自觉。

⚠️ **`unit` 字符串是承重的，不是注释。** 它是 `SG.col_is_ratio()` 第 ③ 级判据的一票
（`single.py:235`：`classify(col) == RATIO and unit_is_ratio(unit)`），改一个字就会让
判定翻掉**且不报错**。本页最刺眼的一处是 `oi_rates_kcontracts`：列名里有 `rates`，
`yoy.classify()` 因此判它 `RATIO`（`yoy.py:159` 的 `_RATIO_PAT` 收 `rate|rates`），
而它是月末净未平仓、是**存量**；挡住这个假阳性的**只有** unit —— `k contracts`
不是比率量纲（`single.py:157` 的 `_RATIO_UNIT_DENOM` 要求 `/` 或 ` per ` 后面跟一个
可数活动单位）。把它的 unit 写成 `%` 或 `k contracts/contract`，它的次轴当场从
`% y/y` 翻成 `pp y/y`，页面照印不误。下面 `_UNIT_LOAD_BEARING__colmeta` 那道闸门就是
**把这件事变成会响的**：它现场把 unit 换掉、验判定确实翻，翻不掉说明「靠 unit 挡住」
这句话已经不成立（比如 classify 的正则改了），停机。
"""

HERE__colmeta = os.path.join(ROOT, 'build')

sys.path.insert(0, HERE__colmeta)

MONTHS__colmeta = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
          'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

def qlab__colmeta(q):
    """季度 Period → '2026-Q2'（照 cme.py:197）。

    pandas 的 `str(Period)` 给 '2026Q2'，少一个连字符；图注要让读者拿着这个季度号
    直接回 CSV / 官方 Key Metrics 里 grep，所以统一成带连字符的写法。
    """
    return f'{q.year}-Q{q.quarter}'

def num__colmeta(v, dec=0):
    """缺值印「—」。表格与图注里的空格子必须看得出是空的，不能印成 0。"""
    if v is None or not np.isfinite(v):
        return '—'
    return f'{nz(v, dec):,.{dec}f}'

#: 合法 unit 白名单。**只有这七串** —— 见文件抬头：unit 是判据的一票，不是注释。
#: 新增一列而它的量纲不在这里，说明要么抄错了，要么真的多了一种量纲；
#: 后者必须先在 build/specs/ice.py 里对着官方表头定名，再同步过来，
#: 不许在手写页里就地发明一个（发明出来的那一串没有任何东西核过）。
UNITS_OK = frozenset({
    'k contracts/day', 'k contracts', 'USD/contract', 'USD/100 shares',
    'mn shares/day', 'USD bn/month', '%',
})

#: 三条交易日列**故意不进 COL**。
#: 它们在 build/specs/ice.py 的 groups 里没有登记（那份 spec 只把它们当算 ADV 的除数，
#: 从不上页面），因此拿不到「逐字抄自 spec」的 zh / unit / fmt，而 `UNITS_OK` 里也没有
#: 「天」这个量纲。凭空造一个 unit 就是在手写页里发明一个无人核过的第二权威 ——
#: 正是本段存在要防的那件事。末尾核对表若要收这三列，先在 spec 侧定名。
#: ⚠️ 顺带记一句：`trading_days_rates` 的列名里也有 `rates`，`yoy.classify()` 同样
#:   判它 RATIO —— 它要是哪天进了 COL，会是第二个假阳性，必须一并进 COL_EXPECT。
TRADING_DAY_COLS = ('trading_days_commod', 'trading_days_rates', 'trading_days_us_equities')

#: 三套交易日各归一各的 ADV（fetch/ice.py 与 10-K FY2025 合约数双向证伪过的配对）。
#: 放在本段是因为它是**列的属性**（这一列的日均是拿哪一列除出来的），不是收入段的私产；
#: 收入段与 bridge 段都读它，两处各写一份必然分叉。
#: ⚠️ 工作表行名 "COMMODITIES & OTHER FINANCIALS" 是陷阱：**金融四条腿全部用
#:   trading_days_rates**。
#: ⚠️ 总 ADV（adv_futures_options_kcontracts）**故意不在表里**：它横跨商品与金融两侧，
#:   没有哪一套日历能代表它 ⇒ 不许把总 ADV 乘回成当月合计。查不到就是答案。
DAYCOL = {
    'adv_energy_kcontracts': 'trading_days_commod',
    'adv_ag_metals_kcontracts': 'trading_days_commod',
    'adv_commodities_kcontracts': 'trading_days_commod',
    'adv_brent_kcontracts': 'trading_days_commod',
    'adv_gasoil_kcontracts': 'trading_days_commod',
    'adv_otheroil_kcontracts': 'trading_days_commod',
    'adv_natgas_kcontracts': 'trading_days_commod',
    'adv_power_kcontracts': 'trading_days_commod',
    'adv_environmentals_kcontracts': 'trading_days_commod',
    'adv_sugar_kcontracts': 'trading_days_commod',
    'adv_otherags_metals_kcontracts': 'trading_days_commod',
    'adv_stir_kcontracts': 'trading_days_rates',
    'adv_mltir_kcontracts': 'trading_days_rates',
    'adv_equity_index_kcontracts': 'trading_days_rates',
    'adv_fx_credit_kcontracts': 'trading_days_rates',
    'adv_financials_kcontracts': 'trading_days_rates',
    'adv_single_stock_kcontracts': 'trading_days_rates',
    'adv_nyse_equity_options_kcontracts': 'trading_days_us_equities',
    'adv_us_equity_options_industry_kcontracts': 'trading_days_us_equities',
    'adv_nyse_us_cash_handled_mnsh': 'trading_days_us_equities',
}

# ══════════════════════════════════════════════════════════════════════════════
#          COL_EXPECT —— 手写的断言表：每一列「应该」被判成什么
# ══════════════════════════════════════════════════════════════════════════════
# 值 = (ratio, money_ratio, stock, classify)：
#   ratio       `SG.col_is_ratio(c)`         —— 同比走百分点差 / 钱的差，还是百分比变化
#   money_ratio `SG.col_is_money_ratio(c)`   —— 这个差的单位是钱还是百分点
#   stock       `bool(c.get('stock'))`       —— 同比是点对点（存量），不做滚动合计
#   classify    `YOY.classify(col)`          —— 只按**列名词根**猜的默认建议
#
# 为什么把 classify 也写进来：它是本表最有用的一列。`classify` 与最终判定**不一致**
# 的那几行，正是「unit 在承重」的现场 —— 一眼就能看见 `oi_rates_kcontracts` 被
# classify 判成 ratio、而最终 ratio=False。不列它的话，那一行看上去和别的存量行
# 一模一样，下一个人会以为它的 unit 可以随便改。
#
# 这张表是**手写的真源**，不是从 SG 反推出来的快照 —— 反推出来的表恒等于被检查的对象，
# 什么都检查不出来（`tools/check_yoy_caliber.py` 抬头那条硬规矩：不许拿被检查的对象
# 当证据）。所以它必须一条一条看着 spec 与官方口径填。
_R, _M, _S = True, True, True      # 只为下面那张表读起来短一点

COL_EXPECT = {
    # col                                          ratio  money  stock  classify
    # ── 流量：ADV（k contracts/day）。classify 走 `adv` 词根 → FLOW ────────────
    'adv_futures_options_kcontracts':             (False, False, False, YOY.FLOW),
    'adv_energy_kcontracts':                      (False, False, False, YOY.FLOW),
    'adv_brent_kcontracts':                       (False, False, False, YOY.FLOW),
    'adv_gasoil_kcontracts':                      (False, False, False, YOY.FLOW),
    'adv_otheroil_kcontracts':                    (False, False, False, YOY.FLOW),
    'adv_natgas_kcontracts':                      (False, False, False, YOY.FLOW),
    'adv_power_kcontracts':                       (False, False, False, YOY.FLOW),
    'adv_environmentals_kcontracts':              (False, False, False, YOY.FLOW),
    'adv_ag_metals_kcontracts':                   (False, False, False, YOY.FLOW),
    'adv_sugar_kcontracts':                       (False, False, False, YOY.FLOW),
    'adv_otherags_metals_kcontracts':             (False, False, False, YOY.FLOW),
    'adv_commodities_kcontracts':                 (False, False, False, YOY.FLOW),
    'adv_financials_kcontracts':                  (False, False, False, YOY.FLOW),
    'adv_stir_kcontracts':                        (False, False, False, YOY.FLOW),
    'adv_mltir_kcontracts':                       (False, False, False, YOY.FLOW),
    'adv_equity_index_kcontracts':                (False, False, False, YOY.FLOW),
    'adv_fx_credit_kcontracts':                   (False, False, False, YOY.FLOW),
    # ⚠️ 列名里有 `single`，但 `_RATIO_PAT` 不收这个词，classify 照旧走 `adv` → FLOW。
    #    真正被 `single` 咬到的是**图的口径声明**（见下面 `_MOM_DECL_ICE` 那段）。
    'adv_single_stock_kcontracts':                (False, False, False, YOY.FLOW),
    # ── 流量：股数口径（mn shares/day）。分母是**时间**，所以 unit 不是比率量纲 ──
    'adv_nyse_us_cash_handled_mnsh':              (False, False, False, YOY.FLOW),
    'adv_tapeA_consolidated_mnsh':                (False, False, False, YOY.FLOW),
    'adv_nyse_tapeA_matched_mnsh':                (False, False, False, YOY.FLOW),
    'adv_nyse_tapeA_handled_mnsh':                (False, False, False, YOY.FLOW),
    'adv_tapeB_consolidated_mnsh':                (False, False, False, YOY.FLOW),
    'adv_nyse_tapeB_matched_mnsh':                (False, False, False, YOY.FLOW),
    'adv_nyse_tapeB_handled_mnsh':                (False, False, False, YOY.FLOW),
    'adv_tapeC_consolidated_mnsh':                (False, False, False, YOY.FLOW),
    'adv_nyse_tapeC_matched_mnsh':                (False, False, False, YOY.FLOW),
    'adv_nyse_tapeC_handled_mnsh':                (False, False, False, YOY.FLOW),
    'adv_nyse_equity_options_kcontracts':         (False, False, False, YOY.FLOW),
    'adv_us_equity_options_industry_kcontracts':  (False, False, False, YOY.FLOW),
    # ── 流量：CDS 清算名义额。classify 走 `notional` → FLOW；
    #    unit `USD bn/month` 的分母是**时间**，进不了比率量纲（single.py:150-156）──
    'cds_total_notional_usdbn':                   (False, False, False, YOY.FLOW),
    'cds_client_notional_usdbn':                  (False, False, False, YOY.FLOW),
    'cds_nonclient_notional_usdbn':               (False, False, False, YOY.FLOW),
    # ── 存量：月末净 OI。ratio 一律 False —— 存量的同比是点对点的**百分比变化** ──
    'oi_commodities_kcontracts':                  (False, False, _S,    YOY.STOCK),
    'oi_energy_kcontracts':                       (False, False, _S,    YOY.STOCK),
    'oi_ag_metals_kcontracts':                    (False, False, _S,    YOY.STOCK),
    'oi_financials_kcontracts':                   (False, False, _S,    YOY.STOCK),
    # ⚠️⚠️ **已知假阳性**：classify 判 RATIO（列名里的 `rates`），最终 ratio=False。
    #      两列不一致 = unit `k contracts` 正在承重。`_UNIT_LOAD_BEARING__colmeta` 焊住。
    'oi_rates_kcontracts':                        (False, False, _S,    YOY.RATIO),
    'oi_other_financials_kcontracts':             (False, False, _S,    YOY.STOCK),
    # ── 比率（分子是**钱**）：RPC 八列。同比差的单位是 USD/contract 或
    #    USD/100 shares，**不是 pp/bp**（single.py:180-190 记着那次全站错印）──────
    'rpc_commodities_usd':                        (_R,    _M,    False, YOY.RATIO),
    'rpc_energy_usd':                             (_R,    _M,    False, YOY.RATIO),
    'rpc_ag_metals_usd':                          (_R,    _M,    False, YOY.RATIO),
    'rpc_financials_usd':                         (_R,    _M,    False, YOY.RATIO),
    'rpc_rates_usd':                              (_R,    _M,    False, YOY.RATIO),
    'rpc_other_financials_usd':                   (_R,    _M,    False, YOY.RATIO),
    'rpc_nyse_equity_options_usd':                (_R,    _M,    False, YOY.RATIO),
    'rpc_nyse_us_cash_usd_per100sh':              (_R,    _M,    False, YOY.RATIO),
    # ── 比率（分子是**百分数**）：份额五列。同比差是**百分点**，unit 里的 `%`
    #    把它挡在 money_ratio 之外（single.py:208：有 % 的分子就是百分数）──────────
    'share_nyse_equity_options':                  (_R,    False, False, YOY.RATIO),
    'share_nyse_us_cash_matched':                 (_R,    False, False, YOY.RATIO),
    'share_nyse_tapeA_matched':                   (_R,    False, False, YOY.RATIO),
    'share_nyse_tapeB_matched':                   (_R,    False, False, YOY.RATIO),
    'share_nyse_tapeC_matched':                   (_R,    False, False, YOY.RATIO),
}

del _R, _M, _S

#: 「unit 在承重」这句话的**可执行版本**：{列: 换成这个 unit 之后 ratio 应当翻成 True}。
#: 只登记 `classify() == RATIO 而最终 ratio == False` 的那些列 —— 也就是全靠 unit
#: 挡住的假阳性。下面 `_unit_gate()` 现场把 unit 换掉、验判定确实翻；翻不掉说明
#: 「靠 unit 挡住」已经不成立（比如 classify 的正则改了、或者 col_is_ratio 的级序变了），
#: 那时候页面上那几条注释就是假话，必须停机而不是继续印。
_UNIT_LOAD_BEARING__colmeta = {
    'oi_rates_kcontracts': '%',
}

def _col_gate():
    """import 期护栏：COL 的形状、unit 白名单、与 CSV 表头的双向对账。

    三件事一起做，因为它们都是「表本身对不对」而不是「判定对不对」：
      ① 键 == entry['col']（错位过一次就再也发现不了：图会画出另一列的数据）；
      ② 键集 ⊆ SG.COL_KEYS 且 ⊇ SG.COL_REQUIRED —— 保证每条都能原样喂给 SG 的判据；
      ③ fmt ∈ SG.FMT_INFO（charts.js 对不认识的格式器**静默退回 f1**，
         所以这是硬校验不是提示，见 single.py:113）；unit ∈ UNITS_OK；
      ④ 与 series/ice.csv 的表头**双向**对账：COL ∪ 交易日列 必须恰好等于表头去掉
         month。少一列 = 官方新发了一列而本页没跟（静默漏掉一条序列）；
         多一列 = 抄了一个不存在的列名（图上会是一条空线，也不报错）。
    """
    for k, c in COL.items():
        if c.get('col') != k:
            raise SystemExit(f'COL 的键与 col 字段对不上：{k!r} vs {c.get("col")!r} —— '
                             f'错位之后图会画出另一列的数据，而且不报错。')
        extra = set(c) - SG.COL_KEYS
        if extra:
            raise SystemExit(f'COL[{k!r}] 有引擎不认识的键 {sorted(extra)}；'
                             f'合法键只有 {sorted(SG.COL_KEYS)} —— 本表保持与引擎同形，'
                             f'才能原样喂给 SG.col_is_ratio / rhs_ylab2 / chg_txt。')
        miss = SG.COL_REQUIRED - set(c)
        if miss:
            raise SystemExit(f'COL[{k!r}] 缺必填键 {sorted(miss)}。')
        if c['fmt'] not in SG.FMT_INFO:
            raise SystemExit(f'COL[{k!r}] 的 fmt {c["fmt"]!r} 不在 charts.js 的格式器表里 —— '
                             f'引擎对不认识的名字**静默退回 f1**，小数位会当场变错。')
        if c['unit'] not in UNITS_OK:
            raise SystemExit(f'COL[{k!r}] 的 unit {c["unit"]!r} 不在白名单里。unit 是 '
                             f'SG.col_is_ratio() 第 ③ 级判据的一票，不是注释；'
                             f'合法值只有 {sorted(UNITS_OK)}。真要新增量纲，'
                             f'先在 build/specs/ice.py 对着官方表头定名再同步过来。')
        # `scale` 只服务「CSV 存的是小数、页面按百分数显示」这一件事。份额五列的
        # CSV 值是 0.183 这种小数，×100 之后才是 18.3%。反过来，非 % 列配了 scale
        # 等于把一条序列悄悄放大 100 倍。
        if ('scale' in c) != (c['unit'] == '%'):
            raise SystemExit(f'COL[{k!r}]：scale 与 unit == "%" 必须同进同出'
                             f'（unit={c["unit"]!r}, scale={c.get("scale")!r}）。')
    if not os.path.exists(CSV):
        raise SystemExit(f'找不到数据文件: {CSV}')
    with open(CSV, encoding='utf-8') as fh:
        head = fh.readline().rstrip('\n').split(',')
    if head[0] != 'month':
        raise SystemExit(f'series/ice.csv 第一列应当是 month，实际是 {head[0]!r}。')
    csv_cols = set(head[1:])
    covered = set(COL) | set(TRADING_DAY_COLS)
    lost = sorted(csv_cols - covered)
    ghost = sorted(covered - csv_cols)
    if lost or ghost:
        raise SystemExit(
            f'COL 与 series/ice.csv 表头对不上 —— 表里有而本页没登记的：{lost}；'
            f'本页登记了而表里没有的：{ghost}。前者是官方新发了一列而页面静默漏掉，'
            f'后者是抄错了列名、图上会画出一条空线，两种都不报错，所以在这里响。')
    bad_day = sorted(set(DAYCOL.values()) - set(TRADING_DAY_COLS))
    if bad_day:
        raise SystemExit(f'DAYCOL 指到了不存在的交易日列：{bad_day}。')
    bad_src = sorted(set(DAYCOL) - set(COL))
    if bad_src:
        raise SystemExit(f'DAYCOL 给了不在 COL 里的列配交易日：{bad_src}。')
    if 'adv_futures_options_kcontracts' in DAYCOL:
        raise SystemExit(
            '总 ADV（adv_futures_options_kcontracts）不许配交易日：它横跨商品与金融两侧，'
            '没有哪一套日历能代表它，所以「乘回当月合计」这件事本页做不了。'
            '查不到就是答案，不要给它凑一个。')

def _caliber_gate():
    """import 期护栏：**逐条**核对 SG 的实际判定 == COL_EXPECT 的手写预期。

    这是本段存在的理由。手写页没有引擎那套自动推导，也就没有引擎那一族
    A1/A2/A10 护栏；这张表 + 这道闸门就是替代品。任何一条判定翻掉 ——
    改了 unit、改了 fmt、`yoy.classify()` 的正则动了、`col_is_ratio` 的级序动了 ——
    都会在这里当场停机，而不是在页面上静默印出一句假单位。
    """
    miss = sorted(set(COL) - set(COL_EXPECT))
    extra = sorted(set(COL_EXPECT) - set(COL))
    if miss or extra:
        raise SystemExit(f'COL 与 COL_EXPECT 不是同一批列 —— COL 有而预期表没有：{miss}；'
                         f'预期表有而 COL 没有：{extra}。一列一条，不许有例外：'
                         f'没进预期表的那一列，它的口径就没有人核过。')
    bad = []
    for k, c in COL.items():
        want = COL_EXPECT[k]
        got = (SG.col_is_ratio(c), SG.col_is_money_ratio(c),
               bool(c.get('stock')), YOY.classify(k))
        if got != want:
            bad.append((k, want, got))
    if bad:
        lines = '\n'.join(
            f'  {k}: 预期 ratio={w[0]} money={w[1]} stock={w[2]} classify={w[3]!r}；'
            f'实际 ratio={g[0]} money={g[1]} stock={g[2]} classify={g[3]!r}'
            for k, w, g in bad)
        raise SystemExit(
            '口径判定与 COL_EXPECT 对不上：\n' + lines +
            '\n这张表是手写的真源，不是从 SG 反推的快照 —— 对不上时**先查是不是判定翻了**'
            '（改 unit / 改 fmt / yoy.classify 的正则动了 / col_is_ratio 的级序动了），'
            '而不是顺手把预期改成实际。')

def _unit_gate():
    """import 期护栏：验「靠 unit 挡住假阳性」这句话**现在还成立**。

    做法是现场把 unit 换成一个比率量纲，看判定是否真的翻成 True。
    翻不掉 = 挡住它的其实不是 unit（比如 classify 不再判它 RATIO 了），
    那么 COL 里那几行 ⚠️ 注释、以及页面上讲这件事的话，全都变成了假话。
    这道闸门只验**方向**，一格数据都不动。
    """
    for k, u in _UNIT_LOAD_BEARING__colmeta.items():
        c = COL[k]
        if SG.col_is_ratio(c):
            raise SystemExit(f'{k} 现在被判成比率了 —— 它是存量（月末净 OI），'
                             f'不该走百分点差。先查 unit 是不是被改了。')
        probe = dict(c, unit=u)
        if not SG.col_is_ratio(probe):
            raise SystemExit(
                f'{k}：把 unit 从 {c["unit"]!r} 换成 {u!r} 之后判定**没有**翻成比率 —— '
                f'说明挡住这个假阳性的已经不是 unit 了（多半是 yoy.classify() 的 '
                f'_RATIO_PAT 或 single.col_is_ratio() 的级序动过）。'
                f'COL 里那条「靠 unit `k contracts` 挡住」的注释、以及页面上讲这件事的话，'
                f'现在都是假话，先改说法再重跑。')
    # 反向：真比率列的 unit 也在承重。把 RPC 的量纲换成一个非比率量纲，
    # 判定必须掉成 False —— 掉不下来说明 fmt 或别的什么在替它做主，
    # 那时候「RPC 靠 unit 认出来」这句同样不成立。
    probe = dict(COL['rpc_energy_usd'], unit='k contracts')
    if SG.col_is_ratio(probe):
        raise SystemExit('rpc_energy_usd 换成非比率量纲之后仍被判成比率 —— '
                         '「RPC 靠 classify + unit 两票认出来」这句话已经不成立。')

_col_gate()

_caliber_gate()

_unit_gate()

# ────────────────────── COL 的取用口（不许绕过去直接写字典）──────────────────────
def C(key):
    """取一条列元数据。存在性由这里保证 —— 手抖写错列名时当场 KeyError，

    而不是在下游变成一句 `c.get('unit')` 返回 None、判定静默掉成「非比率」。
    """
    try:
        return COL[key]
    except KeyError:
        raise SystemExit(f'COL 里没有 {key!r} —— 列名写错了，或者这一列还没登记。'
                         f'登记的有 {len(COL)} 条。') from None

def zh(key):
    """这一列的中文点名（逐字来自 spec）。图注 / 图例 / 表头一律走它，不许就地翻译。"""
    return C(key)['zh']

def unit(key):
    """这一列的单位串。**轴标题、核对表表头、money_diff_txt 印的必须是同一串字** ——
    翻译一次就多一处会漂的副本（single.py:690 那条注释讲的就是这件事）。"""
    return C(key)['unit']

def series_of(df, key):
    """取这一列的**展示口径**序列：`scale` 已经乘好。

    份额五列 CSV 里存的是 0.183 这种小数，页面按 18.3% 显示 —— 忘了 ×100 的后果是
    一条贴着 0 的直线，图能画出来、不报错。Ex13 / Ex16 / Ex17 三张都吃这条，
    所以取数只留这一个口子，不让调用点各乘各的。
    """
    c = C(key)
    s = pd.to_numeric(df[c['col']], errors='coerce')
    sc = c.get('scale')
    return s * sc if sc else s

def rhs_ylab2_col(key, mom=True):
    """次轴标题。转发 `SG.rhs_ylab2()`，但**存量列拒绝 mom=True**。

    理由：`mom=True` 会给标题缀上「（单月）」，而存量的同比是**两个时点**的点对点比，
    「单月同比」这个词对它是错的（存量根本没有第二种合法口径可选，
    `build/yoy.py` 对存量调滚动合计直接抛错）。存量图的标题要带的是
    「（存量，期末口径）」—— `tools/check_yoy_caliber.py` 的 `_STOCK_TXT`
    （tools/check_yoy_caliber.py:391）认的就是「存量 / 期末 / 月末 / 未平仓」那几个字。
    """
    c = C(key)
    if mom and c.get('stock'):
        raise SystemExit(
            f'{key} 是存量（月末净 OI），次轴标题不许缀「（单月）」—— '
            f'它比的是两个**时点**的持仓，不是两个**月份**的成交流量。'
            f'存量图的口径字样走标题里的「（存量，期末口径）」'
            f'（tools/check_yoy_caliber.py 的 _STOCK_TXT 认那几个字）。')
    return SG.rhs_ylab2(c, mom=mom)

def caliber_diff_win(s, win, kind=YOY.FLOW):
    """`yoy.caliber_diff` 的本页入口：**索引换成横轴标签、统计范围限定成图窗**。

    两件事都是 CONTRACT §6.4 点名的坑，所以在一个地方做完，调用点不许各写一遍：

    · **统计范围 = 这张图真画出来的那段窗口。** 图注里报的月份若落在图窗之外，
      读者在图上根本找不到。所以 `win` 是**必填的，不给默认值** —— 给了默认值
      （比如「全历史」）就等于把这个坑设成默认行为。
    · **索引先换成 `Jan-16` 这种横轴标签**，于是 `describe()` 点到的每一个月份
      都能在本图 x 轴上原样找到。

    真正的统计（样本对齐、相邻月跳变、符号相反的月份）一格都不在本文件里做，
    全部走 `build/yoy.py` 的 `caliber_diff` —— 那是全站唯一实现。样本对齐这一步
    尤其不能自己重写：滚动同比比单月同比少 12 个月历史，不取交集就会把
    「样本不同」读成「口径不同」。
    """
    s = pd.Series(s)
    s = s.set_axis([mlab(p) for p in s.index])
    return YOY.caliber_diff(s, kind, win=[mlab(p) for p in win])

def caliber_stats(s, win, kind=YOY.FLOW):
    """`caliber_diff_win` 的键名适配层（页尾口径条与汇总表注引用的字段名沿用旧写法）。

    `first` / `last` / `jump_m_at` 与 `opp` 的索引**已经是横轴标签**（`Dec-17` 这种），
    调用点不要再套一层 `mlab()`。
    """
    d = caliber_diff_win(s, win, kind)
    opp = pd.DataFrame([{'m': m, 'r': r} for _, m, r in d['opposite']],
                       index=[p for p, _, _ in d['opposite']])
    return {'n': d['n'], 'first': d['months'][0] if d['months'] else None,
            'last': d['months'][-1] if d['months'] else None,
            'sd_m': d['std_mom'], 'sd_r': d['std_ttm'],
            'jump_m': d['maxjump_mom'][0] if d['maxjump_mom'] else float('nan'),
            'jump_m_at': d['maxjump_mom'][2] if d['maxjump_mom'] else None,
            'jump_r': d['maxjump_ttm'][0] if d['maxjump_ttm'] else float('nan'),
            'n_opp': d['opposite_n'], 'opp': opp}

#: 逐图代价的最低样本量，照抄 `build/single.py` 的 `Page.MOM_COST_MIN`
#: （全站同一次改口径，门槛不该各定一个）。它比 `yoy.MIN_DIAG_MONTHS`（12）严一档：
#: 12 个月只够 caliber_diff 出一个数，24 个月才够让「符号相反的月份占 X%」不是样本噪声。
#: 不足这个数就照实说「量不出来」，**不许换一条别的序列顶上去凑格式**。
MOM_COST_MIN = 24

#: 逐图代价的账本：`{图号: [ {'label': 点名, 'd': caliber_diff 的结果}, … ]}`。
#: 值是 **list**（抄 cme.py:466）而不是 cboe 的单 dict：一张图可以画不止一条同比线
#: （本页 Ex11 热力矩阵、以及任何把同比画成主序列的折线），一条线的数说不了另一条。
#: 页尾口径条与下面三道闸门**现读**它，图号与条数一个都不写死。
COST_LOG = {}

def _cost_body(n, s_full, win, label, key=None):
    """算一条序列在一段窗口上的口径代价，并**记进账本**。返回 (账本条目, caliber_diff)。

    `label` 必填且不许是空串 —— 它是「这段数是**这张图**的」这件事在图注里唯一的
    落点，也是账本里区分同一张图两条线的唯一键。

    `key`（可选，但**建议每次都给**）是这条序列在 COL 里的列名。给了它才拦得住
    本段自测里当场发现的那个坑：本函数收的是一条**裸 Series**，看不出它是流量、
    比率还是存量，于是拿一条 RPC（比率）或一条 OI（存量）调它，会安安静静地按
    `YOY.FLOW` 算完、记进账本、印出一整段讲「12 个月滚动合计 vs 单月」的话 ——
    而这两类**根本没有滚动合计这一说**（`build/yoy.py` 对存量调滚动合计直接抛错，
    对比率也不比）。那段话每个字都通顺，每个数都是真算出来的，只是讲的不是这张图。
    本页有 8 条 RPC + 6 条 OI，占 COL 的四分之一强，撞上的概率不低。
    ⇒ 给了 key 就当场停机；比率列走 `SG.rhs_ylab2()` 那一档的文案，
      存量列走 `stock_cal_zh()`。
    """
    if key is not None:
        c = C(key)
        if SG.col_is_ratio(c):
            raise SystemExit(
                f'Exhibit {n}：{key} 是**比率**列（{c["unit"]}），不许走 yoy_cal_zh —— '
                f'它的同比是「{SG.rhs_ylab2(c, mom=True)}」这种差，不是百分比变化，'
                f'而且比率没有 12 个月滚动合计这一说，那段代价文案讲的是别的东西。')
        if c.get('stock'):
            raise SystemExit(
                f'Exhibit {n}：{key} 是**存量**列（月末快照），不许走 yoy_cal_zh 也'
                f'不许进 COST_LOG —— §6.1 第 3 条只管流量，存量图的口径段走 '
                f'stock_cal_zh()。进了账本会被 cost_gates() 当场认成 _COST_EXTRA。')
    if not isinstance(n, int):
        raise SystemExit(f'代价账本的图号必须是 EX_* 那种 int，收到 {n!r} —— '
                         f'契约里图号不许写字面量，也不许写成字符串。')
    if not label or not str(label).strip():
        raise SystemExit(
            f'Exhibit {n} 调 yoy_cal_zh / yoy_cal_lines_zh 时没有给 label。'
            f'点名是**必填**：CONTRACT §6.1 第 3 条要求代价用「这条序列自己」实测，'
            f'而读者判断这段数是不是这张图的，靠的就是这个点名。'
            f'（cme.py:530-537 / cboe.py:210-217 各记着一次翻车：页级常量让一张图印了'
            f'另一张图的数，页面上看不出来。）')
    d = caliber_diff_win(s_full, win, YOY.FLOW)
    row = {'label': str(label), 'd': d}
    COST_LOG.setdefault(n, []).append(row)
    return row, d

def _cost_stat_zh(label, d):
    """一条线的代价正文：不足样本就照实说量不出来，够就交给 `yoy.describe()`。

    §6.1 第 3 条要报的三样（逐月标准差、相邻月最大跳变**带月份**、符号相反的月份数）
    全在 `describe()` 里，本文件一个统计量都不自己算、也不自己排版。
    ⚠️ 样本不够时**不许**换一条别的序列的数顶上去凑格式 —— 「量不出来」本身就是
    一句该印给读者看的话。
    """
    if d['n'] < MOM_COST_MIN:
        return (f'<b>{label}</b>：代价量不出来 —— 本图窗口内两种口径都算得出的月份只有 '
                f'{d["n"]} 个（不足 {MOM_COST_MIN} 个，分母太小、报出来的比例是样本噪声'
                f'不是结构），此处不报差异；这本身也是一句该看见的提醒：'
                f'这条线的可比月很少，斜率不要外推。')
    return f'<b>{label}</b>：' + YOY.describe(d)

def yoy_cal_zh(n, s_full, win, label, key=None):
    """Exhibit n 的「口径 + 代价」图注段 —— 拿**这张图自己那条序列、自己那段窗口**实测。

    措辞照 `build/single.py` 的 `mom_cost_zh()`：口径抬头 → 窗口那一句 → `describe()`。
    `label` 必填、`key` 建议每次都给（两个必填 / 建议的理由见 `_cost_body`）。
    """
    _, d = _cost_body(n, s_full, win, label, key)
    xl = [mlab(p) for p in win]
    head = (f'<b>次轴 = <u>单月</u>同比</b>（当月 ÷ 去年同月 − 1），全站统一 —— '
            f'<b>页面所有者指定</b>（<code>build/CONTRACT.md</code> §6：全站同比只有这一种，'
            f'页面上一条 12 个月滚动合计同比都不画）。'
            f'好处只有一个，但是决定性的：<b>柱与线取自同一列</b> —— 拿这根柱除以 12 根柱'
            f'之前那根，就是线上这一点，读者可以自己核对。')
    tail = ('折线要等 12 个月才有第一个点（要有去年同月当分母）；'
            '本页序列自 2011-01 起、图窗自 '
            f'{xl[0]} 起，所以窗口最左边那一格就已经有值。')
    if d['n'] < MOM_COST_MIN:
        return (head +
                f'代价（§6.1 第 3 条）本该在这里用<b>本图这条序列（{label}）</b>自己实测，'
                f'但本图窗口 {xl[0]} 至 {xl[-1]}（{len(win)} 个月）内两种口径都算得出的'
                f'月份只有 {d["n"]} 个（不足 {MOM_COST_MIN} 个，分母太小、报出来的比例是'
                f'样本噪声不是结构），此处不报差异；这本身也是一句该看见的提醒：'
                f'这条线的可比月很少，斜率不要外推。' + tail)
    return (head +
            f'<b>代价（§6.1 第 3 条）用<u>本图这条序列</u>（{label}）自己实测</b>，'
            f'而且<b>只统计本图画出来的这段窗口</b> —— {xl[0]} 至 {xl[-1]}'
            f'（{len(win)} 个月）：图外的历史读者看不到，报出来对不上；'
            f'别的图那条线毛刺多大与这条线无关，各图的数各自印在各自图注里。'
            + YOY.describe(d) + tail)

def yoy_cal_lines_zh(n, items, win):
    """Exhibit n 的口径 + 代价段，用于**把同比画成主序列**的图（折线 / 热力矩阵）。

    与 `yoy_cal_zh()` 的区别只有两处：抬头说的是「这张图的线本身就是同比」，
    以及**一张图有几条线就报几条** —— §6.1 第 3 条要的是「这条序列自己」的实测，
    两条线共用一条线的数，与九张图共用一张图的数是同一个错。

    `items` = [(点名, 全历史序列)] 或 [(点名, 全历史序列, COL 列名)]，顺序即图注里的
    排列顺序。第三项给了就多一道「这条真是流量吗」的检查（理由见 `_cost_body`）。
    """
    if not items:
        raise SystemExit(f'Exhibit {n} 调 yoy_cal_lines_zh 却一条序列都没给。')
    items = [(t[0], t[1], t[2] if len(t) > 2 else None) for t in items]
    xl = [mlab(p) for p in win]
    ds = [_cost_body(n, s, win, lab, k)[1] for lab, s, k in items]
    head = (f'<b>本图画的 {len(items)} 条序列<u>本身</u>就是<u>单月</u>同比</b>'
            f'（当月 ÷ 去年同月 − 1，不是次轴、也不是 12 个月滚动合计）—— 全站统一，'
            f'<b>页面所有者指定</b>（<code>build/CONTRACT.md</code> §6）。'
            f'<b>代价（§6.1 第 3 条）逐条用<u>它自己</u>实测</b>，'
            f'统计范围就是本图画出来的这段窗口 —— {xl[0]} 至 {xl[-1]}'
            f'（{len(win)} 个月）：图外的历史读者看不到，报出来对不上。')
    return head + ''.join(_cost_stat_zh(t[0], d) for t, d in zip(items, ds))

def stock_cal_zh(items, win, ref_ex, ref_label, ref_stats):
    """**存量图**专用的口径段（照 cme.py:580 的 `STOCK_CAL`，但按 ICE 的形状重排）。

    与 cme 的差别有两处，都是被 ICE 的数据形状逼出来的：
      · cme 全页只有一张存量图、一条存量线，所以它把这段写成页级常量；
        本页那张月末未平仓画的是**四条叶子**（能源 / 农金 / 利率 / 股指FX），
        所以这里收 `items` 逐条报 —— 与 `yoy_cal_lines_zh` 同一个理由：
        一条线的毛刺说不了另一条。
      · 单位是 `k contracts`，与 series/cme.csv 的裸张数**差 1000 倍**
        （verify_ice §五.4），横截面并读时这一句必须在场。

    ⚠️ 这一段**不是**「代价」：存量根本没有第二种合法口径可拿来做对照
    （把 12 个月末的存量加起来不是任何东西 —— 既不是「一年的量」，
    也不是「平均水平」，`build/yoy.py` 对存量调滚动合计直接抛错），
    所以 §6.1 第 3 条那笔债这张图**不欠**，它给的是**与流量图的对比**。
    因此它也**不进** `COST_LOG` —— 进了就会让页尾那句「每一张画流量同比的图…」
    替一张存量图背书，而三道账本闸门会当场把它认成 `_COST_EXTRA`。

    `ref_ex` / `ref_label` / `ref_stats`：拿来做对比的那张**流量**图（图号、点名、
    `caliber_stats()` 的结果）—— 对比对象必须点名，否则读者不知道在跟谁比。
    """
    if not items:
        raise SystemExit('stock_cal_zh 至少要一条存量序列。')
    xl = [mlab(p) for p in win]
    rows = []
    for lab, s in items:
        d = caliber_diff_win(s, win, YOY.STOCK)     # ← kind=STOCK：不比滚动，只回点对点
        rows.append(f'<b>{lab}</b> 单月同比标准差 {d["std_mom"]:.1f}pp、'
                    f'相邻月最大跳变 {d["maxjump_mom"][0]:.0f}pp（{d["maxjump_mom"][2]}）')
    return (f'<b>本图读的是<u>存量</u>（月末净未平仓，期末口径）</b>，同比的算法与本页'
            f'其余各图完全相同（当月 ÷ 去年同月 − 1），但<b>读的东西不同</b>：'
            f'这里比的是两个<b>时点</b>的持仓，其余各图比的是两个<b>月份</b>的成交流量，'
            f'高低不要放在一起比。'
            f'另外这一张不存在「改不改口径」的选择：存量做不了 12 个月滚动合计 —— '
            f'把 12 个月末的存量加起来不是任何东西（存量不累积，也没除以 12），'
            f'<code>build/yoy.py</code> 对存量调滚动合计直接抛错。'
            f'存量也不吃日历效应（不像成交量要看当月有几个交易日），'
            f'所以这几条线本来就比成交量的同比稳 —— 都在<b>本图这段窗口</b>'
            f'（{xl[0]} 至 {xl[-1]}，{len(win)} 个月）上量：' + '；'.join(rows) +
            f'；而同窗口的{ref_label}（Exhibit {ref_ex} 那条线）是 '
            f'{ref_stats["sd_m"]:.1f}pp 与 {ref_stats["jump_m"]:.0f}pp。'
            f'（§6.1 第 3 条那笔「换口径的代价」这一张<b>不欠</b>：存量本来就走点对点，'
            f'没有第二种合法口径可拿来做对照，所以这里给的是<b>与流量图的对比</b>，'
            f'不是代价。）'
            f'⚠️ 单位是 <code>k contracts</code>（千张）—— 与 '
            f'<code>series/cme.csv</code> 的 <code>oi_*_contracts</code>（裸张数）'
            f'<b>差 1000 倍</b>，两页并读时先对单位再对数。'
            f'另外官方<b>没有 TOTAL OI 行</b>：新闻稿里的 "Total OI" 是 '
            f'commodities + financials 自己加出来的，本页不造这一列。')

# ══════════════════════════════════════════════════════════════════════════════
#            逐图代价的**双向**对账（抄 cme.py:1941-1955 与 cboe.py:2056-2091）
# ══════════════════════════════════════════════════════════════════════════════
# 两个方向都要查，cboe.py:2056-2091 那段注释明写 2026-09 才补齐 extra 那半，
# 「否则本页不会响本身就是坑」：
#   · 漏印（该印没印）→ 页尾那句「每一张…都印了」静默变假；
#   · 多印（账本里有、payload 里没有那张同比图）→ 页尾那段小结是**现读账本**生成的，
#     于是会替一张不存在、或已经不画单月同比的图背书，印出一行带图号带数字的代价，
#     而读者会照着那个图号去找。触发它不需要谁写错代码：把某张图的 ylab2 改掉、
#     或者图号整体位移一格，`_COST_DUE` 当场变小而 COST_LOG 还带着旧图号。
#
# ⚠️ **ICE 在这里必须偏离 cme 一处，而且是被数据逼的。**cme / cboe 认「声明了单月」
#   用的是裸词 `'single' in title.lower()`。本页有一列叫 `adv_single_stock_kcontracts`
#   （specs/ice.py:643「单股（已剔出合计）」），凡是标题或图例里出现 "single stock"
#   的图都会被裸词误收进 `_SINGLE_EX`，进而被要求印一段它根本不画的同比的代价。
#   所以本页认的是 `single[-\s]?month` —— 这与 `tools/check_yoy_caliber.py:374` 的
#   `_MOM_DECL`（`single[-\s]?month`）逐字同源，收严不收宽。
_MOM_DECL_ICE = re.compile(r'single[-\s]?month', re.I)

_ZH_MOM_DECL = re.compile(r'单月同比|单月口径|单月[的]?[y／/]')

def _ex_decl(e):
    """一张图**对外声明**的口径字面：标题 + 次轴标题 + 次轴序列名 + 各序列名。

    判据只看写进 payload 的字，不看作者记得改了几张（cme.py:1916）。
    序列名也收进来，是因为本页把同比画成主序列的图不止一种形状
    （热力矩阵、折线），它们没有 `yoy` 字段，口径只写在序列名或标题里 ——
    cme.py:2053 记着这个坑：`_COST_DUE` 只从 gs_bar 推导，非 gs_bar 的图画了流量
    单月同比，三道闸门一律看不见，页尾那句全称断言就会静默变假。
    """
    bits = [e.get('title') or '', e.get('ylab2') or '', e.get('legend') or '']
    y = e.get('yoy')
    if isinstance(y, dict):
        bits.append(y.get('name') or '')
    for k in ('series', 'lines', 'bars', 'stacks'):
        for s in (e.get(k) or []):
            if isinstance(s, dict):
                bits.append(s.get('name') or '')
    return ' '.join(bits)

def cost_gates(ex, stock_ex=(), why=None):
    """三道账本闸门 + 页尾小结正文。**在全部 exhibit 画完之后调**。

    参数
      ex        payload 里的 exhibit 列表（现读，不靠人脑枚举）
      stock_ex  读**存量**的图号集合。存量图不进 `_COST_DUE`（§6.1 第 3 条只管流量），
                它们的口径段走 `stock_cal_zh()`，也不进 COST_LOG。
      why       例外登记表 `{图号: 为什么不重复印}`。抄 cme.py:2064-2078：
                例外的**理由要原样印给读者**，漏登记就停机 —— 「唯一的例外是 X」
                这种句子在 cme 上错过一次（漏掉了热力矩阵，反例有两个而句子写着「唯一」）。

    返回 dict：due / exempt / rows_txt / exempt_txt / hi / lo，供页尾口径条与
    各图的导航句现读。
    """
    why = dict(why or {})
    stock_ex = set(stock_ex)

    single = sorted({e['n'] for e in ex if _MOM_DECL_ICE.search(_ex_decl(e))})
    # 用中文「单月」声明、却没被 ASCII 判据认出来的图：页尾那一档会漏掉它，
    # 而 tools/check_yoy_caliber.py 的 R4 认中文、不会漏 —— 两边宽严方向不同，
    # 于是「页面看着点了名、判据认为没点」。抄 cme.py:2037-2045。
    zh_only = sorted({e['n'] for e in ex
                      if _ZH_MOM_DECL.search(_ex_decl(e)) and e['n'] not in single})
    if zh_only:
        raise SystemExit(
            f'Exhibit {zh_only} 用中文「单月」声明了口径，却不带 ASCII 的 '
            f'single-month —— 页尾口径条与本页的账本闸门只认后者，会整张漏掉。'
            f'要么把声明改成带 single-month 的写法，要么把这里的判据一起放宽。')
    roll = sorted({e['n'] for e in ex
                   if re.search(r'roll|滚动', _ex_decl(e))})
    if roll:
        raise SystemExit(
            f'Exhibit {roll} 的标题 / 次轴 / 图例里还留着「滚动」口径的字样 —— '
            f'页面所有者要的是全页单月，页尾口径条与各图导航都是照这句写的。'
            f'要么把那张改过来，要么先改断言再改图。')

    bad_stock = sorted(stock_ex - set(single))
    if bad_stock:
        raise SystemExit(f'登记为存量口径的 Exhibit {bad_stock} 没有声明单月同比 —— '
                         f'存量集合应当是声明集合的子集，先对齐再跑。')
    due = sorted(set(single) - stock_ex - set(why))
    missing = [n for n in due if n not in COST_LOG]
    if missing:
        raise SystemExit(
            f'这些图画了流量单月同比却没有逐图代价段：Exhibit {missing} —— '
            f'CONTRACT §6.1 第 3 条要求每一张都用**它自己那条序列**实测把代价印在'
            f'图注里，「逐图」是字面意思，页尾那段不算数。'
            f'补一句 yoy_cal_zh(图号, 序列, 窗口, 点名) 或 yoy_cal_lines_zh(…)。')
    extra = sorted(set(COST_LOG) - set(due))
    if extra:
        raise SystemExit(
            f'这些图号进了代价账本却不在「该印代价」的名单里：Exhibit {extra} '
            f'（本页真该印的是 Exhibit {due}）—— 账本是页尾那段「逐图代价」小结点名与'
            f'排序的唯一依据，多一个图号就等于替一张不存在、或者已经不画单月同比的图'
            f'背书，还带着数。两种改法：那张确实还画着单月同比，就把它的口径声明改回'
            f'带 single-month 的写法；确实不画了，就把对应那句 yoy_cal_zh() 一起删掉。'
            f'（存量图不该进账本，它走 stock_cal_zh()。）')
    # 例外集合**现算，不手写**（cme.py:2064-2078）：声明了单月的 − 该印代价的 − 存量的。
    exempt = sorted(set(single) - set(due) - stock_ex)
    why_miss = [n for n in exempt if n not in why]
    why_extra = sorted(set(why) - set(exempt))
    if why_miss or why_extra:
        raise SystemExit(
            f'代价的例外集合与登记表对不上：Exhibit {why_miss} 画着流量单月同比、'
            f'又不在该印代价的名单里，但没有登记「为什么不重复印」；'
            f'Exhibit {why_extra} 登记了理由却已经不是例外 —— '
            f'登记的理由是要原样印给读者的，两边必须一致。')

    rows = [(n, r['label'], r['d']) for n in sorted(COST_LOG) for r in COST_LOG[n]]
    rows_txt = '；'.join(
        f'<b>Exhibit {n}</b>（{lab}）{d["std_mom"]:.1f}pp／'
        f'最大跳变 {d["maxjump_mom"][0]:.0f}pp（{d["maxjump_mom"][2]}）／'
        f'符号相反 {d["opposite_n"]} 个月'
        f'（{d["opposite_n"] / d["n"] * 100:.0f}%，共 {d["n"]} 个可比月）'
        for n, lab, d in rows if d['n'] >= MOM_COST_MIN)
    return {
        'single': single, 'due': due, 'exempt': exempt, 'stock': sorted(stock_ex),
        'rows': rows, 'rows_txt': rows_txt,
        'exempt_txt': '；'.join(f'Exhibit {n}（{why[n]}）' for n in exempt),
        'hi': max(rows, key=lambda t: t[2]['std_mom']) if rows else None,
        'lo': min(rows, key=lambda t: t[2]['std_mom']) if rows else None,
    }

# ==========================================================================
# 【guards】
# ==========================================================================

# -*- coding: utf-8 -*-
"""build/ice.py 的**护栏与断言层** —— 手写页失去的引擎护栏，在这里补回来。

## 为什么单开这一段

`build/single.py` 是一台带六族护栏的引擎（口径判据 A、同比账本 B、近零/数据形状 C、
图型排版 D、mix E、散文与写出 G）。手写页 `build/cme.py` / `build/cboe.py`
一条都不经过 —— 它们各自**手抄回来一部分**，而抄回来的部分是不重叠的：

    护栏                      cme.py        cboe.py       本文件
    ─────────────────────────────────────────────────────────────
    图号连号 _ENS             1851-1856     ✗（无）        ✓ guard_ex_numbering
    近零基数（硬失败版）       913-919       ✗（无）        ✓ guard_near_zero
    axisfmt.fix_all           2829          ✗（无）        ✓ finalize_axes
    col_is_ratio 全族          ✗             ✗             ✓ guard_colmeta
    fmt ∈ FMT_INFO 白名单      ✗             ✗             ✓ guard_fmt
    比率列量纲体检（×scale）    ✗             ✗             ✓ guard_colmeta
    DENSE 图窗口内无 null      ✗             ✗             ✓ guard_dense
    MAX_LINES                  ✗             ✗             ✓ guard_max_lines
    heat_matrix 同质性         ✗             ✗             ✓ guard_heat_homog
    flat0_skip                 ✗             ✗             ✓ flat0_skip
    chartscale.fix_all/audit   ✗             ✗             ✓ finalize_axes
    caliber_audit              ✗             ✗             ✓ guard_caliber
    同比查重 log_yoy_bar       ✗             ✗             ✓ log_yoy_bar

两页都没有的那 8 条，正是本段要补的。**ICE 比两个参照页更需要它们**，三个理由：

1. ICE 的 `unit` 是**承重字符串**（`build/specs/ice.py:560-590` 记着经过）：
   `oi_rates_kcontracts` 的列名里有 `rates`，`yoy.classify()` 判它 'ratio'，
   唯一挡住这个假阳性的是 `unit='k contracts'` 不是比率量纲。改一个字，
   它的次轴就从「% y/y」静默翻成「pp y/y」、画出一条几万「pp」的线，**不报错**。
2. `build/specs/ice.py:508-521` 的 fmt 决策**明写依赖 `chartscale._budget` 的标签宽度
   预算**（那段算术：band + 12 − 2×LAB_GAP = 17.3px）。ICE 是三页里唯一把
   chartscale 写进口径依据的页，所以它必须真的接上 chartscale，不能像 cme/cboe 那样跳过。
3. ICE 有 CDS 三列 2013-01 才起步，而全页月度图左端是 `WIN_FROM='2016-01'` ——
   DENSE 图型（`stacked_dual` 等四型）窗口内一个 null 都不许有，
   而 `build/verify_pages.py:479` 把它判 **ERROR** → monthly_run FAIL → **28 家一起不发布**。
   在构造点挡住，比在发布闸门上挡住便宜得多。

## 判据一律转发 `build/single.py`，本文件不自写任何口径判据

`build/pctile.py` 的模块头记着这条教训：各写各的，正是同一条序列在两页被判定相反的原因。
所以下面凡是「这一列是不是比率 / 它的差是钱还是百分点」的地方，一律调
`SG.col_is_ratio` / `SG.col_is_money_ratio` / `SG.rhs_ylab2`。
本文件**唯一**自己拿主意的地方是 `UNIT_EXPECT` —— 它不是第二套判据，
是一份**独立的第二意见**，专门用来在 SG 的判据被改动/被 unit 改写绕过时当场响一声
（见 guard_colmeta 上方那段）。

## 硬失败 vs 告警：怎么分

沿用 `build/verify_pages.py:700-728` 已经算过账的那条线 ——
**会让读者读出一个假数的**硬失败（SystemExit），**只是排版难看的**告警：

  · 图号断号：`verify_pages.py:709-722` 只判 **WARN**（不影响退出码），会静默上线；
    而 `table.n <= max(n)` 判 **ERROR**。两个都在本文件里升成硬失败：
    本页没有任何条件图（17 张全画），断号只可能是漏改常量。
  · chartscale 缩放之后**还压字**：告警。它读出来是难看，不是假数，
    而硬失败的代价是整站不发布（同 :711-717 那笔账）。
"""

# ══════════════════════════════════════════════════════════════════════════
# ⚠️ 下面这一块是 **scratchpad 自测专用**。合并进 build/ice.py 时整块删掉 ——
#    那时 HERE__guards/ROOT/CSV/OUT 与 import 由契约冻结的顶部导入块提供。
_WT = ('/Users/hzhan/Documents/monthly-op-dashboards/'
       '.claude/worktrees/cboe-page-redesign-dc42f8')

HERE__guards = os.path.join(_WT, 'build')

sys.path.insert(0, HERE__guards)

# ══════════════════════════ 1. 列元数据的判据断言表 ══════════════════════════
#
# ── 为什么要有「期望值」这一栏，而不是直接信 SG ────────────────────────────
# `SG.col_is_ratio()` 的第 ③ 级是「`yoy.classify()` 判成比率 **且** `unit` 也是比率
# 量纲」—— 两个证据里有一个是 `unit` 这个**由本页自己写的字符串**。也就是说：
# 本页改一个 unit 字符串，就能让 SG 的判定翻掉，而 SG 没有任何立场说这是错的
# （它只知道「你说它是 USD/contract」）。任务书给的实测基线里最惊险的一条正是这个：
#
#     oi_rates_kcontracts  ratio=False  ← classify() 判 'ratio' 的假阳性
#                                          被 unit 'k contracts' 挡住
#
# 所以这里立一份**独立的第二意见**：按 unit 逐条写死期望判定，与 SG 的实际判定对表。
# 两者一致 = 今天的 unit 字符串确实还是承重的那个；不一致 = 有人改了 unit（或 SG 的
# 判据变了），当场停机。这不是「再写一遍判据」—— 期望表是**枚举**（7 个合法 unit
# 各一行），SG 那边是**正则推导**，两者的失效模式不相关，这才是对表的意义。
#
# ⚠️ 合法 unit 只有这 7 个，逐字来自 build/specs/ice.py（606-752 行各列的 'unit'）。
#    这张表同时兼作 unit 白名单：写错一个字（'USD per contract'、'k contract/day'）
#    在这里当场停，而不是留到页面上印出一句错单位。
UNIT_EXPECT = {
    # unit 字符串           (col_is_ratio, col_is_money_ratio)
    'k contracts/day':      (False, False),   # 分母是**时间** ⇒ 日均流量，不是比率
    'k contracts':          (False, False),   # 存量；挡住 classify 对 oi_rates 的假阳性
    'USD/contract':         (True,  True),    # 比率，且分子是钱 ⇒ 差还是钱，不是 pp
    'USD/100 shares':       (True,  True),    # 同上；净因子 1/100 那条腿的费率单位
    'mn shares/day':        (False, False),   # 分母是时间
    'USD bn/month':         (False, False),   # 分母是时间（CDS 名义额是月度合计）
    '%':                    (True,  False),   # 比率，分子是百分数 ⇒ 差是百分点
}

# 逐列显式期望：**只写任务书里逐格实测过的那 5 列**（它们是这一页的口径地基）。
# 其余各列由 UNIT_EXPECT 按 unit 推。两张表对同一列给出不同答案 = 表本身自相矛盾，
# 也停机 —— 那说明有人改了其中一张而没改另一张。
COL_EXPECT__guards = {
    'rpc_energy_usd':                (True,  True),
    'rpc_nyse_us_cash_usd_per100sh': (True,  True),
    'share_nyse_tapeA_matched':      (True,  False),
    'oi_rates_kcontracts':           (False, False),
    'adv_energy_kcontracts':         (False, False),
}

#: 期望「百分数刻度」的格式器族。判据抄 build/single.py:1558-1569，
#: 但把触发面从「fmt ∈ pct*」放宽到「fmt ∈ pct* **或** unit 含 %」——
#: 引擎那条只看 fmt，而本页的 share 五列万一被改成 f3 就整条溜过去了。
PCT_FMT = ('pct0', 'pct1', 'pct2', 'pct0z')

PCT_MIN_MAX = 1.5       # 缩放后最大绝对值必须 > 它，否则就是漏乘 100

def _die(msg):
    """本层唯一的硬失败出口。用 SystemExit 而不是 raise：手写页是脚本，
    `python3 build/ice.py` 的退出码就是闸门读的那个（同 cme.py:915 的写法）。"""
    raise SystemExit(f'[ice 护栏] {msg}')

def guard_fmt(fmt, where):
    """`fmt` 必须是 `assets/charts.js` 实有的格式器名。

    为什么硬失败而不是回落：引擎的 `fmtOf()` 对不认识的名字**静默退回 f1**
    （见 SG.FMT_INFO 上方那段）。ICE 页上 `rpc_nyse_equity_options_usd` 的量程是
    0.04–0.18，退回 f1 就整列印成「0.0 0.1 0.2」—— 图照画、闸门全过、读数全废。

    独立成函数是因为**派生列没有 COL 条目**：隐含收入（$mn）、bridge 的 pp 腿、
    对账图的相对差线，这些 fmt 不经过 guard_colmeta，只能在各自的构造点调这一条。
    """
    if fmt not in SG.FMT_INFO:
        _die(f'{where} 的 fmt={fmt!r} 不是 assets/charts.js 实有的格式器名'
             f'（引擎对不认识的名字**静默退回 f1**）；可用：{sorted(SG.FMT_INFO)}')
    return fmt

def ylab2_for(c, mom=None):
    """次轴标题。**存量列不许带「（单月）」** —— ICE 特有陷阱第 4 条。

    `mom` 不给就按 `c['stock']` 自动定：存量的同比是两个**时点**的点对点比较，
    「单月同比」这四个字对它是句错话（CONTRACT §6.1 第 3 条那笔逐图代价的债
    只管流量列，存量没有第二种合法口径，也就没有代价可报）。
    显式传 `mom=True` 给一条存量列 = 调用方写错了，当场停。
    """
    if mom is None:
        mom = not bool(c.get('stock'))
    if c.get('stock') and mom:
        _die(f'{c["col"]} 是存量列（stock=True），次轴标题不许写「（单月）」——'
             f'存量的同比是两个时点的点对点比较，不是两个月份的流量比。'
             f'标题另带「（存量，期末口径）」，tools/check_yoy_caliber.py 的 _STOCK_TXT 认的就是那几个字。')
    return SG.rhs_ylab2(c, mom=mom)

def guard_colmeta(COL, df, *, expect=COL_EXPECT__guards, unit_expect=UNIT_EXPECT, verbose=False):
    """列元数据表的总体检。返回逐列的判定表（供页尾释义板/自测打印）。

    六道，任一不过就 SystemExit：
      ① 字段名 ⊆ `SG.COL_KEYS`（手写页保留与引擎同形的列字典，拼错的键会被静默忽略）
      ② 列在 CSV 里真的存在
      ③ `fmt ∈ SG.FMT_INFO`
      ④ `unit ∈ UNIT_EXPECT`（= 本页 unit 白名单，逐字来自 build/specs/ice.py）
      ⑤ 逐列期望 vs 量纲期望不许打架
      ⑥ 期望判定 == `SG.col_is_ratio` / `SG.col_is_money_ratio` 的实际判定
      ⑦ 比率列的量纲体检：`max|v| × scale > 1.5`
    """
    rows = []
    for key, c in COL.items():
        w = f'COL[{key!r}]'
        bad = sorted(set(c) - SG.COL_KEYS)
        if bad:
            _die(f'{w} 有未知字段 {bad} —— 手写页的 COL 与引擎的列字典同形，'
                 f'拼错的键（stocks / ratios / Fmt）会被静默忽略；'
                 f'允许的字段：{sorted(SG.COL_KEYS)}')
        for req in ('col', 'zh', 'unit', 'fmt'):
            if req not in c:
                _die(f'{w} 缺必填字段 {req!r}')
        if c['col'] not in df.columns:
            _die(f'{w} 的 col={c["col"]!r} 不在 series/ice.csv 里')
        guard_fmt(c['fmt'], w)
        if c['unit'] not in unit_expect:
            _die(f'{w} 的 unit={c["unit"]!r} 不在本页 unit 白名单里。\n'
                 f'    ⚠️ unit 在本页是**承重字符串**：SG.col_is_ratio 的第 ③ 级把它当'
                 f'两个证据之一，改一个字就会让同比口径翻掉且不报错'
                 f'（build/specs/ice.py:560-590 记着经过）。\n'
                 f'    合法值只有：{sorted(unit_expect)}')

        exp_u = unit_expect[c['unit']]
        exp_c = expect.get(c['col'])
        if exp_c is not None and exp_c != exp_u:
            _die(f'{w}：逐列期望 {exp_c} 与量纲期望 {exp_u}（unit={c["unit"]!r}）打架 —— '
                 f'两张期望表本身自相矛盾，说明改了其中一张没改另一张。')
        exp = exp_c if exp_c is not None else exp_u

        act = (SG.col_is_ratio(c), SG.col_is_money_ratio(c))
        if act != exp:
            _die(f'{w} 的比率判定与期望不符：期望 ratio={exp[0]} money={exp[1]}，'
                 f'SG 实际判 ratio={act[0]} money={act[1]}。\n'
                 f'    这一列现在的次轴标题会是 {SG.rhs_ylab2(c, mom=True)!r}。\n'
                 f'    两种可能：(a) 有人改了 unit={c["unit"]!r} 或 fmt={c["fmt"]!r}，'
                 f'把判据绕过去了；(b) build/single.py 的 col_is_ratio 判据变了。\n'
                 f'    两种都必须由人来看 —— 判错的代价是「RPC 从 0.05 掉到 0.04」'
                 f'被印成「−1bp」而不是「跌了五分之一」。')

        # ⑦ 比率量纲体检（判据抄 build/single.py:1558-1569，触发面见 PCT_FMT 上方）
        if c['fmt'] in PCT_FMT or '%' in c['unit']:
            v = df[c['col']].astype(float).values
            mx = float(np.nanmax(np.abs(v))) * float(c.get('scale', 1.0)) if np.isfinite(v).any() else np.nan
            if np.isfinite(mx) and mx <= PCT_MIN_MAX:
                _die(f'{w} 的最大绝对值（乘 scale={c.get("scale", 1.0)} 之后）只有 {mx:.4g}，'
                     f'看着是 0–1 的小数比率，而 fmt={c["fmt"]!r} / unit={c["unit"]!r} '
                     f'期望百分数刻度（29.0 表示 29%）——'
                     f"漏乘 100 会把 19.1% 印成 0.2%，图照画、没人报错。"
                     f"请加 'scale': 100，或换成 f2/f3。")
            rows.append((key, c['unit'], c['fmt'], act[0], act[1], mx))
        else:
            rows.append((key, c['unit'], c['fmt'], act[0], act[1], None))
    if verbose:
        for r in rows:
            print(f'    {r[0]:<32} unit={r[1]:<16} fmt={r[2]:<5} '
                  f'ratio={str(r[3]):<5} money={str(r[4]):<5} '
                  + ('' if r[5] is None else f'max×scale={r[5]:.4g}'))
    return rows

# ═════════════════════ 2. exhibit 连号 / 核对表排位 ═════════════════════
_ENS = []

_ENS_WANT = []

AXIS_WARN = []      # finalize_axes 攒下的「只报不改」项，由 run_all_guards 汇出

def guard_ex_numbering(ex, table, ex_first):
    """图号必须等于 `ex.append` 的顺序、自 `ex_first` 起连号无洞、核对表接在最后。

    判据逐字抄 build/cme.py:1851-1856，理由在那里写过一遍，这里只记 ICE 特有的账：

      · `build/verify_pages.py:709-722` 把**断号**判 WARN（不影响退出码）——
        它会**静默上线**。那条 WARN 之所以不能升 ERROR，是因为 exchanges_eu /
        exchanges12 有按数据可得性写的条件图（:711-717 那笔账：升 ERROR 的实测代价是
        「上游断一次货 → 28 家一起不发布」）。**本页没有任何条件图**，17 张全画，
        所以断号只可能是漏改 EX_* 常量 —— 在这里升成硬失败是安全的。
      · `table.n <= max(n)` 在 :723-728 是 **ERROR** → monthly_run 判 FAIL →
        28 家一起不发布。所以核对表编号必须在构建期就对，不能留给闸门。
      · 页面按**列表顺序**渲染、读者按**编号**读，两者不一致就是一页乱序的图。
    """
    global _ENS, _ENS_WANT
    _ENS = [e['n'] for e in ex]
    _ENS_WANT = list(range(ex_first, ex_first + len(ex)))
    tn = (table or {}).get('n')
    if _ENS != _ENS_WANT or tn != ex_first + len(ex):
        _die(f'图号与 ex.append 的顺序对不上：现在是 {_ENS}（应当是 {_ENS_WANT}），'
             f'核对表 n={tn!r}（应当是 {ex_first + len(ex)}）—— '
             f'文件头的 EX_* 常量表与 append 的调用顺序必须一起改。'
             f'（verify_pages 把断号只判 WARN，会静默上线；把 table.n 判 ERROR，'
             f'会让 28 家一起不发布。两头都不能指望，所以在这里挡。）')
    return _ENS

# ══════════════════════ 3. DENSE 图窗口内不许有 null ══════════════════════
#: 逐字同 build/verify_pages.py:72 的 DENSE。**不能少写一个**：那边判 ERROR。
DENSE_KINDS = frozenset({'gs_line', 'gs_line_avg', 'lines_endlabels', 'stacked_dual'})

def _arrays_of(ex):
    """→ [(字段路径, 数组)]，该 exhibit 里全部「按 x 轴逐点」的数组。

    是 build/verify_pages.py:arrays_of 的**本地副本**，不 import 那个文件：
    契约冻结的顶部导入块里没有它，而它是个带 argparse main() 的闸门脚本，
    手写页 import 一个闸门去自检等于把闸门搬进被闸的东西里。
    ⚠️ 副本要跟着改：那边加一个容器键，这里漏了就等于这道护栏对新键失明。
    """
    out = []

    def take(name, obj, key='values'):
        if isinstance(obj, dict) and isinstance(obj.get(key), list):
            out.append((f'{name}.{key}', obj[key]))

    for k in ('values', 'lo', 'hi', 'actual'):
        if isinstance(ex.get(k), list):
            out.append((k, ex[k]))
    for k in ('bar', 'line', 'net', 'yoy', 'base'):
        take(k, ex.get(k))
    if isinstance(ex.get('actual'), dict):
        take('actual', ex['actual'])
    for grp in ('series', 'stacks', 'groups'):
        for i, s in enumerate(ex.get(grp) or []):
            take(f'{grp}[{i}]', s)
    return out

def dense_win(df, cols, win_from, all_periods=None):
    """一张 DENSE 图**自己那几列**的合法窗口 → [Period]。

    ── 为什么窗口左端不能全页共用一个 `_i0` ──────────────────────────────
    cboe.py:1010-1011 已经踩过一半：那一页的 RPC 列比其余列少一个月，于是它单算了
    `i_rpc` / `W25R` 两个窗口。ICE 更狠 —— **CDS 三列 2013-01 才起步**
    （NYSE 各列 2011-01 起，但 2013-11 之前是追溯并入的形式数）。
    全页共用 `WIN_FROM='2016-01'` 对 CDS 恰好安全，可这是**巧合**：
    上游哪天把 CDS 回补到 2014、或者新增一条 2017 才起步的腿，
    共用左端就会在 stacked_dual 里插进几个 null，而那是 verify_pages 的 ERROR。
    所以左端由「这几列的共同首个非空月」与 `WIN_FROM` 取**较晚**的那个 —— 只往右让。

    窗口内部还有洞（首尾有值、中间缺）则**硬失败**：那不是「数据还没到」，
    是上游漏了一个月，截窗口治不了，只能让人去看。
    """
    idx = list(all_periods) if all_periods is not None else list(df.index)
    lo = pd.Period(win_from, 'M')
    for c in cols:
        s = df[c].astype(float)
        nn = s.dropna()
        if not len(nn):
            _die(f'dense_win：列 {c!r} 整列为空，画不了 DENSE 图')
        lo = max(lo, nn.index[0])
    win = [p for p in idx if p >= lo]
    if not win:
        _die(f'dense_win：{cols} 的共同起点 {lo} 晚于数据末月，窗口是空的')
    holes = {}
    for c in cols:
        s = df[c].astype(float)
        bad = [str(p) for p in win if not np.isfinite(s.get(p, np.nan))]
        if bad:
            holes[c] = bad
    if holes:
        _die(f'dense_win：窗口 {win[0]}–{win[-1]} 内这几列有洞，'
             f'而 DENSE 图型窗口内一个 null 都不许有'
             f'（build/verify_pages.py:479 判 ERROR → monthly_run FAIL → 28 家一起不发布）：'
             + '；'.join(f'{c} 缺 {v[:6]}{"…" if len(v) > 6 else ""}' for c, v in holes.items())
             + '。窗口内部的洞截不掉，只能去看上游。')
    return win

def guard_dense(e):
    """一张已经构造好的 exhibit：若是 DENSE 四型，逐个数组断言无 null。

    在**构造点**逐张调，不是最后统一扫一遍 —— 报错要指得出是哪张图的哪一段代码，
    统一扫只能告诉你「Exhibit 12 有 null」，而那时候上下文已经没了。
    """
    kind = e.get('kind')
    if kind not in DENSE_KINDS:
        return e
    for path, arr in _arrays_of(e):
        bad = [i for i, v in enumerate(arr) if v is None]
        if bad:
            xl = e.get('xlabels') or []
            at = [xl[i] for i in bad[:6] if i < len(xl)]
            _die(f'Exhibit {e.get("n")}（{kind}）的 {path} 有 {len(bad)} 个 null'
                 f'（首个在 idx {bad[0]}{"，即 " + str(at) if at else ""}）—— '
                 f'DENSE 图型的平滑会把 null 当 0，画出一条塌到零的假线；'
                 f'{"逐点标数值时还会抛 TypeError" if kind != "lines_endlabels" else "首尾为 null 时抛 TypeError"}。'
                 f'出路是用 dense_win() 把窗口左端让到这几列的共同起点，不是补 0。')
    return e

# ═════════════════════════ 4. MAX_LINES / 热力矩阵同质性 ═════════════════════════
def guard_max_lines(e):
    """一张 lines / lines_endlabels 图最多 `SG.MAX_LINES` 条。

    阈值取 SG 的常量而不是写 5：docs/CHART_KINDS.md §2 那条线要是改了，
    本页跟着改，不用来这里找。
    ICE 这一页真的会撞上：Ex4 的 RPC 若把 `rpc_commodities` / `rpc_financials`
    两条上层聚合也画进去就是 6 条 —— 图序定稿把它们踢出去（只现算进标题与图注），
    这道护栏是那个决定的机器版本。
    """
    if e.get('kind') not in ('lines', 'lines_endlabels'):
        return e
    ser = e.get('series') or []
    if len(ser) > SG.MAX_LINES:
        _die(f'Exhibit {e.get("n")} 有 {len(ser)} 条线 > MAX_LINES={SG.MAX_LINES}'
             f'（数据色只有 6 个，RED 是断点专用、GRAY 另有专职）——'
             f'超出上限的对比图要改画 heat_matrix，或把上层聚合列踢出去只留叶子。'
             f'线名：{[s.get("name") for s in ser]}')
    # 颜色撞车（判据同 verify_pages.py:490-497：判的是颜色有没有真撞上，不是线数）
    cols = [s.get('color') for s in ser if s.get('color')]
    dup = sorted({c for c in cols if cols.count(c) > 1})
    if dup:
        _die(f'Exhibit {e.get("n")} 有两条线同色 {dup} —— 读者分不开')
    return e

def guard_heat_homog(n, cols):
    """热力矩阵里比率列与量列不许混、「分子是钱」的比率与百分点比率也不许混。

    判据与文案抄 build/single.py:2328-2377（`ex_heat`），理由照搬：
    **整张矩阵只有一条色标、一个单位**，混了就是拿 pp 和 % 比高低。
    ICE 的 Ex11 是全页唯一一张矩阵，十二个官方单列产品全是 `k contracts/day`，
    今天必然同质 —— 护栏留着是因为「今天必然」靠的是图序定稿这个约定，
    哪天有人把 RPC 塞进那张矩阵，这里得响一声而不是静默画错。
    """
    kinds = {SG.col_is_ratio(c) for c in cols}
    if len(kinds) > 1:
        _die(f'Exhibit {n} 的热力矩阵里比率列与量列混在一起 —— '
             f'格内一半是差、一半是百分比变化，而整张矩阵共用一条色标，'
             f'颜色深浅会被读成「谁涨得多」。'
             f'比率列：{[c["zh"] for c in cols if SG.col_is_ratio(c)]}；'
             f'量列：{[c["zh"] for c in cols if not SG.col_is_ratio(c)]}。')
    ratio = bool(kinds and next(iter(kinds)))
    money_kinds = {SG.col_is_money_ratio(c) for c in cols} if ratio else {False}
    if len(money_kinds) > 1:
        _die(f'Exhibit {n} 的热力矩阵里「分子是钱」的比率与「分子是百分数」的比率'
             f'混在一起 —— 一半是 {cols[0]["unit"]} 的差、一半是百分点，共用一条色标。'
             f'钱：{[c["zh"] for c in cols if SG.col_is_money_ratio(c)]}；'
             f'百分点：{[c["zh"] for c in cols if not SG.col_is_money_ratio(c)]}。')
    return ratio, bool(money_kinds and next(iter(money_kinds)))

# ═══════════════════════════ 5. 近零基数 ═══════════════════════════
#
# ── 为什么 ICE 选「硬失败 + 注记」两档，而不是引擎的「截轴 + 图注」一档 ──────
# 两个参照实现：
#   · cme.py:913-919 —— 硬失败：命中就 SystemExit，理由是「§6.1 第 5 条明说这条序列
#     该画水平值而不是同比」，画出来那条线读的是分母不是量。
#   · single.py:1887-1960 —— 截轴 + 图注：把上界钳到 P95，再把哪几个月说清楚。
#     它必须这么做，因为引擎是通用的，一硬失败就会把整页打挂而 spec 作者未必改得动。
#
# 本页两档并用，分界是**这条同比画在哪种图上**：
#   ① 有纵轴可截、且这条同比是图上的主角（gs_bar 的次轴金线）→ **硬失败**。
#      ICE 的 `adv_environmentals_kcontracts` 与 `adv_fx_credit_kcontracts` 是小基数行
#      （ICE 特有陷阱第 3 条：官方原表已四舍五入到整千张，小基数行的同比会与官方
#      新闻稿差 1–2pp）。图序定稿里这两列**不占任何一张柱图**，所以这一档今天不该命中；
#      哪天有人给它们单开一张 gs_bar，就该当场停，而不是画一条读分母的线。
#   ② 热力矩阵（Ex11）→ **只注记，不失败**。矩阵**没有纵轴**，截轴无从谈起
#      （single.py:1996 的 `near_zero_rows_zh` 就是为这个单列的一支），
#      超界的格子由色标的 5/95 分位自己吃掉。而 Ex11 是全页唯一一张矩阵、
#      十二个官方单列产品里就有环境权益与 FX 两条小基数行 —— 硬失败等于这张图不能画。
def guard_near_zero(n, c, s_full, win, *, mode='fail'):
    """近零基数。`mode='fail'` → 命中即停；`mode='note'` → 返回一段中文注记（不停）。

    判据与阈值全部转发 `build/yoy.py`（`NEAR_ZERO_BASE_FRAC` / `NEAR_ZERO_SERIES_SHARE`
    的推导在那里，本文件一个字面量都不抄 —— yoy.py 模块头点名禁止抄那一行）。
    比率列直接豁免：比率的同比走差值，分母是不是接近零与它无关（同 single.py:1900）。
    """
    if SG.col_is_ratio(c):
        return ''
    s = s_full.copy()
    s.index = [mlab(p) if hasattr(p, 'strftime') else str(p) for p in s_full.index]
    nz = YOY.near_zero_base(s, win=[mlab(p) for p in win])
    if not nz['flag']:
        return ''
    head = (f'Exhibit {n}（{c["col"]}）的近零基数月在窗口内占 {nz["share"]:.1%}'
            f'（≥ {YOY.NEAR_ZERO_SERIES_SHARE:.4g}），基期低于本序列全历史 |值| 中位数的 '
            f'{YOY.NEAR_ZERO_BASE_FRAC:.0%}')
    if mode == 'fail':
        _die(head + f'。CONTRACT §6.1 第 5 条：这条序列不该画同比，该画水平值。'
                    f'最极端的一个月：{nz.get("worst")}')
    return (f'<b>⚠️ 近零基数：{c["zh"]}这一行的同比有一段读的是分母，不是量。</b>'
            f'{head}（{len(nz["months"])} 个月）。'
            f'本图是热力矩阵，没有纵轴可截，超界的格子由色标的 5/95 分位吃掉 —— '
            f'这一行的深浅不可与其余各行同读。')

# ═══════════════════════ 6. 窗口内恒为 0 的图不出 ═══════════════════════
FLAT0_LOG = []

def flat0_skip(gz, cols, win, vs):
    """窗口内恒为 0 → 记账并让调用方 `return None`（判据同 single.py:1668-1688）。

    手写页为什么也要：ICE 的 `cds_client_notional_usdbn` / `cds_nonclient_*`
    在 2013-01 之前整段为空、`adv_single_stock_kcontracts` 被官方剔出合计之后
    有一段长期为 0。一条恒为 0 的序列画出来是一条贴着轴的直线 + 一条全 nan 的同比，
    读者读不出「它归零了」，只读出「这张图坏了」。
    记的是「哪一组、哪几列、什么窗口、最后一个非零月是哪个月多少」，
    一个数都不写死 —— 指标哪天恢复非零，图自动回来。
    """
    flat = all(all((v is None) or (not np.isfinite(v)) or (float(v) == 0.0) for v in a)
               for a in vs)
    if not flat:
        return False
    for c in cols:
        s = c['_s'].dropna() if '_s' in c else pd.Series(dtype=float)
        nz_s = s[s != 0]
        FLAT0_LOG.append({
            'gz': gz, 'zh': c['zh'], 'unit': c['unit'], 'fmt': c['fmt'],
            'win': (mlab(win[0]), mlab(win[-1]), len(win)),
            # 最后一个非零月取**全序列**：窗口里已经全是 0，读者要知道的正是它何时归零
            'last_nz': (str(nz_s.index[-1]), float(nz_s.iloc[-1])) if len(nz_s) else None,
        })
    return True

# ═══════════════════════ 7. 同比查重（同一列同口径不许画两遍）═══════════════════════
#
# ICE 现状（声明式那一版）就有两对同源：Ex4↔Ex25、Ex5↔Ex26。改写成手写页之后
# 没有任何东西会再挡它 —— `single.py:1731-1775` 的 `log_yoy_bar` 留在引擎里。
# 所以这本账要搬过来。两档判据与理由逐字同引擎：
#   · **同族 + 同窗口 → 硬失败**：两张图连横轴都逐格相同，读者看到的是一字不差的两张。
#   · **同族但窗口不同、或不同族 → 只告警**：那两张确实共用一条数组，
#     但各自还带着对方没有的东西（更长的历史 / 把同比放大到整张画布）。
#     一律硬失败会把设计好的图序当场打挂，而那不是「重复」该付的代价。
#
# ⚠️ 本页比引擎多一族：`qtr_yoy`。季度块（Ex5–Ex9）的同比 L=4、月度块 L=12 ——
#    **同一列的月度同比与季度同比不是同一条线**，不该被判成重复。
#    这就是图序定稿要求「两块的同比 L 不同要逐图点名」的那条规则的机器版本。
YOY_FAMILIES = ('bar_yoy', 'yoy_only', 'qtr_yoy')

YOY_FAMILY_ZH = {'bar_yoy': '水平值柱 + 次轴同比', 'yoy_only': '纯同比图',
                 'qtr_yoy': '季度柱 + 季度同比'}

_YOY_BAR_COLS = {}

DUP_YOY = []

def log_yoy_bar(n, col, win, cal, family, where):
    """登记「Exhibit n 在列 col 上画了一条 cal 口径的同比」，并当场查重。

    `col` 收字符串（列名）而不是 COL 条目：派生列（隐含收入 $mn、bridge 的净值）
    没有 COL 条目，但它们同样会被画两遍。`cal` 是口径标签（'mom' / 'qoq4' …），
    由调用方给 —— 本层不猜口径，猜错的代价是把两条不同口径的线判成重复。
    """
    if family not in YOY_FAMILIES:
        _die(f'log_yoy_bar 收到未知图族 {family!r} —— 这是页面代码写错，'
             f'认得的：{YOY_FAMILIES}')
    lab = (str(win[0]), str(win[-1]), len(win))
    rec = {'n': n, 'family': family, 'cal': cal, 'where': where, 'win': lab}
    for prev in _YOY_BAR_COLS.get(col, []):
        if prev['cal'] != cal:
            continue
        if prev['family'] == family and prev['win'] == lab:
            _die(f'{where} 的列 {col} 与 Exhibit {prev["n"]}（{prev["where"]}）'
                 f'画的是同一张图：同一列、同一口径（{cal}）、同一图族（{family}）、'
                 f'横轴逐格相同（{lab[0]} 至 {lab[1]}，{lab[2]} 期）—— 两张一字不差，'
                 f'请删掉其中一条。若确实要留两张，得让它们有实质差别：'
                 f'换窗口、换列，或者把其中一条并进同单位的多列对比图。')
        DUP_YOY.append({'col': col, 'cal': cal, 'a': prev, 'b': rec})
    _YOY_BAR_COLS.setdefault(col, []).append(rec)
    return rec

def dup_yoy_zh():
    """`DUP_YOY` → 页尾那一段。空账返回 ''。

    写给读者的用处很具体：同一条金线出现在相隔十几号的两张图上时，读者会去找
    「这两条到底差在哪」，而答案是**不差**。逐对现算，不给一句涵盖所有情形的套话。
    """
    if not DUP_YOY:
        return ''
    bits = []
    for d in DUP_YOY:
        a, b = d['a'], d['b']
        same = a['win'] == b['win']
        bits.append(
            f'Exhibit {a["n"]}（{YOY_FAMILY_ZH[a["family"]]}）与 Exhibit {b["n"]}'
            f'（{YOY_FAMILY_ZH[b["family"]]}）画的是同一列 <code>{d["col"]}</code> '
            f'的同一条同比（口径 {d["cal"]}），'
            + (f'横轴逐格相同（{a["win"][0]} 至 {a["win"][1]}，{a["win"][2]} 期），两条线逐点相等'
               if same else
               f'Exhibit {a["n"]} 画 {a["win"][0]}–{a["win"][1]}（{a["win"][2]} 期）、'
               f'Exhibit {b["n"]} 画 {b["win"][0]}–{b["win"][1]}（{b["win"][2]} 期），'
               f'重叠的那一段逐点相等'))
    return ('<b>同一条同比出现在不止一张图上。</b>' + '；'.join(bits)
            + '。<b>这不是两个读数</b>，不必去找它们的差别。'
              '这段话由构建期逐图比对现算，删掉任一张它自动消失。')

# ═══════════════════════ 8. 口径自洽（图注里自相矛盾的断言）═══════════════════════
def guard_caliber(ex):
    """扫全部图注，撞上互斥口径断言就停机。转发 `SG.caliber_audit`（single.py:915-924）。

    为什么手写页更需要它：引擎那几对模式（「本身即当月合计口径，未做还原」×
    「柱是日均」…）抓的是**底座自己**拼图注时踩过两次的坑，而 ICE 的图注是手写的、
    还必须同时说三套交易日与「不许把总 ADV 乘回当月合计」（ICE 特有陷阱第 1 条）——
    正是最容易在同一段里既说日均又说合计的那种页面。
    """
    hits = SG.caliber_audit(ex)
    if hits:
        _die(f'图注里有 {len(hits)} 处自相矛盾的口径断言：'
             + '；'.join(f'Exhibit {n}「{why}」' for n, why in hits))
    return []

def audit_title_since(ex):
    """标题里印着比横轴左端更早的年月 → [(n, 说明)]。**告警，不停机。**

    ICE 一定会撞上：口径断点 2013-11（NYSE Euronext 收购完成）比 WIN_FROM=2016-01 早
    两年多，而讲清楚 NYSE 各列为什么在 2013-11 前是形式数，标题/图注里绕不开这个年月。
    引擎的做法（single.py:1698-1722）是把关系说破而不是禁止 —— 照搬那个态度：
    返回文案让调用方决定挂在哪张图的图注上。
    """
    return [(e.get('n'), t) for e in ex if (t := SG.title_since_zh(e))]

# ══════════════════ 9. 接上 chartscale 与 axisfmt（顺序是承重的）══════════════════
def finalize_axes(ex, *, strict=False):
    """显示缩放 → 轴刻度位数 → 复量标签宽。返回 (disp, tight)。

    **顺序不许换**：`chartscale.fix_all` 会原地改 values 与 fmt，
    `axisfmt.fix_all` 要在**已经缩过**的数上定刻度位数（chartscale.py:271 明写
    「必须在 axisfmt.fix_all() 之前调用」）。反过来就是拿旧量级定的位数去印新数。

    ── 为什么 ICE 必须接，而 cme/cboe 可以不接 ──────────────────────────
    `build/specs/ice.py:508-521` 的 fmt 决策**明写依赖 `chartscale._budget` 的
    标签宽度预算**（band + 12 − 2×LAB_GAP）。也就是说本页的 fmt 是按那把尺子选的；
    尺子不跑，选出来的 fmt 就没有对应的缩放去兜底。cme.py 只接了 axisfmt（:2829），
    cboe.py 两个都没接 —— 那两页的 fmt 决策没有写这条依赖，所以不接也自洽。

    `strict=False`（默认）：缩放之后还压字只**告警**。理由见模块头那笔账 ——
    压字读出来是难看，不是假数，而硬失败的代价是整站不发布。
    `_cols` 由 `chartscale.fix_all` 自己 pop 掉（chartscale.py:316-318），不进 payload。
    """
    disp = chartscale.fix_all(ex)
    axisfmt.fix_all(ex)
    tight = chartscale.audit(ex)     # 缩完再量一遍：回答的是「修完还剩没剩」
    # ⚠️ ICE 特有：本页的单位串**自带量级词**（`k contracts/day`、`mn shares/day`），
    #    chartscale 再追一个「（千）」就读成「k contracts/day（千）」= 千个千张/日。
    #    现网 data/ice.js 上已经有 8 张图是这个样子（Ex2/3/17-26，2026-09-04 实读）——
    #    它不是本轮引入的，但既然手写页要重排图序，就该由页面 owner 当场决定
    #    （改 ylab 预缩成「mn contracts/day」，还是照旧）。所以只报，不改也不停。
    for unit, k, word in disp:
        if re.match(r'^(k|mn|bn)\s', unit or ''):
            AXIS_WARN.append(
                f'单位 {unit!r} 自带量级词，chartscale 又追了一个「{word}」'
                f'（÷{int(k):,}）⇒ 轴标题读成「{unit}（{word}）」。'
                f'要么把 ylab 预缩成一个单一量级词，要么接受 —— 这一条只报不改。')
    if tight and strict:
        _die(f'chartscale 缩放之后仍有 {len(tight)} 处标签压字/越界：'
             + '；'.join(f'Exhibit {n} {sym}（{det}）' for n, sym, det in tight))
    return disp, tight

# ═══════════════════════ 10. 总入口：payload 组装前跑一遍 ═══════════════════════
def run_all_guards(ex, table, *, ex_first, strict_tight=False):
    """图与表都构造完、payload 组装之前调一次。返回 (disp, tight, warn)。

    顺序有讲究：
      ① 连号先判 —— 后面几条的报错文案都要报图号，图号本身错了先说图号；
      ② DENSE / MAX_LINES 逐张复查一遍（构造点已经各查过一次，这里兜底：
         构造点漏调一处不会有任何东西响，而这里扫的是最终 payload）；
      ③ 口径自洽在缩放**之前**跑 —— chartscale 会往 note 末尾追加自己那段
         「本图按百万计」，跑在后面等于把它也扔进互斥模式的正则里比一遍
         （single.py:4008 那行注释记着同一条顺序约束）；
      ④ 缩放与轴刻度最后跑，它们原地改 payload。
    """
    guard_ex_numbering(ex, table, ex_first)
    for e in ex:
        guard_dense(e)
        guard_max_lines(e)
    guard_caliber(ex)
    warn = []
    for n, t in audit_title_since(ex):
        warn.append(f'Exhibit {n} 标题早于横轴左端：{re.sub("<[^>]+>", "", t)[:90]}…')
    disp, tight = finalize_axes(ex, strict=strict_tight)
    warn += AXIS_WARN
    for n, sym, det in tight:
        warn.append(f'Exhibit {n} 缩放后仍压字：{sym} —— {det}')
    if DUP_YOY:
        warn.append(f'同比查重：{len(DUP_YOY)} 对同源（页尾会现算点名）')
    if FLAT0_LOG:
        warn.append(f'窗口内恒为 0 而未出图：{[d["zh"] for d in FLAT0_LOG]}')
    return disp, tight, warn

# ==========================================================================
# 【facts】
# ==========================================================================

# -*- coding: utf-8 -*-
"""build/ice.py 的「图注事实层」—— 图注里每一个数的 import 期现算 helper。

═══ 这一段存在的唯一理由 ═══════════════════════════════════════════════════
build/specs/ice.py:11-16 立的规矩，逐字搬过来：

    列数 / 月数 / 起止月 / 哪几列有空洞**一个都不写在这里** —— 它们每个月都在变，
    写进注释就是养一句下个月自动过期的话。

build/specs/ice.py:44-50 立的第二条：

    图注里要报的数**一个都不写死**：在 import 期从 series/ice.csv 现数。
    读不到就退回不含数字的定性版本 —— **缺文件不许在 import 期抛异常**，
    否则 monthly_run 会因为一张页的配置炸掉整批。

⚠️ 「不许抛异常」有三个**故意的例外**，原样保留、一个都不许放宽：
  · `_nonint_census()`   —— 名单对不上（RPC / 份额之外的列出现小数）→ SystemExit
  · `_cds_start()`       —— CDS 三列首月不一致 → SystemExit
  两者都不是「数据缺失」，是**页面上那句全称断言与数据对不上**。
  差别很重要：缺文件是别人的事故（不该连坐整批），断言失真是本页的事故
  （必须当场停机，否则那句假话会继续印，而且没有任何东西会报错）。
  `_ceil_to()` 不抛异常，但它是同一类护栏（印上界必须向上取），一并原样保留。

═══ 这一段**不做**什么 ═════════════════════════════════════════════════════
不判「这一列的同比是百分数 / 百分点 / 还是美元差」。那一律走
`SG.col_is_ratio` / `SG.col_is_money_ratio` / `SG.rhs_ylab2` / `SG.money_diff_txt`
/ `SG.ratio_diff_txt` / `SG.chg_txt`。build/pctile.py 的模块头记着这条教训：
各写各的判据，正是同一条序列在两页被判定相反的根因。

不格式化。本文件一律返回**裸数**（float / int / dict），格式化交给调用点的
`comma()` / `pctf()` / `pp()` / `nz()`（那是另一段）。唯一的例外是
`_ceil_to()` / `_floor_to()`：它们是**取整方向**的护栏，不是格式化。
"""

sys.path.insert(0, HERE)

if not os.path.exists(os.path.join(ROOT, 'series', 'ice.csv')):
    ROOT = _REPO
    sys.path.insert(0, os.path.join(ROOT, 'build'))

#: 迁移期的别名。specs/ice.py 里这个常量叫 `_CSV`，正文的 helper 全用它；
#: 冻结契约里模块级的名字是 `CSV`。留一个别名，helper 体就能**逐字**搬过来。
_CSV = CSV

# ══════════════════════════════════════════════════════════════════════════════
# §0 读表的两个零件（specs/ice.py:126-146 原样搬）
# ══════════════════════════════════════════════════════════════════════════════
def _rows():
    try:
        with open(_CSV, encoding='utf-8') as fh:
            return list(csv.DictReader(fh))
    except OSError:
        return []

def _num(r, col):
    """CSV 里一格 → float；空格子 / 非数返回 None（不拿 0 冒充缺失）。"""
    try:
        v = r[col].strip()
    except (KeyError, AttributeError):
        return None
    if not v:
        return None
    try:
        return float(v)
    except ValueError:
        return None

#: 新增：本段的 pandas 视图。迁移过来的 helper 一律不碰它（保持逐字），
#: **只有新增的四个统计型 helper**（相关系数 / 季节指数 / 峰值比 / 混合费率）用它 ——
#: 它们要的是滚动窗口、按月分组、lag 对齐这类事，用 csv.DictReader 手写一遍
#: 只会多出一份会写错的代码。读不到返回 None（同样不抛）。
_FRAME_CACHE = []

def _frame():
    """series/ice.csv → 以 PeriodIndex('M') 为索引的 DataFrame；读不到返回 None。"""
    if _FRAME_CACHE:
        return _FRAME_CACHE[0]
    rows = _rows()
    if not rows:
        _FRAME_CACHE.append(None)
        return None
    df = pd.DataFrame(rows)
    idx = pd.PeriodIndex(df['month'], freq='M')
    df = df.drop(columns=['month']).apply(pd.to_numeric, errors='coerce')
    df.index = idx
    _FRAME_CACHE.append(df)
    return df

def _win(df, win):
    """按左端月份切窗。win=None → 全表。序列比窗口短就用它自己的起点（只往右让）。"""
    if df is None:
        return None
    if not win:
        return df
    return df[df.index >= pd.Period(win, 'M')]

# ══════════════════════════════════════════════════════════════════════════════
# §1 迁移：specs/ice.py 里的 11 个 helper（连注释一并搬，一个字不改）
# ══════════════════════════════════════════════════════════════════════════════
def _column_census():
    """数「金额列 / 数量列 / 费率列」各几条 —— 「做不了分解」的机器判据。

    返回 (成交金额列数, 数量列数, 费率列数, 清算名义额列数)；读不到返回 (None,)*4。
    """
    try:
        with open(_CSV, encoding='utf-8') as fh:
            cols = next(csv.reader(fh))
    except (OSError, StopIteration):
        return (None,) * 4
    rate = [c for c in cols if c.startswith('rpc_')]
    notional = [c for c in cols if 'notional' in c]
    qty = [c for c in cols if c.endswith('_kcontracts') or c.endswith('_mnsh')]
    # 「成交金额」= 带货币单位、且不是费率、不是清算名义额的列。本表应当是 0 条。
    money = [c for c in cols
             if (c.endswith('_usd') or c.endswith('_usdbn') or 'usd' in c)
             and c not in rate and c not in notional]
    return len(money), len(qty), len(rate), len(notional)

def _split_vs_total():
    """商品合计 + 金融合计 与「衍生品总 ADV」的相对差。

    ⚠️ 搬过来时**改了 docstring**（算术一个字没动）：原文写的是
    「—— 「两套交易日」的直接证据 …… 官方分项与合计用不同的交易日归一，所以这两个数
    本来就不该逐格相等」。那是**错因果**：这个解释已被 fetch/ice.py:123-131 证伪
    （偏差最大的三个月里两列交易日恰恰相等）。官方从未说明成因，所以这里只陈述
    可核的事实 —— 分项之和与合计不是恒等式，差多少、多少个月精确相等。

    返回 (可比月数, 最大相对差%, 中位相对差%)；算不出返回 (None, None, None)。
    """
    rel = []
    try:
        with open(_CSV, encoding='utf-8') as fh:
            for r in csv.DictReader(fh):
                try:
                    c = float(r['adv_commodities_kcontracts'])
                    f = float(r['adv_financials_kcontracts'])
                    t = float(r['adv_futures_options_kcontracts'])
                except (KeyError, ValueError, TypeError):
                    continue
                if t:
                    rel.append(abs((c + f) / t - 1.0) * 100.0)
    except OSError:
        return (None,) * 3
    if not rel:
        return (None,) * 3
    rel.sort()
    return len(rel), rel[-1], rel[len(rel) // 2]

def _split_exact_months():
    """上面那组月份里，商品合计 + 金融合计与总 ADV **精确相等** 的月数。

    释义板要说的是「这不是恒等式」，而「大多数月份其实相等、少数月份不等」比只报一个
    最大相对差更能挡住误用：读者看见 121/187 就不会把偶发的不等当成解析错误去「修」。
    现算，不写死。算不出返回 None。
    """
    n = 0
    ok = False
    try:
        with open(_CSV, encoding='utf-8') as fh:
            for r in csv.DictReader(fh):
                try:
                    c = float(r['adv_commodities_kcontracts'])
                    f = float(r['adv_financials_kcontracts'])
                    t = float(r['adv_futures_options_kcontracts'])
                except (KeyError, ValueError, TypeError):
                    continue
                if t:
                    ok = True
                    n += (c + f == t)
    except OSError:
        return None
    return n if ok else None

def _shape():
    """(数据列数, 月数, 首月, 末月)；读不到返回 (None,)*4。

    2026-08-19 现算化：这四个数原先写死成「55 列，187 个月，2011-01..2026-07」，
    分散在模块 docstring 与四条图注里。**每长一个月就全体过期**，而页头那句
    「覆盖 Jan-11 – Jul-26（187 个月）」是底座现算的 —— 两处并排印在同一页上，
    下个月就会一个说 188、一个说 187。所以一个都不留，全部从 CSV 现数。
    """
    rows = _rows()
    if not rows:
        return (None,) * 4
    return (len(rows[0]) - 1, len(rows), rows[0]['month'], rows[-1]['month'])

#: 允许出现非整数的列的前缀 —— 图注那句「非整数的只有 RPC 与份额这几列」的**判据**。
_NONINT_OK = ('rpc_', 'share_')

def _nonint_census():
    """(非整数列名 list, 非整数格数)；算不出返回 ([], None)。

    「官方原表就已四舍五入到整千张 / 整百万股，只有 RPC 与份额这些列是非整数」
    —— 这句话的机器判据。列数与格数都随源表长，不写死。

    ⚠ 上一版这个函数**只数了列数、没有验列名**：图注照样印「非整数的只有 RPC 与
    份额这 N 列」，而 N 是数出来的、「只有 RPC 与份额」是人写的。哪天官方给某条
    张数列发了小数，N 会自己变成 14，那句全称断言却会继续印，而且没有任何东西会
    报错 —— 正是这一轮要消灭的那种句子。所以判据下沉到这里：**名单对不上就停机**。
    """
    rows = _rows()
    if not rows:
        return [], None
    cols = [c for c in rows[0] if c != 'month']
    names, cells = [], 0
    for c in cols:
        bad = sum(1 for r in rows
                  if (v := _num(r, c)) is not None and abs(v - round(v)) > 1e-9)
        if bad:
            names.append(c)
            cells += bad
    off = [c for c in names if not c.startswith(_NONINT_OK)]
    if off:
        raise SystemExit(
            'series/ice.csv：图注断言「非整数的只有 RPC 与份额那几列」，但 %s '
            '也有非整数格 —— 断言与数据对不上，先改图注再构建'
            '（build/ice.py 的 _nonint_census / _NONINT_OK）' % '、'.join(off))
    return names, cells

def _sum_check(children, total, tol=2.0):
    """(可比月数, 逐格精确相等的月数, 差 ≤tol 的月数)；算不出返回 (None,)*3。

    「分项之和 ≠ 合计，不要当恒等式」那条注的判据。分子分母都会随月份长，
    所以 85/187 这种写法必须现算 —— 写死的分母下个月就与页头的月数打架。
    """
    rows = _rows()
    if not rows:
        return (None,) * 3
    n = ex = near = 0
    for r in rows:
        t = _num(r, total)
        vs = [_num(r, c) for c in children]
        if t is None or any(v is None for v in vs):
            continue
        n += 1
        d = abs(sum(vs) - t)
        if d < 1e-9:
            ex += 1
        if d <= tol:
            near += 1
    return (n, ex, near) if n else (None,) * 3

#: 「四家交易所占全美现货多少」那条注要读的另外三家的列。
#: 只读不写、逐个 try —— 少了任何一家（那一页被删掉了）就退回不含数字的定性版本，
#: 本页不因为别人的文件不在而炸掉，也不因为别人多发了一个月而说假话。
_PEERS = (
    ('cboe.csv', 'adv_us_equities_matched_shares_bn', 1000.0),   # bn 股 → mn 股
    ('miax.csv', 'adv_equities_mnshares', 1.0),
)

_NDAQ = ('ndaq.csv', 'share_us_cash_matched_group')              # 已是 0–1 的份额

def _venue_mix():
    """四家自营撮合量合计占全美合并量的比例 —— 「场外化侵蚀」那条注的算术。

    **取「四家都有值的最新一个月」，现找不写死。**原先这条注把 2026-06 那次实测
    连同「（四家份额都有值的最新一个月）」这半句一起写死了；等 2026-07 四家都发齐，
    页面上那句就成了假话 —— 而它自称的判据（「最新一个月」）恰恰是**能现算**的。

    返回 dict(month, total, nyse, nyse_pct, cboe, cboe_pct, ndaq_pct,
              miax, miax_pct, four_pct, rest_pct)；算不出返回 None。
    """
    base = os.path.dirname(_CSV)
    ice = {r['month']: r for r in _rows()}
    if not ice:
        return None
    peer = {}
    for fn, col, mult in _PEERS + ((_NDAQ[0], _NDAQ[1], 1.0),):
        try:
            with open(os.path.join(base, fn), encoding='utf-8') as fh:
                peer[fn] = {r['month']: r for r in csv.DictReader(fh)}
        except OSError:
            return None
    for m in sorted(ice, reverse=True):
        tape = [_num(ice[m], 'adv_tape%s_consolidated_mnsh' % t) for t in 'ABC']
        nyse = [_num(ice[m], 'adv_nyse_tape%s_matched_mnsh' % t) for t in 'ABC']
        if any(v is None for v in tape + nyse):
            continue
        total = sum(tape)
        if not total:
            continue
        vals = {}
        for fn, col, mult in _PEERS:
            r = peer[fn].get(m)
            v = _num(r, col) if r else None
            if v is None:
                break
            vals[fn] = v * mult
        else:
            r = peer[_NDAQ[0]].get(m)
            nd = _num(r, _NDAQ[1]) if r else None
            if nd is None:
                continue
            cb, mi = vals['cboe.csv'], vals['miax.csv']
            p = dict(month=m, total=total, nyse=sum(nyse), cboe=cb, miax=mi,
                     nyse_pct=sum(nyse) / total * 100.0,
                     cboe_pct=cb / total * 100.0,
                     ndaq_pct=nd * 100.0,
                     miax_pct=mi / total * 100.0)
            p['four_pct'] = p['nyse_pct'] + p['cboe_pct'] + p['ndaq_pct'] + p['miax_pct']
            p['rest_pct'] = 100.0 - p['four_pct']
            return p
    return None

def _miax_crosscheck(k=2):
    """ICE 三 tape 合并量 vs MIAX 自报行业 ADV，最近 k 个都有值的月。

    返回 [(月, ICE 合并量, MIAX 行业量), …]（新月在前）；算不出返回 []。
    """
    base = os.path.dirname(_CSV)
    try:
        with open(os.path.join(base, 'miax.csv'), encoding='utf-8') as fh:
            mi = {r['month']: r for r in csv.DictReader(fh)}
    except OSError:
        return []
    out = []
    for r in reversed(_rows()):
        tape = [_num(r, 'adv_tape%s_consolidated_mnsh' % t) for t in 'ABC']
        m = mi.get(r['month'])
        v = _num(m, 'industry_adv_equities_mnshares') if m else None
        if any(t is None for t in tape) or v is None:
            continue
        out.append((r['month'], sum(tape), v))
        if len(out) >= k:
            break
    return out

def _ceil_to(v, nd):
    """把 v 向**上**取到 nd 位小数 —— 印「最大不超过 X」时必须这么取。

    四舍五入有一半的概率把上界取**小**，于是页面印出来的那个「最大值」比真正的
    最大值还小 —— 一句自称现算的话，被它自己现算的那列证伪。上界向上取、
    下界向下取，印出来的区间才永远含得住实测值。（这里**不举实测数字当例子**：
    举一个就等于再养一个下个月过期的数。）
    """
    f = 10.0 ** nd
    return math.ceil(v * f - 1e-9) / f

def _floor_to(v, nd):
    """`_ceil_to` 的下界孪生。

    新增，不是迁移件。理由写在 `_ceil_to` 自己的 docstring 里（「上界向上取、
    **下界向下取**，印出来的区间才永远含得住实测值」）—— 那句话说了两个方向，
    specs 里却只实现了一个方向，于是任何要印**区间**的图注（本段新增的
    `_share_ranges()` 就是）只能拿 round() 凑下界，一半的概率把下界取大，
    印出来的区间夹不住实测最小值。补上，好让那句 docstring 名副其实。
    """
    f = 10.0 ** nd
    return math.floor(v * f + 1e-9) / f

_CDS_COLS = ('cds_client_notional_usdbn', 'cds_nonclient_notional_usdbn',
             'cds_total_notional_usdbn')

def _cds_start():
    """CDS 三列共同的首月，以及它比全表首月晚多少个整年。

    ⚠ 图注原先写死「CDS 三列自 2013-01 起（比其余列晚两年）」。起点是能现算的
    （官方回补一次就左移），「晚两年」更是两个现算月份的差 —— 一个都不该抄。
    **三列首月不一致就停机**：那句话说的是「三列」，判据就得管着三列，
    否则它会在某一列被单独回补之后继续印，而没有任何东西会报错。

    返回 (首月, 晚了几年的中文, 相差月数)；算不出返回 (None, None, None)。
    """
    rows = _rows()
    if not rows:
        return (None,) * 3
    firsts = {}
    for c in _CDS_COLS:
        ms = [r['month'] for r in rows if _num(r, c) is not None]
        if ms:
            firsts[c] = ms[0]
    if len(firsts) != len(_CDS_COLS):
        return (None,) * 3
    if len(set(firsts.values())) != 1:
        raise SystemExit(
            'series/ice.csv：图注断言「CDS 三列自同一个月起」，但实际首月是 %s '
            '—— 断言与数据对不上，先改图注再构建（build/ice.py 的 _cds_start）'
            % '、'.join('%s=%s' % kv for kv in sorted(firsts.items())))
    m0 = next(iter(firsts.values()))
    y0, mo0 = (int(x) for x in rows[0]['month'].split('-'))
    y1, mo1 = (int(x) for x in m0.split('-'))
    lag = (y1 - y0) * 12 + (mo1 - mo0)
    zh = ('%d 年' % (lag // 12)) if lag % 12 == 0 else ('%d 个月' % lag)
    return m0, zh, lag

def _share_selfcheck():
    """官方给的 NYSE matched 份额 vs 本机自算 —— (可比月数, 最大 pp 差, 中位比值)。

    ⚠ 这两个数原先写死成「误差 <0.15pp」与「中位比值 = 1.000」。两个都是**实测**，
    两个都会被下一个月的读数顶开，而两个都能现算。算不出返回 (None, None, None)。
    """
    diffs, ratios = [], []
    for r in _rows():
        s = _num(r, 'share_nyse_us_cash_matched')
        tape = [_num(r, 'adv_tape%s_consolidated_mnsh' % t) for t in 'ABC']
        nyse = [_num(r, 'adv_nyse_tape%s_matched_mnsh' % t) for t in 'ABC']
        if s is None or any(v is None for v in tape + nyse) or not sum(tape):
            continue
        own = sum(nyse) / sum(tape)
        diffs.append(abs(s - own) * 100.0)
        if own:
            ratios.append(s / own)
    if not diffs:
        return (None,) * 3
    ratios.sort()
    n = len(ratios)
    med = ratios[n // 2] if n % 2 else (ratios[n // 2 - 1] + ratios[n // 2]) / 2.0
    return len(diffs), max(diffs), med

#: 缺陷 G（同一根轴上量级差几十倍，小的那条压成贴地线）的两个阈值。
#: · 8× —— docs/VISUAL_QA.md:274-290 那段「F/G 清单重出脚本」用的判据，
#:   `max(peak)/min(peak) >= 8` 才进 G 清单。本页拿它当**告警线**。
#: · 4× —— docs/VISUAL_QA.md:198-227 §7.3 实际动手拆图时取的阈值，
#:   理由是「4 落在本池实测比值 1.39× 与 11.83× 中间的空档（≈ 几何中点），
#:   比拍一个 20× 稳」。本页拿它当**该不该在图注里提醒读者「小的那条要看形状
#:   不看高度」**的线。
#: 两个都不是本页发明的，改之前先去改 VISUAL_QA.md。
G_RATIO_WARN, G_RATIO_SPLIT = 8.0, 4.0

def _peak_ratio(cols, win=WIN_FROM, rebase=False):
    """多线图的同轴量级差 —— 缺陷 G 的机器判据。

    `cols`：列名 list，或 (列名, 乘数) 的 list。乘数是给 `share_*` 这类
      「CSV 存 0–1 小数、上图 ×100」的列用的 —— 比值本身对**同一个**乘数免疫，
      但一张图里各线乘数不同时（本页没有，但 `stacked_dual` 的右轴有）就不免疫，
      所以入口留着。
    `rebase=True`：先把每条线按窗口内**第一个有限值**指数化到 100 再量。
      Ex14（两本账的单位经济，Jan-16 = 100）画的就是指数化之后的线，量原始值
      等于量错了对象 —— 那张图两条线的原始量纲（USD/张 vs USD/百股）本来就
      差两个数量级，不指数化的读数会把「已经处理掉的问题」报成缺陷。

    返回 dict(n, months, peaks=[(列名, 峰值), … 从大到小], ratio, hi, lo,
              warn=bool, split=bool)；算不出返回 None。
    """
    df = _win(_frame(), win)
    if df is None or df.empty:
        return None
    pairs = [(c, 1.0) if isinstance(c, str) else tuple(c) for c in cols]
    peaks = []
    for c, mult in pairs:
        if c not in df.columns:
            continue
        s = df[c].astype(float) * float(mult)
        s = s[np.isfinite(s)]
        if s.empty:
            continue
        if rebase:
            b = s.iloc[0]
            if not b:
                continue
            s = s / b * 100.0
        p = float(np.max(np.abs(s.values)))
        if p > 0:
            peaks.append((c, p))
    if len(peaks) < 2:
        return None
    peaks.sort(key=lambda kv: -kv[1])
    hi, lo = peaks[0], peaks[-1]
    ratio = hi[1] / lo[1]
    return dict(n=len(peaks), months=int(len(df)), peaks=peaks, ratio=ratio,
                hi=hi[0], lo=lo[0],
                warn=ratio >= G_RATIO_WARN, split=ratio >= G_RATIO_SPLIT)

#: 本页全部五条份额列。⚠️ 前四条与最后一条**分母不同**：
#: 三条 `share_nyse_tape?_matched` 的分母是**该带自己**的合并量，
#: `share_nyse_us_cash_matched` 才是三带之和除三带之和，
#: `share_nyse_equity_options` 的分母是全美期权行业 ADV。
#: 名字长得像，不能当一族读 —— 这正是 Ex17 要单独画一张的理由。
_SHARE_COLS = (
    ('share_nyse_equity_options',  '美股期权行业'),
    ('share_nyse_tapeA_matched',   'Tape A'),
    ('share_nyse_tapeB_matched',   'Tape B'),
    ('share_nyse_tapeC_matched',   'Tape C'),
    ('share_nyse_us_cash_matched', '三带合计'),
)

def _share_ranges(win=WIN_FROM, nd=1):
    """五条 share_* 在窗口内的区间 —— Ex13 / Ex16 / Ex17 图注里那几个百分数。

    ⚠️ CSV 存的是 0–1 的小数（`_share_selfcheck()` 里 `abs(s - own) * 100.0`
    那一步就是证据），**×100 之后才是页面上的百分数**。这一条踩过：份额列直接
    当百分数印出来会变成 0.1%，而读者不会怀疑一个看着像小数的份额。

    区间的两端**方向性取整**：上界 `_ceil_to`、下界 `_floor_to`，理由见
    `_ceil_to` 的 docstring。返回的 lo/hi 是取整后的（可以直接印），
    lo_raw/hi_raw 是原值（要再算就用它）。

    返回 dict(列名 → dict(zh, n, lo, hi, lo_raw, hi_raw, last, last_month,
                          lo_month, hi_month))；算不出返回 None。
    """
    df = _win(_frame(), win)
    if df is None or df.empty:
        return None
    out = {}
    for c, zh in _SHARE_COLS:
        if c not in df.columns:
            continue
        s = (df[c].astype(float) * 100.0).dropna()
        s = s[np.isfinite(s)]
        if s.empty:
            continue
        out[c] = dict(
            zh=zh, n=int(len(s)),
            lo_raw=float(s.min()), hi_raw=float(s.max()),
            lo=_floor_to(float(s.min()), nd), hi=_ceil_to(float(s.max()), nd),
            lo_month=str(s.idxmin()), hi_month=str(s.idxmax()),
            last=float(s.iloc[-1]), last_month=str(s.index[-1]))
    return out or None

#: 聚合 RPC → (子腿 RPC 列, 该子腿的量列 list)。
#: ⚠️ 两个聚合各自的子腿**共用同一套交易日**（大宗两腿都是 trading_days_commod，
#: 金融四腿全部是 trading_days_rates —— 工作表行名 "COMMODITIES & OTHER FINANCIALS"
#: 是陷阱），所以拿 ADV（日均张数）直接当权重是合法的：日数在权重的分子分母里
#: 约掉了。跨这两个聚合去混（造一条「全所 RPC」）就不合法，因此这里**只做两个聚合**。
_RPC_BLEND = {
    'rpc_commodities_usd': [
        ('rpc_energy_usd', ['adv_energy_kcontracts']),
        ('rpc_ag_metals_usd', ['adv_ag_metals_kcontracts']),
    ],
    'rpc_financials_usd': [
        ('rpc_rates_usd', ['adv_stir_kcontracts', 'adv_mltir_kcontracts']),
        ('rpc_other_financials_usd',
         ['adv_equity_index_kcontracts', 'adv_fx_credit_kcontracts']),
    ],
}

def _rpc_blend_err(win=WIN_FROM):
    """各聚合 RPC 与「子腿量加权混合」的偏差 —— Ex4 图注要报的那个数。

    Ex4 只画四条**叶子** RPC，把 `rpc_commodities` / `rpc_financials` 两条上层
    聚合挡在图外。图注得替读者回答「那两条去哪了」，而唯一诚实的答案是：
    它们**近似**是叶子的量加权混合，偏差多大现算给你看。

    ⚠️ 权重口径有两种，两种都算、都返回，让调用点显式选：
      · `mom`   —— 当月 ADV 作权重。**口径上是错配的**：`rpc_*` 是滚动三月均
        （docs/verify/verify_ice.md 的口径判定），拿单月量去配三月均费率，
        权重与被加权的东西不在同一个窗口上。
      · `roll3` —— M-2..M 三个月 ADV 均值作权重，与费率的窗口对齐。
    偏差本身就是「这两条线不是叶子的简单函数」的度量，两种权重下都报，
    读者才知道差异有多少来自权重口径、多少来自官方口径本身。

    返回 dict(聚合列名 → dict(n, mom=dict(med, med_abs, max_abs),
                              roll3=dict(...)))，单位是**相对偏差 %**；
    算不出返回 None。
    """
    df = _win(_frame(), win)
    if df is None or df.empty:
        return None
    out = {}
    for agg, legs in _RPC_BLEND.items():
        need = [agg] + [c for c, _ in legs] + [q for _, qs in legs for q in qs]
        if any(c not in df.columns for c in need):
            continue
        qty = {c: sum(df[q].astype(float) for q in qs) for c, qs in legs}
        res = dict(n=0)
        for tag in ('mom', 'roll3'):
            w = {c: (v if tag == 'mom' else v.rolling(3, min_periods=3).mean())
                 for c, v in qty.items()}
            tot = sum(w.values())
            mix = sum(df[c].astype(float) * w[c] for c, _ in legs) / tot
            rel = ((mix / df[agg].astype(float)) - 1.0) * 100.0
            rel = rel.replace([np.inf, -np.inf], np.nan).dropna()
            if rel.empty:
                continue
            res['n'] = max(res['n'], int(len(rel)))
            res[tag] = dict(med=float(rel.median()),
                            med_abs=float(rel.abs().median()),
                            max_abs=float(rel.abs().max()))
        if res.get('n'):
            out[agg] = res
    return out or None

#: OI 与其「对应 ADV」的配对。⚠️ 配对不是按列名前缀猜的：`oi_rates` 对的是
#: STIR + MLTIR 两条之和，`oi_other_financials` 对的是股指 + FX 两条之和 ——
#: 与隐含收入那四条腿的配对**完全一致**（同一份 10-K FY2025 合约数双向证伪的结果）。
#: 拿 `adv_financials` 去配 `oi_rates` 会把两条腿混在一起，相关系数会假性升高。
_OI_ADV_PAIRS = (
    ('oi_energy_kcontracts', ['adv_energy_kcontracts'], '能源'),
    ('oi_ag_metals_kcontracts', ['adv_ag_metals_kcontracts'], '农金'),
    ('oi_commodities_kcontracts', ['adv_commodities_kcontracts'], '大宗合计'),
    ('oi_rates_kcontracts', ['adv_stir_kcontracts', 'adv_mltir_kcontracts'], '利率'),
    ('oi_other_financials_kcontracts',
     ['adv_equity_index_kcontracts', 'adv_fx_credit_kcontracts'], '其他金融'),
    ('oi_financials_kcontracts', ['adv_financials_kcontracts'], '金融合计'),
)

#: 「ADV 领先 OI 几个月」要试的滞后。0 / 3 / 6 是方案定的，不是扫出来的最优 ——
#: 扫最优再报 max 是过拟合（六条序列 × 任意 lag，总能扫出一个漂亮的数）。
OI_LAGS = (0, 3, 6)

def _oi_adv_corr(win=WIN_FROM, lags=OI_LAGS, min_n=24):
    """OI 同比 与 ADV 同比 在 lag 0/3/6 的相关系数 —— 「六张 OI 并成两张」的唯一依据。

    Ex12 只画四条叶子 OI，页面因此欠一句「为什么不用六张分别画」。方案给的理由是
    「OI 同比与 ADV 同比走得差不多，另开六张是重复」。**那句话必须有数**，否则它
    只是作者的印象；而这个数一旦写死，下一次分部结构变化就会让它无声地变假。

    ⚠️ 同比一律走 `YOY.mom_yoy()`（build/yoy.py 是同比算术的唯一实现）。
    `kind` **显式传**，不让 `classify()` 替我们决定：OI 是 STOCK（点对点），
    ADV 是 FLOW —— 判反了会把 12 个月末快照加起来当「一年的量」，画出一条看着
    很正常但完全没有意义的线，而且不报错（build/yoy.py:174-198 的原话）。
    lag=k 的含义是 **ADV 领先 OI k 个月**：corr(oi_yoy[t], adv_yoy[t−k])。

    返回 dict(OI 列名 → dict(zh, n, {lag: r}, best_lag, best_r))；算不出返回 None。
    """
    df = _win(_frame(), win)
    if df is None or df.empty:
        return None
    out = {}
    for oi, advs, zh in _OI_ADV_PAIRS:
        if oi not in df.columns or any(a not in df.columns for a in advs):
            continue
        a = YOY.mom_yoy(sum(df[c].astype(float) for c in advs), kind=YOY.FLOW)
        o = YOY.mom_yoy(df[oi].astype(float), kind=YOY.STOCK)
        rs, n_used = {}, 0
        for k in lags:
            pair = pd.concat([o, a.shift(k)], axis=1).dropna()
            if len(pair) < min_n:
                continue
            n_used = max(n_used, len(pair))
            c = pair.iloc[:, 0].corr(pair.iloc[:, 1])
            if np.isfinite(c):
                rs[k] = float(c)
        if not rs:
            continue
        bk = max(rs, key=lambda k: rs[k])
        out[oi] = dict(zh=zh, n=int(n_used), r=rs, best_lag=bk, best_r=rs[bk])
    return out or None

#: 两条头条列 —— Ex2 起 Arc 1（一张合约值多少钱），Ex15 起 Arc 2（还剩多少市场）。
#: 这两条**刻意不放在同一张图上**，季节性也因此要分开报。
_HEADLINE = (
    ('adv_futures_options_kcontracts', '衍生品总 ADV'),
    ('adv_nyse_us_cash_handled_mnsh', 'NYSE 现货 handled ADV'),
)

_MON_ZH = ('1月', '2月', '3月', '4月', '5月', '6月',
           '7月', '8月', '9月', '10月', '11月', '12月')

def _season_index(win=WIN_FROM, min_years=3):
    """两条头条列的同月常态指数 —— 「这个月的高/低是季节性还是真变化」那句的依据。

    做法：值 ÷ 居中 12 个月滚动均值（去趋势），再按日历月取中位数，最后整体归一到
    均值 100。取中位数而不是均值：单月同比在本表里偶有极端值（小基数腿），
    均值会被一个 2020-03 拽走。

    ⚠️ 窗口默认吃 `WIN_FROM`（2016-01）而**不是**全表，理由不是「窗口好看」：
    本表唯一的口径断点是 2013-11（NYSE Euronext 收购完成，此前 34 个月的 NYSE
    各列是追溯并入的形式数）。第二条头条列正是 NYSE 列 —— 全表口径下会把形式数
    的季节形状混进来，而 2016-01 起的窗口整段在断点右侧，天然规避。
    ⚠️ 这是**日历月的常态**，不是预测。图注里不许写成「9 月通常会涨 X%」。

    返回 dict(列名 → dict(zh, n, years, idx={1..12}, hi=(月, 值), lo=(月, 值),
                          spread))；算不出返回 None。
    """
    df = _win(_frame(), win)
    if df is None or df.empty:
        return None
    out = {}
    for c, zh in _HEADLINE:
        if c not in df.columns:
            continue
        s = df[c].astype(float)
        # center=True + min_periods=12：窗口两端各 6 个月天然没有去趋势基准，
        # 留 NaN 而不是用短窗凑 —— 用 6 个月的均值去除 12 个月的季节性，
        # 除掉的正是要量的那个东西。
        ma = s.rolling(12, center=True, min_periods=12).mean()
        rat = (s / ma).replace([np.inf, -np.inf], np.nan).dropna()
        if rat.empty:
            continue
        mon = pd.Series(rat.index.month, index=rat.index)
        cnt = rat.groupby(mon).count()
        if len(cnt) < 12 or int(cnt.min()) < min_years:
            continue
        idx = rat.groupby(mon).median()
        idx = idx / idx.mean() * 100.0
        hi, lo = int(idx.idxmax()), int(idx.idxmin())
        out[c] = dict(zh=zh, n=int(len(rat)), years=int(cnt.min()),
                      idx={int(k): float(v) for k, v in idx.items()},
                      hi=(_MON_ZH[hi - 1], float(idx.loc[hi])),
                      lo=(_MON_ZH[lo - 1], float(idx.loc[lo])),
                      spread=float(idx.max() - idx.min()))
    return out or None

_TD_COLS = (('trading_days_commod', '大宗'),
            ('trading_days_rates', '金融'),
            ('trading_days_us_equities', '美股'))

def _tradingday_diffs():
    """三套交易日**两两**不等的月份数 —— 「不许把总 ADV 乘回成当月合计」的判据。

    替掉 specs/ice.py 的 `_tdays_split()`：那个只比了 commod vs rates 两列，
    而本表有**三套**日历（第三套 `trading_days_us_equities` 给 NYSE 两条腿用）。
    只比两列会漏掉「美股日历与另两套都不同」这种月份，而 Ex13–Ex17 整个 Arc 2
    都吃第三套。

    ⚠️ 这里量的是**事实**（有多少个月不等），不是成因。「分项之和 ≠ 合计是因为
    两套交易日不同」这个解释已被 fetch/ice.py:123-131 证伪（偏差最大的三个月里
    两列交易日恰恰相等），不许在图注里把这两件事连起来说。

    返回 dict(n, pairs={('a','b'): dict(zh, eq, ne)}, all_eq, any_ne)；
    算不出返回 None。
    """
    rows = _rows()
    if not rows:
        return None
    cols = [c for c, _ in _TD_COLS]
    zhs = dict(_TD_COLS)
    n = all_eq = any_ne = 0
    pairs = {}
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            pairs[(cols[i], cols[j])] = dict(
                zh='%s vs %s' % (zhs[cols[i]], zhs[cols[j]]), eq=0, ne=0)
    for r in rows:
        vs = [_num(r, c) for c in cols]
        if any(v is None for v in vs):
            continue
        n += 1
        ne_here = 0
        for i in range(len(cols)):
            for j in range(i + 1, len(cols)):
                k = (cols[i], cols[j])
                if vs[i] == vs[j]:
                    pairs[k]['eq'] += 1
                else:
                    pairs[k]['ne'] += 1
                    ne_here += 1
        all_eq += (ne_here == 0)
        any_ne += (ne_here > 0)
    if not n:
        return None
    return dict(n=n, pairs=pairs, all_eq=all_eq, any_ne=any_ne)

def _handled_sum_check(nd=3):
    """三条 tape handled 之和 vs `adv_nyse_us_cash_handled_mnsh` 的比值分布。

    Ex15 画的是 `adv_nyse_us_cash_handled_mnsh`（官方单列的合计），而 Ex17 讲的是
    三条 tape。读者会假设「三条加起来就是那一条」—— 这条得现算验，因为本表里
    「分项之和 = 合计」**没有一次是恒等式**（`_sum_check()` 的两组读数就是先例）。

    ⚠️ 报的是**比值**不是差：handled 量是百万股、量级随年份变几倍，
    绝对差的分布读不出「对不对得上」。

    返回 dict(n, exact, med, lo, hi, lo_month, hi_month, max_dev_pct)；
    算不出返回 None。比值已按 `nd` 位方向性取整（lo 向下、hi 向上）。
    """
    rows = _rows()
    if not rows:
        return None
    tot, rats = 0, []
    exact = 0
    lo_m = hi_m = None
    for r in rows:
        parts = [_num(r, 'adv_nyse_tape%s_handled_mnsh' % t) for t in 'ABC']
        t = _num(r, 'adv_nyse_us_cash_handled_mnsh')
        if t is None or any(v is None for v in parts) or not t:
            continue
        tot += 1
        s = sum(parts)
        exact += (abs(s - t) < 1e-9)
        rats.append((s / t, r['month']))
    if not rats:
        return None
    rats.sort()
    vals = [v for v, _ in rats]
    n = len(vals)
    med = vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2.0
    lo_m, hi_m = rats[0][1], rats[-1][1]
    return dict(n=tot, exact=exact, med=med,
                lo=_floor_to(vals[0], nd), hi=_ceil_to(vals[-1], nd),
                lo_raw=vals[0], hi_raw=vals[-1],
                lo_month=lo_m, hi_month=hi_m,
                max_dev_pct=max(abs(v - 1.0) for v in vals) * 100.0)

# ══════════════════════════════════════════════════════════════════════════════
# §3 import 期求值：图注只读这些常量，不再调函数
#
# 为什么在模块级求值而不是让每条图注自己调：这些 helper 都要扫全表，一张页十几条
# 图注各调一遍等于把 188 行扫几十遍；更要紧的是**同一个数在两条图注里必须是同一个
# 值** —— 求值一次、共享一个常量，是唯一能保证这件事的写法。
# specs/ice.py:413-430 就是这么排的，照抄。
# ══════════════════════════════════════════════════════════════════════════════
_NMONEY, _NQTY, _NRATE, _NNOT = _column_census()

_SPLITN, _SPLITMAX, _SPLITMED = _split_vs_total()

_SPLITEQ = _split_exact_months()

_CDS0, _CDSLAG_ZH, _CDSLAG = _cds_start()

_SHN, _SHMAXPP, _SHMED = _share_selfcheck()

_NCOLS, _NMONTHS, _M0, _M1 = _shape()

_NONINT_COLS, _NONINT_CELLS = _nonint_census()

_ENN, _ENEX, _ENNEAR = _sum_check(
    ['adv_brent_kcontracts', 'adv_gasoil_kcontracts', 'adv_otheroil_kcontracts',
     'adv_natgas_kcontracts', 'adv_power_kcontracts', 'adv_environmentals_kcontracts'],
    'adv_energy_kcontracts')

_FIN, _FIEX, _FINEAR = _sum_check(
    ['adv_stir_kcontracts', 'adv_mltir_kcontracts', 'adv_equity_index_kcontracts',
     'adv_fx_credit_kcontracts'], 'adv_financials_kcontracts')

_MIX = _venue_mix()

_XCHK = _miax_crosscheck()

# —— 新增的七个 ——
#: Ex4：四条叶子 RPC 同轴。`rpc_energy` 与 `rpc_other_financials` 的量级差是
#: 图注里那句「小的那条要看形状不看高度」的判据。
_PK_RPC4 = _peak_ratio(['rpc_energy_usd', 'rpc_ag_metals_usd',
                        'rpc_rates_usd', 'rpc_other_financials_usd'])

#: Ex17：三条 tape 份额（×100 上图）同轴。
_PK_TAPE = _peak_ratio([('share_nyse_tapeA_matched', 100.0),
                        ('share_nyse_tapeB_matched', 100.0),
                        ('share_nyse_tapeC_matched', 100.0)])

#: Ex14：两本账的单位经济。**必须 rebase** —— 那张图画的就是 Jan-16=100 的指数，
#: 量原始值会把 USD/张 vs USD/百股 这个已经处理掉的量纲差报成缺陷。
_PK_UNIT2 = _peak_ratio(['rpc_nyse_equity_options_usd',
                         'rpc_nyse_us_cash_usd_per100sh'], rebase=True)

#: Ex12：四条叶子 OI 同轴。
_PK_OI4 = _peak_ratio(['oi_energy_kcontracts', 'oi_ag_metals_kcontracts',
                       'oi_rates_kcontracts', 'oi_other_financials_kcontracts'])

_SHRNG = _share_ranges()

_RPCBLEND = _rpc_blend_err()

_OICORR = _oi_adv_corr()

_SEASON = _season_index()

_TDIFF = _tradingday_diffs()

_HANDLED = _handled_sum_check()

# ==========================================================================
# 【revenue】
# ==========================================================================

# -*- coding: utf-8 -*-
"""build/ice.py 的【季度隐含收入层】。

本段负责把 ICE 月度统计表里**没有的那一列**（收入）造出来：ICE 的月度表只发
量（ADV）、费率（RPC）、未平仓（OI），**一条金额列都没有**。而 ICE 自己在表内
脚注 1 里给了恒等式 `RPC = 交易收入 ÷ 合约量`，反过来就是本段做的事。

⚠️ 为什么必须是**季度**、不能是逐月 —— 这是本段最承重的一个决定。
    `rpc_*` 是**滚动三月均**（build/specs/ice.py:666、:898-899 都把这句话当口径
    权威写死了）。季末月那一格的三月窗口恰好覆盖整个季度，所以
        季度收入 = (Σ_{季内3个月} ADV_m × 交易日_m) × RPC_{季末月} ÷ 换算因子
    是一个**窗口对齐**的算法，而「逐月 ADV × 逐月 RPC 再相加」把一个三月均值
    当成了单月值用，窗口错位。
    ⚠️ 但**不许**把这件事说成「逐月形式系统性低估 1.3–2.1%」：本段
    `monthly_form_audit()` 在全部 62 季 × 6 腿 = 372 个观测上实测，逐月形式的相对
    偏差中位数 0.000%、均值 +0.093%、区间 −10.14%~+19.82% —— **全样本上并不
    系统性偏低**。可核的事实只有一条：在**唯一能与官方对账的六个点**上，逐月
    形式一律偏低（0.57%~2.15%），而季末月 RPC 形式落在 ±1.02% 内。页面上只许
    写后面这句；写前面那句，下个季度的数据就会证伪它。

⚠️ 交易日配对：ICE 有**三套**交易日（build/specs/ice.py:835-836、:1077）。
    金融的**四条腿全部**用 `trading_days_rates`。工作表行名
    "COMMODITIES & OTHER FINANCIALS" 是陷阱 —— 已被 10-K FY2025 合约数双向证伪：
      金融用 rates 日 → 985.494mn，对上 10-K 的 983（+0.25%，docs/verify/ice.md:493）
      金融用 commod 日 → 964.847mn，差 −1.85%
      能源用 commod 日 → 1255.772mn，对上 10-K 的 1256（−0.02%）
    本段 `TEN_K_FY2025` 把这条双向证伪固化成构建期断言，配错日历直接停机。

⚠️ NYSE 现货那条腿的换算因子是 **÷100，不是 ÷1000**。全量纲推导见 `_LEG_CASH`
    的注释；用错成 ÷1000 会把现货收入低估 10 倍，而且不会有任何报错。
"""

sys.path.insert(0, os.path.join(ROOT, 'build'))

# ══════════════════════════════════════════════════════════════════════
# 公共头的一小撮工具：正式合并进 build/ice.py 时**删掉本段**，直接用文件头那份。
# 这里重复一遍只是为了让本文件能 `python3 revenue.py` 独立跑起来。
# ══════════════════════════════════════════════════════════════════════
def qlab__revenue(q):
    """季度 Period → '2026-Q2'（与 cboe.py:197-203 同写法：读者能拿它回 CSV grep）。"""
    return f'{q.year}-Q{q.quarter}'

# ══════════════════════════════════════════════════════════════════════
# ① 对账状态：作为**数据结构的一部分**跟着每条腿走
# ══════════════════════════════════════════════════════════════════════
# 为什么要把它塞进腿的字典里、而不是在图注里各写一句：本页有六条腿，其中
# **只有三项**（能源 / 农金 / 金融合计）有官方数可对，另外四条是纯推导。这两
# 类必须在页面上分开说 —— 让对上的三条给对不上的四条背书，是本仓在 cost 页
# 上踩过的坑。下游任何一张图（Ex5 隐含收入、Ex7 收入结构、Ex8 bridge、Ex9
# 分腿表）要报「这个数可信到什么程度」，都从这里读，不许各写各的。
RECON_OK = 'reconciled'                    # 与 ICE 官方披露的分部交易收入直接对上

RECON_NONE = 'derived-no-official-figure'  # 推导值，官方从未单独披露过这一项

RECON_ZH = {
    RECON_OK: '已与官方披露对账',
    RECON_NONE: '推导值，无官方数可对',
}

# ══════════════════════════════════════════════════════════════════════
# ② 六条腿
# ══════════════════════════════════════════════════════════════════════
# `adv` 是**列表**：利率腿 = STIR + MLTIR，其他金融腿 = 股指 + FX/信用 —— 官方
# 只在这两个聚合层上给 RPC（rpc_rates_usd / rpc_other_financials_usd），子项各
# 自没有费率列，所以量必须先加起来再乘费率，不能各乘各的。
#
# ⚠️ `adv_fx_credit_kcontracts` 行名写着 CREDIT 但**不含信用**（specs/ice.py 口径注），
#    `adv_single_stock_kcontracts` 已被官方剔出 TOTAL FINANCIALS / ADV / RPC / OI
#    （specs/ice.py:880、:1062）—— 两者都**不进**任何一条腿。
#
# `div` 的量纲：k contracts × USD/contract = k·USD = USD ÷1000 = $mn ⇒ div=1000。
_LEG_CASH_DIV = 100.0

LEGS = [
    {
        'key': 'energy', 'zh': '能源', 'en': 'Energy futures & options',
        'adv': ['adv_energy_kcontracts'],
        'days': 'trading_days_commod',
        'rpc': 'rpc_energy_usd',
        'div': 1000.0, 'qty_unit': 'k contracts',
        'group': 'commodities', 'deriv': True,
        'recon': RECON_OK,
    },
    {
        'key': 'ag_metals', 'zh': '农产品与金属', 'en': 'Agricultural & metals futures & options',
        'adv': ['adv_ag_metals_kcontracts'],
        'days': 'trading_days_commod',
        'rpc': 'rpc_ag_metals_usd',
        'div': 1000.0, 'qty_unit': 'k contracts',
        'group': 'commodities', 'deriv': True,
        'recon': RECON_OK,
    },
    {
        # 利率 = STIR + MLTIR。⚠️ 交易日用 rates 而不是 commod —— 见模块头的双向证伪。
        'key': 'rates', 'zh': '利率', 'en': 'Interest rates',
        'adv': ['adv_stir_kcontracts', 'adv_mltir_kcontracts'],
        'days': 'trading_days_rates',
        'rpc': 'rpc_rates_usd',
        'div': 1000.0, 'qty_unit': 'k contracts',
        'group': 'financials', 'deriv': True,
        'recon': RECON_NONE,
    },
    {
        # 官方口径：Other Financials includes Equity Indices and FX（表内脚注，
        # docs/verify/verify_ice.md:163-164 复核确认）。所以是股指 + FX 两列相加。
        'key': 'other_financials', 'zh': '股指与 FX', 'en': 'Equity index & FX',
        'adv': ['adv_equity_index_kcontracts', 'adv_fx_credit_kcontracts'],
        'days': 'trading_days_rates',
        'rpc': 'rpc_other_financials_usd',
        'div': 1000.0, 'qty_unit': 'k contracts',
        'group': 'financials', 'deriv': True,
        'recon': RECON_NONE,
    },
    {
        # NYSE 股票期权：第三套交易日（美股日历），单位仍是千张。
        # ⚠️ 这条腿**不进** bridge：rpc_nyse_equity_options_usd 只有 2 位小数而量程
        #    0.04–0.18，低端一格 = 25%，58 季里 15 季（26%）费率腿同比恰为 0。
        'key': 'nyse_options', 'zh': 'NYSE 股票期权', 'en': 'NYSE equity options',
        'adv': ['adv_nyse_equity_options_kcontracts'],
        'days': 'trading_days_us_equities',
        'rpc': 'rpc_nyse_equity_options_usd',
        'div': 1000.0, 'qty_unit': 'k contracts',
        'group': 'nyse', 'deriv': False,
        'recon': RECON_NONE,
    },
    {
        # NYSE 美股现货：量的单位是 **mn shares/day**、费率是 **USD/100 shares**，
        # 所以换算因子是 100 不是 1000（推导见 _LEG_CASH_DIV 上方）。
        # ⚠️ 也正因为它的量不是「张」，它凑不进任何以张为单位的合计 —— bridge 只
        #    能落在四条千张腿上。
        'key': 'nyse_cash', 'zh': 'NYSE 美股现货', 'en': 'NYSE U.S. cash equities',
        'adv': ['adv_nyse_us_cash_handled_mnsh'],
        'days': 'trading_days_us_equities',
        'rpc': 'rpc_nyse_us_cash_usd_per100sh',
        'div': _LEG_CASH_DIV, 'qty_unit': 'mn shares',
        'group': 'nyse', 'deriv': False,
        'recon': RECON_NONE,
    },
]

LEG_BY_KEY = {g['key']: g for g in LEGS}

LEG_KEYS = [g['key'] for g in LEGS]

# bridge 的覆盖面：四条**千张**腿。量的单位打架（期权腿也是千张但费率精度不够，
# 现货腿干脆是百万股），凑不出单一可比的 Q ⇒ bridge 只能落在这四条上。
DERIV_KEYS = [g['key'] for g in LEGS if g['deriv']]

# 两条**聚合腿**：不进六腿之和，只用来做「分项之和 ≈ 合计」的闭合检查，以及 Ex6
# 对账里的「金融合计」那一项（官方 Key Metrics 只发到 Financial f&o 这一层，
# 不拆利率 / 股指FX）。⚠️ 页面上的总收入线**由六腿搭出来**，不是由这两条聚合腿
# 搭的，更不许用 adv_futures_options_kcontracts 造 —— 那一列没有对应的总费率列，
# 而且它**不等于**大宗 + 金融之和（188 个月里只有 122 个精确相等，最大差 0.531%）。
AGGS = {
    'commodities': {
        'zh': '大宗商品合计', 'en': 'Commodities',
        'adv': ['adv_commodities_kcontracts'], 'days': 'trading_days_commod',
        'rpc': 'rpc_commodities_usd', 'div': 1000.0,
        'parts': ['energy', 'ag_metals'], 'recon': RECON_OK,
    },
    'financials': {
        'zh': '金融合计', 'en': 'Financial futures & options',
        'adv': ['adv_financials_kcontracts'], 'days': 'trading_days_rates',
        'rpc': 'rpc_financials_usd', 'div': 1000.0,
        'parts': ['rates', 'other_financials'], 'recon': RECON_OK,
    },
}

# ══════════════════════════════════════════════════════════════════════
# ③ 官方数：**外部常量表**，带出处与发布日
# ══════════════════════════════════════════════════════════════════════
# 为什么写成常量而不是去抓：这六个数不在 series/ice.csv 里（那张表只有量/费率/OI），
# 来源是 ICE 另一份**财报专用**文件。抄进代码就必须把出处钉在旁边，否则半年后没人
# 说得清 595.0 是哪来的。两道构建期闸门见 `assert_official_gates()`。
OFFICIAL_SRC = 'ICE Key-Metrics-Q2-2026.xlsx（投资者关系「财务补充」文件）'

OFFICIAL_ASOF = '2026-07'   # 该文件对应的披露季度发布月（2Q26 业绩）

OFFICIAL_REF = 'docs/verify/ice.md:519-526'

# (对账项 key, 季度, 官方披露 $mn)
# 对账项 key 指向 LEG_BY_KEY 或 AGGS —— 官方只发到这三行的粒度。
OFFICIAL_REV = [
    ('energy',     pd.Period('2025Q2', 'Q'), 595.0),
    ('energy',     pd.Period('2026Q2', 'Q'), 518.0),
    ('ag_metals',  pd.Period('2025Q2', 'Q'),  65.0),
    ('ag_metals',  pd.Period('2026Q2', 'Q'),  87.0),
    ('financials', pd.Period('2025Q2', 'Q'), 158.0),
    ('financials', pd.Period('2026Q2', 'Q'), 192.0),
]

# 实测最差 ±1.02%（残差全部来自 RPC 只保留 2 位小数）。闸门放到 1.5%：够松到
# 不会被下一期的取整噪声误伤，够紧到配错交易日（−1.85%）或换算因子（10 倍）必炸。
RECON_TOL_PCT = 1.5

# 10-K FY2025「Selected Operating Data」的年度合约数（docs/verify/ice.md:490-493）。
# 这三个数是**交易日配对**的双向证伪证据，固化成构建期断言。
TEN_K_FY2025 = {'energy': 1256.0, 'ag_metals': 106.0, 'financials': 983.0}   # mn contracts

TEN_K_TOL_PCT = 1.0

# ══════════════════════════════════════════════════════════════════════
# ④ 数据加载与季度骨架
# ══════════════════════════════════════════════════════════════════════
def load__revenue(csv=CSV):
    d = pd.read_csv(csv)
    d['month'] = pd.PeriodIndex(d['month'], freq='M')
    return d.set_index('month').sort_index()

def complete_quarters(df):
    """只保留**三个月都在表里**的季度。

    ⚠️ 2026Q3 只有 7、8 两个月（CSV 到 2026-08），必须整季剔掉，**不画、也不用
    partial_months 兑水**：季末月 RPC 的三月窗口在季度没走完时根本不存在，用 8 月
    那格的 RPC 去乘两个月的量，画出来的柱既不是季度收入也不是「三分之二个季度」，
    只是一个没有口径的数。这是本页季度块五条粒度规则里的第四条。
    """
    per_q = {}
    for p in df.index:
        per_q.setdefault(p.asfreq('Q'), []).append(p)
    return [q for q in sorted(per_q) if len(per_q[q]) == 3]

def _months_of(q):
    return pd.period_range(q.asfreq('M', 'start'), q.asfreq('M', 'end'), freq='M')

# ══════════════════════════════════════════════════════════════════════
# ⑤ 量：季度合约总量
# ══════════════════════════════════════════════════════════════════════
def quarterly_contracts(df, adv_cols, day_col, quarters=None):
    """Σ_{季内3个月}( Σ_adv_cols × 该腿自己的交易日列 )。

    单位跟着 adv_cols 走：k contracts 或 mn shares。**不换算、不归一**。

    ⚠️ 交易日必须是**这条腿自己那一套**。ICE 有三套日历，各条 ADV 各归一各的
    （specs/ice.py:835-836）；也正因如此，**总 ADV 没有哪一套日历能代表**，本段
    从头到尾不去把总 ADV 乘回成当月合计（specs/ice.py:457-463 已把这条写成禁令）。
    """
    quarters = complete_quarters(df) if quarters is None else quarters
    adv = df[list(adv_cols)].sum(axis=1, min_count=len(adv_cols))
    m_contracts = adv * df[day_col].astype(float)
    out = {}
    for q in quarters:
        v = m_contracts.reindex(_months_of(q))
        # 缺任何一个月 → 整季置空。半个季度的量不是一个可读的数。
        out[q] = float(v.sum()) if v.notna().all() else np.nan
    return pd.Series(out, index=pd.PeriodIndex(quarters, freq='Q'), dtype=float)

def quarter_end_rpc(df, rpc_col, quarters=None):
    """季末月那一格的 RPC。

    这是整段的口径核心：ICE 的 RPC 是**滚动三月均**，季末月的窗口 = 该季三个月。
    ICE 的 RPC **不滞后**（与 Cboe 相反，verify_ice.md:372-374），所以季末月这格
    在季度一结束就有值，不需要像 cme/cboe 那样处理「沿用上一季费率」的外推月。
    """
    quarters = complete_quarters(df) if quarters is None else quarters
    s = df[rpc_col].astype(float)
    return pd.Series({q: float(s.get(q.asfreq('M', 'end'), np.nan)) for q in quarters},
                     index=pd.PeriodIndex(quarters, freq='Q'), dtype=float)

# ══════════════════════════════════════════════════════════════════════
# ⑥ 钱：季度隐含收入
# ══════════════════════════════════════════════════════════════════════
def quarterly_revenue(df, leg, quarters=None):
    """一条腿的季度隐含收入（$mn）。leg 可以是 LEGS 的元素、AGGS 的值，或它们的 key。"""
    if isinstance(leg, str):
        leg = LEG_BY_KEY[leg] if leg in LEG_BY_KEY else AGGS[leg]
    quarters = complete_quarters(df) if quarters is None else quarters
    qty = quarterly_contracts(df, leg['adv'], leg['days'], quarters)
    rpc = quarter_end_rpc(df, leg['rpc'], quarters)
    return qty * rpc / float(leg['div'])

def revenue_table(df, quarters=None):
    """六条腿 + 两条聚合腿 + 合计，一次算齐。

    返回 dict：
      'qty'   {key: Series}  季度合约总量（腿自己的单位）
      'rpc'   {key: Series}  季末月 RPC
      'rev'   {key: Series}  季度收入 $mn（含 'commodities'/'financials' 两条聚合腿）
      'total' Series         六腿之和 = 页面上的「隐含交易收入」
      'deriv' Series         四条千张腿之和 = bridge 的覆盖面
      'q'     PeriodIndex
    """
    quarters = complete_quarters(df) if quarters is None else quarters
    qi = pd.PeriodIndex(quarters, freq='Q')
    qty, rpc, rev = {}, {}, {}
    for spec in LEGS + list(AGGS.values()):
        k = spec.get('key') or [kk for kk, vv in AGGS.items() if vv is spec][0]
        qty[k] = quarterly_contracts(df, spec['adv'], spec['days'], quarters)
        rpc[k] = quarter_end_rpc(df, spec['rpc'], quarters)
        rev[k] = qty[k] * rpc[k] / float(spec['div'])
    total = sum(rev[k] for k in LEG_KEYS)
    deriv = sum(rev[k] for k in DERIV_KEYS)
    return {'qty': qty, 'rpc': rpc, 'rev': rev,
            'total': pd.Series(total, index=qi), 'deriv': pd.Series(deriv, index=qi),
            'q': qi}

def revenue_mix(T, keys=None, pct=True):
    """收入结构：给定几条腿，各自占这几条之和的比重。

    ⚠️ **自归一**：分母恒为「这几条腿之和」，不是别处那条总额线（照 cme.py:1200-1206
    的教训 —— 拿另一条线当分母，残差会变号，占比就不再是占比）。
    """
    keys = list(keys or LEG_KEYS)
    den = sum(T['rev'][k] for k in keys)
    f = 100.0 if pct else 1.0
    return {k: T['rev'][k] / den * f for k in keys}

# ══════════════════════════════════════════════════════════════════════
# ⑦ 构建期闸门
# ══════════════════════════════════════════════════════════════════════
def assert_cash_factor():
    """把现货腿的 ÷100 钉死。

    这道断言存在的唯一理由：÷1000 是本文件里另外五条腿的因子，手一滑改成 1000
    不会有任何报错，只会让现货收入静静地少一个数量级、并让 Ex7 的结构图整体走形。
    """
    assert LEG_BY_KEY['nyse_cash']['div'] == 100.0, (
        'NYSE 现货腿的换算因子必须是 100：mn shares × USD/100shares → $mn 的净因子是 '
        '1e4/1e6 = 1/100。写成 1000 会把现货收入低估 10 倍。')
    for k in LEG_KEYS:
        if k != 'nyse_cash':
            assert LEG_BY_KEY[k]['div'] == 1000.0, f'{k} 的换算因子应为 1000（k contracts × USD → $mn）'

def assert_trading_day_pairing(df):
    """用 10-K FY2025 的年度合约数双向证伪交易日配对。

    正向：按本表的配对算 FY2025 合约数，三项都要落在 ±1%。
    反向：把金融腿换成 commod 日历，必须**对不上**（实测 −1.85%）—— 否则说明这道
    断言根本没有分辨力，那它就不该留在这里。
    """
    y = [p for p in df.index if p.year == 2025]
    out = {}
    for k, spec in [('energy', LEG_BY_KEY['energy']), ('ag_metals', LEG_BY_KEY['ag_metals']),
                    ('financials', AGGS['financials'])]:
        adv = df.loc[y, spec['adv']].sum(axis=1)
        out[k] = float((adv * df.loc[y, spec['days']].astype(float)).sum()) / 1000.0  # k → mn
        rel = out[k] / TEN_K_FY2025[k] * 100.0 - 100.0
        assert abs(rel) <= TEN_K_TOL_PCT, (
            f'交易日配对错：{k} FY2025 合约数 {out[k]:.3f}mn vs 10-K {TEN_K_FY2025[k]}mn（{rel:+.2f}%）')
    # 反向：金融用 commod 日历必须落在容差之外
    adv = df.loc[y, AGGS['financials']['adv']].sum(axis=1)
    wrong = float((adv * df.loc[y, 'trading_days_commod'].astype(float)).sum()) / 1000.0
    rel_w = wrong / TEN_K_FY2025['financials'] * 100.0 - 100.0
    assert abs(rel_w) > TEN_K_TOL_PCT, (
        '反向证伪失效：金融腿改用 trading_days_commod 竟然也对得上 10-K，'
        '说明这道断言分辨不出配对错误，不要留一个假的护栏在这里。')
    out['financials_wrong_commod_days'] = wrong
    return out

def reconcile(T):
    """六项官方对账：本页推导 vs ICE 披露。返回 Ex6 直接可用的行。"""
    rows = []
    for key, q, official in OFFICIAL_REV:
        spec = LEG_BY_KEY.get(key) or AGGS[key]
        ours = float(T['rev'][key].get(q, np.nan))
        rows.append({
            'key': key, 'zh': spec['zh'], 'en': spec['en'], 'q': q, 'qlab__revenue': qlab__revenue(q),
            'ours': ours, 'official': official,
            'rel_pct': ours / official * 100.0 - 100.0 if official else np.nan,
        })
    return rows

def assert_official_gates(df, T):
    """官方常量表的两道构建期闸门。

    闸门①（**存在性**）：常量表点到的每一个季度都必须仍在本页算得出的完整季度里。
      CSV 哪天被截短、或季度完整性判据被人改松，这张手抄的表就会静静地指向空气 ——
      那时页面上会印出一排「本页推导 = 空」对「官方 595.0」，读者只会以为数据坏了。
    闸门②（**一致性**）：六项相对差全部 ≤ RECON_TOL_PCT。这道拦的是配错交易日
      （−1.85%）、用错换算因子（10 倍）、或把季末月 RPC 换成别的月份这类**回归**。
    """
    have = set(T['q'])
    miss = [(k, qlab__revenue(q)) for k, q, _ in OFFICIAL_REV if q not in have]
    assert not miss, (
        f'官方对账常量表指向了本页算不出的季度 {miss} —— 要么 series/ice.csv 被截短了，'
        f'要么完整季度判据被改动。常量表出处：{OFFICIAL_SRC}（{OFFICIAL_REF}）')
    rows = reconcile(T)
    bad = [r for r in rows if not np.isfinite(r['rel_pct']) or abs(r['rel_pct']) > RECON_TOL_PCT]
    assert not bad, (
        '官方对账超容差：' + '；'.join(f"{r['zh']} {r['qlab__revenue']} 本页 {r['ours']:.1f} vs 官方 "
                                     f"{r['official']:.1f}（{r['rel_pct']:+.2f}%）" for r in bad))
    return rows

def closure_stats(T):
    """(能源+农金) vs 大宗商品合计、(利率+其他金融) vs 金融合计 的季度相对差分布。

    ⚠️ 这里量的是**加总近似性**，残差来源是 RPC 只有 2 位小数 —— **不是口径错配**。
    页面上不许把它写成「分项之和 ≠ 合计」的那个成因：那件事官方从未说明，而
    「两套交易日各归一各的」这个解释已被 fetch/ice.py:123-131 证伪（偏差最大的三个
    月里两列交易日恰恰相等）。这里只陈述可核的数。
    """
    out = {}
    for agg, spec in AGGS.items():
        parts = sum(T['rev'][k] for k in spec['parts'])
        rel = (parts / T['rev'][agg] * 100.0 - 100.0).dropna()
        out[agg] = {
            'zh': spec['zh'], 'parts_zh': [LEG_BY_KEY[k]['zh'] for k in spec['parts']],
            'n': int(rel.size),
            'median': float(np.median(np.abs(rel))),
            'p90': float(np.percentile(np.abs(rel), 90)),
            'max': float(np.max(np.abs(rel))),
            'max_at': qlab__revenue(rel.abs().idxmax()),
            'over1': int((rel.abs() > 1.0).sum()),
            'over2': int((rel.abs() > 2.0).sum()),
        }
    return out

# ══════════════════════════════════════════════════════════════════════
# ⑧ 逐月形式的对照 —— 为什么排除它
# ══════════════════════════════════════════════════════════════════════
def monthly_revenue_alt(df, leg, quarters=None):
    """**被排除的**那个形式：Σ_月( ADV_m × 交易日_m × RPC_m )。只用于对照，不上页面。"""
    if isinstance(leg, str):
        leg = LEG_BY_KEY[leg] if leg in LEG_BY_KEY else AGGS[leg]
    quarters = complete_quarters(df) if quarters is None else quarters
    adv = df[leg['adv']].sum(axis=1, min_count=len(leg['adv']))
    m = adv * df[leg['days']].astype(float) * df[leg['rpc']].astype(float) / float(leg['div'])
    out = {}
    for q in quarters:
        v = m.reindex(_months_of(q))
        out[q] = float(v.sum()) if v.notna().all() else np.nan
    return pd.Series(out, index=pd.PeriodIndex(quarters, freq='Q'), dtype=float)

def monthly_form_audit(df, T):
    """两组读数，**必须分开报**：

    ① 六个可对账点上：逐月形式 vs 官方 —— 实测一律偏低。这句话可核。
    ② 全样本 62 季 × 6 腿：逐月形式 vs 季末月形式的相对差分布 —— 实测**不**系统性偏低。
       所以页面上只许说 ①，不许把 ① 的幅度推广成一句关于全样本的话。
    """
    quarters = list(T['q'])
    at_recon = []
    for key, q, official in OFFICIAL_REV:
        alt = float(monthly_revenue_alt(df, key, quarters).get(q, np.nan))
        ours = float(T['rev'][key].get(q, np.nan))
        at_recon.append({
            'zh': (LEG_BY_KEY.get(key) or AGGS[key])['zh'], 'qlab__revenue': qlab__revenue(q),
            'official': official, 'qend': ours, 'monthly': alt,
            'qend_rel': ours / official * 100.0 - 100.0,
            'monthly_rel': alt / official * 100.0 - 100.0,
        })
    diffs = []
    for k in LEG_KEYS:
        alt = monthly_revenue_alt(df, k, quarters)
        rel = (alt / T['rev'][k] * 100.0 - 100.0).replace([np.inf, -np.inf], np.nan).dropna()
        diffs.append(rel)
    allrel = pd.concat(diffs)
    return {
        'at_recon': at_recon,
        'n_obs': int(allrel.size),
        'median': float(np.median(allrel)),
        'mean': float(np.mean(allrel)),
        'min': float(np.min(allrel)),
        'max': float(np.max(allrel)),
        'share_below': float((allrel < 0).mean() * 100.0),
    }

# ══════════════════════════════════════════════════════════════════════
# ⑨ 覆盖区间 / 完整性
# ══════════════════════════════════════════════════════════════════════
def coverage(df, T):
    """每条腿的覆盖区间与洞，外加被剔掉的不完整季。"""
    allq = complete_quarters(df)
    per_q = {}
    for p in df.index:
        per_q.setdefault(p.asfreq('Q'), []).append(p)
    partial = [(qlab__revenue(q), len(per_q[q])) for q in sorted(per_q) if len(per_q[q]) != 3]
    legs = {}
    for k in LEG_KEYS + list(AGGS):
        s = T['rev'][k]
        ok = s.dropna()
        legs[k] = {
            'zh': (LEG_BY_KEY.get(k) or AGGS[k])['zh'],
            'first': qlab__revenue(ok.index[0]) if len(ok) else None,
            'last': qlab__revenue(ok.index[-1]) if len(ok) else None,
            'n': int(ok.size), 'holes': int(s.size - ok.size),
            'recon': (LEG_BY_KEY.get(k) or AGGS[k])['recon'],
        }
    return {'n_complete_q': len(allq),
            'first': qlab__revenue(allq[0]), 'last': qlab__revenue(allq[-1]),
            'partial': partial, 'legs': legs}

# ══════════════════════════════════════════════════════════════════════
# ⑩ 下游要用的现算读数（图注里的覆盖率必须现算，不许写死）
# ══════════════════════════════════════════════════════════════════════
def bridge_coverage(T, q=None):
    """bridge 覆盖面 = 四条千张腿占六腿合计的比重（图注要现算印出来）。"""
    q = q if q is not None else T['q'][-1]
    tot = float(T['total'].get(q, np.nan))
    dv = float(T['deriv'].get(q, np.nan))
    return {
        'qlab__revenue': qlab__revenue(q), 'total': tot, 'deriv': dv,
        'cover_pct': dv / tot * 100.0,
        'energy_of_deriv_pct': float(T['rev']['energy'].get(q, np.nan)) / dv * 100.0,
        'energy_of_total_pct': float(T['rev']['energy'].get(q, np.nan)) / tot * 100.0,
        'legs': {k: float(T['rev'][k].get(q, np.nan)) for k in LEG_KEYS},
    }

def build(df=None, csv=CSV):
    """本段的唯一入口：算齐 + 跑完所有构建期闸门，返回下游全部要用的东西。"""
    df = load__revenue(csv) if df is None else df
    assert_cash_factor()
    tdays = assert_trading_day_pairing(df)
    quarters = complete_quarters(df)
    T = revenue_table(df, quarters)
    recon = assert_official_gates(df, T)
    return {
        'df': df, 'T': T, 'quarters': quarters,
        'recon': recon, 'closure': closure_stats(T),
        'coverage': coverage(df, T), 'tenk': tdays,
        'mix6': revenue_mix(T, LEG_KEYS), 'mix4': revenue_mix(T, DERIV_KEYS),
        'bridge_cov': bridge_coverage(T),
    }

# ==========================================================================
# 【bridge】
# ==========================================================================

# -*- coding: utf-8 -*-
"""build/ice.py 的一段：Exhibit「量/费率分解」（`bridge_bar`，LMDI 对数分解按算术总额重标定）。

本文件是**分段草稿**，正式合并进 build/ice.py 时：
  · 顶部的 import / 路径常量由页面统一那一份代替（契约里逐字冻结的那 20 行）；
  · `mlab / qlab__bridge / L / nz / pctf / pp` 由页面的公共小工具段提供，这里的同名实现删掉；
  · `_legs_quarterly()` 是**自测桩**，正式版由「隐含收入」那一段提供的季度腿表代替
    （见文件末尾 INTERFACES 注释）；
  · `build_bridge()` 的函数体原样摊平成模块级代码（cme/cboe 两页都是线性脚本）。

━━ 这张图为什么长这样 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
数学与护栏逐条对齐 build/cme.py:1424-1497 与 build/cboe.py:1694-1740，两页做法完全
一致，**只有分桶不同**：cme 是「当月 vs 去年同月」、cboe 是「日历年 vs 上一年」，
ICE 是「季度 vs 去年同季度」。ICE 只能按季度，理由不在图型而在数据：
`rpc_*` 是**滚动三月均**，季末月那一格的窗口恰好覆盖该季度 —— 逐月形式在唯一能与官方
对账的六个点上一律偏低 0.57–2.15%，而季末月形式落在 ±1.02% 内。
（注意：全样本上逐月形式并**不**系统性偏低，中位 0.000%、区间 −10.14%~+19.82%；
  页面上只许写「在能对账的六个点上逐月形式一致偏低」这句可核的话。）

覆盖面**只能是衍生品那四条腿**（能源 / 农金 / 利率 / 股指FX），不是六腿合计：
桥需要一个可比的 Q，而四条衍生品腿与 NYSE 期权腿的量是**千张**、NYSE 现货腿是
**百万股**，六腿凑不出单一的量纲。四条腿现算占隐含总收入的比重印进图注。
NYSE 期权腿**单独**的桥也放弃：`rpc_nyse_equity_options_usd` 只有 2 位小数而量程
0.04–0.18，低端一格 = 25%，58 季里 15 季（26%）费率腿同比恰为 0、交叉项最大 36.99pp
—— 那不是分解图，是舍入噪声图。（这两件事本文件的自测块会现算出来，不照抄。）

对账身份要说清楚、不许互相背书：桥覆盖的四腿之和 == 能源 + 农金 + **金融合计**，
而这三个桶正是与 ICE Key-Metrics-Q2-2026 对上的那三个（6 项、最差 ±1.02%，
docs/verify/ice.md:519-526）。**利率 / 其他金融各自**没有官方数可对，桥只用它们的合计。
"""

# 分段草稿跑在 scratchpad 里，仓库根写死；合并后由页面统一的 ROOT__bridge / CSV 代替。
ROOT__bridge = '/Users/hzhan/Documents/monthly-op-dashboards/.claude/worktrees/cboe-page-redesign-dc42f8'

EX_BRIDGE = 8            # 合并后走页面的 EX_* 常量，图注里一律按标题指代、不印字面编号

EX_REV = 5               # 隐含收入那张（图注要说「菱形与它的同比线是同一条数」）

EX_REVMIX = 7            # 收入结构那张（费率腿里的 mix 位移指过去）

EX_RPC = 4               # 每张收入 RPC 那张

def qlab__bridge(q):
    """季度 Period → '2026-Q2'（照 cme.py:197-203：与费率表 period 写法一致，可直接 grep）。"""
    return f'{q.year}-Q{q.quarter}'

# ══ 分解常量（与 build/single.py 的 DECOMP_EPS 同值同义）════════════════════
DEC_EPS = 1e-9      # 三道闭合残差硬上限；超了直接停机，不出一张「两块加起来不等于总数」的图

DEC_LN_MIN = 1e-6   # |ln(V₁/V₀)| 低于它整根柱留空（重标定权重 w 数值上是 0/0）

def bridge_split(V1, V0, Q1, Q0):
    """LMDI：把收入总增长拆成量腿与价腿两块，**两块相加逐格等于算术总增长**。

    返回 dict：
        g_v / g_q / g_p  算术同比（比值，不是 %）
        cross            算术交叉项 g_q·g_p（比值）—— **不进图**，只进图注
        w                重标定权重 g_v ÷ ln(V₁/V₀)；退化时 nan
        qty_pp / rate_pp 画在图上的那两块（**百分点**）；退化时 nan
        ln_v / p1 / p0   给调用方报「最接近留空线的一格」与「隐含费率读数」用

    为什么画对数分解而不是算术分解（cme.py:1413-1417 原话）：
    ln(V₁/V₀) = ln(Q₁/Q₀) + ln(P₁/P₀) 天然可加、**没有交叉项**；算术分解
    g_V = g_Q + g_P + g_Q·g_P 的交叉项必须整段压给某一腿，压给谁都会改读数。
    乘上 w 只是把「对数点」换算回百分点，w 对量与价一视同仁、不含任何分配假设。

    ⚠️ **P 是反算出来的，不是已披露的季末 RPC**：P = V ÷ Q，而 V 的每一条腿各乘各的
    已披露费率、Q 是各腿张数之和 —— 所以 P 是四条腿费率按**当季张数结构**加权的混合值。
    两年的结构不同 ⇒ 即使每条腿的费率一格不动，g_p 也会因为 mix 位移而不为零。
    这件事必须在图注里说破（调用方现算 mix 分量印出来）。
    """
    if not (np.isfinite(V1) and np.isfinite(V0) and np.isfinite(Q1) and np.isfinite(Q0)):
        raise ValueError('bridge_split 收到非有限输入 —— 缺值格该在调用方走留空分支')
    if not (V1 > 0 and V0 > 0 and Q1 > 0 and Q0 > 0):
        raise ValueError(f'bridge_split 要求四个量都为正：V1={V1} V0={V0} Q1={Q1} Q0={Q0}')

    P1, P0 = V1 / Q1, V0 / Q0
    g_v, g_q, g_p = V1 / V0 - 1.0, Q1 / Q0 - 1.0, P1 / P0 - 1.0
    cross = g_q * g_p
    ln_v = float(math.log(V1 / V0))
    ln_q = float(math.log(Q1 / Q0))
    ln_p = float(math.log(P1 / P0))

    # 硬护栏①：算术分解闭合（三项，含交叉项）。残差只应是 float64 舍入（~1e-16）。
    if not abs(g_v - (g_q + g_p + cross)) <= DEC_EPS:
        raise SystemExit(f'量价分解：算术分解不闭合，残差 {g_v - (g_q + g_p + cross):+.3e} '
                         f'> {DEC_EPS:.0e}')
    # 硬护栏②：对数分解闭合（本来就该零残差，没有交叉项）。
    if not abs(ln_v - (ln_q + ln_p)) <= DEC_EPS:
        raise SystemExit(f'量价分解：对数分解不闭合，残差 {ln_v - (ln_q + ln_p):+.3e} '
                         f'> {DEC_EPS:.0e}')

    out = {'g_v': g_v, 'g_q': g_q, 'g_p': g_p, 'cross': cross,
           'w': np.nan, 'qty_pp': np.nan, 'rate_pp': np.nan,
           'ln_v': ln_v, 'p1': P1, 'p0': P0}
    if abs(ln_v) < DEC_LN_MIN:
        # 整根柱留空：w = g_v/ln(V₁/V₀) 此时是 0/0，两个小量都由大数相减得来、
        # 有效位被吃光，算出来的两块没有一位是可信的。宁可不画，不印一个假的分解。
        return out
    w = g_v / ln_v
    q_pp, r_pp = w * ln_q * 100.0, w * ln_p * 100.0
    # 硬护栏③：**画在图上的那两块**相加 == 总增长（图型的全部意义，
    # docs/CHART_KINDS.md:517「net 与 Σstacks 对不上时引擎不会告诉你，Python 侧要断言」）。
    if not abs(g_v * 100.0 - (q_pp + r_pp)) <= DEC_EPS:
        raise SystemExit(f'量价分解：重标定后不闭合，残差 {g_v * 100.0 - (q_pp + r_pp):+.3e} '
                         f'> {DEC_EPS:.0e}')
    out['w'], out['qty_pp'], out['rate_pp'] = w, q_pp, r_pp
    return out

def bridge_rows(qtrs, V, Q, tag=''):
    """一条腿（或一组腿的合计）的整串桥：季度 vs **去年同季度**。

    qtrs  可画的季度序列（Period[Q]，完整季，已按时间排好）
    V / Q dict 或 Series：季度 → 收入($mn) / 张数（同一量纲，桥内部只用比值）
    返回 rows：每季一条，含 lab / q / V1..P0 / 分解结果 / blank 标记。
    两侧任一缺值 → 该格 blank 且 gap=True（净额与两段必须**同空**，
    否则菱形没了柱子还在，读者会当成「净额为 0」，护栏④会核这件事）。
    """
    rows = []
    for q in qtrs:
        q0 = q - 4                      # 去年同季度
        v1, v0 = V.get(q, np.nan), V.get(q0, np.nan)
        s1, s0 = Q.get(q, np.nan), Q.get(q0, np.nan)
        lab = qlab__bridge(q)
        ok = all(np.isfinite(x) for x in (v1, v0, s1, s0)) and \
            v1 > 0 and v0 > 0 and s1 > 0 and s0 > 0
        if not ok:
            rows.append({'lab': lab, 'q': q, 'gap': True, 'blank': True,
                         'V1': v1, 'V0': v0, 'Q1': s1, 'Q0': s0,
                         'w': np.nan, 'qty_pp': np.nan, 'rate_pp': np.nan})
            continue
        try:
            d = bridge_split(float(v1), float(v0), float(s1), float(s0))
        except SystemExit as e:
            raise SystemExit(f'{tag}{lab}：{e}')
        row = {'lab': lab, 'q': q, 'gap': False,
               'blank': not np.isfinite(d['w']),
               'V1': float(v1), 'V0': float(v0), 'Q1': float(s1), 'Q0': float(s0)}
        row.update(d)
        rows.append(row)
    return rows

# ══ 自测桩：季度腿表 ═══════════════════════════════════════════════════════
# 正式合并时**整块删掉**，由「隐含收入」那一段提供 REV_Q / VOL_Q（见文末 INTERFACES）。
# 口径（冻结）：季度收入($mn) = Σ_{季内3个月}(ADV × 该腿对应的交易日列) × **季末月**的 RPC ÷ 换算因子。
# 三套交易日各归一各的（trading_days_commod / _rates / _us_equities）：
# 「金融四条腿全部用 trading_days_rates」已用 10-K FY2025 合约数双向证伪，
# 工作表行名 "COMMODITIES & OTHER FINANCIALS" 是陷阱，不要照它分。
LEG_DEFS = [
    # key,        中文,        ADV 列,                                        交易日列,                  RPC 列,                            换算因子, 量纲, 进桥
    ('energy',    '能源',      ['adv_energy_kcontracts'],                     'trading_days_commod',     'rpc_energy_usd',                   1000.0, 'k',  True),
    ('ag_metals', '农金',      ['adv_ag_metals_kcontracts'],                  'trading_days_commod',     'rpc_ag_metals_usd',                1000.0, 'k',  True),
    ('rates',     '利率',      ['adv_stir_kcontracts', 'adv_mltir_kcontracts'], 'trading_days_rates',    'rpc_rates_usd',                    1000.0, 'k',  True),
    ('other_fin', '其他金融',  ['adv_equity_index_kcontracts', 'adv_fx_credit_kcontracts'], 'trading_days_rates', 'rpc_other_financials_usd', 1000.0, 'k',  True),
    ('nyse_opt',  'NYSE期权',  ['adv_nyse_equity_options_kcontracts'],        'trading_days_us_equities', 'rpc_nyse_equity_options_usd',     1000.0, 'k',  False),
    # ⚠️ 现货腿的因子是 **1/100 不是 1/1000**：mn shares/day × day = mn shares，
    #    ×1e6 = shares，÷100 = 百股，× USD/100shares = USD，÷1e6 = $mn ⇒ 净因子 1/100。
    #    写成 ÷1000 会把现货收入低估 10 倍。
    ('nyse_cash', 'NYSE现货',  ['adv_nyse_us_cash_handled_mnsh'],             'trading_days_us_equities', 'rpc_nyse_us_cash_usd_per100sh',    100.0, 'mnsh', False),
]

BRIDGE_KEYS = [k for k, *_ , inb in LEG_DEFS if inb]

def _legs_quarterly(df):
    """自测桩 → (VQ, QQ, RPCQ, QTRS)：季度收入($mn) / 季度量 / 季末月 RPC / 完整季列表。"""
    per = df.index                      # Period[M]
    qs = per.asfreq('Q')
    # 完整季 = 该季三个月在 CSV 里都在。2026Q3 只有 7、8 两个月 ⇒ 自动落选，
    # 这是「不完整季不画、也不用 partial_months」那条规则的执行点。
    cnt = pd.Series(1, index=per).groupby(qs).sum()
    QTRS = [q for q in cnt.index if cnt[q] == 3]

    VQ, QQ, RPCQ = {}, {}, {}
    for key, zh, advs, dcol, rcol, fac, unit, inb in LEG_DEFS:
        adv = sum(df[c].astype(float) for c in advs)
        vol_m = adv * df[dcol].astype(float)          # 当月合计（张数 k / 百万股）
        vol_q = vol_m.groupby(qs).sum()
        rpc_q = df[rcol].astype(float).groupby(qs).last()   # 季末月那一格
        VQ[key] = {q: float(vol_q[q]) * float(rpc_q[q]) / fac for q in QTRS}
        QQ[key] = {q: float(vol_q[q]) for q in QTRS}
        RPCQ[key] = {q: float(rpc_q[q]) for q in QTRS}
    return VQ, QQ, RPCQ, QTRS

# ══ 图 payload ═════════════════════════════════════════════════════════════
def build_bridge(VQ, QQ, RPCQ, QTRS, ex_bridge=EX_BRIDGE):
    """→ (exhibit dict, BRIDGE_CHECK 文本, stats dict)。

    桥的 V/Q 是**四条衍生品腿的合计**（全是千张，量纲可加）。
    """
    keys = BRIDGE_KEYS
    zh_of = {k: zh for k, zh, *_ in LEG_DEFS}

    # 窗口：左端由 WIN_FROM 换算成季度（Q_FROM），右端是最后一个完整季。
    QW = [q for q in QTRS if q >= Q_FROM and (q - 4) in set(QTRS)]
    if not QW:
        raise SystemExit(f'Exhibit {ex_bridge}：{qlab__bridge(Q_FROM)} 起没有一个两侧都齐的季度')

    Vsum = {q: sum(VQ[k][q] for k in keys) for q in QTRS}
    Qsum = {q: sum(QQ[k][q] for k in keys) for q in QTRS}
    rows = bridge_rows(QW, Vsum, Qsum, tag=f'Exhibit {ex_bridge} ')

    xl = [r['lab'] for r in rows]
    dq = [r['qty_pp'] for r in rows]
    dp = [r['rate_pp'] for r in rows]
    dnet = [(r['g_v'] * 100.0 if not r['blank'] else np.nan) for r in rows]
    blanks = [r['lab'] for r in rows if r['blank'] and not r['gap']]
    gaps = [r['lab'] for r in rows if r['gap']]
    fin = [r for r in rows if np.isfinite(r['qty_pp'])]
    if not fin:
        raise SystemExit(f'Exhibit {ex_bridge}：{len(xl)} 根柱全部留空，没有一根画得出来')

    # 硬护栏④：**写进 payload 的那组数**（round 到 6 位后）也要闭合；留空柱两段必须同空。
    for i, (xn, xq, xp) in enumerate(zip(L(dnet), L(dq), L(dp))):
        if xn is None:
            if xq is not None or xp is not None:
                raise SystemExit(f'Exhibit {ex_bridge} {xl[i]} 净额留空但堆叠段有值 —— '
                                 f'菱形不见了、柱子还在，读者会当成「净额为 0」')
            continue
        if not abs((xq + xp) - xn) <= 2e-6:
            raise SystemExit(f'Exhibit {ex_bridge} {xl[i]} 写进 payload 的两块相加 '
                             f'{xq + xp:.9f} ≠ 净额 {xn:.9f}')

    # 末柱必须是**画得出来**的那一根：图注与 BRIDGE_CHECK 都印「末柱的算术读数」，
    # 缺值柱与留空柱都会进 rows，只比标签挡不住（照 cme.py:1586-1594 那道闸门）。
    last = rows[-1]
    if last['lab'] != xl[-1] or not np.isfinite(last['qty_pp']):
        raise SystemExit(f'Exhibit {ex_bridge}：末柱必须是画得出来的那一根，'
                         f'横轴末格 {xl[-1]}、rows 末条 {last["lab"]}、量腿 {last["qty_pp"]}')

    # ── 印给读者的统计，一律在**画得出来**的那些柱上算 ──────────────────
    # 留空柱的 |g_v| ≈ 0，拿它算「交叉项占净增长」会得到几十万个百分点，
    # 而那一柱图上根本没有东西（cme.py:1511-1513 记着这个坑）。
    x_pp = [abs(r['cross']) * 100 for r in fin]
    CROSS_MED, CROSS_MAX = float(np.median(x_pp)), float(max(x_pp))
    CROSS_AT = max(fin, key=lambda r: abs(r['cross']))['lab']
    far = [r for r in fin if abs(r['g_v']) >= 0.05]     # |净增长| ≥ 5% 才有可靠分母
    CROSS_SH_FAR = float(max(abs(r['cross'] / r['g_v']) * 100 for r in far)) if far else float('nan')
    OPP_N = sum(1 for r in fin if r['qty_pp'] * r['rate_pp'] < 0)
    W_LO, W_HI = float(min(r['w'] for r in fin)), float(max(r['w'] for r in fin))
    NET_LO = float(min(r['g_v'] for r in fin)) * 100
    NET_HI = float(max(r['g_v'] for r in fin)) * 100
    # w 不是 1 ⇒ **深蓝段不是原始量同比**。最大差现算（照 cme.py:1568）。
    LOG_GAP = max(abs(r['g_q'] * 100 - r['qty_pp']) for r in fin)
    LOG_GAP_AT = max(fin, key=lambda r: abs(r['g_q'] * 100 - r['qty_pp']))['lab']
    # 最接近留空线的一柱（在**全部** rows 上算：它问的正是「有没有柱快要留空了」）。
    lv_rows = [r for r in rows if not r['gap'] and np.isfinite(r.get('ln_v', np.nan))]
    lv_row = min(lv_rows, key=lambda r: abs(r['ln_v']))
    LV_MIN, LV_MIN_AT = abs(float(lv_row['ln_v'])), lv_row['lab']

    # ── 费率腿里有多少是 mix、有多少是费率本身 ────────────────────────────
    # P 是四条腿已披露费率按**当季张数结构**加权的混合值，两年结构不同 ⇒ 即使每条腿
    # 费率一格不动，g_p 也会动。用「本期结构 × 基期费率」这个反事实把两者分开：
    #   mix 分量 = P_fixed/P0 − 1（结构位移，费率按基期）
    #   纯费率   = P1/P_fixed − 1
    mix_rows = []
    for r in fin:
        q1, q0 = r['q'], r['q'] - 4
        w1 = {k: QQ[k][q1] for k in keys}
        p_fixed = sum(w1[k] * RPCQ[k][q0] for k in keys) / sum(w1.values())
        p_fixed /= 1000.0                      # $/张 → 与 p1/p0（$mn ÷ k张）同标度
        mix_rows.append({'lab': r['lab'], 'q': q1,
                         'mix': p_fixed / r['p0'] - 1.0,
                         'pure': r['p1'] / p_fixed - 1.0, 'gp': r['g_p']})
    MIX_MAX = max(mix_rows, key=lambda d: abs(d['mix']))
    MIX_MED = float(np.median([abs(d['mix']) for d in mix_rows])) * 100
    PURE_MED = float(np.median([abs(d['pure']) for d in mix_rows])) * 100
    # ⚠️ 实测：mix 分量**并不**总是压过纯费率（现算 16/42），所以图注里不许写
    # 「费率腿主要是结构位移」——那是句会被下个季度证伪的话。只报可核的计数。
    MIX_WINS = sum(1 for d in mix_rows if abs(d['mix']) > abs(d['pure']))
    MIX_LAST = mix_rows[-1]
    # 末柱各腿的已披露费率同比 —— 图注要点名「哪几条腿的费率其实在涨」，
    # 这句话必须由数据现算：2026-Q2 农金那条腿是 2.26 → 2.25（跌一格），
    # 写「每条腿都没降」就是假话（构建期实测抓到过）。
    _ql = last['q']
    RPC_LEG_TXT = '、'.join(
        f'{zh_of[k]} {RPCQ[k][_ql - 4]:.2f}→{RPCQ[k][_ql]:.2f}'
        for k in keys)
    RPC_UP_N = sum(1 for k in keys if RPCQ[k][_ql] > RPCQ[k][_ql - 4])
    RPC_DN_N = sum(1 for k in keys if RPCQ[k][_ql] < RPCQ[k][_ql - 4])
    RPC_FL_N = len(keys) - RPC_UP_N - RPC_DN_N
    # 「纯费率与合计反号」这句话只在末柱真的反号时才写 —— 末柱每个月都会换，
    # 写死一句「纯费率为正金色段为负」下个季度就是假话。
    MIX_FLIP = MIX_LAST['pure'] * MIX_LAST['gp'] < 0
    # 能源腿在四条腿费率里排第几（现算 —— 2026-Q2 是第 2 高，农金 2.25 比它还高；
    # 写死「费率最高的能源腿」会被数据打脸）。
    _rank = sorted(keys, key=lambda k: -RPCQ[k][_ql])
    EN_RANK = _rank.index('energy') + 1

    # ── 标题那句结论的构建期闸门 ────────────────────────────────────────
    # 标题写「量定方向、费率只做修正」，这是**结论**不是修辞，必须现算现验：
    # 一旦某轮数据把它推翻，本页要停机让人改标题，而不是留一句假话在图上。
    QTY_BIG = sum(1 for r in fin if abs(r['qty_pp']) > abs(r['rate_pp']))
    QTY_SIGN = sum(1 for r in fin if r['qty_pp'] * r['g_v'] > 0)
    RATE_SIGN = sum(1 for r in fin if r['rate_pp'] * r['g_v'] > 0)
    QTY_ABS_MED = float(np.median([abs(r['qty_pp']) for r in fin]))
    RATE_ABS_MED = float(np.median([abs(r['rate_pp']) for r in fin]))
    if not (QTY_BIG > len(fin) / 2 and QTY_SIGN > RATE_SIGN
            and QTY_ABS_MED > RATE_ABS_MED):
        raise SystemExit(
            f'Exhibit {ex_bridge}：标题声称「量定方向、费率只做修正」，但本轮数据不支持 '
            f'—— 量腿更大的季度 {QTY_BIG}/{len(fin)}、量腿与净额同号 {QTY_SIGN} 季 vs '
            f'费率腿 {RATE_SIGN} 季、|量腿| 中位 {QTY_ABS_MED:.2f}pp vs |费率腿| '
            f'{RATE_ABS_MED:.2f}pp。请改标题，不要留一句被数据证伪的结论。')

    # ── 桥覆盖了隐含总收入的多少（现算，不写死）────────────────────────────
    qlast = last['q']
    v_all = {k: VQ[k][qlast] for k, *_ in LEG_DEFS}
    V_SIX = sum(v_all.values())
    V_BRIDGE = sum(v_all[k] for k in keys)
    COV = V_BRIDGE / V_SIX * 100
    EN_IN_BRIDGE = v_all['energy'] / V_BRIDGE * 100
    EN_IN_SIX = v_all['energy'] / V_SIX * 100
    # 四条腿的季末费率极差 —— 「mix 一动费率腿就动」这句话的量级依据
    rp = {k: RPCQ[k][qlast] for k in keys}
    RPC_X = max(rp.values()) / min(rp.values())

    BRIDGE_CHECK = (
        f'Exhibit {ex_bridge} 量价分解（季度桶，本季 vs 去年同季）：{len(xl)} 根柱 '
        f'{xl[0]} – {xl[-1]}，画得出 {len(fin)} 根；覆盖衍生品四腿'
        f'（{"、".join(zh_of[k] for k in keys)}），{qlab__bridge(qlast)} 合计 ${V_BRIDGE:,.1f}mn '
        f'= 六腿隐含总收入 ${V_SIX:,.1f}mn 的 {COV:.1f}%；'
        f'末柱 {last["lab"]} 收入 ${last["V1"]:,.1f}mn vs ${last["V0"]:,.1f}mn、'
        f'张数 {last["Q1"]:,.0f}k vs {last["Q0"]:,.0f}k、'
        f'隐含费率 ${last["p1"] * 1000:.4f} vs ${last["p0"] * 1000:.4f}/张 → '
        f'量 {last["qty_pp"]:+.2f}pp + 费率 {last["rate_pp"]:+.2f}pp = '
        f'净 {last["g_v"] * 100:+.2f}%；净额区间 {NET_LO:+.1f}% – {NET_HI:+.1f}%；'
        f'标题闸门：量腿更大 {QTY_BIG}/{len(fin)} 季、量腿与净额同号 {QTY_SIGN} 季'
        f'（费率腿 {RATE_SIGN} 季）、|量腿| 中位 {QTY_ABS_MED:.2f}pp vs |费率腿| '
        f'{RATE_ABS_MED:.2f}pp；费率腿里的 mix 分量 |中位| {MIX_MED:.2f}%、'
        f'压过纯费率 {MIX_WINS}/{len(mix_rows)} 季；'
        f'两腿反号 {OPP_N} 根；w 区间 {W_LO:.3f}–{W_HI:.3f}，深蓝段与原始量同比最大差 '
        f'{LOG_GAP:.2f}pp（{LOG_GAP_AT}）；交叉项 |中位| {CROSS_MED:.2f}pp / |最大| '
        f'{CROSS_MAX:.2f}pp（{CROSS_AT}）；最小 |ln(V1/V0)| = {LV_MIN:.6f}'
        f'（{LV_MIN_AT}，阈值 {DEC_LN_MIN:.0e} 的 {LV_MIN / DEC_LN_MIN:,.0f} 倍）；'
        f'三道闭合残差 ≤ {DEC_EPS:.0e} 全过，payload 闭合 ≤ 2e-6 全过'
        + (f'；留空柱 {"、".join(blanks)}' if blanks else '')
        + (f'；两侧不齐 {"、".join(gaps)}' if gaps else ''))

    exd = {
        'n': ex_bridge, 'kind': 'bridge_bar', 'fmt': 'pct1', 'yfmt': 'pct0',
        # 不写 full / height / xstep / xrot：交给 mrwin.layout_all()。
        # ⚠️ 尤其**不要写 'xrot': 0** —— build/mrwin.py 对 xrot == 0 的 exhibit 整张
        # continue，既不判通栏也不抽标签（cme.py:1612 记着这个坑）。
        'xlabels': xl,
        # 结论式标题 —— 上面那道闸门现算现验这句话（量腿更大的季度过半、量腿与净额同号
        # 的季度多于费率腿、|量腿| 中位大于 |费率腿|），推翻了就停机改标题。
        # ⚠️ 标题用中文 —— 全页其余 16 张图与页尾散文都是中文，混一句英文进来，
        #    读者会以为这张图是从别处搬来的。（CME / Cboe 两页全英文，各自内部一致。）
        # ⚠️ 标题里**不许**用 Markdown 的 `**` —— page.js 走 innerHTML，不解析它，
        #    会把星号原样印在页面上（verify_pages 有一道 WARN 专抓这个）。
        #    要强调就用 <b>，或者像这里一样把强调留给图注。
        'title': '量定方向，费率只修边：隐含衍生品收入增长拆成张数与每张费率'
                 '（分解的是收入，不是成交额）',
        'ylab': '% y/y（本季 vs 去年同季）',
        'stacks': [
            {'name': '成交合约数', 'color': 'NAVY', 'values': L(dq)},
            {'name': '每张费率（RPC）', 'color': 'GOLD', 'values': L(dp)},
        ],
        'net': {'name': '隐含收入同比', 'values': L(dnet)},
        'net_color': 'INK',
        'src_extra': ('Identity: revenue = contracts x rate per contract; log-weight (LMDI) '
                      'decomposition rescaled to the arithmetic total, one bar = one quarter vs. '
                      'the same quarter a year ago. Covers the four derivatives legs only '
                      '(energy, ags & metals, rates, equity index & FX) — all quoted in thousands '
                      'of contracts, so the volume leg is additive. This decomposes REVENUE, '
                      'not notional turnover — ICE does not publish traded notional value'),
        'note': (
            # ① 这是什么分解，不是什么
            f'<b>这是收入的量价分解，不是成交额的量价分解。</b>恒等式是「隐含交易收入 = '
            f'成交合约数 × 每张平均费率(RPC)」；ICE 不披露成交<b>金额</b>，'
            f'「成交额 = 成交量 × 均价」那种分解在本页<b>不具备数据条件</b>，本图也没有假装做到。'
            f'这里的「价」是 ICE 向客户收的<b>每张费率</b>，不是标的资产的成交价格。'
            # ② 覆盖面：为什么是四条腿，不是六条
            f' <b>只覆盖四条衍生品腿</b>（能源、农产品与金属、利率、股指与外汇）：'
            f'桥需要一个可比的量，而这四条腿都以<b>千张</b>计价、可加；'
            f'NYSE 股票期权腿同样是千张但<b>单独的桥必须放弃</b>（费率只有 2 位小数而量程 '
            f'0.04–0.18，低端一格就是 25%，费率腿的同比会被舍入噪声主导），'
            f'NYSE 现货腿的量是<b>百万股</b>，与千张凑不出单一量纲。'
            f'{qlab__bridge(qlast)} 四条腿合计 <b>${V_BRIDGE:,.0f}mn</b>，'
            f'占六腿隐含总收入 ${V_SIX:,.0f}mn 的 <b>{COV:.1f}%</b>；'
            f'其中能源一条腿就占桥内收入的 {EN_IN_BRIDGE:.1f}%、占六腿合计的 {EN_IN_SIX:.1f}%。'
            f'<b>图外那 {100 - COV:.1f}% 不在本图的解释范围内</b>，不要把结论外推到整页收入。'
            # ③ 桶：为什么必须是季度
            f' <b>横轴一格 = 一个季度</b>，本期是该季、基期是<b>去年同季度</b>，'
            f'共 {len(xl)} 根柱（{xl[0]} – {xl[-1]}），左端由本页月度图的左端 {WIN_FROM} '
            f'换算得到。<b>必须按季度</b>：ICE 的 RPC 是<b>滚动三月均</b>，'
            f'季末月那一格的窗口恰好覆盖该季度，所以季度收入 = 季内三个月的'
            f'（ADV × 各自的交易日）之和 × <b>季末月</b>的 RPC。'
            f'逐月形式在<b>唯一能与官方对账的六个点</b>上一律偏低 0.57–2.15%，'
            f'而本页这个季末月形式落在 ±1.02% 内 —— 这是可核的六点事实，'
            f'不是「逐月形式系统性低估」的普遍结论（全样本上逐月形式并不系统性偏低）。'
            f'本页的季度块与月度图<b>不同粒度</b>，不要拿这里的柱去和月度图逐格对读。'
            # ④ 算法
            f' <b>图上画的是对数分解按算术总额重标定后的两块</b>：ln(V₁/V₀) = ln(Q₁/Q₀) + '
            f'ln(P₁/P₀) 天然可加、无交叉项；再乘 w = g<sub>收入</sub> ÷ ln(V₁/V₀) 换算回'
            f'百分点，深蓝 + 金色<b>逐根等于</b>菱形标的净增长（三道闭合检查残差上限 '
            f'{DEC_EPS:.0e}，写进 payload 后再核一道 2e-6，超了本页直接不出图）。'
            f'w 对量与价一视同仁，不含分配假设。'
            # ④b 标题那句结论的实测依据（构建期闸门核过，推翻了本页就停机）
            f' <b>标题那句「量定方向」是现算出来的</b>：{len(fin)} 根柱里 {QTY_BIG} 根'
            f'的量腿绝对值大于费率腿、{QTY_SIGN} 根的量腿与净额<b>同号</b>'
            f'（费率腿只有 {RATE_SIGN} 根），|量腿| 中位 {QTY_ABS_MED:.1f}pp、'
            f'|费率腿| 中位 {RATE_ABS_MED:.1f}pp。这不是「费率不重要」：'
            f'费率腿最大也到过 {max(abs(r["rate_pp"]) for r in fin):.1f}pp。'
            # ⑤ 深蓝段 ≠ 原始量同比
            f' <b>深蓝段不是「合约数同比」本身</b>：它是 w·ln(Q₁/Q₀)，而 w 逐季不同'
            f'（窗口内实测 {W_LO:.3f}–{W_HI:.3f}）—— 两种口径对「量」贡献的读数'
            f'最大差 <b>{LOG_GAP:.2f}pp</b>（{LOG_GAP_AT}）。'
            f'要读「合约数同比是多少」请回本页的量图，不要用这里的蓝段去替代。'
            # ⑥ 交叉项：只进图注，报 pp
            f' <b>算术分解只进图注</b>：g<sub>收入</sub> = g<sub>张数</sub> + g<sub>费率</sub>'
            f' + 交叉项，而交叉项必须整段压给某一腿，压给谁都会改读数，所以'
            f'<b>它不进图、不分配给任何一腿</b>。{len(fin)} 根柱里有 {OPP_N} 根'
            f'（{OPP_N / len(fin) * 100:.0f}%）量与费率<b>方向相反</b>。'
            f'实测交叉项<b>绝对值</b>中位 {CROSS_MED:.2f}pp、最大 {CROSS_MAX:.2f}pp'
            f'（{CROSS_AT}）'
            + (f'；「占净增长百分之多少」只在净增长本身不近零时才有意义 —— '
               f'净增长绝对值 ≥ 5% 的 {len(far)} 根里最大 {CROSS_SH_FAR:.0f}%。'
               if far else '。')
            + f'{last["lab"]} 的算术读数：张数 {pctf(last["g_q"], 1)}、'
            f'费率 {pctf(last["g_p"], 1)}、交叉项 {pp(last["cross"] * 100)}，'
            f'合计 {pctf(last["g_v"], 1)}。'
            # ⑦ P 是反算的，不是已披露的季末 RPC
            f' <b>金色段里的「费率」是反算出来的隐含费率，不是任何一条已披露的 RPC</b>：'
            f'P = 桥内收入 ÷ 桥内张数，也就是四条腿已披露费率按<b>当季张数结构</b>'
            f'加权的混合值（{qlab__bridge(qlast)} 四条腿的季末费率相差 {RPC_X:.1f} 倍）。'
            f'两期的结构不同，所以<b>即使每条腿的费率一格不动，金色段也会因为 mix 位移'
            f'而不为零</b>。用「本期结构 × 基期费率」这个反事实把两者拆开：'
            f'mix 分量 |中位| {MIX_MED:.2f}%、绝对值最大的一根 {pctf(MIX_MAX["mix"], 2)}'
            f'（{MIX_MAX["lab"]}），纯费率分量 |中位| {PURE_MED:.2f}%；'
            f'{len(mix_rows)} 根柱里 <b>{MIX_WINS} 根是 mix 压过纯费率</b> —— '
            f'所以既不能说金色段是「涨价」，也不能说它「主要是结构」，两种说法都会被'
            f'下一个季度证伪。{last["lab"]} 就是 mix 主导的一根：隐含费率合计 '
            f'{pctf(MIX_LAST["gp"], 2)}，拆成 mix {pctf(MIX_LAST["mix"], 2)} × '
            f'纯费率 {pctf(MIX_LAST["pure"], 2)}。同季四条腿的<b>已披露</b>季末费率是'
            f'{RPC_LEG_TXT}（{RPC_UP_N} 涨 {RPC_DN_N} 跌 {RPC_FL_N} 平）'
            + ('，<b>纯费率分量与金色段方向相反</b>' if MIX_FLIP else '')
            + f'；能源腿在张数里的占比从 '
            f'{QQ["energy"][_ql - 4] / last["Q0"] * 100:.1f}% 变到 '
            f'{QQ["energy"][_ql] / last["Q1"] * 100:.1f}%，'
            f'它的费率在四条腿里排第 {EN_RANK}，占比一动金色段就跟着动。'
            f'结构本身见 Exhibit {EX_REVMIX}、各腿费率水平见 Exhibit {EX_RPC}。'
            f'{last["lab"]} 的隐含费率是 ${last["p1"] * 1000:.4f}/张'
            f'（去年同季 ${last["p0"] * 1000:.4f}）。'
            # ⑧ 对账身份：对上的三桶不给对不上的腿背书
            f' <b>桥覆盖的四条腿之和，恰好等于能与官方对账的三个桶</b>（能源、农产品与金属、'
            f'金融合计）：2Q25 与 2Q26 共 6 项，本页推导值与 ICE Key Metrics 披露值'
            f'最差差 1.02%，残差全部来自 RPC 只保留 2 位小数。但<b>利率与股指外汇各自那一腿'
            f'没有官方数可对</b>，它们只是把「金融合计」拆成两半 —— 本图只用它们的<b>合计</b>，'
            f'柱高不依赖这个拆分。'
            # ⑨ 菱形与收入图的关系
            f' <b>菱形（净额）读的是桥内四条腿的收入同比</b>，与 Exhibit {EX_REV} 的'
            f'六腿合计同比<b>不是同一条数</b>（覆盖面差 {100 - COV:.1f}%），不要互相验证。'
            # ⑩ 留空规则
            + (f' <b>留空的柱</b>：{"、".join(blanks)} 的 |ln(V₁/V₀)| < {DEC_LN_MIN:.0e}'
               f'（两期几乎持平），重标定权重 w 是 0/0、算出来没有有效位，'
               f'整根柱（两段与净额菱形一起）留空而不是印一个假的分解。' if blanks else
               f' <b>本轮没有任何一根柱落进留空区间</b>（判据 |ln(V₁/V₀)| < {DEC_LN_MIN:.0e}，'
               f'两期几乎持平时 w = 0/0）：最接近的一根是 {LV_MIN_AT}，'
               f'|ln(V₁/V₀)| = {LV_MIN:.4f}，是阈值的 {LV_MIN / DEC_LN_MIN:,.0f} 倍。')
            + (f' <b>两侧不齐而留空的柱</b>：{"、".join(gaps)}（两段与菱形同空）。'
               if gaps else '')),
    }

    stats = {
        'rows': rows, 'fin': fin, 'xl': xl, 'last': last,
        'NET_LO': NET_LO, 'NET_HI': NET_HI, 'OPP_N': OPP_N,
        'CROSS_MED': CROSS_MED, 'CROSS_MAX': CROSS_MAX, 'CROSS_AT': CROSS_AT,
        'W_LO': W_LO, 'W_HI': W_HI, 'LOG_GAP': LOG_GAP, 'LOG_GAP_AT': LOG_GAP_AT,
        'LV_MIN': LV_MIN, 'LV_MIN_AT': LV_MIN_AT,
        'COV': COV, 'V_BRIDGE': V_BRIDGE, 'V_SIX': V_SIX,
        'EN_IN_BRIDGE': EN_IN_BRIDGE, 'EN_IN_SIX': EN_IN_SIX,
        'MIX_MED': MIX_MED, 'MIX_MAX': MIX_MAX, 'RPC_X': RPC_X,
        'blanks': blanks, 'gaps': gaps,
    }
    return exd, BRIDGE_CHECK, stats

# ==========================================================================
# 【exlib】
# ==========================================================================

# -*- coding: utf-8 -*-
"""build/ice.py 的**图型构造库** —— 每种 chart kind 一个封装函数。

本文件是 build/ice.py 的一个片段（合并时整段贴进去，`if __name__` 自测块删掉，
下面 §0 的 bootstrap 块也删掉 —— 那一块里的名字由别的段提供）。

为什么要有这一层，而不是像 build/cboe.py 那样每张图手写一个 dict：
  · ICE 这一版有近十张 gs_bar（Ex2 / Ex15 …）与五张 stacked_dual（Ex3/7/10/12/13/16/18）。
    手写十遍必漂 —— build/cme.py:873 把 gs_bar 函数化正是为此，本文件照它办。
  · 「口径判据只许有一份实现」这条规矩（build/pctile.py 模块头：各写各的，正是同一条
    序列在两页被判定相反的原因）在图型层同样成立：ylab2 该写 `% y/y` 还是 `pp y/y`
    还是 `USD/contract, y/y 差`，本文件一处都不自己判，全部转发 `single.py`。
  · 窗口左端（「这几条线的共同首个非空月」）本仓已有唯一实现 `mrwin.resolve()`，
    带 Leg/DENSE 分档与机读说明。本文件**不重写**它，只当调用方。

⚠️ 本文件不生产任何图注正文（除了「排版 / 窗口 / 不可见段」这类**只有构造期知道**
   的机读说明）。论证性的图注是 exhibit 那几段的事，走 `note=` 传进来。
"""

sys.path.insert(0, os.path.join(ROOT, 'build'))

BREAK_MONTH = '2013-11'     # 唯一口径断点：NYSE Euronext 收购完成

def qlab__exlib(q):
    """季度 Period → '2026Q2'。

    ⚠️ 与 build/cme.py:197 的 `'2026-Q2'` **有意不同**：那边加连字符是为了让读者
    拿季度号回 `series/fee_rates.csv` 里 grep，而 ICE 页没有那张表，季度号只出现在
    本页自己的横轴与图注里。多加一个连字符等于凭空造一个源里不存在的写法。
    """
    return str(q)

def num__exlib(v):
    """float 化，非有限一律 nan —— 「这个格子有没有数」全站只在这里判一次。"""
    if v is None:
        return float('nan')
    try:
        f = float(v)
    except (TypeError, ValueError):
        return float('nan')
    return f if np.isfinite(f) else float('nan')

def caliber_diff_win__exlib(s, win, kind=YOY.FLOW):
    """`yoy.caliber_diff` 的本页入口：索引换成横轴标签、统计范围限定成图窗
    （抄 cboe.py:233；两件事都是 CONTRACT §6.4 点名的坑）。"""
    s = pd.Series(s)
    s = s.set_axis([mlab(p) for p in s.index])
    return YOY.caliber_diff(s, kind, win=[mlab(p) for p in win])

def caliber_stats__exlib(s, win, kind=YOY.FLOW):
    """键名适配层，抄 cboe.py:254。"""
    d = caliber_diff_win__exlib(s, win, kind)
    opp = pd.DataFrame([{'m': m, 'r': r} for _, m, r in d['opposite']],
                       index=[p for p, _, _ in d['opposite']])
    return {'n': d['n'], 'first': d['months'][0], 'last': d['months'][-1],
            'sd_m': d['std_mom'], 'sd_r': d['std_ttm'],
            'jump_m': d['maxjump_mom'][0], 'jump_m_at': d['maxjump_mom'][2],
            'jump_r': d['maxjump_ttm'][0] if d['maxjump_ttm'] else float('nan'),
            'n_opp': d['opposite_n'], 'opp': opp}

def yoy_cal_zh__exlib(n, s_full, win, label):
    """Exhibit n 的「口径 + 代价」图注段 —— 拿这张图自己那条序列、自己那段窗口实测。
    CONTRACT §6.1 第 3 条；账本进 COST_LOG（列表，见上）。"""
    d = caliber_diff_win__exlib(s_full, win, YOY.FLOW)
    COST_LOG.setdefault(n, []).append({'label': label, 'd': d})
    xl = [mlab(p) for p in win]
    head = (f'<b>次轴那条线是<u>单月</u>同比</b>（当月 ÷ 去年同月 − 1），全站统一、'
            f'页面所有者指定（<code>build/CONTRACT.md</code> §6）。'
            f'<b>代价（§6.1 第 3 条）用<u>本图这条序列</u>实测</b>，'
            f'统计范围就是本图画出来的这段窗口 —— {xl[0]} 至 {xl[-1]}（{len(win)} 个月）：')
    if d['n'] < MOM_COST_MIN:
        return (head + f'<b>{label}</b>：代价量不出来 —— 两种口径都算得出的月份只有 '
                       f'{d["n"]} 个（不足 {MOM_COST_MIN} 个），此处不报差异。')
    return head + f'<b>{label}</b>：' + YOY.describe(d)

def _load():
    df = pd.read_csv(CSV)
    df['month'] = pd.PeriodIndex(df['month'], freq='M')
    df = df.set_index('month').sort_index()
    for c in df.columns:
        df[c] = pd.to_numeric(df[c], errors='coerce')
    return df

#: 列元数据表。**`unit` 字符串是承重的**：它逐字喂给 `SG.col_is_ratio` /
#: `SG.col_is_money_ratio` / `SG.rhs_ylab2`，改一个字判定就翻，而且不报错。
#: 合法值只有 'k contracts/day' 'k contracts' 'USD/contract' 'USD/100 shares'
#: 'mn shares/day' 'USD bn/month' '%'，与 build/specs/ice.py 逐字一致。
#: （真表在别的段，这里只放本文件自测要用到的那些列。）
_U_KD, _U_K, _U_UC = 'k contracts/day', 'k contracts', 'USD/contract'

_U_MS, _U_P100, _U_BN, _U_PCT = 'mn shares/day', 'USD/100 shares', 'USD bn/month', '%'

COL__exlib = {}

def _c(col, zh, unit, fmt, **kw):
    COL__exlib[col] = dict({'col': col, 'zh': zh, 'unit': unit, 'fmt': fmt}, **kw)

for _k, _zh in [('adv_energy_kcontracts', '能源合计'),
                ('adv_brent_kcontracts', 'Brent 原油'),
                ('adv_gasoil_kcontracts', 'Gasoil 柴油'),
                ('adv_otheroil_kcontracts', '其他原油与成品油'),
                ('adv_natgas_kcontracts', '天然气（含 TTF）'),
                ('adv_power_kcontracts', '电力'),
                ('adv_environmentals_kcontracts', '环境权益与其他'),
                ('adv_sugar_kcontracts', '糖'),
                ('adv_otherags_metals_kcontracts', '其他农产品与金属'),
                ('adv_ag_metals_kcontracts', '农产品与金属合计'),
                ('adv_commodities_kcontracts', '大宗商品合计'),
                ('adv_stir_kcontracts', '短期利率'),
                ('adv_mltir_kcontracts', '中长期利率'),
                ('adv_equity_index_kcontracts', '股指'),
                ('adv_fx_credit_kcontracts', 'FX 与 USDX'),
                ('adv_financials_kcontracts', '金融合计（不含单股）'),
                ('adv_futures_options_kcontracts', '衍生品总 ADV'),
                ('adv_nyse_equity_options_kcontracts', 'NYSE 两所合计'),
                ('adv_us_equity_options_industry_kcontracts', '全美股票/ETF 期权行业总量')]:
    _c(_k, _zh, _U_KD, 'f0c')

for _k, _zh in [('oi_energy_kcontracts', '能源'), ('oi_ag_metals_kcontracts', '农产品与金属'),
                ('oi_rates_kcontracts', '利率'), ('oi_other_financials_kcontracts', '股指与 FX'),
                ('oi_commodities_kcontracts', '大宗商品'), ('oi_financials_kcontracts', '金融')]:
    _c(_k, _zh, _U_K, 'f0c', stock=True)

for _k, _zh in [('rpc_energy_usd', '能源'), ('rpc_ag_metals_usd', '农产品与金属'),
                ('rpc_rates_usd', '利率'), ('rpc_other_financials_usd', '股指与 FX'),
                ('rpc_commodities_usd', '大宗商品'), ('rpc_financials_usd', '金融'),
                ('rpc_nyse_equity_options_usd', 'NYSE 期权 RPC')]:
    _c(_k, _zh, _U_UC, 'f2')

_c('rpc_nyse_us_cash_usd_per100sh', '现货 RPC（每 100 股）', _U_P100, 'f3')

for _k, _zh in [('adv_nyse_us_cash_handled_mnsh', 'NYSE Group handled ADV'),
                ('adv_nyse_tapeA_matched_mnsh', 'Tape A · NYSE matched'),
                ('adv_tapeA_consolidated_mnsh', 'Tape A 全市场')]:
    _c(_k, _zh, _U_MS, 'f0c')

for _k, _zh in [('cds_client_notional_usdbn', '客户盘'),
                ('cds_nonclient_notional_usdbn', '非客户盘'),
                ('cds_total_notional_usdbn', '合计')]:
    _c(_k, _zh, _U_BN, 'f0c')

for _k, _zh in [('share_nyse_equity_options', 'NYSE 期权份额'),
                ('share_nyse_us_cash_matched', 'NYSE 全美 matched 份额'),
                ('share_nyse_tapeA_matched', 'Tape A 份额'),
                ('share_nyse_tapeB_matched', 'Tape B 份额'),
                ('share_nyse_tapeC_matched', 'Tape C 份额')]:
    _c(_k, _zh, _U_PCT, 'pct1', scale=100)

# ══════════════════════════ §1  通用零件 ══════════════════════════════════
#: `lines` 开了 `end_label` 的长历史图的最小画布高。照抄 build/exchanges_products.py:151
#: 与 build/exchanges_eu.py:289 的 `LINE_H_ENDLABEL`。
#: 依据在 docs/CHART_KINDS.md §3.9：末点标签的避让逻辑在绘图区高度 < 308px 时会把整列
#: 标签收成一摞贴右上角，**读数会安到别的线上**。默认高 248 减掉顶边距只剩 ~228px。
LINE_H_ENDLABEL = 360

#: 一张图最多几条靠颜色区分的序列（docs/CHART_KINDS.md §2）。转发 single.py 的常量，
#: 不另立一个数 —— 两处各写一个 5，改一处就分叉。
MAX_LINES = SG.MAX_LINES

#: 引擎认得的**数据色**，一共 6 个（RED 是断点与截轴离群值的专用色，不做数据色）。
#: 「一张图最多几条靠颜色区分的序列」的物理上界就是这个 6。
DATA_COLORS = ('NAVY', 'BLUE', 'MBLUE', 'GRAY', 'GREEN', 'GOLD')

#: 堆叠段的取色顺序。三条考虑，缺一条就会踩到已知的坑：
#:   · **GRAY 留给残差段**（全站「其余 / 未拆分」的既定用色），所以不在这条序列里；
#:   · **MBLUE 与 GREEN 不相邻**（docs/CHART_KINDS.md §3.6.1：两者对比度只有 1.07:1、
#:     灰度差 1.7%，挨着排的两段在柱里分不出界）；
#:   · **GOLD 排在 GREEN 前面**：`stacked_dual` 的右轴线缺省色是 GREEN，把 GREEN 往后放
#:     能让「四段以内 + 缺省色的线」天然不撞色；真撞了由 `_color_guard` 停机，
#:     由调用点改线的颜色，而不是在这里悄悄换段色。
SEG_COLORS = ('NAVY', 'MBLUE', 'BLUE', 'GOLD', 'GREEN')

SEG_RESID_COLOR = 'GRAY'

#: 引擎几何常量，用来现算「这一段画出来是不是 0 高」（见 `_invisible_segments`）。
#: 三个数全部来自 assets/charts.js，按**标识符**回指、不写行号
#: （cboe.py 的 draw_break 那段记着理由：charts.js 是 34 页共用、每轮都在动的文件）：
#:   · `stacked_dual` 在 `perPointLabels` 名单里 ⇒ 默认画布高 268 + round(26×(FS−1)) + XB
#:   · 顶边距 `M.t = fscale(14)`（本 kind 不支持截轴，永远走 capOn=false 那一档）
#:   · 底边距 `M.b = XB`，与 H 里那个 XB 抵消 ⇒ ph = 268 + round(26(FS−1)) − 14×FS
#:   · 段高 `hgt = max(0, Y(sDn) − Y(sUp) − sgp)`，`sgp = 1.5`（朝零线那一侧的白缝）
#: FS ∈ [1.45, 1.70]，取 **FS_MIN**（ph 最小 ⇒ 阈值最大 ⇒ 判得最严，宁可多说一句）。
_FS_MIN = 1.45

_SD_PH = 268 + round(26 * (_FS_MIN - 1)) - 14 * _FS_MIN      # ≈ 259.7px

_SD_GAP = 1.5

#: 左轴上界的倍数：给了右轴线是 ×1.28（要给逐点百分比标签留白），不给是 ×1.06。
_SD_TOP = {True: 1.28, False: 1.06}

def cmeta(col):
    """列名 → 列元数据。**不许现造**：`unit` 一个字写错，`col_is_ratio` 的判定就翻，
    而且不报错（冻结契约里那张实测表就是拿这个判据跑出来的）。"""
    c = COL__exlib.get(col)
    if c is None:
        raise SystemExit(f'列 {col!r} 不在 COL__exlib 里 —— 手写页没有引擎那套 unit 推导，'
                         f'不登记就没有单位，ylab2 / 表头 / 释义板会各写各的。')
    return c

def cvals(col, win):
    """一列在一段窗口上的值，**已按 COL__exlib 里的 `scale` 缩过**。

    份额列在 CSV 里是比值（0.295），页面上要读百分数（29.5）—— 引擎的
    `stacked_dual` 右轴点标签写死 `toFixed(1) + '%'`（CHART_KINDS §6），
    喂比值进去会印出「0.3%」。缩放只在这一处做，调用点不许各乘各的。
    """
    c = cmeta(col)
    v = df[col].reindex(win).values.astype(float)
    k = c.get('scale')
    return v * k if k else v

def _legs(cols, win, primary=None):
    """把一组列做成 `mrwin.Leg`。窗口裁决全部转发 `mrwin.resolve()`，本文件不重写。

    `role='primary'` 的腿定义左端；不给就全部当 primary（多条线的图里每一条都是
    主角，没有「派生腿可以更短」这回事）。
    """
    primary = set(primary or cols)
    out = []
    for k in cols:
        c = cmeta(k)
        out.append(mrwin.Leg(k, c['zh'], cvals(k, win),
                             role='primary' if k in primary else 'derived',
                             lag_zh=f'{c["unit"]}'))
    return out

def _resolve(kind, cols, win, primary=None):
    """→ (win2, xlabels2, {col: 切好的数组}, why)。左端由**本图自己那几列**推出。"""
    if not cols:
        # 全部段都是现算数组（没有一条走 CSV 列）：没有「共同首个非空月」可推，
        # 窗口就是调用方给的那一段。裁决层不该替一个它看不见的数组编故事。
        return list(win), [mlab(p) for p in win], {}, ''
    legs = _legs(cols, win, primary)
    labels = [mlab(p) for p in win]
    w = mrwin.resolve(kind, legs, labels, want_from=0)
    kept = [l for l in legs if not l.drop]
    if len(kept) != len(legs):
        raise SystemExit(f'{kind}：{[l.key for l in legs if l.drop]} 在窗口内没有任何值，'
                         f'`mrwin.resolve()` 已把它们摘掉 —— 请在调用点就别传进来，'
                         f'免得图例与色序悄悄错位。')
    win2 = list(win[w.start:])
    data = {l.key: w.cut(l.vals) for l in kept}
    return win2, [mlab(p) for p in win2], data, w.why

def _dense_guard(kind, n, series):
    """DENSE 图型的无 null 断言（docs/CHART_KINDS.md §1.2）。

    `gs_line` / `gs_line_avg` / `lines_endlabels` / `stacked_dual` 四种把 null 交给
    Catmull-Rom / 堆叠基线，后果分别是**抛 TypeError 整页后续 exhibit 全丢**、
    **一条塌到零的假线**、**NaN 坐标那根柱不画**，三种都不报错。
    `mrwin.resolve()` 已经把左端推到「所有腿都稠密」的那一期，这里是收口断言：
    真漏了就当场停机，不要指望引擎兜底。
    """
    if kind not in mrwin.DENSE:
        return
    for name, vals in series:
        bad = [i for i, v in enumerate(vals) if v is None or not np.isfinite(num__exlib(v))]
        if bad:
            raise SystemExit(
                f'Exhibit {n}（{kind}）的「{name}」在窗口内有 {len(bad)} 个 null'
                f'（首个下标 {bad[0]}）—— {kind} 属 DENSE 图型，'
                f'docs/CHART_KINDS.md §1.2：引擎不兜底，画面也不报错。')

def _color_guard(n, kind, colors, rhs_color=None):
    """配色三查：数量上限、互不重复、不与次轴线撞色。

    第三条最容易漏：那条线无描边、画在柱之后，穿过同色段时**整段看不见**
    （verify_pages 对 gs_bar 是硬 ERROR，对 stacked_dual 没这道查，所以本文件自己查）。
    """
    if len(colors) > MAX_LINES:
        raise SystemExit(f'Exhibit {n}（{kind}）有 {len(colors)} 条靠颜色区分的序列，'
                         f'超过 {MAX_LINES}（docs/CHART_KINDS.md §2）—— 引擎的数据色只有 6 个，'
                         f'超了会撞色。出路：并成「其余」，或换成靠行标签认身份的 heat_matrix。')
    if None in colors or len(set(colors)) < len(colors):
        raise SystemExit(f'Exhibit {n}（{kind}）的配色 {colors} 有缺省或重复 —— '
                         f'不认识的色名会静默退回 NAVY，同色两段连不出分界。')
    if rhs_color and rhs_color in colors:
        raise SystemExit(f'Exhibit {n}（{kind}）的次轴线用了 {rhs_color}，与某一段同色 —— '
                         f'折线无描边且画在柱之后，穿过同色段时整段看不见。')

# ══════════════════════════ §2  gs_bar ════════════════════════════════════
#: gs_bar() 建过的**存量口径**图号（kind=YOY.STOCK）。页尾那条「读存量的是哪一张」
#: 现读它，不写死图号（cme.py:_GS_STOCK 同一用法）。
GS_STOCK = []

#: 每张图真正画出来的窗口，供别的段写图注时现读（「本图左端是哪一期」不许手抄）。
WIN_LOG = {}

#: 每张 stacked_dual 的「0 高段」阈值台账（现算，见 `_invisible_segments`）。
#: 图注要说「最矮那一段量得出来」时现读它，不许在正文里手写一个 0.6%。
SEG_THR_LOG = {}

#: 「这张图画的是存量」的文字标记。`tools/check_yoy_caliber.py` 的 `_STOCK_TXT`
#: 认的就是这几个字 —— 标题里没有它们，R1/R4 会把一条**合法**的点对点同比报成
#: 「该用滚动口径」。所以存量图的标题必须自报，这里在构建期查。
_STOCK_TXT = re.compile(r'存量|期末口径|月末|期末|未平仓|month-?end|open interest', re.I)

def gs_bar(n, col, title, ylab, fmt, legend, note=None, src_extra=None,
           kind=YOY.FLOW, zh=None):
    """浅蓝柱 + **次轴同比折线**（给了 `yoy` 引擎就不画 12 个月均线）。

    照 build/cme.py:873 函数化。ICE 这一版有近十张 gs_bar（Ex2 头条 ADV、Ex15 NYSE
    现货 handled …），手写十遍必漂 —— 漂的不是数，是 ylab2 那一串口径字。

    四件事在这里一次做完，调用点一件都不许自己做：

    ① **次轴标题走 `SG.rhs_ylab2(c, mom=…)`。** 三档（`% y/y` / `pp y/y` /
       `USD/contract, y/y 差`）的判据在 single.py 里，本文件一个字都不自己判。
       `mom=True` 只给**流量**：`tools/check_yoy_caliber.py` 的 R4 要「单月」写进
       title/ylab2/legend/yoy.name 四处之一，而存量的点对点同比本来就不是
       「单月 vs 滚动」的二选一，写上「单月」反而是句假话。
    ② **近零基数闸**（CONTRACT §6.1 第 5 条）：命中就停机，不画一条「读的是分母
       不是量」的线。单月口径下这条尤其要紧 —— 滚动窗口能把一个近零的分母摊薄，
       单月不能。
    ③ **逐图代价**（§6.1 第 3 条）：流量图现算，账本进 `COST_LOG`。存量图不欠这笔债
       —— §6.1 第 3 条只管流量列，存量没有第二种合法口径，也就没有「换口径的代价」。
    ④ **强制 `zh=` 点名**（cme.py:934-940）：代价那段要在图注里点明「这是本图这条
       序列的实测」，点名不能省，省了就会变成九张图共用一份数那种错。

    `full` / `height` / `xstep` 一律不写：交给 `finalize()` 里的 `mrwin.layout_all()`
    按 charts.js 的量边距算式判（cme.py:1615）。
    """
    c = cmeta(col)
    stock = (kind == YOY.STOCK)
    if stock:
        GS_STOCK.append(n)
        if not _STOCK_TXT.search(f'{title} {ylab} {legend}'):
            raise SystemExit(
                f'Exhibit {n}（{col}）是存量列，但标题/轴名/图例里没有「存量」「期末口径」'
                f'「未平仓」这类字 —— tools/check_yoy_caliber.py 的 _STOCK_TXT 认不出来，'
                f'会把一条合法的点对点同比报成 R1/R4。标题请带「（存量，期末口径）」。')
    ex = {'n': n, 'kind': 'gs_bar', 'title': title, 'fmt': fmt, 'ylab': ylab,
          # ylab2 的三档判据在 single.py，本文件不自己判（见 docstring ①）
          'ylab2': SG.rhs_ylab2(c, mom=not stock),
          # xlabels 必须显式给：不给就退到 payload 的页级默认，而 mrwin.layout_all()
          # 只对**自带 xlabels** 的 exhibit 判通栏与抽稀，漏给等于这张图不过排版裁决。
          'legend': legend, 'xlabels': XL25,
          'values': L(cvals(col, W25)),
          'yoy': {'name': ('y/y（存量，点对点，RHS）' if stock else 'y/y（单月，RHS）'),
                  'color': 'GOLD', 'yfmt': 'pct0',
                  'values': L(SG.yoy_line(df[col], W25, pct_series=SG.col_is_ratio(c)))}}
    WIN_LOG[n] = {'win': W25, 'cols': [col]}

    # ② 近零基数闸。比率列没有分母可放大，跳过（与 single.py 的 near_zero_rows_zh 同判据）
    if not SG.col_is_ratio(c):
        _nz = YOY.near_zero_base(df[col], win=list(W25))
        if _nz['flag']:
            raise SystemExit(
                f'Exhibit {n}（{col}）的近零基数月在窗口内占 {_nz["share"]:.1%}'
                f'（≥ 1/12），CONTRACT §6.1 第 5 条：这条序列不该画同比，该画水平值。'
                f'最极端的一个月：{_nz["worst"]}')

    # ③④ 代价 + 点名
    if stock:
        cal = ('<b>本图读的是存量</b>（月末未平仓，期末口径），同比是<u>点对点</u>：'
               '本月末 ÷ 去年同月末 − 1。存量没有「滚动合计」这个选项'
               '（12 个月末的持仓相加不指代任何真实的量），所以也就没有'
               '「换口径的代价」可报 —— CONTRACT §6.1 第 3 条那笔逐图的债只管流量列。')
    else:
        if not zh:
            raise SystemExit(
                f'Exhibit {n}（{col}）画的是流量单月同比，但 gs_bar 没收到 zh= 点名 —— '
                f'CONTRACT §6.1 第 3 条要求逐图印代价，而代价那段要在图注里点明'
                f'「这是本图这条序列的实测」，点名不能省。')
        cal = yoy_cal_zh__exlib(n, df[col], W25, zh)
    ex['note'] = (note + ' ' + cal) if note else cal
    if src_extra:
        ex['src_extra'] = src_extra
    return ex

# ══════════════════════ §3  lines / lines_endlabels ══════════════════════
def _lines_core(kind, n, cols, title, ylab, fmt, note=None, src_extra=None,
                colors=None, names=None, yfloor=None, yfmt=None, label_fmt=None,
                zero_base=False, end_label=False, height=None, win=None):
    """`lines` 与 `lines_endlabels` 的共同实现。

    窗口左端**由本图自己那几列的共同首个非空月推出**，走 `mrwin.resolve()`：
      · `lines_endlabels` 属 DENSE ⇒ 左端推到「所有腿都稠密」的那一期，
        再由 `_dense_guard` 收口断言；
      · `lines` 不属 DENSE（它是全站唯一能安全吃缺口的多线图型），中段的 null 允许
        断笔，但左端仍按共同首个非空月裁 —— 否则左边一截只有一条线，读者会把
        「这条线还没开始」读成「那几家当时是零」。
    裁决产出的那段机读说明（`Win.why`）直接追加进图注：窗口为什么不是 2016-01，
    页面上必须有出处。
    """
    win = win or W25
    win2, xl2, data, why = _resolve(kind, cols, win)
    colors = list(colors or SEG_COLORS[:len(cols)])
    _color_guard(n, kind, colors)
    names = list(names or [cmeta(k)['zh'] for k in cols])
    series = [{'name': nm, 'color': cl, 'values': L(data[k])}
              for k, nm, cl in zip(cols, names, colors)]
    _dense_guard(kind, n, [(s['name'], s['values']) for s in series])

    ex = {'n': n, 'kind': kind, 'title': title, 'ylab': ylab, 'fmt': fmt,
          'xlabels': xl2, 'series': series}
    if label_fmt:
        ex['label_fmt'] = label_fmt
    if yfmt:
        ex['yfmt'] = yfmt
    if yfloor is not None:
        ex['yfloor'] = yfloor
    if kind == 'lines':
        # `zero_base` 不给等于一次**没标注的隐性截轴**（CHART_KINDS §3.9），
        # 长历史图必给；含负值的序列它也不会把负值压没。
        if zero_base:
            ex['zero_base'] = True
        if end_label:
            ex['end_label'] = True
            # ⚠️ 这里是本文件**唯一**一处写 `height`，与「height 一律不手写」那条有意冲突：
            # mrwin.layout_all() 只管 full / xstep，从不设 height，而 CHART_KINDS §3.9
            # 明写「开了 end_label 的长历史图 height 要给到 ≥ 360，否则末点标签会收成
            # 一摞贴右上角、读数安到别的线上」。写在函数里而不是调用点，
            # 「调用点不手写」这条仍然成立。依据：exchanges_products.py:151。
            ex['height'] = height or LINE_H_ENDLABEL
    elif height:
        ex['height'] = height

    body = []
    if len(xl2) < len(win):
        body.append(f'<b>本图左端是 {xl2[0]}，不是页面窗口的 {mlab(win[0])}</b>：')
    if why:
        body.append(why)
    ex['note'] = (note or '') + ''.join(body)
    if not ex['note']:
        ex.pop('note')          # 空 note 会在卡片下方留一行空的「Note:」
    if src_extra:
        ex['src_extra'] = src_extra
    WIN_LOG[n] = {'win': win2, 'cols': list(cols)}
    return ex

def lines_endlabels(n, cols, title, ylab, fmt, **kw):
    """N 条平滑线，只标两端。**首尾任一为 null 就抛 TypeError**（§1.2），
    所以窗口必须先在 Python 侧截到「所有序列都有值」——见 `_lines_core`。"""
    return _lines_core('lines_endlabels', n, cols, title, ylab, fmt, **kw)

def lines(n, cols, title, ylab, fmt, zero_base=True, end_label=True, **kw):
    """N 条折线（不平滑、null 处断开）。`zero_base` / `end_label` 默认打开：
    本页用它的两张（指数化的单位经济、按 Tape 的份额）都是长历史图，
    前者不给零基就是隐性截轴，后者不标末点就读不到任何绝对水平。"""
    return _lines_core('lines', n, cols, title, ylab, fmt,
                       zero_base=zero_base, end_label=end_label, **kw)

# ══════════════════════════ §4  stacked_dual ═════════════════════════════
def _invisible_segments(vals_by_seg, top_mult):
    """→ [(段序号, 命中的格数, 最小份额)]。哪几段画出来是 **0 高**。

    引擎的段高是 `hgt = max(0, Y(sDn) − Y(sUp) − 1.5)`：一段自己的像素高度不超过
    那条 1.5px 白缝，这一段就**完全不画**，而画面、verify_pages、visual_qa 都不报错，
    读者看到的是「这块业务这个月没有」。
    所以阈值按引擎几何现算，不写死一个 0.6% —— 换成不给右轴线的图（上界倍数由
    1.28 变 1.06）阈值就变了，写死的数不会跟着变。
    """
    n = len(vals_by_seg[0])
    tot = [sum(num__exlib(s[i]) for s in vals_by_seg) for i in range(n)]
    hi = max([t for t in tot if np.isfinite(t)] or [0.0])
    if hi <= 0:
        return [], 0.0
    y1 = hi * top_mult                       # 左轴上界（全非负 ⇒ y0 = 0）
    thr = _SD_GAP * y1 / _SD_PH              # 值域上的「0 高」阈值
    out = []
    for k, s in enumerate(vals_by_seg):
        hit = [i for i in range(n) if np.isfinite(num__exlib(s[i])) and 0 < num__exlib(s[i]) <= thr]
        if hit:
            out.append((k, len(hit), min(num__exlib(s[i]) for i in hit)))
    return out, thr

def stacked_dual(n, segs, title, ylab, fmt, note=None, src_extra=None,
                 line=None, ylab2=None, total_col=None, resid_name=None,
                 pct100=False, labels=False, win=None):
    """堆叠柱（+ 可选右轴线）。

    `segs`：[(列名 | np.ndarray, 图例名, 色名), …]，≤ 5 段（`_color_guard`）。
    `total_col` + `resid_name`：给了就把「合计 − Σ段」做成最后一段 GRAY 残差。
        **残差必须命名** —— CHART_KINDS §3.14 末条：份额堆叠带的残差要在 note 里
        点名它是什么。这里更进一步，连图例名都强制传，不许出现一段无名的灰。
    `pct100=True`：各段除以合计归一到 100。这一档**必须**显式给 `fmt='pct1'` ——
        不给会退回 `f0c`，卡片的「表格」视图把占比截成整数、相加印成 99 或 101，
        当场证伪「各段之和 = 100%」（cme.py 的 EX_REVMIX 注释记着这一条）。
    `line`：{'col' 或 'values', 'name', 'color', 'ymax'}。**可选** —— 占比型堆叠里
        段高本身就把每一块读出来了，再拿其中一段换个刻度画一遍是同一个数说两遍。
        右轴那条线必须是**百分数的数值**（41.5 表示 41.5%）：引擎把它的点标签写死成
        `toFixed(1) + '%'`（§6）。**含负值的序列不能放这里**：右轴量程写死 `0..ymax`、
        根本不看 `line.values`，负值点会被顶到轴外而画面不报错（§3.14）。
    """
    win = win or W25
    cols = [s[0] for s in segs if isinstance(s[0], str)]
    need = list(cols) + ([total_col] if total_col else [])
    lcol = (line or {}).get('col')
    if lcol:
        need.append(lcol)
    win2, xl2, data, why = _resolve('stacked_dual', need, win)

    def _arr(src):
        return data[src] if isinstance(src, str) else list(np.asarray(src, float))[-len(win2):]

    raw = [_arr(s[0]) for s in segs]
    names = [s[1] for s in segs]
    colors = [s[2] for s in segs]
    if total_col:
        tot = data[total_col]
        resid = [num__exlib(tot[i]) - sum(num__exlib(r[i]) for r in raw) for i in range(len(win2))]
        if not resid_name:
            raise SystemExit(f'Exhibit {n}：给了 total_col={total_col!r} 却没给 resid_name —— '
                             f'残差段必须命名（CHART_KINDS §3.14），'
                             f'一段无名的灰在页面上等于「这块是什么我也不知道」。')
        neg = [i for i, v in enumerate(resid) if np.isfinite(v) and v < 0]
        if neg:
            raise SystemExit(
                f'Exhibit {n} 的残差段「{resid_name}」有 {len(neg)} 格为负'
                f'（首格 {xl2[neg[0]]}：{resid[neg[0]]:.4f}）—— 2026-09 起 stacked_dual '
                f'的左轴能画负段，但那会让柱高不再等于列合计（CHART_KINDS §3.14），'
                f'占比型堆叠尤其不能有；请改用不含这一段的分段清单。')
        raw.append(resid)
        names.append(resid_name)
        colors.append(SEG_RESID_COLOR)

    _color_guard(n, 'stacked_dual', colors, rhs_color=(line or {}).get('color'))

    if pct100:
        tt = [sum(num__exlib(r[i]) for r in raw) for i in range(len(win2))]
        raw = [[(num__exlib(r[i]) / tt[i] * 100 if tt[i] else float('nan')) for i in range(len(win2))]
               for r in raw]
        if fmt != 'pct1':
            raise SystemExit(f'Exhibit {n}：100% 堆叠必须显式给 fmt="pct1"（收到 {fmt!r}）—— '
                             f'不给会退回 f0c，表格视图把占比截成整数、相加印成 99 或 101。')

    stacks = [{'name': nm, 'color': cl, 'values': L(v)} for v, nm, cl in zip(raw, names, colors)]
    if labels:
        # 段内标签写死 `comma(v, 0)`（只印整数、不跟 fmt）—— 百分数 / 百分点口径的堆叠
        # 一律不开（CHART_KINDS §3.14：−0.9 印成 −1、+6.4 印成 6，两位有效数字全丢）。
        if pct100 or fmt.startswith(('pct', 'pp')):
            raise SystemExit(f'Exhibit {n}：占比 / 百分点口径的堆叠不许开段内标签 —— '
                             f'引擎的段内标签写死 comma(v, 0)，只印整数。')
        for s in stacks:
            s['label'] = True
    _dense_guard('stacked_dual', n, [(s['name'], s['values']) for s in stacks])

    ex = {'n': n, 'kind': 'stacked_dual', 'title': title, 'ylab': ylab, 'fmt': fmt,
          'xlabels': xl2, 'stacks': stacks}
    if line:
        lv = line.get('values')
        lv = _arr(lcol) if lcol else list(np.asarray(lv, float))[-len(win2):]
        if not ylab2:
            raise SystemExit(f'Exhibit {n}：给了 line 就是双轴图，必须给 ylab2 —— '
                             f'不给右边距只有 42px，而且没人知道右轴是什么。')
        fin = [v for v in lv if np.isfinite(num__exlib(v))]
        if any(v < 0 for v in fin):
            raise SystemExit(
                f'Exhibit {n} 的右轴线含负值（最小 {min(fin):.3f}）—— stacked_dual 的右轴'
                f'量程写死 `ticks(0, rc.ymax || 60, 6)`、根本不看 line.values，'
                f'负值点会被顶到轴外而画面不报错，读者只会读到「这条线从没转过负」。'
                f'要「堆叠柱 + 会转负的次轴线」请走 gs_bar 的 stacks + yoy（§3.6.2）。')
        ymax = line.get('ymax') or (math.ceil(max(fin) / 10.0) * 10 if fin else 60)
        ex['line'] = {'name': line['name'], 'color': line.get('color', 'GREEN'),
                      'values': L(lv), 'ymax': ymax}
        ex['ylab2'] = ylab2

    # 不可见段 —— 必须在图注里说破，不然读者会把「画不出来」读成「这个月没有」
    inv, thr = _invisible_segments([[num__exlib(x) for x in s['values']] for s in stacks],
                                   _SD_TOP[bool(line)])
    tallest = max([sum(num__exlib(s['values'][i]) for s in stacks)
                   for i in range(len(xl2))] or [0.0]) or 1.0
    smallest = min(min(num__exlib(v) for v in s['values'] if np.isfinite(num__exlib(v))) for s in stacks)
    SEG_THR_LOG[n] = {'thr': thr, 'thr_pct': thr / tallest * 100,
                      'min_seg': smallest, 'invisible': inv}
    seg_note = ''
    if inv:
        bits = '；'.join(
            f'<b>{stacks[k]["name"]}</b>（{cnt} 格，最小 {mn:.2f}）' for k, cnt, mn in inv)
        seg_note = (f'⚠️ <b>下面这些段在图上画不出来</b>：{bits}。'
                    f'引擎的段高是「本段像素高减去 {_SD_GAP}px 白缝」，不足这条缝就是 0 高、'
                    f'完全不画（阈值按本图量程现算 = {thr:.3f}，'
                    f'相当于最高那根柱的 {thr / tallest * 100:.2f}%）。'
                    f'这不是「那几个月没有这块业务」—— 逐格读数走卡片右上角的「表格」视图。')
    ex['note'] = (note or '') + why + seg_note
    if not ex['note']:
        ex.pop('note')          # 空 note 会在卡片下方留一行空的「Note:」
    if src_extra:
        ex['src_extra'] = src_extra
    WIN_LOG[n] = {'win': win2, 'cols': need}
    return ex

# ══════════════════════════ §5  qtr_bar ══════════════════════════════════
def qtr_bar(n, qidx, values, title, ylab, fmt, legend, line_values=None,
            line_name='y/y（RHS）', line_color='GREEN', line_yfmt='pct0',
            note=None, src_extra=None, label_fmt=None, partial_months=None):
    """季度柱 + 右轴 y/y。引擎确有这一支（`kind === 'qtr_bar'`，纵轴
    `y0 = min(0, mn×1.15)`、`y1 = mx×1.32`，1.32 是给柱顶**竖排**数值标签留的）。

    ⚠️ 本页**不画不完整季、也不用 `partial_months`**（季度块的五条粒度规则之一）。
    参数留着只是为了让「传了就一定是有意的」这件事看得见：传进来就在这里停机，
    因为引擎对未满季的处置是**强制作废右轴那条线的最后一点**（绘图/量程/表格/
    tooltip 四处一致），页面上会出现一根没有同比的柱 —— 那正是本页要避免的东西。

    ⚠️ 季度轴上**画不了 2013-11 的断点竖线**（下标要在季度里数，而本页季度左端是
    2016Q1，断点在它左边 26 个月）—— `draw_break()` 会照实返回不画，见 §8。
    """
    if partial_months is not None:
        raise SystemExit(
            f'Exhibit {n}：本页季度块不画不完整季、也不用 partial_months '
            f'（收到 {partial_months}）。不完整季要么不画要么标注，不能让引擎去作废'
            f'右轴那一点 —— 页面上会留下一根没有同比的柱。')
    if len(values) != len(qidx):
        raise SystemExit(f'Exhibit {n}：values {len(values)} 与季度轴 {len(qidx)} 不等长。')
    ex = {'n': n, 'kind': 'qtr_bar', 'title': title, 'ylab': ylab, 'fmt': fmt,
          'legend': legend, 'xlabels': [qlab__exlib(q) for q in qidx], 'values': L(values),
          'qtr_months': 3}
    if label_fmt:
        ex['label_fmt'] = label_fmt
    if line_values is not None:
        if len(line_values) != len(qidx):
            raise SystemExit(f'Exhibit {n}：line.values 与季度轴不等长。')
        ex['line'] = {'name': line_name, 'color': line_color,
                      'values': L(line_values), 'yfmt': line_yfmt}
    if note:
        ex['note'] = note
    if src_extra:
        ex['src_extra'] = src_extra
    WIN_LOG[n] = {'win': list(qidx), 'cols': []}
    return ex

# ══════════════════════════ §6  seasonality ══════════════════════════════
def seasonality(n, col, title, ylab, fmt, note=None, src_extra=None,
                years=None, months=None):
    """灰 = 过去 N 年同月均值 / 蓝 = 实际，配对柱。

    ⚠️ **本函数目前没有调用方**：定稿的 17 张图序（Ex2–Ex18）里没有季节性图。
    留在库里是因为本段的任务书点名要它（「两条头条列各一张」），而两份说明在这一点上
    冲突 —— 谁对由页面 owner 裁决，不由本文件替他拍。库里放着不花任何代价；
    真要加图时它已经把「N 年是几年」这件事按 single.py 的 `ex_season` 办好了：
    哪个月有几年就用几年、缺的年份不补，实际用到的 N 写进 `base.name`。

    `base` 与 `actual` 两个对象都必须存在（缺一个抛异常，§1.3）。
    """
    years = years or SG.SEASON_YEARS
    months = months or SG.WIN_SHORT
    c = cmeta(col)
    s = df[col].dropna()
    if s.empty:
        raise SystemExit(f'Exhibit {n}（{col}）整列无值，画不出季节性。')
    win = [s.index[-1] - k for k in range(months - 1, -1, -1)]
    base, used = [], []
    for p in win:
        prior = [num__exlib(s.get(p - 12 * k, np.nan)) for k in range(1, years + 1)]
        prior = [x for x in prior if np.isfinite(x)]
        used.append(len(prior))
        base.append(float(np.mean(prior)) if prior else float('nan'))
    nyr = max(used) if used else 0
    if not nyr:
        raise SystemExit(f'Exhibit {n}（{col}）窗口内没有任何一个同月历史年，画不出灰柱。')
    act = cvals(col, win)
    ex = {'n': n, 'kind': 'seasonality', 'title': title, 'ylab': ylab,
          'fmt': fmt, 'label_fmt': fmt, 'xlabels': [mlab(p) for p in win],
          'base': {'name': f'过去 {nyr} 年同月均值', 'color': 'GRAY', 'values': L(base)},
          'actual': {'name': '实际', 'color': 'MBLUE', 'values': L(act)}}
    d = act[-1] - base[-1] if np.isfinite(base[-1]) else float('nan')
    gap = SG.ratio_diff_txt(d, c) if SG.col_is_ratio(c) else pctf(
        (d / base[-1]) if (np.isfinite(d) and base[-1]) else float('nan'), 1)
    ex['note'] = (note or '') + (
        f'灰柱 = 该月份在过去最多 {years} 年里的同月均值（实际用到 {nyr} 年，'
        f'哪个月有几年就用几年，缺的年份不补），蓝柱 = 实际。'
        f'{mlab(win[-1])} 实际 {comma(act[-1], 0)} {c["unit"]} '
        f'vs 同月常态 {comma(base[-1], 0)}（{gap}）。')
    if src_extra:
        ex['src_extra'] = src_extra
    WIN_LOG[n] = {'win': win, 'cols': [col]}
    return ex

# ══════════════════════════ §7  heat_matrix ══════════════════════════════
def heat_matrix(n, cols, title, legend=None, note=None, src_extra=None,
                months=None, reverse=False):
    """**多序列 × 近 N 个月**的同比矩阵（rows = 序列名）。

    ⚠️ 这与 build/cme.py:1773 的 `heat()` **不是一回事**：那张是「单列 × 年 × 月」，
    rows 是年份、cols 是 Jan..Dec，用来让同一个月份跨年份上下对齐。照抄那份会得到
    一张只画一条序列的矩阵，而本页 Ex11 要的是 12 个官方单列产品横向比。
    形状照 build/single.py 的 `ex_heat`（rows = 各列的中文名，cols = 近 N 个月）。

    **两道同质性硬检查**（都从 `ex_heat` 端过来，一个字不改判据）：
      ① 比率列与量列不许混：格内一半是百分点差、一半是百分比变化，而整张矩阵
         **只有一条色标**，颜色深浅会被读成「谁涨得多」。
      ② 比率里再分一次：分子是钱的差**还是钱**（USD/contract），分子是百分数的差
         才是百分点。两类混在一起就是拿 pp 和 USD/contract 比高低。
    判据一律走 `SG.col_is_ratio` / `SG.col_is_money_ratio`，本文件不自己写。

    heat_matrix **不支持** xlabels / break_at / ycap / yfloor / xstep / xrot / height
    （高度 = 行数 × cell_h + 18），所以 `full: True` 在这里手写 —— `mrwin.layout_all()`
    对 heat_matrix 整张 `continue`，不写就永远是半栏，24 列在半栏里读不出数字。
    """
    months = months or SG.WIN_HEAT
    win = W25[-months:]
    metas = [cmeta(k) for k in cols]

    kinds = {SG.col_is_ratio(c) for c in metas}
    if len(kinds) > 1:
        raise SystemExit(
            f'Exhibit {n} 的热力矩阵里比率列与量列混在一起 —— 格内一半是百分点差、'
            f'一半是百分比变化，而整张矩阵共用一条色标。'
            f'比率列：{[c["zh"] for c in metas if SG.col_is_ratio(c)]}；'
            f'量列：{[c["zh"] for c in metas if not SG.col_is_ratio(c)]}。'
            f'出路：拆成两张矩阵。')
    ratio = bool(kinds and kinds.pop())
    money_kinds = {SG.col_is_money_ratio(c) for c in metas} if ratio else {False}
    if len(money_kinds) > 1:
        raise SystemExit(
            f'Exhibit {n} 的热力矩阵里「分子是钱」的比率与「分子是百分数」的比率混在'
            f'一起 —— 格内一半是 {metas[0]["unit"]} 的差、一半是百分点，共用一条色标。'
            f'钱：{[c["zh"] for c in metas if SG.col_is_money_ratio(c)]}；'
            f'百分点：{[c["zh"] for c in metas if not SG.col_is_money_ratio(c)]}。')
    money = bool(money_kinds and money_kinds.pop())

    rows, M, dropped = [], [], []
    for c in metas:
        yv = SG.yoy_line(df[c['col']], win, pct_series=SG.col_is_ratio(c))
        if not np.isfinite(np.asarray(yv, float)).any():
            dropped.append(c['zh'])
            continue
        rows.append(c['zh'])
        M.append(L(yv))
    if not rows:
        raise SystemExit(f'Exhibit {n}：{months} 个月窗口内一行同比都算不出来。')

    kept = [c for c in metas if c['zh'] in set(rows)]
    mdec = max(SG.FMT_INFO[c['fmt']][0] for c in kept) if money else 0
    ex = {'n': n, 'kind': 'heat_matrix', 'full': True, 'title': title,
          'fmt': (f'f{min(mdec, 3)}' if money else 'pp1') if ratio else 'pct0z',
          'rows': rows, 'cols': [mlab(p) for p in win], 'matrix': M,
          'legend': legend or (f'同比（{kept[0]["unit"]} 的差）' if money else
                               '同比（百分点差 pp）' if ratio else '同比 y/y（单月）'),
          'row_head': '序列', 'cell_h': 20,
          'row_lab_w': max(SG.label_width(r) for r in rows)}
    if reverse:
        ex['reverse'] = True
    # fmt 用 pct0z 而不是 pct0：pct0 会把 −0.4% 印成「-0%」（一个不存在的数）。
    ex['note'] = (note or '') + (
        f'格内是<b>单月同比</b>'
        + (f'的差，单位 {kept[0]["unit"]}（分子是钱，差还是钱，所以不写 pp）'
           if money else '的百分点差（pp）' if ratio else '（%）')
        + f'，不是水平值。色标由全部有限值的 5/95 分位共用一条 —— '
          f'<b>每张矩阵各算各的色标，两张矩阵之间颜色不可比</b>。'
          f'列数 {len(cols)} > {MAX_LINES}，超出「一张图最多 {MAX_LINES} 条靠颜色区分的'
          f'序列」的上限，故用行标签区分身份；水平值请看末尾核对表。'
        + (f'（{"、".join(dropped)} 整行没有可算的同比，已不列入。）' if dropped else '')
        + '热力矩阵不支持断点竖线（矩阵没有连续横轴），口径断点见「口径与方法说明」。')
    if src_extra:
        ex['src_extra'] = src_extra
    WIN_LOG[n] = {'win': win, 'cols': list(cols)}
    return ex

# ══════════════════════════ §8  draw_break ═══════════════════════════════
# 断点在**全序列**上的下标。语义是「从这一期起与左侧不可比」，线画在该期左缘。
_BRK_ALL = next((i for i, p in enumerate(ALL) if str(p) >= BREAK_MONTH), None)

#: 断点在**月度图横轴**（左端 W25[0]）上的下标。断点落在窗口左端或更早 → None。
#: ICE 实际就是这一档：BREAK_MONTH = 2013-11，而 WIN_FROM = 2016-01 —— 断点在
#: 图窗左边 26 个月，**本页没有一张图跨得过它**，所以竖线一张都画不出来。
#: 这不是「忘了画」，是数据摆在那里的结果；§9 的 `break_audit()` 每次构建现验。
BRK_I = None if (_BRK_ALL is None or _BRK_ALL <= _I0) else _BRK_ALL - _I0

#: 画了竖线的图号（现读，不写死）。
BRK_DRAWN = []

def draw_break(e, extra=''):
    """给一张跨过 2013-11 断点的**月度**图挂上红色竖虚线 + 图注说明。

    **一律只给 `break_at`、不给 `break_label`** —— 抄 build/cboe.py 的 draw_break。
    那边记着理由：竖排标签是 rotate(-90) 从绘图区顶端挂下来的一条长条，与柱值标签
    按构造垂直相交；引擎有一道避让（沿同一条竖线找空白），找不到就原地不动、
    直接印穿数字。cboe 实测窗口放到 2016-01 之后 23 个字压出 6 处 🔴。
    去掉标签不丢信息：断点是什么由本图注 + 页尾 notes 逐条点名。

    **哪几张画不了**（不是漏了，是引擎/口径决定的）：
      · 热力矩阵（Ex11）—— 没有连续横轴，引擎不支持 break_at；
      · 季度轴（Ex5–Ex8）—— 下标要在季度里数，而本页季度左端 2016Q1 已在断点右边；
      · `kind:'table'`（Ex1 / Ex9 / Ex19）—— 根本不过引擎。
      · **以及本页其余全部图**：见 `BRK_I` 那段，断点在图窗左边 26 个月。
    """
    if not BRK_I:
        return e
    e['break_at'] = BRK_I
    BRK_DRAWN.append(e['n'])
    _roll = ('次轴那条单月同比更要留神：它比的是当月与去年同月，虚线右侧头 12 个月的点'
             '分子在实际口径、<b>分母仍落在虚线左侧</b>，是跨口径相除；'
             if e.get('yoy') else '')
    e['note'] = (e.get('note') or '') + (
        f'⚠️ 红色竖虚线左侧（{BRK_I} 期）的 NYSE 各列是<b>追溯并入的形式数</b>'
        f'（ICE 于 {BREAK_MONTH} 完成收购 NYSE Euronext），与其后各期不完全可比 —— '
        f'跨线读水平值只当量级看，跨线的同比与环比同样受影响。' + _roll + extra)
    return e

def break_audit(exs):
    """构建期兜底：**「谁跨了断点却没画线」与「谁画了线」两侧都要对得上**。

    抄 build/cboe.py 那一节的做法（现读 payload，不写死图号）：一张连续横轴的图，
    左端早于断点月却没有 `break_at`，就是一条静默的口径谎话。
    本页现在的正确答案是「两侧都空」；哪天 WIN_FROM 往前挪，这里会自己响。
    """
    crossers = []
    for e in exs:
        if e.get('kind') in ('heat_matrix', 'table') or not e.get('xlabels'):
            continue
        w = WIN_LOG.get(e['n'], {}).get('win') or []
        if not w or not isinstance(w[0], pd.Period) or w[0].freqstr != 'M':
            continue                        # 季度轴：断点下标要在季度里数，另论
        if str(w[0]) < BREAK_MONTH <= str(w[-1]) and e.get('break_at') is None:
            crossers.append(e['n'])
    if crossers:
        raise SystemExit(f'Exhibit {crossers} 的横轴跨过 {BREAK_MONTH} 却没画 break_at —— '
                         f'CONTRACT §5.2：口径断点必须画出来，不能只靠图注提一句。')
    drawn = [e['n'] for e in exs if e.get('break_at') is not None]
    if sorted(drawn) != sorted(BRK_DRAWN):
        raise SystemExit(f'break_at 的账对不上：payload 里是 {sorted(drawn)}，'
                         f'draw_break() 记的是 {sorted(BRK_DRAWN)}。')
    labeled = [e['n'] for e in exs if e.get('break_label') is not None]
    if labeled:
        raise SystemExit(f'Exhibit {labeled} 给了 break_label —— 本页一律只画线不挂标签'
                         f'（理由见 draw_break 的 docstring）。')
    return drawn

# ══════════════════════ §9  排版裁决 & 收口 ══════════════════════════════
def finalize(exs):
    """**顺序是承重的**：`mrwin.layout_all()` → `axisfmt.fix_all()`。

    · `mrwin.layout_all(ex)`：逐张判「通栏 / x 标签抽稀」，把实测 px 追加进图注。
      `full` / `xstep` 就是在这里补上的，所以调用点一律不手写（cme.py:1615）。
      它还会把引擎的默认 `xrot`（n > 20 → 90）显式写进 payload —— 不写进去，
      `layout()` 那条「只对 xrot == 90 的轴抽稀」永远命中不了。
    · `axisfmt.fix_all(ex)`：按真实刻度把 yfmt 升到够用的位数，消灭
      「0.0pp 0.0pp 0.0pp」那种相邻网格线同一个数字的轴。必须在 layout 之后 ——
      通栏与否会改刻度密度。

    ⚠️ **`chartscale.fix_all()` 本页不调**，虽然它按契约是在 axisfmt 之前的那一步。
    理由：它做的是**显示缩放**（把整组数除以 1e3/1e6 并往 `ylab` 里追加「（百万）」）。
    而本页的 `unit` 字符串是承重的 —— 它逐字喂给 `SG.col_is_ratio` /
    `SG.rhs_ylab2`，也逐字进表头与释义板；被改写一次，页面上就出现两种单位写法，
    而且不报错。这里只调只读的 `chartscale.audit()`，把「哪个标签超预算」印在
    构建期日志上（与 cme.py 那段 WONT_FIX 的处置一致：发现了、量过了、
    修它要动 assets/charts.js，不在本轮范围）。
    """
    mrwin.layout_all(exs)
    tight = chartscale.audit(exs)
    if tight:
        print('[chartscale.audit] 标签超预算（只报告不修，理由见 finalize 的 docstring）：')
        for n, sym, det in tight:
            print(f'    Exhibit {n}  {sym}  {det}')
    return axisfmt.fix_all(exs)

# ==========================================================================
# 【summary】
# ==========================================================================

# -*- coding: utf-8 -*-
"""build/ice.py 的 **Exhibit 1 汇总表** 段（独立可跑的草稿，合并时删掉 __main__ 块）。

本段负责三件事：
  ① `COL__summary` —— 手写页的列元数据表。手写页没有引擎那套 `unit` 推导，所以这里保留一份
     与 `build/single.py` 的 spec 列字典**完全同形**的表，再把 single.py 的判据
     （`col_is_ratio` / `col_is_money_ratio` / `ratio_diff_txt`）直接喂给它。
     ⚠️ `unit` 字符串是**承重**的，不是给人看的注解：它同时决定「这一列的差算不算
     百分点」和「算不算钱」。逐字抄自 build/specs/ice.py，改一个字判定就会翻掉且不报错
     （build/specs/ice.py:659-661 记着 `oi_rates_kcontracts` 那个假阳性：列名里有
     `rates`，`yoy.classify()` 判成 ratio，是 `k contracts` 这个单位把它挡住的）。
     文件底部 `_assert_caliber_baseline()` 把这条依赖钉成构建期闸门。
  ② `summary_block(df, cur, prv, yag)` —— 本月 / 上月 / 去年同月 ‖ m/m | y/y | 3Y %ile。
     抄 build/cboe.py:383 的**带参**形态（可单测），不抄 build/cme.py:753 那种读模块级
     常量 CUR/PRV/YAG 的写法。
  ③ `_sum_provenance()` / `_factor()` / `_sum_src_txt()` —— 表注里「哪几行不是 ICE
     直接披露的」那句话，从**活的列集合**现算。抄 build/cme.py:688-752；那里记着翻车
     经过：原先写死的「全部为官方披露值，无推导」被同一张表里的换算列当场证伪。

## 行选择（手写页可以自由选行，引擎是无条件每列一行）

现状（引擎版，build/specs/ice.py + build/single.py:3754）是**无条件每列一行**：
headline 2 行 + 8 个组共 52 行 = 54 个数据行，加 9 条组带 = 63 行 ≈ 1870px，
排在第一张图之前，占整份文档约 10%（接近 CME 整个汇总块的四倍）。
本段是 **31 个数据行 + 7 条组带 = 38 行**：砍掉 28 行、新增 5 行
（「利率」「股指与 FX」两条量腿 + 三套交易日）。砍法只用两条可复述的规则，
不逐行拍脑袋：

  **规则 A（组内取全或不取，不取一半）** —— 表里的一条组带若对应页面上的一张堆叠图，
  就把那张图堆的段全给，否则读者拿表对不上图。所以 OI 给四条叶子（与 Ex12 一致，
  不给 `oi_commodities` / `oi_financials` 那两条段之和），Tape 份额给 A/B/C 三条。

  **规则 B（页面上已经有「水平 + 同比」两张图的板块，表里不重复它的分项）** ——
  能源六个子项在页面上有「按产品的堆叠水平图」和「十二个单列产品 × 近 24 个月单月
  同比」的矩阵两张图，分项的水平与同比都已在页面上、且分辨率高于表里的一格，表里
  只留「能源合计」一行；OI 只有一张水平图、没有同比图，所以给四条叶子的月度读数。

被砍掉的 28 行逐条理由见 `SUM_ROWS` 上方的清单；新增的 5 行理由见 `COL__summary` 里
`adv_rates_kcontracts` 与 `SUM_ROWS` 末尾那条组带上方的注释。
"""

sys.path.insert(0, os.path.join(ROOT, 'build'))

def num__summary(v, dec=0):
    """cme.py:206 的 num__summary：缺失印「—」（表格里的空位要看得出是没有数，不是零）。"""
    if v is None or not np.isfinite(v):
        return '—'
    return f'{v:,.{dec}f}'

# ══════════════════════ 1. COL__summary：列元数据表（与引擎同形）══════════════════════
#
# ⚠️ `unit` 逐字抄 build/specs/ice.py，合法值只有七种：
#     'k contracts/day' 'k contracts' 'USD/contract' 'USD/100 shares'
#     'mn shares/day'   'USD bn/month' '%'
# 例外只有交易日那三列 —— 它们**不在** build/specs/ice.py 里（引擎那版没有交易日行），
# 所以七种里没有它们的量纲。给 'days'：两道判据都认不出它（`unit_is_ratio` 要 '%'
# 或「/ 可数活动单位」，'days' 两者都不是），因此它照旧走 '% y/y'，与量列同档。
# 这一条同样由 `_assert_caliber_baseline()` 钉住。
def _c__summary(col, zh, unit, fmt, stock=False, scale=1):
    """列字典的构造器。引擎在 `Page` 里给每个列字典补齐 scale / stock / ratio 三个
    可选键（`single.py:1653` 的 `ser()` 直接读 `c['scale']`），手写页没有那一步，
    所以在这里补 —— 少补一个键，下游是 KeyError 还是**静默按 1 处理**取决于调用点，
    后者才是真正的坑。`ratio` 一律留 None（= 由 `col_is_ratio()` 自己判），本页没有
    任何一列需要显式覆盖。"""
    return {'col': col, 'zh': zh, 'unit': unit, 'fmt': fmt,
            'stock': stock, 'scale': scale, 'ratio': None}

COL__summary = {
    # ── 头条 ──
    'adv_futures_options_kcontracts': _c__summary(
        'adv_futures_options_kcontracts', '衍生品总 ADV', 'k contracts/day', 'f0c'),
    'adv_nyse_us_cash_handled_mnsh': _c__summary(
        'adv_nyse_us_cash_handled_mnsh', 'NYSE 美股现货 ADV（handled）',
        'mn shares/day', 'f0c'),

    # ── 合约构成与收入四腿的量 ──
    'adv_commodities_kcontracts': _c__summary(
        'adv_commodities_kcontracts', '大宗商品合计', 'k contracts/day', 'f0c'),
    'adv_energy_kcontracts': _c__summary(
        'adv_energy_kcontracts', '能源', 'k contracts/day', 'f0c'),
    'adv_ag_metals_kcontracts': _c__summary(
        'adv_ag_metals_kcontracts', '农产品与金属', 'k contracts/day', 'f0c'),
    'adv_financials_kcontracts': _c__summary(
        'adv_financials_kcontracts', '金融合计（不含单股）', 'k contracts/day', 'f0c'),
    # 派生：ICE 官方**没有**「利率合计」「股指与 FX 合计」这两行，但 rpc_rates_usd 与
    # rpc_other_financials_usd 这两条费率对应的量恰恰就是这两个和（六条腿的配对见
    # 本轮改写的收入构造）。表里给出来，是为了让「量」行与下一条组带的「价」行**逐行配对**
    # ——读者能自己做一次 量×价，而不必相信页面上那张 bridge。
    'adv_rates_kcontracts': _c__summary(
        'adv_rates_kcontracts', '利率（短期 + 中长期）', 'k contracts/day', 'f0c'),
    'adv_other_financials_kcontracts': _c__summary(
        'adv_other_financials_kcontracts', '股指与 FX', 'k contracts/day', 'f0c'),

    # ── 每张收入 RPC（滚动三月均）。四条**叶子**，不含 rpc_commodities / rpc_financials
    #    那两条上层聚合 ──
    'rpc_energy_usd': _c__summary('rpc_energy_usd', '能源', 'USD/contract', 'f2'),
    'rpc_ag_metals_usd': _c__summary('rpc_ag_metals_usd', '农产品与金属', 'USD/contract', 'f2'),
    'rpc_rates_usd': _c__summary('rpc_rates_usd', '利率', 'USD/contract', 'f2'),
    'rpc_other_financials_usd': _c__summary(
        'rpc_other_financials_usd', '股指与 FX', 'USD/contract', 'f2'),

    # ── 月末未平仓：**存量**（stock=True），同比是点对点 ──
    'oi_energy_kcontracts': _c__summary(
        'oi_energy_kcontracts', '能源', 'k contracts', 'f0c', stock=True),
    'oi_ag_metals_kcontracts': _c__summary(
        'oi_ag_metals_kcontracts', '农产品与金属', 'k contracts', 'f0c', stock=True),
    # ⚠️ 列名里的 `rates` 让 `yoy.classify()` 判成 ratio（假阳性），挡住它的是
    #    `k contracts` 这个单位。见 build/specs/ice.py:659-661。
    'oi_rates_kcontracts': _c__summary(
        'oi_rates_kcontracts', '利率', 'k contracts', 'f0c', stock=True),
    'oi_other_financials_kcontracts': _c__summary(
        'oi_other_financials_kcontracts', '股指与 FX', 'k contracts', 'f0c', stock=True),

    # ── NYSE ──
    'adv_us_equity_options_industry_kcontracts': _c__summary(
        'adv_us_equity_options_industry_kcontracts', '全美股票/ETF 期权行业总量',
        'k contracts/day', 'f0c'),
    'adv_nyse_equity_options_kcontracts': _c__summary(
        'adv_nyse_equity_options_kcontracts', 'NYSE 两所合计', 'k contracts/day', 'f0c'),
    'share_nyse_equity_options': _c__summary(
        'share_nyse_equity_options', 'NYSE 期权份额（官方直接给）', '%', 'pct1', scale=100),
    'rpc_nyse_equity_options_usd': _c__summary(
        'rpc_nyse_equity_options_usd', 'NYSE 期权 RPC', 'USD/contract', 'f2'),
    'share_nyse_us_cash_matched': _c__summary(
        'share_nyse_us_cash_matched', 'NYSE 全美 matched 份额', '%', 'pct1', scale=100),
    'share_nyse_tapeA_matched': _c__summary(
        'share_nyse_tapeA_matched', 'Tape A 份额', '%', 'pct1', scale=100),
    'share_nyse_tapeB_matched': _c__summary(
        'share_nyse_tapeB_matched', 'Tape B 份额', '%', 'pct1', scale=100),
    'share_nyse_tapeC_matched': _c__summary(
        'share_nyse_tapeC_matched', 'Tape C 份额', '%', 'pct1', scale=100),
    'rpc_nyse_us_cash_usd_per100sh': _c__summary(
        'rpc_nyse_us_cash_usd_per100sh', '现货 RPC（每 100 股）', 'USD/100 shares', 'f3'),

    # ── CDS（当月总量，不是日均：表标题里没有 daily 字样）──
    'cds_total_notional_usdbn': _c__summary(
        'cds_total_notional_usdbn', '合计', 'USD bn/month', 'f0c'),
    'cds_client_notional_usdbn': _c__summary(
        'cds_client_notional_usdbn', '客户盘', 'USD bn/month', 'f0c'),
    'cds_nonclient_notional_usdbn': _c__summary(
        'cds_nonclient_notional_usdbn', '非客户盘', 'USD bn/month', 'f0c'),

    # ── 三套交易日 ──
    'trading_days_commod': _c__summary('trading_days_commod', '大宗商品交易日', 'days', 'f0'),
    'trading_days_rates': _c__summary('trading_days_rates', '金融（利率）交易日', 'days', 'f0'),
    'trading_days_us_equities': _c__summary(
        'trading_days_us_equities', '美股交易日', 'days', 'f0'),
}

# 冻结基线：这五列的判定是页面上四类读数（美元差 / 百分点差 / % 同比）的分水岭，
# 已在真实数据上实测过。写成断言而不是注释，是因为它依赖的是 `unit` 里的**字符串**
# 与 `build/yoy.py` 的 `classify()`，两边任何一处改动都不会报错、只会静默翻掉。
_CALIBER_BASELINE = {
    'rpc_energy_usd':                (True,  True,  'USD/contract, y/y 差（单月）'),
    'rpc_nyse_us_cash_usd_per100sh': (True,  True,  'USD/100 shares, y/y 差（单月）'),
    'share_nyse_tapeA_matched':      (True,  False, 'pp y/y（单月）'),
    'oi_rates_kcontracts':           (False, False, '% y/y（单月）'),
    'adv_energy_kcontracts':         (False, False, '% y/y（单月）'),
}

def _assert_caliber_baseline():
    got = {}
    for k, (r0, m0, y0) in _CALIBER_BASELINE.items():
        c = COL__summary[k]
        r, m, y = SG.col_is_ratio(c), SG.col_is_money_ratio(c), SG.rhs_ylab2(c, mom=True)
        got[k] = (r, m, y)
        if (r, m, y) != (r0, m0, y0):
            raise SystemExit(
                f'口径基线翻了：{k} 实测 ratio={r} money={m} ylab2={y!r}，'
                f'基线是 ratio={r0} money={m0} ylab2={y0!r}。'
                f'多半是 COL__summary 里的 unit 串被改动了 —— 那串字是承重的，'
                f'不是注解（见 build/specs/ice.py:659-661 的假阳性）。')
    # 交易日三列必须两道判据都不认（否则它们的 m/m 会印成「+1.0pp」）
    for k in ('trading_days_commod', 'trading_days_rates', 'trading_days_us_equities'):
        if SG.col_is_ratio(COL__summary[k]):
            raise SystemExit(f'{k} 被判成比率列 —— 它的差会印成百分点，那是句胡话。')
    return got

# ══════════════════════════ 2. 读数据 + 派生列 ══════════════════════════
#: 派生列的**算式登记处**。`_sum_provenance()` 判不出来源时会到这里找，找不到就停机；
#: 登记的字串会原样印进表注，所以写成读者看得懂的话。
SUM_CALC = {
    'adv_rates_kcontracts': (
        '短期利率 ADV + 中长期利率 ADV（ICE 官方没有「利率合计」这一行，'
        '但费率行 rpc_rates_usd 对应的正是这两条腿之和）'),
    'adv_other_financials_kcontracts': (
        '股指 ADV + FX 与 USDX ADV（同上，对应费率行 rpc_other_financials_usd；'
        '⚠ ICE 的表头把这一行写作 "COMMODITIES & OTHER FINANCIALS"，'
        '但它<b>不含信用</b>，CDS 另有自己的表）'),
}

def load__summary():
    if not os.path.exists(CSV):
        raise SystemExit(f'找不到数据文件: {CSV}')
    df = pd.read_csv(CSV)
    df['month'] = pd.PeriodIndex(df['month'], freq='M')
    df = df.set_index('month').sort_index()
    for c in df.columns:
        df[c] = pd.to_numeric(df[c], errors='coerce')

    idx = list(df.index)
    bad = [(str(idx[i - 1]), str(idx[i])) for i in range(1, len(idx))
           if (idx[i] - idx[i - 1]).n != 1]
    if bad:
        raise SystemExit(f'月份序列不连续: {bad}')

    # 派生列。**不做** adv_futures_options × 交易日 这种「乘回当月合计」的事：
    # 总 ADV 横跨大宗商品与金融两套日历，没有哪一套能代表它（三套交易日在 188 个月里
    # commod≠rates 有 118 个月）。派生只落在**单一日历内**能配对的两个和上。
    df['adv_rates_kcontracts'] = (df['adv_stir_kcontracts']
                                  + df['adv_mltir_kcontracts'])
    df['adv_other_financials_kcontracts'] = (df['adv_equity_index_kcontracts']
                                             + df['adv_fx_credit_kcontracts'])
    return df

# ══════════════════════════ 3. 行选择 ══════════════════════════
#
# ── 被砍掉的 28 行（引擎版 54 个数据行 → 本版 31），逐条理由 ────────────────
#   · **2 行重复**：引擎无条件先画 headline 再画各组，而 adv_futures_options 与
#     adv_nyse_us_cash_handled 两列在 headline 与组里各出现一次 —— 同一列在同一张表里
#     出现两次，读者会以为那是两条不同的序列。本版只在「头条」那条组带上给一次。
#   · 能源六子项（Brent / Gasoil / 其他原油 / 天然气 / 电力 / 环境权益）—— 规则 B：
#     页面上「能源 ADV 按产品」给水平、「十二个单列产品 × 近 24 个月」的矩阵给同比，
#     分项的两种读数都已在页面上且分辨率更高，表里只留「能源」一行。
#   · 农金两子项（糖 / 其他农金）—— 同上，且同在那张矩阵里。
#   · adv_stir / adv_mltir / adv_equity_index / adv_fx_credit 四条单列 —— 它们已被
#     合成「利率」「股指与 FX」两行，与费率行逐行配对；再各留一行等于把同一件事数两遍。
#   · adv_single_stock_kcontracts —— 官方明说已从 TOTAL FINANCIALS / ADV / RPC / OI
#     里剔除，它与本表任何一行都不构成加总关系，留着只会被当成漏加的一块。
#   · rpc_commodities_usd / rpc_financials_usd —— 上层聚合，页面上那张 RPC 图只画四条
#     叶子（两条聚合只现算进标题与图注），表里跟着只给叶子。
#   · oi_commodities_kcontracts / oi_financials_kcontracts —— 规则 A：它们是段之和，
#     未平仓那张堆叠图堆的是四条叶子，表里给段之和会让表与图对不上。
#     （官方也**没有** TOTAL OI 行，新闻稿里的 "Total OI" 是两段自己加的。）
#   · 12 条 per-tape 原始量（adv_tape{A,B,C}_{consolidated,matched,handled}）——
#     页面上按 Tape 看的是**份额**三条线；这 12 行是那三条线的分子分母算术，
#     末尾核对表按官方原始单位逐月给，汇总表不重复。
#   · adv_nyse_tapeA/B/C_handled 之外的 handled 列同上。
#
# ── 有意**不进**本表的一类值：隐含交易收入 ────────────────────────────────
#   隐含收入只能按季度构造（RPC 是滚动三月均，季末月那一格的窗口恰好覆盖该季度），
#   而本表的三列写死是三个**具名月份**。把一个季度值放进「本月 / 上月 / 去年同月」
#   的表头下面，是一句不会报错的假话。收入在页面中段的季度块里，本表只给它的两个
#   输入（量 / 费率）逐行配对，读者可以自己乘。
#
# 第 4 个字段 cal=True → 纯日历行：m/m 与 y/y 不着色、分位整格留空。抄 cme.py:661 的
# 理由：交易日是月历的产物（21 天 vs 22 天纯粹因为这个月工作日少一天），不是经营结果，
# 「-4.3% 涂红」等于说少一个工作日是坏消息。数值仍然要给 —— ICE 有三套日历，读者要拿
# 它们复核收入构造里「每条腿各归一各的」那一步。
SUM_ROWS = [
    ('group', '头条（决定本页数据月）', None, False),
    ('row', None, 'adv_futures_options_kcontracts', False),
    ('row', None, 'adv_nyse_us_cash_handled_mnsh', False),

    ('group', '合约构成与收入四腿的量', None, False),
    ('row', None, 'adv_commodities_kcontracts', False),
    ('row', '　', 'adv_energy_kcontracts', False),
    ('row', '　', 'adv_ag_metals_kcontracts', False),
    ('row', None, 'adv_financials_kcontracts', False),
    ('row', '　', 'adv_rates_kcontracts', False),
    ('row', '　', 'adv_other_financials_kcontracts', False),

    ('group', '一张合约不是一块钱：每张收入（RPC，滚动三月均）', None, False),
    ('row', None, 'rpc_energy_usd', False),
    ('row', None, 'rpc_ag_metals_usd', False),
    ('row', None, 'rpc_rates_usd', False),
    ('row', None, 'rpc_other_financials_usd', False),

    ('group', '月末未平仓（存量，期末口径）', None, False),
    ('row', None, 'oi_energy_kcontracts', False),
    ('row', None, 'oi_ag_metals_kcontracts', False),
    ('row', None, 'oi_rates_kcontracts', False),
    ('row', None, 'oi_other_financials_kcontracts', False),

    ('group', 'NYSE：还剩多少市场', None, False),
    ('row', None, 'adv_us_equity_options_industry_kcontracts', False),
    ('row', None, 'adv_nyse_equity_options_kcontracts', False),
    ('row', None, 'share_nyse_equity_options', False),
    ('row', None, 'rpc_nyse_equity_options_usd', False),
    ('row', None, 'share_nyse_us_cash_matched', False),
    ('row', '　', 'share_nyse_tapeA_matched', False),
    ('row', '　', 'share_nyse_tapeB_matched', False),
    ('row', '　', 'share_nyse_tapeC_matched', False),
    ('row', None, 'rpc_nyse_us_cash_usd_per100sh', False),

    ('group', 'CDS 清算名义额（ICE Clear Credit，当月总量）', None, False),
    ('row', None, 'cds_total_notional_usdbn', False),
    ('row', None, 'cds_client_notional_usdbn', False),
    ('row', None, 'cds_nonclient_notional_usdbn', False),

    # 三套交易日是**新增**的一条组带（引擎版没有 —— build/specs/ice.py 里压根没有
    # 交易日列）。它进表是因为下游的季度收入构造整个建立在「每条腿各归一各的日历」
    # 这一步上，而那个配对是拿 10-K FY2025 的合约数双向证伪过的；读者若不知道有三套
    # 日历，会把本表每一行 ADV 都读错（以为它们可以互相乘回同一个当月合计）。
    ('group', '三套交易日（月历，不是经营结果）', None, False),
    ('row', None, 'trading_days_commod', True),
    ('row', None, 'trading_days_rates', True),
    ('row', None, 'trading_days_us_equities', True),
]

def bare_label(key):
    """不带缩进的行名。缩进（'　'）是**表格的版式**，跟着行名跑进表注的引号里
    （「　Tape A 份额（%）」）只会让读者以为那个空格是名字的一部分。所以表注、来源
    判定、留空账本一律用这个 bare 形态，表格本身用 `row_label()` 的带缩进形态；
    两者由 `assert_note_covers()` 对齐（它比的是 bare）。"""
    c = COL__summary[key]
    return f'{c["zh"]}（{c["unit"]}）'

def row_label(indent, key):
    """行标签 = 缩进 + 中文名 +（单位）。**单位必须逐行给**，不能只写在组带上：
    本表有 8 种单位，光 NYSE 那条组带里就有 4 种（k contracts/day、%、USD/contract、
    USD/100 shares），组带级的单位会当场撒谎。与引擎 `single.py:3804` 同形。"""
    return f'{indent or ""}{bare_label(key)}'

# ══════════════════════ 4. 来源判定（抄 cme.py:688-752）══════════════════════
def _sum_provenance(df):
    """汇总表每一行的水平值是哪来的 —— 四档，判据全部现算，不靠人肉名单。

      · **披露原列**：列名在 series/ice.csv 的表头里，且 scale == 1，原样照抄；
      · **单位换算**：① 是原列但带 scale（本页的 share_* 是比例，×100 印成百分数）；
        ② 不是原列，但逐月都等于某个原列乘同一个常数 —— 源列与常数都是除出来的；
      · **推导**：两档都不是 → 必须在 SUM_CALC 里登记算式，登记不到就停机。

    表注末句由这三类拼出（`_sum_src_txt`），所以「哪几行不是披露值」这句话与实际来源
    只有一个源头。cme.py:698-702 记着翻车经过：写死的「全部为官方披露值，无推导」
    被同一张表里的换算列当场证伪。ICE 这张表里必然命中的是 share_* 的 ×100，以及
    「利率」「股指与 FX」两条腿的加总。
    """
    # 现读 CSV 表头 —— 判据是「ICE 自己发的那张表里有没有这一列」，不是本页 df 里有没有
    # （df 上还挂着本页自己加的派生列，拿 df 当判据等于让被判的人自己出题）。
    # `month` 是索引不是数值列，剔掉：留着它下面那个「常数倍」搜索会拿 Period 去做除法。
    csv_cols = [c for c in pd.read_csv(CSV, nrows=0).columns if c != 'month']
    raw, unit, calc = [], [], []
    for kind, tag, key, _cal in SUM_ROWS:
        if kind != 'row':
            continue
        c = COL__summary[key]
        lab = bare_label(key)          # 表注里的引号名不带版式缩进，见 bare_label()
        col, scale = c['col'], c['scale']
        if col in csv_cols and scale == 1:
            raw.append(lab)
            continue
        if col in csv_cols:                       # 是原列，但显示值做了缩放
            unit.append((lab, col, float(scale)))
            continue
        hit = None
        for cc in csv_cols:                       # 按 CSV 原顺序找，结果与遍历顺序无关
            with np.errstate(divide='ignore', invalid='ignore'):
                r = (df[col].to_numpy() * scale) / df[cc].to_numpy()
            if np.all(np.isfinite(r)) and np.allclose(r, r[0], rtol=1e-9, atol=0.0):
                hit = (cc, float(r[0]))
                break
        if hit:
            unit.append((lab, hit[0], hit[1]))
        elif col in SUM_CALC:
            calc.append((lab, SUM_CALC[col]))
        else:
            raise SystemExit(
                f'汇总表的「{lab}」取的列 {col} 既不在 series/ice.csv 的表头里，也不是'
                f'任何一个披露原列的常数倍 —— 那它就是本页算出来的，必须在 SUM_CALC 里'
                f'登记算式（算式会原样印进表注，所以要写成读者看得懂的话）。')
    return raw, unit, calc

def _factor(k):
    """常数倍 → 读者看得懂的写法：1e-06 印成「÷ 1,000,000」而不是「× 1e-06」。"""
    inv = 1.0 / k if k else float('inf')
    if abs(inv) >= 1 and abs(inv - round(inv)) < 1e-6:
        return f'÷ {round(inv):,}'
    return f'× {k:g}'

def _sum_src_txt(raw, unit, calc):
    """表注末句。名单、算式、行数全部来自 `_sum_provenance()`，一个字都不是写死的。"""
    bits = [f'「{lab}」是披露列 <code>{src}</code> 的单位换算（{_factor(k)}）'
            for lab, src, k in unit]
    bits += [f'「{lab}」是本页算出来的：{how}' for lab, how in calc]
    if not bits:
        return (f'本表 {len(raw)} 行水平值逐行照抄 series/ice.csv 里的 ICE 披露列，'
                f'没有换算也没有推导。')
    return ('<b>本表有哪几行不是 ICE 直接披露的</b>（判据是 series/ice.csv 的表头，'
            '构建期现读）：' + '；'.join(bits)
            + f'。另外 {len(raw)} 行的水平值照抄披露列原值。')

# ══════════════════ 5. ICE 特有的两句「现算事实」（进表注）══════════════════
def _agg_gap_txt(df):
    """「分项之和 ≠ 合计」这件事，现算并**只陈述可核的事实**。

    ⚠️ 不许写因果：这个差的成因**官方从未说明**，而「两套交易日各归一各的」这个
    流传的解释已被 fetch/ice.py:123-131 证伪（偏差最大的三个月里两列交易日恰恰相等）。
    所以这句只报「多少个月精确相等 / 最大相对差多少」，不报为什么。
    """
    out = []
    for tot, parts, zh in (
            ('adv_commodities_kcontracts',
             ['adv_energy_kcontracts', 'adv_ag_metals_kcontracts'], '大宗商品合计'),
            ('adv_financials_kcontracts',
             ['adv_stir_kcontracts', 'adv_mltir_kcontracts',
              'adv_equity_index_kcontracts', 'adv_fx_credit_kcontracts'], '金融合计')):
        s = df[parts].sum(axis=1)
        d = s - df[tot]
        n_exact = int((d.abs() < 1e-9).sum())
        rel = float((d / df[tot]).abs().max() * 100)
        out.append(f'「{zh}」在 {len(df)} 个月里有 {n_exact} 个月与其分项之和精确相等，'
                   f'其余各月最大相对差 {rel:.3f}%')
    return ('<b>本表里的合计行不等于它下面几行之和</b>（现算）：' + '；'.join(out)
            + '。ICE 官方原表已把各行四舍五入到整千张，成因官方从未说明，'
              '本页不作解释、只陈述差多少。')

#: 唯一口径断点：NYSE Euronext 收购完成月。此前的 NYSE 各列是追溯并入的形式数。
BREAK_NYSE = pd.Period('2013-11', freq='M')

def _break_txt(df):
    """断点那句话。**「此前 N 个月」现算** —— 写死一个 34 会在数据回补到更早的时候
    变成假话，而那种假话不报错。"""
    n_before = int((df.index < BREAK_NYSE).sum())
    return (f'<b>{BREAK_NYSE} 是本页唯一的口径断点</b>：NYSE Euronext 收购当月完成，'
            f'此前 {n_before} 个月的 NYSE 各列是追溯并入的形式数。'
            f'3Y %ile 的窗口是近 {pctile.WINDOW} 个月，已经完全在断点之后。')

def _grain_txt(df, key):
    """一条费率列的**刻度粗细**，现算：披露到几位小数、量程多少、最细一格占低端多少。

    这句话解释两件事：① 为什么它的差必须印成钱而不是 bp；② 为什么它的 3Y %ile 会被
    `pctile.is_dead()` 判死（一列只取得到少数几个值，分位自然常年钉在端点）。
    ⚠️ 量程与「一格等于百分之多少」**一个都不许写死**：ICE 的 NYSE 期权 RPC 现在是
    0.04–0.18，下一次费率变动就会改写这两个数，而写死的版本不会报错。
    """
    c = COL__summary[key]
    s = df[c['col']].dropna()
    dec = SG.FMT_INFO[c['fmt']][0]
    step = 10.0 ** (-dec)                     # 官方披露到 dec 位小数 → 最细一格
    lo, hi = float(s.min()), float(s.max())
    n_distinct = int(s.round(dec).nunique())
    return (f'ICE 的「{c["zh"]}」只披露到小数点后 {dec} 位，而它全历史的量程只有 '
            f'{lo:.{dec}f}–{hi:.{dec}f}（{len(s)} 个月里只取到 {n_distinct} 个不同的值）：'
            f'最细的一格 {step:.{dec}f} 在量程低端就等于 {step / lo * 100:.0f}%，'
            f'写成 bp 会把 {step / lo * 100:.0f}% 的单位经济变动读成万分之几。'
            f'这同一件事也是它的 3Y %ile 留空的原因 —— 一列只取得到这么少的值，'
            f'分位自然常年钉在端点。')

def _daycal_txt(df):
    """三套交易日的差异，现算。它是收入构造里「每条腿各归一各的」那一步的前提。"""
    n = len(df)
    a = int((df['trading_days_commod'] == df['trading_days_rates']).sum())
    b = int((df['trading_days_commod'] == df['trading_days_us_equities']).sum())
    return (f'<b>ICE 有三套交易日</b>：大宗商品 / 金融（利率）/ 美股各一套。'
            f'{n} 个月里大宗商品与金融两套只有 {a} 个月相等，'
            f'大宗商品与美股两套有 {b} 个月相等。'
            f'ADV 本身是日均、已经把交易日除掉了，所以本表的 ADV 行可以直接比；'
            f'但把 ADV 乘回当月合计时必须<b>各条腿各用各的日历</b> —— '
            f'总 ADV 横跨两侧，没有哪一套能代表它，本页因此不给总 ADV 的当月合计。')

# ══════════════════════════ 6. 汇总表本体 ══════════════════════════
def summary_block(df, cur, prv, yag):
    """本月 | 上月 | 去年同月 ‖ m/m | y/y | 3Y %ile。

    格式化与着色规则全部在这里定死（CONTRACT §2）：页面只贴字符串。
    """
    idx = list(df.index)
    i_cur = idx.index(cur)
    raw, unit, calc = _sum_provenance(df)

    rows, blanks, dashes, shown_bare = [], [], [], []
    money_zh = []

    for kind, tag, key, cal in SUM_ROWS:
        if kind == 'group':
            # 组带行：tag 是组带名（组带没有列，key 是 None）
            rows.append({'kind': 'group', 'label': tag})
            continue

        # 数据行：tag 是缩进前缀（'　' 表示这一行是上一行的分项）
        c = COL__summary[key]
        lab = row_label(tag, key)      # 表格里的行名（带缩进）
        blab = bare_label(key)         # 表注 / 来源判定 / 留空账本里的行名（不带缩进）
        # 显示序列 = 原列 × scale。与引擎 `Page.ser()`（single.py:1653）同一句。
        s = df[c['col']].astype(float) * c['scale']
        g = lambda p: (float(s.loc[p]) if p in s.index and np.isfinite(s.loc[p])
                       else np.nan)
        a, b1, b12 = g(cur), g(prv), g(yag)

        # ⚠️ 比率判据只有一处：`SG.col_is_ratio()`。本文件不自己写 `fmt in RATIO_FMT`
        #    那一行 —— build/pctile.py 的模块头记着教训：各写各的，正是同一条序列在
        #    两页被判定相反的原因。
        ratio = SG.col_is_ratio(c)
        if SG.col_is_money_ratio(c) and blab not in money_zh:
            money_zh.append(blab)

        def chg(x, y):
            if not (np.isfinite(x) and np.isfinite(y)):
                return None
            if ratio:
                return float(x - y)      # 比率之差，不走「百分比的百分比变化」
            if y == 0 or x * y < 0:
                return None
            return (x / y - 1) * 100

        def cell(v):
            if v is None:
                return {'v': ''}
            if ratio:
                # ⚠️ **全底座只有 `ratio_diff_txt()` 一处做「钱 vs 百分点」的分派**
                #    （single.py:700）。钱比率印「-0.01 USD/contract」，百分点比率印
                #    pp/bp。两处各写一遍的下场是图注说美元、汇总表说 bp —— 那正是
                #    2026-09 之前 ICE 页面上真实发生过的事（NYSE 期权 RPC 从 0.05
                #    掉到 0.04 是跌了五分之一，页面上写着「-1bp」）。
                txt = SG.ratio_diff_txt(v, c)
            else:
                txt = f'{nz(v, 1):+.1f}%'
            txt = SG.nz_txt(txt)
            if txt.lstrip('+-') in ('0', '0.0', '0bp', '≈0bp', '0.0pp', '0.0%', '0%'):
                return {'v': txt.lstrip('+-')}
            if cal:                       # 日历行只给数字、不作好坏判断
                return {'v': txt}
            return {'v': txt, 'cls': 'pos' if v > 0 else ('neg' if v < 0 else '')}

        cells = [{'v': SG.fmt_val(a, c['fmt']) or '—', 'cls': 'cur'},
                 {'v': SG.fmt_val(b1, c['fmt']) or '—'},
                 {'v': SG.fmt_val(b12, c['fmt']) or '—'},
                 cell(chg(a, b1)), cell(chg(a, b12))]

        # 分位一律走 build/pctile.py（全站唯一实现）。本文件只负责「本页自己的口径原因」。
        ser = [None if not np.isfinite(x) else float(x) for x in s.values]
        if cal:
            qv, qcls = '', ''
            blanks.append((blab, '交易日由月历决定，与 ICE 的经营无关，'
                                '它的分位只是在月长之间震荡'))
        elif not np.isfinite(a):
            qv, qcls = '', ''
            dashes.append(blab)
        else:
            qv, qcls = pctile.cell(ser, i_cur)
            if not qv:
                blanks.append((blab, pctile.why_blank(ser) or '样本不足'))
        cells.append({'v': qv, 'cls': qcls} if qv else {'v': ''})
        rows.append({'label': lab, 'cells': cells})
        shown_bare.append(blab)

    n_rows = sum(1 for r in rows if r.get('kind') != 'group')
    n_grp = sum(1 for r in rows if r.get('kind') == 'group')

    note = (
        f'「3Y %ile」= 当月读数在最近 {pctile.WINDOW} 个月里高于多少比例的观测'
        f'（≥66 绿、≤33 红），由全站唯一的 <code>build/pctile.py</code> 计算：'
        f'把这一行的分位在近 {pctile.REPLAY} 个月里逐月回放，若 ≥'
        f'{pctile.DEAD_FRAC:.0%} 的月份都钉在 100 或 0，说明这一列对该行没有区分度，留空。'
        f'比率类指标的变化用<b>差</b>而不是「百分比的百分比变化」；'
        f'其余用百分比变化，分母为 0 或两期异号时留空。'
        + (f'差的单位跟着<b>分子</b>走：分子是百分数的写 pp／bp（差额绝对值小于 1pp 时'
           f'写 bp）；<b>分子是钱</b>的写钱 —— 本表里的「{"」「".join(money_zh)}」就是这一档，'
           f'它们的 m/m 与 y/y 印成「每一个活动单位差多少钱」（例如'
           f'「-0.01 USD/contract」），<b>不是 pp 也不是 bp</b>：每张少收一分钱是钱，'
           f'不是万分之一个百分点。'
           + _grain_txt(df, 'rpc_nyse_equity_options_usd')
           if money_zh else '比率的差一律写 pp／bp（差额绝对值小于 1pp 时写 bp）。')
        + f'<b>「月末未平仓」那一组是存量、期末口径</b>，它的 m/m 与 y/y 是'
          f'点对点（本月末对上月末 / 去年同月末），与上面几组流量行的口径不同，'
          f'不要横着比。'
        + f'<b>RPC 是费率不是成交价</b>，且是 ICE 自己披露的滚动三月均（对水平值的平滑，'
          f'与同比口径无关）；ICE 的 RPC <b>不滞后</b>，所以本表最新一列 RPC 与量同月。'
          f'正因为它是滚动值，<b>不能拿它乘单月量当单月收入</b> —— '
          f'本页的隐含交易收入只按季度构造（季末月那一格的滚动窗口恰好覆盖该季度），'
          f'而本表三列写死的是三个具名月份，所以收入不在这张表里，在下方的季度块中；'
          f'本表给的是它的两个输入，量行与费率行逐行配对，读者可以自己乘。'
        + _agg_gap_txt(df)
        + _daycal_txt(df)
        + _break_txt(df)
        + (f'<b>{"、".join(sorted(set(dashes)))}</b> 的本月一列是「—」：该列本月尚未'
           f'披露，不是 0。' if dashes else '')
        + ('本月分位留空的行：' + '；'.join(f'{a}（{b}）' for a, b in blanks) + '。'
           if blanks else '本表没有留空的分位。')
        + _sum_src_txt(raw, unit, calc))

    return {
        'title': f'洲际交易所（ICE）月度经营指标汇总 — {mlab(cur)}',
        'heads': [f'本月 {mlab(cur)}', f'上月 {mlab(prv)}', f'去年同月 {mlab(yag)}',
                  'm/m', 'y/y', f'{pctile.WINDOW // 12}Y %ile'],
        'sep': 3,
        'rows': rows,
        'note': note,
        # 下面几项不进页面渲染，供本文件的构建期兜底与页尾 notes 引用
        'blank_why': blanks,
        'provenance': (raw, unit, calc),
        'shown_bare': shown_bare,
        'shape': (n_rows, n_grp),
    }

def assert_note_covers(summary, raw, unit, calc):
    """兜底③（抄 cme.py:2784-2793）：三方对一遍 —— 来源判定、真正印进表里的行、
    印进表注的字。手写一句「全部为官方披露值」正是上一轮翻车的地方。"""
    shown = summary['shown_bare']      # 与来源判定同一个 bare 形态，见 bare_label()
    named = [lab for lab, *_ in unit] + [lab for lab, _ in calc]
    uncovered = [lab for lab in shown if lab not in raw and lab not in named]
    unnamed = [lab for lab in named if f'「{lab}」' not in summary['note']]
    if uncovered or unnamed:
        raise SystemExit(
            f'汇总表注与表本身对不上：{uncovered} 这几行没有被来源判定覆盖；'
            f'{unnamed} 不是披露原列，表注里却没有点名。')
    blanks_named = [lab for lab, _ in summary['blank_why']
                    if lab not in summary['note']]
    if blanks_named:
        raise SystemExit(f'留空的行 {blanks_named} 没有印进表注 —— '
                         f'读者只会把空格当成「这一格忘了填」。')
    # 表注走 innerHTML：Markdown 不会被解析，`**粗体**` 会原样印在页面上，页面不报错、
    # payload 也合法，只有截图上看得见（build/verify_pages.py 专门为它加过一条 WARN，
    # 引擎那边由 `single.py:md_bold()` 兜住）。手写页没有那一步，所以在这里直接拦。
    if '**' in summary['note']:
        raise SystemExit('表注里出现了 Markdown 的 `**` —— notes 走 innerHTML，'
                         '它会原样印在页面上。粗体一律写 <b></b>。')
    # 图号字面量：本页所有 exhibit 号走 EX_* 常量，文案里按标题指代。表注写死一个
    # 「Exhibit 8」，图序一动就是一句不报错的假话。
    if re.search(r'Exhibit\s*\d', summary['note']):
        raise SystemExit('表注里出现了字面的「Exhibit N」—— 按标题指代，不写图号。')

# ==========================================================================
# 【glossary】
# ==========================================================================

# -*- coding: utf-8 -*-
"""build/ice.py 的「名词释义」段（payload 的 `glossary`，排在所有 exhibit 之前）。

═══ 为什么是函数而不是模块级常量 ═══
照 build/cboe.py:828-836 的判断原样搬：那里写着「三个结构性量必须现算……写死的那一天
就是它开始变旧的那一天」。ICE 这一页要现算的是**五**个：
  ① 商品合计 + 金融合计 与「衍生品总 ADV」在**本页窗口内**差多远、有几个月精确相等；
  ② RPC 与量列是不是同月齐（这是「ICE 的 RPC 不滞后」那句话的判据，与 Cboe 相反）；
  ③ 拿「三条带合计」当 Tape 份额的分母会把份额算低几倍（读者最容易犯的那个错）；
  ④ CDS 三列的首月，以及本页窗口内还有没有空格；
  ⑤ 计数列里有没有小数格（「官方已取整到整千张」那句话的判据 —— 扫出来就停机）。
全部从 series/ice.csv 现读；`build/specs/ice.py` 那一版里同类的量也都是现算的
（`_split_vs_total__glossary()` / `_nonint_census()` 等），这里只是换了窗口口径。

═══ 与 brief / 图注 / 页尾 notes 的分工（CONTRACT §1）═══
brief 与图注说「**这个月**这组读数怎么读」、每月重写；这一块说「**这些词**是什么意思」、
一年到头是同一段 ⇒ 这里**一个当月读数都不写**。出现的数只有两类：
  (a) 把定义钉住的**结构性**量（上面那五个，全部现算）；
  (b) 恒等式与单位换算常数本身（千张 = 1,000 张；现货那条腿的净因子是 1/100 不是 1/1000）。
凡是随窗口滚动的实测（桥的交叉项多大、对账最差差多少、六段之和有几期不等）
一律**只留一句指路**，数字归各自的图注 —— 同一个数印两处，迟早只改一处。

═══ 选词判据（逐条从 build/specs/ice.py 的 glossary 段搬来，按新图列修订）═══
只从本页**露过面**的字里选（图题 / 序列名 / 纵轴 / 汇总表行头 / 核对表列头 / 图注 /
页尾说明），且限于「不看定义就会读错」的那些：
  · 缩写与行话：ADV、RPC、月末净 OI、Tape A/B/C、CDS 名义额、TTF、合并成交量；
  · 单位陷阱：千张（与 series/cme.csv 的裸张数差 1,000 倍）；
  · 官方标签与实际口径不一致：FX 与 USDX（行名写 & CREDIT，其实不含信用）、
    期权行业总量（ICE 从未书面定义过，别当官方口径引）；
  · 同一个词在本页有特定外延：衍生品总 ADV、份额（三组各有各的分母）、
    handled / matched（份额只能用后者）；
  · 这一轮新加的推导链：隐含交易收入 → 量价分解（两个词是一条链，都是**推导值**，
    最容易被当披露值读）；
  · 口径断点的实质：追溯并入的形式数。
**不收** m/m、y/y、3Y %ile、pp/bp —— 全站通用的读图约定，summary.note 与页尾「同比口径」
已逐条讲过，释义板再讲一遍就是两处各写一份、迟早不同步。

**这一轮删掉的**（页面上已经没有这些东西了，而一条活得比它的图更久的释义比没有释义更糟）：
  · 「单股」独立成条 —— 新图列里 `adv_single_stock_kcontracts` 一张图都不上，
    只在「衍生品总 ADV」的外延里出现一句「不含它」，那一句就够了；
    留一个页面上找不到对应线的 <dt>，读者会去图上找一条不存在的序列。
  · 描述已删掉的图的任何词条（分位带、热力矩阵色标之类）。本页只剩一张热力矩阵，
    它的色标读法归那张图自己的图注。

═══ 两处栽过跟头的地方，改这一段之前先读 ═══
  1. **不许写错因果**：「分项之和 ≠ 合计」的成因 fetch/ice.py:123-131 的口径坑 6 已经
     证伪过（偏差最大的那几个月里两列交易日恰恰相等），只许陈述可核的事实、成因写
     「官方从未说明」。原话是「写一个错的因果，下一个人会去『修』一个修不好的东西」。
  2. **不许有「本仓唯一」这类全称断言**：上一版把注 [18] 上方已经删掉的那半句原样搬了
     回来（miax 也按月披露同口径的行业分母）。全称断言必须有构建期判据才准写；
     本文件里唯一的全称断言（「计数列没有小数格」）自带 `_nonint_guard()` 停机。
"""

# 自测时要 import build/ 下的 glossary.py；并进 build/ice.py 之后这一段随文件头的
# `sys.path.insert(0, HERE)` 一起走，不再需要。
_BUILD = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))), 'build')

if not os.path.isdir(_BUILD):                       # 自测在 scratchpad 里跑，路径要写死
    _BUILD = ('/Users/hzhan/Documents/monthly-op-dashboards/'
              '.claude/worktrees/cboe-page-redesign-dc42f8/build')

sys.path.insert(0, _BUILD)

# ══════════════════════════════════════════════════════════════════════════════
# §1 现算 helper —— 释义里出现的每一个数都从这里来，一个快照都不抄
#
# ⚠️ 这五个函数**应当由 facts 段提供**（interfaces_needed 里已声明）。合并进
# build/ice.py 时，凡是 facts 段已经有同义 helper 的，删掉这里的、改调它的 ——
# build/pctile.py 的模块头记着这条教训：各写各的判据，正是同一条序列在两页被判定
# 相反的原因。这里留一份只为本文件能独立跑起来。
# ══════════════════════════════════════════════════════════════════════════════
def _win__glossary(df, win_from=WIN_FROM):
    """本页月度窗口（WIN_FROM 起）。释义里的实测一律只量**读者看得见**的那一段 ——
    整份 CSV 从 2011-01 起，但页面左端是 WIN_FROM，拿全样本的残差去解释一张
    2016 年起的图，读者在图上永远找不到那个最大值。"""
    return df[df.index >= pd.Period(win_from, 'M')]

def _split_vs_total__glossary(df):
    """(可比月数, 精确相等的月数, 最大相对差%)；算不出返回 (None,)*3。

    「衍生品总 ADV ≠ 大宗商品合计 + 金融合计」这条的判据。**成因官方从未说明**，
    这里只报可核的事实（fetch/ice.py 口径坑 6：把它归给「两套交易日」是错的）。
    """
    try:
        c = df['adv_commodities_kcontracts']
        f = df['adv_financials_kcontracts']
        t = df['adv_futures_options_kcontracts']
    except KeyError:
        return (None,) * 3
    ok = c.notna() & f.notna() & t.notna() & (t != 0)
    if not ok.any():
        return (None,) * 3
    rel = ((c[ok] + f[ok]) / t[ok] - 1.0).abs() * 100.0
    return int(ok.sum()), int(((c[ok] + f[ok]) == t[ok]).sum()), float(rel.max())

def _rpc_in_sync(df):
    """RPC 各列的末月是不是与量列的末月同一个月 —— 「ICE 的 RPC 不滞后」的判据。

    Cboe 那边正相反（滞后一个月发布，汇总表最新一列的 RPC 是空的，
    见 build/cboe.py 的 RPC 释义）。两家并排读的人必须知道这一条，
    而「不滞后」是个会变的事实 ⇒ 现算，不写死。
    """
    rpc = [c for c in df.columns if c.startswith('rpc_')]
    if not rpc:
        return None
    last = df.index[-1]
    return all(df[c].dropna().index[-1] == last for c in rpc if df[c].notna().any())

def _tape_denom_mult(df, tape='A'):
    """(中位, 最小, 最大) 倍数：三带合并量 ÷ 该带自己的合并量。

    这是本页份额列**最容易犯的那个错**的量级：`share_nyse_tapeA_matched` 的分母是
    **Tape A 自己**的合并量，不是三条带的合计；拿三带合计当分母，份额会小成
    这里报的倍数。build/specs/ice.py 的 glossary 段为此改过一版（原文把三条 Tape
    份额与 NYSE 全美份额并成一组说「分母都是全美合并量」，按字面读会把 Tape A
    份额算错三倍多）—— 那一版举的是某一个月的例子，是**当月读数**；
    释义板不写当月读数，所以这里改成全窗口的中位与区间。
    """
    try:
        own = df[f'adv_tape{tape}_consolidated_mnsh']
        tot = (df['adv_tapeA_consolidated_mnsh'] + df['adv_tapeB_consolidated_mnsh']
               + df['adv_tapeC_consolidated_mnsh'])
    except KeyError:
        return (None,) * 3
    r = (tot / own).replace([np.inf, -np.inf], np.nan).dropna()
    if r.empty:
        return (None,) * 3
    return float(r.median()), float(r.min()), float(r.max())

def _cds_span(df, win_from=WIN_FROM):
    """(CDS 三列的首月 Period, 本页窗口内的空格数)；算不出返回 (None, None)。

    ⚠️ 与 build/specs/ice.py 那一版的差别：老页从 2011-01 画起，所以释义要交代
    「早于该月的空格是官方就没有，不是漏抓」；新页左端是 WIN_FROM，CDS 起步早于它
    ⇒ 那句话在新页上**指的是一段读者根本看不到的空白**，必须改成现算的「窗口内
    还有没有空格」。这正是「一条活得比它的图更久的释义」的典型。
    """
    cols = [c for c in df.columns if c.startswith('cds_')]
    if not cols:
        return None, None
    s = df[cols].dropna(how='all')
    if s.empty:
        return None, None
    w = _win__glossary(df, win_from)[cols]
    return s.index[0], int(w.isna().any(axis=1).sum())

def _nonint_guard(df):
    """计数列里有没有小数格；有就**停机**。返回 (非整数列名 list, 非整数格数)。

    「官方原表已四舍五入到整千张 / 整百万股，所以本页计数类一律 0 位小数」是一句
    全称断言。build/specs/ice.py 的 `_nonint_census()` 上方那段注释记着它上一版
    栽的跟头：**只数了列数、没验列名** —— 哪天官方给某条张数列发了小数，页面上那句
    话会继续印，而没有任何东西会报错。⇒ 判据下沉到这里，名单对不上直接 SystemExit。
    """
    names, cells = [], 0
    for c in df.columns:
        v = pd.to_numeric(df[c], errors='coerce').dropna()
        bad = int((v - v.round()).abs().gt(1e-9).sum())
        if bad:
            names.append(c)
            cells += bad
    off = [c for c in names if not c.startswith(_NONINT_OK)]
    if off:
        raise SystemExit(
            'series/ice.csv：释义板断言「非整数的只有 RPC 与份额那几列」，但 %s '
            '也有非整数格 —— 断言与数据对不上，先改释义再构建'
            '（build/ice.py 的 _nonint_guard / _NONINT_OK）' % '、'.join(off))
    return names, cells

# ══════════════════════════════════════════════════════════════════════════════
# §2 释义表
# ══════════════════════════════════════════════════════════════════════════════
def compose_glossary(df, win_from=WIN_FROM):
    """/ice/ 页最上方的「名词释义」，返回 `[(词, 释义), …]`（顺序即页面上的顺序）。

    参数
      df        load() 出来的月度 DataFrame（index 是 PeriodIndex('M')）。
      win_from  月度图的左端，默认冻结常量 WIN_FROM。释义里凡是量「差多远」的话
                都只量窗口内那一段 —— 页面上看不见的月份不该拿来解释页面上的图。

    ⚠️ 释义里只能用**行内**标签，强调一律 `<b>…</b>`：page.js 走 innerHTML，
    Markdown 的星号会原样印在整页第一段上（build/glossary.py 第 1 道护栏）。
    ⚠️ **不写字面的「Exhibit N」**：编号会随图序变，而释义板是页面上最少改动的一段。
    提别的图一律按**标题**指代。
    """
    W = _win__glossary(df, win_from)
    W0, W1 = W.index[0], W.index[-1]

    # ── ① 分项之和 vs 总 ADV：只量窗口内 ────────────────────────────────────
    # 读者能同时看见的就是这两张图（总 ADV 那根柱、合约构成那摞堆叠），
    # 拿全样本的最大残差去解释一张 2016 年起的图，他在图上永远找不到那个值。
    _n, _eq, _mx = _split_vs_total__glossary(W)
    split_txt = ((f'本页窗口（{mlab(W0)}–{mlab(W1)}，{_n} 个月）内逐月现算：'
                  f'{_eq} 个月两边精确相等，其余月份的相对差不超过 <b>{_mx:.2f}%</b>。')
                 if _n else '多数月份两边精确相等，少数月份差一层（逐月现算）。')

    # ── ② RPC 是否与量列同月齐 ──────────────────────────────────────────────
    sync = _rpc_in_sync(df)
    rpc_lag = ('与 Cboe 不同，ICE 的 RPC <b>不滞后</b>发布：现读本表末月，'
               'RPC 各列与成交量列<b>齐到同一个月</b>，所以两家并排画时 ICE 那条'
               '每月都会多伸出一格。' if sync is True else
               '⚠️ 现读本表末月，RPC 各列<b>短于</b>成交量列 —— 凡是用到 RPC 的图'
               '都要在绘图层截齐。' if sync is False else '')

    # ── ③ 三带合计当分母会错几倍 ────────────────────────────────────────────
    _md, _lo, _hi = _tape_denom_mult(W, 'A')
    tape_wrong = ((f'⚠️ 拿<b>三条带的合计</b>当分母是本页最容易犯的一个错：'
                   f'窗口内 Tape A 的合并量中位只占三带合计的 1/{_md:.1f}'
                   f'（区间 1/{_hi:.1f}–1/{_lo:.1f}，现算），'
                   f'除错了会把 Tape A 份额算低约 {_md:.1f} 倍，而曲线形状完全正常。')
                  if _md else
                  '⚠️ 拿三条带的合计当分母会把单条带的份额算低好几倍，而曲线形状完全正常。')

    # ── ④ CDS 起点与窗口内的空格 ────────────────────────────────────────────
    _c0, _cgap = _cds_span(df, win_from)
    cds_span = ((f'三列自 {mlab(_c0)} 起，本页窗口内逐月无缺（现算）。'
                 if _cgap == 0 else
                 f'三列自 {mlab(_c0)} 起，本页窗口内还有 {_cgap} 个月是空的 —— '
                 f'那是官方就没有，不是漏抓（现算）。')
                if _c0 is not None else '')

    # ── ⑤ 计数列有没有小数格（停机式全称断言）───────────────────────────────
    _ni_cols, _ni_cells = _nonint_guard(df)
    round_txt = (f'⚠️ 月度值<b>在官方原表里就已四舍五入到整千张 / 整百万股</b>：'
                 f'全表现扫，有小数格的只有 <code>rpc_*</code> 与 <code>share_*</code> '
                 f'这 {len(_ni_cols)} 列（{_ni_cells:,} 个格子），'
                 f'扫出别的列直接停机。所以本页计数类一律按 0 位小数显示；'
                 f'小基数行（环境权益、FX 与 USDX）的同比会与官方新闻稿差 1–2pp，'
                 f'那是官方自己取整造成的，不是解析错误。')

    return [
        # ══ 单位与分母 ═══════════════════════════════════════════════════════
        ('ADV',
         '日均成交量（average daily volume）：<code>当月合计 ÷ 当月交易日数</code>。'
         '本页凡是标着 ADV 的列都是<b>官方自己算好的日均</b>，本仓不做任何还原、'
         '也不再平均（CDS 那一组不是 ADV，见下）。'
         '⚠️ ICE 有<b>三套交易日</b>（<code>trading_days_commod</code>、'
         '<code>trading_days_rates</code>、<code>trading_days_us_equities</code>），'
         '各条 ADV <b>各归一各的</b> —— <b>不要</b>随手挑一套乘回去把日均还原成当月合计。'
         '衍生品总 ADV 横跨大宗商品与金融两侧，<b>没有哪一套日历能代表它</b>；'
         '本页把 ADV 乘回交易日的地方只有隐含交易收入那一块，'
         '而那里是<b>逐条腿各配各的那一套</b>。'),

        ('千张（k contracts）',
         '官方原表的单位（原文 "contracts in 000s"）：本页衍生品 ADV 与月末 OI 的 1 '
         '就是 <b>1,000 张</b>合约。⚠️ 跨家比较前必须先统一 —— '
         '<code>series/cme.csv</code> 的 <code>oi_*_contracts</code> 是裸张数，'
         '两者差 1,000 倍。' + round_txt),

        ('衍生品总 ADV',
         '页顶头条那一列，官方原表行名 <b>TOTAL FUTURES &amp; OPTIONS</b>，'
         '横跨大宗商品与金融两侧。它<b>不含单股</b>'
         '（<code>adv_single_stock_kcontracts</code> 已被官方从 TOTAL FINANCIALS 剔除，'
         '理由是收入封顶、与量无相关性；本页一张图都不给它，也不要把它并进任何合计）。'
         '⚠️ 它<b>不是</b>「大宗商品合计 + 金融合计」相加得来的：' + split_txt +
         '<b>官方从未说明原因</b>，本仓也未查明 —— <b>不要当恒等式、也不要当校验条件</b>用。'
         '⇒ 本页的隐含交易收入因此<b>只能</b>由大宗商品与金融两侧的分腿搭起来，'
         '不拿这一列去凑。'),

        ('FX 与 USDX',
         '<code>adv_fx_credit_kcontracts</code>。官方行标签写的是 "TOTAL FX &amp; CREDIT"，'
         '但<b>口径是外汇 + 美元指数（USDX），不含信用</b> —— 依据是表内脚注原文只提 '
         'U.S. Dollar Index 与 foreign exchange，并与官方合约级明细文件对上过（见页尾）。'
         'ICE 的信用业务在本页是<b>另一组</b>（CDS 清算名义额），既不同口径也不同单位，'
         '两处不能互相印证。'),

        ('TTF',
         'Title Transfer Facility，荷兰的天然气交易枢纽，是 ICE Futures Europe 那条'
         '<b>欧洲</b>气基准。⚠️ 本页能源分产品那两张图里的「天然气」<b>不是</b>一条纯美国'
         '（Henry Hub）序列 —— 官方把北美、NGX、英国与欧洲（TTF 就在其中）四块'
         '<b>合并成一行</b>披露，<b>不拆</b>。⇒ 本表给不出「ICE 的 TTF 成交量」；'
         '官方新闻稿里单独点评过的 TTF 同比是<b>合约级</b>口径，与这一行同名不同物，'
         '拿它去反推一个 TTF 绝对量是在编数。'),

        # ══ 一张合约值多少钱：费率 → 隐含收入 → 桥 ════════════════════════════
        ('RPC（每张收入）',
         'revenue per contract。官方定义（表内脚注 1）= <code>交易收入 ÷ 合约量</code>，'
         '而且是<b>滚动三个月平均</b>。⚠️ 它是<b>费率不是成交价</b>：分子是 ICE 向会员'
         '收的费，不是市场撮合出来的价格 —— 本表<b>一条成交金额列都没有</b>，'
         '所以本页那座桥分的是<b>收入</b>，不是「成交额 = 量 × 均价」，两者不可并读。'
         '⚠️ 既然已被三个月平滑，<b>就不能拿它乘单月量当单月收入</b>'
         '（隐含交易收入因此只按季构造，见下）。' + rpc_lag +
         '现货那一条的单位是 <b>USD/100 股</b>，不是 USD/张，'
         '与期权那条<b>不同量纲</b>，只能各看各的形状。'),

        ('隐含交易收入',
         '<b>推导值，不是公司披露的数</b>，也<b>不是</b> ICE 的分部收入口径'
         '（不含数据 / 上市 / 固定收益等非交易收入）。构造式按<b>季度</b>：'
         '<code>季度收入 = Σ(季内 3 个月的 ADV × 该腿对应的交易日列) × 季末月的 RPC '
         '÷ 换算因子</code>。'
         '为什么<b>只能</b>按季：RPC 是滚动三月均，<b>季末月那一格的窗口恰好覆盖该季度</b>；'
         '逐月形式在<b>唯一能与官方对账的那几个点</b>上一律偏低，而季末月形式落在很小的'
         '相对差以内（逐点数字见对账那张图的图注）。'
         '⚠️ 换算因子逐条腿不同：四条衍生品腿与 NYSE 期权腿是<code>÷1,000</code>'
         '（千张 × USD/张），<b>NYSE 现货那条是 <code>÷100</code></b>'
         '（百万股 × USD/100 股 —— 用错成 ÷1,000 会把现货收入低估 10 倍）。'
         '⚠️ 能与官方季度指标对上账的只有<b>三项</b>：能源、农产品与金属，'
         '以及利率与其他金融两条腿的<b>合计</b>（官方只披露到「金融」这一层）；'
         '<b>利率、其他金融、NYSE 期权、NYSE 现货这四条腿是纯推导值，没有官方数可对</b> —— '
         '对上的三条<b>不为</b>对不上的四条背书，读的时候两拨要分开看。'),

        ('量价分解',
         '本页那座桥分的是<b>隐含交易收入</b>，恒等式是「收入 = 成交<b>张数</b> × '
         '每张<b>费率</b>(RPC)」——「价」指的是交易所收的<b>费率</b>，'
         '<b>不是</b>标的的成交价格，与别页真正的「成交额 = 量 × 均价」不可并读。'
         '画法<b>不是</b>算术分解，而是<b>对数分解按算术总额重标定</b>：'
         '令 <code>w = (V1/V0 − 1) ÷ ln(V1/V0)</code>，'
         '量腿 = <code>w·ln(Q1/Q0)</code>、价腿 = <code>w·ln(P1/P0)</code>，'
         '两腿<b>精确加总等于</b>收入同比。'
         '⇒ 图上<b>没有</b>交叉项那一段：它不分配给任何一腿，只在图注里报算术读数'
         '（压给谁都会改读数）。'
         '⚠️ 这座桥<b>只覆盖四条衍生品腿</b>（能源、农产品与金属、利率、股指与 FX）—— '
         '桥需要一个可比的量 Q，而那四条都是<b>千张</b>，NYSE 现货是<b>百万股</b>，'
         '凑不出单一的量；NYSE 期权腿另有自己的理由不上桥（见那张图的图注）。'
         '这四条占隐含总收入多少，由图注现算。'),

        # ══ 存量 ═════════════════════════════════════════════════════════════
        ('月末净 OI',
         '未平仓合约（open interest），月末<b>净</b>口径（表内注明按行业惯例报 net OI）。'
         '它是<b>存量</b> —— 某一天的截面，不是当月发生的量，'
         '<b>不能与本页的日均相加</b>，同比也只能走<b>点对点</b>'
         '（月末 vs 去年同月月末；把 12 个月末的快照加起来不指代任何真实的量）。'
         '单位同样是千张。⚠️ 官方<b>没有 TOTAL OI 行</b>，新闻稿里的 "Total OI" 是'
         '「大宗商品 + 金融」两条自己加出来的，本页那张堆叠图画的是<b>四条叶子</b>，'
         '上层两条聚合列一条都不画。'),

        # ══ 还剩多少市场：NYSE 那一侧 ════════════════════════════════════════
        ('handled / matched',
         'handled = 本所撮合 + <b>路由到别家</b>交易所成交的量；'
         'matched = <b>只算本所自己撮合</b>的那部分。'
         '⇒ 市场<b>份额只能用 matched 算</b>，拿 handled 当分子等于把别家的成交'
         '记在自己名下。本页头条「NYSE 现货 handled ADV」量的是 NYSE Group 的<b>体量</b>，'
         '而所有份额列都是 matched 口径 —— <b>两者不可互相换算</b>，'
         '也不要拿 handled 的走势去解释份额的走势。'),

        ('合并成交量',
         'consolidated tape volume：<b>全美</b>该带的成交量，'
         '<b>所有成交场所之和</b>（交易所 + 暗池 + 内化商 + TRF），'
         '<b>不是</b> NYSE 自己的量，也不是「本页出现的这几家」之和。'
         '本页三条 <code>adv_tape{A,B,C}_consolidated_mnsh</code> 就是它，'
         '是所有份额列的<b>分母</b>；「场外化侵蚀」这条趋势只能靠它跟踪 —— '
         '交易所自营撮合量合起来只占其中一部分，其余成交在暗池 / 内化商 / TRF'
         '（具体比例见页尾，现算）。'),

        ('Tape A / B / C',
         '美股合并行情的三条带，按<b>上市地</b>划分：Tape A = NYSE 上市，'
         'Tape B = NYSE Arca / American 与区域所上市，Tape C = Nasdaq 上市。'
         '每条带本页给三列：该带的<b>合并成交量</b>（全市场，见上）、'
         'NYSE 在该带的 <b>matched</b> 与 <b>handled</b>。'
         '⇒ 三条带讲的是<b>上市地结构</b>而不是三个市场，'
         '份额高低跨带比较之前先看清分母是哪一条。'),

        ('份额（share_*）',
         '本页的份额列在官方原表里是 <b>0–1 的小数</b>（<code>0.191</code> 表示 19.1%），'
         '页面统一 ×100 按百分数显示（<code>series/miax.csv</code> 存的却是百分数，'
         '跨页取数别弄混）。<b>分母各不相同，三组各是各的</b>：'
         '三条 <b>Tape 份额</b>的分母是<b>该带自己</b>的合并成交量'
         '（该带 matched ÷ 该带 consolidated）；'
         '<b>NYSE 全美 matched 份额</b>才是三带之和除三带之和；'
         '<b>NYSE 期权份额</b>的分母是全美股票 / ETF 期权行业总量（见下）。'
         '三者都是<b>全市场</b>分母，<b>不是</b>「本页出现的这几家」池内份额；'
         '前两条的自算复核见页尾。' + tape_wrong),

        ('期权行业总量',
         '<code>adv_us_equity_options_industry_kcontracts</code>：'
         '全美股票 / ETF 期权的行业合计，<b>不含指数期权</b>，'
         '是 NYSE 期权份额那条线的分母。⚠️ 这个口径是与 Cboe multilist 及 ICE 10-K '
         '交叉验证出来的 —— <b>工作簿里这一行没有任何脚注、ICE 从未书面定义过</b>，'
         '不要当官方定义引用，也不要拿它去与别家披露的「行业总量」逐位对齐。'),

        # ══ 收入分解看不见的那一块 ═══════════════════════════════════════════
        ('CDS 清算名义额',
         'ICE Clear Credit 当月清算的 CDS <b>名义总额</b>（gross notional，单边计），'
         '单位十亿美元。⚠️ 是<b>当月总量，不是日均</b>（原表标题里没有 daily 字样）'
         ' —— 与本页其余 ADV 列<b>不是同一种口径</b>，不要顺着读成「每天多少」。'
         '「合计 = 客户盘 + 非客户盘」（官方原表行名 CLIENT / NON-CLIENT），入库时逐月核过。'
         '⚠️ 它<b>进不了本页的收入分解</b>：本表既没有 CDS 的费率列、也没有笔数列，'
         '配得上的数量列一条都没有。' + cds_span),

        # ══ 口径断点 ═════════════════════════════════════════════════════════
        ('追溯并入的形式数',
         'ICE 在 <b>2013-11</b> 才完成 NYSE Euronext 收购，但官方原表把 NYSE 的 '
         'ADV / RPC / OI <b>追溯并入了此前的每一个月</b>（原表注：for comparison '
         'purposes）—— 那 34 个月讲的是被收购前 NYSE Euronext 的量，<b>不是 ICE 的</b>。'
         # ⚠ 原文写的是「这是本表**唯一**一处口径断点」。那是个没有构建期判据的全称断言，
         #   正是这一页被改正过两次的那种句子。改成陈述**登记在案**的事实：断点表里
         #   只登记了这一条（fetch/ 的口径核对与页尾断点声明是同一份），而不是宣称
         #   数据里不可能还有别的断点。
         f'口径断点表里<b>只登记了这一条</b>，而本页的月度窗口自 <b>{mlab(W0)}</b> 起'
         '（季度块的左端由同一个月份换算），'
         '<b>整段窗口都在断点右侧</b> ⇒ 页面上出现的 NYSE 各列全部是收购完成后的实际口径，'
         '图上也就没有那条竖虚线。'
         f'⚠️ 但 <code>series/ice.csv</code> 本身回溯到 {mlab(df.index[0])}：'
         '要拿本页之外的更早月份做同比或排名，先把那 34 个月扣掉。'),
    ]

# ==========================================================================
# 【notes】
# ==========================================================================

# -*- coding: utf-8 -*-
"""build/ice.py 的「页尾 notes」段（口径与方法说明）。

本文件是**分段草稿**：正式合并进 build/ice.py 时，
  · 「§0 合并时删除」那一整块（本地 helper 与 __main__ 自测桩）删掉，
    因为 mlab / qlab__notes / comma / pctf / pp / nz / L / COL / COST_LOG / … 由其他段提供；
  · 其余部分（现算 helper + build_notes）原样搬过去。

━━ 这一段在页面上的分工 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
brief 说「**这个月**这组读数怎么读」（每月重写）；图注说「**这一张图**怎么读」
（CONTRACT §6.1 第 3 条：逐图代价印在图注里，页尾这一段顶替不了它）；
本段说「**这些数是怎么来的**」—— 一年到头同一段，只有现算出来的数在动。

━━ 纪律：本段一个字面的「Exhibit N」都不许出现 ━━━━━━━━━━━━━━━━━━━━━━━
图号是分组顺序的函数：往中间插一张，后面全部整体位移，而 notes 不会跟着动。
`build/specs/enx.py:455` 与 `build/specs/sgx.py:841-848` 已经把这条写成规矩
（原话：「按图的标题点名，不写 Exhibit 号 —— 图号会随分组增删整体位移，标题不会」），
本页照办。`tools/check_yoy_caliber.py::check_page_mix()` 只在**一页混用两种同比口径**
时才要求 notes 里出现「Exhibit N」；本页全页只有单月同比一种，那条要求不触发
（判据：`if not (mom_ns and ttm_ns): return []`，tools/check_yoy_caliber.py:1651）。
⇒ 文件底部有一道 grep 自证：notes 里出现 Exhibit 字面量就停机。

━━ 这一轮要修的三处错话（它们今天就在页面上误导读者）━━━━━━━━━━━━━━━━━━
(1) `build/specs/ice.py:32` 与它读者可见的孪生段（`_NO_DECOMP_NOTE`，:432-459）印着
    「没有任何官方数字能对账」。**这是假的。**仓库自己在 `fetch/ice.py:254` 与
    `docs/verify/ice.md:515-529` 记着一次对账：`ADV × 交易日 × RPC` 反算季度收入，
    对上 ICE Key-Metrics 的分部收入 6/6 个季度在 ±1% 内（本机复现，见 _rev_form_stats）。
    诚实的拒绝理由是另外两条：① `series/ice.csv` 里**没有金额列**，而通用引擎的
    `decomp.value` 要一条真实存在的金额列（build/single.py:1425-1440 硬失败）；
    ② RPC 是**滚动三月均**，在月度粒度上与单月量错配。**不是「对不上」。**
    本轮页面已经加进季度收入块，所以这段整体改写成「为什么是季度、为什么不是月度」。
(2) 两条页尾注仍把「分项之和 ≠ 合计」归因于「分项与合计各用各的交易日归一」。
    这个因果已被 `fetch/ice.py:123-131` 证伪（偏差最大的 2011-08 / 2011-10 / 2012-08
    里两列交易日**恰恰相等** —— 本机现算：`_tdays_stats()` 与 `_split_stats()`）。
    glossary（build/specs/ice.py:826-836、:855-864）已经改正过，notes 没跟上。
    换成可核的事实：差异几乎全部落在 2011-04…2012-12，2014-01 之后最大差 1 千张；
    **成因官方从未说明，本仓也未查明。**
(3) （跨页，只记录，**本轮不改**）`build/cboe.py:7-11` 与它 Ex4 的 `src_extra`
    （build/cboe.py:1171）声称 Cboe 是覆盖池里唯一按月同时披露 ADV 与 RPC 的名字。
    ICE 六个衍生品大类加 NYSE 期权与现货都按月同时披露，而且**不滞后**
    （本页 `_rpc_monthly_pairs()` 现算得出配对数）。改 cboe.py 不在本段范围内。
"""

# ══════════════════════════════════════════════════════════════════════════════
# §0 合并进 build/ice.py 时**整块删除** —— 这些名字由前面的段提供
#    （冻结契约：mlab / qlab__notes / num / comma / pctf / pp / L / nz / caliber_stats /
#     yoy_cal_zh / COST_LOG / COL / WIN_FROM / WIN_TABLE）
# ══════════════════════════════════════════════════════════════════════════════
_HERE = os.path.dirname(os.path.abspath(__file__))

def qlab__notes(q):
    """Period('2026Q2','Q') → '2Q26'（与 cme.py / cboe.py 一致）。"""
    return f'{q.quarter}Q{q.year % 100:02d}'

#: 三套交易日。ICE 特有陷阱 ①：各条 ADV 各归一各的，总 ADV 横跨两侧、
#: **没有哪一套日历能代表它**（build/specs/ice.py:_NOTE_TTM_FO）。
_TD_COLS__notes = ('trading_days_commod', 'trading_days_rates', 'trading_days_us_equities')

_TD_ZH = {'trading_days_commod': '大宗商品', 'trading_days_rates': '金融',
          'trading_days_us_equities': '美股'}

BREAK_ZH = 'NYSE Euronext 收购完成；此前 NYSE 各列为追溯并入的形式数'

def _coverage(df):
    """(首月, 末月, 月数, 是否逐月连续)。连续性现验 —— 断月不是「少一格」而是口径事故。"""
    idx = df.index
    full = pd.period_range(idx[0], idx[-1], freq='M')
    return idx[0], idx[-1], len(idx), bool(len(full) == len(idx) and (full == idx).all())

def _nonint_census__notes(df):
    """(非整数列名, 非整数格数)。名单里出现 rpc_/share_ 之外的列 → 停机。

    ⚠ 判据必须管着**列名**而不只是列数：只数列数的话，哪天某条张数列发了小数，
    「非整数的只有 RPC 与份额」这句全称断言会继续印，而没有任何东西会报错
    （build/specs/ice.py:167-176 记着这个坑）。
    """
    names, cells = [], 0
    for c in df.columns:
        s = pd.to_numeric(df[c], errors='coerce')
        bad = int(((s - s.round()).abs() > 1e-9).sum())
        if bad:
            names.append(c)
            cells += bad
    off = [c for c in names if not c.startswith(_NONINT_OK)]
    if off:
        raise SystemExit(
            f'series/ice.csv：页尾断言「非整数的只有 RPC 与份额那几列」，但 '
            f'{"、".join(off)} 也有非整数格 —— 断言与数据对不上，先改注再构建。')
    return names, cells

def _tdays_stats(df):
    """三套交易日两两相等的月数 + 全表极值。

    这一组数服务的是 ③「三套交易日与它们禁止的算术」。**只报事实，不报因果** ——
    「两套交易日不同」曾被拿去解释「分项之和 ≠ 合计」，`fetch/ice.py:123-131`
    已经把那个因果证伪，见 `_split_stats()`。
    """
    out = {'pairs': [], 'n': len(df)}
    for a, b in itertools.combinations(_TD_COLS__notes, 2):
        m = df[a].notna() & df[b].notna()
        out['pairs'].append((a, b, int(m.sum()), int((df[a][m] == df[b][m]).sum())))
    out['all_eq'] = int((df[list(_TD_COLS__notes)].nunique(axis=1) == 1).sum())
    out['lo'] = int(df[list(_TD_COLS__notes)].min().min())
    out['hi'] = int(df[list(_TD_COLS__notes)].max().max())
    return out

def _split_stats(df):
    """「大宗+金融 vs 衍生品总 ADV」：可比月数 / 精确相等月数 / 最大相对差 /
    大偏差落在哪一段 / 2014-01 之后最大绝对差 —— 以及那条**错因果的反证**。

    ⚠ 这里现算的最后两项（td 相等却不平的月数、td 不等却精确相等的月数）就是
    `fetch/ice.py:123-131` 那条口径坑的机器化：偏差最大的 2011-08 / 2011-10 / 2012-08
    里 `trading_days_commod` 与 `trading_days_rates` **恰恰相等**。
    ⇒ 页面上只许陈述「差在哪几个月、有多大」，不许写成因。
    """
    c = df['adv_commodities_kcontracts']
    f = df['adv_financials_kcontracts']
    t = df['adv_futures_options_kcontracts']
    d = c + f - t
    ok = t.notna() & c.notna() & f.notna() & (t != 0)
    rel = (d[ok] / t[ok]).abs() * 100.0
    big = d[ok][d[ok].abs() > 1]
    cut = pd.Period('2014-01', freq='M')
    late = d[ok][d[ok].index >= cut]
    eq = df['trading_days_commod'] == df['trading_days_rates']
    return {
        'n': int(ok.sum()), 'exact': int((d[ok] == 0).sum()),
        'max_rel': float(rel.max()), 'med_rel': float(rel.median()),
        'big_n': len(big),
        'big_from': (big.index.min() if len(big) else None),
        'big_to': (big.index.max() if len(big) else None),
        # 偏差最大的三个月**逐月点名**，并把两列交易日一起印出来 —— 那才是反证本身。
        # 只写「最大那几个月一带」是把反证退回成一句需要读者相信的话。
        'worst3': [(p, int(abs(d[p])), int(df.loc[p, 'trading_days_commod']),
                    int(df.loc[p, 'trading_days_rates']))
                   for p in d[ok].abs().sort_values(ascending=False).index[:3]],
        'late_n': int(len(late)), 'late_cut': cut,
        'late_max': float(late.abs().max()),
        # 错因果的反证（两个方向都要，只报一个方向读者会以为是巧合）
        'td_eq_n': int((eq & ok).sum()),
        'td_eq_unbalanced': int(((d != 0) & eq & ok).sum()),
        'td_ne_n': int(((~eq) & ok).sum()),
        'td_ne_exact': int(((d == 0) & (~eq) & ok).sum()),
    }

def _sum_check__notes(df, children, total, tol=2.0):
    """(可比月数, 逐格精确相等的月数, 差 ≤tol 的月数)。抄 build/specs/ice.py:_sum_check__notes。"""
    t = df[total]
    s = df[list(children)].sum(axis=1, min_count=len(children))
    ok = t.notna() & s.notna()
    d = (s[ok] - t[ok]).abs()
    return int(ok.sum()), int((d < 1e-9).sum()), int((d <= tol).sum())

def _share_selfcheck__notes(df):
    """官方 `share_nyse_us_cash_matched` vs 三带自算 —— (可比月数, 最大 pp 差)。

    ⑥ 那条「官方没有 A+B+C matched 的合计行，只给了这一列」要有据可核。
    上界向上取整（`_ceil_to__notes`）：四舍五入有一半概率把「最大值」取小，
    印出来的上界含不住实测值（build/specs/ice.py:319-327）。
    """
    tapes = 'ABC'
    mat = sum(df[f'adv_nyse_tape{t}_matched_mnsh'] for t in tapes)
    con = sum(df[f'adv_tape{t}_consolidated_mnsh'] for t in tapes)
    own = mat / con
    d = (df['share_nyse_us_cash_matched'] - own).abs() * 100.0
    d = d.dropna()
    return int(len(d)), float(d.max())

def _ceil_to__notes(v, nd):
    """向**上**取到 nd 位小数 —— 印「最大不超过 X」时必须这么取（理由同上）。"""
    import math
    f = 10.0 ** nd
    return math.ceil(v * f - 1e-9) / f

def _tape_denom_demo(df):
    """三条 Tape 份额的分母是**该带自己**的合并量 —— 现算一个反例把差距量出来。

    按字面把它读成「除以三带合计」会把 Tape A 份额算错三倍多
    （build/specs/ice.py:925-930 记着这处更正）。月份现找（最新一个四列齐全的月），
    不写死 —— 写死的月份会在下一期发布后变成一句读者在图上找不到的话。
    """
    tapes = 'ABC'
    need = ([f'adv_nyse_tape{t}_matched_mnsh' for t in tapes]
            + [f'adv_tape{t}_consolidated_mnsh' for t in tapes]
            + ['share_nyse_tapeA_matched'])
    ok = df[need].notna().all(axis=1)
    if not ok.any():
        return None
    p = df.index[ok][-1]
    r = df.loc[p]
    con_all = sum(r[f'adv_tape{t}_consolidated_mnsh'] for t in tapes)
    return {'p': p, 'official': float(r['share_nyse_tapeA_matched']),
            'own': float(r['adv_nyse_tapeA_matched_mnsh'] / r['adv_tapeA_consolidated_mnsh']),
            'wrong': float(r['adv_nyse_tapeA_matched_mnsh'] / con_all)}

def _handled_vs_matched(df):
    """handled 比 matched 多多少 —— ⑥ 那句「份额只能用 matched」的量。"""
    tapes = 'ABC'
    hd = sum(df[f'adv_nyse_tape{t}_handled_mnsh'] for t in tapes)
    mt = sum(df[f'adv_nyse_tape{t}_matched_mnsh'] for t in tapes)
    r = (hd / mt).dropna()
    if r.empty:
        return None
    p = r.index[-1]
    return {'p': p, 'handled': float(hd[p]), 'matched': float(mt[p]),
            'gap': float(r[p] - 1.0), 'max_gap': float(r.max() - 1.0),
            'max_p': r.idxmax()}

def _venue_mix__notes(df, series_dir):
    """四家自营撮合量合计占全美合并量多少 —— 取「四家都有值的**最新一个月**」，现找。

    上一版把某一次实测连同「最新一个月」这半句一起写死了；等其余三家发齐，
    页面上那句自称的判据就当场变成假话（build/specs/ice.py:242-249）。
    """
    peer = {}
    for fn, _, _ in _PEERS + ((_NDAQ[0], _NDAQ[1], 1.0),):
        try:
            t = pd.read_csv(os.path.join(series_dir, fn))
            peer[fn] = t.set_index('month')
        except (OSError, KeyError):
            return None
    tapes = 'ABC'
    for p in reversed(df.index):
        m = str(p)
        r = df.loc[p]
        con = [r.get(f'adv_tape{t}_consolidated_mnsh') for t in tapes]
        nys = [r.get(f'adv_nyse_tape{t}_matched_mnsh') for t in tapes]
        if any(v is None or not np.isfinite(v) for v in con + nys) or not sum(con):
            continue
        total = float(sum(con))
        vals = {}
        bad = False
        for fn, col, mult in _PEERS:
            try:
                v = float(peer[fn].loc[m, col]) * mult
            except (KeyError, TypeError, ValueError):
                bad = True
                break
            if not np.isfinite(v):
                bad = True
                break
            vals[fn] = v
        if bad:
            continue
        try:
            nd = float(peer[_NDAQ[0]].loc[m, _NDAQ[1]])
        except (KeyError, TypeError, ValueError):
            continue
        if not np.isfinite(nd):
            continue
        out = {'p': p, 'total': total, 'nyse': float(sum(nys)),
               'nyse_pct': float(sum(nys)) / total * 100.0,
               'cboe_pct': vals['cboe.csv'] / total * 100.0,
               'ndaq_pct': nd * 100.0,
               'miax_pct': vals['miax.csv'] / total * 100.0}
        out['four_pct'] = (out['nyse_pct'] + out['cboe_pct']
                           + out['ndaq_pct'] + out['miax_pct'])
        out['rest_pct'] = 100.0 - out['four_pct']
        return out
    return None

def _cds_stats(df):
    """CDS 三列的首月（三列不一致就停机）、最新读数、以及「月长」的离散度。

    ⑩ 要说的是：这三列是**当月总量不是日均**，而本表三套交易日全是**交易日历**、
    没有一套是清算日历 ⇒ 本页对 CDS **不作任何月长修正**，把差多少现算出来给读者。
    """
    firsts = {}
    for c in _CDS_COLS:
        s = df[c].dropna()
        if not s.empty:
            firsts[c] = s.index[0]
    if len(firsts) != len(_CDS_COLS):
        return None
    if len(set(firsts.values())) != 1:
        raise SystemExit(
            f'series/ice.csv：页尾断言「CDS 三列自同一个月起」，实际 '
            f'{ {k: str(v) for k, v in firsts.items()} } —— 先改注再构建。')
    p0 = next(iter(firsts.values()))
    last = df[list(_CDS_COLS)].dropna().index[-1]
    dim = df.index.days_in_month
    return {'p0': p0, 'last': last,
            'lag_m': (p0.year - df.index[0].year) * 12 + (p0.month - df.index[0].month),
            'total': float(df.loc[last, 'cds_total_notional_usdbn']),
            'client': float(df.loc[last, 'cds_client_notional_usdbn']),
            'nonclient': float(df.loc[last, 'cds_nonclient_notional_usdbn']),
            'dim_lo': int(dim.min()), 'dim_hi': int(dim.max()),
            'dim_spread': float(dim.max() / dim.min() - 1.0)}

def _rpc_monthly_pairs(df):
    """「按月同时披露 ADV 与 RPC、且不滞后」的配对数 —— ② 的机器判据。

    这条现算同时是三处错话里第 (3) 处的证据：`build/cboe.py:7-11` 声称 Cboe 是覆盖池里
    唯一按月同时披露 ADV 与 RPC 的名字。**本段不改 cboe.py**（跨页，不在范围内），
    只把 ICE 这一侧的事实印在自己页上。
    """
    pairs = [
        ('能源', 'adv_energy_kcontracts', 'rpc_energy_usd'),
        ('农产品与金属', 'adv_ag_metals_kcontracts', 'rpc_ag_metals_usd'),
        ('大宗商品合计', 'adv_commodities_kcontracts', 'rpc_commodities_usd'),
        ('利率', None, 'rpc_rates_usd'),
        ('股指与 FX', None, 'rpc_other_financials_usd'),
        ('金融合计', 'adv_financials_kcontracts', 'rpc_financials_usd'),
        ('NYSE 美股期权', 'adv_nyse_equity_options_kcontracts', 'rpc_nyse_equity_options_usd'),
        ('NYSE 美股现货', 'adv_nyse_us_cash_handled_mnsh', 'rpc_nyse_us_cash_usd_per100sh'),
    ]
    last = df.index[-1]
    live = [zh for zh, a, r in pairs
            if np.isfinite(df.loc[last, r])
            and (a is None or np.isfinite(df.loc[last, a]))]
    # 「不滞后」= RPC 的末月与 ADV 的末月同一个月（Cboe 那边 RPC 要晚一格）。
    rpc_last = max(df[r].dropna().index[-1] for _, _, r in pairs)
    return {'n': len(live), 'zh': live, 'last': last, 'rpc_last': rpc_last,
            'no_lag': bool(rpc_last == last)}

def _rev_form_stats(df, qtr_rev, legs, recon_rows, q_full):
    """「为什么收入块是季度、不是逐月」的两组现算 —— ② 的承重段。

    ⚠ **两组数说的不是同一件事，页面上必须分开说**（写混了下个季度就会被数据证伪）：
      · 六个能与官方对账的点上：季末月 RPC 形式 vs 官方（本页用的那一种），
        以及逐月形式 vs 季末月形式（差多少）。这六个点上逐月形式一律偏低。
      · **全样本**（每条腿 × 每个完整季）上：逐月形式 vs 季末月形式**并不系统性偏低**，
        中位接近 0、两侧都有大偏差。
    ⇒ 「在能对账的六个点上逐月形式一致偏低」是可核的；
       「逐月形式系统性低估 1.3–2.1%」是假话。

    qtr_rev(df, leg, form) 由收入段提供：form='qend' 用季末月 RPC、'monthly' 逐月 RPC。

    ⚠ **全样本那一侧量的是 CSV 里<u>所有</u>完整季，不是页面窗口那 42 个季。**
    这句话的作用是「拦住一个会被下一期数据证伪的全称断言」，量的必须是断言覆盖的全体；
    只量画出来的那一段，等于让这句反证自己也变成一句窗口内的话
    （初稿就是这么写的：42 季 × 6 腿 = 252 个观测，区间 −9.15%~+19.82%，
    而全样本是 62 季 × 6 腿 = 372 个、区间 −10.14%~+19.82%）。
    """
    six = []
    for row in recon_rows:
        leg = row['leg']
        qe = qtr_rev(df, leg, 'qend')[row['q']]
        mo = qtr_rev(df, leg, 'monthly')[row['q']]
        six.append({'zh': leg['zh'], 'q': row['q'], 'official': row['official'],
                    'qend': float(qe), 'monthly': float(mo),
                    'qend_dev': float(qe / row['official'] - 1.0),
                    'mo_vs_qend': float(mo / qe - 1.0)})
    # 完整季 = 该季在 CSV 里有 3 个月。现算，不写死 —— 末季不完整时它自己会掉出去。
    qs = df.index.asfreq('Q')
    q_all = pd.PeriodIndex(
        sorted(pd.Series(1, index=qs).groupby(level=0).sum().pipe(
            lambda s: s[s == 3]).index), freq='Q')
    rel = []
    for leg in legs:
        qe = qtr_rev(df, leg, 'qend').reindex(q_all)
        mo = qtr_rev(df, leg, 'monthly').reindex(q_all)
        r = (mo / qe - 1.0).replace([np.inf, -np.inf], np.nan).dropna()
        rel.append(r)
    allr = pd.concat(rel) if rel else pd.Series(dtype=float)
    return {
        'six': six,
        'qend_worst': max(abs(s['qend_dev']) for s in six),
        'qend_worst_signed': max(six, key=lambda s: abs(s['qend_dev']))['qend_dev'],
        'mo_lo': min(s['mo_vs_qend'] for s in six),
        'mo_hi': max(s['mo_vs_qend'] for s in six),
        'mo_all_low': all(s['mo_vs_qend'] < 0 for s in six),
        'n': int(len(allr)), 'n_legs': len(legs), 'n_q': int(len(q_all)),
        'q_from': q_all[0], 'q_to': q_all[-1], 'n_q_win': int(len(q_full)),
        'med': float(allr.median()), 'mean': float(allr.mean()),
        'lo': float(allr.min()), 'hi': float(allr.max()),
    }

def _agg_gap(df, qtr_rev, agg_leg, children, q_all):
    """「两条腿之和 vs 官方聚合层」差多远 —— ⑬(c) 的量。

    残差来源是 RPC 只有 2 位小数（分子分母各自取整），**不是口径错配** ——
    但这句话要有据：把中位、最大、以及超 1% / 超 2% 的季度数现算出来，
    读者才判得出「近似」是多近。
    """
    a = qtr_rev(df, agg_leg, 'qend').reindex(q_all)
    s = sum(qtr_rev(df, c, 'qend').reindex(q_all) for c in children)
    r = ((s / a - 1.0) * 100.0).replace([np.inf, -np.inf], np.nan).dropna()
    return {'n': int(len(r)), 'med': float(r.abs().median()), 'max': float(r.abs().max()),
            'gt1': int((r.abs() > 1).sum()), 'gt2': int((r.abs() > 2).sum())}

def _break_coverage(ex_span, brk_month):
    """断点月落在哪几张图的横轴里 —— ⑤ 的机器判据，**不许人肉列图名**。

    三类（分类没接住任何一张就停机 —— 抄 build/cboe.py:2141-2152 的兜底思路：
    「分类没接住的图直接停机。停机比出一页『看起来逐图交代了、其实少一张』便宜」）：
      · 'draw'  月度/季度连续横轴，且断点月落在窗口内 ⇒ 画得出竖线；
      · 'out'   同上，但断点月在窗口左端之前 ⇒ 图上没有这条线，因为那段历史压根没画；
      · 'cant'  横轴不连续（热力矩阵按产品 × 月分格）或不是月度刻度（季度轴落不到某一个月）
                ⇒ **结构上画不了**，读同比要自己扣掉这一层。
    """
    b = pd.Period(brk_month, freq='M')
    out = {'draw': [], 'out': [], 'cant': []}
    for n, e in sorted(ex_span.items()):
        title = e['title']
        if e.get('axis') == 'month':
            out['draw' if e['from'] <= b <= e['to'] else 'out'].append(title)
        elif e.get('axis') in ('quarter', 'matrix', 'table'):
            out['cant'].append(title)
        else:
            raise SystemExit(
                f'页尾「口径断点」条没有交代到「{title}」：它的横轴既不是本页月度刻度、'
                f'也不是季度 / 矩阵 / 表。先给它归一类（连同真实范围一起印给读者），'
                f'不要把断言删掉了事。')
    return out

def _ratio_caliber_rows(col_meta):
    """按 build/single.py 的判据把 COL 分成三档 —— ⑦ 的正文，本文件**一条判据都不自写**。

    ⚠ 判据一律调 `SG.col_is_ratio()` / `SG.col_is_money_ratio()` / `SG.rhs_ylab2()`。
    `build/pctile.py` 的模块头记着这条教训：各页各写一份，正是同一条序列在两页被判定
    相反的原因。这里连「哪三档」都不自己数，直接读 `rhs_ylab2()` 印出来的那句话。

    返回 {ylab2 字符串: [(zh, unit), …]}，顺序按 COL 的插入序（= 页面出现顺序）。
    """
    import single as SG
    buckets = {}
    for c in col_meta.values():
        lab = SG.rhs_ylab2(c, mom=True)
        buckets.setdefault(lab, []).append((c['zh'], c.get('unit') or ''))
    return buckets

def _cell(v, meta):
    """一格读数按**这一列自己的 fmt** 印（CONTRACT §5：小数位一律等于官方发的位数）。

    没有 fmt 的列（核对表与图都没收它、COL 里也就没有它）退回按值本身推位数 ——
    退回也要退到「印得出这个数」，不是一律 0 位：`rpc_commodities_usd` 用 0 位会印成
    「2」，读者以为费率是两美元整（初稿就是这么错的）。
    """
    if v is None or not np.isfinite(v):
        return '—'
    fmt = str(meta.get('fmt') or '')
    if fmt.startswith('pct'):
        dec = int(fmt[3:] or 1)
        return f'{v * float(meta.get("scale") or 1):,.{dec}f}%'
    if fmt.startswith('f') and fmt[1:2].isdigit():
        return comma(v, int(fmt[1]))
    if float(v) == round(float(v)):
        return comma(v, 0)
    return comma(v, 3).rstrip('0').rstrip('.')

def _dropped_cols(df, tbl_cols, page_cols, col_meta, col_zh):
    """核对表装不下的列：**逐条点名 + 最新读数**，并声明它们仍在 CSV 里 —— ⑫。

    分两档，因为读者要问的其实是两个不同的问题：
      · 'chart' 图上画着、只是没进核对表 ⇒ 想核数去看那张图的水平值；
      · 'off'   全页一处都没露面 ⇒ 只有 CSV 里有，这是本段唯一能告诉读者的地方。
    中文名取不到就**只印列名**，不把列名当中文名再印一遍（初稿印成
    「adv_gasoil_kcontracts（adv_gasoil_kcontracts）」，读者会以为那是两个东西）。
    """
    last = df.index[-1]
    out = {'chart': [], 'off': []}
    for c in df.columns:
        if c in tbl_cols:
            continue
        meta = col_meta.get(c) or {}
        zh = meta.get('zh') or col_zh.get(c)
        head = f'{zh}（<code>{c}</code>）' if zh else f'<code>{c}</code> '
        out['chart' if c in page_cols else 'off'].append(
            head + _cell(df.loc[last, c], meta))
    out['last'] = last
    return out

def _cost_rows(cost_log, ex_title):
    """逐图代价的正文 —— 从 COST_LOG **现读**，图号一个都不写，按标题点名。

    ⚠ COST_LOG[n] 的值是 **list**（抄 build/cme.py:466）：一张图可以画不止一条同比线，
    一条线的毛刺说不了另一条（CONTRACT §6.1 第 3 条：「逐图」是字面意思，
    而且要拿**这条序列自己**实测）。所以这里逐条线展开，不按图折叠。
    """
    rows = []
    for n in sorted(cost_log):
        title = ex_title[n]
        for item in cost_log[n]:
            rows.append((title, item['label'], item['d']))
    # 排版逐字抄 build/cme.py:1969-1974，只把「Exhibit N」换成标题 —— 三样统计量
    # （逐月标准差／相邻月最大跳变**带月份**／符号相反的月份数）是 §6.1 第 3 条点名要的，
    # 本文件一个都不自己算：全部现读 `yoy.caliber_diff()` 的返回。
    # `maxjump_mom` 是三元组 (pp, 前一月, 后一月)，取 [2]（跳到的那个月）。
    def _m(x):
        return mlab(x) if isinstance(x, pd.Period) else str(x)
    txt = '；'.join(
        f'<b>「{t}」</b>{("（" + lab + "）") if lab else ""}'
        f'{d["std_mom"]:.1f}pp／最大跳变 {d["maxjump_mom"][0]:.0f}pp'
        f'（{_m(d["maxjump_mom"][2])}）／符号相反 {d["opposite_n"]} 个月'
        f'（{d["opposite_n"] / d["n"] * 100:.0f}%，共 {d["n"]} 个可比月）'
        for t, lab, d in rows)
    # 「最毛 / 最稳」点到**线**不是点到图：一张图可以有两条线（本页「合约构成」就有两条），
    # 只报图名的话读者不知道说的是哪一条（初稿把两条都叫「合约构成」）。
    def _name(t, lab):
        return f'「{t}」' + (f'（{lab}）' if lab else '')
    sd = {_name(t, lab): d['std_mom'] for t, lab, d in rows}
    hi = max(sd, key=sd.get)
    lo = min(sd, key=sd.get)
    return {'txt': txt, 'n': len(rows), 'hi': hi, 'lo': lo,
            'hi_sd': sd[hi], 'lo_sd': sd[lo],
            'ratio': (sd[hi] / sd[lo]) if sd[lo] else float('nan')}

# ══════════════════════════════════════════════════════════════════════════════
# 2. 正文
# ══════════════════════════════════════════════════════════════════════════════
def build_notes(df, *, col_meta, col_zh, cost_log, ex_title, ex_span, tbl_cols,
                page_cols, qtr_rev, rev_legs, bridge_legs, agg_legs, recon_rows,
                recon_src, recon_pub, q_full, series_dir, win_from=WIN_FROM):
    """页尾 notes（13 条，顺序即重要性：最容易被读错的口径排在最前）。

    参数全部是**别的段的产物**，本段一条都不自己造：
      col_meta     COL 列元数据表（判 ratio / money_ratio / ylab2 用；只覆盖上页的列）
      col_zh       CSV **全部**列 → 中文名（⑫ 要给没上页的列也报个名字）
      cost_log     {图号: [ {'label':…, 'd': caliber_diff 结果}, … ]}
      ex_title     {图号: 标题}      —— 本段按标题点名，从不印图号
      ex_span      {图号: {'title','axis','from','to'}}
      tbl_cols     末尾核对表实际用到的 CSV 列
      page_cols    全页任何一张图用到的 CSV 列
      qtr_rev      qtr_rev(df, leg, form) → 季度收入 Series（form: 'qend' / 'monthly'）
      rev_legs     六条腿的定义（含 zh）
      bridge_legs  桥覆盖的那四条腿
      agg_legs     [(官方聚合层的腿, [它应当等于的那几条子腿]), …]（⑬(c) 的近似性）
      recon_rows   官方六个对账数（外部常量表，带出处与发布日）
      q_full       完整季的 PeriodIndex
    """
    import single as SG

    p0, p1, n_m, contig = _coverage(df)
    if not contig:
        raise SystemExit('series/ice.csv 有断月 —— 页尾说「逐月连续」，先修数据再构建。')
    nonint_cols, nonint_cells = _nonint_census__notes(df)
    TD = _tdays_stats(df)
    SP = _split_stats(df)
    EN = _sum_check__notes(df, ['adv_brent_kcontracts', 'adv_gasoil_kcontracts',
                         'adv_otheroil_kcontracts', 'adv_natgas_kcontracts',
                         'adv_power_kcontracts', 'adv_environmentals_kcontracts'],
                    'adv_energy_kcontracts')
    FI = _sum_check__notes(df, ['adv_stir_kcontracts', 'adv_mltir_kcontracts',
                         'adv_equity_index_kcontracts', 'adv_fx_credit_kcontracts'],
                    'adv_financials_kcontracts')
    SH_N, SH_MAXPP = _share_selfcheck__notes(df)
    TAPE = _tape_denom_demo(df)
    HM = _handled_vs_matched(df)
    MIX = _venue_mix__notes(df, series_dir)
    CDS = _cds_stats(df)
    RPCM = _rpc_monthly_pairs(df)
    REV = _rev_form_stats(df, qtr_rev, rev_legs, recon_rows, q_full)
    _q_all = pd.period_range(REV['q_from'], REV['q_to'], freq='Q')
    AGG = [(agg, kids, _agg_gap(df, qtr_rev, agg, kids, _q_all))
           for agg, kids in agg_legs]
    BRK = _break_coverage(ex_span, BREAK_MONTH)
    CAL = _ratio_caliber_rows(col_meta)
    DROP = _dropped_cols(df, tbl_cols, page_cols, col_meta, col_zh)
    COST = _cost_rows(cost_log, ex_title)

    # 收入结构的覆盖率：桥只盖得住四条腿，这个比例必须现算（页面在图注里也印一次）。
    q_last = q_full[-1]
    leg_rev = {lg['key']: float(qtr_rev(df, lg, 'qend')[q_last]) for lg in rev_legs}
    tot_rev = sum(leg_rev.values())
    br_rev = sum(leg_rev[lg['key']] for lg in bridge_legs)
    energy_rev = leg_rev[rev_legs[0]['key']]

    # 存量列（OI 六条）不欠逐图代价那笔债：CONTRACT §6.1 第 3 条只管**流量**。
    stock_titles = [e['title'] for e in ex_span.values() if e.get('stock')]

    notes = []

    # ─────────────────────────────────────────────────────────────────────────
    # ① 单月同比口径 + 逐图代价点名
    # ─────────────────────────────────────────────────────────────────────────
    notes.append(
        f'<b>本页覆盖 {mlab(p0)} – {mlab(p1)} 共 {n_m} 个月，逐月连续无缺口</b>'
        f'（断月会在构建期直接停机）；月度图的左端统一在 {win_from}。'
        f'<b>同比一律用<u>单月</u>口径，不是 12 个月滚动合计 —— 页面所有者指定，'
        f'全站统一</b>（<code>build/CONTRACT.md</code> §6：'
        f'「全站同比只有一种口径：单月同比，页面上一条 12 个月滚动合计的同比都不画」）。'
        f'好处是<b>柱与线取自同一列</b>：拿一根柱除以 12 根柱之前那根，就是金线上的那一点，'
        f'读者能自己核。'
        f'<b>代价照写，不藏</b>：单月同比把「去年那<b>一个</b>月碰巧是什么样」整个塞进分母，'
        f'去年同月若是异常低点，今年一个平淡的月份也能印出三位数增速；'
        f'后果不是噪声大一点，而是<b>方向会反</b>。'
        f'<b>代价是逐图的</b>（§6.1 第 3 条：「逐图」是字面意思，页尾这一段顶替不了它）——'
        f'每一张画流量单月同比的图，图注里印的都是<u>那条线自己</u>的实测。'
        f'各条线的毛刺差得很远，所以在这里并排摆一次'
        f'（逐月标准差／相邻月最大跳变／与 12 个月滚动口径符号相反的月份数；'
        f'统计范围都是各图自己画出来的那段窗口，滚动那一侧本页一条都不画、只作对照）：'
        + COST['txt'] + '。'
        + f'最毛的是<b>{COST["hi"]}</b>（{COST["hi_sd"]:.1f}pp），'
        f'最稳的是<b>{COST["lo"]}</b>（{COST["lo_sd"]:.1f}pp），'
        f'相差 {COST["ratio"]:.1f} 倍 —— <b>不要拿其中一条线的数去读另一条</b>。'
        + (f'<b>月末未平仓那几张（{"、".join(f"「{t}」" for t in stock_titles)}）不在这份账本里</b>：'
           f'它们读的是<b>存量</b>（月末快照），同比是两个<b>时点</b>的点对点比较，'
           f'从来没有「12 个月滚动合计」这个选项（把 12 个月末的持仓加起来不是任何东西），'
           f'所以 §6.1 第 3 条那笔逐图代价的债它们不欠 —— 那一条只管流量。'
           f'「流量与存量各自的合法口径」不是本页自订的判据，实现在全站唯一的 '
           f'<code>build/yoy.py</code> 里，对存量调滚动合计会直接抛错。'
           if stock_titles else ''))

    # ─────────────────────────────────────────────────────────────────────────
    # ② RPC 是费率不是价 + 为什么收入块是季度（**这一条整体改写，见文件头错话 (1)**）
    # ─────────────────────────────────────────────────────────────────────────
    _six_txt = '；'.join(
        f'{s["zh"]} {qlab__notes(s["q"])}：本页 ${s["qend"]:.1f}mn vs 官方 ${s["official"]:.0f}mn'
        f'（{pctf(s["qend_dev"], 2)}）'
        for s in REV['six'])
    notes.append(
        f'<b>⚠️ <code>rpc_*</code> 是每张<u>收入</u>（费率），不是成交价。</b>'
        f'官方定义（表内脚注 1）= 交易收入 ÷ 合约量：分子是 ICE 向会员收的费，'
        f'不是市场撮合出来的价格。它长得像「价」（美元/张），语义完全不同 —— '
        f'把它当成交价，「成交量加权平均成交价」那一整套措辞句句是假的。'
        f'<b>而且它是滚动三月均</b>，所以<b>不能拿它乘单月量当单月收入</b>。'
        f'与 Cboe 不同，<b>ICE 的 RPC 不滞后</b>：本页 {RPCM["n"]} 组'
        f'（{"、".join(RPCM["zh"])}）按月同时披露量与费率，'
        + (f'两侧的末月同为 {mlab(RPCM["last"])}（现验）。'
           if RPCM['no_lag'] else
           f'但本期费率只到 {mlab(RPCM["rpc_last"])}、量已到 {mlab(RPCM["last"])}，'
           f'这一期出现了滞后，读末月请留意。')
        + f'<b>它们的同比是<u>美元差</u>不是百分比</b>：两个各带 2 位小数的美元/张相减，'
        f'差还是美元/张（次轴写作「{SG.rhs_ylab2({"col": "rpc_energy_usd", "zh": "能源", "unit": "USD/contract", "fmt": "f2"}, mom=True)}」）。'
        f'<b>本页因此不画成交额的量价分解</b> —— 恒等式「成交额 ≡ 成交量 × 成交价」'
        f'两边本表都凑不齐。'
        f'<b>但「交易收入 ≡ 成交量 × 每张费率」这条恒等式本页是有数的，而且这一轮把它画了出来</b>'
        f'（隐含收入那一组）。'
        f'<b>⚠️ 这里要更正一句在本页挂了很久的错话</b>：旧版页尾写着'
        f'「用 ADV × 交易日 × RPC 造出来的收入没有任何官方数字能对账」。'
        f'<b>那是假的</b> —— 本仓 <code>fetch/ice.py</code> 与 <code>docs/verify/ice.md</code> '
        f'早就记着一次对账，本页在构建期逐点复现：{_six_txt}；'
        f'{len(REV["six"])} 个点<b>全部落在 ±'
        f'{_ceil_to__notes(abs(REV["qend_worst"]) * 100, 2):.2f}% 内</b>'
        f'（上界<b>向上</b>取整 —— 四舍五入有一半概率把「最大值」取小，'
        f'印出来的上界含不住实测的 {pctf(REV["qend_worst_signed"], 2)}），'
        f'残差来自 RPC 只保留 2 位小数。'
        f'真正的拒绝理由是另外两条，与「对不上」无关：'
        f'① <code>series/ice.csv</code> 里<b>没有金额列</b>，而通用引擎的分解图要一条'
        f'<b>真实存在的</b>金额列（<code>build/single.py</code> 在这里是硬失败）；'
        f'② RPC 是滚动三月均，与<b>单月</b>量相乘是口径错配。'
        f'<b>⇒ 所以收入这一块整体做成<u>季度</u>，不是逐月。</b>'
        f'做法是「季内 3 个月各自的（ADV × 该腿对应的交易日）先加起来，再乘<b>季末月</b>的 RPC」——'
        f'ICE 的 RPC 是滚动三月均，季末月那一格的窗口恰好覆盖该季度。'
        f'<b>两种形式差多少，本页现算给读者，而且两个方向要分开说</b>：'
        f'在上面这 {len(REV["six"])} 个<b>能与官方对账</b>的点上，'
        + ('逐月形式相对季末月形式<b>一律偏低</b> '
           f'{abs(REV["mo_hi"]) * 100:.2f}–{abs(REV["mo_lo"]) * 100:.2f}%'
           if REV['mo_all_low'] else
           f'逐月形式相对季末月形式落在 {pctf(REV["mo_lo"], 2)} – {pctf(REV["mo_hi"], 2)}')
        + f'；<b>但这不能推广</b> —— 把 {REV["n_legs"]} 条腿 × '
        f'{REV["n_q"]} 个完整季（{qlab__notes(REV["q_from"])} – {qlab__notes(REV["q_to"])}，'
        f'<b>全样本，不是页面窗口那 {REV["n_q_win"]} 个季</b>）共 {REV["n"]} 个观测全看一遍，'
        f'逐月形式<b>并不系统性偏低</b>：中位 {REV["med"] * 100:.3f}%、'
        f'均值 {pctf(REV["mean"], 3)}、区间 {pctf(REV["lo"], 2)} ~ {pctf(REV["hi"], 2)}，'
        f'两侧都有大偏差。'
        f'<b>⇒ 页面上只说得上「在能对账的那几个点上逐月形式一致偏低」；'
        f'说「逐月形式系统性低估百分之一二」是假话</b> —— '
        f'后者是一句下个季度的数据就能证伪的话，而且证伪它的数就在上面这一行里。')

    # ─────────────────────────────────────────────────────────────────────────
    # ③ 三套交易日与它们禁止的算术（**含错话 (2) 的更正**）
    # ─────────────────────────────────────────────────────────────────────────
    _pair_txt = '、'.join(
        f'{_TD_ZH[a]} vs {_TD_ZH[b]} 相等 {eq}/{n} 个月'
        for a, b, n, eq in TD['pairs'])
    notes.append(
        f'<b>ICE 有<u>三套</u>交易日，各条 ADV 各归一各的：</b>'
        f'<code>trading_days_commod</code>（大宗商品）、<code>trading_days_rates</code>（金融）、'
        f'<code>trading_days_us_equities</code>（美股期权与现货）。'
        f'实测 {TD["n"]} 个月里三套完全一致的只有 {TD["all_eq"]} 个月（{_pair_txt}；'
        f'全表各月落在 {TD["lo"]}–{TD["hi"]} 天之间）。'
        f'<b>⇒ 两条算术本页禁止</b>：'
        f'（a）<b>不许把「衍生品总 ADV」乘回成当月合计</b> —— 那一列横跨商品与金融两侧，'
        f'<b>没有哪一套日历能代表它</b>，硬挑一套会给一半的量配错权重，而图上完全看不出来；'
        f'（b）<b>不许拿一条腿的交易日去乘另一条腿</b> —— 隐含收入那一组的六条腿'
        f'各自配自己那一套（大宗两条用商品日历、金融四条用金融日历、NYSE 两条用美股日历），'
        f'配错一条，那条腿的收入会整体偏几个百分点。'
        f'<b>本页因此没有 CME 那张 day-count 图</b>：那张图的前提是「全公司只有一套交易日、'
        f'日均与当月合计两种口径可以并排比」，ICE 三套并存，画出来的差既不是交易日效应、'
        f'也不是别的什么可解释的东西。'
        f'另外，单月同比本身就把「今年这个月多开几天市」除掉了'
        f'（日均 ÷ 去年同月日均），所以本页的同比一条交易日列都用不上，'
        f'只有<b>季度收入</b>那一组要把日均还原成合约张数，那里才乘交易日。'
        f'<b>⚠️ 这里要更正另一句在本页挂了很久的错话</b>：旧版页尾把'
        f'「分项之和 ≠ 合计」归因于「分项与合计各用各的交易日归一」。'
        f'<b>那个因果已被证伪</b>（<code>fetch/ice.py</code> 的口径坑 6，本页构建期复算）：'
        f'两列交易日相等的 {SP["td_eq_n"]} 个月里有 {SP["td_eq_unbalanced"]} 个月对不平，'
        f'两列不等的 {SP["td_ne_n"]} 个月里反而有 {SP["td_ne_exact"]} 个月精确相等；'
        # 「偏差最大的那几个月两列恰恰相等」是一句**可以被下一期数据顶翻**的话，
        # 所以它不是写死的措辞而是一个分支：现算发现不再全等，这里自动换成中性说法，
        # 不会继续印一句假话（这正是本轮要修的那种句子）。
        + (f'而<b>偏差最大的三个月，两列交易日恰恰相等</b> —— '
           + '、'.join(f'{mlab(p)}（差 {g} 千张，两列同为 {a} 天）'
                       for p, g, a, _ in SP['worst3']) + '。'
           if all(a == b for _, _, a, b in SP['worst3']) else
           f'偏差最大的三个月是 '
           + '、'.join(f'{mlab(p)}（差 {g} 千张，两列 {a}/{b} 天）'
                       for p, g, a, b in SP['worst3'])
           + '，两列在其中一部分月份并不相等 —— 但上面那两个方向的计数已经说明'
             '「两列不等」既不必要也不充分。')
        + f'可核的事实只有这些：{SP["n"]} 个月里 {SP["exact"]} 个月精确相等，'
        f'相对差最大 {SP["max_rel"]:.3f}%、中位 {SP["med_rel"]:.3f}%；'
        f'差超过 1 千张的 {SP["big_n"]} 个月<b>全部落在 {mlab(SP["big_from"])} – '
        f'{mlab(SP["big_to"])}</b>，{mlab(SP["late_cut"])} 之后的 {SP["late_n"]} 个月里'
        f'最大差 {SP["late_max"]:.0f} 千张。'
        f'<b>成因官方从未说明，本仓也未查明</b> —— 写一个错的因果，'
        f'下一个人会去「修」一个修不好的东西。⇒ <b>不要当恒等式，也不要当校验条件。</b>')

    # ─────────────────────────────────────────────────────────────────────────
    # ④ 官方取整 + 现算的精确月数
    # ─────────────────────────────────────────────────────────────────────────
    notes.append(
        f'<b>月度值在官方原表里就已四舍五入到整千张 / 整百万股。</b>'
        f'全表非整数的只有 {len(nonint_cols)} 列（{nonint_cells:,} 个非整数格全落在它们身上，'
        f'名单现扫 —— 扫出 <code>rpc_*</code> / <code>share_*</code> 之外的列直接停机）。'
        f'⇒ 本页所有计数类一律按 <b>0 位小数</b>显示；小基数行（环境权益、FX 与 USDX）的同比'
        f'会与官方新闻稿差 1–2pp，那是<b>官方自己取整</b>造成的，不是解析错误。'
        f'同一层取整也解释了「分项加不回合计」这件事在<b>子项</b>那一层的形态'
        f'（成因见上一条：合计那一层官方没说明）：'
        f'六个能源子项之和 = 能源合计只在 {EN[1]}/{EN[0]} 个月精确成立（±2 千张内 {EN[2]}/{EN[0]}），'
        f'四个金融子项之和 = 金融合计只在 {FI[1]}/{FI[0]} 个月精确成立（±2 千张内 {FI[2]}/{FI[0]}）。'
        f'<b>⇒ 能源那张按产品拆的图只能画成堆叠面，不能画成「柱 + 分段」</b>：'
        f'后者要求各段之和逐格等于柱高（容差 1e-6），而这里逐格相等只是<b>部分月份</b>成立，'
        f'画出来会在构建期硬失败。'
        f'还有一处取整后果落在<b>费率</b>上：<code>rpc_nyse_equity_options_usd</code> '
        f'只有 2 位小数而量程只有 0.04–0.18，低端一格 = 25% —— '
        f'所以<b>期权那条腿单独的量价分解本页放弃</b>（费率腿同比会大量恰好为 0，'
        f'交叉项能到几十个百分点，画出来的两段不是分解而是取整噪声）。')

    # ─────────────────────────────────────────────────────────────────────────
    # ⑤ 2013-11 断点
    # ─────────────────────────────────────────────────────────────────────────
    _bl = lambda xs: '、'.join(f'「{t}」' for t in xs)
    notes.append(
        f'<b>本页唯一一处口径断点：{BREAK_MONTH}（{BREAK_ZH}）。</b>'
        f'ICE 直到 {BREAK_MONTH} 才完成 NYSE Euronext 收购，但官方原表把 NYSE 的 ADV / RPC / OI '
        f'<b>追溯并入了此前的每一个月</b>（原表注：for comparison purposes）——'
        f'那一段里的 NYSE 各列讲的是<b>被收购前 NYSE Euronext 的量，不是 ICE 的</b>，'
        f'与断点右边不可比。'
        + (f'落在横轴上、因此画着红色竖虚线的：{_bl(BRK["draw"])}。'
           if BRK['draw'] else
           f'<b>本页图上一条断点竖线都没有</b>，原因不是漏画：月度图的左端统一在 {win_from}，'
           f'断点月在它<b>左边</b>，那一段历史本页压根没画出来 —— '
           f'{_bl(BRK["out"])} 全部如此。说的和画的一致：本页任何一处图注都没有声称过存在断点线。')
        + (f'<b>另有几张结构上就画不了这条线</b>：{_bl(BRK["cant"])} —— '
           f'热力矩阵是「产品 × 月」的分格、没有连续横轴，季度刻度落不到某一个月，'
           f'核对表不是时序图。读它们的早期同比要自己扣掉这一层。'
           if BRK['cant'] else '')
        + f'⚠️ 若日后左端前移到 {BREAK_MONTH} 之前，这条线必须<b>画出来</b>而不是只在文字里提一句；'
        f'上面那份名单是构建期从各图真实横轴现算的，不是人肉维护的清单。')

    # ─────────────────────────────────────────────────────────────────────────
    # ⑥ matched vs handled + 三条 tape 各自的分母
    # ─────────────────────────────────────────────────────────────────────────
    notes.append(
        f'<b>matched ≠ handled。</b>handled = 本所撮合 + <b>路由到别家</b>交易所成交的量；'
        f'matched = <b>只算本所自己撮合</b>的那部分。'
        + ((f'实测 {mlab(HM["p"])}：三带 handled 合计 {comma(HM["handled"])} 百万股/日、'
            f'matched 合计 {comma(HM["matched"])}，handled 比 matched 多 '
            f'{HM["gap"] * 100:.1f}%（全表最大 {HM["max_gap"] * 100:.1f}%，'
            f'{mlab(HM["max_p"])}）。') if HM else '')
        + f'⇒ <b>市场份额只能用 matched 算</b>，拿 handled 当分子等于把别家的成交记在自己名下；'
        f'本页头条那条 NYSE 现货 ADV 量的是 NYSE Group 的<b>体量</b>（handled 口径），'
        f'所有份额列一律 matched，<b>两者不可互相换算</b>。'
        f'<b>⚠️ 三组份额的分母各不相同，按字面读会算错好几倍：</b>'
        f'（a）<b>三条 Tape 份额</b>的分母是<b>该带自己</b>的全市场合并量'
        f'（该带 matched ÷ 该带 consolidated），<b>不是</b>三条带的合计'
        + ((f' —— 现算 {mlab(TAPE["p"])}：官方 Tape A 份额 {TAPE["official"] * 100:.1f}%，'
            f'按该带自己的分母自算 {TAPE["own"] * 100:.1f}%（对上），'
            f'而按三带合计当分母只有 {TAPE["wrong"] * 100:.1f}%，差三倍多')
           if TAPE else '')
        + f'；（b）<b>NYSE 全美 matched 份额</b>才是三带之和除三带之和 —— '
        f'官方<b>没有</b> A+B+C matched 的合计行，只给了这一列'
        f'（与自算一致：{SH_N} 个可比月里最大差 {_ceil_to__notes(SH_MAXPP, 2):.2f}pp，'
        f'现算且上界<b>向上</b>取整，印出来的数永远含得住实测值）；'
        f'（c）<b>NYSE 期权份额</b>的分母是全美股票/ETF 期权行业总量（见下一条）。'
        f'三者都是<b>全市场</b>分母，<b>不是</b>「本页出现的这几家」池内份额。'
        f'另外这五条份额列在官方原表里是 <b>0–1 的小数</b>（0.191 = 19.1%），本页统一 ×100 显示；'
        f'<code>series/miax.csv</code> 的 <code>share_*_pct</code> 存的却是百分数，'
        f'两家形态相反，跨页取数别弄混。')

    # ─────────────────────────────────────────────────────────────────────────
    # ⑦ 比率同比是 pp、钱比率同比是美元差
    # ─────────────────────────────────────────────────────────────────────────
    _cal_txt = '；'.join(
        f'<b>{lab}</b> —— ' + '、'.join(f'{zh}（{u}）' for zh, u in items)
        for lab, items in CAL.items())
    notes.append(
        f'<b>「同比」在本页有三种单位，全部由<u>列的量纲</u>定，不是由排版定。</b>'
        f'判据只有一份，写在 <code>build/single.py</code> 里'
        f'（<code>col_is_ratio()</code> / <code>col_is_money_ratio()</code> / '
        f'<code>rhs_ylab2()</code>），本页一条都不自写 —— '
        f'<code>build/pctile.py</code> 的模块头记着这条教训：各页各写一份，'
        f'正是同一条序列在两页被判定相反的原因。现读的分档是：{_cal_txt}。'
        f'⇒ <b>量类</b>（张数、股数、名义额）的同比是<b>百分比</b>；'
        f'<b>份额</b>的同比是<b>百分点</b>（差不足 1pp 时改印 bp —— '
        f'份额从 19.1% 掉到 19.0% 写成「-0.0pp」读起来像没动，写成「-10bp」才是那件事）；'
        f'<b>RPC 这类「分子是钱」的比率</b>，同比既不是百分比也不是百分点，'
        f'而是<b>美元差</b>（USD/contract、USD/100 shares）。'
        f'<b>⚠️ 单位串是承重的，不许为排版重打。</b>本页的 <code>unit</code> 字符串'
        f'（<code>k contracts/day</code>、<code>k contracts</code>、'
        f'<code>USD/contract</code>、<code>USD/100 shares</code>、'
        f'<code>mn shares/day</code>、<code>USD bn/month</code>、<code>%</code>）'
        f'同时是轴标题、核对表表头与上面那套判据的输入 —— 改一个字，'
        f'某一列的同比会静默从「美元差」翻成「百分比」，页面上没有任何痕迹。'
        f'最刺眼的一处是 <code>oi_rates_kcontracts</code>：列名里有 rates，'
        f'自动分类器把它误判成比率列，<b>挡住这个假阳性的正是 '
        f'<code>k contracts</code> 这个量纲</b>（不是比率量纲）。'
        f'把它改成别的写法，那张月末未平仓图的次轴会翻成「pp y/y」，而它读的是张数。')

    # ─────────────────────────────────────────────────────────────────────────
    # ⑧ 期权行业分母是推断口径
    # ─────────────────────────────────────────────────────────────────────────
    _last = df.index[-1]
    notes.append(
        f'<b><code>adv_us_equity_options_industry_kcontracts</code> 是全美股票 / ETF 期权的'
        f'行业总量，<u>不含</u>指数期权 —— 但这是<u>推断</u>出来的口径，不是 ICE 的书面定义。</b>'
        f'依据是与 Cboe multilist 及 ICE 10-K 的交叉验证；'
        f'<b>工作簿里这一行没有任何脚注，ICE 从未书面定义过</b>，'
        f'<b>不要在页面上写成官方定义、也不要拿它去反推一个「指数期权行业量」</b>。'
        f'它是本页 NYSE 期权份额那条线的分母（{mlab(_last)}：行业 '
        f'{comma(df.loc[_last, "adv_us_equity_options_industry_kcontracts"])} 千张/日、'
        f'NYSE 两所合计 {comma(df.loc[_last, "adv_nyse_equity_options_kcontracts"])}、'
        f'官方直接给的份额 {df.loc[_last, "share_nyse_equity_options"] * 100:.1f}%）。'
        f'⇒ 份额那条线的<b>分子</b>是官方口径、<b>分母</b>是推断口径，'
        f'读绝对水平要打折扣，读<b>趋势</b>才是它的用法。')

    # ─────────────────────────────────────────────────────────────────────────
    # ⑨ 三次追溯重述
    # ─────────────────────────────────────────────────────────────────────────
    _w0 = pd.Period(win_from, freq='M')
    _rest = [('NGX 的量与收入追溯并入 2011 年起的 Other Oil / 天然气 / 电力 / 能源与商品合计',
              pd.Period('2011-01', freq='M')),
             ('2013 年起的电力 ADV、能源 RPC、能源 OI 按新的电力量折算法重算',
              pd.Period('2013-01', freq='M')),
             ('Russell 合约 2016-12 规格减半后，量 / OI / RPC 全部追溯调整',
              pd.Period('2016-12', freq='M'))]
    _in = [t for t, p in _rest if p >= _w0]
    _out = [t for t, p in _rest if p < _w0]
    notes.append(
        f'<b>历史上有三处官方追溯重刷，已体现在当前文件中</b>（本仓一次性全量摄入，不受影响）：'
        + '；'.join(f'{i + 1}）{t}' for i, (t, _) in enumerate(_rest)) + '。'
        + f'<b>后果是本仓 CSV 与 ICE 历年季报 / 10-K 原文里的数字可能对不上 —— 以当前文件为准。</b>'
        + (f'其中 {len(_out)} 处发生在本页月度窗口（{win_from} 起）<b>左边</b>，'
           f'页面上看不到；'
           if _out else '')
        + (f'<b>{len(_in)} 处落在窗口<u>之内</u>：{"；".join(_in)}</b> —— '
           f'那一格前后的合约规格不同，读那一段的水平值与同比要知道这件事。'
           f'本页<b>不</b>为它画断点竖线：它只动一个产品线的合约规格，'
           f'不改任何一条本页画出来的序列的<b>外延</b>（与 {BREAK_MONTH} 那处不同）。'
           if _in else '窗口之内没有落到任何一处，所以页面上不作标注。'))

    # ─────────────────────────────────────────────────────────────────────────
    # ⑩ CDS 是当月总量不是日均，月长不作修正
    # ─────────────────────────────────────────────────────────────────────────
    notes.append(
        f'<b>CDS 三列是<u>当月清算名义总额</u>（gross notional，单边计），不是日均。</b>'
        + ((f'三列自 {mlab(CDS["p0"])} 起（比全表首月 {mlab(p0)} 晚 {CDS["lag_m"]} 个月；'
            f'两个月份都现算，三列首月对不上就停机），最新一期 {mlab(CDS["last"])}：'
            f'合计 ${comma(CDS["total"])}bn = 客户盘 ${comma(CDS["client"])}bn + '
            f'非客户盘 ${comma(CDS["nonclient"])}bn。')
           if CDS else '')
        + f'⚠️ 与本页其余 ADV 列<b>不是同一种口径</b>，不要顺着读成「每天多少」，'
        f'也不要与任何一条日均列相加或相除。'
        + ((f'<b>⚠️ 本页对它<u>不作月长修正</u>，这是有意的</b>：'
            f'月长在 {CDS["dim_lo"]}–{CDS["dim_hi"]} 天之间'
            f'（两端相差 {CDS["dim_spread"] * 100:.0f}%），这一层原样进到它的同比里。'
            f'不修的理由不是「差不多」，而是<b>没有可用的分母</b> —— '
            f'本表三套交易日全是<b>交易</b>日历，ICE Clear Credit 的<b>清算</b>日历'
            f'官方一列都没给；拿交易日历去除一条清算量，等于用一个来路不明的分母'
            f'换掉一个已知的偏差。⇒ 读 CDS 的同比请知道它含着月长这一层。')
           if CDS else '')
        + f'另外它<b>进不了</b>本页的收入分解：CDS 既没有费率列、也没有笔数或张数列，'
        f'配得上的数量维度一条都没有。')

    # ─────────────────────────────────────────────────────────────────────────
    # ⑪ 四家场所占合并量的比例（跨 CSV 现算）
    # ─────────────────────────────────────────────────────────────────────────
    notes.append(
        f'<b><code>adv_tape{{A,B,C}}_consolidated_mnsh</code> 是<u>全美合并成交量</u>，'
        f'不是 NYSE 自己的量</b> —— 它是本页跟踪「场外化侵蚀」唯一的证据。'
        + ((f'跨 CSV 现算 {mlab(MIX["p"])}（四家份额都有值的最新一个月，逐月现找）：'
            f'三条带合并 {comma(MIX["total"])} 百万股/日，'
            f'NYSE matched {comma(MIX["nyse"])}（{MIX["nyse_pct"]:.2f}%）、'
            f'Cboe {MIX["cboe_pct"]:.2f}%、Nasdaq 三盘口 {MIX["ndaq_pct"]:.2f}%、'
            f'MIAX Pearl {MIX["miax_pct"]:.2f}% —— '
            f'<b>四家合计 {MIX["four_pct"]:.2f}%，其余 {MIX["rest_pct"]:.2f}% '
            f'成交在暗池 / 内化商 / TRF</b>。'
            f'⚠️ 这个月份是<b>现找</b>的，可能比本页头条月早一两期：'
            f'四家不是同一天发布，取「四家都齐」的最新月是为了让四个百分数同分母。')
           if MIX else
           '（本次未能从同仓的 cboe / ndaq / miax 序列复算具体比例 —— '
           '那几个文件缺一个，这句就退回定性说法，本页不因为别人的文件不在而停机。）')
        + f'⇒ 读 NYSE 的份额时请记住：分母是<b>整个美国市场</b>，'
        f'不是「本页出现的这几家」；份额掉一个百分点，可能是别家抢走的，'
        f'也可能是整块池子往场外挪了。')

    # ─────────────────────────────────────────────────────────────────────────
    # ⑫ 从核对表里拿掉的列
    # ─────────────────────────────────────────────────────────────────────────
    notes.append(
        f'<b>末尾核对表只放官方原始单位、且装得下的那几列，其余列<u>逐条点名在这里</u> ——'
        f'它们仍然在 <code>series/ice.csv</code> 里，一列都没有丢。</b>'
        f'（核对表是拿来<b>逐格与官方原表对</b>的，所以它只收官方原样发布的行；'
        f'本页现算出来的派生值 —— 隐含收入、量价两腿、各种占比 —— 一个都不进那张表，'
        f'它们的数在各自图注里。）读数为 {mlab(DROP["last"])}：'
        + (f'<b>（a）图上画着、只是没进核对表</b>（想核数请看那张图的水平值）：'
           + '；'.join(DROP['chart']) + '。' if DROP['chart'] else '')
        + (f'<b>（b）本页一处都没画、只有 CSV 里有</b>：'
           + '；'.join(DROP['off']) + '。' if DROP['off'] else '')
        + f'⚠️ 这份名单是构建期拿 CSV 表头与核对表实际列名<b>做差集</b>算出来的，'
        f'不是人肉维护的清单 —— 官方哪天新发一列，它会自己出现在这里，'
        f'而不是安静地从页面上消失。')

    # ─────────────────────────────────────────────────────────────────────────
    # ⑬ 隐含收入的对账状态：三条对得上、四条是推导值（**不许互相背书**）
    # ─────────────────────────────────────────────────────────────────────────
    # 顺序按对账表**出现的先后**，不排序 —— 排序会按中文笔画随机打乱，
    # 读者对不上上面那六行的顺序。
    _ok_legs = list(dict.fromkeys(r['leg']['zh'] for r in recon_rows))
    _no_legs = [lg['zh'] for lg in rev_legs if lg['zh'] not in _ok_legs]
    notes.append(
        f'<b>⚠️ 隐含收入六条腿的对账状态<u>不一样</u>，必须分开读 —— '
        f'对得上的那几条<u>不能</u>给对不上的那几条背书。</b>'
        f'（a）<b>{"、".join(_ok_legs)}</b>：与 ICE 另一份财报专用文件'
        f'（{recon_src}，发布于 {recon_pub}）披露的分部收入逐点对过，'
        f'{len(recon_rows)} 项全部落在 ±{_ceil_to__notes(abs(REV["qend_worst"]) * 100, 2):.2f}% 内，'
        f'残差来自 RPC 只保留 2 位小数。'
        f'官方那六个数是<b>外部常量</b>（本仓 CSV 里没有金额列），'
        f'所以它们连同出处与发布日一起写死在生成脚本里，并配两道构建期闸门：'
        f'本页推导值与它们的相对差超阈值就停机、常量表与图上画的季度对不上也停机。'
        f'（b）<b>{"、".join(_no_legs)}</b>：<b>纯推导值，没有任何官方数字可对。</b>'
        f'ICE 的分部收入披露只到（a）那个粒度，这 {len(_no_legs)} 条是本页按同一套公式'
        f'往下拆的 —— 公式相同<b>不等于</b>拆出来的数被验证过。'
        f'⚠️ 尤其别把（a）里的「金融合计」当成对（b）里那两条金融腿的背书：'
        f'对上的是<b>用官方聚合费率列算出来的那一条</b>，'
        f'把它拆成利率与股指/FX 两条走的是<b>另外两条费率列</b>，'
        f'两条拆出来的数官方一个都没披露过。'
        f'⚠️ 拆得越细，RPC 那 2 位小数的相对误差越大：'
        f'期权那条腿的费率量程只有 0.04–0.18，低端一格 = 25%。'
        f'（c）<b>加总只是近似，不是恒等式</b> —— 现算（全样本 '
        f'{qlab__notes(REV["q_from"])} – {qlab__notes(REV["q_to"])}）：'
        + '；'.join(
            f'（{"+".join(c["zh"] for c in kids)}）vs 官方的{agg["zh"]}：'
            f'中位差 {g["med"]:.3f}%、最大 {g["max"]:.3f}%，'
            f'{g["n"]} 个季度里超 1% 的 {g["gt1"]} 个、超 2% 的 {g["gt2"]} 个'
            for agg, kids, g in AGG)
        + f'。残差同样来自 RPC 的 2 位小数（分子分母各自取整），<b>不是口径错配</b>。'
        f'（d）<b>量价分解那张桥只覆盖四条衍生品腿</b>，不是六条：'
        f'量的单位打架 —— 四条衍生品腿是<b>千张</b>、现货腿是<b>百万股</b>、'
        f'期权腿虽然也是千张但费率取整太粗，凑不出一个可比的 Q。'
        f'现算 {qlab__notes(q_last)}：六腿合计 ${tot_rev:,.1f}mn，桥覆盖的四腿 ${br_rev:,.1f}mn = '
        f'<b>{br_rev / tot_rev * 100:.1f}%</b>，其中能源占四腿的 {energy_rev / br_rev * 100:.1f}%、'
        f'占六腿合计的 {energy_rev / tot_rev * 100:.1f}%。'
        f'（e）<b>本页做不到的还有一层</b>：CDS 三列、能源六个子项、农金两个子项、'
        f'STIR / 中长期利率 / 股指 / FX 各自单列 —— 官方只在<b>聚合层</b>给费率，'
        f'再往下没有费率列，收入结构最深就到这四条腿加期权、现货两条独立腿。'
        f'总收入线也只能由「大宗商品收入 + 金融收入」搭出来，'
        f'<b>不能</b>拿「衍生品总 ADV」去造 —— 它没有对应的总费率列，'
        f'而且它本身就不等于大宗与金融之和（见上文）。')

    _assert_no_exhibit(notes)
    return notes

#: 「Exhibit N」的判据与 tools/check_yoy_caliber.py:1659 同一条正则 —— 两边认得一样，
#: 才能保证本页在那道检查眼里也确实是「一个图号都没点」。
_EX_RE = re.compile(r'(?:Exhibit|Ex\.?)\s*\d+', re.I)

def _assert_no_exhibit(notes):
    """页尾一个字面的图号都不许有 —— 写出前停机，不是写出后 grep。"""
    bad = [(i + 1, m.group(0)) for i, t in enumerate(notes)
           for m in _EX_RE.finditer(str(t))]
    bad += [(i + 1, 'Exhibit') for i, t in enumerate(notes) if 'Exhibit' in str(t)]
    if bad:
        raise SystemExit(
            f'页尾 notes 里出现了字面的图号 {bad} —— 图号会随分组增删整体位移，'
            f'按<b>标题</b>点名（build/specs/enx.py:455、build/specs/sgx.py:841-848）。')

# ══════════════════════════════════════════════════════════════════════════════
# 3. 自测（合并进 build/ice.py 时整块删除）
#    下面的桩全部按冻结契约搭：真实 CSV、真实 SG / YOY 判据、真实图序。
# ══════════════════════════════════════════════════════════════════════════════
def _stub_page(df):
    """搭出本段需要的、由别的段提供的那些名字。全部按冻结的图序与公式。"""
    import sys
    sys.path.insert(0, os.path.join(ROOT, 'build'))
    import yoy as YOY

    W0 = pd.Period(WIN_FROM, freq='M')
    W = df.index[df.index >= W0]
    Q_FROM = W0.asfreq('Q')

    # ── COL：与 build/specs/ice.py 的 unit 串**逐字一致**（unit 是承重的）──────
    def _c(col, zh, unit, fmt, **kw):
        d = {'col': col, 'zh': zh, 'unit': unit, 'fmt': fmt}
        d.update(kw)
        return d
    COL = {}
    for col, zh in [('adv_futures_options_kcontracts', '衍生品总 ADV'),
                    ('adv_commodities_kcontracts', '大宗商品合计'),
                    ('adv_financials_kcontracts', '金融合计（不含单股）'),
                    ('adv_energy_kcontracts', '能源合计'),
                    ('adv_ag_metals_kcontracts', '农产品与金属合计'),
                    ('adv_brent_kcontracts', 'Brent 原油'),
                    ('adv_nyse_equity_options_kcontracts', 'NYSE 两所合计'),
                    ('adv_us_equity_options_industry_kcontracts', '全美股票/ETF 期权行业总量')]:
        COL[col] = _c(col, zh, 'k contracts/day', 'f0c')
    for col, zh in [('adv_nyse_us_cash_handled_mnsh', 'NYSE handled ADV'),
                    ('adv_tapeA_consolidated_mnsh', 'Tape A 全市场')]:
        COL[col] = _c(col, zh, 'mn shares/day', 'f0c')
    for col, zh in [('oi_energy_kcontracts', '能源'), ('oi_rates_kcontracts', '利率')]:
        COL[col] = _c(col, zh, 'k contracts', 'f0c', stock=True)
    for col, zh in [('rpc_energy_usd', '能源'), ('rpc_ag_metals_usd', '农产品与金属'),
                    ('rpc_rates_usd', '利率'), ('rpc_other_financials_usd', '股指与 FX'),
                    ('rpc_nyse_equity_options_usd', 'NYSE 期权 RPC')]:
        COL[col] = _c(col, zh, 'USD/contract', 'f2')
    COL['rpc_nyse_us_cash_usd_per100sh'] = _c(
        'rpc_nyse_us_cash_usd_per100sh', '现货 RPC（每 100 股）', 'USD/100 shares', 'f3')
    for col, zh in [('share_nyse_tapeA_matched', 'Tape A 份额'),
                    ('share_nyse_us_cash_matched', 'NYSE 全美 matched 份额'),
                    ('share_nyse_equity_options', 'NYSE 份额（官方直接给）')]:
        COL[col] = _c(col, zh, '%', 'pct1', scale=100)
    COL['cds_total_notional_usdbn'] = _c(
        'cds_total_notional_usdbn', 'CDS 合计', 'USD bn/month', 'f0c')

    # ── 冻结的图序（17 张图 + Ex1 汇总表 + Ex19 核对表）────────────────────────
    EX_TITLE = {
        2: 'ICE 衍生品总 ADV：一门横跨两侧的生意', 3: '合约构成：大宗商品与金融各挑多少担子',
        4: '一张合约不是一块钱：四条腿的每张收入', 5: '隐含交易收入：把量翻译成钱',
        6: '对账：本页推导 vs ICE 披露', 7: '收入结构：六条腿各占多少',
        8: '量与费率各贡献了多少', 9: '近 8 个完整季的分腿收入',
        10: '能源 ADV 按产品：特许经营的内部构造', 11: '十二个官方单列产品的单月同比',
        12: '月末未平仓：四条叶子', 13: '美股期权：本所量 vs 全行业分母',
        14: '两本账的单位经济（指数化）', 15: 'NYSE 现货 handled ADV：还剩多少市场',
        16: 'NYSE matched 占全美合并量', 17: '按 Tape 看份额', 18: 'CDS 清算名义额',
        19: '核对表：官方原始单位',
    }
    Q_LAST_FULL = pd.Period('2026Q2', freq='Q')     # CSV 到 2026-08，2026Q3 不完整
    QW = pd.period_range(Q_FROM, Q_LAST_FULL, freq='Q')
    EX_SPAN = {}
    for n in EX_TITLE:
        if n in (5, 6, 7, 8, 9):
            EX_SPAN[n] = {'title': EX_TITLE[n], 'axis': 'quarter',
                          'from': QW[0], 'to': QW[-1]}
        elif n == 11:
            EX_SPAN[n] = {'title': EX_TITLE[n], 'axis': 'matrix',
                          'from': df.index[-24], 'to': df.index[-1]}
        elif n == 19:
            EX_SPAN[n] = {'title': EX_TITLE[n], 'axis': 'table',
                          'from': df.index[-13], 'to': df.index[-1]}
        else:
            EX_SPAN[n] = {'title': EX_TITLE[n], 'axis': 'month',
                          'from': W[0], 'to': W[-1], 'stock': (n == 12)}

    # ── COST_LOG：{图号: [ {'label','d'}, … ]}（值是 list，抄 build/cme.py:466）──
    COST_LOG = {}

    def _log(n, col, label):
        d = YOY.caliber_diff(df[col], YOY.FLOW, win=W)
        COST_LOG.setdefault(n, []).append({'label': label, 'd': d})
    _log(2, 'adv_futures_options_kcontracts', '')
    _log(3, 'adv_commodities_kcontracts', '大宗商品')
    _log(3, 'adv_financials_kcontracts', '金融')
    _log(10, 'adv_energy_kcontracts', '能源合计')
    _log(13, 'adv_nyse_equity_options_kcontracts', 'NYSE 两所合计')
    _log(15, 'adv_nyse_us_cash_handled_mnsh', '')

    # ── 收入六条腿（冻结的配对；金融四条腿全部用 trading_days_rates）───────────
    REV_LEGS = [
        {'key': 'energy', 'zh': '能源', 'adv': ['adv_energy_kcontracts'],
         'td': 'trading_days_commod', 'rpc': 'rpc_energy_usd', 'f': 1000.0},
        {'key': 'ag', 'zh': '农产品与金属', 'adv': ['adv_ag_metals_kcontracts'],
         'td': 'trading_days_commod', 'rpc': 'rpc_ag_metals_usd', 'f': 1000.0},
        {'key': 'rates', 'zh': '利率', 'adv': ['adv_stir_kcontracts', 'adv_mltir_kcontracts'],
         'td': 'trading_days_rates', 'rpc': 'rpc_rates_usd', 'f': 1000.0},
        {'key': 'othfin', 'zh': '其他金融（股指与 FX）',
         'adv': ['adv_equity_index_kcontracts', 'adv_fx_credit_kcontracts'],
         'td': 'trading_days_rates', 'rpc': 'rpc_other_financials_usd', 'f': 1000.0},
        {'key': 'opt', 'zh': 'NYSE 美股期权', 'adv': ['adv_nyse_equity_options_kcontracts'],
         'td': 'trading_days_us_equities', 'rpc': 'rpc_nyse_equity_options_usd', 'f': 1000.0},
        # ⚠ 现货是 ÷100 不是 ÷1000：mn shares × day = mn shares ×1e6 → ÷100 得百股，
        #   × USD/100shares = USD → ÷1e6 得 $mn，净因子 1/100。用 ÷1000 会低估 10 倍。
        {'key': 'cash', 'zh': 'NYSE 美股现货', 'adv': ['adv_nyse_us_cash_handled_mnsh'],
         'td': 'trading_days_us_equities', 'rpc': 'rpc_nyse_us_cash_usd_per100sh', 'f': 100.0},
    ]
    # 对账那三行用的是官方分部收入的粒度：金融是**聚合列**（Financial futures & options
    # 一行），不是 rates + othfin 两条腿相加 —— 这样才与 docs/verify/ice.md:519-526 同源。
    RECON_LEG_FIN = {'key': 'fin_agg', 'zh': '金融合计', 'adv': ['adv_financials_kcontracts'],
                     'td': 'trading_days_rates', 'rpc': 'rpc_financials_usd', 'f': 1000.0}
    AGG_LEG_COMMOD = {'key': 'commod_agg', 'zh': '大宗商品合计',
                      'adv': ['adv_commodities_kcontracts'], 'td': 'trading_days_commod',
                      'rpc': 'rpc_commodities_usd', 'f': 1000.0}
    AGG_LEGS = [(AGG_LEG_COMMOD, REV_LEGS[:2]), (RECON_LEG_FIN, REV_LEGS[2:4])]

    def qtr_rev(d, leg, form):
        q = d.index.asfreq('Q')
        contracts = (d[leg['adv']].sum(axis=1) * d[leg['td']])
        if form == 'qend':
            return contracts.groupby(q).sum() * d.groupby(q)[leg['rpc']].last() / leg['f']
        if form == 'monthly':
            return (contracts * d[leg['rpc']] / leg['f']).groupby(q).sum()
        raise ValueError(form)

    RECON_ROWS = [
        {'leg': REV_LEGS[0], 'q': pd.Period('2025Q2', 'Q'), 'official': 595.0},
        {'leg': REV_LEGS[0], 'q': pd.Period('2026Q2', 'Q'), 'official': 518.0},
        {'leg': REV_LEGS[1], 'q': pd.Period('2025Q2', 'Q'), 'official': 65.0},
        {'leg': REV_LEGS[1], 'q': pd.Period('2026Q2', 'Q'), 'official': 87.0},
        {'leg': RECON_LEG_FIN, 'q': pd.Period('2025Q2', 'Q'), 'official': 158.0},
        {'leg': RECON_LEG_FIN, 'q': pd.Period('2026Q2', 'Q'), 'official': 192.0},
    ]

    # 核对表列（官方原始单位、装得下的那几列）—— 桩，正式实现由核对表段提供。
    TBL_COLS = ['adv_futures_options_kcontracts', 'adv_commodities_kcontracts',
                'adv_financials_kcontracts', 'adv_energy_kcontracts',
                'adv_ag_metals_kcontracts', 'adv_nyse_equity_options_kcontracts',
                'adv_nyse_us_cash_handled_mnsh', 'share_nyse_us_cash_matched',
                'rpc_energy_usd', 'trading_days_commod', 'trading_days_rates',
                'trading_days_us_equities']
    PAGE_COLS = set(COL) | {
        'adv_stir_kcontracts', 'adv_mltir_kcontracts', 'adv_equity_index_kcontracts',
        'adv_fx_credit_kcontracts', 'adv_gasoil_kcontracts', 'adv_otheroil_kcontracts',
        'adv_natgas_kcontracts', 'adv_power_kcontracts', 'adv_environmentals_kcontracts',
        'adv_sugar_kcontracts', 'adv_otherags_metals_kcontracts',
        'oi_ag_metals_kcontracts', 'oi_other_financials_kcontracts',
        'adv_tapeB_consolidated_mnsh', 'adv_tapeC_consolidated_mnsh',
        'share_nyse_tapeB_matched', 'share_nyse_tapeC_matched',
        'cds_client_notional_usdbn', 'cds_nonclient_notional_usdbn',
    }

    return dict(col_meta=COL, cost_log=COST_LOG, ex_title=EX_TITLE, ex_span=EX_SPAN,
                tbl_cols=TBL_COLS, page_cols=PAGE_COLS, qtr_rev=qtr_rev,
                rev_legs=REV_LEGS, bridge_legs=REV_LEGS[:4], recon_rows=RECON_ROWS,
                recon_src='ICE Key-Metrics-Q2-2026.xlsx', recon_pub='2026-07-30',
                q_full=QW, series_dir=os.path.join(ROOT, 'series'))

# ==========================================================================
# 【brief】
# ==========================================================================

# -*- coding: utf-8 -*-
"""build/ice.py 的一段：页顶 ~300 字数据总结（payload 的 `brief`）。

⚠️ 这是**待合并的片段**。正式并进 build/ice.py 时：
    · 删掉本文件底部的 `if __name__ == '__main__':` 自测块；
    · 删掉本文件顶部那段「片段自足化」的 import 与 COL 子集，改吃 ice.py 自己的
      冻结导入与完整的 COL 表（本片段用到的 COL 键名一个字都没改，见 COL_BRIEF）。

═══ 为什么 ICE 到今天还没有 brief ═══
不是谁忘了写，是**通用引擎根本不产这个键** —— build/single.py 组装 payload 的那一段
（:4069-4088）里没有 `brief`，而 build/verify_pages.py 只对缺 glossary 告警、不对缺
brief 告警。所以 ice / ndaq 这两张声明式页面缺 brief 是**静默**的：页面能发、护栏全绿、
只有人眼并排读 cme / cboe / tsm 三页时才看得出少了一段。手写化之后这个洞就该补上，
补法与 cme / cboe 相同 —— 规则库在 build/brief.py，句子在这里拼。

═══ 分寸：以 build/ibkr.py 的 compose_brief() 为准（brief.py::render 的 docstring）═══
四到五句、一句一个意思。本页的五层是：

    s1 规模   总 ADV 的读数、它在断点后样本里的名次（**分母写进句子**）、
              以及四条腿里哪一条在推同比
    s2 基数   环比与单月同比反号时，上月排第几 + 本月这个历月的季节位置
    s3 结构   能源占**合约张数**的比例 × 两条腿的每张费率差 —— 全页存在的理由
    s4 分母   NYSE 的 matched 份额对上**全市场自己的**增速（全仓独一份的对照）
    s5 QTD    本季已过几个月、两条头条的 QTD 对齐去年同期（季度块只画完整季，
              所以本季在图上还看不到）

**每一个限定词都由算出来的值挑分支**：名次、「只有／有／多达」、「高基数／季节」、
「份额在丢还是大盘在缩」、「几个市场在涨」全部当场算。写死的措辞配算出来的数字是本仓
brief 最常复发的 bug（brief.py::quant 的 docstring 记着 CME 的历史重放：199 个月里
108 个月会印出「六个里只有六个」这种自相矛盾的句子）。

═══ ICE 独有，别家不能照抄 ═══
  · **R3（日历修正）必须关掉，理由有两条，缺一条都不足以关。**
    ① 本页 `adv_*` 全部是官方直接发的 **ADV（当月日均）**，公司已经除过交易日，
       再除一次会造出一个根本不存在的修正 —— 这一条与 cme / cboe 相同。
    ② 但本页**确实有一列当月合计**：`cds_*_notional_usdbn` 是 ICE Clear Credit
       的当月清算名义额（原表标题里没有 daily 字样，见 build/specs/ice.py:747-752）。
       它是全页唯一一列 R3 在原理上适用的序列，而 **ICE 不发布 CDS 的清算日历**，
       CSV 里那三条 trading_days_* 是期货/现货的交易日历，不是清算日历。
       ⇒ 修正**算不出来**，不是「用不着」。这一条必须写对：写成「本页没有当月合计列」
       就是假话，下一个读 CDS 那张图的人会当场发现。
  · **三套交易日、且总 ADV 横跨两侧**（trading_days_commod / _rates / _us_equities）。
    所以本段任何地方都不把 ADV 乘回当月合计，QTD 那句也只能按月简单平均 —— 加权要
    先选一套日历，而总 ADV 没有哪一套能代表（build/specs/ice.py:995-1000）。
  · **rpc_* 是费率、且是滚动三月均**，不是成交价、也不是单月数。s3 用到它，所以
    「滚动三月均」这个限定词是**承重的**，字数超了也不许丢（见 assemble 的 drop 清单）。
    与 Cboe 不同的是 ICE 的 RPC **不滞后**（specs/ice.py:756-758：全表同一个 xlsx、
    同一个发布日，slow_cols 为空），所以这里没有 cboe 那套「滞后一期」的分支。
  · **唯一口径断点 2013-11**（NYSE Euronext 收购完成，此前 34 个月的 NYSE 各列是
    追溯并入的形式数，specs/ice.py:762-768）。s4 整句活在 NYSE 列上 ⇒ 名次必须从 i0
    起算。s1/s2/s3 的衍生品列其实**不受这个断点影响**，但本段仍然统一用 i0 起算，
    理由是编辑性的：一段话里出现两个分母（188 与 154）而读者只看得到数字，跨句对读
    必然读错；统一到更保守的那个，并且**把分母写进句子**，读者永远挂得对。
    代价是丢掉 2011-01~2013-10 那 34 个月的衍生品历史 —— 这是有意的取舍，不是漏。
  · **没有反向指标**（ADV / 份额 / RPC 都是越高越好）⇒ `peak_scan` 一律不传 inverse；
    也没有公司 Notes 的一次性重述 ⇒ 无「（还原口径）」标注。
"""

# ── 片段自足化（合并进 build/ice.py 时整块删掉，换成 ice.py 顶部那段冻结导入）──
ROOT__brief = '/Users/hzhan/Documents/monthly-op-dashboards/.claude/worktrees/cboe-page-redesign-dc42f8'

sys.path.insert(0, os.path.join(ROOT__brief, 'build'))

# ── COL 的子集：本段用到的三列。合并时删掉，直接吃 ice.py 的完整 COL 表。
#   `unit` 字符串是**承重**的 —— SG.col_is_ratio / col_is_money_ratio 靠它把
#   ycal.classify() 的假阳性挡回去，改一个字判定就翻，而且不报错。
COL_BRIEF = {
    'rpc_energy_usd': {'col': 'rpc_energy_usd', 'zh': '能源',
                       'unit': 'USD/contract', 'fmt': 'f2'},
    'share_nyse_us_cash_matched': {'col': 'share_nyse_us_cash_matched', 'zh': '美股现货份额',
                                   'unit': '%', 'fmt': 'pct1', 'scale': 100},
    'adv_futures_options_kcontracts': {'col': 'adv_futures_options_kcontracts',
                                       'zh': '衍生品总 ADV',
                                       'unit': 'k contracts/day', 'fmt': 'f0c'},
}

#: 排名区间的左端 —— 唯一口径断点。见 docstring「ICE 独有」第 4 条。
I0_MONTH = '2013-11'

#: brief 去标签字数的自压上界（B.render 的硬护栏是 230-380）。贴着 380 发布等于把
#: 「下个月名次多一位数」当成停更风险 —— 那会让一个数据齐全的月份因为一句解读整页
#: SystemExit。
#: **为什么不是 cboe.py:159 的 330**：本页每一句都比 cboe 多背一个口径限定词
#: （断点后的分母 / RPC 滚动三月均 / 三带合并量是推导值 / 按月简单平均），
#: 2016-01 起 128 个月的回放实测：四句核心版（装饰全省）277-303 字，四句带装饰
#: 324-375 字（中位 356）。压到 330 会让**多数月份连三处名次带峰值扫描一起被削平**，
#: 剩下一段只有读数没有位置的话。340 是「多数月份留得住至少一处装饰」与
#: 「离硬护栏还有 40 字」两头之间的落点。
#: ⚠️ 顺带一个实测结论，写在这里免得下一个人再试一遍：**五句齐全的版本本身就撞破
#:   硬护栏** —— 全量版 324-445 字（中位 421），而 B.render 的上界是 380。
#:   所以 s5（QTD）在本页是**名副其实的可选句**：降级阶梯只在核心版特别短的月份
#:   （回放 128 个月里 2 个月）才装得下它。这不是压出来的，是它本来就放不进这个体例。
BRIEF_HI = 340

#: R1 峰值扫描扫哪几条线。**只放官方单列披露的叶子**，一条聚合列都不放 ——
#: adv_energy / adv_ag_metals / adv_commodities / adv_financials /
#: adv_futures_options 都是下面这些的（近似）合计，放进来等于把同一件事数两遍，
#: 「十二条里只有一条停在峰值」这句当场不成立。
#: `adv_single_stock_kcontracts` 也不放：官方已把它剔出 TOTAL FINANCIALS / ADV /
#: RPC / OI（specs/ice.py 的口径注），它不属于本页说的「十二个官方单列产品」。
#: 这十二条正是热力矩阵那张图扫的同一批列 —— 两处同源，不各写一份。
BRIEF_LINES = [
    ('布伦特', 'adv_brent_kcontracts'),
    ('柴油', 'adv_gasoil_kcontracts'),
    ('其他原油', 'adv_otheroil_kcontracts'),
    ('天然气', 'adv_natgas_kcontracts'),
    ('电力', 'adv_power_kcontracts'),
    ('环境权益', 'adv_environmentals_kcontracts'),
    ('食糖', 'adv_sugar_kcontracts'),
    ('其他农金', 'adv_otherags_metals_kcontracts'),
    ('STIR', 'adv_stir_kcontracts'),
    ('中长期利率', 'adv_mltir_kcontracts'),
    ('股指', 'adv_equity_index_kcontracts'),
    ('外汇与 USDX', 'adv_fx_credit_kcontracts'),
]

#: s1 的「哪条 franchise 在推」用的是**四条腿**，与隐含收入 / 量价分解那一块同一套
#: 划分（能源 / 农金 / 利率 = STIR+MLTIR / 股指与外汇 = 股指+FX）。
#: 这里用聚合列不与上面的 BRIEF_LINES 冲突：那边是峰值扫描（同一张合约不能数两遍），
#: 这边是把同比拆到腿上（本来就要用腿）。两处口径不同，故分两张表，别合并。
#: ⚠️ 官方行名 "COMMODITIES & OTHER FINANCIALS" 是陷阱，与这里的分腿无关；
#:   交易日配对（金融四条腿全部用 trading_days_rates）也与本段无关 —— 本段一次都
#:   没有把 ADV 乘回当月合计。
BRIEF_LEGS = [
    ('能源', ['adv_energy_kcontracts']),
    ('农金', ['adv_ag_metals_kcontracts']),
    ('利率', ['adv_stir_kcontracts', 'adv_mltir_kcontracts']),
    ('股指与外汇', ['adv_equity_index_kcontracts', 'adv_fx_credit_kcontracts']),
]

#: 四条腿各自的费率列（s3 的费率价差在这四条里现比）。RPC 只到聚合层，
#: 六个能源子项与两个农金子项都没有自己的费率列 —— 所以「每张多少钱」这件事
#: 最深只能说到腿，说不到产品。
BRIEF_LEG_RPC = [
    ('能源', 'rpc_energy_usd'),
    ('农金', 'rpc_ag_metals_usd'),
    ('利率', 'rpc_rates_usd'),
    ('其他金融', 'rpc_other_financials_usd'),
]

#: s4 的四个市场：NYSE 在**别人的分母**里占多少。每一项是
#: (名, NYSE 自己的量, 该市场的合并量/行业量, 官方披露的份额列)。
#: ⚠️ 三条 tape 份额的分母是**该带自己**的合并量，不是三带之和 —— 所以这里逐带列，
#:   不能把三条 tape 折成一个数；三带之和那个口径另有 share_nyse_us_cash_matched，
#:   s4 的主句用的就是它。
#: ⚠️ 期权那一行的分母是全美期权行业量（OCC 口径），与三条 tape 不同源，
#:   所以四项只数「份额同比上行的有几个」，不做任何加总。
BRIEF_VENUES = [
    ('美股期权', 'adv_nyse_equity_options_kcontracts',
     'adv_us_equity_options_industry_kcontracts', 'share_nyse_equity_options'),
    ('Tape A', 'adv_nyse_tapeA_matched_mnsh',
     'adv_tapeA_consolidated_mnsh', 'share_nyse_tapeA_matched'),
    ('Tape B', 'adv_nyse_tapeB_matched_mnsh',
     'adv_tapeB_consolidated_mnsh', 'share_nyse_tapeB_matched'),
    ('Tape C', 'adv_nyse_tapeC_matched_mnsh',
     'adv_tapeC_consolidated_mnsh', 'share_nyse_tapeC_matched'),
]

#: 三个**承重限定词**。它们不是修辞，是口径的一部分：删掉任何一个，剩下的句子
#: 就是另一句话（而且是假话）。字数超了走 assemble(drop=…) 的阶梯降级时，
#: 这三个字串永远不在可丢清单里 —— 下面 compose_brief 末尾有一道断言逐条查。
BRIEF_MUST_KEEP = ('滚动三月均',      # RPC 不是单月数（s3）
                   '推导值',          # 三带合并量是本页加出来的（s4）
                   '按月简单平均')    # QTD 没有可代表总量的交易日历（s5）

# ──────────────────────────── 事实件（只算数，不拼字）────────────────────────────
def _seasonal_index(a, months, i, i0, min_obs=3):
    """本月这个**历月**在断点后样本里的季节位置（全样本月均 = 100）。

    为什么 brief 需要它：ICE 的头条带着一个 −16.5% 的环比，而全页没有任何一处解释
    它有多少是季节。总 F&O 的历月均值指数实测 3 月 122、8 月 86，差 36 个点 ——
    这个量级的季节性不交代，读者只能把每年夏天那一跌读成需求塌方。

    ⚠️ 指数是**当场算**的，不写死 122/86：窗口每月往右滚一格，两个数都会变。
    ⚠️ 观测不足 min_obs 个的历月不出这句 —— 拿一两年的均值当「季节」是编的。
       (回放到 2016-01 时断点后只有 27 个月，1 月恰好 3 个观测，卡在这道闸上。)
    """
    a = np.asarray(a, float)[i0:i + 1]
    mm = np.asarray([int(k[5:7]) for k in months[i0:i + 1]])
    base = float(np.nanmean(a))
    if not np.isfinite(base) or base == 0:
        return None
    cur_m = mm[-1]
    idx = {}
    for m_ in range(1, 13):
        v = a[mm == m_]
        if len(v) >= min_obs and np.isfinite(v).any():
            idx[m_] = float(np.nanmean(v) / base * 100)
    if cur_m not in idx or len(idx) < 6:
        return None
    hi_m = max(idx, key=idx.get)
    return {'cur_m': cur_m, 'cur': idx[cur_m], 'hi_m': hi_m, 'hi': idx[hi_m], 'n': len(idx)}

def _leg_contrib(D, tot, i):
    """四条腿对**总 ADV 单月同比**的贡献（pp）。(腿_i − 腿_{i−12}) ÷ 总_{i−12}。

    只报**贡献最大的那一条**，不列四项 —— 分寸线在 brief.py::render 的 docstring 里
    写死：「三项以上的分解并逐项给金额贡献」是超线的写法，读者要自己做一遍加法才跟得上。
    四条腿之和也**不等于**总同比（分项之和 ≠ 合计，官方从未说明成因，
    ⚠️ 而「两套交易日各归一各的」那个解释已被 fetch/ice.py:123-131 证伪：
    偏差最大的三个月里两列交易日恰恰相等）—— 又一个不许把四项摆出来的理由：
    摆出来读者就会去加，加不平就会以为页面算错了。
    """
    if i < 12:
        return None
    base = float(tot[i - 12])
    if not np.isfinite(base) or base == 0:
        return None
    out = []
    for zh, cols in BRIEF_LEGS:
        a = np.zeros(len(D), float)
        for c in cols:
            a = a + np.asarray(D[c].values, float)
        if B.need(a[i], a[i - 12]):
            out.append((zh, float((a[i] - a[i - 12]) / base * 100)))
    if not out:
        return None
    zh, pp_ = max(out, key=lambda x: abs(x[1]))
    return {'zh': zh, 'pp': pp_, 'n': len(out)}

def _rpc_gap(D, i):
    """本月四条腿里最贵与最便宜的每张费率，以及能源相对最便宜那条的倍数。

    ⚠️ 三件事必须由数据说，一件都不能写死：
      ① 谁最贵谁最便宜（当前是农金 2.19 / 利率 0.50，但 rpc_other_financials
         从 0.53 涨到 1.75 过，排序不是常数）；
      ② 能源是不是最便宜的那一条（是的话「N 倍」这句整个不成立，得换分支）；
      ③ 倍数本身（实测断点后中位 3.4×、区间 2.0×–4.3×）。
    返回的 `ratio_med` 是断点后中位数，用来告诉读者本月这个倍数是不是常态。
    """
    vals = [(zh, float(D[c].values[i])) for zh, c in BRIEF_LEG_RPC
            if B.need(D[c].values[i])]
    if len(vals) < 2:
        return None
    lo_zh, lo = min(vals, key=lambda x: x[1])
    hi_zh, hi = max(vals, key=lambda x: x[1])
    if lo == 0:
        return None
    en = dict(vals).get('能源')
    return {'lo_zh': lo_zh, 'lo': lo, 'hi_zh': hi_zh, 'hi': hi,
            'en': en, 'ratio': (en / lo) if en else None}

def _venue_mix__brief(D, i, i0):
    """NYSE 在**四个别人的分母**里的份额：现值、单月同比的 pp 差、以及市场自己的增速。

    「四个市场」= 全美期权行业 + Tape A/B/C。这是 ICE 这张表独有的东西：
    它同时给出 NYSE 自己的量与**市场合并量**，所以「份额在丢」与「大盘在缩」可以
    真的分开 —— 全仓其余 11 家的页面都只有自己的量，分不开。

    ⚠️ 份额的差一律走 SG.ratio_diff_txt（→ pp/bp），**不许自己写判据**：
      同一条序列在两页被判定相反，正是 build/pctile.py 模块头记着的那条教训。
      份额列在 CSV 里是**小数**（0.189），COL 里挂 scale=100，所以这里先 ×100
      再作差 —— ratio_diff_txt 的入参单位是 pp（single.py:642-653 的 ppbp）。
    ⚠️ 四项**只数个数，不做加总**：期权那一行的分母是 OCC 口径的行业量，
      与三条 tape 的合并量不同源，加起来没有意义。
    """
    out = []
    for zh, c_ny, c_mkt, c_sh in BRIEF_VENUES:
        sh = np.asarray(D[c_sh].values, float) * 100.0
        ny = np.asarray(D[c_ny].values, float)
        mk = np.asarray(D[c_mkt].values, float)
        if i < 12 or not B.need(sh[i], sh[i - 12], ny[i], ny[i - 12], mk[i], mk[i - 12]):
            continue
        out.append({
            'zh': zh, 'sh': float(sh[i]), 'd_pp': float(sh[i] - sh[i - 12]),
            'ny_yy': float(ny[i] / ny[i - 12] - 1) if ny[i - 12] else None,
            'mkt_yy': float(mk[i] / mk[i - 12] - 1) if mk[i - 12] else None,
            'rank_lo': B.rank_of(-sh[i0:], i - i0),
        })
    return out

def _qtd(D, cols, i):
    """本季至今 vs 去年同季**的同样几个月**（各月 ADV 按月简单平均）。

    ⚠️ 为什么是简单平均而不是按交易日加权：本页有三套交易日历，而总 ADV 横跨
      商品与现货两侧，**没有哪一套能代表它**（specs/ice.py:995-1000）。
      要加权就得先挑一套日历，挑哪一套都是编的。所以这里明说「按月简单平均」，
      这个限定词进 BRIEF_MUST_KEEP，字数再紧也不许丢。
    ⚠️ 去年那一段必须**截到同样的月数**：拿 2 个月比去年 3 个月是本仓的老坑
      （CONTRACT 里「未满桶不可直读」那条），这里用 [:k] 截齐。
    """
    q = D.index.asfreq('Q')
    cur_q = q[i]
    sel = np.flatnonzero(np.asarray(q == cur_q))
    sel = sel[sel <= i]
    k = len(sel)
    prev = np.flatnonzero(np.asarray(q == cur_q - 4))[:k]
    if k == 0 or len(prev) < k:
        return None
    out = {'q': str(cur_q), 'k': k, 'full': k >= 3, 'legs': []}
    for zh, c in cols:
        a = np.asarray(D[c].values, float)
        x, y = np.nanmean(a[sel]), np.nanmean(a[prev])
        if np.isfinite(x) and np.isfinite(y) and y:
            out['legs'].append((zh, float(x / y - 1)))
    return out if out['legs'] else None

# ──────────────────────── 顶部 ~300 字数据总结（payload 的 brief）────────────────────────
def compose_brief(D):
    """ICE 页顶部的 ~300 字数据总结。规则库在 build/brief.py，句子在这里拼。

    入参 `D` 是已经按月排好序、索引为 PeriodIndex('M') 的整张表；截止月 = 最后一行。
    历史回放只要传 `D.iloc[:i+1]` 即可 —— 本函数内部**一次都不看 i 之后的数据**
    （名次、季节指数、峰值扫描全部在 [i0:i+1] 上算），所以回放不会穿越。

    ⚠️ 分母 `n`（断点后的月数）在 s1 里带「2013-11 断点后」全写一次，s2/s3/s4 只重复
      「{n} 个月里」这半句。理由：分母必须出现在**每一个报名次的句子**里（不然读者会
      拿 s1 的分母去挂 s4 的名次），但「2013-11 断点后」这五个字在一段话里印四遍是
      噪音，而且会把读者的注意力从读数移到口径史上。
    """
    months = [str(p) for p in D.index]
    i = len(months) - 1
    if I0_MONTH not in months:
        # 断点月不在表里 = 数据管道坏了（CSV 从 2011-01 起连续到今天）。
        # 这属于「失败要响」那一类：静默退回全样本排名会让分母悄悄从 154 变成 188。
        raise SystemExit(f'brief: series/ice.csv 里找不到口径断点月 {I0_MONTH}')
    i0 = months.index(I0_MONTH)
    n = i - i0 + 1                      # 断点后的月数 —— 报名次的每一句都要写出它
    if n < 13:
        raise SystemExit(f'brief: 断点后只有 {n} 个月，不足以算任何一句同比')

    tot = np.asarray(D['adv_futures_options_kcontracts'].values, float)
    en = np.asarray(D['adv_energy_kcontracts'].values, float)

    def m(k, ref):
        """月份标签。与参照月同年只写「8 月」，跨年才补年份（抄 cboe.py:531-538）。
        恒写年份的话一句话里会塞三个「2026 年」；恒不写，1 月的页面上「11 月」会被
        读成同一年往前退。"""
        return (f'{months[k][:4]} 年 {int(months[k][5:7])} 月'
                if months[k][:4] != months[ref][:4] else f'{int(months[k][5:7])} 月')

    def ordinal(rk, unit=''):
        """名次措辞。第 1 名写「最高／最低」——「第 1 高」不是中文。
        unit 为空时只写「第 N」：同一句里已经说清在比什么的时候，「高」字是多余的。"""
        return f'最{unit or "高"}' if rk == 1 else f'第 {rk} {unit}'.rstrip()

    def cnt(k):
        """计数 + 一个空格。B.cn 只把 1-10 写成中文，11 以上退回阿拉伯数字，
        而全页排版规矩是「数字与汉字之间留一个空格」—— 不补的话会印出「12条产品线」。"""
        s = B.cn(k)
        return f'{s} ' if s.isdigit() else s

    # ── s1 规模。三段：读数与名次（分母写进句子）／四条腿里谁在推同比／十二条产品线的
    #    峰值扫描。峰值扫描只扫叶子（BRIEF_LINES），聚合列一条不放。
    rk = B.rank_of(tot[i0:], i - i0)
    lc = _leg_contrib(D, tot, i)
    yy_tot = (float(tot[i] / tot[i - 12] - 1)
              if i >= 12 and B.need(tot[i], tot[i - 12]) and tot[i - 12] else None)
    # 「贡献最大的是 X」只有在总同比算得出时才有落点：没有同比就没有「这个同比」可归因。
    drive = (f'单月同比 {B.pct(yy_tot)}，{cnt(lc["n"])}条腿里贡献最大的是'
             f'{lc["zh"]}（{lc["pp"]:+.1f}pp）'
             if (lc and yy_tot is not None) else
             (f'单月同比 {B.pct(yy_tot)}' if yy_tot is not None else ''))
    # 前半区才印分位：「第 140（前 91%）」是真话但没信息。分位走 B.top_pct（向上取整）——
    # 四舍五入会把第 23/223 印成「前 10%」，那是假话。数字与汉字之间补一个空格。
    #   排第 1 时不印分位：「最高（前 4%）」里的括号是废话，第 1 名本来就是分位的顶。
    topn = ('（' + re.sub(r'(\d)', r' \1', B.top_pct(rk, n), count=1) + '）'
            if rk and rk > 1 and rk * 2 <= n else '')

    pk = B.peak_scan(months[i0:], [(z, np.asarray(D[c].values, float)[i0:])
                                   for z, c in BRIEF_LINES], i - i0)
    n_scan = len(pk['at_peak']) + len(pk['off_peak'])
    # 「只有一条」是定性词，必须跟着比例走（B.quant 按 k/n 挑「只有／有／多达」）：
    # 回放里出现过多条同时停在峰值的月份，那时写「只有」就是把普遍现象说成稀缺。
    # 名字直接嵌进量词里（「只有食糖停在峰值」），不另起一个括号 —— 括号里再报一遍
    # 条数是同一个数说两次，cboe.py:733 记着同一件事。
    if pk['at_peak']:
        # 名字最多列两条，其余折成「等」：回放到 2016 年有一次六条并列停在同一个峰值，
        # 全列出来这一句自己就要 30 个字，把后面四句挤出字数护栏（cboe.py:540-548 同因）。
        nm = '、'.join(pk['at_peak'][:2]) + ('等' if len(pk['at_peak']) > 2 else '')
        # ⚠️ B.quant 的 noun 不能传空串：它返回「词 + 中文数 + noun」，传空会印出
        #   「只有一布伦特」这种把量词和名字黏在一起的残句（第一版实测）。
        peak_txt = (f'{cnt(n_scan)}条产品线'
                    f'{B.quant(len(pk["at_peak"]), n_scan, "条")}停在自己的峰值（{nm}）')
    else:
        peak_txt = f'{cnt(n_scan)}条产品线没有一条停在自己的峰值'
    s1 = ('，'.join(x for x in [
        f'{m(i, i)}衍生品总 ADV **{B.num(tot[i], 0)} 千张/日**，'
        f'{I0_MONTH} 断点后 {n} 个月里{ordinal(rk)}{topn}',
        drive, peak_txt] if x) + '。')

    # ── s2 基数（R2）+ 季节。ICE 的头条现在带着一个两位数的环比跌，而全页没有第二处
    #    解释它 —— 上月的位置与本月这个历月的季节位置合起来才解释得完。
    be = B.base_effect(tot[i0:], i - i0)
    si = _seasonal_index(tot, months, i, i0)
    if be['mm'] is None:
        s2 = f'{m(i - 1, i)}无可比读数，本月的环比与基数都不报。'
    else:
        # ⚠️ 不重印同比读数：s1 刚给过一次，相邻两句印同一个数就是被禁的复述式摘要。
        #    安全性靠一条不变式而不是靠自觉：s1 里那个同比**永远印得出来** ——
        #    be['yy'] 要 i-i0 >= 12，而 i0 = 34，所以它成立就一定 i >= 46 >= 12，
        #    s1 的 yy_tot 必然也算得出（drive 那一支即便退化，也还有「单月同比 X」的兜底）。
        #    这条不变式一旦被改动（比如把 i0 挪到序列头部），这里就得跟着改。
        head2 = (f'环比 {B.pct(be["mm"])} 与单月同比'
                 f'{"反号" if be["conflict"] else "同向"}'
                 if be['yy'] is not None else f'环比 {B.pct(be["mm"])}')
        prev = (f'：{m(i - 1, i)}是 {n} 个月里{ordinal(be["prev_rank"], "高")}月'
                if be['prev_rank'] else '')
        if not si:
            seas = ''
        elif round(si['cur']) >= round(si['hi']):
            seas = f'，{si["cur_m"]} 月本就是历月指数最高的一档（{si["cur"]:.0f}）'
        else:
            seas = (f'，{si["cur_m"]} 月历月指数 {si["cur"]:.0f}'
                    f'、最高的 {si["hi_m"]} 月 {si["hi"]:.0f}')
        # 三个判据都当场算，一个都不写死：
        #   hi_base 只有上月**确实**排在前三分之一时才成立（排在后三分之二时说
        #           「跌掉的是高基数」就是编）；
        #   low_season 只有本月这个历月的指数低于 100 时才成立；
        #   两者都不成立时只能说「两个方向各说各话」，不许拼出一个因果。
        hi_base = be['prev_rank'] is not None and be['prev_rank'] * 3 <= n and be['mm'] < 0
        low_season = bool(si and si['cur'] < 100)
        if hi_base and low_season:
            why = '**这个环比里有上月的高基数、也有季节**'
        elif hi_base:
            why = '**这一跌的分母是上月的高位**'
        elif be['conflict']:
            why = '**两个方向各说各话，只读环比会读反**'
        elif be['yy'] is None:
            why = '**序列不足 12 个月，环比只能与上月自身的位置比**'
        else:
            why = '**环比可直读**'
        s2 = head2 + prev + seas + '，' + why + '。'

    # ── s3 结构 × 费率 —— 整页存在的理由。措辞是**结构比较**：只说同一张合约在两条腿上
    #    不是同一块钱，不说任何一条腿贡献了多少收入（收入归季度块那几张图，那里才有
    #    对账与覆盖率）。「滚动三月均」是承重限定词，见 BRIEF_MUST_KEEP。
    sh_en = en / tot * 100
    rk_en = B.rank_of(sh_en[i0:], i - i0)
    gap = _rpc_gap(D, i)
    srank = f'（{n} 个月里{ordinal(rk_en, "高")}）' if rk_en else ''
    if B.need(sh_en[i]) and gap and gap['ratio']:
        r_all = np.asarray(D['rpc_energy_usd'].values, float) / \
            np.asarray(D[dict(BRIEF_LEG_RPC)[gap['lo_zh']]].values, float)
        med = float(np.nanmedian(r_all[i0:i + 1]))
        # 倍数为 1 上下时「N 倍」那句不成立，换成「已经拉平」；判据当场算，不写死。
        punch3 = (f'**能源与{gap["lo_zh"]}的每张费率已经拉平**'
                  if round(gap['ratio'], 1) == 1.0 else
                  '**同一张合约在两条腿上不是同一块钱**')
        s3 = (f'能源占合约张数 {sh_en[i]:.1f}%{srank}，每张费率是{gap["lo_zh"]}腿的 '
              f'{gap["ratio"]:.1f} 倍（RPC 滚动三月均，中位 {med:.1f} 倍）——{punch3}。')
    else:
        s3 = ''

    # ── s4 分母层。NYSE 的份额对上**市场自己的**增速 —— 全仓只有这张表同时给了
    #    NYSE 的量与市场合并量，所以「丢的是份额」还是「缩的是大盘」可以真的分开。
    shc = np.asarray(D['share_nyse_us_cash_matched'].values, float) * 100.0
    cons = sum(np.asarray(D[c].values, float)
               for c in ('adv_tapeA_consolidated_mnsh', 'adv_tapeB_consolidated_mnsh',
                         'adv_tapeC_consolidated_mnsh'))
    vm = _venue_mix__brief(D, i, i0)
    venue = crank = ''
    if i >= 12 and B.need(shc[i], shc[i - 12], cons[i], cons[i - 12]) and cons[i - 12]:
        # 名次报**离得近的那一头**：份额落在样本上半区时印「第 20 低」是真话，
        # 但读者会把「低」读成位置低，而它其实排在高位（回放 2016 全年都是这种月）。
        # 取 rank_hi / rank_lo 里小的那个，措辞跟着走 —— 判据当场算，不写死方向。
        rk_hi = B.rank_of(shc[i0:], i - i0)
        rk_lo = B.rank_of(-shc[i0:], i - i0)
        rk_sh, w_sh = ((rk_lo, '低') if (rk_lo or 99) <= (rk_hi or 99) else (rk_hi, '高'))
        d_sh = float(shc[i] - shc[i - 12])
        mkt = float(cons[i] / cons[i - 12] - 1)
        # 份额的差走 SG.ratio_diff_txt（→ pp/bp），不许自己写判据 —— 见 _venue_mix__brief 的注释。
        d_txt = SG.ratio_diff_txt(d_sh, COL_BRIEF['share_nyse_us_cash_matched'])
        # 「丢的是份额不是大盘」是**判断**，分支全部由两个数当场比出来：
        # 份额跌而大盘没缩 → 份额问题；两个都在动 → 不许说成单因；份额涨 → 换措辞。
        big = abs(mkt) >= 0.05          # 大盘自己动了 5% 以上才算「大盘在动」
        # 五个分支全部由这两个数当场比出来。第一版只有三支，回放里印出过两句坏话：
        #   · 份额同比恰为 0（官方份额只发到 0.1%，实测有这样的月）却印「在回升」；
        #   · 份额在丢、而大盘同比 +18.6% 时印「份额与大盘同时在动」——「同时」把一涨
        #     一跌说成了同一件事，而这恰恰是本页唯一能把两者分开的地方。
        if d_sh == 0:
            punch4 = '**份额同比持平**'
        elif d_sh > 0:
            punch4 = '**份额同比是在回升的**'
        elif not big:
            punch4 = '**丢的是份额不是大盘**'
        elif mkt < 0:
            punch4 = '**份额与大盘同时在缩**'
        else:
            punch4 = '**大盘在长而 NYSE 没跟上**'
        if vm:
            cnt_up = sum(1 for v in vm if v['d_pp'] > 0)
            # ⚠️ B.quant 的判据只对 1..n 有定义：0 传进去会印出「只有0个」
            #   （B.cn 对 0 返回 '0'，而且不带空格）。计数为零是常有的月份、不是异常，
            #   所以在这里换成中文说法，不去改 brief.py 的判据（cme.py:2540 同一处理）。
            up_txt = (B.quant(cnt_up, len(vm), '个') if cnt_up else '一个也没有')
            venue = f'；{cnt(len(vm))}个市场里份额上行的{up_txt}'
        crank = f'（{n} 个月里{ordinal(rk_sh, w_sh)}）' if rk_sh else ''
        s4 = (f'NYSE 现货 matched 份额 {shc[i]:.1f}%{crank}'
              f'、单月同比 {d_txt}，而三带合并量（推导值）单月同比 {B.pct(mkt)}'
              f'——{punch4}{venue}。')
    else:
        s4 = ''

    # ── s5 QTD。季度块只画**完整季**（不完整季不画、也不用 partial_months），所以
    #    未满的当季在图上一格都没有 —— brief 是全页唯一能先给一个季度读数的地方。
    #    ⚠️ 季度一满，这一句就自己消失：那时候季度块已经画得出它，再写就是两处各说一遍。
    #    ⚠️ 只过 1 个月的季度也不写：那时 QTD 逐字等于本月自己的单月同比，s1 已经印过。
    q = _qtd(D, [('总 ADV', 'adv_futures_options_kcontracts'),
                 ('NYSE 现货', 'adv_nyse_us_cash_handled_mnsh')], i)
    if q and not q['full'] and q['k'] >= 2:
        s5 = (f'本季已过 {q["k"]} 个月（季度块只画完整季），QTD 对齐去年同 {q["k"]} 个月：'
              + '、'.join(f'{z} {B.pct(v)}' for z, v in q['legs']) + '，按月简单平均。')
    else:
        s5 = ''

    # ── 字数：B.render 的 230-380 是拦「模板拼坏了」的，贴着上界发布是可预见的停更风险。
    #    这里自压到 BRIEF_HI，压法是**省可省项**，绝不删限定词（滚动三月均 / 推导值 /
    #    按月简单平均）—— 那些是口径的一部分，删了就是另一句话。
    #    可省的六项，以及 2026-08 实测各自省下的字数：
    #      topn  总 ADV 名次的「（前 N%）」（8 字，最便宜）
    #      srank 能源占合约张数在历史里的名次（14 字）
    #      crank NYSE 份额在历史里的名次（14 字）
    #      venue 四个市场里份额上行的个数（17 字）
    #      peak  十二条产品线的峰值扫描（22 字）
    #      qtd   整句 QTD（69 字，最后才动）
    def assemble(drop=()):
        s1_ = s1
        if 'peak' in drop:
            s1_ = s1_.replace('，' + peak_txt, '')
        if 'topn' in drop and topn:
            s1_ = s1_.replace(topn, '')
        s3_ = s3.replace(srank, '') if ('srank' in drop and s3 and srank) else s3
        s4_ = s4
        if 'venue' in drop and s4_ and venue:
            s4_ = s4_.replace(venue, '')
        if 'crank' in drop and s4_ and crank:
            s4_ = s4_.replace(crank, '')
        s5_ = '' if 'qtd' in drop else s5
        return [SG.md_bold(x) for x in (s1_, s2, s3_, s4_, s5_) if x]

    def plain_len(body):
        return len(re.sub(r'<[^>]+>', '', ''.join(body)))

    # ⚠️ 阶梯是**有序的**，不是「枚举全部子集挑删得最少的那一版」—— 第一版就是后者，
    #   实测直接把整句 QTD 判了死刑：五个装饰件合起来 72 字、而 QTD 整句 60 字，
    #   只要缺口落在 60-72 之间，「删得最少」永远会挑那一句整删（回放 128 个月里
    #   五句齐全的只有 2 个月）。「最小的先丢」说的是**先丢小的**，删掉一整句读数
    #   显然不是最小的那一件，所以这里按件从小到大排成一条链，整句 QTD 排在最后。
    LADDER = [(), ('topn',), ('topn', 'srank'), ('topn', 'srank', 'crank'),
              ('topn', 'srank', 'crank', 'venue'),
              ('topn', 'srank', 'crank', 'venue', 'peak'),
              ('topn', 'srank', 'crank', 'venue', 'peak', 'qtd')]
    body = next((b for b in (assemble(d) for d in LADDER) if plain_len(b) <= BRIEF_HI),
                assemble(LADDER[-1]))   # 全删完还超 → 真的拼坏了，交给 render 的护栏去响

    # 承重限定词必须活着。这道断言防的不是笔误，而是**未来某次为了压字数顺手删掉一个
    # 括号**：那种改动读起来更顺、字数更短、而且不会有任何护栏发现口径已经没了。
    # 判据挂在**句子还在不在**上：整句被降级阶梯丢掉是允许的（那时页面上没有那个读数，
    # 也就没有需要限定的东西），丢掉句子里的限定词才是事故。
    txt = ''.join(body)
    for w, src in (('滚动三月均', s3), ('推导值', s4), ('按月简单平均', s5)):
        alive = bool(src) and SG.md_bold(src)[:12] in txt
        if alive and w not in txt:
            raise SystemExit(f'brief: 承重限定词「{w}」被降级阶梯删掉了，那是口径不是修辞')
    return B.render(body)

# ==========================================================================
# 【table】
# ==========================================================================

# -*- coding: utf-8 -*-
"""build/ice.py 的一段：**末尾核对表**（Exhibit EX_TABLE）。

这一段回答一个手写页才有的问题：**表列该放什么**。

声明式引擎里没有这个问题 —— `build/single.py:3859` 的 `table()` 把
`self.head + 所有 group 的 cols` 原样铺开，「不画」与「不进核对表」是同一件事。
ICE 的 spec 注册了 52 列，于是核对表就是 52 列 × 13 行，横向要滚很远，
而 ICE 自己发布的三列交易日数（`trading_days_*`）因为**没上过图**，
在整页上一个字都找不到 —— 一张自称「可与官方披露逐格对账」的表，
读者拿它把日均还原成当月合计都做不到。

手写页把「上图」与「进表」解耦了。这一段用上这个自由，**两个方向都用**：
砍掉页面从不印、也不进任何推导值的 9 列，同时把 3 列从没上过图的交易日**请进来**。
"""

HERE__table = os.path.join(ROOT, 'build')

sys.path.insert(0, HERE__table)

# ══════════════════════ 1. 列元数据（COL__table 的表相关子集）════════════════════
#
# 合并进 build/ice.py 之后这一块**整块删掉**，直接用公共段那个 COL__table。
# 留在这里只为让本文件能独立跑；`__main__` 里有一道闸门，把下面每一格
# 与 build/specs/ice.py 的 SPEC 逐字比对（zh / unit / fmt / scale / stock），
# 差一个字就停机 —— unit 串是承重的（specs/ice.py:560、:589 记着理由：
# 把 'USD/contract' 改写成别的量纲白名单外的写法，`SG.col_is_ratio()` 第 ③ 级
# 会静默翻掉，同比从「美元差」变成「百分比变化」，页面不报错）。
def _c__table(col, zh, unit, fmt, scale=1.0, stock=False):
    return {'col': col, 'zh': zh, 'unit': unit, 'fmt': fmt,
            'scale': scale, 'stock': stock}

COL__table = {c['col']: c for c in [
    # 头条两列
    _c__table('adv_futures_options_kcontracts', '衍生品总 ADV', 'k contracts/day', 'f0c'),
    _c__table('adv_nyse_us_cash_handled_mnsh', 'NYSE 美股现货 ADV（handled）', 'mn shares/day', 'f0c'),
    # 能源 ADV
    _c__table('adv_energy_kcontracts', '能源合计', 'k contracts/day', 'f0c'),
    _c__table('adv_brent_kcontracts', 'Brent 原油', 'k contracts/day', 'f0c'),
    _c__table('adv_gasoil_kcontracts', 'Gasoil 柴油', 'k contracts/day', 'f0c'),
    _c__table('adv_otheroil_kcontracts', '其他原油与成品油', 'k contracts/day', 'f0c'),
    _c__table('adv_natgas_kcontracts', '天然气（含 TTF）', 'k contracts/day', 'f0c'),
    _c__table('adv_power_kcontracts', '电力', 'k contracts/day', 'f0c'),
    _c__table('adv_environmentals_kcontracts', '环境权益与其他', 'k contracts/day', 'f0c'),
    # 农金 ADV
    _c__table('adv_ag_metals_kcontracts', '农产品与金属合计', 'k contracts/day', 'f0c'),
    _c__table('adv_sugar_kcontracts', '糖', 'k contracts/day', 'f0c'),
    _c__table('adv_otherags_metals_kcontracts', '其他农产品与金属', 'k contracts/day', 'f0c'),
    _c__table('adv_commodities_kcontracts', '大宗商品合计（能源+农金）', 'k contracts/day', 'f0c'),
    # 金融 ADV
    _c__table('adv_financials_kcontracts', '金融合计（不含单股）', 'k contracts/day', 'f0c'),
    _c__table('adv_stir_kcontracts', '短期利率', 'k contracts/day', 'f0c'),
    _c__table('adv_mltir_kcontracts', '中长期利率', 'k contracts/day', 'f0c'),
    _c__table('adv_equity_index_kcontracts', '股指', 'k contracts/day', 'f0c'),
    _c__table('adv_fx_credit_kcontracts', 'FX 与 USDX', 'k contracts/day', 'f0c'),
    _c__table('adv_single_stock_kcontracts', '单股（已剔出合计）', 'k contracts/day', 'f0c'),
    # 未平仓（存量）
    _c__table('oi_commodities_kcontracts', '大宗商品', 'k contracts', 'f0c', stock=True),
    _c__table('oi_energy_kcontracts', '能源', 'k contracts', 'f0c', stock=True),
    _c__table('oi_ag_metals_kcontracts', '农产品与金属', 'k contracts', 'f0c', stock=True),
    _c__table('oi_financials_kcontracts', '金融', 'k contracts', 'f0c', stock=True),
    _c__table('oi_rates_kcontracts', '利率', 'k contracts', 'f0c', stock=True),
    _c__table('oi_other_financials_kcontracts', '股指与 FX', 'k contracts', 'f0c', stock=True),
    # RPC（滚动三月均）
    _c__table('rpc_commodities_usd', '大宗商品', 'USD/contract', 'f2'),
    _c__table('rpc_energy_usd', '能源', 'USD/contract', 'f2'),
    _c__table('rpc_ag_metals_usd', '农产品与金属', 'USD/contract', 'f2'),
    _c__table('rpc_financials_usd', '金融', 'USD/contract', 'f2'),
    _c__table('rpc_rates_usd', '利率', 'USD/contract', 'f2'),
    _c__table('rpc_other_financials_usd', '股指与 FX', 'USD/contract', 'f2'),
    # NYSE 美股期权
    _c__table('adv_us_equity_options_industry_kcontracts', '全美股票/ETF 期权行业总量',
       'k contracts/day', 'f0c'),
    _c__table('adv_nyse_equity_options_kcontracts', 'NYSE 两所合计', 'k contracts/day', 'f0c'),
    _c__table('share_nyse_equity_options', 'NYSE 份额（官方直接给）', '%', 'pct1', scale=100),
    _c__table('rpc_nyse_equity_options_usd', 'NYSE 期权 RPC', 'USD/contract', 'f2'),
    # NYSE 美股现货
    _c__table('share_nyse_us_cash_matched', 'NYSE 全美 matched 份额', '%', 'pct1', scale=100),
    _c__table('rpc_nyse_us_cash_usd_per100sh', '现货 RPC（每 100 股）', 'USD/100 shares', 'f3'),
    _c__table('adv_tapeA_consolidated_mnsh', 'Tape A 全市场', 'mn shares/day', 'f0c'),
    _c__table('adv_nyse_tapeA_matched_mnsh', 'Tape A · NYSE matched', 'mn shares/day', 'f0c'),
    _c__table('adv_nyse_tapeA_handled_mnsh', 'Tape A · NYSE handled', 'mn shares/day', 'f0c'),
    _c__table('share_nyse_tapeA_matched', 'Tape A 份额', '%', 'pct1', scale=100),
    _c__table('adv_tapeB_consolidated_mnsh', 'Tape B 全市场', 'mn shares/day', 'f0c'),
    _c__table('adv_nyse_tapeB_matched_mnsh', 'Tape B · NYSE matched', 'mn shares/day', 'f0c'),
    _c__table('adv_nyse_tapeB_handled_mnsh', 'Tape B · NYSE handled', 'mn shares/day', 'f0c'),
    _c__table('share_nyse_tapeB_matched', 'Tape B 份额', '%', 'pct1', scale=100),
    _c__table('adv_tapeC_consolidated_mnsh', 'Tape C 全市场', 'mn shares/day', 'f0c'),
    _c__table('adv_nyse_tapeC_matched_mnsh', 'Tape C · NYSE matched', 'mn shares/day', 'f0c'),
    _c__table('adv_nyse_tapeC_handled_mnsh', 'Tape C · NYSE handled', 'mn shares/day', 'f0c'),
    _c__table('share_nyse_tapeC_matched', 'Tape C 份额', '%', 'pct1', scale=100),
    # CDS
    _c__table('cds_total_notional_usdbn', '合计', 'USD bn/month', 'f0c'),
    _c__table('cds_client_notional_usdbn', '客户盘', 'USD bn/month', 'f0c'),
    _c__table('cds_nonclient_notional_usdbn', '非客户盘', 'USD bn/month', 'f0c'),
]}

# ══════════════════ 2. 表专用列：三列交易日（本轮新加）═══════════════════
#
# 为什么它们**不进 COL__table**：COL__table 的存在理由是喂 `SG.col_is_ratio()` / `rhs_ylab2()`
# 那套口径判据，而那套判据的第 ③ 级读的就是 `unit`。冻结契约把合法 unit 钉死成
# 七个串（都是 build/specs/ice.py 里逐字出现过的量纲）。交易日数不是其中任何一个，
# 也从来不需要被判「同比是百分数还是百分点」—— 它一张图都不上、一条同比都不画。
# 把一个判据认不出的 unit 塞进 COL__table，等于往一个专供判据读的字典里放一个判据读不懂的格子；
# 真出事的时候（有人哪天给它画了同比）判据会静默走到默认档，不响。
# 所以它留在表本地，**永远不经过 SG**。这条约束由 `_meta()` 与闸门 G3 一起兜住。
TBL_LOCAL = {
    'trading_days_commod':      {'zh': '交易日·大宗', 'unit': 'days', 'fmt': 'f0'},
    'trading_days_rates':       {'zh': '交易日·金融', 'unit': 'days', 'fmt': 'f0'},
    'trading_days_us_equities': {'zh': '交易日·美股', 'unit': 'days', 'fmt': 'f0'},
}

#: 冻结契约里的合法 unit 白名单（= build/specs/ice.py 用过的全部量纲）+ 表本地那一个。
#: 右边是**表头里的紧凑记号**。表宽的大头不是数字而是表头：旧版 52 列每个表头都把
#: 完整单位串重复一遍（「大宗商品合计（能源+农金）（k contracts/day）」26 个显示宽度里
#: 有 17 个是单位），横向滚动的距离多半是被这一串吃掉的。
#: 紧凑记号 → 完整官方写法的对照由 `TBL_NOTE` 在表注里**逐条**给出，一个都不省 ——
#: 「压表宽」不许变成「把单位藏起来」。
UNIT_SHORT = {
    'k contracts/day': 'k/d',
    'k contracts':     'k',
    'USD/contract':    '$/ct',
    'USD/100 shares':  '$/100sh',
    'mn shares/day':   'mn sh/d',
    'USD bn/month':    '$bn/mo',
    '%':               '%',
    'days':            'd',
}

# ═════════════════════════ 3. 表列方案（TBL_COLS）═════════════════════════
#
# 判据不是「上没上图」，而是**这一列能不能核一个数**，分四档，从强到弱：
#
#   (B) 本页推导值的输入。隐含收入 = ADV × 交易日 × RPC，三样缺一样，
#       Ex5–Ex9 那一整块（占全页 5 张图）读者一格都对不了。三列交易日就是靠这一条
#       进来的 —— 它们一张图都不上，但它们是全表**唯一**能把日均还原成当月合计的列。
#   (A) 页面上印出来过的官方读数（柱高、线上的点、热力格、headline 数据条、
#       图注里现算的那些聚合读数）。读者拿表核图，核的就是这些。
#   (D) 页面明确**排除**掉的官方读数，且这个排除本身是一句需要凭据的话。
#       只有一列：`adv_single_stock_kcontracts`（官方已把它剔出 TOTAL FINANCIALS）。
#       没有它，读者把四条金融腿加起来对不上 `adv_financials` 时，
#       无法分辨是「单股被剔了」还是「本页抄错了」。
#   (X) 以上都不是 → 走，理由逐列登记在 `DROPPED` 里。
#
# ⚠️ 有一档判据**故意没用**：「这一列 = 表内另外几列之和，读者自己能加出来」。
#    实测下来它一列都砍不动，而且砍了就是错的：ICE 的每一个合计行都是**独立四舍五入到
#    整千张 / 整百万股之后印出来的**，与分项之和处处不等 ——
#      adv_futures_options vs 大宗+金融    188 个月里 66 个不等，最大 0.5314%
#      adv_commodities     vs 能源+农金    188 个月里 49 个不等，最大 0.0466%
#      adv_financials      vs 四条腿       188 个月里 79 个不等，最大 0.0798%
#      adv_energy          vs 六个子项     188 个月里 103 个不等，最大 0.0813%
#      cds_total           vs 客户+非客户   164 个月里 34 个不等，最大 0.1852%
#      oi_commodities      vs 能源+农金    188 个月里 53 个不等，最大 0.0037%
#      oi_financials       vs 利率+股指FX  188 个月里 48 个不等，最大 0.0051%
#    （上面这七行是构建期现算的，见 `_sum_gaps()`；写死会与数据打架。）
#    合计行既然是独立的一格官方数字，它就**只能拿官方那一格去核**，
#    删掉它等于把「分项之和 ≠ 合计」这件事从可核变成传闻 —— 而那正是本页要陈述的事实之一。
#
# 排序按页面的论证顺序走，不按 CSV 的列序：交易日（还原当月合计的钥匙）→
# 头条 → 大宗商品 → 金融 → OI → RPC → NYSE 期权 → NYSE 现货 → CDS。
# 读者横向滚的时候，滚到哪一段是可预期的。
TBL_COLS = [
    # ── (B) 三列交易日：本轮新加，全页唯一能把日均还原成当月合计的列 ──
    ('dcm', 'trading_days_commod'),
    ('drt', 'trading_days_rates'),
    ('deq', 'trading_days_us_equities'),
    # ── (A) 头条 ──
    ('fo',  'adv_futures_options_kcontracts'),
    # ── (A)(B) 大宗商品 ADV：能源六子项上 Ex10/Ex11，能源与农金合计是收入腿的量 ──
    ('cm',  'adv_commodities_kcontracts'),
    ('en',  'adv_energy_kcontracts'),
    ('brn', 'adv_brent_kcontracts'),
    ('gso', 'adv_gasoil_kcontracts'),
    ('oil', 'adv_otheroil_kcontracts'),
    ('gas', 'adv_natgas_kcontracts'),
    ('pwr', 'adv_power_kcontracts'),
    ('env', 'adv_environmentals_kcontracts'),
    ('ag',  'adv_ag_metals_kcontracts'),
    ('sug', 'adv_sugar_kcontracts'),
    ('oag', 'adv_otherags_metals_kcontracts'),
    # ── (A)(B) 金融 ADV：stir+mltir 是利率腿的量，equity_index+fx_credit 是其他金融腿的量 ──
    ('fin', 'adv_financials_kcontracts'),
    ('sti', 'adv_stir_kcontracts'),
    ('mlt', 'adv_mltir_kcontracts'),
    ('eqi', 'adv_equity_index_kcontracts'),
    ('fxc', 'adv_fx_credit_kcontracts'),
    ('ss',  'adv_single_stock_kcontracts'),          # (D)
    # ── (A) 未平仓（存量）：四条叶子上 Ex12，两个合计是官方独立印的格子 ──
    ('oic', 'oi_commodities_kcontracts'),
    ('oie', 'oi_energy_kcontracts'),
    ('oia', 'oi_ag_metals_kcontracts'),
    ('oif', 'oi_financials_kcontracts'),
    ('oir', 'oi_rates_kcontracts'),
    ('oio', 'oi_other_financials_kcontracts'),
    # ── (A)(B) RPC：四条叶子上 Ex4，两个上层聚合进 Ex4 的标题与图注 ──
    ('rc',  'rpc_commodities_usd'),
    ('re',  'rpc_energy_usd'),
    ('ra',  'rpc_ag_metals_usd'),
    ('rf',  'rpc_financials_usd'),
    ('rr',  'rpc_rates_usd'),
    ('ro',  'rpc_other_financials_usd'),
    # ── (A)(B) NYSE 美股期权 ──
    ('ind', 'adv_us_equity_options_industry_kcontracts'),
    ('nyo', 'adv_nyse_equity_options_kcontracts'),
    ('sho', 'share_nyse_equity_options'),
    ('rno', 'rpc_nyse_equity_options_usd'),
    # ── (A)(B) NYSE 美股现货 ──
    ('nyc', 'adv_nyse_us_cash_handled_mnsh'),
    ('shc', 'share_nyse_us_cash_matched'),
    ('rnc', 'rpc_nyse_us_cash_usd_per100sh'),
    ('sha', 'share_nyse_tapeA_matched'),
    ('shb', 'share_nyse_tapeB_matched'),
    ('shcc', 'share_nyse_tapeC_matched'),
    # ── (A) CDS ──
    ('cdt', 'cds_total_notional_usdbn'),
    ('cdc', 'cds_client_notional_usdbn'),
    ('cdn', 'cds_nonclient_notional_usdbn'),
]

#: 走掉的列 + 逐列理由。**这不是文档，是闸门**：闸门 G8 要求
#: `TBL_COLS 的列 ∪ DROPPED 的键 == series/ice.csv 的全部列（除 month）`。
#: ICE 哪天往工作表里加一行、fetch 跟着多一列，构建期当场停机 ——
#: 而不是让新列静默地既不上表也没人记得它存在（旧的引擎版就是这样丢掉三列交易日的：
#: 没人决定过要丢，只是它没被注册成图列，于是自动不在表里）。
_TAPE_WHY = ('页面只印这条 tape 的「份额」（Ex17 三条线），不印它的量；'
             '而份额本身是 ICE 工作表里独立印出来的一格（fetch/ice.py:395-407 按行名抓的），'
             '拿官方那一格就能逐格对上，不需要读者在 13 行里自己做除法。'
             '份额 = matched ÷ consolidated 这个恒等式已经在 fetch/ice.py:858-866 '
             '对全部 188 个月逐月断言过了，比 13 行目视强。')

DROPPED = {
    'adv_nyse_tapeA_matched_mnsh':       _TAPE_WHY,
    'adv_nyse_tapeA_handled_mnsh':       _TAPE_WHY,
    'adv_tapeA_consolidated_mnsh':       _TAPE_WHY,
    'adv_nyse_tapeB_matched_mnsh':       _TAPE_WHY,
    'adv_nyse_tapeB_handled_mnsh':       _TAPE_WHY,
    'adv_tapeB_consolidated_mnsh':       _TAPE_WHY,
    'adv_nyse_tapeC_matched_mnsh':       _TAPE_WHY,
    'adv_nyse_tapeC_handled_mnsh':       _TAPE_WHY,
    'adv_tapeC_consolidated_mnsh':       _TAPE_WHY,
}

# ═══════════════════════════ 4. 构造 ═══════════════════════════════════
def _meta(col):
    """一列的展示元数据。COL__table 与 TBL_LOCAL 各管一半，**不许同时命中**。

    同时命中意味着有人把交易日也塞进了 COL__table（见 TBL_LOCAL 的注释：那是判据字典，
    不该有判据读不懂的格子），或者把一个图列复写了一遍 —— 两种都要当场停。
    """
    a, b = COL__table.get(col), TBL_LOCAL.get(col)
    if a is not None and b is not None:
        raise SystemExit(f'核对表列 {col} 在 COL__table 与 TBL_LOCAL 里各有一份 —— '
                         f'两份元数据早晚会分叉，页面不会响')
    c = a or b
    if c is None:
        raise SystemExit(f'核对表列 {col} 既不在 COL__table 也不在 TBL_LOCAL 里')
    return c

# 表头短名：只在**块内会重名**的地方加前缀。ADV 是表里的大头，不加前缀；
# OI 与 RPC 各加两个字，读者横向滚过去一眼知道自己在哪一段。
_ZH_OVERRIDE = {
    'adv_futures_options_kcontracts': '衍生品总 ADV',
    'adv_commodities_kcontracts': '大宗商品合计',      # 「（能源+农金）」挪进表注
    'adv_financials_kcontracts': '金融合计',           # 「（不含单股）」挪进表注
    'adv_single_stock_kcontracts': '单股（剔出合计）',
    'adv_nyse_us_cash_handled_mnsh': 'NYSE 现货 handled',
    'adv_us_equity_options_industry_kcontracts': '全美期权行业总量',
    'share_nyse_equity_options': 'NYSE 期权份额',
    'share_nyse_us_cash_matched': 'NYSE 现货 matched 份额',
    'rpc_nyse_us_cash_usd_per100sh': '现货 RPC',
    'oi_commodities_kcontracts': 'OI 大宗商品',
    'oi_energy_kcontracts': 'OI 能源',
    'oi_ag_metals_kcontracts': 'OI 农金',
    'oi_financials_kcontracts': 'OI 金融',
    'oi_rates_kcontracts': 'OI 利率',
    'oi_other_financials_kcontracts': 'OI 股指与 FX',
    'rpc_commodities_usd': 'RPC 大宗商品',
    'rpc_energy_usd': 'RPC 能源',
    'rpc_ag_metals_usd': 'RPC 农金',
    'rpc_financials_usd': 'RPC 金融',
    'rpc_rates_usd': 'RPC 利率',
    'rpc_other_financials_usd': 'RPC 股指与 FX',
    'cds_total_notional_usdbn': 'CDS 合计',
    'cds_client_notional_usdbn': 'CDS 客户盘',
    'cds_nonclient_notional_usdbn': 'CDS 非客户盘',
    'adv_ag_metals_kcontracts': '农金合计',
    'adv_otherags_metals_kcontracts': '其他农金',
}

def _zh(col):
    return _ZH_OVERRIDE.get(col) or _meta(col)['zh']

def _header(col):
    c = _meta(col)
    return f'{_zh(col)}（{UNIT_SHORT[c["unit"]]}）'

def _cell__table(v, c):
    """一格。scale 是列自己声明的恒等换算（份额 ×100），fmt 决定小数位与 % 后缀。

    格式化**不自己写**：`SG.fmt_val()` 是引擎那张表用的同一个函数，
    手写页与引擎在同一列上必须逐字节同形（闸门 G5 逐格验），否则读者在
    /ice/ 和别的引擎页之间来回看会以为两边数据不一样。
    """
    if v is None or not np.isfinite(v):
        return None
    return SG.fmt_val(float(v) * c.get('scale', 1.0), c['fmt']) or None

def _sum_gaps(df):
    """「合计 ≠ 分项之和」的现算读数。写死会与数据打架，所以每次构建现算。"""
    out = []
    for zh, tot, parts in [
        ('衍生品总 ADV vs 大宗+金融', 'adv_futures_options_kcontracts',
         ['adv_commodities_kcontracts', 'adv_financials_kcontracts']),
        ('大宗商品合计 vs 能源+农金', 'adv_commodities_kcontracts',
         ['adv_energy_kcontracts', 'adv_ag_metals_kcontracts']),
        ('金融合计 vs 四条腿', 'adv_financials_kcontracts',
         ['adv_stir_kcontracts', 'adv_mltir_kcontracts',
          'adv_equity_index_kcontracts', 'adv_fx_credit_kcontracts']),
        ('能源合计 vs 六个子项', 'adv_energy_kcontracts',
         ['adv_brent_kcontracts', 'adv_gasoil_kcontracts', 'adv_otheroil_kcontracts',
          'adv_natgas_kcontracts', 'adv_power_kcontracts',
          'adv_environmentals_kcontracts']),
        ('CDS 合计 vs 客户+非客户', 'cds_total_notional_usdbn',
         ['cds_client_notional_usdbn', 'cds_nonclient_notional_usdbn']),
        ('OI 大宗商品 vs 能源+农金', 'oi_commodities_kcontracts',
         ['oi_energy_kcontracts', 'oi_ag_metals_kcontracts']),
        ('OI 金融 vs 利率+股指FX', 'oi_financials_kcontracts',
         ['oi_rates_kcontracts', 'oi_other_financials_kcontracts']),
    ]:
        t = df[tot].astype(float)
        s = df[parts].astype(float).sum(axis=1)
        d = (t - s).abs() / t.abs().replace(0, np.nan)
        d = d.dropna()
        out.append({'zh': zh, 'n': int(len(d)), 'n_ne': int((d > 1e-12).sum()),
                    'max': float(d.max()) * 100})
    return out

def _daycal_falsify(df):
    """「合计与分项之差是两套交易日造成的」—— 这个解释的现算证伪。

    为什么要现算而不是照抄 fetch/ice.py:123-131 那句「偏差最大的三个月里两列恰恰相等」：
    照抄会**假**。那句点名的是 2011-08(32) / 2011-10(27) / 2012-08(16) 三个绝对差最大的
    月份，而今天这份 CSV 上第二大的是 2011-09（同样 27，且那个月两列交易日 21 vs 22
    **不相等**）—— 27 那一档是平局，谁排第二取决于排序的稳定性，而且上游一次回补就能
    把名次换掉。拿一个靠排名平局站住的句子去撑一条口径结论，下个月就会自己塌。

    这里换成一条不吃排名的证伪，而且两个方向都测：
      · 有差、但两列交易日**相同**的月份 —— 若真是交易日造成的，这类月份应当一个都没有；
      · 两列交易日**不同**、却**零差**的月份 —— 若真是交易日造成的，这类月份也应当没有。
    两边都非空，解释就不成立。这与 fetch/ice.py 的结论一致，但结论的支点换成了
    「全样本计数」，不再是三个具体月份。
    """
    t = df['adv_futures_options_kcontracts'].astype(float)
    s_ = (df['adv_commodities_kcontracts'].astype(float)
          + df['adv_financials_kcontracts'].astype(float))
    gap = (t - s_).abs()
    ne = gap > 1e-9
    same = df['trading_days_commod'].astype(int) == df['trading_days_rates'].astype(int)
    rel = (gap / t.abs()) * 100
    both = ne & same
    return {'n_ne': int(ne.sum()), 'n_same': int(same.sum()),
            'n_ne_same': int(both.sum()),
            'max_ne_same': float(rel[both].max()) if int(both.sum()) else float('nan'),
            'at_ne_same': mlab(rel[both].idxmax()) if int(both.sum()) else '—',
            'n_eq_diff': int(((~ne) & (~same)).sum())}

def _tbl_note(df, win, gaps):
    """表注。四段，顺序 = 读者拿这张表干活时的先后。

    单位那一段必须**如实说**：本表不是「官方原始单位、未换算」那一句就能了事的
    （cme.py:2139 那张表可以，因为它一列 scale 都没有）——
    ICE 有 5 列份额，CSV 里存的是比值、ICE 的工作表印的是百分数。
    """
    scaled = [(k, c) for k, c in [(k, _meta(c)) for k, c in TBL_COLS]
              if c.get('scale', 1.0) != 1.0]
    n_sc = len(scaled)
    umap = '、'.join(f'<code>{s}</code> = {u}'
                    for u, s in UNIT_SHORT.items()
                    if s != 'd') + '、<code>d</code> = 交易日数（天）'
    # 三套交易日在窗口内真的不一样吗 —— 现算，不写死
    d3 = df.loc[win, ['trading_days_commod', 'trading_days_rates',
                      'trading_days_us_equities']].astype(int)
    n_diff = int((d3.nunique(axis=1) > 1).sum())
    g = max(gaps, key=lambda r: r['max'])
    fz = _daycal_falsify(df)
    return (
        f'<b>单位：官方原始量级，只有一处还原。</b>本表的数值就是 ICE 工作表里印出来的量级，'
        f'不做任何换算 —— 唯一的例外是 {n_sc} 列份额：<code>series/ice.csv</code> 里存的是'
        f'比值（0.218），ICE 印的是百分数（21.8%），本表按 ICE 的印法 ×100 写。'
        f'所以这 {n_sc} 列是<b>往官方印法上还原</b>，不是偏离它。'
        f'表头里的紧凑记号对应的完整官方写法：{umap}。'
        f'（记号是为了压表宽：上一版 52 列把完整单位串在每个表头里重复了一遍，'
        f'横向要滚的距离多半是被这一串吃掉的。完整串在这里逐条给出，一个都不省。）'
        f'两处为压表宽省进本注的限定语：「大宗商品合计」= 能源 + 农金，'
        f'「金融合计」<b>不含单股</b>（官方已把单股剔出 TOTAL FINANCIALS，本表仍单列它，'
        f'好让读者把四条金融腿加起来对不上合计时，分得清是「被剔了」还是「本页抄错了」）。'

        f' <b>三列交易日是本轮加的，它们一张图都不上。</b>'
        f'ICE 每月披露三套交易日数，本表全给：大宗商品各列配 <code>trading_days_commod</code>，'
        f'金融四条腿配 <code>trading_days_rates</code>（工作表里那行写的是 '
        f'"COMMODITIES &amp; OTHER FINANCIALS"，是个陷阱：金融四条腿归的是利率那一套日历），'
        f'NYSE 美股期权与现货配 <code>trading_days_us_equities</code>。'
        f'日均 × 对应的那一套交易日 = 当月合计张数 / 股数 —— 这是把本页的日均口径还原成'
        f'官方新闻稿里那个合计数的<b>唯一</b>一步，没有这三列，读者手里只有日均，'
        f'对不了任何一个当月合计，本页那一整块隐含收入的季度图也无从复核。'
        f'本表窗口 {mlab(win[0])} – {mlab(win[-1])} 里有 {n_diff} 个月三套日历不完全相同。'
        f'⚠️ <b>衍生品总 ADV 不要乘任何一列</b>：它横跨大宗与金融两侧，'
        f'没有哪一套日历能代表它。'

        f' <b>本表不是 CSV 的全部列。</b>本页手写生成，表列与图列是分开选的 ——'
        f'判据是「这一列能不能核一个数」，不是「它上没上图」（三列交易日就是靠前一条进来的）。'
        f'走掉的是 {len(DROPPED)} 列 per-tape 的量（Tape A/B/C 各自的 consolidated / '
        f'matched / handled）：页面只印这三条 tape 的<b>份额</b>，而份额本身是 ICE '
        f'工作表里独立印出来的一格，拿官方那一格就能逐格对上；'
        f'「份额 = matched ÷ consolidated」这个恒等式已在取数环节对全部 {len(df)} 个月逐月'
        f'断言过（<code>fetch/ice.py</code>），不必让读者在 {len(win)} 行里重做。'
        f'这 {len(DROPPED)} 列的原值在 <code>series/ice.csv</code> 里，一格没删。'

        f' <b>「分项之和 ≠ 合计」是真的，别在这张表上当成抄错。</b>'
        f'ICE 的每一个合计行都是独立四舍五入到整千张 / 整百万股之后印出来的，'
        f'所以本表里把分项加起来一般对不上同一行的合计：最松的一档是{g["zh"]}'
        f'（{g["n"]} 个月里 {g["n_ne"]} 个不相等，最大差 {g["max"]:.3f}%）。'
        f'本表把合计与分项<b>都</b>留着，正是为了让这件事可核。'
        f'⚠️ 这个差的成因<b>官方从未说明</b>；不要用「大宗与金融各归一各的交易日」去解释它 —— '
        f'那个解释两个方向都被本表这几列自己证伪（全样本 {len(df)} 个月现算）：'
        f'衍生品总 ADV 与「大宗+金融」有差的 {fz["n_ne"]} 个月里，有 {fz["n_ne_same"]} 个月'
        f'两列交易日<b>完全相同</b>（差最大的一个是 {fz["at_ne_same"]}，{fz["max_ne_same"]:.3f}%）；'
        f'反过来，两列交易日<b>不同</b>却<b>零差</b>的月份有 {fz["n_eq_diff"]} 个。'
        f'写一个错的因果，下一个人会去修一个修不好的东西。'
    )

def build_table(df, n):
    """末尾核对表。`n` 由调用方给（必须 = 最后一张图的编号 + 1，闸门在调用方那边）。"""
    win = list(df.index[-WIN_TABLE:])
    cols, rows = [], []
    for k, c in TBL_COLS:
        cols.append([_header(c), k])
    for p in win:
        r = {'xl': mlab(p)}
        for k, c in TBL_COLS:
            r[k] = _cell__table(df[c].get(p, np.nan), _meta(c))
        rows.append(r)
    gaps = _sum_gaps(df)
    return {
        'n': n,
        # 标题不写「官方原始单位，未换算」——本表有 5 列份额 ×100，那句是假的
        # （cme.py:2139 可以那么写，它一列 scale 都没有）。也不写引擎版的
        # 「本页单位」——本表的量级就是官方的量级，说成「本页单位」等于把
        # 读者往「还要换算一次」上引。如实写成第三种。
        'title': (f'近 {WIN_TABLE} 个月月度指标核对表'
                  f'（ICE 原始量级；仅 {sum(1 for _, c in TBL_COLS if _meta(c).get("scale", 1.0) != 1.0)}'
                  f' 列份额按官方印法 ×100 写成百分数）'),
        'idx': '月份',
        'cols': cols,
        'rows': rows,
        # `note` 不在 CONTRACT §4 的字段表里（§3 的 kind:'table' 才列了它），
        # 但 page.js 的顶层核对表与 kind:'table' 走的是**同一个** tableCardHTML()
        # （assets/page.js:116 / :224），第 130 行就渲染 T.note；
        # build/verify_pages.py:599 的释义板体检也已经在读 `T.get('note')`。
        # 也就是说这个字段两侧都认，只是至今 34 页没人用过。
        # 放在这里而不是页尾 NOTES：这一段全部是「拿着这张表逐格对账时要知道的事」
        # （单位怎么还原、交易日配哪一列、哪些列走了、为什么加不出合计），
        # 读者的眼睛正落在表上，让他翻到页尾去找等于不写。
        'note': _tbl_note(df, win, gaps),
    }

# ══════════════════════════ 5. 自测（合并时删）══════════════════════════
def _w(s):
    """显示宽度估算：CJK/全角按 2，其余按 1。表宽对比要有个可比的尺子。"""
    s = re.sub(r'<[^>]+>', '', s or '')
    return sum(2 if ord(ch) > 0x2E80 else 1 for ch in s)

def _table_width(T):
    """整表显示宽度 ≈ 首列 + 每列 max(表头, 最宽单元格) + 每列 2 格 padding。"""
    w = max([_w(T.get('idx') or '月份')] + [_w(r['xl']) for r in T['rows']]) + 2
    for h, k in T['cols']:
        w += max([_w(h)] + [_w(r.get(k) or '—') for r in T['rows']]) + 2
    return w

# ══════════════════════════════════════════════════════════════════════════════
# 【page】Exhibit 编号 → 图列 → payload → main
# ══════════════════════════════════════════════════════════════════════════════
#
# 图号在十几处图注与页尾说明里被引用，靠人肉数是要出错的（原 PDF deck 的汇总表脚注
# 就把 Exhibit 3 写成了 Exhibit 4）。所以**全文只有这一块出现编号字面量**，
# 正文一律引用常量；图注里连「Exhibit N」这几个字都不许写，按标题指代
# （build/specs/enx.py:455 与 build/specs/sgx.py:841-848 已经这么规定过）。
#
# EX_RPC / EX_REV / EX_REVMIX / EX_BRIDGE 由 bridge 段先定义（它的图注要回指），
# 这里只补齐其余的，并在末尾用一道硬断言核对整串连号。

EX_ADV     = 2       # ① 衍生品总 ADV（水平值 + 次轴单月同比）
EX_MIX     = 3       # ① 合约构成：大宗 vs 金融
#      EX_RPC   = 4    ② 每张收入 RPC（四条叶子）           —— bridge 段已定义
#      EX_REV   = 5    ③ 隐含交易收入（季度）                —— bridge 段已定义
EX_RECON   = 6       # ③ 对账：三条腿对得上
#      EX_REVMIX= 7    ③ 收入结构（六段 100%）              —— bridge 段已定义
#      EX_BRIDGE= 8    ③ 量 / 费率分解（衍生品四腿）        —— bridge 段已定义
EX_REVTBL  = 9       # ③ 近 8 个完整季分腿收入（页中表）
EX_ENERGY  = 10      # ④ 能源 ADV 按产品
EX_HEAT    = 11      # ④ 十二个官方单列产品 × 近 N 个月同比
EX_OI      = 12      # ④ 月末未平仓（四条叶子）
EX_OPT     = 13      # ⑤ NYSE 美股期权 vs 全行业分母
EX_UNIT    = 14      # ⑤ 两本账的单位经济（指数化）
EX_CASH    = 15      # ⑤ NYSE 现货 handled ADV
EX_MATCHED = 16      # ⑤ NYSE matched 占全美合并量
EX_TAPE    = 17      # ⑤ 按 Tape 看份额
EX_CDS     = 18      # ⑥ CDS 清算名义额
EX_TABLE   = 19      # 附录 核对表

EX_FIRST = EX_ADV


# ── 收入与桥：一次算齐，供 Ex5/6/7/8/9 与 brief / notes 共用 ──────────────────
# `revenue_table` 用 LEG_KEYS（… 'other_financials' …），`build_bridge` 用
# BRIDGE_KEYS（… 'other_fin' …）—— 两段各写各的键名，这里做一次适配。
# ⚠️ 不许改任一段的键名去「统一」：两边的键都进了各自的图注与断言文案。
_BRIDGE_ALIAS = {'other_fin': 'other_financials', 'nyse_opt': 'nyse_options'}


def _rekey(d):
    """把 revenue 段的腿名映射成 bridge 段认得的键。

    ⚠️ 要映射 `LEG_DEFS` 的**全部六条**而不是 `BRIDGE_KEYS` 那四条：桥只画四条腿，
    但它要用另外两条算「本图覆盖了隐含总收入的百分之多少」并印进图注。
    """
    return {bk: d[_BRIDGE_ALIAS.get(bk, bk)] for bk, *_ in LEG_DEFS}


def build_page(df):
    """→ (exhibits, table, T, bridge_check, bstats)。"""
    # ── 派生列：两条收入腿的量。汇总表与页尾都要用 ──────────────────────────
    # **不做** adv_futures_options × 交易日 那种「乘回当月合计」的事：总 ADV 横跨
    # 大宗商品与金融两套日历，没有哪一套能代表它（三套交易日里 commod≠rates 的月份
    # 占多数）。派生只落在**单一日历内**能配对的两个和上。
    df['adv_rates_kcontracts'] = df['adv_stir_kcontracts'] + df['adv_mltir_kcontracts']
    df['adv_other_financials_kcontracts'] = (df['adv_equity_index_kcontracts']
                                             + df['adv_fx_credit_kcontracts'])
    for k, zh in (('adv_rates_kcontracts', '利率（短期 + 中长期）'),
                  ('adv_other_financials_kcontracts', '股指与 FX')):
        COL.setdefault(k, {'col': k, 'zh': zh, 'unit': 'k contracts/day', 'fmt': 'f0c'})

    T = revenue_table(df)
    QTRS = list(T['q'])
    ex = []

    # ══ 阶段 A · 头条：ICE 每天成交多少张 ═════════════════════════════════
    ex.append(gs_bar(
        EX_ADV, 'adv_futures_options_kcontracts',
        'ICE 衍生品总 ADV（期货与期权，不含单股）', 'k contracts/day', 'f0c',
        '衍生品总 ADV', zh='衍生品总 ADV'))

    ex.append(stacked_dual(
        EX_MIX, [('adv_commodities_kcontracts', '大宗商品（能源 + 农金）', 'NAVY'),
                 ('adv_financials_kcontracts', '金融（不含单股）', 'MBLUE')],
        'ICE 衍生品 ADV 的两块：大宗商品 vs 金融', 'k contracts/day', 'f0c'))

    # ══ 阶段 B · 一张合约不是一块钱 ═══════════════════════════════════════
    # 只画四条**叶子**费率。上层的 rpc_commodities / rpc_financials 是同一件事的
    # 聚合层，同图并画就是把一件事画两遍；它们的当期值现算进图注。
    ex.append(lines_endlabels(
        EX_RPC, ['rpc_energy_usd', 'rpc_ag_metals_usd',
                 'rpc_rates_usd', 'rpc_other_financials_usd'],
        '每张合约收入（RPC，官方滚动三月均）', 'USD/contract', 'usd2',
        colors=['NAVY', 'MBLUE', 'GREEN', 'GRAY'], yfloor=0))

    # ══ 阶段 C · 钱：隐含交易收入（季度块，块内不插月度图）═════════════════
    qw = [q for q in QTRS if q >= Q_FROM]
    ex.append(qtr_bar(
        EX_REV, qw, [float(T['total'][q]) for q in qw],
        'ICE 隐含交易收入（六条腿之和，季度）', '$mn / 季', 'f0c',
        '隐含交易收入（推导值）',
        line_values=[_qyoy(T['total'], q) for q in qw]))

    ex.append(_ex_recon(T))
    ex.append(_ex_revmix(T, qw))

    exb, bridge_check, bstats = build_bridge(
        _rekey(T['rev']), _rekey(T['qty']), _rekey(T['rpc']), QTRS, ex_bridge=EX_BRIDGE)
    ex.append(exb)

    ex.append(_ex_revtbl(T))

    # ══ 阶段 D · 能源特许经营 ═════════════════════════════════════════════
    # ⚠️ 不能用 gs_bar 的 stacks：那一支要求各段之和逐格 == values（容差 1e-6），
    #    而六个子项之和与 adv_energy 只在一部分月份精确相等（官方原表已四舍五入到
    #    整千张），会当场硬 ERROR。所以走 stacked_dual。
    ex.append(stacked_dual(
        EX_ENERGY,
        [('adv_brent_kcontracts', 'Brent 原油', 'NAVY'),
         ('adv_natgas_kcontracts', '天然气（含 TTF）', 'MBLUE'),
         ('adv_otheroil_kcontracts', '其他原油与成品油', 'GREEN'),
         ('adv_gasoil_kcontracts', 'Gasoil 柴油', 'BLUE')],
        '能源 ADV 按产品', 'k contracts/day', 'f0c',
        total_col='adv_energy_kcontracts',
        # 具名段只能有 5 个（数据色 6 个，残差段占一个）。电力与环境权益折进残差：
        # 实测这一段占能源 2.5%–5.6%，远高于引擎 0.6% 的不可见阈值，读者看得见也量得出；
        # 而把它们各自具名会挤掉 Gasoil 那一段的颜色。
        resid_name='电力与环境权益（含各列取整残差）'))

    ex.append(heat_matrix(EX_HEAT, _P12, '十二个官方单列产品：近 N 个月单月同比'))

    ex.append(stacked_dual(
        EX_OI,
        [('oi_energy_kcontracts', '能源', 'NAVY'),
         ('oi_ag_metals_kcontracts', '农产品与金属', 'MBLUE'),
         ('oi_rates_kcontracts', '利率', 'GREEN'),
         ('oi_other_financials_kcontracts', '股指与 FX', 'GRAY')],
        '月末未平仓合约（净 OI，存量、期末口径）', 'k contracts', 'f0c'))

    # ══ 阶段 E · 另一半公司：NYSE ═════════════════════════════════════════
    ex.append(stacked_dual(
        EX_OPT, [('adv_nyse_equity_options_kcontracts',
                  'NYSE 两所（Arca + American）', 'NAVY')],
        'NYSE 美股期权 ADV 与全行业分母', 'k contracts/day', 'f0c',
        total_col='adv_us_equity_options_industry_kcontracts',
        resid_name='行业其余（全美总量 − NYSE 两所）',
        line={'col': 'share_nyse_equity_options', 'name': 'NYSE 份额（RHS）',
              'color': 'GREEN'},
        ylab2='% —— 官方直接披露的 NYSE 份额'))

    ex.append(_ex_unit())

    ex.append(gs_bar(
        EX_CASH, 'adv_nyse_us_cash_handled_mnsh',
        'NYSE 美股现货 ADV（handled）', 'mn shares/day', 'f0c',
        'NYSE handled ADV', zh='NYSE 美股现货 ADV（handled）'))

    ex.append(_ex_matched())

    ex.append(lines(
        EX_TAPE, ['share_nyse_tapeA_matched', 'share_nyse_tapeB_matched',
                  'share_nyse_tapeC_matched'],
        'NYSE matched 份额按 Tape：各自对该带自己的合并量', '%', 'pct1',
        zero_base=True, end_label=True))

    # ══ 阶段 F · 收入分解看不见的那一块 ═══════════════════════════════════
    ex.append(stacked_dual(
        EX_CDS, [('cds_client_notional_usdbn', '客户盘', 'NAVY'),
                 ('cds_nonclient_notional_usdbn', '非客户盘', 'MBLUE')],
        'ICE Clear Credit 当月清算 CDS 名义额（当月总量，不是日均）',
        'USD bn / month', 'f0c'))

    tbl = build_table(df, EX_TABLE)
    return ex, tbl, T, bridge_check, bstats

# ── 阶段 D 的矩阵行：十二个**官方单列披露**的产品 ─────────────────────────
# 只收官方单列发布的产品，不收任何聚合（聚合与它的子项同图 = 一件事画两遍），
# 也不收行业分母（那不是 ICE 的业务）。
_P12 = ['adv_brent_kcontracts', 'adv_gasoil_kcontracts', 'adv_otheroil_kcontracts',
        'adv_natgas_kcontracts', 'adv_power_kcontracts', 'adv_environmentals_kcontracts',
        'adv_sugar_kcontracts', 'adv_otherags_metals_kcontracts',
        'adv_stir_kcontracts', 'adv_mltir_kcontracts',
        'adv_equity_index_kcontracts', 'adv_fx_credit_kcontracts']


def _qyoy(s, q):
    """季度序列的同比（本季 vs 去年同季）。算不出返回 None，不返回 nan ——
    payload_guard 会把 NaN 当硬错误挡下，而「这一格没有」是合法的。"""
    b = q - 4
    if b not in s.index:
        return None
    a, z = float(s[q]), float(s[b])
    if not np.isfinite(a) or not np.isfinite(z) or z == 0:
        return None
    return round((a / z - 1.0) * 100.0, 6)


def _ex_recon(T):
    """对账图：本页推导 vs ICE 官方披露，六项。

    官方那六个数是**外部常量**（OFFICIAL_REV，带出处与发布日），不随本页数据滚动 ——
    所以它既是图，也是一道构建期闸门：任何一项超容差就停机，而不是画出来让人自己看。
    """
    # 对账那三行用的是**官方分部收入的粒度**：金融是聚合列（官方原表 "Financial
    # futures & options" 就是一行），不是 rates + other_financials 相加 —— 这样才与
    # docs/verify/ice.md:519-526 同源。所以名字查找表要同时覆盖叶子腿与聚合腿。
    zh_of = dict({k: v['zh'] for k, v in AGGS.items()},
                 **{k: v['zh'] for k, v in LEG_BY_KEY.items()})
    labs, mine, offi, rel = [], [], [], []
    for key, q, off in OFFICIAL_REV:
        v = float(T['rev'][key][q])
        labs.append(f'{zh_of[key]} {qlab(q)}')
        mine.append(round(v, 6)); offi.append(float(off))
        rel.append(round((v / off - 1.0) * 100.0, 6))
    worst = max(abs(x) for x in rel)
    if worst > RECON_TOL_PCT:
        raise SystemExit(
            f'Exhibit {EX_RECON}：对账最差 {worst:.2f}% 超过容差 {RECON_TOL_PCT}% —— '
            f'要么口径变了，要么官方锚点该换一期了，不许把图画出来当没事')
    return {
        'n': EX_RECON, 'kind': 'grouped_bars',
        'title': f'对账：三条腿能与官方分部收入对上，最差 {worst:.2f}%',
        'xlabels': labs, 'ylab': '$mn / 季', 'fmt': 'f0c',
        'groups': [{'name': '本页推导（隐含收入）', 'color': 'NAVY', 'values': mine},
                   {'name': f'ICE 披露（{OFFICIAL_SRC}）', 'color': 'BLUE', 'values': offi}],
        'line': {'name': '相对差（RHS）', 'color': 'GRAY', 'values': rel, 'yfmt': 'pct1'},
        'ylab2': '% —— 推导 ÷ 披露 − 1',
        'src_extra': OFFICIAL_REF,
        'note': _RECON_NOTE,
    }


def _ex_revmix(T, qw):
    """收入结构：六段 100% 堆叠。季度粒度，所以手搭而不是走 stacked_dual。"""
    M = revenue_mix(T, keys=LEG_KEYS, pct=True)
    cols = ['NAVY', 'BLUE', 'MBLUE', 'GRAY', 'GREEN', 'GOLD']
    stacks = [{'name': LEG_BY_KEY[k]['zh'], 'color': c,
               'values': [round(float(M[k][q]), 6) for q in qw], 'label': False}
              for k, c in zip(LEG_KEYS, cols)]
    return {
        'n': EX_REVMIX, 'kind': 'stacked_dual',
        'title': '隐含交易收入的结构（六条腿，自归一 = 100%）',
        'xlabels': [qlab(q) for q in qw], 'ylab': '% of implied revenue',
        'fmt': 'pct1', 'stacks': stacks,
        'src_extra': ('Shares are computed as each leg divided by the sum of the six '
                      'legs on the same quarter; the stacks sum to 100% by construction'),
        'note': _REVMIX_NOTE,
    }


def _ex_revtbl(T):
    """页中表：近 8 个完整季的分腿隐含收入。

    末尾那张核对表是**官方原始单位、供逐格对账**的，装不下派生值；派生值只能在这里给，
    而且必须紧跟着它服务的那几张图（CONTRACT §3：读者是看完图之后立刻要看它，
    推到末尾附录等于让他翻回去找）。

    ⚠️ `kind:'table'` 的形状是 `cols=[[表头, 键], …]` + `rows=[{'xl': 行标, 键: 值}]` ——
       page.js:119-123 直接拼 `c[0]` 与 `r.xl`。用 heads/cells 那套会渲成
       「只有首列一根表头」外加一列 `undefined`。
    """
    qs = list(T['q'])[-8:]
    cols = [[LEG_BY_KEY[k]['zh'], k] for k in LEG_KEYS] + [['合计', 'tot']]
    rows = []
    for q in qs:
        r = {'xl': qlab(q), 'tot': comma(float(T['total'][q]), 1)}
        for k in LEG_KEYS:
            r[k] = comma(float(T['rev'][k][q]), 1)
        rows.append(r)
    return {'n': EX_REVTBL, 'kind': 'table',
            'title': f'近 {len(qs)} 个完整季的分腿隐含收入（$mn，全部为推导值）',
            'cols': cols, 'rows': rows, 'note': _REVTBL_NOTE}


def _ex_unit():
    """两本账的单位经济，指数化到窗口左端 = 100。

    两条的单位是 USD/contract 与 USD/100 shares —— **量纲不同不能同轴**
    （Cboe 拆 9a/9b 那一条的同一个判据）。这张图要说的是方向与幅度不是水平，
    所以指数化；绝对值与起点由图注现算给出。
    """
    out = []
    for col, zh, color in (('rpc_nyse_equity_options_usd', 'NYSE 期权 RPC', 'NAVY'),
                           ('rpc_nyse_us_cash_usd_per100sh', 'NYSE 现货 RPC（每 100 股）', 'MBLUE')):
        s = df[col].reindex(W25).astype(float)
        base = float(s.iloc[0])
        if not np.isfinite(base) or base == 0:
            raise SystemExit(f'Exhibit {EX_UNIT}：{col} 在窗口左端没有可用基期')
        out.append({'name': zh, 'color': color,
                    'values': L((s / base * 100.0).values)})
    return {'n': EX_UNIT, 'kind': 'lines',
            'title': f'NYSE 两本账的单位经济（指数化，{XL25[0]} = 100）',
            'xlabels': XL25, 'ylab': f'index, {XL25[0]} = 100', 'fmt': 'f0',
            'series': out, 'zero_base': True, 'end_label': True,
            'height': LINE_H_ENDLABEL, 'note': _UNIT_NOTE}


def _ex_matched():
    """NYSE matched 占全美合并量。

    官方**没有** A+B+C matched 合计行，也没有三带合并量的合计行 —— 两条都是本页
    派生的。派生列写进 df 再走已验过的 stacked_dual，比手搭一个 dict 安全：
    残差非负、逐格闭合、右轴线不是柱除柱这几道闸门都在那个构造器里。
    """
    m = ['adv_nyse_tapeA_matched_mnsh', 'adv_nyse_tapeB_matched_mnsh',
         'adv_nyse_tapeC_matched_mnsh']
    c = ['adv_tapeA_consolidated_mnsh', 'adv_tapeB_consolidated_mnsh',
         'adv_tapeC_consolidated_mnsh']
    df['_nyse_matched_mnsh'] = df[m].sum(axis=1, min_count=len(m))
    df['_consolidated_mnsh'] = df[c].sum(axis=1, min_count=len(c))
    # ⚠️ 两份 COL 都要登记：`COL` 是全页的列元数据（汇总表 / 核对表 / 释义板读它），
    #    `COL__exlib` 是构图库自己那份（图题、ylab、ylab2 读它）。只登记一份，
    #    另一份会在「列不在 COL 里」那道闸上停机 —— 这正是它拦住的事故。
    for k, zh in (('_nyse_matched_mnsh', 'NYSE 自营撮合（A+B+C matched）'),
                  ('_consolidated_mnsh', '全美合并量（A+B+C consolidated）')):
        meta = {'col': k, 'zh': zh, 'unit': 'mn shares/day', 'fmt': 'f0c'}
        COL[k] = dict(meta)
        COL__exlib[k] = dict(meta)
    return stacked_dual(
        EX_MATCHED, [('_nyse_matched_mnsh', 'NYSE 自营撮合（matched）', 'NAVY')],
        'NYSE matched 占全美合并量', 'mn shares/day', 'f0c',
        total_col='_consolidated_mnsh',
        resid_name='其余全部场所（含暗池 / 内化商 / TRF）',
        line={'col': 'share_nyse_us_cash_matched', 'name': 'NYSE matched 份额（RHS）',
              'color': 'GREEN'},
        ylab2='% —— 官方直接披露的全美 matched 份额')

# ── 页面元信息 ────────────────────────────────────────────────────────────────
TRACKER = 'Intercontinental Exchange Monthly Operating Tracker'
TITLE = f'洲际交易所（ICE）月度经营指标 — {CUR.year} 年 {CUR.month} 月'
HUB_LINE = '能源衍生品 + NYSE 上市场所 + CDS 清算；全仓唯一带全市场分母的一家'

# ⚠️ `subtitle` / `headline` / `title` / `tracker` / `through_label` 五个字段
#    **一个 HTML 标签都不许有** —— page.js 走 textContent，标签会原样印出来，
#    而 verify_pages.py 的 TEXT_ONLY 那道是 ERROR（→ monthly_run FAIL → 全站不发布）。
SUBTITLE = (f'{SRC}。数据截至 {mlab(CUR)}；月度图自 {XL25[0]} 起 {len(W25)} 个月，'
            f'季度块自 {qlab(Q_FROM)} 起。收入为本页推导值，非 ICE 披露。')


def _headline():
    """页顶数据条。四个读数：两条头条列 + 隐含收入 + 能源占收入的比重。

    ⚠️ 一个数都不写死 —— 全部现算。正负号交给 f-string 的 `+` 标志。
    """
    T = revenue_table(df)
    q = T['q'][-1]
    tot = float(T['total'][q])
    egy = float(T['rev']['energy'][q]) / tot * 100.0
    a = float(df['adv_futures_options_kcontracts'].iloc[-1])
    c = float(df['adv_nyse_us_cash_handled_mnsh'].iloc[-1])
    ya = _mom_yoy_last('adv_futures_options_kcontracts')
    yc = _mom_yoy_last('adv_nyse_us_cash_handled_mnsh')
    return (f'{mlab(CUR)}：衍生品总 ADV {comma(a, 0)} 千张/日（同比 {ya:+.1f}%）；'
            f'NYSE 美股现货 handled ADV {comma(c, 0)} 百万股/日（同比 {yc:+.1f}%）；'
            f'{qlab(q)} 隐含交易收入 {comma(tot, 0)} 百万美元（推导值），'
            f'其中能源一条腿占 {egy:.1f}%。')


def _mom_yoy_last(col):
    s = df[col].astype(float)
    return float(YOY.mom_yoy(s, YOY.FLOW).iloc[-1])


FOOTER = ('本页由 build/ice.py 生成；口径与方法见页尾说明。'
          '数字全部现算，页面上没有任何一个写死的快照。')

_RECON_NOTE = (
    '<b>这是本页唯一一处派生量有官方对照的地方。</b>隐含收入按季度构造：'
    '<code>Σ<sub>季内三月</sub>(ADV × 该腿的交易日列) × 季末月 RPC ÷ 换算因子</code>。'
    '<b>必须按季</b> —— ICE 的 RPC 是滚动三月均，季末月那一格的窗口恰好覆盖该季度。'
    '逐月形式在<b>这六个能对账的点</b>上一律偏低，而季末月形式全部落在容差内；'
    '这是可核的六点事实，<b>不是</b>「逐月形式系统性低估」那种全样本断言。'
    '⚠️ <b>只有这三条腿能对账</b>（能源、农产品与金属、金融合计）。'
    '利率、股指与 FX、NYSE 期权、NYSE 现货四条腿<b>没有任何官方数可对</b>，'
    '是纯推导值 —— <b>不要让这三条替那四条背书</b>。')

_REVMIX_NOTE = (
    '<b>分母是六条腿之和（自归一），不是 ICE 任何一个官方收入口径</b> —— '
    '它不含数据、上市、固定收益与非交易的清算收入。'
    '⚠️ <b>钱的结构与量的结构不是一回事</b>：这正是本页的论点 —— '
    '合约张数最多的那条腿，未必是挣钱最多的那条。各腿的每张收入见「一张合约不是一块钱」那张图。')

_REVTBL_NOTE = (
    '全部为<b>推导值</b>，不是 ICE 披露的分部收入。本表是收入那三张图的共同底料。'
    '末尾的核对表是<b>官方原始单位、供逐格对账</b>的，装不下派生值，所以派生值只能给在这里。'
    '⚠️ <b>从下一张图起回到月度刻度。</b>')

_UNIT_NOTE = (
    '⚠️ <b>两条线不可读为可比的水平，只读形状</b>：期权那条的单位是 USD/contract、'
    '现货那条是 USD/100 shares，量纲不同，同轴画水平值是错的，所以指数化。'
    '⚠️ <code>rpc_nyse_equity_options_usd</code> 只有 <b>2 位小数</b>而量程 0.04–0.18，'
    '<b>低端一格就是 25%</b>，指数化会把这个量化误差一并放大 —— '
    '这也是量价分解那张图<b>不做期权腿</b>的同一个理由。')


def _ex_title(ex):
    return {e['n']: e.get('title', '') for e in ex}


def _ex_span(ex, tbl):
    """每张图的横轴口径与两端 —— 页尾 notes 按它逐张点名，不许写死。

    ⚠️ `from` / `to` 必须是 **Period 对象**不是标签串：下游要拿它与断点月比大小
    （`_break_coverage` 判「这张图的窗口跨没跨 2013-11」），给字符串会 TypeError。
    """
    qw = [q for q in QALL if q >= Q_FROM]
    out = {}
    for e in ex + [tbl]:
        n, k = e['n'], e.get('kind')
        if k == 'heat_matrix':
            axis, lo, hi = 'matrix', df.index[-len(e['cols'])], df.index[-1]
        elif k == 'table':
            axis, lo, hi = 'table', W_TBL[0], W_TBL[-1]
        elif n in (EX_REV, EX_RECON, EX_REVMIX, EX_BRIDGE, EX_REVTBL):
            axis, lo, hi = 'quarter', qw[0], qw[-1]
        else:
            axis, lo, hi = 'month', W25[0], W25[-1]
        out[n] = {'title': e.get('title', ''), 'axis': axis, 'from': lo, 'to': hi,
                  'stock': (n == EX_OI)}
    return out


def main():
    ex, tbl, T, bridge_check, bstats = build_page(df)

    # ── 闸门①：编号必须严格连号，且核对表号 = 最后一张图 + 1 ──────────────
    # `verify_pages.py` 里 `table.n <= max(exhibit n)` 是 **ERROR** → monthly_run
    # 判 FAIL → 28 家一起不发布；而**断号只是 WARN**、会静默上线。所以这里自己拦。
    got = [e['n'] for e in ex]
    want = list(range(EX_FIRST, EX_FIRST + len(ex)))
    if got != want:
        raise SystemExit(f'图号不连续：{got} ≠ {want}')
    if tbl['n'] != ex[-1]['n'] + 1:
        raise SystemExit(f'核对表号 {tbl["n"]} ≠ 最后一张图 {ex[-1]["n"]} + 1')

    # ── 闸门②：逐图代价的双向对账（CONTRACT §6.1 第 3 条）────────────────
    # 漏印 = 页尾那句「上面每一张都印了代价」变成假话；多记 = 替一张不存在的图背书。
    # 存量图不欠这笔债（该条只管流量），所以从应付名单里剔掉。
    # 判据是「这张图**画没画**流量同比」，不是图型 —— 按图型算会把一堆只画水平值的
    # 堆叠图与折线图也算成欠债，然后为了让账平而去补一段它根本没画的东西的代价。
    # 本页真正画同比的是两张 gs_bar 的次轴金线（`yoy` 块）。
    # 刻意排除的两类：
    #   · 存量图（月末净 OI）—— §6.1 第 3 条只管流量，存量同比是点对点，不欠这笔债；
    #   · 季度块那条右轴线 —— 它是**季度**同比（本季 vs 去年同季），与单月同比不同口径，
    #     由粒度那几条页尾说明负责，不进单月口径的账本（混进来就是拿两种口径凑一本账）。
    due = {e['n'] for e in ex
           if isinstance(e.get('yoy'), dict) and e['n'] != EX_OI}
    miss, extra = due - set(COST_LOG), set(COST_LOG) - due
    if miss or extra:
        raise SystemExit(f'逐图代价账本对不上：漏印 {sorted(miss)}、多记 {sorted(extra)}')

    kw = _stub_page(df)
    kw['cost_log'] = COST_LOG
    # `_stub_page` 漏返回这两个（它自己的自测也卡在这儿）。都从真实对象拼，不另写一份：
    #   col_zh   —— 全部 CSV 列的中文名。页尾第 ⑫ 条要给**没上页**的列也报个名字，
    #              所以不能只给 COL 里那 52 条；交易日三列在 COL 之外，单独补。
    #   agg_legs —— [(官方聚合层的腿, [它应当等于的那几条子腿]), …]，第 ⑬ 条报加总近似性。
    #              金融那条用**聚合列**而不是 rates + other_financials 相加，
    #              这样才与官方原表 "Financial futures & options" 那一行同源。
    kw['col_zh'] = dict({c: (COL[c]['zh'] if c in COL else c) for c in df.columns},
                        **{'trading_days_commod': '交易日（大宗商品）',
                           'trading_days_rates': '交易日（利率 / 金融）',
                           'trading_days_us_equities': '交易日（美股）'})
    _rl = kw['rev_legs']
    kw['agg_legs'] = [
        ({'key': 'commod_agg', 'zh': AGGS['commodities']['zh'],
          'adv': AGGS['commodities']['adv'], 'td': AGGS['commodities']['days'],
          'rpc': AGGS['commodities']['rpc'], 'f': AGGS['commodities']['div']}, _rl[:2]),
        ({'key': 'fin_agg', 'zh': AGGS['financials']['zh'],
          'adv': AGGS['financials']['adv'], 'td': AGGS['financials']['days'],
          'rpc': AGGS['financials']['rpc'], 'f': AGGS['financials']['div']}, _rl[2:4]),
    ]
    kw['ex_title'] = _ex_title(ex)
    kw['ex_span'] = _ex_span(ex, tbl)
    notes = build_notes(df, **kw)

    # `mrwin.layout_all()` 是**就地改、返回 None**（表达式形式另有 layout_all_ret）。
    # 套成 `axisfmt.fix_all(mrwin.layout_all(ex))` 会让 exhibits 变成 None ——
    # 页面上一张图都没有，而 payload_guard 不拦（None 是合法值），
    # 是 verify_pages 的「顶层缺 exhibits」那道 ERROR 抓住的。照 build/cme.py 分两步。
    mrwin.layout_all(ex)

    payload = {
        'ticker': 'ice',
        'tracker': TRACKER,
        'title': TITLE,
        'data_through': str(CUR),
        'through_label': mlab(CUR),
        'subtitle': SUBTITLE,
        'headline': _headline(),
        'brief': compose_brief(df),
        'glossary': gloss.render(compose_glossary(df), where='ice glossary'),
        'hub_line': HUB_LINE,
        'source': SRC,
        'xlabels': XL_TBL,
        'xlabels_long': XL_LONG,
        'summary': summary_block(df, CUR, PRV, YAG),
        'exhibits': axisfmt.fix_all(ex),
        'table': tbl,
        'notes': notes,
        'footer': FOOTER,
    }
    sd = source_dates.lookup(SERIES, 'ice', str(CUR))
    if sd:
        payload['source_date'] = sd

    chartscale.audit(payload['exhibits'])
    payload_guard.write_dash(OUT, payload, 'ice')
    print(f'ice: Exhibit {ex[0]["n"]}-{ex[-1]["n"]} + 核对表 {tbl["n"]}，'
          f'{len(notes)} 条页尾说明 → {OUT}')
    print(bridge_check)


if __name__ == '__main__':
    main()
