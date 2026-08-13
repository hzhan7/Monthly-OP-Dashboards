# -*- coding: utf-8 -*-
r"""日月光投控（ASEH，3711.TW / NYSE: ASX）月度营收 —— 无人值守抓取模块。

对应 build/specs/ase.py（页面由通用底座 build/single.py 生成），维护一个序列文件：

  series/ase.csv    month, revenue_ntd_mn, revenue_atm_ntd_mn, revenue_nonatm_ntd_mn

⚠️ **本页 slug 是 `ase`，不是 `asx`。** `asx` 在本仓已经是 ASX Limited（澳交所）
   的 ticker（series/asx.csv、fetch/asx.py、build/specs/asx.py、asx/ 目录、
   source_dates.csv 里上百行）。日月光的 NYSE ADR 代码恰好也叫 ASX，
   两边写串会同时污染两张页，而且是静默污染 —— 图照出、数全错。

────────────────────────────────────────────────────────────────────────
数据源
────────────────────────────────────────────────────────────────────────
1) 落地页（发现用，**不当数值源**）
   https://ir.aseglobal.com/html/ir_revenues.php?year=YYYY
   一年一张表：Month / Net Revenues (NT$ million) / Press Release，
   最后一列的 <a href> 指向该月英文新闻稿 PDF
   （https://media-aseholdco.todayir.com/<14~16 位时间戳><随机串>_en.pdf）。
   年份下拉框里只有 2018~本年 —— 2017 及更早在 `<!-- -->` 注释里，取不到，
   这正好与 ASEH 控股 2018-04-30 成立、2018-05 起才有合并月报吻合。

   ⚠️ **落地页表格里的金额有错，一律以 PDF 正文为准**（口径坑 2）。

2) 数值源：月度新闻稿 PDF（英文版）
   正文两张 NT$ 表：`CONSOLIDATED NET REVENUES (UNAUDITED)` 与
   `ATM NET REVENUES (UNAUDITED)`（2018-05~2018-12 叫 `IC-ATM NET REVENUES`）。
   每张表三列：当月 / 上月 / 去年同月，所以**一份 PDF 同时给出三个月的读数** ——
   重述体检就靠这个（口径坑 6）。
   季末月（3/6/9/12）的 PDF 另有 Q 表、12 月另有 FY 表，本模块只取月列。

3) 交叉校验源（只读不写，失败只告警不阻断）
   TWSE OpenAPI https://openapi.twse.com.tw/v1/opendata/t187ap05_L
   全市场当期一份 JSON，单位新台币千元。3711 是**本国**上市公司，在 _L 里；
   外国发行人（世芯-KY 3661 那类）走 TPEx 的 _O 端点，不在这张表。
   只有最新一期、没有历史，所以只用来验「最新月是哪个月 + 合并金额对不对」。

4) 全历史第三源（本模块不调，落库时人工对过一次，见文件末「对账实测」）
   https://mopsov.twse.com.tw/nas/t21/sii/t21sc03_<民国年>_<月>_0.html
   MOPS 全市场当月营收表，big5 编码，一月一张 400KB HTML，可回溯到 2018。
   **单张耗时 20~60 秒**，99 张要跑近一小时，不适合放进每月例行；
   例行只跑上面第 3 条。

────────────────────────────────────────────────────────────────────────
发布节奏（99 期实测，取自 PDF 正文电头日期，不是 URL 时间戳）
────────────────────────────────────────────────────────────────────────
· 台湾《证券交易法》要求次月 10 日前公告。ASEH 99 期的「月末后第几天」分布
  （2026-08-13 重测）：
    第 8 天 9 期 / 第 9 天 42 期 / 第 10 天 34 期 / 第 11 天 10 期 /
    第 12 天 1 期 / 第 13 天 1 期 / 第 15 天 1 期 / 第 40 天 1 期
  累计覆盖：≤10 天 85 期、≤11 天 95 期、≤13 天 97 期、≤15 天 98 期。
  最慢的常规一期是 2024-01 → 2024-02-15（农历年，主管机关准予延后）；
  第 40 天那期是 2022-12 的**改版重发**，见下条。
  → roster LAG 取 **(15, 15)**：季末月**没有**例外，3/6/9/12 与常规月同一天发
    （季度表是同一份 PDF 里多印两张表，不另择日），所以两个数相同不是偷懒。
· URL 里的时间戳**不能当公告日**：2026-03 那期 URL 是 `20260508…`，
  正文电头却是 APRIL 10, 2026 —— 官网 5 月批量重传过一次。
  2022-12 那期是**另一回事，别混为一谈**：官网现挂的那份 PDF 标题是
  `REVISED: ASE Technology Holding Co., Ltd. Announces Monthly Net Revenues`、
  正文写 `announces its revised unaudited consolidated net revenues for
  December, 4th quarter and full year of 2022`，电头 FEBRUARY 9, 2023 ——
  它是一次**真实的改版重发**，不是重传，原始 1 月那份已被官网替换掉。
  所以 press_date() 对这一期给出的 2023-02-09 是「改版稿的发布日」，
  当 LAG 统计样本要剔除（月末后第 40 天），当「这份文件几时发的」是对的。
  **电头日期才是公告日。**

────────────────────────────────────────────────────────────────────────
口径坑（踩过的，别再踩）
────────────────────────────────────────────────────────────────────────
1. **PDF 主机对裸 UA 返 403 + 118 字节 HTML，状态码不是 403 就是 200。**
   media-aseholdco.todayir.com 挂在 awselb 后面，不带浏览器 UA 时返回
   `HTTP/2 403` + 118 字节 `<html>…403 Forbidden…</html>`；openpyxl / fitz
   拿到它会报「不是 zip / 不是 PDF」这种与真实原因毫无关系的错。
   → `_get_pdf()` **同时**校验：非 3xx、体长 ≥ 20,000、首 5 字节 `%PDF-`。
     三条缺一不可。落地页 `_get_html()` 同理校验体长 ≥ 50,000
     （真页 108KB，WAF/错误页远小于此）+ 正文含 `revenues-table`。

2. **落地页表格里的金额有错，且错得很像真的。**
   2026-01 那一格印的是 `$59,589`，PDF 正文与 MOPS 都是 **59,989**（差 400）。
   验伪三处一致：① 2026Q1 官方合并 173,662，用 59,989 加出来 173,663（差 1 是
   四舍五入），用 59,589 加出来 173,263（差 399）；② TWSE OpenAPI 2026-07 期的
   「累計營業收入-當月累計營收」438,509,375 千元 = 438,509 百万，
   用 59,989 加出来 438,510、用 59,589 是 438,110；③ MOPS 2026-01 全市场表
   3711 行是 59,988,631 千元。
   → **落地页只用来发现 PDF 链接**；金额从 PDF 取。两者不一致时打印告警
     （`_html_amount_check`），不改写、不阻断 —— 这是上游的排版错误，不是本模块的。

3. **2019-07 那份 PDF 全篇用 NBSP（U+00A0）当空格。**
   `(NT$\xa0Million)`、`Net\xa0Revenues`，任何按普通空格切词的解析器都会静默
   跳过整份文件（不是报错，是解析出 0 个月）。同一批还混着 U+2010 连字符当负号。
   → `_pdf_tokens()` 先做 `replace(' ', ' ')` 再 `\s+` 归一。
     99 份实测：修掉这一条之前 98/99，之后 99/99。

4. **「ATM」的口径是 ATM **分部**基础（含分部间交易），不是合并利润表的
   Packaging + Testing + Others。** 两者不是一回事，实测差 126~3,016 百万：
     2026Q2 月加总 ATM 126,149；合并利润表 Packaging 99,387 + Testing 23,665
     + Others 2,601 = 125,653；而当季法说会 deck 的
     `ATM Statements of Income → Total Net Revenues` = **126,148**。
   月度 PDF 的 ATM = deck 的 ATM 分部合计，逐季逐字对得上（见文末对账）。
   → 因此 `revenue_nonatm_ntd_mn`（= 合并 − ATM）**不是官方 EMS 分部营收**，
     它是「合并总额减 ATM 分部营收」的残差 = EMS + Others − ATM 分部间交易抵销。
     2026Q2：残差（本序列 4~6 月加总）64,914；官方合并 EMS 65,411；
     EMS 分部基础 65,789。（拿官方季度口径算残差是 191,064 − 126,148 = 64,916，
     与月加总差 2 是四舍五入，别把两者混着引。）
     列名故意不叫 `revenue_ems_ntd_mn` —— 叫了就是在口径上说谎。

5. **ATM 有过一次追溯重述，合并没有。**
   2019-09 期的脚注：「The ATM results presented have been retrospectively
   adjusted to exclude a portion of the results related to manufacturing
   integrated circuits from an acquired subsidiary consolidated since May 2019.」
   受影响的月份与调整额（旧 → 新）：
     2018-12  20,194 → 20,187   （−7，**不是**这次重述：2019-01 期就已经改过来了，
                                  是更早的一次小修，与 2019-09 那次无关）
     2019-05  20,248 → 20,148   （−100）
     2019-06  20,700 → 20,605   （−95）
     2019-07  21,763 → 21,668   （−95）
     2019-08  22,974 → 22,884   （−90）
   验：重述后 2019Q2 ATM = 18,841+20,148+20,605 = 59,594，与 2019-09 期印的
   重述后 Q2 逐字相等（原口径是 59,789）；2019Q3 = 21,668+22,884+23,349
   = 67,901，同样逐字相等（原口径 68,086）。
   → 落库一律取**最晚一次公布的读数**。合并口径 99 个月 × 3 次独立观测
     （自己那期 / 次月那期 / 次年同月那期）**零分歧**。

6. **重述体检**：每份新 PDF 自带上月与去年同月两列。本模块把这两列与已入库值
   逐格比对，不一致就**抛异常、本次不写入**，由人判断是重述还是解析变形 ——
   不悄悄改写、不追加第二行。同 fetch/tsm.py 口径坑 6、fetch/guc.py drift 检查。
   （上面第 5 条那次重述，正是这套检查在历史上会抓到的东西。）

7. **不许把 `Pro Forma Basis**` 那几张表当实际数。** 2022-01~2022-12 的每一期
   都多印一组「排除已处分中国四厂」的 pro forma 表，版式与实际表**完全相同**，
   只多一行 `Pro Forma Basis**` 标题。按 `Net Revenues` 硬找会先撞上实际表、
   再撞上 pro forma 表，取错一次就把 2022 全年拉低 8~10%。
   → `_pdf_tables()` 见到 `Pro Forma` 就把当前 section 置空，直到下一个
     section 标题为止。

8. **季末月与 12 月的 PDF 里还有 Q 表与 FY 表**，列头是 `Q1`/`FY` 而不是月份缩写。
   本模块按列头是不是月份缩写来筛，Q/FY 列直接丢掉（但**保留位置对齐**，
   否则 2018-09 那期的 `Q21 / Q22 / Q23`（SPIL 并购的三种 pro forma 口径）
   会把后面的列错位一格）。

9. **电头格式不止一种**。2023-04 / 2023-05 两期是 `TAIPEI, MAY 9, 2023 –`
   （没有 `TAIWAN, R.O.C.,`），同期还把 `TAIEX: 3711` 改成 `TWSE: 3711`。
   按 `TAIPEI, TAIWAN, R\.O\.C\.,` 硬匹配会在这两期上拿不到公告日。
   → `press_date()` 的正则把中段做成可选。

10. **`aseglobal.com` 与 `ir.aseglobal.com` 是两套站**。
    `https://www.aseglobal.com/en/investors/` 是 **404**（不是重定向），
    月营收只在 `ir.aseglobal.com/html/ir_revenues.php`。
    ir 站本身没有 WAF，裸 urllib 直接 200；有 WAF 的是 PDF 那台（坑 1）。

11. **落地页里埋着一张注释掉的假表，月份与真表重叠。**
    `ir_revenues.php` 的 HTML 里有一段 `<!-- … -->` 版式样板，内容是
    `January 23,591 / February 19,003 / March 11,352 / April 33,231`，
    每个 `<td>` 结构与真表**完全一样**，只有 href 是 `#`。
    不剥注释就直接跑行正则，任何年份都会多出这 4 行；2019 年以后 1~4 月是真月份，
    假行排在真行**之后**，只要哪天换成「后写的覆盖先写的」就会静默污染 4 个月。
    实测：不剥注释时 `_year_rows(2018)` 返回 12 行（真表只有 8 行），
    `_year_rows(2027)`（还不存在的年份）返回 4 行而不是 0 行。
    → `_year_rows()` 先 `_COMMENT_RE.sub('', html)`。

━━ 依赖 ━━ pymupdf（import 名 fitz，仓里已有）。不依赖 requests / pandas。

────────────────────────────────────────────────────────────────────────
对账实测（2026-08 落库时跑的，写死在这里当回归基准）
────────────────────────────────────────────────────────────────────────
· 合并 vs 官方季度（IR「Historical data」xlsx `Consolidated IS` sheet 的
  Total 行）：2018Q3~2026Q2 共 32 个季度，月加总与官方逐季差 **−1 ~ +1 百万**
  （四舍五入残差），无一季超过 1。
· 合并 vs 官方年度：2019 FY 413,182 / 2020 476,978（xlsx 印 476,979，公司自己
  两处差 1）/ 2021 569,997 / 2022 670,873 / 2023 581,914 / 2024 595,410 /
  2025 645,388 —— 月加总逐年差 ≤ 2。
· ATM vs 公司自印的季度 ATM（同一份月度 PDF 的 Q 表）：32 个季度**全部**差 ≤ 2。
  ⚠ 必须拿**最晚一版**的 Q 表比。用「季末那期自己印的 Q 表」会踩两处旧口径：
    2019Q2 旧版 59,790（2019-06 期）vs 月加总 59,594 → 差 196；
           2019-09 期重述后印 59,594，diff=0。
    2018Q4 旧版 64,127（2019-01 期）vs 月加总 64,120 → 差 7；
           2019-12 期印 64,120，diff=0。
  2019Q3 两版都是 67,901（2019-09 期与 2020-09 期逐字相同），与月加总相等 ——
  它**不是**例外。
· ATM vs **另一份文件**（2026 Q2 法说会 deck `ATM Statements of Income`）：
  2025Q2 92,564 vs 92,565、2026Q1 112,434 vs 112,434、2026Q2 126,149 vs 126,148。
· 第三源 MOPS 全市场月表（t21sc03，big5）：2018-05~2026-07 共 99 个月，
  逐月与本序列 `revenue_ntd_mn` 相符（MOPS 单位千元，除以 1000 后四舍五入到
  百万，最大绝对差 < 0.5 百万 —— 纯千元→百万的四舍五入残差）。
· 第三源 TWSE OpenAPI t187ap05_L（2026-08-12 出表、資料年月 11507）：
  營業收入-當月營收 73,783,701 千元 = 73,784 百万，与 2026-07 入库值相等；
  累計 438,509,375 千元 = 438,509，与本序列 2026 年 1~7 月加总 438,510 差 1。
"""

