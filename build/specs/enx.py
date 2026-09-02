# -*- coding: utf-8 -*-
"""Euronext（enx）单公司页配置。

本文件只声明「画哪些列、叫什么、什么单位、什么格式」，**不含任何算术、不含任何取数**。

━━ 为什么这家的 slow_cols 是空的 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
series/enx.csv 的每一个数据列都出自**同一份官方 xlsx**
（euronext_monthly_historical_volumes.xlsx，
文件名固定不带月份，每月原地覆盖），所以所有列同时发布、同一个最新月。
「多少列 / 多少行 / 到哪个月 / 几列在最新月有值 / 几列首末月之间有空洞」这几个数
**一个都不写在文档里** —— 它们每月都变，写死一次就过期一次
（上一版这里写着「全部 71 个数据列……含 month 共 72 个字段」，正是这种数）。
`_shape_zh()` 在 import 期从 series/enx.csv 现算，结果原样印进页尾 notes 的最后一条
（连「空洞是 0」都不预设，数出来几个就印几个）。没有慢腿，`slow_cols` 留空。

（发布节奏另说，**发布日实测于 2026-08、不随 CSV 更新**：至那时共 50 期，
 月末后第 4–13 天，中位数第 8 天；历史最小值第 3 天 —— 2020-06 数据月发布于
 2020-07-03。发布日不在 series/ 里，现算不了，所以这里只能是带日期的一次性实测。
 闸门那一层是 monthly_run.py 的事，不在本文件。）

━━ 为什么口径断点是这一家的重点 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Euronext 是靠连续并购长起来的：都柏林、奥斯陆、米兰、雅典逐个并进主列，
**每并一次，被并的那段历史都不重算**。所以主列在并表月会出现「不是业务增长的跳变」。
最危险的一列是单股衍生品：雅典的单股期货占并表后的绝大部分（具体区间由
`_athex_share()` 现算，序列中文名与页尾图注共用它的结果；**这里不抄一个数** ——
上一版抄的「90–98%」已经被 2026-02 的 89.1% 顶出下沿），
2025-11 那一格若当成增长读，就是 3–6 倍的假跳。

断点月份**一律从 `series/enx_breaks.csv` 读**，不写死 —— 那张台账由 fetch/enx.py
从官方脚注原文自动抽取，官方改脚注时它跟着变，写死的月份不会。

断点**必须逐列限定**，不能画成贯穿全页的红线：2018-01 只影响现货列、2019-07 只影响
股指/单股衍生品与商品列，画到对方的图上就是错的（旧的欧亚合页生成器已经纠正过一次
「2019-07 是现货断点」的口传错误；那张页与它的生成器已于 2026-08-06 删除，
但这条结论本身与页面无关，逐列限定的规矩照旧）。底座 `build/single.py` 的 `breaks` 每条支持一个
可选的 `col`（底座 `Page.breaks_for()` 里那句 `if b['col'] and names and b['col'] not
in names: continue` —— 断点只挂到画了那一列的图上；**写函数名不写行号**，
上一版写的 `single.py:537` 早已漂到 `tail_contiguous()` 头上），所以本文件把台账里的
每一条 (列, 月) 原样带上 `col` 输出 —— 覆盖全部 10 个断点月，且每条红线只出现在
它真正影响的那张图上。既不漏，也不误伤。

不用 `'breaks': 'enx_breaks.csv'` 这种字符串写法（底座也支持）：那样 zh 会取台账的
`footnote` 列，印出来是 'Equity Markets (3)' 这种官方分节编号，读者看不懂。
这里保留读 CSV 拿月份与列，只把「这个月发生了什么」翻成中文。

━━ 📌 本页**不画** `decomp`（量价分解），理由不是缺数据，是图注会说假话 ━━━━━━
数据条件其实够：`adv_cash_adnv_eurbn`（成交额 ADV，单边计）与 `adv_cash_trades_k`
（成交笔数 ADV）都自工作簿起点起零断档（起点与月数由 `_span()` 现算；
**不写「全仓最长的一对」** —— 那句话的判据在别的九个 spec 里，本页现算不到）。
`build/exchanges_eu.py` 的 Exhibit 15 就用这一对画了「成交额 = 笔数 × 每笔均值」的
对数分解，并用三重检验判定「**增长率分解成立、绝对水平不可读**」：

  ① 常数缩放不变性 —— 分解对笔数列乘任何常数完全不变（实测残差 2.1e-14）；
  ② 计数惯例没有中途翻转 —— 惯例一翻，每笔均值会在那一个月跳约 ln2；而排除并表
     断点月之后的实测最大单月跳变远低于它（**幅度与月份这里不抄**，由
     `_conv_stability()` 现算并印进 `_NO_DECOMP_NOTE`；抄一份就是养第二个会过期的数）；
  ③ 断点集合逐个相同。

「绝对水平不可读」的原因：官方同一张表里**金额列单边计、笔数列买卖双边计**
（docs/verify/enx.md 口径坑 6），两者相除得到的不是每笔真实成交额，
而是它除以一个没有独立证据确证的计数因子 —— 自算约 €4 千/笔，只有常识值的一半。
所以那张横截面图**一个每笔均值的绝对数都不印**。

而 `build/single.py` 的 `ex_decomp` 图注**无条件**印出年度派生量的水平值
（`年度{price_zh}（Σ金额 ÷ 数量）… {price_unit}`），没有任何 spec 字段能关掉它。
⇒ 在这一页上用 `decomp`，等于把「不可读的绝对水平」印到页面上。
**宁可少一张图，也不印一个自己都不信的数**（准确优先于覆盖）。
增长这一侧没有丢：末尾一张 `level_yoy` 给出**成交额**的水平值与单月同比，
靠前那张单列组图给出**成交笔数**的单月同比（2026-09 之前那张 12 个月滚动同比的
笔数专图已删 —— 与组图同列同窗口同口径，重复了）；两条金线现在同口径，
它们之差就是每笔均值的增长贡献 —— 全程只有增长率、没有水平值。
"""

import collections
import csv
import math
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_CSV = os.path.join(_ROOT, 'series', 'enx.csv')
_BREAKS_CSV = os.path.join(_ROOT, 'series', 'enx_breaks.csv')

# 断点月的中文说法。**月份不写死在这里** —— 月份与受影响的列都从 CSV 读，
# 这张表只负责把官方英文脚注翻成一句中文。CSV 里冒出没登记的月份时走兜底文案，
# 绝不静默丢弃一个断点。
_BREAK_ZH = {
    '2015-01': 'ETC 从结构化产品并入 ETF 列',
    '2017-01': '现货并入 Euronext Dublin',
    '2018-01': '现货并入 Euronext Oslo',
    '2019-01': '上市统计并入 Dublin 与 Oslo',
    '2019-07': '衍生品与商品并入 Oslo Børs',
    '2021-05': '并入 Borsa Italiana（米兰）；同月发行人家数改计算方法',
    '2023-11': 'Euronext Clearing 扩容，股票清算量已重述',
    '2025-06': '债券含 Euronext ABM、新增挂牌口径扩至所有类型（均已重述）',
    '2025-11': '并入雅典交易所（Euronext Athens）',
    '2026-03': '电力衍生品市场 2026-03-16 起全面运行',
}


