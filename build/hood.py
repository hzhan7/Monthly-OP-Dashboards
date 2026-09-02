# -*- coding: utf-8 -*-
"""Robinhood Markets (HOOD) 月度经营指标 —— 网页看板数据生成器。

把 build/build_hood.py（matplotlib / PDF）里的 Exhibit 1-27 逐张移植成 payload 里的
exhibit 对象，写出 data/hood.js。顺序、编号、标题文案、图注、口径断点全部照搬原 deck。

数据源（唯一）：series/hood.csv（月度）与 series/hood_q.csv（季度 GAAP P&L + 季度成交量）。
两份都来自 investors.robinhood.com → Monthly Metrics 的同一个 Excel；HOOD 的月度数据
按 Reg FD 挂在 IR 网站上，不走 8-K，盯 EDGAR 抓不到。

gsx 函数 → 网页 kind 的对应：
    gsx.lvl_bar        → bar_line_dual   柱（左轴）+ 右轴 y/y 线
                         （**不用 gs_bar**：gs_bar 画的是 "Prior 12mo Avg." 虚线，而本
                          deck 相对 GS 原版的第一处改动就是把滚动均线换成 y/y。用
                          gs_bar 等于把被砍掉的东西装回来。）
    gsx.stack_share    → stacked_dual
    gsx.multi_line     → lines_endlabels（费率那张退回 lines，见下）
    gsx.indexed_lines  → lines
    gsx.long_line      → lines
    gsx.bridge_bar     → bridge_bar
    gsx.implied_vs_actual → grouped_bars
    gsx.qtr_bar        → qtr_bar
    gsx.year_lines     → year_lines
    gsx.heat_matrix    → heat_matrix
    gsx.summary_table  → payload['summary']

三处与 PDF 的有意差异（引擎能力所限，均在对应图注里写明）：
  1. 费率那张 PDF 用对数轴（四条费率跨两个数量级），charts.js 没有对数轴，也不许拿
     「压在零刻度上的两条线」充数 —— 改成**按量级拆成两张**：Exhibit 13 是高档的
     Options / Crypto，Exhibit 14 是低档的 Equities / Event contracts（两档的实测区间
     由 `_rate_span()` 现算写进图注，不在任何地方写死）。因此本页从
     旧编号 14 起整体后移一位（旧 Ex14→15 … 旧 Ex27→28，核对表 28→29）。
     两张都用 kind='lines'：lines_endlabels 会对首/末点无条件调用格式器，而事件合约
     费率在 2023Q3 是缺失的（成交量四舍五入成 0.0），会直接抛 TypeError 把整页打挂。
  2. lvl_bar 的柱顶数值与 m/m 气泡：bar_line_dual 不画柱顶数值（数值在 tooltip 与表格
     视图里），m/m 改写进图注文字。
  3. 两张热力矩阵不设 full:true —— 通栏卡片会被 page.js 挂到 #lead 里，排到 Exhibit 2
     前面去，图序就乱了。半栏 12 列仍然读得清。

分位（3Y %ile）不在本文件里实现，一律调 build/pctile.py 的 cell() / why_blank()：
判据是口径，口径只能有一处定义。本页原先那份 pctile36 的「≥90% 月环比不降」代理拦不住
margin book 这类「上下波动但分位常年顶格」的行（近两年里绝大多数月份的 3Y 分位都是
100 —— 具体几个月每月都在变，所以这里不写死，要看就现算）。
"""
import datetime
import importlib.util
import json
import math
import os
import re

# 「全站同比只有单月」这句话在页面上必须带 §6.2 那五张例外 —— 不带的话，读者从本页翻到
# /exchanges-apac/ Exhibit 5（标题就写着「12 个月滚动合计的同比」）会当场撞上一句假话。
# 这一段三页共用同一份措辞，改一处要三处一起改（本仓没有跨文件的共用图注模块）。
EXC_ZH = (
    '本页与全站绝大多数页只有这一种口径 —— 页面所有者定的（CONTRACT §6 抬头引了原话）。'
    '⚠️ <b>「全站」有五张明文例外</b>（§6.2 点名保留 12 个月滚动合计口径，都不是折线：'
    '<code>/exchanges-apac/</code> 的 Exhibit 5 与 15、<code>/exchanges12/</code> 的 Exhibit 4、7、8）'
    ' —— 翻到那两页时口径与本页不同，不要跨页比高低。'
    '本页上一条 12 个月滚动合计的同比都不画。'
)

import numpy as np
import pandas as pd

import brief as B
import axisfmt
import mrwin                            # 通栏 / x 标签抽稀的裁决层，与 single.py 共用
import payload_guard
import pctile
import yoy            # 同比口径的唯一实现（build/yoy.py）：本页不再自己写一份滚动同比

D = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(D)