from __future__ import annotations

import csv
import datetime
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

IR_ORIGIN = 'https://ir.aseglobal.com'
IR_PAGE = IR_ORIGIN + '/html/ir_revenues.php'
TWSE_API = 'https://openapi.twse.com.tw/v1/opendata/t187ap05_L'
TWSE_CODE = '3711'

START_MONTH = '2018-05'          # ASEH 控股 2018-04-30 成立，2018-05 是第一个合并月
COLUMNS = ['month', 'revenue_ntd_mn', 'revenue_atm_ntd_mn', 'revenue_nonatm_ntd_mn']

_UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
       '(KHTML, like Gecko) Chrome/126.0 Safari/537.36')

_MIN_HTML = 50_000               # 真落地页 ~108KB；WAF / 错误页远小于此
_MIN_PDF = 20_000                # 真新闻稿 118~192KB；403 壳页 118 字节

_MONTH_NAME = {'January': 1, 'February': 2, 'March': 3, 'April': 4, 'May': 5,
               'June': 6, 'July': 7, 'August': 8, 'September': 9,
               'October': 10, 'November': 11, 'December': 12}
_MONTH_ABBR = {'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
               'June': 6, 'Jul': 7, 'July': 7, 'Aug': 8, 'Sep': 9, 'Sept': 9,
               'Oct': 10, 'Nov': 11, 'Dec': 12}
