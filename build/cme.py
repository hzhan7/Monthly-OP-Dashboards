# -*- coding: utf-8 -*-
"""CME Group (CME) 月度成交量 —— 网页看板数据生成器（build/build_cme.py 的移植）。

原 deck：build/build_cme.py（matplotlib → PDF）。本文件把它的每一张 exhibit
重新实现成 data/cme.js 里的一个 payload 对象，页面（assets/page.js + charts.js）
只负责画，不做任何计算。

模版来源（照抄原 deck 的 docstring）：
  · Goldman Sachs「IBKR Monthly」成对图法（水平柱 + 次轴 y/y 折线 ⇄ 变化率曲线）
    与 Exhibit 7「堆叠柱 + 次轴占比线」的量能/结构同框做法
  · Barclays「IBKR July Monthly Metrics」的 day-count 调整 —— 该报告因交易日数差异，
    把「股票成交总量 +7%」修正为「按日 -5%」，方向被口径反转。CME 官方 xlsx 里
    直接给了每月交易日数，故本页用 Exhibit 3 显式呈现总量口径与按日口径的差。
数据源：CME Group IR 月度成交量 xlsx（cmegroupinc.gcs-web.com/monthly-volume），
        次月第 1-2 个工作日。费率取 series/fee_rates.csv 里的季度 RPC。

读取：  series/cme.csv、series/fee_rates.csv（唯一数据源，不读 build/data/）
输出：  data/cme.js

幂等：payload 里不放构建日期（只写文件首行注释），不用随机数，窗口一律从数据
      最新月倒推 —— 同一份 CSV 重复跑，输出逐字节相同（除首行）。
"""
import datetime
import json
import os

import numpy as np
import pandas as pd

import brief as B
import payload_guard
import pctile
import repo            # 仓库定位 + 发布日台账入口

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SERIES = os.path.join(ROOT, 'series')
OUT = os.path.join(ROOT, 'data', 'cme.js')

SRC = 'Source: CME Group monthly volume reports; format after Goldman Sachs GIR / Barclays'

# 资产类别 →（CSV 列, 图例名, 引擎色名）。
# 原 deck 的金属用 gsx.GOLD(#BF9000)，charts.js 的 C.* 里没有金色（engine_kinds.md
# 明确说了这一点）—— 后来在 charts.js 的 C.* 里补上了 GOLD(#BF9000)，与 gsx.py 同色，
# 所以金属恢复用 GOLD。不能拿 RED 当数据色：RED 在这套语言里是断点与离群值的专用色，
# 一根红柱到底是「金属品种」还是「这个点被截轴了」会分不清。
CLS = [('adv_rates_kcontracts', 'Interest rates', 'NAVY'),
       ('adv_equity_kcontracts', 'Equity index', 'MBLUE'),
       ('adv_energy_kcontracts', 'Energy', 'BLUE'),
       ('adv_ag_kcontracts', 'Agricultural', 'GRAY'),
       ('adv_fx_kcontracts', 'FX', 'GREEN'),
       ('adv_metals_kcontracts', 'Metals', 'GOLD')]

# 原 Exhibit 5「ADV by asset class」把六个品种画在同一根轴上。利率品种的峰值 21,327
# 独自定死了 0–25,000 的量程，能源 / 农产品 / 外汇 / 金属四条线全被压进 0–3,000 那条
# 窄带里互相叠着，浅蓝 / 灰 / 绿 / 金四色在那个厚度下分不出走势 —— 整张图实际只读得出
# 利率和股指两条。
# 这里按量级拆成两张：不同量级本来就不该共用一根轴。不用 ycap 的原因是截轴是给「少数
# 几个离群点」用的 —— 这里要截掉的是整整两条序列的 25 个点，那不是标注离群值，
# 是把两条主力序列全画成红圈。
CLS_MAJOR = CLS[:2]     # 利率 + 股指：5,500 – 21,300
CLS_MINOR = CLS[2:]     # 能源 / 农产品 / 外汇 / 金属：540 – 5,100

# 品种曲线图（原 Exhibit 5）拆成两张后，后面所有 exhibit 号整体后移一位。号码写死在
# 十几处图注与说明里，靠人肉数是要出错的（原 PDF 的汇总表脚注就把 Exhibit 3 写成了
# Exhibit 4），所以统一在这里定名，正文一律引用常量。
EX_ADV, EX_DAYCOUNT, EX_MIX = 2, 3, 4
EX_MAJORS, EX_MINORS = 5, 6          # 品种曲线：两大品种 / 四小品种，见下方拆图说明
EX_HIST, EX_QTR, EX_OI = 7, 8, 9
EX_RATES, EX_EQUITY, EX_ENERGY = 10, 11, 12
EX_REV, EX_RPC = 13, 14
EX_FX, EX_METALS, EX_AG = 15, 16, 17
EX_HEAT_YOY, EX_HEAT_SHARE = 18, 19
EX_TABLE = 20

WIN_BAR = 13     # gs_bar 类近期图：契约 §5.4「近期图固定 13 个月」
WIN_LINE = 25    # 曲线类图：照搬原 deck 的 win=25
WIN_QTR = 14     # 季度柱：照搬原 deck 的 win=14
HEAT_YEARS = 10  # 热力矩阵：照搬原 deck 的 n_years=10
MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
          'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
ZH_MONTH = '一二三四五六七八九十十一十二'


def mlab(p):
    """与 gsx.mlab 一致：Period('2026-07') → 'Jul-26'。"""
    return f'{MONTHS[p.month - 1]}-{p.year % 100:02d}'


def qlab(q):
    """季度 Period → '2026-Q2'，与 series/fee_rates.csv 的 period 写法一致。

    pandas 的 str(Period) 给的是 '2026Q2'，和费率表里的 '2026-Q2' 差一个连字符；
    图注要让读者能拿着这个季度号回 CSV 里直接 grep，所以统一成 CSV 的写法。
    """
    return f'{q.year}-Q{q.quarter}'


def num(v, dec=0):
    if v is None or not np.isfinite(v):
        return '—'
    return f'{v:,.{dec}f}'


def _z(v, dec):
    """把 -0.0 这类「四舍五入后其实是零」的值归零，否则会印出 '-0.0pp'。"""
    v = round(float(v), dec)
    return 0.0 if v == 0 else v


def pct(v, dec=1):
    """带符号的百分比变化，正负号交给 f-string 的 + 标志。"""
    if v is None or not np.isfinite(v):
        return '—'
    return f'{_z(v, dec):+,.{dec}f}%'


def pp(v, dec=1):
    """百分点差（比率类指标的差异一律用 pp）。"""
    if v is None or not np.isfinite(v):
        return '—'
    return f'{_z(v, dec):+.{dec}f}pp'


def L(a):
    """序列 → JSON 安全的 float 列表（NaN → None）。"""
    return [None if v is None or not np.isfinite(float(v)) else round(float(v), 6) for v in a]


# ══════════════════════════ 1. 读数据（只读 series/*.csv）══════════════════════════
def load():
    p = os.path.join(SERIES, 'cme.csv')
    df = pd.read_csv(p)
    need = ['month', 'adv_total_kcontracts', 'oi_total_contracts', 'trading_days'] + \
           [c for c, _, _ in CLS]
    miss = [c for c in need if c not in df.columns]
    if miss:                                     # 失败要响：绝不静默写 NaN 上线
        raise SystemExit(f'series/cme.csv 缺列 {miss}')
    df['month'] = pd.PeriodIndex(df['month'], freq='M')
    df = df.set_index('month').sort_index()
    gaps = [(df.index[i] - df.index[i - 1]).n for i in range(1, len(df))]
    if set(gaps) != {1}:
        bad = [str(df.index[i]) for i in range(1, len(df)) if (df.index[i] - df.index[i - 1]).n != 1]
        raise SystemExit(f'series/cme.csv 月份不连续，断在 {bad}')
    for c in need[1:]:
        if df[c].isna().any():
            raise SystemExit(f'series/cme.csv 的 {c} 有缺值，无法画连续序列')
    return df.astype(float)


