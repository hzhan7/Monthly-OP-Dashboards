# -*- coding: utf-8 -*-
"""IBKR 官方 PDF 的下载与解析管道。

**本文件搬自 `~/.claude/skills` 下的 `IBKR月度指标/build_report.py`，原 skill 已删除。**
逐字复制该文件里被本仓库引用的部分（`UA` / `HIST_URL` / `PR_URL` / `curl` /
`LABELS` / `parse_hist_page` / `parse_pr`），注释一并保留 —— 那些注释记录的是
踩过的坑，不是装饰。skill 里出 PDF 的那一半（matplotlib 绘图、GS 版式排版、
OneDrive 落盘、`main()`）本仓库用不上，没有搬。

调用方：
  · `fetch/ibkr.py`  —— curl / HIST_URL / PR_URL / parse_hist_page / LABELS
  · `build/ibkr.py`  —— parse_pr（月度新闻稿的佣金与订单规模）、
                        parse_pr_fut_fee（期货费用占比，页尾脚注用）

`parse_pr_fut_fee` 是**本仓后加的**，原 skill 里没有；加在这里而不是 build/ 侧，
是为了让「新闻稿怎么解析」始终只有一处定义。

**`parse_hist_page` 已不再是逐字复制件**：原版「一路收数字、按页脚有没有 '% Change'
砍掉两格」的写法在一格读不出来时会静默截断整行，截在 `US Trading days` 上就是 IBKR
永久停更而日志天天报 NOCHANGE。现在列数改由表头推、并加了逐页行长对账与交易日数
范围检查，对不上抛 `IbkrParseError`。原因写在 `parse_hist_page` 与各常量的注释里，
别按「跟 skill 原版对齐」的理由改回去。取数口径一格没动。

两边都用 `spec_from_file_location` 按路径加载本文件：`fetch/` 与 `build/` 都不在
sys.path 上（monthly_run.py 用 spec 加载 fetch 模块、用子进程跑 build 脚本），
裸 `import ibkr_source` 在 fetch 侧会 ModuleNotFoundError。

缓存目录 `cache/ibkr/`（gitignored）由本模块定义，fetch 与 build 共用同一个常量 ——
两边各写各的路径正是「fetch 下到 A、build 去 B 找」这类空转的来源。
"""
import collections
import os
import re
import subprocess

import fitz

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
# 原 skill 的 cache/ 整个搬到这里（hist_latest.pdf + 各月 pr_YYYYMM.pdf）。
# 历史新闻稿是一月一个文件、且部分月份的链接未必还在，丢了就补不回来。
CACHE = os.path.join(ROOT, 'cache', 'ibkr')

UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36'
HIST_URL = 'https://www.interactivebrokers.com/mkt/getFileNew.php?file=latestMetric'
PR_URL = 'https://www.interactivebrokers.com/mkt/getFileNew.php?file={ym}MetricsPressRelease.pdf'


