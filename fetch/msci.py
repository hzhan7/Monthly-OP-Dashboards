# -*- coding: utf-8 -*-
"""MSCI Inc. — 挂钩 MSCI 股票指数的 ETF 月度 AUM 抓取模块。

═══ 源 ═══
    https://ir.msci.com/aum-etfs-linked-msci-indexes
    页面标题「AUM in ETFs Linked to MSCI Equity Indexes」。

为什么用 IR 页面而不是找 xlsx：MSCI 这张表**没有**对应的下载文件。IR 站（Q4 Inc.
托管的 Drupal）把整张表**服务端渲染**成 <table class="table nirtable">，一次
GET 就拿到 2008-12 至今的全历史，不需要 JS、不需要 Cookie、不需要登录态。
所以本模块**不依赖浏览器**，可无人值守跑。
（/download-library、/static-files/* 下没有这份 AUM 数据；SEC 10-Q 里只有季度
平均值的文字描述，粒度不够，不作为备源。）

⚠ 2026-08-05 实测过「普通 python urllib + 桌面 Chrome UA，HTTP 200，无 Cloudflare /
Akamai / PerimeterX 拦截」—— **这句 2026-09-10 起不再成立**。ir.msci.com 在 Akamai
Bot Manager 后面，09-10 起 stdlib urllib 按本文件的请求头每发 45 s 读超时（只带 UA 则
403 秒回），生产连挂三轮。现在主通道是 curl_cffi，urllib 退为兜底；实测表、排班与判据
见 _download() 上方「两条通道」。

═══ 发布节奏 ═══
    每月一次，更新「上一个自然月」。MSCI 不为此发新闻稿，只是悄悄改这个页面，
    所以没有可订阅的事件——只能轮询。经验节奏是次月中旬（本文件写于
    2026-08-05，向源站取到的**未走缓存**的页面最新行仍是 Jun'26，Jul'26 未上线）。
    → 调度建议：次月 10 日起每天跑一次 latest_month()，出现新月份再 update()。
      不要在月初 1–5 号就判定「源挂了」，那只是还没发。

═══ CDN 缓存陷阱（无人值守的头号坑）═══
    响应头是 `cache-control: public, max-age=0, s-maxage=2592000` —— 边缘节点
    （Akamai EdgeConnect）可以缓存这个页面 **30 天**。新月份上线后，轮询可能连续
    好几天都还看到旧表，然后误判「MSCI 这个月没发」。

    ⚠ **2026-09-07 实测：query-string 形式的 cache-buster 已经完全失效**，本文件
    原来那句「加 `?_=<ts>` 之后 x-age=0，是源站现渲染的页面」不再成立 ——

        裸 URL                      x-age=227439  hits=93  ETag "1788535440"（63.3 小时前渲染）
        URL + "?_=<ts>"             x-age=227273  hits=92  ETag "1788535440"（同一份，逐字节相同）
        URL + "/?_=<ts>"（尾斜杠）    x-age=9627    hits=2   ETag "1788753086"（2.8 小时前）
        路径大小写变体（从未请求过）      x-age=0       hits=—   ETag = 请求时刻（冷 miss）

    边缘现在**按 path 做缓存键、完全忽略 query string**。所以：

      · **唯一有效的杠杆是「一个从未被请求过的 path」**，见 _cache_key_url()。
        请求头一律无效 —— Pragma / no-store / must-revalidate / If-Modified-Since /
        Accept-Encoding / HEAD 全试过，拿到的都是同一份钉住的副本。
      · **尾斜杠不是修法，是一次性的**：它只是换了个还没被填的键，第一次请求把它
        填上之后，它自己也被钉住 30 天。任何**固定** URL 的写法都会在第一次成功
        之后自动退化成读缓存。这一条最容易被下一个人重新踩：别再往 URL 上加常量。
      · `x-age` **不能当新鲜度判据**：实测同一份副本（ETag 相同）在不同边缘节点
        报出 0 与 9452 两个值。它是非标准头，语义由节点自己定。
      · 可信的只有 `Last-Modified`（本站 `ETag` 就是它的 unix 戳，两者逐秒吻合），
        它是**这份 HTML 的渲染时刻**，所以 `now − Last-Modified` 就是这份 HTML 的
        真实陈旧度。判据见 MAX_RENDER_AGE。冷 miss 的响应里带 `X-Drupal-Dynamic-Cache:
        UNCACHEABLE`，但它和 `x-age: 0` 一样**不是现渲染的证据**：2026-09-12 在 curl_cffi
        通道上，这两个头原样出现在 31 分钟、44 分钟前渲染的副本上（见 _download() 上方「两条通道」）。

    另：判断有没有新数据仍然只能看解析出来的 max(month)；上面这些只保证「你看的
    这份 HTML 是刚渲染的」，不保证里面有新月份。

    ═══ 口径坑 ═══
1. 这是**第三方 ETF 的资产规模**，不是 MSCI 自己的钱、也不是 MSCI 营收。它的
   意义在于 asset-based fee ≈ 季度平均 AUM × 有效基点费率，所以 avg 列比 eop
   列更重要（build_msci.py 的 Exhibit 5 就是用季度平均）。
2. 两列不是同一种量：
     aum_eop_usdbn  = Month-End Balance，月末快照
     aum_avg_usdbn  = Monthly Average Balance，月内日均
   avg 不是相邻两个 eop 的平均，**不要用 eop 反推 avg**（例如 2026-05 eop
   2828.6 高于 2026-06 eop 2818.3，但 06 的 avg 2795.1 反而高于 05 的 2745.9）。
3. 表里含 ETN，MSCI 自述占比 <1%，无法拆分，历史序列一直是这个口径。
4. **数据供应商在 2019-04/05 换过**（Bloomberg → Refinitiv，页脚注 1/2/3）。
   Apr-2019 那一行两列口径还不一致（月末已是 Refinitiv，月均是 4/1–4/25
   Bloomberg + 4/26–4/30 Refinitiv 的缝合）。build_msci.py 在 2019-04 画了
   break line 就是为这个。跨 2019 年做同比要知道这条缝。
5. 数值全是 MSCI 的**估算值**（页面原文 "estimates"），不是审计数。MSCI 保留
   重述历史行的权利——本模块每次跑都会重算已入库月份并比对，发现不一致时
   打 warning 到 stderr，但**不覆盖** series/msci.csv（仓库约定：CSV 是真值，
   重述要人工确认后再改）。
   ⚠ 「数值变了」与「整行没了」是两回事，处置也不同：前者是源的正常行为，只喊；
   后者不是（源从不删行），那是我们把行解析丢了的信号，直接抛。见 update() 哨兵②。
6. 月份写法在表格里混用直角撇 ' (U+0027) 和弯撇 ’ (U+2019)、混用 &nbsp;、
   月份后还挂脚注号——解析器必须全都容忍，不能按固定字符串切。
   ⚠ **脚注号有两种写法，而且同一张表里会混用**：绝大多数行是标签
   `<td>Jun’26 <sup>3</sup></td>`（_clean 删得掉），但 2026-08 实测 Jul'26 那一行
   写成了**裸文本** `<td>Jul’26 3</td>`（删不掉）。原来的 _MONTH_RE 结尾锚 `$`
   不容忍尾随字符，于是这一行被当说明行 continue 掉 —— 源上明明有 7 月，
   latest_month() 却返回 6 月，fetch 干净地报 NOCHANGE，**没有任何报错**。
   这个坏法比抓取失败危险得多：它不产生 FAIL，连续失败计数、红点、断档哨兵
   全都抓不到它，页面就一直挂着旧数据。修法是两条一起：
     (a) _MONTH_RE 容忍尾随的裸脚注尾巴（见该常量旁注；尾巴前**必须**有空白或
         逗号，否则四位年 `Jul’2026` 会被拆成「年 20 + 脚注 26」= 2020-07）；
     (b) parse() 增加**行数对账**——凡是「长得像数据行」却没能落库的行，一律抛
         异常：后两格都是金额而首格不像月份的（写法变了），以及首格是月份而整行
         格数不够的（表结构变了）。(a) 只挡住已知的这一种变体，(b) 才是挡住下一种
         没见过的变体的那道。别只留 (a)。
   这两道都是从「页面上有什么」这一侧查的，看不见「金额格变成横杠」之类的坏法；
   反侧那道在 update() 哨兵②：已入库的月份在官网解析结果里消失就抛。三道一起才齐。

═══ 接口 ═══
    latest_month(cache_dir) -> "YYYY-MM"        官方源当前最新月；抓不到抛异常
    update(series_dir, cache_dir) -> list[str]  追加新月份到 series/msci.csv
"""

