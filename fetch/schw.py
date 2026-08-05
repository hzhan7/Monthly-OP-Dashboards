# -*- coding: utf-8 -*-
"""Charles Schwab (SCHW) —— 月度经营指标抓取模块。

================================ 数据源 ================================
官方只有一个真源：Schwab Monthly Activity Report 随附的 Excel 附表，走 Akamai CDN 直链，
文件名完全可推导，因此不需要爬列表页、不需要登录态、不需要浏览器：

    月报附表   https://content.schwab.com/web/retail/public/about-schwab/excels/
               schw_<mon><yyyy>_table.xlsx        例：schw_may2026_table.xlsx
    月报正文   https://content.schwab.com/web/retail/public/about-schwab/
               schw_<mon><yyyy>_press_release.pdf （本模块不用，留档参考）
    季报附表   https://content.schwab.com/web/retail/public/about-schwab/excels/
               schw_q<n>_<yyyy>_earnings_tables.xlsx  例：schw_q2_2026_earnings_tables.xlsx

<mon> 是小写三字母英文月份缩写（jan…dec），<yyyy> 四位年。

—— 为什么不用别的源 ——
· www.aboutschwab.com（IR 站正文页）在 Akamai 后面，会按 TLS/HTTP2 指纹拦截：
  python urllib 无论带什么 UA/Sec-Fetch 头都是 403，只有真浏览器栈（curl --http2 带全套
  浏览器头也行）能过。所以**不能**把落地页解析放进无人值守主路径。
  content.schwab.com 这个 CDN 域宽松得多：urllib + 普通 Chrome UA 即可 200。
· SEC EDGAR 不是可选源。查过 CIK 0000316709 的全部 8-K：月度经营数据**从不单独 8-K 披露**，
  EDGAR 全文里出现「monthly activity report」的只有季度 8-K Ex-99.1 里的一句提示。
  想靠 EDGAR 拿月度数据是走不通的。
· 新闻稿 PDF 里的数字和 xlsx 完全一致，但 PDF 要 OCR/文本抽取，没必要，xlsx 是结构化的。

================================ 发布节奏 ================================
· 非季末月：次月**第 2 周的周一到周五之间**（历史上多在 12–14 日）发月报，附表当天上线。
· 季末月（3/6/9/12）：**没有独立月报**，对应 URL 直接 404（已实测 mar2026 / jun2026 /
  dec2025 全 404）。季末月的数值有两条路可拿，本模块两条都走：
    (a) 当季**季报附表**的 "ER SMART" 页 —— 季报次月中下旬发（Q2-2026 是 7/21），最快；
    (b) 下一个月报附表的 13 个月滚动表 —— 例如 jul2026 月报的表里会带上 jun2026，
        但要等到 8 月中，比 (a) 慢一个月。
  所以「季末月漏掉」这个坑的正确解法不是特判某几个月，而是：**两个源都抓，取并集**。

================================ 口径坑 ================================
1. **单位在两种文件里不一样**，这是最容易静默算错的地方：
   · 月报附表：客户资产/融资余额已经是 $bn（13135.3），账户数/DATs 已经是千（461 / 11813）。
   · 季报附表：同样的行是**原始单位**（13135300000000 美元 / 490000 个账户 / 13615000 笔）。
   所以不能写死除数。本模块用「基准行反推倍率」：用 Total Client Assets 定金额倍率、用
   Active Brokerage Accounts 定计数倍率，再把倍率套到同一单位块里的其它行，并对结果做
   量级断言。硬编码 /1e9 迟早会在某次版式微调后炸掉。
2. **行标签会变**，不能按行号取数：
   · 2026-02 那期把 "Net Market Gains (Losses)" 写成 "Net Market (Losses) Gains"（词序颠倒）。
   · sheet 名月报是 'SMART'、2019 年的老文件是 'Smart'、季报是 'ER SMART'。
   所以一律按标签前缀 + 大小写无关匹配。
3. **两列是 2026-01 那期才新增的**：Client Daily Average Trades (DATs) 和 Margin Balances
   at month end。同一期把老的 "Average Margin Balances"（月均口径，单位 $mn）删掉了。
   series/schw_avg_margin.csv 就是那条已停更的老序列，它**永远停在 2025-12**，
   本模块绝不去追加它 —— 追加只会把两种口径（月均 vs 月末）混成一条假序列。
   新增的两列在 2026-01 期的 13 个月滚动表里回填到了 2025-01，所以 series 里这两列从
   2025-01 起才有值，这是数据本身的边界，不是解析漏了。
4. **core NNA ≠ NNA**。序列取的是 Core Net New Assets（剔除单笔巨额流入/流出 + 表外
   Schwab Bank Retail CD 流量）。2025 年起「巨额」的门槛从 $10bn 提到 $25bn，
   所以 2025 年前后的 core NNA 严格说不完全可比 —— 这是官方口径变更，不是数据错。
5. 月报附表**不重述历史**：apr2026 与 may2026 两期文件里 12 个重叠月份的数值逐个相同。
   但季报附表口径上是「最终版」，万一和月报打架，本模块以季报为准（见 _SOURCE_RANK）。
6. 2020-10 的 new_brokerage_accounts_k = 14718 是 TD Ameritrade 并表的一次性搬账，
   不是当月开户量。build_schw.py 已经单独处理，这里原样入库、不做清洗。

===================== series/schw_backfill.csv：留着，但不进图 =====================
那个文件是一次做了一半、从未接上的回填：表头承诺 dats_k 与 margin_balances_usdbn 两列，
dats_k 整列是空的，实际只有 2018-12…2024-12 共 7 个年末的月末融资余额。
2026-08-05 专门评估过要不要把它接进 build/schw.py，**结论是不接**，理由按分量排列：

(a) **来历不可复现，而且能证明它不可能来自本管道的源。** cache/schw_may2019_table.xlsx
    （2019 年的月报附表）里逐行查过：整张 Smart 页**没有任何融资余额行**，月均的没有、
    月末的也没有 —— Schwab 是 2020-04 才开始披露月均融资余额（见 schw_avg_margin.csv
    的起点）、2026-01 才开始披露月末融资余额（见上面第 3 条）。所以这 7 个数只可能来自
    10-K / 年报或某个外部源，而文件里没记来源、没记表名、也没有任何 fetch 代码产生它。
    本页在「口径与方法说明」里对读者写的是「无任何估算或补插」，一个连出处都指不出来的
    序列不满足这句话；§5.5「失败要响、绝不静默上线」管的也是同一件事。
(b) **边际信息只有 2 个点。** 2020-12 起的 5 个年末，schw_avg_margin.csv 已经**逐月**
    覆盖（2020-04 → 2025-12），两者逐年只差 -1.7 / -0.9 / +0.3 / +1.8 / +2.3 bn，
    符号正负都有 —— 这正是「月末 vs 月均」的基差噪音，不是新形状。真正新增的只有
    2018-12 (19.3) 与 2019-12 (19.5) 两个点。
(c) **这 2 个新点还落在 TD Ameritrade 并购的另一侧。** 并购 2020-10 完成，
    19.5 → 60.9 是资产负债表搬账不是融资需求，和第 6 条的 14,718k 是同一类假象。
    一张只有 7 个点的图，最抢眼的特征会是这个 3 倍台阶，读者读到的是并购不是杠杆周期。
(d) **年末单点混不进月度轴。** 7 个点之间是 6 段 12 个月的空档，直接塞进 Exhibit 9/12
    会造出 66 个空月并违反 CONTRACT §5.3（不可比的相邻期不得画成连续序列）。
    技术上可以另开一张明确标「year-end snapshot」的图（不与月度点连线），但那张图要用
    (a) 的无源数据、换来 (b) 的 2 个点、再给一个已经背着两条口径警告（core NNA 门槛断点、
    月末 vs 月均不可接续）的页面加上第三条 —— 不划算。

**下次做孤儿文件盘点的人：不要删它。** 它不是残留垃圾，是全仓独一份的 2018–2024 年末
月末融资余额，管道抓不回来（见 (a)），删了就永久丢失。它的正确用途是**离线核对**：
比如想验证某年年末的月末余额、或者判断月均序列与月末序列的基差量级时，手工翻它。
要让它有资格进图，得先补齐两件事 —— 在文件里写清每个数出自哪份 10-K/年报的哪张表，
并在 fetch 侧写出可复现的抓取路径；在那之前它只能停在 series/ 里当参考料。

================================ 落盘 ================================
所有下载文件只写 cache/（已 gitignore），文件名与官方一致，便于事后复核。
"""
from __future__ import annotations

