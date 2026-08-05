# -*- coding: utf-8 -*-
"""LPL Financial Holdings (LPLA) 月度经营指标抓取。

═══ 数据源 ═══
索引页（唯一入口，必须爬，不能硬编码文件 URL）：
    https://investor.lpl.com/financials/monthly-results
真正要下的文件：该页每月挂两个 PDF，我们只用后者——
    "<Month> <Year> Monthly Metrics"            → 当月新闻稿，只有当月 / 上月 / 去年同月三列
    "<Month> <Year> Monthly Metrics Historical File" → **滚动 13 个月的全表**，本模块的唯一解析对象
文件本体走 https://investor.lpl.com/static-files/<uuid>，uuid 每期都变且无规律，
所以 latest_month() / update() 每次都要重新爬索引页拿链接——**任何"记住的" URL 都会过期**。

为什么用 Historical File 而不是当月新闻稿：
  · 它一次给 13 个月，断更几个月后自动补齐，不必逐月回溯下载；
  · **它把季末月（3/6/9/12）也一并列出**，而季末月没有独立月度新闻稿。
    也就是说季末月不必去季报里抠——等下一份 Historical File 出来就有官方原值（见下文"口径坑 2"）。

反爬情况：无。普通 urllib + 常规浏览器 UA 即可 200（不带 UA 会被拒）。
无 Cloudflare / Akamai / PerimeterX，不需要登录态、不需要浏览器、不需要验证码 → 可无人值守。

═══ 发布节奏 ═══
月度新闻稿在**次月中旬**发布，实测：
    2025-08 → 2025-09-18   2025-10 → 2025-11-20   2025-11 → 2025-12-16
    2026-01 → 2026-02-19   2026-02 → 2026-03-19   2026-04 → 2026-05-21   2026-05 → 2026-06-16
即"次月第 3 个星期四前后（16–21 日）"。跑批建议放在每月 22 日之后。
季末月（3/6/9/12）**没有**自己的新闻稿，它随下一个月的 Historical File 一起出来，
所以 6 月数据要等 7 月报（≈8 月 20 日）——季末月天然比常规月晚一个发布周期。

═══ 口径坑（踩过的，别再踩） ═══
1) **series/lpla.csv 的 nna_* 三列是 "Total NNA"，含并购导入，不是 "Organic NNA"。**
   官方同页并排给三组：Organic NNA / Acquired NNA / Total NNA。
   核对锚点：2025-08 total 292.8 = organic 17.8 + acquired 275.0；2025-12 total 10.6 = 8.6 + 2.0。
   build/build_lpla.py 自己再用一张写死的 ACQ 字典把并购部分减掉出"有机"图，
   所以这里**必须存 Total NNA**，存成 Organic 会让 build 二次扣减、把并购月扣成负数。
2) 季末月无独立月报 → 见"发布节奏"。本模块只认 Historical File，**不从季报推算**。
   季报只给季度合计 NNA，要拿季末月得用"季合计 − 前两月"倒挤。
   拿 2024Q2–2026Q1 共 8 个季度回测过：**4 个存量列（advisory/brokerage/total/cash）每季全对**，
   但 **NNA 三列 8 个季度里有 6 个季度存在恰好 ±0.1 的偏差**（官方每列独立四舍五入，倒挤会放大）：
       2026Q1 brk −1.5/−1.6 | 2025Q4 total 10.5/10.6, adv 10.3/10.2, brk 0.5/0.4
       2025Q2 total 7.9/8.0, brk 0.0/0.1 | 2024Q4 total 25.7/25.8, brk 13.1/13.2
       2024Q3 brk 0.4/0.5 | 2024Q2 adv 9.3/9.2 |（2025Q3、2025Q1 全对）
   所以倒挤值**不进唯一真值表**，只在 quarter_end_estimate() 里提供，供"季报出了、下期月报还没出"
   的那 3 周抢先看一眼。
3) **client cash 被官方回溯重述过，重述发生在 Client Cash Account (CCA) 那一行。**
   同一个月在不同期 Historical File 里数值不同：2024-01 在 2024-01 期是 47.3（CCA 2.3），
   在 2025-01 期变成 46.9（CCA 1.9）；sweep 三行完全没动。2021 年底也有一次同类重述。
   → 回补历史时**必须用尽可能新的那期文件**，别拿当月那期。update() 只读最新一期，天然满足；
     重叠月份如有漂移会打印告警（默认不改写，见下）。
4) **PDF 行名 2026 年 4 月期改过版**，两套词表都得认，否则静默取不到值：
   旧（≤2026-02 期）：Advisory Assets / Brokerage Assets / Total Advisory and Brokerage Assets /
                      Net New Advisory Assets / Net New Brokerage Assets / Total Net New Assets
   新（≥2026-04 期）：分节表，节标题 Client Assets / Organic NNA / Acquired NNA / Total NNA，
                      节内行名退化成裸的 "Advisory" / "Brokerage"，必须靠节标题消歧。
   新格式里 "Advisory" 出现 4 次（资产、Organic、Acquired、Total NNA），只按行名匹配一定取错。
5) 表尾脚注区里还有一张 "Organic NNA from Large Institutions" 小表，行名同样是 Advisory/Brokerage。
   解析前必须在第一条脚注 "(1) " 处截断，否则小表会覆盖正表。
6) client_cash_usdbn 取 **Total Client Cash Balances**（含 CCA），不是 Total Bank Sweep、
   也不是 Total Client Cash Sweep Held by Third Parties。三者在表里上下相邻，很容易拿错。
7) 官方会把 sweep 货基转成 purchased money market（2025-11 转 1.6B、2026-02 转 0.5B）。
   这会让 client cash 出现**非资金流动导致的**下降，看图别当成客户提现。
8) 官方原表明写 "Totals may not foot due to rounding"，advisory + brokerage 与 total 差 0.1 属正常，
   所以本模块**不做 total = adv + brk 的硬校验**，只做"列必须存在"的硬校验。
9) 2025 年的 organic NNA 里含 OSJ（misaligned large OSJ）分离造成的流出，官方在脚注里逐月列出。
   本模块不做该调整——真值表存官方口径，调整留给 build 层。

═══ 解析器覆盖范围（实测） ═══
官网索引页共挂 51 期 Historical File（2020-02 … 2026-05）。本解析器跑通 **2022-07 起的 32 期**；
2022-05 及更早的 19 期是另一套版式（月份表头不在同一行），会抛 ParseError。
这不影响 update()——它只读最新一期，而真值表 2022-07 以前的部分早已入库。

═══ 真值表已知遗留偏差（本模块不改，只记录） ═══
把 32 期官方文件与 series/lpla.csv 全量交叉核对，发现 19 处 (月, 列) 不一致：
  · 17 处是 client_cash_usdbn，全部落在 2021-07…2021-12 与 2023-04，
    成因是上面口径坑 3 的 CCA 回溯重述——series 这些月停在重述前的旧值。
  · 2 处是 **2024-05 的 brokerage_assets_usdbn(657.0) 与 total_assets_usdbn(1466.4)**，
    覆盖该月的 8 期官方文件（2024-05 期到 2025-04 期）**无一例外都是 655.0 / 1464.4**，
    且 advisory 809.4 两边一致 → 这是真值表自己的录入错误，不是官方重述。
    要不要改由人决定（改了 build 出来的 2024-05 环比会动），update() 默认不碰。

═══ 幂等与不写 NaN ═══
update() 只追加 series 里没有的月份；已有月份一律不动（默认 revise=False，
只在数值漂移时打印告警，因为官方确实会重述，例如并购月的 acquired 拆分）。
任一目标列在 PDF 里没解析到 → 直接抛 ParseError，绝不写 NaN / 绝不填 0。
"""
from __future__ import annotations

