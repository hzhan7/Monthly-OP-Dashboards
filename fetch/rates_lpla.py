# -*- coding: utf-8 -*-
"""LPL Financial Holdings (LPLA) 季度费率解析器 —— 喂 series/fee_rates.csv 的 LPLA 行。

═══ 它产出什么 ═══
series/fee_rates.csv 里 company=LPLA 现有 6 个 metric，全部来自同一张表：
    metric                          unit            表里的列
    avg_ica_sweep_balance           USD_bn          Average Balance (in billions)
    ica_sweep_revenue               USD_k           Revenue
    ica_sweep_net_yield             bp_annualized   Net Yield (bps)
    avg_total_client_cash_balance   USD_bn          同上三列，只是换一行
    client_cash_revenue             USD_k
    client_cash_net_yield           bp_annualized
前三个取 "Insured cash account sweep" 行，后三个取 "Total Client Cash" 行。
metric 名 / unit 写法**必须与 CSV 现有行逐字一致**（上层按 (company, period, metric) 合并，
改名 = 凭空多一个指标而老的永远不再更新）。

═══ 数据源 ═══
SEC EDGAR 官方 JSON API，无登录态、无验证码、无浏览器：
    https://data.sec.gov/submissions/CIK0001397911.json      → 挑出 item 2.02 的 8-K
    https://www.sec.gov/Archives/edgar/data/1397911/<acc>/index.json  → 找 EX-99.1 文件名
    https://www.sec.gov/Archives/edgar/data/1397911/<acc>/a<YYYY>q<N>earningsrelease.htm
第三步的文件名**不硬编码**，从 index.json 里按 'earningsrelease' 子串挑出来
（历史上一直是 a2026q2earningsrelease.htm 这种，但命名规律不进代码）。
UA 必须带邮箱，否则 SEC 返 403。

═══ 表的位置与形状 ═══
在新闻稿的 "Client Cash Data" 页，标题行是
    Three Months Ended
    June 30, 2026 | March 31, 2026 | June 30, 2025
    Interest-Earning Assets | Average Balance (in billions) | Revenue | Net Yield (bps)(27) | …×3
即**一份新闻稿同时给三个季度**：本季 / 上季 / 去年同季。这就是全量回补的抓手——
把历次新闻稿并起来，覆盖范围一直退到该表首次出现的那期。

═══ 口径坑（踩过的） ═══
1) **这张表是 2024Q1 新闻稿（2024-04-30 发）才有的**，之前的新闻稿只给
   "Client Cash Balances Average Yields - bps"（只有收益率，没有平均余额、没有收入）
   和期末余额表。所以本解析器的**最早季度是 2023-Q1**（2024Q1 新闻稿的去年同季列），
   再往前 fee_rates.csv 也拿不到——不是解析器的锅，是官方没披露过这个口径。
2) 表头标签官方拼错过又改回：≤2025Q4 新闻稿写 **"Interest-Earnings Assets"**（多个 s），
   ≥2026Q1 新闻稿写 "Interest-Earning Assets"。两种都得认，只认一种会静默漏掉一半文件。
3) 行名 "Total Client Cash" 必须**精确等值匹配**。同表里还有
   "Total Client Cash Held By Third Parties" 和 "Total Client Cash and Interest Income, Net"，
   用 startswith / in 会取到错的行（前者少了 CCA，后者多了 margin 和 other interest）。
4) 行名尾巴粘着脚注角标，形如 "Client cash account(25)"，角标号每期都变。匹配前必须剥。
5) **同一页上方还有一张期末余额表**（"Client Cash Balances (in billions)"），行名一模一样
   （Insured cash account sweep / Total Client Cash Balances），但那是**期末时点值**、
   带同比环比百分比列。fee_rates.csv 要的是**平均余额**，所以必须先定位到
   "Interest-Earning(s) Assets" 那一行、只在它下面找数据行，绝不能全文搜行名。
   期末表的 Total 行叫 "Total Client Cash Balances"（带 Balances），平均表叫 "Total Client Cash"，
   一字之差，取错会让 2026-Q2 从 55.7 变成 56.9。
6) 一个季度会在**三期新闻稿**里各出现一次（本季 / 下季的上季列 / 明年同季的去年同季列）。
   实测 2023-Q1…2026-Q2 全部 14 个季度 × 6 个 metric 的跨期比对：**官方一个数都没改过**
   （见 `restatements()`，2026-08-05 跑出来是空表）。但重述是迟早的事，所以规则先立好：
   rows() 默认「三期一致 → 用最早那期（原始披露）；三期分歧 → 认重述，用最新那期的值和 URL」。
   → 对 CSV 现有 45 行，默认策略只改 9 行的 source_url（数值全不变），
     全是「CSV 指向较晚的一期、解析器指向首次披露那一期」：
     2023-Q4 的 client_cash 三件套（CSV→2024Q4 稿，实际首披在 2024Q1 稿），
     2025-Q2 与 2026-Q1 的 ica_sweep 三件套（CSV→2026Q2 稿，实际首披在各自当季稿）。
7) revenue 单位是**千美元**（表头 "Dollars in thousands, except where noted"），
   平均余额是**十亿美元**（列名自带 "in billions"）。两个单位在同一行里混着，别整体换算。
8) 官方对 Net Yield 的定义（脚注 27 原文）是 "Calculated by dividing revenue for the period
   by the average balance during the period"，**没写年化口径**。实测按 actual/365
   （revenue ÷ 平均余额 × 365 ÷ 季度实际天数）能把 28 个「季度 × 行」的 bps 复现到 ±1.8bp 以内，
   按 ×4 复现不了。残差主要来自平均余额只披露到 0.1bn（官方内部用未舍入值），
   最差两处是 2024-Q2 Total（复现 324.2 vs 披露 326）与 2024-Q4 ICA（333.6 vs 335）。
   → 这只是「三列有没有对错行」的交叉验算，**不用它去反推或覆盖官方 bps**。
   → 另注意 build/lpla.py 的量→收入桥用的是 `月末现金 × bps / 12`，与官方 actual/365 的分母
     不同，天生有 1-2% 的月度差，那是 build 层的近似，不是本模块的口径问题。

═══ 覆盖与验证（2026-08-05 实测） ═══
19 份 item 2.02 的 8-K（2021Q4 起）里 10 份含这张表（2024Q1 起），
解析出 2023-Q1 … 2026-Q2 共 14 个季度 × 6 个 metric = 84 行。
与 fee_rates.csv 现有 45 行逐条对账：**45/45 数值完全一致（偏差 0），unit 全等，metric 名全等**，
CSV 里没有一行是本解析器取不到的。相对 CSV 净增 39 行：
    2023-Q1 / 2023-Q2 各 6 行（CSV 完全没有这两季）
    2023-Q3…2026-Q2 的 ica_sweep 三件套各 3 行 × 9 季（CSV 只有 2025-Q2 / 2026-Q1 / 2026-Q2）

═══ 无人值守 ═══
纯 urllib + 标准库（无 pdfplumber / 无 lxml —— 新闻稿是 HTML，正则拆表足够）。
SEC 限速 10 req/s，这里每次请求间 sleep 0.2s，一次全量约 30 次请求。
落盘只到 cache_dir，不碰 series/。任何一步解析不出目标行 → 抛 ParseError，绝不写 None/0。
"""
from __future__ import annotations

