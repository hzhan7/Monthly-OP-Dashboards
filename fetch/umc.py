# -*- coding: utf-8 -*-
r"""联华电子（UMC，2303.TW / NYSE: UMC）月度营收 —— 无人值守抓取模块。

对应 build/specs/umc.py（页面由通用底座 build/single.py 生成），维护一个序列文件：

  series/umc.csv    month, revenue_ntd_mn, revenue_ytd_ntd_mn

两列都是**官方公告原值**（NT$ 千元 ÷ 1000 落成 NT$ 百万，三位小数无损）：
第二列是公司自己公布的「本年累计营收」，不是本模块算出来的。它留在 CSV 里有两个用处，
都不是装饰：① 增量月份的金额由 `本月累计 − 上月累计` 反算（见口径坑 2，公司印错过
单月数但累计数从没错过）；② 增量抓取只需要下载新的那几份 6-K，不必每次重抓 163 份。

────────────────────────────────────────────────────────────────────────
数据源
────────────────────────────────────────────────────────────────────────
1) 主源：SEC EDGAR 的 6-K（data.sec.gov + www.sec.gov/Archives）
   UMC 是在 NYSE 上市的外国私人发行人，每月把台湾那份「营运情形公告」原文作为
   Exhibit 99.x 附在 6-K 里报到 SEC。一份附件一次给齐四个数：
   当月净销售额、去年同月净销售额、本年累计、去年同期累计，外加变动额与变动率。

     清单  https://data.sec.gov/submissions/CIK0001033767.json
     正文  https://www.sec.gov/Archives/edgar/data/1033767/<accno_nodash>/<accno>.txt
           （整份 submission 的合并文本，一次请求拿到全部附件，不必先取 index）

   附件正文长这样（2026-08-06 的 7 月号）：
     "United Microelectronics Corporation August 6, 2026
      This is to report the changes or status of 1) Sales volume, ... for the
      period of July 2026.  1) Sales volume (NT$ Thousand)
      Period Items 2026 2025 Changes %
      July          Net sales  23,844,045  20,040,049  3,803,996  18.98%
      Year-to-Date  Net sales 153,614,609 136,656,663 16,957,946  12.41%"

   **为什么主源是 SEC 而不是公司 IR**：带申明用途的 User-Agent 时 data.sec.gov 与
   Archives 实测 100% 成功（本轮一次性拉了 372 份 6-K，零失败）；而 UMC 自己的
   IR 月营收年表页挂在 Cloudflare 后面，实测单次成功率只有 7%–30%，无人值守下
   每个月都会随机失败，只配做偶发回补，不能当主源。IR 页上挂的那份 xlsx 是过期的
   年度快照（文件内部自述的更新日比 HTTP Last-Modified 还早两年），一律不用。

2) 交叉校验源（只读不写，失败只告警不阻断）
   TWSE OpenAPI https://openapi.twse.com.tw/v1/opendata/t187ap05_L
   「上市公司每月营业收入汇总表」，全市场当期一份 JSON，单位新台币千元。
   2303 是**本国公司**，在 t187ap05_L 里（世芯-KY 3661 那类外国发行人不在这张表，
   走 TPEx 的 mopsfin_t187ap05_O）。只有最新一期、没有历史，所以只能校验最新月。
   实测 2026-07：TWSE 當月營收 23,844,045、累計 153,614,609，与 6-K 逐字相等。

3) 对账用的官方年度数（不入库，只在建库时核过一遍，见「对账」一节）
   20-F 的合并综合损益表 / data.sec.gov 的 XBRL companyfacts
   https://data.sec.gov/api/xbrl/companyfacts/CIK0001033767.json（ifrs-full:Revenue）

────────────────────────────────────────────────────────────────────────
发布节奏（实测，不是公司承诺）
────────────────────────────────────────────────────────────────────────
· 台湾《证券交易法》要求次月 10 日前公告上月营收。UMC 的实际公告日（附件抬头日期）
  163 个月**无一例外落在次月 4–10 日**：
    2025-08→09/04  2025-09→10/07  2025-10→11/06  2025-11→12/04  2025-12→01/07
    2026-01→02/05  2026-02→03/05  2026-03→04/08  2026-04→05/08  2026-05→06/05
    2026-06→07/06  2026-07→08/06
· **6-K 的 EDGAR filingDate 与台湾公告日自 2025-05 起逐月同日**（实测 15 个月零分歧）。
  但更早不是这样：2013–2024 年 UMC 把当月的十几份公告攒成一份 6-K 在月底才报，
  EDGAR 最长滞后 33 天（2013-11 的营收 2014-01-02 才上 EDGAR）；2024 年仍有 14 天
  （2024-10 → 2024-11-14）。**所以不要拿 filingDate 当公告日用在历史上**，
  只有 2025-05 之后两者才等价。
  → 调度：roster LAG 取 (14, 14)。取 14 不是照最近 12 个月（最大 8 天）定的，
    是照最近 24 个月的最坏值（2024-10 那期 14 天）留的余量；季末月与常规月同节奏
    （2025-03→04/10、2025-06→07/07、2025-09→10/07、2025-12→01/07），所以两个数相同。
· UMC **不给营收指引**，所以没有指引桥可建：法说会给的是「wafer shipments 环比 ±x%」
  「ASP（美元）环比 ±x%」「毛利率约 y%」「产能利用率 z%」这类**非营收口径**的指引，
  要折成营收区间得先假设产品结构与汇率，折出来的数没有官方值可以对账。

────────────────────────────────────────────────────────────────────────
口径坑（踩过的，别再踩）
────────────────────────────────────────────────────────────────────────
1. **口径连续起点是 2013-01，不是「最早可得」。** EDGAR 上 UMC 的月营收 6-K 能一直
   翻到 2002-02，但 2012 及以前那批公告的口径与 2013 起**不是同一个东西**：
     · 2012 年自己那 12 份公告加总 = NT$105,998,159 千元；
     · 2013 年那 12 份公告里印的「去年同期」加总 = NT$115,674,763 千元；
     · FY2013 20-F 审计过的 2012 年比较数就是 115,674,763（合并、TIFRS）。
   也就是说 2012 当年报的是旧口径（母公司/未按 TIFRS 合并），2013 起改合并口径并
   把比较数重述了。后果很具体：**公司在 2013 年那 12 份公告里印出来的同比是
   「合并数 ÷ 旧口径数」**——2013 全年 123,811,636 ÷ 105,998,159 − 1 = **+16.81%**，
   而同口径真实增长是 123,811,636 ÷ 115,674,763 − 1 = **+7.03%**。
   → 本序列起点定在 2013-01，且**不入库 2012**：库里没有 2012，底座就算不出 2013 的
     同比，页面上 2013 那 12 个月的同比是空的 —— 这正是想要的结果。
     把 2012 的重述比较数补进来在算术上也能自洽，但那是「比较栏」不是当期公告，
     与全站「入库值必须是当期官方公告原值」的规矩冲突，故不做。

2. **公司印错过单月数，但累计数从没错过 —— 所以单月一律由累计差反算。**
   2016-06-24 那份 6-K（2016-05 营收）印的单月数是 **17,705,227**，而
     · 本年累计 57,873,709 − 上月累计 45,168,482 = **12,705,227**
     · 同一行的「Changes」栏 −225,827 = 12,705,227 − 12,931,054（去年同月）✓
     · 2017-06 那份公告的「去年同月」栏 = 12,705,227 ✓
   四路证据里三路指向 12,705,227，印出来的单月数是把 `1` 打成 `7` 的手误。
   → 本模块新增月份的金额 = `本月累计 − 上月累计`，并拿「Changes」栏做仲裁：
     Changes 栏站累计差那边（2016-05 就是这种）→ **打印告警后照累计差入库**
     （为一个上游手误停掉整页不值当）；Changes 栏反过来站印出的单月数那边
     → 与历史 163 个月的形态相反，**抛异常**交给人判断。
   全 163 个月只此一处四路读数不一致，其余 162 个月完全一致。

3. **附件里的月份名与「for the period of X」两处都会写错，都不能当月份判据。**
     · 2015-03-27 那份（2015-02 营收）表格里的行标签印成 "January"，
       而累计 24,939,478 − 12,883,284 = 12,056,194 与该行金额一致 ⇒ 实为 February；
     · 2016-02-25 那份（2016-01 营收）行标签印成 "December"，而累计 = 单月 ⇒ 实为 January；
     · "for the period of ..." 那句在 2013-09 ~ 2014-01 连着六份都卡在 "July 2013" 没改。
   → 月份判据只有两个：**累计链**（本模块用的）与 EDGAR filingDate（辅助）。

4. **抬头日期的「年」在跨年时会写错。** 2021-12 营收那份（filingDate 2022-01-25）
   抬头印成 "January 6, 2021"，2022-12 营收那份印成 "January 6, 2022" —— 都少了一年。
   → 抬头日期只用来取**月**，年份一律从 filingDate 推。

5. **一份 6-K 里常常混着十几份别的公告**（董事会决议、人事异动、法说会摘要、
   取得处分资产…），营收公告只是其中一个 Exhibit 99.x。判据必须是正文的
   `This is to report the changes` + `Sales volume` + `Net sales` 三者同时出现；
   只按 form=6-K 或按文件名猜会捞进一堆无关件。

6. **HTTP 200 不等于成功。** data.sec.gov / www.sec.gov 在 User-Agent 缺失或不含联系
   方式时会返回一张「Your Request Originated from an Undeclared Automated Tool」的
   **200 页面**，不是 403。所以本模块每一次取回都同时校验
   ① 响应体长度下限、② 目标标记串确实在体内、③ 未命中封禁页特征串。
   （对照：MOPS 实测返回 200 + 800 字节 WAF 页；GUC 不存在的新闻稿 slug 是 302 跳
   /en、跟随后 200 + 172,215 字节壳页 —— 都是按状态码校验会被骗过去的。）

7. **重述**：已入库月份与官方重新读到的值不一致时**抛异常**，不悄悄改写、不追加，
   由人判断是重述、口径变更还是解析变形。同 fetch/tsm.py 口径坑 6 / fetch/guc.py。
   本模块每次固定回看最近 `DRIFT_BACK` 份营收公告做这项体检。

8. **2019-10 USJC 并表**是真断点。UMC 2019-09-25 公告已取得全部政府核准、
   交割日 2019-10-01，三重富士通半导体（MIFS，更名 USJC）自 2019-10 起 100% 并表。
   ⇒ 2019-10 ~ 2020-09 共 12 个月的同比里含一块无机增量，与前后不可比。
   登记进 build/specs/umc.py 的 `breaks`（不剔除数据 —— 营收本身是真实的合并数，
   不可比的是同比）。

────────────────────────────────────────────────────────────────────────
对账（建库时逐年核过，不是「看起来对」）
────────────────────────────────────────────────────────────────────────
· 月度加总 vs **官方年度**（20-F 合并综合损益表 / XBRL ifrs-full:Revenue），单位 NT$ 千元：
    2013 123,811,636 | 2014 140,012,076 | 2015 144,830,421 | 2016 147,870,124
    2017 149,284,706 | 2018 151,252,571 | 2019 148,201,641 | 2020 176,820,914
    2021 213,011,018 | 2022 278,705,264 | 2023 222,533,000 | 2024 232,302,584
    2025 237,553,199
  **13 个完整年度 diff 全部 = 0**（2013/2014 取自 FY2013、FY2014 20-F 正文，
  2015–2024 取自 XBRL，2025 取自 FY2025 20-F 正文）。
· 月度加总 vs **官方季度**（季报 6-K 的合并损益表）：抽查 2023Q1–2026Q2 共 11 个季度，
  逐季金额在对应季报正文中**逐字命中**，例如 2026Q2 = 22,663,945 + 22,943,755 +
  23,124,962 = 68,732,662。
· vs **第三源** TWSE OpenAPI t187ap05_L（2026-07 当期）：
  当月 23,844,045 / 累计 153,614,609，与 6-K **逐字相等**，diff = 0。
  ⇒ 本页的季度聚合、YTD、TTM 同比全部合法：UMC 功能货币与表达货币均为新台币
    （20-F: "The functional currency of ... is the New Taiwan dollar"），
    月营收是原生记账数不是折算值，不存在世芯-KY（3661）那种逐月折算导致的
    「十二个月相加 ≠ 官方本年累计」。
"""