import csv
import html as _html
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import date as _date, datetime, timezone
from email.utils import parsedate_to_datetime

URL = "https://ir.msci.com/aum-etfs-linked-msci-indexes"

# 常规桌面 UA。**只给兜底通道 urllib 用，别拿它去覆盖 curl_cffi 的 UA**（理由见
# _via_curl_cffi）。
#
# 当初加它的理由：2026-08-05 带默认 UA "Python-urllib/3.x" 时会间歇性挂住（连试两次，
# 一次 25s 超时、一次 0.8s 正常），换这个 Chrome UA 后多次均稳定 <1s。那是 09-09 之前
# 的事。09-10 起换 UA 救不回来，而且拒法跟着**请求头集合**走，不是同一组头时好时坏：
# _via_urllib 带着它再加 Accept / Accept-Language / Cache-Control / Pragma 四个头，09-12 实测
# 5 发 5 发 45 s 读超时（生产 09-10~09-12 每发也是）；同一键隔 2 分钟只带它一个头，0.25 s 就
# 403。实测表见 _download() 上方「两条通道」。
# **也别以为把版本号改新就行**：curl_cffi 发的是 Chrome/146，但它
# 同时换掉了 TLS / HTTP2 指纹和整套请求头，UA 版本单独起不起作用从没测过（台账
# prod_ua_chrome126_stale_untested_criterion_20260912）。
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
# 这份 HTML 最多允许有多旧。26 小时 = 一天（缓存键按日历日轮换）+ 2 小时余量：
# 生产上 cron 一天跑一次，每次都是当日键的首次请求 ⇒ render_age ≈ 0；同一天人工
# 重跑会复用同一个键，最坏 24 小时，仍在阈值内，**不会误报**。
# 上界够狠：s-maxage 是 720 小时，26 小时与它差 27 倍，任何被钉住的副本都拦得下。
# 代价上界是「新数据晚一天入库」—— 而红点要到月末后第 23 天才亮（LAG 17 + GRACE 5
# + 1），余量十天，一天承受得起。
MAX_RENDER_AGE = 26 * 3600

# ── 重试、超时、总时限（排班见 _download() 上方「两条通道」）──────────────────────
# RETRIES 是**主通道**的发数：curl_cffi 一发没成就退避 5 s、10 s 再来；兜底 urllib 只在最后
# 一轮上一发。curl_cffi 导入失败时 urllib 顶上当主通道、拿满 RETRIES 发（= 改写前的单通道）。
# 它原来的旁注是「间歇性挂起是本源唯一的失败模式，重试是主要防线」—— 09-10 起不对了：按
# 客户端拦截时同一条通道重试几次都一样（生产三轮、每轮 3 发全超时），主要防线是换通道，
# 重试只防单发抖动。
#
# TIMEOUT 是每一发的超时，但对两条通道**不是一个意思**（127.0.0.1 滴灌实测，服务器每秒
# 吐 1 字节）：
#   · curl_cffi 的 timeout 是整发墙钟，到点就抛 Timeout；
#   · urllib 的 timeout 只管单次 socket 读，每收到一个字节就重新计时，所以 timeout=2 也能
#     一直读下去，那一发被滴灌时**不封顶**。实测数字见 _download() 上方「排班」。
#
# BUDGET 是一次 _download() 里所有发共用的总时限，护栏 A 换键后重跑的那一整条排班也算在
# 里面。到点就不再发新请求、不再退避，带着已试过的每一发抛；每一发的 timeout 也压到剩余
# 时间以内。
#   · 单个键按排班最坏 = curl_cffi 3 × 45 + 退避 15 + urllib 45 = 195 s；curl_cffi 导入
#     失败时 = urllib 3 × 45 + 15 = 150 s。240 s 两种都放得下，换键那条只能用剩下的。
#   · 不设它，换键会把 195 s 整个再来一遍（390 s）。monthly_run 串行跑各家，09-12 整轮
#     6 分 41 秒（日志 07:18:28 建、07:25:09 最后写入），旧码 msci 按排班自己就占 150 s。
#   · 它**不是硬上界**：已经发出去的那发 urllib 若被滴灌，只受单次读超时约束，会超出。
#     09-12 实测 urllib 的挂法是一个字节都不回的 45 s 读超时，碰不到这一条。
# 改写第一版旁注写的「最坏 3 × (45 + 45) + 15 = 285 s，只在注定失败的那一天才付」两半都不对：
# 换键会翻倍、urllib 滴灌不封顶；而且那版每轮 curl_cffi → urllib 交错，curl_cffi 偶发抖一下
# 就要先陪 urllib 读挂 45 s，并不只在注定失败的日子才付。
RETRIES = 3
TIMEOUT = 45
BUDGET = 240

# 「2xx 却没有 nirtable」时，正文多大才算「源站的整页」而不是拦截页 / 挑战页。它只决定报错
# 怎么说，不决定抛不抛（见「每一发怎么判」）。09-12 实测：curl_cffi 拿到的整页 63,547 B，其中
# 表格 30,773 B，去掉表格还剩 32,774 B；urllib 被拦的 Akamai「Access Denied」页 407 B。
# 取 20 KB，两边都有余量。
PAGE_MIN_BYTES = 20_000

