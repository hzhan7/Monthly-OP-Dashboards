# -*- coding: utf-8 -*-
"""American Express (AXP) 月度信贷指标抓取 —— SEC EDGAR，无人值守。

════════ 数据源 ════════
两份申报，同一天送达，缺一不可：

1) 8-K Item 7.01「U.S. Consumer and U.S. Small Business Delinquency and Write-off
   Rate Statistics」——  发行人 AMERICAN EXPRESS CO，CIK 0000004962
     索引：https://data.sec.gov/submissions/CIK0000004962.json
     正文：https://www.sec.gov/Archives/edgar/data/4962/<accession-no-dash>/<primaryDocument>
   数据直接写在 8-K 主文档的 HTML 表里（不是 EX-99.1，2026 年这几期都如此），
   每期给**最近 3 个月**，所以哪怕漏跑两个月也能自动补齐。

2) Form 10-D「Monthly Servicer's Certificate」—— American Express Credit Account
   Master Trust，CIK 0001003509，数据在 EX-99.01（2.4 MB 的大 HTML）
     索引：https://data.sec.gov/submissions/CIK0001003509.json
   每期只覆盖 1 个月，但给到小数点后 4 位，远细于 8-K 里那张四舍五入到 0.1 的摘要表。
   该 CIK **没有任何 ABS-EE 申报**（信用卡 ABS 不适用 Reg AB II 资产级披露），
   所以 10-D 是唯一一条路，别去找资产级文件。

   trust 两张表的月份**由 10-D 自己的申报清单决定**（见 START_MONTH 与 update()），
   不再由「最新 8-K 给的那 3 个月」决定 —— 后者让序列结构上永远回不到 2020 年之前。

为什么不用 8-K 里那张 trust 摘要表：它把 payment rate / portfolio yield / excess
spread 全砍掉了，只留 4 行且四舍五入到 0.1 —— 画不出 build_axp.py 要的 excess
spread 曲线。所以 trust 必须回 10-D 原始件。

════════ 发布节奏 ════════
每月 15 日；15 日撞周末或联邦假日则顺延到下一个工作日（实测 2026-02→17 日、
2026-03→16 日）。8-K 与 10-D **同日**送出，所以一次跑把两边一起拉即可。
报告的是**上一个自然月**：7 月 15 日的申报 = 6 月数据。

「同日」这条以前写的是「近 31 期 31/31」——一个**随窗口滚动却写死在文案里**的数字。
回补到 2016-01 之后重新全量核过一次（2026-08-18）：拿库内 127 个月的 10-D filing_date
去比 AXP 的 8-K(Item 7.01) 申报日，EDGAR「recent」索引能覆盖到的 **83 个月 83/83 同日**；
更早的 44 个月（10-D 申报日早于 2019-10-15）8-K 索引已经滚出，**没核过，也别声称核过**。
下次要复核就重跑这段比对，别改这段话里的数。

════════ 口径坑（会咬人的地方）════════
· 2026-05 起改口径。2026-05-15 之前叫 "Card Member loans"（只含循环余额），
  之后改叫 "Card balances"，把 pay-in-full 余额并了进来，量级跳一大截
  （2026-03 消费者口径：旧 97.5bn → 新 110.8bn）。两套口径**不能连着看**。
  本模块按标题里出现的是 "Card Member loans" 还是 "Card balances" 自动判定，
  绝不靠日期硬编码 —— 万一以后再改一次，日期硬编码会静默出错，标题判定会报错。
· 2026-05-15 那期附了 EX-99.1，把 2024-05 起的 24 个月按新口径全部重述。
  这份历史已经在 series/axp_newbasis.csv 与 axp_8k_card_balances.csv 里了，
  本模块只做增量，不重跑重述（要重跑用 parse_8k_table() 直接喂 EX-99.1，
  它对 3 列和 24 列一视同仁）。
· series/axp.csv 是「按当期口径原样入库」的长序列：2026-03 及以前是 loans-only，
  2026-04 起是新口径。build_axp.py 用 .loc[:'2026-03'] 把它截断当旧口径用。
  这不是 bug，是约定：axp.csv = 历史存档，axp_newbasis.csv = 干净的新口径。
· 每期表格最后一列常是 "Three Months Ended"（季度合计），**必须丢掉**，
  否则会被当成一个月份写进 CSV。
· 8-K 表头带 "(Preliminary)" 的月份下期会被小幅修订（通常是 avg balances）。
  本模块只追加、不改写已入库的月份 —— 修订量在 0.1bn 级，改写反而破坏可复现性。
· 2026-06：AXP 卖掉了一批已核销余额，把 net write-off rate 压低了约 0.3pp
  （Consumer）/ 0.1pp（SBS），trust 的 net default rate 同样受影响
  （0.72% vs 前月 1.24%）。这是真实披露值，不是解析错误，不要「修正」。
· 10-D 里 "Annualized Default Rate" 出现两次：A 段 4 位小数、D 段 2 位小数。
  已入库的历史取 A 段（1.7827），而 "Annualized Recovery Rate" 只有 D 段有（1.06）。
  混着取才对得上，别图省事全取一段。
· trust 的 excess spread 是**按 series 逐个列出**的，Group 1 各 series 数值相同。
  取众数、并把「有多少个 series 报了这个数」一并存进 n_series_at_that_es，
  这样以后哪天 Group 1 分裂成两个数值，这一列会立刻露馅。
  ⚠️ 回补到 2016 之后这一列**常年在动**（实测 2016 年 8 个 series、2019-04 到 12 个、
  2022-04 降到 5 个、2025-07 又到 14 个）。它是「Group 1 分裂预警」的哨兵，
  数值本身变动是正常的发债节奏，不是异常。
· **10-D 的口径断点（回补时踩到的，都已在代码里处理）**：
    2016-12 及更早  A 段叫 `Ending Total Accounts Receivable`（2017-01 起改名）
    2019-11 及更早  EX-99 附件名不带 01（`dNNNNNNdex99.htm`）
    2013-01 及更早  A 段整行没有「期末总应收」→ parser 干净下界 = 2014-01
    2007 及更早     附件是 .txt 且无 D 段分节，解不了
· **trust 本金应收是 level 序列，2018-10 有一个真实台阶**：22.915bn → 30.840bn，
  因为那期 A 段写着 `Addition of Principal Receivables 7,829,153,847.24`（信托加池），
  账户数同月 12,499,212 → 16,372,586。**画 level 一定要标注加池，否则会被读成业务放量。**
  比率类（payment rate / portfolio yield / excess spread / dq30 / 违约率）是池内比率，
  跨这个台阶可连比。

════════ 反爬 ════════
EDGAR 不设 Cloudflare/Akamai，标准库 urllib + 带邮箱的 User-Agent 即可，
无需浏览器、无需登录、无验证码。唯一硬性要求是 UA 里必须有联系邮箱，
否则 403。速率上 SEC 要求 <10 req/s，本模块串行且带 sleep，远低于上限。
"""
import collections
import csv
import gzip
import html as _html
import json
import os
import re
import time
import urllib.error
import urllib.request

