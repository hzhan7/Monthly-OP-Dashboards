# -*- coding: utf-8 -*-
"""SLM（Sallie Mae Bank）SMB 私人学生贷 ABS 信托 —— 全部信托的月度合计 / 加权值（自算）。

━━ 数据源（只有官网一处）━━
来源页：https://www.salliemae.com/investors/asset-backed-securities/
页上挂一份「SMB Private Education Loan ABS Trusts Static Pool Information and Monthly
Performance」xlsx，文件名 `Trust_Performance_MMDDYYYY.xlsx`（日期 = 数据截止日），
所在的月份文件夹（`.../investors/october-2026/`）与文件名每月都变 ——
**链接一律从来源页现解析，不拼 URL**（拼错文件夹名是静默拿到旧文件或 404 的坏法）。
一份文件就含全部信托的全部历史（2014-A 从 2014-08 起），所以每月只下这一份、整表重算；
另有每个信托一个的「交割日池余额」常数取自该信托子页的月度服务报告（口径坑 1）。

同一期还挂着：`Monthly_Trust_Performance_Report_*.pdf`（这份 xlsx 的图表版，**不用**）、
`CPR*.xlsx`（openpyxl 读它报 stylesheet 错，**不用**：since-issued CPR 本 xlsx 里已有，
且 CPR 不进本页，见口径坑 6）、`abdist_*.xlsx`（债券因子，**不用**）、
`Smart_Option_..._Historical_Performance_Data_*.xlsx`（季度静态池，**不用**）。

━━ 文件结构（2026-09-30 那期实测；2025-09 / 2026-03 / 2026-08 三期结构相同）━━
· `Orig. Characteristics On BS` / `Off BS`：第 6 行是信托名（表内 24 个 / 表外 17 个，
  共 41 个），下面是**统计截止日**的原始池特征。信托名带 `*` = 已行使清仓赎回
  （optional purchase / clean-up call），见表尾脚注。
· `Performance`：19 个指标块，块标题在 B 列，下一行是表头，再往下每个信托一行。
  表头有两种 —— **整数 1..n（发行后第 k 期）**或**月末日期**。本模块按块现认表头类型，
  不按标题写死（池因子、P&I 占比、累计违约是期数；逾期、forbearance、年化违约是日期）。
  块标题各期会改：2026-03 那期「年化当期违约」没有括号后缀，贷款修改两块叫
  「Loan Modification Since Issuance」/「… as a % of P&I Repayment」，2026-09 改成
  「… by Period」/「… by Date」—— 所以按标题**开头**认块（BLOCKS），每条恰好命中一块，否则抛。

━━ 第 k 期 ↔ 日历月（2026-11-09 钉死，实测见 docs/verify/slm.md §2）━━
日期型块直接给出每个信托每一格的月份。期数型块的第 1 期 = 同一信托在日期型块里的
首个有值月，第 k 期 = 首月 + (k−1)。三条独立证据：
  ① 贷款修改「by Period」与「by Date」两块是同一条序列的两种排法 —— 41 个信托逐个比，
     逐格相等、个数相等（本模块每期都现验，见 parse_workbook 第 3 步）；
  ② 各信托子页上最早一份月度服务报告的标签月 = 日期块首月（41/41；2014-A
     「August 2014」= 2014-08，2026-A「April 2026」= 2026-04）；
  ③ 每个信托最新一份服务报告的当期池余额 = 池因子（按上述映射取月）× 交割日池余额，
     41/41 差额 < $0.01（每接入一个新信托都现做这一道，见 `_ensure_trusts`）。
⚠ **不能用 Orig 表的「Closing Date」推首月**：首期收款期长短逐笔不同（2014-A 交割 08-07、
  首期 = 8 月；2026-A 交割 03-11、首期 = 4 月），而且该表有笔误（2020-A 的 Closing Date
  印成 2019-02-12，早于它自己的统计截止日 2019-12-12；服务报告的 Settlement Date 是 2020-02-12）。

━━ 口径坑（踩过才知道的）━━
1. **池因子的分母是「交割日池余额」，不是 Orig 表里的「统计截止日池余额」。**
   2026-A：Orig 表 Pool Balance $650,062,490.87（截止 2026-01-28），服务报告第 2 页
   「Settlement Date 03/11/2026」那一列 $646,508,148.26；2026-09 池因子 0.954489423
   × 后者 = $617,085,189.40 = 当期报告的池余额，× 前者则多出 $3.4mn（+0.55%）。
   交割日池余额 xlsx 里没有，只能从服务报告取 —— 落在 series/slm_trusts.csv，
   每个信托一行、只取一次（`_ensure_trusts`）。
2. **每个比率只能按自己的分母加权**（服务报告「Loans by Borrower Status」一表全有，
   2026-08/09 两个月 38–39 个信托逐项还原到分）：
     P&I 占比      = P&I 还款余额 ÷ 池余额         （P&I = 当期 + 三档逾期，不含 forbearance）
     任意还款占比  = 「Repayment」状态余额 ÷ 池余额 （含在校期只付利息 / 每月 $25 的借款人）
     逾期三档      = 各档余额 ÷ P&I 还款余额
     年化当期违约  = 当期违约本金 × 12 ÷ P&I 还款余额（报告脚注：Periodic as a % of Loans in Repayment (P&I) × 12）
     贷款修改      = 修改中余额 ÷ P&I 还款余额
     forbearance   = forbearance ÷ (P&I + forbearance)
     deferment     = deferment ÷ (P&I + forbearance + deferment)
   ⇒ 池余额_i = 因子_i × 交割日池余额_i，P&I_i = P&I 占比_i × 池余额_i，
     Forb_i = f_i·P&I_i/(1−f_i)，Defer_i = d_i·(P&I_i+Forb_i)/(1−d_i)，其余各项 = 比率 × 自己的分母；
     合计比率 = Σ分子 ÷ Σ分母（只对当月仍在报告的信托）。
   服务报告 PDF 的「% of Loans in P&I Repay」一栏分母**含** forbearance，与 xlsx 的定义
   （标题写明 Forbearance is not included）不同 —— 本模块只用 xlsx 的定义。
   ⚠ 贷款修改：xlsx 的比率在 2026-08/09 与当期报告的「Loans in Modification」逐分相等，
   但 2020-04 / 2023-06 的 xlsx 值比当年报告原文高约 0.1%（相对），合计层面约 0.01pp ——
   xlsx 对历史的修改口径与当年报告不完全一样。本列照 xlsx（当期官方口径）出，差异记在
   docs/verify/slm.md。
3. **2014-A 由 Navient 子服务，核销线是 212 天，其余信托是 120 天**（Static Pool
   Information 表脚注 1）。它的 90+ 天逾期因此含 120–212 天那一段。2014-08..2015-04 合计里
   只有它一家，此后权重一路降到千分之几，照实并入、页尾写明。它的服务报告没有
   「Loans by Borrower Status」表，P&I / 逾期 / forbearance / deferment / 修改五项只能取 xlsx。
4. **表内 / 表外按「当期文件」的归属回溯整条历史**：文件只给当前归属，不给归属变化史。
   2025-09 / 2026-03 / 2026-08 / 2026-09 四期文件的归属逐个相同。
5. **范围 = 这份文件里的 41 个 SMB Private Education Loan Trust。**来源页另列的
   2020-PT-A / 2020-PT-B（pass-through）与 2024-R1（repackaging）不在文件里，也不进合计。
6. **CPR、债券余额、超额抵押、累计违约 / 回收不做合计**：since-issued CPR 与累计违约 /
   回收都是「自发行以来」的累计量，跨不同账龄的信托相加没有指称；超额抵押的债券口径不统一
   （2014-A 报告注明只按 A/B 级「rated」债券算，不含 C 级），反推的债券余额合计会少算
   —— 误差不可控，不上页。
7. **清仓赎回**：2015-A 最后一期 2026-07、2015-C 最后一期 2026-08（文件里带 `*`）。
   退出那个月（2026-08 / 2026-09）起合计里少一个高账龄信托 —— 由本模块写进
   series/slm_breaks.csv，页面画成口径断点。新信托加入不画断点（每年 1–6 个、2021 年起 3–6 个，是合计的常态）。
8. **信托子页的标签会错**：2015-C 子页标「April 2020」的链接指向的是 3 月那份
   （DistRpt15-C_20200415.pdf，与「March 2020」重复），4 月那份（…_20200515.pdf）页上没挂。
   所以本模块现验时一律用报告**自己第 I.A 节的列头日期**认月份，不信链接标签。

━━ 重述 ━━
官方每期整表重出全部历史，会悄悄改旧格：2026-03 那期与 2026-09 那期比，2021-C 的
2026-03 那一格六个比率都动了（最大 3.2e-06）；2025-09 那期与 2026-09 比，2024-A 第 1 期
累计违约从 9.77e-06 改成 0。所以本模块对已入库的月份**永不覆盖**：现算值与库内值
超过写盘精度的差写进 cache/slm/restatements.csv 供人判（monthly_run 的
`report_restatement_logs()` 会在每轮日志末尾点名），只追加库里没有的新月份。

━━ 发布节奏（HTTP Last-Modified，13 期，2026-11-09 实测）━━
数据月 → xlsx 上传日（月末后第几天）：
  2025-09→10-24(24)  2025-10→11-13(13)  2025-11→12-08(8)   2025-12→01-13(13)
  2026-01→02-27(27)  2026-02→03-19(19)  2026-03→04-08(8)   2026-04→05-12(12)
  2026-05→06-11(11)  2026-06→07-13(13)  2026-07→08-13(13)  2026-08→09-14(14)
  2026-09→10-13(13)
中位第 13 天，最早第 8 天，最晚第 27 天。2025-08 及更早按同一命名探不到（只为测节奏才探，
fetcher 本身从不拼 URL）。⚠ Last-Modified 是资产最后一次被改的时间，**被重传过的期次会显得
更晚**（第 24 / 27 天那两期可能就是），分不出来。文件自身 docProps 的修改时间（2026-09 那期
2026-10-07）早于上传日约一周。所以 LAG 照最晚值 27 给（红点要上界），闸门照最早值第 8 天
（EARLY_BY 让闸门第 7 天开），见 docs/CRON_WIRING.md §2.3。
本源**不自述发布日**（文件里只有数据截止日），不写 series/source_dates.csv。
季末月与常规月同节奏（2026-03→第 8 天、2026-06→第 13 天、2026-09→第 13 天）。

━━ 护栏（任一不过就抛异常，旧 CSV 原地不动）━━
· 来源页恰好一个 Trust_Performance 链接；文件名日期 = Performance!B1「As of …」。
· 10 个必需指标块按标题开头各命中恰好一块；贷款修改的日期型块恰好一块。
· 每块信托集合相同，= 表内 ∪ 表外（去 `*`），两表不重叠；`*` 标记两处一致；
  已入库的信托不许从文件里消失，首月不许变。
· 日期块：表头逐月连续、末月 = 截止月；每个信托有值格连续、各块首末月一致；
  未带 `*` 的信托末月 = 截止月，带 `*` 的早于它。
· 期数块：第 1..n 期连续、n = 日期块月数；by Period / by Date 两块逐格相同。
· 数值范围：池因子 (0, 1.2]，各比率 [0, 1]。
· 新信托接入时：最新服务报告两期的池余额 = 因子 × 交割日池余额（差 ≤ $1）。
· 库里已有的月份，现算结果里必须还在（不许静默缩短历史）。
"""
import csv
import datetime as dt
import html as htmlmod
import importlib.util
import os
import re
import time
import urllib.request

