# -*- coding: utf-8 -*-
r"""南亚科技（Nanya Technology，2408.TW）月度合并营收 —— 无人值守抓取模块。

对应 build/specs/nanya.py（页面由通用底座 build/single.py 生成），维护一个序列文件：

  series/nanya.csv    month, revenue_ntd_mn

────────────────────────────────────────────────────────────────────────
数据源（四处，各司其职；哪一处能做什么、不能做什么，逐条实测过）
────────────────────────────────────────────────────────────────────────
1) **入库值** —— MOPS 公开资讯观测站「上市公司月营业收入统计表」CSV
   POST https://mopsov.twse.com.tw/server-java/FileDownLoad
        step=9 & functionName=show_file2 & filePath=/t21/sii/
        & fileName=t21sc03_<民国年>_<月>.csv
   一个月一份**全市场**档（2026-07 那份 203,650 字节、1,071 家），UTF-8 with BOM，
   单位新台币千元。2408 那一行的字段：
     營業收入-當月營收 / 營業收入-去年當月營收 / 累計營業收入-當月累計營收 /
     累計營業收入-去年累計營收 / 備註
   选它当主源的理由是**它是申报原件的分发通道**：2013-01 至今每个月都有独立档案，
   一次请求拿一个月、不依赖任何页面版式，而且与公司 IR 年表逐格相等（见口径坑 3）。

2) **最新月探针 + 交叉核对** —— TWSE OpenAPI
   https://openapi.twse.com.tw/v1/opendata/t187ap05_L
   全市场**当期**一份 JSON（595,942 字节 / 1,071 家），单位千元，字段名同上。
   只有最新一期、没有历史，所以只用来回答「官方最新月是哪个月、金额多少」。
   2408 是本国公司，在 _L（上市）里；外国发行人（KY 股）走 TPEx 的 _O 端点。

3) **重述体检** —— 南亚科 IR 月营收年表
   https://www.nanya.com/en/IR/36?Year=<YYYY>    （2013 ~ 当年，一年一页）
   表体在 `<!--IRMonthlyRevenue_li S-->` 与 `E-->` 之间，12 行「月份 / 合并净营收 /
   MoM / YoY」，单位千元，另有一行 Accumulated Revenue。
   这是公司**当下**对历史的口径；拿它和已入库值逐格比，就是重述体检（口径坑 4）。

4) **发布日** —— 南亚科英文新闻稿列表（AJAX，返回 JSON）
   https://www.nanya.com/en/Activity?Action=IR_PressCenter_year_Item&year=<YYYY>&En_Pagetype=0
   （`En_Pagetype=0` 是 Press Releases；`=100` 是 Announcements/重大公告，那里**没有**
   月营收，别取错。）每月一条，标题形如
     "Nanya Technology July 2026 Revenue NT$ 43,868 Million"
   日期形如 "AUG 04, 2026"。2013-01 起 158 条，是本模块唯一「官方自己说的发布日」。

────────────────────────────────────────────────────────────────────────
发布节奏（实测，不是公司承诺）
────────────────────────────────────────────────────────────────────────
· 台湾《证券交易法》要求上市公司次月 10 日前公告上月营收。南亚科的实际惯例比法定
  上限快得多：**次月第 2-9 天**。
  逐条统计（数据月月末到新闻稿日期的日历天数，来源 = 上面第 4 项的新闻稿日期）：
    · 2013-01 ~ 2026-07 共 158 条：第 2 ~ 13 天，中位第 5 天。
      唯一的第 13 天是 2014-09 数据 → 2014-10-13：法定的 10 日当天是双十节连假，顺延。
    · 2022-01 ~ 2026-07 共 55 条：第 2 ~ **9** 天，中位第 4 天，众数第 3 天（22 次）。
      最晚一条是 2022-01 数据 → 2022-02-09（撞农历年）。
  → roster LAG 建议 **(9, 9)**：取近四年半那 55 条的最晚值。
  → **季末月没有例外**：3/6/9/12 月和常规月同一条节奏（2026-06 数据 → 2026-07-03，
     第 3 天），所以两位写同一个数，不像 hood/schw/spgi 那样要给季末月单独放宽。
  → 但**不要拿「次月第 N 天」去外推发布日**，每次去新闻稿列表现读。顺延不规律
     （撞农历年、双十节、清明各是一种走法）。

· ⚠️ **IR 月营收年表（源 3）比新闻稿慢，而且能慢一个多星期。**
  实测 2026-08-13 当天：新闻稿 2026-08-04 已公布 July 2026 = NT$43,868mn、
  TWSE OpenAPI 也已有 11507 = 43,867,609 千元，而 /en/IR/36?Year=2026 的 July 一行
  **还是空的**（Accumulated 仍停在 1-6 月的 131,636,005）。
  → 所以 `latest_month()` 绝不能读 IR 年表，否则每个月都会晚 1-2 周才认出新数据，
     而表现是「南亚科这个月还没发」——一句看上去完全正常的假话。源 3 只做体检。

────────────────────────────────────────────────────────────────────────
口径坑（踩过的，别再踩）
────────────────────────────────────────────────────────────────────────
1. **MOPS 的软失败是 HTTP 200 + 564 字节**。并发拉档（实测 xargs -P 6）会触发限流，
   服务器返回 `200 OK` 加一张 564 字节的 HTML：
     「Overrun - 查詢過於頻繁,請稍後再試!! / Too many query requests from your ip」
   真档是 129,657 ~ 203,650 字节。按状态码判成功会把这张页当 CSV 解析、
   得到 0 行、然后静默认为「那个月 2408 没申报」。
   → 本模块三重护栏：① 正文长度 >= `_MIN_CSV`（100,000）；② 正文里必须有
     `公司代號` 表头；③ 必须解析出 2408 那一行且 `資料年月` 等于请求的月份。
     命中限流页时退避 20 秒重试（`_MOPS_BACKOFF`），并且**顺序取档、每次之间 sleep**，
     不并发 —— 这不是礼貌问题，是并发本身就会把结果变成静默错误。

2. **nanya.com 的证书链在 Python 默认 context 下验不过**。
   www.nanya.com 的叶证书由 `Sectigo Public Server Authentication CA OV R36` 签发，
   对应的根 `Sectigo Public Server Authentication Root R46` **不在** macOS 自带的那
   128 个根里；`ssl.create_default_context()` 当场 CERTIFICATE_VERIFY_FAILED，
   而 `curl` 和 `openssl s_client` 都说 OK（它们用另一套根库）—— 这个不一致会让人
   往「网站挂了 / 被墙了」的方向排查半天。certifi 的 cacert.pem 里有 R46。
   → 见 `_ssl_ctx()`：优先 certifi，没装就退回默认 context 并让该通道整体缺席，
     **绝不降级成 CERT_NONE**。主通道（MOPS / TWSE，源 1、2）不受影响，
     所以 nanya.com 验不过时本模块照样能入库，只是少了体检与发布日。
     同一条坑在 fetch/fx.py 口径坑 9 已经踩过一次（那次是 www.ecb.europa.eu）。

3. **nanya.com 的软 404 也是 HTTP 200**：任何不存在的路径（实测
   /en/Investors/MonthlyRevenue）会 302 到 `/en/Page/102/System error?aspxerrorpath=...`，
   跟随后 **200 + 65,981 字节**的壳页。而真页只有 70,495 ~ 114,021 字节，
   **区间与壳页几乎相接**，光看长度分不开。
   → 判据用内容：IR 年表页必须含 `IRMonthlyRevenue_li S` 这个注释锚点；
     新闻稿 JSON 必须 `success == true` 且 msg 里有 `calendar-detail`。

4. **本序列没有重述，但「比较基期」被重述过 —— 两件事别混。**
   逐格实测（2013-01 ~ 2026-06 共 162 个月，MOPS 月档 vs IR 年表；2026-07 IR 年表还没填）：
   **當月營收 diff = 0，一格不差**。也就是说公司从没改过已公布的月度水平值。
   但公司在 2014 年的申报里把 2013 年 9-12 月的**比较基期**下修了：
     2014-09 申报的「去年當月」3,633,353 vs 2013-09 当时申报的 3,804,586  −4.50%
     2014-10                 4,218,341 vs 4,401,784                        −4.17%
     2014-11                 3,697,581 vs 3,845,626                        −3.85%
     2014-12                 4,033,844 vs 4,168,898                        −3.24%
     （2014-09 的「去年累計」33,274,294 vs 原申报累计 34,537,533，−1,263,239）
   另外每逢年结会把 12 月的基期微调到审计数：2015-12 申报的「去年當月」4,160,806
   vs 2014-12 原申报 4,159,574，+1,232 —— 这 +1,232 正好等于 2014 年审计年报
   「2014 (Adjusted)」49,107,622 与月度加总 49,106,390 的差额。
   → 结论：**「去年當月/去年累計」是另一个量，不是本序列存的那个量。**
     所以本模块把它做成**告警而不是异常**（异常等于每隔几年必然假 FAIL 一次），
     并把 2013-09 登记进 `build/specs/nanya.py` 的 `breaks`：从这一期起，
     用本序列算出来的 2014-09~12 单月同比与公司当年公告的同比对不上。
     真正会抛异常的是**水平值**与 IR 年表不一致（`_drift_check`）。

5. **月度加总可加，但它是「未审计」口径**，与审计年度有可辨识的小差。
   逐年实测（月度加总 vs 官方审计合并营业收入，单位千元，见下面「对账」一节）：
   13 个完整年度里 7 年 diff 恰为 0（2018-2023、2025），最大相对差 −0.046%（2013 年）。
   → 页面上说「季度/YTD 聚合合法」是对的，但**不能说「等于审计数」**。
     具体数字全部写在 build/specs/nanya.py 的图注里，且在 import 期从 CSV 现算。

6. **数据起点是 2013-01，不是「最早可得」。** 南亚科自己在 IR 页脚注写明：
   "Starting 2013, financial statements in accordance with IFRS ... consolidated
   financial figures reported starts from January 2013."
   2012 及以前 IR 只挂**母公司个别**月营收（页面上那个被注释掉的 2012-2016 下拉），
   与合并口径不可比。所以 START_MONTH = 2013-01，这是口径连续的最早月，
   不是能抓到的最早月。

7. **MOPS 历史档的「出表日期」不是发布日**。t21sc03_102_1.csv（2013-01）今天取回来
   写的是 115/08/12 —— 那是 MOPS 现生成这份档的日期，每次取都不一样。
   发布日只能走源 4 的新闻稿日期。TWSE OpenAPI 的「出表日期」同理（是证交所汇总
   全市场那份档的日期，2026-08 那期是 1150812/1150813，比公司公告晚 8-9 天）。

8. **2408 不发月营收「重大讯息」。** MOPS t05st01（重大訊息）在 115/08 只有取得机器
   设备、董事会决议那类，没有月营收 —— 别去那里找发布日。公司英文/中文「Announcements」
   页（En_Pagetype=100）同样一条月营收都没有；月营收只在 Press Releases（=0）里。

9. **新增子公司 MemoLead 不是并购。** 2025 年审计合并报表附注：
   "MemoLead Technology Corp. was officially registered and established on August 29,
   2025, and has since been included in the consolidated financial statements."
   持股 72.10%，2025 年净损 3,642 千元。是**新设**（greenfield）而不是收购，
   没有把一段既有营收凭空并进来，所以不构成伪同比；仍登记进 breaks 备查，
   但 spec 的说明里写清「新设、非并购、营收贡献不可辨识」，不谎称「左右不可比」。

10. **2014-01 / 2014-02 的新闻稿标题金额与申报值差 +4.0%~+4.6%，标题是错的那一边。**
    163 个月逐月扫过，只有这两个月对不上（其余 161 个月标题与申报四舍五入后完全一致）：
      2014-01 标题 NT$4,355mn vs 申报 4,165,035 千元（+4.56%）
      2014-02 标题 NT$3,904mn vs 申报 3,754,520 千元（+3.98%）
    判据不是"标题看着不对"，是加总对审计：申报值加总的 2014 全年 49,106,390 与审计
    49,107,622 只差 +1,232；换成两条标题金额则变成 49,445,835，比审计高 338,213。
    ⇒ 标题是被后续更正取代的旧基期，申报值才是审计基期。这两个月正好落在
    口径坑 4 那段「2013-09 ~ 2014-02 基期被下修 3.2%~4.5%」的窗口里，方向幅度都对得上。
    → `update()` 的新闻稿标题交叉核对对这两个月降级为告警（`_PR_HEADLINE_KNOWN_OFF`），
      否则一次深度回补（把 MAX_BACKFILL 放开重建全序列）必然假 FAIL 在 2014 年初。
      其余月份仍然抛异常。

────────────────────────────────────────────────────────────────────────
对账（2026-08-13 实测；数字就是数字，"看起来对"不算）
────────────────────────────────────────────────────────────────────────
A. 月度加总 vs **官方审计年度**（合并营业收入，单位新台币千元）
   年度审计数取自 MOPS 全市场合并综合损益表 ajax_t163sb04（TYPEK=sii, season=4），
   并与南亚科 IR 自己挂的审计合并财报 PDF 逐年互校（2015/2020/2021/2022/2023/
   2024/2025 七份可解析的 PDF 全部一致）。

     年度   月度加总        官方审计        diff        相对
     2013   46,953,841     46,975,291     −21,450     −0.0457%   ← 全期最大偏差
     2014   49,106,390     49,107,622      −1,232     −0.0025%   ← 年报列名 "2014 (Adjusted)"
     2015   43,869,307     43,875,905      −6,598     −0.0150%
     2016   41,630,894     41,632,505      −1,611     −0.0039%
     2017   54,932,774     54,918,224     +14,550     +0.0265%   ← 唯一月度加总偏高的一年
     2018   84,721,804     84,721,804           0      0
     2019   51,727,458     51,727,458           0      0
     2020   61,005,514     61,005,514           0      0
     2021   85,604,158     85,604,158           0      0
     2022   56,952,275     56,952,275           0      0
     2023   29,892,306     29,892,306           0      0
     2024   34,131,670     34,131,667          +3     +0.0000088%
     2025   66,586,520     66,586,520           0      0
   → 13 个完整年度里 **7 年 diff 恰为 0**（2018-2023、2025），其余 6 年最大 −0.046%（2024 只差 +3 千元）。也就是说月度值是
     未审计申报数，年结时会有极小的审计调整，且公司**不回头改月度序列**。
     2016-2019 那四份 IR 年报 PDF 是扫描件、没有文字层（pdftotext 出 69-612 字节），
     所以那几年的审计数只能走 t163sb04；2015/2020/2021/2022/2023/2024/2025
     七份有文字层的 PDF 与 t163sb04 逐年一致，两条通道互校过。

B. 月度加总 vs **官方季度 / 期中累计**（单位新台币千元）
     期间            月度加总      官方值        diff   官方值出处
     2025 年 1-3 月    7,187,940    7,187,940      0    2026Q1 合并财报 PDF 的比较列
     2026 年 1-3 月   49,086,932   49,086,932      0    2026Q1 合并财报 PDF（IR Id=129）
     2026 年 1-6 月  131,636,005  131,636,005      0    TWSE OpenAPI t187ap06_L_ci（115Q2 累计）
   ⇒ 2026Q2 单季 = 上半年累计 − Q1 = 131,636,005 − 49,086,932 = **82,549,073 千元
     = NT$82,549mn**，与 4/5/6 三个月月度值相加（25,491,201 + 27,669,563 + 29,388,309）
     **逐字相等**。（2026Q2 那份合并财报 PDF 截至 2026-08-13 还没挂上 IR —— 董事会
     2026-08-05 才通过；IR 的下载端点 Id=130 返回 **HTTP 200 + 0 字节**，
     又一个「状态码说成功、正文是空的」的例子。）

C. 月度值 vs **第三源**（同一笔申报的另一条分发通道）
   · MOPS 月档（源 1）逐月拉全 163 份（2013-01 ~ 2026-07）与 series/nanya.csv
     **逐格相等，diff 全部为 0**。
   · MOPS 月档（源 1）vs 南亚科 IR 年表（源 3）：2013-01 ~ 2026-06 共 **162 个月
     逐格相等，diff 全部为 0**（2026-07 那格 IR 年表还是空的；唯一一处 1 千元级差异
     在 IR 页的 2016 年 Accumulated Revenue 行 41,630,895 vs 12 个月相加 41,630,894，
     是那一行自己的四舍五入，不影响任何月度值）。
   · TWSE OpenAPI t187ap05_L（源 2）2026-07：當月營收 **43,867,609** 千元，
     与 MOPS 月档、与新闻稿标题「NT$ 43,868 Million」（四舍五入到百万）三处一致。

────────────────────────────────────────────────────────────────────────
幂等
────────────────────────────────────────────────────────────────────────
没有新月份时 `update()` **一个字节都不写**（连既有行的重排都不做），
series/nanya.csv 字节级不变。已入库值永不覆盖 —— 与官方不一致时抛异常，由人判断。

━━ 依赖 ━━ 只用标准库；体检与发布日两条支线额外需要 certifi（口径坑 2），
没有 certifi 时那两条支线自动缺席、主链不受影响。
"""

