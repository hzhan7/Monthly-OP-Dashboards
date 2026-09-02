# -*- coding: utf-8 -*-
"""gsx — GS/JPM 月度经营数据 exhibit 制图内核（仅版式，不含任何数据）。

图型来源（均由投行原件拆解得出，见 SOURCES）：
  lvl_bar         水平柱 + 次轴金色 y/y 折线（不用滚动均线：均线只是把柱子再平滑一遍，不带新信息）
  chg_line        变化率曲线 + 零轴 + 每点标签。**m/m 仅用于同比已饱和的高增速指标**
  stack_share     GS Monthly Ex7 版式  堆叠柱 + 次轴占比折线（体量与结构同框）
  multi_line      GS Monthly Ex9 版式  多序列平滑曲线，只在首/末标数值
  rev_bar_yoy     GS 台股月营收 Ex1    深色=已公布/浅色=预测 柱 + 次轴金色 YoY 折线
  seasonality     JPM AXP Fig2         灰=过去N年同月均值 / 蓝=当期实际 的配对柱
  month_box       JPM AXP Fig3         逐日历月箱线图 + 当年/去年标记
  heat_matrix     JPM AXP Fig4         月 x 年热力矩阵
  long_line       GS HKEX Ex1          超长历史单序列折线 + 末端数据标签 + 最新点红圈
  summary_table   GS Monthly Ex1       汇总表 本月|上月|去年同月 ‖ m/m|y/y|近 3 年分位（后三列红绿着色）

页面：A4 竖版，2 列 x 3 行 = 6 exhibit/页。

同比口径：本模块画的每一条 y/y 都是**单月**（`qtr_bar` 是单季度）口径 —— 本期 ÷ 去年
同期 − 1。`lvl_bar` / `chg_line` / `rev_bar_yoy` / `qtr_bar` / `zscore_panel` 五处一律
如此，没有一处做 12 个月滚动合计，与 `build/CONTRACT.md` §6「全站同比只有一种口径：
单月同比」同向。要往这里加图型的人注意：**不要**在本模块里新开一条滚动合计的同比线，
那是契约明令不画的东西。
比率序列的同比走**百分点差**（CONTRACT §6.1 第 4 条），本模块只有两处走得了：
`lvl_bar(pct_series=True)` 与 `summary_table` 的 `pp` / `abs` 模式。**`chg_line` 没有
比率分支**，`kind='yoy'` 一律按比值算 —— 别拿它画费率、占比、逾期率，那会印出
「百分比的百分比变化」。现有五处调用全是量与余额，没有一处是比率。
"""
import os
import datetime as _dt
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Ellipse, Patch
from matplotlib.lines import Line2D

plt.rcParams.update({
    'font.family': 'sans-serif',
    'font.sans-serif': ['Arial', 'Helvetica', 'Arial Unicode MS', 'Hiragino Sans GB'],
    'axes.edgecolor': '#999999', 'axes.linewidth': 0.6,
    'xtick.color': '#333333', 'ytick.color': '#333333', 'text.color': '#000000',
    'axes.unicode_minus': False,
    'pdf.fonttype': 42,
})

BLUE  = '#9DC3E6'   # 浅蓝：水平柱
NAVY  = '#1F3864'   # 藏青：均线 / 变化率曲线 / 主序列
MBLUE = '#2E75B6'   # 中蓝：第三序列
GRAY  = '#A6A6A6'   # 灰：季节性基准
GREEN = '#548235'   # 绿：占比线 / 正向
RED   = '#B23A48'   # 红：负向
GOLD  = '#BF9000'   # 金：台股月营收 YoY 线
GRID  = '#E3E3E3'
LGRAY = '#D9D9D9'

PAGE = (8.27, 11.69)   # A4 portrait, inches
MX = 0.065             # 左右页边距（figure fraction）


# ────────────────────────────── 页面与网格 ──────────────────────────────
class Deck:
    """一份 PDF。负责页眉页脚、exhibit 编号、2x3 网格分配。"""

    def __init__(self, pdf, title, subtitle, footer, start_ex=1):
        self.pdf = pdf
        self.title = title
        self.subtitle = subtitle
        self.footer = footer
        self.n = start_ex - 1
        self.page_no = 0
        self.fig = None
        self._slot = 0

    # -- exhibit 编号 --
    def nxt(self):
        self.n += 1
        return self.n

    # -- 分页 --
    def _new_page(self):
        self.flush()
        self.fig = plt.figure(figsize=PAGE)
        self.page_no += 1
        f = self.fig
        f.text(MX, 0.975, self.title, fontsize=11.5, fontweight='bold')
        f.text(MX, 0.9585, self.subtitle, fontsize=7.4, color='#444444')
        f.add_artist(Line2D([MX, 1 - MX], [0.951, 0.951], color=NAVY, lw=1.0,
                            transform=f.transFigure))
        f.text(MX, 0.014, self.footer, fontsize=6.8, color='#555555')
        f.text(1 - MX, 0.014, str(self.page_no), fontsize=7.5, ha='right', color='#555555')
        self._slot = 0

    def flush(self):
        if self.fig is not None:
            self.pdf.savefig(self.fig)
            plt.close(self.fig)
            self.fig = None

    def ax(self, h_scale=1.0, full_width=False):
        """取下一个 exhibit 画布。full_width=True 占整行（用于宽表）。"""
        if self.fig is None or self._slot >= 6:
            self._new_page()
        if full_width and self._slot % 2 == 1:
            self._slot += 1                       # 宽 exhibit 必须从行首开始
            if self._slot >= 6:
                self._new_page()
        row, col = divmod(self._slot, 2)
        gap = 0.082
        w = (1 - 2 * MX - gap) / 2
        top, bot = 0.928, 0.045
        hh = (top - bot) / 3
        x = MX + col * (w + gap)
        y = top - (row + 1) * hh + 0.083
        h = (hh - 0.138) * h_scale
        if full_width:
            w = 1 - 2 * MX
            self._slot += 2
        else:
            self._slot += 1
        return self.fig.add_axes([x, y, w, h])


# ────────────────────────────── 通用零件 ──────────────────────────────
def mlab(p):
    return p.strftime('%b-%y')


def _esc(t):
    """转义 $，否则一句话里出现两个 $ 会被 matplotlib 当成 mathtext 渲染成斜体公式。"""
    return str(t).replace('$', r'\$')


def style_ax(ax, ygrid=True):
    if ygrid:
        ax.grid(axis='y', color=GRID, lw=0.6, zorder=0)
    ax.set_axisbelow(True)
    for s in ('top', 'right'):
        ax.spines[s].set_visible(False)
    ax.tick_params(labelsize=6.2, length=2, width=0.5)


def title(ax, n, text, width=52):
    import textwrap as _tw
    full = f'Exhibit {n}: {text}'
    lines = _tw.wrap(full, width)[:2]
    ax.text(0, 1.20 if len(lines) == 1 else 1.20, _esc('\n'.join(lines)),
            transform=ax.transAxes, fontsize=8.0, fontweight='bold', va='bottom')


def src(ax, text, extra='', width=None, max_lines=4):
    import textwrap as _tw
    if width is None:
        # 按「画布左缘 → 页面右边距」的实际可用宽度折行。
        # 不能只看画布宽度：z 面板的画布被整体右移过，只按宽度算会让注释冲出页面。
        try:
            bb_ = ax.get_position()
            # 半宽图按自身宽度折行（右边是另一张图，不能占）；
            # 全宽图按「左缘 → 页面右边距」折行（z 面板的画布被右移过，不能只看宽度）。
            avail = bb_.width if bb_.width < 0.6 else ((1 - MX) - bb_.x0)
            width = max(60, int(avail * 236))          # 236 ≈ 5.6pt 字在整页宽下的字符数
        except Exception:
            width = 96
    lines = []
    for chunk in ([text] + ([extra] if extra else [])):
        lines += _tw.wrap(chunk, width) or ['']
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1][:width - 1].rstrip() + '…'
    ax.text(0, -0.30, _esc('\n'.join(lines)), transform=ax.transAxes, fontsize=5.6,
            color='#333333', va='top', linespacing=1.30)


