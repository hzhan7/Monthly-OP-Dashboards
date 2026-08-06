# -*- coding: utf-8 -*-
"""LPL Financial (LPLA) 月度经营指标 —— 把 build/build_lpla.py 的 matplotlib deck
逐张移植成网页看板 payload，写出 data/lpla.js。

模版来源：Goldman Sachs (Alexander Blostein 团队)「LPL Financial Holdings (LPLA):
          April metrics…」的 Exhibit 1，以及同系列 11 月期。该表的三条口径规矩本站全部照搬：
   1) **流量类（NNA）不算环比/同比百分比**，改用「年化有机增长率」= 当月 NNA x 12 / 上月末资产；
   2) **比率类差异一律用 bp / pp**，不用百分比变化；
   3) 存量分两个业务口径（Advisory / Brokerage）+ Total + 占比行。
   另采用 GS「SCHW First Take」Exhibit 2 的恒等式滚存桥（期初 + 净新增 + 市值变动 = 期末）。
数据源：LPL Financial IR 月度经营指标新闻稿。季末月（3/6/9/12）无独立月报，取自当季季报。

⚠️ 并购导入：两笔整体并表会把 as-reported 序列打断 —— 2024 年 10 月 Atria（$88.3bn）与
   2025 年 8 月 Commonwealth Financial Network（$275.0bn）。两个月都不是有机流入，
   凡是画 as-reported 客户资产 / 现金 / NNA 的图都以红色竖虚线标出（见 ACQ_BREAKS）。

输入（只读，一律来自 series/）：
    series/lpla.csv       月度经营指标（2018-07 起）
    series/fee_rates.csv  季度费率与季度实际收入（company = LPLA）
输出：
    data/lpla.js          window.DASH = {...}

幂等：payload 里不写构建日期（只写首行注释），不使用随机数，窗口一律从数据最新月倒推。
"""
import datetime
import json
import math
import os

import numpy as np
import pandas as pd

import brief as B       # 顶部 brief 的规则库（R1-R6），只算事实、不出文字
import payload_guard
import pctile           # 汇总表 3Y %ile 的唯一实现，不在本文件里另写一套
import repo             # 仓库定位 + 发布日台账入口

D = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(D)
SERIES = os.path.join(ROOT, 'series')

SRC = ('Source: LPL Financial monthly activity and quarterly reports; '
       'format after Goldman Sachs GIR')
# $275bn 是公司披露值，不是估算：LPL 2025Q3 报告原文
# "This included $275 billion of acquired net new assets resulting from the acquisition
#  of Commonwealth" —— 曾经这里写过 ~$285bn（来自原 deck docstring 的约数），
# 而同一事件在 wealth 页又写成 $277.0bn，同一个数在站内出现三种写法。
QNOTE = ('Quarter-end months have no standalone monthly report; those values come from '
         'the quarterly release')

# 官方同页披露的 Acquired NNA（$bn）。2022 年起完整；更早年份原件用旧行名，未解析，故不调整。
# 逐条与 build/build_lpla.py 的 ACQ 表一致 —— 它不是 series/lpla.csv 的一列，
# 而是 deck 里登记的公司披露常量，移植时原样带过来（见 notes 第 4 条）。
ACQ = {'2023-01': 3.2, '2023-03': 0.5, '2024-04': 5.0, '2024-08': 0.3, '2024-09': 0.3,
       '2024-10': 88.3, '2024-11': 0.8, '2024-12': 0.3, '2025-01': 0.1, '2025-02': 0.7,
       '2025-03': 7.1, '2025-08': 275.0, '2025-12': 2.0}

# ── 结构性断点 ──────────────────────────────────────────────────────────────
# ACQ 里的两笔**整体并表**：Atria（2024-10，$88.3bn，约当月资产的 5%）与
# Commonwealth（2025-08，$275.0bn，约 14%）。凡是画 as-reported 客户资产 / 客户现金 /
# 总 NNA 的图都要把它们画出来（CONTRACT.md §5.2：口径断点必须画出来，不能靠图注提一句
# 就算数）。与 ACQ 挨着放是因为它们是同一件事的两种用法，改一处必须改另一处；
# build/wealth.py 的 ACQ_BREAKS 是同一张表的横截面页副本。
#
# 曾经这里只有 Commonwealth 一条，于是同一条 LPL as-reported 序列在本页被判成
# 「Oct-24 可比」、在 /wealth/ 被判成「Oct-24 不可比」，两页互相矛盾。
ACQ_BREAKS = [(pd.Period('2024-10', 'M'), 'Atria'),
              (pd.Period('2025-08', 'M'), 'Commonwealth')]
BRK_TXT = {'Atria': 'Oct-2024 Atria ($88.3bn)',
           'Commonwealth': 'Aug-2025 Commonwealth ($275.0bn)'}

WIN_L = 25          # gsx.lvl_bar / multi_line 在原 deck 里的窗口
WIN_S = 13          # gsx.stack_share / bridge_bar 的窗口
WIN_Q = 14          # gsx.qtr_bar / implied_vs_actual 的窗口（季度）

DRAWN = []          # 真正画出了断点线的 exhibit 编号，供 notes 现算文案用
CAPPED = []         # 真正截了轴的 (编号, 说明)，同理


def cap_pack(n, desc, vals, hi=None, lo=None, cap_note='axis capped — true values shown in red'):
    """只在窗口里**真的有点越界**时才截轴，返回可展开进 exhibit 的字段。

    与断点同一条道理：ycap 一给上，引擎就无条件把「axis capped」那行红字画出来。
    窗口往前滚、离群月掉出窗口之后，图上一个红圈都没有却还写着「已截轴」，
    就成了第二句假话。所以这里现算：没有越界点就不截、也不写那行字。
    """
    fin = [float(v) for v in vals if v is not None and np.isfinite(float(v))]
    over = [v for v in fin if (hi is not None and v > hi) or (lo is not None and v < lo)]
    if not over:
        return {}, ''
    CAPPED.append((n, desc))
    out = {'cap_note': cap_note}
    if hi is not None:
        out['ycap'] = hi
    if lo is not None:
        out['yfloor'] = lo
    return out, len(over)


def brk_pack(idx, n=None):
    """把结构性断点映射到某张图窗口里的 x 索引，返回 (exhibit 字段, 该图的断点图注)。

    窗口盖不到的断点自动省略，一条都盖不到时返回 ({}, '') —— 图上不画、图注也不会
    声称画了。**断点滚出窗口是常态而不是错误**：窗口每月往前滚，2025-08 迟早会掉出
    13 个月窗口。这里原先写的是「不在窗口里就 raise SystemExit」，那意味着 LPL 的
    2026-09 数据一入库整页就永久停更（monthly_run 每天 `lpla FAIL`、页面冻结在旧月）。
    build/schw.py 的 brk_idx() 与 build/wealth.py 的 brks() 早就是这个写法，本文件跟上。

    idx 可以是月度也可以是季度索引：断点按目标索引的频率折算（月度 2025-08 → 2025Q3）。
    """
    lst = list(idx)
    if not lst:
        return {}, ''
    fr = lst[0].freq
    at, lb, tx = [], [], []
    for p, lab in ACQ_BREAKS:
        q = p.asfreq(fr) if fr != p.freq else p
        if q in lst and lst.index(q) not in at:
            at.append(lst.index(q))
            lb.append(lab)
            tx.append(BRK_TXT[lab])
    if not at:
        return {}, ''
    if n is not None:
        DRAWN.append(n)
    note = ('Red dashed line' + ('s' if len(tx) > 1 else '') + ' = ' + ' and '.join(tx)
            + ' — whole-firm onboardings, not organic flow; readings to the left of each '
              'line are not directly comparable with those to the right')
    return {'break_at': at, 'break_label': lb}, note


# ────────────────────────────── 读数 ──────────────────────────────
def mlab(p):
    return p.strftime('%b-%y')


def source_day(month):
    """series/source_dates.csv 里 lpla 这个月的官方发布日；没有就返回 None。"""
    return repo.source_date('lpla', str(month))


def load():
    df = pd.read_csv(os.path.join(SERIES, 'lpla.csv'))
    df['month'] = pd.PeriodIndex(df['month'], freq='M')
    df = df.set_index('month').sort_index()
    for c in df.columns:
        df[c] = pd.to_numeric(df[c], errors='coerce')
    need = ['total_assets_usdbn', 'advisory_assets_usdbn', 'brokerage_assets_usdbn',
            'nna_total_usdbn', 'nna_advisory_usdbn', 'nna_brokerage_usdbn',
            'client_cash_usdbn']
    missing = [c for c in need if c not in df.columns]
    if missing:
        raise SystemExit(f'series/lpla.csv 缺列: {missing}')
    # 逐月连续性：断档会让「相隔数月的两点」被画成相邻柱（规矩 3）
    idx = list(df.index)
    for i in range(1, len(idx)):
        if (idx[i] - idx[i - 1]).n != 1:
            raise SystemExit(f'series/lpla.csv 月份不连续: {idx[i-1]} → {idx[i]}')
    return df


def rate_series(metric, to=None):
    """series/fee_rates.csv 里 LPLA 的季度序列，索引 PeriodIndex(freq='Q')。"""
    d = pd.read_csv(os.path.join(SERIES, 'fee_rates.csv'))
    d = d[(d['company'] == 'LPLA') & (d['metric'] == metric)].copy()
    if not len(d):
        raise SystemExit(f'fee_rates.csv 里没有 LPLA/{metric}')
    d['q'] = pd.PeriodIndex(d['period'].str.replace('-', '', regex=False), freq='Q')
    out = d.set_index('q')['value'].astype(float).sort_index()
    if to:
        units = set(d['unit'].dropna())
        if len(units) != 1:
            raise SystemExit(f'LPLA/{metric} 单位不唯一: {units}')
        scale = {('USD_k', 'mn'): 1e-3, ('USD_mn', 'mn'): 1.0, ('USD_bn', 'mn'): 1e3}
        u = units.pop()
        if (u, to) not in scale:
            raise SystemExit(f'LPLA/{metric} 单位 {u} 无法换算到 {to}')
        out = out * scale[(u, to)]
    return out


# ────────────────────────────── 格式化零件 ──────────────────────────────
def _nz(v, dec):
    """四舍五入到 dec 位后落在零上的值一律归正零 —— 否则 -0.04 会印成「-0.0」/「-0bp」，
    读者会当成一个（很小的）负数，而它其实是「按这个精度就是 0」。"""
    v = float(v)
    return 0.0 if round(v, dec) == 0 else v


def pm(v, dec=1, sfx=''):
    """带正负号的差异文本。四舍五入后为 0 时不带符号 —— 「+0.0%」和「-0bp」
    都会被读成一个方向明确的小变化，而它们其实是「按这个精度没变」。"""
    z = _nz(v, dec)
    sign = '' if z == 0 else ('+' if z > 0 else '-')
    return f'{sign}{abs(z):,.{dec}f}{sfx}'


def num(v, dec=1, money='', pct=False):
    if v is None or not np.isfinite(v):
        return '—'
    return f'{money}{_nz(v, dec):,.{dec}f}' + ('%' if pct else '')


def L(a):
    """序列 → JSON 数组，非有限值写 None（页面自动断开，不画假线）。"""
    return [None if (v is None or not np.isfinite(float(v)))
            else (round(float(v), 6) or 0.0) for v in a]