def _read_breaks(charted):
    """读 series/enx_breaks.csv，返回 (逐列断点 list, 说明 list)。

    每条形如 {'month': '2018-01', 'zh': '现货并入 Euronext Oslo', 'col': 'adv_cash_adnv_eurbn'}
    —— 带 `col` 的断点只会画在画了那一列的图上（底座 `Page.breaks_for()`），
    所以可以把台账里**全部**断点带出来，不必为了不误伤别的图而丢掉一半。

    只保留本页真的画了的列：底座对 col 不在 series 里的断点会抛 `SpecError` 硬失败
    （`Page.build()` 里那句 "breaks 里 col=… 不在 series/… 里"），
    而画不到的列上的断点纯属噪声。

    台账读不到时**不抛异常**：返回空断点 + 一条显式说明，让「红线没画」这件事
    在页面上说出来，而不是变成沉默的缺失。
    """
    try:
        with open(_BREAKS_CSV, newline='') as fh:
            rows = list(csv.DictReader(fh))
    except (IOError, OSError):
        return [], ['⚠ 读不到 series/enx_breaks.csv，本页未画任何口径断点竖线 —— '
                    'Euronext 的并表跳变因此没有标注，读同比前请自行回官方脚注核对。']
    if not rows:
        return [], ['⚠ series/enx_breaks.csv 为空，本页未画任何口径断点竖线。']

    out, seen = [], set()
    months = collections.defaultdict(set)      # 月 -> 受影响的本页列
    skipped = collections.defaultdict(set)     # 月 -> 台账有、本页没画的列
    for r in rows:
        month = (r.get('break_month') or '').strip()
        col = (r.get('column') or '').strip()
        if not month or not col:
            continue
        if col not in charted:
            skipped[month].add(col)
            continue
        months[month].add(col)
        if (month, col) in seen:               # 同一断点常按多条官方脚注重复登记
            continue
        seen.add((month, col))
        out.append({'month': month, 'col': col,
                    'zh': _BREAK_ZH.get(
                        month, '口径断点（官方脚注原文见 series/enx_breaks.csv）')})
    out.sort(key=lambda b: (b['month'], b['col']))

    note = ['口径断点全部读自 series/enx_breaks.csv（该台账由 fetch/enx.py 从官方脚注'
            '原文自动抽取），本页共 %d 条、覆盖 %d 个断点月，**每条只画在它真正影响的'
            '那张图上**：%s。'
            % (len(out), len(months),
               '；'.join('%s %s（%d 列）' % (m, _BREAK_ZH.get(m, '口径断点'), len(months[m]))
                         for m in sorted(months)))]
    only_skipped = sorted(m for m in skipped if m not in months)
    if only_skipped:
        note.append('台账里另有 %d 个断点月只影响本页没画的列，因此页面上看不到：%s。'
                    % (len(only_skipped),
                       '、'.join('%s（%s）' % (m, '、'.join(sorted(skipped[m])))
                                 for m in only_skipped)))
    return out, note


# ══════════════════════════════════════════════════════════════════════════════
# 图注里要报的数**一个都不写死**：全部在 import 期从 series/enx.csv 现算。
# ⚠ 本页有一条额外纪律：这些函数**只许算增长率与占比，不许算每笔均值的水平值** ——
#   理由见模块 docstring 里的 📌 那一节。
# 任何一步算不出来就退回不含数字的定性版本；缺文件不许在 import 期抛异常。
# ══════════════════════════════════════════════════════════════════════════════
_ROWS = None


def _rows():
    """series/enx.csv 全部行。缓存一份 —— 下面按列现算要遍历 72 次，没必要读 72 遍文件。"""
    global _ROWS
    if _ROWS is None:
        try:
            with open(_CSV, encoding='utf-8') as fh:
                _ROWS = list(csv.DictReader(fh))
        except OSError:
            _ROWS = []
    return _ROWS


def _num(r, col):
    try:
        v = r[col].strip()
    except (KeyError, AttributeError):
        return None
    if not v:
        return None
    try:
        return float(v)
    except ValueError:
        return None


def _assert_all_numeric():
    """入库后的 series/enx.csv 里**一格非数值都不许有** —— 有就停机。

    这是页尾那句「fetch/enx.py 把 "NA" 当缺失丢掉，所以入库后不会留下非数值格」
    的判据。没有这道闸门，那句话就只是一句人写的全称断言：抓取器哪天漏放一个
    "NA" / "n.a." / "-" 进来，`_num()` 会静静地把它当缺失，图上断一笔、
    图注继续印「不会留下非数值格」，而没有任何东西会报错。
    """
    bad = []
    for r in _rows():
        for c, v in r.items():
            if c == 'month' or not (v or '').strip():
                continue
            try:
                float(v)
            except ValueError:
                bad.append('%s/%s=%r' % (r.get('month'), c, v))
    if bad:
        raise SystemExit(
            'series/enx.csv 里有非数值格 %s（共 %d 处）—— 页尾那条注断言「入库后不会'
            '留下非数值格」，判据与数据对不上，先查 fetch/enx.py 再构建'
            % ('、'.join(bad[:5]), len(bad)))


def _span(col):
    """某一列的 (有值月数, 首月, 末月, 首末月之间的空洞数)。列不存在/全空返回四个 None。

    ⚠ 这是本文件里**唯一**能说「这条序列从哪个月开始」的地方 —— 起点一律现算，
    不写死。Euronext 的起点会因为官方回填而向左移动（雅典备注列就是先有 2025-11
    的事件、官方再把备注列回填到 2021-01 的），写死的起点扛不住这种事。
    """
    rs = _rows()
    idx = [k for k, r in enumerate(rs) if (r.get(col) or '').strip()]
    if not idx:
        return (None,) * 4
    return (len(idx), rs[idx[0]].get('month'), rs[idx[-1]].get('month'),
            (idx[-1] - idx[0] + 1) - len(idx))


def _shape_zh():
    """「多少行、到哪个月、多少列在最新月有值、多少列有空洞」——  一句现算的中文。

    这四个数每月都变。**故意连「gaps 全部为 0」都不写死**：印出来的是数出来的数，
    数不是 0 时这句话会自己说实话，而不是变成一句陈年断言。
    """
    rs = _rows()
    if not rs:
        return '（本次未能从 series/enx.csv 复算形状。）'
    cols = [c for c in rs[0] if c != 'month']
    full = holes = 0
    for c in cols:
        n, m0, m1, gap = _span(c)
        if n is None:
            continue
        if m1 == rs[-1].get('month'):
            full += 1
        if gap:
            holes += 1
    return ('本文件 import 期现算 series/enx.csv：%d 行 %s → %s；%d 个数据列（不含 month）里'
            '有 %d 列在 %s 有值、%d 列的首末月之间有空洞。'
            % (len(rs), rs[0].get('month'), rs[-1].get('month'),
               len(cols), full, rs[-1].get('month'), holes))


def _break_months():
    """台账里全部断点月（不分列）—— 计数惯例检验要把这些月排除在外。"""
    try:
        with open(_BREAKS_CSV, newline='') as fh:
            return {(r.get('break_month') or '').strip() for r in csv.DictReader(fh)}
    except (IOError, OSError):
        return set()