from __future__ import annotations

import csv
import datetime as _dt
import io
import json
import os
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

TICKER = 'nanya'
TWSE_CODE = '2408'
START_MONTH = '2013-01'
COLUMNS = ['month', 'revenue_ntd_mn']

MOPS_DL = 'https://mopsov.twse.com.tw/server-java/FileDownLoad'
TWSE_API = 'https://openapi.twse.com.tw/v1/opendata/t187ap05_L'
NY_ORIGIN = 'https://www.nanya.com'
NY_IR_REV = NY_ORIGIN + '/en/IR/36?Year=%d'
NY_PR = NY_ORIGIN + '/en/Activity?Action=IR_PressCenter_year_Item&year=%d&En_Pagetype=0'

_UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
       '(KHTML, like Gecko) Chrome/126.0 Safari/537.36')

# 真档 129,657 ~ 203,650 字节；限流页 564 字节（口径坑 1）
_MIN_CSV = 100_000
_MOPS_BACKOFF = 20          # 秒；命中限流页后的退避
_MOPS_GAP = 1.5             # 秒；顺序取档之间的间隔，别并发
_MIN_JSON = 100_000         # t187ap05_L 实测 595,942 字节
_MIN_HTML = 60_000          # 只做粗筛；真正的判据是 _IR_ANCHOR（口径坑 3）
_IR_ANCHOR = 'IRMonthlyRevenue_li S'

