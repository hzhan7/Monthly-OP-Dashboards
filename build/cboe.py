# -*- coding: utf-8 -*-
"""Cboe Global Markets (CBOE) 月度成交量与 RPC —— 网页看板数据生成器。

把 build/build_cboe.py（matplotlib / PDF）的每一张 exhibit 逐张移植成 data/cboe.js 里的
payload 对象。图的顺序、编号、标题文案、窗口长度、图注全部照搬原 deck；数值全部来自
series/cboe.csv，页面不做任何计算。

模版来源：Goldman Sachs「IBKR Monthly」的成对图法与 Exhibit 6-9 的「量 x 价」处理 ——
          GS 对券商永远同时画「量」(DARTs) 与「单位价格」(CPT)，再用二者乘积画收入/日。
          Cboe 是全清单里唯一官方同时披露 ADV 与 RPC 的标的，因此这套量价框架可以
          完整复刻：ADV x RPC = 每日交易净收入的直接估算。
数据源：Cboe 官网 Monthly volume and revenue per contract (RPC) reports，次月第 3 个工作日。

⚠️ 口径断点与已知坑（详见 payload 的 notes）：
  · RPC 是**三个月滚动平均、滞后一个月发布**，不是单月数 —— 空白 RPC 不是数据缺口。
  · 2017 年数字是 Bats pro-forma combined（Cboe 2017-02 完成收购 Bats），与其后不完全可比。
  · Implied options transaction revenue 是推导值（当月 ADV × 三个月滚动 RPC），不是披露值。

与原 deck 的**有意差异**（图表引擎能力所限或可读性权衡，已在 notes 里逐条写明）：
  · Exhibit 7 原 deck 用对数轴（log=True），charts.js 只有线性轴 → 改线性 + yfloor=0。
  · Exhibit 6 原 deck 在末 3 个月画红色虚线椭圆（circle=3），charts.js 无此元件 → 不画。
  · Exhibit 9 原 deck 把三种单位画在同一根轴上 → 拆成 9a / 9b 两张单序列图
    （第三条欧股 ADNV 与 Exhibit 11 同序列同窗口，不重画）。

用法: python3 build/cboe.py     （可重复跑，除首行日期外逐字节相同）
"""
import datetime
import json
import os
import re

import numpy as np
import pandas as pd

import brief as B
from monthlab import mlab   # x 轴月份标签 Jul-26 的唯一实现
import payload_guard
import pctile
import repo            # 仓库定位 + 发布日台账入口

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CSV = os.path.join(ROOT, 'series', 'cboe.csv')
OUT = os.path.join(ROOT, 'data', 'cboe.js')

SRC = 'Source: Cboe monthly volume and RPC reports; format after Goldman Sachs GIR'

WIN_LONG = 25       # 原 deck 的 lvl_bar / multi_line 窗口
WIN_SHORT = 13      # 原 deck 的 stack_share 窗口
WIN_QTR = 14        # 原 deck 的 qtr_bar 窗口（季度数）
HEAT_YEARS = 10     # 原 deck 的 heat_matrix n_years

# 顶部 brief 用：RPC 的滚动口径。公司自己写明是 three-month rolling average（见 notes），
# 但没说是哪三个月。用「(w 三个月成交量加权的指数占比) x 指数 RPC + 余下 x 多重挂牌 RPC」
# 去复原披露的混合 RPC，对齐窗口实测只有 M-2..M 一个解：
#   M-2..M 平均绝对误差 0.10%（最大 0.72%）｜M-1..M+1 2.28%｜M..M+2 4.01%｜单月 3.42%
# 相差一个量级，不是调参调出来的。compose_brief 每次重跑都会重算这个误差并卡阈值。
RPC_WIN = 3
BRIEF_HI = 330      # brief 去标签字数的自压上界（B.render 的护栏是 230-380）。贴着上界发布
                    # 等于把「下个月名次多一位数」当成停更风险；压法见 compose_brief 末尾
RPC_FIT_TOL = 2.0   # 复原误差上限（%）。实测 0.10%，留 20 倍余量：这道闸只拦「口径变了」
                    # 那种量级的事故，不拦月度噪音（拦太紧会让整页因为一个数据毛刺永久停更）

# brief 的 R1 峰值扫描扫哪几条产品线。只放**公司单列披露的成交量**，不放派生比值
# （占比、implied 收入那些各自有图）；每条都是「越高越好」的量，故 peak_scan 不传 inverse。
# 不放美国期权总量与自有指数期权总量：它们是下面九条里若干条的合计，放进来等于把同一件事
# 数两遍，「九条里只有一条创新高」这句就不成立了。
BRIEF_LINES = [
    ('SPX 期权', 'adv_spx_options_kcontracts'),
    ('XSP 期权', 'adv_xsp_options_kcontracts'),
    ('VIX 期权', 'adv_vix_options_kcontracts'),
    ('VIX 期货', 'adv_vix_futures_kcontracts'),
    ('CFE 期货', 'adv_futures_kcontracts'),
    ('美股撮合', 'adv_us_equities_matched_shares_bn'),
    ('欧股 ADNV', 'adv_eu_equities_adnv_eurbn'),
    ('全球外汇', 'adv_fx_adnv_usdbn'),
    ('多重挂牌期权', 'adv_multilist_options_kcontracts'),
]


# ────────────────────────────── 通用零件 ──────────────────────────────


def nz(v, dec):
    """消掉负零。round(-0.04, 1) 是 -0.0，f-string 会照实印成「-0.0」/「-0」——
    读者看到的是一个不存在的负数（复查在 exchanges 热力矩阵与 tsm 上都抓到过）。
    四舍五入到展示精度之后若等于 0，就把符号去掉。"""
    if v is None or not np.isfinite(v):
        return v
    r = round(float(v), dec)
    return 0.0 if r == 0 else float(v)


def comma(v, dec=0, money=''):
    """与 gsx._fmt 一致的数值格式化（千分位 + 固定小数位 + 货币前缀）。"""
    if v is None or not np.isfinite(v):
        return ''
    return f'{money}{nz(v, dec):,.{dec}f}'


def pctf(x, dec=0):
    """百分比变化，带显式正号（负值由 f-string 自带负号）。"""
    if x is None or not np.isfinite(x):
        return ''
    return f'{nz(x * 100, dec):+.{dec}f}%'


def pp(x):
    """与 gsx._pp 一致：小变化给 1 位小数，大变化给 0 位。"""
    if x is None or not np.isfinite(x):
        return ''
    v = x * 100
    return f'{nz(v, 1):+.1f}%' if abs(v) < 2 else f'{nz(v, 0):+.0f}%'


def L(a):
    """序列 → JSON 数组，非有限值写 null（图与表都会画成断点／—）。"""
    return [None if (v is None or not np.isfinite(v)) else round(float(v), 6) for v in a]


def yoy(v, i=-1, lag=12):
    """同比。基数缺失／为 0／异号时返回 nan（与 gsx.lvl_bar 的判据一致）。"""
    v = np.asarray(v, float)
    i = i % len(v)
    j = i - lag
    if j < 0 or not (np.isfinite(v[i]) and np.isfinite(v[j])) or v[j] == 0 or v[i] * v[j] < 0:
        return np.nan
    return v[i] / v[j] - 1


def mom(v, i=-1):
    return yoy(v, i, lag=1)


def prior12(v):
    """Prior 12mo Avg. —— 最新月之前的 12 个月均值（gs_bar 的虚线）。"""
    v = np.asarray(v, float)
    return float(np.nanmean(v[-13:-1]))


def yoy_line(s_full, win):
    """逐月同比（%），窗口对齐到 win，供 gs_bar 的次轴 y/y 折线用。

    口径逐行照抄 gsx.lvl_bar（build/gsx.py:285-296）：
      · 基数 |b| < 中位绝对值 × 0.15 → 放弃（小基数会把同比放大成几百个百分点）
      · 两期异号 → 放弃（负转正的「同比」没有意义）
    引擎不替这一步做判断（engine_kinds.md §8 明写「口径判断由 Python 侧完成」），
    所以放弃的期一律写 null，图上断开、表格视图里是「—」。
    """
    v = np.asarray(s_full.values, float)
    scale = float(np.nanmedian(np.abs(v))) or 1.0
    out = np.full(len(v), np.nan)
    for i in range(12, len(v)):
        a, b = v[i], v[i - 12]
        if not (np.isfinite(a) and np.isfinite(b)):
            continue
        if abs(b) < 0.15 * scale or a * b < 0:
            continue
        out[i] = (a / b - 1) * 100
    return pd.Series(out, index=s_full.index).reindex(win).values


def yoy_rhs(s_full, win, name='y/y (RHS)'):
    """gs_bar 的次轴 y/y 折线 payload（给了它引擎就不画 12 个月均线）。"""
    return {'name': name, 'color': 'GOLD', 'yfmt': 'pct0', 'values': L(yoy_line(s_full, win))}


# ────────────────────────────── 读数据 ──────────────────────────────
def load():
    if not os.path.exists(CSV):
        raise SystemExit(f'找不到数据文件: {CSV}')
    df = pd.read_csv(CSV)
    df['month'] = pd.PeriodIndex(df['month'], freq='M')
    df = df.set_index('month').sort_index()
    for c in df.columns:
        df[c] = pd.to_numeric(df[c], errors='coerce')

    need = ['adv_us_options_kcontracts', 'rpc_us_options_usd', 'adv_futures_kcontracts',
            'adv_us_equities_matched_shares_bn', 'adv_eu_equities_adnv_eurbn',
            'adv_fx_adnv_usdbn', 'adv_multilist_options_kcontracts',
            'rpc_multilist_options_usd', 'adv_index_options_kcontracts',
            'rpc_index_options_usd', 'adv_spx_options_kcontracts',
            'adv_vix_options_kcontracts', 'adv_xsp_options_kcontracts']
    missing = [c for c in need if c not in df.columns]
    if missing:
        raise SystemExit(f'series/cboe.csv 缺列: {missing}')

    # 月份必须逐月连续 —— 否则 25 个月窗口、同比与季度合计全部错位（CONTRACT §5.3/§5.5）
    idx = list(df.index)
    bad = [(str(idx[i - 1]), str(idx[i])) for i in range(1, len(idx))
           if (idx[i] - idx[i - 1]).n != 1]
    if bad:
        raise SystemExit(f'月份序列不连续: {bad}')

    # ── 派生列（逐行照抄 build_cboe.py）──
    df['opt_rev_day_usdmn'] = df['adv_us_options_kcontracts'] * df['rpc_us_options_usd'] / 1000.0
    df['adv_us_options_mn'] = df['adv_us_options_kcontracts'] / 1000.0
    df['adv_index_options_mn'] = df['adv_index_options_kcontracts'] / 1000.0
    df['adv_spx_mn'] = df['adv_spx_options_kcontracts'] / 1000.0
    df['adv_vix_opt_mn'] = df['adv_vix_options_kcontracts'] / 1000.0
    df['adv_xsp_mn'] = df['adv_xsp_options_kcontracts'] / 1000.0
    df['adv_multilist_mn'] = df['adv_multilist_options_kcontracts'] / 1000.0
    df['index_share'] = df['adv_index_options_kcontracts'] / df['adv_us_options_kcontracts'] * 100
    return df