from __future__ import annotations

import csv
import html as _html
import json
import os
import re
import ssl
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

CIK = 1033767
SUB_URL = f'https://data.sec.gov/submissions/CIK{CIK:010d}.json'
ARCH = f'https://www.sec.gov/Archives/edgar/data/{CIK}/%s/%s.txt'
TWSE_API = 'https://openapi.twse.com.tw/v1/opendata/t187ap05_L'
TWSE_CODE = '2303'

START_MONTH = '2013-01'
COLUMNS = ['month', 'revenue_ntd_mn', 'revenue_ytd_ntd_mn']

# SEC 要求 UA 里带申明用途与联系方式；不带会拿到 200 + 封禁页（口径坑 6）
_UA = 'monthly-op-dashboards/1.0 (hzhan@outlook.com)'
_CTX = ssl.create_default_context()

# 最多往回翻多少份 6-K（UMC 一年约 40 份，翻 40 份≈覆盖一年）
MAX_SCAN = 40
# 每次固定回看多少份**营收公告**做重述体检
DRIFT_BACK = 3

_MIN_SUB = 20_000          # submissions JSON 实测 117KB
_MIN_TXT = 5_000           # 单份 6-K 合并文本实测 20KB~2MB
_BLOCK = ('Undeclared Automated Tool', 'Request Rate Threshold Exceeded',
          'You have been blocked')

