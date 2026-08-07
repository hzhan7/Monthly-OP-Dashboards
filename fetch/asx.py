# -*- coding: utf-8 -*-
"""ASX Limited（澳大利亚证券交易所，ASX:ASX）月度经营指标 —— 无人值守抓取。

━━ 数据源 ━━
主源：**ASX Group Monthly Activity Report（MAR）**，ASX 按澳洲持续披露义务同时发给
ASIC 与自家 Market Announcements Office 的市场公告，地位等同美股 8-K Item 7.01。
首页抬头逐字写着 "ASX GROUP MONTHLY ACTIVITY REPORT – JULY 2026 /
Release of market announcement authorised by: Andrew Tobin, Chief Financial Officer"。

  索引页（cron 唯一入口）
      https://www.asx.com.au/about/media-centre
      一次 GET 拿到整页 494 条 PDF href（服务端渲染，无分页、无 JS），其中 80 条是 MAR，
      覆盖 2020-02 → 至今 78 个月 + 2 份更正稿。
  PDF 直链（同域 DAM，无中转页）
      https://www.asx.com.au/content/dam/asx/about/media-releases/{YYYY}/{...}-{month}-{YYYY}.pdf

历史回补源（**cron 不走**，见下）：ASX 自家公告存档
      列表  .../asx/v2/statistics/announcements.do?by=asxCode&asxCode=asx&timeframe=Y&year=YYYY
      中转  .../asx/v2/statistics/displayAnnouncement.do?display=pdf&idsId={idsId}
      直链  https://announcements.asx.com.au/asxpdf/{YYYYMMDD}/pdf/{hash}.pdf
实测 2009-12 → 2026-07 共 211 个月、只缺 2009-05。技术上纯 GET 可通（中转页的
`<input name="pdfURL">` 隐藏字段直接写出真实直链，不需要 POST、不需要 cookie），
但那一页是一张**「点击即接受使用条款」的同意表单**——让 cron 每月自动穿过它是策略问题，
不是技术问题。所以本模块把两条路分开：

  · `update()` / `latest_month()`（cron 跑的）**只走媒体中心**，全程不碰同意页；
  · 历史一次性回补走 `python3 fetch/asx.py --backfill 2017-10 2020-01`，**人工跑**。
    series/asx.csv 里 2020-01 及更早的行就是这样来的，之后再没人需要跑它。

裸 `urllib`（默认 Python-urllib UA、零 header）对三个入口全部 200：无 Cloudflare、
无 Akamai、无 JS 渲染、无登录墙、不校验 UA。满足无人值守。

辅源（分品种，**只有最近 2 期**）：Monthly SFE Trading Report
      https://www.asx.com.au/content/dam/asx/documents/unlinked-docs/
      monthly-futures-markets-report-{DDMMYYYY}.pdf      DDMMYYYY = 数据月最后一个日历日
这份报告的链接**印在 MAR 正文第 4 页**，所以不用猜文件名，跟着 MAR 走。
它是 SPI 200 / 3 年期国债 / 10 年期国债 / 90 日银行票据分品种月度成交与未平仓的
唯一官方月度来源（MAR 本身只给期货合计，不拆品种）。
实测 `31072026` / `30062026` → 200 application/pdf；`31052026` / `31122025` /
`30062025` → 真 404。**历史不可回补**，只能从 2026-06 起逐月往后攒，漏抓一个月就永久缺一个月。

━━ 发布节奏 ━━
次月第 3–8 个日历日，众数第 5–6 日，悉尼时间 8:30–9:30 am 上市场。
211 期公告时间戳的日分布（本模块开发时从存档页统计）：
    第 3 天 33 ｜ 第 4 天 40 ｜ 第 5 天 58 ｜ 第 6 天 63 ｜ 第 7 天 13 ｜ 第 8 天 3
另有 1 期落在第 20 天，那是 2022-06 的**更正稿**，不是首发。
**没有季末月特殊性**：ASX 财年 6 月底结束，但 6 月的月报照常次月初发
（2025-06 → 2025-07-04；2026-06 → 2026-07-06）。⇒ `build/roster.py` 的 LAG 两档同为 (8, 8)。

发布日只认**PDF 首页正文第一行 ASX 自己写的那个日期**（"6 August 2026"），记进
series/source_dates.csv。不用 HTTP Last-Modified：DAM 副本比公告晚约 30 分钟上传
（公告 8:40 am，DAM 9:10 am AEST），跨日就会错一天；也不用文件名里的日期，
2020–2021 那批文件名根本不带发布日，2021 起带的那个前缀数字是**日历年内公告序号**
（`43-06-august-2026-…` 的 43 与数据月无关）。

━━ 口径坑（按踩坑概率排序）━━
1. **同名诱饵：ASX Compliance Monthly Activity Report。** 2010-08 → 2016-06 共 71 个月，
   ASX 每月同一天发两份标题几乎相同的公告，idsId 相邻：
       01754741  ASX Group      Monthly Activity Report - June 2016   7 pages
       01754742  ASX Compliance Monthly Activity Report - June 2016   5 pages   ← 诱饵
   Compliance 版里有 "Listed entities at month end 2,204" 这种**完全合法、看上去正确**
   的数字，但整份**没有任何成交数据**。按 `'Monthly Activity' in title` 匹配必然中招，
   而中招的表现是「上市实体数对，成交全空」，不报错。⇒ 发现逻辑一律 `'compliance' not in
   title.lower()`（见 `_ARCHIVE_SKIP`），且解析后断言必填列齐全（见 `_validate`）。
   媒体中心那条路天然不含 Compliance 版，但存档回补那条路每个月都会撞上。

2. **soft-404：HTTP 200 + text/html 的假成功。** 2024 年代 MAR 正文里印的旧版分品种直链
   `https://www.asx.com.au/data/market-reports/MonthlyFuturesMarketsReport{YYMMDD}.pdf`
   返回 **200 + text/html + 恒定 136,750 字节的错误页**，不是 404。实测 `200228` /
   `190228` / `160630` / `170428` / `240731` 五个日期字节数完全相同。
   任何 `if status == 200: save()` 都会把 HTML 错误页当 PDF 存下来，然后在解析阶段
   报一个跟真实原因毫无关系的错。⇒ `_http_pdf()` **同时**校验 Content-Type 为
   application/pdf 且首 5 字节为 `%PDF-`，两条缺一不可。
   （新版 `unlinked-docs/monthly-futures-markets-report-*.pdf` 是真 404，行为不一样，
   所以「我试过没问题」这种经验在这里是靠不住的。）

3. **绝不能按 `Average daily contracts` 的出现序号取值。** 同一份 PDF 里这个行名出现
   5 次（2020 版起：期货 / 期货期权 / 期货合计 / 单股期权 / 指数期权）或 **6 次**
   （2015-09 – 2017 版多一行 `Total options volume` 的合计 ADV，实测 2016-06 = 418,112
   ≈ 347,474 + 70,639）。次数会变，序号法必然在某一代版式上整体串位，而**串出来的每个数
   都是合法数字**。⇒ 一律先用大标题（`Trading – Futures` / `Trading – Equity Options`）
   切 section，再用小标题（`Futures volume` / `Options on futures volume` / …）切 subsection，
   最后才查行名。见 `_SECTIONS` / `_SUBSECTIONS` / `COLUMN_SPEC`。

4. **列数按行变，不按报告变。** 8 月至次年 6 月的报告，流量行有 4 列
   `[本月, 去年同月, 本财年 YTD, 去年同期 YTD]`；时点行（listed entities / CHESS / margins）
   只有 2 列；而 **7 月**那一期因为财年 YTD ≡ 本月，官方直接把后两列删掉，整份只有 2 列。
   实测同一份 2016-06 报告：`Secondary capital raised` → [1726, 5083, 45299, 38787]，
   `Total Listed entities` → [2204, 2220]。
   ⇒ 只能取「值列里从左数第 1 个数字」。「取最后一列」「按列数判断版式代际」都会在某个月炸。

5. **竖排水印 "For personal use only" 会污染标签。** pymupdf 把这四个词按 y 坐标并进
   任意一行的词流，实测把 `Total notional cleared value ($billion)¹` 变成
   `For Total notional cleared value ($billion)¹`，前缀锚定的正则直接失配。
   ⇒ `_page_rows()` 按词过滤 `for|personal|use|only`（`_WATERMARK`）。

6. **标签里有数字，所以不能全行扫数字。** `S&P/ASX 200 VIX (average daily value) 11.3 11.3`
   全行扫会把「本月值」读成 200；夹在标签与数值之间的括号说明同样含数字
   （`(includes interest rate, ASX SPI 200, commodities and energy contracts)`），
   所以连「跳过无数字的行」都救不了。⇒ 按**页宽比例**切值列左边界：`_NUMCUT = 0.47`。
   实测 2015–2026 全部版式都成立（值列 x 起点：2016 版 ~287，2024/2026 版 ~426；
   标签词 x 起点最远 ~262）。

7. **标签与数值经常不在同一「阅读顺序行」上，得靠 y 坐标聚类 + 续行前瞻。** 三种实测形态：
     · 2016 版：`Total trading days` 单独一行，值挂在下一行的括号说明上
       （`(Cash market includes … market  21  21  254  254`）；
     · 2016 版：`Value of CHESS holdings – period end` / 值 / `($billion)` 三行，值在中间那行；
     · 2024 版：`Total trading days` 行自带值，括号说明在**下面**。
   ⇒ 标签行没有值时，向下前瞻至多 2 行，且只接受「标签区为空 / 以 `(` 开头 / 以小写字母
   开头」的续行——正文行与下一个指标的标签都是大写开头，不会被误吃。

8. **脚注标记有三种形态，还会出现在标签中段。** 2026 版是上标 Unicode `¹`，2024 版是
   **普通 ASCII 数字直接粘在标签后**（`Total notional cleared value ($billion)1`），
   2016 版是 `*` 且在中段（`Total notional cleared value* ($billion)`）。
   只剥尾部记号救不了 2016 版。⇒ `_key()` 全串删 `*¹²³†‡`，再剥尾部 ASCII 数字。

9. **单位后缀会换行掉队，所以它不能参与匹配。** 同一个指标，131 个月里 13 个月的标签是
   `Total billable cash market value cleared`、118 个月是 `…cleared ($billion)`
   （`($billion)` 换到了下一行，落在标签区之外）。CHESS 22/109、Austraclear 34/97、
   `Other capital raised including scrip-for-scrip` 12/119 都是同一回事。
   ⇒ `_key()` 统一剥掉尾部单位括号 `($billion)` `($million)` `($)` `(million)`
   `(at end of month)`，剥完两边才对得上。

10. **Listings 段在 2023-10 换过定义，不是换名字 —— 两套口径必须分列存。**
      · …2023-09：`Initial capital raised ($million)`（IPO **实际募资额**）
                  `Total capital raised including other ($million)`
      · 2023-10 ：`Quoted market capital of new listings`（**无 -isation**，仅此一月）
                  `Total initial and secondary capital quoted`（第三种写法，2023-10/11 两月）
      · 2023-11+：`Quoted market capitalisation of new listings ($million)`
      · 2023-12+：`Total new capital quoted ($million)`
    「IPO 募到多少钱」与「新上市实体挂牌市值多少」差 6 倍（FY26 官方新闻稿同时给出
    IPO capital raised $5.6bn 与 new listings added $32.6bn in quoted market capitalisation）。
    ⇒ 本模块给它们**两组独立列**：`capital_initial_raised_audmn` /
    `capital_total_raised_incl_other_audmn`（老口径，2023-09 止）与
    `mktcap_new_listings_audmn` / `capital_new_quoted_audmn`（新口径，2023-10 起）。
    画图时在 2023-10 打结构性断点红线；**同一列里连起来画就是编数据**。

11. **`Total secondary capital raised` ≠ 新闻稿说的 follow-on。**
    MAR 里 `Total secondary = Secondary capital raised + Other capital raised including
    scrip-for-scrip`。FY26 实测：窄口径 $37.849bn（新闻稿 "raised $37.8 billion in
    follow-on capital during FY26" ✅），含换股对价 $58.428bn。
    ⇒ 三列都存（`capital_secondary_audmn` / `capital_other_scrip_audmn` /
    `capital_secondary_total_audmn`），只存合计必然对不上任何一份官方文本。

12. **OTC 名义额是双边计数。** 官方脚注逐字写着 "Cleared notional value is double sided"。
    与 CME / LCH 的单边惯例不同，跨家比之前必须先统一，否则 ASX 凭空大一倍。
    `otc_notional_cleared_audbn` 是**当月流量**，`otc_open_notional_audbn` 是**月末存量**，
    两者都是双边。

13. **三套交易日数经常不等**：cash / futures / ETO。2026-04 实测 19 / 20 / 19。
    用 `ADV × 交易日` 反推月度总量时配错就整月偏 5%。所以三个都存
    （`trading_days_cash` / `trading_days_futures` / `trading_days_eto`），
    而且**每一类的月度总张数本模块也照原样存**，下游根本不需要自己乘。

14. **ASX 现货 ≠ 澳洲现货全市场。** Cboe Australia（原 Chi-X）的成交不在 MAR 里。
    本仓横截面页若只用 MAR，口径是「ASX 自身经营量」而不是「澳洲市场量」，图注要写明。
    另外 `value_tradereport_audbn` 是**场外成交事后向 ASX 报告**的金额，不是 ASX 撮合量；
    `adt_cash_onmarket_audbn`（不含它）才是与 HKEX `adt_hkdbn` 同概念的那个数。

15. **`On-market value` 这一行 2017-10 才出现，早期是真缺失，不是解析失败。**
    2015-09 – 2017-09 的现货段行名与现在**全部不同**（纯改名，定义没变，已用
    Open+Auctions+CentrePoint+TradeReporting = Total 的恒等式验证）：
        `Total value ($billion)`                → `Total cash market value ($billion)`
        `Average daily value on-market ($bn)`   → `On-market average daily value ($bn)`
        `Average daily value ($billion)`        → `Total average daily value ($billion)`
    唯独 `On-market value`（当月 on-market 成交额）2017-10 之前**官方没印过**。
    另外 `S&P/ASX 200 VIX` 行 **2019-10** 才出现，`Entities de-listed` 等四行 **2024-05** 才出现。
    ⇒ 每一列都带 `since`/`until` 月份边界（`COLUMN_SPEC`），越界为空是合法的，
    界内为空一律抛异常。

16. **2017-04 那一期 PDF 的期货期权小块整体错行，本模块拒绝解析它。** 实测该页
    `Options on futures volume`（小标题行）上挂着 `Total contracts` 的值，
    `Total contracts` 行上挂着 `Change on pcp` 的百分比，`Average daily contracts` 行是空的
    —— 值列相对标签列整体上移了一行。加总恒等式可以证明真值
    （8,901,810 + 124,649 = 9,026,459 ✔；494,545 + 6,925 = 501,470 ✔），
    但那是**人拿算术推回来的**，不是解析出来的。实测本模块在这一期上抛的是
    `_validate` 的缺列异常（`contracts_options_on_futures_total` /
    `adv_options_on_futures_contracts` 两列取不到值），不是加总恒等式 ——
    错行错得够狠时值列直接落空，轮不到恒等式说话；恒等式管的是另一种情况：
    **每个格子都有数、但装错了格子**（见 `_check_identities`）。两道闸门各守一边。
    series 起点定在 2017-10 之后，这一期落在起点之前，实际不影响 cron。

17. **同月有更正稿时必须用更正稿，且要跳过第 1 页。** 更正稿第 1 页是
    「Incorrect figure / Correct figure」对照表，**错值就印在第 1 页上**
    （2025-01 的 `Centre Point ($billion) 9.548` 是错值，正确值 8.852）。
    不跳第 1 页就会把错值当本月值读进去。实测同月存在多份 Group 文档的月份共 4 个：
    2011-01 / 2015-04 / 2022-06 / 2025-01。用原版 2025-01 加总 FY25 会让 Centre Point
    偏 +0.48%、trade reporting 偏 +1.18%、总成交额偏 +0.22%；换更正版后与年报逐项 0 偏差。

18. **存档页的标题变体极多**，回补时的匹配必须宽松：大小写不敏感（2026-04 起整体转小写）、
    "Group" 不能强求（2016-07…2016-10、2017-04 是 `ASX Monthly Activity Report`）、
    月份支持缩写（`… - Jan 2025`）、**标题不带年份时数据月 = 发布月 − 1**
    （2017-10、2017-11、2018-02/03/08/11 等期标题只有月名）。

━━ 依赖 ━━ pymupdf（import 名 fitz）。不依赖 pandas / requests。
"""