# ---------------- download helpers ----------------
def curl(url, dest):
    """下到临时文件 → 验过 → 才改名到 dest。**失败绝不碰 dest 已有的内容。**

    以前是直接 `curl -o dest`，失败只抛异常不清理，于是磁盘上留下一个 0 字节残骸；
    而下游（fetch/ibkr.py 与 build/ibkr.py）都用 `os.path.exists(...)` 判断「缓存在不在」，
    残骸存在就等于「已经有了」→ **永不重试**。一次瞬时 404 之后 IBKR 会永久停在旧月份，
    而调度器每天读到的都是 NOTHING_TO_DO。

    但「失败就删 dest」同样是错的：hist_latest.pdf 每次都要重下，网络抖一下就会把
    上一次成功的缓存也删掉，等于把一次瞬时故障升级成数据丢失。所以走临时文件 + 原子改名：
    成功才替换，失败时 dest 保持原样（新鲜度由调用方按内容判断，不靠文件在不在）。
    """
    tmp = dest + '.part'
    try:
        r = subprocess.run(['curl', '-sL', '--retry', '3', '--max-time', '120',
                            '-A', UA, '-o', tmp, url])
        ok = (r.returncode == 0 and os.path.exists(tmp) and os.path.getsize(tmp) >= 5000)
        if ok:
            with open(tmp, 'rb') as f:
                blob = f.read()
            if not blob.startswith(b'%PDF'):
                # IBKR 这个端点会（至少 2026-08 起）把 PDF 包在一个 Java 序列化的
                # javax.sql.rowset.serial.SerialBlob 里吐出来：HTTP 200、
                # Content-Type 仍是 application/pdf，只是前面多了 147 字节的序列化头。
                # 实测 2026-08-03 那期是 147 字节头 + 138536 字节完整 PDF。
                # 只判大小的老写法会把整坨写进缓存，然后 fitz.open 崩在别处 ——
                # 报错点离病因十万八千里。这里直接把内层 PDF 抠出来。
                i, j = blob.find(b'%PDF'), blob.rfind(b'%%EOF')
                if i >= 0 and j > i:
                    blob = blob[i:j + 5]
                    with open(tmp, 'wb') as f:
                        f.write(blob)
                else:
                    ok = False                      # 真不是 PDF：拦截页 / 错误页
        if not ok:
            raise RuntimeError(f'download failed (not a PDF): {url}')
        os.replace(tmp, dest)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


# ---------------- parse historical metrics PDF ----------------
LABELS = [
    ('trading_days',  r'US Trading days'),
    ('accounts',      r'Total Accounts'),
    ('net_new',       r'Net New Accounts'),
    ('darts',         r'Total Client DARTs'),
    ('ann_dart_acct', r'Cleared Avg\. DART per Account'),
    ('opt_contracts', r'Options Contracts'),
    ('fut_contracts', r'Futures Contracts'),
    ('stk_shares',    r'Stock Shares'),
    ('equity',        r'Client Equity'),
    ('credits',       r'Client Credits\(\d\)'),
    ('margin',        r'Client Margin Loans'),
]


class IbkrParseError(RuntimeError):
    """历史指标表**对不上账**时抛它。

    继承 RuntimeError 而不是另起一支：本文件原有的失败路径（`curl` / `parse_pr`）
    抛的都是 RuntimeError，既有的 except 照旧接得住。单独起个名字只为让
    monthly_run.py 那行 `FAIL <类名>: <消息前 120 字>` 一眼看出是**解析对账**挂了，
    而不是网络挂了 —— 两者的处置完全不同（前者要人去看 PDF，后者等下一轮就好）。
    """


# ── 表头：判断「这一行该有几格」的独立外部判据 ──
# 原来的写法是「一路收数字，最后按页脚有没有 '% Change' 砍掉两格」，两处都不牢靠：
#   · 数字串**一格读不出来就整行从那里断掉**。这张表本来就带脚注号 (1)(2)(3)，
#     而且编号逐年重排（当年页用 (1)(2)、上一年页用 (1)(2)(3)），哪天挂到某个数字
#     格上（'22.0(4)'、'22.0*'）或某格印成 'N/A'，那一格右边的月份就**全没了**。
#   · 断在 `US Trading days` 行最要命：fetch/ibkr.py::_hist 拿这一行当「这个月有没有
#     数」的唯一闸门，最新月被切掉就等于被当成「未来月份的空格」，update() 干干净净
#     返回 NOCHANGE，红点与断档检查一个都够不着 —— 连续十天这样和连续十天正常，
#     日志里长得一模一样（README 第四类）。
# 所以列数改由这一页自己印的表头说了算：'Jan'…'Dec' 这段表头与数字解析器互相独立，
# 数字那边坏掉时它不会跟着坏，正是 fetch/cboe.py::_crosscheck_report_month 那个形状。
_MONTH_HEADERS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

# 认表头至少要连对这么多个月。当年页也印满十二个月（只是右边几格没数），
# 所以今天永远是 12；容忍更短是留给「IBKR 改成只印已发布月份」那种排版调整，
# 免得一次无害的改版把整轮 FAIL 掉。低于这个数就不算表头 —— 正文里偶然出现一个
# 'Jan' 不该被当成表头。
MIN_MONTH_HEADERS = 3