_MON = {m: i + 1 for i, m in enumerate(
    ['January', 'February', 'March', 'April', 'May', 'June',
     'July', 'August', 'September', 'October', 'November', 'December'])}


class UmcFetchError(RuntimeError):
    """本模块的故障出口。抓不到 / 认不出来一律抛它，不返回 None 掩盖故障。"""


# ══════════════════════════════════════════════════════════════════════════
# HTTP —— 200 不等于成功（口径坑 6）
# ══════════════════════════════════════════════════════════════════════════
def _get(url, *, min_bytes, must_contain=(), tries=3):
    last = None
    for _ in range(tries):
        try:
            req = urllib.request.Request(url, headers={
                'User-Agent': _UA, 'Accept-Encoding': 'gzip, deflate',
                'Accept': '*/*'})
            with urllib.request.urlopen(req, timeout=120, context=_CTX) as fh:
                body = fh.read()
                if fh.headers.get('Content-Encoding') == 'gzip':
                    import gzip
                    body = gzip.decompress(body)
        except Exception as exc:                                   # noqa: BLE001
            last = exc
            time.sleep(1.5)
            continue
        if len(body) < min_bytes:
            raise UmcFetchError(
                f'{url} 只有 {len(body)} 字节（< {min_bytes}），疑似 WAF / 壳页而非真内容')
        head = body[:4000].decode('utf-8', 'ignore')
        for bad in _BLOCK:
            if bad in head:
                raise UmcFetchError(f'{url} 返回 SEC 封禁页（{bad}）—— 检查 User-Agent')
        txt = body.decode('utf-8', 'ignore')
        for need in must_contain:
            if need not in txt:
                raise UmcFetchError(
                    f'{url} 拿到 {len(body)} 字节但里面没有 {need!r} —— '
                    '状态码是 200 也不算成功（口径坑 6）')
        return txt
    raise UmcFetchError(f'{url} 取不到：{last!r}')


