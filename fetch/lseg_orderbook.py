# -*- coding: utf-8 -*-
"""LSEG Capital Markets 现货腿 —— LSE 与 Turquoise 电子订单簿月度成交（无人值守抓取）。

本模块只负责 LSEG 四条腿里的 **Capital Markets / 现货订单簿** 这一条：
London Stock Exchange 主板订单簿 + Turquoise（Integrated 与暗池）成交额、笔数、
日均、交易日数，以及官方自己公布的两个份额（LSE 在英国 Lit 订单簿的份额、
Turquoise 在泛欧的份额）。衍生品、清算（LCH）、Tradeweb、数据业务都不在这里。

━━ 数据源（两个，互为独立核对）━━

**主源：LSEG Monthly Market Report（每月一个 PDF）**
  标题固定为 `LSEG market report <Month> <Year>`，第 1 页表名
  "LSEG - Electronic Order Book Trading"。本模块只读第 1 页最上面那张 **MTD 表**。
  文件落在 https://docs.londonstockexchange.com/sites/default/files/reports/ 。

**副源（只做核对，不入库）：`Order book trading` 工作簿**
  同一个文件服务器上的一个 xlsx，三个 sheet（Daily / Monthly / Yearly Order Book
  Trading）。Monthly sheet 从 **1997-10 到当月**共 346 行（2026-08-07 实测），
  给的是 LSE 订单簿的成交笔数、成交额（**精确到便士**，不是 PDF 那样四舍五入到 £m）、
  交易日数、日均笔数、日均成交额。每月逐笔核对 PDF 的 LSE 那三个数，对不上就抛异常。

⚠️ **两个文件的 URL 都不能写死，必须每次从官方检索接口里查出来**，理由见下面「文件名坑」。

━━ 怎么找到文件（**不许猜文件名**）━━

londonstockexchange.com 是 Angular SPA，`/reports?tab=...` 那个页面 curl 下来只有空壳，
文件链接是运行时才注入的。但站内检索有一个**可以直接 curl 的 JSON 接口**：

    GET https://api.londonstockexchange.com/api/v1/pages
        ?path=search&parameters=<双重 urlencode 的 "q=...&tab=documents&size=..&page=..">

`parameters` 是 **双重编码**：内层先把 `q=LSEG market report June 2026&tab=documents`
整串 urlencode 一次，再整体 urlencode 一次（浏览器发的就是 `q%253D...%2526tab%253D...`）。
少编一层不会报错，只会**静音返回错误的结果集**，所以 `_search()` 里那两层 quote 谁都别删。

返回体里 `components[type=="search"].content[0].value.pagesdocuments` 是文档命中列表，
每条形如：

    {"url": "https://docs.londonstockexchange.com/sites/default/files/reports/
             LSEG%20market%20report%20June%202026.pdf",
     "world": "documents", "title": "LSEG market report June 2026",
     "lastupdate": "2026-07-30T21:04:07"}

本模块按 **title 精确匹配**取链接，绝不按文件名拼 URL。

📌 已经踩到的两个文件名坑（正是「不许猜」的理由）：
  1. **同名重传会被 Drupal 加后缀**：`Order book trading_1558.xlsx`（数字每传一次 +1）、
     `LSEG market report January 2026_1.pdf`、`March 2022_1`、`September 2022_0`、
     `December 2022_0`。不带后缀的 `Order book trading.xlsx` **确实存在且返回 200**，
     但 Last-Modified 停在 **2020-09-15**（实测）—— 这是最恶心的一种坑：
     猜出来的 URL 不报错，只是永远给你六年前的数据。
  2. **少数条目的 title 里带扩展名**：2022-06 那期在 CMS 里的标题是
     `LSEG market report June 2022.pdf`（其余月份都不带）。所以匹配时要把 title 末尾的
     `.pdf` 去掉再比。

反面教材记在这里免得下次重来：docs.londonstockexchange.com 的目录页返回 403，
Angular 的 `/api/v1/components/refresh` 用页面里那些 block_content id 去拉 tab 模块
**一律返回 `[]`**（页面级 component 如 hero 却能拉到，说明 id 不通用），
web.archive.org 在本机是黑名单。别再往这三条路上走。

━━ 抓取方式与依赖 ━━
`urllib.request` 裸奔即可：api.londonstockexchange.com 与 docs.londonstockexchange.com
都是 CloudFront，实测无 Cloudflare/Akamai 挑战、无 JS 渲染、无登录墙、无 JA3 指纹拦截，
**满足无人值守**。PDF 解析用 PyMuPDF（`fitz`，仓里已有），xlsx 用 openpyxl（仓里已有）。

━━ 实测发布节奏 ━━
样本 = **2021-01 → 2026-06 共 66 期，一期不缺**，逐期读 PDF 内嵌的 /CreationDate
（Excel 导出时间戳），算相对**数据月月末**的日历天数。复算：
`python3 fetch/lseg_orderbook.py --cadence`。

    全样本 66 期：最早 +1 天，最晚 +51 天，中位 +4 天，均值 +7.2 天
    分布：+1 天 16 期 / +2..+6 天 28 期 / +7..+9 天 4 期 / +10..+24 天 17 期 / +51 天 1 期
    季末月（22 期）与非季末月（44 期）**没有系统差异**（中位 4.5 vs 4.0），
    所以 LAG / EARLY_BY 两个位置写同一个值即可。

⚠️ **节奏在 2024 年明显变慢，定闸门只能照近两年，不能照全样本中位数：**

    2021 年 12 期  +1..+6  天，中位 +2
    2022 年 12 期  +1..+5  天，中位 +2
    2023 年 12 期  +1..+6  天，中位 +2.5
    2024 年 12 期  +5..+20 天，中位 +9.5
    2025 年 12 期  +2..+15 天，中位 +10
    2026 上半年 6 期 +2..+51 天，中位 +21

    近 30 期（2024-01 起）实测最晚 = **2026-03 的数据 → 2026-04-24（+24 天）**，
    实测最早 = +2 天（2025-06 → 07-02、2026-06 → 07-02）。

📌 那个 +51 天（2026-01 数据，CreationDate 2026-03-23）**只能当上界读**：
   这一期的文件名是 `..._1.pdf`，是重传件，CreationDate 记的是重新导出的时间而不是首发时间。
   但同日（2026-03-23）生成的还有 2026-02 那期（文件名无后缀，不是重传），
   说明 2026 年初确实积压了两个月一起补发 —— 这不是纯粹的重传假象。

给 docs/CRON_WIRING.md §2 的建议（按本仓判据：LAG 照实测最晚、开闸日=实测最早）：

    LAG['lseg'] = (26, 26)          # 近 30 期最晚 +24，留 2 天余量
    EARLY_BY['lseg'] = (25, 25)     # 26 − 25 = 次月第 1 天开闸 = 实测最早发布日

⚠ EARLY_BY 必须写成**元组**：monthly_run.py 取值处是
`EARLY_BY.get(t, (EARLY, EARLY))[1 if qe else 0]`，写成裸整数会在下标那步 TypeError，
崩掉的是**整轮** monthly_run，不只是这一家。

📌 另一个必须知道的滞后：**副源 xlsx 自己也会落后。** 2026-08-07 实测，
`Order book trading` 工作簿的 Last-Modified 停在 2026-07-30 21:04 GMT、数据只到 7 月 30 日；
同一天 2026-07 那期月报**还没发**（检索接口查无此条）。所以「LSEG 的月度数据慢」
是常态，别把 NOCHANGE 当成抓取坏了。

━━ 口径坑（按踩坑概率排序）━━

**1. 只读第一张表（MTD），YTD 那张表是坏的。**
   2026-06 那期的 YTD 区块里 Turquoise Integrated 的 £m 印成 28,264（跟 MTD 一模一样）、
   €m 印成 204,771、同比 −83% —— 官方自己排版错了。本模块只解析第 1 页
   "Average Daily" 之前 + "Trading days" 表，YTD 区块从不碰。谁要加 YTD 列先去核对这一期。

**2. 行标签改过三轮名字，同一条序列换过三个标题。**
   · LSE 现货：`UK order book`（→2020-12）→ `LSE Order Book`（2021-01→）
     2021-01 改名的同时，报告里 `Italian order book` 那一行消失 —— 那是 Borsa Italiana
     卖给 Euronext（2021-04 交割）前后的口径切换。本模块从来只取 UK/LSE 那一行，
     所以**这条序列本身不含意大利**，2021 年前后不存在口径断点。
   · Turquoise 暗池：`Turquoise MidPoint` → `Turquoise Plato™`（2017 起）→
     `Turquoise Dark`（2026-01 起，实测 2026-06 那期已是 Dark）。三个名字是同一条腿，
     统一写进 `turquoise_dark_*`。
   · 份额行：`UK Lit Orderbook trading`（→2020-12）→ `LSE Lit Orderbook trading in UK`。
   标签里的 `™` 和结尾空格都要 strip（"Turquoise Dark " 在 Average Daily 区块里带尾空格）。

**3. 起点定在 2021-01，不是没有更早的数据，是更早的 PDF 少列。**
   2013-01 起就有月报，但 2020-12 及以前那批还额外印 Italian / Derivatives / MTS /
   EuroTLX 等行，且 2021-01 才出现 `LSE Lit Orderbook trading in UK` 这个标签。
   本仓禁止写 NaN，所以**宁可少月份不许缺列**：只收全部 17 列都齐的月份。
   要往前接 2013-2020，得先决定份额列怎么对齐旧标签，那是另一件事。

**4. 成交额单位是「官方印的 £m」，不做换算。**
   PDF 只印到百万英镑整数（146,827 = £146.827bn）。xlsx 有精确到便士的同一个数
   （146,827,153,894.25）。本模块**入库 PDF 的 £m**、拿 xlsx 做核对（容差见
   `_crosscheck()` 里那段实测记录）。反过来（入库 xlsx 精确值）会让 LSE 那几列和
   Turquoise 那几列**精度口径不一致**，画在同一张图上没人说得清差在哪。
   两源 66 个月全部对得上，最大偏差：笔数 8 笔、成交额 1.30 £m、交易日 0 天。

**5. 交易日数 LSE 与 Turquoise 不一样，各存一列。**
   Turquoise 跟的是泛欧日历（2026-06：LSE 22 天 / Turquoise 22 天，但 2019-12 是
   UK 20 / Turquoise 20 / Italy 18，差异真实存在）。日均成交额=月成交额÷各自的交易日数，
   别拿 LSE 的天数去除 Turquoise 的成交额。

**6. 副源 xlsx 的最后一个月经常是残月，核对时要跳过。**
   2026-08-07 实测：xlsx 的 Daily sheet 最新一天是 2026-07-30，Monthly sheet 里
   `Jul-26` 只有 22 个交易日（7 月实际 23 个），即**当月未走完就已入表**。
   `_xlsx_monthly()` 因此只承认「Daily sheet 里已经出现过更晚月份」的那些月，
   剩下的直接丢掉 —— 拿残月去核对 PDF 会得到一个假的不一致。

**7. 份额是百分数，入库存百分点数值（69.2 表示 69.2%），不是 0.692。**
"""
import csv
import datetime
import json
import os
import re
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CACHE = os.path.join(ROOT, 'cache', 'lseg_orderbook')
SERIES = os.path.join(ROOT, 'series')

