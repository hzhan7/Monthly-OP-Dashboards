# -*- coding: utf-8 -*-
"""S&P Global (SPGI) 月度经营指标抓取模块。

════════ 数据源 ════════
发现入口（首选，无人值守可用）：
    https://investor.spglobal.com/feed/FinancialReport.svc/GetFinancialReportList
      ?apiKey=BF185719B0464B3CB809D23926182246&reportTypes=&year=-1&excludeSelection=1
    这是 Q4 Inc. 托管的 IR 站点自带的公开 JSON feed，apiKey 硬编码在
    investor.spglobal.com/quarterly-earnings/ 页面的 Q4Settings 里，不是密钥、无需登录。
    为什么必须走 feed 而不是解析页面 HTML：月度 xlsx 的链接是 JS 渲染的，
    静态 HTML 里根本没有 .xlsx 字样。

实际下载：feed 里 Documents[].DocumentPath 指向的 s29.q4cdn.com CDN 直链，形如
    https://s29.q4cdn.com/690959130/files/doc_financials/2026/q2/
        S-P-Global-Monthly-Metrics-as-of-June-2026-Published-7-15-2026.xlsx

════════ 反爬：为什么用 urllib 而不是 curl ════════
investor.spglobal.com 和 s29.q4cdn.com 都挂在 Cloudflare 后面。实测：
    · curl（默认 HTTP/2）→ 对 CDN 直接 "error in the HTTP2 framing layer"，对主站 403；
    · curl --http1.1 + 浏览器 UA → 200，可用但脆；
    · python urllib + 浏览器 UA → 200，主站 feed 和 CDN 都通。
所以本模块只用 urllib，绝不 shell out 到 curl。不需要浏览器登录态、不需要过验证码。

════════ 发布节奏 ════════
**2026-01 数据起换了节奏，且是公司公开承诺的**：每月 15 日发布上一个月的数据，
撞非工作日顺延到下一个工作日，**季末月不再例外**。出处是 2025Q4 财报 8-K
（SEC accession 0000064040-26-000007，filed 2026-02-10，附件
a4q2025earningsrelease.htm）："Beginning with January 2026 data, the Company
expects to release its monthly billed issuance data and exchange-traded
derivatives data on the 15th of each month (or the next business day
thereafter), one month in arrears." —— 说的正是本工作簿的那两张表。

工作簿右下角 "Published on M/D/YYYY" 是权威发布日（published_on() 读它，
逐月记进 series/source_dates.csv）。下表是全部实测，**只增不改**：
「月末后第 N 天」= 次月 N 号（次月 1 号即第 1 天，与 roster.LAG 同口径）。

    ── 旧节奏（2025-12 数据及以前）：季末月的那一份跟着当季财报一起发 ──
    2023-03 → 2023-04-27（第 27 天）    2024-09 → 2024-10-24（第 24 天）
    2023-06 → 2023-07-27（第 27 天）    2024-12 → 2025-02-11（第 42 天）
    2023-09 → 2023-11-02（第 33 天）    2025-03 → 2025-04-29（第 29 天）
    2023-12 → 2024-02-08（第 39 天）    2025-06 → 2025-07-31（第 31 天）
    2024-03 → 2024-04-25（第 25 天）    2025-09 → 2025-10-30（第 30 天）
    2024-06 → 2024-07-30（第 30 天）    2025-12 → 2026-02-10（第 41 天）
    n=12，第 24-42 天。**不是「大致同期」而是同一天**：后五期的发布日与公司
    earnings 8-K 的 filingDate 逐个字相同（2025-02-11 / 04-29 / 07-31 / 10-30、
    2026-02-10）。旧的 LAG[1]=46 就是照这一档的最坏值定的。

    ── 新节奏（2026-01 数据起）：逐月核对「15 号或顺延」，6/6 全中 ──
    2026-02 → 2026-03-16（第 16 天）  3/15 周日 → 顺延周一
    2026-03 → 2026-04-15（第 15 天）  周三；**季末月，且早于 Q1 财报 13 天**
    2026-04 → 2026-05-15（第 15 天）  周五
    2026-05 → 2026-06-15（第 15 天）  周一
    2026-06 → 2026-07-15（第 15 天）  周三；**季末月，早于 Q2 财报 13 天**
    2026-07 → 2026-08-17（第 17 天）  8/15 周六 → 顺延周一
    那两个季末月是关键证据：Q1/Q2 2026 的 earnings 8-K 分别 filed 于 2026-04-28
    与 2026-07-28，工作簿都比它早 13 天出 —— 与财报脱钩了，不是「碰巧快」。
    （2026-01 那一份按现行命名规则在 CDN 上找不到，1..28 号全试过；
    它落在下面两个界之内的哪一天都不影响结论。）

由这两条定死的上下界，**别再按「季末月一定晚」去调**：
  · **下界恒为第 15 天。**「次月 15 号」在本口径里永远等于第 15 天，与数据月有
    28/29/30/31 天无关。按承诺的规则不可能更早 —— 闸门的余量只能从这里算。
  · **上界第 18 天。** 15 号撞周六、顺延到的那个周一又是假日（MLK 与总统日都能
    落在 17 号），或 15 号本身是假日周五（2022 年的耶稣受难日就是 4/15）。

所以 roster.LAG['spgi'] = (18, 18)，monthly_run.EARLY_BY['spgi'] = (7, 7)
（红点 = 18 + GRACE 5 = 第 23 天；闸门 = 18 − 7 = 第 11 天，比下界还早 4 天）。
两处取值仍然不同，但不再是旧的「一个照最慢、一个照最快」——现在是同一个 LAG
上界，红点加宽限、闸门减余量，理由见 monthly_run.not_due 的 docstring。

⚠ 8-K 的原话是 "expects to"，是承诺不是保证。万一哪季又拖回财报日，现象是
**红点第 23 天变红、一直红到数据到货**，而闸门第 11 天就开着、数据照抓不误
（not_due 只在 data_through 追平时才关闸，源站晚发就一直是开的）。
红点响了是叫人回来重读这张表、把新的一期补进去，**不是**叫人把 LAG 悄悄调大。

⚠️ feed 的一个结构性坑：月度 xlsx 不是独立条目，而是**挂在当季那条 Quarterly 记录下面
的附件**，季内每发一版就把上一版换掉。所以 feed 任何时刻只能看到「最新的那一份」，
看不到季内历史版本。这对本模块无所谓（我们只要最新一份，它含当年全部已披露月份），
但意味着补历史月份不能靠 feed，只能靠 CDN 直链猜文件名（见 _guess_cdn_urls）。

════════ 口径坑（决定了本模块能产出什么、不能产出什么）════════
1. Billed Issuance 官方**只披露同比百分比，从不给绝对面值**。所以
   billed_issuance_index 是我们自己按同比链式构造的指数（2024 年同月 = 100），
   不是公司披露值。链式规则：index[y,m] = index[y-1,m] * (1 + yoy_fraction)，
   2024 年各月的基数固定为 100（因为 2024 年没有可用的同比数据）。
2. SPDJI ADV 给绝对值，但每份 xlsx 只有「当年 + 上年」两列。
   spgi_clean.csv 里 2024 年的绝对值是用 2025 年值除以官方 '25 v. '24 同比反算出来的
   （adv_derived=1 标记这一点）——是披露数据的算术推导，不是估计。
   更早年份的 xlsx 在 CDN 上已不可访问，故序列起点固定为 2024-01。
3. 2025 年 12 月起 ADV 定义**剔除 event contracts，且官方不重述更早月份**。
   也就是说 2025-11 与 2025-12 之间存在一处口径断点，画图时要标注（build_spgi.py 已标）。
4. 百分比在 xlsx 里存的是小数（0.03 = +3%），CSV 里存的是百分数（3）。
   小数 ×100 会引入浮点噪声（0.29*100 == 28.999999999999996），
   spgi.csv 历史行是用 "%.15g" 清洗过的，spgi_clean.csv 历史行没清洗。
   本模块**分别复刻这两种写法**（见 _g15 / _repr），否则同一个月在两个文件里
   会出现肉眼可见的位数差异。已验证：按此规则重算，两个 CSV 的全部历史行
   与磁盘上的字节完全一致。
5. 每月 xlsx 是**全年重发**（不是增量），实测 2026-03 版与 2026-06 版对 1-3 月的
   数值完全一致，没有重述。但重述是可能的，所以 update() 会把工作簿重算的历史月份
   与 CSV 已有值对一遍，发现不一致时**告警但不改写历史**（改写历史必须人工决定）。

════════ 对外接口 ════════
    latest_month(cache_dir) -> "YYYY-MM" | None
    update(series_dir, cache_dir) -> ["YYYY-MM", ...]   # 新增的月份，幂等
    published_on(xlsx_path) -> ("YYYY-MM-DD", 出处) | (None, None)

依赖：openpyxl（读 xlsx）。其余全是标准库，刻意不引 pandas —— 本模块的输出要和
历史 CSV 逐字节一致，pandas 的浮点格式化会自作主张。
"""