def _flat(html_txt):
    """SGML/HTML → 单行纯文本。表格全靠空白分隔，所以压平空白后再上正则。"""
    t = re.sub(r'(?is)<(script|style).*?</\1>', ' ', html_txt)
    t = _html.unescape(re.sub(r'<[^>]+>', ' ', t)).replace('\xa0', ' ')
    return re.sub(r'\s+', ' ', t)


# ══════════════════════════════════════════════════════════════════════════
# EDGAR
# ══════════════════════════════════════════════════════════════════════════
def _recent_6k():
    """最新在前的 [(filing_date, accession)]，只含 6-K / 6-K/A。"""
    txt = _get(SUB_URL, min_bytes=_MIN_SUB,
               must_contain=('"filings"', '"UNITED MICROELECTRONICS'))
    d = json.loads(txt)
    r = d['filings']['recent']
    out = [(r['filingDate'][i], r['accessionNumber'][i])
           for i in range(len(r['accessionNumber']))
           if str(r['form'][i]).startswith('6-K')]
    if not out:
        raise UmcFetchError('submissions JSON 里一份 6-K 都没有（结构变了？）')
    out.sort(reverse=True)
    return out


def _filing_text(acc):
    url = ARCH % (acc.replace('-', ''), acc)
    return _flat(_get(url, min_bytes=_MIN_TXT,
                      must_contain=('UNITED MICROELECTRONICS',)))


