# -*- coding: utf-8 -*-
"""窗口与排版的边界裁决 —— 月度营收底座（`build/mrbase.py`）的边界层。

这个文件里没有任何一家公司的知识，也没有任何图注文案。它只回答两个问题：

  ① **这张图的左端该停在哪一格？**（`resolve`）
     把窗口从 20 个月拉到 127 个月，坏的不是常量，是「派生序列比主序列短」这件事
     突然变得可见：滚动同比要 24 个月历史、环比要 1 个月、单月同比要 12 个月、
     「同比的同比」要 24 个月。谁能带前导 null、谁必须截断，由**图型**决定，
     不由写图的人记性决定。

  ② **这张图放得下吗？**（`layout`）
     127 个点塞进半栏卡片，band 只剩 3.9px，柱宽 2.4px、逐点标签压进左轴刻度栏。
     这不是「看着挤」，是几何必然：band = pw / n，而字号是写死的 8px。
     所以窗口一长就必须通栏 + 抽稀 x 标签，且这件事该由算式决定不由人眼决定。

━━ ① 前导 null 的两类图型 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
`assets/charts.js` 的 `polyline(vals, c, lw, doSmooth, markers, yfn)`：

  · `doSmooth=false` 那一支逐点走 `if (vs[i] == null) { pen = false; continue; }`
    —— null 是断笔，画得对。`gs_bar` 的次轴 y/y、`qtr_bar` / `grouped_bars` 的
    `ex.line` 全走这一支，**可以带前导 null**。
  · `doSmooth=true` 那一支把整条 `vs` 交给 `smooth()` 做 Catmull-Rom，null 参与
    插值就是 NaN；`gs_line` 还要逐点 `fv(vv)` 标数值，null 上直接 TypeError，
    该卡片之后的 exhibit 全不渲染。`build/verify_pages.py` 的 `DENSE` 集合
    （gs_line / gs_line_avg / lines_endlabels / stacked_dual）就是这一类，
    数组里出现一个 null 就是 ERROR。**这类只能截断，不能补 null，更不能补假值。**

所以 `resolve()` 的返回值里，`start` 对 DENSE 图型 = 所有腿里最晚的那个首值，
对非 DENSE 图型 = 主腿的首值（派生腿的前导 null 由引擎断笔处理）。
两种情形都产出一段**可以直接贴进图注**的机读说明（`why`），因为
「派生线为何比柱短」是关于这张图的事实，不写出来读者只会以为数据缺了。

⚠️ 还有第三种情形，比前两种都隐蔽：**派生腿在窗口内一个有效值都没有**。
此时不能给次轴 —— 引擎只看 `ex.yoy` / `ex.line` 在不在就判 dual，值全是 null 时
量程退化成 [0,1]，右边印出一列假刻度而线一个点都没画（CONTRACT §6.3 最后一条）。
`resolve()` 把这种腿标成 `drop=True`，由底座整条摘掉并在图注里点名。

━━ ② 排版：band 的算式照抄 charts.js ━━━━━━━━━━━━━━━━━━━━━━━━━━━━
`draw()` 里：

    M.l = fscale((ylab ? 56 : 46) + (kind === 'lines_endlabels' ? 30 : 0))
    M.r = fscale(dual ? (ylab2 ? 56 : 42)
                      : (lines_endlabels|gs_line_avg|year_lines ? 42 : 14))
    pw  = max(60, W - M.l - M.r)
    band = pw / n

半栏卡片宽 `(内容宽 − 30) / 2`（`.grid` 是两列 + 30px gap），通栏 = 内容宽。
`fscale` 只在窄屏放大字号，桌面设计宽度下是 1.0，这里按 1.0 算 —— 我们要挡的是
「桌面上就已经挤爆」，窄屏更挤是同一结论的加强版，不是另一个结论。

阈值 `MIN_BAND = 6.0px`：`gs_bar` 的柱宽是 `BW(0.62)`，band 6px → 柱 3.7px；
`grouped_bars` 单组是 `BW(0.74)` → 4.4px；再窄就是「一排竖线」而不是柱图了。
这个数不是从美学来的，是从既有页反推的：现网 Exhibit 7/8 是 127 点通栏折线，
band 8.4px，可读；同样 127 点放半栏是 3.6px。而且这一格**有成文规矩**：
`build/CONTRACT.md` 的 `full` 字段那一行原文就是
「`full` | True 走通栏（127 根柱塞进半栏每根不到 3px，必须通栏）」——
所以对 127 点的柱图来说，通栏不是可读性偏好，是照章办事。

━━ 几何模型只有一处，在 build/chartscale.py ━━━━━━━━━━━━━━━━━━━━━━━━
`_margins` / `band_px` **不在这里重新实现**，直接调 `chartscale._margins(ex)`。
全站现在已经有过三份互相抄来的量边距算式（tsm.py、axp.py、chartscale.py），
再抄第四份的下场是改一处漏三处。本文件只负责「拿 band 去判事」。
"""

