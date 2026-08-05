# -*- coding: utf-8 -*-
"""CME Group (CME) 季度 RPC（average rate per contract）解析器 —— series/fee_rates.csv 的 CME 部分。

────────────────────────────────────────────────────────────────────────────
源
────────────────────────────────────────────────────────────────────────────
  SEC EDGAR，CIK 0001156375。每季财报当天 CME 报一份 8-K（Item 2.02），
  正文的 EX-99.1 就是收益新闻稿，稿末「Quarterly Average Rate Per Contract (RPC)」
  一表给出**最近 5 个季度**的分品种 RPC。这是 RPC 的唯一官方一手披露口径 ——
  10-Q/10-K 里没有这张表，XBRL 里也没有（RPC 不是 GAAP 项，未打标签），
  所以只能解析新闻稿 HTML，没有更「结构化」的捷径可走。

  走的都是官方无鉴权端点，无需登录态 / 无验证码：
    https://data.sec.gov/submissions/CIK0001156375.json      （+ 分卷 files[]）
    https://www.sec.gov/Archives/edgar/data/1156375/<acc>/<acc>-index-headers.html
    https://www.sec.gov/Archives/edgar/data/1156375/<acc>/<EX-99.1 文件名>
  SEC 要求 User-Agent 带联系邮箱，见 _UA；不带会被 403。

────────────────────────────────────────────────────────────────────────────
口径坑
────────────────────────────────────────────────────────────────────────────
1. **EX-99.1 的文件名每季都变，且变得毫无规律，绝对不要猜。**
   实际出现过 exhibit9916302026.htm / exhibit99133121.htm / exhibit991123120.htm /
   d133311dex991.htm（2016-Q4、2017-Q2、2017-Q3 换过申报代理，名字完全不同系列）。
   唯一可靠的拿法是读该 accession 的 index-headers.html，从 SGML 头里按
   <TYPE>EX-99.1 找 <FILENAME>。本模块就是这么做的。

2. **一份新闻稿盖 5 个季度，所以同一个 (period, metric) 会被 5 份文件各报一次。**
   这正是「官方重述」能被发现的地方：merge 时**后申报的覆盖先申报的**
   （见 rows() 的 latest-filing-wins），并且 disclosures() 保留全部原始记录，
   让上层能自己判断某个数是被改过还是解析错了。实测 2014-Q2 至今
   所有重叠期次的 RPC 完全一致 —— CME 迄今没重述过 RPC，但别把这当成保证。

3. **品种标签在 2019 年前后改过名，metric 名不能跟着源文件走。**
   2014-2018 用 Interest rate / Equity / Agricultural commodity / Metal（单数），
   2019 起改成 Interest rates / Equity indexes / Agricultural commodities / Metals。
   series/fee_rates.csv 的 metric 名是按**新名**定的（rpc_interest_rates 等），
   _LABELS 把新旧两套都映射到同一个 metric —— 改这里等于凭空造出新指标，
   老指标从此不再更新（上层按 (company, period, metric) 三元组合并）。

4. **同一页上有三张表头长得一模一样的表**（Trading Days / 分品种 ADV / 分品种 RPC），
   表头都是 ['Product Line', '2Q 2025', …]。只能靠表内是否有 'Average RPC'
   这一行来认 RPC 表 —— 按表序号（第 7 张）硬编会在换排版时静默取到 ADV 表，
   而 ADV 是四位数、RPC 是零点几，一旦取错图会直接爆表。
   实测 2014-Q2 起 44 份新闻稿里 'Average RPC' 每份恰好出现 1 次。

5. **RPC 表格里 '$' 是独立单元格，还有大量空白占位格。**
   HTML 是 inline-table 排版，一行的单元格数在 6 到 21 之间浮动。
   解析必须「过滤空格与 $ 之后按顺序取数字」，数字个数必须与表头季度数严格相等，
   不等就抛错 —— 不许按列下标硬对齐。

6. **只回溯到 2014-Q2 的新闻稿。**
   更早的 8-K（2013 及以前，多数由 RR Donnelley 代申报）在 Archives 里
   没有 index-headers.html（404），拿不到 EX-99.1 的文件名。硬要更早的数据
   得换成解析 .txt 全文，收益（2013 年及以前的 RPC）与风险不成正比，故不做。
   当前可得区间：2013-Q2（2014-Q2 新闻稿的最左一列）至最新一季。

7. **脚注口径：ADV 与 RPC 只含期货与期货期权**（'ADV and RPC includes futures and
   options on futures only.'），不含现金/OTC。2020 年前的新闻稿没有这条脚注，
   但表本身口径一致。

────────────────────────────────────────────────────────────────────────────
接口
────────────────────────────────────────────────────────────────────────────
  rows(cache_dir) -> list[dict]      每季每品种一条，latest-filing-wins
  disclosures(cache_dir) -> list[dict]  全部原始披露（含被覆盖的），供查重述
  verify(series_dir, cache_dir)      与 series/fee_rates.csv 现有 CME 行逐条对账
"""
from __future__ import annotations