def _conv_stability():
    """复算 exchanges_eu.py 的检验 ②：计数惯例有没有中途从单边翻成双边。

    翻转一次，每笔均值（= 成交额 ÷ 笔数）会在那一个月跳约 ln2 ≈ 69.3%。
    所以逐月算 |Δln(每笔均值)|、排除并表断点月（那些月覆盖范围本来就变了），
    看最大的一个离 ln2 有多远。**这是增长率统计量，不是水平值** ——
    本页允许印它，正如本页不允许印任何一个每笔均值的绝对数。

    返回 (可比月数, 最大单月跳变%, 该月份, ln2 的百分数)；算不出全部返回 None。
    """
    bm = _break_months()
    prev_m, prev_v, best = None, None, (0.0, None)
    n = 0
    for r in _rows():
        m = (r.get('month') or '').strip()
        a, b = _num(r, 'adv_cash_adnv_eurbn'), _num(r, 'adv_cash_trades_k')
        v = (a / b) if (a and b) else None
        if v is not None and prev_v is not None and m not in bm:
            n += 1
            j = abs(math.log(v / prev_v)) * 100.0
            if j > best[0]:
                best = (j, m)
        prev_m, prev_v = m, v
    if not n:
        return (None,) * 4
    return n, best[0], best[1], math.log(2.0) * 100.0


def _tradingday_spread():
    v = [d for d in (_num(r, 'trading_days_cash') for r in _rows()) if d]
    if not v:
        return None, None, None
    return min(v), max(v), (max(v) / min(v) - 1.0) * 100.0


_CVN, _CVMAX, _CVM, _LN2 = _conv_stability()
_DMIN, _DMAX, _DSPR = _tradingday_spread()
_SHAPE_ZH = _shape_zh()
_VN, _VM0, _VM1, _VGAP = _span('adv_cash_adnv_eurbn')      # 成交额 ADV
_TN, _TM0, _TM1, _TGAP = _span('adv_cash_trades_k')        # 成交笔数 ADV
_PN, _PM0, _PM1, _PGAP = _span('adv_power_systemprice_futures_gwh')   # 电力衍生品


def _band(lo, hi, nd):
    """把 (lo, hi) 收成一对**印得出来又含得住实测值**的端点：下界向下取、上界向上取。

    ⚠ 上一版这两处（结构化产品量级、雅典占比）都是直接 `%.2f` / `%.0f` 四舍五入
    印出去的，而四舍五入会把区间**收窄**：下界被取大、上界被取小，于是真实读数
    落在页面自己声明的区间之外 —— 一句自称「现算」的话，被它自己现算的那列当场
    证伪（本轮这两处都实际发生了）。端点是要当**边界**用的，就只能一个向下、
    一个向上取。（这里**不举实测数字当例子** —— 举一个就等于再养一个会过期的数。）
    """
    if lo is None or hi is None:
        return None, None
    f = 10.0 ** nd
    return math.floor(lo * f + 1e-9) / f, math.ceil(hi * f - 1e-9) / f


def _col_range(col):
    """一列的 (最小值, 最大值)；算不出返回 (None, None)。

    「结构化产品那列量级很小」那半句的算术底 —— 原先写死成「0.03–0.22 EUR bn/日」，
    而区间每个月都可能被一个新读数顶出去。区间是能现算的，就别抄。
    """
    v = [x for x in (_num(r, col) for r in _rows()) if x is not None]
    return (min(v), max(v)) if v else (None, None)


_assert_all_numeric()
_STRU_MIN, _STRU_MAX = _band(*_col_range('adv_cash_structured_adnv_eurbn'), nd=2)


def _athex_month(main):
    """雅典并进 `main` 这一列的月份 —— 从 series/enx_breaks.csv 读，不写死。

    ⚠ **这个起点非有不可**：athex_* 备注列被官方回填到 2021-01，而主列直到并表月
    才含雅典。拿全部重叠月去算「雅典占主列多少」，得到的是备注列 ÷ 不含雅典的主列
    —— 那个比值可以大到几百倍，根本不是要说的那件事。
    """
    months = []
    try:
        with open(_BREAKS_CSV, newline='') as fh:
            for r in csv.DictReader(fh):
                if (r.get('column') or '').strip() != main:
                    continue
                m = (r.get('break_month') or '').strip()
                if m:
                    months.append(m)
    except (IOError, OSError):
        return None
    ath = [m for m in months if '雅典' in _BREAK_ZH.get(m, '')]
    return min(ath) if ath else (max(months) if months else None)


def _athex_share(main, note_col):
    """并表之后雅典占主列多少（%）的 (最小, 最大, 月数, 并表月)；算不出返回 (None,)*4。

    ⚠ 这个区间 2026-08-19 之前写死成「90–98%」，写在四处（模块 docstring、组注释、
    **序列中文名**、页尾图注）。实测已经掉出下沿：2026-02 是 89.1%。
    区间会被每一个新月份顶宽，写死的必然先烂 —— 而它完全能现算。
    """
    m0 = _athex_month(main)
    if not m0:
        return (None,) * 4
    v = []
    for r in _rows():
        if r['month'] < m0:
            continue
        m, a = _num(r, main), _num(r, note_col)
        if m and a is not None:
            v.append(a / m * 100.0)
    return (min(v), max(v), len(v), m0) if v else (None,) * 4


_ATH_LO, _ATH_HI, _ATH_N, _ATH_M0 = _athex_share(
    'adv_singlestock_futures_kcontracts', 'athex_adv_singlestock_futures_kcontracts')
#: 序列中文名与图注共用同一个区间字符串 —— 两处各写各的，迟早只改一处。
#: 端点走 `_band()`（下界向下取、上界向上取）：上一版直接 `%.0f` 四舍五入，
#: 而四舍五入会把上界取小、下界取大 —— 印出来的区间装不下自己的数据。
_ATH_BLO, _ATH_BHI = _band(_ATH_LO, _ATH_HI, 1)
_ATH_ZH = ('%.1f–%.1f%%' % (_ATH_BLO, _ATH_BHI)) if _ATH_BLO is not None else '绝大部分'

_NO_DECOMP_NOTE = (
    '📌 <b>本页刻意不画量价分解图。</b>数据条件是够的（'
    # ⚠ 这里原先还写着「是全仓最长的一对」。那是一句**跨页**的最高级断言：判据散在
    #   别的九个 spec 里，本页现算不到，别页加一个月或换一列它就悄悄变假 —— 而它对
    #   「本页为什么不画这张图」这个论点一点用都没有。⇒ 删掉，只留本页自己数得出的两个数。
    + ((f'成交额 ADV 与成交笔数 ADV 都是 {_VM0} 起 {_VN} 个月、首末月之间 {_VGAP} 个空洞'
        if (_VN and (_VN, _VM0, _VGAP) == (_TN, _TM0, _TGAP)) else
        '成交额 ADV 与成交笔数 ADV 逐月成对'))
    + '），欧洲横截面页 '
    '<code>build/exchanges_eu.py</code> 的 Exhibit 15 就用这一对画了'
    '「成交额 = 笔数 × 每笔均值」的对数分解。但那张图的结论是'
    '<b>「增长率分解成立、绝对水平不可读」</b>：官方同一张表里金额列<b>单边计</b>、'
    '笔数列<b>买卖双边计</b>，两者相除得到的不是每笔真实成交额，'
    '而是它除以一个我们没有独立证据确证的计数因子，所以那张图<b>一个绝对数都不印</b>。'
    + ((f'本页在 import 期复算了它的关键检验：排除并表断点月后的 {_CVN} 个可比月里，'
        f'每笔均值的最大单月跳变是 <b>{_CVMAX:.1f}%</b>（{_CVM}），'
        f'远低于计数惯例翻转会造成的 ln2 ≈ {_LN2:.1f}% —— '
        f'惯例确实没有中途翻过，所以<b>增长</b>那一侧可信。'
        if _CVMAX is not None else
        '（本次未能从 CSV 复算该检验。）'))
    + '而 <code>build/single.py</code> 的量价分解图注会<b>无条件</b>印出年度每笔均值的'
      '水平值，没有任何 spec 字段能关掉它。⇒ 在这一页上画那张图，等于把一个'
      '「自己都不信的绝对数」印到页面上。'
      '<b>宁可少一张图</b>：增长这一侧没有丢 —— 成交额与成交笔数各自的<b>单月同比</b>'
      '都在页面上，只是不在同一张图里：成交笔数那条在靠前的组图'
      '「现货成交笔数（⚠ 买卖双边计，含 reported trades；次轴：单月同比）」上，'
      '成交额那条在页尾的「现货成交额：水平值与单月同比」上'
      '（<b>按标题点名，不写 Exhibit 号</b> —— 图号会随分组增删整体位移）。'
      '<b>两条金线之差</b>就是每笔均值的增长贡献，全程只有增长率、没有水平值。'
      '2026-09 之前这两条金线一条是单月、一条是 12 个月滚动，相减是错的；'
      '现在同为单月口径，可以直接对读（严格成立是在对数上，见页尾那张图的图注）。'
)