import math

import chartscale

# assets/charts.js 的 DENSE 同义集（与 build/verify_pages.py:61 逐字相同，改一处要改两处）。
DENSE = {'gs_line', 'gs_line_avg', 'lines_endlabels', 'stacked_dual'}

MIN_BAND = 6.0        # px。低于它就必须通栏，理由见文件头
# 卡片宽度不在本文件定义：`chartscale.W_CARD` = 571、`W_FULL` = 1172。
# 那两个数是浏览器实测校准过的（1400px 视口下量到通栏卡片 clientWidth = 1172、
# 半栏 571 = (1172−30)/2），不是照 `.wrap` 的 max-width 1240 直接抄 ——
# 抄 1240 会把 band 高估 6%，而 6% 恰好够让「3.6px」看成「3.9px」，判到阈值另一边去。
# 90° 旋转的 x 标签横向占位。charts.js 的 `fitSize(base, cap) = max(base, min(base*FS, cap))/FS`
# 在桌面（FS=1）下**永远取 base=8.2**，那个 max() 让它不会因为 band 变窄而缩小 ——
# 也就是说 x 标签的横向占位是写死的 8.2px，band 一低于它就实打实叠字。
# 再加 1.4px 最小间隙（与 charts.js 自己给数值标签定的 LAB_GAP=1.5 同量级）。
XLAB_W = 9.6
# 长月份轴上的编辑上限：即使不叠字，127 个月份标签也是一堵字墙。
# 这个数不是拍的 —— 现网 Exhibit 7／8 就是 127 点长历史图，用的是 `xstep: 9`（15 个标签），
# 本底座沿用同一密度。只对 n > 60 的轴生效：季度轴（43 格）本来就稀疏，抽了反而难定位。
MAX_XLABS, LONG_AXIS_N = 20, 60
# 「柱顶逐格标签不被引擎抽稀」的图型 —— charts.js 只对 gs_bar / gs_line / gs_line_avg
# 调 `thinLabels()`；`qtr_bar` 的 `vLabel` 是**每根柱都画**的，一个都不抽。
#
# VLABEL_W 由浏览器**实测反推**，不是从字号推的：43 个季度放半栏时 band = 10.67px，
# 42 个相邻标签间隙全部为负、中位 −2.03px ⇒ 实际占位 = 10.67 + 2.03 = 12.70px。
# 阈值再加 1.5px 最小间隙（charts.js 自己的 LAB_GAP 就是 1.5）。
#
# ⚠️ 这个 12.7 量的是 getBoundingClientRect 的**行盒**，不是墨迹。复核时另用
#    getBBox + getScreenCTM 的墨迹 OBB（tools/visual_qa.py 的口径）量过同一批元素：
#    墨迹口径下 0 对相交，行盒口径下 83 对相邻为负。两个口径都不假 ——
#    「41 对文字实打实叠在一起」是**行盒**重叠，不是肉眼可见的墨迹重叠。
#    保留这条规则是因为结论另有独立依据（CONTRACT 那一行的通栏规矩 + 竖排标签
#    在 qtr_bar 上一根不抽），而不是因为墨迹相交；写在这里免得下一个人把
#    「行盒重叠」当成「压字」再去改引擎。
# 真正撑住这条规则的事实是：charts.js 只对 gs_bar / gs_line / gs_line_avg 调
# `thinLabels()`，`qtr_bar` 的 `vLabel` 每根柱都画、一个不抽 —— 所以「band 高于
# 柱宽下限就放得下」对 qtr_bar 不成立，它需要一个更高的下限。
VLABEL_KINDS = {'qtr_bar'}
VLABEL_W = 12.7


def _ok(v):
    return v is not None and v == v and abs(v) != float('inf')


def _first_finite(vals):
    for i, v in enumerate(vals):
        if _ok(v):
            return i
    return None


