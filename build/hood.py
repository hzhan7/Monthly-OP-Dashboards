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
  1. 费率那张 PDF 用对数轴（四条费率跨 1.0 到 55），charts.js 没有对数轴，也不许拿
     「压在零刻度上的两条线」充数 —— 改成**按量级拆成两张**：Exhibit 13 是 20–55 档的
     Options / Crypto，Exhibit 14 是 1–2 档的 Equities / Event contracts。因此本页从
     旧编号 14 起整体后移一位（旧 Ex14→15 … 旧 Ex27→28，核对表 28→29）。
     两张都用 kind='lines'：lines_endlabels 会对首/末点无条件调用格式器，而事件合约
     费率在 2023Q3 是缺失的（成交量四舍五入成 0.0），会直接抛 TypeError 把整页打挂。
  2. lvl_bar 的柱顶数值与 m/m 气泡：bar_line_dual 不画柱顶数值（数值在 tooltip 与表格
     视图里），m/m 改写进图注文字。
  3. 两张热力矩阵不设 full:true —— 通栏卡片会被 page.js 挂到 #lead 里，排到 Exhibit 2
     前面去，图序就乱了。半栏 12 列仍然读得清。

分位（3Y %ile）不在本文件里实现，一律调 build/pctile.py 的 cell() / why_blank()：
判据是口径，口径只能有一处定义。本页原先那份 pctile36 的「≥90% 月环比不降」代理拦不住
margin book（近 24 个月里 18 个月钉 100）这类「上下波动但分位常年顶格」的行。
"""
import datetime
import importlib.util
import json
import math
import os
import re

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
if len(df) < 25 or len(q) < 8:
    raise SystemExit(f'序列太短：月度 {len(df)}、季度 {len(q)}')

LATEST = df.index[-1]
LAST_Q = q.index[-1]

# ────────────────────────── 派生列（逐行照搬 build_hood.py）──────────────────────────
BRK_WONDERFI = pd.Period('2026-06', 'M')   # 收购 WonderFi，带进 ~30 万 Funded Customers
BRK_BITSTAMP = pd.Period('2025-06', 'M')   # Bitstamp 并入净流入、加密成交量与客户数
BRK_TRADEPMR = pd.Period('2026-03', 'M')   # TradePMR 顾问资产的流量并入净流入
BRK_SWEEP = pd.Period('2026-02', 'M')      # High-Yield Cash 改版，>$6bn 从 sweep 挪到 deposits
WONDERFI_CUSTOMERS_MN = 0.3                # WonderFi 带进的 funded customers（公司披露 ~300k）

# 每条序列受哪些断点影响。汇总表的 m/m / y/y 是否跨断点、图上画哪几条竖虚线，
# 都从这里推 —— 手写在两处必然走偏（原版就是图上画了 WonderFi、表里 m/m 照涂绿）。
BK_ND = [(BRK_BITSTAMP, 'Bitstamp'), (BRK_TRADEPMR, 'TradePMR'), (BRK_WONDERFI, 'WonderFi')]
BK_CUST = [(BRK_BITSTAMP, 'Bitstamp'), (BRK_WONDERFI, 'WonderFi')]
BK_TPA = [(BRK_WONDERFI, 'WonderFi')]
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
for i in range(1, len(q)):
    cur_q, prv_q = q.index[i], q.index[i - 1]
    tot = act = 0.0
    n_cls = 0
    for _nm, _rc, _vc, _mc in RATE:
        r, v = _rate(_rc, _vc, prv_q), q[_vc].get(cur_q, np.nan)
        if not (np.isfinite(r) and np.isfinite(v)):
            continue
        tot += r * v
        act += q[_rc][cur_q]
        n_cls += 1
    if n_cls:
        pred[cur_q], actual_txn[cur_q] = tot, act

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
# 单月同比的分母是**去年那一个月**：流量的月度分布本身带季节性与时点噪音（发薪日、
# 加密行情的爆发月、并表落在哪一个月），分母越小同一笔绝对变化被放大得越狠。
# 12 个月滚动合计把整整一年的流量加起来再比，分母是一整年，季节性自动对消。
# 本页实测（对齐到两种口径都算得出的同一批月份，见 caliber_stats）：
# 净流入的单月同比标准差是滚动口径的 2.2 倍，相邻月最大跳变 260pp vs 26pp，
# 16 个可比月里 5 个月符号相反（Dec-25 单月 −40%、滚动 +35%）。具体数字一律现算。
#
# ⚠ 一条更正（2026-08-07）：早先本文件写过「存量不许做滚动合计，所以只能点对点」。
# **后半句是假的**：Σ12/Σ12′ 里的除数约掉，12 个月滚动**合计**比恒等于 12 个月
# 滚动**均值**比（共享模块 build/yoy.py 实测两者差 2.3e-14），而「去年一整年的
# 平均平台资产 vs 前年」是一个真实存在、可以核对的量。**错的只是「合计」这个名字**。
# 所以：存量**可以**平滑（走 yoy.ttm_mean_yoy，文案必须写「12 个月均值同比」），
# 本页仍保留点对点，但理由必须是**本序列实测**出来的（见 stock_note）。
# 比率序列另说 —— 12 个月的比率做算术平均没有意义，yoy.ttm_mean_yoy 对 RATIO
# 直接抛 CaliberError，那是一条真的硬约束（见 ratio_note）。
def roll_yoy_of(s):
    """12 个月滚动合计同比（%）—— 流量类。数值实现走共享模块，本页不另写一份。"""
    return yoy.ttm_yoy(s, yoy.FLOW)


def mean_yoy_of(s):
    """12 个月滚动**均值**同比（%）—— 存量类唯一说得通的平滑口径。

    数值上与滚动合计比完全相同（除数约掉），差别只在**说法**：对存量，
    「12 个月合计」不指代任何真实的量，「去年一整年的平均余额」才是。
    本页只拿它做反事实对照，图上画的仍是点对点。
    """
    return yoy.ttm_mean_yoy(s, yoy.STOCK)


def caliber_stats(mono, roll, idx):
    """两种口径的实测对比。返回 None 表示可比月份不足。

    ⚠ **必须先对齐到两种口径都算得出的同一批月份**：滚动口径天然少掉头 12 个月，
    不对齐就是拿两个不同样本比波动，样本效应会伪装成口径效应。
    """
    keep = [p for p in idx if p in mono.index and p in roll.index
            and np.isfinite(mono.loc[p]) and np.isfinite(roll.loc[p])]
    if len(keep) < 3:
        return None
    A, B = mono.loc[keep].astype(float), roll.loc[keep].astype(float)
    jump = lambda x: float(np.abs(np.diff(x.values)).max()) if len(x) > 1 else float('nan')
    return {'n': len(keep), 'sd_m': float(A.std(ddof=0)), 'sd_r': float(B.std(ddof=0)),
            'jump_m': jump(A), 'jump_r': jump(B),
            'flips': [(mlab(p), float(A.loc[p]), float(B.loc[p]))
                      for p in keep if A.loc[p] * B.loc[p] < 0],
            'lo_m': float(A.min()), 'hi_m': float(A.max()),
            'cur_m': float(A.iloc[-1]), 'cur_r': float(B.iloc[-1]),
            'first': keep[0], 'last': keep[-1]}


def roll_note(st, unit='%'):
    """「本图的次轴为什么是滚动 12 个月合计同比」——数字全部来自本页自己的序列。"""
    if st is None:
        return ('右轴为 <b>12 个月滚动合计同比</b>（本年 12 个月合计 ÷ 上年同 12 个月合计 − 1），'
                '不是单月同比。本序列两种口径都算得出的月份不足 3 个，暂不给对比数字。')
    ratio = st['sd_m'] / st['sd_r'] if st['sd_r'] else float('nan')
    t = (f'右轴绿线为 <b>12 个月滚动合计同比</b>（本年 12 个月合计 ÷ 上年同 12 个月合计 − 1），'
         f'不是单月同比。理由是实测的：把两种口径<b>对齐到同一批月份</b>后'
         f'（{mlab(st["first"])}–{mlab(st["last"])}，{st["n"]} 个月），单月同比标准差 '
         f'{st["sd_m"]:,.1f}pp 是滚动口径 {st["sd_r"]:,.1f}pp 的 {ratio:,.1f} 倍，'
         f'相邻月最大跳变 {st["jump_m"]:,.0f}pp vs {st["jump_r"]:,.0f}pp')
    if st['flips']:
        w = max(st['flips'], key=lambda f: abs(f[1] - f[2]))
        t += (f'，{len(st["flips"])} 个月两种口径<b>符号相反</b>'
              f'（{"、".join(f"{m} 单月 {a:+,.0f}{unit} / 滚动 {b:+,.0f}{unit}" for m, a, b in st["flips"])}）'
              f'—— 最极端的 {w[0]} 相差 {abs(w[1] - w[2]):,.0f}pp。')
    else:
        t += '，本窗口内两种口径没有符号相反的月份。'
    t += (f'当期并排：单月 {st["cur_m"]:+,.1f}{unit}、滚动 {st["cur_r"]:+,.1f}{unit}'
          f'（差 {abs(st["cur_m"] - st["cur_r"]):,.0f}pp）。柱本身是当月读数，没有改。')
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
            + '。均值口径更平滑，但按构造滞后约半年、回答的是另一个问题'
            '（「去年一整年的平均水平」而非「现在相对去年此刻」）；'
            '而存量的分子分母都是时点数、不含日历效应，本来就不像流量那样被小分母放大。'
            '噪声用轴范围解决。')


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
W15 = df.index[-15:]
W13 = df.index[-13:]
XL25 = [mlab(p) for p in W25]
XL15 = [mlab(p) for p in W15]
XL13 = [mlab(p) for p in W13]
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
# 手写「Exhibit 3、7、8 的右轴是滚动同比」这种名单必然烂掉：y/y 覆盖率不够时 lvl()
# 会把整张图退成 bars_labeled（连线都没有），而名单不会自己知道。
AXIS_KIND, AXIS_ZH = {}, {}

# 图注与口径说明里被点名引用的 Exhibit 编号集中在这里。上一版把费率图拆成两张时，
# 散在正文里的「Exhibit 14」「Exhibit 21」「Exhibit 22 / 25」会集体指错一张图，
# 而那种错没有任何自动化能发现 —— 所以引用一律走常量，不写字面数字。
N_RATE_HI, N_RATE_LO = 13, 14          # 费率：高量级档 / 低量级档
N_BRIDGE_TEST, N_IMPLIED = 15, 16      # 样本外检验 / 隐含交易收入
N_HIST = 22                            # 总平台资产全历史
N_QTR_ND, N_QTR_DATS = 23, 26          # 季度净流入 / 季度 DATs
N_TABLE = 29                           # 末尾核对表

# y/y 线要画出来，至少得有这么高比例的点是可比的。
# 事件合约（Exhibit 10）窗口内只有 6 个月有可比基数，画出来是「两段近乎垂直的竖线
# 加一段贴地的直线」，还顺带把右轴撑到 0–3000% —— 除了「涨了很多」读不出别的，
# 却挡住了柱子。这不是排版偏好：一条 76% 是断口的折线本来就不是一条序列。
# 用覆盖率而不是「量程多宽」当判据，是因为它会自己恢复：等事件合约有满 12 个月的
# 真实基数，覆盖率自然过线，线就回来了，不用有人记得回来改这里。
YOY_MIN_COVER = 0.60


def lvl(n, s, title, *, win=None, fmt='f1', yfmt=None, ylab='', note='', pct_series=False,
        breaks=(), show_mom=False, bar_name='Monthly', yoy_drop_note='', roll=True,
        roll_src=None, what='', ratio_extra='', left_zh=''):
    """gsx.lvl_bar → bar_line_dual：浅蓝柱（左轴水平值）+ 右轴 y/y 线。

    `roll=True`（流量类的默认）右轴画 <b>12 个月滚动合计同比</b>；
    `roll=False` 右轴画点对点（单月）同比，并按序列类型给出对应的理由：
    `pct_series=True` → ratio_note（比率不许做滚动均值，硬约束）；
    否则 → stock_note（存量可以做滚动**均值**，本图不做的理由由实测给出）。
    口径判断只在调用点写一次，标签、图注、实测对比全部由这里按同一个开关生成，
    这样「图例上写的口径」和「实际算的口径」不可能分叉。

    `roll_src` 给**由流量推导的比率**用（本页只有年化有机增速一条）：它的滚动口径
    不是「把 12 个月的比率平均」，而是分子分母各自滚动 12 个月再相除
    （见 organic_growth_roll）—— 那样算出来的是真实的「过去一年的有机增速」，
    与「12 个月比率的算术平均」不是一回事，后者才是被 yoy.py 禁掉的那个。

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
    d = s.iloc[-win:]
    mono = (s - s.shift(12)) if pct_series else yoy_of(s)
    if pct_series:
        rl = ((roll_src - roll_src.shift(12)) if roll_src is not None else mono)
    else:
        rl = roll_yoy_of(s)
    ys = (rl if roll else mono).iloc[-win:]
    cal = 'y/y (pp, 12M roll, RHS)' if pct_series else 'y/y (12M roll, RHS)'
    if not roll:
        cal = 'y/y (pp, 单月, RHS)' if pct_series else 'y/y (单月, RHS)'

    # ── 左端裁决（见 docstring）：柱是主腿，y/y 是派生腿；bar_line_dual 不属 DENSE，
    #    所以 resolve 只把左端推到**柱自己第一个有值的月**，派生腿的前导 null 交给
    #    引擎断笔。`w.why` 里那句「y/y 比柱短 N 期」也由它生成，本页不再手写。──
    _labels = [mlab(p) for p in d.index]
    _lag = ('滚动 12 个月合计同比要 24 个月历史' if roll and not pct_series else
            '滚动口径要 24 个月历史' if roll else '单月同比要 12 个月历史')
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
    AXIS_KIND[n] = (('roll' if roll else 'mono') if cover >= YOY_MIN_COVER else None)
    if cover >= YOY_MIN_COVER:
        if roll:
            why = roll_note(caliber_stats(mono, rl, d.index), 'pp' if pct_series else '%')
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
        # 近零基数：换成滚动口径也救不了 —— 分母是「去年那一年几乎没有业务」，
        # 滚动合计同样会算出几千个百分点。这类序列的正确做法是**不画同比、改画水平值**，
        # 正是本分支干的事。两种口径的实测读数区间一起印出来，好让人相信这不是懒。
        mf, rf = mono.iloc[-win:].dropna(), rl.iloc[-win:].dropna()
        both = (f'两种口径都救不了这条序列：单月同比在本窗口内落在 '
                f'{mf.min():+,.0f}%–{mf.max():+,.0f}%（{len(mf)} 个点），'
                f'12 个月滚动合计同比落在 {rf.min():+,.0f}%–{rf.max():+,.0f}%（{len(rf)} 个点，'
                f'标准差 {rf.std(ddof=0):,.0f}pp vs 单月 {mf.std(ddof=0):,.0f}pp）—— '
                '滚动口径在这里反而更吵，因为它的分母是「去年那一整年业务还没起量」。'
                '<b>近零基数的序列不该画同比，该画水平值</b>，所以本图直接在柱上标数。'
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
# 存量：期末资产，右轴保留单月同比（roll=False）。
lvl(2, tpa, 'Total platform assets', win=len(W25), fmt='usd0', ylab='$bn', breaks=BK_TPA,
    roll=False, what='总平台资产',
    note='Previously reported as Assets Under Custody; renamed and widened to include '
         'TradePMR-advised assets not custodied by Robinhood.')

# 流量：净流入，右轴换 12 个月滚动合计同比。
lvl(3, nd, 'Net deposits', win=len(W25), fmt='usd1', ylab='$bn', show_mom=True, breaks=BK_ND,
    note='m/m shown because net deposits swing far more than any y/y can express.')

# 有机增速的分子就是净流入，断点原样传导过来（同 build/schw.py 对 core NNA 的处理）：
# 分子跨了口径变化，比率也跨了，只在净流入那张画线等于让读者以为这张没受影响。
# 柱仍是**当月**年化率（GS 的流量口径规矩），右轴换成滚动口径那条比率的百分点差。
lvl(4, df['organic_growth_ann'], 'Annualised organic growth rate', win=len(W25), fmt='pct1',
    ylab='% annualised', pct_series=True, breaks=BK_ND,
    roll_src=df['organic_growth_roll'],
    note='Monthly net deposits x 12 / prior month-end total platform assets — the same '
         'convention used for Schwab core NNA and LPL organic NNA in this series. '
         '柱是当月年化率；右轴画的是「滚动 12 个月净流入 ÷ 12 个月前的月末平台资产」'
         '这条比率的<b>百分点差</b>，不是当月年化率的百分点差。')

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
    breaks=BK_CUST, roll=False, what='入金客户数', note=_ex5_note)