_NOTE_TTM_VAL = (
    '<b>柱与线取自同一列</b>（<code>adv_cash_adnv_eurbn</code>，官方直接发布的当月'
    '日均 ADNV）：柱是水平值，金线是它自己的<b>单月同比</b> —— 拿这根柱除以 12 根柱'
    '之前那根就是线上这一点，中间没有任何还原步骤。'
    + (f'⚠️ 因为柱是<b>日均</b>，「这个月多开了几天市」这一层已经在柱里除掉了：'
       f'本序列覆盖期内每月 {_DMIN:.0f}–{_DMAX:.0f} 个交易日、两端相差 {_DSPR:.0f}%，'
       f'若柱画的是当月合计，这 {_DSPR:.0f}% 会原样进到同比里。'
       if _DSPR is not None else '')
    + '<b>与「现货成交笔数」那张组图成对读</b>（本页靠前，组名带「次轴：单月同比」）：'
      '<b>两条金线之差读出来的就是「每笔平均成交额」的增长贡献</b> —— '
      '这是本页能给出的全部分解信息，而且它<b>只用增长率</b>，'
      '绕开了「每笔均值的绝对水平不可读」那个坑。两条线现在同为单月口径，可以直接对读。'
      '⚠️ <b>「两条金线之差」严格成立是在对数上</b>：ln 成交额 = ln 笔数 + ln 每笔均值；'
      '增长率大时（例如 +40% 以上）要按对数读，不要拿两个百分数直接相减去汇报。'
    + '⚠️ 这一列是<b>单边计</b>（官方表头 "single counted"），与笔数列'
      '（买卖双边计）不是同一种计数惯例 —— 两条线可以比<b>增长</b>'
      '（双边计等价于整列乘一个常数，而同比对常数缩放恒等不变），'
      '但相除得到的每笔均值绝对水平不可读，本页因此不印它（见页尾 📌 那一条）。'
)


# ── 头条 ───────────────────────────────────────────────────────────────────
# 两条都自工作簿起点 2012-01 起、首末月之间没有空洞（月数与空洞数由 `_span()` 现算，
# 印在 _NO_DECOMP_NOTE 里；这里不复述一个会过期的数字）。
# 用两条而不是一条，且刻意取自**两张不同的官方 sheet**（Equity Markets / FICC Markets）：
# 门槛判定因此不会被单张 sheet 的静默解析失败绕过去。
# adv_cash_adnv_eurbn 同时是 fetch/enx.py 自己的 ANCHOR（判断「这个月真的有数据」的锚）。
HEADLINE = [
    {'col': 'adv_cash_adnv_eurbn', 'zh': '现货 ADV（全品种，单边计）',
     'unit': 'EUR bn/day', 'fmt': 'f1'},
    {'col': 'adv_commodity_futures_kcontracts', 'zh': '商品期货 ADV（MATIF 农产品）',
     'unit': 'k contracts/day', 'fmt': 'f1'},
]

