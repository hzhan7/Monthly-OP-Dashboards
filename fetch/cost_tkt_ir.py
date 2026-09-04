# -*- coding: utf-8 -*-
"""Costco 客单/客流 —— IR 站补充资料 deck 的**一次性历史回填**（FY24Q1 / FY24Q2）。

═══ 为什么是「一次性」而不是接进 fetch/cost_sec.py 的 update() ═══
`series/cost_tkt_q.csv` 由 cost_sec.build_tkt_q 供给，而 `cost_sec._write`（fetch/cost_sec.py:1526）
是**整表重写**：每轮把解析结果全量覆盖回文件。也就是说，任何手工加进那张 CSV 的行，
下一次 `python fetch/cost_sec.py` 跑完就没了 —— 而且是静默没的，不报错。
所以回填必须落在**另一张 fetch 永不写的 CSV** 上：`series/cost_tkt_q_ir.csv`。

那为什么不干脆把 IR deck 也接进 cost_sec 的常规抓取？因为这两份 deck 是**已经封闭的历史**：
FY24Q1/FY24Q2 的数字 2024 年就定死了，IR 站不会再改（改了就是新文件、新 URL）。
一件抓一次、落盘、提交进版本库，此后永久有效；每月再去 IR 站重抓一遍同样两份 PDF
（各 4MB）只是白白多打请求、还给自己新增一个「IR 站改版就整轮 FAIL」的脆弱点。
本脚本因此是「跑一次、把结果提交、以后基本不用再跑」的性质，跟 fetch/ 下其余每月跑的模块不同。

═══ 为什么只回填这两季 ═══
带 Sales/Ticket/Traffic 分部表的更早 deck，实测只存在四份：
    FY22Q4 (2022-08-28)、FY23Q1 (2022-12)、FY24Q1 (2023-11-26)、FY24Q2 (2024-02-18)
**FY23Q2 / FY23Q3 / FY23Q4 三季遍寻不得**（IR feed 里没有、CDN 上也没扫到带这张表的件）。
接上 FY22Q4+FY23Q1 会让序列长成「FY22Q4, FY23Q1, [断三格], FY24Q1, …」——
CONTRACT §5 第 3 条不允许这种中间带洞的序列。
所以本次只取 FY24Q1 与 FY24Q2：它们与 CSV 里现有的 FY24Q3 首尾相接，
合并后是 FY24Q1..FY26Q3 **连续 11 季**，没有洞。
（FY22Q4/FY23Q1 那两份不是不能要，是要等 FY23 那三季找到之后一起进来。）

═══ 为什么 accession 列是空的 ═══
这两份 deck **从未随任何 8-K 报进 SEC**。EDGAR 上 FY24Q1/FY24Q2 的业绩 8-K 只挂了 EX-99.1
（新闻稿），没有 EX-99.2 补充资料 —— 这正是 cost_sec.build_tkt_q 抓不到它们的原因
（`_ex992_url` 返回 None，那一件被跳过）。
既然文件不在 SEC，就没有 accession。填上同期 8-K 的 accession 会让下游以为
「去 EDGAR 那件里能找到这张表」，那是**伪造溯源**。所以宁可留空，
另出 `source` / `doc_url` / `doc_sha256` 三列把真实来路写死：来自哪个 IR 文件、内容 hash 是多少。
sha256 是给「所有者哪天问这个数从哪来」准备的：拿着 hash 去比对 cache/ 里那份 PDF，
或者重新下载一次比对，能立刻判定是不是同一个文件。

═══ 为什么 basis 只有 reported ═══
老版 deck 印四行：Comp Sales / W/O Gas & FX / Traffic / Ticket*。
`W/O Gas & FX` 是**除油汇口径的 comp sales**，不是除油汇口径的 ticket ——
它旁边并没有配一张完整的 Ticket/Traffic 分解表（新版 deck 才有 "Adjusted Comp Sales" 那张）。
拿 comp 去反推 adjusted ticket 就是在合成源里没有的数，
跟 cost_sec 对 FY24Q3/FY24Q4/FY25Q1 的处置一样：**缺就是缺，绝不合成**。
（本脚本仍然读这一行，但只拿它当校验输入，不写进 CSV —— 见 `_star_guard` 的注释。）

═══ 老版 deck 的两个解析坑（与 cost_sec 的新版解析器不同）═══
1. 行标签是 `Ticket*`（带星号，星号指向页脚那句 "*Including the impacts from changes in
   gasoline prices and foreign exchange."）。按 `Ticket` 精确匹配的正则一个都匹配不到。
2. **Traffic 行排在 Ticket 行之前**，新版 deck 恰好相反。所以本模块**按标签取值**，
   不靠行序；且值与标签的配对是**按 PDF 里的 y 坐标同带、x 坐标对齐表头**做的，
   不靠文本流顺序。
而 cost_sec._deck_guard 的乘法恒等式 (1+t)(1+f)−1 ≈ Sales **对 t/f 互换是对称的**，
探测不到这两行串位 —— 补一条抓得到的判据，见 `_swap_guard`。

═══ 幂等 ═══
下载全落 `cache/cost_tkt_ir/`（内容缓存，永不过期：IR 站上的文件改了就是新 URL）。
行顺序按 fq 排、字段顺序固定、行尾 `\n`，所以重复跑输出**逐字节相同**，
第二次跑还完全不联网。
"""
import csv
import datetime
import hashlib
import json
import os
import re
import sys
import urllib.request