import html as _html
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

COMPANY = 'CME'
CIK = 1156375
CIK10 = f'{CIK:010d}'

# SEC 要求 UA 带联系邮箱，否则 403。
_UA = 'monthly-op-dashboards CME rates fetcher (hzhan7@gmail.com)'
_ARCHIVE = 'https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{fn}'
_SUBMISSIONS = 'https://data.sec.gov/submissions/CIK{cik10}.json'

# 坑 6：更早的申报拿不到 index-headers.html。
MIN_FILING_DATE = '2014-01-01'

UNIT = 'USD_per_contract'

# 坑 3：新旧标签都要认，metric 名固定用 series/fee_rates.csv 现有写法。
_LABELS = {
    'interest rate': 'rpc_interest_rates',
    'interest rates': 'rpc_interest_rates',
    'equity': 'rpc_equity_indexes',
    'equities': 'rpc_equity_indexes',
    'equity index': 'rpc_equity_indexes',
    'equity indexes': 'rpc_equity_indexes',
    'foreign exchange': 'rpc_foreign_exchange',
    'energy': 'rpc_energy',
    'agricultural commodity': 'rpc_agricultural',
    'agricultural commodities': 'rpc_agricultural',
    'agricultural': 'rpc_agricultural',
    'metal': 'rpc_metals',
    'metals': 'rpc_metals',
    'average rpc': 'rpc_total',
}
METRICS = sorted(set(_LABELS.values()))

_QUARTER = re.compile(r'^([1-4])Q\s*[’\']?\s*(\d{2}|\d{4})$')


class FetchError(RuntimeError):
    """源不可达 / 结构变了 / 数值对不齐 —— 一律显式抛，绝不静默返回半截数据。"""


# ── HTTP ────────────────────────────────────────────────────────────────────
def _fetch(url, dest, max_age_hours=None, retries=4):
    """下载到 dest 并返回 bytes。max_age_hours=None 表示「一旦落盘就永不重下」。

    EDGAR 的 Archives 文件是不可变的（申报一旦公开就不会改内容），所以正文
    永久缓存；只有 submissions JSON 需要按时效刷新。
    """
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        if max_age_hours is None:
            return open(dest, 'rb').read()
        age = (time.time() - os.path.getmtime(dest)) / 3600.0
        if age < max_age_hours:
            return open(dest, 'rb').read()

    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={
                'User-Agent': _UA,
                'Accept-Encoding': 'gzip, deflate',
                'Host': urllib.parse.urlsplit(url).netloc,
            })
            with urllib.request.urlopen(req, timeout=60) as r:
                blob = r.read()
                if (r.headers.get('Content-Encoding') or '') == 'gzip':
                    import gzip
                    blob = gzip.decompress(blob)
            # SEC 限速 10 req/s，这里放慢到 ~3 req/s，无人值守跑不至于被封。
            time.sleep(0.3)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, 'wb') as f:
                f.write(blob)
            return blob
        except urllib.error.HTTPError as e:
            last = e
            if e.code == 404:
                raise FetchError(f'404 {url}') from e
            time.sleep(2 + 3 * attempt)
        except Exception as e:                                    # noqa: BLE001
            last = e
            time.sleep(2 + 3 * attempt)
    raise FetchError(f'下载失败 {url}: {last!r}')


def _cache(cache_dir):
    d = os.path.join(cache_dir, 'cme_rates')
    os.makedirs(d, exist_ok=True)
    return d


