# -*- coding: utf-8 -*-
"""HKEX 香港交易所 (0388.HK) 月度市场统计 —— 网页看板数据生成器。

把 build/build_hkex.py（matplotlib / PDF）里的每一张 exhibit 重新实现成 payload 里的
一个 exhibit 对象，写出 data/hkex.js。图序、编号、标题文案、图注、口径断点全部照搬原 deck。

原 deck 的设计（模块 docstring，逐条沿用）：
  模版来源 Goldman Sachs「Hong Kong Exchanges (0388.HK): New listings and profit growth
  inflection to drive sustainable ADT growth」（Exhibit 1-15）与「Multiple tailwinds in
  2026E despite weak Nov ADT」（Exhibit 1-28）。核心做法：
    1) 三层时间窗：超长历史判周期位置 / 中长期判趋势 / 近 13-25 个月讲当下；
    2) 双图开场：整体 ADT 与南向 ADT 并列；
    3) 驱动量置顶：ADT / 衍生品张数这类经营量指标放在汇总表最上方，先于市值等存量。

数据源（只读 series/，不读 build/data/）：
  series/hkex.csv       HKEX Monthly Market Highlights 月度序列
  series/fee_rates.csv  HKEX 季度费率与现货分部收入（量→收入桥用）

用法: python3 build/hkex.py
"""
import datetime
import json
import os
import re

import numpy as np
import pandas as pd

import brief as B
from monthlab import mlab   # x 轴月份标签 Jul-26 的唯一实现
import payload_guard
import pctile
import repo            # 仓库定位 + 发布日台账入口

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SERIES = os.path.join(ROOT, 'series')

TICKER = 'hkex'
SRC = 'Source: HKEX Monthly Market Highlights; format after Goldman Sachs GIR'


# ────────────────────────────── 读数据 ──────────────────────────────


def qlab(q):
    """PeriodIndex(freq='Q') 的一格 → 「2026-Q2」，与 series/fee_rates.csv 的 period 列同写法。"""
    return f'{q.year}-Q{q.quarter}'


def load():
    df = pd.read_csv(os.path.join(SERIES, 'hkex.csv'))
    df['month'] = pd.PeriodIndex(df['month'], freq='M')
    df = df.set_index('month').sort_index()
    for c in df.columns:
        df[c] = pd.to_numeric(df[c], errors='coerce')
    need = ['adt_hkdbn', 'mktcap_hkdtn', 'new_listings', 'ipo_funds_hkdbn',
            'derivatives_adv_contracts', 'southbound_adt_hkdbn']
    miss = [c for c in need if c not in df.columns]
    if miss:
        raise SystemExit(f'series/hkex.csv 缺列: {miss}')
    return df


def rate_series(metric, scale=1.0):
    """series/fee_rates.csv 里 HKEX 的某个季度参数，索引 PeriodIndex(freq='Q')。"""
    d = pd.read_csv(os.path.join(SERIES, 'fee_rates.csv'))
    d = d[(d['company'] == 'HKEX') & (d['metric'] == metric)].copy()
    if not len(d):
        raise SystemExit(f'fee_rates.csv 里没有 HKEX/{metric}')
    d['q'] = pd.PeriodIndex(d['period'].str.replace('-', ''), freq='Q')
    return d.set_index('q')['value'].astype(float).sort_index() * scale


def to_monthly(rate_q, month_index):
    """季度费率 → 月度：当季各月用该季费率；最新季之后沿用最后一个已知值。"""
    q = pd.PeriodIndex(month_index).asfreq('Q')
    return pd.Series([rate_q.get(x, np.nan) for x in q],
                     index=month_index, dtype=float).ffill()


# ────────────────────────── 费率口径披露（全部现算，不写死季度号） ──────────────────────────
# 月度量每月往前走，费率按季度更新 —— 所以「最新一两个月的隐含值用的是上一季费率」是这一页
# 的常态，不是 bug。但读者有权知道自己看的这个月是拿哪一季的费率算出来的，尤其在公司财报
# 延迟、费率落后两个季度以上的时候。
#
# 下面两个函数**只从数据现算**季度号与落后月数：本仓已经因为把季度号／图形特征写死在文案里
# 翻过车（schw 的「过去 32 个季度单边降」、cost 的「Exhibit 4 画了红线」），
# 写死的句子下一季就变成假话，而且没有任何检查会响。
#
# 过期判据（两个函数共用）：**同一季费率被沿用的月数 ≥ 5**。
# 判据写成月数而不是「落后几个季度」，是因为后者在每个季度刚翻页时都会误报：
# 数据月 Jul-26 落在 2026-Q3，「上一季」是 2026-Q2，而 HKEX 的 Q2 业绩要到八月中才发 ——
# 那时费率最新只能到 2026-Q1，按季度差判就成了「落后两季」，可它完全正常。
# 按月数看则很干净：一季费率正常最多被沿用 4 个月（本季 3 个月 + 下季首月、业绩未发），
# 第 5 个月还在沿用，就说明公司披露真的晚了或漏了一季，那时才值得提示。
STALE_CARRY_MONTHS = 5


def _carry_months(rq_last, last_month):
    """数据月里「本季费率尚未披露、只能沿用 rq_last」的那些月份。"""
    first = rq_last.asfreq('M', 'end') + 1
    if last_month < first:
        return []
    return list(pd.period_range(first, last_month, freq='M'))


def _stale_tail(rq_last, last_month):
    """费率落后到异常程度时的显式提示，否则空串。"""
    carry = _carry_months(rq_last, last_month)
    if len(carry) < STALE_CARRY_MONTHS:
        return ''
    return (f' <b>⚠️ 费率已经落后</b>：最新可得仍是 {qlab(rq_last)}，'
            f'到 {mlab(last_month)} 已被连续沿用 {len(carry)} 个月 —— '
            f'{qlab(rq_last + 1)} 及之后各季公司尚未披露费率。'
            f'一季费率正常最多沿用 {STALE_CARRY_MONTHS - 1} 个月，'
            f'超过即为披露延迟；在补上之前，本页隐含值仍按 {qlab(rq_last)} 的费率计算。')


def vintage_monthly(rate_qs, last_month, what, scope='本图'):
    """月度隐含值图的费率口径句：最后一个数据月用的是哪一季费率、有几个月在沿用上一季。

    rate_qs 给这张图实际用到的**全部**季度参数（费率 + 交易日数）；取它们里最早的末季，
    这样 fetch 只补上其中一个 metric 时，图注说的仍是真正生效的那一季。
    """
    rq_last = min(s.index[-1] for s in rate_qs)
    carry = _carry_months(rq_last, last_month)
    txt = (f'<b>费率口径</b>：{what}取公司披露的季度值，最新可得为 {qlab(rq_last)}；'
           f'{scope}数据截至 {mlab(last_month)}，')
    stale = _stale_tail(rq_last, last_month)
    if carry:
        span = mlab(carry[0]) + (f' 至 {mlab(carry[-1])}' if len(carry) > 1 else '')
        txt += (f'其中 {span} 这 {len(carry)} 个月尚无对应季度的披露费率，'
                f'一律沿用 {qlab(rq_last)} 的费率。')
        # 这句安抚只在沿用月数还在正常区间时说；已经判为落后了还说「是常态」就是自相矛盾
        if not stale:
            txt += '月度量按月走、费率按季更新，最新一两个月用上一季费率是这一页的常态口径，不是缺数。'
    else:
        txt += f'费率已覆盖到该月所在的 {qlab(rq_last)}，没有任何月份在沿用更早的费率。'
    return txt + stale


def vintage_quarterly(last_plotted_q, month_of_page, what):
    """季度图的费率口径句：最后一格是哪一季、比本页月度数据落后多少。"""
    data_q = month_of_page.asfreq('Q')
    lag = (data_q - last_plotted_q).n
    txt = (f'<b>费率口径</b>：{what}按季披露，x 轴最后一格是 {qlab(last_plotted_q)}；'
           f'本页月度数据已到 {mlab(month_of_page)}（{qlab(data_q)}），'
           + (f'比费率新 {lag} 个季度 —— 季度口径本就滞后于月度量，本图只画有披露的季度、不外推。'
              if lag else '两者同季。'))
    return txt + _stale_tail(last_plotted_q, month_of_page)


def tail_contiguous(s):
    """只保留末尾逐月连续的一段（南向通 2022-2024 断档 40 个月，直接取尾 N 个点
    会把相隔数年的月份并排画成相邻期 —— 那是假的时间轴）。同 gsx._tail_contiguous。"""
    s = s.dropna()
    if len(s) < 3:
        return s
    idx = list(s.index)
    gaps = [(idx[i] - idx[i - 1]).n for i in range(1, len(idx))]
    stride = max(set(gaps), key=gaps.count)
    start = 0
    for i in range(len(idx) - 1, 0, -1):
        if (idx[i] - idx[i - 1]).n != stride:
            start = i
            break
    return s.iloc[start:]


# ────────────────────────────── 格式化（一律在 Python 侧） ──────────────────────────────
def L(a):
    return [round(float(v), 6) for v in a]


def LN(a):
    return [None if v is None or not np.isfinite(v) else round(float(v), 6) for v in a]


def nz(txt):
    """去掉「负零」。f-string 对 -0.4%（dec=0）印出的是「-0%」、对 -0.004pp 印出「-0bp」——
    在一整列两位数里特别扎眼，读者会停下来想这是不是缺失值（人眼审查在 tsm Ex13 与
    exchanges Ex8 各报了一条）。四舍五入到零就是零，符号已经没有信息了。"""
    for bad, good in (('-0%', '0%'), ('-0.0%', '0.0%'), ('-0pp', '0pp'), ('-0.0pp', '0.0pp'),
                      ('-0bp', '0bp'), ('+0bp', '0bp')):
        if txt == bad:
            return good
    return txt


def num(v, dec=1, pct=False):
    """汇总表的水平值。pct=True 的行带百分号 —— gsx.summary_table 的 _fmt(pct=True)
    印的就是「40.7%」，网页版原先只印「40.7」，同一张表里比率行与水平值行分不出来。"""
    if v is None or not np.isfinite(v):
        return '—'
    return f'{v:,.{dec}f}' + ('%' if pct else '')


def pctf(x, dec=0):
    """oval / headline 用的百分比。正负号交给 f-string 的 + 标志。"""
    return '—' if not np.isfinite(x) else nz(f'{x * 100:+.{dec}f}%')