_MONTH_UPPER = {k.upper(): v for k, v in _MONTH_NAME.items()}

_PERIOD_RE = re.compile(r'^(Q\d{1,2}|FY|YTD|Jan|Feb|Mar|Apr|May|Jun|June|Jul|'
                        r'July|Aug|Sep|Sept|Oct|Nov|Dec)$')
_NUM_RE = re.compile(r'^[\d,]+$')
_ROW_RE = re.compile(
    r"<tr>\s*<td>([A-Za-z]+)</td>\s*<td>([^<]*)</td>\s*<td>(.*?)</td>\s*</tr>", re.S)
_HREF_RE = re.compile(r"""href=['"]([^'"]+\.pdf)['"]""", re.I)
_COMMENT_RE = re.compile(r'<!--.*?-->', re.S)


class AseFetchError(RuntimeError):
    """本模块的故障出口。抓不到 / 认不出来一律抛它，不返回 None 掩盖故障。"""


# ══════════════════════════════════════════════════════════════════════════════
# HTTP —— 状态码从来不是成功的证据（口径坑 1）
# ══════════════════════════════════════════════════════════════════════════════
def _open(url, *, referer=None, tries=3, timeout=120):
    """取 URL，3xx 一律判失败（软 404 会被当成真内容）。"""
    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            raise AseFetchError(f'{url} 重定向到 {newurl}（{code}）—— 该资源不存在')

    opener = urllib.request.build_opener(_NoRedirect)
    headers = {'User-Agent': _UA}
    if referer:
        headers['Referer'] = referer
    last = None
    for _ in range(tries):
        try:
            return opener.open(urllib.request.Request(url, headers=headers),
                               timeout=timeout).read()
        except AseFetchError:
            raise
        except Exception as exc:                                   # noqa: BLE001
            last = exc
    raise AseFetchError(f'{url} 取不到：{last!r}')


