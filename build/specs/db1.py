# -*- coding: utf-8 -*-
"""Deutsche Börse Group（db1）单公司页配置。

本文件只声明「画哪些列、叫什么、什么单位、什么格式」，**不含任何算术、不含任何取数**。
数值在通用底座里算完再进 payload，页面只画不算。

━━ 为什么这家的 slow_cols 特别长 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DB1 一家缝了**三个官方源、两种发布节奏**（fetch/db1.py 模块 docstring「发布节奏」节）。
发布日不在 series/db1.csv 里（CSV 只有数据月），所以下面的带宽**现算不出来**，
只能是带日期的一次性实测 —— 期数与具体天数一律以 notes 里那条（同样标着实测日期的）
为准，**这里不再抄一份**，抄下来的那份没有任何检查会在它过期时报警：

  快腿 Eurex 工作簿   月末后第 2–6 天
  快腿 FWB 现货工作簿 月末后第 1–4 天
  慢腿 集团 IR 台账   月末后约第 10 天（落地页原文 "available as of the second week
                      after the reporting month"）

所以每个月都有一段时间：Eurex / Xetra 列已经有最新月，而 Clearstream / EurexOTC /
360T / EEX / 台账口径成交量这些列**天生是空的**。这不是解析失败，也不是数据缺失。
两条腿各自的最新月**不写在这里**：它是 `_FASTM` / `_SLOWM` 从 CSV 现算的，
notes 里那条印的就是它们的返回值。上一版这里写死了「快腿 2026-07、慢腿 2026-06，
正好差一个月」，而慢腿追上来之后，同一个文件里的注与这段 docstring 就开始互相打脸
—— 正是这一轮要消灭的那种句子。差不差一个月都不影响结论：
慢腿列放进门槛判定，整页就会被拖住整整一个月。

⇒ `slow_cols` 不手抄。fetch/db1.py 的 docstring 口径坑 12 明写「模块常量
   `FAST_LEG_COLUMNS` / `SLOW_LEG_COLUMNS` 就是给下游做这个排除用的，别再手抄一份清单」。
   本文件照办：能 import 到就从那个常量派生，import 不到才退回本文件里的字面量兜底
   （兜底是为了「删掉本文件不留残渣」这条约束 —— spec 不该硬依赖 fetch/ 才能被读）。

━━ 口径断点 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
`series/db1_breaks.csv` **不存在**（enx 有、db1 没有 —— 官方 xlsx 没有可机器抽取的
脚注台账）。已知的列级口径变化（360T 自 2018-07 含 GTX 等）只影响单列，
画在全页的红色竖线会误伤其余四十多列，所以 `breaks` 留空，逐条写进 `notes`。

━━ 单位与「存量 / 流量」━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
`stock: True` 的列在跨币种换算时配月末汇率，缺省配月均汇率。本页是 EUR 本币页，
换算不在这里发生（notional.py 的事），但标注必须先对 —— 见 notes 里 AuC 那条**冲突声明**。
"""

import collections
import csv
import math
import os

_CSV = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), 'series', 'db1.csv')


# ══════════════════════════════════════════════════════════════════════════════
# 图注里要报的数**一个都不写死**：在 import 期从 series/db1.csv 的表头现数。
# 算不出就退回不含数字的定性版本 —— 缺文件不许在 import 期抛异常。
# ══════════════════════════════════════════════════════════════════════════════
def _column_census():
    """数一数：金额列几条、张数/笔数列几条、两者配得上对的有几条。

    这就是「本页为什么做不了量价分解」的**机器判据**，不是一句形容词：
    量价分解要 (金额, 数量) 成对同口径，而本表的金额全在现货侧（turnover_*_eurbn）、
    数量全在衍生品侧（*_contracts）—— 两侧是两个不同的市场，相除没有经济含义。

    返回 (金额列数, 合约张数列数, 现货侧数量列数)；读不到返回 (None, None, None)。
    """
    try:
        with open(_CSV, encoding='utf-8') as fh:
            cols = next(csv.reader(fh))
    except (OSError, StopIteration):
        return (None,) * 3
    money = [c for c in cols if c.startswith('turnover_') or c.endswith('_eurbn')
             or c.endswith('_eurmn')]
    contracts = [c for c in cols if c.endswith('_contracts')]
    # 现货侧的「数量」列 = 股数 / 笔数 / 手数。逐个词根找，一条都找不到才是本页的处境。
    qty_spot = [c for c in cols
                if any(k in c for k in ('shares', 'volume_sh', 'trades', 'transactions',
                                        'txn'))
                and not c.endswith('_contracts')]
    # settle_* 是结算笔数，属于托管结算业务，不是现货成交笔数 —— 不算配对候选。
    qty_spot = [c for c in qty_spot if not c.startswith('settle_')]
    return len(money), len(contracts), len(qty_spot)