# 一次 update 最多补几个月。正常一次补 1 个；补到 24 说明序列已经断了很久，
# 那是人该看一眼的事（而且顺序取 24 份 200KB 的全市场档要跑一分钟以上）。
MAX_BACKFILL = 24

_MON_EN = ('January', 'February', 'March', 'April', 'May', 'June',
           'July', 'August', 'September', 'October', 'November', 'December')
_MON3 = {m[:3].upper(): i + 1 for i, m in enumerate(_MON_EN)}

# 官方审计年度合并营业收入（新台币千元）。用途只有一个：`selfcheck()` 拿它复算
# 上面「对账 A」那张表，确认月度加总与审计数的差还是那个量级。
# 出处：MOPS ajax_t163sb04（TYPEK=sii, season=4, year=民国年）+ 南亚科 IR 审计合并
# 财报 PDF 互校。**这不是入库数据**，不参与任何写入。
_ANNUAL_AUDITED = {
    2013: 46_975_291, 2014: 49_107_622, 2015: 43_875_905, 2016: 41_632_505,
    2017: 54_918_224, 2018: 84_721_804, 2019: 51_727_458, 2020: 61_005_514,
    2021: 85_604_158, 2022: 56_952_275, 2023: 29_892_306, 2024: 34_131_667,
    2025: 66_586_520,
}

