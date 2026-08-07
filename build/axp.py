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

import numpy as np
import pandas as pd

import axisfmt
import payload_guard
import pctile

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


# ────────────────────────────── 小工具 ──────────────────────────────
def mlab(p):
    return p.strftime('%b-%y')


def xl(idx):
    return [mlab(p) for p in idx]


def L(a):
    """序列 → JSON 数组，NaN 写 null（缺口不连线，规矩 3）。"""
    return [None if v is None or not np.isfinite(float(v)) else round(float(v), 6) for v in a]


def lvl_yoy(s, pct_series=False):
    """照抄 gsx.lvl_bar 的次轴同比：比率序列取百分点差；水平值取百分比变化，
    但基数过小（< 0.15 x 中位绝对值）或两期异号时留空 —— 那种同比没有意义。"""
    v = np.asarray(s.values, dtype=float)
    scale = float(np.nanmedian(np.abs(v))) or 1.0
    out = np.full(len(v), np.nan)
    for i in range(12, len(v)):
        a, b = v[i], v[i - 12]
        if not (np.isfinite(a) and np.isfinite(b)):
            continue
        if pct_series:
            out[i] = a - b
        elif abs(b) < 0.15 * scale or a * b < 0:
            continue
        else:
            out[i] = (a / b - 1) * 100.0
    return pd.Series(out, index=s.index)


def plain_yoy(s):
    """照抄 gsx.rev_bar_yoy 用的 _yoy：不做基数保护，只要两期都在就算。"""
    v = np.asarray(s.values, dtype=float)
    out = np.full(len(v), np.nan)
    for i in range(12, len(v)):
        a, b = v[i], v[i - 12]
        if np.isfinite(a) and np.isfinite(b) and b != 0:
            out[i] = (a / b - 1) * 100.0
    return pd.Series(out, index=s.index)


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
_es_w = trust['excess_spread_pct'].dropna().iloc[-25:]
_es_y = lvl_yoy(tail_contiguous(trust['excess_spread_pct']), True).iloc[-25:].dropna()
# 图注里的同比读数必须跟次轴用同一个单位，所以走的是同一个 pp_unit()（同一份判据、
# 同一批输入 → 同一个答案）。写死「pp」的话，哪个月轴切到 bp 图注就开始自相矛盾。
_ES_MULT, _ES_UNIT, _ = pp_unit(_es_y.values)
_es_d = 0 if _ES_UNIT == 'bp' else 2
ex.append(gs_bar_ex(
    8, SEC_T + 'Trust excess spread', trust['excess_spread_pct'],
    win=25, yfmt='pct1', fmt='pct1', ylab='%', pct_series=True,
    note=f'窗口内超额利差始终在 {_es_w.min():.2f}%–{_es_w.max():.2f}% 之间（极差只有 '
         f'{_es_w.max() - _es_w.min():.2f}pp）。柱从 0 起是利差的正确基线，'
         f'在这个基线上 {len(_es_w)} 根柱的高度差不到画布的 '
         f'{(_es_w.max() - _es_w.min()) / (_es_w.max() * 1.22) * 100:.0f}%，看上去一样高 ——'
         f'<b>水平请读柱顶数值，变化请读次轴那条金色同比线</b>'
         f'（窗口内 {_es_y.min() * _ES_MULT:+.{_es_d}f}{_ES_UNIT} ~ '
         f'{_es_y.max() * _ES_MULT:+.{_es_d}f}{_ES_UNIT}，'
         f'当期 {_es_y.iloc[-1] * _ES_MULT:+.{_es_d}f}{_ES_UNIT}）。'
         f'本图左右轴零点不同高（引擎已在绘图区左上角标出）：柱全为正而同比跨零，'
         f'强行把两个零点拉到同一高度会把左轴一路扩到 −25% 左右，四成画布是空的。',
    src_extra=TRUST_SRC + '.  Portfolio yield less charge-offs, servicing and note coupon — '
              'the cushion that absorbs losses before noteholders are hit. The single '
              'most-watched number in the trust report'))

