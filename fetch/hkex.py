# -*- coding: utf-8 -*-
"""HKEX 香港交易所 00388 —— 月度市场统计抓取模块（无人值守）。

═══ 数据源 ═══
本模块有**两条互不相干的官方链路**，各管一批列，谁挂了另一条照跑：

  A. hkexgroup.com 的「Monthly HK Market Highlight Data」xlsx
     → adt_hkdbn / mktcap_hkdtn / new_listings / ipo_funds_hkdbn /
       derivatives_adv_contracts / southbound_adt_hkdbn（下面「数据源」整节讲的都是它）

  B. hkex.com.hk 的 Monthly Bulletin 报表 JSON（逐日档案 + 每月 Stock market highlights）
     → trading_days_cash / vol_shares_* / trades_* / adv_shares_mn / adt_trades
       （见文件后半「═══ 成交股数与成交笔数 ═══」那一节）

链路 A 的真值文件：HKEX 官方「Monthly HK Market Highlight Data」Excel
    落地页  https://www.hkexgroup.com/Investor-Relations/Business-Analysis/Key-Market-Data?sc_lang=en
    直链模板 https://www.hkexgroup.com/-/media/HKEX-Group-Site/Ir/Monthly-market-highlights/
             HKEX-HK-market-monthly-highlight-statistics-(Updated-to-{Mon}-{YYYY}).xlsx
             例：...(Updated-to-Jun-2026).xlsx

为什么不写死直链、而是先去落地页抓 href：
    文件名里带月份，写死等于每月都要改代码；而 HKEX 偶尔会跳月或改大小写。
    落地页上那一条「Monthly HK Market Highlight Data Download (Updated to X)」链接
    是官方自己维护的「当前最新」指针，跟着它走才是真正无人值守。
    落地页挂了才退回按月份倒推试直链（_probe_direct），两条腿都断才抛异常。

反爬情况（2026-08-05 实测）：
    hkexgroup.com 与其 /-/media/ 静态资源都没有 Cloudflare / Akamai 交互式挑战。
    python urllib + 普通桌面 UA 即可 200，curl 亦可。不需要浏览器、不需要登录态。
    唯一坑：路径大小写敏感，且带 `?sc_lang=en` 的页面路径写错会返回 404 而不是 302。

═══ 发布节奏 ═══
    次月上旬发布上一个月的数据。实测 Last-Modified：
        2025-10 → 11/11、2025-11 → 12/08、2025-12 → 01/08、2026-01 → 02/09、
        2026-02 → 03/17（异常晚，疑似重传）、2026-03 → 04/09、
        2026-04 → 05/08、2026-05 → 06/04、2026-06 → 07/07
    ⇒ 定时任务排在**次月 10 日之后**跑最稳；10 号之前跑很可能扑空，
      这不是故障，latest_month() 会如实返回上上个月。

═══ 发布日（页面抬头「官方发布于」那半句）═══
    HKEX **哪儿都不写发布日**：工作簿里没有 "Updated on …" 之类的字符串（整表扫过），
    落地页那条链接只写 "(Updated to Jun 2026)" —— 那是数据月，不是发布日；
    也没有配套的新闻稿。所以本家只能用上面那张表的口径：**xlsx 直链的 HTTP
    Last-Modified**，它本来就是本模块记录发布节奏的实测依据。
    另有一条独立佐证写在文件肚子里：工作簿 docProps/core.xml 的 dcterms:modified
    （HKEX 自己的 Excel 存盘时刻，Company = "Hong Kong Exchanges and Clearing"）。
    2026-06 档两者相差 11 秒（存盘 07-07 10:24:36Z、上线 07-07 10:24:47 GMT），
    说明存盘即上传，用 Last-Modified 当发布日是站得住的。
    ⇒ 只在**首次摄入某个月**时记一笔（见 update()），事后不覆盖：HKEX 会原地重传，
      重传会把 Last-Modified 推后，拿它盖掉当初那次真发布的日期就是把事实改错。

═══ 口径坑（都是真踩过的，不是想象的）═══
1. 表是**横排**的：第 1 列是指标名，第 2 列起每列一个月（2018-01 起，逐月累加，不滚动）。
   行号会因为 HKEX 新上产品而整体下移（例如 2025-11 新增 Hang Seng Biotech Index Futures），
   所以本模块一律**按指标名定位行**，绝不按行号硬编码。

2. `Equities - IPO Total*` 这个标签在文件里**出现两次**（Main Board 段 + GEM 段），
   必须靠上方的段落标题 `FUND RAISED AMOUNT BY TYPES (MAIN BOARD)/(GEM)` 区分。
   series 里的 ipo_funds_hkdbn = 两段之和（GEM 近年恒为 0，但别省）。

3. **IPO 募资额是"暂定数"，会被下个月的文件上修**（表里原文脚注：
   "* Provisional figures for latest month"）。实测幅度：
       2025-11  40,455.8 →(Dec 档) 41,832.2   +3.4%
       2026-01  39,179.8 →(Feb 档) 42,298     +8.0%
       2026-05  13,357.3 →(Jun 档) 14,431.4   +8.0%
   ⇒ 本月刚发布的 ipo_funds_hkdbn 天生偏低，不要拿它做同比结论。
   ⇒ 本模块**默认不覆盖 series 里已有的非空数值**（见 update(allow_restate)），
     免得历史被官方重述悄悄改掉；差异会写进 cache/hkex_restatements.csv 供人工判断。

4. series 里有三段**故意的留白**，别手贱回填：
       new_listings   2019-01~2024-05 空（当年逐月简报没这项）
       ipo_funds      2019-01~2023-12 空（同上）
       southbound     2022-01~2025-06 空（官方停发了 40 个月，
                      build_hkex.py 的 multi_line 图注专门讲了这个 gap）
   今天这份 xlsx 其实把 2018-01 起的这些历史都补全了，但一次性回填 =
   把两代口径混进同一条序列、并改掉看板叙事，属于人工决策。
   ⇒ update() 只对「adt 为空的行」补空 + 追加新月，adt 已有的历史行一个字节都不碰。

5. mktcap 是月末时点数（$Bil.→ /1000 得 HK$tn）；ADT / 南向 ADT / 衍生品 ADV 是月内日均。
   南向 ADT 官方口径含买卖双边（表内注 "ADT for Stock Connect includes buy and sell trades"）。

6. series/hkex.csv 是 **CRLF** 换行、无引号、7 列定宽小数
   （adt 3 位 / mktcap 4 位 / new_listings 整数 / ipo 3 位 / deriv 整数 / 南向 3 位）。
   本模块逐行改写文本、不经 pandas.to_csv，就是为了保证没动过的行**逐字节不变**。

7. 已知遗留：series 里 2026-07 那一行的 ipo/deriv/southbound 有值而 adt/mktcap/new_listings 为空，
   且 2025-12、2026-06 的 ipo 高于官方 xlsx 任何一版。说明前人对最新月用过一个
   比 xlsx 更快的**未知来源**。本模块不假装知道那是什么，也不去动它，
   只在 7 月档 xlsx 出来后把空格补上，并把冲突记进 cache/hkex_restatements.csv。


═══ 成交股数与成交笔数（链路 B）═══
上面那份 Monthly Market Highlights xlsx 的现货段**只有三行**（ADT、市值、新上市），
成交股数与成交笔数根本不在里面。它们在 HKEX 的**另一份刊物 Monthly Bulletin**（月报），
栏目原文就叫 `Turnover volume (mil shares)` 与 `No. of deals`，
两行都同时给「当月合计」和「- Daily average」。主板与 GEM 分册发布。

本模块用的两个端点（都在 https://www.hkex.com.hk/eng/stat/smstat/mthbull/ 下）：

  B1【历史主力】Securities Statistics Archive —— Trading value, volume and number of deals
     索引 rpt_data_statistics_archive_trading_data.json      （主板）
          rpt_data_statistics_archive_trading_data_gem.json  （GEM）
     索引里每条指向一册 5 年期的**逐日**表，列是
         Year/Month/Day │ │ Total trading value (HKD) │ Total trading volume (Shares) │ Number of deals
     主板最老一册标签 1986-1989、GEM 1999-2003 —— 也就是逐日档案能回到 1980 年代。
     逐日 → 逐月只做**求和与计数**，不做任何口径改写。

  B2【最新月 + 交叉核对】Monthly Bulletin —— Stock market highlights
     rpt_Stock_market_highlights_{YYMM}.json       （主板）
     rpt_Stock_market_highlights_GEM_{YYMM}.json   （GEM）
     只挂**最近 13 个月**（更早的月份 404，实测 2412/2312/2212/2505 全 404），
     所以它当不了历史来源，但它有两个不可替代的用处：
       ① 比逐日档案快。实测 2026-06：Bulletin 07-02 14:02 GMT 就上线了，
          逐日档案 07-02 14:59 GMT 同日跟上；而 2026-07 的 Bulletin 08-03 14:04 GMT
          已经上线，逐日档案到 08-07 仍停在 06-30（带 no-cache 复核过，不是 CDN 缓存）。
          ⇒ 逐日档案对最新月**会落后整整一个月**，最新月必须靠 B2。
       ② 给 B1 当闸门。逐日档案的最后一个月有可能是「月中快照」（合计天生偏小），
          从档案本身看不出来。所以本模块规定：**档案的最后一个月必须被同月的
          Bulletin 逐位确认才收**，确认不了就整月不要（见 _trading_stats）。

  为什么不用 hkexgroup.com 那份 xlsx 顺手带出来：它压根没有这两行，试过了。

── 三重闭合（2026-08-07 本机实测，逐位相同，不是四舍五入到差不多）──
  ① 逐日档案汇总（主板，2026-06，21 个交易日）
        成交额 6,698,704,112,075 HKD → 6,698,704 HK$mil，日均 318,986 HK$mil
        成交股数 7,370,724,218,440 股 → 7,370,724 mil sh，日均 350,987 mil sh
        成交笔数 100,533,281 笔，日均 4,787,299 笔
     Monthly Bulletin 2606 主板同月原文：6,698,704 / 318,986、7,370,724 / 350,987、
        100,533,281 / 4,787,299 —— **六个数逐位相同**。
  ② 主板日均成交额 318.986 + GEM 日均成交额 0.090 = 319.076 HK$bn
     = series/hkex.csv 2026-06 的 adt_hkdbn **319.076**，逐位相同。
  ③ 把 ② 推广到全序列：series 里 90 个有 adt_hkdbn 的月（2019-01~2026-06），
     用 B1 逐日档案（主板+GEM）重算日均成交额，**90/90 全部在 3 位小数上逐位相同**。
     ⇒ 新列与既有 adt_hkdbn 是**同一套逐日底稿**，口径天然一致，不是"看着差不多"。

── 口径 ──
  · 「主板+GEM」：合计口径与 adt_hkdbn 完全对齐（adt_hkdbn 就是两板之和，见闭合 ②）。
  · 交易日：以主板逐日档案的行数为准。GEM 与主板同一个交易日历，2019-01~2026-06
    实测 90 个月两边行数**从无差异**；万一将来差了会打印警告并仍以主板为准
    （GEM 只占成交额的 0.03%，用主板日历不会改变任何结论）。
  · 半日市：档案在日期后打 `*`（圣诞前夕 / 除夕 / 年三十，以及 2020-08-19、2021-06-28、
    2022-08-25、2023-10-09 这类台风黑雨缩短交易时段的日子）。HKEX 自己的日均**照算一整天**——
    这是闭合 ③ 90/90 反推出来的事实，不是假设：含半日市的月份（如 2025-01、2024-02）
    如果按 0.5 天折算，日均就对不上官方数了。所以本模块也不折算。
  · 单位：档案发的是**股**，Bulletin 发的是**百万股**。本模块统一按 Bulletin 的
    `mil shares` 存（档案值 ÷ 1e6），与既有列把 HK$mil ÷1000 存成 HK$bn 是同一类换算——
    只换单位刻度，不换口径、不引入任何外部参数。
  · 「笔数」= HKEX 原文 `No. of deals`（成交宗数）。列名用 trades 是跟仓里
    asx.csv 的 trades_cash_total / adt_cash_trades、enx.csv 的 adv_cash_trades_k 对齐。

── 发布节奏与滞后 ──
  Bulletin：次月上旬，实测 2026-06 档 07-02、2026-07 档 08-03（Last-Modified, GMT）。
            比链路 A 的 xlsx 还早 ~5 天（2026-06 的 xlsx 是 07-07）。
  逐日档案：正常也是次月上旬同日跟上（2026-06 档 07-02 14:59 GMT），
            但 2026-07 这一轮明显掉队（到 08-07 未更新）。这正是要留 B2 兜底的原因。

── 历史深度：为什么只补到 series 现有的最早月，不往前加行 ──
  逐日档案能回到 1986（主板）/ 1999（GEM），足够把这两列铺到 1990 年代。
  但 series/hkex.csv 现在是 2019-01 起，往前加行会改变 build/hkex.py 里
  df.index[0] 与全部窗口函数的输入，而那些文件不归本模块管。
  ⇒ 本模块**只给已存在的行补格，绝不新增早于序列首月的行**。
    真要往前铺，改法是一行：把 _trading_stats 的 since_year 放宽 + 允许 append，
    但那是人工决策（要连带确认 build 侧的图注与窗口），不该由无人值守任务顺手做掉。
"""