import html as _html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import date as _date

CIK = 1397911
CIK_PADDED = '%010d' % CIK
COMPANY = 'LPLA'

SUBMISSIONS_URL = 'https://data.sec.gov/submissions/CIK%s.json' % CIK_PADDED
SUBMISSIONS_PAGE_URL = 'https://data.sec.gov/submissions/%s'
ARCHIVE_DIR = 'https://www.sec.gov/Archives/edgar/data/%d/%%s' % CIK

# SEC 要求 UA 带联系邮箱，否则 403。不带浏览器、不带 cookie。
UA = 'monthly-op-dashboards/1.0 (hzhan7@gmail.com)'

# 这张表最早出现在 2024Q1 新闻稿；再早的 8-K 下下来也白下，直接按日期截断省请求
_EARLIEST_FILING_DATE = '2024-01-01'

# Interest-Earning Assets 表首次出现的那一份新闻稿的申报日（2024Q1 稿，见口径坑 1）。
# 这是 observations() 里那道「新闻稿必须解析出行」的闸门：更早的稿子解析出 0 行是
# **设计内**的正常结果（表还不存在），拿它当失败会在上线第一天就炸 —— 缓存里
# 2024-02-01 那份（2023Q4 业绩）正是这样，11 份里唯一解析出 0 行的一份。
_EARLIEST_TABLE_FILING_DATE = '2024-04-30'