try:
    import fitz                                  # PyMuPDF
except ImportError as _e:                        # pragma: no cover
    raise SystemExit('本脚本需要 PyMuPDF（import fitz），先 pip install pymupdf') from _e

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SERIES = os.path.join(ROOT, 'series')
CACHE = os.path.join(ROOT, 'cache', 'cost_tkt_ir')

OUT = os.path.join(SERIES, 'cost_tkt_q_ir.csv')
#: 列名与列序必须与它逐字相同（本脚本启动时会核对），另外三列追加在尾部。
SEC_CSV = os.path.join(SERIES, 'cost_tkt_q.csv')
#: 财季起止日的权威表（cost_sec 的分部表），用来给 feed 认出的财季对第二只眼。
SEG_CSV = os.path.join(SERIES, 'cost_seg_q.csv')

#: 与 cost_sec 同一个 UA。注意 investor.costco.com 的**网页**对它是 403，
#: 只有 /feed/*.svc/* 这组接口和 s201.q4cdn.com 上的 PDF 通 —— 所以本脚本
#: 全程只碰这两处，不去解析 IR 的 HTML 页面。
USER_AGENT = os.environ.get('SEC_EDGAR_UA', 'hzhan7@gmail.com research')

#: Costco IR 的**官方可枚举索引**（presentationDateFilter=3 = 全部年份）。
#: 用它而不是写死两个 PDF URL：写死的 URL 一旦 IR 改版就变成 404，而且
#: 「这两份是不是就是官方挂出来的那两份」这件事将无从验证。走索引则每次都是
#: 从官方清单里按财季**认**出来的，认不出宁可抛。
FEED_URL = ('https://investor.costco.com/feed/Presentation.svc/GetPresentationList'
            '?presentationDateFilter=3&excludeSelection=1&tagList=&LanguageId=1'
            '&presentationYear=-1&pageSize=500')

#: 要回填的全部财季：FY22Q4 → FY24Q2，接上 series/cost_tkt_q.csv 的 FY24Q3，
#: Exhibit 15 因此横跨 FY22Q4–FY26Q3 **连续无洞**。
#: 左端到此为止是**查过的**：更早的 Costco Today（2019-06 至 2022-09 八版）逐页扫过，
#: Ticket/Traffic/Frequency 零命中 —— 那一页是 2022-09 版才新增的；2006-2007 的
#: "Supplemental Information"（doc_news/2006/…）只有一页，全文连 Ticket 一词都没有。
WANT = ('FY22Q4', 'FY23Q1', 'FY23Q2', 'FY23Q3', 'FY23Q4', 'FY24Q1', 'FY24Q2')

#: **IR 索引够不到的那几季：冻结直链。**
#: 那条 Presentation.svc 索引只回溯到 FY24Q1（再往前只剩一条没有财季的 "Costco Today"），
#: 而更早的 deck 文件**还在 CDN 上**，只是不再被任何页面链接。所以这几季只能钉死 URL。
#: ⚠️ 这是本仓唯一一处「没有官方索引兜底」的取数路径，因此每一份都**同时钉死 sha256**：
#: 冻结 URL 的失效方式是 404（响），但**同一 URL 被换掉内容**是不响的 —— 那才是要防的。
#: URL 形状换过四种（单数 doc_presentation + 数字月 / 单数 + 无月目录 /
#: 复数 doc_presentations + 三字母月 + **季末日** / 复数 + 月），推不出规律，只能逐条列。
FROZEN = {
    'FY22Q4': 'https://s201.q4cdn.com/287523651/files/doc_presentation/2022/08/Q4-FY%2722.pdf',
    'FY23Q1': 'https://s201.q4cdn.com/287523651/files/doc_presentation/2022/12/Q1-FY%2723.pdf',
    'FY23Q2': 'https://s201.q4cdn.com/287523651/files/doc_presentation/2023/q2-fy%2723.pdf',
    'FY23Q3': 'https://s201.q4cdn.com/287523651/files/doc_presentations/2023/May/07/q3-fy-23.pdf',
    'FY23Q4': 'https://s201.q4cdn.com/287523651/files/doc_presentations/2023/Sep/03/q4-fy-23.pdf',
}

#: deck 的 PresentationDate 距所报财季**季末**的合理区间（天）。
#: 实测这两份都是 **0 天**（feed 给的 PresentationDate 就是季末当天，
#: 11/26/2023 与 02/18/2024 分别正是 FY24Q1、FY24Q2 的最后一天，
#: 而业绩发布其实在两三周之后）—— 所以下界 0 是**必须**的，不能照抄
#: 「申报日总在季末之后若干天」的直觉写成 (7, 60)。上界 60 沿用 cost_sec._DECK_LAG，
#: 够挡住「认到隔壁季」（相邻季末相隔约 84 天）。
_DATE_LAG = (0, 60)