def yoy_txt(s, pct_series=False):
    """gs_bar 气泡里的 y/y 文案。比率序列用 pp（GS 规矩 2），水平值用百分比。"""
    a, b = float(s.iloc[-1]), float(s.iloc[-13])
    if not (np.isfinite(a) and np.isfinite(b)):
        return None
    if pct_series:
        return f'{_nz(a - b, 1):+.1f}pp y/y'
    if b == 0 or a * b < 0:
        return None
    return f'{_nz((a / b - 1) * 100, 0):+.0f}% y/y'


def yoy_series(s, idx, pct_series=False, lag=12):
    """次轴 y/y 折线的取值，逐行照搬 gsx.lvl_bar 的口径（build/gsx.py:279-289）：

      · 比率序列（pct_series）→ **百分点差**，不是「百分比的百分比变化」（GS 规矩 2）；
      · 水平值 → 百分比变化，但基数过小（|base| < 0.15 × 全序列 |值| 中位数）或
        与当期异号时放弃 —— 那种同比只是把一个接近零的分母放大成三位数噪音。

    口径判断一律在 Python 侧做完，引擎不替我们算（见 build/engine_kinds.md §8）。
    """
    s = s.dropna()
    v = s.values.astype(float)
    scale = float(np.nanmedian(np.abs(v))) or 1.0
    out = pd.Series(np.nan, index=s.index, dtype=float)
    for i in range(lag, len(v)):
        a, b = v[i], v[i - lag]
        if not (np.isfinite(a) and np.isfinite(b)):
            continue
        if pct_series:
            out.iloc[i] = a - b
        elif abs(b) < 0.15 * scale or a * b < 0:
            continue
        else:
            out.iloc[i] = (a / b - 1) * 100
    return out.reindex(idx)


def avg_prior12(s):
    """「Prior 12mo Avg.」= 最新月之前的 12 个月均值（不含最新月）。"""
    v = s.iloc[-13:-1].astype(float)
    if not np.isfinite(v.values).any():
        raise SystemExit('avg12 无有效值')
    return round(float(np.nanmean(v.values)), 6)


def compose_brief(months, tot, adv, bro, cash, cashp, og, nna_ex, nnaa, nnab):
    """LPLA 页顶部的 ~300 字数据总结（payload 的 `brief` 字段）。

    规则库在 `build/brief.py`（R1 峰值扫描 / R2 基数护栏 / R4 单位恒等 / R5 标注 /
    R6 有效位），那边只算事实，句子在这里拼 —— 措辞是口径的一部分，属于各家自己。
    每个数字都当场从序列算，**一处硬编码都没有**：新高月计数、名次、「N 个月最低」、
    峰值停在哪个月、并表后经过几个月，下月重跑全部自己变。

    ═══ 定性词一律由当场算出的量决定分支（写死措辞 + 算出来的数字 = bug）═══
    「只有 / 信息量低 / 内部搬家 / 被摊薄」这些词全部挂在 if 上，而不是预设方向：
      · 计数类的「只有 N 个」一律走 `B.quant()`，量词跟着数字走；
      · 拼句子前用 `B.need()` 挡缺值 —— 缺了就**这一句不写**，不是整页构建失败；
      · 缺分支会印出自相矛盾的句子（「四条里只有四条落后」），历史重放能逮到。

    ═══ LPLA 独有，别家不能照抄 ═══
      · **并购并表是本页最大的误读源。**Atria（2024-10）与 Commonwealth（2025-08）
        是整体并表（见 ACQ / ACQ_BREAKS），当月既不是有机流入、并表后的存量也与左侧
        不可直读。所以本段的「区间」一律以**最近一个并表月之后**为起点现算 ——
        这是 lpla / wealth 两页专有的护栏。
      · **R3 日历护栏在这里根本不成立**：本页没有交易日列，资产/现金是月末时点值，
        NNA 是整月流量、公司也不按日均披露。硬套 calendar_split 会造出一个不存在的
        「日均修正」（brief.py 开头点名的那个坑）。
      · **T3 的处理与 IBKR 相反**：三条资产存量在长历史上并没有单调到被
        `is_monotonic()` 挡掉（2022 熊市那一年跌了大半年），所以 peak_scan 会老老实实
        报「三条同创新高」。给这句话降权用的是**历史新高月的频率本身**
        （`tot >= np.maximum.accumulate(tot)` 的计数），不是「上涨月频率」——
        两者是两个量：一条序列完全可以七成月份在涨、同时连续 18 个月低于前高
        （LPLA 2022-01→2023-06 正是如此），拿后者去证明前者是论据错位。
      · **分部 NNA 的主语必须钉死。**Brokerage NNA 长期为负，但 Advisory NNA 与
        全公司有机 NNA 同期为正、Brokerage 占资产同期在降 —— 那是公司战略目标的
        brokerage→advisory 内部搬家，不是客户流失。所以「失血」这类词只能在
        **全公司口径也为负**时才印，且三条对手方数字（Advisory NNA / 全公司有机 NNA /
        Brokerage 占比）必须同句给出，否则读者会把分部读成全公司。
      · **有机口径**：本页的 NNA 一律先减去公司同页披露的 Acquired NNA（R5 的
        「还原口径」在 LPLA 这里表现为「已扣披露的并购导入」），名次也按还原后的序列排。
        但**分部 NNA 公司只披露 as-reported**（ACQ 表只有总额、不按 Advisory/Brokerage
        拆分），所以分部那句必须自己标 as-reported 并把窗口内的并购导入金额写出来，
        不能让读者以为它和总量一样已经还原。
      · **现金占资产是 A/B 推导值**（公司只披露客户现金与客户资产两条），按 R4 只报
        「分子增速 ÷ 分母增速」这一个恒等关系，绝不写成「几成来自分子、几成来自分母」。
        s1 的基准是历史峰值、s4 的基准是去年同月，两句同段出现会撞车；解法是**把两个
        增速的数字直接摆进 s4**（样板 ibkr 的「是客户现金 +25.1% 除以账户 +34.3% 的商」
        就是这个写法），读者自己看得见现金同比是正是负。原先另加一句「客户现金按同比
        看反而在涨：」的过渡语已删 —— 有了数字它就是同一句话说两遍。
    """
    A = lambda s: np.asarray(s, float)
    tot, adv, bro, cash = A(tot), A(adv), A(bro), A(cash)
    cashp, og, nna_ex, nnaa, nnab = A(cashp), A(og), A(nna_ex), A(nnaa), A(nnab)
    i, n = len(months) - 1, len(months)
    sg = lambda v: '+' if v >= 0 else '-'
    bn = lambda v: f'{sg(v)}{B.usd(abs(v), 1)}bn'

    # ── R1：存量峰值扫描。skip_monotonic 保持默认开着 —— 本页四条都通不过
    #    is_monotonic（2022 年跌了大半年），所以一条都不会被剔，「同创新高」照实报，
    #    但紧接着用**历史新高月的频率**把这句话降权（T3 的相对表述）。
    ser = [('总资产', tot), ('Advisory', adv), ('Brokerage', bro), ('客户现金', cash)]
    pk = B.peak_scan(months, ser, i)
    smap = dict(ser)
    # 「新高」的信息量由 ATH 频率本身决定，不能拿上涨月频率代替（两者不是一个量）。
    # NaN 不能进 np.maximum.accumulate（会把后面整段污染成 NaN），所以逐点扫。
    def ath_flags(a):
        out, m = np.zeros(len(a), bool), -np.inf
        for t, v in enumerate(np.asarray(a, float)):
            if np.isfinite(v) and v >= m:
                out[t], m = True, v
        return out

    ft = ath_flags(tot)
    m_ath = int(np.sum(np.isfinite(tot)))
    ath = int(np.sum(ft))
    # 定性词跟着算出来的比例走：过半月份都在新高上，「创新高」才是噪音。
    v1 = '<b>新高本身信息量低</b>' if m_ath and ath / m_ath >= 0.5 else '<b>创新高并非常态</b>'
    ath_txt = f'总资产{m_ath}个月中{B.quant(ath, m_ath, "个月")}在新高上'
    # 计数只能落在 peak_scan **真的扫过**的那几条上（缺值月与被单调剔除的列不算），
    # 否则会印出「四条存量无一在峰值上」而其实只扫了两条。
    scan = [(nm, s) for nm, s in ser if nm not in set(pk['skipped']) and np.isfinite(s[i])]
    # 两个分支都要给计数：一轮回调会让四条同时掉出峰值、「同创新高」那半句消失，
    # 只剩一串落后名单时整段会掉到 render() 的 240 字下限以下，页面同样停更。
    if not scan:
        s1 = ''
    elif pk['at_peak']:
        s1 = f'{B.mo(months[i])}月末{B.cn(len(pk["at_peak"]))}条存量同创新高，但{ath_txt}，{v1}；'
    else:
        s1 = f'{B.mo(months[i])}月末{B.cn(len(scan))}条存量无一在峰值上，{ath_txt}，{v1}；'
    if s1 and pk['skipped']:
        s1 += f'{"、".join(pk["skipped"])}已按单调序列剔除；'
    if s1 and pk['off_peak']:
        # 落后的只详写差得最多的那条，其余只报个数 —— 一轮回调可能让四条同时掉出峰值，
        # 逐条写「峰值停在 X、现低 Y%」会把整段顶穿 render() 的 400 字上限，页面停更。
        # 「只有一条 / 有两条 / 多达三条」由 B.quant 按占比决定，不写死。
        gaps = sorted(((abs(smap[nm][i] / np.nanmax(smap[nm]) - 1), nm, k)
                       for nm, k in pk['off_peak']), reverse=True)
        g, wn, wk = gaps[0]
        # 个数只在「有的在峰值、有的没跟上」时才报；开头那句若已经写成
        # 「N 条存量无一在峰值上」，这里再报一遍个数就是重复，而且 scan 只剩一条时
        # 会印出「没跟上的多达一条」这种量词与语义打架的句子。
        s1 += ((f'没跟上的{B.quant(len(gaps), len(scan), "条")}：' if pk['at_peak']
                else '其中')
               + f'{wn}峰值停在{wk}、低{B.pct(g, sign=False)}。')
    elif s1:
        # 几条同时站在峰值上是个稀有事件，报它的历史频次比干说「无一落后」有信息量，
        # 而且这一支若只写四个字，整段会掉到 render() 的 240 字下限以下、页面停更。
        # 频次只对**本月扫过的那几条**算，否则「四条同处峰值」会把没扫的列也算进去。
        allpk = np.logical_and.reduce([ath_flags(s) for _, s in scan])
        k4 = int(np.sum(allpk))
        prev4 = [t for t in range(i) if allpk[t]]
        s1 += (f'{B.cn(len(scan))}条同处峰值的月份{n}个月里{B.quant(k4, n, "个")}'
               + (f'，上一次是{months[prev4[-1]]}。' if prev4 else '，本月是第一次。'))

    # ── R2：有机 NNA 的基数护栏。名次按**年化有机增速**排而不是按 $bn 排：
    #    资产基数八年翻了近四倍，同样的 $bn 在 2018 与今天不是一回事。
    #    R2 明写：m/m 与 y/y 反号、或上月处在全样本前三高时，**必须**同句给基数说明。
    #    那一句要挂在两个分支上 —— 只接「谷底反弹」分支的话，下个月环比一转负就会
    #    印出一句光秃秃的「环比 -X%」，正是 R2 点名要拦的误读，而且不会报错。
    be = B.base_effect(nna_ex, i)
    nf = int(np.sum(np.isfinite(og)))
    r_prev = B.rank_of(-og, i - 1) if i >= 1 else None
    r_cur = B.rank_of(-og, i)
    mult = (be['mm'] + 1) if (be['mm'] is not None and i >= 1 and nna_ex[i - 1] > 0) else None
    g_high = (('（上月是全样本 NNA 最高月，环比属基数效应）' if be['prev_is_max'] else
               f'（上月 NNA 排全样本第{be["prev_rank"]}高，环比属基数效应）')
              if be['prev_rank'] is not None and be['prev_rank'] <= 3 else '')
    g_conf = (f'（环比与同比反号、上月 NNA 排第{be["prev_rank"]}，是基数不是趋势）'
              if be['conflict'] else '')
    # 「谷底反弹」那一支自己已经把「上月倒数第 N、回升后仍是倒数第 M」写全了，R2 要的
    # 基数说明在那里就已经给到；再挂一遍完整补注等于同一件事说两遍，还把整段顶出 350 字
    # （历史重放里 2025-12 撑到 356 字、2026-02 撑到 352 字，都是这么来的）。
    # 所以那一支只留「反号」这一个它自己讲不出来的事实 —— 删的是重复，不是分支判断。
    g_conf_lite = '（环比与同比反号）' if be['conflict'] else ''
    lead = '有机 NNA（已扣披露并购导入）'
    if not B.need(r_cur, be['mm']):
        s2 = ''
    elif be['mm'] > 0 and r_prev is not None and r_prev <= nf * 0.25:
        # 「像拐点、实为谷底反弹」这两句只在上月真的处在低位四分之一时才成立。
        # 「环比升至上月的 N 倍」而不是「环比 N 倍」：后者在中文里会被读成「增长 N 倍」。
        # 这一支已经把上月的名次（倒数第 N）写在句子里了，R2 对「上月处在前三高」的
        # 补注要求自动满足，且与本支的前提互斥，所以只接反号那一条。
        s2 = (lead + (f'环比升至上月的{mult:.1f}倍' if mult else f'环比{B.pct(be["mm"])}')
              + f'像拐点，实为谷底反弹：上月年化增速排{nf}个月倒数第{r_prev}，'
              + f'<b>回升后仍是倒数第{r_cur}</b>{g_conf_lite}。')
    else:
        s2 = (lead + f'环比{B.pct(be["mm"])}，年化增速排{nf}个月倒数第{r_cur}'
              + (f'、上月倒数第{r_prev}' if r_prev is not None else '')
              + f'{g_high or g_conf}。')

    # ── 口径背离：分部流量 vs 全公司流量。起点现算（不写死 2025-08），
    #    并表月本身不计入窗口 —— 那个月的 NNA 是并表导入，不是流量。
    #    **算不出来要降级，不能硬失败**：本文件历史上正是栽在 `.index()` 找不到就
    #    ValueError、整页永久停更（build/ibkr.py 的 Exhibit 18 注释点名的就是这件事）。
    #    样本里一笔并表都没有时（只会发生在被截短的历史上）退回「近 12 个月」的窗口，
    #    并把「并表月」相关的字样一并省掉 —— 只许声称真存在的东西。
    bidx = [(months.index(str(p_)), l_) for p_, l_ in ACQ_BREAKS if str(p_) in months]
    prior = [b for b in bidx if b[0] < i]
    jb, lab = prior[-1] if prior else (None, None)
    if bidx and bidx[-1][0] == i:
        # 本月就是并表月：流量窗口无从谈起（当月 NNA 是并表导入不是流量），
        # 这一句改成交代并表本身 —— 那才是这个月唯一该讲的读法。
        s3 = (f'本月{bidx[-1][1]}整体并表导入{B.usd(ACQ.get(months[i], 0.0), 1)}bn，'
              '既不是有机流入，并表后的存量也与左侧不可直读；'
              '本段的有机口径已把它扣除，分部 NNA 仍是 as-reported。')
    else:
        j = jb if jb is not None else max(0, i - 12)
        if i - j < 1 or not B.need(bro[i], bro[j], tot[i], tot[j]):
            s3 = ''
        else:
            f_bro = float(np.nansum(nnab[j + 1:i + 1]))
            f_adv = float(np.nansum(nnaa[j + 1:i + 1]))
            f_firm = float(np.nansum(nna_ex[j + 1:i + 1]))      # 全公司有机口径
            sh0, sh1 = bro[j] / tot[j] * 100, bro[i] / tot[i] * 100
            # R5：分部 NNA 是 as-reported，窗口内若含已披露的并购导入必须写出来 ——
            # 公司不按分部拆分，所以这一段的分部数里可能混着它（方向保守：剔掉只会更负）。
            # 逐月列会随窗口变长而顶穿 400 字上限，所以只报窗口合计与月数。
            aw = [(m, ACQ[m]) for m in months[j + 1:i + 1] if ACQ.get(m)]
            aws = sum(v for _, v in aw)
            cal = (f'（as-reported，含未拆分的{B.usd(aws, 1)}bn并购导入）'
                   if aw else '（as-reported）')
            # 结论按当场算出的三个方向定分支，不预设「失血」：
            if f_firm <= 0:
                v3 = '<b>全公司有机口径同为净流出</b>'
            elif f_bro < 0 <= f_adv and sh1 < sh0:
                v3 = '<b>是转投顾的内部搬家非客户流失</b>'
            else:
                negs = [nm for nm, v in (('Advisory', f_adv), ('Brokerage', f_bro)) if v < 0]
                v3 = ('<b>两个分部同为净流入</b>' if not negs else
                      f'<b>净流出只在{"、".join(negs)}，全公司有机口径仍为正</b>')
            # 一句一个意思（F1）：分号前只讲 Brokerage 自己（占比与流量同一个主语、同一个
            # 方向），口径标注跟在数字后面而不是插在「NNA」与「累计」中间；分号后摆两条
            # 对手方数字再落点。原先六个层次挤在一串逗号里，读起来像脚注不像导读。
            s3 = ((f'{lab}并表后{i - j}个月，' if jb is not None else f'近{i - j}个月，')
                  + f'Brokerage 占资产{"降" if sh1 < sh0 else "升"}{abs(sh1 - sh0):.1f}pp、'
                  + f'NNA 累计{bn(f_bro)}{cal}；'
                  + f'同期 Advisory {bn(f_adv)}、全公司有机 {bn(f_firm)}，{v3}。')

    # ── R4：现金占资产是 A/B 推导值。只报「分子增速 ÷ 分母增速」这一个恒等关系。
    #    原先这里还写了「同比降幅的 N% 出在并表那一个月的机械稀释」，为压字数删掉了：
    #    它是第二层分解，而这一句真正要拦的误读（占比创新低 ≠ 客户把钱搬走）由
    #    「分子分母同比双涨 → 被摊薄」这半句就已经拦住，删的是补充不是论据。
    pu = B.per_unit(cash, tot, i, scale=100.0)
    ny, dy = pu.get('num_yoy'), pu.get('den_yoy')
    both_up = B.need(ny, dy) and ny > 0 and dy > 0
    mc = int(np.sum(np.isfinite(cashp)))
    if not B.need(pu['value']):
        s4 = ''
    else:
        # 「第 N 低」在 N 等于样本量时其实是最高，写死「低」字会把方向说反。
        lvl = (f'{mc}个月最低' if pu['is_min'] else
               f'{mc}个月最高' if pu['is_max'] else
               f'{mc}个月里第{pu["rank_low"]}低')
        # 恒等式照样板写法：两个增速的数字直接摆出来，后面接一句短落点。落点按当场
        # 算出的两个符号分三支，三支穷尽了 both_up 之外的全部情形，一个都不写死：
        #   分子分母同涨 → 摊薄；分子在缩 → 占比走低含真实收缩；分子涨而分母缩 → 分母推高。
        idt = (f'，是客户现金同比{B.pct(ny)}除以客户资产{B.pct(dy)}的商'
               if B.need(ny, dy) else '')
        # 同比算不出来时（样本不足 12 个月）不能装作能判断摊薄还是撤资，直接说明白 ——
        # 「该句不写」在这里不适用：读者看到占比创新低，最需要的恰恰是「凭什么还判断不了」。
        if not B.need(ny, dy):
            tail = f'，样本仅{mc}个月还算不出同比，无从判断是摊薄还是被搬走。'
        elif both_up:
            tail = idt + '，属摊薄而非撤资。'
        elif ny <= 0:
            tail = idt + '，占比走低含客户现金自身的收缩。'
        else:
            tail = idt + '，占比是被收缩的客户资产推高的。'
        s4 = '现金占资产（推导值）为' + lvl + tail

    return B.render([s1, s2, s3, s4])


