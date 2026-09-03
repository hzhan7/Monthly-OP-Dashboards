"""assets/charts.js 双轴对齐算法的 Python 复刻 —— 用来核对图注写的轴行为是不是真的。

存在的理由：2026-08-17 实测发现 schw Exhibit 3 的图注声称「引擎按兜底规则改成两轴各自
缩放、并标了『左右轴零点不同高』、左轴从 0 起」，而引擎实际走的是对齐、没标那句话、
左轴下界 -86.5 —— 三条断言同时为假。成因是图注文案从另一张图搬过来后没按新窗口重算，
而「图注说的」与「引擎做的」之间此前没有任何机器判据。全站扫描下来这是唯一一处假断言
（另有 39 处只是图注没提标注，那不算错）；该处已于当日修好，现全站 0 处。

⚠️ 拿它写自动判据时：**别用朴素子串匹配**。「图注提到了『左右轴零点不同高』」不等于
   「图注声称引擎标了它」—— 修好后的 schw Ex3 图注里正好有一句「图内也**不**标
   『左右轴零点不同高』」，朴素匹配会把这句正确的话报成假断言（本人踩过）。
   要么在短语前 ~18 字内查否定词（不/没有/未/无），要么干脆人工读那几处命中。

⚠️ **它是复刻件，不是引擎本身 —— 会漂。**
   复刻基准：assets/charts.js @ commit 75ab0f8（2026-08-17），已含该 commit 新加的右轴
   截轴字段 `ymax`（rhsOf(ex).ymax，charts.js:1003-1004，语义同左轴 ycap：截轴不删点）。
   下面所有 `charts.js:NNN` 行号已于 2026-09-03 重锚，基准是把 `stacked_dual` 负段
   支持两支实现合并之后的 assets/charts.js（main 8e7681e ＋ 分支 fervent-murdock-3ee22b
   ＋ 分支 silly-jennings-74b6a7，合并后共 2383 行）—— 合并本身又把行号整体推移了一次，
   两支分支上各自算出来的锚点都已作废，别拿它们对。
   75ab0f8 → 该合并点之间 charts.js 改了十几次，除下面这条 `stacked_dual` 改动外，
   **量程/刻度/对齐四段逻辑逐字节未变**（ticks/zeroFrac/alignZero、lv、y0/y1 各分支、
   右轴+零点对齐），只是被无关改动整体推移。
   2026-09-03 起 `stacked_dual` 认负段：`lv` 改推正/负两条包络（同 bridge_bar），
   `y0` 由写死的 0 改成 `min(0, mn*1.15)`。同一改动同时落在 charts.js、
   build/axisfmt.py（`_left_vals` / `_left_range`）与这里三处；全段非负时三处的输出
   都与从前逐字节相同。
   charts.js 每次动量程/刻度/对齐逻辑，这里都要跟着改并重跑一次全站扫描 ——
   核对基准永远是 charts.js，不是这里。
   同一份量程逻辑在仓里另有两份副本（build/axisfmt.py 的 fix_all、build/mrbase.py 的
   align_sim，见 charts.js:991-993 的警告），改的时候三处加这里一共四处要一起看。

用法：
    python3 tools/align_replica.py data/schw.js            # 全部 exhibit
    python3 tools/align_replica.py data/schw.js 3          # 只看 Ex3
    python3 tools/align_replica.py --note data/schw.js 3   # 直接吐写图注要用的数
    python3 tools/align_replica.py --all data               # 全站扫描
"""


import json
import math
import os
import sys

# charts.js:317
ALIGN_WASTE_MAX = 0.38

# charts.js:905-906 —— 判「这个 kind 有柱」，决定 y0 能不能因 5% 留白掉到 0 以下
_HAS_BAR = ('bar_line', 'bar_line_dual', 'diverging_bars', 'bars_labeled')