def _source_dates():
    """加载仓库根的 source_dates.py。`python3 build/hood.py` 时 sys.path 上只有 build/，
    裸 import 会 ModuleNotFoundError。"""
    p = os.path.join(ROOT, 'source_dates.py')
    spec = importlib.util.spec_from_file_location('source_dates', p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


SRC = 'Source: Robinhood monthly metrics and quarterly reports'

# ────────────────────────── 读数据（只从 series/ 读）──────────────────────────
df = pd.read_csv(os.path.join(ROOT, 'series', 'hood.csv'), index_col=0)
df.index = pd.PeriodIndex(df.index, freq='M')
df = df.sort_index().apply(pd.to_numeric, errors='coerce')

q = pd.read_csv(os.path.join(ROOT, 'series', 'hood_q.csv'), index_col=0)
q.index = pd.PeriodIndex(q.index, freq='Q')
q = q.sort_index().apply(pd.to_numeric, errors='coerce')

# 失败要响：窗口靠「最新月倒推」，序列断档会让 y/y 与季度合计整体错位
gaps = [(df.index[i] - df.index[i - 1]).n for i in range(1, len(df))]
if set(gaps) != {1}:
    raise SystemExit(f'series/hood.csv 月份不连续：{sorted(set(gaps))}')
# 季度表同样要连续。Exhibit 13/14/15/17 的 x 轴直接取 `[str(p) for p in q.index]`，
# 缺一季不会有任何报错，只会把 2022Q1 与 2022Q3 画成相邻两格 —— 正是 CONTRACT 规矩 3
# 禁止的假时间轴。hood_q.csv 现在有人工回填的历史段（build/basefill/hood_q_2021.py），
# 是一个人手可编辑的文件，所以这道看门狗必须和月度那道一样存在。缺的季度要**留空行**
# （每列 NaN）把时间轴铺满，不许整行不写。
qgaps = [(q.index[i] - q.index[i - 1]).n for i in range(1, len(q))]
if set(qgaps) != {1}:
    _miss = [str(q.index[i - 1] + k)
             for i in range(1, len(q)) if (q.index[i] - q.index[i - 1]).n != 1
             for k in range(1, (q.index[i] - q.index[i - 1]).n)]
    raise SystemExit(f'series/hood_q.csv 季度不连续：缺 {_miss}'
                     f'（补空行、不要补 0；步长 {sorted(set(qgaps))}）')
if len(df) < 25 or len(q) < 8:
    raise SystemExit(f'序列太短：月度 {len(df)}、季度 {len(q)}')

LATEST = df.index[-1]
LAST_Q = q.index[-1]

# ────────────────────────── 派生列（逐行照搬 build_hood.py）──────────────────────────
BRK_WONDERFI = pd.Period('2026-06', 'M')   # 收购 WonderFi，带进 ~30 万 Funded Customers
BRK_BITSTAMP = pd.Period('2025-06', 'M')   # Bitstamp 并入净流入、加密成交量与客户数
BRK_TRADEPMR = pd.Period('2026-03', 'M')   # TradePMR 顾问资产的流量并入净流入
BRK_SWEEP = pd.Period('2026-02', 'M')      # High-Yield Cash 改版，>$6bn 从 sweep 挪到 deposits
BRK_TRUMP = pd.Period('2026-07', 'M')      # Trump Account 并入总平台资产与净流入（见下）
WONDERFI_CUSTOMERS_MN = 0.3                # WonderFi 带进的 funded customers（公司披露 ~300k）

# Trump Account 断点的口径边界**只有两条序列**，第三条明确排除 —— 官方 7 月 Monthly
# Metrics Excel 的脚注原文（cache/hood_2026-07_*_July_2026_Monthly_Metrics_xlsx.xlsx）：
#   · "Starting in July 2026, Total Platform Assets include Trump Account assets
#      custodied by Robinhood."          → BK_TPA 要这条断点
#   · "Starting in July 2026, Net Deposits include Trump Account contributions."
#                                        → BK_ND 要这条断点
#   · "Funded Customers do not include Trump Accounts."
#                                        → **BK_CUST 不要这条断点**
# 三条序列一刀切全加会在客户数那张图上凭空画一条假断点，把一个口径没变的 m/m
# 涂成「不可比」。加断点和不加断点一样，都要按脚注逐条对，不能按「这个月有新闻」加。

# 每条序列受哪些断点影响。汇总表的 m/m / y/y 是否跨断点、图上画哪几条竖虚线，
# 都从这里推 —— 手写在两处必然走偏（原版就是图上画了 WonderFi、表里 m/m 照涂绿）。
BK_ND = [(BRK_BITSTAMP, 'Bitstamp'), (BRK_TRADEPMR, 'TradePMR'), (BRK_WONDERFI, 'WonderFi'),
         (BRK_TRUMP, 'Trump Accounts')]
BK_CUST = [(BRK_BITSTAMP, 'Bitstamp'), (BRK_WONDERFI, 'WonderFi')]   # 刻意不含 BRK_TRUMP，见上
BK_TPA = [(BRK_WONDERFI, 'WonderFi'), (BRK_TRUMP, 'Trump Accounts')]
BK_CRYPTO = [(BRK_BITSTAMP, 'Bitstamp acquired')]
BK_SWEEP = [(BRK_SWEEP, 'High-Yield Cash')]

tpa = df['total_platform_assets_usdbn']
nd = df['net_deposits_usdbn']
df['organic_growth_ann'] = nd * 12 / tpa.shift(1) * 100        # 年化有机增速（单月）
# 同一指标的**滚动 12 个月口径**：滚动 12 个月净流入 ÷ 12 个月前的月末平台资产。
# 分子已经是一整年的流量，不用再乘 12。比率的滚动口径必须是「分子分母各自滚动再相除」，
# 不能把 12 个月的比率加起来 —— 那样每个月的分母不同，加出来的数没有含义。
df['organic_growth_roll'] = nd.rolling(12).sum() / tpa.shift(12) * 100
df['market_gains_usdbn'] = tpa.diff() - nd                      # 恒等式残差 = 市值变动
df['tpa_change_usdbn'] = tpa.diff()
df['crypto_bitstamp_share'] = (df['adv_crypto_bitstamp_usdmn']
                               / df['adv_crypto_usdmn'] * 100)
# $bn / mn 客户 = 10^9/10^6 = 千美元/客户，本身已经是 $k，不要再乘 1000
df['assets_per_customer_usdk'] = tpa / df['funded_customers_mn']
df['dats_total_mn'] = (df['dats_equity_mn'] + df['dats_options_mn']
                       + df['dats_crypto_mn'])

# ── 费率（季度实际收入 ÷ 季度成交量）与收入桥 ──
RATE = [('Options', 'rev_options_usdmn', 'q_vol_options_mn', 'vol_options_mn'),
        ('Equities', 'rev_equities_usdmn', 'q_vol_equity_usdbn', 'vol_equity_usdbn'),
        ('Crypto', 'rev_crypto_usdmn', 'q_vol_crypto_usdbn', 'vol_crypto_usdbn'),
        ('Event contracts', 'rev_event_usdmn', 'q_vol_event_bn', 'vol_event_bn')]


def _rate(rc, vc, p):
    """某季某类的反解费率。成交量为 0 时公司仍可能报几百万收入（事件合约 2024Q4 就是
    量四舍五入成 0.0、收入 $5mn），直接相除会得到 inf 并顺着 ffill 污染整条链。"""
    v, r = q[vc].get(p, np.nan), q[rc].get(p, np.nan)
    if not (np.isfinite(v) and np.isfinite(r)) or v <= 0:
        return np.nan
    return r / v


rate_q = {}
for _nm, _rc, _vc, _mc in RATE:
    rate_q[_nm] = pd.Series({p: _rate(_rc, _vc, p) for p in q.index}, dtype=float)
# 量纲：$1bn 名义额产生 r 个 $mn，即 r/1000 的费率 = r x 10 bp。
rate_options_c = rate_q['Options'] * 100          # $mn/mn张 = $/张 → 美分/张
rate_equities_bp = rate_q['Equities'] * 10        # $mn/$bn → bp
rate_crypto_bp = rate_q['Crypto'] * 10            # $mn/$bn → bp
rate_event_c = rate_q['Event contracts'] * 0.1    # $mn/bn张 → 美分/张

# 样本外预测：每个季度用**上一季**的费率 x 本季实际成交量。
# 某一类若上季没有可用费率（业务还没起量），该类同时从预测和实际里剔除。
pred = pd.Series(index=q.index, dtype=float)
actual_txn = pd.Series(index=q.index, dtype=float)
# 每一类第一次真正进入桥（既进预测柱、也进「实际收入」柱）的季度。图注要现算：
# 「哪张图含事件合约、从哪一季起含」写死过一次就错过一次（见 Exhibit 17 图注）。
first_in_bridge = {}
# 每一季两根柱**共同**覆盖的那一组类别。Exhibit 15 图注原先写死「four asset
# classes」，而这一组是随季度变宽的（事件合约要等到有可用的上季费率才进桥）——
# 类别数只能现算，不能写死，也不能拿今天的四类去做全称断言。
cls_in_bridge = {}
for i in range(1, len(q)):
    cur_q, prv_q = q.index[i], q.index[i - 1]
    tot = act = 0.0
    got = []
    for _nm, _rc, _vc, _mc in RATE:
        r, v = _rate(_rc, _vc, prv_q), q[_vc].get(cur_q, np.nan)
        if not (np.isfinite(r) and np.isfinite(v)):
            continue
        tot += r * v
        act += q[_rc][cur_q]
        got.append(_nm)
        first_in_bridge.setdefault(_nm, cur_q)
    if got:
        pred[cur_q], actual_txn[cur_q] = tot, act
        cls_in_bridge[cur_q] = got

# 隐含月度交易收入 = 当月成交量 x 该月所属季度的费率（最新季之后沿用最后一个已知费率）
qi = pd.PeriodIndex(df.index).asfreq('Q')
imp = pd.DataFrame(index=df.index)
for _nm, _rc, _vc, _mc in RATE:
    rq = rate_q[_nm].ffill()
    rm = pd.Series([rq.get(x, np.nan) for x in qi], index=df.index).ffill()
    imp[_nm] = rm * df[_mc]
df['implied_txn_rev_usdmn'] = imp.sum(axis=1, min_count=1)


# ────────────────────────── 小零件 ──────────────────────────
def mlab(p):
    return p.strftime('%b-%y')


def L(a):
    """序列 → JSON 数组，非有限值一律 null（不许把 NaN/inf 写上线）。"""
    out = []
    for v in (a.values if hasattr(a, 'values') else a):
        try:
            fv = float(v)
        except (TypeError, ValueError):
            out.append(None)
            continue
        out.append(round(fv, 6) if np.isfinite(fv) else None)
    return out


def fnum(v, dec=1, money='', pct=False):
    if v is None or not np.isfinite(v):
        return '—'
    return money + f'{v:,.{dec}f}' + ('%' if pct else '')


def pp_txt(x):
    """gsx._pp：小变化给 1 位小数，大变化给 0 位。"""
    if not np.isfinite(x):
        return '—'
    v = x * 100
    return f'{v:+.1f}%' if abs(v) < 2 else f'{v:+.0f}%'


def yoy_of(s, pct_series=False, lag=12):
    """照搬 gsx.lvl_bar 的次轴序列：比率序列取百分点差，其余取同比；
    基数过小（< 0.15 x 中位绝对值）或两期异号时同比无意义，留空。"""
    v = np.asarray(s.values, float)
    scale = np.nanmedian(np.abs(v))
    if not np.isfinite(scale) or scale == 0:
        scale = 1.0
    out = np.full(len(v), np.nan)
    for i in range(lag, len(v)):
        a, b = v[i], v[i - lag]
        if not (np.isfinite(a) and np.isfinite(b)):
            continue
        if pct_series:
            out[i] = a - b
        elif abs(b) < 0.15 * scale or a * b < 0:
            continue
        else:
            out[i] = (a / b - 1) * 100
    return pd.Series(out, index=s.index)


def mom_of(s):
    v = np.asarray(s.dropna().values, float)
    if len(v) < 2 or v[-2] == 0:
        return np.nan
    return v[-1] / v[-2] - 1


# ────────────────── 同比口径：数值实现一律走 build/yoy.py ──────────────────
# ⚠ **2026-09 的口径改动**：本页流量类各图的右轴从「12 个月滚动合计同比」改成
# **单月同比**（当月 ÷ 去年同月 − 1）。理由是一句可核对的事实 ——
# **页面所有者要求全站统一成单月口径**（CONTRACT §6 抬头引了原话），不是「看着更
# 灵敏」那种 §6.1 第 3 条点名禁止的说法。改完之后 CONTRACT §6 本身也翻了面：
# §6.1 第 1 条现在写的就是「流量序列用单月同比，走 yoy.mom_yoy(s, yoy.FLOW)」，
# 并把「柱与线取自同一列、读者能自己核对」列为它的决定性好处；
# §6.2 那张「所有者点名保留滚动」的例外表里**没有本页**。
# 要照办的是 §6.1 第 3 条：每一张画**流量**同比的图都得印出单月口径的**代价**
#（该条自己把范围限定在流量：只有流量列换了口径，存量与比率没有可对照的滚动口径）
# （逐月标准差、相邻月最大跳变带月份、符号相反的月份数），由 mom_cost_note() 现算。
# 图例名 / ylab2 里带「单月」（tools/check_yoy_caliber.py 的 R4 只认
# title / ylab2 / legend / 序列名这四处）。
#
# 单月口径的代价不隐瞒，也不复述：它的分母是**去年那一个月**，流量的月度分布本身带
# 季节性与时点噪音（发薪日、加密行情的爆发月、并表落在哪一个月），分母越小同一笔
# 绝对变化被放大得越狠。⚠ 具体的标准差倍数、相邻月最大跳变、符号相反的月份数
# **一律由 mom_cost_note() 拿本序列现算写进图注** —— 注释里写死的读数每个月都会过期
# （窗口 2026-08 放宽那一次已经让上一版注释里的一组数字全部对不上了）。
# 滚动口径仍然算，但只作**对照**（roll_yoy_of），图上不画。
#
# 存量与比率**不受这次改动影响**：它们本来就是单月口径，而且是算术上唯一/唯一合法的
# 那一个，不是选出来的。
# ⚠ 一条更正（2026-08-07，仍然成立）：早先本文件写过「存量不许做滚动合计，所以只能
# 点对点」。**后半句是假的**：Σ12/Σ12′ 里的除数约掉，12 个月滚动**合计**比恒等于
# 12 个月滚动**均值**比（共享模块 build/yoy.py 实测两者差 2.3e-14），而「去年一整年的
# 平均平台资产 vs 前年」是一个真实存在、可以核对的量。**错的只是「合计」这个名字**。
# 所以：存量**可以**平滑（走 yoy.ttm_mean_yoy，文案必须写「12 个月均值同比」），
# 本页仍保留点对点，但理由必须是**本序列实测**出来的（见 stock_note）。
# 比率序列另说 —— 12 个月的比率做算术平均没有意义，yoy.ttm_mean_yoy 对 RATIO
# 直接抛 CaliberError，那是一条真的硬约束（见 ratio_note）。
def mom_yoy_of(s):
    """单月同比（%）—— 流量类**图上画的就是这一条**。实现走共享模块，本页不另写一份。"""
    return yoy.mom_yoy(s, yoy.FLOW)


def roll_yoy_of(s):
    """12 个月滚动合计同比（%）—— 流量类的**对照**口径，2026-09 起本页不再画它。

    留着不是摆设：mom_cost_note() 要拿它量出「换成单月口径的代价是多少」，
    页尾口径说明与 Exhibit 1 表注里的并排读数也来自它。数值实现走共享模块。
    """
    return yoy.ttm_yoy(s, yoy.FLOW)


def mean_yoy_of(s):
    """12 个月滚动**均值**同比（%）—— 存量类唯一说得通的平滑口径。

    数值上与滚动合计比完全相同（除数约掉），差别只在**说法**：对存量，
    「12 个月合计」不指代任何真实的量，「去年一整年的平均余额」才是。
    本页只拿它做反事实对照，图上画的仍是点对点。
    """
    return yoy.ttm_mean_yoy(s, yoy.STOCK)


def flow_stats(s, idx):
    """**流量列**的两口径实测对比 —— 统计量整段由 `yoy.caliber_diff()` 出，本页不自己算。

    CONTRACT §6.4 白纸黑字：「`yoy.caliber_diff()` 已经先取交集再比，别自己写」。
    对齐、逐月标准差、相邻月最大跳变、符号相反的月份，四样全部取自它返回的那一个
    dict —— 与 `build/single.py::mom_cost_zh()`、`build/yoy.py::describe()` 拿的是
    同一个来源，所以页面上这三处印出来的「逐月标准差」是同一个统计量的同一个定义。

    ⚠ caliber_diff 的相邻月跳变只量「相邻两个月**都在交集里**」的那些对（它的
    docstring 明写：跨过一个空洞的「跳变」不是跳变）。下面 `caliber_stats()` 里那份
    自写的 `_jump` 做不到这一点 —— 交集有洞时它会把洞两侧接起来当成一次跳变。
    这是流量列改走 caliber_diff 的第二个理由，不只是为了统一估计量。

    caliber_diff 不返回读数区间与当期并排值（它是诊断器，不是取数器），这两样在下面
    按它给出的**同一批月份**补齐 —— 补的是取值，不是统计量。
    """
    d = yoy.caliber_diff(s, yoy.FLOW, win=list(idx))
    keep = list(d['months'])
    if len(keep) < 3:
        return None
    A = mom_yoy_of(s).loc[keep].astype(float)
    B = roll_yoy_of(s).loc[keep].astype(float)

    def _at(j):
        """caliber_diff 的 (跳变值, 前一月, 后一月) → 本页图注要的 (值, 「X → Y」)。
        CONTRACT §6.1 第 3 条要求带月份 —— 一个光秃秃的「最大跳变 N pp」读者没法
        回到图上去核，带上月份就能。"""
        return (float(j[0]), f'{mlab(j[1])} → {mlab(j[2])}') if j else (float('nan'), '')

    _jm, _jm_at = _at(d['maxjump_mom'])
    _jr, _jr_at = _at(d['maxjump_ttm'])
    return {'n': d['n'], 'sd_m': d['std_mom'], 'sd_r': d['std_ttm'],
            'jump_m': _jm, 'jump_r': _jr, 'jump_m_at': _jm_at, 'jump_r_at': _jr_at,
            'flips': [(mlab(p), float(a), float(b)) for p, a, b in d['opposite']],
            'lo_m': float(A.min()), 'hi_m': float(A.max()),
            'cur_m': float(A.iloc[-1]), 'cur_r': float(B.iloc[-1]),
            'first': keep[0], 'last': keep[-1]}


def caliber_stats(mono, roll, idx):
    """两种口径的实测对比。返回 None 表示可比月份不足。

    ⚠ **必须先对齐到两种口径都算得出的同一批月份**：滚动口径天然少掉头 12 个月，
    不对齐就是拿两个不同样本比波动，样本效应会伪装成口径效应。

    ⚠ **为什么这一份没有并进 `yoy.caliber_diff()`**：它只对 `kind=FLOW` 做两口径对比，
    其余两种 kind 的滚动侧一律返回 None（存量做滚动**合计**非法、比率连合法的对照
    口径都没有）。而本页要比的另外两对恰恰不是 FLOW：
      · 存量对 12 个月滚动**均值**同比（`stock_note`，走 yoy.ttm_mean_yoy）；
      · 由流量推导的比率，对「分子分母各自滚动 12 个月再相除」的那条比率
        （`lvl(pct_series=True, roll_src=...)`）—— 那条不是 12 个月比率的算术平均，
        共享模块里没有它。
    所以这两对只能在这里算。**但估计量必须与共享模块同一个**：下面用的是样本标准差
    （`ddof=1`）。共享模块那边写成 `np.nanstd(x, ddof=1)`，这里写成 pandas 的
    `.std(ddof=1)` —— keep 已经把非有限值滤干净，两种写法逐值相同（实测差 0.0）——
    这里曾经写的是 `ddof=0`，于是同一个词「逐月标准差」在站上有了两种定义。
    两者之比恒为 sqrt((n−1)/n)，与数据无关 —— 举个算得出来的例子：n = 44 个月时
    sqrt(43/44) = 0.9886，ddof=0 印出来的数比 ddof=1 小 1.1%。
    纯流量列不走这里，走上面的 flow_stats()。
    """
    keep = [p for p in idx if p in mono.index and p in roll.index
            and np.isfinite(mono.loc[p]) and np.isfinite(roll.loc[p])]
    if len(keep) < 3:
        return None
    A, B = mono.loc[keep].astype(float), roll.loc[keep].astype(float)

    def _jump(x):
        """相邻月最大跳变 **与它落在哪两个月**。CONTRACT §6.1 第 3 条要求带月份 ——
        一个光秃秃的「最大跳变 N pp」读者没法回到图上去核，带上月份就能。"""
        if len(x) < 2:
            return float('nan'), ''
        d = np.abs(np.diff(x.values))
        i = int(np.argmax(d))
        return float(d[i]), f'{mlab(keep[i])} → {mlab(keep[i + 1])}'

    _jm, _jm_at = _jump(A)
    _jr, _jr_at = _jump(B)
    return {'n': len(keep), 'sd_m': float(A.std(ddof=1)), 'sd_r': float(B.std(ddof=1)),
            'jump_m': _jm, 'jump_r': _jr, 'jump_m_at': _jm_at, 'jump_r_at': _jr_at,
            'flips': [(mlab(p), float(A.loc[p]), float(B.loc[p]))
                      for p in keep if A.loc[p] * B.loc[p] < 0],
            'lo_m': float(A.min()), 'hi_m': float(A.max()),
            'cur_m': float(A.iloc[-1]), 'cur_r': float(B.iloc[-1]),
            'first': keep[0], 'last': keep[-1]}


def mom_cost_note(st, unit='%'):
    """「本图的次轴为什么是单月同比、代价是多少」——数字全部来自本页自己的序列。

    CONTRACT §6：全站同比只有单月一种，页面所有者定的（§6 抬头引了原话），
    页上一条 12 个月滚动合计的同比都不画。§6.1 第 3 条要求**每一张画流量同比的图**
    都印出单月口径的代价，用这条序列自己实测，报三样：逐月标准差、相邻月最大跳变
    （**带月份**）、两种口径符号相反的月份数 —— 这里三样都给。
    同一条还明令**不许写「看着更灵敏」**，也**不许说「滚动口径更好但我们没用」**：
    图注要说的是代价，不是替页面上不存在的那条线背书。所以下面只报数。
    对照那一侧（12 个月滚动合计同比）本页只算不画。

    ⚠ **「同源」这个词以前在这里是含混的，现在把两件事分开写**：
      · **措辞**与 build/single.py 的 mom_cost_zh()、build/yoy.py 的 describe() 同源
        —— 三处照着 §6.1 第 3 条同一份要求写，句子结构一样，但字是各写各的。
      · **统计量**：`st` 从哪儿来，决定它同不同源。纯流量列（`pct_series=False`）
        走 `flow_stats()`，数字整段出自 `yoy.caliber_diff()`，与上面那两处**同一个
        来源**；由流量推导的比率（`pct_series=True`，对照侧是 roll_src 那条自己滚出来
        的比率）caliber_diff 根本不比，走 `caliber_stats()` 自己算，但用的是同一个
        估计量（样本标准差 ddof=1）。
      上一版这里只写「措辞……同源」一句，读起来像两者都同源，而当时 caliber_stats
      用的是 ddof=0 —— 措辞同源、统计量不同源，那句话因此是半句真话。
    """
    how = ('本月读数 − 去年同月读数，出<b>百分点差</b>' if unit == 'pp'
           else '本月 ÷ 去年同月 − 1')
    head = (f'右轴绿线为 <b>单月同比</b>（{how}）。'
            + EXC_ZH +
            f'§6.1 第 1 条同时给了它一个可核对的好处：<b>柱与线取自同一列</b> —— '
            f'拿这根柱和 {yoy.LAG} 根柱之前那根一比，就是线上这一点，读者能自己验算。')
    if st is None:
        return head + '本序列两种口径都算得出的月份不足 3 个，此处暂不给代价数字。'
    ratio = st['sd_m'] / st['sd_r'] if st['sd_r'] else float('nan')
    t = (head + f'<b>代价按 §6.1 第 3 条用本序列自己实测印出来</b>：把两种口径'
         f'<b>对齐到同一批月份</b>后（{mlab(st["first"])}–{mlab(st["last"])}，'
         f'{st["n"]} 个月；滚动那一侧只作对照、本页不画），'
         f'单月同比逐月标准差 {st["sd_m"]:,.1f}pp，'
         f'滚动口径 {st["sd_r"]:,.1f}pp（放大 {ratio:,.1f} 倍），'
         f'相邻月最大跳变 {st["jump_m"]:,.0f}pp（{st["jump_m_at"]}）'
         f' vs {st["jump_r"]:,.0f}pp')
    if st['flips']:
        w = max(st['flips'], key=lambda f: abs(f[1] - f[2]))
        t += (f'，{len(st["flips"])} 个月两种口径<b>符号相反</b>'
              f'（{"、".join(f"{m} 单月 {a:+,.0f}{unit} / 滚动 {b:+,.0f}{unit}" for m, a, b in st["flips"])}）'
              f'—— 最极端的 {w[0]} 相差 {abs(w[1] - w[2]):,.0f}pp。')
    else:
        t += '，本窗口内两种口径没有符号相反的月份。'
    t += (f'当期并排：单月 {st["cur_m"]:+,.1f}{unit}、滚动 {st["cur_r"]:+,.1f}{unit}'
          f'（差 {abs(st["cur_m"] - st["cur_r"]):,.0f}pp）。柱本身是当月读数，没有改。'
          f'⇒ <b>这条线要连着柱高一起读</b>：低基数月份它会被放大，'
          f'单看它挑月份能把结论说成两个方向。')
    return t


def stock_note(s, idx, what):
    """**存量**序列保留点对点（单月）同比的理由 —— 事实要说对，数字要现算。

    这段被更正过一次。旧版写的是「12 个月末值相加不是任何东西，所以存量只能
    点对点」，前半句对、后半句错：存量确实可以平滑，走的是 12 个月滚动**均值**同比
    （yoy.ttm_mean_yoy），它回答「去年一整年的平均余额 vs 前年」，是个真实的量。
    """
    st = caliber_stats(yoy.mom_yoy(s, yoy.STOCK), mean_yoy_of(s), idx)
    base = (f'右轴仍是<b>点对点（单月）同比</b>：{what}是<b>期末存量</b>。'
            '存量并非不能平滑 —— 合法的平滑口径是 <b>12 个月滚动均值同比</b>'
            '（去年一整年的平均余额 vs 前年；数值上等同于滚动合计比，除数约掉了），'
            '<b>但不能叫「12 个月合计同比」</b>：12 个月末余额相加不指代任何真实的量。'
            '本图不换的理由不是「不能换」，是实测下来换了没有收益：')
    if st is None:
        return base + '本序列两种口径都算得出的月份不足 3 个，暂时给不出对照数字。'
    ratio = st['sd_m'] / st['sd_r'] if st['sd_r'] else float('nan')
    return (base + f'对齐到同一批月份后（{st["n"]} 个月），点对点同比标准差 '
            f'{st["sd_m"]:,.1f}pp、12 个月均值同比 {st["sd_r"]:,.1f}pp（{ratio:,.2f} 倍），'
            f'相邻月最大跳变 {st["jump_m"]:,.1f}pp vs {st["jump_r"]:,.1f}pp，'
            f'两种口径符号相反的月份 {len(st["flips"])} 个'
            + ('（一个都没有）' if not st['flips'] else '')
            # ⚠ 这里原先无条件写「均值口径更平滑」—— 同一句话里刚印出来的那两个标准差
            # 当场就能证伪它：本页有存量图实测下来是均值口径更吵。所以哪个更平滑一律由
            # 下面这个三分支按 st 现判，不写死结论、也不在注释里存具体读数
            # （上一版这里存了两张图的 pp 数当例子，改一次估计量就全部过期）。
            # build/lpla.py 的同一段（`verdict`）早就是这么写的，本页漏改了一处。
            + ('。<b>均值口径在这条序列上反而更吵</b>，而且按构造滞后约半年、'
               if st['sd_r'] > st['sd_m'] else
               '。两种口径的波动幅度实测相同，而均值口径还按构造滞后约半年、'
               if st['sd_r'] == st['sd_m'] else
               '。均值口径确实更平滑，但按构造滞后约半年、')
            + '回答的是另一个问题'
            '（「去年一整年的平均水平」而非「现在相对去年此刻」）；'
            '而存量的分子分母都是时点数、不含日历效应，本来就不像流量那样被小分母放大。'
            '噪声用轴范围解决。')


# ── 「本身是两条序列相除、却按存量处理」的图：在这里报到，并当场过一道数值检验 ──
# ⚠ 分组判据不是「是不是相除」，而是「12 个月的算术平均代不代表得了那一年」：
#   占比／费率的分母逐月不同，算术平均不指代任何真实的量（那是 ratio_note 那条硬约束）；
#   而分子分母同为存量、量纲同源时，均值口径与分母加权口径只差一个**可以量出来的小量**。
#   所以这里不写结论、写检验：差多少现算，超过阈值就停机 —— 那时「按存量处理」这句话
#   就不成立了，页尾 (2) 那一段也会跟着说假话。
#   （hood 的 mean_yoy_of() 对所有非 pct_series 的图一律传 yoy.STOCK，绕开了共享模块
#   对 RATIO 的拒绝；这道检验就是那次绕开的对价，不是白绕。）
RATIO_EQUIV_MAX_PP = 3.0     # 判据阈值（政策常量，不是实测值）；实测差额由下面现算并印出
_QUOT_STOCK = {}


def quot_stock(n, num, den, zh):
    """两个同源存量之比、按存量处理的图在这里报到。返回实测的口径差（pp）。"""
    r = num / den
    mr = r.rolling(12, min_periods=12).mean()
    a = (mr / mr.shift(12) - 1) * 100                    # 页面印的：比率的算术平均同比
    rw = num.rolling(12, min_periods=12).sum() / den.rolling(12, min_periods=12).sum()
    b = (rw / rw.shift(12) - 1) * 100                    # 硬约束要求的：分母加权同比
    gap = float(pd.concat([a, b], axis=1).dropna().diff(axis=1).iloc[:, -1].abs().max())
    if not np.isfinite(gap) or gap > RATIO_EQUIV_MAX_PP:
        raise SystemExit(
            f'Exhibit {n}（{zh}）按存量处理的前提不再成立：12 个月均值口径同比与分母'
            f'加权口径同比最大差 {gap:.2f}pp，超过 {RATIO_EQUIV_MAX_PP:g}pp —— '
            '页尾同比口径 (2) 那一段会因此说假话')
    _QUOT_STOCK[n] = (zh, gap)
    return gap


def ratio_note(what, extra=''):
    """**比率**序列保留点对点同比的理由 —— 这一条是硬约束，不是选择。

    比率不许做 12 个月滚动均值：12 个月的占比做算术平均没有意义（每个月的分母不同），
    要「一年的平均占比」得用分母加权（Σ分子 ÷ Σ分母），那需要两条序列。
    共享模块 build/yoy.py 的 ttm_mean_yoy() 对 RATIO 直接抛 CaliberError。
    """
    return (f'右轴是<b>点对点（单月）同比的百分点差（pp）</b>。{what}是<b>比率</b>，'
            '12 个月滚动均值同比在这里是<b>非法</b>口径：把 12 个月的比率做算术平均没有意义'
            '（每个月的分母不同），要「一年的平均水平」必须用分母加权（Σ分子 ÷ Σ分母），'
            '那要两条序列而不是这一条 —— 共享模块 <code>build/yoy.py</code> 的 '
            '<code>ttm_mean_yoy()</code> 对比率序列直接抛 <code>CaliberError</code>。'
            '所以比率只有点对点这一个口径，差异一律用 pp / bp。' + extra)


BRK_DRAWN = {}          # 断点 period → 真正画出竖虚线的 exhibit 编号，口径说明由它现生成


def breaks_for(n, index, items):
    """把 [(period, label), …] 折成该图窗口里的 break_at / break_label。

    返回 (payload 片段, 人话短句)。窗口盖不到的断点自动省略，一个都盖不到就返回
    ({}, '') —— 图上不画、图注也不会声称画了。**绝不因为断点滚出窗口而报错退出**：
    13 个月与长窗口每月往前滚，断点滚出去是必然事件，硬失败等于让这一页永久停更
    （build/lpla.py 现在就是这个毛病）。写法照 build/schw.py 与 build/wealth.py。
    """
    lst = list(index)
    hit = [(lst.index(p), lab, p) for p, lab in items if p in lst]
    if not hit:
        return {}, ''
    for _i, _lab, p in hit:
        BRK_DRAWN.setdefault(p, []).append(n)
    seg = '、'.join(f'{lab}（{p}）' for _i, lab, p in hit)
    return ({'break_at': [i for i, _l, _p in hit],
             'break_label': [l for _i, l, _p in hit]}, seg)


def drawn_on(period):
    """某个断点最终画在哪几张图上；一张都没有返回 ''。给口径说明用。"""
    ns = sorted(set(BRK_DRAWN.get(period, [])))
    return '、'.join(f'Exhibit {x}' for x in ns)


def spans(period, lo, hi):
    """断点 period 是否落在比较区间 (lo, hi] 内 —— 即这一格的两端跨了口径变化。
    断点语义是「从这一期起与左侧不可比」，所以 period == lo 时两端同在右侧，可比。"""
    return lo < period <= hi


MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
       'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

#: 时序图窗口的左端。2026-08-18 从「近 25 个月」改成「2016-01 起」，全站统一
#: （build/single.py 的 WIN_FROM、cboe / cme / hkex / cost 的同名常量、msci 的 WIN0）。
#: 本页序列 2026-08-19 从 2023-04 起回填到 **2021-01**（build/basefill/hood_2021.py，
#: 源是 IR 站上还挂着的最早几份 Earnings Supplement）。2021-01 是天花板：公司 2022-04
#: 才开始月度披露、首期回填 12 个月，更早只在 S-1/10-Q 且不是月度粒度。
#: 所以 WIN_FROM 在这一页实际拿到的仍是序列自己的全长 —— 只往右让、不往左借。
#: ⚠ 回填段的**列不齐**（老版式没有 ADV / Cash and Deposits / Bitstamp / Event 那几行），
#: 各图的左端因此不再统一：一律由 mrwin.resolve() 按各自序列裁，见 lvl() 的 docstring。
#: 变量名保留 W25 是因为它散落在几十处，改名的 diff 会淹没实质改动。
WIN_FROM = '2016-01'
_I0 = next((i for i, p in enumerate(df.index)
            if f'{p.year}-{p.month:02d}' >= WIN_FROM), 0)
W25 = df.index[_I0:]
# W15/XL15 已删（2026-08-19）：只有 Exhibit 9 / 25 用过，两张都是从 deck 抄来的「近 15 个月」
# 漂移窗口 —— 今天它正好含 1 个 Bitstamp 并表前的月份，下个月一个都不剩。两张现在都跟着
# 各自序列自己的可得历史走（左端由 mrwin.resolve() 裁），常量留着只会诱人再写死一次。
W13 = df.index[-13:]        # not-a-window: 只有页尾核对表的行数用它，表标题里现算自报
XL25 = [mlab(p) for p in W25]
XL_LONG = [mlab(p) for p in df.index]
XQ = [str(p) for p in q.index]

EX = []


def xstep_for(n):
    """x 标签步长。

    ⚠ `mrwin.layout()` 也会抽稀，但它**只在 payload 没写 xstep 时才动手**，而本页每张
    时序图都显式写了 xstep —— 所以长轴的编辑上限（`mrwin.MAX_XLABS`，只对 n > 60 生效）
    必须在这里跟上。序列回填到 2021-01 之后 x 轴从 40 期变成 67 期，还照写 xstep=2
    就是 34 个 90° 竖排标签，一堵字墙。抽的是标签不是数据点。
    """
    if n <= 14:
        return 1
    if n > mrwin.LONG_AXIS_N:
        return max(2, math.ceil(n / mrwin.MAX_XLABS))
    return 2


# ── 右轴同比口径的**实际**去向：由 lvl() 现填，页尾口径说明照它生成 ──
# 手写「Exhibit 3、7、8 的右轴画了同比线」这种名单必然烂掉：y/y 覆盖率不够时 lvl()
# 会把整张图退成 bars_labeled（连线都没有），而名单不会自己知道。
# 值域：'flow'（流量类，2026-09 起按所有者指令统一画单月同比）/ 'mono'（存量与比率，
# 单月是它们算术上唯一/唯一合法的口径）/ None（本轮没画出同比线）。
# 两类画出来的都是**单月**读数，分开记是因为**为什么是单月**的理由不同，页尾要分开说。
AXIS_KIND, AXIS_ZH = {}, {}
# ⚠ 这个集合收的是 `pct_series=True` 的图，也就是**序列本身以 % 计量**（占比／费率）
#   的那几张 —— 判据是计量单位，不是「是不是两条序列相除」。别把它叫「比率」：页尾
#   (2) 那一段就是因为用「比率」当分组判据，写出「Exhibit 25 不同：它是比率」，
#   而同一段话里 Exhibit 21 自己就叫「户均资产（两个期末数之比）」—— 被本页当场证伪。
#   分子分母同为存量、量纲同源的那种「之比」走 `quot_stock()`，在那里过数值检验。
AXIS_RATIO = set()      # pct_series（以 % 计量）的图；页尾口径说明照它现算，不手数

# 图注与口径说明里被点名引用的 Exhibit 编号集中在这里。上一版把费率图拆成两张时，
# 散在正文里的「Exhibit 14」「Exhibit 21」「Exhibit 22 / 25」会集体指错一张图，
# 而那种错没有任何自动化能发现 —— 所以引用一律走常量，不写字面数字。
N_RATE_HI, N_RATE_LO = 13, 14          # 费率：高量级档 / 低量级档
N_BRIDGE_TEST, N_IMPLIED = 15, 16      # 样本外检验 / 隐含交易收入
N_HIST = 22                            # 总平台资产全历史
N_QTR_ND, N_QTR_DATS = 23, 26          # 季度净流入 / 季度 DATs
N_TABLE = 29                           # 末尾核对表

# y/y 线要画出来，至少得有这么高比例的点是可比的。
# 事件合约（Exhibit 10）窗口内只有一小撮月份有可比基数（确切几个由该图图注现算 ——
# 窗口一放宽写死的数就作废），画出来是「两段近乎垂直的竖线加一段贴地的直线」，
# 还顺带把右轴撑到几千个百分点 —— 除了「涨了很多」读不出别的，却挡住了柱子。
# 这不是排版偏好：一条大部分是断口的折线本来就不是一条序列。
# 用覆盖率而不是「量程多宽」当判据，是因为它会自己恢复：等事件合约有满 12 个月的
# 真实基数，覆盖率自然过线，线就回来了，不用有人记得回来改这里。
YOY_MIN_COVER = 0.60


def lvl(n, s, title, *, win=None, fmt='f1', yfmt=None, ylab='', note='', pct_series=False,
        breaks=(), show_mom=False, bar_name='Monthly', yoy_drop_note='', flow=True,
        roll_src=None, what='', ratio_extra='', left_zh=''):
    """gsx.lvl_bar → bar_line_dual：浅蓝柱（左轴水平值）+ 右轴 y/y 线。

    **右轴一律画单月同比**（2026-09 起，按页面所有者的指令全站统一），
    `flow` 只决定**为什么是单月**这句话怎么写：
    `flow=True`（流量类）→ mom_cost_note：口径是所有者指定的，代价（与滚动口径的
    标准差之比、相邻月最大跳变、符号相反的月份）由本序列现算印出；
    `flow=False` + `pct_series=True` → ratio_note（比率不许做滚动均值，硬约束）；
    `flow=False` + 其余 → stock_note（存量可以做滚动**均值**，本图不做的理由由实测给出）。
    口径判断只在调用点写一次，标签、图注、实测对比全部由这里按同一个开关生成，
    这样「图例上写的口径」和「实际算的口径」不可能分叉。

    `roll_src` 给**由流量推导的比率**用（本页只有年化有机增速一条）：它的滚动口径
    不是「把 12 个月的比率平均」，而是分子分母各自滚动 12 个月再相除
    （见 organic_growth_roll）—— 那样算出来的是真实的「过去一年的有机增速」，
    与「12 个月比率的算术平均」不是一回事，后者才是被 yoy.py 禁掉的那个。
    2026-09 之后它**不再进图**，只作 mom_cost_note 的对照那一侧。

    y/y 的可比点覆盖率低于 YOY_MIN_COVER 时，整张图退成单轴的 `bars_labeled`
    （深蓝柱 + 每柱数值），而不是「保留 bar_line_dual 但不给 ex.line」——
    引擎的 bar_line_dual 是**硬双轴**，无条件取 ex.line.values，缺了会抛 TypeError
    把整页打挂（这条路踩过一次：Exhibit 10 去掉 y/y 后页面只渲染到第 9 张卡）。
    退化写在这里而不是在调用点各写各的，是为了让以后任何一条新序列都自动走这条安全路径。

    ⚠ **左端不由本函数拍板，交给 `mrwin.resolve()`（只调用，不改）。**
    2026-08-19 序列回填到 2021-01 之后这条第一次咬人：老版式的 Earnings Supplement
    没有 ADV 那一节、没有 Cash and Deposits、没有 Bitstamp / Event 拆分，
    所以 `adv_*` 等列的前 24 期全是 null。柱图能吃 null（引擎按缺格处理），但
    ①左端会挂一大截空柱，②`cover` 被 null 拖到 60% 以下，整张图会误退成
    `bars_labeled`，把本来画得出的 y/y 线丢掉。裁到「这条序列自己第一个有值的月」
    两个问题一起消失，而且不需要在每个调用点各写一遍。
    `left_zh` 是这一段的人话理由（写进图注）；不给就用一句通用的。
    """
    # win=None（默认）= 跟着 W25（现在是 WIN_FROM 起的全窗口）走。
    # 原默认写死 25，窗口一变就会出现「values 长 25、x 轴 40 格」——
    # build/verify_pages.py 会拦（「尾部会静默变成缺失」），但默认值本身就该跟着窗口。
    win = win or len(W25)
    d = s.iloc[-win:]   # data-window: win = 实参或 len(W25)；左端随后交 mrwin.resolve() 再裁
    # 单月同比 mono：流量类走共享模块 yoy.mom_yoy（口径的唯一实现）；比率取**百分点差**，
    # 也走共享模块（yoy.mom_yoy(kind=RATIO) 的定义就是 v − v.shift(12)）——
    # 这里原先手写 `s - s.shift(12)`，数值一样，但那是同一个口径的第二份实现。
    # 存量仍走本页的 yoy_of()（它比 mom_yoy 多一道近零基数护栏，这次改动不碰存量）。
    # rl 是**对照**那一侧（滚动口径），2026-09 起只进图注、不进图。
    mono = (yoy.mom_yoy(s, yoy.RATIO) if pct_series
            else (mom_yoy_of(s) if flow else yoy_of(s)))
    if pct_series:
        rl = (yoy.mom_yoy(roll_src, yoy.RATIO) if roll_src is not None else mono)
    else:
        rl = roll_yoy_of(s)
    ys = mono.iloc[-win:]   # data-window: 同上，跟着柱那一刀
    cal = 'y/y (pp, 单月, RHS)' if pct_series else 'y/y (单月, RHS)'

    # ── 左端裁决（见 docstring）：柱是主腿，y/y 是派生腿；bar_line_dual 不属 DENSE，
    #    所以 resolve 只把左端推到**柱自己第一个有值的月**，派生腿的前导 null 交给
    #    引擎断笔。`w.why` 里那句「y/y 比柱短 N 期」也由它生成，本页不再手写。──
    _labels = [mlab(p) for p in d.index]
    _lag = '单月同比要 12 个月历史'
    _legs = [mrwin.Leg('bar', bar_name, L(d), 'primary'),
             mrwin.Leg('yoy', cal.replace(', RHS', ''), L(ys), 'derived', _lag)]
    _w = mrwin.resolve('bar_line_dual', _legs, _labels, 0)
    left_txt = ''
    if _w.start:
        left_txt = (f'<b>本图左端截在 {_labels[_w.start]}，不是序列起点 {_labels[0]}</b>：'
                    + (left_zh or '官方那一行更早的月份根本没有印过')
                    + '，左边那一段补零或补上一期的值都能让图画满，但那是画一个数据里'
                      '不存在的点，本页不做。')
    d, ys = d.iloc[_w.start:], ys.iloc[_w.start:]
    labels = _labels[_w.start:]
    win = len(d)

    line_fmt = ('pp1' if pct_series and win <= 15 else 'pp0') if pct_series else 'pct0'
    txt = note
    mtxt = None
    if show_mom:
        mv = ((d.values[-1] - d.values[-2]) if pct_series else mom_of(s))
        mtxt = (f'{mv:+.1f}pp m/m' if pct_series else pp_txt(mv) + ' m/m')
        txt = (txt + ' ' if txt else '') + f'Latest reading: {mtxt}.'
    ok = np.isfinite(np.asarray(ys.values, float))
    cover = float(ok.sum()) / len(ok) if len(ok) else 0.0
    # 这张图的右轴最终**画了什么** —— 页尾的口径名单照它生成，不手写（见 AXIS_KIND）。
    AXIS_ZH[n] = what or title
    AXIS_KIND[n] = (('flow' if flow else 'mono') if cover >= YOY_MIN_COVER else None)
    if pct_series:
        AXIS_RATIO.add(n)
    if cover >= YOY_MIN_COVER:
        if flow:
            # 纯流量列的统计量走共享模块（CONTRACT §6.4：caliber_diff 已经先取交集再比，
            # 别自己写）；pct_series 那一支比的是「本页自己滚出来的那条比率」，
            # caliber_diff 不比这一对，只能自己算 —— 两条路的估计量相同，见两个函数。
            _st = (caliber_stats(mono, rl, d.index) if pct_series
                   else flow_stats(s, d.index))
            why = mom_cost_note(_st, 'pp' if pct_series else '%')
        elif pct_series:
            why = ratio_note(what or title, ratio_extra)
        else:
            why = stock_note(s, d.index, what or title)
        txt = (txt + ' ' if txt else '') + why
        ex = {
            'n': n, 'kind': 'bar_line_dual', 'title': title,
            'xlabels': labels, 'xstep': xstep_for(win),
            'fmt': fmt, 'ylab': ylab,
            'ylab2': cal.replace(', RHS', '').replace('(', '(').strip(),
            'bar': {'name': bar_name, 'color': 'BLUE', 'values': L(d), 'yfmt': yfmt or fmt},
            'line': {'name': cal, 'color': 'GREEN', 'values': L(ys), 'yfmt': line_fmt},
        }
    else:
        ex = {
            'n': n, 'kind': 'bars_labeled', 'title': title,
            'xlabels': labels, 'xstep': xstep_for(win),
            'values': L(d), 'fmt': fmt, 'yfmt': yfmt or fmt, 'label_fmt': fmt,
            'ylab': ylab, 'legend': f'{title} ({ylab})' if ylab else title,
        }
        if mtxt:
            ex['annot'] = f'{mlab(d.index[-1])}: {mtxt}'
        fin = ys.dropna()
        rng = (f'and those readings run from {fin.min():+,.0f}% to {fin.max():+,.0f}%. '
               if len(fin) else '')
        # 两种口径的实测读数区间一起印出来，好让人相信这不是懒。
        # ⚠ 结论那一句**必须跟着实测走**：这段原先无条件写「两种口径都救不了这条序列
        # …滚动口径在这里反而更吵…近零基数的序列不该画同比」，而它同一句话里印出来的
        # 标准差当场就能证伪 —— 有几张图的滚动口径比单月稳得多，也谈不上近零基数，
        # 那几张不画线的真实理由是**可比点不够**（窗口左端那一段没有上年同月基数），
        # 与噪音无关。⚠ 上一版这里还举了「Exhibit 7 是 14pp vs 单月 45pp、Exhibit 8 是
        # 6pp vs 17pp」当例子 —— 2026-09 改单月口径之后这两张的可比点覆盖率过线、
        # 已经画出线来了，不再走这条分支，例子因此删掉：注释里点名具体图号，图一改
        # 就成了假话，而没有任何自动化会发现。
        # ⚠ 标准差这一对**必须在对齐后的同一批月份上量**（2026-09 更正）：这里原先拿
        # 两条各自 dropna 的序列直接比 std，而滚动侧天生少掉头 12 个月 —— 比的是两个
        # 不同样本，样本效应会伪装成口径效应，正是本文件别处反复警告的那个错。
        # 现在对齐与统计量都交给上面那两个函数（纯流量列走 yoy.caliber_diff），
        # 估计量因此与页面上其它每一处「逐月标准差」是同一个（样本标准差 ddof=1；
        # 这里原来写的是 ddof=0，同一个词两种定义）。
        # 区间与点数仍按各自口径报：那两个数回答的是「这条线画出来会有多宽」，
        # 本来就该各算各的，而且点数已经写在句子里，读者不会误当成同一批月份。
        mf, rf = mono.iloc[-win:].dropna(), rl.iloc[-win:].dropna()  # data-window: 同上
        _stq = (flow_stats(s, d.index) if flow and not pct_series
                else caliber_stats(mono, rl, d.index))
        _sd_m = _stq['sd_m'] if _stq else float('nan')
        _sd_r = _stq['sd_r'] if _stq else float('nan')
        _noisier = bool(_stq and _sd_r >= _sd_m)
        _sd_txt = (f'两种口径都有值的月份不足 3 个，标准差不可比'
                   if not _stq else
                   f'对齐到两种口径都有值的 {_stq["n"]} 个月后，'
                   f'逐月标准差 {_sd_r:,.0f}pp vs 单月 {_sd_m:,.0f}pp')
        _first_ok = mlab(ys.dropna().index[0]) if len(ys.dropna()) else '—'
        both = ((f'{"两种口径都救不了这条序列" if _noisier else "两种口径的实测读数"}：'
                 f'本页统一的<b>单月同比</b>口径在本窗口内落在 '
                 f'{mf.min():+,.0f}%–{mf.max():+,.0f}%（{len(mf)} 个点），'
                 f'作对照的 12 个月滚动合计同比落在 {rf.min():+,.0f}%–{rf.max():+,.0f}%'
                 f'（{len(rf)} 个点）；{_sd_txt} —— '
                 + ('' if not _stq else
                    '对照口径在这里反而更吵，因为它的分母是「去年那一整年业务还没起量」。'
                    '<b>近零基数的序列不该画同比，该画水平值</b>，所以本图直接在柱上标数。'
                    if _noisier else
                    '对照口径的标准差更低 —— 这个数只是本图该印的代价，'
                    '那条线全站都不画。')
                 + (f'<b>本图不画同比线的理由与口径无关，是可比点不够</b>：'
                    f'{int(ok.sum())}/{len(ok)} = '
                    f'{cover:.0%}，低于 {YOY_MIN_COVER:.0%} 的下限，第一个算得出的期是 '
                    f'{_first_ok} —— 画出来只是一条盖住右侧一小段的线，'
                    '所以本图改在柱上标数。' if not _noisier else ''))
                if len(mf) and len(rf) else '')
        txt = (txt + ' ' if txt else '') + (
            yoy_drop_note or
            f'No y/y line on this chart, and that is deliberate: only {int(ok.sum())} of '
            f'{len(ok)} months in this window have a comparable prior-year base, {rng}'
            'A right-hand axis stretched to fit them turns the line into near-vertical '
            'segments that say only "a lot" while covering the bars. Levels are labelled on '
            'the bars; the exact y/y is in the Exhibit 1 summary table. ' + both)
    # 左端为什么截在这里、右轴那条线为什么比柱短 —— 两句都不手写，来自 mrwin.resolve()
    # 的裁决结果（`_w.why` 只在派生腿真的更短时才有内容）。
    for _bit in (left_txt, _w.why if cover >= YOY_MIN_COVER else ''):
        if _bit:
            txt = (txt + ' ' if txt else '') + _bit
    bk, seg = breaks_for(n, d.index, breaks)
    ex.update(bk)
    if seg:
        txt = (txt + ' ' if txt else '') + \
            f'红色竖虚线为口径断点：{seg}；线右侧与左侧不可直读。'
    if txt:
        ex['note'] = txt
    EX.append(ex)
    return ex


# ══════════════════════ 客户与资产 ══════════════════════
# 存量：期末资产，右轴是点对点（单月）同比（flow=False）—— 这次口径改动不影响它。
lvl(2, tpa, 'Total platform assets', win=len(W25), fmt='usd0', ylab='$bn', breaks=BK_TPA,
    flow=False, what='总平台资产',
    note='Previously reported as Assets Under Custody; renamed and widened to include '
         'TradePMR-advised assets not custodied by Robinhood.')

# 流量：净流入。右轴 2026-09 起画**单月同比**（所有者要求全站统一口径），
# 与滚动口径的实测差额由 mom_cost_note() 印进图注。
lvl(3, nd, 'Net deposits', win=len(W25), fmt='usd1', ylab='$bn', show_mom=True, breaks=BK_ND,
    what='净流入（流量）', note='m/m shown because net deposits swing far more than any y/y can express.')

# 有机增速的分子就是净流入，断点原样传导过来（同 build/schw.py 对 core NNA 的处理）：
# 分子跨了口径变化，比率也跨了，只在净流入那张画线等于让读者以为这张没受影响。
# 柱是**当月**年化率（GS 的流量口径规矩），右轴是同一条序列的**单月**百分点差。
# ⚠ 2026-09 之前右轴画的是滚动口径那条比率（organic_growth_roll）的百分点差；
# 现按所有者指令改成单月，滚动那条只留作 mom_cost_note() 的对照（roll_src）。
lvl(4, df['organic_growth_ann'], 'Annualised organic growth rate', win=len(W25), fmt='pct1',
    ylab='% annualised', pct_series=True, breaks=BK_ND,
    roll_src=df['organic_growth_roll'], what='年化有机增速（由流量推导的比率）',
    note='Monthly net deposits x 12 / prior month-end total platform assets — the same '
         'convention used for Schwab core NNA and LPL organic NNA in this series. '
         '柱是当月年化率；右轴是<b>同一条当月年化率</b>的百分点差（本月年化率 − 去年同月'
         '年化率），比率的同比一律用 pp、不用「百分比的百分比变化」。'
         '作对照的滚动口径是「滚动 12 个月净流入 ÷ 12 个月前的月末平台资产」这条比率的'
         '百分点差 —— 它<b>不进图</b>，只在下面的口径段里报数字。')

# 剔除 WonderFi 的客户数 m/m。只有「WonderFi 就是本月」时这句话才成立 —— 窗口一往前滚，
# 分母就不再是并购前的那个月，所以由 LATEST 现判，不写死一句话。
FC = df['funded_customers_mn']
FC_MM = float(FC.iloc[-1] / FC.iloc[-2] - 1)
FC_MM_EX = (float((FC.iloc[-1] - WONDERFI_CUSTOMERS_MN) / FC.iloc[-2] - 1)
            if LATEST == BRK_WONDERFI else None)
_ex5_note = (
    f'Jun-2026 includes about {WONDERFI_CUSTOMERS_MN * 1000:.0f}k funded customers acquired '
    'with WonderFi on 1 Jun 2026 — a stock transfer, not organic acquisition.'
    + (f' Excluding those customers the month was {FC_MM_EX:+.1%} m/m rather than {FC_MM:+.1%}.'
       if FC_MM_EX is not None else ''))

# Bitstamp 也是客户数的断点（页面口径说明第 3 条自己就是这么写的），原版只画了 WonderFi。
# 存量：账户/客户**存量**，右轴保留单月同比。全站审计里 /wealth/ 的 IBKR 账户数
# 实测证明这类序列换成滚动反而更吵，本页 funded customers 同理。
lvl(5, FC, 'Funded customers', win=len(W25), fmt='f1', ylab='mn customers',
    breaks=BK_CUST, flow=False, what='入金客户数', note=_ex5_note)

# ────────── 「起点是排版决定的」那几张图：逐处挂号，页尾照它现算 ──────────
# ⚠ 这份清单 2026-08-19 是手写的三条，当天就漏了 Exhibit 24（year_lines 只画 4 年）
# 与 Exhibit 27（heat 的 n_years=4），页尾却对读者写着「除这三张外都是数据决定的」——
# 一条被同一页当场证伪的全称断言。手写枚举保不住这句话，所以改成：
#   (a) 每一处真的按排版截过的地方**在原地挂号**，截多少、能画多少都现算；
#   (b) drawn >= avail 时**不挂号**（多点一张与漏点一张同样是假话）；
#   (c) 文件末尾两道看门狗：挂了号却没在自己图注里自报的 → 停更；
#       新出现「写死的尾部切片」却没标注归属的 → 停更。
_FIXED_LEFT = []


def _drawable(*cols):
    """一张图**画得出来**的那些期 = 它的定义性分量都非空的期。

    ⚠「序列有多长」不等于「这张图能画多少期」：差分 / shift(1) 派生的分量首期按构造
    就是 NaN。Exhibit 6 的桥当初把「数据支持」写成 `len(df)`（月度序列长度），而它的
    三条腿有两条是 `tpa.diff()` 派生的 —— 同一页的 Exhibit 4（同样吃上月末资产）实测
    就比月度序列短一期。哪几条算「定义性分量」由调用点决定：桥缺一条腿就画不成一根柱，
    而季度柱图的右轴 y/y 缺前几期照样画得出柱，所以那里只传柱自己。
    """
    return pd.concat(cols, axis=1).dropna().index


def _fix_left(n, what, drawn, avail, unit):
    """按排版截过起点的图在这里挂号，返回「今天是不是真的截了」。

    `drawn` / `avail` 传的是**期标签本身**（月份 / 季度 / 年份的集合），不是个数 ——
    个数由这里现算。这条签名是有意的：传标签就写不出 `len(df)` 那种「拿别的东西的长度
    冒充数据支持」的写法，`avail` 只能是「这张图**自己**画得出来的那些期」，
    谁画得出来由 notna() 说了算（见 `_drawable()`）。
    并当场兜一道：画的期不在 avail 里就停机 —— 那时「画 x／数据支持 y」必然说假话。
    """
    drawn, avail = list(drawn), list(avail)
    _ghost = [x for x in drawn if x not in set(avail)]
    if _ghost:
        raise SystemExit(f'Exhibit {n}（{what}）画了「数据支持」里没有的期：'
                         f'{[str(x) for x in _ghost[:5]]} —— 页尾「序列起点」那一条里'
                         f'「画 x／数据支持 y」会因此说假话')
    if len(drawn) >= len(avail):
        return False
    _FIXED_LEFT.append(
        f'Exhibit {n}（{what}，画 {len(drawn)}{unit}／数据支持 {len(avail)}{unit}）')
    return True


# ⚠ 这张**刻意**只画近端 13 个月，不跟着放宽后的主窗口走 —— 它读的是段内那三个数值与
# 相邻月的差，段宽拉到全历史只剩几个像素、数值标签会被 charts.js 的 thinLabels 抽稀掉
# 大半。页尾「序列起点」那一条对读者写着「每张图的左端由 mrwin.resolve() 裁、图注里都
# 写了截在哪一期」，所以这个例外必须在图注里自报，否则那句话就是假的。
# 这张桥的腿只在这里列一次：可画期数、「几条腿吃上月末资产」、「段内几个数值标签」
# 三处都从它现算。列两遍就是下一次「只改了一处」的入口。
_B_STACKS = (('Net deposits', 'NAVY', 'net_deposits_usdbn'),
             ('Market gains (balancing)', 'BLUE', 'market_gains_usdbn'))
_B_NET = ('Total change in platform assets', 'tpa_change_usdbn')
_B_COLS = [c for _nm, _c, c in _B_STACKS] + [_B_NET[1]]
_b_all = _drawable(*(df[c] for c in _B_COLS))               # 三条腿都非空的那些期
_b = df.iloc[-13:]                                          # fixed-left: 6
_b_gone = [mlab(p) for p in df.index if p not in set(_b_all)]   # 桥画不出来的那几期
_b_lag = sum(1 for c in _B_COLS if df[c].first_valid_index() != df.index[0])
_b_note = ('' if not _fix_left(6, '资产变动分解', _b.index, _b_all, ' 个月') else
           f'<b>左端是排版决定的，不是数据决定的</b>：本图只画最后 {len(_b)} 个月'
           f'（这张桥画得出来的共 {len(_b_all)} 个月 —— {_b_lag} 条腿从'
           '「当月末资产 − 上月末资产」派生，'
           + (f'月度序列的 {"、".join(_b_gone)} 没有上月，那{"几" if len(_b_gone) > 1 else "一"}'
              '格在数据里不存在），' if _b_gone else '月度序列每一期都算得出来），')
           + f'拉到全历史段内那 {len(_B_COLS)} 个数值标签会被抽稀掉大半。')
EX.append({
    'n': 6, 'kind': 'bridge_bar', 'title': 'What moved platform assets: flows vs. markets',
    # x 轴直接取自这张图自己那一刀（上面已挂号）。原先走的是文件上半段的 XL13 ——
    # 同一刀在两处各切一遍，其中一处还标着「not-a-window」，那个标记因此是假的。
    'xlabels': [mlab(p) for p in _b.index], 'fmt': 'usd0', 'ylab': '$bn change',
    'stacks': [{'name': nm, 'color': c, 'values': L(_b[col])} for nm, c, col in _B_STACKS],
    'net': {'name': _B_NET[0], 'values': L(_b[_B_NET[1]])},
    'net_color': 'INK',
    'note': 'Identity: opening assets + net deposits + market gains = closing assets. '
            'Market gains is the balancing item, so it also absorbs any acquired assets. '
            + _b_note,
})

# ══════════════════════ 交易量 ══════════════════════
# ⚠ ADV 三列在 2023-01 之前**是空的，而且必须是空的**：2021-01~2022-12 那 24 个月的
# 官方月度表（老版式 Earnings Supplement）只有「Total Trading Volumes」与交易日两节，
# 「Average Daily Trading Volumes」那一节是后来才加的。两个分量（当月合计、交易日）
# series 里都有，除一下就能把格子填满 —— 但那是**我们算的**，不是公司印的，
# 仓规「入库值必须是当期官方公告原值、不许换算」把这条路堵死了。
# 于是这几张图的左端由 mrwin.resolve() 裁到 2023-01（见 lvl 的 docstring）。
ADV_LEFT = ('官方 2023-01 才开始印「日均成交量（ADV）」那一节，更早的月度表只有当月合计'
            '与交易日两行；ADV = 合计 ÷ 交易日 这个除法本页不代做 —— 换算值不是披露值')

# ADV 是「每天平均多少量」的流量率，按流量处理（flow=True）：右轴画单月同比，
# 与滚动口径的实测差额由 mom_cost_note() 印进图注。
# ⚠ 2026-09 口径改动的一个**副作用**要在这里记一笔：这两张图上一版退成了
# bars_labeled（柱上标数、没有右轴线），理由是滚动同比要 24 个月历史、窗口内可比点
# 覆盖率只有 47%，低于 YOY_MIN_COVER。单月同比只要 12 个月历史，覆盖率升到 72% ——
# 于是它们自动过线、右轴的线自己回来了。这正是 YOY_MIN_COVER 那条判据的设计意图
# （「等基数长满，线会自己回来，不用有人记得回来改这里」），不是这次手动加的。
# ⚠ 图注原先写死「running at more than twice last year」。实测 Jul-26 / Jul-25 =
# 15.1 / 9.7 = 1.6x，与「twice」对不上。这类「倍数」是每个月都在走的量，
# 写死一次就过期一次，改成现算。
_EQ_X = float(df['adv_equity_usdbn'].iloc[-1] / df['adv_equity_usdbn'].iloc[-13])
lvl(7, df['adv_equity_usdbn'], 'Equity notional ADV', win=len(W25), fmt='usd1', ylab='$bn / day',
    show_mom=True, left_zh=ADV_LEFT, what='股票名义 ADV（流量率）',
    note=f'm/m shown: equity volume is running at {_EQ_X:.1f}x its level a year ago, '
         'so y/y alone no longer separates months.')

lvl(8, df['adv_options_mn'], 'Options contracts ADV', win=len(W25), fmt='f1',
    ylab='mn contracts / day', show_mom=True, left_zh=ADV_LEFT, what='期权 ADV（流量率）')

# ⚠ 窗口原来写死 `df.iloc[-15:]`（deck 移植时的近端窗口，2026-08 两轮放宽都漏掉了它）。
# 那是一个会**漂**的窗口：今天 15 个月正好含 1 个并表前的月份，下个月就一个都不剩，
# 图上只剩并表后的一段，读者再也看不到 Bitstamp 是从哪儿冒出来的。
# 官方 Q1'26 Supplement 的「Total / Average Daily Trading Volumes」两节里，
# 'Robinhood App' 与 'Bitstamp' 两行**逐月印到 2023-01**，并表前的月份印的是 0
# （不是留白）—— 那是公司自己印出来的读数，照抄入库，所以这张图能画到 2023-01。
# 再往前是老版式的 Supplement，那里根本没有这两行（见 build/basefill/hood_2021.py），
# 所以左端由 mrwin.resolve() 钉在 2023-01，不是我们挑的。
_share_all = (df['adv_crypto_bitstamp_usdmn'] /
              (df['adv_crypto_app_usdmn'] + df['adv_crypto_bitstamp_usdmn']) * 100)
_l9 = [mrwin.Leg('app', 'Robinhood App', L(df['adv_crypto_app_usdmn']), 'primary'),
       mrwin.Leg('bs', 'Bitstamp', L(df['adv_crypto_bitstamp_usdmn']), 'primary'),
       mrwin.Leg('sh', '% Bitstamp', L(_share_all), 'primary')]
_w9 = mrwin.resolve('stacked_dual', _l9, XL25, 0)
_c = df.iloc[_w9.start:]
_cshare = _share_all.iloc[_w9.start:]
_pre9 = int((_c['adv_crypto_bitstamp_usdmn'] == 0).sum())
_ex9 = {
    'n': 9, 'kind': 'stacked_dual', 'title': 'Crypto ADV: Robinhood App vs. Bitstamp',
    'xlabels': XL25[_w9.start:], 'xstep': xstep_for(len(_c)), 'fmt': 'f0c',
    'ylab': '$mn / day',
    'ylab2': '% Bitstamp (RHS)',
    # ⚠ `label` / `label_color` 已删（2026-08-19）。段内逐段标数值在 15 个月的旧窗口下
    # 放得下，43 期放不下 —— 而且撞的不是「同族标签互相挤」，是**两族标签互相看不见**：
    # charts.js 的 `thinLabels()` 对每个 stack 抽一次、对右轴那条线的百分比标签再抽一次，
    # 两次抽稀彼此不知道对方留下了哪些。并表前那一段 Bitstamp = 0，引擎把 `0.0%` 从零刻度
    # 抬到柱顶上方 2px（charts.js:1495 的 `Math.min(yPct, Y(base[i]) - 2)`），于是它正好
    # 落进相邻列段内数值所在的那一带高度上。
    # 通栏救不了：768px 窄屏本来就是单列（`.card.wide` 是 `grid-column: 1/-1`，单列时无效），
    # 那里 band 仍不够；缩窗口等于把刚放宽的窗口收回去。
    # ⚠ 这里原先写的是「全站长轴的 stacked_dual（ase / cme / exchanges-eu /
    # exchanges-na / guc，68–127 期）也都是不标段内数值的，本图 43 期原是唯一的例外」。
    # 两处都别再写了：期数每个月自己往前走一格；而「长轴都不标」这条**实测就是假的**
    # —— cboe Exhibit 5 今天是 127 期、通栏，`stacks[].label` 照标（`assets/charts.js`
    # 里 stacked_dual 那段的注释就拿它当压字例子）。跨页的做法本来就不一致，
    # 拿它当理由只会得到一条随时被别页推翻的断言。
    # **本图不标段内数值的理由是本页自己量出来的**，全在下面那段图注里（段宽 px 现算
    # + 两族标签各抽各的稀）。要核跨页现状就扫 `data/*.js` 里 kind == 'stacked_dual'
    # 的图，比 `full` 与 `stacks[].label`，别把当天的读数抄回这里。
    # 逐月读数一格不少，见右上角「表格」。
    'stacks': [
        {'name': 'Robinhood App', 'color': 'NAVY', 'values': L(_c['adv_crypto_app_usdmn'])},
        {'name': 'Bitstamp', 'color': 'BLUE', 'values': L(_c['adv_crypto_bitstamp_usdmn'])},
    ],
    'line': {'name': '% Bitstamp (RHS)', 'color': 'GREEN', 'values': L(_cshare),
             'ymax': float(np.ceil(np.nanmax(_cshare.values) / 10.0) * 10)},
    'note': 'Bitstamp is institutional and carries a different take rate from the '
            'retail app, so the mix shift matters for revenue, not just for volume. '
            f'左边 {_pre9} 个月 Bitstamp 段的高度是 <b>0</b>，那是官方自己印的 0（并表前'
            '这家还不在合并范围内），不是缺数补零。'
            + _w9.why
            + '本图左端不能再往左：更早的月度表（老版式 Earnings Supplement）'
              '没有「Robinhood App / Bitstamp」这两行，加密成交量只有一个总数。',
}
_bk9, _seg9 = breaks_for(9, _c.index, BK_CRYPTO)
_ex9.update(_bk9)
# band 现算（`mrwin.band_px` 走 `chartscale._margins`，与 charts.js 同一套量边距算式），
# 不写死：窗口每过一个月就长一期，写死的像素数下个月就是假的。
_ex9['note'] += (
    f'<b>柱段上不再逐月标数值</b>：{len(_c)} 期塞进半栏卡片，每期只有 '
    f'{mrwin.band_px(_ex9):.1f}px（按 <code>assets/charts.js</code> 的量边距算式复算，'
    '不是目测），装不下一个三位数；而且引擎对「段内数值」与「右轴百分比」是各抽各的稀、'
    '两边互不相让，并表前那一段的 <code>0.0%</code> 被抬到柱顶上方之后，正好压住相邻列的'
    '段内数值。逐月读数一格不少，切右上角「表格」视图读。')
if _seg9:
    _ex9['note'] += f' 红色竖虚线为口径断点：{_seg9}；线右侧与左侧不可直读。'
EX.append(_ex9)

# 事件合约的 y/y 覆盖率只有 6/25，lvl() 会自动把它退成单轴的 bars_labeled（见函数注释）。
# 原来它是 bar_line_dual + 右轴 y/y：那 6 个读数在 +488% 到 +2600% 之间，右轴被撑到
# 0–3000%，绿线退化成两段近乎垂直的竖线加一段贴地的直线，除了「涨了很多」读不出任何
# 东西，还横穿柱子。现在每根柱直接标出数值，「这个月到底多少」一眼可得。
lvl(10, df['adv_event_mn'], 'Event contracts ADV', win=len(W25), fmt='f0',
    ylab='mn contracts / day', show_mom=True, left_zh=ADV_LEFT,
    note='Prediction Markets Hub, launched at scale in 2025.')

_d = df.iloc[_I0:]          # 与 W25/XL25 同窗口（原先写死 -25）

# ⚠ dats_* 三列在 2023-03 及更早那一段装的是 **DARTs**，不是 DATs。
# 官方 2026-07-29 发的 Q2'26 Earnings Supplement 起，那一节从「Daily Average *Revenue*
# Trades (DARTs)」改叫「Daily Average Trades (DATs)」，并把 **2025-01 起**的历史重述
# （equity 2025-01 由 2.6 改成 3.3，+27%）。重述只回溯到 2025-01：2024-12 及更早
# 两种口径逐月逐位相同（build/basefill/hood_2021.py 的看门狗 B 每次运行都重算一遍）。
# 所以回填段填 DARTs 接得上，但**这件事必须写在图注里**，不能让读者以为整条线一把尺子。
DARTS_UNTIL = pd.Period('2023-03', 'M')
DATS_CALIBER = (
    f'口径提示：{mlab(DARTS_UNTIL)} 及更早这一段填的是官方当期印的 <b>DARTs</b>'
    '（Daily Average <i>Revenue</i> Trades）。公司 2026-07 才把这一节改名 DATs 并重述历史，'
    '而重述只回溯到 Jan-25（equity 由 2.6 改成 3.3）—— Dec-24 及更早两种口径逐月逐位相同，'
    '所以两段接得上；但左段严格说是窄口径（不含不产生收入的交易），这里一并说明。')

_l11 = [mrwin.Leg('eq', 'Equity DATs', L(_d['dats_equity_mn']), 'primary'),
        mrwin.Leg('op', 'Options DATs', L(_d['dats_options_mn']), 'primary'),
        mrwin.Leg('cr', 'Crypto DATs', L(_d['dats_crypto_mn']), 'primary')]
_w11 = mrwin.resolve('lines_endlabels', _l11, XL25, 0)
EX.append({
    'n': 11, 'kind': 'lines_endlabels', 'title': 'Daily average trades by asset class',
    'xlabels': XL25[_w11.start:], 'xstep': xstep_for(len(XL25) - _w11.start),
    'fmt': 'f1', 'ylab': 'mn trades / day',
    'series': [{'name': nm, 'color': c, 'values': _w11.cut(leg.vals)}
               for leg, nm, c in zip(_l11, ('Equity', 'Options', 'Crypto'),
                                     ('NAVY', 'RED', 'MBLUE')) if not leg.drop],
    'note': 'Crypto DATs exclude Bitstamp institutional activity; crypto trades every '
            'calendar day while equities and options use exchange trading days. '
            + DATS_CALIBER + _w11.why,
})

_idx = {'Equity notional': df['adv_equity_usdbn'], 'Options contracts': df['adv_options_mn'],
        'Crypto notional': df['adv_crypto_usdmn'], 'Funded customers': df['funded_customers_mn']}
# 基期不写死：它必须是**四条线都已经有值**的第一个月，否则除数是 NaN，整条线全空。
# 原来写死 2023-04（当时的序列起点），序列回填到 2021-01 之后那句「the first month in
# the published file」就成了假话 —— 现在起点是 2021-01，而 ADV 三列 2023-01 才有。
_l12 = [mrwin.Leg(k, k, L(v.iloc[_I0:]), 'primary') for k, v in _idx.items()]
_w12 = mrwin.resolve('lines', _l12, XL25, 0)
BASE = W25[_w12.start]
EX.append({
    # zero_base：指数图的 100 与 0 都是有意义的刻度，而通用留白分支给的是
    # y0 = min − 极差×5%、y1 = max + 极差×5%，刻度只排到 800，两条跑到 935/954 的线
    # 就落在最高刻度线以上的无刻度区里 —— 整张图最想让人看的两个高点没有任何参照。
    # end_label：末点数值是这类图上唯一的绝对锚点。
    'n': 12, 'kind': 'lines', 'title': 'Volume vs. customer growth, rebased',
    'xlabels': XL25[_w12.start:], 'xstep': xstep_for(len(XL25) - _w12.start),
    'fmt': 'f0', 'label_fmt': 'f0',
    'ylab': 'index, base = 100', 'zero_base': True, 'end_label': True,
    'series': [{'name': k, 'color': c,
                'values': L((v / v.loc[BASE] * 100).iloc[_I0 + _w12.start:])}
               for (k, v), c in zip(_idx.items(), ['NAVY', 'RED', 'MBLUE', 'GREEN'])],
    'note': f'Rebased to 100 at {mlab(BASE)}, the first month in which all four series '
            'exist — the monthly file only starts publishing average daily volumes then, '
            f'while funded customers and total volumes go back to {mlab(df.index[0])}. '
            'The gap between the volume lines and the customer line is monetisation '
            'per customer, not customer acquisition. Axis starts at zero and the last '
            'point of each line is labelled.',
})

# ══════════════════════ 收入桥：先讲费率，再讲检验，最后才给隐含值 ══════════════════════
# ── 费率图按量级拆两张 ──
# 四条费率的量级差两个数量级：Options 与 Crypto 是一档，Equities 与 Event 是另一档
# （两档的实测区间由下面的 _rate_span() 现算，不写死 —— 窗口一变写死的数字就成假话）。
# 原来四条共用一根线性轴，低位两条被完全压在零刻度线上、一条盖着另一条，整个窗口看不出
# 任何变化——而图注自己就写着「线性轴会把股票与事件合约压到零附近」。既然知道，
# 就不该这样发出来。引擎没有对数轴（也不许有：读者按线性直觉读对数轴会把 10x 读成 2x），
# 所以按本仓既有规矩「不同量纲本来就不该同轴」拆成两张，每张两条线各自读得出变化。
# 拆的依据是量级不是单位：按单位拆（c/contract 一张、bp 一张）会把 45 和 1.1 放同一张，
# 压扁的问题原样保留。每条线的单位写在它自己的图例名里。
#
# ⚠ 窗口**不再写死 `[-13:]`**（2026-08-19）。原来那句理由是「对齐 PDF deck 的 win=13」，
# 而 2026-08-18 全站把时序窗口改成「数据有多少画多少」时那条理由就作废了；写死的切片
# 还有第二个毛病：hood_q.csv 每多一季，最左边那一季就被静默丢掉。左端一律交给
# `mrwin.resolve()` 按各条序列自己的首值裁（只调用，不改 mrwin）。
# 2026-08-19 hood_q.csv 由 build/basefill/hood_q_2021.py 回填到 2021Q1 之后，这两张图的
# 左端就只由各自那几条费率的首值定。⚠ 这里原先还写着「（13 → 22 季）…画的就是全部历史」：
# 季数每季都会走一格，而「正好等于全部历史」也只是今天的巧合（哪一季的成交量缺了、
# 反解不出费率，左端就往右挪）。两件事都不写死，各图窗口以图注里现算的那句为准。
_RATE_SRC = ('Quarterly reported revenue / quarterly volume — derived, not disclosed. ')


def _rate_span(*ss):
    """几条费率合起来的实测区间，给图注用。写死区间是本仓踩过的坑（规矩 C）。"""
    v = np.concatenate([np.asarray(s.values, float) for s in ss])
    v = v[np.isfinite(v)]
    d = 0 if v.max() >= 10 else 2
    return f'{v.min():.{d}f}–{v.max():.{d}f}'


_RATE_SPLIT = (
    'PDF 版把四条费率画在同一根对数轴上；网页引擎没有对数轴，改按量级拆两张 —— '
    f'Exhibit {N_RATE_HI} 是 {_rate_span(rate_options_c, rate_crypto_bp)} 这一档，'
    f'Exhibit {N_RATE_LO} 是 {_rate_span(rate_equities_bp, rate_event_c)} 那一档。'
    '两张的单位都混着 c/contract 与 bp（写在各自图例名里），跨图不能直接比高低，'
    '要比就切右上角「表格」视图读逐季数值。')

_l13 = [mrwin.Leg('op', 'Options (c/contract)', L(rate_options_c), 'primary'),
        mrwin.Leg('cr', 'Crypto (bp)', L(rate_crypto_bp), 'primary')]
_w13 = mrwin.resolve('lines', _l13, XQ, 0)
_c13 = rate_crypto_bp.iloc[_w13.start:]
# 「近一年怎么走的」用最后 4 个季度现算；拿整窗口的 max→min 说「腰斩」会说反话 ——
# 回填之后窗口内的最低点落在 2021Q1（业务刚起步），不是崩在最高点之后。
_c13pk = _c13.idxmax()
_c13tail = _c13.dropna()
EX.append({
    'n': N_RATE_HI, 'kind': 'lines', 'markers': True, 'zero_base': True, 'end_label': True,
    'title': 'Effective take rate: options and crypto',
    'xlabels': XQ[_w13.start:], 'fmt': 'f2', 'label_fmt': 'f1',
    'ylab': 'cents/contract (options) · bp (crypto)',
    'series': [
        {'name': 'Options (c/contract)', 'color': 'NAVY',
         'values': L(rate_options_c)[_w13.start:]},
        {'name': 'Crypto (bp)', 'color': 'MBLUE', 'values': L(rate_crypto_bp)[_w13.start:]},
    ],
    'note': _RATE_SRC + 'Crypto is the volatile one and it is what makes the revenue '
            f'bridge (Exhibit {N_BRIDGE_TEST}) miss: it peaked at '
            f'{_c13.max():.0f}bp in {_c13pk} and is {_c13tail.iloc[-1]:.0f}bp in '
            f'{_c13tail.index[-1]}, having run between {_c13.min():.0f}bp and '
            f'{_c13.max():.0f}bp across the window. Options moves in a much narrower band '
            f'({rate_options_c.iloc[_w13.start:].min():.0f}–'
            f'{rate_options_c.iloc[_w13.start:].max():.0f}c). ' + _RATE_SPLIT,
})

# 事件合约那条腿**不进 resolve 的 legs**：mrwin 给「派生腿比主腿短」生成的那句话写的是
# 「所以左段只有柱没有线」—— 那是给 bar_line_dual 写的措辞，这里没有柱，会说假话。
# 左端只由 equities 定（它是主腿），事件合约从哪一季开始由下面现算的一句话交代。
_l14 = [mrwin.Leg('eq', 'Equities (bp)', L(rate_equities_bp), 'primary')]
_w14 = mrwin.resolve('lines', _l14, XQ, 0)
_ev14 = rate_event_c.dropna()
_evv = q['q_vol_event_bn']
_ev_blank = int(_evv.iloc[_w14.start:].isna().sum())      # 官方那一行还不存在的季度
_ev_zero = int((_evv.iloc[_w14.start:] == 0).sum())       # 印出来但四舍五入成 0.0 的季度
_ev14_txt = (
    f'Event contracts have no back-solvable rate before {_ev14.index[0]}: quarterly event '
    f'volume is blank for the first {_ev_blank} quarters here (the row did not exist in '
    f'the supplements of the day) and then rounds to 0.0bn for {_ev_zero} more — including '
    f'Oct-2024, the launch quarter — so the division has no denominator. That line starts '
    f'{_ev14.index[0]} and is broken, not zero-filled, to its left. ' if len(_ev14) else '')
EX.append({
    'n': N_RATE_LO, 'kind': 'lines', 'markers': True, 'zero_base': True, 'end_label': True,
    'title': 'Effective take rate: equities and event contracts',
    'xlabels': XQ[_w14.start:], 'fmt': 'f2', 'label_fmt': 'f2',
    'ylab': 'bp (equities) · cents/contract (event)',
    'series': [
        {'name': 'Equities (bp)', 'color': 'RED', 'values': L(rate_equities_bp)[_w14.start:]},
        {'name': 'Event contracts (c/contract)', 'color': 'GREEN',
         'values': L(rate_event_c)[_w14.start:]},
    ],
    'note': _RATE_SRC + 'Both are round-number rates an order of magnitude below options '
            'and crypto, which is why they get their own axis. ' + _ev14_txt + _RATE_SPLIT,
})

# 桥检验的窗口跟着 pred 自己的长度走（原来写死 `[-12:]`，与上面两张同一个毛病）。
# pred 的第一期必然缺：它按构造要「上一季的费率」，所以 hood_q 的第一季算不出预测值。
_pi = [p for p in pred.index if p in actual_txn.index and np.isfinite(pred[p])]
_pv = np.array([pred.get(p, np.nan) for p in _pi], float)
_av = np.array([actual_txn.get(p, np.nan) for p in _pi], float)
_err = np.where(_av != 0, (_pv / _av - 1) * 100, np.nan)
_mae = float(np.nanmean(np.abs(_err)))
# ⚠ 图注原先写死「Both bars cover the same **four** asset classes.」——「同一组类别」
# 是对的（notes 里那条口径对齐保证了它），「four」是假的：事件合约要等到有可用的上季
# 费率才进桥，在那之前两根柱都只有三类，本轮实测 21 季里有 16 季是三类。类别数按
# cls_in_bridge 现算，并按「哪几季是同一组」压成分段，不留任何写死的数。
_segs = []
for _p in _pi:
    _c = tuple(cls_in_bridge[_p])
    if _segs and _segs[-1][2] == _c:
        _segs[-1][1] = _p
    else:
        _segs.append([_p, _p, _c])
_cls_txt = '; '.join(
    (f'{a}' if a == b else f'{a}–{b}') + f' ({len(c)}: ' + ', '.join(c).lower() + ')'
    for a, b, c in _segs)
_cls_sent = ('Both bars cover the same asset classes in each quarter — that is what makes '
             'the error meaningful — but the set itself is '
             + (f'unchanged across the window ({_cls_txt}). ' if len(_segs) == 1 else
                f'not constant across the window: {_cls_txt}. '))
EX.append({
    'n': N_BRIDGE_TEST, 'kind': 'grouped_bars', 'height': 300,
    'title': "Bridge test: last quarter's rate applied to this quarter's volume",
    'xlabels': [str(p) for p in _pi], 'fmt': 'f0c', 'ylab': '$mn per quarter',
    'ylab2': 'Error (%)',
    'groups': [
        {'name': 'Implied by the bridge', 'color': 'BLUE', 'values': L(_pv)},
        {'name': 'Actually reported', 'color': 'NAVY', 'values': L(_av)},
    ],
    'line': {'name': 'Error (RHS)', 'color': 'RED', 'values': L(_err), 'yfmt': 'pct1'},
    # 这里原来写的是「双轴图的零点必须落在同一条水平线上……柱子因此压在画布上半张」。
    # 引擎后来加了兜底：对齐代价过大时改成两轴各自缩放，并在绘图区左上角画一行红字
    # 「左右轴零点不同高（两轴独立缩放）」。这张图正是触发那条兜底的四张之一，
    # 于是图注声称的和图上写的正好相反 —— 图注必须跟着改成实话。
    'note': "The only non-circular test: the prior quarter's rate applied to this "
            "quarter's actual volumes, versus revenue reported afterwards. "
            + _cls_sent
            + f'Mean absolute error over the window: {_mae:.1f}%. '
            '本图的左右两轴零点<b>不在同一高度</b>（误差线跨零、对齐会浪费掉四成画布，'
            '引擎因此改为两轴独立缩放，并在图内左上角以红字标出）：柱子的基线只代表左轴，'
            '误差线的零点请看右轴刻度上那条同色虚线。',
})

lvl(N_IMPLIED, df['implied_txn_rev_usdmn'], 'Implied transaction revenue', win=len(W25), fmt='usd0',
    ylab='$mn / month', what='隐含交易收入（流量）',
    left_zh=f'费率是季度收入 ÷ 季度成交量反解出来的，而 series/hood_q.csv 只回溯到 '
            f'{q.index[0]}，更早的月份反解不出费率（不是成交量缺，是收入那一半缺）',
    note='Assumption: constant take rate within a quarter, back-solved as reported revenue / volume '
         f'({LAST_Q}: options {rate_options_c[LAST_Q]:.0f}c/contract, '
         f'equities {rate_equities_bp[LAST_Q]:.2f}bp, crypto {rate_crypto_bp[LAST_Q]:.1f}bp), '
         'held flat afterwards. Matches its own quarter by construction — '
         f'Exhibit {N_BRIDGE_TEST} is the real test.')

# ⚠ 左端由 mrwin.resolve() 裁，不写死（原来是 `q.iloc[-13:]`，多一季就丢最左那一季）。
# 这张图注定截在 rev_event_usdmn 的首值上，而那一格的边界是**披露史**不是业务史：
# 「Event contracts」是 Q2'26 Earnings Supplement 才从 P&L 的 'Other' 一行里拆出来的，
# 而那份文件的季度 P&L 是滚动 13 个季度的窗口 —— 于是 2023Q2 及以后印得出事件合约收入
# （2024Q3 及更早印的是 0），再往前**没有任何一份官方文件印过这一行**。
# 业务本身 2024-10 才上线、事后看那一段就是 0，但补 0 是我们的断言不是公司的披露，
# 所以 series/hood_q.csv 那 9 期留空（见 build/basefill/hood_q_2021.py 的文件头），
# stacked_dual 又是平滑图型吃不了 null，两件事叠起来把左端钉在 2023Q2。
_rcols = ['rev_options_usdmn', 'rev_equities_usdmn', 'rev_crypto_usdmn', 'rev_event_usdmn']
_rshare_all = q['rev_event_usdmn'] / q[_rcols].sum(axis=1, min_count=4) * 100
_l17 = [mrwin.Leg('op', 'Options', L(q['rev_options_usdmn']), 'primary'),
        mrwin.Leg('eq', 'Equities', L(q['rev_equities_usdmn']), 'primary'),
        mrwin.Leg('cr', 'Crypto', L(q['rev_crypto_usdmn']), 'primary'),
        mrwin.Leg('ev', 'Event contracts', L(q['rev_event_usdmn']), 'primary',
                  '事件合约收入是 Q2\'26 Supplement 才从 Other 里拆出来的一行，'
                  '而那份文件只滚动覆盖 13 个季度'),
        mrwin.Leg('sh', '% event contracts', L(_rshare_all), 'primary')]
_w17 = mrwin.resolve('stacked_dual', _l17, XQ, 0)
_rq = q.iloc[_w17.start:]
_rshare = _rshare_all.iloc[_w17.start:]
_ev_on = q.index[[bool(v) for v in (q['rev_event_usdmn'] > 0).fillna(False)]]
# ⚠ 下面这段结尾原先写的是「本页其余三张季度图（13/14/15）不含这一行，窗口是完整的 22 个
# 季度」—— 两处都假：Exhibit 15 是 21 季（首季按构造算不出预测值），而 14 与 15 恰恰都用了
# 事件合约。三张图的窗口与「含不含事件合约」一律现算，不写死也不做全称断言。
_n13, _n14 = len(XQ) - _w13.start, len(XQ) - _w14.start
_ev_bridge = first_in_bridge.get('Event contracts')
_why17_others = (
    f'<b>被这一行截住左端的只有本图</b>，因为堆叠图吃不了前导 null。'
    f'Exhibit {N_RATE_HI} / {N_RATE_LO} / {N_BRIDGE_TEST} 各有各的窗口：'
    f'Exhibit {N_RATE_HI} 不含事件合约，{_n13} 季；'
    + (f'Exhibit {N_RATE_LO} <b>含</b>（绿线自 {_ev14.index[0]} 起），但折线允许左段断开，'
       f'x 轴仍是 {_n14} 季；' if len(_ev14) else
       f'Exhibit {N_RATE_LO} 目前反解不出事件合约费率，x 轴 {_n14} 季；')
    + (f'Exhibit {N_BRIDGE_TEST} 的两根柱自 {_ev_bridge} 起<b>也把这一行计入</b>，'
       if _ev_bridge is not None else
       f'Exhibit {N_BRIDGE_TEST} 尚未把这一行计入，')
    + f'它只有 {len(_pi)} 季是因为首季按构造算不出预测值（要用上一季的费率），与事件合约无关。')
_why17_zh = (
    '' if not _w17.start else
    '钉住左端的是<b>事件合约收入那一行本身</b>：它是 Q2\'26 Earnings Supplement 才从 P&L 的 '
    '「Other」里拆出来的，而那份文件的季度 P&L 只滚动覆盖 13 个季度 —— '
    f'{XQ[_w17.start]} 及以后印得出（早期印的是 0），再往前<b>没有任何一份官方文件印过</b>。'
    '事件合约 2024-10 才上线、事后看更早那一段就是 0，但补 0 是我们的断言不是公司的披露，'
    '所以 series/hood_q.csv 那几期留空（详见 build/basefill/hood_q_2021.py 的文件头）。'
    + _why17_others)
_ev17_txt = (
    f'Event contracts went from nothing to {_rshare.iloc[-1]:.0f}% of transaction revenue '
    f'in the {(_rq.index[-1] - _ev_on[0]).n + 1} quarters since {_ev_on[0]} — the fastest '
    'mix shift in the business. ' if len(_ev_on) else '')
EX.append({
    'n': 17, 'kind': 'stacked_dual', 'title': 'Transaction revenue mix by asset class',
    'xlabels': [str(p) for p in _rq.index], 'fmt': 'f0c', 'ylab': '$mn per quarter',
    'ylab2': '% event contracts (RHS)',
    'stacks': [
        {'name': 'Options', 'color': 'NAVY', 'values': L(_rq['rev_options_usdmn']),
         'label': True, 'label_color': 'WHITE'},
        {'name': 'Equities', 'color': 'MBLUE', 'values': L(_rq['rev_equities_usdmn']),
         'label': True, 'label_color': 'WHITE'},
        {'name': 'Crypto', 'color': 'BLUE', 'values': L(_rq['rev_crypto_usdmn']),
         'label': True, 'label_color': 'NAVY'},
        {'name': 'Event contracts', 'color': 'GREEN', 'values': L(_rq['rev_event_usdmn']),
         'label': True, 'label_color': 'WHITE'},
    ],
    'line': {'name': '% event contracts (RHS)', 'color': 'GREEN', 'values': L(_rshare),
             'ymax': float(np.ceil(np.nanmax(_rshare.values) / 5.0) * 5)},
    # 「几个季度从零到几分之一」两个数都现算：写死之后每过一季就多错一季（规矩 C）。
    'note': 'Quarterly actuals, not derived. ' + _ev17_txt + _w17.why + _why17_zh,
})

# ══════════════════════ 生息资产 ══════════════════════
# 存量：期末融资余额（Period-end），右轴保留单月同比。
lvl(18, df['margin_book_usdbn'], 'Margin book', win=len(W25), fmt='usd1', ylab='$bn',
    flow=False, what='期末融资余额',
    note='Period-end margin loans receivable, including balances from RIAs on the '
         'TradePMR platform.')

# ⚠ Exhibit 19 / 20 都是 `lines_endlabels`，属 mrwin.DENSE：引擎把整条 values 交给
# Catmull-Rom 平滑，null 参与插值就是一条塌到零的假线，逐点标数值那步还会抛 TypeError
# 把该卡片之后的 exhibit 全打挂（build/verify_pages.py 有专门一条规则拦它）。
# 序列回填到 2021-01 之后这两张第一次咬人：Cash and Deposits 那一行 2023-01 才进官方表，
# Securities lending 更晚（Total 2022-05 出借业务上线才有数、Net 那一行 2023-01 才单列）。
# 左端一律交给 mrwin.resolve() 按「所有线都已经有值」裁 —— **只调用它，不改它**，
# 也不补 0、不补上一期的值（那是画一个数据里不存在的点）。
# 谁是 primary 谁是 derived 决定图注措辞：`mrwin.resolve()` 的「定住左端的是谁」
# 只点名 **derived** 腿（primary 被当成「本来就该有」）。所以更晚才有的那条挂 derived，
# 图注里才会印出「Cash and deposits（官方 2023-01 才单列，首点 Jan-23）」而不是干巴巴一个期号。
_l19 = [mrwin.Leg('sweep', 'Cash sweep', L(_d['cash_sweep_usdbn']), 'primary'),
        mrwin.Leg('cash', 'Cash and deposits', L(_d['cash_and_deposits_usdbn']), 'derived',
                  '官方 2023-01 才把 Cash and Deposits 单列进月度表')]
_w19 = mrwin.resolve('lines_endlabels', _l19, XL25, 0)
_i19 = _d.index[_w19.start:]
_ex19 = {
    'n': 19, 'kind': 'lines_endlabels', 'title': 'Cash sweep vs. cash and deposits',
    'xlabels': XL25[_w19.start:], 'xstep': xstep_for(len(XL25) - _w19.start),
    'fmt': 'usd1', 'ylab': '$bn',
    'series': [{'name': nm, 'color': c, 'values': _w19.cut(leg.vals)}
               for leg, nm, c in zip(_l19, ('Cash sweep (off balance sheet)',
                                            'Cash and deposits'), ('NAVY', 'MBLUE'))
               if not leg.drop],
    'note': 'In Feb-2026 the first $10k of enrolled balances per customer moved to '
            'free credit balances to fund margin lending, shifting over $6bn between '
            'these two lines. The y/y decline in cash sweep after that date is '
            'mechanical, not customer attrition — read the two lines together. '
            + _w19.why,
}
# 断点标签是从绘图区顶端往下竖排的，字越长挂得越深。原来的 'High-Yield Cash change'
# 正好挂到 Cash sweep 那条深蓝线的拐点上，红字与深蓝线在交叉处互相糊掉。
# 完整说法在图注里，标签只留能认出是哪件事的最短形式。
_bk19, _seg19 = breaks_for(19, _i19, BK_SWEEP)
_ex19.update(_bk19)
if _seg19:
    _ex19['note'] += f' 红色竖虚线为口径断点：{_seg19}；线右侧与左侧不可直读。'
EX.append(_ex19)

_l20 = [mrwin.Leg('tot', 'Total securities lending revenue', L(_d['seclend_total_usdmn']),
                  'primary', '出借业务 2022-05 才上线，之前官方那一格印 NA'),
        # Net 那一行更晚，挂 derived 才会在图注里被点名（见 Ex19 上面那段注释）
        # 原来这条用 C.BLUE(#9DC3E6)：它是柱图的填充色，画成 1.8px 的细线、
        # 端点标签又拿它当字色时，白底上的对比度只有 1.9:1，「$10」「$2」两个端点值
        # 要凑近才看得清。MBLUE(#2E75B6) 是同色系的线条色，对比度 4.8:1。
        mrwin.Leg('net', 'Securities lending, net', L(_d['seclend_net_usdmn']),
                  'derived', 'Net 那一行 2023-01 才单列进月度表')]
_w20 = mrwin.resolve('lines_endlabels', _l20, XL25, 0)
EX.append({
    'n': 20, 'kind': 'lines_endlabels', 'title': 'Securities lending revenue',
    'xlabels': XL25[_w20.start:], 'xstep': xstep_for(len(XL25) - _w20.start),
    'fmt': 'usd0', 'ylab': '$mn / month',
    'series': [{'name': nm, 'color': c, 'values': _w20.cut(leg.vals)}
               for leg, nm, c in zip(_l20, ('Total securities lending revenue',
                                            'Securities lending, net'), ('NAVY', 'MBLUE'))
               if not leg.drop],
    'note': 'Net excludes interest on cash collateral for margin-based lending, so the '
            'gap between the two lines widens as the margin book grows. ' + _w20.why,
})

# 两个期末数之比（期末资产 ÷ 期末客户数）：按**存量**处理，右轴点对点同比。
# 它不走 ratio_note：分子分母同为存量、量纲同源，12 个月滚动均值同比在这里其实是
# 合法的（等价于「去年一年的平均资产 ÷ 去年一年的平均客户数」的近似），
# 所以理由必须由实测给出，而不是「比率不能平滑」。
# 「其实是合法的」这句话原先只是一条注释里的断言 —— 现在由 quot_stock() 当场量：
# 均值口径与分母加权口径差多少现算，差大了就停机（见该函数）。
quot_stock(21, tpa, df['funded_customers_mn'], '户均资产')
lvl(21, df['assets_per_customer_usdk'], 'Assets per funded customer', win=len(W25), fmt='usd1',
    ylab='$k per customer', breaks=BK_CUST, flow=False, what='户均资产（两个期末数之比）',
    note='Total platform assets / funded customers. Rises when existing customers '
         'deposit or markets rally, falls when acquisitions bring in customers with '
         'smaller balances.')

# ══════════════════════ 长历史 ══════════════════════
EX.append({
    # 长历史图务必给 zero_base + end_label：不给 zero_base 时引擎走的是
    # y0 = min − 极差×5%，那是一次没有任何标注的隐性截轴，会把整段的增长幅度
    # 凭空放大；不给 end_label 就没有任何绝对水平锚点，只能拿眼睛去够刻度。
    'n': N_HIST, 'kind': 'lines', 'title': 'Total platform assets — full published history',
    'xlabels': XL_LONG, 'xstep': xstep_for(len(XL_LONG)),
    'fmt': 'usd0', 'label_fmt': 'usd0', 'ylab': '$bn',
    'zero_base': True, 'end_label': True,
    'series': [{'name': 'Total platform assets', 'color': 'NAVY', 'values': L(tpa)}],
    'note': f'{mlab(df.index[0])} 起的全部官方月度披露。'
            'The current monthly file only publishes a rolling three-year window; the '
            f'months before {mlab(pd.Period("2023-04", "M"))} come from the earliest '
            'earnings supplement that still carries them (Q1-23 for 2021-01~2022-12, '
            'Q1-26 for 2023-01~03) — 取的一律是<b>能拿到的最早那一版</b>，不是后来重述过的值。'
            f'{mlab(df.index[0])} 是天花板：公司 2022-04 才开始月度披露、首期回填 12 个月，'
            '更早的数只存在于 S-1 与 10-Q，且不是月度粒度。'
            '这一段口径叫 Assets Under Custody（后改名 Total Platform Assets，见 Exhibit 2）。'
            'Axis starts at zero, so the slope on this chart is the real slope.',
})

_qs = nd.groupby(nd.index.asfreq('Q')).agg(['sum', 'count'])
_qsum = _qs['sum']
_qyoy = np.array([(_qsum.values[i] / _qsum.values[i - 4] - 1) * 100
                  if i >= 4 and _qsum.values[i - 4] else np.nan for i in range(len(_qsum))])
_nlast = int(_qs['count'].iloc[-1])
# ⚠ 两张季度柱图（本图与 Exhibit 26）都**通栏**，左端也都仍写死在近 13 季。
# 这两件事是同一条几何约束的两半，都不是美学偏好，推导如下：
#
#   `charts.js` 的 qtr_bar 把右轴 y/y 的**末点读数**画在「最后一个可比 y/y」右侧 5px
#   （:1547 的 `Xc(jq) + 5`）；而 `lineVals()` 会把未满季那一点丢掉（拿 1 个月比去年
#   3 个月是口径错误，引擎在这一层就拦住了）。于是末季未满时 jq 是**倒数第二根**柱，
#   读数正好画进最后一根柱那一格里 —— 而那一格已经有一个竖排的柱顶数值，且 qtr_bar 的
#   柱顶标签**每根都画、一个不抽**（见 mrwin.VLABEL_KINDS 上面那段）。两段文字要错开，
#   需要 band ≥ 5px 偏移 + 末点读数宽 + 竖排标签行盒半宽。
#
#   · 半栏 13 季的 band 装不下这个和。撞不撞取决于 y/y 与柱高这个月恰好落在哪 ——
#     等于每个月重掷一次骰子：2026-08-19 这一轮 Exhibit 23 掷中了（「$5.6」压「57%」，
#     实测墨迹相交 36.6px²），Exhibit 26 没中。所以两张一起通栏，不然只是把下个月的
#     骰子交给另一张（band 现算写进各自图注，不写死）。
#   · 那为什么不顺手把窗口铺到全部季度？因为 768px 窄屏本来就是单列、通栏在那里无效
#     （`.card.wide` 只是 `grid-column: 1/-1`）。实测把两张都铺满全部季度：Exhibit 23 在
#     768 下当场压成 🔴（66.8px²）。所以窗口维持近 13 季，被略去的季度数现算写进图注
#     （页尾「序列起点」那一条承诺了「各图图注里都写了截在哪一期」，不写就是假话）。
_w = _qsum.iloc[-13:]                                       # fixed-left: 23


def _qtr_cut(ex, what, avail, drawn):
    """两张季度柱图的自报 + 挂号。挂号与自报同生同灭：今天真没截就两边都不说。

    `avail` / `drawn` 传季度标签本身（不是个数），由 `_fix_left()` 现算并兜底。
    定义性分量只有柱自己：右轴 y/y 前几季算不出来照样画得出柱。
    """
    if not _fix_left(ex['n'], what, drawn, avail, ' 季'):
        return ''
    n_all, n_win = len(avail), len(drawn)
    return (
            f'<b>本图通栏，左端也是排版决定的</b>：月度序列能聚合出 {n_all} 个季度，'
            f'本图只画最后 {n_win} 个（更早的 {n_all - n_win} 季被略去）。'
            '定住这两件事的是右轴 y/y 的<b>末点读数</b>：引擎把它画在「最后一个可比 y/y」'
            '的右侧，而末季未满时那一点是倒数第二根柱 —— 读数于是落进最后一根柱那一格，'
            '那里已经有一根竖排的柱顶数值。半栏每季只有 '
            f'{mrwin.band_px(ex, full=False):.0f}px、两段文字错不开，通栏后是 '
            f'{mrwin.band_px(ex, full=True):.0f}px（两个数都由构建期按 '
            '<code>assets/charts.js</code> 的量边距算式复算，不是目测）。'
            '窗口没有跟着铺满，是因为 <b>768px 窄屏本来就是单列、通栏在那里不起作用</b>：'
            f'2026-08-19 实测把两张季度柱图都铺满全部季度，Exhibit {N_QTR_ND} 在 768 下'
            f'当场把这两段文字压在一起；维持 {n_win} 季则两个视口都不压。')


_ex23 = {
    'n': N_QTR_ND, 'kind': 'qtr_bar', 'title': 'Net deposits by quarter', 'full': True,
    'xlabels': [str(p) for p in _w.index], 'fmt': 'usd1', 'label_fmt': 'usd1',
    'ylab': '$bn per quarter', 'ylab2': 'y/y (季度合计)',
    'legend': 'Complete quarter', 'values': L(_w),
    'partial_months': _nlast, 'qtr_months': 3,
    # 名字里带口径：本页现在同时有三种同比口径（单月 / 季度合计 / 季度均值），
    # 图例上不写清楚，读者把这条绿线跟 Exhibit 3 的绿线放一起看必然对不上。
    'line': {'name': 'y/y (季度合计, RHS)', 'color': 'GREEN',
             'values': L(pd.Series(_qyoy, index=_qsum.index).iloc[-13:]),   # fixed-left: 23
             'yfmt': 'pct0'},
    'note': 'Quarterly totals remove the month-length and month-end timing noise in the '
            'monthly series. '
            '右轴是<b>季度合计同比</b>（本季 3 个月合计 ÷ 去年同季 3 个月合计 − 1）。'
            f'Exhibit 3 右轴与 Exhibit 1 汇总表的 y/y 列现在<b>都是单月同比</b>（同一个口径），'
            '而本图这条不是 —— 分母是去年那三个月，不是去年那一个月。'
            '两者当期读数并排见页尾「同比口径」那一条。',
}
_ex23['note'] += (_qtr_cut(_ex23, '季度净流入', _drawable(_qsum), _w.index)
                  + ('' if _nlast >= 3 else
                     ' Latest bar is quarter-to-date and not comparable to full quarters.'))
EX.append(_ex23)

# ⚠ `[-4:]` 是**排版上限**（从原 deck 抄来的 n_years），不是数据边界：净流入在
# 2021/2022 两年都有整年的数，被这一刀静默丢掉过一整轮 —— 页尾却对读者写着
# 「除点名的三张外都是数据决定的」。上限保留（线再多就分不清哪条是哪年），
# 但必须挂号 + 在图注里自报丢了哪几年、丢了多少个月。
N_YEAR_LINES = 4
_yrs_all = sorted({p.year for p in nd.dropna().index})
_yrs = _yrs_all[-N_YEAR_LINES:]                             # fixed-left: 24
_ylines = []
for _y in _yrs:
    sub = nd[[p.year == _y for p in nd.index]].cumsum()
    vals = [None] * 12
    for p, v in sub.items():
        vals[p.month - 1] = round(float(v), 6)
    _ylines.append({'name': str(_y), 'values': vals})
# 哪几条线不是整年、为什么，一律现算：序列左端往前推之后「2023 只有 4~12 月」那句
# 会变成假话（2023 现在是完整的 12 个月），而那种错没有任何自动化能发现。
_part = [(y, sum(1 for v in ln['values'] if v is not None))
         for y, ln in zip(_yrs, _ylines)
         if sum(1 for v in ln['values'] if v is not None) < 12]
_pnote = ('' if not _part else ' ' + '；'.join(
    f'{y} 线只有 {n} 个月'
    + ('（本年尚未走完）' if y == LATEST.year
       else f'（官方月度披露自 {mlab(df.index[0])} 起，这一年被序列左端截断）')
    for y, n in _part) + ' —— 与整年线不可直读。')
_ydrop = _yrs_all[:len(_yrs_all) - len(_yrs)]
_ydrop_n = int(sum(1 for _p in nd.dropna().index if _p.year in _ydrop))
_ycut = ('' if not _fix_left(24, '逐年净流入路径', _yrs, _yrs_all, ' 年') else
         f' <b>画哪几年是排版决定的，不是数据决定的</b>：本图只画最近 {len(_yrs)} 年'
         f'（year_lines 的 n_years 上限，抄自原 deck），而净流入在 '
         f'{"、".join(str(_y) for _y in _ydrop)} 同样有数（{_ydrop_n} 个月）却没有画 —— '
         '线再多就分不清哪条是哪年了。那几年的逐月净流入见 Exhibit 3（全窗口）。')
EX.append({
    'n': 24, 'kind': 'year_lines', 'title': 'Net deposits path by year',
    'xlabels': MON, 'fmt': 'usd0', 'label_fmt': 'usd0', 'ylab': '$bn cumulative',
    'series': _ylines, 'highlight': len(_ylines) - 1,
    'note': 'Cumulative within each calendar year.' + _pnote + _ycut,
})

# 混合占比（两条流量之比）：序列本身以 % 计量，走比率那条硬约束（flow=False +
# pct_series=True）—— 12 个月的占比做算术平均没有意义，滚动均值同比在这里非法。
# 它同时是个被 0–100 夹住的份额，分母不会趋零，同比 pp 差本来就不会爆掉；
# Bitstamp 从 ~4% 涨到 ~57% 是一次真实的结构性迁移，不是噪音，平滑掉反而看不见拐点。
# 口径写进图例（`y/y (pp, 单月, RHS)`）。
# ⚠ `win=15` 已删（2026-08-19）：与 Exhibit 9 同一个漂移窗口的毛病 —— 15 个月今天正好
# 含 1 个并表前的月份，下个月一个都不剩。改成跟着 W25 走，左端交给 mrwin.resolve()，
# 它按 crypto_bitstamp_share 自己的首值（2023-01，官方拆分行第一次出现的月）裁。
lvl(25, df['crypto_bitstamp_share'], 'Bitstamp share of crypto volume', fmt='pct0',
    ylab='% of crypto ADV', pct_series=True, breaks=BK_CRYPTO,
    flow=False, what='加密成交量里 Bitstamp 的占比',
    left_zh='官方的加密成交量拆分行（Robinhood App / Bitstamp）逐月只印到 2023-01，'
            '更早的月度表只有一个加密总数、没有分母以外的那一半',
    ratio_extra='另外两点：它是被 0–100 夹住的份额，分母是同期加密总量、不会趋零，'
                '所以百分点差本来就不存在小基数爆炸；而 Bitstamp 在并表当月一步从 '
                f'{float(df["crypto_bitstamp_share"].loc[BRK_BITSTAMP - 1]):.0f}% 跳到 '
                f'{float(df["crypto_bitstamp_share"].loc[BRK_BITSTAMP]):.0f}%、'
                f'其后最高到过 {float(df["crypto_bitstamp_share"].max()):.0f}%，'
                '是一次真实的结构性迁移，任何平滑都会把那个拐点抹掉。'
                '（真要一个「过去一年的 Bitstamp 占比」，正确做法是滚动 12 个月的 '
                'Bitstamp 成交量 ÷ 滚动 12 个月的加密总成交量 —— 那是量加权，'
                '不是把 12 个月的占比平均；本图不画它，因为拐点才是这张图的题眼。）',
    note='Institutional crypto now runs above half of total crypto volume but earns a '
         'far lower take rate than the retail app, which is why crypto revenue has '
         'not followed crypto volume. '
         '这是<b>份额</b>不是水平值：分母是同期加密总量，不会趋零，所以它的同比百分点差'
         '不存在小基数爆炸的问题。')

_dq = df['dats_total_mn'].groupby(df.index.asfreq('Q')).agg(['mean', 'count'])
_dmean = _dq['mean']
_dyoy = np.array([(_dmean.values[i] / _dmean.values[i - 4] - 1) * 100
                  if i >= 4 and _dmean.values[i - 4] else np.nan for i in range(len(_dmean))])
_dlast = int(_dq['count'].iloc[-1])
_wd = _dmean.iloc[-13:]                                     # fixed-left: 26（_qtr_cut 挂号）
_ex26 = {
    'n': N_QTR_DATS, 'kind': 'qtr_bar', 'title': 'Total daily average trades by quarter',
    # 通栏的理由与 Exhibit 23 同源（见 _qtr_cut 上面那段）：本月它没撞上，只是因为
    # y/y 与柱高恰好错开了 —— 几何约束是一样的，只改撞上的那一张等于把骰子留给下个月。
    'full': True,
    'xlabels': [str(p) for p in _wd.index], 'fmt': 'f1', 'label_fmt': 'f1',
    'ylab': 'mn trades / day', 'ylab2': 'y/y (季度均值)',
    'legend': 'Complete quarter', 'values': L(_wd),
    'partial_months': _dlast, 'qtr_months': 3,
    'line': {'name': 'y/y (季度均值, RHS)', 'color': 'GREEN',
             'values': L(pd.Series(_dyoy, index=_dmean.index).iloc[-13:]),  # fixed-left: 26
             'yfmt': 'pct0'},
    'note': 'Quarterly average of the three asset classes; removes the month-length '
            'differences between equity trading days and crypto calendar days. '
            '右轴是<b>季度均值同比</b>（本季 3 个月均值 ÷ 去年同季 3 个月均值 − 1），'
            '口径与各张时序柱图右轴的<b>单月</b>同比不同（分母是去年那三个月，'
            '不是去年那一个月）。哪几张画了右轴同比线由构建期现算，见页尾「同比口径」那一条。',
}
_ex26['note'] += (_qtr_cut(_ex26, '季度 DATs', _drawable(_dmean), _wd.index)
                  + ('' if _dlast >= 3 else
                     ' Latest bar is quarter-to-date and not comparable to full quarters.'))
EX.append(_ex26)


def heat(n, s, title, note, legend, what, n_years=4, fmt='f0'):
    """热力矩阵。⚠ `n_years` 是**排版上限**不是数据边界 —— Exhibit 27 就因此丢过
    2021/2022 两整年而一个字没说。丢了就挂号、就自报；没丢就两边都不说。"""
    ss = s.dropna()
    yrs_all = sorted({p.year for p in ss.index})
    yrs = yrs_all[-n_years:]                                # fixed-left: 27,28
    M = [[None] * 12 for _ in yrs]
    for p, v in ss.items():
        if p.year in yrs and np.isfinite(v):
            M[yrs.index(p.year)][p.month - 1] = round(float(v), 6)
    if _fix_left(n, what, yrs, yrs_all, ' 年'):
        _drop = yrs_all[:len(yrs_all) - len(yrs)]
        _ncell = int(sum(1 for p in ss.index if p.year in _drop))
        note += (f' <b>画哪几年是排版决定的，不是数据决定的</b>：本表只画最近 '
                 f'{len(yrs)} 年（n_years={n_years} 的排版上限），而 '
                 f'{"、".join(str(y) for y in _drop)} 同样有数'
                 f'（共 {_ncell} 格）却没有进表。')
    EX.append({
        'n': n, 'kind': 'heat_matrix', 'title': title,
        'rows': [str(y) for y in yrs], 'cols': MON, 'matrix': M,
        'fmt': fmt, 'legend': legend, 'row_head': '年', 'cell_h': 20, 'note': note,
    })


# 两张热力矩阵属 CONTRACT §6.3 的**图型豁免**（heat_matrix 每一格本来就是一个月的
# 读数）：逐格的月度波动与季节形状就是热力图的题眼。豁免不等于可以不写口径 ——
# 标题里必须写「单月」，读者才知道格子里那个数是怎么算的。
# ⚠ 2026-09 起页上其余各图的右轴也统一成单月口径，所以这两张与它们**同口径**了；
# 旧稿那句「不是 Exhibit 4 / 7 右轴的滚动口径」已经不成立，逐句改掉，别留着。
heat(27, df['organic_growth_ann'], 'Annualised organic growth rate — 单月年化 (%)',
     'Green = faster organic growth. Colour scale runs on the 5–95 percentile of all '
     'finite cells, so one outlier month does not flatten the table. '
     '格内是<b>单月</b>年化增速的<b>水平值</b>（当月净流入 x 12 ÷ 上月末资产），不是同比 —— '
     'Exhibit 4 的柱画的是同一条序列，它的右轴则是这条序列的单月同比（百分点差）。'
     '逐格的季节形状正是这张图要看的东西。',
     'Annualised organic growth, 单月 (%)', what='年化有机增速热力矩阵')
# ⚠ 这里原先写的是 `df['adv_equity_usdbn'].pct_change(12) * 100` —— 数值上与
# mom_yoy_of() 对这条序列逐月相同：两者只差 mom_yoy 多的那道「基期为 0 或两期异号
# 则留空」的护栏，而本列自首值起全程为正、既无 0 也无负值，那道护栏一格都没触发
#（改动当轮逐月对过，两条序列的差是 0 行；序列若哪天出现 0 或负值，改走共享模块
# 之后会自动多留一格空，那才是对的），
# 但那是同比的第二份实现，而全仓只准有一份（build/yoy.py）。改走共享模块之后，
# 下面那句「与 Exhibit 7 右轴那条线同口径」不再是「两段代码碰巧算出同一个数」，
# 而是字面上同一个函数。
_adv_yoy = mom_yoy_of(df['adv_equity_usdbn'])
_adv0 = df['adv_equity_usdbn'].dropna().index[0]
heat(28, _adv_yoy, 'Equity notional ADV y/y — 单月同比 (%)',
     # 「表从哪一格开始」不写死：ADV 那一节官方 2023-01 才印，同比又要去年同月的基数，
     # 所以第一格是 ADV 起点 + 12 个月。回填把序列左端推到 2021-01 之后，
     # 旧稿那句「2024 starts in April」已经不成立了 —— 改成现算。
     'Green = faster growth. Average daily volumes are only published from '
     f'{mlab(_adv0)}, and a y/y cell needs the same month a year earlier, so the first '
     f'cell in this table is {mlab(_adv_yoy.dropna().index[0])}. '
     '格内是<b>单月同比</b>（本月 ÷ 去年同月 − 1）'
     # Exhibit 7 的右轴只有在可比点覆盖率过线时才存在（不够就退成柱上标数），
     # 所以这句话得看 AXIS_KIND 现说，不能写死。
     + ('，与 Exhibit 7 右轴那条线<b>同口径</b>（同一条序列、同一个分母，'
        '逐月读数应当对得上）。' if AXIS_KIND.get(7) == 'flow'
        else '；Exhibit 7 本轮没有右轴同比线（窗口内可比点覆盖率不够，'
             '判据见页尾），确切的 y/y 在 Exhibit 1 汇总表里。'),
     'Equity notional ADV y/y, 单月 (%)', what='股票名义 ADV 同比热力矩阵')


# ────────────────────────── Exhibit 1：汇总表 ──────────────────────────
CUR, PRV, YAG = LATEST, LATEST - 1, LATEST - 12


MARK = '<sup>†</sup>'     # 该格的比较区间跨过口径断点


def chg_cell(a, b, mode, inv, crossed=False):
    """一格变动。crossed=True 表示比较区间跨过口径断点：数值照登（读者要知道披露口径下
    的读数是多少），但**不涂红绿** —— 涂色是「这是好消息 / 坏消息」的判断，而跨断点的
    两端根本不是同一个口径下的数，这个判断做不了。改用 † 提示，理由写在表注里。"""
    if not (np.isfinite(a) and np.isfinite(b)):
        return {'v': '—'}
    if mode == 'pp':
        v = a - b
        txt = f'{v * 100:+.0f}bp' if abs(v) < 1 else f'{v:+.2f}pp'
    else:
        if b == 0 or a * b < 0:
            return {'v': '—'}
        v = (a / b - 1) * 100
        txt = f'{v:+.1f}%'
    if crossed:
        return {'v': txt + MARK, 'cls': ''}
    good = (v < 0) if inv else (v > 0)
    return {'v': txt, 'cls': 'pos' if good else 'neg'}


# 每行末位是该序列受哪些口径断点影响。原版只在表注里写「y/y for those rows is not
# like-for-like」，对 m/m 一字未提 —— 而 WonderFi 的断点就落在本月，入金客户 m/m 印的
# +2.5% 里有四成来自并购，还照涂绿色。跨不跨断点由 spans() 现算，窗口滚动自动跟上。
SUM = [
    ('g', 'Customers and assets'),
    ('r', 'Total platform assets ($bn)', tpa, 0, '$', False, BK_TPA),
    ('r', 'Net deposits ($bn)', nd, 1, '$', False, BK_ND),
    ('r', 'Annualised organic growth (%)', df['organic_growth_ann'], 1, '', True, BK_ND),
    ('r', 'Funded customers (mn)', df['funded_customers_mn'], 1, '', False, BK_CUST),
    ('r', 'Assets per funded customer ($k)', df['assets_per_customer_usdk'], 1, '$', False, BK_CUST),
    ('g', 'Trading — average daily volumes'),
    ('r', 'Equity notional ($bn/day)', df['adv_equity_usdbn'], 1, '$', False, []),
    ('r', 'Options contracts (mn/day)', df['adv_options_mn'], 1, '', False, []),
    ('r', 'Crypto notional ($mn/day)', df['adv_crypto_usdmn'], 0, '$', False, BK_CRYPTO),
    ('r', '&nbsp;&nbsp;of which Bitstamp ($mn/day)', df['adv_crypto_bitstamp_usdmn'], 0, '$', False, BK_CRYPTO),
    ('r', 'Event contracts (mn/day)', df['adv_event_mn'], 0, '', False, []),
    ('r', 'Total DATs (mn/day)', df['dats_total_mn'], 1, '', False, []),
    ('g', 'Interest-earning assets ($bn)'),
    ('r', 'Margin book', df['margin_book_usdbn'], 1, '$', False, []),
    ('r', 'Cash sweep', df['cash_sweep_usdbn'], 1, '$', False, BK_SWEEP),
    ('r', 'Cash and deposits', df['cash_and_deposits_usdbn'], 1, '$', False, BK_SWEEP),
    ('r', 'Securities lending revenue ($mn)', df['seclend_total_usdmn'], 0, '$', False, []),
]

srows = []
blank_rows = []          # 分位留空的行 + 原因，写进表注
# 汇总表的 y/y 列一直是单月口径：它恒等于表内算术「本月 ÷ 去年同月」，读者拿第一列除
# 第三列就能验算。2026-09 各图右轴也改成单月之后，这一列与图上那条线**同口径**了 ——
# 但组标题上的口径标注不能因此省掉：本页仍有季度合计 / 季度均值两种同比在别的图上。
GRP_SUFFIX = '　·　y/y 列 = 单月口径（本月 ÷ 去年同月）'
for item in SUM:
    if item[0] == 'g':
        srows.append({'kind': 'group', 'label': item[1] + GRP_SUFFIX})
        continue
    _, lab, s, dec, money, pct, bks = item
    ss = s.dropna()
    mode = 'pp' if pct else 'ratio'
    c = float(ss.get(CUR, np.nan)) if CUR in ss.index else np.nan
    p1 = float(ss.get(PRV, np.nan)) if PRV in ss.index else np.nan
    p12 = float(ss.get(YAG, np.nan)) if YAG in ss.index else np.nan
    # 分位一律走 build/pctile.py：判据是口径，口径只能有一处定义。本页原先那份
    # 「≥90% 月环比不降就留空」的代理判不出 margin book（近 24 个月 18 个月钉 100），
    # 同一张表里回放比例更低的 funded customers 反而被留空，同表内自相矛盾。
    hist = [float(v) for v in ss.values]
    pv, pcls = pctile.cell(hist)
    why = pctile.why_blank(hist)
    if not pv and why:
        blank_rows.append((lab.replace('&nbsp;', '').strip(), why))
    srows.append({'label': lab, 'cells': [
        {'v': fnum(c, dec, money, pct), 'cls': 'cur'},
        {'v': fnum(p1, dec, money, pct)},
        {'v': fnum(p12, dec, money, pct)},
        chg_cell(c, p1, mode, False, any(spans(p, PRV, CUR) for p, _l in bks)),
        chg_cell(c, p12, mode, False, any(spans(p, YAG, CUR) for p, _l in bks)),
        {'v': pv, 'cls': pcls},
    ]})

_by_why = {}
for _lab, _why in blank_rows:
    _by_why.setdefault(_why, []).append(_lab)
_blank_txt = ('；'.join(f'{"、".join(labs)}：{why}' for why, labs in _by_why.items())
              if blank_rows else '本表当前没有因此留空的行')
_fc_ex_txt = (f'例如入金客户 m/m 印 {FC_MM:+.1%}，剔除 WonderFi 带进的 '
              f'{WONDERFI_CUSTOMERS_MN * 1000:.0f}k 客户后约 {FC_MM_EX:+.1%}；'
              '总平台资产与户均资产里的并购贡献公司未单独披露，无法同样还原。'
              if FC_MM_EX is not None else '')

# ── 同页两种口径的当期读数：全部现算，供表注与页尾口径说明并排印出 ──
# 净流入是本页口径混用最严重的一条：同一条序列在三张不同的图上有三个都叫「y/y」的数。
def _my(s):
    """单月同比（%）。"""
    s = s.dropna()
    p = s.index[-1]
    return float(s.iloc[-1] / s.loc[p - 12] - 1) * 100 if (p - 12) in s.index else None


def _ry(s):
    """12 个月滚动合计同比（%）。"""
    v = roll_yoy_of(s).dropna()
    return float(v.iloc[-1]) if len(v) else None


def _qy(s, how='sum'):
    """最后一个**满 3 个月**季度的季度合计（或均值）同比（%），连同季度标签一起返回。"""
    s = s.dropna()
    g = s.groupby(s.index.asfreq('Q'))
    agg, cnt = (g.sum() if how == 'sum' else g.mean()), g.count()
    full = [p for p in agg.index if int(cnt.loc[p]) == 3 and (p - 4) in agg.index
            and agg.loc[p - 4]]
    if not full:
        return None, None
    p = full[-1]
    return float(agg.loc[p] / agg.loc[p - 4] - 1) * 100, p


ND_M, ND_R = _my(nd), _ry(nd)
ND_Q, ND_QP = _qy(nd)
# 本页口径差距最大的一处，现算不写死：同一条净流入，Exhibit 1 汇总表与 Exhibit 3 右轴
# 印单月（2026-09 起同口径）、Exhibit N_QTR_ND 的绿线印季度合计；滚动口径只作对照。
_MIX_ND = ''
if None not in (ND_M, ND_Q):
    _MIX_ND = (f'<b>本页口径差距最大的一处就在净流入</b>：{mlab(LATEST)} 的单月同比 '
               f'{ND_M:+,.1f}%（本表 y/y 列，也是 Exhibit 3 右轴画的那条线）'
               f'vs Exhibit {N_QTR_ND} 末满季 {ND_QP} 的'
               f'季度合计同比 {ND_Q:+,.1f}% —— 同一条序列，两个都叫 y/y，'
               f'<b>相差 {abs(ND_M - ND_Q):,.0f}pp</b>'
               + (f'；作对照的 12 个月滚动合计同比（本页<b>不画</b>，只在 Exhibit 3 '
                  f'的图注与本条里报数）是第三个数 {ND_R:+,.1f}%'
                  f'（与单月差 {abs(ND_M - ND_R):,.0f}pp）。' if ND_R is not None else '。')
               + '差距来自分母：单月比的是去年那一个月，季度比的是去年那三个月，'
               '滚动比的是去年那一整年 —— 三个都对，换的是分母不是对错。'
               '本页统一画单月（所有者指定），它的毛刺代价印在各流量图的图注里。')

_EQ_M, _EQ_R = _my(df['adv_equity_usdbn']), _ry(df['adv_equity_usdbn'])


def _axis_named(kind):
    """右轴口径 → 「Exhibit n（中文名）」串。名单由 lvl() 实际画出来的东西现生成。

    手写这份名单栽过：y/y 覆盖率低于 YOY_MIN_COVER 时 lvl() 会把整张图退成
    bars_labeled（右轴连线都没有），而写死在页尾的「Exhibit 7 / 8 的右轴画了同比线」
    不会自己知道。2026-09 换单月口径那一轮又反过来栽了一次：单月只要 12 个月历史，
    Exhibit 7 / 8 的覆盖率当场从 47% 升到 72%、线自己回来了。序列一回填、口径一变、
    覆盖率一变，名单就该跟着变 —— 所以它必须是算出来的。
    """
    return '、'.join(f'Exhibit {n}（{AXIS_ZH[n]}）'
                     for n in sorted(AXIS_KIND) if AXIS_KIND[n] == kind) or '（本轮一张都没有）'


_AX_FLOW, _AX_MONO = _axis_named('flow'), _axis_named('mono')
_AX_NONE = _axis_named(None)
# ⚠ 页尾口径说明原先写「前四张保留点对点是实测结论」「Exhibit 25 不同」—— 两处都是
# 手数出来的，而上面这份名单是现算的：名单一变（多一张存量图、或某张覆盖率掉线退成
# bars_labeled），「前四张」就指错人。改成从同一份名单里切。
_MONO_STOCK = [n for n in sorted(AXIS_KIND)
               if AXIS_KIND[n] == 'mono' and n not in AXIS_RATIO]
_MONO_RATIO = [n for n in sorted(AXIS_KIND)
               if AXIS_KIND[n] == 'mono' and n in AXIS_RATIO]


def _exlist(ns):
    return '、'.join(f'Exhibit {x}' for x in ns) or '（本轮一张都没有）'


def _quot_note():
    """「同样是相除、却按存量处理」的那几张的现算说明。

    只列今天真的还在 (2) 名单里的那几张：Exhibit 21 哪天覆盖率掉线退成 bars_labeled，
    它就不在 _MONO_STOCK 里，这一句也就自动消失，不会留下一条指着页外的解释。
    """
    q = [(n, zh, gap) for n, (zh, gap) in sorted(_QUOT_STOCK.items()) if n in _MONO_STOCK]
    if not q:
        return ''
    return ('（判据是「序列本身以 % 计量」，不是「是不是两条序列相除」：'
            + '；'.join(
                f'Exhibit {n}（{zh}）同样是两条序列相除，但分子分母都是<b>月末时点存量</b>，'
                f'12 个月均值口径同比与分母加权口径同比实测最大只差 {gap:.2f}pp'
                for n, zh, gap in q)
            + f'，低于 {RATIO_EQUIV_MAX_PP:g}pp 的停机线 —— 这个差额是构建期现算的，'
              '超线就不出页，所以它按存量处理。）')

summary = {
    'title': f'Robinhood monthly metrics — {mlab(LATEST)}',
    'heads': [mlab(CUR), mlab(PRV), mlab(YAG), 'm/m', 'y/y 单月', '3Y %ile'],
    'sep': 3,
    'rows': srows,
    'note': f'口径断点：Bitstamp 自 {BRK_BITSTAMP} 并入净流入、加密成交量与客户数；'
            f'TradePMR 的流量自 {BRK_TRADEPMR} 并入净流入；High-Yield Cash 改版于 {BRK_SWEEP} '
            f'把逾 $6bn 从 Cash sweep 挪到 Cash and deposits；WonderFi 自 {BRK_WONDERFI} '
            f'带进约 {WONDERFI_CUSTOMERS_MN * 1000:.0f}k funded customers（股权交易，不是自然获客）；'
            f'Trump Account 自 {BRK_TRUMP} 起并入总平台资产（Robinhood 托管部分）与净流入'
            f'（缴款），<b>但不计入 funded customers</b>。'
            f'带 {MARK} 的格子表示<b>该格的比较区间跨过上述断点</b>，两端不是同一个口径下的数，'
            f'因此数值照登、但不涂红绿。{_fc_ex_txt}'
            '3Y %ile = 当月读数在近 36 个月里高于多少百分比的观测，判据统一取自 '
            '<code>build/pctile.py</code>（全站唯一实现）：把这一行的分位回放近 24 个月，'
            f'若 ≥70% 的月份钉在区间端点，说明这一列对该行没有区分度，留空 —— {_blank_txt}。'
            '比率行的差异用 pp / bp，不用百分比变化。'
            '<br><b>本表的 y/y 列是「单月口径」= 本月 ÷ 去年同月 − 1，'
            '与各时序图右轴现在<b>同一个口径</b>（2026-09 起全站统一，页面所有者指定）。</b>'
            '这一列同时恒等于表内算术（第一列 ÷ 第三列），读者可以直接验算。'
            f'本轮右轴真的画出同比线的图是：流量类 {_AX_FLOW}；存量／比率类 {_AX_MONO}'
            '（这两份名单由构建期按各图实际画出来的东西现生成，不手写）。'
            f'仍与本列不同口径的只有两张季度柱图：Exhibit {N_QTR_ND}（季度合计）与 '
            f'Exhibit {N_QTR_DATS}（季度均值）。' + _MIX_ND,
}

# ────────────────────────── 核对表（官方原始单位，未换算）──────────────────────────
TCOLS = [
    ('Funded customers (mn)', 'fc', 'funded_customers_mn', 1),
    ('Total platform assets ($bn)', 'tpa', 'total_platform_assets_usdbn', 1),
    ('Net deposits ($bn)', 'nd', 'net_deposits_usdbn', 1),
    ('Equity notional ADV ($bn)', 'aeq', 'adv_equity_usdbn', 1),
    ('Options ADV (mn contracts)', 'aop', 'adv_options_mn', 1),
    ('Crypto ADV ($mn)', 'acr', 'adv_crypto_usdmn', 0),
    ('of which Bitstamp ($mn)', 'abs', 'adv_crypto_bitstamp_usdmn', 0),
    ('Event contracts ADV (mn)', 'aev', 'adv_event_mn', 0),
    ('Equity DATs (mn)', 'deq', 'dats_equity_mn', 1),
    ('Options DATs (mn)', 'dop', 'dats_options_mn', 1),
    ('Crypto DATs (mn)', 'dcr', 'dats_crypto_mn', 1),
    ('Margin book ($bn)', 'mb', 'margin_book_usdbn', 1),
    ('Cash sweep ($bn)', 'cs', 'cash_sweep_usdbn', 1),
    ('Cash and deposits ($bn)', 'cd', 'cash_and_deposits_usdbn', 1),
    ('Sec. lending revenue ($mn)', 'sl', 'seclend_total_usdmn', 0),
    ('Eq/opt trading days', 'td', 'eqopt_trading_days', 1),
]
trows = []
for p in W13:
    row = {'xl': mlab(p)}
    for _h, key, col, dec in TCOLS:
        v = df[col].get(p, np.nan)
        row[key] = None if not np.isfinite(v) else f'{float(v):,.{dec}f}'
    trows.append(row)

# 图号自查：核对表编号必须紧接在最后一张图之后。N_TABLE 是常量（页尾说明要在
# EX 建完之前就引用它），所以这里硬拦一道 —— 全站审计发现别的页把核对表写死成
# 'n': 15，后来在末尾追加了两张图，页面就出现「…16、17、15」而没有任何东西报错。
_ENS = [e['n'] for e in EX]
if _ENS != list(range(2, 2 + len(_ENS))) or N_TABLE != _ENS[-1] + 1:
    raise SystemExit(f'Exhibit 编号不连续或核对表编号没跟上：图 {_ENS}，N_TABLE={N_TABLE}')


# ────────── 两道看门狗：页尾那句「除下面点名的 N 张外」不靠人记得来维护 ──────────
# (1) 挂了号的图必须在**自己的图注里**自报 —— 页尾对读者的承诺就是这一句，
#     漏写就是页尾在替一张沉默的图打保票。
_BY_N = {e['n']: e for e in EX}
for _lab in _FIXED_LEFT:
    _fn = int(re.match(r'Exhibit (\d+)', _lab).group(1))
    if '排版决定的' not in _BY_N.get(_fn, {}).get('note', ''):
        raise SystemExit(f'Exhibit {_fn} 的起点是排版决定的（已挂号：{_lab}），'
                         f'却没在自己的图注里自报 —— 页尾「序列起点」那一条会因此说假话')
# (2) 反过来：本文件里任何**尾部切片**都得当场表明身份，三选一：
#       `# fixed-left: <图号>`  挂号给某张图（排版截断，上面 (1) 会追它自报）
#       `# data-window: <理由>` 窗口跟着数据／共享判据走（len(W25)、mrwin.resolve()），非排版上限
#       `# not-a-window: <理由>` 根本不是图窗口
#     新加一处切片却忘了挂号，正是 Exhibit 24 / 27 那次漏点名的成因，而那种漏
#     没有任何自动化能发现 —— 除非像这里一样，让漏掉的那一行自己把构建打挂。
# ⚠ 第一版只认**字面数字**（`\[-\d+:\]`），于是在它当初被写出来要堵的那个形状上是瞎的：
#     Exhibit 24 那一行本来是 `[-4:]`（会被抓住），改写成 `[-N_YEAR_LINES:]` 就从眼皮
#     底下溜了；`heat()` 的 `[-n_years:]`、以及 `.tail(n)` 同理。守卫的自述因此比它的
#     覆盖面宽 —— 又是一条「外延超过枚举」的断言，只不过写在源码注释里。现在切片界限
#     认任意表达式，`.tail(` 也一并认，注释与实际覆盖面对齐。
_TAIL_RE = re.compile(r'\[\s*-\s*[^\[\]:]+:\s*\]|\.tail\s*\(')   # not-a-window: 守卫自己的模式
_MARK_RE = re.compile(r'#\s*(fixed-left|data-window|not-a-window)\b')
_SRC_LINES = open(os.path.abspath(__file__), encoding='utf-8').read().splitlines()
_unmarked = [(i, ln.strip())
             for i, ln in enumerate(_SRC_LINES, 1)
             if _TAIL_RE.search(ln) and not ln.lstrip().startswith('#')
             and not _MARK_RE.search(ln)]
if _unmarked:
    raise SystemExit('尾部切片没有表明身份（同一行末尾加 `# fixed-left: <图号>` / '
                     '`# data-window: <理由>` / `# not-a-window: <理由>`）：'
                     + '；'.join(f'{i}: {t}' for i, t in _unmarked))
# (3) `# fixed-left: n` 标记里的图号必须真的是本页的一张图 —— 图一改号、标记就指错人，
#     而标记指错人时上面 (1) 追的是另一张图，等于白追。
_STALE = sorted({int(_m) for _ln in _SRC_LINES
                 for _hit in re.findall(r'#\s*fixed-left:\s*([\d,\s]+)', _ln)
                 for _m in re.findall(r'\d+', _hit)} - set(_BY_N))
if _STALE:
    raise SystemExit(f'`# fixed-left:` 标记指向不存在的图号：{_STALE}')

table = {
    # 标题里的月数跟着 trows 现算：W13 哪天改了，标题不会留在原地说假话。
    'n': N_TABLE, 'title': f'近 {len(trows)} 个月月度指标核对表（官方原始单位，未换算）',
    'idx': '月份',
    'cols': [[h, k] for h, k, _c, _d in TCOLS], 'rows': trows,
}

# ────────────────────────── 口径与方法说明 ──────────────────────────
# 断点那一条不许写死「三个断点图上均以红色虚线标出」：窗口每月往前滚，某个断点滚出
# 窗口再变的那天，这句话就变成页面上的第二处「注释说有、图上没有」。
# 由 BRK_DRAWN 现生成 —— 只说真正画上的那几张图。


# Exhibit 10 那条没画出来的线，如果画出来右轴会被撑到多高 —— 现算，见下面那条 note。
# 取的是**本页实际口径**（单月）在该图窗口内算得出的最大读数；一个都算不出就整句不写。
_ev10 = mom_yoy_of(df['adv_event_mn']).iloc[-len(W25):].dropna()   # data-window: 同 Exhibit 10
_EV10_MAX = float(_ev10.max()) if len(_ev10) else None


def _brk_line(period, what):
    ds = drawn_on(period)
    where = f'{ds} 上有红色竖虚线' if ds else '当前各图窗口已整段落在该断点右侧，无需画线'
    return f'{what}（{period}，{where}）'


notes = [
    '<b>数据源（唯一）</b>：investors.robinhood.com → Monthly Metrics 的 Excel。HOOD 的月度数据'
    '按 Reg FD 挂在 IR 网站上，<b>不走 8-K</b>，盯 EDGAR 抓不到；季度收入与季度成交量取自同一个'
    ' Excel 的 Quarterly GAAP P&amp;L 页。本页读的是仓库里的 <code>series/hood.csv</code> 与'
    ' <code>series/hood_q.csv</code>。',

    '<b>版式出处</b>：Goldman Sachs「Robinhood Markets Inc. (HOOD): Monthly」（James Yaro 团队）。'
    '本报告对 GS 版本做了三处改动：(1) GS 每张图挂的 "Prior 12mo Avg." 虚线与汇总表的 12M Avg. 列'
    '全部换成 y/y —— 滚动均值只是把序列再平滑一遍，不回答「相对去年同月是好是坏」；'
    '(2) GS 把「水平值」与「环比」拆成两张图，这里合并成「柱 + 右轴 y/y 线」；'
    '(3) GS 的佣金收入用的是 GSe 季度费率 x 当月成交量（未经验证的第三方估计），'
    f'本报告改用<b>公司自己披露的季度收入</b>反解费率，并加了 GS 没有的样本外检验（Exhibit {N_BRIDGE_TEST}）。',

    '⚠️ <b>窗口内的官方口径断点，虚线右侧与左侧不可直读</b>：'
    + '；'.join([
        _brk_line(BRK_BITSTAMP, 'Bitstamp 并入净流入、加密成交量与客户数'),
        _brk_line(BRK_TRADEPMR, 'TradePMR 的流量并入净流入'),
        _brk_line(BRK_SWEEP, 'High-Yield Cash 改版，逾 $6bn 从 Cash sweep 挪到 Cash and deposits'),
        _brk_line(BRK_WONDERFI,
                  f'WonderFi 带进约 {WONDERFI_CUSTOMERS_MN * 1000:.0f}k funded customers'
                  '（股权交易，不是自然获客）'),
        _brk_line(BRK_TRUMP,
                  'Trump Account 并入总平台资产（Robinhood 托管部分）与净流入（缴款），'
                  '不计入 funded customers'),
    ])
    + '。汇总表里<b>跨断点的 m/m 与 y/y 都带 †</b>，数值照登但不涂红绿 —— 两端不是同一个口径下的数，'
      '「好消息还是坏消息」这个判断做不了。',

    '<b>费率是反解值，不是披露值</b>：季度披露收入 ÷ 同季披露成交量。量纲换算——$1bn 名义额产生'
    ' r 个 $mn，即 r/1000 的费率 = r x 10 bp；$mn/mn 张 = $/张，x100 得美分/张。'
    '因此「隐含收入 vs 同季实际收入」必然完全吻合，是循环论证、没有信息量；'
    f'<b>唯一有信息量的检验是 Exhibit {N_BRIDGE_TEST}</b>：拿上一季的费率去预测本季收入，'
    '再与事后披露的实际值对照。',

    f'<b>费率图拆成两张（Exhibit {N_RATE_HI} / {N_RATE_LO}）</b>：四条费率跨 '
    f'{_rate_span(rate_equities_bp, rate_event_c).split("–")[0]} 到 '
    f'{_rate_span(rate_options_c, rate_crypto_bp).split("–")[1]}，'
    'PDF 版靠对数轴收在一张图里，而本页的图表引擎没有对数轴。原先四条共用一根线性轴，'
    f'股票（最新 {rate_equities_bp.dropna().iloc[-1]:.1f}bp）与事件合约'
    f'（最新 {rate_event_c.dropna().iloc[-1]:.1f}c/张）被压在零刻度线上、一条盖着另一条，'
    '整个窗口看不出变化。'
    '现按<b>量级</b>拆开：高的一张放 Options 与 Crypto，低的一张放 Equities 与 Event contracts；'
    '两张的单位都混着 c/张与 bp（写在各条图例名里），<b>跨图不能直接比高低</b>。'
    f'本页因此从旧编号 14 起整体后移一位（核对表为 Exhibit {N_TABLE}）。',

    f'<b>Exhibit {N_BRIDGE_TEST} 的口径对齐</b>：某一类若上季没有可用费率（业务还没起量、'
    '或成交量四舍五入成 0.0），该类同时从预测和实际里剔除，保证两根柱子覆盖同样的资产类别 —— '
    '否则预测缺一块、实际多一块，算出来的误差是假的。'
    '该图的左右两轴<b>零点不同高</b>（误差线跨零，强行对齐会浪费掉四成画布，'
    '引擎因此改为两轴独立缩放并在图内左上角红字标出）：柱的基线只是左轴的零。',

    f'<b>Exhibit {N_IMPLIED}（Implied transaction revenue）是推导值，不是公司披露值</b>：'
    '假设季度内费率恒定，最新季之后沿用最后一个已知费率；'
    '某类业务在其起量之前的贡献视为 0（整行全空才留空）。',

    '<b>年化有机增速</b> = 当月净流入 x 12 / 上月末总平台资产 —— 与本系列里 Schwab core NNA、'
    'LPL organic NNA 用的是同一套约定。<b>市值变动</b>是恒等式残差（期末 − 期初 − 净流入），'
    '因此也吸收并购带进来的资产，不能当成纯市场回报读。',

    # ── 同比口径：本页有三种，逐处点名 ──
    # 「点名」不是客套。读者在同一页上看到两个都叫 y/y 的净流入读数（单月 / 季度合计），
    # 如果没人告诉他分母不同，他只会以为哪里算错了。
    '<b>⚠ 同比口径：本页有三种，逐处点名。</b>'
    '(1) <b>单月同比</b>（本月 ÷ 去年同月 − 1；比率序列取<b>百分点差</b>）—— '
    '本页<b>所有时序图的右轴</b>、Exhibit 1 汇总表的 y/y 列、'
    'Exhibit 27 / 28 两张热力矩阵的逐格读数，以及页顶 headline 与 brief 里标「单月」的读数，'
    '全部是这一个口径，彼此可以逐格对上。'
    f'其中<b>流量类</b>（{_AX_FLOW}）'
    f'<b>是 2026-09 才从「{yoy.TTM_WIN} 个月滚动合计同比」改过来的，理由是页面所有者要求'
    '全站统一成单月口径</b>（CONTRACT §6 抬头引了原话）—— 一句可核对的指令，'
    '不是「看着更灵敏」（§6.1 第 3 条点名禁止的说法）。'
    '§6.1 第 1 条同时给了单月口径一个可核对的好处：<b>柱与线取自同一列</b>，'
    f'拿一根柱和 {yoy.LAG} 根柱之前那根一比就是线上那一点，读者能自己验算。'
    '<b>代价按 §6.1 第 3 条一并印出</b>（逐月标准差、相邻月最大跳变带月份、'
    '两种口径符号相反的月份数），由各图用<b>自己那条序列</b>现算写在图注里，'
    '不引别页的例子，也不只写结论；作对照的滚动口径<b>只以数字出现，页上一条线都不画</b>。'
    f'<b>存量与比率类</b>（{_AX_MONO}）不受这次改动影响：单月本来就是它们唯一（或唯一合法）'
    '的口径，不是选出来的。'
    f'<b>本轮没有右轴同比线的图</b>：{_AX_NONE} —— 窗口内可比点覆盖率低于 '
    f'{YOY_MIN_COVER:.0%}（判据见下条），整张图退成柱上标数，确切的 y/y 在汇总表里。'
    f'<b>上面 {_exlist(_MONO_STOCK)} 这 {len(_MONO_STOCK)} 张保留点对点是实测结论，'
    '不是「存量不能平滑」</b> —— 后者是句错话，'
    '本页更正过：存量的合法平滑口径是 <b>12 个月滚动均值同比</b>（去年一整年的平均余额 '
    'vs 前年；数值上等同于滚动合计比，除数约掉了），不能叫的只是「12 个月<b>合计</b>同比」，'
    '因为 12 个月末余额相加不指代任何真实的量。各图图注里给的是本序列自己的实测对照。'
    f'{_exlist(_MONO_RATIO)} 不同：{"它们的序列" if len(_MONO_RATIO) > 1 else "它的序列"}'
    '<b>本身就以 % 计量</b>（占比／费率），12 个月的占比做算术平均本身就没有意义'
    '（每个月的分母不同），要一年的平均占比必须量加权 —— 那是一条真的硬约束。'
    # ⚠ 判据必须写成「以 % 计量」而不是「是不是比率」：上一版写的是「它是比率」，
    #   而同一段话里 Exhibit 21 自己就叫「户均资产（两个期末数之比）」—— 一条被同一
    #   段话当场证伪的唯一性断言。名单与差额都现算，Exhibit 21 掉出名单时整句自动消失。
    + _quot_note()
    + f'(2) <b>季度合计 / 季度均值同比</b> —— Exhibit {N_QTR_ND}（净流入，季度合计）与 '
    f'Exhibit {N_QTR_DATS}（DATs，季度均值）的右轴。<b>本页仅有的两处与 (1) 不同口径的地方。</b>'
    '(3) <b>环比</b> —— 各图图注与页顶 brief 里的 m/m（brief 的日历修正句给的是'
    '「表面 vs 日均」两个环比，喂的是当月合计 vol_*，与图上已日均化的 ADV 不是同一列）。'
    + (f'<br>{_MIX_ND}' if _MIX_ND else '')
    # 「那个滚动读数印在哪儿」得跟着实际走：Exhibit 7 的可比点覆盖率不够时它退成
    # bars_labeled，右轴上根本没有线，再说「Exhibit 7 右轴」就是假话。
    # ⚠ 上一版这里写的是「股票名义 ADV 同样两处混用：Exhibit 7 右轴（滚动）vs
    #   Exhibit 28 热力矩阵（单月）」，而当时 Exhibit 7 根本没有右轴线（覆盖率不够，
    #   退成了柱上标数）—— 那句话点名的那条线在页面上并不存在。现在两者同口径了，
    #   「混用」这个说法本身也不再成立，改成把对照读数摆出来。
    + (f'<br>股票名义 ADV 的两种口径读数：单月同比 {_EQ_M:+,.1f}%'
       + ('（Exhibit 7 右轴与 Exhibit 28 热力矩阵当月格画的都是这个数）'
          if AXIS_KIND.get(7) == 'flow'
          else '（Exhibit 28 热力矩阵当月格；Exhibit 7 本轮没有右轴同比线）')
       + f'，作对照的 {yoy.TTM_WIN} 个月滚动合计同比 {_EQ_R:+,.1f}%'
       f'（本页不画），两者差 {abs(_EQ_M - _EQ_R):,.0f}pp —— 同一条序列、'
       '同一个月，换分母就换出这么大一个差，这正是口径必须写在图上的理由。'
       if None not in (_EQ_M, _EQ_R) else ''),

    '<b>交易日口径不一</b>：股票与期权按交易所交易日折算 ADV/DATs，加密按自然日；'
    f'Crypto DATs 不含 Bitstamp 的机构交易，而 Crypto ADV 含。季度图（Exhibit {N_QTR_ND} / {N_QTR_DATS}）'
    '正是为了抹掉月长与月末时点差异而做的。',

    '<b>Total platform assets 曾名 Assets Under Custody</b>，改名后口径扩大到包含 TradePMR 顾问的'
    '资产（这部分并不由 Robinhood 托管）。',

    # ── 历史从哪里来、为什么各图左端不一样：这一条是 2026-08-19 回填之后新增的 ──
    f'<b>序列起点 {mlab(df.index[0])}，但各图从哪一期（哪一年）起画不一样 —— '
    f'除下面点名的 {len(_FIXED_LEFT)} 张外，都是数据决定的、不是排版决定的。</b>'
    '当期那份月度 Excel 只发<b>滚动三年</b>窗口，2023-04 之前的月份要去 Quarterly Results 页'
    '翻当年的 Earnings Supplement（另一张页、另一种版式）。本站取的一律是'
    '<b>还拿得到的最早那一版</b>（2021-01~2022-12 用 Q1-23 那份、2023-01~03 用 Q1-26 那份），'
    '不用后来重述过的值 —— 实测被后期改过的只有净流入 4 个月各 0.1（脚本每次运行都重列一遍）。'
    f'再往前没有了：公司 2022-04 才开始月度披露、首期回填 12 个月，所以 {mlab(df.index[0])} 是天花板。'
    '<b>老版式的行少一半</b>：没有 ADV 那一节、没有 Cash and Deposits、没有 Bitstamp / '
    'Event contracts 拆分、没有加密交易日，出借收入 2022-05 才有数、Net 那一行 2023-01 才单列。'
    '这些格子<b>留空</b>，不补 0 也不用「成交量 ÷ 交易日」自己算 ADV —— 换算值不是披露值。'
    # ⚠ 这句话被改坏过两次，两次都是同一个毛病 —— 断言的外延比作者脑子里枚举的
    # 那几张图宽：第一版写「每张图的左端都由 mrwin.resolve() 裁」（漏了三张近端对比图），
    # 第二版改成「除下面点名的三张外」（又漏了 Exhibit 24 / 27 两张按年截断的）。
    # 现在这份名单由 _fix_left() 在每个真正截断的地方现挂号（见文件上半段），
    # 数量、窗口、被丢掉多少期全部现算；文件末尾还有一道看门狗，挂了号却没在自己
    # 图注里自报的直接停更 —— 这句话对读者的承诺因此是被机器兜住的，不是被记性兜住的。
    f'于是绝大多数图的左端由 <code>mrwin.resolve()</code> 按它自己那几条序列裁，'
    f'截在哪一期、被谁定住写在各自图注里。<b>下面 {len(_FIXED_LEFT)} 张是例外，'
    f'它们画到哪一期（哪一年）是排版决定的</b>：' + '、'.join(_FIXED_LEFT) +
    # ⚠ 这里原先还接了一句共同理由「每一格上都要印数值、拉到全历史标签会被抽稀掉大半」——
    # 对 Exhibit 6 成立，对两张 qtr_bar 不成立（charts.js 只对 gs_bar / gs_line /
    # gs_line_avg 调 thinLabels，qtr_bar 的柱顶竖排标签每根都画、一个不抽）。
    # 三张的理由不是同一个，就不要在这里替它们做全称断言，各自图注里已经写了。
    ' —— 每一张略去多少期、被什么定住，都写在它自己的图注里。'
    f'另有一处口径提示：{mlab(DARTS_UNTIL)} 及更早的 DATs 三列填的是当期印的 <b>DARTs</b>'
    '（公司 2026-07 才改名并重述，且只回溯到 Jan-25，Dec-24 及更早两种口径逐月相同），'
    f'见 Exhibit 11 图注。',

    # ── 季度那一半的历史：2026-08-19 同一轮回填 ──
    f'<b>季度表（<code>series/hood_q.csv</code>）同样回填过，现覆盖 {q.index[0]}–{LAST_Q}'
    f'（{len(q)} 个季度）。</b>Earnings Supplement 的 Quarterly GAAP P&amp;L 与 '
    'Quarterly KPIs 两页都是<b>滚动 13 个季度</b>的窗口，而抓取只吃最新那一份、只追加不回头 —— '
    f'所以这张表原先左端停在 2023Q2，那是<b>管道</b>的起点不是<b>数据</b>的起点。'
    '2021Q1–2022Q4 取自 Q1-23 那份 Supplement、2023Q1 取自 Q1-26 那份，'
    '第三份（Q4-23）当证人逐格复核，实测三份文件对这段历史<b>零处不一致</b>'
    '（脚本 <code>build/basefill/hood_q_2021.py</code> 每次运行都重算）。'
    f'再往前没有了：公司 2021-07 才 IPO，现存最早的 Supplement 两页都从 {q.index[0]} 起。'
    '<b>留空的两列</b>：事件合约收入是 Q2-26 那份才从 P&amp;L 的「Other」里拆出来的一行'
    '（更早的文件里 Other ≡ 今天的 Other + Event，脚本逐季验过这条恒等式），'
    f'所以 2023Q1 及更早没有任何官方文件印过它；事件合约成交量同理，只有 2023Q1 那一期'
    f'（Q1-26 印了 0）有数。业务 2024-10 才上线、事后看那一段就是 0，但补 0 是我们的断言、'
    f'不是公司的披露，故留空 —— 代价是 Exhibit 17 的左端因此钉在 {XQ[_w17.start]}。',

    # ⚠ 「右轴会被撑到多高」原先写死 3,000%（那是**滚动口径**下的读数）。2026-09 全站
    #   改单月之后，这张图上算得出的那几个点变成了另一批数，写死的那个数就成了一句
    #   与页面无关的旧话 —— 改成拿这条序列现算：它自己会跟着口径与窗口走。
    f'<b>Exhibit 10（事件合约）没有画 y/y 线</b>，不是漏了：窗口内只有少数几个月有大于零的'
    '上年同月基数，画出来是两段近乎垂直的竖线加一段贴地的直线'
    + (f'，还会把右轴撑到 {_EV10_MAX:,.0f}% 以上' if _EV10_MAX is not None else '')
    + '，除了「涨了很多」读不出任何东西。判据是<b>可比点的覆盖率</b>'
    f'（低于 {YOY_MIN_COVER:.0%} 就不画，阈值只有 <code>YOY_MIN_COVER</code> 一处定义），'
    '所以等基数长满 12 个月，这条线会自己回来。确切的 y/y 在 Exhibit 1 汇总表里。',

    '<b>所有数值与格式化都在 Python 侧完成</b>，页面只负责排版：同一个数字在两种语言里各算一遍，'
    '迟早会出现图上与表里对不上而没人发现。每张卡右上角的「表格」是与图同源的数值，'
    '比坐标轴多给一位小数，可直接与公司披露逐条核对。',
]

# ────────────────────────── 顶部数据总结（brief）──────────────────────────
def compose_brief(df, nd, bk_nd, brk_sweep):
    """HOOD 页顶部的 ~300 字数据总结（payload 的 `brief` 字段）。

    规则库在 `build/brief.py`（R1 峰值扫描 / R2 基数护栏 / R3 日历护栏 / R5 标注 /
    R6 有效位），那边只算事实，句子在这里拼 —— 措辞是口径的一部分，属于各家自己。
    一行 `headline` 与 Exhibit 1 给的是**读数**，这里只写图表本身讲不出来的三件事：
    基数效应、口径背离、所处区间；两边印过的数字一个都不复述。

    每个数字都当场从序列算，**没有一处硬编码**：排名、峰值停在哪个月、「已 N 个月没回去」、
    多几天少几天，下个月重跑全部自己会变。

    ═══ 与同比口径的关系（CONTRACT §6；2026-09 全站统一成单月之后）═══
      本页各时序图的右轴现在**一律画单月同比**（流量类是 2026-09 按页面所有者的指令
      从 12 个月滚动合计同比改过来的；存量与比率本来就是单月）。汇总表的 y/y 列一直是
      单月，所以 brief、汇总表、图上那条绿线现在**三者同口径**，读者可以互相对照 ——
      这比改造之前省心，但措辞不能因此放松：凡同比字样仍一律写明「单月同比」
      （CONTRACT §6 + tools/check_yoy_caliber.py 的 R4 都要求口径写明），
      因为本页还有两张季度柱图（季度合计 / 季度均值）
      不是这个口径；页尾「同比口径逐处点名」的 (1)（单月）与 (3)（环比）两条已把
      brief 计入名单。
      **具体哪几张图真的画出了右轴线是算出来的**（见 `AXIS_KIND` / `_axis_named()`）——
      可比点覆盖率不够的会退成柱上标数、右轴上根本没有线，写死名单必然烂掉。
      单月读数在本段只作**位置与基数**陈述（排名 / 峰值 / 口径背离 / 日历修正），
      不作趋势断言 —— 单月口径的毛刺代价印在各流量图的图注里（`mom_cost_note`），
      要读趋势得连着柱高一起看。峰值扫描那句的主语因此从旧稿的「存量指标」
      改成「指标的当月读数」：篮子里的股票 ADV、证券出借收入在页尾口径条里归**流量类**，
      brief 再叫它们「存量」会与同页的口径分类打架；R1 扫的本来就是
      当月水平读数（位置陈述），与流量/存量的同比口径之分无关。
      派生列 `organic_growth_roll`（滚动口径的有机增速，现在只作图注里的对照）
      **不进 R1 篮子**：篮子是显式点名的十条，不按列名白名单扫描，派生比率列天然被
      排除 —— 它是另一条序列的平滑读数，「创新高」在它身上不是信息。

    ═══ HOOD 独有，别家不能照抄 ═══
      · **同一个月里有两套日历，而且方向可以相反**：股票/期权走 `eqopt_trading_days`
        （含半日，故有 .5），加密 7×24 走 `crypto_trading_days`（= 日历日）。本月股票多一天、
        加密少一天，R3 的修正一条往下压、一条往上抬。别家只有一套日历，照抄必然把方向搞混，
        所以「多/少」两处措辞由 `dday` 的符号现算，不写死；表面与日均**两个数直接摆出来**
        （样板 ibkr 就是「期权表面跌 6.7%、日均实跌 11.0%」），不写「读高 X pp」——
        后者要读者自己做一次减法才拿得到真正该用的那个数。
      · **vol_\\* 与 adv_\\* 两套口径都在同一张表里**：`vol_*` 是当月合计、`adv_*` 是公司
        自己已经日均化的。R3 只能喂 `vol_*`；把 `adv_*` 再除一次交易日会造出一个根本不存在
        的修正。这条只管**喂进去的是哪一列**，不写进正文 —— 「表内 ADV 已日均化、别再除
        一次」是写给构建者的规则备忘，读者用不上。
      · **总资产恒等式的残差**：HOOD 同时披露资产存量与净流入，市值变动只能由
        `tpa.diff() − nd` 反解，是**推导值**（R5 必须标）。别家没有净流入这一列，
        做不了「资产环比转跌 ≠ 客户在撤」这个拆分。
      · **增量里混着三笔并购**：Bitstamp（进加密成交量）、TradePMR（进净流入）、
        WonderFi（进净流入与客户数）。所以「净流入创新高」必须先说清是不是外延，
        「加密同比转正」要拆成并购来的 Bitstamp 与原生 App 两个口径 —— 后者本月与合计反向。
        跨不跨断点一律用 `spans()` 现算，断点滚出窗口后这半句自己会消失。
      · **现金两行是互通的**：High-Yield Cash 改版把逾 $6bn 从 sweep 挪到 deposits，
        单看任一行的同比都是改版的产物，只有两者合计（推导值）跨得过断点。
      · **峰值扫描的篮子要过两道筛，不是一道**：`peak_scan` 自带的 `is_monotonic` 只看
        环比方向（diff ≥ 0 的比例），能挡住 `funded_customers`，却挡不住 `margin_book`
        —— 后者上下波动、diff 比例只有 0.87 过不了 0.90 那道门，可它近两年有 20/24 个月
        都 ≥ 自身滚动 36 个月的最大值，「又创新高」四个月里三个多月都成立，同样是噪音。
        所以这里额外过一道 `pctile.is_dead`（只读引用，与汇总表分位留空**同一条口径**）：
        Exhibit 1 那一格留空、brief 却说它创新高，是同一张页面自相矛盾。

    ═══ 分寸：与 build/ibkr.py 的 compose_brief() 并排读 ═══
    那一版是用户逐句验收过的标准，既是**上限也是下限**：四句、一句一个意思、~300 字
    （`B.render` 护栏 230-380）。本页照它的四个层次排 —— 规模（旗舰读数 + 峰值扫描）/
    增量归属（净流入与市值变动）/ 日历 / 口径背离。样板每一句都是「读数 + 它在历史里的
    位置」，所以四句里的比较都成对给数，不留光秃秃的名次或光秃秃的变化率。

    砍掉的是**同一件事印两遍**和写给构建者的备忘：
      · 日历差「原样进收入图」那半句 —— 讲的是页面机制，不是本月读数；
      · 剔除列的逐个点名 —— 早期月份能点到八条、光这半句 44 字，讲的还是筛选口径，
        改成只报条数（篮子多大、剩几条在比，读者要的是这个；名字在 Exhibit 1 里，
        那一格本来就留空）；
      · 「已 N 个月没回去」（＝本月与刚印出的峰值月之差，读者自己能减）；
      · 市值变动残差的历史名次（净流入已经给过一个全样本名次）；
      · Bitstamp 占比（Exhibit 25 画的就是这一条）。
    留下的一个字都不能省：「（推导值＝资产变动−净流入）」「（该月并入 WonderFi，口径
    不同）」「（推导值，单月同比 …）」这类**口径标注** —— 它们才是这一段存在的理由。

    后两处砍掉的细节留成**补丁**（`s1_long` / `s2_long`）：任何一句因缺值整句不写、总长
    掉到 250 字以下时自动补回。否则「缺一个读数 → 该句不写」会变成「整页当月发不出去」，
    正好走到 `B.need()` 想避免的反面。
    """
    M = [str(p) for p in df.index]
    i = len(M) - 1
    A = lambda c: np.asarray(df[c].values, float)
    # 金额一处定义：负号用 U+2212（与页面其余处一致），符号由数值现定，不写死。
    # 四舍五入后为 0 时不带符号 —— 「−$0.0bn」是格式化产物不是数据（brief.py 的
    # num()/pct() 用的是同一条规矩），夹在一片两位数金额里会让读者停下来猜它是不是缺失值。
    def bn(v, sign=False):
        s = '' if abs(v) < 0.05 else ('−' if v < 0 else ('+' if sign else ''))
        return f'{s}${abs(v):,.1f}bn'

    # ── 第一层 规模：R1 峰值扫描。量、融资、资产、生息四类混在一个篮子里扫，
    #    谁在峰值上由数据说了算。（样板 ibkr 的第一句也是规模 + 它在历史里的位置。）
    dats = A('dats_equity_mn') + A('dats_options_mn') + A('dats_crypto_mn')
    basket = [('股票ADV', A('adv_equity_usdbn')), ('期权ADV', A('adv_options_mn')),
              ('事件合约ADV', A('adv_event_mn')), ('总DATs', dats),
              ('融资余额', A('margin_book_usdbn')), ('加密ADV', A('adv_crypto_usdmn')),
              ('总平台资产', A('total_platform_assets_usdbn')),
              ('Cash sweep', A('cash_sweep_usdbn')),
              ('证券出借收入', A('seclend_total_usdmn')),
              ('入金客户', A('funded_customers_mn'))]
    # 两道筛：`is_dead`（与汇总表分位留空同一条口径，逮住 margin book 这种上下波动
    # 但常年贴着自身高位的列）+ `peak_scan` 自带的 `is_monotonic`（逮住入金客户）。
    # 只用后一道，就会出现「Exhibit 1 那格留空、brief 却说它创新高」的同页矛盾。
    dead = {nm for nm, a in basket
            if pctile.is_dead([float(v) if np.isfinite(v) else None for v in a])}
    pk = B.peak_scan(M, [(nm, a) for nm, a in basket if nm not in dead], i)
    n_at, n_off = len(pk['at_peak']), len(pk['off_peak'])
    n_tot = n_at + n_off
    # 样板的第一句是「当月读数 + 它在历史里的位置 + 相对表述」，三样都有。原来这里只有
    # 相对表述（几条里几条创新高），一个读数都没有，读者要翻回一行数据条才知道规模多大。
    # 旗舰读数取总平台资产：它是本页的规模基数，也是下一句「资产环比转跌」的主语。
    # 名次现算，不写死 —— 它并不是每月都在最高位（本月就排第 2）。
    tpa_s = A('total_platform_assets_usdbn')
    lead = []
    if B.need(tpa_s[i]):
        r = B.rank_of(tpa_s, i)
        # 这一条取整到 $bn（R6：几百亿的量级给到小数位没有信息，还会与一行数据条上的
        # $369bn 对不上，读者会以为是两个数）。市值变动那种个位数金额仍给一位小数。
        lead.append(f'{df.index[i].month}月末总平台资产${B.num(tpa_s[i], 0)}bn'
                    + ('为全样本最高' if r == 1 else f'排全样本第{r}'))
    scan = scan_long = ''
    if n_tot:
        # 三处都得能承受「全在峰值上」与「一条都不在」两种极端：名单要有上界（超过 5 条只列
        # 前 5 条加「等」），空名单要换句式。不然某个月这一句会把 render 的字数护栏撑爆，
        # 或者 min() 在空的 off_peak 上抛 ValueError —— 两种都是整页当月发不出去。
        # 「只有/有/多达」交给 B.quant 按占比现算：写死「只有」而 N 是算出来的，
        # 全线创新高的月份就会印出「八条里只有八条」，把普涨写成稀缺。
        at_txt = '、'.join(pk['at_peak'][:5]) + ('等' if n_at > 5 else '')
        head = f'{B.quant(n_at, n_tot, "条")}创新高（{at_txt}）' if n_at else '没有一条创新高'
        # 被两道筛剔掉的**只报条数，不逐个点名**：名字要占到 44 字（早期月份能点到八条），
        # 而它讲的是筛选口径不是本月读数；名字在 Exhibit 1 里，那一格本来就留空。
        # 条数不能省：它交代了篮子原本多大、现在拿几条在比，否则「两条指标里…」
        # 会读成数据缺失。措辞取两道筛都成立的那个交集（单调列贴自身最大值、死列贴
        # 滚动窗口端点，都是「贴顶」），写「单调只增」会冤枉后者。
        skipped = [nm for nm, _ in basket if nm in dead or nm in pk['skipped']]
        skip_txt = f'；另{B.cn(len(skipped))}条常年贴顶不计入' if skipped else ''
        tail = tail_long = '，没有一条落在峰值以外'
        if pk['off_peak']:
            # 「已 N 个月没回去」只在总长不够时才补：N 就是本月与刚印出来的峰值月之差，
            # 读者自己能减，正常月里属同一个数印两遍。
            old_nm, old_k = min(pk['off_peak'], key=lambda t: t[1])
            tail = f'，最久的{old_nm}峰值停在{old_k}'
            tail_long = tail + f'、已{i - M.index(old_k)}个月没回去'
        # 主语是「当月读数」不是「存量指标」（口径适配，见 docstring）：篮子里的 ADV 与
        # 证券出借收入在页尾口径条里归流量类，叫它们「存量」会与同页口径分类打架；
        # R1 的「创新高」本来就是对当月水平读数的位置陈述。
        scan = f'{B.cn(n_tot)}条指标的当月读数里{head}{tail}{skip_txt}'
        scan_long = f'{B.cn(n_tot)}条指标的当月读数里{head}{tail_long}{skip_txt}'
    elif pk['skipped'] or dead:
        # 篮子被两道筛清空的月份（早期几乎每条都还在单调爬坡）：这一句照样要成立，
        # 不能整句消失 —— 否则总长掉到 render 的下限以下，整页当月发不出去。
        scan = scan_long = (f'{B.cn(len(basket))}条指标全部常年贴着自身极值，'
                            f'本月峰值扫描没有可比对象')
    # 读数与扫描各自可能不存在，句子仍要成立：两半都空才整句不写。
    s1 = '，'.join(lead + [scan] if scan else lead)
    s1_long = '，'.join(lead + [scan_long] if scan_long else lead)
    s1, s1_long = (s1 + '。' if s1 else ''), (s1_long + '。' if s1_long else '')

    # ── 第二层 增量归属：恒等式残差 资产变动 − 净流入 = 市值变动（推导值，R5）。
    #    净流入的名次跨不跨并购断点现算。这一句只给**名次与环比方向**，不给净流入的同比 ——
    #    页尾口径条刚点过名：同一条净流入在本页有三个都叫 y/y 的读数（单月 / 季度合计 /
    #    12 个月滚动合计），brief 再引任何一个都得连口径一起背出来，而名次不需要。
    ndv, mg = np.asarray(nd.values, float), A('market_gains_usdbn')
    d_tpa = float(A('tpa_change_usdbn')[i])
    s2 = s2_long = ''
    if i >= 1 and B.need(ndv[i], mg[i], d_tpa):
        be = B.base_effect(ndv, i)
        # 读数 + 它在历史里的位置一起给（样板每一句都是这么写的）：只说「为全样本最高」
        # 是个没有读数的名次，读者要翻回一行数据条才知道最高是多少。
        nd_rank = '为全样本最高' if be['rank'] == 1 else f'排全样本第{be["rank"]}'
        xs = [lab for p, lab in bk_nd if spans(p, df.index[i - 1], df.index[i])]
        xs_txt = f'（该月并入{"、".join(xs)}，口径不同）' if xs else ''
        # 三种月份都要说得通：资产跌而流入正（本月）、资产涨但市值在拖、资产涨且市值在推。
        # 判据是 tpa 的环比方向与残差的符号，一律现算 —— 把「资产环比转跌」写死，
        # 下个月资产回升时这一句就是一句假话，而没有任何自动化会发现。
        # 残差的历史名次（原来的「为全样本第 N 大负贡献」）砍掉了：净流入那半句已经给了
        # 一个全样本名次，残差再给一个是同一类信息的第二遍，而「推导值＝资产变动−净流入」
        # 这个口径注解砍不得（R5 + 它是这一句能不能被读者自己验算的全部依据）。
        # 「不是客户在撤」还得看净流入本身的符号：净流入转负的月份资产跌就**真的**有
        # 客户在撤，这句写死就是把坏消息读成好消息。三个符号（tpa 环比、残差、净流入）
        # 定四种说法，一个都不能预设。
        pos = ndv[i] > 0
        if mg[i] < 0:
            opening = ('资产环比转跌不是客户在撤' if pos and d_tpa < 0
                       else '资产环比是净流入顶上去的' if pos else '资产在跌、客户也在撤')
            s2 = (f'{opening}：净流入{bn(ndv[i])}{nd_rank}{xs_txt}，'
                  f'同期市值变动<b>{bn(mg[i])}</b>（推导值＝资产变动−净流入）')
            s2_more = f'，为第{B.rank_of(-mg, i)}大负贡献'
        else:
            s2 = (f'{"资产的增量不全是客户给的" if pos else "资产靠市值撑着、客户在净撤出"}：'
                  f'净流入{bn(ndv[i])}{nd_rank}{xs_txt}，'
                  f'{"其余来自" if pos else "同期"}市值变动<b>{bn(mg[i], sign=True)}</b>'
                  f'（推导值＝资产变动−净流入）')
            s2_more = f'，为第{B.rank_of(mg, i)}大正贡献'
        s2, s2_long = s2 + '。', s2 + s2_more + '。'

    # ── 第三层 日历：R3 日历护栏。喂进去的必须是**当月合计**的 vol_*，不是已经日均化的 adv_*。
    tde, tdc = A('eqopt_trading_days'), A('crypto_trading_days')
    ce = B.calendar_split(A('vol_equity_usdbn'), tde, i)
    cc = B.calendar_split(A('vol_crypto_usdbn'), tdc, i)
    s3 = ''
    # 两条腿分开处理：某个月只有一条日历/一条成交量缺读数时，`calendar_split` 只把那一条
    # 判成 None，另一条照样成立。要求两条同时可用会让整句消失，而整句消失会把总长压到
    # render 的下限以下 —— 一句解读的缺值，代价变成整页当月发不出去。
    legs = [('股票', '交易日', ce), ('加密', '日历日', cc)]
    have = [(nm, u, c) for nm, u, c in legs if c]
    if have:
        # 「方向相反」是本月的事实，不是这一页的常设结论：两条日历同向、只动一条、
        # 两条都没动的月份都会出现，全都得说得通，措辞按 dday 的符号现算。
        dtxt = lambda d: '持平' if d == 0 else ('多' if d > 0 else '少') + f'{abs(d):g}天'
        # |gap| 小于 0.05pp 就当没有日历差 —— 否则会印出一个由格式化造出来的假修正。
        sg = lambda c: 0 if abs(c['gap_pp']) < 0.05 else 1
        day_txt = '、'.join(f'{nm}{u}{"比上月" if k == 0 else ""}{dtxt(c["dday"])}'
                           for k, (nm, u, c) in enumerate(have))
        # 表面与日均两个数直接摆出来（样板：「期权表面跌 6.7%、日均实跌 11.0%」），
        # 不写「读高 X pp」：那要读者自己做一次减法才拿得到真正该用的那个数，而本月
        # 加密就是个现成的例子 —— 表面与日均差好几个 pp，pp 差写法两个数一个都不给。
        # 没动日历的那条只印一个数：raw 与 per_day 相等时印两遍是假的对比。
        pair = lambda nm, c: (f'{nm}表面{B.pct(c["raw"])}、日均{B.pct(c["per_day"])}'
                              if sg(c) else f'{nm}{B.pct(c["raw"])}')
        nums = '，'.join(pair(nm, c) for nm, u, c in have)
        if any(sg(c) for nm, u, c in have):
            s3 = f'{day_txt}：{nums}。'
        else:
            # 两条都没动（或只剩一条腿且没动）：这一句仍要成立，措辞换成「不必修正」。
            s3 = f'{day_txt}，合计额不必做日历修正：{nums}。'

    # ── 口径背离：加密的增量是外延还是内生；现金两行被改版对挪，只有合计可比。
    # Bitstamp 占比取派生列（Exhibit 25 画的同一条），不在这里再除一遍 —— 口径只能有一处
    # 定义。它在这一句里只当**开关**（并购并进来了没有）用，占比本身不印：Exhibit 25 已经
    # 画了它，再写一遍就是复述式摘要。
    app, tot = A('adv_crypto_app_usdmn'), A('adv_crypto_usdmn')
    bs_share = A('crypto_bitstamp_share')[i]
    sw, dep = A('cash_sweep_usdbn'), A('cash_and_deposits_usdbn')
    # 序列开头不足 12 个月时退到环比，标签一起换掉：直接写 a[i-12] 会被 numpy 的负索引
    # 悄悄绕到序列末尾，印出一个由回绕算出来的假同比，而且不报错。
    # 口径适配（CONTRACT §6）：同比一律标「单月」。2026-09 起图上的绿线也是
    # 单月，这两处读数与它同口径 —— 但标注不能省：本页还有两张季度柱图不是这个口径。
    # 它们在这里只作口径背离（App vs 合计反向、两行只有合计可比）的陈述，不作趋势断言。
    lag = 12 if i >= 12 else 1
    lab = '单月同比' if lag == 12 else '环比'
    parts = []
    if i >= 1 and B.need(app[i], app[i - lag], tot[i], tot[i - lag], bs_share) \
            and app[i - lag] and tot[i - lag]:
        app_g, tot_g = app[i] / app[i - lag] - 1, tot[i] / tot[i - lag] - 1
        # Bitstamp 占比（57.6%）本身没写进来：Exhibit 25 画的就是这一条，写进 brief 是
        # 复述图上已有的数。brief 该给的是图上没有的那半句 —— 原生 App 与合计反向。
        # 并购之前 Bitstamp 占 0，那几个月 app ≡ tot，「弱于/强于合计」是拿一条序列
        # 和它自己比，必须换句式。「反向/弱于/强于」两侧是**同月同口径**（都是单月同比）
        # 的比较，合法；跨口径比高低才是被页尾口径条禁掉的那种。
        peer = '并购后的合计' if bs_share >= 0.05 else '合计'
        div = (f'与{peer}反向' if (app_g < 0) != (tot_g < 0)
               else f'弱于{peer}' if app_g < tot_g else f'强于{peer}')
        # 变化率后面挂上读数本身：样板每一处比较都是「读数 + 变化」成对给的，
        # 只给一个 -13.9% 读者无从判断这条腿有多大分量（它是页面上唯一的原生口径）。
        parts.append(f'加密原生 App ADV ${B.num(app[i], 0)}mn/日、{lab}{B.pct(app_g)}、{div}'
                     if bs_share >= 0.05 else
                     f'加密还全部是原生 App（Bitstamp 未并入），ADV ${B.num(app[i], 0)}mn/日、'
                     f'{lab}{B.pct(app_g)}')
    if i >= 1 and B.need(sw[i], dep[i], sw[i - lag], dep[i - lag]) and (sw[i - lag] + dep[i - lag]):
        rec = ('被 High-Yield Cash 改版对挪' if spans(brk_sweep, df.index[i - lag], df.index[i])
               else '口径互通')
        parts.append(f'现金两行{rec}，只有合计（推导值{bn(sw[i] + dep[i])}，{lab}'
                     f'{B.pct((sw[i] + dep[i]) / (sw[i - lag] + dep[i - lag]) - 1)}）可比')
    # 原来这句以「两处背离：」起头 —— 五个字的套话，而且「两」是写死的：某一处因缺值
    # 不写时它就是假话。直接删掉，两处背离本来就并列在句子里，读者不需要先被数一遍。
    s4 = '；'.join(parts) + '。' if parts else ''

    # ── 组装：规模 / 增量归属 / 日历 / 口径背离，与样板 ibkr 的四层同序。
    #    上面每一句都可能因缺值整句不写（`B.need` 的正确用法），但 render 的字数下限是
    #    硬的：少一句就可能掉到 230 以下、整页当月发不出去 —— 那正是 need() 要避免的
    #    结果。所以砍掉的两处细节留成**补丁**：正常月不用，某句真的消失时再补回来。
    #    补的是早已算好的事实，不是凑字数的套话。
    body = [s1, s2, s3, s4]
    for k, longer in ((0, s1_long), (1, s2_long)):
        if longer and len(re.sub(r'<[^>]+>', '', ''.join(body))) < 250:
            body[k] = longer
    return B.render(body)


# ────────────────────────── payload ──────────────────────────
# 抬头是多数人唯一会读的一行，所以每个 y/y 都要带口径标签：本页有三种同比口径，
# 一个光秃秃的「y/y」在这里等于误导（读者会拿它去核汇总表，然后对不上）。
# ⚠ 2026-09 起流量类（股票 ADV、净流入、证券出借收入）在这里也报**单月**同比 ——
# 上一版报的是 12 个月滚动合计，而抬头上面那句注释同时声称「与图上那条线是同一个数」；
# 图改成单月之后那句话就会变成假话，所以两处一起改，抬头与图上仍然是同一个数。
# 存量类（平台资产、cash sweep）本来就是点对点同比 —— 存量也能做 12 个月**均值**同比，
# 但实测下来换了没收益（逐图数字见各自图注），所以留点对点。
_tpa_yoy = float(tpa.iloc[-1] / tpa.iloc[-13] - 1)                 # 存量 → 单月
_tpa_mom = mom_of(tpa)
_nd_mom = mom_of(nd)
_og = float(df['organic_growth_ann'].iloc[-1])
_eq_yoy = (_EQ_M / 100.0) if _EQ_M is not None else float('nan')   # 流量 → 单月
_fc = float(df['funded_customers_mn'].iloc[-1])
_apc = df['assets_per_customer_usdk']
_apc_mom = mom_of(_apc)
_sl = df['seclend_total_usdmn']
_sl_m = _my(_sl)
_sl_yoy = (_sl_m / 100.0) if _sl_m is not None else float('nan')   # 流量 → 单月
_cs = df['cash_sweep_usdbn']
_cs_yoy = float(_cs.iloc[-1] / _cs.iloc[-13] - 1)                  # 存量 → 单月

# headline 原来只挑涨的说：总资产写 +32% y/y 却不提本月 −2.2%，户均资产、Cash sweep、
# 证券出借收入三条都在下行、一条没写。一句话摘要挑着说等于替读者做了结论。
# 这里固定「先给规模与增量，再把窗口里明确下行的项目一并列出」，涨跌都由数据现算。
_down = []
if np.isfinite(_apc_mom) and _apc_mom < 0:
    _down.append(f'户均资产 ${_apc.iloc[-1]:,.1f}k（{pp_txt(_apc_mom)} m/m）')
if np.isfinite(_cs_yoy) and _cs_yoy < 0:
    _down.append(f'Cash sweep ${_cs.iloc[-1]:,.1f}bn（{pp_txt(_cs_yoy)} y/y·单月，含 High-Yield Cash 改版）')
if np.isfinite(_sl_yoy) and _sl_yoy < 0:
    _down.append(f'证券出借收入 ${_sl.iloc[-1]:,.0f}mn（{pp_txt(_sl_yoy)} y/y·单月）')

headline = (
    f'总平台资产 ${tpa.iloc[-1]:,.0f}bn（{pp_txt(_tpa_yoy)} y/y·单月，但 {pp_txt(_tpa_mom)} m/m） · '
    f'净流入 ${nd.iloc[-1]:,.1f}bn（{pp_txt(_nd_mom)} m/m'
    + (f'，{pp_txt(ND_M / 100.0)} y/y·单月' if ND_M is not None else '')
    + f'，年化有机增速 {_og:.1f}%） · '
    f'股票名义 ADV ${df["adv_equity_usdbn"].iloc[-1]:,.1f}bn/日（{pp_txt(_eq_yoy)} y/y·单月） · '
    f'期权 ADV {df["adv_options_mn"].iloc[-1]:,.1f}mn 张/日 · '
    f'事件合约 ADV {df["adv_event_mn"].iloc[-1]:,.0f}mn 张/日 · '
    f'融资余额 ${df["margin_book_usdbn"].iloc[-1]:,.1f}bn · '
    f'入金客户 {_fc:,.1f}mn'
    + (f'（含 WonderFi 并入的 ~{WONDERFI_CUSTOMERS_MN * 1000:.0f}k，'
       f'剔除后 {FC_MM_EX:+.1%} m/m 而非 {FC_MM:+.1%}）' if FC_MM_EX is not None else '')
    + (' ｜ 本月下行：' + ' · '.join(_down) if _down else '')
)

payload = {
    'ticker': 'hood',
    'tracker': 'HOOD Monthly Operating Metrics',
    'title': f'Robinhood Markets (HOOD)：月度经营指标 — {LATEST.year} 年 {LATEST.month} 月',
    'data_through': str(LATEST),
    'through_label': f'{LATEST.year} 年 {LATEST.month} 月',
    'subtitle': f'数据源：Robinhood 月度经营指标（IR 网站，Reg FD 披露）+ 季度 GAAP P&L · '
                f'覆盖 {mlab(df.index[0])} – {mlab(LATEST)}（{len(df)} 个月）与 '
                f'{q.index[0]} – {LAST_Q}（{len(q)} 个季度） · '
                f'版式沿用 Goldman Sachs GIR「HOOD Monthly」，含 GS 版没有的收入桥样本外检验',
    'headline': headline,
    'brief': compose_brief(df, nd, BK_ND, BRK_SWEEP),
    'hub_line': f'总平台资产 ${tpa.iloc[-1]:,.0f}bn（{pp_txt(_tpa_yoy)} y/y 单月）·'
                f'净流入 ${nd.iloc[-1]:,.1f}bn · 入金客户 {_fc:,.1f}mn',
    'source': SRC,
    'xlabels': XL25,
    'xlabels_long': XL_LONG,
    'summary': summary,
    # 轴刻度小数位与截轴护栏：判据见 build/axisfmt.py（全站唯一实现）。
    # 长窗口的图放不进半栏卡片 —— 逐张按 charts.js 的量边距算式判通栏与抽稀。
    # 排在 axisfmt.fix_all 之后：轴刻度定稿了才量得准边距（与 single.py 同序）。
    'exhibits': mrwin.layout_all_ret(axisfmt.fix_all(EX)),
    'table': table,
    'notes': notes,
    'footer': '仅供个人研究，不构成投资建议 · 数值全部来自 Robinhood 官方月度指标与季度报告，'
              '推导值（费率、隐含收入、有机增速、市值变动）已在图注中标明假设',
}

# 抬头那半句「官方发布于 …」。台账里没有这个月就**整个字段不写**：page.js 判的是字段
# 存不存在，写 None 会渲染成 "官方发布于 None"。查不到时抬头少半句，页面照常成立。
_sdate = _source_dates().lookup(os.path.join(ROOT, 'series'), 'hood', str(LATEST))
if _sdate:
    payload['source_date'] = _sdate

out = os.path.join(ROOT, 'data', 'hood.js')
# 写出前先过 CONTRACT §5.5 护栏（NaN/Infinity 一律拒写）；首行注释与序列化都在里面。
payload_guard.write_dash(out, payload, 'hood')

print(f'月度窗口 {df.index[0]} → {LATEST}（{len(df)} 个月）| 季度 {q.index[0]} → {LAST_Q}（{len(q)} 个季度）')
print(f'Exhibit 1 汇总表 + Exhibit {EX[0]["n"]}-{EX[-1]["n"]}（{len(EX)} 张）+ Exhibit {table["n"]} 核对表')
print(f'Exhibit {N_BRIDGE_TEST} 窗口内平均绝对误差 {_mae:.1f}%')
print('断点画在：' + '；'.join(f'{p} → {sorted(set(v))}' for p, v in sorted(BRK_DRAWN.items())))
print('分位留空：' + ('、'.join(lab for lab, _w in blank_rows) or '（无）'))
print(f'写出 {out}  ({os.path.getsize(out) / 1024:.1f} KB)')
print(headline)
