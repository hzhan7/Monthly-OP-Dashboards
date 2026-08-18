# -*- coding: utf-8 -*-
"""American Express (AXP) 月度信贷经营指标 —— 网页看板数据生成器。

把 build/build_axp.py（matplotlib / JPM「Managed Data Release」版式 PDF）里的每一张
exhibit 逐张移植成 payload 对象，写出 data/axp.js。图的顺序、编号、标题文案、图注、
窗口长度、口径断点全部照搬原 deck；数值一律在本文件算好并格式化成字符串，页面不做计算。

⚠️ 口径断点：AXP 自 2026 年 5 月起把 Card Member loans 与 receivables 合并披露为
   "Card balances"（含 pay-in-full 余额），并在 2026-05-15 的 8-K Exhibit 99.1 里
   重述了 24 个月历史。两套口径不可直接连比。PDF 分两页呈现，网页版没有分页概念，
   改用标题里的板块小标题 + Exhibit 分组表达：
     【新口径 · Card balances】  Exhibit 2-7    2024-05 起（重述历史 + 最新申报）
     【Lending Trust · 10-D】    Exhibit 8-11   2023-07 起（与 8-K 同日报送）
     【旧口径 · loans only】     Exhibit 12-18  2016-01 → 2026-03，只用于长历史与季节性

数据源（只读 series/*.csv，不碰 build/data/）：
    series/axp_newbasis.csv          新合并口径月度信贷指标
    series/axp_8k_card_balances.csv  8-K 原表（含平均余额与 total HFI）
    series/axp_trust.csv             Master Trust 月度 10-D 摘要
    series/axp_trust_full.csv        10-D 全字段（只取 filing_date 当发布日）
    series/axp.csv                   旧 loans-only 口径长历史
    series/fee_rates.csv             季度 net interest yield（新口径）

用法：python3 build/axp.py
"""
import datetime
import json
import os
import re

import numpy as np
import pandas as pd

import axisfmt
import brief as B
import payload_guard
import pctile
import yoy as Y        # 同比口径的唯一实现（build/yoy.py）；kind 必填，传错会抛而不是静默给错数

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SERIES = os.path.join(ROOT, 'series')

MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
          'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

# ── 原 deck 逐字照搬的口径文案 ──
SRC_N = 'AXP 8-K Item 7.01, combined Card balances basis; format after J.P. Morgan'
SRC_O = 'AXP 8-K Item 7.01, Card Member loans basis; format after J.P. Morgan'
BASIS_N = 'Combined Card balances basis (loans + receivables), effective May-2026'
BASIS_O = 'Card Member loans only (pre-2026 basis) — not comparable to the new-basis exhibits above'
# ── 出售已核销余额的一次性影响 ──
# 月份与量级都写成常量而不是散在文案里：窗口一滚动，「末点」「最新月」这类说法就会
# 指到别的月份上去（下个月 LATEST 变成 Jul-26，而这件事仍然只发生在 Jun-26）。
# 所有引用一律用 mlab(ONEOFF_M)，headline 的 underlying 调整也只在 CUR == ONEOFF_M 时才做。
ONEOFF_M = pd.Period('2026-06', 'M')
ONEOFF_C, ONEOFF_S = 0.3, 0.1          # 公司披露的量级（pp）：Consumer / Small Business
JUN_NOTE = (f'{ONEOFF_M.strftime("%b-%y")} write-off rate cut ~{ONEOFF_C:.1f}pp (Consumer) / '
            f'~{ONEOFF_S:.1f}pp (SBS) by a sale of written-off balances')
TRUST_SRC = ('American Express Credit Account Master Trust monthly Form 10-D '
             '(SEC CIK 0001003509)')
TRUST_NOTE = 'Trust pool = revolve-eligible balances only, so its rates sit below the 8-K rates'

SEC_A = '【新口径 · Card balances】'
SEC_T = '【Lending Trust · Form 10-D】'
SEC_O = '【旧口径 · Card Member loans only】'


# ────────────────────────────── 读数 ──────────────────────────────
def load(name):
    d = pd.read_csv(os.path.join(SERIES, name))
    d['month'] = pd.PeriodIndex(d['month'], freq='M')
    return d.set_index('month').sort_index()


def need(df, cols, who):
    miss = [c for c in cols if c not in df.columns]
    if miss:
        raise SystemExit(f'{who} 缺列 {miss} —— 拒绝静默出图')


new = load('axp_newbasis.csv')
avgbal = load('axp_8k_card_balances.csv')
trust = load('axp_trust.csv')
old = load('axp.csv').loc[:pd.Period('2026-03', 'M')]

need(new, ['consumer_balance_usdbn', 'consumer_dq30_pct', 'consumer_nco_pct',
           'sbs_balance_usdbn', 'sbs_dq30_pct', 'sbs_nco_pct'], 'axp_newbasis.csv')
need(avgbal, ['consumer_avg_bal_usdbn', 'smb_avg_bal_usdbn', 'total_hfi_usdbn'],
     'axp_8k_card_balances.csv')
need(trust, ['payment_rate_pct', 'portfolio_yield_pct', 'excess_spread_pct',
             'principal_receivables_usdbn', 'dq30_pct', 'nco_pct'], 'axp_trust.csv')
need(old, ['consumer_balance_usdbn', 'consumer_nco_pct', 'consumer_dq30_pct',
           'sbs_nco_pct'], 'axp.csv')

# 季度 net interest yield（新口径）→ 月度：当季各月用该季值，最新季之后沿用
_rates = pd.read_csv(os.path.join(SERIES, 'fee_rates.csv'))
_r = _rates[(_rates['company'] == 'AXP') & (_rates['metric'] == 'net_interest_yield_newbasis')]
if not len(_r):
    raise SystemExit('fee_rates.csv 里没有 AXP/net_interest_yield_newbasis')
_niy = (_r.assign(q=pd.PeriodIndex(_r['period'].str.replace('-', ''), freq='Q'))
          .set_index('q')['value'].astype(float).sort_index())
_q = pd.PeriodIndex(avgbal.index).asfreq('Q')
avgbal['niy'] = pd.Series([_niy.get(qq, np.nan) for qq in _q],
                          index=avgbal.index, dtype=float).ffill()
avgbal['us_avg_bal'] = avgbal['consumer_avg_bal_usdbn'] + avgbal['smb_avg_bal_usdbn']
avgbal['implied_nii_usdmn'] = avgbal['us_avg_bal'] * 1000.0 * avgbal['niy'] / 100.0 / 12.0

NII_NOTE = ('Assumption: monthly NII = average U.S. Consumer + Small Business card balances '
            f'x the disclosed net interest yield / 12 ({_niy.index[-1]} = {_niy.iloc[-1]:.1f}%, '
            'held flat after). The yield is company-wide but the balances are U.S. card only.')

trust = trust.join(new[['consumer_nco_pct', 'consumer_dq30_pct']], how='left')

new['total_balance'] = new['consumer_balance_usdbn'] + new['sbs_balance_usdbn']
old['total_balance'] = old['consumer_balance_usdbn'] + old['sbs_balance_usdbn']

LATEST = new.index[-1]
if trust.index[-1] != LATEST:
    raise SystemExit(f'8-K 最新月 {LATEST} 与 Trust 最新月 {trust.index[-1]} 不一致')
if old.index[-1] != pd.Period('2026-03', 'M'):
    raise SystemExit(f'旧口径序列末月应为 2026-03，实际 {old.index[-1]}')

# 逐月连续性护栏：断档会让 y/y 与同月均值整体错位
for df, who in ((new, 'axp_newbasis.csv'), (trust, 'axp_trust.csv'), (old, 'axp.csv')):
    d = np.diff(np.array([p.ordinal for p in df.index]))
    if len(d) and (d != 1).any():
        raise SystemExit(f'{who} 月份不连续')

# 发布日：10-D 的 filing_date（8-K 与 10-D 近 31 期 31/31 同日报送）
_tf = pd.read_csv(os.path.join(SERIES, 'axp_trust_full.csv'))
_tf['month'] = pd.PeriodIndex(_tf['month'], freq='M')
_fd = _tf.set_index('month')['filing_date']
SOURCE_DATE = str(_fd.get(LATEST, '')) or None

# 10-D 全字段，按 axp_trust.csv 的月份对齐（两者起点不同：full 从 2023-01，摘要从 2023-07，
# 排名口径必须与摘要表同一个窗口，否则「36 个月里第几低」会和汇总表那一列各说各话）。
# 这张表才有违约率的**分解**：ann_default_rate_pct（毛）− ann_recovery_rate_pct（回收）
# = ann_default_rate_net_pct（净，等于摘要表的 nco_pct）。brief 的 Trust 那句要用它。
tfull = _tf.set_index('month').sort_index().reindex(trust.index)
need(tfull, ['days_in_period', 'ann_default_rate_pct', 'ann_recovery_rate_pct',
             'ann_default_rate_net_pct', 'recoveries_usd', 'defaulted_amount_usd'],
     'axp_trust_full.csv')


# ────────────────────────────── 小工具 ──────────────────────────────
def mlab(p):
    return p.strftime('%b-%y')


def xl(idx):
    return [mlab(p) for p in idx]


def L(a):
    """序列 → JSON 数组，NaN 写 null（缺口不连线，规矩 3）。"""
    return [None if v is None or not np.isfinite(float(v)) else round(float(v), 6) for v in a]


def lvl_yoy(s, pct_series=False):
    """gsx.lvl_bar 的次轴**单月同比**：比率序列取百分点差，水平值取百分比变化。

    算式本身走 <build/yoy.py>（全站唯一一份实现），本函数只做两件本页特有的事：

      1. **kind 的选择**。`yoy.py` 的 kind 是必填参数，就是为了逼调用点把
         「这条序列是流量、存量还是比率」写出来而不是默认掉。本页的 `pct_series`
         正是这个判断：True → RATIO（同比出百分点差，而不是「百分比的百分比变化」），
         False → STOCK。**本页所有非比率的 gs_bar 画的都是月末余额与月度隐含收入**，
         这里统一传 STOCK 是安全的一侧：STOCK 与 FLOW 的 `mom_yoy` 结果逐位相同
         （两者都是 a/b−1），差别只在 STOCK 不许再往下调 `ttm()` —— 传错方向会抛，
         传对方向不会静默给错数。
      2. **近零基数保护**（基期 < 本序列 |值| 中位数 × 0.15 时留空）。这一层 yoy.py
         做成了独立的 `near_zero_base()` 诊断而不是塞进 mom_yoy，因为它是「要不要画
         这条线」的判断、不是同比的定义。本页保留逐点过滤（原 gsx 行为），
         阈值 0.15 与 yoy.NEAR_ZERO_BASE_FRAC 同源，不再写第二个常数。
    """
    v = Y._as_series(s)
    out = Y.mom_yoy(v, Y.RATIO if pct_series else Y.STOCK)
    if not pct_series:
        scale = float(np.nanmedian(np.abs(v.values.astype(float)))) or 1.0
        out = out.mask(v.shift(Y.LAG).abs() < Y.NEAR_ZERO_BASE_FRAC * scale)
    return pd.Series(out.values, index=s.index)


def plain_yoy(s):
    """gsx.rev_bar_yoy 用的 _yoy：不做近零基数保护，只要两期都在就算。

    与 `lvl_yoy` 的差别只有那一层保护，算式同样走 yoy.mom_yoy —— 本页两个同比
    口径的定义因此只有一处，不会出现「同一条余额序列在 Exhibit 2 和 Exhibit 12
    算出两个数」。"""
    return pd.Series(Y.mom_yoy(Y._as_series(s), Y.STOCK).values, index=s.index)


def tail_contiguous(s):
    """gsx._tail_contiguous：先 dropna，再只留末尾逐月连续的一段。"""
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


ALIGN_WASTE_MAX = 0.38      # 与 assets/charts.js 的 ALIGN_WASTE_MAX 同值


def align_sim(ex):
    """复算引擎「两轴零点画在同一高度」之后，这张图的左轴与浪费掉的画布比例。

    返回 dict（单轴图或右轴无值返回 None）：
      lo/hi     引擎**实际**用的左轴上下界
      alo/ahi   假如对齐，左轴会被扩到哪（不对齐分支下就是「代价有多大」的具体数）
      waste     对齐要浪费掉的量程比例
      aligned   引擎最终有没有对齐（waste > ALIGN_WASTE_MAX 就不对齐并在图上标红字）

    为什么要在生成端复算：图注里「零点不同高 / 左轴会被扩到 −25%、四成画布是空的」
    是一句**关于渲染结果的声称**，而那两个数随每月新数据变；更要命的是
    「对齐还是不对齐」这个结论本身由浪费比例与 38% 阈值的大小关系决定 ——
    数变了而话不变，就会出现「图注说零点不同高、图上其实已经对齐」。
    本仓规矩也是「一个数字都不许写死在文案里」。

    零件全部来自 build/axisfmt.py（引擎量程/刻度算法的 Python 复算），
    这里只把 charts.js:690 起那段对齐分支按同一顺序走一遍，不另写算法。
    ⚠️ 本函数与 build/tsm.py 里的同名函数逐字相同 —— 它该住在 axisfmt.py 里供全站共用，
    但那个文件本轮不归本任务改，所以先各放一份，注释互相点名以免日后只改一处。
    """
    rng = axisfmt._left_range(ex)
    rc = axisfmt._rhs(ex)
    k = ex.get('kind')
    dual = k in ('bar_line_dual', 'stacked_dual') or \
        (k in ('qtr_bar', 'grouped_bars', 'gs_bar') and rc is not None)
    if rng is None or not (dual and rc):
        return None
    y0, y1 = rng
    rv = axisfmt._fin(rc.get('values'))
    if not rv:
        return None
    rtk = axisfmt.ticks(min(rv + [0.0]), max(rv), 9)
    r0, r1 = rtk[0], rtk[-1]
    f = max(axisfmt._zero_frac(y0, y1), axisfmt._zero_frac(r0, r1))
    if f <= 1e-9:                      # 两轴都不含负值：零点本来就同高，没有代价
        return {'lo': y0, 'hi': y1, 'alo': y0, 'ahi': y1, 'waste': 0.0, 'aligned': False}
    la0, la1 = axisfmt._align_zero(y0, y1, f)
    ra0, ra1 = axisfmt._align_zero(r0, r1, f)
    w1 = 1 - (y1 - y0) / (la1 - la0) if (la1 - la0) else float('nan')
    w2 = 1 - (r1 - r0) / (ra1 - ra0) if (ra1 - ra0) else float('nan')
    waste = max(w1, w2)
    ok = not (waste > ALIGN_WASTE_MAX)     # 超阈值 → 引擎改为不对齐并在图上标红字
    return {'lo': la0 if ok else y0, 'hi': la1 if ok else y1,
            'alo': la0, 'ahi': la1, 'waste': waste, 'aligned': ok}


