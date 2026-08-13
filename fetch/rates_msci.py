# -*- coding: utf-8 -*-
"""MSCI Inc. — 季度费率解析器（series/fee_rates.csv 的 company=MSCI 部分）。

═══ 这张表回答什么 ═══
    MSCI 的 asset-based fee（Index 分部里跟着别人 ETF 规模走的那块收入）≈
    季度平均 AUM x 有效基点费率 / 4。build/msci.py 的 Exhibit 8（量→收入桥）
    就是拿这三个数反解的，所以这四个 metric 必须成套：

      asset_based_fee_revenue                    USD_mn        官方披露（Index 分部）
      avg_aum_etfs_linked_msci_equity            USD_bn        官方披露（Period Average AUM）
      disclosed_period_end_basis_point_fee_etf   bp            官方披露（Period-End Basis Point Fee）
      asset_based_fee_effective_rate_annualized  bp_of_etf_aum **本模块算的**，非官方披露

    第四个的定义（与 build/msci.py 的桥完全一致，别改）：
        rate_bp = revenue_USDmn * 4 / (avg_aum_USDbn * 1000) * 10000
                = revenue_USDmn * 40 / avg_aum_USDbn
    即「把当季 ABF 收入年化，再除以当季平均 AUM」。它**不等于**官方那条
    Period-End Basis Point Fee（后者是用期末 Run Rate ÷ 期末 AUM 算的，是个
    时点数，口径完全不同，两个数常年差 1.2-1.7bp）。两条都留着是有意的：
    一条是「实际收到的钱摊到实际规模上」，一条是「官方对外说的牌价」。

═══ 源 ═══
    SEC EDGAR，8-K Item 2.02（季度业绩新闻稿）的 EX-99.1。
      1) https://data.sec.gov/submissions/CIK0001408198.json   列出全部 8-K
      2) .../Archives/edgar/data/1408198/<acc>/<acc>-index-headers.html
         这份 SGML 头里有 <TYPE>EX-99.1 <FILENAME>xxx.htm，是**唯一**可靠地
         定位新闻稿文件名的办法 —— MSCI 的 EX-99.1 文件名毫无规律，换过至少
         五种（a53705949ex99_1.htm / earningsrelease-20240930xf.htm /
         exhibit991earningsrelease-.htm / earningsrelease-20260331xe.htm …），
         而且同一个季度 Q1 和 Q2 的命名都能不一样。不要猜文件名。
      3) 下载 EX-99.1，纯文本解析两张表。
    全程 UA 带邮箱，无 Cookie、无登录态、无验证码，可无人值守。

═══ 每份新闻稿给多少期 ═══
    AUM 表（新版「AUM in ETFs Linked to MSCI Equity Indexes」／
            2017-08-03 及更早叫「Table 7: ETF Assets Linked to MSCI Indexes」）：
        **5 个季度**（滚动窗口）→ 平均 AUM、Period-End Basis Point Fee 各 5 期
    收入表：**两种版式**，本模块 Table 1A 优先、Table 5 兜底
        Table 1A（Index Segment: Results，2020-01-30 起）：**2 期**（本季 + 去年同季）
        Table 5（Operating Results by Segment and Revenue Type，全期都有）：
            **3 期**（本季 + 去年同季 + 上一季）—— 2019-10-31 及更早唯一的来源
    所以 revenue 是最稀缺的那一维，全量历史必须逐份新闻稿扫过去。
    Table 5 在新版新闻稿里也还在，但只作兜底：新版走 Table 1A 就够，两条路都解析
    只会往 restatements() 里灌一堆「同一个数出现两次」，还会改掉既有行的 source_url。

═══ 覆盖到哪一季 ═══
    2015-Q1 – 最新季（submissions.json 的 recent 段回溯到 2016-04-28 那份 8-K，
    它的 AUM 表给 2015-Q1 – 2016-Q1、Table 5 给 2015-Q1）。
    METRIC_BP 只有 2019-Q2 起才有（见口径坑 4：更早的新闻稿印的是另一个口径，
    宁可缺一期也不混）。build/msci.py 不读 METRIC_BP 的历史值，只用最新季那一个。

═══ 口径坑（每一条都踩过，删任何一条都会静默出错）═══
1. **列顺序不固定**。2021-07 / 2021-10 / 2022-01 三份是**新到旧**
   （June'21, Mar'21, Dec'20, Sep'20, June'20），2022-04 起改成旧到新。
   所以绝不能按位置认季度 —— 必须解析表头的「月-日」与「年份」两串再 zip。
   表头里月日和年份是分开两段排的（"…Sep. 30, Dec. 31, … In billions 2024 2024 …"），
   但**顺序一致**，zip 出来就是列。
2. **Q2/Q3/Q4 的表头有 7 列，后 2 列是 YTD**（Six/Nine/Year Ended），Q1 只有 5 列。
   季度列永远是前 5 个 pair，YTD 挂在最后。取前 5 个即可。
3. **单位换过**。Table 1A 2026-Q1 起从 "In thousands" 改成 "In millions"
   （197,515 → 224.5）；AUM 表 2026-Q1 起从 1 位小数改成整数十亿
   （2,274.5 → 2,274）。所以：
     · 必须从表头读 thousands/millions，不能写死；
     · 2026 起的期数精度天然比老期数低，**这是 MSCI 改了披露精度，不是解析错**。
4. **"Period-End Basis Point Fee" 与 "Avg. Basis Point Fee" 是两个东西**。
   2019-08 之前那一行叫 "Avg. Basis Point Fee"。CSV 里的 metric 名叫
   disclosed_period_end_basis_point_fee_etf，只能接前者。本模块对后者**不产出**
   该 metric（宁可缺一期，不可混口径），所以 2019-Q1 及更早没有这个 metric ——
   这是**设计结果不是缺失**。曾经拿它当 START_FILING_DATE 的下界，那是搞混了：
   拦口径的是解析器里的 _AUM_BP_PE，不是起点日期（见 START_FILING_DATE 的注释）。

4b. **老版 AUM 表叫另一个名字**。2017-08-03 及更早是 "Table 7: ETF Assets Linked to
   MSCI Indexes (unaudited)"，行标签是 "Period-Average AUM"（带连字符）。表体结构
   与新版逐行一致，重叠季度数值逐格相同。_AUM_CAPTION_OLD 只作兜底。
   老版表头还有一处不同：月-日与年份是**交替排**的（"Mar. 31, 2016 Dec. 31, 2015 …"）
   而不是分两段。_columns() 用 findall + zip，两种排法都还原得对，不用改。
5. **表格标签会被数字截断**。个别年份的 HTML 把标签折行成
   "Beginning Period AUM in ETFs linked to $ 1,336.2 … MSCI equity indexes"，
   数字插在标签中间。所以只能「锚定标签前缀 → 往后取 N 个数字」，
   不能按「标签 + 一整行」切。
6. **脚注号会混进数字流**。"Period-End Basis Point Fee 3 2.43 2.43 …"（2026 版
   把脚注号写成裸数字 3）和 "Period-End Basis Point Fee(3) 2.44 …"（老版带括号）
   都出现过。bp 行一律只收**带小数点**的数字，裸整数当脚注号丢掉。
7. **口径改名但数没变**：2020-04 起 AUM 表从 "ETFs linked to MSCI Indexes" 改叫
   "equity ETFs linked to MSCI indexes"。实测改名前后重叠季度数值完全一致
   （2019-Q1 877.1 / 2019-Q2 810.9 …），是纯改名。即便如此，本模块默认只从
   2020-04-28 那份开始，保证 metric 名 avg_aum_etfs_linked_msci_equity 与
   披露口径字面一致。
8. 数值是 MSCI 的**估算值**（第三方 ETF 规模，源自 Bloomberg/Refinitiv），
   不是审计数，MSCI 保留重述权。见下面「取哪一版」。

═══ 取哪一版（重述策略）═══
    同一个季度会在最多 5 份新闻稿里出现。本模块取「**该季度作为当季首次披露**
    的那一份」（original disclosure），理由有两条：
      · 精度最高。2025-Q4 平均 AUM 首披是 2,274.5，到 2026-Q2 那份只剩 2,274。
        取最新版等于主动丢精度，还会凭空造出「和 CSV 对不上」的假差异。
      · 与 series/fee_rates.csv 现有 12 行的数值完全一致，上层不用动。
    首披那份拿不到时（例如 2021-04-27 那份 8-K 没有 EX-99 附件）回落到
    「最早一份含该期的新闻稿」。
    所有其他版本仍会被解析并比对，差异走 restatements()：
      · 只是精度变粗（粗版 == round(细版, 粗版小数位)）标为 'rounding'
      · 真的改了数字才标为 'restatement'，打到 stderr，**不改返回值**
        （仓库约定：重述要人工确认）。

═══ 接口 ═══
    rows(cache_dir) -> list[dict]      每个 dict: period/metric/value/unit/source_url
    parse_all(cache_dir) -> dict       全部观测（含每一版），供对账
    restatements(cache_dir) -> list    跨版本差异明细
    直接跑本文件 = 对 series/fee_rates.csv 现有 MSCI 行逐条对账并打印偏差。
"""

