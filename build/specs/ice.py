# -*- coding: utf-8 -*-
"""ICE（Intercontinental Exchange，NYSE: ICE）单公司页配置。

一行一条注册、删掉不留残渣：本文件是 ICE 在看板里的**全部**足迹，
除了 series/ice.csv 与导航注册表之外，没有任何一处写着 "ice"。

口径以 docs/verify/verify_ice.md（复核稿，判定 A）为准，与 docs/verify/ice.md
（侦察稿）冲突时一律听复核稿 —— 侦察稿的 §5「Cloudflare 403」「adv_fx_credit 含信用」
两条已被复核实测证伪。

列名全部对着 `head -1 series/ice.csv` 逐字核过。**列数 / 月数 / 起止月 / 哪几列有空洞
一个都不写在这里** —— 它们每个月都在变，写进注释就是养一句下个月自动过期的话；
要用就调 `_shape()` / `_cds_start()`（图注印的就是它们的返回值）。
（上一版这里写着「CDS 三列比其余列晚两年起步，其余各列零空洞」—— 后半句是个全称断言，
没有任何检查会在它变假时报警，删掉；前半句改由 `_cds_start()` 现算并印进图注。）

━━ 📌 本页做不了量价分解，而且「收入分解」也不是它的替身 ━━━━━━━━━━━━━━━━
量价分解的恒等式是 `成交额 ≡ 成交量 × 成交价`。本表**一条成交金额列都没有** ——
`adv_*_kcontracts` 是张数、`oi_*` 是未平仓张数、`adv_nyse_tape*_mnsh` 是股数，
唯一带货币单位的是 `rpc_*_usd` 与 `cds_*_notional_usdbn`。

⚠ **`rpc_*_usd` 是每张收入（费率），不是成交价。**这是本页最容易犯的一个错：
它长得像「价」（美元 / 张），语义却完全不同 —— 成交价是市场撮合出来的价格，
每张收入是 ICE 向会员收的费。拿它当 `decomp` 的派生量，底座会印出
「成交量加权平均成交价」那一整套措辞，句句是假的。

ICE 确实有另一条恒等式 `交易收入 ≡ 成交量 × 每张费率`，底座也确实为它准备了
`kind='revenue_rate'`（图注会写明「分解的是**收入**不是成交额；与前两类不可并读」）。
**但本页仍然不画**，原因是缺列不是缺口径：`decomp.value` 要的是一条**真实存在的
金额列**，而本表没有收入列。用 `ADV × 交易日 × RPC` 现造一条，等于把算术写进 spec ——
契约第一句就是「配置里只有数据，没有逻辑」，而且那样造出来的「收入」既不是 ICE 的
分部收入口径（不含数据 / 上市 / 固定收益等非交易收入），也没有任何官方数字能对账。
⇒ 📌 **不具备数据条件，不凑。**RPC 本身照常上页面（「单位经济」那一组），
它作为费率序列是有信息的，只是不能进分解图。

`cds_*_notional_usdbn` 是清算名义额，配得上的数量列同样没有（没有 CDS 笔数 / 张数列）。
"""

import csv
import math
import os

_CSV = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), 'series', 'ice.csv')


# ══════════════════════════════════════════════════════════════════════════════
# 图注里要报的数**一个都不写死**：在 import 期从 series/ice.csv 的表头现数。
# 读不到就退回不含数字的定性版本 —— 缺文件不许在 import 期抛异常，
# 否则 monthly_run 会因为一张页的配置炸掉整批。
# ══════════════════════════════════════════════════════════════════════════════
def _column_census():
    """数「金额列 / 数量列 / 费率列」各几条 —— 「做不了分解」的机器判据。

    返回 (成交金额列数, 数量列数, 费率列数, 清算名义额列数)；读不到返回 (None,)*4。
    """
    try:
        with open(_CSV, encoding='utf-8') as fh:
            cols = next(csv.reader(fh))
    except (OSError, StopIteration):
        return (None,) * 4
    rate = [c for c in cols if c.startswith('rpc_')]
    notional = [c for c in cols if 'notional' in c]
    qty = [c for c in cols if c.endswith('_kcontracts') or c.endswith('_mnsh')]
    # 「成交金额」= 带货币单位、且不是费率、不是清算名义额的列。本表应当是 0 条。
    money = [c for c in cols
             if (c.endswith('_usd') or c.endswith('_usdbn') or 'usd' in c)
             and c not in rate and c not in notional]
    return len(money), len(qty), len(rate), len(notional)


