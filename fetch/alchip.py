# -*- coding: utf-8 -*-
r"""世芯-KY（Alchip，3661.TW）月度营收 —— 无人值守抓取模块。

对应 build/specs/alchip.py（页面由通用底座 build/single.py 生成），维护一个序列文件：

  series/alchip.csv   month, revenue_usd_mn, revenue_ntd_mn, fx_ntd_per_usd,
                      ytd_revenue_usd_mn, ytd_revenue_ntd_mn

五列都是**官方原值的无损搬运**（÷1000 换单位而已）：MOPS 的美元栏是 US$ 仟元、
两位小数 ⇒ 存 5 位小数；新台币栏是 NT$ 仟元、整数 ⇒ 存 3 位小数；换算汇率 4 位小数原样存。
所以核对表里的任何一格都可以拿去和 MOPS 页面逐字对，不需要「大约等于」。

后两列是官方同一张表的「本年累計」两栏（当年 1 月至本月的累计，1 月重置）。
**它们不上图**，存在的理由是让「新台币月值不可加总」这件事在 `build/specs/alchip.py`
的 import 期能**从 CSV 现算**（本仓规矩：图注里的数不许写死）：
逐年把 12 个月的 `revenue_ntd_mn` 相加，与当年 12 月的 `ytd_revenue_ntd_mn` 一比就是
那个几十个基点的缺口；同一检验在美元列上是 0。

────────────────────────────────────────────────────────────────────────
数据源
────────────────────────────────────────────────────────────────────────
1) 主源：MOPS 公开资讯观测站「采用 IFRSs 后之月营业收入资讯」内部接口
   POST https://mopsov.twse.com.tw/mops/web/ajax_t05st10_ifrs
        co_id=3661&year=<民國年>&month=<MM>&TYPEK=all&queryName=co_id&…（见 _FORM）

   一次一个月，返回一张小表：

       項目        新台幣        功能性貨幣(美金)
       本月        7,433,152     230,742.90
       去年同期    2,637,889      89,990.42
       本年累計   19,173,152     604,831.29
       去年累計   22,236,743     706,040.43
       本月換算匯率：   ─          32.2140
       本年累計換算匯率：─         31.7000
       註1: 本月新台幣營業收入淨額＝本月功能性貨幣營業收入淨額×本月換算匯率

   **「功能性貨幣(美金)」这一栏全网只有这里有。** TWSE OpenAPI、TPEx OpenAPI、
   MOPS 的全市场彙總表（t21sc03）、公司官网、法说会简报，一律只给新台币。
   而世芯的功能货币是美元、新台币月营收是**逐月折算值** —— 见下面「口径坑 1」，
   这就是本页主序列必须用美元栏、不能用新台币栏的全部理由。

   ⚠ 域名必须是 **mopsov**.twse.com.tw。`mops.twse.com.tw/mops/web/ajax_t05st10_ifrs`
     会 302 到 /mops/error/error.html，跟随后 **HTTP 200 + 65 字节**；
     `mops.twse.com.tw/nas/t21/...` 直接 404。按状态码判成功在这里完全无效。

2) 独立第三源（只读不写，用于交叉核对，不进 series）
   a. TWSE OpenAPI  https://openapi.twse.com.tw/v1/opendata/t187ap05_L
      「上市公司每月营业收入汇总表」，全市场当期一份 JSON，单位新台币仟元。
      **3661 在这张表里**（实测 2026-07 那期 1,071 家，含 3661 / 6415 / 3443 / 2330）。
      只有最新一期、没有历史，所以只用来验「最新月是哪个月 + 新台币金额对不对」。
      （fetch/guc.py 的 docstring 说 KY 公司不在 _L、要走 TPEx 的 _O —— 那句话对
      **上柜**的 KY 公司成立，对**上市**的世芯不成立。这里实测过，别照抄那句。）
   b. MOPS 全市场月报静态页
      https://mopsov.twse.com.tw/nas/t21/sii/t21sc03_<民國年>_<月>_1.html
      有历史，可逐月对新台币值。**后缀 `_1` = 外國公司（93 家），`_0` = 國內公司
      （983 家）**；世芯是 KY（开曼注册的外国发行人），只在 `_1` 里，2013-01 起每月都在。
      文件是 **big5** 编码（不是 utf-8，也没有 BOM），`<meta charset=big5>`。
   c. 审计年报口径：MOPS 合并综合损益表
      POST https://mopsov.twse.com.tw/mops/web/ajax_t164sb04 (co_id=3661, season=04)
      「營業收入合計」，单位新台币仟元。用于年度对账，见下面的实测表。

3) 公告日：**没有。这是一等状态，不要给它设兜底。**
   · 公司官网 alchip.com 新闻中心（/en/Newsroom?cate=Press_Releases）只有季报与公司
     新闻，**从不发月营收新闻稿**；官网也没有月营收页面。
   · TWSE OpenAPI t187ap04_L（上市公司每日重大讯息）里 3661 **零条**。
   · MOPS 的 t05st10_ifrs 回应体里没有任何申报时间戳。
   · t21sc03 静态页的 HTTP `Last-Modified` **不是发布日**：实测 2013-01 那张的
     Last-Modified 是 2026-08-12、2013-02 那张是 2026-08-01 —— MOPS 会整批重生成
     历史文件，这个头只记录重生成时刻。
   ⇒ 本模块**不写 series/source_dates.csv**，页面抬头就没有「官方发布于 X」那一行。
     这比编一个日期出来诚实。**不要**拿 TWSE OpenAPI 的「出表日期」顶上 ——
     那是证交所生成全市场汇总档的日期，不是公司申报日。

────────────────────────────────────────────────────────────────────────
发布节奏
────────────────────────────────────────────────────────────────────────
· 台湾《证券交易法》第 36 条要求上市公司于**次月 10 日前**公告并申报上月营运情形；
  第一上市外国发行人（KY）同规。世芯没有自订的更早惯例，也不预告日期
  （对照组：创意 GUC 在 IR 财务日历里逐条预告「次月 5 日 14:00」）。
· 实测锚点（2026-08-13 当天）：2026-07 的数在 MOPS t05st10_ifrs 里已经有，
  TWSE OpenAPI 那期的「出表日期」是 1150812 = 2026-08-12。2026-08 查回
  「外國發行人免申報本項資訊」。
  → roster LAG 取 (10, 10)，与 tsm 同源（法定上限），不是公司承诺。
    季末月与常规月同一个数：月营收不随季报走，3/6/9/12 没有额外延迟。
· 查未来月份 / 未申报月份时接口返回的是「外國發行人免申報本項資訊」这句话，
  **HTTP 200，2,674 字节**，不是 404。所以「有没有新月份」只能靠这句话判，
  不能靠状态码，也不能靠长度单独判（正常回应约 5,300 字节，空白回应 3,004 字节，
  三者都是 200）。

────────────────────────────────────────────────────────────────────────
口径坑（踩过的，别再踩）
────────────────────────────────────────────────────────────────────────
1. **新台币月营收不可加总；美元才可以。** 世芯的功能货币是美元，MOPS 那张表的
   新台币栏是「当月美元营收 × 当月换算汇率」逐月折算出来的。逐年实测
   （12 个月相加 vs 官方 12 月「本年累计」）：

       年    美元相加 vs 官方累计        新台币相加 vs 官方累计
       2016  +0.0000 ppm                −0.1617%
       2017  +0.0000 ppm                −0.2956%
       2022  +0.0000 ppm                +0.7194%   ← 最大
       2023  +0.0000 ppm                +0.2136%
       2024  +0.0000 ppm                +0.1204%
       2025  +0.0000 ppm                +0.3779%
       2026(前 7 月) +0.0165 ppm         +0.4817%

   美元列 2014-01 起 151 个月**全年残差不超过 ±0.02 US$仟元**（= ±$20，
   纯粹是累计栏两位小数的舍入），新台币列则年年差几十个基点，因为各月用各月的汇率。
   ⇒ 主序列 = 美元列。新台币列留在页面上只为了跟 TWSE/媒体报的那个数对账。

2. **序列起点 2014-01，不是「最早可得」。** 接口本身能查到更早：
   · `ajax_t05st10_ifrs` 覆盖民國 102 年（2013）起；民國 101 及更早**返回一个空
     `div01`（3,004 字节、HTTP 200），不报错**，要靠「没有『合併營業收入淨額』」判。
   · 旧接口 `ajax_t05st10`（非 IFRS）覆盖到 2011-07。
   不取 2013 及更早的三条理由，逐条实测过：
   ① **2013 及以前美元栏被舍入到整数仟元**（4,201.00 / 9,779.00 …），
      于是加总不再等于官方累计：2013 年 12 个月相加 87,035.04 vs 官方累计
      87,006.30，差 **+28.74 US$仟元 = +330 ppm**；2014 年同一检验是 **−0.065 ppm**，
      相差 5,000 倍。本页最核心的那句「美元列可加总」在 2013 段落上不成立。
   ② 换算汇率栏 2013 及以前只有 2–3 位小数（29.07 / 29.5 / 29.76），2014 起是
      4 位（30.1138）。恒等式核验的分辨率跟着差一个量级。
   ③ 2013-01 是 ROC GAAP → Taiwan-IFRSs 的准则断点；而 IFRS 之前那一段**有真重述**：
      2011-12 当时申报 NT$336,689 / US$11,128，一年后在 2012-12 那期里被列成
      NT$328,443 / US$10,872（−2.4%）。2012-01 起的「去年同期」与上一年「本月」
      逐月相等（169 个月零分歧），2011 那 6 个月是唯一的例外。
   ⇒ 起点定 2014-01。序列 2014-01…2026-07 共 151 个月，逐月连续无缺口。
     这个断点落在序列第 0 格，所以 spec 里**不登记 breaks**（底座对第 0 格断点不画线），
     改在页尾 notes 里写清楚。

3. **恒等式是护栏，不是装饰**：官方自己在页脚写「註1: 本月新台幣營業收入淨額＝
   本月功能性貨幣營業收入淨額×本月換算匯率」。本模块每落一个月都验一次
   |NT$ − US$ × 汇率| / NT$ ≤ 1 个基点。151 个月实测最大偏差 **0.2162 bp（2017-03）**，
   机理是 4 位小数的汇率舍入（0.5e-4 / 30 ≈ 0.17 bp），所以 1 bp 是有余量的硬界。
   这条同时把「解析串位」「读错列」「MOPS 改版把两栏换位置」一次性拦掉。

4. **HTTP 200 ≠ 成功，本家有三种 200 的假成功**：
   ① 走错域名 `mops.twse.com.tw` → 302 → error.html，200 + 65 字节；
   ② 查未申报月份 → 200 + 2,674 字节「外國發行人免申報本項資訊」；
   ③ 查 IFRS 接口覆盖范围之外的年份 → 200 + 3,004 字节的**空 div**，
      连一句错误说明都没有。
   → `_fetch_month()` 逐项校验：长度下限、必须出现「合併營業收入淨額」与
     「功能性貨幣」、公司名必须含「世芯-KY」、**回应里的「民國YYY年MM月」必须与请求
     的年月逐字相等**（防止接口把别的月份的表回给你）。任一条不过就抛异常，
     只有明确认出「免申報」那句话才判「这个月还没有」。

5. **重述体检：已入库值与官方不一致时抛异常，不悄悄改写、不追加。**
   同 fetch/tsm.py 口径坑 6 与 fetch/guc.py 的 drift 检查。这里做三层，都不额外花请求：
   ① 每轮重抓**最近 3 个已入库月份**，逐字段比对；
   ② 最新一期回应自带的「去年同期」必须等于已入库的 M−12（新台币与美元两栏都比）；
   ③ 最新一期回应自带的「本年累计」美元值必须等于已入库的本年各月美元之和
      （容差 0.05 US$仟元 = $50，留给累计栏的两位小数舍入）。
   要全历史体检就跑 `python3 fetch/alchip.py --audit`，它逐月重抓 151 个月再比对。

6. **年度口径有三个数，不要混着用**（都实测过，单位 NT$ 仟元）：
       年    12 个月相加   官方 12 月累计   审计年报「營業收入合計」
       2019   4,318,777     4,329,103      4,331,956
       2022  13,804,374    13,705,778     13,725,204
       2023  30,544,913    30,479,805     30,481,576
       2024  52,039,348    51,976,782     51,968,570
       2025  31,041,305    30,924,428     30,926,092
   · 「官方 12 月累计」≡ 累计美元 × 累计换算汇率（实测逐年偏差 ≤ 0.5 NT$仟元）；
   · 审计年报与官方累计差 −0.14% ~ +0.02%（2025 是 −0.0054%），因为财报按实际交易
     汇率逐笔换算，月报按月度/年度平均汇率换算。**这不是错，是两个口径。**
   · 审计年报逐年互查过：每一年的「去年度」比较列与上一年自己的数逐字相等
     （2019–2025 七年零分歧）⇒ 年度层面无重述。

7. **世芯不给指引，本页也不做指引桥。** 公司只在季度法说会给定性展望，
   不公布数字财测；MOPS「财测」相关表 3661 零条。同 GUC，这里是对象不存在，
   不是数据缺失。

8. **MOPS 有节流，症状是 HTTP 307 而不是 429。** 一个月一次请求的正常节奏碰不到它
   （`update()` 一轮只发 4–6 次），但 `--audit` 那种连打 150 次的用法会在几十次之后
   开始连续 307：urllib 对 POST **不跟随 307**，直接抛 `HTTPError 307`。
   实测 2 秒退避无效，所以 `_post()` 对 307/429/503 走 5→15→45→135 秒的指数退避，
   `audit()` 本身也把间隔放到 1.5 秒。**别把 307 当成「接口挂了」去改域名** ——
   歇一会儿就好了。

9. **本模块不做美元↔新台币的任何自算换算。** 三列全部来自官方同一张表，
   汇率也是官方给的那个「本月換算匯率」，不是外部牌价（H.10 / FRED / 台银）。
   拿外部月均汇率去折世芯的营收会得到一个**对不上官方任何一个数**的第四个口径。
"""