# ── EDGAR 申报清单 ──────────────────────────────────────────────────────────
def earnings_8ks(cache_dir, min_date=MIN_FILING_DATE):
    """返回 [(filing_date, accession)]，按时间升序；只取 Item 2.02 的 8-K。

    submissions JSON 分卷：filings.recent 只装最近 1000 条，更早的在
    filings.files[] 里，必须一起读，否则 2018-06 以前的季度全部丢失。
    """
    d = _cache(cache_dir)
    blob = _fetch(_SUBMISSIONS.format(cik10=CIK10),
                  os.path.join(d, 'submissions.json'), max_age_hours=6.0)
    subs = json.loads(blob)

    chunks = [subs['filings']['recent']]
    for f in subs['filings'].get('files', []):
        if f.get('filingTo', '9999') < min_date:
            continue
        b = _fetch(f'https://data.sec.gov/submissions/{f["name"]}',
                   os.path.join(d, f['name']), max_age_hours=24 * 30)
        chunks.append(json.loads(b))

    out = []
    for r in chunks:
        for i, form in enumerate(r['form']):
            if form != '8-K':
                continue
            if '2.02' not in (r['items'][i] or ''):
                continue
            fd = r['filingDate'][i]
            if fd < min_date:
                continue
            out.append((fd, r['accessionNumber'][i]))
    if not out:
        raise FetchError('EDGAR 里一份 Item 2.02 的 8-K 都没找到，submissions 结构可能变了')
    return sorted(set(out))


def _ex991_name(cache_dir, acc):
    """坑 1：EX-99.1 的文件名只能从 SGML 头里读，不能猜。拿不到返回 None。"""
    nod = acc.replace('-', '')
    dest = os.path.join(_cache(cache_dir), f'hdr_{acc}.html')
    try:
        blob = _fetch(_ARCHIVE.format(cik=CIK, acc=nod, fn=f'{acc}-index-headers.html'), dest)
    except FetchError:
        return None
    txt = re.sub(r'<[^>]+>', '', blob.decode('utf-8', 'replace'))
    txt = txt.replace('&lt;', '<').replace('&gt;', '>')
    for ty, fn in re.findall(r'<TYPE>([^\n<]+).*?<FILENAME>([^\n<]+)', txt, re.S):
        if ty.strip().upper().startswith('EX-99.1'):
            return fn.strip()
    return None


# ── HTML 表格解析 ───────────────────────────────────────────────────────────
def _cells(tr):
    out = []
    for cell in re.findall(r'<t[dh]\b[^>]*>(.*?)</t[dh]>', tr, re.S | re.I):
        t = re.sub(r'<[^>]+>', ' ', cell)
        t = _html.unescape(t).replace('\xa0', ' ')
        out.append(re.sub(r'\s+', ' ', t).strip())
    return out


def _table_rows(tbl):
    return [_cells(tr) for tr in re.findall(r'<tr\b.*?</tr>', tbl, re.S | re.I)]


def _period(label):
    m = _QUARTER.match(label)
    if not m:
        return None
    q, y = m.group(1), m.group(2)
    y = int(y) + 2000 if len(y) == 2 else int(y)
    return f'{y}-Q{q}'


def _num(tok):
    t = tok.replace('$', '').replace(',', '').strip()
    neg = t.startswith('(') and t.endswith(')')
    t = t.strip('()')
    if not t or not re.match(r'^-?\d*\.?\d+$', t):
        return None
    v = float(t)
    return -v if neg else v