# ══════════════════════════════════════════════════════════════════════════
# 三个原语（charts.js:273 / 288 / 297 的逐行等价实现）
# ══════════════════════════════════════════════════════════════════════════
def ticks(mn, mx, count):
    """charts.js:273-284。

    刻意保留 JS 的浮点累加 `v += step`（而不是 lo + k*step），
    这样 out[0] / out[-1] 与浏览器里算出来的是同一串二进制。
    """
    if not (isinstance(mn, float) or isinstance(mn, int)) or \
       not (isinstance(mx, float) or isinstance(mx, int)) or \
       not math.isfinite(mn) or not math.isfinite(mx):
        mn, mx = 0.0, 1.0                                    # charts.js:274
    mn, mx = float(mn), float(mx)
    if mn == mx:                                             # charts.js:275
        mn, mx = mn - 1.0, mx + 1.0
    raw = (mx - mn) / count                                  # charts.js:276
    # JS: Math.pow(10, Math.floor(Math.log10(raw)))。raw<=0 时 JS 得 NaN/−Inf，
    # 上游 mn==mx 已被处理，故 raw>0 恒成立；仍留一条兜底且**不吞错**。
    if raw <= 0:
        raise ValueError('ticks(): raw <= 0，上游 min/max 不合法: %r %r' % (mn, mx))
    mag = math.pow(10, math.floor(math.log10(raw)))          # charts.js:277
    step = None
    for cand in (1, 2, 2.5, 5, 10):                          # charts.js:278-279
        if cand * mag >= raw:
            step = cand * mag
            break
    if step is None:                                         # charts.js:280
        step = 10 * mag
    lo = math.floor(mn / step) * step                        # charts.js:281
    hi = math.ceil(mx / step) * step
    out, v, guard = [], lo, 0
    while v <= hi + step / 2:                                # charts.js:282
        out.append(0.0 if abs(v) < step / 1e6 else v)
        v += step
        guard += 1
        if guard > 10000:
            raise RuntimeError('ticks(): 步进失控')
    return out


def zero_frac(a0, a1):
    """charts.js:288-292 —— 0 在该轴上的相对高度（0=贴底，1=贴顶）。"""
    if not (a1 > a0) or a0 >= 0:                             # charts.js:289
        return 0.0
    if a1 <= 0:                                              # charts.js:290
        return 1.0
    return -a0 / (a1 - a0)                                   # charts.js:291


def align_zero(a0, a1, f):
    """charts.js:297-301 —— 把 [a0,a1] 重排成「0 落在相对高度 f」，只放大不缩小。"""
    if not (f > 1e-9) or f >= 1 - 1e-9:                      # charts.js:298
        return a0, a1
    R = max(max(a1, 0.0) / (1 - f), max(-a0, 0.0) / f)       # charts.js:299
    return -f * R, (1 - f) * R                               # charts.js:300


# ══════════════════════════════════════════════════════════════════════════
# payload 侧的取值（charts.js:495-508 / 858-899）
# ══════════════════════════════════════════════════════════════════════════
def _is_num(v):
    """charts.js:482 isNum。注意 JS 里 true/false 会过 isFinite，Python 侧显式排除 bool。"""
    return v is not None and not isinstance(v, bool) and \
        isinstance(v, (int, float)) and math.isfinite(v)


def _fin(seq):
    return [float(v) for v in (seq or []) if _is_num(v)]


def rhs_of(ex):
    """charts.js:495-498。"""
    if ex.get('kind') == 'gs_bar':
        y = ex.get('yoy')
        return y if (y and y.get('values')) else None
    ln = ex.get('line')
    return ln if (ln and ln.get('values')) else None


def line_vals(ex):
    """charts.js:499-508 —— qtr_bar 末季未满时，右轴 y/y 的最后一点作废。

    这一步直接决定右轴量程：漏掉它，一个根本不画出来的点会把右轴撑开。
    """
    r = rhs_of(ex)
    v = r.get('values') if r else None
    if not v or ex.get('kind') != 'qtr_bar':
        return v
    pm, qm = ex.get('partial_months'), ex.get('qtr_months') or 3
    if _is_num(pm) and float(pm) > 0 and float(pm) < qm:
        v = list(v)
        v[-1] = None
    return v


