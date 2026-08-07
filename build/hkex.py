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

import numpy as np
import pandas as pd

import payload_guard
import pctile
import yoy as YOY                       # 同比口径的唯一实现，见 build/yoy.py 的模块头

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SERIES = os.path.join(ROOT, 'series')

TICKER = 'hkex'
SRC = 'Source: HKEX Monthly Market Highlights; format after Goldman Sachs GIR'


def source_dates():
    """按路径加载仓库根的 source_dates.py（发布日台账）。

    不能裸 import：本文件是 `python3 build/hkex.py` 跑的，sys.path 上只有 build/，
    仓库根不在上面。
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        'source_dates', os.path.join(ROOT, 'source_dates.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ────────────────────────────── 读数据 ──────────────────────────────
def mlab(p):
    return p.strftime('%b-%y')


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


# ══════════════════ 同比口径：次轴一律画 12 个月滚动合计同比 ══════════════════
# 单月同比 = 本月 ÷ 去年同月 − 1，它把「去年那**一个**月碰巧是什么样」整个塞进分母。
# 港股的月度成交额本来就大起大落，去年同月若是异常低点，今年一个平淡的月份也能印出
# 三位数增速。后果不是「噪声大一点」，而是**方向会反**：本页 ADT 的单月同比与它的
# 12 个月滚动合计同比在两成以上的月份符号相反，图上讲的是反的故事，而读者从图上完全
# 看不出来（实测数字由 caliber_stats() 现算，见 notes 的口径条与各图图注，一个都没写死）。
#
# 因此本页所有 gs_bar 的次轴金色折线改画「12 个月滚动合计同比」：
#     最近 12 个月合计 ÷ 上一个 12 个月合计 − 1
# 实现上取滚动**均值**再相比 —— 窗口固定 12 个月，除以 12 是同一个常数，所以
# 「滚动均值同比」与「滚动合计同比」逐点严格相等；用均值的好处是 ADT 这类日均值源列的
# 单位保持「HK$bn/日」不变，读者不必换算。
#
# 交易日加权：**不乘**。本页 Exhibit 7 早就定过这条口径 ——「ADT 本身已经是『每日』口径，
# 合计会随季内交易日数变化而失真」，季度柱因此取简单平均而不是合计。滚动 12 个月若改成
# 「ADT × 交易日」求和，等于在同一页里引入第二套聚合口径，和 Exhibit 7 直接打架；
# 何况 series/fee_rates.csv 里的交易日数只有 2023-Q4 起十个季度，乘上去会把整条滚动
# 同比从 2019 年砍到 2025 年。既有做法优先，不引入第二套。
ROLL = 12


def roll_mean(s):
    """12 个月滚动均值（TTM 水平值与分解的「合计 ÷ 合计」用）。窗口不满 12 个月一律
    NaN —— 不做 min_periods 降级：用 3 个月凑出来的「滚动值」和满窗的值不可比，
    画在同一条线上就是静默造假。

    与 YOY.ttm() 只差一个常数 12。这里用均值而不是合计，是因为本页的量类源列都是
    **日均值**（ADT / 成交股数 / 笔数），除以 12 之后单位不变，读者不必换算；
    两者的同比逐点严格相等。
    """
    return pd.Series(s).rolling(ROLL, min_periods=ROLL).mean()


def caliber_stats(s, kind=YOY.FLOW):
    """单月同比 vs 12 个月滚动合计同比的实测对比（图注引用的数字全由此现算）。

    只做键名适配：真正的统计（样本对齐、相邻月跳变、符号相反的月份）全部走
    build/yoy.py 的 caliber_diff —— 那是全站唯一实现，各页各写一份正是同一条序列
    在两页被判定相反的原因。样本对齐这一步尤其不能自己重写：滚动同比比单月同比少
    12 个月历史，不取交集就会把「样本不同」读成「口径不同」。
    """
    d = YOY.caliber_diff(pd.Series(s), kind)
    opp = pd.DataFrame([{'m': m, 'r': r} for _, m, r in d['opposite']],
                       index=[p for p, _, _ in d['opposite']])
    return {'n': d['n'], 'first': d['months'][0], 'last': d['months'][-1],
            'sd_m': d['std_mom'], 'sd_r': d['std_ttm'],
            'jump_m': d['maxjump_mom'][0], 'jump_m_at': d['maxjump_mom'][2],
            'jump_r': d['maxjump_ttm'][0] if d['maxjump_ttm'] else float('nan'),
            'n_opp': d['opposite_n'], 'opp': opp}


def yoy_line(s_full, win=25, kind=YOY.FLOW):
    """次轴折线的数值。**流量**走 12 个月滚动合计同比，**存量 / 比率**走点对点同比。

      · 流量（ADT、成交股数、衍生品张数、隐含费收入）：滚动口径，理由见上方 ROLL 那一段；
      · 存量（市值，月末快照）：点对点。把 12 个月末的市值加起来不是任何东西 ——
        既不是「一年的量」（存量不累积），也不是「平均水平」（没除以 12）；
        而且存量不吃日历效应，单月同比在它上面本来就稳得多；
      · 比率（换手率）：点对点的**百分点差**，不是「百分比的百分比变化」。

    三条判据与实现都在 build/yoy.py（全站唯一），本文件只负责说清「这一列是哪一类」——
    kind 猜错的代价不对称，所以它是每个调用点显式写出来的，没有按列名自动判定。
    同比一律在**切窗口之前**算：窗口只有 25 个月，切完再算前面的柱全没有线。
    """
    s = pd.Series(s_full)
    out = YOY.ttm_yoy(s, YOY.FLOW) if kind == YOY.FLOW else YOY.mom_yoy(s, kind)
    return np.asarray(out.values, float)[-win:]


def yoy_rhs(s_full, win=25, kind=YOY.FLOW):
    """gs_bar 的次轴 y/y 字段（给了它引擎就画同比折线、不画均线）。

    2026-08 改口径：**流量**序列的折线由单月同比改为 12 个月滚动合计同比；存量与比率
    序列<b>不改</b>（理由见 yoy_line）。图例名与右轴标题随口径走 —— 只改数不改名，
    读者会拿一条已被平滑过的线当单月同比读，那比不改更糟；反过来，存量图若不写明
    「单月」，读者又会把它和滚动折线放在一起比。
    """
    roll = (kind == YOY.FLOW)
    pct_series = (kind == YOY.RATIO)
    tag = '12M rolling y/y' if roll else 'y/y, single month'
    return {
        'name': f'{tag} (pp, RHS)' if pct_series else f'{tag} (RHS)',
        'color': 'GOLD',
        'yfmt': 'pp0' if pct_series else 'pct0',
        'values': LN(yoy_line(s_full, win, kind)),
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


def main():
    df = load()
    RAW_COLS = list(df.columns)          # 派生列加进去之前的原始列，供下面的成交股数探测用

    # ══════════ 现货量价分解的数据条件：有没有成交股数那一列 ══════════
    # 「成交额 = 成交量 × 均价」要的是**成交股数**。它不在 Monthly Market Highlights 里，
    # 而在另一份刊物 Monthly Bulletin（栏目原文「Turnover volume (mil shares)」），
    # 所以本仓早期的 series/hkex.csv 没有它。抓取补上之后列名是 adv_shares_mn。
    #
    # 这里做成**条件分支而不是硬依赖**：抓取模块与本文件由不同的人/进程改，那一列在过程中
    # 会来回出现与消失（实测就撞上过一次中途回滚）。硬依赖的后果是整页在别人改文件的
    # 几分钟里停更 —— 把成本转嫁给了别人。有列就画分解、没列就如实写「不具备数据条件」，
    # 两条路的图注各说各的实话，页面在哪种状态下都建得出来。
    # 三段分解要三条腿都在：日均成交股数 + 日均成交笔数（金额那条 adt_hkdbn 一直都在）。
    # 两者由同一次抓取一起入库，所以这里要求**同时**存在 —— 只有其中一条时退回两段分解
    # 会多出一条永远走不到的分支，而分支写了不跑就是坏的。
    HAS_VP = {'adv_shares_mn', 'adt_trades'} <= set(RAW_COLS)
    HAS_TD = 'trading_days_cash' in RAW_COLS
    SHARE_COLS = [c for c in RAW_COLS
                  if 'share' in c.lower() or 'volume' in c.lower() or 'shr' in c.lower()]
    # 图号随数据条件走：有量价分解就多两张图，核对表跟着往后顺延。全文引用一律走这三个
    # 变量，不写字面量 —— 否则列一来一回，正文里的「见 Exhibit 20」就会指到别的图上。
    EX_VP, EX_TTMVOL, EX_TABLE = (19, 20, 21) if HAS_VP else (None, None, 19)
    # 只有画了分解才有这几个实测值；没画时正文里引用它们的句子整段不出现。
    CROSS_MED = CROSS_MAX = DAYW_GAP = None
    DAYW_SAME = False

    # 列在但语义变了，比列不在危险得多：一个单位写错的「均价」在图上完全看不出来，
    # 方向和大小都不可知。所以列一旦出现就**必须**通过闭合检验，不通过就硬失败退出
    # （CONTRACT §5.5「失败要响，绝不静默写 NaN 上线」的同一条理由）。
    if HAS_VP and HAS_TD:
        for _tot, _parts in (('adv_shares_mn', ('vol_shares_mb_mn', 'vol_shares_gem_mn')),
                             ('adt_trades', ('trades_mb_total', 'trades_gem_total'))):
            if not set(_parts) <= set(RAW_COLS):
                continue
            _chk = (df[_parts[0]] + df[_parts[1]]) / df['trading_days_cash']
            _rel = float(((_chk - df[_tot]) / df[_tot]).abs().max())
            if not np.isfinite(_rel) or _rel > 1e-4:
                raise SystemExit(
                    f'series/hkex.csv 的 {_tot} 不再等于（{_parts[0]} + {_parts[1]}）÷ '
                    f'trading_days_cash：最大相对误差 {_rel:.2e}（上限 1e-4）。'
                    f'Exhibit 的量价分解靠这条恒等式确认「股数／笔数与成交金额是同一个市场、'
                    f'同一批交易日」，它一破，算出来的均价与每笔股数就不再有经济含义 —— '
                    f'图上完全看不出来，所以这里必须停。请先核对列的口径与单位')

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
        # 隐含均价 = 当月成交金额 ÷ 当月成交股数（HK$/股）。两条腿同市场、同交易日、
        # 同「日均」基准，所以这个商有经济含义 —— 但它是主板 + GEM 上所有品种的**混合**
        # 均价（含窝轮牛熊证，以仙计价、股数极大），不是任何一只股票的价格。
        if HAS_VP:
            d['implied_px_hkd'] = d['adt_hkdbn'] * 1e9 / (d['adv_shares_mn'] * 1e6)
            # 每笔股数 = 成交股数 ÷ 成交笔数（股/笔）。它测的是**订单碎片化程度**，与价格
            # 无关 —— 算法单把大单拆小，这个数就往下走，而成交额可以一分不变。
            d['shares_per_trade'] = d['adv_shares_mn'] * 1e6 / d['adt_trades']

    # ── TTM 序列：比率一律用「合计 ÷ 合计」，不是「逐月比率的均值」──
    # 逐月换手率的简单平均对每个月等权，而各月成交额差着数倍；更要命的是均值之积 ≠
    # 积之均值，所以 TTM 平均 ADT ≠ TTM 平均市值 × 逐月换手率的均值 —— 恒等式一破，
    # Exhibit 的分解两块相加就对不上总增长，而图上完全看不出来。
    # 这里重算的 TTM 换手率满足 TTM_ADT ≡ TTM_市值 × TTM_换手率 / 252，是恒等式。
    df['ttm_adt'] = roll_mean(df['adt_hkdbn'])                   # HK$bn/日，近 12 个月均值

    # ── 同比口径的实测：数字全部现算，一个都不写死（见上方 ROLL 那一段的理由）──
    CALIB = caliber_stats(df['adt_hkdbn'])                       # 现货 ADT：全页的口径样本
    CALIB_DV = caliber_stats(df['deriv_adv_k'])                  # 衍生品 ADV：第二个样本
    # 每张改口径的图都要自己说清新口径与理由；完整实测放在 notes 里，这里给一句压缩版。
    YOY_CAL = (f'<b>次轴 = 12 个月滚动合计同比</b>（最近 12 个月合计 ÷ 上一个 12 个月合计 − 1），'
               f'不是单月同比。理由是本页自己的实测：现货 ADT 的单月同比在 {CALIB["n"]} 个'
               f'可比月里有 {CALIB["n_opp"]} 个月（{CALIB["n_opp"] / CALIB["n"] * 100:.0f}%）'
               f'与滚动口径<b>符号相反</b>，相邻月最大跳变 {CALIB["jump_m"]:.0f}pp'
               f'（滚动口径 {CALIB["jump_r"]:.0f}pp）。折线要等 24 个月才有第一个点'
               f'（12 个月填窗 + 12 个月比较），窗口左端因此可能没有线。')

    # 存量图（市值）与比率图（换手率）**不改**口径，但必须各自说清为什么不改，
    # 否则读者会以为漏改了两张，或者把它们的折线和别的图的滚动折线放在一起比高低。
    CALIB_MC = caliber_stats(df['mktcap_hkdtn'], YOY.STOCK)
    STOCK_CAL = (f'<b>次轴 = 单月同比</b>（本月 ÷ 去年同月 − 1），与本页成交量各图的 '
                 f'12 个月滚动合计同比<b>不是一个口径</b>，两者不要放在一起比高低。'
                 f'这里之所以不改：市值是<b>存量</b>（月末快照），把 12 个月末的市值加起来'
                 f'不是任何东西 —— 既不是「一年的量」（存量不累积），也不是「平均水平」'
                 f'（没除以 12）；而且存量不吃日历效应（不像成交额要看当月有几个交易日），'
                 f'单月同比在它上面本来就稳得多。本页实测：市值的单月同比标准差 '
                 f'{CALIB_MC["sd_m"]:.1f}pp、相邻月最大跳变 {CALIB_MC["jump_m"]:.0f}pp，'
                 f'而现货 ADT 是 {CALIB["sd_m"]:.1f}pp 与 {CALIB["jump_m"]:.0f}pp —— '
                 f'成交额非平滑不可，存量不必。判据与实现见 <code>build/yoy.py</code>，'
                 f'对存量序列调滚动合计会直接抛错。')
    RATIO_CAL = ('<b>次轴 = 单月百分点差</b>（本月 − 去年同月），与本页成交量各图的 '
                 '12 个月滚动合计同比<b>不是一个口径</b>。换手率是<b>比率</b>：'
                 '它的分子分母来自同一时点，滚动之后既不再是加权比率、也不再满足'
                 '「ADT = 市值 × 换手率 ÷ 252」这条恒等式（均值之积 ≠ 积之均值）；'
                 '而且比率的变化本来就该用百分点差，不是「百分比的百分比变化」。'
                 '判据与实现见 <code>build/yoy.py</code>。')

    def ttm_yoy(col, at=None):
        """图注 / 抬头里的 TTM 同比读数（**流量列专用**，缺失给「—」）。

        存量与比率列不走这里 —— 它们的合法同比是点对点，直接用 pctf(yoy(...)) /
        ppf(...)，与图上次轴同口径。判据见 yoy_line 的 docstring。
        """
        v = YOY.ttm_yoy(df[col], YOY.FLOW).get(
            at if at is not None else df.index[-1], np.nan)
        return '—' if not np.isfinite(v) else pctf(v / 100.0, 1)

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
        'ylab': 'HK$bn / day', 'ylab2': '% y/y, 12M roll.', 'legend': 'Monthly ADT',
        'values': L(adt_v), 'yoy': yoy_rhs(adt_c),
        # 原句写的是「次轴与原 deck 的 lvl_bar 一致，画的就是 y/y、不是滚动均线」。
        # 改口径之后那句已经不成立：次轴现在画的是 12 个月滚动合计同比，与 deck 有意不同。
        # 图注若还说「与原 deck 一致」，读者会按 deck 的口径去读一条已经不同的线。
        'note': f'次轴金色折线是同比，但<b>与原 deck 的口径有意不同</b>：deck 的 lvl_bar 在'
                f'这个位置画的是<b>单月</b>同比，本页改画 <b>12 个月滚动合计同比</b>'
                f'（理由见下）。deck 当年舍弃 12 个月滚动均线的理由仍然成立 —— 均线只是把'
                f'柱子再平滑一遍、不带新信息，而同比回答「相对去年是好是坏」；'
                f'本页只是把「去年」从一个月换成了十二个月。'
                f'{mlab(adt.index[-1])} 的 ADT 为 HK${adt_v[-1]:,.1f}bn/日，'
                f'TTM 同比 {ttm_yoy("adt_hkdbn", adt.index[-1])}'
                f'（单月同比 {pctf(yoy(adt_v), 1)}、m/m {pctf(mom(adt_v), 1)}）。'
                # 这一页正是「单月同比讲反故事」的样本：Jun-24 单月 +11.5%、滚动 −10.2%。
                # 该月份与读数由 CALIB 现算列出，随数据滚动，不写死。
                + (f'<b>这条序列本身就是反例</b>：'
                   + '、'.join(
                       f'{mlab(p)} 单月 {r["m"]:+.1f}% 而滚动 {r["r"]:+.1f}%'
                       for p, r in CALIB['opp'].loc[
                           CALIB['opp']['m'].abs().sort_values().index[-2:]].iterrows())
                   + ' —— 同一个月，两种口径给出方向相反的结论。'
                   if len(CALIB['opp']) >= 2 else '') + YOY_CAL,
    })

    # ══════════ Exhibit 3：ADT m/m 变化率（gsx.chg_line, win=25, kind='mom'）══════════
    full_adt = tail_contiguous(df['adt_hkdbn'])
    mm = full_adt.pct_change() * 100
    mm = mm.iloc[-25:]
    ex.append({
        'n': 3, 'kind': 'gs_line', 'fmt': 'pct1', 'xlabels': [mlab(p) for p in mm.index],
        'title': 'ADT, m/m change',
        'ylab': '% m/m', 'values': L(mm.values),
        # 环比不平滑：这是「本月 vs 上月」的运营监控指标，读者要的就是「这个月掉了多少」。
        # 把它换成 12 个月滚动值，图上剩下的是一条几乎平的线，这张图就没有存在意义了。
        'note': '与 Exhibit 2 同一序列的环比。ADT 的月度波动本身就是这门生意的收入波动，'
                '所以水平值与变化率成对看。'
                '<b>本图是环比（本月 vs 上月），不是同比，也没有做 12 个月滚动平滑</b> —— '
                '它回答的是「这个月相对上个月怎么样」这个运营问题，平滑掉就什么也不剩了。'
                '与 Exhibit 2 次轴那条 12 个月滚动同比金色折线<b>不是一个口径</b>，'
                '两者不要放在一起读：本图讲当月动能，那条线讲趋势方向。',
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
        # height：开了 end_label 的 lines 图，末点若恰好是全图最大值（本图正是 ——
        # 整体 ADT 的末点 319.1 就是两条线的最高点），标签会落在绘图区顶缘 3.6px 处，
        # 触发 charts.js spreadY 的「上下都顶满」兜底 —— 整列末点标签被收成一摞贴在
        # 右上角，南向那条的 129.2 会被摆到距自己的线 158px 的高处，读者会把它当成
        # 整体 ADT 的第二个读数。判据是纯几何（通用留白分支下 ph > 308 才安全），
        # 与 build/exchanges.py 的 LINE_H_ENDLABEL 同一条，取同一个值 360。
        # 由 build/verify_pages.py 复算引擎公式抓出。
        'height': 360,
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
        'ylab': 'k contracts / day', 'ylab2': '% y/y, 12M roll.', 'legend': 'Monthly derivatives ADV',
        'values': L(dv_v), 'yoy': yoy_rhs(dv_c),
        'note': f'期货与期权合计，公司披露的原始单位是张数，此处除以 1,000 显示为「千张/日」'
                f'（核对表里给原始张数）。{mlab(dv.index[-1])} 的 ADV 为 {dv_v[-1]:,.0f} 千张/日，'
                f'TTM 同比 {ttm_yoy("deriv_adv_k", dv.index[-1])}'
                f'（单月同比 {pctf(yoy(dv_v), 1)}）。衍生品比现货多披露一个月。'
                f'本序列的单月同比比现货更毛：{CALIB_DV["n"]} 个可比月里有 {CALIB_DV["n_opp"]} 个月'
                f'（{CALIB_DV["n_opp"] / CALIB_DV["n"] * 100:.0f}%）与滚动口径符号相反，'
                f'单月同比标准差 {CALIB_DV["sd_m"]:.1f}pp、滚动口径 {CALIB_DV["sd_r"]:.1f}pp。'
                + YOY_CAL,
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
                + ('（完整季）。' if n_in_last >= 3 else '，未满季与完整季不可比，右轴 y/y 已作废。')
                # 季度柱的右轴是本页的**第三种**同比口径。柱是季度的，线就必须与柱同期，
                # 改成 12 个月滚动会让线与柱指的不是同一段时间 —— 那比口径不统一更糟。
                + f'<b>右轴的同比口径与其余各图不同</b>：这里是「本季 3 个月 vs 上年同季 3 个月」，'
                  f'既不是单月同比、也不是各 gs_bar 次轴的 12 个月滚动合计同比。'
                  f'柱是季度口径，线只能与柱同期，否则线讲的是另一段时间。'
                  f'三个月已经压掉一部分单月毛刺，但仍比 12 个月滚动口径敏感得多，'
                  f'跨图比高低没有意义。'
                  f'本页三种口径的分工见「口径与方法说明」的同比口径条。',
    })

    # ══════════ Exhibit 8：市值（gsx.lvl_bar, win=25, show_mom=True）══════════
    mc_c = tail_contiguous(df['mktcap_hkdtn'])
    mc = mc_c.iloc[-25:]
    mc_v = mc.values
    ex.append({
        'n': 8, 'kind': 'gs_bar', 'fmt': 'f1', 'xlabels': [mlab(p) for p in mc.index],
        'title': 'Securities market capitalisation',
        'ylab': 'HK$tn', 'ylab2': '% y/y, single month', 'legend': 'Month-end market cap',
        # 市值是**存量**（月末快照）：不可加总，且不吃日历效应，点对点同比在它上面本来
        # 就稳（见 yoy_line 的判据）。全页只有这张与 Exhibit 9 走非滚动口径。
        'values': L(mc_v), 'yoy': yoy_rhs(mc_c, kind=YOY.STOCK),
        'note': f'期末口径。{mlab(mc.index[-1])} 为 HK${mc_v[-1]:,.1f}tn，'
                f'y/y {pctf(yoy(mc_v), 1)}、m/m {pctf(mom(mc_v), 1)}（次轴金色折线即这条 y/y）。'
                '它是 Exhibit 9 换手率的分母：成交额与市值的差额正是换手率在动。' + STOCK_CAL,
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
        'ylab': '% of market cap, annualised', 'ylab2': 'pp y/y, single month',
        'legend': 'Implied velocity (%)',
        # 比率序列走点对点的百分点差：换手率的分子分母都是同一时点的读数，
        # 滚动之后既不是加权比率、也不再满足「ADT = 市值 × 换手率」（均值之积 ≠ 积之均值）。
        'values': L(vel_v), 'yoy': yoy_rhs(vel_c, kind=YOY.RATIO),
        'note': 'ADT x 252 / market cap — the ratio GS uses to judge whether turnover is '
                'structurally higher。<b>推导值，非公司披露</b>：252 是惯例年化交易日数，'
                '不是当年实际交易日数；分母用当月期末市值。比率序列的同比用百分点差，'
                f'{mlab(vel.index[-1])} 为 {vel_v[-1]:,.1f}%，'
                f'y/y {ppf(vel_pp, 1)}（次轴金色折线即这条百分点差）。'
                + RATIO_CAL,
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
        'ylab': 'HK$mn / month', 'ylab2': '% y/y, 12M roll.', 'legend': 'Implied trading fee',
        'values': L(tfee_v), 'yoy': y10,
        'note': BR_NOTE + f' 费率与交易日数只有 {tf_list.index[0]} 起 {len(tf_list)} 个季度，'
                          f'故整条隐含序列自 {mlab(tfee_c.index[0])} 起（图上按惯例只画最近 '
                          f'{len(tfee)} 个月，即 {mlab(tfee.index[0])} 之后）；'
                          f'次轴改画 12 个月滚动合计同比后要等序列满 <b>24</b> 个月'
                          f'（12 个月填窗 + 12 个月比较），因此从 '
                          f'{first_yoy_month(tfee.index, y10)} 才有点 —— 折线比柱短是口径的'
                          f'必然结果，不是缺数。费率序列本身只有十个季度，这条线因此比本页'
                          f'其他 gs_bar 的次轴短得多。'
                          '季内各月同费率，最新季之后沿用。'
                          '月度交易日数按「季度交易日数 ÷ 3」摊，不是当月实际交易日数。'
                          '单位用 HK$mn（公司分部收入的披露单位），原 deck 是 HK$bn 保留两位小数，'
                          '两者等价。' + YOY_CAL + ' '
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
        'ylab': 'HK$mn / month', 'ylab2': '% y/y, 12M roll.', 'legend': 'Implied clearing fee',
        'values': L(cfee_v), 'yoy': y13,
        'note': CLR_NOTE + ' 清算费有最低/最高收费与 CCASS 结算费等分项，倒算出的有效费率把这些'
                           '一并吸收进去了，所以它随 mix 漂移，不能当法定费率读。'
                           f'次轴自 {first_yoy_month(cfee.index, y13)} 起才有点 —— '
                           f'12 个月滚动合计同比要等序列满 <b>24</b> 个月'
                           f'（12 个月填窗 + 12 个月比较），而费率序列本身只有十个季度。 '
                + YOY_CAL + ' '
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

    # ══════════ Exhibit 19：现货成交额的三段分解（真·量价，不是费率分解）══════════
    # 恒等式：成交额 ≡ 成交笔数 × 每笔股数 × 每股单价。定义式，零假设 ——
    # 每笔股数 ≡ 成交股数 ÷ 笔数，每股单价 ≡ 成交额 ÷ 成交股数，代回去逐项抵消。
    # 为什么分三段而不是两段：两段（股数 × 单价）会把「下单行为」与「订单碎片化」揉在
    # 「股数」那一块里。港股这两年的实际情形正是二者反向 —— 笔数在涨、每笔股数在跌，
    # 合成的股数增速看不出这是「更多人在交易」还是「同样的人拆更多单」。
    #
    # 三条腿是不是同口径 —— 这是全图唯一值得担心的事，逐条核对过：
    #   · adt_hkdbn     = 证券市场平均每日成交**金额**（HK$bn/日）
    #   · adv_shares_mn = 主板 + GEM 平均每日成交**股数**（mn 股/日）
    #   · adt_trades    = 主板 + GEM 平均每日成交**笔数**（笔/日）
    #   后两条实测 ≡（主板 + GEM 月度合计）÷ trading_days_cash（上面的闭合检验硬卡 1e-4），
    #   且抓取侧核对过：有 adt_hkdbn 的 90 个月里主板 + GEM 相加 100% 逐位重现既有金额值，
    #   所以三条腿是同一套逐日底稿，不是「口径相近」。
    # 反例（本页拒绝做的那种）：拿南向 ADT 或衍生品张数当分子分母，那是跨市场相除。
    #
    # 口径纪律与 CME / Cboe 两页同一套，跨页可比：
    # （1）每一层的「单位量」一律用「合计 ÷ 合计」（TTM 金额 ÷ TTM 股数、TTM 股数 ÷ TTM 笔数），
    #      不是「逐月比率的平均」—— 后者对每月等权而各月量差着数倍，且均值之积 ≠ 积之均值，
    #      分解会不闭合，而图上完全看不出来。
    # （2）端点用 TTM12（截至该月的 12 个月）对比 12 个月前的 TTM12，不做点对点。
    # （3）图上用**对数分解**：ln(额比) = ln(笔数比) + ln(每笔股数比) + ln(单价比)，
    #      天然可加、对称、零残差，不必选「交叉项归谁」。算术分解必须选一个替换次序，
    #      交叉项会整段压进最后替换的那一块；三段的交叉项比两段更大，方向对冲的年份
    #      画出来就是错的。算术版仍照算，两者的差写进图注。
    # （4）单位是**对数点**（100 × ln），不是百分点：不把对数贡献按总增长等比缩放回百分点，
    #      是因为那要除以 ln(额比)，净增长近零的月份分母也近零，同一个病又回来了。
    # 三条腿齐了才画这两张；缺任何一条就整段跳过，页面照常建得出来（见上面 HAS_VP 那段）。
    if HAS_VP:
        df['ttm_shares'] = roll_mean(df['adv_shares_mn'])                  # mn 股/日
        df['ttm_trades'] = roll_mean(df['adt_trades'])                     # 笔/日
        df['ttm_spt'] = df['ttm_shares'] * 1e6 / df['ttm_trades']          # 股/笔 = 合计 ÷ 合计
        df['ttm_px'] = df['ttm_adt'] * 1e9 / (df['ttm_shares'] * 1e6)      # HK$/股 = 合计 ÷ 合计
        _vp = df[['ttm_adt', 'ttm_shares', 'ttm_trades', 'ttm_spt', 'ttm_px']].dropna()
        _a1, _a0 = _vp['ttm_adt'], _vp['ttm_adt'].shift(ROLL)
        _t1, _t0 = _vp['ttm_trades'], _vp['ttm_trades'].shift(ROLL)
        _s1, _s0 = _vp['ttm_spt'], _vp['ttm_spt'].shift(ROLL)
        _x1, _x0 = _vp['ttm_px'], _vp['ttm_px'].shift(ROLL)
        _rt, _rs, _rx = _t1 / _t0, _s1 / _s0, _x1 / _x0
        _dec = pd.concat({
            'tot': np.log(_a1 / _a0) * 100,
            'trd': np.log(_rt) * 100,
            'spt': np.log(_rs) * 100,
            'px': np.log(_rx) * 100,
            # 算术分解：按「笔数 → 每笔股数 → 单价」的次序逐层替换，望远镜式相加恒等于总增长；
            # 代价是交叉项全部落在最后替换的单价那一块，所以它只进图注、不画。
            'arith_tot': (_a1 / _a0 - 1) * 100,
            'arith_trd': (_rt - 1) * 100,
            'arith_spt': (_rs - 1) * _rt * 100,
            'arith_px': (_rx - 1) * _rt * _rs * 100,
        }, axis=1).dropna()

        # 硬护栏：分解是恒等式，不是近似。对不上说明某处 shift / 口径写错了，必须停在这里 ——
        # 「三块加起来不等于总数」的分解图，读者是看不出来的。两种分解各查各的。
        for _tag, _pp3, _pt in (('对数', ('trd', 'spt', 'px'), 'tot'),
                                ('算术', ('arith_trd', 'arith_spt', 'arith_px'), 'arith_tot')):
            _res = float((sum(_dec[c] for c in _pp3) - _dec[_pt]).abs().max())
            if not np.isfinite(_res) or _res > 1e-9:
                raise SystemExit(f'Exhibit {EX_VP} {_tag}分解不闭合：'
                                 f'max|笔数+每笔股数+单价−总| = {_res:.3e}（上限 1e-9）')

        # 两种分解在「单价」那一块差最多 —— 交叉项全压在它身上，正是不画算术版的理由
        _lgap = float((_dec['px'] - _dec['arith_px']).abs().max())
        _lgap_at = (_dec['px'] - _dec['arith_px']).abs().idxmax()
        # 「算术分解里交叉项占净增长多大」的实测值：总增长 − 三段各自的独立变化率
        _cross = _dec['arith_tot'] - ((_rt - 1) + (_rs - 1) + (_rx - 1)).reindex(_dec.index) * 100
        _csh = (_cross / _dec['arith_tot']).abs().replace([np.inf, -np.inf], np.nan).dropna() * 100
        CROSS_MED, CROSS_MAX = float(_csh.median()), float(_csh.max())

        # 交易日加权 vs 不加权：现在 series 里有 trading_days_cash 了，这个取舍可以实测而不是
        # 靠推理。仍然沿用不加权 —— Exhibit 7 早就定过「ADT 已是每日口径，合计会失真」——
        # 但把加权口径的差算出来写进图注，读者才能判断这个取舍值不值。
        _wsum = (df['adt_hkdbn'] * df['trading_days_cash']).rolling(ROLL).sum()
        _dsum = df['trading_days_cash'].rolling(ROLL).sum()
        _wadt = _wsum / _dsum                                   # 交易日加权的 TTM 日均成交额
        _w_yoy = (_wadt / _wadt.shift(ROLL) - 1) * 100
        _u_yoy = (df['ttm_adt'] / df['ttm_adt'].shift(ROLL) - 1) * 100
        _cmp = pd.concat([_u_yoy, _w_yoy], axis=1, keys=['u', 'w']).dropna()
        DAYW_GAP = float((_cmp['u'] - _cmp['w']).abs().max())
        DAYW_SAME = bool(((_cmp['u'] * _cmp['w']) > 0).all())

        _DW = _dec.index[-13:]
        _dw = _dec.loc[_DW]
        ex.append({
            'n': EX_VP, 'kind': 'bridge_bar', 'fmt': 'f1', 'xlabels': [mlab(p) for p in _DW],
            'xrot': 0,
            'title': 'Cash turnover growth split: trades x shares per trade x price per share',
            'ylab': 'log points of TTM turnover growth',
            'stacks': [
                {'name': 'Number of trades', 'color': 'NAVY', 'values': LN(_dw['trd'].values)},
                {'name': 'Shares per trade', 'color': 'MBLUE', 'values': LN(_dw['spt'].values)},
                {'name': 'Price per share', 'color': 'GOLD', 'values': LN(_dw['px'].values)},
            ],
            'net': {'name': 'TTM turnover growth', 'values': LN(_dw['tot'].values)},
            'net_color': 'INK',
            'src_extra': 'Identity: turnover value = trades x shares per trade x price per share. '
                         'All three legs are HKEX monthly disclosures for the same market '
                         '(Main Board + GEM cash) over the same trading days',
            'note': (f'<b>恒等式：成交额 ≡ 成交笔数 × 每笔股数 × 每股单价</b> —— 定义式，'
                     f'没有任何估算成分（每笔股数 ≡ 成交股数 ÷ 笔数，每股单价 ≡ 成交额 ÷ '
                     f'成交股数，代回去逐项抵消）。<b>为什么分三段</b>：两段（股数 × 单价）'
                     f'会把「有多少人在交易」与「同一批人把单子拆得多碎」揉进同一块，'
                     f'而港股这两年正是二者反向 —— 笔数在涨、每笔股数在跌，合起来看就丢了信息。'
                     f' <b>三条腿同口径</b>：成交金额（ADT）、成交股数、成交笔数都来自 HKEX 月度'
                     f'披露、同一个现货证券市场（主板 + GEM）、同一批交易日、同一个「日均」基准；'
                     f'股数与笔数实测 ≡（主板 + GEM 月度合计）÷ 当月交易日数，生成脚本对这条'
                     f'恒等式设了 1e-4 的硬门槛，破了直接退出。'
                     f'<b>本页拒绝的凑法</b>：南向 ADT 与衍生品张数分属另外两个市场，'
                     f'拿它们当现货的分子分母是跨市场相除，商出来的「单价」方向与大小都不可知。'
                     f' <b>口径</b>：端点用 TTM12（截至该月的 12 个月）对比 12 个月前的 TTM12，'
                     f'与本页各图次轴同比一致；每一层的单位量都用「合计 ÷ 合计」'
                     f'（TTM 金额 ÷ TTM 股数、TTM 股数 ÷ TTM 笔数），不是逐月比率的平均。'
                     f' <b>用对数分解</b>：ln(额比) = ln(笔数比) + ln(每笔股数比) + ln(单价比)，'
                     f'天然可加、对称、零残差，不必选「交叉项归谁」；算术分解必须选一个替换次序，'
                     f'交叉项会整段压进最后替换的那一块，本页实测交叉项占净增长中位 '
                     f'{CROSS_MED:.1f}%、最大 {CROSS_MAX:.0f}%，两种分解的「单价」这一块'
                     f'最大相差 {_lgap:.1f}（出现在 {mlab(_lgap_at)}）。'
                     f' <b>单位是对数点</b>（100 × ln），不是百分点：小幅变化时两者近似相等，'
                     f'大幅时不等。{mlab(_DW[-1])}：笔数 {float(_dw["trd"].iloc[-1]):+.1f}、'
                     f'每笔股数 {float(_dw["spt"].iloc[-1]):+.1f}、'
                     f'单价 {float(_dw["px"].iloc[-1]):+.1f}，合计 '
                     f'{float(_dw["tot"].iloc[-1]):+.1f} 对数点，对应算术总增长 '
                     f'{pctf(float(_dw["arith_tot"].iloc[-1]) / 100.0, 1)}；'
                     f'水平值 TTM 每笔 {float(_vp["ttm_spt"].iloc[-1]):,.0f} 股、'
                     f'TTM 单价 HK${float(_vp["ttm_px"].iloc[-1]):.4f}/股。'
                     f' <b>三块各读什么</b>：笔数 = 交易活动的广度；'
                     f'每笔股数 = <b>订单碎片化程度</b>，与价格无关（算法单把大单拆小，'
                     f'这一块就往下走）；单价 = <b>加权平均成交价</b>，'
                     f'既含市场涨跌、也含<b>成交结构变化</b> —— 分母把主板 + GEM 上所有品种的'
                     f'成交股数加在一起（股票、ETF、窝轮与牛熊证、债券），而窝轮牛熊证以「仙」'
                     f'计价、股数极大，低价品种的成交占比一升这条单价就下移，哪怕每只股票的'
                     f'价格都没动。<b>它不是恒生指数的收益率</b>，也不是任何一只股票的价格。'
                     f'<b>它更不是 Exhibit 10 / 13 那种费率分解</b>：那里的「费率」是 HKEX 向'
                     f'客户收的交易费，本图的「单价」是标的资产的成交价格，两者不可混为一谈。'),
        })

        # ══════════ Exhibit 20：量本身（TTM 水平值 + 同源增速曲线）══════════
        # 「量的数据 + 量的增速曲线」单独成图 —— 分解图里的「量」那一块自己的水平线。
        # 为什么不是「月度成交股数 + 滚动同比」：那样又是一张毛刺图，而本页已经有 Exhibit 2
        # （金额口径）在承担「看单月水平」这个角色。这里画近 12 个月的**平均**成交股数，
        # 好处是柱与次轴的金色线同源 —— 线上任一点的增速就是这根柱相对 12 根柱之前的涨幅。
        _tv = df['ttm_shares'].dropna()
        _TW = _tv.index[-25:]
        _tv_yoy = (df['ttm_shares'] / df['ttm_shares'].shift(ROLL) - 1) * 100
        CALIB_SH = caliber_stats(df['adv_shares_mn'])
        ex.append({
            'n': EX_TTMVOL, 'kind': 'gs_bar', 'fmt': 'f0c', 'xlabels': [mlab(p) for p in _TW],
            'title': 'Cash share volume, trailing 12-month average',
            'ylab': 'mn shares / day, TTM avg', 'ylab2': '% y/y, 12M roll.',
            'legend': 'Trailing 12-month average share volume',
            'values': LN(_tv.loc[_TW].values),
            'yoy': {'name': '12M rolling y/y (RHS)', 'color': 'GOLD', 'yfmt': 'pct0',
                    'values': LN(_tv_yoy.reindex(_TW).values)},
            'src_extra': f'The volume leg of Exhibit {EX_VP}, shown as a level. Main Board + GEM '
                         'turnover volume divided by cash-market trading days',
            'note': (f'柱 = 截至该月的近 12 个月<b>平均</b>成交股数（百万股/日，主板 + GEM）。'
                     f'成交股数 ADV 本身已是「每日」口径，12 个月合计再除以 12 就回到同一单位，'
                     f'所以这里给均值而不是合计 —— 两者的同比逐点严格相等（除以 12 是同一个'
                     f'常数），换算不影响任何结论；这也与 Exhibit 7 季度柱取简单平均的既定口径'
                     f'一致，本页不引入第二套聚合口径。'
                     f'金色线 = 该均值相对上一个 12 个月均值的同比，柱与线<b>同源</b> —— '
                     f'线上任一点的读数就是这根柱相对 12 根柱之前的涨幅。'
                     f'{mlab(_TW[-1])} 为 {float(_tv.loc[_TW[-1]]):,.0f} 百万股/日，'
                     f'{pctf(float(_tv_yoy.get(_TW[-1], np.nan)) / 100.0, 1)} y/y。'
                     f'单月毛刺在这条 TTM 曲线上看不到，这正是它的用处：成交股数的单月同比在 '
                     f'{CALIB_SH["n"]} 个可比月里有 {CALIB_SH["n_opp"]} 个月'
                     f'（{CALIB_SH["n_opp"] / CALIB_SH["n"] * 100:.0f}%）与滚动口径符号相反，'
                     f'相邻月最大跳变 {CALIB_SH["jump_m"]:.0f}pp，TTM 口径只有 '
                     f'{CALIB_SH["jump_r"]:.0f}pp。'
                     f'与 Exhibit 2 的区别：那张是成交<b>金额</b>的月度水平值，本图是成交'
                     f'<b>股数</b>的趋势水平线，两者之比就是 Exhibit {EX_VP} 里的均价。'),
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
    if HAS_VP:
        # Exhibit EX_VP 三段分解的三条腿 + 中间量。分解图上只画贡献（对数点），水平值必须
        # 在表里给得出来，否则读者没有任何办法自己复核「每笔股数」与「单价」是怎么来的。
        # 插在 ADT 那一行之后（同属现货驱动量），不是追加在表尾 —— 表的分组是按业务线的。
        # 顺序照恒等式排：笔数 × 每笔股数 = 股数，股数 × 单价 = 成交额。
        SUM[2:2] = [
            ('row', 'Number of trades (per day)', 'adt_trades', 0, 'ratio', False, None),
            ('row', 'Shares per trade', 'shares_per_trade', 0, 'ratio', False, None),
            ('row', 'Turnover volume (mn shares/day)', 'adv_shares_mn', 0, 'ratio', False, None),
            ('row', 'Implied price per share (HK$)', 'implied_px_hkd', 4, 'ratio', False, None),
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
        'note': '<b>本表的 y/y 是单月同比</b>（本月 ÷ 去年同月 − 1），与各图次轴的 12 个月'
                '滚动合计同比不是一个口径 —— 本表三列写死的就是「本月 / 上月 / 去年同月」'
                '这三个具名月份，滚动值放进来与列头自相矛盾，所以保留单月口径并在此点名。'
                f'单月同比有多毛：本页 ADT 的实测是 {CALIB["n"]} 个可比月里 {CALIB["n_opp"]} 个月'
                f'（{CALIB["n_opp"] / CALIB["n"] * 100:.0f}%）与滚动口径<b>符号相反</b>。'
                f'要判趋势请看各图的次轴金色折线{f"与 Exhibit {EX_TTMVOL}" if HAS_VP else ""}，本表回答的是'
                '「本月相对上月与去年同月的水平」。'
                'Velocity is derived as ADT x 252 / market cap, not a disclosed figure. '
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

    # ══════════ Exhibit 21：核对表（官方原始单位，不换算）══════════
    # 号由 19 顺延到 21：Exhibit 19 / 20 是后加的两张（量价分解、TTM 量），追加在所有图
    # 之后，核对表本来就排在最末，号跟着走才不会出现「18、21、19、20」这种读者以为漏图的
    # 序列。新增的成交股数与交易日数两列是 Exhibit 19 / 20 的输入 —— 分解图的两条腿必须
    # 能被逐格核对，否则读者没有任何办法验证那个「均价」是怎么来的。
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
        # 分解图的两条腿必须能被逐格核对，否则读者没有办法验证那个「均价」是怎么来的。
        # 交易日数一并给出：成交股数 ADV ≡（主板 + GEM 月度股数）÷ 交易日数，
        # 有了这一列读者才复核得了「两条腿是同一批交易日」这个前提。
        if HAS_VP:
            trows[-1]['shr'] = (None if not np.isfinite(r['adv_shares_mn'])
                                else f"{r['adv_shares_mn']:,.0f}")
            trows[-1]['trd'] = (None if not np.isfinite(r['adt_trades'])
                                else f"{r['adt_trades']:,.0f}")
        if HAS_TD:
            trows[-1]['td'] = (None if not np.isfinite(r['trading_days_cash'])
                               else f"{r['trading_days_cash']:,.0f}")
    table = {
        'n': EX_TABLE, 'title': '近 13 个月月度指标核对表（官方原始单位，未换算）',
        'idx': '月份',
        'cols': ([['ADT (HK$bn)', 'adt']]
                 + ([['Turnover volume (mn shares/day)', 'shr'],
                     ['Trades per day', 'trd']] if HAS_VP else [])
                 + ([['Trading days', 'td']] if HAS_TD else [])
                 + [['Market cap (HK$tn)', 'mcap'],
                    ['Southbound ADT (HK$bn)', 'sb'],
                    ['Derivatives ADV (contracts)', 'dv'],
                    ['New listings', 'nl'], ['IPO funds (HK$bn)', 'ipo']]),
        'rows': trows,
    }

    # ══════════ notes ══════════
    notes = [
        '<b>数据源</b>：HKEX 每月公布的 Monthly Market Highlights（月度市场概况）与季度业绩'
        '中的现货分部收入、费率与交易日数。版式沿用 Goldman Sachs GIR 两份 HKEX note'
        '（「New listings and profit growth inflection to drive sustainable ADT growth」'
        'Exhibit 1-15 与「Multiple tailwinds in 2026E despite weak Nov ADT」Exhibit 1-28）：'
        '三层时间窗（超长历史判周期位置 / 中长期判趋势 / 近 25 个月讲当下）、双图开场、驱动量置顶。',

        # ── 同比口径：本页最容易被读反的一条，紧跟在数据源之后 ──
        f'<b>同比一律用 12 个月滚动合计，不是单月同比。</b>单月同比把「去年那<b>一个</b>月'
        f'碰巧是什么样」整个塞进分母。港股月度成交额本来就大起大落，去年同月若是异常低点，'
        f'今年一个平淡的月份也能印出三位数增速。后果不是噪声大一点，而是<b>方向会反</b>。'
        f'本页现货 ADT 的实测（{CALIB["first"]} – {CALIB["last"]}，{CALIB["n"]} 个两种口径'
        f'都有值的月份）：单月同比逐月标准差 <b>{CALIB["sd_m"]:.1f}pp</b>、相邻月最大跳变 '
        f'<b>{CALIB["jump_m"]:.0f}pp</b>（{mlab(CALIB["jump_m_at"])}）；'
        f'12 个月滚动合计同比标准差 <b>{CALIB["sd_r"]:.1f}pp</b>、最大跳变 '
        f'<b>{CALIB["jump_r"]:.0f}pp</b>；两者<b>符号相反</b>的月份有 {CALIB["n_opp"]} 个'
        f'（{CALIB["n_opp"] / CALIB["n"] * 100:.0f}%）'
        + (('，最近几例：' + '、'.join(
            f'{mlab(p)}（单月 {r["m"]:+.1f}%／滚动 {r["r"]:+.1f}%）'
            for p, r in CALIB['opp'].tail(3).iterrows()) + '。')
           if CALIB['n_opp'] else '。')
        + f'衍生品 ADV 更极端：{CALIB_DV["n"]} 个可比月里 {CALIB_DV["n_opp"]} 个月'
        f'（{CALIB_DV["n_opp"] / CALIB_DV["n"] * 100:.0f}%）符号相反。'
        f'算法是「最近 12 个月合计 ÷ 上一个 12 个月合计 − 1」；实现上取滚动均值再相比 —— '
        f'窗口固定 12 个月，除以 12 是同一个常数，两者逐点严格相等，而均值让 ADT 类源列的'
        f'单位保持「HK$bn/日」不变。第一个有值的点要等 24 个月（12 个月填窗 + 12 个月比较），'
        f'所以窗口左端可能没有折线，那不是缺数 —— Exhibit 10 / 13 的费率序列本身只有十个'
        f'季度，那两条线因此特别短。'
        f'<b>不乘交易日数</b>：Exhibit 7 早就定过这条口径（「ADT 已是每日口径，合计会随季内'
        f'交易日数变化而失真」，季度柱因此取简单平均），滚动口径沿用它，本页不引入第二套'
        f'聚合口径。'
        + ((f'这不是想当然 —— <code>series/hkex.csv</code> 里有逐月的现货交易日数'
            f'（<code>trading_days_cash</code>），两种口径可以直接对：加权口径'
            f'（Σ ADT×交易日 ÷ Σ 交易日）与不加权口径的 TTM 同比最大只差 '
            f'<b>{DAYW_GAP:.1f}pp</b>，'
            + ('逐月符号完全一致' if DAYW_SAME else '仍有符号不一致的月份')
            + '，交易日效应在 12 个月窗口里基本自抵，为这点差别引入第二套聚合口径不划算。')
           if DAYW_GAP is not None else
           '（本仓的月度序列里目前没有现货交易日数，即便想加权也没有数据。）'),

        f'<b>本页有四种变化率口径，已逐处点名，不要跨口径比高低。</b>'
        f'（a）<b>流量</b>序列（Exhibit 2 / 6 / 10 / 13'
        + (f' / {EX_TTMVOL} 的次轴金色折线与 Exhibit {EX_VP} 的分解）：'
           if HAS_VP else ' 的次轴金色折线）：')
        + f'12 个月滚动合计同比；'
        f'（b）<b>存量与比率</b>序列（Exhibit 8 市值的次轴、Exhibit 9 换手率的次轴）：'
        f'<b>点对点</b>同比 —— 存量不可加总（把 12 个月末的市值加起来不是任何东西），'
        f'比率滚动之后也不再是加权比率；两者都不吃日历效应，单月口径本来就稳'
        f'（实测市值单月同比标准差 {CALIB_MC["sd_m"]:.1f}pp，现货 ADT 是 '
        f'{CALIB["sd_m"]:.1f}pp）。比率的变化用百分点差，不是百分比的百分比变化。'
        f'这条「流量用滚动、存量与比率用点对点」的判据不是本页自订的，'
        f'实现在全站唯一的 <code>build/yoy.py</code> 里，对存量调滚动合计会直接抛错；'
        f'（c）Exhibit 7 的绿线：本季 3 个月 vs 上年同季（柱是季度的，线只能与柱同期）；'
        f'（d）Exhibit 3 是<b>环比</b>（本月 vs 上月），汇总表（Exhibit 1）的 m/m 与 y/y 列'
        f'是单月口径 —— 环比回答的是当月动能这个运营问题，平滑掉就什么也不剩；'
        f'汇总表三列写死的就是「本月 / 上月 / 去年同月」三个具名月份，'
        f'放滚动值进去与列头自相矛盾。',

        # ── 量价分解：两条腿是不是同口径，是这张图唯一值得担心的事，逐条写清 ──
        # 没有成交股数列时这一整条换成「不具备数据条件」，把缺的是什么、在哪、什么形态
        # 全部写清 —— 空着不写，读者只会以为这一页压根没想过量价分解。
        (f'<b>Exhibit {EX_VP} 的三段分解：恒等式，不是估算。</b>'
        f'成交额 ≡ 成交笔数 × 每笔股数 × 每股单价 —— 定义式（每笔股数 ≡ 股数 ÷ 笔数，'
        f'每股单价 ≡ 成交额 ÷ 股数，代回去逐项抵消）。'
        f'<b>为什么是三段不是两段</b>：两段（股数 × 单价）会把「有多少人在交易」与'
        f'「同一批人把单子拆得多碎」揉进「股数」同一块里，而港股这两年恰恰是二者反向 —— '
        f'笔数在涨、每笔股数在跌，只看合成的股数增速就丢掉了这层信息。'
        f'它做得成的<b>唯一</b>前提是三条腿同口径，这一点逐条核对过：成交金额（ADT，'
        f'HK$bn/日）、成交股数（主板 + GEM，mn 股/日）、成交笔数（主板 + GEM，笔/日）'
        f'都来自 HKEX 自己的月度披露、同一个现货证券市场、同一批交易日、同一个「日均」基准；'
        f'股数与笔数实测 ≡（主板 + GEM 月度合计）÷ 当月交易日数，生成脚本对这条恒等式设了 '
        f'1e-4 的硬门槛，破了直接退出。三条腿的水平值都在汇总表与核对表里给出，'
        f'读者可以自己把每笔股数与单价除一遍。'
        f'<b>本页拒绝的凑法</b>：南向 ADT 与衍生品张数分属另外两个市场，'
        f'拿它们当现货的分子分母是跨市场相除，商出来的「单价」方向与大小都不可知，'
        f'而图上完全看不出来 —— 宁可不做。'
        f'<b>三块各读什么</b>：笔数 = 交易活动的广度；每笔股数 = <b>订单碎片化程度</b>，'
        f'与价格无关（算法单把大单拆小它就往下走，成交额可以一分不变）；'
        f'每股单价 = <b>加权平均成交价</b>，既含市场涨跌、也含<b>成交结构变化</b> —— '
        f'分母把主板 + GEM 上所有品种的成交股数加在一起（股票、ETF、窝轮与牛熊证、债券），'
        f'窝轮牛熊证以「仙」计价、股数极大，低价品种的成交占比一升这条单价就下移，'
        f'哪怕每只股票的价格都没动。<b>它不是恒生指数的收益率</b>。'
        f'<b>它与 Exhibit 10 / 13 也不是一回事</b>：那两张里的「费率 × 成交额」是 HKEX 向'
        f'客户收的<b>交易费率</b>，不是标的资产的成交价格，两者不可混为一谈；'
        f'跨页看也一样 —— CME / Cboe 两页做的是「收入 = 张数 × 每张费率」的<b>收入分解</b>，'
        f'与本页的成交额量价分解不可并读。'
        f'分解本身有硬护栏：三块相加逐月等于总增长，生成脚本对<b>对数与算术两种分解</b>的'
        f'残差都设了 1e-9 的门槛，超了直接退出、不出图。图上画对数分解（ln 天然可加、对称、'
        f'零残差，不必选交叉项归谁），算术分解只进图注 —— 算术版必须选一个替换次序、'
        f'交叉项整段压进最后那一块，本页实测交叉项占净增长中位 {CROSS_MED:.1f}%、'
        f'最大 {CROSS_MAX:.0f}%。'
        + (f'（另注：<code>series/hkex.csv</code> 里与股数相关的列为 '
           f'{"、".join(f"<code>{c}</code>" for c in SHARE_COLS)}，'
           f'本页用的是其中的日均口径列 <code>adv_shares_mn</code>。）' if SHARE_COLS else '')
         if HAS_VP else
         '<b>📌 现货的「成交额 = 成交量 × 均价」分解：目前不具备数据条件。</b>'
         '本仓的 <code>series/hkex.csv</code> 里现货只有成交<b>金额</b>（ADT，HK$bn/日），'
         '没有成交<b>股数</b> —— 而均价 = 成交额 ÷ 成交量，缺了分母就算不出均价。'
         '能凑的替代品一个都不能用：南向 ADT 与衍生品张数分属另外两个市场，'
         '拿它们当现货的分子分母是跨市场相除，商出来的「均价」方向与大小都不可知，'
         '而图上完全看不出来 —— 宁可不做。'
         '缺的是<b>本仓的抓取</b>而不是公司的披露：HKEX 确实按月公布成交股数，'
         '只是它不在 Monthly Market Highlights 里，而在另一份刊物 Monthly Bulletin'
         '（栏目原文「Turnover volume (mil shares)」）。'
         '这一列（<code>adv_shares_mn</code>）一进 CSV，本页自动补上两张图：'
         '成交额增长的量价分解与现货成交量本身的水平值 + 增速曲线 —— 生成脚本已按'
         '「有列就画、没列就如实说」写好，不需要再改代码。'
         '另请注意：Exhibit 10 / 13 里的「费率 × 成交额」不是量价分解 —— '
         '那里的费率是 HKEX 向客户收的<b>交易费率</b>，不是标的资产的成交价格，'
         '两者不可混为一谈。'),

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
        f'（1）Exhibit 2 / 6 / 8 / 9 / 10 / 13{f" / {EX_TTMVOL}" if HAS_VP else ""} 的次轴画的是<b>金色 y/y 折线</b>而不是 '
        '12 个月均线（均线只是把柱子再平滑一遍、不带新信息，同比才回答「相对去年是好是坏」），'
        '这一点与原 deck 一致；但<b>流量序列的口径与 deck 有意不同</b> —— deck 一律画单月'
        f'同比，本页的流量图（Exhibit 2 / 6 / 10 / 13{f" / {EX_TTMVOL}" if HAS_VP else ""}）'
        '改画 <b>12 个月滚动合计同比</b>，理由与实测见上面的同比口径条；'
        '存量图（Exhibit 8 市值）与比率图（Exhibit 9 换手率）<b>仍与 deck 一致走点对点</b>'
        '（比率用百分点差），因为存量不可加总、也不吃日历效应。'
        '基数近零或异号的月份仍然放弃、折线在那里断开；'
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

        f'<b>核对表（Exhibit {EX_TABLE}）保持官方原始单位</b>：衍生品 ADV 给原始张数（不是千张），'
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
    # 抬头是全页曝光最高的一行，而本页 ADT 的单月同比有两成以上的月份与趋势符号相反 ——
    # 只放单月同比、不给对照，正是最容易被读反的地方。TTM 与单月两个口径都写、都标名。
    parts = [f'ADT HK${h_adt[-1]:,.1f}bn/日（TTM {ttm_yoy("adt_hkdbn", LATEST)} y/y；'
             f'单月 {pctf(yoy(h_adt), 1)} y/y，{pctf(mom(h_adt), 1)} m/m）']
    if h_sb is not None:
        parts.append(f'南向 ADT HK${h_sb[-1]:,.1f}bn（{pctf(mom(h_sb), 1)} m/m）')
    if h_dv is not None:
        parts.append(f'衍生品 ADV {h_dv[-1]:,.0f} 千张/日'
                     f'（TTM {ttm_yoy("deriv_adv_k", LATEST)} y/y；'
                     f'单月 {pctf(yoy(h_dv), 1)} y/y，{pctf(mom(h_dv), 1)} m/m）')
    if h_mc is not None:
        # 市值是存量：抬头只给点对点同比，与 Exhibit 8 的次轴同口径。写「TTM」会让读者
        # 以为它和 ADT 那一段的 TTM 可比，而存量的 12 个月合计本身就不是东西。
        parts.append(f'市值 HK${h_mc[-1]:,.1f}tn（{pctf(yoy(h_mc), 1)} y/y，{pctf(mom(h_mc), 1)} m/m）')
    h_shr = hv('adv_shares_mn', '成交股数') if HAS_VP else None
    h_trd = hv('adt_trades', '成交笔数') if HAS_VP else None
    h_px = hv('implied_px_hkd', '隐含单价') if HAS_VP else None
    if h_shr is not None and h_trd is not None and h_px is not None:
        # 抬头必须给出三段分解那三条腿的水平值：分解图画的是贡献（对数点），读者在抬头
        # 看不到笔数 / 股数 / 单价各自是多少，就没法判断那张图在说什么。
        # 笔数与股数的 TTM 同比方向不同（笔数快、股数慢＝订单在变碎），两个都写才看得出来。
        parts.append(f'成交笔数 {h_trd[-1] / 1e4:,.0f} 万笔/日'
                     f'（TTM {ttm_yoy("adt_trades", LATEST)} y/y）· '
                     f'成交股数 {h_shr[-1]:,.0f} 百万股/日'
                     f'（TTM {ttm_yoy("adv_shares_mn", LATEST)} y/y）· '
                     f'隐含单价 HK${h_px[-1]:,.4f}/股')
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
        'hub_line': f'ADT HK${h_adt[-1]:,.0f}bn/日（TTM {ttm_yoy("adt_hkdbn", LATEST)} y/y）'
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
    src_date = source_dates().lookup(SERIES, TICKER, str(LATEST))
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