# 新闻稿标题金额与申报值对不上的**已知**月份（口径坑 10）。全历史 163 个月里只有这两个，
# 逐月扫过一遍确认没有第三个。**申报值是对的、标题是旧基期**：
#   2014-01 标题 NT$4,355mn vs 申报 4,165,035 千元（+4.56%）
#   2014-02 标题 NT$3,904mn vs 申报 3,754,520 千元（+3.98%）
# 判据不是「标题看着不对」而是加总对审计：2014 年申报值加总 49,106,390 与审计
# 49,107,622 只差 +1,232；若改用两条标题金额，2014 全年会变成 49,445,835、
# 比审计高 338,213 —— 也就是说标题是被后续更正取代的旧数，申报值才是审计基期。
# 这两个月落在 2013-09 ~ 2014-02 那段「基期被下修 3.2%~4.5%」的窗口里（口径坑 4），
# 方向与幅度都对得上。放这里的唯一目的：**深度回补时别让这条护栏假 FAIL**。
_PR_HEADLINE_KNOWN_OFF = {
    '2014-01': '标题 NT$4,355mn 是更正前旧基期，申报 4,165,035 千元才对得上 2014 审计数',
    '2014-02': '标题 NT$3,904mn 是更正前旧基期，申报 3,754,520 千元才对得上 2014 审计数',
}


class NanyaFetchError(RuntimeError):
    """本模块的故障出口。抓不到 / 认不出来 / 与官方对不上，一律抛它，不返回 None。"""