SOURCE_URL = 'https://www.salliemae.com/investors/asset-backed-securities/'
SITE = 'https://www.salliemae.com'
TRUST_URL = SOURCE_URL + 'smb/{slug}/'

CSV_NAME = 'slm.csv'
TRUSTS_NAME = 'slm_trusts.csv'
BREAKS_NAME = 'slm_breaks.csv'
RESTATE_NAME = 'restatements.csv'      # 落 cache/slm/restatements.csv（monthly_run 认这个裸名）

_UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
       '(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36')

# 列 → 写盘小数位。顺序就是 CSV 列序。
COLUMNS = [
    ('n_trusts', 0),             # 当月有报告的信托数
    ('pool_bal_usdbn', 6),       # 池余额合计（本金 + 待资本化利息），$bn
    ('pool_bal_onbs_usdbn', 6),  # 其中表内信托
    ('pool_bal_offbs_usdbn', 6), # 其中表外信托
    ('pi_bal_usdbn', 6),         # P&I 还款余额合计（当期 + 三档逾期，不含 forbearance）
    ('age_wavg_periods', 2),     # 池余额加权的发行后期数（第 1 期 = 1）
    ('pi_share_pct', 4),         # P&I 还款余额 ÷ 池余额
    ('anyrepay_share_pct', 4),   # 任意还款状态余额 ÷ 池余额
    ('deferment_pct', 4),        # deferment ÷ (P&I + forbearance + deferment)
    ('forbearance_pct', 4),      # forbearance ÷ (P&I + forbearance)
    ('dq30_59_pct', 4),          # 30-59 天逾期 ÷ P&I
    ('dq60_89_pct', 4),          # 60-89 天逾期 ÷ P&I
    ('dq90p_pct', 4),            # 90+ 天逾期 ÷ P&I
    ('dq30p_pct', 4),            # 30+ 天逾期合计 ÷ P&I（= 三档之和，同分母）
    ('defaults_usdmn', 3),       # 当期违约本金（gross principal realized loss，periodic），$mn
    ('ann_default_pct', 4),      # 12 × 当期违约本金 ÷ P&I
    ('loan_mod_pct', 4),         # 修改中余额 ÷ P&I
]
COL_NAMES = [c for c, _ in COLUMNS]
DEC = dict(COLUMNS)