def rpc_quarterly(metrics):
    """从 series/fee_rates.csv 取 CME 的季度 RPC（$/张）。"""
    d = pd.read_csv(os.path.join(SERIES, 'fee_rates.csv'))
    d = d[d['company'] == 'CME']
    out = {}
    for key, metric in metrics:
        s = d[d['metric'] == metric]
        if not len(s):
            raise SystemExit(f'fee_rates.csv 里没有 CME/{metric}')
        u = set(s['unit'].dropna())
        if u != {'USD_per_contract'}:
            raise SystemExit(f'CME/{metric} 单位不是 USD_per_contract：{u}')
        q = pd.PeriodIndex(s['period'].str.replace('-', ''), freq='Q')
        out[key] = pd.Series(s['value'].astype(float).values, index=q).sort_index()
    return out


def to_monthly(rate_q, month_index):
    """季度费率 → 月度：当季各月用该季费率；最新季之后沿用最后一个已知值（同 bridge.to_monthly）。"""
    q = pd.PeriodIndex(month_index).asfreq('Q')
    return pd.Series([rate_q.get(qq, np.nan) for qq in q], index=month_index, dtype=float).ffill()


# ══════════════════════════ 2. 派生序列（照抄原 deck 的算法）══════════════════════════
df = load()
adv = df['adv_total_kcontracts']
days = df['trading_days']
LATEST = df.index[-1]

df['total_vol_mn'] = adv * days / 1000.0                    # 月度总成交量 = ADV x 交易日（百万张）
df['adv_mn'] = adv / 1000.0
df['oi_total_mn'] = df['oi_total_contracts'] / 1e6
df['vol_yoy'] = df['total_vol_mn'].pct_change(12) * 100
df['adv_yoy'] = adv.pct_change(12) * 100
df['daycount_effect'] = df['vol_yoy'] - df['adv_yoy']       # 两者之差 = 交易日数贡献
df['rates_share'] = df['adv_rates_kcontracts'] / adv * 100

RPC = rpc_quarterly([('total', 'rpc_total'), ('rates', 'rpc_interest_rates'),
                     ('equity', 'rpc_equity_indexes'), ('energy', 'rpc_energy'),
                     ('metals', 'rpc_metals')])
rpc_m = to_monthly(RPC['total'], df.index)
df['implied_txn_rev_usdmn'] = df['total_vol_mn'] * rpc_m    # 百万张 x $/张 = $mn
RPC_Q, RPC_V = RPC['total'].index[-1], float(RPC['total'].iloc[-1])

# ══════════ 费率期间披露 ══════════
# 成交量按月往前走，RPC 一个季度才更新一次 —— 所以「最新一两个月的隐含值用的是上一季
# 费率」是本页的常驻口径，不是 bug。但页面此前只说了「最新季之后沿用」，没说清本月究竟
# 挂在哪一季上，读者无从判断这个隐含收入落后多少。下面几行把期间算出来写进图注。
#
# 季度号一个都不许写死：写死的话下季度这句话就自动变成假话（本仓踩过 schw「过去 32 个
# 季度单边降」、cost「Exhibit 4 画了红线」两次同类坑）。全部由 df.index 与
# fee_rates.csv 现算，随数据自动滚动。
CUR_Q = LATEST.asfreq('Q')            # 本页最新数据月所在的季度
RPC_LAG = (CUR_Q - RPC_Q).n           # 费率比数据月落后几个季度；正常节奏 = 1
# 落在最新可得费率季度之后的月份 —— 这些月的隐含值是拿上一季费率外推出来的
CARRY = [p for p in df.index if p.asfreq('Q') > RPC_Q]
# 统一收尾在中文字上（「…这 N 个月」），后面无论接「尚无」还是「的隐含值」都不留半角缝
_CARRY_TXT = ('' if not CARRY else
              f'{mlab(CARRY[0])} 这 1 个月' if len(CARRY) == 1 else
              f'{mlab(CARRY[0])}–{mlab(CARRY[-1])} 这 {len(CARRY)} 个月')

# 正常节奏（RPC_LAG == 1，本季用上一季费率）只陈述期间；落后两季及以上要显式示警。
RATE_PERIOD = (
    f'<b>费率期间</b>：本页数据截至 {mlab(LATEST)}（{qlab(CUR_Q)}），费率取 CME 季报披露的 '
    f'{qlab(RPC_Q)} 值（总 RPC ${RPC_V:.3f}），这是目前可得的最新一季。'
    + (f'{qlab(RPC_Q)} 及以前各月用其所属季度的实际披露费率；{_CARRY_TXT}尚无对应季度费率，'
       f'沿用 {qlab(RPC_Q)} 的 ${RPC_V:.3f} 推算。' if CARRY else
       f'本页每个月都落在已披露费率的季度内，没有任何一个月是沿用上一季费率。'))

RATE_STALE = ('' if RPC_LAG < 2 else
              f'<b>⚠ 费率已过期</b>：按正常节奏，{qlab(CUR_Q)} 的月份至少应当能用上 '
              f'{qlab(CUR_Q - 1)} 的费率，但 fee_rates.csv 里最新只到 {qlab(RPC_Q)}，'
              f'比正常节奏又老了 {RPC_LAG - 1} 个季度（多半是官方季报延迟）。'
              f'{_CARRY_TXT}的隐含值因此建立在 {RPC_LAG} 个季度以前的费率上；'
              f'期间若发生品种结构位移或定价调整，本图会系统性偏离，'
              f'费率补齐后这些月份的数值会被改写。')

BR_NOTE = ('Assumption: monthly transaction revenue = contracts traded x average rate per contract '
           f'({qlab(RPC_Q)} = ${RPC_V:.3f}, held flat after). CME derives RPC from reported revenue, so '
           'closed quarters reconstruct a known total — the value is the current quarter. '
           '费率是季度值，当季各月共用该季 RPC，最新季之后沿用；品种结构变化会让混合 RPC 偏离，'
           f'见 Exhibit {EX_RPC}。'
           + RATE_PERIOD + RATE_STALE)

W13 = df.index[-WIN_BAR:]
W25 = df.index[-WIN_LINE:]
XL13 = [mlab(p) for p in W13]
XL25 = [mlab(p) for p in W25]
XL_LONG = [mlab(p) for p in df.index]


def win(col, n):
    return df[col].iloc[-n:].values


# ══════════════════════════ 3. Exhibit 1：汇总表 ══════════════════════════
CUR, PRV, YAG = LATEST, LATEST - 1, LATEST - 12

# 第 5 个字段 cal=True → 纯日历行：m/m 与 y/y 不着色、分位整格留空。
# 交易日数是月历的产物（22 天 vs 21 天纯粹因为 7 月比 6 月多一个工作日），不是经营结果：
# 「+4.8% 涂绿、分位 69 涂绿」等于说多一个交易日是好消息，与本表注
# 「ADV is already day-count neutral」的立场自相矛盾。数值仍然要给 —— 读者要拿它复核
# Exhibit 3 的 day-count 口径差 —— 只是不做好坏判断。
SUM_ROWS = [
    ('group', 'Average daily volume (k contracts)', None, None, False),
    ('row', 'Total ADV', 'adv_total_kcontracts', 0, False),
    ('row', 'Interest rates', 'adv_rates_kcontracts', 0, False),
    ('row', 'Equity index', 'adv_equity_kcontracts', 0, False),
    ('row', 'Energy', 'adv_energy_kcontracts', 0, False),
    ('row', 'Agricultural', 'adv_ag_kcontracts', 0, False),
    ('row', 'FX', 'adv_fx_kcontracts', 0, False),
    ('row', 'Metals', 'adv_metals_kcontracts', 0, False),
    ('group', 'Volume and open interest', None, None, False),
    ('row', 'Total contracts traded (mn)', 'total_vol_mn', 1, False),
    ('row', 'Month-end open interest (mn)', 'oi_total_mn', 1, False),
    ('row', 'Trading days', 'trading_days', 0, True),
]

