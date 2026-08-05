# -*- coding: utf-8 -*-
"""HKEX 香港交易及結算所 00388 —— **季度费率**解析器（无人值守）。

产出 series/fee_rates.csv 里 company=HKEX 的 16 个 metric，覆盖当前官方口径下
可得的全部季度。只读网、只写 cache/，不碰 series/。

═══════════════════════════════════════════════════════════════════════════
1. 数据源与发现方式
═══════════════════════════════════════════════════════════════════════════
HKEX 不进 EDGAR。业绩公告的真正落脚点是 hkexgroup.com 的 IR 站，且官方维护了
一组**语义化的跳转 URL**（302 → 当期 PDF），这是唯一能无人值守发现新季度的入口：

    https://www.hkexgroup.com/Investor-Relations/Financial-Results-and-Presentations/
        {Y}/Q1/{Y}-Q1-Results-Announcement?sc_lang=en
        {Y}/Interim/{Y}-Interim-Results-Announcement?sc_lang=en
        {Y}/Q3/{Y}-Q3-Results-Announcement?sc_lang=en
        {Y}/Annual/{Y}-Annual-Results-Announcement?sc_lang=en

实测（2026-08-05）2022–2026 全部命中，最终 PDF 落在三个不同域：
    hkexgroup.com/-/media/.../annouce/documents/2026/260429_1qtr_e.pdf
    hkexgroup.com/-/media/.../annouce/documents/2025/250820_interim_e.pdf
    www1.hkexnews.hk/listedco/listconews/sehk/2026/0226/2026022600166.pdf   ← 年报走这里
⇒ **不要写死 PDF 直链**。年度业绩有时挂 hkexnews、有时挂 hkexgroup，且
  Q2/Q4 的路径段是 `Interim`/`Annual` 而不是 `Q2`/`Q4`（写 Q2/Q4 一律 404）。

反爬情况（2026-08-05 实测）：
    普通桌面 UA + urllib 即可，无 Cloudflare/PerimeterX、无登录态、无验证码。
    唯一坑：**HEAD 请求被 Akamai 一律返 503**，必须用 GET（可只读首字节）。

series/fee_rates.csv 里 HKEX 现有行的 source_url 用的是 hkex.com.hk 的
「新闻稿」镜像（.../News-Release/2026/260429news/260429news_e.pdf），那是同一份
公告的另一个副本，且后缀在 `_e.pdf` / `_eng.pdf` 之间随机摇摆（250430/250820/
251105/260429 是 `_e`，260226 是 `_eng`）。本模块**改用实际下载解析的那一份**
（IR 跳转解析出来的 canonical PDF）作为 source_url —— 上层按
(company, period, metric) 合并，source_url 不进 key。

═══════════════════════════════════════════════════════════════════════════
2. 披露节奏与「季度不是季度」这个大坑
═══════════════════════════════════════════════════════════════════════════
HKEX 一年发四份，但**只有 Q1 那份是单季口径**：

    Q1 公告  (4 月底)  → 三个月                    ⇒ Q1 直接可用
    Interim (8 月中下) → 六个月 1H                 ⇒ Q2 = 1H − Q1
    Q3 公告  (11 月初) → 九个月 YTD Q3             ⇒ Q3 = YTD Q3 − 1H
    Annual  (次年 2 月) → 十二个月 FY              ⇒ Q4 = FY − YTD Q3

分部收入（Cash Segment 的 trading / clearing / SI fee）**只有累计数**，必须差分。
交易日数同理（60 / 120 / 185 / 246 → 60 / 60 / 65 / 61）。

但 **ADT 不能差分**：它是「日均」，差分会引入四舍五入误差。HKEX 每份公告里都另有
一张单季对照表（"Comparison of Qn 20XX with Qn 20YY" 下的 Key Market Statistics），
直接给单季 ADT，必须用那个。
    实证：2025-Q4 官方直接披露 ADT = 209.9；用 FY 231.5×246 − 9M 238.7×185 再
    除 61 差分出来是 209.66 → 209.7。CSV 里存的是 209.7（差分产物），本模块用
    官方直接披露的 209.9。差 0.2，会把 trading_fee_effective_rate_both_sides
    从 0.009709 拉到 0.009700。见文件末 VERIFICATION_NOTES。

═══════════════════════════════════════════════════════════════════════════
3. 口径断层：2024-Q3 之前不要碰
═══════════════════════════════════════════════════════════════════════════
`cash_seg_trading_fee_revenue` 的口径是「Stock Exchange equity products」，
**不含** Northbound。HKEX 是从 2024 年三季报才开始这样拆的：
    2024-Q1 公告原文：「Trading fees of equity products for Q1 2024 were $654m」
                      —— 654 = 543(SEHK) + 111(Northbound)，混在一起。
    2025-Q1 公告的图里才有 543 / 111 分开列。
⇒ 老公告的数字**语义不同**，直接拿来会让同一条序列前后不可比。
⇒ 本模块只吃「新口径」的文档（2024 年三季报起），并且 2024 各季一律走
  **2025 年各份公告的上年同期比较列**（那是官方按新口径重述过的）。
  能覆盖到的最早季度因此是 2024-Q1，再往前官方没有按新口径给过累计数。

═══════════════════════════════════════════════════════════════════════════
4. PDF 解析：为什么不能按阅读顺序硬数
═══════════════════════════════════════════════════════════════════════════
Cash Segment 的费用拆分只存在于一张**堆叠柱状图的数据标签**里，正文叙述不全
（例如 SI fee 从头到尾没在正文出现过；1H 公告的正文还把 clearing 和 SI 合并
成一个数 "$1,976 million"）。所以必须解析图。

图的文本抽取顺序**看起来**是「图例顺序的 (本期, 上年同期) 数对」，但有两个陷阱：
  (a) 图里有一个**没有图例标签的空系列**，抽出来是 `-` / `-`。它出现的位置会变：
      2024-Q3 在第 5 对，2025 各期在第 6 对，2026-Q1 干脆没有。
      ⇒ 先剔掉 None，再和图例按序对齐，不能按下标硬映射。
  (b) 图例文案会改：2025-Q1 之前叫 "Stock Exchange trades"，之后叫
      "Stock Exchange equity products"。⇒ 正则要两种都认。
末尾固定是 4 对：营业开支 / EBITDA / 收入净额 / 交易相关开支。

**所有解析结果都过算术自校验**（各段之和 + 交易相关开支 == 收入净额；
收入净额 − 营业开支 == EBITDA）。对不上直接抛异常，绝不吐半对的数。

年报的版式完全不同（两张独立的图 + Summary 表），单独写了 _parse_annual_charts，
同样靠算术恒等式定位（excl-SB + SB == 合计；四段之和 == 总计）。

ADT 数字后面常粘着**脚注上标数字**（"225.44" 其实是 225.4 + 脚注4，
"238.74" 是 238.7 + 脚注4）。ADT 官方一律 1 位小数，所以按 `(\\d+\\.\\d)` 截断。

═══════════════════════════════════════════════════════════════════════════
5. 费率表常数（8 个 metric）从哪来
═══════════════════════════════════════════════════════════════════════════
这几个不是季度经营数据，是**收费表**，只在改制时跳变。全部真下载真解析：

  trading_fee_listed_rate_per_side  0.00565  ← 交易所收费页 HTML
  trading_tariff_per_side           0.0      ← 同页脚注「Effective 1 January 2023,
                                                Trading Tariff was removed」
  stock_clearing_fee_exchange_trade 0.0      ← HKSCC OP SEC21.pdf「Stock clearing fee NIL」
  stock_settlement_fee_*                     ← 2025-06-30 改制，两套：
      改制前 0.002% / 0.001%，min HK$2 / max HK$100  ← 019_25 规则**改字稿**
      改制后 0.0042% / 0.0021%，无 min/max          ← 现行 SEC21.pdf

改制前那套只在**改字稿**（`..._e_markup.pdf`）里能看到划线原文；
CSV 现有行把改制前的值挂在「干净版通函」上，那份通函其实只有改制后的数字。
本模块改挂 markup 稿（值完全一致，只是把出处修对）。

季度归属规则：**按季初生效的费率**。2025-06-30 是 Q2 最后一个交易日，
所以 2025-Q2 仍算旧费率、2025-Q3 起新费率 —— 与 CSV 现有行一致。

已知局限（故意的）：SEC21.pdf 永远只有现行费率。若 HKEX 再次改制，本模块会发现
SEC21 解析出的数字和 _SETTLEMENT_FEE_REGIMES 最后一档对不上，并**抛异常**要求
人工补一档（含生效日和 markup 稿 URL），而不是悄悄把历史季度全改成新费率。
"""