def legend(ax, ncol=3, loc_y=1.01):
    h, l = ax.get_legend_handles_labels()
    if not h:
        return
    ax.legend(h, [_esc(x) for x in l], loc='lower left', bbox_to_anchor=(0, loc_y), ncol=ncol,
              frameon=False, fontsize=6.0, handlelength=1.2, handleheight=0.9,
              columnspacing=0.9, borderaxespad=0)


def month_xticks(ax, idx, step=None):
    n = len(idx)
    if step is None:
        step = 1 if n <= 14 else (2 if n <= 28 else (3 if n <= 50 else max(1, n // 18)))
    ax.set_xticks(range(0, n, step))
    ax.set_xticklabels([mlab(p) for p in idx[::step]], rotation=90, fontsize=5.5)


def _fmt(v, dec=1, pct=False, money=''):
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return ''
    s = f'{v:,.{dec}f}'
    out = (money + s + '%') if pct else (money + s)
    return _esc(out)


def bubble(ax, xy, text, color=NAVY, w=0.155, h=0.135):
    """GS 式椭圆气泡标注（axes fraction 坐标）。"""
    e = Ellipse(xy, w, h, transform=ax.transAxes, facecolor='white',
                edgecolor=color, lw=0.9, zorder=20, clip_on=False)
    ax.add_patch(e)
    ax.text(xy[0], xy[1], text, transform=ax.transAxes, ha='center', va='center',
            fontsize=6.6, fontweight='bold', color=color, zorder=21, clip_on=False)


def _yoy(v, i, lag=12):
    if i - lag < 0 or not np.isfinite(v[i]) or not np.isfinite(v[i - lag]) or v[i - lag] == 0:
        return np.nan
    return v[i] / v[i - lag] - 1


def _mom(v, i):
    if i < 1 or not np.isfinite(v[i]) or not np.isfinite(v[i - 1]) or v[i - 1] == 0:
        return np.nan
    return v[i] / v[i - 1] - 1


def _pp(x):
    if not np.isfinite(x):
        return ''
    v = x * 100
    return f'{v:+.1f}%' if abs(v) < 2 else f'{v:+.0f}%'



def _tail_contiguous(s):
    """只保留序列末尾「逐月连续」的一段。

    有些披露中间断档（如港交所南向通 2022-2024 缺 40 个月），直接 dropna 后取
    最后 N 个点，会把相隔数年的月份并排画成相邻柱子 —— 那是假的时间轴。
    """
    s = s.dropna()
    if len(s) < 3:
        return s
    idx = list(s.index)
    gaps = [(idx[i] - idx[i - 1]).n for i in range(1, len(idx))]
    # 用众数步长判断「正常间隔」：季度间隔的序列（步长恒为 3）不是断档，不能截
    stride = max(set(gaps), key=gaps.count)
    start = 0
    for i in range(len(idx) - 1, 0, -1):
        if (idx[i] - idx[i - 1]).n != stride:
            start = i
            break
    return s.iloc[start:]


def _draw_break(ax, idx, break_at, label):
    """在指定月份处画一条红色竖虚线，标出口径断点/并表等不可连比的位置。"""
    if break_at is None:
        return
    idx = list(idx)
    bp = pd.Period(break_at, 'M') if not isinstance(break_at, pd.Period) else break_at
    if bp not in idx:
        return
    x = idx.index(bp)
    ax.axvline(x - 0.5, color=RED, lw=1.0, ls=(0, (3, 2)), zorder=11)
    lo, hi = ax.get_ylim()
    ax.text(x - 0.72, lo + (hi - lo) * 0.02, label, fontsize=5.2, color=RED,
            va='bottom', ha='right', rotation=90, zorder=12)


# ────────────────────────────── 图型 1：GS 水平图 ──────────────────────────────
def lvl_bar(deck, s_full, ttl, source, *, win=13, dec=1, money='', unit='',
            extra='', labels=True, pct_series=False, show_mom=False,
            break_at=None, break_label='basis change', yoy_label=None):
    """浅蓝柱（水平值） + 次轴金色 y/y 折线。

    次轴画的是同比而不是滚动均线 —— 均线只是把柱子再平滑一遍、不带新信息，
    同比才回答「相对去年这个月是好是坏」。
    比率序列（pct_series=True）的同比用**百分点差**，不是「百分比的百分比变化」。
    show_mom=True 时才额外给一个环比气泡：只有同比已经饱和、看不出月度动能的
    高增速指标才需要环比，普通增速指标的环比是噪音。
    """
    ax = deck.ax()
    s = _tail_contiguous(s_full)
    d = s.iloc[-win:]
    x = np.arange(len(d))
    ax.bar(x, d.values, 0.72, color=BLUE, zorder=3, label='Monthly')
    if labels:
        rng = np.nanmax(d.values) - min(0, np.nanmin(d.values))
        every = 1 if len(d) <= 14 else 2
        for i, v in enumerate(d.values):
            if np.isfinite(v) and (i % every == 0 or i == len(d) - 1):
                ax.text(i, v + rng * 0.03, _fmt(v, dec, money=money), ha='center',
                        va='bottom', fontsize=5.2, color='#222222', zorder=6)

    # ── 同比序列 ──
    v = s.values
    # 序列步长决定同比的滞后期数：月度 = 12 期，季度间隔（步长 3）= 4 期
    _g = [(s.index[i] - s.index[i - 1]).n for i in range(1, len(s))] or [1]
    _stride = max(set(_g), key=_g.count)
    LAG = max(1, round(12 / _stride))
    scale = np.nanmedian(np.abs(v)) or 1.0
    yv = np.full(len(v), np.nan)
    for i in range(LAG, len(v)):
        a, b = v[i], v[i - LAG]
        if not (np.isfinite(a) and np.isfinite(b)):
            continue
        if pct_series:
            yv[i] = a - b                              # 比率 → 百分点差
        elif abs(b) < 0.15 * scale or a * b < 0:
            continue                                   # 基数过小或异号，同比无意义
        else:
            yv[i] = (a / b - 1) * 100
    ys = pd.Series(yv, index=s.index).iloc[-win:]
    lab = yoy_label or (('y/y (pp, RHS)' if pct_series else 'y/y (RHS)')
                        if LAG == 12 else ('y/y (pp, RHS)' if pct_series else 'y/y (RHS)'))
    ax2 = ax.twinx()
    if np.isfinite(ys.values).any():
        ax2.plot(x, ys.values, color=GOLD, lw=1.6, marker='o', ms=2.3, zorder=7, label=lab)
        ax2.axhline(0, color=GOLD, lw=0.5, ls=':', zorder=2)
        last = np.where(np.isfinite(ys.values))[0]
        if len(last):
            j = last[-1]
            # 用 offset 把标签推到点的右下方，避开柱顶数值标签
            ax2.annotate(f'{ys.values[j]:+.0f}' + ('pp' if pct_series else '%'),
                         xy=(j, ys.values[j]), xytext=(5, -7), textcoords='offset points',
                         fontsize=6.2, color=GOLD, fontweight='bold', va='center',
                         ha='left', zorder=9, annotation_clip=False)
        ax2.set_xlim(-0.9, len(d) - 0.1)
        lo_y, hi_y = np.nanmin(ys.values), np.nanmax(ys.values)
        pad = max((hi_y - lo_y) * 0.30, 1.0)
        ax2.set_ylim(lo_y - pad, hi_y + pad * 2.6)     # 同比线压在画布上半，不压柱子
    if np.isfinite(ys.values).any():
        ax2.tick_params(labelsize=6.0, length=2, width=0.5)
        ax2.spines['top'].set_visible(False)
        # 量程很窄时用 1 位小数，否则刻度会全部显示成同一个「0pp」
        _rng = float(np.nanmax(ys.values) - np.nanmin(ys.values))
        _d = 1 if _rng < 6 else 0
        ax2.yaxis.set_major_locator(matplotlib.ticker.MaxNLocator(5))
        ax2.yaxis.set_major_formatter(
            lambda t, _: f'{t:.{_d}f}' + ('pp' if pct_series else '%'))
    else:
        ax2.set_axis_off()      # 没有 12 个月历史 → 不画空轴

    if show_mom:
        i = len(v) - 1
        mv = (v[i] - v[i - 1]) if (pct_series and i >= 1) else _mom(v, i)
        if np.isfinite(mv):
            # 气泡放左侧：右侧已经归 y/y 折线与其次轴
            bubble(ax, (0.145, 0.90),
                   (f'{mv:+.1f}pp m/m' if pct_series else _pp(mv) + ' m/m'))

    style_ax(ax)
    month_xticks(ax, d.index)
    if unit:
        ax.set_ylabel(_esc(unit), fontsize=6.0)
    ax.set_ylim(min(0, np.nanmin(d.values) * 1.15), np.nanmax(d.values) * 1.28)
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc='lower left', bbox_to_anchor=(0, 1.01), ncol=2,
              frameon=False, fontsize=6.0, handlelength=1.2, borderaxespad=0)
    _draw_break(ax, d.index, break_at, break_label)
    title(ax, deck.nxt(), ttl)
    src(ax, source, extra)
    return ax


# ────────────────────────────── 图型 2：GS 变化率图 ──────────────────────────────
def chg_line(deck, s_full, ttl, source, *, win=13, kind='mom', dec=1, extra='', unit=''):
    """单条藏青平滑曲线 + 零轴 + 每点数据标签。与 lvl_bar 成对使用。"""
    ax = deck.ax()
    s = _tail_contiguous(s_full)
    v = s.values
    if kind == 'mom':
        ch = np.array([_mom(v, i) for i in range(len(v))]) * 100
        lab, ylab = 'm/m change', unit or '% m/m'
    else:
        ch = np.array([_yoy(v, i) for i in range(len(v))]) * 100
        lab, ylab = 'y/y change', unit or '% y/y'
    ser = pd.Series(ch, index=s.index).iloc[-win:]
    x = np.arange(len(ser))
    ax.plot(x, ser.values, color=NAVY, lw=1.5, marker='o', ms=2.4, zorder=4, label=lab)
    ax.axhline(0, color='#999999', lw=0.7, zorder=2)
    rng = np.nanmax(ser.values) - np.nanmin(ser.values)
    rng = rng if np.isfinite(rng) and rng > 0 else 1
    for i, y in enumerate(ser.values):
        if np.isfinite(y):
            up = y >= 0
            ax.text(i, y + rng * (0.07 if up else -0.07), f'{y:,.{dec}f}%', ha='center',
                    va='bottom' if up else 'top', fontsize=5.2, color='#222222')
    style_ax(ax)
    month_xticks(ax, ser.index)
    ax.set_ylabel(_esc(ylab), fontsize=6.0)
    ax.set_ylim(np.nanmin(ser.values) - rng * 0.34, np.nanmax(ser.values) + rng * 0.34)
    title(ax, deck.nxt(), ttl)
    src(ax, source, extra)
    return ax


# ────────────────────────── 图型 3：堆叠柱 + 次轴占比线 ──────────────────────────
def stack_share(deck, df, cols, colors, share_num, ttl, source, *,
                win=13, dec=1, unit='', share_label='% of total', extra='',
                names=None, bar_labels=True, break_at=None, break_label='basis change'):
    ax = deck.ax()
    d = df.iloc[-win:]
    x = np.arange(len(d))
    bot = np.zeros(len(d))
    names = names or cols
    tot_max = float(np.nanmax(d[cols].sum(axis=1)))
    for c, col, nm in zip(cols, colors, names):
        vals = d[c].fillna(0).values
        ax.bar(x, vals, 0.72, bottom=bot, color=col, zorder=3, label=nm)
        if bar_labels and len(d) <= 16 and len(cols) <= 4:
            lc = 'white' if col in (NAVY, MBLUE, GREEN, RED) else '#333333'
            for i, (v, b) in enumerate(zip(vals, bot)):
                if v > 0 and v / max(1e-9, tot_max) > 0.10:
                    ax.text(i, b + v / 2, _fmt(v, dec), ha='center', va='center',
                            fontsize=4.9, color=lc, zorder=6)
        bot = bot + vals
    ax2 = ax.twinx()
    sh = (d[share_num].sum(axis=1) / d[cols].sum(axis=1) * 100).values
    ax2.plot(x, sh, color=GREEN, lw=1.5, marker='o', ms=2.2, zorder=7, label=share_label)
    for i, y in enumerate(sh):
        if np.isfinite(y) and (len(d) <= 16 or i % 2 == 0):
            ax2.text(i, y, f'{y:.0f}%', ha='center', va='bottom', fontsize=5.0,
                     color=GREEN, zorder=8)
    lo_s, hi_s = float(np.nanmin(sh)), float(np.nanmax(sh))
    pad = max(1.0, (hi_s - lo_s) * 0.45)
    # 占比线压到画布上 1/3，避免与柱体重叠
    ax2.set_ylim(lo_s - pad - (hi_s - lo_s + 2 * pad) * 1.05, hi_s + pad)
    ax.set_ylim(0, tot_max * 1.42)
    ax2.tick_params(labelsize=6.0, length=2, width=0.5)
    ax2.spines['top'].set_visible(False)
    _sdec = 1 if (hi_s - lo_s) < 6 else 0
    ax2.yaxis.set_major_locator(matplotlib.ticker.MaxNLocator(5, prune='lower'))
    ax2.yaxis.set_major_formatter(lambda v, _: f'{v:.{_sdec}f}%')
    style_ax(ax)
    month_xticks(ax, d.index)
    if unit:
        ax.set_ylabel(_esc(unit), fontsize=6.0)
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc='lower left', bbox_to_anchor=(0, 1.01), ncol=4,
              frameon=False, fontsize=5.9, handlelength=1.2, columnspacing=0.8,
              borderaxespad=0)
    _draw_break(ax, d.index, break_at, break_label)
    title(ax, deck.nxt(), ttl)
    src(ax, source, extra)
    return ax


# ────────────────────────────── 图型 4：多序列曲线 ──────────────────────────────
def multi_line(deck, df, cols, colors, ttl, source, *, win=13, dec=2, money='',
               unit='', names=None, extra='', log=False, break_at=None,
               break_label='basis change'):
    ax = deck.ax()
    d = df.iloc[-win:]
    x = np.arange(len(d))
    names = names or cols
    for c, col, nm in zip(cols, colors, names):
        v = d[c].values
        ax.plot(x, v, color=col, lw=1.4, marker='o', ms=2.0, zorder=4, label=nm)
        for i, ha in ((0, 'right'), (len(v) - 1, 'left')):
            if np.isfinite(v[i]):
                pad = ' ' if ha == 'left' else ''
                ax.text(i, v[i], pad + _fmt(v[i], dec, money=money) + ('' if ha == 'left' else ' '),
                        fontsize=5.2, color=col, va='center', ha=ha, zorder=6)
    ax.set_xlim(-1.9, len(d) + 0.9)
    if log:
        ax.set_yscale('log')
    style_ax(ax)
    month_xticks(ax, d.index)
    if unit:
        ax.set_ylabel(_esc(unit), fontsize=6.0)
    legend(ax, min(4, len(cols)))
    _draw_break(ax, d.index, break_at, break_label)
    title(ax, deck.nxt(), ttl)
    src(ax, source, extra)
    return ax


# ─────────────────────── 图型 5：台股月营收（实际 + 预测） ───────────────────────
def rev_bar_yoy(deck, s_full, ttl, source, *, win=20, n_fcst=0, dec=0,
                unit='', extra='', money='', label_div=1.0, label_dec=None,
                break_at=None, break_label='basis change'):
    """深色柱=已公布，浅色柱=预测（末 n_fcst 根），次轴金色 YoY 折线。

    label_div: 柱顶标签的除数（如月营收以 NT$mn 存、想标 NT$bn 就传 1000）。
    """
    ax = deck.ax()
    s = s_full.dropna()
    d = s.iloc[-win:]
    x = np.arange(len(d))
    n_act = len(d) - n_fcst
    cols = [NAVY] * n_act + [BLUE] * n_fcst
    ax.bar(x, d.values, 0.70, color=cols, zorder=3)
    ld = label_dec if label_dec is not None else dec
    for i, v in enumerate(d.values):
        if np.isfinite(v) and (len(d) <= 18 or i % 2 == 0):
            ax.text(i, v * 1.02, _fmt(v / label_div, ld, money=money), ha='center',
                    va='bottom', fontsize=5.0, color='#222222', rotation=90, zorder=6)
    ax2 = ax.twinx()
    v = s.values
    yoy = np.array([_yoy(v, i) for i in range(len(v))]) * 100
    ys = pd.Series(yoy, index=s.index).iloc[-win:]
    ax2.plot(x, ys.values, color=GOLD, lw=1.6, marker='o', ms=2.4, zorder=7)
    if np.isfinite(ys.values[-1]):
        ax2.text(len(d) - 1, ys.values[-1], f' {ys.values[-1]:+.0f}%', fontsize=6.0,
                 color=GOLD, fontweight='bold', va='center')
    ax2.axhline(0, color=GOLD, lw=0.5, ls=':', zorder=2)
    ax2.tick_params(labelsize=6.0, length=2, width=0.5)
    ax2.spines['top'].set_visible(False)
    ax2.yaxis.set_major_formatter(lambda t, _: f'{t:.0f}%')
    style_ax(ax)
    month_xticks(ax, d.index, step=1 if win <= 24 else 2)
    if unit:
        ax.set_ylabel(_esc(unit), fontsize=6.0)
    ax.set_ylim(0, np.nanmax(d.values) * 1.30)
    hs = [Patch(fc=NAVY, label='Reported'), Line2D([], [], color=GOLD, lw=1.6, label='y/y (RHS)')]
    if n_fcst:
        hs.insert(1, Patch(fc=BLUE, label='Forecast'))
    ax.legend(handles=hs, loc='lower left', bbox_to_anchor=(0, 1.01), ncol=3,
              frameon=False, fontsize=6.0, handlelength=1.2, borderaxespad=0)
    title(ax, deck.nxt(), ttl)
    src(ax, source, extra)
    return ax


# ──────────────── 图型 5b：月度 → 季度桥（当季未满月份用浅色标出） ────────────────
def qtr_bar(deck, s_monthly, ttl, source, *, win=13, dec=0, unit='', money='',
            extra='', label_div=1.0, label_dec=None, how='sum'):
    """把月度序列汇总成季度柱 + 次轴金色 YoY 折线。

    当前季度若未满 3 个月，用浅蓝柱标出并在图上注明已含几个月——
    这是台股月营收/交易所成交量「用月度抢跑季报」的核心图。
    """
    ax = deck.ax()
    s = s_monthly.dropna()
    q = s.groupby(s.index.asfreq('Q')).agg(['sum', 'mean', 'count'])
    vals = q['sum'] if how == 'sum' else q['mean']
    n_in_last = int(q['count'].iloc[-1])
    partial = n_in_last < 3
    d = vals.iloc[-win:]
    x = np.arange(len(d))
    cols = [NAVY] * len(d)
    if partial:
        cols[-1] = BLUE
    ax.bar(x, d.values, 0.70, color=cols, zorder=3)
    ld = label_dec if label_dec is not None else dec
    for i, v in enumerate(d.values):
        ax.text(i, v * 1.02, _fmt(v / label_div, ld, money=money), ha='center',
                va='bottom', fontsize=5.2, color='#222222', rotation=90, zorder=6)
    yv = vals.values
    yoy = np.array([(yv[i] / yv[i - 4] - 1) * 100 if i >= 4 and yv[i - 4] else np.nan
                    for i in range(len(yv))])
    ys = pd.Series(yoy, index=vals.index).iloc[-win:]
    ax2 = ax.twinx()
    ax2.plot(x, ys.values, color=GOLD, lw=1.6, marker='o', ms=2.4, zorder=7)
    if np.isfinite(ys.values[-1]):
        ax2.text(len(d) - 1, ys.values[-1], f' {ys.values[-1]:+.0f}%', fontsize=6.0,
                 color=GOLD, fontweight='bold', va='center')
    ax2.axhline(0, color=GOLD, lw=0.5, ls=':', zorder=2)
    ax2.tick_params(labelsize=6.0, length=2, width=0.5)
    ax2.spines['top'].set_visible(False)
    ax2.yaxis.set_major_formatter(lambda t, _: f'{t:.0f}%')
    style_ax(ax)
    ax.set_xticks(x)
    ax.set_xticklabels([str(p) for p in d.index], rotation=90, fontsize=5.5)
    if unit:
        ax.set_ylabel(_esc(unit), fontsize=6.0)
    ax.set_ylim(0, np.nanmax(d.values) * 1.32)
    hs = [Patch(fc=NAVY, label='Complete quarter'),
          Line2D([], [], color=GOLD, lw=1.6, label='y/y (RHS)')]
    if partial:
        hs.insert(1, Patch(fc=BLUE, label=f'QTD ({n_in_last} of 3 months)'))
    ax.legend(handles=hs, loc='lower left', bbox_to_anchor=(0, 1.01), ncol=3,
              frameon=False, fontsize=5.9, handlelength=1.2, borderaxespad=0)
    title(ax, deck.nxt(), ttl)
    src(ax, source, extra or ('Latest bar is quarter-to-date and not comparable to full quarters'
                              if partial else ''))
    return ax


# ─────────────────── 图型 6：JPM 季节性配对柱（灰=历史同月均值） ───────────────────
def seasonality(deck, s_full, ttl, source, *, win=13, years=10, dec=1,
                unit='', extra='', money='', pct=False):
    """灰柱 = 过去 N 年同一日历月的均值；蓝柱 = 当期实际。剥离季节性。"""
    ax = deck.ax()
    s = s_full.dropna()
    d = s.iloc[-win:]
    base = []
    used_years = []
    for p in d.index:
        prior = [s.get(p - 12 * k, np.nan) for k in range(1, years + 1)]
        prior = [v for v in prior if v is not None and np.isfinite(v)]
        used_years.append(len(prior))
        base.append(np.mean(prior) if prior else np.nan)
    base = np.array(base)
    x = np.arange(len(d))
    ax.bar(x - 0.20, base, 0.40, color=GRAY, zorder=3,
           label=f'Prior {max(used_years)}yr same-month avg.')
    ax.bar(x + 0.20, d.values, 0.40, color=MBLUE, zorder=3, label='Actual')
    rng = np.nanmax(np.concatenate([base[np.isfinite(base)], d.values])) or 1
    for i, v in enumerate(d.values):
        if np.isfinite(v):
            ax.text(i + 0.20, v + rng * 0.02, _fmt(v, dec, pct, money), ha='center',
                    va='bottom', fontsize=5.0, color=MBLUE)
    style_ax(ax)
    month_xticks(ax, d.index)
    if unit:
        ax.set_ylabel(_esc(unit), fontsize=6.0)
    ax.set_ylim(0, rng * 1.26)
    legend(ax, 2)
    title(ax, deck.nxt(), ttl)
    src(ax, source, extra or f'Grey bar = mean of the same calendar month over the prior {max(used_years)} years')
    return ax


# ──────────────────── 图型 7：JPM 逐日历月箱线图 + 当年/去年标记 ────────────────────
def month_box(deck, s_full, ttl, source, *, dec=1, unit='', extra='', pct=False):
    ax = deck.ax()
    s = s_full.dropna()
    yrs = sorted({p.year for p in s.index})
    cur, prev = yrs[-1], yrs[-2] if len(yrs) > 1 else yrs[-1]
    data, cur_pts, prv_pts = [], [], []
    for m in range(1, 13):
        vals = [v for p, v in s.items() if p.month == m and p.year not in (cur,)]
        data.append(vals if vals else [np.nan])
        cv = [v for p, v in s.items() if p.month == m and p.year == cur]
        pv = [v for p, v in s.items() if p.month == m and p.year == prev]
        cur_pts.append(cv[0] if cv else np.nan)
        prv_pts.append(pv[0] if pv else np.nan)
    bp = ax.boxplot(data, positions=range(1, 13), widths=0.55, patch_artist=True,
                    showfliers=False, zorder=3)
    for b in bp['boxes']:
        b.set(facecolor='#EDF2F8', edgecolor=GRAY, lw=0.7)
    for k in ('whiskers', 'caps'):
        for w in bp[k]:
            w.set(color=GRAY, lw=0.7)
    for md in bp['medians']:
        md.set(color=NAVY, lw=1.1)
    ax.plot(range(1, 13), prv_pts, ls='none', marker='x', ms=4.2, mew=1.2,
            color=GRAY, zorder=6, label=f'{prev}')
    ax.plot(range(1, 13), cur_pts, ls='none', marker='x', ms=5.2, mew=1.6,
            color=RED, zorder=7, label=f'{cur}')
    ax.set_xticks(range(1, 13))
    ax.set_xticklabels(['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug',
                        'Sep', 'Oct', 'Nov', 'Dec'], fontsize=5.6)
    style_ax(ax)
    if unit:
        ax.set_ylabel(_esc(unit), fontsize=6.0)
    legend(ax, 2)
    title(ax, deck.nxt(), ttl)
    lo, hi = min(yrs), max(yrs)
    src(ax, source, extra or f'Box = distribution across {lo}-{hi} ex. {cur}; whiskers = min/max')
    return ax


# ───────────────────────── 图型 8：月 x 年热力矩阵 ─────────────────────────
def heat_matrix(deck, s_full, ttl, source, *, dec=1, n_years=8, extra='',
                cmap='RdYlGn', reverse=False, pct=False):
    ax = deck.ax(full_width=True, h_scale=0.92)
    s = s_full.dropna()
    yrs = sorted({p.year for p in s.index})[-n_years:]
    M = np.full((len(yrs), 12), np.nan)
    for p, v in s.items():
        if p.year in yrs:
            M[yrs.index(p.year), p.month - 1] = v
    cm = plt.get_cmap(cmap + ('_r' if reverse else ''))
    fin = M[np.isfinite(M)]
    vmin, vmax = (np.percentile(fin, 5), np.percentile(fin, 95)) if fin.size else (0, 1)
    ax.imshow(M, aspect='auto', cmap=cm, vmin=vmin, vmax=vmax, zorder=2)
    for i in range(len(yrs)):
        for j in range(12):
            if np.isfinite(M[i, j]):
                ax.text(j, i, _fmt(M[i, j], dec, pct), ha='center', va='center',
                        fontsize=5.4, color='#111111', zorder=3)
    ax.set_xticks(range(12))
    ax.set_xticklabels(['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug',
                        'Sep', 'Oct', 'Nov', 'Dec'], fontsize=6.0)
    ax.set_yticks(range(len(yrs)))
    ax.set_yticklabels([str(y) for y in yrs], fontsize=6.0)
    ax.tick_params(length=0)
    for sp in ax.spines.values():
        sp.set_visible(False)
    ax.set_xticks(np.arange(-.5, 12, 1), minor=True)
    ax.set_yticks(np.arange(-.5, len(yrs), 1), minor=True)
    ax.grid(which='minor', color='white', lw=1.1)
    ax.tick_params(which='minor', length=0)
    title(ax, deck.nxt(), ttl)
    src(ax, source, extra or 'Colour scale runs green(high) to red(low) within each metric')
    return ax


# ──────────── 图型 1b：本月异常度面板（z-score，横向条） ────────────
def zscore_panel(deck, df, rows, ttl, source, *, lookback=36, extra='', h_scale=1.0):
    """一屏回答「这个月哪些指标不正常」—— 同时给出两个基准，因为它们会分歧。

    rows: [(label, col, basis, invert)]
      basis='yoy'   量/增速类 —— 取本月同比
      basis='level' 比率类（逾期率、占比，均值回复）—— 直接用水平值
    invert=True 表示下降为好（信用类），着色反向。

    ■ 柱子 = 相对过去 lookback 期**分布**的 z（读数 - 均值）/ 标准差
    ◆ 菱形 = 相对过去 lookback 期**趋势线**的 z（读数 - 趋势外推值）/ 残差标准差

    为什么要两个：高增长标的的同比本身在爬坡，窗口均值被旧数据拖低，
    单看柱子会把「趋势照常延续」误报成「异常」。两者背离本身就是结论。
    比率类不做去趋势 —— 那类指标本来就均值回复，外推趋势是错的。

    ⚠️ 这里的同比是**单月**同比（`pct_change(12)`，本月 ÷ 去年同月，CONTRACT §6.1
    第 1 条）。它的相邻两期**不共享任何月份**（第 i 期取 i 与 i−12，第 i+1 期取
    i+1 与 i−11）—— 会共享 11 个月的是 12 个月滚动合计的同比，而本仓一条都不画，
    别把那套说法套到这条线上。**但不重叠不等于独立**：水平序列本身有持续性，
    一轮行情会连着几个月同向偏离去年同期，同比读数照样高度自相关
    （实测本仓 624 条月度序列的单月同比，一阶自相关中位 0.72、四分位 0.53–0.89）。
    所以有效样本量仍然远小于 lookback。图注里标的那个有效样本是拿**本窗口实测的**
    一阶自相关折算的，不是写死的经验值；σ 只能当粗略刻度。
    """
    ax = deck.ax(full_width=True, h_scale=h_scale)
    bb = ax.get_position()
    ax.set_position([bb.x0 + 0.185, bb.y0, bb.width - 0.195, bb.height])

    labs, zs, zt, cur, cols, neffs, dropped = [], [], [], [], [], [], []
    for lab, col, basis, inv in rows:
        s_ = df[col].dropna()
        if basis == 'yoy':
            v = s_.pct_change(12).dropna() * 100
            unit = '% y/y'
        else:
            v = s_
            unit = 'level'
        if len(v) < 12:
            continue
        hist = v.iloc[-(lookback + 1):-1]
        sd = hist.std(ddof=1)
        if len(hist) < 8 or not np.isfinite(sd) or sd == 0:
            # 样本太少时 sigma 没有统计意义 —— 宁可不画，也不给一个假精度的数
            dropped.append(f'{lab} ({len(hist)} readings)')
            continue
        z = (v.iloc[-1] - hist.mean()) / sd
        if not np.isfinite(z):
            continue
        # 去趋势 z：对窗口内读数拟合线性趋势，与外推值比
        zz = np.nan
        if basis == 'yoy' and len(hist) >= 12:
            t = np.arange(len(hist))
            b1, b0 = np.polyfit(t, hist.values, 1)
            resid = hist.values - (b0 + b1 * t)
            rsd = resid.std(ddof=1)
            if np.isfinite(rsd) and rsd > 0:
                zz = (v.iloc[-1] - (b0 + b1 * len(hist))) / rsd
        ar1 = pd.Series(hist.values).autocorr(1)
        if np.isfinite(ar1) and ar1 < 1:
            neffs.append(min(len(hist), len(hist) * (1 - ar1) / (1 + ar1)))
        labs.append(f'{lab}  ({unit})')
        zs.append(z); zt.append(zz); cur.append(v.iloc[-1])
        good = (z < 0) if inv else (z > 0)
        cols.append(GREEN if good else RED)

    y = np.arange(len(labs))[::-1]
    ax.barh(y, zs, 0.58, color=cols, zorder=3, label='vs 3-year distribution')
    fin = [i for i, q in enumerate(zt) if np.isfinite(q)]
    if fin:
        ax.plot([zt[i] for i in fin], [y[i] for i in fin], ls='none', marker='D',
                ms=3.6, mfc='white', mec=NAVY, mew=1.2, zorder=8,
                label='vs 3-year trend')
    for i, (yy, z, c) in enumerate(zip(y, zs, cur)):
        parts = f'{z:+.1f}'
        if np.isfinite(zt[i]):
            parts += f' / {zt[i]:+.1f}'
        anchor = max(z, zt[i]) if np.isfinite(zt[i]) else z
        anchor_lo = min(z, zt[i]) if np.isfinite(zt[i]) else z
        if z >= 0:
            ax.text(anchor + 0.10, yy, f'{parts}\u03c3   ({c:,.1f})', va='center',
                    ha='left', fontsize=6.0, color='#222222')
        else:
            ax.text(anchor_lo - 0.10, yy, f'{parts}\u03c3   ({c:,.1f})', va='center',
                    ha='right', fontsize=6.0, color='#222222')
    for xv, st in ((0, '-'), (1, (0, (3, 2))), (-1, (0, (3, 2))), (2, (0, (1, 2))), (-2, (0, (1, 2)))):
        ax.axvline(xv, color='#999999' if xv == 0 else LGRAY, lw=0.8 if xv == 0 else 0.7,
                   ls=st, zorder=2)
    ax.set_yticks(y)
    ax.set_yticklabels(labs, fontsize=6.3)
    ax.tick_params(length=0)
    allz = [q for q in list(zs) + list(zt) if np.isfinite(q)]
    lim = max(2.6, np.nanmax(np.abs(allz)) * 1.55) if allz else 3
    ax.set_xlim(-lim, lim)
    ax.set_xlabel('standard deviations', fontsize=6.2)
    ax.grid(axis='x', color=GRID, lw=0.6, zorder=0)
    ax.set_axisbelow(True)
    for sp in ('top', 'right', 'left'):
        ax.spines[sp].set_visible(False)
    ax.legend(loc='lower left', bbox_to_anchor=(0, 1.01), ncol=2, frameon=False,
              fontsize=6.0, handlelength=1.3, borderaxespad=0)
    title(ax, deck.nxt(), ttl)
    ne = f'{min(neffs):.0f}-{max(neffs):.0f}' if neffs else 'n/a'
    note = (f'Bar: (latest - mean of the prior {lookback} months) / their standard deviation. '
            f'Diamond: the same reading against the trailing TREND line — when growth is itself '
            f'accelerating the flat mean sits too low and the bar overstates. Divergence between '
            f'the two means trend continuation, not news. Rates use the level, no trend line. '
            f'y/y is single-month (this month vs the same month a year ago); consecutive '
            f'readings share no months, but the level series is persistent so they are still '
            f'autocorrelated — effective sample only {ne}.')
    if extra:
        note += '  ' + extra
    elif dropped:
        note += '  Excluded for too little history: ' + '; '.join(dropped) + '.'
    src(ax, source, note)
    return ax


# ──────── 图型 7b：恒等式滚存桥（正负分向堆叠 + 净额标记） ────────
def bridge_bar(deck, df, cols, colors, names, ttl, source, *, win=13, dec=1,
               money='', unit='', extra='', net_label='Net change'):
    """把「期末 - 期初」拆成若干贡献项：正值向上堆、负值向下堆，黑点标净额。

    来源：GS「SCHW First Take」Exhibit 2 的恒等式滚存块
    （期初 BOP + 净流入 + 市值变动 = 期末 EOP）——它让月度数据可无损累加到季度。
    """
    ax = deck.ax()
    d = df.iloc[-win:]
    x = np.arange(len(d))
    pos = np.zeros(len(d))
    neg = np.zeros(len(d))
    for c, col, nm in zip(cols, colors, names):
        v = d[c].fillna(0).values.astype(float)
        bot = np.where(v >= 0, pos, neg)
        ax.bar(x, v, 0.70, bottom=bot, color=col, zorder=3, label=nm)
        pos = pos + np.where(v >= 0, v, 0)
        neg = neg + np.where(v < 0, v, 0)
    net = d[cols].fillna(0).sum(axis=1).values
    ax.plot(x, net, ls='none', marker='D', ms=3.0, color='#111111', zorder=8,
            label=net_label)
    ax.axhline(0, color='#666666', lw=0.7, zorder=2)
    style_ax(ax)
    month_xticks(ax, d.index)
    if unit:
        ax.set_ylabel(_esc(unit), fontsize=6.0)
    lo, hi = float(np.nanmin(neg)), float(np.nanmax(pos))
    pad = (hi - lo) * 0.16 or 1
    ax.set_ylim(lo - pad, hi + pad)
    legend(ax, min(4, len(cols) + 1))
    title(ax, deck.nxt(), ttl)
    src(ax, source, extra)
    return ax


# ──────────── 图型 5d：桥的验证图（季度隐含 vs 实际） ────────────
def implied_vs_actual(deck, implied_q, actual_q, ttl, source, *, dec=0, money='',
                      unit='', extra='', win=14):
    """把桥算出来的季度隐含值与公司披露的实际值并排画，并在下方标出误差。

    这张图是「假设可不可信」的唯一凭据 —— 误差大就说明费率假设不成立，
    不能只在图注里写一句「这是假设」就当交代过去了。
    """
    ax = deck.ax()
    idx = [q for q in implied_q.index if q in actual_q.index][-win:]
    imp = np.array([implied_q[q] for q in idx], float)
    act = np.array([actual_q[q] for q in idx], float)
    x = np.arange(len(idx))
    ax.bar(x - 0.19, imp, 0.36, color=BLUE, zorder=3, label='Implied by the bridge')
    ax.bar(x + 0.19, act, 0.36, color=NAVY, zorder=3, label='Actually reported')
    err = np.where(act != 0, (imp / act - 1) * 100, np.nan)
    ax2 = ax.twinx()
    ax2.plot(x, err, color=RED, lw=1.2, marker='o', ms=2.4, zorder=7, label='Error (RHS)')
    ax2.axhline(0, color=RED, lw=0.5, ls=':', zorder=2)
    lim = max(6.0, np.nanmax(np.abs(err)) * 1.9) if np.isfinite(err).any() else 6
    ax2.set_ylim(-lim, lim)
    ax2.tick_params(labelsize=6.0, length=2, width=0.5)
    ax2.spines['top'].set_visible(False)
    ax2.yaxis.set_major_formatter(lambda t, _: f'{t:.0f}%')
    if np.isfinite(err).any():
        j = np.where(np.isfinite(err))[0][-1]
        ax2.annotate(f'{err[j]:+.1f}%', xy=(j, err[j]), xytext=(5, -7),
                     textcoords='offset points', fontsize=6.2, color=RED,
                     fontweight='bold', annotation_clip=False)
    style_ax(ax)
    ax.set_xticks(x)
    ax.set_xticklabels([str(q) for q in idx], rotation=90, fontsize=5.5)
    if unit:
        ax.set_ylabel(_esc(unit), fontsize=6.0)
    ax.set_ylim(0, max(np.nanmax(imp), np.nanmax(act)) * 1.22)
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc='lower left', bbox_to_anchor=(0, 1.01), ncol=3,
              frameon=False, fontsize=5.9, handlelength=1.2, borderaxespad=0)
    title(ax, deck.nxt(), ttl)
    mae = np.nanmean(np.abs(err)) if np.isfinite(err).any() else np.nan
    src(ax, source, extra + (f'  Mean absolute error over the window: {mae:.1f}%.'
                             if np.isfinite(mae) else ''))
    return ax


