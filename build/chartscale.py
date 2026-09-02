# -*- coding: utf-8 -*-
"""图表**显示缩放** —— 只改图，不改核对表与汇总表。

## 要修的缺陷（docs/VISUAL_QA.md §3.F）

柱图的数值标签是**居中钉在自己那根柱上**的，最左边那根柱的标签因此向左伸出绘图区，
压住右对齐在 `M.l − 6` 的 y 轴刻度；最右边那根同理压住右轴刻度。实测 18 处，
读出来是「8000000076,941,267」。`lines_endlabels` 的左端标签落在 `M.l − 10 − tickW`，
刻度一宽 x 就变成负数，标签被 SVG 左边界切掉（db1 Ex10「208,146,474」越界 14px、
Ex16「818,829,790」越界 19px）。

两处是同一根因：**数字太长**。引擎不许改，payload 侧唯一的杠杆就是把数字变短。

## 为什么不是在 spec 里给列加 `scale`

`scale` 是**列级恒等换算**，`Page.ser()` 一乘就贯穿全页 —— 汇总表、末尾 13 个月核对表
一起被改掉。而核对表的用途正是「与官方披露逐条核对」（CONTRACT §4），
改成百万计就对不了账了。所以显示缩放必须与核对表**解耦**：本模块只动
`exhibits[]` 里的 series 数组、`ylab` 与数值格式器，`Page.ser()` / `summary()` /
`table()` 一个字节都不碰。

## 判据是几何，不是量级门槛

任务书建议「最大绝对值 ≥ 1e8 就缩」。1e8 这个数经不起算：压字与量级无关，
只与**标签像素宽**和**一格柱的宽度**有关，所以判据直接算这两个数（`_budget` / `_label_px`）：

    半宽卡片 W = 571（1440px 视口下 qa_geom 逐张量的），gs_bar 有次轴
    ⇒ M.l = 56、M.r = 56、pw = 459，25 个月 ⇒ band = 18.4px。
    标签居中钉在柱上、刻度右对齐在 M.l−6 ⇒ 两者的间隙 = (band + 12 − 标签宽) / 2。
    引擎字体是 Helvetica 族，8px 字号下数字宽 4.45px、逗号 2.22px。
    要求这个间隙不小于引擎自己判「两个标签挨太近」的阈值 `LAB_GAP = 1.5px`
    （charts.js:858）⇒ **标签宽度预算 = band + 12 − 2 × 1.5 = 27.4px**。

按这条尺子量出来的门槛比 1e8 低两个数量级：

  · 7 位数带千分位「1,729,208」= 35.6px，超预算 8.2px ⇒ 实际压字 4.1px
    （VISUAL_QA §3.F 那张表自己就有这个反例：db1 Ex23 只有 7 位数，照样压了 2.6px）；
  · **6 位数「171,773」= 28.9px 也超**，间隙只剩 0.72px —— 比一个空格（2.2px）还窄，
    读出来就是「175000171,773」。qa_geom 判压字的门限是 2.5px，所以这一类它一条都没报，
    但读者看到的是一样的东西。本模块按 0.72 < 1.5 判它超标，一并修掉。

同一把尺子还量另外两处同源的症状：`lines_endlabels` 的左端标签（右边界在
`M.l − 10 − tickW`，再宽就被 SVG 左边界切掉），以及 `bars_labeled` 相邻两根柱的标签
（引擎**没给这个 kind 调 thinLabels**，标签一宽就直接互相盖住 —— enx Ex30 实测重叠 10.7px）。

## 判据的粒度：连通分量，不是单张图，也不是整页

两条约束同时成立才不会读出错：

  1. **同一张图里各列必须同一倍数** —— 一根轴上两个量级，图就画错了；
  2. **同一列在它出现的每张图里必须同一倍数** —— 头条列会同时出现在长历史图、
     季节性图和它自己那张组图里，Exhibit 3 印「1.56」而 Exhibit 13 印「1,562,551」，
     读者会以为是两条不同的序列。

把「列 ↔ 图」当成二部图求**连通分量**，一个分量定一个倍数，两条约束就同时满足了。
分量之间互不相干：db1 的 16 张 contracts 图各自是一个分量，各按自己的量级定倍数
（1.6 亿那张按百万、3.7 万那张不缩放），这是对的 —— 它们本来就是不同的列、不同的图。

## 有量级差 100× 以上的列同处一图时，倍数会自动退档

分量里最小的那条序列缩放后至少要保住 2 位有效数字（`f3` 只有 3 位小数，
所以下限是 0.0095）。asx Ex13「ASX 24 期货 1,563k / 期货期权 2,823」按百万缩会把
后者印成「0.00」—— 那是拿缺陷 F 的修法制造缺陷 G（同轴量级差，见 VISUAL_QA §3.G）。
所以这种分量自动退到「千」，两条都还读得出来。退到最后仍不满足就整个分量不缩放。

## 用法

    import chartscale
    applied = chartscale.fix_all(exhibits)   # 原地改，返回 [(unit, 倍数, 中文词), …]

调用方须在每张**画原始量级数值**的 exhibit 上放一个临时键 `_cols`（该图画了哪几列的
列名），`fix_all` 会把它 pop 掉，不会流进 payload。必须在 `axisfmt.fix_all()
**之前**调用：轴刻度小数位是按最终数值算的。
"""
import math
import re