from __future__ import annotations

import csv
import datetime as _dt
import html as _html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

MOPS_ORIGIN = 'https://mopsov.twse.com.tw'
MOPS_URL = MOPS_ORIGIN + '/mops/web/ajax_t05st10_ifrs'
TWSE_API = 'https://openapi.twse.com.tw/v1/opendata/t187ap05_L'
CO_ID = '3661'
CO_NAME = '世芯-KY'

START_MONTH = '2014-01'          # 见 docstring 口径坑 2
COLUMNS = ['month', 'revenue_usd_mn', 'revenue_ntd_mn', 'fx_ntd_per_usd',
           'ytd_revenue_usd_mn', 'ytd_revenue_ntd_mn']

# 恒等式容差（基点）。151 个月实测最大 0.2162 bp，机理是 4 位小数汇率的舍入。见口径坑 3。
IDENTITY_TOL_BP = 1.0
# 「本年累计美元 = 本年各月美元之和」的容差，单位 US$ 仟元。累计栏只有两位小数。
YTD_TOL_KUSD = 0.05
# 每轮重抓多少个已入库月份做重述体检（口径坑 5 ①）
DRIFT_RECHECK = 3

_UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
       '(KHTML, like Gecko) Chrome/126.0 Safari/537.36')

# 正常回应约 5,300 字节；「免申報」2,674；空 div 3,004；error.html 65。
# 长度只做第一道粗筛，判别力全在下面的标记字符串上（口径坑 4）。
_MIN_BYTES = 1_500
_MARK_TABLE = '合併營業收入淨額'
_MARK_CCY = '功能性貨幣'
_MARK_NONE = '免申報本項資訊'