import csv
import gzip
import html as _html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

CIK = 1408198
CIK10 = '0001408198'
SUBMISSIONS = f'https://data.sec.gov/submissions/CIK{CIK10}.json'
ARCH = f'https://www.sec.gov/Archives/edgar/data/{CIK}'

# SEC 要求 UA 带可联系到人的邮箱，否则 403 / 限流。
UA = 'monthly-op-dashboards/1.0 (Hainan Zhan; hzhan7@gmail.com)'
HEADERS = {'User-Agent': UA, 'Accept-Encoding': 'gzip, deflate'}
TIMEOUT = 90
RETRIES = 4
SLEEP = 0.35            # SEC 公开限速 10 req/s，这里留足余量

# 起点：2016-04-28 那份（2016-Q1 业绩）。原来是 2020-04-01，那时把口径坑 4 和 7
# 当成了「不能往前取」的理由，其实两条都只是**metric 覆盖面**的问题而不是串味：
#   · 坑 4（"Avg. Basis Point Fee" ≠ "Period-End Basis Point Fee"）：解析器本来就只认
#     后者，老新闻稿里没有那一行 → 老季度天然不产出 METRIC_BP。缺一期，不混口径，
#     这正是坑 4 要的行为，不需要靠起点日期兜。实测老季度 METRIC_BP 全部为空。
#   · 坑 7（"ETFs linked to MSCI indexes" → "…MSCI equity indexes"）：官方自己确认是
#     纯改名，重叠季度数值逐格相同。METRIC_AUM 的名字带 equity 而 2019-10 之前的
#     披露标题不带 —— 这是**名字**与披露字面的出入，不是口径的出入；这张 AUM 表
#     从来就只含股票 ETF。下面 _AUM_CAPTION_OLD 的注释里记了这笔账。
# 换起点是为了让 build/msci.py 的 Exhibit 8 / 10 / 11 能和同页其余各图一样从 2016 起
# （费率序列是那三张图唯一的左边界）。这份能给到 2016-Q1 的平均 AUM 与 ABF 收入。
START_FILING_DATE = '2016-04-01'