_b = df.iloc[-13:]
EX.append({
    'n': 6, 'kind': 'bridge_bar', 'title': 'What moved platform assets: flows vs. markets',
    'xlabels': XL13, 'fmt': 'usd0', 'ylab': '$bn change',
    'stacks': [
        {'name': 'Net deposits', 'color': 'NAVY', 'values': L(_b['net_deposits_usdbn'])},
        {'name': 'Market gains (balancing)', 'color': 'BLUE', 'values': L(_b['market_gains_usdbn'])},
    ],
    'net': {'name': 'Total change in platform assets', 'values': L(_b['tpa_change_usdbn'])},
    'net_color': 'INK',
    'note': 'Identity: opening assets + net deposits + market gains = closing assets. '
            'Market gains is the balancing item, so it also absorbs any acquired assets',
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

# ADV 是「每天平均多少量」的流量率：12 个月滚动合计同比与「滚动 12 个月日均量的同比」
# 是同一个数（分子分母都乘了同样的月数），所以照流量处理，roll=True。
lvl(7, df['adv_equity_usdbn'], 'Equity notional ADV', win=len(W25), fmt='usd1', ylab='$bn / day',
    show_mom=True, left_zh=ADV_LEFT,
    note='m/m shown: equity volume is running at more than twice last year, so y/y '
         'alone no longer separates months.')

lvl(8, df['adv_options_mn'], 'Options contracts ADV', win=len(W25), fmt='f1',
    ylab='mn contracts / day', show_mom=True, left_zh=ADV_LEFT)

_c = df.iloc[-15:]
_cshare = (_c['adv_crypto_bitstamp_usdmn'] /
           (_c['adv_crypto_app_usdmn'] + _c['adv_crypto_bitstamp_usdmn']) * 100)
_ex9 = {
    'n': 9, 'kind': 'stacked_dual', 'title': 'Crypto ADV: Robinhood App vs. Bitstamp',
    'xlabels': XL15, 'xstep': 2, 'fmt': 'f0c', 'ylab': '$mn / day',
    'ylab2': '% Bitstamp (RHS)',
    'stacks': [
        {'name': 'Robinhood App', 'color': 'NAVY', 'values': L(_c['adv_crypto_app_usdmn']),
         'label': True, 'label_color': 'WHITE'},
        {'name': 'Bitstamp', 'color': 'BLUE', 'values': L(_c['adv_crypto_bitstamp_usdmn']),
         'label': True, 'label_color': 'NAVY'},
    ],
    'line': {'name': '% Bitstamp (RHS)', 'color': 'GREEN', 'values': L(_cshare),
             'ymax': float(np.ceil(np.nanmax(_cshare.values) / 10.0) * 10)},
    'note': 'Bitstamp is institutional and carries a different take rate from the '
            'retail app, so the mix shift matters for revenue, not just for volume.',
}
_bk9, _seg9 = breaks_for(9, _c.index, BK_CRYPTO)
_ex9.update(_bk9)
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
# 四条费率跨 1.0 到 55：Options 41–51 c/contract、Crypto 20–55bp 是一档，
# Equities 1.28–1.73bp、Event 1.00–1.19 c/contract 是另一档。原来四条共用一根线性轴，
# 低位两条被完全压在零刻度线上、一条盖着另一条，整个窗口看不出任何变化——而图注自己
# 就写着「线性轴会把股票与事件合约压到零附近」。既然知道，就不该这样发出来。
# 引擎没有对数轴（也不许有：读者按线性直觉读对数轴会把 10x 读成 2x），
# 所以按本仓既有规矩「不同量纲本来就不该同轴」拆成两张，每张两条线各自读得出变化。
# 拆的依据是量级不是单位：按单位拆（c/contract 一张、bp 一张）会把 45 和 1.1 放同一张，
# 压扁的问题原样保留。每条线的单位写在它自己的图例名里。
# 窗口必须显式切到 13 个季度（deck 的 win=13）。今天 hood_q.csv 恰好 13 个季度，
# 不切也看不出问题 —— 但 2026Q3 一入库网页就变 14 点而 PDF 仍是 13 点，此后越差越远。
_RATE_SRC = ('Quarterly reported revenue / quarterly volume — derived, not disclosed. ')
_RATE_SPLIT = (
    'PDF 版把四条费率画在同一根对数轴上；网页引擎没有对数轴，改按量级拆两张 —— '
    f'Exhibit {N_RATE_HI} 是 20–55 这一档，Exhibit {N_RATE_LO} 是 1–2 那一档。'
    '两张的单位都混着 c/contract 与 bp（写在各自图例名里），跨图不能直接比高低，'
    '要比就切右上角「表格」视图读逐季数值。')

EX.append({
    'n': N_RATE_HI, 'kind': 'lines', 'markers': True, 'zero_base': True, 'end_label': True,
    'title': 'Effective take rate: options and crypto',
    'xlabels': XQ[-13:], 'fmt': 'f2', 'label_fmt': 'f1',
    'ylab': 'cents/contract (options) · bp (crypto)',
    'series': [
        {'name': 'Options (c/contract)', 'color': 'NAVY', 'values': L(rate_options_c)[-13:]},
        {'name': 'Crypto (bp)', 'color': 'MBLUE', 'values': L(rate_crypto_bp)[-13:]},
    ],
    'note': _RATE_SRC + 'Crypto is the volatile one and it is what makes the revenue '
            f'bridge (Exhibit {N_BRIDGE_TEST}) miss: the rate more than halved from '
            f'{np.nanmax(rate_crypto_bp.values[-13:]):.0f}bp to '
            f'{np.nanmin(rate_crypto_bp.values[-13:]):.0f}bp inside this window. ' + _RATE_SPLIT,
})

EX.append({
    'n': N_RATE_LO, 'kind': 'lines', 'markers': True, 'zero_base': True, 'end_label': True,
    'title': 'Effective take rate: equities and event contracts',
    'xlabels': XQ[-13:], 'fmt': 'f2', 'label_fmt': 'f2',
    'ylab': 'bp (equities) · cents/contract (event)',
    'series': [
        {'name': 'Equities (bp)', 'color': 'RED', 'values': L(rate_equities_bp)[-13:]},
        {'name': 'Event contracts (c/contract)', 'color': 'GREEN', 'values': L(rate_event_c)[-13:]},
    ],
    'note': _RATE_SRC + 'Both are round-number rates an order of magnitude below options '
            'and crypto, which is why they get their own axis. Event contracts have no '
            'rate before the business had volume, so that line starts partway through. '
            + _RATE_SPLIT,
})

_pi = [p for p in pred.index if p in actual_txn.index][-12:]
_pv = np.array([pred.get(p, np.nan) for p in _pi], float)
_av = np.array([actual_txn.get(p, np.nan) for p in _pi], float)
_err = np.where(_av != 0, (_pv / _av - 1) * 100, np.nan)
_mae = float(np.nanmean(np.abs(_err)))
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
            "quarter's actual volumes, versus revenue reported afterwards. Both bars "
            f'cover the same four asset classes. Mean absolute error over the window: {_mae:.1f}%. '
            '本图的左右两轴零点<b>不在同一高度</b>（误差线跨零、对齐会浪费掉四成画布，'
            '引擎因此改为两轴独立缩放，并在图内左上角以红字标出）：柱子的基线只代表左轴，'
            '误差线的零点请看右轴刻度上那条同色虚线。',
})