def pp_unit(y_vals):
    """比率序列的同比该用 pp 还是 bp —— 由**刻度印不印得出来**决定，不靠手感。

    返回 (倍数, 单位字, 次轴格式器)：`(1.0, 'pp', 'pp1')` 或 `(100.0, 'bp', 'f0')`。

    为什么这件事必须在生成端解决、而不是交给 build/axisfmt.py：
    引擎的格式器表（assets/charts.js:88）里 pp 只有 `pp0` / `pp1` 两档，**没有 pp2**；
    axisfmt 只能在同族里往上升小数位，升到 pp1 就到顶，再细的步长它救不了。
    实测 Exhibit 8 的同比落在 −0.97pp ~ +1.14pp，引擎算出的步长是 **0.25pp**，
    `toFixed(1)` 把这列刻度印成 −1.0 / −0.8 / −0.5 / −0.2 / +0.0 / +0.2 / +0.5 / +0.8 /
    +1.0 / +1.2 —— 网格线是等距的，标签的差却在 0.2 与 0.3 之间来回跳，
    读者按标签量线会系统性偏半档（visual_qa 实测像素-数值比偏 33.3%，判 🔴）。
    不这么做的两条替代路都更差：改 assets/charts.js 要把 27 张已验收的页全部重验；
    放着不管就是发布一张刻度写着错值的图。

    换成 bp（×100）之后同一批刻度变成 −100 / −75 / … / +125，`f0` 一位不差地印得出来。
    这也正是本仓的单位规矩（占比变化 |v| < 1pp 用 bp）——本图窗口内多数月份的同比
    绝对值不到 1pp，抬头那行印的本来就是 bp（「Trust 超额利差 …（+86bp y/y）」），
    换过来之后轴与抬头终于说的是同一种单位。

    判据直接借 axisfmt 的 `_need_dec`，不另写一份：同一件事各写各的判据，
    正是同一条序列在两处得出相反结论的根因。
    ⚠️ 这里量的是**对齐零点之前**的刻度。引擎在两轴零点对齐时只会把量程往外扩
    （步长只会变粗、不会更细），所以这个判据是保守方向的：最坏情况是本来 pp 也够用
    却换成了 bp —— 那不是错误，只是选了本仓更偏好的那个单位。
    """
    vals = [float(v) for v in y_vals if v is not None and np.isfinite(v)]
    if not vals:
        return 1.0, 'pp', 'pp1'
    tk = axisfmt.ticks(min(vals + [0.0]), max(vals), 9)
    if axisfmt._need_dec(tk, tk[0], tk[-1]) <= 1:      # pp1 印得出来就不动
        return 1.0, 'pp', 'pp1'
    return 100.0, 'bp', 'f0'


def gs_bar_ex(n, ttl, s_full, *, win, yfmt, fmt, ylab, pct_series=False,
              legend='Monthly', ylab2=None, yoy_yfmt=None, no_yoy=False,
              note=None, src_extra=None):
    """gsx.lvl_bar → 网页 gs_bar + 次轴 y/y（engine_kinds.md §8 的 `yoy` 开关）。

    deck 的 lvl_bar 画的是「浅蓝柱 + **每根柱的数值标签** + 次轴金色 y/y 折线」，
    docstring 明写次轴那条是同比不是滚动均线（「均线只是把柱子再平滑一遍、不带新信息」）。
    给了 `yoy` 字段，引擎就画同比折线并**不画 12 个月均线**，与 deck 一致；
    hkex / cboe / cme 三页的 lvl_bar 图已是这个写法，本页照同一规矩。

    换掉原来的 bar_line_dual 是因为它丢了「每柱数值标签」这一层 —— 而本页有两张图
    （Ex7 费率 7.8–8.4%、Ex8 超额利差 24.1–26.1%）的全部信息就在那一层：
    柱从 0 起是比率的正确基线，可 0 基线上这点差异肉眼分不出来，只有柱顶数字读得出。
    标签密度由引擎的 thinLabels() 按实测 bbox 抽稀，25 根柱不会叠字。

    `no_yoy=True` 是**唯一**的例外口子，只给「同比在整个窗口内是常数」的序列用：
    常数同比等于零信息，而且任何画法都会退化 —— 次轴量程塌成一个点，刻度四舍五入成
    一列重复读数，末点读数又必然落在轴的最大刻度上（末点值 = 轴最大值），
    于是右上角出现两个一模一样的数字。这种图改回 12 个月均线（对费率而言
    「当前 vs 过去一年均值」是真参考），同比的那个常数写进图注。
    """
    s = tail_contiguous(s_full)
    y = lvl_yoy(s, pct_series).iloc[-win:]
    d = s.iloc[-win:]
    ex = {
        'n': n, 'kind': 'gs_bar', 'title': ttl,
        'xlabels': xl(d.index), 'xrot': 90,
        'ylab': ylab, 'legend': legend, 'fmt': fmt, 'yfmt': yfmt,
        'values': L(d.values),
    }
    if no_yoy:
        # Prior 12mo Avg. = 最新月之前的 12 个月均值（与 cboe.prior12 同口径）
        ex['avg12'] = round(float(np.nanmean(np.asarray(d.values, float)[-13:-1])), 6)
    elif pct_series and yoy_yfmt is None:
        # 比率序列的同比：单位（pp / bp）由 pp_unit() 按「刻度印不印得出来」定，见该函数。
        mult, unit, yfm = pp_unit(y.values)
        ex['ylab2'] = ylab2 or f'y/y ({unit})'
        ex['yoy'] = {'name': f'y/y ({unit}, RHS)', 'color': 'GOLD', 'yfmt': yfm,
                     'values': L(y.values * mult)}
    else:
        ex['ylab2'] = ylab2 or ('y/y (pp)' if pct_series else '% y/y')
        ex['yoy'] = {'name': ('y/y (pp, RHS)' if pct_series else 'y/y (RHS)'), 'color': 'GOLD',
                     'yfmt': yoy_yfmt or ('pp1' if pct_series else 'pct0'),
                     'values': L(y.values)}
    if note:
        ex['note'] = note
    if src_extra:
        ex['src_extra'] = src_extra
    return ex


def yoy_step_note(s_full, *, win, min_pp=4.0):
    """同比线在窗口内有没有一处「断崖」；有就给一句解释，没有返回 None。

    图上一条近乎垂直的同比线在旁边那张平滑的同类图对照下，第一眼就像算错了。
    这里不写死月份 —— 窗口每月滚动，写死的说明迟早指到别的月上去。
    """
    s = tail_contiguous(s_full)
    y = lvl_yoy(s).iloc[-win:]
    d = s.iloc[-win:]
    v, idx = y.values, list(y.index)
    best, j = 0.0, None
    for i in range(1, len(v)):
        if np.isfinite(v[i]) and np.isfinite(v[i - 1]) and abs(v[i] - v[i - 1]) > best:
            best, j = abs(v[i] - v[i - 1]), i
    if j is None or best < min_pp:
        return None
    cur, prv = idx[j], idx[j - 1]
    lvl_now, lvl_prv = float(d.get(cur, np.nan)), float(d.get(prv, np.nan))
    base_now, base_prv = float(s.get(cur - 12, np.nan)), float(s.get(prv - 12, np.nan))
    return (f'同比线在 {mlab(cur)} 有一处断崖（{mlab(prv)} {v[j - 1]:+.1f}% → '
            f'{mlab(cur)} {v[j]:+.1f}%，一个月里掉了 {best:.1f}pp），是真数据不是算错：'
            f'当月水平从 {lvl_prv:,.1f} 走到 {lvl_now:,.1f}（{(lvl_now / lvl_prv - 1) * 100:+.1f}% m/m），'
            f'而去年同期的基数从 {base_prv:,.1f} 抬到 {base_now:,.1f}'
            f'（{(base_now / base_prv - 1) * 100:+.1f}%），两头反向叠加。'
            f'断崖两侧的柱本身是连续可比的，只有那条同比线跨过了这个基数台阶。')


def bar_yoy_ex(n, ttl, s_full, *, win, yfmt, ylab, pct_series=False,
               bar_color='BLUE', bar_name='Monthly', note=None, src_extra=None,
               xstep=None):
    """gsx.rev_bar_yoy → 网页 bar_line_dual（深色柱 + 右轴 y/y 线）。

    只剩 Exhibit 12 在用。rev_bar_yoy 的柱是深色 NAVY（图例写 "Reported"），
    而 gs_bar 的柱色写死在引擎里的浅蓝 C.BLUE，换过去会把「已公布 vs 预测」的
    深浅语义弄丢；42 根柱上逐柱标数值在 deck 里也是竖排的，gs_bar 只有横排。
    lvl_bar 那五张已改走 gs_bar_ex。
    """
    s = tail_contiguous(s_full)
    y = (lvl_yoy(s, pct_series) if bar_color == 'BLUE' else plain_yoy(s)).iloc[-win:]
    d = s.iloc[-win:]
    ex = {
        'n': n, 'kind': 'bar_line_dual', 'title': ttl,
        'xlabels': xl(d.index), 'xrot': 90,
        'ylab': ylab, 'ylab2': ('y/y (pp)' if pct_series else 'y/y (%)'),
        'bar': {'name': bar_name, 'color': bar_color, 'values': L(d.values), 'yfmt': yfmt},
        'line': {'name': ('y/y (pp, RHS)' if pct_series else 'y/y (RHS)'), 'color': 'GREEN',
                 'values': L(y.values), 'yfmt': ('pp1' if pct_series else 'pct0')},
    }
    if xstep:
        ex['xstep'] = xstep
    if note:
        ex['note'] = note
    if src_extra:
        ex['src_extra'] = src_extra
    return ex


def multi_line_ex(n, ttl, df, cols, colors, names, *, win, src_extra=None, note=None):
    """gsx.multi_line → 网页 lines_endlabels（多条平滑线，仅两端标数值）。"""
    d = df.iloc[-win:]
    ex = {
        'n': n, 'kind': 'lines_endlabels', 'title': ttl, 'fmt': 'pct1', 'yfmt': 'pct1',
        'xlabels': xl(d.index), 'xrot': 90, 'ylab': '%',
        'series': [{'name': nm, 'color': c, 'values': L(d[col].values)}
                   for col, c, nm in zip(cols, colors, names)],
    }
    if note:
        ex['note'] = note
    if src_extra:
        ex['src_extra'] = src_extra
    return ex


def seasonality_ex(n, ttl, s_full, *, win, years, src_extra=None):
    """gsx.seasonality → 网页 seasonality（灰=过去 N 年同月均值，蓝=实际）。"""
    s = s_full.dropna()
    d = s.iloc[-win:]
    base, used = [], []
    for p in d.index:
        prior = [s.get(p - 12 * k, np.nan) for k in range(1, years + 1)]
        prior = [v for v in prior if v is not None and np.isfinite(v)]
        used.append(len(prior))
        base.append(float(np.mean(prior)) if prior else np.nan)
    ex = {
        'n': n, 'kind': 'seasonality', 'title': ttl, 'fmt': 'pct1', 'label_fmt': 'pct1',
        'yfmt': 'pct1', 'xlabels': xl(d.index), 'xrot': 90, 'ylab': '%',
        'base': {'name': f'Prior {max(used)}yr same-month avg.', 'color': 'GRAY',
                 'values': L(base)},
        'actual': {'name': 'Actual', 'color': 'MBLUE', 'values': L(d.values)},
    }
    if src_extra:
        ex['src_extra'] = src_extra
    return ex, max(used)


def year_lines_ex(n, ttl, s_full, *, n_years, src_extra=None):
    """gsx.year_lines（cumulative=False）→ 网页 year_lines。"""
    s = s_full.dropna()
    yrs = sorted({p.year for p in s.index})[-n_years:]
    series = []
    for y in yrs:
        vals = [np.nan] * 12
        for p, v in s.items():
            if p.year == y:
                vals[p.month - 1] = v
        series.append({'name': str(y), 'values': L(vals)})
    return {
        'n': n, 'kind': 'year_lines', 'title': ttl, 'fmt': 'pct1', 'label_fmt': 'pct1',
        'yfmt': 'pct1', 'xlabels': MONTHS, 'ylab': '%', 'series': series,
        'highlight': len(series) - 1,
        'src_extra': src_extra,
    }