# ── 网络 ────────────────────────────────────────────────────────────────
def _ssl_ctx():
    """给 www.nanya.com 用的 context：优先 certifi 的根库（口径坑 2）。

    **不降级成 CERT_NONE**：宁可让体检与发布日两条支线整体缺席
    （MOPS / TWSE 主链照常入库），也不要为了一条支线把校验关掉。
    """
    try:
        import certifi
    except ImportError:
        return ssl.create_default_context()
    return ssl.create_default_context(cafile=certifi.where())


def _get(url, *, data=None, timeout=180, tries=3, context=None):
    last = None
    for _ in range(tries):
        try:
            req = urllib.request.Request(
                url, data=data,
                headers={'User-Agent': _UA, 'Accept': '*/*'})
            return urllib.request.urlopen(req, timeout=timeout, context=context).read()
        except Exception as exc:                                   # noqa: BLE001
            last = exc
            time.sleep(2)
    raise NanyaFetchError(f'{url} 取不到：{last!r}')


# ── 源 1：MOPS 月档 ──────────────────────────────────────────────────────
def _mops_csv(year, month, cache_dir=None):
    """取某个月的全市场月营收 CSV，返回 decode 好的正文。

    三重护栏见口径坑 1：长度、表头、以及调用方再核 `資料年月`。
    """
    roc = year - 1911
    fname = f't21sc03_{roc}_{month}.csv'
    body = None
    if cache_dir:
        p = os.path.join(cache_dir, 'nanya_' + fname)
        if os.path.exists(p) and os.path.getsize(p) >= _MIN_CSV:
            body = open(p, 'rb').read()
    if body is None:
        payload = urllib.parse.urlencode({
            'step': '9', 'functionName': 'show_file2',
            'filePath': '/t21/sii/', 'fileName': fname}).encode()
        for attempt in range(3):
            body = _get(MOPS_DL, data=payload, tries=2)
            if len(body) >= _MIN_CSV:
                break
            head = body[:400].decode('utf-8', 'ignore')
            if 'Overrun' in head or '過於頻繁' in head:
                # HTTP 200 + 564 字节的限流页。退避重试，不当成「这个月没数据」。
                print(f'[nanya][warn] MOPS 限流（{len(body)} 字节），'
                      f'退避 {_MOPS_BACKOFF}s 后重试 {fname}')
                time.sleep(_MOPS_BACKOFF)
                continue
            raise NanyaFetchError(
                f'MOPS {fname} 只有 {len(body)} 字节（<{_MIN_CSV}），'
                f'不是月营收档；开头：{head[:160]!r}')
        else:
            raise NanyaFetchError(f'MOPS {fname} 连续 3 次拿到限流页，本次放弃')
        if cache_dir:
            os.makedirs(cache_dir, exist_ok=True)
            open(os.path.join(cache_dir, 'nanya_' + fname), 'wb').write(body)
        time.sleep(_MOPS_GAP)
    try:
        text = body.decode('utf-8-sig')
    except UnicodeDecodeError:
        text = body.decode('big5', 'ignore')
    if '公司代號' not in text:
        raise NanyaFetchError(f'MOPS {fname} 里没有「公司代號」表头，版式变了？')
    return text


def _mops_row(year, month, cache_dir=None):
    """返回 2408 在该月档里的整行 dict。找不到就抛异常，不返回 None。"""
    text = _mops_csv(year, month, cache_dir)
    for row in csv.DictReader(io.StringIO(text)):
        if (row.get('公司代號') or '').strip() == TWSE_CODE:
            row = {(k or '').strip(): (v or '').strip() for k, v in row.items()}
            ym = row.get('資料年月', '')
            want = (f'{year - 1911}/{month}', f'{year - 1911}{month:02d}')
            if ym not in want:
                raise NanyaFetchError(
                    f'MOPS {year}-{month:02d} 档里 2408 的資料年月是 {ym!r}，'
                    f'不是 {want[0]!r} —— 取到了别的月份的档')
            return row
    raise NanyaFetchError(f'MOPS {year}-{month:02d} 档里没有 {TWSE_CODE} 那一行')


def _mops_month(year, month, cache_dir=None):
    """(当月营收 千元, 去年当月营收 千元 or None, 整行)。"""
    row = _mops_row(year, month, cache_dir)
    cur = float(row['營業收入-當月營收'])
    try:
        base = float(row['營業收入-去年當月營收'])
    except (KeyError, ValueError):
        base = None
    return cur, base, row


# ── 源 2：TWSE OpenAPI ──────────────────────────────────────────────────
def _twse_current():
    """('YYYY-MM', 当月营收 千元)。抓不到抛异常 —— 它是 latest_month 的主探针。"""
    blob = _get(TWSE_API, timeout=120)
    if len(blob) < _MIN_JSON:
        raise NanyaFetchError(f'TWSE OpenAPI 只有 {len(blob)} 字节，疑似错误页')
    recs = json.loads(blob.decode('utf-8', 'ignore'))
    if not isinstance(recs, list) or not recs:
        raise NanyaFetchError('TWSE OpenAPI 返回的不是非空列表')
    for rec in recs:
        if str(rec.get('公司代號', '')).strip() == TWSE_CODE:
            roc = str(rec['資料年月']).strip()          # 11507 = 2026-07
            month = f'{int(roc[:-2]) + 1911}-{int(roc[-2:]):02d}'
            return month, float(rec['營業收入-當月營收'])
    raise NanyaFetchError(f'TWSE OpenAPI 当期名单里没有 {TWSE_CODE}（{len(recs)} 家）')


