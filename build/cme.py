# -*- coding: utf-8 -*-
"""CME Group (CME) 月度成交量 —— 网页看板数据生成器（build/build_cme.py 的移植）。

原 deck：build/build_cme.py（matplotlib → PDF，冻结存档，它读的 build/data/ 已不存在）。
本文件最初把它的每一张 exhibit 重新实现成 data/cme.js 里的一个 payload 对象，页面
（assets/page.js + charts.js）只负责画、不做任何计算。

**已与 deck 分叉，分叉清单（2026-09 按页面所有者的指令）**：
  · 删三张：全历史 ADV 线、季度合计柱、当月成交张数柱；
  · 加一张：各品种隐含收入占比（100% 堆叠，deck 里没有对应图）；
  · 改一张的口径：收入的量价分解由「完整日历年 + 当年 YTD」改成**月度**桶；
  · 改一张的内容：品种 RPC 由四条线扩到六条（补上农产品与外汇）；
  · 重排：六张品种 ADV 柱收拢在一起，收入那一组按「水平值 → 结构 → 分解」排。
所以「本文件逐张移植自 deck」这句话现在只对**其余各张**成立，别再拿它当全称断言。

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
import glossary as gloss                # 名词释义的版式层与护栏，全站共用
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
# 分组判据是**窗口内峰值最大的两个 vs 其余四个**，不是「量级差一个数量级」——
# 后者当场就是假的：能源的峰值落在股指的区间里面（实测见 Exhibit EX_MINORS 的图注，
# 那里现算「四小之最大 ÷ 两大之最大」，2026-08 是 24%，也就是 4 倍出头，不是 10 倍）。
# 具体区间随窗口变，所以一个数都不写死在注释里；判据本身在构建期核对（拆图那两张的
# 上方，_MINOR_MAX 与 _MAJOR_MIN_PEAK 一比）：两组的峰值一旦交叉（比如能源哪天超过
# 股指），立刻停机。
CLS_MAJOR = CLS[:2]     # 利率 + 股指：窗口内峰值最大的两个品种
CLS_MINOR = CLS[2:]     # 能源 / 农产品 / 外汇 / 金属：窗口内峰值都低于上面两个

#: 品种 →（RPC key, fee_rates.csv 的 metric 名, 中文名）。**与 CLS 逐项同序**，
#: 这是「哪个品种的量该乘哪个品种的费率」的<b>唯一</b>真相 —— 两份平行清单 zip 起来
#: 错位（把农产品的量乘上金属的费率）不会有任何闸门响，画出来的占比看着完全合理。
#: 所以只留这一份，颜色 / 图例名 / ADV 列一律从 CLS 同下标取，下面 _CLS_REV_ALIGN 现验。
CLS_RPC = [('rates', 'rpc_interest_rates', '利率'),
           ('equity', 'rpc_equity_indexes', '股指'),
           ('energy', 'rpc_energy', '能源'),
           ('ag', 'rpc_agricultural', '农产品'),
           ('fx', 'rpc_foreign_exchange', '外汇'),
           ('metals', 'rpc_metals', '金属')]
if len(CLS_RPC) != len(CLS):
    raise SystemExit(f'CLS_RPC（{len(CLS_RPC)} 个）与 CLS（{len(CLS)} 个）品种数对不上 —— '
                     f'收入占比图的段序、配色与图例会与 ADV 那几张错开。')
#: 品种词根：ADV 列写 `adv_<k>_kcontracts`，fee_rates 的 metric 写 `rpc_<stem>`。
#: 三个品种两边词不同（利率 / 股指 / 外汇），显式登记；其余三个两边同词。
_RPC_STEM = {'rates': 'interest_rates', 'equity': 'equity_indexes', 'energy': 'energy',
             'ag': 'agricultural', 'fx': 'foreign_exchange', 'metals': 'metals'}
# ⚠ **这道是全页唯一挡得住「配错费率」的判据。** CLS 与 CLS_RPC 是两份平行清单靠 zip 对齐，
# 而错位是**置换**：长度不变、总量量级不变，于是 Σ段仍恒为 100%、量侧仍闭合、与 EX_REV 的
# 相对差也只有个位数百分点 —— 收入占比图的六道护栏一道都不会响，画出来的图看着完全合理。
# （实测：把农产品的量乘上金属的费率，相对差只有 8.5%，远在 15% 的阈值之内；15 种两两置换
#  里有 7 种能这样静默通过。）所以这里不靠聚合残差，直接核对「列名的词根与 metric 的词根
#  是不是同一个品种」。2026-09 之前这里只有一句 `len(CLS_RPC) != len(CLS)`，管个数不管顺序。
if sorted(_RPC_STEM) != sorted(k for k, _, _ in CLS_RPC):
    raise SystemExit(f'_RPC_STEM 的品种名单 {sorted(_RPC_STEM)} 与 CLS_RPC 的 '
                     f'{sorted(k for k, _, _ in CLS_RPC)} 对不上。')
def _adv_key(col):
    """'adv_ag_kcontracts' → 'ag'。判据从**列名**回推品种，不信 CLS_RPC 自己报的 key。"""
    return col[len('adv_'):-len('_kcontracts')]


_CLS_REV_ALIGN = [(c, k, m) for (c, _, _), (k, m, _) in zip(CLS, CLS_RPC)
                  if _adv_key(c) != k or m != f'rpc_{_RPC_STEM.get(k, "?")}']
if _CLS_REV_ALIGN:
    raise SystemExit(
        'CLS 与 CLS_RPC 逐项对不上（量与费率配错品种，画出来的收入占比会看着很合理）：'
        + '、'.join(
            f'{c}（品种 {_adv_key(c)}）配到了 {m}，应当是 '
            f'rpc_{_RPC_STEM.get(_adv_key(c), "?")}' for c, k, m in _CLS_REV_ALIGN))

#: 逐项对齐的组合视图：(ADV 列, 图例名, 颜色, RPC key, metric, 中文名)。全文只此一份。
CLS_REV = [(c, nm, cl, k, m, zh) for (c, nm, cl), (k, m, zh) in zip(CLS, CLS_RPC)]

# 图号写死在十几处图注与说明里，靠人肉数是要出错的（原 PDF 的汇总表脚注就把 Exhibit 3
# 写成了 Exhibit 4），所以统一在这里定名，正文一律引用常量。
#
# **2026-09 按页面所有者的指令整体重排。下面这份是现在的阅读顺序，不是「在旧号后面追加」**
# —— 上一版的注释写着「20/21 是后加的两张，一律追加在末尾」，那种「只加不排」的做法
# 正是把六张同类的品种柱拆散在 10-12 与 15-17 两处的原因。本轮做了四件事：
#   · 删三张：全历史 ADV 线、季度合计柱、当月成交张数柱；
#   · 六张品种 ADV 柱收拢到 EX_MINORS 之后 —— 六张之间的**相对次序照原 deck 不动**
#     （利率 / 股指 / 能源 / 外汇 / 金属 / 农产品，也就是所有者点名那六个旧号的次序）。
#     ⚠ 它**不是**按量级排的（窗口内峰值：外汇 < 金属 < 农产品，末三张恰好是升序），
#     也与本页其余几张六品种图的段序（CLS：利率 / 股指 / 能源 / 农产品 / 外汇 / 金属）
#     不同 —— 旧版这六张散在两处看不出来，收拢之后这处不一致就摆在读者眼前了。
#     要改成与 CLS 同序是另一件事，得先问页面所有者。
#   · 新增 EX_REVMIX（各品种隐含收入占比），紧跟在隐含收入那张之后；
#   · EX_DECOMP 由「完整日历年 + 当年 YTD」改成**月度**桶，并移到 EX_REVMIX 之后 ——
#     收入这一组（水平值 → 结构 → 量价分解）因此连成一段。
#
# 这份号**必须逐行等于 ex.append() 的调用顺序、自 2 起连号无洞、核对表接在最后一张之后**。
# 三件事都由 4.9 节的兜底⓪现读 payload 核对，外部工具指望不上：
# build/verify_pages.py 只把重号判 ERROR、编号倒退判 WARN，**跳号一声不吭**，
# 而 main() 那行 `Exhibit {ex[0]['n']}-{ex[-1]['n']}` 假定连号，有洞时会静默印出假区间。
EX_ADV, EX_DAYCOUNT, EX_MIX = 2, 3, 4
EX_MAJORS, EX_MINORS = 5, 6          # 品种曲线：两大品种 / 四小品种，见下方拆图说明
EX_RATES, EX_EQUITY, EX_ENERGY = 7, 8, 9        # 六张品种 ADV 柱，次序照原 deck（见下）
EX_FX, EX_METALS, EX_AG = 10, 11, 12
EX_OI = 13                                      # 全页唯一读**存量**（月末快照）的一张
EX_REV, EX_REVMIX, EX_DECOMP = 14, 15, 16       # 收入：水平值 → 品种结构 → 量价分解
EX_RPC = 17                                     # 全页唯一的季度刻度图
EX_HEAT_YOY, EX_HEAT_SHARE = 18, 19
EX_TABLE = 20

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
#: series/cme.csv 里 2008-01 起的数一直都在（页面上不再单独画那段全历史），13 个月是
#: **画的时候截的**，不是数据没有。§5.4 本身该不该改，由 build/CONTRACT.md 的持有者
#: 裁决（本文件不去数别的页面现在停在几个月 —— 把跨页统计写进本页注释，就是给它
#: 安一个必然过期的实测数），本文件不动那份契约，
#: 只在页尾 notes 的「与原 PDF 版的有意差异」条里把冲突写给读者看。
WIN_FROM = '2016-01'
#: 2026-08-19：`WIN_QTR = 14`（季度柱照搬原 deck 的 win=14）已删除，当时的两张季度刻度图
#: 都改吃 `Q_FROM`（= WIN_FROM 换算到季度）；2026-09 删掉季度合计柱之后，季度刻度只剩
#: 品种 RPC 那一张，仍吃 `Q_FROM`。本页不再有第二个窗口常量 —— 留一个只在一处用得上的
#: 旧窗口常量，下一次放宽时又会漏掉它（2026-08 那次就漏了）。
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
#: series/cme.csv 的表头（month 已经当了索引，所以这里就是「公司披露了哪些列」）。
#: 下面往 df 上加多少派生列，这份名单都不跟着变 —— 它是「这个数是不是 CME 原样披露的」
#: 唯一判据，§3 的 _sum_provenance() 现读它，不靠任何人肉名单。
CSV_COLS = tuple(df.columns)
adv = df['adv_total_kcontracts']
days = df['trading_days']
LATEST = df.index[-1]

#: 汇总表要用、而 series/cme.csv 里**没有对应列**的推导值：算式文本与算式本身在这里绑成
#: 一对，列的值就由这个 lambda 算出来（紧接着的赋值那一行调的就是它）。所以表注里印给
#: 读者的算式不可能与实际算法走散 —— 改了 lambda，印出来的字跟着变。
#: 凡是 SUM_ROWS 用到、又落不进「披露原列 / 披露原列的常数倍」两档的列，都必须登记在
#: 这里；漏登记就在 _sum_provenance() 里停机，不会静默变成「无推导」。
SUM_CALC = {
    'total_vol_mn': ('ADV × 当月交易日数',
                     lambda d: d['adv_total_kcontracts'] * d['trading_days'] / 1000.0),
}

df['total_vol_mn'] = SUM_CALC['total_vol_mn'][1](df)        # 月度总成交量（百万张）
df['adv_mn'] = adv / 1000.0
df['oi_total_mn'] = df['oi_total_contracts'] / 1e6
# 全页唯一验证「总成交张数 ÷ ADV ≡ 当月交易日数」的地方。Exhibit EX_DAYCOUNT 的图注、
# 页尾口径条、以及量价分解那张图的张数腿都建立在这个恒等式上，而 SUM_CALC 的算式是
# 可以被人改动的一行 lambda —— 让它在构建期响，而不是等读者拿两张图相除。
# （2026-09 之前这道断言长在「当月成交张数柱」那张图里，那张图按所有者指令删除时，
#  断言搬到了这里，没有跟着一起删。）
if not np.allclose((df['total_vol_mn'] / df['adv_mn']).values,
                   df['trading_days'].values, rtol=1e-9, atol=0):
    raise SystemExit('total_vol_mn ÷ adv_mn 与 trading_days 列对不上 —— '
                     f'SUM_CALC["total_vol_mn"] 的算式（{SUM_CALC["total_vol_mn"][0]}）'
                     '与多处图注、页尾口径条都建立在这个恒等式上，先改句子再改算式。')
# 同比一律走 build/yoy.py（全站唯一实现），不在这里自己写 pct_change(12)：
# 那样绕过了「基期为 0 / 与当期异号就留空」这道判据，而且各页各写一份正是同一条序列
# 在两页被判定相反的原因。这两列是**单月**同比（Exhibit 3 的两条线、热力矩阵、
# 汇总表的 y/y 列都取自它们），与全页次轴金线同一个口径 —— 见下面的口径段。
df['vol_yoy'] = YOY.mom_yoy(df['total_vol_mn'], YOY.FLOW)
df['adv_yoy'] = YOY.mom_yoy(adv, YOY.FLOW)
df['daycount_effect'] = df['vol_yoy'] - df['adv_yoy']       # 两者之差 = 交易日数贡献
df['rates_share'] = df['adv_rates_kcontracts'] / adv * 100


# ══════════════════ 同比口径：全页月度同比一律画单月同比 ══════════════════
# **2026-09 改口径。** 本页此前所有次轴金色折线画的是「12 个月滚动合计同比」，现在
# 一律改成**单月同比**（当月 ÷ 去年同月 − 1）。理由是一句可核对的事实：**页面所有者
# 要求全站统一成单月口径**（原话：「我就需要直接的月度数据 yoy 同比折线图，不要给我搞
# 12 月滚动合计同比」）—— 不是「看着更灵敏」那种 CONTRACT §6.1 第 3 条明令禁止的说法。
#
# 这不是本页自己的偏好：同一轮里 `build/CONTRACT.md` §6 已经整条改写成「全站同比只有
# 一种口径：单月同比，页面上一条 12 个月滚动合计的同比都不画」，本页是照契约办。
# 契约同时要求的两件事，这里都照办：
#   · **口径写进图上**：次轴名与 ylab2 一律带 `single month`
#     （`tools/check_yoy_caliber.py` 的 R4 把 title / 序列名 / ylab2 / legend 拼起来看）；
#   · **每张画流量同比的图都要印出单月口径的代价，用<那张图自己那条>序列实测**
#     （§6.1 第 3 条，「逐图」是字面意思，页级那段不算数）—— 每张图的图注挂
#     yoy_cal_zh() 现算的一段：逐月标准差、相邻月最大跳变（带月份）、与滚动口径符号
#     相反的月份数，一个数都没有写死；统计范围是**这张图画出来的那段窗口**（§6.4），
#     所以图注里点到的每个月份都能在它自己的横轴上找到。
#     对照的那一侧只以数字出现在文字里，页上一条线都不画。
#     ⚠️ 2026-09 之前这里是一个页级常量 YOY_CAL，九张图共用总 ADV 的全历史一份数 ——
#     跨图引错，留档见 yoy_cal_zh() 的 docstring。
# 契约也明令不许在图注里替「页面上不存在的那个口径」背书，所以下面的措辞只报代价、
# 不说「滚动更好但我们没用」。
#
# 代价是实打实的：单月同比把「去年那**一个**月碰巧是什么样」整个塞进分母，去年同月若是
# 异常低点，今年一个平淡的月份也能印出三位数的增速。所以图注要求读者「连着柱高一起读」，
# 而不是单看金线挑月份下结论。
#
# ⚠ **存量序列不受这次改动影响**。month-end OI 这类期末快照走的一直是点对点同比
# （YOY.mom_yoy(s, STOCK)）—— 把 12 个月末的 OI 加起来不是任何东西：既不是「一年的量」
# （存量不累积），也不是「平均水平」（没除以 12）。改完之后全页月度刻度的同比因此只剩
# **一种算法**：当月 ÷ 去年同月 − 1；流量与存量的区别退到「读的是流量还是时点存量」。
# 判据与实现都在 build/yoy.py，本文件只负责说清「这一列是流量还是存量」。
#
# 要不要把日均乘回交易日数？**仍然不乘，但理由随口径一起变了**（见 DAYCOUNT_* 那几行）：
# 在滚动口径下交易日效应 12 个月内基本自抵，「乘不乘都一样」；改成单月口径之后它**不再
# 自抵**（实测最大差 DC_MAXGAP_MOM ≈ 21pp，还有若干个月符号相反）。不乘的理由因此换成
# 更硬的一条：CME 直接披露的 ADV 本身就是按交易日中性化的量，而「乘回去与不乘回去差多少」
# 本页不藏 —— Exhibit EX_DAYCOUNT 整张图就是把这个差画出来给读者看。


def roll_yoy(s):
    """12 个月滚动合计同比（%），**只作口径对照、本页不再画任何一条**。委托给 build/yoy.py。

    2026-09 改口径之后，页面上所有金色折线走的都是 YOY.mom_yoy（单月）。这个函数留着
    是因为「单月口径的代价有多大」必须用滚动那一侧当尺子量出来印在图注里 ——
    没有对照的「代价」是空话。凡是调它的地方，产出的数只会进**文字**，不会进 values。

    前 23 个点必然为 NaN：12 个月填窗 + 12 个月比较。
    滚动合计与滚动均值的同比逐点严格相等（除以 12 是同一个常数）。
    """
    return YOY.ttm_yoy(pd.Series(s), YOY.FLOW)


def caliber_diff_win(s, win, kind=YOY.FLOW):
    """`yoy.caliber_diff` 的本页入口：**索引换成横轴标签、统计范围限定成图窗**。

    两件事都是 CONTRACT §6.4 点名的坑，所以在一个地方做完，调用点不许各写一遍：

    · **统计范围 = 这张图真画出来的那段窗口。** 图注里报的月份若落在图窗之外，
      读者在图上根本找不到（§6.4 举的例子是 `ndaq` Ex14 在一张 127 期的图上印
      2008 年的跳变）。所以 `win` 必填，不给默认值 —— 本页序列自 2008-01 起，
      而图窗自 2016-01 起，全历史与图窗不是同一段，差得还不小。
    · **索引先换成 `Jan-16` 这种横轴标签**（照 `build/single.py` 的 `mom_cost_zh()`）——
      于是 `describe()` 点到的每一个月份都能在本图 x 轴上原样找到。

    真正的统计（样本对齐、相邻月跳变、符号相反的月份）一格都不在本文件里做，
    全部走 build/yoy.py 的 caliber_diff —— 那是全站唯一实现，各页各写一份正是同一条
    序列在两页被判定相反的原因。样本对齐这一步尤其不能自己重写：滚动同比比单月同比少
    12 个月历史，不取交集就会把「样本不同」读成「口径不同」。
    """
    s = pd.Series(s)
    s = s.set_axis([mlab(p) for p in s.index])
    return YOY.caliber_diff(s, kind, win=[mlab(p) for p in win])


def caliber_stats(s, win, kind=YOY.FLOW):
    """`caliber_diff_win` 的键名适配层（页尾、汇总表注与热力图注沿用旧字段名）。

    `first` / `last` / `jump_m_at` 与 `opp` 的索引现在都已经是横轴标签（`Jan-16` 这种），
    调用点**不要**再套一层 `mlab()`。
    """
    d = caliber_diff_win(s, win, kind)
    opp = pd.DataFrame([{'m': m, 'r': r} for _, m, r in d['opposite']],
                       index=[p for p, _, _ in d['opposite']])
    return {
        'n': d['n'], 'first': d['months'][0], 'last': d['months'][-1],
        'sd_m': d['std_mom'], 'sd_r': d['std_ttm'],
        'jump_m': d['maxjump_mom'][0], 'jump_m_at': d['maxjump_mom'][2],
        'jump_r': d['maxjump_ttm'][0] if d['maxjump_ttm'] else float('nan'),
        'n_opp': d['opposite_n'], 'opp': opp,
    }


# ── 图窗：口径代价一律**在这段窗口上**量，所以窗口必须先算出来（CONTRACT §6.4）──
# 2026-09 之前这一块排在下面几十行，而 CALIB 那批统计量在它之前就算完了，于是只能走
# 全历史（2008-01 起，200 个可比月）—— 印在一张 2016-01 起、127 期的图上，报出来的
# 月份读者在横轴上找不到。现在窗口先定，统计跟着窗口走。
W_TBL = df.index[-WIN_TABLE:]        # 只给末尾核对表用
_I0 = next((i for i, p in enumerate(df.index)
            if f'{p.year}-{p.month:02d}' >= WIN_FROM), 0)
W25 = df.index[_I0:]
WIN_LINE = len(W25)          # 下面 win(col, WIN_LINE) 与图注里的「N 个月」都跟着它走
XL25 = [mlab(p) for p in W25]
# 季度轴的左端：与 WIN_FROM 同一个月份，换算到季度（'2016-01' → 2016Q1）。
# 写成换算而不是写死 '2016Q1'，是为了 WIN_FROM 哪天再动时季度图跟着一起动。
Q_FROM = pd.Period(WIN_FROM, freq='M').asfreq('Q')


# CALIB / CALIB_OI / DAYCOUNT_STATS 一律在**图窗**上量（W25 = 本页所有月度图的横轴）。
# 它们服务的是 Exhibit EX_ADV / EX_OI / EX_DAYCOUNT 这三张图的图注与页尾口径条，
# 而那三张图画的都是这段窗口 —— 拿全历史（2008-01 起）的数去说一张 2016-01 起的图，
# 报出来的月份读者在横轴上找不到（CONTRACT §6.4）。
#: CALIB 量的是**哪一张图那条线**。写成常量而不是散在文案里的字面量：下面有一条构建期
#: 断言拿它去和逐图账本 COST_LOG 对数，图号哪天变了是当场停机，不是印出假话。
CAL_EX = EX_ADV
CALIB = caliber_stats(adv, W25)                  # 总 ADV = Exhibit EX_ADV 那条线
CALIB_OI = caliber_stats(df['oi_total_contracts'], W25, YOY.STOCK)   # 月末未平仓：存量
# 交易日加权 vs 日均：同一条量在两种聚合口径下差多少（决定「要不要把日均乘回交易日」）。
# **两种同比口径都要量**，因为答案不一样，而页面上讲的话必须跟着实际画的口径走：
#   · 滚动口径（本页已不画，只作对照）：12 个月窗口里交易日效应基本自抵；
#   · 单月口径（本页现在画的）：完全不自抵，最大差二十几个百分点，还有月份符号相反。
# 这一组的统计范围同样是图窗 —— 它们印在 Exhibit EX_DAYCOUNT 的图注里，
# 而那张图的横轴就是 W25。
DAYCOUNT_STATS = caliber_stats(df['total_vol_mn'], W25)
_c_both = pd.concat([roll_yoy(adv), roll_yoy(df['total_vol_mn'])],
                    axis=1, keys=['a', 'v']).reindex(W25).dropna()
DC_MAXGAP = float((_c_both['a'] - _c_both['v']).abs().max())
DC_SAME_SIGN = bool(((_c_both['a'] * _c_both['v']) > 0).all())
_m_both = pd.concat([df['adv_yoy'], df['vol_yoy']],
                    axis=1, keys=['a', 'v']).reindex(W25).dropna()
DC_N_MOM = int(len(_m_both))
DC_MAXGAP_MOM = float((_m_both['a'] - _m_both['v']).abs().max())
DC_MEDGAP_MOM = float((_m_both['a'] - _m_both['v']).abs().median())
DC_OPP_MOM = int(((_m_both['a'] * _m_both['v']) < 0).sum())

#: 逐图代价的最低样本量，照抄 `build/single.py` 的 `Page.MOM_COST_MIN`（全站同一次改
#: 口径，门槛不该各定一个）。它比 `yoy.MIN_DIAG_MONTHS`（12）严一档：12 个月只够
#: caliber_diff 出一个数，24 个月才够让「符号相反的月份占 X%」这个比例不是样本噪声。
#: 不足这个数就照实说「量不出来」，**不许换一条别的序列顶上去凑格式**。
MOM_COST_MIN = 24

#: 逐图代价的账本：{图号: {'label': 点名, 'd': caliber_diff 的结果}}。
#: 页尾口径条与 4.9 节的兜底现读它，图号与条数一个都不写死。
COST_LOG = {}


def _cost_body(n, s_full, win, label):
    """算一条序列在一段窗口上的口径代价，并**记进账本**。返回 (账本条目, caliber_diff)。

    账本是按图号存的**列表**，因为一张图可以画不止一条同比线（Exhibit EX_DAYCOUNT
    的两条线就都是单月同比，两条各有各的毛刺，一条的数说不了另一条）。
    """
    d = caliber_diff_win(s_full, win, YOY.FLOW)
    row = {'label': label, 'd': d}
    COST_LOG.setdefault(n, []).append(row)
    return row, d


def _cost_stat_zh(label, d, win):
    """一条线的代价正文：不足样本就照实说量不出来，够就交给 `yoy.describe()`。

    §6.1 第 3 条要报的三样（逐月标准差、相邻月最大跳变**带月份**、符号相反的月份数）
    全在 `describe()` 里，本文件一个统计量都不自己算、也不自己排版。
    ⚠️ 样本不够时**不许**换一条别的序列的数顶上去凑格式 —— 「量不出来」本身就是
    一句该印给读者看的话。
    """
    if d['n'] < MOM_COST_MIN:
        return (f'<b>{label}</b>：代价量不出来 —— 本图窗口内两种口径都算得出的月份只有 '
                f'{d["n"]} 个（不足 {MOM_COST_MIN} 个，分母太小、报出来的比例是样本噪声'
                f'不是结构），此处不报差异；这本身也是一句该看见的提醒：'
                f'这条线的可比月很少，斜率不要外推。')
    return f'<b>{label}</b>：' + YOY.describe(d)


def yoy_cal_lines_zh(n, items, win):
    """Exhibit n 的口径 + 代价段，用于**把同比画成主序列**的折线图（不是次轴）。

    与 `yoy_cal_zh()` 的区别只有两处：抬头说的是「这张图的线本身就是同比」，
    以及一张图有几条线就报几条 —— §6.1 第 3 条要的是「这条序列自己」的实测，
    两条线共用一条线的数，与九张图共用一张图的数是同一个错。
    """
    xl = [mlab(p) for p in win]
    ds = [_cost_body(n, s, win, lab)[1] for lab, s in items]
    head = (f'<b>本图画的两条线<u>本身</u>就是<u>单月</u>同比</b>（当月 ÷ 去年同月 − 1，'
            f'不是次轴、也不是 12 个月滚动合计）—— 全站统一，'
            f'<b>页面所有者指定</b>（<code>build/CONTRACT.md</code> §6）。'
            f'<b>代价（§6.1 第 3 条）逐条线用<u>它自己</u>实测</b>，'
            f'统计范围就是本图画出来的这段窗口 —— {xl[0]} 至 {xl[-1]}'
            f'（{len(win)} 个月）：图外的历史读者看不到，报出来对不上。')
    # `yoy.describe()` 的末句是「这条线要连着柱高一起读」—— 那句是替「水平值柱 + 次轴同比」
    # 那种图写的，而本图**没有柱**（两条线本身就是同比）。措辞由 build/yoy.py 统一持有、
    # 本轮不改它，所以在这里把这句话对本图该怎么读补明白，而不是让它对着一个不存在的柱。
    fix = (f'（上面每段末句「连着柱高一起读」是 <code>build/yoy.py</code> 给'
           f'「水平值柱 + 次轴同比」那种图写的通用收尾 —— <b>本图没有柱</b>。'
           f'对本图，那句话的对应读法是：深蓝线连着 Exhibit {EX_ADV} 的柱高读，'
           f'那张画的正是这条线的水平值；灰线（总成交张数）本页<b>不单独出柱图</b>，'
           f'它的水平值 = Exhibit {EX_ADV} 的柱高 × 当月交易日数（交易日数见末尾核对表'
           f'的最后一列），汇总表「Total contracts traded (mn)」一行另给本月 / 上月 / '
           f'去年同月三个读数。）')
    return head + ''.join(_cost_stat_zh(lab, d, win) for (lab, _), d in zip(items, ds)) + fix


def yoy_cal_zh(n, s_full, win, label):
    """Exhibit n 的「口径 + 代价」图注段 —— 拿**这张图自己那条序列、自己那段窗口**实测。

    CONTRACT §6.1 第 3 条：每一张画<u>流量</u>同比的图都要印出单月口径的代价，
    「它拿**这条序列自己**实测，不引别家的例子」，而且「**『逐图』是字面意思，
    页级不算数**」。

    ⚠️ **2026-09 之前本页在这里做错过，留档 —— 两个错叠在一起。** 那一版把这段写成一个
    页级常量 `YOY_CAL`：①九张图共用一份数，量的全是**总 ADV**；②统计范围是**全历史**
    （2008-01 起 200 个可比月），而图窗是 2016-01 起的 127 期。
    除 Exhibit EX_ADV 外的八张画的都不是总 ADV，于是最刺眼的一处是 Exhibit EX_METALS
    （金属）：读者读到的「逐月标准差 18.2pp」是总 ADV 的全历史数，而金属这条线自己
    全历史 35.2pp、在本页图窗内 36.5pp —— 两个窗口下都接近两倍。
    第二处是 Exhibit EX_FX（外汇）：印着的「相邻月最大跳变 61pp（Apr-26）」是总 ADV 的，
    外汇这条线自己在图窗内最大跳 58pp（Mar-20 → Apr-20），全历史 100pp（2010-06）。
    跨页没引错，跨**图**引错了，而且引的还是一段图上看不见的历史。
    现在每张图各算各的、都只在自己那段窗口上算，数字全部由本函数现算。

    措辞照 `build/single.py` 的 `mom_cost_zh()`：口径抬头 → 窗口那一句 → `yoy.describe()`。
    三样必报的东西全在 `describe()` 里：逐月标准差、相邻月最大跳变（带月份）、
    两种口径符号相反的月份数。

    `label` 是这条序列的中文点名，进图注 —— 读者要能一眼看出这段数是**这张图**的。
    """
    d = _cost_body(n, s_full, win, label)[1]
    xl = [mlab(p) for p in win]
    head = (f'<b>次轴 = <u>单月</u>同比</b>（当月 ÷ 去年同月 − 1），全站统一 —— '
            f'<b>页面所有者指定</b>（<code>build/CONTRACT.md</code> §6：全站同比只有这一种，'
            f'页面上一条 12 个月滚动合计同比都不画）。'
            f'好处只有一个，但是决定性的：<b>柱与线取自同一列</b> —— 拿这根柱除以 12 根柱'
            f'之前那根，就是线上这一点，读者可以自己核对。')
    # ⚠️ 这一句**不许出现图窗以外的月份标签**：图注里点到的每个月份读者都会去横轴上找，
    # 找不到就是一句读者无法核对的话（CONTRACT §6.4）。本页序列自 2008 年起、图窗自
    # 2016 年起，所以这里说的是「图窗左边还有多少个月的历史」，不写那个月份的名字。
    _pre = len(df.index) - len(win)
    tail = (f'（换来的一点好处：单月口径只要 12 个月历史，滚动口径要 24 个月；'
            f'而本页序列在图窗左端之前还有 {_pre} 个月的历史 —— '
            f'折线在窗口最左边那一格就已经有值，左端不再有一段空着的线。）')
    if d['n'] < MOM_COST_MIN:
        return (head +
                f'代价（§6.1 第 3 条）本该在这里用<b>本图这条序列（{label}）</b>自己实测，'
                f'但本图窗口 {xl[0]} 至 {xl[-1]}（{len(win)} 个月）内两种口径都算得出的'
                f'月份只有 {d["n"]} 个（不足 {MOM_COST_MIN} 个，分母太小、报出来的比例是'
                f'样本噪声不是结构），此处不报差异；这本身也是一句该看见的提醒：'
                f'这条线的可比月很少，斜率不要外推。' + tail)
    return (head +
            f'<b>代价（§6.1 第 3 条）用<u>本图这条序列</u>（{label}）自己实测</b>，'
            f'而且<b>只统计本图画出来的这段窗口</b> —— {xl[0]} 至 {xl[-1]}'
            f'（{len(win)} 个月）：图外的历史读者看不到，报出来对不上；'
            f'别的图那条线毛刺多大与这条线无关，各图的数各自印在各自图注里。'
            + YOY.describe(d) + tail)

# 存量图（月末未平仓合约）的对应说明。它的算法与全页一致（当月 ÷ 去年同月），
# 但读的东西不同，而且它本来就没有第二种合法口径可选 —— 这两件事都要说清楚，
# 否则读者会以为它是「漏改的那一张」。
STOCK_CAL = (f'<b>次轴 = <u>单月</u>同比</b>（当月 ÷ 去年同月 − 1），算法与本页其余各图的'
             f'次轴完全相同，但<b>读的东西不同</b>：未平仓合约是<b>存量</b>（月末快照），'
             f'这条线比的是两个<b>时点</b>的持仓，其余各图比的是两个<b>月份</b>的成交流量，'
             f'高低不要放在一起比。'
             f'另外这一张不存在「改不改口径」的选择：存量做不了 12 个月滚动合计 —— '
             f'把 12 个月末的存量加起来不是任何东西，既不是「一年的量」（存量不累积），'
             f'也不是「平均水平」（没除以 12），<code>build/yoy.py</code> 对存量调滚动合计'
             f'直接抛错。存量也不吃日历效应（不像成交量要看当月有几个交易日），'
             f'所以这条线本来就比成交量的同比稳 —— 两组数都在<b>本图这段窗口</b>'
             f'（{XL25[0]} 至 {XL25[-1]}，{WIN_LINE} 个月）上量：'
             f'本图这条未平仓合约线的单月同比标准差 {CALIB_OI["sd_m"]:.1f}pp、'
             f'相邻月最大跳变 {CALIB_OI["jump_m"]:.0f}pp（{CALIB_OI["jump_m_at"]}），'
             f'而同窗口的总 ADV（Exhibit {CAL_EX} 那条线）是 {CALIB["sd_m"]:.1f}pp 与 '
             f'{CALIB["jump_m"]:.0f}pp。'
             f'（§6.1 第 3 条那笔「换口径的代价」这一张不欠：存量本来就走点对点，'
             f'没有第二种合法口径可拿来做对照，所以这里给的是<b>与流量图的对比</b>，'
             f'不是代价。）')

# 七条：总 RPC + 六个品种。2026-09 之前只加载四个品种（农产品与外汇没进来），
# 于是标题写着「by asset class」的那张图只画得出四条，而收入占比图需要六条才算得出。
RPC = rpc_quarterly([('total', 'rpc_total')] + [(k, m) for k, m, _ in CLS_RPC])
rpc_m = to_monthly(RPC['total'], df.index)
df['implied_txn_rev_usdmn'] = df['total_vol_mn'] * rpc_m    # 百万张 x $/张 = $mn
RPC_Q, RPC_V = RPC['total'].index[-1], float(RPC['total'].iloc[-1])

#: 各品种最新一季的读数，图注里逐条印出来（图上按 $0.01 显示，第三位小数以图注为准）。
_RPC_LAST = '、'.join(f'{zh} ${RPC[k].iloc[-1]:.3f}' for k, _, zh in CLS_RPC)
_RPC_HI = max(CLS_RPC, key=lambda t: RPC[t[0]].iloc[-1])
_RPC_LO = min(CLS_RPC, key=lambda t: RPC[t[0]].iloc[-1])
#: 「各品种 RPC 相差几倍」——页尾与收入占比图都引这个数，全页只算这一次。
RPC_SPREAD_X = float(RPC[_RPC_HI[0]].iloc[-1] / RPC[_RPC_LO[0]].iloc[-1])

# ══════════════════ TTM 合计（只供抬头那一项读数，页面上不画）══════════════════
# 2026-09 那张「当月成交张数柱」按页面所有者指令删除之后，本页**不画任何一条 TTM
# 曲线**。留下的这一列只有一个用途：抬头里「近 12 个月成交 X mn 张」那一项 ——
# 一个水平值，不是同比。**别顺手删它**：兜底⑤盯着抬头那一项。
# （同时删掉了 ttm_rev_usdmn / ttm_rpc_usd：口径改完之后没有任何地方读它们，
#  而「TTM 序列供量价分解共用」那句原注释也不再成立 —— Exhibit EX_DECOMP 的两条腿是
#  **逐月**取值（当月 vs 去年同月），从来没有走过这三列。）
df['ttm_vol_mn'] = YOY.ttm(df['total_vol_mn'], YOY.FLOW)           # 近 12 个月成交合约数

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

def _sum_provenance():
    """汇总表每一行的水平值是哪来的 —— 三档，判据全部现算，不靠人肉名单。

      · **披露原列**：列名出现在 CSV_COLS（series/cme.csv 的表头）里，原样照抄；
      · **单位换算**：不是原列，但逐月都等于某个原列乘同一个常数 —— 源列与常数都是
        除出来的，不是写在这里的；
      · **推导**：两档都不是。必须在 SUM_CALC 里登记算式，登记不到就停机。

    表注末句由这三档拼出（_sum_src_txt），所以「哪几行不是披露值」这句话与实际来源
    只有一个源头。原先那句「全部为 CME 官方披露值，无推导。」正是同一张表里的
    「Total contracts traded (mn)」（= ADV × 交易日，CSV 里没有这一列）证伪的。
    """
    raw, unit, calc = [], [], []
    for kind, label, col, _dec, _cal in SUM_ROWS:
        if kind != 'row':
            continue
        if col in CSV_COLS:
            raw.append(label)
            continue
        hit = None
        for c in CSV_COLS:                       # 按 CSV 原顺序找，结果与遍历顺序无关
            with np.errstate(divide='ignore', invalid='ignore'):
                r = df[col].to_numpy() / df[c].to_numpy()
            if np.all(np.isfinite(r)) and np.allclose(r, r[0], rtol=1e-9, atol=0.0):
                hit = (c, float(r[0]))
                break
        if hit:
            unit.append((label, hit[0], hit[1]))
        elif col in SUM_CALC:
            calc.append((label, SUM_CALC[col][0]))
        else:
            raise SystemExit(
                f'汇总表的「{label}」取的列 {col} 既不在 series/cme.csv 的表头里，也不是'
                f'任何一个披露原列的常数倍 —— 那它就是本页算出来的，必须在 SUM_CALC 里'
                f'登记算式（算式会原样印进表注，所以要写成读者看得懂的话）。')
    return raw, unit, calc


SUM_RAW, SUM_UNIT, SUM_DERIVED = _sum_provenance()


def _factor(k):
    """常数倍 → 读者看得懂的写法：1e-06 印成「÷ 1,000,000」而不是「× 1e-06」。"""
    inv = 1.0 / k if k else float('inf')
    if abs(inv) >= 1 and abs(inv - round(inv)) < 1e-6:
        return f'÷ {round(inv):,}'
    return f'× {k:g}'


def _sum_src_txt():
    """表注末句。名单、算式、行数全部来自 _sum_provenance()，一个字都不是写死的。"""
    bits = [f'「{lab}」是披露列 <code>{src}</code> 的单位换算（{_factor(k)}）'
            for lab, src, k in SUM_UNIT]
    bits += [f'「{lab}」是本页算出来的：{how}' for lab, how in SUM_DERIVED]
    if not bits:
        return (f'本表 {len(SUM_RAW)} 行水平值逐行照抄 series/cme.csv 里的 CME 披露列，'
                f'没有换算也没有推导。')
    return ('<b>本表有哪几行不是 CME 直接披露的</b>（判据是 series/cme.csv 的表头，'
            '构建期现读）：' + '；'.join(bits)
            + f'。另外 {len(SUM_RAW)} 行的水平值照抄披露列原值。')


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
                 # 具名月份之比。2026-09 全页口径统一成单月之后，这一列与各图次轴**同口径**
                 # 了 —— 但仍然要点名：一是本表的口径本来就由列头钉死、不随页面口径变，
                 # 二是「同口径」这件事本身是读者要知道的（上一版这里写的是「不是一个口径」，
                 # 改口径之后那句话当场变成假话）。
                 '<b>本表的 y/y 是单月同比</b>（本月 ÷ 去年同月 − 1），'
                 f'与 {len(_GS_MOM)} 张 gs_bar 次轴的金色折线<b>同一个口径</b>'
                 f'（全页统一，见口径与方法说明{note_ref("⟨note:caliber⟩")}），可以直接对读：'
                 f'本表三列写死的就是'
                 f'「本月 / 上月 / 去年同月」这三个具名月份，本表的口径由列头决定，'
                 f'即使页面口径日后再变也只能是这一个。'
                 f'单月同比有多毛：Exhibit {CAL_EX} 那条总 ADV 在图窗（{XL25[0]} – '
                 f'{XL25[-1]}）内的实测是 {CALIB["n"]} 个可比月里 {CALIB["n_opp"]} 个月'
                 f'与 12 个月滚动口径（本页不画，只作对照）符号相反 —— '
                 f'这个数<b>逐图不同</b>，别的图各自印在自己的图注里。'
                 f'本表回答的是「本月相对上月与去年同月的水平」；本页不画任何平滑口径的线，'
                 f'要判趋势得看柱高本身的形状（Exhibit {EX_ADV} 的柱高），'
                 f'不是看某一个月的同比读数。'
                 'ADV is already day-count neutral; total contracts traded is not. '
                 f'Exhibit {EX_DAYCOUNT} isolates the difference.（原 PDF 此处误写作 '
                 f'Exhibit 4 —— 汇总表本身占 Exhibit 1，day-count 图是 Exhibit '
                 f'{EX_DAYCOUNT}。）'
                 '3Y %ile = 当月读数在最近 36 个月里高于多少百分比的观测，判据见'
                 f'「口径与方法说明」{note_ref("⟨note:pctile⟩")}。'
                 + (f'本表留空的行：{blank}。' if blank else '本表没有留空的分位。')
                 + '「Trading days」行的 m/m 与 y/y 只给数字、不着色，理由同上。'
                 # 原句是「全部为 CME 官方披露值，无推导。」——被同一张表里的
                 # 「Total contracts traded (mn)」当场证伪（CSV 里没有这一列，是本页
                 # 用 ADV × 交易日算的）。改成现读 CSV 表头判来源，判据与句子对不上
                 # 就在 §7 的兜底③停机。
                 + _sum_src_txt()),
    }


# ══════════ 4. Exhibit EX_ADV .. EX_HEAT_SHARE（图号见文件头的常量表）══════════
def yoy_line(col, win_n=WIN_LINE, kind=YOY.FLOW):
    """次轴折线的数值 —— 全页统一走**单月**同比（当月 ÷ 去年同月 − 1，见上面的口径段）。

    流量与存量在算法上是同一件事，但 `kind` 仍然必传：`YOY.mom_yoy` 用它决定比率列出
    百分点差、也用它把「这一列是流量还是存量」这个判断留在调用点（build/yoy.py 模块头：
    这个判断不许默认掉）。同比一律在**全历史上算完再切窗**，切完再算的话窗口最前 12 期
    永远是空的（CONTRACT §6.4）。

    引擎不替我们算同比 ——「这一点的同比有没有意义」是口径判断，只能在 Python 侧做。
    """
    return L(YOY.mom_yoy(df[col], kind).values[-win_n:])


#: gs_bar() 建过的**存量口径**图号（kind=YOY.STOCK）。口径统一成单月之后，「哪几张是
#: 单月」已经不再有区分度（全都是），但「哪一张读的是存量」仍然要点名 —— 4.9 节拿它
#: 核对那句因果，不核对，那句因果就只是作者的记忆。
_GS_STOCK = []

# ══ 已知残留：gs_bar 首末点的数值标签压住左侧刻度栏（2026-08-19 裁决 WONT_FIX）══
# 不是「没发现」，是**发现了、量过了、这一轮修不了**，所以写在这里而不是只留在工作日志里。
# 机理：窗口从 13 个月放到 WIN_LINE 期之后一格宽度骤缩，而标签宽度预算 = band + 12 − 3
# （chartscale._budget）跟着缩，位数多一点的读数就超。
# 名单与超出量**不抄在这里**（抄了下个月就过期，而且没有任何东西会报错）—— 跑这段就有：
#     python3 - <<'PY'
#     import json, sys; sys.path.insert(0, 'build'); import mrwin
#     t = open('data/cme.js').read(); d = json.loads(t[t.index('{'):t.rindex('}') + 1])
#     for e in d['exhibits']:
#         r = mrwin.label_clash(e)
#         if r and r['over'] > 0: print(e['n'], r)
#     PY
#   把同一段的路径换成 `git show ab70cd7^:data/cme.js` 的落盘副本，就是放宽**之前**的量尺：
#   那份 payload 逐张的 over 都是负数（全部在预算内）—— 所以这几处是窗口放宽**引入**的，
#   不是历史遗留。ab70cd7^ 是不会再变的 git 对象，这个结论照命令复核即可，不必信这行字。
#   （上一版在这里写「band 459px、over 一律 −44x」，两项对当时的月度成交张数柱都不对：
#    它当时 band 35.3px、over −24.3。结论不受影响，但「一律」在这里就是错的。
#    那张图已于 2026-09 按所有者指令删除。）
# 为什么本文件不修：能收口的只有标签预算与抽稀策略，两者都在 assets/charts.js（34 页共用的
# 渲染层，本轮明令不许碰）。在 build/cme.py 这一侧能做的只有「把窗口改回 13 个月」或「换一个
# 位数更少的 fmt」——前者是拿判据去迁就排版（本页反复拒绝的做法），后者会改掉读数本身。
# 两道闸门都不拦这一项（build/verify_pages.py 0 ERROR、tools/visual_qa.py --page cme
# 🔴0🟡0🔵0），所以它不会自己冒出来：真要收口，动的是 charts.js 的 LAB_GAP 与抽稀策略。
def gs_bar(n, col, title, ylab, fmt, legend, note=None, src_extra=None, kind=YOY.FLOW,
           zh=None):
    """← gsx.lvl_bar：浅蓝柱 + **次轴金色 y/y 折线**。窗口 `WIN_FROM` 起（本页 127 期）。

    2026-08-19 窗口由 13 个月放到 2016-01 起。原来的 13 个月不是数据下限：同一份
    series/cme.csv 从 2008-01 起就是满的（那段历史页面上不再单独画），13 是**画的时候
    截的**。契约 §5.4 写的是「近期图**固定** 13 个月」，本页是有意不照它办、不是把
    「固定」读成「至少」；这处冲突写在页尾 notes 的「与原 PDF 版的有意差异」条里，
    §5.4 本身该不该改由 build/CONTRACT.md 的持有者裁决。127 期塞不进半栏卡片，
    通栏与 x 标签抽稀交给 `mrwin.layout_all()` 按 charts.js 的量边距算式判，不在这里拍。

    次轴画的是同比而不是 12 个月滚动均线 —— gsx.lvl_bar 的 docstring 写死了这条理由：
    「均线只是把柱子再平滑一遍、不带新信息，同比才回答『相对去年这个月是好是坏』」。
    **本函数**生成的每一张 gs_bar 都由 build_cme.py 的 gsx.lvl_bar 移植而来，所以与 deck
    对齐：给 yoy 就不画均线（引擎侧自动），同时不再需要左上角那个 y/y 气泡。数一句「本页
    共几张 gs_bar」写进注释是没用的（加一张就过期）—— 要点名哪几张，见 4.9 节现读 payload
    的那段。

    2026-09 改口径：**所有**序列那条折线一律画**单月**同比（当月 ÷ 去年同月 − 1），
    页面所有者指定，理由与代价见文件上半部的口径段。轴标题与图例名一并写明 single month
    —— 只改数不改名，读者会拿一条口径已经变了的线当原来那条读，那比不改更糟。
    每张图的 note 都挂上对应的压缩版口径说明（带本页实测的代价数字）。

    kind=STOCK 的图（月末未平仓合约）算法与流量图完全相同（同一个 YOY.mom_yoy），
    但挂的是 STOCK_CAL：它读的是两个**时点**的存量而不是两个月份的流量，
    而且它从来就没有「滚动合计」这个选项（判据与实现见 build/yoy.py）。
    """
    if kind == YOY.STOCK:
        _GS_STOCK.append(n)             # 4.9 节核对「读存量的是哪一张」
    ex = {'n': n, 'kind': 'gs_bar', 'title': title, 'fmt': fmt, 'ylab': ylab,
          'ylab2': '% y/y, single month',
          # xlabels 必须显式给：不给就退到 payload 的页级默认，而 mrwin.layout_all()
          # 只对**自带 xlabels** 的 exhibit 判通栏与抽稀，漏给等于这张图不过排版裁决。
          'legend': legend, 'xlabels': XL25, 'values': L(win(col, WIN_LINE)),
          'yoy': {'name': 'y/y, single month (RHS)',
                  'color': 'GOLD', 'yfmt': 'pct0',
                  'values': yoy_line(col, win_n=WIN_LINE, kind=kind)}}
    # §6.1 第 5 条：近零基数的序列不画同比、画水平值 —— 契约明说这一条在单月口径下
    # （滚动合计能把一个近零的分母摊薄，单月不能）。逐张现验，命中就停机而不是画一条
    # 「读的是分母不是量」的线。判据与两个阈值的推导都在 build/yoy.py。
    _nz = YOY.near_zero_base(df[col], win=list(W25))
    if _nz['flag']:
        raise SystemExit(
            f'Exhibit {n}（{col}）的近零基数月在窗口内占 {_nz["share"]:.1%}（≥ 1/12），'
            f'CONTRACT §6.1 第 5 条：这条序列不该画同比，该画水平值。'
            f'最极端的一个月：{_nz["worst"]}')
    # 口径 + 代价：流量图**逐图现算**（拿这张图自己那条列、自己那段窗口），
    # 存量图走 STOCK_CAL（§6.1 第 3 条把「印代价」这条债限定在流量列上，
    # 存量没有第二种合法口径，也就没有「换口径的代价」可报）。
    if kind == YOY.STOCK:
        cal = STOCK_CAL
    else:
        if not zh:
            raise SystemExit(
                f'Exhibit {n}（{col}）画的是流量单月同比，但 gs_bar 没收到 zh= 点名 —— '
                f'CONTRACT §6.1 第 3 条要求逐图印代价，而代价那段要在图注里点明'
                f'「这是本图这条序列的实测」，点名不能省。')
        cal = yoy_cal_zh(n, df[col], W25, zh)
    ex['note'] = (note + ' ' + cal) if note else cal
    if src_extra:
        ex['src_extra'] = src_extra
    return ex


#: 图注里凡是讲「**别的**图是什么样」的句子（次轴口径、左端），写这张图的时候后面的图
#: 还没画出来，落笔的只能是作者脑子里的枚举 —— 本页因此埋过三次假的全称断言（见 4.9 节）。
#: 所以这两处先放占位符，等所有 exhibit 都画完再由 4.9 节现读 payload 回填；回填不到就停机。
_NAV_GS_CAL = '⟨nav:gs-caliber⟩'
_NAV_AX_OTHER = '⟨nav:ax-other⟩'

ex = []


def _ylab_of(n):
    """现读某张**已经画好**的图的纵轴名。图注里提别的图的单位时走这里 ——
    本页出过一次把 Exhibit EX_ADV 的单位写成「千张/日」的错（它的纵轴是
    mn contracts / day，差一千倍），从此提别图的单位一律现读，不手抄。"""
    return next(e['ylab'] for e in ex if e['n'] == n)


# 全页第一张图，因此由它交代窗口与左端 —— 这段话 2026-09 之前挂在全历史线那张图的
# 图注上，那张按所有者指令删除时整段搬到了这里（占位符 {_NAV_AX_OTHER} 全页只有一个
# 宿主，丢了宿主 4.9 节的回填闸门会当场停机）。
# 搬家同时补了一句删图之后才需要的话：页顶那段与汇总表的分位用的是**全样本**排名，
# 而本页现在没有任何一张图画到图窗左端之前 —— 不说明白，读者在页面上无从核对。
ex.append(gs_bar(EX_ADV, 'adv_mn', 'Total average daily volume', 'mn contracts / day', 'f1',
                 'Total ADV', zh='总 ADV',
                 note=(f'本图与本页其余<b>按月推进</b>的图，左端一律是 {WIN_FROM}'
                       f'（{XL25[0]} 起的 {WIN_LINE} 个月）；季度刻度只有 '
                       f'Exhibit {EX_RPC} 一张，同一个左端换算成 {qlab(Q_FROM)}。'
                       f'{_NAV_AX_OTHER}'
                       f'<b>图窗之外还有历史</b>：<code>series/cme.csv</code> 自 '
                       f'{mlab(df.index[0])} 起满 {len(df)} 个月，页顶那段的名次与'
                       f'「峰值停在哪个月」用的是这个<b>全样本</b>，而本页图上看不到早于 '
                       f'{XL25[0]} 的点（2026-09 之前有一张画到序列起点的全历史线，'
                       f'已按页面所有者指令删除）—— 图窗内核不到的名次，出处在那份 CSV。'
                       f'最近 {WIN_TABLE} 个月的原始单位读数见末尾核对表。')))

ex.append({
    'n': EX_DAYCOUNT, 'kind': 'lines_endlabels', 'fmt': 'f1', 'xlabels': XL25,
    # 标题写明「single-month」：本图的命题就是「一个月内交易日数能把方向读反」，
    # 换滚动口径两条线就重合了、图就空了（2026-08 那轮口径改造时的判定，2026-09 全页
    # 改回单月之后这张图的口径反而成了默认）。标题里那四个字不能省 ——
    # CONTRACT §6 要求口径写进标题，check_yoy_caliber 的 R4 判的就是这个。
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
             # 这半句的职责是替读者做「别的图是什么口径」的导航，所以它**只能现读 payload**：
             # 2026-08-19 这里写过「各 gs_bar 的次轴已改 12 个月滚动合计同比」，而 Exhibit 9
             # 就是 gs_bar、次轴却是单月同比（存量不可滚动）—— 一句导航把读者导到了错的
             # 地方，还和 Exhibit 9 自己的图注、页尾的口径条三方打架。判据现成（e['ylab2']
             # 与 e['yoy']['name'] 里写着 single month 还是 roll），回填见 4.9 节。
             f'<b>本图是全页唯一把同比画成<b>主序列</b>的折线图</b>（{_NAV_GS_CAL}）：'
             f'这张图的全部命题就是「交易日数差异能在<b>一个月</b>之内把成交量的方向读反」'
             f'（Barclays 调整）。'
             # 这一段现在有两个用途：既解释本图为什么必须是单月口径（改成滚动它会消失），
             # 也解释全页改成单月之后「为什么还是不把日均乘回交易日」——
             # 两个用途的实测数字方向相反，所以两组都要印，不能只留下好看的那一组。
             f'改成滚动口径这张图会自己消失 —— 实测（滚动那一侧本页不画，只作对照）：'
             f'滚动口径下两条线的逐月标准差是 {CALIB["sd_r"]:.1f}pp（按日）vs '
             f'{DAYCOUNT_STATS["sd_r"]:.1f}pp（总量），最大差 {DC_MAXGAP:.1f}pp，'
             + ('且逐月符号完全一致' if DC_SAME_SIGN else '仍有符号不一致的月份')
             + f'，交易日效应在 12 个月窗口里基本自抵。'
             f'<b>而在本页现在用的单月口径下它完全不自抵</b>：同一对序列的标准差是 '
             f'{CALIB["sd_m"]:.1f}pp vs {DAYCOUNT_STATS["sd_m"]:.1f}pp，'
             f'{DC_N_MOM} 个可比月里两者最大差 <b>{DC_MAXGAP_MOM:.1f}pp</b>'
             f'（中位 {DC_MEDGAP_MOM:.1f}pp），有 <b>{DC_OPP_MOM}</b> 个月<b>符号相反</b> —— '
             f'这正是本页坚持画 CME 直接披露的 ADV（已按交易日中性化）、不把日均乘回交易日的理由，'
             f'也是这张图在口径统一之后反而更该看的理由。'
             f'两条线与各图次轴<b>现在是同一个口径</b>（都是单月同比），可以跨图对读；'
             f'其中深蓝线（按日）与 Exhibit {EX_ADV} 次轴的金线是<b>逐点相同的同一条'
             f'序列</b>（构建期逐点现验，对不上就不出图），本图的作用是把它与灰线并排'
             f'放在同一根轴上量那个差；灰线（总量）本页只在这里画一次，没有第二处。'
             # §6.1 第 3 条对本图同样开口：这张图的两条线就是单月同比本身，
             # 所以代价要逐条印，而且印的是**这两条线自己**的数，不是别的图的。
             + yoy_cal_lines_zh(EX_DAYCOUNT,
                                [('总成交张数（灰线）', df['total_vol_mn']),
                                 ('ADV，按日、交易日中性（深蓝线）', adv)],
                                W25)),
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
# 每期六列里有几列带小数 —— 印给读者的那句话只能照 _mix_int 的判据说（「不全是整数」），
# 不能升级成「六列都是三位小数」：2025-06 的利率列就是整数 11587，而它恰是这一组里
# 残差最大、图注点名的那一期；另外几期还有两位小数的列。判据比句子弱，句子就得跟着弱。
_mix_frac = np.array([sum(1 for c, _, _ in CLS if not float(_stack[c][i]).is_integer())
                      for i in range(WIN_LINE)])
_mix_eq = _mix_abs < _MIX_TOL           # 视同严格相等（含纯浮点噪声）
_mix_rnd = ~_mix_eq & _mix_int          # 整千张披露 ⇒ 差的是各自取整到千张的舍入
_mix_sub = ~_mix_eq & ~_mix_int         # 带小数披露 ⇒ 舍入解释不适用


def _mix_round_txt():
    """Exhibit 4 图注里那句残差说明。三组各自成句，缺哪组哪句就不出现。"""
    if not (_mix_rnd.any() or _mix_sub.any()):
        return (f'{len(CLS)} 段之和逐月严格等于披露的 Total ADV（{WIN_LINE} 期，'
                f'判据带 {_MIX_TOL * 1000:.1f} 张合约的容差，'
                f'滤掉 {len(CLS)} 列浮点相加的舍入残渣）。')
    _tot = win('adv_total_kcontracts', WIN_LINE)
    _noise = _mix_abs[_mix_eq].max() * 1000 if _mix_eq.any() else 0.0
    out = [f'{len(CLS)} 段之和与披露的 Total ADV 在 {WIN_LINE} 期里有 '
           f'{int(_mix_eq.sum())} 期相等（判据带 {_MIX_TOL * 1000:.1f} 张合约的容差 —— '
           f'{len(CLS)} 列 float64 相加的舍入残渣'
           f'实测最大 {_noise:.0e} 张，直接拿 ≠0 去比会把它当成差异）。']
    if _mix_rnd.any():
        _lo, _hi = int(_mix_abs[_mix_rnd].min()), int(_mix_abs[_mix_rnd].max())
        _pmax = (_mix_abs / _tot * 100)[_mix_rnd].max()
        out.append(f'另有 {int(_mix_rnd.sum())} 期差 '
                   f'{_lo if _lo == _hi else f"{_lo}–{_hi}"} 千张'
                   f'（最大 {_hi} 千张 = 该月总量的 {_pmax:.3f}%）—— 这些月份 CME '
                   f'{len(CLS)} 个品种披露的都是<b>整千张的整数</b>（这一条是逐期逐列'
                   f'核对过的，这几期就是按它分出来的），差的就是各自取整到千张的舍入，'
                   f'不是漏了品种。')
    if _mix_sub.any():
        _j = int(np.where(_mix_sub, _mix_abs, -1.0).argmax())
        _c = np.round(_mix_abs[_mix_sub] * 1000).astype(int)
        _fl, _fh = int(_mix_frac[_mix_sub].min()), int(_mix_frac[_mix_sub].max())
        out.append(f'还有 {int(_mix_sub.sum())} 期差不到 1 千张（逐期 {_c.min():,d}–'
                   f'{_c.max():,d} 张，最大的一期在 {XL25[_j]}）—— 这几期 {len(CLS)} '
                   f'个品种<b>不全是整千张</b>（逐期实测 {len(CLS)} 列里有 '
                   f'{_fl if _fl == _fh else f"{_fl}–{_fh}"} 列带小数），'
                   f'所以上面那条「各自取整到千张」的解释对它们不成立，'
                   f'零头出在哪一段官方没有交代。')
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
    'note': (f'CME 的 {len(CLS)} 个品种划分是穷尽且互斥的，所以柱高之和在<b>口径上</b>'
             f'就是披露的 Total ADV；但<b>数值上</b>并非逐月严格相等。'
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

_SPLIT_NOTE = (f'原 PDF 把 {len(CLS)} 个品种画在同一根轴上，利率品种的峰值 '
               f'{df["adv_rates_kcontracts"].iloc[-WIN_LINE:].max():,.0f} 独自定死了量程，'
               f'{" / ".join(nm for _, nm, _ in CLS_MINOR)} '
               f'{len(CLS_MINOR)} 条线被压成底部一条带、彼此分不开。'
               f'这里按窗口内峰值大小拆成 Exhibit {EX_MAJORS}（峰值最大的 '
               f'{len(CLS_MAJOR)} 个）与 Exhibit {EX_MINORS}（另外 {len(CLS_MINOR)} 个）'
               f'两张，窗口、口径、配色一律不变，一个点也没有删；'
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

# 两张图的量级比现算。原文写的是「纵轴上界只有 Exhibit 5 的约五分之一」——
# 约数一换窗口就更不准，索性给实测值。
_MAJOR_MAX = float(max(np.nanmax(win(c, WIN_LINE)) for c, _, _ in CLS_MAJOR))
_MINOR_MAX = float(max(np.nanmax(win(c, WIN_LINE)) for c, _, _ in CLS_MINOR))
# ── 兜底：分组判据「峰值最大的两个 vs 其余四个」必须真的成立 ──────────────
# 两组的峰值区间一旦交叉，「两大 / 四小」这个说法就没了依据，图注也该跟着重写 ——
# 让它在构建期响，而不是等读者拿 Exhibit 5 的纵轴去比 Exhibit 6 的线。
_MAJOR_MIN_PEAK = float(min(np.nanmax(win(c, WIN_LINE)) for c, _, _ in CLS_MAJOR))
if _MINOR_MAX >= _MAJOR_MIN_PEAK:
    raise SystemExit(
        f'品种拆图的判据是「窗口内峰值最大的两个 vs 其余四个」，但现在四小品种的峰值 '
        f'{_MINOR_MAX:,.0f} 已经不低于两大品种里较小的那个（{_MAJOR_MIN_PEAK:,.0f}）——'
        f'CLS_MAJOR / CLS_MINOR 的划分和两张图的图注都得重写，不是改个数字。')
ex.append({
    'n': EX_MINORS, 'kind': 'lines_endlabels', 'fmt': 'f0c', 'xlabels': XL25,
    'title': 'ADV by asset class: energy, ag, FX and metals',
    'ylab': 'k contracts / day',
    'series': [{'name': nm, 'color': cl, 'values': L(win(c, WIN_LINE))}
               for c, nm, cl in CLS_MINOR],
    # 「量级差一个数量级」这句原话被紧跟着的现算数字当场推翻（实测 24%，是 4 倍出头
    # 不是 10 倍），而且逐序列看两组根本不是按量级分开的 —— 能源的区间整段落在股指
    # 里面。改成陈述真正的判据（峰值最小的四个），那条判据由构建期的兜底核对。
    'note': (f'与 Exhibit {EX_MAJORS} 同一份数据、同一个 {WIN_LINE} 个月窗口，'
             f'只是把窗口内峰值最小的 {len(CLS_MINOR)} 个品种单独放到自己的轴上。'
             f'差多少现算：本图 {len(CLS_MINOR)} 条线在窗口内的最大值是 {_MINOR_MAX:,.0f}，'
             f'Exhibit {EX_MAJORS} 是 {_MAJOR_MAX:,.0f}，前者是后者的 '
             f'{_MINOR_MAX / _MAJOR_MAX * 100:.0f}% —— 纵轴上界随之低一档，'
             f'两张图不能跨图比高度。'),
})

ex.append(gs_bar(EX_RATES, 'adv_rates_kcontracts', 'Interest-rate complex ADV',
                 'k contracts / day', 'f0c', 'Interest rates ADV', zh='利率品种 ADV'))
ex.append(gs_bar(EX_EQUITY, 'adv_equity_kcontracts', 'Equity-index complex ADV',
                 'k contracts / day', 'f0c', 'Equity index ADV', zh='股指品种 ADV'))
ex.append(gs_bar(EX_ENERGY, 'adv_energy_kcontracts', 'Energy complex ADV',
                 'k contracts / day', 'f0c', 'Energy ADV', zh='能源品种 ADV'))
ex.append(gs_bar(EX_FX, 'adv_fx_kcontracts', 'FX complex ADV', 'k contracts / day', 'f0c', 'FX ADV',
                 zh='外汇品种 ADV'))
ex.append(gs_bar(EX_METALS, 'adv_metals_kcontracts', 'Metals complex ADV', 'k contracts / day', 'f0c',
                 'Metals ADV', zh='金属品种 ADV'))
ex.append(gs_bar(EX_AG, 'adv_ag_kcontracts', 'Agricultural complex ADV', 'k contracts / day', 'f0c',
                 'Agricultural ADV', zh='农产品品种 ADV'))
ex.append(gs_bar(EX_OI, 'oi_total_mn', 'Month-end total open interest', 'mn contracts', 'f1',
                 'Month-end OI', kind=YOY.STOCK,
                 note='月末未平仓合约是存量口径（期末快照），与 ADV 这类流量口径不可直接相加。'))
# 派生列：代价拿**本图真画出来的那条隐含收入序列**自己跑（= 当月成交张数 × 当季 RPC），
# 不拿它的任一分量顶替 —— 两个因子各自的同比不等于乘积的同比，而读者读的是乘出来的这条线。
ex.append(gs_bar(EX_REV, 'implied_txn_rev_usdmn', 'Implied transaction revenue', '$mn / month',
                 'usd0', 'Implied transaction revenue', note=BR_NOTE,
                 zh='隐含交易收入，= 当月成交张数 × 当季 RPC'))

# ══════════ Exhibit EX_REVMIX：隐含收入的品种结构（100% 堆叠）══════════
# 为什么要这张：**成交量的结构 ≠ 收入的结构**。各品种 RPC 相差数倍（Exhibit EX_RPC），
# 所以同一个月里利率品种占了一半以上的成交量、却只贡献四成的隐含收入。这件事此前页面上
# 一张图都读不出来 —— Exhibit EX_MIX 画的是各品种 ADV 的**绝对水平**堆叠（柱高之和 =
# Total ADV），量的结构要靠段的比例去看，钱的结构则完全没有。
#
# ⚠ **分母只能是「六个品种隐含收入之和」，不能用 Exhibit EX_REV 那条线**
#   （= 总张数 × CME 披露的混合 rpc_total）。两者逐月不等而且**会变号** —— 差不在量侧
#   （六品种 ADV 相加与披露 Total ADV 只差舍入，见 Exhibit EX_MIX 图注那段实测），
#   而在费率侧：rpc_total 是 CME 从总收入倒算的混合费率，不等于六条品种 RPC 按各自
#   成交量加权。残差既然会变号，「以 EX_REV 为分母、把差额画成第七段灰色残差」这条路
#   也走不通：stacked_dual 画不了负段（引擎只钳段高、base 已经被减过头，整柱上移且不报错）。
#   本图因此**自归一**：六段之和按构造恒为 100%，与 EX_REV 的差现算印在图注里。
_rm_leg = {k: (df[c] * days / 1000.0 * to_monthly(RPC[k], df.index)).reindex(W25).values
           for c, _, _, k, _, _ in CLS_REV}                       # $mn / 月
_rm_sum = np.sum(list(_rm_leg.values()), axis=0)

# ── 护栏①：窗口内六条腿都不许缺值。stacked_dual 属 mrwin.DENSE，一个 null 就让那根柱
#    整根不画，而引擎不报错。六条 RPC 自 2013-Q2 起、图窗自 WIN_FROM 起，中间只隔十几个
#    季度 —— 窗口一旦再往左放宽就会画出塌到零的假柱，所以这道断言必须在。
_rm_holes = [nm for (_, nm, _, k, _, _) in CLS_REV if np.isnan(_rm_leg[k]).any()]
if _rm_holes or np.isnan(_rm_sum).any():
    raise SystemExit(f'Exhibit {EX_REVMIX} 是平滑图型，窗口内不许有缺值：'
                     f'{_rm_holes or "六腿合计"}')
# ── 护栏②：分母必须为正（占比无定义时本页的做法是不出图，不补零、不补假值）。
#    这道必须排在算占比**之前** —— 事后再判，numpy 已经先写出 inf/NaN 了。
if not (_rm_sum > 0).all():
    raise SystemExit(f'Exhibit {EX_REVMIX}：六品种隐含收入合计有非正的月份，占比没有定义。')
# ── 护栏③：各段非负（堆叠柱画不出负段；负值还会让 axisfmt 给这张图写 yfloor）。
_rm_neg = [nm for (_, nm, _, k, _, _) in CLS_REV if (_rm_leg[k] < 0).any()]
if _rm_neg:
    raise SystemExit(f'Exhibit {EX_REVMIX}：{_rm_neg} 有负的隐含收入，堆叠柱画不出负段。')

_rm_share = {k: _rm_leg[k] / _rm_sum * 100.0 for _, _, _, k, _, _ in CLS_REV}
# ── 护栏④：六段之和逐格 == 100。自归一之后本该恒成立 —— 这道防的是「有人改了分母」，
#    而它是本页**唯一**一道分母护栏（build/single.py 那套 spec 驱动的 mix 护栏不管手写
#    生成器，真有人拿 EX_REV 当分母，页面上只会静静地少掉几个百分点）。
_RM_SUM_TOL = 1e-4
_rm_off = float(np.max(np.abs(sum(_rm_share.values()) - 100.0)))
if _rm_off > _RM_SUM_TOL:
    raise SystemExit(f'Exhibit {EX_REVMIX} 各月占比合计偏离 100 达 {_rm_off:.2e}pp '
                     f'（容差 {_RM_SUM_TOL:g}pp）—— 分母已经不是六段之和了。')
# ── 护栏⑤：量侧闭合。图注声称「差全在费率一侧」，这句话只有量侧真的闭合时才成立；
#    某个品种列被换掉或漏掉时，这道比⑥先响、也更能指向病灶。
_RM_VOL_TOL = 0.10                       # %，实测最大 0.015%
_rm_vol_gap = float(np.max(np.abs(sum(win(c, WIN_LINE) for c, _, _, _, _, _ in CLS_REV)
                                  - win('adv_total_kcontracts', WIN_LINE))
                           / win('adv_total_kcontracts', WIN_LINE) * 100))
if _rm_vol_gap > _RM_VOL_TOL:
    raise SystemExit(f'Exhibit {EX_REVMIX} 的图注声称「量侧闭合、差全在费率一侧」，但 '
                     f'Σ{len(CLS_REV)} 品种 ADV 与披露的 Total ADV 最大差 {_rm_vol_gap:.4f}%'
                     f'（容差 {_RM_VOL_TOL}%）—— 先改句子，别改容差。')
# ── 护栏⑥：与 Exhibit EX_REV 的相对差。这道防的是**单位或 metric 映射错**（少乘一个
#    1000、把农产品的量乘上金属的费率），不是防结构差 —— 所以阈值放到 15%：窗口内实测
#    上限 6.0%，即使窗口哪天放宽到费率起点最坏也只有 10.8%，而典型的映射/单位错是几十倍。
#    收到 7% 会在下一次结构大位移时误停机，而结构位移正是这张图要画的东西。
_RM_RESID_MAX = 15.0
_rm_rel = _rm_sum / win('implied_txn_rev_usdmn', WIN_LINE) * 100.0 - 100.0
if float(np.max(np.abs(_rm_rel))) > _RM_RESID_MAX:
    raise SystemExit(f'Exhibit {EX_REVMIX}：{len(CLS_REV)} 品种隐含收入之和与 '
                     f'Exhibit {EX_REV} 的相对差最大 {np.max(np.abs(_rm_rel)):.2f}%'
                     f'（上限 {_RM_RESID_MAX}%）—— 这个量级不是品种结构差，'
                     f'多半是 RPC 的 metric 映射或单位错了。')

_RM_LO, _RM_HI = float(np.min(_rm_rel)), float(np.max(_rm_rel))
_RM_LO_AT, _RM_HI_AT = XL25[int(np.argmin(_rm_rel))], XL25[int(np.argmax(_rm_rel))]
_RM_POS = int((_rm_rel > 0).sum())
_RM_NEG = int((_rm_rel < 0).sum())
# 「残差会变号」这句话本身要由数据说了算：两侧都非空才说得出口，同号时换一句话。
_RM_SIGN_TXT = (f'{_RM_POS} 个月为正、{_RM_NEG} 个月为负（<b>会变号</b>）'
                if _RM_POS and _RM_NEG else
                f'窗口内逐月同号（全为{"正" if _RM_POS else "负"}，但随时可能翻号）')
#: 各品种最新占比与窗口区间。单月首末差不印 —— 占比逐月抖动本身就有几个 pp，
#: 拿两个单月读数相减当「十年结构位移」，换成两端各取 12 个月均值就有品种直接反号。
#: 所以这里给的是「最新 + 窗口区间 + 两端各 12 个月均值的差」三样。
_RM_ROLL = 12
_rm_rows = []
for _, nm, _, k, _, zh in CLS_REV:
    _sh = _rm_share[k]
    _d12 = float(np.mean(_sh[-_RM_ROLL:]) - np.mean(_sh[:_RM_ROLL]))
    _rm_rows.append((zh, float(_sh[-1]), float(np.min(_sh)), float(np.max(_sh)), _d12))
_RM_RNG = '、'.join(f'{zh} {last:.1f}%（窗口内 {lo:.1f}–{hi:.1f}%，两端各取 {_RM_ROLL} '
                   f'个月均值差 {pp(d12)}）' for zh, last, lo, hi, d12 in _rm_rows)
_RM_ABS = '、'.join(f'{zh} ${_rm_leg[k][-1]:,.0f}mn'
                    for _, _, _, k, _, zh in CLS_REV)
#: 量占比 − 收入占比。只把**窗口内逐月不翻号**的那几个品种当结构事实讲；会翻号的
#: 点名说明它会翻，不拿它举证（本仓 schw / cost 都踩过「本月碰巧成立」的坑）。
_rm_vol_sh = {k: win(c, WIN_LINE) / win('adv_total_kcontracts', WIN_LINE) * 100.0
              for c, _, _, k, _, _ in CLS_REV}
_rm_gap = {k: _rm_vol_sh[k] - _rm_share[k] for _, _, _, k, _, _ in CLS_REV}
_rm_always = [(zh, k) for _, _, _, k, _, zh in CLS_REV
              if (_rm_gap[k] > 0).all() or (_rm_gap[k] < 0).all()]
_rm_flips = [zh for _, _, _, k, _, zh in CLS_REV
             if not ((_rm_gap[k] > 0).all() or (_rm_gap[k] < 0).all())]
_RM_ALWAYS_TXT = '、'.join(
    f'{zh}的量占比<b>{"每一格都高于" if (_rm_gap[k] > 0).all() else "每一格都低于"}</b>'
    f'收入占比（{np.min(np.abs(_rm_gap[k])):.2f}–{np.max(np.abs(_rm_gap[k])):.2f}pp，'
    f'{mlab(LATEST)} 为 {abs(_rm_gap[k][-1]):.2f}pp）' for zh, k in _rm_always)
#: 季初那一次「费率改写」单独能把占比推多远：把当月成交量固定住，只把该月的费率
#: 由上一季换成本季，占比会平移多少。季内的位移全部来自成交量，季初那一格不是。
_rm_qshift = []
for _i in range(1, WIN_LINE):
    if W25[_i].asfreq('Q') == W25[_i - 1].asfreq('Q'):
        continue
    _prev_q = W25[_i - 1].asfreq('Q')
    _alt = np.array([float(df[c].iloc[_I0 + _i]) * float(RPC[k].get(_prev_q, np.nan))
                     for c, _, _, k, _, _ in CLS_REV])
    if np.isnan(_alt).any() or _alt.sum() <= 0:
        continue
    _alt = _alt / _alt.sum() * 100.0
    _act = np.array([_rm_share[k][_i] for _, _, _, k, _, _ in CLS_REV])
    _rm_qshift.append((float(np.max(np.abs(_act - _alt))), XL25[_i],
                       CLS_REV[int(np.argmax(np.abs(_act - _alt)))][5]))
_RM_QS_MED = float(np.median([t[0] for t in _rm_qshift])) if _rm_qshift else 0.0
_RM_QS_MAX, _RM_QS_AT, _RM_QS_WHO = (max(_rm_qshift) if _rm_qshift else (0.0, '', ''))
#: 六条品种费率各自的最新可得季度未必与 rpc_total 同步；本图的外推月要按**六条里最早的
#: 那一季**算，拿 CARRY（rpc_total 的口径）会低报外推范围。
_RM_LASTQ = min(RPC[k].index[-1] for _, _, _, k, _, _ in CLS_REV)
_RM_CARRY = [p for p in W25 if p.asfreq('Q') > _RM_LASTQ]
#: 六条品种费率的末季与 rpc_total 的末季是不是同一季 —— 印给读者的那句必须现算：
#: 两者当前相同，写死成「不是 rpc_total 的季度」就是一句当期为假的话。
_RM_VS_TOT = ('相同' if _RM_LASTQ == RPC_Q else
              f'不同 —— rpc_total 最新到 {qlab(RPC_Q)}，本图因此比 Exhibit {EX_REV} '
              f'多外推了几个月')
_RM_CARRY_TXT = ('' if not _RM_CARRY else
                 f'{mlab(_RM_CARRY[0])} 这 1 个月' if len(_RM_CARRY) == 1 else
                 f'{mlab(_RM_CARRY[0])}–{mlab(_RM_CARRY[-1])} 这 {len(_RM_CARRY)} 个月')

ex.append({
    'n': EX_REVMIX, 'kind': 'stacked_dual',
    # fmt 必须显式给 'pct1'：不给会退回 f0c，卡片的「表格」视图把六个占比截成整数，
    # 相加印成 99 或 101，当场证伪「六段之和 = 100%」。
    'fmt': 'pct1', 'xlabels': XL25,
    'title': 'Implied revenue mix across the six complexes',
    # 轴标题里点明分母 —— 下面整段图注都在说「这个 100% 不是 Exhibit EX_REV 那条线」，
    # 轴上再写一个含混的「% of implied revenue」等于自己拆自己的台。
    'ylab': '% of six-complex implied revenue',
    # 不给 line、也不给 ylab2：六段之和恒为 100，段高本身已经把每一块读出来了，
    # 再拿其中一段换一根刻度画一遍是同一个数说两遍。
    'stacks': [{'name': nm, 'color': cl, 'values': L(_rm_share[k])}
               for _, nm, cl, k, _, _ in CLS_REV],
    'src_extra': ('Each complex: contracts traded x that complex quarterly rate per contract. '
                  'Shares are of the six-complex sum and add to 100% by construction; that sum '
                  'differs from contracts x blended RPC (the implied revenue exhibit above) '
                  "because CME's blended rate is derived from total revenue, not volume-weighted "
                  'from the complex rates'),
    'note': (
        f'每一段 = 该品种当月成交张数 × 该品种<b>当季</b> RPC，再除以 {len(CLS_REV)} 段之和。'
        f'<b>六段之和是 100%，因为分母就是这六段之和（自归一）</b> —— 不是因为「品种划分'
        f'穷尽互斥」：划分确实穷尽互斥，但那只保证<b>量</b>侧闭合，与本图的 100% 无关。'
        # ② 与 EX_REV 的差距，全部现算
        f' <b>本图的 100% 不是 Exhibit {EX_REV} 那条线。</b>那张画的是「当月总张数 × CME '
        f'披露的混合 rpc_total」，本图的分母是 {len(CLS_REV)} 条腿之和 —— 两者<b>逐月不等</b>：'
        f'{WIN_LINE} 个月里相对差从 {pct(_RM_LO)}（{_RM_LO_AT}）到 {pct(_RM_HI)}'
        f'（{_RM_HI_AT}），{_RM_SIGN_TXT}，{mlab(LATEST)} 是 {pct(float(_rm_rel[-1]))}'
        f'（六腿 ${_rm_sum[-1]:,.0f}mn vs 那张的 '
        f'${float(df["implied_txn_rev_usdmn"][CUR]):,.0f}mn）。'
        f'差<b>不在量侧</b>：{len(CLS_REV)} 个品种的 ADV 相加与披露的 Total ADV 最大只差 '
        f'{_rm_vol_gap:.4f}%（残差的量级与解释见 Exhibit {EX_MIX} 的图注）；'
        f'差在<b>费率侧</b> —— CME 披露的 rpc_total 是它从总收入倒算的混合费率，'
        f'与「{len(CLS_REV)} 条品种 RPC 按各自成交量加权」不是同一个数。'
        f'本页不做配平，也不把差额画成第七段（残差会变号，堆叠柱画不出负段）。'
        f'<b>所以不要拿本图的占比去乘 Exhibit {EX_REV} 的总额</b>还原某个品种的收入；'
        f'乘本图自己的分母是恒等的 —— {mlab(LATEST)} 六腿合计 ${_rm_sum[-1]:,.0f}mn'
        f'（窗口内 ${np.min(_rm_sum):,.0f}–${np.max(_rm_sum):,.0f}mn），'
        f'逐段的绝对值是：{_RM_ABS}（逐段各自取整，相加与上面那个合计可能差 $1mn，'
        f'差的是取整残差不是口径）。绝对量的走势请看 Exhibit {EX_REV}'
        f'（纵轴 {_ylab_of(EX_REV)}），本图只读结构。'
        # ③ 与量的结构对读 —— 这张图存在的理由，只用窗口内不翻号的事实举证
        f' <b>钱的结构与量的结构是两回事</b>，这正是本图存在的理由：各品种 RPC 相差 '
        f'{RPC_SPREAD_X:.2f} 倍（{qlab(RPC_Q)} 实测，{len(CLS_REV)} 条全部画在 '
        f'Exhibit {EX_RPC}）。拿量占比减去收入占比，{WIN_LINE} 格里<b>一格都不翻号</b>的是：'
        f'{_RM_ALWAYS_TXT}'
        + (f'；{"、".join(_rm_flips)}会翻号，不能拿它们当结构证据。' if _rm_flips else '。')
        + f'（注意 Exhibit {EX_MIX} 画的是各品种 ADV 的<b>绝对水平</b>堆叠，柱高之和是 '
        f'Total ADV，右轴那条线是利率 + 股指合计的<b>量</b>占比；'
        f'利率单独一条的量占比另有一整张图 —— Exhibit {EX_HEAT_SHARE} 的年 × 月热力矩阵，'
        f'读者可以拿它减本图利率那一段，减出来就是上面那个 pp 差。'
        f'其余四个品种的量占比页面上不单画，由本图注现算。）'
        # ④ 窗口、区间与读法
        f' {XL25[0]} 至 {XL25[-1]}（{WIN_LINE} 个月）各段最新值与窗口区间：{_RM_RNG}。'
        f'首末两个<b>单月</b>读数相减不构成趋势判断（占比逐月抖动本身就有几个 pp），'
        f'所以上面给的是两端各取 {_RM_ROLL} 个月均值的差。'
        f'<b>本图不给右轴线</b>：{len(CLS_REV)} 段之和恒为 100，段高本身已经把每一块'
        f'读出来了。逐月读数请走卡片右上角的「表格」。'
        # ⑤ 季度费率造成的季初台阶 + 外推月
        + (f' <b>费率一季才动一次</b>：季内每一次占比位移都只来自成交量结构；'
           f'而每季第一个月的位移里另含一次<b>费率改写</b> —— 把当月成交量固定住、'
           f'只把费率由上一季换成本季，占比就会平移，实测这一项单独造成的季初平移'
           f'中位 {_RM_QS_MED:.2f}pp、最大 {_RM_QS_MAX:.2f}pp'
           f'（{_RM_QS_AT} 的{_RM_QS_WHO}）。两种位移在图上长得一模一样。'
           if _rm_qshift else '')
        + (f' <b>{_RM_CARRY_TXT}</b>的 {len(CLS_REV)} 条费率全部沿用 {qlab(_RM_LASTQ)}'
           f'（这是 {len(CLS_REV)} 条品种费率里最早的那一季；它与 rpc_total 的最新季'
           f'{_RM_VS_TOT}），'
           f'所以这几根柱的结构位移<b>只来自成交量</b>、不含任何费率变动；'
           f'费率补齐后这几个月的占比会被改写。' if _RM_CARRY else '')
        + RATE_PERIOD + RATE_STALE),
})
# ══════════ Exhibit EX_DECOMP：收入增长的量／费率分解（**不是成交额的量价分解**）══════════
# 恒等式：收入 ≡ 成交合约数 × 每张平均费率。CME 不披露成交**金额**（期货的名义本金要靠
# 合约乘数逐品种推，本仓 series/contract_specs.csv 只覆盖一部分品种），所以「成交额 =
# 成交量 × 均价」那种分解在这一页做不到，做出来也是拿口径不全的名义本金去凑分母。
# 能做的是**收入**的量价分解：张数是量、RPC 是价。两者性质不同，标题和图注都必须写死这一点。
#
# 横轴改过两回，两回都是所有者指令：2026-08 由「近 13 个月的 TTM 滚动端点」改成
# 「4 个完整日历年 + 1 根当年 YTD」；**2026-09 再改成「一格 = 一个月」**（原话：
# 「ex20 做成月度的 revenue split」）。方法与护栏照旧，只有桶换了粒度 —— 因此本页这张
# 与 build/single.py 的 ex_decomp **不再同口径**（那边仍是年度桶），别再写「跨页可比」。
# 口径纪律：
# （1）**桶**：一格 = 一个月，本期 = 该月、基期 = **去年同月**，也就是单月同比 ——
#      与本页所有月度图、汇总表 y/y 列同一种口径（CONTRACT §6：全站只有这一种）。
#      不用环比：RPC 是季度值铺月，环比下费率腿在每季的第 2、3 个月严格为 0，
#      一年 12 格里有 8 格是「纯量」，那不是分解图。
#      年度版那两条「YTD 基期要逐月对齐」「YTD 柱不能与完整年柱比大小」随之作废：
#      每一格覆盖的月数都是 1，格与格本来就可比。
# （2）单月桶里 **P = 当月收入 ÷ 当月张数 ≡ 该月挂靠的那一季 RPC**（收入本来就是
#      张数 × 该季费率算出来的，比值把张数约掉），两侧都不做任何平均 —— 年度版那段
#      「Σ收入 ÷ Σ张数，不是逐月 RPC 的简单平均」在这里解释的是一个不存在的陷阱，已删。
# （3）**图上画对数分解按总增长重标定后的两块**：w = g_V ÷ ln(V₁/V₀)，
#      贡献_量 = w·ln(Q₁/Q₀)、贡献_价 = w·ln(P₁/P₀)，两块相加逐格 = 算术总增长 g_V，
#      纵轴回到 %，读者不必在「对数点」与「百分比」之间换算。对数分解天然可加、无交叉项；
#      算术分解 g_V = g_Q + g_P + g_Q·g_P 的交叉项必须整段压给某一腿，压给谁都会改读数
#      —— 算术版照算，只进图注。
# （4）w 在 V₁ ≈ V₀ 时解析上 → 1、数值上是 0/0（两个小量都由大数相减得来，有效位被吃光），
#      所以 |ln(V₁/V₀)| < DEC_LN_MIN 的那一格**整格留空**，不印一个算不准的数。
#      （月度桶下实测一格都没命中，最接近的一格是阈值的上千倍 —— 但规则要留着，
#       它防的是极端巧合，「这轮没命中」不是删兜底的理由。）
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


# 桶 = 图窗 W25 的每一个月，基期 = 该月 − 12。横轴用与本页其余月度图同一条 XL25，
# 读者能逐格上下对读同一个月（下面 _dxl != XL25 现验这句话）。
# CME 的费率 2013-Q2 才有（此前隐含收入为 NaN），而图窗自 WIN_FROM 起 —— 左端那一格的
# 基期落在 2015 年，早就有值，所以本轮 128 格两侧全齐。两侧不齐的格走留空分支，
# 那是给「窗口再往左放宽」或「数据缺月」准备的，不是死代码。
_dec_bars = [(mlab(p), [p], [p - 12]) for p in W25]
if not _dec_bars:
    raise SystemExit(f'Exhibit {EX_DECOMP}：图窗 W25 是空的，一格都画不出来')

_dxl, _dq, _dp, _dnet, _drows, _dblanks, _dgaps = [], [], [], [], [], [], []
for _lab, _m1, _m0 in _dec_bars:
    _b1, _b0 = _dec_bucket(_m1), _dec_bucket(_m0)
    if _b1 is None or _b0 is None:
        # 两侧任一腿缺值：净额与两段必须**同空**（护栏④核对），否则菱形没了柱子还在。
        _dxl.append(_lab)
        _dgaps.append(_lab)
        _dq.append(np.nan)
        _dp.append(np.nan)
        _dnet.append(np.nan)
        continue
    _V1, _Q1 = _b1
    _V0, _Q0 = _b0
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
    row = {'lab': _lab, 'per': _m1[0], 'V1': _V1, 'Q1': _Q1, 'P1': _P1,
           'V0': _V0, 'Q0': _Q0, 'P0': _P0,
           'gV': _gV, 'gQ': _gQ, 'gP': _gP, 'cross': _crs, 'lV': _lV,
           'w': np.nan, 'cq': np.nan, 'cp': np.nan}
    if abs(_lV) < DEC_LN_MIN:
        # 整格留空：w = g_V/ln(V₁/V₀) 此时是 0/0，算出来的两块没有有效位。
        _dblanks.append(_lab)
        _dq.append(np.nan)
        _dp.append(np.nan)
        _dnet.append(np.nan)
    else:
        _w = _gV / _lV
        row['w'] = _w
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
    raise SystemExit(f'Exhibit {EX_DECOMP}：{len(_dxl)} 格全部留空（两侧不齐或落在 '
                     f'|ln(V₁/V₀)| < {DEC_LN_MIN:.0e} 的区间），没有一格画得出来')
# 横轴必须与本页其余月度图逐格对齐 —— 图注声称「可以逐格上下对读同一个月」，
# 兜底① 只查左端，这一条查全长。
if _dxl != XL25:
    raise SystemExit(f'Exhibit {EX_DECOMP} 的横轴与 XL25 对不上（{len(_dxl)} vs '
                     f'{len(XL25)} 格）—— 图注那句「逐格上下对读」就是假话。')

#: 真正**画出来**的那些格。所有印给读者的统计一律在它上面算 —— 留空格的 |gV| ≈ 0，
#: 拿它算「交叉项占净增长」能得到几十万个百分点，而那一格图上根本没有柱。
#: 年度桶只有 5 根柱、永远撞不上；月度 128 格把这个分支从「理论上」变成「随时可能」。
_fin_rows = [r for r in _drows if np.isfinite(r['cq'])]
# 「算术分解里交叉项有多大」正是不用算术分解的理由。**印 pp 而不是只印占比**：
# 占比的分母是净增长，净增长近零的格子会把占比顶到几十上百，读者会以为交叉项本身巨大。
# 所以三样一起给：绝对值（pp）、只在净增长不近零时才有意义的占比、以及近零格数。
_x_pp = [abs(r['cross']) * 100 for r in _fin_rows]
if not _x_pp:
    raise SystemExit(f'Exhibit {EX_DECOMP}：没有一格算得出交叉项')
_CROSS_PP_MED, _CROSS_PP_MAX = float(np.median(_x_pp)), float(max(_x_pp))
_CROSS_PP_AT = max(_fin_rows, key=lambda r: abs(r['cross']))['lab']
_NEAR0 = [r for r in _fin_rows if abs(r['gV']) < 0.05]      # |净增长| < 5%
_x_far = [r for r in _fin_rows if abs(r['gV']) >= 0.05]
if not _x_far:
    raise SystemExit(f'Exhibit {EX_DECOMP}：没有一格的净增长绝对值达到 5%，'
                     f'「交叉项占净增长」这个比例在本窗口没有可靠的分母')
_CROSS_SH_FAR = float(max(abs(r['cross'] / r['gV']) * 100 for r in _x_far))
_CROSS_MED = float(np.median([abs(r['cross'] / r['gV']) * 100 for r in _fin_rows
                              if r['gV'] != 0]))
#: 两腿反号（量涨费率跌，或反之）的格数 —— 分母是**画得出来的格数**，不是 WIN_LINE。
_OPP_N = sum(1 for r in _fin_rows if r['cq'] * r['cp'] < 0)
#: 重标定权重 w 的实测区间。图上的金色段 = w·ln(P₁/P₀)，w 逐月不同 ——
#: 所以「费率同比季内恒等」这件事**不等于**「金色段季内等高」，两句话必须分开说。
_W_LO, _W_HI = float(min(r['w'] for r in _fin_rows)), float(max(r['w'] for r in _fin_rows))
#: 原始费率同比 gP 的常数区间段数（每季一段），以及**画出来的**金色段同季极差。
_gp_runs, _prev_gp = 0, None
for r in _fin_rows:
    if _prev_gp is None or abs(r['gP'] - _prev_gp) > 1e-12:
        _gp_runs += 1
    _prev_gp = r['gP']
_GP_RUNS = _gp_runs
_cp_by_q = {}
for r in _fin_rows:
    _cp_by_q.setdefault(r['per'].asfreq('Q'), []).append(r['cp'])
_cp_spread = {q: max(v) - min(v) for q, v in _cp_by_q.items() if len(v) > 1}
_CP_QSPREAD_MAX = float(max(_cp_spread.values())) if _cp_spread else 0.0
_CP_QSPREAD_AT = qlab(max(_cp_spread, key=_cp_spread.get)) if _cp_spread else ''
_CP_QSPREAD_MED = float(np.median(list(_cp_spread.values()))) if _cp_spread else 0.0
#: 金色段有多薄 —— 「逐格读数请走表格」那句话的真正理由。
_CP_ABS_MED = float(np.median([abs(r['cp']) for r in _fin_rows]))
_CP_THIN_N = sum(1 for r in _fin_rows if abs(r['cp']) < 1.0)
#: 有多少格的金色段矮于净额菱形（assets/charts.js 里半径写死 3.2px ⇒ 6.4px 见方，
#: 不随格宽缩）。128 格通栏后柱宽只有 6.0px 出头，菱形比柱还宽，画在净额那个高度上
#: 就会盖掉一截金色 —— 这件事图注要跟读者说清楚，不能让人以为那一格费率贡献是零。
#: 量程用 payload 自己的（引擎对 bridge_bar 的 y 量程就是「包络 ± 16% 极差」），
#: 绘图区高取通栏实测的 262.2px；两个常数都只影响这一个计数，不进任何数值。
_DIA_PX, _PLOT_PX = 6.4, 262.2
_env = [sum(v for v in (r['cq'], r['cp']) if v > 0) for r in _fin_rows] + \
       [sum(v for v in (r['cq'], r['cp']) if v < 0) for r in _fin_rows] + \
       [r['gV'] * 100 for r in _fin_rows]
_e_lo, _e_hi = min(_env), max(_env)
_PP_PER_PX = ((_e_hi - _e_lo) * 1.32) / _PLOT_PX
_CP_UNDER_DIA = sum(1 for r in _fin_rows if abs(r['cp']) < _DIA_PX * _PP_PER_PX)
#: 最接近留空线的一格（这一项要在 _drows 上算 —— 它问的正是「有没有格快要留空了」）。
_lv_row = min((r for r in _drows if np.isfinite(r['lV'])), key=lambda r: abs(r['lV']))
_LV_MIN, _LV_MIN_AT = abs(float(_lv_row['lV'])), _lv_row['lab']
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

# 末格必须是**画得出来**的那一格，否则下面图注里「{_last['lab']} 的算术读数」会挂在
# 一个与横轴末端不同的月份上 —— 缺值格走 continue、不进 _drows，留空格却会进，
# 所以 _drows[-1] 与 _dxl[-1] 不是天然对齐的（年度桶没有这个洞，每根柱都进 _drows）。
_last = _drows[-1]
if _last['lab'] != _dxl[-1] or not np.isfinite(_last['cq']):
    raise SystemExit(
        f'Exhibit {EX_DECOMP}：图注与 DECOMP_CHECK 都印「末格 {{_last["lab"]}} 的读数」，'
        f'但末格必须是**画得出来**的那一格 —— 横轴末格是 {_dxl[-1]}、_drows 末条是 '
        f'{_last["lab"]}、它的量腿是 {_last["cq"]}。'
        f'（缺值格走 continue 不进 _drows，留空格却会进且 cq 是 NaN，所以只比标签挡不住。）')

DECOMP_CHECK = (
    f'Exhibit {EX_DECOMP} 量价分解（月度桶，当月 vs 去年同月）：{len(_dxl)} 格 '
    f'{_dxl[0]} – {_dxl[-1]}，画得出 {len(_fin_rows)} 格；'
    f'末格 {_last["lab"]} 收入 ${_last["V1"]:,.1f}mn vs ${_last["V0"]:,.1f}mn、'
    f'张数 {_last["Q1"]:,.1f}mn vs {_last["Q0"]:,.1f}mn、'
    f'RPC ${_last["P1"]:.4f} vs ${_last["P0"]:.4f} → 量 {_last["cq"]:+.2f}pp + '
    f'费率 {_last["cp"]:+.2f}pp = 净 {_last["gV"] * 100:+.2f}%；'
    f'净额区间 {min(r["gV"] for r in _fin_rows) * 100:+.1f}% – '
    f'{max(r["gV"] for r in _fin_rows) * 100:+.1f}%；两腿反号 {_OPP_N} 格；'
    f'原始费率同比 gP {_GP_RUNS} 段常数区间，画出来的金色段同季最大落差 '
    f'{_CP_QSPREAD_MAX:.2f}pp；交叉项 |中位| {_CROSS_PP_MED:.2f}pp / |最大| '
    f'{_CROSS_PP_MAX:.2f}pp（{_CROSS_PP_AT}）；最小 |ln(V1/V0)| = {_LV_MIN:.6f}'
    f'（{_LV_MIN_AT}，阈值 {DEC_LN_MIN:.0e} 的 {_LV_MIN / DEC_LN_MIN:.0f} 倍）；'
    f'三道闭合残差 ≤ {DEC_EPS:.0e} 全过'
    + (f'；留空格 {"、".join(_dblanks)}' if _dblanks else '')
    + (f'；两侧不齐 {"、".join(_dgaps)}' if _dgaps else ''))

ex.append({
    'n': EX_DECOMP, 'kind': 'bridge_bar', 'fmt': 'pct1', 'yfmt': 'pct0',
    # **不要写 'xrot': 0**（月度化之前是写着的）：build/mrwin.py 对 xrot == 0 的
    # exhibit 整张 continue，既不判通栏也不抽标签 —— 128 格塞进半栏每格不到 4px，
    # 128 个横排 'Jan-16' 会叠成一堵字墙，而引擎、verify_pages、visual_qa 全都不报错。
    # full / height / xstep 同理一律不手写，交给 mrwin.layout_all()（它还会把实测 px
    # 追加进 note，回填②那道闸门核对这件事）。
    'xlabels': _dxl,
    # 标题必须含 ASCII 'single-month'：_ZH_SINGLE 那道闸门会对「只写中文单月、
    # 没写 single」的图停机；写上之后本图自动归进页尾口径条（a）那一档。
    'title': 'Implied revenue growth split by month, single-month y/y: '
             'contracts vs. rate per contract (a revenue split, NOT a turnover split)',
    'ylab': '% y/y, single month',
    'stacks': [
        {'name': 'Contracts traded', 'color': 'NAVY', 'values': L(_dq)},
        {'name': 'Rate per contract (RPC)', 'color': 'GOLD', 'values': L(_dp)},
    ],
    'net': {'name': 'Implied revenue growth', 'values': L(_dnet)},
    'net_color': 'INK',
    'src_extra': ('Identity: revenue = contracts x rate per contract; log-weight decomposition, '
                  'one bar = one month vs. the same month a year ago (single-month y/y). '
                  'CME discloses RPC quarterly, so the three months of a quarter share one rate. '
                  'This decomposes REVENUE, not notional turnover — CME does not publish '
                  'traded notional value'),
    'note': (f'<b>这是收入的量价分解，不是成交额的量价分解。</b>恒等式是「隐含交易收入 = '
             f'成交合约数 × 每张平均费率(RPC)」；CME 不披露成交<b>金额</b>，所以'
             f'「成交额 = 成交量 × 均价」那种分解在本页<b>不具备数据条件</b>，本图也没有假装做到。'
             f'两者不可混为一谈，也不要和别的页上真正的量价分解并读：这里的「价」是 CME 向客户'
             f'收的<b>每张费率</b>，不是标的资产的成交价格。'
             # ── 横轴：2026-09 由日历年改成月（所有者指令）
             f' <b>横轴一格 = 一个月</b>：本期是该月，基期是<b>去年同月</b>'
             f'（当月 ÷ 去年同月 − 1，就是单月同比），共 {len(_dxl)} 格'
             f'（{_dxl[0]} – {_dxl[-1]}），左端与本页其余月度图同为 {WIN_FROM}，'
             f'<b>可以逐格上下对读同一个月</b>（构建期核对横轴逐格相同）。'
             f'每一格覆盖的月数都是 1，所以格与格之间可以直接比大小 —— '
             f'这与本页 2026-09 之前那版按日历年分桶、末柱是当年 YTD 的分解图不同，'
             f'那版的末柱与完整年柱覆盖月数不同、本来就不可比。'
             # ── 与 EX_REV 的关系（构建期逐点现验）
             f' <b>菱形（净额）与 Exhibit {EX_REV} 次轴的金色折线是同一条数</b>，'
             f'逐点相同（构建期逐点现验，对不上就不出图）：那张画的是隐含收入的水平值'
             f'与它的单月同比，本图把同一条同比拆成量与费率两块。'
             f'换口径的代价（§6.1 第 3 条）就印在 Exhibit {EX_REV} 自己的图注里、'
             f'用的正是这条序列自己的实测，本图不重复印一遍。'
             # ── 单月桶里没有平均
             f' <b>单月桶里没有任何平均</b>：P = 当月收入 ÷ 当月张数 ≡ 该月<b>挂靠</b>的'
             f'那一季 RPC（收入本来就是张数 × 该季费率算出来的，比值把张数约掉），'
             f'所以两侧都不存在「逐月 RPC 该怎么加权」的问题。'
             f'张数腿 = 当月 ADV × 当月交易日数（与汇总表同口径）。'
             # ── 费率腿的季度台阶：原始 gP 与画出来的 cp 必须分开说
             f' <b>费率一季才披露一次</b>，当季各月共用该季数值 —— 所以<b>算术读数</b>里的'
             f'费率同比在同一个季度内三个月完全相同，{len(_fin_rows)} 格里只有 '
             f'{_GP_RUNS} 段常数区间（每季一段）。但<b>图上那段金色不是它</b>：'
             f'画出来的是 w·ln(P₁/P₀)，重标定权重 w 逐月不同'
             f'（窗口内实测 {_W_LO:.2f}–{_W_HI:.2f}），所以<b>金色段同季并不等高</b>，'
             f'实测同季最大落差 {_CP_QSPREAD_MAX:.2f}pp（{_CP_QSPREAD_AT}）、'
             f'中位 {_CP_QSPREAD_MED:.2f}pp。别按「三格一台阶」去数。'
             # ── 算法
             f' <b>图上画的是对数分解按总增长重标定后的两块</b>：ln(V₁/V₀) = ln(Q₁/Q₀) + '
             f'ln(P₁/P₀) 天然可加、无交叉项；再乘 w = g<sub>收入</sub> ÷ ln(V₁/V₀) 换算回'
             f'百分点，深蓝 + 金色<b>逐格等于</b>菱形标的总增长（三道闭合检查残差上限 '
             f'{DEC_EPS:.0e}，超了本页直接不出图）。w 对量与价一视同仁，不含分配假设。'
             # ── 算术分解：印 pp，不要只印占比
             f' <b>算术分解只进图注</b>：g<sub>收入</sub> = g<sub>张数</sub> + g<sub>费率</sub>'
             f' + 交叉项，而交叉项必须整段压给某一腿，压给谁都会改读数 —— '
             f'{len(_fin_rows)} 格里有 {_OPP_N} 格（{_OPP_N / len(_fin_rows) * 100:.0f}%，'
             f'分母是画得出来的格数）量与费率<b>方向相反</b>。'
             f'实测交叉项<b>绝对值</b>中位 {_CROSS_PP_MED:.2f}pp、最大 {_CROSS_PP_MAX:.2f}pp'
             f'（{_CROSS_PP_AT}）；「占净增长百分之多少」只在净增长本身不近零时才有意义 ——'
             f'净增长绝对值 ≥ 5% 的 {len(_x_far)} 格里最大 {_CROSS_SH_FAR:.0f}%'
             f'（另有 {len(_NEAR0)} 格净增长不足 5%，那里的占比读的是分母不是交叉项）。'
             f'{_last["lab"]} 的算术读数：张数 {pct(_last["gQ"] * 100)}、'
             f'费率 {pct(_last["gP"] * 100)}、交叉项 {pp(_last["cross"] * 100)}，'
             f'合计 {pct(_last["gV"] * 100)}。'
             # ── 深蓝段 vs Exhibit 3 的灰线：页面上第三处「几乎同一条数」
             f' <b>深蓝段与 Exhibit {EX_DAYCOUNT} 的灰线读的是同一条总量单月同比</b>，'
             f'但深蓝段乘过重标定权重 w，两者最大差 {_log_gap:.1f}pp（{_log_gap_at}）—— '
             f'逐格对读时以本图为准（构建期现验这个差就是 w 造成的那一个）。'
             + (f' <b>留空的格</b>：{"、".join(_dblanks)} 的 |ln(V₁/V₀)| < {DEC_LN_MIN:.0e}'
                f'（两期几乎持平），重标定权重 w 是 0/0、算出来没有有效位，'
                f'整格留空而不是印一个假的分解。' if _dblanks else
                f' <b>本轮没有任何一格落进留空区间</b>（判据 |ln(V₁/V₀)| < {DEC_LN_MIN:.0e}，'
                f'两期几乎持平时 w = 0/0）：最接近的一格是 {_LV_MIN_AT}，'
                f'|ln(V₁/V₀)| = {_LV_MIN:.4f}，是阈值的 {_LV_MIN / DEC_LN_MIN:,.0f} 倍。')
             + (f' <b>两侧不齐而留空的格</b>：{"、".join(_dgaps)}。' if _dgaps else '')
             # ── 费率段读的是什么 + 外推月逐格点名
             + f' <b>费率段读的是三重内容</b>：RPC 由 CME 从已披露收入倒算，所以它同时吸收了'
             f'品种结构位移（各品种 RPC 相差 {RPC_SPREAD_X:.2f} 倍，见 Exhibit {EX_RPC}；'
             f'结构本身见 Exhibit {EX_REVMIX}）、定价调整与折扣计划，不是一个纯粹的「价」。'
             + (f'<b>末 {len(CARRY)} 格（{_CARRY_TXT}）的费率腿建在沿用费率上</b>：'
                f'这几个月尚无对应季度的披露费率，本期用的是 {qlab(RPC_Q)} 的值，'
                f'而它们的基期用的是当时已披露的实际费率 —— 费率补齐后这几格的金色段会被'
                f'改写；<b>原始张数同比 g<sub>张数</sub> 不变，但画出来的深蓝段会随 w 一起'
                f'轻微改写</b>（w 里含着被沿用的费率）。' if CARRY else '')
             # ── 读数走表格：理由是金色段本身薄，不是 band 窄
             + f' <b>逐格读数请走卡片右上角的「表格」</b>：{len(_dxl)} 格通栏之后每格只有'
             f'几个像素宽（实测值由本注末尾那句排版说明给出），而金色段常常更薄 —— '
             f'窗口内 |费率腿| 中位 '
             f'{_CP_ABS_MED:.1f}pp，有 {_CP_THIN_N} 格不足 1pp，图上看不出正负。'
             f'<b>净额菱形还会压住它</b>：菱形是固定 6.4px 见方（不随格宽缩），比这里的'
             f'柱还宽一点，画在净额那个高度上，于是金色段矮于 6.4px 的格子会被它盖掉一截 '
             f'—— 本窗口这样的格有 {_CP_UNDER_DIA} 个。要读某一格的量与费率各是多少，'
             f'一律走表格，不要拿眼睛去量柱段。'
             + RATE_PERIOD + RATE_STALE),
})

# 本图是**季度**口径（费率一个季度才披露一次），所以它的左端不是「2016-01 这一个月」
# 而是 2016-01 所在的季度 Q_FROM。原先取末 14 个季度（= 3.5 年，旧常量 WIN_QTR），
# 那是照搬原 deck 的窗口，不是数据下限：series/fee_rates.csv 里 CME 的七条 RPC
# （总 RPC + 六个品种）都是 2013-Q2 起、53 个季度连续无缺，2016-Q1 起的每一季都在。
#
# **2026-09 由四条线扩到六条**：此前只画利率 / 股指 / 能源 / 金属，而标题写的是
# 「by asset class」—— 农产品与外汇两个品种的费率一根线不画、一个读数不印，同一页
# 却有一张图拿这六条费率算收入结构（Exhibit EX_REVMIX）。读者核不到的数不该被引用，
# 所以两条一并画上，颜色一律取 CLS 里该品种自己的色（农产品 GRAY、外汇 GREEN），
# 不新增配色。
# lines_endlabels 属 mrwin.DENSE，窗口内一个 null 都不能有 —— 下面显式校验，
# 六条腿里任何一条在 2016-Q1 之后缺一季就在构建期响，不靠人眼看图。
_rq = RPC['total'].index[RPC['total'].index >= Q_FROM]
#: 图窗（月度）覆盖的季度数 —— 本图的季度数少于它时，少的是「费率尚未披露」的尾季。
_Q_SPAN = (CUR_Q - Q_FROM).n + 1
_rpc_gap = {k: [qlab(q) for q in _rq if q not in RPC[k].index] for k, _, _ in CLS_RPC}
_rpc_gap = {k: v for k, v in _rpc_gap.items() if v}
if _rpc_gap:
    raise SystemExit(f'Exhibit {EX_RPC} 是平滑图型，{Q_FROM} 起不许缺季：{_rpc_gap}')
# 六条品种曲线各自的最新可得季度未必与总 RPC 同步（某一季只补了一部分品种时会脱节），
# 脱节的那条曲线在末端会断开。差异现算，不写死品种名与季度号。
_RPC_ZH = dict({'total': '总 RPC'}, **{k: zh for k, _, zh in CLS_RPC})
_rpc_behind = [(k, RPC[k].index[-1]) for k, _, _ in CLS_RPC if RPC[k].index[-1] != RPC_Q]
_RPC_SYNC = ('' if not _rpc_behind else
             f'注意 {len(CLS_RPC)} 条曲线并未同步：'
             + '、'.join(f'{_RPC_ZH[k]}最新只到 {qlab(q)}' for k, q in _rpc_behind)
             + f'（其余为 {qlab(RPC_Q)}），末端断开处即缺该季披露。')
ex.append({
    'n': EX_RPC, 'kind': 'lines_endlabels', 'fmt': 'usd2',
    'xlabels': [mlab(q.asfreq('M', 'end')) for q in _rq],
    'title': 'Rate per contract by asset class', 'ylab': '$ per contract',
    'series': [{'name': nm, 'color': cl, 'values': L(RPC[k].reindex(_rq).values)}
               for _, nm, cl, k, _, _ in CLS_REV],
    'src_extra': ('RPC differs several-fold across complexes, so a volume mix shift moves blended '
                  'revenue even when total ADV is flat. This is the main uncertainty in the '
                  'implied-revenue bridge and the driver of the revenue mix chart above.'),
    'note': (f'季度值，x 轴标的是各季末月（{mlab(_rq[0].asfreq("M", "end"))} = {qlab(_rq[0])}，'
             f'最新为 {qlab(RPC_Q)}，共 {len(_rq)} 个季度）。本图与本页各月度时序图一样从 '
             f'{WIN_FROM} 起，只是刻度是季度不是月 —— <b>本图是全页唯一的季度刻度图</b>'
             f'（{qlab(_rq[0])} – {qlab(RPC_Q)}；图窗覆盖的季度共 {_Q_SPAN} 个'
             + (f'，本图右端少的那 {_Q_SPAN - len(_rq)} 季是费率尚未披露，不是窗口不同'
                if _Q_SPAN > len(_rq) else '')
             + f'）：费率一季才披露一次，按月铺开只会把同一个数抄三遍。'
             f'<b>{len(CLS_REV)} 个品种全部画在这里</b>（2026-09 之前只画四条，'
             f'农产品与外汇没有出图；同一页的 Exhibit {EX_REVMIX} 用的正是这 '
             f'{len(CLS_REV)} 条费率，读者核得到才算数）。'
             f'{mlab(_rq[-1].asfreq("M", "end"))}：{_RPC_LAST} —— '
             f'最高的{_RPC_HI[2]}是最低的{_RPC_LO[2]}的 {RPC_SPREAD_X:.2f} 倍，'
             f'图上按 $0.01 显示（原 PDF 为 $0.001），第三位小数以此注为准。' + _RPC_SYNC
             # 本图本身只画季度费率、不跨月外推，但它是 EX_REV 那张隐含收入桥的费率来源，
             # 所以同一句期间披露在这里也要出现：读者看到曲线停在哪一季，就知道隐含收入
             # 那张图的最新一两个月是拿哪一季的费率算的。
             + f'本图曲线止于 {qlab(RPC_Q)}，Exhibit {EX_REV} 的隐含收入即以此季费率为准。'
             + RATE_PERIOD + RATE_STALE),
})



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
# 这张矩阵一直画的就是单月同比，标题里也一直写着「single-month」。2026-08 那一轮它是
# 全页的**例外**（其余图是滚动口径），2026-09 全页改成单月之后它反而成了默认的一员 ——
# 标题与图例不动（本来就是对的），但图注里那句「与 12 个月滚动合计同比不是一个口径」
# 必须改掉：现在它与各图次轴同口径，那句话已经是假话。
ex.append(heat(EX_HEAT_YOY, 'adv_yoy', 'Total ADV y/y growth, single month (%)',
               'Green = faster y/y growth, red = slower. Single-month y/y — the same basis '
               'as the gold line on every volume bar chart',
               fmt='pct0z', legend='Total ADV y/y (single month)',
               note=f'<b>本图的每一格是单月同比</b>（该月 ÷ 去年同月 − 1），'
                    f'与各图次轴的金色折线<b>同一个口径</b>（全页统一，见 '
                    f'Exhibit {EX_DAYCOUNT} 图注与页尾口径条），可以直接对读 —— '
                    f'本图的每一格就是 Exhibit {EX_ADV} 次轴金线上的一个点，只是排成了'
                    f'年 × 月的格子，好让同一个月份跨年份上下对齐。'
                    f'热力矩阵本来也只能是单月口径：换成 12 个月滚动值，相邻 12 格几乎会'
                    f'填成同一个数、整张表退化成一片同色。'
                    f'单月同比本身很毛：本图这条序列（总 ADV，与 Exhibit {CAL_EX} 同一条）'
                    f'在 {XL25[0]} – {XL25[-1]} 内的实测是 {CALIB["n"]} 个可比月里有 '
                    f'{CALIB["n_opp"]} 个月与 12 个月滚动口径（本页不画，只作对照）符号相反'
                    f'（相邻月最大跳变 {CALIB["jump_m"]:.0f}pp，出现在 '
                    f'{CALIB["jump_m_at"]}）—— 所以这张表读的是「哪几个月不寻常」，'
                    f'不是「趋势往哪走」；本页不画任何平滑口径的线，趋势要看水平值本身'
                    f'（Exhibit {EX_ADV} 的柱高）。'))
ex.append(heat(EX_HEAT_SHARE, 'rates_share', 'Interest-rate share of total ADV (%)',
               'Rates is the largest and most rate-cycle-sensitive complex',
               legend='Rates share of ADV'))



# ══════════ 4.9 跨图断言：构建期兜底 + 图注回填（所有 exhibit 都画完之后）══════════
# 这一节管一类句子：**外延比作者脑子里那几张图宽的断言**（「各 gs_bar…」「其余时序图
# 一律…」「全页唯一…」）。它们写下来的时候多半是真的，加一张图 / 漏改一张图之后不会自己
# 跟着变，而读者往下滚三张图就当场抓到页面自相矛盾。本页在同一个坑里栽过三次，全部留档：
#   ① 2026-08-19：全历史线那张（**当时**的 Exhibit 7）图注写「其余时序图的左端一律是
#      2016-01」，而季度合计柱（当时的 Exhibit 8）还停在末 14 个季度（2023Q2 起）。
#      —— 这两张已于 2026-09 按所有者指令删除；下面的号一律是**当时**的号，
#         不要按现在的常量表去读，也不要「顺手改成新号」（改了留档就没了意义）。
#   ② 修 ① 的时候新埋的：Exhibit 3 图注写「各 gs_bar 的次轴已改 12 个月滚动合计同比」，
#      而月末未平仓那张（当时的 Exhibit 9）是 gs_bar、次轴却是**单月**同比
#      （存量不可滚动）—— 与它自己的图注、
#      与页尾的口径条正面打架。把一个假的全称断言换成另一个假的全称断言，只是把过期时间
#      往后推一轮。（2026-09 全页改单月之后，这类句子又被翻了一遍：凡是写着「与滚动口径
#      不是一个口径」的图注全部当场变成假话，逐条改过来了。判据仍然现读 payload。）
#   ③ 同日：①的新版只枚举了「月度刻度」与「季度刻度」两类，而两张热力矩阵（当时的
#      Exhibit 18/19，行 2017 起）与年度桥（当时的 Exhibit 20，2022 起）不在这两类里。
#      它们进了 _AX_EXEMPT 让兜底放行 —— 可**读者手里没有 _AX_EXEMPT**。
#      兜底挡得住「漏放宽一张图」，挡不住「断言的外延本来就比枚举宽」。
#      （那座年度桥 2026-09 改成月度桶之后横轴就是月份轴，已从 _AX_EXEMPT 摘掉；
#       现在这份豁免名单只剩两张热力矩阵。）
# 由此两条规矩，本节全部照办：
#   （1）判据一律现读已经画好的 payload（ylab2 / xlabels / rows / kind），一个都不写死；
#   （2）豁免名单不只喂给兜底，**同时印给读者**，连它们真实的时间范围一起印。

# ── 兜底⓪：图号必须等于 ex.append 的顺序、自 EX_ADV 起连号无洞、核对表接在最后 ──
# 页面按**列表顺序**渲染、读者按**编号**读，两者一旦不一致就是一页乱序的图。
# 外部闸门指望不上：build/verify_pages.py 只把重号判 ERROR、把编号倒退判 WARN
# （不影响退出码），**跳号一声不吭**；而 main() 里那行
# `Exhibit {ex[0]['n']}-{ex[-1]['n']}（{len(ex)} 张）` 假定连号，有洞时会静默印出一个
# 假区间。2026-09 整体重排（删三张、加一张、六张品种柱挪位）之后这道闸门必须在。
_ENS = [e['n'] for e in ex]
_ENS_WANT = list(range(EX_ADV, EX_ADV + len(ex)))
if _ENS != _ENS_WANT or EX_TABLE != EX_ADV + len(ex):
    raise SystemExit(
        f'图号与 ex.append 的顺序对不上：现在是 {_ENS}（应当是 {_ENS_WANT}），'
        f'核对表 EX_TABLE = {EX_TABLE}（应当是 {EX_ADV + len(ex)}）—— '
        f'文件头的常量表与 append 的调用顺序必须一起改。')

# ── 兜底①：「按月/按季推进的图，左端一律是 WIN_FROM」──────────────────
_AX_QTR_LEFT = {EX_RPC: mlab(Q_FROM.asfreq('M', 'end'))}    # 季度 RPC：季末月标 'Mar-16'
#: 这句话**管不到**的图。值不是内部备忘，而是要原样印给读者的理由（见 _ax_other_txt）。
# 2026-09 摘掉了 EX_DECOMP 这一条：那座桥改成月度桶之后横轴就是月份轴、左端与其余
# 月度图相同，留着那条「年度分解桥…不是月份轴」的理由就是印在页面上的一句假话
# （这份名单的值是**原样印给读者**的）。摘掉之后 _ax_bad 会正常检查它的左端。
_AX_EXEMPT = {
    EX_HEAT_YOY: '热力矩阵：年 × 月的格子，没有连续时间轴',
    EX_HEAT_SHARE: '热力矩阵：年 × 月的格子，没有连续时间轴',
}
# 这里**不能**加 `and e.get('xlabels')` 这个前置条件（2026-08-19 之前加了）：横轴走
# rows/cols 的图型（热力矩阵那种）根本没有 xlabels，加了前置条件它就两头落空 ——
# _ax_bad 不检查它，_ax_other_txt() 又只遍历已登记的 _AX_EXEMPT，于是一张忘了登记的
# 新图既不停机、也不会让读者那句「另有 N 张图既不按月也不按季推进」跟着变。
# 现在的判据是：不在 _AX_EXEMPT 里，就必须有月度 / 季度左端；没有 xlabels 也算对不上。
_ax_bad = [(e['n'], (e.get('xlabels') or ['(没有 xlabels，横轴不是时间轴)'])[0])
           for e in ex
           if e['n'] not in _AX_EXEMPT
           and (e.get('xlabels') or [None])[0] != _AX_QTR_LEFT.get(e['n'], XL25[0])]
if _ax_bad:
    raise SystemExit(
        f'Exhibit {EX_ADV} 的图注与页尾口径条断言「按月/按季推进的图左端一律是 '
        f'{WIN_FROM}」，但这些图对不上：'
        + '、'.join(f'Exhibit {n} 起于 {lab}' for n, lab in _ax_bad)
        + '。要么把它们一起放宽，要么把断言改掉并在 _AX_EXEMPT 里登记理由'
          '（登记的理由会原样印给读者，所以要写成读者看得懂的话）。')

# ── 兜底②：页尾口径条断言「本页没有口径断点，图上也确实一条都没画」──────
# 哪天真给某张图传了 break_at，那句话立刻变成假话 —— 让它在构建期响，
# 而不是等读者看见线再来打脸。
_brk_drawn = [e['n'] for e in ex if e.get('break_at') is not None]
if _brk_drawn:
    raise SystemExit(
        '页尾口径条写着「本页没有口径断点」，但 Exhibit '
        + '、'.join(str(n) for n in _brk_drawn)
        + ' 画了 break_at。断点是真的就把那一条改写掉（并说明断点是什么、'
          '为什么现在才出现），不能只加线不改文案。')

_EX_BY_N = {e['n']: e for e in ex}


def _exlist(ns):
    """[18, 19] → 'Exhibit 18 与 Exhibit 19'；空列表 → ''。"""
    ns = list(ns)
    if not ns:
        return ''
    if len(ns) == 1:
        return f'Exhibit {ns[0]}'
    return '、'.join(f'Exhibit {n}' for n in ns[:-1]) + f' 与 Exhibit {ns[-1]}'


def _exnums(ns):
    """[2, 10, 11] → 'Exhibit 2/10/11'（枚举一长就别把「Exhibit」抄十遍）。"""
    return ('Exhibit ' + '/'.join(str(n) for n in ns)) if ns else ''


# ── 现读 payload：次轴是不是**真的**一张不剩全改成了单月 ────────────────────
# 判据只看写进 payload 的字（ylab2 与次轴名），不看作者记得改了几张。
_GS = [e for e in ex if e['kind'] == 'gs_bar']
_GS_MOM = [e['n'] for e in _GS
           if 'single' in ((e.get('ylab2') or '') + (e['yoy']['name'] if e.get('yoy') else '')).lower()]
_GS_ROLL = [e['n'] for e in _GS
            if 'roll' in ((e.get('ylab2') or '') + (e['yoy']['name'] if e.get('yoy') else '')).lower()]
if not _GS or _GS_ROLL or sorted(_GS_MOM) != sorted(e['n'] for e in _GS):
    raise SystemExit(
        f'本页 {len(_GS)} 张 gs_bar 里，声明单月口径的是 {sorted(_GS_MOM)}、'
        f'还留着滚动口径字样的是 {sorted(_GS_ROLL)} —— 页面所有者要的是「全页月度同比'
        f'一律单月」，页尾口径条与 Exhibit {EX_DAYCOUNT} 的导航都是照这句写的。'
        f'要么把漏掉的那张改过来，要么先改断言再改图。')
# 「哪一张读的是存量」这句**因果**也不能凭印象：gs_bar() 建图时登记了哪几张是存量口径
# （kind=YOY.STOCK），这里对一遍。口径统一之后 ylab2 上已经看不出流量与存量的分别，
# 这份登记因此是页面上「那一张读的是月末快照」唯一的依据。
if not set(_GS_STOCK) <= set(_GS_MOM):
    raise SystemExit(f'登记为存量口径的 gs_bar 是 {sorted(_GS_STOCK)}，而声明了单月的是 '
                     f'{sorted(_GS_MOM)} —— 前者应当是后者的子集。')
if len(_GS_STOCK) != 1 or _GS_STOCK[0] != EX_OI:
    raise SystemExit(f'页面多处写着「本页只有 Exhibit {EX_OI} 这一张读的是存量」，'
                     f'而登记为存量口径的是 {sorted(_GS_STOCK)} —— 先改句子。')

# ── 兜底：每一张画**流量**单月同比的图都必须**自己**印过一段代价（§6.1 第 3 条）──
# 判据两侧都现读：应当有代价的 = 声明了单月的 gs_bar 去掉存量那张，再加上把同比画成
# 主序列的 Exhibit EX_DAYCOUNT；实际有的 = yoy_cal_zh() / yoy_cal_lines_zh() 登记的账本。
# 少一张就停机 —— 不停机的话，页尾那句「每一张…都印了」会静默变假，
# 而 2026-09 之前那一版正是这么假的：九张图共用一段总 ADV 的文字，跨图引错了数。
_COST_DUE = sorted(set(_GS_MOM) - set(_GS_STOCK) | {EX_DAYCOUNT})
_COST_MISSING = [n for n in _COST_DUE if n not in COST_LOG]
if _COST_MISSING:
    raise SystemExit(
        f'这些图画了流量单月同比却没有逐图代价段：Exhibit {_COST_MISSING} —— '
        f'CONTRACT §6.1 第 3 条要求每一张都用**它自己那条序列**实测把代价印在图注里，'
        f'「逐图」是字面意思，页尾那段不算数。')
_COST_EXTRA = sorted(set(COST_LOG) - set(_COST_DUE))
if _COST_EXTRA:
    raise SystemExit(
        f'这些图号进了代价账本却不在「该印代价」的名单里：Exhibit {_COST_EXTRA} —— '
        f'账本是页尾口径条点名的依据，多一个就等于替一张不存在的同比图背书。')
# CALIB（页尾、汇总表注、热力图注引用的那一份）声称自己是 CAL_EX 那条线的实测。现验：
# 同列同窗口，逐个统计量必须对得上，否则那句点名是假的。
_cal_ref = next((r['d'] for r in COST_LOG.get(CAL_EX, []) if r['label'] == '总 ADV'), None)
if (_cal_ref is None or _cal_ref['n'] != CALIB['n']
        or abs(_cal_ref['std_mom'] - CALIB['sd_m']) > 1e-9
        or _cal_ref['opposite_n'] != CALIB['n_opp']):
    raise SystemExit(
        f'页尾口径条把 CALIB 点名成「Exhibit {CAL_EX} 那条总 ADV」，但两边对不上'
        f'（账本里的图号：{sorted(COST_LOG)}）—— 先改点名再改数。')
#: 页尾口径条里那张「逐图代价」小结的正文：现读账本，一条线一行，图号与数都不写死。
#: 它顶替不了逐图那一段（契约明说），用途是把各条线的毛刺并排摆一次 ——
#: 只有并排摆才看得出「拿一条线的数替另一条说话」错得有多离谱。
_COST_ROWS = [(n, r['label'], r['d'])
              for n in sorted(COST_LOG) for r in COST_LOG[n]]
_cost_rows_txt = '；'.join(
    f'<b>Exhibit {n}</b>（{lab}）{d["std_mom"]:.1f}pp／'
    f'最大跳变 {d["maxjump_mom"][0]:.0f}pp（{d["maxjump_mom"][2]}）／'
    f'符号相反 {d["opposite_n"]} 个月'
    f'（{d["opposite_n"] / d["n"] * 100:.0f}%，共 {d["n"]} 个可比月）'
    for n, lab, d in _COST_ROWS)
_cost_hi = max(_COST_ROWS, key=lambda t: t[2]['std_mom'])
_cost_lo = min(_COST_ROWS, key=lambda t: t[2]['std_mom'])

# ── 现验三处「同一条数」的断言（三处的图注都写了，所以三处都要由构建期核对）──
#   ① Exhibit EX_DAYCOUNT 的深蓝线 ≡ Exhibit EX_ADV 次轴的金线（逐点相同）；
#   ② Exhibit EX_DECOMP 的净额菱形 ≡ Exhibit EX_REV 次轴的金线（逐点相同）；
#   ③ Exhibit EX_DECOMP 的深蓝段 vs Exhibit EX_DAYCOUNT 的灰线 —— 这两条**不**逐点相同
#      （深蓝段乘过重标定权重 w），图注把差点名成 _log_gap，所以核的是「差正好是它」。
# 既然都写在图注里，就得由构建期核对，不能靠作者记忆。
# 容差 1e-5pp 而不是 `==`：Exhibit EX_ADV 的源列是 adv ÷ 1000（换成「百万张/日」），
# 同比在数学上与不除 1000 的那条完全相同，但两条浮点路径不同，末位可能差 1ulp。
# 1e-5pp 比 payload 自己的 6 位小数还细两个数量级，够严了。
_DUP_TOL = 1e-5
for _n_bar, _si in ((EX_ADV, 1),):
    _gold = _EX_BY_N[_n_bar]['yoy']['values']
    _line = _EX_BY_N[EX_DAYCOUNT]['series'][_si]['values']
    _bad = [i for i, (g, l) in enumerate(zip(_gold, _line))
            if (g is None) != (l is None) or (g is not None and abs(g - l) > _DUP_TOL)]
    if len(_gold) != len(_line) or _bad:
        raise SystemExit(
            f'Exhibit {EX_DAYCOUNT} 的图注声称它的第 {_si + 1} 条线与 Exhibit {_n_bar} '
            f'次轴的金线逐点相同，实际有 {len(_bad)} 个点对不上（首个在 '
            f'{XL25[_bad[0]] if _bad else "长度不同"}）—— 两处图注都得改。')

# ── 第二处：Exhibit EX_DECOMP 的净额菱形 ≡ Exhibit EX_REV 次轴的金线 ──
# 月度化之后这两条是同一条序列（隐含收入的单月同比），图注两边都这么写，所以要现验。
# 它同时是「代价只在 EX_REV 那张印一次」这个安排的依据：同一条数印两遍没有意义。
_rev_gold = _EX_BY_N[EX_REV]['yoy']['values']
_dec_net = _EX_BY_N[EX_DECOMP]['net']['values']
_bad2 = [i for i, (g, d) in enumerate(zip(_rev_gold, _dec_net))
         if (g is None) != (d is None) or (g is not None and abs(g - d) > _DUP_TOL)]
if len(_rev_gold) != len(_dec_net) or _bad2:
    raise SystemExit(
        f'Exhibit {EX_DECOMP} 的图注声称它的净额菱形就是 Exhibit {EX_REV} 次轴的金线，'
        f'实际有 {len(_bad2)} 个点对不上（首个在 '
        f'{XL25[_bad2[0]] if _bad2 else "长度不同"}）—— 两处图注都得改。')

# ── 第三处：Exhibit EX_DECOMP 的深蓝段 vs Exhibit EX_DAYCOUNT 的灰线 ──
# 这两条读的是同一件事（总量的单月同比），但深蓝段乘过重标定权重 w，所以**不**逐点相同。
# 图注把这个差点名成 _log_gap 并叫读者「以本图为准」—— 那句话得由构建期钉住：
# 差的最大值必须正好是 _log_gap（它算的是 |gQ·100 − cq|，而灰线画的就是 gQ·100）。
_dc_gray = _EX_BY_N[EX_DAYCOUNT]['series'][0]['values']
_dec_cq = _EX_BY_N[EX_DECOMP]['stacks'][0]['values']
_gap_obs = max(abs(g - c) for g, c in zip(_dc_gray, _dec_cq)
               if g is not None and c is not None)
if abs(_gap_obs - _log_gap) > 1e-4:
    raise SystemExit(
        f'Exhibit {EX_DECOMP} 的图注声称它的深蓝段与 Exhibit {EX_DAYCOUNT} 灰线的最大差是 '
        f'{_log_gap:.4f}pp（重标定权重 w 造成的那一个），实测 payload 里是 '
        f'{_gap_obs:.4f}pp —— 两个数对不上，先查是不是两条画的已经不是同一件事。')
#: 全页**声明了单月同比**的图：标题 / 次轴名 / ylab2 里带 single 的就算。页尾口径条
#: （a）那一档就是这批图，不再人肉枚举。2026-09 改口径之后这一档不再是「少数例外」，
#: 而是「除了两张非月度刻度的图以外的全部」—— 判据不用改，含义变了，句子跟着改。
#: 判据**不等于** tools/check_yoy_caliber.py 的 R4，别再把两者说成一回事（上上一版就是
#: 这么写的）：R4 认的是含中文的 _MOM_DECL 正则，且把 title / 序列名 / ylab2 / legend
#: 拼在一起看；这里只认 ASCII 的 'single'，看 title 与 ylab2 与次轴名。两边宽严方向不同，
#: 所以下面补一道闸门：凡是用中文「单月」声明口径、却漏出这一档的图，构建期直接停机
#: （否则页尾（a）会漏掉它而 R4 不会）。
_SINGLE_EX = sorted({e['n'] for e in ex
                     if 'single' in (e.get('ylab2') or '').lower()
                     or 'single' in e['title'].lower()
                     or 'single' in ((e.get('yoy') or {}).get('name') or '').lower()})
_ZH_SINGLE = sorted({e['n'] for e in ex
                     if ('单月' in e['title'] or '单月' in (e.get('ylab2') or ''))
                     and e['n'] not in _SINGLE_EX})
if _ZH_SINGLE:
    raise SystemExit(
        f'Exhibit {_ZH_SINGLE} 的标题或次轴名用中文「单月」声明了口径，却没被 _SINGLE_EX '
        f'认出来（它只认 ASCII 的 single）—— 页尾口径条（a）那一档会漏掉这几张。'
        f'要么把声明改成带 single-month 的写法，要么把这里的判据一起放宽。')
_SINGLE_LINE = [n for n in _SINGLE_EX
                if _EX_BY_N[n]['kind'] in ('lines', 'lines_endlabels')]
if _SINGLE_LINE != [EX_DAYCOUNT]:
    raise SystemExit(f'Exhibit {EX_DAYCOUNT} 的图注写着「本图是全页唯一把同比画成主序列'
                     f'的折线图」，但现在这样的折线图是 {_SINGLE_LINE}。')

# ── 代价（§6.1 第 3 条）的**例外集合**：现算，不手写 ──────────────────
# 页尾那句「每一张画流量单月同比的图都把代价印在自己的图注里」是个全称断言，而
# _COST_DUE 只从 kind=='gs_bar' 推导 —— 非 gs_bar 的图画了流量单月同比，三道账本闸门
# （_COST_MISSING / _COST_EXTRA）一律看不见，那句话就会静默变假。
# 本轮就踩过一次：手写「唯一不在名单里的是 Exhibit 16 的净额菱形」，漏掉了 Exhibit 18
# （热力矩阵，每一格也是总 ADV 的单月同比）—— 反例有两个，句子却写着「唯一」。
# 现在改成：例外 = 声明了单月同比的全部图 − 该印代价的 − 读存量的；每一个例外都必须在
# _COST_WHY 里登记「为什么不重复印」，登记的理由**原样印给读者**，漏登记就停机。
_COST_WHY = {
    EX_DECOMP: f'净额与 Exhibit {EX_REV} 次轴的金线是<b>同一条序列</b>（构建期逐点现验）',
    EX_HEAT_YOY: f'每一格与 Exhibit {EX_ADV} 次轴的金线是<b>同一条序列</b>，'
                 f'代价印在那张与本图各自的图注里',
}
_COST_EXEMPT = sorted(set(_SINGLE_EX) - set(_COST_DUE) - set(_GS_STOCK))
_cost_why_miss = [n for n in _COST_EXEMPT if n not in _COST_WHY]
_cost_why_extra = sorted(set(_COST_WHY) - set(_COST_EXEMPT))
if _cost_why_miss or _cost_why_extra:
    raise SystemExit(
        f'代价的例外集合与登记表对不上：Exhibit {_cost_why_miss} 画着流量单月同比、'
        f'又不在该印代价的名单里，但没有登记「为什么不重复印」；'
        f'Exhibit {_cost_why_extra} 登记了理由却已经不是例外 —— '
        f'登记的理由是要原样印给读者的，两边必须一致。')
_COST_EXEMPT_TXT = '；'.join(f'Exhibit {n}（{_COST_WHY[n]}）' for n in _COST_EXEMPT)


def _gs_cal_txt():
    """Exhibit 3 图注里那句「别的图的次轴是什么口径」的导航。判据现读，不靠人脑枚举。"""
    head = (f'本页 {len(_GS)} 张 gs_bar 的次轴（{_exnums(_GS_MOM)}）画的<b>都是</b>'
            f'单月同比，与本图两条线同一个口径')
    if _GS_STOCK:
        head += (f'；其中 {_exlist(sorted(_GS_STOCK))} 读的是<b>存量</b>（月末快照），'
                 f'算法相同但比的是两个时点而不是两个月份的流量，理由见该图图注')
    return head


def _ax_other_txt():
    """「左端一律 WIN_FROM」管不到的那几张图 —— 连它们真实的时间范围一起印给读者。

    只喂给兜底不印给读者，正是上一版翻车的地方：兜底放行了，读者却在页面上看见
    热力矩阵那两张从 2017 起的行标，手里又没有 _AX_EXEMPT 这份名单。
    """
    groups = []
    for e in ex:
        if e['n'] not in _AX_EXEMPT:
            continue
        lab = e.get('rows') or e.get('xlabels') or []
        key = (_AX_EXEMPT[e['n']], f'{lab[0]} – {lab[-1]}' if lab else '')
        if groups and groups[-1][0] == key:
            groups[-1][1].append(e['n'])        # 同型同范围的合并（热力矩阵有两张）
        else:
            groups.append((key, [e['n']]))
    n_ex = sum(len(ns) for _, ns in groups)
    if not n_ex:
        return ''
    body = '；'.join(f'{_exlist(ns)}（{why}{("，" + rng) if rng else ""}）'
                     for (why, rng), ns in groups)
    return f'另有 {n_ex} 张图既不按月也不按季推进，上面这句话对它们不适用：{body}。'


# ── 回填：占位符是空头支票，这里兑现，兑不出来就停机 ──────────────────
_NAV = {_NAV_GS_CAL: _gs_cal_txt(), _NAV_AX_OTHER: _ax_other_txt()}
_nav_used = {k: 0 for k in _NAV}
for _e in ex:
    if not _e.get('note'):
        continue
    for _k, _v in _NAV.items():
        if _k in _e['note']:
            _nav_used[_k] += 1
            _e['note'] = _e['note'].replace(_k, _v)
_nav_miss = [k for k, c in _nav_used.items() if not c]
_nav_left = sorted({e['n'] for e in ex for k in _NAV if k in (e.get('note') or '')})
if _nav_miss or _nav_left:
    raise SystemExit(f'跨图导航句没有兑现：占位符 {_nav_miss} 没有任何图用到，'
                     f'{_nav_left} 的图注里还留着没回填的占位符。')


# ═════════════ 5. 核对表（Exhibit EX_TABLE，官方原始单位）═════════════
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
    f'<b>同比一律用<u>单月</u>口径，不是 12 个月滚动合计 —— 页面所有者指定。</b>'
    f'2026-09 起本页所有月度刻度的同比（各图次轴的金色折线、Exhibit {EX_DAYCOUNT} 的两条线、'
    f'热力矩阵、汇总表的 y/y 列、页顶那两段）都是「当月 ÷ 去年同月 − 1」。'
    f'这不是本页自己的偏好：<code>build/CONTRACT.md</code> §6 在同一轮里已整条改写成'
    f'「全站同比只有一种口径：单月同比，页面上一条 12 个月滚动合计的同比都不画」，'
    f'本页是照契约办 —— 次轴名与轴标题写着 single month，'
    f'<b>每一张画流量单月同比的图（{_exlist(_COST_DUE)}）都按 §6.1 第 3 条'
    f'把代价印在<u>自己</u>的图注里，用的是<u>那条线自己</u>的实测</b>'
    f'（构建期逐张核对，少一张就停机不出图）。'
    f'名单之外还有 {len(_COST_EXEMPT)} 张图也画着流量单月同比，它们不重复印代价，'
    f'理由逐张登记（构建期核对，漏登记就停机）：{_COST_EXEMPT_TXT}。'
    f'这条口径推翻的是 2026-08 那次全站审计的<b>结论</b>，'
    f'不是它的<b>测量</b>：那次测到的毛刺是真的（下面就是本页自己那一份），'
    f'但它真正的病根是「同一页混用两种口径」，统一成单月同样解决 —— '
    f'而单月是能被读者拿柱高自己除出来核对的那一种。'
    f'本页因此有一个决定性的好处：<b>柱与线取自同一列</b>，'
    f'拿一根柱除以 12 根柱之前那根，就是金线上的那一点。'
    f'<b>代价照写，不藏</b>：单月同比把「去年那<b>一个</b>月碰巧是什么样」整个塞进分母，'
    f'去年同月若是异常低点，今年一个平淡的月份也能印出三位数增速；后果不是噪声大一点，'
    f'而是<b>方向会反</b>。'
    f'<b>代价是逐图的，每张图的图注里印的都是<u>那条线自己</u>的实测</b>'
    f'（§6.1 第 3 条：「逐图」是字面意思，页尾这一段顶替不了它）—— '
    f'各条线的毛刺差得很远，所以在这里并排摆一次（逐月标准差／相邻月最大跳变／'
    f'与 12 个月滚动口径符号相反的月份数；统计范围都是各图自己画出来的那段窗口 '
    f'{XL25[0]} – {XL25[-1]}，滚动那一侧本页一条都不画，只作对照）：'
    + _cost_rows_txt + '。'
    + f'最毛的是 <b>Exhibit {_cost_hi[0]}</b>（{_cost_hi[1]}，{_cost_hi[2]["std_mom"]:.1f}pp），'
    f'最稳的是 <b>Exhibit {_cost_lo[0]}</b>（{_cost_lo[1]}，{_cost_lo[2]["std_mom"]:.1f}pp），'
    f'相差 {_cost_hi[2]["std_mom"] / _cost_lo[2]["std_mom"]:.1f} 倍 —— '
    f'<b>不要拿其中一条线的数去读另一条</b>。'
    f'（本页 2026-09 之前就是这么错的：九张图共用一段文字，印的全是 Exhibit {CAL_EX} '
    f'那条总 ADV 的数，而且量的是全历史而不是图窗。）'
    + f'总 ADV（Exhibit {CAL_EX}）那条线的完整对照：单月逐月标准差 '
    f'<b>{CALIB["sd_m"]:.1f}pp</b>、12 个月滚动 <b>{CALIB["sd_r"]:.1f}pp</b>'
    f'（放大 <b>{CALIB["sd_m"] / CALIB["sd_r"]:.1f} 倍</b>），滚动口径同期最大跳变 '
    f'<b>{CALIB["jump_r"]:.1f}pp</b>'
    + (('；两者符号相反的最近几例：' + '、'.join(
        f'{p}（单月 {pct(r["m"])}／滚动 {pct(r["r"])}）'
        for p, r in CALIB['opp'].tail(3).iterrows()) + '。')
       if CALIB['n_opp'] else '。')
    + f'所以本页的金色折线要<b>连着柱高一起读</b>：单看它、光是挑月份就能把结论说成两个方向；'
    f'本页现在不画任何平滑口径的线，判趋势请看水平值本身的形状。'
    f'换来的一点好处：单月口径只要 12 个月历史（滚动口径要 24 个月），而本页序列自 '
    f'{mlab(df.index[0])} 起，窗口左端因此不再有一段空着的折线。'
    f'近零基数的序列不该画同比（§6.1 第 5 条，契约明说这一条在单月口径下更要紧：滚动合计还能把一个近零的'
    f'分母摊薄，单月不能）—— 本页画同比的每一条都在构建期过了 '
    f'<code>yoy.near_zero_base()</code>，窗口内近零基数月一个都没有，命中就直接停机不出图。'
    f'<b>不乘交易日数</b>：本页立场是 ADV 已按交易日中性化（公司直接披露的就是它）。'
    f'这一条的理由在改口径之后<b>变了，得说清楚</b>：滚动口径下日均与交易日加权两种聚合的'
    f'同比最大只差 {DC_MAXGAP:.1f}pp、'
    + ('逐月符号完全一致' if DC_SAME_SIGN else '仍有符号不一致的月份')
    + f'（交易日效应在 12 个月窗口里基本自抵，「乘不乘都一样」）；'
    f'而在现在用的单月口径下它<b>完全不自抵</b> —— {DC_N_MOM} 个可比月里最大差 '
    f'<b>{DC_MAXGAP_MOM:.1f}pp</b>（中位 {DC_MEDGAP_MOM:.1f}pp）、{DC_OPP_MOM} 个月符号相反。'
    f'所以不乘的理由不再是「差不多」，而是契约 §6.4 那一条：日均列的单月同比'
    f'（日均 ÷ 去年同月日均）本身就把「今年这个月多开几天市」除掉了，乘回去等于把它请回来。'
    f'而差多少本页不藏：Exhibit {EX_DAYCOUNT} 整张图就是把这个差画出来。'
    f'（「ADV × 当月交易日数」= 当月一共成交了多少张，那是<b>另一个量</b>的水平值，'
    f'汇总表里有同一行；本页 2026-09 起不再单独给它出柱图，Exhibit {EX_DAYCOUNT} '
    f'的灰线画的就是这个量自己的单月同比，不是把 ADV 的同比按交易日重新加权。）',

    f'<b>本页的同比只有一种口径：单月同比，已逐处点名。</b>'
    # 点名一律用契约 §6.2 规定的「Exhibit N、Exhibit M」写法，不用 _exnums 的
    # 「Exhibit 2/3/9」缩写：后者读者要自己补「Exhibit」两个字，而 tools/check_yoy_caliber.py
    # 的点名判据（正则 `(?:Exhibit|Ex\.?)\s*(\d+)`）也只认得斜杠前的第一个号 ——
    # 缩写等于只点名了第一张。宁可长一点。
    f'（a）<b>单月同比</b>（当月 ÷ 去年同月 − 1）—— 全页月度刻度的同比一律走这一档，'
    f'包括 {_exlist(_SINGLE_EX)} 这 {len(_SINGLE_EX)} 张图（其中 {_exlist(_GS_MOM)} '
    f'是 gs_bar 次轴的金色折线）、汇总表的 y/y 列与页顶「{B.TITLE}」一段；'
    f'这一档由构建期现读 payload 认定 —— 标题、次轴名或 ylab2 里带 single 的就归这一档，'
    f'不靠人肉枚举，漏掉一张会当场停机。'
    f'（2026-09 之前这里还有另外两档：一张季度合计柱（本季 3 个月合计 vs 上年同季）与'
    f'一座按日历年分桶的分解桥。前者已按所有者指令删除，后者同轮改成<b>月度</b>桶 —— '
    f'Exhibit {EX_DECOMP} 现在一格 = 一个月、比的就是去年同月，归进上面这一档。）'
    f'（a）里有两处要单独记住：<b>Exhibit {EX_OI} 读的是存量</b>（月末快照），'
    f'算法与其余各图相同，但比的是两个<b>时点</b>的持仓而不是两个月份的成交流量 —— '
    f'它也从来没有「滚动合计」这个选项（把 12 个月末的存量加起来不是任何东西），'
    f'而且存量不吃日历效应、本来就比成交量稳（图窗 {XL25[0]} – {XL25[-1]} 内实测标准差 '
    f'{CALIB_OI["sd_m"]:.1f}pp vs 总 ADV 的 {CALIB["sd_m"]:.1f}pp，相邻月最大跳变 '
    f'{CALIB_OI["jump_m"]:.0f}pp vs {CALIB["jump_m"]:.0f}pp）；'
    f'<b>Exhibit {EX_DAYCOUNT} 的深蓝线与 Exhibit {EX_ADV} 次轴的金线是同一条数</b>'
    f'（构建期逐点现验），那张图的作用是把它与总量那条并排放在一根轴上量交易日贡献。'
    f'「流量与存量各自的合法口径」这条判据不是本页自订的，实现在全站唯一的 '
    f'<code>build/yoy.py</code> 里，对存量调滚动合计会直接抛错。',

    '<b>ADV 与总量的口径差（Barclays 调整）。</b>ADV 本身已按交易日中性化，总成交合约数没有。'
    'Barclays 那份报告因交易日数差异，把「股票成交总量 +7%」修正为「按日 -5%」，方向被口径整个反转。'
    f'Exhibit {EX_DAYCOUNT} 把两条同比并排画出来，两线之差纯粹是交易日数的变化；'
    '月度总成交量 = ADV × 当月交易日数，这一步换算是本页做的，不是公司披露的单独口径。'
    '汇总表末行的「Trading days」同理只是月历读数，所以它的 m/m、y/y 不着色、3Y %ile 留空 —— '
    '多一个交易日既不是好消息也不是坏消息。',

    # 原句是「<b>唯一</b>带外推成分的推导值：Exhibit 13。」——隔两句就被自己那条
    # 「Exhibit 20 建在这张图之上，所以同样带外推成分」推翻。把假的全称断言换成另一个
    # 假的全称断言，正是这一页翻过三次的车。这里不再声称「唯一」：句子只讲这一张图，
    # 而「有没有外推」由 CARRY（现算出来的沿用费率月份）决定 —— 哪个月开始外推、外推
    # 几个月，RATE_PERIOD 已经现算写在同一条注的末尾；没有外推时这半句自动消失。
    (f'<b>Exhibit {EX_REV} 是推导值，而且带外推成分。</b>' if CARRY else
     f'<b>Exhibit {EX_REV} 是推导值。</b>（本页每个月都落在已披露费率的季度里，'
     f'所以它当前不含外推成分。）')
    + f'Implied transaction revenue = 当月成交合约数 × '
    f'每张平均费率（RPC）。RPC 是季度值（CME 季报），当季各月共用该季费率，'
    f'最新季（{qlab(RPC_Q)} = ${RPC_V:.3f}）'
    '之后沿用。CME 的 RPC 本身是用已披露收入倒推的，所以已收官季度只是把一个已知总额重建一遍 —— '
    '这张图的价值全在<b>当前未收官的季度</b>。标题带 Implied 即表示非公司披露值。'
    # 上一版在这里挂了一串「本页另外几处推导」的人肉清单（页顶电子化占比、总成交、
    # Exhibit 4 与 19 的占比），那串清单只为撑住前面那个「唯一」。「唯一」已经删掉，
    # 清单也就没有活干了 —— 留着它等于留一份下个月加图就过期、又没有任何东西会报错的
    # 断言。汇总表哪几行是推导值，现在由 _sum_provenance() 现读 CSV 表头印在表注里。
    + (f'（Exhibit {EX_DECOMP} 的量价分解建在这张图之上、Exhibit {EX_REVMIX} 的品种'
        f'收入结构走的是同一套季度费率，所以两张同样带外推成分 —— '
        f'{EX_REVMIX} 那张的外推月按<b>六条品种费率里最早的那一季</b>算，'
        f'与本条按 rpc_total 算的月份未必一样，逐格点名写在它自己的图注里。）'
       if CARRY else '')
    # 「用的是哪一季费率」随每月新数据自动变化，所以这句由数据现算，不写死季度号。
    + RATE_PERIOD + RATE_STALE,

    f'<b>RPC 的口径风险。</b>各品种 RPC 相差 {RPC_SPREAD_X:.2f} 倍'
    f'（{qlab(RPC_Q)} 实测，{len(CLS_REV)} 条全部画在 Exhibit {EX_RPC}），因此总 ADV 不变、'
    f'只要品种结构位移，混合费率与隐含收入照样会动。这是上面那座桥最大的不确定性；'
    f'Exhibit {EX_MIX} 把品种结构与体量画在同一张图里，'
    f'Exhibit {EX_REVMIX} 则把这件事直接量成钱 —— 同一个月里各品种占成交量的比重与'
    f'占隐含收入的比重差得很远，差多少见那张图的图注。',

    '<b>汇总表的 3Y %ile。</b>= 当月读数在最近 36 个月里高于多少百分比的观测，'
    '由全站唯一的一份实现（<code>build/pctile.py</code>）算出，本页不再自带判据 —— '
    '各页各写一份，正是同一条序列在两页判定相反的原因。'
    '留空的判据是「把这一列在过去 24 个月里逐月回放一遍，若 ≥70% 的月份都钉在 100 或 0，'
    '这一列对这一行没有区分度」；旧判据「≥90% 的月环比不降」测的是序列形状而不是分位列本身，'
    '拦不住「上下波动但分位常年钉 100」的行。'
    '本页另有一处按自己的口径留空：Trading days 是日历产物（见⟨note:daycount⟩）。'
    '比率类指标的差异一律用 pp/bp；本页汇总表里没有比率行，故全部是百分比变化。',

    '<b>口径断点：本页没有，图上也确实一条都没画。</b>CME 的 ADV / 未平仓合约 / 交易日口径'
    f'自 {mlab(df.index[0])} 至今保持一致，品种六分类穷尽且互斥，所以全页没有红色竖虚线断点，'
    '相邻期可以直读 —— 本页任何一处图注都没有声称过存在断点线，说的和画的一致。'
    '若日后出现并购并表或品种重分类，必须在这里登记、给对应 exhibit 传 break_at 画出竖线，'
    '并在断点滚出窗口后让图注文案一起消失，不能只靠图注文字提一句、也不能因为断点滚出窗口就报错停更。',

    '<b>与原 PDF 版的有意差异（四处）。</b>'
    f'(a) <b>凡是按月或按季推进的图，左端一律统一在 {WIN_FROM}'
    f'（月度刻度 {WIN_LINE} 个月）</b>，不是 deck 的 25 个月。'
    f'这一条 2026-08-18 先在曲线类（Exhibit {EX_DAYCOUNT}/{EX_MAJORS}/{EX_MINORS}）落地，'
    f'2026-08-19 gs_bar 与堆叠柱（Exhibit {EX_ADV}/{EX_MIX}/{EX_RATES}/{EX_EQUITY}/'
    f'{EX_ENERGY}/{EX_FX}/{EX_METALS}/{EX_AG}/{EX_OI}/{EX_REV}）跟上 —— 那批图此前停在 '
    f'13 个月，写的理由是契约 §5.4「近期图<b>固定</b> 13 个月」'
    f'（2026-09 新增的 Exhibit {EX_REVMIX} 与改成月度的 Exhibit {EX_DECOMP} 直接按这个'
    f'左端建，不在那一轮的名单里）。这里说清楚：'
    f'§5.4 的原文写的是「固定」，本页是<b>有意不照它办</b>，不是把它读成了「至少」——'
    f'理由是这条规矩的括注（「够算 y/y 首末对比与 prior-12mo 均值」）讲的是为什么 13 个月'
    f'够用，而不是为什么更长不行，而本页 {mlab(df.index[0])} 起的数据一直都在'
    f'（<code>series/cme.csv</code> 自 {mlab(df.index[0])} 起满 {len(df)} 个月），'
    f'13 个月是画的时候截的、不是数据没有。'
    f'§5.4 该怎么改由 <code>build/CONTRACT.md</code> 的持有者裁决，本页不动那份文件，'
    f'只在这里公开这处冲突。'
    f'季度刻度的只剩 Exhibit {EX_RPC} 一张，左端换算成 {qlab(Q_FROM)}、共 {len(_rq)} 个'
    f'季度（比图窗覆盖的 {_Q_SPAN} 个少 {_Q_SPAN - len(_rq)} 季，是费率尚未披露）。'
    f'本页不再单独画全历史线（原 deck 的那张已按所有者指令删除），'
    f'末尾核对表仍是 {WIN_TABLE} 行（表是拿来逐行核对的，不是时序图）。'
    # 这一句是上一版漏掉的三张图：兜底把它们豁免了，读者却在页面上看得见 2017 与 2022。
    + _ax_other_txt() +
    f'{WIN_LINE} 期放不进半栏卡片：<code>build/mrwin.py</code> 按 '
    f'<code>assets/charts.js</code> 的量边距算式在构建期判「要不要升通栏、x 标签隔几期'
    f'标一个」，⟨nav:mrwin-px⟩。'
    '次轴那条金色 y/y 折线画的是同比而不是 12 个月均线（deck 的 docstring：「均线只是把柱子'
    '再平滑一遍、不带新信息」），这一点与 deck 一致；<b>同比口径现在也与 deck 一致</b> —— '
    '两边都是<b>单月</b>同比。（网页版 2026-08 曾把流量图改成 12 个月滚动合计同比，'
    '2026-09 按页面所有者的指令改回单月，所以这里不再是一处差异；'
    '细节上仍有一点不同：deck 在 gsx.lvl_bar 里对「基期小于序列中位绝对值 15%」的单点留空，'
    '网页版走 <code>build/yoy.py</code> 的判据 —— 近零基数是<b>整条序列</b>的属性、'
    '命中就不画同比，而不是逐点挖洞；本页画同比的每一条序列在窗口内一个近零基数月都没有'
    '（构建期逐张现验），所以窗口内两种判法给出的线是同一条。）'
    f'(b) deck 的品种曲线图把 {len(CLS)} 个品种画在一根轴上，利率品种的峰值把量级小的'
    f'那几条压成底部一条带；网页版按<b>窗口内峰值大小</b>拆成 Exhibit {EX_MAJORS}'
    f'（峰值最大的 {len(CLS_MAJOR)} 个）与 Exhibit {EX_MINORS}（另外 {len(CLS_MINOR)} 个）'
    f'两张，数据、窗口、配色全同，没有删点、没有截轴（详见两图图注）。'
    '(c) 金属品种在 deck 里用金色 #BF9000，网页引擎的调色板后来补齐了同一个金色，'
    '所以两边同色；红色在本站是断点与离群值的专用色，不拿来当数据色。'
    f'(d) Exhibit {EX_RPC} 的第三位小数无对应实现（图上按 $0.01 显示），'
    '精确值逐条写进该图图注。',

    f'<b>Exhibit {EX_DECOMP} 分的是收入，不是成交额。</b>恒等式「隐含交易收入 = 成交合约数 × '
    f'每张平均费率」两边都在本页有数，所以这张分解做得成；而「成交额 = 成交量 × 均价」'
    f'那种分解本页<b>不具备数据条件</b> —— CME 按月披露的是合约张数与未平仓合约，'
    f'从来没有披露过成交<b>金额</b>；要凑一个名义本金得逐品种乘合约乘数，本仓的 '
    f'<code>series/contract_specs.csv</code> 只覆盖一部分品种，拿它当分母算出来的「均价」'
    f'方向与大小都不可知，而且图上完全看不出来。宁可不做。'
    f'<b>横轴一格 = 一个月</b>（{_dxl[0]} – {_dxl[-1]}，{len(_dxl)} 格），与本页其余月度图'
    f'逐格对齐；同比是单月同比（当月 ÷ 去年同月 − 1），与各图次轴的金线同一个口径。'
    f'2026-09 之前这张按日历年分桶、末柱是当年 YTD，按页面所有者的指令改成月度 —— '
    f'因此它与全站其余 decomp（那些仍是年度桶）<b>不再同口径</b>，跨页不要比。'
    f'当月收入 = 当月张数 × 当月费率；当月 RPC = 收入 ÷ 张数，两侧都不做平均。'
    f'分解本身是恒等式而不是估算：图上两块相加逐格等于总增长，生成脚本对算术闭合、对数闭合、'
    f'重标定闭合三道检查都设了 {DEC_EPS:.0e} 的硬门槛，超了直接退出、不出图。'
    f'图上画的是<b>对数分解按总增长重标定后的两块</b>（w = g<sub>收入</sub> ÷ ln(V₁/V₀)，'
    f'ln 天然可加、无交叉项、不必选归属，纵轴回到 %）；算术分解照算但只进图注 —— '
    f'算术版必须把交叉项整段压给某一腿，本页实测交叉项绝对值中位 {_CROSS_PP_MED:.2f}pp、'
    f'最大 {_CROSS_PP_MAX:.2f}pp，量与费率方向对冲的月份（{_OPP_N} 格）画出来就是错的。'
    f'费率一季才披露一次，所以<b>算术读数</b>里的费率同比在同一季内三个月相同；'
    f'但图上那段金色乘过逐月不同的权重 w，同季并不等高（最大落差 {_CP_QSPREAD_MAX:.2f}pp）。'
    f'费率那一块要按「结构 + 定价」读，不能当纯价格 —— RPC 是 CME 从'
    f'已披露收入倒算的，各品种 RPC 相差 {RPC_SPREAD_X:.2f} 倍（Exhibit {EX_RPC}），'
    f'品种结构一位移它就动，结构本身画在 Exhibit {EX_REVMIX}。',

    f'<b>核对表（Exhibit {EX_TABLE}）用官方原始单位，不做任何换算</b>：ADV 为千张/日、'
    '未平仓合约为张、交易日为天，可直接与 CME 月度 xlsx 逐格对。'
    '图上的「百万张」「百万美元」都是本页换算后的口径，核对时请以核对表为准。',
]

# ── 「见第 N 条」这类交叉引用：现找条号，不写死 ──────────────────────
# 写死的条号是必然过期的，而且过期之后页面上一点痕迹都没有 —— 它只是安静地指到别人
# 身上。本轮就修了两处：表注写「判据见第 7 条」（3Y %ile 实际是第 9 条，第 7 条是 RPC
# 口径风险）、第 9 条自己写「见第 3 条」（日历产物的理由实际在第 5 条，第 3 条是同比口径）。
# 锚点取该条开头那个加粗小标题：它本来就是唯一的，改标题会当场停机而不是悄悄指错。
_NOTE_ANCHOR = {'⟨note:pctile⟩': '<b>汇总表的 3Y %ile。</b>',
                '⟨note:daycount⟩': '<b>ADV 与总量的口径差（Barclays 调整）。</b>',
                '⟨note:caliber⟩': '<b>本页的同比只有一种口径：单月同比，已逐处点名。</b>'}
NOTE_NO = {}
for _mark, _anchor in _NOTE_ANCHOR.items():
    _hit = [i for i, t in enumerate(NOTES) if _anchor in t]
    if len(_hit) != 1:
        raise SystemExit(f'交叉引用 {_mark} 的锚点「{_anchor}」在页尾 notes 里命中 '
                         f'{len(_hit)} 条 —— 条号找不准就不能印给读者。')
    NOTE_NO[_mark] = f'第 {_hit[0] + 1} 条'


def note_ref(mark):
    """NOTES 之外的地方（表注等）引用条号走这里；NOTES 自己用占位符，见下面那段回填。"""
    return NOTE_NO[mark]


for _mark, _no in NOTE_NO.items():
    NOTES = [t.replace(_mark, _no) for t in NOTES]
_note_left = [i + 1 for i, t in enumerate(NOTES) if '⟨note:' in t]
if _note_left:
    raise SystemExit(f'页尾第 {_note_left} 条里还留着没回填的条号占位符。')

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

    ═══ 同比口径（2026-09 全页改造后，本段的既定立场）═══
    本页所有月度刻度的同比现在都是**单月**同比（页面所有者指定，理由与实测代价见页尾
    口径条）—— 本段讲的又正是「本月 / 上月 / 去年同月」三个具名月份，所以这里的 m/m 与
    y/y 与各图次轴、与紧挨着的汇总表**同口径**，可以直接对读。
    即便如此，**凡出现同比措辞仍然一律写明「单月」**（CONTRACT §6）：口径是页面级的约定、
    会随一纸指令再变（这一页两个月里就变过两回），而这一段的口径由它自己讲的三个具名月份
    钉死，写明白了才不用跟着页面口径改一遍。趋势判断不归本段管 —— s2 的职责只是基数护栏
    （这个环比是不是被上月极值顶出来的），措辞不越这条线；本页不画任何平滑口径的线，
    要看趋势请看柱高本身（Exhibit EX_ADV 的柱高）。

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
    #    这一句里的同比是**单月**同比（与紧挨着的汇总表 y/y 列、与各图次轴同口径）。
    #    仍然点名的理由见 docstring：页面口径是会变的，这一段的口径不会。
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


# ══════════════════════════ 6.5 名词释义（payload 的 `glossary`）══════════════════════════
# 排在所有 exhibit 之前，页面最上方的一段定义。版式与四道护栏在 build/glossary.py，
# 这里只交 [(词, 释义), …]；顺序即页面上的顺序。
#
# ━━ 与 brief / 图注 / 页尾 notes 的分工 ━━
# brief 与图注说的是「**这个月**这组读数该怎么读」（含当月读数、当图窗口内实测的毛刺量），
# 每月重写；这一块说的是「**这些词**是什么意思」，一年到头是同一段
# ⇒ 这里**一个当月读数都不写**，也不写「最新一期」。出现的数只有两类：
#   (a) 把定义钉住的结构性量 —— 本页只有一个（交易日数的全样本区间，import 期现读
#       series/cme.csv，见下面的 TD_MIN/TD_MAX，一个数都没写死）；
#   (b) 恒等式本身（ADV = 当月合计 ÷ 当月交易日数；收入 = 张数 × RPC）。
#   其余凡是随窗口滚动的实测（六段之和有几期不等、交叉项占多少、各线的毛刺 pp）
#   一律**只留一句指路**，数字仍归各自的图注 —— 同一个数印两处，迟早只改一处。
#
# ━━ 为什么是这 10 个词（选词判断）━━
# 判据只有一条：这个词出现在本页的图题 / 序列名 / 纵轴 / 汇总表行头 / 核对表列头 /
# 图注里，而且**不看定义就会读错**。按「读错会出什么事」分四类：
#   ① 单位与分母   合约张数 / ADV / 当月成交合约数 / 交易日数 —— 本页最密集的坑：
#      ADV 是公司披露的、已按交易日中性化，当月合计是本页乘回交易日数轧出来的，
#      两者只差一个当月开市天数（Exhibit EX_DAYCOUNT 整张图就是量这个差）。
#      不点破，读者会拿 contracts/day 与 contracts/month 直接比高低，
#      或者把「合约张数」读成美元成交额（CME 从不披露成交金额）。
#   ② 存量 vs 流量   未平仓合约（OI）—— 与 ADV 并排画在同一页上，两者不能相加，
#      同比也只能走点对点。
#   ③ 结构口径      品种划分 / 占总 ADV 的比重 —— 后者本页有**两个分子不同**的版本
#      （Exhibit EX_MIX 右轴是利率+股指，Exhibit EX_HEAT_SHARE 与抬头是利率一个品种），
#      读串了整条线会整体位移，而图形完全正常（两条占比之差恰是股指品种的占比，
#      随窗口滚动，所以这里只指路、不写量级 —— 数字归两张图各自的图注）。
#   ④ 推导链条      RPC / 隐含交易收入 / 量价分解 —— 三个词是同一条链：费率按季披露、
#      由已披露收入倒算，隐含收入非公司披露且末几个月带外推，桥分的是**收入**不是成交额。
#      这一类的共同后果是把推导值当成披露值读。
# **有意不收**：
#   · m/m、y/y、3Y %ile、pp/bp —— 全站通用的读图约定，汇总表的 summary.note 已逐条讲过；
#   · 「单月同比 vs 12 个月滚动合计」与「本页三种同比口径」—— 页尾 notes 第 3、4 条
#     讲的正是这两件事在本页的**具体落点**（连同逐图实测），释义板再讲一遍就是两处
#     各写一份，而且那份实测随窗口滚动，抄到这里就会与图注对不上；
#   · 「口径断点」—— 页尾 notes 第 10 条已经写明本页没有断点、图上也一条没画；
#   · 「电子化占比」—— 它只出现在每月重写的 brief 里，页面的图与表都不画它
#     （brief 自己已标「推导值」），释义板挂一个只在别处出现一次的词是虚的；
#   · 成交量、市值这类本页没有特殊口径的常识词。
#   · 「未满季」「YTD」—— 2026-09 的 /cme/ 重排（057ae0c）删掉了季度柱图、并把量价
#     分解从日历年分桶改成**月度**分桶，两根「不可直读的末柱」在本页都不复存在。
#     这两条释义连同原第 ⑤ 类一起删了：释义板解释的是**本页现在有**的词，
#     页面上已经没有的词留在这里，比不解释更糟（读者会去图上找那根浅蓝末柱）。
TD_MIN, TD_MAX = int(df['trading_days'].min()), int(df['trading_days'].max())

GLOSSARY = [
    # ① 单位与分母 —— 四个词一组，后三个都要用到第一个
    ('合约张数',
     f'本页所有体量指标的单位都是<b>合约张数</b>（contracts），<b>不是金额</b>：'
     f'CME 按月披露的是张数与未平仓合约，从来没有披露过成交<b>金额</b>。'
     f'所以本页任何一处的「量」都不能读成美元成交额；'
     f'要把张数折成名义本金得逐品种乘合约乘数，而本仓的 '
     f'<code>series/contract_specs.csv</code> 只覆盖一部分品种，本页因此不做这个换算 —— '
     f'Exhibit {EX_DECOMP} 那座桥分的是<b>收入</b>而不是成交额，也是同一个理由。'),

    ('ADV',
     f'<b>日均成交张数</b>（average daily volume，核对表印作 k contracts/day；'
     f'图上按 k 或 mn contracts/day 两种换算，<b>以各图纵轴自标的为准</b>）：'
     f'<code>当月成交合约数 ÷ 当月交易日数</code>。'
     f'这一列是 CME <b>直接披露</b>的、未经加工，本页不自算 —— 反过来，'
     f'「当月成交合约数」才是本页拿它乘回交易日数轧出来的。'
     f'⚠️ ADV <b>已按交易日中性化</b>：今年这个月多开几天市，它不会因此变高。'),

    ('当月成交合约数',
     f'当月成交张数的<b>合计</b>（汇总表的 Total contracts traded 一行）。'
     f'<b>不是 CME 单独披露的一列</b>，是本页轧出来的：<code>ADV × 当月交易日数</code>。'
     f'它<b>没有</b>按交易日中性化 —— 与 ADV 的<b>比值</b>就是当月开了几天市；'
     f'两者<b>同比之差</b>才是交易日贡献（单位 pp，'
     f'Exhibit {EX_DAYCOUNT} 整张图量的就是这个差）。'
     f'⚠️ 它的纵轴是 contracts/month，ADV 那几张是 contracts/day，'
     f'<b>不是一个单位</b>，跨图比柱高没有意义。'),

    ('交易日数',
     f'当月的开市天数（汇总表的 Trading days，CME 直接披露）。'
     f'它是<b>月历的产物</b>，不是经营结果 —— 多一个交易日既不是好消息也不是坏消息，'
     f'所以汇总表这一行的 m/m 与 y/y 只给数字、不着色，分位整格留空。'
     f'本页全样本实测在 <b>{TD_MIN}–{TD_MAX} 天</b>之间，'
     f'所以「当月合计」与 ADV 之间<b>不是一个常数倍</b>。'),

    # ② 存量 vs 流量
    ('未平仓合约（OI）',
     f'open interest：月末<b>仍未了结</b>的合约张数，是月末快照那一天的<b>存量</b>，'
     f'不是当月累计的<b>流量</b>。'
     f'⇒ 与 ADV、当月成交这些流量口径<b>不能相加</b>，高低也不要放在一起比；'
     f'它的同比只能走点对点（月末 vs 去年同月月末）—— 把 12 个月末的快照加起来'
     f'不指代任何真实的量（<code>build/yoy.py</code> 对存量调 12 个月滚动合计直接抛错）。'),

    # ③ 结构口径
    ('品种划分',
     f'CME 把成交拆成的六个资产类别（利率、股指、能源、农产品、外汇、金属），'
     f'<b>穷尽且互斥</b>，所以六段之和在<b>口径上</b>就是披露的 Total ADV；'
     f'但<b>数值上并非逐月严格相等</b>，多数月份差的是各品种各自取整到千张的舍入。'
     f'本页对任何一种残差都<b>不做配平</b>，柱高一律是官方原值 —— '
     f'哪几期不等、差多大，见 Exhibit {EX_MIX} 的图注（逐期现算）。'),

    ('占总 ADV 的比重',
     f'本页有<b>两个分子不同</b>的「占比」，分母都是披露的 Total ADV：'
     f'Exhibit {EX_MIX} 的右轴是<b>利率 + 股指两大品种合计</b>的占比，'
     f'Exhibit {EX_HEAT_SHARE} 的热力矩阵（与抬头那一项）是<b>利率一个品种</b>的占比。'
     f'两者<b>不是同一条序列</b>，读串了整条线会整体位移，而图形完全正常 —— '
     f'两条线各自的水平以 Exhibit {EX_MIX} 的右轴与 Exhibit {EX_HEAT_SHARE} 的格子为准。'
     f'⚠️ Exhibit {EX_HEAT_SHARE} 的格子装的是<b>占比的水平值</b>，'
     f'而 Exhibit {EX_HEAT_YOY} 那张同样长相的热力矩阵装的是<b>同比</b>，两张不能对读。'),

    # ④ 推导链条：费率 → 隐含收入 → 分解桥
    ('RPC（每张平均费率）',
     f'rate per contract：每成交一张合约 CME 平均收到多少钱，<b>按季</b>披露（季报），'
     f'当季各月共用该季的值，最新一季之后沿用。'
     f'⚠️ 它是 CME 拿<b>已披露收入倒算</b>出来的，因此同时吸收了品种结构位移、'
     f'定价调整与折扣计划，<b>不是一个纯粹的「价」</b>；'
     f'各品种的 RPC 相差数倍（Exhibit {EX_RPC}），'
     f'总 ADV 一动不动、只要品种结构位移，混合费率照样会动。'),

    ('隐含交易收入',
     f'implied transaction revenue：<code>当月成交合约数 × 当季 RPC</code>，'
     f'<b>不是公司披露的数</b>（Exhibit {EX_REV} 标题里的 Implied 就是这个意思）。'
     f'已收官的季度只是把一个已知总额重建一遍，这张图的价值全在<b>尚未收官</b>的那个季度；'
     f'落在最新可得费率季度之后的月份是<b>沿用上一季 RPC 外推</b>的，费率补齐后会被改写'
     f'（本页当前挂在哪一季，见 Exhibit {EX_REV} 图注的「费率期间」一段）。'),

    ('量价分解',
     f'Exhibit {EX_DECOMP} 那座桥分的是<b>收入</b>，不是成交额：'
     f'恒等式是「隐含交易收入 = 成交合约数 × 每张平均费率」，'
     f'所以「价」那一段是 CME 向客户收的<b>每张费率</b>，<b>不是</b>标的资产的成交价格，'
     f'也不要与别的页上真正的成交额量价分解并读。'
     f'图上画的是<b>对数分解</b>按总增长重标定后的两块（天然可加、无交叉项，'
     f'两块逐格等于菱形标的总增长）；算术分解的交叉项在本页不是可忽略的余项，'
     f'所以只写进图注、不上图。'
     f'⚠️ 本页这张桥的一格 = <b>一个月</b>（口径与全站其余 decomp 不同，'
     f'那些仍按日历年分桶）—— 跨页不要拿它与别家的分解比大小。'),

]


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
# 抬头是全页曝光最高的一行，所以它只印本页的口径 —— **单月**同比与环比，别的一律不放。
# 这里 2026-09 反复过一次，把裁决留档：改口径时曾在抬头保留一个 12 个月滚动读数当「对照」，
# 理由是 CONTRACT §6.1 第 3 条要求印代价。裁掉了，理由有两条，都比那条强：
#   ① 所有者的原话就是「不要给我搞 12 月滚动合计同比」，而抬头正是曝光最高的那一行；
#   ② 抬头**没有图注**。图上的每一条金线旁边都有 yoy_cal_zh() 那段话说明「滚动那一侧只是
#      对照、页上不画」，抬头没有地方放这句话 —— 一个孤零零的滚动数字，读者只会把它
#      当成本页的口径读数，那恰好是这次改口径要消灭的东西。
# 「印代价」的职责由每张图的图注 + 页尾口径条承担，不由抬头兼。

# 跨图断言的兜底与回填在 4.9 节（所有 exhibit 都画完的地方），不在这里 ——
# 断言与事实必须只有一个来源，兜底与印给读者的那句话也就只能共用同一份名单。

# 127 点的图放不进半栏卡片 —— 逐张按 charts.js 的量边距算式判通栏与抽稀。
# 哪几张真被它改了版式（并因此在图注末尾留下实测 px），只有跑完才知道 —— 所以先记下
# 跑之前的图注，跑完做差集，再回填页尾那句导航。
_notes_before = [(e.get('note') or '') for e in ex]
mrwin.layout_all(ex)
_MRWIN_PX = sorted(e['n'] for e, was in zip(ex, _notes_before)
                   if (e.get('note') or '') != was)

# ── 回填②：页尾那句「实测 px 写在哪几张的图注里」──────────────────────
# 上一版写的是「升了通栏的那些图，图注末尾写着实测的 px 数」，读者会当成「凡通栏皆有
# px」——而热力矩阵与全历史图是源码里手写 'full': True、mrwin.layout() 对它们直接返回
# 空串，三张通栏图一个 px 都没有。这里改成现读差集：印出去的名单就是真被 mrwin 改过、
# 因而带实测 px 的那几张，读者数得清、也不会随下个月加图而变假。
_NAV_MRWIN_PX = '⟨nav:mrwin-px⟩'
# 只声称「实测的每期宽度（px）」——不要顺手加上「抽稀步长」：mrwin 判通栏与判抽稀是
# 两件独立的事，被判通栏却没有抽稀的图，图注里就没有步长那半句（本页历史上出现过）。
# 句子只能声称逐张都成立的那一项，下面对一遍。
_px_missing = [n for n in _MRWIN_PX if 'px' not in (_EX_BY_N[n].get('note') or '')]
if _px_missing:
    raise SystemExit(f'页尾说 mrwin 把实测 px 写进了这几张的图注，但 Exhibit {_px_missing} '
                     f'的图注里没有 px —— 要么 mrwin 改了输出，要么这句话该重写。')
_mrwin_txt = (f'它实测的每期宽度（px）写在 {_exnums(_MRWIN_PX)} 这 '
              f'{len(_MRWIN_PX)} 张的图注末尾'
              if _MRWIN_PX else
              '本次构建它一张图的版式都没有改动，所以没有任何一条图注带实测 px')
# 数的是**出现次数**不是「有几条 notes 命中」——同一条注里抄两遍，按条数数是数不出来的。
_mrwin_hit = sum(_t.count(_NAV_MRWIN_PX) for _t in NOTES)
if _mrwin_hit != 1:
    raise SystemExit(f'占位符 {_NAV_MRWIN_PX} 在页尾 notes 里出现 {_mrwin_hit} 次'
                     f'（应当正好 1 次）—— 这句导航要么没兑现、要么被抄成了两份。')
NOTES[:] = [_t.replace(_NAV_MRWIN_PX, _mrwin_txt) for _t in NOTES]

# ── 兜底③：汇总表注末句必须点到每一个「不是披露原列」的行 ────────────────
# 三方对一遍：_sum_provenance() 判出来的来源、真正印进表里的行、印进表注的字。
SUMMARY = summary()
_sum_shown = [r['label'] for r in SUMMARY['rows'] if r.get('kind') != 'group']
_sum_named = [lab for lab, *_ in SUM_UNIT] + [lab for lab, _ in SUM_DERIVED]
_sum_uncovered = [lab for lab in _sum_shown
                  if lab not in SUM_RAW and lab not in _sum_named]
_sum_unnamed = [lab for lab in _sum_named if f'「{lab}」' not in SUMMARY['note']]
if _sum_uncovered or _sum_unnamed:
    raise SystemExit(
        f'汇总表注与表本身对不上：{_sum_uncovered} 这几行没有被来源判定覆盖；'
        f'{_sum_unnamed} 不是披露原列，表注里却没有点名。表注末句只能由 '
        f'_sum_src_txt() 生成 —— 手写一句「全部为官方披露值」正是上一轮翻车的地方。')

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
                 f'{pct(_adv_mm)} m/m）· '
                 f'总成交 {df["total_vol_mn"][CUR]:,.0f}mn 张（单月 {pct(_vol_yy)} y/y，'
                 f'{pct(_vol_mm)} m/m，交易日贡献 {pp(_dc)}）· '
                 f'近 12 个月成交 {float(df["ttm_vol_mn"][CUR]):,.0f}mn 张 · '
                 f'月末未平仓 {df["oi_total_mn"][CUR]:,.1f}mn 张'
                 f'（单月 {pct(_oi_yy)} y/y）· 利率品种占 ADV {_share:.0f}% · '
                 f'隐含交易收入 ${df["implied_txn_rev_usdmn"][CUR]:,.0f}mn'),
    # headline 之下、Exhibit 1 之上的 ~300 字解读。职责与 headline 互补：
    # 那一行给读数，这一段给「读数该怎么读」。见 compose_brief 的 docstring。
    'brief': BRIEF,
    # 名词释义：页面把它排在所有 exhibit 之前。选词判断与「有意不收哪些词」写在
    # 上面 GLOSSARY 那段注释里；版式与护栏在 build/glossary.py（全站一份）。
    'glossary': gloss.render(GLOSSARY, where='cme glossary'),
    # hub 上只有一行的位置，口径与页面一致（单月）；理由同抬头那一段，不放滚动对照。
    'hub_line': (f'ADV {df["adv_mn"][CUR]:,.1f}mn 张/日，单月 {pct(_adv_yy)} y/y、'
                 f'{pct(_adv_mm)} m/m'),
    'source': SRC,
    # 页级默认轴 = 时序图的统一窗口（2016-01 起）。每张 exhibit 现在都自带 xlabels，
    # 这一项只剩兜底作用；但它必须与图的窗口同长，否则日后有人新增一张不写 xlabels 的图，
    # 就会拿到一根 13 格的轴去画 127 个点（引擎按 xlabels.length 循环，多出来的点画不出来
    # 却仍参与量程 —— 图被一个看不见的点压扁，不报错）。
    'xlabels': XL25,
    'summary': SUMMARY,
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

# ── 兜底④：占位符一条都不许漏进 data/cme.js ────────────────────────────
# 上面三处回填各自数过自己的占位符，但那都是「按名字找」——名字打错一个字，
# 三道计数全都若无其事地通过，占位符就直接印到读者眼前。这里对**整个 payload**
# 扫一遍前缀，谁漏了都拦得住，将来新增第四个占位符也不用记得再加一道闸门。
_blob = json.dumps(payload, ensure_ascii=False)
if '⟨nav:' in _blob:
    _i = _blob.index('⟨nav:')
    raise SystemExit(f'payload 里还留着没回填的占位符：{_blob[_i:_i + 48]}… '
                     f'—— 占位符是空头支票，兑不出来就不能上线。')

# ── 兜底⑤：抬头里「近 12 个月成交」那一项必须是**纯水平值**，不许带增速 ──────
# 它是抬头上唯一一个 12 个月口径的读数，留着是因为「过去一年一共成交了多少张」是一句
# 关于**规模**的事实，读者不会拿它和任何同比读数比高低，也不是页面所有者点名反对的
# 那种「12 个月滚动合计同比」。但这两件事只隔着一个括号：哪天有人顺手给它补一个
# 「（+X% y/y）」，抬头就又有了一条滚动口径的增速 —— 而抬头**没有图注**可以说明
# 那是什么（2026-09 抬头那个「对照用」的滚动读数正是因此被裁掉的）。
# 所以把「这一项不许出现百分号 / 同比措辞」钉在构建期，而不是靠下一个人记得。
_HL_SEP = '·'
_hl_ttm = [seg for seg in payload['headline'].split(_HL_SEP) if '近 12 个月' in seg]
_hl_bad = [k for k in ('%', '％', 'y/y', '同比', 'pp') if any(k in seg for seg in _hl_ttm)]
if len(_hl_ttm) != 1 or _hl_bad:
    raise SystemExit(
        f'抬头里「近 12 个月成交」应当正好出现 1 项、且是纯水平值，现在命中 '
        f'{len(_hl_ttm)} 项、其中带着 {_hl_bad}：{_hl_ttm}。'
        f'抬头只印本页的口径（单月同比与环比）加绝对规模 —— 给这一项配增速，'
        f'等于把 12 个月滚动口径请回全页曝光最高的那一行，而那里没有图注解释它。')


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