BLANK_PCTILE = []      # summary() 里逐行记下留空原因，供表注引用


def summary():
    """3Y %ile 一律走 build/pctile.py（全站唯一实现）。

    本文件原先自带一份 `pctile36()`，判据是「逐月不降的月份占比 ≥ 90% 就留空」。
    那个代理量测的是序列形状，不是分位列本身有没有区分度，所以既拦不住「上下波动但
    分位常年钉 100」的行，各页各写一份还会让同一条序列在两页判定相反。分位是口径，
    口径只能有一处定义 —— 这里只负责「本页自己的口径原因」（交易日数是日历产物）。
    """
    rows = []
    for kind, label, col, dec, cal in SUM_ROWS:
        if kind == 'group':
            rows.append({'kind': 'group', 'label': label})
            continue
        s = df[col]
        c, p1, p12 = float(s[CUR]), float(s[PRV]), float(s[YAG])
        mm = (c / p1 - 1) * 100 if p1 else np.nan
        yy = (c / p12 - 1) * 100 if p12 else np.nan

        def sign(v):
            if cal:                       # 日历行不做好坏判断
                return ''
            return 'pos' if v > 0 else ('neg' if v < 0 else '')

        cells = [{'v': num(c, dec)}, {'v': num(p1, dec)}, {'v': num(p12, dec)},
                 {'v': pct(mm), 'cls': sign(mm)}, {'v': pct(yy), 'cls': sign(yy)}]
        if cal:
            cells.append({'v': ''})
            BLANK_PCTILE.append((label, '交易日数由月历决定，与 CME 的经营无关，'
                                        '其分位只是在 0 与 91 之间随月长震荡'))
        else:
            q, cls = pctile.cell(L(s.values), -1)
            cells.append({'v': q, 'cls': cls})
            if not q:
                BLANK_PCTILE.append((label, pctile.why_blank(L(s.values)) or '样本不足'))
        rows.append({'label': label, 'cells': cells})

    blank = '；'.join(f'{lab} —— {why}' for lab, why in BLANK_PCTILE)
    return {
        'title': f'CME Group monthly volume summary — {mlab(CUR)}',
        'heads': [f'本月 {mlab(CUR)}', f'上月 {mlab(PRV)}', f'去年同月 {mlab(YAG)}',
                  'm/m', 'y/y', '3Y %ile'],
        'sep': 3,
        'rows': rows,
        'note': ('ADV is already day-count neutral; total contracts traded is not. '
                 f'Exhibit {EX_DAYCOUNT} isolates the difference.（原 PDF 此处误写作 '
                 f'Exhibit 4 —— 汇总表本身占 Exhibit 1，day-count 图是 Exhibit '
                 f'{EX_DAYCOUNT}。）'
                 '3Y %ile = 当月读数在最近 36 个月里高于多少百分比的观测，判据见'
                 '「口径与方法说明」第 7 条。'
                 + (f'本表留空的行：{blank}。' if blank else '本表没有留空的分位。')
                 + '「Trading days」行的 m/m 与 y/y 只给数字、不着色，理由同上。'
                 '全部为 CME 官方披露值，无推导。'),
    }


# ══════════════════════════ 4. Exhibit 2..19 ══════════════════════════
def yoy_line(col, win_n=WIN_BAR):
    """次轴同比序列，口径逐条照抄 gsx.lvl_bar（基数过小或异号就放弃该点）。

    引擎不替我们算同比 —— 「这一点的同比有没有意义」是口径判断，只能在 Python 侧做。
    """
    v = df[col].values
    scale = float(np.nanmedian(np.abs(v))) or 1.0
    out = np.full(len(v), np.nan)
    for i in range(12, len(v)):
        a, b = v[i], v[i - 12]
        if not (np.isfinite(a) and np.isfinite(b)):
            continue
        if abs(b) < 0.15 * scale or a * b < 0:
            continue                      # 基数过小 / 异号 → 同比无意义，宁可断线
        out[i] = (a / b - 1) * 100
    return L(out[-win_n:])


def gs_bar(n, col, title, ylab, fmt, legend, note=None, src_extra=None):
    """← gsx.lvl_bar：浅蓝柱 + **次轴金色 y/y 折线**。窗口 13 个月（契约 §5.4）。

    次轴画的是同比而不是 12 个月滚动均线 —— gsx.lvl_bar 的 docstring 写死了这条理由：
    「均线只是把柱子再平滑一遍、不带新信息，同比才回答『相对去年这个月是好是坏』」。
    本页九张 gs_bar 全部由 build_cme.py 的 gsx.lvl_bar 移植而来，所以与 deck 对齐：
    给 yoy 就不画均线（引擎侧自动），同时不再需要左上角那个 y/y 气泡。
    """
    ex = {'n': n, 'kind': 'gs_bar', 'title': title, 'fmt': fmt, 'ylab': ylab,
          'ylab2': '% y/y', 'legend': legend, 'values': L(win(col, WIN_BAR)),
          'yoy': {'name': 'y/y (RHS)', 'color': 'GOLD', 'yfmt': 'pct0',
                  'values': yoy_line(col)}}
    if note:
        ex['note'] = note
    if src_extra:
        ex['src_extra'] = src_extra
    return ex


ex = []

ex.append(gs_bar(EX_ADV, 'adv_mn', 'Total average daily volume', 'mn contracts / day', 'f1',
                 'Total ADV'))

ex.append({
    'n': EX_DAYCOUNT, 'kind': 'lines_endlabels', 'fmt': 'f1', 'xlabels': XL25,
    'title': 'Total volume vs. ADV growth: the day-count gap',
    'ylab': '% y/y', 'zero_line': True,
    'series': [
        {'name': 'Total contracts y/y', 'color': 'GRAY', 'values': L(win('vol_yoy', WIN_LINE))},
        {'name': 'ADV y/y (day-count neutral)', 'color': 'NAVY',
         'values': L(win('adv_yoy', WIN_LINE))},
    ],
    'src_extra': ('Gap between the two lines is purely the change in trading days — '
                  'the Barclays adjustment'),
    'note': (f'{mlab(CUR)}：总成交 {pct(df["vol_yoy"][CUR])} y/y，按日 {pct(df["adv_yoy"][CUR])} y/y，'
             f'交易日数贡献 {pp(float(df["daycount_effect"][CUR]))}'
             f'（{days[CUR]:.0f} 天 vs 去年同月 {days[YAG]:.0f} 天）。'),
})

_stack13 = {c: win(c, WIN_BAR) for c, _, _ in CLS}
_share13 = (win('adv_rates_kcontracts', WIN_BAR) + win('adv_equity_kcontracts', WIN_BAR)) \
    / win('adv_total_kcontracts', WIN_BAR) * 100
# 右轴上界取 10 的整数倍：占比线要压在堆叠柱之上，太高会掉进柱子里
_ymax = float(np.ceil(np.nanmax(_share13) / 10.0) * 10)
if np.nanmax(_share13) / _ymax > 0.995:
    _ymax += 10