#: 乘法护栏容差（百分点）。**按印法的天花板推，不按这两份样本量出来的偏差定。**
#: ticket 与 traffic 各按 0.1pp 印 → 真值各有 ±0.05pp 的舍入误差；
#: ∂[(1+t)(1+f)−1]/∂t = 1+f ≤ 1.10（本页面所有 traffic ≤ 8.2%），f 侧同理；
#: 印出来的 Sales 自己再带 ±0.05pp。合起来上限 ≈ 0.05×1.10×2 + 0.05 = **0.16pp**。
#: 取 0.25 ≈ 1.5 倍余量。它要挡的是「列串一格」，那种偏差是**几个 pp** 的量级
#: （实测把 FY24Q1 整行左移一格，Total 列偏 5.6pp），0.25 与 1pp 之间的空当足够宽。
_MUL_TOL = 0.25

#: 值与表头列心的最大横向偏离，表示成「相邻表头间距的几分之一」。
#: 实测两份 deck 的值列心与表头列心**完全重合**（偏差 < 0.2pt），
#: 0.25 倍间距（约 33pt）是给字体/版式微调留的余量，同时任何一格串位
#: （= 整整一个间距）都必然被判为「配不上任何一列」。
_COL_FRAC = 0.25


class CostTktIrError(RuntimeError):
    """本模块所有失败路径统一抛它（照 cost_sec.CostSecError 的做法）。"""


# ═══════════════════════════ HTTP + 缓存 ═══════════════════════════

def _fetch(name, url):
    """下载 `url`，缓存成 `cache/cost_tkt_ir/<name>`，返回 bytes。命中缓存不发请求。

    内容缓存不是时效缓存：IR 站上的 PDF 一旦挂出就不会原地改（改了就是新路径），
    索引本身只增不减、而本脚本要的两季早已封闭 —— 所以**索引也一起缓存**是安全的，
    并且这正是「第二次跑完全不联网、输出逐字节相同」的来源。
    要强制重取就 `rm -rf cache/cost_tkt_ir/`。
    """
    os.makedirs(CACHE, exist_ok=True)
    p = os.path.join(CACHE, name)
    if os.path.exists(p) and os.path.getsize(p) > 0:
        with open(p, 'rb') as f:
            return f.read()
    req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            body = r.read()
    except Exception as e:
        raise CostTktIrError(f'取不到 {url}: {type(e).__name__}: {e}') from e
    tmp = p + '.tmp'
    with open(tmp, 'wb') as f:
        f.write(body)
    os.replace(tmp, p)
    return body


# ═══════════════════════════ 索引：认财季 ═══════════════════════════

#: feed 里 Title 的写法在四年里换过好几版："Q3-FY26" / "Q2-FY'26" / "Q3 - FY'25"，
#: 还有一条根本不带财季的 "Costco Today"（那是 FY22Q4 的 deck，本次不要）。
#: 所以分隔符、撇号、空格全部放宽，但**季号与年号本身必须印在标题里**——认不出就是认不出。
_TITLE_FQ = re.compile(r"\bQ\s*([1-4])\s*[-–—]?\s*FY\s*[’'`]?\s*(\d{2,4})\b", re.I)
#: 封面那一页的写法（第三只眼），与 cost_sec._DECK_FQ 同源但允许换行。
_COVER_FQ = re.compile(r'\b(1st|2nd|3rd|4th|First|Second|Third|Fourth)\s+Quarter\s+FY\s*'
                       r"[’'`]?\s*(\d{2,4})", re.I)
_ORD = {'1st': 1, 'first': 1, '2nd': 2, 'second': 2, '3rd': 3, 'third': 3,
        '4th': 4, 'fourth': 4}


def _fq(year, q):
    if year < 100:
        year += 2000
    return f'FY{year % 100:02d}Q{q}'


def _title_fq(title):
    """feed 的 Title → "FY24Q1"；标题里认不出财季就返回 None（**不猜**）。"""
    m = _TITLE_FQ.search(title or '')
    return _fq(int(m.group(2)), int(m.group(1))) if m else None


def _cover_fq(page_text):
    """deck 第 1 页 → "FY24Q1"；认不出返回 None。"""
    m = _COVER_FQ.search(page_text or '')
    return _fq(int(m.group(2)), _ORD[m.group(1).lower()]) if m else None


def _quarter_ends():
    """{财季标签: 季末日} —— 取自 series/cost_seg_q.csv（cost_sec 从 10-K/10-Q 的 XBRL 解出来的）。

    为什么不硬编码这两个日期：硬编码的日期没法证伪。走这张表则「feed 说这是 FY24Q1」
    与「FY24Q1 到底哪天结束」是两个独立来源，对不上就是有一边错了。
    """
    if not os.path.exists(SEG_CSV):
        raise CostTktIrError(f'找不到 {SEG_CSV} —— 财季起止日的来源，没有它就无法给 feed 对第二只眼')
    with open(SEG_CSV, newline='', encoding='utf-8') as f:
        return {r['fq']: r['period_end'] for r in csv.DictReader(f) if r.get('scope') == 'Q'}