def _last_finite(vals):
    for i in range(len(vals) - 1, -1, -1):
        if _ok(vals[i]):
            return i
    return None


def _dense_first(vals):
    """**从这一格往右一个洞都没有**的第一格；整条无值或末尾就是洞时返回 None。

    与 `_first_finite` 的差别只在中段空洞：`[1, 2, None, 4, 5]` 的首个有值点是 0，
    但平滑图型从 0 起画会把中间那个 null 送进 Catmull-Rom（当 0 插值 → 一条塌到零的
    假线；`gs_line` 还要逐点标数值，直接 TypeError 让该卡片以下全不渲染）。
    稠密区间只能从**最后一个洞之后**起算。

    今天这 7 家的序列没有中段洞，所以这条分支跑不到 —— 它防的是「某家改了数据源、
    中间缺了一个月」这种以后必然会发生、而且不会报错只会画错的情形。
    """
    j = _first_finite(vals)
    if j is None:
        return None
    holes = [i for i in range(j, len(vals)) if not _ok(vals[i])]
    if holes:
        j = holes[-1] + 1
    return j if j < len(vals) else None


class Leg:
    """一条画在图上的序列。`role='primary'` 的腿定义窗口左端，`'derived'` 的腿可以更短。

    `labels` 是与 `vals` 同长的期标签（月份 / 季度串），只用来在图注里说清
    「这条线的第一点落在哪一期」—— 图注里的期号必须是真的期号，不是下标。
    """

    def __init__(self, key, zh, vals, role='derived', lag_zh=''):
        self.key, self.zh, self.vals, self.role, self.lag_zh = key, zh, list(vals), role, lag_zh
        self.first = _first_finite(self.vals)
        # 平滑图型用这个（见 _dense_first）：中段有洞时首个**稠密**格在洞的右边。
        self.dense_first = _dense_first(self.vals)
        self.last = _last_finite(self.vals)
        self.drop = False

    def start_of(self, dense):
        return self.dense_first if dense else self.first


class Win:
    """`resolve()` 的结果。"""

    def __init__(self, start, n_total, legs, kind, why, truncated):
        self.start, self.n_total, self.legs, self.kind = start, n_total, legs, kind
        self.why, self.truncated = why, truncated

    @property
    def n(self):
        return self.n_total - self.start

    def cut(self, vals):
        """按裁决出来的左端切一条与全序列同长的数组。"""
        return list(vals)[self.start:]


def resolve(kind, legs, labels, want_from=0):
    """裁决左端 + 产出「为什么这条线比那条短」的机读说明。

    kind      图型名（决定能不能吃 null）
    legs      list[Leg]，至少一条 role='primary'
    labels    与全序列同长的期标签
    want_from 调用方想要的左端下标（例如「2016-01 起」）。裁决只会**往右**让，
              不会往左借 —— 没有的数据造不出来。

    返回 Win。`Win.why` 是一段 HTML 片段，空串表示「没什么可解释的」。
    """
    n_total = len(labels)
    prim = [l for l in legs if l.role == 'primary']
    if not prim:
        raise ValueError('resolve() 至少要有一条 role="primary" 的腿')

    dense = kind in DENSE
    # 主腿必须有值：主腿都没有的那一段，画什么都是空的。
    base = max([l.start_of(dense) for l in prim if l.start_of(dense) is not None] or [0])
    start = max(want_from, base)

    if dense:
        # 平滑图型：窗口里任何一条腿有 null 都是 ERROR，只能把左端推到最晚的那条腿
        # ——「最晚」按**稠密**首格算（中段洞的右边），不是按首个有值点算。
        cand = [l.dense_first for l in legs if l.dense_first is not None]
        if len(cand) != len(legs):        # 有腿整条无值 → 那条腿必须摘掉，不能画空线
            for l in legs:
                if l.dense_first is None:
                    l.drop = True
            cand = [l.dense_first for l in legs if l.dense_first is not None]
        start = max([start] + cand)

    for l in legs:
        if l.drop:
            continue
        # 窗口内一个有效值都没有的腿：非 DENSE 图型也不能留 —— 引擎只看字段在不在就判
        # dual，右轴会印出一列假刻度而线一个点都没画（CONTRACT §6.3）。
        if l.first is None or l.first > (l.last if l.last is not None else -1) or l.last is None \
                or l.last < start:
            l.drop = True

    late = [l for l in legs
            if not l.drop and l.role != 'primary' and l.first is not None and l.first > start]
    dropped = [l for l in legs if l.drop]

    bits = []
    if dense and start > want_from:
        who = '、'.join(f'{l.zh}（{l.lag_zh}，首点 {labels[l.first]}）'
                        for l in legs if l.first == start and l.role != 'primary') \
            or f'{labels[start]}'
        bits.append(
            f'<b>本图左端截在 {labels[start]}，不是序列起点 {labels[0]}</b>：'
            f'{kind} 是平滑图型，引擎把 null 交给 Catmull-Rom 插值会画出一条塌到零的假线、'
            f'逐点标数值时还会抛异常，所以窗口只能从「所有线都已经有值」的那一期开始 —— '
            f'定住左端的是{who}。'
            f'补零或补上一期的值都能让图画满，但那是<b>画一个数据里不存在的点</b>，本页不做。')
    if late:
        for l in late:
            bits.append(
                f'<b>{l.zh}比柱短 {l.first - start} 期</b>：{l.lag_zh}，'
                f'第一个能算出来的期是 {labels[l.first]}，'
                f'在此之前引擎按 null 断笔（不画、也不补值），所以左段只有柱没有线。')
    for l in dropped:
        bits.append(
            f'<b>{l.zh}本轮整条画不出来</b>（{l.lag_zh}，窗口内没有任何一期算得出），'
            f'已整条摘掉而不是画成一条全 null 的线 —— 引擎只看字段在不在就判双轴，'
            f'留着会印出一列没有线的右轴刻度。')

    return Win(start, n_total, legs, kind, ''.join(bits), start > want_from)