# ────────────────── 引擎几何（assets/charts.js，复算，不改引擎） ──────────────────
# 1440px 视口下实测的画布宽：普通卡片 571、`full: True` 通栏 1172（qa_geom 逐张量过）。
W_CARD, W_FULL = 571.0, 1172.0

# Helvetica 族的字宽（每 1000 单位 em）。只列标签里真会出现的字符，其余按数字宽算。
# 校准过：db1 Ex14「76,941,267」按此算 40.0px，qa_geom 实测的重叠 4.8px 与
# (40.0 − band 18.4 − 12) / 2 = 4.8px 逐位吻合。
_ADV = {',': 278, '.': 278, '-': 333, '%': 889, '$': 556, '+': 584}


def _label_px(s, size):
    return size * sum(_ADV.get(ch, 556) for ch in s) / 1000.0


# 缩放倍数与轴标题上的中文词。只用 1000 的幂：读者对「千 / 百万 / 十亿」有直觉，
# 对「÷2.5 万」没有。
_FACTORS = ((1e9, '十亿'), (1e6, '百万'), (1e3, '千'))
_MARK = re.compile('（(?:%s)）$' % '|'.join(w for _, w in _FACTORS))   # 轴标题上的缩放标记
LAB_GAP = 1.5            # charts.js:858 —— 引擎自己判「两个标签挨太近」的最小间隙
MIN_KEEP = 0.0095        # 分量里最小的那条序列缩放后至少还有 2 位有效数字（f3 = 3 位小数）
MAX_DEC = 3              # 引擎的格式器表只到 f3 / usd3（docs/CHART_KINDS.md §2）

# 画原始量级数值的 kind。`grouped_bars`（同比）与 `heat_matrix`（同比）画的是百分数，
# 不在此列。
#
# `bridge_bar`（build/single.py 的 decomp）与 `stacked_dual`（同文件的 groups[].mix
# 占比堆叠）现在**是**由底座产出的，但两者都**不该**进这张表，理由与百分数那两个一样：
# 画在它们轴上的数本来就是「百分点」与「占合计的 %」，两位数量级，
# 「百万分之几个百分点」不是人话。`_arrays()` 对它们返回 None，于是 `_needs` / `audit`
# 一起跳过 —— 那是正确结果，不是漏接。**要给它们做缩放之前先想清楚缩的是什么。**
SCALABLE = ('gs_bar', 'bars_labeled', 'lines', 'lines_endlabels', 'seasonality',
            'gs_line', 'gs_line_avg')