# ────────────────────── Exhibit 1：汇总表（gsx.summary_table）──────────────────────
def summary_block(df, cur, prv, yag):
    """本月 | 上月 | 去年同月 ‖ m/m | y/y | 3Y %ile。

    格式化与着色规则全部在这里定死（CONTRACT §2）：页面只贴字符串。
    """
    ROWS = [
        ('group', 'U.S. options ADV (k contracts/day)', None, 0, ''),
        ('row', 'Total U.S. options', 'adv_us_options_kcontracts', 0, ''),
        ('row', 'Index options (proprietary)', 'adv_index_options_kcontracts', 0, ''),
        ('row', '　of which SPX', 'adv_spx_options_kcontracts', 0, ''),
        ('row', '　of which VIX options', 'adv_vix_options_kcontracts', 0, ''),
        ('row', 'Multiply-listed options', 'adv_multilist_options_kcontracts', 0, ''),
        ('group', 'Other franchises', None, 0, ''),
        ('row', 'Futures ADV (k contracts/day)', 'adv_futures_kcontracts', 0, ''),
        ('row', 'U.S. equities matched (bn shares/day)', 'adv_us_equities_matched_shares_bn', 2, ''),
        ('row', 'European equities ADNV (EUR bn/day)', 'adv_eu_equities_adnv_eurbn', 1, ''),
        ('row', 'Global FX ADNV ($bn/day)', 'adv_fx_adnv_usdbn', 1, ''),
        ('group', 'Revenue per contract ($)', None, 0, ''),
        ('row', 'U.S. options RPC', 'rpc_us_options_usd', 3, '$'),
        ('row', 'Index options RPC', 'rpc_index_options_usd', 3, '$'),
        ('row', 'Multiply-listed options RPC', 'rpc_multilist_options_usd', 3, '$'),
    ]

    # 分位一律走 build/pctile.py：判据（回放近 24 个月、≥70% 钉在极值就留空）是**口径**，
    # 口径只能有一处定义。本文件原来自己写的「diff>=0 占比 ≥90% 就留空」拦不住
    # 「上下波动但分位常年钉 100」的行，且与其他 13 个生成器各写各的、同一条序列在
    # 两页可以判定相反。
    i_cur = list(df.index).index(cur)

    rows, blanks = [], []
    for kind, lab, col, dec, money in ROWS:
        if kind == 'group':
            rows.append({'kind': 'group', 'label': lab})
            continue
        s = df[col].dropna()
        g = lambda p: (float(s.loc[p]) if p in s.index else np.nan)
        c, p1, p12 = g(cur), g(prv), g(yag)

        def chg(a, b):
            # 比率模式：分母为 0 或两期异号时百分比变化无意义（同 gsx.summary_table）
            if not (np.isfinite(a) and np.isfinite(b)) or b == 0 or a * b < 0:
                return None
            return (a / b - 1) * 100

        cells = [{'v': comma(c, dec, money), 'cls': 'cur'},
                 {'v': comma(p1, dec, money)},
                 {'v': comma(p12, dec, money)}]
        for v in (chg(c, p1), chg(c, p12)):
            if v is None:
                cells.append({'v': ''})
            else:
                v = nz(v, 1)
                cells.append({'v': f'{v:+.1f}%',
                              'cls': 'pos' if v > 0 else ('neg' if v < 0 else '')})

        ser = [None if not np.isfinite(x) else float(x) for x in df[col].values]
        qv, qcls = pctile.cell(ser, i_cur)
        cells.append({'v': qv, 'cls': qcls} if qv else {'v': ''})
        if not qv:
            # 留空必须给得出理由，否则读者只会当成「这一格忘了填」
            why = pctile.why_blank(ser) or ('最新月尚未披露，RPC 滞后一个月发布'
                                            if ser[i_cur] is None else '样本不足')
            blanks.append((lab.strip('　'), why))
        rows.append({'label': lab, 'cells': cells})

    return {
        'title': f'Cboe monthly volume and RPC summary — {mlab(cur)}',
        'heads': [mlab(cur), mlab(prv), mlab(yag), 'm/m', 'y/y', '3Y %ile'],
        'sep': 3,
        'rows': rows,
        'blank_why': blanks,        # 供 notes 生成表注，不进页面渲染
    }