def parse_release(htm, source_url):
    """从一份 EX-99.1 新闻稿里解析出 RPC 表。

    返回 {period: {metric: value}}；整篇压根没有 'Average RPC' 字样（说明这份
    Item 2.02 的 8-K 不是季度财报稿）时返回 None —— 调用方跳过即可。
    但只要出现了 'Average RPC' 而表结构对不上，一律抛 FetchError：
    「静默跳过」和「排版变了」必须区分，否则改版当天会安静地少一整季数据。
    """
    plain = re.sub(r'<[^>]+>', ' ', htm)
    plain = _html.unescape(plain).replace('\xa0', ' ')
    if 'average rpc' not in re.sub(r'\s+', ' ', plain).lower():
        return None

    tables = re.findall(r'<table\b.*?</table>', htm, re.S | re.I)
    hit = None
    for tbl in tables:
        rs = _table_rows(tbl)
        flat = ' '.join(c for r in rs for c in r).lower()
        # 坑 4：三张表表头一样，只能靠 'Average RPC' 这行认 RPC 表。
        if 'average rpc' not in flat:
            continue
        hit = rs
        break
    if hit is None:
        raise FetchError(f'{source_url}: 正文有 "Average RPC" 却不在任何 <table> 里，排版变了')

    periods = None
    for r in hit:
        ps = [_period(c) for c in r if c]
        ps = [p for p in ps if p]
        if len(ps) >= 2:
            periods = ps
            break
    if not periods:
        raise FetchError(f'{source_url}: RPC 表里认不出季度表头')

    out = {p: {} for p in periods}
    seen = set()
    for r in hit:
        nz = [c for c in r if c]
        if not nz:
            continue
        key = re.sub(r'\s+', ' ', nz[0].strip().rstrip('*').rstrip(':')).lower()
        key = re.sub(r'\(\d\)$', '', key).strip()
        metric = _LABELS.get(key)
        if metric is None:
            continue
        # 坑 5：'$' 独立成格、空格一堆，只能顺序取数字再校验个数。
        vals = [v for v in (_num(c) for c in nz[1:]) if v is not None]
        if len(vals) != len(periods):
            raise FetchError(
                f'{source_url}: 行 {nz[0]!r} 取到 {len(vals)} 个数字，'
                f'表头却有 {len(periods)} 个季度 —— 拒绝猜测对齐')
        # RPC 是零点几到两块钱之间；四位数说明认错成 ADV 表了（坑 4）。
        if any(v <= 0 or v > 10 for v in vals):
            raise FetchError(f'{source_url}: 行 {nz[0]!r} 数值 {vals} 不像 RPC，疑似取到 ADV 表')
        for p, v in zip(periods, vals):
            out[p][metric] = v
        seen.add(metric)

    missing = set(METRICS) - seen
    if missing:
        raise FetchError(f'{source_url}: RPC 表缺 metric {sorted(missing)}')
    return out


# ── 对外接口 ────────────────────────────────────────────────────────────────
def disclosures(cache_dir, min_date=MIN_FILING_DATE):
    """全部原始披露记录（含被后续申报覆盖的旧版），按申报时间升序。

    每条: {period, metric, value, unit, source_url, filing_date, accession}
    """
    out = []
    newest_ok = False
    filings = earnings_8ks(cache_dir, min_date)
    for i, (fd, acc) in enumerate(filings):
        fn = _ex991_name(cache_dir, acc)
        if fn is None:
            continue                     # 坑 6：老申报没有 SGML 头页，跳过
        nod = acc.replace('-', '')
        url = _ARCHIVE.format(cik=CIK, acc=nod, fn=fn)
        blob = _fetch(url, os.path.join(_cache(cache_dir), f'ex991_{acc}_{fn}'))
        rec = parse_release(blob.decode('utf-8', 'replace'), url)
        if rec is None:
            continue                     # 这份 2.02 不是季度财报稿
        if i == len(filings) - 1:
            newest_ok = True
        for period, d in rec.items():
            for metric, value in d.items():
                out.append({
                    'period': period, 'metric': metric, 'value': value,
                    'unit': UNIT, 'source_url': url,
                    'filing_date': fd, 'accession': acc,
                })
    if not out:
        raise FetchError('一条 RPC 都没解析出来')
    if not newest_ok:
        # 最新一份 Item 2.02 的 8-K 没吐出 RPC —— 要么 CME 改了披露方式，
        # 要么解析器该修了。不抛的话上层只会看到「数据停在上一季」，
        # 和现在 fee_rates.csv 冻在 2026-Q2 是同一种无声失效。
        raise FetchError(
            f'最新的 Item 2.02 8-K {filings[-1][1]}（{filings[-1][0]}）里没解析出 RPC 表 —— '
            f'披露口径或排版可能变了，拒绝返回一份「看起来正常但少最新一季」的结果')
    return out