# ── 分组 ───────────────────────────────────────────────────────────────────
# 列名全部 head -1 series/enx.csv 核过。单边 / 双边计一律写进 zh 或 notes ——
# 同一张官方表里两种计数方式混着放，每引用一列都要回表头看分组行。
#
# 两条头条列在下面的组里**再出现一次是故意的**：头条的契约职责是「定共同最新月与门槛」，
# 它会不会同时被画成图由底座决定。列在组里 ⇒ 底座只画组时不会丢掉旗舰序列；
# 若底座也画头条，去重是底座一行的事。反过来（漏掉旗舰图）修起来贵得多。db1.py 同约定。
GROUPS = [
    # Total ≡ Equities + ETF + Structured 是官方恒等式，fetch/enx.py 每月撞一次；
    # 结构化产品那一列量级很小（0.03–0.22 €bn/日），入图是为了让这条恒等式看得见。
    {'zh': '现货市场（Cash）', 'cols': [
        {'col': 'adv_cash_adnv_eurbn', 'zh': '成交额 ADV（全品种，单边）',
         'unit': 'EUR bn/day', 'fmt': 'f1'},
        {'col': 'adv_cash_equities_adnv_eurbn', 'zh': '股票与投资基金（单边）',
         'unit': 'EUR bn/day', 'fmt': 'f1'},
        {'col': 'adv_cash_etf_adnv_eurbn', 'zh': 'ETF（单边）',
         'unit': 'EUR bn/day', 'fmt': 'f2'},
        {'col': 'adv_cash_structured_adnv_eurbn', 'zh': '结构化产品（单边）',
         'unit': 'EUR bn/day', 'fmt': 'f3'},
    ]},

    # ⚠ 笔数与清算笔数原先挂在上面那一组里，但它们各自是**单位桶里的独苗**
    #   （k trades/day 与 k contracts/day 各一列），底座对单桶画 gs_bar，
    #   而 gs_bar 的次轴是**单月同比**。tools/check_yoy_caliber.py 的口径矩阵实测
    #   （全历史、死区 ±0.5pp，2026-08-18 复算）：成交笔数有 40 个月、股票清算有 4 个月
    #   与 12 个月滚动口径**符号相反**。
    #   ⚠ 这类计数随窗口与新月份变，别当常量引用 —— 复算方法：
    #     tools/check_yoy_caliber.py 的 build_index() + sign_flips()。
    #   本表里没有同单位同量级的第二条列可以同轴（athex 那两条只有主列的 3–6%，
    #   同轴等于画一条贴地线），所以改成**各自单列一组、口径写进组名** ——
    #   单月是全站唯一口径（CONTRACT §6.1 第 1 条），§6.6 的自动判据要求它写进标题
    #   （R4，不写就报 🟡）。
    #   ⚠️ 2026-09 全站改单月口径之后，**这张就是成交笔数唯一的一张图**：
    #   末尾那张「12 个月滚动同比专图」与它同列同窗口同口径，已经删掉。
    #   页尾 level_yoy 里「现货成交额」那张的图注要拿本图的金线成对读（两条金线之差
    #   = 每笔均值的增长贡献），所以本组不能删 —— 它同时还管页尾核对表那一列。
    {'zh': '现货成交笔数（⚠ 买卖双边计，含 reported trades；次轴：单月同比）', 'cols': [
        {'col': 'adv_cash_trades_k', 'zh': '成交笔数（⚠ 买卖双边计，含 reported trades）',
         'unit': 'k trades/day', 'fmt': 'f0'},
    ]},

    {'zh': '股票清算笔数/手数（单边，2022-01 起；次轴：单月同比）', 'cols': [
        {'col': 'adv_shares_cleared_kcontracts', 'zh': '股票清算笔数/手数（单边，2022-01 起）',
         'unit': 'k contracts/day', 'fmt': 'f0'},
    ]},

    # 期货与期权是官方分开存的两列，没有合计列 —— 想看总量要自己加，本页不加。
    {'zh': '股指衍生品（CAC 40 / AEX / BEL 20 / FTSE MIB / OBX 等）', 'cols': [
        {'col': 'adv_index_futures_kcontracts', 'zh': '指数期货 ADV',
         'unit': 'k contracts/day', 'fmt': 'f1'},
        {'col': 'adv_index_options_kcontracts', 'zh': '指数期权 ADV',
         'unit': 'k contracts/day', 'fmt': 'f1'},
        {'col': 'oi_index_futures_kcontracts', 'zh': '指数期货未平仓（月末）',
         'unit': 'k contracts', 'fmt': 'f0', 'stock': True},
        {'col': 'oi_index_options_kcontracts', 'zh': '指数期权未平仓（月末）',
         'unit': 'k contracts', 'fmt': 'f0', 'stock': True},
    ]},

    # ⚠ 全表最危险的一组：2025-11 并入雅典之后，雅典的单股期货占了并表后的绝大部分
    #   （区间见 `_ATH_ZH`，现算）。那一格是口径跳变不是增长。
    #   读同比必须先看「Athens 并表备注列」那一组。
    {'zh': '单股衍生品（⚠ 2025-11 并入雅典后口径跳变，见备注列）', 'cols': [
        {'col': 'adv_singlestock_futures_kcontracts', 'zh': '单股期货 ADV',
         'unit': 'k contracts/day', 'fmt': 'f1'},
        {'col': 'adv_singlestock_options_kcontracts', 'zh': '单股期权 ADV',
         'unit': 'k contracts/day', 'fmt': 'f1'},
        {'col': 'oi_singlestock_futures_kcontracts', 'zh': '单股期货未平仓（月末）',
         'unit': 'k contracts', 'fmt': 'f0', 'stock': True},
        {'col': 'oi_singlestock_options_kcontracts', 'zh': '单股期权未平仓（月末）',
         'unit': 'k contracts', 'fmt': 'f0c', 'stock': True},
    ]},

    # 巴黎 MATIF 的农产品（小麦 / 玉米 / 菜籽），**不是能源**。
    # 跨家配对只能配 cme.adv_ag_kcontracts，绝不能配 adv_energy_kcontracts。
    {'zh': '商品衍生品（巴黎 MATIF 农产品，非能源）', 'cols': [
        {'col': 'adv_commodity_futures_kcontracts', 'zh': '商品期货 ADV',
         'unit': 'k contracts/day', 'fmt': 'f1'},
        {'col': 'adv_commodity_options_kcontracts', 'zh': '商品期权 ADV',
         'unit': 'k contracts/day', 'fmt': 'f1'},
        {'col': 'oi_commodity_futures_kcontracts', 'zh': '商品期货未平仓（月末）',
         'unit': 'k contracts', 'fmt': 'f0', 'stock': True},
        {'col': 'oi_commodity_options_kcontracts', 'zh': '商品期权未平仓（月末）',
         'unit': 'k contracts', 'fmt': 'f0', 'stock': True},
    ]},

    {'zh': 'MTS 固定收益（欧洲主权债）', 'cols': [
        {'col': 'adv_mts_cash_eurbn', 'zh': 'MTS 现券 ADV（欧洲主权债，单边）',
         'unit': 'EUR bn/day', 'fmt': 'f1'},
        {'col': 'taadv_mts_repo_eurbn', 'zh': 'MTS 回购 TAADV（期限调整后，官方主口径）',
         'unit': 'EUR bn/day', 'fmt': 'f0'},
    ]},

    # 下面两条与 MTS 那两条**单位不同**（EUR mn/day、USD bn/day），底座本来就会把它们
    # 拆成两张单桶 gs_bar；原先它们与 MTS 同组，只是让组名读起来像一张图而已。
    # 实测（同上，2026-08-18 复算）债券 ADV 有 40 个月、FX 即期有 43 个月与 12 个月滚动口径
    # **符号相反**，所以口径写进各自的组名。
    # 拿 MTS 那两条硬凑同轴不是办法：MTS 现券是 EUR bn 量级、这一条是 EUR mn 量级，
    # 差两三个数量级，小的那条振幅只占画布百分之一，等于白画。
    {'zh': 'MTS 以外的债券成交 ADV（次轴：单月同比）', 'cols': [
        {'col': 'adv_other_fixed_income_eurm', 'zh': 'MTS 以外的债券成交 ADV',
         'unit': 'EUR mn/day', 'fmt': 'f0'},
    ]},

    # ⚠ adv_fx_spot_usdbn 是**美元**，不是欧元。整页只有这一列不是 EUR，
    #   所以它在本表里天然没有同单位的同伴。
    {'zh': 'Euronext FX 即期 ADV（⚠ 美元，单边；次轴：单月同比）', 'cols': [
        {'col': 'adv_fx_spot_usdbn', 'zh': 'Euronext FX 即期 ADV（⚠ 美元，单边）',
         'unit': 'USD bn/day', 'fmt': 'f1'},
    ]},

    # 电力现货是 Nord Pool，**买卖双边计**，且分母是自然日不是交易日。
    # 电力衍生品 2026-03-16 才全面上线（官方 FICC Markets 脚注 (5) 原文），序列因此很短 ——
    # 到底几个月由 `_span()` 现算，印在页尾 notes 里，这里不写死。
    {'zh': 'Nord Pool 电力（现货双边计；衍生品 2026-03 起）', 'cols': [
        {'col': 'adv_power_dayahead_twh', 'zh': '日前市场 ADV（双边，除自然日）',
         'unit': 'TWh/day', 'fmt': 'f2'},
        {'col': 'adv_power_intraday_twh', 'zh': '日内市场 ADV（双边，除自然日）',
         'unit': 'TWh/day', 'fmt': 'f3'},
        {'col': 'adv_power_systemprice_futures_gwh', 'zh': '系统价格期货 ADV（2026-03 起）',
         'unit': 'GWh/day', 'fmt': 'f0'},
        {'col': 'adv_power_epad_futures_gwh', 'zh': 'EPAD 期货 ADV（2026-03 起）',
         'unit': 'GWh/day', 'fmt': 'f0'},
        {'col': 'oi_power_deriv_notional_gwh', 'zh': '电力衍生品名义未平仓（月末，2026-03 起）',
         'unit': 'GWh', 'fmt': 'f0c', 'stock': True},
    ]},

    # 上市家数 / 只数 / 市值都是**月末时点值**；新增挂牌与募资额是**当月总量**。
    # listed_funds 起点 2019-01（2018 全年官方写的是字面量 'NA'，不是 0）。
    {'zh': '上市公司、挂牌产品与募资', 'cols': [
        {'col': 'issuers_equities', 'zh': '股票发行人家数（月末）',
         'unit': 'issuers', 'fmt': 'f0', 'stock': True},
        {'col': 'listed_etfs', 'zh': '挂牌 ETF 只数（月末）',
         'unit': 'instruments', 'fmt': 'f0c', 'stock': True},
        {'col': 'listed_bonds', 'zh': '挂牌债券只数（月末，2025-06 起含 ABM）',
         'unit': 'instruments', 'fmt': 'f0c', 'stock': True},
        {'col': 'listed_funds', 'zh': '挂牌基金只数（月末，2019-01 起）',
         'unit': 'instruments', 'fmt': 'f0c', 'stock': True},
        {'col': 'money_raised_new_listings_eurm', 'zh': '当月新上市募资额（含超额配售）',
         'unit': 'EUR mn/month', 'fmt': 'f0c'},
        {'col': 'money_raised_followon_eurm', 'zh': '当月再融资募资额',
         'unit': 'EUR mn/month', 'fmt': 'f0c'},
        {'col': 'mktcap_eurtn', 'zh': '挂牌总市值（月末，2022-01 起）',
         'unit': 'EUR tn', 'fmt': 'f2', 'stock': True},
    ]},

    # 家数是这一组里唯一的 listings/month 列 ⇒ 单桶 gs_bar ⇒ 次轴单月同比。
    # 实测（同上，2026-08-18 复算）有 20 个月与 12 个月滚动口径符号相反
    # （最刺眼的一格是 2024-10：单月 +33.3% vs 滚动 −43.3%）。
    # 家数是小整数序列（个位到十几），单月同比天生毛刺极大 —— 口径写进组名。
    # 不给它配 level_yoy：新增挂牌家数在多个月为个位数，换哪种同比口径都救不了
    # 而多画一张图会让读者以为那条线更可信。
    {'zh': '当月新增股票挂牌家数（次轴：单月同比）', 'cols': [
        {'col': 'new_listings_equities', 'zh': '当月新增股票挂牌家数',
         'unit': 'listings/month', 'fmt': 'f0'},
    ]},

    # ⚠ 组名里不能写「五家 CSD」：官方 Securities Services 脚注 (1) 原文
    #   "Includes figures from Euronext Athens since November 2025" —— Total 列在
    #   2025-11 之前只含哥本哈根 / 米兰 / 奥斯陆 / 波尔图四家，雅典是与它并列的备注列。
    #   本机对着官方分地明细复核过：2022-01 四地相加 = Total，2025-11 起要五地相加才 = Total。
    # 两条列单位不同（EUR bn 与 mn instructions/month）⇒ 各自单桶 gs_bar ⇒ 次轴是**单月同比**，
    #   按 CONTRACT.md §6 写进组名（托管资产那条是存量，底座会自己补「存量，期末口径」）。
    {'zh': '结算与托管（四家 CSD，2025-11 起含雅典成五家；2022-01 起；次轴：单月同比）', 'cols': [
        {'col': 'csd_auc_eurbn', 'zh': 'CSD 托管资产（月末时点）',
         'unit': 'EUR bn', 'fmt': 'f0c', 'stock': True},
        {'col': 'csd_settlement_instructions_m', 'zh': '当月结算指令笔数',
         'unit': 'mn instructions/month', 'fmt': 'f1'},
    ]},

    # ★ 这一组是读懂 2025-11 那条红线的钥匙，不是可有可无的附录。
    #   官方把雅典做成**贯穿全历史的备注列**（2021-01 起），主列只从 2025-11 起含雅典。
    #   ⇒ 主列 + 备注列 = 官方 pro-forma 口径（实测能精确复现官方季报的备考数）；
    #     主列 − 备注列 = legacy Euronext（旧口径）。
    #   实测 Q2-25 单股衍生品：主列 19,608,871 + 雅典 = 22,791,315 = 官方备考数（相对差 0）。
    # 现货那条备注列在这一组里同样是单桶（EUR bn/day 只有它一条）⇒ gs_bar + 单月同比。
    # 单列一组、口径写进组名；不能把声明写在下面那一组的组名上 ——
    # 那一组的两条 k contracts/day 同轴成 lines、**根本没有次轴同比**，
    # 写上去就成了一句假话（口径断言不许无条件写，SINGLE_SPEC §4 最后一行）。
    #
    # ⚠️ unit / fmt 这两格**不要为了躲叠字去改**（2026-08-19 裁决，visual_qa 🟡 两条）。
    #   现象：窗口拉到 2016-01 之后本图 127 期通栏，末柱（Jul-26 = 0.325）的柱顶数值标签
    #   与右轴刻度「150%」相叠 12.0px²（1280 视口）/ 12.3px²（768）—— 🟡 门槛正好 12.0，
    #   🔴 是 60。这不是新发现：`chartscale.audit()` 每次构建都在喊
    #   「Exhibit 20 柱顶标签压轴刻度：0.325 宽 20.0px > 预算 17.3px」
    #   （设计宽度口径 band = 1060/127 = 8.35px，预算 = band + 12 − 2×LAB_GAP）。
    #   浏览器实测几何（Chrome 151、1280 视口、fscale 1.7）：绘图区右沿 x=1076.8，
    #   末柱中心 1072.94，居中锚的「0.325」bbox 宽 34.02 ⇒ 右端 1089.94，探出绘图区 13.1px，
    #   而右轴刻度栏只有 fscale(6)=10.2px。横向实压 2.94px、纵向墨迹 4.08px；
    #   柱顶标签画在刻度**之后**（引擎先画右轴刻度、再建数据层 g），白描边把刻度打了个洞，
    #   两个数放大 5 倍目视都读得出。
    #   根因在引擎：右轴刻度只给 priorityLabs（次轴末点读数）让位，柱顶数值标签不在其列
    #   —— 左轴那半边早就会给数值标签让位了，右轴这半边没有。那是 24 页共用的
    #   assets/charts.js，本轮不动。
    #   payload 侧三个杠杆，三个都比这 2.94px 贵：
    #     · 本文件给列加 `scale`：那是**列级恒等换算**，`Page.ser()` 一乘贯穿全页，
    #       末尾 13 个月核对表跟着变成百万计，就没法「与官方披露逐格对账」了
    #       —— 理由原文见 build/chartscale.py 模块头「为什么不是在 spec 里给列加 scale」。
    #     · 走 chartscale 的**显示缩放**（只动 exhibits、不碰核对表，正是为这类事造的）：
    #       它的 `_FACTORS` 只有 1e9/1e6/1e3 三档**除法**，`_factor()` 还要求 cmax/k >= 1，
    #       按构造只往下缩。0.325 要的是「×1000」，不在它射程内；补一档要改 chartscale.py，
    #       那同样是 34 页共用的。
    #     · fmt f3 → f2（「0.33」宽 15.6px，能进预算）：序列低端 0.045 会印成 0.05，
    #       正是 charts.js FMT 高精度档那段注释点名的「3 位小数掉到 1 位有效数字，
    #       图还画得出、数字没了意义」。
    #   顺带记一笔：把两条同单位的雅典分列拉进本组凑成 lines（那样就没有柱顶标签与右轴了）
    #   也不行 —— athex_adv_cash_etf_adnv_eurbn 全历史最大 0.0006（占总额 0.15%）、
    #   athex_adv_cash_equities_adnv_eurbn 与总额差同样 0.15%，画出来是两条重合线
    #   加一条贴地线，比现在难读得多。
    #   最后，这一条是**随数据漂的**，不是固定错位：末柱标签的高度由当月值定，右轴刻度是
    #   50% 一格的固定网格，两者撞上纯属这一期的落点（本页共 22 张带次轴的 gs_bar，
    #   同一条构造下只有这一张撞上）。
    {'zh': 'Athens 并表备注列：雅典现货 ADV（次轴：单月同比）', 'cols': [
        {'col': 'athex_adv_cash_adnv_eurbn', 'zh': '雅典现货 ADV（备注列，2021-01 起）',
         'unit': 'EUR bn/day', 'fmt': 'f3'},
    ]},

    {'zh': 'Athens（Athex）并表备注列 —— 2025-11 红线的桥', 'cols': [
        {'col': 'athex_adv_singlestock_futures_kcontracts',
         'zh': '雅典单股期货 ADV（占并表后 %s）' % _ATH_ZH,
         'unit': 'k contracts/day', 'fmt': 'f1'},
        {'col': 'athex_adv_index_futures_kcontracts', 'zh': '雅典指数期货 ADV',
         'unit': 'k contracts/day', 'fmt': 'f2'},
        {'col': 'athex_issuers_equities', 'zh': '雅典股票发行人家数（月末）',
         'unit': 'issuers', 'fmt': 'f0', 'stock': True},
    ]},
]