from __future__ import annotations

import datetime as _dt
import os
import re
import urllib.error
import urllib.request

try:
    import fitz  # PyMuPDF
except ImportError as _e:  # pragma: no cover
    raise ImportError('rates_hkex 需要 PyMuPDF: pip install pymupdf') from _e


# ── 网络 ──────────────────────────────────────────────────────────────────
UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
TIMEOUT = 90

IR_BASE = ('https://www.hkexgroup.com/Investor-Relations/'
           'Financial-Results-and-Presentations')

# (path 段, 该文档覆盖到第几个季度)
KINDS = (
    ('Q1',      'Q1',      1),
    ('Interim', 'Interim', 2),
    ('Q3',      'Q3',      3),
    ('Annual',  'Annual',  4),
)

# 新口径（trading fee 拆出 Northbound）最早成立的年份：见模块 docstring §3
FIRST_YEAR = 2024

# 新版式（Cash Segment 分部图把 SEHK / Northbound / SI 拆开）最早的一份文档。
# 2024-Q1 / 2024-Interim 用的还是旧版式，正文只有合并数，解析不出来是**设计如此**，
# 它们那两个累计期改从 2025 年同类文档的「上年同期比较列」取。
NEW_LAYOUT_FROM = (2024, 2)   # (year, KINDS 下标) —— 2024 年的 Q3 那份起