def main():
    df = load()
    LATEST = df.index[-1]
    tot = df['total_assets_usdbn']
    nna = df['nna_total_usdbn']

    df['pct_advisory'] = df['advisory_assets_usdbn'] / tot * 100
    df['organic_growth_ann'] = nna * 12 / tot.shift(1) * 100
    df['cash_pct_assets'] = df['client_cash_usdbn'] / tot * 100
    df['market_gains'] = tot.diff() - nna
    acq = pd.Series({pd.Period(k, 'M'): v for k, v in ACQ.items()}).reindex(df.index).fillna(0.0)
    df['acquired_nna'] = acq
    df['nna_ex'] = nna - acq
    df['organic_growth_ex'] = df['nna_ex'] * 12 / tot.shift(1) * 100
    df['total_tn'] = tot / 1000.0

    # ── 量→收入桥：client cash revenue = 月末客户现金 x 披露净收益率 / 12 ──
    cy = rate_series('client_cash_net_yield')                    # bp, annualised
    q_of_month = pd.PeriodIndex(df.index).asfreq('Q')
    cy_m = pd.Series([cy.get(qq, np.nan) for qq in q_of_month], index=df.index).ffill()
    df['implied_cash_rev_usdmn'] = df['client_cash_usdbn'] * 1000.0 * cy_m / 10000.0 / 12.0
    BR_NOTE = ('Assumption: monthly client-cash revenue = month-end client cash x the disclosed '
               'net yield / 12. The yield is taken from the quarterly report '
               f'({cy.index[-1]} = {cy.iloc[-1]:,.4g} bp) and held flat for months after '
               'that quarter')

    # ── 费率期间的披露文案（全部现算）───────────────────────────────────────
    # 月度数字每月往前走、费率按季度更新，所以「本月的隐含值用的是哪一季的费率」是
    # 长期存在的口径事实，不是 bug —— 但读者有权知道。文案一律从 series/fee_rates.csv
    # 现算：写死季度号的话，下一季就变成假话（本仓已经踩过 schw「过去 32 个季度」、
    # cost「Exhibit 4 画了红线」两次同类的坑）。
    def rate_q_for(p):
        """月份 p 实际用到的费率季度 = 不晚于该月所属季度的最后一个可得季度（对齐 ffill）。"""
        prior = [q for q in cy.index if q <= p.asfreq('Q')]
        return prior[-1] if prior else None

    LAT_Q = LATEST.asfreq('Q')            # 本页数据最新月所在季度
    RQ_LAST = cy.index[-1]                # 最新可得费率季度
    RQ_LAT = rate_q_for(LATEST)           # 最新月真正用到的费率季度
    LAG_Q = None if RQ_LAT is None else (LAT_Q - RQ_LAT).n
    # 「过期」判据：最新可得费率季度比「数据月所在季度的上一季」还老（滞后 ≥ 2 个季度）。
    # 正常节奏下 LAG_Q 只会是 0 或 1（季初一两个月还没等到当季财报），那是口径不是异常。
    FEE_STALE = LAG_Q is not None and LAG_Q >= 2
    # 窗口内所属季度尚无披露费率、只能沿用上一季的月份
    CARRY_M = [p for p in df.index[-WIN_L:] if p.asfreq('Q') not in cy.index]
    _carry_span = ('' if not CARRY_M else
                   mlab(CARRY_M[0]) if len(CARRY_M) == 1
                   else f'{mlab(CARRY_M[0])}–{mlab(CARRY_M[-1])}')
    FEE_Q_NOTE = (
        f'<b>费率期间：</b>净收益率按季度披露，本页月度数据截至 {mlab(LATEST)}（{LAT_Q}）。'
        + (f'{mlab(LATEST)} 的隐含值取 {RQ_LAT} 公司披露的 {float(cy.loc[RQ_LAT]):,.4g} bp'
           + ('（与该月同季，无滞后）。' if LAG_Q == 0 else
              f'（{LAT_Q} 尚无披露费率，沿用上一可得季度，滞后 {LAG_Q} 个季度）。')
           if RQ_LAT is not None else '最新月早于任何一个可得费率季度，隐含值留空。')
        + (f'近 {WIN_L} 个月窗口里有 {len(CARRY_M)} 个月（{_carry_span}）所属季度尚无披露费率、'
           '沿用上一季费率，其余月份用的是本季费率。' if CARRY_M else
           f'近 {WIN_L} 个月窗口里每个月都用到了自己所属季度的披露费率。')
        + (f'<b>⚠️ 费率尚未更新至 {LAT_Q}，也未更新至 {LAT_Q - 1}</b> —— 本图仍用 '
           f'{RQ_LAST} 的读数（滞后 {LAG_Q} 个季度，通常是公司财报延后）。'
           '这期间利率环境若已变化，隐含值不会跟着动，落差要算在费率口径上、不是业务上。'
           if FEE_STALE else ''))

    # 桥的季度验证：只保留满 3 个月的季度
    imp_m = df['implied_cash_rev_usdmn'].dropna()
    qi = pd.PeriodIndex(imp_m.index).asfreq('Q')
    imp_q = imp_m.groupby(qi).sum()
    cnt = pd.Series(1, index=imp_m.index).groupby(qi).sum()
    imp_q = imp_q.loc[[q for q in imp_q.index if cnt.get(q, 0) == 3]]
    act_q = rate_series('client_cash_revenue', to='mn')

    # ── 三个窗口 ──
    W25 = df.iloc[-WIN_L:]
    W13 = df.iloc[-WIN_S:]
    XL25 = [mlab(p) for p in W25.index]
    XL13 = [mlab(p) for p in W13.index]
    XLALL = [mlab(p) for p in df.index]
    BK25, BN25 = brk_pack(W25.index)
    BK13, BN13 = brk_pack(W13.index)
    BKALL, BNALL = brk_pack(df.index)

    # gsx.lvl_bar 的 docstring：「次轴画的是同比而不是滚动均线 —— 均线只是把柱子再平滑
    # 一遍、不带新信息，同比才回答『相对去年这个月是好是坏』」。本页是从 gsx deck 移植
    # 的，所以照 deck 画次轴 y/y、不画均线（cost / ibkr 两页不是从 deck 移植的，保持均线）。
    YOY_NOTE = ('右轴金色折线为同比（同原 deck 的 gsx.lvl_bar 次轴），不再画 12 个月均线：'
                '均线只是把柱子再平滑一遍、不带新信息，而且它按构造落在柱子中段，'
                '凡是当月值接近均值的月份数值标签都会被它拦腰划断。')

    def bar(n, col, title, legend, ylab, fmt, note, pct_series=False,
            window=W25, xl=XL25, breaks=None, brk_note='', extra=None,
            yoy=True, ylab2=None):
        """gsx.lvl_bar → 网页 gs_bar（柱 + 每柱数值 + 次轴 y/y 折线）。

        yoy=False 只留给「同比本身没有意义」的序列（本页只有 Exhibit 3，见那里的说明），
        那种图退回 Prior-12mo 均线 + y/y 气泡。
        """
        s = df[col].dropna()
        ex = {'n': n, 'kind': 'gs_bar', 'fmt': fmt, 'yfmt': fmt, 'xlabels': xl,
              'title': title, 'ylab': ylab, 'legend': legend,
              'values': L(window[col].values)}
        if yoy:
            yv = yoy_series(df[col], window.index, pct_series)
            ex['ylab2'] = ylab2 or ('y/y (pp, RHS)' if pct_series else 'y/y (%, RHS)')
            ex['yoy'] = {'name': 'y/y (pp, RHS)' if pct_series else 'y/y (RHS)',
                         'color': 'GOLD', 'values': L(yv.values),
                         'yfmt': 'pp1' if pct_series else 'pct0'}
        else:
            ex['avg12'] = avg_prior12(s)
            y = yoy_txt(s, pct_series)
            if y:
                ex['yoy_txt'] = y
        if breaks:
            ex.update(breaks)
            if n is not None:
                DRAWN.append(n)
        if note or brk_note:
            ex['note'] = ((note or '') + ((brk_note + '。') if brk_note else ''))
        if extra:
            ex['src_extra'] = extra
        return ex

    ex = []

    def add(exd, breaks=None):
        """把断点字段并进 exhibit 再登记编号 —— notes 里「哪几张图画了断点线」那句现算，
        写死一串编号，窗口滚过断点的那个月就变成假话。"""
        if breaks:
            exd.update(breaks)
            DRAWN.append(exd['n'])
        ex.append(exd)
        return exd

    # ── Exhibit 2：Total client assets（gsx.lvl_bar, win=25, dec=2, $tn）──
    ex.append(bar(2, 'total_tn', 'Total client assets', 'Total client assets',
                  'Total client assets ($tn)', 'usd2',
                  '原 deck 的 gsx.lvl_bar（win=25、dec=2、单位 $tn）。柱为月末客户资产总额。'
                  + YOY_NOTE,
                  breaks=BK25, brk_note=BN25))

    # ── Exhibit 3：Organic net new assets（gsx.lvl_bar, win=25, dec=1, $bn）──
    # 这张**不开**次轴 y/y，是本页唯一的例外：有机 NNA 是一个体量小、月度波动大的流量，
    # 按 gsx 的口径实算出来的同比在本窗口里是 -88% ~ +1,600%（2025-01 的 $33.3bn 比
    # 2024-01 的 $2.0bn），一条贴着零的直线加一根冲天尖峰，读者读不出任何东西，
    # 还要把右轴撑成四位数。GS 规矩 1 说的正是这件事：流量不算百分比，趋势读 Exhibit 4
    # 的年化有机增长率（那才是流量的「同比」）。所以这张退回 Prior-12mo 均线 + y/y 气泡。
    ex.append(bar(3, 'nna_ex', 'Organic net new assets', 'Organic NNA',
                  'Organic net new assets ($bn)', 'usd1',
                  'Total NNA less the Acquired NNA that LPL discloses on the same page '
                  '(Atria Oct-24 $88.3bn, Commonwealth Aug-25 $275.0bn)。'
                  '并购导入按公司披露的拆分逐月扣除，不整月置零。'
                  '本页只有这一张不画次轴同比：有机 NNA 是小体量流量，实算同比在本窗口内'
                  '介于 -88% 与 +1,600% 之间（2025-01 的 $33.3bn 比 2024-01 的 $2.0bn），'
                  '按 GS 规矩 1 流量不算百分比，趋势请读 Exhibit 4 的年化有机增长率；'
                  '这里改画最新月之前 12 个月的均值虚线。',
                  yoy=False))

    # ── Exhibit 4：Annualised organic growth rate（gsx.lvl_bar, pct_series）──
    ex.append(bar(4, 'organic_growth_ex', 'Annualised organic growth rate',
                  'Annualised organic growth', 'Organic growth (% annualised)', 'pct1',
                  'Organic NNA x 12 / prior month-end assets, the GS convention; acquired '
                  'assets stripped out using the disclosed split。'
                  '比率序列的同比用百分点差（GS 规矩 2），所以右轴单位是 pp。' + YOY_NOTE +
                  '本图右轴同比在 ±22pp 之间跨零、左轴柱值恒正，两轴零点对齐的代价超过阈值，'
                  '引擎改为两轴独立缩放并在绘图区左上角标出（红色斜体）。',
                  pct_series=True))

    # ── Exhibit 5：Client assets advisory vs brokerage（gsx.stack_share, win=13）──
    share13 = (W13['advisory_assets_usdbn'] / (W13['advisory_assets_usdbn']
                                               + W13['brokerage_assets_usdbn']) * 100)
    ymax_share = max(60.0, 10.0 * math.ceil(float(share13.max()) / 10.0))
    add({
        'n': 5, 'kind': 'stacked_dual', 'xlabels': XL13,
        'title': 'Client assets: advisory vs. brokerage',
        'ylab': 'Client assets ($bn)', 'ylab2': '% advisory (RHS)',
        'yfmt': 'f0c',
        'stacks': [
            {'name': 'Advisory', 'color': 'NAVY', 'values': L(W13['advisory_assets_usdbn'].values),
             'label': True, 'label_color': 'WHITE'},
            {'name': 'Brokerage', 'color': 'BLUE', 'values': L(W13['brokerage_assets_usdbn'].values),
             'label': True, 'label_color': 'NAVY'},
        ],
        'line': {'name': '% advisory (RHS)', 'color': 'GREEN', 'values': L(share13.values),
                 'ymax': ymax_share},
        'note': '堆叠柱为两个业务口径的月末资产（$bn），右轴绿线为 advisory 占比。'
                + (BN13 + '。' if BN13 else '') + QNOTE + '。',
    }, BK13)

    # ── Exhibit 6：What moved client assets（gsx.bridge_bar, win=13）──
    net13 = W13['nna_total_usdbn'].fillna(0) + W13['market_gains'].fillna(0)
    add({
        'n': 6, 'kind': 'bridge_bar', 'xlabels': XL13, 'fmt': 'f0',
        'title': 'What moved client assets: flows vs. markets',
        'ylab': 'Change in client assets ($bn)',
        'stacks': [
            {'name': 'Net new assets', 'color': 'NAVY', 'values': L(W13['nna_total_usdbn'].values)},
            {'name': 'Market gains (balancing)', 'color': 'BLUE', 'values': L(W13['market_gains'].values)},
        ],
        'net': {'name': 'Total change in client assets', 'values': L(net13.values)},
        'net_color': 'INK',
        'note': 'Identity: opening assets + NNA + market gains = closing assets. '
                'Market gains 是恒等式的配平项（当月资产变动 − 当月 NNA），不是公司披露值。'
                + (BN13 + '。' if BN13 else ''),
    }, BK13)

    # ── Exhibit 7：NNA by channel（gsx.multi_line, win=25）──
    # 截轴（规矩 7）：两笔并表把 Advisory NNA 顶到 $211.1bn、Brokerage NNA 顶到 $81.7bn，
    # 而其余 23 个月两条线都在 -$3 ~ +$15bn 之间 —— 不截轴的话整张图就是「两条压在
    # 零线上的平线 + 两根尖峰」，日常经营的那点差异一个都读不出。截轴不删点：超界的点
    # 画成空心红圈、真值竖排标出（Oct-24 的 66.5 / 30.1 与 Aug-25 的 211.1 / 81.7）。
    # yfloor 必须一起给：lines_endlabels 的默认下界是 mn - 0.20×极差，极差被尖峰撑到
    # 214 之后下界会掉到 -46，只给 ycap 会留下一大片空白负区。
    ex7_lo, ex7_hi = -6.0, 35.0
    ex7_v = list(W25['nna_advisory_usdbn'].values) + list(W25['nna_brokerage_usdbn'].values)
    CAP7, _ = cap_pack(7, f'渠道 NNA，截 ${ex7_lo:.0f} ~ ${ex7_hi:.0f}bn', ex7_v,
                        hi=ex7_hi, lo=ex7_lo,
                        cap_note='axis capped — true values shown in red')
    ex7_top = '、'.join(
        f'{mlab(p)} 的 {lab} NNA ${v:,.1f}bn'
        for p, lab, v in sorted(
            [(p, lab, float(v)) for c, lab in (('nna_advisory_usdbn', 'Advisory'),
                                               ('nna_brokerage_usdbn', 'Brokerage'))
             for p, v in W25[c].items() if v > ex7_hi],
            key=lambda t: (t[0], t[1])))
    add({
        'n': 7, 'kind': 'lines_endlabels', 'fmt': 'f1', 'xlabels': XL25,
        'title': 'Net new assets by channel', 'ylab': 'Net new assets ($bn)',
        'series': [
            {'name': 'Advisory NNA', 'color': 'NAVY', 'values': L(W25['nna_advisory_usdbn'].values)},
            {'name': 'Brokerage NNA', 'color': 'RED', 'values': L(W25['nna_brokerage_usdbn'].values)},
        ],
        **CAP7,
        'note': 'Brokerage NNA has been persistently negative — the advisory conversion is '
                'visible as a mirror image。'
                + (f'纵轴截在 ${ex7_lo:.0f}bn ~ ${ex7_hi:.0f}bn：并表月把线顶出量程'
                   f'（{ex7_top}），不截轴则其余各月全部压成贴零的平线。'
                   '<b>截轴不删点</b> —— 超界的点画成空心红圈，真值竖排标在图上，'
                   '表格视图与 tooltip 里也是真值。' if CAP7 else '')
                + (BN25 + '。' if BN25 else ''),
    }, BK25)

    # ── Exhibit 8：Total client assets since 2018（gsx.long_line）──
    # zero_base + end_label = 补回 gsx.long_line 的 set_ylim(0, max*1.16) 与 n_label。
    # 不给 zero_base 时引擎走 y0 = min − 极差×5%，那是一次没有任何标注的隐性截轴，
    # 在长历史图上等于把增长幅度凭空放大（本图实测轴底原为 0.8，数据最低 0.67）。
    add({
        'n': 8, 'kind': 'lines', 'x': 'long', 'full': True, 'fmt': 'usd1', 'xstep': 6,
        'zero_base': True, 'end_label': True, 'label_fmt': 'usd2',
        'title': 'Total client assets since 2018', 'ylab': 'Total client assets ($tn)',
        'series': [{'name': 'Total client assets', 'color': 'NAVY', 'values': L(df['total_tn'].values)}],
        'note': (BNALL + '。' if BNALL else '') +
                '纵轴从 0 起（同原 deck 的 long_line），末点标出最新读数 —— '
                '浮动基线会把这条线的增长幅度视觉上放大，而长历史图上末点数值是唯一的'
                '绝对水平锚点。原 deck 在末端画了一个红色虚线圈标出最近 3 个月，'
                '网页版没有等价元素，改由末点数值标注与表格视图直接读数。',
    }, BKALL)

    # ── Exhibit 9：Client cash balances（gsx.lvl_bar, win=25）──
    # 客户现金同样跨并表：2025-07 $49.5bn → 2025-08 $52.7bn（+6.5% m/m，2018 年以来
    # 8 个 8 月里最大的一个），Commonwealth 把客户现金一起带了进来。原先这一族
    # （Ex9/10/13/17）一条断点线都没画，而页面 notes 却声称「凡是跨这一期读的图都画了」。
    ex.append(bar(9, 'client_cash_usdbn', 'Client cash balances', 'Client cash balances',
                  'Client cash ($bn)', 'usd1',
                  '月末客户现金余额（含银行存款 sweep）。' + QNOTE + '。' + YOY_NOTE,
                  breaks=BK25, brk_note=BN25))

    # ── Exhibit 10：Client cash as % of client assets（gsx.lvl_bar, pct_series）──
    ex.append(bar(10, 'cash_pct_assets', 'Client cash as % of client assets',
                  'Client cash / client assets', 'Client cash (% of client assets)', 'pct1',
                  'Cash share is the key net-interest-revenue driver; a falling share is a '
                  'headwind。原 deck 这张图取两位小数；网页图上取一位 —— 25 根柱的两位小数'
                  '标签会横向叠成一片（引擎只能把它们抽稀掉一半），两位小数见本图的'
                  '「表格」视图与末尾 Exhibit 20 核对表。分子分母跨并表同时跳，'
                  '断点两侧的占比不可直读。' + YOY_NOTE,
                  pct_series=True, breaks=BK25, brk_note=BN25))

    # ── Exhibit 11：NNA by quarter（gsx.qtr_bar, win=14）──
    nq = nna.dropna()
    qidx = pd.PeriodIndex(nq.index).asfreq('Q')
    q_sum = nq.groupby(qidx).sum()
    q_cnt = pd.Series(1, index=nq.index).groupby(qidx).sum()
    q_yoy = pd.Series([(q_sum.iloc[i] / q_sum.iloc[i - 4] - 1) * 100
                       if i >= 4 and q_sum.iloc[i - 4] else np.nan
                       for i in range(len(q_sum))], index=q_sum.index)
    qw = q_sum.iloc[-WIN_Q:]
    qy = q_yoy.iloc[-WIN_Q:]
    partial = int(q_cnt.iloc[-1])
    qlabs = [str(p) for p in qw.index]
    BKQ, BNQ = brk_pack(qw.index)
    # 右轴同比撤掉的依据不是「看着难看」，是逐季实算：并购污染率 = 该季 Acquired NNA ÷
    # 该季总 NNA；自身 ≥10% 或去年同期 ≥10% 的季度，同比就不是可比读数。
    acq_q = acq.groupby(pd.PeriodIndex(df.index).asfreq('Q')).sum().reindex(q_sum.index).fillna(0.0)
    contam = (acq_q / q_sum.replace(0, np.nan) * 100).abs()
    bad_q = [q for q in qw.index
             if contam.get(q, 0) >= 10
             or (q - 4 in q_sum.index and contam.get(q - 4, 0) >= 10)]
    ok_yoy = qy.dropna().drop(index=[q for q in bad_q if q in qy.index], errors='ignore')
    worst = float(ok_yoy.abs().max()) if len(ok_yoy) else 0.0
    ex11_cap = 48.0
    CAP11, _ = cap_pack(11, f'季度 NNA，截 ${ex11_cap:.0f}bn', list(qw.values), hi=ex11_cap)
    ex11_top = '、'.join(f'{q} ${v:,.0f}bn' for q, v in qw.items() if v > ex11_cap)
    add({
        'n': 11, 'kind': 'qtr_bar', 'xlabels': qlabs, 'fmt': 'f0c', 'label_fmt': 'f0c',
        'title': 'Net new assets by quarter', 'ylab': 'Net new assets ($bn)',
        'legend': 'Complete quarter',
        'values': L(qw.values), 'qtr_months': 3,
        **({'partial_months': partial} if partial < 3 else {}),
        **CAP11,
        'note': '月度 NNA 按日历季汇总。'
                + (f'纵轴截在 ${ex11_cap:.0f}bn：{ex11_top} 这几个含并表/大型机构导入的季度'
                   '不截轴会把其余常规季度全部压成矮矮一排。'
                   '<b>截轴不删点</b> —— 超界的柱画到边界并加断口符号，真值竖排标在柱旁，'
                   '表格视图与 tooltip 里是完整的季度合计。' if CAP11 else '')
                + '<b>右轴同比已撤掉</b>：按 GS 规矩 1，NNA 是流量、不算百分比；'
                f'实算下来窗口内 {len(qw)} 个季度有 {len(bad_q)} 个的同比不可比'
                '（自身或去年同期的 Acquired NNA 占该季 NNA 的 10% 以上），'
                f'只剩 {len(ok_yoy)} 个可比点、彼此还不相邻，连不成一条可读的线，'
                f'而且其中最大的一个仍有 {worst:.0f}%，画出来照样是「一根尖峰加一条贴零的直线」。'
                '季度趋势请读 Exhibit 4 与 Exhibit 18 的年化有机增速，'
                '各季 NNA 合计与并表金额见本图的「表格」视图与 Exhibit 20。'
                + (BNQ + '。' if BNQ else ''),
    }, BKQ)

    # ── Exhibit 12：Advisory assets（gsx.lvl_bar, win=25）──
    ex.append(bar(12, 'advisory_assets_usdbn', 'Advisory assets', 'Advisory assets',
                  'Advisory assets ($bn)', 'f0c',
                  '月末 advisory 口径客户资产。' + YOY_NOTE,
                  breaks=BK25, brk_note=BN25))

    # ── Exhibit 13：Implied client-cash revenue（gsx.lvl_bar, win=25）──
    ex.append(bar(13, 'implied_cash_rev_usdmn', 'Implied client-cash revenue',
                  'Implied client-cash revenue', 'Implied client-cash revenue ($mn / month)',
                  'usd0', BR_NOTE + '。<b>推导值，非公司披露</b>，验证见 Exhibit 14。'
                  '规模基数是月末客户现金，因此与 Exhibit 9 一样跨并表跳升。' + YOY_NOTE,
                  breaks=BK25, brk_note=BN25, extra=FEE_Q_NOTE))

    # ── Exhibit 14：Bridge check（gsx.implied_vs_actual）──
    qs = [q for q in imp_q.index if q in act_q.index][-WIN_Q:]
    imp_v = np.array([float(imp_q[q]) for q in qs])
    act_v = np.array([float(act_q[q]) for q in qs])
    err = np.where(act_v != 0, (imp_v / act_v - 1) * 100, np.nan)
    mae = float(np.nanmean(np.abs(err)))
    # 「未满 3 个月的季度」也现算 —— 这句原先写死「2026Q2 只有 2 个月」，下一季就是假话
    _part = sorted(q for q in cnt.index if int(cnt.get(q, 0)) != 3)
    PART_TXT = ('未满 3 个月的季度不参与对比（'
                + '、'.join(f'{q} 只有 {int(cnt[q])} 个月' for q in _part) + '）。'
                if _part else '本页月度序列覆盖到的季度都满 3 个月，没有季度被排除。')
    # 对比窗口里哪些季度的隐含值是用「上一季费率」算的 —— 那几季验的是费率的时滞，
    # 不是月末/季均余额这一个近似，误差读数要分开看。
    _qc = [q for q in qs if q not in cy.index]
    FEE_Q14 = FEE_Q_NOTE + ((
        f'对比窗口 {qs[0]}–{qs[-1]} 内，'
        + (f'{"、".join(str(q) for q in _qc)} 用的是上一季费率（这几季的误差同时含费率时滞），'
           if _qc else '每个季度都用到了本季披露的费率，')
        + f'公司披露的实际客户现金收入已更新至 {act_q.index[-1]}。') if qs else '')
    ex.append({
        'n': 14, 'kind': 'grouped_bars', 'xlabels': [str(q) for q in qs],
        'fmt': 'f0c', 'label_fmt': 'f0c',
        'title': 'Bridge check: implied vs. reported client-cash revenue',
        'ylab': 'Client-cash revenue ($mn / quarter)', 'ylab2': 'Error (%)',
        'groups': [
            {'name': 'Implied by the bridge', 'color': 'BLUE', 'values': L(imp_v)},
            {'name': 'Actually reported', 'color': 'NAVY', 'values': L(act_v)},
        ],
        'line': {'name': 'Error (RHS)', 'color': 'RED', 'values': L(err), 'yfmt': 'pct1'},
        'note': 'Reported = the client-cash revenue line in LPL results. The bridge applies the '
                'disclosed yield to MONTH-END cash while LPL earns it on AVERAGE cash — that '
                f'proxy error is what this tests. 窗口内平均绝对误差 {mae:.1f}%。'
                + PART_TXT +
                '误差线跨零而柱恒正，本引擎又要求两轴零点画在同一高度，所以左轴基线被'
                '拉到负区（收入本身不会为负）—— 这是双轴对齐的既定代价，浪费率约 25%，'
                '在引擎的 38% 阈值以内，故保留对齐而不是让两轴零点错位。'
                '原 deck 的 matplotlib 不对齐零点、误差线直接压在柱上。',
        'src_extra': FEE_Q14,
    })

    # ── Exhibit 15：Brokerage assets（gsx.lvl_bar, win=25）──
    ex.append(bar(15, 'brokerage_assets_usdbn', 'Brokerage assets', 'Brokerage assets',
                  'Brokerage assets ($bn)', 'f0c',
                  '月末 brokerage 口径客户资产。' + YOY_NOTE,
                  breaks=BK25, brk_note=BN25))

    # ── Exhibit 16：Advisory share of client assets（gsx.lvl_bar, pct_series）──
    ex.append(bar(16, 'pct_advisory', 'Advisory share of client assets',
                  'Advisory share', 'Advisory share (% of client assets)', 'pct1',
                  'Advisory assets carry a higher payout-adjusted margin than brokerage, so the '
                  'mix shift is a structural profit driver。原 deck 取两位小数；'
                  '网页图上取一位 —— 25 根柱的两位小数标签会横向叠成一片，'
                  '两位小数见本图的「表格」视图与末尾 Exhibit 20 核对表。'
                  '两笔并表都直接改变了业务口径的构成（Atria 偏 brokerage、'
                  'Commonwealth 偏 advisory），断点两侧的占比不可直读。' + YOY_NOTE,
                  pct_series=True, breaks=BK25, brk_note=BN25))

    # ── Exhibit 17：Client cash since 2018（gsx.long_line）──
    add({
        # fmt 用 f1 而不是 deck 的 dec=0：末点标注与表格视图共用 fmt，f0c 会把 54.8 印成 55
        'n': 17, 'kind': 'lines', 'x': 'long', 'full': True, 'fmt': 'f1', 'xstep': 6,
        'zero_base': True, 'end_label': True,
        'title': 'Client cash since 2018', 'ylab': 'Client cash ($bn)',
        'series': [{'name': 'Client cash', 'color': 'NAVY',
                    'values': L(df['client_cash_usdbn'].values)}],
        'note': '2020 的台阶是疫情期间的现金堆积，2022-24 的回落是现金搬家（cash sorting）；'
                '这条线是 Exhibit 13 隐含收入的规模基数。'
                '纵轴从 0 起（同原 deck 的 long_line）、末点标出最新读数：'
                '之前轴底浮在 30 附近，把 2020 台阶与 2022-24 回落的幅度视觉上放大了约 2.5 倍。'
                + (BNALL + '。' if BNALL else ''),
    }, BKALL)

    # ── Exhibit 18：Organic growth path by year（gsx.year_lines, n_years=6）──
    og = df['organic_growth_ex'].dropna()
    yrs6 = sorted({p.year for p in og.index})[-6:]
    yl_series = []
    for y in yrs6:
        vals = [None] * 12
        for p, v in og.items():
            if p.year == y:
                vals[p.month - 1] = round(float(v), 6)
        yl_series.append({'name': str(y), 'values': vals})
    # 截轴（规矩 7）：2021-04 的 Waddell & Reed 导入让当月年化增速冲到 92.4%，
    # 而 6 条线的其余 71 个月全部落在 1.2%–29.0%。不截轴的话六年全部压成贴零的一小团，
    # 年份之间的对比一个都做不了。yfloor=0 与截轴一起给：这 6 年里没有负值月份，
    # 不给 yfloor 的话通用留白会把轴底压到 -3.3，凭空多出一段空区。
    ex18_cap = 32.0
    y18_all = [v for s_ in yl_series for v in s_['values'] if v is not None]
    y18_max = max(y18_all)
    y18_next = max([v for v in y18_all if v <= ex18_cap], default=0.0)
    CAP18, _ = cap_pack(18, f'年化有机增速，截 {ex18_cap:.0f}%', y18_all,
                          hi=ex18_cap, lo=0.0 if min(y18_all) >= 0 else None)
    if not CAP18 and min(y18_all) >= 0:
        CAP18 = {'yfloor': 0.0}          # 没有越界点也仍要零基线，但不写「已截轴」
    add({
        'n': 18, 'kind': 'year_lines', 'fmt': 'pct1', 'label_fmt': 'pct1',
        'xlabels': ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct',
                    'Nov', 'Dec'],
        'title': 'Organic growth path by year', 'ylab': 'Organic growth (% annualised)',
        'series': yl_series, 'highlight': len(yl_series) - 1,
        **CAP18,
        'note': 'Red = current year。画的是各月的年化有机增速本身（非累计，同原 deck 的 '
                'cumulative=False）。'
                + (f'2021 年 4 月是 Waddell & Reed 导入（当月 NNA $73.8bn），'
                   '公司当年用旧行名披露 Acquired NNA、未解析，故未从有机口径里扣除，'
                   f'该点实际为 {y18_max:.1f}%。'
                   f'纵轴截在 {ex18_cap:.0f}%（其余各月最高 {y18_next:.1f}%）—— '
                   '<b>截轴不删点</b>：越界的点画成空心红圈、真值竖排标在旁边，'
                   '表格视图与 tooltip 里也是真值；不截轴则六条线全部压成贴零的一团，'
                   '年份之间无法比较。' if CAP18.get('cap_note') else
                   f'纵轴从 0 起，本图窗口内最高 {y18_max:.1f}%，无需截轴。'),
    })

    # ── Exhibit 19：Organic growth heat matrix（gsx.heat_matrix, n_years=9）──
    yrs9 = sorted({p.year for p in og.index})[-9:]
    matrix = []
    for y in yrs9:
        row = [None] * 12
        for p, v in og.items():
            if p.year == y:
                row[p.month - 1] = round(float(v), 6)
        matrix.append(row)
    ex.append({
        'n': 19, 'kind': 'heat_matrix', 'full': True, 'fmt': 'pct1',
        'title': 'Annualised organic growth rate (%)',
        'rows': [str(y) for y in yrs9],
        'cols': ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct',
                 'Nov', 'Dec'],
        'matrix': matrix, 'legend': 'Annualised organic growth', 'row_head': '年',
        'note': 'Green = faster organic asset gathering; acquired assets removed using the '
                'disclosed split (complete from 2022 onward)。色标取全部有限值的 5/95 分位，'
                '2021-04 那类离群月不会把整表压平。'
                f'{yrs9[0]} 行只有 {sum(v is not None for v in matrix[0])} 格有数、'
                f'{yrs9[-1]} 行只有 {sum(v is not None for v in matrix[-1])} 格：'
                f'序列自 {df.index[0]} 起，而年化增速要用到上月末资产，所以首月算不出；'
                '末行是当年至今。空白格是数据不存在，不是没画。',
    })

    # ── Exhibit 1：汇总表（gsx.summary_table 的行分组范式）──
    cur, prv, yag = LATEST, LATEST - 1, LATEST - 12

    # 3Y %ile 的判据一律走 build/pctile.py，本文件不再自己写一套。
    # 从前每个生成器各写各的，结果是同一条 LPL total client assets 在本页被判成噪音留空、
    # 在 /wealth/ 却印成绿色 100，两页互相矛盾。判据是口径，口径只能有一处定义。
    blank_rows = []          # 留空的行标签，供表注现算

    def srow(label, col, dec, mode, pct=False, money='', inv=False):
        s = df[col].dropna()
        c = s.get(cur, np.nan)
        p1 = s.get(prv, np.nan)
        p12 = s.get(yag, np.nan)
        cells = [{'v': num(c, dec, money, pct)}, {'v': num(p1, dec, money, pct)},
                 {'v': num(p12, dec, money, pct)}]
        for b in (p1, p12):
            if not (np.isfinite(c) and np.isfinite(b)):
                cells.append({'v': ''})
                continue
            if mode in ('pp', 'abs'):
                v = c - b
            elif b == 0 or c * b < 0:
                cells.append({'v': ''})
                continue
            else:
                v = (c / b - 1) * 100
            # 四舍五入后落在零上的差异不带方向：印「-0bp」/「-0.0」会被读成一个很小的
            # 负数，而它其实是「按这个精度就是 0」。归零并去掉涨跌配色。
            if mode == 'pp' and abs(v) < 1:
                z, sfx, d = _nz(v * 100, 0), 'bp', 0
            elif mode == 'pp':
                z, sfx, d = _nz(v, 2), 'pp', 2
            elif mode == 'abs':
                z, sfx, d = _nz(v, max(0, dec)), '', max(0, dec)
            else:
                z, sfx, d = _nz(v, 1), '%', 1
            sign = '' if z == 0 else ('+' if z > 0 else '-')
            txt = f'{money}{sign}{abs(z):,.{d}f}{sfx}'
            if z == 0:                       # 「按这个精度就是 0」，不带方向也不上色
                cells.append({'v': txt})
                continue
            good = (v < 0) if inv else (v > 0)
            cells.append({'v': txt, 'cls': 'pos' if good else 'neg'})
        # 分位一律走 pctile.cell()：它自己判死列、自己给颜色类
        if s.index[-1] != cur:               # 该列最新月缺数，分位没有对应的当期读数
            cells.append({'v': ''})
            blank_rows.append((label, f'该列最新读数停在 {mlab(s.index[-1])}'))
            return {'label': label, 'cells': cells}
        vals = [float(x) for x in s.values]
        txtp, cls = pctile.cell(vals, inverse=inv)
        cells.append({'v': txtp, 'cls': cls} if txtp else {'v': ''})
        if not txtp:
            blank_rows.append((label, pctile.why_blank(vals) or '样本不足'))
        return {'label': label, 'cells': cells}

    sum_rows = [
            # srow() 有副作用（往 blank_rows 里登记留空原因），所以必须在 summary 之前跑完
            {'kind': 'group', 'label': 'Assets ($bn)'},
            srow('Advisory', 'advisory_assets_usdbn', 1, 'ratio'),
            srow('Brokerage', 'brokerage_assets_usdbn', 1, 'ratio'),
            srow('Total client assets', 'total_assets_usdbn', 1, 'ratio'),
            srow('% Advisory', 'pct_advisory', 1, 'pp', pct=True),
            {'kind': 'group', 'label': 'Net new assets ($bn)'},
            srow('Advisory NNA', 'nna_advisory_usdbn', 1, 'abs'),
            srow('Brokerage NNA', 'nna_brokerage_usdbn', 1, 'abs'),
            srow('Total NNA', 'nna_total_usdbn', 1, 'abs'),
            srow('Annualised organic growth (%)', 'organic_growth_ann', 2, 'pp', pct=True),
            {'kind': 'group', 'label': 'Client cash ($bn)'},
            srow('Client cash balances', 'client_cash_usdbn', 1, 'ratio'),
            srow('% of client assets', 'cash_pct_assets', 2, 'pp', pct=True),
    ]
    # 表注里「哪几行留空、为什么」现算，不写死行名 —— 序列一变，写死的名单就是假话
    _why = {}
    for lab, why in blank_rows:
        _why.setdefault(why, []).append(lab)
    _bl = '；'.join(f'{" / ".join(v)}（{k}）' for k, v in _why.items())
    summary = {
        'title': f'LPL Financial monthly metrics — {mlab(LATEST)}',
        'heads': [mlab(cur), mlab(prv), mlab(yag), 'm/m', 'y/y', '3Y %ile'],
        'sep': 3,
        'rows': sum_rows,
        'note': 'Per GS convention: flow items (NNA) show an absolute change rather than a '
                'percentage, and are read through the annualised organic growth line. '
                + QNOTE + '. 3Y %ile = 当月读数在最近 36 个月里高于多少百分比的观测，'
                '判据与全站其余 13 页共用一份实现（<code>build/pctile.py</code>）：'
                '把这一列在过去 24 个月里逐月回放一遍，若 ≥ 70% 的月份分位都钉在极值'
                '（100 或 0），这一列对该行就没有区分度，留空。'
                + (f'本期留空：{_bl}。它们的强弱读 m/m 与 y/y。' if _bl else '本期没有留空的行。'),
    }

    # ── 末尾核对表（官方原始单位，未换算）──
    T13 = df.iloc[-13:]
    tcols = [['Total client assets ($bn)', 'tot'], ['Advisory ($bn)', 'adv'],
             ['Brokerage ($bn)', 'brk'], ['Total NNA ($bn)', 'nna'],
             ['Advisory NNA ($bn)', 'nnaa'], ['Brokerage NNA ($bn)', 'nnab'],
             ['Acquired NNA ($bn)', 'acq'], ['Client cash ($bn)', 'cash'],
             ['Client cash (% of assets)', 'cashp']]
    trows = []
    for p, r in T13.iterrows():
        trows.append({
            'xl': mlab(p),
            'tot': num(r['total_assets_usdbn'], 1),
            'adv': num(r['advisory_assets_usdbn'], 1),
            'brk': num(r['brokerage_assets_usdbn'], 1),
            'nna': num(r['nna_total_usdbn'], 1),
            'nnaa': num(r['nna_advisory_usdbn'], 1),
            'nnab': num(r['nna_brokerage_usdbn'], 1),
            'acq': num(r['acquired_nna'], 1),
            'cash': num(r['client_cash_usdbn'], 1),
            'cashp': num(r['cash_pct_assets'], 2, pct=True),
        })
    table = {
        'n': 20, 'title': '近 13 个月月度指标核对表（官方原始单位，未换算）',
        'idx': '月份', 'cols': tcols, 'rows': trows,
    }

    # ── 抬头 ──
    # 抬头必须**同时**报好消息与坏消息。原先这一行只写「资产 +37.8% y/y、有机增速、
    # 现金 +11.4%、Advisory 占比 +5.09pp」，四项全是顺风，而同一页的汇总表里
    # Brokerage NNA 已连续为负、现金占资产比正在刷 3 年新低 —— 读者只看抬头会得到
    # 一个与页面本身相反的印象。规矩：跨并表的同比要注明含并表，并至少带上一项逆风。
    latest = df.iloc[-1]
    tot12 = float(df['total_assets_usdbn'].iloc[-13])
    y_tot = (float(latest['total_assets_usdbn']) / tot12 - 1) * 100
    # 并表口径：把窗口内（近 12 个月）已披露的 Acquired NNA 从当期资产里剔掉再比一次
    acq12 = float(df['acquired_nna'].iloc[-12:].sum())
    y_tot_ex = (float(latest['total_assets_usdbn']) - acq12) / tot12 * 100 - 100
    y_cash = (float(latest['client_cash_usdbn']) / float(df['client_cash_usdbn'].iloc[-13]) - 1) * 100
    m_cash = (float(latest['client_cash_usdbn']) / float(df['client_cash_usdbn'].iloc[-2]) - 1) * 100
    d_adv = float(latest['pct_advisory']) - float(df['pct_advisory'].iloc[-13])
    d_cashp = (float(latest['cash_pct_assets'])
               - float(df['cash_pct_assets'].iloc[-13])) * 100          # bp
    # Brokerage NNA 连续为负的月数
    nneg = 0
    for v in reversed(list(df['nna_brokerage_usdbn'].values)):
        if np.isfinite(v) and v < 0:
            nneg += 1
        else:
            break
    cp36 = df['cash_pct_assets'].iloc[-36:]
    cp_low = float(latest['cash_pct_assets']) <= float(cp36.min()) + 1e-9
    og_now = float(latest['organic_growth_ex'])
    og_avg = float(df['organic_growth_ex'].iloc[-13:-1].mean())
    # 并表只在它仍落在同比比较窗口（近 12 个月）里时才需要在抬头点名；
    # 滚出窗口之后再写「含 Commonwealth 并表」就成了假话。
    acq_in12 = [f'{p.strftime("%b-%y")} {lab} 并表 ${ACQ.get(str(p), 0):,.1f}bn'
                for p, lab in ACQ_BREAKS if p in df.index[-12:]]
    acq_txt = ('，含 ' + '、'.join(acq_in12) + '；'
               f"剔除近 12 个月已披露的并购导入约 {pm(y_tot_ex, 1, '%')}"
               if acq_in12 and acq12 > 0 else '')
    headline = (f"客户资产 ${float(latest['total_assets_usdbn']):,.1f}bn"
                f"（{pm(y_tot, 1, '%')} y/y{acq_txt}）"
                f" · 总 NNA ${float(latest['nna_total_usdbn']):,.1f}bn，"
                f"有机 ${float(latest['nna_ex']):,.1f}bn"
                f"（年化有机增速 {og_now:.1f}%，前 12 个月均值 {og_avg:.1f}%）"
                + ' · Brokerage NNA '
                + ('-' if float(latest['nna_brokerage_usdbn']) < 0 else '+')
                + f"${abs(float(latest['nna_brokerage_usdbn'])):,.1f}bn"
                + (f"（已连续 {nneg} 个月净流出）" if nneg >= 2 else '')
                + f" · 客户现金 ${float(latest['client_cash_usdbn']):,.1f}bn"
                f"（{pm(y_cash, 1, '%')} y/y，环比 {pm(m_cash, 1, '%')}），"
                f"占资产 {float(latest['cash_pct_assets']):.2f}%（{pm(d_cashp, 0, 'bp')} y/y"
                + ('，为近 36 个月最低' if cp_low else '') + '）'
                + f" · Advisory 占比 {float(latest['pct_advisory']):.2f}%（{pm(d_adv, 2, 'pp')} y/y）")
    hub = (f"客户资产 ${float(latest['total_assets_usdbn'])/1000:.2f}tn"
           f"（{pm(y_tot, 0, '%')} y/y{'，含并表' if acq_in12 and acq12 > 0 else ''}）、"
           f"有机增速 {og_now:.1f}%、"
           f"现金占资产 {float(latest['cash_pct_assets']):.2f}%"
           + ('（3 年低位）' if cp_low else ''))

    # ── 断点说明：从「真的画出来了」的清单现算 ──────────────────────────────
    # 复查规矩：图注声称画了断点线，图上就必须真有。原先这句写死「受影响的是
    # Exhibit 2、5、6、7、8、11、12、15」，而客户现金一族（9/10/13/17）同样跨并表却
    # 一条线都没画，Atria 更是整页一条都没有 —— 说明与渲染对不上。现在名单从 DRAWN 现算。
    drawn = sorted(set(DRAWN))
    _in_win = [BRK_TXT[lab] for p, lab in ACQ_BREAKS
               if p in df.index or p.asfreq('Q') in q_sum.index]
    if drawn:
        BRK_NOTE = ('<b>⚠️ 并购断点。</b>' + '、'.join(_in_win) +
                    ' 是整体并表导入，当月既不是有机流入、并表后的存量也与左侧不可直读。'
                    '凡是画 as-reported 客户资产 / 客户现金 / 总 NNA 的图，都在该期柱的'
                    '左缘画了红色竖虚线并标出并购名：从这一期起与左侧不可比。'
                    '本期真正画出断点线的是 Exhibit ' +
                    '、'.join(str(i) for i in drawn) +
                    '（各图窗口不同，盖不到的断点自动不画，也不会在图注里声称画了）。'
                    'Exhibit 3/4/18/19 走有机口径、已按公司披露的拆分把并购导入扣除，'
                    '所以不画断点线。')
    else:
        BRK_NOTE = ('<b>并购断点。</b>' + '、'.join(_in_win) +
                    ' 两笔整体并表已全部滚出各图窗口，本期没有任何一张图需要画断点线。')

    # ── 双轴零点对齐的代价：现算「右轴跨零而左轴柱恒正」的图，不写死编号 ──
    DUAL_NEG = []
    for e_ in ex:
        rhs = e_.get('yoy') or e_.get('line')
        if not rhs or not rhs.get('values'):
            continue
        rv_ = [v for v in rhs['values'] if v is not None]
        if e_['kind'] == 'gs_bar':
            lv_ = [v for v in e_['values'] if v is not None]
        elif e_['kind'] == 'grouped_bars':
            lv_ = [v for g in e_['groups'] for v in g['values'] if v is not None]
        else:
            continue
        # 必须是**跨零**：整条右轴都在零下时引擎根本不做对齐（Exhibit 10 即如此），
        # 左轴不会被拉下去，写进来就是一句假话。
        if rv_ and lv_ and min(rv_) < 0 < max(rv_) and min(lv_) >= 0:
            DUAL_NEG.append(e_['n'])

    # ── 截轴说明：同样从「真的截了」的清单现算 ──
    if CAPPED:
        CAP_NOTE = ('<b>截轴的 ' + str(len(CAPPED)) + ' 处，一处都不删点。</b>' +
                    '、'.join(f'Exhibit {i}（{d_}）' for i, d_ in sorted(CAPPED)) +
                    '的纵轴被并表月 / 并表季单独撑爆，不截轴则其余各期全部压成贴零的一条带。'
                    '一律按本仓的规矩 7 处理：轴截住、超界的柱画到边界加断口符号、'
                    '超界的点画成空心红圈，<b>真值一律竖排标在图上</b>，'
                    '表格视图与 tooltip 里也仍是真值 —— 截的是轴，不是数据。'
                    '图右上角的红色斜体小字标明该图截过轴；离群期滚出窗口之后截轴自动撤销，'
                    '那行字与图注里的相应说明也一并消失。本站没有对数轴，也不用对数轴绕开这件事。')
    else:
        CAP_NOTE = ('<b>本期没有截轴。</b>各图窗口内都没有把其余各期压平的离群值，'
                    '所以纵轴全部按数据自然范围画；一旦再出现并表这类离群期，'
                    '会自动改为截轴 + 标出真值（规矩 7），并在图右上角标明。')

    payload = {
        'ticker': 'lpla',
        'tracker': 'LPLA Monthly Metrics Tracker',
        'title': f'LPL Financial Holdings (LPLA)：月度经营指标 — {LATEST.year} 年 {LATEST.month} 月',
        'data_through': str(LATEST),
        'through_label': f'{LATEST.year} 年 {LATEST.month} 月',
        'subtitle': ('LPL Financial 月度经营指标新闻稿 + 季报（季末月无独立月报）· '
                     f'覆盖 {df.index[0]} – {LATEST}（{len(df)} 个月）· '
                     '版式照 Goldman Sachs GIR「LPLA monthly metrics」系列'),
        'headline': headline,
        # 一行数据条给读数，brief 给「这个读数该怎么读」。序列一律传全历史：
        # 名次、「N 个月最低」、并表后经过几个月都要在全样本上算，13/25 个月窗口算不出。
        'brief': compose_brief([str(p) for p in df.index],
                               df['total_assets_usdbn'].values,
                               df['advisory_assets_usdbn'].values,
                               df['brokerage_assets_usdbn'].values,
                               df['client_cash_usdbn'].values,
                               df['cash_pct_assets'].values,
                               df['organic_growth_ex'].values,
                               df['nna_ex'].values,
                               df['nna_advisory_usdbn'].values,
                               df['nna_brokerage_usdbn'].values),
        'hub_line': hub,
        'source': SRC,
        'xlabels': XL13,
        'xlabels_long': XLALL,
        'summary': summary,
        'exhibits': ex,
        'table': table,
        'notes': [
            '<b>数据源。</b>全部数值来自 <code>series/lpla.csv</code>（LPL Financial IR 月度经营指标'
            f'新闻稿，{df.index[0]} 起逐月连续）与 <code>series/fee_rates.csv</code>（LPLA 季度净收益率与'
            '季度实际客户现金收入）。页面不做任何计算，所有口径判断与格式化都在 '
            '<code>build/lpla.py</code> 里完成。'
            f'两份源的更新节奏不同：月度序列到 {mlab(LATEST)}，净收益率到 {RQ_LAST}、'
            f'季度实际客户现金收入到 {act_q.index[-1]}。费率按季度披露而月度数字每月往前走，'
            '所以某个月所属季度尚未披露费率时，该月的隐含值沿用上一可得季度的费率；'
            + (f'本期近 {WIN_L} 个月窗口里有 {len(CARRY_M)} 个月是这样算的。' if CARRY_M
               else f'本期近 {WIN_L} 个月窗口里没有这样的月份。')
            + '逐图的期间说明见 Exhibit 13 / 14 图下的「费率期间」一行。',
            '<b>季末月口径。</b>' + QNOTE + '（3/6/9/12 月无独立月报，取自当季季报），'
            '因此这几个月的披露时点与其余月份不同，但口径一致。',
            BRK_NOTE,
            '<b>有机口径与 Acquired NNA。</b>Exhibit 3/4/18/19 用的是有机 NNA = 总 NNA − '
            '公司同页披露的 Acquired NNA。该拆分自 2022 年起完整（Atria Oct-24 $88.3bn、'
            'Commonwealth Aug-25 $275.0bn 等），更早年份原件用旧行名、未解析，故未调整 —— '
            '2021 年 4 月 Waddell &amp; Reed 导入的 $73.8bn 仍留在有机序列里，'
            f'Exhibit 18 该月因此高达 {y18_max:.1f}%，纵轴已截在 {ex18_cap:.0f}% 并把真值标出。'
            '这张 Acquired NNA 常量表随原 deck 一并移植，'
            '不是 <code>series/lpla.csv</code> 的一列，与 <code>build/wealth.py</code> 里的'
            '同名表逐条一致（改一处必须改另一处）。',
            CAP_NOTE,
            '<b>GS 规矩 1：流量不算百分比。</b>NNA 是流量，月度环比/同比百分比没有经济含义，'
            '汇总表里给的是绝对变化（$bn），趋势请读「年化有机增长率」= 当月 NNA × 12 / '
            '上月末客户资产。这条规矩也决定了两张图上没有同比线：Exhibit 11（季度 NNA）'
            '撤掉了原 deck 的右轴同比，Exhibit 3（有机 NNA）保留 12 个月均线而不画同比 —— '
            '两者实算出来分别是「14 个季度里 10 个不可比」和「-88% ~ +1,600%」。',
            '<b>次轴同比取代了 12 个月均线。</b>原 deck 的 <code>gsx.lvl_bar</code> 在右轴画'
            '金色同比折线，其 docstring 写明「均线只是把柱子再平滑一遍、不带新信息，'
            '同比才回答『相对去年这个月是好是坏』」。网页版此前一律画成均线，本轮改回同比：'
            'Exhibit 2/4/9/10/12/13/15/16 现在画的是次轴 y/y（比率序列用 pp），不再画均线。'
            '副作用是双轴要对齐零点 —— 同比跨零而柱恒正时，左轴基线会被拉进负区'
            '（Exhibit 9/13/16 各浪费两三成画布），代价超过引擎阈值时改为两轴独立缩放并在'
            '绘图区左上角用红色斜体标出（本期 Exhibit 4 即如此）。'
            '只有 Exhibit 3 例外，理由见上一条与该图图注。',
            '<b>3Y %ile 的判据。</b>与全站其余各页共用同一份实现'
            '（<code>build/pctile.py</code>），本文件不再自己写一套 —— 从前各页各写各的，'
            '同一条 LPL 客户资产序列在本页被判成噪音留空、在横截面页却印成绿色 100。'
            '判据是「把这一列在过去 24 个月里逐月回放，≥70% 的月份分位钉在极值就留空」，'
            '本期留空的行与原因印在汇总表下方。',
            '<b>GS 规矩 2：比率类差异用 pp / bp。</b>% Advisory、% of client assets、'
            '年化有机增速这三行的 m/m 与 y/y 都是百分点差；绝对值小于 1pp 时改用 bp。',
            '<b>推导值必须标 Implied。</b>Exhibit 13 的月度客户现金收入 = 月末客户现金 × '
            '公司披露的季度净收益率 ÷ 12，是<b>推导值</b>；Exhibit 6 的 Market gains 是恒等式'
            '配平项（当月资产变动 − 当月 NNA），同样不是披露值。Exhibit 14 把桥算出的季度值'
            f'与公司披露的实际值并排，窗口内平均绝对误差 {mae:.1f}% —— 误差主要来自'
            '「月末余额 vs 季度平均余额」这一个近似。' + FEE_Q_NOTE,
            '<b>窗口。</b>近期柱图与双序列线图沿用原 deck 的 25 个月窗口，堆叠图与滚存桥用 13 个月，'
            '季度图用 14 个季度，长历史图用全序列。窗口一律从数据最新月倒推，不依赖构建当天的日期。'
            '断点线也随窗口现算：滚出窗口就不画，同时这段说明里的编号清单也跟着少一张，'
            '不会留下「图注说画了、图上却没有」的死文案。',
            '<b>与原 PDF 的已知差异。</b>'
            '(1) 比率图（Exhibit 10/16）原 deck 取两位小数，网页图上取一位 —— 25 根柱的'
            '两位小数标签会横向叠成一片；两位小数见这两张图的「表格」视图、汇总表与末尾核对表。'
            '(2) Exhibit 6/12/14/15 的数值标签去掉了 <code>$</code> 前缀（改用带千分位的 '
            '<code>f0c</code>）：引擎的 <code>usd0</code> 没有千分位，会把 advisory 印成 '
            '$1537；单位写在纵轴标题里。Exhibit 2/3/9/13 数值较短，仍保留 $。'
            '(3) 原 deck 长历史图末端的红色虚线圈没有网页等价元素，改由末点数值标注'
            '（Exhibit 8/17 已补上）与表格视图读数。'
            '(4) Exhibit 11 撤掉了原 deck 的右轴季度同比、Exhibit 3 保留均线不画同比'
            '（理由见 GS 规矩 1 那一条）。'
            '(5) 本引擎强制两轴零点同高，原 deck 的 matplotlib 不对齐 —— 右轴序列跨零'
            '而左轴柱恒正的图，左轴基线会被拉到零下（金额/占比本身不会为负）；'
            f'本期这样的是 Exhibit {"、".join(str(i) for i in DUAL_NEG)}，'
            '其中对齐代价超过引擎阈值的改为两轴独立缩放并在绘图区左上角红字标出。'
            '(6) 原 deck 的截轴由 matplotlib 自动量程决定，网页版是显式截轴 + 标出真值，'
            + (f'本期共 {len(CAPPED)} 张（清单见上文「截轴」那一条）。' if CAPPED
               else '本期没有一张需要截轴。'),
            '<b>两处已知的渲染瑕疵（引擎层，非本页数据）。</b>'
            '(1) 红色断点竖虚线画在所有系列之上（这是刻意的，否则会被柱子盖住），'
            '于是紧贴断点左侧那根柱的数值标签会被削掉一个角，例如 Exhibit 2 的「$1.94」、'
            'Exhibit 12 的「1,077」—— 真值可在该图的「表格」视图里读到。'
            '(2) 逐柱数值标签在 25 根柱下会互相压住，引擎按实测 bbox 抽稀（通常隔一根标一次，'
            '最新一期永远保留），被抽掉的数值同样在「表格」视图里一个不少。',
            '<b>核对表。</b>末尾 Exhibit 20 是官方原始单位、未做任何换算的近 13 个月明细，'
            '用来与 LPL 新闻稿逐条对账。每张图右上角的「表格」按钮同样给出该图的源数值。',
        ],
        'footer': ('数据与算法源自本机 <code>monthly-op-dashboards</code> 项目 · '
                   '仅供个人研究，不构成投资建议'),
    }

    # 官方发布日：查到才写这个字段。写 None 或空串都会让抬头印出「官方发布于 」这半句空话——
    # assets/page.js 判的是字段在不在，不是值真不真。
    src_day = source_day(LATEST)
    if src_day:
        payload['source_date'] = src_day

    path = os.path.join(ROOT, 'data', 'lpla.js')
    # 写出前先过 CONTRACT §5.5 护栏（NaN/Infinity 一律拒写）；首行注释与序列化都在里面。
    payload_guard.write_dash(path, payload, 'lpla')

    print(f'数据截至 {LATEST} | 25 个月窗口 {W25.index[0]} → {W25.index[-1]} | '
          f'长历史 {df.index[0]} → {df.index[-1]}（{len(df)} 个月）')
    print(f'Exhibit 1 汇总表 + Exhibit {ex[0]["n"]}-{ex[-1]["n"]}（{len(ex)} 张图）+ '
          f'Exhibit {table["n"]} 核对表')
    print(f'桥验证：{len(qs)} 个完整季度，平均绝对误差 {mae:.2f}%')
    print(f'写出 data/lpla.js ({os.path.getsize(path)/1024:.1f} KB)')
    print(headline)


if __name__ == '__main__':
    main()
