# -*- coding: utf-8 -*-
"""MIAX（Miami International Holdings，NYSE: MIAX）单公司页配置。

口径以 docs/verify/verify_miax.md（复核稿，判定 B）为准。侦察稿被复核推翻的地方，
本文件按复核稿写：
  · 「MIAX 四所指数期权恒为 0」是错的。复核稿说的是「2019-06~2023」，本机对 CSV 实测更精确：
    非零区间是 <b>2019-02 ~ 2024-12（57 个月非零）</b>，峰值 2019-12 = 10.208 千张/日，
    2025-01 起才一路为 0。CSV 里 adv_index_options_api_kcontracts 的实测区间是 0 ~ 10.21 千张/日，
    所以这一列要进页面，且任何地方都不许写 assert == 0。
  · 「重述只发生在 industry_adv_equities 一列」是错的 —— rpc_futures_ag_usd 也被改过
    （2026-04 从 1.981 改到 1.977）。

列名全部对着 `head -1 series/miax.csv` 逐字核过（25 列，136 个月，2015-04..2026-07）。

本页最容易被误读的一件事：<b>成交量与 RPC 的历史长度差 10 年</b>。
API 口径的四所 ADV 回到 2015-04（136 个月），而 IR 月报 PDF 口径的一切（含全部 RPC）
只有 2025-01 起 19 个月。这不是同一段历史，横轴必须分开读。

━━ 量价分解（decomp / ttm_yoy）━━
本页有**两对**成对的股票列，都在 indsum API 段、都覆盖 2020-12..2026-07 共 68 个月零断档：
  Pearl 自家 ：adnv_equities_api_usdbn          ÷ adv_equities_api_mnshares
  全美行业   ：industry_adnv_equities_api_usdbn ÷ industry_adv_equities_api_mnshares
两对都同源（同一次 indsum 请求的同一个 PEARLEQ / 交易所行）、同粒度（都是当月**日均**）、
同覆盖（含 TRF 场外），相除得到的是「成交量加权平均成交价」，没有口径楔子。
Pearl 在所成交 ⊂ 全美含 TRF ⇒ **子集关系成立**，这是 SINGLE_SPEC §1.3.1 要求 spec 作者
自己负责核实、底座验证不了的那一条。所以本页走**三分法**（bench_value / bench_qty）：
行业整体增长 / Pearl 的份额变化 / Pearl 的品种结构（均价相对行业）。
核查全过程与全部实测数字见文件末尾的「量价分解：口径核查实测日志」注释块。

⚠ 本家做量价分解时最容易出错的三件事：
  1. **别用 trading_days_options 当 weight_col。**它只有 2025-01 起 19 个月，
     而 decomp 要的是 2021..2025 五个完整年；weight_col 一旦缺月，Page._years 会把
     整年丢掉，实测只剩 1 个完整年、图直接不出（底座打印「完整年度只有 1 个」）。
     ⇒ 本页 granularity='daily_avg' 且**不给** weight_col / *_total_col，
     底座会在图注里印一段 ⚠️ 说明等权相加带偏差 —— 那句话是真的，别去掩盖它。
  2. **别用点对点端点。**2026-07 是本序列的低位月（Pearl ADV 在 68 个月里排第 21 低），
     点对点会把结论说反 —— 详见末尾注释块 §E4 的实测对照。
  3. **year_start_month=1 / year_label='start'。**MIAX 的财年就是日历年（10-K 截至 12-31）。
     不要为了让末桶落在 2026-07 改成 8 月制：柱数一样是 4 根，却会印出一个 MIAX
     根本不用的 FY 标签。日历年下 year_label 只能是 'start'（底座硬失败挡 'end'）。
"""

# ── 两个源、两种节奏 ──────────────────────────────────────────────────────
# API（www.miaxglobal.com/indsum，10 列，2015-04 起）：月末次日即可取，无 UA 校验。
# PDF（ir.miaxglobal.com 的 Volume & RPC Report，14 列，2025-01 起）：
#     次月第 3~5 个工作日发布，是与 10-K 对得上的权威值（四项误差 ≤0.11%）。
# 头条同时取一条 API 列（管历史长度）与一条 PDF 列（管发布门槛），
# 共同最新月自然落在 PDF 那一期上 —— 与仓库 roster 对这家的发布日预期一致。

# ══════════════════════════════════════════════════════════════════════════════
# 图注要报的数，**一个都不写死**：全部在 import 期从 series/miax.csv 现算，
# 再用 f-string 拼进 _DECOMP_NOTE / _TTM_NOTE（照 build/specs/jpx.py 的 _wedges()）。
# 任何一步失败都返回 None 并让 note 退回不含数字的定性版本 ——
# 缺文件不许在 import 期抛异常，否则 monthly_run 会因为一张页的配置炸掉整批。
# ══════════════════════════════════════════════════════════════════════════════
import csv
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_CSV = os.path.join(_ROOT, 'series', 'miax.csv')

# 量价分解用到的四列（两对）。顺序 = 金额、数量、行业金额、行业数量。
_EQ4 = ('adnv_equities_api_usdbn', 'adv_equities_api_mnshares',
        'industry_adnv_equities_api_usdbn', 'industry_adv_equities_api_mnshares')

# PDF 段的行业股数 ADV —— 与 _EQ4[3] 是**两个源的同一个概念**，拿来互相对账。
# 它正是官方承认出过数据处理错误并重述过的那一列（fetch/miax.py 口径坑 7）。
_PDF_IND_Q = 'industry_adv_equities_mnshares'

# 两源对账的「一致」阈值。取 0.5% 不是随手定的：实测一致的那批月份最大偏差与
# 对不上的那批最小偏差之间有一个数量级的空档（图注会把两侧都报出来，读者自己看得见）。
_AGREE_TOL = 0.5


def _rows():
    try:
        with open(_CSV, encoding='utf-8') as fh:
            return list(csv.DictReader(fh))
    except OSError:
        return []


def _num(r, col):
    """CSV 里一格 → float，空格子/非数返回 None（不拿 0 冒充缺失）。"""
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


def _eq_cover():
    """四列的覆盖体检 → (月数, 首月, 末月, 四列有值月份是否**完全**同一批)。

    「同一批」这件事必须验而不是假定：分解的分子分母只要有一列多出/少掉一个月，
    年度桶就会缺月被 Page._years 整年丢掉，而图上只会少一根柱、看不出原因。
    """
    sets = []
    for c in _EQ4:
        sets.append({r['month'] for r in _rows() if _num(r, c) is not None})
    if not sets or not sets[0]:
        return None, None, None, None
    same = all(s == sets[0] for s in sets)
    ms = sorted(set.intersection(*sets))
    return (len(ms), ms[0], ms[-1], same) if ms else (None, None, None, None)