import csv
import datetime as _dt
import email.utils
import io
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
import zipfile

# ── 常量 ──────────────────────────────────────────────────────────────────
LANDING_URLS = (
    'https://www.hkexgroup.com/Investor-Relations/Business-Analysis/Key-Market-Data?sc_lang=en',
    'https://www.hkexgroup.com/?sc_lang=en',   # 首页也挂同一条链接，作为备份锚点
)
MEDIA_BASE = ('https://www.hkexgroup.com/-/media/HKEX-Group-Site/Ir/Monthly-market-highlights/'
              'HKEX-HK-market-monthly-highlight-statistics-(Updated-to-%s-%d).xlsx')
_HREF_RE = re.compile(
    rb'HKEX-HK-market-monthly-highlight-statistics-\(Updated-to-([A-Za-z]{3})-(\d{4})\)\.xlsx')

# 普通桌面 UA 就够；不要用 curl 默认 UA，HKEX 的 CDN 对它偶发 403
_UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
       '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36')
_HEADERS = {'User-Agent': _UA, 'Accept-Language': 'en-US,en;q=0.9'}

_MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

# 发布方在香港，发布日按它自己的日历算。实测最近 10 档的上线时刻落在 09:43–19:32 HKT
# （01:43–11:32 GMT），换不换时区都是同一天 —— 转成港时只是把口径写明确，不是为了改日期。
_HK = _dt.timezone(_dt.timedelta(hours=8))