def _split_vs_total():
    """商品合计 + 金融合计 与「衍生品总 ADV」的相对差 —— 「两套交易日」的直接证据。

    官方分项与合计用不同的交易日归一，所以这两个数本来就不该逐格相等。
    量出来才敢在图注里说「没有哪一套交易日能单独代表总 ADV」。

    返回 (可比月数, 最大相对差%, 中位相对差%)；算不出返回 (None, None, None)。
    """
    rel = []
    try:
        with open(_CSV, encoding='utf-8') as fh:
            for r in csv.DictReader(fh):
                try:
                    c = float(r['adv_commodities_kcontracts'])
                    f = float(r['adv_financials_kcontracts'])
                    t = float(r['adv_futures_options_kcontracts'])
                except (KeyError, ValueError, TypeError):
                    continue
                if t:
                    rel.append(abs((c + f) / t - 1.0) * 100.0)
    except OSError:
        return (None,) * 3
    if not rel:
        return (None,) * 3
    rel.sort()
    return len(rel), rel[-1], rel[len(rel) // 2]


def _split_exact_months():
    """上面那组月份里，商品合计 + 金融合计与总 ADV **精确相等** 的月数。

    释义板要说的是「这不是恒等式」，而「大多数月份其实相等、少数月份不等」比只报一个
    最大相对差更能挡住误用：读者看见 121/187 就不会把偶发的不等当成解析错误去「修」。
    现算，不写死。算不出返回 None。
    """
    n = 0
    ok = False
    try:
        with open(_CSV, encoding='utf-8') as fh:
            for r in csv.DictReader(fh):
                try:
                    c = float(r['adv_commodities_kcontracts'])
                    f = float(r['adv_financials_kcontracts'])
                    t = float(r['adv_futures_options_kcontracts'])
                except (KeyError, ValueError, TypeError):
                    continue
                if t:
                    ok = True
                    n += (c + f == t)
    except OSError:
        return None
    return n if ok else None


def _rows():
    try:
        with open(_CSV, encoding='utf-8') as fh:
            return list(csv.DictReader(fh))
    except OSError:
        return []


def _num(r, col):
    """CSV 里一格 → float；空格子 / 非数返回 None（不拿 0 冒充缺失）。"""
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


def _shape():
    """(数据列数, 月数, 首月, 末月)；读不到返回 (None,)*4。

    2026-08-19 现算化：这四个数原先写死成「55 列，187 个月，2011-01..2026-07」，
    分散在模块 docstring 与四条图注里。**每长一个月就全体过期**，而页头那句
    「覆盖 Jan-11 – Jul-26（187 个月）」是底座现算的 —— 两处并排印在同一页上，
    下个月就会一个说 188、一个说 187。所以一个都不留，全部从 CSV 现数。
    """
    rows = _rows()
    if not rows:
        return (None,) * 4
    return (len(rows[0]) - 1, len(rows), rows[0]['month'], rows[-1]['month'])


#: 允许出现非整数的列的前缀 —— 图注那句「非整数的只有 RPC 与份额这几列」的**判据**。
_NONINT_OK = ('rpc_', 'share_')


def _nonint_census():
    """(非整数列名 list, 非整数格数)；算不出返回 ([], None)。

    「官方原表就已四舍五入到整千张 / 整百万股，只有 RPC 与份额这些列是非整数」
    —— 这句话的机器判据。列数与格数都随源表长，不写死。

    ⚠ 上一版这个函数**只数了列数、没有验列名**：图注照样印「非整数的只有 RPC 与
    份额这 N 列」，而 N 是数出来的、「只有 RPC 与份额」是人写的。哪天官方给某条
    张数列发了小数，N 会自己变成 14，那句全称断言却会继续印，而且没有任何东西会
    报错 —— 正是这一轮要消灭的那种句子。所以判据下沉到这里：**名单对不上就停机**。
    """
    rows = _rows()
    if not rows:
        return [], None
    cols = [c for c in rows[0] if c != 'month']
    names, cells = [], 0
    for c in cols:
        bad = sum(1 for r in rows
                  if (v := _num(r, c)) is not None and abs(v - round(v)) > 1e-9)
        if bad:
            names.append(c)
            cells += bad
    off = [c for c in names if not c.startswith(_NONINT_OK)]
    if off:
        raise SystemExit(
            'series/ice.csv：图注断言「非整数的只有 RPC 与份额那几列」，但 %s '
            '也有非整数格 —— 断言与数据对不上，先改图注再构建'
            '（build/specs/ice.py 的 _nonint_census / _NONINT_OK）' % '、'.join(off))
    return names, cells


def _sum_check(children, total, tol=2.0):
    """(可比月数, 逐格精确相等的月数, 差 ≤tol 的月数)；算不出返回 (None,)*3。

    「分项之和 ≠ 合计，不要当恒等式」那条注的判据。分子分母都会随月份长，
    所以 85/187 这种写法必须现算 —— 写死的分母下个月就与页头的月数打架。
    """
    rows = _rows()
    if not rows:
        return (None,) * 3
    n = ex = near = 0
    for r in rows:
        t = _num(r, total)
        vs = [_num(r, c) for c in children]
        if t is None or any(v is None for v in vs):
            continue
        n += 1
        d = abs(sum(vs) - t)
        if d < 1e-9:
            ex += 1
        if d <= tol:
            near += 1
    return (n, ex, near) if n else (None,) * 3


def _tdays_split():
    """(可比月数, 两套交易日相等的月数, 不等的月数)；算不出返回 (None,)*3。"""
    rows = _rows()
    if not rows:
        return (None,) * 3
    n = eq = 0
    for r in rows:
        a, b = _num(r, 'trading_days_commod'), _num(r, 'trading_days_rates')
        if a is None or b is None:
            continue
        n += 1
        if a == b:
            eq += 1
    return (n, eq, n - eq) if n else (None,) * 3


#: 「四家交易所占全美现货多少」那条注要读的另外三家的列。
#: 只读不写、逐个 try —— 少了任何一家（那一页被删掉了）就退回不含数字的定性版本，
#: 本页不因为别人的文件不在而炸掉，也不因为别人多发了一个月而说假话。
_PEERS = (
    ('cboe.csv', 'adv_us_equities_matched_shares_bn', 1000.0),   # bn 股 → mn 股
    ('miax.csv', 'adv_equities_mnshares', 1.0),
)
_NDAQ = ('ndaq.csv', 'share_us_cash_matched_group')              # 已是 0–1 的份额


def _venue_mix():
    """四家自营撮合量合计占全美合并量的比例 —— 「场外化侵蚀」那条注的算术。

    **取「四家都有值的最新一个月」，现找不写死。**原先这条注把 2026-06 那次实测
    连同「（四家份额都有值的最新一个月）」这半句一起写死了；等 2026-07 四家都发齐，
    页面上那句就成了假话 —— 而它自称的判据（「最新一个月」）恰恰是**能现算**的。

    返回 dict(month, total, nyse, nyse_pct, cboe, cboe_pct, ndaq_pct,
              miax, miax_pct, four_pct, rest_pct)；算不出返回 None。
    """
    base = os.path.dirname(_CSV)
    ice = {r['month']: r for r in _rows()}
    if not ice:
        return None
    peer = {}
    for fn, col, mult in _PEERS + ((_NDAQ[0], _NDAQ[1], 1.0),):
        try:
            with open(os.path.join(base, fn), encoding='utf-8') as fh:
                peer[fn] = {r['month']: r for r in csv.DictReader(fh)}
        except OSError:
            return None
    for m in sorted(ice, reverse=True):
        tape = [_num(ice[m], 'adv_tape%s_consolidated_mnsh' % t) for t in 'ABC']
        nyse = [_num(ice[m], 'adv_nyse_tape%s_matched_mnsh' % t) for t in 'ABC']
        if any(v is None for v in tape + nyse):
            continue
        total = sum(tape)
        if not total:
            continue
        vals = {}
        for fn, col, mult in _PEERS:
            r = peer[fn].get(m)
            v = _num(r, col) if r else None
            if v is None:
                break
            vals[fn] = v * mult
        else:
            r = peer[_NDAQ[0]].get(m)
            nd = _num(r, _NDAQ[1]) if r else None
            if nd is None:
                continue
            cb, mi = vals['cboe.csv'], vals['miax.csv']
            p = dict(month=m, total=total, nyse=sum(nyse), cboe=cb, miax=mi,
                     nyse_pct=sum(nyse) / total * 100.0,
                     cboe_pct=cb / total * 100.0,
                     ndaq_pct=nd * 100.0,
                     miax_pct=mi / total * 100.0)
            p['four_pct'] = p['nyse_pct'] + p['cboe_pct'] + p['ndaq_pct'] + p['miax_pct']
            p['rest_pct'] = 100.0 - p['four_pct']
            return p
    return None


def _miax_industry_start():
    """series/miax.csv 里那条行业 ADV 的首月；读不到返回 None。

    「本页这条现货行业分母回溯得比同仓那条深」这句话的另一半判据 —— 两个起点都
    现读，谁被回补都不用改这句话。miax 那页被删掉时返回 None，本页退回不比较的说法。
    """
    try:
        with open(os.path.join(os.path.dirname(_CSV), 'miax.csv'), encoding='utf-8') as fh:
            ms = [r['month'] for r in csv.DictReader(fh)
                  if _num(r, 'industry_adv_equities_mnshares') is not None]
    except OSError:
        return None
    return ms[0] if ms else None


def _miax_crosscheck(k=2):
    """ICE 三 tape 合并量 vs MIAX 自报行业 ADV，最近 k 个都有值的月。

    返回 [(月, ICE 合并量, MIAX 行业量), …]（新月在前）；算不出返回 []。
    """
    base = os.path.dirname(_CSV)
    try:
        with open(os.path.join(base, 'miax.csv'), encoding='utf-8') as fh:
            mi = {r['month']: r for r in csv.DictReader(fh)}
    except OSError:
        return []
    out = []
    for r in reversed(_rows()):
        tape = [_num(r, 'adv_tape%s_consolidated_mnsh' % t) for t in 'ABC']
        m = mi.get(r['month'])
        v = _num(m, 'industry_adv_equities_mnshares') if m else None
        if any(t is None for t in tape) or v is None:
            continue
        out.append((r['month'], sum(tape), v))
        if len(out) >= k:
            break
    return out


def _ceil_to(v, nd):
    """把 v 向**上**取到 nd 位小数 —— 印「最大不超过 X」时必须这么取。

    四舍五入有一半的概率把上界取**小**，于是页面印出来的那个「最大值」比真正的
    最大值还小 —— 一句自称现算的话，被它自己现算的那列证伪。上界向上取、
    下界向下取，印出来的区间才永远含得住实测值。（这里**不举实测数字当例子**：
    举一个就等于再养一个下个月过期的数。）
    """
    f = 10.0 ** nd
    return math.ceil(v * f - 1e-9) / f


_CDS_COLS = ('cds_client_notional_usdbn', 'cds_nonclient_notional_usdbn',
             'cds_total_notional_usdbn')


def _cds_start():
    """CDS 三列共同的首月，以及它比全表首月晚多少个整年。

    ⚠ 图注原先写死「CDS 三列自 2013-01 起（比其余列晚两年）」。起点是能现算的
    （官方回补一次就左移），「晚两年」更是两个现算月份的差 —— 一个都不该抄。
    **三列首月不一致就停机**：那句话说的是「三列」，判据就得管着三列，
    否则它会在某一列被单独回补之后继续印，而没有任何东西会报错。

    返回 (首月, 晚了几年的中文, 相差月数)；算不出返回 (None, None, None)。
    """
    rows = _rows()
    if not rows:
        return (None,) * 3
    firsts = {}
    for c in _CDS_COLS:
        ms = [r['month'] for r in rows if _num(r, c) is not None]
        if ms:
            firsts[c] = ms[0]
    if len(firsts) != len(_CDS_COLS):
        return (None,) * 3
    if len(set(firsts.values())) != 1:
        raise SystemExit(
            'series/ice.csv：图注断言「CDS 三列自同一个月起」，但实际首月是 %s '
            '—— 断言与数据对不上，先改图注再构建（build/specs/ice.py 的 _cds_start）'
            % '、'.join('%s=%s' % kv for kv in sorted(firsts.items())))
    m0 = next(iter(firsts.values()))
    y0, mo0 = (int(x) for x in rows[0]['month'].split('-'))
    y1, mo1 = (int(x) for x in m0.split('-'))
    lag = (y1 - y0) * 12 + (mo1 - mo0)
    zh = ('%d 年' % (lag // 12)) if lag % 12 == 0 else ('%d 个月' % lag)
    return m0, zh, lag


def _share_selfcheck():
    """官方给的 NYSE matched 份额 vs 本机自算 —— (可比月数, 最大 pp 差, 中位比值)。

    ⚠ 这两个数原先写死成「误差 <0.15pp」与「中位比值 = 1.000」。两个都是**实测**，
    两个都会被下一个月的读数顶开，而两个都能现算。算不出返回 (None, None, None)。
    """
    diffs, ratios = [], []
    for r in _rows():
        s = _num(r, 'share_nyse_us_cash_matched')
        tape = [_num(r, 'adv_tape%s_consolidated_mnsh' % t) for t in 'ABC']
        nyse = [_num(r, 'adv_nyse_tape%s_matched_mnsh' % t) for t in 'ABC']
        if s is None or any(v is None for v in tape + nyse) or not sum(tape):
            continue
        own = sum(nyse) / sum(tape)
        diffs.append(abs(s - own) * 100.0)
        if own:
            ratios.append(s / own)
    if not diffs:
        return (None,) * 3
    ratios.sort()
    n = len(ratios)
    med = ratios[n // 2] if n % 2 else (ratios[n // 2 - 1] + ratios[n // 2]) / 2.0
    return len(diffs), max(diffs), med


_NMONEY, _NQTY, _NRATE, _NNOT = _column_census()
_SPLITN, _SPLITMAX, _SPLITMED = _split_vs_total()
_SPLITEQ = _split_exact_months()
_CDS0, _CDSLAG_ZH, _CDSLAG = _cds_start()
_SHN, _SHMAXPP, _SHMED = _share_selfcheck()
_NCOLS, _NMONTHS, _M0, _M1 = _shape()
_NONINT_COLS, _NONINT_CELLS = _nonint_census()
_ENN, _ENEX, _ENNEAR = _sum_check(
    ['adv_brent_kcontracts', 'adv_gasoil_kcontracts', 'adv_otheroil_kcontracts',
     'adv_natgas_kcontracts', 'adv_power_kcontracts', 'adv_environmentals_kcontracts'],
    'adv_energy_kcontracts')
_FIN, _FIEX, _FINEAR = _sum_check(
    ['adv_stir_kcontracts', 'adv_mltir_kcontracts', 'adv_equity_index_kcontracts',
     'adv_fx_credit_kcontracts'], 'adv_financials_kcontracts')
_TDN, _TDEQ, _TDNE = _tdays_split()
_MIX = _venue_mix()
_XCHK = _miax_crosscheck()
_MIAX0 = _miax_industry_start()

_NO_DECOMP_NOTE = (
    '📌 <b>本页不具备量价分解的数据条件。</b>量价分解的恒等式是「成交额 ≡ 成交量 × '
    '成交价」，而本表<b>一条成交金额列都没有</b>：'
    + ((f'数量类列 <b>{_NQTY}</b> 条（合约张数与股数），费率类 <code>rpc_*</code> '
        f'<b>{_NRATE}</b> 条，清算名义额 <b>{_NNOT}</b> 条，'
        f'真正的成交金额列 <b>{_NMONEY}</b> 条。'
        if _NQTY is not None else
        '数量类列有几十条，货币单位的只有 rpc_* 与 CDS 清算名义额。'))
    + '<b>⚠️ <code>rpc_*_usd</code> 是每张收入（费率），不是成交价</b> —— '
      '这是本页最容易犯的一个错：它长得像「价」（美元/张），语义却完全不同。'
      '成交价是市场撮合出来的价格，每张收入是 ICE 向会员收的费。'
      '拿它当分解的派生量，图注会印出「成交量加权平均成交价」那一整套措辞，句句是假的。'

      '<b>ICE 确实另有一条恒等式：交易收入 ≡ 成交量 × 每张费率。</b>'
      '那是<b>收入分解</b>，与成交额分解不是一回事，两者的读数<b>不可并读</b>。'
      '本页仍然不画它，原因同样是缺列：分解图要的是一条<b>真实存在的金额列</b>，'
      '而本表没有收入列。用「ADV × 交易日 × RPC」现造一条，'
      '既把算术写进了配置（契约只允许配置放数据、不放逻辑），'
      '造出来的「收入」也不是 ICE 任何一个官方口径（不含数据 / 上市 / 固定收益等'
      '非交易收入），没有任何官方数字能对账。<b>不具备数据条件，不凑。</b>'
      'RPC 本身照常上页面（见「单位经济」那一组），它作为费率序列有信息，'
      '只是不能进分解图。'
)

_NOTE_TTM_FO = (
    '<b>⚠️ 本图没有交易日权重列可用，这是有意的选择而不是疏漏。</b>'
    '<code>series/ice.csv</code> 里有两套交易日（<code>trading_days_commod</code> 与 '
    '<code>trading_days_rates</code>），而「衍生品总 ADV」横跨商品与金融两侧，'
    '没有哪一套能单独代表它 —— 官方自己也是分项与合计用不同的交易日归一。'
    + ((f'这件事在本表里量得出来：商品合计 + 金融合计与「衍生品总 ADV」的相对差'
        f'<b>中位 {_SPLITMED:.3f}%、最大 {_SPLITMAX:.3f}%</b>（{_SPLITN} 个月）——'
        f'两套交易日不同，分项与合计本来就不该逐格相等。'
        if _SPLITMAX is not None else
        '分项之和与合计因此有一个系统性差。'))
    + '硬挑一套乘回去，会给一半的量配错权重，而图上完全看不出来。'
    '<b>⇒ 2026-09 起这件事在本图上整个消失了</b>：金线改成本列自己的<b>单月同比</b>'
    '（日均 ÷ 去年同月日均），既不做滚动合计、也就不需要把日均还原成当月合计，'
    '一条交易日列都用不上。'
    '⚠️ 代价是另一头：日均口径除掉的是「本月开了几天」，'
    '除不掉「去年同月那一个数本身高不高」—— 图注后面那段实测就是量这个的。'
)

_NOTE_TTM_CASH = (
    '<b>柱与线取自同一列</b>（<code>adv_nyse_us_cash_handled_mnsh</code>，当月日均）：'
    '柱是水平值，金线是它自己的<b>单月同比</b>，拿这根柱除以 12 根柱之前那根就是'
    '线上这一点。日均口径本身已经把「这个月多开了几天市」除掉了。'
    '⚠️ 2026-09 之前本图的金线是 12 个月滚动合计的同比，用 '
    '<code>trading_days_us_equities</code>（官方拿来算这条 ADV 的那一列除数）'
    '把日均精确还原成当月合计再滚 —— 改单月口径后那一步不再需要。'
    '⚠️ handled ≠ matched：handled 含 ICE 为客户路由到别家撮合的量，'
    'matched 才是本所自己撮合的。市场份额只能用 matched 算'
    '（见「NYSE 美股现货：本所量 vs 全市场分母」那一组）。'
)

# ── 为什么 fmt 这么选 ───────────────────────────────────────────────────────
# 1) 月度单元格在官方原表里就已经四舍五入到整千张 / 整百万股（非整数格全落在 RPC
#    与份额那几列上，verify_ice §1.2；具体列数与格数由 `_nonint_census()` 现扫，
#    图注里印的就是它的返回值，这里不复述一个会过期的快照）。
#    给月度 ADV 标小数位是假精度 ⇒ 计数类一律 f0c（千分位整数，见 assets/charts.js
#    的 `FMT.f0c`；**别在这里写行号** —— charts.js 一改就漂）。
# 2) share_* 五列在 CSV 里是**分数**（0.191 = 19.1%），不是百分数。
#    charts.js 的 pct1 实现是 `v.toFixed(1) + '%'`（`FMT.pct1`），**不做 ×100**，
#    直接配 pct1 会把 19.1% 印成「0.2%」—— 图照画、没人报错。
#    所以这五列一律 `'scale': 100` + pct1。本机用算术验过是分数而不是百分数：
#    share ÷ (matched ÷ consolidated) 的中位比值 ≈ 1（若是百分数会是 100）——
#    具体数由 `_share_selfcheck()` 现算并印在图注上，**这里不复述一个会过期的快照**。
#    对照：series/miax.csv 的 share_*_pct 存的是百分数（比值两个数量级之差），那边不加 scale。
# 3) 小数位一律**等于官方发的位数**，不多不少：rpc_*_usd 与 rpc_nyse_equity_options_usd
#    源表给 2 位（0.05 / 0.04），rpc_nyse_us_cash_usd_per100sh 给 3 位（0.032~0.055），
#    share_* 给到 0.001 的分数（= 0.1pp）。所以是 f2 / f3 / pct1。
#    ⚠️ 这三处**不许为了让标签变窄而降位**：降一位就是把 ICE 已经发出来的有效数字扔掉，
#    而 13 个月核对表的用途正是与官方披露逐格对账（CONTRACT §5.4）。
#    实测：share 降到 pct0 之后，汇总表「本月 / 上月 / 去年同月」三格会一起印成
#    「21%」，而旁边的变化列还写着 -10bp —— 表自己打自己。
# 4) 8 条 RPC 列一律 **f2 / f3 而不是 usd2 / usd3** —— 去掉 `$` 前缀。
#    `$` 在这一页是纯冗余：数字每一次出现旁边都已经写着单位 ——
#    图上是纵轴标题 `USD/contract`、核对表是表头「（USD/contract）」、
#    图注走 `unit_txt()` 印的是「$0.04 USD/contract」（币种符号与单位并排重复了一遍）。
#    去掉它不丢任何信息，却把柱顶数值标签从 20.0px / 24.5px 压到 15.6px / 20.0px
#    （8px 字号，尺子是 build/chartscale.py 的 `_label_px`）。
#    这是必要的：窗口拉到 2016-01 之后每张时序图有 127 格，通栏 band 只有 8.35px，
#    柱顶标签居中钉在自己那一格上、右轴刻度起于绘图区右缘 +6px，
#    ⇒ 标签宽度预算 = band + 12 − 2×LAB_GAP = 17.3px（`chartscale._budget`）。
#    超预算的标签会横向伸进右轴刻度那一列，和金色同比刻度叠字。
#    每次 `python3 build/single.py ice` 都会把当轮实测值打在日志里
#    （「⚠️ Exhibit N 柱顶标签压轴刻度：… 宽 …px > 预算 …px」），不用人眼去看。
#    去 `$` 之后 Exhibit 12（期权 RPC，2 位小数）落进预算、不再叠字；
#    Exhibit 15（现货 RPC）「0.041」= 20.0px 仍超 2.7px —— 3 位有效数字最短就是这么宽，
#    再窄只能降位或改用官方没发过的单位（美分），两条都比这处叠字更坏，所以留着。
#
# 5) ⚠️ **上面 3) 4) 两条只谈排版。2026-09 之前 fmt 还<u>顺带决定同比口径</u>，
#    而那一层上一版一个字没写 —— 本轮把口径这一层拆出来，并把它写在这里。**
#    CONTRACT §6.1 第 4 条：比率序列的同比一律走**百分点差**（RPC 从 0.24 到 0.25
#    是 +1bp，不是 +4.2%）。本页 8 条 `rpc_*` 与 5 条 `share_*` 都是比率列
#    （`yoy.classify()` 对这 13 个列名全部返回 'ratio'）。
#    改之前底座判比率只有一行 `c['fmt'] in RATIO_FMT`（pct*/pp*），于是 share 五列
#    （pct1，在名单里）走对了百分点差，RPC 八列（f2 / f3，不在名单里）走的是
#    「百分比的百分比变化」—— 差别只在 fmt，不在数据、不在图型。
#    实测被翻掉的三处：Exhibit 12（NYSE 期权 RPC）Jul-26 印 **−20.0%**、
#    Exhibit 15（现货 RPC，每 100 股）Jul-26 印 **+13.9%**、
#    Exhibit 9（RPC 滚动三月均热力矩阵）整张 6 行格内都是 %。
#    2026-09 起底座的判据是 `build/single.py` 的 `col_is_ratio()`，三级：
#    ① spec 显式 `'ratio': True/False` → ② `fmt ∈ RATIO_FMT` →
#    ③ `yoy.classify()` 判成比率 **且** `unit` 也是比率的量纲。
#    **本页 13 列全部由 ②③ 覆盖，一条 `'ratio'` 都不用写**：share 五列走 ②，
#    RPC 八列走 ③（`USD/contract` 与 `USD/100 shares` 都是「每一个可数活动单位」）。
#    ⚠️ **这个差的单位是钱，不是 pp/bp —— 2026-09-03 又改了一次，两轮都记下来。**
#    比率的同比走**差**（§6.1 第 4 条），这一步一直没变；但**差的单位跟着分子走**：
#    本页 8 条 `rpc_*` 的分子是美元，差出来仍然是美元/张，把它叫 1bp 是换了个量在说话。
#    NYSE 期权 RPC 从 0.05 掉到 0.04 是**跌了五分之一**，而「−1bp」读起来是万分之一 ——
#    只看页面的读者会把一次 20% 的单位经济下滑读成一次可以忽略的波动。
#    今天底座对这一档单列了轴标题与措辞（`build/single.py` 的 `unit_is_money_ratio()`
#    / `money_diff_txt()` / `rhs_ylab2()`）：
#      · 右轴标题 `USD/contract, y/y 差`、序列名 `y/y (USD/contract, RHS)`；
#      · 图注与汇总表印 **Exhibit 12 Jul-26 同比 −0.01 USD/contract**
#        （0.04 vs 去年同月 0.05）、**Exhibit 15 +0.005 USD/100 shares**
#        （0.041 vs 0.036）；
#      · Exhibit 9 那张 RPC 矩阵同理：图例改成「同比（USD/contract 的差）」、
#        格内格式从 `pp1` 换成 `f2`（`pp1` 会把 +0.12 美元/张印成「+0.1pp」）。
#    ⚠️ **payload 里的数一格没动**：仍是 `yoy.mom_yoy(s, yoy.RATIO)` 的差，
#    改的只是单位名与展示格式 —— `tools/check_yoy_caliber.py` 的回源复算认的是那些数。
#    （两轮之前这里还写过「Exhibit 15 是 +1bp」，那个 +1 不是四舍五入是**浮点残差**：
#     底座当时把 bp 一律按 `:+.0f` 取整，而 `0.041 - 0.036` 在双精度里是
#     0.0050000000000000044，掐着 0.5bp 的进位线往上翻了一格；同为 0.005 的
#     `0.040 - 0.035` 落在线的另一侧，会印成「0bp」。后来底座改成按量级给小数位
#     （`_bp_dec`），它变成「+0.5bp」；再后来单位整个换成钱，这一档对本页
#     8 条 RPC 列**不再适用** —— `_bp_dec` 今天服务的是本页 5 条 `share_*`
#     那种真·百分点比率。）
#    ⚠️ 于是 `unit` 这一栏在本页变成**承重的**：把 `USD/contract` 改写成量纲白名单
#    认不出的写法（例如只写 `USD`），③ 当场失效，这几列的同比会静默翻回 %。
#    要改单位就同时补上 `'ratio': True`。
#    ⚠️ **仍然不许拿改 fmt 去碰口径。** RPC 的量纲是 USD/contract 不是百分数：
#    配 pct* 既推翻 3) 的「小数位等于官方发的位数」，也会被底座那道比率量纲体检
#    （pct* 列最大绝对值须 > 1.5，而 `rpc_nyse_equity_options_usd` 全历史最大 0.18）
#    当场硬失败挡下。
#    ⚠️ **右轴刻度这一半也在底座解决了，别再往回改。** `pp` 族在
#    `assets/charts.js` 的 FMT 表里只有 pp0 / pp1 两档，而本页 RPC 的差是
#    0.01~0.06 这个量级 —— pp1 会把 Exhibit 12 的右轴印成一列「0.0pp」，
#    而且那个「pp」本身就是假单位。所以钱这一档在 `yoy_rhs()` 里直接取纯数字族
#    `f0`（随后由 axisfmt 升到 f2 / f3），单位交给右轴标题与图注；
#    真·百分点比率仍走 `pp_yfmt()`（它按引擎的刻度算法试算，1 位小数分不开刻度时
#    才换族）。所以 Exhibit 12 的右轴是「−0.06 … +0.03」、
#    Exhibit 15 是「−0.020 … +0.010」
#    （2026-09-03 本机按 `axisfmt.ticks` 实测，数据到 2026-07；刻度随数据走，
#     这里存的是那一天那个窗口的读数，不是一条恒成立的断言）。
#    图注与汇总表里那句「同比 −0.01 USD/contract」走的是 `money_diff_txt()`：
#    位数从该列自己的 `fmt` 起（官方发几位就是几位），只有在那个位数上四舍五入
#    成零、而差又不是零时才往下补位。
#
# 6) `oi_rates_kcontracts` 是 `yoy.classify()` 的一个**假阳性**，本页唯一一个：
#    列名里有 `rates` 就被判成 'ratio'，可它是**存量**列（月末净 OI，
#    13,040~50,770 k contracts，spec 里已标 'stock': True）。
#    判据要是无条件相信 classify()，Exhibit 23（未平仓合约·利率）的次轴会从
#    「% y/y」翻成「pp y/y」、画出一条几万「pp」的线 —— 而 `is_ratio` 在
#    `build/single.py` 里排在 `c['stock']` 前面，存量那一支根本轮不到。
#    今天挡住它的是 `col_is_ratio()` 第 ③ 级里的 `unit_is_ratio()`：本列的 unit 是
#    `k contracts`，没有「每一个可数活动单位」那种分母，量纲这一票投的是「不是比率」。
#    **所以这一列的 `unit` 也是承重的**，别为了好看改写它；真要改，同时写死
#    `'ratio': False`。本页其余 5 条 `oi_*` 不受影响（classify 直接判存量）。

SPEC = {
    'ticker': 'ice',
    'name':   'Intercontinental Exchange',
    'title':  '洲际交易所（ICE）月度经营指标',
    'csv':    'ice.csv',
    'ccy':    'USD',
    'source': 'Source: ICE Monthly Statistics Tracking spreadsheet (ir.theice.com ContentAsset feed, '
              'file hosted on s2.q4cdn.com); format after Goldman Sachs GIR',

    # 头条：TOTAL F&O ADV 与 NYSE 现货 handled ADV。
    # 两条都在同一个 xlsx 里、同一天发布、全历史零空洞 —— 满足「历史长 / 发布快 / 无空洞」。
    # 不用 adv_energy 之类分项当头条：分项与合计用不同的交易日归一，
    # 分项之和与合计有 0~0.55% 的系统性差（verify_ice §四.4），当门槛会引入无意义的抖动。
    'headline': [
        {'col': 'adv_futures_options_kcontracts', 'zh': '衍生品总 ADV',
         'unit': 'k contracts/day', 'fmt': 'f0c'},
        {'col': 'adv_nyse_us_cash_handled_mnsh',  'zh': 'NYSE 美股现货 ADV（handled）',
         'unit': 'mn shares/day', 'fmt': 'f0c'},
    ],

    'groups': [
        # ── 能源：ICE 的利润中心。六个子项 + TOTAL，六项之和 = TOTAL 只在一部分月份
        #    精确成立（各自四舍五入到整千张），±2 内才全中 —— 不要当恒等式校验。
        #    精确成立的月数由 `_sum_check()` 现算并印进图注（写死的 85/187 每长一个月
        #    就与页头那句「覆盖 … 个月」打架）。
        {'zh': '能源衍生品 ADV', 'cols': [
            {'col': 'adv_energy_kcontracts',         'zh': '能源合计',   'unit': 'k contracts/day', 'fmt': 'f0c'},
            {'col': 'adv_brent_kcontracts',          'zh': 'Brent 原油', 'unit': 'k contracts/day', 'fmt': 'f0c'},
            {'col': 'adv_gasoil_kcontracts',         'zh': 'Gasoil 柴油', 'unit': 'k contracts/day', 'fmt': 'f0c'},
            {'col': 'adv_otheroil_kcontracts',       'zh': '其他原油与成品油', 'unit': 'k contracts/day', 'fmt': 'f0c'},
            {'col': 'adv_natgas_kcontracts',         'zh': '天然气（含 TTF）', 'unit': 'k contracts/day', 'fmt': 'f0c'},
            {'col': 'adv_power_kcontracts',          'zh': '电力',       'unit': 'k contracts/day', 'fmt': 'f0c'},
            {'col': 'adv_environmentals_kcontracts', 'zh': '环境权益与其他', 'unit': 'k contracts/day', 'fmt': 'f0c'},
        ]},

        {'zh': '农产品与金属 ADV', 'cols': [
            {'col': 'adv_ag_metals_kcontracts',       'zh': '农产品与金属合计', 'unit': 'k contracts/day', 'fmt': 'f0c'},
            {'col': 'adv_sugar_kcontracts',           'zh': '糖',       'unit': 'k contracts/day', 'fmt': 'f0c'},
            {'col': 'adv_otherags_metals_kcontracts', 'zh': '其他农产品与金属', 'unit': 'k contracts/day', 'fmt': 'f0c'},
            {'col': 'adv_commodities_kcontracts',     'zh': '大宗商品合计（能源+农金）', 'unit': 'k contracts/day', 'fmt': 'f0c'},
        ]},

        # ── 金融：ICE 的利率腿是**欧洲曲线**（Euribor / SONIA / Gilts），
        #    与 CME 的美国曲线互补不竞争，横截面上只能画增速不能画绝对量。
        #    单股一列官方明说已从 TOTAL FINANCIALS 剔除，放在这里只作单独观察。
        {'zh': '金融衍生品 ADV', 'cols': [
            {'col': 'adv_financials_kcontracts',   'zh': '金融合计（不含单股）', 'unit': 'k contracts/day', 'fmt': 'f0c'},
            {'col': 'adv_stir_kcontracts',         'zh': '短期利率', 'unit': 'k contracts/day', 'fmt': 'f0c'},
            {'col': 'adv_mltir_kcontracts',        'zh': '中长期利率', 'unit': 'k contracts/day', 'fmt': 'f0c'},
            {'col': 'adv_equity_index_kcontracts', 'zh': '股指',     'unit': 'k contracts/day', 'fmt': 'f0c'},
            {'col': 'adv_fx_credit_kcontracts',    'zh': 'FX 与 USDX', 'unit': 'k contracts/day', 'fmt': 'f0c'},
            {'col': 'adv_single_stock_kcontracts', 'zh': '单股（已剔出合计）', 'unit': 'k contracts/day', 'fmt': 'f0c'},
            {'col': 'adv_futures_options_kcontracts', 'zh': '期货与期权总计', 'unit': 'k contracts/day', 'fmt': 'f0c'},
        ]},

        # ── OI：月末净未平仓，是**存量**（stock=True）。
        #    单位是千张 —— 与 cme.csv 的 oi_*_contracts（裸张）差 1000 倍，
        #    这是横截面上最容易翻车的一处（verify_ice §五.4）。
        #    官方没有 TOTAL OI 行，新闻稿里的 "Total OI" 是 commodities + financials 自己加的。
        {'zh': '未平仓合约（月末净 OI）', 'cols': [
            {'col': 'oi_commodities_kcontracts',       'zh': '大宗商品', 'unit': 'k contracts', 'fmt': 'f0c', 'stock': True},
            {'col': 'oi_energy_kcontracts',            'zh': '能源',     'unit': 'k contracts', 'fmt': 'f0c', 'stock': True},
            {'col': 'oi_ag_metals_kcontracts',         'zh': '农产品与金属', 'unit': 'k contracts', 'fmt': 'f0c', 'stock': True},
            {'col': 'oi_financials_kcontracts',        'zh': '金融',     'unit': 'k contracts', 'fmt': 'f0c', 'stock': True},
            # ⚠️ 这一列的列名里有 `rates`，`yoy.classify()` 因此把它误判成 'ratio' ——
            #    它是存量（月末净 OI）。挡住这个假阳性的是 unit（`k contracts`
            #    不是比率量纲）；改 unit 会让 Exhibit 23 的次轴翻成「pp y/y」。见第 6 条。
            {'col': 'oi_rates_kcontracts',             'zh': '利率',     'unit': 'k contracts', 'fmt': 'f0c', 'stock': True},
            {'col': 'oi_other_financials_kcontracts',  'zh': '股指与 FX', 'unit': 'k contracts', 'fmt': 'f0c', 'stock': True},
        ]},

        # ── RPC：滚动三月均，美元/张。与 Cboe 的 RPC 不同，ICE **不滞后**
        #    （2026-07 期 rpc_energy 已填），所以不进 slow_cols。
        #    但正因如此，任何 ICE vs Cboe 的 RPC 并排图，ICE 那条每月都会多伸出一格。
        #    ⚠️ 「滚动三月均」是 ICE 自己在表内脚注里的**披露口径**，是对<u>水平值</u>的
        #    平滑，与同比口径无关 —— 修同比不许动它。
        #    ⚠️ 这六列都是比率列，本组画成 Exhibit 9 那张热力矩阵。2026-09 起格内
        #    已经是**差**而不是 (a/b−1)×100（`col_is_ratio()` 第 ③ 级：
        #    classify → 'ratio'，unit `USD/contract` 是比率量纲）。
        #    ⚠️ **2026-09-03 再改一次：这个差的单位是钱，不是百分点。**
        #    这六列的分子是美元，当月减去年同月得到的仍然是美元/张 ——
        #    矩阵的 `fmt` 因此是 `f2`、图例是「同比（USD/contract 的差）」
        #    （`ex_heat()` 按 `unit_is_money_ratio()` 选；从前选的是 `pp1` /
        #    「同比（百分点差 pp）」，会把 +0.12 美元/张印成「+0.1pp」）。
        #    六列同为「分子是钱」的比率、不会与量列或百分点比率混色标 ——
        #    真混了底座会 SpecError，不会静默画错。
        {'zh': '单位经济：每张收入（RPC，滚动三月均）', 'cols': [
            {'col': 'rpc_commodities_usd',       'zh': '大宗商品', 'unit': 'USD/contract', 'fmt': 'f2'},
            {'col': 'rpc_energy_usd',            'zh': '能源',     'unit': 'USD/contract', 'fmt': 'f2'},
            {'col': 'rpc_ag_metals_usd',         'zh': '农产品与金属', 'unit': 'USD/contract', 'fmt': 'f2'},
            {'col': 'rpc_financials_usd',        'zh': '金融',     'unit': 'USD/contract', 'fmt': 'f2'},
            {'col': 'rpc_rates_usd',             'zh': '利率',     'unit': 'USD/contract', 'fmt': 'f2'},
            {'col': 'rpc_other_financials_usd',  'zh': '股指与 FX', 'unit': 'USD/contract', 'fmt': 'f2'},
        ]},

        # ── 美股期权：adv_us_equity_options_industry_kcontracts 是**全行业分母**，
        #    全仓最值钱的几列之一 —— 有了它，NYSE 与 Cboe multilist、MIAX 才能同分母算份额。
        {'zh': 'NYSE 美股期权（Arca + American）', 'cols': [
            {'col': 'adv_us_equity_options_industry_kcontracts', 'zh': '全美股票/ETF 期权行业总量',
             'unit': 'k contracts/day', 'fmt': 'f0c'},
            {'col': 'adv_nyse_equity_options_kcontracts', 'zh': 'NYSE 两所合计',
             'unit': 'k contracts/day', 'fmt': 'f0c'},
            {'col': 'share_nyse_equity_options', 'zh': 'NYSE 份额（官方直接给）',
             'unit': '%', 'fmt': 'pct1', 'scale': 100},
            # 比率列。f2 不在 RATIO_FMT 里，靠 `col_is_ratio()` 第 ③ 级认出来
            # （classify → 'ratio'，且 unit `USD/contract` 是比率量纲）——
            # 所以 Exhibit 12 的金线画的是**差**，与同组上一列（份额，pct1）同口径；
            # 但两者的**单位不同**：份额的差是百分点（pp/bp），RPC 的差是
            # USD/contract（分子是钱）。2026-09 之前它走的是 (a/b−1)×100，
            # 详见上方「为什么 fmt 这么选」第 5 条。
            {'col': 'rpc_nyse_equity_options_usd', 'zh': 'NYSE 期权 RPC',
             'unit': 'USD/contract', 'fmt': 'f2'},
        ]},

        # ── 美股现货：本页最重要的一组。
        #    adv_tape{A,B,C}_consolidated_mnsh 是**全市场**合并成交量（不是 NYSE 自己的），
        #    是「场外化侵蚀」这条趋势唯一可跟踪的证据：四家自营撮合量合起来只占全美
        #    合并量的四成多，其余成交在暗池 / 内化商 / TRF。这个分母只有 ICE 披露。
        #    ⚠ 具体是哪个月、四家各占多少，由 `_venue_mix()` 在 import 期现找现算
        #    （判据是「四家都有值的最新一个月」）。这里**不再抄一份快照**：
        #    上一版把 2026-06 那次实测连同「最新一个月」这半句一起写死，
        #    等 2026-07 四家发齐，页面上那句自称的判据就当场变成假话。
        {'zh': 'NYSE 美股现货：本所量 vs 全市场分母', 'cols': [
            {'col': 'adv_nyse_us_cash_handled_mnsh', 'zh': 'NYSE Group handled ADV',
             'unit': 'mn shares/day', 'fmt': 'f0c'},
            {'col': 'share_nyse_us_cash_matched', 'zh': 'NYSE 全美 matched 份额',
             'unit': '%', 'fmt': 'pct1', 'scale': 100},
            # 同上：比率列配 f3，靠 unit `USD/100 shares` 走第 ③ 级（见第 5 条）。
            {'col': 'rpc_nyse_us_cash_usd_per100sh', 'zh': '现货 RPC（每 100 股）',
             'unit': 'USD/100 shares', 'fmt': 'f3'},
            {'col': 'adv_tapeA_consolidated_mnsh', 'zh': 'Tape A 全市场',
             'unit': 'mn shares/day', 'fmt': 'f0c'},
            {'col': 'adv_nyse_tapeA_matched_mnsh', 'zh': 'Tape A · NYSE matched',
             'unit': 'mn shares/day', 'fmt': 'f0c'},
            {'col': 'adv_nyse_tapeA_handled_mnsh', 'zh': 'Tape A · NYSE handled',
             'unit': 'mn shares/day', 'fmt': 'f0c'},
            {'col': 'share_nyse_tapeA_matched', 'zh': 'Tape A 份额',
             'unit': '%', 'fmt': 'pct1', 'scale': 100},
            {'col': 'adv_tapeB_consolidated_mnsh', 'zh': 'Tape B 全市场',
             'unit': 'mn shares/day', 'fmt': 'f0c'},
            {'col': 'adv_nyse_tapeB_matched_mnsh', 'zh': 'Tape B · NYSE matched',
             'unit': 'mn shares/day', 'fmt': 'f0c'},
            {'col': 'adv_nyse_tapeB_handled_mnsh', 'zh': 'Tape B · NYSE handled',
             'unit': 'mn shares/day', 'fmt': 'f0c'},
            {'col': 'share_nyse_tapeB_matched', 'zh': 'Tape B 份额',
             'unit': '%', 'fmt': 'pct1', 'scale': 100},
            {'col': 'adv_tapeC_consolidated_mnsh', 'zh': 'Tape C 全市场',
             'unit': 'mn shares/day', 'fmt': 'f0c'},
            {'col': 'adv_nyse_tapeC_matched_mnsh', 'zh': 'Tape C · NYSE matched',
             'unit': 'mn shares/day', 'fmt': 'f0c'},
            {'col': 'adv_nyse_tapeC_handled_mnsh', 'zh': 'Tape C · NYSE handled',
             'unit': 'mn shares/day', 'fmt': 'f0c'},
            {'col': 'share_nyse_tapeC_matched', 'zh': 'Tape C 份额',
             'unit': '%', 'fmt': 'pct1', 'scale': 100},
        ]},

        # ── CDS：ICE Clear Credit 当月清算名义总额，**当月总量不是日均**（表标题里没有 daily 字样）。
        #    2013-01 起，比其余列晚两年，但它每月与主表同时发布，所以不是慢腿。
        {'zh': 'CDS 清算名义额（ICE Clear Credit，当月总量）', 'cols': [
            {'col': 'cds_total_notional_usdbn',     'zh': '合计',   'unit': 'USD bn/month', 'fmt': 'f0c'},
            {'col': 'cds_client_notional_usdbn',    'zh': '客户盘', 'unit': 'USD bn/month', 'fmt': 'f0c'},
            {'col': 'cds_nonclient_notional_usdbn', 'zh': '非客户盘', 'unit': 'USD bn/month', 'fmt': 'f0c'},
        ]},
    ],

    # ICE 全表 55 列同一个 xlsx、同一天发布，没有任何一列比头条晚 ——
    # RPC 不滞后（这是与 Cboe 的关键差别），CDS 也不滞后。所以慢腿为空。
    'slow_cols': [],

    # 唯一一处会改变序列含义的口径断点。
    # ICE 2013-11 才完成 NYSE Euronext 收购，但原表 row 79 明写
    # "For comparison purposes, we include NYSE ADV, RPC and OI in all periods covered"
    # ⇒ 2011-01 ~ 2013-10 的 NYSE 现货与期权是**追溯并入的形式数**，
    #    那 34 个月讲的是被收购前 NYSE Euronext 的份额，不是 ICE 的。
    'breaks': [
        {'month': '2013-11', 'zh': 'NYSE Euronext 收购完成；此前 NYSE 各列为追溯并入的形式数'},
    ],

    # 📌 'decomp' 刻意留空：本表没有任何一条成交金额列，rpc_* 是费率不是价。
    # 完整理由与机器判据见 _NO_DECOMP_NOTE（它进了下面 notes 的第一条）。

    # ══ 水平值 + 次轴单月同比 ════════════════════════════════════════════════
    # 两条头条各一张。两条 level 列在 groups 里都落在多列同轴的图里
    # （能源/金融 ADV 那几组、以及 tape 那一大组），不是单桶 gs_bar
    # ⇒ 不与任何一张**单桶 gs_bar** 重复。
    # ⚠️ 但这两条正是**头条列**，头条各自自带一张 grouped_bars 的「：单月同比」——
    #   2026-09 改口径之后那两张的柱与这里两条的金线**逐点同源**（改口径前一张单月、
    #   一张滚动，各有各的用处）。底座 `ex_level_yoy` 的护栏只拦「level_yoy ∩ groups
    #   单列桶」，拦不到头条这条路；要不要合并成一张由页面所有者定。
    'level_yoy': [
        # 两条都是官方原表直接发的 ADV（当月日均）。次轴是**本列自己的单月同比**，
        # 所以本页那两套互不相同的交易日列（trading_days_commod / _rates /
        # _us_equities）一条都用不上 —— 从前要用它们，是因为滚动 12 个月合计非得先把
        # 日均还原成当月合计不可，而总 ADV 横跨商品与金融两侧，哪一套日历都不能代表它。
        {'zh': 'ICE 衍生品成交量',
         'level': {'col': 'adv_futures_options_kcontracts', 'zh': '衍生品总 ADV',
                   'unit': 'k contracts/day', 'fmt': 'f0c'},
         'note': _NOTE_TTM_FO},

        {'zh': 'NYSE 美股现货成交股数',
         'level': {'col': 'adv_nyse_us_cash_handled_mnsh', 'zh': 'NYSE handled ADV',
                   'unit': 'mn shares/day', 'fmt': 'f0c'},
         'note': _NOTE_TTM_CASH},
    ],

    # ══ 名词释义：排在所有 exhibit 之前（CONTRACT §1）════════════════════════
    # 分工：brief 说「**这个月**这组读数怎么读」、每月重写；这里说「**这些词**是
    # 什么意思」、一年到头同一段 ⇒ 一个当月读数都不写。出现的数只有两类：
    # 单位换算常数（千张 = 1,000 张）与恒等式本身；实测量只有两个（分项之和与合计
    # 差多远、差在哪几个月），都复用 `_split_vs_total()` / `_split_exact_months()`
    # 在 import 期算出来的 `_SPLITMAX` / `_SPLITEQ`，不另抄一份会过期的快照。
    # 起点年月（`_M0` / `_MIAX0` / `_CDS0`）同理，一律现读。
    #
    # 选词只从本页**露过面**的字里选（图题 / 序列名 / 纵轴 / 汇总表行头 /
    # 核对表列头 / 图注 / 页尾说明），且限于「不看定义就会读错」的那些：
    #   · 缩写与行话：ADV、月末净 OI、RPC、Tape A/B/C、CDS 名义额、
    #     TTF（在页上只露过一次脸 —— 汇总表行头「天然气（含 TTF）」—— 但纯缩写，
    #     不知道它是荷兰枢纽的人会把那一行读成一条纯美国天然气序列）；
    #   · 单位陷阱：千张（跨家差 1,000 倍）；
    #   · 官方标签与实际口径不一致：FX 与 USDX（行名写 & CREDIT，其实不含信用）、
    #     期权行业总量（ICE 从未书面定义过，别当官方口径引）；
    #   · 同一个词在本页有特定外延：衍生品总 ADV（不含单股、也不是分项相加）、
    #     单股（已被官方剔出合计）、份额（三组各有各的分母，都是全市场不是池内）、
    #     handled / matched（份额只能用后者）；
    #   · 口径断点的实质：追溯并入的形式数（改的是外延，不只是名字）。
    # 不收 m/m、y/y、3Y %ile、pp/bp —— 那是全站通用的读图约定，summary.note 与
    # 页尾「同比口径」已经逐条讲过，释义板再讲一遍就是两处各写一份、迟早不同步。
    #
    # 每条的口径都对着页尾 notes、图注、series/ 现算与 fetch/ 的口径坑核过，
    # 冲突以既有 notes / fetch 口径坑为准。⚠ 这一行不是一句自述而是一条纪律：
    # 上一版栽在它上面两次 —— 一次把 fetch 口径坑 6 明令禁写的错因果（「分项与合计
    # 各用各的交易日归一」）当定义写进了两条释义，一次把注 [18] 上方已经删掉的
    # 「本仓唯一」全称断言原样搬了回来。改这一段之前先读那两处。
    'glossary': [
        ('ADV',
         '日均成交量（average daily volume）：<code>当月合计 ÷ 当月交易日数</code>。'
         '本页凡是标着 ADV 的列都是<b>官方自己算好的日均</b>，本仓不做任何还原、也不再平均'
         '（CDS 那一组不是 ADV，见下）。'
         # ⚠ 这里原本接着写「分项与合计各用各的那一套归一 —— 这是页尾『分项之和 ≠
         #   合计』那条的成因」。那个因果 fetch/ice.py 的口径坑 6 已经证伪过（偏差最大的
         #   2011-08 / 2011-10 / 2012-08 里两列交易日恰恰相等），本机现算也是：两列相等
         #   的 69 个月里有 25 个月不平，两列不等的 118 个月里反而有 77 个月精确相等。
         #   ⇒ 只留「两套交易日各归一各的」这个可核的事实，不再宣称它解释了什么。
         '⚠️ ICE 有<b>不止一套交易日</b>（<code>trading_days_commod</code>、'
         '<code>trading_days_rates</code>，美股现货另有一套），各条 ADV <b>各归一各的</b>'
         ' —— <b>不要</b>随手挑一套乘回去把日均还原成当月合计，横跨两侧的列没有哪一套'
         '日历能代表它。'),

        ('千张（k contracts）',
         '官方原表的单位（原文 "contracts in 000s"）：本页衍生品 ADV 与 OI 的 1 '
         '就是 <b>1,000 张</b>合约。⚠️ 跨家比较前必须先统一 —— '
         '<code>series/cme.csv</code> 的 <code>oi_*_contracts</code> 是裸张数，'
         '两者差 1,000 倍。另外月度值<b>在官方原表里就已四舍五入到整千张 / 整百万股</b>，'
         '所以本页计数类一律按 0 位小数显示；小基数行（环境权益、FX 与 USDX）的同比'
         '因此会与官方新闻稿略有出入，那是官方自己取整造成的（见页尾）。'),

        ('衍生品总 ADV',
         '页顶头条那一列，官方原表行名 <b>TOTAL FUTURES & OPTIONS</b>，'
         '横跨大宗商品与金融两侧、<b>不含单股</b>。汇总表「金融衍生品 ADV」组里的'
         '「期货与期权总计」<b>是同一列</b>，不是第二个读数。'
         # ⚠ 原文在这里给了「合计按总量÷总交易日归一、而两套交易日不同」这个因果。
         #   fetch/ice.py 口径坑 6 白纸黑字写着它已被证伪，原话是「写一个错的因果，
         #   下一个人会去『修』一个修不好的东西」。⇒ 只留现算得出的事实，成因写「官方
         #   未说明」。（页尾注与 Ex25 图注里还留着同一句错因果，那两处不在本次范围内。）
         '⚠️ 它<b>不是</b>「大宗商品合计 + 金融合计」相加得来的：'
         + ((f'{_SPLITN} 个月里 {_SPLITEQ} 个月两边精确相等，其余月份有 '
             f'0~{_SPLITMAX:.2f}% 的相对差（现算）。')
            if (_SPLITMAX is not None and _SPLITEQ is not None) else
            '多数月份两边精确相等，少数月份差一层（见页尾实测）。')
         + '<b>官方从未说明原因</b>，本仓也未查明 —— '
         '<b>不要当恒等式、也不要当校验条件</b>用。'),

        # TTF 在全页只露过一次脸：汇总表「能源衍生品 ADV」组的行头「天然气（含 TTF）」。
        # 它是纯缩写，且正好是「不看定义就会读错」的那一类 —— 不知道它是荷兰枢纽的人，
        # 会把这一行当成一条纯美国（Henry Hub）天然气序列。
        # 口径出处：docs/verify/ice.md:89（adv_natgas_kcontracts = 北美 + NGX + 英国 +
        # 欧洲（含 TTF））与 fetch/ice.py 口径坑 17（整份工作簿逐格扫过，TTF 没有独立行，
        # 被折进 Nat Gas；官方新闻稿点评的 TTF 是合约级口径，与本表的产品组行同名不同物）。
        ('TTF',
         'Title Transfer Facility，荷兰的天然气交易枢纽，是 ICE Futures Europe 那条'
         '<b>欧洲</b>气基准。⚠️ 本页汇总表里的「天然气（含 TTF）」<b>不是</b>一条纯美国'
         '（Henry Hub）序列 —— 官方把北美、NGX、英国与欧洲（TTF 就在其中）四块'
         '<b>合并成一行</b>披露，<b>不拆</b>。⇒ 本表给不出「ICE 的 TTF 成交量」；'
         '官方新闻稿里单独点评过的 TTF 同比是<b>合约级</b>口径，与这一行同名不同物，'
         '拿它去反推一个 TTF 绝对量是在编数。'),

        ('单股',
         '<code>adv_single_stock_kcontracts</code>，ICE Futures Europe 的单股期货 / 期权。'
         '官方<b>已把它从 TOTAL FINANCIALS 剔除</b>（理由是收入封顶、与量无相关性），'
         '所以本页的「金融合计（不含单股）」与「衍生品总 ADV」<b>都不含它</b>。'
         '它只能单独看，<b>不要并进任何合计或竞争池</b>。'),

        ('FX 与 USDX',
         '<code>adv_fx_credit_kcontracts</code>。官方行标签写的是 "TOTAL FX & CREDIT"，'
         '但<b>口径是外汇 + 美元指数（USDX），不含信用</b> —— 依据是表内脚注原文只提 '
         'U.S. Dollar Index 与 foreign exchange，并与官方合约级明细文件对上过（见页尾）。'
         'ICE 的信用业务在本页是<b>另一组</b>（CDS 清算名义额），两者既不同口径也不同单位。'),

        ('月末净 OI',
         '未平仓合约（open interest），月末<b>净</b>口径（表内注明按行业惯例报 net OI）。'
         '它是<b>存量</b> —— 某一天的截面，不是当月发生的量，'
         '<b>不能与本页的日均 / 当月合计相加</b>；跨币种换算时流量配月均汇率、'
         '存量配月末汇率。单位同样是千张。⚠️ 官方<b>没有 TOTAL OI 行</b>，'
         '新闻稿里的 "Total OI" 是「大宗商品 + 金融」两条自己加出来的。'),

        ('RPC（每张收入）',
         'revenue per contract。官方定义（表内脚注 1）= <code>交易收入 ÷ 合约量</code>，'
         '而且是<b>滚动三月均</b> —— 所以<b>不能拿它乘单月量当单月收入</b>。'
         '⚠️ 它是<b>费率不是成交价</b>：分子是 ICE 向会员收的费，'
         '不是市场撮合出来的价格，本页因此不画量价分解（见页尾第一条）。'
         '与 Cboe 不同，ICE 的 RPC <b>不滞后</b>一个月，两家并排画时 ICE 那条每月都会'
         '多伸出一格。现货那一条的单位是 USD/100 股，不是 USD/张。'),

        ('handled / matched',
         'handled = 本所撮合 + <b>路由到别家</b>交易所成交的量；'
         'matched = <b>只算本所自己撮合</b>的那部分。'
         '⇒ 市场<b>份额只能用 matched 算</b>，拿 handled 当分子等于把别家的成交'
         '记在自己名下。本页头条「NYSE 美股现货 ADV（handled）」量的是 NYSE Group 的'
         '<b>体量</b>，而所有份额列（NYSE 全美 matched 份额、三条 Tape 份额）'
         '都是 matched 口径，<b>两者不可互相换算</b>。'),

        ('Tape A / B / C',
         '美股合并行情的三条带，按<b>上市地</b>划分：Tape A = NYSE 上市，'
         'Tape B = NYSE Arca / American 与区域所上市，Tape C = Nasdaq 上市。'
         # ⚠ 原文这里写的是「这个分母只有 ICE 按月披露」。它与本页自己的页尾注打架：
         #   注 [18] 点名 series/miax.csv 的行业 ADV 是同类分母，注 [19] 更说两条数值
         #   几乎逐位相同 —— MIAX 那条同样按月披露。这正是 [18] 上方那段注释警告过的
         #   「跨页全称断言」，被删掉的那半句不能从释义板搬回来。
         #   ⇒ 换成两条都在本仓、都能现读的事实：起点谁更早，以及「按 tape 拆」这一层。
         '每条带本页给三列：<b>「全市场」是全美合并成交量</b>（所有成交场所之和，'
         '<b>不是</b> NYSE 自己的量）'
         + ((f'。同口径的分母本仓另有一条（<code>series/miax.csv</code> 的行业 ADV，'
             f'两家独立申报、数值几乎逐位相同，见页尾），但它自 {_MIAX0} 才起，'
             f'本页这三列回溯到 {_M0}；')
            if (_M0 and _MIAX0) else '。同口径的分母本仓另有一条（miax 的行业 ADV），')
         + '且 miax 那条只有一个全市场合计，<b>按 tape 拆开</b>的是 ICE 这三列。'
         '另两列是 NYSE 在该带的 matched 与 handled。'),

        ('份额（share_*）',
         '本页五条份额列在官方原表里是 <b>0–1 的小数</b>（0.191 = 19.1%），'
         '页面统一 ×100 按百分数显示（<code>series/miax.csv</code> 存的却是百分数，'
         # ⚠ 原文把三条 Tape 份额与「NYSE 全美 matched 份额」并成一组，说分母都是
         #   「全美合并成交量」。三条 Tape 份额的分母其实是**该带自己**的合并量：
         #   现算 2026-07，share_nyse_tapeA_matched = 0.291 = 1,534 ÷ 5,267（Tape A 自己
         #   的合并量），而 1,534 ÷ 17,437（三带合计）只有 0.088 —— 按字面读会把
         #   Tape A 份额算错三倍多。⇒ 三组分母分开写。
         '跨页取数别弄混）。<b>分母各不相同</b>，三组各是各的：'
         '三条 <b>Tape 份额</b>的分母是<b>该带自己</b>的全市场合并量'
         '（该带 matched ÷ 该带 consolidated），<b>不是</b>三条带的合计；'
         '<b>NYSE 全美 matched 份额</b>才是三带之和除三带之和'
         '（三带 matched 之和 ÷ 三带合并量之和）；'
         '<b>NYSE 份额（官方直接给）</b>的分母是全美股票/ETF 期权行业总量。'
         '三者都是<b>全市场</b>分母，<b>不是</b>「本页出现的这几家」池内份额。'),

        ('期权行业总量',
         '<code>adv_us_equity_options_industry_kcontracts</code>：'
         '全美股票 / ETF 期权的行业合计，<b>不含指数期权</b>，'
         '是「NYSE 份额（官方直接给）」的分母。⚠️ 这个口径是与 Cboe multilist 及 '
         'ICE 10-K 交叉验证出来的 —— <b>工作簿里这一行没有任何脚注、'
         'ICE 从未书面定义过</b>，不要当官方定义引用。'),

        ('CDS 清算名义额',
         'ICE Clear Credit 当月清算的 CDS <b>名义总额</b>（gross notional，单边计），'
         '单位十亿美元。⚠️ 是<b>当月总量，不是日均</b>（原表标题里没有 daily 字样）'
         '—— 与本页其余 ADV 列<b>不是同一种口径</b>，不要顺着读成「每天多少」。'
         '「合计 = 客户盘 + 非客户盘」（官方原表行名 CLIENT / NON-CLIENT），'
         '入库时逐月核过。'
         + ((f'三列自 {_CDS0} 起，早于该月的空格是官方就没有，不是漏抓。')
            if _CDS0 else '三列起步晚于全表首月，早期的空格是官方就没有，不是漏抓。')),

        ('追溯并入的形式数',
         'ICE 在 2013-11 才完成 NYSE Euronext 收购，但官方原表把 NYSE 的 ADV / RPC / OI '
         '<b>追溯并入了此前的每一个月</b>（原表注：for comparison purposes）。'
         '⇒ 红色竖虚线<b>左边</b>那一段里的 NYSE 各列，讲的是被收购前 NYSE Euronext 的量，'
         '<b>不是 ICE 的</b>，与线右边不可比。这是本页唯一一处口径断点；'
         '热力矩阵没有连续横轴、画不出这条线，读它的同比要自己扣掉这一层。'),
    ],

    'notes': [
        _NO_DECOMP_NOTE,

        '数据源：ICE 官网 IR 的 Monthly Statistics Tracking 单一 xlsx（4 个 sheet'
        + ((f'，{_M0} 起 {_NMONTHS} 个月') if _NMONTHS else '')
        + '），指针由 ir.theice.com 的 ContentAsset JSON feed 给出。'
        + ((f'全部 {_NCOLS} 列取自同一文件、同一发布日。')
           if _NCOLS else '全部数据列取自同一文件、同一发布日。'),

        '<b>衍生品 ADV 单位是千张（官方原表 "contracts in 000s"）；OI 单位同样是千张</b> —— '
        '与 series/cme.csv 的 oi_*_contracts（裸张数）差 1000 倍。跨家对比时必须先统一。',

        '<b>月度值在官方原表里就已四舍五入到整千张 / 整百万股</b>，'
        + ((f'非整数的只有 RPC 与份额这 {len(_NONINT_COLS)} 列'
            f'（全表 {_NONINT_CELLS:,} 个非整数格全落在它们身上 —— 名单现扫，'
            f'扫出 <code>rpc_*</code> / <code>share_*</code> 之外的列直接停机）。')
           if _NONINT_COLS else '非整数的只有 RPC 与份额那几列。')
        + '所以本页所有计数类一律按 0 位小数显示；小基数行（环境权益、FX/USDX）的同比会与官方新闻稿差 1–2pp，'
          '这是官方自己的取整造成的，不是解析错误。',

        '<b>分项之和 ≠ 合计，不要当恒等式。</b>'
        + ((f'TOTAL ENERGY = 六子项之和只在 {_ENEX}/{_ENN} 个月精确成立'
            f'（±2 内 {_ENNEAR}/{_ENN}）；') if _ENN else 'TOTAL ENERGY = 六子项之和常常差几张；')
        + ((f'TOTAL FINANCIALS = 四子项之和只在 {_FIEX}/{_FIN} 个月精确成立。')
           if _FIN else 'TOTAL FINANCIALS = 四子项之和同理。')
        + ('另外 adv_commodities + adv_financials 与 adv_futures_options 有'
           + ((f' 0~{_SPLITMAX:.2f}% ') if _SPLITMAX is not None else '一层')
           + '的系统性差 —— ')
        + ((f'合计用「总量÷总交易日」归一，而商品与利率两条交易日在 {_TDN} 个月里有 '
            f'{_TDNE} 个月不相等。')
           if _TDN else '合计用「总量÷总交易日」归一，而商品与利率两条交易日常常不相等。'),

        '<b>官方没有 TOTAL OI 行。</b>新闻稿里的 "Total OI" 是 oi_commodities + oi_financials 自己加出来的'
        '（已用 2026-06 / 2026-07 两期新闻稿反算验证）。OI 是月末净未平仓（net OI）。',

        '<b>RPC 是滚动三月均，不能与单月量相乘当单月收入。</b>官方定义（表内脚注 1）= 交易收入 ÷ 合约量。'
        '与 Cboe 不同，ICE 的 RPC 不滞后一个月，所以任何 ICE vs Cboe 的 RPC 并排图，'
        'ICE 那条线每个月都会比 Cboe 多伸出一格，需要在绘图层截齐。',

        '<b>share_* 五列在官方原表里是 0–1 的小数比率</b>（0.191 = 19.1%），'
        '本页统一乘 100 按百分数显示。这一点用算术核过而不是照抄文档：'
        'share ÷（matched ÷ consolidated）的中位比值'
        + ((f' = {_SHMED:.3f}（{_SHN} 个可比月现算；若源表存的是百分数，该比值会是 100）。')
           if _SHMED is not None else '接近 1（若源表存的是百分数，该比值会是 100）。')
        + '注意 series/miax.csv 的 share_*_pct 存的是百分数，两家形态相反，跨页取数时别弄混。',

        '<b>adv_tapeA/B/C_consolidated_mnsh 是全美合并成交量，不是 NYSE 自己的量</b> —— '
        # ⚠ 原文写的是「这是本仓**唯一**一个由交易所自己披露、且回溯到 2011-01 的现货
        #   行业分母」。「本仓唯一」是跨页的全称断言，而同一页下面那条注自己就点了名：
        #   MIAX 也披露一条行业 ADV。救它的只有「回溯到 …」这半个限定，而那半个限定
        #   没有任何检查 —— MIAX 哪天被回补到 2011 年，这句话就假了，且不会有人知道。
        #   ⇒ 改成拿两条**都在本仓、都能现读**的起点直接比，比出来的话不需要维护。
        + ((f'同类分母本仓另有一条（<code>series/miax.csv</code> 的行业 ADV，'
            f'见下一条注），但它自 {_MIAX0} 才起；本页这三列回溯到 {_M0}，'
            f'两个起点都是现读的。')
           if (_M0 and _MIAX0) else
           (f'这是本仓回溯得最深的一条现货行业分母（自 {_M0} 起，现读）。'
            if _M0 else '这是一条由交易所自己披露的现货行业分母。'))
        + ((f'本机实测 {_MIX["month"]}（四家份额都有值的最新一个月，逐月现找）：'
            f'三个 tape 合并 {_MIX["total"]:,.0f} 百万股/日，'
            f'NYSE matched {_MIX["nyse"]:,.0f}（{_MIX["nyse_pct"]:.1f}%）、'
            f'Cboe {_MIX["cboe"]:,.0f}（{_MIX["cboe_pct"]:.1f}%）、'
            f'Nasdaq 三盘口 {_MIX["ndaq_pct"]:.1f}%、'
            f'MIAX Pearl {_MIX["miax"]:,.0f}（{_MIX["miax_pct"]:.1f}%），'
            f'<b>四家合计 {_MIX["four_pct"]:.2f}%，其余 {_MIX["rest_pct"]:.2f}% '
            f'成交在暗池 / 内化商 / TRF</b>。')
           if _MIX else
           '四家自营撮合量合起来只占全美合并量的四成多，其余成交在暗池 / 内化商 / TRF'
           '（本次未能从同仓的 cboe / ndaq / miax 序列复算具体比例）。')
        + '「场外化侵蚀」这条趋势只能靠这几列跟踪。',

        '<b>ICE 的三 tape 合并量与 MIAX 自己披露的行业 ADV 是两家独立申报、数值几乎逐位相同的两条线</b>'
        + (('：实测 ' + '、'.join('%s = %s vs %s' % (m, format(a, ',.0f'), format(b, ',.0f'))
                                 for m, a, b in _XCHK) + '。')
           if _XCHK else '（本次未能复算具体月份）。')
        + '这既是两边解析正确性的交叉证据，也意味着横截面页上这两列是同一个分母，不要当成两个口径并列。',

        '<b>matched ≠ handled。</b>handled 含路由到别的交易所成交的量，跨家份额一律用 matched。'
        '官方没有 A+B+C matched 的合计行，只给了 share_nyse_us_cash_matched'
        + ((f'（与自算一致：{_SHN} 个可比月里最大差 {_ceil_to(_SHMAXPP, 2):.2f}pp —— '
            f'现算，且上界向上取整，印出来的数永远含得住实测值）。')
           if _SHMAXPP is not None else '（与自算一致）。'),

        '<b>adv_us_equity_options_industry_kcontracts 是全美股票/ETF 期权行业总量，'
        '经与 Cboe multilist 及 ICE 10-K 交叉验证与「不含指数期权」的口径一致</b> —— '
        '但工作簿里这一行没有任何脚注，ICE 从未书面定义过，不要在页面上写成官方定义。',

        '<b>adv_fx_credit_kcontracts 的行标签写着 "TOTAL FX & CREDIT"，但口径是 FX + 美元指数，不含信用。</b>'
        '依据：表内脚注 (12) 原文只提 U.S. Dollar Index 与 foreign exchange；'
        '2015-2021 官方合约级明细文件里对应行 Total FX & Other 与本列 2019-06 精确相符（38,947 张 = 39 千张）。',

        '<b>adv_single_stock_kcontracts 已被官方从 TOTAL FINANCIALS 剔除</b>'
        '（理由是收入封顶、与量无相关性），只能单独看，不要并入任何合计或竞争池。',

        '2011-01 起的历史里还有三处官方追溯重刷，已体现在当前文件中（本仓一次性全量摄入，不受影响）：'
        'NGX 的量与收入追溯并入 2011 年起的 Other Oil / 天然气 / 电力 / 能源与商品合计；'
        '2013 年起的电力 ADV、能源 RPC、能源 OI 按新的电力量折算法重算；'
        'Russell 合约 2016-12 规格减半后量、OI、RPC 全部追溯调整。'
        '<b>后果是本仓 CSV 与 ICE 历年季报 / 10-K 原文里的数字可能对不上</b> —— 以当前文件为准。',

        'CDS 三列'
        + ((f'自 {_CDS0} 起（比全表首月 {_M0} 晚 {_CDSLAG_ZH}；两个月份都现算，'
            f'三列首月对不上就停机）') if _CDS0 else '起步晚于全表首月')
        + '，是当月清算名义总额（单边计），不是日均。'
        '历史上出过一次实质重述：2026-06 那期的 2026-01 Non-Client = 291（不平 99），'
        '2026-07 那期改成 391 —— 这是跨 vintage 唯一一处实质改动。',

        '交易日有两列（trading_days_commod / trading_days_rates'
        + ((f'，{_TDN} 个月里只有 {_TDEQ} 个月相同') if _TDN else '，两列常常不等')
        + '），本页所有序列已是官方算好的 ADV，因此不单独出图；'
          '两列的差异是上面「分项之和 ≠ 合计」的成因之一。',
    ],
}