SUB_DIR = 'msci_rates'          # cache_dir 下的子目录
SUBMISSIONS_TTL = 6 * 3600      # submissions.json 缓存 6 小时；EX-99.1 是不可变文件，永久缓存

METRIC_RATE = 'asset_based_fee_effective_rate_annualized'
METRIC_REV = 'asset_based_fee_revenue'
METRIC_AUM = 'avg_aum_etfs_linked_msci_equity'
METRIC_BP = 'disclosed_period_end_basis_point_fee_etf'

UNITS = {
    METRIC_RATE: 'bp_of_etf_aum',
    METRIC_REV: 'USD_mn',
    METRIC_AUM: 'USD_bn',
    METRIC_BP: 'bp',
}

_MONTHS = {'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
           'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12}


# ──────────────────────────── 网络 ────────────────────────────

def _fetch(url):
    last = None
    for k in range(RETRIES):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=TIMEOUT) as fh:
                body = fh.read()
                if fh.headers.get('Content-Encoding') == 'gzip':
                    body = gzip.decompress(body)
                return body
        except Exception as exc:            # 503 / 超时是 EDGAR 的常态，退避重试
            last = exc
            time.sleep(1.5 + 2.5 * k)
    raise RuntimeError(f'下载失败 {url}: {last}')


def _cached(path, url, ttl=None):
    """有文件且没过期就用文件；否则下载落盘。落盘只落到 cache_dir 下。"""
    if os.path.exists(path) and os.path.getsize(path) > 0:
        if ttl is None or (time.time() - os.path.getmtime(path)) < ttl:
            return open(path, 'rb').read()
    body = _fetch(url)
    tmp = path + '.tmp'
    with open(tmp, 'wb') as fh:
        fh.write(body)
    os.replace(tmp, path)
    time.sleep(SLEEP)
    return body