# ── 常量 ────────────────────────────────────────────────────────────────
CIK_AXP = '0000004962'      # American Express Company —— 发月度 8-K 的主体
CIK_TRUST = '0001003509'    # American Express Credit Account Master Trust —— 发 10-D 的主体

# SEC 要求 UA 里带真实联系方式，否则整站 403。这不是可选项。
USER_AGENT = os.environ.get('SEC_EDGAR_UA', 'monthly-op-dashboards hzhan7@gmail.com')

SUBMISSIONS = 'https://data.sec.gov/submissions/CIK{cik}.json'
ARCHIVE_DIR = 'https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc}'

# ── trust 两张表的回补下界 ────────────────────────────────────────────────────
# 这是个**真能拧的旋钮**：`update()` 每轮拿它跟 10-D 申报清单求差集，缺哪个月补哪个月，
# 往前长与往回长走同一条路。改小它、跑一次 `python3 fetch/axp.py`，序列就长回去。
#
# 为什么停在 2016-01 而不是源的边界：
#   · 申报下界 2006-06（242 份 10-D，中间只缺 2006-10 / 2006-12），但 2007 年及更早是
#     `.txt` 且没有 `D. Trust Performance … E. Repurchases` 分节，parse_10d 切不出来。
#   · 2013-01 及更早，A 段整行没有 `Ending Total Accounts Receivable`
#     （只剩 Ending Total Principal Balance）→ `ending_total_receivables_usd` 拿不到。
#   · 所以 **parser 干净可达的下界是 2014-01**。停在 2016-01 是与全站窗口对齐
#     （build/cboe.py / build/cme.py 的 WIN_FROM、build/msci.py 的 WIN0 都是这一个），
#     不是被源卡住的。要往前到 2014-01 只需改这一行，2014/2015 那 24 个月实测同样解得动。
# ⚠️ 本常量只管 trust 两张表。axp.csv 想早于 2016-01 会撞**真口径断点**：
#    2016 年那批月度 8-K 只披露单一 U.S. Card Services 段、没有 Consumer / SBS 拆分，
#    硬接会把两条线在 2016 年之前变成同一条。那不是解析问题，改这里也没用。
START_MONTH = '2016-01'