# ────────────────────────────── 排版 ──────────────────────────────
def _probe(ex, full=None):
    """喂给 `chartscale._margins` 的等价 ex。

    ⚠️ 两处口径差，都在这里对齐，**不改 chartscale.py**（那个文件被全站 audit 用着，
    改它是另一次改动）：
      · `chartscale._margins` 的 dual 判据是 `gs_bar+yoy | bar_line_dual | stacked_dual`，
        漏了 `qtr_bar` / `grouped_bars` 带 `ex.line` 的情形；而 `assets/charts.js:740`
        把这两种也算 dual（右边距 42/56 而不是 14）。这里用 `bar_line_dual` 顶替去问，
        m_l 不受 kind 影响（只看 ylab 与 lines_endlabels），m_r 正好等于 charts.js 的值。
      · `full=True/False` 用来问反事实（「升通栏之后 band 是多少」），不改原 ex。
    """
    p = dict(ex)
    if p.get('kind') in ('qtr_bar', 'grouped_bars') and (p.get('line') or p.get('yoy')):
        p['kind'] = 'bar_line_dual'
    if full is not None:
        p['full'] = bool(full)
    return p


def band_px(ex, full=None):
    """一格占多少像素 —— 走 `chartscale._margins(ex)`，本文件不再复算一遍几何。"""
    if not (ex.get('xlabels') or []):
        return float('inf')
    return chartscale._margins(_probe(ex, full))[3]