# 「新闻稿申报日 − 它解析出的最新季度的季末」实测跨度：缓存里 10 份全在 25-38 天。
# 阈值取 75 天，两头都留了余量：
#   · 往下，是实测最大值 38 天的近两倍 —— LPLA 比史上最慢再拖五周也不会误报；
#   · 往上，「整整落后一个季度」这种坏法最快也要 115 天（25 + 一个季度 90 天），
#     离 75 还有 40 天，所以该抓的照样抓得住。
# 别往 120 调：那会盖过 115，判据就永远抓不到「落后一个季度」这件唯一要抓的事。
_MAX_REPORT_LAG_DAYS = 75

# 松口径再验：文件名是申报代理手拼的（见上面「数据源」一节：「那是巧合不是契约」），
# 'earnings-release' / '.html' / 'ex99_1' 任何一种写法都能打穿严口径匹配。
# 用它把「这份申报真没有新闻稿正文」和「正文在，只是改名了」分开。
_RELEASE_HINT = re.compile(r'earn|release|ex-?_?99', re.I)

# EDGAR 的 SGML 头页自报的文档数。它和 index.json 是**两条独立的索引**，
# 这正是它能当判据的原因，见 _sgml_document_count。
_DOC_COUNT_RE = re.compile(r'PUBLIC[\s-]*DOCUMENT[\s-]*COUNT[:>]?\s*(\d+)', re.I)

# (行名精确匹配, 三个列位) → CSV 里的 metric 名与 unit。名字和单位写法是 CSV 的既有约定，不许改。
_ROW_SPEC = {
    'insured cash account sweep': [
        ('avg_ica_sweep_balance', 'USD_bn'),
        ('ica_sweep_revenue', 'USD_k'),
        ('ica_sweep_net_yield', 'bp_annualized'),
    ],
    'total client cash': [
        ('avg_total_client_cash_balance', 'USD_bn'),
        ('client_cash_revenue', 'USD_k'),
        ('client_cash_net_yield', 'bp_annualized'),
    ],
}

METRICS = [m for spec in _ROW_SPEC.values() for m, _u in spec]

_MONTHS = {'january': 1, 'february': 2, 'march': 3, 'april': 4, 'may': 5, 'june': 6,
           'july': 7, 'august': 8, 'september': 9, 'october': 10,
           'november': 11, 'december': 12}


class ParseError(RuntimeError):
    """新闻稿结构变了 / 目标行找不到。宁可炸也不能静默返回残缺结果。"""


class SourceError(RuntimeError):
    """官方源取不到（网络、403、EDGAR 改版）。"""


# ────────────────────────── 网络 ──────────────────────────

