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
import pctile                      # 3Y %ile 的唯一实现，本文件不再自己写分位判据

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
# FY26 起 e-commerce comp 更名为 Digitally-Enabled comparable sales，公司不重述历史。
# 断点在哪张图上画得出来、汇总表哪几格要加注，全部由它现算，不写死索引也不写死月份文案。
ECOMM_BREAK = pd.Period('2025-09', 'M')

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
        """把断点月换算成给定窗口内的 x 索引（引擎把线画在该期柱的左缘）。

        窗口盖不到的断点自然不在返回值里，返回空表示这张图上一条线都没有 ——
        调用处必须据此把图注里「此处画了红色竖虚线」那句话一并去掉，否则就是
        图注声称画了、图上没有（复查全站报了 7 条这类）。"""
        return [i for i, p in enumerate(d.index) if p in WEEK_BREAKS]

    def brk1(d, period):
        """单个断点在窗口内的 x 索引；滚出窗口返回 None，绝不抛异常。

        原来这里写的是 list(d8.index).index(...)，2025-09 一旦滚出 e-comm 图窗
        就是 ValueError、整个生成器退出、页面永久停更（build/lpla.py 现在就是
        这个毛病）。窗口起点固定时今天不会触发，但硬失败的写法本身不能留。"""
        lst = list(d.index)
        return lst.index(period) if period in lst else None

    # ── 数值格式化的两条硬约定 ────────────────────────────────────────────
    def dsp(v, d, unit):
        """格式化一个差值/水平值，返回 (显示串, 配色类)。

        两件事在这里一并管住：
          1. **负零不是信息**：四舍五入后等于 0 就印 '0.0'，不印 '-0.0'。
          2. **配色按四舍五入后的值定**：+0.04 印成 '0.0' 却涂成绿色是自相矛盾。
        """
        r = round(float(v), d) + 0.0                 # +0.0 把 -0.0 归一成 0.0
        s = f'{r:+.{d}f}{unit}' if r else f'{0:.{d}f}{unit}'
        return s, ('pos' if r > 0 else ('neg' if r < 0 else ''))

    def ppdiff(v):
        """比率类差异的单位规矩（CONTRACT §2 / GS LPLA 规矩 2）：|差| < 1 写 bp，否则写 pp。

        本页原来一律写 pp，与其余 8 页（schw/lpla/axp/hood/hkex/msci/tsm/wealth）不一致，
        同一站内同类量出现两套写法（复查 recheck#2）。数值本身没错，改的是单位约定。"""
        return dsp(v * 100, 0, 'bp') if abs(v) < 1 else dsp(v, 1, 'pp')

    # ── 截轴上界：从数据里定，而不是从 deck 抄一个固定值 ──────────────────
    def cap_for(d, cols, step=5):
        """上界 = 「除最极端那一个月之外的最大值」向上取整到 step 的倍数；算不出返回 None。

        原来四张图的上界是 deck 里的固定值 18/20/20/25，结果 Apr-21 与 May-21 两个
        COVID 低基数月（有时还带上 Jun-22 那种只超界 0.1pp 的）一起越界，图顶挤出
        三四个红色竖排真值，而空心圈只有一两个 —— 标签与锚点对不上号，人眼复查
        逐张点名（Ex2 / Ex5 / Ex7 / Ex8）。

        改成「只截最极端的那一个月」之后，越界读数集中在同一个 x 上，每个标签都有
        唯一锚点；其余尖峰照常画在轴内。**一个点都没删**，变的只是画到哪里为止。
        """
        v = pd.concat([d[c] for c in cols], axis=1)
        peak = v.max(axis=1)                          # 每月的上包络
        if peak.notna().sum() < 3:
            return None
        rest = peak.drop(peak.idxmax()).max()
        return None if not np.isfinite(rest) else float(np.ceil(rest / step) * step)

    def cap_outliers(d, named, cap):
        """被截读数的清单：月份 + 是哪条序列 + 真值。

        图上那几个红色竖排数字必须能对上号 —— 复查原话是「第三个数没有任何锚点，
        读者没法知道它属于哪个月、哪条序列」。图上画不下的那部分身份信息写进图注。"""
        out = []
        for p in d.index:
            for c, name in named:
                v = d.at[p, c]
                if pd.notna(v) and float(v) > cap:
                    out.append(f'{mlab(p)} {name} {float(v):+.1f}%')
        return out

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
                    src_extra=None, cap=False, **kw):
        d = win(start)
        out = {'n': n, 'kind': 'bar_line', 'title': title, 'yfmt': 'pct0',
               'xlabels': [mlab(p) for p in d.index], 'xstep': xstep,
               'bar': {'name': bar_name, 'color': 'NAVY', 'values': L(d[bar_col])},
               'line': {'name': line_name, 'color': 'BLUE', 'values': L(d[line_col])}}
        if cap:
            c = cap_for(d, [bar_col, line_col])
            outl = ([] if c is None else                       # 上界可能算出 0，别用真值判断
                    cap_outliers(d, [(bar_col, bar_name), (line_col, line_name)], c))
            # 一个点都没越界就根本不截轴，也不留下「本图已截轴」的说明 ——
            # 图注说了截轴、图上却没有红色标注，读者会去找一个不存在的东西。
            if outl:
                out.update({'ycap': c, 'cap_note': CAP_NOTE, 'label_fmt': 'pct1'})
                capped.append(n)
                cs = (f'纵轴上界截在 {c:.0f}%，其余月份全部画在轴内；'
                      f'超界读数（{len(outl)} 个，一个点都没删）：{"；".join(outl)}，'
                      f'图上以红色空心圈/柱端断口符号 + 竖排真值标出。')
                src_extra = (src_extra + cs) if src_extra else cs
        if src_extra:
            out['src_extra'] = src_extra
        out.update(kw)
        return out

    # 截轴文案统一一份：2021 年那几个 COVID 低基数尖峰把近 12 个月压成一条窄带，
    # 规矩 7 的做法是截轴 + 标真值，不是删点也不是砍窗口。
    CAP_NOTE = 'axis capped — outliers shown in red'

    ex = []
    capped = []          # 真正截了轴的 exhibit 编号，「口径与方法说明」那一条据此生成

    # Ex 2 —— 头条图：核心 comp 柱 + 报告口径线（同一 % 轴），全历史窗口
    # full: True → 渲染器把它排到汇总表下方的通栏区（127 根柱塞进半栏每根不到 3px）
    ex.append(bar_line_ex(2, 'tc_a', 'tc_r', 'COST Core Comp vs Reported Comp, y/y',
                          'Core Comp (ex. gas & FX)', 'Reported Comp',
                          start=HIST_START, xstep=6, full=True, cap=True,
                          src_extra='Core Comp = global SSS, ex. gas & FX；本图窗口自 '
                                    f'{HIST_START} 起（其余 comp 图自 {WIN_START} 起）。'))

    # Ex 3 —— 全公司 stacks
    ex.append(stack_ex(3, 'tc_a', 'COST Core Comp Growth Trends'))

    # Ex 4 —— 净销售额（左轴 $bn 柱）+ 同比（右轴 % 线）：PDF 为双轴，此处照搬
    d = win()
    b4 = brk(d)
    ex4 = {
        'n': 4, 'kind': 'bar_line_dual', 'title': 'Monthly Net Sales ($bn) & y/y Growth',
        'xlabels': [mlab(p) for p in d.index], 'xstep': 3, 'ylab2': 'y/y (%)',
        'src_extra': '注: 柱 = 净销售额绝对值，未按周数调整（零售月为 4 或 5 周，4-4-5 日历）；'
                     '线 = 公司报告 y/y，其基期是同样周数的上年错位窗口，与相邻柱不是同一区间。',
        'bar': {'name': 'Net sales ($bn, LHS)', 'color': 'BLUE', 'values': L(d['net_sales_bn']), 'yfmt': 'usd0'},
        'line': {'name': 'y/y % (RHS)', 'color': 'NAVY', 'values': L(d['ns_yoy']), 'yfmt': 'pct0'},
    }
    if b4:
        # 断点竖排标签压在柱体上（人眼复查：红字盖住浅蓝柱、占掉图中相当高一段），
        # 所以标签只留能一眼认出的最短说法，完整解释在下面的 src_extra、tooltip
        # 与页尾说明第 5 条里各有一份 —— 信息一点没少，图上少压掉三分之二的柱。
        ex4.update({
            'break_at': b4, 'break_label': '53-week month',
            'bar_marks': b4,
            'mark_note': '本零售月与上年同月周数不同（53 周财年），柱的同比不可直接读',
        })
        ex4['src_extra'] += (f'图上 {"、".join(mlab(d.index[i]) for i in b4)} 处画有红色竖虚线、'
                             '柱用斜纹标出：53 周财年造成该月与上年同月周数不同，'
                             '该处柱的同比不可直接读。')
    ex.append(ex4)

    # Ex 5 —— 净销售额增长的 comp / 非 comp 拆分（柱线间距即非 comp 贡献）
    ex.append(bar_line_ex(5, 'tc_r', 'ns_yoy', 'Net Sales Growth: Comp vs Non-Comp Contribution',
                          'Reported comp (y/y)', 'Net sales (y/y)', xstep=3, cap=True,
                          src_extra='恒等式轧差：非 comp 贡献 = 净销售额 y/y − 报告口径 comp，'
                                    '含新开/关闭仓库与口径残差，不是公司披露值。'))

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
                          cap=True))
    ex.append(bar_line_ex(8, 'ca_a', 'ca_r', 'Canada Comp, y/y', 'Core (ex. gas & FX)', 'Reported',
                          cap=True))
    # Ex9 不截轴：其余三张图的最大值与「次极端月」差着一大截（Canada 44.0 vs 28.8），
    # 截掉一个月能换回 1/3 的纵向空间；Other Int'l 是 33.5 vs 25.7，同样规则只把上界
    # 从 ~34 挪到 30，为一成的空间多添一处红色标注不划算。轴范围本来就不是被单点定死的。
    ex.append(bar_line_ex(9, 'oi_a', 'oi_r', 'Other International Comp, y/y',
                          'Core (ex. gas & FX)', 'Reported'))

    # Ex 10 —— 电商（窗口自 2022 起）
    d8 = win(ECOMM_START)
    b10 = brk1(d8, ECOMM_BREAK)
    ec_src = ('序列本身月度波动很大（FY25 区间 −2.5% ~ +35.7%），无法从图上分离口径影响。'
              '图窗自 2022 起（2021-01 曾达 ~+106% 的 COVID 低基数）。')
    ec_kw = {}
    if b10 is not None:
        # 同 Ex4：竖排标签原文 44 个字符，从图顶一路压到零线，中段压在深蓝柱上读不出来。
        # 图上只留「definition change」，改成什么、为什么不可比写在图注与说明第 4 条。
        ec_kw = {'break_at': [b10], 'break_label': 'definition change'}
        ec_src = (f'FY26 起口径由 e-commerce 改为 Digitally-Enabled comparable sales，前后不保证可比；'
                  f'图上 {mlab(ECOMM_BREAK)} 处的红色竖虚线即该口径变更。' + ec_src)
    else:
        ec_src = ('FY26 起口径由 e-commerce 改为 Digitally-Enabled comparable sales，前后不保证可比；'
                  '该断点已滚出本图窗口，图上不再画竖虚线。' + ec_src)
    ex.append(bar_line_ex(10, 'ec_a', 'ec_r', 'E-commerce / Digitally-Enabled Comp, y/y',
                          'E-comm Core (ex. FX)', 'Reported', start=ECOMM_START,
                          src_extra=ec_src, **ec_kw))

    # Ex 11 —— 分地区核心 comp 叠图（最近 25 个月，带点标记）
    # 标题里的月数由实际画出的点数生成：原文写死 "last 24m" 而 OVERLAY_MONTHS=25，
    # 图上是 25 个点 —— 这是规格书自带的口径瑕疵，移植时照抄了下来。
    # 标题也是一句「声称」，一样得是实话。
    d9 = df.iloc[-OVERLAY_MONTHS:]
    ex.append({
        'n': 11, 'kind': 'lines', 'yfmt': 'pct0',
        'title': f"Core Comp by Region (ex. gas & FX), last {len(d9)}m",
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
    # 缺失月份也从数据里读，不写死：图注声称「线在这三处断开」，那就必须真的是这三处。
    wh_gaps = [str(p) for p in wh.index[wh['wh_total'].isna()]]
    wh_src = ('未披露月份：' + ' / '.join(wh_gaps) +
              f'（共 {len(wh_gaps)} 处），线在这些位置断开，不做插值补点。'
              ) if wh_gaps else '全窗口逐月均有披露，线上没有断点。'
    ex.append({
        'n': 13, 'kind': 'lines', 'title': 'Warehouse Count', 'yfmt': 'int',
        'xlabels': [mlab(p) for p in wh.index], 'xstep': 6,
        'annot': f'{mlab(whv.index[0])}: {v0:.0f} → {mlab(whv.index[-1])}: {v1:.0f}',
        'src_extra': wh_src,
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

    # ── 3Y %ile ──────────────────────────────────────────────────────────
    # 分位**判据**统一走 build/pctile.py，本文件不再自己写一份：同一条序列在两页被判
    # 成相反结果，正是各写各的造成的。下面这张表是**本页自己的口径理由**导致的留空，
    # 与「这一列有没有区分度」是两回事，各自独立生效。
    BLANK_WHY = {
        'net_sales_bn':
            '4-4-5 零售日历下 4 周月与 5 周月混在同一段历史里，拿 5 周月去比一堆 4 周月'
            '不是同一个量（与 Exhibit 4 红线标的是同一件事）',
        'wh_total':
            '期末仓库数是只增不减的开店计数，几乎每月都是历史新高，分位恒在区间上端'
            '并被涂成绿色，读起来像「异常之高」，其实只是在开店',
    }
    BLANK_WHY['wh_us'] = BLANK_WHY['wh_total']
    # e-comm 两行的 36 个月分位窗口跨了 FY26 口径变更：窗口里一部分是旧 e-commerce、
    # 一部分是新 Digitally-Enabled，混在一起排序算不出有意义的分位。断点滚出 36 个月
    # 窗口后这两条自动消失，不写死。
    EC_IN_WIN = ECOMM_BREAK > cur - 36
    if EC_IN_WIN:
        for _c in ('ec_a', 'ec_r'):
            BLANK_WHY[_c] = (f'近 36 个月窗口跨了 {ECOMM_BREAK} 的口径变更'
                             '（e-commerce → Digitally-Enabled），窗口内两种口径混排')
    # y/y 是否也跨断点（本月与去年同月分属两种口径）—— 同样现算
    EC_CROSS_YOY = yag < ECOMM_BREAK <= cur

    def pcell(col):
        """3Y %ile 单元格。判据交给 pctile.cell()，本页只负责口径性留空。"""
        if col in BLANK_WHY:
            return {'v': ''}
        s = [None if pd.isna(x) else float(x) for x in df[col]]
        v, cls = pctile.cell(s)
        return {'v': v, 'cls': cls} if cls else {'v': v}

    PCTF = lambda v: '—' if not np.isfinite(v) else dsp(v, 1, '%')[0]
    # 非 comp 贡献是两个增速相减，量纲是百分点不是百分比，水平值也得写 pp
    PPF = lambda v: '—' if not np.isfinite(v) else dsp(v, 1, 'pp')[0]
    USDF = lambda v: '—' if not np.isfinite(v) else f'${v:.2f}bn'
    INTF = lambda v: '—' if not np.isfinite(v) else f'{v:,.0f}'

    def srow(label, col, mode, vfmt, mm_ok=True, cross=False):
        """mode: pp = 比率指标（变化只能是百分点差）/ abs = 绝对个数 / ratio = 百分比变化。

        mm_ok=False 用于「相邻月本身就不可比」的行（4-4-5 零售日历下的绝对额）：
        m/m 整格留空。算得出来不等于该显示 —— 净销售额 4 周月与 5 周月相邻，
        m/m 的绝对多数是周数比而不是经营变化，一旦算出来还会按符号被涂成绿色，
        与表注里「不可当趋势读」的说明正好相反。

        cross=True 用于 y/y 两端分属两种口径的行（e-comm 跨 FY26 定义变更）：
        数值照印 —— 公司自己就是这么报的 —— 但**不涂涨跌色**，并在行名后加 †。
        把一个跨口径的差涂成绿色，等于替读者下了「确实好转了」这个结论，而本页
        Exhibit 10 的图注刚说过「前后不保证可比、无法从图上分离口径影响」。
        """
        c, p1, p12 = sget(col, cur), sget(col, prv), sget(col, yag)

        def delta(a, b):
            if not (np.isfinite(a) and np.isfinite(b)):
                return ('', '')
            if mode == 'pp':
                return ppdiff(a - b)
            if mode == 'abs':
                r = round(a - b) + 0.0
                return (f'{r:+,.0f}' if r else '0'), ('pos' if r > 0 else ('neg' if r < 0 else ''))
            if b == 0 or a * b < 0:          # 分母近 0 或两期异号，百分比变化没有意义
                return ('', '')
            return dsp((a / b - 1) * 100, 1, '%')

        mm, yy = (delta(c, p1) if mm_ok else ('', '')), delta(c, p12)
        if cross:
            yy = (yy[0], '')
        return {'kind': 'row', 'label': label + (' †' if cross else ''), 'cells': [
            {'v': vfmt(c), 'cls': 'cur'}, {'v': vfmt(p1)}, {'v': vfmt(p12)},
            {'v': mm[0], 'cls': mm[1]}, {'v': yy[0], 'cls': yy[1]},
            pcell(col),
        ]}

    # 表注：每一个留空、每一个 † 都必须在这里有一句对应的解释，且解释由留空本身
    # 现算出来 —— 手写的表注会在数据滚动后变成假话。
    _blank_lines = []
    for _c, _lab in [('net_sales_bn', '净销售额 ($bn)'), ('wh_total', '仓库数（全球 / 美国及波多黎各）'),
                     ('ec_a', 'E-comm / Digitally-Enabled（核心与报告两行）')]:
        if _c in BLANK_WHY:
            _blank_lines.append(f'<b>{_lab}</b> 的 3Y %ile 留空：{BLANK_WHY[_c]}。')
    # pctile.py 自己判成「没有区分度」的行，理由用它给的原话，不另写一套说法
    for _c, _lab in [('tc_a', '核心 comp Total'), ('us_a', '核心 comp US'), ('ca_a', '核心 comp Canada'),
                     ("oi_a", "核心 comp Other Int'l"), ('tc_r', '报告 comp Total'),
                     ('us_r', '报告 comp US'), ('ca_r', '报告 comp Canada'),
                     ('oi_r', "报告 comp Other Int'l"), ('ns_yoy', '净销售额 y/y'),
                     ('nc_gap', '非 comp 贡献')]:
        if _c not in BLANK_WHY:
            _w = pctile.why_blank([None if pd.isna(x) else float(x) for x in df[_c]])
            if _w:
                _blank_lines.append(f'<b>{_lab}</b> 的 3Y %ile 留空：{_w}。')
    _summary_note = (
        'm/m、y/y 对比率指标一律取百分点差，|差| ≥ 1 写 pp、< 1 写 bp（全站同一约定）；'
        '对绝对量取百分比或个数差。3Y %ile = 该读数在最近 36 个月中的分位（100 = 三年最高），'
        '判据与全站共用 build/pctile.py：某一行的分位若在近两年里几乎恒定在区间端点，'
        '说明它对这一行没有区分度，整列留空。'
        f'净销售额是 4-4-5 零售日历下的月度绝对额，相邻月在周数与季节性上都不可比'
        f'（本月 {iv(df["weeks"].iloc[-1])} 周 vs 上月 {iv(df["weeks"].iloc[-2])} 周），'
        f'其 m/m 一律留空，不做周均折算；y/y 对齐同一零售月，可比。'
        + ('' if not _blank_lines else ' ' + ' '.join(_blank_lines))
        + ('' if not EC_CROSS_YOY else
           f' <b>†</b>：本月（{mlab(cur)}）与去年同月（{mlab(yag)}）分处 {ECOMM_BREAK} '
           'e-commerce → Digitally-Enabled 口径变更的两侧，该 y/y 是两种口径相减，'
           '数值照公司披露印出但不涂涨跌色（见 Exhibit 10 的断点线与图注）。'))

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
            srow('E-comm / Digitally-Enabled', 'ec_a', 'pp', PCTF, cross=EC_CROSS_YOY),
            G('报告口径 comp（含汽油与汇率，y/y）'),
            srow('Total', 'tc_r', 'pp', PCTF),
            srow('US', 'us_r', 'pp', PCTF),
            srow('Canada', 'ca_r', 'pp', PCTF),
            srow("Other Int'l", 'oi_r', 'pp', PCTF),
            srow('E-comm / Digitally-Enabled', 'ec_r', 'pp', PCTF, cross=EC_CROSS_YOY),
            G('净销售额'),
            srow('净销售额 ($bn)', 'net_sales_bn', 'ratio', USDF, mm_ok=False),
            srow('净销售额 y/y', 'ns_yoy', 'pp', PCTF),
            srow('非 comp 贡献 (y/y − 报告 comp)', 'nc_gap', 'pp', PPF),
            G('仓库数（期末）'),
            srow('全球', 'wh_total', 'abs', INTF),
            srow('美国及波多黎各', 'wh_us', 'abs', INTF),
        ],
        'note': _summary_note,
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

    # ── 口径与方法说明（原 index.html 的 10 条；凡是「图上画了什么」的话一律现算）──
    #
    # 这一节里的每一句「Exhibit N 画了红色竖虚线 / 截了轴」都是对渲染结果的**声称**。
    # 声称必须由生成断点、生成截轴的那段代码本身产出，不能手写：Ex4 的窗口自 2021-01 起，
    # 而 WEEK_BREAKS 里有 2018-01 / 2019-01 两个月落在窗口之外，原文却写「故 Exhibit 4
    # 在这些位置画红色竖虚线」——读者会去图上找四条线，实际只有两条。
    wk_all = sorted(WEEK_BREAKS)
    wk_drawn = [d.index[i] for i in b4]                       # Ex4 上真正画出来的
    wk_out = [p for p in wk_all if p not in wk_drawn]
    wk_txt = f'本页自动识别：{" / ".join(str(p) for p in wk_all)}'
    if wk_drawn:
        wk_txt += ('；其中 ' + ' / '.join(str(p) for p in wk_drawn) +
                   ' 落在 Exhibit 4 的窗口内，图上画有红色竖虚线、柱用斜纹标出')
        if wk_out:
            wk_txt += ('，' + ' / '.join(str(p) for p in wk_out) +
                       ' 早于图窗起点，图上没有对应的线')
    else:
        wk_txt += '；全部早于 Exhibit 4 的图窗起点，图上没有对应的线'
    ec_note = ('<b>E-commerce 口径</b>：FY26 起更名为 Digitally-Enabled comparable sales，历史序列直接拼接'
               + (f'，Exhibit 10 在 {ECOMM_BREAK} 处画红色竖虚线标注该断点。'
                  if b10 is not None else
                  '；该断点已早于 Exhibit 10 的图窗起点，图上没有对应的线。')
               + 'Exhibit 10 图窗自 2022 起（2021-01 曾达 ~+106% 的 COVID 低基数）。'
               + ('' if not EC_CROSS_YOY else
                  f'Exhibit 1 汇总表里 e-comm 两行的 y/y 跨该断点，已加 † 标出。'))
    cap_note_txt = (
        '<b>截轴</b>（' + ' / '.join(f'Exhibit {n}' for n in capped) + '）：'
        '2021 年 COVID 低基数尖峰把近 12 个月压成窄带，故对 y 轴设上界。'
        '上界不是拍的：设在「除最极端那一个月之外的最大值」之上，'
        '使越界读数集中在同一个月份上、图上每个红色数字都有唯一锚点；'
        '<strong>超界的点一个都不删</strong>，柱端加断口符号、点画成红色空心圈，'
        '真实值以红色竖排数字标在图上，并在各图图注里逐条列出「哪个月、哪条序列、多少」。'
    ) if capped else '<b>截轴</b>：本期数据没有需要截轴的离群月，各图 y 轴均按数据自适应。'
    NOTES = [
        ('<b>数据源（唯一）</b>：Costco 每零售月结束后首个周三盘后在官网 IR'
         '（investor.costco.com）发布的月度销售新闻稿；本页解析 '
         f'{HIST_START} 以来全部新闻稿，不使用任何第三方（券商）研报数据或观点。'),
        ('<b>4-4-5 零售日历</b>：零售月为 4 周或 5 周（周日截止），4 周与 5 周月份的'
         '净销售额绝对值<strong>不可直接环比</strong>。'),
        ('<b>核心 comp</b> = 公司披露的「剔除汽油价格变动与汇率影响」的可比销售；'
         '报告口径为未调整值。两者之差按地区拆开即 Exhibit 6。'),
        ec_note,
        (f'<b>53 周财年</b>造成个别 1 月的周数与上年同月不同（{wk_txt}）。'
         '公司披露的 comp 已按可比周调整；<strong>净销售额同比是公司报告值，'
         '其基期是同样周数的上年错位窗口</strong>，与图上相邻的柱不是同一区间。'),
        ('<b>客流与品类</b>：traffic（客流）/ ticket（客单）与品类细分不在月度新闻稿内'
         '（仅公司预录电话留言口头披露），本页只采用官网新闻稿数据，故不含该细分。'),
        ('<b>Stacks</b>（Exhibit 3 / 12）= 同一零售月过去 N 年核心 comp 之和，'
         '用于剔除单年基数扰动看趋势。'),
        cap_note_txt,
        ('<b>核对表保持官方原始单位</b>：净销售额为 $bn、comp 与 y/y 为百分比、'
         '周数与仓库数为个数，均未换算，可直接拿去和官网新闻稿逐条对。'),
        ('本页图表版式模仿 Goldman Sachs GIR exhibit 风格，仅为视觉版式，'
         '不含其研究观点或数据。仅供个人研究，不构成投资建议。'),
    ]

    Lr = df.iloc[-1]
    tail13 = [mlab(p) for p in d13.index]
    # 抬头带上核心 comp 与净销售额 y/y 的**环比方向**：只写水平值时，一个从 +8.0%
    # 掉到 +7.0% 的月份在抬头上看仍然是「+7.0%」，读者要翻到汇总表才知道在减速。
    # 抬头不该只报一个方向的事实（复查对 cme 抬头报的就是这一条）。
    mm_tc = ppdiff(sget('tc_a', cur) - sget('tc_a', prv))[0]
    mm_ns = ppdiff(sget('ns_yoy', cur) - sget('ns_yoy', prv))[0]
    headline = (f'核心 comp（除油汇）{dsp(Lr["tc_a"], 1, "%")[0]}（{mm_tc} m/m）· '
                f'报告口径 comp {dsp(Lr["tc_r"], 1, "%")[0]} · '
                f'净销售额 ${Lr["net_sales_bn"]:.2f}bn（{dsp(Lr["ns_yoy"], 1, "%")[0]} y/y，'
                f'{mm_ns} m/m）· 仓库数 {iv(Lr["wh_total"])}（US & PR {iv(Lr["wh_us"])}）')

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
        'hub_line': (f'核心 comp {dsp(Lr["tc_a"], 1, "%")[0]}（{mm_tc} m/m）· '
                     f'净销售额 ${Lr["net_sales_bn"]:.2f}bn（{dsp(Lr["ns_yoy"], 1, "%")[0]} y/y）'),
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
    print(f'53 周周数错位月份（自动识别）: {sorted(str(p) for p in WEEK_BREAKS)}'
          f' | Ex4 窗口内画线: {[str(d.index[i]) for i in b4]}')
    print('截轴（自动定界）: ' + ('无' if not capped else ', '.join(
        f'Ex{e["n"]}→{e["ycap"]:.0f}%' for e in ex if e.get('ycap') is not None)))
    print(f'Exhibit 1 汇总表 + Exhibit 2-{ex[-1]["n"]} 共 {len(ex)} 张图 + '
          f'Exhibit {table["n"]} 核对表 → {os.path.relpath(OUT, ROOT)} '
          f'({os.path.getsize(OUT) / 1024:.1f} KB)')
    print(headline)


if __name__ == '__main__':
    main()