_N = r'\(?\s*-?[\d,]+\s*\)?'
_ROW = re.compile(
    rf'([A-Za-z0-9][A-Za-z0-9 \-]{{0,18}}?)\s*Net sales\s+({_N})\s+({_N})\s+'
    rf'({_N})\s*\(?\s*(-?[\d.]+)\s*%?\s*\)?\s*%?')
_MARK = re.compile(r'This is to report the changes')
_HEAD_DATE = re.compile(r'([A-Z][a-z]+)\s+(\d{1,2}),\s*(\d{4})[^A-Za-z0-9]{0,4}$')


def _num(s):
    s = s.strip()
    v = int(re.sub(r'[^\d]', '', s) or 0)
    return -v if s.startswith('(') or s.startswith('-') else v


def _parse_announcement(flat, filing_date):
    """从压平后的 6-K 全文里取出月营收公告。不是营收公告就返回 None（口径坑 5）。

    返回 {'cur','prev','chg','ytd','ytd_prev','ann_month'}，金额单位 NT$ 千元。
    `ann_month` 是「抬头日期的月」，只用来做辅助判据 —— 年份从 filing_date 推，
    因为抬头的年在跨年时会写错（口径坑 4）。
    """
    best = None
    for m in _MARK.finditer(flat):
        seg = flat[m.end(): m.end() + 2500]
        # ⚠ 不能直接拿 '2) Funds lent' 当表格下界：开头那句
        # "...status of 1) Sales volume, 2) Funds lent to other parties, 3) ..."
        # 里就有一个，切下去会把整张表切掉（实测踩过，表现是「一份都解析不出来」）。
        # 表头 'Sales volume (NT$ Thousand)' 全 166 份公告逐字一致，用它定表格起点。
        ts = seg.find('Sales volume (NT$ Thousand)')
        if ts < 0:
            continue
        tail = seg[ts:]
        cut = tail.find('2) Funds lent')
        rows = _ROW.findall(tail[:cut if cut > 0 else 1800])
        if len(rows) < 2:
            continue
        a, b = rows[0], rows[1]
        head = flat[max(0, m.start() - 200): m.start()].strip()
        hm = _HEAD_DATE.search(head)
        ann_month = _MON.get(hm.group(1)) if hm else None
        rec = dict(cur=_num(a[1]), prev=_num(a[2]), chg=_num(a[3]),
                   ytd=_num(b[1]), ytd_prev=_num(b[2]), ann_month=ann_month,
                   filing_date=filing_date)
        # 一份 6-K 里理论上只有一份营收公告；真出现多份时取最新（累计最大）的那份
        if best is None or rec['ytd'] > best['ytd']:
            best = rec
    return best