# 比率格式器：百分数/百分点本来就是两位数量级，「百万分之几个百分点」不是人话，
# 所以这些图一律不碰 —— 它们真压字的话要用别的办法（换 fmt 或换窗口），不是缩量级。
_RATIO = ('pct0', 'pct1', 'pct2', 'pct0z', 'pp0', 'pp1', 'x0')


def _arrays(ex):
    """该图左轴上的数值数组 → [(容器, 键)]，供原地改写。认不出的 kind 返回 None。"""
    k = ex.get('kind')
    if k in ('gs_bar', 'bars_labeled', 'gs_line', 'gs_line_avg'):
        return [(ex, 'values')]
    if k in ('lines', 'lines_endlabels'):
        return [(s, 'values') for s in (ex.get('series') or [])]
    if k == 'seasonality':
        return [(ex['base'], 'values'), (ex['actual'], 'values')]
    return None


# 与左轴同量纲的标量（缩放时必须跟着一起改，否则截轴界跑到量程外面去）。
# `yoy` 是次轴百分数、`line` 是次轴，一律不动。
_SCALARS = ('ycap', 'yfloor', 'avg12')


def _fin(seq):
    return [float(v) for v in (seq or [])
            if v is not None and isinstance(v, (int, float)) and math.isfinite(v)]


def scalable(ex):
    """这张图能不能做显示缩放。比率图型与认不出结构的图一律不碰。"""
    if not isinstance(ex, dict) or ex.get('kind') not in SCALABLE:
        return False
    if (ex.get('fmt') or 'f1') in _RATIO or (ex.get('label_fmt') or 'f1') in _RATIO:
        return False
    return _arrays(ex) is not None


def _series_maxes(ex):
    """该图每条序列各自的最大绝对值（空序列不计）。"""
    out = []
    for obj, key in _arrays(ex) or []:
        v = [abs(x) for x in _fin(obj.get(key))]
        if v:
            out.append(max(v))
    return out


def _factor(cmax, cmin_series):
    """一个连通分量的倍数。定不下来（或不该缩）返回 None。

    上界：最大值缩完不能小于 1（把 1.5e6 缩成 0.0015 比不缩还难读）。
    下界：最小的那条序列缩完要保住 2 位有效数字，见模块头「倍数会自动退档」。
    """
    if not math.isfinite(cmax):
        return None
    for k, word in _FACTORS:
        if cmax / k >= 1.0 and cmin_series / k >= MIN_KEEP:
            return k, word
    return None


def _decimals(vals, cap):
    """**已缩放**的一组值要几位小数：最大值给 3 位有效数字，最小的非零值保住 2 位。

    `cap` 是标签宽度预算：小数位加到把标签又撑爆预算就白修了，所以最后按预算回收
    （宁可少一位有效数字，也不要再压回刻度上）。
    """
    mx = max(vals)
    dec = 2 if mx < 10 else (1 if mx < 100 else 0)
    nz = [x for x in vals if x]
    if nz:
        # 1 − floor(log10(x))：0.42 → 2 位（'0.42'）、0.048 → 3 位（'0.048'）
        dec = max(dec, min(MAX_DEC, 1 - int(math.floor(math.log10(min(nz))))))
    dec = max(0, min(MAX_DEC, dec))
    while dec > 0 and cap and _label_px(f'{mx:.{dec}f}', 8.5) > cap:
        dec -= 1
    return dec


def _needs(ex):
    """这张图的数值标签是不是已经宽到会压字 / 出画布。判据见模块头「判据是几何」。"""
    arrs = _arrays(ex) or []
    vals = [v for obj, key in arrs for v in _fin(obj.get(key))]
    if not vals:
        return False
    kind = ex.get('kind')
    name = ex.get('label_fmt') or ex.get('fmt') or 'f1'
    # 用**全部**点算最宽标签，而不是只算首尾那两个：首尾是哪两个月取决于窗口，
    # 下个月窗口一滚就换人，判据会跟着一个月缩一个月不缩。
    w = max(_label_px(_efmt(v, name), 8.5 if kind == 'bars_labeled' else 8) for v in vals)
    cap = _budget(ex)
    return bool(cap and w > cap)


