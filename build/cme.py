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
import importlib.util
import json
import os

import numpy as np
import pandas as pd

import brief as B
import axisfmt
import mrwin                            # 通栏 / x 标签抽稀的裁决层，与 single.py 共用
import payload_guard
import pctile
import yoy as YOY                       # 同比口径的唯一实现，见 build/yoy.py 的模块头

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SERIES = os.path.join(ROOT, 'series')
OUT = os.path.join(ROOT, 'data', 'cme.js')

# 发布日台账在仓库根，不在 build/ —— `python3 build/cme.py` 时 sys.path 上只有 build/，
# 裸 import 找不到，只能按路径加载。
_sd_spec = importlib.util.spec_from_file_location(
    'source_dates', os.path.join(ROOT, 'source_dates.py'))
source_dates = importlib.util.module_from_spec(_sd_spec)
_sd_spec.loader.exec_module(source_dates)

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
# 20/21 是后加的两张（量价分解与 TTM 量），一律**追加在末尾**，前面的号一个都没动；
# 核对表因此由 20 顺延到 22 —— 它本来就排在所有图之后，号跟着走才不会出现
# 「18、19、22、20、21」这种读者以为漏图的序列。全文引用一律走这些常量。
EX_DECOMP, EX_TTMVOL = 20, 21
EX_TABLE = 22

#: **末尾核对表**的行数 —— 这是表的窗口，不是任何一张图的窗口。表的用途是拿着它和
#: 公司披露逐行对，127 行没人对得完，所以它留在 13 个月。
#: （2026-08-19 之前这个常量叫 WIN_BAR，同时管着九张 gs_bar 与 Exhibit 4 的堆叠柱。）
WIN_TABLE = 13
#: 所有**时序图**的窗口左端。2026-08-18 曲线类先从「近 25 个月」改成「2016-01 起」，
#: 2026-08-19 gs_bar / stacked_dual 类跟上，全站统一
#: （build/single.py 的 WIN_FROM、build/cboe.py 同名常量、build/msci.py 的 WIN0 都是这一个）。
#: 本页序列自 2008-01 起，所以这里实际拿到 127 期；序列比它短的家用序列自己的起点。
#: 变量名保留 WIN_LINE 是因为它还被 `win(col, n)` 当「取末 n 期」的参数用（见下）。
#:
#: gs_bar 类原先停在 13 个月，注释写的理由是契约 §5.4「近期图**固定** 13 个月」。
#: 本页是**有意不照那条办**，而不是把「固定」读成「至少」—— 该条的括注（「够算 y/y
#: 首末对比与 prior-12mo 均值」）说的是 13 个月为什么够用，没有说更长不行；而本页同一份
#: series/cme.csv 里 2008-01 起的数一直都在（Exhibit 7 就画着 223 个月），13 个月是
#: **画的时候截的**，不是数据没有。§5.4 本身该不该改，由 build/CONTRACT.md 的持有者
#: 裁决（本文件不去数别的页面现在停在几个月 —— 把跨页统计写进本页注释，就是给它
#: 安一个必然过期的实测数），本文件不动那份契约，
#: 只在页尾 notes 的「与原 PDF 版的有意差异」条里把冲突写给读者看。
WIN_FROM = '2016-01'
#: 2026-08-19：`WIN_QTR = 14`（季度柱照搬原 deck 的 win=14）已删除。Exhibit 8 与
#: Exhibit 14 都改吃 `Q_FROM`（= WIN_FROM 换算到季度），本页不再有第二个窗口常量 ——
#: 留一个只在一处用得上的旧窗口常量，下一次放宽时又会漏掉它（这次就漏了）。
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


# ══════════════════ 同比口径：次轴一律画 12 个月滚动合计同比 ══════════════════
# 单月同比 = 本月 ÷ 去年同月 − 1，它把「去年那**一个**月碰巧是什么样」整个塞进分母。
# 去年同月若是异常低点，今年一个平淡的月份也能印出三位数的增速；反过来同理。后果不是
# 「噪声大一点」，而是**方向会反**：同一条序列的单月同比与 12 个月滚动合计同比经常符号
# 相反，图上讲的是反的故事，而读者从图上完全看不出来。本页的实测数字由 caliber_stats()
# 现算（见 NOTES 的口径条与各图图注），一个都没有写死。
#
# 因此本页所有 gs_bar 的次轴金色折线改画「12 个月滚动合计同比」：
#     最近 12 个月合计 ÷ 上一个 12 个月合计 − 1
# 实现上取滚动**均值**再相比 —— 窗口固定 12 个月，除以 12 是同一个常数，所以
# 「滚动均值同比」与「滚动合计同比」逐点严格相等；用均值的好处是对 ADV 这类日均值源列
# 单位不变（仍是「千张/日」），读者不必在脑子里换算。
#
# 要不要乘交易日数？**不乘。** 本页 Exhibit EX_DAYCOUNT 的既定立场是「ADV 已按交易日
# 中性化」，而实测（DAYCOUNT_STATS）显示交易日效应在 12 个月窗口里基本自抵：日均口径与
# 交易日加权口径的滚动同比标准差只差零点几个百分点、符号相反的月份集合完全相同。为这点
# 差别在同一页里引入第二套聚合口径，代价远大于收益 —— 而「同一页两套同比口径」正是读者
# 会把不可比的数放在一起读的地方。
# ⚠ **存量序列不适用**。month-end OI 这类期末快照走的是点对点同比（YOY.mom_yoy）：
# 把 12 个月末的 OI 加起来不是任何东西 —— 既不是「一年的量」（存量不累积），也不是
# 「平均水平」（没除以 12）。而且存量本来就不吃日历效应，单月同比在它上面稳得多
# （本页实测 OI 的两种口径标准差只差 1.2 倍，成交量类差 2 倍以上）。
# 判据与实现都在 build/yoy.py，本文件只负责说清「这一列是流量还是存量」。
ROLL = 12


def roll_yoy(s):
    """12 个月滚动合计同比（%），**流量序列专用**。委托给 build/yoy.py。

    前 23 个点必然为 NaN：12 个月填窗 + 12 个月比较。
    滚动合计与滚动均值的同比逐点严格相等（除以 12 是同一个常数），所以对 ADV 这类
    日均值源列，读者可以把它读成「近 12 个月的平均 ADV 相对上一个 12 个月」。
    """
    return YOY.ttm_yoy(pd.Series(s), YOY.FLOW)


def caliber_stats(s, kind=YOY.FLOW):
    """单月同比 vs 12 个月滚动合计同比的实测对比（图注里引用的数字全由此现算）。

    只做键名适配：真正的统计（样本对齐、相邻月跳变、符号相反的月份）全部走
    build/yoy.py 的 caliber_diff —— 那是全站唯一实现，各页各写一份正是同一条序列
    在两页被判定相反的原因。样本对齐这一步尤其不能自己重写：滚动同比比单月同比少
    12 个月历史，不取交集就会把「样本不同」读成「口径不同」。
    """
    d = YOY.caliber_diff(pd.Series(s), kind)
    opp = pd.DataFrame([{'m': m, 'r': r} for _, m, r in d['opposite']],
                       index=[p for p, _, _ in d['opposite']])
    return {
        'n': d['n'], 'first': d['months'][0], 'last': d['months'][-1],
        'sd_m': d['std_mom'], 'sd_r': d['std_ttm'],
        'jump_m': d['maxjump_mom'][0], 'jump_m_at': d['maxjump_mom'][2],
        'jump_r': d['maxjump_ttm'][0] if d['maxjump_ttm'] else float('nan'),
        'n_opp': d['opposite_n'], 'opp': opp,
    }


CALIB = caliber_stats(adv)                       # 总 ADV：全页的口径样本（流量）
CALIB_OI = caliber_stats(df['oi_total_contracts'], YOY.STOCK)   # 月末未平仓：存量对照样本
# 交易日加权 vs 日均：同一条量在两种聚合口径下的滚动同比差多少（决定「要不要乘交易日」）
DAYCOUNT_STATS = caliber_stats(df['total_vol_mn'])
_c_adv, _c_vol = roll_yoy(adv), roll_yoy(df['total_vol_mn'])
_c_both = pd.concat([_c_adv, _c_vol], axis=1, keys=['a', 'v']).dropna()
DC_MAXGAP = float((_c_both['a'] - _c_both['v']).abs().max())
DC_SAME_SIGN = bool(((_c_both['a'] * _c_both['v']) > 0).all())

# 每张改口径的图都要自己说清楚新口径与理由；完整实测放在 NOTES 里，这里给一句压缩版。
YOY_CAL = (f'<b>次轴 = 12 个月滚动合计同比</b>（最近 12 个月合计 ÷ 上一个 12 个月合计 − 1），'
           f'不是单月同比。理由是本页自己的实测：总 ADV 的单月同比在 {CALIB["n"]} 个可比月里'
           f'有 {CALIB["n_opp"]} 个月（{CALIB["n_opp"] / CALIB["n"] * 100:.0f}%）'
           f'与滚动口径<b>符号相反</b>，相邻月最大跳变 {CALIB["jump_m"]:.0f}pp'
           f'（滚动口径 {CALIB["jump_r"]:.0f}pp）。折线要等 24 个月才有第一个点'
           f'（12 个月填窗 + 12 个月比较），窗口左端因此可能没有线。')

# 存量图（月末未平仓合约）的对应说明：它**不改**口径，但必须说清为什么不改，
# 否则读者会以为漏改了一张，或者把它的折线和别的图的滚动折线放在一起比。
STOCK_CAL = (f'<b>次轴 = 单月同比</b>（本月 ÷ 去年同月 − 1），与本页成交量各图的 '
             f'12 个月滚动合计同比<b>不是一个口径</b>，两者不要放在一起比高低。'
             f'这里之所以不改：未平仓合约是<b>存量</b>（月末快照），'
             f'把 12 个月末的存量加起来不是任何东西 —— 既不是「一年的量」（存量不累积），'
             f'也不是「平均水平」（没除以 12）；而且存量不吃日历效应（不像成交量要看'
             f'当月有几个交易日），单月同比在它上面本来就稳得多。'
             f'本页实测：未平仓合约的单月同比标准差 {CALIB_OI["sd_m"]:.1f}pp、'
             f'相邻月最大跳变 {CALIB_OI["jump_m"]:.0f}pp，而总 ADV 是 '
             f'{CALIB["sd_m"]:.1f}pp 与 {CALIB["jump_m"]:.0f}pp —— 差着一个量级，'
             f'所以成交量非平滑不可，存量不必。判据与实现见 <code>build/yoy.py</code>。')