def _shift(month, k):
    y, m = int(month[:4]), int(month[5:])
    t = (y * 12 + m - 1) + k
    return f'{t // 12}-{t % 12 + 1:02d}'


def _month_from_date(rec):
    """按日期判月：公告月 − 1。抬头的**年**不可信，只取月（口径坑 4）。

    实测 163/163 的公告日都落在数据月的次月 4–10 日，所以「抬头月 − 1」是硬判据；
    抬头日期解析不出来时退回 filingDate 的月 − 1（EDGAR 自 2025-05 起与公告同日，
    更早最多滞后 33 天，所以只在 3 个月的窗口里锚定年份）。
    """
    fy, fm = int(rec['filing_date'][:4]), int(rec['filing_date'][5:7])
    fidx = fy * 12 + fm
    for am in ([rec['ann_month']] if rec['ann_month'] else []) + [fm]:
        cm = am - 1 or 12
        cy = fy - (1 if am == 1 else 0)
        # 数据月必须落在 filingDate 之前 1–4 个月内，否则这个候选不作数
        if 1 <= fidx - (cy * 12 + cm) <= 4:
            return f'{cy}-{cm:02d}'
    return None


def _month_from_chain(rec, ledger):
    """按累计链判月。ledger: {'YYYY-MM': ytd_千元}。判不出来返回 None。"""
    fy = int(rec['filing_date'][:4])
    hit = [m for m, v in ledger.items() if v == rec['ytd']]
    if len(hit) == 1:                              # 已入库月份的复核
        return hit[0]
    if rec['ytd'] == rec['cur']:                   # 1 月：本年累计 == 当月
        return f'{fy}-01'
    for y in (fy, fy - 1):
        known = sorted(m for m in ledger if m.startswith(f'{y}-'))
        if known and rec['ytd'] > ledger[known[-1]]:
            cand = _shift(known[-1], 1)
            if cand.startswith(f'{y}-'):
                return cand
    return None


def _month_of(rec, ledger):
    """判定这份公告是哪个月的。两条互相独立的判据必须一致（口径坑 3/4）。"""
    a, b = _month_from_date(rec), _month_from_chain(rec, ledger)
    if a and b and a != b:
        raise UmcFetchError(
            f'{rec["filing_date"]} 那份公告的两条月份判据打架：'
            f'日期判据 {a} vs 累计链判据 {b}（ytd={rec["ytd"]:,}）—— 本次不写入')
    m = a or b
    if not m:
        raise UmcFetchError(
            f'{rec["filing_date"]} 那份公告判不出月份（ytd={rec["ytd"]:,}，'
            f'抬头月={rec["ann_month"]}）—— 版式变了？本次不写入')
    return m


def _monthly_value(rec, ledger, month):
    """当月金额 = 本月累计 − 上月累计，并用「Changes」栏仲裁（口径坑 2）。"""
    if month.endswith('-01'):
        return rec['ytd']
    prev = ledger[_shift(month, -1)]
    derived = rec['ytd'] - prev
    if derived != rec['cur']:
        ok_derived = (derived - rec['prev'] == rec['chg'])
        ok_printed = (rec['cur'] - rec['prev'] == rec['chg'])
        print(f'[umc][warn] {month} 公告内部不自洽：印出的单月数 {rec["cur"]:,}，'
              f'累计差 {derived:,}（Changes 栏支持'
              f'{"累计差" if ok_derived else ""}{"印出值" if ok_printed else ""}'
              f'{"两者都不" if not (ok_derived or ok_printed) else ""}）'
              f' —— 按累计差入库，见 fetch/umc.py 口径坑 2')
        if ok_printed and not ok_derived:
            raise UmcFetchError(
                f'{month} 反常：Changes 栏支持印出的单月数 {rec["cur"]:,} 而非累计差 '
                f'{derived:,}，与历史 163 个月的形态相反 —— 本次不写入，请人工判断')
    return derived