def _bridge_net(ex, n):
    """charts.js:637-649。"""
    if ex.get('net') and ex['net'].get('values'):
        return ex['net']['values']
    out = []
    for i in range(n):
        t, any_ = 0.0, False
        for st in ex['stacks']:
            v = st['values'][i]
            if _is_num(v):
                t += v
                any_ = True
        out.append(t if any_ else None)
    return out


def _n_of(ex):
    """charts.js 用 xlabels 定 n；payload 一律带 xlabels（或从左轴序列反推）。"""
    xl = ex.get('xlabels')
    if xl:
        return len(xl)
    for key in ('values',):
        if ex.get(key):
            return len(ex[key])
    if ex.get('stacks'):
        return len(ex['stacks'][0]['values'])
    if ex.get('series'):
        return len(ex['series'][0]['values'])
    if ex.get('groups'):
        return len(ex['groups'][0]['values'])
    raise ValueError('无法确定 n')


def left_values_of(ex):
    """charts.js:858-899 的 `lv`。认不出的 kind **抛错**，不静默返回空。"""
    k = ex.get('kind')
    if k == 'bar_line':
        return list(ex['bar']['values']) + list(ex['line']['values'])
    if k == 'bar_line_dual':
        return list(ex['bar']['values'])
    if k in ('lines', 'lines_endlabels', 'year_lines'):
        return [v for s in ex['series'] for v in s['values']]
    if k == 'seasonality':
        return list(ex['base'].get('values') or []) + list(ex['actual'].get('values') or [])
    if k == 'grouped_bars':
        return [v for gp in ex['groups'] for v in gp['values']]
    if k == 'range_band':
        lv = list(ex.get('lo') or []) + list(ex.get('hi') or []) + list(ex.get('actual') or [])
        if _is_num(ex.get('qtd')):
            lv.append(ex['qtd'])
        return lv
    if k == 'bridge_bar':
        n = _n_of(ex)
        lv = []
        for i in range(n):
            bp, bn = 0.0, 0.0
            for st in ex['stacks']:
                bv = st['values'][i]
                if not _is_num(bv):
                    continue
                if bv >= 0:
                    bp += bv
                else:
                    bn += bv
            lv.append(bp)
            lv.append(bn)
        return lv + list(_bridge_net(ex, n))
    if k == 'stacked_dual':
        # 与 bridge_bar 同形：一列推**两条**包络（正向堆到哪、负向堆到哪），
        # 不是两者相抵之后的合计。2026-09 起引擎的 stacked_dual 能画负段了
        # （charts.js 那支与 build/axisfmt.py 的 _left_vals 同时改的），这里是
        # 第三份副本，漏改就会让本工具算出的轴与页面上画的对不上 —— 而这个工具
        # 存在的全部意义就是复算出与引擎逐位相同的轴。
        # 全非负时负包络恒为 0、正包络恒等于旧的合计，取值与从前一字不差。
        # `or 0` 是照抄引擎那行的 `|| 0`（null → 0，落进正包络），**不是**上面
        # bridge_bar 的 isNum 跳过 —— 两条分支在引擎里本来就写法不同，别顺手统一。
        n = _n_of(ex)
        lv = []
        for i in range(n):
            vs = [(st['values'][i] or 0) for st in ex['stacks']]
            lv.append(sum(v for v in vs if v >= 0))
            lv.append(sum(v for v in vs if v < 0))
        return lv
    # charts.js:899 `else lv = ex.values.slice()`
    if 'values' in ex:
        return list(ex['values'] or [])
    raise ValueError('kind=%r 没有 ex.values，且不在已知分支里' % k)