RPC = rpc_quarterly([('total', 'rpc_total'), ('rates', 'rpc_interest_rates'),
                     ('equity', 'rpc_equity_indexes'), ('energy', 'rpc_energy'),
                     ('metals', 'rpc_metals')])
rpc_m = to_monthly(RPC['total'], df.index)
df['implied_txn_rev_usdmn'] = df['total_vol_mn'] * rpc_m    # 百万张 x $/张 = $mn
RPC_Q, RPC_V = RPC['total'].index[-1], float(RPC['total'].iloc[-1])

# ══════════════════ TTM 序列（量价分解与 Exhibit EX_TTMVOL 共用）══════════════════
# 均价一律用「合计 ÷ 合计」定义，绝不用「逐月 RPC 的均值」——
# 后者对每个月等权，而各月的成交量差着一倍以上；更要命的是均值之积 ≠ 积之均值，
# 拿它做分解，两块相加就对不上总增长，而图上完全看不出来。
df['ttm_vol_mn'] = YOY.ttm(df['total_vol_mn'], YOY.FLOW)           # 近 12 个月成交合约数
df['ttm_rev_usdmn'] = YOY.ttm(df['implied_txn_rev_usdmn'], YOY.FLOW)
df['ttm_rpc_usd'] = df['ttm_rev_usdmn'] / df['ttm_vol_mn']         # 近 12 个月混合 RPC

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

W_TBL = df.index[-WIN_TABLE:]        # 只给末尾核对表用
_I0 = next((i for i, p in enumerate(df.index)
            if f'{p.year}-{p.month:02d}' >= WIN_FROM), 0)
W25 = df.index[_I0:]
WIN_LINE = len(W25)          # 下面 win(col, WIN_LINE) 与图注里的「N 个月」都跟着它走
XL25 = [mlab(p) for p in W25]
XL_LONG = [mlab(p) for p in df.index]
# 季度轴的左端：与 WIN_FROM 同一个月份，换算到季度（'2016-01' → 2016Q1）。
# 写成换算而不是写死 '2016Q1'，是为了 WIN_FROM 哪天再动时季度图跟着一起动。
Q_FROM = pd.Period(WIN_FROM, freq='M').asfreq('Q')


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
        'note': (
                 # 表的三列就是三个具体月份（本月 / 上月 / 去年同月），y/y 只能是这两个
                 # 具名月份之比 —— 换成 12 个月滚动值，列头写的月份与格里的数就对不上了。
                 # 所以这一列保留单月口径，但必须点名，否则读者会拿它和各图次轴的滚动同比
                 # 直接对照，那是两个不同的量。
                 '<b>本表的 y/y 是单月同比</b>（本月 ÷ 去年同月 − 1），'
                 f'与各图次轴的 12 个月滚动合计同比不是一个口径：本表三列写死的就是'
                 f'「本月 / 上月 / 去年同月」这三个具名月份，滚动值放进来与列头自相矛盾。'
                 f'单月同比有多毛：本页总 ADV 的实测是 {CALIB["n"]} 个可比月里 '
                 f'{CALIB["n_opp"]} 个月与滚动口径符号相反。要判趋势请看各图的次轴金色折线'
                 f'与 Exhibit {EX_TTMVOL}，本表回答的是「本月相对上月与去年同月的水平」。'
                 'ADV is already day-count neutral; total contracts traded is not. '
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
def yoy_line(col, win_n=WIN_LINE, kind=YOY.FLOW):
    """次轴折线的数值。流量走 12 个月滚动合计同比，存量走点对点同比（见 ROLL 那一段）。

    引擎不替我们算同比 ——「这一点的同比有没有意义」是口径判断，只能在 Python 侧做。
    """
    s = YOY.ttm_yoy(df[col], kind) if kind == YOY.FLOW else YOY.mom_yoy(df[col], kind)
    return L(s.values[-win_n:])


def gs_bar(n, col, title, ylab, fmt, legend, note=None, src_extra=None, kind=YOY.FLOW):
    """← gsx.lvl_bar：浅蓝柱 + **次轴金色 y/y 折线**。窗口 `WIN_FROM` 起（本页 127 期）。

    2026-08-19 窗口由 13 个月放到 2016-01 起。原来的 13 个月不是数据下限：同一份
    series/cme.csv 从 2008-01 起就是满的（Exhibit 7 画着 223 个月），13 是**画的时候
    截的**。契约 §5.4 写的是「近期图**固定** 13 个月」，本页是有意不照它办、不是把
    「固定」读成「至少」；这处冲突写在页尾 notes 的「与原 PDF 版的有意差异」条里，
    §5.4 本身该不该改由 build/CONTRACT.md 的持有者裁决。127 期塞不进半栏卡片，
    通栏与 x 标签抽稀交给 `mrwin.layout_all()` 按 charts.js 的量边距算式判，不在这里拍。

    次轴画的是同比而不是 12 个月滚动均线 —— gsx.lvl_bar 的 docstring 写死了这条理由：
    「均线只是把柱子再平滑一遍、不带新信息，同比才回答『相对去年这个月是好是坏』」。
    本页九张 gs_bar 全部由 build_cme.py 的 gsx.lvl_bar 移植而来，所以与 deck 对齐：
    给 yoy 就不画均线（引擎侧自动），同时不再需要左上角那个 y/y 气泡。

    2026-08 改口径：**流量**序列那条折线由单月同比改为 12 个月滚动合计同比。轴标题与
    图例名一并改掉 —— 只改数不改名，读者会拿一条已经被平滑过的线当单月同比读，
    那比不改更糟。每张图的 note 都追加对应的压缩版口径说明（带本页实测数字）。

    kind=STOCK 的图（月末未平仓合约）**不改**：存量不可加总，且它本来就不吃日历效应，
    单月同比在它上面已经足够稳（判据与实现见 build/yoy.py）。这类图的轴名写「单月」，
    与滚动口径的图区分开。
    """
    roll = (kind == YOY.FLOW)
    ex = {'n': n, 'kind': 'gs_bar', 'title': title, 'fmt': fmt, 'ylab': ylab,
          'ylab2': '% y/y, 12M roll.' if roll else '% y/y, single month',
          # xlabels 必须显式给：不给就退到 payload 的页级默认，而 mrwin.layout_all()
          # 只对**自带 xlabels** 的 exhibit 判通栏与抽稀，漏给等于这张图不过排版裁决。
          'legend': legend, 'xlabels': XL25, 'values': L(win(col, WIN_LINE)),
          'yoy': {'name': '12M rolling y/y (RHS)' if roll else 'y/y, single month (RHS)',
                  'color': 'GOLD', 'yfmt': 'pct0',
                  'values': yoy_line(col, win_n=WIN_LINE, kind=kind)}}
    cal = YOY_CAL if roll else STOCK_CAL
    ex['note'] = (note + ' ' + cal) if note else cal
    if src_extra:
        ex['src_extra'] = src_extra
    return ex


ex = []

ex.append(gs_bar(EX_ADV, 'adv_mn', 'Total average daily volume', 'mn contracts / day', 'f1',
                 'Total ADV'))

ex.append({
    'n': EX_DAYCOUNT, 'kind': 'lines_endlabels', 'fmt': 'f1', 'xlabels': XL25,
    # 标题写明「single-month」：本图的命题就是「一个月内交易日数能把方向读反」，
    # 换滚动口径两条线就重合了、图就空了（本页口径改造时的判定）。CONTRACT §6 要求
    # 保留单月的图必须在标题声明 —— check_yoy_caliber 的 R4 判据认的就是标题。
    'title': 'Total volume vs. ADV growth: the day-count gap (single-month y/y)',
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
             f'（{days[CUR]:.0f} 天 vs 去年同月 {days[YAG]:.0f} 天）。'
             # 全页只有这一张（外加热力矩阵 EX_HEAT_YOY）保留单月同比。理由不是习惯，
             # 是这张图的命题本身：day-count 效应是**单月现象**，平滑掉它这张图就空了。
             f'<b>本图是全页唯一保留单月同比的折线图</b>（各 gs_bar 的次轴已改 12 个月滚动'
             f'合计同比；Exhibit {EX_QTR} 的季度柱是第三种口径 —— 本季 3 个月合计 vs '
             f'上年同季，见该图图注）：'
             f'这张图的全部命题就是「交易日数差异能在<b>一个月</b>之内把成交量的方向读反」'
             f'（Barclays 调整）。改成滚动口径这张图会自己消失 —— 实测：滚动口径下'
             f'两条线的逐月标准差是 {CALIB["sd_r"]:.1f}pp（按日）vs {DAYCOUNT_STATS["sd_r"]:.1f}pp'
             f'（总量），最大差 {DC_MAXGAP:.1f}pp，'
             + ('且逐月符号完全一致' if DC_SAME_SIGN else '仍有符号不一致的月份')
             + f'，12 个月窗口里交易日效应基本自抵。单月口径下同一对序列的标准差是 '
             f'{CALIB["sd_m"]:.1f}pp vs {DAYCOUNT_STATS["sd_m"]:.1f}pp。'
             f'读这两条线时请记住它们与其余各图的次轴<b>口径不同</b>，不要跨图比高低。'),
})

# stacked_dual 属 mrwin.DENSE：右轴那条占比线走 Catmull-Rom，窗口内出现一个 null 就会
# 被当 0 插值（还不报错）。六个品种列与总 ADV 在 load() 里已经逐列校验过「无缺值」，
# 2016-01 起的 127 期因此是满的 —— 下面的断言把这件事钉死，日后源文件缺一个月要在
# 构建期响，而不是在页面上画出一条塌到零的假线。
_stack = {c: win(c, WIN_LINE) for c, _, _ in CLS}
_share = (win('adv_rates_kcontracts', WIN_LINE) + win('adv_equity_kcontracts', WIN_LINE)) \
    / win('adv_total_kcontracts', WIN_LINE) * 100
