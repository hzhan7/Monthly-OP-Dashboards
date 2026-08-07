# -*- coding: utf-8 -*-
"""轴刻度小数位收口 —— 把 `assets/charts.js` 的量程与刻度算法在 Python 侧复算一遍，
只在引擎默认的格式器会印错时，往 payload 里补一个显式的 `yfmt`。

## 为什么需要这一层

`charts.js` 的 `ticks()`（第 155 行）步长候选是 `[1, 2, 2.5, 5, 10] × 10^k`，
而画刻度用的 `plainAxis(step)`（第 116 行）按 `-floor(log10(step))` 定小数位：
step = 2.5 时 `log10(2.5) = 0.398`、`floor = 0` ⇒ **0 位小数**，于是
2.5 / 7.5 / 12.5 / 17.5 被印成 3 / 8 / 13 / 18。轴上写着「3」和「5」的两条网格线，
间距跟「5」和「8」一模一样 —— 按标签量线会系统性偏半档。

右轴同理：默认格式器是 `pct0`（`toFixed(0) + '%'`）。y/y 量程窄的图（步长 0.5pp）
整列刻度会印成「-1% -1% 0% 1% 1% 2% 2%」，相邻两条网格线同一个数字。

实测本仓 13 张页里有 60+ 张图中招；`build/cboe.py:507` 早就手工绕过同一个坑
（显式给 `yfmt`），只是没抽出来复用，新建的页又踩了一遍。

## 为什么不改引擎

`assets/charts.js` 同时服务 27 张已验收上线的页，改 `plainAxis` 一行要重新验收全部。
而 payload 侧的 `ex['yfmt']` / `ex['yoy']['yfmt']` 会**完全接管**轴格式器
（`charts.js:718` `yfKey = ex.yfmt || (ex.bar && ex.bar.yfmt)`），
所以在生成端补一位小数是等效且零风险的做法。

## 用法

    import axisfmt
    axisfmt.fix(ex)          # 原地改，幂等；认不出的 kind 原样返回

`fix()` 只**加**小数位，不减：整数步长的图一位都不动，已上线版式不变。
"""
import math

# 引擎 FMT 表（charts.js:88）里每个格式器的小数位与「族」。
# 族 = 后缀，同族之间只差小数位，可以安全地往上升一档。
_DEC = {
    'f0': 0, 'f1': 1, 'f2': 2, 'f3': 3, 'f0c': 0, 'int': 0,
    'usd0': 0, 'usd1': 1, 'usd2': 2, 'usd3': 3, 'usd4': 4,
    'pct0': 0, 'pct1': 1, 'pct2': 2, 'pct0z': 0,
    'pp0': 0, 'pp1': 1, 'x0': 0,
}
_FAMILY = {
    'f0': ['f0', 'f1', 'f2', 'f3'],
    'pct0': ['pct0', 'pct1', 'pct2'],
    'pp0': ['pp0', 'pp1'],
    'usd0': ['usd0', 'usd1', 'usd2', 'usd3', 'usd4'],
}
_HEAD = {f: seq for seq in _FAMILY.values() for f in seq}   # 任一成员 → 所在族


def ticks(mn, mx, count=9):
    """`charts.js:155` `ticks()` 的逐行等价实现。"""
    if not (math.isfinite(mn) and math.isfinite(mx)):
        mn, mx = 0.0, 1.0
    if mn == mx:
        mn, mx = mn - 1, mx + 1
    raw = (mx - mn) / count
    mag = 10.0 ** math.floor(math.log10(raw)) if raw > 0 else 1.0
    step = None
    for cand in (1, 2, 2.5, 5, 10):
        if cand * mag >= raw:
            step = cand * mag
            break
    if step is None:
        step = 10 * mag
    lo = math.floor(mn / step) * step
    hi = math.ceil(mx / step) * step
    out, k = [], 0
    # 逐次累加会积累浮点误差（JS 里也一样），但 lo + k*step 与 JS 的 v += step
    # 在这些量级上落到同一个 toFixed 结果，判小数位够用。
    while lo + k * step <= hi + step / 2 and k < 400:
        v = lo + k * step
        out.append(0.0 if abs(v) < step / 1e6 else v)
        k += 1
    return out


def _zero_frac(a0, a1):
    if not (a1 > a0) or a0 >= 0:
        return 0.0
    if a1 <= 0:
        return 1.0
    return -a0 / (a1 - a0)


def _align_zero(a0, a1, f):
    if not (f > 1e-9) or f >= 1 - 1e-9:
        return a0, a1
    R = max(max(a1, 0.0) / (1 - f), max(-a0, 0.0) / f)
    return -f * R, (1 - f) * R