def _pick(entries, q_end):
    """从 feed 的全部条目里挑出 WANT 那两季 → {fq: entry}。

    两只眼同时睁着：
      · Title 里必须**印着**季号与财年（`_title_fq`）；
      · PresentationDate 必须落在那一季季末之后 `_DATE_LAG` 天内。
    任何一只眼过不了 → 抛。认错一季在 CSV 里不会留下任何痕迹
    （一整季的客单客流被贴到隔壁季上，数还是那些数），所以绝不许「猜一个最像的」。

    只校验**要的那两条**：feed 里另外十条与本次回填无关，
    其中还有一条标题根本没有财季（"Costco Today"）—— 为它们抛异常等于把一次
    一次性回填绑死在无关条目的标题格式上。它们只在报错时被列出来供人工核。
    """
    got, unresolved = {}, []
    for it in entries:
        fq = _title_fq(it.get('Title'))
        if not fq:
            unresolved.append((it.get('PresentationDate'), it.get('Title')))
            continue
        got.setdefault(fq, []).append(it)
    out = {}
    for fq in WANT:
        if fq in FROZEN:
            continue                 # 索引够不到，走 FROZEN 那条路，不在这里较真
        hits = got.get(fq, [])
        if len(hits) != 1:
            raise CostTktIrError(
                f'IR 索引里按标题认出 {len(hits)} 条 {fq}（要求恰好 1 条）。'
                f'索引共 {len(entries)} 条，认出财季的 {sorted(got)}；'
                f'标题里没有财季的 {unresolved}。拒绝猜。')
        it = hits[0]
        end = q_end.get(fq)
        if not end:
            raise CostTktIrError(f'{SEG_CSV} 里没有 {fq} 的季末日，无法给 feed 对第二只眼')
        d = datetime.date.fromisoformat(_mmddyyyy(it['PresentationDate']))
        lag = (d - datetime.date.fromisoformat(end)).days
        if not _DATE_LAG[0] <= lag <= _DATE_LAG[1]:
            raise CostTktIrError(
                f'IR 索引说 {it["Title"]!r} 是 {fq}，但 {fq} 在 {end} 就结束了，'
                f'而这条的 PresentationDate 是 {d}（隔 {lag} 天，合理区间 {_DATE_LAG}）。'
                f'标题与日期两只眼对不上，拒绝写入。')
        out[fq] = {'entry': it, 'date': d.isoformat(), 'lag': lag}
    return out


def _mmddyyyy(s):
    """feed 的 "02/18/2024 00:00:00" → "2024-02-18"。"""
    m = re.match(r'\s*(\d{1,2})/(\d{1,2})/(\d{4})', s or '')
    if not m:
        raise CostTktIrError(f'IR 索引的 PresentationDate 认不出来: {s!r}')
    return f'{m.group(3)}-{int(m.group(1)):02d}-{int(m.group(2)):02d}'


# ═══════════════════════════ PDF：按标签 + 坐标取值 ═══════════════════════════

#: 表里的百分数。`0.0%` 没有正负号（FY24Q2 的 US ticket 就是这么印的），
#: 所以符号必须是可选的 —— 逐字照抄源，不补符号、不换算。
_PCT = re.compile(r'^[+\-]?\d+(?:\.\d)?%$')
#: 四个行标签的规范名。老版 deck 的行序是 comp / wofx / traffic / ticket，
#: 新版是 comp / ticket / traffic —— 本表**只按标签取**，行序在这里没有任何意义。
_LABELS = {'comp sales': 'comp', 'w/o gas & fx': 'wofx',
           'traffic': 'traffic', 'ticket': 'ticket'}
#: 表头 → CSV 的列前缀。INTL 就是 CSV 里的 oi（Other International）。
_HEADERS = {'us': 'us', 'canada': 'ca', 'intl': 'oi', 'total': 'tc'}
_COLS = ('us', 'ca', 'oi', 'tc')


def _norm(s):
    """标签归一：吃掉 `Ticket*` 的星号、压平空白、转小写。星号是脚注引，不是标签的一部分。"""
    return re.sub(r'\s+', ' ', s.replace('*', '').replace('’', "'")).strip().lower()


def _bands(page):
    """一页 → [(y中心, [(x中心, 词), ...])]，按 y 分带、带内按 x 排序。

    为什么按坐标而不按 `get_text()` 的文本流：文本流是**一维**的，标签与它那一行的四个值
    之所以挨着，只是排版恰好如此；一旦版式改动（比如某一行的值被塞进另一个 block），
    文本流会静默地把值接到相邻标签后面，而按坐标分带则会当场发现「这个标签这一带只有 3 个值」。
    实测两份 deck 的每一行都是一条干净的水平带（y0 完全相同，带间隔 ≥ 30pt）。
    """
    words = []
    for x0, y0, x1, y1, w, *_ in page.get_text('words'):
        words.append(((y0 + y1) / 2, (x0 + x1) / 2, w))
    words.sort()
    out = []
    for yc, xc, w in words:
        if out and abs(yc - out[-1][0]) <= 6:      # 6pt：远小于 30pt 的带间隔
            out[-1][1].append((xc, w))
        else:
            out.append((yc, [(xc, w)]))
    return [(yc, sorted(ws)) for yc, ws in out]