def _ind_recon():
    """API 行业股数 ADV vs PDF 行业股数 ADV 的逐月对账 → 一个 dict，算不出返回 None。

    为什么非做不可：PDF 那一列是官方**承认报错并重述过**的列，而本页的行业分母走的是
    另一个源（API），两者在重叠窗口上对不对得上，是这条分母唯一可得的外部体检。
    年度影响也在这里现算：把重叠月的 API 值换成 PDF 值，看最近一个完整日历年的
    行业股数合计与同比各动多少 —— 「月频差 1.7% 但年度差不到 20bp」这句话要有数支撑。
    """
    api_q, pdf_q, pearl_q = {}, {}, {}
    for r in _rows():
        m = r.get('month')
        a, p, q = _num(r, _EQ4[3]), _num(r, _PDF_IND_Q), _num(r, _EQ4[1])
        if a is not None:
            api_q[m] = a
        if p is not None:
            pdf_q[m] = p
        if q is not None:
            pearl_q[m] = q
    ov = sorted(set(api_q) & set(pdf_q))
    if not ov:
        return None
    dev = [(m, (api_q[m] / pdf_q[m] - 1.0) * 100.0) for m in ov if pdf_q[m]]
    bad = [(m, d) for m, d in dev if abs(d) > _AGREE_TOL]
    ok = [abs(d) for m, d in dev if abs(d) <= _AGREE_TOL]
    out = {'n': len(dev), 'n_ok': len(ok), 'max_ok': max(ok) if ok else None, 'bad': bad}
    # 年度影响：最近一个「PDF 覆盖满 12 个月、且上一年 API 也满 12 个月」的日历年。
    yrs = sorted({int(m[:4]) for m in api_q})
    for y in reversed(yrs):
        cur = ['%d-%02d' % (y, k) for k in range(1, 13)]
        prv = ['%d-%02d' % (y - 1, k) for k in range(1, 13)]
        if not all(m in pdf_q for m in cur):
            continue
        if not all(m in api_q for m in cur + prv):
            continue
        mix = {m: pdf_q.get(m, api_q[m]) for m in api_q}
        a1, b1 = sum(api_q[m] for m in cur), sum(mix[m] for m in cur)
        a0, b0 = sum(api_q[m] for m in prv), sum(mix[m] for m in prv)
        out['year'] = y
        out['bp'] = (b1 / a1 - 1.0) * 1e4
        out['g_pp'] = ((a1 / a0) - (b1 / b0)) * 100.0
        if all(m in pearl_q for m in cur + prv):
            p1, p0 = sum(pearl_q[m] for m in cur), sum(pearl_q[m] for m in prv)
            out['s_pp'] = (((p1 / a1) / (p0 / a0)) - ((p1 / b1) / (p0 / b0))) * 100.0
        break
    return out


def _px_rel():
    """Pearl 均价 ÷ 行业均价 → (月数, 溢价月数, 最后一个溢价月, min, max, 末月值)。

    这个数是三分法第三块（品种结构）的水平值。**它不是一个静止的折价** ——
    序列早期 Pearl 均价高于行业，后来才转为折价。只报中位数会把这次翻转整个盖掉。
    """
    seq = []
    for r in _rows():
        v, q = _num(r, _EQ4[0]), _num(r, _EQ4[1])
        iv, iq = _num(r, _EQ4[2]), _num(r, _EQ4[3])
        if None in (v, q, iv, iq) or not (q and iq and iv):
            continue
        seq.append((r['month'], (v / q) / (iv / iq)))
    if not seq:
        return (None,) * 6
    prem = [m for m, x in seq if x > 1.0]
    xs = [x for _, x in seq]
    return len(seq), len(prem), (prem[-1] if prem else None), min(xs), max(xs), xs[-1]


def _tdays():
    """交易日数列的覆盖与离散度 → (有值月数, min, max, 两端相差%, 四列窗口内缺权重的月数)。

    本页股票段没有自己的交易日列；期权段的 trading_days_options 覆盖不到分解窗口，
    填进 weight_col 会让 Page._years 整年丢掉（实测只剩 1 个完整年，图直接不出）。
    所以这几个数的用途不是「用它加权」，而是**量出等权相加那一步在赌多大的离散度**。
    """
    d = {r['month']: _num(r, 'trading_days_options') for r in _rows()}
    v = [x for x in d.values() if x]
    n, first, last, _ = _eq_cover()
    if not v or n is None:
        return (None,) * 5
    miss = sum(1 for r in _rows()
               if first <= r['month'] <= last and not d.get(r['month']))
    return len(v), min(v), max(v), (max(v) / min(v) - 1.0) * 100.0, miss


_N4, _M0, _M1, _SAME4 = _eq_cover()
_REC = _ind_recon()
_PN, _PPREM, _PLAST, _PMIN, _PMAX, _PCUR = _px_rel()
_TDN, _TDMIN, _TDMAX, _TDSPR, _TDMISS = _tdays()


def _fmt_bad(rec):
    """对不上的那几个月 → 「2025-06 −1.17%、…」。没有就返回空串。

    负号用真减号 U+2212 而不是 ASCII 连字符，但**只换数值那一个符号** ——
    整串 replace 会把月份里的 `2025-06` 也换成 `2025−06`。
    """
    if not rec or not rec.get('bad'):
        return ''
    return '、'.join(f'{m} {"−" if d < 0 else "+"}{abs(d):.2f}%' for m, d in rec['bad'])