def ppf(x, dec=0):
    return '—' if not np.isfinite(x) else nz(f'{x:+.{dec}f}pp')


def yoy_line(s_full, win=25, pct_series=False, lag=12):
    """次轴同比序列，口径逐条照搬 gsx.lvl_bar（deck 在 lvl_bar 的次轴上画的是同比，
    不是滚动均线 —— 均线只是把柱子再平滑一遍、不带新信息）。

      · 比率序列（pct_series=True）的同比用**百分点差**，不是「百分比的百分比变化」；
      · 基数过小（|去年同月| < 0.15 × 全序列绝对值中位数）或与当期异号时放弃同比 ——
        那种同比不是信息，是把一个接近零的分母放大成三位数。

    同比在**切窗口之前**算：窗口只有 25 个月，切完再算会让前 12 根柱没有同比。
    """
    v = np.asarray(s_full.values, float)
    scale = float(np.nanmedian(np.abs(v))) or 1.0
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
    return out[-win:]


def yoy_rhs(s_full, win=25, pct_series=False):
    """gs_bar 的次轴 y/y 字段（给了它引擎就画同比折线、不画均线）。"""
    return {
        'name': 'y/y (pp, RHS)' if pct_series else 'y/y (RHS)',
        'color': 'GOLD',
        'yfmt': 'pp0' if pct_series else 'pct0',
        'values': LN(yoy_line(s_full, win, pct_series)),
    }


def yoy(a, lag=12):
    """序列末期相对 lag 期前的变化率（小数）。"""
    a = np.asarray(a, float)
    if len(a) <= lag or not np.isfinite(a[-1]) or not np.isfinite(a[-1 - lag]) or a[-1 - lag] == 0:
        return np.nan
    return a[-1] / a[-1 - lag] - 1


def mom(a):
    a = np.asarray(a, float)
    if len(a) < 2 or not np.isfinite(a[-1]) or not np.isfinite(a[-2]) or a[-2] == 0:
        return np.nan
    return a[-1] / a[-2] - 1


# 原先这里有个 avg_prior12()，给 gs_bar 的 12 个月均线用。本页六张 lvl_bar 图已按原 deck
# 改画次轴 y/y（见 yoy_rhs），均线不再出现，函数随之删除 —— 留着会让下一个人以为还有图在用。


def _plain_len(sentences):
    """句子列表的去标签字数 —— 与 `brief.render()` 的字数口径逐字符一致（含 h4 标题）。"""
    return len(re.sub(r'<[^>]+>', '', B.TITLE + ''.join(s for s in sentences if s)))


def _liang(txt):
    """量词前的「2」在中文里写「两」，不写「二」。

    `brief.cn()` 给的是序数形式（一二三…），共享规则库是只读的，所以在本页的展示层改：
    「二条主序列」「多披露二个月」都不是中文。只碰这两个组合，别的「二」（月份、名次
    都是阿拉伯数字）碰不到。
    """
    return txt.replace('二条', '两条').replace('二个月', '两个月')