def _get_html(url):
    body = _open(url)
    if len(body) < _MIN_HTML:
        raise AseFetchError(f'{url} 只有 {len(body)} 字节（<{_MIN_HTML}），疑似 WAF / 错误页')
    text = body.decode('utf-8', 'ignore')
    if 'revenues-table' not in text:
        raise AseFetchError(f'{url} 里没有 revenues-table（落地页改版？）')
    return text


def _get_pdf(url):
    """PDF 三重校验：非 3xx（由 _open 保证）、体长、魔数。缺一不可（口径坑 1）。"""
    body = _open(url, referer=IR_PAGE)
    if len(body) < _MIN_PDF:
        raise AseFetchError(
            f'{url} 只有 {len(body)} 字节（<{_MIN_PDF}）—— '
            f'媒体主机对裸 UA 返 403 + 118 字节 HTML，见 fetch/ase.py 口径坑 1')
    if not body.startswith(b'%PDF-'):
        raise AseFetchError(f'{url} 首 5 字节是 {body[:5]!r}，不是 %PDF-')
    return body


# ══════════════════════════════════════════════════════════════════════════════
# 落地页 —— 只用来发现 PDF 链接与月份，金额一概不信（口径坑 2）
# ══════════════════════════════════════════════════════════════════════════════
def _year_rows(year):
    """返回 [(month 'YYYY-MM', 落地页印的金额 float|None, PDF 绝对 URL|None), …]。

    ⚠️ 必须先剥掉 HTML 注释（口径坑 11）。
    """
    html = _COMMENT_RE.sub('', _get_html(f'{IR_PAGE}?year={year}'))
    out = []
    for name, amount, cell in _ROW_RE.findall(html):
        if name not in _MONTH_NAME:
            continue
        href = _HREF_RE.search(cell)
        raw = amount.replace('$', '').replace(',', '').replace('﻿', '').strip()
        try:
            val = float(raw)
        except ValueError:
            val = None
        out.append((f'{year}-{_MONTH_NAME[name]:02d}', val,
                    urllib.parse.urljoin(IR_ORIGIN, href.group(1)) if href else None))
    return out