# 指标块：标题开头（各期措辞会在尾部增删）→ 内部键。'mod' 另按表头类型分出日期块与期数块。
BLOCKS = {
    'factor': r'^Pool Balance as a % of Original Pool Balance',
    'pi':     r'^Loans in P&I Repayment as a % of Current Pool Balance',
    'anyrep': r'^Loans in Any Type of Repayment as a % of Current Pool Balance',
    'defer':  r'^Deferment as a % of Loans in P&I Repayment, Forbearance and Deferment',
    'forb':   r'^Forbearance as a % of Loans in P&I Repayment and Forbearance',
    'dq30':   r'^30-59 Day Delinquencies as a % of Loans in P&I Repayment',
    'dq60':   r'^60-89 Day Delinquencies as a % of Loans in P&I Repayment',
    'dq90':   r'^90\+ Day Delinquencies as a % of Loans in P&I Repayment',
    'anndef': r'^Annualized Periodic Defaults as a % of Loans in P&I Repayment',
}
MOD_BLOCK = r'^Loan Modification'
_TRUST_RE = re.compile(r'^\d{4}-[A-Z]{1,2}\d?\*?$')
_LINK_RE = re.compile(r'href="([^"]*/Trust_Performance_(\d{2})(\d{2})(\d{4})\.xlsx)"', re.I)


class SlmFetchError(RuntimeError):
    pass