_MONTHS = {m: i + 1 for i, m in enumerate(
    ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'])}

# 各 CSV 的列定义。写之前拿它逐列查缺 —— 缺任何一列直接抛异常，绝不写 NaN。
COLS_MAIN = ['month', 'consumer_balance_usdbn', 'consumer_dq30_pct', 'consumer_nco_pct',
             'sbs_balance_usdbn', 'sbs_dq30_pct', 'sbs_nco_pct']
COLS_8K = ['month', 'consumer_total_bal_usdbn', 'consumer_dpd30_pct', 'consumer_avg_bal_usdbn',
           'consumer_nwo_pct', 'smb_total_bal_usdbn', 'smb_dpd30_pct', 'smb_avg_bal_usdbn',
           'smb_nwo_pct', 'total_hfi_usdbn', 'source']
COLS_TRUST = ['month', 'payment_rate_pct', 'portfolio_yield_pct', 'excess_spread_pct',
              'principal_receivables_usdbn', 'dq30_pct', 'nco_pct']
COLS_TRUST_FULL = [
    'month', 'report_date', 'filing_date', 'accession', 'days_in_period',
    'payment_rate_pct', 'portfolio_yield_pct', 'excess_spread_pct_group1',
    'n_series_at_that_es', 'ending_principal_receivables_usd', 'ending_total_receivables_usd',
    'ending_total_principal_balance_usd', 'ending_transferor_amount_usd',
    'beginning_accounts', 'ending_accounts', 'total_fc_collections_usd',
    'fc_collections_excl_recoveries_usd', 'recoveries_usd', 'total_principal_collections_usd',
    'new_principal_receivables_usd', 'defaulted_amount_usd', 'net_default_amount_usd',
    'ann_default_rate_pct', 'ann_recovery_rate_pct', 'ann_default_rate_net_pct',
    'dq3160_usd', 'dq3160_pct', 'dq6190_usd', 'dq6190_pct', 'dq91120_usd', 'dq91120_pct',
    'dq120p_usd', 'dq120p_pct', 'dq30p_usd', 'dq30p_pct']


class FetchError(RuntimeError):
    """抓不到 / 解析不出时统一抛这个，方便调度器分类告警。"""


# ── 网络层 ──────────────────────────────────────────────────────────────
def _http_get(url, retries=4):
    """EDGAR 偶发 503/超时，退避重试；连不上就抛，绝不返回半截内容。"""
    last = None
    for i in range(retries):
        req = urllib.request.Request(url, headers={
            'User-Agent': USER_AGENT,
            'Accept-Encoding': 'gzip, deflate',
            'Accept': '*/*',
        })
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                raw = r.read()
                if r.headers.get('Content-Encoding') == 'gzip':
                    raw = gzip.decompress(raw)
                return raw
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as e:
            last = e
            time.sleep(1.5 * (i + 1))
    raise FetchError(f'下载失败 {url}: {last}')


def _cached(cache_dir, name, url):
    """原始件一律落盘再解析：出问题时能拿现场复算，也省掉重复下载。"""
    d = os.path.join(cache_dir, 'axp', 'raw')
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, name)
    if os.path.exists(p) and os.path.getsize(p) > 0:
        with open(p, 'rb') as f:
            return f.read()
    b = _http_get(url)
    with open(p, 'wb') as f:
        f.write(b)
    time.sleep(0.25)      # SEC 限速 10 req/s，这里远低于上限
    return b


def _filings(cik, form=None, item=None):
    """读 EDGAR submissions JSON，返回按申报日倒序的申报列表。

    submissions JSON 每次都重新下（它是索引，缓存了就永远发现不了新申报）。
    """
    j = json.loads(_http_get(SUBMISSIONS.format(cik=cik)).decode('utf-8'))
    rec = j['filings']['recent']
    out = []
    for i in range(len(rec['accessionNumber'])):
        if form and rec['form'][i] != form and not rec['form'][i].startswith(form):
            continue
        if item and item not in (rec['items'][i] or ''):
            continue
        out.append({
            'accession': rec['accessionNumber'][i],
            'form': rec['form'][i],
            'filing_date': rec['filingDate'][i],
            'report_date': rec['reportDate'][i],
            'primary': rec['primaryDocument'][i],
        })
    return out


def _dir_listing(cik, accession, cache_dir):
    acc = accession.replace('-', '')
    url = ARCHIVE_DIR.format(cik_int=int(cik), acc=acc) + '/index.json'
    j = json.loads(_cached(cache_dir, f'idx-{accession}.json', url).decode('utf-8'))
    return [it['name'] for it in j['directory']['item']]


def _doc_url(cik, accession, name):
    return ARCHIVE_DIR.format(cik_int=int(cik), acc=accession.replace('-', '')) + '/' + name


# ── HTML 工具 ───────────────────────────────────────────────────────────
class _TableParser:
    """极简 HTML 表格抽取器 —— 只用标准库。

    为什么不用 pandas.read_html / bs4：无人值守跑在 cron 里，少一个可选依赖
    就少一类「换了台机器就挂」的故障。EDGAR 的表格结构规整，标准库够用。
    """

    def __init__(self):
        from html.parser import HTMLParser

        outer = self

        class P(HTMLParser):
            def __init__(s):
                super().__init__(convert_charrefs=True)
                s.tables, s.stack, s.row, s.cell = [], [], None, None

            def handle_starttag(s, tag, attrs):
                if tag == 'table':
                    s.stack.append([])
                elif tag == 'tr' and s.stack:
                    s.row = []
                elif tag in ('td', 'th') and s.row is not None:
                    s.cell = []

            def handle_endtag(s, tag):
                if tag in ('td', 'th') and s.cell is not None:
                    s.row.append(re.sub(r'\s+', ' ', ''.join(s.cell)).strip())
                    s.cell = None
                elif tag == 'tr' and s.row is not None:
                    if s.stack:
                        s.stack[-1].append(s.row)
                    s.row = None
                elif tag == 'table' and s.stack:
                    s.tables.append(s.stack.pop())

            def handle_data(s, data):
                if s.cell is not None:
                    s.cell.append(data)

        outer._P = P

    def parse(self, html_bytes):
        p = self._P()
        p.feed(html_bytes.decode('utf-8', 'replace'))
        return p.tables


def _tables(html_bytes):
    return _TableParser().parse(html_bytes)


def _flat_text(html_bytes):
    """把 HTML 压成单行空格分隔的纯文本 —— 10-D 那种「标签 换行 数值」的结构
    用行解析很脆，压平后用锚定正则反而稳。"""
    t = html_bytes.decode('utf-8', 'replace')
    t = re.sub(r'(?is)<(script|style).*?</\1>', ' ', t)
    t = re.sub(r'<[^>]+>', ' ', t)
    t = _html.unescape(t)
    t = t.replace(' ', ' ').replace(' ', ' ').replace(' ', ' ')
    return re.sub(r'\s+', ' ', t)


def _num(s):
    """'$ 1,234.56' → 1234.56；'(0.7)' → -0.7；空/破折号 → None。"""
    if s is None:
        return None
    s = s.strip().replace('$', '').replace('%', '').replace(',', '').strip()
    if s in ('', '-', '–', '—', 'N/A', 'NA'):
        return None
    neg = s.startswith('(') and s.endswith(')')
    s = s.strip('()')
    try:
        v = float(s)
    except ValueError:
        return None
    return -v if neg else v


def _month_from_header(h):
    """表头 → 'YYYY-MM'。同时吃 'April 30,2026' / 'Apr302026' / '(Preliminary) June 30,2026'。

    含 'Three Months' 的列是季度合计，返回 None 让调用方丢掉 —— 这一列如果混进去，
    会伪装成一个月份写进 CSV，且数值看着「差不多对」，非常难查。
    """
    if not h or 'three month' in h.lower():
        return None
    m = re.search(r'(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s*(\d{1,2})\s*,?\s*(\d{4})',
                  h, re.I)
    if not m:
        return None
    return f'{int(m.group(3)):04d}-{_MONTHS[m.group(1).lower()]:02d}'


# ── 8-K 解析 ────────────────────────────────────────────────────────────
# 表内行标签 → 内部字段名。新旧口径的行标签不同，两套都列出来。
_ROW_MAP = [
    (r'^total (card balances|loans)$', 'total_bal'),
    (r'^30 days past due', 'dpd30'),
    (r'^average (card balances|loans)$', 'avg_bal'),
    (r'^net write-off rate', 'nwo'),
]
_TOTAL_HFI = r'^total card (balances|member loans) held for investment'


def parse_8k_table(html_bytes):
    """解析 8-K（或其 EX-99.1）里的信贷统计表。

    返回 (basis, {month: {consumer_*/smb_*/total_hfi}})，
    basis ∈ {'card_balances', 'card_member_loans'}。

    对 3 列的常规月报和 24 列的重述附件用同一段代码 —— 列数由表头决定，
    不写死，这样重述件不需要第二套解析器。
    """
    target = None
    for tab in _tables(html_bytes):
        flat = ' '.join(' '.join(r) for r in tab).lower()
        if 'net write-off rate' in flat and ('30 days past due' in flat):
            target = tab
            break
    if target is None:
        return None, {}

    flat = ' '.join(' '.join(r) for r in target).lower()
    # 口径靠标题文字判定，不靠日期 —— 日期硬编码在下一次口径变更时会静默出错
    if 'card member loans' in flat:
        basis = 'card_member_loans'
    elif 'card balances' in flat:
        basis = 'card_balances'
    else:
        raise FetchError('8-K 表格里既没有 "Card balances" 也没有 "Card Member loans"，口径无法判定')

    # 表头：找含日期的那一行。数据行里穿插着纯 '$'/'%' 的装饰单元格，列位和表头对不齐，
    # 所以不按列位取，而是「按顺序取本行全部数值」再切片 —— 前 n 个是月份，
    # 尾部多出来的是 "Three Months Ended" 季度合计列。
    months, n_qtr = None, 0
    for row in target:
        cand = [_month_from_header(c) for c in row]
        if sum(1 for c in cand if c) >= 2:
            months = [c for c in cand if c]
            qtr_idx = [i for i, c in enumerate(row) if 'three month' in c.lower()]
            mon_idx = [i for i, c in enumerate(cand) if c]
            # 季度合计列必须在所有月份列右边，否则切片会切错；真出现就宁可炸
            if qtr_idx and min(qtr_idx) < max(mon_idx):
                raise FetchError(f'8-K 表头里 "Three Months" 列不在最右边: {row}')
            n_qtr = len(qtr_idx)
            break
    if not months:
        raise FetchError('8-K 表头里找不到月份列')

    out = {m: {} for m in months}
    section = None
    for row in target:
        label = row[0].strip() if row else ''
        low = label.lower()
        if 'u.s. consumer' in low and low.endswith(':'):
            section = 'consumer'
            continue
        if 'small business' in low and low.endswith(':'):
            section = 'smb'
            continue
        field = None
        for pat, name in _ROW_MAP:
            if re.match(pat, low):
                field = name
                break
        is_hfi = bool(re.match(_TOTAL_HFI, low))
        if not field and not is_hfi:
            continue

        nums = [_num(c) for c in row if _num(c) is not None]
        if len(nums) != len(months) + n_qtr:
            raise FetchError(
                f'8-K 行「{label}」取到 {len(nums)} 个数 {nums}，'
                f'但表头有 {len(months)} 个月份列 + {n_qtr} 个季度合计列')

        for m, v in zip(months, nums[:len(months)]):
            if is_hfi:
                out[m]['total_hfi'] = v
            else:
                out[m][f'{section}_{field}'] = v
    return basis, out


def _find_monthly_8k(cache_dir, limit=14):
    """从最新往回找「真正是月度信贷统计」的那份 8-K。

    不能只看 Item 7.01：财报稿(2.02,7.01)、投资者演示(7.01,9.01) 也挂 7.01。
    也不能只看「15 号前后」：假日顺延会漂。所以下载后按内容判定，命中即停。
    """
    for f in _filings(CIK_AXP, form='8-K', item='7.01')[:limit]:
        try:
            b = _cached(cache_dir, f'8k-{f["accession"]}-{f["primary"]}',
                        _doc_url(CIK_AXP, f['accession'], f['primary']))
        except FetchError:
            continue
        # 便宜的预筛：先压平再查关键词，避免 "Net write-off<br/>rate" 这类
        # 被标签劈开的写法漏判
        if 'net write-off rate' not in _flat_text(b).lower():
            continue
        basis, data = parse_8k_table(b)
        if data:
            return f, basis, data
    raise FetchError(f'最近 {limit} 份含 Item 7.01 的 8-K 里找不到月度信贷统计表')


# ── 10-D（Lending Trust）解析 ───────────────────────────────────────────
def _grab(text, pattern, label, cast=float):
    m = re.search(pattern, text, re.I)
    if not m:
        raise FetchError(f'10-D 里找不到「{label}」')
    v = _num(m.group(1))
    if v is None:
        raise FetchError(f'10-D 里「{label}」解析不出数值: {m.group(1)!r}')
    return cast(v)


def parse_10d(html_bytes):
    """解析 Monthly Servicer's Certificate（10-D 的 EX-99.01）。

    只取 A 段（Trust Activity）与 D 段（Trust Performance）：
    中间的 B/C 段是逐 series 的分配明细，除了 excess spread 之外用不上，
    而且体量占了这份 2.4 MB 文件的绝大部分。先切段再匹配，避免跨段串味。
    """
    t = _flat_text(html_bytes)

    def _section(start, end):
        i = t.lower().find(start.lower())
        j = t.lower().find(end.lower(), i + 1) if i >= 0 else -1
        if i < 0 or j < 0:
            raise FetchError(f'10-D 里切不出 {start!r} … {end!r} 段')
        return t[i:j]

    A = _section('A. Trust Activity', 'B. Series Allocations')
    D = _section('D. Trust Performance', 'E. Repurchases')

    N = r'\(?\$?\s*([\d,]+\.?\d*)\)?'
    r = {}
    r['days_in_period'] = _grab(A, r'Number of days in Monthly Period\s*' + N, 'days in period')
    r['beginning_accounts'] = _grab(A, r'Beginning Number of Accounts\s*' + N, 'beginning accounts')
    r['ending_accounts'] = _grab(A, r'Ending Number of Accounts\s*' + N, 'ending accounts')
    # 'Recoveries' 这个词在 A 段出现多次，用后文锚死唯一那处
    r['fc_collections_excl_recoveries_usd'] = _grab(
        A, r'Finance Charge Collections \(excluding Recoveries\)\s*' + N, 'FC collections ex-recoveries')
    r['recoveries_usd'] = _grab(
        A, r'Recoveries\s*' + N + r'\s*Total Collections of Finance Charge Receivables', 'recoveries')
    r['total_fc_collections_usd'] = _grab(
        A, r'Total Collections of Finance Charge Receivables\s*' + N, 'total FC collections')
    r['total_principal_collections_usd'] = _grab(
        A, r'Total Collections of Principal Receivables\s*' + N, 'total principal collections')
    r['payment_rate_pct'] = _grab(A, r'Monthly Payment Rate\s*' + N, 'payment rate')
    r['defaulted_amount_usd'] = _grab(A, r'Defaulted Amount\s*' + N, 'defaulted amount')
    # A 段给 4 位小数，D 段只有 2 位；已入库历史用的是 A 段，这里保持一致
    r['ann_default_rate_pct'] = _grab(
        A, r'Annualized Default Rate\s*' + N + r'\s*%', 'annualized default rate')
    r['ann_default_rate_net_pct'] = _grab(
        A, r'Annualized Default Rate, Net of Recoveries\s*' + N + r'\s*%', 'annualized default rate net')
    r['portfolio_yield_pct'] = _grab(A, r'Trust Portfolio Yield\s*' + N + r'\s*%', 'portfolio yield')
    r['new_principal_receivables_usd'] = _grab(
        A, r'New Principal Receivables\s*' + N, 'new principal receivables')
    r['ending_principal_receivables_usd'] = _grab(
        A, r'Ending Principal Receivables Balance\s*' + N, 'ending principal receivables')
    r['ending_transferor_amount_usd'] = _grab(
        A, r'Ending Transferor Amount\s*' + N, 'ending transferor amount')
    r['ending_total_principal_balance_usd'] = _grab(
        A, r'Ending Total Principal Balance\s*' + N, 'ending total principal balance')
    # 2016-12 及更早，A 段这一行叫 **Ending Total Accounts Receivable**；2017-01 起
    # 改成 Ending Total Receivables，其余 30 个标签逐字未变（切换点实测钉死在
    # 2016-12 / 2017-01 之间）。两种写法都认，**不按日期分支** —— 日期硬编码在下一次
    # 改名时会静默取到别的行，别名匹配顶多是找不到而报错，错法更安全。
    # ⚠️ 2013-01 及更早这一行整行消失（A 段只剩 Ending Total Principal Balance），
    #    所以 parser 干净可达的下界是 2014-01，不是申报下界 2006-06。
    r['ending_total_receivables_usd'] = _grab(
        A, r'Ending Total (?:Accounts )?Receivables?\s*' + N, 'ending total receivables')

    # D 段：回收率只有这里有；净核销额同理
    r['net_default_amount_usd'] = _grab(D, r'Net Default Amount\s*' + N, 'net default amount')
    r['ann_recovery_rate_pct'] = _grab(D, r'Annualized Recovery Rate\s*' + N + r'\s*%', 'annualized recovery rate')

    for key, lab in [('dq3160', r'31-60 Days Delinquent'), ('dq6190', r'61-90 Days Delinquent'),
                     ('dq91120', r'91-120 Days Delinquent'), ('dq120p', r'120\+ Days Delinquent'),
                     ('dq30p', r'Total 30\+ Days Delinquent')]:
        m = re.search(lab + r'\s*' + N + r'\s*([\d.]+)\s*%', D, re.I)
        if not m:
            raise FetchError(f'10-D 里找不到拖欠分档「{lab}」')
        r[f'{key}_usd'] = _num(m.group(1))
        r[f'{key}_pct'] = _num(m.group(2))

    # excess spread 逐 series 列出；Group 1 各 series 同值，取众数并记录家数。
    es = re.findall(r'Excess Spread Percentage \(?(-?[\d,]+\.\d+)\)? ?%', t)
    es = [v for v in es if _num(v) not in (None, 0.0)]
    if not es:
        raise FetchError('10-D 里找不到非零的 Excess Spread Percentage')
    val, cnt = collections.Counter(es).most_common(1)[0]
    r['excess_spread_pct_group1'] = _num(val)
    r['n_series_at_that_es'] = float(cnt)
    return r


# EX-99.01 附件名在 20 年里换过三套，回补到 2016 必须三套都认（实测）：
#   · 2019-12 期起（filed 2020-01-15）  d867872dex9901.htm   —— 带 01，同目录还有 ex9902
#   · 2019-11 期及更早                  d841871dex99.htm     —— 不带 01（2016-01 也是这套）
#   · 2011 年前后                       y85537exv99.htm      —— exv99，中间多个 v
# 原来的 `ex99[-_.]?0?1` 只吃第一套，2019-11 及更早一律抛「找不到 EX-99.01」，
# 也就是说抓取器结构上回不到 2020 年之前 —— 这是回补的第二处硬阻塞。
# 结尾锚死 `.htm`：2007 年及更早是 `b414471_ex99.txt`，那批文件没有 D 段分节、
# parse_10d 切不出来，宁可在这里就找不到而报错，也不要下载回来再解出半张表。
# `(?:[-_.]?0?1)?` 后面必须紧跟 `.htm`，所以 ex9902 / ex9903 这些同族附件不会误命中。
_EX99_RE = re.compile(r'ex[-_.]?v?99(?:[-_.]?0?1)?\.htm$', re.I)


def _trust_summary(r):
    """10-D 全字段 → axp_trust.csv 那 6 列。**摘要表唯一的产生方式。**

    摘要表没有自己的数据来源：它按定义就是 full 表的投影，所以这条换算只能有一处
    实现，两张表才不可能各说各话（回补交付后拿全部 127 个月 x 6 列逐格核过，0 处不一致；
    回补之前两表只有 37 个月重叠，同样 0 处不一致 —— 所以这条投影不是本轮新定的口径）。
    入参既可以是 `parse_10d()` 刚解出来的 dict，也可以是从 full CSV 读回来的一行
    （数值列已 `_num` 过）—— 两者键名相同，正是为了让这条投影对新旧数据一视同仁。
    """
    return {
        'payment_rate_pct': r['payment_rate_pct'],
        'portfolio_yield_pct': r['portfolio_yield_pct'],
        'excess_spread_pct': r['excess_spread_pct_group1'],
        # 单位换算：原始件是美元，CSV 存十亿美元并保留 6 位（≈ 千美元精度）
        'principal_receivables_usdbn': round(r['ending_principal_receivables_usd'] / 1e9, 6),
        'dq30_pct': r['dq30p_pct'],
        'nco_pct': r['ann_default_rate_net_pct'],
    }


def _find_10d(cache_dir, months_needed):
    """按报告月取 10-D。返回 {month: (filing_meta, parsed)}。"""
    out = {}
    for f in _filings(CIK_TRUST, form='10-D'):
        month = f['report_date'][:7]
        if month not in months_needed or month in out:
            continue
        names = _dir_listing(CIK_TRUST, f['accession'], cache_dir)
        ex = sorted(n for n in names if _EX99_RE.search(n))
        if not ex:
            raise FetchError(f'10-D {f["accession"]}（{month}）里找不到 EX-99.01，'
                             f'目录内容：{sorted(names)}')
        if len(ex) > 1:
            # 同一份申报里出现两个都像 EX-99.01 的附件 —— 挑哪个都是猜，宁可炸。
            raise FetchError(f'10-D {f["accession"]}（{month}）里有多个 EX-99.01 候选：{ex}')
        b = _cached(cache_dir, f'10d-{f["accession"]}-{ex[0]}',
                    _doc_url(CIK_TRUST, f['accession'], ex[0]))
        out[month] = (f, parse_10d(b))
        if len(out) == len(months_needed):
            break
    return out


# ── CSV 读写 ────────────────────────────────────────────────────────────
def _read_csv(path):
    """读既有 CSV，同时把「行尾符」和「最后一行原样」带回来 —— 追加时要照着写。

    这几个文件不是同一个工具生成的：axp.csv / axp_8k_card_balances.csv /
    axp_trust*.csv 是 CRLF，axp_newbasis.csv 是 LF。追加时不照抄就会在
    git diff 里炸出一堆假改动，也会让「本次跑完还原到原状」失效。
    """
    if not os.path.exists(path):
        return [], [], '\n'
    with open(path, 'rb') as f:
        raw = f.read()
    nl = '\r\n' if raw.count(b'\r\n') > raw.count(b'\n') // 2 else '\n'
    with open(path, newline='', encoding='utf-8') as f:
        rd = csv.reader(f)
        header = next(rd)
        rows = [r for r in rd if r and any(c.strip() for c in r)]
    return header, rows, nl


def _fmt_like(sample, v):
    """按同列既有值的写法输出，避免 11 变成 11.0 这种「只是格式变了」的噪音。

    既有文件是 pandas 写的，float 列用最短往返表示（repr），
    整数列（n_series_at_that_es）就是纯整数。样本取该列最后一行。
    """
    if isinstance(v, str):
        return v
    v = float(v)
    if sample is not None and re.fullmatch(r'-?\d+', sample.strip() or 'x'):
        return str(int(round(v)))
    return repr(v)


def _upsert(path, rows_by_month, new_months, cols):
    """写入新月份并保持月份升序 —— 既能往后追加，也能插到现有首行**之前**。

    这个函数取代了原来的 `_append`（docstring 明写「只追加，绝不重写既有行」）。
    换掉的原因是回补：2016-01…2022-12 这批月份要排在库内首行 2023-01 之前，
    纯追加路径写出来的是一个月份乱序的 CSV —— 下游 `build/axp.py` 的
    `PeriodIndex.sort_index()` 会替它排好，于是**乱序本身不会报错**，只会让
    「CSV 顺序 = 时间顺序」这个所有人都在默认的前提静默失效。

    「绝不重写既有行」这条保证一个字没变，只是改成了逐行照抄来实现：
    既有数据行按**原始文本**原样搬运（连行尾符一起，见 `_read_csv`），
    本函数只格式化自己新造的那几行。整表重写很容易顺手把 pandas 写的
    `26.119674` 变成 `26.1196740`，这种 diff 混在真回补里没人分得出来。
    已存在的月份**拒绝改写**（抛异常），重述要走人工决策，不在这条路上发生。

    写盘前逐列检查：缺任何一个已有列就抛异常。宁可整月不入库，
    也不能写半行 —— 半行会被下游当成真值画进图里。
    """
    if not new_months:
        return
    header, rows, nl = _read_csv(path)
    if header and header != cols:
        raise FetchError(f'{os.path.basename(path)} 列名与预期不符: {header} != {cols}')
    last = rows[-1] if rows else None
    if os.path.exists(path):
        with open(path, 'r', newline='', encoding='utf-8') as f:
            body = [ln for ln in f.read().split(nl) if ln.strip()]
        hdr_line, keep = body[0], {ln.split(',', 1)[0]: ln for ln in body[1:]}
    else:
        hdr_line, keep = ','.join(cols), {}
    for m in sorted(new_months):
        if m in keep:
            raise FetchError(f'{os.path.basename(path)} {m} 已有行，拒绝改写（重述要人工决策）')
        rec = rows_by_month[m]
        missing = [c for c in cols if c != 'month' and rec.get(c) is None]
        if missing:
            raise FetchError(f'{os.path.basename(path)} {m} 缺列 {missing}，拒绝写入')
        cells = [m]
        for i, c in enumerate(cols):
            if c == 'month':
                continue
            sample = last[i] if last and i < len(last) else None
            cells.append(_fmt_like(sample, rec[c]))
        keep[m] = ','.join(cells)
    out = [hdr_line] + [keep[m] for m in sorted(keep)]
    with open(path, 'wb') as f:
        f.write((nl.join(out) + nl).encode('utf-8'))


# ── 对外接口 ────────────────────────────────────────────────────────────
def latest_month(cache_dir):
    """官方源当前最新月，'YYYY-MM'。抓不到 / 解析不出 → 抛 FetchError。

    以 8-K 为准（trust 10-D 同日发布、同月），因为 8-K 是 build_axp.py 第 1 页的主序列。
    """
    os.makedirs(cache_dir, exist_ok=True)
    _f, _basis, data = _find_monthly_8k(cache_dir)
    if not data:
        raise FetchError('8-K 解析出 0 个月份')
    return max(data)


def update(series_dir, cache_dir):
    """把新月份写进 series/*.csv，返回新增月份列表（去重、升序）。

    幂等：已有月份直接跳过，重复跑不会重复追加。
    """
    os.makedirs(cache_dir, exist_ok=True)
    meta, basis, data = _find_monthly_8k(cache_dir)
    src_label = '8-K Item 7.01'

    p_main = os.path.join(series_dir, 'axp.csv')
    p_new = os.path.join(series_dir, 'axp_newbasis.csv')
    p_8k = os.path.join(series_dir, 'axp_8k_card_balances.csv')
    p_tr = os.path.join(series_dir, 'axp_trust.csv')
    p_trf = os.path.join(series_dir, 'axp_trust_full.csv')

    have = {p: {r[0] for r in _read_csv(p)[1]}
            for p in (p_main, p_new, p_8k, p_tr, p_trf)}

    # ── 8-K 三张表 ──
    main_rows, new_rows, k8_rows = {}, {}, {}
    for m, d in data.items():
        rec_main = {
            'consumer_balance_usdbn': d.get('consumer_total_bal'),
            'consumer_dq30_pct': d.get('consumer_dpd30'),
            'consumer_nco_pct': d.get('consumer_nwo'),
            'sbs_balance_usdbn': d.get('smb_total_bal'),
            'sbs_dq30_pct': d.get('smb_dpd30'),
            'sbs_nco_pct': d.get('smb_nwo'),
        }
        main_rows[m] = rec_main
        k8_rows[m] = {
            'consumer_total_bal_usdbn': d.get('consumer_total_bal'),
            'consumer_dpd30_pct': d.get('consumer_dpd30'),
            'consumer_avg_bal_usdbn': d.get('consumer_avg_bal'),
            'consumer_nwo_pct': d.get('consumer_nwo'),
            'smb_total_bal_usdbn': d.get('smb_total_bal'),
            'smb_dpd30_pct': d.get('smb_dpd30'),
            'smb_avg_bal_usdbn': d.get('smb_avg_bal'),
            'smb_nwo_pct': d.get('smb_nwo'),
            'total_hfi_usdbn': d.get('total_hfi'),
            'source': src_label,
        }
        if basis == 'card_balances':
            new_rows[m] = rec_main

    add_main = sorted(set(main_rows) - have[p_main])
    add_new = sorted(set(new_rows) - have[p_new])
    # 新口径的 avg balances 表只从改口径那期起有意义，旧口径不往里写
    add_8k = sorted(set(k8_rows) - have[p_8k]) if basis == 'card_balances' else []

    # ── trust 两张表 ──
    # 要哪些月：**10-D 自己的申报清单里 >= START_MONTH 且库内没有的**。
    #
    # 旧写法是 `set(data) - have[p_trf]`，其中 `data` 只有最新 8-K 里的最近 3 个月。
    # 那条路让 trust 表结构上每次最多前进 3 个月、而且**永远回不去**：历史月份连被
    # 问一次的机会都没有，于是 START_MONTH 这种常量改了也不会生效。改成直接问
    # 10-D 的申报清单之后，「往前长（新月）」与「往回长（回补）」是同一条代码路径，
    # 这个常量才真的是个能拧的旋钮。多出来的成本只有一次 submissions JSON 请求 ——
    # 那份索引本来每轮就要下（`_filings` 从不缓存它）。
    all_10d = sorted({f['report_date'][:7] for f in _filings(CIK_TRUST, form='10-D')
                      if f['report_date'][:7] >= START_MONTH})
    want_trf = [m for m in all_10d if m not in have[p_trf]]
    tr = _find_10d(cache_dir, set(want_trf)) if want_trf else {}
    missing = sorted(set(want_trf) - set(tr))
    if missing:
        # 清单里有、却没解出来 —— 静默跳过等于让序列悄悄缺月，宁可整轮 FAIL。
        raise FetchError(f'10-D 申报清单里有 {len(missing)} 个月取不到：{missing[:6]}')
    trf_rows = {}
    for m, (f, r) in tr.items():
        trf_rows[m] = dict(r, report_date=f['report_date'], filing_date=f['filing_date'],
                           accession=f['accession'])

    # axp_trust.csv 是 axp_trust_full.csv 的**精确投影**（换算规则见 _trust_summary；
    # 回补交付后拿全部 127 个月 x 6 列逐格核过，0 处不一致）。所以摘要表缺的月份一律
    # 从 full 表现算 —— 包括**库里 full 表已有、摘要表却没有的**那几个月
    # （交付时是 2023-01…2023-06 六个月），它们零网络就能补出来。
    # 两张表从此不可能各说各话：摘要表没有自己的数据来源。
    _fh, _fr, _ = _read_csv(p_trf)
    known_full = {r[0]: {c: _num(v) for c, v in zip(_fh, r)} for r in _fr}
    tr_rows = {}
    for m in sorted(set(trf_rows) | set(known_full)):
        if m < START_MONTH or m in have[p_tr]:
            continue
        tr_rows[m] = _trust_summary(trf_rows.get(m) or known_full[m])

    add_tr = sorted(set(tr_rows) - have[p_tr])
    add_trf = sorted(set(trf_rows) - have[p_trf])

    _upsert(p_main, main_rows, add_main, COLS_MAIN)
    _upsert(p_new, new_rows, add_new, COLS_MAIN)
    _upsert(p_8k, k8_rows, add_8k, COLS_8K)
    _upsert(p_tr, tr_rows, add_tr, COLS_TRUST)
    _upsert(p_trf, trf_rows, add_trf, COLS_TRUST_FULL)

    return sorted(set(add_main) | set(add_new) | set(add_8k) | set(add_tr) | set(add_trf))


if __name__ == '__main__':
    import argparse

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ap = argparse.ArgumentParser()
    ap.add_argument('--series', default=os.path.join(root, 'series'))
    ap.add_argument('--cache', default=os.path.join(root, 'cache'))
    ap.add_argument('--check', action='store_true', help='只报最新月，不写盘')
    a = ap.parse_args()
    if a.check:
        print('latest_month =', latest_month(a.cache))
    else:
        print('latest_month =', latest_month(a.cache))
        print('added        =', update(a.series, a.cache))