def _table(page):
    """含 ticket/traffic 的那一页 → {'comp'|'wofx'|'traffic'|'ticket': {列: 值}}。

    值到列的映射**按 x 坐标对齐表头**（US / Canada / INTL / Total），
    不按「从左到右第 n 个」。理由与 cost_sec._deck_guard 的 docstring 同源：
    压平之后就是一串裸数字，串一格时数字全都还在、量级也全都合理。
    这里多一道保险：串了格的值会**落在两个表头列心之间**，直接判为配不上任何一列。
    """
    bands = _bands(page)
    hdr = None
    for _, ws in bands:
        names = [_norm(w) for _, w in ws]
        if all(h in names for h in _HEADERS) and not any(_PCT.match(w) for _, w in ws):
            hdr = {_HEADERS[_norm(w)]: x for x, w in ws if _norm(w) in _HEADERS}
            break
    if not hdr:
        raise CostTktIrError('这一页找不到 US / Canada / INTL / Total 这一条表头带')
    xs = sorted(hdr.values())
    tol = _COL_FRAC * min(b - a for a, b in zip(xs, xs[1:]))

    out = {}
    for _, ws in bands:
        vals = [(x, w) for x, w in ws if _PCT.match(w)]
        if not vals:
            continue
        lab = _norm(' '.join(w for x, w in ws if not _PCT.match(w)))
        key = _LABELS.get(lab)
        if key is None or key in out:              # 后面几页/几行还可能有别的表，只取第一次
            continue
        row = {}
        for x, w in vals:
            near = [c for c in _COLS if abs(hdr[c] - x) <= tol]
            if len(near) != 1:
                raise CostTktIrError(
                    f'"{lab}" 行的值 {w} 落在 x={x:.1f}，配不上唯一一列表头 '
                    f'（列心 {[(c, round(hdr[c], 1)) for c in _COLS]}，容差 {tol:.1f}pt）。'
                    f'这正是「列串位」的样子，拒绝写入。')
            if near[0] in row:
                raise CostTktIrError(f'"{lab}" 行有两个值同时落在 {near[0]} 列')
            row[near[0]] = float(w.rstrip('%'))
        if len(row) != 4:
            raise CostTktIrError(f'"{lab}" 行只解出 {len(row)} 个值（应为 4 个：{_COLS}）')
        out[key] = row
    miss = [k for k in ('comp', 'wofx', 'traffic', 'ticket') if k not in out]
    if miss:
        raise CostTktIrError(f'这一页缺行 {miss}（老版 deck 应有 Comp Sales / W/O Gas & FX / '
                             f'Traffic / Ticket* 四行），解出来的是 {sorted(out)}')
    return out


def _table_page(doc):
    """整份 PDF → 唯一那一页（含 Ticket 与 Traffic 两个标签）。多于一页或一页都没有 → 抛。"""
    hit = [i for i in range(doc.page_count)
           if 'Ticket' in doc[i].get_text() and 'Traffic' in doc[i].get_text()]
    if len(hit) != 1:
        raise CostTktIrError(f'这份 deck 里同时含 Ticket 与 Traffic 的页有 {len(hit)} 页'
                             f'（页码 {[i + 1 for i in hit]}），要求恰好 1 页')
    return hit[0]


# ═══════════════════════════ 三道护栏 ═══════════════════════════

def _mul_guard(fq, tbl):
    """乘法恒等式：(1+ticket)(1+traffic)−1 ≈ 印出来的 Comp Sales，四列都要过。

    思路直接沿用 cost_sec._deck_guard —— 它挡的是**整行/整列错位**：错位之后
    12 个数字全都还在、量级也全都合理，CSV 里看不出任何异常。所以必须 raise 不是 warn。
    容差的推法见 `_MUL_TOL`（按印法天花板推，不贴样本）。
    ⚠️ 这道护栏对 ticket ↔ traffic **互换是对称的**（乘法可交换），
    老版 deck 恰恰把这两行印反了序 —— 所以它一个人不够，见 `_swap_guard`。
    """
    worst = 0.0
    for c in _COLS:
        t, f, s = tbl['ticket'][c], tbl['traffic'][c], tbl['comp'][c]
        imp = ((1 + t / 100) * (1 + f / 100) - 1) * 100
        worst = max(worst, abs(imp - s))
        if abs(imp - s) > _MUL_TOL:
            raise CostTktIrError(
                f'{fq} {c} 列：ticket {t}% × traffic {f}% 推出 {imp:.2f}%，'
                f'印的 Comp Sales 是 {s}%，差 {abs(imp - s):.2f}pp > {_MUL_TOL}pp。'
                f'一位小数印法的舍入上限只有 0.16pp，这么大的偏差只可能是版式改了、列串位了。')
    return worst


def _star_guard(fq, page):
    """语义前提检查：星号必须挂在 **Ticket** 行上，且脚注必须说的是油价与汇率。

    这道检查确认的是**发行方自己的口径**：gas / FX 是**价**的扰动，所以它被注在 ticket 上，
    而 traffic（人次）不带星。整个 `_swap_guard` 的立论——「除油汇只动价不动量」——
    就建立在这句脚注上；哪天 Costco 把星号改挂到 Traffic 上，
    那条判据的前提就没了，必须当场停下来让人看，而不是继续按老假设算。

    顺带说明为什么 `W/O Gas & FX` 这一行只进护栏、不进 CSV：它是**除油汇口径的 comp sales**，
    不是除油汇口径的 ticket。老版 deck 没有配套的 adjusted Ticket/Traffic 两行，
    拿 comp 去除以 traffic 反推 adjusted ticket 就是在造源里没有的数（见模块 docstring）。
    """
    labs = {}
    for _, ws in _bands(page):
        lab = ' '.join(w for _, w in ws if not _PCT.match(w))
        if _norm(lab) in _LABELS:
            labs[_LABELS[_norm(lab)]] = lab
    if '*' not in labs.get('ticket', ''):
        raise CostTktIrError(f'{fq}：Ticket 行的标签是 {labs.get("ticket")!r}，没有星号 —— '
                             f'「油价/汇率注在 ticket 上」这个前提失效了，停下来人工核。')
    if '*' in labs.get('traffic', ''):
        raise CostTktIrError(f'{fq}：Traffic 行的标签 {labs["traffic"]!r} 带了星号 —— '
                             f'脚注改挂到人次上了？这会推翻 _swap_guard 的立论，停下来人工核。')
    foot = re.sub(r'\s+', ' ', page.get_text()).lower()
    if not ('gasoline' in foot and 'foreign exchange' in foot):
        raise CostTktIrError(f'{fq}：这一页的脚注里找不到 "gasoline" 与 "foreign exchange" —— '
                             f'星号指向的不再是油价与汇率，前提失效。')