import calendar
import csv
import datetime as _dt
import json
import os
import re
import sys
import urllib.error
import urllib.request

import openpyxl

# ---------------------------------------------------------------- 常量

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

Q4_API_KEY = 'BF185719B0464B3CB809D23926182246'
Q4_FEED = ('https://investor.spglobal.com/feed/FinancialReport.svc/'
           'GetFinancialReportList?apiKey={key}&exchange=&symbol=&reportTypes='
           '&year=-1&excludeSelection=1&includeTags=true&pageSize=500')
CDN_BASE = 'https://s29.q4cdn.com/690959130/files/doc_financials'

# 走浏览器 UA 是硬要求：Cloudflare 对 python-urllib/3.x 这种 UA 直接 403。
UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36')

SHEET_RATINGS = 'Ratings'          # 子串匹配，防官方改全名
SHEET_INDICES = 'Dow Jones'
MONTHS = list(calendar.month_name)[1:]      # January..December

# series/spgi.csv 的列（顺序即写盘顺序）
COLS_RAW = ['month', 'billed_issuance_yoy_pct',
            'spdji_adv_mn_contracts', 'spdji_adv_yoy_pct']
# series/spgi_clean.csv 的列
COLS_CLEAN = ['month', 'spdji_adv_mn', 'spdji_adv_yoy', 'billed_issuance_yoy',
              'adv_derived', 'billed_issuance_index']