_dense_holes = [nm for c, nm, _ in CLS if np.isnan(_stack[c]).any()]
if _dense_holes or np.isnan(_share).any():
    raise SystemExit(f'Exhibit {EX_MIX} 是平滑图型，窗口内不许有缺值：{_dense_holes or "占比线"}')
# 右轴上界取 10 的整数倍：占比线要压在堆叠柱之上，太高会掉进柱子里
_ymax = float(np.ceil(np.nanmax(_share) / 10.0) * 10)
if np.nanmax(_share) / _ymax > 0.995:
    _ymax += 10
# 六段之和 vs 披露的 Total ADV。窗口拉长后残差月份变多，图注里那句「加总即 Total ADV」
# 得带上实测残差，否则读者拿柱高去减总量会以为漏了一个品种。三件事必须分开数，
# 混成一个 `!= 0` 就会同时说错数和说错因（2026-08-19 那版图注写的「61 期差 1–2 千张」
# 正是这么来的，真值是 48 期）：
#   ① **浮点噪声不是差异。** 六列 float64 相加再相减，IEEE754 舍入残渣量级 ~1e-12 千张
#      （= 百万分之几张合约），`!= 0` 会把它算成「差」。判据因此带容差 _MIX_TOL = 0.0005
#      千张 = 0.5 张合约 —— 比实测噪声（~7e-9 张）大七八个数量级，又只有最小的真实
#      差异（1 张）的一半，两边都留着足够余量。
#   ② **「取整到千张」这个因果解释只对整千张的月份成立。** 所以不按残差大小分组，
#      而是按**源数据本身是不是整千张**分组（_mix_int 现验六列是否全为整数）：
#      是整数 ⇒ 舍入解释站得住；不是 ⇒ 官方给的就是三位小数，没有取整这回事。
#   ③ 剩下那组的零头（本页最大的一期差 472 张）另说，不套舍入解释。
# 三组的期数、量级、最大值一律现算，一个都不写死。
_mix_resid = (sum(_stack[c] for c, _, _ in CLS) - win('adv_total_kcontracts', WIN_LINE))
_mix_abs = np.abs(_mix_resid)
_MIX_TOL = 0.0005                       # 千张；0.5 张合约
_mix_int = np.array([all(float(_stack[c][i]).is_integer() for c, _, _ in CLS)
                     for i in range(WIN_LINE)])
_mix_eq = _mix_abs < _MIX_TOL           # 视同严格相等（含纯浮点噪声）
_mix_rnd = ~_mix_eq & _mix_int          # 整千张披露 ⇒ 差的是各自取整到千张的舍入
_mix_sub = ~_mix_eq & ~_mix_int         # 带小数披露 ⇒ 舍入解释不适用


def _mix_round_txt():
    """Exhibit 4 图注里那句残差说明。三组各自成句，缺哪组哪句就不出现。"""
    if not (_mix_rnd.any() or _mix_sub.any()):
        return (f'六段之和逐月严格等于披露的 Total ADV（{WIN_LINE} 期，'
                f'判据带 {_MIX_TOL * 1000:.1f} 张合约的容差，'
                f'滤掉六列浮点相加的舍入残渣）。')
    _tot = win('adv_total_kcontracts', WIN_LINE)
    _noise = _mix_abs[_mix_eq].max() * 1000 if _mix_eq.any() else 0.0
    out = [f'六段之和与披露的 Total ADV 在 {WIN_LINE} 期里有 {int(_mix_eq.sum())} 期相等'
           f'（判据带 {_MIX_TOL * 1000:.1f} 张合约的容差 —— 六列 float64 相加的舍入残渣'
           f'实测最大 {_noise:.0e} 张，直接拿 ≠0 去比会把它当成差异）。']
    if _mix_rnd.any():
        _lo, _hi = int(_mix_abs[_mix_rnd].min()), int(_mix_abs[_mix_rnd].max())
        _pmax = (_mix_abs / _tot * 100)[_mix_rnd].max()
        out.append(f'另有 {int(_mix_rnd.sum())} 期差 '
                   f'{_lo if _lo == _hi else f"{_lo}–{_hi}"} 千张'
                   f'（最大 {_hi} 千张 = 该月总量的 {_pmax:.3f}%）—— 这些月份 CME 六个品种'
                   f'披露的都是<b>整千张的整数</b>，差的就是各自取整到千张的舍入，'
                   f'不是漏了品种。')
    if _mix_sub.any():
        _j = int(np.where(_mix_sub, _mix_abs, -1.0).argmax())
        _c = np.round(_mix_abs[_mix_sub] * 1000).astype(int)
        out.append(f'还有 {int(_mix_sub.sum())} 期差不到 1 千张（逐期 {_c.min():,d}–'
                   f'{_c.max():,d} 张，最大的一期在 {XL25[_j]}）—— 这几期六个品种披露的是'
                   f'<b>带三位小数</b>的值、并没有取整到千张，上面那条舍入解释对它们'
                   f'不成立，零头出在哪一段官方没有交代。')
    out.append('本页对以上任何一种残差都不做配平，柱高一律是官方原值。')
    return ''.join(out)


_MIX_ROUND = _mix_round_txt()
ex.append({
    'n': EX_MIX, 'kind': 'stacked_dual', 'fmt': 'f0c', 'xlabels': XL25,
    'title': 'ADV mix by asset class',
    'ylab': 'k contracts / day', 'ylab2': '% rates + equity',
    'stacks': [{'name': nm, 'color': cl, 'values': L(_stack[c])} for c, nm, cl in CLS],
    'line': {'name': '% rates + equity (RHS)', 'color': 'GREEN',
             'values': L(_share), 'ymax': _ymax, 'yfmt': 'pct0'},
    # 头一句原文是「六个品种加总即披露的 Total ADV」——「即」是严格相等的断言，
    # 而紧接着的 _MIX_ROUND 就在说有几十期不等，读者滚一眼就抓到自相矛盾。
    # 改成「口径上穷尽互斥、数值上不处处相等」，把断言让给下面那句实测。
    'note': ('CME 的六个品种划分是穷尽且互斥的，所以柱高之和在<b>口径上</b>就是披露的 '
             'Total ADV；但<b>数值上</b>并非逐月严格相等。'
             + _MIX_ROUND +
             '右轴是利率 + 股指两大品种占总 ADV 的比重 —— 体量与结构同框，'
             f'总量持平但结构位移一样会改变混合费率（见 Exhibit {EX_RPC}）。'
             f'{XL25[0]} 至 {XL25[-1]}（{WIN_LINE} 个月）：右轴占比由 {_share[0]:.1f}% '
             f'走到 {_share[-1]:.1f}%（{pp(_share[-1] - _share[0])}），'
             f'窗口内在 {np.nanmin(_share):.1f}–{np.nanmax(_share):.1f}% 之间 —— '
             f'这个区间在原来的 13 个月窗口里只有 '
             f'{np.nanmin(_share[-WIN_TABLE:]):.1f}–{np.nanmax(_share[-WIN_TABLE:]):.1f}%，'
             f'结构位移的幅度要看满窗口才看得出来。'),
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
    # ⚠️ 下面这句是**全称断言**（「其余时序图……」），读者滚一张图就能证伪，所以
    #    不能凭印象写：文件末尾的 _AX_* 那段在构建期把每一张图的左端数一遍，
    #    对不上就停机。原来那句写的是「一律从 Jan-16 起（127 个月）」，
    #    而同页 Exhibit 8 当时只有 14 个季度 —— 断言与图、断言与 notes[10] 三方打架。
    'note': ('原 PDF 在末端画了一个红色虚线椭圆圈出最近 3 个月，网页引擎没有对应的注解图元，'
             f'故未移植。本图是全页唯一画到序列起点 {mlab(df.index[0])} 的图（{len(df)} 个月）；'
             f'其余时序图的左端一律是 {WIN_FROM} —— 月度刻度的那些是 {XL25[0]} 起的 '
             f'{WIN_LINE} 个月，Exhibit {EX_QTR} 与 Exhibit {EX_RPC} 是季度刻度，'
             f'同一个左端换算成 {qlab(Q_FROM)}。'
             f'逐月读数见 Exhibit {EX_ADV}，最近 {WIN_TABLE} 个月的原始单位读数见末尾核对表。'),
})

_qs = df['total_vol_mn'].groupby(df.index.asfreq('Q')).agg(['sum', 'count'])
_qv = _qs['sum'].values
_qyoy = np.array([(_qv[i] / _qv[i - 4] - 1) * 100 if i >= 4 and _qv[i - 4] else np.nan
                  for i in range(len(_qv))])
_npart = int(_qs['count'].iloc[-1])
# 季度柱的左端：与本页其余时序图同一个 WIN_FROM，换算到季度（2016-01 → 2016Q1）。
# 2026-08-19 之前这里取的是末 WIN_QTR = 14 个季度，判据与 Exhibit 14 那张季度 RPC
# 一模一样（「照搬原 deck 的窗口」），而那张已经放宽到 Q_FROM —— 同一页对同一种刻度
# 给两个左端，还在 Exhibit 7 的图注里写了句「其余时序图一律从 Jan-16 起」，
# 三处互相打架。数据不缺：本页月度序列自 2008-01 起，2016Q1 之后每一季都是 3 个完整月
# （下面现验，不靠人眼数），所以放宽的是画法而不是数据。
_qi0 = int(np.flatnonzero(_qs.index >= Q_FROM)[0])
_qidx = _qs.index[_qi0:]
_qhole = [str(p) for p, c in zip(_qidx[:-1], _qs['count'].values[_qi0:-1]) if c != 3]
if _qhole:
    raise SystemExit(f'Exhibit {EX_QTR}：{qlab(Q_FROM)} 起有未满 3 个月的季度 {_qhole}，'
                     f'柱高不可比，请先补月度数据再放宽窗口')
