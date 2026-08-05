# -*- coding: utf-8 -*-
"""Costco (COST) 月度销售 —— 生成 data/cost.js（网页看板的数据源）。

本文件是 costco-monthly-sales/build_data.py 的移植：那个站已经上线并由用户逐张验收过，
所以 **exhibit 的顺序、编号、标题文案、图注、窗口、截轴与断点一张都没改**，
改的只有三处工程约定：

  1. 数据源改读本仓库的 series/cost.csv（内容与 ~/.claude/skills/COST月度销售/
     cost_monthly.csv 逐字节相同，后者仍由 /COST月度销售 skill 每月解析官网新闻稿后更新）。
  2. payload 顶层字段名改成 build/CONTRACT.md 的统一契约（window.DASH，
     不再是 window.COST_DATA），补上 ticker / tracker / title / notes / footer。
  3. 汇总表的行由 {cur,prev,yag,mm,...} 摊平成 cells 数组，末尾核对表由裸数组
     改成 {n,title,cols,rows} 且单元格全部是**已格式化的字符串**（页面不做计算）。

原 index.html 里写死的「口径与方法说明」10 条搬进 payload.notes；其中 53 周月份
那条改成从数据里自动识别（原来是手写死的四个月份，加一个 53 周财年就会过时）。

CSV 列义：_r = reported（报告口径）, _a = adjusted（核心口径，剔除汽油与汇率）
         tc = total comp, us/ca/oi = 美国/加拿大/其他国际, ec = 电商, wh = 仓库数

依赖：pandas、numpy
用法：python3 build/cost.py
"""
import datetime
import json
import os

import numpy as np
import pandas as pd

import payload_guard

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SERIES = os.path.join(ROOT, 'series', 'cost.csv')
OUT = os.path.join(ROOT, 'data', 'cost.js')

# 与 PDF 一致的窗口起点
WIN_START = '2021-01'
# 头条图（Ex2）单独用全历史窗口：2021 起的窗口里，基数本身被 COVID 扭曲，
# 「当前 7-8% 相对 Costco 常态算什么水平」这个问题在短窗口下根本回答不了。
HIST_START = '2016-01'
ECOMM_START = '2022-01'
OVERLAY_MONTHS = 25

SRC = 'Source: Company data (Costco monthly sales press releases)'