def _budget(ex):
    """这张图的数值标签宽度上限（px）。None = 这个 kind 没有硬约束。"""
    kind = ex.get('kind')
    _, m_l, _, band = _margins(ex)
    if kind in ('gs_bar', 'seasonality'):
        # 标签居中钉在柱上（seasonality 钉在蓝柱中心，左边多出半根柱的余量），
        # 刻度右对齐在 M.l−6 ⇒ 间隙 = (band + 12 + 让位 − 宽) / 2 ≥ LAB_GAP
        extra = min(band * 0.40, band - 1.5) if kind == 'seasonality' else 0
        return band + 12 + extra - 2 * LAB_GAP
    if kind == 'bars_labeled':
        # 同上，另加一条：引擎**没给这个 kind 调 thinLabels**，相邻两根柱的标签
        # 一宽就直接互相盖住（enx Ex30 实测重叠 10.7px），所以还要塞得进一个 band。
        return min(band + 12 - 2 * LAB_GAP, band - LAB_GAP)
    if kind == 'lines_endlabels':
        # 左端标签 anchor=end 落在 M.l − 10 − tickW，再宽就被 SVG 左边界切掉
        return m_l - 10 - (_tick_px(ex) or 26) - LAB_GAP
    return None                       # lines 的末点标签 anchor=end 往左伸，撞不到轴


def _fmt_name(old, dec):
    """缩放后的格式器名。保留「族」（$ 前缀要留着），只换小数位。

    缩放后一律不带千分位（`f0c` / `int` → `f0`）：缩完的数都在 4 位数以内，
    逗号只会把标签变宽，而标签宽正是这次要修的东西。
    """
    fam = 'usd' if str(old).startswith('usd') else 'f'
    return f'{fam}{dec}'


# ────────────────────────── 连通分量 ──────────────────────────
def _components(exhibits):
    """按「列 ↔ 图」的二部图求连通分量 → [[ex, …], …]。

    没带 `_cols` 的图各自成一个分量（不与任何人绑定）—— 这样调用方漏标一处，
    受影响的只是那一张图的倍数，不会静默地把别的图也拖走。
    """
    parent = {}

    def find(x):
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    keyed = []
    for i, ex in enumerate(exhibits):
        if not scalable(ex):
            continue
        cols = [str(c) for c in (ex.get('_cols') or [])]
        me = ('ex', i)
        find(me)
        for c in cols:
            union(me, ('col', c))
        keyed.append((me, ex))
    groups = {}
    for me, ex in keyed:
        groups.setdefault(find(me), []).append(ex)
    return list(groups.values())