def _discover(years):
    """扫若干年的落地页，返回 {month: (落地页金额, PDF URL)}，只保留有 PDF 的月。"""
    found = {}
    for year in years:
        try:
            rows = _year_rows(year)
        except AseFetchError as exc:
            print(f'[ase][warn] {year} 年落地页跳过：{exc}')
            continue
        for month, val, url in rows:
            if url and month >= START_MONTH:
                found[month] = (val, url)
    if not found:
        raise AseFetchError(f'{years} 这几年的落地页一个 PDF 链接都没抓到（改版？）')
    return found


# ══════════════════════════════════════════════════════════════════════════════
# PDF 解析 —— token 流，不依赖列坐标
# ══════════════════════════════════════════════════════════════════════════════
def _pdf_tokens(blob):
    """PyMuPDF 的阅读顺序文本 → 逐行 token。NBSP 必须先归一（口径坑 3）。"""
    try:
        import fitz
    except ImportError as exc:                                     # pragma: no cover
        raise AseFetchError('需要 pymupdf（fitz）才能解析 ASEH 的新闻稿 PDF') from exc
    with fitz.open(stream=blob, filetype='pdf') as doc:
        raw = '\n'.join(page.get_text() for page in doc)
    toks = []
    for line in raw.split('\n'):
        s = re.sub(r'\s+', ' ', line.replace(' ', ' ')).strip()
        if s:
            toks.append(s)
    return toks