# ══════════════════════════════════════════════════════════════════════════
# 核心：compute_axes
# ══════════════════════════════════════════════════════════════════════════
def compute_axes(left_series, right_series, opts):
    """复算某张双轴（或单轴）exhibit 的左右轴上下界与对齐行为。

    参数
    ----
    left_series : list[float|None]
        已按 charts.js:858-899 展平后的**左轴参与量程的值**。
        （从 payload 直接算用 `compute_axes_from_exhibit`，它会替你展平。）
    right_series : list[float|None] | None
        右轴序列。**必须是过了 lineVals() 的版本**（qtr_bar 未满季那点要置 None）。
        None 或空 = 单轴图。
    opts : dict
        kind            str   必填，决定 y0/y1 分支
        ycap, yfloor    float 截轴上/下界（charts.js:972-973，**在对齐之前**生效）
        avg12           float gs_line / gs_line_avg 用
        zero_base       bool  左轴：payload 顶层的 ex.zero_base（charts.js:949）
        zero_line       bool  charts.js:945
        right_zero_base bool  右轴 rc.zero_base；显式 False 时不把 0 纳入右轴量程
                              （charts.js:994）
        right_ymax      float 仅 stacked_dual：rc.ymax（charts.js:984）
        has_rhs         bool  仅 stacked_dual 的 y1 分档用（charts.js:919-920）；
                              不给就按 right_series 是否非空推断

    返回 dict：
        left_min, left_max, right_min, right_max   最终轴界（right_* 单轴时为 None）
        waste                    两轴浪费率取大者；f<=1e-9 或单轴时为 0.0
        fallback_triggered       是否触发 ALIGN_WASTE_MAX 兜底（= 两轴各自缩放）
        zero_aligned             两轴零点是否被摆到同一画布高度
        draws_zero_mismatch_label  图上是否会画「左右轴零点不同高（两轴独立缩放）」
        —— 另附诊断字段：dual / f / left_ticks / right_ticks /
           left_ticks_visible / right_ticks_visible /
           draws_right_zero_dashline / notes
    """
    kind = opts.get('kind')
    if not kind:
        raise ValueError('opts["kind"] 必填')

    clean = _fin(left_series)
    if not clean:
        raise ValueError('左轴没有有限值（charts.js 此时直接打印「无数据」）')
    mn, mx = min(clean), max(clean)

    # ── charts.js:911-969：各 kind 的 y0/y1 ──────────────────────────────
    if kind == 'gs_bar':
        y0, y1 = 0.0, mx * 1.22                                      # :911
    elif kind == 'stacked_dual':
        has_rhs = opts.get('has_rhs')
        if has_rhs is None:
            has_rhs = bool(_fin(right_series))
        # 下界原来写死 0.0。2026-09 起与引擎一起改成 min(0, mn×1.15)
        # （qtr_bar / seasonality / grouped_bars 同一条负向留白规矩）——
        # 全非负时 mn 恒为 0 ⇒ 仍是 0.0，既有 23 张一位都不变。
        y0, y1 = min(0.0, mn * 1.15), mx * (1.28 if has_rhs else 1.06)   # :919-920
    elif kind == 'bars_labeled':
        y0, y1 = 0.0, mx * 1.13                                      # :922
    elif kind == 'qtr_bar':
        y0, y1 = min(0.0, mn * 1.15), mx * 1.32                      # :924
    elif kind == 'seasonality':
        y0, y1 = min(0.0, mn * 1.15), mx * 1.26                      # :925
    elif kind == 'grouped_bars':
        y0, y1 = min(0.0, mn * 1.15), mx * 1.22                      # :926
    elif kind == 'bridge_bar':
        bpad = (mx - mn) * 0.16 or 1.0                               # :928
        y0, y1 = mn - bpad, mx + bpad
    elif kind == 'range_band':
        if mn >= 0:
            y0, y1 = mn * 0.88, mx * 1.10                            # :932
        else:
            rr0 = (mx - mn) or 1.0                                   # :933
            y0, y1 = mn - rr0 * 0.12, mx + rr0 * 0.10
    elif kind in ('gs_line', 'gs_line_avg'):
        avg = opts.get('avg12')
        if _is_num(avg):                                             # :936
            mn, mx = min(mn, avg), max(mx, avg)
        rr = (mx - mn) or 1.0
        pd = 0.35 if kind == 'gs_line_avg' else 0.30                 # :937
        y0, y1 = mn - rr * pd, mx + rr * pd
    elif kind == 'lines_endlabels':
        r2 = (mx - mn) or 1.0                                        # :940
        y0, y1 = mn - r2 * 0.20, mx + r2 * 0.18
    else:
        inc = (kind in _HAS_BAR) or bool(opts.get('zero_line'))      # :945
        dmn = min(mn, 0.0) if inc else mn
        dmx = max(mx, 0.0) if inc else mx
        rg = (dmx - dmn) or 1.0
        if opts.get('zero_base'):                                    # :949
            rz = (mx - mn) or abs(mx) or 1.0
            y0 = mn - rz * 0.08 if mn < 0 else 0.0
            y1 = mx * 1.16 if mx > 0 else rz * 0.08
        else:
            y0 = 0.0 if (kind in _HAS_BAR and dmn >= 0) else dmn - rg * 0.05   # :966
            y1 = dmx + rg * 0.05

    # ── charts.js:971-973：截轴。**在零点对齐之前**覆写，所以 ycap/yfloor 会
    #    整体改变 zeroFrac、进而改变 f、waste 与是否兜底。顺序不可换。 ────────
    notes = []
    if opts.get('ycap') is not None:
        y1 = float(opts['ycap'])
        notes.append('ycap=%g 覆写上界（对齐之前）' % y1)
    if opts.get('yfloor') is not None:
        y0 = float(opts['yfloor'])
        notes.append('yfloor=%g 覆写下界（对齐之前）' % y0)

    # ── charts.js:977-1028：右轴 + 零点对齐 ───────────────────────────────
    rv = _fin(right_series)
    dual = bool(rv)                       # 调用方负责只在 dual 图型上传 right_series
    r0 = r1 = None
    rtk = None
    f = 0.0
    waste = 0.0
    misalign = False
    aligned = False

    if dual:
        if kind == 'stacked_dual':                                   # :984
            rtk = ticks(0.0, opts.get('right_ymax') or 60, 6)
            r0, r1 = 0.0, rtk[-1]
        else:                                                        # :985-1007
            rzb = opts.get('right_zero_base') is not False
            # 右轴截轴上界（charts.js:1003-1004）。语义同左轴 ycap：**截轴不删点**，
            # 超界的点钳到边界、画空心红圈、真值红色竖排标出。只在 ymax 比实际最大值
            # 更小时才生效，所以不给 ymax 时下面这行与从前逐字节相同。
            rhi = max(rv)
            _cap = opts.get('right_ymax')
            if _cap is not None and float(_cap) < rhi:
                rhi = float(_cap)
            rtk = ticks(min(rv + ([0.0] if rzb else [])), rhi, 9)
            r0, r1 = rtk[0], rtk[-1]

        f = max(zero_frac(y0, y1), zero_frac(r0, r1))                # :1015
        if f > 1e-9:                                                 # :1016
            la0, la1 = align_zero(y0, y1, f)                          # :1017
            ra0, ra1 = align_zero(r0, r1, f)
            # :1018-1019。分母为 0 是退化图（序列恒 0）：JS 里 0/0=NaN、
            # `NaN > 0.38` 为 false → 走「对齐」分支。这里照此还原，不吞错。
            w1 = 1 - (y1 - y0) / (la1 - la0) if (la1 - la0) else float('nan')
            w2 = 1 - (r1 - r0) / (ra1 - ra0) if (ra1 - ra0) else float('nan')
            waste = max(w1, w2) if (w1 == w1 and w2 == w2) else float('nan')
            if waste > ALIGN_WASTE_MAX:                              # :1020
                misalign = True                                      # :1021
                notes.append('waste %.4f > ALIGN_WASTE_MAX %.2f → 兜底：两轴各自缩放'
                             % (waste, ALIGN_WASTE_MAX))
            else:                                                    # :1022-1026
                y0, y1 = la0, la1
                r0, r1 = ra0, ra1
                rtk = ticks(r0, r1, 9)
                aligned = True
                notes.append('waste %.4f <= %.2f → 两轴零点对齐'
                             % (waste, ALIGN_WASTE_MAX))
        else:
            # f == 0：两轴本来就同零点（左右都不含负值），走老路径，
            # 引擎不改任何量程、也不画兜底标注。charts.js:1010 那句注释。
            aligned = True
            notes.append('f=0（两轴本就同零点）→ 不需要重排，也不标注')

    tk = ticks(y0, y1, 9)                                            # :1030

    def _vis(seq, lo, hi):
        # charts.js:1039 / :1086 —— 落在轴外的刻度不画
        return [v for v in (seq or []) if not (v < lo - 1e-9 or v > hi + 1e-9)]

    # charts.js:1854-1856
    draws_label = misalign
    # qtr_bar / grouped_bars / gs_bar 的右轴零虚线由各自的绘制分支画
    # （qtr_bar 见 :1654-1656），与 misalign 无关；其余 dual 图型只在 misalign 时补。
    if dual and r0 is not None and r0 < -1e-9 and r1 > 1e-9:
        draws_right_zero = (kind in ('qtr_bar', 'grouped_bars', 'gs_bar')) or misalign
    else:
        draws_right_zero = False

    return {
        'left_min': y0, 'left_max': y1,
        'right_min': r0, 'right_max': r1,
        'waste': waste,
        'fallback_triggered': misalign,
        'zero_aligned': (not misalign) and aligned,
        'draws_zero_mismatch_label': draws_label,
        # 诊断
        'dual': dual,
        'f': f,
        'left_ticks': tk,
        'right_ticks': rtk,
        'left_ticks_visible': _vis(tk, y0, y1),
        'right_ticks_visible': _vis(rtk, r0, r1) if dual else None,
        'draws_right_zero_dashline': draws_right_zero,
        'notes': notes,
    }


