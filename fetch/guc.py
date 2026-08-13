# -*- coding: utf-8 -*-
r"""创意电子（GUC，3443.TW）月度营收 —— 无人值守抓取模块。

对应 build/specs/guc.py（页面由通用底座 build/single.py 生成），维护一个序列文件：

  series/guc.csv    month, revenue_ntd_mn, revenue_turnkey_ntd_mn, revenue_nre_other_ntd_mn

────────────────────────────────────────────────────────────────────────
数据源
────────────────────────────────────────────────────────────────────────
1) 营收（guc.csv）—— 官方 xlsx，一份文件带全 2017-01 至今
   落地页 https://www.guc-asic.com/en/investor/financial?financial-tab=option2
   页面上挂一个「Historical Monthly revenue」按钮，指向
   /upload/<上传日>/8_<随机串>.xlsx。单 sheet `revenue breakdown`，单位 NT$K，
   逐年一块，每块 = 月份表头行（YYYYMM）+ Turnkey / NRE / Others / Total 四行。

   **URL 每月随新数据换一次**（路径含上传日，与当月营收公告同日），所以必须每次从
   落地页现抓，写死的那一刻就注定了下个月拿到的是上个月的文件。

2) 交叉校验源（只读不写）
   TWSE OpenAPI https://openapi.twse.com.tw/v1/opendata/t187ap05_L
   全市场当期一份 JSON，单位新台币千元。只有最新一期、没有历史，所以只用来验证
   「官方最新月是哪个月 + 金额对不对」。3443 是**本国公司**，在 t187ap05_L 里；
   世芯-KY 3661、矽力-KY 6415 那类外国发行人不在这张表、走 TPEx 的 _O 端点。

3) 公告日（source_dates.csv 的 guc 行）
   新闻稿列表页 https://www.guc-asic.com/en/news/PressRelease
   正文首句是电头：「Hsinchu, Taiwan, Aug 5, 2026 - GUC (TAIEX: 3443) today
   announced its net sales for July 2026 were NT5,769 million...」

────────────────────────────────────────────────────────────────────────
发布节奏
────────────────────────────────────────────────────────────────────────
· 台湾《证券交易法》要求次月 10 日前公告，但 GUC 的实际惯例是**次月 5 日 14:00**，
  而且公司在 IR 财务日历（同一份 HTML，见口径坑 5）里**逐条预告**下一次的日期。
  实测预告日与新闻稿电头日逐条相等：
    2025-12→01/05  2026-01→02/05  2026-03→04/07  2026-04→05/05
    2026-05→06/05  2026-06→07/06  2026-07→08/05
  → 调度：roster LAG 取 (7, 7)，覆盖撞假日顺延的最坏情形（2026-03 那期撞清明落到 4/7）。
  → 但**不要拿「次月 5 日」外推公告日**，照样每次去新闻稿现读 —— 顺延不规律。

────────────────────────────────────────────────────────────────────────
口径坑（踩过的，别再踩）
────────────────────────────────────────────────────────────────────────
1. **Total 行 115 格里 61 格是活公式，不许读它**。xlsx 的 Total 行在 2018~2022
   整年是 `=SUM(B23:B25)` 这种公式串；openpyxl 默认 `data_only=False` 会静默读到
   字符串，`data_only=True` 读到的是 **Excel 写入的缓存值** —— 而缓存是发布者保存
   工具的副产品，上游某月改用 LibreOffice 或脚本另存就没了，整块变 None 静默漏年。
   → 本模块一律**对分项求和**（Turnkey + NRE/Others）。实测 115 个月分项和与 Total
     无一例外相等，所以这不是近似，是绕开一个会静默失效的依赖。

2. **2026-01 起官方把 NRE 与 Others 合并**：年份块从
   `Turnkey / NRE / Others / Total` 四行变成 `Turnkey / NRE & Others / Total` 三行
   （IR deck 里同一口径又叫 'NRE & IP'）。Total 不受影响，但拆分列有断点。
   → 落库统一成两列，2017-2025 的 NRE + Others 在这里就合并掉，序列口径逐月连续。

3. **xlsx 链接是相对路径**。href 写作 `/upload/2026_08_05/8_...xlsx`，不是绝对 URL。
   用 `https?://[^"']+\.xlsx` 这种正则会一个都抓不到，然后误判成「页面是 JS 渲染的」。
   → 必须 urljoin。（实测踩过。）

4. **新闻稿 slug 不可拼，且软 404 是 302 不是 404**。
   · slug 命名法至少 7 种：`202607revenue` / `202604revenueE` / `202601revenuE`
     （官网自己拼错）/ `202505` / `202502E-20250305` / `GUCMonthlySalesReportinJune2025`…
   · 不存在的 slug **302 跳到 /en**，跟随重定向后是 172,215 字节的通用壳页，
     HTTP 状态码 200 —— 按状态码校验完全无效，会把壳页当文章解析出错日期。
   · 壳页里**也有 'Hsinchu'**（页脚地址），所以 'Hsinchu' 没有判别力，
     真正有判别力的是正文的 'net sales'。
   → 本模块从列表页抓 href，且 `_no_redirect_opener` 关掉重定向：3xx 直接判失败。

5. **`financial-tab=option2` 与 `option7` 返回完全同一份 HTML**（353,794 字节，
   tab 是纯前端切换）。一次请求同时拿到最新 xlsx 链接与下次公告日历，
   不必两次请求，也不存在两个页面不同步的问题。

6. **重述**：xlsx 是全量覆盖式文件，而且 URL 每月一换（比 TSMC 的替换频率还高）。
   一旦上游改历史，本模块会检测到与已入库值不一致并**抛异常**，
   而不是悄悄改写或追加 —— 由人判断是口径变更还是解析出错。同 fetch/tsm.py 口径坑 6。

7. guc-asic.com **没有 WAF**，裸 urllib 直接 200，不像 investor.tsmc.com 认 UA 指纹。
"""