def _swap_guard(fq, tbl, anchor_fq, anchor):
    """**不对称护栏**：抓 ticket / traffic 两行整体串位（乘法恒等式抓不到的那一类）。

    ── 为什么乘法恒等式抓不到，且为什么在这一页里**根本不可能**抓到 ──
    页面只印了四组数：Comp S、W/O Gas & FX S'、以及两行各自的四个值 a、b。
    可用的约束只有两条：
        (1) 乘法： (1+a)(1+b) = 1+S          —— 交换 a、b 完全不变；
        (2) 语义： 除油汇只动价不动量，所以除油汇口径下「量」那一行不变，
                   于是 除油汇的 ticket' = (1+S')/(1+量) − 1。
    把 a 当量、还是把 b 当量，(2) 都能解出一个数来，两边都不产生矛盾
    —— 因为这一页**从来没有印过** adjusted 的 ticket 或 traffic 去跟它对。
    代数上这两种读法严格等价（(1+t')/(1+t) = (1+S')/(1+S) 与「量」是谁无关）。
    结论：判据必须**伸到这一页之外**去，才可能是不对称的。

    ── 伸到哪里 ──
    伸到相邻那一季。ticket 与 traffic 是两条各自缓慢演进的序列，
    而**互换它俩会把两条序列对调**，对调后与相邻季的落差是「两条线之间的距离」量级，
    远大于一个季度的正常移动。锚点链：
        FY24Q3（已在 series/cost_tkt_q.csv 里，来自 SEC 的 8-K EX-99.2，
                由 cost_sec 那套**新版式**解析器解出，行序与本页相反）
          → 校验 FY24Q2 → 再用校验过的 FY24Q2 校验 FY24Q1
    链条的根扎在一条与本脚本完全无关的数据上，所以不是自证。
    两份 deck 若同时串位，第一环（FY24Q2 vs FY24Q3）就会当场炸掉，走不到第二环。

    ── 判据（不含任何拍脑袋的常数）──
    令 d  = Σ|本季按标签读到的 8 个值 − 锚季对应值|（8 = 4 列 × ticket/traffic 两行）
       d' = 同样的和，但本季两行**互换**
       G  = Σ_列 |锚季 ticket − 锚季 traffic|（锚季两条线的分离度）
    三角不等式给出 d' ≥ 2G − d，于是
                d < G  ⟹  d < G ≤ 2G − d ≤ d'，
    即「按标签读」严格优于「互换读」，且余量可证。所以判据就是一句 **d < G**。
    这条判据自带一个正确的失效模式：哪天 ticket 与 traffic 贴到一起（G→0），
    它会**变严直到抛异常**，而不是悄悄放行 —— 一条分不清两者的护栏必须承认自己分不清。
    （FY26 就在往那个方向走：FY26Q2→Q3 两条线已经交叉。所以这条判据只适用于
      FY24 这种「客流领跑、两条线相隔 4-7pp」的时期，用在别处前先看 G。）
    """
    d = sum(abs(tbl[row][c] - anchor[row][c]) for row in ('ticket', 'traffic') for c in _COLS)
    dsw = sum(abs(tbl[{'ticket': 'traffic', 'traffic': 'ticket'}[row]][c] - anchor[row][c])
              for row in ('ticket', 'traffic') for c in _COLS)
    g = sum(abs(anchor['ticket'][c] - anchor['traffic'][c]) for c in _COLS)
    if not d < g:
        raise CostTktIrError(
            f'{fq} 对不上锚季 {anchor_fq}：按标签读的总偏离 d={d:.1f}pp，'
            f'互换两行读 d\'={dsw:.1f}pp，锚季两条线的分离度 G={g:.1f}pp。'
            f'判据要求 d < G（这样才能证明 d < d\'）。'
            f'{"两行多半串位了。" if dsw < d else "或者锚季 ticket/traffic 已经贴到一起，这条护栏在这个时期失效——需要人工核。"}')
    return d, dsw, g


def _anchor_from_csv(fq):
    """从 series/cost_tkt_q.csv 取某季 reported 行 → {'ticket': {列: 值}, 'traffic': {...}}。"""
    with open(SEC_CSV, newline='', encoding='utf-8') as f:
        rows = [r for r in csv.DictReader(f) if r['fq'] == fq and r['basis'] == 'reported']
    if len(rows) != 1:
        raise CostTktIrError(f'{SEC_CSV} 里 {fq} 的 reported 行有 {len(rows)} 条（要求 1 条），'
                             f'锚点不成立')
    r = rows[0]
    return {'ticket': {c: float(r[f'{c}_tkt']) for c in _COLS},
            'traffic': {c: float(r[f'{c}_trf']) for c in _COLS}}