def compose_brief(df, LATEST, NEWEST):
    """HKEX 页顶部的 ~300 字数据总结（payload 的 `brief` 字段）。

    规则库在 `build/brief.py`（R1 峰值扫描 / R2 基数护栏 / R3 日历护栏 / R4 单位恒等 /
    R5 标注 / R6 有效位），那边只算事实，句子在这里拼 —— 措辞是口径的一部分，属于各家自己。
    职责与 `headline` 互补：那一行给读数，这一段给「读数该怎么读」，所以**刻意不复述**
    headline 与 Exhibit 1 已经印过的水平值、m/m、y/y，只讲排名／峰值位置／背离／口径错位。
    每个数字都当场从序列算出，没有一处硬编码：排名、「N 个月最低」、峰值月份、倍数、
    「多披露一个月」的那个月份，下月重跑都会自己变。

    ═══ 分寸以 build/ibkr.py 的 compose_brief() 为准（2026-08 定）═══
    那一版是逐句验收过的样板：**四句话四个层次，每句一个意思**。本页把它对到
    规模（峰值扫描）／基数（ADT 上月名次）／分母（期间倍数 + 换手率恒等式）／口径
    （南向断点、各列截止月错位）—— 口径占两句，所以是五句，这是上限。
    第一版在这里写成了七句：「成交创纪录≠规模创纪录」与后面的换手率恒等式讲的是
    同一件事（分子创新高、分母自己在动），期间倍数又单独占一句再说第三遍，
    读起来像研究报告摘要而不是导读。合并成一句「分母」之后三层只讲一次。

    ═══ HKEX 独有，别家不能照抄 ═══
      · **R3（日历护栏）在这一页整条不适用**：HKEX 披露的 `adt_hkdbn` 与
        `derivatives_adv_contracts` 本来就是 ADT / ADV（**已经日均化**），再除一次交易日
        会造出一个根本不存在的修正。同理 R4 的 regime_ratio 在别家要先把成交量除交易日，
        这里**不能除** —— 两条序列进去时已经是「每日」口径。
      · **换手率是本页唯一能把「量」与「存量」接起来的推导值**（ADT × 252 ÷ 市值，
        252 是惯例年化交易日数、非当年实际），故正文必带「（推导值）」。ADT 创新高而
        换手率没有，差额只能是市值这个分母 —— 这个对照是 HKEX 特有的，别家没有
        「同一个分子配一个会自己涨跌的分母」的结构。写法走 R4 的单位恒等（`per_unit`）：
        只报**两个增速之商**（换手率同比 ≡ ADT 同比 ÷ 市值同比），不做「多少来自分子、
        多少来自分母」的比例拆分 —— 那个拆法在数学上就是错的。
      · **南向 ADT 的排名不能用全样本**：中间整段停发过，所以「最近 36 个观测」不是
        三年窗口（Exhibit 1 的 3Y %ile 对它留空正是这个理由）。句子里报的是**当场从
        观测索引算出的缺口长度**与「凑满 36 个观测要回溯到哪个月」，不报「跨 N 年」——
        `(末月 − 首月) // 12` 的地板除会把 7.42 年写成「7 年」，而且与 Exhibit 1 表注
        的「最近 36 个观测横跨六年多」并列在同一页上，读者会以为其中一个算错了。
        排名改在 `tail_contiguous()` 取出的**恢复披露后连续段**里算，与 Exhibit 5
        「缺口不用直线连」是同一条口径。
      · **各列截止月不一样**：HKEX 是分列到货的（当前是 IPO 募资 / 衍生品 ADV / 南向
        跑在现货前面，但**哪几列领先每个月都不一样**），而汇总表与 headline 一律锁死在
        核心量齐备的那个月。多出来的月份只出现在核对表里，本段专门把它点出来。
        所以「有没有错位」与「IPO 是不是领先的那一列」必须**分两级判**：合成一个守卫时，
        IPO 不领先而别的列领先的月份会落到 else，印出与事实相反的「各列截止月一致」。
    """
    M = [str(p) for p in df.loc[:LATEST].index]
    i, n = len(M) - 1, len(M)
    d = df.loc[:LATEST]
    adt, dv = d['adt_hkdbn'].values, d['deriv_adv_k'].values
    mc, vel = d['mktcap_hkdtn'].values, d['velocity'].values
    # 南向不取 .values：它有真实缺口，下面一律走 dropna() 后的 ser / tail_contiguous(seg)。

    # ── R1：峰值扫描。四条主序列都不是单调列（T3），故走 skip_monotonic 默认值；
    #    真有一条变成只增不减时它会被自动剔除，句中的「N 条」也随之减一。
    ADT_LAB, VEL_LAB = '现货ADT', '换手率'
    pk = B.peak_scan(M, [(ADT_LAB, adt), ('衍生品ADV', dv), ('市值', mc), (VEL_LAB, vel)], i)
    grp = {}
    for nm, k in pk['off_peak']:
        grp.setdefault(k, []).append(nm)
    # 组内（同一个峰值月的几条序列）用「、」，组间用「；」。两级都用「、」的话，三组以上
    # 会串成「A停在M1、B、C停在M2」，B 看上去像个没有归属的裸项，读者判不出它归哪个月。
    off_txt = '；'.join(f'{"、".join(v)}停在{k}' for k, v in grp.items())
    at = pk['at_peak']
    tot = len(at) + len(pk['off_peak'])
    # 「只有」必须由算出来的占比决定：写死它，某个月 at_peak 变成全部时就会印出
    # 「一条主序列里只有现货ADT创新高」这种把全线新高说成稀缺的句子。故走 B.quant。
    #    tot == 0（序列开头几个月里四条全被 is_monotonic 判为只增不减而剔除）时整句不写：
    #    B.cn(0) 返回 '0'，硬拼会印出「0条主序列本月一个新高都没有」。
    #    全中与全不中各走一条自己的分支：B.quant 在 k == n 时给「多达」，而「四条里多达
    #    四条」和它要防的「四条里只有四条」是同一种别扭，全线新高就该直说「全部」。
    s1 = ''
    if at and len(at) == tot:
        s1 = f'{B.cn(tot)}条主序列本月全部创{n}个月新高'
    elif at:
        s1 = (f'{B.cn(tot)}条主序列{B.quant(len(at), tot, "条")}创{n}个月新高'
              f'（<b>{"、".join(at)}</b>）')
    elif tot:
        s1 = f'{B.cn(tot)}条主序列本月一个新高都没有'
    if s1:
        s1 += (f'，{"其余" if at else "各自"}峰值：{off_txt}' if off_txt else '') + '。'
    # ── R2：基数护栏。本页最常见的误读是把「从高位再上一档」当成低基数反弹，所以报的是
    #    **上月自己的名次**。但这个结论有条件：上月名次掉出前四分之一时，环比里就真有
    #    基数成分，那时必须反过来说 —— 一句写死的「不是低基数反弹」在低位月是假话。
    #    主语必须写出来（`现货ADT上月…`）：省略主语时，承前省略会让读者把这个名次挂到
    #    上一句最后一个名词（市值）上，而「不是低基数反弹」套到市值上正好读反。
    #    判据用**纯四分位**（rank×4 ≤ n），不留 `max(2, …)` 那个下限：n=90 时两者都取
    #    第 22 名、结论一字不差，但样本只有两三个月时那个下限会把「上月是全样本最低」
    #    也算成前四分位，于是印出「不是低基数反弹」——正好读反。
    be = B.base_effect(adt, i)
    if be['mm'] is not None:
        top = be['prev_rank'] * 4 <= n
        # 名次后面补分位（走 B.top_pct，向上取整）：光看「排第 5」判不出这是高位还是中段，
        # 而「前 6%」正是后半句那个四分位判定的可核对形式，读者能自己验。
        # 两处不补：上月就是全样本最高（「第 1（前 1%）」是废话）；样本不足 12 个月 ——
        # 序列开头 n=2 时「排第 2（前 100%）」是个纯噪音的百分数，重放里真会印出来。
        prev = ('本就是全样本最高月' if be['prev_is_max'] else
                f'排第{be["prev_rank"]}'
                + (f'（{B.top_pct(be["prev_rank"], n)}）' if n >= 12 else ''))
        if be['mm'] > 0:
            judge = '不是低基数反弹' if top else '这个环比含低基数成分'
        else:
            judge = '是从高位往下' if top else '低位再下一档'
        s1 += f'{ADT_LAB}上月{prev}，<b>{judge}</b>。'

    # ── 分母（R4）：期间均值对期间均值 + 单位恒等，合成一句。
    #    原先这里是三句：「成交创纪录≠规模创纪录（市值比换手率峰值月高 X%）」、
    #    「市值为 N 个月最低、同比为正而环比在跌」、「2019 年均→近 13 个月：ADT 3.0 倍、
    #    市值 1.4 倍」。三句讲的是同一件事——分子在创纪录、分母自己也在动——只是换了
    #    三种度量（相对峰值月 / 相对上月与去年 / 相对起点年）。样板（build/ibkr.py）
    #    的对应位置是**一句**：期间倍数 + 户均值的恒等式 + 一句短落点。照它合成一句。
    #
    #    期间倍数：ADT 进去时已是日均口径，**不再除交易日**（R3 在本页不成立）。
    #    送进去的与印出来的必须是同一组列，否则 `down` 里会冒出一个正文没给过倍数的名字。
    #    换手率不送进 regime_ratio：它按定义就是 ADT ÷ 市值，第三个倍数是前两个的商。
    rg = B.regime_ratio(M, [('ADT', adt), ('市值', mc)], i)
    r = dict(rg['ratios'])
    head = (f'{rg["y0"]}年均→近{len(rg["win_idx"])}个月均值 ADT {r["ADT"]:.1f}倍、'
            f'市值{r["市值"]:.1f}倍'
            + (f'（{"、".join(rg["down"])}低于起点）' if rg['down'] else '')) if len(r) == 2 else ''

    #    恒等式：换手率同比 ≡ (1+ADT 同比)/(1+市值 同比) − 1，只报两个增速之商。
    #    scale 与 df['velocity'] 同式（×252÷1000×100），这样 pu['series'] 与图上那条线
    #    逐点相等；读数与名次仍一律取 `vel`（图与汇总表用的就是它），一个数只有一个来源。
    pu = B.per_unit(adt, mc, i, scale=252 / 1000 * 100)
    body = ''
    if B.need(vel[i]):
        rk = B.rank_of(vel, i)
        pos = f'为{n}个月最高' if rk == 1 else f'排{n}个月第{rk}'
        # 「没跟着 ADT 创新高」是定性词，必须由两条序列各自在不在峰值上决定：写死它，
        # ADT 本身不在峰值的月份就会凭空多出一个对照（本仓已经栽过一次的那类 bug）。
        cmp_v = ('、与ADT同步见顶' if VEL_LAB in at else '、没跟着ADT创新高') if ADT_LAB in at else ''
        body = f'{VEL_LAB}（推导值）<b>{vel[i]:.1f}%</b>{pos}{cmp_v}'
        if B.need(pu.get('yoy'), pu.get('num_yoy'), pu.get('den_yoy')):
            # 落点必须同时看**商的方向**与**两个增速各自的正负**。上一版照搬了 regime 版
            # 的「ga ≥ gb → 两端同步扩张」，而 regime 的两个倍数恒为正、同比不是：
            # 重放到 2023-01（ADT +8.8%、市值 −7.5%）就印出「两端同步扩张」，而市值在缩。
            # 商在 ±10% 以内不给方向词——那点差异说不出谁跑赢谁。
            if abs(pu['yoy']) < 0.10:
                verdict = '两端大体同步'
            elif pu['yoy'] > 0:
                verdict = ('放大在周转不在规模' if pu['den_yoy'] > 0 else
                           ('成交在涨而规模在缩，两头都在抬它' if pu['num_yoy'] > 0 else
                            '成交自己也在跌，抬它的是缩水的分母'))
            else:
                verdict = ('规模跑在成交前面' if pu['num_yoy'] > 0 else
                           ('成交在跌而规模还在涨' if pu['den_yoy'] > 0 else
                            '两端同步收缩、成交跌得更多'))
            body += (f'，同比{B.pct(pu["yoy"])}是 ADT {B.pct(pu["num_yoy"])}'
                     f'除以市值{B.pct(pu["den_yoy"])}的商，{verdict}')
    s2 = ('分母：' + '；'.join(x for x in (head, body) if x) + '。') if (head or body) else ''

    # ── 南向的口径断点。
    #    这里原先还有一句「三条成交量序列里只有 X 环比走低」，已整句删除，两个理由：
    #      1) 它是**复述 headline**。抬头那一行已经逐条印出 ADT / 南向 / 衍生品 ADV 的
    #         m/m，谁在往下走一眼可见；本段的职责是「读数该怎么读」，不是把 m/m 再数一遍
    #         （brief.py 模块 docstring 明令禁止复述式摘要）。
    #      2) 它的写法本身有错且不可救：`(mm or 0) < 0` 把「本月没读数」折成 0、当作
    #         「没下跌」，于是南向停发的月份会印出「三条一致向上」，紧接着下一句又说
    #         「南向本月未披露」——同一段自相矛盾，而南向 2022-01 起真停发过 42 个月。
    #         条数「三条」也是写死的中文数字，不随实际有读数的序列数变化。
    #    删掉即同时解决两件事；下面这段本来就按 seg / ser 的实际可得性分支，不折缺值。
    # 「恢复披露后」「中间整段停发」这两句只在序列**真的有过缺口**时才成立：把它写死，
    # 回放到停发发生之前的月份就会印出一段假历史（连续段 == 全部观测时无缺口可言）。
    #  「本月未披露」与「本月有读数但连续段还排不出名次」是两回事，必须分开判：
    #  合成一个 `len(seg) >= 3 and 末月对得上` 的守卫，会让序列开头只有一两个观测的月份
    #  落到 else，印出「南向本月未披露」——而那些月份南向明明发了数。
    ser = d['southbound_adt_hkdbn'].dropna()
    seg = tail_contiguous(d['southbound_adt_hkdbn'])
    gapped = len(seg) < len(ser)
    have = bool(len(ser)) and str(ser.index[-1]) == M[i]
    if have and len(seg) >= 3:
        rk = B.rank_of(seg.values, len(seg) - 1)
        if gapped:
            idx = list(ser.index)
            # 缺口长度与「凑满 36 个观测要回溯到哪个月」都当场算。不写「跨 N 年」：
            # 地板除会低估跨度，且与 Exhibit 1 表注的「最近 36 个观测」并列会互相打架。
            hole = max((idx[j] - idx[j - 1]).n - 1 for j in range(1, len(idx)))
            why = (f'36个观测要回溯到{idx[-36]}、非三年窗口' if len(idx) >= 36
                   else f'全部只有{len(idx)}个观测、凑不满三年窗口')
            s3 = (f'南向名次只算恢复披露后的{len(seg)}个连续月（第{rk}）：'
                  f'停发{hole}个月，{why}，3Y 分位留空。')
        else:
            s3 = f'南向在{len(ser)}个已披露月里排第{rk}，逐月连续、无缺口。'
    elif have:
        s3 = f'南向本月有读数，但只有{len(ser)}个已披露月，排不出名次，3Y 分位一并留空。'
    else:
        s3 = '南向本月未披露，它与占比两行留空' + (
            '：该序列整段停发过，缺口一律断开不连线，也不给 3Y 分位。' if gapped else '，缺口不连线。')

    # ── 口径错位：汇总表锁在核心量齐备的月份，另有几列已多披露一个月。
    #    只数**公司披露的原始列**（load() 的 need），不数 df 上派生出来的 deriv_adv_k /
    #    velocity / implied_* —— 派生列跟着原始列一起有值，会把「三列」数成「四列」。
    #    **两级判断**：先判「有没有错位」，再判「IPO 是不是那条领先的列」。合成一个守卫
    #    会在「IPO 不领先但别的列领先」时落到 else，印出与事实相反的「各列截止月一致」——
    #    HKEX 本来就是分列到货，这一句正是全页唯一在讲口径错位的句子。
    DISCLOSED = ('adt_hkdbn', 'mktcap_hkdtn', 'new_listings', 'ipo_funds_hkdbn',
                 'derivatives_adv_contracts', 'southbound_adt_hkdbn')
    CN_COL = {'adt_hkdbn': '现货ADT', 'mktcap_hkdtn': '市值', 'new_listings': '新股数',
              'ipo_funds_hkdbn': 'IPO', 'derivatives_adv_contracts': '衍生品',
              'southbound_adt_hkdbn': '南向'}
    lead = [c for c in DISCLOSED if df[c].loc[LATEST + 1:].notna().any()]
    if not lead or NEWEST <= LATEST:
        s4 = f'本月各列截止月一致（同为{M[i]}），抬头、汇总表与各图口径没有错位。'
    else:
        ahead = B.cn(max((df[c].dropna().index[-1] - LATEST).n for c in lead))
        s4 = (f'汇总表锁在核心量齐备的{M[i]}，'
              f'{"、".join(CN_COL[c] for c in lead)}多披露{ahead}个月')
        ipo = df['ipo_funds_hkdbn'].dropna()
        if 'ipo_funds_hkdbn' in lead and len(ipo) and str(ipo.index[-1]) == str(NEWEST):
            rk = B.rank_of(ipo.values, len(ipo) - 1)
            extra = (f'为{len(ipo)}个已披露月最高' if rk == 1 else
                     f'排{len(ipo)}个已披露月的第{rk}')
            s4 += f'——{NEWEST} 募资{extra}，Exhibit 1 看不到。'
        else:
            s4 += '，Exhibit 1 看不到。'

    # ── 下界护栏。上面每一句都可能因为「这个月没有这件事」而整句不写（缺值月、序列开头
    #    不足 12 个月、各列没有错位的月份），历史重放里最短的月份只剩一百多字，会撞上
    #    render 的下界、整页构建失败 —— 那正是 B.need 要避免的失效模式，只不过发生在
    #    整段的层面。补进去的不是注水，是**永远成立且读者确实需要的口径说明**：
    #    数据密的月份被结论句挤掉，数据稀的月份正好有位置放。顺序按重要性，够了就停。
    #    阈值是**含标题**的去标签字数（`_plain_len` 比 render 看到的多 7 个字），所以 245
    #    对应 render 的 238，比 230 的下界留 8 个字余量。原来写的 260 太高：历史重放里
    #    58/91 个月本来五句就够长，却因为差几个字被塞进第六句，撞上「最多五句」那条分寸。
    #    余量不能再压——每条 fill 有 40 字上下，补一条就跳一大截，宁可留 8 个字空转。
    FILL_UNTIL = 245
    fill = []
    if n < 36:
        fill.append(f'注意样本只有{n}个月：上面的排名与「{n}个月新高」参照的就是这{n}个月，'
                    f'不是长历史口径。')
    fill += [
        f'{VEL_LAB}是推导值：ADT×252÷市值，252 为惯例年化交易日数、不是当年实际交易日。',
        'ADT 与衍生品ADV 公司披露的就是日均值，本页不再按交易日折算，再折一次是假修正。',
        '市值取月末时点而 ADT 是全月日均，两者不同期，换手率只能当代理读。',
    ]
    out = [s1, s2, s3, s4]
    for note in fill:
        if _plain_len(out) >= FILL_UNTIL:
            break
        out.append(note)
    return B.render([_liang(s) for s in out])