import csv
import io
import os
import re
import time
import urllib.error
import urllib.request

BASE = 'https://investor.lpl.com'
INDEX_URL = BASE + '/financials/monthly-results'
QUARTER_INDEX_URL = BASE + '/financials/quarterly-results'
STATIC_URL = BASE + '/static-files/%s'

# 不带 UA 会被站点拒掉；这里用常规桌面 Chrome UA，无需 cookie / 登录态
UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36')

# series/lpla.csv 的列名与顺序，唯一真值，不许改
MONTH_COL = 'month'
VALUE_COLS = [
    'total_assets_usdbn',
    'advisory_assets_usdbn',
    'brokerage_assets_usdbn',
    'nna_total_usdbn',
    'nna_advisory_usdbn',
    'nna_brokerage_usdbn',
    'client_cash_usdbn',
]

_MON = {m: i for i, m in enumerate(
    ['jan', 'feb', 'mar', 'apr', 'may', 'jun',
     'jul', 'aug', 'sep', 'oct', 'nov', 'dec'], 1)}
_MON_FULL = {'january': 1, 'february': 2, 'march': 3, 'april': 4, 'may': 5, 'june': 6,
             'july': 7, 'august': 8, 'september': 9, 'october': 10,
             'november': 11, 'december': 12}


class ParseError(RuntimeError):
    """PDF 结构变了 / 目标行找不到。宁可炸也不能静默写 NaN。"""