def _pdf_tables(blob):
    """解析一份新闻稿，返回 {'C': {month: NT$mn}, 'A': {month: NT$mn}}。

    C = CONSOLIDATED NET REVENUES，A = (IC-)ATM NET REVENUES。
    一份 PDF 通常给三个月（当月 / 上月 / 去年同月）。
    US$ 表、Q 表、FY 表、Pro Forma 表全部剔除（口径坑 7、8）。
    """
    toks = _pdf_tokens(blob)
    out = {'C': {}, 'A': {}}
    section = None
    for i, tok in enumerate(toks):
        if tok.startswith('CONSOLIDATED NET REVENUES'):
            section = 'C'
            continue
        if re.match(r'^(IC-)?ATM NET REVENUES', tok):
            section = 'A'
            continue
        if tok.startswith('Pro Forma'):          # 口径坑 7：pro forma 不是实际数
            section = None
            continue
        if section is None or tok != '(NT$ Million)':
            continue                              # US$ 表在这里被挡掉
        # 往回取列头（月份 / Q1 / FY …），往前取年份与数值
        j = i - 1
        while j >= 0 and toks[j] in ('Sequential', 'YoY'):
            j -= 1
        periods = []
        while j >= 0 and _PERIOD_RE.match(toks[j]):
            periods.append(toks[j])
            j -= 1
        periods.reverse()
        k = i + 1
        years = []
        while k < len(toks) and re.fullmatch(r'\d{4}', toks[k]):
            years.append(toks[k])
            k += 1
        while k < len(toks) and toks[k] == 'Change':
            k += 1
        if k >= len(toks) or not toks[k].startswith('Net Revenues'):
            continue
        k += 1
        values = []
        while k < len(toks) and _NUM_RE.match(toks[k]):
            values.append(toks[k])
            k += 1
        # 位置对齐后再筛月份列：Q21/Q22/Q23 这类列必须占位，否则整行错位（口径坑 8）
        for c, period in enumerate(periods):
            if period not in _MONTH_ABBR or c >= len(years) or c >= len(values):
                continue
            key = f'{years[c]}-{_MONTH_ABBR[period]:02d}'
            out[section].setdefault(key, float(values[c].replace(',', '')))
    if not out['C'] or not out['A']:
        raise AseFetchError(
            f'新闻稿解析出 C={len(out["C"])} 个、A={len(out["A"])} 个月份 —— 版式变了？'
            '（若是 0/0，先怀疑 NBSP，见口径坑 3）')
    return out