# ── 网络 ────────────────────────────────────────────────────────────────
def _http_get(url, timeout=90, tries=3, pause=2.0):
    """先 curl_cffi（chrome 指纹），没装就 urllib。2026-11-09 实测两条都通（站点不拦 UA / TLS）。"""
    last = None
    for k in range(tries):
        try:
            try:
                from curl_cffi import requests as cr
            except ImportError:
                cr = None
            if cr is not None:
                r = cr.get(url, impersonate='chrome', timeout=timeout)
                if r.status_code != 200:
                    raise SlmFetchError('HTTP %s %s' % (r.status_code, url))
                return r.content, {k_.lower(): v for k_, v in r.headers.items()}
            req = urllib.request.Request(url, headers={'User-Agent': _UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read(), {k_.lower(): v for k_, v in r.headers.items()}
        except Exception as e:                       # noqa: BLE001
            last = e
            if k + 1 < tries:
                time.sleep(pause * (k + 1))
    raise SlmFetchError('下载失败 %s: %r' % (url, last)) from last


def _abs(href):
    href = htmlmod.unescape(href)
    return href if href.startswith('http') else SITE + href


def perf_link(page_html):
    """来源页 → (xlsx 绝对 URL, 截止日 date)。恰好一个链接，否则抛。"""
    hits = {(_abs(h), dt.date(int(y), int(m), int(d)))
            for h, m, d, y in _LINK_RE.findall(page_html)}
    if len(hits) != 1:
        raise SlmFetchError('来源页 Trust_Performance 链接应恰好 1 个，实际 %d 个：%s'
                            % (len(hits), sorted(hits)))
    return hits.pop()


def latest_month(cache_dir=None):
    """官方当前最新数据月 'YYYY-MM'（只读来源页，一个请求）。"""
    body, _ = _http_get(SOURCE_URL)
    _url, asof = perf_link(body.decode('utf-8', 'replace'))
    return _ym(asof)


# ── 月份小工具 ─────────────────────────────────────────────────────────
def _ym(d):
    return '%04d-%02d' % (d.year, d.month)


def _add_months(ym, k):
    t = int(ym[:4]) * 12 + (int(ym[5:7]) - 1) + k
    return '%04d-%02d' % (t // 12, t % 12 + 1)


def _months_between(a, b):
    """'YYYY-MM' a → b 相隔几个月（b − a）。"""
    return (int(b[:4]) * 12 + int(b[5:7])) - (int(a[:4]) * 12 + int(a[5:7]))


def _num(v, where):
    if v is None:
        return None
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise SlmFetchError('%s 不是数值：%r' % (where, v))
    return float(v)


# ── 工作簿解析 ─────────────────────────────────────────────────────────
def _bs_lists(wb):
    """两张 Orig 表的信托名行 → ({'2015-B': 'on', '2015-A': 'off', …}, 带 * 的集合)。"""
    out, starred = {}, set()
    for sheet, tag in (('Orig. Characteristics On BS', 'on'), ('Orig. Characteristics Off BS', 'off')):
        if sheet not in wb.sheetnames:
            raise SlmFetchError('工作簿缺表 %r（现有 %s）' % (sheet, wb.sheetnames))
        names = None
        for row in wb[sheet].iter_rows(min_row=1, max_row=12, values_only=True):
            cand = [v.strip() for v in row if isinstance(v, str) and _TRUST_RE.match(v.strip())]
            if len(cand) >= 3:
                names = cand
                break
        if not names:
            raise SlmFetchError('%s 前 12 行找不到信托名行' % sheet)
        for n in names:
            bare = n.rstrip('*')
            if bare in out:
                raise SlmFetchError('信托 %s 同时出现在表内与表外' % bare)
            out[bare] = tag
            if n.endswith('*'):
                starred.add(bare)
    return out, starred


def _perf_blocks(ws):
    """Performance 表 → (全部行, {标题: (表头 {列号: 1..n 或 datetime}, {信托: {列号: 值}})})。"""
    rows = list(ws.iter_rows(values_only=True))
    blocks, i = {}, 0
    while i < len(rows):
        b = rows[i][1] if len(rows[i]) > 1 else None
        if isinstance(b, str) and not _TRUST_RE.match(b.strip()) and i + 1 < len(rows):
            hdr = {j: v for j, v in enumerate(rows[i + 1]) if j >= 2 and v is not None}
            if hdr and all(isinstance(v, (int, float, dt.datetime)) and not isinstance(v, bool)
                           for v in hdr.values()):
                title = ' '.join(b.split())
                data, k = {}, i + 2
                while (k < len(rows) and isinstance(rows[k][1], str)
                       and _TRUST_RE.match(rows[k][1].strip())):
                    data[rows[k][1].strip()] = {j: rows[k][j] for j in hdr}
                    k += 1
                if title in blocks:
                    raise SlmFetchError('Performance 表有两个同名块：%s' % title)
                blocks[title] = (hdr, data)
                i = k
                continue
        i += 1
    return rows, blocks


def _is_date_block(hdr):
    kinds = {type(v) for v in hdr.values()}
    if kinds == {dt.datetime}:
        return True
    if all(isinstance(v, (int, float)) for v in hdr.values()):
        return False
    raise SlmFetchError('表头混了日期与期数：%r' % sorted(kinds, key=str))


def parse_workbook(path):
    """→ dict(asof='YYYY-MM', bs={信托: on/off}, retired=set, first={信托: 首月},
               last={信托: 末月}, m={键: {信托: {月: 值}}})。护栏见模块 docstring。"""
    import openpyxl
    wb = openpyxl.load_workbook(path, data_only=True)
    bs, starred = _bs_lists(wb)
    if 'Performance' not in wb.sheetnames:
        raise SlmFetchError('工作簿缺 Performance 表')
    rows, blocks = _perf_blocks(wb['Performance'])

    # 截止日：B1「*As of September 30 , 2026」
    asof_txt = ' '.join(str(rows[0][1] or '').replace(',', ' , ').split())
    mm = re.search(r'As of ([A-Za-z]+) (\d{1,2}) , (\d{4})', asof_txt)
    if not mm:
        raise SlmFetchError('Performance!B1 认不出截止日：%r' % rows[0][1])
    asof = dt.datetime.strptime('%s %s %s' % mm.groups(), '%B %d %Y').date()
    asof_ym = _ym(asof)

    found = {}
    for key, pat in BLOCKS.items():
        hit = [t for t in blocks if re.match(pat, t)]
        if len(hit) != 1:
            raise SlmFetchError('指标块 %s（%s）应命中 1 块，实际 %d：%s' % (key, pat, len(hit), hit))
        found[key] = blocks[hit[0]]
    mods = [blocks[t] for t in blocks if re.match(MOD_BLOCK, t)]
    mod_d = [b for b in mods if _is_date_block(b[0])]
    mod_p = [b for b in mods if not _is_date_block(b[0])]
    if len(mod_d) != 1 or len(mod_p) > 1:
        raise SlmFetchError('贷款修改块应为 1 个日期型 + 至多 1 个期数型，实际 %d + %d'
                            % (len(mod_d), len(mod_p)))
    found['mod'] = mod_d[0]

    trusts = set(bs)
    for key, (hdr, data) in found.items():
        names = {t.rstrip('*') for t in data}
        if names != trusts:
            raise SlmFetchError('块 %s 的信托集合与 Orig 两表不一致：多 %s 少 %s'
                                % (key, sorted(names - trusts), sorted(trusts - names)))
        perf_star = {t.rstrip('*') for t in data if t.endswith('*')}
        if perf_star != starred:
            raise SlmFetchError('块 %s 的 * 标记与 Orig 表不一致：%s vs %s'
                                % (key, sorted(perf_star), sorted(starred)))

    # 1) 日期块：每个信托的首末月（各块必须一致），有值格连续
    first, last, out = {}, {}, {}
    for key, (hdr, data) in found.items():
        if not _is_date_block(hdr):
            continue
        cols = sorted(hdr)
        months = [_ym(hdr[j]) for j in cols]
        for a, b in zip(months, months[1:]):
            if b != _add_months(a, 1):
                raise SlmFetchError('块 %s 表头月份不连续：%s → %s' % (key, a, b))
        if months[-1] != asof_ym:
            raise SlmFetchError('块 %s 表头末月 %s ≠ 截止月 %s' % (key, months[-1], asof_ym))
        out[key] = {}
        for t_raw, vals in data.items():
            t = t_raw.rstrip('*')
            have = [(months[i], _num(vals[j], '%s/%s/%s' % (key, t, months[i])))
                    for i, j in enumerate(cols) if vals[j] is not None]
            if not have:
                raise SlmFetchError('块 %s 信托 %s 一格都没有' % (key, t))
            ms = [m for m, _ in have]
            if ms != [_add_months(ms[0], i) for i in range(len(ms))]:
                raise SlmFetchError('块 %s 信托 %s 有值格不连续：%s..%s 共 %d 格'
                                    % (key, t, ms[0], ms[-1], len(ms)))
            if t in first and (first[t], last[t]) != (ms[0], ms[-1]):
                raise SlmFetchError('信托 %s 在不同日期块里首末月不一致：%s..%s vs %s..%s（块 %s）'
                                    % (t, first[t], last[t], ms[0], ms[-1], key))
            first[t], last[t] = ms[0], ms[-1]
            out[key][t] = dict(have)
    if set(first) != trusts:
        raise SlmFetchError('日期块没覆盖到全部信托：缺 %s' % sorted(trusts - set(first)))
    for t in trusts:
        if t in starred:
            if last[t] >= asof_ym:
                raise SlmFetchError('信托 %s 带 *（已清仓赎回）却报到了截止月 %s' % (t, asof_ym))
        elif last[t] != asof_ym:
            raise SlmFetchError('信托 %s 未带 * 而末月 %s ≠ 截止月 %s（停报却没标赎回？）'
                                % (t, last[t], asof_ym))

    # 2) 期数块：第 1..n 期连续、n = 日期块月数，第 k 期 = 首月 + k−1
    for key, (hdr, data) in found.items():
        if _is_date_block(hdr):
            continue
        cols = sorted(hdr)
        if [hdr[j] for j in cols] != list(range(1, len(cols) + 1)):
            raise SlmFetchError('块 %s 期数表头不是 1..n' % key)
        out[key] = {}
        for t_raw, vals in data.items():
            t = t_raw.rstrip('*')
            seq = [vals[j] for j in cols]
            n = sum(v is not None for v in seq)
            if any(v is None for v in seq[:n]) or any(v is not None for v in seq[n:]):
                raise SlmFetchError('块 %s 信托 %s 期数格不连续' % (key, t))
            span = _months_between(first[t], last[t]) + 1
            if n != span:
                raise SlmFetchError('块 %s 信托 %s 有 %d 期，而日期块是 %s..%s 共 %d 个月'
                                    % (key, t, n, first[t], last[t], span))
            out[key][t] = {_add_months(first[t], k): _num(seq[k], '%s/%s/第%d期' % (key, t, k + 1))
                           for k in range(n)}

    # 3) 见证：贷款修改 by Period 与 by Date 逐格相同（期数 ↔ 日历月映射的官方内证）
    if mod_p:
        hp, dp = mod_p[0]
        cols = sorted(hp)
        for t_raw, vals in dp.items():
            t = t_raw.rstrip('*')
            seq = [float(vals[j]) for j in cols if vals[j] is not None]
            dseq = [out['mod'][t][m] for m in sorted(out['mod'][t])]
            if len(seq) != len(dseq) or any(abs(a - b) > 1e-12 for a, b in zip(seq, dseq)):
                raise SlmFetchError('映射见证失败：信托 %s 的贷款修改 by Period 与 by Date 对不上' % t)

    # 4) 数值范围
    for key, per in out.items():
        hi = 1.2 if key == 'factor' else 1.0
        for t, mv in per.items():
            for m, v in mv.items():
                if not (0.0 <= v <= hi) or (key == 'factor' and v <= 0):
                    raise SlmFetchError('数值越界：%s/%s/%s = %r' % (key, t, m, v))
    return {'asof': asof_ym, 'bs': bs, 'retired': starred, 'first': first, 'last': last,
            'm': out, 'witness': bool(mod_p)}


# ── 服务报告：交割日池余额 ─────────────────────────────────────────────
_DATE = re.compile(r'^\d{2}/\d{2}/\d{4}$')
_AMT = re.compile(r'^\$?[\d,]+\.\d{2}$')
_RPT_RE = re.compile(r'<a\b[^>]*href="([^"]*DistRpt[^"]*\.pdf)"[^>]*>(.*?)</a>', re.I | re.S)


def _pdf_lines(page, tol=2.5):
    """PyMuPDF 的纯文本顺序是乱的：按词坐标重组成行（同一行 y 中心差 ≤ tol）。"""
    ws = sorted(page.get_text('words'), key=lambda w: ((w[1] + w[3]) / 2, w[0]))
    out, cur, cy = [], [], None
    for w in ws:
        y = (w[1] + w[3]) / 2
        if cy is None or abs(y - cy) <= tol:
            cur.append(w)
            cy = y if cy is None else cy
        else:
            out.append([x[4] for x in sorted(cur, key=lambda x: x[0])])
            cur, cy = [w], y
    if cur:
        out.append([x[4] for x in sorted(cur, key=lambda x: x[0])])
    return out


def parse_distrpt(path):
    """服务报告第 I.A 节 → {'cols': [交割日, 上月末, 本月末], 'pool': [三个池余额]}。
    第一行恰好三个日期的是列头，其后第一行以「Pool Balance」开头的就是池余额。"""
    import fitz
    doc = fitz.open(path)
    for pno in range(min(3, len(doc))):
        hdr = None
        for toks in _pdf_lines(doc[pno]):
            dates = [t for t in toks if _DATE.match(t)]
            if hdr is None and len(dates) == 3:
                hdr = [dt.datetime.strptime(d, '%m/%d/%Y').date() for d in dates]
                continue
            if hdr and ' '.join(toks).startswith('Pool Balance'):
                nums = [float(t.replace('$', '').replace(',', '')) for t in toks if _AMT.match(t)]
                if len(nums) != 3:
                    raise SlmFetchError('%s 的 Pool Balance 行应有 3 个金额，实际 %r' % (path, toks))
                return {'cols': hdr, 'pool': nums}
    raise SlmFetchError('%s 前 3 页找不到「三个日期列头 + Pool Balance」' % path)


def _reports(slug):
    """信托子页 → [(标签月 'YYYY-MM', URL)]，按标签月排序。标签可能错（口径坑 8），只作挑选用。"""
    body, _ = _http_get(TRUST_URL.format(slug=slug))
    page = body.decode('utf-8', 'replace')
    reps = []
    for href, lab in _RPT_RE.findall(page):
        lab = ' '.join(re.sub(r'<[^>]+>', ' ', htmlmod.unescape(lab)).split())  # 标签外可能还包着 <span>
        try:
            d = dt.datetime.strptime(lab, '%B %Y').date()
        except ValueError:
            continue
        reps.append((_ym(d), _abs(href)))
    if not reps:
        raise SlmFetchError('信托子页 %s 一份服务报告都没认出来' % slug)
    return sorted(set(reps))


TRUST_FIELDS = ['trust', 'bs', 'first_month', 'last_month', 'retired', 'settlement_date',
                'init_pool_usd', 'report_month', 'report_pool_usd', 'factor_x_init_diff_usd',
                'first_report_label', 'report_url']


def _read_trusts(series_dir):
    p = os.path.join(series_dir, TRUSTS_NAME)
    if not os.path.exists(p):
        return {}
    with open(p, encoding='utf-8', newline='') as f:
        return {r['trust']: r for r in csv.DictReader(f)}


def _ensure_trusts(series_dir, cache_dir, wb):
    """series/slm_trusts.csv 里没有的信托：取它最新一份服务报告，读交割日池余额，
    并用「报告两期池余额 = 因子 × 交割日池余额」现验映射与分母（月份认报告自己的列头）。
    已有的信托只更新 bs / last_month / retired 三格（来自当期文件），交割日池余额永不改。"""
    have = _read_trusts(series_dir)
    gone = set(have) - set(wb['bs'])
    if gone:
        raise SlmFetchError('已入库的信托从当期文件里消失了：%s' % sorted(gone))
    rows = {}
    os.makedirs(os.path.join(cache_dir, 'slm'), exist_ok=True)
    for t in sorted(wb['bs']):
        r = dict(have.get(t, {}))
        if r and r.get('first_month') != wb['first'][t]:
            raise SlmFetchError('信托 %s 的首月从 %s 变成了 %s' % (t, r.get('first_month'), wb['first'][t]))
        if not r:
            reps = _reports(t.lower())
            first_lab, (rep_m, url) = reps[0][0], reps[-1]
            pdf, _ = _http_get(url)
            lp = os.path.join(cache_dir, 'slm', os.path.basename(url))
            with open(lp, 'wb') as f:
                f.write(pdf)
            info = parse_distrpt(lp)
            init = info['pool'][0]
            fac = wb['m']['factor'][t]
            diffs = [(_ym(d), pool, fac[_ym(d)] * init - pool)
                     for d, pool in zip(info['cols'][1:], info['pool'][1:]) if _ym(d) in fac]
            if not diffs:
                raise SlmFetchError('信托 %s 的服务报告（%s）两期都不在当期 xlsx 里，无从现验'
                                    % (t, url.rsplit('/', 1)[-1]))
            if any(abs(d) > 1.0 for _m, _p, d in diffs):
                raise SlmFetchError('信托 %s：因子 × 交割日池余额 ≠ 报告池余额：%r' % (t, diffs))
            if first_lab != wb['first'][t]:
                print('[slm] ⚠ 信托 %s：子页最早报告标签 %s ≠ 日期块首月 %s（子页标签会错，见口径坑 8；'
                      '池余额现验已过，照常接入）' % (t, first_lab, wb['first'][t]))
            m, pool, diff = diffs[-1]
            r = {'trust': t, 'settlement_date': info['cols'][0].isoformat(),
                 'init_pool_usd': '%.2f' % init, 'report_month': m,
                 'report_pool_usd': '%.2f' % pool, 'factor_x_init_diff_usd': '%.4f' % diff,
                 'first_report_label': first_lab, 'report_url': url}
            print('[slm] 新信托 %s：交割日 %s 池余额 $%s，%s 现验差 $%.4f'
                  % (t, r['settlement_date'], r['init_pool_usd'], m, diff))
        r['bs'] = wb['bs'][t]
        r['first_month'] = wb['first'][t]
        r['last_month'] = wb['last'][t]
        r['retired'] = '1' if t in wb['retired'] else '0'
        rows[t] = r
    _write_csv(os.path.join(series_dir, TRUSTS_NAME), TRUST_FIELDS,
               [rows[t] for t in sorted(rows, key=lambda x: (rows[x]['first_month'], x))])
    return {t: float(rows[t]['init_pool_usd']) for t in rows}


# ── 合计 ───────────────────────────────────────────────────────────────
def aggregate(wb, init):
    """→ {月: {列: 值}}。公式见模块 docstring 口径坑 2：先还原各信托的金额，同分母相加再除。"""
    M = wb['m']
    months = sorted({m for t in M['factor'] for m in M['factor'][t]})
    out = {}
    for m in months:
        acc = dict.fromkeys(['pool', 'on', 'off', 'pi', 'any', 'forb', 'defer', 'd30', 'd60',
                             'd90', 'dflt', 'mod', 'age', 'n'], 0.0)
        for t in M['factor']:
            if m not in M['factor'][t]:
                continue
            pool = M['factor'][t][m] * init[t]
            pi = M['pi'][t][m] * pool
            f, d = M['forb'][t][m], M['defer'][t][m]
            forb = f * pi / (1.0 - f)
            defer = d * (pi + forb) / (1.0 - d)
            acc['n'] += 1
            acc['pool'] += pool
            acc['on' if wb['bs'][t] == 'on' else 'off'] += pool
            acc['pi'] += pi
            acc['any'] += M['anyrep'][t][m] * pool
            acc['forb'] += forb
            acc['defer'] += defer
            acc['d30'] += M['dq30'][t][m] * pi
            acc['d60'] += M['dq60'][t][m] * pi
            acc['d90'] += M['dq90'][t][m] * pi
            acc['dflt'] += M['anndef'][t][m] * pi / 12.0
            acc['mod'] += M['mod'][t][m] * pi
            acc['age'] += (_months_between(wb['first'][t], m) + 1) * pool
        pi = acc['pi']
        out[m] = {
            'n_trusts': acc['n'],
            'pool_bal_usdbn': acc['pool'] / 1e9,
            'pool_bal_onbs_usdbn': acc['on'] / 1e9,
            'pool_bal_offbs_usdbn': acc['off'] / 1e9,
            'pi_bal_usdbn': pi / 1e9,
            'age_wavg_periods': acc['age'] / acc['pool'],
            'pi_share_pct': 100 * pi / acc['pool'],
            'anyrepay_share_pct': 100 * acc['any'] / acc['pool'],
            'deferment_pct': 100 * acc['defer'] / (pi + acc['forb'] + acc['defer']),
            'forbearance_pct': 100 * acc['forb'] / (pi + acc['forb']),
            'dq30_59_pct': 100 * acc['d30'] / pi,
            'dq60_89_pct': 100 * acc['d60'] / pi,
            'dq90p_pct': 100 * acc['d90'] / pi,
            'dq30p_pct': 100 * (acc['d30'] + acc['d60'] + acc['d90']) / pi,
            'defaults_usdmn': acc['dflt'] / 1e6,
            'ann_default_pct': 100 * 12 * acc['dflt'] / pi,
            'loan_mod_pct': 100 * acc['mod'] / pi,
        }
    return out


def exit_breaks(wb):
    """清仓赎回退出的月份（= 该信托末月的下一个月）→ 断点行。"""
    by = {}
    for t in sorted(wb['retired']):
        by.setdefault(_add_months(wb['last'][t], 1), []).append(
            '%s 清仓赎回退出' % t)
    return [{'month': m, 'zh': '、'.join(v)} for m, v in sorted(by.items())]


# ── 写盘 ───────────────────────────────────────────────────────────────
def _fmt(col, v):
    if v is None:
        return ''
    d = DEC[col]
    return str(int(round(v))) if d == 0 else '%.*f' % (d, v)


def _write_csv(path, fields, rows):
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator='\n')
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, '') for k in fields})
    os.replace(tmp, path)