FEE_PAGE_URL = ('https://www.hkex.com.hk/Services/Rules-and-Forms-and-Fees/Fees/'
                'Securities-(Hong-Kong)/Trading/Transaction?sc_lang=en')
SEC21_URL = ('https://www.hkex.com.hk/-/media/HKEX-Market/Services/'
             'Rules-and-Forms-and-Fees/Rules/HKSCC/Operational-Procedures/SEC21.pdf')
SETTLE_MARKUP_URL = (
    'https://www.hkex.com.hk/-/media/HKEX-Market/Services/Rules-and-Forms-and-Fees/'
    'Rules/HKSCC/Rule-Update_Operational-Procedures/'
    '019_25_HKSCC-OP_Stock-settlement-fee-restructure_e_markup.pdf')

# 结算费制度沿革。effective_q = 该费率生效后的第一个完整季度（含）。
# 2025-06-30 生效 → Q2 最后一天，故从 2025-Q3 起算（与 CSV 现有行一致）。
_SETTLEMENT_FEE_REGIMES = (
    {
        'from': (0, 0),
        'listed': 0.002, 'crossed': 0.001, 'min': 2, 'max': 100,
        'min_unit': 'HKD', 'max_unit': 'HKD',
        'source': SETTLE_MARKUP_URL,
    },
    {
        'from': (2025, 3),
        'listed': 0.0042, 'crossed': 0.0021, 'min': 0, 'max': 0,
        'min_unit': 'HKD_none', 'max_unit': 'HKD_none',
        'source': SEC21_URL,
    },
)


class ParseError(RuntimeError):
    """解析失败 —— 宁可炸也不吐半对的数。"""


def _log(msg):
    print('[rates_hkex] %s' % msg)


def _get(url, want_body=True):
    """GET；返回 (final_url, body_or_None)。HEAD 会被 Akamai 503，别用。"""
    req = urllib.request.Request(url, headers={
        'User-Agent': UA,
        'Accept': '*/*',
        'Accept-Language': 'en-US,en;q=0.9',
    })
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        final = resp.geturl()
        body = resp.read() if want_body else None
    return final, body


def _cache_dir(cache_dir):
    d = os.path.join(cache_dir, 'hkex_rates')
    os.makedirs(d, exist_ok=True)
    return d


def _fetch_to_cache(url, path, force=False):
    if not force and os.path.exists(path) and os.path.getsize(path) > 50_000:
        return path
    _log('download %s' % url)
    _, body = _get(url)
    if len(body) < 10_000:
        raise ParseError('下载体积异常 (%d bytes): %s' % (len(body), url))
    with open(path, 'wb') as fh:
        fh.write(body)
    return path


# ═══════════════════════════════════════════════════════════════════════════
# 文档发现
# ═══════════════════════════════════════════════════════════════════════════

def _landing(year, kind):
    return '%s/%d/%s/%d-%s-Results-Announcement?sc_lang=en' % (
        IR_BASE, year, kind, year, kind)


def discover_documents(cache_dir, first_year=FIRST_YEAR, today=None):
    """返回 [ {year, kind, nq, url, path, order} ]，按发布先后排序。

    年报在次年 2 月才发，所以 today 那年的年报要到明年才有；一律靠
    landing URL 是否 200 判断，不猜。
    """
    today = today or _dt.date.today()
    cdir = _cache_dir(cache_dir)
    docs = []
    for year in range(first_year, today.year + 1):
        for ki, (kind, _label, nq) in enumerate(KINDS):
            try:
                final, body = _get(_landing(year, kind))
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    continue
                _log('WARN %d %s landing HTTP %s' % (year, kind, e.code))
                continue
            except Exception as e:                       # noqa: BLE001
                _log('WARN %d %s landing failed: %s' % (year, kind, e))
                continue
            if not final.lower().endswith('.pdf'):
                # 还没发布时 IR 站返 404 页面（200 + HTML）
                continue
            name = '%d_%s.pdf' % (year, kind)
            path = os.path.join(cdir, name)
            if not (os.path.exists(path) and os.path.getsize(path) > 50_000):
                with open(path, 'wb') as fh:
                    fh.write(body)
                _log('saved %s <- %s' % (name, final))
            docs.append({'year': year, 'kind': kind, 'nq': nq,
                         'url': final, 'path': path, 'order': year * 10 + ki})
    docs.sort(key=lambda d: d['order'])
    return docs


# ═══════════════════════════════════════════════════════════════════════════
# PDF 解析
# ═══════════════════════════════════════════════════════════════════════════