# ── 图 A（量价分解，三分法）的口径交代 ────────────────────────────────────
# 底座已经讲了：恒等式、年度端点是 12 个月合计、为什么画对数不画算术、
# 「均价不是指数收益率」、以及子集关系这条 caveat。这里**只补底座讲不了的**：
# 这四列凭什么算同口径、行业分母那条唯一的外部体检结果、以及品种结构块的水平值。
_DECOMP_NOTE = (
    '<b>四列同源、同粒度、同覆盖，所以相除没有口径楔子。</b>'
    '金额与数量出自 <code>miaxglobal.com/indsum</code> 的<b>同一次请求</b>'
    '（<code>sumType=volume</code> / <code>notional</code> 两个视图）：'
    'Pearl 两列取 <code>PEARLEQ (H)</code> 行，行业两列取<b>交易所行</b>的 '
    '<code>TOTAL_MARKET_*</code>（TOTAL <b>行</b>自己的同名字段是个按行数重复累加的'
    '陷阱值，取错会让行业分母整整大一个量级，fetch 侧已避开）。'
    + (f'四列有值的月份是<b>完全同一批</b>：{_M0}…{_M1} 共 {_N4} 个月、零断档 —— '
       f'这一条是验过的，不是假定：分子分母只要差一个月，年度桶就会被整年丢掉，'
       f'而图上只会少一根柱、看不出原因。'
       if _SAME4 else '⚠️ 四列的有值月份**不是同一批**，年度桶可能被整年丢掉，请先查 CSV。')

    + '<b>行业分母那条唯一的外部体检。</b>本页的行业分母走 API 源，而 IR 月报 PDF 段'
      '另有一条同概念的行业股数 ADV（<code>' + _PDF_IND_Q + '</code>），'
      '两者在重叠窗口上可以逐月对账 —— 这一条尤其要做，因为 PDF 那一列正是官方'
      '<b>承认出过数据处理错误并重述过</b>的列。'
    + ((f'实测 {_REC["n"]} 个重叠月：{_REC["n_ok"]} 个对得上'
        + (f'（最大偏差仅 {_REC["max_ok"]:.2f}%）' if _REC.get('max_ok') is not None else '')
        + (f'，<b>{len(_REC["bad"])} 个对不上</b>：{_fmt_bad(_REC)}。'
           if _REC.get('bad') else '，全部对得上。'))
       if _REC else '（本次算不出对账结果，请查 CSV。）')
    + ((f'年度层面小得多：把重叠月换成 PDF 值重算，{_REC["year"]} 年的行业股数合计只动 '
        f'{_REC["bp"]:+.1f}bp、行业同比动 {abs(_REC["g_pp"]):.2f}pp'
        + (f'、Pearl 份额同比动 {abs(_REC["s_pp"]):.2f}pp' if 's_pp' in _REC else '')
        + '。<b>⇒ 本图（年度口径）的结论不受影响；但月频图上不要拿这一列讲 1% 级的故事。</b>')
       if _REC and 'year' in _REC else '')

    + '<b>金额两列没有第二个源可对，如实标为未独立验证。</b>'
      'PDF 段在 <code>series/miax.csv</code> 里<b>一个金额列都没有</b>'
      '（那边全是张数与股数），所以 <code>adnv_equities_api_usdbn</code> 与 '
      '<code>industry_adnv_equities_api_usdbn</code> 只有源侧的单点佐证，'
      '没有跨源逐月对账。这是本页分解链条里唯一没有独立交叉验证的一环。'

    + '<b>第三块「品种结构」的水平值。</b>它就是 Pearl 均价 ÷ 行业均价，'
      '市场涨跌对两条均价同向作用、相除之后基本抵消，剩下的是 Pearl 的成交品种'
      '相对全市场偏贵还是偏便宜。'
    + ((f'实测 {_PN} 个月：区间 {_PMIN:.2f}–{_PMAX:.2f}，最新 {_PCUR:.2f}。'
        + (f'<b>它不是一个静止的折价</b> —— 序列早期有 {_PPREM} 个月 Pearl 均价'
           f'反而<b>高于</b>行业（最后一个是 {_PLAST}），此后才转为折价并走深。'
           f'只看中位数会把这次翻转整个盖掉。' if _PPREM else ''))
       if _PN else '')
)

# ── 图 B（量的水平值 + 滚动同比）的口径交代 ──────────────────────────────
_TTM_NOTE = (
    '<b>本页股票段没有自己的交易日列</b>，所以滚动合计是把「日均」按月<b>等权</b>相加。'
    + (f'表里唯一的交易日列 <code>trading_days_options</code> 只覆盖 {_TDN} 个月，'
       f'本序列有 {_TDMISS} 个月拿不到权重；已覆盖的那些月实测每月 '
       f'{_TDMIN:.0f}–{_TDMAX:.0f} 个交易日、两端相差 {_TDSPR:.0f}% —— '
       f'等权相加赌的就是这一层离散度。' if _TDN else '')
    + '把它填进 <code>weight_col</code> 是<b>行不通</b>的：缺月会让底座把整个年度丢掉'
      '（实测只剩一个完整年，两张图一起不出）。要真正消掉这层偏差，得让 '
      '<code>fetch/miax.py</code> 把 indsum 返回体里的交易日数落成一列。'
      '离线体检（另建交易日历，已零误差复现上面那一列的全部覆盖月）的过程与实测数字'
      '写在本文件末尾的注释块 §F1 —— <b>页面不复述那些数</b>：它们不是从 '
      '<code>series/miax.csv</code> 算得出来的，写进图注就成了写死的数字。'
)

# ── breaks 是从 CSV 读出来的，不是抄文档 ────────────────────────────────
# 四个所各自 API 列的首个有值月：
#   adv_miax_options_api_kcontracts     2015-04（序列起点）
#   adv_pearl_options_api_kcontracts    2017-02
#   adv_emerald_options_api_kcontracts  2019-03
#   adv_sapphire_options_api_kcontracts 2024-08
# 后三个是新交易所上线，直接改变「MIAX 集团合计」这条序列的成分口径，
# 所以进 breaks；2015-04 是起点不是断点，不进。