ex.append({
    'n': EX_MIX, 'kind': 'stacked_dual', 'fmt': 'f0c', 'xlabels': XL13,
    'title': 'ADV mix by asset class',
    'ylab': 'k contracts / day', 'ylab2': '% rates + equity',
    'stacks': [{'name': nm, 'color': cl, 'values': L(_stack13[c])} for c, nm, cl in CLS],
    'line': {'name': '% rates + equity (RHS)', 'color': 'GREEN',
             'values': L(_share13), 'ymax': _ymax, 'yfmt': 'pct0'},
    'note': ('六个品种加总即披露的 Total ADV（CME 的品种划分是穷尽且互斥的）。'
             '右轴是利率 + 股指两大品种占总 ADV 的比重 —— 体量与结构同框，'
             f'总量持平但结构位移一样会改变混合费率（见 Exhibit {EX_RPC}）。'),
})

_SPLIT_NOTE = (f'原 PDF 把六个品种画在同一根轴上，利率品种的峰值 '
               f'{df["adv_rates_kcontracts"].iloc[-WIN_LINE:].max():,.0f} 独自定死了量程，'
               f'能源 / 农产品 / 外汇 / 金属四条线被压成底部一条带、彼此分不开。'
               f'这里按量级拆成 Exhibit {EX_MAJORS}（两大品种）与 Exhibit {EX_MINORS}'
               f'（四个小品种）两张，窗口、口径、配色一律不变，一个点也没有删；'
               f'两张图的纵轴刻度不同，跨图比高度是没有意义的，要比绝对量请回 '
               f'Exhibit {EX_MIX} 的堆叠柱或末尾核对表。')

ex.append({
    'n': EX_MAJORS, 'kind': 'lines_endlabels', 'fmt': 'f0c', 'xlabels': XL25,
    'title': 'ADV by asset class: rates and equity index',
    'ylab': 'k contracts / day',
    'series': [{'name': nm, 'color': cl, 'values': L(win(c, WIN_LINE))}
               for c, nm, cl in CLS_MAJOR],
    'note': _SPLIT_NOTE,
})

ex.append({
    'n': EX_MINORS, 'kind': 'lines_endlabels', 'fmt': 'f0c', 'xlabels': XL25,
    'title': 'ADV by asset class: energy, ag, FX and metals',
    'ylab': 'k contracts / day',
    'series': [{'name': nm, 'color': cl, 'values': L(win(c, WIN_LINE))}
               for c, nm, cl in CLS_MINOR],
    'note': (f'与 Exhibit {EX_MAJORS} 同一份数据、同一个 {WIN_LINE} 个月窗口，'
             f'只是把量级差一个数量级的四个小品种单独放到自己的轴上。'
             f'注意纵轴上界只有 Exhibit {EX_MAJORS} 的约五分之一。'),
})

ex.append({
    'n': EX_HIST, 'kind': 'lines', 'x': 'long', 'full': True, 'height': 300,
    'fmt': 'f1', 'yfmt': 'f0', 'xstep': 12, 'xrot': 90, 'zero_line': True,
    'title': 'Full ADV history since 2008', 'ylab': 'mn contracts / day',
    'series': [{'name': 'Total ADV', 'color': 'NAVY', 'values': L(df['adv_mn'].values)}],
    'src_extra': f'Full disclosed history: {mlab(df.index[0])} – {mlab(LATEST)}（{len(df)} 个月）',
    'note': ('原 PDF 在末端画了一个红色虚线椭圆圈出最近 3 个月，网页引擎没有对应的注解图元，'
             f'故未移植；最近 {WIN_BAR} 个月的读数见 Exhibit {EX_ADV} 与末尾核对表。'),
})

_qs = df['total_vol_mn'].groupby(df.index.asfreq('Q')).agg(['sum', 'count'])
_qv = _qs['sum'].values
_qyoy = np.array([(_qv[i] / _qv[i - 4] - 1) * 100 if i >= 4 and _qv[i - 4] else np.nan
                  for i in range(len(_qv))])
_npart = int(_qs['count'].iloc[-1])
ex.append({
    'n': EX_QTR, 'kind': 'qtr_bar', 'fmt': 'f0c', 'label_fmt': 'f0c',
    'xlabels': [str(p) for p in _qs.index[-WIN_QTR:]],
    'title': 'Contracts traded aggregated to quarters', 'ylab': 'mn contracts',
    'ylab2': '% y/y',
    'values': L(_qv[-WIN_QTR:]),
    'partial_months': _npart, 'qtr_months': 3,
    'line': {'name': 'y/y (RHS)', 'color': 'GREEN', 'values': L(_qyoy[-WIN_QTR:]),
             'yfmt': 'pct0'},
    'src_extra': 'Latest bar is quarter-to-date and not comparable to full quarters',
    'note': (f'季度合计 = 该季各月「ADV x 当月交易日」之和，在 Python 侧算好。'
             f'末柱 {_qs.index[-1]} 只含 {_npart} 个月（浅蓝），其右轴 y/y 已被作废 —— '
             '拿未满季去比上年完整季必然砸出一个假坑。'
             # 绿线末端那个读数的标签由引擎固定右移 5px，窄屏下会飘到 QTD 柱上方，
             # 容易被读成 QTD 那一期的同比。把它归属的季度写死在图注里，读者不必靠像素判断。
             f'因此绿线的最后一个读数 {pct(_qyoy[-2], 0)} 属于 {_qs.index[-2]}'
             f'（最后一个完整季），不是 {_qs.index[-1]}。'),
})

ex.append(gs_bar(EX_OI, 'oi_total_mn', 'Month-end total open interest', 'mn contracts', 'f1',
                 'Month-end OI',
                 note='月末未平仓合约是存量口径（期末快照），与 ADV 这类流量口径不可直接相加。'))
ex.append(gs_bar(EX_RATES, 'adv_rates_kcontracts', 'Interest-rate complex ADV',
                 'k contracts / day', 'f0c', 'Interest rates ADV'))
ex.append(gs_bar(EX_EQUITY, 'adv_equity_kcontracts', 'Equity-index complex ADV',
                 'k contracts / day', 'f0c', 'Equity index ADV'))
ex.append(gs_bar(EX_ENERGY, 'adv_energy_kcontracts', 'Energy complex ADV',
                 'k contracts / day', 'f0c', 'Energy ADV'))
ex.append(gs_bar(EX_REV, 'implied_txn_rev_usdmn', 'Implied transaction revenue', '$mn / month',
                 'usd0', 'Implied transaction revenue', note=BR_NOTE))

_rq = RPC['total'].index[-WIN_QTR:]
# 四条品种曲线各自的最新可得季度未必与总 RPC 同步（某一季只补了一部分品种时会脱节），
# 脱节的那条曲线在末端会断开。差异现算，不写死品种名与季度号。
_RPC_ZH = {'total': '总 RPC', 'rates': '利率', 'equity': '股指', 'energy': '能源',
           'metals': '金属'}
_rpc_behind = [(k, RPC[k].index[-1]) for k in ('rates', 'equity', 'energy', 'metals')
               if RPC[k].index[-1] != RPC_Q]
_RPC_SYNC = ('' if not _rpc_behind else
             '注意四条曲线并未同步：'
             + '、'.join(f'{_RPC_ZH[k]}最新只到 {qlab(q)}' for k, q in _rpc_behind)
             + f'（其余为 {qlab(RPC_Q)}），末端断开处即缺该季披露。')