SHEET = 'Monthly Data'

# series/hkex.csv 的列顺序与小数位。改这里等于改 CSV 格式，别改。
#
# HIGHLIGHT_COLUMNS = 链路 A（hkexgroup.com 的 xlsx）供数的 6 列，历来就有。
# TRADING_COLUMNS   = 链路 B（hkex.com.hk 的 Monthly Bulletin 报表 JSON）供数的 7 列，
#                     2026-08 新增，一律追加在末尾 —— 旧列的位置一格都不动。
HIGHLIGHT_COLUMNS = ['adt_hkdbn', 'mktcap_hkdtn', 'new_listings', 'ipo_funds_hkdbn',
                     'derivatives_adv_contracts', 'southbound_adt_hkdbn']
TRADING_COLUMNS = ['trading_days_cash',        # 现货交易日数（主板日历；半日市算整天）
                   'vol_shares_mb_mn',         # 当月成交股数合计 · 主板（百万股）
                   'vol_shares_gem_mn',        # 当月成交股数合计 · GEM（百万股）
                   'trades_mb_total',          # 当月成交笔数合计 · 主板（No. of deals）
                   'trades_gem_total',         # 当月成交笔数合计 · GEM
                   'adv_shares_mn',            # 日均成交股数 · 主板+GEM（百万股）
                   'adt_trades']               # 日均成交笔数 · 主板+GEM
COLUMNS = HIGHLIGHT_COLUMNS + TRADING_COLUMNS

# 新 7 列全是整数位：股数已经以「百万股」为单位（末位 = 100 万股，占日均的 3e-6），
# 笔数与交易日本来就是计数。整数位同时让「逐日档案算出来的值」与
# 「Bulletin 印出来的值」落在同一个刻度上，两条链路互为替代时不会因为精度打架。
_DECIMALS = {'adt_hkdbn': 3, 'mktcap_hkdtn': 4, 'new_listings': 0, 'ipo_funds_hkdbn': 3,
             'derivatives_adv_contracts': 0, 'southbound_adt_hkdbn': 3,
             'trading_days_cash': 0, 'vol_shares_mb_mn': 0, 'vol_shares_gem_mn': 0,
             'trades_mb_total': 0, 'trades_gem_total': 0,
             'adv_shares_mn': 0, 'adt_trades': 0}

# 指标名 → (段落限定, 精确/前缀匹配的标签)。段落为 None 表示全表唯一。
# 用 tuple 是因为 IPO 那一行标签重名，必须靠段落标题夹住。
_ROWSPEC = {
    'mktcap_bil':   (None, 'Total market capitalisation ($Bil.)'),
    'newlist_mb':   (None, 'No. of newly listed companies (Main Board)'),
    'newlist_gem':  (None, 'No. of newly listed companies (GEM)'),
    'ipo_mb_mil':   ('FUND RAISED AMOUNT BY TYPES  (MAIN BOARD)', 'Equities - IPO Total'),
    'ipo_gem_mil':  ('FUND RAISED AMOUNT BY TYPES  (GEM)', 'Equities - IPO Total'),
    'adt_mil':      (None, 'Average daily turnover by value'),
    'southbound_mil': (None, 'Total Southbound average daily turnover by value'),
    'deriv_adv':    (None, 'Total Futures and Options'),
}


class HkexFetchError(RuntimeError):
    """抓取或解析失败。调度器看到它就该报警，而不是当成'本月没数据'。"""


# ── 网络 ──────────────────────────────────────────────────────────────────
def _get(url, timeout=90, want_headers=False):
    """want_headers=True 时连响应头一起给出去 —— 发布日只能从 Last-Modified 拿
    （HKEX 的文件与页面都不写发布日，见模块 docstring），而响应头一旦出了这个
    with 块就没了，事后补一次 HEAD 拿到的可能已经是下一次重传的时刻。"""
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        blob = r.read()
        return (blob, r.headers.get('Last-Modified')) if want_headers else blob


def _discover_url():
    """从官方落地页读出「当前最新」那一份 xlsx 的直链。

    返回 (url, 'YYYY-MM')。落地页给的月份只是文件名上的声明，
    真实最新月以解析结果为准（见 _parse）。
    """
    errs = []
    for page in LANDING_URLS:
        try:
            html = _get(page, timeout=60)
        except Exception as e:                      # noqa: BLE001
            errs.append('%s -> %r' % (page, e))
            continue
        hits = set(_HREF_RE.findall(html))
        if not hits:
            errs.append('%s -> 页面 200 但没匹配到 xlsx 链接（版式可能改了）' % page)
            continue
        # 页面上可能同时挂着旧档，取月份最大的那个
        best = max(hits, key=lambda t: (int(t[1]), _MON.index(t[0].decode().capitalize()) + 1))
        mon, year = best[0].decode().capitalize(), int(best[1])
        return MEDIA_BASE % (mon, year), '%04d-%02d' % (year, _MON.index(mon) + 1)
    raise HkexFetchError('落地页发现失败：\n  ' + '\n  '.join(errs))


def _probe_direct(max_back=6):
    """落地页不可用时的退路：按 (Mon-YYYY) 从上个月往前倒推试直链。

    为什么从"上个月"起：当月数据永远要等次月上旬才发，当月档必然 404。
    """
    today = _dt.date.today()
    y, m = today.year, today.month
    tried = []
    for _ in range(max_back):
        m -= 1
        if m == 0:
            m, y = 12, y - 1
        url = MEDIA_BASE % (_MON[m - 1], y)
        try:
            req = urllib.request.Request(url, headers=_HEADERS, method='HEAD')
            with urllib.request.urlopen(req, timeout=45) as r:
                if r.status == 200:
                    return url, '%04d-%02d' % (y, m)
        except Exception as e:                      # noqa: BLE001
            tried.append('%s-%d %r' % (_MON[m - 1], y, e))
    raise HkexFetchError('直链倒推也失败：' + '; '.join(tried))


def _download(cache_dir):
    """把最新一档 xlsx 落到 cache_dir，返回 (本地路径, 文件名声明的月份, Last-Modified 原文)。

    每次都重新下载：文件才 ~160KB，而 HKEX 会**原地重传**同名文件
    （2026-02 档的 Last-Modified 就晚到了 3/17），缓存命中反而会漏掉重述。
    """
    os.makedirs(cache_dir, exist_ok=True)
    try:
        url, claimed = _discover_url()
    except HkexFetchError as e:
        url, claimed = _probe_direct()
        print('[hkex] 落地页发现失败(%s)，改用直链倒推：%s' % (e, url))
    blob, last_modified = _get(url, want_headers=True)
    if not blob.startswith(b'PK'):                   # xlsx 必须是 zip；返回 HTML 说明被挡或路径错
        raise HkexFetchError('下载到的不是 xlsx（前 16 字节 %r），URL=%s' % (blob[:16], url))
    path = os.path.join(cache_dir, 'hkex_monthly_highlights_%s.xlsx' % claimed)
    with open(path, 'wb') as f:
        f.write(blob)
    return path, claimed, last_modified