# ── 缓存键 ────────────────────────────────────────────────────────────────
# 边缘按 path 做键（见文件头「CDN 缓存陷阱」），所以每天换一个**没被请求过的
# path**，才能拿到源站现渲染的页面。手法是把 slug 里的字母位大写：源站的路径匹配
# 大小写不敏感（2026-09-07 实测 6 个单/双位变体全部 HTTP 200、x-age=0、解析出
# 213 个月），而边缘的缓存键大小写敏感。
#
# ⚠ **池长必须远大于 s-maxage 的 30 天**，否则键回环时会撞上自己 30 天前钉住的
#   旧副本，护栏 A 就会天天误 FAIL —— 这是本模块唯一一个「写小了会让护栏反过来
#   咬人」的常数。24 个字母位取一或二 = 300 种，是 30 天的 10 倍。
# ⚠ 若哪天源站改成大小写敏感，这里会拿到 **HTTP 404**，而 _download() 把 404 当
#   确定性错误、不换通道当场抛（403 / 429 / 5xx 只算这一发没成，见「每一发怎么判」）——
#   那是一次响亮的失败，不是静默退化，可接受。报错会同时点出「slug 改了 / 页面下线」这
#   另一种可能，别一看到 404 就认定是大小写。
_SLUG = "aum-etfs-linked-msci-indexes"
_URL_ROOT = URL[:-len(_SLUG)]
_LETTER_POS = [i for i, c in enumerate(_SLUG) if c.isalpha()]
_KEY_POOL = ([(i,) for i in _LETTER_POS]
             + [(i, j) for a, i in enumerate(_LETTER_POS)
                for j in _LETTER_POS[a + 1:]])          # 24 + 276 = 300


def _cache_key_url(day, shift=0):
    """按日历日派生一个当天专用的 URL。shift 用于换一个「久未使用」的键重试。"""
    idxs = _KEY_POOL[(day.toordinal() + shift) % len(_KEY_POOL)]
    b = list(_SLUG)
    for i in idxs:
        b[i] = b[i].upper()
    return _URL_ROOT + "".join(b)


def _render_age(hdrs, now):
    """这份 HTML 距今多少秒前渲染的；两个头都没有时返回 None（调用方 WARN 放行）。"""
    lm = hdrs.get("Last-Modified")
    if lm:
        try:
            return now - parsedate_to_datetime(lm).timestamp()
        except (TypeError, ValueError):
            pass
    et = (hdrs.get("ETag") or "").strip('"')             # 本站 ETag = 渲染时刻 unix 戳
    return now - int(et) if et.isdigit() else None


SERIES_FILE = "msci.csv"
MONTH_COL = "month"
# 解析器能产出的列。CSV 里若出现这里没有的列，update() 会抛异常而不是写空值。
VALUE_COLS = {
    "aum_eop_usdbn": "eop",   # Month-End Balance
    "aum_avg_usdbn": "avg",   # Monthly Average Balance
}

_MON = {m: i + 1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun",
     "jul", "aug", "sep", "oct", "nov", "dec"])}

# 只认这一张表；nirtable 是 Q4/Drupal IR 模板给数据表的固定 class
_TABLE_RE = re.compile(
    r'<table[^>]*class="[^"]*nirtable[^"]*"[^>]*>(.*?)</table>', re.S | re.I)
_ROW_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S | re.I)
_CELL_RE = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.S | re.I)
# 月份格：三字母月 + 任意撇号 + 两位年 + **可选的裸脚注尾巴**
#
# 尾巴那一段是为 `Jul’26 3` 这种写法加的（见文件头口径坑 6）。它被刻意限死成
# 「数字 / 逗号 / 空白 / 星号剑标」这几类字符，不是写成 `.*$`：
# 放开成任意尾随字符，说明行（"Dec'08 onwards, source: …"）也会被当成月份行吃进来，
# 那是比漏一行更坏的错——漏行只是数据旧了，错行会把说明文字变成一个月度数据点。
#
# 脚注号与年份之间**必须隔一个空白或逗号**（`[\s,]+`，不是 `[\s,]*`）。写成 `*`
# 时四位年会被拆成「两位年 + 脚注号」：`Jul’2026` → 年 `20`、脚注 `26` → 2020-07，
# 凭空捏造一个历史点，正是上一段说的那种「错行」。今天它侥幸撞得停（表里 2020 年
# 十二个月俱在，会被下面的「同月出现两次」拦下），但那是运气不是设计 —— 靠的是
# 「碰巧已有同月」这个跟本条毫无关系的前提。改成 `+` 之后 `Jul’2026` 直接不匹配，
# 转由行数对账抛错：源真换成四位年时，要的是一次响亮的失败，不是一个错年份。
_MONTH_RE = re.compile(
    r"^([A-Za-z]{3})[’'‘ʼ`]\s*(\d{2})"      # Jul’26
    r"(?:[\s,]+[\d*†‡§¶]+)*"                # 可选：裸脚注号，可有多个（"3"、"1,2"）
    r"\s*$")