_FORM = {
    'encodeURIComponent': '1', 'step': '1', 'firstin': '1', 'off': '1',
    'keyword4': '', 'code1': '', 'TYPEK2': '', 'checkbtn': '',
    'queryName': 'co_id', 'inpuType': 'co_id', 'TYPEK': 'all', 'isnew': 'false',
}


class AlchipFetchError(RuntimeError):
    """本模块的故障出口。抓不到 / 认不出来 / 对不上一律抛它，不返回 None 掩盖故障。"""


# ── 月份小工具（全站不许写 dateutil 依赖，这里手算）────────────────────────
def _split(month):
    y, m = month.split('-')
    return int(y), int(m)


def _shift(month, k):
    y, m = _split(month)
    n = y * 12 + (m - 1) + k
    return f'{n // 12}-{n % 12 + 1:02d}'


def _roc(month):
    y, m = _split(month)
    return y - 1911, m


# ── HTTP ────────────────────────────────────────────────────────────────
def _post(url, form, *, tries=5, min_bytes=0):
    """POST 一次查询。**MOPS 有节流**：连续快速请求几十次之后会开始回 HTTP 307
    （urllib 对 POST 不跟随 307，直接抛 HTTPError），此时必须退避而不是当故障。
    见 docstring 口径坑 8。"""
    body = urllib.parse.urlencode(form).encode()
    last = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(
                url, data=body,
                headers={'User-Agent': _UA,
                         'Content-Type': 'application/x-www-form-urlencoded'})
            resp = urllib.request.urlopen(req, timeout=120)
            blob = resp.read()
            # 走错域名时 MOPS 会 302 到 /mops/error/error.html 再回 200，
            # 所以校验的是**落地 URL**，不是状态码（口径坑 4 ①）。
            if not resp.geturl().startswith(MOPS_ORIGIN + '/mops/web/'):
                raise AlchipFetchError(
                    f'请求 {url} 落到了 {resp.geturl()} —— 期望的是 '
                    f'{MOPS_ORIGIN}/mops/web/…（走错域名会 302 到 error.html 再回 200，'
                    f'按状态码判成功在这里无效）')
            if len(blob) < min_bytes:
                raise AlchipFetchError(
                    f'{url} 只回了 {len(blob)} 字节（<{min_bytes}），疑似 WAF / 错误页')
            return blob.decode('utf-8', 'replace')
        except AlchipFetchError:
            raise
        except urllib.error.HTTPError as exc:
            last = exc
            # 307/429/503 = 节流，不是坏请求。退避要拉长（5/15/45/135s），
            # 短退避在 MOPS 上没用 —— 实测连打 150 次之后 2 秒退避照样连续 307。
            time.sleep((5 * 3 ** attempt) if exc.code in (307, 429, 503)
                       else 2 * (attempt + 1))
        except Exception as exc:                                   # noqa: BLE001
            last = exc
            time.sleep(2 * (attempt + 1))
    raise AlchipFetchError(f'{url} 取不到：{last!r}')