def compute_axes_from_exhibit(ex):
    """从 payload 里的一张 exhibit 直接算。dual 判定同 charts.js:768-770。"""
    kind = ex.get('kind')
    rc = rhs_of(ex)
    dual = (kind == 'bar_line_dual') or \
        (kind in ('qtr_bar', 'grouped_bars', 'gs_bar', 'stacked_dual') and rc is not None)
    rs = line_vals(ex) if dual else None
    opts = {
        'kind': kind,
        'ycap': ex.get('ycap'),
        'yfloor': ex.get('yfloor'),
        'avg12': ex.get('avg12'),
        'zero_base': ex.get('zero_base'),
        'zero_line': ex.get('zero_line'),
        'right_zero_base': (rc or {}).get('zero_base'),
        'right_ymax': (rc or {}).get('ymax'),
        'has_rhs': rc is not None,
    }
    if kind == 'stacked_dual' and dual:
        # stacked_dual 的右轴量程不看 values，只看 rc.ymax；给个非空占位让 dual 成立
        rs = rs or [0.0]
    return compute_axes(left_values_of(ex), rs, opts)


# ══════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════
def load_payload(path):
    src = open(path, encoding='utf-8').read()
    i = src.index('window.DASH = ') + len('window.DASH = ')
    j = src.rindex('};') + 1
    return json.loads(src[i:j])