# ──────────── 图型 5c：指引区间 vs 实际（季度） ────────────
def range_vs_actual(deck, idx, lo, hi, actual, ttl, source, *, dec=1, money='',
                    unit='', extra='', qtd=None, qtd_label='quarter-to-date'):
    """公司给的区间画成浮动柱，实际值用菱形标在上面。

    用于「季度营收指引 vs 实际」这类问题：一眼看出公司指引偏保守还是激进。
    qtd: 可选，当前未完成季度的累计值，用空心菱形标出并注明是进行中。
    """
    ax = deck.ax()
    x = np.arange(len(idx))
    lo = np.asarray(lo, float); hi = np.asarray(hi, float)
    act = np.asarray(actual, float)
    ax.bar(x, hi - lo, 0.74, bottom=lo, color=BLUE, zorder=3, label='Guidance range')
    for i in range(len(idx)):
        if np.isfinite(lo[i]) and np.isfinite(hi[i]):
            ax.plot([i - 0.32, i + 0.32], [lo[i]] * 2, color=MBLUE, lw=0.8, zorder=4)
            ax.plot([i - 0.32, i + 0.32], [hi[i]] * 2, color=MBLUE, lw=0.8, zorder=4)
    fin = np.isfinite(act)
    ax.plot(x[fin], act[fin], ls='none', marker='D', ms=3.2, color=NAVY, zorder=7,
            label='Actual')
    for i in np.where(fin)[0]:
        ax.annotate(_fmt(act[i], dec, money=money), xy=(i, act[i]), xytext=(0, 6),
                    textcoords='offset points', ha='center', fontsize=5.4, color=NAVY)
    if qtd is not None and np.isfinite(qtd):
        j = len(idx) - 1
        ax.plot([j], [qtd], ls='none', marker='D', ms=4.4, mfc='white', mec=RED,
                mew=1.4, zorder=8, label=qtd_label)
        ax.annotate(_fmt(qtd, dec, money=money), xy=(j, qtd), xytext=(0, -10),
                    textcoords='offset points', ha='center', fontsize=5.6,
                    color=RED, fontweight='bold')
    style_ax(ax)
    ax.set_xticks(x)
    ax.set_xticklabels([str(p) for p in idx], rotation=90, fontsize=5.5)
    if unit:
        ax.set_ylabel(_esc(unit), fontsize=6.0)
    good = np.concatenate([lo[np.isfinite(lo)], hi[np.isfinite(hi)], act[fin]])
    ax.set_ylim(np.nanmin(good) * 0.88, np.nanmax(good) * 1.10)
    legend(ax, 3)
    title(ax, deck.nxt(), ttl)
    src(ax, source, extra)
    return ax