ex.append({
    'n': EX_RPC, 'kind': 'lines_endlabels', 'fmt': 'usd2',
    'xlabels': [mlab(q.asfreq('M', 'end')) for q in _rq],
    'title': 'Rate per contract by asset class', 'ylab': '$ per contract',
    'series': [
        {'name': 'Interest rates', 'color': 'NAVY', 'values': L(RPC['rates'].reindex(_rq).values)},
        {'name': 'Equity index', 'color': 'MBLUE', 'values': L(RPC['equity'].reindex(_rq).values)},
        {'name': 'Energy', 'color': 'BLUE', 'values': L(RPC['energy'].reindex(_rq).values)},
        {'name': 'Metals', 'color': 'GOLD', 'values': L(RPC['metals'].reindex(_rq).values)},
    ],
    'src_extra': ('RPC differs several-fold across complexes, so a volume mix shift moves blended '
                  'revenue even when total ADV is flat. This is the main uncertainty in the bridge '
                  'above.'),
    'note': (f'季度值，x 轴标的是各季末月（{mlab(_rq[0].asfreq("M", "end"))} = 1Q{_rq[0].year % 100:02d}，'
             f'最新为 {qlab(RPC_Q)}）。'
             f'{mlab(_rq[-1].asfreq("M", "end"))}：利率 ${RPC["rates"].iloc[-1]:.3f}、'
             f'股指 ${RPC["equity"].iloc[-1]:.3f}、能源 ${RPC["energy"].iloc[-1]:.3f}、'
             f'金属 ${RPC["metals"].iloc[-1]:.3f} —— 图上按 $0.01 显示（原 PDF 为 $0.001），'
             '第三位小数以此注为准。' + _RPC_SYNC
             # 本图本身只画季度费率、不跨月外推，但它是 EX_REV 那张隐含收入桥的费率来源，
             # 所以同一句期间披露在这里也要出现：读者看到曲线停在哪一季，就知道隐含收入
             # 那张图的最新一两个月是拿哪一季的费率算的。
             + f'本图曲线止于 {qlab(RPC_Q)}，Exhibit {EX_REV} 的隐含收入即以此季费率为准。'
             + RATE_PERIOD + RATE_STALE),
})

ex.append(gs_bar(EX_FX, 'adv_fx_kcontracts', 'FX complex ADV', 'k contracts / day', 'f0c', 'FX ADV'))
ex.append(gs_bar(EX_METALS, 'adv_metals_kcontracts', 'Metals complex ADV', 'k contracts / day', 'f0c',
                 'Metals ADV'))
ex.append(gs_bar(EX_AG, 'adv_ag_kcontracts', 'Agricultural complex ADV', 'k contracts / day', 'f0c',
                 'Agricultural ADV'))


def heat(n, col, title, src_extra, fmt='pct0', legend=None):
    s = df[col].dropna()
    yrs = sorted({p.year for p in s.index})[-HEAT_YEARS:]
    M = [[None] * 12 for _ in yrs]
    for p, v in s.items():
        if p.year in yrs:
            M[yrs.index(p.year)][p.month - 1] = round(float(v), 6)
    return {'n': n, 'kind': 'heat_matrix', 'full': True, 'title': title, 'fmt': fmt,
            'rows': [str(y) for y in yrs], 'cols': MONTHS, 'matrix': M,
            'legend': legend or title, 'cell_h': 20, 'row_lab_w': 38, 'row_head': '年',
            'src_extra': src_extra}


# fmt 用 pct0z 而不是 pct0：pct0 会把 −0.4% 印成「-0%」（一个不存在的数）。
# 当前 10 年窗口里恰好没有落在 ±0.5% 内的月份，但 y/y 序列每月都在动，这是迟早会命中的
# 格式坑，先按 pct0z 钉住（|v| < 0.5 → 0）。
ex.append(heat(EX_HEAT_YOY, 'adv_yoy', 'Total ADV y/y growth (%)',
               'Green = faster y/y growth, red = slower', fmt='pct0z',
               legend='Total ADV y/y'))
ex.append(heat(EX_HEAT_SHARE, 'rates_share', 'Interest-rate share of total ADV (%)',
               'Rates is the largest and most rate-cycle-sensitive complex',
               legend='Rates share of ADV'))

# ══════════════════════════ 5. Exhibit 20：核对表（官方原始单位）══════════════════════════
TBL_COLS = [('Total ADV (k)', 'adv', 'adv_total_kcontracts', 3),
            ('Rates (k)', 'rates', 'adv_rates_kcontracts', 3),
            ('Equity (k)', 'eq', 'adv_equity_kcontracts', 3),
            ('Energy (k)', 'en', 'adv_energy_kcontracts', 3),
            ('Ag (k)', 'ag', 'adv_ag_kcontracts', 3),
            ('FX (k)', 'fx', 'adv_fx_kcontracts', 3),
            ('Metals (k)', 'me', 'adv_metals_kcontracts', 3),
            ('Open interest (contracts)', 'oi', 'oi_total_contracts', 0),
            ('Trading days', 'days', 'trading_days', 0)]
table = {
    'n': EX_TABLE, 'title': '近 13 个月月度指标核对表（官方原始单位，未换算）', 'idx': '月份',
    'cols': [[h, k] for h, k, _, _ in TBL_COLS],
    'rows': [dict({'xl': mlab(p)},
                  **{k: num(float(df[c][p]), d) for _, k, c, d in TBL_COLS})
             for p in W13],
}