def press_date(blob):
    """从正文电头取公告日 'YYYY-MM-DD'。取不到返回 None（口径坑 9）。"""
    flat = ' '.join(_pdf_tokens(blob))
    m = re.search(r'TAIPEI,\s*(?:TAIWAN,\s*R\.O\.C\.,\s*)?([A-Z]+)\s+(\d{1,2}),\s*(\d{4})',
                  flat)
    if not m or m.group(1) not in _MONTH_UPPER:
        return None
    return datetime.date(int(m.group(3)), _MONTH_UPPER[m.group(1)],
                         int(m.group(2))).isoformat()


# ══════════════════════════════════════════════════════════════════════════════
# 交叉校验（只告警，不阻断）
# ══════════════════════════════════════════════════════════════════════════════
def _twse_latest():
    """TWSE OpenAPI 里 3711 的 (月份, 当月营收 NT$mn, 当年累计 NT$mn)。"""
    try:
        blob = _open(TWSE_API, tries=2, timeout=90)
        if len(blob) < 100_000:
            raise AseFetchError(f'TWSE OpenAPI 只有 {len(blob)} 字节，疑似壳页')
        for rec in json.loads(blob.decode('utf-8', 'ignore')):
            if rec.get('公司代號') == TWSE_CODE:
                roc = str(rec['資料年月'])                    # 11507 = 2026-07
                month = f'{int(roc[:-2]) + 1911}-{int(roc[-2:]):02d}'
                return (month,
                        float(rec['營業收入-當月營收']) / 1000.0,
                        float(rec['累計營業收入-當月累計營收']) / 1000.0)
    except Exception as exc:                                       # noqa: BLE001
        print(f'[ase][warn] TWSE OpenAPI 交叉校验跳过：{exc!r}')
    return None, None, None


def _html_amount_check(month, html_val, pdf_val):
    """落地页表格 vs PDF 正文。不一致只告警 —— 上游排版错误不该拖住抓取（口径坑 2）。"""
    if html_val is None or pdf_val is None:
        return
    if abs(html_val - pdf_val) > 0.5:
        print(f'[ase][warn] {month} 落地页表格印 {html_val:,.0f}、PDF 正文 {pdf_val:,.0f} '
              f'—— 以 PDF 为准（2026-01 有过同样的排版错，见口径坑 2）')


# ══════════════════════════════════════════════════════════════════════════════
# 对外的两个函数
# ══════════════════════════════════════════════════════════════════════════════
def latest_month(cache_dir):                                       # noqa: ARG001
    """官方源当前最新月 'YYYY-MM'。抓不到一律抛 AseFetchError。"""
    today = datetime.date.today()
    # 跨年那几天当年页可能还是空的，往回多看一年
    found = _discover([today.year, today.year - 1])
    newest = max(found)
    tables = _pdf_tables(_get_pdf(found[newest][1]))
    if newest not in tables['C']:
        raise AseFetchError(
            f'落地页说最新月是 {newest}，但那份 PDF 里没有 {newest} 的合并列 '
            f'（PDF 里有 {sorted(tables["C"])}）—— 落地页与 PDF 不同步')
    return newest


def _fmt(v):
    return f'{v:.0f}'