ex.append({
    'n': EX_QTR, 'kind': 'qtr_bar', 'fmt': 'f0c', 'label_fmt': 'f0c',
    'xlabels': [str(p) for p in _qidx],
    'title': 'Contracts traded aggregated to quarters', 'ylab': 'mn contracts',
    'ylab2': '% y/y',
    'values': L(_qv[_qi0:]),
    'partial_months': _npart, 'qtr_months': 3,
    'line': {'name': 'y/y (RHS)', 'color': 'GREEN', 'values': L(_qyoy[_qi0:]),
             'yfmt': 'pct0'},
    'src_extra': 'Latest bar is quarter-to-date and not comparable to full quarters',
    'note': (f'季度合计 = 该季各月「ADV x 当月交易日」之和，在 Python 侧算好。'
             f'本图与本页其余时序图同一个左端 {WIN_FROM}，只是刻度是季度不是月'
             f'（{qlab(_qidx[0])} – {qlab(_qidx[-1])}，共 {len(_qidx)} 个季度；'
             f'Exhibit {EX_RPC} 的季度 RPC 同此口径）。'
             f'末柱 {_qs.index[-1]} 只含 {_npart} 个月（浅蓝），其右轴 y/y 已被作废 —— '
             '拿未满季去比上年完整季必然砸出一个假坑。'
             # 绿线末端那个读数的标签由引擎固定右移 5px，窄屏下会飘到 QTD 柱上方，
             # 容易被读成 QTD 那一期的同比。把它归属的季度写死在图注里，读者不必靠像素判断。
             f'因此绿线的最后一个读数 {pct(_qyoy[-2], 0)} 属于 {_qs.index[-2]}'
             f'（最后一个完整季），不是 {_qs.index[-1]}。'
             # 季度柱的右轴是**第三种**同比口径（3 个月合计 vs 上年同季）。柱是季度的，
             # 线就必须与柱同期，改成 12 个月滚动会让线与柱指的不是同一段时间。
             f'<b>右轴的同比口径与其余各图不同</b>：这里是「本季 3 个月合计 vs 上年同季 3 个月合计」，'
             f'既不是单月同比、也不是各 gs_bar 次轴的 12 个月滚动合计同比。柱是季度口径，'
             f'线只能与柱同期，否则线讲的是另一段时间。三个月的合计已经把单月毛刺压掉一部分，'
             f'但仍比 12 个月滚动口径敏感得多，跨图比高低没有意义。'),
})

ex.append(gs_bar(EX_OI, 'oi_total_mn', 'Month-end total open interest', 'mn contracts', 'f1',
                 'Month-end OI', kind=YOY.STOCK,
                 note='月末未平仓合约是存量口径（期末快照），与 ADV 这类流量口径不可直接相加。'))
ex.append(gs_bar(EX_RATES, 'adv_rates_kcontracts', 'Interest-rate complex ADV',
                 'k contracts / day', 'f0c', 'Interest rates ADV'))
ex.append(gs_bar(EX_EQUITY, 'adv_equity_kcontracts', 'Equity-index complex ADV',
                 'k contracts / day', 'f0c', 'Equity index ADV'))
ex.append(gs_bar(EX_ENERGY, 'adv_energy_kcontracts', 'Energy complex ADV',
                 'k contracts / day', 'f0c', 'Energy ADV'))
ex.append(gs_bar(EX_REV, 'implied_txn_rev_usdmn', 'Implied transaction revenue', '$mn / month',
                 'usd0', 'Implied transaction revenue', note=BR_NOTE))

# 本图是**季度**口径（费率一个季度才披露一次），所以它的左端不是「2016-01 这一个月」
# 而是 2016-01 所在的季度 Q_FROM —— 与 Exhibit 8 的季度柱同一个左端。原先取末 14 个
# 季度（= 3.5 年，旧常量 WIN_QTR），那是照搬原 deck 的窗口，不是数据下限：
# series/fee_rates.csv 里 CME 的五条 RPC 都是
# 2013-Q2 起、53 个季度连续无缺，2016-Q1 起的每一季都在。
# lines_endlabels 属 mrwin.DENSE，窗口内一个 null 都不能有 —— 下面显式校验，
# 四条腿里任何一条在 2016-Q1 之后缺一季就在构建期响，不靠人眼看图。
_rq = RPC['total'].index[RPC['total'].index >= Q_FROM]
_rpc_gap = {_RPC_ZH_K: [qlab(q) for q in _rq if q not in RPC[_RPC_ZH_K].index]
            for _RPC_ZH_K in ('rates', 'equity', 'energy', 'metals')}