import csv
import os
import re
import urllib.request
from datetime import datetime

import fitz

MEDIA_CENTRE_URL = 'https://www.asx.com.au/about/media-centre'
ASX_HOST = 'https://www.asx.com.au'
ARCHIVE_LIST_URL = (ASX_HOST + '/asx/v2/statistics/announcements.do'
                    '?by=asxCode&asxCode=asx&timeframe=Y&year=%d')
ARCHIVE_ITEM_URL = (ASX_HOST + '/asx/v2/statistics/displayAnnouncement.do'
                    '?display=pdf&idsId=%s')

# 带常规浏览器 UA：asx.com.au 目前完全不校验（裸 urllib 也 200），
# 但带上是零成本的保险，且出问题时对方日志里能看出是谁在打。
_UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
       '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36')

# series/asx.csv 的第一行数据月。定在 2017-10 的理由见口径坑 15 / 16：
#   · 2017-10 是现货段行名换代的那一月，从它开始一套标签映射走到底；
#   · 再往前那 21 个月要第二套映射，而且 2017-04 那期 PDF 本身错行（口径坑 16）。
# 老口径的别名仍写在 COLUMN_SPEC 里（--backfill 到更早的月份能解析），只是不入库。
SERIES_START = '2017-10'

_MONTHS = {m.lower(): i for i, m in enumerate(
    ['January', 'February', 'March', 'April', 'May', 'June', 'July',
     'August', 'September', 'October', 'November', 'December'], 1)}