# 本页真的画了哪些列 —— 断点只挂到这些列上。放在 GROUPS 之后算，顺序不能反。
_CHARTED = frozenset([c['col'] for c in HEADLINE]
                     + [c['col'] for g in GROUPS for c in g['cols']])
_BREAKS, _BREAK_NOTES = _read_breaks(_CHARTED)


def _starts_zh():
    """把本页画了的列按**现算出来的起点月**分组，列成一句中文。

    原先这一条是手写的枚举，手写的枚举有两个必坏的地方：官方回填会让起点向左移
    （雅典备注列就是这么来的），新并购会长出新的起点月。所以起点一律现算。
    最早那个月（= 工作簿自己的起点）只报条数不报列名，否则半页都是它。
    """
    zh = {}
    for c in HEADLINE:
        zh.setdefault(c['col'], c['zh'])
    for g in GROUPS:
        for c in g['cols']:
            zh.setdefault(c['col'], c['zh'])
    by = collections.defaultdict(list)
    for col, name in zh.items():
        m0 = _span(col)[1]
        if m0:
            by[m0].append(name)
    if not by:
        return ''
    ms = sorted(by)
    parts = ['<b>%s</b>：%s' % (m, '、'.join(sorted(by[m]))) for m in ms[1:]]
    parts.append('其余 %d 条自 <b>%s</b>（工作簿自己的起点）' % (len(by[ms[0]]), ms[0]))
    return '；'.join(parts)