# ─────────────────────── 顶部 ~300 字数据总结（payload 的 brief）───────────────────────
def compose_brief(ALL, i0, tot, ix, ru, ri, rm, lines):
    """Cboe 页顶部的 ~300 字数据总结。

    规则库在 `build/brief.py`（R1 峰值扫描 / R2 基数护栏 / R3 日历护栏 / R4 单位恒等 /
    R5 标注 / R6 有效位），那边只算事实，句子在这里拼——措辞是口径的一部分，属于各家自己。
    每个数字都是当场从序列算的，**没有一处硬编码**：排名、滚出窗口的是哪个月、峰值停在
    哪一年，下个月重跑都会自己变。**每个定性词也一样**——「只有 N 条」「与总数反向」
    「同比全为正」「最高」全部由当场算出的量决定分支（`B.quant()` / `B.need()` /
    `B.top_pct()`）。写死的措辞配算出来的数字是这一段返工过的主因，别再往回写。

    ═══ Cboe 独有，别家不能照抄 ═══
      · **R3（日历护栏）在这里不成立，而且用了就是错的。** cboe.csv 的 adv_* 列公司披露
        的本来就是 ADV（每日平均），不是当月合计；再除一次交易日会造出一个根本不存在的
        修正。全站只有 IBKR / COST 那种「当月合计」列才轮得到 R3。
      · **RPC 是三个月滚动平均、滞后一个月发布**，这两条合起来造出一个别家没有的基数陷阱：
        混合 RPC 的环比可以整段由「三个月窗口换掉了哪个月」决定，而与本月的定价、本月的
        成交完全无关。本段的主句讲的就是这件事，其余 13 家没有一家的单价序列是滚动的。
      · Cboe 是全清单里唯一官方**同时**按月披露量（ADV）与单位价（RPC）、且按两本账
        （自有指数 / 多重挂牌）分别披露的标的，所以「动的是结构还是单价」可以真的算出来
        并回验；其余各家只有量，价得靠季度费率去凑。
      · 排名一律从 `i0`（首个非 pro-forma 月）起算，与 Exhibit 6 那条红色断点虚线同一个
        下标。2017 年是 Bats pro-forma combined 口径，混进分母会把一次并表算成历史区间。
        同一个理由使 `B.regime_ratio()` 在本页不可用——它的基期写死取序列首年，那正好是
        pro-forma 的 2017 年（T4/R4 因此整条跳过，不是忘了写）。**环比同样受这条约束**：
        上一期 RPC 落在 i0 之前时两期不可比，那一句宁可不写。
      · 本页没有反向指标（RPC、ADV 都是越高越好），故 `peak_scan` 不传 inverse；
        九条产品线经 `B.is_monotonic()` 判定无一单调，「创新高」在这里是信息不是噪音。

    ═══ R5 的标记挂在哪（核验退回过一次：方向挂反了）═══
      两条分账 RPC（指数 / 多重挂牌）与九条 ADV 都是**公司披露列**，所以「拆开两本账」
      本身不是推导，不能挂（推导值）——挂在那里等于把公司自己发的数标成我们算的。真正的
      推导值是：三个月成交量加权权重、结构/单价分解、指数占比，标记跟着这几个走。分解虽然
      不再逐项印数，但「跌的是结构不是单价」这个判断整个建在它上面，所以标记不跟着数字走、
      跟着**依据**走，留在那句判断后面。
      另外「M-2 至 M」这个对齐窗口是**拟合**出来的（公司只说 three-month rolling，没说
      是哪三个月，见文件头 RPC_WIN 的注释），故单标「拟合口径」，与「推导值」不是一回事。

    ═══ 分解印到哪一层（2026-08 收窄）═══
      分解照算，正文**只印结论**：「跌的是结构不是单价」。此前印的是「结构 -1.46¢、
      费率合计 -0.22¢、复原余项 -0.06¢」三项带余项——读者要先做一次三项加法才跟得上，
      比样板（build/ibkr.py 的二元恒等式 + 一句落点）深一档。洞察保留，层数收掉。
      随之作废的还有余项那套倒算逻辑：分解对**复原**序列 wn·ri+(1−wn)·rm 是恒等式，
      而 d_rpc 用的是**披露**的 ru，两者差一个复原残差，所以当时得把余项按印出来的两位
      小数倒算出来才能让三个数相加等于总数。不印分项就没有加不平的问题，这一层一并删掉。
      复原误差仍然每次重算，但只作 RPC_FIT_TOL 那道闸的判据，不进正文。

    ═══ 字数 ═══
      `B.render()` 的护栏是 230-380，那是拦「模板拼坏了」用的。这里自己压到 BRIEF_HI
      以内：贴着上界发布等于把「下个月排名多一位数」当成停更风险。压法不是删限定语
      （推导值 / 拟合口径 / 滞后一期），而是先试最小的删法，见函数末尾。
    """
    i = len(ALL) - 1
    y0 = ALL[i0][:4]                       # 排名区间的起点年（= pro-forma 之后）
    fin = np.where(np.isfinite(np.asarray(ru, float)))[0]
    fin = fin[fin >= i0]
    # RPC 最新可得月（比成交量晚一期）。断点之后一个都还没披露时为 None——此时整块 RPC
    # 叙述不写，页面照发（B.need 的规矩：缺值是「该句不写」，不是整页构建失败）。
    j = int(fin[-1]) if len(fin) else None

    def m(k, ref):
        """月份标签。与参照月同年时只写「6 月」，跨年才补年份。

        RPC 的三个月窗口每年有两次跨年（12 月那一档含 10、11、12 月，1 月那一档含
        11、12、1 月）。恒不写年份，1 月的页面上「11 月换成 1 月」会被读成同一年往前退；
        恒写年份则一句话里塞四个「2026 年」。所以按需补。"""
        return (f'{ALL[k][:4]} 年 {int(ALL[k][5:7])} 月' if ALL[k][:4] != ALL[ref][:4]
                else f'{int(ALL[k][5:7])} 月')

    def ordinal(rk, n, unit='高'):
        """排名措辞。第 1 名写「最高」——「第 1 高」不是中文。"""
        return f'{n} 个月里最{unit}' if rk == 1 else f'{n} 个月里第 {rk} {unit}'

    def fold(names, cap=2, count=True):
        """名字最多列 cap 条，其余折成「等 N 条」（count=False 时只写「等」）。

        并列条数是当场算的：回放到 2019 年会有六七条线并列停在同一个月，全列出来一句话
        就撑破字数护栏。cap 从 3 收到 2，是因为三条并列 + 三个排名恰好卡在护栏上界附近，
        再多一条就发不出去——折叠省下的字必须够抵掉后面多出来的排名项。"""
        head = '、'.join(names[:cap])
        if len(names) <= cap:
            return head
        return head + (f'等{B.cn(len(names))}条' if count else '等')

    def w3(k):
        """三个月滚动的量加权指数占比（推导值）。

        分子分母必须取**同一批月份**：各自 nansum 时，哪天 ix 与 tot 在窗口内的不同月
        缺值，比值会静默混月（当前 115 行两列全无 NaN，未触发，但这道掩码是白拿的）。
        窗口不足 RPC_WIN 个月时按现有月份算——负下标会把序列尾巴卷进来。"""
        a = max(0, k - RPC_WIN + 1)
        x = np.asarray(ix[a:k + 1], float)
        t = np.asarray(tot[a:k + 1], float)
        msk = np.isfinite(x) & np.isfinite(t)
        s = float(t[msk].sum())
        return float(x[msk].sum() / s) if msk.any() and s else float('nan')

    # ── 「披露的混合 RPC 能不能被两本账复原」的当场回验。误差每次重算：口径哪天变了
    #    （比如改成两个月滚动）这道闸会响，而不是静默印错话。样本为空（序列只有两三个月、
    #    或断点后还没攒够一个窗口）时不响——那不是口径变了，是还没数可拟合，此时下面的
    #    分解整块不写。
    j_hi = j if j is not None else i0 - 1
    fit = [abs((w3(k) * ri[k] + (1 - w3(k)) * rm[k]) / ru[k] - 1)
           for k in range(max(i0, RPC_WIN - 1), j_hi + 1)
           if B.need(ru[k], ri[k], rm[k], w3(k)) and ru[k]]
    if fit and float(np.mean(fit)) * 100 > RPC_FIT_TOL:
        raise SystemExit(
            f'brief: 混合 RPC 用「三个月滚动量加权 x 两本账 RPC」复原的平均误差 '
            f'{float(np.mean(fit)) * 100:.2f}% 超过 {RPC_FIT_TOL}%，RPC 的滚动口径可能变了。'
            f'先重新拟合 RPC_WIN 与对齐窗口，不要让 compose_brief 照旧印那句分解。')

    sh = ix / tot * 100                     # 单月指数占比（%，推导值）
    n_sh = int(np.isfinite(sh[i0:]).sum())  # 量口径的样本月数：比 RPC 多一个月（RPC 滞后一期）
    n_ri = int(np.isfinite(ri[i0:]).sum())
    n_ru = int(np.isfinite(ru[i0:]).sum())

    # ── 两道闸，决定 RPC 这一块能写到哪一层。写不动的部分由量口径那句顶上，页面照发。
    have_chg = (j is not None and j - 1 >= i0
                and B.need(ru[j], ru[j - 1], ri[j], ri[j - 1], rm[j], rm[j - 1]))
    have_dec = have_chg and bool(fit) and B.need(w3(j), w3(j - 1))

    rk_ri = B.rank_of(ri[i0:], j - i0) if j is not None else None
    hi_txt = f'指数期权 RPC 是 {y0} 年以来 {ordinal(rk_ri, n_ri)}' if rk_ri else ''

    # ── s1：本期变动 + 贵的那本账在历史里的位置 + 动的是结构还是单价。一句三段，都是读数
    #    或由读数直接比出来的判断，不含中间步骤。
    head1 = punch = ''
    if have_chg:
        # ── mix vs rate 分解（推导值）。各项都用**分**表示，不做除法：RPC 走平的月份
        #    「mix 占跌幅百分之几」会除出一个爆炸的数，而分是它本来的差异单位（CONTRACT §2：
        #    比率类指标的差异不写百分比变化；RPC 以美元计价，其差异形式就是 ¢/张）。
        d_rpc = (ru[j] - ru[j - 1]) * 100                                # ¢/张
        flat = round(d_rpc, 2) == 0
        w_dn = '变动' if flat else ('跌' if d_rpc < 0 else '涨')
        # 「滞后一期」是口径标注，但它也得由数据说：j == i 的月份 RPC 并不滞后。
        lag = '（滞后一期）' if j < i else ' '
        chg = '环比几乎持平' if flat else f'环比{w_dn} {abs(d_rpc):.2f}¢'

        punch = ''
        if have_dec:
            # 分解照算，但**只印结论不印分项**：谁在动是这句话的信息，三个带余项的数是
            # 读者要自己做一遍加法才跟得上的中间步骤（分寸见 docstring「印到哪一层」）。
            wn, wp = w3(j), w3(j - 1)
            d_mix = (wn - wp) * (ri[j - 1] - rm[j - 1]) * 100            # 结构效应 ¢/张
            d_rate = (wn * (ri[j] - ri[j - 1])
                      + (1 - wn) * (rm[j] - rm[j - 1])) * 100            # 两本账单价效应合计
            # 「跌的是结构不是单价」是**判断**不是读数，三个分支全部由这两项当场比出来：
            # 回放 101 个可比月里结构主导 76 个月、单价主导 25 个月、两者量级相当 34 个月，
            # 写死任何一句都会在别的月份变成假话。判据分两道——
            #   ① 方向：主导项必须与总变动同向，否则「跌的是 X」会把一个在往上顶的分项
            #      说成下跌的原因（2019-10 就是这种月：总数 -0.02¢，两项 ∓0.4¢ 互相抵消）
            #   ② 量级：主导项至少是另一项的 2 倍才配说「不是」，否则只说两头都在动
            m2, r2 = round(d_mix, 2), round(d_rate, 2)
            drv, oth = ((m2, r2) if abs(m2) >= abs(r2) else (r2, m2))
            lead = '结构' if abs(m2) >= abs(r2) else '单价'
            if flat:
                # 总数持平时没有方向可归因，能说的只是两项互相抵消（同号则连这句也不成立）
                punch = ('<b>结构与单价互相抵消</b>'
                         if m2 and r2 and (m2 < 0) != (r2 < 0) else '')
            elif drv and (drv < 0) == (d_rpc < 0) and abs(drv) >= 2 * abs(oth):
                punch = (f'<b>{w_dn}的是{lead}不是'
                         f'{"单价" if lead == "结构" else "结构"}</b>（推导值，三个月成交量加权）')
            else:
                punch = '<b>结构与单价都在动</b>（推导值，三个月成交量加权）'
        head1 = f'{m(j, i)} RPC{lag}{chg}'
    elif j is not None:
        head1 = f'{m(j, i)} RPC 与上一期不可比（上一期落在 {y0} 年前的 pro-forma 口径里）'
        punch = ''
    else:
        head1 = punch = ''

    # ── s2：R2 的基数。上面那个「结构」在 Cboe 有一半是机械的——三个月窗口换掉了哪个月，
    #    与本月定价无关。这是 Cboe 独有的基数陷阱，别家的单价序列都不是滚动的。
    s2, swap = '', ''
    if have_dec:
        k_out = j - RPC_WIN                 # 滚出窗口的那个月；落在 i0 之前就不写这一句
        if k_out >= i0 and B.need(sh[k_out], sh[j]):
            rk_out = B.rank_of(sh[i0:], k_out - i0)
            # 第二个月份挂在**滚出月**上做参照，不挂在本月：1 月的页面上两头都是去年，
            # 挂本月会印成「2020 年 9 月换成 2020 年 12 月」，年份白写两遍。
            # 占比是 load() 里的派生列（指数 ADV ÷ 美国期权总 ADV），R5 要求正文带标记；
            # 上一句那个（推导值）挂的是分解与权重，管不到这里，所以这里自己再挂一次。
            swap = (f'RPC 按 M-2 至 M 滚动（拟合口径），这一档把指数占比（推导值）'
                    f'{sh[k_out]:.1f}%（{ordinal(rk_out, n_sh)}）的 {m(k_out, i)}'
                    f'换成 {sh[j]:.1f}% 的 {m(j, k_out)}')
        # 一句话一个意思：s1 说清是结构还是单价在动，这一句只说滚动窗口换掉了哪个月。
        s2 = swap + '。' if swap else ''

    # ── s2b：没有上面那句窗口换月时（断点后的头几个月、RPC 缺值月），指数占比的位置就
    #    没人交代了。改从量口径直接给——tot 与 ix 两列没有缺口，任何截止月都算得出。
    s2b = ''
    if not swap:
        # 量口径的窗口同样从 i0 起：2017 是 Bats pro-forma combined，环比与排名都不能
        # 跨过断点去比（与上面 RPC 那句同一条规矩，不是两套）。
        beq = B.base_effect(np.asarray(tot, float)[i0:], i - i0)
        rk_sh = B.rank_of(sh[i0:], i - i0)
        bits = [f'{m(i, i)}指数占比 {sh[i]:.1f}%（{ordinal(rk_sh, n_sh)}）'] if rk_sh else []
        if beq['mm'] is not None:
            bits.append('美国期权总 ADV 环比 ' + B.pct(beq['mm'])
                        + (f'、同比 {B.pct(beq["yy"])}' if beq['yy'] is not None else ''))
        if beq['rank']:
            bits.append(f'总 ADV 排 {ordinal(beq["rank"], n_sh)}')
        # 自有指数期权这条线是本页的主角，RPC 讲不动的月份至少把它的量交代掉
        bix = B.base_effect(np.asarray(ix, float)[i0:], i - i0)
        if bix['mm'] is not None:
            bits.append('指数期权 ADV 环比 ' + B.pct(bix['mm'])
                        + (f'（{ordinal(bix["rank"], n_sh)}）' if bix['rank'] else ''))
        s2b = ('量口径（推导值：占比 = 指数 ADV ÷ 美国期权总 ADV）：'
               + '，'.join(bits) + '。') if bits else ''

    # ── s3：R2 的落点。分四种，都由数据挑：变动小于历史月变动中位数时它本身就不是信号
    #    （回放里 0.01¢ 的月份确实出现过，照印「会读成费率战」等于给噪音配一段解读）；
    #    反号才轮得到窗口效应那句；同向时是真下行，说成误读就把事实讲反了；同比还没有
    #    （断点后不足 12 个月）时三种都判不出来，那就不下这个判断——原来这里会印「同向」，
    #    在没有同比的月份那是假话。
    s3 = ''
    if j is not None:
        be = B.base_effect(ru[i0:], j - i0)
        dif = np.abs(np.diff(np.asarray(ru[i0:j + 1], float)))
        noise = float(np.nanmedian(dif)) * 100 if np.isfinite(dif).any() else None
        head3 = '环比与同比反号，' if be['yy'] is not None and be['conflict'] else ''
        rank3 = ''
        if be['rank']:
            # 分母写出来：RPC 口径比量口径少一个月，两处名次不是同一个分母（核验点名）。
            # 名次本身还不够——「跌完还在前 7%」才是与 headline 相反的那半句，故带 top_pct；
            # 但只在前半区带：排在后半区时「前 96%」是句废话，那时只给分母。R2 要的上月
            # 名次同理，只有上月真的在前三高（基数效应的触发条件）才占这几个字。
            prev = f'上月第 {be["prev_rank"]}、' if (be['prev_rank'] or 99) <= 3 else ''
            # 全文的数字与汉字之间留一个空格，B.top_pct 返回的「前7%」不带，这里补上
            where = ('的' + re.sub(r'(\d)', r' \1', B.top_pct(be['rank'], n_ru), count=1)
                     if be['rank'] * 2 <= n_ru else '中')
            rank3 = f'混合 RPC {prev}本月第 {be["rank"]}（{n_ru} 个月{where}）'
        end3 = ''
        if have_chg and B.need(noise) and abs(d_rpc) < noise:
            end3 = f'<b>这一{w_dn}小于历史月变动中位数 {noise:.2f}¢，本身不算信号</b>'
        elif have_chg and be['yy'] is not None:
            end3 = (f'<b>只看这一{w_dn}会读成费率{"战" if d_rpc < 0 else "回升"}</b>'
                    if be['conflict'] else f'<b>这一{w_dn}不只是窗口效应</b>')
        body3 = head3 + rank3 + ('——' + end3 if rank3 and end3 else end3)
        s3 = body3 + '。' if body3 else ''

    # ── s4：R1 产品线峰值扫描。谁停在自己的最高点，谁的峰值还停在很多年前。
    #    九条 ADV 全部非单调（B.is_monotonic 判定），所以「创新高」在这里是信息不是噪音；
    #    真有单调列被 skip_monotonic 剔掉时，「N 条」跟着用实际扫过的条数，不写死 len(lines)。
    pk = B.peak_scan(ALL[i0:], [(nm, a[i0:]) for nm, a in lines], i - i0)
    n_scan = len(pk['at_peak']) + len(pk['off_peak'])
    # 「只有一条」是定性词，必须跟着比例走：回放里最多 4/9 条同时停在峰值，那时写「只有」
    # 就是把普遍现象说成稀缺。B.quant() 按 k/n 挑「只有／有／多达」。
    # 条数已经在「只有 N 条」里给过，括号里再写一遍「等四条」是同一个数说两次
    top = (f'{B.quant(len(pk["at_peak"]), n_scan, "条")}停在自己的峰值'
           f'（{fold(pk["at_peak"], count=False)}）' if pk['at_peak']
           else '没有一条停在自己的峰值')
    tone = pos = grp_txt = ''
    if pk['off_peak']:
        old = min(k for _, k in pk['off_peak'])          # 最早的那个峰值月
        all_grp = [nm for nm, k in pk['off_peak'] if k == old]
        grp, srs = all_grp[:2], dict(lines)
        rk = [(B.rank_of(srs[nm][i0:], i - i0), int(np.isfinite(srs[nm][i0:]).sum()))
              for nm in grp]
        # 同比方向当场算（写死「两位数正增长」下个月就可能变成假话），且必须覆盖
        # **被这句话点到的全部**产品线（含折进「等 N 条」的那几条），不能只看列名的两条。
        # 一条都算不出来（不足 12 个月）时不写方向——「涨跌互见」在没有同比的月份是假话。
        yy = [srs[nm][i] / srs[nm][i - 12] - 1 for nm in all_grp
              if i >= 12 and B.need(srs[nm][i], srs[nm][i - 12]) and srs[nm][i - 12]]
        tone = ('同比全为正' if all(v > 0 for v in yy) else
                ('同比已全部转负' if all(v < 0 for v in yy) else '同比涨跌互见')) if yy else ''
        # 分母相同就只写一次；哪天组里混进历史更短的产品（如 XSP 从 2019 起）再逐条写
        dn = {n for _, n in rk if n}
        if all(r for r, _ in rk):
            pos = (f'{dn.pop()} 个月里排第 ' + '、'.join(str(r) for r, _ in rk) + ' 位'
                   if len(dn) == 1 else '排第 ' + '、'.join(f'{r}/{n}' for r, n in rk) + ' 位')
        # 「的」不是可省的虚字：产品线名可能以拉丁字母收尾（欧股 ADNV），直接接汉字会
        # 印成「ADNV峰值」，与全页「字母数字与汉字之间留空」的排版不一致。
        grp_txt = f'{fold(all_grp)}的峰值仍停在 {m(ALL.index(old), i)}'

    def assemble(drop=()):
        # 「但」要同时满足两个条件才成立，缺一个都会印出一句假转折：
        #   (1) 前半句真的给了一个跌／涨（不可比的月份没有转折可转）；
        #   (2) 分账 RPC 的名次真的在**前半区** —— 否则「RPC 跌了，但分账排第 11 高」
        #       里的「但」无处落脚。重放到 2019-03 至 2019-07 会印「但…15 个月里第 11 高」，
        #       正是这种假转折。判据当场算，不写死名次门槛。
        hi_is_high = rk_ri is not None and n_ri and rk_ri * 2 <= n_ri
        hi = '' if 'hi' in drop else (
            ('但' + hi_txt) if have_chg and hi_txt and hi_is_high else hi_txt)
        s1 = '，'.join(x for x in [head1, hi, punch] if x)
        tail = '；' + '，'.join(x for x in [grp_txt,
                                          '' if 'tone' in drop else tone,
                                          '' if 'pos' in drop else pos] if x) if grp_txt else ''
        s4 = f'量这边{B.cn(n_scan)}条产品线{top}{tail}。'
        return [s1 + '。' if s1 else '', s2, s2b, s3, s4]

    # ── 字数：render 的 230-380 是拦「模板拼坏了」的，贴着上界发布是可预见的停更风险
    #    （名次多一位数、产品线改名都会撞破，整页就 SystemExit 发不出去）。所以在这里自己
    #    压到 BRIEF_HI 以内，压法是省可省项，而不是删任何限定语（推导值 / 拟合口径 /
    #    滞后一期）——那些是口径的一部分，删了就是另一句话。可省的三项：
    #      tone 峰值停在多年前那几条的同比方向（5 个字，最便宜）
    #      pos  那几条今天的名次（约 18 个字）
    #      hi   指数 RPC 自己的名次（最后才动：它是 s1 那个转折的依据）
    #    顺序按「先试最小的删法」排，不是固定优先级：只超 3 个字时省掉 tone 就够了，
    #    没必要连名次一起砍掉。三项都省完还超，说明真的拼坏了，交给 render 的护栏去响。
    for drop in ((), ('tone',), ('pos',), ('pos', 'tone'), ('pos', 'tone', 'hi')):
        body = assemble(drop)
        if len(re.sub(r'<[^>]+>', '', ''.join(x for x in body if x))) <= BRIEF_HI:
            break
    return B.render(body)