# ═══════════════════════════ 组装 ═══════════════════════════

def _head():
    """表头 = cost_tkt_q.csv 的表头逐字照抄 + 四列（溯源三列 + 口径标记一列）。

    启动时读 SEC 那张表的第一行而不是把列名抄一份写死：抄一份就意味着
    cost_sec 哪天改了列名，两张表会**静默错位**（下游 concat 之后串列，谁都不会收到通知）。
    读过来则当场就能发现不一致 —— 代价只是多读一个文件的第一行。
    """
    if not os.path.exists(SEC_CSV):
        raise CostTktIrError(f'找不到 {SEC_CSV}，无法确认列名与列序')
    with open(SEC_CSV, newline='', encoding='utf-8') as f:
        base = next(csv.reader(f))
    expect = ['fq', 'filed', 'accession', 'basis',
              'us_sales', 'ca_sales', 'oi_sales', 'tc_sales',
              'us_tkt', 'ca_tkt', 'oi_tkt', 'tc_tkt',
              'us_trf', 'ca_trf', 'oi_trf', 'tc_trf',
              'mdna_tc_tkt', 'mdna_tc_frq']
    if base != expect:
        raise CostTktIrError(f'{os.path.basename(SEC_CSV)} 的表头变了：\n  现在 {base}\n  预期 {expect}\n'
                             f'两张表必须同名同序，先确认这次改动再更新本脚本。')
    return base + ['source', 'filed_kind', 'doc_url', 'doc_sha256']


def build(verbose=True):
    """→ (head, rows)。走 IR 索引 → 下载两份 PDF → 解表 → 三道护栏 → 组行。"""
    q_end = _quarter_ends()
    feed = json.loads(_fetch('presentations.json', FEED_URL).decode('utf-8'))
    entries = feed.get('GetPresentationListResult')
    if not isinstance(entries, list) or not entries:
        raise CostTktIrError(f'IR 索引返回的不是条目数组: {list(feed)[:5]}')
    picked = _pick(entries, q_end)
    # 索引够不到的那几季：URL 冻结，`filed` 用**季末日**。这与索引那几季同义 ——
    # 实测 feed 的 PresentationDate 给的正是季末当天（见 _DATE_LAG 的注释），
    # 所以两批行的这一列口径一致，不会在同一张 CSV 里混进两种日期语义。
    for fq, url in FROZEN.items():
        if fq not in WANT or fq in picked:
            continue
        if fq not in q_end:
            raise CostTktIrError(f'{SEG_CSV} 里没有 {fq} 的季末日 —— 冻结那几季的 filed '
                                 f'列全靠它，缺了就只能编一个日期，不许')
        picked[fq] = {'entry': {'DocumentPath': url, 'Title': f'{fq}（冻结直链，IR 索引够不到）'},
                      'date': q_end[fq], 'lag': 0}

    # 倒序处理并**逐季串成一条锚链**：链根 FY24Q3 来自 series/cost_tkt_q.csv
    # （SEC 的 8-K EX-99.2，与本脚本毫无关系的一条数据），过关的那一季再去当下一季的锚。
    # 顺序不能反 —— 反了就是拿一条还没被验过的行去验另一条，等于自证。
    order = sorted(WANT, reverse=True)
    anchors, prev = {}, 'FY24Q3'
    for fq in order:
        anchors[fq] = prev
        prev = fq
    verified, out = {}, {}
    for fq in order:
        p = picked[fq]
        url = p['entry']['DocumentPath']
        raw = _fetch(f'{fq}.pdf', url)
        sha = hashlib.sha256(raw).hexdigest()
        doc = fitz.open(stream=raw, filetype='pdf')
        cover = _cover_fq(doc[0].get_text())
        if cover != fq:                            # 第三只眼：封面自己说是第几季
            raise CostTktIrError(
                f'IR 索引说 {url} 是 {fq}，但封面上写的是 {cover!r}'
                f'（首页原文 {doc[0].get_text()[:80]!r}）。两者必须一致。')
        pg = _table_page(doc)
        tbl = _table(doc[pg])
        _star_guard(fq, doc[pg])
        worst = _mul_guard(fq, tbl)
        afq = anchors[fq]
        anchor = verified.get(afq) or _anchor_from_csv(afq)
        d, dsw, g = _swap_guard(fq, tbl, afq, anchor)
        verified[fq] = {'ticket': tbl['ticket'], 'traffic': tbl['traffic']}
        out[fq] = {'tbl': tbl, 'url': url, 'sha': sha, 'date': p['date'],
                   'page': pg + 1, 'lag': p['lag'], 'title': p['entry']['Title']}
        if verbose:
            print(f'{fq}  {p["entry"]["Title"]!r}  {p["date"]}'
                  f'（季末 {q_end[fq]} 后 {p["lag"]} 天）  p{pg + 1}/{doc.page_count}'
                  f'  sha256 {sha[:16]}…\n'
                  f'      护栏：乘法 max {worst:.3f}pp ≤ {_MUL_TOL}；'
                  f'不对称 d={d:.1f} < G={g:.1f}（互换读 d\'={dsw:.1f}）锚 {afq}',
                  file=sys.stderr)
        doc.close()

    head = _head()
    rows = []
    for fq in sorted(out):
        o = out[fq]
        t = o['tbl']
        row = [fq, o['date'], '', 'reported']       # accession 留空，理由见模块 docstring
        for key in ('comp', 'ticket', 'traffic'):
            row += [f'{t[key][c]:.1f}' for c in _COLS]
        row += ['', '']                             # mdna_*：10-Q MD&A 那句量化的话
        #                                             2025-06 的 10-Q 起才有，这两季没有
        # `filed_kind`：**口径标记**，照 cost_fy.csv 的 seg_oi_basis / preopen_src 的做法。
        # 两张表的 `filed` 列**不同义**：cost_tkt_q.csv 放的是 8-K 的申报日，本表放的是
        # 财季**最后一天**（IR deck 的实际发布在季末后两三周，而 feed 的 PresentationDate
        # 给的就是季末当天；冻结那几季更是直接取 series/cost_seg_q.csv 的 period_end）。
        # 不改列名而加标记：改名会让本表与 SEC 那张表不再同名同序，_head() 那道
        # 「两表必须逐字同构」的护栏就得拆掉 —— 而它防的是更要命的静默串列。
        # 标记留在数据里，下游按 filed 做时点分析之前先读它，而不是靠记性。
        row += ['ir-deck', 'period-end', o['url'], o['sha']]
        rows.append(row)
    return head, rows