# 'Dec' 之后、第一行指标标签之前剩几格就是几列摘要（2026-08 实测：当年页两格
# 'Pr Mo' / 'Pr Yr'，往年页一格没有）。**不写死 2**：写死就等于把「页脚那句
# '% Change' 一个字都不许改」变成隐含前提，而它改名的后果是静默算错——
# 两格百分比会顺位变成第 8、第 9 个月被写进 series，且 update() 只追加、永不改写。
MAX_SUMMARY_COLS = 4

# 美国一个自然月的交易日数。series/ibkr.csv 里 2016-01 至今 127 个月实测落在
# 18.5–23.0（半日休市出现 .5），日历上限本就是 23 个工作日。
# 放宽到 15–25 是**刻意留的余量**：2001-09 那种全市场停市一周会把月度交易日压到 15，
# 那种月份不该让抓取失败。这道范围不是用来挑剔小数的，它挡的是「摘要格被当成月份
# 读进来」——那时这一格会是 5.0 或 2.0（百分比），数字看着人模人样，落进 series 就
# 再也改不回来了。
TRADING_DAYS_MIN, TRADING_DAYS_MAX = 15.0, 25.0

# 数字格的**词形**容错：只把装饰摘掉再 float()，口径一格不放宽。
# 同 fetch/axp.py::_series_excess_spread docstring 里那条思路 —— 正则只认识已经见过的
# 写法，所以宁可让它多认几种，也不要让一个没见过的脚注号把半行数据吃掉。
_ORNAMENT = r'(?:\s*\(\d+\)|\s*\*+|[¹²³⁰-⁹]+)'
_NUM_RE = re.compile(r'^\$?-?[\d,]+(?:\.\d+)?%?' + _ORNAMENT + r'?$')
_ORNAMENT_TAIL = re.compile(_ORNAMENT + r'$')

# 印成横杠 / N/A 的空格。**它是「这一格没有值」，不是「这一行到此为止」**——
# 当成结束会把它右边的整段月份一起丢掉，那正是本文件要防的静默失联。
# 记成 None 则位置还在，缺的月份会在 fetch/ibkr.py::update() 的「缺列一律失败」处出声。
_BLANK_CELLS = {'-', '–', '—', '−', 'N/A', 'NA', 'n/a', 'n.a.'}

_NOT_A_CELL = object()          # 「这一行压根不是数据格」的哨兵，与「空格」区分开


def _strip_ornament(s):
    """摘掉尾部脚注号 / 星号 / 上标，留下正文。表头与数字格共用。"""
    return _ORNAMENT_TAIL.sub('', s).strip()


def _cell(s):
    """一格文本 → float；空占位格 → None；根本不是数据格 → `_NOT_A_CELL`。"""
    if s in _BLANK_CELLS:
        return None
    if not _NUM_RE.match(s):
        return _NOT_A_CELL
    return float(_strip_ornament(s).replace('$', '').replace(',', '').replace('%', ''))


def _label_at(line):
    """这一行是不是某个指标的标签行；是就返回它的键，不是返回 None。"""
    for key, pat in LABELS:
        if re.match(pat, line):
            return key
    return None


def _page_layout(lines):
    """按表头定位这一页的列结构，返回 `(月份列数, 摘要列数)`。

    找不到月份表头返回 `(None, None)`；表头找到了、后面却接不上任何一行指标标签，
    返回 `(月份列数, None)`。两种情况的处置不同，交给 `parse_hist_page` 决定 ——
    这里只负责看，不负责判。
    """
    for i in range(len(lines)):
        n = 0
        while (n < len(_MONTH_HEADERS) and i + n < len(lines)
               and _strip_ornament(lines[i + n]) == _MONTH_HEADERS[n]):
            n += 1
        if n < MIN_MONTH_HEADERS:
            continue
        for k in range(i + n, min(i + n + MAX_SUMMARY_COLS + 1, len(lines))):
            if _label_at(lines[k]) is not None:
                return n, k - (i + n)
        return n, None
    return None, None