# ══════════════════════════════════════════════════════════════════════════
# 交叉校验源
# ══════════════════════════════════════════════════════════════════════════
def _twse_latest():
    """TWSE OpenAPI 里 2303 的 (月份, 当月营收, 累计营收)，单位 NT$ 千元。"""
    try:
        txt = _get(TWSE_API, min_bytes=10_000, must_contain=('公司代號',), tries=2)
        for rec in json.loads(txt):
            if rec.get('公司代號') == TWSE_CODE:
                roc = str(rec['資料年月'])                 # 11507 = 2026-07
                month = f'{int(roc[:-2]) + 1911}-{int(roc[-2:]):02d}'
                return (month, float(rec['營業收入-當月營收']),
                        float(rec['累計營業收入-當月累計營收']))
    except Exception as exc:                                       # noqa: BLE001
        print(f'[umc][warn] TWSE OpenAPI 交叉校验跳过：{exc!r}')
    return None, None, None


# ══════════════════════════════════════════════════════════════════════════
# 对外的两个函数
# ══════════════════════════════════════════════════════════════════════════
def _scan(ledger):
    """从最新的 6-K 往回翻，返回 [(month, rec)]（按月份升序）。

    翻的时候不判月份 —— 判月要用累计链，而链必须**从旧往新**接。所以先只按
    「这份公告的本年累计是不是已经在库里」判断该不该继续往回翻，
    收够了再倒过来按 filingDate 升序逐份定月。
    """
    known_ytd = set(ledger.values())
    picked, seen_old = [], 0
    for fdate, acc in _recent_6k()[:MAX_SCAN]:
        try:
            flat = _filing_text(acc)
        except UmcFetchError as exc:
            print(f'[umc][warn] {fdate} {acc} 取不到，跳过：{exc}')
            continue
        rec = _parse_announcement(flat, fdate)
        time.sleep(0.15)                       # SEC 限速 10 req/s，留足余量
        if rec is None:
            continue
        picked.append(rec)
        if rec['ytd'] in known_ytd:            # 这个月已入库
            seen_old += 1
            if seen_old >= DRIFT_BACK:
                break
    picked.sort(key=lambda r: r['filing_date'])
    out, chain = [], dict(ledger)
    for rec in picked:
        month = _month_of(rec, chain)
        chain[month] = rec['ytd']
        out.append((month, rec))
    out.sort(key=lambda x: x[0])
    return out


def latest_month(cache_dir=None):                                  # noqa: ARG001
    """官方源当前最新月 'YYYY-MM'。抓不到一律抛 UmcFetchError。

    走 series/umc.csv 的累计链定月（口径坑 3：附件里的月份名不可信）。
    """
    ledger, _, _ = _read_csv(os.path.join(ROOT, 'series'))
    for fdate, acc in _recent_6k()[:MAX_SCAN]:
        rec = _parse_announcement(_filing_text(acc), fdate)
        time.sleep(0.15)
        if rec is None:
            continue
        # 这里**不**用 _month_of 的双判据互卡：库里落后两个月以上时链判据必然给不出
        # 最新月，而 latest_month 的用途正是「官方已经发到哪个月了」。
        m = _month_from_date(rec) or _month_from_chain(rec, ledger)
        if m:
            return m
    raise UmcFetchError(f'最近 {MAX_SCAN} 份 6-K 里没有一份月营收公告（版式变了？）')


def _read_csv(series_dir):
    path = os.path.join(series_dir, 'umc.csv')
    with open(path, newline='', encoding='utf-8') as fh:
        rows = list(csv.reader(fh))
    header, body = rows[0], [r for r in rows[1:] if r and r[0].strip()]
    if header != COLUMNS:
        raise UmcFetchError(f'series/umc.csv 列不对：{header} != {COLUMNS}')
    ledger = {r[0]: int(round(float(r[2]) * 1000)) for r in body}
    # 自检：单月 ≡ 本月累计 − 上月累计（1 月则 ≡ 本年累计）。两列同时落库的唯一理由
    # 就是这条恒等式能被机器验证 —— 手工改过其中一列会在这里立刻现形。
    for r in body:
        m, mv = r[0], int(round(float(r[1]) * 1000))
        want = ledger[m] if m.endswith('-01') else ledger[m] - ledger.get(_shift(m, -1), 0)
        if _shift(m, -1) not in ledger and not m.endswith('-01'):
            raise UmcFetchError(f'series/umc.csv 在 {m} 之前断月 —— 累计差反算失效')
        if mv != want:
            raise UmcFetchError(
                f'series/umc.csv 内部不自洽：{m} 单月 {mv:,} 但累计差 {want:,}')
    return ledger, body, path