def _report(path, wanted=None):
    d = load_payload(path)
    print('== %s  (ticker=%s, data_through=%s)' %
          (os.path.basename(path), d.get('ticker'), d.get('data_through')))
    for ex in d['exhibits']:
        n = ex.get('n')
        if wanted and n not in wanted:
            continue
        kind = ex.get('kind')
        rc = rhs_of(ex)
        dual = (kind == 'bar_line_dual') or \
            (kind in ('qtr_bar', 'grouped_bars', 'gs_bar', 'stacked_dual') and rc is not None)
        if not dual and not wanted:
            continue
        try:
            r = compute_axes_from_exhibit(ex)
        except Exception as e:                      # 让错误可见，不吞
            print('  Ex%-3s %-14s ERROR %s: %s' % (n, kind, type(e).__name__, e))
            continue
        if not r['dual']:
            print('  Ex%-3s %-14s 单轴  L[%.4g, %.4g]  ticks=%s'
                  % (n, kind, r['left_min'], r['left_max'],
                     [round(v, 6) for v in r['left_ticks_visible']]))
            continue
        print('  Ex%-3s %-14s waste=%6.2f%%  %s  L[%.4g, %.4g] R[%.4g, %.4g]  '
              'label=%s  dashline=%s'
              % (n, kind, r['waste'] * 100,
                 '兜底(各自缩放)' if r['fallback_triggered'] else '对齐    ',
                 r['left_min'], r['left_max'], r['right_min'], r['right_max'],
                 'Y' if r['draws_zero_mismatch_label'] else 'n',
                 'Y' if r['draws_right_zero_dashline'] else 'n'))
        print('        Lticks=%s' % [round(v, 6) for v in r['left_ticks_visible']])
        print('        Rticks=%s' % [round(v, 6) for v in r['right_ticks_visible']])