def _get(url, tries=3, timeout=60):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={
                'User-Agent': UA,
                'Accept-Encoding': 'gzip, deflate',
                'Accept': '*/*',
            })
            with urllib.request.urlopen(req, timeout=timeout) as r:
                blob = r.read()
                if r.headers.get('Content-Encoding') == 'gzip':
                    import gzip
                    blob = gzip.decompress(blob)
                return blob
        except (urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
            last = e
            time.sleep(1.5 * (i + 1))
    raise SourceError('下载失败 %s: %r' % (url, last))


def _cached(cache_dir, name, url, binary=True):
    """下过就不再下。新闻稿是已归档的不可变文件，缓存永远有效。"""
    path = os.path.join(cache_dir, name)
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        blob = _get(url)
        tmp = path + '.tmp'
        with open(tmp, 'wb') as f:
            f.write(blob)
        os.replace(tmp, path)
        time.sleep(0.2)                      # SEC 限速 10 req/s，留足余量
    return path


# ────────────────────────── EDGAR 索引 ──────────────────────────

def _warn(msg):
    sys.stderr.write('[rates_lpla] %s\n' % msg)


def _sgml_document_count(acc, acc_nodash):
    """这份申报**真实的**文档数，取自 EDGAR 的 SGML 头页（index-headers.html）。

    为什么需要第二条索引：index.json 会漏列，而且此刻就在漏。
    2026-08-26 实测，窗口内 11 份 item 2.02 的 8-K 里有 4 份
    （2024-02-01 / 2024-10-30 / 2025-05-08 / 2025-07-31）的 index.json 只列出
    index / xbrl 那四个包装文件、一份正文都不列；而同一份申报的 SGML 头页写着
    PUBLIC DOCUMENT COUNT: 14-16，人读版 index.html 里 a2025q2earningsrelease.htm
    也好端端挂着。文档在，只是 index.json 这条索引看不见它。
    这四份在 2026-08-05 建缓存时还是正常发现的（cache/lpla_rates/ 里躺着它们的正文），
    之后才退化 —— 解析器一个字没改，覆盖面自己缩了水，而缩水的日子和正常的日子
    在日志里长得一模一样。正是 README 第四类。

    形状上与 fetch/cboe.py 的 _crosscheck_report_month、fetch/ice.py 的
    _crosscheck_workbook_month 一致：拿一条**不经过同一个解析路径**的外部事实，
    去核对我们手里的东西。取不到就返回 None，判据退化成「不下结论」而不是误判。
    """
    try:
        txt = _get(ARCHIVE_DIR % ('%s/%s-index-headers.html' % (acc_nodash, acc)))
    except SourceError:
        return None
    m = _DOC_COUNT_RE.search(txt.decode('utf-8', 'replace'))
    return int(m.group(1)) if m else None


def _judge_missing_release(filing_date, acc, acc_nodash, listed, fatal):
    """一份 item 2.02 的 8-K 没匹配到 *earningsrelease*.htm 时，判定这是不是真的没有正文。

    原来这里是一句无条件 `continue`（注释写「有些 2.02 的 8-K 只是补充材料」）。
    问题是这一个动作压着三件完全不同的事：
      ① 真的只有补充材料，没有新闻稿正文 —— 合法，跳过；
      ② 正文在，只是申报代理换了命名（accession 前缀已经换过一次代理，
         000139791… → 000162828…，命名规律跟着换很正常）；
      ③ 正文在、名字也没变，是 index.json 这条索引漏列了（见 _sgml_document_count）。

    ②③ 落在**最新**那份申报上时，后果是当季整季拿不到，而整条链上没有一个人会喊：
    observations() 的 `if not out` 炸不了（老申报照样解析得出来），
    fee_rates._validate 只查形状也拦不住，update() 发现没有新 key 就一行不写，
    monthly_run 打印一句 NOCHANGE。这就是 fetch/rates_cme.py disclosures() 里那道
    newest_ok 绊线要拦的同一件事，rates_lpla 一直没有对应物。

    处置分两档，和 fetch/msci.py update() 的「数值变了只喊，整行没了就抛」同构：
      · 最新那份 → 抛。这一季不补上就永远不会有人发现。
      · 更早的那些 → 只喊不抛。这个源一份新闻稿同时给三个季度（本季 / 上季 /
        去年同季），中间漏一份通常会被前后两份的冗余列补回来 —— 今天漏掉的那四份
        里，有三份的季度就是这样被补回去的，只有 2023-Q3 真的掉了。为一个早就滚出
        看板窗口、且多半能被补回的老季度把整个 fee_rates 步骤天天判失败，方向反了。
        **但这一声必须和正常日子长得不一样**，所以把判据的结论写进 WARN 正文。
    """
    # index.json 里以 accession 打头的那四个是包装文件（index-headers / index / txt /
    # xbrl.zip），不是申报正文。
    real = [n for n in listed if not n.startswith(acc)]
    if not real:
        why = ('index.json 一份正文都不列（只有 %d 个 index/xbrl 包装文件）—— '
               '而任何一份 EDGAR 申报至少有一份主文档，所以这不可能是「真的没有正文」，'
               '是 index.json 这条索引漏列了' % len(listed))
    else:
        loose = [n for n in real
                 if n.lower().endswith(('.htm', '.html')) and _RELEASE_HINT.search(n)]
        if not loose:
            # 目录里确实有文档，只是没有一份像新闻稿 —— 这才是注释里说的「补充材料」，
            # 合法跳过，保持原来的安静行为。
            return
        why = ('目录里有长得像新闻稿的文件 %r，只是文件名不含 earningsrelease '
               '或后缀不是 .htm —— 命名变了' % (loose[:3],))

    if not fatal:
        _warn('WARN %s %s 没找到新闻稿正文：%s。它不是最新一份，本次只告警不判失败 —— '
              '该季度多半会被相邻两份新闻稿的「上季 / 去年同季」列补回来。' % (filing_date, acc, why))
        return

    declared = _sgml_document_count(acc, acc_nodash)
    extra = ('；SGML 头页自报这份申报有 %d 份文档' % declared) if declared else ''
    raise SourceError(
        '最新一份 item 2.02 的 8-K %s（%s）取不到新闻稿正文：%s%s。'
        '拒绝返回一份「看起来完整、只是少最新一季」的结果 —— 那种结果上层只会报 NOCHANGE。'
        '要修：命名变了就放宽 earnings_releases() 里的匹配；index.json 漏列就改从'
        ' %s-index.html（人读版申报索引，那里仍然列着正文）取文件名。'
        % (acc, filing_date, why, extra, acc))


def earnings_releases(cache_dir):
    """列出所有「业绩新闻稿」文档：[(filing_date, accession_no_dashes, url)]，按日期升序。

    做法：submissions JSON 里挑 form=8-K 且 items 含 2.02（Results of Operations）的申报，
    再进各自的 index.json 找文件名含 'earningsrelease' 的文档。
    文件名不硬编码——LPLA 至今叫 a2026q2earningsrelease.htm，但那是巧合不是契约。
    """
    os.makedirs(cache_dir, exist_ok=True)
    sub = json.loads(_get(SUBMISSIONS_URL))
    buckets = [sub['filings']['recent']]
    # recent 目前一路回到 2017，够用；万一将来被挤出去，分页文件里还有
    if min(sub['filings']['recent']['filingDate']) > _EARLIEST_FILING_DATE:
        for f in sub['filings'].get('files', []):
            if f['filingTo'] >= _EARLIEST_FILING_DATE:
                buckets.append(json.loads(_get(SUBMISSIONS_PAGE_URL % f['name'])))

    cand = []
    for r in buckets:
        for form, date, acc, items in zip(r['form'], r['filingDate'],
                                          r['accessionNumber'], r['items']):
            if form != '8-K' or '2.02' not in (items or ''):
                continue
            if date < _EARLIEST_FILING_DATE:
                continue
            cand.append((date, acc))
    if not cand:
        raise SourceError('EDGAR 里没找到 LPLA 含 item 2.02 的 8-K，submissions JSON 结构可能改了')

    cand = sorted(set(cand))
    newest_acc = cand[-1][1]          # 绊线只绑在**最新**那份上，见 _judge_missing_release

    out = []
    for date, acc in cand:
        a = acc.replace('-', '')
        idx = json.loads(_get(ARCHIVE_DIR % (a + '/index.json')))
        time.sleep(0.2)
        listed = [it['name'] for it in idx['directory']['item']]
        names = [n for n in listed
                 if 'earningsrelease' in n.lower() and n.lower().endswith('.htm')]
        if not names:
            # 有些 2.02 的 8-K 只是补充材料，没有新闻稿正文，跳过不算错 —— 但只有
            # 经判据确认「真的没有正文」时才算，否则告警或抛。
            _judge_missing_release(date, acc, a, listed, fatal=(acc == newest_acc))
            continue
        out.append((date, a, ARCHIVE_DIR % (a + '/' + names[0])))
    if not out:
        raise SourceError('所有 item 2.02 的 8-K 里都找不到 *earningsrelease*.htm 文档')
    return out


# ────────────────────────── HTML 拆表 ──────────────────────────

def _table_lines(path):
    """把新闻稿 HTML 压成「一行一个表格行、单元格用 | 分隔」的文本行列表。

    不引第三方库：新闻稿是规规矩矩的 <table>，把 </td> 换成分隔符、</tr> 换成换行即可。
    """
    with open(path, encoding='utf-8', errors='replace') as f:
        t = f.read()
    t = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', t, flags=re.S | re.I)
    t = re.sub(r'</t[dh]>', ' | ', t, flags=re.I)
    t = re.sub(r'</tr>', '\n', t, flags=re.I)
    t = re.sub(r'<[^>]+>', '', t)
    t = _html.unescape(t)
    return [re.sub(r'\s+', ' ', l).strip(' |') for l in t.split('\n') if l.strip()]


def _label(line):
    """行首标签，剥掉脚注角标 (25) 和首尾空白，小写化。"""
    head = line.split('|')[0]
    head = re.sub(r'\(\d+\)\s*$', '', head.strip())
    return head.strip().lower()


def _cell_numbers(line):
    """行里的数值单元格，顺序保留。$ / 空格 / 百分比 / 破折号一律不算数。"""
    out = []
    for cell in line.split('|')[1:]:
        c = cell.strip()
        if not c or c in ('$', '—', '-', '–', 'n/m', '%'):
            continue
        if '%' in c or 'bps' in c.lower():
            continue
        m = re.fullmatch(r'\(?\$?\s*(-?[\d,]+(?:\.\d+)?)\)?', c)
        if not m:
            continue
        v = float(m.group(1).replace(',', ''))
        out.append(-v if c.startswith('(') else v)
    return out


def _period(month, day, year):
    """'June 30, 2026' → '2026-Q2'。季末月以外的日期出现即视为表头识别错了。"""
    if month not in (3, 6, 9, 12):
        raise ParseError('表头日期 %d-%02d-%02d 不是季末，定位错行了' % (year, month, day))
    return '%d-Q%d' % (year, month // 3)


def parse_release(path, source_url):
    """解析一份新闻稿 → [{period, metric, value, unit, source_url}]（该文件里的 3 个季度）。

    表不存在（2024Q1 之前的新闻稿）返回 []，这是正常的，不算错误。
    表存在但目标行缺失 / 数字个数对不上 → 抛 ParseError。
    """
    lines = _table_lines(path)

    # 口径坑 2：官方两种拼法都要认
    anchor = None
    for i, l in enumerate(lines):
        if re.match(r'^\s*Interest-Earnings?\s+Assets\b', l):
            anchor = i
            break
    if anchor is None:
        return []

    # 表头日期行：锚点往上找最近的、含 ≥2 个 "Month D, YYYY" 的行
    periods = None
    for j in range(anchor - 1, max(-1, anchor - 8), -1):
        found = re.findall(r'([A-Z][a-z]+)\s+(\d{1,2}),\s*(\d{4})', lines[j])
        if len(found) >= 2:
            periods = [_period(_MONTHS[m.lower()], int(d), int(y)) for m, d, y in found
                       if m.lower() in _MONTHS]
            break
    if not periods:
        raise ParseError('找不到 Interest-Earning Assets 表的季度表头行：' + path)
    if len(periods) != 3:
        raise ParseError('表头解析出 %d 个季度（预期 3）：%r @ %s' % (len(periods), periods, path))
    if len(set(periods)) != 3:
        raise ParseError('表头季度重复 %r @ %s' % (periods, path))

    # 口径坑 5：只在锚点**之下**找数据行，且到表尾就停
    body = []
    for l in lines[anchor + 1:]:
        lab = _label(l)
        if lab.startswith('note:') or lab.startswith('total client cash and interest income'):
            body.append(l)
            break
        body.append(l)

    out = []
    seen = set()
    for l in body:
        lab = _label(l)                       # 口径坑 3/4：精确等值 + 剥角标
        spec = _ROW_SPEC.get(lab)
        if spec is None or lab in seen:
            continue
        seen.add(lab)
        nums = _cell_numbers(l)
        if len(nums) != 9:
            raise ParseError('行 %r 解析出 %d 个数字（预期 9 = 3 季 × 3 列）：%r @ %s'
                             % (lab, len(nums), nums, path))
        for qi, period in enumerate(periods):
            for ci, (metric, unit) in enumerate(spec):
                out.append({
                    'company': COMPANY,
                    'period': period,
                    'metric': metric,
                    'value': nums[qi * 3 + ci],
                    'unit': unit,
                    'source_url': source_url,
                })

    missing = set(_ROW_SPEC) - seen
    if missing:
        raise ParseError('Interest-Earning Assets 表里缺行 %r（官方改行名了？）：%s'
                         % (sorted(missing), path))
    return out


# ────────────────────────── 对外 API ──────────────────────────

def _quarter_end(period):
    """'2026-Q2' → date(2026, 6, 30)。"""
    y, q = period.split('-Q')
    m = int(q) * 3
    return _date(int(y), m, 31 if m in (3, 12) else 30)


def _crosscheck_filing_lag(filing_date, source_url, got):
    """外部判据：一份新闻稿解析出的最新季度，不能比它自己的申报日落后一个季度。

    申报日是 EDGAR 的元数据，HTML 解析器一个字都读不到它 —— 这正是它能当判据的
    原因，形状与 fetch/cboe.py 的 _crosscheck_report_month、fetch/ice.py 的
    _crosscheck_workbook_month 一致。

    它拦的是「解析成功了，只是认错了表」这一支：比如官方在同一页再排一张历史季度的
    Interest-Earning Assets 表、锚点飘到那张上去。这种坏法行名对、列数对、
    9 个数字也照样取到，parse_release 里那几道 ParseError 一道都不会响，
    上面那道「解析出 0 行就抛」也看不见 —— 只是整份稿子的季度集体后退一格。
    """
    newest = max(r['period'] for r in got)
    lag = (_date.fromisoformat(filing_date) - _quarter_end(newest)).days
    if lag > _MAX_REPORT_LAG_DAYS:
        raise ParseError(
            '%s 申报的新闻稿解析出的最新季度是 %s，两者相差 %d 天，超过 %d 天上限'
            '（实测 LPLA 一贯是季末后 25-38 天发稿）—— 多半是表锚点落到了同一页上'
            '另一张历史季度的表上，或者官方改了表头日期的写法。'
            '拒绝把一份整体后退的结果当成正常数据。来源：%s'
            % (filing_date, newest, lag, _MAX_REPORT_LAG_DAYS, source_url))


def observations(cache_dir):
    """所有 (季度, metric) 在**每一期**新闻稿里的观测值，含重复。用来找重述。

    返回 [{company, period, metric, value, unit, source_url, filing_date}]，按申报日升序。
    """
    os.makedirs(cache_dir, exist_ok=True)
    out = []
    for date, acc, url in earnings_releases(cache_dir):
        path = _cached(cache_dir, 'lpla_8k_%s_%s.htm' % (date, acc), url)
        got = parse_release(path, url)
        # parse_release 对「找不到 Interest-Earning Assets 锚点」是 return []，不是抛。
        # 那一支对 2024Q1 之前的稿子是**正确**的（表还不存在，口径坑 1），但对之后的
        # 每一份都是静默失效：官方改一次表头行名，这里就安静地少一份稿子的三个季度，
        # 而 rows() 仍然返回一份形状完整的结果。所以按申报日开闸 —— 表已经存在的年代，
        # 解析出 0 行只有一种解释，就是解析器该修了。
        if not got and date >= _EARLIEST_TABLE_FILING_DATE:
            raise ParseError(
                '%s 申报的新闻稿解析出 0 行，但这张表从 %s 那份起就一直存在 —— '
                '官方大概率改了 "Interest-Earning(s) Assets" 这个锚点行名（历史上已经'
                '拼错过又改回，见口径坑 2）。宁可整次失败，也不静默少一份稿子的三个季度。'
                '来源：%s' % (date, _EARLIEST_TABLE_FILING_DATE, url))
        if got:
            _crosscheck_filing_lag(date, url, got)
        for row in got:
            row['filing_date'] = date
            out.append(row)
    if not out:
        raise ParseError('一份新闻稿都没解析出数据，Interest-Earning Assets 表可能整体改版了')
    return out


def rows(cache_dir, prefer='original'):
    """LPLA 当前官方可得的全部季度费率行。按 (period, metric) 升序。

    每个 (period, metric) 只留一行。一个季度会在三期新闻稿里各出现一次（口径坑 6），
    prefer 决定留哪一期：
      'original'（默认）—— 三期数值一致时用**最早**披露它的那期（原始披露，也是
                          fee_rates.csv 现有行的隐含约定，source_url 改动最小）；
                          三期出现分歧 = 官方重述，则改用**最新**那期的值与 URL。
                          既不丢重述，又不无谓地翻搅历史行的出处。与 fetch/rates_axp.py 同规则。
      'latest'          —— 无条件用最新一期。想让所有 source_url 都指向最新披露时用。
    两种取值在 2026-08-05 的实测里**数值完全相同**（restatements() 为空），
    只有 source_url 不同：对 CSV 现有 45 行，'original' 改动 9 行、'latest' 改动 27 行。
    """
    if prefer not in ('original', 'latest'):
        raise ValueError("prefer 只能是 'original' 或 'latest'，收到 %r" % (prefer,))
    grouped = {}
    for row in observations(cache_dir):           # 已按申报日升序
        grouped.setdefault((row['period'], row['metric']), []).append(row)

    out = []
    for key in sorted(grouped):
        obs = grouped[key]
        restated = max(o['value'] for o in obs) != min(o['value'] for o in obs)
        pick = obs[-1] if (prefer == 'latest' or restated) else obs[0]
        r = dict(pick)
        r.pop('filing_date', None)
        out.append(r)
    return out


def restatements(cache_dir, tol=1e-9):
    """官方重述清单：同一 (季度, metric) 在不同新闻稿里数值不同的条目。

    返回 [(period, metric, [(filing_date, value), ...])]，空表 = 官方从没改过数。
    """
    seen = {}
    for row in observations(cache_dir):
        seen.setdefault((row['period'], row['metric']), []).append(
            (row['filing_date'], row['value']))
    out = []
    for key in sorted(seen):
        vals = seen[key]
        if max(v for _d, v in vals) - min(v for _d, v in vals) > tol:
            out.append((key[0], key[1], vals))
    return out


if __name__ == '__main__':
    import sys
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cache = os.path.join(root, 'cache', 'lpla_rates')
    rs = rows(cache)
    print('%d rows, %s … %s' % (len(rs), rs[0]['period'], rs[-1]['period']))
    if '--print' in sys.argv:
        for r in rs:
            print('%s,%s,%s,%s,%s,%s' % (r['company'], r['period'], r['metric'],
                                         ('%g' % r['value']), r['unit'], r['source_url']))
    rst = restatements(cache)
    print('restatements: %d' % len(rst))
    for p, m, vals in rst:
        print('  %s %s: %s' % (p, m, vals))