SPEC = {
    'ticker': 'miax',
    'name':   'Miami International Holdings',
    'title':  'MIAX（Miami International Holdings）月度经营指标',
    'csv':    'miax.csv',
    'ccy':    'USD',
    'source': 'Source: MIAX Volume & RPC Report (ir.miaxglobal.com) and miaxglobal.com '
              'industry summary API; format after Goldman Sachs GIR',

    # ── 头条只能取 API 两列。底座的门槛要求头条有 ≥24 个月的共同历史，
    # 而 IR 月报 PDF 口径的 adv_multilist_options_kcontracts 只有 19 个月 ——
    # 把它放进头条，这一页要等到 2026-12 才够 24 个月，现在出不来
    # （实测：底座打印「共同历史只有 19 个月」并退出码 0）。
    # API 两列各有 136 个月且零空洞，共同历史 136 个月，够。
    'headline': [
        {'col': 'adv_miax_options_api_kcontracts', 'zh': 'MIAX 期权所 ADV（2015-04 起）',
         'unit': 'k contracts/day', 'fmt': 'f0c'},
        {'col': 'industry_adv_options_api_kcontracts', 'zh': '全美股票/ETF 期权行业 ADV',
         'unit': 'k contracts/day', 'fmt': 'f0c'},
    ],

    'groups': [
        # ── 四所 + 行业分母，API 口径，本页唯一的长历史。
        #    Pearl / Emerald / Sapphire 三列在各自上线前是空值 ——
        #    <b>平滑类图型（gs_line / gs_line_avg / lines_endlabels / stacked_dual）不能吃这三列</b>，
        #    引擎会把 null 当 0 画出塌到零的假线，gs_line 还会 null.toFixed() 抛异常。
        #    这一组只能用 lines（唯一能安全吃缺口的多线图型）。
        {'zh': '四家期权所 ADV（indsum API 口径，2015-04 起）', 'cols': [
            {'col': 'adv_miax_options_api_kcontracts', 'zh': 'MIAX（2015-04 起）',
             'unit': 'k contracts/day', 'fmt': 'f0c'},
            {'col': 'adv_pearl_options_api_kcontracts', 'zh': 'MIAX Pearl（2017-02 起）',
             'unit': 'k contracts/day', 'fmt': 'f0c'},
            {'col': 'adv_emerald_options_api_kcontracts', 'zh': 'MIAX Emerald（2019-03 起）',
             'unit': 'k contracts/day', 'fmt': 'f0c'},
            {'col': 'adv_sapphire_options_api_kcontracts', 'zh': 'MIAX Sapphire（2024-08 起）',
             'unit': 'k contracts/day', 'fmt': 'f0c'},
            {'col': 'adv_index_options_api_kcontracts', 'zh': '指数期权（2019-02~2024-12 曾做，现为 0）',
             'unit': 'k contracts/day', 'fmt': 'f1'},
            {'col': 'industry_adv_options_api_kcontracts', 'zh': '全美股票/ETF 期权行业总量（API 口径）',
             'unit': 'k contracts/day', 'fmt': 'f0c'},
        ]},

        # ── IR 月报口径的多挂牌期权：全仓唯一能与 Cboe 做**单价对照**的第二家。
        #    RPC 定义两家逐字相同（净交易费 ÷ 总成交张数），单位都是千张/日，不需要换算。
        #    但重叠窗口只有 2025-01~2026-06 共 18 个月，Cboe 那边有 114 个月。
        {'zh': '多挂牌期权（IR 月报口径，2025-01 起）', 'cols': [
            {'col': 'industry_adv_options_kcontracts', 'zh': '行业总量',
             'unit': 'k contracts/day', 'fmt': 'f0c'},
            {'col': 'adv_multilist_options_kcontracts', 'zh': 'MIAX 集团四所合计',
             'unit': 'k contracts/day', 'fmt': 'f0c'},
            {'col': 'share_multilist_options_pct', 'zh': 'MIAX 集团份额',
             'unit': '%', 'fmt': 'pct1'},
            {'col': 'rpc_multilist_options_usd', 'zh': '多挂牌期权 RPC（滚动三月均）',
             'unit': 'USD/contract', 'fmt': 'usd3'},
            {'col': 'trading_days_options', 'zh': '期权交易日数',
             'unit': 'days/month', 'fmt': 'f0'},
        ]},

        # ── Pearl Equities 股票：IR 月报口径。
        #    capture 与 Cboe 的分母不同（MIAX 是 total shares、Cboe 是 touched shares），
        #    两家的 take rate 不能相减、不能同轴画。
        {'zh': 'MIAX Pearl 股票（IR 月报口径，2025-01 起）', 'cols': [
            {'col': 'industry_adv_equities_mnshares', 'zh': '全美股票行业 ADV',
             'unit': 'mn shares/day', 'fmt': 'f0c'},
            {'col': 'adv_equities_mnshares', 'zh': 'Pearl Equities ADV',
             'unit': 'mn shares/day', 'fmt': 'f0'},
            # Pearl 股票份额实测区间 0.7~1.3%（源表已是百分数刻度，不加 scale）。
            # 用 f2 而不是 pct1：底座的比率量纲体检要求 pct* 列最大值 > 1.5，
            # 而这一列真实上限就是 1.3，配 pct1 会被硬失败挡下。单位由 unit 写明。
            {'col': 'share_equities_pct', 'zh': 'Pearl Equities 份额',
             'unit': '%', 'fmt': 'f2'},
            {'col': 'capture_equities_usd_per100shares', 'zh': '股票 capture（每 100 股，可为负）',
             'unit': 'USD/100 shares', 'fmt': 'usd3'},
        ]},

        # ── Pearl Equities 股票：API 口径，2020-12 起 68 个月，比 PDF 长 4 年多，
        #    而且多给了**日均名义额**（PDF 完全没有金额口径）。
        {'zh': 'MIAX Pearl 股票（indsum API 口径，2020-12 起，含名义额）', 'cols': [
            {'col': 'adv_equities_api_mnshares', 'zh': 'Pearl Equities ADV',
             'unit': 'mn shares/day', 'fmt': 'f1'},
            {'col': 'adnv_equities_api_usdbn', 'zh': 'Pearl Equities 日均名义额',
             'unit': 'USD bn/day', 'fmt': 'f2'},
            {'col': 'industry_adv_equities_api_mnshares', 'zh': '全美股票行业 ADV',
             'unit': 'mn shares/day', 'fmt': 'f0c'},
            {'col': 'industry_adnv_equities_api_usdbn', 'zh': '全美股票行业日均名义额',
             'unit': 'USD bn/day', 'fmt': 'f0c'},
        ]},

        # ── MIAX Futures：农产品实质是 Minneapolis 硬红春小麦一个品种，
        #    单位是**裸张数**（不是千张），与 cme.adv_ag_kcontracts 差约 160 倍且标的不重合。
        #    金融期货 2026-05 才上线，只有 3 个月。
        {'zh': 'MIAX Futures（IR 月报口径）', 'cols': [
            {'col': 'adv_futures_ag_contracts', 'zh': '农产品期货 ADV（硬红春小麦为主）',
             'unit': 'contracts/day', 'fmt': 'f0c'},
            {'col': 'rpc_futures_ag_usd', 'zh': '农产品期货 RPC（滚动三月均）',
             'unit': 'USD/contract', 'fmt': 'usd3'},
            {'col': 'adv_futures_fin_contracts', 'zh': '金融期货 ADV（2026-05 上线）',
             'unit': 'contracts/day', 'fmt': 'f0c'},
            {'col': 'rpc_futures_fin_usd', 'zh': '金融期货 RPC（爬坡期为负）',
             'unit': 'USD/contract', 'fmt': 'usd3'},
            {'col': 'trading_days_futures', 'zh': '期货交易日数',
             'unit': 'days/month', 'fmt': 'f0'},
        ]},
    ],

    # ── 图 A：Pearl Equities 成交额增长的量价分解，**走三分法** ────────────────
    # 恒等式 成交额 ≡ 成交股数 × 均价 是定义式；给了 bench_* 之后再拆一层：
    #   V ≡ V_行业 × s × r   （s = 股数份额、r = 均价相对行业）
    # ⇒ ln 三块可加、无交叉项。本页敢用三分法，靠的是**子集关系成立**：
    #   Pearl 在所成交 ⊂ 全美股票市场（含 TRF）。SINGLE_SPEC §1.3.1 说明底座验不了这一条，
    #   由 spec 作者负责 —— 核实过程写在文件末尾注释块 §A。
    # granularity='daily_avg'：四列都是当月**日均**（fetch/miax.py 的 API 段逐列写明）。
    #   **不给 weight_col / *_total_col**：本表的 trading_days_options 只覆盖 19 个月，
    #   填进去会让 Page._years 把 2021..2024 整年丢掉（实测只剩 1 个完整年，图不出）。
    #   底座会因此在图注里印一段 ⚠️ 等权相加的说明 —— 那句话是真的，别去掩盖。
    # price_scale=1e3：USD bn/day ÷ mn shares/day = 1e9/1e6 → USD/share。
    #   它在分子分母上同时出现，对分解结果一个数都不影响，只决定图注里的水平值读数。
    # year_start_month=1 / year_label='start'：MIAX 财年就是日历年（10-K 截至 12-31）。
    # years=4：CSV 只有 2020-12 起 68 个月 ⇒ 完整日历年恰好 5 个（2021..2025）⇒ 4 根柱。
    #   2020 缺 11 个月、2026 只到 7 月，底座会自己丢掉，不折算、不补。
    'decomp': [
        {'zh': 'MIAX Pearl Equities 成交额',
         'kind': 'share_price',
         'granularity': 'daily_avg',
         'value': {'col': 'adnv_equities_api_usdbn', 'zh': 'Pearl 日均成交额',
                   'unit': 'USD bn/day', 'fmt': 'f2'},
         'qty': {'col': 'adv_equities_api_mnshares', 'zh': 'Pearl 日均成交股数',
                 'unit': 'mn shares/day', 'fmt': 'f1'},
         'bench_value': {'col': 'industry_adnv_equities_api_usdbn',
                         'zh': '全美股票行业成交额', 'unit': 'USD bn/day', 'fmt': 'f0c'},
         'bench_qty': {'col': 'industry_adv_equities_api_mnshares',
                       'zh': '全美股票行业成交股数', 'unit': 'mn shares/day', 'fmt': 'f0c'},
         'share_zh': 'Pearl 的股数份额',
         'mix_zh': '均价相对行业（品种结构）',
         'price_zh': '成交量加权平均成交价',
         'price_unit': 'USD/share', 'price_fmt': 'usd2', 'price_scale': 1e3,
         'year_start_month': 1, 'year_label': 'start', 'years': 4,
         'note': _DECOMP_NOTE},
    ],

    # ── 图 B：量本身（水平值 + 12 个月滚动同比）────────────────────────────
    # 同样 granularity='daily_avg' 且没有权重列可给，理由与图 A 相同。
    'ttm_yoy': [
        {'zh': 'MIAX Pearl Equities 成交股数',
         'granularity': 'daily_avg',
         'level': {'col': 'adv_equities_api_mnshares', 'zh': 'Pearl 日均成交股数',
                   'unit': 'mn shares/day', 'fmt': 'f1'},
         'note': _TTM_NOTE},
    ],

    # 四条 RPC / capture 比成交量晚一个月：当年那份 PDF 里 12 月的 RPC 是空的，
    # 要等次年 5 月左右重发上一年那份才补上（已实证 Dec-25 的 RPC = $0.106 出现在
    # 2026-05-06 那份里）。最新月留空是这四列的常态，不参与门槛。
    'slow_cols': [
        'rpc_multilist_options_usd',
        'capture_equities_usd_per100shares',
        'rpc_futures_ag_usd',
        'rpc_futures_fin_usd',
    ],

    # 三次新交易所上线，直接改变「MIAX 集团合计」的成分口径。
    # 月份取自 CSV 里各所 API 列的首个有值月，不是抄文档。
    # 三次开所都只改**期权**这一端的口径（集团合计里多了一所），所以逐列绑定，
    # 不写成全页断点。不绑列的断点底座会画到本页每一张图上：实测「MIAX Sapphire
    # 上线（变 4 所）」曾出现在 19 张图里的 16 张 —— Pearl 股票 ADV/份额/capture、
    # MIAX Futures 的农产品与金融期货、期货交易日数全被标了一条与开所无关的红线，
    # 而开一家期权所既不改股票口径、也不改期货口径。
    'breaks': [
        {'month': '2017-02', 'col': c, 'zh': 'MIAX Pearl 上线（集团从 1 所变 2 所）'}
        for c in ('adv_miax_options_api_kcontracts', 'adv_multilist_options_kcontracts',
                  'share_multilist_options_pct')
    ] + [
        {'month': '2019-03', 'col': c, 'zh': 'MIAX Emerald 上线（变 3 所）'}
        for c in ('adv_miax_options_api_kcontracts', 'adv_multilist_options_kcontracts',
                  'share_multilist_options_pct')
    ] + [
        {'month': '2024-08', 'col': c, 'zh': 'MIAX Sapphire 上线（变 4 所）'}
        for c in ('adv_miax_options_api_kcontracts', 'adv_multilist_options_kcontracts',
                  'share_multilist_options_pct')
    ],

    'notes': [
        '<b>本页有两段长度差 10 年的历史，不要当成同一段。</b>'
        'indsum API 口径的四所 ADV 与行业分母回到 2015-04（136 个月）；'
        'IR 月报 PDF 口径的一切（多挂牌 ADV/份额/RPC、Pearl 股票、期货）只有 2025-01 起 19 个月。'
        '成交量与 RPC 的起点差整整 10 年。',

        '两个源的关系：<b>PDF 是权威值</b>（与 FY2025 10-K 对账，多挂牌 ADV 9,538、行业 55,798、'
        'Pearl 股票 183、农产品 12,989 四项误差均 ≤0.11%），'
        '<b>API 是历史与分拆</b>。两边的 MIAX 合计比值稳定在 0.9967~0.9976，'
        '但<b>行业分母差 3.1%~4.5%</b>（API 偏低）—— 所以 industry_adv_options_kcontracts 与 '
        'industry_adv_options_api_kcontracts 是两条不同的线，不要混用、不要互相回补。',

        '<b>多挂牌期权 RPC 是全仓唯一能做单价对照的第二家。</b>MIAX 与 Cboe 的 RPC 定义逐字相同'
        '（净交易费 ÷ 总成交张数），单位都是千张/日，不需要任何换算。'
        '但重叠窗口只有 2025-01~2026-06 共 18 个月（Cboe 侧有 114 个月），'
        '<b>2026-12 之前做不了同比与指数化</b>，并排图上必须写明 MIAX 线的起点。',

        '<b>industry_adv_equities_mnshares 与 ICE 的三个 tape 合并量是同一个分母。</b>'
        '本机实测 2026-06 = 23,383 vs ICE 的 tapeA+B+C = 23,382、2026-07 = 17,437 vs 17,437 —— '
        '两家独立申报、几乎逐位相同。横截面页上不要把这两列当成两个并列口径。',

        '<b>股票 capture 与 Cboe 不可比。</b>Cboe 的口径是 per 100 <i>touched</i> shares，'
        'MIAX 10-K 脚注 3 是 divided by one-hundredth of <i>total</i> shares —— 分母不同，'
        '不能相减、不能画在同一根轴上。股票端只有 ADV 可以跨家比。',

        '<b>指数期权那一列不是恒为 0。</b>本机对 CSV 实测：MIAX（M）在 <b>2019-02 ~ 2024-12</b> 期间'
        '做过指数期权，其中 57 个月非零，峰值 2019-12 = 10.208 千张/日（即日均 10,208 张，本列最大值），'
        '2025-01 起才一路为 0。当前为 0 是事实，恒为 0 不是 —— '
        '任何 assert == 0 的校验一旦回补到 2019~2024 就会当场炸。',

        '<b>Pearl / Emerald / Sapphire 三列在各自上线前是空值</b>（2017-02 / 2019-03 / 2024-08）。'
        '平滑类图型 gs_line / gs_line_avg / lines_endlabels / stacked_dual 不能吃 null —— '
        '引擎会把 null 当 0 参与 Catmull-Rom 画出塌到零的假线，gs_line 还会 null.toFixed() 抛 TypeError '
        '导致该卡片之后的 exhibit 全不渲染。这一组只能用 lines。',

        '<b>share_multilist_options_pct 与 share_equities_pct 在 CSV 里是百分数（17.1 = 17.1%）</b>，'
        '所以本页用 pct1 直出。注意这与 series/ice.csv、series/ndaq.csv 的 share_* 列相反 —— '
        '那两家存的是分数（0.191 = 19.1%），只能用 f3。三家页面上「份额」的显示形态因此不一致，'
        '根因在 fetcher 落库口径不统一，不是配置写错。',

        '<b>农产品期货单位是裸张数不是千张</b>（2026-07 = 12,123 张/日），'
        '与 series/cme.csv 的 adv_ag_kcontracts（2026-07 = 1,952.5 千张/日）差约 160 倍；'
        '且 MIAX 实质只是 Minneapolis 硬红春小麦一个品种，CME 是整个农产品复合体，'
        '两家几乎不争同一张合约。<b>只能做规模对照，不要建份额图。</b>',

        '<b>金融期货 2026-05 上线，那一个月的 ADV 是按「上线以来的交易日」算的，不是整月。</b>'
        '官方 PDF 该段的行标签是 "MIH - ADV from launch trade date"，并另给一行 '
        '"Trading days from launch"（2026-05 = 9 天，而当月 trading_days_futures = 20）。'
        '⇒ 2026-05 那一点与后面两点不可比，RPC 在爬坡期为负（返佣大于收费）也是真值不是错值。',

        '<b>官方会重述，且不止一列。</b>已实证 industry_adv_equities_mnshares 有三处改动'
        '（2025-07 从 17,648 改到 18,033，+2.2%），rpc_futures_ag_usd 也被改过'
        '（2026-04 从 1.981 改到 1.977）。另外 industry_adv_equities_mnshares 按交易日加权回 10-K '
        '有 +0.20% 的未闭合缺口（官方两边都没修），不要对这一列做硬断言。',

        '发布日以 PDF 正文里的 "Updated on &lt;Month D, YYYY&gt;" 为准，不要用 HTTP last-modified —— '
        '实测 5 份里有 3 份不一致，last-modified 早 1~3 天（文件先上传、后挂通稿）。',
    ],
}