# ────────────────────────────── 下载 ──────────────────────────────
#
# ═══ 两条通道（2026-09-10 起）═══
# 09-09 07:17 生产还用 urllib 取到了页面（cache/msci_aum_20260908.html，63,184 B）；
# 09-10 / 09-11 / 09-12 三轮全是「MSCI IR 连续 3 次抓取失败：TimeoutError: The read
# operation timed out」，抛在落盘之前。同一个 24 小时窗口里 ndaq 的 ir.nasdaq.com 也以
# 同样的形态开始失败 —— 两家同在 gcs-web IR 平台、同在 Akamai Bot Manager 后面，收紧的
# 是平台这一侧，不是 MSCI 页面变了。
#
# 2026-09-12 本机实测，按「通道 + 请求头集合」分行。时间是 SGT；「变体键」= 当日生产键
# auM-etFs-linked-msci-indexes（生产失败的正是它），「规范 URL」= 全小写 slug：
#
#   通道与请求头                              结果
#   urllib + _via_urllib 的全套头             45 s 读超时、一个字节都没回，5 发 5 发，全在变体键：
#     （Chrome/126 UA、Accept、                 10:52:59 45.27 s；10:58:54 45.04 s；
#       Accept-Language、Cache-Control、        11:08–11:10 三发 45.09 / 45.05 / 45.41 s。
#       Pragma）                                生产 09-10~09-12 每发也是它
#   urllib + 只带 Chrome/126 UA               10:54:45 变体键 403，0.25 s，正文是 407 B 的
#                                             Akamai「Access Denied」
#   urllib，只记了 UA、没记整组头             10:36 规范 URL：Chrome/126 UA → 403 秒回；
#                                             curl 的 UA → 403；Python-urllib 默认 UA → 12 s 读超时
#   curl_cffi(impersonate='chrome')，不传头   200 / 63,547 B / 0.7–1.7 s / 含 nirtable：
#                                             10:36 规范 URL；07:34、10:54、10:58、11:07、
#                                             11:39 变体键（11:39 那次拿到的是缓存副本，见下）
#
# 读法：
#   · urllib 是 403 秒回还是 45 s 读超时，跟着**请求头集合**走，不是同一组头时好时坏：
#     10:52:59 与 10:54:45 两发同一变体键、同一 IP、隔 2 分钟，只差 Accept / Accept-Language
#     / Cache-Control / Pragma 四个头，一发读挂 45 s、一发 0.25 s 就 403。是四个里的哪个没
#     隔离。所以兜底通道按现在的头**每发都要白烧满一个超时**，排班里只让它在最后一轮上一发
#     （见下）。别为了让它失败得快一点去删头：墙撤了那天哪组头进得来，没测过。
#   · curl_cffi 这条也会拿到缓存副本，别以为它次次现渲染：同一个变体键上留了响应头记录的
#     07:34 / 10:54 / 11:07 三次都是 Last-Modified = Date；11:39:19 那次拿到的却是 11:07:55 渲染的那份
#     （Last-Modified 比 Date 早 31 分钟，与 11:07 那次的响应逐字节相同），而 x-age 照样报 0、
#     X-Drupal-Dynamic-Cache 照样是 UNCACHEABLE。是边缘还是源站那层缓存的，没隔离。两条结论：
#     ① 文件头「可信的只有 Last-Modified」在 curl_cffi 通道上同样成立，x-age 0 与 UNCACHEABLE
#     都不是现渲染的证据；② **别删按日轮换的缓存键和护栏 A**：钉住 30 天是 09-07 在 urllib 通道
#     上实测的，兜底仍走它；curl_cffi 这条也实测到了缓存，只是这回 31 分钟、远在 MAX_RENDER_AGE
#     以内。
#   · 按日轮换的缓存键不是诱因：curl_cffi 请求那条变体键次次 200，解析 213 行与
#     series/msci.csv 零差异。别去动 _cache_key_url()。
#
# 判据**不要收窄**：curl_cffi 一次同时换掉了 TLS 指纹 / HTTP2 指纹 / 头集合与顺序 /
# UA 版本，没做单变量隔离，只能说判据落在这几类的并集里（同 fetch/cme.py 文件头那段）。
# 所以修法是整套换通道，不是改 UA 字符串。
#
# ═══ 排班（一次 _once() 取一个 URL）═══
#   curl_cffi#1 →没成→ 退避 5 s → curl_cffi#2 →没成→ 退避 10 s → curl_cffi#3 →没成→ urllib#1 →没成→ 抛
#   · curl_cffi 打头、重试都给它：今天只有它进得来；全仓既有范式也是它打头（fetch/cme.py
#     的 _CHANNELS、fetch/hood.py 的 fetch_bytes）。延迟 import。
#   · urllib 只在最后一轮上一发：零依赖，墙哪天撤了（09-09 之前它一直能用）还能走，但按现在
#     的头它每发白烧 45 s。改写第一版是每轮 curl_cffi → urllib 交错，curl_cffi 偶发抖一下，就得
#     先陪 urllib 读挂 45 s 才轮到 curl_cffi#2；现在抖一下只花 5 s 退避。
#   · curl_cffi 导入失败（没装 / 装了但动态库坏了）时一发请求都发不出去，urllib 当场顶上当
#     主通道、拿满 RETRIES 发 —— 就是改写前的单通道行为。
#   · 所有发共用 BUDGET（见其旁注），每一发的 timeout 压到剩余时间以内。两条通道的 timeout
#     语义不同，127.0.0.1 滴灌实测（服务器每秒吐 1 字节，两次复测一致）：curl_cffi 是整发墙钟，
#     timeout=3 在 3.00 s、timeout=2 在 2.00 s 抛 Timeout；urllib 只管单次读，timeout=3 跑了
#     9.03–9.04 s、timeout=2 跑了 5.02 s，都正常读完。所以 BUDGET 管得住 curl_cffi，管不住一发
#     正在被滴灌的 urllib。
#
# ═══ 每一发怎么判 ═══
#   · 最终 URL ≠ 请求 URL → **当场抛**，不管状态码、不管有没有表（重定向护栏）。跳回规范
#     路径，是文件头「CDN 缓存陷阱」要防的「缓存键静默变回被钉住的那个」；跳去别处（挑战页 /
#     同意页 / slug 改了）是没见过的形态 —— 09-12 实测的拦法只有 403 与读超时 —— 没见过的就
#     交给人看。改写前的码也是一发就抛。改写第一版把它排在「收下」之后才判，没有表的重定向
#     就被当成通道失败重试了 6 发，报错里连最终 URL 和「重定向」几个字都没有（复核本机实测）。
#   · 404 → **确定性错误，不换通道，当场抛**。404 不是拦截的样子（拦截给的是 403 / 读超时），
#     它说的是「没有这个 path」，换条通道只会把同一句话再听一遍。缓存键那段写的「源站改成
#     大小写敏感」就靠这一支响亮地报出来。
#   · 2xx 且正文含 nirtable → 收下（护栏 A 在 _download 里判）。
#   · 其余一律算这条通道这一发没成，记下来按排班继续：网络错误 / 超时 / 403 / 429 / 5xx /
#     其它状态码，以及「2xx 却没有 nirtable」。最后这类再分两种，只决定报错怎么说：
#       - 正文不到 PAGE_MIN_BYTES，或渲染年龄超过 MAX_RENDER_AGE / 读不出 → 拦截页 / 挑战页 / 旧副本；
#       - 正文够大、渲染年龄在上限内 → 源站的整页，只是没有表 → 多半是页面改版。报错首行
#         直说「拿到了整页却没有表」，不说「全部没取到」、不往 Bot Manager 上引（第一版就是
#         这么误诊的，复核本机实测）。它**也不当场抛**：单发分不清「改版」和「源站那一刻表格
#         区块没渲染出来」—— 后者没见过，但单发排除不了，退避重试能好；代价在墙撤了的日子是
#         十几秒，在 urllib 被读挂的日子多一个 45 s。
#
# ⚠ Akamai 会往 curl_cffi 拿到的 HTML 里注入 Bot Manager 的脚本：</head> 前一段
#   <script src="https://ir.msci.com/akam/13/<id>">、</body> 前一个 noscript 像素（urllib 取到的
#   历次缓存里 0 次）。注入的内容和大小**每次都可能不同**，别拿任何固定差值当判据：akam id 会变；
#   09-12 11:52 那次与 11:07、11:39 是同一次渲染（Last-Modified、ETag 都相同），却多了一段约 1 KB
#   的 AKSB 性能脚本，比 11:39 那份大 1,020 B。当天几份 curl_cffi 快照 parse() 结果完全相同（213 行）。
#   **字节相同与否都不是内容信号**：以后谁要拿 cache/msci_aum_*.html 推断「源哪天更新了」、
#   或做 sha 去重，比 parse() 的 max(month)，别比字节。
#   这也说明这条通道靠的是 Bot Manager 继续放行「不执行传感器 JS 的会话」，我们控制不了；
#   真被收紧时 curl_cffi 也会拿到 403 / 挑战页，报错会把每一发的结果列出来。


def _via_curl_cffi(url, timeout):
    """通道 1：curl_cffi 用真 Chrome 的 TLS / HTTP2 指纹与整套请求头发包。
    返回 (状态码, 正文, 响应头, 最终 URL)；HTTP 错误码不抛，交给 _download 统一分类。
    timeout 是**整发墙钟**（见「排班」里的滴灌实测）。

    **一个请求头都不传**，User-Agent 更不许手工塞：impersonate='chrome' 把 UA、
    sec-ch-ua、Sec-Fetch-*、Accept、Accept-Language 连同指纹配成一整套（本机回显实测
    它自己就发 Chrome/146 的 UA 和 Accept-Language: en-US,en;q=0.9），手工覆盖任何一个
    都可能自相矛盾。urllib 那条带的 Cache-Control / Pragma 这里也不带：文件头「CDN 缓存
    陷阱」实测过请求头对边缘缓存键全无作用，带上只会让头集合偏离真 Chrome。

    延迟 import：导入失败（没装 / 动态库坏了）时抛 ImportError，_download 把这条标成
    导入失败、本次不再排，urllib 当场顶上。
    curl_cffi 默认跟随重定向，r.url 是**跳完之后**的地址（本机实测 301 之后 r.url 已变），
    重定向护栏靠的就是它；r.headers.get() 大小写不敏感（同一次实测），护栏 A 不用分通道。
    """
    from curl_cffi import requests as cr
    r = cr.get(url, impersonate="chrome", timeout=timeout)
    return r.status_code, r.content, r.headers, r.url