SEARCH_API = 'https://api.londonstockexchange.com/api/v1/pages'
UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36')
REFERER = 'https://www.londonstockexchange.com/search'

# 起点见 docstring 口径坑 3。终点由官方发到哪算哪。
START_MONTH = '2021-01'

MONTH_NAMES = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
               'August', 'September', 'October', 'November', 'December']

# ── 行标签 → 列前缀。全部先经 _norm_label() 归一化（去 ™、去尾空格、小写、压空格）。
LSE_LABELS = ('lse order book', 'uk order book')
TQ_INT_LABELS = ('turquoise integrated',)
TQ_DARK_LABELS = ('turquoise dark', 'turquoise plato', 'turquoise midpoint')
UK_SHARE_LABELS = ('lse lit orderbook trading in uk', 'uk lit orderbook trading')
TQ_SHARE_LABELS = ('turquoise total pan european trading',)
LSE_DAY_LABELS = ('lse', 'uk')
TQ_DAY_LABELS = ('turquoise',)

COLUMNS = [
    'lse_orderbook_value_gbp_m',
    'lse_orderbook_trades_count',
    'lse_orderbook_adv_gbp_m',
    'lse_orderbook_avg_daily_trades_count',
    'lse_trading_days_count',
    'turquoise_integrated_value_gbp_m',
    'turquoise_integrated_trades_count',
    'turquoise_integrated_adv_gbp_m',
    'turquoise_integrated_avg_daily_trades_count',
    'turquoise_dark_value_gbp_m',
    'turquoise_dark_trades_count',
    'turquoise_dark_adv_gbp_m',
    'turquoise_dark_avg_daily_trades_count',
    'turquoise_trading_days_count',
    'lse_lit_uk_share_pct',
    'turquoise_paneuropean_share_pct',
    'gbp_eur_rate',
]