def _rawkeep():
    """按路径加载 fetch/rawkeep.py（本模块被 monthly_run 以文件路径加载，裸 import 不可用）。"""
    spec = importlib.util.spec_from_file_location(
        'rawkeep', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'rawkeep.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def download(cache_dir):
    """来源页 → 当期 xlsx，落 cache/slm/ 并存证。返回 (本地路径, 截止月, Last-Modified)。
    来源页只挂最新一期，旧期会被下一期顶掉 —— 所以每期原始字节进 cache/raw/slm/。"""
    d = os.path.join(cache_dir, 'slm')
    os.makedirs(d, exist_ok=True)
    body, _ = _http_get(SOURCE_URL)
    url, asof = perf_link(body.decode('utf-8', 'replace'))
    data, hdr = _http_get(url)
    if data[:2] != b'PK':
        raise SlmFetchError('%s 下回来的不是 xlsx（前 2 字节 %r）' % (url, data[:2]))
    p = os.path.join(d, os.path.basename(url))
    with open(p, 'wb') as f:
        f.write(data)
    _rawkeep().keep('slm', data, 'xlsx', _ym(asof))
    return p, _ym(asof), hdr.get('last-modified')


def update(series_dir, cache_dir):
    """全表重算；只追加 series/slm.csv 里没有的月份，已有月份不覆盖（差异记重述台账）。
    series/slm_trusts.csv 与 series/slm_breaks.csv 每轮按当期文件重写（前者交割日池余额不动）。
    返回新增月份列表。"""
    path, asof, lm = download(cache_dir)
    wb = parse_workbook(path)
    if wb['asof'] != asof:
        raise SlmFetchError('文件名截止月 %s ≠ 表内截止月 %s' % (asof, wb['asof']))
    init = _ensure_trusts(series_dir, cache_dir, wb)
    agg = aggregate(wb, init)

    csv_path = os.path.join(series_dir, CSV_NAME)
    cur = {}
    if os.path.exists(csv_path):
        with open(csv_path, encoding='utf-8', newline='') as f:
            rd = csv.DictReader(f)
            if rd.fieldnames != ['month'] + COL_NAMES:
                raise SlmFetchError('series/slm.csv 列名与 COLUMNS 不符：%s' % rd.fieldnames)
            cur = {r['month']: r for r in rd}
    lost = sorted(set(cur) - set(agg))
    if lost:
        raise SlmFetchError('库里已有的月份在当期文件里算不出来了：%s' % lost)

    # 重述：只记不改
    conflicts = []
    for m, r in cur.items():
        for c in COL_NAMES:
            new = _fmt(c, agg[m][c])
            if r[c] != new and (r[c] == '' or abs(float(r[c]) - float(new)) > 1.01 * 10 ** (-DEC[c])):
                conflicts.append({'month': m, 'column': c, 'stored': r[c], 'official_now': new,
                                  'source': os.path.basename(path), 'seen': dt.date.today().isoformat()})
    if conflicts:
        rp = os.path.join(cache_dir, 'slm', RESTATE_NAME)
        old = []
        if os.path.exists(rp):
            with open(rp, encoding='utf-8', newline='') as f:
                old = list(csv.DictReader(f))
        seen = {(r['month'], r['column'], r['official_now']) for r in old}
        old += [r for r in conflicts if (r['month'], r['column'], r['official_now']) not in seen]
        _write_csv(rp, ['month', 'column', 'stored', 'official_now', 'source', 'seen'], old)
        print('[slm] ⚠ %d 格现算值与库内不同（官方重述？），未覆盖，记入 cache/slm/%s'
              % (len(conflicts), RESTATE_NAME))

    new = sorted(m for m in agg if m not in cur)
    if new:
        rows = [cur[m] if m in cur else dict({'month': m}, **{c: _fmt(c, agg[m][c]) for c in COL_NAMES})
                for m in sorted(set(cur) | set(new))]
        _write_csv(csv_path, ['month'] + COL_NAMES, rows)
    _write_csv(os.path.join(series_dir, BREAKS_NAME), ['month', 'zh'], exit_breaks(wb))
    print('[slm] 截止 %s · %d 个信托（表内 %d / 表外 %d，已赎回 %d）· Last-Modified %s · 新增 %d 个月%s'
          % (asof, len(wb['bs']), sum(v == 'on' for v in wb['bs'].values()),
             sum(v == 'off' for v in wb['bs'].values()), len(wb['retired']), lm, len(new),
             '（%s..%s）' % (new[0], new[-1]) if new else ''))
    return new


if __name__ == '__main__':
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    print(update(os.path.join(_root, 'series'), os.path.join(_root, 'cache')))