# ────────────────────────── 主入口 ──────────────────────────
def fix_all(exhibits):
    """一页的 exhibits：需要时做显示缩放。原地改，返回 [(unit, 倍数, 中文词), …]。

    必须在 `axisfmt.fix_all()` 之前调用。`_cols` 一律 pop 掉，不进 payload。
    """
    exhibits = list(exhibits or [])
    applied = []
    for grp in _components(exhibits):
        if any(_MARK.search(ex.get('ylab') or '') for ex in grp):
            continue                      # 已经缩过（重复调用）：再缩一次会写出「（百万）（百万）」
        # 分量里**有一张**图压字，整个分量一起缩：同一列在长历史图与柱图里必须同量级。
        if not any(_needs(ex) for ex in grp):
            continue
        smax = [m for ex in grp for m in _series_maxes(ex)]
        if not smax:
            continue
        got = _factor(max(smax), min(smax))
        if not got:
            continue
        k, word = got
        # 先把整组的数缩完，再定小数位与格式器：`_budget()` 对 lines_endlabels 要用
        # 刻度宽，而刻度宽只有等数缩完才是最终值。
        for ex in grp:
            for obj, key in _arrays(ex):
                obj[key] = [None if v is None else round(float(v) / k, 9)
                            for v in obj.get(key) or []]
            for s in _SCALARS:
                if isinstance(ex.get(s), (int, float)):
                    ex[s] = round(float(ex[s]) / k, 9)
        for ex in grp:
            vals = [abs(x) for obj, key in _arrays(ex) for x in _fin(obj.get(key))]
            if not vals:
                continue
            dec = _decimals(vals, _budget(ex))
            new = _fmt_name(ex.get('fmt') or 'f1', dec)
            ex['fmt'] = new
            if 'label_fmt' in ex:
                ex['label_fmt'] = new
            unit = (ex.get('ylab') or '').strip()
            ex['ylab'] = f'{unit}（{word}）' if unit else word
            ex['note'] = (ex.get('note') or '') + (
                f'<b>本图纵轴与图上数值按{word}计</b>（官方原始值 ÷ {int(k):,}）：'
                f'原始量级的标签比一格柱还宽，会横向压住纵轴刻度、读成两个数粘在一起的一串。'
                f'<b>本图注文字、汇总表与末尾核对表仍是官方原始量级</b>'
                f'（核对表就是拿来与官方披露逐格对账的），两处数量级不同不是错。')
            applied.append((unit, k, word))
    for ex in exhibits:
        if isinstance(ex, dict):
            ex.pop('_cols', None)
    # 同一个单位可能有好几个分量（各按自己的量级），这里按 (单位, 倍数) 去重后回给页注
    return list(dict.fromkeys(applied))


# ══════════════════ 机器判据：缩放之后还有没有压字 / 越界 ══════════════════
# 眼睛扫 90 张切图会漏掉 2.6px 的重叠，这段算术漏不掉。判据与 docs/verify/qa/qa_geom.html
# 判的是同一件事，区别是这里在**生成端**就能跑，不用起服务器、不用等渲染。
_DEC = {'f0': 0, 'f1': 1, 'f2': 2, 'f3': 3, 'f0c': 0, 'int': 0,
        'usd0': 0, 'usd1': 1, 'usd2': 2, 'usd3': 3, 'usd4': 4,
        'pct0': 0, 'pct1': 1, 'pct2': 2, 'pct0z': 0, 'pp0': 0, 'pp1': 1, 'x0': 0}


def _efmt(v, name):
    """`charts.js:88` FMT 表的等价实现 —— **引擎的** f0/f1 不带千分位，f0c/int 才带。

    不能借用 `single.fmt_val()`：那一份一律带千分位（HTML 表格里五位数不带逗号读不动），
    拿它量标签宽会把「14640」量成「14,640」，多出 2.2px。
    """
    d = _DEC.get(name, 1)
    s = f'{abs(float(v)):.{d}f}'
    if name in ('f0c', 'int'):
        a, _, b = s.partition('.')
        s = '{:,}'.format(int(a)) + (('.' + b) if b else '')
    s = ('-' if float(v) < 0 else '') + s
    if name.startswith('usd'):
        s = '$' + s.lstrip('-') if float(v) >= 0 else '-$' + s.lstrip('-')
    if name.startswith('pct'):
        s += '%'
    if name.startswith('pp'):
        s = ('+' if float(v) >= 0 else '') + s + 'pp'
    if name == 'x0':
        s += 'X'
    return s