_NUM = re.compile(r'^\(?-?[\d,]+\)?$')


def _num(tok):
    """'1,484' -> 1484 ; '(3)' -> -3 ; '-' -> None"""
    tok = tok.strip()
    if tok in ('-', '–', '—', 'N/A'):
        return None
    neg = tok.startswith('(') and tok.endswith(')')
    tok = tok.strip('()').replace(',', '')
    if not re.fullmatch(r'-?\d+', tok):
        raise ParseError('非数字 token: %r' % tok)
    v = int(tok)
    return -v if neg else v


def _pages(path):
    doc = fitz.open(path)
    try:
        return [p.get_text() for p in doc]
    finally:
        doc.close()


# 图例标签 → 内部键。文案改过（trades → equity products），两种都认。
_LEGEND = (
    ('trading_sehk',   r'Trading fees for\s+Stock\s+Exchange\s+(?:trades|equity products)'),
    ('trading_nb',     r'Trading fees for\s+Northbound Trading'),
    ('clearing_sehk',  r'Clearing fees for\s+Stock\s+Exchange\s+(?:trades|equity products)'),
    ('si_sehk',        r'SI fees for\s+Stock\s+Exchange\s+(?:trades|equity products)'),
    ('clearing_si_nb', r'Clearing and SI fees for\s+Northbound Trading'),
    ('listing',        r'Stock Exchange\s+listing fees'),
    ('depository',     r'Depository, custody and\s+nominee services fees'),
    ('net_inv',        r'Net investment income'),
    ('other_rev',      r'Other revenue'),
    ('txn_exp',        r'Transaction-related\s+expenses'),
)


def _parse_segment_chart(pages):
    """Q1 / Interim / Q3 公告里的 Cash Segment 堆叠柱状图。

    返回 {key: (current, prior)}，含 trading_sehk / clearing_sehk / si_sehk 等。
    """
    for text in pages:
        if 'Trading fees for' not in text or 'Transaction-related' not in text:
            continue
        m = re.search(r'\(\$m\)\s*\n(?P<nums>(?:[^\n]*\n)*?)(?P<rest>Trading fees for\b.*)',
                      text, re.S)
        if not m:
            continue

        nums = [_num(t) for t in m.group('nums').split() if _NUM.match(t) or t == '-']
        if len(nums) < 20 or len(nums) % 2:
            continue

        rest = re.sub(r'\s+', ' ', m.group('rest'))
        found = []
        for key, pat in _LEGEND:
            mm = re.search(pat, rest)
            if mm:
                found.append((mm.start(), key))
        found.sort()
        labels = [k for _, k in found]
        if 'trading_sehk' not in labels or 'txn_exp' not in labels:
            continue

        pairs = [(nums[i], nums[i + 1]) for i in range(0, len(nums), 2)]
        # 末尾固定 4 对：营业开支 / EBITDA / 收入净额 / 交易相关开支
        opex, ebitda, total, txn = pairs[-4:]
        segs = [p for p in pairs[:-4] if p[0] is not None]  # 剔掉无标签的空系列

        seg_labels = [k for k in labels if k != 'txn_exp']
        if len(segs) != len(seg_labels):
            raise ParseError('图例(%d)与数据段(%d)对不上: %s'
                             % (len(seg_labels), len(segs), seg_labels))

        # 算术自校验（本期 + 上年同期各一遍）
        for col in (0, 1):
            s = sum(p[col] for p in segs) + txn[col]
            if s != total[col]:
                raise ParseError('分段合计 %d + 交易开支 %d != 收入净额 %d'
                                 % (s - txn[col], txn[col], total[col]))
            if total[col] - opex[col] != ebitda[col]:
                raise ParseError('收入净额 %d − 开支 %d != EBITDA %d'
                                 % (total[col], opex[col], ebitda[col]))

        return dict(zip(seg_labels, segs))
    raise ParseError('没找到 Cash Segment 分部图')


def _numeric_run(text):
    """按行取数字 token，遇到 0/1,000/2,000… 的坐标轴刻度就停。

    注意首行往往是页码（"18"），后面还可能跟年份标签，所以调用方必须对
    **两种奇偶起点**都试一遍，别假设第 0 个 token 就是第一根柱子。
    """
    out = []
    for raw in text.split('\n'):
        tok = raw.strip()
        if not tok:
            continue
        if not (_NUM.match(tok) or tok == '-'):
            continue
        v = _num(tok)
        if v == 0 and len(out) >= 6:      # 坐标轴从 0 起
            break
        out.append(v)
    return out


def _pairings(nums):
    """(本期, 上年同期) 数对的候选切法：偏移 0 和 1 各一份。"""
    for off in (0, 1):
        seq = nums[off:]
        yield [(seq[i], seq[i + 1]) for i in range(0, len(seq) - 1, 2)]