def heat_ex(n, ttl, s_full, *, n_years, src_extra=None):
    """gsx.heat_matrix（reverse=True：低核销率=绿）→ 网页 heat_matrix。"""
    s = s_full.dropna()
    yrs = sorted({p.year for p in s.index})[-n_years:]
    m = [[None] * 12 for _ in yrs]
    for p, v in s.items():
        if p.year in yrs:
            m[yrs.index(p.year)][p.month - 1] = round(float(v), 6)
    return {
        'n': n, 'kind': 'heat_matrix', 'title': ttl, 'fmt': 'f1', 'reverse': True,
        'rows': [str(y) for y in yrs], 'cols': MONTHS, 'matrix': m,
        'row_head': '年', 'legend': ttl.split('】')[-1], 'cell_h': 19,
        'src_extra': src_extra,
    }


# ────────────────────────────── Exhibit 1：汇总表 ──────────────────────────────
CUR, PRV, YAG = LATEST, LATEST - 1, LATEST - 12


def fmt_val(v, dec, pct, money):
    if v is None or not np.isfinite(v):
        return '—'
    return f'{money}{v:,.{dec}f}' + ('%' if pct else '')


def _signed(v, dec, unit, money=''):
    """带符号的变化量。四舍五入到零时写「0」不带正负号。

    f-string 的 `+` 标志按**未舍入**的值定符号，所以 -0.4bp 会印成「-0bp」、
    +0.0004pp 会印成「+0.00pp」—— 读者看到的是一个不存在的方向。零就是零，不给方向。
    """
    if round(v, dec) == 0:
        return f'{money}{0:.{dec}f}{unit}'
    return f'{money}{v:+,.{dec}f}{unit}'


def fmt_chg(a, b, mode, dec, money):
    """gsx.summary_table 的变化率口径：比率类一律 pp/bp，|差| < 1 用 bp。"""
    if not (np.isfinite(a) and np.isfinite(b)):
        return None
    if mode == 'pp':
        v = a - b
        return _signed(v * 100, 0, 'bp') if abs(v) < 1 else _signed(v, 2, 'pp')
    if mode == 'abs':
        return _signed(a - b, max(0, dec), '', money)
    if b == 0 or a * b < 0:
        return None
    return _signed((a / b - 1) * 100, 1, '%')


def chg_good(a, b, mode, inv):
    """返回 True=好 / False=坏 / None=不着色。
    gsx 把「零变化」着成红色（good = v > 0 为假），那是在说「没变 = 变坏」，
    这里改成中性 —— 口径判断在 Python 侧做完，页面不猜。"""
    if not (np.isfinite(a) and np.isfinite(b)):
        return None
    v = (a - b) if mode in ('pp', 'abs') else ((a / b - 1) if b and a * b > 0 else np.nan)
    if not np.isfinite(v) or v == 0:
        return None
    return (v < 0) if inv else (v > 0)


# 分位一列不再在本文件里自己算：判据是口径，口径只能有一处定义（见 build/pctile.py 的
# 模块 docstring —— 同一条序列在两页被判成相反结果，根因就是各写各的）。
# 本文件只负责把序列递进去、把 (显示串, 颜色类) 放进 cell，以及把 why_blank() 写进表注。


SUM_ROWS = [
    ('U.S. Consumer Card', None, None, None, None, None, None),
    (new, 'Total Card balances ($bn)', 'consumer_balance_usdbn', 1, False, '$', False),
    (new, '30+ days past due (%)', 'consumer_dq30_pct', 2, True, '', True),
    (new, 'Net write-off rate, principal (%)', 'consumer_nco_pct', 2, True, '', True),
    ('U.S. Small Business Card', None, None, None, None, None, None),
    (new, 'Total Card balances ($bn)', 'sbs_balance_usdbn', 1, False, '$', False),
    (new, '30+ days past due (%)', 'sbs_dq30_pct', 2, True, '', True),
    (new, 'Net write-off rate, principal (%)', 'sbs_nco_pct', 2, True, '', True),
    ('Combined', None, None, None, None, None, None),
    (new, 'Card balances held for investment ($bn)', 'total_balance', 1, False, '$', False),
    ('Trust performance (%, monthly)', None, None, None, None, None, None),
    (trust, 'Portfolio yield', 'portfolio_yield_pct', 2, True, '', False),
    (trust, 'Payment rate', 'payment_rate_pct', 2, True, '', False),
    (trust, 'Excess spread', 'excess_spread_pct', 2, True, '', False),
    (trust, 'Annualised default rate, net of recoveries', 'nco_pct', 2, True, '', True),
    (trust, 'Total 30+ day delinquency', 'dq30_pct', 2, True, '', True),
    ('Pool size', None, None, None, None, None, None),
    (trust, 'Principal receivables ($bn)', 'principal_receivables_usdbn', 2, False, '$', False),
]

srows, blanked = [], []
for src_df, lab, col, dec, pct, money, inv in SUM_ROWS:
    if lab is None:
        srows.append({'kind': 'group', 'label': src_df})
        continue
    s = src_df[col].dropna()
    g = lambda p: (float(s.get(p, np.nan)) if p in s.index else np.nan)
    c, p1, p12 = g(CUR), g(PRV), g(YAG)
    mode = 'pp' if pct else 'ratio'
    cells = [{'v': fmt_val(c, dec, pct, money), 'cls': 'cur'},
             {'v': fmt_val(p1, dec, pct, money)},
             {'v': fmt_val(p12, dec, pct, money)}]
    for b in (p1, p12):
        t = fmt_chg(c, b, mode, dec, money)
        good = chg_good(c, b, mode, inv)
        cells.append({'v': t or '', 'cls': ('' if good is None else ('pos' if good else 'neg'))})
    # 分位：唯一实现在 build/pctile.py，直接吃 (显示串, 颜色类)
    ser = [float(v) for v in s.values]
    pv, pcls = pctile.cell(ser, -1, inverse=inv)
    cells.append({'v': pv, 'cls': pcls} if pv else {'v': ''})
    if not pv:
        blanked.append((lab, pctile.why_blank(ser) or '当期读数缺失'))
    srows.append({'label': lab, 'cells': cells})

PCT_NOTE = ('3Y %ile 由 <code>build/pctile.py</code> 统一计算（全站唯一实现，各页不再各写各的）：'
            '取近 36 个月百分位；留空的判据是「把这一列在近 24 个月里逐月回放，'
            '若 ≥70% 的月份钉在 100 或 0，这一列对这一行就没有区分度」——'
            '旧判据「月环比不降的比例 ≥90%」拦不住上下波动、分位却常年钉在极值的行。')
PCT_NOTE += ('　本期留空：' + '；'.join(f'{l}（{w}）' for l, w in blanked) + '。'
             if blanked else '　本期没有任何一行触发该规则。')

summary = {
    'title': f'AXP monthly credit metrics — {mlab(LATEST)}'
             f'（原 deck 的 Exhibit 1 与 Exhibit 8 两张汇总表合并，两者最新月同为 {mlab(LATEST)}）',
    'heads': [mlab(CUR), mlab(PRV), mlab(YAG), 'm/m', 'y/y', '3Y %ile'],
    'sep': 3,
    'rows': srows,
    'note': (BASIS_N + '.  ' + JUN_NOTE + '.  Green = improving (lower delinquency / write-off).  '
             'Trust 各行来自与 8-K 同日报送的 Form 10-D（近 31 期 31/31 同日）；'
             + TRUST_NOTE + '.  比率类指标的差异一律用 pp / bp（|差| &lt; 1pp 时写 bp）；'
             '四舍五入到零的变化写「0bp」不带正负号，零变化不着色。'
             '逾期率／核销率等反向指标按「越低越好」着色（分位低=绿）。' + PCT_NOTE +
             f'　注意新口径序列只有 {len(new)} 个月历史（{new.index[0]} 起），'
             f'其分位实际是在 {len(new)} 个月内取的；Trust 行才是满 36 个月。'),
}


# ──────────────────── 费率期间披露（Exhibit 6 / 7 用）────────────────────
# 月度余额每月往前走，净利息收益率却按季度披露 —— 所以「最新一两个月的隐含值用的是
# 上一季的费率」是本页的**常态口径**，不是 bug。但读者有权知道是哪一季，尤其当官方
# 财报延迟、费率落后两个季度以上时。
#
# 整句一律现算：季度号写死的话下季度就变成假话（本仓踩过 schw「过去 32 个季度」、
# cost「Exhibit 4 画了红线」两次）。三个量都从数据来：
#   _Q_DATA  本页数据月所在季度
#   _Q_FEE   fee_rates.csv 里最新可得的费率季度
#   _Q_USED  最新月实际套用的那一季（ffill 后 = 不晚于 _Q_DATA 的最后一季）
# 过期判据：_Q_USED 比「_Q_DATA 的上一季」还老（即滞后 >= 2 季）时显式报警。
def _qlab(q):
    return f'{q.year}-Q{q.quarter}'


_Q_DATA = LATEST.asfreq('Q')
_Q_FEE = _niy.index[-1]
_Q_USED = max([q for q in _niy.index if q <= _Q_DATA], default=_Q_FEE)
_V_USED = float(_niy.loc[_Q_USED])
_CARRY = [m for m in avgbal.index if m.asfreq('Q') > _Q_USED]
_LAG = (_Q_DATA - _Q_USED).n

FEE_PERIOD_NOTE = (
    f'<b>费率取哪一季：</b>净利息收益率是<b>季度</b>披露值，'
    f'fee_rates 里最新可得的是 {_qlab(_Q_FEE)}（{float(_niy.iloc[-1]):.1f}%）；'
    f'本页数据截至 {mlab(LATEST)}，该月的隐含值用的是 <b>{_qlab(_Q_USED)} 的 {_V_USED:.1f}%</b>。')
if _CARRY:
    FEE_PERIOD_NOTE += (
        f'{mlab(_CARRY[0])}–{mlab(_CARRY[-1])}（{len(_CARRY)} 个月）所在季度尚无披露费率，'
        f'一律沿用 {_qlab(_Q_USED)} 的值 —— 这几个月的柱高只反映余额变化，费率那一档是冻住的。')
else:
    FEE_PERIOD_NOTE += '窗口内每个月都落在已披露费率的季度内，没有月份需要沿用上一季。'
if _LAG >= 2:
    FEE_PERIOD_NOTE += (
        f'<b>⚠️ 费率已落后 {_LAG} 个季度：尚未更新至 {_qlab(_Q_DATA - 1)}'
        f'（更没有 {_qlab(_Q_DATA)}），本图仍在用 {_qlab(_Q_USED)} 的 {_V_USED:.1f}%。</b>'
        f'费率与最新月之间隔了不止一个季度，隐含值的误差会随口径漂移放大，'
        f'水平请当作粗略量级读，不要读斜率。')


# ────────────────────────────── Exhibit 2..18 ──────────────────────────────
ex = []

# ══ 板块 A：新合并口径（PDF 第 1 页，Exhibit 2-7）══
ex.append(gs_bar_ex(
    2, SEC_A + 'U.S. Consumer Card balances', new['consumer_balance_usdbn'],
    win=25, yfmt='usd0', fmt='usd1', ylab='$bn', yoy_yfmt='pct1',
    note=yoy_step_note(new['consumer_balance_usdbn'], win=25),
    src_extra=SRC_N + '.  ' + BASIS_N))

ex.append(multi_line_ex(
    3, SEC_A + 'U.S. Consumer delinquency and write-off', new,
    ['consumer_dq30_pct', 'consumer_nco_pct'], ['MBLUE', 'RED'],
    ['30+ days past due', 'Net write-off (principal)'],
    win=26, src_extra=SRC_N + '.  ' + JUN_NOTE))

ex.append(gs_bar_ex(
    4, SEC_A + 'U.S. Small Business Card balances', new['sbs_balance_usdbn'],
    win=25, yfmt='usd0', fmt='usd1', ylab='$bn', yoy_yfmt='pct1',
    note=yoy_step_note(new['sbs_balance_usdbn'], win=25),
    src_extra=SRC_N + '.  ' + BASIS_N))

ex.append(multi_line_ex(
    5, SEC_A + 'U.S. Small Business delinquency and write-off', new,
    ['sbs_dq30_pct', 'sbs_nco_pct'], ['MBLUE', 'RED'],
    ['30+ days past due', 'Net write-off (principal)'],
    win=26, src_extra=SRC_N + '.  ' + JUN_NOTE))

ex.append(gs_bar_ex(
    6, SEC_A + 'Implied U.S. card net interest income', avgbal['implied_nii_usdmn'],
    win=25, yfmt='f0c', fmt='f0c', ylab='$mn / month', yoy_yfmt='pct1',
    note=NII_NOTE + '　' + FEE_PERIOD_NOTE, src_extra=SRC_N))