_rpc_gap = {k: v for k, v in _rpc_gap.items() if v}
if _rpc_gap:
    raise SystemExit(f'Exhibit {EX_RPC} 是平滑图型，{Q_FROM} 起不许缺季：{_rpc_gap}')
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
    'note': (f'季度值，x 轴标的是各季末月（{mlab(_rq[0].asfreq("M", "end"))} = {qlab(_rq[0])}，'
             f'最新为 {qlab(RPC_Q)}，共 {len(_rq)} 个季度）。本图与本页其余时序图一样从 '
             f'{WIN_FROM} 起，只是刻度是季度不是月（Exhibit {EX_QTR} 的季度柱同此左端，'
             f'{len(_qidx)} 个季度'
             + (f'；本图右端少的那 {len(_qidx) - len(_rq)} 季是费率尚未披露，不是窗口不同'
                if len(_qidx) > len(_rq) else '')
             + f'）：费率一季才披露一次，按月铺开只会把同一个数抄三遍。'
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


def heat(n, col, title, src_extra, fmt='pct0', legend=None, note=None):
    s = df[col].dropna()
    yrs = sorted({p.year for p in s.index})[-HEAT_YEARS:]
    M = [[None] * 12 for _ in yrs]
    for p, v in s.items():
        if p.year in yrs:
            M[yrs.index(p.year)][p.month - 1] = round(float(v), 6)
    d = {'n': n, 'kind': 'heat_matrix', 'full': True, 'title': title, 'fmt': fmt,
         'rows': [str(y) for y in yrs], 'cols': MONTHS, 'matrix': M,
         'legend': legend or title, 'cell_h': 20, 'row_lab_w': 38, 'row_head': '年',
         'src_extra': src_extra}
    if note:
        d['note'] = note
    return d


# fmt 用 pct0z 而不是 pct0：pct0 会把 −0.4% 印成「-0%」（一个不存在的数）。
# 当前 10 年窗口里恰好没有落在 ±0.5% 内的月份，但 y/y 序列每月都在动，这是迟早会命中的
# 格式坑，先按 pct0z 钉住（|v| < 0.5 → 0）。
#
# 这张矩阵**保留单月同比**，且标题里把「single-month」写进去。热力矩阵的用途就是逐格
# 看单月的季节性与异常月，把它换成 12 个月滚动值等于把相邻 12 格填成同一个数 —— 矩阵
# 会退化成一片同色，一格都读不出来。代价是本页出现第二种同比口径，所以标题、图例与图注
# 三处都显式点明，不靠读者自己猜。
ex.append(heat(EX_HEAT_YOY, 'adv_yoy', 'Total ADV y/y growth, single month (%)',
               'Green = faster y/y growth, red = slower. Single-month y/y — the only '
               'exhibit besides Exhibit 3 that is not on the 12-month rolling basis',
               fmt='pct0z', legend='Total ADV y/y (single month)',
               note=f'<b>本图的每一格是单月同比</b>（该月 ÷ 去年同月 − 1），'
                    f'与各 gs_bar 次轴的 12 个月滚动合计同比<b>不是一个口径</b>，'
                    f'两者不要放在一起读。这里之所以不平滑：热力矩阵的用途就是逐格看'
                    f'单月的季节性与异常月，换成滚动值会让相邻 12 格几乎填成同一个数、'
                    f'整张表退化成一片同色。代价是单月同比本身很毛：本页实测 '
                    f'{CALIB["n"]} 个可比月里有 {CALIB["n_opp"]} 个月与滚动口径符号相反'
                    f'（相邻月最大跳变 {CALIB["jump_m"]:.0f}pp，出现在 '
                    f'{mlab(CALIB["jump_m_at"])}）—— 所以这张表读的是「哪几个月不寻常」，'
                    f'不是「趋势往哪走」；趋势请看 Exhibit {EX_ADV} 的次轴与 Exhibit {EX_TTMVOL}。'))
ex.append(heat(EX_HEAT_SHARE, 'rates_share', 'Interest-rate share of total ADV (%)',
               'Rates is the largest and most rate-cycle-sensitive complex',
               legend='Rates share of ADV'))


# ══════════ Exhibit EX_DECOMP：收入增长的量／费率分解（**不是成交额的量价分解**）══════════
# 恒等式：收入 ≡ 成交合约数 × 每张平均费率。CME 不披露成交**金额**（期货的名义本金要靠
# 合约乘数逐品种推，本仓 series/contract_specs.csv 只覆盖一部分品种），所以「成交额 =
# 成交量 × 均价」那种分解在这一页做不到，做出来也是拿口径不全的名义本金去凑分母。
# 能做的是**收入**的量价分解：张数是量、RPC 是价。两者性质不同，标题和图注都必须写死这一点。
#
# 2026-08 改横轴：由「近 13 个月的 TTM 滚动端点」改成「4 个完整日历年 + 1 根当年 YTD」，
# 方法与护栏对齐全站其余 decomp（build/single.py 的 ex_decomp），跨页可比。口径纪律：
# （1）**桶**：一格 = 一个完整日历年（Jan–Dec 合计 vs 上一年同 12 个月合计）；末格 =
#      当年 YTD（今年 1 月–最新月合计 vs 去年**同一组月份**）。YTD 的基期必须逐月对齐 ——
#      不对齐就是拿 7 个月比 12 个月，柱高毫无意义。两侧月份集合由代码保证逐月相同。
# （2）**年度收入 = Σ(当月张数 × 当月费率)**，费率不做二次平均；年度 RPC = Σ收入 ÷ Σ张数
#      （合计 ÷ 合计）。「逐月 RPC 的简单平均」对每个月等权，而各月成交量差着一倍以上，
#      且均值之积 ≠ 积之均值 —— 拿它做分解，两块相加对不上总增长，而图上完全看不出来。
# （3）**图上画对数分解按总增长重标定后的两块**：w = g_V ÷ ln(V₁/V₀)，
#      贡献_量 = w·ln(Q₁/Q₀)、贡献_价 = w·ln(P₁/P₀)，两块相加逐格 = 算术总增长 g_V，
#      纵轴回到 %，读者不必在「对数点」与「百分比」之间换算。对数分解天然可加、无交叉项；
#      算术分解 g_V = g_Q + g_P + g_Q·g_P 的交叉项在量价对冲的年份能大到净增长的数倍，
#      堆叠柱画出来就是错的 —— 算术版照算，只进图注。
# （4）w 在 V₁ ≈ V₀ 时解析上 → 1、数值上是 0/0（两个小量都由大数相减得来，有效位被吃光），
#      所以 |ln(V₁/V₀)| < DEC_LN_MIN 的那一格**整根留空**，不印一个算不准的数。
# （5）分解是恒等式不是近似：算术闭合、对数闭合、重标定闭合三道检查残差 > DEC_EPS 一律
#      raise —— 一张「两块加起来不等于总数」的分解图，读者是看不出来的。
DEC_EPS = 1e-9      # 残差硬上限（与 build/single.py 的 DECOMP_EPS 同值同义）
DEC_LN_MIN = 1e-6   # |ln(V₁/V₀)| 低于它整根柱留空（重标定权重 w 数值上是 0/0）

_rev_m = df['implied_txn_rev_usdmn']    # 月收入（$mn）= 当月张数 × 当月费率，映射见 RATE_PERIOD
_vol_m = df['total_vol_mn']             # 月张数（mn）= ADV × 当月交易日数（当月合计）


def _dec_bucket(months):
    """一组月份 → (Σ收入, Σ张数)；任一月任一腿缺值、或合计非正 → None（该桶不可用）。"""
    v = _rev_m.reindex(months).astype(float)
    q = _vol_m.reindex(months).astype(float)
    if len(v) == 0 or v.isna().any() or q.isna().any():
        return None
    V, Q = float(v.sum()), float(q.sum())
    return (V, Q) if (V > 0 and Q > 0) else None


# 完整日历年：本桶与基期桶（上一年同 12 个月）都齐才画得出柱；数据允许时取最近 4 个。
# CME 的费率 2013-Q2 才有（此前隐含收入为 NaN），所以最早可画的年份由数据自己决定。
_YTD_Y = LATEST.year
_dec_bars = []                          # (柱标签, 本期月份, 基期月份)
for _y in sorted({p.year for p in df.index}):
    if _y >= _YTD_Y:
        continue
    _m1 = pd.period_range(f'{_y}-01', f'{_y}-12', freq='M')
    if _dec_bucket(_m1) and _dec_bucket(_m1 - 12):
        _dec_bars.append((str(_y), list(_m1), list(_m1 - 12)))
_dec_bars = _dec_bars[-4:]
if not _dec_bars:
    raise SystemExit(f'Exhibit {EX_DECOMP}：没有任何一个「本年与上一年都齐」的完整日历年，'
                     f'一根柱都画不出来')

# 当年 YTD：今年 1 月起、两侧（今年该月与去年同月）两条腿都齐的**连续前缀** ——
# 跳月拼出来的「YTD」两侧月份集合就不再是「1–N 月」。CME 的费率腿按本页常驻口径外推
# （最新季之后沿用上一季，见 RATE_PERIOD/RATE_STALE），所以「齐」= 隐含收入有定义；
# 哪些月用的是沿用费率由 RATE_PERIOD 现算写明，不在这里写死。
_ytd1 = []
for _p in [q for q in df.index if q.year == _YTD_Y]:
    if _dec_bucket([_p]) and _dec_bucket([_p - 12]):
        _ytd1.append(_p)
    else:
        break
if not _ytd1:
    raise SystemExit(f'Exhibit {EX_DECOMP}：{_YTD_Y} 年没有一个两侧都齐的月份，YTD 柱画不出')
YTD_LAB = f'{_YTD_Y} YTD'
YTD_COV = (f'{_ytd1[0].month}–{_ytd1[-1].month} 月' if len(_ytd1) > 1
           else f'{_ytd1[0].month} 月')
_dec_bars.append((YTD_LAB, _ytd1, [p - 12 for p in _ytd1]))

_dxl, _dq, _dp, _dnet, _drows, _dblanks = [], [], [], [], [], []
for _lab, _m1, _m0 in _dec_bars:
    _V1, _Q1 = _dec_bucket(_m1)
    _V0, _Q0 = _dec_bucket(_m0)
    _P1, _P0 = _V1 / _Q1, _V0 / _Q0          # $mn ÷ mn 张 = $/张
    _gV, _gQ, _gP = _V1 / _V0 - 1, _Q1 / _Q0 - 1, _P1 / _P0 - 1
    _crs = _gQ * _gP
    _lV = float(np.log(_V1 / _V0))
    _lQ = float(np.log(_Q1 / _Q0))
    _lP = float(np.log(_P1 / _P0))
    # 硬护栏①：算术分解闭合（三项，含交叉项）。残差只应是 float64 舍入（~1e-16）。
    if not abs(_gV - (_gQ + _gP + _crs)) <= DEC_EPS:
        raise SystemExit(f'Exhibit {EX_DECOMP} {_lab} 算术分解不闭合：'
                         f'残差 {_gV - (_gQ + _gP + _crs):+.3e} > {DEC_EPS:.0e}')
    # 硬护栏②：对数分解闭合（本来就该零残差，没有交叉项）。
    if not abs(_lV - (_lQ + _lP)) <= DEC_EPS:
        raise SystemExit(f'Exhibit {EX_DECOMP} {_lab} 对数分解不闭合：'
                         f'残差 {_lV - (_lQ + _lP):+.3e} > {DEC_EPS:.0e}')
    _dxl.append(_lab)
    row = {'lab': _lab, 'V1': _V1, 'Q1': _Q1, 'P1': _P1, 'V0': _V0, 'Q0': _Q0, 'P0': _P0,
           'gV': _gV, 'gQ': _gQ, 'gP': _gP, 'cross': _crs,
           'cq': np.nan, 'cp': np.nan}
    if abs(_lV) < DEC_LN_MIN:
        # 整根柱留空：w = g_V/ln(V₁/V₀) 此时是 0/0，算出来的两块没有有效位。
        _dblanks.append(_lab)
        _dq.append(np.nan)
        _dp.append(np.nan)
        _dnet.append(np.nan)
    else:
        _w = _gV / _lV
        _cq, _cp = _w * _lQ * 100, _w * _lP * 100
        # 硬护栏③：**画在图上的那两块**相加 == 总增长。
        if not abs(_gV * 100 - (_cq + _cp)) <= DEC_EPS:
            raise SystemExit(f'Exhibit {EX_DECOMP} {_lab} 重标定后不闭合：'
                             f'残差 {_gV * 100 - (_cq + _cp):+.3e} > {DEC_EPS:.0e}')
        row['cq'], row['cp'] = _cq, _cp
        _dq.append(_cq)
        _dp.append(_cp)
        _dnet.append(_gV * 100)
    _drows.append(row)

if not any(np.isfinite(x) for x in _dnet):
    raise SystemExit(f'Exhibit {EX_DECOMP}：{len(_dxl)} 根柱全部落在 |ln(V₁/V₀)| < '
                     f'{DEC_LN_MIN:.0e} 的留空区间，没有一根画得出来')

# 「算术分解里交叉项占净增长多大」正是不用算术分解的理由；两法对「量」的最大读数差
# 也现算 —— 数字一个都不照抄别的页。
_x_sh = [abs(r['cross'] / r['gV']) * 100 for r in _drows if r['gV'] != 0]
if not _x_sh:
    raise SystemExit(f'Exhibit {EX_DECOMP}：所有柱的净增长都恰为零，交叉项占比没有定义')
_CROSS_MED, _CROSS_MAX = float(np.median(_x_sh)), float(max(_x_sh))
_fin_rows = [r for r in _drows if np.isfinite(r['cq'])]
_log_gap = max(abs(r['gQ'] * 100 - r['cq']) for r in _fin_rows)
_log_gap_at = max(_fin_rows, key=lambda r: abs(r['gQ'] * 100 - r['cq']))['lab']

# 硬护栏④：**写进 payload 的那组数**（round 到 6 位后）也要闭合；留空柱两段必须同空。
for _i, (_xn, _xq, _xp) in enumerate(zip(L(_dnet), L(_dq), L(_dp))):
    if _xn is None:
        if _xq is not None or _xp is not None:
            raise SystemExit(f'Exhibit {EX_DECOMP} {_dxl[_i]} 净额留空但堆叠段有值 —— '
                             f'菱形不见了、柱子还在，读者会当成「净额为 0」')
        continue
    if not abs((_xq + _xp) - _xn) <= 2e-6:
        raise SystemExit(f'Exhibit {EX_DECOMP} {_dxl[_i]} 写进 payload 的两块相加 '
                         f'{_xq + _xp:.9f} ≠ 净额 {_xn:.9f}')

_ytd_row = _drows[-1]
DECOMP_CHECK = (f'Exhibit {EX_DECOMP} 量价分解：柱 = {"、".join(_dxl)}；'
                f'{YTD_LAB} 覆盖 {_YTD_Y} 年 {YTD_COV}（vs {_YTD_Y - 1} 年同月组）；'
                f'YTD 收入 ${_ytd_row["V1"]:,.0f}mn vs ${_ytd_row["V0"]:,.0f}mn、'
                f'张数 {_ytd_row["Q1"]:,.0f}mn vs {_ytd_row["Q0"]:,.0f}mn、'
                f'RPC ${_ytd_row["P1"]:.4f} vs ${_ytd_row["P0"]:.4f}；'
                f'三道闭合残差 ≤ {DEC_EPS:.0e} 全过'
                + (f'；留空柱 {"、".join(_dblanks)}' if _dblanks else ''))

_last = _drows[-1]
ex.append({
    'n': EX_DECOMP, 'kind': 'bridge_bar', 'fmt': 'pct1', 'yfmt': 'pct0',
    'xlabels': _dxl, 'xrot': 0,
    'title': 'Implied revenue growth split by calendar year: contracts vs. rate per contract '
             '(a revenue split, NOT a turnover split)',
    'ylab': '% y/y',
    'stacks': [
        {'name': 'Contracts traded', 'color': 'NAVY', 'values': L(_dq)},
        {'name': 'Rate per contract (RPC)', 'color': 'GOLD', 'values': L(_dp)},
    ],
    'net': {'name': 'Implied revenue growth', 'values': L(_dnet)},
    'net_color': 'INK',
    'src_extra': 'Identity: revenue = contracts x rate per contract; log-weight decomposition, '
                 'one bar = one calendar year (last bar = YTD vs. same months a year ago). '
                 'This decomposes REVENUE, not notional turnover — CME does not publish '
                 'traded notional value',
    'note': (f'<b>这是收入的量价分解，不是成交额的量价分解。</b>恒等式是「隐含交易收入 = '
             f'成交合约数 × 每张平均费率(RPC)」；CME 不披露成交<b>金额</b>，所以'
             f'「成交额 = 成交量 × 均价」那种分解在本页<b>不具备数据条件</b>，本图也没有假装做到。'
             f'两者不可混为一谈，也不要和别的页上真正的量价分解并读：这里的「价」是 CME 向客户'
             f'收的<b>每张费率</b>，不是标的资产的成交价格。'
             f' <b>横轴一格 = 一个完整日历年</b>（该年 12 个月合计 vs 上一年同 12 个月合计），'
             f'共 {len(_dxl) - 1} 格（{_dxl[0]} … {_dxl[-2]}）；'
             f'末柱 <b>{YTD_LAB}</b> 覆盖 {_YTD_Y} 年 <b>{YTD_COV}</b>'
             f'（{mlab(_ytd1[0])} – {mlab(_ytd1[-1])}），基期是 {_YTD_Y - 1} 年'
             f'<b>同一组月份</b> —— 两侧月份集合逐月相同，不是拿 {len(_ytd1)} 个月去比 12 个月。'
             f'<b>{YTD_LAB} 柱与完整年柱不可直接比大小</b>（覆盖月数不同）：'
             f'它回答的是「今年到目前为止 vs 去年同期」，不是「{_YTD_Y} 全年会怎样」。'
             f' <b>年度收入 = Σ(当月张数 × 当月费率)</b>，费率不做二次平均；'
             f'年度 RPC = Σ收入 ÷ Σ张数（合计 ÷ 合计），不是逐月 RPC 的简单平均 —— '
             f'那样对每个月等权而各月成交量差着一倍以上，均值之积 ≠ 积之均值，分解会不闭合。'
             f'张数腿 = Σ「ADV × 当月交易日数」（当月合计，与汇总表同口径），费率是季度值、'
             f'当季各月共用该季 RPC。'
             f' <b>图上画的是对数分解按总增长重标定后的两块</b>：ln(V₁/V₀) = ln(Q₁/Q₀) + '
             f'ln(P₁/P₀) 天然可加、无交叉项；再乘 w = g<sub>收入</sub> ÷ ln(V₁/V₀) 换算回'
             f'百分点，深蓝 + 金色<b>逐格等于</b>菱形标的总增长（三道闭合检查残差上限 '
             f'{DEC_EPS:.0e}，超了本页直接不出图）。w 对量与价一视同仁，不含分配假设。'
             f' <b>算术分解只进图注</b>：g<sub>收入</sub> = g<sub>张数</sub> + g<sub>费率</sub>'
             f' + 交叉项，而交叉项不是可忽略的余项 —— 本窗口实测交叉项占净增长中位 '
             f'{_CROSS_MED:.1f}%、最大 {_CROSS_MAX:.0f}%，量价对冲的年份堆叠柱画出来就是错的。'
             f'{_dxl[-1]} 的算术读数：张数 {pct(_last["gQ"] * 100)}、'
             f'费率 {pct(_last["gP"] * 100)}、交叉项 {pp(_last["cross"] * 100)}，'
             f'合计 {pct(_last["gV"] * 100)}；两种口径对「量」贡献的读数最大差 '
             f'{_log_gap:.1f}pp（{_log_gap_at}）。'
             + (f' <b>留空的柱</b>：{"、".join(_dblanks)} 的 |ln(V₁/V₀)| < {DEC_LN_MIN:.0e}'
                f'（两期几乎持平），重标定权重 w 是 0/0、算出来没有有效位，'
                f'整根留空而不是印一个假的分解。' if _dblanks else '')
             + f' <b>费率段读的是三重内容</b>：RPC 由 CME 从已披露收入倒算，所以它同时吸收了'
             f'品种结构位移（各品种 RPC 差数倍，见 Exhibit {EX_RPC}）、定价调整与折扣计划，'
             f'不是一个纯粹的「价」。' + RATE_PERIOD + RATE_STALE),
})

# ══════════ Exhibit EX_TTMVOL：量本身（TTM 水平值 + 同源增速曲线）══════════
# 为什么不是「月度 ADV + 滚动同比」——那张图就是 Exhibit EX_ADV，再画一遍是把同一份数据
# 在同一页上画两次。这里画的是分解图里那个「量」自己的水平值：近 12 个月成交合约数合计。
# 好处是柱与次轴的金色线**同源**：线上任一点的增速，就是柱子相对 12 根柱之前的涨幅，
# 读者不需要在两张图之间换算口径。
# 窗口与其余时序图同一个左端。TTM 合计要 12 个月填窗，本页序列自 2008-01 起，
# 所以 ttm_vol_mn 从 2008-12 起就有值 —— 2016-01 那一格早就落在有值区里，
# 这张图不存在「定义性前置期把左端顶开」的问题（cboe 的同名图有，见 build/cboe.py）。
_tv = df['ttm_vol_mn'].dropna()
_tw = _tv.index[_tv.index >= pd.Period(WIN_FROM, freq='M')]
if len(_tw) != WIN_LINE:
    raise SystemExit(f'Exhibit {EX_TTMVOL}：TTM 序列在 {WIN_FROM} 起只有 {len(_tw)} 期，'
                     f'与本页时序窗口的 {WIN_LINE} 期对不上')
_ttm_yoy = roll_yoy(df['total_vol_mn'])       # ≡ TTM 合计的同比（滚动均值同比与合计同比逐点相等）
ex.append({
    'n': EX_TTMVOL, 'kind': 'gs_bar', 'fmt': 'f0c', 'xlabels': [mlab(p) for p in _tw],
    'title': 'Contracts traded, trailing 12 months',
    'ylab': 'mn contracts, TTM', 'ylab2': '% y/y, 12M roll.',
    'legend': 'Trailing 12-month contracts',
    'values': L(_tv.loc[_tw].values),
    'yoy': {'name': '12M rolling y/y (RHS)', 'color': 'GOLD', 'yfmt': 'pct0',
            'values': L(_ttm_yoy.reindex(_tw).values)},
    'src_extra': 'The volume leg of Exhibit ' + str(EX_DECOMP) + ', shown as a level',
    'note': (f'柱 = 截至该月的近 12 个月成交合约数<b>合计</b>（= Σ「ADV × 当月交易日数」，'
             f'与汇总表「Total contracts traded」同一口径，只是累加 12 个月）；'
             f'金色线 = 该合计相对上一个 12 个月合计的同比，柱与线<b>同源</b> —— '
             f'线上任一点的读数就是这根柱相对 12 根柱之前的涨幅。'
             f'与 Exhibit {EX_ADV} 的区别：那张画的是月度 ADV（千张/日）的水平值，'
             f'本图画的是分解图 Exhibit {EX_DECOMP} 里「量」那一块自己的水平线。'
             f'{mlab(_tw[-1])} 为 {float(_tv.loc[_tw[-1]]):,.0f}mn 张，'
             f'{pct(float(_ttm_yoy.get(_tw[-1], np.nan)))} y/y。'
             f'单月成交量的毛刺在这条 TTM 曲线上看不到，这正是它的用处：'
             f'本页单月同比的相邻月最大跳变是 {CALIB["jump_m"]:.0f}pp，'
             f'TTM 口径只有 {CALIB["jump_r"]:.0f}pp。'),
})

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
    'n': EX_TABLE,
    'title': f'近 {WIN_TABLE} 个月月度指标核对表（官方原始单位，未换算）', 'idx': '月份',
    'cols': [[h, k] for h, k, _, _ in TBL_COLS],
    'rows': [dict({'xl': mlab(p)},
                  **{k: num(float(df[c][p]), d) for _, k, c, d in TBL_COLS})
             for p in W_TBL],
}