def _parse_annual_charts(pages):
    """年报版式：交易费、结算费各一张独立的图。靠算术恒等式认段，不靠位置。"""
    res = {}

    # ── 交易费图：excl-SB + SB == SEHK合计； SEHK + NB == 总计
    for text in pages:
        if 'Trading fees for' not in text or 'SI fees for' in text:
            continue
        if 'Northbound Trading' not in text or 'Total' not in text:
            continue
        for pr in _pairings(_numeric_run(text)):
            for i in range(max(0, len(pr) - 4)):
                a, b, c, d, e = pr[i:i + 5]
                if None in (a[0], b[0], c[0], d[0], e[0]):
                    continue
                if all(a[k] + b[k] == c[k] and c[k] + d[k] == e[k] for k in (0, 1)):
                    res['trading_sehk'] = c
                    break
            if 'trading_sehk' in res:
                break
        if 'trading_sehk' in res:
            break

    # ── 结算费图：excl-SB + SB == CF_SEHK； CF_SEHK+SI_SEHK+CF_NB+SI_NB == 总计
    for text in pages:
        if 'SI fees for' not in text or 'Clearing fees for' not in text:
            continue
        for pr in _pairings(_numeric_run(text)):
            for i in range(max(0, len(pr) - 6)):
                grp = pr[i:i + 7]
                if any(v is None for p in grp for v in p):
                    continue
                a, b, c, d, e, f, g = grp
                if all(a[k] + b[k] == c[k] and c[k] + d[k] + e[k] + f[k] == g[k]
                       for k in (0, 1)):
                    res['clearing_sehk'] = c
                    res['si_sehk'] = d
                    break
            if 'clearing_sehk' in res:
                break
        if 'clearing_sehk' in res:
            break

    missing = {'trading_sehk', 'clearing_sehk', 'si_sehk'} - set(res)
    if missing:
        raise ParseError('年报图解析失败，缺 %s' % sorted(missing))

    # 正文交叉核对（年报正文口径偶有合并，只 warn 不 fail）
    body = '\n'.join(pages)
    m = re.search(r'Trading fees for Stock Exchange equity products for \d{4} were '
                  r'\$([\d,]+) million', body)
    if m and _num(m.group(1)) != res['trading_sehk'][0]:
        _log('WARN 年报正文 trading fee %s 与图 %d 不符'
             % (m.group(1), res['trading_sehk'][0]))
    return res


def _parse_trading_days(pages):
    """Cash Segment 的 Key Market Indicators 里的累计交易日数 (本期, 上年同期)。

    一份公告里 "Number of trading days" 会出现 2–3 次（现货 / 衍生品 / 商品），
    数字不一样（例：2025-Q3 是 185 / 194 / 189）。现货段永远排最前（Cash 是
    第一个分部），所以取**第一处**，并用「前文出现过 ADT of equity products」兜底。
    """
    body = '\n'.join(pages)
    for m in re.finditer(r'Number of trading days\s*\d?\s*\n\s*(\d{1,3})\s*\n\s*(\d{1,3})',
                         body):
        cur, pri = int(m.group(1)), int(m.group(2))
        if not (1 <= cur <= 260 and 1 <= pri <= 260):
            continue
        head = body[max(0, m.start() - 6000):m.start()]
        if 'ADT of equity products' not in head:
            continue
        return cur, pri
    raise ParseError('没解析到 Cash Segment 的 Number of trading days')


_ADT_LABEL = r'ADT of equity products traded on\s*\n?\s*the Stock Exchange\s*[\d, ]*\(\$bn\)'


def _parse_quarter_adt(pages, year, nq):
    """单季 ADT（不是累计）。公告里有专门的单季对照表，别去差分。"""
    body = '\n'.join(pages)
    q = 'Q%d' % nq
    hits = []
    for m in re.finditer(_ADT_LABEL, body):
        tail = body[m.end():m.end() + 200]
        vals = re.findall(r'(\d{1,4}\.\d)\d*', tail)   # 去掉粘在后面的脚注上标
        if len(vals) < 2:
            continue
        head = body[max(0, m.start() - 900):m.start()]
        hits.append((head, float(vals[0]), float(vals[1])))

    if nq == 1:
        # Q1 公告全篇都是单季口径，第一处即可
        if hits:
            return hits[0][1], hits[0][2]
    else:
        # 单季对照表的表头：'Q3 2025 / Q3 2024' 或 'Three months ended 30 Jun 2025'。
        # 注意 PDF 里表头会硬换行成 'Three months \nended  \n30 Jun 2025'，
        # 所以词间必须用 \s+ 而不是空格。
        pat_q = re.compile(r'%s\s+%d\b' % (q, year))
        pat_3m = re.compile(r'Three\s+months\s+ended')
        for head, cur, pri in hits:
            if pat_q.search(head) or pat_3m.search(head):
                return cur, pri
    raise ParseError('没解析到 %d-Q%d 单季 ADT' % (year, nq))