def _fd_reconcile():
    """撞一次「Eurex 工作簿口径 × 交易日」与「集团台账口径月成交量」。

    这不是好奇：旧 ttm_yoy 的 `total_col` 一旦填了 vol_fd_total_contracts，
    底座会拿它与 `adv × weight` 逐月对账，超过 1e-6 就硬失败。
    所以「为什么不填」这句话的依据必须量出来，不能靠形容词。

    返回 (可比月数, 最大相对偏差, 中位相对偏差)；算不出返回 (None, None, None)。
    """
    rel = []
    for r in _rows():
        a = _num(r, 'adv_eurex_total_contracts')
        w = _num(r, 'trading_days_eurex')
        t = _num(r, 'vol_fd_total_contracts')
        if a and w and t:
            rel.append(abs(a * w / t - 1.0))
    if not rel:
        return (None,) * 3
    rel.sort()
    return len(rel), rel[-1], rel[len(rel) // 2]


def _rows():
    try:
        with open(_CSV, encoding='utf-8') as fh:
            return list(csv.DictReader(fh))
    except OSError:
        return []


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


#: 现货那 10 列 2026-08-18 由 build/basefill/db1_spot_2016.py 回填到 2016 年，
#: 各列的首月、月数、空洞都不一样（官方那几个月压根没有可用披露）。
#: 图注里凡是要报这些数的地方**一律现算**，别再写死 —— 上一版写死的
#: 「turnover_xetra_eurbn 只有 2024-01 起 31 个月」在回填后当场变成假话。
_SPOT_COLS = [
    'turnover_xetra_eurbn', 'turnover_fwb_eurbn',
    'turnover_xetra_equities_eurbn', 'turnover_xetra_etp_eurbn',
    'turnover_xetra_structured_eurbn', 'turnover_fwb_equities_eurbn',
    'turnover_fwb_etp_eurbn', 'turnover_fwb_bonds_eurbn',
    'turnover_fwb_funds_eurbn', 'turnover_fwb_structured_eurbn',
]


def _mi(m):
    return int(m[:4]) * 12 + int(m[5:7])


def _runs(months):
    """['2017-06','2017-07','2019-12'] -> ['2017-06~2017-07', '2019-12']"""
    out, s, p = [], None, None
    for m in months:
        if s is None:
            s = p = m
        elif _mi(m) - _mi(p) == 1:
            p = m
        else:
            out.append(s if s == p else '%s~%s' % (s, p))
            s = p = m
    if s:
        out.append(s if s == p else '%s~%s' % (s, p))
    return out


def _coverage(col):
    """(首月, 有数月数, 无洞连续起点, 空洞段列表)；算不出返回 (None, None, None, [])。"""
    rows = _rows()
    if not rows:
        return None, None, None, []
    months = [r['month'] for r in rows]
    nz = [r['month'] for r in rows if _num(r, col) is not None]
    if not nz:
        return None, 0, None, []
    have = set(nz)
    holes = [m for m in months if nz[0] <= m <= nz[-1] and m not in have]
    cont = nz[-1]
    for i in range(len(nz) - 1, 0, -1):
        if _mi(nz[i]) - _mi(nz[i - 1]) != 1:
            break
        cont = nz[i - 1]
    return nz[0], len(nz), cont, _runs(holes)


def _xetra_adv_check():
    """最新一个「月总额与现货交易日都有值」的月：(月, 月总额, 交易日, 相除得到的 ADV)。

    这是「本页为什么只画月度总额、不画 Xetra ADV」那条注的算术底：
    官方新闻稿印的 ADV 正是这个商，但除数 trading_days_cash 是**慢腿**，
    每个月总有几天它是空的 —— 那几天这张图会缺最新一格。
    """
    for r in reversed(_rows()):
        t, d = _num(r, 'turnover_xetra_eurbn'), _num(r, 'trading_days_cash')
        if t and d:
            return r['month'], t, d, t / d
    return (None,) * 4


def _slow_leg_lag():
    """快腿最新月与慢腿最新月各是几月 —— slow_cols 那条注的实测底。"""
    fast = slow = None
    for r in _rows():
        if _num(r, 'adv_eurex_total_contracts') is not None:
            fast = r['month']
        if _num(r, 'trading_days_cash') is not None:
            slow = r['month']
    return fast, slow


def _calendar_gap():
    """两套交易日日历（Eurex vs Xetra）有几个月不等 —— 「不能互相顶替」的判据。

    返回 (可比月数, 不等的月数)；算不出返回 (None, None)。
    """
    n = diff = 0
    for r in _rows():
        a, b = _num(r, 'trading_days_eurex'), _num(r, 'trading_days_cash')
        if a is None or b is None:
            continue
        n += 1
        if a != b:
            diff += 1
    return (n, diff) if n else (None, None)


_SPOT_COV = {c: _coverage(c) for c in _SPOT_COLS}
_ADVM, _ADVT, _ADVD, _ADVV = _xetra_adv_check()
_FASTM, _SLOWM = _slow_leg_lag()


def _cov_txt(col):
    """'2016-01 起 127 个月，无空洞' / '2016-06 起 62 个月，空洞 2016-07；2017-06~2022-04'"""
    first, n, _cont, holes = _SPOT_COV.get(col, (None, None, None, []))
    if first is None:
        return '（读不到 series/db1.csv）'
    return '%s 起 %d 个月，%s' % (first, n,
                                 '无空洞' if not holes else '空洞 ' + '；'.join(holes))


#: 现货两组折线图上真正画出来的四条**分资产类别**列，顺序与 GROUPS 一致。
#: 图注里点名哪几段没数据时只念这四条 —— 念没入图的列会让读者去图上找一条不存在的线。
_SPOT_DRAWN = [
    ('turnover_xetra_equities_eurbn', 'Xetra 股票'),
    ('turnover_xetra_etp_eurbn', 'Xetra ETF/ETC/ETN'),
    ('turnover_fwb_equities_eurbn', '法兰克福场内股票'),
    ('turnover_fwb_structured_eurbn', '法兰克福场内结构化产品'),
]


def _segs(col):
    """一列在时间轴上被空洞切成几段：返回各段的月数（一段 = 折线上的一笔）。"""
    nz = [r['month'] for r in _rows() if _num(r, col) is not None]
    if not nz:
        return []
    segs, cur = [], 1
    for i in range(1, len(nz)):
        if _mi(nz[i]) - _mi(nz[i - 1]) == 1:
            cur += 1
        else:
            segs.append(cur)
            cur = 1
    segs.append(cur)
    return segs


def _drawn_gap_txt():
    """四条分类线的空洞段 + 会被切成几笔，现算。

    「有洞」与「洞多到画不出线」是两件事，读者需要一个量分辨；段数、最长段与
    「长度 1 的段」（孤立点，前后都是 null，SVG 里连一个笔画都构不成）就是那个量。
    """
    out, lone_any = [], 0
    for col, zh in _SPOT_DRAWN:
        _first, _n, _cont, holes = _SPOT_COV.get(col, (None, None, None, []))
        segs = _segs(col)
        lone_any += sum(1 for s in segs if s == 1)
        out.append('<b>%s</b> 缺 %s ⇒ 画成 %d 笔，最长一笔 %d 个月'
                   % (zh, '、'.join(holes) if holes else '（无）',
                      len(segs), max(segs) if segs else 0))
    return ('；'.join(out) + '。'
            + ('其中长度只有 1 个月的段共 %d 处（前后都是 null 的孤立点）：'
               '折线画不出笔画，那几个月请看末尾核对表。' % lone_any if lone_any else ''))


def _med(col, only=None):
    """一列的中位数（可限定到 only 这组月份）。算不出返回 None。"""
    v = sorted(_num(r, col) for r in _rows()
               if _num(r, col) is not None and (only is None or r['month'] in only))
    return v[len(v) // 2] if v else None


def _ratio_pct(num_col, den_col):
    """两列在**共同有值的月份**上的中位数之比（%）。「量级差多少」那句话的算术底。

    取共同月份而不是各算各的全程中位数 —— 两列覆盖区间不同时，各算各的会把
    「区间不同」混进「量级不同」里读。算不出返回 None。
    """
    both = {r['month'] for r in _rows()
            if _num(r, num_col) is not None and _num(r, den_col) is not None}
    a, b = _med(num_col, both), _med(den_col, both)
    return None if not a or not b else a / b * 100.0


#: 1 位小数 €bn 的四舍五入半宽。**图注里印的那个 "0.05 €bn" 也从这里取** ——
#: 写成两处字面量就会各改各的，图注哪天说 0.05 而算式用 0.005 谁都看不出来。
_ROUND_HALF = 0.05


def _round_err_pct(cols, half=_ROUND_HALF):
    """四舍五入半宽 half 落在这几列的中位数上是百分之几。

    精度闸门那句话的算术底：闸门比的是每组里**最小**的值，这里给读者一个更温和的
    中位数版本 —— 中位数都超 3%，最小值只会更糟。
    """
    v = [m for m in (_med(c) for c in cols) if m]
    return None if not v else half / (sorted(v)[len(v) // 2]) * 100.0


def _ledger_gap():
    """(可比月数, |台账合计 − Xetra| ÷ 台账合计 的中位数 %, 最大 %)。

    「台账合计与 Xetra 合计两条线为什么几乎重合」那句话的算术底 —— 那道缝就是
    法兰克福场内。**不写死**：官方哪天改了场所构成，这个数自己会变。
    """
    d = []
    for r in _rows():
        t, x = _num(r, 'turnover_cash_total_eurbn'), _num(r, 'turnover_xetra_eurbn')
        if t and x:
            d.append(abs(t - x) / t * 100.0)
    if not d:
        return None, None, None
    d.sort()
    return len(d), d[len(d) // 2], d[-1]


def _parallel_gap(ledger, eurex):
    """两套并行口径逐月对不对得上：(可比月数, 不等的月数)。

    `ledger` = 台账口径的列名列表（当月**合计**），`eurex` = Eurex 工作簿口径的
    ADV 列名列表（乘 trading_days_eurex 还原成当月合计再比）。Eurex 那侧缺格
    （股息组 2008-06 才有）按 0 计 —— 那正是「摊回股指+单股」这句话的算法。

    2026-08-19 现算化：这两组数原先写死成「222 个月里 48 个不等 / 217 个仍然不等」，
    而同一页 Exhibit 41 的图注印的是 `_calendar_gap()` / `_fd_reconcile()` 现算的
    223 / 211 —— 同一页两个分母，读者往下滚一屏就能抓到。分母每个月长 1，
    写死的那个必然先烂。算不出返回 (None, None)。
    """
    n = diff = 0
    for r in _rows():
        d = _num(r, 'trading_days_eurex')
        led = [_num(r, c) for c in ledger]
        eur = [_num(r, c) for c in eurex]
        if d is None or any(v is None for v in led) or eur[0] is None:
            continue
        n += 1
        if abs(sum(led) - sum(v or 0.0 for v in eur) * d) > 0.5:
            diff += 1
    return (n, diff) if n else (None, None)


def _fd_unequal():
    """Eurex「ADV × 交易日」与台账 vol_fd_total 逐月不等的月数（分母同 `_FDN`）。"""
    return _parallel_gap(['vol_fd_total_contracts'], ['adv_eurex_total_contracts'])


def _first_months(cols):
    """{列名: 首个非空月}，读不到的列不进字典。「各列首个非空月」那条注的算术底。

    ⚠ 这条注原先是**手抄**的，抄错过一处：`vol_fd_total_contracts` 实际自 2009-01 起，
    注里写的是 2010-01。手抄的清单没有任何检查会报错，所以改成现算。
    """
    out = {}
    for r in _rows():
        for c in cols:
            if c not in out and _num(r, c) is not None:
                out[c] = r['month']
    return out


#: 一次性回填的窗口右端（build/basefill/db1_spot_2016.py 的作用域）。
#: 这是个**闭区间**：回填做完就冻住了，不随 CSV 生长 —— 所以它可以写死，
#: 而窗口里的月数与残差不行（官方回补一格就变），那两个现算。
_BF_END = '2023-12'


def _ceil_to(v, nd):
    """把 v 向**上**取到 nd 位小数 —— 印「最大不超过 X」时必须这么取。

    四舍五入有一半的概率把上界取**小**，页面印出来的「最大值」于是比真正的最大值
    还小，被它自己的数据证伪。上界只能向上取。（**不举实测数字当例子** ——
    举一个就等于再养一个会过期的数。）
    """
    f = 10.0 ** nd
    return math.ceil(v * f - 1e-9) / f


def _closure_check(hi=_BF_END):
    """回填窗口内的台账闭合：|Xetra + 法兰克福 − turnover_cash_total| 有多大。

    返回 (首月, 可比月数, 最大残差 €bn, 最大残差那个月)；算不出返回 (None,)*4。

    ⚠ 只算到 `hi` 为止。窗口之外还有官方事后重述造成的大残差
    （basefill 的 KNOWN_RESTATEMENTS 里记着的那个月就是），把它们算进来，
    「全在四舍五入界内」这半句立刻变成假话 —— 这条注说的本来就只是回填那一段。
    """
    out = []
    for r in _rows():
        if r['month'] > hi:
            continue
        x = _num(r, 'turnover_xetra_eurbn')
        f = _num(r, 'turnover_fwb_eurbn')
        t = _num(r, 'turnover_cash_total_eurbn')
        if None in (x, f, t):
            continue
        out.append((r['month'], abs(x + f - t)))
    if not out:
        return (None,) * 4
    m, v = max(out, key=lambda z: z[1])
    return out[0][0], len(out), v, m


def _span_months(col):
    """一列的 (首月, 末月, 月数)；算不出返回 (None, None, None)。"""
    nz = [r['month'] for r in _rows() if _num(r, col) is not None]
    return (nz[0], nz[-1], len(nz)) if nz else (None, None, None)


_NMONEY, _NCONTRACTS, _NQTY = _column_census()
_FDN, _FDMAX, _FDMED = _fd_reconcile()
_FDGN, _FDGDIFF = _fd_unequal()
_RATEN, _RATEDIFF = _parallel_gap(['vol_fd_rates_contracts'],
                                  ['adv_eurex_rates_contracts'])
_EQN, _EQDIFF = _parallel_gap(['vol_fd_index_contracts', 'vol_fd_equity_contracts'],
                              ['adv_eurex_index_contracts', 'adv_eurex_equity_contracts',
                               'adv_eurex_dividend_contracts'])
_BF0, _BFN, _BFMAX, _BFM = _closure_check()
_CALN, _CALDIFF = _calendar_gap()
_LEDN, _LEDMED, _LEDMAX = _ledger_gap()
#: 「为什么不按场所总额/分资产类别拆」那句话的两个量级比（现算，别写死）。
_R_VENUE = _ratio_pct('turnover_fwb_eurbn', 'turnover_xetra_eurbn')
_R_CLASS = _ratio_pct('turnover_fwb_structured_eurbn', 'turnover_xetra_equities_eurbn')
#: 1 位小数 €bn 的四舍五入半宽落在法兰克福分类列上是百分之几（精度闸门阈值 3%）。
_R_ROUND = _round_err_pct(['turnover_fwb_equities_eurbn', 'turnover_fwb_structured_eurbn',
                           'turnover_fwb_etp_eurbn', 'turnover_fwb_bonds_eurbn',
                           'turnover_fwb_funds_eurbn'])
_R_ROUND_X = _round_err_pct(['turnover_xetra_eurbn'])

_NO_DECOMP_NOTE = (
    '📌 <b>本页不具备量价分解的数据条件 —— 缺的是列，不是口径。</b>'
    '量价分解要一对<b>同口径</b>的（金额，数量）：现货侧要「成交额 + 成交股数/笔数」，'
    '衍生品侧要「名义金额 + 合约张数」。本表两侧各缺一半：'
    + ((f'金额类列 {_NMONEY} 条<b>全在现货侧</b>（<code>turnover_*_eurbn</code> 与'
        f'托管结算的余额类），而现货侧可配对的数量列有 <b>{_NQTY}</b> 条；'
        f'合约张数类列 {_NCONTRACTS} 条<b>全在衍生品侧</b>（Eurex 与集团台账两套口径），'
        f'而衍生品侧一条名义金额列都没有。'
        if _NMONEY is not None else
        '金额类列全在现货侧、合约张数类列全在衍生品侧，两侧都配不成对。'))
    + '⇒ 唯一「凑得出来」的做法是拿现货成交额去除以衍生品张数，'
      '那是两个不同市场的数相除，得到的比值不指代任何东西。'
      '<b>缺的是列不是口径，所以不去凑</b> —— 官方哪天把现货成交笔数或衍生品名义额发出来，'
      '这张图一行配置就能加上。'
      '（对照：本仓 SGX / TMX 有「金额 + 股数」，ASX / Euronext 有「金额 + 笔数」，'
      'DB1 两者都没有。）'
)

_NOTE_TTM_EUREX = (
    '<b>柱与线取自同一列</b>（<code>adv_eurex_total_contracts</code>，'
    '官方工作簿自己发的 Daily average，不是本仓算的）：柱是水平值，'
    '金线是它自己的<b>单月同比</b> —— 拿这根柱除以 12 根柱之前那根就是线上这一点。'
    '<b>因为柱是日均，「这个月多开了几天市」这一层已经在柱里除掉了</b>，'
    '同比自然也不含它。'
    '⚠️ 2026-09 之前本图的金线是 12 个月滚动合计的同比，为此要先拿 '
    '<code>× trading_days_eurex</code> 把日均还原成当月合计；改单月口径后'
    '这一步整个消失，下面两处旧坑因此也一并作废，记在这里免得有人再走一遍：'
    '<b>① 不能用台账口径的 <code>vol_fd_total_contracts</code> 当合计列</b> ——'
    '那是<b>另一套并行口径</b>（含 ETC / 农产品 / 贵金属），与 Eurex 工作簿永不互校'
    + ((f'；{_FDN} 个可比月里「ADV × 交易日」与台账合计的相对偏差'
        f'<b>中位 {_FDMED:.2e}、最大 {_FDMAX:.2e}</b>，远超底座对账阈值 1e-6。'
        if _FDMAX is not None else '，偏差远超底座对账阈值 1e-6。'))
    + '<b>② 交易日必须用 <code>trading_days_eurex</code> 而不是 '
      '<code>trading_days_cash</code></b>'
    + ((f'：两套日历在 {_CALN} 个可比月里有 <b>{_CALDIFF}</b> 个不等'
        if _CALN else '：两套日历并不总是相等')
       + '（德国统一日与圣灵降临节周一 Eurex 开、Xetra 关）。'
         '这两条现在都不影响本图 —— 它一条交易日列都不用了。')
)

_NOTE_TTM_CASH = (
    '<b>柱与线取自同一列</b>（<code>turnover_cash_total_eurbn</code>，当月<b>合计</b>），'
    '所以这里没有任何「日均还原成合计」的步骤 —— 也正因为如此，'
    '这张图不受 <code>trading_days_cash</code> 是慢腿列的影响。'
    '<b>⚠️ 但这一列是「当月合计」，所以日历差留在同比里</b>：德国现货的月度形状被'
    '复活节、圣灵降临节与年末假期推着走，各月交易日数在 18–23 天之间浮动，'
    '本图的单月同比里有一截只是「今年这个月比去年多开 / 少开了几天市」，'
    '读的时候要把它减掉再判断量本身的方向。'
    '（同页 Eurex 那张的柱是<b>日均</b>，天然不含这一层 —— 两张图要分开读。）'
    '⚠️ 这一列是<b>集团台账口径</b>的现货合计（2010-01 起深史），与 FWB 工作簿那条'
    '产线彼此独立。它同时画在上面「Xetra 电子盘成交额」那张折线里 —— '
    + ((f'与 Xetra 合计只差 <b>{_LEDMED:.1f}%</b>（{_LEDN} 个可比月的中位，最大 {_LEDMAX:.1f}%），'
        if _LEDMED is not None else '与 Xetra 合计只差百分之几，')
       + '两条线几乎重合是对的，不是同一列画了两遍：那道缝正是法兰克福场内，'
         '紧随其后的那张「法兰克福场内成交额」就是把这道缝单独放大来画。')
    + '⚠️ 缝虽小，两条线仍是**两套口径**：Xetra / 法兰克福两列出自 FWB 现货工作簿，'
      '这一列出自集团 IR 台账，逐月能对上是回填时那道闭合闸门的结论，不是定义上的恒等。'
)


# ── 慢腿列：优先从 fetch/db1.py 的权威常量派生 ─────────────────────────────
# 兜底清单只在 fetch/db1.py 读不到时使用。两者本机实测完全一致（20 列），
# 不一致时以 fetch 侧为准 —— 那边是跟着抓取代码一起改的，这边是配置。
_SLOW_FALLBACK = frozenset([
    'adv_360t_fx_eurbn', 'auc_fund_services_eurbn', 'auc_securities_services_eurbn',
    'aum_stoxx_dax_etf_eurbn', 'cash_balances_eurmn', 'gsf_collateral_eurbn',
    'otc_notional_cleared_eurbn', 'otc_notional_outstanding_eurbn',
    'settle_icsd_txn_mn', 'settle_ifs_txn_mn', 'trading_days_cash',
    'turnover_cash_total_eurbn', 'vol_fd_equity_contracts', 'vol_fd_index_contracts',
    'vol_fd_rates_contracts', 'vol_fd_total_contracts', 'vol_gas_mwh',
    'vol_licensed_index_contracts', 'vol_power_deriv_mwh', 'vol_power_spot_mwh',
])


def _slow_universe():
    """返回「哪些列属于慢腿」的全集。读得到 fetch/db1.py 就用它的常量。

    用 spec_from_file_location 而不是 import fetch.db1 —— 本仓没有 __init__.py，
    monthly_run.py 自己也是这么加载模块的（那边的 `load()`；**这里不写行号** ——
    上一版写的 `monthly_run.py:151` 早就漂到别的函数里去了，行号一改就成假话）。
    任何失败都静默退回兜底清单：spec 被读的时候不该因为 fetch/ 缺席而炸。
    """
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), 'fetch', 'db1.py')
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location('_db1_fetch_for_spec', path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        cols = frozenset(mod.SLOW_LEG_COLUMNS)
        return cols if cols else _SLOW_FALLBACK
    except Exception:
        return _SLOW_FALLBACK


# ── 头条 ───────────────────────────────────────────────────────────────────
# Eurex 全所日均成交合约数：2008-01 起 223 个月零空洞、快腿（月末后第 2–6 天）、
# 官方工作簿自己就发 Daily average（不是本仓算的）。三条都满足「历史长 / 发布快 / 无空洞」。
# 不用 Xetra 现货做头条：它 2026-08-18 已经回填到 2016-01（build/basefill/db1_spot_2016.py），
# 长度不再是理由，但**成色**是 —— 2016-01~2023-12 那一段里有 55 个月只有官方新闻稿的
# 四舍五入值（法兰克福那一格相对误差最坏 2.2%），而 Eurex ADV 全程是官方工作簿原值。
# 头条要的是「最长 + 最快 + 最干净」那一条，三条里 Eurex ADV 仍然全占。
HEADLINE = [
    {'col': 'adv_eurex_total_contracts', 'zh': 'Eurex 衍生品 ADV',
     'unit': 'contracts/day', 'fmt': 'f0c'},
]

# ── 分组 ───────────────────────────────────────────────────────────────────
# 每组一个 exhibit 群。列名全部 head -1 series/db1.csv 核过。
# 刻意排除 turnover_xetra_structured_eurbn：**官方多数月压根不发这一格**
# （工作簿里留空、新闻稿里印 '-'），所以它天生是一条稀疏序列，回填也救不了 ——
# 2026-08-18 回填后它反而更稀（首月往前挪到 2016-06，中间的洞比有数的月还多，
# 实测覆盖见 notes 里那条现算的 _cov_txt）。
# 同理不入图的还有 turnover_fwb_etp / bonds / funds 三列（本来就没进过任何 exhibit）：
# 它们在 0.03~1.0 €bn 量级，回填源里 1 位小数时代的相对误差 5%~50%，
# build/basefill/db1_spot_2016.py 的精度闸门已经把那些格子整组丢掉，序列因此是断的。
#
# ⚠ 2026-08-19 更新排除理由。原来写的是「平滑类图型遇到 null 会画出塌到零的假线」——
#   现货两组现在走的是 kind='lines'（doSmooth=false，null 是断笔），那条理由**不再成立**，
#   留着会让下一个人以为「换个图型就能把这四列加回来」。真正的两条理由是：
#   ① 密度：turnover_xetra_structured 在 127 个月的窗口里只有 21 个值、101 个洞，
#      画出来是一串互不相连的孤点，而 lines 的孤立点（前后都是 null）在 SVG 里是
#      「M 但没有 L」—— 一个像素都画不出来（assets/charts.js: polyline，markers 默认关）。
#      有洞的线还能读，全是洞的线读不了，这不是图型能救的。
#   ② 名额：加回去就撞 MAX_LINES。法兰克福那组现在 3 列，再塞 etp/bonds/funds 就是 6 列
#      > 5，底座立刻退回 heat_matrix，本次拆组要修的正是这个。
GROUPS = [
    # 头条那一列在这里再出现一次是**故意的**：头条的契约职责是「定共同最新月与门槛」，
    # 它会不会同时被画成图由底座决定。列在组里 ⇒ 底座只画组时不会丢掉旗舰序列；
    # 若底座也画头条，去重是底座一行的事。反过来（漏掉旗舰图）修起来贵得多。
    # enx.py 同理，两份 spec 保持同一个约定。
    {'zh': 'Eurex 衍生品 ADV（按官方大组）', 'cols': [
        {'col': 'adv_eurex_total_contracts', 'zh': '全所合计',
         'unit': 'contracts/day', 'fmt': 'f0c'},
        {'col': 'adv_eurex_rates_contracts', 'zh': '利率衍生品',
         'unit': 'contracts/day', 'fmt': 'f0c'},
        {'col': 'adv_eurex_index_contracts', 'zh': '股指衍生品（不含股息）',
         'unit': 'contracts/day', 'fmt': 'f0c'},
        {'col': 'adv_eurex_equity_contracts', 'zh': '单股衍生品（不含股息）',
         'unit': 'contracts/day', 'fmt': 'f0c'},
        {'col': 'adv_eurex_dividend_contracts', 'zh': '股息衍生品',
         'unit': 'contracts/day', 'fmt': 'f0c'},
    ]},

    # OI 全部是月末时点值 ⇒ stock。Eurex 的 OI 会被官方事后重述
    # （fetch/db1.py 口径坑 3：222 对里 17 对不等，最大 2.48%），所以这条线的历史段
    # 与当年印出来的数字可能对不上，不是本页算错。
    {'zh': 'Eurex 未平仓合约（月末）', 'cols': [
        {'col': 'oi_eurex_total_contracts', 'zh': '全所合计',
         'unit': 'contracts', 'fmt': 'f0c', 'stock': True},
        {'col': 'oi_eurex_rates_contracts', 'zh': '利率',
         'unit': 'contracts', 'fmt': 'f0c', 'stock': True},
        {'col': 'oi_eurex_index_contracts', 'zh': '股指',
         'unit': 'contracts', 'fmt': 'f0c', 'stock': True},
        {'col': 'oi_eurex_equity_contracts', 'zh': '单股',
         'unit': 'contracts', 'fmt': 'f0c', 'stock': True},
        {'col': 'oi_eurex_dividend_contracts', 'zh': '股息',
         'unit': 'contracts', 'fmt': 'f0c', 'stock': True},
    ]},

    # 德债三剑客 = Eurex 的利率支柱。产品代码 FGBL / FGBM / FGBS。
    {'zh': '德债期货三剑客（Bund / Bobl / Schatz）', 'cols': [
        {'col': 'adv_bund_contracts', 'zh': 'Bund（FGBL，10 年）ADV',
         'unit': 'contracts/day', 'fmt': 'f0c'},
        {'col': 'oi_bund_contracts', 'zh': 'Bund 未平仓',
         'unit': 'contracts', 'fmt': 'f0c', 'stock': True},
        {'col': 'adv_bobl_contracts', 'zh': 'Bobl（FGBM，5 年）ADV',
         'unit': 'contracts/day', 'fmt': 'f0c'},
        {'col': 'oi_bobl_contracts', 'zh': 'Bobl 未平仓',
         'unit': 'contracts', 'fmt': 'f0c', 'stock': True},
        {'col': 'adv_schatz_contracts', 'zh': 'Schatz（FGBS，2 年）ADV',
         'unit': 'contracts/day', 'fmt': 'f0c'},
        {'col': 'oi_schatz_contracts', 'zh': 'Schatz 未平仓',
         'unit': 'contracts', 'fmt': 'f0c', 'stock': True},
    ]},

    # BTP（意大利）2009-09 起、OAT（法国）2012-04 起 —— 比德债三剑客晚，
    # 前段天然留空，是官方就没有，不是解析失败。
    {'zh': '外围主权债与短端利率（BTP / OAT / EURIBOR）', 'cols': [
        {'col': 'adv_btp_contracts', 'zh': 'BTP（FBTP，意大利）ADV',
         'unit': 'contracts/day', 'fmt': 'f0c'},
        {'col': 'oi_btp_contracts', 'zh': 'BTP 未平仓',
         'unit': 'contracts', 'fmt': 'f0c', 'stock': True},
        {'col': 'adv_oat_contracts', 'zh': 'OAT（FOAT，法国）ADV',
         'unit': 'contracts/day', 'fmt': 'f0c'},
        {'col': 'oi_oat_contracts', 'zh': 'OAT 未平仓',
         'unit': 'contracts', 'fmt': 'f0c', 'stock': True},
        {'col': 'adv_euribor3m_contracts', 'zh': '3 个月 EURIBOR（FEU3）ADV',
         'unit': 'contracts/day', 'fmt': 'f0c'},
        {'col': 'oi_euribor3m_contracts', 'zh': '3 个月 EURIBOR 未平仓',
         'unit': 'contracts', 'fmt': 'f0c', 'stock': True},
    ]},

    # ⚠ 两条 ADV 列用 f0 而不是全页通用的 f0c，**只为了让开竖排的纵轴标题**，
    #   不是嫌逗号难看。这一组的两条 ADV 同单位 ⇒ 底座画成一张 lines_endlabels，
    #   而那个图型的左端标签是 anchor=end 落在 `M.l − 10 − tickW`（assets/charts.js
    #   的 lines_endlabels 分支，那个 10 写死、不随字号缩放；那段注释早就把「db1 Ex7
    #   两处」列进「左端标签与竖排标题只差零点几像素」的清单，只是当时还是正的）。
    #   窗口拉到 2016-01 之后左端那一格是 2016-01，两条线的首值
    #   1,609,994 / 1,492,079 都是 7 位数，带上两个千分位逗号刚好把标签撑到压住
    #   竖排的「contracts/day」：
    #     1280px 视口（画布 1172、FS=1.70）实测 lx = 146.2 − 10 − 59.5(tickW「3500000」)
    #     = 76.7px，「1,609,994」宽 60.5px ⇒ 左边界 16.2px，而竖排标题的墨迹右界
    #     ≈ fscale(13) = 22.1px ⇒ 横向压 5.9px（tools/visual_qa.py 报 56.4px²，🟡）。
    #   去掉两个逗号后标签 52.9px ⇒ 左边界 23.8px，让开 1.7px；768px 视口同理让开
    #   0.4px。QA 实测 Ex7 的 4 条（两个视口 × 两条线）全部消失、无新增。
    #
    #   为什么不是别的修法：① 缩量级（build/chartscale.py）在这张图上**判过不需要**——
    #   它的 lines_endlabels 预算 `m_l − 10 − tickW − 1.5` = 39.5px 只模型化了
    #   「被 SVG 左边界切掉」，没有把竖排标题那一列算进去，而最宽标签 35.6px < 39.5px；
    #   ② 缩短 unit 字符串没用：竖排标题的**墨迹右界只由字号决定**（≈ fscale(13)），
    #   与字数无关，字数只改它的竖向长度；③ 加宽 M.l 那 30px 是引擎改动，
    #   会动到全站 80+ 张 lines_endlabels，不在本轮范围（charts.js 里已写明）。
    #
    #   代价不落在数字上：核对表与汇总表走 build/single.py 的 `fmt_val()`，那一份
    #   **一律带千分位**（f0 / f0c 同样印 "514,907"），一位有效数字都没少；少掉逗号的
    #   只有 SVG 上的标签与卡片内「表格」视图这两处。
    {'zh': 'EURO STOXX 50 期货与期权（FESX / OESX）', 'cols': [
        {'col': 'adv_estoxx50_fut_contracts', 'zh': 'EURO STOXX 50 期货 ADV',
         'unit': 'contracts/day', 'fmt': 'f0'},
        {'col': 'oi_estoxx50_fut_contracts', 'zh': 'EURO STOXX 50 期货未平仓',
         'unit': 'contracts', 'fmt': 'f0c', 'stock': True},
        {'col': 'adv_estoxx50_opt_contracts', 'zh': 'EURO STOXX 50 期权 ADV',
         'unit': 'contracts/day', 'fmt': 'f0'},
        {'col': 'oi_estoxx50_opt_contracts', 'zh': 'EURO STOXX 50 期权未平仓',
         'unit': 'contracts', 'fmt': 'f0c', 'stock': True},
    ]},

    # FVS 这一行的产品名换过（前 93 期「Mini-Futures auf VSTOXX®」，后 114 期
    # 「Futures on VSTOXX®」），代码始终 FVS；合约乘数是否也换过 fetch 侧没核实过 ——
    # 本页只画张数不做名义额换算，所以不受影响；要换算先去查 Eurex 产品规格。
    {'zh': 'DAX 与 VSTOXX（FDAX / ODAX / FVS）', 'cols': [
        {'col': 'adv_dax_fut_contracts', 'zh': 'DAX 期货 ADV',
         'unit': 'contracts/day', 'fmt': 'f0c'},
        {'col': 'oi_dax_fut_contracts', 'zh': 'DAX 期货未平仓',
         'unit': 'contracts', 'fmt': 'f0c', 'stock': True},
        {'col': 'adv_dax_opt_contracts', 'zh': 'DAX 期权 ADV',
         'unit': 'contracts/day', 'fmt': 'f0c'},
        {'col': 'oi_dax_opt_contracts', 'zh': 'DAX 期权未平仓',
         'unit': 'contracts', 'fmt': 'f0c', 'stock': True},
        {'col': 'adv_vstoxx_fut_contracts', 'zh': 'VSTOXX 期货 ADV',
         'unit': 'contracts/day', 'fmt': 'f0c'},
        {'col': 'oi_vstoxx_fut_contracts', 'zh': 'VSTOXX 期货未平仓',
         'unit': 'contracts', 'fmt': 'f0c', 'stock': True},
    ]},

    # ⚠ 这一组全是**月度总额**，不是 ADV。官方现货工作簿只发月总额；
    #   ADV = 月总额 ÷ trading_days_cash（fetch/db1.py 口径坑 7），而 trading_days_cash
    #   是慢腿列，本页不做算术，所以这里如实标成「月度总额」，别在标题里写 ADV。
    #
    # ══ 2026-08-19：原本 7 列一组，现在按**场所**拆成两组 ═══════════════════════
    # 为什么拆：7 列 > single.py 的 MAX_LINES=5 ⇒ 底座只能画 heat_matrix，而热力矩阵
    # (a) 画的是同比不是水平值、(b) 窗口固定 WIN_HEAT=24 个月。于是 2026-08-18 那次
    # 把 turnover_xetra_* / turnover_fwb_* 回补到 2016 年的 572 格，在页面上的全部体现
    # 只是「矩阵里 74 个 null 变成了 0」—— 2016~2023 的水平值读者一个都看不到。
    # 拆到每组 ≤ 5 列，底座就走折线，窗口跟着 WIN_FROM=2016-01 铺满 127 个月。
    #
    # 为什么按**场所**拆，而不是按「场所总额 / 分资产类别」拆：后者两组都会撞上
    # **同轴量级差**。本机实测 2016-01~2026-07 窗口内的中位数（€bn/月）：
    #     Xetra 合计 117.8 · Xetra 股票 101.8 · Xetra ETP 16.7
    #     法兰克福合计 3.7 · 法兰克福股票 1.59 · 法兰克福结构化 1.08 · 台账合计 121.1
    # 「场所总额」那组会把 3.7 和 121.1 摆在一根轴上（法兰克福那条压成零线，
    # 振幅占画布 <2%）；「分资产类别」那组会把 1.08 和 101.8 摆在一起，更糟。
    # 按场所拆之后，组内中位数的最大 / 最小是 121.1÷16.7 ≈ 7.2 倍与 3.7÷1.08 ≈ 3.4 倍，
    # 三四条线都读得出来 —— 这正是页尾「图型选择规则」第 ① 条（同一张图只放同一单位
    # **且**同量级的列）想拦的那种图；底座按单位自动拆，同单位不同量级只能在 spec 这层拆。
    # ⚠ 上面这几个中位数是写这段注释时的实测，注释会过期而图注不会：
    #   页面上印出来的那两个比例走 `_ratio_pct()` 现算，别拿这里的数去核页面。
    #
    # 台账合计放在 Xetra 这一组：它 = Xetra + 法兰克福（回填时逐月过了闭合闸门），
    # 两条线几乎重合（差多少由 `_ledger_gap()` 现算后印进 level_yoy 那张的图注），
    # 而**那道缝就是下一张图的全部内容**。
    # 它不能自己单独成组：单列组走 gs_bar + 次轴单月同比，而这一列已经在 level_yoy
    # 那张（Exhibit「集团台账口径现货成交额」）画了一条同比线。
    # ⚠️ 2026-09 之前这里的理由是「那张画的是滚动、这张会是单月，同一列同一页两种
    # 同比口径」；全站改单月之后**理由换了但结论没换**：两张现在同列、同窗口、同口径，
    # 落单成组只会画出一字不差的第二张图（CONTRACT §6.4「改口径会造出重复图」，
    # 底座 `ex_level_yoy` 撞上直接硬失败）。也不能整个从 groups 里拿掉：
    # allc = headline + groups 同时决定末尾核对表，拿掉它表里就没有这一列了。
    {'zh': 'Xetra 电子盘成交额（月度总额，单边计）', 'cols': [
        {'col': 'turnover_xetra_eurbn', 'zh': 'Xetra 电子盘合计',
         'unit': 'EUR bn/month', 'fmt': 'f1'},
        {'col': 'turnover_xetra_equities_eurbn', 'zh': 'Xetra 股票',
         'unit': 'EUR bn/month', 'fmt': 'f1'},
        {'col': 'turnover_xetra_etp_eurbn', 'zh': 'Xetra ETF/ETC/ETN',
         'unit': 'EUR bn/month', 'fmt': 'f1'},
        {'col': 'turnover_cash_total_eurbn', 'zh': '集团台账口径合计（深史，2010-01 起）',
         'unit': 'EUR bn/month', 'fmt': 'f1'},
    ]},

    # ⚠ 这一组三条线的**中间大洞是真的**（法兰克福分类列 2017-06~2022-04 整段没有）。
    #   底座对「窗口内有 null」的组自动降级到 kind='lines'（doSmooth=false，null 是断笔），
    #   横轴仍由 win_long() 逐月铺开、缺月留 null —— 绝不能把「有值的月」拼成横轴，
    #   那会把 2017-05 与 2022-05 画成相邻格（exchanges-eu Ex12 栽过，CONTRACT 规矩 3）。
    #   lines_endlabels 属 mrwin.DENSE，吃不了中间的洞，所以这一组**永远不许**凑够
    #   「逐点稠密」去换平滑图型。缺哪几段、为什么缺，见 notes 里由 `_drawn_gap_txt()`
    #   现算的那一条（段数 / 最长段 / 孤立点都是当场从 CSV 数出来的，不写死）。
    {'zh': '法兰克福场内成交额（月度总额，单边计）', 'cols': [
        {'col': 'turnover_fwb_eurbn', 'zh': '法兰克福场内合计',
         'unit': 'EUR bn/month', 'fmt': 'f2'},
        {'col': 'turnover_fwb_equities_eurbn', 'zh': '法兰克福场内股票',
         'unit': 'EUR bn/month', 'fmt': 'f2'},
        {'col': 'turnover_fwb_structured_eurbn', 'zh': '法兰克福场内结构化产品',
         'unit': 'EUR bn/month', 'fmt': 'f2'},
    ]},

    # 与上面 adv_eurex_* / oi_eurex_* 是**两套并行口径**，永不互校。
    # fetch/db1.py 口径坑 4 全量实测：vol_fd_rates vs Eurex 利率组小计，
    # 222 个月里 48 个不等；按官方脚注把股息摊回去之后，222 个月里 217 个仍然不等。
    {'zh': '集团台账口径衍生品月成交量（IR 口径，与 Eurex 工作簿不可互校）', 'cols': [
        {'col': 'vol_fd_total_contracts', 'zh': '全所合计（含 ETC/农产品/贵金属）',
         'unit': 'contracts/month', 'fmt': 'f0c'},
        {'col': 'vol_fd_index_contracts', 'zh': '股指（已摊入股息衍生品）',
         'unit': 'contracts/month', 'fmt': 'f0c'},
        {'col': 'vol_fd_equity_contracts', 'zh': '单股（已摊入股息衍生品）',
         'unit': 'contracts/month', 'fmt': 'f0c'},
        {'col': 'vol_fd_rates_contracts', 'zh': '利率',
         'unit': 'contracts/month', 'fmt': 'f0c'},
    ]},

    # ⚠ 存量与流量拆成两组，不是为了排版。合在一组时流量那一列是**单位桶里的独苗**，
    #   底座对单桶画 gs_bar，而 gs_bar 的次轴是**单月同比**；
    #   tools/check_yoy_caliber.py 实测这一列有 5 个月与 12 个月滚动口径**符号相反**
    #   （2025-02 单月 −37.5% vs 滚动 +24.2%）。本表里没有第二条 EUR bn/month 的
    #   同伴可以同轴，所以口径写进组名 —— 单月是全站唯一口径（CONTRACT §6.1 第 1 条），
    #   §6.6 的自动判据要求它写进标题（R4，不写就报 🟡）。
    #   声明必须只落在真的画了次轴同比的那张图上，
    #   所以存量那一列先搬出去（存量走点对点同比，本来就不适用这条声明）。
    {'zh': 'EurexOTC Clear 名义未平仓（月内平均值）', 'cols': [
        {'col': 'otc_notional_outstanding_eurbn', 'zh': '名义未平仓（月内平均值）',
         'unit': 'EUR bn', 'fmt': 'f0c', 'stock': True},
    ]},

    {'zh': 'EurexOTC Clear 当月清算名义量（次轴：单月同比）', 'cols': [
        {'col': 'otc_notional_cleared_eurbn', 'zh': '当月清算名义量（含压缩）',
         'unit': 'EUR bn/month', 'fmt': 'f0c'},
    ]},

    # ★ 单独成组、单独一图。全仓**唯一的非交易量月度指标** ——
    #   「利润跑向托管结算层」这条结构性趋势的唯一可跟踪证据。
    #   17,459 €bn = €17.46 tn（本页按 €bn 原样画，不做单位换算）。
    {'zh': 'Clearstream 托管资产 AuC（ICSD + CSD 合并）', 'cols': [
        {'col': 'auc_securities_services_eurbn', 'zh': '托管资产（Assets under custody）',
         'unit': 'EUR bn', 'fmt': 'f0c', 'stock': True},
    ]},

    {'zh': 'Clearstream 结算笔数、担保品与现金余额', 'cols': [
        {'col': 'settle_icsd_txn_mn', 'zh': '结算笔数（⚠ 只含 ICSD，不含德国本土 CSD）',
         'unit': 'mn transactions/month', 'fmt': 'f2'},
        {'col': 'gsf_collateral_eurbn', 'zh': 'GSF 担保品在外量（月内平均）',
         'unit': 'EUR bn', 'fmt': 'f0', 'stock': True},
        {'col': 'cash_balances_eurmn', 'zh': '日均现金余额（含受制裁冻结账户）',
         'unit': 'EUR mn', 'fmt': 'f0c', 'stock': True},
    ]},

    # 同上：存量与流量拆开，口径声明只落在真的画了次轴同比的那一张上。
    {'zh': 'Clearstream 基金服务（IFS）托管资产', 'cols': [
        {'col': 'auc_fund_services_eurbn', 'zh': 'IFS 托管资产（月内平均）',
         'unit': 'EUR bn', 'fmt': 'f0c', 'stock': True},
    ]},

    {'zh': 'Clearstream 基金服务（IFS）结算笔数（次轴：单月同比）', 'cols': [
        {'col': 'settle_ifs_txn_mn', 'zh': 'IFS 结算笔数',
         'unit': 'mn transactions/month', 'fmt': 'f2'},
    ]},

    # 原本三列同组、三个单位 ⇒ 三个单桶 ⇒ 三张 gs_bar，次轴都是单月同比。
    # 实测：授权指数衍生品有 11 个月与 12 个月滚动口径**符号相反**
    # （2024-06 单月 +4.2% vs 滚动 −11.6%），360T 外汇则是「用了单月但标题没写明」。
    # 存量那一列（ETF 资产）走点对点同比、本来就合法，所以单独拆出去，
    # 免得口径声明落到一张不适用的图上。
    # ⚠ 这一列与下面的 adv_360t_fx_eurbn 用 f0 而不是 f1，理由是**几何**，见
    #   本组下方「三位数 €bn 的单桶柱图为什么不留小数」那段长注释。
    {'zh': '挂钩 STOXX/DAX 的 ETF 资产（存量）', 'cols': [
        {'col': 'aum_stoxx_dax_etf_eurbn', 'zh': '挂钩 STOXX/DAX 的 ETF 资产',
         'unit': 'EUR bn', 'fmt': 'f0', 'stock': True},
    ]},

    {'zh': '授权指数衍生品月成交量（次轴：单月同比）', 'cols': [
        {'col': 'vol_licensed_index_contracts', 'zh': '授权指数衍生品月成交量',
         'unit': 'contracts/month', 'fmt': 'f0c'},
    ]},

    {'zh': '360T 外汇 ADV（次轴：单月同比）', 'cols': [
        {'col': 'adv_360t_fx_eurbn', 'zh': '360T 外汇 ADV',
         'unit': 'EUR bn/day', 'fmt': 'f0'},
    ]},

    # ══ 三位数 €bn 的单桶柱图为什么不留小数（aum_stoxx_dax_etf / adv_360t_fx）══════
    # 两列都是「一桶一列」⇒ 底座画 gs_bar，而 gs_bar 的柱顶数值标签是**居中钉在自己
    # 那根柱上**的。127 根柱通栏时最后一根柱的中心离右轴只剩半个 band，标签的右半边
    # 必然伸进右轴刻度那一列：
    #   1280px 视口（画布 1172、FS=1.70）：M.l = M.r = fscale(56) = 95.2 ⇒ band = 7.73，
    #   末柱中心在右轴左侧 3.9px，右轴刻度列起于 +fscale(6) = 10.2px
    #   ⇒ 标签半宽预算 14.1px（宽度上限 28.1px）。
    #   「191.3」宽 34.0px ⇒ 压住金色刻度「40%」2.9px（visual_qa 报 28.3px²，🟡；
    #   768px 视口 34.6px²）；「223.5」同宽，压「50%」（11.0px²，🔵）。
    #   「191」/「224」宽 22.7px ⇒ 让开 2.7px，两个视口 4 条全清、无新增。
    # 这不是只有 QA 才看得见：`python3 build/single.py db1` 自己就打
    #   「Exhibit 16 柱顶标签压轴刻度：191.3 宽 20.0px > 预算 17.3px」
    # （build/chartscale.py 的 audit()，缺陷 F 的生成端判据）。
    #
    # 为什么不走 chartscale 的缩量级：它的 `_factor()` 要求最大值缩完 ≥ 1，而
    # 208.1 / 1000 = 0.21 < 1 ⇒ 返回 None，三位数的列它按设计**修不了**。剩下的唯一
    # 杠杆就是小数位，而这正是 chartscale 自己在预算吃紧时做的事（`_decimals()`：
    # 「宁可少一位有效数字，也不要再压回刻度上」）。
    # 也不能靠拆组绕开：ETF 资产是 stock ⇒ 底座一律单列成图；360T 是全表唯一一条
    # 'EUR bn/day'，没有同单位的同伴可以凑成折线。
    #
    # 代价（实测，别当形容词看）：舍入后相对误差最大 0.60%（ETF 资产）/ 0.78%（360T），
    # 都出现在 2016 年那批小值上。末尾 13 期核对表里 ETF 资产没有一对相邻月因此撞成
    # 同一个数；360T 有一对 —— 2026-01（182.71）与 2026-02（182.99）现在都印 183。
    # 要拿回那一位小数就把 fmt 改回 f1，代价是上面那 4 条压字回来。

    # ⚠ 单位是 MWh 不是 TWh。官方工作簿表头写「(in TWh)」是笔误，
    #   单元格里是 MWh，差 10⁶。列名带 _mwh 就是为了每次看到都提醒一次。
    {'zh': 'EEX 电力与天然气（MWh，注意不是 TWh）', 'cols': [
        {'col': 'vol_power_spot_mwh', 'zh': '电力现货',
         'unit': 'MWh/month', 'fmt': 'f0c'},
        {'col': 'vol_power_deriv_mwh', 'zh': '电力衍生品',
         'unit': 'MWh/month', 'fmt': 'f0c'},
        {'col': 'vol_gas_mwh', 'zh': '天然气',
         'unit': 'MWh/month', 'fmt': 'f0c'},
    ]},
]


def _charted():
    """本页真正画出来的列（头条 + 全部分组），按出现顺序去重。"""
    out, seen = [], set()
    for item in HEADLINE + [c for g in GROUPS for c in g['cols']]:
        if item['col'] not in seen:
            seen.add(item['col'])
            out.append(item['col'])
    return out


# 慢腿列 = 本页画的列 ∩ 慢腿全集。只列真正画了的，避免 slow_cols 里出现幽灵列。
_SLOW_ALL = _slow_universe()
SLOW_COLS = sorted(c for c in _charted() if c in _SLOW_ALL)


def _starts_zh():
    """本页画的列按**现算出来的首月**分组，列成一句中文（同 build/specs/enx.py）。

    ⚠ 这条注 2026-08-19 之前是手抄的枚举，抄错过一处：`vol_fd_total_contracts`
    实际自 2009-01 起，注里跟 turnover_cash_total / settle_* 一道写成了 2010-01。
    手抄清单没有任何检查会报错 —— 官方回填一次、或者谁加一列，它就再错一处。
    列名用 CSV 原名而不是中文名：这条注是给回源核对用的，原名才对得上 head -1。
    """
    cols = _charted()
    first = _first_months(cols)
    if not first:
        return ''
    by = collections.defaultdict(list)
    for c in cols:
        if c in first:
            by[first[c]].append(c)
    # 一个月里超过 5 列就只点名前 5 条 + 报总数：Eurex 那一批有二十几列，
    # 全铺出来这一条注比整页别的注加起来还长，读者反而找不到重点。
    # 「等 N 条」是真话（不是省略号冒充完整枚举），要全清单看 head -1 series/db1.csv。
    def _one(m):
        cs = sorted(by[m])
        head = '、'.join('<code>%s</code>' % c for c in cs[:5])
        return '<b>%s</b>：%s' % (m, head if len(cs) <= 5
                                 else '%s 等 %d 条' % (head, len(cs)))

    return '；'.join(_one(m) for m in sorted(by))


_STARTS_ZH = _starts_zh()


SPEC = {
    'ticker': 'db1',
    'name':   'Deutsche Börse',
    'title':  '德意志交易所（DB1）月度经营指标',
    'csv':    'db1.csv',
    'ccy':    'EUR',
    # 现货那 10 列 2016-01~2023-12 那一段来自后两个源（回填，见 notes 的精度分层那条），
    # 所以出处栏必须把它们写出来 —— 页面上印的「Source:」是读者判断可信度的唯一入口。
    'source': ('Source: Deutsche Börse Group IR "Major business figures"、'
               'Eurex Monthly Statistics、FWB Monthly Cash Market Statistics'
               '（2016-01–2023-12 现货历史取自 web.archive.org 存档的同名官方工作簿'
               '与 Deutsche Börse 月度现货新闻稿）; format after Goldman Sachs GIR'),

    'headline': HEADLINE,
    'groups':   GROUPS,
    'slow_cols': SLOW_COLS,

    # series/db1_breaks.csv 不存在 —— 官方 xlsx 没有可机器抽取的脚注台账。
    # 已知的列级口径变化只影响单列，画成全页红线会误伤其余四十多列，故留空。
    'breaks': [],

    # 📌 'decomp' 刻意留空：本表没有任何一对同口径的（金额，数量）列。
    # 理由与机器判据见 _NO_DECOMP_NOTE（它进了下面的 notes 第一条）。

    # ══ 水平值 + 次轴单月同比 ════════════════════════════════════════════════
    # 两条腿各一张：Eurex 衍生品（快腿，2008-01 起）与集团台账口径现货（慢腿，2010-01 起）。
    # 两条 level 列在 groups 里分别落在「5 列同轴的 lines」与「4 列同轴的 lines」
    # （2026-08-19 之前是「7 列的热力矩阵」）里，都不是单桶 gs_bar
    # ⇒ 这两张不会与任何一张**单桶 gs_bar** 重复。
    # ⚠️ 但 adv_eurex_total_contracts 同时是**头条列**，头条自带一张 grouped_bars
    #   的「：单月同比」——2026-09 改口径之后那张的柱与本段第一条的金线**逐点同源**
    #   （改口径前一张单月、一张滚动，各有各的用处）。底座 `ex_level_yoy` 的护栏只拦
    #   「level_yoy ∩ groups 单列桶」，拦不到头条这条路；要不要合并成一张由页面所有者定。
    # ⚠ 拆组时务必保住这条：turnover_cash_total_eurbn 一旦落单成组，底座会给它
    #   gs_bar + 次轴**单月**同比 —— 与下面 level_yoy 那张同列、同窗口、同口径，
    #   页面上会出现一字不差的两张图（CONTRACT §6.4「改口径会造出重复图」）。
    #   底座 `ex_level_yoy` 的重复护栏对这种情况**硬失败**，整页发不出去。
    #   （2026-09 之前这里写的是「立刻有了两种同比口径，CONTRACT §6 拿 cme Ex2/旧 Ex8
    #   当反例的就是这个形状」—— 那时 level_yoy 画的是滚动。现在两边同口径，
    #   撞车的形状从「读者不知道信哪张」变成了「两张完全一样」。）
    'level_yoy': [
        {'zh': 'Eurex 衍生品成交量',
         # 官方工作簿直接发 Daily average。次轴是**本列自己的单月同比**，
         # 不再需要 trading_days_eurex 把日均还原成当月合计 —— 那一步只在滚动 12 个月
         # 合计的年代有意义（台账口径的 vol_fd_total_contracts 与「ADV × 交易日」
         # 相对偏差量级 1e-3，本来就对不上账）。
         'level': {'col': 'adv_eurex_total_contracts', 'zh': '全所日均成交',
                   'unit': 'contracts/day', 'fmt': 'f0c'},
         'note': _NOTE_TTM_EUREX},

        {'zh': '集团台账口径现货成交额',
         # turnover_* 本身就是当月合计，次轴同样是本列除本列。
         'level': {'col': 'turnover_cash_total_eurbn', 'zh': '当月成交额（单边计）',
                   'unit': 'EUR bn/month', 'fmt': 'f1'},
         'note': _NOTE_TTM_CASH},
    ],

    'notes': [
        _NO_DECOMP_NOTE,

        # ⚠ 括号里那两个「N 期」是**发布日**的实测，而发布日不在 series/db1.csv 里
        #   （CSV 只有数据月，没有那一期什么时候上线），所以这两个数**现算不出来**。
        #   现算不了就把它写成带日期的一次性实测，别让它冒充一个会自己更新的数 ——
        #   原文「2016-01 以来 127 期全部在此带宽内」不带日期，读起来像「此刻」，
        #   而 127 每个月都会少一个。
        '发布节奏：三个源两种节奏（发布日实测于 2026-08，不随 CSV 更新）：'
        'Eurex 工作簿月末后第 2–6 天（2016-01…2026-07 共 127 期全部在此带宽内）'
        '、FWB 现货工作簿第 1–4 天（20 期里 18 期）、集团 IR 台账'
          '约第 10 天（落地页原文 "available as of the second week after the reporting '
          'month"）。'
        # ⚠ 这半句原先写死成「快腿列最新月 2026-07，慢腿列最新月 2026-06」，
        #   而同一页下面那条注是拿 _FASTM/_SLOWM 现算的 —— 慢腿追上来那个月，
        #   两条注就在同一页上互相打脸。判据能现算就不许写快照。
        + ((f'本机实测 series/db1.csv：快腿列最新月 {_FASTM}、慢腿列最新月 {_SLOWM}'
            + ('，两者已追平。' if _FASTM == _SLOWM else '，正差着。'))
           if _FASTM and _SLOWM else '本次未能从 CSV 复算两条腿各自的最新月。'),

        'slow_cols（共 %d 列）不参与门槛判定，最新月留空是正常的。清单不手抄，'
        '由 fetch/db1.py 的模块常量 SLOW_LEG_COLUMNS 派生（本文件保留同名字面量兜底，'
        '两者本机实测一致）。把慢腿列放进门槛会让整页被拖住整整一个月。' % len(SLOW_COLS),

        '⚠ settle_icsd_txn_mn 只含 ICSD，**不含**德国本土 CSD 的约 2 倍笔数；'
        '而同一张表的 auc_securities_services_eurbn 却是 ICSD+CSD 合并 —— 同一份文件'
        '两行两个口径。两期独立实证：2025-12 台账结算 9.823717m ≡ Clearstream 稿 ICSD 9.8'
        '（CSD 17.6 不在内）；同期 AuC 16,788.0104 ≡ ICSD 9,756 + CSD 7,032。'
        '2026-03 再次复现（结算 11.867241m ≡ ICSD 12，CSD 25 不在内）。',

        '⚠⚠ AuC 的「存量」标注与官方口径有冲突，已按主线程指令标 stock: True，但换算时必须特判：'
        '官方 monthly-volume-development PDF 把这一行写成 '
        '"Value of securities deposited (average value)"，即**月内平均值而非期末时点**'
        '（otc_notional_outstanding / gsf_collateral / cash_balances / auc_fund_services 同理）。'
        'stock: True 的缺省语义是配月末汇率，而这几列跨币种换算应配**月均汇率**。'
        '本页是 EUR 本币页、不做换算，所以不影响当前呈现；notional.py 接手之前必须先解决这个冲突。',

        '📈 <b>现货成交额 2026-08-19 从一张热力矩阵改成两张折线，'
        '2016~2023 的水平值这才真的画在了页面上。</b>'
        '2026-08-18 那次把 Xetra 与法兰克福两条产线回补到 2016 年 —— 实测覆盖 '
        '<code>turnover_xetra_eurbn</code>（' + _cov_txt('turnover_xetra_eurbn')
        + '）、<code>turnover_fwb_eurbn</code>（' + _cov_txt('turnover_fwb_eurbn')
        + '）。但当时七列同组、超过「一张图最多 5 条靠颜色区分的序列」的上限，'
          '底座只能画热力矩阵；而矩阵格里是<b>同比</b>不是水平值、窗口又固定在近 24 个月，'
          '于是那次回补在页面上的全部体现只是「矩阵里少了几十个空格」，'
          '<b>2016~2023 那段水平值一格都看不见</b>。'
          '现在按<b>场所</b>拆成两组（Xetra 电子盘 4 列、法兰克福场内 3 列），'
          '两组都在上限之内 ⇒ 走折线，横轴一路铺回 2016-01。'
          '为什么不按「场所总额 / 分资产类别」拆：那样两组都会把量级差一两个数量级的列'
          '摆到同一根轴上（现算：法兰克福合计的中位数只有 Xetra 合计的 '
        + (('<b>%.1f%%</b>' % _R_VENUE) if _R_VENUE else '百分之几')
        + '、法兰克福结构化产品只有 Xetra 股票的 '
        + (('<b>%.1f%%</b>' % _R_CLASS) if _R_CLASS else '百分之一二')
        + '），小的那条会压成一条贴着零线的直线 —— 那只是把「看不见」换了个形状。'
          '按场所拆之后每组内部的极差都在一个数量级以内，三四条线都读得出来。',

        '⚠ <b>分资产类别那几条线中间是断的 —— 不是抓漏，是官方当年就没有。</b>'
        '现货两组走的是<b>不平滑</b>的 <code>lines</code> 图型：横轴由窗口<b>逐月</b>铺开，'
        '缺月留 null、折线在那里断笔。<b>绝不</b>把「有值的月」拼起来当横轴 —— '
        '那会把 2017-05 与 2022-05 画成相邻的两格（假时间轴）。现算：'
        + _drawn_gap_txt()
        + '成因分三层，实测都在 <code>build/basefill/db1_spot_2016.py</code> 的 docstring 里：'
          '① <b>官方那几年根本不发分场所的分类拆分</b> —— 2018-04 及更早的月度现货新闻稿'
          '是散文，只给得出两个场所总额（稿里那组分类数是 Xetra + 法兰克福 + Tradegate '
          '<b>三</b>场所合计，与本仓这两条场所列不是一个口径，不能拿来充数）；'
          '能给满精度拆分的存档工作簿只有 2016-06、2016-08~2017-05 与 2022-05 之后的若干期，'
          '中间那几年一期都没有 —— 两条 Xetra 分类线上 2017-06~2018-04 那个洞就是它。'
          '② <b>四个月官方没发月度稿</b>（2017-12、2018-06、2018-07、2019-12）：'
          '这几个月的场所总额是从次年同月那篇的「去年同月」对照行捡回来的，'
          '而那一行只有总额、没有分类 —— Xetra 分类线上 2018-06~2018-07 与 2019-12 '
          '那三个洞就是它。'
          '③ <b>精度闸门</b>：2018-05~2022-07 的新闻稿只印 1 位小数 €bn，四舍五入半宽 '
        + ('%g €bn' % _ROUND_HALF)
        + ' 落在法兰克福那五条分类列（equities / etp / bonds / funds / structured）'
          '上是 '
        + (('<b>±%.1f%%</b>' % _R_ROUND) if _R_ROUND else '百分之几')
        + '（各列中位数的中位；闸门比的是每组里最小的那个值，只会更糟），'
          '超过闸门的 3% ⇒ 整组丢弃。'
          '与其入库一个连环比方向都可能读反的数，不如让线断在那里。'
          '⇒ 反过来，两条<b>场所总额</b>位数绰绰有余（同样 '
        + ('%g €bn' % _ROUND_HALF) + ' 落在 Xetra 合计上只有 '
        + (('±%.2f%%' % _R_ROUND_X) if _R_ROUND_X else '万分之几')
        + '），所以它们 2016-01 起 127 个月无洞 —— 那 96 个月的回补在这两张图上是'
          '<b>连续、可读的水平值</b>，不必再退到表格视图去查。',

        '⚠ 现货那两组是**月度总额**不是 ADV。官方现货工作簿只发月总额；'
        'ADV = 月总额 ÷ trading_days_cash，官方新闻稿印的 ADV 正是这个商。'
        + ((f'本机最新一个两列都有值的月是 {_ADVM}：'
            f'turnover_xetra_eurbn = {_ADVT:.3f} ÷ {_ADVD:.0f} 个现货交易日 = {_ADVV:.3f} €bn/日。'
            if _ADVM else '')
           + ('但 <b>trading_days_cash 是慢腿</b>（次月约第 10 天才随集团台账到齐；'
              + (f'本机此刻快腿列与慢腿列都到 {_FASTM}，赶上了'
                 if _FASTM and _FASTM == _SLOWM else
                 f'本机此刻快腿列到 {_FASTM}、慢腿列只到 {_SLOWM}，正差着'
                 if _FASTM else '每个月总有几天它落在后面')
              + '）：拿它当除数，')
           + '算出来的 ADV 会跟着变成慢腿列，正好丢掉快腿的意义 —— 这就是本页只画月度总额的原因。')
        + '除数与 trading_days_eurex '
        + ((f'在 {_CALN} 个可比月里有 {_CALDIFF} 个不等') if _CALN else '并不总是相等')
        + '（德国统一日与圣灵降临节周一 Eurex 开、Xetra 关），两个日历不能互相顶替。',

        '⚠ vol_fd_*（台账口径）与 adv_eurex_* / oi_eurex_*（Eurex 工作簿口径）是两套并行口径，'
        '**永不互校、也不要放进同一条线**。全量实测（现算，不是写死的快照）：'
        + ((f'vol_fd_rates 与 Eurex 利率组小计 {_RATEN} 个月里 {_RATEDIFF} 个不等；')
           if _RATEN else 'vol_fd_rates 与 Eurex 利率组小计逐月不等；')
        + ((f'按官方脚注把股息衍生品摊回股指+单股之后，{_EQN} 个月里 {_EQDIFF} 个仍然不等。')
           if _EQN else '按官方脚注把股息衍生品摊回股指+单股之后仍然不等。')
        + '官方脚注自己也写明「总数不等于分项之和」（含 ETC / 农产品 / 贵金属）。',

        '⚠ EEX 三列的单位是 **MWh 不是 TWh**。官方工作簿表头写「(in TWh)」是笔误，'
        '差 10⁶：2026-06 单元格 power spot 88,034,094.5 / power deriv 960,720,291 / '
        'gas 679,742,442.47，同期官方 PDF 是 88.0 / 960.7 / 679.7 TWh。'
        '列名带 _mwh 就是这个原因，本页照原值画，不做换算。',

        'aum_stoxx_dax_etf_eurbn 的时点口径**官方未言明**：同一页别的行都标了 (average value)，'
        '唯独这一行没标，暗示是期末数，但这是推断不是证据。本页按 stock: True 标注，'
        '在拿到官方定义前不要拿它跟 msci.aum_eop_usdbn 比水平值。',

        'adv_360t_fx_eurbn 自 2018-07 起含 GTX，跨那个月的同比不是纯内生增长。'
        '这是列级口径变化、不是全页断点，所以不画红线。',

        'turnover_xetra_structured_eurbn 刻意不入图：官方多数月本来就不发这一格'
        '（工作簿留空、新闻稿印 "-"），本机实测 ' + _cov_txt('turnover_xetra_structured_eurbn')
        + '。<b>不入图的理由不是「怕平滑图型把 null 当 0」</b>（现货两组走的是不平滑的 '
          'lines，null 就是断笔）：是这条序列洞比值多，画出来是一串前后都是 null 的孤点，'
          '而孤点在折线里连一个笔画都构不成 —— 有洞的线还能读，全是洞的线读不了。'
          '再者法兰克福那组只剩 2 个名额，加回 3 条就重新越过 5 条线的上限、'
          '整组退回热力矩阵，正好把这次拆组要修的问题原样退回去。'
          '同样不入图的还有 turnover_fwb_etp / bonds / funds（' + _cov_txt('turnover_fwb_etp_eurbn')
        + '）—— 它们在 0.03~1.0 €bn 量级，官方新闻稿的位数不够，回填时被精度闸门整段丢弃。',

        '成交额一律**单边计**（single-counted）：FWB 工作簿「Explanation Report」表与 IR 台账 PDF '
        '现货行的脚注都写明了。跨家比要注意 HKEX 的南向 ADT 是双边。'
        '另：Xetra ≠ Deutsche Börse 现货全部 —— 2026-07 官方新闻稿的 €163.37bn 是 '
        'Xetra(XETR) €157.51bn + Frankfurt(XFRA) €5.86bn。',

        '三条腿都会被官方事后重述，fetcher 一律「只填空不覆盖」、冲突写 '
        'cache/db1_restatements.csv。实测：Eurex 月成交总数 vs 台账 vol_fd_total，'
        + ((f'{_FDGN} 个可比月里 {_FDGDIFF} 个不等') if _FDGN else '逐月常常不等')
        # ⚠ 下面这半句**不是本仓能现算的**：它比的是同一列在两期工作簿里的两个 vintage，
        #   而旧 vintage 只在抓取时见过一次（冲突写 cache/db1_restatements.csv，
        #   当前无冲突、文件尚未生成）。所以只能是一次性实测 —— 那就把日期写出来，
        #   让读者知道它是快照而不是「此刻」，别再让它冒充一个会自己更新的数。
        + '；另有一次性 vintage 对比（2026-08 实测，不随 CSV 更新）：'
          'Eurex 未平仓 222 对里 17 对不等，最大 2.48%（2008-07）。'
          '所以历史段与当年印出来的数字对不上是官方重述，不是本页算错。',

        '各列首个非空月（<b>逐列现算</b>，不是手抄的清单 —— 手抄的那版把 '
        '<code>vol_fd_total_contracts</code> 写成 2010-01，实际是 2009-01）：'
        + (_STARTS_ZH or '（本次未能从 CSV 复算各列首月。）')
        + '。早于首月为空是官方就没有。现货那几列 2026-08-18 回填过，覆盖与空洞逐列现算如下 —— '
        + '；'.join('<code>%s</code> %s' % (c, _cov_txt(c)) for c in (
            'turnover_xetra_eurbn', 'turnover_fwb_eurbn',
            'turnover_xetra_equities_eurbn', 'turnover_xetra_etp_eurbn',
            'turnover_fwb_equities_eurbn', 'turnover_fwb_structured_eurbn')) + '。',

        '⚠ <b>现货那两组有精度分层，跨年比要知道哪一段是四舍五入值。</b>'
        '2016-01~2023-12 不是本仓抓的，是 build/basefill/db1_spot_2016.py 一次性回填的：'
        '满精度（官方工作簿原值）只有 2016-06、2016-08~2017-05、2022-01~2024-05 与 2024-12 起；'
        '其余月份取自同站<b>月度现货新闻稿</b>，2016-01~2022-07 是 1 位小数 €bn、'
        '2022-08 起是 2 位小数。对两条场所总额，四舍五入的最大相对误差 '
        'Xetra ≤0.06%、法兰克福 ≤2.2%（画月度形状够用，但别拿它做小数点后两位的对账）；'
        '分资产类别列里位数不够的格子已经在回填时被精度闸门整组丢弃，'
        '所以它们是断的而不是被凑出来的。'
        '<b>口径没有变</b>：回填值与本仓其余月份同为单边计的 order book turnover、同两个场所，'
        '逐月都过了「Xetra + 法兰克福 ≡ turnover_cash_total_eurbn」的台账闭合检验'
        # ⚠ 这个括号原先抄的是 build/basefill/db1_spot_2016.py 运行时打印的两个计数
        #   （「N 个工作簿月…；M 个新闻稿月…」）。工作簿那一侧在 CSV 里复算得出，
        #   新闻稿那一侧**复算不出来**：按回填窗口去数得到的是另一个数，而 basefill
        #   自己的 docstring 与 `CLOSURE_SLACK` 的常量注释里，同一个计数还写着两个不同的
        #   值（两处对不上）。抄一个没人能复算、源头还自相矛盾的数进图注 = 又养一句假话。
        #   ⇒ 只印**从 series/db1.csv 现算得出来**的那部分：窗口右端是回填的作用域、
        #   一次性冻住的闭区间，不随 CSV 生长；月数与残差每次构建现算。
        + ((f'（现算：回填窗口 {_BF0}…{_BF_END} 里 {_BFN} 个三列都有值的月，'
            f'残差最大 {_ceil_to(_BFMAX, 4):.4f} €bn @{_BFM}'
            f'（上界向上取整），全在 1 位小数的四舍五入界内）。')
           if _BFN else '（本次未能从 CSV 复算这道闭合检验。）')
        + '所以 breaks 仍然留空 —— 这是精度断点，不是口径断点，画红竖线会误导。',
    ],
}