# ══════════════════════════ 6. 口径与方法说明 ══════════════════════════
NOTES = [
    f'<b>数据源与节奏。</b>CME Group IR 月度成交量 xlsx（cmegroupinc.gcs-web.com/monthly-volume），'
    f'次月第 1-2 个工作日发布。本页覆盖 {mlab(df.index[0])} – {mlab(LATEST)} 共 {len(df)} 个连续月，'
    f'无缺月；ADV、未平仓合约、交易日数三项均为公司直接披露，未经加工。',

    '<b>版式出处。</b>Goldman Sachs「IBKR Monthly」的成对图法（水平柱 + 次轴 y/y 折线）'
    '与其 Exhibit 7「堆叠柱 + 次轴占比线」的量能/结构同框做法；day-count 那张图取自 Barclays'
    '「IBKR July Monthly Metrics」。',

    '<b>ADV 与总量的口径差（Barclays 调整）。</b>ADV 本身已按交易日中性化，总成交合约数没有。'
    'Barclays 那份报告因交易日数差异，把「股票成交总量 +7%」修正为「按日 -5%」，方向被口径整个反转。'
    f'Exhibit {EX_DAYCOUNT} 把两条同比并排画出来，两线之差纯粹是交易日数的变化；'
    '月度总成交量 = ADV × 当月交易日数，这一步换算是本页做的，不是公司披露的单独口径。'
    '汇总表末行的「Trading days」同理只是月历读数，所以它的 m/m、y/y 不着色、3Y %ile 留空 —— '
    '多一个交易日既不是好消息也不是坏消息。',

    f'<b>唯一的推导值：Exhibit {EX_REV}。</b>Implied transaction revenue = 当月成交合约数 × '
    f'每张平均费率（RPC）。RPC 是季度值（CME 季报），当季各月共用该季费率，'
    f'最新季（{qlab(RPC_Q)} = ${RPC_V:.3f}）'
    '之后沿用。CME 的 RPC 本身是用已披露收入倒推的，所以已收官季度只是把一个已知总额重建一遍 —— '
    '这张图的价值全在<b>当前未收官的季度</b>。标题带 Implied 即表示非公司披露值。'
    # 「用的是哪一季费率」随每月新数据自动变化，所以这句由数据现算，不写死季度号。
    + RATE_PERIOD + RATE_STALE,

    f'<b>RPC 的口径风险。</b>各品种 RPC 相差数倍（Exhibit {EX_RPC}），因此总 ADV 不变、'
    f'只要品种结构位移，混合费率与隐含收入照样会动。这是上面那座桥最大的不确定性，'
    f'也是 Exhibit {EX_MIX} 把结构与体量画在同一张图里的原因。',

    f'<b>未满季不可直读。</b>Exhibit {EX_QTR} 的末柱是季度至今（{_qs.index[-1]} 目前只含 '
    f'{_npart} 个月），'
    '用浅蓝标出，其右轴 y/y 的最后一点被引擎强制作废 —— 拿未满季的累计去比上年完整季，'
    '必然砸出一个纯口径造成的假坑。',

    '<b>汇总表的 3Y %ile。</b>= 当月读数在最近 36 个月里高于多少百分比的观测，'
    '由全站唯一的一份实现（<code>build/pctile.py</code>）算出，本页不再自带判据 —— '
    '各页各写一份，正是同一条序列在两页判定相反的原因。'
    '留空的判据是「把这一列在过去 24 个月里逐月回放一遍，若 ≥70% 的月份都钉在 100 或 0，'
    '这一列对这一行没有区分度」；旧判据「≥90% 的月环比不降」测的是序列形状而不是分位列本身，'
    '拦不住「上下波动但分位常年钉 100」的行。'
    '本页另有一处按自己的口径留空：Trading days 是日历产物（见第 3 条）。'
    '比率类指标的差异一律用 pp/bp；本页汇总表里没有比率行，故全部是百分比变化。',

    '<b>口径断点：本页没有，图上也确实一条都没画。</b>CME 的 ADV / 未平仓合约 / 交易日口径'
    f'自 {mlab(df.index[0])} 至今保持一致，品种六分类穷尽且互斥，所以全页没有红色竖虚线断点，'
    '相邻期可以直读 —— 本页任何一处图注都没有声称过存在断点线，说的和画的一致。'
    '若日后出现并购并表或品种重分类，必须在这里登记、给对应 exhibit 传 break_at 画出竖线，'
    '并在断点滚出窗口后让图注文案一起消失，不能只靠图注文字提一句、也不能因为断点滚出窗口就报错停更。',

    '<b>与原 PDF 版的有意差异（四处）。</b>'
    '(a) gs_bar 类近期图的窗口由 25 个月收到 13 个月 —— 契约 §5.4 的规定；次轴那条金色 y/y '
    '折线与 deck 的 gsx.lvl_bar 一致（deck 的 docstring：「均线只是把柱子再平滑一遍、'
    '不带新信息」），网页版一度改画 12 个月均线，现已改回同比。'
    f'曲线类（Exhibit {EX_DAYCOUNT}/{EX_MAJORS}/{EX_MINORS}）与长历史图（Exhibit {EX_HIST}）'
    '的窗口一字未改。'
    f'(b) deck 的品种曲线图把六个品种画在一根轴上，利率品种的峰值把其余四条压成底部一条带；'
    f'网页版按量级拆成 Exhibit {EX_MAJORS} 与 Exhibit {EX_MINORS} 两张，数据、窗口、配色全同，'
    f'没有删点、没有截轴（详见两图图注）。'
    '(c) 金属品种在 deck 里用金色 #BF9000，网页引擎的调色板后来补齐了同一个金色，'
    '所以两边同色；红色在本站是断点与离群值的专用色，不拿来当数据色。'
    f'(d) Exhibit {EX_HIST} 的「最近 3 个月红色虚线圈」与 Exhibit {EX_RPC} 的第三位小数'
    '无对应实现，前者说明写进图注，后者的精确值写进图注。',

    f'<b>核对表（Exhibit {EX_TABLE}）用官方原始单位，不做任何换算</b>：ADV 为千张/日、'
    '未平仓合约为张、交易日为天，可直接与 CME 月度 xlsx 逐格对。'
    '图上的「百万张」「百万美元」都是本页换算后的口径，核对时请以核对表为准。',
]

# ══════════════════ 6.5 页顶 brief：读数该怎么读（规则库 build/brief.py）══════════════════
# 品种三元组：(ADV 列, 中文名, 对应的月末持仓列)。
# 这里原先还带着「该品种 ADV 的 exhibit 号」，供 brief 里那句「Exhibit 12 那根涨柱是换手
# 不是建仓」用。那半句已经删掉（一句话一个意思，品类那句的落点是量与仓，不是导航），
# 号码字段随之成了死数据 —— 留着只会让下一个人以为正文里还引着 exhibit 号。
CLS_BRIEF = [('adv_rates_kcontracts', '利率', 'oi_rates_contracts'),
             ('adv_equity_kcontracts', '股指', 'oi_equity_contracts'),
             ('adv_energy_kcontracts', '能源', 'oi_energy_contracts'),
             ('adv_ag_kcontracts', '农产品', 'oi_ag_contracts'),
             ('adv_fx_kcontracts', '外汇', 'oi_fx_contracts'),
             ('adv_metals_kcontracts', '金属', 'oi_metals_contracts')]

# 电子化占比与分品种持仓这两组列 load() 没有校验（它只管画图要用的那几列），而 brief 要用。
# 这里区分两种「缺」，处理方式相反：
#   · **列不在** = 数据管道坏了，直接响。不静默少一句话：少掉的那一句在页面上没有任何痕迹。
#   · **列在、某个月是 NaN** = 常态，不是故障（CME 的 2021-04 整月没拆 Globex 电子成交／
#     公开喊价／场外协议三列，CSV 里就是空的）。这属于 brief.py::need() 管的事：把用到那个
#     格子的半句降级成「哪个月缺了什么」，既不静默少一句、也不为一句解读让整页发不出去。
#     原实现只查列名，于是 2021-04（分子缺）与 2022-04（它的 i-12 缺）两个月分别抛
#     TypeError 与 KeyError，整页构建失败且不给任何口径提示。
_BRIEF_COLS = ['adv_globex_electronic_kcontracts'] + [o for _, _, o in CLS_BRIEF]
_miss_brief = [c for c in _BRIEF_COLS if c not in df.columns]
if _miss_brief:
    raise SystemExit(f'series/cme.csv 缺 brief 需要的列 {_miss_brief}')