# ── 源 3：IR 年表（重述体检用；比新闻稿慢，绝不当最新月探针）───────────────
def _ir_year(year):
    """{'YYYY-MM': 千元} —— 该年 IR 年表里已填的月份。取不到返回 None（不抛）。"""
    try:
        html = _get(NY_IR_REV % year, timeout=90, tries=2,
                    context=_ssl_ctx()).decode('utf-8', 'ignore')
    except NanyaFetchError as exc:
        print(f'[nanya][warn] IR 年表 {year} 取不到，重述体检跳过：{exc}')
        return None
    if len(html) < _MIN_HTML or _IR_ANCHOR not in html:
        # 软 404 是 200 + 65,981 字节的 System error 壳页（口径坑 3）
        print(f'[nanya][warn] IR 年表 {year} 拿到的不是月营收页'
              f'（{len(html)} 字节，无 {_IR_ANCHOR!r}），重述体检跳过')
        return None
    seg = html.split(_IR_ANCHOR, 1)[1].split('IRMonthlyRevenue_li E', 1)[0]
    out = {}
    named = 0                       # 认出月份名的行数（不管那格填没填）
    for name, val in re.findall(
            r'(?is)<tr>\s*<td>(.*?)</td>\s*<td[^>]*>(.*?)</td>', seg):
        name = re.sub(r'<[^>]+>', '', name).strip()
        val = re.sub(r'<[^>]+>', '', val).strip().replace(',', '').replace('&nbsp;', '')
        if name not in _MON_EN:
            continue
        named += 1
        if val:
            try:
                out[f'{year}-{_MON_EN.index(name) + 1:02d}'] = float(val)
            except ValueError:
                pass
    # 锚点还在、行却一个都认不出来 = 表体版式变了。这时 out 是空 dict，
    # 而空 dict 会让 _drift_check 静默比对 0 个月然后报「全部一致」——
    # 正是仓库硬规矩 1 说的那种 HTTP 200 静默失败。**空表体不等于表体没填**：
    # 当年 1 月初 12 行都在、值全空是正常的（那时 named == 12、out == {}），
    # 所以判据用 named 而不是 out。
    if named == 0:
        print(f'[nanya][warn] IR 年表 {year} 锚点在、但一行月份都解析不出来'
              f'（{len(seg)} 字节表体）—— 版式变了，重述体检跳过')
        return None
    return out


# ── 源 4：新闻稿发布日 ──────────────────────────────────────────────────
def _press_releases(year):
    """[(数据月 'YYYY-MM', 发布日 'YYYY-MM-DD', 标题里的 NT$mn)]，取不到返回 []。"""
    try:
        blob = _get(NY_PR % year, timeout=90, tries=2, context=_ssl_ctx())
        doc = json.loads(blob.decode('utf-8', 'ignore'))
    except (NanyaFetchError, ValueError) as exc:
        print(f'[nanya][warn] {year} 新闻稿列表取不到，发布日跳过：{exc!r}')
        return []
    if not doc.get('success') or 'calendar-detail' not in (doc.get('msg') or ''):
        print(f'[nanya][warn] {year} 新闻稿列表返回的不是稿件列表，发布日跳过')
        return []
    out = []
    for blk in doc['msg'].split('calendar-row3')[1:]:
        dm = re.search(r'col-xs-9 col-sm-12">([A-Z]{3} \d{2}, \d{4})<', blk)
        tm = re.search(r'calendar-detail" href="[^"]*">(.*?)</a>', blk, re.S)
        if not (dm and tm):
            continue
        title = re.sub(r'\s+', ' ', re.sub('<[^>]+>', '', tm.group(1))).strip()
        # "Nanya Technology July 2026 Revenue NT$ 43,868 Million"
        # 2016-03 与 2020 下半年那 6 条的月名是缩写或省了年份，所以月名与年份都放宽
        rm = re.search(r'(' + '|'.join(m[:3] for m in _MON_EN) +
                       r')[a-z]*\.?\s*(\d{4})?\s+Revenue\s+NT\$\s*([\d,.]+)\s*Million',
                       title, re.I)
        if not rm:
            continue
        p = dm.group(1)
        rel = f'{p[8:12]}-{_MON3[p[:3]]:02d}-{p[4:6]}'
        mo = _MON3[rm.group(1)[:3].upper()]
        yy = int(rm.group(2)) if rm.group(2) else (
            int(rel[:4]) - (1 if mo == 12 and rel[5:7] == '01' else 0))
        out.append((f'{yy}-{mo:02d}', rel, float(rm.group(3).replace(',', ''))))
    return out


def _pr_years(month):
    """某个数据月的新闻稿会挂在哪一年的列表里（按序试）。

    12 月的稿子发在**次年**（实测 2012-12 → 2013-01-03），其余月份发在当年。
    只列该试的那一两年 —— 无脑试 `y+1` 会在当年数据上去请求一个还不存在的年份，
    每个月打印一条无意义的 warn，久了就没人看 warn 了。
    """
    y = int(month[:4])
    return (y + 1, y) if month[5:7] == '12' else (y,)


def release_date(month):
    """某个数据月的官方发布日 'YYYY-MM-DD'（新闻稿日期），拿不到返回 None。"""
    for cand in _pr_years(month):
        for ym, rel, _ in _press_releases(cand):
            if ym == month:
                return rel
    return None