def _get(url, *, tries=3, min_bytes=0):
    last = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': _UA})
            blob = urllib.request.urlopen(req, timeout=120).read()
            if len(blob) < min_bytes:
                raise AlchipFetchError(f'{url} 只回了 {len(blob)} 字节（<{min_bytes}）')
            return blob
        except AlchipFetchError:
            raise
        except Exception as exc:                                   # noqa: BLE001
            last = exc
            time.sleep(2 * (attempt + 1))
    raise AlchipFetchError(f'{url} 取不到：{last!r}')


# ── 解析 ────────────────────────────────────────────────────────────────
_NUM = re.compile(r'-?\d[\d,]*(?:\.\d+)?$')


def _flat(text):
    """把 ajax 片段压成 `|` 分隔的纯文本（标签一律当分隔符，避免依赖具体版式）。"""
    i = text.find('<div id="div01"')
    body = text[i:] if i >= 0 else text
    txt = _html.unescape(re.sub(r'<[^>]+>', '|', body))
    return re.sub(r'[ \t ]+', ' ', re.sub(r'\|+', '|', txt))


def _cells_after(parts, label, n):
    """取 `label` 之后紧邻的 n 个数值格（遇到非数值格立刻停）。'─' 记作 None。"""
    for i, p in enumerate(parts):
        if p == label:
            out = []
            for q in parts[i + 1:]:
                q = q.strip()
                if q == '─':
                    out.append(None)
                elif _NUM.match(q):
                    out.append(float(q.replace(',', '')))
                else:
                    break
                if len(out) >= n:
                    break
            return out
    return []