# ══════════════════════════════════════════════════════════════════════════════
# 量价分解：口径核查实测日志
# ══════════════════════════════════════════════════════════════════════════════
# 上面 'decomp' / 'ttm_yoy' 两块**已经生效**。这一段是它们的依据 ——
# 图注只印从 series/miax.csv 现算得出来的数（全仓通则），下面这些是**离线体检**的结果，
# 算不出来所以不上页面，但落地前一个都不能少。数字全部由本机对 CSV 实测。
#
# ── A. 口径核查结论：可分解，两对分子分母各自同口径 ────────────────────────────
#
# A1. 同源。四列全部出自 fetch/miax.py 的 API 段（源 B，www.miaxglobal.com/indsum）：
#     Pearl 两列取 PEARLEQ (H) 行的 EXCHANGE_AVERAGE_TRADE_VOLUME ÷ 1e6 与
#     EXCHANGE_AVERAGE_NOTIONAL_VALUE ÷ 1e9；行业两列取**交易所行**的
#     TOTAL_MARKET_AVERAGE_TRADE_VOLUME / TOTAL_MARKET_AVERAGE_NOTIONAL_VALUE。
#     金额与股数是同一次请求、同一批标的、同一个 DATA_START_DATE..DATA_END_DATE 区间，
#     只是 sumType=volume / notional 两个视图。⇒ 没有口径楔子。
#     （TOTAL **行**自己的同名字段是陷阱值，约 19 倍，fetch 侧已避开，见 fetch/miax.py 口径坑 5。）
#
# A2. 同粒度。四列都是「期内总量 ÷ 期内交易日数」的**当月日均**，不是月合计、不是累计。
#     ⇒ granularity='daily_avg'。V_month / Q_month 直接就是该月的成交量加权均价，
#     与交易日数无关；只有**年度**聚合才需要权重（见 §F1）。
#
# A3. 同覆盖 + **子集关系成立**。行业两列含 TRF 场外；Pearl 两列是在所成交。
#     Pearl 在所成交 ⊂ 全美含 TRF ⇒ 份额 s = Q_pearl/Q_ind ∈ (0,1)，实测区间
#     0.086%~2.377%，从未接近 1。这正是 SINGLE_SPEC §1.3.1 点名「底座验不了、
#     spec 作者负责」的那一条，本页因此敢开 bench_value / bench_qty。
#
# A4. 同区间。四列各自的有值月份集合**完全相同**：2020-12..2026-07，68 个月，零缺口
#     （Pearl Equities 2020-12 才开业，这就是它的全生命周期）。这一条由 _eq_cover()
#     每次 import 现算并写进图注，不是一次性人工核对。
#
# ── B. 重述体检：本页用的四列**都没有被重述** ──────────────────────────────────
#
# 官方承认的重述只发生在 **PDF 段**（源 A）：
#     industry_adv_equities_mnshares  2025-05 17,585→17,586、2025-07 17,648→18,033（+2.2%）、
#                                     2025-08 16,379→16,380
#     rpc_futures_ag_usd              2026-04 1.981→1.977
# 这两列都不在 decomp 里。decomp 用的是 `_api` 后缀的**另一个源**，而 fetch/miax.py 的
# API 段「已入库的月份从不重抓」，所以库里的 68 个月是一次性快照，不会被官方重述改写。
#
# 快照本身信不信得过，靠 PDF 侧 19 个重叠月的逐月对账（_ind_recon() 现算，结果进图注）：
#   · adv_equities_api_mnshares vs adv_equities_mnshares（PDF）：19/19 全部一致到
#     PDF 的整数四舍五入以内 ⇒ **分子（Pearl）这一条是干净的**。
#   · industry_adv_equities_api_mnshares vs PDF 同概念列：16/19 一致（最大偏差 0.05%），
#     **3 个月对不上**：2025-06 −1.17%、2025-07 −1.08%、2026-06 −1.69%。
#     其中 2025-07 正是官方承认报错的那个月，API 值 17,837.7 落在旧值 17,648 与
#     新值 18,033 **之间**（第三个基准）。⇒ 行业分母带**月级 ±1.7% 的不确定性**。
#     年度影响小两个数量级：2025 年行业股数合计 +19.5bp、行业同比 0.28pp、
#     Pearl 份额同比 0.13pp（三个数都由 _ind_recon() 现算并印在图注里）。
#     ⇒ 年度分解结论不受影响；**月频图上不要拿这一列讲 1% 级的故事**。
#   · adnv_equities_api_usdbn / industry_adnv_equities_api_usdbn（金额两列）：
#     **PDF 段完全没有金额列，本仓没有第二个源可对**。唯一佐证是
#     docs/verify/verify_miax.md 记的单点（2026-07 Pearl 名义额占行业 0.39%，
#     本机复算 0.3946%）。⇒ 这是本页分解链条里唯一没有独立交叉验证的一环，
#     图注已如实标注，不要说成「已核实」。
#
# ── C. 均价序列的跳变体检 ────────────────────────────────────────────────────
#
# 两条均价（USD/股）都做了逐月跳变扫描。最大的几处**Pearl 与行业同向共振**，
# 说明是市场结构本身在动，不是口径变更：
#   2021-02→03  Pearl +28.9%、行业 +25.7%  ← meme 股行情退潮，低价股成交占比塌下去
#   2024-04→05  Pearl −17.2%、行业 −17.0%
# 只有两处是 Pearl 单独动、行业没跟，属于**Pearl 自己的成交结构变化**，要点名：
#   2025-05→06  Pearl +22.6% 而行业只有 +4.1%  ⇒ 相对行业的均价从 0.675 跳到 0.795
#   2026-03→04  Pearl −24.6% 而行业只有 −2.9%  ⇒ 相对行业从 0.692 跌到 0.537，之后没回来
# 两处都不是口径断点（源、单位、覆盖都没变），所以**不进 breaks**；
# 但它们正是三分法第三块（品种结构）的主要来源，读图时要知道钱是从哪来的。
#
# ── D. 均价与份额的水平值 ────────────────────────────────────────────────────
#
# D1 均价水平（USD/股，68 个月）
#     Pearl ：min 25.81  中位 34.67  max 77.83   首(2020-12) 58.15   末(2026-07) 34.74
#     行业  ：min 39.07  中位 49.00  max 61.37   首 45.97            末 58.96
#     相对倍数 Pearl/行业：min 0.537(2026-04)  中位 0.711  max 1.584(2021-03)
#         ⇒ **不是一个静止的折价**：2020-12..2021-12 共 13 个月 Pearl 均价**高于**行业
#           （最高 1.58 倍），2022-01 起转为折价并一路走深到 0.54。
#           「Pearl 中位 34.7 vs 行业 49.0」这个中位数对照会盖掉这次翻转，别单独引用。
#           （区间、溢价月数、最后一个溢价月由 _px_rel() 现算并进图注。）
#
# D2 份额与结构（年度，日历年）
#     year   股数份额%   均价相对   金额份额%      （恒等式：金额份额 = 股数份额 × 均价相对，
#     2021    0.3809     1.2444     0.4740          实测最大残差 2.2e-16）
#     2022    0.9913     0.8545     0.8471
#     2023    1.6929     0.7154     1.2111
#     2024    1.6234     0.6244     1.0137
#     2025    1.0452     0.6945     0.7258
#     月频：股数份额 峰 2.377%(2023-10) 谷 0.086%(2020-12) 末 0.670%(2026-07)
#     corr(股数份额, 均价相对) = −0.719（水平值）；一阶差分上只有 −0.037
#         ⇒ 「抢份额靠低价股」是**趋势层面**的关系，不是月度层面的机械同步。
#
# ── E. 分解读数与端点、毛刺实测 ──────────────────────────────────────────────
#
# E1 三分法（对数按总增长重标定，日历年，4 根柱）—— 与 docs/SINGLE_SPEC.md §1.3.1
#    的回归基准逐位一致，图上读到别的数就是 spec 配错了：
#     year   净增长%   行业pp    份额pp    结构pp
#     2022   +81.84    +2.39   +130.90    −51.45
#     2023   +27.89   −12.63    +60.68    −20.15
#     2024    −0.83   +16.88     −4.17    −13.54
#     2025    −3.25   +29.61    −43.32    +10.45
#    读法：2022–2023 的成交额增长**几乎全部来自抢份额**，而抢来的份额是低价股，
#    品种结构一路倒扣；2024–2025 反转 —— 行业自己在涨，Pearl 却在丢份额，
#    2025 才第一次靠品种结构回补。两分法看不见这一层（它只会说「量 −7.55pp、价 +4.30pp」）。
#
# E2 两分法（同一份数据，只进图注不上图）
#     year   净增长%    量pp      价pp     | 纯对数 lQ/lP/lV（对数点）| 算术 gQ/gP/交叉
#     2022   +81.84   +135.76   −53.92    | +99.19 / −39.39 / +59.80 | +169.64 / −32.56 / −55.24
#     2023   +27.89    +52.36   −24.46    | +46.18 / −21.58 / +24.60 |  +58.69 / −19.41 / −11.39
#     2024    −0.83     +5.70    −6.53    |  +5.72 /  −6.55 /  −0.83 |   +5.89 /  −6.34 /  −0.37
#     2025    −3.25     −7.55    +4.30    |  −7.68 /  +4.38 /  −3.30 |   −7.39 /  +4.47 /  −0.33
#
# E3 残差（底座六道护栏的实测余量，阈值都是 DECOMP_EPS = 1e-9）
#     算术三项闭合 ≤2.4e-16、纯对数两项 ≤2.4e-16、图上两块（乘过 w）≤1.5e-14、
#     三分法纯对数三项 ≤2.3e-16、三分法重标定后 ≤2.9e-14。
#     实跑 payload 逐格复核：Σ堆叠 − 菱形 最大 1.42e-14。⇒ 全部有 5 个数量级以上的余量。
#
# E4 为什么端点必须是 12 个月合计（底座的年度分桶天然满足，这里是它的代价证明）
#     终点 2026-07：点对点 vs 2025-07  gV −42.56%  gQ −38.97%  gP  −5.89%
#                   TTM12  vs 前 12 月  gV  +5.25%  gQ  −6.89%  gP +13.05%
#                   ⇒ **符号完全相反**，价的贡献差 18.9pp（对数口径 −6.07 vs +12.26）。
#                   原因：终点月 2026-07 Pearl ADV = 116.81 mn 股/日，在 68 个月里排
#                   第 **21 低**（31 分位），而基期月 2025-07 = 191.39 是第 19 高。
#     终点 2025-12（本页实际用的日历年端点，作对照）：
#                   点对点 gV −11.69% gQ −34.28% gP +34.37%
#                   TTM12  gV  −3.25% gQ  −7.39% gP  +4.47%   ⇒ 价的贡献差 29.9pp。
#
# E5 交叉项：为什么图上不能画算术分解
#     两分法 交叉/净增长 绝对占比：中位 43.0%、最大 67.5%（2022）。
#       （全仓参考值是「中位 10.5%、最大 362.8%」。本家没出现 362.8% 那种极端，
#         但中位数比参考值高 4 倍 —— 2022/2023 是「量暴涨 + 价暴跌」，g_Q·g_P 天然巨大。）
#     **三分法的算术版更糟**（3 个二阶 + 1 个三阶交叉项）：
#       2022 59.6%、2023 57.6%、**2024 300.7%、2025 429.9%**。
#       2025 那一格：主效应 +10.72%、交叉 −13.97%，而净增长只有 −3.25%。⇒ 只能用对数。
#     两法读数差：对「量」最大 33.88pp、对「价」最大 21.36pp（均出现在 2022，图注现算）。
#
# E6 毛刺量级（单月同比 vs 12 个月滚动合计同比，n = 45 个两者都有值的月份）
#     序列                  单月std  滚动std   相邻月最大跳变（单月 vs 滚动）      符号相反
#     Pearl ADV（股数）      39.3pp   49.6pp   63.9pp(2023-09→10) vs 44.8pp        14 = 31%
#     Pearl ADNV（成交额）    42.1pp   29.8pp   81.4pp(2023-09→10) vs 40.8pp        22 = 49%
#     行业 ADV               24.0pp   18.1pp   51.3pp(2025-10→11) vs  8.0pp        12 = 27%
#     行业 ADNV              25.3pp   19.9pp   37.1pp(2026-04→05) vs  6.1pp         9 = 20%
#     ⚠ **Pearl ADV 那一行的 σ 是反的（滚动 49.6 > 单月 39.3）**。真因：本序列 2021→2023
#       从 9 mn 股/日爬到 250 mn 股/日，滚动同比在 2022 年一度 +214%，σ 量的是这段趋势
#       幅度而不是噪声。判据要看相邻月跳变：63.9 vs 44.8pp（全窗口）、
#       54.9 vs 12.2pp（只看 2024-01 起的 31 个月）—— 滚动照样平滑得多。
#       底座的 ex_ttm 已按这条逻辑改写（σ 与跳变两个判据分别报、结论由数据判定），
#       图注会自己把「σ 反过来」这件事解释清楚，不需要 spec 再补一句。
#     符号相反 31%（Pearl ADV）与全仓在 SGX 上实测的 25–30% 同一量级；Pearl ADNV 更高（49%）。
#
# ── F. 已知缺陷（图注已如实印出，这里记它的量级）─────────────────────────────
#
# F1 **本页拿不到股票端的交易日数，年度合计是「按月等权」而不是「按交易日加权」。**
#    series/miax.csv 里唯一的交易日列是 trading_days_options，只有 2025-01 起 19 个月
#    （PDF 段），而 decomp 要的是 2021..2025。把它填进 weight_col 的实测后果：
#    Page._years 因缺月丢掉 4 个年度，只剩 1 个完整年，底座打印
#    「完整年度只有 1 个（起始月 1），画不出任何一根『相对上一年』的柱」，图直接不出。
#    ⇒ 三个字段全不给，granularity='daily_avg' 让底座走「⚠️ 等权相加」那一支。
#    代价本机量过（构造独立的 NYSE 交易日历，已验证**零误差**复现 trading_days_options
#    那 19 个月，含 2025-01-09 卡特国葬休市）：
#        年度均价水平误差   Pearl ≤41bp（2022）、行业 ≤48bp（2021）
#        年度增速误差       价的贡献 ≤0.81pp（行业 2022）、Pearl 侧 ≤0.40pp（2023）
#    ⇒ 偏差有界且小于图上任何一块的量级，但**不是零**。这几个数**不写进图注** ——
#    它们算不自 series/miax.csv，写进去就成了写死的数字（全仓通则）。
#    干净解：让 fetch/miax.py 把 indsum 返回体里的交易日数落成一列，再填 weight_col。
#    那一步落地后，这一节连同图注里那段 ⚠️ 一起作废。
#
# F2 行业分母的月级 ±1.7% 不确定性（见 §B）。年度层面 ≤20bp，不影响本图结论。
#
# F3 金额两列在本仓内无第二源可对（见 §B 末）。
#
# ── G. 顺手记下的底座小缺口（不在本次授权范围，未改）────────────────────────
#
# Page.__init__ 的 `aux` 列存在性检查（build/single.py，「decomp / ttm_yoy 引用的列同样要查」
# 那一段）收集了 value / qty / *_total_col / weight_col / level，**漏了 bench_value 与
# bench_qty**。写错 bench 列名不会在那里被拦下，要等 self.ser() 取列时才炸，
# 报错信息离 spec 更远。本页四列都真实存在，所以不受影响。