# ── 契约函数 ────────────────────────────────────────────────────────────
def latest_month(cache_dir):                                       # noqa: ARG001
    """官方源当前最新月 'YYYY-MM'。

    走 TWSE OpenAPI（源 2）—— 一次请求、当期一份、与 MOPS 月档同步。
    **不读 IR 年表**：它慢 1-2 周（发布节奏那节的实测），拿它当探针会每月假报
    「还没发」。TWSE 挂了就退回 MOPS：从当月往回探最多 3 个月。
    """
    try:
        return _twse_current()[0]
    except NanyaFetchError as exc:
        print(f'[nanya][warn] TWSE OpenAPI 探针失败，改用 MOPS 回探：{exc}')
    today = _dt.date.today()
    y, m = today.year, today.month
    for _ in range(3):
        m -= 1
        if m == 0:
            y, m = y - 1, 12
        try:
            _mops_month(y, m, cache_dir)
            return f'{y}-{m:02d}'
        except NanyaFetchError:
            continue
    raise NanyaFetchError('TWSE 与 MOPS 两条探针都没能确认最新月')


def _read_series(csv_path):
    with open(csv_path, newline='', encoding='utf-8') as fh:
        rows = list(csv.reader(fh))
    header, body = rows[0], [r for r in rows[1:] if r and r[0].strip()]
    if header != COLUMNS:
        raise NanyaFetchError(f'series/nanya.csv 列不对：{header} != {COLUMNS}')
    seen = set()
    for r in body:
        if r[0] in seen:
            raise NanyaFetchError(f'series/nanya.csv 有重复月份 {r[0]}')
        seen.add(r[0])
    return header, body


def _fmt(k_ntd):
    """千元 → NT$mn 字符串（3 位小数 = 保住千元级精度，不丢一格）。"""
    return f'{k_ntd / 1000:.3f}'


def _next_month(ym):
    y, m = int(ym[:4]), int(ym[5:7])
    return f'{y + 1}-01' if m == 12 else f'{y}-{m + 1:02d}'


def _drift_check(have, cache_dir):                                 # noqa: ARG001
    """重述体检：已入库水平值 vs 公司 IR 年表当下的口径。不一致 → 抛异常。

    只查最近两年（两次请求）。理由：IR 年表一年一页，而重述真要发生，
    先出现在最近的年份上；把 14 年全查一遍要 14 次请求，代价与收益不成比例。
    IR 取不到（证书 / 改版 / 壳页）时**跳过**并打印 —— 体检缺席比误报好，
    真正的护栏是「已有值永不覆盖」。
    """
    if not have:
        return
    newest = max(have)
    drift = []
    checked = 0
    for year in (int(newest[:4]) - 1, int(newest[:4])):
        got = _ir_year(year)
        if got is None:
            continue
        for month, k in got.items():
            if month in have:
                checked += 1
                want = _fmt(k)
                if have[month][1] != want:
                    drift.append((month, have[month][1], want))
    if drift:
        raise NanyaFetchError(
            '南亚科 IR 年表与已入库值不一致（疑似重述或解析变形），本次不写入：\n  '
            + '\n  '.join(f'{m}: 库内 {old} vs 官方 {new}' for m, old, new in drift[:6])
            + '\n（口径坑 4：水平值历来一格不差；先人工判断是重述还是解析出错）')
    if checked == 0:
        # 一格都没比到 ≠ 全部一致。两条支线都可能悄悄归零（证书没过、壳页、版式变动），
        # 而「全部一致」这句话看上去完全正常 —— 必须说成体检没做。
        print('[nanya][warn] 重述体检一格都没比到（IR 年表取不到 / 版式变了 / 那两年还没填），'
              '本次体检视为未执行 —— 护栏只剩「已入库值永不覆盖」')
        return
    print(f'[nanya] 重述体检：IR 年表逐格比对 {checked} 个月，全部一致')