def _parse_month(text, month):
    """把一个月的 ajax 回应解析成 dict；该月未申报返回 None；认不出来抛异常。

    单位：新台币仟元 / 美金仟元 / 新台币每美元。
    """
    flat = _flat(text)
    if _MARK_NONE in flat:
        return None
    if _MARK_TABLE not in flat or _MARK_CCY not in flat:
        raise AlchipFetchError(
            f'{month} 的回应里既没有「{_MARK_TABLE}」也没有「{_MARK_NONE}」'
            f'（{len(text)} 字节）—— MOPS 改版或接口异常，本次不写入')
    if CO_NAME not in flat:
        raise AlchipFetchError(f'{month} 的回应里没有公司名「{CO_NAME}」—— 查到别家去了？')

    # 回应自报的年月必须与请求逐字相等（口径坑 4）
    ry, rm = _roc(month)
    if f'民國{ry}年{rm:02d}月' not in flat.replace(' ', ''):
        got = re.search(r'民國\s*\d+\s*年\s*\d+\s*月', flat.replace(' ', ''))
        raise AlchipFetchError(
            f'{month} 请求的是 民國{ry}年{rm:02d}月，回应写的是 {got.group(0) if got else "（没写）"}')

    parts = [p.strip() for p in flat.split('|')]
    cur = _cells_after(parts, '本月', 2)
    py = _cells_after(parts, '去年同期', 2)
    ytd = _cells_after(parts, '本年累計', 2)
    fx = _cells_after(parts, '本月換算匯率：', 2)
    if len(cur) < 2 or len(ytd) < 2 or len(fx) < 2 or fx[1] is None:
        raise AlchipFetchError(f'{month} 的表格解析不全：本月={cur} 本年累計={ytd} 匯率={fx}')

    rec = {'month': month, 'ntd_k': cur[0], 'usd_k': cur[1], 'fx': fx[1],
           'py_ntd_k': py[0] if len(py) > 1 else None,
           'py_usd_k': py[1] if len(py) > 1 else None,
           'ytd_ntd_k': ytd[0], 'ytd_usd_k': ytd[1]}
    for k in ('ntd_k', 'usd_k', 'fx'):
        if rec[k] is None or rec[k] <= 0:
            raise AlchipFetchError(f'{month} 的 {k} 解析成 {rec[k]}，不是正数')

    # 官方页脚的恒等式：本月新台幣 ＝ 本月美金 × 本月換算匯率（口径坑 3）
    dev_bp = abs(rec['ntd_k'] - rec['usd_k'] * rec['fx']) / rec['ntd_k'] * 1e4
    if dev_bp > IDENTITY_TOL_BP:
        raise AlchipFetchError(
            f'{month} 恒等式不成立：NT${rec["ntd_k"]:,.0f}k vs '
            f'US${rec["usd_k"]:,.2f}k × {rec["fx"]:.4f} = {rec["usd_k"] * rec["fx"]:,.1f}k，'
            f'偏差 {dev_bp:.3f} bp > {IDENTITY_TOL_BP} bp')
    rec['dev_bp'] = dev_bp
    return rec