lvl(N_IMPLIED, df['implied_txn_rev_usdmn'], 'Implied transaction revenue', win=len(W25), fmt='usd0',
    ylab='$mn / month',
    left_zh=f'费率是季度收入 ÷ 季度成交量反解出来的，而 series/hood_q.csv 只回溯到 '
            f'{q.index[0]}，更早的月份反解不出费率（不是成交量缺，是收入那一半缺）',
    note='Assumption: constant take rate within a quarter, back-solved as reported revenue / volume '
         f'({LAST_Q}: options {rate_options_c[LAST_Q]:.0f}c/contract, '
         f'equities {rate_equities_bp[LAST_Q]:.2f}bp, crypto {rate_crypto_bp[LAST_Q]:.1f}bp), '
         'held flat afterwards. Matches its own quarter by construction — '
         f'Exhibit {N_BRIDGE_TEST} is the real test.')

_rq = q.iloc[-13:]
_rcols = ['rev_options_usdmn', 'rev_equities_usdmn', 'rev_crypto_usdmn', 'rev_event_usdmn']
_rshare = _rq['rev_event_usdmn'] / _rq[_rcols].sum(axis=1) * 100
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
    'note': 'Quarterly actuals, not derived. Event contracts went from nothing to a '
            'fifth of transaction revenue in six quarters — the fastest mix shift in '
            'the business.',
})