def main():
    df = load()

    # ── 序列完整性体检：中间缺月必须响，不能静默降级 ──
    # 近期图的窗口一律由 tail_contiguous 取「末尾逐月连续段」。这个函数是为南向通
    # 2022-01~2025-06 那 40 个月的**真实停发**设计的（Exhibit 5 的图注专门讲它，
    # 缺口不用直线连 —— CONTRACT 规矩 3），所以对南向的空洞必须保留原行为。
    # 但对逐月必发的列，中间少一个月会让「末尾连续段」只剩最后 1 个点：25 点窗口塌成
    # 1 点、y/y 与 m/m 全变「—」、Exhibit 3 还会写出字面 NaN，而退出码仍是 0，
    # 页面照常发布且肉眼看不出 —— 正是 CONTRACT 规矩 5 要禁的「静默写 NaN 上线」。
    # 尾部半行（当前 2026-07 只有衍生品/IPO/南向）不受影响：那是各列自己的末月之后，
    # 不构成中间空洞，也是 fetch/hkex.py 声明的正常状态。
    GAPPY_OK = {'southbound_adt_hkdbn'}          # 唯一允许中间空洞的列，见上
    for c in [x for x in df.columns if x not in GAPPY_OK]:
        s = df[c].dropna()
        if len(s) < 2:
            continue
        holes = [str(p) for p in
                 pd.period_range(s.index[0], s.index[-1], freq='M').difference(s.index)]
        if holes:
            raise SystemExit(
                f'series/hkex.csv 的 {c} 在 {s.index[0]}~{s.index[-1]} 之间缺 {len(holes)} 个月：'
                f'{holes[:6]}{" …" if len(holes) > 6 else ""}。近期图窗口取末尾逐月连续段，'
                f'中间缺月会把 25 点窗口砍成 1 点并写出 NaN，请先补齐 series/hkex.csv 再重建')

    # 汇总表用「核心量指标已齐备」的最后一个月；衍生品 / IPO / 南向更新更快，图上保留最新月
    CORE = df['adt_hkdbn'].dropna()
    LATEST = CORE.index[-1]
    NEWEST = df.index[-1]
    dfc = df.loc[:LATEST].copy()

    for d in (df, dfc):
        d['deriv_adv_k'] = d['derivatives_adv_contracts'] / 1000.0
        d['sb_share'] = d['southbound_adt_hkdbn'] / d['adt_hkdbn'] * 100
        # 换手率代理：年化成交额 / 市值
        d['velocity'] = d['adt_hkdbn'] * 252 / (d['mktcap_hkdtn'] * 1000) * 100

    # ── 量→收入桥：现货交易费 = 成交额 x 有效交易费率（双边）──
    tf_eff = rate_series('trading_fee_effective_rate_both_sides')      # 由收入倒算
    tf_list = rate_series('trading_fee_listed_rate_per_side', 2.0)     # 挂牌费率，双边
    td = rate_series('trading_days')
    tf_m = to_monthly(tf_list, df.index)
    td_q = to_monthly(td, df.index)
    df['implied_tradefee_hkdbn'] = df['adt_hkdbn'] * (td_q / 3.0) * tf_m / 100.0
    BR_NOTE = ('Assumption: monthly cash trading-fee revenue = ADT x trading days x the statutory '
               'both-sides trading-fee rate published in the HKEX fee schedule (0.00565% per side). '
               'That rate is independent of reported revenue, so the bridge check below is a real test, '
               'not an identity.')

    cf = rate_series('clearing_fee_effective_rate_both_sides')
    cf_m = to_monthly(cf, df.index)
    df['implied_clearfee_hkdbn'] = df['adt_hkdbn'] * (td_q / 3.0) * cf_m / 100.0
    CLR_NOTE = ('Assumption: monthly clearing-fee revenue = ADT x trading days x the effective '
                f'both-sides clearing rate ({cf.index[-1]} = {cf.iloc[-1]:.5f}%, held flat after). '
                'Unlike the trading fee, this rate is back-solved from revenue, so it is a now-cast '
                'rather than a test.')

    imp_all = df['implied_tradefee_hkdbn'].dropna()
    cnt = pd.Series(1, index=imp_all.index).groupby(
        pd.PeriodIndex(imp_all.index).asfreq('Q')).sum()
    ok_q = list(cnt[cnt == 3].index)
    imp_q = imp_all.groupby(pd.PeriodIndex(imp_all.index).asfreq('Q')).sum()
    imp_q = imp_q.loc[[q for q in imp_q.index if q in ok_q]]
    act_q = rate_series('cash_seg_trading_fee_revenue', 1e-3)          # HKD_mn → HKD_bn

    ex = []

    # ══════════ Exhibit 2：ADT 水平柱（gsx.lvl_bar, win=25, show_mom=True）══════════
    adt_c = tail_contiguous(df['adt_hkdbn'])
    adt = adt_c.iloc[-25:]
    XL_ADT = [mlab(p) for p in adt.index]
    adt_v = adt.values
    ex.append({
        'n': 2, 'kind': 'gs_bar', 'fmt': 'f0', 'xlabels': XL_ADT,
        'title': 'Average daily turnover',
        'ylab': 'HK$bn / day', 'ylab2': '% y/y', 'legend': 'Monthly ADT',
        'values': L(adt_v), 'yoy': yoy_rhs(adt_c),
        'note': f'次轴金色折线是同比（与原 deck 的 lvl_bar 一致 —— 该位置画的就是 y/y，'
                f'不是滚动均线：均线只是把柱子再平滑一遍、不带新信息）。'
                f'{mlab(adt.index[-1])} 的 ADT 为 HK${adt_v[-1]:,.1f}bn/日，'
                f'm/m {pctf(mom(adt_v), 1)}、y/y {pctf(yoy(adt_v), 1)}。',
    })

    # ══════════ Exhibit 3：ADT m/m 变化率（gsx.chg_line, win=25, kind='mom'）══════════
    full_adt = tail_contiguous(df['adt_hkdbn'])
    mm = full_adt.pct_change() * 100
    mm = mm.iloc[-25:]
    ex.append({
        'n': 3, 'kind': 'gs_line', 'fmt': 'pct1', 'xlabels': [mlab(p) for p in mm.index],
        'title': 'ADT, m/m change',
        'ylab': '% m/m', 'values': L(mm.values),
        'note': '与 Exhibit 2 同一序列的环比。ADT 的月度波动本身就是这门生意的收入波动，'
                '所以水平值与变化率成对看。',
    })

    # ══════════ Exhibit 4：ADT 超长历史（gsx.long_line, circle=3）══════════
    adt_long = df['adt_hkdbn'].dropna()
    XL_LONG = [mlab(p) for p in adt_long.index]
    last3 = ' / '.join(f'{mlab(p)} {v:,.0f}' for p, v in adt_long.iloc[-3:].items())
    ex.append({
        # zero_base：deck 的 long_line 是 set_ylim(0, max*1.16) 的零基线面积图。不给它时
        # 引擎走 y0 = min − 极差×5%，那是一次没有任何标注的隐性截轴，长历史图上会把
        # 振幅凭空放大（Ex15 实测放大约 3 倍）。full：90 个点塞进半栏每点不到 3px。
        'n': 4, 'kind': 'lines', 'fmt': 'f0', 'xlabels': XL_LONG, 'xstep': 6,
        'zero_base': True, 'end_label': True, 'full': True,
        'title': 'Full ADT history since 2019',
        'ylab': 'HK$bn / day',
        'series': [{'name': 'Average daily turnover', 'color': 'NAVY', 'values': L(adt_long.values)}],
        'note': f'Full disclosed history（{XL_LONG[0]} → {XL_LONG[-1]}，{len(adt_long)} 个月）。'
                f'纵轴从 0 起（同原 deck），末点标出数值。原 deck 另在末 3 个月打红圈标记，'
                f'网页 lines 图型没有该标记，最新 3 个月为 {last3}（HK$bn/日）。',
    })

    # ══════════ Exhibit 5：整体 vs 南向（gsx.multi_line, win=25）══════════
    # 窗口就是 deck 的 df.iloc[-25:]，两条线各画各的可用月份，缺口留 null 由引擎断笔
    # （CONTRACT 规矩 3：不可比的相邻期不能连成一条线）。
    # 原先这里取「两条同时有值的连续末段」，代价是把整体 ADT 这条**没有缺口**的线
    # 从 25 个月砍到 12 个月，还丢掉了南向最新的一个月（南向比现货多披露一个月）——
    # 为了迁就另一条序列的空洞去删自己有的数据，那是把缺口的成本转嫁给了完整序列。
    # 之所以从 lines_endlabels 换成 lines：前者无条件取 values[0] / values[-1] 做端点标签，
    # 序列里有 null 就会标出一个 NaN；后者的 end_label 走「最后一个有限点」。
    sb_win = df.iloc[-25:]
    sb_av = sb_win['southbound_adt_hkdbn'].dropna()
    # 图注里凡是引用南向具体读数的句子，都要在「窗口里一个南向观测都没有」时整段消失，
    # 而不是抛 IndexError —— 南向停发过 40 个月，再停一次这一页不能就此停更
    # （build/lpla.py 的断点硬失败正是这类失效的样板）。
    if len(sb_av):
        sb0, sb0_adt = float(sb_av.iloc[0]), float(df['adt_hkdbn'].get(sb_av.index[0], np.nan))
        SB_TXT = (
            f'南向自 {mlab(sb_av.index[0])} 才恢复披露，此前各月留空、线在缺口处断开，不用直线连；'
            f'整体 ADT 则到 {mlab(LATEST)} 为止（南向与衍生品比现货多披露一个月）。'
            + (f'南向占整体 ADT 的比例从 {sb0 / sb0_adt * 100:.1f}%（{mlab(sb_av.index[0])}）'
               f'变为 {df["sb_share"].get(LATEST):.1f}%（{mlab(LATEST)}）；'
               if np.isfinite(sb0_adt) and sb0_adt and np.isfinite(df['sb_share'].get(LATEST, np.nan))
               else '')
            + f'南向 {mlab(sb_av.index[-1])} 的最新读数为 HK${sb_av.iloc[-1]:,.1f}bn/日。')
    else:
        SB_TXT = '本窗口内南向成交额一个月都未披露，图上只有整体 ADT 一条线。'
    ex.append({
        'n': 5, 'kind': 'lines', 'fmt': 'f0', 'markers': True, 'end_label': True,
        'xlabels': [mlab(p) for p in sb_win.index], 'xstep': 2,
        'title': 'Total vs. southbound turnover',
        'ylab': 'HK$bn / day',
        'series': [
            {'name': 'Total market ADT', 'color': 'NAVY', 'values': LN(sb_win['adt_hkdbn'].values)},
            {'name': 'Southbound ADT', 'color': 'MBLUE',
             'values': LN(sb_win['southbound_adt_hkdbn'].values)},
        ],
        'note': 'Southbound carries a lower fee take, so mix matters to revenue. Its 40-month '
                'publication gap (2022-2024) is why it is shown here and not as a bar chart。'
                f'窗口 {mlab(sb_win.index[0])} → {mlab(sb_win.index[-1])}（同原 deck 的 25 个月）：'
                + SB_TXT + '两条线只标末点数值（原 deck 首末两端都标）。',
    })

    # ══════════ Exhibit 6：衍生品 ADV（gsx.lvl_bar, win=25）══════════
    dv_c = tail_contiguous(df['deriv_adv_k'])
    dv = dv_c.iloc[-25:]
    dv_v = dv.values
    ex.append({
        # fmt 由 f0 改回 f0c，与 Ex14 / Ex18 / 核对表统一（同一个数原先在三张图里两种写法）。
        # 原注释的理由「逗号会让相邻标签黏成一团」已经不成立：引擎按实测 bbox 抽稀标签，
        # 实测 1280px 屏上 f0 与 f0c 都是 25 抽 13、更宽的屏上两者都是 25 个全留 ——
        # 逗号一个标签都没多抽掉，那就没有理由为它牺牲一致性。
        'n': 6, 'kind': 'gs_bar', 'fmt': 'f0c', 'xlabels': [mlab(p) for p in dv.index],
        'title': 'Derivatives average daily volume',
        'ylab': 'k contracts / day', 'ylab2': '% y/y', 'legend': 'Monthly derivatives ADV',
        'values': L(dv_v), 'yoy': yoy_rhs(dv_c),
        'note': f'期货与期权合计，公司披露的原始单位是张数，此处除以 1,000 显示为「千张/日」'
                f'（核对表里给原始张数）。{mlab(dv.index[-1])} 的 ADV 为 {dv_v[-1]:,.0f} 千张/日，'
                f'y/y {pctf(yoy(dv_v), 1)}（次轴金色折线，同原 deck）。衍生品比现货多披露一个月。',
    })

    # ══════════ Exhibit 7：季度 ADT（gsx.qtr_bar, win=14, how='mean'）══════════
    qs = df['adt_hkdbn'].dropna()
    qg = qs.groupby(pd.PeriodIndex(qs.index).asfreq('Q'))
    qmean = qg.mean()
    qcnt = qg.count()
    n_in_last = int(qcnt.iloc[-1])
    qv = qmean.values
    qyoy = np.array([(qv[i] / qv[i - 4] - 1) * 100 if i >= 4 and qv[i - 4] else np.nan
                     for i in range(len(qv))])
    qw = qmean.iloc[-14:]
    qy = qyoy[-14:]
    ex.append({
        'n': 7, 'kind': 'qtr_bar', 'fmt': 'f0', 'label_fmt': 'f0',
        'xlabels': [str(p) for p in qw.index],
        'title': 'ADT by quarter',
        'ylab': 'HK$bn / day', 'legend': 'Complete quarter',
        'values': L(qw.values), 'partial_months': n_in_last, 'qtr_months': 3,
        'line': {'name': 'y/y (RHS)', 'color': 'GREEN', 'values': LN(qy), 'yfmt': 'pct0'},
        'note': '季度值是该季各月 ADT 的<b>简单平均</b>（每日成交额的季度均值），不是季度合计 —— '
                'ADT 本身已经是「每日」口径，合计会随季内交易日数变化而失真。'
                f'最新季 {qw.index[-1]} 已含 {n_in_last} 个月'
                + ('（完整季）。' if n_in_last >= 3 else '，未满季与完整季不可比，右轴 y/y 已作废。'),
    })

    # ══════════ Exhibit 8：市值（gsx.lvl_bar, win=25, show_mom=True）══════════
    mc_c = tail_contiguous(df['mktcap_hkdtn'])
    mc = mc_c.iloc[-25:]
    mc_v = mc.values
    ex.append({
        'n': 8, 'kind': 'gs_bar', 'fmt': 'f1', 'xlabels': [mlab(p) for p in mc.index],
        'title': 'Securities market capitalisation',
        'ylab': 'HK$tn', 'ylab2': '% y/y', 'legend': 'Month-end market cap',
        'values': L(mc_v), 'yoy': yoy_rhs(mc_c),
        'note': f'期末口径。{mlab(mc.index[-1])} 为 HK${mc_v[-1]:,.1f}tn，'
                f'm/m {pctf(mom(mc_v), 1)}、y/y {pctf(yoy(mc_v), 1)}（次轴金色折线）。'
                '它是 Exhibit 9 换手率的分母：成交额与市值的差额正是换手率在动。',
    })

    # ══════════ Exhibit 9：隐含换手率（gsx.lvl_bar, pct_series=True）══════════
    vel_c = tail_contiguous(df['velocity'])
    vel = vel_c.iloc[-25:]
    vel_v = vel.values
    vel_pp = vel_v[-1] - vel_v[-13] if len(vel_v) >= 13 else np.nan
    ex.append({
        # 比率序列：次轴同比走**百分点差**（同 gsx.lvl_bar 的 pct_series=True），
        # 不是「百分比的百分比变化」
        'n': 9, 'kind': 'gs_bar', 'fmt': 'f0', 'xlabels': [mlab(p) for p in vel.index],
        'title': 'Implied market velocity',
        'ylab': '% of market cap, annualised', 'ylab2': 'pp y/y',
        'legend': 'Implied velocity (%)',
        'values': L(vel_v), 'yoy': yoy_rhs(vel_c, pct_series=True),
        'note': 'ADT x 252 / market cap — the ratio GS uses to judge whether turnover is '
                'structurally higher。<b>推导值，非公司披露</b>：252 是惯例年化交易日数，'
                '不是当年实际交易日数；分母用当月期末市值。比率序列的同比用百分点差，'
                f'{mlab(vel.index[-1])} 为 {vel_v[-1]:,.1f}%，y/y {ppf(vel_pp, 1)}。',
    })

    # ══════════ Exhibit 10：隐含现货交易费收入（gsx.lvl_bar, dec=2）══════════
    # 单位由 HK$bn 改为 HK$mn（= 公司分部收入的披露单位），f0c 比原 deck 的「HK$bn 两位
    # 小数」多一位有效数字，是等价换算不是精度取舍。（引擎的 FMT 现已补上 f2/f3，
    # 原先「格式器最多一位小数」的理由已经过时，但换算本身仍照 mn 走 —— 那是披露单位。）
    tfee_c = tail_contiguous(df['implied_tradefee_hkdbn']) * 1000.0
    tfee = tfee_c.iloc[-25:]
    tfee_v = tfee.values
    y10 = yoy_rhs(tfee_c)

    def first_yoy_month(index, y):
        """次轴同比第一个有值的月份 —— 图注要说清楚折线为什么不是从最左边起画。"""
        k = next((i for i, v in enumerate(y['values']) if v is not None), None)
        return mlab(index[k]) if k is not None else None

    ex.append({
        'n': 10, 'kind': 'gs_bar', 'fmt': 'f0c', 'xlabels': [mlab(p) for p in tfee.index],
        'title': 'Implied cash trading-fee revenue',
        'ylab': 'HK$mn / month', 'ylab2': '% y/y', 'legend': 'Implied trading fee',
        'values': L(tfee_v), 'yoy': y10,
        'note': BR_NOTE + f' 费率与交易日数只有 {tf_list.index[0]} 起 {len(tf_list)} 个季度，'
                          f'故整条隐含序列自 {mlab(tfee_c.index[0])} 起（图上按惯例只画最近 '
                          f'{len(tfee)} 个月，即 {mlab(tfee.index[0])} 之后）；'
                          f'次轴同比要等序列满 12 个月，因此从 {first_yoy_month(tfee.index, y10)} 才有点。'
                          '季内各月同费率，最新季之后沿用。'
                          '月度交易日数按「季度交易日数 ÷ 3」摊，不是当月实际交易日数。'
                          '单位用 HK$mn（公司分部收入的披露单位），原 deck 是 HK$bn 保留两位小数，'
                          '两者等价。次轴金色折线是同比（同原 deck 的 lvl_bar）。 '
                + vintage_monthly([tf_list, td], tfee_c.index[-1],
                                  '法定挂牌交易费率与季度交易日数'),
    })

    # ══════════ Exhibit 11：桥的检验（gsx.implied_vs_actual）══════════
    qidx = [q for q in imp_q.index if q in act_q.index][-14:]
    imp = np.array([imp_q[q] for q in qidx], float) * 1000.0     # HK$bn → HK$mn（披露单位）
    act = np.array([act_q[q] for q in qidx], float) * 1000.0
    err = np.where(act != 0, (imp / act - 1) * 100, np.nan)
    mae = float(np.nanmean(np.abs(err)))
    ex.append({
        'n': 11, 'kind': 'grouped_bars', 'fmt': 'f0c',
        'xlabels': [str(q) for q in qidx],
        'title': 'Bridge check: statutory rate vs. reported fees',
        'ylab': 'HK$mn / quarter', 'ylab2': 'Error (%)', 'bar_labels': False,
        'groups': [
            {'name': 'Implied by the bridge', 'color': 'BLUE', 'values': L(imp)},
            {'name': 'Actually reported', 'color': 'NAVY', 'values': L(act)},
        ],
        'line': {'name': 'Error (RHS)', 'color': 'RED', 'values': L(err), 'yfmt': 'pct1'},
        'note': 'The implied bar applies the published statutory rate to all turnover; the reported '
                'bar is the actual cash-segment trading-fee line. The gap is fee-exempt turnover '
                '(market makers, certain ETF and structured-product flow).'
                f'  Mean absolute error over the window: {mae:.1f}%.'
                f' 误差始终为正、区间 {np.nanmin(err):+.1f}% ~ {np.nanmax(err):+.1f}%，'
                '说明免费成交占比稳定 —— 这条误差线一旦变窄或变宽，就是 mix 在动。'
                f'只有 {len(qidx)} 个季度可比，因为公司分部收入拆分只回溯到 {qidx[0]}。 '
                + vintage_quarterly(qidx[-1], LATEST, '法定费率、交易日数与现货分部交易费收入'),
    })

    # ══════════ Exhibit 12：有效费率 vs 法定费率（gsx.multi_line, dec=4）══════════
    # 原 deck 用「% of turnover」保留 4 位小数。改成「每成交 HK$1m 收多少费」，乘 1e4 后
    # f1 恰好等价于原来的 4 位小数，而且单位本身就有意义（读者能直接读出每百万成交收几块）。
    # （当初选它是因为引擎的 FMT 只到一位小数，如今 f2/f3/pct2 都已补上；换算是恒等的，
    #  没有精度损失，所以保留 —— 但理由已经不是「格式器不支持」了。）
    rq = [q for q in tf_eff.index if q in tf_list.index]
    XL_RATE = [mlab(q.asfreq('M', 'end')) for q in rq]
    eff_r = np.array([tf_eff[q] for q in rq], float) * 1e4
    lst_r = np.array([tf_list[q] for q in rq], float) * 1e4
    ex.append({
        'n': 12, 'kind': 'lines_endlabels', 'fmt': 'f1', 'xlabels': XL_RATE,
        'title': 'Fee capture: effective vs. statutory rate',
        'ylab': 'HK$ of trading fee per HK$1m traded',
        'series': [
            {'name': 'Effective (revenue / turnover)', 'color': 'NAVY', 'values': L(eff_r)},
            {'name': 'Statutory schedule rate', 'color': 'GRAY', 'values': L(lst_r)},
        ],
        'note': 'The persistent shortfall is the share of turnover that pays no trading fee. '
                'Watching this ratio is how you catch a mix shift before it shows up in revenue。'
                '单位由原 deck 的「% of turnover（4 位小数）」改为「每成交 HK$1m 的交易费」'
                f'（× 10,000，等价换算）：法定 HK${lst_r[-1]:,.1f} 恒定，'
                f'实收 HK${eff_r[-1]:,.1f}，捕获率 {eff_r[-1] / lst_r[-1] * 100:.1f}%。'
                'x 轴标的是各季末月份。 '
                + vintage_quarterly(rq[-1], LATEST, '有效费率（由收入倒算）与法定挂牌费率'),
    })

    # ══════════ Exhibit 13：隐含现货清算费收入（gsx.lvl_bar, dec=2）══════════
    cfee_c = tail_contiguous(df['implied_clearfee_hkdbn']) * 1000.0            # → HK$mn
    cfee = cfee_c.iloc[-25:]
    cfee_v = cfee.values
    y13 = yoy_rhs(cfee_c)
    ex.append({
        'n': 13, 'kind': 'gs_bar', 'fmt': 'f0c', 'xlabels': [mlab(p) for p in cfee.index],
        'title': 'Implied cash clearing-fee revenue',
        'ylab': 'HK$mn / month', 'ylab2': '% y/y', 'legend': 'Implied clearing fee',
        'values': L(cfee_v), 'yoy': y13,
        'note': CLR_NOTE + ' 清算费有最低/最高收费与 CCASS 结算费等分项，倒算出的有效费率把这些'
                           '一并吸收进去了，所以它随 mix 漂移，不能当法定费率读。'
                           f'次轴金色折线是同比（同原 deck 的 lvl_bar），自 '
                           f'{first_yoy_month(cfee.index, y13)} 起才有 —— 序列要满 12 个月。 '
                + vintage_monthly([cf, td], cfee_c.index[-1],
                                  '由收入倒算的有效清算费率与季度交易日数'),
    })

    # ══════════ Exhibit 14：衍生品 ADV 超长历史（gsx.long_line）══════════
    dv_long = df['deriv_adv_k'].dropna()
    XL_DV = [mlab(p) for p in dv_long.index]
    dv3 = ' / '.join(f'{mlab(p)} {v:,.0f}' for p, v in dv_long.iloc[-3:].items())
    ex.append({
        'n': 14, 'kind': 'lines', 'fmt': 'f0c', 'xlabels': XL_DV, 'xstep': 6,
        'zero_base': True, 'end_label': True, 'full': True,
        'title': 'Derivatives ADV history since 2019',
        'ylab': 'k contracts / day',
        'series': [{'name': 'Derivatives ADV', 'color': 'NAVY', 'values': L(dv_long.values)}],
        'note': f'{XL_DV[0]} → {XL_DV[-1]}，{len(dv_long)} 个月，纵轴从 0 起（同原 deck）、'
                f'末点标出数值。原 deck 另在末 3 个月打红圈，网页 lines 图型没有该标记，'
                f'最新 3 个月为 {dv3}（千张/日）。',
    })

    # ══════════ Exhibit 15：市值超长历史（gsx.long_line）══════════
    mc_long = df['mktcap_hkdtn'].dropna()
    XL_MC = [mlab(p) for p in mc_long.index]
    mc3 = ' / '.join(f'{mlab(p)} {v:,.1f}' for p, v in mc_long.iloc[-3:].items())
    ex.append({
        # 这张图的图注要求「与 Exhibit 4 对照看」，两张图就必须同基线：不从 0 起的话
        # 市值的振幅会被放大约 3 倍（实测轴底 ≈30 而非 0），对照本身就被扭曲了。
        'n': 15, 'kind': 'lines', 'fmt': 'f1', 'xlabels': XL_MC, 'xstep': 6,
        'zero_base': True, 'end_label': True, 'full': True,
        'title': 'Market capitalisation since 2019',
        'ylab': 'HK$tn',
        'series': [{'name': 'Securities market cap', 'color': 'NAVY', 'values': L(mc_long.values)}],
        'note': f'{XL_MC[0]} → {XL_MC[-1]}，{len(mc_long)} 个月，期末口径，纵轴从 0 起、末点标出数值。'
                f'原 deck 另在末 3 个月打红圈，网页 lines 图型没有该标记，最新 3 个月为 {mc3}（HK$tn）。'
                '与 Exhibit 4 对照看（两张图都是零基线，振幅可直接比）：市值这一轮并没有跟着'
                '成交额同步扩张，换手率（Exhibit 9）才是差额。',
    })

    # ══════════ Exhibit 16：逐年 ADT 路径（gsx.year_lines, n_years=6, cumulative=False）══════════
    yrs = sorted({p.year for p in adt_long.index})[-6:]
    yseries = []
    for y in yrs:
        vals = [None] * 12
        for p, v in adt_long.items():
            if p.year == y:
                vals[p.month - 1] = round(float(v), 6)
        yseries.append({'name': str(y), 'values': vals})
    ex.append({
        'n': 16, 'kind': 'year_lines', 'fmt': 'f0', 'label_fmt': 'f0',
        'xlabels': ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug',
                    'Sep', 'Oct', 'Nov', 'Dec'],
        'title': 'ADT path by year',
        'ylab': 'HK$bn / day', 'series': yseries, 'highlight': len(yrs) - 1,
        'note': f'Red = current year。画的是每月 ADT 的水平值（原 deck cumulative=False），'
                f'不是年初至今累计。{yrs[-1]} 年只有 {sum(1 for v in yseries[-1]["values"] if v is not None)} '
                f'个月，后面留空。',
    })

    # ══════════ Exhibit 17：ADT 热力矩阵（gsx.heat_matrix, n_years=8）══════════
    def heat(s, n_years=8):
        ys = sorted({p.year for p in s.index})[-n_years:]
        M = [[None] * 12 for _ in ys]
        for p, v in s.items():
            if p.year in ys:
                M[ys.index(p.year)][p.month - 1] = round(float(v), 6)
        return [str(y) for y in ys], M

    rows17, M17 = heat(adt_long)
    ex.append({
        # full：8×12 的矩阵塞进半栏，每格连两位数都写不下（全站另外八个页面的
        # heat_matrix 一律通栏）
        'n': 17, 'kind': 'heat_matrix', 'full': True, 'fmt': 'f0',
        'title': 'Average daily turnover (HK$bn)',
        'rows': rows17, 'matrix': M17, 'legend': 'Average daily turnover (HK$bn)',
        'row_head': '年',
        'note': 'Green = heavier turnover。色标取全部有限值的 5/95 分位，一两个离群月不会把整表压平。',
    })

    rows18, M18 = heat(dv_long)
    ex.append({
        'n': 18, 'kind': 'heat_matrix', 'full': True, 'fmt': 'f0c',
        'title': 'Derivatives ADV (k contracts / day)',
        'rows': rows18, 'matrix': M18, 'legend': 'Derivatives ADV (k contracts / day)',
        'row_head': '年',
        'note': 'Green = heavier derivatives activity。同 Exhibit 17 的色标口径（5/95 分位）。'
                '与 Exhibit 17 对照：衍生品的季节性形状与现货并不完全同步。',
    })

    # ══════════ Exhibit 1：汇总表 ══════════
    cur, prv, yag = LATEST, LATEST - 1, LATEST - 12
    # (kind, 行标签, 列名, 小数位, 变化口径, 水平值是否带 %, 分位是否因本页口径留空)
    SUM = [
        ('group', 'Cash market drivers'),
        ('row', 'Average daily turnover (HK$bn)', 'adt_hkdbn', 1, 'ratio', False, None),
        # 南向两行：可用观测跨 2019-2021 与 2025-2026 两段，「最近 36 个观测」实际横跨
        # 六年多，那算出来的不是 3Y 分位，是一个被 40 个月断档拼起来的假窗口 —— 留空，
        # 理由写在表注里（这是本页自己的口径原因，与 pctile.py 的死列判据无关）
        ('row', 'Southbound ADT (HK$bn)', 'southbound_adt_hkdbn', 1, 'ratio', False, '断档'),
        ('row', 'Southbound share of ADT (%)', 'sb_share', 1, 'pp', True, '断档'),
        ('row', 'Implied market velocity (%)', 'velocity', 1, 'pp', True, None),
        ('group', 'Derivatives'),
        ('row', 'ADV of futures and options (k contracts)', 'deriv_adv_k', 0, 'ratio', False, None),
        ('group', 'Market size and primary market'),
        ('row', 'Securities market cap (HK$tn)', 'mktcap_hkdtn', 1, 'ratio', False, None),
        ('row', 'New listings in the month', 'new_listings', 0, 'abs', False, None),
        ('row', 'IPO funds raised (HK$bn)', 'ipo_funds_hkdbn', 1, 'ratio', False, None),
    ]

    def chg(a, b, mode):
        if not (np.isfinite(a) and np.isfinite(b)):
            return None
        if mode in ('pp', 'abs'):
            return float(a - b)
        if b == 0 or a * b < 0:
            return None
        return float(a / b - 1) * 100

    def chg_cell(v, mode, dec):
        if v is None:
            return {'v': ''}
        if mode == 'pp':
            # CONTRACT §2：比率差 abs(v) < 1 用 bp，否则用 pp
            txt = f'{v * 100:+.0f}bp' if abs(v) < 1 else f'{v:+.2f}pp'
        elif mode == 'abs':
            txt = f'{v:+,.{max(0, dec)}f}'
        else:
            txt = f'{v:+.1f}%'
        txt = nz(txt)                     # 四舍五入到零的「-0bp / -0.0%」一律写成零
        if txt.lstrip('+-') in ('0', '0.0', '0bp', '0.0pp', '0.0%', '0%'):
            return {'v': txt.lstrip('+-'), 'cls': ''}
        return {'v': txt, 'cls': 'pos' if v > 0 else ('neg' if v < 0 else '')}

    dead_rows, gappy_rows = [], []
    srows = []
    for item in SUM:
        if item[0] == 'group':
            srows.append({'kind': 'group', 'label': item[1]})
            continue
        _, lab, col, dec, mode, pct, gappy = item
        s = dfc[col].dropna()
        c = float(s.get(cur, np.nan)) if cur in s.index else np.nan
        p1 = float(s.get(prv, np.nan)) if prv in s.index else np.nan
        p12 = float(s.get(yag, np.nan)) if yag in s.index else np.nan
        # 分位一律走 build/pctile.py：判据是口径，口径只能有一处定义。
        # 各页各写各的，正是同一条序列在两页被判定相反的原因（见 build/pctile.py 的
        # 模块 docstring）。这里只保留本页自己的口径原因（南向断档）。
        if gappy or not np.isfinite(c) or not len(s) or s.index[-1] != cur:
            # 末月不是汇总表口径月时不算分位：那算的是另一个月的分位，表头却写着本月
            pv, cls = '', ''
            if gappy:
                gappy_rows.append(lab)
        else:
            pv, cls = pctile.cell([float(v) for v in s.values], -1)
            if not pv and pctile.why_blank([float(v) for v in s.values]):
                dead_rows.append((lab, pctile.why_blank([float(v) for v in s.values])))
        srows.append({'label': lab, 'cells': [
            {'v': num(c, dec, pct)}, {'v': num(p1, dec, pct)}, {'v': num(p12, dec, pct)},
            chg_cell(chg(c, p1, mode), mode, dec),
            chg_cell(chg(c, p12, mode), mode, dec),
            {'v': pv, 'cls': cls},
        ]})

    summary = {
        'title': f'HKEX monthly market highlights — {mlab(LATEST)}',
        'heads': [f'本月 {mlab(cur)}', f'上月 {mlab(prv)}', f'去年同月 {mlab(yag)}',
                  'm/m', 'y/y', '3Y %ile'],
        'sep': 3,
        'rows': srows,
        'note': 'Velocity is derived as ADT x 252 / market cap, not a disclosed figure. '
                'New-listing and IPO series have gaps in the published monthly summary. '
                '3Y %ile = 当月读数高于最近 36 个<b>已公布</b>观测里多少百分比的观测，'
                '由全站唯一的 <code>build/pctile.py</code> 算出（判据：回放近 24 个月，'
                '若 ≥70% 的月份钉在 0 或 100，这一列对该行没有区分度，留空）。'
                '比率类指标（南向占比、换手率）的差异一律用 pp／bp，不用百分比的百分比变化。'
                + (f'<b>{"、".join(gappy_rows)}</b> 的分位留空：南向 ADT 2022-01 起断档 40 个月，'
                   '「最近 36 个观测」实际横跨六年多，那不是 3Y 分位。' if gappy_rows else '')
                + (''.join(f'<b>{lab}</b> 的分位留空：{why}。' for lab, why in dead_rows))
                + '去年同月无披露时 y/y 留空。',
    }

    # ══════════ Exhibit 19：核对表（官方原始单位，不换算）══════════
    tail = df.iloc[-13:]
    trows = []
    for p, r in tail.iterrows():
        trows.append({
            'xl': mlab(p),
            'adt': None if not np.isfinite(r['adt_hkdbn']) else f"{r['adt_hkdbn']:,.3f}",
            'mcap': None if not np.isfinite(r['mktcap_hkdtn']) else f"{r['mktcap_hkdtn']:,.4f}",
            'sb': None if not np.isfinite(r['southbound_adt_hkdbn']) else f"{r['southbound_adt_hkdbn']:,.3f}",
            'dv': None if not np.isfinite(r['derivatives_adv_contracts']) else f"{r['derivatives_adv_contracts']:,.0f}",
            'nl': None if not np.isfinite(r['new_listings']) else f"{r['new_listings']:,.0f}",
            'ipo': None if not np.isfinite(r['ipo_funds_hkdbn']) else f"{r['ipo_funds_hkdbn']:,.3f}",
        })
    table = {
        'n': 19, 'title': '近 13 个月月度指标核对表（官方原始单位，未换算）',
        'idx': '月份',
        'cols': [['ADT (HK$bn)', 'adt'], ['Market cap (HK$tn)', 'mcap'],
                 ['Southbound ADT (HK$bn)', 'sb'],
                 ['Derivatives ADV (contracts)', 'dv'],
                 ['New listings', 'nl'], ['IPO funds (HK$bn)', 'ipo']],
        'rows': trows,
    }

    # ══════════ notes ══════════
    notes = [
        '<b>数据源</b>：HKEX 每月公布的 Monthly Market Highlights（月度市场概况）与季度业绩'
        '中的现货分部收入、费率与交易日数。版式沿用 Goldman Sachs GIR 两份 HKEX note'
        '（「New listings and profit growth inflection to drive sustainable ADT growth」'
        'Exhibit 1-15 与「Multiple tailwinds in 2026E despite weak Nov ADT」Exhibit 1-28）：'
        '三层时间窗（超长历史判周期位置 / 中长期判趋势 / 近 25 个月讲当下）、双图开场、驱动量置顶。',

        f'<b>⚠️ 各序列的截止月不一样</b>：现货 ADT、市值、新上市家数到 {mlab(LATEST)}；'
        f'衍生品 ADV、IPO 募资、南向 ADT 已有 {mlab(NEWEST)}。'
        '汇总表与页面顶部的「数据截至」一律取<b>核心量指标齐备的最后一个月</b>，'
        '各图则各自画到自己序列的最新月 —— 所以 Exhibit 5（南向那条线）/6/14/18 的末端'
        f'比 Exhibit 2/4/17 多一个月；Exhibit 5 里整体 ADT 那条线到 {mlab(LATEST)} 为止，'
        '末点比南向早一格，不是数据缺失。',

        '<b>⚠️ 南向 ADT 有 40 个月断档</b>：2022-01 至 2025-06 的月度概况未披露南向成交额，'
        '2025-07 起恢复。缺口不用直线连（不可比的相邻期不能画成连续序列）：'
        'Exhibit 5 画满 25 个月的窗口，南向在断档各月留空、线在缺口处断开，'
        '整体 ADT 那条没有缺口的线则一个月都不砍。汇总表里南向那一行的「去年同月」是空的，'
        '<b>3Y %ile</b> 也留空 —— 它的「最近 36 个观测」实际横跨六年多，那不是 3Y 分位。',

        '<b>换手率是推导值，不是披露值</b>：Implied market velocity = ADT × 252 ÷ 市值。'
        '252 是惯例年化交易日数（不是港股当年实际交易日数），分母用当月期末市值。'
        '它回答的是「这轮成交放大里有多少来自存量资产周转加快、而不是市值本身变大」。',

        '<b>量→收入桥的两条假设，性质不同</b>：'
        '（a）现货交易费用<b>法定挂牌费率</b>（每边 0.00565%，双边 0.0113%）× ADT × 交易日数 —— '
        '这个费率独立于已披露收入，所以 Exhibit 11 是一次<b>真检验</b>；'
        '（b）现货清算费用<b>由收入倒算</b>的有效费率，只能算 now-cast，不能当检验。'
        '两者标题都带 Implied。',

        f'<b>费率序列只有 {tf_list.index[0]} 起 {len(tf_list)} 个季度</b>：季内各月共用该季费率，'
        '最新季之后沿用最后一个已知值；月度交易日数按「季度交易日数 ÷ 3」摊，'
        f'不是当月实际交易日数。因此 Exhibit 10 / 13 的隐含收入序列自 {mlab(tfee_c.index[0])} 起，'
        f'早于此的月份不画（宁可短，不拿近似值糊）；这两张图与其余近期图一样只展示最近 '
        f'{len(tfee)} 个月，图上最左一格是 {mlab(tfee.index[0])}，不是序列起点。'
        + vintage_monthly([tf_list, td, cf], tfee_c.index[-1],
                          '本页全部隐含收入图的费率', scope='隐含收入序列')
        + '（这句与 Exhibit 10 / 11 / 12 / 13 的费率口径说明一样，都由 series/fee_rates.csv '
          '的最新季度现算，不写死季度号。）',

        f'<b>桥的误差是结构性的，不是估算误差</b>：Exhibit 11 显示按法定费率算出的交易费'
        f'系统性高于实际披露 {np.nanmin(err):+.1f}% ~ {np.nanmax(err):+.1f}%（窗口内平均绝对误差 {mae:.1f}%），'
        '差额是不付交易费的成交 —— 做市商、部分 ETF 与结构性产品流。'
        '这条误差线一旦变窄或变宽，就是成交结构在动，会先于收入体现出来。',

        '<b>网页版式与原 PDF 的已知差异</b>：'
        '（1）Exhibit 2 / 6 / 8 / 9 / 10 / 13 的次轴与原 deck 一致，画的是<b>金色 y/y 折线</b>'
        '（比率序列 Exhibit 9 走百分点差），不画 12 个月均线 —— 均线只是把柱子再平滑一遍、'
        '不带新信息，同比才回答「相对去年这个月是好是坏」；基数过小或异号的月份放弃同比、'
        '折线在那里断开；'
        '（2）Exhibit 10 / 11 / 13 的单位由原 deck 的 HK$bn（两位小数）改为 <b>HK$mn</b>'
        '（也正是公司分部收入的披露单位），Exhibit 12 由「% of turnover（4 位小数）」改为'
        '「每成交 HK$1m 收多少交易费」（× 10,000）—— 两处都是恒等换算，精度只增不减；'
        '（3）Exhibit 4 / 14 / 15 在原 deck 里给最新 3 个月打了红圈，网页 lines 图型没有该标记，'
        '这三个月的具体数值改写在各自图注里；这三张图的纵轴与原 deck 一样<b>从 0 起</b>，'
        '并标出末点数值；'
        '（4）Exhibit 5 只标末点数值，原 deck 首末两端都标。'
        '另：衍生品 ADV 的千分位写法此前在 Exhibit 6（「1731」）与 Exhibit 14 / 18 / 核对表'
        '（「1,731」）之间不一致，现已统一为「1,731」。',

        '<b>3Y %ile</b> = 当月读数高于最近 36 个已公布观测里多少百分比的观测，'
        '由全站唯一的 <code>build/pctile.py</code> 算出：把这一列在过去 24 个月里逐月回放，'
        '若 ≥70% 的月份都钉在 0 或 100，说明这一列对该行没有区分度，那一行留空'
        '（旧判据「差分非负的比例 ≥ 90%」测的是序列形状，拦不住「上下波动但分位常年钉 100」'
        '的行，已废弃）。本页另有一条自己的口径留空：南向两行的可用观测跨越 40 个月断档，'
        '窗口不是连续的三年。比率类指标的变化一律用 pp／bp（差额绝对值小于 1pp 时写 bp）。',

        '<b>核对表（Exhibit 19）保持官方原始单位</b>：衍生品 ADV 给原始张数（不是千张），'
        'ADT／南向／IPO 给 HK$bn、市值给 HK$tn，小数位与官方披露一致，可与 Monthly Market '
        'Highlights 原文逐格对齐。所有图表的数值都由这套原始序列在 Python 侧算好并格式化，'
        '页面不做任何计算。',
    ]

    # ── headline / hub_line：整行锁死在 LATEST，不许各取各的 [-1] ──
    # 这一行紧挨着抬头的「数据截至 {through_label}」，首页卡片上也已经有一个权威月份徽章，
    # 两处都没有逐指标标月份的位置 —— 所以整行必须与 data_through 同口径。
    # 取各序列自己的末值会串到 NEWEST（衍生品与南向比现货多披露一个月），
    # 于是同一页对同一指标给出两个互斥读数（衍生品 1,731 vs 1,926、南向 129.2 vs 130.0），
    # 与本页 Exhibit 1 和 /exchanges/ Exhibit 1 直接打架。
    # 领先一个月的读数不会丢：Exhibit 6 / 18 / 19 逐点带月份标签地展示它们。
    # 月份对不上时：**只有 ADT 硬失败**，其余指标那一段整段略过。
    # ADT 是 data_through 的定义者，它对不上说明管道自相矛盾，必须响。其余指标只是
    # 「本月还没披露」——南向就停发过 40 个月，若为此抛异常退出，那一天起这一页永久停更
    # （build/lpla.py 的断点硬失败正是这个失效模式）。略过的读数不会丢：汇总表那一行
    # 显示「—」，各图仍画到自己序列的最新月。
    def hv(col, name, required=False):
        """headline 用的序列：截到 LATEST 的末尾连续段，末月不是 LATEST 就返回 None。"""
        s = tail_contiguous(df[col].loc[:LATEST]).iloc[-25:]
        if not len(s) or s.index[-1] != LATEST:
            if required:
                raise SystemExit(f'headline 口径月错位：{name}({col}) 末月 = '
                                 f'{s.index[-1] if len(s) else "空序列"}，data_through = {LATEST}')
            return None
        return s.values

    h_adt = hv('adt_hkdbn', 'ADT', required=True)
    h_sb = hv('southbound_adt_hkdbn', '南向 ADT')
    h_dv = hv('deriv_adv_k', '衍生品 ADV')
    h_mc = hv('mktcap_hkdtn', '市值')
    h_vel = hv('velocity', '换手率')
    h_tfee = hv('implied_tradefee_hkdbn', '隐含现货交易费')
    if h_tfee is not None:
        h_tfee = h_tfee * 1000.0

    # 每个指标都带 y/y 与 m/m 两个方向：只写 y/y 的抬头会把一个环比大跌的月份读成纯正面
    # （本月市值 y/y 是正的、m/m 掉了 8%，只报 y/y 等于把它藏起来，读者得翻到汇总表才知道）。
    parts = [f'ADT HK${h_adt[-1]:,.1f}bn/日（{pctf(yoy(h_adt), 1)} y/y，{pctf(mom(h_adt), 1)} m/m）']
    if h_sb is not None:
        parts.append(f'南向 ADT HK${h_sb[-1]:,.1f}bn（{pctf(mom(h_sb), 1)} m/m）')
    if h_dv is not None:
        parts.append(f'衍生品 ADV {h_dv[-1]:,.0f} 千张/日'
                     f'（{pctf(yoy(h_dv), 1)} y/y，{pctf(mom(h_dv), 1)} m/m）')
    if h_mc is not None:
        parts.append(f'市值 HK${h_mc[-1]:,.1f}tn（{pctf(yoy(h_mc), 1)} y/y，{pctf(mom(h_mc), 1)} m/m）')
    if h_vel is not None and len(h_vel) > 1:
        parts.append(f'换手率 {h_vel[-1]:,.1f}%（{ppf(h_vel[-1] - h_vel[-2], 1)} m/m）')
    if h_tfee is not None:
        parts.append(f'隐含现货交易费 HK${h_tfee[-1]:,.0f}mn/月')
    headline = ' · '.join(parts)

    payload = {
        'ticker': TICKER,
        'tracker': 'HKEX Monthly Market Tracker',
        'title': f'Hong Kong Exchanges (0388.HK)：月度市场统计跟踪 — {LATEST.year} 年 {LATEST.month} 月',
        'data_through': str(LATEST),
        'through_label': f'{LATEST.year} 年 {LATEST.month} 月',
        'subtitle': f'数据源 HKEX Monthly Market Highlights + 季度业绩费率表 · '
                    f'覆盖 {mlab(adt_long.index[0])} → {mlab(NEWEST)}（核心量指标至 {mlab(LATEST)}）· '
                    f'版式沿用 Goldman Sachs GIR 的 HKEX exhibit 体例 · 仅图，无观点',
        'headline': headline,
        # headline 之下、Exhibit 1 之上的 ~300 字解读。职责与 headline 互补：
        # 那一行给读数，这一段给「读数该怎么读」。见 compose_brief 的 docstring。
        'brief': compose_brief(df, LATEST, NEWEST),
        'hub_line': f'ADT HK${h_adt[-1]:,.0f}bn/日（{pctf(yoy(h_adt))} y/y）'
                    + (f'· 衍生品 ADV {h_dv[-1]:,.0f}k 张/日' if h_dv is not None else ''),
        'source': SRC,
        'xlabels': XL_ADT,
        'xlabels_long': XL_LONG,
        'summary': summary,
        'exhibits': ex,
        'table': table,
        'notes': notes,
        'footer': '数据与算法源自本机 <code>monthly-op-dashboards</code> 项目 · '
                  '仅供个人研究，不构成投资建议 · 所有推导值均已在图注中标注 Implied 与假设',
    }

    # 抬头「官方发布于 …」：查的是 LATEST，不是 NEWEST —— 抬头另半句写的是「数据截至
    # {through_label}」，两句必须说同一个月，否则读者会把领先一个月的衍生品/南向那一档的
    # 发布日读成本页整页的发布日。查不到就**整个字段不写**：渲染端判的是字段在不在，
    # 给 None 或空串会印出「官方发布于 None」。
    src_date = repo.source_date(TICKER, str(LATEST))
    if src_date:
        payload['source_date'] = src_date

    # 兜底：json.dump 对 float('nan') 会写出**字面 NaN** —— 那不是合法 JSON，
    # 但 Python 的 json.loads 与浏览器的 window.DASH = 都照单全收，于是坏 payload
    # 能一路发布而不报错（CONTRACT 规矩 5）。缺值一律走 LN() 出 null，不能出 NaN。
    # 这里原本有一份本地的 scan_nonfinite，已并入 build/payload_guard.py 统一实现
    # （多一条：还扫已被 f-string 格式化进展示串的小写 nan，本地那版看不见）。
    path = os.path.join(ROOT, 'data', f'{TICKER}.js')
    payload_guard.write_dash(path, payload, TICKER)

    print(f'核心月 {LATEST} | 最新月 {NEWEST} | 长历史 {adt_long.index[0]} → {adt_long.index[-1]}'
          f'（{len(adt_long)} 个月）')
    print(f'Exhibit 1 汇总表 + Exhibit {ex[0]["n"]}-{ex[-1]["n"]}（{len(ex)} 张图）+ '
          f'Exhibit {table["n"]} 核对表')
    print(f'写出 {path}  ({os.path.getsize(path) / 1024:.1f} KB)')
    print(headline)


if __name__ == '__main__':
    main()