def _dir(cache_dir):
    d = os.path.join(cache_dir, SUB_DIR)
    os.makedirs(d, exist_ok=True)
    return d


# ──────────────────────────── 申报清单 ────────────────────────────

def _earnings_8ks(cache_dir):
    """全部 Item 2.02 的 8-K，按申报日升序：[(date, accession, ex99_filename)]"""
    d = _dir(cache_dir)
    raw = _cached(os.path.join(d, 'submissions.json'), SUBMISSIONS, ttl=SUBMISSIONS_TTL)
    sub = json.loads(raw)
    rec = sub['filings']['recent']
    out = []
    for i, form in enumerate(rec['form']):
        if form != '8-K':
            continue
        if '2.02' not in (rec['items'][i] or ''):
            continue
        date = rec['filingDate'][i]
        if date < START_FILING_DATE:
            continue
        acc = rec['accessionNumber'][i]
        nod = acc.replace('-', '')
        hdr = _cached(os.path.join(d, f'{acc}-index-headers.html'),
                      f'{ARCH}/{nod}/{acc}-index-headers.html')
        # SGML 头在这个页面里是 HTML 转义过的，必须先 unescape 才能匹配尖括号
        text = _html.unescape(hdr.decode('utf-8', 'replace'))
        docs = re.findall(r'<TYPE>([^\s<]+)\s*<SEQUENCE>\d+\s*<FILENAME>([^\s<]+)', text)
        ex = [fn for typ, fn in docs if typ.upper().startswith('EX-99')]
        out.append((date, acc, ex[0] if ex else None))
    out.sort()
    # submissions.json 的 recent 段只装最近 ~1000 条申报。MSCI 现在回溯到 2014，
    # 离 START_FILING_DATE 还很远；但哪天申报变密、recent 段够不到 2020 时，
    # 历史会被**静默截断**（老季度悄悄消失，上层还以为只是没更新）。这里叫一声。
    oldest = min(rec['filingDate'])
    if oldest > START_FILING_DATE:
        sys.stderr.write(
            f'[rates_msci] 警告：submissions.json 的 recent 段只到 {oldest}，'
            f'早于此的季度拿不到（需要改读 filings.files 里的分片）\n')
    return out


def _release_text(cache_dir, acc, filename):
    nod = acc.replace('-', '')
    raw = _cached(os.path.join(_dir(cache_dir), f'{acc}__{filename}'),
                  f'{ARCH}/{nod}/{filename}')
    return _flatten(raw.decode('utf-8', 'replace'))


def _url(acc, filename):
    return f'{ARCH}/{acc.replace("-", "")}/{filename}'