# ══════════════════════════ 6. 口径与方法说明 ══════════════════════════
NOTES = [
    f'<b>数据源与节奏。</b>CME Group IR 月度成交量 xlsx（cmegroupinc.gcs-web.com/monthly-volume），'
    f'次月第 1-2 个工作日发布。本页覆盖 {mlab(df.index[0])} – {mlab(LATEST)} 共 {len(df)} 个连续月，'
    f'无缺月；ADV、未平仓合约、交易日数三项均为公司直接披露，未经加工。',

    '<b>版式出处。</b>Goldman Sachs「IBKR Monthly」的成对图法（水平柱 + 次轴 y/y 折线）'
    '与其 Exhibit 7「堆叠柱 + 次轴占比线」的量能/结构同框做法；day-count 那张图取自 Barclays'
    '「IBKR July Monthly Metrics」。',

    # ── 同比口径：本页最容易被读反的一条，放在前面 ──
    f'<b>同比一律用 12 个月滚动合计，不是单月同比。</b>单月同比把「去年那<b>一个</b>月碰巧是'
    f'什么样」整个塞进分母，去年同月若是异常低点，今年一个平淡的月份也能印出三位数增速。'
    f'后果不是噪声大一点，而是<b>方向会反</b>。本页总 ADV 的实测（{CALIB["first"]} – '
    f'{CALIB["last"]}，{CALIB["n"]} 个两种口径都有值的月份）：'
    f'单月同比逐月标准差 <b>{CALIB["sd_m"]:.1f}pp</b>、相邻月最大跳变 '
    f'<b>{CALIB["jump_m"]:.0f}pp</b>（{mlab(CALIB["jump_m_at"])}）；'
    f'12 个月滚动合计同比标准差 <b>{CALIB["sd_r"]:.1f}pp</b>、最大跳变 '
    f'<b>{CALIB["jump_r"]:.1f}pp</b>；两者<b>符号相反</b>的月份有 {CALIB["n_opp"]} 个'
    f'（{CALIB["n_opp"] / CALIB["n"] * 100:.0f}%）'
    + (('，最近几例：' + '、'.join(
        f'{mlab(p)}（单月 {pct(r["m"])}／滚动 {pct(r["r"])}）'
        for p, r in CALIB['opp'].tail(3).iterrows()) + '。')
       if CALIB['n_opp'] else '。')
    + f'滚动同比的算法是「最近 12 个月合计 ÷ 上一个 12 个月合计 − 1」；实现上取滚动均值再相比 —— '
    f'窗口固定 12 个月，除以 12 是同一个常数，两者逐点严格相等，而均值让 ADV 类源列的单位'
    f'保持「千张/日」不变。第一个有值的点要等 24 个月（12 个月填窗 + 12 个月比较），'
    f'所以近期图窗口的左端可能没有折线，那不是缺数。'
    f'<b>不乘交易日数</b>：本页立场是 ADV 已按交易日中性化，实测也支持 —— 日均口径与'
    f'交易日加权口径的滚动同比最大只差 {DC_MAXGAP:.1f}pp，'
    + ('逐月符号完全一致' if DC_SAME_SIGN else '仍有符号不一致的月份')
    + f'，交易日效应在 12 个月窗口里基本自抵；为这点差别引入第二套聚合口径不划算。',

    f'<b>本页有四种同比口径，已逐处点名，不要跨口径比高低。</b>'
    f'（a）各 gs_bar 次轴的金色折线与 Exhibit {EX_TTMVOL}：12 个月滚动合计同比；'
    f'（b）Exhibit {EX_QTR} 的绿线：本季 3 个月合计 vs 上年同季（柱是季度的，线只能与柱同期）；'
    f'（c）Exhibit {EX_DAYCOUNT}、Exhibit {EX_OI}、Exhibit {EX_HEAT_YOY}、汇总表的 y/y 列'
    f'与页顶「{B.TITLE}」一段：单月同比；'
    f'（d）Exhibit {EX_DECOMP}：日历年合计同比 —— 整年 12 个月合计 vs 上一年同 12 个月，'
    f'末柱为当年 YTD（{_YTD_Y} 年 {YTD_COV}）vs 去年<b>同一组月份</b>，一格 = 一年，'
    f'既不要与（a）的滚动折线对读，也不要拿 YTD 柱去比完整年柱（覆盖月数不同）。'
    f'（c）里这五处保留单月各有理由 —— day-count 那张图的命题就是「一个月之内交易日数能把'
    f'方向读反」，平滑掉图就空了；<b>未平仓合约是存量</b>（月末快照），把 12 个月末的存量'
    f'加起来不是任何东西，而且存量不吃日历效应、单月同比本来就稳（本页实测标准差 '
    f'{CALIB_OI["sd_m"]:.1f}pp vs 总 ADV 的 {CALIB["sd_m"]:.1f}pp，相邻月最大跳变 '
    f'{CALIB_OI["jump_m"]:.0f}pp vs {CALIB["jump_m"]:.0f}pp）；'
    f'热力矩阵的用途是逐格看季节性与异常月，滚动值会把相邻 12 格'
    f'填成几乎同一个数、整表退化成一片同色；汇总表三列写死的是「本月/上月/去年同月」三个'
    f'具名月份，放滚动值进去与列头自相矛盾；页顶那段解读讲的正是这三个具名月份之间的'
    f'基数与排名，与汇总表同口径，句中凡同比都已标注「单月」——趋势判断不归它管，'
    f'归各图次轴的滚动折线与 Exhibit {EX_TTMVOL}。'
    f'「流量用滚动、存量用点对点」这条判据不是本页自订的，实现在全站唯一的 '
    f'<code>build/yoy.py</code> 里，对存量调滚动合计会直接抛错。',

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
    f'(a) <b>所有时序图的左端统一在 {WIN_FROM}（月度刻度 {WIN_LINE} 个月）</b>，'
    f'不是 deck 的 25 个月。'
    f'这一条 2026-08-18 先在曲线类（Exhibit {EX_DAYCOUNT}/{EX_MAJORS}/{EX_MINORS}）落地，'
    f'2026-08-19 gs_bar 与堆叠柱（Exhibit {EX_ADV}/{EX_MIX}/{EX_OI}/{EX_RATES}/{EX_EQUITY}/'
    f'{EX_ENERGY}/{EX_REV}/{EX_FX}/{EX_METALS}/{EX_AG}/{EX_TTMVOL}）跟上 —— 那批图此前停在 '
    f'13 个月，写的理由是契约 §5.4「近期图<b>固定</b> 13 个月」。这里说清楚：'
    f'§5.4 的原文写的是「固定」，本页是<b>有意不照它办</b>，不是把它读成了「至少」——'
    f'理由是这条规矩的括注（「够算 y/y 首末对比与 prior-12mo 均值」）讲的是为什么 13 个月'
    f'够用，而不是为什么更长不行，而本页 {mlab(df.index[0])} 起的数据一直都在'
    f'（Exhibit {EX_HIST} 就画着 {len(df)} 个月），13 个月是画的时候截的、不是数据没有。'
    f'§5.4 该怎么改由 <code>build/CONTRACT.md</code> 的持有者裁决，本页不动那份文件，'
    f'只在这里公开这处冲突。'
    f'季度刻度的两张同一个左端 {qlab(Q_FROM)}：Exhibit {EX_QTR} 的季度柱 {len(_qidx)} 个季度、'
    f'Exhibit {EX_RPC} 的季度 RPC {len(_rq)} 个季度（RPC 少的那几季是费率尚未披露）。'
    f'Exhibit {EX_HIST} 画全部 {len(df)} 个月，'
    f'末尾核对表仍是 {WIN_TABLE} 行（表是拿来逐行核对的，不是时序图）。'
    f'127 期放不进半栏卡片，哪几张升通栏、x 标签隔几期标一个，由 <code>build/mrwin.py</code> '
    f'按 <code>assets/charts.js</code> 的量边距算式在构建期算，各图图注里写着实测的 px 数。'
    '次轴那条金色 y/y 折线画的是同比而不是 12 个月均线（deck 的 docstring：「均线只是把柱子'
    '再平滑一遍、不带新信息」），这一点与 deck 一致；但<b>口径与 deck 有意不同</b> —— '
    'deck 画的是<b>单月</b>同比，网页版改画 <b>12 个月滚动合计同比</b>，'
    '理由与实测见上面的同比口径条。'
    f'(b) deck 的品种曲线图把六个品种画在一根轴上，利率品种的峰值把其余四条压成底部一条带；'
    f'网页版按量级拆成 Exhibit {EX_MAJORS} 与 Exhibit {EX_MINORS} 两张，数据、窗口、配色全同，'
    f'没有删点、没有截轴（详见两图图注）。'
    '(c) 金属品种在 deck 里用金色 #BF9000，网页引擎的调色板后来补齐了同一个金色，'
    '所以两边同色；红色在本站是断点与离群值的专用色，不拿来当数据色。'
    f'(d) Exhibit {EX_HIST} 的「最近 3 个月红色虚线圈」与 Exhibit {EX_RPC} 的第三位小数'
    '无对应实现，前者说明写进图注，后者的精确值写进图注。',

    f'<b>Exhibit {EX_DECOMP} 分的是收入，不是成交额。</b>恒等式「隐含交易收入 = 成交合约数 × '
    f'每张平均费率」两边都在本页有数，所以这张分解做得成；而「成交额 = 成交量 × 均价」'
    f'那种分解本页<b>不具备数据条件</b> —— CME 按月披露的是合约张数与未平仓合约，'
    f'从来没有披露过成交<b>金额</b>；要凑一个名义本金得逐品种乘合约乘数，本仓的 '
    f'<code>series/contract_specs.csv</code> 只覆盖一部分品种，拿它当分母算出来的「均价」'
    f'方向与大小都不可知，而且图上完全看不出来。宁可不做。'
    f'横轴是「{len(_dxl) - 1} 个完整日历年 + 当年 YTD」（与全站其余 decomp 同口径）：'
    f'整年 12 个月合计对上一年同 12 个月合计；YTD 柱对去年<b>同一组月份</b>'
    f'（{_YTD_Y} 年 {YTD_COV}），两侧月份集合逐月相同，且 YTD 柱与完整年柱不可直接比大小。'
    f'年度收入 = Σ(当月张数 × 当月费率)，费率不做二次平均；年度 RPC = Σ收入 ÷ Σ张数。'
    f'分解本身是恒等式而不是估算：图上两块相加逐格等于总增长，生成脚本对算术闭合、对数闭合、'
    f'重标定闭合三道检查都设了 {DEC_EPS:.0e} 的硬门槛，超了直接退出、不出图。'
    f'图上画的是<b>对数分解按总增长重标定后的两块</b>（w = g<sub>收入</sub> ÷ ln(V₁/V₀)，'
    f'ln 天然可加、无交叉项、不必选归属，纵轴回到 %）；算术分解照算但只进图注 —— '
    f'算术版必须把交叉项整段压进费率那一块，本页实测交叉项占净增长中位 {_CROSS_MED:.1f}%、'
    f'最大 {_CROSS_MAX:.0f}%，量与费率方向对冲的年份画出来就是错的。'
    f'费率那一块要按「结构 + 定价」读，不能当纯价格 —— RPC 是 CME 从'
    f'已披露收入倒算的，各品种 RPC 相差数倍（Exhibit {EX_RPC}），品种结构一位移它就动。',

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

    ═══ 同比口径（2026-08 全页改造后，本段的既定立场）═══
    本页各图次轴已改 12 个月滚动合计同比，而本段与 headline、汇总表一样，讲的是
    「本月 / 上月 / 去年同月」三个具名月份 —— 所以这里引用 m/m 与 y/y 用单月口径是
    合法的（与紧挨着的汇总表同口径），但**凡出现同比措辞一律写明「单月」**
    （CONTRACT §6），免得读者拿它去对各图次轴的滚动读数。趋势判断不归本段管 ——
    s2 的职责只是基数护栏（这个环比是不是被上月极值顶出来的），措辞不越这条线；
    趋势请看各图次轴的金色折线与 Exhibit EX_TTMVOL。

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
        # 四句里有三句以上月为参照。这不是数据缺值而是调用错误（compose_brief 拿的是
        # df.index 全序列，CUR/PRV/YAG 取的是 LATEST、LATEST-1、LATEST-12），
        # 照本仓「失败要响」处理。
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
    #    这一句里的同比是**单月**同比（与紧挨着的汇总表 y/y 列同口径），措辞必须点名 ——
    #    本页各图次轴是 12 个月滚动合计同比，不点名读者会拿这里的数去对金色折线。
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
            s2 = f'{mtxt}，但{pmo}月是{prev_where}，单月同比{B.pct(be["yy"])}，<b>{why}</b>。'
        elif be['yy'] is None:
            s2 = (f'{mtxt}，{pmo}月是{prev_where}；序列到本月共 {n} 个月，'
                  f'还差 {12 - i} 个月才够算单月同比，环比只能与上月自身的位置比。')
        else:
            s2 = (f'{mtxt}，单月同比{B.pct(be["yy"])}，两者同向，{pmo}月是{prev_where}，'
                  f'环比可直读。')

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
    #    同比只能报两个增速之商，不能做「几成来自分子」的比例拆分。三个增速都是单月口径
    #    （i vs i-12），句首点名一次即可：恒等式把分子分母绑在同一句里，口径跟着走。
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
            ytxt = (f'单月同比{B.pct(pu["yoy"])}，是电子成交{B.pct(pu["num_yoy"])}除以总 ADV '
                    f'{B.pct(pu["den_yoy"])}的商，{move}')
        else:
            ytxt = ('序列不足 12 个月，单月同比暂缺' if i < 12
                    else f'{months[i - 12]} 的分子缺读数，单月同比暂缺')
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
# 抬头原先只有单月 y/y 与 m/m。用户的核心诉求正是「单月同比未必反映真实趋势」——
# 而抬头是全页曝光最高的一行，把一个 33% 概率与趋势符号相反的数放在这里、
# 不给任何对照，是本页最容易被读反的地方。补上 TTM 口径，两个都写、哪个难看都照写。
_adv_ttm = float(roll_yoy(adv).get(CUR, np.nan))

# ── 全称断言的构建期兜底：「其余时序图的左端一律是 WIN_FROM」──────────────
# Exhibit 7 的图注与 notes 的「与原 PDF 版的有意差异」条都对**所有**时序图的左端下了
# 断言。这种句子最容易变成假话：加一张图、漏放宽一张图，句子不会自己跟着改
# （2026-08-19 那版就是 Exhibit 8 没跟上，图注却已经写了「一律」）。所以在这里逐张数
# 一遍，对不上直接停机 —— 让「断言」与「事实」只有一个来源。
# 三类登记，写的是**为什么不适用**，不是为了让它过：
_AX_QTR_LEFT = {EX_QTR: str(Q_FROM),                        # 季度柱：'2016Q1'
                EX_RPC: mlab(Q_FROM.asfreq('M', 'end'))}    # 季度 RPC：季末月标 'Mar-16'
_AX_EXEMPT = {
    EX_HIST: '全历史图，图注自己声明了它是全页唯一画到序列起点的图',
    EX_HEAT_YOY: '热力矩阵：年 × 月的格子，没有连续时间轴',
    EX_HEAT_SHARE: '热力矩阵：年 × 月的格子，没有连续时间轴',
    EX_DECOMP: '年度分解桥：横轴是完整日历年 + 当年 YTD，不是月份轴',
}
_ax_bad = [(e['n'], (e.get('xlabels') or ['(无 xlabels)'])[0])
           for e in ex
           if e['n'] not in _AX_EXEMPT and e.get('xlabels')
           and e['xlabels'][0] != _AX_QTR_LEFT.get(e['n'], XL25[0])]
if _ax_bad:
    raise SystemExit(
        'Exhibit 7 的图注与 notes 断言「其余时序图的左端一律是 '
        f'{WIN_FROM}」，但这些图对不上：'
        + '、'.join(f'Exhibit {n} 起于 {lab}' for n, lab in _ax_bad)
        + '。要么把它们一起放宽，要么把断言改掉并在 _AX_EXEMPT 里登记理由。')

# 同一类兜底：页尾口径条断言「本页没有口径断点，图上也确实一条都没画」。哪天真给某张图
# 传了 break_at，那句话立刻变成假话 —— 让它在构建期响，而不是等读者看见线再来打脸。
_brk_drawn = [e['n'] for e in ex if e.get('break_at') is not None]
if _brk_drawn:
    raise SystemExit(
        f'页尾口径条写着「本页没有口径断点」，但 Exhibit '
        + '、'.join(str(n) for n in _brk_drawn)
        + ' 画了 break_at。断点是真的就把那一条改写掉（并说明断点是什么、'
          '为什么现在才出现），不能只加线不改文案。')

# 127 点的图放不进半栏卡片 —— 逐张按 charts.js 的量边距算式判通栏与抽稀。
mrwin.layout_all(ex)

payload = {
    'ticker': 'cme',
    'tracker': 'CME Monthly Volume Tracker',
    'title': f'CME Group (CME): 月度成交量跟踪 — {CUR.year}年{CUR.month}月',
    'data_through': str(CUR),
    'through_label': f'{CUR.year} 年 {CUR.month} 月',
    'subtitle': (f'数据源：CME Group IR 月度成交量报告（次月第 1-2 个工作日发布）· '
                 f'覆盖 {mlab(df.index[0])} – {mlab(LATEST)}（{len(df)} 个月）· '
                 f'版式仿 Goldman Sachs GIR「IBKR Monthly」与 Barclays day-count 调整 · 仅图，无评论'),
    'headline': (f'ADV {df["adv_mn"][CUR]:,.1f}mn 张/日（单月 {pct(_adv_yy)} y/y，'
                 f'{pct(_adv_mm)} m/m；TTM {pct(_adv_ttm)} y/y）· '
                 f'总成交 {df["total_vol_mn"][CUR]:,.0f}mn 张（单月 {pct(_vol_yy)} y/y，'
                 f'{pct(_vol_mm)} m/m，交易日贡献 {pp(_dc)}）· '
                 f'近 12 个月成交 {float(df["ttm_vol_mn"][CUR]):,.0f}mn 张 · '
                 f'月末未平仓 {df["oi_total_mn"][CUR]:,.1f}mn 张'
                 f'（单月 {pct(_oi_yy)} y/y）· 利率品种占 ADV {_share:.0f}% · '
                 f'隐含交易收入 ${df["implied_txn_rev_usdmn"][CUR]:,.0f}mn'),
    # headline 之下、Exhibit 1 之上的 ~300 字解读。职责与 headline 互补：
    # 那一行给读数，这一段给「读数该怎么读」。见 compose_brief 的 docstring。
    'brief': BRIEF,
    'hub_line': (f'ADV {df["adv_mn"][CUR]:,.1f}mn 张/日，TTM {pct(_adv_ttm)} y/y；'
                 f'单月 {pct(_adv_yy)} y/y、{pct(_adv_mm)} m/m'),
    'source': SRC,
    # 页级默认轴 = 时序图的统一窗口（2016-01 起）。每张 exhibit 现在都自带 xlabels，
    # 这一项只剩兜底作用；但它必须与图的窗口同长，否则日后有人新增一张不写 xlabels 的图，
    # 就会拿到一根 13 格的轴去画 127 个点（引擎按 xlabels.length 循环，多出来的点画不出来
    # 却仍参与量程 —— 图被一个看不见的点压扁，不报错）。
    'xlabels': XL25,
    'xlabels_long': XL_LONG,
    'summary': summary(),
    # 轴刻度小数位与截轴护栏：判据见 build/axisfmt.py（全站唯一实现）。
    'exhibits': axisfmt.fix_all(ex),
    'table': table,
    'notes': NOTES,
    'footer': 'CME Group (CME) · monthly volume reports · charts only, no commentary · '
              'personal research use',
}

# 抬头右侧那半句「官方发布于 X」是关于外部世界的事实断言，只能取台账里记下的、
# 由源头自己给出的日期（CME 这家是 xlsx 的 Last-Modified 与工作簿保存时间戳互证，
# 见 fetch/cme.py 的 _publish_date）。台账里没有就**整个字段不写** ——
# 页面判的是字段在不在，塞 None 会把那半句变成「官方发布于 None」。
_SOURCE_DATE = source_dates.lookup(SERIES, 'cme', str(CUR))
if _SOURCE_DATE:
    payload['source_date'] = _SOURCE_DATE


def main():
    # 写出前先过 CONTRACT §5.5 护栏（NaN/Infinity 一律拒写）；首行注释与序列化都在里面。
    payload_guard.write_dash(OUT, payload, 'cme')
    print(f'数据截至 {CUR} | 月份 {df.index[0]} → {LATEST}（{len(df)}）')
    print(f'Exhibit 1 汇总表 + Exhibit {ex[0]["n"]}-{ex[-1]["n"]}（{len(ex)} 张）+ '
          f'Exhibit {table["n"]} 核对表')
    print(f'写出 {OUT}（{os.path.getsize(OUT) / 1024:.1f} KB）')
    print(DECOMP_CHECK)
    print(payload['headline'])


if __name__ == '__main__':
    main()