from __future__ import annotations

import csv
import io
import json
import os
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

ORIGIN = 'https://www.guc-asic.com'
IR_PAGE = ORIGIN + '/en/investor/financial?financial-tab=option2'
PR_LIST = ORIGIN + '/en/news/PressRelease'
TWSE_API = 'https://openapi.twse.com.tw/v1/opendata/t187ap05_L'
TWSE_CODE = '3443'

START_MONTH = '2017-01'
COLUMNS = ['month', 'revenue_ntd_mn', 'revenue_turnkey_ntd_mn', 'revenue_nre_other_ntd_mn']

_UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
       '(KHTML, like Gecko) Chrome/126.0 Safari/537.36')
_CTX = ssl.create_default_context()

# 真页 >100KB；壳页 172KB 但没有 'net sales'；WAF/错误页远小于此
_MIN_HTML = 50_000
_MIN_XLSX = 5_000


class GucFetchError(RuntimeError):
    """本模块的故障出口。抓不到 / 认不出来一律抛它，不返回 None 掩盖故障。"""


def _get(url, *, follow=True, tries=3, min_bytes=0):
    """取 URL。follow=False 时 3xx 直接判失败（见口径坑 4）。"""
    if follow:
        opener = urllib.request.build_opener()
    else:
        class _NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                raise GucFetchError(f'{url} 重定向到 {newurl}（{code}）—— 该资源不存在')
        opener = urllib.request.build_opener(_NoRedirect)
    last = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': _UA})
            body = opener.open(req, timeout=120).read()
            if len(body) < min_bytes:
                raise GucFetchError(f'{url} 只有 {len(body)} 字节（<{min_bytes}），疑似壳页')
            return body
        except GucFetchError:
            raise
        except Exception as exc:                                  # noqa: BLE001
            last = exc
    raise GucFetchError(f'{url} 取不到：{last!r}')


def _ir_html():
    return _get(IR_PAGE, min_bytes=_MIN_HTML).decode('utf-8', 'ignore')


def _xlsx_url(html):
    """从落地页 HTML 取最新 xlsx 的绝对 URL。相对路径必须 urljoin（口径坑 3）。"""
    hits = re.findall(r'["\']([^"\']*\.xlsx)["\']', html)
    if not hits:
        raise GucFetchError('落地页里找不到 .xlsx 链接（页面改版？）')
    return urllib.parse.urljoin(ORIGIN, hits[0])


def _parse_xlsx(blob):
    """解析 revenue breakdown sheet，返回 {'YYYY-MM': (turnkey, nre_other)}，单位 NT$K。

    只对分项求和，永不读 Total 行（口径坑 1）。
    """
    try:
        import openpyxl
    except ImportError as exc:                                     # pragma: no cover
        raise GucFetchError('需要 openpyxl 才能解析 GUC 的 xlsx') from exc
    wb = openpyxl.load_workbook(io.BytesIO(blob), data_only=True)
    if 'revenue breakdown' not in wb.sheetnames:
        raise GucFetchError(f'xlsx 里没有 revenue breakdown sheet：{wb.sheetnames}')
    rows = [list(r) for r in wb['revenue breakdown'].iter_rows(values_only=True)]

    out = {}
    for i, row in enumerate(rows):
        # 年份块的表头行：第一格空，第二格是 YYYYMM 形态的整数
        if row[0] is not None or not isinstance(row[1], (int, float)):
            continue
        if not (200_000 < int(row[1]) < 300_000):
            continue
        months = [int(x) for x in row[1:] if isinstance(x, (int, float))]
        block = {}
        for j in range(i + 1, min(i + 6, len(rows))):
            label = str(rows[j][0] or '').strip()
            if not label:
                continue
            block[label] = list(rows[j][1:1 + len(months)])
            if label.lower().startswith('total'):
                break
        turnkey = block.get('Turnkey')
        if turnkey is None:
            raise GucFetchError(f'年份块 {months[0]} 里没有 Turnkey 行')
        merged = block.get('NRE & Others')        # 2026 起
        nre, others = block.get('NRE'), block.get('Others')        # 2025 及以前
        if merged is None and nre is None:
            raise GucFetchError(f'年份块 {months[0]} 里既没有 NRE 也没有 NRE & Others')
        for k, ym in enumerate(months):
            t = turnkey[k]
            if merged is not None:
                n = merged[k]
            else:
                n = (nre[k] if nre else 0) + (others[k] if others else 0)
            if t is None or n is None:
                continue
            out[f'{ym // 100}-{ym % 100:02d}'] = (float(t), float(n))
    if not out:
        raise GucFetchError('xlsx 解析出 0 个月（版式变了？）')
    return out