def _note_numbers(path, n):
    """把「写图注要用的那几个数」直接吐出来，省得人肉从上面的表里抄。

    用法： python3 tools/align_replica.py --note <data/xxx.js> <n>
    """
    ex = [e for e in load_payload(path)['exhibits'] if e.get('n') == n][0]
    r = compute_axes_from_exhibit(ex)
    if not r['dual']:
        print('Ex%d 不是双轴图，无对齐行为可写。' % n)
        return
    print('Ex%d  kind=%s  窗口 %s..%s' %
          (n, ex['kind'], (ex.get('xlabels') or ['?'])[0], (ex.get('xlabels') or ['?'])[-1]))
    print('  分支              : %s' % ('兜底（两轴各自缩放）' if r['fallback_triggered']
                                        else ('对齐（f=0，本就同零点）' if r['f'] <= 1e-9
                                              else '对齐（扩量程凑零点）')))
    print('  waste             : %.6f  → 图注写 "%s"' % (r['waste'], format(r['waste'], '.0%')))
    print('  阈值              : %.2f    → 图注写 "%s"' % (ALIGN_WASTE_MAX,
                                                          format(ALIGN_WASTE_MAX, '.0%')))
    print('  左轴最终下界      : %.6f  → 图注写 "%s"' % (r['left_min'],
                                                        format(r['left_min'], ',.0f')))
    print('  左轴最终上界      : %.6f' % r['left_max'])
    print('  右轴最终区间      : [%.6f, %.6f]' % (r['right_min'], r['right_max']))
    print('  画「零点不同高」  : %s' % r['draws_zero_mismatch_label'])
    print('  画右轴零虚线      : %s%s' % (r['draws_right_zero_dashline'],
                                          '（与柱基线重合）' if r['zero_aligned'] and
                                          r['draws_right_zero_dashline'] else ''))
    print('  左轴是否自 0 起   : %s' % (abs(r['left_min']) < 1e-9))
    print('  可见左刻度        : %s' % [round(v, 6) for v in r['left_ticks_visible']])


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    if argv[1] == '--note':
        _note_numbers(argv[2], int(argv[3]))
        return 0
    if argv[1] == '--all':
        base = argv[2]
        for fn in sorted(os.listdir(base)):
            if fn.endswith('.js') and fn != 'roster.js':
                _report(os.path.join(base, fn))
        return 0
    wanted = set(int(x) for x in argv[2:]) or None
    _report(argv[1], wanted)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