def update(series_dir, cache_dir):
    """把新月份追加进 series/nanya.csv，返回新增月份列表（升序）。

    幂等：没有新月份时**一个字节都不写**（既有行连重排都不做）。
    已入库值永不覆盖 —— 与官方不一致时抛异常（口径坑 4），由人判断。
    """
    csv_path = os.path.join(series_dir, 'nanya.csv')
    header, body = _read_series(csv_path)
    have = {r[0]: r for r in body}

    latest = latest_month(cache_dir)
    if have:
        cursor = _next_month(max(have))
    else:
        cursor = START_MONTH
    wanted = []
    while cursor <= latest:
        wanted.append(cursor)
        cursor = _next_month(cursor)
    if len(wanted) > MAX_BACKFILL:
        raise NanyaFetchError(
            f'要补 {len(wanted)} 个月（{wanted[0]} ~ {wanted[-1]}），超过 '
            f'MAX_BACKFILL={MAX_BACKFILL}。序列断得太久，先人工确认再放开。')

    # 重述体检放在写入之前：官方改过历史就整批不写
    _drift_check(have, cache_dir)

    added, fetched = [], {}
    for ym in wanted:
        y, m = int(ym[:4]), int(ym[5:7])
        cur, base, row = _mops_month(y, m, cache_dir)
        fetched[ym] = (cur, base, row)
        body.append([ym, _fmt(cur)])
        added.append(ym)

    if not added:
        print(f'[nanya] 无新月份（库内最新 {max(have) if have else "空"}，'
              f'官方最新 {latest}），series/nanya.csv 未改动')
        return []

    body.sort(key=lambda r: r[0])
    with open(csv_path, 'w', newline='', encoding='utf-8') as fh:
        w = csv.writer(fh, lineterminator='\n')
        w.writerow(header)
        w.writerows(body)

    now = {r[0]: r[1] for r in body}

    # ── 交叉核对 1：TWSE OpenAPI（同一笔申报的另一条分发通道）
    try:
        tw_month, tw_val = _twse_current()
        if tw_month in fetched and abs(fetched[tw_month][0] - tw_val) > 0.5:
            raise NanyaFetchError(
                f'{tw_month} MOPS 月档 {fetched[tw_month][0]:,.0f} 与 TWSE OpenAPI '
                f'{tw_val:,.0f} 千元不一致 —— 同一笔申报的两条通道对不上')
        print(f'[nanya] 交叉核对 TWSE OpenAPI {tw_month} = {tw_val:,.0f} 千元：一致')
    except NanyaFetchError as exc:
        if '不一致' in str(exc):
            raise
        print(f'[nanya][warn] TWSE 交叉核对跳过：{exc}')

    # ── 交叉核对 2：新闻稿标题里的 NT$mn（四舍五入到百万，容差 1）
    for ym in added:
        hit = [p for cand in _pr_years(ym) for p in _press_releases(cand) if p[0] == ym]
        if not hit:
            print(f'[nanya][warn] {ym} 找不到对应新闻稿，标题核对与发布日跳过')
            continue
        _, rel, mn = hit[0]
        got_mn = fetched[ym][0] / 1000.0
        if abs(got_mn - mn) > 1.0:
            if ym in _PR_HEADLINE_KNOWN_OFF:
                # 已查实的两个月：标题是更正前的旧基期，申报值才对得上审计数。
                # 抛异常等于让一次深度回补必然假 FAIL 在 2014 年初（口径坑 10）。
                print(f'[nanya][warn] {ym} 新闻稿标题 NT${mn:,.0f}mn 与申报 '
                      f'NT${got_mn:,.3f}mn 差 {got_mn - mn:+,.3f}mn —— 已知例外：'
                      f'{_PR_HEADLINE_KNOWN_OFF[ym]}。按申报值入库。')
                _record_release(series_dir, ym, rel)
                continue
            raise NanyaFetchError(
                f'{ym} MOPS 月档 NT${got_mn:,.3f}mn 与新闻稿标题 NT${mn:,.0f}mn '
                f'差 {got_mn - mn:+,.3f}mn，超过四舍五入容差')
        print(f'[nanya] 交叉核对新闻稿 {ym}：NT${mn:,.0f}mn（{rel} 发布）一致')
        _record_release(series_dir, ym, rel)

    # ── 告警（不抛）：公司自报的「去年當月」基期 vs 库内同月水平值。
    # 这两个是**不同的量**，历史上 2014-09~12 差过 3.2%~4.5%（口径坑 4）。
    for ym in added:
        base = fetched[ym][1]
        prev = f'{int(ym[:4]) - 1}-{ym[5:7]}'
        if base and prev in now:
            mine = float(now[prev]) * 1000.0
            if abs(base - mine) > 0.5:
                print(f'[nanya][warn] {ym} 申报里的「去年當月」{base:,.0f} 与库内 '
                      f'{prev} 的 {mine:,.0f} 千元差 {base - mine:+,.0f}'
                      f'（{(base - mine) / mine * 100:+.3f}%）—— 公司重述了比较基期。'
                      f'水平值序列不动（口径坑 4），但请确认 spec 的 breaks 是否要加一条。')

    print(f'[nanya] 新增 {len(added)} 个月：{", ".join(added)}')
    return added


def _record_release(series_dir, month, day):
    """把发布日记进全仓共用的 series/source_dates.csv（只在有新月份时调用）。

    只写自己这一行，其余行由 source_dates.record 原样保留 + flock。
    写失败不阻断入库 —— 少一句「官方发布于」远好过整条链 FAIL。
    """
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            'source_dates', os.path.join(ROOT, 'source_dates.py'))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.record(series_dir, TICKER, month, day,
                   f'IR 新闻稿列表标题日期 "Nanya Technology ... Revenue NT$..." （{day}）')
    except Exception as exc:                                       # noqa: BLE001
        print(f'[nanya][warn] source_dates 记录失败（不阻断）：{exc!r}')


# ── 自检（不写任何文件；`python3 fetch/nanya.py` 直接跑）──────────────────
def selfcheck(series_dir=None):
    """复算模块头「对账 A」那张表：月度加总 vs 官方审计年度。"""
    series_dir = series_dir or os.path.join(ROOT, 'series')
    _, body = _read_series(os.path.join(series_dir, 'nanya.csv'))
    per_year = {}
    for month, val in body:
        per_year.setdefault(int(month[:4]), []).append(float(val))
    print(f'{"年度":<6}{"月度加总(千元)":>18}{"官方审计":>16}{"diff":>12}{"相对":>12}')
    for y in sorted(per_year):
        if len(per_year[y]) != 12 or y not in _ANNUAL_AUDITED:
            continue
        s = round(sum(per_year[y]) * 1000)
        a = _ANNUAL_AUDITED[y]
        print(f'{y:<6}{s:>18,}{a:>16,}{s - a:>+12,}{(s - a) / a * 100:>+11.4f}%')


if __name__ == '__main__':
    selfcheck()