# ──────────────────────────── 文本工具 ────────────────────────────

def _flatten(doc):
    """HTML → 单行纯文本。标签换成空格（不是空串！否则相邻单元格会粘成一个数）。"""
    txt = re.sub(r'(?is)<(script|style)[^>]*>.*?</\1>', ' ', doc)
    txt = re.sub(r'<[^>]+>', ' ', txt)
    txt = _html.unescape(txt)
    txt = txt.replace('’', "'").replace('–', '-').replace('—', '-')
    return re.sub(r'[\s\xa0]+', ' ', txt)


_DATE_RE = re.compile(
    r'\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s*(\d{1,2})\b')
_YEAR_RE = re.compile(r'\b(20\d\d)\b')
_NUM_RE = re.compile(r'\(\s*([\d,]+(?:\.\d+)?)\s*\)|([\d,]+(?:\.\d+)?)')


def _columns(header, want):
    """表头 → 列对应的季度列表。

    表头把「月-日」和「年份」分成两段排（见口径坑 1），但两段顺序一致，
    zip 起来就是列顺序。want = 需要的季度列数（AUM 表 5，Table 1A 2）。
    """
    dates = _DATE_RE.findall(header)
    years = _YEAR_RE.findall(header)
    n = min(len(dates), len(years))
    if n < want:
        return None
    cols = []
    for (mon, day), yr in list(zip(dates, years))[:n]:
        m = _MONTHS[mon.lower()[:3]]
        if m not in (3, 6, 9, 12):
            return None
        cols.append(f'{yr}-Q{m // 3}')
    return cols[:want]


def _numbers(text, start, count, decimals_only=False):
    """从 start 往后取 count 个数字，跳过 $ / 标签碎片 / 括号。

    decimals_only=True 时只收带小数点的数（用来甩掉裸整数脚注号，见口径坑 6）。
    """
    out = []
    for m in _NUM_RE.finditer(text, start):
        neg = m.group(1) is not None
        tok = m.group(1) or m.group(2)
        if decimals_only and '.' not in tok:
            continue
        val = float(tok.replace(',', ''))
        out.append(-val if neg else val)
        if len(out) == count:
            break
    return out if len(out) == count else None


# ──────────────────────────── 两张表 ────────────────────────────

# 标题里 "Equity" 的位置在 2021-Q1 那份挪过位（"AUM in Equity ETFs Linked to MSCI
# Indexes" → "AUM in ETFs Linked to MSCI Equity Indexes"），大小写也不统一。
# 重叠季度数值完全一致（2020-Q4 平均 AUM 两份都是 999.2），是纯改写法。
_AUM_CAPTION = re.compile(
    r'AUM in (?:equity )?ETFs linked to MSCI (?:equity )?indexes\s*\(unaudited\)', re.I)
# 2017-08-03 及更早的新闻稿里这张表根本不叫这个名字，叫 "Table 7: ETF Assets Linked to
# MSCI Indexes (unaudited)"（2017-11-02 那份起才改成上面那种写法）。行标签也不同：
# "Period-Average AUM"（带连字符）、"Avg. Basis Point Fee"（不是 Period-End）。
# 表体结构完全一样：5 个季度列、Beginning / Appreciation / Inflows / Period-End /
# Period-Average 五行，重叠季度数值逐格相同（2016-Q3 467.3、2016-Q4 471.1 两版一致）。
# 只作**兜底**：新写法匹配得上就绝不走这条，保证 2017-11 之后的既有行逐字节不变。
_AUM_CAPTION_OLD = re.compile(
    r'Table\s*\d+[A-Z]?\s*:\s*ETF Assets Linked to MSCI Indexes\s*\(unaudited\)', re.I)
_AUM_AVG = re.compile(r'Period[-\s]Average AUM in')
_AUM_BP_PE = re.compile(r'Period-End Basis Point Fee')
_AUM_BP_AVG = re.compile(r'Avg\.\s*Basis Point Fee')
_AUM_BEGIN = re.compile(r'Beginning Period AUM in')