# ──────────── 图型 8c：跨公司指数化折线（同一起点 = 100） ────────────
def indexed_lines(deck, series_map, ttl, source, *, base=None, colors=None,
                  extra='', unit='index, base = 100', start=None, log=False):
    """把单位不同的几家公司放到同一张图上比增速：各自在 base 月归 100。

    series_map: {'公司名': Series}
    base: 归一化的基准月；省略则取所有序列都有数据的最早月份。
    """
    ax = deck.ax()
    cleaned = {k: v.dropna() for k, v in series_map.items()}
    cleaned = {k: v for k, v in cleaned.items() if len(v)}
    if start:
        cleaned = {k: v.loc[pd.Period(start, 'M'):] for k, v in cleaned.items()}
    if base is None:
        base = max(v.index[0] for v in cleaned.values())
    else:
        base = pd.Period(base, 'M')
    cols = colors or [NAVY, RED, MBLUE, GREEN, GOLD, GRAY]
    allidx = sorted(set().union(*[set(v.index) for v in cleaned.values()]))
    allidx = [p for p in allidx if p >= base]
    xs = {p: i for i, p in enumerate(allidx)}
    ends = []
    for (name, v), c in zip(cleaned.items(), cols):
        if base not in v.index:
            continue
        iv = v.loc[base:] / v.loc[base] * 100
        x = [xs[p] for p in iv.index if p in xs]
        y = [iv[p] for p in iv.index if p in xs]
        ax.plot(x, y, color=c, lw=1.5, zorder=4, label=name)
        if y:
            ends.append([y[-1], x[-1], c])
    # 末端标签：值接近时上下错开，避免叠字
    ends.sort(key=lambda e: e[0])
    span = (max(e[0] for e in ends) - min(e[0] for e in ends)) if len(ends) > 1 else 1
    minsep = max(span * 0.075, 1e-9)
    for i in range(1, len(ends)):
        if ends[i][0] - ends[i - 1][0] < minsep:
            ends[i][0] = ends[i - 1][0] + minsep
    for (yv, xv, c), (orig, _, _) in zip(ends, sorted(
            [[v.loc[base:].iloc[-1] / v.loc[base] * 100, 0, 0] for v in cleaned.values()
             if base in v.index], key=lambda e: e[0])):
        ax.annotate(f'{orig:,.0f}', xy=(xv, yv), xytext=(4, 0), textcoords='offset points',
                    fontsize=6.2, color=c, fontweight='bold', va='center',
                    annotation_clip=False)
    ax.axhline(100, color='#999999', lw=0.7, ls=(0, (3, 2)), zorder=2)
    if log:
        ax.set_yscale('log')
    style_ax(ax)
    step = max(1, len(allidx) // 12)
    ax.set_xticks(range(0, len(allidx), step))
    ax.set_xticklabels([mlab(p) for p in allidx[::step]], rotation=90, fontsize=5.5)
    ax.set_xlim(-0.5, len(allidx) + 2.5)
    ax.set_ylabel(unit, fontsize=6.0)
    legend(ax, min(4, len(cleaned)))
    title(ax, deck.nxt(), ttl)
    src(ax, source, extra or f'Each series rebased to 100 at {mlab(base)}; compares growth, not absolute size')
    return ax


# ──────────── 图型 8b：逐年同期对照（Jan..Dec 一年一条线，当年加粗） ────────────
def year_lines(deck, s_monthly, ttl, source, *, n_years=6, cumulative=True,
               dec=0, money='', unit='', extra=''):
    """把序列按年份拆成多条线叠在 Jan–Dec 轴上，当年用红色加粗。

    cumulative=True 时画年初至今累计（判断「今年跑得比往年快多少」）。
    """
    ax = deck.ax()
    s = s_monthly.dropna()
    yrs = sorted({p.year for p in s.index})[-n_years:]
    cmap = [LGRAY, '#C9D6E4', BLUE, MBLUE, NAVY]
    for k, y in enumerate(yrs):
        sub = s[[p.year == y for p in s.index]]
        if sub.empty:
            continue
        months = [p.month for p in sub.index]
        vals = sub.cumsum().values if cumulative else sub.values
        cur = (y == yrs[-1])
        col = RED if cur else cmap[min(k, len(cmap) - 1)]
        ax.plot(months, vals, color=col, lw=1.9 if cur else 1.1,
                marker='o' if cur else None, ms=2.4, zorder=6 if cur else 4, label=str(y))
        if cur:
            ax.text(months[-1], vals[-1], ' ' + _fmt(vals[-1], dec, money=money),
                    fontsize=6.0, color=RED, fontweight='bold', va='center')
    ax.set_xticks(range(1, 13))
    ax.set_xticklabels(['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug',
                        'Sep', 'Oct', 'Nov', 'Dec'], fontsize=5.8)
    style_ax(ax)
    if unit:
        ax.set_ylabel(_esc(unit), fontsize=6.0)
    legend(ax, min(6, len(yrs)))
    title(ax, deck.nxt(), ttl)
    src(ax, source, extra or ('Cumulative from January of each year; red = current year'
                              if cumulative else 'Red = current year'))
    return ax


# ───────────────────── 图型 9：GS HKEX 式超长历史折线 ─────────────────────
def long_line(deck, s_full, ttl, source, *, dec=0, unit='', money='', extra='',
              n_label=4, circle=3, start=None, break_at=None, break_label='basis change',
              clip_at=None, clip_note=''):
    ax = deck.ax()
    s = s_full.dropna()
    if start:
        s = s.loc[pd.Period(start, 'M'):]
    x = np.arange(len(s))
    ax.plot(x, s.values, color=NAVY, lw=1.1, zorder=4)
    ax.fill_between(x, 0, s.values, color=NAVY, alpha=0.06, zorder=2)
    rngy = float(np.nanmax(s.values) - np.nanmin(s.values)) or 1.0
    # 末端只标最新一点（长序列上多标必叠字），并把标签抬到点上方
    if n_label:
        i = len(s) - 1
        ax.annotate(_fmt(s.values[i], dec, money=money),
                    xy=(i, s.values[i]), xytext=(-6, 12), textcoords='offset points',
                    fontsize=6.0, fontweight='bold', ha='right', color=NAVY, zorder=12)
    _circle_args = (x[-circle:], s.values[-circle:]) if circle else None
    style_ax(ax)
    step = max(1, len(s) // 14)
    ax.set_xticks(range(0, len(s), step))
    ax.set_xticklabels([mlab(p) for p in s.index[::step]], rotation=90, fontsize=5.4)
    if unit:
        ax.set_ylabel(_esc(unit), fontsize=6.0)
    if clip_at is not None:
        # 一次性离群值（并购并表等）会把整条线压平。截轴而不是删点：
        # 数值仍然标在图上，只是不让它主导纵轴。
        ax.set_ylim(0, clip_at * 1.16)
        over = [(i, vv, s.index[i]) for i, vv in enumerate(s.values)
                if np.isfinite(vv) and vv > clip_at]
        for i, vv, per in over:
            ax.plot([i, i], [clip_at * 0.96, clip_at * 1.10], color=RED, lw=1.1, zorder=9)
            ax.annotate(f'{_fmt(vv, dec, money=money)}\n{mlab(per)}', xy=(i, clip_at * 1.10),
                        xytext=(4, -2), textcoords='offset points', fontsize=5.4,
                        color=RED, fontweight='bold', va='top', ha='left', zorder=10,
                        annotation_clip=False)
        if over:
            ax.text(0.0, 1.02, 'axis capped — outlier shown in red',
                    transform=ax.transAxes, ha='left', va='bottom', fontsize=5.4,
                    color=RED, style='italic')
    else:
        ax.set_ylim(0, np.nanmax(s.values) * 1.16)
    if _circle_args is not None:
        # 圈高按最终纵轴范围算 —— 若按序列极差算，被截掉的离群值会把圈撑到画布外
        _lo, _hi = ax.get_ylim()
        _xs, _ys = _circle_args
        ax.add_patch(Ellipse((_xs.mean(), np.nanmean(_ys)),
                             max(circle * 2.4, len(s) * 0.035),
                             (_hi - _lo) * 0.16, facecolor='none', edgecolor=RED, lw=1.0,
                             ls=(0, (3, 2)), zorder=10, clip_on=False))
    _draw_break(ax, s.index, break_at, break_label)
    title(ax, deck.nxt(), ttl)
    src(ax, source, extra)
    return ax


# ──────────────────── Exhibit 1：GS 汇总表（本月 vs 上月/去年同月/近 3 年分位） ────────────────────
def summary_table(deck, df, rows, ttl, source, *, extra='', h_scale=1.0):
    """rows: [(group|None, label, col, dec, pct, money, invert)]
    group 为 str 时插入一条板块分隔条；invert=True 表示该指标下降为好（着色反转）。
    列：本月 | 上月 | 去年同月 ‖ m/m | y/y | 3Y %ile

    GS 原件的「12M Avg.」与「vs 12M Avg.」两列**这里没有**，理由写在下面 heads 那行
    旁边。`y/y` 是**单月**口径（本月 ÷ 去年同月，跨 12 期取值），不是 12 个月滚动
    合计之比 —— 表上一列滚动量都没有。
    """
    ax = deck.ax(full_width=True, h_scale=h_scale)
    ax.axis('off')
    idx = df.index
    cur = idx[-1]
    prv = cur - 1
    yag = cur - 12
    # 去掉「12M 均值」与「vs 12M」：滚动均值只是把序列再平滑一遍，不带新信息。
    # 换成「近 3 年分位」—— 直接回答「这个读数在自己的历史里有多极端」。
    heads = [mlab(cur), mlab(prv), mlab(yag), 'm/m', 'y/y', '3Y %ile']
    ncol = len(heads) + 1
    body = []
    for r in rows:
        if r[0] is not None and r[1] is None:
            body.append(('GROUP', r[0]))
            continue
        _, lab, col, dec, pct, money, inv = r[:7]
        mode = r[7] if len(r) > 7 else ('pp' if pct else 'ratio')
        s = df[col].dropna()
        def g(p):
            return s.get(p, np.nan) if p in s.index else np.nan
        c, p1, p12 = g(cur), g(prv), g(yag)
        hist = s.iloc[-36:]
        pctile = (float((hist < c).sum()) / max(1, len(hist) - 1) * 100
                  if np.isfinite(c) and len(hist) >= 8 else np.nan)
        def d(a, b, _ignored, _mode=None):
            _mode = _mode or mode
            if not (np.isfinite(a) and np.isfinite(b)):
                return np.nan
            if _mode in ('pp', 'abs'):
                return a - b
            # 比率模式：分母接近 0 或两期异号时，百分比变化无意义
            if b == 0 or (a * b) < 0:
                return np.nan
            return (a / b - 1) * 100
        body.append(('ROW', lab,
                     _fmt(c, dec, pct, money), _fmt(p1, dec, pct, money),
                     _fmt(p12, dec, pct, money),
                     d(c, p1, pct), d(c, p12, pct), pctile, mode, inv, money, dec))
    nrow = len(body) + 1
    ax.set_xlim(0, ncol)
    ax.set_ylim(0, nrow)
    ax.invert_yaxis()
    W = [2.55] + [1] * 6
    xs = np.cumsum([0] + W)
    xs = xs / xs[-1] * ncol
    # 表头
    ax.add_patch(plt.Rectangle((0, 0), ncol, 1, facecolor=NAVY, zorder=2))
    for j, h in enumerate(heads):
        ax.text((xs[j + 1] + xs[j + 2]) / 2 if False else (xs[j + 1] + xs[j + 2]) / 2,
                0.5, h, ha='center', va='center', fontsize=6.4, color='white',
                fontstyle='italic', zorder=3)
    ax.text(xs[0] + 0.08, 0.5, '', ha='left', va='center', fontsize=6.4, color='white', zorder=3)
    y = 1
    for b in body:
        if b[0] == 'GROUP':
            ax.add_patch(plt.Rectangle((0, y), ncol, 1, facecolor=MBLUE, zorder=2))
            ax.text(xs[0] + 0.08, y + 0.5, b[1], ha='left', va='center', fontsize=6.3,
                    color='white', fontweight='bold', zorder=3)
            y += 1
            continue
        _, lab, c, p1, p12, dm, dy, pctile, mode, inv, money, dec = b
        if int(y) % 2 == 0:
            ax.add_patch(plt.Rectangle((0, y), ncol, 1, facecolor='#F5F8FB', zorder=1))
        ax.text(xs[0] + 0.08, y + 0.5, lab, ha='left', va='center', fontsize=6.2, zorder=3)
        for j, v in enumerate([c, p1, p12]):
            ax.text((xs[j + 1] + xs[j + 2]) / 2, y + 0.5, v, ha='center', va='center',
                    fontsize=6.2, zorder=3,
                    fontweight='bold' if j == 0 else 'normal')
        for k, v in enumerate([dm, dy]):
            if np.isfinite(v):
                good = (v < 0) if inv else (v > 0)
                col = GREEN if good else RED
                if mode == 'pp':
                    txt = f'{v*100:+.0f}bp' if abs(v) < 1 else f'{v:+.2f}pp'
                elif mode == 'abs':
                    txt = money + f'{v:+,.{max(0, dec)}f}'
                else:
                    txt = f'{v:+.1f}%'
            else:
                col, txt = '#333333', ''
            ax.text((xs[k + 4] + xs[k + 5]) / 2, y + 0.5, txt, ha='center', va='center',
                    fontsize=6.2, color=col, zorder=3)
        # 近 3 年分位
        if np.isfinite(pctile):
            pv = (100 - pctile) if inv else pctile
            pc = GREEN if pv >= 66 else (RED if pv <= 33 else '#333333')
            ax.text((xs[6] + xs[7]) / 2, y + 0.5, f'{pctile:.0f}', ha='center',
                    va='center', fontsize=6.2, color=pc, zorder=3)
        y += 1
    for yy in range(nrow + 1):
        ax.plot([0, ncol], [yy, yy], color='#E8E8E8', lw=0.4, zorder=4)
    ax.plot([0, ncol], [0, 0], color=NAVY, lw=0.9, zorder=5)
    ax.plot([0, ncol], [nrow, nrow], color=NAVY, lw=0.9, zorder=5)
    ax.plot([xs[4], xs[4]], [0, nrow], color='#BBBBBB', lw=0.7, zorder=5)
    ax.text(0, -0.55, f'Exhibit {deck.nxt()}: {ttl}', fontsize=8.0, fontweight='bold',
            va='bottom', transform=ax.transData)
    import textwrap as _tw
    _sl = []
    for chunk in ([source] + ([extra] if extra else [])):
        _sl += _tw.wrap(chunk, 175) or ['']
    ax.text(0, nrow + 0.75, _esc('\n'.join(_sl)), fontsize=5.7, color='#333333',
            va='top', transform=ax.transData, linespacing=1.35)
    return ax


# ────────────────────────────── 出片 ──────────────────────────────
def build(path, title_txt, subtitle, footer, fn, start_ex=1):
    """fn(deck) 里按顺序调用各图型；返回写出的文件路径。"""
    from matplotlib.backends.backend_pdf import PdfPages
    tmp = path + '.tmp'
    with PdfPages(tmp) as pdf:
        deck = Deck(pdf, title_txt, subtitle, footer, start_ex=start_ex)
        fn(deck)
        deck.flush()
    os.replace(tmp, path)
    return path


def today():
    return _dt.date.today().strftime('%-d %b %Y')