# ── 发布日 ────────────────────────────────────────────────────────────────
_SAVED_RE = re.compile(rb'<dcterms:modified[^>]*>'
                       rb'(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}:\d{2})Z?</dcterms:modified>')


def _doc_saved_at(xlsx_path):
    """工作簿自己记的最后存盘时刻（docProps/core.xml 的 dcterms:modified，UTC）。

    这是 HKEX 那台 Excel 写进文件肚子里的时间戳，不是我们下载的时间，也不受 CDN 影响，
    所以它能给 Last-Modified 当独立佐证。取不到就 None —— 它只是佐证，不该让抓取失败。
    """
    try:
        with zipfile.ZipFile(xlsx_path) as z:
            hit = _SAVED_RE.search(z.read('docProps/core.xml'))
    except (OSError, KeyError, zipfile.BadZipFile):
        return None
    if not hit:
        return None
    return _dt.datetime.strptime(hit.group(1).decode() + ' ' + hit.group(2).decode(),
                                 '%Y-%m-%d %H:%M:%S').replace(tzinfo=_dt.timezone.utc)


def _published_on(xlsx_path, last_modified):
    """这一档 xlsx 的发布日，返回 ("YYYY-MM-DD", 出处描述)；判断不出来就 (None, None)。

    HKEX 不写发布日（工作簿、落地页都只写数据月），所以这里用的是 HTTP Last-Modified ——
    本模块 docstring 的「发布节奏」表一直就是按它记的。出处描述里把原始头和佐证都写全，
    将来有人怀疑某个日期，不用重新做一遍考古。
    """
    saved = _doc_saved_at(xlsx_path)
    online = None
    if last_modified:
        try:
            online = email.utils.parsedate_to_datetime(last_modified)
        except (TypeError, ValueError):
            online = None
    # 头缺失时退回工作簿存盘时刻：存盘早于上线，宁可偏早也不编一个。
    ref, src = (online, 'online') if online else (saved, 'saved')
    if ref is None:
        return None, None
    iso = ref.astimezone(_HK).date().isoformat()

    if src == 'online':
        ev = ('xlsx 直链 HTTP Last-Modified: %s（= %s HKT）'
              % (last_modified, online.astimezone(_HK).strftime('%Y-%m-%d %H:%M')))
        if saved:
            same = saved.astimezone(_HK).date().isoformat() == iso
            ev += ('；工作簿 docProps/core.xml dcterms:modified=%s %s'
                   % (saved.strftime('%Y-%m-%dT%H:%M:%SZ'),
                      '同日，互为印证' if same else '不同日（疑似原地重传），以上线时刻为准'))
    else:
        ev = ('响应无 Last-Modified，退回工作簿 docProps/core.xml dcterms:modified=%s（= %s HKT）'
              % (saved.strftime('%Y-%m-%dT%H:%M:%SZ'), saved.astimezone(_HK).strftime('%Y-%m-%d %H:%M')))
    return iso, ev + '。HKEX 的工作簿与落地页都不写发布日，落地页只写数据月 "Updated to …"'