def _fin(seq):
    return [float(v) for v in (seq or [])
            if v is not None and isinstance(v, (int, float)) and math.isfinite(v)]


def _left_vals(ex):
    """左轴参与量程计算的值（`charts.js:578` 起的 `lv`）。认不出的 kind 返回 None。"""
    k = ex.get('kind')
    if k == 'bar_line':
        return list(ex['bar']['values']) + list(ex['line']['values'])
    if k == 'bar_line_dual':
        return list(ex['bar']['values'])
    if k in ('lines', 'lines_endlabels', 'year_lines'):
        return [v for s in ex['series'] for v in s['values']]
    if k == 'seasonality':
        return list(ex['base']['values']) + list(ex['actual']['values'])
    if k == 'grouped_bars':
        return [v for g in ex['groups'] for v in g['values']]
    if k == 'stacked_dual':
        n = len(ex['stacks'][0]['values'])
        return [sum((st['values'][i] or 0) for st in ex['stacks']) for i in range(n)]
    if k in ('gs_bar', 'gs_line', 'gs_line_avg', 'bars_labeled', 'diverging_bars', 'qtr_bar'):
        return list(ex.get('values') or [])
    return None


_HAS_BAR = ('bar_line', 'bar_line_dual', 'diverging_bars', 'bars_labeled')


def _left_range(ex):
    """左轴 [y0, y1]（`charts.js:620` 起各 kind 的分支，含 ycap / yfloor）。"""
    lv = _left_vals(ex)
    if lv is None:
        return None
    clean = _fin(lv)
    if not clean:
        return None
    mn, mx, k = min(clean), max(clean), ex['kind']
    if k == 'gs_bar':
        y0, y1 = 0.0, mx * 1.22
    elif k == 'stacked_dual':
        y0, y1 = 0.0, mx * 1.28
    elif k == 'bars_labeled':
        y0, y1 = 0.0, mx * 1.13
    elif k == 'qtr_bar':
        y0, y1 = min(0.0, mn * 1.15), mx * 1.32
    elif k == 'seasonality':
        y0, y1 = min(0.0, mn * 1.15), mx * 1.26
    elif k == 'grouped_bars':
        y0, y1 = min(0.0, mn * 1.15), mx * 1.22
    elif k == 'bridge_bar':
        bpad = (mx - mn) * 0.16 or 1.0
        y0, y1 = mn - bpad, mx + bpad
    elif k in ('gs_line', 'gs_line_avg'):
        avg = ex.get('avg12')
        if isinstance(avg, (int, float)) and math.isfinite(avg):
            mn, mx = min(mn, avg), max(mx, avg)
        rr = (mx - mn) or 1.0
        pd = 0.35 if k == 'gs_line_avg' else 0.30
        y0, y1 = mn - rr * pd, mx + rr * pd
    elif k == 'lines_endlabels':
        r2 = (mx - mn) or 1.0
        y0, y1 = mn - r2 * 0.20, mx + r2 * 0.18
    elif ex.get('zero_base'):
        rz = (mx - mn) or abs(mx) or 1.0
        y0 = mn - rz * 0.08 if mn < 0 else 0.0
        y1 = mx * 1.16 if mx > 0 else rz * 0.08
    else:
        inc = (k in _HAS_BAR) or bool(ex.get('zero_line'))
        dmn = min(mn, 0.0) if inc else mn
        dmx = max(mx, 0.0) if inc else mx
        rg = (dmx - dmn) or 1.0
        y0 = 0.0 if (k in _HAS_BAR and dmn >= 0) else dmn - rg * 0.05
        y1 = dmx + rg * 0.05
    if ex.get('ycap') is not None:
        y1 = float(ex['ycap'])
    if ex.get('yfloor') is not None:
        y0 = float(ex['yfloor'])
    return y0, y1


def _rhs(ex):
    """谁在右轴上（`charts.js:283` `rhsOf`）。"""
    if ex.get('kind') == 'gs_bar':
        y = ex.get('yoy')
        return y if (y and y.get('values')) else None
    ln = ex.get('line')
    return ln if (ln and ln.get('values')) else None


def _need_dec(tk, lo, hi):
    """这串刻度要几位小数，才能既不出现重复标签、又不四舍五入到错值。"""
    vis = [v for v in tk if lo - 1e-9 <= v <= hi + 1e-9]
    if not vis:
        return 0
    for d in range(0, 5):
        labs = ['%.*f' % (d, v) for v in vis]
        if len(set(labs)) == len(labs) and all(abs(round(v, d) - v) < 1e-9 for v in vis):
            return d
    return 4


def _bump(fmt, dec):
    """把格式器名升到至少 dec 位小数；同族没有更高位数就原样返回。"""
    seq = _HEAD.get(fmt)
    if not seq:
        return fmt
    return seq[min(max(dec, seq.index(fmt)), len(seq) - 1)]