# Exhibit 7：本页唯一一张**不画次轴同比**的 lvl_bar 图。费率是季度阶梯，窗口内同比
# 恒为 +0.20pp（常数），画出来的次轴必然退化：量程 0–0.2pp、刻度四舍五入成一列重复
# 读数，而末点读数又必然等于轴的最大刻度 → 右上角两个一模一样的数字。零信息 + 必然
# 退化，所以这一张退回 12 个月均线（费率的「当前 vs 过去一年均值」是真参考），
# 那个常数写进图注。理由见 gs_bar_ex 的 no_yoy 说明。
_niy_y = lvl_yoy(tail_contiguous(avgbal['niy']), True).iloc[-25:].dropna()
_niy_yy_set = sorted({round(float(v), 2) for v in _niy_y.values})
_niy_w = avgbal['niy'].dropna().iloc[-25:]
_niy_avg = float(np.nanmean(np.asarray(_niy_w.values, float)[-13:-1]))
# 常数假设不成立时**自动改回次轴同比**，不要硬失败退出。
# 这里曾经是 `raise SystemExit`，而触发条件恰恰是常态：月度数字本来就走在季度费率前面，
# 费率一落后一个季度，ffill 就把最后一档拉平、同比不再是常数 —— 那一天起 AXP 页
# 再也构建不出来，而调度器只会看到一行 FAIL。断言本身说的处置（「改回次轴同比」）
# 是对的，那就让它自己改回去，别等人来改代码。
_niy_const = len(_niy_yy_set) == 1
if _niy_const:
    _niy_note = (
        f'费率是<b>季度阶梯</b>（同一季度三个月同值），窗口内每一季都恰好比去年同季高 '
        f'{_niy_yy_set[0]:+.2f}pp —— 同比是个<b>常数</b>，不带任何信息。'
        f'其余同类图（Exhibit 2/4/6/8）都按原 deck 画次轴同比线，只有这一张不画：'
        f'常数同比会让次轴量程塌成一个点，刻度被四舍五入成一列重复读数，'
        f'末点读数又必然压在轴的最高刻度上。这里改画 12 个月均线'
        f'（{_niy_avg:.2f}%，费率看「当前 vs 过去一年均值」才有参考意义）。')
else:
    _niy_note = (
        f'费率是<b>季度阶梯</b>（同一季度三个月同值）。窗口内同比取值 '
        f'{"、".join(f"{v:+.2f}pp" for v in _niy_yy_set)} —— 不是常数，'
        f'故本图按原 deck 画次轴同比线（同比恒定时这张图会改画 12 个月均线，'
        f'因为常数同比会让次轴量程塌成一个点）。')
ex.append(gs_bar_ex(
    7, SEC_A + 'Net interest yield on card balances', avgbal['niy'],
    win=25, yfmt='pct1', fmt='pct1', ylab='% annualised', pct_series=True,
    no_yoy=_niy_const,
    note=_niy_note +
         f'柱从 0 起是费率的正确基线，但 {_niy_w.min():.1f}%–{_niy_w.max():.1f}% 的差异'
         f'在 0 基线上肉眼分不出来，<b>水平请读柱顶数值</b>。　' + FEE_PERIOD_NOTE,
    src_extra=SRC_N + '.  The disclosed company-wide yield, stepped quarterly. This is the '
              'rate the bridge above multiplies by, so it is where the bridge can go wrong.'))

# ══ 板块 B：Lending Trust 月度 10-D（PDF Exhibit 9-12；Exhibit 8 的汇总表已并入上表）══
# 本板块四张图共用一个窗口长度。图注里的「窗口内 min-max」必须跟图上真正画出来的
# 是同一批点，窗口长度与统计切片各写一个 25 迟早会分叉。
_TW = 25
_es_w = trust['excess_spread_pct'].dropna().iloc[-_TW:]
_es_y = lvl_yoy(tail_contiguous(trust['excess_spread_pct']), True).iloc[-_TW:].dropna()
# 图注里的同比读数必须跟次轴用同一个单位，所以走的是同一个 pp_unit()（同一份判据、
# 同一批输入 → 同一个答案）。写死「pp」的话，哪个月轴切到 bp 图注就开始自相矛盾。
_ES_MULT, _ES_UNIT, _ = pp_unit(_es_y.values)
_es_d = 0 if _ES_UNIT == 'bp' else 2
ex.append(gs_bar_ex(
    8, SEC_T + 'Trust excess spread', trust['excess_spread_pct'],
    win=_TW, yfmt='pct1', fmt='pct1', ylab='%', pct_series=True,
    note=f'<b>超额利差 ＝ 组合收益率 − 净核销 − 服务费 − 票息</b>，也就是信托收上来的钱付完'
         f'所有成本之后剩下的那一层，债券持有人被打到之前先由它吸收损失。这是 ABS 交易里'
         f'最被盯的一个数：跌到 0 附近会触发提前摊还（early amortization）—— 投资人本金被'
         f'提前还回，AXP 失去这条融资渠道。所以这张图是用来<b>确认没事</b>的，不是用来找信号的。　'
         f'窗口内超额利差始终在 {_es_w.min():.2f}%–{_es_w.max():.2f}% 之间（极差只有 '
         f'{_es_w.max() - _es_w.min():.2f}pp）。柱从 0 起是利差的正确基线，'
         f'在这个基线上 {len(_es_w)} 根柱的高度差不到画布的 '
         f'{(_es_w.max() - _es_w.min()) / (_es_w.max() * 1.22) * 100:.0f}%，看上去一样高 ——'
         f'<b>水平请读柱顶数值，变化请读次轴那条金色同比线</b>'
         f'（窗口内 {_es_y.min() * _ES_MULT:+.{_es_d}f}{_ES_UNIT} ~ '
         f'{_es_y.max() * _ES_MULT:+.{_es_d}f}{_ES_UNIT}，'
         f'当期 {_es_y.iloc[-1] * _ES_MULT:+.{_es_d}f}{_ES_UNIT}）。'
         f'{{ALIGN}}',
    src_extra=TRUST_SRC + '.  Portfolio yield less charge-offs, servicing and note coupon — '
              'the cushion that absorbs losses before noteholders are hit. The single '
              'most-watched number in the trust report'))

# 「两轴零点同不同高、代价多大」这句话由 align_sim 现读本图 payload，不写死。
# 原文写的是「左轴一路扩到 −25% 左右，四成画布是空的」—— 今天恰好对得上
# （实测 −25.5%、浪费 44%），但这两个数随每月新数据变，而且更要命的是
# 「对齐 / 不对齐」这个结论本身由浪费比例与引擎 38% 阈值的大小关系决定：
# 数变了而话不变，就会出现「图注说零点不同高、图上其实对齐了」。
_a8 = align_sim(ex[-1])
if _a8 is None or _a8['waste'] <= 1e-9:
    _ALIGN_TXT = '本图左右轴零点同高（柱与同比线都不跨零，本来就对得上）。'
elif _a8['aligned']:
    _ALIGN_TXT = (f'本图左右两轴的零点已被引擎拉到同一高度，代价是左轴向下扩到 '
                  f'{_a8["lo"]:.1f}%、浪费掉量程的 {_a8["waste"]:.0%}'
                  f'（低于引擎 {ALIGN_WASTE_MAX:.0%} 的兜底阈值，所以仍然对齐）。')
else:
    _ALIGN_TXT = (f'本图左右轴零点<b>不同高</b>（引擎已在绘图区左上角标出）：柱全为正'
                  f'而同比跨零，强行把两个零点拉到同一高度会把左轴一路扩到 '
                  f'{_a8["alo"]:.0f}%、{_a8["waste"]:.0%} 的画布是空的，'
                  f'超过引擎 {ALIGN_WASTE_MAX:.0%} 的兜底阈值。')
ex[-1]['note'] = ex[-1]['note'].replace('{ALIGN}', _ALIGN_TXT)

# 两条线肉眼最显眼的特征是逐月锯齿，而它主要是「当月有几天」造成的，不是经营波动。
# 相关系数现算、结论跟着它走：写死一句「是日历假象」而哪个月相关性真的消失了，
# 图注就会把一个真信号当成假象、劝读者别看。判据阈值也写成常量，图注里同时印出来。
CAL_R_MIN = -0.4
_py_w = trust['portfolio_yield_pct'].iloc[-_TW:]
_pr_w = trust['payment_rate_pct'].iloc[-_TW:]
_dim = np.asarray(_py_w.index.days_in_month, float)
_r_py = float(np.corrcoef(_dim, _py_w.values.astype(float))[0, 1])
_r_pr = float(np.corrcoef(_dim, _pr_w.values.astype(float))[0, 1])
_r_txt = f'{_r_py:+.2f}（组合收益率）/ {_r_pr:+.2f}（还款率）'
if min(_r_py, _r_pr) < CAL_R_MIN:
    _cal_note = (f'<b>⚠️ 两条线的逐月锯齿主要是日历假象，不是经营波动。</b>窗口内它们与'
                 f'当月天数的相关系数是 {_r_txt} —— 负相关意味着 2 月这种短月是尖峰、31 天的'
                 f'月份是谷底。<b>要比就比天数相同的月份，单月的上下不要读。</b>')
else:
    _cal_note = (f'两条线与当月天数的相关系数是 {_r_txt}，本窗口内日历效应已不显著'
                 f'（弱于 {CAL_R_MIN:+.1f} 的判据），逐月锯齿另有来源，仍建议读趋势而非单月。')

ex.append(multi_line_ex(
    9, SEC_T + 'Trust portfolio yield and payment rate', trust,
    ['portfolio_yield_pct', 'payment_rate_pct'], ['NAVY', 'MBLUE'],
    ['Portfolio yield', 'Payment rate'], win=_TW,
    note=f'<b>两条线口径不同，不是一组可比对照，各读各的。</b>'
         f'<b>Portfolio yield（组合收益率）</b>＝池子当月收到的利息与各项费用，年化后占本金'
         f'应收的比例，即这个池子的毛收入率；Exhibit 8 的超额利差就是从它身上逐层扣出来的'
         f'（窗口内 {_py_w.min():.1f}%–{_py_w.max():.1f}%，当期 {_py_w.iloc[-1]:.1f}%）。'
         f'<b>Payment rate（还款率）</b>＝持卡人当月还掉了多少存量余额'
         f'（窗口内 {_pr_w.min():.1f}%–{_pr_w.max():.1f}%，当期 {_pr_w.iloc[-1]:.1f}%）。'
         f'AXP 的还款率结构性地高 —— 客群以每月全额还清的 transactor 为主 —— '
         f'所以<b>绝对水平不能拿去跟别家发卡行比，只看它自己的走向</b>。'
         f'<b>还款率是本板块唯一的领先指标</b>：它掉头意味着持卡人开始还不满、转向循环，'
         f'通常比逾期率（Exhibit 11）早几个月出现，更早于核销（Exhibit 10）。　' + _cal_note,
    src_extra=TRUST_SRC + '.  Payment rate is how fast cardholders repay; a falling payment '
              'rate is an early warning that shows up months before delinquency does'))

ex.append(multi_line_ex(
    10, SEC_T + 'Loss rate: trust pool vs. 8-K Card balances', trust,
    ['nco_pct', 'consumer_nco_pct'], ['NAVY', 'RED'],
    ['Trust: annualised default rate, net of recoveries',
     '8-K: U.S. Consumer net write-off rate'], win=_TW,
    src_extra=TRUST_SRC + '.  The two are close analogues but not the same definition, and '
              + TRUST_NOTE.lower()))

ex.append(multi_line_ex(
    11, SEC_T + 'Delinquency: trust pool vs. 8-K Card balances', trust,
    ['dq30_pct', 'consumer_dq30_pct'], ['NAVY', 'RED'],
    ['Trust: total 30+ days delinquent', '8-K: U.S. Consumer 30+ days past due'], win=_TW,
    src_extra=TRUST_SRC + '.  Both are 30+ day measures on the same concept, so the persistent '
              'gap is purely the pool difference: ' + TRUST_NOTE.lower()))

# ══ 板块 C：旧 loans-only 口径（PDF 第 2 页，Exhibit 13-19）══
# JPM Fig 1：柱=水平值 + 线=同比，长窗口含疫情前
ex.append(bar_yoy_ex(
    12, SEC_O + 'U.S. Consumer loans and y/y growth', old['consumer_balance_usdbn'],
    win=42, yfmt='usd0', ylab='$bn', bar_color='NAVY', bar_name='Reported',
    xstep=2, src_extra=SRC_O + '.  ' + BASIS_O))

# JPM Fig 2：季节性剥离
e13, y13 = seasonality_ex(13, SEC_O + 'Write-off rate vs. same-month norm',
                          old['consumer_nco_pct'], win=13, years=9,
                          src_extra=SRC_O + '.  ' + BASIS_O)
ex.append(e13)

# JPM Fig 3：逐日历月分布
ex.append(year_lines_ex(
    14, SEC_O + 'Consumer write-off rate by year', old['consumer_nco_pct'], n_years=6,
    src_extra=SRC_O + '.  Each line is one calendar year; red = current year.  ' + BASIS_O))

e15, y15 = seasonality_ex(15, SEC_O + 'Delinquency vs. same-month norm',
                          old['consumer_dq30_pct'], win=13, years=9,
                          src_extra=SRC_O + '.  ' + BASIS_O)
ex.append(e15)

ex.append(year_lines_ex(
    16, SEC_O + 'Small Business write-off rate by year', old['sbs_nco_pct'], n_years=6,
    src_extra=SRC_O + '.  Each line is one calendar year; red = current year.  ' + BASIS_O))

# JPM Fig 4：月 x 年热力矩阵（信用指标：低=好，故反转配色）
ex.append(heat_ex(
    17, SEC_O + 'Consumer net write-off rate (%)', old['consumer_nco_pct'], n_years=11,
    src_extra=SRC_O + '.  Green = lower write-off rate (better).  ' + BASIS_O))