def _margins(ex):
    """(W, M.l, M.r, band) —— `charts.js:535` 那段 margin 分支的复算。"""
    kind, n = ex.get('kind'), len(ex.get('xlabels') or [])
    # `stacked_dual` 的右轴是**可选**的（2026-08-14 起，`line` 不给就退化成纯堆叠柱），
    # 引擎的判据是 `rhsOf(ex)`（assets/charts.js 的 `dual`），所以这里也要看 `line` 在不在。
    # 之前无条件当双轴算，右边距按 42/56 估而引擎实际用 14 —— band 被低估 28px/n，
    # 后果是偏保守（过早升通栏、过早抽稀 x 标签），不报错也看不出来。
    # build/single.py 的 groups[].mix 开始产出不带 `line` 的占比堆叠之后这条才有页面命中。
    dual = (kind == 'gs_bar' and bool(ex.get('yoy'))) or kind == 'bar_line_dual' or \
           (kind == 'stacked_dual' and bool(ex.get('line')))
    W = W_FULL if ex.get('full') else W_CARD
    m_r = (56 if ex.get('ylab2') else 42) if dual else (
        42 if kind in ('lines_endlabels', 'gs_line_avg', 'year_lines') else 14)
    m_l = (56 if ex.get('ylab') else 46) + (30 if kind == 'lines_endlabels' else 0)
    pw = max(60.0, W - m_l - m_r)
    return W, m_l, m_r, (pw / n if n else pw)


def _tick_px(ex):
    """左轴刻度里最宽的那条的像素宽（`charts.js:720` 的 tickW）。"""
    import axisfmt                                    # 只在自检时用，避免装载期循环依赖
    rng = axisfmt._left_range(ex)
    if rng is None:
        return 0.0
    y0, y1 = rng
    tk = [v for v in axisfmt.ticks(y0, y1, 9) if y0 - 1e-9 <= v <= y1 + 1e-9]
    if not tk:
        return 0.0
    name = ex.get('yfmt') or (ex.get('bar') or {}).get('yfmt')
    if name:
        return max(_label_px(_efmt(v, name), 9) for v in tk)
    step = (tk[1] - tk[0]) if len(tk) > 1 else 1.0    # 引擎的 plainAxis(step)
    d = 0 if abs(step - round(step)) < 1e-9 else \
        max(0, min(4, -int(math.floor(math.log10(abs(step) or 1)))))
    return max(_label_px(f'{abs(v):.{d}f}' if v >= 0 else f'-{abs(v):.{d}f}', 9) for v in tk)


_SYMPTOM = {'gs_bar': '柱顶标签压轴刻度', 'seasonality': '柱顶标签压轴刻度',
            'bars_labeled': '柱顶标签压轴刻度/压邻居', 'lines_endlabels': '左端标签出画布'}


def audit(exhibits):
    """缺陷 F 的机器判据 → [(n, 症状, 详情), …]。空列表 = 干净。

    与 `_needs()` 同一把尺子（`_budget`），区别只在这里量的是**实际画出来的那几个标签**，
    并且缩放跑完之后才调 —— 它回答的是「修完还剩没剩」，不是「要不要修」。

    **只判横向**，比 `qa_geom.html` 严：那边要求横竖都相交才算压字，所以
    「标签已经伸进刻度那一列、只是这个月刚好跟刻度不同高」在那边不报、在这里报。
    这是有意的 —— 那种图下个月数据一变就压上，属于同一个缺陷。
    """
    out = []
    for ex in exhibits or []:
        arrs = _arrays(ex) or []
        cap = _budget(ex) if arrs else None
        if not cap:
            continue
        kind = ex.get('kind')
        name = ex.get('label_fmt') or ex.get('fmt') or 'f1'
        size = 8.5 if kind == 'bars_labeled' else 8
        for obj, key in arrs:
            arr = obj.get(key) or []
            # 只量画在两端的那些标签：中间的标签离不开轴刻度那一列，
            # 而 bars_labeled 的相邻标签互压由 `_budget` 里那条 band − LAB_GAP 兜住。
            drawn = (arr[:1] + arr[-1:]) if kind != 'bars_labeled' else arr
            for v in drawn:
                if v is None:
                    continue
                w = _label_px(_efmt(v, name), size)
                if w > cap:
                    out.append((ex.get('n'), _SYMPTOM.get(kind, '标签过宽'),
                                f'{_efmt(v, name)} 宽 {w:.1f}px > 预算 {cap:.1f}px'))
    return out