def main():
    if not os.path.exists(SERIES):
        raise SystemExit(f'找不到源数据: {SERIES}')

    df = pd.read_csv(SERIES, index_col=0)
    df.index = pd.PeriodIndex(df.index, freq='M')
    need = ['net_sales_bn', 'weeks', 'ns_yoy', 'us_r', 'ca_r', 'oi_r', 'tc_r',
            'us_a', 'ca_a', 'oi_a', 'tc_a', 'wh_total', 'wh_us', 'ec_r', 'ec_a']
    miss = [c for c in need if c not in df.columns]
    if miss:
        raise SystemExit(f'series/cost.csv 缺列 {miss}')
    # 月份必须逐月连续：断档的序列画成相邻柱就是假的时间轴
    for a, b in zip(df.index[:-1], df.index[1:]):
        if (b - a).n != 1:
            raise SystemExit(f'月份不连续：{a} → {b}')
    LATEST = df.index[-1]

    # 净销售额增速里不进 comp 基数的那部分（新开/关闭仓库 + 口径残差），Ex5 与汇总表共用一列
    df['nc_gap'] = df['ns_yoy'] - df['tc_r']

    mlab = lambda p: p.strftime('%b-%y')                      # 'Jan-21'
    win = lambda start=WIN_START: df.loc[pd.Period(start, 'M'):]
    L = lambda a: [None if (v is None or (isinstance(v, float) and np.isnan(v))) else round(float(v), 6) for v in a]
    iv = lambda v: '—' if pd.isna(v) else f'{int(v)}'         # 缺列时别把 NaN 塞进 int()

    # 53 周财年多出的那一周落在某个 1 月，使该月与「上年同月」不是同一长度的区间。
    # 自动识别而不是硬编码月份；shift(12) 落在序列头部时是 NaN，而 NaN != 4.0 恒为 True，
    # 不加 notna() 守卫会把最早 12 个月整段误报成断点。
    _w = df['weeks']
    WEEK_BREAKS = set(df.index[_w.notna() & _w.shift(12).notna() & (_w != _w.shift(12))])

    def brk(d):
        """把断点月换算成给定窗口内的 x 索引（引擎把线画在该期柱的左缘）。"""
        return [i for i, p in enumerate(d.index) if p in WEEK_BREAKS]

    def stack(col, k):
        """同一零售月过去 N 年核心 comp 之和（照抄 build_report.py 的 stack）。"""
        v = df[col].values
        out = []
        for i in range(len(v)):
            idxs = [i - 12 * j for j in range(k)]
            out.append(np.nan if min(idxs) < 0 else sum(v[j] for j in idxs))
        return np.array(out)

    def stack_ex(n, col, title):
        d = win()
        pos = [df.index.get_loc(p) for p in d.index]
        ser = []
        for k, c, lab in [(2, 'BLUE', '2-year stack'), (3, 'NAVY', '3-year stack'), (4, 'MBLUE', '4-year stack')]:
            s = stack(col, k)
            ser.append({'name': lab, 'color': c, 'values': L([s[p] for p in pos])})
        return {'n': n, 'kind': 'lines', 'title': title, 'yfmt': 'pct0',
                'xlabels': [mlab(p) for p in d.index], 'xstep': 3,
                'src_extra': 'Stacks = sum of same-retail-month core comp over trailing N years',
                'series': ser}

    def bar_line_ex(n, bar_col, line_col, title, bar_name, line_name, start=WIN_START, xstep=4,
                    src_extra=None, **kw):
        d = win(start)
        out = {'n': n, 'kind': 'bar_line', 'title': title, 'yfmt': 'pct0',
               'xlabels': [mlab(p) for p in d.index], 'xstep': xstep,
               'bar': {'name': bar_name, 'color': 'NAVY', 'values': L(d[bar_col])},
               'line': {'name': line_name, 'color': 'BLUE', 'values': L(d[line_col])}}
        if src_extra:
            out['src_extra'] = src_extra
        out.update(kw)
        return out

    # 截轴文案统一一份：2021 年那几个 COVID 低基数尖峰把近 12 个月压成一条窄带，
    # 规矩 7 的做法是截轴 + 标真值，不是删点也不是砍窗口。
    CAP_NOTE = 'axis capped — outliers shown in red'
    CAP_SRC = '2021 年 COVID 低基数月份已截轴（红色空心圈/断口符号），真实值见图上标注'

    ex = []

    # Ex 2 —— 头条图：核心 comp 柱 + 报告口径线（同一 % 轴），全历史窗口
    # full: True → 渲染器把它排到汇总表下方的通栏区（127 根柱塞进半栏每根不到 3px）
    ex.append(bar_line_ex(2, 'tc_a', 'tc_r', 'COST Core Comp vs Reported Comp, y/y',
                          'Core Comp (ex. gas & FX)', 'Reported Comp',
                          start=HIST_START, xstep=6, full=True,
                          ycap=18, cap_note=CAP_NOTE, label_fmt='pct1',
                          src_extra='Core Comp = global SSS, ex. gas & FX；本图窗口自 '
                                    f'{HIST_START} 起（其余 comp 图自 {WIN_START} 起）。' + CAP_SRC))

    # Ex 3 —— 全公司 stacks
    ex.append(stack_ex(3, 'tc_a', 'COST Core Comp Growth Trends'))

    # Ex 4 —— 净销售额（左轴 $bn 柱）+ 同比（右轴 % 线）：PDF 为双轴，此处照搬
    d = win()
    ex.append({
        'n': 4, 'kind': 'bar_line_dual', 'title': 'Monthly Net Sales ($bn) & y/y Growth',
        'xlabels': [mlab(p) for p in d.index], 'xstep': 3, 'ylab2': 'y/y (%)',
        'break_at': brk(d), 'break_label': '53-week month — y/y not comparable',
        'bar_marks': brk(d),
        'mark_note': '本零售月与上年同月周数不同（53 周财年），柱的同比不可直接读',
        'src_extra': '注: 柱 = 净销售额绝对值，未按周数调整（零售月为 4 或 5 周，4-4-5 日历）；'
                     '线 = 公司报告 y/y，其基期是同样周数的上年错位窗口，与相邻柱不是同一区间。'
                     '红色虚线处为 53 周财年造成的周数错位月份，该处柱的同比不可直接读。',
        'bar': {'name': 'Net sales ($bn, LHS)', 'color': 'BLUE', 'values': L(d['net_sales_bn']), 'yfmt': 'usd0'},
        'line': {'name': 'y/y % (RHS)', 'color': 'NAVY', 'values': L(d['ns_yoy']), 'yfmt': 'pct0'},
    })

    # Ex 5 —— 净销售额增长的 comp / 非 comp 拆分（柱线间距即非 comp 贡献）
    ex.append(bar_line_ex(5, 'tc_r', 'ns_yoy', 'Net Sales Growth: Comp vs Non-Comp Contribution',
                          'Reported comp (y/y)', 'Net sales (y/y)', xstep=3,
                          ycap=20, cap_note=CAP_NOTE, label_fmt='pct1',
                          src_extra='恒等式轧差：非 comp 贡献 = 净销售额 y/y − 报告口径 comp，'
                                    '含新开/关闭仓库与口径残差，不是公司披露值。' + CAP_SRC))

    # Ex 6 —— 汽油与汇率影响（报告 − 核心）分地区，避免正负相消
    ex.append({
        'n': 6, 'kind': 'lines', 'title': 'Gas & FX Wedge by Region (reported - core), pp',
        'yfmt': 'pp0', 'xlabels': [mlab(p) for p in d.index], 'xstep': 3, 'zero_line': True,
        'src_extra': '用公司自己披露的分地区 reported 与 core 之差做的近似归因：'
                     '美国项主要是汽油价格，国际项主要是汇率折算——不是公司拆分。'
                     '合并成一根柱时两股力常互相抵消（如 2022-05：US +6.8 对 Other Intl −7.5）。',
        'series': [{'name': 'US', 'color': 'NAVY', 'values': L(d['us_r'] - d['us_a'])},
                   {'name': 'Canada', 'color': 'MBLUE', 'values': L(d['ca_r'] - d['ca_a'])},
                   {'name': "Other Int'l", 'color': 'BLUE', 'values': L(d['oi_r'] - d['oi_a'])},
                   {'name': 'Total (对照)', 'color': 'GRAY', 'values': L(d['tc_r'] - d['tc_a'])}],
    })

    # Ex 7-9 —— 分地区
    ex.append(bar_line_ex(7, 'us_a', 'us_r', 'US Comp, y/y', 'Core (ex. gas & FX)', 'Reported',
                          ycap=20, cap_note=CAP_NOTE, label_fmt='pct1', src_extra=CAP_SRC))
    ex.append(bar_line_ex(8, 'ca_a', 'ca_r', 'Canada Comp, y/y', 'Core (ex. gas & FX)', 'Reported',
                          ycap=25, cap_note=CAP_NOTE, label_fmt='pct1', src_extra=CAP_SRC))
    ex.append(bar_line_ex(9, 'oi_a', 'oi_r', 'Other International Comp, y/y',
                          'Core (ex. gas & FX)', 'Reported'))

    # Ex 10 —— 电商（窗口自 2022 起）
    d8 = win(ECOMM_START)
    ex.append(bar_line_ex(10, 'ec_a', 'ec_r', 'E-commerce / Digitally-Enabled Comp, y/y',
                          'E-comm Core (ex. FX)', 'Reported', start=ECOMM_START,
                          break_at=[list(d8.index).index(pd.Period('2025-09', 'M'))],
                          break_label='definition change: e-comm → Digitally-Enabled',
                          src_extra='FY26 起口径由 e-commerce 改为 Digitally-Enabled comparable sales，'
                                    '前后不保证可比；序列本身月度波动很大（FY25 区间 −2.5% ~ +35.7%），'
                                    '无法从图上分离口径影响。图窗自 2022 起（2021-01 曾达 ~+106% 的 COVID 低基数）。'))

    # Ex 11 —— 分地区核心 comp 叠图（最近 25 个月，带点标记）
    d9 = df.iloc[-OVERLAY_MONTHS:]
    ex.append({
        'n': 11, 'kind': 'lines', 'title': "Core Comp by Region (ex. gas & FX), last 24m", 'yfmt': 'pct0',
        'xlabels': [mlab(p) for p in d9.index], 'xstep': 2, 'markers': True,
        'zero_line': True,          # PDF 里 ex_region_overlay 调了 axhline(0)，轴需含 0
        'series': [{'name': 'US', 'color': 'NAVY', 'values': L(d9['us_a'])},
                   {'name': 'Canada', 'color': 'MBLUE', 'values': L(d9['ca_a'])},
                   {'name': "Other Int'l", 'color': 'BLUE', 'values': L(d9['oi_a'])}],
    })

    # Ex 12 —— 美国 stacks
    ex.append(stack_ex(12, 'us_a', 'US Core Comp Growth Trends'))

    # Ex 13 —— 仓库数（全历史）
    # 2016-08 / 2017-08 / 2017-09 三个月的新闻稿未披露仓库数。这里不能 dropna：
    # dropna 会把这 3 个月从 x 轴上一并抹掉，剩下的点等距连成一条线 ——
    # Jun-16→Jan-17 的 7 个月与 Jan-17→Jul-17 的 6 个月在图上一样宽，
    # 「一年新开多少家」直接从图上读会偏，且页面无任何提示（违反 CONTRACT §5.3）。
    # 保留完整月度轴，缺失月由 L() 传 None，charts.js 的 lines 分支遇 null 抬笔断线。
    # 用 first/last_valid_index 而不是整段 df，是保留 dropna 原本「序列两端不留空」的效果
    # （本例首尾都有值，结果就是全部 127 行；将来该列若晚于 Dec-15 才开始也仍然正确）。
    wh = df.loc[df['wh_total'].first_valid_index():df['wh_total'].last_valid_index()]
    whv = wh['wh_total'].dropna()          # annot 的首末端点必须落在真实观测上
    v0, v1 = whv.iloc[0], whv.iloc[-1]
    ex.append({
        'n': 13, 'kind': 'lines', 'title': 'Warehouse Count', 'yfmt': 'int',
        'xlabels': [mlab(p) for p in wh.index], 'xstep': 6,
        'annot': f'{mlab(whv.index[0])}: {v0:.0f} → {mlab(whv.index[-1])}: {v1:.0f}',
        'src_extra': '2016-08 / 2017-08 / 2017-09 三个月的新闻稿未披露仓库数，'
                     '线在这三处断开，不做插值补点。',
        'series': [{'name': 'Total warehouses', 'color': 'NAVY', 'values': L(wh['wh_total'])},
                   {'name': 'US & PR', 'color': 'BLUE', 'values': L(wh['wh_us'])}],
    })

    # Ex 14 —— 同一零售月跨年
    mo = LATEST.month
    same = df[(df.index.month == mo)].dropna(subset=['net_sales_bn'])
    n_yr = len(same) - 1
    cagr = ((same['net_sales_bn'].iloc[-1] / same['net_sales_bn'].iloc[0]) ** (1 / n_yr) - 1) * 100 if n_yr > 0 else 0.0
    ex.append({
        'n': 14, 'kind': 'bars_labeled',
        'title': f'{LATEST.strftime("%B")} Retail-Month Net Sales Across Years ($bn)', 'yfmt': 'usd0',
        'xlabels': [str(p.year) for p in same.index], 'xstep': 1, 'xrot': 0,   # PDF 里年份标签水平
        'src_extra': '同一零售月跨年对比(周数一致口径), 剔除季节性',
        'annot': f'{same.index[0].year}-{same.index[-1].year} CAGR: {cagr:.1f}%',
        'values': L(same['net_sales_bn']), 'label_fmt': 'f1',
    })

    # ── Exhibit 1：规矩 10 的汇总表（本月 | 上月 | 去年同月 ‖ m/m | y/y | 3Y %ile）──
    cur, prv, yag = LATEST, LATEST - 1, LATEST - 12

    def sget(col, p):
        v = df[col].get(p, np.nan) if p in df.index else np.nan
        return float(v) if pd.notna(v) else np.nan

    def pctile36(col, v):
        """近 36 个月分位 —— 直接回答「这个读数在自己的历史里有多极端」。
        分母取 len-1（自己不与自己比），与 gsx.summary_table 同口径。

        两类序列留空，因为分位对它们没有信息量：
          1. 单调不减的存量（仓库数）——几乎每月都是历史新高，分位恒为 ~100
             并被着成绿色，读起来像「异常之高」，其实只是在开店。判据用
             「非递减月份占比 ≥ 90%」而不是「递增 ≥ 90%」：仓库数有很多个月持平，
             按递增判会漏掉。
          2. 净销售额绝对值——4-4-5 零售日历下 4 周月与 5 周月混在同一个历史里，
             拿 5 周月去和一堆 4 周月比分位是拿苹果比橘子（与 Ex4 红线标的是同一件事）。
        增速类（comp、y/y）不受影响，它们本来就是可比的。"""
        h = df[col].dropna().iloc[-36:]
        if not np.isfinite(v) or len(h) < 8:
            return None
        if col == 'net_sales_bn':
            return None
        dd = h.diff().dropna()
        if len(dd) and float((dd >= 0).sum()) / len(dd) >= 0.90:
            return None
        return round(float((h < v).sum()) / max(1, len(h) - 1) * 100, 0)

    PCTF = lambda v: '—' if not np.isfinite(v) else f'{v:+.1f}%'
    # 非 comp 贡献是两个增速相减，量纲是百分点不是百分比，水平值也得写 pp
    PPF = lambda v: '—' if not np.isfinite(v) else f'{v:+.1f}pp'
    USDF = lambda v: '—' if not np.isfinite(v) else f'${v:.2f}bn'
    INTF = lambda v: '—' if not np.isfinite(v) else f'{v:,.0f}'

    def srow(label, col, mode, vfmt, mm_ok=True):
        """mode: pp = 比率指标（变化只能是百分点差）/ abs = 绝对个数 / ratio = 百分比变化。

        mm_ok=False 用于「相邻月本身就不可比」的行（4-4-5 零售日历下的绝对额）：
        m/m 整格留空。算得出来不等于该显示 —— 净销售额 4 周月与 5 周月相邻，
        m/m 的绝对多数是周数比而不是经营变化，一旦算出来还会按符号被涂成绿色，
        与表注里「不可当趋势读」的说明正好相反。这与 pctile36 因为同一条 4-4-5
        理由把该行 3Y %ile 留空是同一条口径规则，只是当时只落实到了分位列。
        """
        c, p1, p12 = sget(col, cur), sget(col, prv), sget(col, yag)

        def delta(a, b):
            if not (np.isfinite(a) and np.isfinite(b)):
                return ('', '')
            if mode in ('pp', 'abs'):
                v = a - b
                s = f'{v:+.1f}pp' if mode == 'pp' else f'{v:+,.0f}'
            else:
                if b == 0 or a * b < 0:      # 分母近 0 或两期异号，百分比变化没有意义
                    return ('', '')
                v = (a / b - 1) * 100
                s = f'{v:+.1f}%'
            return (s, 'pos' if v > 0 else ('neg' if v < 0 else ''))

        mm, yy = (delta(c, p1) if mm_ok else ('', '')), delta(c, p12)
        p = pctile36(col, c)
        return {'kind': 'row', 'label': label, 'cells': [
            {'v': vfmt(c), 'cls': 'cur'}, {'v': vfmt(p1)}, {'v': vfmt(p12)},
            {'v': mm[0], 'cls': mm[1]}, {'v': yy[0], 'cls': yy[1]},
            {'v': '' if p is None else f'{p:.0f}',
             'cls': '' if p is None else ('hi' if p >= 66 else ('lo' if p <= 33 else ''))},
        ]}

    G = lambda t: {'kind': 'group', 'label': t}
    summary = {
        'title': '关键指标汇总（本月 vs 上月 / 去年同月，含近 3 年分位）',
        'heads': [mlab(cur), mlab(prv), mlab(yag), 'm/m', 'y/y', '3Y %ile'],
        'sep': 3,                     # 竖线画在「水平值」与「变化率」之间
        'rows': [
            G('核心 comp（剔除汽油与汇率，y/y）'),
            srow('Total', 'tc_a', 'pp', PCTF),
            srow('US', 'us_a', 'pp', PCTF),
            srow('Canada', 'ca_a', 'pp', PCTF),
            srow("Other Int'l", 'oi_a', 'pp', PCTF),
            srow('E-comm / Digitally-Enabled', 'ec_a', 'pp', PCTF),
            G('报告口径 comp（含汽油与汇率，y/y）'),
            srow('Total', 'tc_r', 'pp', PCTF),
            srow('US', 'us_r', 'pp', PCTF),
            srow('Canada', 'ca_r', 'pp', PCTF),
            srow("Other Int'l", 'oi_r', 'pp', PCTF),
            srow('E-comm / Digitally-Enabled', 'ec_r', 'pp', PCTF),
            G('净销售额'),
            srow('净销售额 ($bn)', 'net_sales_bn', 'ratio', USDF, mm_ok=False),
            srow('净销售额 y/y', 'ns_yoy', 'pp', PCTF),
            srow('非 comp 贡献 (y/y − 报告 comp)', 'nc_gap', 'pp', PPF),
            G('仓库数（期末）'),
            srow('全球', 'wh_total', 'abs', INTF),
            srow('美国及波多黎各', 'wh_us', 'abs', INTF),
        ],
        'note': ('m/m、y/y 对比率指标一律取百分点差（pp），对绝对量取百分比或个数差；'
                 f'3Y %ile = 该读数在最近 36 个月中的分位（100 = 三年最高）。'
                 f'净销售额是 4-4-5 零售日历下的月度绝对额，相邻月在周数与季节性上都不可比'
                 f'（本月 {iv(df["weeks"].iloc[-1])} 周 vs 上月 {iv(df["weeks"].iloc[-2])} 周），'
                 f'其 m/m 与 3Y %ile 一律留空，不做周均折算；y/y 对齐同一零售月，可比。'),
    }

    # ── 近 13 个月核对表（与 PDF 第 4 页一致；逐条核对用，放在页面最后）──
    # 单元格一律是已格式化的字符串（CONTRACT §4）：官方原始单位，不做任何换算。
    F1 = lambda v: None if pd.isna(v) else f'{float(v):.1f}'
    F2 = lambda v: None if pd.isna(v) else f'{float(v):.2f}'
    I0 = lambda v: None if pd.isna(v) else f'{int(v):,d}'
    d13 = df.iloc[-13:]
    table = {
        'n': 15,
        'title': '近 13 个月月度数据核对表（comp 均为 y/y %, 核心 = 除油汇）',
        'idx': '零售月',
        'cols': [['净销售额 $bn', 'net_sales_bn'], ['y/y %', 'ns_yoy'], ['核心 Total', 'tc_a'],
                 ['核心 US', 'us_a'], ['核心 Canada', 'ca_a'], ['核心 Other Intl', 'oi_a'],
                 ['核心 E-comm', 'ec_a'], ['报告 Total', 'tc_r'], ['周数', 'weeks'],
                 ['仓库数(全球)', 'wh_total']],
        'rows': [{'xl': mlab(p), 'net_sales_bn': F2(r.net_sales_bn),
                  **{k: F1(getattr(r, k)) for k in
                     ['ns_yoy', 'tc_a', 'us_a', 'ca_a', 'oi_a', 'ec_a', 'tc_r']},
                  'weeks': I0(r.weeks), 'wh_total': I0(r.wh_total)}
                 for p, r in zip(d13.index, d13.itertuples())],
    }

    # ── 口径与方法说明（原 index.html 的 10 条；53 周月份那条改成自动识别）──
    wk = '/'.join(str(p) for p in sorted(WEEK_BREAKS))
    NOTES = [
        ('<b>数据源（唯一）</b>：Costco 每零售月结束后首个周三盘后在官网 IR'
         '（investor.costco.com）发布的月度销售新闻稿；本页解析 '
         f'{HIST_START} 以来全部新闻稿，不使用任何第三方（券商）研报数据或观点。'),
        ('<b>4-4-5 零售日历</b>：零售月为 4 周或 5 周（周日截止），4 周与 5 周月份的'
         '净销售额绝对值<strong>不可直接环比</strong>。'),
        ('<b>核心 comp</b> = 公司披露的「剔除汽油价格变动与汇率影响」的可比销售；'
         '报告口径为未调整值。两者之差按地区拆开即 Exhibit 6。'),
        ('<b>E-commerce 口径</b>：FY26 起更名为 Digitally-Enabled comparable sales，'
         '历史序列直接拼接，Exhibit 10 在 2025-09 处画红色竖虚线标注该断点。'
         'Exhibit 10 图窗自 2022 起（2021-01 曾达 ~+106% 的 COVID 低基数）。'),
        (f'<b>53 周财年</b>造成个别 1 月的周数与上年同月不同（本页自动识别：{wk}）。'
         '公司披露的 comp 已按可比周调整；<strong>净销售额同比是公司报告值，'
         '其基期是同样周数的上年错位窗口</strong>，与图上相邻的柱不是同一区间，'
         '故 Exhibit 4 在这些位置画红色竖虚线、柱用斜纹标出。'),
        ('<b>客流与品类</b>：traffic（客流）/ ticket（客单）与品类细分不在月度新闻稿内'
         '（仅公司预录电话留言口头披露），本页只采用官网新闻稿数据，故不含该细分。'),
        ('<b>Stacks</b>（Exhibit 3 / 12）= 同一零售月过去 N 年核心 comp 之和，'
         '用于剔除单年基数扰动看趋势。'),
        ('<b>截轴</b>（Exhibit 2 / 5 / 7 / 8）：2021 年 COVID 低基数尖峰把近 12 个月压成窄带，'
         '故对 y 轴设上界；<strong>超界的点一个都不删</strong>，柱端加断口符号、'
         '点画成红色空心圈，真实值以红色竖排数字标在图上。'),
        ('<b>核对表保持官方原始单位</b>：净销售额为 $bn、comp 与 y/y 为百分比、'
         '周数与仓库数为个数，均未换算，可直接拿去和官网新闻稿逐条对。'),
        ('本页图表版式模仿 Goldman Sachs GIR exhibit 风格，仅为视觉版式，'
         '不含其研究观点或数据。仅供个人研究，不构成投资建议。'),
    ]

    Lr = df.iloc[-1]
    tail13 = [mlab(p) for p in d13.index]
    headline = (f'核心 comp（除油汇）{Lr["tc_a"]:+.1f}% · 报告口径 comp {Lr["tc_r"]:+.1f}% · '
                f'净销售额 ${Lr["net_sales_bn"]:.2f}bn（{Lr["ns_yoy"]:+.1f}% y/y）· '
                f'仓库数 {iv(Lr["wh_total"])}（US & PR {iv(Lr["wh_us"])}）')

    payload = {
        # 构建日期不进 JSON：进了以后每天跑都会 diff，monthly_run 的幂等检查永久失效。
        # 页面上的新鲜度信号绑数据月份（data_through），不绑构建日期。
        'ticker': 'cost',
        'tracker': 'COST Monthly Sales Tracker',
        'title': f'Costco Wholesale (COST): 月度销售跟踪 — {LATEST.year}年{LATEST.month}月',
        'data_through': str(LATEST),
        'through_label': f'零售月 {LATEST.strftime("%b %Y")}（{iv(Lr["weeks"])} 周）',
        # 月数按 CSV 实际首末月算，不能用 len(df)：CSV 从 2015-12 起，
        # 而 Ex2 的时间轴自 HIST_START(2016-01) 起，两者差一个月，写死会和图对不上。
        'subtitle': (f'零售月 {LATEST.strftime("%b %Y")} ({iv(Lr["weeks"])}周) | '
                     f'数据: Costco 官网月度销售新闻稿 ({df.index[0]} 至今 {len(df)} 个月) | '
                     f'版式仿 Goldman Sachs GIR'),
        # 规矩 13：只留一行数据条，叙述性 bullets 里的数字全部在下面的表和图里。
        # 正负号一律交给 f-string 的 '+' 标志，不能写死字面量（负值会印成 '+-0.6%'）。
        'headline': headline,
        'hub_line': (f'核心 comp {Lr["tc_a"]:+.1f}% · 净销售额 ${Lr["net_sales_bn"]:.2f}bn'
                     f'（{Lr["ns_yoy"]:+.1f}% y/y）'),
        'source': SRC,
        'xlabels': tail13,
        'xlabels_long': [mlab(p) for p in df.index],
        'summary': summary,
        'exhibits': ex,
        'table': table,
        'notes': NOTES,
        'footer': ('数据与算法源自 <code>/COST月度销售</code> skill 的解析管道 · '
                   '数值以 Costco 官网原始披露为准 · '
                   '每张图右上角可切换「表格」视图逐条核对 · '
                   '仅供个人研究，不构成投资建议'),
    }

    # 写出前先过 CONTRACT §5.5 护栏（NaN/Infinity 一律拒写）；首行注释与序列化都在里面。
    payload_guard.write_dash(OUT, payload, 'cost')

    print(f'cost: 数据截至 {LATEST} | CSV 共 {len(df)} 个月 {df.index[0]} → {df.index[-1]}')
    print(f'53 周周数错位月份（自动识别）: {sorted(str(p) for p in WEEK_BREAKS)}')
    print(f'Exhibit 1 汇总表 + Exhibit 2-{ex[-1]["n"]} 共 {len(ex)} 张图 + '
          f'Exhibit {table["n"]} 核对表 → {os.path.relpath(OUT, ROOT)} '
          f'({os.path.getsize(OUT) / 1024:.1f} KB)')
    print(headline)


if __name__ == '__main__':
    main()
