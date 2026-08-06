# -*- coding: utf-8 -*-
"""HKEX 香港交易所 00388 —— 月度市场统计抓取模块（无人值守）。

═══ 数据源 ═══
唯一真值文件：HKEX 官方「Monthly HK Market Highlight Data」Excel
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
"""

import csv
import datetime as _dt
import email.utils
import io
import os
import re
import urllib.error
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
COLUMNS = ['adt_hkdbn', 'mktcap_hkdtn', 'new_listings', 'ipo_funds_hkdbn',
           'derivatives_adv_contracts', 'southbound_adt_hkdbn']
_DECIMALS = {'adt_hkdbn': 3, 'mktcap_hkdtn': 4, 'new_listings': 0, 'ipo_funds_hkdbn': 3,
             'derivatives_adv_contracts': 0, 'southbound_adt_hkdbn': 3}

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

    任何一个 COLUMNS 里的列在官方源里取不到值 → 抛异常，绝不写 NaN/空。

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
    if header != ['month'] + COLUMNS:
        raise HkexFetchError('series/hkex.csv 列名与预期不符：%s' % header)

    body = [ln.split(',') for ln in lines[1:]]
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
            for j, col in enumerate(COLUMNS, start=1):
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
        missing = [c for c in COLUMNS if rec[c] is None]
        if missing:
            raise HkexFetchError(
                '%s 解析结果缺列 %s —— 拒绝写入残缺行。'
                '要么官方版式变了，要么该月确实只发了一半，请人工确认。' % (month, missing))
        body.append([month] + [_fmt(c, rec[c]) for c in COLUMNS])
        idx[month] = len(body) - 1
        added.append(month)

    # 重述记录始终落盘，方便人工判断是口径变化还是解析出错
    if restatements:
        os.makedirs(cache_dir, exist_ok=True)
        rp = os.path.join(cache_dir, 'hkex_restatements.csv')
        with open(rp, 'w', newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            w.writerow(['month', 'column', 'in_series_csv', 'in_official_xlsx'])
            w.writerows(restatements)
        print('[hkex] 官方源与 series 有 %d 处不一致，已写 %s（allow_restate=%s）'
              % (len(restatements), rp, allow_restate))

    if not (added or filled_cells or (restatements and allow_restate)):
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