# ────────────────────────────── 主流程 ──────────────────────────────
def main():
    df = load()
    LATEST = df.index[-1]
    LATEST_RPC = df['rpc_us_options_usd'].dropna().index[-1]
    ALL = list(df.index)

    # 所有窗口一律从**数据最新月**倒推，绝不依赖运行当天的日期（幂等要求）
    W13 = ALL[-WIN_SHORT:]
    W25 = ALL[-WIN_LONG:]
    XL13 = [mlab(p) for p in W13]
    XL25 = [mlab(p) for p in W25]
    XL_LONG = [mlab(p) for p in ALL]

    # 口径断点：2017 年为 Bats pro-forma combined，2018-01 起才是实际口径。
    # break_at 语义是「从这一期起与左侧不可比」，边界落在**首个 2018 月的左缘**。
    # 取「首个 year>=2018 的下标」而不是硬编码 12、也不是数首年的月数：源文件若哪天
    # 回补到 2016，数首年月数会把虚线错画到 Jan-17。首月已晚于 2017 则不画（=None）。
    I_2018 = next((i for i, p in enumerate(ALL) if p.year >= 2018), None)
    BREAK_PF = I_2018 if I_2018 else None       # 0 也视作无断点（左缘无意义）
    PF_YEAR = 2017                              # pro-forma 那一年，供图注与热力矩阵共用

    # RPC 与 implied revenue 的窗口以 LATEST_RPC 结尾：末点为 null 时 lines_endlabels
    # 会对 null 调 toFixed 而崩，且一个空的末点也不带信息
    i_rpc = ALL.index(LATEST_RPC)
    W25R = ALL[max(0, i_rpc - WIN_LONG + 1):i_rpc + 1]
    XL25R = [mlab(p) for p in W25R]

    def col(name, win):
        return df[name].reindex(win).values.astype(float)

    ex = []

    # ── Exhibit 2：Total U.S. options ADV（gsx.lvl_bar → gs_bar）──
    adv = col('adv_us_options_mn', W25)
    adv_all = df['adv_us_options_mn'].values.astype(float)
    ex.append({
        'n': 2, 'kind': 'gs_bar', 'fmt': 'f1', 'xlabels': XL25,
        'title': 'Total U.S. options ADV',
        'ylab': 'mn contracts / day', 'ylab2': '% y/y', 'legend': 'Monthly',
        'values': L(adv),
        'yoy': yoy_rhs(df['adv_us_options_mn'], W25),
        'note': f'近 {WIN_LONG} 个月窗口，与原 deck 一致。金色折线 = 次轴同比'
                f'（与原 deck 相同；原来这里画的是 12 个月滚动均线，那只是把柱子再平滑'
                f'一遍、不带新信息）。{mlab(LATEST)} {comma(adv[-1], 1)} mn/日，'
                f'同比 {pctf(yoy(adv_all))}、环比 {pp(mom(adv_all))}。',
    })

    # ── Exhibit 3：Revenue per contract by book（gsx.multi_line → lines_endlabels）──
    # 单位与原 deck 一致：美元/张、3 位小数。原先这里改成「美分/张」是因为引擎的格式器
    # 最细只到 usd2（$0.07 → 多重挂牌那条线剩不到两位有效数字）；引擎补上 usd3/f3 之后
    # 这个绕道没必要了，换回美元还能与汇总表、核对表、图注的 $0.072 逐字对上。
    rpc_us = col('rpc_us_options_usd', W25R)
    rpc_ix = col('rpc_index_options_usd', W25R)
    rpc_ml = col('rpc_multilist_options_usd', W25R)
    ratio = rpc_ix[-1] / rpc_ml[-1]
    ex.append({
        # yfloor=0：RPC 是单价，不可能为负，而线图默认下界会掉到 −$0.12。
        'n': 3, 'kind': 'lines_endlabels', 'fmt': 'usd3', 'yfmt': 'usd2', 'yfloor': 0,
        'xlabels': XL25R,
        'title': 'Revenue per contract by book',
        'ylab': '$ per contract',
        'series': [
            {'name': 'All U.S. options', 'color': 'NAVY', 'values': L(rpc_us)},
            {'name': 'Index (proprietary)', 'color': 'MBLUE', 'values': L(rpc_ix)},
            {'name': 'Multiply-listed', 'color': 'BLUE', 'values': L(rpc_ml)},
        ],
        'src_extra': 'RPC is a three-month rolling average published on a one-month lag, '
                     'not a single-month figure. Index options carry roughly 10x the RPC '
                     'of multiply-listed',
        'note': f'窗口以 RPC 的最新可得月 {mlab(LATEST_RPC)} 结尾（成交量已到 {mlab(LATEST)}，'
                f'RPC 滞后一个月发布），不是数据缺口。{mlab(LATEST_RPC)}：全美股期权 '
                f'{comma(rpc_us[-1], 3, "$")}、自有指数期权 {comma(rpc_ix[-1], 3, "$")}、'
                f'多重挂牌 {comma(rpc_ml[-1], 3, "$")} —— 指数期权是多重挂牌的 '
                f'{ratio:.1f} 倍，所以 mix（Exhibit 5）对收入的杠杆远大于总量。',
    })

    # ── Exhibit 4：Implied options transaction revenue per day（gsx.lvl_bar → gs_bar）──
    rev = col('opt_rev_day_usdmn', W25R)
    rev_all = df['opt_rev_day_usdmn'].dropna().values.astype(float)
    ex.append({
        # 柱顶标签用 usd1：25 根柱塞进半栏时 "$4.41" 这样的 5 字标签会互相压字。
        # 表格视图会自动回到 usd2（charts.js 的 PRECISE 映射），两位小数一点即得。
        'n': 4, 'kind': 'gs_bar', 'fmt': 'usd1', 'xlabels': XL25R,
        'title': 'Implied options transaction revenue per day',
        'ylab': '$mn / day', 'ylab2': '% y/y', 'legend': 'Monthly',
        'values': L(rev),
        'yoy': yoy_rhs(df['opt_rev_day_usdmn'], W25R),
        'src_extra': 'Current-month ADV x three-month rolling RPC. Cboe is the only name in '
                     'this set where BOTH inputs are officially disclosed monthly, so no '
                     'quarterly rate has to be assumed — but the RPC is a three-month average, '
                     'so the result is smoothed.',
        'note': f'<b>推导值，非公司披露。</b>= 当月美国期权 ADV（k 张/日）× 同月三个月滚动 RPC'
                f'（$/张）÷ 1,000 → $mn/日。假设：RPC 的三个月滚动口径可以直接套在单月成交量上；'
                f'因 RPC 已被平滑，本图的月度波动主要来自量而不是价。'
                f'{mlab(LATEST_RPC)} 为 {comma(rev[-1], 2, "$")}mn/日，同比 {pctf(yoy(rev_all))}、'
                f'环比 {pp(mom(rev_all))}。金色折线 = 次轴同比（同原 deck）。'
                f'柱顶标签取 1 位小数（{WIN_LONG} 根柱塞进半栏，'
                f'2 位小数会压字），点右上角「表格」可看 2 位小数。',
    })

    # ── Exhibit 5：U.S. options mix（gsx.stack_share → stacked_dual）──
    ix13 = col('adv_index_options_kcontracts', W13)
    ml13 = col('adv_multilist_options_kcontracts', W13)
    share13 = ix13 / (ix13 + ml13) * 100
    # 右轴上界：原来是「上取整到 10 的倍数再加 10」，占比只在 25–33% 之间动却把轴拉到
    # 0–50%，这条线的振幅被压掉近一半（原 deck 的 stack_share 把它压进画布上 1/3，
    # 右轴实际只有约 8–36%）。引擎的 stacked_dual 强制右轴从 0 起，能调的只有上界，
    # 所以取「刚好罩住最大值的那一档」——留 2% 余量免得最高点顶在画布边线上。
    ymax = int(np.ceil(np.nanmax(share13) * 1.02 / 10.0) * 10)
    ex.append({
        'n': 5, 'kind': 'stacked_dual', 'fmt': 'f0c', 'xlabels': XL13,
        'title': 'U.S. options mix: proprietary index vs. multiply-listed',
        'ylab': 'k contracts / day', 'ylab2': '% index',
        'stacks': [
            # label_color 不能给 WHITE：引擎给所有数值标签加了 2.4px 的**白色**描边
            # （为了不被均线/折线划穿），白字 + 白描边在 6.6px 下会糊成一个白方块，
            # 深蓝段上的四个数字全部读不出（改之前的渲染实测如此）。改成深色 INK：
            # 白描边此时正好当成描白边的深字用，在深蓝底上反而读得出来。
            {'name': 'Index options (proprietary)', 'color': 'NAVY',
             'values': L(ix13), 'label': True, 'label_color': 'INK'},
            {'name': 'Multiply-listed options', 'color': 'BLUE',
             'values': L(ml13), 'label': True, 'label_color': 'INK'},
        ],
        'line': {'name': '% index (RHS)', 'color': 'GREEN', 'values': L(share13), 'ymax': ymax},
        'note': f'两段之和即 Total U.S. options ADV（Exhibit 2 × 1,000）—— Cboe 的美国期权只分这两块。'
                f'右轴 = 自有指数期权占比：{XL13[0]} {share13[0]:.1f}% → {XL13[-1]} {share13[-1]:.1f}%'
                f'（{nz(share13[-1] - share13[0], 1):+.1f}pp），窗口内在 '
                f'{np.nanmin(share13):.1f}–{np.nanmax(share13):.1f}% 之间。这条线比总量更值钱：'
                f'指数期权的 RPC 约为多重挂牌的 {ratio:.0f} 倍。',
    })

    # ── Exhibit 6：Full U.S. options ADV history（gsx.long_line → lines，通栏）──
    ex6 = {
        # zero_base / end_label 对应原 deck 的 long_line：set_ylim(0, max*1.16) + n_label。
        # 不给 zero_base 时引擎走的是 y0 = min − 极差×5%，那是一次没有标注的隐性截轴，
        # 在这张「约 3.5 倍」的全历史图上会把增长幅度凭空放大（也正是原来纵轴刻度出现
        # 7.5/12.5 这种半档、还被轴格式器印成 8/13 的根因）。
        'n': 6, 'kind': 'lines', 'fmt': 'f1', 'label_fmt': 'f1',
        'zero_base': True, 'end_label': True,
        'xlabels': XL_LONG, 'xstep': max(1, len(ALL) // 14),
        'full': True, 'height': 300,
        'title': 'Full U.S. options ADV history since 2017',
        'ylab': 'mn contracts / day',
        'series': [{'name': 'Total U.S. options ADV', 'color': 'NAVY', 'values': L(adv_all)}],
        'src_extra': 'Full disclosed history; zero-based axis',
        'note': f'{XL_LONG[0]} → {XL_LONG[-1]} 共 {len(ALL)} 个月，无缺月。'
                f'{comma(adv_all[0], 1)} mn/日 → {comma(adv_all[-1], 1)} mn/日，'
                f'约 {adv_all[-1] / adv_all[0]:.1f} 倍。最近 3 个月：'
                + '、'.join(f'{XL_LONG[i]} {adv_all[i]:.1f}' for i in (-3, -2, -1))
                + '。纵轴从 0 起（同原 deck），末点标出最新读数。',
    }
    if BREAK_PF:
        # 标签必须点明「异口径的是虚线左边那段」—— lpla/msci 的先例里变口径的是断点
        # 右侧，这里方向相反，照抄 'M&A' 这种中性词会读反。
        ex6['break_at'] = BREAK_PF
        ex6['break_label'] = '2017 = Bats pro-forma'
        # 断点滚出窗口（源文件哪天只保留 2018 起）时这一整句必须跟着消失，
        # 否则就成了「图注说画了线、图上没有」的自相矛盾。
        ex6['note'] += ('⚠️ 红色竖虚线左侧（2017 年）为 Bats pro-forma combined 口径'
                        '（Cboe 2017-02 完成收购 Bats），与其后年份不完全可比，'
                        '读长期趋势应从虚线右侧起算；倍数一句是端点对端点，同样受此影响。')
    ex6['note'] += ('（另注：原 deck 在末 3 个月画了一个红色虚线椭圆做强调，'
                    '网页图表引擎没有这个元件。）')
    ex.append(ex6)

    # ── Exhibit 7：Proprietary index options ADV by product（gsx.multi_line → lines_endlabels）──
    # 单位用「千张/日」而不是原 deck 的「百万张/日」：百万张口径下 XSP（0.23mn）只剩
    # 两位有效数字，而三条线共用一个格式器。引擎后来补了 f2/f3，但 "0.23" 仍不如
    # "229" 好读，故维持千张；数值本身与 deck 完全一致（× 1,000）。
    spx = col('adv_spx_options_kcontracts', W25)
    vix = col('adv_vix_options_kcontracts', W25)
    xsp = col('adv_xsp_options_kcontracts', W25)
    ex.append({
        # yfloor=0：合约张数恒正，而 lines_endlabels 的默认下界是 min − 极差×20%，
        # 本图算出来是 −1,000 千张/日 —— 约 1/9 的画布在展示一个不存在的量纲区间。
        # 没有任何点落在 0 以下，所以这不是截轴（不会出现红圈与断口），只是把轴归零。
        'n': 7, 'kind': 'lines_endlabels', 'fmt': 'f0c', 'yfloor': 0, 'xlabels': XL25,
        'title': 'Proprietary index options ADV by product',
        'ylab': 'k contracts / day',
        'series': [
            {'name': 'SPX options', 'color': 'NAVY', 'values': L(spx)},
            {'name': 'VIX options', 'color': 'RED', 'values': L(vix)},
            {'name': 'XSP options (Mini-SPX)', 'color': 'GREEN', 'values': L(xsp)},
        ],
        'src_extra': 'The only three index option products Cboe breaks out (XSP from Jan-2019). '
                     'Deck used a log scale: XSP is a fraction of SPX in absolute terms but has '
                     'grown fastest — here the axis is linear and zero-based, so read XSP/VIX '
                     'in the table view',
        'note': f'Cboe 单列的三个指数期权产品（VIX / Mini-VIX 期货属期货，不在此图）。'
                f'{mlab(LATEST)}：SPX {comma(spx[-1], 0)}k、VIX options {comma(vix[-1], 0)}k、'
                f'XSP {comma(xsp[-1], 0)}k 张/日。窗口内 XSP 增长最快'
                f'（{XL25[0]} {comma(xsp[0], 0)}k → {XL25[-1]} {comma(xsp[-1], 0)}k，'
                f'{pctf(xsp[-1] / xsp[0] - 1)}），但绝对量只有 SPX 的 '
                f'{xsp[-1] / spx[-1] * 100:.0f}%。'
                f'<b>与原 deck 的差异：</b>原 deck 用对数轴把三条线拉开，'
                f'网页图表引擎只有线性轴，XSP 与 VIX 在图上被压得很扁 —— '
                f'要读它们自己的走势请切「表格」视图。纵轴从 0 起（张数不可能为负），'
                f'单位由「百万张/日」改为「千张/日」，数值本身不变。',
    })

    # ── Exhibit 8：U.S. options ADV by quarter（gsx.qtr_bar → qtr_bar）──
    sq = df['adv_us_options_mn'].dropna()
    q = sq.groupby(sq.index.asfreq('Q')).agg(['mean', 'count'])
    qv = q['mean'].values.astype(float)
    qi = list(q.index)
    n_in_last = int(q['count'].iloc[-1])
    qyoy = np.array([(qv[i] / qv[i - 4] - 1) * 100 if i >= 4 and qv[i - 4] else np.nan
                     for i in range(len(qv))])
    qw = slice(max(0, len(qv) - WIN_QTR), len(qv))
    exq = {
        'n': 8, 'kind': 'qtr_bar', 'fmt': 'f1', 'label_fmt': 'f1',
        'xlabels': [str(p) for p in qi[qw]],
        'title': 'U.S. options ADV by quarter',
        'ylab': 'mn contracts / day', 'legend': 'Complete quarter',
        'values': L(qv[qw]),
        'line': {'name': 'y/y (RHS)', 'color': 'GREEN', 'values': L(qyoy[qw]), 'yfmt': 'pct0'},
        'qtr_months': 3,
    }
    if n_in_last < 3:
        exq['partial_months'] = n_in_last
        exq['src_extra'] = ('Latest bar is quarter-to-date and not comparable to full quarters')
    exq['note'] = (f'柱为季内**月度 ADV 的均值**（不是季度合计）—— ADV 本身已是「每日」口径，'
                   f'加总没有意义。y/y 与上年同季比。'
                   f'最新季 {qi[-1]} 已含 {n_in_last} 个月'
                   + ('（完整季）' if n_in_last >= 3 else '，为季度至今、与完整季不可比')
                   + f'，{qv[-1]:.1f} mn/日，同比 {qyoy[-1]:+.0f}%。')
    ex.append(exq)

    # ── Exhibit 9a/9b：Non-options franchises（gsx.multi_line → 拆成两张单序列图）──
    # 原 deck 把「十亿股/日」「EUR bn/日」「$bn/日」三种单位画在同一根轴上，标题写
    # mixed units。三条线的量级是 2 : 15 : 64，最小的那条（美股撮合）振幅只占画布的
    # 0.9%，完全贴在零线上，读者看不出它有没有在动 —— 那条线是白画的。
    # 处理办法不是截轴：截轴的前提是「主体在轴内、个别离群点出界」，这里是三个不同
    # 量纲，25 个 FX 点会全部出界。不同量纲本来就不该同轴，所以拆开，各用各的轴与单位。
    # 只拆出两张：第三条（欧股 ADNV）与 Exhibit 11 是同一条序列、同一个 25 个月窗口，
    # 再画一张就是把同一份数据在同一页上画两遍，改为在图注里指过去。
    us_eq = col('adv_us_equities_matched_shares_bn', W25)
    eu_eq = col('adv_eu_equities_adnv_eurbn', W25)
    fx = col('adv_fx_adnv_usdbn', W25)
    # yfmt 必须显式给：轴刻度的默认格式器按步长取小数位，步长落在 2.5 这一档时会把
    # 7.5 / 12.5 印成 8 / 13（Exhibit 6 原来就是这么错的），按标签量线会系统性偏半档。
    NONOPT = [
        ('9a', 'U.S. equities matched volume', 'bn shares / day', 'NAVY', us_eq, 'f2', 'f1',
         'Matched shares on Cboe U.S. equities exchanges',
         'adv_us_equities_matched_shares_bn'),
        ('9b', 'Global FX ADNV', '$bn / day', 'GREEN', fx, 'f1', 'f0',
         'Average daily notional value, USD', 'adv_fx_adnv_usdbn'),
    ]
    for nn, ttl, unit, colr, vv, ff, yf, sx, cname in NONOPT:
        ex.append({
            # yfloor=0：成交量/成交金额恒正，默认下界会掉到零轴以下（同 Exhibit 7）。
            'n': nn, 'kind': 'lines_endlabels', 'fmt': ff, 'yfmt': yf,
            'yfloor': 0, 'xlabels': XL25,
            'title': ttl, 'ylab': unit,
            'series': [{'name': ttl, 'color': colr, 'values': L(vv)}],
            'src_extra': sx,
            'note': f'原 deck 的 Exhibit 9 把美股撮合（十亿股/日）、欧股 ADNV（EUR bn/日）、'
                    f'全球外汇 ADNV（$bn/日）三种单位画在同一根轴上，量级 2 : 15 : 64，'
                    f'最小的那条被压得与横轴分不开。三种量纲不该同轴，故拆开各自成轴'
                    f'（窗口、线型、数值均未改）；第三条欧股 ADNV 就是 Exhibit 11 的那条'
                    f'序列（同一个 {WIN_LONG} 个月窗口），不再重画。'
                    f'{XL25[0]} {comma(vv[0], 2 if ff == "f2" else 1)} → '
                    f'{XL25[-1]} {comma(vv[-1], 2 if ff == "f2" else 1)}（{unit}），'
                    f'同比 {pctf(yoy(df[cname].values.astype(float)))}、'
                    f'环比 {pp(mom(df[cname].values.astype(float)))}。',
        })

    # ── Exhibit 10：Futures (CFE) ADV（gsx.lvl_bar, show_mom=True → gs_bar）──
    fut = col('adv_futures_kcontracts', W25)
    fut_all = df['adv_futures_kcontracts'].values.astype(float)
    ex.append({
        'n': 10, 'kind': 'gs_bar', 'fmt': 'f0c', 'xlabels': XL25,
        'title': 'Futures (CFE) ADV',
        'ylab': 'k contracts / day', 'ylab2': '% y/y', 'legend': 'Monthly',
        'values': L(fut),
        'yoy': yoy_rhs(df['adv_futures_kcontracts'], W25),
        'note': f'CFE（Cboe Futures Exchange）合计，主体是 VIX 期货。金色折线 = 次轴同比'
                f'（同原 deck）。本图的同比在 ±36% 之间跨零，柱又全为正，两轴零点若强行'
                f'对齐会浪费掉约一半画布，引擎因此改成两轴各自缩放并在图内左上角标出'
                f'「左右轴零点不同高」——<b>柱与折线的零线不在同一高度，不要按同一条水平线读</b>。'
                f'原 deck 对本图额外开了环比气泡（show_mom=True）：同比已经饱和时，'
                f'月度动能只能从环比看 —— 网页版的环比气泡带一条指向第 12 根柱的箭头'
                f'（为 13 个月窗口写死的），在本图 {WIN_LONG} 根柱的窗口下会指错柱，故不画，'
                f'环比改写在这里。{mlab(LATEST)} {comma(fut[-1], 0)}k 张/日，'
                f'同比 {pctf(yoy(fut_all))}、环比 {pp(mom(fut_all))}。',
    })

    # ── Exhibit 11：European equities ADNV（gsx.lvl_bar → gs_bar）──
    eu_all = df['adv_eu_equities_adnv_eurbn'].values.astype(float)
    ex.append({
        'n': 11, 'kind': 'gs_bar', 'fmt': 'f1', 'xlabels': XL25,
        'title': 'European equities ADNV',
        'ylab': 'EUR bn / day', 'ylab2': '% y/y', 'legend': 'Monthly',
        'values': L(eu_eq),
        'yoy': yoy_rhs(df['adv_eu_equities_adnv_eurbn'], W25),
        'note': f'Cboe Europe 的平均每日成交金额（ADNV，欧元计价，非合约张数）。'
                f'金色折线 = 次轴同比（同原 deck）。'
                f'{mlab(LATEST)} €{eu_eq[-1]:.1f} bn/日，同比 {pctf(yoy(eu_all))}、'
                f'环比 {pp(mom(eu_all))}。原 deck 的 Exhibit 9 里那条欧股线就是本图的序列'
                f'（同一个 {WIN_LONG} 个月窗口），拆图时没有再单画一张。',
    })

    # ── Exhibit 12：Index options share heat matrix（gsx.heat_matrix → heat_matrix，通栏）──
    share_all = df['index_share']
    years = sorted({p.year for p in share_all.dropna().index})[-HEAT_YEARS:]
    M = [[None] * 12 for _ in years]
    for p, v in share_all.dropna().items():
        if p.year in years:
            M[years.index(p.year)][p.month - 1] = round(float(v), 6)
    # heat_matrix 不支持 break_at（矩阵没有连续 x 轴），口径警告只能落在图注上；
    # 但那一句必须跟着「pro-forma 那一年还在不在矩阵里」走，否则 2027 年 2017 滚出
    # 10 年窗口之后，这句话会把 2018 年错说成 pro-forma 口径。
    pf_in_heat = PF_YEAR in years
    heat_pf = (f'⚠️ {PF_YEAR} 年（首行）为 Bats pro-forma combined 口径，'
               f'与其后年份不完全可比。' if pf_in_heat else '')
    ex.append({
        'n': 12, 'kind': 'heat_matrix', 'full': True,
        'title': 'Index options share of U.S. options ADV (%)',
        'rows': [str(y) for y in years],
        'cols': ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug',
                 'Sep', 'Oct', 'Nov', 'Dec'],
        'matrix': M, 'fmt': 'f0', 'legend': 'Index options share of U.S. options ADV (%)',
        'row_head': '年',
        'src_extra': 'Green = richer mix (index options earn far higher RPC)',
        'note': f'格内为「自有指数期权 ADV ÷ 美国期权总 ADV」的百分数，色标取全部有限值的 '
                f'5/95 分位（与原 deck 的 RdYlGn 一致，绿=高、红=低）。' + heat_pf +
                f'{years[0]} 均值 {np.nanmean([v for v in M[0] if v is not None]):.0f}% → '
                f'{years[-1]} 年至今均值 '
                f'{np.nanmean([v for v in M[-1] if v is not None]):.0f}%。',
    })

    # ── Exhibit 13：核对表（官方原始单位，不做任何换算）──
    TCOLS = [
        ('U.S. options ADV (k)', 'us', 'adv_us_options_kcontracts', 0, ''),
        ('Index options (k)', 'ix', 'adv_index_options_kcontracts', 0, ''),
        ('SPX (k)', 'spx', 'adv_spx_options_kcontracts', 0, ''),
        ('VIX options (k)', 'vix', 'adv_vix_options_kcontracts', 0, ''),
        ('XSP (k)', 'xsp', 'adv_xsp_options_kcontracts', 0, ''),
        ('Multiply-listed (k)', 'ml', 'adv_multilist_options_kcontracts', 0, ''),
        ('Futures ADV (k)', 'fut', 'adv_futures_kcontracts', 0, ''),
        ('U.S. equities (bn shares)', 'useq', 'adv_us_equities_matched_shares_bn', 2, ''),
        ('EU equities ADNV (EURbn)', 'eueq', 'adv_eu_equities_adnv_eurbn', 2, ''),
        ('Global FX ADNV ($bn)', 'fx', 'adv_fx_adnv_usdbn', 1, ''),
        ('RPC U.S. options ($)', 'rus', 'rpc_us_options_usd', 3, '$'),
        ('RPC index options ($)', 'rix', 'rpc_index_options_usd', 3, '$'),
        ('RPC multiply-listed ($)', 'rml', 'rpc_multilist_options_usd', 3, '$'),
    ]
    trows = []
    for p in W13:
        r = {'xl': mlab(p)}
        for _, key, cname, dec, money in TCOLS:
            v = df[cname].get(p, np.nan)
            r[key] = comma(v, dec, money) if np.isfinite(v) else None
        trows.append(r)
    table = {
        'n': 13,
        'title': f'近 {WIN_SHORT} 个月月度指标核对表（官方原始单位，未换算）',
        'idx': '月份',
        'cols': [[c[0], c[1]] for c in TCOLS],
        'rows': trows,
    }

    # ── 抬头与一行数据条 ──
    adv_l = float(df['adv_us_options_mn'].iloc[-1])
    ix_l = float(df['adv_index_options_mn'].iloc[-1])
    sh_l = float(df['index_share'].iloc[-1])
    rpc_l = float(df['rpc_us_options_usd'].loc[LATEST_RPC])
    rev_l = float(df['opt_rev_day_usdmn'].loc[LATEST_RPC])
    fut_l = float(df['adv_futures_kcontracts'].iloc[-1])

    # 抬头一律**同比与环比都写**：只写同比的话，同比在高位、环比在跌的月份会给出一个
    # 纯正面的印象，读者要翻到 Exhibit 1 才知道环比掉了多少（hkex / msci 两页本来就
    # 两个都写，cme / cboe 原来只写同比，同一套页面口径不一致）。
    # Implied 收入与 RPC 同口径月（滞后一期），月份标记不能省 —— 卡片头写的是 LATEST，
    # 不标月份读者会把它当成最新月的数。
    headline = (f'美国期权 ADV {adv_l:.1f}mn/日（{pctf(yoy(adv_all))} y/y、'
                f'{pp(mom(adv_all))} m/m）· '
                f'自有指数期权 {ix_l:.1f}mn/日、占比 {sh_l:.0f}% · '
                f'美国期权 RPC {comma(rpc_l, 3, "$")}（{mlab(LATEST_RPC)}，三个月滚动）· '
                f'Implied 期权交易收入 {comma(rev_l, 2, "$")}mn/日（{mlab(LATEST_RPC)}）· '
                f'CFE 期货 ADV {fut_l:,.0f}k/日（{pctf(yoy(fut_all))} y/y、'
                f'{pp(mom(fut_all))} m/m）')
    # 首页卡片把 through_label（=LATEST 月）紧贴这一行渲染，读者会把三个指标一并归到
    # 最新月；RPC 却滞后一期（口径月 = LATEST_RPC）。口径月必须留在卡片上，否则与本页
    # Exhibit 1「最新月 RPC 单元格为空」直接冲突。「三个月滚动」这半句舍在子页 headline
    # 与 notes 里 —— 一并写进来会到 66 字，破 CONTRACT 的 hub_line ≤60 字上限。
    hub_line = (f'美国期权 ADV {adv_l:.1f}mn/日（{pctf(yoy(adv_all))} y/y）· '
                f'指数期权占比 {sh_l:.0f}% · RPC {comma(rpc_l, 3, "$")}'
                + (f'（{mlab(LATEST_RPC)}）' if LATEST_RPC != LATEST else ''))

    # 「图注说画了断点线，图上就必须真有」：本页唯一的结构性断点是 2017 pro-forma，
    # 只有 Exhibit 6 是连续 x 轴、画得出 break_at；Exhibit 12 是热力矩阵，引擎不支持
    # break_at，只能靠文字。这里从 payload 现读「谁真的画了线」，而不是写死编号 ——
    # 源文件哪天回补/裁剪到 2018 起，断点滚出全历史窗口，这段话要跟着消失。
    summary = summary_block(df, LATEST, LATEST - 1, LATEST - 12)
    _blank_why = summary.pop('blank_why')      # 只用来生成表注，不进页面 payload

    _brk_drawn = [str(e['n']) for e in ex if e.get('break_at') is not None]
    if _brk_drawn:
        _brk_note = (f'<b>⚠️ 口径断点：{PF_YEAR} 年为 Bats pro-forma combined。</b>'
                     f'Cboe 于 2017-02 完成对 Bats Global Markets 的收购，{PF_YEAR} 年的数字'
                     f'是合并模拟口径，与其后年份不完全可比。红色竖虚线画在 Exhibit '
                     + '、'.join(_brk_drawn) + f'（{mlab(ALL[BREAK_PF])} 的左缘，'
                     f'线左边那段才是异口径的一侧）；'
                     + (f'Exhibit 12 的热力矩阵首行同受影响，但矩阵没有连续横轴、'
                        f'画不出断点线，只能靠图注交代。' if pf_in_heat else '')
                     + '读长期趋势应从 2018 年起算。')
    else:
        # 断点已滚出所有窗口：不再声称画了线，也不再提它 —— 硬失败退出会让整页永久停更。
        _brk_note = (f'<b>口径断点已滚出所有窗口。</b>{PF_YEAR} 年的 Bats pro-forma combined '
                     f'口径不在当前任何一张图的横轴范围内，故本页不画断点线。')

    notes = [
        f'<b>数据源与节奏。</b>全部数值来自本仓 <code>series/cboe.csv</code>，'
        f'解析自 Cboe 官网 Monthly volume and revenue per contract (RPC) reports；'
        f'上月数据通常在次月第 3 个工作日发布。当前覆盖 {XL_LONG[0]} – {XL_LONG[-1]}，'
        f'共 {len(ALL)} 个月，逐月连续无缺口（生成脚本会对断月直接抛异常）。',

        f'<b>⚠️ RPC 是三个月滚动平均，且滞后一个月发布。</b>不是单月数。当前成交量已到 '
        f'{mlab(LATEST)}，RPC 只到 {mlab(LATEST_RPC)} —— 汇总表里空白的 RPC 单元格'
        f'（本月一列）不是数据缺口。Exhibit 3 与 Exhibit 4 的横轴同样以 {mlab(LATEST_RPC)} '
        f'结尾：窗口长度仍是 {WIN_LONG} 个月、与其他图等长，只是整体前移一个月'
        f'（{XL25R[0]} – {XL25R[-1]} vs 其他图 {XL25[0]} – {XL25[-1]}）。',

        _brk_note,

        '<b>Implied options transaction revenue（Exhibit 4）是推导值，不是披露值。</b>'
        '= 当月美国期权 ADV × 同月三个月滚动 RPC ÷ 1,000（$mn/日）。Cboe 是本站清单里'
        '唯一官方同时按月披露「量」与「单位价格」的标的，因此不必像其他券商那样假设一个'
        '季度费率；代价是 RPC 已被三个月平滑，本图的月度波动主要来自量而非价，'
        # notes 走 innerHTML，markdown 的 ** ** 不会被渲染，只会原样印出四个星号
        '且它是<b>每日</b>净交易收入的估算，要得到月度总额还需再乘当月交易日数。',

        f'<b>Mix 比总量更值钱。</b>自有指数期权（SPX / VIX / XSP）的 RPC 约为多重挂牌期权的 '
        f'{ratio:.0f} 倍（{mlab(LATEST_RPC)}：{comma(rpc_ix[-1], 3, "$")} vs '
        f'{comma(rpc_ml[-1], 3, "$")}），所以 Exhibit 5 的占比线与 Exhibit 12 的热力矩阵'
        f'对收入的解释力大于 Exhibit 2 的总量。',

        '<b>Exhibit 9 已拆开。</b>原 deck 把美股撮合（十亿股/日）、欧股 ADNV（EUR bn/日）、'
        '全球外汇 ADNV（$bn/日）三条线画在同一根轴上，量级是 2 : 15 : 64，最小的那条振幅'
        '只占画布的 0.9%、完全贴在零线上，等于白画。三种量纲本来就不该同轴，也不能靠截轴救'
        '（截轴的前提是主体在轴内、个别点出界，这里是 25 个 FX 点会全部出界），所以拆成 '
        'Exhibit 9a（美股撮合）与 9b（全球外汇）各自成轴；第三条欧股 ADNV 与 Exhibit 11 '
        '是同一条序列、同一个 25 个月窗口，不再重画一张。窗口、线型、数值一概未改。',

        '<b>Exhibit 8 的季度柱是月度 ADV 的均值，不是合计。</b>ADV 本身已经是「每日平均」'
        '口径，把三个月加起来没有意义。末季未满 3 个月时该柱会变浅蓝并在图例标出，'
        '同时右轴 y/y 的最后一点由图表引擎强制作废（拿 2 个月比上年完整 3 个月必然砸出假坑）。',

        '<b>与原 PDF deck 的四处有意差异（都只影响画法，不影响数值）。</b>'
        '(1) Exhibit 7 原 deck 用对数轴把 SPX / VIX / XSP 三条量级差很大的线拉开，'
        '网页图表引擎只有线性轴，XSP 与 VIX 在图上被压扁 —— 要读它们自己的走势请点右上角「表格」。'
        '该图的纵轴已改为从 0 起：合约张数不可能为负，而线图的默认下界会掉到 −1,000 千张/日。'
        '(2) Exhibit 6 原 deck 在末 3 个月画了一个红色虚线椭圆，网页版没有这个元件，'
        '改在图注里点名最近 3 个月的读数；纵轴与 deck 一样从 0 起、末点标数值。'
        '(3) Exhibit 7 的纵轴单位由「百万张/日」改为「千张/日」：百万张口径下 XSP 只剩'
        '「0.23」两位有效数字，而三条线共用一个格式器。数值本身不变（× 1,000）。'
        'Exhibit 3 曾因同样理由改成美分，引擎补上 3 位小数格式器后已换回原 deck 的「美元/张」。'
        '(4) Exhibit 9 拆成 9a/9b（见上一条）。'
        '除此之外图的顺序、编号、标题、窗口长度与图注均照搬原 deck。',

        '<b>柱图的次轴同比（Exhibit 2 / 4 / 10 / 11）。</b>金色折线是同比，与原 deck 一致；'
        '这四张图早先画的是 12 个月滚动均线，那只是把柱子再平滑一遍、不带新信息，'
        '而同比回答的是「相对去年这个月是好是坏」。基数过小（不足序列中位绝对值的 15%）'
        '或两期异号时该点留空，不硬算一个几百个百分点的假同比。'
        '双轴图的规矩是两轴零点画在同一高度，代价过大时引擎改为两轴独立缩放并在图内注明 —— '
        '本页 Exhibit 10 命中这一条，读它的柱与线时不要按同一条零线对齐。',

        '<b>汇总表读法。</b>「3Y %ile」= 当月读数在最近 36 个月里高于多少比例的观测'
        '（≥66 绿、≤33 红），由全站统一的 <code>build/pctile.py</code> 计算：'
        '把这一行的分位在近 24 个月里逐月回放，若 ≥70% 的月份都钉在 100 或 0，'
        '说明这一列对该指标没有区分度，留空。'
        + (('本月留空的行：' + '；'.join(f'{lab}（{why}）' for lab, why in _blank_why) + '。')
           if _blank_why else '本月没有留空的行。')
        + 'm/m 与 y/y 对分母为 0 或两期异号的情形留空。'
        '末尾核对表（Exhibit 13）保持官方原始单位（k 张/日、bn 股/日、EUR bn/日、$bn/日、$/张），'
        '不做任何换算，便于与公司披露逐条对账；列数较多，在窄屏上需要左右滚动。',
    ]

    payload = {
        'ticker': 'cboe',
        'tracker': 'Cboe Monthly Volume & RPC Tracker',
        'title': f'Cboe Global Markets (CBOE)：月度成交量与 RPC 跟踪 — '
                 f'{LATEST.year} 年 {LATEST.month} 月',
        'data_through': str(LATEST),
        'through_label': f'{LATEST.year} 年 {LATEST.month} 月',
        'subtitle': f'数据源：Cboe 官网 Monthly volume and revenue per contract (RPC) reports'
                    f'（次月第 3 个工作日）· 覆盖 {XL_LONG[0]} – {XL_LONG[-1]}（{len(ALL)} 个月）'
                    f'· 版式沿用 Goldman Sachs GIR monthly-metrics note · 只出图，不带观点',
        'headline': headline,
        # headline 之下、Exhibit 1 之上的 ~300 字解读。职责与 headline 互补：
        # 那一行给读数，这一段给「读数该怎么读」。见 compose_brief 的 docstring。
        # i0 传 BREAK_PF（首个非 pro-forma 月），与 Exhibit 6 的断点虚线同一个下标 ——
        # 排名的分母不能混进 2017 年的 Bats pro-forma combined 口径。
        # ALL 在本文件里是 pandas Period 的列表，brief.py 的月份口径是 'YYYY-MM' 字符串
        # （`B.mo()` 直接切片），所以在边界上转一次，不让 Period 漏进规则库。
        'brief': compose_brief(
            [str(p) for p in ALL], BREAK_PF or 0,
            df['adv_us_options_kcontracts'].values.astype(float),
            df['adv_index_options_kcontracts'].values.astype(float),
            df['rpc_us_options_usd'].values.astype(float),
            df['rpc_index_options_usd'].values.astype(float),
            df['rpc_multilist_options_usd'].values.astype(float),
            [(nm, df[c].values.astype(float)) for nm, c in BRIEF_LINES]),
        'hub_line': hub_line,
        'source': SRC,
        'xlabels': XL13,
        'xlabels_long': XL_LONG,
        'summary': summary,
        'exhibits': ex,
        'table': table,
        'notes': notes,
        'footer': 'Cboe Global Markets (CBOE) · monthly volume and RPC reports · '
                  'charts only, no commentary · 个人研究用，不构成投资建议',
    }
    # 表注只说这张表里的数说得着的事。原来这里还有一句「2017 figures are Bats pro-forma
    # combined」—— 本表只有本月/上月/去年同月三列 + 36 个月分位，窗口最早也只到 2023，
    # 2017 的口径与表里任何一个数都无关，那句话留着只会让人以为表里混了 pro-forma 数。
    payload['summary']['note'] = (
        f'Volume through {mlab(LATEST)}; RPC through {mlab(LATEST_RPC)} — RPC is a three-month '
        f'rolling average published on a one-month lag, so blank RPC cells are not a data gap. '
        f'3Y %ile = 当月读数在最近 36 个月中的分位（口径见下方「汇总表读法」）。'
    )

    # 抬头右侧「官方发布于 X」。台账按月钉死（fetch 入库时从 xlsx 的 "Updated on …" 记下），
    # 所以只查 LATEST 这一个月：cache/ 里可能躺着比 LATEST 更新的一期，现解析会把新一期的
    # 发布日安到旧月份的数据上。查不到就**整个字段不写** —— 渲染端判的是字段在不在，
    # 给它 None 或空串会印出一句没有内容的断言。
    src_day = repo.source_date('cboe', str(LATEST))
    if src_day:
        payload['source_date'] = src_day

    # 写出前先过 CONTRACT §5.5 护栏（NaN/Infinity 一律拒写）；首行注释与序列化都在里面。
    payload_guard.write_dash(OUT, payload, 'cboe')

    print(f'数据 {ALL[0]} → {LATEST}（{len(ALL)} 个月）；RPC 至 {LATEST_RPC}')
    print(f'Exhibit 1 汇总表 + Exhibit {ex[0]["n"]}-{ex[-1]["n"]}（{len(ex)} 张图）'
          f' + Exhibit {table["n"]} 核对表')
    print(f'写出 {OUT}  ({os.path.getsize(OUT) / 1024:.1f} KB)')
    print(headline)


if __name__ == '__main__':
    main()
