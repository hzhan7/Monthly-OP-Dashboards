# -*- coding: utf-8 -*-
"""spec 侧的「图注里的数在构建期现算」小工具。

规矩（本仓通用）：**图注里的数一个都不许写死，构建期现算；读不到源就退回不含数字的
定性版本，不许抛异常。** 一份 spec 是被 `import` 进来的，import 期抛异常等于整条构建
挂在一个「少一句话」的问题上，不划算。

所以这里每个函数都：拿得到 → 返回数；拿不到（文件缺、列缺、数不够）→ 返回 None，
调用方用 `if 数 is None: 退回定性版本`。下划线开头的文件名让 `--all` 不会把它当成一家。
"""
import csv
import os

SERIES = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), 'series')


def _rows(csvname):
    try:
        with open(os.path.join(SERIES, csvname), encoding='utf-8') as fh:
            return list(csv.DictReader(fh))
    except Exception:
        return None


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _days(m):
    """'YYYY-MM' → 该月天数。"""
    import calendar
    y, mo = int(m[:4]), int(m[5:7])
    return calendar.monthrange(y, mo)[1]


def days_effect(csvname, col):
    """「月营收该不该按天数归一化」的实测判据。拿不到返回 None。

    回答两个数：
      · `slope` —— `(m/m %) ~ (天数变化 %)` 的最小二乘斜率。**日历日驱动产出**这个假设
        要求斜率 ≈ 1（多一天多一天的货）。晶圆厂 24/7 连续生产，看上去正该如此。
      · `feb` / `feb_days` —— 2 月营收对相邻 1、3 月均值的实际比值，以及同一口径下的
        天数比值。若产出真按天数走，两者应当相等。
    斜率显著偏离 1、或 feb 明显低于 feb_days，就说明天数只是农历年与季末拉货日历的
    **代理变量**，按天数除一遍会把农历年效应算成「经营性走弱」。
    """
    rs = _rows(csvname)
    if not rs:
        return None
    ms = [r['month'] for r in rs]
    vs = [_f(r.get(col)) for r in rs]
    xs, ys = [], []
    for i in range(1, len(vs)):
        a, b = vs[i], vs[i - 1]
        if a is None or not b:
            continue
        d0, d1 = _days(ms[i - 1]), _days(ms[i])
        xs.append((d1 / d0 - 1) * 100)
        ys.append((a / b - 1) * 100)
    if len(xs) < 24:
        return None
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx <= 0:
        return None
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx

    fr, dr = [], []
    by = {m: v for m, v in zip(ms, vs) if v is not None}
    for m in ms:
        if not m.endswith('-02'):
            continue
        y = m[:4]
        j, mar = by.get(f'{y}-01'), by.get(f'{y}-03')
        if not j or not mar:
            continue
        fr.append(by[m] / ((j + mar) / 2))
        dr.append(_days(m) / ((_days(f'{y}-01') + _days(f'{y}-03')) / 2))
    if not fr:
        return None
    return {'slope': slope, 'n': n,
            'feb': sum(fr) / len(fr), 'feb_days': sum(dr) / len(dr), 'feb_n': len(fr)}


def share_range(csvname, part_col, total_col):
    """分部占比的 (当期, 最小, 最大, 中位, n)，单位 %。拿不到返回 None。"""
    rs = _rows(csvname)
    if not rs:
        return None
    xs = []
    for r in rs:
        p, t = _f(r.get(part_col)), _f(r.get(total_col))
        if p is None or not t:
            continue
        xs.append(p / t * 100)
    if len(xs) < 3:
        return None
    ss = sorted(xs)
    return {'cur': xs[-1], 'min': ss[0], 'max': ss[-1],
            'med': ss[len(ss) // 2], 'n': len(xs)}


def additivity_gap(csvname, month_col, ytd_col, year_of=lambda m: m[:4]):
    """逐年「12 个月相加 vs 官方本年累计」的相对缺口（%）。返回 {年: 缺口%}。

    用途：世芯-KY 那条「新台币月值不可加总」的实测。功能货币不是新台币时，
    各月用各月汇率折算，相加 ≠ 官方累计（后者 = 累计外币 × 累计换算汇率）。
    """
    rs = _rows(csvname)
    if not rs:
        return None
    acc, last = {}, {}
    for r in rs:
        y = year_of(r['month'])
        v, t = _f(r.get(month_col)), _f(r.get(ytd_col))
        if v is None or t is None:
            continue
        acc[y] = acc.get(y, 0.0) + v
        last[y] = (r['month'], t)
    out = {}
    for y, s in acc.items():
        m, t = last[y]
        if m.endswith('-12') and t:                  # 只看完整年
            out[y] = (s / t - 1) * 100
    return out or None


def yoy_extremes(csvname, col, lag=12):
    """单月同比的 (最小, 最大, p5, p95, n) —— 判热力矩阵读不读得出来用。"""
    rs = _rows(csvname)
    if not rs:
        return None
    vals = [_f(r.get(col)) for r in rs]
    ys = []
    for i in range(lag, len(vals)):
        a, b = vals[i], vals[i - lag]
        if a is None or not b:
            continue
        ys.append((a / b - 1) * 100)
    if len(ys) < 24:
        return None
    ss = sorted(ys)

    def q(p):
        k = (len(ss) - 1) * p
        lo, hi = int(k), min(int(k) + 1, len(ss) - 1)
        return ss[lo] + (ss[hi] - ss[lo]) * (k - lo)

    p5, p95 = q(0.05), q(0.95)
    span = (p95 - p5) or 1.0
    # 引擎的色阶（charts.js heatScale）：t = (v − p5) / (p95 − p5)，
    # t<0.5 在红→白之间线性插值、t>0.5 在白→绿之间 —— **线性**，没有 log 入口。
    # 所以「这张矩阵读不读得出来」的判据是：这些格子在 t 轴上摊得开吗。
    # 这里量最挤的那一段：**最宽 20% 的色带里最多塞进了几个格子**。
    # 塞得越多，说明它们彼此的色差不到两成，肉眼分不开。
    ts = sorted(min(max((v - p5) / span, 0.0), 1.0) for v in ys)
    best, j = 0, 0
    for i2 in range(len(ts)):
        while ts[i2] - ts[j] > 0.20:
            j += 1
        best = max(best, i2 - j + 1)
    return {'min': ss[0], 'max': ss[-1], 'p5': p5, 'p95': p95,
            'n': len(ys), 'dull': best, 'dull_share': best / len(ys) * 100}