_MONTHS.update({k[:3]: v for k, v in list(_MONTHS.items())})
_MONTHS['sept'] = 9

# 媒体中心 href 里的 MAR。文件名末尾的 {month}-{YYYY} 是**数据月**，
# 中间那段是发布日、开头那个数字是日历年内公告序号 —— 都不能拿来当数据月（口径坑：发布节奏节）。
_MAR_HREF = re.compile(
    r'href="(/content/dam/asx/[^"]*monthly[-%20]*activity[-%20]*report[^"]*\.pdf)"', re.I)
# 分隔符要写成可有可无：2019-12 与 2020-01 两期的文件名是驼峰无分隔的
# `ASXGroupMonthlyActivityReportJanuary2020.pdf`，其余 80 期是 `…-january-2020.pdf`。
# 锚在 `$` 上，所以文件名中段那个「发布月」（`43-06-august-2026-…`）抢不到。
_TAIL_MONTH = re.compile(
    r'[-_ ]?(january|february|march|april|may|june|july|august|september|october|'
    r'november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)[-_ ]?(\d{4})\.pdf$', re.I)
# 从 PDF 正文抬头读它自称的数据月，用来反证文件名没读错（见 _fetch_one）
_SELF_TITLE = re.compile(
    r'monthly\s+activity\s+report\s*(?:for\s+|[-‐-―]\s*)?'
    r'(january|february|march|april|may|june|july|august|september|october|'
    r'november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)\s+(\d{4})', re.I)

# 存档列表页的一行：日期 / 时刻 / idsId / 标题
_ARCHIVE_ROW = re.compile(
    r'<tr>\s*<td>\s*(\d{2}/\d{2}/\d{4})\s*<br>\s*<span class="dates-time">\s*([^<]+?)\s*'
    r'</span>.*?idsId=(\d+)"[^>]*>\s*(.*?)<br>', re.S)
# 诱饵与噪声：Compliance 版（口径坑 1）；"and Fee and Rebate Changes" 那种完全没有月份的公告
_ARCHIVE_SKIP = ('compliance',)
_TITLE_MONTH = re.compile(
    r'\b(january|february|march|april|may|june|july|august|september|october|'
    r'november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)\b\.?\s*(\d{4})?', re.I)
_CORRECTION = re.compile(r'correct|update', re.I)

# 首页正文第一行的发布日，例 "6 August 2026"（口径坑：发布节奏节）
_PUB_DATE = re.compile(
    r'^(\d{1,2})\s+(January|February|March|April|May|June|July|August|'
    r'September|October|November|December)\s+(\d{4})$')

# 分品种辅源：链接印在 MAR 正文里，直接从 PDF 文本里抠
_SFE_LINK = re.compile(
    r'https?://[^\s]*monthly-futures-markets-report-(\d{8})\.pdf', re.I)


class AsxFetchError(RuntimeError):
    """源站结构变化 / 下载失败 / 解析结果不完整。一律炸掉，绝不静默写 NaN。"""