def _twse_latest():
    """TWSE OpenAPI 里 3443 的 (月份, 当月营收 NT$K)。交叉校验用，失败不阻断。"""
    try:
        blob = _get(TWSE_API, tries=2, min_bytes=1000)
        for rec in json.loads(blob.decode('utf-8', 'ignore')):
            if rec.get('公司代號') == TWSE_CODE:
                roc = str(rec['資料年月'])           # 11507 = 2026-07
                month = f'{int(roc[:-2]) + 1911}-{int(roc[-2:]):02d}'
                return month, float(rec['營業收入-當月營收'])
    except Exception as exc:                                       # noqa: BLE001
        print(f'[guc][warn] TWSE OpenAPI 交叉校验跳过：{exc!r}')
    return None, None


def latest_month(cache_dir):                                       # noqa: ARG001
    """官方源当前最新月 'YYYY-MM'。抓不到一律抛 GucFetchError。"""
    return max(_parse_xlsx(_get(_xlsx_url(_ir_html()), min_bytes=_MIN_XLSX)))


def _fmt(v):
    return f'{v / 1000:.3f}'


def update(series_dir, cache_dir):                                 # noqa: ARG001
    """把新月份追加进 series/guc.csv，返回新增月份列表（升序）。

    幂等：已入库的月份不重写；既有行原样搬运，没有新月份时文件字节级不变。
    已有值永不覆盖 —— 与官方值不一致时**抛异常**（口径坑 6），由人判断。
    """
    csv_path = os.path.join(series_dir, 'guc.csv')
    with open(csv_path, newline='', encoding='utf-8') as fh:
        rows = list(csv.reader(fh))
    header, body = rows[0], [r for r in rows[1:] if r and r[0].strip()]
    if header != COLUMNS:
        raise GucFetchError(f'series/guc.csv 列不对：{header} != {COLUMNS}')
    have = {r[0]: r for r in body}

    official = _parse_xlsx(_get(_xlsx_url(_ir_html()), min_bytes=_MIN_XLSX))

    # 重述体检：已入库月份逐格比对，不一致抛异常而不是改写
    drift = []
    for month, row in have.items():
        if month not in official:
            continue
        t, n = official[month]
        want = [month, _fmt(t + n), _fmt(t), _fmt(n)]
        if row != want:
            drift.append((month, row, want))
    if drift:
        raise GucFetchError(
            'GUC 官方 xlsx 与已入库值不一致（疑似重述或解析变形），本次不写入：\n  '
            + '\n  '.join(f'{m}: 库内 {old} vs 官方 {new}' for m, old, new in drift[:5]))

    added = []
    for month in sorted(official):
        if month < START_MONTH or month in have:
            continue
        t, n = official[month]
        body.append([month, _fmt(t + n), _fmt(t), _fmt(n)])
        added.append(month)

    if added:
        body.sort(key=lambda r: r[0])
        with open(csv_path, 'w', newline='', encoding='utf-8') as fh:
            w = csv.writer(fh)
            w.writerow(header)
            w.writerows(body)

    # 交叉校验：官方最新月与 TWSE OpenAPI 对账（只告警，不阻断）
    tw_month, tw_val = _twse_latest()
    if tw_month:
        newest = max(official)
        if tw_month != newest:
            print(f'[guc][warn] TWSE 最新月 {tw_month} 与 IR xlsx 最新月 {newest} 不一致')
        elif tw_val is not None:
            t, n = official[newest]
            if abs((t + n) - tw_val) > 1.0:
                print(f'[guc][warn] {newest} IR {t + n:,.0f} vs TWSE {tw_val:,.0f} NT$K 不符')

    return added