import csv
import datetime as _dt
import os
import re
import urllib.error
import urllib.request

import openpyxl

# ── 常量 ────────────────────────────────────────────────────────────────
CDN = 'https://content.schwab.com/web/retail/public/about-schwab'
MONTHLY_URL = CDN + '/excels/schw_{mon}{year}_table.xlsx'
QUARTER_URL = CDN + '/excels/schw_q{q}_{year}_earnings_tables.xlsx'
IR_PAGE = 'https://www.aboutschwab.com/financial-reports'

# CDN 只看 UA，给个普通 Chrome UA 就放行；不带 UA 或带 Python-urllib 会 403。
_UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
       '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36')

_MON = ['jan', 'feb', 'mar', 'apr', 'may', 'jun',
        'jul', 'aug', 'sep', 'oct', 'nov', 'dec']

SERIES = 'schw.csv'
COLS = ['core_nna_usdbn', 'total_client_assets_usdbn',
        'new_brokerage_accounts_k', 'dats_k', 'margin_balances_usdbn']

# 标签前缀（小写、去空白后前缀匹配）。用前缀而不是全等，是因为官方在标签尾部挂脚注号，
# 脚注号每期都在变（"(1,2)" → "(1,2,3)"），全等匹配必挂。
_LABEL = {
    'core_nna_usdbn':           'core net new assets',
    'total_client_assets_usdbn': 'total client assets',
    'new_brokerage_accounts_k': 'new brokerage accounts',
    'dats_k':                   'client daily average trades',
    'margin_balances_usdbn':    'margin balances at month end',
    # 下面两行只用来定单位倍率，不入库
    '_anchor_money':            'total client assets',
    '_anchor_count':            'active brokerage accounts',
}
# 金额类 / 计数类分组：决定用哪个锚点行的倍率
_MONEY = {'core_nna_usdbn', 'total_client_assets_usdbn', 'margin_balances_usdbn'}
_COUNT = {'new_brokerage_accounts_k', 'dats_k'}

