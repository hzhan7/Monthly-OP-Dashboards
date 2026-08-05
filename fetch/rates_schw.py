# -*- coding: utf-8 -*-
"""Charles Schwab (SCHW) —— 季度费率（净利息口径）解析器。

series/fee_rates.csv 里 SCHW 的 5 个 metric 全部来自**同一张表**：季度业绩新闻稿
（8-K Ex-99.1）里的 "Net Interest Revenue Information"。本模块把那张表解析出来。

================================ 数据源 ================================
唯一真源是 SEC EDGAR，全程官方 JSON API + Archives 静态文件，无登录态、无验证码：

  1) 申报清单  https://data.sec.gov/submissions/CIK0000316709.json
               （2021-05 之前的在 CIK0000316709-submissions-001.json 里，
                 靠 recent.files[] 自动发现，不硬编码）
     过滤条件：form == '8-K' 且 items 含 '2.02'（Results of Operations）。
  2) 附件清单  https://www.sec.gov/Archives/edgar/data/316709/<accession>/index.json
     从里面挑 Ex-99.1（见 _exhibit_name 的挑法，不猜文件名 —— 官方文件名 10 年换了
     5 种写法：exhibit991.htm / exhibit991093019.htm / a3q23exhibit991_093023.htm /
     schw-20161017xex99_1.htm / d758923dex991.htm，任何硬编码规则都会挂）。
  3) 正文     同目录下那个 htm，1MB 左右，直接解析 <table>。

UA 必须带邮箱，否则 EDGAR 403。请求之间限速，403/503/429 退避重试。

—— 为什么不用别的源 ——
· content.schwab.com 的季报 xlsx（fetch/schw.py 在用的那个）里**没有**这张表：
  它只有 "ER SMART" 那类经营指标页，没有平均余额/收益率。
· 10-Q 里有同样的表，但 10-Q 比 8-K 晚发好几周，且 Q4 没有 10-Q（要等 10-K），
  用 8-K 覆盖面最全、最快。

================================ 口径坑 ================================
1. **一份申报能读出两个季度**：表里第一块是本季、第二块是**去年同季**（还有两块是
   年初至今，本模块不用）。去年同季那块就是官方的「最新说法」，跟当年原报的数字
   对不上就是**重述**。本模块把两块都解析，差异记进 RESTATEMENTS，但 rows() 返回的
   **仍是各季自己那份申报的原报值** —— 理由见下面「返回哪个值」。
2. **重述是真实存在的**，不是解析错。已实测：2026-Q2 申报把 2025-Q2 的
   avg_interest_earning_assets 从 422,729 改成 421,845、net_interest_margin 从
   2.65 改成 2.66。Schwab 每隔几年会调整 "Total interest-earning assets" 里
   证券出借/其它利息收入的归类，导致往期平均余额被重算。
3. **"Total interest-earning assets" 在表里出现两次**：一次是六个明细行的小计
   （对应「利息收入」口径的收益率），一次是加上证券出借与其它利息收入后的合计
   （对应总收益率）。两次的 Average Balance **数值相同**，CSV 取的就是这个余额，
   所以取第一次出现即可；本模块额外断言两次余额相等，不等就抛。
4. **行标签改过名**：2015-Q2 以前融资端那行叫 "Deposits from banking clients"，
   之后叫 "Bank deposits"。同一个 line item 改名而已，_DEPOSIT_LABELS 里两个都认。
   标签尾部的脚注号 "(1)" "(1,2)" 每期都在变，一律先剥掉再比。
5. **百分号有两种写法**：2017-Q1 以前是 "1.76%" 粘在数字里，之后是 "1.76" + 独立
   的 "%" 单元格。_numbers() 两种都吃。
6. **单位就是 CSV 里写的那个**，没有换算：金额行本来就是 $mn（表头 "In millions"），
   收益率/NIM 本来就是年化百分数。所以不做任何缩放 —— 一旦官方改成 $bn，量级断言
   会立刻炸，而不是静默算错。
7. 2015-Q1 的业绩 8-K 在 EDGAR 上**没有 2.02 条目**（官方漏标）。这类缺口由「下一年
   同季申报的去年同季块」补上，source_url 指向真正用到的那份文件，不伪造。

================================ 返回哪个值 ================================
rows() 对每个季度返回**该季自己那份 8-K Ex-99.1 的原报值**，source_url 指向该文件。
这跟 series/fee_rates.csv 现有 12 行的构造方式一致（已逐值核对），所以并进去不会
让老行凭空跳变。官方后来的重述不丢：全在 RESTATEMENTS 里，值、两个 URL、差多少都有，
由上层决定要不要采信。

================================ 落盘 ================================
只写 <cache_dir>/schw_rates/，文件名一律带 accession 前缀 —— 官方老申报里一堆同名的
dex991.htm，不加前缀会互相覆盖（踩过：2010-2011 五个季度全被覆盖成同一份）。
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from html import unescape

CIK = 316709
CIK10 = f'CIK{CIK:010d}'
SUBMISSIONS = f'https://data.sec.gov/submissions/{CIK10}.json'
ARCHIVES = f'https://www.sec.gov/Archives/edgar/data/{CIK}'

# EDGAR 要求 UA 带可联系邮箱，否则 403。
_UA = 'hzhan7@gmail.com monthly-op-dashboards (SCHW quarterly rate parser)'

# 只回溯到这个申报日。EDGAR 上 SCHW 的业绩 8-K 能追到 1990 年代，但 2013 年及更早的
# 新闻稿版式没有逐份核对过，不纳入无人值守路径。2014-01-16 起（= 2013-Q4）到今天的
# 每一份都实测解析通过，并用「下一年同季申报的去年同季块」做过跨年互校。
EARLIEST_FILING_DATE = '2014-01-01'

CACHE_SUBDIR = 'schw_rates'

# ── metric 规格：名字与单位必须和 series/fee_rates.csv 里 SCHW 现有行逐字一致 ──
# (metric, unit, 取值来源)
M_DEPOSITS = 'avg_bank_deposits'              # USD_mn
M_IEA = 'avg_interest_earning_assets'         # USD_mn
M_DEP_RATE = 'bank_deposits_rate_paid'        # pct_annualized
M_NIM = 'net_interest_margin'                 # pct_annualized
M_NIR = 'net_interest_revenue'                # USD_mn
UNITS = {
    M_DEPOSITS: 'USD_mn',
    M_IEA: 'USD_mn',
    M_DEP_RATE: 'pct_annualized',
    M_NIM: 'pct_annualized',
    M_NIR: 'USD_mn',
}
METRICS = [M_DEPOSITS, M_IEA, M_DEP_RATE, M_NIM, M_NIR]

# 合理量级断言：不是为了「好看」，是为了在官方换单位（$mn→$bn）或版式错位时立刻炸。
_SANE = {
    M_DEPOSITS: (10_000.0, 2_000_000.0),      # $mn
    M_IEA: (50_000.0, 5_000_000.0),           # $mn
    M_DEP_RATE: (0.0, 15.0),                  # 年化 %
    M_NIM: (0.3, 10.0),                       # 年化 %
    M_NIR: (100.0, 50_000.0),                 # $mn
}

_IEA_LABEL = 'total interest-earning assets'
_NIR_LABEL = 'net interest revenue'
_DEPOSIT_LABELS = ('bank deposits', 'deposits from banking clients')

_MONTHS = {'january': 1, 'february': 2, 'march': 3, 'april': 4, 'may': 5, 'june': 6,
           'july': 7, 'august': 8, 'september': 9, 'october': 10, 'november': 11,
           'december': 12}
_QEND = {3: 1, 6: 2, 9: 3, 12: 4}

# 上一次 rows() 发现的官方重述：(period, metric, 原报值, 重述值, 原报URL, 重述URL)
RESTATEMENTS: list[tuple] = []


class FetchError(RuntimeError):
    """抓不到 / 解析不出 / 数值不合理，一律抛这个，绝不静默降级或写 NaN。"""


# ── HTTP ───────────────────────────────────────────────────────────────
_last_call = [0.0]


def _get(url: str, timeout: int = 60) -> bytes:
    """带限速与退避的 GET。EDGAR 建议 <10 req/s，这里压到 ~5 req/s。"""
    for attempt in range(5):
        wait = 0.2 - (time.time() - _last_call[0])
        if wait > 0:
            time.sleep(wait)
        _last_call[0] = time.time()
        req = urllib.request.Request(url, headers={
            'User-Agent': _UA,
            'Accept-Encoding': 'gzip, deflate',
            'Accept': '*/*',
        })
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read()
                if r.headers.get('Content-Encoding') == 'gzip':
                    import gzip
                    raw = gzip.decompress(raw)
                return raw
        except urllib.error.HTTPError as e:
            if e.code in (403, 429, 503) and attempt < 4:
                time.sleep(1.5 * (attempt + 1))
                continue
            raise FetchError(f'HTTP {e.code} on {url}') from e
        except Exception as e:
            if attempt < 4:
                time.sleep(1.5 * (attempt + 1))
                continue
            raise FetchError(f'{type(e).__name__} on {url}: {e}') from e
    raise FetchError(f'重试 5 次仍失败：{url}')


def _cache_path(cache_dir, name: str) -> str:
    d = os.path.join(cache_dir, CACHE_SUBDIR)
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, name)


def _fetch(url: str, cache_dir, name: str, immutable: bool = True) -> bytes:
    """immutable=True 的走缓存（EDGAR Archives 里的历史申报永不变）；
    申报清单每天都在变，immutable=False 强制重取。"""
    p = _cache_path(cache_dir, name)
    if immutable and os.path.exists(p) and os.path.getsize(p) > 200:
        with open(p, 'rb') as f:
            return f.read()
    blob = _get(url)
    with open(p, 'wb') as f:
        f.write(blob)
    return blob


# ── 申报清单 ───────────────────────────────────────────────────────────
def _earnings_filings(cache_dir) -> list[dict]:
    """返回 [{'accession','date','primary'}, ...]，按申报日倒序（新→旧）。

    只认 form=8-K 且 items 含 2.02。历史分片文件名从 recent.files[] 里读，不硬编码。
    """
    top = json.loads(_fetch(SUBMISSIONS, cache_dir, 'submissions.json', immutable=False))
    blocks = [top['filings']['recent']]
    for f in top['filings'].get('files', []):
        # 分片是「早于某日的历史」，早到不需要就别下
        if f.get('filingTo', '9999') < EARLIEST_FILING_DATE:
            continue
        blocks.append(json.loads(_fetch(
            f'https://data.sec.gov/submissions/{f["name"]}', cache_dir, f['name'])))

    out = []
    for b in blocks:
        for i in range(len(b['form'])):
            if b['form'][i] != '8-K':
                continue
            if '2.02' not in (b['items'][i] or ''):
                continue
            if b['filingDate'][i] < EARLIEST_FILING_DATE:
                continue
            out.append({'accession': b['accessionNumber'][i],
                        'date': b['filingDate'][i],
                        'primary': (b.get('primaryDocument') or [''] * (i + 1))[i]})
    if not out:
        raise FetchError('EDGAR 上没找到任何 item 2.02 的 8-K，CIK 或 API 形态可能变了')
    out.sort(key=lambda r: (r['date'], r['accession']), reverse=True)
    return out


def _exhibit_name(cache_dir, accession: str, primary: str) -> str:
    """从 index.json 里挑出业绩新闻稿正文（Ex-99.1）。

    官方文件名 10 年换了 5 种写法，所以不按名字猜，按「排除法 + 体积」挑：
    去掉索引页、XBRL 渲染出来的 R*.htm、8-K 壳（primaryDocument），
    剩下的 .htm 里最大的那个就是新闻稿（1MB 级，别的都是 KB 级）。
    挑完还要能解析出 NIR 表，解析不出会在上层抛错，所以挑错了不会静默。
    """
    accn = accession.replace('-', '')
    idx = json.loads(_fetch(f'{ARCHIVES}/{accn}/index.json', cache_dir, f'{accn}_index.json'))
    best, best_size = None, -1
    for item in idx['directory']['item']:
        name = item['name']
        low = name.lower()
        if not low.endswith(('.htm', '.html')):
            continue
        if 'index' in low or re.fullmatch(r'r\d+\.htm', low) or low == primary.lower():
            continue
        try:
            size = int(item.get('size') or 0)
        except (TypeError, ValueError):
            size = 0
        if size > best_size:
            best, best_size = name, size
    if best is None:
        raise FetchError(f'{accession}: index.json 里没有可用的 htm 附件')
    return best


# ── HTML 表格 ──────────────────────────────────────────────────────────
def _table_rows(table_html: str) -> list[list[str]]:
    rows = []
    for tr in re.findall(r'<tr.*?</tr>', table_html, re.S | re.I):
        cells = []
        for td in re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', tr, re.S | re.I):
            v = unescape(re.sub(r'<[^>]+>', ' ', td))
            v = v.replace('﻿', '').replace('\xa0', ' ')
            v = re.sub(r'\s+', ' ', v).strip()
            if v:
                cells.append(v)
        if cells:
            rows.append(cells)
    return rows


_NUM_RE = re.compile(r'^\(?-?[\d,]+(?:\.\d+)?\)?%?$')


def _numbers(cells: list[str]) -> list[float]:
    """把一行里的数值按出现顺序取出来（跳过标签、$、%、空档）。

    百分号两种写法都吃：独立的 '%' 单元格直接跳过，'1.76%' 这种剥掉再转。
    括号是负数。
    """
    out = []
    for c in cells[1:]:
        c = c.strip()
        if c in ('$', '%', '—', '–', '-', ''):
            continue
        if not _NUM_RE.match(c):
            continue
        c = c.rstrip('%')
        neg = c.startswith('(')
        out.append((-1.0 if neg else 1.0) * float(c.strip('()').replace(',', '')))
    return out


def _clean_label(cell: str) -> str:
    """剥掉尾部脚注号（"(1)" "(1,2)" "(1, 2, 3)"）与冒号，转小写。"""
    s = re.sub(r'\s*\((?:\d+\s*,?\s*)+\)\s*$', '', cell.strip())
    return s.rstrip(':').strip().lower()


def _find_nir_table(doc: str) -> str:
    """在新闻稿里定位 "Net Interest Revenue Information" 那张表。

    不按标题文字找（标题在表外，且 2016 年前后写法不同），按内容特征找：
    同时含「总生息资产」「净利息收入」「平均收益率/成本率」三样的表全文只有一张。
    """
    hits = []
    for tb in re.findall(r'<table.*?</table>', doc, re.S | re.I):
        flat = re.sub(r'\s+', ' ', unescape(re.sub(r'<[^>]+>', ' ', tb))).lower()
        if (_IEA_LABEL in flat and _NIR_LABEL in flat
                and 'average yield' in flat and 'average balance' in flat):
            hits.append(tb)
    if len(hits) != 1:
        raise FetchError(f'期望正文里恰好 1 张净利息收入表，实际 {len(hits)} 张')
    return hits[0]


def _period_of(rows: list[list[str]], filing_date: str) -> str:
    """从表头判断本季是哪一期，返回 'YYYY-Qn'。

    表头形如：['Three Months Ended June 30,', 'Six Months Ended June 30,']
              ['2026', '2025', '2026', '2025']
    2016 年前是拆成三行的（'Three Months Ended' / 'June 30,' / 年份行），
    所以把前若干行拼起来再匹配，别按行号取。
    最后拿申报日交叉验证：申报日必须落在季末后的 0-4 个月内，否则抛。
    """
    head = ' '.join(' '.join(r) for r in rows[:6])
    # 不能写成「Three Months Ended 后面紧跟月份」：2016 年前的版式是
    # 'Three Months Ended Twelve Months Ended' / 'December 31, December 31,' 拆成两行，
    # 中间隔着别的字。表头里出现的月份**全部是同一个季末日**，所以取全部再要求一致。
    found = re.findall(r'\b(' + '|'.join(_MONTHS) + r')\s+\d{1,2}\b', head, re.I)
    months = {_MONTHS[x.lower()] for x in found}
    if len(months) != 1:
        raise FetchError(f'表头里读不出唯一的季末月份（{sorted(months)}）：{head[:160]!r}')
    month = months.pop()
    if month not in _QEND:
        raise FetchError(f'季末月份不是 3/6/9/12：{month}')

    years = None
    for r in rows[:6]:
        ys = [c for c in r if re.fullmatch(r'(19|20)\d{2}', c.strip())]
        if len(ys) >= 2:
            years = [int(y) for y in ys]
            break
    if not years:
        raise FetchError(f'表头里读不出年份行：{head[:160]!r}')
    year = years[0]
    if years[1] != year - 1:
        raise FetchError(f'表头年份不是「本年, 去年」：{years[:4]}')

    fy, fm, _ = (int(x) for x in filing_date.split('-'))
    lag = (fy - year) * 12 + (fm - month)
    if not 0 <= lag <= 4:
        raise FetchError(f'季末 {year}-{month:02d} 与申报日 {filing_date} 相差 {lag} 个月，不合理')
    return f'{year}-Q{_QEND[month]}'


def _row_numbers(rows, want, per_block: int) -> list[list[float]]:
    """取出所有标签匹配、且**数值个数正好等于「区块数 × per_block」**的行。

    为什么要卡死个数而不是「至少 N 个」：官方用 '—' 表示该季无该项，而 '—' 在
    _numbers 里会被跳过，于是那一行的数值会**整体左移**，按下标 0/1/2 取就会串位。
    实测 2020-Q4 那份里 "Held to maturity securities" 就是这种残行
    （['—','—','—','136,717','870','2.53',…]，本季 3 个位置全是破折号）。
    本模块用到的三行历史上都是满的，一旦哪天不满，宁可抛也不能取到错位的数。
    区块数：Q1 的表只有「本季 / 去年同季」2 块，Q2-Q4 还多两块年初至今，共 4 块。
    """
    labels = (want,) if isinstance(want, str) else tuple(want)
    out = []
    for r in rows:
        if _clean_label(r[0]) in labels:
            n = _numbers(r)
            if len(n) in (2 * per_block, 4 * per_block):
                out.append(n)
    return out


def parse_release(doc: str, filing_date: str) -> dict:
    """解析一份业绩新闻稿正文。

    返回 {'period': 'YYYY-Qn', 'current': {metric: value}, 'prior': {metric: value},
          'prior_period': 'YYYY-Qn'}

    表的列结构是 4 个区块 × 3 列（平均余额 / 利息收支 / 平均收益率或成本率）：
      区块0 = 本季，区块1 = 去年同季，区块2/3 = 年初至今（本模块不用）。
    "Net interest revenue" 那行没有「利息收支」列，是 2 列一块（金额 / NIM）。
    """
    rows = _table_rows(_find_nir_table(doc))
    period = _period_of(rows, filing_date)
    year, q = int(period[:4]), int(period[-1])
    prior_period = f'{year - 1}-Q{q}'

    iea_rows = _row_numbers(rows, _IEA_LABEL, 3)
    if not iea_rows:
        raise FetchError(f'{period}: 找不到列数完整的 "{_IEA_LABEL}" 行')
    # 小计与合计两行的平均余额必须一致（见口径坑 3）
    for extra in iea_rows[1:]:
        for k in (0, 3):
            if abs(extra[k] - iea_rows[0][k]) > 0.5:
                raise FetchError(
                    f'{period}: "{_IEA_LABEL}" 两行的平均余额不一致 '
                    f'({iea_rows[0][k]} vs {extra[k]})，版式可能变了')
    iea = iea_rows[0]

    dep_rows = _row_numbers(rows, _DEPOSIT_LABELS, 3)
    if not dep_rows:
        raise FetchError(f'{period}: 找不到列数完整的存款行 {_DEPOSIT_LABELS}')
    dep = dep_rows[0]

    # 净利息收入那行没有「利息收支」列，一块只有 2 个数（金额 / NIM）
    nir_rows = _row_numbers(rows, _NIR_LABEL, 2)
    if not nir_rows:
        raise FetchError(f'{period}: 找不到列数完整的 "{_NIR_LABEL}" 行')
    nir = nir_rows[0]

    # 三行必须来自同一种区块数，否则说明有行残缺、下标含义已经不一致
    blocks = {len(iea) // 3, len(dep) // 3, len(nir) // 2}
    if len(blocks) != 1:
        raise FetchError(f'{period}: 三行的区块数不一致（{sorted(blocks)}），版式可能变了')

    cur = {M_IEA: iea[0], M_DEPOSITS: dep[0], M_DEP_RATE: dep[2],
           M_NIR: nir[0], M_NIM: nir[1]}
    pri = {M_IEA: iea[3], M_DEPOSITS: dep[3], M_DEP_RATE: dep[5],
           M_NIR: nir[2], M_NIM: nir[3]}
    for tag, vals in (('本季', cur), ('去年同季', pri)):
        for k, v in vals.items():
            lo, hi = _SANE[k]
            if not (lo <= v <= hi):
                raise FetchError(f'{period} {tag} {k}={v} 超出合理区间 [{lo}, {hi}]')
    return {'period': period, 'prior_period': prior_period, 'current': cur, 'prior': pri}


# ── 值的规范化：必须和 CSV 里现有写法逐字一致 ──────────────────────────
def _norm(metric: str, v: float):
    """USD_mn 是整数（CSV 里写 3357，不是 3357.0）；百分数保留两位再去掉多余的 0
    （CSV 里 3.00 写成 3.0、0.90 写成 0.9）。"""
    if UNITS[metric] == 'USD_mn':
        iv = int(round(v))
        if abs(iv - v) > 1e-6:
            raise FetchError(f'{metric}={v} 不是整数百万美元')
        return iv
    return round(v + 0.0, 2)


# ── 对外接口 ───────────────────────────────────────────────────────────
def rows(cache_dir) -> list[dict]:
    """返回 SCHW 当前官方可得的全部季度费率行。

    每个 dict: {'company','period','metric','value','unit','source_url'}
    值取「该季自己那份 8-K Ex-99.1 的原报值」；官方后来的重述不覆盖它，
    而是记进模块级 RESTATEMENTS（见文件头「返回哪个值」）。
    """
    RESTATEMENTS.clear()
    filings = _earnings_filings(cache_dir)

    primary: dict[str, dict] = {}     # period -> {'vals':…, 'url':…, 'date':…}
    prior: dict[str, dict] = {}       # period -> 最新一份提到它的「去年同季」块
    for f in filings:
        accn = f['accession'].replace('-', '')
        name = _exhibit_name(cache_dir, f['accession'], f['primary'])
        url = f'{ARCHIVES}/{accn}/{name}'
        doc = _fetch(url, cache_dir, f'{accn}_{name}').decode('utf-8', 'replace')
        try:
            p = parse_release(doc, f['date'])
        except FetchError as e:
            raise FetchError(f'{f["date"]} {f["accession"]} ({name}): {e}') from e
        if p['period'] in primary:
            raise FetchError(f'{p["period"]} 出现在两份申报里：'
                             f'{primary[p["period"]]["url"]} 与 {url}')
        primary[p['period']] = {'vals': p['current'], 'url': url, 'date': f['date']}
        # filings 是新→旧，所以第一次写入的就是最新一份提到该期的文件
        prior.setdefault(p['prior_period'], {'vals': p['prior'], 'url': url})

    # 重述对账：原报 vs 后来申报里的「去年同季」
    for period, orig in primary.items():
        later = prior.get(period)
        if not later:
            continue
        for m in METRICS:
            a, b = _norm(m, orig['vals'][m]), _norm(m, later['vals'][m])
            if a != b:
                RESTATEMENTS.append((period, m, a, b, orig['url'], later['url']))
    RESTATEMENTS.sort()

    # 输出区间 = 有原报的最早季 → 最新季。比这更早的期只有「去年同季」块能提供，
    # 是重述口径的残尾，不出。区间内不允许有洞：2015-Q1 那种官方漏标 2.02 的缺口
    # 由「去年同季」块补齐，补不上就抛，绝不悄悄少一期。
    span = sorted(primary)
    first, last = span[0], span[-1]

    def _i(p):
        return int(p[:4]) * 4 + int(p[-1])

    wanted = []
    y, q = int(first[:4]), int(first[-1])
    while _i(f'{y}-Q{q}') <= _i(last):
        wanted.append(f'{y}-Q{q}')
        q += 1
        if q > 4:
            q, y = 1, y + 1
    holes = [p for p in wanted if p not in primary and p not in prior]
    if holes:
        raise FetchError(f'{first}..{last} 区间内这些季度既无原报也无「去年同季」兜底：{holes}')

    out = []
    for period in wanted:
        src = primary.get(period) or prior[period]   # 自己那份没有就用「去年同季」块兜底
        for m in METRICS:
            out.append({
                'company': 'SCHW',
                'period': period,
                'metric': m,
                'value': _norm(m, src['vals'][m]),
                'unit': UNITS[m],
                'source_url': src['url'],
            })
    return out


def reconcile(series_dir, cache_dir) -> list[tuple]:
    """把 series/fee_rates.csv 里 SCHW 现有的每一行拿解析结果重算一遍，返回不一致清单。

    **只读**，不写 CSV。返回 [(period, metric, csv 里的值, 解析出来的值, 说明), ...]。
    说明会区分「官方重述」（原报值和 CSV 一致，只是后来的申报改了口径）与真·解析不符。
    """
    import csv as _csv
    parsed = {(r['period'], r['metric']): r for r in rows(cache_dir)}
    rest = {(p, m): (a, b, u2) for p, m, a, b, _u1, u2 in RESTATEMENTS}
    bad = []
    with open(os.path.join(series_dir, 'fee_rates.csv'), newline='') as f:
        for row in _csv.DictReader(f):
            if row['company'] != 'SCHW':
                continue
            key = (row['period'], row['metric'])
            got = parsed.get(key)
            if got is None:
                bad.append(key + (row['value'], None, '解析器覆盖不到这一期/指标'))
                continue
            note = []
            if str(got['value']) != row['value'].strip():
                note.append('值不符')
            if got['unit'] != row['unit'].strip():
                note.append(f"unit 不符（解析出 {got['unit']}）")
            if got['source_url'] != row['source_url'].strip():
                note.append('source_url 不符')
            if note:
                bad.append(key + (row['value'], str(got['value']), '；'.join(note)))
            elif key in rest:
                bad.append(key + (row['value'], str(got['value']),
                                  f'原报一致，但官方后来重述为 {rest[key][1]}（见 {rest[key][2]}）'))
    return bad


if __name__ == '__main__':
    import sys
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if '--csv' in sys.argv:
        _bad = reconcile(os.path.join(_root, 'series'), os.path.join(_root, 'cache'))
        print(f'与 series/fee_rates.csv 对账，需要关注 {len(_bad)} 条：')
        for b in _bad:
            print('  ', b)
        raise SystemExit(0)
    _rows = rows(os.path.join(_root, 'cache'))
    _periods = sorted({r['period'] for r in _rows})
    print(f'{len(_rows)} rows / {len(_periods)} periods: {_periods[0]} .. {_periods[-1]}')
    for r in _rows[-10:]:
        print(' ', r['period'], r['metric'], r['value'], r['unit'])
    print(f'官方重述 {len(RESTATEMENTS)} 条：')
    for r in RESTATEMENTS:
        print('  ', r[0], r[1], f'{r[2]} -> {r[3]}')