def _parse_aum_table(text):
    """→ {period: {'avg': float, 'bp': float|None}}，5 期。"""
    cap = _AUM_CAPTION.search(text) or _AUM_CAPTION_OLD.search(text)
    if not cap:
        return {}
    begin = _AUM_BEGIN.search(text, cap.end())
    if not begin:
        return {}
    cols = _columns(text[cap.end():begin.start()], 5)
    if not cols:
        return {}
    out = {p: {} for p in cols}

    avg = _AUM_AVG.search(text, begin.end())
    if avg:
        vals = _numbers(text, avg.end(), 5)
        if vals:
            for p, v in zip(cols, vals):
                out[p]['avg'] = v

    # 只认 "Period-End Basis Point Fee"；"Avg. Basis Point Fee" 是另一个口径，
    # 绝不能塞进 disclosed_period_end_basis_point_fee_etf（口径坑 4）。
    bp = _AUM_BP_PE.search(text, begin.end())
    if bp:
        vals = _numbers(text, bp.end(), 5, decimals_only=True)
        if vals:
            for p, v in zip(cols, vals):
                out[p]['bp'] = v
    return out


_T1A = re.compile(r'Index Segment\s*:?\s*Table\s*1A\s*:?\s*Results', re.I)
_T1A_ALT = re.compile(r'Operating Results \(unaudited\)\s*Index\b')
_OPREV = re.compile(r'Operating revenues\s*:')
_ABF = re.compile(r'Asset-based fees\b')

# 2020-01-30 之前没有 Table 1A。同一份数据在
# "Table 5: Operating Results by Segment and Revenue Type (unaudited)" 的 Index 段里，
# 而且给的是**三列**（本季 / 去年同季 / 上一季），比 Table 1A 还多一期。
# 锚点必须一直吃到 "Index" 那个分段小标题：这张表按 Index / Analytics / All Other 依次排，
# 只锚表名会让下面的 _OPREV 落到 Index 段的表头里没问题，但表名与 Index 之间偶尔夹一个
# 脚注号（"(unaudited) 1 Index"），所以中间允许一小段非字母。
_T5 = re.compile(
    r'Table\s*\d+[A-Z]?\s*:\s*Operating Results by Segment[^()]*\(unaudited\)'
    r'[^A-Za-z]*Index\b', re.I)


def _qi(p):
    y, q = p.split('-Q')
    return int(y) * 4 + int(q)


def _parse_index_revenue(text):
    """Index 分部的 asset-based fee 收入 → {period: revenue_USDmn}。

    两种版式，**Table 1A 优先**（2020-01-30 起）：
      Table 1A  2 列：本季、去年同季
      Table 5   3 列：本季、去年同季、上一季（2016-04 – 2019-10 唯一的来源）
    Table 5 在新版新闻稿里也还在，但这里只把它当兜底 —— 新版走 Table 1A 就够，
    多解析一份只会往 restatements() 里灌进一堆「同一个数出现两次」的噪音，
    而且会动到既有 CSV 行的 source_url。
    """
    anchor, want = _T1A.search(text) or _T1A_ALT.search(text), 2
    if not anchor:
        anchor, want = _T5.search(text), 3
    if not anchor:
        return {}
    head_end = _OPREV.search(text, anchor.end())
    if not head_end:
        return {}
    header = text[anchor.end():head_end.start()]
    cols = _columns(header, want)
    if not cols:
        return {}
    # 本季与去年同季必须正好差 4 个季度，差了说明表头认错了；
    # 三列版还要求第三列正好是上一季（Table 5 的列序固定，错位就是解析出了岔子）。
    if _qi(cols[0]) - _qi(cols[1]) != 4:
        return {}
    if want == 3 and _qi(cols[0]) - _qi(cols[2]) != 1:
        return {}

    low = header.lower()
    if 'in thousands' in low:
        scale = 1e-3            # 千美元 → 百万美元
    elif 'in millions' in low:
        scale = 1.0
    else:
        return {}

    abf = _ABF.search(text, head_end.end())
    if not abf:
        return {}
    vals = _numbers(text, abf.end(), want)
    if not vals:
        return {}
    return {p: round(v * scale, 3) for p, v in zip(cols, vals)}