# 合理量级断言。core NNA 会是负数、也可能接近 0（2019-04 是 -0.3），无法用量级判，
# 所以它不做独立断言，只跟着锚点倍率走。
_SANE = {
    'total_client_assets_usdbn': (1_000.0, 100_000.0),    # $1tn – $100tn
    'margin_balances_usdbn':     (1.0, 5_000.0),          # $bn
    'new_brokerage_accounts_k':  (10.0, 100_000.0),       # 千（含 2020-10 那个 14718）
    'dats_k':                    (100.0, 1_000_000.0),    # 千笔/日
    '_anchor_count':             (5_000.0, 500_000.0),    # 千个活跃账户
}

# DATs 与月末融资余额自 2026-01 期起披露，回填到 2025-01。比这更早的月份这两列本就没有。
_DATS_MARGIN_FROM = (2025, 1)

# 同一个月同时来自月报和季报时谁说了算：季报是最终版。
_SOURCE_RANK = {'monthly': 0, 'quarterly': 1}


class FetchError(RuntimeError):
    """抓不到 / 解析不出 / 缺列，一律抛这个，绝不静默降级。"""


# ── HTTP ───────────────────────────────────────────────────────────────
def _get(url: str, timeout: int = 60) -> bytes | None:
    """404 返回 None（季末月月报本来就不存在，属正常）；其它错误抛异常。"""
    req = urllib.request.Request(url, headers={'User-Agent': _UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise FetchError(f'HTTP {e.code} on {url}') from e
    except Exception as e:                      # 网络层问题必须炸出来，不能当没数据
        raise FetchError(f'{type(e).__name__} on {url}: {e}') from e


def _download(url: str, cache_dir: str, reuse: bool = True) -> str | None:
    """下载到 cache/，返回本地路径；404 返回 None。

    reuse=True 时复用已落盘的文件。老月份的附表官方从不重发（已核对 apr/may 两期 12 个
    重叠月逐值相同），复用是安全的；但**最近两个月的文件可能被官方重新上传更正**，
    所以调用方对新文件传 reuse=False，强制重取。
    """
    os.makedirs(cache_dir, exist_ok=True)
    path = os.path.join(cache_dir, url.rsplit('/', 1)[-1])
    if reuse and os.path.exists(path) and os.path.getsize(path) > 10_000:
        return path
    blob = _get(url)
    if blob is None:
        return None
    if len(blob) < 10_000 or blob[:2] != b'PK':   # xlsx 是 zip，PK 开头
        raise FetchError(f'{url} 返回的不是 xlsx（{len(blob)} bytes）')
    with open(path, 'wb') as f:
        f.write(blob)
    return path


def _ir_page_links(cache_dir: str) -> list[str]:
    """兜底诊断用：万一 CDN 命名规则变了，从 IR 落地页把真实链接捞出来。

    www.aboutschwab.com 拦 urllib（Akamai 按 TLS 指纹拦），只能借 curl 的 HTTP/2 栈，
    所以这条路**不进主流程**，只在主流程全 404 时被 update() 调用来生成有用的报错。
    """
    import subprocess
    hdr = [
        '-H', 'User-Agent: ' + _UA,
        '-H', 'Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        '-H', 'Accept-Language: en-US,en;q=0.9',
        '-H', 'Sec-Fetch-Dest: document', '-H', 'Sec-Fetch-Mode: navigate',
        '-H', 'Sec-Fetch-Site: none', '-H', 'Sec-Fetch-User: ?1',
        '-H', 'Upgrade-Insecure-Requests: 1',
    ]
    try:
        out = subprocess.run(['curl', '-sSL', '--compressed', '--http2', *hdr, IR_PAGE],
                             capture_output=True, timeout=90).stdout.decode('utf-8', 'replace')
    except Exception:
        return []
    with open(os.path.join(cache_dir, '_schw_ir_financial_reports.html'), 'w') as f:
        f.write(out)
    return sorted(set(re.findall(r'https://content\.schwab\.com/[^"\']+\.xlsx', out)))


# ── 解析 ───────────────────────────────────────────────────────────────
def _sheet(wb):
    for name in wb.sheetnames:
        if name.strip().lower().endswith('smart'):     # 'SMART' / 'Smart' / 'ER SMART'
            return wb[name]
    raise FetchError(f'找不到 SMART 页，sheet 有：{wb.sheetnames}')


def _month_columns(ws, report_ym: tuple[int, int]) -> dict[tuple[int, int], int]:
    """定位 13 个月滚动表的列。

    不信任表头上方那行稀疏的年份标签（它只在每年第一列出现，一次版式微调就会错位），
    改成：找到月份缩写那一行，认定**最右一个数据列就是报告月**，然后按月倒推。
    倒推完再和表里写的月份缩写逐个核对，对不上直接抛 —— 这样版式变了会立刻炸，
    而不是悄悄把数据错位一格。
    """
    abbr = {m: i + 1 for i, m in enumerate(_MON)}
    hdr_row = hdr_cols = None
    for row in ws.iter_rows(min_row=1, max_row=15):
        cols = [(c.column, str(c.value).strip().lower()[:3]) for c in row
                if isinstance(c.value, str) and str(c.value).strip().lower()[:3] in abbr]
        if len(cols) >= 6:
            hdr_row, hdr_cols = row[0].row, cols
            break
    if hdr_cols is None:
        raise FetchError('找不到月份表头行')

    y, m = report_ym
    out: dict[tuple[int, int], int] = {}
    for k, (col, tag) in enumerate(reversed(hdr_cols)):     # 从最右（=报告月）往左
        yy, mm = y, m - k
        while mm <= 0:
            mm += 12
            yy -= 1
        if abbr[tag] != mm:
            raise FetchError(
                f'表头月份与报告月对不上：第 {hdr_row} 行第 {col} 列写的是 {tag}，'
                f'按报告月 {y}-{m:02d} 倒推应为 {mm:02d}。版式可能变了，人工核对后再跑。')
        out[(yy, mm)] = col
    return out


def _row_values(ws, prefix: str, cols: dict) -> dict | None:
    """按标签前缀找行，返回 {(y,m): 原始数值}；找不到该行返回 None。"""
    for row in ws.iter_rows(min_row=1, max_row=ws.max_row):
        lab = row[0].value
        if not isinstance(lab, str):
            continue
        lab = re.sub(r'\s+', ' ', lab).strip().lower()
        if not lab.startswith(prefix):
            continue
        vals = {}
        for ym, col in cols.items():
            v = ws.cell(row=row[0].row, column=col).value
            if isinstance(v, (int, float)):
                vals[ym] = float(v)
        if vals:
            return vals
    return None


def _scale(anchor: dict, lo: float, hi: float, what: str) -> float:
    """用锚点行反推单位倍率。候选只有 1 / 1e-3 / 1e-6 / 1e-9 四档，
    要求**所有**锚点值套上倍率后都落进合理区间，且只有一档满足 —— 有歧义就抛。"""
    ok = [s for s in (1.0, 1e-3, 1e-6, 1e-9)
          if all(lo <= abs(v) * s <= hi for v in anchor.values())]
    if len(ok) != 1:
        raise FetchError(f'{what} 单位倍率判不定（候选 {ok}，样值 {list(anchor.values())[:3]}）')
    return ok[0]


def parse_table(path: str, report_ym: tuple[int, int]) -> dict:
    """把一个 xlsx 解析成 {(year, month): {列名: 值}}。缺关键行直接抛。"""
    ws = _sheet(openpyxl.load_workbook(path, data_only=True, read_only=False))
    cols = _month_columns(ws, report_ym)

    a_money = _row_values(ws, _LABEL['_anchor_money'], cols)
    a_count = _row_values(ws, _LABEL['_anchor_count'], cols)
    if not a_money or not a_count:
        raise FetchError(f'{os.path.basename(path)}: 找不到单位锚点行')
    s_money = _scale(a_money, *_SANE['total_client_assets_usdbn'], 'money')
    s_count = _scale(a_count, *_SANE['_anchor_count'], 'count')

    raw = {c: _row_values(ws, _LABEL[c], cols) for c in COLS}
    out: dict[tuple[int, int], dict] = {ym: {} for ym in cols}
    for c in COLS:
        if raw[c] is None:
            continue
        s = s_money if c in _MONEY else s_count
        for ym, v in raw[c].items():
            x = v * s
            lo_hi = _SANE.get(c)
            if lo_hi and not (lo_hi[0] <= abs(x) <= lo_hi[1]):
                raise FetchError(f'{os.path.basename(path)} {ym} {c}={x} 超出合理区间 {lo_hi}')
            out[ym][c] = round(x, 6)
    return out


def _required(ym: tuple[int, int]) -> list[str]:
    """该月**必须**解析出来的列。缺任何一列 → 抛，绝不写 NaN。"""
    if ym >= _DATS_MARGIN_FROM:
        return list(COLS)
    return [c for c in COLS if c not in ('dats_k', 'margin_balances_usdbn')]


# ── 源枚举 ─────────────────────────────────────────────────────────────
def _today_ym() -> tuple[int, int]:
    t = _dt.date.today()
    return (t.year, t.month)


def _shift(ym: tuple[int, int], k: int) -> tuple[int, int]:
    y, m = ym
    m += k
    while m <= 0:
        m += 12
        y -= 1
    while m > 12:
        m -= 12
        y += 1
    return (y, m)


def _candidates(back: int = 8):
    """按时间倒序给出待探的 (kind, url, report_ym)。

    月报探最近 back 个月；季报探最近 3 个季度。都探是因为季末月只有季报有，
    而季报又比「下一期月报」早一个月出来。
    """
    y, m = _today_ym()
    for k in range(back):
        yy, mm = _shift((y, m), -k)
        if mm % 3 == 0:          # 季末月没有独立月报，别浪费一次请求
            continue
        yield 'monthly', MONTHLY_URL.format(mon=_MON[mm - 1], year=yy), (yy, mm)
    q = (m - 1) // 3 + 1
    for k in range(3):
        qq, yy = q - k, y
        while qq <= 0:
            qq += 4
            yy -= 1
        yield 'quarterly', QUARTER_URL.format(q=qq, year=yy), (yy, qq * 3)


RESTATEMENTS: list = []      # 上一次 _collect 发现的跨源/跨期数值打架，供调用方审计


def _collect(cache_dir: str, back: int = 8) -> dict:
    """下载 + 解析所有能拿到的源，合并成 {(y,m): {col: val}}。

    _candidates 是「新→旧」序，所以合并规则是：**先写者胜**（越新的文件越权威），
    唯一的例外是季报——季报是该季末月的最终版，rank 更高，可以覆盖月报的同月值。
    覆盖时如果新旧值不等，说明官方重述了，记进 RESTATEMENTS 让人看得见，不静默吞掉。
    """
    merged: dict[tuple[int, int], dict] = {}
    origin: dict[tuple[int, int], str] = {}
    RESTATEMENTS.clear()
    got = False
    for kind, url, ym in _candidates(back):
        fresh = ym >= _shift(_today_ym(), -2)          # 最近两个月的文件不吃缓存
        path = _download(url, cache_dir, reuse=not fresh)
        if path is None:
            continue
        got = True
        for m_ym, vals in parse_table(path, ym).items():
            prev_rank = _SOURCE_RANK.get(origin.get(m_ym), -1)
            slot = merged.setdefault(m_ym, {})
            for c, v in vals.items():
                if c in slot:
                    if abs(slot[c] - v) > 1e-6:
                        RESTATEMENTS.append((m_ym, c, slot[c], v, os.path.basename(path)))
                    if _SOURCE_RANK[kind] <= prev_rank:
                        continue                       # 先写者胜
                slot[c] = v
            if _SOURCE_RANK[kind] > prev_rank:
                origin[m_ym] = kind
            else:
                origin.setdefault(m_ym, kind)
    if not got:
        links = _ir_page_links(cache_dir)
        raise FetchError(
            '最近 %d 个月的月报附表和最近 3 个季度的季报附表全部 404。'
            'CDN 命名规则可能变了。IR 落地页上当前的 xlsx 链接：%s'
            % (back, links[:10] or '（落地页也取不到）'))
    return merged


# ── 对外接口 ───────────────────────────────────────────────────────────
def latest_month(cache_dir) -> str | None:
    """官方源当前最新月，"YYYY-MM"。抓不到抛 FetchError。"""
    data = _collect(cache_dir)
    ok = [ym for ym, v in data.items() if all(c in v for c in _required(ym))]
    if not ok:
        raise FetchError('源文件解析出来了，但没有任何一个月凑齐必需列')
    y, m = max(ok)
    return f'{y:04d}-{m:02d}'


def _fmt(col: str, v) -> str:
    if v is None:
        return ''
    if col in ('new_brokerage_accounts_k', 'dats_k'):
        return str(int(round(v)))
    s = f'{round(v, 1):.1f}'
    return s


def update(series_dir, cache_dir) -> list:
    """把新月份追加进 series/schw.csv，返回新增月份 ["YYYY-MM", ...]。

    幂等：已存在的月份一律跳过（不覆盖、不重排、不改动已有行的任何字符）。
    """
    path = os.path.join(series_dir, SERIES)
    with open(path, newline='') as f:
        rows = list(csv.reader(f))
    header, body = rows[0], [r for r in rows[1:] if r and r[0].strip()]
    if header != ['month'] + COLS:
        raise FetchError(f'{SERIES} 列名与预期不符：{header}')
    have = {r[0] for r in body}

    data = _collect(cache_dir)
    added = []
    for ym in sorted(data):
        key = f'{ym[0]:04d}-{ym[1]:02d}'
        if key in have:
            continue
        vals = data[ym]
        missing = [c for c in _required(ym) if c not in vals]
        if missing:
            raise FetchError(f'{key} 解析结果缺列 {missing}，拒绝写入（不写 NaN）')
        body.append([key] + [_fmt(c, vals.get(c)) for c in COLS])
        added.append(key)

    if not added:
        return []
    body.sort(key=lambda r: r[0])
    tmp = path + '.tmp'
    with open(tmp, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(body)
    os.replace(tmp, path)
    return added


if __name__ == '__main__':
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    print('latest_month:', latest_month(os.path.join(_root, 'cache')))
    print('update      :', update(os.path.join(_root, 'series'), os.path.join(_root, 'cache')))
    if RESTATEMENTS:
        print('官方重述（人工确认后再信新值）:')
        for r in RESTATEMENTS:
            print('  ', r)