def compose_brief(months, adv, oi, gx, cls):
    """CME 页顶部的 ~300 字数据总结（payload 的 `brief` 字段）。

    规则库在 `build/brief.py`（R1 峰值扫描 / R2 基数护栏 / R3 日历护栏 / R4 单位恒等 /
    R5 标注 / R6 有效位）：那边只算事实，句子在这里拼 —— 措辞是口径的一部分，属于各家自己。
    职责与 `headline` 互补：那一行给读数，这一段给「读数该怎么读」。

    ═══ 分寸以 build/ibkr.py 的 compose_brief() 为准（既是上限也是下限）═══
    四句四个层次，每句一个意思。ibkr 那版是 规模 / 基数 / 日历 / 分母；本页第三层的
    「日历」用不了（见下），换成 CME 自己那层独有的信息——**品类的量与仓**：

        s1 规模：两个总量（成交与持仓）在全样本里的位置，谁创了新高、谁的峰值停在哪个月
        s2 基数：环比与同比反号时，上月在全样本里排第几（不给这个会把回落读成转向）
        s3 品类：六个品种里 ADV 上行、月末持仓收缩各几个，两头都占的是谁
        s4 分母：电子化占比（推导值）+ R4 的两个增速之商 + 一句落点

    第一版这里是五层，多出来的一句是「口径分层：ADV 是流量、月末持仓是时点存量……
    互不印证」——那是写给构建者看的方法论议论，不是导读；总持仓的位置与峰值已经在 s1 里，
    删的只是那句议论，分支判断（谁创新高／峰值停在哪月／缺读数怎么办）一条没少。

    每个数字都当场从序列算出：排名、峰值停在哪个月、占比的分子分母增速，下月重跑全会自己变。
    **每个定性词也一样**：「只有／多达」走 `B.quant()`、「前 N%」走 `B.top_pct()`（向上取整，
    四舍五入会把第 23/223 印成「前 10%」，那是假话）、「唯一创新高／高基数／没挪窝」一律由
    当场算出的判据选分支。写死的措辞配算出来的数字是本页返工过的老毛病 —— 历史重放里过半的
    月份会印出「六个品种里 ADV 上行的只有六个」这种自相矛盾的句子，本月读着通顺纯属数据凑巧。

    ═══ CME 独有，别家不能照抄 ═══
      · **R3（日历护栏）在本页完全不适用，不是「用不上」而是「用了就是造假」。**
        CME 披露的 `adv_*` 本来就是 ADV（当月合计 ÷ 当月交易日，公司在 xlsx 里已经除过），
        `oi_*` 是月末时点存量 —— 两类列都没有可再扣的日历成分。CSV 里那一列 trading_days
        存在，只是为了让 Exhibit 3 把「总量口径 vs 按日口径」的差摆出来（Barclays 调整），
        绝不是给 brief 再除一次的分母。对 ADV 套 `calendar_split()` 会凭空造出一个
        根本不存在的「日历修正」，而且它长得跟真的一样。
      · **同一个品种的 ADV 与 OI 反向才是本页的核心信息**：CME 六个品种的 ADV（流量）
        与月末持仓（存量）是两套独立披露，Exhibit 1 只汇总总持仓、分品种持仓一格都没有。
        所以「某品种成交回升的同时持仓在缩」这件事，除了这一段，全页任何图表都读不出来 ——
        它把一根往上的涨柱从「需求回来了」改读成「换手」。别家（IBKR/COST）没有这组对照。
      · **电子化占比是推导值**：公司披露 Globex 电子成交与 Total ADV 两个绝对量，不披露商，
        故正文带「（推导值）」（R5）。它的同比只能按 R4 报**两个增速之商**，
        不能写成「几成来自电子、几成来自总量」的比例拆分 —— 那个拆法数学上就是错的。
      · **本页有真实缺值**：`adv_globex_electronic_kcontracts` 在 2021-04 整月为空，
        于是 2021-04（占比本身）与 2022-04（它的 i-12，同比）两个月都算不出来。凡是要用到
        某一格的半句，拼之前一律过 `B.need()`，缺就换成「哪个月缺了什么」——不让 None 流进
        `B.top_pct()` / `B.pct()`，也不因为一句解读把整页构建掀掉。
      · CME 没有反向指标（无逾期率/坏账率一类越低越好的序列），故 `peak_scan` 一律
        `inverse=False`；也没有公司 Notes 的一次性重述，故无「（还原口径）」标注。
    """
    i = len(months) - 1
    n = len(months)
    if i < 1:
        # 四句里有三句以上月为参照。这不是数据缺值而是调用错误（本页窗口本身就要 13 个月：
        # CUR/PRV/YAG 取的是 LATEST、LATEST-1、LATEST-12），照本仓「失败要响」处理。
        raise SystemExit(f'brief 至少需要 2 个月，收到 {n} 个月')
    # 分位只在名次落在前半段时才印：「第12（前100%）」是真话但没有信息，n 小的时候尤其吵；
    # 后半段退回「第r/n」这个中性写法（已验收的 ibkr.py 样板通篇只报名次，不报分位）。
    # 印分位一律走 B.top_pct（向上取整）—— 四舍五入会把第 23/223 印成「前 10%」，那是假话。
    top = lambda r: (f'（{B.top_pct(r, n)}）' if r / n <= 0.5 else f'/{n}') if r else ''
    quant = lambda c: B.quant(c, len(cls), '个')

    # ── R1 峰值扫描（两个总量：ADV 与月末持仓）。skip_monotonic=False 的理由同 ibkr.py：
    #    「谁创了新高」正是这一句要讲的事，被单调性挡掉就没得讲了。两条序列 load() 都
    #    校验过无缺值，但仍按 peak_scan 的返回拼句 —— 名字由它给，不在句子里写死。
    pk = B.peak_scan(months, [('成交', adv), ('持仓', oi)], i, skip_monotonic=False)
    ntot = B.cn(len(pk['at_peak']) + len(pk['off_peak']))
    off_txt = '、'.join(f'{nm}峰值停在 {m}' for nm, m in pk['off_peak'])
    if not pk['off_peak']:
        tail = f'{ntot}个总量指标同时创 {n} 个月新高'
    elif pk['at_peak']:
        # 创新高的是哪一个必须点名：主语是 ADV，而创新高的可能是持仓，含糊会挂错。
        tail = f'创 {n} 个月新高的只有{"、".join(pk["at_peak"])}，{off_txt}'
    else:
        tail = f'{ntot}个总量指标一个都没创新高，{off_txt}'
    rnk, orank = B.rank_of(adv, i), B.rank_of(oi, i)
    s1 = (f'{B.mo(months[i])}月总 ADV <b>{B.num(adv[i] / 1000, 1)}mn张/日</b>排全样本 {n} 个月'
          f'第{rnk}{top(rnk)}、月末持仓 {B.num(oi[i], 1)}mn张第{orank}{top(orank)}，{tail}。')

    # ── R2 基数护栏。CME 的月度量能天生锯齿（季月换月、到期周、宏观事件挤在同一个月），
    #    环比与同比反号是常态；不给出上月在全样本里的位置，读者会把「从一个极值月回落」
    #    直接读成需求转向。本页最高频的一处误读。
    be = B.base_effect(adv, i)
    pr, pmo = be['prev_rank'], B.mo(months[i - 1])
    # 上月在全样本里的位置：这一句的全部作用就是让读者知道环比的分母是不是一个极值月。
    # 「最高月」由 prev_is_max 判，不写死；名次缺（该月无读数）时整句退化成只讲方向。
    prev_where = ('全样本最高月' if be['prev_is_max'] else f'全样本第{pr}高月') if pr else '无读数'
    if be['mm'] is None:
        # 上月缺读数或为零时 prev_where 也没得说，整句退成一句交代，不硬拼出「是无读数」。
        s2 = f'{pmo}月无可比读数，本月的环比与基数都不报。'
    else:
        mtxt = (f'环比从{pmo}月{B.num(adv[i - 1] / 1000, 1)}mn'
                f'{"跌" if be["mm"] < 0 else "涨"}{abs(be["mm"]) * 100:.1f}%')
        if be['conflict']:
            # 「高基数」不能写死：它只有在上月自身确实靠前时才成立。上月若排在后三分之二，
            # 这个环比跌就不是被极值顶出来的，那时只能说两个方向不一致，不能编出基数效应。
            hi_base = be['mm'] < 0 and pr is not None and pr / n <= 1 / 3
            why = ('环比跌掉的是上月的高基数，不是需求' if hi_base
                   else '两个方向各说各话，只读环比会读反')
            s2 = f'{mtxt}，但{pmo}月是{prev_where}，同比{B.pct(be["yy"])}，<b>{why}</b>。'
        elif be['yy'] is None:
            s2 = (f'{mtxt}，{pmo}月是{prev_where}；序列到本月共 {n} 个月，'
                  f'还差 {12 - i} 个月才够算同比，环比只能与上月自身的位置比。')
        else:
            s2 = f'{mtxt}，同比{B.pct(be["yy"])}，两者同向，{pmo}月是{prev_where}，环比可直读。'

    # ── 品类结构 × 存量：ADV 是流量、OI 是月末时点存量，同一个品种两者反向才是信息。
    fin2 = lambda a: B.need(a[i], a[i - 1])
    a_up = [z for _, z, a, _ in cls if fin2(a) and a[i] > a[i - 1]]
    o_dn = [z for _, z, _, o in cls if fin2(o) and o[i] < o[i - 1]]
    solo = [z for z in a_up if z in o_dn]
    k = B.cn(len(cls))
    # B.quant 的判据只对 1..len(cls) 有定义：0 走进去会印出「只有0个」（cn 对 0 返回 '0'）。
    # 计数为零是常有的月份，不是异常，所以在这里换成中文的说法，不去改 brief.py 的判据。
    cnt = lambda c: quant(c) if c else '一个也没有'
    if solo:
        # solo 不一定只有一家（重放里 43% 的月份 ≥2 家）：全员点名，唯一性暗示不能留在句子里。
        s3 = (f'品类：{k}个品种里 ADV 环比上行的{cnt(len(a_up))}、月末持仓收缩的'
              f'{cnt(len(o_dn))}，两头都占的是{"、".join(solo)}，量回来了、仓在往外走。')
    elif a_up:
        # o_dn 为空时「两头都占的一个也没有」是废话（前半句已经说了没有品种在缩仓），
        # 而且会让「一个也没有」在同一句里出现两次。只有确有品种缩仓时才点这一句。
        s3 = (f'品类：{k}个品种里 ADV 环比上行的{cnt(len(a_up))}、月末持仓收缩的'
              f'{cnt(len(o_dn))}，{"两头都占的一个也没有，" if o_dn else ""}量仓同向可直读。')
    else:
        s3 = (f'品类：{k}个品种的 ADV 环比无一上行，月末持仓收缩的{cnt(len(o_dn))}，'
              f'是全线回落而不是结构轮动。')

    # ── R4 单位恒等 + R5 标注：电子化占比 = Globex 电子成交 ÷ Total ADV，公司只披露分子分母。
    #    同比只能报两个增速之商，不能做「几成来自分子」的比例拆分。
    pu = B.per_unit(gx, adv, i, scale=100.0)
    if not B.need(gx[i], adv[i]):
        s4 = (f'电子化占比（推导值）本月不报：{months[i]} 的 Globex 电子成交在 CME 的 xlsx 里'
              f'就是空的，占比与它的同比都算不出来。')
    else:
        srank = B.rank_of(pu['series'], i)
        if B.need(pu.get('yoy'), pu.get('num_yoy'), pu.get('den_yoy')):
            # 「没挪窝」得由商的大小说了算：商大到一个百分点以上就是渠道结构自己在动。
            move = '渠道结构没跟着量能动' if abs(pu['yoy']) <= 0.01 else '渠道结构自身也在移'
            # R4：只报两个同比之商（(1+分子同比)÷(1+分母同比)−1），不做「几成来自分子」的拆分。
            ytxt = (f'同比{B.pct(pu["yoy"])}，是电子成交{B.pct(pu["num_yoy"])}除以总 ADV '
                    f'{B.pct(pu["den_yoy"])}的商，{move}')
        else:
            ytxt = ('序列不足 12 个月，同比暂缺' if i < 12
                    else f'{months[i - 12]} 的分子缺读数，同比暂缺')
        s4 = (f'电子化占比（推导值）<b>{B.num(pu["value"])}%</b>'
              f'排第{srank}{top(srank)}，{ytxt}。')

    return B.render([s1, s2, s3, s4])