def rows(cache_dir) -> list:
    """当前官方可得的**全部**季度 RPC，每条 dict 含 period/metric/value/unit/source_url。

    同一 (period, metric) 会被 5 份新闻稿各报一次（坑 2），取值与取 URL 用两条规则：

    * **值**：以**最新**申报为准 —— 官方若重述，重述值胜出。
    * **source_url**：指向「首次发布这个现行值」的那份新闻稿，而不是最新那份。
      没有重述时，这就是该季度自己的那份财报新闻稿（2026-Q2 ← 6/30/2026 的稿），
      语义最直观，而且**季度间稳定**：否则每出一季财报，前 4 个季度的 source_url
      都会跟着挪到新稿上，CSV 每季平白多出 28 行「值没变、URL 变了」的 diff。
      一旦真的重述，URL 会自动挪到重述它的那份稿上 —— 值和出处始终对得上。
    """
    hist = {}
    for r in disclosures(cache_dir):
        hist.setdefault((r['period'], r['metric']), []).append(r)

    out = []
    for k, recs in hist.items():
        recs.sort(key=lambda r: (r['filing_date'], r['accession']))
        in_force = recs[-1]['value']
        first = recs[-1]
        for r in reversed(recs):              # 回溯到该值连续出现的最早一份
            if r['value'] != in_force:
                break
            first = r
        out.append({'period': k[0], 'metric': k[1], 'value': in_force,
                    'unit': UNIT, 'source_url': first['source_url']})
    out.sort(key=lambda r: (r['period'], r['metric']))
    return out


def restatements(cache_dir):
    """同一 (period, metric) 在不同新闻稿里给出不同值的情况（= 官方重述）。

    返回 [(period, metric, [(filing_date, value, url), ...])]，只列有分歧的。
    """
    hist = {}
    for r in disclosures(cache_dir):
        hist.setdefault((r['period'], r['metric']), []).append(
            (r['filing_date'], r['value'], r['source_url']))
    out = []
    for k, v in sorted(hist.items()):
        if len({x[1] for x in v}) > 1:
            out.append((k[0], k[1], sorted(v)))
    return out


def verify(series_dir, cache_dir):
    """与 series/fee_rates.csv 现有 CME 行逐条对账（只读，不写 CSV）。

    返回 dict: matched / value_mismatch / missing_in_source / source_url_changed。
    """
    import csv
    path = os.path.join(series_dir, 'fee_rates.csv')
    with open(path, encoding='utf-8', newline='') as f:
        cur = [r for r in csv.DictReader(f) if r['company'] == COMPANY]

    mine = {(r['period'], r['metric']): r for r in rows(cache_dir)}
    res = {'matched': 0, 'value_mismatch': [], 'missing_in_source': [],
           'source_url_changed': [], 'csv_rows': len(cur), 'parsed_rows': len(mine)}
    for r in cur:
        k = (r['period'], r['metric'])
        m = mine.get(k)
        if m is None:
            res['missing_in_source'].append((k, r['value'], r['source_url']))
            continue
        a, b = float(r['value']), float(m['value'])
        if r['unit'] != m['unit']:
            res['value_mismatch'].append((k, f"unit {r['unit']}", f"unit {m['unit']}", None))
        elif a != b:
            res['value_mismatch'].append((k, a, b, (b - a) / a if a else float('inf')))
        else:
            res['matched'] += 1
        if r['source_url'] != m['source_url']:
            res['source_url_changed'].append((k, r['source_url'], m['source_url']))
    return res


if __name__ == '__main__':
    import sys
    D = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sd, cd = os.path.join(D, 'series'), os.path.join(D, 'cache')
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'rows'
    if cmd == 'rows':
        rs = rows(cd)
        print(f'{len(rs)} rows, {len({r["period"] for r in rs})} quarters '
              f'{min(r["period"] for r in rs)}..{max(r["period"] for r in rs)}')
        for r in rs[-14:]:
            print(' ', r)
    elif cmd == 'restate':
        for x in restatements(cd):
            print(x)
        print('restatements:', len(restatements(cd)))
    elif cmd == 'verify':
        v = verify(sd, cd)
        print('csv_rows', v['csv_rows'], 'parsed_rows', v['parsed_rows'], 'matched', v['matched'])
        for kk in ('value_mismatch', 'missing_in_source', 'source_url_changed'):
            print(f'{kk}: {len(v[kk])}')
            for x in v[kk][:200]:
                print('   ', x)