def parse_document(doc):
    """解析一份业绩公告，返回该文档报告的**累计**口径数据。"""
    pages = _pages(doc['path'])
    if doc['kind'] == 'Annual':
        chart = _parse_annual_charts(pages)
    else:
        chart = _parse_segment_chart(pages)

    td_cur, td_pri = _parse_trading_days(pages)
    adt_cur, adt_pri = _parse_quarter_adt(pages, doc['year'], doc['nq'])

    out = {}
    for col, yr in ((0, doc['year']), (1, doc['year'] - 1)):
        out[(yr, doc['nq'])] = {
            'trading_fee': chart['trading_sehk'][col],
            'clearing_fee': chart['clearing_sehk'][col],
            'si_fee': chart['si_sehk'][col],
            'trading_days': (td_cur, td_pri)[col],
            'adt': (adt_cur, adt_pri)[col],
            'source': doc['url'],
            'order': doc['order'],
        }
    return out


# ═══════════════════════════════════════════════════════════════════════════
# 收费表常数
# ═══════════════════════════════════════════════════════════════════════════

def _html_text(raw):
    t = re.sub(r'<script.*?</script>', ' ', raw, flags=re.S | re.I)
    t = re.sub(r'<style.*?</style>', ' ', t, flags=re.S | re.I)
    t = re.sub(r'<[^>]+>', ' ', t)
    for a, b in (('&nbsp;', ' '), ('&amp;', '&'), ('&#39;', "'"), ('&quot;', '"')):
        t = t.replace(a, b)
    return re.sub(r'\s+', ' ', t)


def parse_fee_schedule(cache_dir):
    """真下载真解析收费表；解析不出来就抛，绝不回退到记忆里的数字。"""
    cdir = _cache_dir(cache_dir)

    # ── 交易费页（HTML）
    p = _fetch_to_cache(FEE_PAGE_URL, os.path.join(cdir, 'fee_trading_page.html'))
    txt = _html_text(open(p, encoding='utf-8', errors='ignore').read())
    m = re.search(r'Trading Fee of (\d+\.\d+)% per side of the consideration', txt)
    if not m:
        raise ParseError('交易所收费页没解析到 Trading Fee 费率')
    trading_fee_rate = float(m.group(1))
    if not re.search(r'Trading Tariff was removed', txt):
        raise ParseError('交易所收费页没有「Trading Tariff was removed」，'
                         '交易征费可能已恢复，需人工确认')
    trading_tariff = 0.0

    # ── HKSCC 现行营运程序 SEC21（PDF）
    p = _fetch_to_cache(SEC21_URL, os.path.join(cdir, 'hkscc_sec21.pdf'))
    sec21 = '\n'.join(_pages(p))
    flat = re.sub(r'\s+', ' ', sec21)
    if not re.search(r'Stock clearing fee\s+NIL', flat):
        raise ParseError('SEC21 没解析到「Stock clearing fee NIL」')
    clearing_fee_exchange_trade = 0.0
    m = re.search(r'(\d+\.\d+)% per side of gross value of an Exchange Trade', flat)
    if not m:
        raise ParseError('SEC21 没解析到 Exchange Trade 结算费率')
    cur_listed = float(m.group(1))
    # min/max 只能在**这一条**费率的行文里找。SEC21 别处（SI Transaction、
    # Transfer Instruction）至今仍有 "minimum fee of HK$2 and maximum fee of
    # HK$100"，全文搜会永远误判成「还有 min/max」。
    cur_has_minmax = bool(re.search(r'minimum fee of HK\$', flat[m.start():m.end() + 220]))
    m = re.search(r'(\d+\.\d+)% per side of gross value of a crossed Exchange Trade', flat)
    if not m:
        raise ParseError('SEC21 没解析到 crossed Exchange Trade 结算费率')
    cur_crossed = float(m.group(1))
    cur_has_minmax = cur_has_minmax or bool(
        re.search(r'minimum fee of HK\$', flat[m.start():m.end() + 220]))

    # ── 改制前费率：规则改字稿（划线版）
    p = _fetch_to_cache(SETTLE_MARKUP_URL, os.path.join(cdir, 'hkscc_019_25_markup.pdf'))
    mk = re.sub(r'\s+', ' ', '\n'.join(_pages(p)))
    # 划线版把新旧两个数字粘在一起："0.00420.0020%"
    m = re.search(r'0\.0042(0\.00\d+)% per side of gross value of an Exchange Trade', mk)
    if not m:
        raise ParseError('markup 稿没解析到改制前 Exchange Trade 费率')
    old_listed = float(m.group(1))
    m = re.search(r'0\.0021(0\.00\d+)% per side of gross value of a crossed Exchange Trade', mk)
    if not m:
        raise ParseError('markup 稿没解析到改制前 crossed Exchange Trade 费率')
    old_crossed = float(m.group(1))
    m = re.search(r'minimum fee of HK\$(\d+) and a maximum fee of HK\$(\d+) per trade', mk)
    if not m:
        raise ParseError('markup 稿没解析到改制前 min/max')
    old_min, old_max = int(m.group(1)), int(m.group(2))

    regimes = [dict(r) for r in _SETTLEMENT_FEE_REGIMES]
    regimes[0].update(listed=old_listed, crossed=old_crossed,
                      min=old_min, max=old_max)
    regimes[-1].update(listed=cur_listed, crossed=cur_crossed)

    # 现行 SEC21 必须和最后一档吻合，否则说明又改制了 —— 停下来要人工补一档
    last = _SETTLEMENT_FEE_REGIMES[-1]
    if (cur_listed, cur_crossed) != (last['listed'], last['crossed']) or cur_has_minmax:
        raise ParseError(
            'SEC21 现行结算费 (%s%%/%s%%, min/max=%s) 与已知最后一档 '
            '(%s%%/%s%%, 无 min/max) 不符 —— HKSCC 可能又改制了，'
            '请在 _SETTLEMENT_FEE_REGIMES 追加一档（含生效季与 markup 稿 URL）'
            % (cur_listed, cur_crossed, cur_has_minmax,
               last['listed'], last['crossed']))

    return {
        'trading_fee_rate': trading_fee_rate,
        'trading_tariff': trading_tariff,
        'clearing_fee_exchange_trade': clearing_fee_exchange_trade,
        'regimes': regimes,
    }