ex.append(multi_line_ex(
    9, SEC_T + 'Trust portfolio yield and payment rate', trust,
    ['portfolio_yield_pct', 'payment_rate_pct'], ['NAVY', 'MBLUE'],
    ['Portfolio yield', 'Payment rate'], win=25,
    src_extra=TRUST_SRC + '.  Payment rate is how fast cardholders repay; a falling payment '
              'rate is an early warning that shows up months before delinquency does'))

ex.append(multi_line_ex(
    10, SEC_T + 'Loss rate: trust pool vs. 8-K Card balances', trust,
    ['nco_pct', 'consumer_nco_pct'], ['NAVY', 'RED'],
    ['Trust: annualised default rate, net of recoveries',
     '8-K: U.S. Consumer net write-off rate'], win=25,
    src_extra=TRUST_SRC + '.  The two are close analogues but not the same definition, and '
              + TRUST_NOTE.lower()))

ex.append(multi_line_ex(
    11, SEC_T + 'Delinquency: trust pool vs. 8-K Card balances', trust,
    ['dq30_pct', 'consumer_dq30_pct'], ['NAVY', 'RED'],
    ['Trust: total 30+ days delinquent', '8-K: U.S. Consumer 30+ days past due'], win=25,
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

    f'<b>与原 PDF 的四处有意差异。</b>(1) 原 deck 的 <code>lvl_bar</code>（Exhibit 2/4/6/7/8）'
    f'是「浅蓝柱 + 每柱数值 + 次轴金色同比线」，网页版现在用 <code>gs_bar</code> + '
    f'<code>yoy</code> 逐条还原，<b>不画 12 个月均线</b>（deck 的 docstring：均线只是把柱子'
    f'再平滑一遍、不带新信息）。此前用的 <code>bar_line_dual</code> 形态对、但丢了'
    f'「每柱数值」那一层，而 Exhibit 7 / 8 的全部信息恰好就在那一层。'
    f'Exhibit 12 来自 <code>rev_bar_yoy</code> 而非 <code>lvl_bar</code>，柱是深色 NAVY'
    f'（图例 "Reported"），<code>gs_bar</code> 的柱色写死在引擎里的浅蓝，故仍留 '
    f'<code>bar_line_dual</code>。'
    f'(2) <b>Exhibit 7 是本页唯一不画次轴同比的一张</b>：费率是季度阶梯，同比在整个窗口内'
    f'恒为 {_niy_yy_set[0]:+.2f}pp，是个常数、不带信息，而常数同比的次轴必然退化'
    f'（量程塌成一个点、刻度舍成一列重复读数、末点读数压在最高刻度上）。'
    f'那一张改画 12 个月均线（费率看「当前 vs 过去一年均值」才有意义），常数写进图注；'
    f'生成器里有断言，同比一旦不再是常数就会报错要求改回次轴同比。'
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
    'hub_line': HUB,
    'source': 'Source: AXP 8-K Item 7.01 (SEC CIK 0000004962) and American Express Credit Account '
              'Master Trust Form 10-D (SEC CIK 0001003509); format after J.P. Morgan',
    'xlabels': [mlab(p) for p in TB_WIN],
    'xlabels_long': xl(old.index),
    'summary': summary,
    # 轴刻度小数位：引擎默认格式器把 2.5 印成「3」、把 0.25 步长整列印成重复/错值，
    # 判据与算法见 build/axisfmt.py（与 build/single.py 共用同一份）。
    # 放在全部 exhibit 建完之后统一做一遍，而不是散在每个 ex_* 里 —— 判据只跟最终
    # 量程（含 ycap/yfloor）有关，各处各写一遍必然漏掉后加的图。
    'exhibits': axisfmt.fix_all(ex),
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