def layout(ex, min_band=MIN_BAND):
    """就地给 exhibit 补 `full` / `xstep`，并返回一段可贴进图注的实测说明。

    两件事，都由算式决定：
      · band 低于阈值 → 通栏。通栏仍低于阈值就照实说（没有第三档可升，
        剩下的办法只有缩窗口，而窗口是用户指定的）。
      · x 标签 90° 旋转后横向占 ≈ 一个字号，band 装不下就按步长抽稀 ——
        `xstep` 只影响标签，不影响数据点，抽稀不丢数。
    """
    kind = ex.get('kind')
    if kind == 'heat_matrix':
        return ''
    labs = ex.get('xlabels') or []
    n = len(labs)
    if not n:
        return ''
    half = band_px(ex, full=False)
    fullb = band_px(ex, full=True)

    # ── 逐格标签不被引擎抽稀的图型，阈值另算（见文件头 VLABEL_W 那段的注意事项）──
    need = min_band
    if kind in VLABEL_KINDS and ex.get('bar_labels') is not False:
        need = max(need, VLABEL_W + 1.5)

    txt = ''
    if half < need and not ex.get('full'):
        ex['full'] = True
        extra = ('' if need == min_band else
                 f'（本图型的柱顶竖排标签<b>每根都画、引擎不抽稀</b>，实测占 {VLABEL_W:.1f}px，'
                 f'所以下限比一般柱图的 {min_band:.0f}px 高）')
        txt = (f'<b>本图通栏</b>：{n} 期塞进半栏卡片，每期只有 {half:.1f}px'
               f'{extra}，低于 {need:.1f}px 的可读下限；'
               f'通栏后是 {fullb:.1f}px。这一步由构建期按 <code>assets/charts.js</code> 的'
               f'量边距算式复算得出，不是目测。')
        if fullb < need:
            txt += (f'⚠️ 通栏仍只有 {fullb:.1f}px —— 已无更宽的档位，'
                    f'逐点数值标签会被引擎按实测 bbox 抽稀，读数请走右上角「表格」。')
    used_full = bool(ex.get('full'))
    b = fullb if used_full else half
    if ex.get('xrot') == 90 and not ex.get('xstep'):
        clash = int(math.ceil(XLAB_W / b)) if b < XLAB_W else 1
        crowd = int(math.ceil(n / MAX_XLABS)) if n > LONG_AXIS_N else 1
        step = max(clash, crowd)
        if step > 1:
            ex['xstep'] = step
            why = []
            if clash > 1:
                why.append(f'90° 旋转后每个标签横向固定占 {XLAB_W:.1f}px（引擎在桌面不缩字号），'
                           f'而每期只有 {b:.1f}px')
            if crowd > 1:
                why.append(f'{n} 期全标是一堵字墙，沿用现网 127 点长历史图的密度'
                           f'（约 {MAX_XLABS} 个标签）')
            txt += ('x 轴标签每 ' + str(step) + ' 期标一个：' + '；'.join(why)
                    + '。抽的是标签不是数据点，柱与线的每一期都还在。')
    return txt


def label_clash(ex, full=None):
    """首点/末点数值标签压进轴刻度栏 —— 量出来，不改图。**尺子是 chartscale 的，不是新造的。**

    `gs_bar` / `gs_line` 的逐点标签居中钉在自己那一格上，刻度右对齐在 `M.l − 6`，
    所以间隙 = (band + 12 − 标签宽) / 2，要求它不小于引擎自己的 `LAB_GAP = 1.5px`
    ⇒ 标签宽度预算 = band + 12 − 3（`chartscale._budget`）。

    返回 dict：band / 预算 / 实际最宽标签 / 超出多少 px；`None` = 这个 kind 没有硬约束
    （`_budget` 返回 None，例如 `lines` 的末点标签向左伸、撞不到轴）。

    ⚠️ 用法上的规矩（这一轮三份实现里两份栽在这上面）：要断言「本轮**引入**了这个
    冲突」，必须先拿**旧 payload** 量同一个指标做反事实对照。`full=True/False` 参数就是
    为此留的 —— 先问「半栏时多少」再问「通栏后多少」，不然「既有问题」会被说成「新问题」。
    """
    p = _probe(ex, full)
    cap = chartscale._budget(p)
    if not cap:
        return None
    arrs = chartscale._arrays(p) or []
    name = p.get('label_fmt') or p.get('fmt') or 'f1'
    size = 8.5 if p.get('kind') == 'bars_labeled' else 8
    drawn = []
    for obj, key in arrs:
        arr = obj.get(key) or []
        drawn += [v for v in (arr[:1] + arr[-1:]) if v is not None]
    if not drawn:
        return None
    w = max(chartscale._label_px(chartscale._efmt(v, name), size) for v in drawn)
    return {'band': chartscale._margins(p)[3], 'cap': cap, 'w': w, 'over': w - cap}