def _own_quarter(revenue_cols):
    """Table 1A / Table 5 的第一列都是新闻稿自己那一季。"""
    return revenue_cols[0] if revenue_cols else None


# ──────────────────────────── 汇总 ────────────────────────────

def parse_all(cache_dir):
    """解析全部新闻稿。

    → {'obs': {(period, metric): [ {value, release_date, acc, url, own} ... ]},
       'releases': [...], 'skipped': [...]}
    """
    obs = {}
    releases, skipped = [], []
    for date, acc, fn in _earnings_8ks(cache_dir):
        if not fn:
            skipped.append((date, acc, 'EX-99 附件缺失'))
            continue
        text = _release_text(cache_dir, acc, fn)
        rev = _parse_index_revenue(text)
        aum = _parse_aum_table(text)
        if not rev and not aum:
            # 不是每份 Item 2.02 的 8-K 都是季度业绩稿。已知良性例子：
            # 2021-02-23 那份是分部口径重述（Burgiss / All Other - Private Assets），
            # 只重列历史分部收入，没有 Table 1A 也没有 AUM 表。跳过是对的。
            skipped.append((date, acc, '不是季度业绩稿（无 Table 1A / 无 AUM 表），跳过'))
            continue
        own = _own_quarter(sorted(rev, reverse=True))
        url = _url(acc, fn)
        releases.append({'date': date, 'acc': acc, 'url': url, 'own': own,
                         'n_rev': len(rev), 'n_aum': len(aum)})

        def put(period, metric, value):
            obs.setdefault((period, metric), []).append(
                {'value': value, 'release_date': date, 'acc': acc, 'url': url,
                 'own': period == own})

        for p, v in rev.items():
            put(p, METRIC_REV, v)
        for p, d in aum.items():
            if 'avg' in d:
                put(p, METRIC_AUM, d['avg'])
            if 'bp' in d:
                put(p, METRIC_BP, d['bp'])
    return {'obs': obs, 'releases': releases, 'skipped': skipped}


def _primary(cands):
    """首披优先（own=True），否则最早的一份。"""
    own = [c for c in cands if c['own']]
    if own:
        return sorted(own, key=lambda c: c['release_date'])[0]
    return sorted(cands, key=lambda c: c['release_date'])[0]


def _decimals(x):
    s = repr(float(x))
    return len(s.split('.')[1].rstrip('0')) if '.' in s else 0


def restatements(cache_dir, parsed=None):
    """跨新闻稿的同期同 metric 差异。分 rounding（只是精度变粗）与 restatement。"""
    parsed = parsed or parse_all(cache_dir)
    out = []
    for (period, metric), cands in sorted(parsed['obs'].items()):
        base = _primary(cands)
        for c in cands:
            if c is base or abs(c['value'] - base['value']) < 1e-9:
                continue
            dc, db = _decimals(c['value']), _decimals(base['value'])
            coarse, fine = (c, base) if dc <= db else (base, c)
            kind = ('rounding'
                    if abs(round(fine['value'], _decimals(coarse['value'])) - coarse['value']) < 1e-9
                    else 'restatement')
            out.append({'period': period, 'metric': metric, 'kind': kind,
                        'primary': base['value'], 'primary_src': base['release_date'],
                        'other': c['value'], 'other_src': c['release_date'],
                        'diff': round(c['value'] - base['value'], 6)})
    return out


