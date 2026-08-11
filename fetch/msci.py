# -*- coding: utf-8 -*-
"""MSCI Inc. — 挂钩 MSCI 股票指数的 ETF 月度 AUM 抓取模块。

═══ 源 ═══
    https://ir.msci.com/aum-etfs-linked-msci-indexes
    页面标题「AUM in ETFs Linked to MSCI Equity Indexes」。

为什么用 IR 页面而不是找 xlsx：MSCI 这张表**没有**对应的下载文件。IR 站（Q4 Inc.
托管的 Drupal）把整张表**服务端渲染**成 <table class="table nirtable">，一次
GET 就拿到 2008-12 至今的全历史，不需要 JS、不需要 Cookie、不需要登录态。
2026-08-05 实测：普通 python urllib + 桌面 Chrome UA，HTTP 200，无 Cloudflare /
Akamai / PerimeterX 拦截。所以本模块**不依赖浏览器**，可无人值守跑。
（/download-library、/static-files/* 下没有这份 AUM 数据；SEC 10-Q 里只有季度
平均值的文字描述，粒度不够，不作为备源。）

═══ 发布节奏 ═══
    每月一次，更新「上一个自然月」。MSCI 不为此发新闻稿，只是悄悄改这个页面，
    所以没有可订阅的事件——只能轮询。经验节奏是次月中旬（本文件写于
    2026-08-05，向源站取到的**未走缓存**的页面最新行仍是 Jun'26，Jul'26 未上线）。
    → 调度建议：次月 10 日起每天跑一次 latest_month()，出现新月份再 update()。
      不要在月初 1–5 号就判定「源挂了」，那只是还没发。

═══ CDN 缓存陷阱（无人值守的头号坑，别删 cache-buster）═══
    响应头是 `cache-control: public, max-age=0, s-maxage=2592000` —— 边缘节点
    可以缓存这个页面 **30 天**。2026-08-05 实测裸 URL 拿到的是 x-age=546028
    （6.3 天前）、x-cache-hits=299 的缓存副本。也就是说：新月份上线后，轮询
    可能连续好几天都还看到旧表，然后误判「MSCI 这个月没发」。
    → 所以 _download() 一律加 `?_=<unix ts>` + no-cache 头。加了之后 x-age=0，
      是源站现渲染的页面。这一行不是洁癖，删了会静默漏数据。
    另：`last-modified` 头**不能**当数据新鲜度用 —— 走缓存时它是 6 天前，绕过
    缓存时它直接变成「当前时刻」，它反映的是渲染时间不是数据时间。判断有没有
    新数据只能看解析出来的 max(month)。

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
6. 月份写法在表格里混用直角撇 ' (U+0027) 和弯撇 ’ (U+2019)、混用 &nbsp;、
   月份后还挂脚注号——解析器必须全都容忍，不能按固定字符串切。
   ⚠ **脚注号有两种写法，而且同一张表里会混用**：绝大多数行是标签
   `<td>Jun’26 <sup>3</sup></td>`（_clean 删得掉），但 2026-08 实测 Jul'26 那一行
   写成了**裸文本** `<td>Jul’26 3</td>`（删不掉）。原来的 _MONTH_RE 结尾锚 `$`
   不容忍尾随字符，于是这一行被当说明行 continue 掉 —— 源上明明有 7 月，
   latest_month() 却返回 6 月，fetch 干净地报 NOCHANGE，**没有任何报错**。
   这个坏法比抓取失败危险得多：它不产生 FAIL，连续失败计数、红点、断档哨兵
   全都抓不到它，页面就一直挂着旧数据。修法是两条一起：
     (a) _MONTH_RE 容忍尾随的裸脚注尾巴（见该常量旁注）；
     (b) parse() 增加**行数对账**——凡是「长得像数据行」（后两格都是金额）却
         没能解析出月份的行，一律抛异常。(a) 只挡住已知的这一种变体，
         (b) 才是挡住下一种没见过的变体的那道。别只留 (a)。

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
from datetime import datetime, timezone

URL = "https://ir.msci.com/aum-etfs-linked-msci-indexes"

# 用常规桌面 UA。实测该站不封 python-urllib（没有 403、没有验证码），但带默认
# UA "Python-urllib/3.x" 时会**间歇性挂住**：2026-08-05 连试两次，一次 25s 超时、
# 一次 0.8s 正常；换 Chrome UA 后多次均稳定 <1s。像是 WAF 的 tarpit 而非硬拦。
# 所以：UA 换成 Chrome + 下面的重试，两条一起才能撑住无人值守。
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
RETRIES = 3          # 间歇性挂起是本源唯一的失败模式，重试是主要防线
TIMEOUT = 45

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
_MONTH_RE = re.compile(
    r"^([A-Za-z]{3})[’'‘ʼ`]\s*(\d{2})"      # Jul’26
    r"(?:[\s,]*[\d*†‡§¶]+)*"                # 可选：裸脚注号，可有多个（"3"、"1,2"）
    r"\s*$")


# ────────────────────────────── 下载 ──────────────────────────────

def _download(cache_dir):
    """抓页面并落盘到 cache_dir。返回 (html_text, saved_path)。

    每次都存一份带日期的快照：这张表是「活页面」，MSCI 改了历史行不会留痕，
    留快照才能事后判断某次数值变化是重述还是解析 bug。
    """
    os.makedirs(cache_dir, exist_ok=True)
    # ↓ cache-buster 不是洁癖，是必须的：见文件头「CDN 缓存陷阱」
    url = f"{URL}?_={int(time.time())}"
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    })
    raw, last_err = None, None
    for attempt in range(RETRIES):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                raw = r.read()
            break
        except urllib.error.HTTPError as e:
            # 4xx/5xx 是确定性错误，重试没意义，直接抛
            raise RuntimeError(f"MSCI IR 返回 HTTP {e.code}（URL={url}）") from e
        except Exception as e:            # URLError / socket.timeout / 连接重置
            last_err = e
            if attempt < RETRIES - 1:
                time.sleep(5 * (attempt + 1))
    if raw is None:
        raise RuntimeError(
            f"MSCI IR 连续 {RETRIES} 次抓取失败：{type(last_err).__name__}: "
            f"{last_err}（URL={url}）")

    text = raw.decode("utf-8", errors="replace")
    if "nirtable" not in text:
        raise RuntimeError(
            "MSCI IR 页面里找不到 nirtable 表格——页面改版或被拦截页顶掉了，"
            f"落盘文件请人工看一眼（{len(raw)} bytes）")

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
    unmatched = []          # 长得像数据行、却没解析出月份的行；循环末尾一起抛
    for row in _ROW_RE.findall(m.group(1)):
        cells = [_clean(c) for c in _CELL_RE.findall(row)]
        if len(cells) < 3:
            continue
        mm = _MONTH_RE.match(cells[0])
        if not mm:
            # 表头行 / 说明行本该在这里被安静丢掉。但**后两格都是金额**的行不是
            # 说明行，它就是一行数据，只是首格的月份写法我们没见过。记下来。
            if _num(cells[1]) is not None and _num(cells[2]) is not None:
                unmatched.append(cells[0])
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
    if unmatched:
        raise RuntimeError(
            f"表里有 {len(unmatched)} 行后两格都是金额、首格却不像月份："
            f"{unmatched[:5]!r}——多半是月份写法又变了（脚注号、空格、撇号）。"
            "宁可整次失败也不静默漏月；请对照 cache/msci_aum_latest.html "
            "确认写法后改 _MONTH_RE")

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

    # ② 重述哨兵：不改历史，只喊一声。静默覆盖会让 CSV 与已发布的 PDF 对不上。
    for month in sorted(rows)[-6:]:
        if month not in parsed:
            print(f"[msci] WARN {month} 在 CSV 里但官网表格没有", file=sys.stderr)
            continue
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