def write(head, rows, path=OUT):
    """整表重写。空格只允许出现在 accession 与两列 mdna_* 上（照 cost_sec._write 的规矩）。"""
    opt = {head.index(c) for c in ('accession', 'mdna_tc_tkt', 'mdna_tc_frq')}
    for r in rows:
        if len(r) != len(head):
            raise CostTktIrError(f'行宽 {len(r)} ≠ 表头 {len(head)}: {r}')
        blank = [head[i] for i, c in enumerate(r) if c == '' and i not in opt]
        if blank:
            raise CostTktIrError(f'行 {r[:2]} 的 {blank} 为空，而这些列不允许为空')
    tmp = path + '.tmp'
    with open(tmp, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f, lineterminator='\n')
        w.writerow(head)
        w.writerows(rows)
    os.replace(tmp, path)
    return path


# ═══════════════════════════ 自检 ═══════════════════════════

def selftest():
    """离线自检：三道护栏各喂一份**已知坏**的输入，必须抛。

    护栏最危险的坏法是「写着写着变成永远不抛」，那时它长得跟正常一模一样。
    所以每道护栏都要有一个已知会把它触发的样本。
    """
    ok = True

    def expect_raise(name, fn):
        nonlocal ok
        try:
            fn()
        except CostTktIrError:
            print(f'  ok   {name}')
            return
        ok = False
        print(f'  FAIL {name}：本该抛却过了')

    print('── 标题解析 ──')
    for title, want in (("Q1-FY'24", 'FY24Q1'), ('Q3-FY26', 'FY26Q3'),
                        ("Q3 - FY'25", 'FY25Q3'), ('Costco Today', None)):
        got = _title_fq(title)
        print(f'  {"ok  " if got == want else "FAIL"} {title!r} → {got}')
        ok = ok and got == want

    # 真实的 FY24Q2 表（本次解出来的值），拿去构造坏样本。
    good = {'comp':    {'us': 4.3, 'ca': 9.2, 'oi': 8.6, 'tc': 5.6},
            'ticket':  {'us': 0.0, 'ca': 0.9, 'oi': 1.7, 'tc': 0.3},
            'traffic': {'us': 4.3, 'ca': 8.2, 'oi': 6.8, 'tc': 5.3}}
    print('── 乘法护栏 ──')
    _mul_guard('FY24Q2', good)
    print('  ok   真值通过')
    shifted = {k: dict(zip(_COLS, [v[c] for c in ('ca', 'oi', 'tc', 'us')]))
               for k, v in good.items() if k != 'comp'}
    shifted['comp'] = good['comp']                  # 只把 ticket/traffic 左移一格
    expect_raise('列左移一格被挡住', lambda: _mul_guard('FY24Q2', shifted))

    print('── 不对称护栏（ticket ↔ traffic 串位）──')
    anchor = _anchor_from_csv('FY24Q3')
    d, dsw, g = _swap_guard('FY24Q2', good, 'FY24Q3', anchor)
    print(f'  ok   真值通过 d={d:.1f} < G={g:.1f}（互换读 d\'={dsw:.1f}）')
    swapped = dict(good, ticket=good['traffic'], traffic=good['ticket'])
    print(f'  （注：互换后的表**照样通过乘法护栏** —— 这正是它必须存在的理由）')
    _mul_guard('FY24Q2-swapped', swapped)
    expect_raise('两行互换被挡住', lambda: _swap_guard('FY24Q2', swapped, 'FY24Q3', anchor))
    return ok


def main(argv):
    if '--selftest' in argv:
        return 0 if selftest() else 1
    head, rows = build()
    write(head, rows)
    print(f'wrote {OUT}  {len(rows)} 行')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