class SourceError(RuntimeError):
    """官方源取不到（网络、404、索引页改版）。"""


# ────────────────────────── 网络 ──────────────────────────

def _get(url, tries=3, timeout=60):
    """带 UA 的裸 urllib GET。源站无反爬，失败基本就是网络抖动，退避重试即可。"""
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={
                'User-Agent': UA,
                'Accept': '*/*',
                'Accept-Language': 'en-US,en;q=0.9',
            })
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except (urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
            last = e
            time.sleep(2 * (i + 1))
    raise SourceError('下载失败 %s: %r' % (url, last))


def _index_entries(html_text, want='historical'):
    """从索引页 HTML 里抽出 (period 'YYYY-MM', 绝对 URL) 列表，按月份倒序。

    条目文本形如 'May 2026 Monthly Metrics Historical File' / 'May 2026 Monthly Metrics'。
    两者只差尾巴，所以必须精确区分，不能只 in 'Monthly Metrics'。
    """
    out = {}
    for m in re.finditer(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', html_text, re.S):
        href = m.group(1)
        txt = re.sub(r'<[^>]+>', ' ', m.group(2))
        txt = re.sub(r'&[a-z]+;', ' ', txt)
        txt = re.sub(r'\s+', ' ', txt).strip()
        mm = re.match(r'^([A-Z][a-z]+)\s+(\d{4})\s+Monthly Metrics(.*)$', txt)
        if not mm:
            continue
        mon = _MON_FULL.get(mm.group(1).lower())
        if not mon:
            continue
        tail = mm.group(3).strip().lower()
        is_hist = tail.startswith('historical')
        if (want == 'historical') != is_hist:
            continue
        period = '%s-%02d' % (mm.group(2), mon)
        if not href.startswith('http'):
            href = BASE + href
        out.setdefault(period, href)          # 同期重复时保留先出现的（页面按新→旧排）
    if not out:
        raise SourceError('索引页里没找到任何 Monthly Metrics 条目，页面结构可能改了：' + INDEX_URL)
    return sorted(out.items(), key=lambda kv: kv[0], reverse=True)


def _fetch_latest_historical(cache_dir):
    """爬索引页 → 下最新一期 Historical File 到 cache。返回 (索引标称期, 本地路径, url)。"""
    os.makedirs(cache_dir, exist_ok=True)
    html_text = _get(INDEX_URL).decode('utf-8', 'replace')
    with open(os.path.join(cache_dir, 'lpla_monthly_results_index.html'), 'w') as f:
        f.write(html_text)
    entries = _index_entries(html_text, want='historical')
    period, url = entries[0]
    blob = _get(url)
    if not blob.startswith(b'%PDF'):
        raise SourceError('%s 拿回来的不是 PDF（前 16 字节 %r），链接可能变成了落地页' % (url, blob[:16]))
    path = os.path.join(cache_dir, 'lpla_hist_%s.pdf' % period)
    with open(path, 'wb') as f:
        f.write(blob)
    return period, path, url


# ────────────────────────── PDF 解析 ──────────────────────────

def _pdf_text(path):
    try:
        import pdfplumber
    except ImportError as e:                                  # noqa: F841
        raise ParseError('需要 pdfplumber 才能解析 LPL 的 PDF：pip install pdfplumber')
    with pdfplumber.open(path) as pdf:
        return '\n'.join(p.extract_text() or '' for p in pdf.pages)


def _numbers(s):
    """把一行里的数字取出来。会计负号是括号；千分位逗号要去掉；百分比 / bps 不算数字列。"""
    out = []
    for tok in s.split():
        if tok.endswith('%') or tok.endswith('bps') or tok.endswith('bps)'):
            continue
        if not re.fullmatch(r'\(?-?\$?[\d,]+(\.\d+)?\)?', tok):
            continue
        neg = tok.startswith('(')
        t = tok.strip('()').replace(',', '').replace('$', '')
        if t in ('', '-'):
            continue
        try:
            v = float(t)
        except ValueError:
            continue
        out.append(-v if neg else v)
    return out


def _rows(text):
    """把表格文本切成 {(节, 行名小写): [数值...]}。节用来给新格式的裸 Advisory/Brokerage 消歧。"""
    lines = [l.rstrip() for l in text.split('\n')]
    # 口径坑 4：脚注区还有同名行的小表，先截断
    for i, l in enumerate(lines):
        if re.match(r'^\(1\)\s', l.strip()):
            lines = lines[:i]
            break

    section, rows = None, {}
    for raw in lines:
        s = re.sub(r'\(\d+\)', '', raw).strip()      # 去掉行内脚注角标 (1)(2)…
        if not s:
            continue
        vals = _numbers(s)
        low = s.lower()
        if not vals:                                  # 无数字 = 节标题
            for pat, tag in (('client assets', 'assets'),
                             ('organic net new assets', 'organic'),
                             ('organic nna', 'organic'),
                             ('acquired nna', 'acquired'),
                             ('acquired net new assets', 'acquired'),
                             ('total nna', 'total_nna'),
                             ('client cash balances', 'cash')):
                if low.startswith(pat):
                    section = tag
                    break
            continue
        # 行名 = 开头那串"非数值"词。不能用正则从第一个数字处切，
        # 因为季报里金额写成 "Advisory $ 1,548.4"，货币符号和数字之间有空格，会把 "$" 粘进行名。
        head = []
        for tok in s.split():
            if re.match(r'^\(?-?\$?[\d,]+(\.\d+)?\)?$', tok) or tok in ('$', '—', '-', '(', 'n/m'):
                break
            head.append(tok)
        label = ' '.join(head).rstrip('$ ').strip().lower()
        rows.setdefault((section, label), vals)       # 只留首次出现（季报里 Brokerage 会重复）
    return rows


def _header_months(text):
    """表头那一行的 13 个 'May 2026' → ['2026-05', '2026-04', ...]，顺序即数据列顺序。"""
    for l in text.split('\n'):
        ms = re.findall(r'\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{4})\b', l)
        if len(ms) >= 6:
            return ['%s-%02d' % (y, _MON[m.lower()]) for m, y in ms]
    raise ParseError('找不到月份表头行，PDF 版式可能改了')


# 目标列 → 查找规则。两级：
#   strict：(节, 行名)。**新格式（≥2026-04 期）专用**，因为那里行名退化成裸的 Advisory/Brokerage，
#           一个文件里出现 4 次，只能靠节标题消歧。
#   loose ：只按行名找，且要求全表**唯一**命中。旧格式（≤2026-02 期）行名本身就带限定词
#           （Organic / Acquired / 光杆 = Total），全局唯一，反而不能信节标题：
#           旧版式里 "Acquired NNA" 小节标题在前、Total 那组行在后且没有自己的标题，
#           按节匹配会把 Total 那组误判进 acquired 节。
_PICK = {
    'advisory_assets_usdbn':  {'strict': [('assets', 'advisory')],
                               'loose': ['advisory assets']},
    'brokerage_assets_usdbn': {'strict': [('assets', 'brokerage')],
                               'loose': ['brokerage assets']},
    'total_assets_usdbn':     {'strict': [('assets', 'total client assets')],
                               'loose': ['total advisory and brokerage assets',
                                         'total client assets']},
    'nna_advisory_usdbn':     {'strict': [('total_nna', 'advisory')],
                               'loose': ['net new advisory assets']},
    'nna_brokerage_usdbn':    {'strict': [('total_nna', 'brokerage')],
                               'loose': ['net new brokerage assets']},
    'nna_total_usdbn':        {'strict': [('total_nna', 'total nna')],
                               'loose': ['total net new assets']},
    'client_cash_usdbn':      {'strict': [('cash', 'total client cash balances')],
                               'loose': ['total client cash balances']},
}


def _lookup(rows, col, rule, path):
    for key in rule['strict']:
        if key in rows:
            return rows[key]
    for label in rule['loose']:
        hits = [v for (_sec, lab), v in rows.items() if lab == label]
        if not hits:
            continue
        # 季报里同一行会在 "Client Assets" 和 "Assets by Platform" 两块各印一次，
        # 数值完全相同——这种重复不算歧义，只有数值不同才是真歧义。
        if all(h == hits[0] for h in hits):
            return hits[0]
        raise ParseError('列 %s 的行名 %r 在 %s 里出现 %d 次且数值不一致，无法消歧'
                         % (col, label, path, len(hits)))
    raise ParseError('PDF 里找不到列 %s 对应的行（strict=%r loose=%r）；'
                     '官方很可能又改行名了，先人工看 %s'
                     % (col, rule['strict'], rule['loose'], path))


def parse_historical(path):
    """解析一期 Historical File → {'YYYY-MM': {列: 值}}。任一目标列缺失直接抛。

    注意 nna_* 取的是 **Total NNA**（含并购导入），见口径坑 1。
    """
    text = _pdf_text(path)
    months = _header_months(text)
    rows = _rows(text)

    picked = {}
    for col, rule in _PICK.items():
        vals = _lookup(rows, col, rule, path)
        if len(vals) < len(months):
            raise ParseError('列 %s 只解析到 %d 个值，表头有 %d 个月（%s）'
                             % (col, len(vals), len(months), path))
        picked[col] = vals[:len(months)]

    out = {}
    for i, mth in enumerate(months):
        out[mth] = {c: picked[c][i] for c in VALUE_COLS}
    return out


def source_month(path):
    """PDF 标题 'Historical Monthly Activity Through May 2026' → '2026-05'。
    以文件自述为准，不信索引页标题（索引页是人工录入的，理论上可能写错）。"""
    text = _pdf_text(path)
    m = re.search(r'Through\s+([A-Z][a-z]+)\s+(\d{4})', text)
    if not m:
        raise ParseError('PDF 标题里读不出 "Through <Month> <Year>"：' + path)
    return '%s-%02d' % (m.group(2), _MON_FULL[m.group(1).lower()])


# ────────────────────────── CSV 读写 ──────────────────────────

def _read_series(csv_path):
    """返回 (表头原文, 列位置, {月: 值}, {月: 原始行文本})。

    保留原始行文本是为了让 update() 把**已有行原样搬过去**——
    重新格式化会把历史上写成 '-0.0' 的单元格变成 '0.0'，那就等于动了真值表。
    """
    with open(csv_path, newline='') as f:
        raw = f.read().split('\n')
    raw = [l for l in raw if l.strip()]
    header_line, body = raw[0], raw[1:]
    header = next(csv.reader([header_line]))
    missing = [c for c in [MONTH_COL] + VALUE_COLS if c not in header]
    if missing:
        raise RuntimeError('series/lpla.csv 缺列 %r，列名不许改' % missing)
    idx = {c: header.index(c) for c in [MONTH_COL] + VALUE_COLS}
    data, lines = {}, {}
    for line in body:
        r = next(csv.reader([line]))
        mth = r[idx[MONTH_COL]]
        data[mth] = {c: float(r[idx[c]]) for c in VALUE_COLS}
        lines[mth] = line
    return header_line, idx, data, lines


def _fmt(v):
    """官方就是 1 位小数，直接照抄，不做任何再加工。"""
    s = '%.1f' % v
    return '0.0' if s == '-0.0' else s


# ────────────────────────── 对外 API ──────────────────────────

def latest_month(cache_dir):
    """官方源当前最新月 'YYYY-MM'。抓不到 / 解析不出 → 抛异常，不返回 None。

    返回的是最新一期 Historical File 覆盖到的月份。季末月因为随下一期才出现，
    在季报发布到下一期月报之间会"看起来落后一个月"，这是源本身的节奏，不是 bug。
    """
    _, path, _ = _fetch_latest_historical(cache_dir)
    return source_month(path)


def update(series_dir, cache_dir, revise=False, verbose=True):
    """把官方新月份写进 series/lpla.csv，返回新增月份列表（升序）。

    幂等：series 里已存在的月份不重复追加。
    revise=False（默认）时，重叠月份即使官方重述也**不改动**已有行，只打印告警——
    真值表的历史由人决定何时改。revise=True 才会就地改写重述值。
    """
    csv_path = os.path.join(series_dir, 'lpla.csv')
    header_line, idx, existing, raw_lines = _read_series(csv_path)
    ncol = len(next(csv.reader([header_line])))

    period, path, url = _fetch_latest_historical(cache_dir)
    src_month = source_month(path)
    if verbose:
        print('[lpla] 源文件 %s（索引标称 %s，自述 %s）\n[lpla] %s' % (path, period, src_month, url))
    parsed = parse_historical(path)
    if src_month not in parsed:
        raise ParseError('PDF 自述最新月 %s 不在解析出的月份里 %r' % (src_month, sorted(parsed)))

    # 重叠月份对账：官方重述（尤其并购月的 acquired 拆分）会在这里现形
    drift = []
    for mth in sorted(set(parsed) & set(existing)):
        for c in VALUE_COLS:
            a, b = existing[mth][c], parsed[mth][c]
            if abs(a - b) > 0.05:
                drift.append((mth, c, a, b))
    if drift and verbose:
        print('[lpla] 官方与 series 不一致 %d 处（%s）：' % (len(drift), '已改写' if revise else '未改写'))
        for mth, c, a, b in drift:
            print('       %s %s: series=%.1f 官方=%.1f' % (mth, c, a, b))

    new_months = sorted(set(parsed) - set(existing))
    if not new_months and not (revise and drift):
        if verbose:
            print('[lpla] 无新增月份，series 已到 %s' % max(existing))
        return []

    def render(mth, vals):
        row = [''] * ncol
        row[idx[MONTH_COL]] = mth
        for c in VALUE_COLS:
            row[idx[c]] = _fmt(vals[c])
        buf = io.StringIO()
        csv.writer(buf, lineterminator='').writerow(row)
        return buf.getvalue()

    out = dict(raw_lines)                       # 已有行原样保留，一个字符都不动
    for mth in new_months:
        out[mth] = render(mth, parsed[mth])
    if revise:
        for mth in sorted({d[0] for d in drift}):
            vals = dict(existing[mth])
            for m2, c, _a, b in drift:
                if m2 == mth:
                    vals[c] = b
            out[mth] = render(mth, vals)

    tmp = csv_path + '.tmp'
    with open(tmp, 'w') as f:
        f.write(header_line + '\n')
        for mth in sorted(out):
            f.write(out[mth] + '\n')
    os.replace(tmp, csv_path)
    if verbose:
        print('[lpla] 新增 %d 个月：%s' % (len(new_months), ', '.join(new_months)))
    return new_months


# ────────────────────────── 季末月倒挤（默认不用） ──────────────────────────

def quarter_end_estimate(series_dir, cache_dir, quarter=None):
    """用季报把季末月倒挤出来。**默认不接进 update()**，因为有 ±0.1 的四舍五入误差。

    存量三列（advisory / brokerage / total / cash）季报直接给季末时点值，是精确的；
    只有 NNA 三列要靠"季合计 − 季内前两月"倒挤。实测 2026Q1：
        Mar advisory 倒挤 9.7 = 官方 9.7 ✓
        Mar total    倒挤 8.1 = 官方 8.1 ✓
        Mar brokerage倒挤 −1.5 vs 官方 −1.6 ✗（差 0.1，纯四舍五入）
    所以它只适合"季报出了但下一期月报还没出"的那 3 周里抢先看一眼，
    不适合写进唯一真值表。返回 (month, {列: 值}, 说明)。
    """
    html_text = _get(QUARTER_INDEX_URL).decode('utf-8', 'replace')
    rel = {}
    for m in re.finditer(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', html_text, re.S):
        txt = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', m.group(2))).strip()
        mm = re.match(r'^Q([1-4])\s+(\d{4})\s+Press Release$', txt)
        if mm:
            key = '%sQ%s' % (mm.group(2), mm.group(1))
            href = m.group(1)
            rel.setdefault(key, href if href.startswith('http') else BASE + href)
    if not rel:
        raise SourceError('季报索引页里没找到 "Qn YYYY Press Release"：' + QUARTER_INDEX_URL)
    quarter = quarter or max(rel)
    if quarter not in rel:
        raise SourceError('没有 %s 的季报，现有 %r' % (quarter, sorted(rel)))

    os.makedirs(cache_dir, exist_ok=True)
    path = os.path.join(cache_dir, 'lpla_q_%s.pdf' % quarter)
    with open(path, 'wb') as f:
        f.write(_get(rel[quarter]))

    # 季报是 20+ 页，"Advisory assets" 这种行名在多张表里各出现一次（含一张补充的月度表），
    # 列数还不一样。所以先把文本切到 "Operating Metrics" 起、"Interest-Earning Assets" 止
    # 这一段——经营指标三块（资产 / NNA / 客户现金）都在里面，且行名唯一。
    text = _pdf_text(path)
    a = text.find('Operating Metrics')
    c = text.find('Total Client Cash Balances', a if a > 0 else 0)
    if a < 0 or c < 0:
        raise ParseError('季报里定位不到 Operating Metrics … Total Client Cash Balances 区段：' + path)
    b = text.find('\n', c)
    rows = _rows(text[a:b if b > 0 else len(text)])
    yr, q = int(quarter[:4]), int(quarter[-1])
    qend = '%d-%02d' % (yr, q * 3)
    prior = ['%d-%02d' % (yr, q * 3 - 2), '%d-%02d' % (yr, q * 3 - 1)]

    _, _, existing, _ = _read_series(os.path.join(series_dir, 'lpla.csv'))
    if any(p not in existing for p in prior):
        raise RuntimeError('倒挤需要季内前两月 %r 已在 series 里' % prior)

    # 季报的行名和月报同源，新旧两套词表复用 _PICK；每行第一个数字 = 本季
    vals = {}
    for col in ('advisory_assets_usdbn', 'brokerage_assets_usdbn',
                'total_assets_usdbn', 'client_cash_usdbn'):
        vals[col] = _lookup(rows, col, _PICK[col], path)[0]
    for col in ('nna_advisory_usdbn', 'nna_brokerage_usdbn', 'nna_total_usdbn'):
        q_total = _lookup(rows, col, _PICK[col], path)[0]
        vals[col] = round(q_total - sum(existing[p][col] for p in prior), 1)
    note = ('存量列取自季报时点值（精确）；NNA 三列 = 季合计 − %s，存在 ±0.1 四舍五入误差，'
            '等 %s 的 Historical File 出来后应以官方为准' % ('+'.join(prior), qend))
    return qend, vals, note


if __name__ == '__main__':
    import sys
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    print('latest:', latest_month(os.path.join(root, 'cache')))
    if '--update' in sys.argv:
        print(update(os.path.join(root, 'series'), os.path.join(root, 'cache')))