ex.append(heat_ex(
    18, SEC_O + 'Small Business net write-off rate (%)', old['sbs_nco_pct'], n_years=11,
    src_extra=SRC_O + '.  Green = lower write-off rate (better).  ' + BASIS_O))


# ────────────────────────────── Exhibit 19：核对表 ──────────────────────────────
TB_WIN = [LATEST - k for k in range(12, -1, -1)]
tb_cols = [
    ['Consumer 余额 ($bn)', 'c_bal'], ['Consumer 30+ DPD (%)', 'c_dq'],
    ['Consumer 平均余额 ($bn)', 'c_avg'], ['Consumer 净核销 (%)', 'c_nco'],
    ['SBS 余额 ($bn)', 's_bal'], ['SBS 30+ DPD (%)', 's_dq'],
    ['SBS 平均余额 ($bn)', 's_avg'], ['SBS 净核销 (%)', 's_nco'],
    ['Card balances HFI ($bn)', 'hfi'],
    ['Trust 组合收益率 (%)', 't_py'], ['Trust 还款率 (%)', 't_pay'],
    ['Trust 超额利差 (%)', 't_es'], ['Trust 30+ 逾期 (%)', 't_dq'],
    ['Trust 年化净违约率 (%)', 't_nco'], ['Trust 本金应收 ($bn)', 't_bal'],
]


def cell(df, p, col, dec):
    if p not in df.index or col not in df.columns:
        return None
    v = df.loc[p, col]
    return None if v is None or not np.isfinite(float(v)) else f'{float(v):,.{dec}f}'


tb_rows = []
for p in TB_WIN:
    tb_rows.append({
        'xl': mlab(p),
        'c_bal': cell(avgbal, p, 'consumer_total_bal_usdbn', 1),
        'c_dq': cell(avgbal, p, 'consumer_dpd30_pct', 1),
        'c_avg': cell(avgbal, p, 'consumer_avg_bal_usdbn', 1),
        'c_nco': cell(avgbal, p, 'consumer_nwo_pct', 1),
        's_bal': cell(avgbal, p, 'smb_total_bal_usdbn', 1),
        's_dq': cell(avgbal, p, 'smb_dpd30_pct', 1),
        's_avg': cell(avgbal, p, 'smb_avg_bal_usdbn', 1),
        's_nco': cell(avgbal, p, 'smb_nwo_pct', 1),
        'hfi': cell(avgbal, p, 'total_hfi_usdbn', 1),
        't_py': cell(trust, p, 'portfolio_yield_pct', 4),
        't_pay': cell(trust, p, 'payment_rate_pct', 4),
        't_es': cell(trust, p, 'excess_spread_pct', 4),
        't_dq': cell(trust, p, 'dq30_pct', 2),
        't_nco': cell(trust, p, 'nco_pct', 4),
        't_bal': cell(trust, p, 'principal_receivables_usdbn', 3),
    })

table = {
    'n': 19,
    'title': f'近 13 个月月度指标核对表（{mlab(TB_WIN[0])} → {mlab(TB_WIN[-1])}，官方原始单位，未换算）',
    'idx': '月份', 'cols': tb_cols, 'rows': tb_rows,
}


# ────────────────────────────── headline / notes ──────────────────────────────
c_bal, c_bal_y = new.loc[CUR, 'consumer_balance_usdbn'], new.loc[YAG, 'consumer_balance_usdbn']
s_bal, s_bal_y = new.loc[CUR, 'sbs_balance_usdbn'], new.loc[YAG, 'sbs_balance_usdbn']
c_dq, c_dq_y = new.loc[CUR, 'consumer_dq30_pct'], new.loc[YAG, 'consumer_dq30_pct']
c_nco, c_nco_y = new.loc[CUR, 'consumer_nco_pct'], new.loc[YAG, 'consumer_nco_pct']
t_es, t_es_y = trust.loc[CUR, 'excess_spread_pct'], trust.loc[YAG, 'excess_spread_pct']
t_pr, t_pr_y = (trust.loc[CUR, 'principal_receivables_usdbn'],
                trust.loc[YAG, 'principal_receivables_usdbn'])
hfi, hfi_p = new.loc[CUR, 'total_balance'], new.loc[PRV, 'total_balance']
s_bal_p = new.loc[PRV, 'sbs_balance_usdbn']

# ── headline 的「underlying」调整 ──
# 报出来的净核销 y/y 里有一档是出售已核销余额买来的，只在 ONEOFF_M 那个月成立。
# headline 只印公司报出来的数、把一次性影响藏在括号里的一句定语中，就是「只报喜不报忧」：
# 读者拿走的是 -50bp，而剔除一次性后只有 -20bp。两个数都印出来，方向由读者自己判断。
if CUR == ONEOFF_M:
    _c_ul = c_nco + ONEOFF_C
    NCO_TXT = (f'净核销 {c_nco:.1f}%（{_signed((c_nco - c_nco_y) * 100, 0, "bp")} y/y；'
               f'剔除出售已核销余额约 {ONEOFF_C:.1f}pp 的一次性影响后约 {_c_ul:.1f}%，'
               f'即 {_signed((_c_ul - c_nco_y) * 100, 0, "bp")} y/y）')
else:
    NCO_TXT = f'净核销 {c_nco:.1f}%（{_signed((c_nco - c_nco_y) * 100, 0, "bp")} y/y）'

HEADLINE = (
    f'{mlab(CUR)}：U.S. Consumer Card 余额 ${c_bal:,.1f}bn（{_signed((c_bal / c_bal_y - 1) * 100, 1, "%")} y/y）'
    f' · 30+ 逾期 {c_dq:.1f}%（{_signed((c_dq - c_dq_y) * 100, 0, "bp")} y/y）'
    f' · {NCO_TXT}'
    f' · SBS 余额 ${s_bal:,.1f}bn（{_signed((s_bal / s_bal_y - 1) * 100, 1, "%")} y/y，'
    f'但 {_signed((s_bal / s_bal_p - 1) * 100, 1, "%")} m/m）'
    f' · Card balances HFI ${hfi:,.1f}bn（{_signed((hfi / hfi_p - 1) * 100, 1, "%")} m/m）'
    f' · Trust 超额利差 {t_es:.2f}%（{_signed((t_es - t_es_y) * 100, 0, "bp")} y/y）'
    f' · Trust 本金应收 ${t_pr:,.2f}bn（{_signed((t_pr / t_pr_y - 1) * 100, 1, "%")} y/y，池子仍在缩）')

# hub_line 是首页卡片上的一行，CONTRACT §1 限 60 字 —— 超了会把卡片撑变形。
# 取舍：余额（本页主指标）+ 净核销的 underlying（唯一被一次性因素粉饰过的数）+ Trust 利差。
# 按重要性排好，超长就从尾巴丢，而不是硬截字符串（截出来的「Trust 利…」比少一段更糟）。
_hub = [f'Consumer 余额 ${c_bal:,.1f}bn（{_signed((c_bal / c_bal_y - 1) * 100, 1, "%")} y/y）',
        (f'净核销 {c_nco:.1f}%、剔一次性 ~{c_nco + ONEOFF_C:.1f}%' if CUR == ONEOFF_M
         else f'净核销 {c_nco:.1f}%'),
        f'Trust 利差 {t_es:.1f}%']
while len(_hub) > 1 and len('；'.join(_hub)) > 60:
    _hub.pop()
HUB = '；'.join(_hub)