# ══════════════════════ 生息资产 ══════════════════════
# 存量：期末融资余额（Period-end），右轴保留单月同比。
lvl(18, df['margin_book_usdbn'], 'Margin book', win=len(W25), fmt='usd1', ylab='$bn',
    roll=False, what='期末融资余额',
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
lvl(21, df['assets_per_customer_usdk'], 'Assets per funded customer', win=len(W25), fmt='usd1',
    ylab='$k per customer', breaks=BK_CUST, roll=False, what='户均资产（两个期末数之比）',
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
_w = _qsum.iloc[-13:]
EX.append({
    'n': N_QTR_ND, 'kind': 'qtr_bar', 'title': 'Net deposits by quarter',
    'xlabels': [str(p) for p in _w.index], 'fmt': 'usd1', 'label_fmt': 'usd1',
    'ylab': '$bn per quarter', 'ylab2': 'y/y (季度合计)',
    'legend': 'Complete quarter', 'values': L(_w),
    'partial_months': _nlast, 'qtr_months': 3,
    # 名字里带口径：本页现在同时有三种同比口径（12 个月滚动合计 / 季度合计 / 单月），
    # 图例上不写清楚，读者把这条绿线跟 Exhibit 3 的绿线放一起看必然对不上。
    'line': {'name': 'y/y (季度合计, RHS)', 'color': 'GREEN',
             'values': L(pd.Series(_qyoy, index=_qsum.index).iloc[-13:]), 'yfmt': 'pct0'},
    'note': 'Quarterly totals remove the month-length and month-end timing noise in the '
            'monthly series. '
            '右轴是<b>季度合计同比</b>（本季 3 个月合计 ÷ 去年同季 3 个月合计 − 1），'
            f'与 Exhibit 3 右轴的 12 个月滚动合计同比、以及 Exhibit 1 汇总表的单月同比'
            '都不是同一个口径 —— 三者当期读数并排见页尾「同比口径」那一条。'
            + ('' if _nlast >= 3 else
               ' Latest bar is quarter-to-date and not comparable to full quarters.'),
})

_yrs = sorted({p.year for p in nd.index})[-4:]
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
EX.append({
    'n': 24, 'kind': 'year_lines', 'title': 'Net deposits path by year',
    'xlabels': MON, 'fmt': 'usd0', 'label_fmt': 'usd0', 'ylab': '$bn cumulative',
    'series': _ylines, 'highlight': len(_ylines) - 1,
    'note': 'Cumulative within each calendar year.' + _pnote,
})

# 混合占比（两条流量之比）：实测下来单月与滚动的标准差只差 1.1 倍、且没有一个月符号相反 ——
# 因为它是个被 0–100 夹住的份额，分母不会趋零，同比 pp 差本来就不会爆掉。
# Bitstamp 从 ~4% 涨到 ~57% 是一次真实的结构性迁移，不是噪音，平滑掉反而看不见拐点。
# 所以这张**保留单月口径**（roll=False），并把口径写进图例。
lvl(25, df['crypto_bitstamp_share'], 'Bitstamp share of crypto volume', win=15, fmt='pct0',
    ylab='% of crypto ADV', pct_series=True, breaks=BK_CRYPTO,
    roll=False, what='加密成交量里 Bitstamp 的占比',
    ratio_extra='另外两点：它是被 0–100 夹住的份额，分母是同期加密总量、不会趋零，'
                '所以百分点差本来就不存在小基数爆炸；而 Bitstamp 从个位数涨到过半是一次'
                '真实的结构性迁移，任何平滑都会把那个拐点抹掉。'
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
_wd = _dmean.iloc[-13:]
EX.append({
    'n': N_QTR_DATS, 'kind': 'qtr_bar', 'title': 'Total daily average trades by quarter',
    'xlabels': [str(p) for p in _wd.index], 'fmt': 'f1', 'label_fmt': 'f1',
    'ylab': 'mn trades / day', 'ylab2': 'y/y (季度均值)',
    'legend': 'Complete quarter', 'values': L(_wd),
    'partial_months': _dlast, 'qtr_months': 3,
    'line': {'name': 'y/y (季度均值, RHS)', 'color': 'GREEN',
             'values': L(pd.Series(_dyoy, index=_dmean.index).iloc[-13:]), 'yfmt': 'pct0'},
    'note': 'Quarterly average of the three asset classes; removes the month-length '
            'differences between equity trading days and crypto calendar days. '
            '右轴是<b>季度均值同比</b>（本季 3 个月均值 ÷ 去年同季 3 个月均值 − 1），'
            '口径与 Exhibit 3 / 7 / 8 右轴的 12 个月滚动合计同比不同。'
            + ('' if _dlast >= 3 else
               ' Latest bar is quarter-to-date and not comparable to full quarters.'),
})


def heat(n, s, title, note, legend, n_years=4, fmt='f0'):
    ss = s.dropna()
    yrs = sorted({p.year for p in ss.index})[-n_years:]
    M = [[None] * 12 for _ in yrs]
    for p, v in ss.items():
        if p.year in yrs and np.isfinite(v):
            M[yrs.index(p.year)][p.month - 1] = round(float(v), 6)
    EX.append({
        'n': n, 'kind': 'heat_matrix', 'title': title,
        'rows': [str(y) for y in yrs], 'cols': MON, 'matrix': M,
        'fmt': fmt, 'legend': legend, 'row_head': '年', 'cell_h': 20, 'note': note,
    })


# 两张热力矩阵**豁免**于「换滚动口径」那条规矩：逐格的月度波动与季节形状就是热力图的
# 题眼，平滑掉等于把这类图唯一的信息抹掉。但豁免不等于可以不写口径 —— 标题里必须写「单月」，
# 否则读者会拿格子里的数去核 Exhibit 7 右轴那条滚动线，然后对不上。
heat(27, df['organic_growth_ann'], 'Annualised organic growth rate — 单月年化 (%)',
     'Green = faster organic growth. Colour scale runs on the 5–95 percentile of all '
     'finite cells, so one outlier month does not flatten the table. '
     '格内是<b>单月</b>年化增速（当月净流入 x 12 ÷ 上月末资产），不是 Exhibit 4 右轴的滚动口径 —— '
     '逐格的季节形状正是这张图要看的东西，换成滚动就全抹平了。',
     'Annualised organic growth, 单月 (%)')
_adv_yoy = df['adv_equity_usdbn'].pct_change(12) * 100
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
     + ('，Exhibit 7 右轴画的是 12 个月滚动合计同比' if AXIS_KIND.get(7) == 'roll'
        else '；Exhibit 7 本轮没有右轴同比线（可比点不够），页顶 headline 引用的是'
             '12 个月滚动合计同比')
     + '，两者当期读数差见页尾「同比口径」那一条。',
     'Equity notional ADV y/y, 单月 (%)')


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
# 汇总表的 y/y 列**不换口径**：它恒等于表内算术「本月 ÷ 去年同月」，读者拿第一列除第三列
# 就能验算。换成滚动口径之后这一步会得出另一个数，表内自相矛盾比口径混用更糟。
# 改为在组标题上把口径写死，并在表注里把各口径的当期读数并排现算印出。
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
# 本页口径差距最大的一处，现算不写死：同一条净流入，Exhibit 1 汇总表印单月、
# Exhibit N_QTR_ND 的绿线印季度合计、Exhibit 3 的绿线印 12 个月滚动合计。
_MIX_ND = ''
if None not in (ND_M, ND_Q):
    _MIX_ND = (f'<b>本页口径差距最大的一处就在净流入</b>：{mlab(LATEST)} 的单月同比 '
               f'{ND_M:+,.1f}%（本表 y/y 列）vs Exhibit {N_QTR_ND} 末满季 {ND_QP} 的'
               f'季度合计同比 {ND_Q:+,.1f}% —— 同一条序列，两个都叫 y/y，'
               f'<b>相差 {abs(ND_M - ND_Q):,.0f}pp</b>'
               + (f'；Exhibit 3 右轴的 12 个月滚动合计同比是第三个数 {ND_R:+,.1f}%'
                  f'（与单月差 {abs(ND_M - ND_R):,.0f}pp）。' if ND_R is not None else '。')
               + '差距来自分母：单月比的是去年那一个月，季度比的是去年那三个月，'
               '滚动比的是去年那一整年。三个都对，但只有最后一个能当趋势读。')

_EQ_M, _EQ_R = _my(df['adv_equity_usdbn']), _ry(df['adv_equity_usdbn'])


def _axis_named(kind):
    """右轴口径 → 「Exhibit n（中文名）」串。名单由 lvl() 实际画出来的东西现生成。

    手写这份名单栽过：y/y 覆盖率低于 YOY_MIN_COVER 时 lvl() 会把整张图退成
    bars_labeled（右轴连线都没有），而写死在页尾的「Exhibit 7 / 8 的右轴是滚动同比」
    不会自己知道。序列一回填、覆盖率一变，名单就该跟着变 —— 所以它必须是算出来的。
    """
    return '、'.join(f'Exhibit {n}（{AXIS_ZH[n]}）'
                     for n in sorted(AXIS_KIND) if AXIS_KIND[n] == kind) or '（本轮一张都没有）'


_AX_ROLL, _AX_MONO = _axis_named('roll'), _axis_named('mono')
_AX_NONE = _axis_named(None)

summary = {
    'title': f'Robinhood monthly metrics — {mlab(LATEST)}',
    'heads': [mlab(CUR), mlab(PRV), mlab(YAG), 'm/m', 'y/y 单月', '3Y %ile'],
    'sep': 3,
    'rows': srows,
    'note': f'口径断点：Bitstamp 自 {BRK_BITSTAMP} 并入净流入、加密成交量与客户数；'
            f'TradePMR 的流量自 {BRK_TRADEPMR} 并入净流入；High-Yield Cash 改版于 {BRK_SWEEP} '
            f'把逾 $6bn 从 Cash sweep 挪到 Cash and deposits；WonderFi 自 {BRK_WONDERFI} '
            f'带进约 {WONDERFI_CUSTOMERS_MN * 1000:.0f}k funded customers（股权交易，不是自然获客）。'
            f'带 {MARK} 的格子表示<b>该格的比较区间跨过上述断点</b>，两端不是同一个口径下的数，'
            f'因此数值照登、但不涂红绿。{_fc_ex_txt}'
            '3Y %ile = 当月读数在近 36 个月里高于多少百分比的观测，判据统一取自 '
            '<code>build/pctile.py</code>（全站唯一实现）：把这一行的分位回放近 24 个月，'
            f'若 ≥70% 的月份钉在区间端点，说明这一列对该行没有区分度，留空 —— {_blank_txt}。'
            '比率行的差异用 pp / bp，不用百分比变化。'
            '<br><b>本表的 y/y 列是「单月口径」= 本月 ÷ 去年同月 − 1，与多数图上的右轴不同口径。</b>'
            '不改它是刻意的：这一列恒等于表内算术（第一列 ÷ 第三列），读者可以直接验算；'
            '换成滚动口径后这一步会得出另一个数，表内自相矛盾比口径混用更糟。'
            f'本轮右轴画 12 个月滚动合计同比的图是 {_AX_ROLL}，比这一列稳得多'
            '（这份名单由构建期按各图实际画出来的东西现生成，不手写）。' + _MIX_ND,
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

table = {
    'n': N_TABLE, 'title': '近 13 个月月度指标核对表（官方原始单位，未换算）', 'idx': '月份',
    'cols': [[h, k] for h, k, _c, _d in TCOLS], 'rows': trows,
}

# ────────────────────────── 口径与方法说明 ──────────────────────────
# 断点那一条不许写死「三个断点图上均以红色虚线标出」：窗口每月往前滚，某个断点滚出
# 窗口再变的那天，这句话就变成页面上的第二处「注释说有、图上没有」。
# 由 BRK_DRAWN 现生成 —— 只说真正画上的那几张图。


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
    ])
    + '。汇总表里<b>跨断点的 m/m 与 y/y 都带 †</b>，数值照登但不涂红绿 —— 两端不是同一个口径下的数，'
      '「好消息还是坏消息」这个判断做不了。',

    '<b>费率是反解值，不是披露值</b>：季度披露收入 ÷ 同季披露成交量。量纲换算——$1bn 名义额产生'
    ' r 个 $mn，即 r/1000 的费率 = r x 10 bp；$mn/mn 张 = $/张，x100 得美分/张。'
    '因此「隐含收入 vs 同季实际收入」必然完全吻合，是循环论证、没有信息量；'
    f'<b>唯一有信息量的检验是 Exhibit {N_BRIDGE_TEST}</b>：拿上一季的费率去预测本季收入，'
    '再与事后披露的实际值对照。',

    f'<b>费率图拆成两张（Exhibit {N_RATE_HI} / {N_RATE_LO}）</b>：四条费率跨 1.0 到 55，'
    'PDF 版靠对数轴收在一张图里，而本页的图表引擎没有对数轴。原先四条共用一根线性轴，'
    '股票（1.3bp）与事件合约（1.1c/张）被压在零刻度线上、一条盖着另一条，整个窗口看不出变化。'
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

    # ── 同比口径：本页有四种，逐处点名 ──
    # 「点名」不是客套。读者在同一页上看到三个都叫 y/y 的净流入读数（单月 / 季度合计 /
    # 12 个月滚动合计），如果没人告诉他分母不同，他只会以为哪里算错了。
    '<b>⚠ 同比口径：本页有四种，逐处点名。</b>'
    '(1) <b>12 个月滚动合计同比</b>（本年 12 个月合计 ÷ 上年同 12 个月合计 − 1）—— '
    f'{_AX_ROLL} 的右轴。<b>流量类一律用这个口径。</b>'
    '(2) <b>单月同比</b>（本月 ÷ 去年同月 − 1）—— '
    f'{_AX_MONO} 的右轴，Exhibit 1 汇总表的 y/y 列，'
    f'页顶 brief 里标「单月同比」的读数（与汇总表同口径、可与表逐格对上；brief 里的单月读数'
    '只作位置与口径背离陈述，不作趋势断言），'
    f'以及 Exhibit 27 / 28 两张热力矩阵的逐格读数。'
    f'<b>本轮没有右轴同比线的图</b>：{_AX_NONE} —— 窗口内可比点覆盖率低于 '
    f'{YOY_MIN_COVER:.0%}（判据见下条），整张图退成柱上标数，确切的 y/y 在汇总表里。'
    '<b>前四张保留点对点是实测结论，不是「存量不能平滑」</b> —— 后者是句错话，'
    '本页更正过：存量的合法平滑口径是 <b>12 个月滚动均值同比</b>（去年一整年的平均余额 '
    'vs 前年；数值上等同于滚动合计比，除数约掉了），不能叫的只是「12 个月<b>合计</b>同比」，'
    '因为 12 个月末余额相加不指代任何真实的量。各图图注里给的是本序列自己的实测对照。'
    'Exhibit 25 不同：它是<b>比率</b>，12 个月的占比做算术平均本身就没有意义'
    '（每个月的分母不同），要一年的平均占比必须量加权 —— 那是一条真的硬约束。'
    f'(3) <b>季度合计 / 季度均值同比</b> —— Exhibit {N_QTR_ND}（净流入，季度合计）与 '
    f'Exhibit {N_QTR_DATS}（DATs，季度均值）的右轴。'
    '(4) <b>环比</b> —— 各图图注与页顶 brief 里的 m/m（brief 的日历修正句给的是'
    '「表面 vs 日均」两个环比，喂的是当月合计 vol_*，与图上已日均化的 ADV 不是同一列）。'
    + (f'<br>{_MIX_ND}' if _MIX_ND else '')
    # 「那个滚动读数印在哪儿」得跟着实际走：Exhibit 7 的可比点覆盖率不够时它退成
    # bars_labeled，右轴上根本没有线，再说「Exhibit 7 右轴（滚动）」就是假话。
    + (f'<br>股票名义 ADV 同样两处混用：'
       + ('Exhibit 7 右轴（滚动）' if AXIS_KIND.get(7) == 'roll'
          else '页顶 headline 引用的 12 个月滚动合计同比')
       + f' {_EQ_R:+,.1f}% vs '
       f'Exhibit 28 热力矩阵当月格（单月）{_EQ_M:+,.1f}%，差 {abs(_EQ_M - _EQ_R):,.0f}pp。'
       '热力矩阵不换口径是刻意的 —— 逐格的月度波动与季节形状就是那张图的题眼，'
       '平滑掉等于把它唯一的信息抹掉；标题里已写明是「单月同比」。'
       if None not in (_EQ_M, _EQ_R) else ''),

    '<b>交易日口径不一</b>：股票与期权按交易所交易日折算 ADV/DATs，加密按自然日；'
    f'Crypto DATs 不含 Bitstamp 的机构交易，而 Crypto ADV 含。季度图（Exhibit {N_QTR_ND} / {N_QTR_DATS}）'
    '正是为了抹掉月长与月末时点差异而做的。',

    '<b>Total platform assets 曾名 Assets Under Custody</b>，改名后口径扩大到包含 TradePMR 顾问的'
    '资产（这部分并不由 Robinhood 托管）。',

    # ── 历史从哪里来、为什么各图左端不一样：这一条是 2026-08-19 回填之后新增的 ──
    f'<b>序列起点 {mlab(df.index[0])}，但各图左端不一样，这是数据决定的不是排版决定的。</b>'
    '当期那份月度 Excel 只发<b>滚动三年</b>窗口，2023-04 之前的月份要去 Quarterly Results 页'
    '翻当年的 Earnings Supplement（另一张页、另一种版式）。本站取的一律是'
    '<b>还拿得到的最早那一版</b>（2021-01~2022-12 用 Q1-23 那份、2023-01~03 用 Q1-26 那份），'
    '不用后来重述过的值 —— 实测被后期改过的只有净流入 4 个月各 0.1（脚本每次运行都重列一遍）。'
    f'再往前没有了：公司 2022-04 才开始月度披露、首期回填 12 个月，所以 {mlab(df.index[0])} 是天花板。'
    '<b>老版式的行少一半</b>：没有 ADV 那一节、没有 Cash and Deposits、没有 Bitstamp / '
    'Event contracts 拆分、没有加密交易日，出借收入 2022-05 才有数、Net 那一行 2023-01 才单列。'
    '这些格子<b>留空</b>，不补 0 也不用「成交量 ÷ 交易日」自己算 ADV —— 换算值不是披露值。'
    '于是每张图的左端由 <code>mrwin.resolve()</code> 按它自己那几条序列裁，'
    '各图图注里都写了截在哪一期、被谁定住。'
    f'另有一处口径提示：{mlab(DARTS_UNTIL)} 及更早的 DATs 三列填的是当期印的 <b>DARTs</b>'
    '（公司 2026-07 才改名并重述，且只回溯到 Jan-25，Dec-24 及更早两种口径逐月相同），'
    f'见 Exhibit 11 图注。',

    f'<b>Exhibit 10（事件合约）没有画 y/y 线</b>，不是漏了：窗口内只有少数几个月有大于零的'
    '上年同月基数，画出来是两段近乎垂直的竖线加一段贴地的直线，还会把右轴撑到 3,000% 以上，'
    '除了「涨了很多」读不出任何东西。判据是<b>可比点的覆盖率</b>（低于 60% 就不画），'
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

    ═══ 与本页 2026-08 同比口径改造（CONTRACT §6）的关系（移植时的口径适配）═══
      本页流量类各图的右轴已改画 **12 个月滚动合计同比**（**具体哪几张是算出来的**，
      见 `AXIS_KIND` / `_axis_named()` —— 可比点覆盖率不够的会退成柱上标数、右轴上
      根本没有线，写死名单必然烂掉），而 brief 排在 headline 之下、Exhibit 1（汇总表）
      之上 —— 汇总表的 y/y 列按
      §6.2 豁免、保留单月，所以本段引用 m/m / y/y 时**与汇总表同口径（单月）**，凡同比
      措辞一律写明「单月同比」（§6.1 第 2 条的正文版），不得让读者拿它去对图上的滚动
      绿线；页尾「同比口径逐处点名」的 (2)（单月）与 (4)（环比）两条已把 brief 计入名单。
      单月读数在本段只作**位置与基数**陈述（排名 / 峰值 / 口径背离 / 日历修正），
      不作趋势断言 —— 趋势归图上的滚动口径。峰值扫描那句的主语因此从旧稿的「存量指标」
      改成「指标的当月读数」：篮子里的股票 ADV、证券出借收入在页尾口径条里归**流量类**
      （右轴画滚动），brief 再叫它们「存量」会与同页的口径分类打架；R1 扫的本来就是
      当月水平读数（位置陈述），与流量/存量的同比口径之分无关。
      本页今天新增的派生列（`organic_growth_roll`，滚动口径的有机增速）**不进 R1 篮子**：
      篮子是显式点名的十条，不按列名白名单扫描，派生比率列天然被排除 —— 它是另一条
      序列的平滑读数，「创新高」在它身上不是信息。

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
    # 口径适配（CONTRACT §6.1 第 2 条）：同比一律标「单月」。本页流量图的右轴自 2026-08
    # 起画 12 个月滚动合计同比，这两处单月读数不标口径就会被读者拿去对图上的绿线；
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
# 抬头是多数人唯一会读的一行，所以每个 y/y 都要带口径标签：本页有四种同比口径，
# 一个光秃秃的「y/y」在这里等于误导（读者会拿它去核汇总表，然后对不上）。
# 流量类（股票 ADV、证券出借收入）用滚动口径，与图上那条线是同一个数；
# 存量类（平台资产、cash sweep）用点对点同比 —— 存量也能做 12 个月**均值**同比，
# 但实测下来换了没收益（逐图数字见各自图注），所以留点对点。
_tpa_yoy = float(tpa.iloc[-1] / tpa.iloc[-13] - 1)                 # 存量 → 单月
_tpa_mom = mom_of(tpa)
_nd_mom = mom_of(nd)
_og = float(df['organic_growth_ann'].iloc[-1])
_eq_yoy = (_EQ_R / 100.0) if _EQ_R is not None else float('nan')   # 流量 → 滚动
_fc = float(df['funded_customers_mn'].iloc[-1])
_apc = df['assets_per_customer_usdk']
_apc_mom = mom_of(_apc)
_sl = df['seclend_total_usdmn']
_sl_r = _ry(_sl)
_sl_yoy = (_sl_r / 100.0) if _sl_r is not None else float('nan')   # 流量 → 滚动
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
    _down.append(f'证券出借收入 ${_sl.iloc[-1]:,.0f}mn（{pp_txt(_sl_yoy)} y/y·12M滚动）')

headline = (
    f'总平台资产 ${tpa.iloc[-1]:,.0f}bn（{pp_txt(_tpa_yoy)} y/y·单月，但 {pp_txt(_tpa_mom)} m/m） · '
    f'净流入 ${nd.iloc[-1]:,.1f}bn（{pp_txt(_nd_mom)} m/m'
    + (f'，{pp_txt(ND_R / 100.0)} y/y·12M滚动' if ND_R is not None else '')
    + f'，年化有机增速 {_og:.1f}%） · '
    f'股票名义 ADV ${df["adv_equity_usdbn"].iloc[-1]:,.1f}bn/日（{pp_txt(_eq_yoy)} y/y·12M滚动） · '
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