def _regime_for(sched, year, q):
    pick = sched['regimes'][0]
    for r in sched['regimes']:
        if (year, q) >= r['from']:
            pick = r
    return pick


# ═══════════════════════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════════════════════

def _r6(x):
    return round(x, 6)


def rows(cache_dir):
    """返回 HKEX 当前官方可得的全部季度费率行。

    每个 dict: {period, metric, value, unit, source_url}
    （company 由上层补，与其它 rates_*.py 一致的最小契约。）
    """
    docs = discover_documents(cache_dir)
    if not docs:
        raise ParseError('一份业绩公告都没发现，检查网络或 IR 站改版')

    cum = {}          # (year, nq) -> dict
    for doc in docs:
        ki = [k[0] for k in KINDS].index(doc['kind'])
        if (doc['year'], ki) < NEW_LAYOUT_FROM:
            _log('INFO 旧版式，按设计跳过 %d-%s（该累计期改从次年同类文档的'
                 '上年同期列取）' % (doc['year'], doc['kind']))
            continue
        try:
            parsed = parse_document(doc)
        except Exception as e:                            # noqa: BLE001
            _log('WARN 跳过 %d-%s: %s' % (doc['year'], doc['kind'], e))
            continue
        for key, val in parsed.items():
            # 同一 (year, nq) 可能被多份文档报告（本期 / 下一年的上年同期列）。
            # 取**发布最晚**的那份 —— 官方重述以最新为准。
            if key not in cum or val['order'] > cum[key]['order']:
                cum[key] = val

    sched = parse_fee_schedule(cache_dir)

    out = []
    for (year, q) in sorted(cum):
        cur = cum[(year, q)]
        if q == 1:
            prev = {'trading_fee': 0, 'clearing_fee': 0, 'si_fee': 0, 'trading_days': 0}
        else:
            prev = cum.get((year, q - 1))
            if prev is None:
                _log('WARN %d-Q%d 缺上一累计期，跳过' % (year, q))
                continue

        tf = cur['trading_fee'] - prev['trading_fee']
        cf = cur['clearing_fee'] - prev['clearing_fee']
        si = cur['si_fee'] - prev['si_fee']
        td = cur['trading_days'] - prev['trading_days']
        adt = cur['adt']
        src = cur['source']
        period = '%d-Q%d' % (year, q)

        if td <= 0 or adt <= 0:
            _log('WARN %s 交易日/ADT 异常 (td=%s adt=%s)，跳过' % (period, td, adt))
            continue
        if min(tf, cf, si) < 0:
            _log('WARN %s 差分出负数 (tf=%s cf=%s si=%s)，跳过' % (period, tf, cf, si))
            continue

        turnover_mn = adt * td * 1000.0          # HKD_bn * days -> HKD_mn
        tf_both = tf / turnover_mn * 100.0
        cf_both = cf / turnover_mn * 100.0

        add = lambda m, v, u, s=src: out.append(          # noqa: E731
            {'period': period, 'metric': m, 'value': v, 'unit': u, 'source_url': s})

        add('adt_equity_products', adt, 'HKD_bn')
        add('trading_days', td, 'days')
        add('cash_seg_trading_fee_revenue', tf, 'HKD_mn')
        add('cash_seg_clearing_fee_revenue', cf, 'HKD_mn')
        add('cash_seg_si_fee_revenue', si, 'HKD_mn')
        add('trading_fee_effective_rate_both_sides', _r6(tf_both), 'pct_of_turnover')
        add('trading_fee_effective_rate_per_side', _r6(tf_both / 2), 'pct_of_consideration')
        add('clearing_fee_effective_rate_both_sides', _r6(cf_both), 'pct_of_turnover')
        add('clearing_fee_effective_rate_per_side', _r6(cf_both / 2), 'pct_of_gross_value')

        add('trading_fee_listed_rate_per_side', sched['trading_fee_rate'],
            'pct_of_consideration', FEE_PAGE_URL)
        add('trading_tariff_per_side', sched['trading_tariff'],
            'HKD_per_side_per_trade', FEE_PAGE_URL)
        add('stock_clearing_fee_exchange_trade', sched['clearing_fee_exchange_trade'],
            'HKD', SEC21_URL)

        reg = _regime_for(sched, year, q)
        add('stock_settlement_fee_listed_rate_per_side', reg['listed'],
            'pct_of_gross_value', reg['source'])
        add('stock_settlement_fee_crossed_trade_per_side', reg['crossed'],
            'pct_of_gross_value', reg['source'])
        add('stock_settlement_fee_min_per_trade', reg['min'],
            reg['min_unit'], reg['source'])
        add('stock_settlement_fee_max_per_trade', reg['max'],
            reg['max_unit'], reg['source'])

    return out