def _source_dates():
    """按路径加载仓库根的 source_dates.py（发布日台账）。

    不能裸 import：本模块是被 monthly_run 用 spec_from_file_location 加载的，
    那时 sys.path 上既没有 fetch/ 也没有仓库根。
    """
    import importlib.util
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    spec = importlib.util.spec_from_file_location(
        'source_dates', os.path.join(root, 'source_dates.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _record_source_date(series_dir, month, xlsx_path, last_modified):
    """把该月的发布日记进台账。失败只告警，不抛。

    调用点在 series 落盘之后：数据已经进库了，再为「抬头那半句话」把整月抓取判成失败，
    赔本。写不进去的后果是页面少半句，不是数据错。
    """
    iso, ev = _published_on(xlsx_path, last_modified)
    if not iso:
        print('[hkex] %s 拿不到发布日（无 Last-Modified 也无 docProps 时间戳），台账留空' % month)
        return
    try:
        _source_dates().record(series_dir, 'hkex', month, iso, ev)
    except Exception as e:                          # noqa: BLE001
        print('[hkex] 发布日台账没写成（%r），series 数据不受影响' % (e,))


# ── 解析 ──────────────────────────────────────────────────────────────────
def _find_rows(ws):
    """按标签定位行号；缺任何一个必需标签直接抛异常。

    这是最重要的一道闸：HKEX 一旦改版式（改标签、拆表、换 sheet），
    宁可让任务红着停掉，也不能让 update() 写出一串 NaN。
    """
    labels = []
    for r in range(1, ws.max_row + 1):
        v = ws.cell(r, 1).value
        labels.append(v.replace('\xa0', ' ').strip() if isinstance(v, str) else None)

    def section_of(r):
        """向上找最近一个全大写的段落标题。"""
        for i in range(r - 1, 0, -1):
            s = labels[i - 1]
            if s and s.isupper() and len(s) > 8:
                return s
        return None

    out = {}
    missing = []
    for key, (sec, lab) in _ROWSPEC.items():
        hit = None
        for r in range(1, len(labels) + 1):
            s = labels[r - 1]
            if not s or not s.startswith(lab):
                continue
            if sec is not None and section_of(r) != sec:
                continue
            hit = r
            break
        if hit is None:
            missing.append('%s（段落=%s，标签=%s）' % (key, sec, lab))
        out[key] = hit
    if missing:
        raise HkexFetchError('xlsx 版式变了，找不到这些指标行：' + '；'.join(missing))
    return out


def _num(v):
    """'-' / None / 空 一律当缺失；HKEX 用 '-' 表示该产品当月不存在。"""
    if v is None or v == '' or v == '-':
        return None
    if isinstance(v, str):
        v = v.replace(',', '').strip()
        if v in ('', '-', 'N/A'):
            return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _parse(path):
    """xlsx → {'YYYY-MM': {列名: 数值 or None}}，只保留 series 的 6 列口径。"""
    import openpyxl                                   # 延迟 import，纯读 CSV 的调用方不用装

    wb = openpyxl.load_workbook(path, data_only=True, read_only=False)
    if SHEET not in wb.sheetnames:
        raise HkexFetchError('xlsx 里没有 sheet %r（现有：%s）' % (SHEET, wb.sheetnames))
    ws = wb[SHEET]

    # 月份表头：第 2 列起是日期。别写死第 2 行，HKEX 加过说明行。
    hdr_row = None
    for r in range(1, 9):
        if isinstance(ws.cell(r, 2).value, _dt.datetime):
            hdr_row = r
            break
    if hdr_row is None:
        raise HkexFetchError('找不到月份表头行（前 8 行第 2 列都不是日期）')
    cols = {}
    for c in range(2, ws.max_column + 1):
        v = ws.cell(hdr_row, c).value
        if isinstance(v, _dt.datetime):
            cols['%04d-%02d' % (v.year, v.month)] = c
    if not cols:
        raise HkexFetchError('月份表头行没有任何日期列')

    rows = _find_rows(ws)
    data = {}
    for month, c in cols.items():
        g = {k: _num(ws.cell(r, c).value) for k, r in rows.items()}

        def add(a, b):
            """两段相加；两边都缺才算缺（GEM 段常年 0，但偶尔留空）。"""
            if g[a] is None and g[b] is None:
                return None
            return (g[a] or 0.0) + (g[b] or 0.0)

        data[month] = {
            'adt_hkdbn': None if g['adt_mil'] is None else g['adt_mil'] / 1000.0,
            'mktcap_hkdtn': None if g['mktcap_bil'] is None else g['mktcap_bil'] / 1000.0,
            'new_listings': add('newlist_mb', 'newlist_gem'),
            'ipo_funds_hkdbn': (lambda v: None if v is None else v / 1000.0)(
                add('ipo_mb_mil', 'ipo_gem_mil')),
            'derivatives_adv_contracts': g['deriv_adv'],
            'southbound_adt_hkdbn': (None if g['southbound_mil'] is None
                                     else g['southbound_mil'] / 1000.0),
        }
    return data


def _materially_differs(col, old_s, new_s):
    """末位 1 个单位以内的差算舍入噪声，不算重述。"""
    try:
        a, b = float(old_s), float(new_s)
    except ValueError:
        return True
    return abs(a - b) > 10.0 ** (-_DECIMALS[col]) + 1e-12


def _fmt(col, val):
    if val is None:
        return ''
    d = _DECIMALS[col]
    return ('%d' % round(val)) if d == 0 else ('%.*f' % (d, val))


# ══ 链路 B：成交股数 / 成交笔数 ═══════════════════════════════════════════
# 端点、口径、闭合证据全部写在模块 docstring 的「═══ 成交股数与成交笔数 ═══」一节，
# 这里只放代码。改动这一段前先把那节读完，尤其是「档案最后一个月必须被 Bulletin 确认」
# 那条闸门 —— 它是唯一能挡住「月中快照被当成整月合计入库」的东西。

_BULL_BASE = 'https://www.hkex.com.hk/eng/stat/smstat/mthbull/'
_ARCHIVE_INDEX = {
    'mb':  _BULL_BASE + 'rpt_data_statistics_archive_trading_data.json',
    'gem': _BULL_BASE + 'rpt_data_statistics_archive_trading_data_gem.json',
}
_HIGHLIGHT_URL = {
    'mb':  _BULL_BASE + 'rpt_Stock_market_highlights_%s.json',
    'gem': _BULL_BASE + 'rpt_Stock_market_highlights_GEM_%s.json',
}
_BOARDS = ('mb', 'gem')
_BOARD_ZH = {'mb': '主板', 'gem': 'GEM'}

_ARCH_DATE_RE = re.compile(r'^(\d{4})/(\d{2})/(\d{2})$')
_BUCKET_RE = re.compile(r'_(\d{4})_(\d{4})\.json$')
_MON_FULL = ['January', 'February', 'March', 'April', 'May', 'June',
             'July', 'August', 'September', 'October', 'November', 'December']

# 逐日表的三个数值列。按**表头文字**认列，不按列号 —— 表头之间还夹着一个空列
# （放半日市那颗 `*`），HKEX 将来挪一下列序，认文字的写法不会静默错位。
_ARCH_COLS = (('value', 'Total trading value'),
              ('volume', 'Total trading volume'),
              ('deals', 'Number of deals'))

# Stock market highlights 里要的三行。用 startswith 匹配：HKEX 在标签尾部挂了
# `<br/>- Daily average`，而且 "No. of deals " 后面还有个尾随空格。
_HL_ROWS = (('value', 'Turnover value (HK$mil)'),
            ('volume', 'Turnover volume (mil shares)'),
            ('deals', 'No. of deals'))


def _tidy(s):
    """报表 JSON 的单元格文本 → 纯文本。`<br/>` 转成换行（Bulletin 靠它把
    「当月合计」和「日均」塞进同一格），其余标签与 &nbsp; 一律抹掉。"""
    s = re.sub(r'<\s*br\s*/?\s*>', '\n', s or '')
    s = re.sub(r'<[^>]+>', ' ', s)
    s = s.replace('\xa0', ' ').replace('&nbsp;', ' ')
    return '\n'.join(re.sub(r'\s+', ' ', ln).strip() for ln in s.split('\n')).strip()


def _grid(table, key):
    """report JSON 的 header/body 单元格列表 → 二维文本表（行内按 col 对齐补空）。"""
    cells = table.get(key) or []
    if not cells:
        return []
    ncol = max(c['col'] for c in cells) + 1
    rows = {}
    for c in cells:
        rows.setdefault(c['row'], {})[c['col']] = c.get('text', '')
    return [[rows[r].get(i, '') for i in range(ncol)] for r in sorted(rows)]


def _json_get(url, cache_dir=None, cache_name=None):
    """GET 一个 HKEX 报表 JSON。顺手把原文落到 cache/（gitignore 的），
    出了争议能拿原始档对账，不用重新做一遍考古。"""
    blob = _get(url, timeout=120)
    if cache_dir and cache_name:
        try:
            os.makedirs(cache_dir, exist_ok=True)
            with open(os.path.join(cache_dir, cache_name), 'wb') as f:
                f.write(blob)
        except OSError:
            pass                                  # 缓存写不进去不该让抓取失败
    try:
        return json.loads(blob.decode('utf-8-sig'))
    except ValueError as e:
        raise HkexFetchError('%s 返回的不是 JSON（%s；前 80 字节 %r）' % (url, e, blob[:80]))


def _int(txt):
    """'100,533,281' → 100533281。逐日档案里 21,390 个数值格实测**全是整数**
    （2026-08-07 全量扫过），所以这里不接受小数：真出现小数说明版式变了，该响。"""
    s = _tidy(txt).replace(',', '')
    if not re.match(r'^\d+$', s):
        raise HkexFetchError('逐日档案里出现非整数数值 %r' % txt)
    return int(s)


def _archive_daily(board, since_year, cache_dir):
    """某个板块的逐日档案 → {'YYYY-MM': [交易日数, 成交额HKD, 成交股数股, 成交笔数]}。

    只下载**年份区间覆盖到 since_year 及以后**的分册：每册 ~600KB，全下 9 册纯属浪费；
    但也绝不按「当前年份」猜册名 —— 册名与区间一律从官方索引读。
    """
    idx = _json_get(_ARCHIVE_INDEX[board], cache_dir, 'hkex_archive_index_%s.json' % board)
    if not isinstance(idx, list) or not idx:
        raise HkexFetchError('%s 逐日档案索引不是非空数组（版式可能改了）：%s'
                             % (_BOARD_ZH[board], _ARCHIVE_INDEX[board]))
    picked, skipped = [], []
    for it in idx:
        url = (it or {}).get('url') or ''
        m = _BUCKET_RE.search(url)
        if not m:
            skipped.append(url)
            continue
        lo, hi = int(m.group(1)), int(m.group(2))
        if hi >= since_year:
            picked.append((lo, hi, urllib.parse.urljoin(_BULL_BASE, url)))
    if not picked:
        raise HkexFetchError('%s 逐日档案索引里没有覆盖 %d 年及以后的分册（索引 %d 条，'
                             '认不出册名的 %d 条）' % (_BOARD_ZH[board], since_year,
                                                      len(idx), len(skipped)))

    out = {}
    for lo, hi, url in sorted(picked):
        doc = _json_get(url, cache_dir, 'hkex_archive_%s_%d_%d.json' % (board, lo, hi))
        tables = doc.get('tables') or []
        if not tables:
            raise HkexFetchError('%s 逐日档案 %d-%d 没有 tables' % (_BOARD_ZH[board], lo, hi))
        for tbl in tables:
            head = [_tidy(x) for x in (_grid(tbl, 'header') or [[]])[0]]
            colof = {}
            for key, want in _ARCH_COLS:
                hit = [i for i, h in enumerate(head) if h.startswith(want)]
                if len(hit) != 1:
                    raise HkexFetchError(
                        '%s 逐日档案 %d-%d 的表头认不出「%s」（表头=%r）—— 版式变了，'
                        '宁可停也不能猜列号' % (_BOARD_ZH[board], lo, hi, want, head))
                colof[key] = hit[0]
            for row in _grid(tbl, 'body'):
                day = _tidy(row[0]) if row else ''
                if not day:
                    continue                      # 纯空行：忽略
                if not _ARCH_DATE_RE.match(day):
                    raise HkexFetchError('%s 逐日档案 %d-%d 出现非日期行 %r —— 可能是新加的'
                                         '小计/脚注行，必须人工确认后再改解析'
                                         % (_BOARD_ZH[board], lo, hi, day))
                if len(row) <= max(colof.values()):
                    # 表头有 5 列而这一行只给了 3 格：不能让它变成 IndexError，
                    # 那种堆栈看不出是"数据源缺格"还是"我写错了"。
                    raise HkexFetchError('%s 逐日档案 %d-%d 的 %s 行只有 %d 格，'
                                         '表头要到第 %d 格' % (_BOARD_ZH[board], lo, hi, day,
                                                              len(row), max(colof.values()) + 1))
                ym = day[:4] + '-' + day[5:7]
                a = out.setdefault(ym, [0, 0, 0, 0])
                a[0] += 1
                a[1] += _int(row[colof['value']])
                a[2] += _int(row[colof['volume']])
                a[3] += _int(row[colof['deals']])
    if not out:
        raise HkexFetchError('%s 逐日档案一条日线都没解析出来' % _BOARD_ZH[board])
    return out


def _highlights(board, month, cache_dir):
    """Monthly Bulletin 的 Stock market highlights → 该月三行的 (合计, 日均)。

    返回 {'value': (合计, 日均), 'volume': (...), 'deals': (...)}；
    该月没挂（HTTP 404）返回 None —— 只挂最近 13 个月是官方的正常状态，不是故障。
    """
    y, m = int(month[:4]), int(month[5:7])
    url = _HIGHLIGHT_URL[board] % ('%02d%02d' % (y % 100, m))
    try:
        doc = _json_get(url, cache_dir, 'hkex_highlights_%s_%s.json' % (board, month))
    except urllib.error.HTTPError as e:
        if e.code in (403, 404):
            return None
        raise HkexFetchError('%s %s Stock market highlights 取不到：%r' % (_BOARD_ZH[board], month, e))
    tables = doc.get('tables') or []
    if not tables:
        raise HkexFetchError('%s %s Stock market highlights 没有 tables' % (_BOARD_ZH[board], month))
    tbl = tables[0]

    # 认列：表头里写的是 "June 2026" / "June 2025"（本月 vs 去年同月）。
    # 必须按月份名认，不能默认第 1 列 —— 认错一列就是把去年同月当本月入库。
    head = [_tidy(x) for x in (_grid(tbl, 'header') or [[]])[0]]
    want = '%s %d' % (_MON_FULL[m - 1], y)
    hit = [i for i, h in enumerate(head) if h == want]
    if len(hit) != 1:
        raise HkexFetchError('%s %s 的 highlights 表头里找不到唯一的「%s」列（表头=%r）'
                             % (_BOARD_ZH[board], month, want, head))
    col = hit[0]

    body = _grid(tbl, 'body')
    out = {}
    for key, lab in _HL_ROWS:
        row = None
        for r in body:
            if _tidy(r[0]).startswith(lab):
                row = r
                break
        if row is None:
            raise HkexFetchError('%s %s 的 highlights 里找不到「%s」行'
                                 % (_BOARD_ZH[board], month, lab))
        if len(row) <= col:
            raise HkexFetchError('%s %s 的「%s」行只有 %d 格，取不到第 %d 格（%s）'
                                 % (_BOARD_ZH[board], month, lab, len(row), col + 1, want))
        parts = [p for p in _tidy(row[col]).split('\n') if p]
        if len(parts) != 2:
            raise HkexFetchError('%s %s 的「%s」格拆不出「合计 / 日均」两行（原文 %r）'
                                 % (_BOARD_ZH[board], month, lab, row[col]))
        out[key] = (_int(parts[0]), _int(parts[1]))
    return out


def _archive_row(mb, gem, month):
    """某月两板的逐日汇总 → 该月 7 个新列的值。"""
    days_mb, days_gem = mb[0], gem[0]
    if days_mb <= 0:
        raise HkexFetchError('%s 主板逐日档案 0 个交易日' % month)
    if days_gem != days_mb:
        # 同一家交易所、同一套交易日历，正常永远相等（2019-01~2026-06 实测 90/90 相等）。
        # 真差了也不该让整月落空 —— 交易日以主板为准，GEM 只占成交额 0.03%。
        print('[hkex] %s 主板 %d 个交易日、GEM %d 个，取主板；GEM 合计仍按原样入库'
              % (month, days_mb, days_gem))
    return {
        'trading_days_cash': days_mb,
        'vol_shares_mb_mn': mb[2] / 1e6,
        'vol_shares_gem_mn': gem[2] / 1e6,
        'trades_mb_total': mb[3],
        'trades_gem_total': gem[3],
        # 合计口径 = 主板+GEM，与 adt_hkdbn 完全一致（见 docstring 闭合 ②③）。
        # 先相加再取整，不是两个取整值相加 —— 后者会在末位上多出 ±1 的抖动。
        'adv_shares_mn': (mb[2] + gem[2]) / 1e6 / days_mb,
        'adt_trades': (mb[3] + gem[3]) / float(days_mb),
    }


def _confirm_with_bulletin(month, row, cache_dir):
    """拿 Monthly Bulletin 逐位核对某月的档案汇总。返回 (是否确认, 说明)。

    这是挡「月中快照」的唯一闸门：逐日档案自己不声明「这个月发完了没有」，
    只有 Bulletin 印出当月合计才等于官方宣布这个月收口了。
    """
    got = {}
    for b in _BOARDS:
        hl = _highlights(b, month, cache_dir)
        if hl is None:
            return False, 'Monthly Bulletin 还没挂 %s（只挂最近 13 个月，或该月尚未发布）' % month
        got[b] = hl
    checks = [
        ('主板当月成交股数(mil sh)', got['mb']['volume'][0], round(row['vol_shares_mb_mn'])),
        ('GEM当月成交股数(mil sh)', got['gem']['volume'][0], round(row['vol_shares_gem_mn'])),
        ('主板当月成交笔数', got['mb']['deals'][0], row['trades_mb_total']),
        ('GEM当月成交笔数', got['gem']['deals'][0], row['trades_gem_total']),
        ('主板日均成交股数(mil sh)', got['mb']['volume'][1],
         round(row['vol_shares_mb_mn'] / row['trading_days_cash'])),
        ('主板日均成交笔数', got['mb']['deals'][1],
         round(row['trades_mb_total'] / float(row['trading_days_cash']))),
    ]
    bad = ['%s：Bulletin %d vs 档案 %d' % (n, a, b) for n, a, b in checks if abs(a - b) > 1]
    if bad:
        return False, '与 Monthly Bulletin 对不上（%s）' % '；'.join(bad)
    return True, 'Monthly Bulletin %s 逐位确认（6 项，容差 ±1 个末位）' % month


def _bulletin_row(month, cache_dir):
    """只有 Bulletin、还没进逐日档案的月份 → 该月 7 个新列的值；没挂就 None。

    交易日不在 Bulletin 里印，但「当月合计 ÷ 日均」必然等于交易日数，
    而且主板与 GEM 两套数必须给出同一个整数 —— 对不上就说明我读错了格，宁可不要。
    """
    hl = {}
    for b in _BOARDS:
        one = _highlights(b, month, cache_dir)
        if one is None:
            return None
        hl[b] = one

    days = set()
    for b in _BOARDS:
        for key in ('value', 'volume', 'deals'):
            tot, avg = hl[b][key]
            if avg <= 0:
                continue
            days.add(int(round(tot / float(avg))))
    if len(days) != 1:
        print('[hkex] %s 的 Bulletin 反推交易日不唯一（%s），该月不入库'
              % (month, sorted(days)))
        return None
    d = days.pop()
    if d <= 0:
        return None
    return {
        'trading_days_cash': d,
        'vol_shares_mb_mn': hl['mb']['volume'][0],
        'vol_shares_gem_mn': hl['gem']['volume'][0],
        'trades_mb_total': hl['mb']['deals'][0],
        'trades_gem_total': hl['gem']['deals'][0],
        'adv_shares_mn': (hl['mb']['volume'][0] + hl['gem']['volume'][0]) / float(d),
        'adt_trades': (hl['mb']['deals'][0] + hl['gem']['deals'][0]) / float(d),
    }


def _trading_stats(months, cache_dir):
    """series 已有的月份 → {'YYYY-MM': {新列名: 值}}。

    months 是 series/hkex.csv 现有的全部月份；本函数**只给这些月出数**，
    一个新行都不造（理由见模块 docstring「历史深度」一节）。

    优先级：逐日档案 > Monthly Bulletin。
      · 档案是逐日底稿，精度最高、口径与 adt_hkdbn 同源；
      · 档案的**最后一个月**必须过 Bulletin 确认，过不了就丢掉（可能是月中快照）；
      · 档案还没覆盖到的月份（实测会落后一整个月）交给 Bulletin。
    """
    if not months:
        return {}
    since_year = int(min(months)[:4])
    arch = {b: _archive_daily(b, since_year, cache_dir) for b in _BOARDS}
    common = sorted(set(arch['mb']) & set(arch['gem']))
    if not common:
        raise HkexFetchError('主板与 GEM 逐日档案没有共同月份（索引或版式可能变了）')

    out = {}
    last_arch = common[-1]
    for month in common:
        if month not in months:
            continue                              # 早于/晚于 series 现有行：不造行
        row = _archive_row(arch['mb'][month], arch['gem'][month], month)
        if month == last_arch:
            ok, why = _confirm_with_bulletin(month, row, cache_dir)
            if not ok:
                print('[hkex] 逐日档案最新月 %s 未通过确认（%s），本轮不写该月' % (month, why))
                continue
            print('[hkex] 逐日档案最新月 %s：%s' % (month, why))
        out[month] = row

    # 档案还没跟上的月份（只可能在档案末月之后）交给 Bulletin
    for month in sorted(m for m in months if m > last_arch):
        row = _bulletin_row(month, cache_dir)
        if row is None:
            continue
        out[month] = row
        print('[hkex] %s 逐日档案尚未覆盖，改用 Monthly Bulletin 当月合计' % month)
    return out


# ── 对外接口 ──────────────────────────────────────────────────────────────
def latest_month(cache_dir):
    """官方源当前最新月 "YYYY-MM"。抓不到 / 解析不出就抛 HkexFetchError。

    以**表里最后一个 ADT 非空的月**为准，而不是信文件名：
    HKEX 有时先把下个月的列开出来再填数，信文件名会得到一个空壳月。
    """
    path, claimed, _ = _download(cache_dir)
    data = _parse(path)
    filled = sorted(m for m, v in data.items() if v['adt_hkdbn'] is not None)
    if not filled:
        raise HkexFetchError('解析成功但没有任何月份有 ADT，文件疑似空壳：%s' % path)
    last = filled[-1]
    if last != claimed:
        print('[hkex] 注意：文件名声称 %s，实际最后有数的月是 %s' % (claimed, last))
    return last


def update(series_dir, cache_dir, allow_restate=False):
    """把官方源里 series 还没有的月份写进 series/hkex.csv，返回新增月份列表。

    「新增」= 该月的 adt_hkdbn 从"没有"变成"有"。这样定义是因为 build_hkex.py
    用 adt_hkdbn 挑 LATEST，一行只填了衍生品的残缺月对看板等于不存在。
    两种情况都算：整行追加、以及给已存在但 adt 为空的行补上数。

    幂等：已有且非空的单元格默认原样保留（allow_restate=True 才覆盖），
    重复跑第二遍返回 []。

    任何一个 HIGHLIGHT_COLUMNS 里的列在官方源里取不到值 → 抛异常，绝不写 NaN/空。

    链路 B（TRADING_COLUMNS，成交股数/成交笔数）在下面单独走一遍：它给**所有已有行**
    补空格，不受「adt 已有的行不动」那条规矩约束 —— 那条规矩管的是历史留白，
    而这 7 列是 2026-08 才新增的，全序列的空格都不是留白，是还没抓。

    序列落盘之后，顺手把这一档带来的那个最新月的发布日记进 series/source_dates.csv
    （页面抬头「官方发布于」用它），细节见下面那段注释与模块 docstring 的「发布日」节。
    """
    csv_path = os.path.join(series_dir, 'hkex.csv')
    if not os.path.exists(csv_path):
        raise HkexFetchError('找不到 %s；本模块只负责增量，不负责从零建序列' % csv_path)

    path, _, last_modified = _download(cache_dir)
    data = _parse(path)

    raw = open(csv_path, 'rb').read().decode('utf-8')
    nl = '\r\n' if '\r\n' in raw else '\n'
    lines = raw.replace('\r\n', '\n').rstrip('\n').split('\n')
    header = lines[0].split(',')

    body = [ln.split(',') for ln in lines[1:]]
    migrated = False
    if header == ['month'] + HIGHLIGHT_COLUMNS:
        # 一次性表头迁移：新 7 列追加在末尾，旧 7 个字段（month + 6 列）**原位不动**，
        # 每行补 7 个空格。之后由链路 B 逐格填上；填不上的就保持空。
        header = ['month'] + COLUMNS
        for f in body:
            f.extend([''] * len(TRADING_COLUMNS))
        migrated = True
    elif header != ['month'] + COLUMNS:
        raise HkexFetchError('series/hkex.csv 列名与预期不符：%s' % header)
    ncol = len(header)
    for f in body:
        if len(f) != ncol:
            raise HkexFetchError('series/hkex.csv 的 %s 行有 %d 个字段，表头是 %d 个'
                                 % (f[0], len(f), ncol))

    idx = {f[0]: i for i, f in enumerate(body)}
    last_csv_month = body[-1][0]

    added, filled_cells, restatements = [], [], []

    def month_key(m):
        y, mm = m.split('-')
        return int(y) * 12 + int(mm)

    for month in sorted(data, key=month_key):
        rec = data[month]
        if month in idx:
            # ── 已有行 ──
            # 只给「adt 为空」的行补空格。这类行是前人用比 xlsx 更快的来源先写了半行
            # （如 2026-07），等官方文件到位就该补齐。
            # 反过来，adt 已有的历史行里的空格是**故意留白**：new_listings / ipo 早期
            # 官方简报没发、southbound 有 2022-01~2025-06 的 40 个月停发窗口，
            # build_hkex.py 的图注专门讲了这个 gap。现在的 xlsx 虽然把这些历史都补全了，
            # 但一次性回填 = 把两代口径混进同一条序列、并改掉看板叙事，
            # 属于人工决策，不该由无人值守任务顺手做掉。
            row = body[idx[month]]
            had_adt = bool(row[1])
            for j, col in enumerate(HIGHLIGHT_COLUMNS, start=1):
                new = rec[col]
                if new is None:
                    continue
                s = _fmt(col, new)
                if not row[j]:
                    if had_adt:
                        continue                     # 历史留白，不动
                    row[j] = s
                    filled_cells.append((month, col, s))
                elif row[j] != s and _materially_differs(col, row[j], s):
                    # 只记"真差异"：末位 1 个单位的差是历史序列当年四舍五入留下的，
                    # 全记下来会把真正的官方重述（IPO 那种 5%）淹没掉
                    restatements.append((month, col, row[j], s))
                    if allow_restate:
                        row[j] = s
            if not had_adt and row[1]:
                added.append(month)
            continue

        # ── 新行：只接受"当月 6 列全齐"的月份 ──
        if month_key(month) <= month_key(last_csv_month):
            # 早于序列尾部的历史空档：不回填（口径会混两代来源，见 docstring 坑 4）
            continue
        if rec['adt_hkdbn'] is None:
            continue                    # 官方把列开出来了但还没填数，等下个月
        missing = [c for c in HIGHLIGHT_COLUMNS if rec[c] is None]
        if missing:
            raise HkexFetchError(
                '%s 解析结果缺列 %s —— 拒绝写入残缺行。'
                '要么官方版式变了，要么该月确实只发了一半，请人工确认。' % (month, missing))
        # 新行先只填链路 A 的 6 列；链路 B 的 7 列紧接着在下面那一段填。
        body.append([month] + [_fmt(c, rec[c]) for c in HIGHLIGHT_COLUMNS]
                    + [''] * len(TRADING_COLUMNS))
        idx[month] = len(body) - 1
        added.append(month)

    # ── 链路 B：成交股数 / 成交笔数（TRADING_COLUMNS）──
    # 与上面那一段的两点不同，都是有意的：
    #   · 不看 had_adt。这 7 列是新增列，全序列的空格都不是「故意留白」，是还没抓。
    #   · 不造新行。只给 idx 里已经存在的月份补格，理由见模块 docstring「历史深度」一节。
    # 相同的是：非空格子一律不覆盖（allow_restate=True 才覆盖），所以第二遍跑一格不动。
    tcol_at = {c: j for j, c in enumerate(header) if c in set(TRADING_COLUMNS)}
    stats = _trading_stats(sorted(idx, key=month_key), cache_dir)
    for month in sorted(stats, key=month_key):
        row = body[idx[month]]
        for col, j in tcol_at.items():
            val = stats[month].get(col)
            if val is None:
                continue
            s = _fmt(col, val)
            if not row[j]:
                row[j] = s
                filled_cells.append((month, col, s))
            elif row[j] != s and _materially_differs(col, row[j], s):
                restatements.append((month, col, row[j], s))
                if allow_restate:
                    row[j] = s

    # 重述记录始终落盘，方便人工判断是口径变化还是解析出错
    if restatements:
        os.makedirs(cache_dir, exist_ok=True)
        rp = os.path.join(cache_dir, 'hkex_restatements.csv')
        with open(rp, 'w', newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            w.writerow(['month', 'column', 'in_series_csv', 'in_official_source'])
            w.writerows(restatements)
        print('[hkex] 官方源与 series 有 %d 处不一致，已写 %s（allow_restate=%s）'
              % (len(restatements), rp, allow_restate))

    if not (migrated or added or filled_cells or (restatements and allow_restate)):
        return []

    body.sort(key=lambda f: month_key(f[0]))
    out = nl.join([','.join(header)] + [','.join(f) for f in body]) + nl
    tmp = csv_path + '.tmp'
    with open(tmp, 'wb') as f:
        f.write(out.encode('utf-8'))
    os.replace(tmp, csv_path)           # 原子替换，中途挂掉不会留半截文件

    # ── 发布日台账：只给「这一档 xlsx 自己带来的那个最新月」记一笔 ──
    # 文件里同时躺着 2018 年以来的全部历史，而这一档的上线时刻只能证明**最新月**是这天发的；
    # 本轮顺带补空的旧月是更早那些档发的，把今天的日期安到它们头上就是造假。
    # 也只在该月**首次入库**时记（in added）：HKEX 会原地重传，重传后的 Last-Modified
    # 更晚，事后覆盖等于把当初那次真发布的日期改错。
    src_months = [mth for mth, v in data.items() if v['adt_hkdbn'] is not None]
    src_last = max(src_months, key=month_key) if src_months else None
    if src_last and src_last in added:
        _record_source_date(series_dir, src_last, path, last_modified)

    if filled_cells:
        print('[hkex] 补空 %d 格：%s' % (len(filled_cells), filled_cells[:12]))
    return added


if __name__ == '__main__':
    import sys
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    _cache = os.path.join(_root, 'cache')
    if len(sys.argv) > 1 and sys.argv[1] == 'update':
        print('added:', update(os.path.join(_root, 'series'), _cache))
    else:
        print('latest_month:', latest_month(_cache))