def _fmt(v_k):
    """NT$ 千元 → NT$ 百万，三位小数（无损）。"""
    return f'{v_k / 1000:.3f}'


def update(series_dir, cache_dir=None):                            # noqa: ARG001
    """把新月份追加进 series/umc.csv，返回新增月份列表（升序）。

    幂等：没有新月份时既有行原样搬运、文件**一个字节都不动**。
    已入库值永不覆盖 —— 与官方重新读到的值不一致时**抛异常**（口径坑 7）。
    """
    ledger, body, path = _read_csv(series_dir)
    if not ledger:
        raise UmcFetchError('series/umc.csv 是空的 —— 本模块只做增量，建库请人工')
    last = max(ledger)

    got = _scan(ledger)
    if not got:
        raise UmcFetchError('翻遍最近的 6-K 也没解析出任何一份月营收公告')

    have = {r[0]: r for r in body}

    # ── 重述体检：已入库月份逐格比对，不一致抛异常而不是改写 ──────────────
    drift = []
    for month, rec in got:
        if month not in have:
            continue
        want_ytd = _fmt(rec['ytd'])
        if have[month][2] != want_ytd:
            drift.append((month, have[month][2], want_ytd))
    if drift:
        raise UmcFetchError(
            'UMC 6-K 的本年累计与已入库值不一致（疑似重述或解析变形），本次不写入：\n  '
            + '\n  '.join(f'{m}: 库内累计 {o} vs 官方 {n}' for m, o, n in drift[:5]))

    # ── 追加新月份：必须逐月连续，中间断一个月就停下报错 ────────────────
    added = []
    for month, rec in got:
        if month <= last or month in have:
            continue
        if month != _shift(last, len(added) + 1):
            raise UmcFetchError(
                f'新月份 {month} 与库内末月 {last} 之间断档 —— '
                '累计差反算依赖逐月连续，本次不写入')
        val = _monthly_value(rec, ledger, month)
        row = [month, _fmt(val), _fmt(rec['ytd'])]
        body.append(row)
        ledger[month] = rec['ytd']
        added.append(month)

    if added:
        body.sort(key=lambda r: r[0])
        with open(path, 'w', newline='', encoding='utf-8') as fh:
            w = csv.writer(fh)
            w.writerow(COLUMNS)
            w.writerows(body)

    # ── 第三源交叉校验：只告警，不阻断 ──────────────────────────────────
    newest_month, newest_rec = got[-1]
    tw_month, tw_val, tw_ytd = _twse_latest()
    if tw_month:
        if tw_month != newest_month:
            print(f'[umc][warn] TWSE 最新月 {tw_month} 与 6-K 最新月 {newest_month} 不一致')
        else:
            if abs(tw_ytd - newest_rec['ytd']) > 1.0:
                print(f'[umc][warn] {newest_month} 累计：6-K {newest_rec["ytd"]:,.0f} '
                      f'vs TWSE {tw_ytd:,.0f} NT$K 不符')
            mine = float(ledger.get(newest_month, 0))
            if abs(tw_val - (mine if newest_month.endswith('-01')
                             else newest_rec['ytd'] - ledger.get(
                                 _shift(newest_month, -1), 0))) > 1.0:
                print(f'[umc][warn] {newest_month} 当月：TWSE {tw_val:,.0f} NT$K 与'
                      '累计差反算值不符')
    return added


if __name__ == '__main__':                                         # pragma: no cover
    print('latest_month =', latest_month())
    print('added =', update(os.path.join(ROOT, 'series')))