def _row_values(lines, idx, width):
    """从标签行 `idx` 往下收这一行的数字格，最多收 `width` 格（`None` = 不设上限）。

    上限来自表头，专治「最后一行把页脚年份也吃进去」：往年页没有 Notes 段，
    `Client Margin Loans` 的数字串会一路收到页脚的 '2023' —— 实测 2016–2023 八页
    每页都多一格。多出来的那格今天不影响取数（按月份下标读，读不到第 13 格），
    但它让「行长」这个判据失去意义，而下面的对账正要靠行长。
    """
    j = idx + 1
    while j < len(lines) and not isinstance(_cell(lines[j]), float):
        j += 1                      # 空占位格不许起头，否则整行会整体右移一格
    vals = []
    while j < len(lines) and (width is None or len(vals) < width):
        v = _cell(lines[j])
        if v is _NOT_A_CELL:
            break
        vals.append(v)
        j += 1
    while vals and vals[-1] is None:
        vals.pop()                  # 行尾的空占位格不算数据列（当年页右边那几个月）
    return vals


def parse_hist_page(page):
    """把一页历史指标表解析成 `(年份, {指标键: [逐月值]})`。

    三道护栏，都是冲着「解析漏了却没人知道」那一类失败去的（README 第四类）：
      ① 列数按**表头**算，不再靠页脚那句 '% Change' 猜；数字格容忍脚注号与空占位格。
      ② **同页行长对账**：任何一行都不许短过 `US Trading days`，`US Trading days`
         也不许短过本页的众数行长。这是真正兜住「最新月被静默切掉」的那道网。
      ③ `US Trading days` 的取值必须落在一个月合理的交易日数区间内。
    对不上一律抛 `IbkrParseError`：宁可整轮 FAIL，也不要一个干干净净的 NOCHANGE。

    ⚠ 对账**必须逐页做、且不能要求各行严格等长**。这张 PDF 今天就不是齐的：当年页
    比往年页少一段（只印到已发布的月份，且多两格摘要列），往年页最后一行还会多吃一格
    页脚年份（已由 `_row_values` 的上限削掉）。要求「全页各行等长」会在**今天、
    完全正常的输入**上每天 FAIL 八页 —— 那比它要修的漏数据更糟。
    """
    text = page.get_text()
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    years = [int(l) for l in lines if re.fullmatch(r'20\d{2}', l)]
    year = max(years) if years else None

    n_months, n_summary = _page_layout(lines)
    cap = None if (n_months is None or n_summary is None) else n_months + n_summary

    out = {}
    for key, pat in LABELS:
        idx = next((j for j, l in enumerate(lines) if re.match(pat, l)), None)
        if idx is None:
            out[key] = []
            continue
        vals = _row_values(lines, idx, cap)
        if n_summary and len(vals) >= n_summary:
            vals = vals[:-n_summary]
        out[key] = vals

    found = {k: v for k, v in out.items() if v}
    if not found:
        # 整页一行指标数据都没有 —— 封面页 / 纯说明页就长这样，_hist 会自然跳过。
        # 这里**不抛**：抛了就等于 IBKR 哪天在 PDF 前面加一页封面，整轮跟着 FAIL。
        return year, out

    if n_months is None:
        raise IbkrParseError(
            f'历史表某页有 {len(found)} 行指标数据、却找不到 Jan…Dec 表头，'
            f'列结构变了，本次拒绝解析；请看 cache/ibkr/hist_latest.pdf')
    if n_summary is None:
        raise IbkrParseError(
            f'历史表 {year} 页月份表头之后 {MAX_SUMMARY_COLS} 格内没有任何指标标签，'
            f'摘要列变多或标签改名了；请看 cache/ibkr/hist_latest.pdf')

    td = out.get('trading_days') or []
    if not td:
        raise IbkrParseError(
            f'历史表 {year} 页有 {len(found)} 行指标数据、却读不到 US Trading days —— '
            f'_hist 拿这一行当「这个月有没有数」的唯一闸门，读不到等于整页静默消失')

    # 众数行长，不是最大值也不是「全体相等」：见本函数 docstring 里那条 ⚠。
    lens = [len(v) for v in found.values()]
    width = collections.Counter(lens).most_common(1)[0][0]
    if len(td) < width:
        raise IbkrParseError(
            f'历史表 {year} 页 US Trading days 只有 {len(td)} 格、同页多数行 {width} 格，'
            f'这一行被截断了（多半是某格挂了没见过的脚注号），最新月会被静默丢掉')
    short = sorted(k for k, v in found.items() if len(v) < len(td))
    if short:
        # 诊断写在最前面：monthly_run.py 的 FAIL 行只印消息的前 120 字，
        # 把行名列表放前面会把「为什么挂」挤掉，只剩一串键名。
        raise IbkrParseError(
            f'历史表 {year} 页有 {len(short)} 行短过 US Trading days（{len(td)} 格），'
            f'被截断了、缺的格子会静默写成空值：{short}')

    if any(v is None for v in td):
        # 空格出现在行中间（行尾的已被 `_row_values` 削掉）。这一格是空，
        # _hist 就把那个月整月跳过 —— 序列里留一个洞，而洞是不出声的。
        raise IbkrParseError(
            f'历史表 {year} 页 US Trading days 第 {td.index(None) + 1} 格是空的，'
            f'那个月会被整月跳过；请看 cache/ibkr/hist_latest.pdf 确认是不是印成了横杠/N/A')
    bad = [v for v in td if not TRADING_DAYS_MIN <= v <= TRADING_DAYS_MAX]
    if bad:
        raise IbkrParseError(
            f'历史表 {year} 页 US Trading days 出现 {bad[:3]}，不在一个月合理的 '
            f'{TRADING_DAYS_MIN}–{TRADING_DAYS_MAX} 天内，八成是摘要列被当成月份读进来了')
    return year, out