_STARTS_ZH = _starts_zh()



SPEC = {
    'ticker': 'enx',
    'name':   'Euronext',
    'title':  'Euronext（ENX）月度经营指标',
    'csv':    'enx.csv',
    'ccy':    'EUR',
    'source': ('Source: Euronext IR monthly historical volumes '
               '(euronext_monthly_historical_volumes.xlsx); format after Goldman Sachs GIR'),

    'headline': HEADLINE,
    'groups':   GROUPS,

    # 全部数据列出自同一份 xlsx、同时发布 ⇒ 没有慢腿。
    # 「有几列在最新月真有值」由 `_shape_zh()` 现算并印在页尾 notes，这里不复述数字。
    'slow_cols': [],

    # 月份与受影响的列都从 series/enx_breaks.csv 读，不写死；逐列限定，见模块 docstring。
    'breaks': _BREAKS,

    # 📌 'decomp' 刻意留空 —— 理由见模块 docstring 的 📌 一节与 notes 里那一条。
    # 不是没有数据，是底座的分解图注会无条件印出「每笔均值」的绝对水平，
    # 而这一家的绝对水平不可读（金额单边计 vs 笔数双边计）。

    # ══ 水平值 + 次轴单月同比 ════════════════════════════════════════════════
    # ⚠️ **原来这里有两条（成交额 + 成交笔数），2026-09 删掉了笔数那条。**
    # 它当时的存在理由是「组图那张画单月同比、这张画 12 个月滚动同比，并列让读者
    # 看见两种口径差多少」。全站同比统一成单月之后，笔数那条与组图
    # 「现货成交笔数（…；次轴：单月同比）」变成**同一列、同一窗口、同一口径**，
    # 画出来一模一样 —— 所以删重复，而不是留一张影子图。
    # 「两条金线之差 = 每笔均值的增长贡献」这个读法一点没丢：另一条金线就在那张组图上，
    # 两条现在同口径，反而比从前（一张滚动、一张单月）更能直接相减。
    # 笔数列不能反过来从 groups 里删：groups 还管页尾核对表，删了那一列就从表上消失。
    'level_yoy': [
        {'zh': '现货成交额',
         # adv_ 前缀 = 当月日均（官方直接发布 ADNV，不是本仓算的）。
         # 次轴是**本列自己的单月同比**，不再乘 trading_days_cash 还原成当月合计 ——
         # 日均 ÷ 去年同月日均已经把交易日数除掉了，还原一步反而把它请回来。
         'level': {'col': 'adv_cash_adnv_eurbn', 'zh': '日均成交额（全品种，单边）',
                   'unit': 'EUR bn/day', 'fmt': 'f1'},
         'note': _NOTE_TTM_VAL},
    ],

    'notes': _BREAK_NOTES + [
        _NO_DECOMP_NOTE,

        '⚠ 现货断点与衍生品断点不是同一批月份，别搞混：现货的都柏林在 2017-01、'
        '奥斯陆在 **2018-01**；而 2019-07 那个奥斯陆断点属于**股指与单股衍生品、商品**列。'
        '上市统计的都柏林与奥斯陆则是 2019-01。这三条线在官方脚注里分属 '
        'Equity Markets (3) / (5) 与 Capital Markets (1)，不是同一条脚注。'
        '本页的红线逐列限定，所以现货图上不会出现 2019-07、衍生品图上不会出现 2018-01。',

        '⚠ 2025-11 并入雅典是本页最容易读错的一格。官方把雅典做成**贯穿全历史的备注列**'
        '（athex_*，2021-01 起），主列只从 2025-11 起含雅典 ⇒ 主列+备注列 = 官方 pro-forma、'
        '主列−备注列 = legacy Euronext。最危险的是单股期货：'
        + ((f'雅典占并表后的 {_ATH_ZH}（{_ATH_M0} 起 {_ATH_N} 个月现算的区间），')
           if _ATH_LO is not None else '雅典占并表后的绝大部分，')
        + '不做处理时 2025-11 那一格是 3–6 倍的假跳。实测 Q2-25 单股衍生品主列 19,608,871 + '
        '雅典 = 22,791,315，与官方备考数相对差 0。',

        '⚠ 同一张官方表里混着单边计与双边计，本页逐列标注：现货成交额单边、'
        '现货成交笔数**双边**（且含 reported trades）、股票清算单边、债券清算双边、'
        'Nord Pool 电力**双边**。跨家对比前先看这一条。',

        '⚠ adv_fx_spot_usdbn 是**美元**不是欧元 —— 整页只有这一列不是本币 EUR。'
        '官方表头写 "Volume (in M$, single counted)"，但单元格里是绝对美元：'
        '2019-01 那格 441,099,188,988.6 ÷ 22 个交易日 ÷ 1e6 = $20,050m，'
        '与当期新闻稿原文 "stood at $20,050 million" 一致。',

        '现货恒等式：adv_cash_adnv_eurbn ≡ equities + etf + structured，'
        'fetch/enx.py 每月撞一次，撞得上说明四列一格没错行。结构化产品那列量级很小'
        + ((f'（现算 {_STRU_MIN:.2f}–{_STRU_MAX:.2f} EUR bn/日）')
           if _STRU_MIN is not None else '')
        + '，入图是为了让这条恒等式看得见。',

        'listed_funds 的起点是 **2019-01** 不是 2018-01：官方 2018 全年那 12 格写的是'
        # ⚠ 原文这里还有一句「这是整个工作簿里唯一的非数值污染」。那是对**官方 xlsx**
        #   的全称断言：xlsx 不在本仓（fetch/enx.py 每月现下、当场把非数值当缺失丢掉），
        #   仓库里没有任何东西能复算它，也没有任何东西会在它变假时报警。⇒ 删掉断言，
        #   只留能核的那一半：入库之后的 series/enx.csv 里一格非数值都没有。
        '字面量字符串 "NA"，不是 0，也不是缺失 —— <code>fetch/enx.py</code> 把它当缺失丢掉，'
        '所以入库后的 series/enx.csv 里不会留下非数值格。',

        '电力衍生品（系统价格期货 / EPAD / 名义未平仓）2026-03-16 才全面上线 —— 官方 '
        'FICC Markets 脚注 (5) 原文 "Power derivatives market became fully operational on '
        '16 March 2026"。'
        + ((f'本页 import 期实测这三列只有 {_PN} 个月（{_PM0} → {_PM1}）。')
           if _PN else '')
        + '这不是数据缺失，2026-03 之前官方没有这个市场。同比要等到 2027-03 之后才有意义。',

        # ═══ 本页最容易被误读成「数据缺失」的一条 ═══════════════════════════════
        # 抓取器没有窗口：fetch/enx.py 只下一份滚动全历史 xlsx、遍历全部 Period 行。
        # 所以「某列早于某月为空」在这一家**只可能**是官方那一格本来没内容。
        # 下面每个日期都回 Euronext 官方新闻稿 / 工作簿脚注原文复核过；核不实的不写。
        '📌 <b>左半边空白是业务史，不是数据缺失。</b>抓取器没有任何时间窗口 —— '
        '<code>fetch/enx.py</code> 每月只下一份滚动全历史 xlsx 并遍历它的全部 Period 行，'
        '所以「某列早于某月为空」只能是官方那一格本来就没有内容。逐条对上业务事件：'
        '<b>2020-01 Nord Pool 现货电力</b> —— Euronext 于 <b>2020-01-15</b> 完成收购 Nord Pool '
        '66% 股权与表决权（余下 34% 由原股东输电系统运营商持有），官方自 2020-01-16 起并表，'
        '序列起点与事件同月，是本页唯一一处「起点 = 交割月」；'
        '<b>2020-01 MTS（现券 / 回购 / TAADV）</b> —— MTS 是随 Borsa Italiana Group 进来的，'
        '而那笔交易 <b>2021-04-29</b> 才交割：序列回填到 2020-01，比 Euronext 拥有 MTS 早 15 个月，'
        '<b>是官方的历史回填，不是并表日</b>；'
        '<b>2013-01 Euronext FX</b> —— 前身 FastMatch，Euronext 于 <b>2017-08-14</b> 完成收购约 90% '
        '股权，序列同样回填到被收购方自己的历史，比收购早四年七个月；'
        '<b>2021-01 athex_* 备注列</b> —— 雅典的换股要约 <b>2025-11-19</b> 宣告成功'
        '（接纳期 2025-11-17 截止，约 74% 表决权接受；对价股 2025-11-21 发行、2025-11-24 交割），'
        '官方把雅典做成回填到 2021-01 的备注列，比事件早近五年；'
        '<b>2026-03 电力衍生品</b> —— 官方脚注写死的上线日 2026-03-16，见上一条。',

        '📌 <b>2022-01 那一批是「披露起点」，不是任何一个事件的日期。</b>股票清算 / 债券清算 / '
        '总市值 / CSD 托管与结算全部自 2022-01 起。让这一块成为可能的业务前提是 <b>2021-04-29</b> '
        'Borsa Italiana Group 交割 —— 它同时带来了 Euronext Clearing（原 CC&amp;G）与米兰 CSD '
        'Monte Titoli（今 Euronext Securities Milan）。在那之前 Euronext 的 CSD 只有波尔图 '
        'Interbolsa、奥斯陆 VPS（随 Oslo Børs VPS <b>2019-06-18</b> 完成交割）与哥本哈根 '
        'VP Securities（<b>2020-08-04</b> 完成交割），米兰缺位，一条口径一致的合计根本不存在。'
        '⇒ 四家齐备最早只能到 <b>2021-05</b>，而官方实际从 <b>2022-01</b> 才按月披露 —— '
        '中间那 8 个月是官方选择不发，不是我们没抓到。'
        '（同理：CSD 的 Total 列 2025-11 才含雅典，官方 Securities Services 脚注 (1) 原文 '
        '"Includes figures from Euronext Athens since November 2025"；'
        '本机对着官方分地明细复核：2022-01 四地相加 = Total，2025-11 起要五地相加才 = Total。）',

        '⚠ <b>并购完成日 ≠ 进入主列的月份</b>，本页两者常常差很远，读断点时别把两者混为一谈：'
        '都柏林 <b>2018-03-27</b> 完成收购爱尔兰交易所、自 2018-04-01 并入财报，'
        '而现货成交量的官方脚注写的是 "Euronext Dublin since January 2017"（往前回填 14 个月）、'
        '上市统计写的是 "since January 2019"（往后推 10 个月）；'
        '奥斯陆 <b>2019-06-18</b> 完成收购 Oslo Børs VPS，衍生品脚注写 "since July 2019"'
        '（交割后第一个整月），现货却回填到 "January 2018"（往前 17 个月）。'
        '⇒ 主列的断点月一律以官方脚注为准（本页红线全部读自 series/enx_breaks.csv 的脚注原文），'
        '交割日只用来解释「为什么是这个月」。',

        '各列起点由 import 期现算（<code>_span()</code>，不写死 —— 官方回填会让起点向左移动）：'
        + (_STARTS_ZH or '（本次未能从 CSV 复算起点。）')
        + '。早于起点为空是官方就没有，不是抓漏。',

        '商品衍生品是**巴黎 MATIF 的农产品**（小麦 / 玉米 / 菜籽），不是能源。'
        '跨家配对只能配 cme.adv_ag_kcontracts，配 adv_energy_kcontracts 是错的。',

        'slow_cols 为空：全部列出自同一份官方 xlsx（文件名固定、每月原地覆盖），'
        '同时发布、同一个最新月。' + _SHAPE_ZH
        + '（这四个数每月都变，所以是现算的 —— 不是写死的快照。）',

        '⚠ 不要拿 euronext_latest_month_volumes.xlsx 核对本页的历史值：'
        '它的同比/上年列是**含雅典的 pro-forma**（脚注写 "since January 2025"），'
        '与本页主列的 legacy 基准不同，单股衍生品会差到 23%；'
        '而且它的 FX 是 M$，历史文件的 FX 是绝对美元，两个文件同一序列两种单位。',
    ],
}
