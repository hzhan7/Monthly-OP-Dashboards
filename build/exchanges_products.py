# -*- coding: utf-8 -*-
"""标的轴横截面页（利率 / 股指 / 单股与 ETF 期权 / 能源 / 农产品 / FX 即期 ECN）
→ 写出 data/exchanges-products.js。

━━━━━━━━━━━━━ 一、这一页问的是另一个问题 ━━━━━━━━━━━━━
三张地理轴的页（exchanges-na / -eu / -apac）问的是「同一个法域里谁抢了谁」：
成员争的是同一批订单流，所以「占比」这个词在那里是有内容的。

**本页问的是两件地理轴问不出来的事：**
  ① **同一类标的在不同法域，周期是不是错位的。**
     利率是最典型的一条：CME 是美元曲线（SOFR / Treasuries）、Eurex 是欧元曲线、
     MX 是加元曲线 —— 它们不争同一批订单，但它们的成交量各自随本币的货币政策周期走。
     把三条放进同一根轴（定基名义额让这件事第一次成立），错位就直接看得见。
  ② **谁的独占产品真的独占。**「独占」在本页有一个可计算的定义：
     该池头名成员的池内占比，以及它自基期以来的 pp 变化。
     占比高且不掉 = 这门生意确实没人抢得动；占比高但在掉 = 独占正在被侵蚀。

**推论：本页的占比不是竞争胜负。** 各池成员的标的几乎不重合（CME 的玉米/大豆复合体
与 MATIF 的欧洲小麦不是同一批合约），所以占比只能读作「这一类标的的名义额构成」。
唯一一对真正争同一批订单流的是能源池里的 **Brent（ICE）vs WTI（CME）**，
而那一对还受制于本页第三节说的口径缩水。

━━━━━━━━━━━━━ 二、口径：主口径是定基名义额 ━━━━━━━━━━━━━
    定基名义额 = 张数 × 乘数 × **基期(2019-01)价格**，汇率同样锁 2019-01
价格项与汇率项都是常数 ⇒ 每条序列的**增长率与它的张数增长率完全相同**，
名义额只改变成员之间与产品之间的权重。于是增长图里没有标的涨跌、
份额图里没有汇率漂移，跨交易所跨币种跨资产类的量第一次可以放进同一根轴。
恒等式不是口号：本页 `main()` 把「单腿成员的名义额同比 − 张数同比」逐月算一遍，
最大偏差打在自检行上（应当是浮点舍入量级）。

**本页没有一个池是 `share='true'`** —— 全仓只有北美两池 + fn_monopoly 有官方行业分母，
那三个都在别的页。⚠️ 但**不许**把这句话收紧成「本页所有池的 share 档次都是 `pool`」：
本页在场的池里还有 `share='none'` 的一档（连池内占比都不画，页尾另有一整条在讲），
写成「都是 pool」会被同一页当场证伪。⚠️ 这里也**不许抄一份档次名单**：
逐档有几个、分别是谁，由 `_share_tier_txt()` 现读 `POOL_STATE` 算出，散文里一个都不写死。
⇒ **本页不出现「市场份额」这个说法**；页面上凡出现这四个字都是在否定它。
**画占比的**那几张图，图注逐张点名分母是哪几家，且逐字带上该池自己的 `share_caveat`。

━━━━━━━━━━━━━ 三、两处必须落到图注上的口径缩水 ━━━━━━━━━━━━━
1. **能源池的 ICE 只含 Brent 原油（期货 + 期权），不是 ICE 的全部能源。**
   这是 pools.py 的 `scope_note` 强制要求：任何画到这条腿的图，图注必须写明，
   且 ICE 的占比读作**下界**。理由是口径自洽优先于覆盖率 —— ICE 唯一公开、
   不要 reCAPTCHA 的分产品历史表只覆盖 ICE Futures Europe，拿它的品种结构
   去套全球口径的量，偏差方向与大小都不可知。本页除了逐字引用 scope_note，
   还用 `ice.csv` 的 `adv_brent_kcontracts ÷ adv_energy_kcontracts` **当场复算**
   这条腿的覆盖率并印进图注 —— 引用的话与实测的数必须对得上，对不上就是有人改了列。

2. **利率池的 ICE 永久停留在张数口径**（`contracts_only`）。它只进增长图
   （指数化 / 同比），**不进水平值图，也不进任何份额的分子或分母**。
   这不是待补的缺口：即便官方哪天肯拆开短端与中长端，名义额对利率衍生品
   本身就是误导性单位（同名义额下 2 年期与 10 年期的 DV01 差 5 倍以上）。
   ⇒ 本页**不给它补基期常数**，也不为它留 TODO。
   为什么它进增长图一点折扣都不打：定基名义额 = 张数 × 常数，增长率恒等。

━━━━━━━━━━━━━ 四、缺基期常数的成员：留空，不用近似值填 ━━━━━━━━━━━━━
`series/contract_specs.csv` 里 `base_price_local` 还空着的产品，本页**一律不呈现**
用到它的那个成员，并在图注与口径说明里逐个点名「📌 未找到 / 不呈现」。
这与上一节的 `contracts_only` 是两件不同的事，页面上必须分开说：

    「还没测出来」  → 下一个人应该去测（本节，📌）
    「测出来也不该用」→ 下一个人**不应该**去测（上一节 ②，⛔）

不用近似值填的理由是本仓通用的取舍准则：**覆盖率低但无偏 > 覆盖率高但有未知偏差**。
覆盖率低是看得见的缺陷（写在图注上，读者知道自己在看什么）；
拿一个产品的乘数去凑另一个产品，图上一切正常而结论已经错了。

一个成员被拿掉之后，池的成员数会变，本页的占比分母也随之变 —— 所以
**每一张占比图的图注都印当前分母的成员名单与「N 家里有几家可呈现」**，
不写死在文案里，全部由代码算出。

━━━━━━━━━━━━━ 五、跨池对比只放 deflator='base_price' 的池 ━━━━━━━━━━━━━
`fx_spot_ecn` 的源列是成交额（ADNV），拿不到成交笔数 ⇒ 只能锁汇率、锁不了价格
（`deflator='fx_only'`）。它的增长里含着它成交的那些货币对的波动，
与另外几个池「已剔标的价格」的增长**不是同一个东西**。
所以跨池的规模、增长、动量三张图一律**不含它**，它单独一张图并在图注写明原因。
这同样是「宁可少一条线，也不要把两种口径混进一根轴」。

━━━━━━━━━━━━━ 六、同比口径：单月，而且必须说出来 ━━━━━━━━━━━━━
本页的同比一律是**单月同比**（当月 ÷ 去年同月 − 1），算术走 `build/yoy.py` 的
`mom_yoy()` —— 全站唯一实现，本文件不另写一份（CONTRACT §6.1 第 1 条；`fn_index_aum`
那一池是存量，按第 2 条走点对点，落到算术上是同一个式子）。
**页上没有任何一处画 12 个月滚动合计的同比**：滚动口径只作为「换口径的代价」
在动量矩阵的图注里以数字出现（§6.1 第 3 条要求逐图印，统计量一律由
`yoy.caliber_diff()` 出，窗口取矩阵画出来的那几个月；可比月不足
`yoy.MIN_DIAG_MONTHS` 的行照实说量不出来，不硬编数字）。

这一节 2026-09 才补上，补的是一个**只看页面的读者会中招**的缺口：在此之前
subtitle / headline / 图注 / 页尾**一处都没有**说过本页画的是哪种同比，而首页
「横截面」那一排里与本页并排的 `exchanges12` 恰恰是 CONTRACT §6.2 点名**保留
12 个月滚动口径**的页。两页并排、一页明写滚动一页什么都不说，读者默认会读成同口径。
所以口径声明现在落在读者看得到的四处：subtitle、汇总表的 note、动量矩阵的
title / legend / note、页尾「口径与方法说明」；「与 exchanges12 不可跨页比高低」
这一句同时出现在 subtitle、动量矩阵图注与页尾那条里。

⚠️ **换实现时逐点复算过，一个数都没变**：本页 47 条序列（7 个池的合计、各成员的
定基名义额与张数原列、矩阵那 13 行）拿 `pct_change(12) * 100` 与
`mom_yoy(…, FLOW)` 各算一遍，max|差| = 0.0、NaN 位置逐点一致；写出的热力矩阵
逐格相同。本页的序列里既没有零基期、也没有基期变号的月份，两者掩码上的差异用不上。
换过来是为了「同比怎么算」这个判断只留一处，不是为了改数。

数据源（只读 series/*.csv）：
  series/cme.csv  db1.csv  tmx.csv  enx.csv  cboe.csv  ice.csv  asx.csv   各家月度成交
  series/contract_specs.csv   乘数与 2019-01 基期价格（唯一权威）
  series/fx.csv               ECB 月均 / 月末汇率
池定义（成员、换算链、share 档次、caveat）的唯一真值是 build/pools.py，
本文件**不重复声明任何一条**，全部现读现用。

用法: python3 build/exchanges_products.py   （可重复跑，除首行构建日期外逐字节相同）
"""
import os
import sys

import numpy as np
import pandas as pd

import axisfmt
import glossary as gloss          # 名词释义的版式层与护栏，全站共用
import payload_guard
import pctile        # 3Y %ile 的唯一实现，全站共用
import yoy as YOY    # 同比口径的**唯一实现**（build/yoy.py）：单月同比与口径对比诊断一律走它。
                     # 别名大写只是为了不与本文件里 `_st['yoy']` 这个键名读串
                     # （build/exchanges_apac.py 用的是同一个别名）。

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SERIES = os.path.join(ROOT, 'series')
# 目录名 = data 文件名 = payload 的 ticker，三者逐字相同（页面壳引 `../data/exchanges-products.js`）。
# 模块名只能用下划线，输出物必须用连字符。
TICKER = 'exchanges-products'
OUT = os.path.join(ROOT, 'data', f'{TICKER}.js')

SRC = ('Source: CME, Eurex (Deutsche Börse), Montréal Exchange (TMX), Euronext, Cboe, ICE, ASX '
       'monthly volume disclosures; contract specs from each exchange rulebook; '
       'FX from ECB SDMX; format after Goldman Sachs GIR')

BASE_MONTH = '2019-01'   # 全仓基期，与 build/notional.py 的 BASE_MONTH 一致（加载时校验）
MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
          'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

MIN_SHARE_MEMBERS = 2    # 少于两家可呈现成员的池不成其为横截面，整池不画
MIN_POOL_MONTHS = 36     # 一个池的共同窗口短于 36 个月不画。**绑定条件是 3Y 分位**
#                          （近 36 个月百分位），不是同比：单月同比只要 13 期就有第一个
#                          点（本页的同比一律走 yoy.mom_yoy(…, yoy.FLOW)，从来不是滚动合计）。
#                          原注写「同比 + 分位都要」，读起来像是同比也要 36 个月 ——
#                          不对，而且 2026-09 全站改单月之后更不对。门槛保持 36 不动：
#                          它由分位定，与本轮口径改动无关。
MIN_POOLS = 3            # 全页可画的池少于这个数就不发（一两个池不构成「标的轴」）
MAX_POOL_LAG = 2         # 某池的最新月比最快的池落后超过这么多个月 → 该池出局，
#                          不让一个停更的池把整页的共同最新月拖回去
HEAT_MONTHS = 24         # y/y 动量矩阵的列数
LINE_H_ENDLABEL = 360    # 开 end_label 的长历史线图的最小高度。
                         # ⚠️ 原注写「理由见 build/exchanges.py 同名常量」——
                         # **本仓没有 build/exchanges.py 这个文件**（本轮 grep 实测）。
                         # 判据在 docs/CHART_KINDS.md §3.9；同名常量的现存副本在
                         # build/exchanges_eu.py（exchanges_apac.py 里叫 LINE_H）。
TBL_MONTHS = 13
CAT_ROT = 0              # 类别轴（x 是池名 / 公司名）一律不旋转


def mlab(p):
    """Period('2026-06') → 'Jun-26'。"""
    return f'{MONTHS[p.month - 1]}-{p.year % 100:02d}'


def zh_month(p):
    return f'{p.year} 年 {p.month} 月'


def _z(v, dec):
    """把 -0.0 这类「四舍五入后其实是零」的值归零，否则会印出 '-0.0pp'。"""
    v = round(float(v), dec)
    return 0.0 if v == 0 else v


def ok(v):
    try:
        return v is not None and np.isfinite(float(v))
    except (TypeError, ValueError):
        return False


def num(v, dec=0):
    return f'{float(v):,.{dec}f}' if ok(v) else '—'


def pct(v, dec=1):
    """水平值的变化一律用百分比。"""
    return f'{_z(v, dec):+,.{dec}f}%' if ok(v) else '—'


def pp(v, dec=1):
    """比率类指标的变化一律 pp/bp（契约 §2：绝对值不足 1pp 时写 bp）。"""
    if not ok(v):
        return '—'
    if abs(_z(v, dec)) < 1:
        return f'{_z(v * 100, 0):+,.0f}bp'
    return f'{_z(v, dec):+.{dec}f}pp'


def L(a):
    """序列 → JSON 安全的 float 列表（NaN → None，线在缺口处断开而不是直连）。"""
    return [None if not ok(v) else round(float(v), 6) for v in a]


def skip(msg):
    """未达发布门槛 —— 打印原因，**退出码 0**。横截面页只在成员齐了之后生成。"""
    print(f'{TICKER}: 跳过，未达发布门槛 —— {msg}')
    print('monthly_run 下次例行跑会自动重试；这里不抛异常，免得日志天天多一条假 FAIL。')
    sys.exit(0)


MD_ODD = []


def md(s):
    """pools.py 的文案用 Markdown 的 `**` 加粗，而 note / notes 走 innerHTML（不解析 Markdown）。

    转成 `<b>`；换行折成空格（innerHTML 里换行只是空白）。
    标记数为奇数时整段去掉标记并记进 MD_ODD 打在自检行上 —— 悄悄留下四个星号
    是 verify_pages 的一条 WARN，而它在页面上表现为正文里凭空多出 `**`。
    """
    parts = str(s).replace('\n', ' ').split('**')
    if len(parts) % 2 == 0:
        MD_ODD.append(str(s)[:48])
        return ''.join(parts)
    return ''.join(x if i % 2 == 0 else f'<b>{x}</b>' for i, x in enumerate(parts))