def _via_urllib(url, timeout):
    """通道 2：零依赖兜底。返回值同 _via_curl_cffi；HTTP 错误码也照常返回、不抛 ——
    403 的正文就是拦截页，要落快照。网络类错误（超时 / 连接重置）照常抛给调用方。
    timeout 只管单次 socket 读，被滴灌时整发不封顶（见「排班」）。"""
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            # 头与最终 URL 必须在这里取：出了 with 就没了。
            # final_url 是护栏的一部分 —— urllib 默认跟随重定向，若源站哪天
            # 给变体路径加了 301 到规范路径，缓存键会**静默**变回那个被钉住
            # 的键，而只 read() 的写法完全看不见这件事。
            return r.status, r.read(), r.headers, r.url
    except urllib.error.HTTPError as e:
        try:
            body = e.read()
        except Exception:             # 读错误页正文时又超时：状态码已经够分类了
            body = b""
        return e.code, body, e.headers, e.geturl() or url


_CHANNELS = (("curl_cffi", _via_curl_cffi), ("urllib", _via_urllib))


def _snapshot(cache_dir, name, raw):
    """把一份**没被收下**的响应原样落盘，返回路径；没有正文时返回 None。

    原来 nirtable / 护栏 A / 重定向这几支都在落盘之前抛，报错却叫人「看落盘文件」，
    而那一轮 cache/ 里根本没有这个文件（台账
    msci_download_error_msg_points_to_unwritten_file_20260910）。所以凡是要抛、要按排班
    继续的支，先把拿到的字节存下来，再把路径写进报错 / 出声那一行。

    **一次 _download() 里每个名字只写一次**：blocked 快照的名字带通道和「该通道第几发」，
    换键那次再加 shift_ 前缀；stale、rejected 各自最多写一次。所以某一行点名的路径里就是
    那一发的正文。改写第一版每条通道只有一个固定名、每发覆盖，报错里 curl_cffi#1 那行指向
    的文件其实装着 curl_cffi#3 的正文（复核本机实测）—— 和上面台账是同一类毛病。
    跨次运行仍然覆盖、名字集合固定（最多 14 个），墙挂几周也不会堆出一排；代价是 cache/ 里
    可能留着更早某次的同名文件，**以报错里点名的路径为准**，别按目录里有什么去猜。

    文件名刻意**不是** msci_aum_<日期>.html 的形状：那个形状是「源这一天的真实快照」，
    monthly_run.py FACT_GATE 那段拿它观测源的真实发布日，拦截页混进去会污染这份观测。
    """
    if not raw:
        return None
    path = os.path.join(cache_dir, f"msci_aum_{name}.html")
    with open(path, "wb") as f:
        f.write(raw)
    return path