def rows(cache_dir):
    """MSCI 当前官方可得的全部季度费率行。

    每个 dict: period / metric / value / unit / source_url
    metric 名与 unit 写法与 series/fee_rates.csv 现有 MSCI 行完全一致。
    """
    parsed = parse_all(cache_dir)
    picked = {k: _primary(v) for k, v in parsed['obs'].items()}

    out = []
    periods = sorted({p for p, _ in picked})
    for p in periods:
        rev = picked.get((p, METRIC_REV))
        aum = picked.get((p, METRIC_AUM))
        bp = picked.get((p, METRIC_BP))
        if rev and aum:
            # 有效费率 = 年化 ABF 收入 / 平均 AUM，单位 bp。与 build/msci.py 的桥同源。
            rate = round(rev['value'] * 40.0 / aum['value'], 3)
            out.append({'period': p, 'metric': METRIC_RATE, 'value': rate,
                        'unit': UNITS[METRIC_RATE], 'source_url': rev['url']})
        if rev:
            out.append({'period': p, 'metric': METRIC_REV, 'value': rev['value'],
                        'unit': UNITS[METRIC_REV], 'source_url': rev['url']})
        if aum:
            out.append({'period': p, 'metric': METRIC_AUM, 'value': aum['value'],
                        'unit': UNITS[METRIC_AUM], 'source_url': aum['url']})
        if bp:
            out.append({'period': p, 'metric': METRIC_BP, 'value': bp['value'],
                        'unit': UNITS[METRIC_BP], 'source_url': bp['url']})

    for r in restatements(cache_dir, parsed):
        if r['kind'] == 'restatement':
            sys.stderr.write(
                f"[rates_msci] 重述告警 {r['period']} {r['metric']}: "
                f"首披 {r['primary']} ({r['primary_src']}) vs "
                f"{r['other']} ({r['other_src']})\n")
    for d, acc, why in parsed['skipped']:
        sys.stderr.write(f'[rates_msci] 跳过 {d} {acc}: {why}\n')
    return out


# ──────────────────────────── 对账 ────────────────────────────

def _reconcile(cache_dir, csv_path):
    have = {}
    with open(csv_path, encoding='utf-8') as fh:
        for r in csv.DictReader(fh):
            if r['company'] == 'MSCI':
                have[(r['period'], r['metric'])] = (float(r['value']), r['unit'], r['source_url'])

    got = {(r['period'], r['metric']): r for r in rows(cache_dir)}

    print(f'CSV 现有 MSCI 行 {len(have)} 条；解析器产出 {len(got)} 条 '
          f'（{min(p for p, _ in got)} .. {max(p for p, _ in got)}）\n')
    bad = 0
    for key in sorted(have):
        v, unit, src = have[key]
        g = got.get(key)
        if not g:
            print(f'MISS  {key[0]} {key[1]}: 解析器没产出'); bad += 1; continue
        d = g['value'] - v
        flag = 'OK  ' if abs(d) < 5e-4 else 'DIFF'
        if flag == 'DIFF':
            bad += 1
        note = '' if g['unit'] == unit else f"  !! unit {unit} -> {g['unit']}"
        same = '' if g['source_url'] == src else '  (source_url 换到首披件)'
        print(f'{flag}  {key[0]} {key[1]:<42} csv={v:>10} parsed={g["value"]:>10} '
              f'diff={d:+.6f}{note}{same}')
    extra = sorted(set(got) - set(have))
    print(f'\n新增（CSV 里没有的期/指标）{len(extra)} 条，'
          f'期间 {min(p for p, _ in extra) if extra else "-"} .. '
          f'{max(p for p, _ in extra) if extra else "-"}')
    print(f'不一致 {bad} 条')
    return bad


if __name__ == '__main__':
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cd = os.path.join(here, 'cache')
    if len(sys.argv) > 1 and sys.argv[1] == 'dump':
        for r in rows(cd):
            print(f"MSCI,{r['period']},{r['metric']},{r['value']},{r['unit']},{r['source_url']}")
    elif len(sys.argv) > 1 and sys.argv[1] == 'restate':
        for r in restatements(cd):
            print(r)
    else:
        sys.exit(1 if _reconcile(cd, os.path.join(here, 'series', 'fee_rates.csv')) else 0)