class LsegOrderbookFetchError(RuntimeError):
    """本模块所有失败路径统一抛它，调度器只需 catch 一种。"""


# ──────────────────────────────────────────────────────────────── HTTP 与检索

def _http_get(url, timeout=90, tries=3, pause=1.5):
    """带退避的 GET。docs/api 两个域都是 CloudFront，偶发 5xx 重试即可。"""
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={
                'User-Agent': UA, 'Referer': REFERER,
                'Accept': 'application/json,text/html,*/*'})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:                      # noqa: BLE001 —— 什么错都重试
            last = e
            if i + 1 < tries:
                time.sleep(pause * (i + 1))
    raise LsegOrderbookFetchError(f'GET 失败 {url}: {last}')


def _search(q, size=20, page=0, tab='documents'):
    """站内检索。返回 pagesdocuments 列表（可能为空）。

    `parameters` 必须双重 urlencode，见 docstring「怎么找到文件」。
    """
    inner = urllib.parse.urlencode({'q': q, 'tab': tab,
                                    'size': str(size), 'page': str(page)})
    once = urllib.parse.quote(inner, safe='')
    twice = urllib.parse.quote(once, safe='')
    url = f'{SEARCH_API}?path=search&parameters={twice}'
    raw = _http_get(url)
    try:
        doc = json.loads(raw)
    except Exception as e:
        raise LsegOrderbookFetchError(f'检索接口返回的不是 JSON（q={q!r}）: {e}') from e
    comps = [c for c in (doc.get('components') or []) if c.get('type') == 'search']
    if not comps:
        raise LsegOrderbookFetchError(
            f'检索接口没有 search 组件（q={q!r}）—— 接口改版了，别再往下解析')
    content = comps[0].get('content') or []
    if not content:
        return []
    return (content[0].get('value') or {}).get('pagesdocuments') or []