# ────────────────────────── 页顶 ~300 字数据总结（brief）──────────────────────────
def compose_brief(new, avgbal, trust, tfull, cur, oneoff_m, oneoff_c):
    """AXP 页顶部的 ~300 字数据总结（payload 的 `brief` 字段）。

    规则库在 `build/brief.py`（R1 峰值扫描 / R2 基数护栏 / R3 日历护栏 /
    R4 单位恒等 / R5 标注 / R6 有效位），那边只算事实，句子在这里拼 ——
    措辞是口径的一部分，属于各家自己。每个数字都当场从序列算，一处硬编码都没有：
    排名、并列数、一次性影响占环比降幅的比例、毛/净违约率各自的变动，
    下个月重跑全都会自己变。

    ═══ 分寸：以 build/ibkr.py 的 compose_brief 为准 ═══
    那一版是用户逐句验收过的标准，既是上限也是下限：四句话四个层次，一句一个意思，
    ~300 字。本页对齐它砍掉的东西（第一版写过头的地方）：
      · 回收率占净降幅的百分比、「按上月回收率固定」的反事实 —— 贡献度拆解，删。
      · 「两者非独立佐证」—— 方法论议论，删；改为只陈述「与 8-K 那笔出售同月」这个事实。
      · s1 尾巴的「两条同向下行、位置分化」与 SBS 还原口径位置 —— 第三、四个意思，删。
        随之 `oneoff_s` 不再进正文，故不再入参（ONEOFF_S 仍用于 Exhibit 的 JUN_NOTE）。
      · 期末余额的名次、回收/违约比的名次 —— 同一句里第二、三个名次，删。
    删的是措辞不是判断：每处保留的定性词仍挂在当场算出的分支上（见下）。

    ═══ 本地移植适配（2026-08-07，同比口径全站改造之后）═══
    远端写这一段时与本地的差别，逐条核对过：
      · **本页全部同比今天复查后仍是点对点（单月）口径**（NOTES 那条逐类给了理由与
        实测：余额是存量走 §6.4 默认、比率走 pp 差、流量那张滚动口径画不满窗口），
        brief 与全页同口径，不存在 ibkr / cboe 那种「图改滚动、brief 并排两口径」的
        适配。要做的只有 CONTRACT §6 的措辞面：brief 里出现的同比一律标「单月」
        （s4 的 SBS 余额那句），并把 brief 补进页尾「同比口径逐处点名」的名单。
      · **Exhibit 8 的次轴今天从 pp 换成了 bp**（pp1 印不出 0.25 步长，见 pp_unit()）。
        本段不引用超额利差及其同比 —— Trust 那句用的是 10-D 的毛/净违约率分解，
        bp 措辞与汇总表「|差| < 1pp 写 bp」同规，不受那次换轴影响；若日后往这里
        加超额利差的读数，单位必须走同一个 pp_unit() 的结论（bp），不许写死 pp。
      · 月均余额合计不再当场相加：本地装载段已有 `avgbal['us_avg_bal']`
        （Exhibit 6 隐含 NII 的乘数基数就是它），口径只能有一处定义，直接引用。

    ═══ 定性词一律由当场算出的量决定分支 ═══
    「买来的」「跌幅不是位置」「还得快」「改善落在回收」这些词全部挂在 if 分支上，
    判据写在旁边。写死措辞 + 算出来的数字 = 下个月印出自相矛盾的句子，这是本轮审查
    逮到的最主要一类 bug（本页原文的「26 个月最低是买来的」与紧随其后的
    「还原后并列第 1 低」就是同一句里自相矛盾）。

    ═══ AXP 独有，别家不能照抄 ═══
      · **本页四条主指标全是反向指标**（30+ 逾期率、净核销率，Consumer 与 SBS 各两条），
        `peak_scan` 一律传 `inverse=True`，措辞只能写「最低位」「最好读数」，
        写成「创新高」会把风险读成利好。本页没有任何一句用「新高」形容这四条。
      · **`peak_scan` 的 argmin 在并列最低时只认第一次出现的那个月**，会把当月并列的
        序列错报成「峰值停在 X 月」。AXP 的 Consumer 逾期率恰好连着两个月并列最低，
        所以「谁在最低位」改用 `months_since_lower()`（没有严格更低的月 = 最低，含并列）
        判定，`peak_scan` 的 `off_peak` 只用来取「还没回到最低位」那几条的月份。
      · **被买来的是跌幅，不是最低位本身**：公司披露出售已核销余额压低了 Consumer / SBS
        的核销率（ONEOFF_C / ONEOFF_S pp，只在 ONEOFF_M 那一个月成立）。正文给
        **还原口径**的位置与排名（R5，字面必须出现「还原口径」四个字），并算出
        「这一档占了环比降幅的百分之几」。当期还原后 Consumer 仍与另一个月并列全样本
        最低 —— 所以只能说跌幅是买来的，不能说最低位是买来的，落点句挂在 `r_lo == 1`
        且 `d_mm < 0` 上，两个条件缺一句子就换。
      · **还原值本身不印数字**：headline 已逐字给出「剔除…后约 X%」，hub_line 也印了一次，
        brief 再印一遍就是规矩 13 禁的复述式摘要。brief 只印 headline 没有的增量：
        名次与并列数。
      · **交叉验证只能用没被那笔出售动过的序列**：`inv_rows` 的第三个元素登记「这条受不受
        该出售影响」，`clean_best`（谁在最低位）与 `off`（谁没跟上）**都**只从 hit=False
        的两条逾期率里取。拿核销率给核销率作证等于用一次性因素给自己背书。
      · **Trust 的违约率是净额口径，正文必须同时给毛与净**：`axp_trust.csv` 的 `nco_pct`
        与 `axp_trust_full.csv` 的 `ann_default_rate_net_pct` 是同一列（净额、已扣回收），
        而 full 表另给毛违约率 `ann_default_rate_pct` 与回收率 `ann_recovery_rate_pct`。
        句子只做一件事：把「净降 X bp」与「毛只降 Y bp」并排放（同 ibkr 的
        「表面跌 6.7%、日均实跌 11.0%」），差额归谁由 `share_rec` 的分支决定。
        **不再算占比、不再做反事实** —— 那是贡献度拆解。当期净降主要来自回收率跳升，
        而 8-K 同月披露的正是出售已核销余额，故 `share_rec >= 0.5 and on` 时点明同月，
        点到为止，不写「互不印证」这类议论。
      · **MIN_BP 是材料性闸门**：净变动只有一两个 bp 时不谈来源分解 —— 分母一小，
        任何占比都会飙成噪音（重放里 2025-05 真的印出过「440%」）。
      · **余额有期末与月均两个口径**：8-K 同时披露 total 与 average balances，月均那条是
        Exhibit 6 隐含 NII 的乘数基数。**不能叫「计息余额」**——本页 NOTES 第一条明写合并
        口径里含不计息的 pay-in-full 部分，两处会自相矛盾。名次只给月均那条（NII 基数
        是它），期末那条给方向就够；一句里塞两个名次是第一版的通病。
      · **R3 日历护栏在这里不成立**：`axp_trust_full.csv` 确有 `days_in_period` 列（28-31 天），
        所以理由不是「没有交易日列」；理由是**本页没有一列是当月合计量**——余额是月末/月均
        存量，逾期率核销率是比率，Trust 三条是月度比率或年化比率，除天数会造出一个假修正。
        天数只作**定性限定**用：还款率在少一天的月份里仍站高位，比硬做日均化更硬。
      · **两套口径不可连比**：新合并 Card balances 口径只有两年出头（`new.index[0]` 起），
        旧 loans-only 长历史（Exhibit 12-18）的分母不含 pay-in-full 余额，比率整体更高。
        所以正文里的「N 个月」一律以新口径序列长度现算，并显式点明口径变更；
        Trust 那句的「N 个月」是另一条更长的序列，两个 N 各算各的，不能共用。
    """
    i = len(new) - 1
    n_new, n_tr = len(new), len(trust)
    ml = [mlab(p) for p in new.index]

    # ── R1（inverse=True）：四条**越低越好**的比率。绝不写「创新高」。
    c_dq, c_nco = new['consumer_dq30_pct'].values, new['consumer_nco_pct'].values
    s_dq, s_nco = new['sbs_dq30_pct'].values, new['sbs_nco_pct'].values
    # 第三个元素 = 那笔出售有没有动过这条序列（公司只把影响归到核销率）。
    inv_rows = [('Consumer 逾期', c_dq, False), ('Consumer 核销', c_nco, True),
                ('SBS 逾期', s_dq, False), ('SBS 核销', s_nco, True)]
    pk = B.peak_scan(ml, [(nm, a) for nm, a, _ in inv_rows], i, inverse=True)
    # 并列修正：argmin 只认第一次出现的最低月，当月并列时会被误判成 off_peak。
    # 「有没有严格更低的月」才是「是不是最低位」的正确判据。
    at_best = [nm for nm, a, _ in inv_rows if B.months_since_lower(a, i) is None]
    # 交叉验证只能用**没被那笔出售动过**的序列，否则等于拿一次性因素给自己作证。
    # `off`（谁没跟上）与 `clean_best`（谁在最低位）同属这一句，必须过同一个 clean 滤网。
    clean = [nm for nm, _, hit in inv_rows if not hit]
    clean_best = [nm for nm in clean if nm in at_best]
    off = [(nm, k) for nm, k in pk['off_peak'] if nm in clean and nm not in at_best]
    off_all = [(nm, k) for nm, k in pk['off_peak'] if nm not in at_best]

    def fmt_off(pairs):
        """几条同时停在同一个月时按月份归并：「A 停在 May-24、B 停在 May-24」是同一个数印两遍。"""
        by_m = {}
        for nm, k in pairs:
            by_m.setdefault(k, []).append(nm)
        return '、'.join('、'.join(v) + f'停在 {k}' for k, v in by_m.items())

    # ── R5：净核销的还原口径。一次性影响只在 ONEOFF_M 那一个月成立。
    # `mention` = s1 这一版会不会提到那笔出售（当月命中，或它还坐在 y/y 基数里）——
    # 后面几句的「该出售」「同样」都指回 s1，s1 不提就不能用这些词。
    on = (cur == oneoff_m) and B.need(c_nco[i], c_nco[i - 1])
    mention = on or (0 < cur.ordinal - oneoff_m.ordinal <= 12)
    if on:
        rc = c_nco.copy()
        rc[i] += oneoff_c
        d_mm = c_nco[i] - c_nco[i - 1]
        share = (oneoff_c / abs(d_mm)) if d_mm else None
        # 「买来的」是有条件的：这一档大于报出来的跌幅时，还原后其实是升的；
        # 报出来根本没跌时更不能说「降幅的百分之几」。三种都得分开写。
        if d_mm < 0 and share is not None and share < 1:
            head = f'{mlab(cur)} Consumer 核销率环比降幅的 {share * 100:.0f}% 是出售已核销余额买来的'
        elif d_mm < 0:
            head = f'{mlab(cur)} Consumer 核销率的环比下降全部由出售已核销余额贡献'
        else:
            head = f'{mlab(cur)} Consumer 核销率环比未降，出售已核销余额已压低它 {oneoff_c:.1f}pp'
        # 还原后的位置：值本身 headline 已印过（规矩 13），这里只印名次与并列数。
        # 转折词也挂在分支上：只有还原后仍站在最低位，才能说「买来的只是跌幅」。
        r_lo = B.rank_of(-rc, i)
        tie = int(np.sum(np.isclose(rc[np.isfinite(rc)], rc[i]))) - 1
        # R5 要求字面出现「（还原口径）」；这里不印还原后的数值（headline 已逐字印过），
        # 标注就挂在名次前面 —— 名次与并列数才是 headline 没有的增量。
        if r_lo == 1:
            pos_c = (f'，但（还原口径）仍与另{B.cn(tie)}个月并列全样本最低' if tie
                     else '，但（还原口径）仍是全样本唯一最低')
        else:
            pos_c = f'，（还原口径）退到第{r_lo}低'
        # 落点只在「确实跌了」且「还原后仍在最低位」时才成立 —— 两个条件缺一，
        # 「买来的是跌幅不是位置」就成了假话，所以它挂在分支上而不是写死在句尾。
        land = '，买来的是跌幅不是位置' if (d_mm < 0 and r_lo == 1) else ''
        s1 = head + pos_c + land + f'（新口径 {new.index[0]} 起，与旧口径不可连比）。'
    elif 0 < cur.ordinal - oneoff_m.ordinal <= 12:
        # 一次性影响已滚出当月读数，但它还坐在 y/y 的比较基数里，直到 ONEOFF_M + 12。
        # 用 ordinal 之差判断而不是「不等于就是之后」：数据回补／回放时 cur 可能早于
        # ONEOFF_M，那时说「已不在当月读数里、要到某月才滚出去」是反的。
        # 这一句原先 117 字，长到把后面的交叉验证句挤出了字数护栏（重放里 s2 被丢掉、
        # 整段只剩三句）。压到 ~95 字，四句就都放得下。
        s1 = (f'{mlab(oneoff_m)} 出售已核销余额压低 Consumer 核销率的那 {oneoff_c:.1f}pp 已不在当月读数里，'
              f'但仍坐在 y/y 的基数上，要到 {mlab(oneoff_m + 12)} 才滚出去'
              f'（新口径 {new.index[0]} 起，与旧口径不可连比）。')
    else:
        # 那笔出售要么还没发生、要么连 y/y 的基数都滚过了：正文不再提它。
        # 这一句原本是一整句纯口径声明，一个读数都没有 —— 重放里 13/14 个月都以免责声明
        # 开场，比 build/ibkr.py 的样板（s1 就是当月读数 + 它在历史里的位置）单薄一截。
        # 改成四条反向指标的**位置扫描**（R1，inverse=True），口径断点没删，只是降级成
        # 句尾的括号：F4 要求标注一个都不许少，但没要求它自成一句。
        # 注：ONEOFF_M 那个月的核销率被出售压低，它一直留在历史分布里，所以此后
        # 「N 个月最低」只会更难达成 —— 偏保守，不会把改善说过头。
        if at_best:
            core1 = (f'{B.quant(len(at_best), len(inv_rows), "条")}在{n_new}个月最低：'
                     + '、'.join(at_best))
        else:
            core1 = f'没有一条落在{n_new}个月最低'
        tail1 = fmt_off(off_all)
        s1 = (f'{mlab(cur)} {B.cn(len(inv_rows))}条逾期与核销率里{core1}'
              + (f'；{tail1}' if tail1 else '')
              + f'（新口径 {new.index[0]} 起，与旧 loans-only 序列不可连比）。')

    # ── R1 续：逾期率不在那笔出售之列，是本页唯一能对冲一次性因素的交叉验证。
    # 只在 s1 确实点了那笔出售的月份才写：不提出售的月份里「不受该出售影响」没有先行词，
    # 而四条的位置 s1 已经全量给过一遍，再写一句就是同一件事说两遍。
    # B.cn(2) 给的是「二」，中文量词这里要「两」——「二条逾期率」读起来是错的。
    if mention:
        n_clean = '两' if len(clean) == 2 else B.cn(len(clean))
        if clean_best:
            core = '、'.join(clean_best) + f'同样在{n_new}个月最低，改善有真实成分'
        else:
            core = f'没有一条落在{n_new}个月最低，真实改善存疑'
        off_txt = fmt_off(off)
        s2 = (f'不受该出售影响的{n_clean}条逾期率里，' + core
              + (f'，{off_txt}。' if off_txt else '。'))
    else:
        s2 = ''

    # ── 口径背离：期末余额 vs 月均余额（后者是 Exhibit 6 隐含 NII 的乘数基数）。
    # **不写「计息的」**：合并 Card balances 含不计息的 pay-in-full 部分，见本页 NOTES 第一条。
    # 月均合计直接用装载段的 us_avg_bal（Exhibit 6 的乘数基数就是这一列，口径同一处定义）。
    end_tot = (new['consumer_balance_usdbn'] + new['sbs_balance_usdbn']).values
    avg_tot = avgbal['us_avg_bal'].values
    if i >= 1 and B.need(end_tot[i], end_tot[i - 1], avg_tot[i], avg_tot[i - 1]):
        e_mm = end_tot[i] / end_tot[i - 1] - 1
        a_mm = avg_tot[i] / avg_tot[i - 1] - 1
        # T3：月均若是几乎只增不减的序列，「排第几高」每月都是同一个答案、是噪音，那就不报名次。
        # 名次只给月均那一条：它是 Exhibit 6 隐含 NII 的乘数基数，也是这句话的主语；
        # 期末那条给方向就够 —— 一句里并排两个名次是第一版的通病，读起来像脚注。
        mono = B.is_monotonic(avg_tot)
        rk_a = '' if mono else f'、第{B.rank_of(avg_tot, i)}高'
        # 四舍五入后印成 0.0% 的月均变动不配叫「口径反向」：页面上会出现「期末降、月均
        # 却 0.0% m/m」这种自打嘴巴的句子（重放里 Jun-25 就是）。闸门与 B.pct 的显示
        # 精度对齐（<0.05% 即印成 0.0%），所以判据用显示精度而不是另设一个阈值。
        if abs(a_mm) * 100 < 0.05:
            s3 = (f'期末合计环比{"降" if e_mm < 0 else "升"}，但隐含 NII 的月均余额几乎没动'
                  f'（{B.pct(a_mm)} m/m{rk_a}），NII 的基数没跟着走。')
        elif (e_mm < 0) != (a_mm < 0):
            s3 = (f'余额口径反向：期末合计环比{"降" if e_mm < 0 else "升"}，'
                  f'隐含 NII 的月均余额却 <b>{B.pct(a_mm)}</b> m/m{rk_a}，'
                  f'只读期末会把 NII 基数读{"成缩表" if e_mm < 0 else "偏乐观"}。')
        else:
            s3 = (f'期末与月均两个余额口径同向（月均 {B.pct(a_mm)} m/m{rk_a}），'
                  f'本月不会把 NII 基数读反。')
    else:
        s3 = ''

    # ── R2：SBS 余额的基数护栏。上月排全样本第几，是这句话的全部信息量。
    # 存量的点对点同比是 §6.4 的默认口径，但措辞按 §6 标「单月」——
    # 与页尾「同比口径逐处点名」那条互为对照，读者不用猜这个 y/y 是哪种。
    be = B.base_effect(new['sbs_balance_usdbn'].values, i)
    if be['conflict'] and be['prev_rank']:
        s4 = (f'SBS 余额环比的{"负" if be["mm"] < 0 else "正"}号来自上月基数：{mlab(cur - 1)} 是新口径'
              + ('最高月' if be['prev_is_max'] else f'第{be["prev_rank"]}高月')
              + f'，单月同比仍{"为正" if be["yy"] > 0 else "为负"}。')
    elif be['prev_rank'] and be['yy'] is not None:
        s4 = f'SBS 余额环比与单月同比同向（上月排第{be["prev_rank"]}高），不是基数造出来的。'
    else:
        s4 = ''

    # ── 所处区间 + 口径分解：Trust 层（另一个池子、另一条更长的序列，N 各算各的）。
    j = len(trust) - 1
    prate = trust['payment_rate_pct'].values
    pool = trust['principal_receivables_usdbn'].values
    days = tfull['days_in_period'].values
    gross = tfull['ann_default_rate_pct'].values          # 毛违约率
    recr = tfull['ann_recovery_rate_pct'].values          # 回收率
    netd = tfull['ann_default_rate_net_pct'].values       # 净违约率（= 摘要表 nco_pct）

    pr_rank = B.rank_of(prate, j)
    # R3 不适用（本页没有当月合计量），但天数可以当定性限定：少一天还能站高位才是硬证据。
    dd = (days[j] - days[j - 1]) if (j >= 1 and B.need(days[j], days[j - 1])) else 0
    if dd < 0:
        lead = f'Trust 还款率在 {days[j]:.0f} 天短月里仍排{n_tr}个月第{pr_rank}高'
    elif dd > 0:
        lead = f'Trust 还款率排{n_tr}个月第{pr_rank}高（当月多 {dd:.0f} 天）'
    else:
        lead = f'Trust 还款率排{n_tr}个月第{pr_rank}高'
    # 「池子缩是还得快」只在还款率确实站在高位、且池子确实在缩时才成立。
    if pool[j] < pool[j - 1] and pr_rank <= max(1, n_tr // 3):
        pay = lead + '，池子缩是<b>还得快</b>；'
    else:
        pay = lead + f'，池子在{"缩" if pool[j] < pool[j - 1] else "扩"}；'

    # 净额口径：Δ净 = Δ毛 − Δ回收。句子只做一件事 —— 把「净降 X bp」与「毛只降 Y bp」
    # 并排放（同 ibkr 的「表面跌 6.7%、日均实跌 11.0%」），差额归谁由分支决定。
    # 远端这里写的是「单月降 X bp」—— 指的是 m/m。今天的口径改造把「单月」定成了
    # **单月同比**的专用标签（CONTRACT §6.2，页尾点名条也按这个词核对），m/m 再用
    # 这两个字就会被读成 y/y，所以下面四个分支一律改写「环比」（本函数第一个分支
    # 「环比持平」本来就是这个词）。
    # **不再报回收率占净降幅的百分比、不再算「按上月回收率固定」的反事实**：那是贡献度
    # 拆解，样板里没有这种东西。share_rec 仍然当场算，但只用来选句子，不印出来。
    # MIN_BP 是**材料性闸门**：净变动只有一两个 bp 时谈来源就是把噪音当信号 ——
    # 分母一小，任何占比都能飙到几百 %（重放里 2025-05 真的印出过「440%」）。
    MIN_BP = 5.0
    if not B.need(netd[j], netd[j - 1], gross[j], gross[j - 1], recr[j], recr[j - 1]):
        dec = '违约率为净额口径（已扣回收），当月缺分解所需字段。'
    else:
        d_net = netd[j] - netd[j - 1]
        d_gross = gross[j] - gross[j - 1]
        d_rec = recr[j] - recr[j - 1]
        share_rec = (-d_rec / d_net) if d_net else None
        mv, gv = ('降' if d_net < 0 else '升'), ('降' if d_gross < 0 else '升')
        rv = '升' if d_rec > 0 else '降'
        g_lo = B.rank_of(-gross, j)
        # 四舍五入到 0 的变化不给方向（同 _signed 的规矩：舍入后的零没有方向）。
        g_txt = ('毛违约率几乎没动' if round(abs(d_gross) * 100) == 0
                 else f'毛违约率只{gv} {abs(d_gross) * 100:.0f}bp')
        # 8-K 那笔出售在信托里的表现形式就是回收跳升 —— 只在同月才可能是同一笔，
        # 所以这半句挂在 `on` 上。只陈述「同月」这个事实，不下「互不印证」的判断。
        same = '，与 8-K 那笔出售同月' if on else ''
        if share_rec is None or abs(d_net) * 100 < MIN_BP:
            dec = (f'违约率（<b>净额</b>口径）环比{"持平" if share_rec is None else "只动了个位数 bp"}，'
                   f'毛违约率在{n_tr}个月里排第{g_lo}低。')
        elif share_rec > 1:
            # 回收率一头把净额拉过了头：毛违约率其实在往反方向走。
            dec = (f'违约率是<b>净额</b>口径：环比{mv} {abs(d_net) * 100:.0f}bp 全由回收率'
                   f'{rv} {abs(d_rec) * 100:.0f}bp 造成，'
                   f'毛违约率反而{gv} {abs(d_gross) * 100:.0f}bp{same}。')
        elif share_rec >= 0.5:
            dec = (f'违约率是<b>净额</b>口径：环比{mv} {abs(d_net) * 100:.0f}bp，'
                   f'{g_txt}、第{g_lo}低，差额是回收率{rv} {abs(d_rec) * 100:.0f}bp{same}。')
        elif share_rec > 0:
            dec = (f'违约率是<b>净额</b>口径：环比{mv} {abs(d_net) * 100:.0f}bp 主要来自毛违约率'
                   f'（{gv} {abs(d_gross) * 100:.0f}bp、第{g_lo}低），回收率只添 '
                   f'{abs(d_rec) * 100:.0f}bp。')
        else:
            dec = (f'违约率是<b>净额</b>口径：环比{mv} {abs(d_net) * 100:.0f}bp 全部来自毛违约率'
                   f'（{gv} {abs(d_gross) * 100:.0f}bp、第{g_lo}低），回收率反向变动。')
    s5 = pay + dec

    # 字数：B.render 的 230-380 是硬护栏（拦「模板拼坏了」），本页自己收到 250-330 ——
    # 句子长度随数据变（off 里几条、at_best 里几条、Trust 走哪个分支都会变），所以超出
    # 上界时按**重要性倒序**丢句：先丢 R2 基数句，再丢交叉验证，最后才是口径背离。
    # s1（一次性因素怎么读）与 s5（净额口径怎么读）是本页的全部理由，一句都不丢。
    # 丢之前先看丢完会不会掉到下界以下 —— 会的话宁可略长，也不要把一段解读砍成半段。
    # 五句是上限（F3），正常月份丢掉 s4 后落在四句，与 build/ibkr.py 的样板同形。
    plain = lambda ss: len(re.sub(r'<[^>]+>', '', ''.join(x for x in ss if x)))
    LO, HI = 250, 330
    sents = [s1, s2, s3, s4, s5]
    for k in (3, 1, 2):
        if plain(sents) <= HI:
            break
        # 这一句已经空了、或丢掉它会掉到下界以下 —— 跳过它去试下一句，别整个停下来
        # （写成 break 的那一版：s4 恰好为空时后面两句一句都不再考虑，重放里 344 字下不来）。
        if not sents[k] or plain(sents) - plain([sents[k]]) < LO:
            continue
        sents[k] = ''
    return B.render(sents)


# ── 轴刻度收口（必须排在 NOTES 之前）──────────────────────────────────────────
# 轴刻度小数位：引擎默认格式器把 2.5 印成「3」、把 0.25 步长整列印成重复/错值，
# 判据与算法见 build/axisfmt.py（与 build/single.py 共用同一份）。
# **位置很要紧**：axisfmt 除了改格式器，还会给「柱图型出现负值」的图补 ycap/yfloor。
# 下面那几串「哪几张画了什么」的编号是现读 payload 生成的，必须读到最终结果，
# 否则又会出现「图注声称的与图上画的对不上」——本轮修的正是这一类。
axisfmt.fix_all(ex)

# ── 「哪几张画了什么」一律从 payload 现读，不手写编号 ──────────────────────────
# 全站复查抓到过一整类缺陷：图注声称的口径与图上实际画的对不上，根因都是注释是手写常量、
# 而图上画什么由数据当场决定（本页 Exhibit 7 就是：费率同比是不是常数决定它画次轴同比
# 还是 12 个月均线，而那句说明以前写死成「Exhibit 7 是本页唯一不画次轴同比的一张」）。
# 下面三串编号跟着 payload 走，改了图这几句话会自己改口。
_LVL_EX = [str(e['n']) for e in ex if e['kind'] == 'gs_bar']
_YOY_EX = [str(e['n']) for e in ex if e.get('yoy')]
_AVG_EX = [str(e['n']) for e in ex if e.get('avg12') is not None]

# ── 同比口径盘点：本页每一条同比线是什么口径、为什么 ──────────────────────────
# 判据不是「感觉存量噪声小」，而是**用本页自己的序列实测**：
# 存量序列的 12 个月滚动窗口同比在数值上完全正确（Σ12/Σ12′ ≡ 均值比，实测差 2.3e-14），
# 只是不能把它叫作「合计」（12 个月末快照相加不指代任何东西），所以这里用
# yoy.ttm_mean_yoy() 算出「12 个月均值同比」，与点对点同比并排实测，再决定用哪个。
def _cal_stock(s, win):
    """存量序列：点对点同比 vs {TTM_WIN} 个月均值同比，对齐月份后各项统计。"""
    v = Y._as_series(s)
    a = Y.mom_yoy(v, Y.STOCK)
    b = Y.ttm_mean_yoy(v, Y.STOCK)
    av, bv = a.values.astype(float), b.values.astype(float)
    m = np.isfinite(av) & np.isfinite(bv)
    if win:
        w = np.zeros(len(m), bool)
        w[-win:] = True
        m &= w
    idx = list(v.index)
    aa, bb = np.where(m, av, np.nan), np.where(m, bv, np.nan)
    n = int(m.sum())
    opp = [(idx[i], float(av[i]), float(bv[i])) for i in np.flatnonzero(m & (av * bv < 0))]
    def _sd(x):
        return float(np.nanstd(x, ddof=1)) if np.isfinite(x).sum() >= 2 else float('nan')
    def _mj(x):
        d = np.abs(np.diff(x))
        return float(np.nanmax(d)) if np.isfinite(d).any() else float('nan')
    return {'n': n, 'sd_mom': _sd(aa), 'sd_ttm': _sd(bb),
            'mj_mom': _mj(aa), 'mj_ttm': _mj(bb), 'opp': opp}


# 拿**旧口径**那条余额序列做这次实测，不是新口径：新口径自 2024-05 起只有 26 个月，
# 而 12 个月均值同比要 24 个月才有第一个点 —— 样本只剩 3 个月，算出来的标准差比
# 它要回答的问题还不确定。旧口径同一个量有 123 个月，正是 Exhibit 12 画的那条。
_W12 = 42                # Exhibit 12 实际画出来的窗口长度（下面 bar_yoy_ex 的 win）
_CAL_BAL = _cal_stock(tail_contiguous(old['consumer_balance_usdbn']), _W12)
_CAL_ALL = _cal_stock(tail_contiguous(old['consumer_balance_usdbn']), None)
_CAL_MIN_N = 24          # 少于两年的重叠就不下「哪个口径更好」的结论，只报数

NOTES = [
    f'<b>两套口径不可连比。</b>AXP 自 2026 年 5 月起把 Card Member loans 与 receivables 合并披露为'
    f' "Card balances"（含 pay-in-full 余额），并在 2026-05-15 的 8-K Exhibit 99.1 里重述了 24 个月历史。'
    f'原 PDF 分两页呈现，网页版没有分页概念，改用标题里的板块小标题分组：'
    f'<b>{SEC_A}</b>为 Exhibit 2-7（{new.index[0]} 起），'
    f'<b>{SEC_O}</b>为 Exhibit 12-18（{old.index[0]} → {old.index[-1]}）。'
    f'跨这两组读同一条指标是错的 —— 合并口径的余额里多了不计息的 pay-in-full 部分，'
    f'分母变大会把逾期率与核销率整体压低。',

    f'<b>旧口径序列刻意截到 {old.index[-1]}</b>（改口径前最后一个月），只用于长历史与季节性；'
    f'{new.index[0]} 之后的新口径数字不会被接到旧序列尾巴上，避免画出一条假的连续曲线。',

    f'<b>⚠️ {JUN_NOTE}。</b>受影响的是 Exhibit 3 / 5 的 {mlab(ONEOFF_M)} 那一点、'
    f'Exhibit 10 的 8-K 线在 {mlab(ONEOFF_M)} 的读数'
    + (f'，以及汇总表与 headline 里 Consumer / SBS 两行的净核销 m/m 与 y/y'
       if CUR == ONEOFF_M else '（当期已不是该月，汇总表的 m/m 不再受它影响，'
                               f'y/y 要到 {mlab(ONEOFF_M + 12)} 才滚出比较基数）')
    + f' —— 这一档下降不是资产质量改善，不要外推。'
    + (f'headline 已同时给出剔除该影响后的 Consumer 净核销约 {c_nco + ONEOFF_C:.1f}%。'
       if CUR == ONEOFF_M else ''),

    f'<b>本页没有一条红色竖虚线，这是刻意的，不是漏画。</b>2026-05 的口径切换发生在'
    f'<b>两组 exhibit 之间</b>，而不是某一张图的横轴内部：新口径各图只画 {new.index[0]} 起的'
    f'重述序列，旧口径各图刻意截到 {old.index[-1]}，没有任何一张图的 x 轴跨过 2026-05，'
    f'所以 <code>break_at</code> 没有落点可画 —— 口径变化由标题里的板块小标题与本节第一条承担。'
    f'（首页「怎么读这个看板」把「AXP 2026-05 合并 Card balances」列成了红色竖虚线的例子，'
    f'那句话与本页实际渲染不符，以本页为准。）',

    f'<b>Exhibit 6 是推导值，标了 Implied。</b>{NII_NOTE} 净利息收益率是公司整体口径（含非美卡与其他贷款），'
    f'而余额只取美国 Consumer + Small Business 卡，两者总体不一致；季度费率按「当季各月同值、'
    f'最新季之后沿用」摊到月度（Exhibit 7 画的就是这条阶梯）。公司不按月披露 NII，因此这张图无从对账。'
    f'　{FEE_PERIOD_NOTE}',

    f'Exhibit 6 / 7 的序列比其余新口径图短两个月：{new.index[0]} 与 {new.index[0] + 1} 落在 '
    f'{_niy.index[0]} 之前，没有可用的新口径净利息收益率，按「缺列就没有那个点」处理，不做外推。',

    f'<b>Lending Trust（Exhibit 8-11）是另一个池子，不是 8-K 的子集。</b>{TRUST_NOTE}；'
    f'信托池只含 revolve-eligible 余额，所以组合收益率、违约率、逾期率都系统性低于/异于 8-K 口径，'
    f'Exhibit 10 / 11 里那条持续存在的缺口是池子差异，不是数据错。Form 10-D 与 8-K 同日报送'
    f'（近 31 期 31/31 同日），所以两份材料一次到手。',

    f'<b>汇总表把原 deck 的两张表合并成了一张。</b>原 PDF 的 Exhibit 1（8-K 指标）与 Exhibit 8'
    f'（Trust 月报）是两张独立的汇总表，网页版只有一个汇总表位，两者最新月同为 {mlab(LATEST)}、'
    f'列口径也完全一致，故合并并用板块分隔条区分；其后各图顺延一位编号（PDF 的 Fig 9-19 = 本页的 '
    f'Exhibit 8-18）。',

    f'比率类指标的变化一律用百分点：|差| &lt; 1pp 写 bp，否则写 pp，不用「百分比的百分比变化」；'
    f'四舍五入到零的变化写「0bp」而不是「+0bp」／「-0bp」—— 舍入后的零没有方向。'
    f'逾期率、核销率、信托违约率按「越低越好」着色（下降为绿）。' + PCT_NOTE,

    f'Exhibit 13 / 15 的灰柱是<b>过去 {y13} 年同一日历月的均值</b>（不是滚动均值），'
    f'用来把季节性从水平值里剥掉；Exhibit 14 / 16 每条线是一个日历年，红线为当前年（{old.index[-1].year} 年'
    f'只到 {MONTHS[old.index[-1].month - 1]}）。Exhibit 17 / 18 的热力矩阵配色已反转：'
    f'<b>绿 = 核销率低（好）</b>，色标取全部有限值的 5/95 分位，一两个离群月不会把整表压平。',

    f'<b>与原 PDF 的四处有意差异。</b>(1) 原 deck 的 <code>lvl_bar</code>'
    f'（Exhibit {"/".join(_LVL_EX)}）是「浅蓝柱 + 每柱数值 + 次轴金色同比线」，'
    f'网页版用 <code>gs_bar</code> + <code>yoy</code> 逐条还原。'
    f'本轮实际画出次轴同比的是 <b>Exhibit {"/".join(_YOY_EX)}</b>；'
    + (f'画 12 个月均线（而非次轴同比）的是 <b>Exhibit {"/".join(_AVG_EX)}</b>，'
       f'理由见第 (2) 条。'
       if _AVG_EX else
       '本轮<b>没有任何一张画 12 个月均线</b>（deck 的 docstring：均线只是把柱子'
       '再平滑一遍、不带新信息）。')
    + f'这两串编号由本页 payload 现读（谁挂了 <code>yoy</code>、谁挂了 '
    f'<code>avg12</code>），不是写死的说明文字 —— 哪张图改了口径，这句话会自己跟着改。'
    f'此前用的 <code>bar_line_dual</code> 形态对、但丢了'
    f'「每柱数值」那一层，而 Exhibit 7 / 8 的全部信息恰好就在那一层。'
    f'Exhibit 12 来自 <code>rev_bar_yoy</code> 而非 <code>lvl_bar</code>，柱是深色 NAVY'
    f'（图例 "Reported"），<code>gs_bar</code> 的柱色写死在引擎里的浅蓝，故仍留 '
    f'<code>bar_line_dual</code>。'
    f'(2) <b>Exhibit 7 的次轴画什么，由数据当场决定</b>：费率是季度阶梯（同一季三个月同值），'
    + (f'本轮窗口内它的同比<b>恒为 {_niy_yy_set[0]:+.2f}pp</b> —— 一个常数、不带信息，'
       f'而常数同比的次轴必然退化（量程塌成一个点、刻度舍成一列重复读数、'
       f'末点读数压在最高刻度上），所以这一张<b>改画 12 个月均线</b>'
       f'（费率看「当前 vs 过去一年均值」才有参考意义），那个常数写进图注。'
       if _niy_const else
       f'本轮窗口内它的同比取值 {"、".join(f"{v:+.2f}pp" for v in _niy_yy_set)}'
       f'（{len(_niy_yy_set)} 个不同值），<b>不是常数</b>，所以这一张与其余同类图一样'
       f'画次轴同比。')
    + f'这里没有断言、也不会因此构建失败：月度数字本来就走在季度费率前面，'
    f'费率一落后一个季度、ffill 把最后一档拉平，同比就不再是常数 —— '
    f'那是常态不是异常，生成器自己在两种画法之间切换，本条说明跟着切。'
    f'(2.5) 本页<b>没有任何一条同比线用 {Y.TTM_WIN} 个月滚动口径</b>，全部是'
    f'<b>点对点同比</b>（当月对去年同月；比率序列取百分点差）——'
    f'Exhibit {"/".join(_YOY_EX)} 的次轴、Exhibit 12 的右轴线、'
    f'Exhibit 13/15 的季节性基准、Exhibit 17/18 的热力矩阵、两张表的 y/y 列，'
    f'以及页顶 brief 段里出现的任何同比读数（句中已标「单月」）全部同口径，'
    f'所以本页任意两处的同比读数可以直接互相对读。理由逐类不同，都不是「存量不能滚动」'
    f'那句一般性说辞（{Y.TTM_WIN} 个月滚动<b>均值</b>同比对存量在数值上完全正确，'
    f'不许说的只是把它叫「合计」）：'
    f'① <b>余额类（Exhibit 2/4/12）是期末存量</b>，用本页自己的序列实测'
    f'（取 Exhibit 12 那条旧口径 Consumer 余额，<b>只量图上真画出来的 {_W12} 个月</b> —— '
    f'图外的历史读者根本看不到；新口径只有 {len(new)} 个月，'
    f'重叠样本太少算不出可信的标准差）：'
    f'{_CAL_BAL["n"]} 个两种口径都有值的月份上，'
    f'点对点同比逐月标准差 {_CAL_BAL["sd_mom"]:.2f}pp、'
    f'{Y.TTM_WIN} 个月<b>均值</b>同比 {_CAL_BAL["sd_ttm"]:.2f}pp'
    f'（放大 {_CAL_BAL["sd_mom"] / _CAL_BAL["sd_ttm"]:.2f} 倍），'
    f'相邻月最大跳变 {_CAL_BAL["mj_mom"]:.2f}pp vs {_CAL_BAL["mj_ttm"]:.2f}pp，'
    f'符号相反的月份 {len(_CAL_BAL["opp"])} 个'
    + (f'（{_CAL_BAL["opp"][0][0]} 点对点 {_CAL_BAL["opp"][0][1]:+.1f}% vs '
       f'均值 {_CAL_BAL["opp"][0][2]:+.1f}%）' if _CAL_BAL['opp'] else '')
    + ' —— '
    + ('重叠样本不足两年，这里只报数、不下「哪个口径更好」的结论；'
       if _CAL_BAL['n'] < _CAL_MIN_N else
       '存量的点对点同比比的是两个时点的余额、不含日历效应，放大倍数远低于'
       f'全站流量序列的中位 2.08 倍，且没有一个月符号相反，'
       '所以这里保留点对点、噪声用轴范围解决；'
       if _CAL_BAL['sd_mom'] < _CAL_BAL['sd_ttm'] * 2.08 and not _CAL_BAL['opp'] else
       f'放大倍数或符号分歧已经追上全站流量序列的水平，'
       f'下一轮应当把这几张图改成 {Y.TTM_WIN} 个月均值同比；')
    + (f'（把窗口放到全历史 {_CAL_ALL["n"]} 个月，放大倍数是 '
       f'{_CAL_ALL["sd_mom"] / _CAL_ALL["sd_ttm"]:.2f} 倍、符号相反 '
       f'{len(_CAL_ALL["opp"])} 个月，那 {len(_CAL_ALL["opp"])} 个月全部落在 '
       f'{_CAL_ALL["opp"][0][0]}–{_CAL_ALL["opp"][-1][0]} 的疫情 V 型段里、'
       f'早已滚出本图窗口 —— 拿它当判据就是报图外的问题。）'
       if _CAL_ALL['opp'] and not _CAL_BAL['opp'] else '')
    + f'② <b>比率类（Exhibit 7/8 与逾期率、核销率）</b>的同比只能是百分点差，'
    f'滚动合计与滚动均值对比率都没有意义（要「一年的平均费率」得用余额加权）；'
    f'③ <b>Exhibit 6（隐含净利息收入）是流量</b>，按契约默认本该用 {Y.TTM_WIN} 个月滚动合计，'
    f'但新口径序列自 {new.index[0]} 起只有 {len(new)} 个月，'
    f'而滚动同比要 {Y.TTM_WIN} 个月填窗 + {Y.TTM_WIN} 个月比较才有第一个点 —— '
    f'本图 24 个月的窗口里滚动口径只画得出 '
    f'{int(Y.ttm_yoy(tail_contiguous(avgbal["implied_nii_usdmn"]), Y.FLOW).iloc[-24:].notna().sum())} '
    f'个月，画出来是一条几乎空白的线；'
    f'④ <b>Exhibit 13/15/17/18</b> 是季节性与热力矩阵，按 CONTRACT.md §6 本就豁免'
    f'（逐格逐月的波动正是这两类图的题眼）；'
    f'⑤ <b>两张表的 y/y 列</b>必须恒等于「本月 ÷ 去年同月」的表内算术，'
    f'读者拿第一列除第三列要能得到同一个数 —— 表内自相矛盾比口径混用更糟。'
    f'(3) 两张热力矩阵没有走通栏：通栏卡片会被渲染器排到汇总表正下方、跑到 Exhibit 2 前面，'
    f'为保住原 deck 的图序改用半栏（引擎会按格宽自动收字号）。'
    f'(4) 汇总表里「零变化」不着色（原 deck 把 0 着成红色，等于说「没变 = 变坏」）。'
    f'除此之外顺序、窗口、标题与图注均照搬。',
]

FOOTER = ('American Express (AXP)  ·  SEC 8-K Item 7.01 (CIK 0000004962) + Credit Account Master '
          'Trust Form 10-D (CIK 0001003509)  ·  template after J.P. Morgan managed-data-release '
          'note  ·  charts only, no commentary  ·  personal research use')

payload = {
    'ticker': 'axp',
    'tracker': 'AXP Monthly Credit Metrics Tracker',
    'title': f'American Express (AXP)：月度信贷经营指标 — {LATEST.year} 年 {LATEST.month} 月',
    'data_through': str(LATEST),
    'through_label': f'{LATEST.year} 年 {LATEST.month} 月',
    'subtitle': f'数据源：SEC 8-K Item 7.01（CIK 0000004962）与 American Express Credit Account '
                f'Master Trust Form 10-D（CIK 0001003509）　·　覆盖 {old.index[0]} → {LATEST}'
                f'（旧 loans-only 口径 {old.index[0]} → {old.index[-1]}；新合并 Card balances 口径 '
                f'{new.index[0]} 起；Trust {trust.index[0]} 起）　·　版式仿 J.P. Morgan'
                f'「Managed Data Release」',
    'headline': HEADLINE,
    # headline 之下、Exhibit 1 之上的 ~300 字解读。职责与 headline 互补：
    # 那一行给读数，这一段给「读数该怎么读」。见 compose_brief 的 docstring。
    'brief': compose_brief(new, avgbal, trust, tfull, CUR, ONEOFF_M, ONEOFF_C),
    'hub_line': HUB,
    'source': 'Source: AXP 8-K Item 7.01 (SEC CIK 0000004962) and American Express Credit Account '
              'Master Trust Form 10-D (SEC CIK 0001003509); format after J.P. Morgan',
    'xlabels': [mlab(p) for p in TB_WIN],
    'xlabels_long': xl(old.index),
    'summary': summary,
    'exhibits': ex,              # 已在上面过完 axisfmt.fix_all（幂等，这里不重复调）
    'table': table,
    'notes': NOTES,
    'footer': FOOTER,
}
if SOURCE_DATE:
    payload['source_date'] = SOURCE_DATE


def main():
    out_dir = os.path.join(ROOT, 'data')
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, 'axp.js')
    # 写出前先过 CONTRACT §5.5 护栏（NaN/Infinity 一律拒写）；首行注释与序列化都在里面。
    payload_guard.write_dash(path, payload, 'axp')

    print(f'最新月 {LATEST}  ·  旧口径 {old.index[0]} → {old.index[-1]}（{len(old)} 个月）'
          f'  ·  新口径 {new.index[0]} → {new.index[-1]}（{len(new)} 个月）'
          f'  ·  Trust {trust.index[0]} → {trust.index[-1]}（{len(trust)} 个月）')
    print(f'Exhibit 1 汇总表（{len(srows)} 行）+ Exhibit {ex[0]["n"]}-{ex[-1]["n"]}'
          f'（{len(ex)} 张图）+ Exhibit {table["n"]} 核对表（{len(tb_rows)} 行 x {len(tb_cols)} 列）'
          f'  ·  notes {len(NOTES)} 条')
    print(f'写出 data/axp.js  ({os.path.getsize(path) / 1024:.1f} KB)')
    print(HEADLINE)


if __name__ == '__main__':
    main()