def load_source_dates():
    """按路径加载仓库根的 source_dates.py（裸 import 不行：sys.path 上只有 build/）。"""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        'source_dates', os.path.join(ROOT, 'source_dates.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ────────────────────────── 1. 池定义、换算库与规格表 ──────────────────────────
# 任何一样没就绪都算「未达门槛」，一律 skip(0)，不抛异常。
try:
    import pools
    import notional
except Exception as e:                                    # noqa: BLE001
    skip(f'build/pools.py 或 build/notional.py 加载失败（{type(e).__name__}: {e}）')

try:
    SPECS = notional.load_specs(SERIES)
    FX = notional.load_fx(SERIES)
except Exception as e:                                    # noqa: BLE001
    skip(f'规格表 / 汇率表加载失败（{type(e).__name__}: {e}）')

if notional.BASE_MONTH != BASE_MONTH:
    skip(f'基期不一致：本页写死 {BASE_MONTH}，build/notional.py 是 {notional.BASE_MONTH} —— '
         '基期一变，所有定基序列的权重都变，必须两处同时改')

BASE_P = pd.Period(BASE_MONTH, freq='M')

# 本页要画哪些池，**问 pools.py 要**，不在这里另抄一份名单。
# 抄一份的后果是：pools.py 哪天把某个池挪走或改名，这里仍然照旧画，
# 而两处不一致在页面上完全看不出来（只是多了/少了一段）。
PAGE_POOLS = pools.pools_on(TICKER)
if not PAGE_POOLS:
    skip(f'build/pools.py 里没有 page={TICKER!r} 的池')

# 池的短名，只用于类别轴与矩阵行标签（长名会把 x 轴挤爆）。
# 查不到就回落到 pools.py 的 zh —— 回落只是标签变长，不会画错。
POOL_SHORT = {
    'rates': '利率', 'equity_index': '股指', 'single_stock_etf_opt': '单股/ETF',
    'energy': '能源', 'ags': '农产品', 'fx_futures': 'FX 期货', 'fx_spot_ecn': 'FX 即期',
    'fn_index_aum': '指数 AUM',
}


def pshort(p):
    return POOL_SHORT.get(p['id'], p['zh'])


def mshort(m):
    """成员显示名去掉括号里的口径注解：'CME（美元）' → 'CME'。"""
    return m['disp'].split('（')[0].strip()


# ────────────────────────── 2. 读数据 ──────────────────────────
_CSV = {}


def read_csv(name):
    """series/<name> → 连续周期索引的 DataFrame（读不到返回 None）。

    reindex 成连续期：原始文件中间缺月时，单月同比的 `shift(12)`（`yoy.mom_yoy` 内部）
    会按**位置**移 12 行，算出来的「同比」其实跨了 13 个月而完全看不出来。
    """
    if name in _CSV:
        return _CSV[name]
    p = os.path.join(SERIES, name)
    if not os.path.exists(p):
        _CSV[name] = None
        return None
    d = pd.read_csv(p)
    if 'month' not in d.columns:
        _CSV[name] = None
        return None
    d['month'] = pd.PeriodIndex(d['month'], freq='M')
    d = d.set_index('month').sort_index().apply(pd.to_numeric, errors='coerce')
    _CSV[name] = d.reindex(pd.period_range(d.index[0], d.index[-1], freq='M'))
    return _CSV[name]


def get_col(csv_name, col):
    """notional.resolve_chain 的取数回调：{月份字符串: 值}。取不到就抛（换算链必须断在这里）。"""
    d = read_csv(csv_name)
    if d is None:
        raise notional.ChainError(f'series/{csv_name} 读不到')
    if col not in d.columns:
        raise notional.ChainError(f'series/{csv_name} 没有列 {col}')
    return {str(p): (None if pd.isna(v) else float(v)) for p, v in d[col].items()}


def to_series(mapping):
    """{'YYYY-MM': v} → 按月升序、连续期的 pandas Series。"""
    s = pd.Series({pd.Period(k, freq='M'): (np.nan if v is None else float(v))
                   for k, v in mapping.items()})
    s = s.sort_index()
    return s.reindex(pd.period_range(s.index[0], s.index[-1], freq='M'))


def member_cols(m):
    """这个成员**自己**要读的 {csv: {列}}。

    刻意不用 pools.cols_used(p)：那是整池的并集，同一张 csv 上别家成员的列
    会被算到这个成员头上 —— 一个成员因为另一个成员的列缺失而被判「不可呈现」，
    而报出来的原因指向一条它根本用不到的列。
    """
    need = {}
    for leg in (m.get('chain') or []):
        c = leg.get('csv') or m['csv']
        need.setdefault(c, set()).add(leg['col'])
        pd_spec = leg.get('per_day')
        if pd_spec:
            dc = pd_spec.get('csv') or c
            need.setdefault(dc, set()).add(pd_spec['col'])
            if pd_spec.get('div_col'):
                need[dc].add(pd_spec['div_col'])
    for c in (m.get('contracts_col') or []):
        need.setdefault(m['csv'], set()).add(c)
    return need


def member_block(m):
    """这个成员为什么画不了 —— 画得了返回 None。

    两类原因必须分开说，页面上也分开印：
      · 📌 基期常数还没实测入库 → 下一个人应该去测；
      · CSV / 列不在 → fetch 侧还没落地。
    `contracts_only` 的成员**不查基期常数**：它按设计永远不会有，
    照 pending 处理会把整池判死（pools.contracts_only_products 的存在理由）。
    """
    for csv_name, cols in member_cols(m).items():
        d = read_csv(csv_name)
        if d is None:
            return f'series/{csv_name} 还没有'
        miss = sorted(c for c in cols if c not in d.columns)
        if miss:
            return f'series/{csv_name} 缺列 {", ".join(miss)}'
    if not m.get('contracts_only'):
        pend = notional.pending_products(
            [leg['product'] for leg in (m.get('chain') or [])], SPECS)
        if pend:
            return '📌 未找到基期常数：' + '、'.join(f'{pid}（{why}）' for pid, why in pend)
    return None


def base_bn(m, p):
    """成员的定基名义额日均，单位 USD bn/day。汇率档次由池的 flow 机械推出。"""
    s = notional.resolve_chain(get_col, m['chain'], m['csv'], SPECS, FX,
                               'base', None, pools.fx_basis(p))
    return to_series(s) / 1e9


def contracts_kper_day(m):
    """成员的**张数**日均（千张/日）—— 只给 contracts_only 成员用，只进增长图。

    走 notional.apply_unit 而不是自己乘除：unit_scale 的语义（源列写法 → 张）
    只有那一处定义，在这里再写一次就会有一天两处不一致。
    """
    legs = []
    for leg in m['chain']:
        if leg.get('per_day'):
            raise notional.ChainError(
                f'{m["key"]} 的张数腿带 per_day，本函数没实现除交易日 —— '
                f'真出现了要在这里补，不能默默按日均处理')
        raw = get_col(leg.get('csv') or m['csv'], leg['col'])
        legs.append(notional.apply_unit(raw, leg['unit_scale']))
    return to_series(notional.add_series(*legs)) / 1e3


# ────────────────────────── 3. 逐池解析成员 ──────────────────────────
POOL_STATE = []      # 可画的池
POOL_SKIPPED = []    # (池, 原因) —— 整池画不了，页面上要说出来

for _p in PAGE_POOLS:
    # share 档次决定这个池在本页长什么样，两条完全不同的轨道：
    #   'true' / 'pool' → 有分母，画池内占比（本页全是 'pool'，所以只能叫池内占比）
    #   'none'          → **任何形式的占比都不许画**，只画水平值与增长
    # 后者也正是 fn_index_aum（挂钩 ETF 的 AUM 存量）在本页的形态：
    # 它的 in_share 两家都是 False，按占比池的规则读会被判成「一家成员都没有」。
    _has_share = _p['share'] in ('true', 'pool')
    _share, _growth, _dropped = [], [], []
    for _m in _p['members']:
        _why = member_block(_m)
        if _why:
            _dropped.append((_m, _why))
            continue
        try:
            if _m.get('contracts_only'):
                _growth.append((_m, contracts_kper_day(_m)))
            elif _m.get('in_share') or not _has_share:
                _share.append((_m, base_bn(_m, _p)))
            else:
                # in_share=False 且池有分母：这一家只做量级对照，不进分子（如 ags 的 MIAX）。
                # 本页的占比图按分母成员画，所以它没有位置 —— 记进 dropped 把理由说出来。
                _dropped.append((_m, '池定义里 in_share=False（只做量级对照，不进分子）'))
        except Exception as _e:                            # noqa: BLE001
            _dropped.append((_m, f'换算链执行失败（{type(_e).__name__}: {_e}）'))
    _need = MIN_SHARE_MEMBERS if _has_share else 1
    if len(_share) < _need:
        POOL_SKIPPED.append((_p, f'可呈现的成员只有 {len(_share)} 家（门槛 {_need} 家'
                                 + ('，不足两家不成其为横截面' if _has_share else '') + '）：'
                             + '；'.join(f'{mshort(m)} — {w}' for m, w in _dropped)))
        continue
    POOL_STATE.append({'p': _p, 'has_share': _has_share,
                       'share': _share, 'growth': _growth, 'dropped': _dropped})

if len(POOL_STATE) < MIN_POOLS:
    skip(f'可画的池只有 {len(POOL_STATE)} 个（门槛 {MIN_POOLS}）；'
         + ' | '.join(f'{s[0]["id"]}: {s[1]}' for s in POOL_SKIPPED))

# ── 池合计与池窗口 ──────────────────────────────────────────────────────
# 池合计 = 可呈现成员之和，**任一家缺值该月即缺**（不拿 0 顶替：
# 一家没到就当 0 加进去，图上是一次凭空的下跌，而且没有任何标记）。
# ⚠ share='none' 的池同样算这个合计，但它**只用来定窗口**，
#   既不进汇总表、也不做任何占比的分母 —— why_none 说得很清楚：
#   两家之和的占比会被读成「这个行业二分天下」。
for _st in POOL_STATE:
    _df = pd.DataFrame({m['key']: s for m, s in _st['share']})
    _tot = _df.sum(axis=1, min_count=len(_st['share']))
    _win = _tot.dropna()
    _st['tot_full'] = _tot
    _st['first'] = _win.index[0] if len(_win) else None
    _st['last'] = _win.index[-1] if len(_win) else None
    _st['holes'] = (0 if not len(_win) else
                    (_win.index[-1] - _win.index[0]).n + 1 - len(_win))

_alive = [s for s in POOL_STATE if s['last'] is not None]
if not _alive:
    skip('每一个池的合计都是空的 —— 成员窗口没有交集')

_fastest = max(s['last'] for s in _alive)
_kept = []
for _st in _alive:
    _lag = (_fastest - _st['last']).n
    if _lag > MAX_POOL_LAG:
        POOL_SKIPPED.append((_st['p'], f'该池最新月 {_st["last"]} 比最快的池 {_fastest} '
                                       f'落后 {_lag} 个月（上限 {MAX_POOL_LAG}）—— '
                                       f'留在页里会把全页的共同最新月一起拖回去'))
        continue
    _kept.append(_st)
POOL_STATE = _kept

if len(POOL_STATE) < MIN_POOLS:
    skip(f'剔掉落后太多的池之后只剩 {len(POOL_STATE)} 个（门槛 {MIN_POOLS}）')

# 全页共同最新月 = 各池最新月里最慢的那个。跑在前面的池，其最新月不进本页任何一张图。
LATEST = min(s['last'] for s in POOL_STATE)
START = min(s['first'] for s in POOL_STATE)
IDX = pd.period_range(START, LATEST, freq='M')
XL_LONG = [mlab(p) for p in IDX]

_short_pools = [pshort(s['p']) for s in POOL_STATE if s['last'] == LATEST]
_ahead_pools = [(pshort(s['p']), s['last']) for s in POOL_STATE if s['last'] > LATEST]

for _st in POOL_STATE:
    _st['idx'] = pd.period_range(max(_st['first'], START), LATEST, freq='M')
    _st['tot'] = _st['tot_full'].reindex(_st['idx'])
    _st['months'] = int(_st['tot'].notna().sum())

_thin = [s for s in POOL_STATE if s['months'] < MIN_POOL_MONTHS]
for _st in _thin:
    POOL_SKIPPED.append((_st['p'], f'共同窗口只有 {_st["months"]} 个月'
                                   f'（门槛 {MIN_POOL_MONTHS}）'))
POOL_STATE = [s for s in POOL_STATE if s['months'] >= MIN_POOL_MONTHS]
if len(POOL_STATE) < MIN_POOLS:
    skip(f'剔掉窗口太短的池之后只剩 {len(POOL_STATE)} 个（门槛 {MIN_POOLS}）')

if BASE_P < START or BASE_P > LATEST:
    skip(f'基期 {BASE_MONTH} 不在全页共同窗口 {START}–{LATEST} 内，指数化图无从画起')

# ── 派生：占比、同比、指数化 ────────────────────────────────────────────
for _st in POOL_STATE:
    _st['ser'] = {m['key']: s.reindex(_st['idx']) for m, s in _st['share']}
    _st['gser'] = {m['key']: s.reindex(_st['idx']) for m, s in _st['growth']}
    _st['share_pct'] = ({k: v / _st['tot'] * 100 for k, v in _st['ser'].items()}
                        if _st['has_share'] else {})
    # 单月同比（当月 ÷ 去年同月 − 1）。CONTRACT §6.1 第 1 条：流量走 yoy.mom_yoy(…, FLOW)，
    # 全站只有 build/yoy.py 这一份实现。本页此前写的是 `pct_change(12) * 100`，
    # 算术相同（2026-09 换过来时把本页 47 条序列逐点复算过，max|diff| = 0.0、NaN 位置一致），
    # 换过来是为了让「近零基数 / 基期为零 / 基期变号」这几种掩码与全站同一套。
    _st['yoy'] = YOY.mom_yoy(_st['tot'], YOY.FLOW).reindex(_st['idx'])
    _b = float(_st['tot'].get(BASE_P, np.nan))
    if not ok(_b) or _b == 0:
        skip(f'池 {_st["p"]["id"]} 在基期 {BASE_MONTH} 没有有效合计，指数化算不了')
    _st['index'] = _st['tot'] / _b * 100

# 份额自检：每池各月占比之和必须是 100（分母就是这几家之和，恒等式，不成立说明代码写错了）
SHARE_SUM_MAXGAP = 0.0
for _st in POOL_STATE:
    if not _st['has_share']:
        continue
    _s = sum(_st['share_pct'].values())
    _g = float((_s.dropna() - 100).abs().max()) if _s.notna().any() else 0.0
    SHARE_SUM_MAXGAP = max(SHARE_SUM_MAXGAP, _g)
if SHARE_SUM_MAXGAP > 1e-6:
    skip(f'池内占比之和偏离 100% 达 {SHARE_SUM_MAXGAP:.3e}pp —— 分母算错了，不发')

# ── 恒等式自检：单腿成员的「定基名义额同比」必须逐月等于「张数同比」──────────
# 这是整套口径的前提（价格项是常数 ⇒ 增长率不变）。只对**单条正腿且有张数原列**的
# 成员成立：多腿成员各腿常数不同，合计的增长率本来就不等于任一列的增长率。
IDENT_ROWS, IDENT_MAX = [], 0.0
for _st in POOL_STATE:
    for _m, _s in _st['share']:
        _legs = [lg for lg in _m['chain'] if lg.get('sign', 1) > 0]
        if len(_m['chain']) != 1 or len(_legs) != 1 or not _m.get('contracts_col'):
            continue
        if _legs[0]['src'] != 'contracts' or len(_m['contracts_col']) != 1:
            continue
        _raw = to_series(get_col(_m['csv'], _m['contracts_col'][0])).reindex(_st['idx'])
        _a = YOY.mom_yoy(_s.reindex(_st['idx']), YOY.FLOW).dropna()
        _b2 = YOY.mom_yoy(_raw, YOY.FLOW).dropna()
        _both = _a.index.intersection(_b2.index)
        if not len(_both):
            continue
        _gap = float((_a[_both] - _b2[_both]).abs().max())
        IDENT_ROWS.append((f'{pshort(_st["p"])}·{mshort(_m)}', len(_both), _gap))
        IDENT_MAX = max(IDENT_MAX, _gap)

# ── 能源池 ICE 覆盖率：当场复算，不照抄 scope_note 里的数 ────────────────
ICE_COV = None
_energy = next((s for s in POOL_STATE if s['p']['id'] == 'energy'), None)
if _energy is not None:
    _icem = next((m for m, _ in _energy['share'] if m['key'] == 'ice'), None)
    _iced = read_csv('ice.csv')
    if _icem is not None and _iced is not None:
        _num_c = _icem['chain'][0]['col']
        _den_c = (_icem.get('crosscheck_col') or [None])[0]
        if _den_c and _num_c in _iced.columns and _den_c in _iced.columns:
            _r = (_iced[_num_c] / _iced[_den_c] * 100).reindex(_energy['idx']).dropna()
            if len(_r):
                ICE_COV = {'base': float(_r.get(BASE_P, np.nan)), 'med': float(_r.median()),
                           'min': float(_r.min()), 'max': float(_r.max()), 'n': int(len(_r)),
                           'num': _num_c, 'den': _den_c}

# ────────────────────────── 4. 分池：定基口径 vs 只锁汇率 ──────────────────────────
# 跨池的规模 / 增长 / 动量三张图只放 deflator='base_price' 的池。
# fx_only 的池（源列是成交额，价格剔不掉）与它们**不是同一个东西**：
# 前者的增长里没有标的涨跌，后者有。混进同一根轴，两种增长会被读成可比的。
# 同轴的第二个前提是 flow 也一样：per_day 是流量（USD bn/日），stock 是存量（USD bn）。
# 把 AUM 存量和日均成交量画进同一根轴，单位后缀只差三个字，读者一定会读成同一件事。
BASE_POOLS = [s for s in POOL_STATE
              if s['p']['deflator'] == 'base_price' and s['p']['flow'] == 'per_day']
OTHER_POOLS = [s for s in POOL_STATE if s not in BASE_POOLS]
FXONLY_POOLS = [s for s in OTHER_POOLS if s['p']['deflator'] != 'base_price']
STOCK_POOLS = [s for s in OTHER_POOLS if s['p']['flow'] == 'stock']

if len(BASE_POOLS) < MIN_POOLS:
    skip(f'定基口径（deflator=base_price）的池只有 {len(BASE_POOLS)} 个（门槛 {MIN_POOLS}）—— '
         '跨池对比图放不了 fx_only 的池，页面立不住')

# 跨池图的一池一色。数据色只有 6 个，超编就没法靠颜色分辨（引擎会静默重色）。
CROSS_PALETTE = ['NAVY', 'MBLUE', 'GOLD', 'GREEN', 'GRAY', 'BLUE']
if len(BASE_POOLS) > len(CROSS_PALETTE):
    skip(f'定基口径的池有 {len(BASE_POOLS)} 个，数据色只有 {len(CROSS_PALETTE)} 个 —— '
         '跨池折线图必然重色，该换 heat_matrix 再发')
POOL_COLOR = {s['p']['id']: CROSS_PALETTE[i] for i, s in enumerate(BASE_POOLS)}

CUR, PRV, YAG = LATEST, LATEST - 1, LATEST - 12

# ────────────────────────── 5. 通用文案块 ──────────────────────────
NO_MKT_SHARE = (
    '<b>本页的占比一律是「池内占比」，不是市场份额</b> —— 分母是本池成员之和，'
    '不是这一类标的的行业总量；页面上凡出现「市场份额」四个字都是在否定它。'
    '各池成员的标的几乎不重合（各自本土的指数、各自的曲线、各自的作物），'
    '所以占比读作「这一类标的的名义额构成」，不是「谁抢了谁的单」。')

BASE_UNIT_TXT = (
    f'<b>主口径 = 定基名义额</b> = 张数 × 乘数 × 锁死的 {mlab(BASE_P)} 基期价格，'
    f'汇率同锁 {mlab(BASE_P)}（USD bn/日）。价格项与汇率项都是常数 ⇒ '
    '每条序列的增长率与它的张数增长率<b>恒等</b>，图上没有标的涨跌、也没有汇率漂移。')

# ── 同比口径的声明块 ────────────────────────────────────────────────────────
# 本页从前 subtitle / headline / 图注 / 页尾**一处都没有**说过自己画的是哪种同比。
# 那在别的页只是不够漂亮，在本页会直接误导：首页「横截面」那一排里与它并排的
# `exchanges12` 是全站唯一整页保留 12 个月滚动口径的页（CONTRACT §6.2 点名保留），
# 读者从首页点进来两页并排看，一页明写滚动、一页什么都不说，默认就会读成同口径。
# 所以口径声明要出现在读者看得到的四处：subtitle（那里只能用纯文本，见下）、
# 汇总表的 note、动量矩阵自己的 title / legend / note、页尾「口径与方法说明」；
# 下面这两个串在后两处逐字复用，subtitle 那一处另写纯文本版。
MOM_TXT = (
    '<b>口径：本页的同比一律是<u>单月</u>同比</b>（当月 ÷ 去年同月 − 1）—— 全站统一，'
    '<b>页面所有者指定</b>（<code>build/CONTRACT.md</code> §6 抬头引了原话）。'
    '成交量这类流量序列按 §6.1 第 1 条走，指数挂钩 AUM 那种存量序列按第 2 条走点对点 —— '
    '两条落到算术上是同一个式子。图上那几处走全站唯一实现 '
    '<code>build/yoy.py</code> 的 <code>mom_yoy()</code>，本文件不另写一份；'
    '汇总表那一列是同一个式子直接落在表里 —— 它旁边就摆着本月与去年同月两个水平值，'
    '读者可以逐行自己除。'
    '<b>本页没有任何一处画 12 个月滚动合计的同比</b> —— 滚动口径只在下面那段'
    '实测代价里以数字出现。')

SIB12_TXT = (
    '⚠ <b>首页与本页并排的 <code>exchanges12</code>（12 家总览）不是这个口径，'
    '两页的同比读数不能互相比高低。</b>那一页在 <code>build/CONTRACT.md</code> §6.2 的'
    '例外名单上，<b>整页保留 12 个月滚动合计</b>的同比'
    '（§6.2 同时要求它在自己的副标题里声明这个口径）；'
    '本页是单月。同一个月、同一家交易所，两种口径能差多远，'
    '就是上面那段实测里「符号相反的成员月」量的那件事。')


def denom_txt(st):
    """这个池的分母到底是谁 —— 每一张占比图都要印，且成员名单由代码算出。"""
    p = st['p']
    names = '、'.join(mshort(m) for m, _ in st['share'])
    return (f'<b>分母 = 本池 {len(st["share"])} 家可呈现成员之和</b>（{names}）；'
            f'池定义里共 {len(p["members"])} 家，'
            f'本轮可呈现 {len(st["share"])} 家。' + NO_MKT_SHARE)


def dropped_txt(st):
    """本池有哪些成员没画出来、为什么。一个都不省 —— 省掉就是悄悄缩小了分母。"""
    where = '分母里也没有它们' if st['has_share'] else '这张图上也没有它们'
    if not st['dropped']:
        return ('本池成员全部可呈现，'
                + ('分母没有缺口。' if st['has_share'] else '没有留空的成员。'))
    return (f'<b>本轮不呈现的成员（{where}）</b>：'
            + '；'.join(f'<code>{m["key"]}</code> {mshort(m)} — {w}'
                        for m, w in st['dropped'])
            + '。<b>缺基期常数的一律留空，不用近似值填</b>：'
              '拿别的产品的乘数去凑，图上一切正常而结论已经错了 —— '
              '覆盖率低是看得见的缺陷，口径不一致是看不见的缺陷。')


# scope_note 之后要追加的「当场复算」小节，按池 id 挂。它不是补充说明，是让
# pools.py 里那段引用变成**可核对**的：引用的话与实测的数对不上，就说明有人改了列。
SCOPE_EXTRA = {}
if ICE_COV:
    SCOPE_EXTRA['energy'] = (
        f'<b>本页当场复算这条腿的覆盖率</b>（不照抄上面那段话里的数）：'
        f'<code>{ICE_COV["num"]} ÷ {ICE_COV["den"]}</code>，'
        f'{mlab(BASE_P)} = {ICE_COV["base"]:.1f}%，'
        f'窗口内 {ICE_COV["n"]} 个月中位 {ICE_COV["med"]:.1f}%'
        f'（区间 {ICE_COV["min"]:.1f}–{ICE_COV["max"]:.1f}%）。'
        '引用的话与实测的数对不上，就说明有人改了列或改了口径。')


def caveat_txt(st):
    """该池自己的 share_caveat + scope_note + contracts_only_note，一个字不改地落到图注。"""
    p, out = st['p'], []
    if p.get('share_caveat'):
        out.append(md(p['share_caveat']))
    if p.get('scope_note'):
        out.append(md(p['scope_note']))
        out.append(SCOPE_EXTRA.get(p['id'], ''))
    if p.get('contracts_only_note'):
        out.append(md(p['contracts_only_note']))
    return ''.join(out)


# 跨池图里带的那一段 = 能源池的 scope_note + 同一段复算。两处必须是同一个串，
# 不然「能源池自己那张图」与「跨池图」会给出两套说法，而两处不一致看不出来。
ICE_SCOPE = ((md(_energy['p']['scope_note']) + SCOPE_EXTRA.get('energy', ''))
             if _energy is not None else '')


def has_energy_ice(pool_ids):
    """这张图里有没有能源池的 ICE 那条腿 —— 有就必须带 scope_note（pools.py 的硬要求）。"""
    return ICE_SCOPE and 'energy' in pool_ids


# ────────────────────────── 6. Exhibit 1：汇总表 ──────────────────────────
SUM_ROWS = []      # ('group', 标签) | ('row', 标签, 序列, 小数位, 模式)
for st in POOL_STATE:
    p = st['p']
    SUM_ROWS.append(('group',
                     f'{p["zh"]} — {p["unit"]} · '
                     + (f'分母 = 本池 {len(st["share"])} 家之和，非市场份额'
                        if st['has_share'] else
                        'share=none：本池没有可用分母，任何形式的占比都不画')))
    for m, _s in st['share']:
        SUM_ROWS.append(('row', f'　{m["disp"]}', st['ser'][m['key']], 2, 'num'))
    if st['has_share']:
        SUM_ROWS.append(('row', f'　本池 {len(st["share"])} 家合计', st['tot'], 2, 'num'))
        for m, _s in st['share']:
            SUM_ROWS.append(('row', f'　　池内占比 — {mshort(m)}（%）',
                             st['share_pct'][m['key']], 2, 'share'))
    for m, _s in st['growth']:
        SUM_ROWS.append(('row', f'　{m["disp"]}｜{p["unit_contracts"]}（只进增长图）',
                         st['gser'][m['key']], 1, 'num'))

SUM_HEADS = [f'本月 {mlab(CUR)}', f'上月 {mlab(PRV)}', f'去年同月 {mlab(YAG)}',
             'm/m', 'y/y', '3Y %ile']


def ser_of(s):
    """pandas Series → pctile.py 吃的「按月升序、缺失为 None」的 float 列表。

    NaN 不能直接喂：pctile 里 `v is not None` 会把 NaN 当有效样本收进 hist，
    而 NaN 的比较恒为 False，分位会被悄悄压低。
    """
    return [None if not ok(v) else float(v) for v in s.reindex(IDX).values]


def lvl(v, dec, mode):
    if not ok(v):
        return '—'
    if mode == 'share':
        return f'{float(v):,.{dec}f}%'
    return f'{float(v):,.{dec}f}'


def cls_of(v):
    if not ok(v):
        return ''
    return 'pos' if v > 0 else ('neg' if v < 0 else '')


CO_LABELS = [f'{pshort(s["p"])}·{mshort(m)}' for s in POOL_STATE for m, _ in s['growth']]


def summary():
    rows, blank_why = [], []
    for spec in SUM_ROWS:
        if spec[0] == 'group':
            rows.append({'kind': 'group', 'label': spec[1]})
            continue
        _, label, s, dec, mode = spec
        c = float(s.get(CUR, np.nan)) if CUR in s.index else np.nan
        p1 = float(s.get(PRV, np.nan)) if PRV in s.index else np.nan
        p12 = float(s.get(YAG, np.nan)) if YAG in s.index else np.nan
        if mode == 'share':                      # 比率类：变化一律 pp/bp
            mm = c - p1 if ok(c) and ok(p1) else np.nan
            yy = c - p12 if ok(c) and ok(p12) else np.nan
            dm, dy = pp(mm), pp(yy)
        else:                                    # 水平值：变化用百分比
            mm = (c / p1 - 1) * 100 if ok(c) and ok(p1) and p1 else np.nan
            yy = (c / p12 - 1) * 100 if ok(c) and ok(p12) and p12 else np.nan
            dm, dy = pct(mm), pct(yy)
        cells = [{'v': lvl(c, dec, mode)}, {'v': lvl(p1, dec, mode)},
                 {'v': lvl(p12, dec, mode)},
                 {'v': dm, 'cls': cls_of(mm)}, {'v': dy, 'cls': cls_of(yy)}]
        ser = ser_of(s)
        txt_, cls_ = pctile.cell(ser)
        cells.append({'v': txt_, 'cls': cls_} if txt_ else {'v': ''})
        if not txt_:
            blank_why.append((label.strip(), pctile.why_blank(ser)))
        rows.append({'label': label, 'cells': cells})
    blank_txt = ('本轮留空：'
                 + '；'.join(f'{lab}（{why}）' for lab, why in blank_why) + '。'
                 ) if blank_why else '本轮各行均未触发留空，分位照算。'
    return {
        'title': f'标的轴横截面 — {len(POOL_STATE)} 个池 · {mlab(CUR)}（共同最新月）',
        'heads': SUM_HEADS,
        'sep': 3,
        'rows': rows,
        'note': (BASE_UNIT_TXT + NO_MKT_SHARE
                 + '<b>各池之间的水平值可以放进同一根轴，但占比不能横着读</b>：'
                   '每个池的分母是它自己的成员之和，池与池之间的分母是两回事。'
                   '占比与其变化用 pp/bp（绝对值不足 1pp 时写 bp），水平值的变化用百分比。'
                 + f'<b>「y/y」这一列 = 本月 ÷ 去年同月 − 1，即<u>单月</u>同比</b>'
                   f'（占比那几行走百分点差）；三列水平值 {mlab(CUR)} / {mlab(PRV)} / '
                   f'{mlab(YAG)} 就摆在旁边，读者可以逐行自己除。'
                   '本页任何一处都没有 12 个月滚动合计的同比。'
                 + (f'<b>张数口径的行（{"、".join(CO_LABELS)}）只有增长有意义</b>：'
                    '它不进任何池合计，也不进占比的分子或分母。'
                    if CO_LABELS else '')
                 # 窗口现读 pctile.WINDOW，不写死 36：这一列的窗口由那份实现定，
                 # 它一改，这句话就是页面上一个没人会发现的假数。
                 + f'3Y %ile = 该读数在最近 {pctile.WINDOW} 个月里高于多少百分比的观测，'
                   '判据与留空规则由全站唯一实现 <code>build/pctile.py</code> 给出。'
                 + blank_txt),
    }


# ────────────────────────── 7. Exhibit 2..N ──────────────────────────
ex = []
_n = [1]


def nxt():
    _n[0] += 1
    return _n[0]


# ── Ex2：跨池累计增长（自基期）——规模差三个数量级，绝对值同轴读不出来，所以画增长 ──
_g_rows = sorted(
    ((s, (float(s['tot'][CUR]) / float(s['tot'][BASE_P]) - 1) * 100) for s in BASE_POOLS),
    key=lambda kv: -kv[1])
_lvl_txt = '、'.join(
    f'{pshort(s["p"])} {float(s["tot"][BASE_P]):,.1f} → {float(s["tot"][CUR]):,.1f}'
    for s, _v in _g_rows)
ex.append({
    'n': nxt(), 'kind': 'grouped_bars', 'height': 300,
    'fmt': 'pct0', 'label_fmt': 'pct1', 'bar_labels': True,
    'xrot': CAT_ROT, 'xstep': 1,
    'title': f'Cumulative growth by product pool, {mlab(BASE_P)} → {mlab(CUR)} '
             f'(base-locked USD notional)',
    'ylab': f'% vs {mlab(BASE_P)}',
    'xlabels': [pshort(s['p']) for s, _v in _g_rows],
    'groups': [{'name': f'自 {mlab(BASE_P)} 的累计增长（%）', 'color': 'NAVY',
                'values': L([v for _s, v in _g_rows])}],
    'src_extra': ('Pool totals are the sum of the members that have a measured base-period '
                  'constant; contracts-only legs are excluded from levels by construction'),
    'note': ('<b>这张图画的是增长而不是规模，是因为规模没法同轴画</b>：'
             f'本页各池的日均名义额从 {min(float(s["tot"][CUR]) for s in BASE_POOLS):,.1f} 到 '
             f'{max(float(s["tot"][CUR]) for s in BASE_POOLS):,.1f} USD bn/日，'
             '差三个数量级 —— 放进同一根线性轴，小的那几根柱子只剩一条底边。'
             f'水平值改用文字给出（{mlab(BASE_P)} → {mlab(CUR)}，USD bn/日）：{_lvl_txt}。'
             + BASE_UNIT_TXT
             + '<b>增长率不受口径宽窄影响</b>（口径宽只是整条线乘一个常数），'
               '所以这一张图上池与池之间是干净可比的；'
               '而占比只能在池内读，见后面各池自己的图。'
             + (f'<b>本图不含 {"、".join(pshort(s["p"]) for s in FXONLY_POOLS)}</b>：'
                '那个池的源列是成交额，价格项剔不掉（只锁了汇率），'
                '它的增长里含着所成交货币对的波动，与已剔标的价格的增长不是同一个东西。'
                if FXONLY_POOLS else '')
             + (ICE_SCOPE if has_energy_ice([s['p']['id'] for s in BASE_POOLS]) else '')),
})

# ── Ex3：跨池指数化长历史 —— 周期错位就在这张图上 ──
_idx_now = {s['p']['id']: float(s['index'][CUR]) for s in BASE_POOLS}
_lead = max(_idx_now.items(), key=lambda kv: kv[1])
_lagr = min(_idx_now.items(), key=lambda kv: kv[1])
_lead_st = next(s for s in BASE_POOLS if s['p']['id'] == _lead[0])
_lagr_st = next(s for s in BASE_POOLS if s['p']['id'] == _lagr[0])
ex.append({
    'n': nxt(), 'kind': 'lines', 'x': 'long', 'full': True, 'height': LINE_H_ENDLABEL,
    'fmt': 'f0', 'yfmt': 'f0', 'xstep': 12, 'xrot': 90, 'markers': False,
    'zero_base': True, 'end_label': True, 'label_fmt': 'f0',
    'title': f'Product pools rebased to {mlab(BASE_P)} = 100 — where the cycles diverge',
    'ylab': f'index, {mlab(BASE_P)} = 100',
    'series': [{'name': pshort(s['p']), 'color': POOL_COLOR[s['p']['id']],
                'values': L(s['index'].reindex(IDX).values)} for s in BASE_POOLS],
    # 基期月现读 BASE_P，不写死「Jan-2019」：BASE_MONTH 一改，这句英文就是假的
    # （而它是本页唯一一处把基期写成英文长格式的地方，改起来最容易被漏掉）。
    'src_extra': (f'Each pool is the sum of its presentable members, converted at fixed '
                  f'{MONTHS[BASE_P.month - 1]}-{BASE_P.year} contract prices and FX, '
                  f'then rebased'),
    'note': ('<b>本页的第一个问题：同一套宏观环境下，各类标的的周期是不是错位的。</b>'
             '定基名义额把乘数、基期价格与汇率都变成常数之后，'
             '这几条线的斜率第一次可以直接比 —— 差别只来自成交量本身。'
             f'{mlab(CUR)} 累计领先 <b>{pshort(_lead_st["p"])}（{_lead[1]:,.0f}）</b>、'
             f'落后 {pshort(_lagr_st["p"])}（{_lagr[1]:,.0f}）。'
             + '各池起点不同（'
             + '、'.join(f'{pshort(s["p"])} {mlab(s["idx"][0])}' for s in BASE_POOLS)
             + '），线在起点之前断开，不是缺数。'
             + f'基期取 {mlab(BASE_P)}（全仓统一基期），'
               f'所以 {mlab(BASE_P)} 之前的一段在 100 附近上下是正常的。'
             + BASE_UNIT_TXT
             + (ICE_SCOPE if has_energy_ice([s['p']['id'] for s in BASE_POOLS]) else '')),
})

# ── Ex4：成员 × 近 24 个月的**单月**同比动量矩阵（张数口径成员在这里是完全合法的） ──
# 口径：CONTRACT §6.1 第 1 条，流量走 yoy.mom_yoy(…, FLOW)。每一格就是「这个月 ÷
# 去年同月 − 1」，所以这张图同时也在 §6.3 的图型豁免表上（横轴按月铺开、格内本来
# 就是单月读数）—— **豁免的是「必须把『单月』写进标题」那条机检，不是 §6.1 第 3 条
# 那笔代价**：契约 §6.1 第 3 条把本图逐字点名在「真欠账」那一档里，写法是
# 「在图注里报总体、并点名最毛刺的那一条」，不是逐行报一遍。下面就是那笔账。
_hm_rows, _hm_lab, _hm_note_ids, _hm_src = [], [], [], []
for st in BASE_POOLS:
    for m, _s in st['share']:
        _hm_lab.append(f'{pshort(st["p"])}·{mshort(m)}')
        _hm_src.append(st['ser'][m['key']])
        _hm_note_ids.append(st['p']['id'])
    for m, _s in st['growth']:
        _hm_lab.append(f'{pshort(st["p"])}·{mshort(m)}(张)')
        _hm_src.append(st['gser'][m['key']])
        _hm_note_ids.append(st['p']['id'])
_hm_rows = [YOY.mom_yoy(s, YOY.FLOW) for s in _hm_src]
_hm_cols = list(IDX[-HEAT_MONTHS:])
_hm_matrix = [L(r.reindex(_hm_cols).values) for r in _hm_rows]
_hm_flat = [v for row in _hm_matrix for v in row if v is not None]
_hm_neg = sum(1 for v in _hm_flat if v < 0)


def _mom_cost_txt():
    """§6.1 第 3 条要的那段：换单月口径的代价，用本图这几条序列自己实测。

    统计量一律由 `yoy.caliber_diff()` 出（窗口 = 图上画出来的那几个月，图外的历史
    读者根本看不到），本文件不自己算标准差、不自己数符号相反的月份。
    ⚠ 可比月不足 `yoy.MIN_DIAG_MONTHS` 的行**照实说量不出来**，不硬编数字 ——
    一条 2026 年才进池的腿，两种口径的交集可能只有几个月。
    """
    good, thin = [], []
    for _lab, _s in zip(_hm_lab, _hm_src):
        d = YOY.caliber_diff(_s, YOY.FLOW, win=_hm_cols)
        if d['n'] >= YOY.MIN_DIAG_MONTHS and ok(d['std_mom']) and ok(d['std_ttm']):
            good.append((_lab, d))
        else:
            thin.append(_lab)
    if not good:
        return ('<b>换单月口径的代价这一轮量不出来</b>：本图每一行两种口径都有值的月份'
                f'都不足 {YOY.MIN_DIAG_MONTHS} 个，'
                f'<code>build/yoy.py</code> 的 <code>caliber_diff()</code> 报不出比例。'
                '按契约（§6.1 第 3 条）这也是一种付账 —— 它同样是拿本图的序列实测出来的，'
                '结论是「差异量不出来」，不是「没有差异」。')
    sm = [d['std_mom'] for _l, d in good]
    st_ = [d['std_ttm'] for _l, d in good]
    rt = [d['std_ratio'] for _l, d in good]
    wlab, wd = max(good, key=lambda kv: kv[1]['std_mom'])
    jrows = [(lab, d) for lab, d in good if d['maxjump_mom']]
    jlab, jd = max(jrows, key=lambda kv: kv[1]['maxjump_mom'][0]) if jrows else (None, None)
    n_cell = sum(d['n'] for _l, d in good)
    n_opp = sum(d['opposite_n'] for _l, d in good)
    return (
        f'<b>换单月口径的代价，用动量矩阵那 {len(good)} 条序列自己实测</b>'
        f'（窗口 = 矩阵画出来的这 {len(_hm_cols)} 个月；每条只取两种口径都算得出的月份，'
        f'样本先对齐；统计量由 <code>build/yoy.py</code> 的 <code>caliber_diff()</code> 出）：'
        f'逐月标准差单月 <b>{min(sm):.1f}–{max(sm):.1f}pp</b>，'
        f'对照的 {YOY.TTM_WIN} 个月滚动口径 {min(st_):.1f}–{max(st_):.1f}pp'
        f'（放大 {min(rt):.1f}–{max(rt):.1f} 倍）。'
        f'<b>最毛刺的一行是 {wlab}</b>：单月标准差 {wd["std_mom"]:.1f}pp、'
        f'滚动 {wd["std_ttm"]:.1f}pp，相邻月跳变中位 {wd["medjump_mom"]:.1f}pp '
        f'vs {wd["medjump_ttm"]:.1f}pp。'
        + (f'矩阵内相邻月最大跳变 <b>{jd["maxjump_mom"][0]:.0f}pp</b>'
           f'（{jlab}，{mlab(jd["maxjump_mom"][1])} → {mlab(jd["maxjump_mom"][2])}）'
           + (f'；同一行、同一窗口内，滚动口径的最大跳变只有 '
              f'{jd["maxjump_ttm"][0]:.0f}pp（{mlab(jd["maxjump_ttm"][1])} → '
              f'{mlab(jd["maxjump_ttm"][2])}，不必是同一对月份）。'
              if jd['maxjump_ttm'] else '。')
           if jlab else '')
        + f'这 {n_cell} 个「成员 × 月」里，两种口径<b>符号相反的有 {n_opp} 个'
          f'（{n_opp / n_cell * 100:.0f}%）</b>。'
        + (f'另有 {len(thin)} 行（{"、".join(thin)}）两种口径都有值的月份不足 '
           f'{YOY.MIN_DIAG_MONTHS} 个、或统计量算不出来，<b>差异在这几行上量不出来</b>，'
           f'没进上面那组数 —— 照实说，不硬编一个数字。' if thin else '')
        + '⇒ <b>每一格要连着该成员自己的水平值一起读</b> —— 汇总表里每一行都摆着'
          '本月 / 上月 / <b>去年同月</b>三个水平值，而去年同月正是这一格的分母：'
          '它低的时候格子会被放大，单挑一格能把结论说成两个方向。'
        + f'对照的 {YOY.TTM_WIN} 个月滚动口径<b>只在这段文字里以数字出现，'
          f'本页一条线、一格都不画</b>。')


MOM_COST_TXT = _mom_cost_txt()
ex.append({
    'n': nxt(), 'kind': 'heat_matrix', 'full': True,
    'title': f'Growth momentum, single-month y/y by member — last {len(_hm_cols)} months',
    'rows': _hm_lab,
    'cols': [mlab(p) for p in _hm_cols],
    'matrix': _hm_matrix,
    'fmt': 'pct0',
    'legend': '成交量单月同比（当月 ÷ 去年同月 − 1；定基名义额口径，张数腿标「张」）',
    'cell_h': 19, 'row_lab_w': 104, 'row_head': '池 · 成员',
    'src_extra': ('Rows are grouped by product pool; a contracts-only leg is marked so — '
                  'its growth rate is identical to the notional growth rate by construction. '
                  'Every cell is a single-month y/y: this month over the same month a year '
                  'earlier, no rolling window anywhere'),
    'note': ('<b>行按池分组，所以同一类标的在不同法域的周期错位可以横着一行行读。</b>'
             '同一个池里两行同时红或同时绿 = 这一类标的的周期在两个法域是同步的；'
             '一红一绿 = 错位，那正是本页最想让人看见的东西。'
             '<b>标「张」的行是张数口径成员</b>：定基名义额 = 张数 × 常数，'
             '所以它的同比与名义额同比恒等，放在这张增长图里与别人比一点折扣都不打；'
             '但它不进水平值图，也不进任何占比的分子或分母。'
             f'色标是本图全部 {len(_hm_flat)} 个有效格子的 5/95 分位，'
             f'其中 <b>{_hm_neg} 个</b>是负的 —— '
             '<b>颜色只在本图内部可比</b>，与页面上任何别的图的颜色没有关系；'
             '读数一律以格内数字为准。格内取 0 位小数。'
             + MOM_TXT + MOM_COST_TXT + SIB12_TXT
             + (ICE_SCOPE if has_energy_ice(_hm_note_ids) else '')),
})

# ── Ex5：头名占比 —— 「谁的独占产品真的独占」的可计算定义 ──
_top = []
for st in POOL_STATE:
    if not st['has_share']:
        continue
    _k, _v = max(((k, float(v[CUR])) for k, v in st['share_pct'].items() if ok(v[CUR])),
                 key=lambda kv: kv[1])
    _m = next(m for m, _ in st['share'] if m['key'] == _k)
    _b0 = float(st['share_pct'][_k].get(BASE_P, np.nan))
    _top.append((st, _m, _b0, _v))
_top.sort(key=lambda t: -t[3])
ex.append({
    'n': nxt(), 'kind': 'grouped_bars', 'height': 320,
    'fmt': 'f0', 'label_fmt': 'f1', 'bar_labels': True, 'xrot': CAT_ROT, 'xstep': 1,
    'title': f'Top member\'s pool share, {mlab(BASE_P)} vs {mlab(CUR)} — how exclusive is it',
    'ylab': '% of pool（分母 = 各自池内可呈现成员之和）',
    'xlabels': [f'{pshort(st["p"])}·{mshort(m)}' for st, m, _b, _v in _top],
    'groups': [
        {'name': f'{mlab(BASE_P)}', 'color': 'BLUE',
         'values': L([b for _st, _m, b, _v in _top])},
        {'name': f'{mlab(CUR)}', 'color': 'NAVY',
         'values': L([v for _st, _m, _b, v in _top])},
    ],
    'src_extra': ('The "top member" is the one with the largest pool share in the latest '
                  'common month; the same member is shown at the base month'),
    'note': ('<b>「独占」在这里有一个可计算的定义</b>：该池头名成员的池内占比，'
             '以及它自基期以来的变化。占比高且不掉 = 这门生意确实没人抢得动；'
             '占比高但在掉 = 独占正在被侵蚀。'
             + '逐池：' + '；'.join(
                 f'{pshort(st["p"])} 的 {mshort(m)} {b:.1f}% → {v:.1f}%（{pp(v - b)}）'
                 for st, m, b, v in _top) + '。'
             + '<b>两组柱都是同一个成员</b>（按最新月定头名），不是「基期的头名 vs 现在的头名」——'
               '后者会把「换了个第一名」画成「第一名的份额变了」。'
             + NO_MKT_SHARE
             + '⚠ <b>占比高不等于垄断</b>：本页各池成员的标的几乎不重合，'
               '一家占九成往往只是说「这一类标的的名义额九成集中在这条曲线/这个指数上」，'
               '而不是说它打赢了谁。真正争同一批订单流的只有能源池的 Brent vs WTI 一对。'
             + (ICE_SCOPE if has_energy_ice([st['p']['id'] for st, _m, _b, _v in _top]) else '')),
})

# ── Ex6..：逐池一张（有分母的画池内占比，share=none 的只画水平值） ──
for st in POOL_STATE:
    p = st['p']
    _xl = [mlab(q) for q in st['idx']]
    if not st['has_share']:
        # share='none'：**一个占比都不画**。levels=True 才有这张水平值图 ——
        # 定基口径把各家的单位换成同一个之后，「占比不成立」不等于「水平值不可比」。
        _lv = [{'name': mshort(m), 'color': m['color'],
                'values': L(st['ser'][m['key']].values)} for m, _s in st['share']]
        _lvnow = [(mshort(m), float(st['ser'][m['key']].get(st['idx'][0], np.nan)),
                   float(st['ser'][m['key']][CUR])) for m, _s in st['share']]
        ex.append({
            'n': nxt(), 'kind': 'lines', 'full': True, 'height': LINE_H_ENDLABEL,
            'fmt': 'f0', 'yfmt': 'f0', 'xstep': 12, 'xrot': 90, 'markers': False,
            'zero_base': True, 'end_label': True, 'label_fmt': 'f0',
            'xlabels': _xl,
            'title': f'{p["zh"]} — levels only, no share of any kind '
                     f'({mlab(st["idx"][0])} to {mlab(CUR)})',
            'ylab': p['unit'],
            'series': _lv,
            'src_extra': ('No denominator exists for this pool at monthly frequency; '
                          'levels are comparable because the unit is the same, shares are not'),
            'note': ('<b>本池的 share 档次是 <code>none</code>，所以这一页不给它画任何形式的占比</b>'
                     '（连「池内占比」都不画）。理由是池定义里写死的：'
                     + md(p.get('why_none') or '')
                     + '<b>但占比不成立不等于水平值不可比</b>：'
                     + f'折成同一个记账单位（{p["unit"]}）之后，各家的绝对量可以放进同一根轴 —— '
                       'levels=True 说的就是这件事。'
                     + f'{mlab(st["idx"][0])} → {mlab(CUR)}：'
                     + '、'.join(f'{n} {a:,.0f} → {b:,.0f}（{pct(b / a * 100 - 100, 0)}）'
                                 for n, a, b in _lvnow if ok(a) and a) + '。'
                     + md(p['basis'])
                     + dropped_txt(st)
                     + (f'<b>本池在池定义里被排除的成员</b>：'
                        + '；'.join(f'<code>{k}</code> — {md(w)}'
                                    for k, w in (p.get('excluded') or [])) + '。'
                        if p.get('excluded') else '')),
        })
        continue
    _ser = [{'name': mshort(m), 'color': m['color'],
             'values': L(st['share_pct'][m['key']].values)} for m, _s in st['share']]
    _mv = [(mshort(m), float(st['share_pct'][m['key']].get(st['idx'][0], np.nan)),
            float(st['share_pct'][m['key']][CUR])) for m, _s in st['share']]
    ex.append({
        'n': nxt(), 'kind': 'lines', 'full': True, 'height': LINE_H_ENDLABEL,
        'fmt': 'f1', 'yfmt': 'f0', 'xstep': 12, 'xrot': 90, 'markers': False,
        'zero_base': True, 'end_label': True, 'label_fmt': 'f1',
        'xlabels': _xl,
        'title': f'{p["zh"]} — pool share, {mlab(st["idx"][0])} to {mlab(CUR)}',
        'ylab': '% of pool（分母 = 本池可呈现成员之和）',
        'series': _ser,
        'src_extra': (f'Denominator = the {len(st["share"])} presentable members of this pool, '
                      f'summed; there is no published industry total for this product class'),
        'note': (denom_txt(st)
                 + f'{mlab(st["idx"][0])} → {mlab(CUR)}：'
                 + '、'.join(f'{n} {a:.1f}% → {b:.1f}%（{pp(b - a)}）' for n, a, b in _mv)
                 + '。'
                 + caveat_txt(st)
                 + md(p['basis'])
                 + dropped_txt(st)
                 + (f'<b>本池只有两家可呈现，两条线互为镜像</b>（一家多一分必然另一家少一分）'
                    '—— 有信息的是水平位置与斜率，不是「两条线交叉」这件事本身。'
                    if len(st['share']) == 2 else '')
                 + (f'<b>本池在池定义里被排除的成员</b>：'
                    + '；'.join(f'<code>{k}</code> — {md(w)}' for k, w in (p.get('excluded') or []))
                    + '。' if p.get('excluded') else '')),
    })

    # 张数口径成员只能进增长图 —— 有它的池另配一张指数化图，把这条规矩画出来
    if st['growth']:
        _gser = ([{'name': mshort(m), 'color': m['color'],
                   'values': L((st['ser'][m['key']] / float(st['ser'][m['key']][BASE_P]) * 100
                                ).values)} for m, _s in st['share']]
                 + [{'name': f'{mshort(m)}（张数口径）', 'color': m['color'],
                     'values': L((st['gser'][m['key']] / float(st['gser'][m['key']][BASE_P]) * 100
                                  ).values)} for m, _s in st['growth']])
        _gnow = [(s['name'], next((v for v in reversed(s['values']) if v is not None), None))
                 for s in _gser]
        ex.append({
            'n': nxt(), 'kind': 'lines', 'full': True, 'height': LINE_H_ENDLABEL,
            'fmt': 'f0', 'yfmt': 'f0', 'xstep': 12, 'xrot': 90, 'markers': False,
            'zero_base': True, 'end_label': True, 'label_fmt': 'f0',
            'xlabels': _xl,
            'title': f'{p["zh"]} — growth rebased to {mlab(BASE_P)} = 100 '
                     f'(contracts-only leg included)',
            'ylab': f'index, {mlab(BASE_P)} = 100',
            'series': _gser,
            'src_extra': ('The contracts-only leg is indexed on contracts; its growth rate is '
                          'identical to a base-locked notional growth rate by construction'),
            'note': ('<b>这张图存在的理由就是那条张数口径的线。</b>'
                     '定基名义额 = 张数 × 常数，常数是常数 ⇒ 两种口径的<b>增长率恒等</b>，'
                     '所以它在增长图里与别人完全可比；'
                     '而它在水平值图与占比图里一律缺席（上一张图的分母里没有它）。'
                     + caveat_txt(st)
                     + f'{mlab(CUR)} 指数：'
                     + '、'.join(f'{n} {v:,.0f}' for n, v in _gnow if v is not None) + '。'
                     + '<b>这不是「还没补上的缺口」</b>：即便官方哪天肯把短端与中长端拆开，'
                       '名义额对利率衍生品本身就是误导性单位（同名义额下 2 年期与 10 年期的 '
                       'DV01 差 5 倍以上），正确的单位是 DV01 或久期加权名义额，'
                       '而月度成交报表里没有久期字段。完整理由见页尾口径说明。'),
        })

# ────────────────────────── 8. 末尾核对表（官方原始单位） ──────────────────────────
# 一行一个成员、一列一个月：本页成员多，按月做行会横出十六列，
# 而按成员做行正好与页面上「一池几家」的读法一致。
W13 = list(IDX[-TBL_MONTHS:])
TBL_COLS = [[mlab(q), f'm{i}'] for i, q in enumerate(W13)]


def raw_row(st, m, kind):
    """成员在核对表里的一行：官方原始列的原始单位，**一个换算都不做**。"""
    csvd = read_csv(m['csv'])
    pos = [lg for lg in m['chain'] if lg.get('sign', 1) > 0]
    cols = list(m.get('contracts_col') or []) or [lg['col'] for lg in pos]
    scales = {lg['unit_scale'] for lg in pos}
    srcs = {lg['src'] for lg in pos}
    ccys = {SPECS[lg['product']]['ccy'] for lg in pos}
    # 每天 vs 每月 vs 期末：三种时间语义在列名上看不出来，必须写进单位里。
    per = ('（期末）' if st['p']['flow'] == 'stock'
           else ('/月（月度总量）' if any(lg.get('per_day') for lg in pos) else '/日'))
    if len(scales) == 1 and len(srcs) == 1:
        sc, sr = scales.pop(), srcs.pop()
        if sr == 'contracts':
            base = '千张' if sc == pools.K else ('张' if sc == pools.ONE else f'×{sc:g} 张')
            unit, dec = base + per, (1 if sc == pools.K else 0)
        else:
            unit, dec = '、'.join(sorted(ccys)) + ' bn' + per, 3
    else:                       # 多种量纲混在一个成员里：不敢合成一列，只标出来
        unit, dec = '（多量纲，见列名）', 3
    s = csvd[cols].sum(axis=1, min_count=len(cols)) if len(cols) > 1 else csvd[cols[0]]
    lab = (f'{pshort(st["p"])}·{mshort(m)}｜{"+".join(cols)}（{unit}）'
           + ('｜张数口径成员' if kind == 'growth' else ''))
    row = {'xl': lab}
    for i, q in enumerate(W13):
        v = float(s.get(q, np.nan)) if q in s.index else np.nan
        row[f'm{i}'] = num(v, dec)
    return row


TBL_ROWS = []
for st in POOL_STATE:
    for m, _s in st['share']:
        TBL_ROWS.append(raw_row(st, m, 'share'))
    for m, _s in st['growth']:
        TBL_ROWS.append(raw_row(st, m, 'growth'))

table = {
    'n': _n[0] + 1,
    'title': f'近 {TBL_MONTHS} 个月原始指标核对表（各家官方原始单位与币种，未做任何换算）',
    'idx': '池 · 成员｜官方原始列（单位）',
    'cols': TBL_COLS,
    'rows': TBL_ROWS,
}

# ────────────────────────── 9. 口径与方法说明 ──────────────────────────
_ahead_txt = ('；'.join(f'{d} 自身已更新至 {mlab(mo)}' for d, mo in _ahead_pools)
              if _ahead_pools else '本期各池的最新月恰好一致，没有池跑在前面')
_drop_lines = []
for st in POOL_STATE:
    for m, w in st['dropped']:
        _drop_lines.append(f'<code>{st["p"]["id"]}.{m["key"]}</code>（{m["disp"]}）— {w}')
for p, w in POOL_SKIPPED:
    _drop_lines.append(f'<code>{p["id"]}</code>（{p["zh"]}，整池不画）— {w}')

# ── 「本页共 N 个池、其中 M 个是标的轴」这句话的分项必须与总数对得上 ──────────
# 上一版的分子分母取自两个不同的集合：总数取 PAGE_POOLS（本页挂了几个池），
# 分项却取 POOL_STATE（本轮画得出来的池）。一旦有池因缺基期常数出局，页上就会印出
# 「共 8 个，其中 7 个是标的轴、1 个是 function」这种加不起来的算术，而没有任何东西报错。
# 这里统一都从 PAGE_POOLS 数，并且当场验加总。
_AX_PRODUCT = [_p for _p in PAGE_POOLS if _p['axis'] == 'product']
_AX_OTHER = [_p for _p in PAGE_POOLS if _p['axis'] != 'product']
# 那句话还许诺「没画出来的在下面逐个点了名」——兑现它的是 POOL_SKIPPED。
# 池被丢掉却没进 POOL_SKIPPED 时，读者面前就是一个没人交代的差额：这里当场停机。
_unaccounted = ({_p['id'] for _p in PAGE_POOLS}
                - {_st['p']['id'] for _st in POOL_STATE}
                - {_p['id'] for _p, _w in POOL_SKIPPED})
if _unaccounted:
    raise SystemExit(
        f'这些池既没画出来、也没记进 POOL_SKIPPED：{sorted(_unaccounted)}。'
        f'页尾会宣称「其余的下面逐个点了名」，而它们一个字都不会出现。')

_co_pairs = [(st, m) for st in POOL_STATE for m, _ in st['growth']]

# ── 「本页的池都是哪一档 share」这句话必须现算 ────────────────────────────────
# 旧文案写死成「本页所有池的 share 档次都是 pool」，而同一页的页尾另有一整条注在讲
# 「share=none 的池：连池内占比都不画」，指的就是 fn_index_aum —— 两条注当场打架。
# 判据就在 POOL_STATE 里，逐池现读。
def _share_tier_txt():
    tiers = {}
    for st in POOL_STATE:
        tiers.setdefault(st['p']['share'], []).append(pshort(st['p']))
    if set(tiers) == {'pool'}:
        return (f'<b>本页在场的 {len(POOL_STATE)} 个池全是 <code>share=pool</code>'
                f'（分母 = 本池成员之和），一个都不是 <code>true</code>。</b>')
    order = [t for t in ('true', 'pool', 'none') if t in tiers]
    body = '；'.join(f'<code>{t}</code> {len(tiers[t])} 个（{"、".join(tiers[t])}）'
                     for t in order)
    return (f'<b>本页在场的 {len(POOL_STATE)} 个池里没有一个是 <code>share=true</code>'
            f'（官方行业分母）。</b>逐档现算：{body}。'
            + ('<b>其中 <code>none</code> 那一档连「池内占比」都不画</b>，'
               '下面另有一条专讲。'
               if 'none' in tiers else ''))


# ── 「同比出现在哪几张图上」现读已经建好的 exhibit，不写死图号 ────────────────
# 判据 = 图题 / 图例 / 右轴标题里出现同比字样。这三处正是 CONTRACT §6.1 第 1 条
# 要求把口径写进去的地方（判据脚本的 R4 也只认这几处），所以一张不在这三处提同比的
# 图，本来就不该是同比图。CONTRACT §6.5 记着「散文里存图号」这条病：中间插一张图，
# 写死的「Exhibit 4」当场就指着别的图。
_YOY_EX = [e['n'] for e in ex
           if any(k in (str(e.get('title', '')) + str(e.get('legend', ''))
                        + str(e.get('ylab2', ''))).lower()
                  for k in ('y/y', 'yoy', '同比'))]

# ── 「哪几家连交易日列都没有」这句话现读 series/*.csv，不写死名单 ────────────
# 写死的后果：哪天某家补了这一列，页面上仍然点着它的名。判据 = 表头有没有任何
# 一列的列名含 `trading_days`（与 build/yoy.py 第 ⑥ 节的清点方式逐字相同）。
def _no_daycol_txt():
    src = sorted({m['csv'] for s in POOL_STATE for m, _ in s['share'] + s['growth']})
    none = [c[:-4].upper() for c in src
            if not [k for k in (read_csv(c).columns if read_csv(c) is not None else [])
                    if 'trading_days' in k]]
    if not none:
        return '本页每一个成员文件都带交易日列，但各家的拆法互不相同'
    return ('本页各成员的交易日列口径互不相同，而 '
            + '、'.join(none) + f' 这 {len(none)} 家一列都没有')


NOTES = [
    f'<b>发布门槛：各池的共同最新月。</b>本页统一截到 <b>{mlab(LATEST)}</b>，'
    f'即 {len(POOL_STATE)} 个可画池里最慢那个的最新月。'
    f'本期短板是 <b>{"、".join(_short_pools)}</b>；{_ahead_txt}。'
    '门槛存在的理由：各家披露节奏差一两周，若各画各的最新月，'
    '读者会拿一个池的 7 月比另一个池的 6 月，看到的「周期错位」有一整个月是口径造出来的。'
    '<b>跑在前面那个池的最新一个月不在本页任何一张图、任何一行表里。</b>'
    f'全页窗口 {mlab(START)} – {mlab(LATEST)}（{len(IDX)} 个月），'
    f'各池起点不同：' + '、'.join(f'{pshort(s["p"])} {mlab(s["idx"][0])}（{s["months"]} 个月）'
                                  for s in POOL_STATE) + '。'
    + (f'另有一条护栏：某个池的最新月比最快的池落后超过 {MAX_POOL_LAG} 个月就整池出局，'
       '不让一个停更的池把全页的共同最新月一起拖回去。'),

    '<b>本页画哪些池，由 <code>build/pools.py</code> 的 <code>page</code> 字段决定，'
    '本文件不另抄一份名单。</b>'
    f'本轮 <code>page={TICKER}</code> 的池共 {len(PAGE_POOLS)} 个，'
    f'其中 {len(_AX_PRODUCT)} 个是标的轴'
    f'（<code>axis=product</code>：同一类标的、不同法域）'
    + (f'，{len(_AX_OTHER)} 个是'
       + '、'.join(sorted({f'<code>axis={_p["axis"]}</code>（{_p["zh"]}）'
                          for _p in _AX_OTHER}))
       + ' —— 后者不是标的轴，是 pools.py 把它挂在本页的；它在本页只占一张图，'
         '不进任何跨池对比'
       if _AX_OTHER else '')
    + f'。这 {len(PAGE_POOLS)} 个里本轮实际画出来的是 {len(POOL_STATE)} 个'
    + ('，其余的在下面「缺基期常数」那条里逐个点了名。' if len(POOL_STATE) < len(PAGE_POOLS)
       else '，一个都没落下。')
    + '抄一份名单的后果很具体：pools.py 哪天把某个池挪走或改名，本页仍然照旧画，'
      '而两处不一致在页面上完全看不出来 —— 只是多了或少了一段。',

    '<b>主口径是定基名义额，不是张数。</b>' + BASE_UNIT_TXT
    + '张数不可比，因为单张合约的名义额 = 乘数 × 标的价格，而乘数是交易所自己选的'
      '产品设计参数：把合约切得更细，张数份额立刻上升，可市场上并没有多一分钱的风险转移。'
      '定基名义额把这一层剥掉之后，跨交易所、跨币种、跨资产类的量第一次可以放进同一根轴。'
    + (f'<b>恒等式是机器验过的</b>：本轮对 {len(IDENT_ROWS)} 个单腿成员逐月比较'
       f'「定基名义额同比 − 张数原列同比」，最大偏差 <b>{IDENT_MAX:.2e} pp</b>'
       f'（浮点舍入量级）；逐个成员为 '
       + '、'.join(f'{lab} {gap:.1e}pp（{n} 个月）' for lab, n, gap in IDENT_ROWS) + '。'
       '多腿成员不在这项自检里 —— 各腿的常数不同，合计的增长率本来就不等于任一原列的增长率。'
       if IDENT_ROWS else '本轮没有可做恒等式自检的单腿成员。'),

    # ── 页尾口径条：本页的同比是哪一种，以及它与并排那一页的关系 ──────────────
    # 与动量矩阵的图注、subtitle 用的是同一批串（MOM_TXT / MOM_COST_TXT / SIB12_TXT），
    # 三处不可能走样。「同比出现在哪几张图上」这句全称断言由 _YOY_EX 现算，图号也现读 ——
    # 写死的话，中间插一张图或再加一张同比图，这句话当场就是假的。
    MOM_TXT
    + (f'在本页它出现在 {len(_YOY_EX)} 张 exhibit 上（'
       + '、'.join(f'<b>Exhibit {n}</b>' for n in _YOY_EX)
       + '，每一格就是一个月的单月同比），另加汇总表的「y/y」一列'
         '（占比那几行走百分点差）与抬头那一行的 y/y。'
       if _YOY_EX else
       '本轮没有一张 exhibit 画同比，同比只出现在汇总表的「y/y」一列'
       '（占比那几行走百分点差）与抬头那一行的 y/y。')
    + f'定基名义额的价格项与汇率项都是常数，所以这几处的同比与各成员<b>张数</b>的'
      f'单月同比恒等（上一条那个 {IDENT_MAX:.2e} pp 的自检量的就是它）。'
    + MOM_COST_TXT
    + SIB12_TXT
    + f'⚠ 两句配套的实现细节，免得上面的话被读成别的东西：'
      f'① <b>流量池的同比建在<u>日均</u>序列上</b>'
      f'（{"、".join(sorted({s["p"]["unit"] for s in BASE_POOLS}))}），不建在月度合计上 —— '
      f'当月与去年同月的交易日数不同，月度合计的同比会带一块纯日历效应，'
      f'而日均口径把它直接除掉了。{_no_daycol_txt()}，'
      f'跨家乘回交易日在本页根本做不到。'
    + (f'② <b>存量池（{"、".join(pshort(s["p"]) for s in STOCK_POOLS)}）的同比是点对点</b>：'
       f'把 12 个月的期末快照加起来不是任何东西 —— 既不是「一年的量」也不是「平均水平」，'
       f'所以它本来就没有第二种口径可选（§6.1 第 2 条），也不在上面那段代价的分母里'
       f'（那笔账只对换过口径的流量列付）。' if STOCK_POOLS else
       f'② 本轮没有存量池在场，本页的同比全是流量列的。'),

    _share_tier_txt()
    + NO_MKT_SHARE
    + '全仓只有北美现货、北美多重挂牌期权与「垄断 vs 竞争」三个池有官方披露的行业分母，'
      '而那三个都靠 ICE 一家带进来，都不在本页。'
      '⇒ 分母一旦有了（某个产品类真的出现了官方行业总量），本页的占比图可以原地换分母，'
      '图型一张都不用改。<b>画占比的</b>那几张图，分母成员名单逐张印在图注里，'
      '并且是由代码从 <code>build/pools.py</code> 现读出来的，不写死在文案里'
      '（<code>share=none</code> 的池没有这一段，因为它压根没有分母）。',

    '<b>缺基期常数的成员一律留空，不用近似值填。</b>'
    + (('本轮不呈现的有：' + '；'.join(_drop_lines) + '。') if _drop_lines
       else '本轮每个池的成员都齐了。')
    + '这里的 📌 一律指 <code>series/contract_specs.csv</code> 里该产品的 '
      '<code>base_price_local</code> 还是空的 —— 基期价格必须来自官方一手披露并实测入库，'
      '在它填上之前，任何用到它的成员都留空。'
      '<b>用户的明确原则：准确优先于覆盖，误差说不清就不呈现</b>；'
      '覆盖率低但无偏 &gt; 覆盖率高但有未知偏差。'
      '覆盖率低是<b>看得见</b>的缺陷（写在图注上，读者知道自己在看什么），'
      '拿一个产品的乘数去凑另一个产品是<b>看不见</b>的缺陷（图上一切正常，结论已经错了）。'
      '⚠ 一个成员被拿掉，池的分母就跟着变 —— 所以每张占比图都印当前分母是哪几家、'
      '池定义里原本有几家。',

    ('<b>张数口径成员（<code>contracts_only</code>）：这不是缺口，是终局。</b>'
     + '本页有 ' + '、'.join(f'<code>{st["p"]["id"]}.{m["key"]}</code>（{m["disp"]}）'
                             for st, m in _co_pairs) + '。'
     + '它只进增长图（指数化 / 同比），<b>不进水平值图，也不进任何份额的分子或分母</b>。'
     + ''.join(md(m.get('contracts_only_why') or '') for _st, m in _co_pairs)
     + ''.join(md(st['p'].get('contracts_only_note') or '') for st, _m in _co_pairs)
     + '⇒ 本页<b>不为它留 TODO</b>，也不会有人再去撞一次那道 reCAPTCHA。'
     if _co_pairs else
     '<b>本轮没有张数口径（<code>contracts_only</code>）的成员在场。</b>'
     '这类成员按设计永久停留在张数口径，只进增长图；本页各池目前没有这样的腿。'),

    ('<b>能源池的 ICE 只含 Brent 原油，不是 ICE 的全部能源 —— 这一条必须跟着每一张图走。</b>'
     + ICE_SCOPE
     + '⇒ 本页凡是画到 ICE 这条腿的图（跨池规模、跨池指数、动量矩阵、头名占比、'
       '能源池自己的占比图）图注里都带着上面这段话，'
       '<b>ICE 的占比读作下界</b>，「CME 能源是 ICE 的几倍」这句话在本页任何一张图上都不成立。'
     if ICE_SCOPE else '<b>本轮能源池不在场，没有需要缩小口径的腿。</b>'),

    ('<b>利率池的占比是全页最需要小心的一张。</b>'
     + md(next(s for s in POOL_STATE if s['p']['id'] == 'rates')['p'].get('risk_note') or '')
     + '所以那张图只能读作「各货币曲线的名义额构成」，不可读作「谁承担了更多利率风险」，'
       '更不可读作「谁的利率生意更大」—— 手续费是按张收的，不是按名义额收的，'
       '张数原列全部留在核对表里。'
     if any(s['p']['id'] == 'rates' for s in POOL_STATE) else
     '<b>本轮利率池不在场。</b>'),

    ('<b>口径不同的池单独成段，不进任何跨池对比图。</b>跨池的规模、增长、动量三张图'
     f'只放 <code>deflator=base_price</code> 且 <code>flow=per_day</code> 的 '
     f'{len(BASE_POOLS)} 个池（' + '、'.join(pshort(s['p']) for s in BASE_POOLS) + '）。'
     + (('<b>只锁汇率的池</b>（' + '、'.join(pshort(s['p']) for s in FXONLY_POOLS)
         + '）：源列本身就是金额，官方不披露笔数 ⇒ 价格项剔不掉'
           '（<code>deflator=fx_only</code>）。它的增长里含着标的自身的涨跌，'
           '与另外几个池「已剔标的价格」的增长<b>不是同一个东西</b>；'
           '混进同一根轴，两种增长会被读成可比的，而图上看不出来。')
        if FXONLY_POOLS else '')
     + (('<b>存量池</b>（' + '、'.join(pshort(s['p']) for s in STOCK_POOLS)
         + f'，单位 {STOCK_POOLS[0]["p"]["unit"]}）：它是某一时点的余额，'
           '另外几个池是整月里陆续发生的流量。两者的汇率档次都不一样'
           '（存量取月末、流量取月均，见 <code>pools.fx_basis()</code>），'
           '单位后缀只差三个字，画进同一根轴一定会被读成同一件事。')
        if STOCK_POOLS else '')
     + '⇒ 这些池只在自己那一张图里出现，跨池图一律不收。'
     if OTHER_POOLS else
     '<b>本轮所有在场的池都是定基口径（<code>base_price</code>）的日均流量</b>，'
     '跨池对比图收全了所有池。'),

    ('<b>share=none 的池：连「池内占比」都不画。</b>'
     + '；'.join(f'{s["p"]["zh"]} — ' + md(s['p'].get('why_none') or '')
                 for s in POOL_STATE if not s['has_share'])
     + '<b>但占比不成立不等于水平值不可比</b> —— 定基口径把这些池的量也换成了'
       '同一个记账单位，所以它们的绝对值照样进图（池定义里的 <code>levels=True</code>），'
       '只是那张图上没有任何百分数。'
     if any(not s['has_share'] for s in POOL_STATE) else
     '<b>本轮在场的池全部有分母（<code>share=pool</code>）</b>，'
     '每一张占比图都点名了分母是哪几家。'),

    '<b>颜色：成员的颜色由 <code>build/pools.py</code> 给定，本文件不另配一套。</b>'
    + '；'.join(f'{pshort(s["p"])} — '
                + '、'.join(f'{mshort(m)} = {m["color"]}'
                            for m, _ in s['share'] + s['growth'])
                for s in POOL_STATE)
    + f'。跨池图另有一套一池一色（'
    + '、'.join(f'{pshort(s["p"])} = {POOL_COLOR[s["p"]["id"]]}' for s in BASE_POOLS)
    + '），两套色只在不同的图里出现，同一张图内不混用。'
      '引擎的数据色只有 NAVY / BLUE / MBLUE / GRAY / GREEN / GOLD 六个'
      '（RED 是断点与截轴离群值专用，不做数据色），所以一张图最多 5–6 条靠颜色区分的线；'
      '成员多于此就必须换成身份靠行标签的 <code>heat_matrix</code>。',

    f'<b>核对表（Exhibit {table["n"]}）用各家官方披露的原始计量单位与币种，一个换算都不做。</b>'
    '这张表存在的唯一理由是让人拿它与官方新闻稿逐位对账，所以它是<b>一行一个成员、'
    '一列一个月</b>（本页成员多，按月做行会横出十几列）。'
    '列名里写着这一行取的是哪几条原列与它们的单位；'
    '<b>并表口径的还原腿（如 Euronext 的 Athens 备注列减法）不在这张表里</b> —— '
    '那是本仓为了可比而做的修正，不是官方原始披露，混进来就没法拿它对账了。'
    f'表同样只到 {mlab(LATEST)}，与全页门槛一致。'
    + (f'⚠ 本页有 {sum(s["holes"] for s in POOL_STATE)} 个「池合计有值区间内的空洞月」，'
       '那些月份至少有一家成员没数，池合计与占比一并留空（线在缺口处断开）。'
       if sum(s['holes'] for s in POOL_STATE) else
       '本页各池的合计在各自窗口内没有空洞。'),
]

# ────────────────────────── 10. 抬头与 payload ──────────────────────────
_yoy_now = sorted(((pshort(s['p']), float(s['yoy'][CUR])) for s in BASE_POOLS
                   if ok(s['yoy'][CUR])), key=lambda kv: -kv[1])
_top_line = '；'.join(f'{pshort(st["p"])} 头名 {mshort(m)} {v:.1f}%（自基期 {pp(v - b)}）'
                      for st, m, b, v in _top[:3])
# 发布日 = 成员里**最晚**的那一家发 LATEST 这个月的数据的日子。
# 有任何一个成员查不到就整个字段省掉（latest_of 的规矩）—— 拿部分成员算出来的 max
# 会偏早，而偏早的日期看上去完全正常。
_MEMBER_TICKERS = sorted({m['csv'][:-4] for s in POOL_STATE
                          for m, _ in s['share'] + s['growth']})
SOURCE_DATE = load_source_dates().latest_of(
    SERIES, _MEMBER_TICKERS, {t: LATEST for t in _MEMBER_TICKERS})

# ── 「本页所有图表一律截到此月」这句话的现算判据 ─────────────────────────────
# 这是一句无条件的全称断言，而页上凡有一张画历史片段的图（右端停在过去某个月），
# 它当场就是假的，且没有任何东西会报错。所以逐张现读右端，例外由代码给出。
# 判据覆盖三种时间右端：xlabels（时序图）、heat_matrix 的 cols、以及默认长轴。
def _right_lab(e):
    if e.get('kind') == 'heat_matrix':
        c = e.get('cols') or []
        return str(c[-1]) if c else None
    xl = e.get('xlabels') or (XL_LONG if e.get('x') == 'long' else None)
    return str(xl[-1]) if xl else None


def _is_mlab(lab):
    return (lab is not None and len(lab) == 6 and lab[3] == '-'
            and lab[:3] in MONTHS)


_CUR_LAB = mlab(LATEST)
_TRUNC_EXC = [(e['n'], _right_lab(e)) for e in ex
              if _is_mlab(_right_lab(e)) and _right_lab(e) != _CUR_LAB]
_exc_txt = '、'.join(f'Exhibit {n}（止于 {lab}）' for n, lab in _TRUNC_EXC)
TRUNC_TXT = ('本页凡是带时间右端的图一律截到此月' if not _TRUNC_EXC else
             '本页带时间右端的图截到此月，'
             + (f'只有 {_exc_txt}例外' if len(_TRUNC_EXC) == 1
                else f'例外是 {_exc_txt} 这 {len(_TRUNC_EXC)} 张')
             + '（画的是已经结束的历史片段）')

# ────────────────────────── 11. 名词释义（页顶「名词释义」板块） ──────────────────────────
# ━━ 与页尾 notes / 图注的分工 ━━
# notes 与图注说的是「这一张图**这个月**该怎么读」（含当月读数、当月实测的毛刺量、
# 逐池的起讫读数）；这一块说的是「**这些词**是什么意思」，一年到头是同一段。
# ⇒ 这里**一个随月份变的数都不出现**：没有当月读数、没有最新一期、没有累计增长。
# 要写的数只有两类 —— 把定义钉住的结构性量（门槛、池数、可呈现成员数、
# 留空成员数）与恒等式本身，且**一个都不写死**：全部现读上面已经算好的
# POOL_STATE / FXONLY_POOLS / STOCK_POOLS 与门槛常数，与页尾那几条注同源。
# 合约面值与久期那两组数**故意不写**（虽然利率池的 share_caveat 里有）：
# 它们是 pools.py 的文案，抄过来就是第二份，改一处会两处不一致；这里只写方向。
#
# ━━ 为什么是这 15 个词（选词判断）━━
# 判据只有一条：这个词出现在本页的图题 / 序列名 / 纵轴 / 汇总表行头 / 核对表 /
# 图注 / 页尾说明里，而且**不看定义就会读错**。
# 横截面页与单公司页的差别在于：最要紧的那几个词**是这一页自己造的口径** ——
# 读者在别的地方见不到，也就无从猜，而且每一个都关系到「分母是什么」。
# 按「读错会出什么事」分六类：
#   ① 主口径与它的三个零件   定基名义额 / 基期常数 / 汇率档次 ——
#      定基口径那几个池的水平值、占比、增长都建在它上面（fx_only 那几个池**不**在
#      其列 —— 它们的源列本身就是金额，见「只锁汇率」那一条）。
#      不点破，读者会把它当成「成交额」，
#      于是要么把「增长率与张数增长率恒等」这条本页反复用到的性质读成巧合，
#      要么反过来以为图上还留着标的涨跌与汇率漂移。
#   ② 分母是谁   池与成员 / 池内占比 / 真份额 / 独占度 —— 本页最容易出事的一类。
#      「占比」两个字在地理轴那三页（exchanges-na / -eu / -apac）是竞争份额，
#      在本页**不是**：分母是本池**可呈现成员之和**。读串的代价是把
#      「这一类标的的名义额构成」读成「谁抢了谁的单」，而图形完全正常。
#      真份额单独立一条，正因为它是本页**没有**的那个东西 —— 不说清「有官方分母
#      长什么样」，读者没法知道自己看的不是它。独占度跟在这一组末尾，因为它是本页
#      用池内占比**造出来**的那个量，分母读错它就跟着错。
#   ③ 页面窗口是怎么定的   共同最新月 / 指数化 —— 前者决定了本页任何一张图上都没有
#      跑在前面那个池的最新月，后者决定了各池的线在自己起点之前是断的。
#      两件事都不是数据缺失，但看上去都像。
#   ④ 一个成员以哪种方式在场   张数口径成员 / 不呈现的成员 / 流量 存量 / 只锁汇率 ——
#      本页有四种在场方式，一条线进不进水平值图、进不进占比的分子分母、
#      进不进跨池图，逐条不同。不点破，读者会把「某家不在这张图上」读成它的量是零。
#   ⑤ 一个口径断点   legacy 口径 —— 这四个字逐字印在汇总表股指组的行头上
#      （成员 disp 给的名字），而全页没有一处定义过它：页尾最接近的那一句
#      （并表口径的还原腿不进核对表）既没出现「legacy」这个词，也没说那条线就是
#      那条还原腿。不看定义，读者会把它读成「旧的/已弃用的序列」，读不出两件要紧事 ——
#      这条线是本仓做的修正（不是官方原始披露，所以与核对表那一行对不上是正常的），
#      以及并表当月有一个口径断点。
#   ⑥ 名义额不是风险   DV01 —— 利率池那张占比图是全页最需要小心的一张，
#      而这个词是那句告诫唯一的抓手。
# **有意不收**：
#   · m/m、y/y、3Y %ile、pp/bp —— 全站通用的读图约定，summary.note 已经逐条讲过，
#     释义板再讲一遍就是两处各写一份（样板 /cost/ 的 9 条里一条都没有，是同一条判断）。
#   · 「单月同比 vs 12 个月滚动」—— subtitle、动量矩阵图注、页尾三处已各有一份完整
#     口径声明，且那一条要带**当轮实测**的毛刺代价（标准差、符号相反的成员月），
#     按分工属于 notes 不属于释义。
#   · 「能源池的 ICE 只含 Brent」—— 那是一个**成员的覆盖率**，不是一个名词；
#     它已经跟着每一张画到那条腿的图走（ICE_SCOPE），复述只会多一份要同步的文案。
#   · 成交量 / 交易所 / 期货与期权 这类本页没有特殊口径的常识词（「名义额」不在此列 ——
#     本页的名义额是定基口径，与常识里的名义额不是一个东西，所以它是第 1 条）。
_FXB_ZH = {'avg': '月均', 'eom': '月末'}
_g_basis = {}
for _gst in POOL_STATE:
    _g_basis.setdefault(pools.fx_basis(_gst['p']), []).append(pshort(_gst['p']))
_G_BASIS_TXT = '；'.join(f'{_FXB_ZH.get(k, k)}汇率配 {"、".join(v)}'
                         for k, v in sorted(_g_basis.items()))
# 「本轮有几个成员因为缺基期常数而留空」—— 现读 dropped 的原因，不写死。
# 判据与 member_block() 打的那个 📌 前缀逐字相同（那里是唯一打标的地方）。
_G_PIN = sum(1 for _gst in POOL_STATE for _gm, _gw in _gst['dropped']
             if _gw.startswith('📌'))
_G_CONTRACTS = [f'{pshort(_gst["p"])}·{mshort(_gm)}'
                for _gst in POOL_STATE for _gm, _gs in _gst['growth']]
_G_FXONLY = [pshort(s['p']) for s in FXONLY_POOLS]
_G_STOCK = [pshort(s['p']) for s in STOCK_POOLS]
# 「legacy 口径」这四个字是从成员 disp 里印到汇总表行头上去的（pools.py 给的名字），
# 所以在场与否也现读 disp —— 名单空了这一条就整条不发（页面上没有的词不进释义板）。
_G_LEGACY = [f'{pshort(_gst["p"])}·{mshort(_gm)}'
             for _gst in POOL_STATE
             for _gm, _gs in (_gst['share'] + _gst['growth'])
             if 'legacy' in _gm['disp']]
# 并表当月同样不写死：pools.py 的 ENX_ATHEX_SINCE 是减法腿 since 的唯一真值。
_G_ATHEX_M = mlab(pd.Period(pools.ENX_ATHEX_SINCE, 'M'))

GLOSSARY = [
    # ── ① 主口径与它的三个零件 ──────────────────────────────────────────────
    ('定基名义额',
     f'本页的<b>主口径</b>，定基口径那 {len(BASE_POOLS)} 个池'
     f'（{"、".join(pshort(s["p"]) for s in BASE_POOLS)}）的水平值、占比与增长的共同底座：'
     f'<code>张数 × 合约乘数 × 锁死的 {mlab(BASE_P)} 基期价格</code>，'
     f'汇率同锁 {mlab(BASE_P)}，单位 USD bn/日。价格项与汇率项都是<b>常数</b>，'
     f'所以每条序列的增长率与它自己的<b>张数</b>增长率<b>恒等</b> —— '
     f'图上既没有标的涨跌、也没有汇率漂移。'
     f'（这条恒等式本页每次构建都对单腿成员逐月复算一遍，实测偏差在浮点舍入量级，'
     f'逐个成员的数印在页尾。）'
     f'⚠ 它<b>不是</b>成交额：成交额里含着当期价格，本页任何一条线都没有。'
     f'⚠ 也<b>不是</b>张数：单张合约的名义额 = 乘数 × 标的价格，而乘数是交易所自己选的'
     f'产品设计参数 —— 把合约切得更细，张数份额立刻上升，可市场上并没有多一分钱的'
     f'风险转移。定基名义额把这一层剥掉之后，跨交易所、跨币种、跨资产类的量'
     f'第一次可以放进同一根轴。'
     # 「主口径」不等于「全页口径」：fx_only 那几个池的水平值、占比与增长都不建在
     # 它上面（源列本身就是金额，价格项剔不掉）。写成「所有」会与页尾那条
     # 「只锁汇率的池」直接打架，而打架的那两个池各占一整张图。名单现读，不写死。
     + (f'⚠ <b>不是全页都建在它上面</b>：<code>deflator=fx_only</code> 的那 '
        f'{len(_G_FXONLY)} 个池（{"、".join(_G_FXONLY)}）源列本身就是金额，'
        f'价格项剔不掉 —— 它们的水平值、占比与增长走的是另一档口径，'
        f'见「只锁汇率」那一条。' if _G_FXONLY else '')),

    ('基期常数',
     f'把张数换成定基名义额所需要的那两个数：<b>合约乘数</b>与 <b>{mlab(BASE_P)} 的'
     f'基期价格</b>。唯一权威是 <code>series/contract_specs.csv</code>'
     f'（<code>multiplier</code> 与 <code>base_price_local</code> 两列），'
     f'必须来自官方一手披露并实测入库。'
     f'⚠ 缺一个就<b>整个成员留空</b>，绝不拿别的产品的乘数去凑：'
     f'覆盖率低是<b>看得见</b>的缺陷（写在图注上，读者知道自己在看什么），'
     f'口径不一致是<b>看不见</b>的缺陷（图上一切正常而结论已经错了）。'),

    ('汇率档次',
     f'本页的汇率<b>也锁在 {mlab(BASE_P)}</b>（与基期价格同一个月），所以图上没有汇率漂移；'
     f'但「{mlab(BASE_P)} 的汇率」本身还分两档，由池的 <code>flow</code> 机械推出'
     f'（<code>build/pools.py</code> 的 <code>fx_basis()</code>，全仓只有这一份映射）：'
     f'{_G_BASIS_TXT}。'
     f'⚠ 拿月末汇率去折整月的流量，等于把整月成交按最后一天记账；拿月均汇率去折一个'
     f'时点的余额，等于给存量安一个不存在的平均价 —— 两种错都<b>不会报错</b>，'
     f'只在同比里多出一段汇率噪声，所以这个档次不由人选。'),

    # ── ② 分母是谁 ─────────────────────────────────────────────────────────
    ('池与成员',
     f'<b>池</b>（pool）= 同一类标的、不同法域的一组交易所，是本页的作图单位；'
     f'<b>成员</b> = 池里的一家交易所的一条腿。成员名单、颜色、换算链与 share 档次的'
     f'唯一真值是 <code>build/pools.py</code>，本页一条都不另抄。'
     f'本轮挂在 <code>page={TICKER}</code> 名下的池共 {len(PAGE_POOLS)} 个，'
     f'画得出来的 {len(POOL_STATE)} 个。'
     f'⚠ 「池定义里共 N 家」与「本轮<b>可呈现</b> N 家」是两个数，'
     f'每张占比图都把两个一起印出来 —— 因为后者才是分母。'),

    ('池内占比',
     f'<code>该成员 ÷ 本池可呈现成员之和 × 100</code>。'
     f'⚠ <b>分母不是这一类标的的行业总量，所以它不是市场份额</b> —— '
     f'页面上凡出现「市场份额」四个字都是在否定它。各池成员的标的几乎不重合'
     f'（各自本土的指数、各自的曲线、各自的作物），占比只能读作'
     f'「这一类标的的名义额构成」，不是「谁抢了谁的单」。'
     f'⚠ <b>占比不能跨池横着读</b>：每个池的分母是它自己的成员之和，'
     f'池与池的分母是两回事（水平值倒是可以横着读，单位是同一个）。'
     f'恒等式：每池各月的占比之和 = 100 —— 本页逐月自检，不成立就整页不发。'),

    ('真份额',
     f'分母是<b>官方披露的行业总量</b>的那一档份额（<code>build/pools.py</code> 的 '
     f'<code>share=true</code>），也就是通常说的「市场份额」。'
     f'<b>本页在场的池一个都不是这一档</b>（逐档现算印在页尾）：'
     f'全仓有官方行业分母的那几个池都在别的页。'
     f'⇒ 本页出现的每一个<b>占比</b>都是上一条那个池内占比，两者不可混读。'
     f'分母一旦有了（某一类标的真的出现了按月披露的行业总量），'
     f'本页的占比图可以原地换分母，图型一张都不用改。'),

    ('独占度',
     f'本页给「独占」下的<b>可计算</b>定义：该池<b>头名成员</b>的池内占比，'
     f'以及它自基期 {mlab(BASE_P)} 以来的 pp 变化。占比高且不掉 = 这门生意确实没人'
     f'抢得动；占比高但在掉 = 独占正在被侵蚀。'
     f'头名<b>按最新月定</b>，基期那一组柱画的是<b>同一个成员</b>在基期的占比 —— '
     f'不是「基期的头名 vs 现在的头名」（后者会把「换了个第一名」画成'
     f'「第一名的份额变了」）。'
     f'⚠ 占比高<b>不等于</b>垄断：标的不重合时，一家占九成往往只是说'
     f'「这一类标的的名义额九成集中在这条曲线上」，不是说它打赢了谁。'),

    # ── ③ 页面窗口是怎么定的 ───────────────────────────────────────────────
    ('共同最新月',
     f'本页的<b>发布门槛</b>：全页统一截到各可画池的最新月里<b>最慢</b>的那一个，'
     f'把它定住的那个（那几个）池，本页叫<b>短板</b>。'
     f'理由是各家披露节奏差一两周，若各画各的最新月，读者会拿一个池的 7 月比另一个池的 '
     f'6 月，看到的「周期错位」有一整个月是口径造出来的。'
     f'⇒ <b>跑在前面那个池的最新一个月，不在本页任何一张图、任何一行表里</b>。'
     f'另有一条护栏：某个池的最新月比最快的池落后超过 {MAX_POOL_LAG} 个月就整池出局，'
     f'不让一个停更的池把全页的共同最新月一起拖回去。'),

    ('指数化',
     f'把一条序列除以它<b>自己</b>在基期 {mlab(BASE_P)} 的值再乘 100，'
     f'纵轴写作「index, {mlab(BASE_P)} = 100」。这样画出来的是<b>增长</b>不是规模 —— '
     f'本页各池的日均名义额差着几个数量级，同轴放线性刻度，小的那几条只剩一条底边。'
     f'增长率<b>不受口径宽窄影响</b>（口径宽只是把整条线乘一个常数），'
     f'所以指数化之后池与池之间是干净可比的，而占比只能在池内读。'
     f'⚠ 各池起点不同，线在自己起点<b>之前是断开的</b>，那是披露史不是缺数；'
     f'基期取全仓统一的 {mlab(BASE_P)}，所以基期之前那一段在 100 上下都算正常。'),

    # ── ④ 一个成员以哪种方式在场 ───────────────────────────────────────────
    ('张数口径成员',
     f'池定义里标 <code>contracts_only</code> 的成员：官方拆不出这条腿的分产品名义额，'
     f'本页只用它的<b>张数</b>（千张/日）。它<b>只进增长图</b>（指数化与同比），'
     f'<b>不进水平值图，也不进任何占比的分子或分母</b>。'
     f'放进增长图一点折扣都不打 —— 定基名义额 = 张数 × 常数，两种口径的增长率恒等。'
     f'⚠ 这<b>不是</b>待补的缺口而是终局：即便官方哪天肯把短端与中长端拆开，'
     f'名义额对利率衍生品本身就是误导性单位（见 DV01 那条）⇒ 本页不为它留 TODO。'
     + (f'本轮的张数口径成员：{"、".join(_G_CONTRACTS)}。' if _G_CONTRACTS else '')),

    ('不呈现的成员',
     f'池定义里有、但本轮画不出来的成员，图注与页尾逐个点名（标 📌）。'
     f'几乎都是<b>基期常数还没实测入库</b>（<code>contract_specs.csv</code> 的 '
     f'<code>base_price_local</code> 还空着）'
     + (f'；本页在场的池里有 <b>{_G_PIN}</b> 个成员因此留空' if _G_PIN else '')
     + f'。⚠ <b>一个成员被拿掉，池的分母就跟着变</b> —— 所以每张占比图都印'
       f'当前分母是哪几家、池定义里原本有几家。'
       f'⚠ 与上一条<b>不是一回事</b>，页面上也分开说：📌 是「还没测出来」'
       f'（下一个人应该去测），张数口径成员是「测出来也不该用」'
       f'（下一个人<b>不</b>应该去测）。'),

    ('流量 / 存量',
     f'本页两种性质不同的量。<b>流量</b>（池的 <code>flow=per_day</code>）是整月里'
     f'陆续发生的成交，写作 USD bn/<b>日</b>；<b>存量</b>（<code>flow=stock</code>）'
     f'是某一时点的余额（本页是挂钩 ETF 的 AUM），写作 USD bn。'
     + (f'本轮的存量池：{"、".join(_G_STOCK)}。' if _G_STOCK else '')
     + f'⚠ 两者<b>不能放进同一根轴</b>（单位后缀只差三个字，一定会被读成同一件事），'
       f'也<b>不能相加</b>；存量的同比只能走<b>点对点</b>（月末 vs 去年同月月末）—— '
       f'把 12 个月的期末快照加起来不指代任何真实的量。汇率档次也跟着分（见上）。'),

    ('只锁汇率',
     f'池的 <code>deflator=fx_only</code>：源列本身就是<b>金额</b>'
     f'（官方不披露对应的笔数或张数），价格项<b>剔不掉</b> —— '
     f'只锁住了汇率，没锁住标的价格。'
     + (f'本轮这一档的池：{"、".join(_G_FXONLY)}。' if _G_FXONLY else '')
     + f'⚠ 它的增长里<b>含着</b>标的自身的涨跌，与定基口径那几个池「已剔标的价格」的'
       f'增长<b>不是同一个东西</b> ⇒ 跨池的规模、增长、动量三张图一律不收它，'
       f'它只出现在自己那一张图里。混进同一根轴，两种增长会被读成可比的，'
       f'而图上一点都看不出来。'),

    # ── ⑤ 一个口径断点 ─────────────────────────────────────────────────────
    # 这四个字逐字印在汇总表股指组的行头上，而全页没有一处定义过它 ——
    # 页尾 notes 里最接近的一句（并表口径的还原腿不进核对表）既没出现「legacy」
    # 这个词，也没说那条线就是那条还原腿。名单为空时整条不发（下面 * 展开）。
    *([('legacy 口径',
        f'成员名里带这四个字的那条线（本轮：{"、".join(_G_LEGACY)}），取的是'
        f'<code>官方主列 − 官方 athex_* 备注列</code>，还原 Athens 于 {_G_ATHEX_M} '
        f'并入 Euronext 主列<b>之前</b>的可比口径。减法腿由 <code>build/pools.py</code> '
        f'的 <code>enx_legacy_legs()</code> 现算，<code>since</code> 卡在并表当月 —— '
        f'更早的月份主列本来就不含 Athens，一路硬减会减掉一块从没加进来的量。'
        f'⚠ 它<b>不是</b>官方原始披露的那个数，是本仓为了跨并表可比而做的<b>修正</b>：'
        f'核对表（Exhibit {table["n"]}）里那一行印的是官方主列、<b>不含</b>这条减法腿'
        f'（那张表存在的理由就是拿去与官方新闻稿逐位对账），'
        f'所以本页这条线与核对表那一行对不上是<b>正常的</b>，要对账请认核对表。'
        f'⚠ 反过来，不做这个减法，并表当月会凭空多出一块 Athens 的量 —— '
        f'图上是一次纯口径造成的跳变，与真实增长长得一模一样。')]
      if _G_LEGACY else []),

    # ── ⑥ 名义额不是风险 ───────────────────────────────────────────────────
    ('DV01',
     f'利率敞口的正确计量单位：收益率变动 1bp 时头寸价值的变动额。'
     f'本页的利率池按<b>名义额</b>作图，而<b>名义额 ≠ 风险敞口</b>：'
     # 页面上这是两组各自成立的对比，前提不同，不能焊成一句 ——
     #   · Ex6/Ex7 的 share_caveat 比的是**逐张合约**（短端面值大久期短 vs
     #     长端面值小久期长，按名义额短端是长端的 10 倍，按 DV01 反过来）；
     #   · 页尾 contracts_only 那条比的是**同一笔名义额**（2 年期 vs 10 年期）。
     # 「同样一笔名义额」配「按名义额短端更大」自相矛盾：同名义额就没有谁更大。
     # 面值、久期与倍数仍不抄进来（见本块开头的说明），这里只写方向。
     f'<b>逐张合约</b>看，短端合约面值大、久期短，长端合约面值小、久期长 —— '
     f'按名义额短端更大，按 DV01 反过来，两者能差一个数量级；'
     f'换成<b>同一笔名义额</b>看，短端那一头的 DV01 要小上数倍。'
     f'⇒ 「谁的名义额占比最大」<b>不等于</b>「谁承担了最多利率风险」，'
     f'更不等于「谁的利率生意最大」（手续费是按<b>张</b>收的，'
     f'张数原列全部留在核对表里）。'
     f'本页做不了 DV01 加权：月度成交报表里<b>没有久期字段</b>（📌 未找到），'
     f'自己算要逐合约取到期日与票息维护一整套曲线数据，远超本仓无人值守的边界。'),
]

payload = {
    'ticker': TICKER,
    'tracker': f'Product-Axis Cross-Section — {len(POOL_STATE)} product pools, '
               f'base-locked USD notional',
    'title': f'标的轴横截面：同一类标的在各法域的周期与独占度 — {zh_month(LATEST)}',
    'data_through': str(LATEST),
    'through_label': f'{zh_month(LATEST)}（各池共同最新月）',
    'subtitle': (f'数据源：各交易所官方月度成交披露 + 合约规格表 + ECB 汇率 · '
                 f'{len(POOL_STATE)} 个池 / '
                 f'{sum(len(s["share"]) + len(s["growth"]) for s in POOL_STATE)} 条成员线 · '
                 f'共同窗口 {mlab(START)} – {mlab(LATEST)}（{len(IDX)} 个月）· '
                 # subtitle 走 page.js 的 set()，它用的是 textContent —— 标签会被原样印成
                 # 「<b>…</b>」的字面量。要强调只能靠措辞，不能靠 HTML。
                 f'主口径 = 定基名义额（锁 {mlab(BASE_P)} 价格与汇率）· '
                 f'占比一律是池内占比，分母 = 本池成员之和 · '
                 # 口径声明（CONTRACT §6）。并排的 exchanges12 是 §6.2 名单上保留
                 # 滚动口径的页，两页并排而只有一页写着，读者会默认它们同口径。
                 f'同比口径 = 单月同比（当月 ÷ 去年同月 − 1；不是 12 个月滚动合计，'
                 f'与首页并排的 exchanges12 口径不同，两页不可比高低）· '
                 '版式仿 Goldman Sachs GIR · 仅图，无评论'),
    'headline': (f'自 {mlab(BASE_P)} 累计增长：'
                 + '、'.join(f'{pshort(s["p"])} '
                             f'{pct(float(s["index"][CUR]) - 100, 0)}' for s, _v in _g_rows)
                 # 抬头是全页曝光最高的一行 —— 口径必须写在这里，而不是只写在图注里。
                 + f' · 单月 y/y（{mlab(CUR)} 比 {mlab(YAG)}）：'
                 + '、'.join(f'{n} {pct(v)}' for n, v in _yoy_now)
                 + ' · 独占度：' + _top_line
                 + ' · 分母 = 各自池内成员之和，不是行业总量'),
    # 名词释义：排在所有 exhibit 之前。选词的判断与「有意不收哪些词」写在 GLOSSARY
    # 上面那一块注释里；版式与四道护栏在 build/glossary.py，本页不另拼字符串。
    'glossary': gloss.render(GLOSSARY, where='exchanges-products glossary'),
    'hub_line': (f'各池共同最新月 {mlab(LATEST)}（短板 {"、".join(_short_pools)}）；'
                 f'{len(POOL_STATE)} 个池 · 定基名义额；'
                 f'自 {mlab(BASE_P)} 领涨 {pshort(_lead_st["p"])} '
                 f'{pct(_lead[1] - 100, 0)}；占比均为池内占比'),
    'source': SRC,
    'xlabels': [mlab(p) for p in IDX[-TBL_MONTHS:]],
    'xlabels_long': XL_LONG,
    'summary': summary(),
    # 轴刻度小数位：引擎默认格式器把 2.5 印成「3」、把 0.5% 步长整列印成重复数字，
    # 判据与算法见 build/axisfmt.py（与 build/single.py 共用同一份）。
    'exhibits': axisfmt.fix_all(ex),
    'table': table,
    'notes': NOTES,
    'footer': (f'标的轴横截面 · {" / ".join(s["p"]["zh"] for s in POOL_STATE)} · '
               f'<b>发布门槛：各池共同最新月 {mlab(LATEST)}</b>，'
               f'本期短板 {"、".join(_short_pools)} —— {TRUNC_TXT} · '
               f'<b>主口径 = 定基名义额（张数 × 乘数 × 锁死的 {mlab(BASE_P)} 基期价格，'
               f'汇率同锁基期）</b>，增长率与张数增长率恒等 · '
               '<b>所有占比的分母 = 本池可呈现成员之和，不是这一类标的的行业总量；'
               '这不是市场份额</b> · '
               '缺基期常数的成员一律留空，不用近似值填 · '
               'charts only, no commentary · personal research use'),
}
if SOURCE_DATE:
    payload['source_date'] = SOURCE_DATE          # 查不到就整个字段省掉，渲染端判的是存在性


def main():
    payload_guard.write_dash(OUT, payload, TICKER)
    print(f'共同最新月 {LATEST} | 全页窗口 {START} → {LATEST}（{len(IDX)} 个月）')
    print(f'可画池 {len(POOL_STATE)}/{len(PAGE_POOLS)}：'
          + '、'.join(f'{s["p"]["id"]}({len(s["share"])}家+{len(s["growth"])}张数,'
                      f'{s["months"]}月,{s["p"]["share"]})' for s in POOL_STATE))
    for p, w in POOL_SKIPPED:
        print(f'  整池不画 {p["id"]}：{w}')
    for st in POOL_STATE:
        for m, w in st['dropped']:
            print(f'  留空成员 {st["p"]["id"]}.{m["key"]}：{w}')
    print(f'份额恒等式 max|Σ占比 − 100| = {SHARE_SUM_MAXGAP:.3e} pp')
    print(f'定基/张数同比恒等 max|gap| = {IDENT_MAX:.3e} pp（{len(IDENT_ROWS)} 个单腿成员）')
    if ICE_COV:
        print(f'能源 ICE 覆盖率复算 {ICE_COV["num"]}÷{ICE_COV["den"]}：'
              f'{BASE_MONTH}={ICE_COV["base"]:.1f}%，中位 {ICE_COV["med"]:.1f}%'
              f'（{ICE_COV["min"]:.1f}–{ICE_COV["max"]:.1f}%，{ICE_COV["n"]} 个月）')
    for st in POOL_STATE:
        unit = st['p']['unit'].split(',')[0]
        if st['has_share']:
            body = ('池内占比 ' + mlab(CUR) + '：'
                    + '、'.join(f'{mshort(m)} {float(st["share_pct"][m["key"]][CUR]):.2f}%'
                                for m, _ in st['share'])
                    + f' | 合计 {float(st["tot"][CUR]):,.2f} {unit}')
        else:
            body = ('share=none，只有水平值 ' + mlab(CUR) + '：'
                    + '、'.join(f'{mshort(m)} {float(st["ser"][m["key"]][CUR]):,.2f}'
                                for m, _ in st['share']) + f' {unit}')
        print('  ' + f'{st["p"]["id"]:<22}' + ' ' + body)
    if MD_ODD:
        print(f'⚠ {len(MD_ODD)} 段文案的 Markdown 标记数是奇数，已整段去掉标记：{MD_ODD}')
    print(f'发布日 source_date = {SOURCE_DATE or "（成员里有查不到的，整字段省略）"}')
    print(f'Exhibit 1 汇总表（{len(payload["summary"]["rows"])} 行）+ '
          f'Exhibit {ex[0]["n"]}-{ex[-1]["n"]}（{len(ex)} 张）+ '
          f'Exhibit {table["n"]} 核对表（{len(TBL_ROWS)} 行 × {len(TBL_COLS)} 列）')
    print(f'写出 {OUT}（{os.path.getsize(OUT) / 1024:.1f} KB）')
    print(payload['hub_line'])


if __name__ == '__main__':
    main()