# ---------------- parse press release ----------------
def parse_pr(path):
    t = fitz.open(path)[0].get_text()
    mo = re.search(r'Average commission per cleared Commissionable Order.*?of \$([\d.]+)', t, re.S)
    mk = re.search(r'Stocks\s*\n([\d,.]+)\s*shares?\s*\n\$([\d.]+)\s*\nEquity Options\s*\n([\d.]+)\s*contracts\s*\n\$([\d.]+)\s*\nFutures\s*\n([\d.]+)\s*contracts\s*\n\$([\d.]+)', t)
    if not (mo and mk):
        raise RuntimeError(f'PR parse failed: {path}')
    return (float(mo.group(1)), float(mk.group(1).replace(',', '')), float(mk.group(2)),
            float(mk.group(3)), float(mk.group(4)), float(mk.group(5)), float(mk.group(6)))


# 「We estimate exchange, clearing and regulatory fees to be NN% of the futures commissions.」
# PDF 抽文本时这句被换行拆开（"… to be 54% of the \nfutures commissions."），故 \s+ 跨行。
FUT_FEE_RE = re.compile(r'fees to be\s+(\d+(?:\.\d+)?)\s*%\s+of the\s+futures commissions', re.I)


def parse_pr_fut_fee(path):
    """新闻稿里「交易所／清算／监管费用占期货佣金」的百分比。命中返回 float，没有返回 None。

    ⚠ **这个比例逐月披露、每月都在动**（本地缓存的十几份稿子跨了好几个百分点），
    任何地方都不许写死一个常数 —— build/ibkr.py 页尾脚注原先写死的「56%」正是这么
    与目标月（那期披露的是 54%）对不上的。

    单独成函数、不并进 `parse_pr` 的返回元组：那个元组按位置解包、已有调用方在用；
    而这一句只喂页尾脚注，缺了不该让整个月度构建挂掉，所以命中失败返回 None 而不 raise。
    放在本文件是因为**「新闻稿怎么解析」只能有一处定义**（同 parse_pr 的理由）。
    """
    m = FUT_FEE_RE.search(fitz.open(path)[0].get_text())
    return float(m.group(1)) if m else None