def _fetch_month(month):
    """取一个月。返回 dict（有数）或 None（该月未申报）。"""
    ry, rm = _roc(month)
    form = dict(_FORM, co_id=CO_ID, year=str(ry), month=f'{rm:02d}')
    return _parse_month(_post(MOPS_URL, form, min_bytes=_MIN_BYTES), month)


# ── 落库格式（无损：官方原值 ÷ 1000）────────────────────────────────────
def _row(rec):
    return [rec['month'],
            f'{rec["usd_k"] / 1000:.5f}',      # US$ 仟元两位小数 ⇒ 百万 5 位小数，无损
            f'{rec["ntd_k"] / 1000:.3f}',      # NT$ 仟元整数     ⇒ 百万 3 位小数，无损
            f'{rec["fx"]:.4f}',
            f'{rec["ytd_usd_k"] / 1000:.5f}',
            f'{rec["ytd_ntd_k"] / 1000:.3f}']


# ── 第三源交叉核对 ──────────────────────────────────────────────────────
def _twse_latest():
    """TWSE OpenAPI 里 3661 的 (月份, 当月营收 NT$仟元, 本年累计 NT$仟元)。失败不阻断。"""
    try:
        recs = json.loads(_get(TWSE_API, tries=2, min_bytes=10_000).decode('utf-8'))
        for r in recs:
            if r.get('公司代號') == CO_ID:
                roc = str(r['資料年月'])                  # 11507 = 2026-07
                month = f'{int(roc[:-2]) + 1911}-{int(roc[-2:]):02d}'
                return (month, float(r['營業收入-當月營收']),
                        float(r['累計營業收入-當月累計營收']))
    except Exception as exc:                                       # noqa: BLE001
        print(f'[alchip][warn] TWSE OpenAPI 交叉核对跳过：{exc!r}')
    return None, None, None