def _neg_bar_guard(ex):
    """柱状图型有负值时把 `yfloor` / `ycap` 钉死 —— 否则柱子会画到画布外面去。

    `charts.js:622-624` 给 gs_bar / stacked_dual / bars_labeled 三个 kind
    **写死** `y0 = 0`，只按最大值定上界。序列里出现负值时 `Y(v)` 落在绘图区下方，
    而 SVG 没有 clip-path —— 柱子会一路画下去盖住后面的 exhibit。
    实测 miax Ex13「股票 capture（每 100 股，可为负）」最小值 −0.028、上界 0.0073，
    越出 3.8 个图高，整片浅蓝色柱压在 Exhibit 15 与 Exhibit 17 的正文上。

    整段全负更糟：`y1 = max × 1.22` 落在最大值**下方**（−4 → −4.88），
    上下界反过来，整张图没有一根柱画得对（实测 asx Ex20「当月退市实体数（负值）」）。

    这里只在生成端补边界，不动引擎。`yfloor` 一置上引擎就进「截轴」分支，
    但我们给的下界比最小值还低 22%，不会有任何一根柱真的被截，
    所以图上不会出现断口符号。
    """
    if ex.get('kind') not in ('gs_bar', 'bars_labeled', 'stacked_dual'):
        return
    vs = _fin(_left_vals(ex))
    if not vs or min(vs) >= 0:
        return
    mn, mx = min(vs), max(vs)
    if ex.get('yfloor') is None:
        ex['yfloor'] = mn * 1.22
    if ex.get('ycap') is None and mx <= 0:
        ex['ycap'] = 0.0            # 全负：柱从零线往下挂，上界必须是 0


def fix(ex):
    """一张 exhibit：需要时补 `yfloor`/`ycap` 与 `yfmt`。原地改，幂等。"""
    if not isinstance(ex, dict):
        return ex
    _neg_bar_guard(ex)
    kind = ex.get('kind')
    rng = _left_range(ex)
    if rng is None:
        return ex
    y0, y1 = rng
    rc, rtk, r0, r1 = _rhs(ex), None, None, None
    dual = kind in ('bar_line_dual', 'stacked_dual') or \
        (kind in ('qtr_bar', 'grouped_bars', 'gs_bar') and rc is not None)
    if dual and rc is not None:
        if kind == 'stacked_dual':
            rtk = ticks(0.0, rc.get('ymax') or 60, 6)
            r0, r1 = 0.0, rtk[-1]
        else:
            rv = _fin(rc.get('values'))
            if rv:
                rtk = ticks(min(rv + [0.0]), max(rv), 9)
                r0, r1 = rtk[0], rtk[-1]
                f = max(_zero_frac(y0, y1), _zero_frac(r0, r1))
                if f > 1e-9:
                    la0, la1 = _align_zero(y0, y1, f)
                    ra0, ra1 = _align_zero(r0, r1, f)
                    # 分母为 0 是退化图（序列恒等于 0）；JS 里 0/0 = NaN、
                    # `NaN > 0.38` 为 false，走「对齐」分支，这里照此还原。
                    w1 = 1 - (y1 - y0) / (la1 - la0) if (la1 - la0) else float('nan')
                    w2 = 1 - (r1 - r0) / (ra1 - ra0) if (ra1 - ra0) else float('nan')
                    waste = max(w1, w2) if (w1 == w1 and w2 == w2) else float('nan')
                    if not waste > 0.38:              # charts.js 的 ALIGN_WASTE_MAX
                        y0, y1, r0, r1 = la0, la1, ra0, ra1
                        rtk = ticks(r0, r1, 9)
    # 左轴：没给 yfmt 时引擎用 plainAxis（纯数字），等价于 f0/f1/f2/f3
    cur = ex.get('yfmt') or (ex.get('bar') or {}).get('yfmt') or 'f0'
    if cur in _DEC:
        dec = _need_dec(ticks(y0, y1, 9), y0, y1)
        if dec > _DEC[cur]:
            new = _bump(cur, dec)
            if new != cur:
                if ex.get('yfmt') is None and (ex.get('bar') or {}).get('yfmt') is not None:
                    ex['bar']['yfmt'] = new
                else:
                    ex['yfmt'] = new
    # 右轴
    if rtk is not None and rc is not None:
        rcur = rc.get('yfmt') or 'pct0'
        if rcur in _DEC:
            rdec = _need_dec(rtk, r0, r1)
            if rdec > _DEC[rcur]:
                rc['yfmt'] = _bump(rcur, rdec)
    return ex


def fix_all(exhibits):
    for e in exhibits or []:
        fix(e)
    return exhibits