_MM_RE = re.compile(r'monthly-metrics-as-of-([a-z]+)-(\d{4})', re.I)
# 工作簿正文下方那行 "Published on 7/15/2026"。日期是美式 M/D/YYYY —— 文件名里的
# "-Published-7-15-2026" 与它同源同序，两处对得上就说明这个读法没错。
_PUB_RE = re.compile(r'Published\s+on\s+(\d{1,2})/(\d{1,2})/(20\d{2})', re.I)


class SpgiFetchError(RuntimeError):
    """抓取 / 解析 / 口径校验失败。调用方应当让它冒出去，不要 fallback 成空数据。"""


# ---------------------------------------------------------------- 小工具

def _g15(x):
    """spgi.csv 的数值写法：15 位有效数字，把 ×100 引入的浮点尾巴抹掉。

    为什么不是 round(x, n)：round 到固定小数位会把 6.6892991348713515 这种
    本来就有意义的长尾截短；%.15g 只抹掉 28.999999999999996 → 29 这类噪声。
    """
    return float('%.15g' % x)


def _fmt15(x):
    return '%.15g' % x


def _repr(x):
    """spgi_clean.csv 的数值写法：Python 原生 repr，保留全部浮点位。"""
    return repr(float(x))


def _source_dates():
    """按路径加载仓库根的 source_dates.py（发布日台账）。

    不能裸 import：本模块是被 monthly_run 用 spec_from_file_location 加载的，
    那时 sys.path 上既没有 fetch/ 也没有仓库根。
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        'source_dates', os.path.join(ROOT, 'source_dates.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _http_get(url, timeout=120):
    req = urllib.request.Request(url, headers={
        'User-Agent': UA,
        'Accept': '*/*',
        'Accept-Language': 'en-US,en;q=0.9',
    })
    with urllib.request.urlopen(req, timeout=timeout) as fh:
        return fh.read()


def _ym(period):
    return '%04d-%02d' % period


def _parse_ym(s):
    y, m = s.split('-')
    return int(y), int(m)


def _prev_year(period):
    return (period[0] - 1, period[1])


# ---------------------------------------------------------------- 发现源文件

def _discover_via_feed():
    """从 Q4 feed 里挑出「as-of 月份最新」的一份 Monthly Metrics xlsx。

    返回 (url, asof_period)。asof 月份从文件名里取，不从 ReportDate 取——
    ReportDate 是季报的日期，和数据月份对不上（实测 Q2-2026 那条 ReportDate
    是 07/28/2026，但附件是 as-of June 2026）。
    """
    raw = _http_get(Q4_FEED.format(key=Q4_API_KEY), timeout=60)
    try:
        items = json.loads(raw)['GetFinancialReportListResult']
    except (ValueError, KeyError) as exc:
        raise SpgiFetchError('Q4 feed 返回的不是预期 JSON: %r' % (raw[:200],)) from exc

    found = []
    for item in items or []:
        for doc in item.get('Documents') or []:
            path = doc.get('DocumentPath') or ''
            if not path.lower().endswith(('.xlsx', '.xls')):
                continue
            hit = _MM_RE.search(os.path.basename(path))
            if not hit:
                continue
            name, year = hit.group(1).capitalize(), int(hit.group(2))
            if name not in MONTHS:
                continue
            found.append(((year, MONTHS.index(name) + 1), path))
    if not found:
        raise SpgiFetchError('Q4 feed 里没有任何 Monthly Metrics xlsx；'
                             'feed 结构可能变了，需人工检查')
    found.sort()
    return found[-1][1], found[-1][0]


def _guess_cdn_urls(period):
    """兜底：直接猜 CDN 上某个 as-of 月份的文件名。

    只在 feed 挂掉、或需要补 feed 已经换掉的季内历史版本时用。
    只扫**次月** 8..28 号；大小写两种都试（2024/q1 那份是全小写，其余是首字母大写）。

    ⚠ 这个范围只覆盖得住**新节奏**（2026-01 数据起固定次月 15 号或顺延，实测
    第 15-17 天，稳稳落在窗口内）。对**旧节奏的季末月它覆盖不住**，而且不是差
    一两天：拿上面那张实测表逐条比，12 期里有 8 期在窗口外（只有 2023-03/2023-06/
    2024-03/2024-09 这 4 期落在窗口内）——
      · 发布日滑到**再下一个月**，本函数连月份都猜错（`pub_m` 只取次月）：
        2023-09 → 11-02、2023-12 → 02-08、2024-12 → 02-11、2025-12 → 02-10；
      · 落在次月但超过 28 号：2024-06 → 07-30、2025-03 → 04-29、
        2025-06 → 07-31、2025-09 → 10-30。
    这不是待修的 bug，是这条兜底路径的**已知边界**：那些历史月份都已在
    cache/basefill/spgi/ 里（补历史是一次性的事，已完成），而往后的月份按新节奏
    全在窗口内。真要再补一个旧季末月，别加宽这里的循环（8..28 已经是每月 42 次
    HTTP），直接把文件放进 basefill 更省事。
    """
    y, m = period
    q = 'q%d' % ((m - 1) // 3 + 1)
    pub_y, pub_m = (y + 1, 1) if m == 12 else (y, m + 1)
    stem = 'S-P-Global-Monthly-Metrics-as-of-%s-%d-Published' % (MONTHS[m - 1], y)
    for day in list(range(8, 29)):
        for name in (stem, stem.lower()):
            yield '%s/%d/%s/%s-%d-%d-%d.xlsx' % (
                CDN_BASE, y, q, name, pub_m, day, pub_y)


def _resolve_source(cache_dir):
    """定位并下载最新一份 xlsx，返回 (本地路径, asof_period, 源 url)。"""
    try:
        url, period = _discover_via_feed()
    except (urllib.error.URLError, SpgiFetchError) as exc:
        # feed 不可用时，从「上个月」往回猜 6 个月，找到第一个能下的。
        sys.stderr.write('[spgi] feed 不可用（%s），改用 CDN 文件名猜测兜底\n' % exc)
        today = _dt.date.today()
        url = period = None
        probe = (today.year, today.month)
        for _ in range(6):
            probe = (probe[0] - 1, 12) if probe[1] == 1 else (probe[0], probe[1] - 1)
            for cand in _guess_cdn_urls(probe):
                try:
                    _http_get(cand, timeout=20)
                except urllib.error.URLError:
                    continue
                url, period = cand, probe
                break
            if url:
                break
        if not url:
            raise SpgiFetchError(
                'Q4 feed 与 CDN 猜名两条路都失败，判定为 blocked。'
                '人工兜底：浏览器打开 https://investor.spglobal.com/quarterly-earnings/ '
                '展开当季 Quarterly Earnings 卡片，下载 "Monthly Metrics" xlsx，'
                '手动放到 cache/ 下再跑 update()。')

    os.makedirs(cache_dir, exist_ok=True)
    local = os.path.join(cache_dir, 'spgi_monthly_metrics_%s.xlsx' % _ym(period))
    if not (os.path.exists(local) and os.path.getsize(local) > 4096):
        blob = _http_get(url)
        if not blob.startswith(b'PK'):
            raise SpgiFetchError('下载到的不是 xlsx（前 4 字节 %r），可能被拦截页顶替了'
                                 % blob[:4])
        with open(local, 'wb') as fh:
            fh.write(blob)
    return local, period, url


# ---------------------------------------------------------------- 解析 xlsx

def _sheet(wb, needle):
    for name in wb.sheetnames:
        if needle.lower() in name.lower():
            return wb[name]
    raise SpgiFetchError('工作簿里找不到含 %r 的 sheet，实际有 %r' % (needle, wb.sheetnames))


def _header_row(ws):
    """找到表头行号：第一行里出现 "% Change" 的那一行。"""
    for row in range(1, min(ws.max_row, 15) + 1):
        for col in range(1, min(ws.max_column, 15) + 1):
            v = ws.cell(row, col).value
            if isinstance(v, str) and '% change' in v.lower():
                return row
    raise SpgiFetchError('sheet %r 里找不到 "% Change" 表头行' % ws.title)


def _yoy_columns(ws, hrow):
    """把 "'26 v. '25 % Change" 这类表头解析成 {年份: 列号}。

    年份用两位数写的，补成 20xx。硬编码列号是不行的——Ratings sheet 与
    Indices sheet 的列位不同，且官方历史上挪过列。
    """
    out = {}
    for col in range(1, ws.max_column + 1):
        v = ws.cell(hrow, col).value
        if not isinstance(v, str) or '% change' not in v.lower():
            continue
        hit = re.search(r"'(\d{2})\s*v\.?\s*'(\d{2})", v)
        if not hit:
            raise SpgiFetchError('看不懂的同比表头 %r（sheet %r）' % (v, ws.title))
        out[2000 + int(hit.group(1))] = col
    if not out:
        raise SpgiFetchError('sheet %r 表头行没有同比列' % ws.title)
    return out


def _adv_columns(ws, hrow):
    """把 "2026 ADV (in millions of contracts)" 解析成 {年份: 列号}。"""
    out = {}
    for col in range(1, ws.max_column + 1):
        v = ws.cell(hrow, col).value
        if isinstance(v, str) and 'adv' in v.lower():
            hit = re.search(r'(20\d{2})', v)
            if hit:
                out[int(hit.group(1))] = col
    if not out:
        raise SpgiFetchError('Indices sheet 表头行没有 ADV 绝对值列')
    return out


def _month_rows(ws, hrow):
    """表头之后连续的 12 个月份行，返回 {月份序号: 行号}。"""
    out = {}
    for row in range(hrow + 1, min(ws.max_row, hrow + 30) + 1):
        v = ws.cell(row, 1).value
        if isinstance(v, str) and v.strip() in MONTHS:
            out[MONTHS.index(v.strip()) + 1] = row
    if len(out) != 12:
        raise SpgiFetchError('sheet %r 只认出 %d 个月份行，期望 12' % (ws.title, len(out)))
    return out


def _num(cell):
    v = cell.value
    if v is None or (isinstance(v, str) and not v.strip()):
        return None
    if isinstance(v, str):
        raise SpgiFetchError('期望数字，读到字符串 %r' % v)
    return float(v)


def parse(xlsx_path):
    """解析一份 xlsx，返回 {(year, month): {字段: 原始小数/绝对值}}。

    注意同比字段这里保持 xlsx 原样的**小数**（0.03 = +3%），不在这里 ×100，
    以便 index 链式计算用未经清洗的原值（历史 CSV 就是这么算的）。
    """
    wb = openpyxl.load_workbook(xlsx_path, data_only=True, read_only=False)

    ws_r = _sheet(wb, SHEET_RATINGS)
    hr = _header_row(ws_r)
    r_yoy, r_rows = _yoy_columns(ws_r, hr), _month_rows(ws_r, hr)

    ws_i = _sheet(wb, SHEET_INDICES)
    hi = _header_row(ws_i)
    i_yoy, i_adv, i_rows = _yoy_columns(ws_i, hi), _adv_columns(ws_i, hi), _month_rows(ws_i, hi)

    data = {}
    for year, col in sorted(r_yoy.items()):
        for m, row in r_rows.items():
            v = _num(ws_r.cell(row, col))
            if v is not None:
                data.setdefault((year, m), {})['billed_yoy'] = v
    for year, col in sorted(i_yoy.items()):
        for m, row in i_rows.items():
            v = _num(ws_i.cell(row, col))
            if v is not None:
                data.setdefault((year, m), {})['adv_yoy'] = v
    for year, col in sorted(i_adv.items()):
        for m, row in i_rows.items():
            v = _num(ws_i.cell(row, col))
            if v is not None:
                data.setdefault((year, m), {})['adv'] = v
    if not data:
        raise SpgiFetchError('xlsx 解析出 0 条月度数据: %s' % xlsx_path)
    return data


def published_on(xlsx_path):
    """工作簿自述的发布日，返回 ("YYYY-MM-DD", 出处描述)；没写就 (None, None)。

    两个 sheet 的正文下方各有一行 "Published on 7/15/2026"（当前版式落在 A22）。
    这是**源头自己说的**发布日，页面抬头「官方发布于」只认这一种来源 ——
    文件 mtime 是我们下载它的时间，构建日更是与官方无关，都不能顶替。

    整表扫字符串而不是钉死 A22：那行的行号跟在 Definition/Source 两段文字后面，
    官方改一次措辞就会上下浮动，钉死单元格的失败方式是**静默读到 None**。
    """
    wb = openpyxl.load_workbook(xlsx_path, data_only=True, read_only=True)
    try:
        hits = {}
        for ws in wb.worksheets:
            for row in ws.iter_rows():
                for cell in row:
                    if not isinstance(cell.value, str):
                        continue
                    hit = _PUB_RE.search(cell.value)
                    if hit:
                        iso = '%s-%02d-%02d' % (hit.group(3), int(hit.group(1)),
                                                int(hit.group(2)))
                        hits.setdefault(iso, []).append(
                            '%s!%s %r' % (ws.title, cell.coordinate, cell.value.strip()))
    finally:
        wb.close()
    if not hits:
        return None, None
    # 两个 sheet 的页脚本该同期刷新。真不一致时取最晚的那个：整份工作簿是一次发布事件，
    # 更可能是官方漏刷了其中一张的页脚，而不是它真的早发了一版。但这属于官方版式异常，
    # 必须吵出来让人看一眼。
    iso = max(hits)
    if len(hits) > 1:
        sys.stderr.write('[spgi] ⚠ 工作簿里的 Published on 有多个日期（%s），取最晚的 %s；'
                         '请人工确认官方是不是漏刷了某个 sheet 的页脚\n'
                         % (', '.join(sorted(hits)), iso))
    return iso, '; '.join(hits[iso])


NEED = ('billed_yoy', 'adv', 'adv_yoy')


def _complete_months(data):
    """三个字段齐全的月份 —— 只有这种月份才允许入库。

    还要顺手抓一种致命情况：某个月**在已披露区间之内**却缺列。
    正常的 xlsx 是「已披露的月份三列全有，未披露的月份三列全空」，
    出现「有 ADV 没有 Billed Issuance」只能是官方改版或我们的列定位错了，
    这时候写库就会静默产生 NaN —— 所以直接抛异常，让人来看。
    """
    complete, partial = [], []
    for p, d in sorted(data.items()):
        (complete if all(k in d for k in NEED) else partial).append(p)
    for p in partial:
        year_done = [q for q in complete if q[0] == p[0]]
        if year_done and p < max(year_done):          # 夹在已披露区间里
            raise SpgiFetchError(
                '%s 处在已披露区间内却缺字段（拿到 %r，需要 %r）；'
                '不做静默跳过，也不写 NaN，请人工核对 xlsx 版式是否变了'
                % (_ym(p), sorted(data[p]), list(NEED)))
    return complete


# ---------------------------------------------------------------- CSV 读写

def _read_csv(path, cols):
    if not os.path.exists(path):
        raise SpgiFetchError('缺少序列文件 %s；本模块只负责追加，不负责从零建库' % path)
    with open(path, newline='', encoding='utf-8') as fh:
        rdr = csv.reader(fh)
        header = next(rdr)
        if header != cols:
            raise SpgiFetchError('%s 列名变了：磁盘 %r，期望 %r' % (path, header, cols))
        return header, [r for r in rdr if r and r[0].strip()]


def _append_csv(path, lines):
    """追加新行。

    两个坑：
    · 换行符必须沿用原文件的 —— 实测 spgi.csv 是 CRLF、spgi_clean.csv 是 LF，
      同一个仓库里两种都有。写错会让 git diff 整段飘红。
    · 原文件结尾若没有换行符，先补一个，否则新行会粘在最后一行后面。
    """
    with open(path, 'rb') as fh:
        blob = fh.read()
    eol = b'\r\n' if b'\r\n' in blob else b'\n'
    with open(path, 'ab') as fh:
        if blob and not blob.endswith(b'\n'):
            fh.write(eol)
        fh.write(eol.join(l.encode('utf-8') for l in lines) + eol)


# ---------------------------------------------------------------- 对外接口

def latest_month(cache_dir):
    """官方源当前最新、且三个字段齐全的月份 "YYYY-MM"。

    抓不到 / 解析不出来一律抛 SpgiFetchError（不返回 None 掩盖故障）。
    返回 None 只在一种情形：文件下到了、结构也对，但一个完整月份都没有——
    那是官方发了空表，属于真·无数据。
    """
    path, _, _ = _resolve_source(cache_dir)
    done = _complete_months(parse(path))
    return _ym(done[-1]) if done else None


def update(series_dir, cache_dir):
    """把新月份追加到 series/spgi.csv 与 series/spgi_clean.csv，返回新增月份列表。

    幂等：已存在的月份跳过。任一列算不出来就抛异常，绝不写 NaN。

    ── series/spgi.csv 不可删（孤儿盘点请勿标记为可删）────────────────────────
    两个 CSV 是本函数**同一次调用里一起写的**，中间不存在「先出 raw、再清洗成
    clean」这个环节 —— 所以 spgi.csv 不是 spgi_clean.csv 的上游中间产物，
    删掉它不会「由清洗步骤重新生成」。

    没有任何 build/*.py 读 spgi.csv（画图只读 spgi_clean.csv），按「谁读它」
    盘点必然把它判成断链孤儿。但它在本模块里承担两个不可替代的职责，都是**读**：

    1. 去重台账。下面 have_raw 取自 spgi.csv，与 clean_by_month 一起构成
       「这个月是否已入库」的判据。文件没了，_read_csv 直接抛
       SpgiFetchError（见该函数：本模块只追加、不从零建库），SPGI 抓取当场失败。
    2. 官方重述体检的**唯一基线**。下面那段循环逐行拿本期 xlsx 重算 spgi.csv
       的历史月份，不一致就告警（不改历史，改写历史必须人工决定）。
       这件事 spgi_clean.csv 顶不了：它的数值是 repr 未清洗写法，且 2024 年的
       绝对值是拿 2025 年值除以官方同比反算出来的（见模块 docstring 坑 3/4），
       拿它当基线会满屏假告警。基线丢了，官方悄悄重述历史就再没人发现。

    结论：spgi.csv = 本模块的私有台账 + 重述基线，只被 fetch 读回、不进 build。
    要动它之前先把上面两条职责搬走，否则删除 = SPGI 抓取炸掉 + 永久丢失重述告警。
    """
    path, asof, url = _resolve_source(cache_dir)
    data = parse(path)
    done = _complete_months(data)
    if not done:
        return []
    if done[-1] != asof:
        # 文件名的 as-of 月份和表里最后一个完整月份对不上 —— 多半是官方某一列漏填了。
        sys.stderr.write('[spgi] 提醒：文件名 as-of=%s，但表内最后完整月份=%s\n'
                         % (_ym(asof), _ym(done[-1])))

    raw_path = os.path.join(series_dir, 'spgi.csv')
    clean_path = os.path.join(series_dir, 'spgi_clean.csv')
    _, raw_rows = _read_csv(raw_path, COLS_RAW)
    _, clean_rows = _read_csv(clean_path, COLS_CLEAN)

    have_raw = {r[0] for r in raw_rows}
    clean_by_month = {r[0]: r for r in clean_rows}

    # ---- 先做重述体检：用工作簿重算已有月份，和 CSV 比。不一致只告警，不改历史。
    for r in raw_rows:
        p = _parse_ym(r[0])
        if p not in data or not all(k in data[p] for k in ('billed_yoy', 'adv', 'adv_yoy')):
            continue
        recalc = (_fmt15(_g15(data[p]['billed_yoy'] * 100)),
                  _fmt15(_g15(data[p]['adv'])),
                  _fmt15(_g15(data[p]['adv_yoy'] * 100)))
        if tuple(r[1:4]) != recalc:
            sys.stderr.write('[spgi] ⚠ %s 官方数值与库内不一致（库内 %r → 本期 xlsx %r），'
                             '疑似重述；本模块不改历史，请人工确认\n'
                             % (r[0], tuple(r[1:4]), recalc))

    new_raw, new_clean, added = [], [], []
    for p in done:
        key = _ym(p)
        if key in have_raw and key in clean_by_month:
            continue
        d = data[p]

        # billed_issuance_index 需要上一年同月的指数；2024 年是约定基数 100。
        prev = _prev_year(p)
        prev_key = _ym(prev)
        if prev[0] <= 2024:
            base = 100.0
        else:
            prev_row = clean_by_month.get(prev_key)
            base = None
            if prev_row and prev_row[COLS_CLEAN.index('billed_issuance_index')].strip():
                base = float(prev_row[COLS_CLEAN.index('billed_issuance_index')])
            else:
                for line in new_clean:                    # 可能是本轮刚追加的
                    if line.startswith(prev_key + ','):
                        base = float(line.split(',')[COLS_CLEAN.index('billed_issuance_index')])
                        break
            if base is None:
                raise SpgiFetchError(
                    '%s 算不出 billed_issuance_index：缺少上年同月 %s 的指数值。'
                    '同比链断了就整条序列失真，宁可报错。' % (key, prev_key))

        if key not in have_raw:
            new_raw.append(','.join([key,
                                     _fmt15(_g15(d['billed_yoy'] * 100)),
                                     _fmt15(_g15(d['adv'])),
                                     _fmt15(_g15(d['adv_yoy'] * 100))]))
        if key not in clean_by_month:
            new_clean.append(','.join([key,
                                       _repr(d['adv']),
                                       _repr(d['adv_yoy'] * 100),
                                       _repr(d['billed_yoy'] * 100),
                                       '0',
                                       _repr(base * (1 + d['billed_yoy']))]))
        added.append(key)

    if new_raw:
        _append_csv(raw_path, new_raw)
    if new_clean:
        _append_csv(clean_path, new_clean)

    # ── 发布日入台账（页面抬头「官方发布于」的唯一来源）────────────────────────
    # 只记 as-of 那一个月：xlsx 是全年重发，同一份文件里更早的月份是历次旧版各自发的，
    # 把本期的 "Published on" 安到它们头上，等于给旧月份印一个偏晚的假日期。
    # 补历史月份的发布日只能各自去找当期那份 xlsx（见 _guess_cdn_urls）。
    #
    # 条件是「as-of 月确实躺在两个 CSV 里」而不是「本轮新增了它」：数据落库与台账落库
    # 是两件事，某次跑只成了前一件（xlsx 页脚缺行、台账写失败）时，该月再也进不了
    # added 分支，那半句话就永久缺席。每次跑都对 as-of 月重申一遍，record 同键覆盖。
    asof_key = _ym(asof)
    if asof_key in added or (asof_key in have_raw and asof_key in clean_by_month):
        pub, where = published_on(path)
        if pub:
            try:
                _source_dates().record(series_dir, 'spgi', asof_key, pub,
                                       '%s（源文件 %s）' % (where, os.path.basename(url)))
            except Exception as exc:                        # noqa: BLE001
                # 台账写不进去不该把已经落库的月份回滚成 FAIL —— 数值是对的，
                # 代价只是页面抬头少半句话。响一声，让人回头补。
                sys.stderr.write('[spgi] ⚠ %s 发布日 %s 写台账失败：%s\n'
                                 % (asof_key, pub, exc))
        else:
            sys.stderr.write('[spgi] ⚠ %s 的 xlsx 里找不到 "Published on M/D/YYYY"，'
                             '本页不印「官方发布于」——宁可缺这半句，也不拿下载时间冒充\n'
                             % asof_key)

    if added:
        sys.stderr.write('[spgi] 新增 %d 个月：%s（源 %s）\n'
                         % (len(added), ', '.join(added), url))
    return added


if __name__ == '__main__':
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cache = os.path.join(root, 'cache')
    print('latest_month =', latest_month(cache))
    print('update       =', update(os.path.join(root, 'series'), cache))