# ══════════════════════════════════════════════════════════════════════
# 网络
# ══════════════════════════════════════════════════════════════════════
def _http_get(url, timeout=90):
    req = urllib.request.Request(url, headers={
        'User-Agent': _UA,
        'Accept': '*/*',
        'Accept-Language': 'en-AU,en;q=0.9',
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            # 返回 r.headers 本体而不是 dict(r.headers)：前者查名字**不分大小写**。
            # 转成 dict 会把大小写钉死，服务器一旦发 `content-type`（HTTP/2 一律小写）
            # 而不是 `Content-Type`，_http_pdf 的 Content-Type 校验就会读到空串，
            # 于是**每一个正常的 PDF 都被当成 soft-404 拒收**。实测这台源站两种写法都出现过。
            return r.read(), r.headers
    except Exception as e:                                # noqa: BLE001
        raise AsxFetchError('下载失败 %s: %r' % (url, e)) from e


def _http_pdf(url, timeout=90):
    """下载并**证明它真的是 PDF**。

    只看 HTTP 200 是不够的：ASX 有一条路径（口径坑 2）在文件不存在时返回
    200 + text/html + 恒定 136,750 字节的错误页。存下来之后 pymupdf 会报一个
    「文件损坏」之类跟真实原因毫无关系的错，排查成本极高。
    Content-Type 与 `%PDF-` 魔数两条都校验：前者防对方改错误页大小，后者防对方
    把错误页的 Content-Type 也标成 application/pdf。
    """
    body, hdrs = _http_get(url, timeout)
    ctype = (hdrs.get('Content-Type') or '').split(';')[0].strip().lower()
    if ctype != 'application/pdf' or body[:5] != b'%PDF-':
        raise AsxFetchError(
            '%s 返回的不是 PDF（Content-Type=%r, 前 5 字节=%r, %d 字节）——'
            '多半是 soft-404 错误页，见模块 docstring 口径坑 2'
            % (url, ctype, body[:5], len(body)))
    return body


def _write_bytes(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(data)


# ══════════════════════════════════════════════════════════════════════
# 发现：媒体中心（cron 唯一入口）
# ══════════════════════════════════════════════════════════════════════
def _discover_media_centre(cache_dir):
    """返回 {'YYYY-MM': {'orig': url|None, 'corr': url|None}}。

    原版与更正稿**两个都留着**，不是二选一：数值要用更正稿（口径坑 17），
    但「官方哪天发的这个月」要用**原版**的日期。2022-06 的更正稿抬头写的是
    20 July 2022，原版是 6 July 2022；把 20 号记进 source_dates.csv，
    等于告诉 LAG 审计「ASX 有时候拖到次月 20 号才发」，那张表就白记了。
    """
    html, _ = _http_get(MEDIA_CENTRE_URL)
    _write_bytes(os.path.join(cache_dir, 'asx_media_centre.html'), html)
    text = html.decode('utf-8', 'replace')
    hits = _MAR_HREF.findall(text)
    if not hits:
        raise AsxFetchError('媒体中心找不到任何 Monthly Activity Report 链接，'
                            '源站可能改版：' + MEDIA_CENTRE_URL)
    out = {}
    for href in hits:
        name = href.rsplit('/', 1)[-1]
        if 'compliance' in name.lower():          # 媒体中心目前不挂 Compliance 版，但白挡不亏
            continue
        m = _TAIL_MONTH.search(name.replace('%20', ' '))
        if not m:
            # 文件名不带数据月 = 命名规则变了。宁可炸，也不要按发布月猜一个数据月。
            raise AsxFetchError('媒体中心 MAR 文件名读不出数据月：%s' % name)
        mon = '%s-%02d' % (m.group(2), _MONTHS[m.group(1).lower()])
        slot = 'corr' if _CORRECTION.search(name) else 'orig'
        out.setdefault(mon, {'orig': None, 'corr': None})[slot] = ASX_HOST + href
    return out


def _discover_archive(year):
    """存档列表页 → [(数据月, idsId, 标题, 发布日 'YYYY-MM-DD', 是否更正稿)]。

    **只在 --backfill 里用**：该页本身是纯 HTML 表格，但拿 PDF 要经过一页
    「点击即接受条款」的同意表单（见模块 docstring）。
    """
    html, _ = _http_get(ARCHIVE_LIST_URL % year)
    text = html.decode('utf-8', 'replace')
    out = []
    for d, _tm, ids, title in _ARCHIVE_ROW.findall(text):
        title = re.sub(r'\s+', ' ', title).strip()
        low = title.lower()
        if 'monthly activity report' not in low:
            continue
        if any(s in low for s in _ARCHIVE_SKIP):          # 口径坑 1：Compliance 诱饵
            continue
        dd, mm, yy = (int(x) for x in d.split('/'))
        m = _TITLE_MONTH.search(low)
        if not m:
            continue                                       # "…and Fee and Rebate Changes"：无月份
        mo = _MONTHS[m.group(1).lower()]
        if m.group(2):
            mon = '%s-%02d' % (m.group(2), mo)
        else:
            # 口径坑 18：标题不带年份时，数据月 = 发布月 − 1
            py, pm = (yy - 1, 12) if mm == 1 else (yy, mm - 1)
            if mo != pm:
                continue                                   # 对不上就别猜
            mon = '%04d-%02d' % (py, pm)
        out.append((mon, ids, title, '%04d-%02d-%02d' % (yy, mm, dd),
                    bool(_CORRECTION.search(title))))
    return out


def _archive_pdf_url(ids_id):
    """从同意页里读出真实 PDF 直链（隐藏字段，纯 GET，不 POST 那张表单）。"""
    html, _ = _http_get(ARCHIVE_ITEM_URL % ids_id)
    m = re.search(r'name="pdfURL"[^>]*value="([^"]+)"',
                  html.decode('utf-8', 'replace'))
    if not m:
        raise AsxFetchError('存档中转页读不出 pdfURL 隐藏字段：idsId=%s' % ids_id)
    return m.group(1)


# ══════════════════════════════════════════════════════════════════════
# PDF → 行（y 坐标聚类 + 水印过滤 + 值列左边界）
# ══════════════════════════════════════════════════════════════════════
_WATERMARK = {'for', 'personal', 'use', 'only'}     # 口径坑 5：竖排水印
_NUMCUT = 0.47                                      # 口径坑 6：值列左边界 / 页宽
_YTOL = 3.0                                         # 同一视觉行的 y 容差（磅）

_DASH = re.compile(r'[‐‑‒–—―−]')
_FOOTNOTE = re.compile(r'[*¹²³†‡]')
_UNIT_SUFFIX = re.compile(
    r'\s*\((?:\$billion|\$million|\$|million|billion|at end of month|period end)\)\s*$', re.I)
_NUM_TOKEN = re.compile(r'^\(?-?[\d,]+(?:\.\d+)?\)?$')


def _norm(s):
    """统一破折号、删脚注记号、压空白。破折号有 7 种 Unicode 变体在同一批 PDF 里混用。"""
    return re.sub(r'\s+', ' ', _FOOTNOTE.sub('', _DASH.sub('-', s))).strip()


def _section_of(k):
    """行标签键 -> 它是不是某个大标题；不是就返回 None。见 _SECTIONS 上方的注释。"""
    for s in _SECTIONS:
        if k == s or k.startswith(s + ' ('):
            return s
    return None


def _key(label):
    """行标签 → 匹配键：小写、剥前导项目符号、剥尾部 ASCII 脚注数字、剥尾部单位括号。

    三件事各自对应一个实测的坑：
      · 前导 '-'：2018-05/06/07 与 2019-07 的 `-Total secondary capital raised ($million)`
        比别的月份多一个前导破折号（口径坑 8 的同类）；
      · 尾部 ASCII 数字：2024 版把脚注标记写成 `($billion)1`（口径坑 8）；
      · 尾部单位括号：`($billion)` 经常换行掉队到标签区之外，同一个指标 131 个月里
        13 个月没有它、118 个月有（口径坑 9）。
    剥完之后没有任何两个约定标签会撞车 —— COLUMN_SPEC 里的别名就是按剥完的形态写的。
    """
    s = _norm(label).lstrip('-•● ').strip()
    s = s.rstrip('0123456789 ').strip()
    prev = None
    while prev != s:                       # `($billion) (at end of month)` 要剥两次
        prev = s
        s = _UNIT_SUFFIX.sub('', s).strip()
    return s.lower()


def _num(tok):
    """'1,234' -> '1234'；'(964)' -> '-964'；'24%' / 'na' -> None。

    返回**字符串**而不是 float：入库要与官方印出来的写法一模一样
    （`635.499` 不写成 `635.499000001`，`2045` 不写成 `2045.0`），
    这样重跑时 CSV 字节级不变，幂等判断才干净。
    """
    t = tok.strip()
    neg = t.startswith('(') and t.endswith(')')
    t = t.strip('()').replace(',', '')
    if not re.fullmatch(r'-?\d+(?:\.\d+)?', t):
        return None
    return ('-' + t) if (neg and not t.startswith('-')) else t


def _page_rows(page):
    """一页 → [(标签, [值字符串…])]，按视觉行自上而下。

    为什么按 y 坐标聚类而不用 `page.get_text()` 的阅读顺序：2024 版把括号说明排在
    标签与数值之间（阅读顺序里是 标签 / 说明 / 说明 / 23 / 21），2016 版把值排在
    标签与单位之间 —— 阅读顺序两边都对不上，但**视觉行**永远是对的。
    """
    width = page.rect.width
    cut = width * _NUMCUT
    words = [w for w in page.get_text('words')
             if w[4].strip() and w[4].strip().lower() not in _WATERMARK]
    words.sort(key=lambda w: (round(w[1], 1), w[0]))
    buckets = []
    for w in words:
        y = (w[1] + w[3]) / 2.0
        for b in buckets:
            if abs(b['y'] - y) <= _YTOL:
                b['w'].append(w)
                b['y'] = (b['y'] * (len(b['w']) - 1) + y) / len(b['w'])
                break
        else:
            buckets.append({'y': y, 'w': [w]})
    rows = []
    for b in sorted(buckets, key=lambda b: b['y']):
        ws = sorted(b['w'], key=lambda w: w[0])
        label = _norm(' '.join(w[4] for w in ws if w[0] < cut))
        vals = []
        for w in ws:
            if w[0] >= cut:
                v = _num(w[4])
                if v is not None:
                    vals.append(v)
        rows.append((label, vals))
    return rows


# ══════════════════════════════════════════════════════════════════════
# MAR 解析
# ══════════════════════════════════════════════════════════════════════
# section：大标题。破折号已归一成 '-'，全部小写比较。
#
# **只认整行相等，或 `大标题 + " ("` 开头**，不能用宽松的前缀匹配。
# 前缀匹配踩过一次实测的坑：`settlement` 是个很短的词，正文里
# "…resigned as ASX Settlement Participants." 这种句子换行后正好以它开头，
# 于是在 Participants 段中间把 section 悄悄改回 `settlement`，
# 结果 2020-10 与 2023-03 两个月的参与者数解析为空 —— 而其余 129 个月都正常，
# 属于「大部分月份看着没问题」的那种最难发现的错。
# 之所以还要留 `+ " ("` 这条口子：现货段的大标题自带括号说明，且说明本身改过词
#   TRADING - CASH MARKETS (INCLUDING EQUITIES, INTEREST RATE AND WARRANTS TRADES)  2016 版
#   Trading - Cash Markets (including equities, interest rate and ETP trades)       现行
_SECTIONS = [
    'listings and capital raisings',
    'trading - cash markets',
    'trading - futures',
    'trading - equity options',
    'clearing - otc markets',
    'clearing - exchange-traded markets',
    'settlement',
    'participants',
]
# subsection：小标题。只有它能把 5–6 次的 `average daily contracts` 分开（口径坑 3）。
_SUBSECTIONS = [
    'cash market volume', 'cash market value',
    'futures volume', 'options on futures volume',
    'total futures and options on futures volume',
    'single stock equity options volume', 'equity options volume',
    'index options volume', 'total options volume',
    'austraclear settlement and depository',
]

# (csv 列名, section, subsection|None, [标签别名…], since, until)
#   subsection=None 表示该标签在整个 section 内唯一，不需要再切一层。
#   since/until 是**实测**的官方起止月（口径坑 15）；越界为空合法，界内为空抛异常。
COLUMN_SPEC = [
    # ── 现货（Cash Markets）──────────────────────────────────────────
    ('trading_days_cash', 'trading - cash markets', None,
     ['total trading days'], None, None),
    ('trades_cash_total', 'trading - cash markets', 'cash market volume',
     ['total trades'], None, None),
    ('adt_cash_trades', 'trading - cash markets', 'cash market volume',
     ['average daily trades'], None, None),
    ('value_open_trading_audbn', 'trading - cash markets', 'cash market value',
     ['open trading'], None, None),
    ('value_auctions_audbn', 'trading - cash markets', 'cash market value',
     ['auctions trading'], None, None),
    ('value_centrepoint_audbn', 'trading - cash markets', 'cash market value',
     ['centre point'], None, None),
    ('value_tradereport_audbn', 'trading - cash markets', 'cash market value',
     ['trade reporting'], None, None),
    ('value_cash_onmarket_audbn', 'trading - cash markets', 'cash market value',
     ['on-market value'], '2017-10', None),
    ('value_cash_total_audbn', 'trading - cash markets', 'cash market value',
     ['total cash market value', 'total value'], None, None),
    ('adt_cash_onmarket_audbn', 'trading - cash markets', 'cash market value',
     ['on-market average daily value', 'average daily value on-market'], None, None),
    ('adt_cash_total_audbn', 'trading - cash markets', 'cash market value',
     ['total average daily value', 'average daily value',
      # 2017-07 那一期独有的写法，只此一月
      'average daily value on-market and trade reporting'], None, None),
    ('avg_value_per_trade_aud', 'trading - cash markets', 'cash market value',
     ['average value per trade'], None, None),
    ('vix_asx200_avg', 'trading - cash markets', 'cash market value',
     ['s&p/asx 200 vix (average daily value)'], '2019-10', None),
    # ── ASX 24 期货与期货期权 ────────────────────────────────────────
    ('trading_days_futures', 'trading - futures', None,
     ['futures and options total trading days'], None, None),
    ('contracts_futures_total', 'trading - futures', 'futures volume',
     ['total contracts'], None, None),
    ('adv_futures_contracts', 'trading - futures', 'futures volume',
     ['average daily contracts'], None, None),
    ('contracts_options_on_futures_total', 'trading - futures',
     'options on futures volume', ['total contracts'], None, None),
    ('adv_options_on_futures_contracts', 'trading - futures',
     'options on futures volume', ['average daily contracts'], None, None),
    ('contracts_futures_and_options_total', 'trading - futures',
     'total futures and options on futures volume', ['total contracts'], None, None),
    ('adv_futures_and_options_contracts', 'trading - futures',
     'total futures and options on futures volume',
     ['average daily contracts'], None, None),
    # ── 股票期权（ASX Clear ETO）─────────────────────────────────────
    ('trading_days_eto', 'trading - equity options', None,
     ['exchange-traded options total trading days'], None, None),
    ('contracts_single_stock_options_total', 'trading - equity options',
     'single stock equity options volume', ['total contracts'], None, None),
    ('adv_single_stock_options_contracts', 'trading - equity options',
     'single stock equity options volume', ['average daily contracts'], None, None),
    ('contracts_index_options_total', 'trading - equity options',
     'index options volume', ['total contracts'], None, None),
    ('adv_index_options_contracts', 'trading - equity options',
     'index options volume', ['average daily contracts'], None, None),
    # ── 上市与融资 ───────────────────────────────────────────────────
    ('listed_entities_total', 'listings and capital raisings', None,
     ['total listed entities'], None, None),
    ('new_listed_entities', 'listings and capital raisings', None,
     ['new listed entities', 'new listed entities admitted'], None, None),
    ('delisted_entities', 'listings and capital raisings', None,
     ['entities de-listed'], '2024-05', None),
    ('capital_initial_raised_audmn', 'listings and capital raisings', None,
     ['initial capital raised'], None, '2023-09'),
    ('mktcap_new_listings_audmn', 'listings and capital raisings', None,
     ['quoted market capitalisation of new listings',
      'quoted market capital of new listings'], '2023-10', None),
    ('capital_secondary_audmn', 'listings and capital raisings', None,
     ['secondary capital raised'], None, None),
    ('capital_other_scrip_audmn', 'listings and capital raisings', None,
     ['other capital raised including scrip-for-scrip'], None, None),
    ('capital_secondary_total_audmn', 'listings and capital raisings', None,
     ['total secondary capital raised'], None, None),
    ('capital_total_raised_incl_other_audmn', 'listings and capital raisings', None,
     ['total capital raised including other'], None, '2023-09'),
    ('capital_new_quoted_audmn', 'listings and capital raisings', None,
     ['total new capital quoted', 'total initial and secondary capital quoted'],
     '2023-10', None),
    ('mktcap_delisted_audmn', 'listings and capital raisings', None,
     ['quoted market capitalisation of entities de-listed'], '2024-05', None),
    ('capital_net_new_quoted_audmn', 'listings and capital raisings', None,
     ['total net new capital quoted'], '2024-05', None),
    # ── 清算 / 结算 ──────────────────────────────────────────────────
    ('otc_notional_cleared_audbn', 'clearing - otc markets', None,
     ['total notional cleared value'], None, None),
    ('otc_open_notional_audbn', 'clearing - otc markets', None,
     ['open notional cleared value'], None, None),
    ('billable_cash_cleared_audbn', 'clearing - exchange-traded markets', None,
     ['total billable cash market value cleared'], None, None),
    ('margin_cash_onbs_audbn', 'clearing - exchange-traded markets', None,
     ['total cash margins held on balance sheet'], '2019-10', '2024-07'),
    ('margin_total_audbn', 'clearing - exchange-traded markets', None,
     ['total margins held'], '2024-08', None),
    ('chess_holdings_audbn', 'settlement', None,
     ['value of chess holdings - period end'], None, None),
    ('settlement_msgs_mn', 'settlement', None,
     ['dominant settlement messages'], None, None),
    ('austraclear_holdings_audbn', 'settlement', 'austraclear settlement and depository',
     ['austraclear securities holdings - period end'], None, None),
    ('participants_asx_total', 'participants', None,
     ['market/clearing/settlement participants at month end',
      # 2017-06 那一期这一行断成两截（"…at month" / "end"），只在 --backfill 到
      # 2017 年中时才用得上；截断形态不会与别的标签撞车。
      'market/clearing/settlement participants at month'], '2016-07', None),
    ('participants_asx24_total', 'participants', None,
     ['trading/clearing participants at month end'], '2016-07', None),
]

MAR_COLUMNS = [c for c, *_ in COLUMN_SPEC]

# 辅源 SFE 分品种：(csv 列名, section, 合约代码, 取哪一列)
# 代码（AP/YT/XT/IR）比品名稳定，且同一个 `3 Year Bonds / YT` 在
# `Interest Rates - Futures` 与 `Interest Rates - Options` 两段各出现一次 ——
# 与口径坑 3 同一类错误，所以这里同样先切 section 再查代码。
SFE_SPEC = [
    ('contracts_spi200_futures', 'equity indices - futures', 'AP', 'month'),
    ('oi_spi200_futures', 'equity indices - futures', 'AP', 'oi'),
    ('contracts_3y_bond_futures', 'interest rates - futures', 'YT', 'month'),
    ('oi_3y_bond_futures', 'interest rates - futures', 'YT', 'oi'),
    ('contracts_10y_bond_futures', 'interest rates - futures', 'XT', 'month'),
    ('oi_10y_bond_futures', 'interest rates - futures', 'XT', 'oi'),
    ('contracts_90d_bankbill_futures', 'interest rates - futures', 'IR', 'month'),
    ('oi_90d_bankbill_futures', 'interest rates - futures', 'IR', 'oi'),
]
SFE_COLUMNS = [c for c, *_ in SFE_SPEC]

CSV_COLUMNS = ['month'] + MAR_COLUMNS + SFE_COLUMNS


def _values_for(rows, i):
    """取第 i 行标签对应的值列表；本行没有就向下前瞻至多 2 行（口径坑 7）。

    只接受「标签区为空 / 以 '(' 开头 / 以小写字母开头」的续行 —— 正文段落与下一个
    指标的标签都是大写字母开头（`Change on pcp`、`Total contracts`、`Cash market value`），
    所以不会把别人的数字吃过来。碰到不合格的行立即停，宁可空着让 _validate 炸。
    """
    if rows[i][1]:
        return rows[i][1]
    for j in (i + 1, i + 2):
        if j >= len(rows):
            break
        lab, vals = rows[j]
        if lab and not (lab.startswith('(') or lab[0].islower()):
            break
        if vals:
            return vals
    return []


def parse_mar(path, skip_first_page=False):
    """解析一份 MAR PDF，返回 {csv 列名: 值字符串}（缺的键就不出现）。

    skip_first_page：更正稿专用（口径坑 17）。更正稿第 1 页是「错误值 / 正确值」
    对照表，**错误值就印在那一页**，不跳过就会把错值当本月值读走。
    """
    doc = fitz.open(path)
    try:
        rows = []
        for pi in range(doc.page_count):
            if skip_first_page and pi == 0:
                continue
            rows.extend(_page_rows(doc[pi]))
    finally:
        doc.close()

    # (section, subsection, 标签键) -> 值；同键只认第一次出现
    table = {}
    section = sub = None
    for i, (label, vals) in enumerate(rows):
        k = _key(label)
        if not k:
            continue
        hit = _section_of(k)
        if hit and not vals:
            section, sub = hit, None
            continue
        if k in _SUBSECTIONS and not vals:
            sub = k
            continue
        v = _values_for(rows, i)
        if v:
            table.setdefault((section, sub, k), v)

    out = {}
    for name, sec, want_sub, aliases, _since, _until in COLUMN_SPEC:
        for alias in aliases:
            if want_sub is not None:
                v = table.get((sec, want_sub, alias))
            else:
                # subsection 不限定：section 内该标签唯一（已逐月核过），
                # 但 subsection 会一直沿用到下一个小标题，所以要跨 subsection 找。
                cand = [vv for (s, _sb, lab), vv in table.items()
                        if s == sec and lab == alias]
                v = cand[0] if len(cand) == 1 else (None if not cand else cand[0])
            if v:
                out[name] = v[0]        # 口径坑 4：永远取值列从左数第 1 个
                break
    return out


def _assert_self_month(path, month):
    """核对 PDF 抬头自称的数据月与我们打算入库的月份一致。

    数据月是从**文件名**（媒体中心）或**公告标题**（存档）推出来的，两个来源都出过花样：
    文件名有驼峰无分隔的写法、中段还带着一个发布月；标题有不带年份的（那时靠
    「发布月 − 1」倒推）。推错了不会报错，只会把某个月的数字写到另一个月名下 ——
    而月份错位在图上看起来完全正常。这里让 PDF 自己作证，把那条路堵死。
    """
    doc = fitz.open(path)
    try:
        text = re.sub(r'\s+', ' ', '\n'.join(
            doc[i].get_text() for i in range(min(2, doc.page_count))))
    finally:
        doc.close()
    m = _SELF_TITLE.search(text)
    if not m:
        raise AsxFetchError('%s 抬头里找不到 "Monthly Activity Report <月> <年>"，'
                            '无法自证数据月' % os.path.basename(path))
    got = '%s-%02d' % (m.group(2), _MONTHS[m.group(1).lower()])
    if got != month:
        raise AsxFetchError('%s 自称是 %s 的月报，但我们按 %s 入库 —— '
                            '数据月推错了，拒绝写入'
                            % (os.path.basename(path), got, month))


def _pub_date(path):
    """PDF 首页正文第一行的发布日 -> ('YYYY-MM-DD', 出处文字)；读不出返回 (None, None)。

    这是 ASX 自己写在公告抬头上的日期，是「官方发布于 X」唯一合法的来源。
    读不出就让这半句缺席，绝不用下载时间 / Last-Modified / 按节奏推算的日子顶替
    —— 那些看上去一样体面，但都是我们编的。
    """
    doc = fitz.open(path)
    try:
        for label, _vals in _page_rows(doc[0]):
            m = _PUB_DATE.match(label)
            if m:
                d = datetime(int(m.group(3)), _MONTHS[m.group(2).lower()],
                             int(m.group(1)))
                return d.strftime('%Y-%m-%d'), (
                    '%s 第 1 页抬头 "%s"' % (os.path.basename(path), label))
    finally:
        doc.close()
    return None, None


def _sfe_url(path):
    """从 MAR 正文里抠出当期分品种报告直链 -> (url, 'DDMMYYYY')；没有返回 (None, None)。

    不自己按「数据月最后一天」拼 URL：2024 版正文里的那条链接是另一套命名
    （`MonthlyFuturesMarketsReport240731.pdf`，YYMMDD），而且现在整条路径都是
    soft-404（口径坑 2）。跟着官方正文走，官方哪天再改命名也不用改代码。
    """
    doc = fitz.open(path)
    try:
        for pi in range(doc.page_count):
            m = _SFE_LINK.search(doc[pi].get_text())
            if m:
                return m.group(0), m.group(1)
    finally:
        doc.close()
    return None, None


# ══════════════════════════════════════════════════════════════════════
# 辅源解析：Monthly SFE Trading Report（分品种）
# ══════════════════════════════════════════════════════════════════════
_SFE_NUMCUT = 0.30          # 值列 x 起点 ~188，合约代码在 ~156，页宽 595
_SFE_SECTION = re.compile(
    r'^(equity indices|interest rates|commodities|nz interest rates|nz commodities)'
    r' - (futures|options)$', re.I)


def parse_sfe(path, month):
    """解析分品种报告，返回 {csv 列名: 值字符串}。

    列序固定为 [本月量, 去年同月量, %, 年初至今量, 去年同期量, %, 月末 OI, 去年月末 OI, %]，
    百分比与 'na' 不是数字会被 `_num` 丢掉，所以纯数字序列稳定是 6 个：
    index 0 = 本月量，index 4 = 月末未平仓。**不取 YTD**：这份报告的 YTD 是
    **日历年**（表头 "YTD 2026 (149-Days)"），而 MAR 的 YTD 是**财年**（7 月起算），
    两者混用即错（这里根本不入库，从源头断掉这个可能）。
    """
    doc = fitz.open(path)
    try:
        first = doc[0].get_text()
        head = 'Monthly SFE Trading Report for %s' % datetime.strptime(
            month, '%Y-%m').strftime('%B %Y')
        if head not in first:
            raise AsxFetchError('%s 首页抬头不是 %r —— 抓到的可能是别的月份'
                                % (os.path.basename(path), head))
        found = {}
        for pi in range(doc.page_count):
            page = doc[pi]
            cut = page.rect.width * _SFE_NUMCUT
            words = [w for w in page.get_text('words') if w[4].strip()]
            words.sort(key=lambda w: (round(w[1], 1), w[0]))
            buckets = []
            for w in words:
                y = (w[1] + w[3]) / 2.0
                for b in buckets:
                    if abs(b['y'] - y) <= _YTOL:
                        b['w'].append(w)
                        break
                else:
                    buckets.append({'y': y, 'w': [w]})
            section = None
            for b in sorted(buckets, key=lambda b: b['y']):
                ws = sorted(b['w'], key=lambda w: w[0])
                left = [w[4] for w in ws if w[0] < cut]
                nums = [n for n in (_num(w[4]) for w in ws if w[0] >= cut)
                        if n is not None]
                label = _norm(' '.join(left))
                if _SFE_SECTION.match(label):
                    section = label.lower()
                    continue
                if not left or not nums:
                    continue
                code = left[-1]
                if section and re.fullmatch(r'[A-Z]{2}', code):
                    found.setdefault((section, code), nums)
    finally:
        doc.close()

    out = {}
    for name, sec, code, which in SFE_SPEC:
        nums = found.get((sec, code))
        if not nums:
            raise AsxFetchError('分品种报告里找不到 %s / %s（%s）——'
                                '官方表结构可能已变' % (sec, code, name))
        if len(nums) != 6:
            raise AsxFetchError('分品种报告 %s / %s 一行取到 %d 个数字（应为 6 个：'
                                '本月/去年同月/YTD/去年YTD/OI/去年OI）：%s'
                                % (sec, code, len(nums), nums))
        out[name] = nums[0] if which == 'month' else nums[4]
    return out


# ══════════════════════════════════════════════════════════════════════
# 校验
# ══════════════════════════════════════════════════════════════════════
def _f(rec, name):
    v = rec.get(name)
    return None if v in (None, '') else float(v)


def _check_identities(month, rec):
    """用官方自己在同一张表里印出来的加总关系做体检。

    这不是「算出缺的那一格」——缺的格一律留给 _validate 去炸；这是**证明我们没有串行**。
    口径坑 3 那类错误（section 切错、行错位）的特征是「每个数都合法，但装错了格子」，
    只有加总恒等式能当场发现。2017-04 那一期 PDF 值列整体上移一行（口径坑 16），
    就是被第 1 条抓出来的。
    """
    checks = [
        ('期货 + 期货期权 = 合计（总张数）',
         ['contracts_futures_total', 'contracts_options_on_futures_total'],
         'contracts_futures_and_options_total', 0.0),
        ('期货 + 期货期权 = 合计（ADV）',
         ['adv_futures_contracts', 'adv_options_on_futures_contracts'],
         'adv_futures_and_options_contracts', 1.5),          # 官方各自四舍五入到整张
        ('open + auctions + centre point + trade reporting = 现货总成交额',
         ['value_open_trading_audbn', 'value_auctions_audbn',
          'value_centrepoint_audbn', 'value_tradereport_audbn'],
         'value_cash_total_audbn', 0.002),
        ('open + auctions + centre point = on-market 成交额',
         ['value_open_trading_audbn', 'value_auctions_audbn',
          'value_centrepoint_audbn'], 'value_cash_onmarket_audbn', 0.002),
        ('二次融资 + 换股对价 = 二次融资合计',
         ['capital_secondary_audmn', 'capital_other_scrip_audmn'],
         'capital_secondary_total_audmn', 0.5),
    ]
    for desc, parts, total, tol in checks:
        pv = [_f(rec, p) for p in parts]
        tv = _f(rec, total)
        if tv is None or any(v is None for v in pv):
            continue                     # 该月官方没印这几行，交给 _validate 判
        if abs(sum(pv) - tv) > tol:
            raise AsxFetchError(
                '%s 加总恒等式不成立：%s —— %s 之和 %.6f，官方印的 %s = %.6f。'
                '这是解析串行的典型症状（见模块 docstring 口径坑 3 / 16），拒绝写入'
                % (month, desc, parts, sum(pv), total, tv))


def _in_window(month, since, until):
    return (since is None or month >= since) and (until is None or month <= until)


def _validate(month, rec):
    """界内为空一律炸。宁可整月不更新，也不要写出一列悄悄全空的 CSV。"""
    missing = [name for name, _s, _sb, _a, since, until in COLUMN_SPEC
               if _in_window(month, since, until) and not rec.get(name)]
    if missing:
        raise AsxFetchError(
            '%s 解析缺列 %s —— 官方表结构可能已变，或抓到的是 ASX Compliance 版'
            '（见模块 docstring 口径坑 1），拒绝写入' % (month, missing))
    stray = [name for name, _s, _sb, _a, since, until in COLUMN_SPEC
             if not _in_window(month, since, until) and rec.get(name)]
    if stray:
        raise AsxFetchError(
            '%s 解析出了本不该存在的列 %s —— 官方要么恢复了旧行名、要么本模块的'
            'since/until 边界记错了，两种都得人来看，拒绝写入' % (month, stray))
    _check_identities(month, rec)


# ══════════════════════════════════════════════════════════════════════
# 单月抓取
# ══════════════════════════════════════════════════════════════════════
def _download_mar(month, url, is_correction, cache_dir):
    path = os.path.join(cache_dir, 'asx_mar_%s%s.pdf'
                        % (month, '_correction' if is_correction else ''))
    if not os.path.exists(path):
        _write_bytes(path, _http_pdf(url))
    _assert_self_month(path, month)
    return path


def _fetch_one(month, urls, cache_dir, want_sfe=True):
    """下载并解析某一个月，返回 (记录 dict, 发布日, 出处文字)。

    urls = {'orig': url|None, 'corr': url|None}。
    **数值取更正稿，发布日取原版** —— 理由见 _discover_media_centre 的 docstring。
    """
    os.makedirs(cache_dir, exist_ok=True)
    if not (urls.get('orig') or urls.get('corr')):
        raise AsxFetchError('%s 既没有原版也没有更正稿的链接' % month)
    corr_path = (_download_mar(month, urls['corr'], True, cache_dir)
                 if urls.get('corr') else None)
    orig_path = (_download_mar(month, urls['orig'], False, cache_dir)
                 if urls.get('orig') else None)

    path = corr_path or orig_path
    rec = parse_mar(path, skip_first_page=bool(corr_path))
    _validate(month, rec)
    day, evidence = _pub_date(orig_path or corr_path)

    # 分品种（辅源）：官方只保留最近 2 期，抓不到是常态，不能因此让整月失败。
    if want_sfe:
        sfe_url, stamp = _sfe_url(path)
        if sfe_url:
            spath = os.path.join(cache_dir, 'asx_sfe_%s.pdf' % month)
            try:
                if not os.path.exists(spath):
                    _write_bytes(spath, _http_pdf(sfe_url))
                rec.update(parse_sfe(spath, month))
            except AsxFetchError:
                # 404 / soft-404 = 官方已经把这一期撤下来了（滚动 2 期窗口）。
                # 这些列在 series 里天然为空，_validate 不管它们。
                if os.path.exists(spath):
                    os.remove(spath)
    return rec, day, evidence


# ══════════════════════════════════════════════════════════════════════
# 发布日台账
# ══════════════════════════════════════════════════════════════════════
def _source_dates():
    """按路径加载仓库根的 source_dates.py。

    不能裸 import：本模块被 monthly_run 用 spec_from_file_location 加载，
    那时 sys.path 上既没有 fetch/ 也没有仓库根。
    """
    import importlib.util
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    spec = importlib.util.spec_from_file_location(
        'source_dates', os.path.join(root, 'source_dates.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ══════════════════════════════════════════════════════════════════════
# 对外接口
# ══════════════════════════════════════════════════════════════════════
def latest_month(cache_dir):
    """官方源当前最新的数据月 'YYYY-MM'。

    只读媒体中心索引，不下载 PDF —— 「本月发了没有」这个问题索引页就能回答。
    抓不到 / 读不出一律抛 AsxFetchError，不返回 None 掩盖故障。
    """
    os.makedirs(cache_dir, exist_ok=True)
    return max(_discover_media_centre(cache_dir))


def _read_csv(csv_path):
    with open(csv_path, newline='', encoding='utf-8') as f:
        rows = list(csv.reader(f))
    header = rows[0]
    body = [r for r in rows[1:] if r and r[0].strip()]
    return header, body


def _write_csv(csv_path, header, body):
    body.sort(key=lambda r: r[0])
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f, lineterminator='\n')
        w.writerow(header)
        w.writerows(body)


def update(series_dir, cache_dir):
    """把新月份追加进 series/asx.csv，返回新增月份列表（升序）。

    幂等保证：
      · 已存在的月份不重复追加；
      · 已经有值的单元格**永不覆盖** —— ASX 会在同一天补发更正稿改数（口径坑 17），
        也偶尔在后续月报的 pcp 列里体现重述。让自动流程去改历史，等于把「官方悄悄
        改过数」这件事永久掩盖掉；要重刷历史请人工重跑 `--backfill`。
      · 只在既有行**原本为空**的格子上回补。目前唯一会用到的是分品种那 8 列：
        它们的源只保留最近 2 期，所以本月跑的时候上个月那行可能还空着，而下个月
        再想补就永远补不到了 —— 不做这个回补，那 8 列会长期只有最新一行有数。
      · 未被触碰的单元格是原样字符串搬运，所以「什么都没变」时文件字节级不变。
    """
    csv_path = os.path.join(series_dir, 'asx.csv')
    header, body = _read_csv(csv_path)
    idx = {name: i for i, name in enumerate(header)}
    unknown = [c for c in CSV_COLUMNS if c not in idx]
    if unknown:
        raise AsxFetchError('series/asx.csv 里没有这些列：%s' % unknown)

    index = _discover_media_centre(cache_dir)
    have = {r[0]: r for r in body}
    newest = max(index)

    # 要处理的月份：CSV 里还没有的（不早于 SERIES_START），
    # 外加最新那一个月的前一月 —— 后者是为了给分品种那 8 列留一次回补机会。
    todo = sorted(m for m in index if m >= SERIES_START and m not in have)
    prev = _month_shift(newest, -1)
    if prev in have and prev in index and not have[prev][idx[SFE_COLUMNS[0]]].strip():
        todo.append(prev)

    pub = {}
    added = []
    for mon in sorted(set(todo)):
        # 分品种辅源官方只保留最近 2 期（更早的日期是真 404 或 soft-404），
        # 所以只对这 2 个月发那一次请求 —— 补历史时挨个去敲一条必然失败的路径，
        # 既拖慢自己也是给对方站点添堵。
        rec, day, evidence = _fetch_one(
            mon, index[mon], cache_dir, want_sfe=(mon >= prev))
        if day:
            pub[mon] = (day, evidence)
        if mon in have:
            row = have[mon]
            for name in CSV_COLUMNS[1:]:            # 只填空，不覆盖
                if not row[idx[name]].strip() and rec.get(name):
                    row[idx[name]] = rec[name]
            continue
        row = [''] * len(header)
        row[0] = mon
        for name in CSV_COLUMNS[1:]:
            row[idx[name]] = rec.get(name, '')
        have[mon] = row
        body.append(row)
        added.append(mon)

    _write_csv(csv_path, header, body)

    # 记发布日放在落盘之后：写盘失败就不该在台账上留下「这个月官方发过了」这条断言。
    sd = _source_dates()
    for mon in sorted(pub):
        if mon in have and not sd.lookup(series_dir, 'asx', mon):
            sd.record(series_dir, 'asx', mon, pub[mon][0], pub[mon][1])
    return sorted(added)


def _month_shift(month, delta):
    y, m = int(month[:4]), int(month[5:])
    m += delta
    y += (m - 1) // 12
    m = (m - 1) % 12 + 1
    return '%04d-%02d' % (y, m)


def _month_range(start, end):
    out = []
    cur = start
    while cur <= end:
        out.append(cur)
        cur = _month_shift(cur, 1)
    return out


# ══════════════════════════════════════════════════════════════════════
# 历史回补（**人工跑，cron 不碰**）
# ══════════════════════════════════════════════════════════════════════
def _backfill(series_dir, cache_dir, start, end):
    """用公告存档把 [start, end] 补进 series/asx.csv。

    走这条路是因为媒体中心只到 2020-02，再往前只有公告存档有。存档取 PDF 要经过
    一页「点击即接受使用条款」的同意表单 —— 技术上纯 GET 就能读到隐藏字段里的真实直链
    （不 POST、不带 cookie），但让 cron 每月自动穿过它是策略决定，所以这条路
    **只由人显式调用一次**，结果固化进 CSV 之后再也不需要跑。
    """
    csv_path = os.path.join(series_dir, 'asx.csv')
    header, body = _read_csv(csv_path)
    idx = {name: i for i, name in enumerate(header)}
    have = {r[0]: r for r in body}

    index = {}
    titles = {}
    for year in range(int(start[:4]), int(end[:4]) + 2):
        for mon, ids, title, _day, corr in _discover_archive(year):
            if not (start <= mon <= end):
                continue
            index.setdefault(mon, {})['corr' if corr else 'orig'] = ids
            titles.setdefault(mon, []).append(title)

    missing = [m for m in _month_range(start, end) if m not in index]
    if missing:
        raise AsxFetchError('公告存档里找不到这些月份的 MAR：%s' % missing)

    sd = _source_dates()
    added = []
    for mon in _month_range(start, end):
        urls = {k: _archive_pdf_url(v) for k, v in index[mon].items()}
        title = ' + '.join(titles[mon])
        rec, pubday, evidence = _fetch_one(mon, urls, cache_dir, want_sfe=False)
        if mon in have:
            row = have[mon]
            for name in CSV_COLUMNS[1:]:
                if not row[idx[name]].strip() and rec.get(name):
                    row[idx[name]] = rec[name]
        else:
            row = [''] * len(header)
            row[0] = mon
            for name in CSV_COLUMNS[1:]:
                row[idx[name]] = rec.get(name, '')
            have[mon] = row
            body.append(row)
            added.append(mon)
        if pubday and not sd.lookup(series_dir, 'asx', mon):
            sd.record(series_dir, 'asx', mon, pubday, evidence)
        print('  %s  %s  (%s)' % (mon, pubday or '发布日读不出', title))
    _write_csv(csv_path, header, body)
    return sorted(added)


if __name__ == '__main__':
    import sys
    _here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    _series, _cache = os.path.join(_here, 'series'), os.path.join(_here, 'cache')
    if len(sys.argv) >= 2 and sys.argv[1] == '--backfill':
        print('backfilled:', _backfill(_series, _cache, sys.argv[2], sys.argv[3]))
    else:
        print('latest:', latest_month(_cache))
        print('added :', update(_series, _cache))