# ── series 读写 ─────────────────────────────────────────────────────────
def _read(csv_path):
    with open(csv_path, newline='', encoding='utf-8') as fh:
        rows = list(csv.reader(fh))
    if not rows:
        raise AlchipFetchError(f'{csv_path} 是空文件')
    header, body = rows[0], [r for r in rows[1:] if r and r[0].strip()]
    if header != COLUMNS:
        raise AlchipFetchError(f'{csv_path} 列不对：{header} != {COLUMNS}')
    months = [r[0] for r in body]
    if len(set(months)) != len(months):
        raise AlchipFetchError(f'{csv_path} 有重复月份')
    for a, b in zip(months, months[1:]):
        if _shift(a, 1) != b:
            raise AlchipFetchError(f'{csv_path} 月份不连续：{a} 之后是 {b}')
    return header, body


def _drift(stored_row, rec):
    want = _row(rec)
    return None if stored_row == want else (rec['month'], stored_row, want)


# ── 对外的两个函数 ──────────────────────────────────────────────────────
def latest_month(cache_dir):                                       # noqa: ARG001
    """官方源当前最新月 'YYYY-MM'。全抓不到一律抛 AlchipFetchError。

    从本月往回找（月营收次月才申报，所以本月几乎必然是「免申報」，正常要回退 1 格）。
    """
    today = _dt.date.today()
    cur = f'{today.year}-{today.month:02d}'
    for k in range(0, -7, -1):
        m = _shift(cur, k)
        if m < START_MONTH:
            break
        if _fetch_month(m) is not None:
            return m
    raise AlchipFetchError(f'MOPS 里 {CO_ID} 最近 7 个月都没有月营收（接口改版？）')