VERIFICATION_NOTES = """
2026-08-05 与 series/fee_rates.csv 现有 HKEX 行逐条对账（78 行，5 期）：
    metric 名集合完全一致，unit 逐行一致，缺失 0 行，73/78 值完全相同。
    5 处不一致全部来自同一个根因，且**是 CSV 那边算法有偏差，不是解析错**：

    2025-Q4 adt_equity_products         CSV 209.7   本模块 209.9
    2025-Q4 trading_fee_eff_both_sides  CSV 0.009709 本模块 0.0097
    2025-Q4 trading_fee_eff_per_side    CSV 0.004855 本模块 0.00485
    2025-Q4 clearing_fee_eff_both_sides CSV 0.006582 本模块 0.006576
    2025-Q4 clearing_fee_eff_per_side   CSV 0.003291 本模块 0.003288

    2025 年报（www1.hkexnews.hk/.../2026022600166.pdf）里 Q4 单季 ADT
    **两处**都白纸黑字写着 209.9：
        "Comparison of Q4 2025 with Q4 2024 Results" → 209.9 / 171.5 / 22%
        "Comparison of Q4 2025 with Q3 2025 Results" → 209.9 / 267.9
    209.7 是拿年度和九个月差分出来的：
        FY 231.5×246 − 9M 238.7×185 = 12,789.5 ; /61 = 209.66 → 209.7
    ADT 是日均、且官方只给 1 位小数，差分必然放大舍入误差 0.2。
    费率差异纯粹是这 0.2 传导过去的（1242/(209.9×61×1000)×100 = 0.0097）。
    ⇒ 不是官方重述，是差分口径。本模块一律取官方直接披露的单季 ADT。

新增（CSV 里没有、本模块给出）：
    2025-Q3 cash_seg_si_fee_revenue = 181  （9M 474 − 1H 293）
    2025-Q4 cash_seg_si_fee_revenue = 160  （FY 634 − 9M 474）
    交叉核对：1H 293 = Q1 143 + Q2 150，与 CSV 已有的 Q1/Q2 SI 完全吻合。
    另新增 2023-Q4 / 2024-Q1..Q4 共 5 个季度（80 行）。

重述检测（同一累计期被两份文档报告过的，逐项比对）：
    2024 前三季累计  2024-Q3 vs 2025-Q3 : tf/cf/si/td/adt 全同
    2024 全年累计    2024-Annual vs 2025-Annual : 全同
    2025 一季累计    2025-Q1 vs 2026-Q1 : 全同
    ⇒ 当前窗口内官方**没有**重述过现金分部的费用拆分。

source_url 与 CSV 的差别（值不受影响，仅出处）：
    CSV 用 hkex.com.hk 的新闻稿镜像（后缀 _e / _eng 随机），本模块用 IR
    跳转解析出的 canonical 公告 PDF —— 即实际下载并解析的那一份。
    结算费改制前费率，CSV 挂在通函干净版（那份只有改制后的数字），
    本模块改挂规则改字稿 markup 版（划线原文里能看到 0.0020% / 0.001% /
    min HK$2 / max HK$100），值一致，出处修对。
"""


if __name__ == '__main__':
    import sys
    _cache = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          'cache')
    rs = rows(_cache)
    periods = sorted({r['period'] for r in rs})
    _log('%d rows, %d periods: %s' % (len(rs), len(periods), ' '.join(periods)))
    for r in rs:
        sys.stdout.write('HKEX,%s,%s,%s,%s,%s\n' % (
            r['period'], r['metric'], r['value'], r['unit'], r['source_url']))