def _download(cache_dir):
    """抓页面并落盘到 cache_dir。返回 (html_text, saved_path)。

    每次都存一份带日期的快照：这张表是「活页面」，MSCI 改了历史行不会留痕，
    留快照才能事后判断某次数值变化是重述还是解析 bug。
    没被收下的响应另存（见 _snapshot()），路径写进报错 / 出声那一行：
      msci_aum_blocked_[shift_]<通道>_<第几发>.html   按排班算没成的那一发
      msci_aum_stale.html                            护栏 A 换键之前，当日键拿到的旧副本
      msci_aum_rejected.html                         当场抛的那一发（重定向 / 404 / 护栏 A）
    """
    os.makedirs(cache_dir, exist_ok=True)
    deadline = time.monotonic() + BUDGET     # 当日键与换键两次 _once() 共用，见 BUDGET 旁注

    def _once(url, key="", ctx=""):
        """按上方「排班」「每一发怎么判」取 url，返回 (raw, headers, final_url)。

        key 只进 blocked 快照的文件名（换键那次传 "shift_"，免得盖掉当日键那几发）；
        ctx 补进抛错首行（换键那次写明当日键拿到了什么）。
        """
        tried = []           # (通道, 类别, 那一行)：降级成功时喊出来，全挂时整串抛出去
        dead = set()         # 导入失败的通道：重试也不会好，本次不再排
        count = {}           # 每条通道各自第几发：快照名和 #n 都用它
        out_of_time = False

        def schedule():
            for rnd in range(RETRIES):
                if rnd:
                    time.sleep(max(0.0, min(5 * rnd, deadline - time.monotonic())))
                for name, fn in _CHANNELS:
                    if name in dead:
                        continue
                    primary = next((n for n, _ in _CHANNELS if n not in dead), None)
                    if name != primary and rnd < RETRIES - 1:
                        continue             # 兜底只在最后一轮上一发
                    yield name, fn

        for name, fn in schedule():
            left = deadline - time.monotonic()
            if left < 3:                     # 剩这点时间连一发 curl_cffi 都不够看
                out_of_time = True
                break
            count[name] = count.get(name, 0) + 1
            tag = f"{name}#{count[name]}"
            t0 = time.monotonic()
            try:
                status, raw, hdrs, final = fn(url, min(TIMEOUT, left))
            except ImportError as e:
                dead.add(name)
                tried.append((name, "import",
                              f"{tag}: 导入失败，一发请求都没发出去（{type(e).__name__}: {e}）"
                              + (f"—— 2026-09-10 起它是唯一实测进得来的通道，修："
                                 f"{sys.executable} -m pip install curl_cffi==0.16.0"
                                 "（版本同 requirements.txt；装着却导入失败多半是动态库坏了）"
                                 if name == "curl_cffi" else "")))
                continue
            except Exception as e:    # 超时 / 连接重置 / TLS 握手失败 / DNS
                tried.append((name, "net", f"{tag}: {type(e).__name__}: {e}"
                                           f"（{time.monotonic() - t0:.1f} s）"))
                continue
            took = time.monotonic() - t0
            has_table = b"nirtable" in raw
            before = "".join(f"\n  {ln}" for _, _, ln in tried)

            if final != url:
                snap = _snapshot(cache_dir, "rejected", raw)
                age = _render_age(hdrs, time.time())
                # 边缘按 path 做键、区分大小写、忽略 query（文件头「CDN 缓存陷阱」），所以只有逐字
                # 跳回规范 URL 才是「缓存键变回被钉住的那个」；跳到同一页面的另一种写法（带 query /
                # 尾斜杠 / 另一个大小写变体）键未必变回去，更像挑战页验完跳回原地址，分开报。
                base = final.split("#")[0]
                home = base == URL
                same_page = not home and base.split("?")[0].rstrip("/").lower() == URL
                raise RuntimeError(
                    f"MSCI IR 把请求重定向到了 {final!r}（{tag}，请求的是 {url!r}；跳完之后 "
                    f"HTTP {status}，{len(raw)} B，{'含' if has_table else '没有'} nirtable"
                    + ("" if age is None else f"，渲染于 {age / 3600:.1f} 小时前")
                    + (f"，响应已存 {snap}" if snap else "，没有正文") + "）"
                    + ("—— 缓存键已经变回规范路径，此后拿到的都可能是被钉住 30 天的旧副本。"
                       "需要重新找一种能生成新缓存键的写法，见文件头「CDN 缓存陷阱」。"
                       if home else
                       "—— 跳到了同一页面的另一种写法（加了 query / 尾斜杠 / 换了大小写），缓存键"
                       "未必变回规范路径，多半是挑战页验完跳回；打开快照看拿到的是什么，见 _download()"
                       " 上方「每一发怎么判」。"
                       if same_page else
                       "—— 跳去的不是这个页面本身（挑战页 / 同意页 / slug 改了？）。这是没见过的"
                       "形态，不换通道当场抛；打开快照看跳到了什么，见 _download() 上方「每一发"
                       "怎么判」。")
                    + (f"\n  此前：{before}" if tried else ""))

            if status == 404:
                snap = _snapshot(cache_dir, "rejected", raw)
                raise RuntimeError(
                    f"MSCI IR 返回 HTTP 404（{tag}，URL={url}，没有重定向，{took:.1f} s，"
                    + (f"响应已存 {snap}" if snap else "响应没有正文") + "）"
                    "—— 这是确定性错误不是拦截，不换通道。"
                    + ("两种可能：源站改成了路径大小写敏感（这个 URL 是 _cache_key_url() 的"
                       "大小写变体，那样按日轮换就此失效，见其旁注），或者 slug 改了 / 页面下线。"
                       f"手工请求规范小写 URL {URL} 看状态码与 Last-Modified 可以分清（它可能是"
                       "边缘钉住的旧副本，别只看 200）。"
                       if url != url.lower() else
                       "请求的已经是规范小写 URL：slug 改了或页面下线了。")
                    + (f"\n  此前：{before}" if tried else ""))

            if 200 <= status < 300 and has_table:
                if tried:
                    # 主通道 / 第一发没成、后面成了：数据没事，但这是「下一次可能就
                    # 全挂」的预警（同 fetch/cme.py 的口径）。tried 只在抛异常时才会
                    # 被人读到，这里不喊，等兜底也挂的那天日志里连一句铺垫都没有。
                    print(f"[msci] ⚠ 靠 {tag} 才取到页面（URL={url}），前序失败："
                          + "；".join(ln for _, _, ln in tried), file=sys.stderr)
                return raw, hdrs, final

            snap = _snapshot(cache_dir, f"blocked_{key}{name}_{count[name]}", raw)
            saved = f"，响应已存 {snap}" if snap else "，没有正文"
            if 200 <= status < 300:
                age = _render_age(hdrs, time.time())
                aged = "，渲染年龄不明" if age is None else f"，渲染于 {age / 3600:.1f} 小时前"
                # 渲染年龄读不出也不算整页：边缘自己吐的挑战页不带 Drupal 的 Last-Modified / ETag。
                if len(raw) >= PAGE_MIN_BYTES and age is not None and age <= MAX_RENDER_AGE:
                    kind, why = "page", f"整页却没有 nirtable 表格（多半是页面改版）{aged}"
                else:
                    kind, why = "chal", f"没有 nirtable 表格（拦截页 / 挑战页 / 旧副本）{aged}"
            elif status in (403, 429):
                kind, why = "block", ("被拦" if status == 403 else "被限流")
            elif 500 <= status < 600:
                kind, why = "http", "源站或边缘出错"
            elif 300 <= status < 400:
                kind, why = "http", "重定向没跟完（环 / 超过跳数上限）"
            else:
                kind, why = "http", "意外状态码"
            tried.append((name, kind,
                          f"{tag}: HTTP {status}，{len(raw)} B，{took:.1f} s，{why}{saved}"))

        # ── 没取到：首行按各发实际的失败类型说，别一律往墙上引 ──
        sent = {n: c - (n in dead) for n, c in count.items()}       # 真发出去的发数
        spread = "、".join(f"{n} {c} 发" for n, c in sent.items() if c) or "一发都没发出去"
        kinds = {n: {k for ch, k, _ in tried if ch == n} for n in count}
        where = f"URL={url}" + (f"；{ctx}" if ctx else "")
        hints = []
        if any(k == "page" for _, k, _ in tried):
            blocked_too = any(k in ("block", "chal") for _, k, _ in tried)
            head = (f"MSCI IR 拿到了整页、里面却没有 nirtable 表格（{spread}，{where}）"
                    + ("—— 但同一轮另有几发被拦（403 / 429 / 挑战页，见下），改版与墙收紧两种都要查"
                       if blocked_too else "—— 多半是页面改版，不是被拦"))
            if blocked_too:
                hints.append("被拦的那几发见上：多半是 Bot Manager 又收紧了，见 _download() 上方「两条通道」。")
            hints.append(f"「整页」= 正文 ≥ {PAGE_MIN_BYTES} B 且渲染年龄在上限内：09-12 实测这张页面"
                         "去掉表格还有 32,774 B，拦截页 407 B。也可能是源站那一刻表格区块没渲染出来"
                         "（没见过）。打开上面点名的快照看表格现在长什么样，再改 _TABLE_RE / parse()。")
        else:
            if out_of_time:
                head = (f"MSCI IR 到了总时限 BUDGET={BUDGET} s 仍没取到页面（{spread}，{where}）"
                        + ("；其中 curl_cffi 导入失败、一发请求都没发出去" if "curl_cffi" in dead else ""))
            elif dead:
                head = (f"MSCI IR 没取到页面：{'、'.join(sorted(dead))} 导入失败、一发请求都没发出去，"
                        f"实际只有 {spread}（{where}）")
            else:
                head = f"MSCI IR {spread}全部没取到页面（{where}）"
            if "curl_cffi" in dead:
                hints.append("先修 curl_cffi（命令见上面那一行）。09-10 起单靠 urllib 进不来。")
            elif sent.get("curl_cffi"):
                ck = kinds["curl_cffi"]
                if ck & {"block", "chal"}:
                    hints.append("curl_cffi 发出去了、拿到了 HTTP 响应却被拦（403 / 429 / 挑战页，见上）："
                                 "多半是 Bot Manager 又收紧了，见 _download() 上方「两条通道」。")
                elif "http" in ck:
                    hints.append("curl_cffi 拿到的是 5xx 或意外状态码，不是被拦的样子：先看源站自己是不是"
                                 "出错（隔几小时再跑），再怀疑墙。")
                else:
                    hints.append("curl_cffi 每发都是网络层错误 / 超时，一个 HTTP 响应都没拿到：先排除本机"
                                 "网络 / DNS / 代理，再怀疑墙。")
        if sent.get("urllib") and not any(k == "page" for k in kinds.get("urllib", ())):
            hints.append("urllib 没取到是 09-10 起的已知常态（按本文件的头每发 45 s 读超时），"
                         "它失败本身不说明新问题。")
        if out_of_time:
            hints.append("总时限是一次 _download() 所有发（含护栏 A 换键）共用的，见 BUDGET 旁注。")
        raise RuntimeError(head + "：" + "".join(f"\n  {ln}" for _, _, ln in tried)
                           + "".join(f"\n  {h}" for h in hints))

    today = _date.today()
    url = _cache_key_url(today)
    raw, hdrs, _final = _once(url)
    age = _render_age(hdrs, time.time())

    # ── 护栏 A：这份 HTML 有多旧 ───────────────────────────────────────────
    # 重定向护栏和 nirtable 检查都已经在 _once 里判过，能走到这里的一定是「最终 URL = 请求
    # URL、含表」的 2xx。先后和改写前不一样了：原来护栏 A 在前、重定向在后，两个同时成立时
    # （跳回规范路径、拿到钉住的旧副本）报的是「缓存副本太旧」，真正的原因「跳回了规范路径」
    # 反而看不见；现在先报重定向，报错里带着渲染年龄，两个诊断都在。
    first = ""
    if age is not None and age > MAX_RENDER_AGE:
        stale = _snapshot(cache_dir, "stale", raw)
        first = (f"当日键 {url} 拿到的是 {age / 3600:.1f} 小时前渲染的副本（Last-Modified="
                 f"{hdrs.get('Last-Modified')!r}，已存 {stale}）")
        # 换一个久未使用的键再试一次。shift 取池长一半 ⇒ 该键上次被用是 150 天前，
        # 早已过 s-maxage 的 30 天，必定是冷 miss。换键重跑的是整条排班，和当日键共用 BUDGET。
        url = _cache_key_url(today, shift=len(_KEY_POOL) // 2)
        raw, hdrs, _final = _once(url, key="shift_", ctx=f"这是护栏 A 换键之后：{first}")
        age = _render_age(hdrs, time.time())
    if age is not None and age > MAX_RENDER_AGE:
        snap = _snapshot(cache_dir, "rejected", raw)
        raise RuntimeError(
            f"MSCI IR 拿到的是 {age / 3600:.1f} 小时前渲染的缓存副本"
            f"（上限 {MAX_RENDER_AGE / 3600:.0f} 小时，Last-Modified="
            f"{hdrs.get('Last-Modified')!r}，ETag={hdrs.get('ETag')!r}，"
            f"URL={url}，响应已存 {snap}；换键之前{first}）—— 换缓存键已经不起作用了，"
            "见文件头「CDN 缓存陷阱」。**别把阈值调大绕过它**：那等于同意在旧表上判断『这个月"
            "没发』。")
    if age is None:
        print("[msci] ⚠ 响应里没有 Last-Modified 也没有可解析的 ETag —— 无法判断这份"
              " HTML 有多旧，护栏 A 本轮失效（放行）。源站或 CDN 换了，请人工看一眼；"
              "兜底靠 monthly_run.audit_overdue_headline()。", file=sys.stderr)

    text = raw.decode("utf-8", errors="replace")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    path = os.path.join(cache_dir, f"msci_aum_{stamp}.html")
    with open(path, "wb") as f:
        f.write(raw)
    # latest 供人工/调试直接看，不用找日期
    with open(os.path.join(cache_dir, "msci_aum_latest.html"), "wb") as f:
        f.write(raw)
    return text, path


# ────────────────────────────── 解析 ──────────────────────────────

def _clean(cell):
    """去 <sup> 脚注、去标签、去 &nbsp;，只留可读文本。"""
    s = re.sub(r"<sup[^>]*>.*?</sup>", "", cell, flags=re.S | re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = _html.unescape(s).replace("\xa0", " ")
    return re.sub(r"\s+", " ", s).strip()


def _num(cell_text):
    """'$2,818.3' -> 2818.3。空/破折号返回 None（调用方决定是否算缺列）。"""
    s = cell_text.replace("$", "").replace(",", "").strip()
    if s in ("", "-", "–", "—", "N/A", "NA", "n/a"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def parse(html_text):
    """把页面 HTML 解析成 {"YYYY-MM": {"eop": float, "avg": float}}。

    只要有一行的月份能解析、数值却解析不出来，就抛异常——宁可整次失败，
    也不能把半张表写进序列（那会在图上留一个假的断崖）。

    反过来那半边（月份解析不出来、数值好好的）同样抛异常，见下面的「行数对账」。
    """
    m = _TABLE_RE.search(html_text)
    if not m:
        raise RuntimeError("没找到 nirtable 表格")

    out = {}
    dropped = []            # 长得像数据行、却没能落库的行；循环末尾一起抛
    for row in _ROW_RE.findall(m.group(1)):
        cells = [_clean(c) for c in _CELL_RE.findall(row)]
        if len(cells) < 3:
            # 列数不够的多半是表头 / 装饰行，安静丢掉。但**首格就是月份**的行不是
            # 装饰行——那是数据行被源改了结构（合并单元格、拆成两张表、少一列）。
            # 这一支专管**最新那一行**：它还没进 CSV，所以 update() 那道「已入库
            # 月份不许消失」的反向检查够不着它，而漏的恰恰又是最新月。
            if cells and _MONTH_RE.match(cells[0]):
                dropped.append(f"{cells[0]}（整行只有 {len(cells)} 格）")
            continue
        mm = _MONTH_RE.match(cells[0])
        if not mm:
            # 表头行 / 说明行本该在这里被安静丢掉。但**后两格都是金额**的行不是
            # 说明行，它就是一行数据，只是首格的月份写法我们没见过。记下来。
            if _num(cells[1]) is not None and _num(cells[2]) is not None:
                dropped.append(cells[0])
            continue
        mon = _MON.get(mm.group(1).lower())
        if mon is None:
            raise RuntimeError(f"月份缩写不认识：{cells[0]!r}")
        # 两位年：这张表最早 Dec'08，不会出现 19xx，直接补 20
        month = f"20{mm.group(2)}-{mon:02d}"

        eop, avg = _num(cells[1]), _num(cells[2])
        if eop is None or avg is None:
            raise RuntimeError(
                f"{month} 行数值解析失败：{cells[1]!r} / {cells[2]!r}")
        if month in out:
            raise RuntimeError(f"页面里 {month} 出现两次，源异常")
        out[month] = {"eop": eop, "avg": avg}

    # ── 行数对账：挡住「源改了月份写法 → 静默漏月」的那道闸 ──
    # 2026-08 的 `Jul’26 3`（裸脚注号）就是从这里漏过去的：当时没有这道检查，
    # 表现是 parse() 少产出一行、latest_month() 悄悄停在上个月、fetch 干净返回
    # NOCHANGE。没有 FAIL、没有断档（断档只看已入库月份之间的洞，管不到表尾少一行），
    # 所以连续失败计数与红点全都抓不到它。**下一次源换写法时，靠的是这一段，
    # 不是上面那条正则**——正则只认识已经见过的变体。
    if dropped:
        raise RuntimeError(
            f"表里有 {len(dropped)} 行长得像数据行却没能落库：{dropped[:5]!r}"
            "——「后两格都是金额、首格却不像月份」多半是月份写法又变了（脚注号、"
            "空格、撇号）；「整行格数不够」是表结构变了。宁可整次失败也不静默漏月；"
            "请对照 cache/msci_aum_latest.html 确认写法后改 _MONTH_RE / 解析逻辑")

    if len(out) < 100:
        raise RuntimeError(f"只解析出 {len(out)} 行，远少于预期（应 >200 行）")
    return out


# ────────────────────────────── 对外接口 ──────────────────────────────

def latest_month(cache_dir):
    """官方源当前最新月，"YYYY-MM"。抓不到 / 解析不出来一律抛异常，绝不返回 None
    来掩盖故障（返回 None 会让调度器以为「本月没数据」而静默跳过）。"""
    text, _ = _download(cache_dir)
    return max(parse(text))


def _read_series(path):
    """返回 (表头, {month: {col: 原始字符串}}, meta)。

    刻意按文本读、按文本写：仓库约定 series/*.csv 的格式不许改。读成 float 再
    整体写回，会把 '2340.7' 变成 '2340.7000000000003' 这类噪声，也会动小数位数。
    meta 记录换行风格和文件是否以换行结尾 —— **这个仓库的 msci.csv 是 CRLF**，
    追加时若写 '\\n' 就会混用行尾，git diff 上看着像整文件被改写。
    """
    with open(path, newline="", encoding="utf-8") as f:
        text = f.read()
    if not text.strip():
        raise RuntimeError(f"{path} 是空文件")
    nl = "\r\n" if "\r\n" in text else "\n"
    meta = {"newline": nl, "ends_with_nl": text.endswith(("\n", "\r"))}

    lines = text.splitlines()
    header = next(csv.reader([lines[0]]))
    rows = {}
    for ln in lines[1:]:
        if not ln.strip():
            continue
        vals = next(csv.reader([ln]))
        rows[vals[0]] = dict(zip(header, vals))
    return header, rows, meta


def _fmt(v):
    """按源的精度写：整张表都是一位小数。"""
    return f"{v:.1f}"


def check_restatements(series_dir, cache_dir, n=3, tol=0.05):
    """重算 series 里最后 n 个月并逐列比对，返回 [(month, col, csv值, 解析值, 差)]。

    tol 单位是 $bn（0.05 = 半个最小刻度），因为源只给一位小数。
    """
    path = os.path.join(series_dir, SERIES_FILE)
    header, rows, _ = _read_series(path)
    text, _ = _download(cache_dir)
    parsed = parse(text)

    diffs = []
    for month in sorted(rows)[-n:]:
        if month not in parsed:
            diffs.append((month, "*", "in csv", "MISSING on site", float("nan")))
            continue
        for col, key in VALUE_COLS.items():
            if col not in header:
                continue
            a = float(rows[month][col])
            b = parsed[month][key]
            if abs(a - b) > tol:
                diffs.append((month, col, a, b, b - a))
    return diffs


def update(series_dir, cache_dir):
    """把官方源上比 series/msci.csv 更新的月份追加进去，返回新增月份列表。

    幂等：已存在的月份一律跳过，且**只在文件末尾追加**（源表本身就是按月连续、
    升序落库的），已有行一个字节都不动。
    """
    path = os.path.join(series_dir, SERIES_FILE)
    header, rows, meta = _read_series(path)

    # ① 列口径检查：CSV 有而解析器给不出的列 → 直接抛，绝不写空值
    unknown = [c for c in header if c != MONTH_COL and c not in VALUE_COLS]
    if unknown:
        raise RuntimeError(
            f"{path} 有本解析器覆盖不了的列 {unknown}；"
            "拒绝写入（否则这些列会变成空值/NaN）")
    if header[0] != MONTH_COL:
        raise RuntimeError(f"{path} 首列应为 {MONTH_COL}，实际是 {header[0]!r}")

    text, snap = _download(cache_dir)
    parsed = parse(text)

    last = max(rows) if rows else ""
    new_months = sorted(m for m in parsed if m > last)

    # ② 两个哨兵，**处置刻意不一样**。判据不是「差得多不多」，而是「这件事是源的
    #    正常行为，还是我们把行解析丢了」：
    #
    #    · 已入库的月份**整行不见了** → 抛。这个源从不删行（Dec'08 起一路累加），
    #      所以它八成不是源少发了，而是我们没解析出来。它是 parse() 那道行数对账的
    #      补网，两道网的盲区不重叠：对账只看得见「后两格是金额、首格不像月份」的行，
    #      从**页面有什么**这一侧查；这里从**我们已知该有什么**的反侧查，连
    #      「金额格变成横杠」这种对账看不见的坏法也能兜住。
    #    · 已入库月份的**数值变了** → 只喊一声，不抛。重述是这个源说明书里就写着的
    #      正常行为（数值是 estimates，见文件头口径坑 5）。把它当致命错误，等于让
    #      一个 2019 年的格子改了 0.1 就把本月的新数据挡在门外 —— 拿「发不出正确的
    #      新数据」换「不漏看一次历史微调」，方向反了。何况漏看的代价也小：CSV 里
    #      留的是 MSCI 当时发布的口径，是旧，不是错。
    for month in sorted(rows)[-6:]:
        if month not in parsed:
            raise RuntimeError(
                f"{month} 在 series/msci.csv 里，官网表格却解析不出这一行——"
                "源不删历史行，所以多半是解析漏了（表结构变了？）。"
                "本次不写入，请对照 cache/msci_aum_latest.html 人工确认")
        for col, key in VALUE_COLS.items():
            a, b = float(rows[month][col]), parsed[month][key]
            if abs(a - b) > 0.05:
                print(f"[msci] WARN 官网重述 {month}.{col}: CSV={a} 官网={b} "
                      f"(diff {b - a:+.1f})；未自动覆盖，请人工确认",
                      file=sys.stderr)

    if not new_months:
        return []

    # ③ 断档检查：源表是连续月度，出现跳月说明解析漏了行，宁可失败
    prev = last
    for month in new_months:
        if prev and _next_month(prev) != month:
            raise RuntimeError(
                f"{prev} 与 {month} 之间断档，解析可能漏行；本次不写入")
        prev = month

    out = []
    for month in new_months:
        rec = parsed[month]
        row = [month] + [_fmt(rec[VALUE_COLS[c]]) for c in header[1:]]
        out.append(",".join(row))

    nl = meta["newline"]
    chunk = nl.join(out) + nl
    if not meta["ends_with_nl"]:      # 原文件最后一行没换行时先补上，别粘成一行
        chunk = nl + chunk
    # newline="" 让 Python 原样输出我们自己拼的行尾，不做转换
    with open(path, "a", encoding="utf-8", newline="") as f:
        f.write(chunk)

    print(f"[msci] +{len(new_months)} 月：{', '.join(new_months)}（源快照 {snap}）",
          file=sys.stderr)
    return new_months


def _next_month(m):
    y, mo = int(m[:4]), int(m[5:7])
    return f"{y + 1}-01" if mo == 12 else f"{y}-{mo + 1:02d}"


if __name__ == "__main__":
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    _cache = os.path.join(_root, "cache")
    print("latest on site:", latest_month(_cache))
    print("new months    :", update(os.path.join(_root, "series"), _cache))