BRIEF = compose_brief(
    [str(p) for p in df.index],
    df['adv_total_kcontracts'].values,
    df['oi_total_contracts'].values / 1e6,
    df['adv_globex_electronic_kcontracts'].values,
    [(c, z, df[c].values, df[o].values) for c, z, o in CLS_BRIEF])


# ══════════════════════════ 7. 抬头与 payload ══════════════════════════
_adv_yy = float(df['adv_yoy'][CUR])
# 抬头原先只写 y/y。7 月 ADV 是 +23.0% y/y 但 −11.9% m/m（一年里第二大的环比跌幅），
# 只报同比等于把「本月比上月掉了一成多」藏到表格里，读者不往下翻就得到一个纯正面的印象。
# 同比与环比同时给，哪一个难看都照写。
_adv_mm = (float(df['adv_mn'][CUR]) / float(df['adv_mn'][PRV]) - 1) * 100
_vol_yy = float(df['vol_yoy'][CUR])
_vol_mm = (float(df['total_vol_mn'][CUR]) / float(df['total_vol_mn'][PRV]) - 1) * 100
_dc = float(df['daycount_effect'][CUR])
_oi_yy = (float(df['oi_total_mn'][CUR]) / float(df['oi_total_mn'][YAG]) - 1) * 100
_share = float(df['rates_share'][CUR])

payload = {
    'ticker': 'cme',
    'tracker': 'CME Monthly Volume Tracker',
    'title': f'CME Group (CME): 月度成交量跟踪 — {CUR.year}年{CUR.month}月',
    'data_through': str(CUR),
    'through_label': f'{CUR.year} 年 {CUR.month} 月',
    'subtitle': (f'数据源：CME Group IR 月度成交量报告（次月第 1-2 个工作日发布）· '
                 f'覆盖 {mlab(df.index[0])} – {mlab(LATEST)}（{len(df)} 个月）· '
                 f'版式仿 Goldman Sachs GIR「IBKR Monthly」与 Barclays day-count 调整 · 仅图，无评论'),
    'headline': (f'ADV {df["adv_mn"][CUR]:,.1f}mn 张/日（{pct(_adv_yy)} y/y，'
                 f'{pct(_adv_mm)} m/m）· '
                 f'总成交 {df["total_vol_mn"][CUR]:,.0f}mn 张（{pct(_vol_yy)} y/y，'
                 f'{pct(_vol_mm)} m/m，交易日贡献 {pp(_dc)}）· '
                 f'月末未平仓 {df["oi_total_mn"][CUR]:,.1f}mn 张'
                 f'（{pct(_oi_yy)} y/y）· 利率品种占 ADV {_share:.0f}% · '
                 f'隐含交易收入 ${df["implied_txn_rev_usdmn"][CUR]:,.0f}mn'),
    # headline 之下、Exhibit 1 之上的 ~300 字解读。职责与 headline 互补：
    # 那一行给读数，这一段给「读数该怎么读」。见 compose_brief 的 docstring。
    'brief': BRIEF,
    'hub_line': (f'ADV {df["adv_mn"][CUR]:,.1f}mn 张/日，{pct(_adv_yy)} y/y、'
                 f'{pct(_adv_mm)} m/m；利率品种占 {_share:.0f}%'),
    'source': SRC,
    'xlabels': XL13,
    'xlabels_long': XL_LONG,
    'summary': summary(),
    'exhibits': ex,
    'table': table,
    'notes': NOTES,
    'footer': 'CME Group (CME) · monthly volume reports · charts only, no commentary · '
              'personal research use',
}

# 抬头右侧那半句「官方发布于 X」是关于外部世界的事实断言，只能取台账里记下的、
# 由源头自己给出的日期（CME 这家是 xlsx 的 Last-Modified 与工作簿保存时间戳互证，
# 见 fetch/cme.py 的 _publish_date）。台账里没有就**整个字段不写** ——
# 页面判的是字段在不在，塞 None 会把那半句变成「官方发布于 None」。
_SOURCE_DATE = repo.source_date('cme', str(CUR))
if _SOURCE_DATE:
    payload['source_date'] = _SOURCE_DATE


def main():
    # 写出前先过 CONTRACT §5.5 护栏（NaN/Infinity 一律拒写）；首行注释与序列化都在里面。
    payload_guard.write_dash(OUT, payload, 'cme')
    print(f'数据截至 {CUR} | 月份 {df.index[0]} → {LATEST}（{len(df)}）')
    print(f'Exhibit 1 汇总表 + Exhibit {ex[0]["n"]}-{ex[-1]["n"]}（{len(ex)} 张）+ '
          f'Exhibit {table["n"]} 核对表')
    print(f'写出 {OUT}（{os.path.getsize(OUT) / 1024:.1f} KB）')
    print(payload['headline'])


if __name__ == '__main__':
    main()