def _title_key(title):
    """CMS 里少数条目的 title 带扩展名（2022-06 那期），比对前去掉。"""
    t = (title or '').strip()
    for ext in ('.pdf', '.xlsx', '.xls'):
        if t.lower().endswith(ext):
            t = t[:-len(ext)]
    return re.sub(r'\s+', ' ', t).strip().lower()


def _find_doc(title):
    """按标题精确匹配拿一条文档记录，找不到返回 None（不抛）。"""
    for hit in _search(title, size=30):
        if _title_key(hit.get('title')) == _title_key(title):
            if not (hit.get('url') or '').startswith('http'):
                continue                            # 页面命中不是文档，跳过
            return hit
    return None


def _download(url, path, min_bytes=20000):
    """下到 cache/。判有效而不只判存在 —— 0 字节残骸会让后续每轮都以为「已经有了」。"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path) and os.path.getsize(path) >= min_bytes:
        return path
    if os.path.exists(path):
        os.remove(path)
    data = _http_get(url, timeout=120)
    if len(data) < min_bytes:
        raise LsegOrderbookFetchError(
            f'下到的文件只有 {len(data)} 字节，疑似拦截页: {url}')
    with open(path, 'wb') as f:
        f.write(data)
    return path


# ──────────────────────────────────────────────────────────────── 月份小工具

def _month_label(month):
    y, m = month.split('-')
    return f'{MONTH_NAMES[int(m) - 1]} {y}'


def _months(start, end):
    y0, m0 = (int(x) for x in start.split('-'))
    y1, m1 = (int(x) for x in end.split('-'))
    out = []
    while (y0, m0) <= (y1, m1):
        out.append(f'{y0}-{m0:02d}')
        m0 += 1
        if m0 == 13:
            y0, m0 = y0 + 1, 1
    return out


def _prev_month(month):
    y, m = (int(x) for x in month.split('-'))
    return f'{y - 1}-12' if m == 1 else f'{y}-{m - 1:02d}'


def _today_month():
    d = datetime.date.today()
    return f'{d.year}-{d.month:02d}'


# ──────────────────────────────────────────────────────────────── PDF 解析

_NUM = re.compile(r'^-?[\d,]+(?:\.\d+)?%?$')


def _norm_label(s):
    s = (s or '').replace('™', '').replace('\xa0', ' ')
    return re.sub(r'\s+', ' ', s).strip().lower()


def _num(tok):
    """'146,827' → 146827.0；'69.2%' → 69.2；不是数就返回 None。"""
    t = (tok or '').strip().replace('\xa0', '')
    if not _NUM.match(t):
        return None
    return float(t.rstrip('%').replace(',', ''))


def _take(lines, i, n, month, where):
    """从 lines[i+1] 起取 n 个数值行，中间不允许夹非数值行。"""
    out = []
    j = i + 1
    while j < len(lines) and len(out) < n:
        v = _num(lines[j])
        if v is None:
            raise LsegOrderbookFetchError(
                f'{month} {where}: 第 {len(out) + 1} 个数位置上是 {lines[j]!r}，'
                f'不是数字 —— 排版变了，拒绝猜')
        out.append(v)
        j += 1
    if len(out) < n:
        raise LsegOrderbookFetchError(f'{month} {where}: 只取到 {len(out)}/{n} 个数')
    return out


def _find_line(lines, labels, lo, hi, month, where):
    for i in range(lo, min(hi, len(lines))):
        if _norm_label(lines[i]) in labels:
            return i
    raise LsegOrderbookFetchError(
        f'{month} {where}: 在第 1 页找不到标签 {labels}（标签又改名了？）')


def parse_report(path, month):
    """解析 Monthly Market Report 第 1 页的 MTD 表，返回 {列: 值}。

    只碰第一张表：`Average Daily` 之前是月合计区块，之后到 `Exchange Rate` 是日均区块，
    再往后是汇率 / 份额 / 交易日。`Trading days` 之后还有一张 YTD 表，本函数不看。
    """
    import fitz
    doc = fitz.open(path)
    if doc.page_count < 1:
        raise LsegOrderbookFetchError(f'{month}: PDF 没有页面 {path}')
    text = doc[0].get_text()
    lines = [ln.rstrip() for ln in text.split('\n')]
    norm = [_norm_label(ln) for ln in lines]

    head = next((i for i, s in enumerate(norm)
                 if s.startswith('lseg - electronic order book trading')), None)
    if head is None:
        raise TypeError('not-an-eob-report')       # 由调用方翻译成更友好的错误

    want = _norm_label(_month_label(month))
    if want not in norm[head:head + 4]:
        raise LsegOrderbookFetchError(
            f'{month}: PDF 抬头写的不是 {want!r}（前几行 {lines[head:head + 4]}）'
            f' —— 下到了别的月份，拒绝入库')

    def idx(pred, what):
        for i in range(head, len(norm)):
            if pred(norm[i]):
                return i
        raise LsegOrderbookFetchError(f'{month}: 第 1 页找不到 {what} 区块')

    i_avg = idx(lambda s: s == 'average daily', '"Average Daily"')
    i_fx = idx(lambda s: s.startswith('exchange rate'), '"Exchange Rate"')
    i_share = idx(lambda s: s == 'share of trading', '"Share of trading"')
    i_days = idx(lambda s: s == 'trading days', '"Trading days"')
    if not head < i_avg < i_fx <= i_share < i_days:
        raise LsegOrderbookFetchError(
            f'{month}: 第 1 页区块顺序反常 '
            f'(head={head} avg={i_avg} fx={i_fx} share={i_share} days={i_days})')

    rec = {}
    # 月合计区块：每行 9 个数 = [笔数, £m, €m] 当月 / [同上] 去年同月 / [同比 ×3]，只取前 3。
    for labels, pfx in ((LSE_LABELS, 'lse_orderbook'),
                        (TQ_INT_LABELS, 'turquoise_integrated'),
                        (TQ_DARK_LABELS, 'turquoise_dark')):
        i = _find_line(lines, labels, head, i_avg, month, f'月合计 {pfx}')
        trades, gbp, _eur = _take(lines, i, 3, month, f'月合计 {pfx}')
        rec[f'{pfx}_trades_count'] = int(round(trades))
        rec[f'{pfx}_value_gbp_m'] = gbp
    # 日均区块
    for labels, pfx in ((LSE_LABELS, 'lse_orderbook'),
                        (TQ_INT_LABELS, 'turquoise_integrated'),
                        (TQ_DARK_LABELS, 'turquoise_dark')):
        i = _find_line(lines, labels, i_avg, i_fx, month, f'日均 {pfx}')
        trades, gbp, _eur = _take(lines, i, 3, month, f'日均 {pfx}')
        rec[f'{pfx}_adv_gbp_m'] = gbp
        rec[f'{pfx}_avg_daily_trades_count'] = int(round(trades))

    # 汇率：Exchange Rate (GBP/EUR) 后面两个数 = 当月 / 去年同月
    rec['gbp_eur_rate'] = _take(lines, i_fx, 2, month, '汇率')[0]

    # 份额：标签后面两个百分数 = 当月 / 去年同月
    i = _find_line(lines, UK_SHARE_LABELS, i_share, i_days, month, '份额 UK Lit')
    rec['lse_lit_uk_share_pct'] = _take(lines, i, 2, month, '份额 UK Lit')[0]
    i = _find_line(lines, TQ_SHARE_LABELS, i_share, i_days, month, '份额 Turquoise')
    rec['turquoise_paneuropean_share_pct'] = _take(lines, i, 2, month, '份额 Turquoise')[0]

    # 交易日：标签后面 4 个数 = MTD / YTD / 去年 MTD / 去年 YTD，只要 MTD。
    # 窗口给到 30 行：2021 年那批还多印一行 CurveGlobal（2022-01 停业前），
    # Turquoise 会被挤到第 14 行往后。窗口再宽也不会误命中 YTD 表 ——
    # 那张表里的标签是 "Turquoise Integrated"，归一化后不等于 "turquoise"。
    i = _find_line(lines, LSE_DAY_LABELS, i_days, i_days + 30, month, '交易日 LSE')
    rec['lse_trading_days_count'] = int(round(_take(lines, i, 4, month, '交易日 LSE')[0]))
    i = _find_line(lines, TQ_DAY_LABELS, i_days, i_days + 30, month, '交易日 Turquoise')
    rec['turquoise_trading_days_count'] = int(
        round(_take(lines, i, 4, month, '交易日 Turquoise')[0]))

    missing = [c for c in COLUMNS if rec.get(c) is None]
    if missing:
        # 缺列一律失败，绝不静默写空 —— 空值会一路画成 null 点上线而全程无报错。
        raise LsegOrderbookFetchError(f'{month} 解析缺列 {missing}')
    _sanity(month, rec)
    return rec


def _sanity(month, rec):
    """结构性自检：解析没报错但把数字接错行时，只有恒等式能发现。"""
    for pfx in ('lse_orderbook', 'turquoise_integrated', 'turquoise_dark'):
        days = rec['lse_trading_days_count' if pfx == 'lse_orderbook'
                   else 'turquoise_trading_days_count']
        tot, adv = rec[f'{pfx}_value_gbp_m'], rec[f'{pfx}_adv_gbp_m']
        if adv <= 0 or tot <= 0 or days <= 0:
            raise LsegOrderbookFetchError(f'{month} {pfx}: 非正数 tot={tot} adv={adv} d={days}')
        # 官方自己四舍五入到 £m，日均×天数与月合计允许 1.5% 的漂移。
        if abs(adv * days - tot) > max(1.5, 0.015 * tot):
            raise LsegOrderbookFetchError(
                f'{month} {pfx}: 日均×交易日({adv}×{days}={adv * days:.0f}) '
                f'与月合计({tot}) 对不上 —— 多半是把某一行的数接到了别的行')
    for col in ('lse_lit_uk_share_pct', 'turquoise_paneuropean_share_pct'):
        if not 0 < rec[col] <= 100:
            raise LsegOrderbookFetchError(f'{month} {col}={rec[col]} 不像百分点')
    if not 0.9 < rec['gbp_eur_rate'] < 1.5:
        raise LsegOrderbookFetchError(f'{month} gbp_eur_rate={rec["gbp_eur_rate"]} 不像汇率')


# ─────────────────────────────────────────────── 副源 xlsx（只做核对，不入库）

def _xlsx_monthly():
    """返回 {'YYYY-MM': (trades, value_gbp, days, adv_trades, adv_gbp)}，只含**完整月**。

    完整月的判据不看日历、不查假期表：Daily sheet 里出现过比该月更晚的交易日，
    该月就一定走完了。见 docstring 口径坑 6。
    """
    import openpyxl
    hit = _find_doc('Order book trading')
    if hit is None:
        raise LsegOrderbookFetchError('检索接口找不到 "Order book trading" 工作簿')
    path = _download(hit['url'], os.path.join(CACHE, 'order_book_trading.xlsx'),
                     min_bytes=100000)
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    for need in ('Daily Order Book Trading', 'Monthly Order Book Trading'):
        if need not in wb.sheetnames:
            raise LsegOrderbookFetchError(f'工作簿少 sheet {need!r}: {wb.sheetnames}')

    newest_day = None
    for row in wb['Daily Order Book Trading'].iter_rows(values_only=True):
        v = row[1] if len(row) > 1 else None
        if isinstance(v, datetime.datetime):
            if newest_day is None or v > newest_day:
                newest_day = v
    if newest_day is None:
        raise LsegOrderbookFetchError('Daily sheet 里一个交易日期都没解析出来')
    cutoff = f'{newest_day.year}-{newest_day.month:02d}'   # 该月本身算未完成

    out = {}
    for row in wb['Monthly Order Book Trading'].iter_rows(values_only=True):
        lab = row[1] if len(row) > 1 else None
        if not isinstance(lab, str):
            continue
        m = re.match(r'^([A-Za-z]{3})-(\d{2})$', lab.strip())
        if not m:
            continue
        mon = ['jan', 'feb', 'mar', 'apr', 'may', 'jun',
               'jul', 'aug', 'sep', 'oct', 'nov', 'dec'].index(m.group(1).lower()) + 1
        # 两位年份：这份表从 Oct-97 起头，'97'/'98'/'99' 必须还原成 19xx。
        # 直接拼 '20'+yy 会得到 2097-10 —— 不报错，只是悄悄多出一堆未来月份。
        yy = int(m.group(2))
        key = f'{1900 + yy if yy >= 70 else 2000 + yy}-{mon:02d}'
        if key >= cutoff:
            continue
        vals = [row[i] if len(row) > i else None for i in (2, 3, 4, 5, 6)]
        if any(v is None for v in vals):
            continue
        out[key] = tuple(float(v) for v in vals)
    wb.close()
    if not out:
        raise LsegOrderbookFetchError('工作簿 Monthly sheet 解析不出任何完整月')
    return out


def _crosscheck(rows, xlsx):
    """逐月拿 xlsx 精确值核对 PDF 的 LSE 三个数。xlsx 没有的月份跳过并说明。"""
    skipped = []
    for r in rows:
        ref = xlsx.get(r['month'])
        if ref is None:
            skipped.append(r['month'])
            continue
        trades, value_gbp, days, adv_trades, adv_gbp = ref
        # 容差是实测定的，不是拍的：2021-01..2026-06 共 66 个月逐月比对，
        # 观测到的最大偏差 —— 笔数 8 笔（2026-03，21,124,329 vs 21,124,326，
        # 月报快照与持续重述的工作簿之间的微小差异）、成交额 1.30 £m、
        # 日均笔数 0.5、日均成交额 0.49 £m、交易日 0。
        # 下面的阈值留了 2-3 倍余量；接错行会差好几个数量级，一定拦得住。
        pairs = [
            ('trades', r['lse_orderbook_trades_count'], trades, 25),
            ('value_gbp_m', r['lse_orderbook_value_gbp_m'], value_gbp / 1e6, 2.0),
            ('trading_days', r['lse_trading_days_count'], days, 0.5),
            ('avg_daily_trades', r['lse_orderbook_avg_daily_trades_count'], adv_trades, 1.5),
            ('adv_gbp_m', r['lse_orderbook_adv_gbp_m'], adv_gbp / 1e6, 1.0),
        ]
        for name, got, want, tol in pairs:
            if abs(got - want) > tol:
                raise LsegOrderbookFetchError(
                    f'{r["month"]} 双源对不上 {name}: 月报 PDF={got} vs '
                    f'Order book trading.xlsx={want:.4f}（容差 {tol}）')
    if skipped:
        print(f'[lseg_orderbook] 副源 xlsx 尚无这些月份，未做双源核对: {skipped}')
    return len(rows) - len(skipped)


# ──────────────────────────────────────────────────────────────── 对外接口

def fetch_rows(start=START_MONTH, end=None, verbose=True, crosscheck=True):
    """返回 [{'month': 'YYYY-MM', <17 列>}, ...]，按月份升序。

    end 默认取「上个月」—— 当月的月报当然还没出。逐月按标题去检索接口要链接，
    检索不到就当作「这一期还没发」跳过（并打印），不抛异常。
    """
    end = end or _prev_month(_today_month())
    rows, missing = [], []
    for month in _months(start, end):
        title = f'LSEG market report {_month_label(month)}'
        hit = _find_doc(title)
        if hit is None:
            missing.append(month)
            continue
        fn = os.path.join(CACHE, f'mmr_{month}.pdf')
        _download(hit['url'], fn)
        try:
            rec = parse_report(fn, month)
        except TypeError:
            raise LsegOrderbookFetchError(
                f'{month}: {os.path.basename(hit["url"])} 第 1 页不是 '
                f'"LSEG - Electronic Order Book Trading" 表 —— 官方换排版了')
        rec['month'] = month
        rec['_src_url'] = hit['url']
        rows.append(rec)
        if verbose:
            print(f'[lseg_orderbook] {month} ok  LSE £{rec["lse_orderbook_value_gbp_m"]:,.0f}m '
                  f'/ {rec["lse_orderbook_trades_count"]:,} trades')
        time.sleep(0.25)                            # 对官方站客气一点

    if not rows:
        raise LsegOrderbookFetchError(f'{start}..{end} 一期月报都没抓到')
    if missing:
        print(f'[lseg_orderbook] 检索接口没有这些月份的月报: {missing}')
    if crosscheck:
        n = _crosscheck(rows, _xlsx_monthly())
        print(f'[lseg_orderbook] 双源核对通过 {n}/{len(rows)} 个月')
    rows.sort(key=lambda r: r['month'])
    return rows


def _fmt(v):
    if isinstance(v, float) and v == int(v):
        return str(int(v))
    return str(v)


def write_csv(rows, series_dir=SERIES):
    """写 series/lseg_part_orderbook.csv（首列 month，升序）。只填空不覆盖。"""
    path = os.path.join(series_dir, 'lseg_part_orderbook.csv')
    have = {}
    if os.path.exists(path):
        with open(path, newline='', encoding='utf-8') as f:
            rd = list(csv.reader(f))
        if rd:
            head = rd[0]
            if head != ['month'] + COLUMNS:
                raise LsegOrderbookFetchError(
                    f'已有 CSV 的列与本模块不一致，拒绝覆盖:\n  旧 {head}\n  新 {["month"] + COLUMNS}')
            have = {r[0]: r for r in rd[1:] if r}
    for r in rows:
        if r['month'] in have:
            continue                                # 幂等：已有月份不重写
        have[r['month']] = [r['month']] + [_fmt(r[c]) for c in COLUMNS]
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f, lineterminator='\n')
        w.writerow(['month'] + COLUMNS)
        for k in sorted(have):
            w.writerow(have[k])
    return path


def cadence(rows=None):
    """实测发布节奏：读每期 PDF 内嵌 CreationDate，算相对数据月月末的日历天数。"""
    import fitz
    out = []
    for fn in sorted(os.listdir(CACHE)) if os.path.isdir(CACHE) else []:
        m = re.match(r'^mmr_(\d{4})-(\d{2})\.pdf$', fn)
        if not m:
            continue
        month = f'{m.group(1)}-{m.group(2)}'
        raw = (fitz.open(os.path.join(CACHE, fn)).metadata or {}).get('creationDate') or ''
        d = re.match(r"D:(\d{4})(\d{2})(\d{2})", raw)
        if not d:
            continue
        made = datetime.date(int(d.group(1)), int(d.group(2)), int(d.group(3)))
        y, mo = int(m.group(1)), int(m.group(2))
        eom = (datetime.date(y + (mo == 12), (mo % 12) + 1, 1) - datetime.timedelta(days=1))
        out.append((month, made.isoformat(), (made - eom).days))
    return out


def main():
    import sys
    if '--cadence' in sys.argv:
        for month, made, lag in cadence():
            print(f'{month}\t{made}\t+{lag}d')
        return
    rows = fetch_rows()
    path = write_csv(rows)
    print(f'[lseg_orderbook] {len(rows)} 个月 '
          f'{rows[0]["month"]}..{rows[-1]["month"]} → {path}')


if __name__ == '__main__':
    main()