def update(series_dir, cache_dir):                                 # noqa: ARG001
    """把新月份追加进 series/ase.csv，返回新增月份列表（升序）。

    幂等：已入库的月份不重写；既有行原样搬运，没有新月份时**文件字节级不变**。
    已有值永不覆盖 —— 与官方值不一致时**抛异常**（口径坑 6），由人判断。
    """
    csv_path = os.path.join(series_dir, 'ase.csv')
    with open(csv_path, newline='', encoding='utf-8') as fh:
        rows = list(csv.reader(fh))
    header, body = rows[0], [r for r in rows[1:] if r and r[0].strip()]
    if header != COLUMNS:
        raise AseFetchError(f'series/ase.csv 列不对：{header} != {COLUMNS}')
    have = {r[0]: r for r in body}

    today = datetime.date.today()
    last = max(have) if have else START_MONTH
    years = sorted({int(last[:4]), today.year - 1, today.year})
    found = _discover(years)

    missing = sorted(m for m in found if m >= START_MONTH and m not in have)
    if not missing:
        # 没有新月份也照样做一次交叉校验，但**绝不写文件**（幂等是验收项）
        _crosscheck(have)
        return []

    official_c, official_a, seen_html = {}, {}, {}
    for month in missing:
        html_val, url = found[month]
        tables = _pdf_tables(_get_pdf(url))
        if month not in tables['C'] or month not in tables['A']:
            raise AseFetchError(
                f'{month} 的新闻稿里没有 {month} 那一列'
                f'（C={sorted(tables["C"])} A={sorted(tables["A"])}）—— 链接串行了？')
        seen_html[month] = html_val
        # 一份 PDF 顺带给出上月与去年同月，全部收进来供重述体检
        for key, val in tables['C'].items():
            official_c[key] = val
        for key, val in tables['A'].items():
            official_a[key] = val

    # ── 重述体检：已入库月份逐格比对，不一致抛异常而不是改写（口径坑 6）──────────
    drift = []
    for month, row in sorted(have.items()):
        if month not in official_c or month not in official_a:
            continue
        c, a = official_c[month], official_a[month]
        want = [month, _fmt(c), _fmt(a), _fmt(c - a)]
        if row != want:
            drift.append((month, row, want))
    if drift:
        raise AseFetchError(
            'ASEH 新闻稿与已入库值不一致（疑似重述或解析变形），本次不写入：\n  '
            + '\n  '.join(f'{m}: 库内 {old} vs 官方 {new}' for m, old, new in drift[:5])
            + '\n  （2019 年那次 ATM 追溯重述就是这个形状，见 fetch/ase.py 口径坑 5）')

    added = []
    for month in missing:
        c, a = official_c[month], official_a[month]
        _html_amount_check(month, seen_html.get(month), c)
        body.append([month, _fmt(c), _fmt(a), _fmt(c - a)])
        have[month] = body[-1]
        added.append(month)

    body.sort(key=lambda r: r[0])
    with open(csv_path, 'w', newline='', encoding='utf-8') as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        writer.writerows(body)

    _crosscheck(have)
    return added


def _crosscheck(have):
    """与 TWSE OpenAPI 当期对账。只告警，不阻断 —— 第三源挂掉不该拖住本页。"""
    month, val, ytd = _twse_latest()
    if not month:
        return
    newest = max(have) if have else None
    if newest and month > newest:
        print(f'[ase][warn] TWSE 已有 {month}，但 IR 落地页最新只到 {newest} —— 下次再跑')
    if month in have:
        mine = float(have[month][1])
        if abs(mine - val) > 1.0:
            print(f'[ase][warn] {month} 入库 {mine:,.0f} vs TWSE {val:,.0f} NT$mn 不符')
    if ytd:
        year = month[:4]
        mine_ytd = sum(float(r[1]) for m, r in have.items() if m[:4] == year and m <= month)
        if abs(mine_ytd - ytd) > 2.0:
            print(f'[ase][warn] {year} 年 1~{month[5:]} 月入库加总 {mine_ytd:,.0f} '
                  f'vs TWSE 累计 {ytd:,.0f} NT$mn 不符')


if __name__ == '__main__':                                         # pragma: no cover
    print('latest_month =', latest_month(None))
    print('added =', update(os.path.join(ROOT, 'series'), None))