# ────────────────────────────── 自检 ──────────────────────────────
def _selftest():
    """`python3 build/mrwin.py` —— 对着六类已知失败模式各跑一遍。

    「今天没报错」与「规则坏了」在输出上长得一模一样，只有对着**已知错例**跑
    才分得开（同 tools/check_yoy_caliber.py --selftest 的理由）。
    """
    N = 127
    lab = [f'M{i:03d}' for i in range(N)]
    n_ok = 0

    def ck(cond, msg):
        nonlocal n_ok
        print(('  OK   ' if cond else '  FAIL ') + msg)
        n_ok += bool(cond)

    # ① 平滑图型 + 派生腿更短 ⇒ 必须截断到最晚的首值，且窗口内不许有 null
    bar = [1.0] * N
    lag12 = [None] * 12 + [1.0] * (N - 12)
    w = resolve('lines_endlabels', [Leg('a', '本币同比', bar, 'primary'),
                                    Leg('b', '美元同比', lag12, 'derived', '要 12 个月')], lab, 0)
    ck(w.start == 12 and None not in w.cut(lag12), 'DENSE 图型截断到 idx 12，窗口内无 null')
    ck('<b>本图左端截在' in w.why, 'DENSE 截断产出了图注文字')

    # ② 柱图型 + 派生腿更短 ⇒ 保留前导 null，并解释「线为什么比柱短」
    lag24 = [None] * 24 + [1.0] * (N - 24)
    w = resolve('gs_bar', [Leg('a', '柱', bar, 'primary'),
                           Leg('b', '滚动同比', lag24, 'derived', '要 24 个月')], lab, 0)
    ck(w.start == 0 and w.cut(lag24)[:24] == [None] * 24, 'gs_bar 保留 24 个前导 null')
    ck('比柱短 24 期' in w.why, '产出了「线比柱短几期」的图注文字')

    # ③ 派生腿在窗口内一个值都没有 ⇒ drop，绝不留一条全 null 的次轴
    dead = [None] * N
    w = resolve('gs_bar', [Leg('a', '柱', bar, 'primary'),
                           Leg('b', '滚动同比', dead, 'derived', '历史不够')], lab, 0)
    ck([l for l in w.legs if l.key == 'b'][0].drop, '整条无值的次轴腿被 drop')

    # ④ 排版：127 点半栏必须升通栏；qtr_bar 的竖排标签阈值比一般柱图高
    ex = {'kind': 'gs_bar', 'xlabels': lab, 'xrot': 90, 'ylab': 'x', 'ylab2': 'y',
          'yoy': {'values': bar}}
    t = layout(ex)
    ck(ex.get('full') and ex.get('xstep') == 7, f'127 点 gs_bar 升通栏 + xstep=7（得 {ex.get("xstep")}）')
    q = {'kind': 'qtr_bar', 'xlabels': lab[:35], 'xrot': 90, 'ylab': 'x',
         'line': {'values': [1.0] * 35}}
    layout(q)
    ck(q.get('full'), '35 个季度的 qtr_bar 升通栏（band 13.5px > 6px 的柱宽下限，'
                      '但低于竖排标签实测占位 12.7px + 间隙）')
    q2 = {'kind': 'qtr_bar', 'xlabels': lab[:14], 'xrot': 90, 'ylab': 'x',
          'line': {'values': [1.0] * 14}}
    layout(q2)
    ck(not q2.get('full'), '14 个季度（迁移前的窗口）仍走半栏，不动既有版式')

    # ⑤ 中段空洞：平滑图型的稠密区间必须从**最后一个洞之后**起算，不是首个有值点。
    #    这一条今天 7 家都跑不到（没有一家的序列中间缺月），加它是因为「数据源改了、
    #    中间少一个月」这件事不会报错，只会画出一条塌到零的假线。
    holed = [1.0] * 5 + [None] + [1.0] * (N - 6)
    w = resolve('gs_line', [Leg('a', '环比', holed, 'primary')], lab, 0)
    ck(w.start == 6 and None not in w.cut(holed),
       f'中段有洞的 DENSE 序列从洞之后起算（得 start={w.start}）')
    w2 = resolve('gs_bar', [Leg('a', '柱', holed, 'primary')], lab, 0)
    ck(w2.start == 0, '同一条序列在柱图型上仍从首个有值点起（柱容忍中段 null，断笔即可）')

    # ⑥ 标签宽度预算走 chartscale 的尺子：同一张图升通栏之后预算必须变宽。
    #    （这是「拉长窗口是不是引入了压字」那件事的反事实对照入口。）
    g = {'kind': 'gs_bar', 'xlabels': lab, 'xrot': 90, 'ylab': 'x', 'ylab2': 'y',
         'fmt': 'f0', 'label_fmt': 'f0', 'values': [123456.0] * N,
         'yoy': {'values': bar}}
    c_half = label_clash(g, full=False)
    c_full = label_clash(g, full=True)
    ck(c_half and c_full and c_full['cap'] > c_half['cap'] and c_half['w'] == c_full['w'],
       f'升通栏把标签预算从 {c_half["cap"]:.1f}px 抬到 {c_full["cap"]:.1f}px（标签本身不变）')

    print(f'── mrwin 自检：{n_ok}/11 通过 ──')
    return 0 if n_ok == 11 else 1


if __name__ == '__main__':
    raise SystemExit(_selftest())