def update(series_dir, cache_dir):                                 # noqa: ARG001
    """把新月份追加进 series/alchip.csv，返回新增月份列表（升序）。

    幂等：没有新月份时**一个字节都不写**（既有行原样保留，连重排都不做）。
    已有值永不覆盖 —— 与官方值不一致时抛异常（口径坑 5），由人判断是重述还是解析出错。
    """
    csv_path = os.path.join(series_dir, 'alchip.csv')
    header, body = _read(csv_path)
    have = {r[0]: r for r in body}
    if not have:
        raise AlchipFetchError('series/alchip.csv 没有任何数据行，本模块只做增量，不做冷启动')

    # ── 1) 往前走，抓到「免申報」为止 ─────────────────────────────────
    fresh = {}
    cursor = _shift(max(have), 1)
    for _ in range(24):                       # 上限 24 个月，防接口异常时无限循环
        rec = _fetch_month(cursor)
        if rec is None:
            break
        fresh[cursor] = rec
        cursor = _shift(cursor, 1)
    else:
        raise AlchipFetchError(f'连抓 24 个月都有数（抓到 {cursor}），像是接口在回同一张表')

    # ── 2) 重述体检 ①：重抓最近 N 个已入库月份，逐字段比对 ───────────
    recheck = sorted(have)[-DRIFT_RECHECK:]
    drift = []
    for m in recheck:
        rec = _fetch_month(m)
        if rec is None:
            raise AlchipFetchError(f'{m} 已入库，但官方现在回「{_MARK_NONE}」—— 数据被撤回？')
        d = _drift(have[m], rec)
        if d:
            drift.append(d)

    newest_rec = fresh[max(fresh)] if fresh else _fetch_month(max(have))
    if newest_rec is None:
        raise AlchipFetchError(f'{max(have)} 重抓不到，本次不写入')

    # ── 3) 重述体检 ②：最新一期自带的「去年同期」vs 已入库的 M−12 ────
    prev = _shift(newest_rec['month'], -12)
    if prev in have and newest_rec['py_ntd_k'] is not None:
        want = [f'{newest_rec["py_usd_k"] / 1000:.5f}', f'{newest_rec["py_ntd_k"] / 1000:.3f}']
        got = have[prev][1:3]
        if got != want:
            drift.append((f'{prev}（{newest_rec["month"]} 的「去年同期」栏）', got, want))

    # ── 4) 重述体检 ③：最新一期自带的「本年累计（美元）」vs 已入库本年各月之和 ──
    year = newest_rec['month'][:4]
    known = {m: r for m, r in have.items() if m.startswith(year)}
    known.update({m: _row(r) for m, r in fresh.items() if m.startswith(year)})
    if known and min(known) == f'{year}-01':
        s = sum(float(r[1]) for r in known.values()) * 1000.0
        gap = s - newest_rec['ytd_usd_k']
        if abs(gap) > YTD_TOL_KUSD:
            drift.append((f'{year} 全年美元累计',
                          [f'{s:,.2f} US$k（各月相加）'],
                          [f'{newest_rec["ytd_usd_k"]:,.2f} US$k（官方累计）'
                           f'，差 {gap:+,.2f}']))

    if drift:
        raise AlchipFetchError(
            'MOPS 官方值与已入库值不一致（疑似重述或解析变形），本次不写入：\n  '
            + '\n  '.join(f'{m}: 库内 {old} vs 官方 {new}' for m, old, new in drift[:6]))

    # ── 5) 写入 ───────────────────────────────────────────────────────
    added = []
    for m in sorted(fresh):
        if m < START_MONTH:
            continue
        body.append(_row(fresh[m]))
        added.append(m)
    if added:
        body.sort(key=lambda r: r[0])
        with open(csv_path, 'w', newline='', encoding='utf-8') as fh:
            w = csv.writer(fh)
            w.writerow(header)
            w.writerows(body)

    # ── 6) 第三源交叉核对（TWSE OpenAPI，只告警不阻断：它可能比 MOPS 晚一天）──
    tw_month, tw_ntd, tw_ytd = _twse_latest()
    if tw_month:
        newest = newest_rec['month']
        if tw_month != newest:
            print(f'[alchip][warn] TWSE OpenAPI 最新月 {tw_month} 与 MOPS 最新月 {newest} 不一致')
        else:
            if abs(tw_ntd - newest_rec['ntd_k']) > 0.5:
                print(f'[alchip][warn] {newest} 新台币当月营收 MOPS {newest_rec["ntd_k"]:,.0f}k '
                      f'vs TWSE {tw_ntd:,.0f}k 不符')
            if tw_ytd is not None and abs(tw_ytd - newest_rec['ytd_ntd_k']) > 0.5:
                print(f'[alchip][warn] {newest} 新台币本年累计 MOPS {newest_rec["ytd_ntd_k"]:,.0f}k '
                      f'vs TWSE {tw_ytd:,.0f}k 不符')
        print(f'[alchip] 交叉核对 TWSE OpenAPI t187ap05_L：{tw_month} 当月 {tw_ntd:,.0f} NT$k、'
              f'累计 {tw_ytd:,.0f} NT$k')

    return added


# ── 手动全历史体检（不进 monthly_run）──────────────────────────────────
def audit(series_dir=None):
    """逐月重抓全历史与 series/alchip.csv 比对。差一格就打印，最后给汇总。

        python3 fetch/alchip.py --audit
    """
    series_dir = series_dir or os.path.join(ROOT, 'series')
    _, body = _read(os.path.join(series_dir, 'alchip.csv'))
    bad = 0
    worst = (0.0, None)
    for stored in body:
        rec = _fetch_month(stored[0])
        if rec is None:
            print(f'  {stored[0]}: 官方现在回「{_MARK_NONE}」'); bad += 1; continue
        if rec['dev_bp'] > worst[0]:
            worst = (rec['dev_bp'], stored[0])
        d = _drift(stored, rec)
        if d:
            print(f'  {d[0]}: 库内 {d[1]} vs 官方 {d[2]}'); bad += 1
        time.sleep(1.5)      # MOPS 节流，见口径坑 8
    print(f'体检完毕：{len(body)} 个月，{bad} 处不一致；'
          f'恒等式最大偏差 {worst[0]:.4f} bp（{worst[1]}），阈值 {IDENTITY_TOL_BP} bp')
    return bad


if __name__ == '__main__':
    if '--audit' in sys.argv:
        raise SystemExit(1 if audit() else 0)
    print('latest_month =', latest_month(None))
    print('added =', update(os.path.join(ROOT, 'series'), os.path.join(ROOT, 'cache')))
