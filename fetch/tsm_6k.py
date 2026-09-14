# -*- coding: utf-8 -*-
r"""台积电（2330.TW / NYSE: TSM）月报 6-K 第 3/4 项 —— 背書保證与衍生性商品两张表的无人值守追加模块。

对应 build/mrspecs/_tsm_extra.py（/tsm/ 页「非营收月度披露」板块的 Ex12/13/16/17 与汇总表下半张）。
由 monthly_run.tsm_6k() 单独一步驱动；为什么不是 fetch/tsm.py 的一条慢腿，见那个函数的 docstring。

────────────────────────────────────────────────────────────────────────
1) 维护什么
────────────────────────────────────────────────────────────────────────
  series/tsm_derivatives.csv   month,open_notional_ntd_k,open_fair_value_ntd_k
  series/tsm_guarantees.csv    month,approved_total_k,outstanding_total_k,arizona_approved_k,arizona_outstanding_k

· 表头逐字如上，读到别的表头直接抛。
· 只追加 ≥ FORMAT_FROM（2023-03）的新月份，而且每张表只追加「大于它自己末月」的月份。
  两张表各自 tmp 文件 + os.replace，不是跨文件原子：进程恰好死在两次替换之间时，
  下一轮只补落后的那张（两表失步可自愈）。tmp 文件一律写在 cache/tsm_6k/ 下，
  绝不在 series/ 里留 .tmp（`git add series` 会把它收走）。
· 历史行一个字节不碰：与官方重新读到的值不一致时抛异常，不改写（口径坑 i）。
· 对外接口（monthly_run.tsm_6k() 依赖这四个名字与语义，别改）：
    last_month(series_dir)   → 'YYYY-MM'，两表末月取较小值；表头不对就抛
    fingerprint(series_dir)  → 两表字节的 sha256 hex（补建戳比的就是它）
    update(series_dir, cache_dir, upto, today=None, opener=None) → 新增月份列表（升序）
    STAMP_NAME = '_last_built.sha256'  补建戳的文件名（戳只由 monthly_run.tsm_6k() 写，本模块不写）
  日历预闸、逾期黏警报、补建戳都在调用侧；update() 被调到就去取 (两表末月较小值, upto] 这几个月。

────────────────────────────────────────────────────────────────────────
2) 源
────────────────────────────────────────────────────────────────────────
· 主源：SEC EDGAR 上 TSMC（CIK 0001046179）的月报 6-K。
    清单  https://data.sec.gov/submissions/CIK0001046179.json（只收 form 以 6-K 开头的行）
    正文  https://www.sec.gov/Archives/edgar/data/1046179/<accession 去横线>/<primaryDocument>
  月报就是营收新闻稿那份 6-K 的后半截，以 marker 句开头：
    "This is to report the changes or status of 1) revenue, 2) funds lent to other parties,
     3) endorsements and guarantees, and 4) financial derivative transactions for <Month> <YYYY>"
  清单里的 reportDate = 数据月的月末（42/42 实测），所以定位先按 reportDate（见 candidates()）。
  User-Agent 必须带联系方式，不带会拿到 200 + 封禁页（同 fetch/umc.py 口径坑 6）。
  默认值照抄 fetch/umc.py 的 `_UA`（与 umc 生产同一个值；本模块不许 import umc，
  所以做不到单点引用，由 fetch/test_tsm_6k.py 钉住两处相等），可用环境变量 SEC_EDGAR_UA 覆盖。
  缓存：cache/tsm_6k/<filingDate>_<accession>_<primaryDocument>，存原始 HTML，
  命中就零请求；未命中时 GET 后先写同目录 .tmp 再 os.replace。
· 外部对账（只核两格，取不到只告警不拦，对不上才抛）：
    POST https://mopsov.twse.com.tw/mops/web/ajax_t05st11
    表单 = fetch/alchip.py 的 _FORM + co_id=2330 / year=民國年 / month=两位月，
    UA 同 fetch/mops_remarks.py 的 `_UA`（浏览器 UA；MOPS 不认 SEC 那种声明式 UA）。
  这一页只有汇总：本公司「至本月份累計餘額」（= 核准合计）与「最高額度」（= 6-K 首行限额），
  没有在外余额、没有逐被保证方的行 —— 所以 6 格里它只能证 1 格，外加限额。

────────────────────────────────────────────────────────────────────────
3) 发布节奏（实测，不是公司承诺）
────────────────────────────────────────────────────────────────────────
· 2023-03..2026-08 共 42 期，filingDate 落在月末后第 6–13 天：第 10 天 25 次，第 8、9 天各 6 次，
  第 7 天 2 次，第 13 天 2 次（2023-11-13、2026-07-13），第 6 天 1 次。与营收新闻稿同日同一份 6-K。
· ⇒ LATEST_FILED_DAY = 13：第 13 天之前只看 reportDate 等于月末的件；第 14 天起才放宽候选
  （防 EDGAR 把 reportDate 盖错），且放宽段每次最多下载 WIDEN_MAX_DOCS 份未缓存件。
· 调用侧的开闸日与逾期线复用 tsm 的 LAG−EARLY 与 LAG+GRACE+1（见 monthly_run.tsm_6k()）。

────────────────────────────────────────────────────────────────────────
4) 逐格口径映射（单位 NT$ 仟元，一律不换算）
────────────────────────────────────────────────────────────────────────
· open_notional_ntd_k   = 第 4 项里 entity=='TSMC' 且 instrument=='Forward' 的**全部**块的
                          Outstanding Notional Amount 之和，落 '%d'。
                          (1) not applying / (2) applying hedge accounting 两节合计；不含子公司块。
                          **块主体按清单认**（口径坑 k）：主体恰好是 'TSMC' 才计入；SUBSIDIARY_ENTITIES
                          里的已知子公司块不计入、打一行；不在清单里、名字（大小写不敏感）含 tsmc 或
                          taiwan semiconductor 的主体一律抛，交人判定；其余清单外主体不计入、打一行 ⚠。
                          (1) 节必须恰好 1 块主体为 'TSMC'，否则抛（结构不变式，同见口径坑 k）。
· open_fair_value_ntd_k = 同一批块的 Mark to Market of Outstanding Contracts 之和，
                          括号为负、'-' 为 0，落 '%.1f'。
· approved_total_k      = 第 3 项 guarantor=='TSMC' 各行 Amount approved by the Board of Directors
                          之和，落 '%d'。它等于 MOPS「本公司至本月份累計餘額」（115/08、113/08 实测）。
· outstanding_total_k   = 同一批行的 Outstanding amount 之和，落 '%.1f'。
· arizona_approved_k / arizona_outstanding_k
                        = guarantor=='TSMC' 且脚注写 TSMC Arizona 的**唯一**一行，落 '%.1f'。
解析是**严格语法**：第 3、4 项从标题到结尾逐段消费，剩下任何一个认不出的字都抛。
唯一的预处理是把「数字 + 空格 + ,三位数字」并回一个数：2025-09 那份（filed 2025-10-09）
把 TSMC Nanjing 的名目印成 "8 ,463,834"（HTML 把一个数拆进两段文本）。
这是刻意的「宁可不发」—— TSMC 在这两项里加任何新句式（新工具、新担保人命名、新的 TSMC 命名块主体、新脚注写法），
整月每轮 FAIL，直到有人判定口径、改解析器；而不是悄悄少算一块、多算一行。

────────────────────────────────────────────────────────────────────────
5) 口径坑（踩过的，别再踩）
────────────────────────────────────────────────────────────────────────
a. **TSMC 的 Forward 块可能有两个。** (1) 节一个、(2) 节一个。2023-03..2026-07 的 41 个月里
   15 个月有两块；只取第一块只有 37/41 与库内相等。例 2023-03：
   114,372,932 + 230,810 = 114,603,742；MtM 110,516 + (1,179) = 109,337。
b. **子公司担保人行不计入。** 2023-03..2025-01 共 23 个月第 3 项多一行担保人「TSMC Japan Ltd.」
   （被保证方 TSMC Design Technology Japan）。全部行相加只有 18/41 与库内相等，
   只加 guarantor=='TSMC' 的行才 41/41。MOPS 113/08 本公司累計餘額 626,915,640 = 库内 2024-08，
   「各子公司」那一格 291,060 不在其中。以 'TSMC ' 开头的其他担保人照此不计入、只打印一行；
   其他任何名字直接抛。
c. **星号不是键。** 行数 3–5 在变（含子公司担保人行），亚利桑那按脚注里的公司名认行，
   不按「第三个星号」认。每个星号必须恰好对应一条脚注，脚注句式只认
   "<星号> The guarantee was provided to <X>, a wholly-owned subsidiary of TSMC."（42 份真件归纳）。
d. **限额是合并格。** 同一担保人的第一行印 3 个数（限额、核准、在外），其余行只印 2 个数；
   子公司担保人另起一组、自己也是 3 个数。首行限额必须 ≥ TSMC 各行核准之和。
e. **HTTP 200 不等于成功。** SEC 会回 200 + 「Undeclared Automated Tool」封禁页；
   MOPS 未申报是 200 + 2,503 B「資料庫中查無需求資料」，限流是 200 + 「Overrun - 查詢過於頻繁」。
   所以每次取回都核封禁串、长度下限、必含串，不看状态码。
   长度下限：submissions JSON 实测 132–162KB ⇒ _MIN_SUB 50,000；单份正文不能用 20,000 ——
   recent 670 份 6-K 里 149 份整份 submission 都不到 20,000 B（例 2026-09-01
   tsm-dividendadjustmentx202.htm 17,441 B），cache/tsm_6k 里最小的一份合法正文只有 3,994 B
   （2025-07-17 a2q25presentatione_6kxwm.htm）⇒ _MIN_DOC 2,000，截断另由「</html> 在不在」把关。
f. **远期为 0 的月份历史上缺行，不写 0。** 库内 6 个缺月：2006-01、2006-04、2006-12、2009-09、
   2009-12、2011-06。TSMC Forward 名目合计为 0（没有块或全是 '-'）⇒ 抛异常交人判定
   （所有者 2026-09-14 定：缺行会在 48 个月窗口里造出假时间轴，写 0 又与历史惯例不一致）。
g. **第 3 项为「None.」抛异常。** 早年担保余额为零时 6-K 就这么印；写 0 还是缺行同样交人。
h. **2023-03 之前的版式没有核准栏，拒绝解析。** 2021-08、2022-02 的表头是
   "Guarantor Limit of guarantee Amount Bal. as of period end"，第 4 项的栏名也不同。
   那一段的核准数只来自 MOPS，库内早已录好，本模块不回补。
i. **6-K/A 与重述。** submissions 近 1000 份申报里 6-K/A 只有 6 份，但**月报被 6-K/A 更正过**：前例是
   2020-04-14 的 0001564590-20-016539 —— 文前的 Amendment 说明写明更正的是 4/10 那份月报 6-K
   （0001564590-20-016193）里 TSMC Global 已沖銷契約（Expired Contracts）的名目，其余数字不变；
   reportDate 沿用原件（两份都是 2020-04-10）。那份压平后更正格是并排两个数 "9,957,703 9,755,101"，
   同样的印法落在现行版式里会被严格语法拒绝（抛，交人）。
   照此前例，今天的更正件 reportDate 会是数据月月末、落在候选第一段：已认到原件之后 _scan 仍下载未缓存的
   6-K/A；reportDate 没沿用原件的，**前提是更正件 filingDate 在月末 +45 天内（candidates 第二段上界）**，
   才落在第二段，已认到原件时第二段也只再看 6-K/A（2026-09-14 实拉 submissions：
   2026-05..08 的候选窗口里没有 6-K/A，常规月份不多一个请求）。超窗的更正件（reportDate 没沿用原件、
   filingDate 晚于月末 +45 天）不在该月候选里，会被丢弃 —— 即便被后面某个月的第二段下载到，也因 marker
   月份不符而跳过 —— 重述体检照印「逐格相等」，这一处没有护栏。同一个月找到多份月报时取 6-K/A、
   再取 filingDate 最新的。每次 update() 都拿最近 DRIFT_BACK 个月的月报与库内逐格比，不一致就抛、
   列出 月/列/库内/官方/accession，不改写（同 fetch/umc.py 口径坑 7）；更正的若只是 6 格之外的数
   （如 2020 那次的子公司已沖銷名目），体检照常通过。
j. **本文件与 fetch/test_tsm_6k.py 里不许出现带引号的重述台账文件名字面量**（以 restatements
   结尾的 CSV 名）：monthly_run.check_restatement_logs() 用 RESTATE_LOG 扫整个 fetch/*.py 的源码，
   写一个就会凭空登记出一个写入方。本模块本来也不写重述台账 —— 重述一律抛异常。
k. **第 4 项块主体按清单认，不是「非 'TSMC' 即子公司」。** 旧写法把 entity != 'TSMC' 的块一律当子公司
   静默不计入 —— 母公司块只要换个印法（例如 (2) 节印成 'TSMC Ltd.'），名目就少算一块、照样入库。
   2026-09-14 对 cache/tsm_6k 里 2023-03..2026-08 共 42 份月报真件重跑普查，块主体恰好 5 个：
   TSMC（57 块，(1)(2) 两节，全是 Forward）、TSMC China 与 TSMC Nanjing（各 42 块，(1) 节 Forward）、
   TSMC Global（42 块，(2) 节 Future）、Japan Advanced Semiconductor Mfg., Inc.（JASM，33 块，2023-12 起）。
   后 4 个就是 SUBSIDIARY_ENTITIES。清单外的主体：名字含 tsmc / taiwan semiconductor（大小写不敏感）→ 抛
   （分不清是母公司改了印法还是新的 TSMC 子公司，交人）；其它名字 → 不计入、打一行 ⚠（新的非 TSMC 命名
   子公司不至于每月 FAIL，但日志里看得见；确认是子公司后加进清单）。
   **结构不变式：(1) 节恰好 1 个主体为 'TSMC' 的块，否则抛**（同一批 42 份逐份确认 42/42；(2) 节 15 份 1 块、
   27 份 0 块，所以 (2) 节不设）。它堵的是上面那条 ⚠ 路：两块母公司的月份里，(1) 节母公司块改印成清单外的
   非 TSMC 名字（如 'The Company'）时，没有这条就只打一行 ⚠（不进末行）、按子公司不计入，静默少算 ——
   2023-03 会写成 230810，真值 114603742。**堵不住的：(2) 节同样改名**，仍只打 ⚠、名目少算一块。

────────────────────────────────────────────────────────────────────────
6) 对账记录与重放命令
────────────────────────────────────────────────────────────────────────
· 2026-09-14：cache/tsm_6k 里 2023-03..2026-07 共 41 份月报逐月严格解析，与两张表 41 个月 × 6 列
  逐格相等（`audit` 回放，0 差异）。
· 2026-08（0001046179-26-000658，filed 2026-09-10）：192,798,341 / 1,582,051；
  657,356,394 / 520,453,981 / 483,851,076 / 346,948,663，首行限额 2,573,007,334；
  MOPS 115/08 本公司至本月份累計餘額 657,356,394、最高額度 2,573,007,334，两格与 6-K 相等。

    python3 fetch/tsm_6k.py                 dry-run：只打印将追加的行（允许联网、会写 cache，不写 series）
    python3 fetch/tsm_6k.py --write         update(upto=上个月)，真追加
    python3 fetch/tsm_6k.py audit           离线：cache 里所有 ≥2023-03 的月报逐月严格解析并与两表逐格比
    --cache DIR / --series DIR              worktree 里演练时指向主 checkout 的 cache
    python3 fetch/test_tsm_6k.py            离线单测（TSM6K_CACHE 可指定真缓存目录）
"""

from __future__ import annotations

import csv
import datetime
import glob
import gzip
import hashlib
import html as _html
import io
import json
import os
import re
import ssl
import sys
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

CIK = 1046179
SUB_URL = f'https://data.sec.gov/submissions/CIK{CIK:010d}.json'
DOC_URL = f'https://www.sec.gov/Archives/edgar/data/{CIK}/%s/%s'

# 照抄 fetch/umc.py 的 _UA（与 umc 生产同一个值）；fetch/test_tsm_6k.py 钉住两处相等。
USER_AGENT = os.environ.get('SEC_EDGAR_UA', 'monthly-op-dashboards/1.0 (hzhan@outlook.com)')
_CTX = ssl.create_default_context()

CACHE_SUB = 'tsm_6k'
STAMP_NAME = '_last_built.sha256'

DER_CSV = 'tsm_derivatives.csv'
GUA_CSV = 'tsm_guarantees.csv'
DER_COLS = ['month', 'open_notional_ntd_k', 'open_fair_value_ntd_k']
GUA_COLS = ['month', 'approved_total_k', 'outstanding_total_k',
            'arizona_approved_k', 'arizona_outstanding_k']

FORMAT_FROM = '2023-03'          # 6-K 第 3 项开始印核准栏的第一个月（口径坑 h）
LATEST_FILED_DAY = 13            # 42 期实测最晚月末后第 13 天（第 3 节）
WIDEN_MAX_DOCS = 4               # 放宽段每次 find() 最多下载几份未缓存件
MAX_SUBMISSION_BYTES = 1_000_000  # 季报 / 年报类 6-K 动辄几 MB，月报 88–112KB
DRIFT_BACK = 3                   # 重述体检回看几个月
MAX_BACKFILL = 3                 # 一次最多补几个月；更多说明断了很久，交人

_MIN_SUB = 50_000                # submissions JSON 实测 132–162KB
_MIN_DOC = 2_000                 # 最小合法正文 3,994 B（口径坑 e）
_BLOCK = ('Undeclared Automated Tool', 'Request Rate Threshold Exceeded',
          'You have been blocked')

_MON = {m: i + 1 for i, m in enumerate(
    ['January', 'February', 'March', 'April', 'May', 'June',
     'July', 'August', 'September', 'October', 'November', 'December'])}
MARKER = re.compile(
    r'This is to report the changes or status of 1\) revenue, 2\) funds lent to other parties, '
    r'3\) endorsements and guarantees, and 4\) financial derivative transactions '
    r'for (?:the period of )?([A-Z][a-z]+) (\d{4})')

HDR_GUAR = ('Guarantor Limit of guarantee Amount approved by the Board of Directors '
            'Outstanding amount')
_S3_TITLE = '3. Endorsements and guarantees'
_S4_TITLE = '4. Financial derivative transactions'
_UNIT = '(in NT$ thousands)'
_S4_H1 = '(1) Derivatives not applying hedge accounting.'
_S4_H2 = '(2) Derivatives applying hedge accounting.'

MOPS_T05ST11 = 'https://mopsov.twse.com.tw/mops/web/ajax_t05st11'
_MOPS_LANDING = 'https://mopsov.twse.com.tw/mops/web/'
_MOPS_FORM = {                   # 抄 fetch/alchip.py 的 _FORM
    'encodeURIComponent': '1', 'step': '1', 'firstin': '1', 'off': '1',
    'keyword4': '', 'code1': '', 'TYPEK2': '', 'checkbtn': '',
    'queryName': 'co_id', 'inpuType': 'co_id', 'TYPEK': 'all', 'isnew': 'false',
}
_MOPS_UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
            '(KHTML, like Gecko) Chrome/126.0 Safari/537.36')      # 同 fetch/mops_remarks.py 的 _UA
_MOPS_NONE = ('資料庫中查無需求資料',)
_MOPS_OVERRUN = ('Overrun', '過於頻繁')
_MOPS_MIN = 5_000                # 实拉 6,723 B；查無 2,503 B

_sleep = time.sleep              # 测试缝：单测里换掉，免得重试退避拖慢


class Tsm6kError(RuntimeError):
    """本模块的故障出口。抓不到 / 认不出来 / 对不上一律抛它，不返回 None 掩盖故障。"""


# ══════════════════════════════════════════════════════════════════════════
# 月份小工具
# ══════════════════════════════════════════════════════════════════════════
def _shift(month, k):
    t = int(month[:4]) * 12 + int(month[5:7]) - 1 + k
    return f'{t // 12}-{t % 12 + 1:02d}'


def _month_end(month):
    y, m = int(month[:4]), int(month[5:7])
    return datetime.date(y + (m == 12), m % 12 + 1, 1) - datetime.timedelta(days=1)


def _months_after(lo, hi):
    """(lo, hi] 里的月份，升序。"""
    out, m = [], _shift(lo, 1)
    while m <= hi:
        out.append(m)
        m = _shift(m, 1)
    return out


# ══════════════════════════════════════════════════════════════════════════
# HTTP —— 200 不等于成功（口径坑 e）
# ══════════════════════════════════════════════════════════════════════════
def _fetch(url, *, headers, data=None, opener=None, timeout=120):
    """→ (body bytes, 落地 URL)。opener 是测试缝：opener(url, data, headers) → bytes。"""
    if opener is not None:
        return opener(url, data, dict(headers)), url
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout, context=_CTX) as fh:
        body = fh.read()
        if (fh.headers.get('Content-Encoding') or '').lower() == 'gzip':
            body = gzip.decompress(body)
        return body, fh.geturl()


def _get_bytes(url, *, min_bytes, must_contain=(), opener=None, tries=3):
    last = None
    for i in range(tries):
        try:
            body, _ = _fetch(url, opener=opener, headers={
                'User-Agent': USER_AGENT, 'Accept-Encoding': 'gzip, deflate', 'Accept': '*/*'})
        except Exception as exc:                                   # noqa: BLE001
            last = exc
            if i + 1 < tries:
                _sleep(1.5 * (i + 1))
            continue
        head = body[:4000].decode('utf-8', 'ignore')
        for bad in _BLOCK:
            if bad in head:
                raise Tsm6kError(f'{url} 返回 SEC 封禁页（{bad}）—— 检查 User-Agent / SEC_EDGAR_UA')
        if len(body) < min_bytes:
            raise Tsm6kError(
                f'{url} 只有 {len(body)} 字节（< {min_bytes}），疑似 WAF / 壳页而非真内容')
        txt = body.decode('utf-8', 'ignore')
        for need in must_contain:
            if need not in txt:
                raise Tsm6kError(f'{url} 拿到 {len(body)} 字节但里面没有 {need!r} —— '
                                 '状态码是 200 也不算成功（口径坑 e）')
        return body
    raise Tsm6kError(f'{url} 取不到（{tries} 次）：{last!r}')


def _get(url, **kw):
    return _get_bytes(url, **kw).decode('utf-8', 'ignore')


def flat(html_txt):
    """HTML → 单行纯文本（抄 fetch/umc.py 的 _flat）。表格全靠空白分隔，压平后再上正则。"""
    t = re.sub(r'(?is)<(script|style).*?</\1>', ' ', html_txt)
    t = _html.unescape(re.sub(r'<[^>]+>', ' ', t)).replace('\xa0', ' ')
    return re.sub(r'\s+', ' ', t)


# ══════════════════════════════════════════════════════════════════════════
# EDGAR
# ══════════════════════════════════════════════════════════════════════════
_SUBS_MEMO = []


def submissions(opener=None):
    """→ [dict(fd, form, acc, doc, size, rd)]，只收 form 以 6-K 开头的行。真网络路径进程内 memo。"""
    if opener is None and _SUBS_MEMO:
        return list(_SUBS_MEMO[0])
    txt = _get(SUB_URL, min_bytes=_MIN_SUB, must_contain=('"filings"',), opener=opener)
    try:
        d = json.loads(txt)
        if int(str(d.get('cik', '0'))) != CIK:
            raise Tsm6kError(f'submissions JSON 的 cik 是 {d.get("cik")!r}，不是 {CIK}')
        r = d['filings']['recent']
        n = len(r['accessionNumber'])
        out = []
        for i in range(n):
            if not str(r['form'][i]).startswith('6-K'):
                continue
            out.append(dict(fd=r['filingDate'][i], form=r['form'][i],
                            acc=r['accessionNumber'][i], doc=r['primaryDocument'][i],
                            size=int(r['size'][i]), rd=r['reportDate'][i]))
    except Tsm6kError:
        raise
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise Tsm6kError(f'submissions JSON 结构认不出：{exc!r}') from exc
    if not out:
        raise Tsm6kError('submissions JSON 里一份 6-K 都没有（结构变了？）')
    if opener is None:
        _SUBS_MEMO[:] = [out]
    return out


def _cache_path(cache_dir, row):
    name = f"{row['fd']}_{row['acc']}_{row['doc'].replace('/', '_')}"
    return os.path.join(cache_dir, CACHE_SUB, name)


def _doc(cache_dir, row, opener=None):
    """→ 扁平正文。先查 cache/tsm_6k；未命中则 GET，写同目录 .tmp 再 os.replace。"""
    p = _cache_path(cache_dir, row)
    if os.path.exists(p):
        with open(p, 'rb') as f:
            return flat(f.read().decode('utf-8', 'replace'))
    url = DOC_URL % (row['acc'].replace('-', ''), row['doc'])
    body = _get_bytes(url, min_bytes=_MIN_DOC, opener=opener)
    if row['doc'].lower().endswith(('.htm', '.html')) and b'</html>' not in body[-4096:].lower():
        raise Tsm6kError(f'{url} 取回 {len(body)} 字节但结尾没有 </html> —— 疑似截断，不入缓存')
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + '.tmp'
    with open(tmp, 'wb') as f:
        f.write(body)
    os.replace(tmp, p)
    if opener is None:
        _sleep(0.15)                       # EDGAR 限速 10 req/s，留足余量
    return flat(body.decode('utf-8', 'replace'))


# ══════════════════════════════════════════════════════════════════════════
# 解析 —— 严格语法（第 4 节末段）
# ══════════════════════════════════════════════════════════════════════════
_N = r'\(\d{1,3}(?:,\d{3})*\)|\d{1,3}(?:,\d{3})*|-'
_ROW = re.compile(
    r"(?P<name>[A-Za-z][A-Za-z.,&'\- ]*?) ?(?P<stars>\*+) "
    r'(?P<nums>(?:' + _N + r')(?: (?:' + _N + r')){1,2}) ')
_FOOT = re.compile(
    r'(?P<stars>\*+) The guarantee was provided to (?P<who>[^*]+?), '
    r'a wholly-owned subsidiary of TSMC\. ')
_BLK = re.compile(
    r'‧ ?(?P<head>[^‧]+?) Margin Payment (?P<margin>' + _N + r') '
    r'Premium Income \(Expense\) (?P<premium>' + _N + r') '
    r'Existing Contracts Outstanding Notional Amount (?P<notional>' + _N + r') '
    r'Mark to Market of Outstanding Contracts (?P<mtm>' + _N + r') '
    r'Cumulative Unrealized Profit/Loss (?P<unreal>' + _N + r') '
    r'Expired Contracts Cumulative Notional Amount (?P<exp_notional>' + _N + r') '
    r'Cumulative Realized Profit/Loss (?P<realized>' + _N + r') '
    r'Equity price linked product \(Y/N\) (?P<eq>[YN]) ')
# 块标题 = "<entity> <instrument>"，instrument 取最后一个词。多词工具名（Cross Currency Swap、
# Interest Rate Swap…）会把前几个词挤进 entity，把 TSMC 自己的块误判成「子公司块」而静默不计 ——
# 所以 entity 里一出现工具类词汇就抛，交人判定口径。
_INSTR_WORD = re.compile(
    r'(?i)\b(?:forwards?|futures?|swaps?|options?|rates?|currency|currencies|interest|cross|'
    r'exchange|contracts?|commodity|commodities|collars?|fx|hedges?|hedging|derivatives?)\b')

# 第 4 项已知的子公司块主体（口径坑 k：2023-03..2026-08 共 42 份月报真件普查）—— 不计入、打一行。
# 登记本表不会让测试变红：fetch/test_tsm_6k.py 的 TestBlockEntityList 用 mock 换成虚构夹具清单，
# 照口径坑 k 登记确认过的子公司（如 'TSMC Arizona'、'WaferTech'）直接加一行即可。
# 只有删掉下面 4 个真件里出现过的名字才会红（TestParse2026_08 / TestReplayCached 按真件钉住）。
SUBSIDIARY_ENTITIES = frozenset({
    'TSMC China',
    'TSMC Nanjing',
    'TSMC Global',
    'Japan Advanced Semiconductor Mfg., Inc.',      # JASM，2023-12 起
})
# 清单外的主体名字里有这些就抛：可能是母公司块换了印法，按子公司静默不计入会少算名目。
_TSMC_LIKE = re.compile(r'(?i)tsmc|taiwan\s*semiconductor')


def num(s):
    """'(7,563,234)' → -7563234；'-' → 0；千分位格式不对就抛。"""
    s = s.strip()
    if s == '-':
        return 0
    neg = s.startswith('(') and s.endswith(')')
    body = s[1:-1] if neg else s
    if not re.fullmatch(r'\d{1,3}(?:,\d{3})*', body):
        raise Tsm6kError(f'认不出的数字格 {s!r}')
    v = int(body.replace(',', ''))
    return -v if neg else v


def marker_month(fl):
    """扁平正文里月报 marker 句给出的月份 'YYYY-MM'；没有 marker 返回 None；多于一句就抛。"""
    hits = MARKER.findall(fl)
    if not hits:
        return None
    if len(hits) > 1:
        raise Tsm6kError(f'一份正文里有 {len(hits)} 句月报 marker：{hits} —— 不知道该认哪一句')
    name, year = hits[0]
    if name not in _MON:
        raise Tsm6kError(f'marker 句的月份名认不出：{name!r}')
    return f'{year}-{_MON[name]:02d}'


def _eat(s, pos, lit, month, what):
    if not s.startswith(lit, pos):
        raise Tsm6kError(f'{month} {what}：期望 {lit!r}，实际是 {s[pos:pos + 120]!r}')
    return pos + len(lit)


def _once(fl, title, start, month):
    n = fl.count(title, start)
    if n != 1:
        raise Tsm6kError(f'{month} 的月报里「{title}」出现 {n} 次（应恰好 1 次）')
    return fl.index(title, start)


def _parse_s3(month, s3, verbose=True):
    if re.match(r'[:：]?\s*(?:\(in NT\$ thousands\)\s*[:：]?\s*)?None\b', s3):
        raise Tsm6kError(
            f'{month} 第 3 项为「None.」—— 本月没有任何背書保證。写 0 还是缺行是口径决定，'
            '交人判定（口径坑 g），本次不写入')
    unit = re.match(r'\(in NT\$ thousands\)[:：]? ', s3)          # 2021/2022 旧版单位后面带全角冒号
    if not unit:
        raise Tsm6kError(f'{month} 第 3 项标题之后：期望 {_UNIT!r}，实际是 {s3[:120]!r}')
    pos = unit.end()
    if not s3.startswith(HDR_GUAR + ' ', pos):
        raise Tsm6kError(
            f'{month} 第 3 项表头不是 2023-03 起那一代（{HDR_GUAR!r}），实际是 '
            f'{s3[pos:pos + 100]!r} —— 2023-03 之前的 6-K 没有核准栏，本模块拒绝解析（口径坑 h）')
    pos += len(HDR_GUAR) + 1

    rows = []
    while True:
        m = _ROW.match(s3, pos)
        if not m:
            break
        rows.append(dict(guarantor=m['name'].strip(), stars=m['stars'],
                         nums=[num(x) for x in m['nums'].split(' ')]))
        pos = m.end()
    foots = {}
    while True:
        m = _FOOT.match(s3, pos)
        if not m:
            break
        if m['stars'] in foots:
            raise Tsm6kError(f'{month} 第 3 项脚注星号 {m["stars"]} 出现两次')
        foots[m['stars']] = m['who'].strip()
        pos = m.end()
    if pos != len(s3):
        raise Tsm6kError(f'{month} 第 3 项有认不出的文字（严格语法）：{s3[pos:pos + 160]!r}')
    if not rows:
        raise Tsm6kError(f'{month} 第 3 项表头之后一行都没有')

    stars = [r['stars'] for r in rows]
    if len(set(stars)) != len(stars) or set(stars) != set(foots):
        raise Tsm6kError(f'{month} 第 3 项行星号 {stars} 与脚注星号 {sorted(foots)} 对不上（口径坑 c）')

    seen, prev, limit = set(), None, None
    for r in rows:
        g = r['guarantor']
        if g != 'TSMC' and not g.startswith('TSMC '):
            raise Tsm6kError(f'{month} 第 3 项出现认不出的担保人 {g!r}（只认 TSMC 与 TSMC 子公司）')
        if g != prev:                                   # 新一组：合并格限额只印在组首行（口径坑 d）
            if g in seen:
                raise Tsm6kError(f'{month} 第 3 项担保人 {g!r} 的行不连续，限额合并格无法归属')
            if len(r['nums']) != 3:
                raise Tsm6kError(f'{month} 第 3 项 {g}{r["stars"]} 是该担保人首行，应有 3 个数，'
                                 f'实际 {len(r["nums"])} 个')
            seen.add(g)
            r['limit'], r['approved'], r['outstanding'] = r['nums']
            if g == 'TSMC':
                limit = r['limit']
        else:
            if len(r['nums']) != 2:
                raise Tsm6kError(f'{month} 第 3 项 {g}{r["stars"]} 不是首行，应有 2 个数，'
                                 f'实际 {len(r["nums"])} 个')
            r['limit'] = None
            r['approved'], r['outstanding'] = r['nums']
        prev = g
        r['party'] = foots[r['stars']]
        r['counted'] = g == 'TSMC'

    tsmc = [r for r in rows if r['counted']]
    if not tsmc:
        raise Tsm6kError(f'{month} 第 3 项没有担保人为 TSMC 的行')
    for r in tsmc:
        if not r['approved'] >= r['outstanding'] >= 0:
            raise Tsm6kError(f'{month} 第 3 项 TSMC{r["stars"]}（{r["party"]}）不满足 核准 ≥ 在外 ≥ 0：'
                             f'{r["approved"]:,} / {r["outstanding"]:,}')
    az = [r for r in tsmc if r['party'] == 'TSMC Arizona']
    if len(az) != 1:
        raise Tsm6kError(f'{month} 第 3 项脚注为 TSMC Arizona 的 TSMC 行有 {len(az)} 行（应恰好 1 行）；'
                         f'脚注：{[r["party"] for r in rows]}')
    approved = sum(r['approved'] for r in tsmc)
    if limit is None or limit < approved:
        raise Tsm6kError(f'{month} 第 3 项 TSMC 首行限额 {limit} 小于 TSMC 各行核准之和 {approved:,}')
    if verbose:
        for r in rows:
            if not r['counted']:
                print(f'[tsm_6k] {month} 第 3 项有子公司担保人行：{r["guarantor"]} → {r["party"]}'
                      f'（核准 {r["approved"]:,}），按口径坑 b 不计入')
    return dict(approved_total_k=approved,
                outstanding_total_k=sum(r['outstanding'] for r in tsmc),
                arizona_approved_k=az[0]['approved'],
                arizona_outstanding_k=az[0]['outstanding'],
                limit_k=limit,
                parties=[{k: r[k] for k in ('guarantor', 'stars', 'party', 'limit', 'approved',
                                            'outstanding', 'counted')} for r in rows])


def _blocks(s4, pos, month, section):
    """逐块消费第 4 项的一节。每块带 kind（口径坑 k）：
    parent = 主体恰好是 'TSMC'（计入）；known = SUBSIDIARY_ENTITIES；unlisted = 清单外且名字不像 TSMC。
    结构不变式（口径坑 k）：(1) 节恰好 1 个 parent 块，否则抛；(2) 节不设。"""
    out = []
    while True:
        m = _BLK.match(s4, pos)
        if not m:
            n = sum(b['kind'] == 'parent' for b in out)
            if section == 1 and n != 1:
                raise Tsm6kError(
                    f'{month} 第 4 项 (1) 节主体恰好是 TSMC 的块有 {n} 个（应恰好 1 个，42/42 份真件如此）—— '
                    '母公司块可能改印成了清单外的名字（按子公司不计入就会少算名目），也可能版式变了；'
                    f'交人判定口径（口径坑 k），本次不写入。本节块主体 {[b["entity"] for b in out]}，'
                    f'节后文字 {s4[pos:pos + 80]!r}')
            return out, pos
        entity, _, instrument = m['head'].strip().rpartition(' ')
        if not entity:
            raise Tsm6kError(f'{month} 第 4 项块标题 {m["head"]!r} 拆不出主体与工具')
        if _INSTR_WORD.search(entity):
            raise Tsm6kError(f'{month} 第 4 项块标题 {m["head"]!r} 的主体里混着工具类词汇 —— '
                             '疑似多词工具名，TSMC 的块可能被误判成子公司块；交人判定口径')
        if entity == 'TSMC':
            if instrument != 'Forward':
                raise Tsm6kError(f'{month} 第 4 项出现 TSMC 的 {instrument} 块 —— 57/57 块实测都是 Forward，'
                                 '新工具进不进名目是口径决定，交人')
            kind = 'parent'
        elif entity in SUBSIDIARY_ENTITIES:
            kind = 'known'
        elif _TSMC_LIKE.search(entity):
            raise Tsm6kError(
                f'{month} 第 4 项 ({section}) 节块标题 {m["head"]!r} 的主体 {entity!r} 不在子公司清单里，'
                '名字却含 TSMC / Taiwan Semiconductor —— 可能是母公司块换了印法（按子公司静默不计入就会少算名目），'
                '也可能是新的 TSMC 子公司；交人判定口径（口径坑 k），本次不写入')
        else:
            kind = 'unlisted'
        out.append(dict(section=section, entity=entity, instrument=instrument,
                        notional=num(m['notional']), mtm=num(m['mtm']),
                        kind=kind, counted=kind == 'parent'))
        pos = m.end()


def _parse_s4(month, s4, verbose=True):
    pos = _eat(s4, 0, _UNIT + ' ', month, '第 4 项标题之后')
    pos = _eat(s4, pos, _S4_H1 + ' ', month, '第 4 项 (1) 节标题')
    b1, pos = _blocks(s4, pos, month, 1)
    pos = _eat(s4, pos, _S4_H2 + ' ', month, '第 4 项 (1) 节之后应是 (2) 节标题（严格语法）')
    b2, pos = _blocks(s4, pos, month, 2)
    if pos != len(s4):
        raise Tsm6kError(f'{month} 第 4 项有认不出的文字（严格语法）：{s4[pos:pos + 160]!r}')
    blocks = b1 + b2
    fwd = [b for b in blocks if b['counted']]
    notional = sum(b['notional'] for b in fwd)
    if notional == 0:
        raise Tsm6kError(
            f'{month} 第 4 项 TSMC Forward 名目合计为 0（{len(fwd)} 块）—— 历史上远期为 0 的月份缺行、'
            '不写 0，写不写交人判定（口径坑 f），本次不写入')
    known = [b for b in blocks if b['kind'] == 'known']
    if verbose and known:
        print(f'[tsm_6k] {month} 第 4 项子公司块按清单不计入（口径坑 k）：'
              + '、'.join(f'({b["section"]}) {b["entity"]} {b["instrument"]}' for b in known))
    for b in blocks:                        # 清单外：不看 verbose，重述体检 / audit 里也要看得见
        if b['kind'] == 'unlisted':
            print(f'[tsm_6k][warn] ⚠ {month} 第 4 项 ({b["section"]}) 节有清单外的块主体 {b["entity"]!r}'
                  f'（{b["instrument"]}，名目 {b["notional"]:,}）—— 名字不含 TSMC，按子公司不计入；'
                  '确认是子公司后加进 SUBSIDIARY_ENTITIES（口径坑 k）')
    return dict(open_notional_ntd_k=notional,
                open_fair_value_ntd_k=sum(b['mtm'] for b in fwd),
                blocks=blocks)


# 唯一的预处理：HTML 把一个数拆进两段文本时，压平后千分位逗号前会多一个空格。
# 实测 2025-09 那份（filed 2025-10-09）把 TSMC Nanjing 的名目印成 "8 ,463,834"。
# 只修「数字 + 空格 + 逗号 + 三位数字」这一种形状，别的一概不猜。
_SPLIT_THOUSANDS = re.compile(r'(\d) (,\d{3})(?!\d)')


def parse(fl, verbose=True):
    """扁平正文 → {month, guar{…}, deriv{…}}。严格语法：认不出就抛 Tsm6kError。"""
    month = marker_month(fl)
    if month is None:
        raise Tsm6kError('正文里没有月报 marker 句（This is to report the changes or status of …）')
    at = MARKER.search(fl).end()
    i3 = _once(fl, _S3_TITLE, at, month)
    i4 = _once(fl, _S4_TITLE, i3, month)
    s3 = _SPLIT_THOUSANDS.sub(r'\1\2', fl[i3 + len(_S3_TITLE):i4].strip()) + ' '
    s4 = _SPLIT_THOUSANDS.sub(r'\1\2', fl[i4 + len(_S4_TITLE):].strip()) + ' '
    return dict(month=month, guar=_parse_s3(month, s3, verbose), deriv=_parse_s4(month, s4, verbose))


def _cells(p):
    g, d = p['guar'], p['deriv']
    return {'open_notional_ntd_k': d['open_notional_ntd_k'],
            'open_fair_value_ntd_k': d['open_fair_value_ntd_k'],
            'approved_total_k': g['approved_total_k'],
            'outstanding_total_k': g['outstanding_total_k'],
            'arizona_approved_k': g['arizona_approved_k'],
            'arizona_outstanding_k': g['arizona_outstanding_k']}


def rows_for(p):
    """→ (衍生品行, 背书保证行)，格式与既有行逐字一致（第 4 节）。"""
    c = _cells(p)
    der = '%s,%d,%.1f' % (p['month'], c['open_notional_ntd_k'], c['open_fair_value_ntd_k'])
    gua = '%s,%d,%.1f,%.1f,%.1f' % (p['month'], c['approved_total_k'], c['outstanding_total_k'],
                                    c['arizona_approved_k'], c['arizona_outstanding_k'])
    return der, gua


# ══════════════════════════════════════════════════════════════════════════
# 定位某个月的月报 6-K
# ══════════════════════════════════════════════════════════════════════════
def candidates(month, subs, today=None):
    """→ 按顺序排的候选行（各带 seg=1/2）。

    第一段：reportDate == 月末(M)、filingDate > 月末、size ≤ MAX_SUBMISSION_BYTES；文件名含 revenue 的排前。
    第二段：只在 today ≥ 月末 + LATEST_FILED_DAY + 1 时启用 —— filingDate 落在 (月末, 月末+45 天]、
            size ≤ 上限的其余 6-K / 6-K/A，按 filingDate 升序（防 EDGAR 把 reportDate 盖错）。
    """
    today = today or datetime.date.today()
    end = _month_end(month)
    es = end.isoformat()
    seg1 = [dict(r, seg=1) for r in subs
            if r['rd'] == es and r['fd'] > es and r['size'] <= MAX_SUBMISSION_BYTES]
    seg1.sort(key=lambda r: ('revenue' not in r['doc'].lower(), r['fd'], r['acc']))
    if today < end + datetime.timedelta(days=LATEST_FILED_DAY + 1):
        return seg1
    lim = (end + datetime.timedelta(days=45)).isoformat()
    ids = {r['acc'] for r in seg1}
    seg2 = [dict(r, seg=2) for r in subs
            if es < r['fd'] <= lim and r['size'] <= MAX_SUBMISSION_BYTES and r['acc'] not in ids]
    seg2.sort(key=lambda r: (r['fd'], r['acc']))
    return seg1 + seg2


def _scan(month, cache_dir, today=None, opener=None, subs=None, verbose=True):
    """→ ((row, parsed) | None, 已读正文份数, 跳过的未缓存份数)。

    · 第一段逐份读；一旦认到 M 的月报，余下未缓存件只有 6-K/A 才下载（普通件跳过）——
      这样已缓存的月份重放是零请求（月末 6-K 这类同 reportDate 的无关件不必下）。
    · 第二段：第一段一份都没认到时整段看；已认到时只再看其中的 6-K/A（reportDate 没沿用原件的更正件，
      口径坑 i）—— 普通件照旧不碰，常规月份不多一个请求。第二段每次最多下载 WIDEN_MAX_DOCS 份未缓存件。
    · marker 缺失的无关件照常跳过、不抛；marker 月份不是 M 的也跳过。
    """
    subs = submissions(opener) if subs is None else subs
    hits, checked, skipped, widened = [], 0, 0, 0
    for r in candidates(month, subs, today):
        if r['seg'] == 2 and hits and r['form'] != '6-K/A':
            continue                       # 已认到月报：第二段只再看 6-K/A
        if not os.path.exists(_cache_path(cache_dir, r)):
            if hits and r['form'] != '6-K/A':
                skipped += 1
                continue
            if r['seg'] == 2:
                if widened >= WIDEN_MAX_DOCS:
                    skipped += 1
                    continue
                widened += 1
        fl = _doc(cache_dir, r, opener)
        checked += 1
        mm = marker_month(fl)
        if mm is None:
            if r['seg'] == 1 and 'revenue' in r['doc'].lower():
                print(f'[tsm_6k][warn] {month}：{r["fd"]} {r["acc"]} {r["doc"]} 是月末营收件，'
                      '却没有月报 marker 句 —— 版式可能变了（逾期黏警报会在第 16 天响）')
            continue
        if mm != month:
            continue
        hits.append((r, parse(fl, verbose)))
    if not hits:
        return None, checked, skipped
    best = max(hits, key=lambda h: (h[0]['form'] == '6-K/A', h[0]['fd'], h[0]['acc']))
    if len(hits) > 1:
        print(f'[tsm_6k] {month} 找到 {len(hits)} 份月报：'
              f'{[(h[0]["form"], h[0]["fd"], h[0]["acc"]) for h in hits]}，取 {best[0]["acc"]}'
              '（6-K/A 优先，再取 filingDate 最新）')
    return best, checked, skipped


def find(month, cache_dir, today=None, opener=None, subs=None, verbose=True):
    """→ (row, parsed) 或 None（源上还没有 M 的月报）。"""
    return _scan(month, cache_dir, today, opener, subs, verbose)[0]


# ══════════════════════════════════════════════════════════════════════════
# 外部对账：MOPS ajax_t05st11（取不到只告警，对不上才抛）
# ══════════════════════════════════════════════════════════════════════════
_MN = r'(-?\d{1,3}(?:,\d{3})*)'
_MOPS_ROW = re.compile(
    r'是否有背書保證資訊 本月增減金額 至本月份累計餘額 最高額度 本公司 [有無] 背書保證資訊 '
    + _MN + ' ' + _MN + ' ' + _MN + r'(?: |$)')
_MOPS_TOSUBS = re.compile(r'本公司對子公司背書保證累計餘額 ' + _MN + r'(?: |$)')


def _mnum(s):
    return int(s.replace(',', ''))


def mops_crosscheck(month, parsed, opener=None):
    """核 6-K 的核准合计与首行限额。通过返回 True；取不到返回 False（只告警）；对不上抛。"""
    y, m = int(month[:4]), int(month[5:7])
    roc = y - 1911

    def warn(why):
        print(f'[tsm_6k][warn] 护栏失效：MOPS t05st11 {month} 本轮取不到（{why}），'
              '本月核准合计未做外部对账（不阻断）')
        return False

    form = dict(_MOPS_FORM, co_id='2330', year=str(roc), month=f'{m:02d}')
    try:
        body, landed = _fetch(MOPS_T05ST11, data=urllib.parse.urlencode(form).encode(),
                              opener=opener, timeout=60,
                              headers={'User-Agent': _MOPS_UA, 'Accept': '*/*',
                                       'Content-Type': 'application/x-www-form-urlencoded'})
    except Exception as exc:                                       # noqa: BLE001
        return warn(f'网络错 {type(exc).__name__}: {str(exc)[:120]}')
    txt = body.decode('utf-8', 'replace')
    if any(k in txt for k in _MOPS_NONE):
        return warn('資料庫中查無需求資料')
    if any(k in txt for k in _MOPS_OVERRUN):
        return warn('限流页 Overrun')
    if not landed.startswith(_MOPS_LANDING):
        return warn(f'落到了 {landed}')
    if len(body) < _MOPS_MIN:
        return warn(f'只有 {len(body)} 字节的认不出的短页')
    fl = flat(txt)
    want = f'民國{roc}年{m:02d}月'
    if want not in fl or '新台幣仟元' not in fl:
        raise Tsm6kError(f'MOPS t05st11 {month} 拿到 {len(body)} 字节，却没有「{want}」「新台幣仟元」—— '
                         f'版式变了？开头：{fl[:160]!r}')
    row, tosubs = _MOPS_ROW.search(fl), _MOPS_TOSUBS.search(fl)
    if not row or not tosubs:
        raise Tsm6kError(f'MOPS t05st11 {month} 认不出本公司背書保證那一行 / 對子公司累計餘額 —— 版式变了？')
    cum, lim, to_subs = _mnum(row.group(2)), _mnum(row.group(3)), _mnum(tosubs.group(1))
    if to_subs != cum:
        raise Tsm6kError(f'MOPS t05st11 {month} 内部不自洽：本公司至本月份累計餘額 {cum:,} ≠ '
                         f'本公司對子公司背書保證累計餘額 {to_subs:,}')
    g = parsed['guar']
    bad = []
    if cum != g['approved_total_k']:
        bad.append(f'核准合计：MOPS 至本月份累計餘額 {cum:,} vs 6-K TSMC 各行核准之和 {g["approved_total_k"]:,}')
    if lim != g['limit_k']:
        bad.append(f'限额：MOPS 最高額度 {lim:,} vs 6-K TSMC 首行限额 {g["limit_k"]:,}')
    if bad:
        raise Tsm6kError(f'{month} 月报 6-K 与 MOPS t05st11 对不上，本次不写入：' + '；'.join(bad))
    print(f'[tsm_6k] MOPS t05st11 {month} 对账通过：至本月份累計餘額 {cum:,} = 6-K 核准合计，'
          f'最高額度 {lim:,} = 6-K 首行限额')
    return True


# ══════════════════════════════════════════════════════════════════════════
# 两张表
# ══════════════════════════════════════════════════════════════════════════
def _read_table(path, cols):
    """→ (原始字节, {month: row}, 升序月份列表)。表头不对 / 月份乱序 / 2023-03 起断月都抛。"""
    with open(path, 'rb') as f:
        raw = f.read()
    rows = list(csv.reader(io.StringIO(raw.decode('utf-8'), newline='')))
    if not rows or rows[0] != cols:
        raise Tsm6kError(f'{path} 表头不对：{rows[0] if rows else None} != {cols}')
    body = [r for r in rows[1:] if r and any(c.strip() for c in r)]
    months = [r[0] for r in body]
    if not months:
        raise Tsm6kError(f'{path} 没有数据行 —— 本模块只做增量，建库请人工')
    if any(not re.fullmatch(r'\d{4}-\d{2}', x) for x in months) or months != sorted(set(months)):
        raise Tsm6kError(f'{path} 的月份列不是严格升序的 YYYY-MM')
    recent = [x for x in months if x >= FORMAT_FROM]
    for a, b in zip(recent, recent[1:]):
        if b != _shift(a, 1):
            raise Tsm6kError(f'{path} 在 {a} 与 {b} 之间断月（{FORMAT_FROM} 起必须逐月连续）')
    return raw, {r[0]: r for r in body}, months


def _tables(series_dir):
    der = _read_table(os.path.join(series_dir, DER_CSV), DER_COLS)
    gua = _read_table(os.path.join(series_dir, GUA_CSV), GUA_COLS)
    return der, gua


def last_month(series_dir):
    """两表末月的较小值 'YYYY-MM'。表头不对就抛。"""
    der, gua = _tables(series_dir)
    return min(der[2][-1], gua[2][-1])


def fingerprint(series_dir):
    """两表字节的 sha256 hex。"""
    h = hashlib.sha256()
    for name in (DER_CSV, GUA_CSV):
        with open(os.path.join(series_dir, name), 'rb') as f:
            data = f.read()
        h.update(name.encode() + b'\0' + str(len(data)).encode() + b'\0' + data)
    return h.hexdigest()


def _append(path, lines, tmp_dir, expect_raw=None):
    """只追加：读全文、照抄既有行尾、末行无换行先补，写 tmp_dir/<name>.tmp 再 os.replace。

    行尾判据同 fetch/tsm.py 的 _line_terminator（看开头 4KB 有没有 CRLF）。
    `expect_raw` 给了就先核文件自读入以来没被别人改过，改过就抛（不覆盖别人的写入）。
    """
    with open(path, 'rb') as f:
        raw = f.read()
    if expect_raw is not None and raw != expect_raw:
        raise Tsm6kError(f'{path} 在本轮读入之后被改动过，拒绝覆盖')
    term = b'\r\n' if b'\r\n' in raw[:4096] else b'\n'
    data = raw if (not raw or raw.endswith(b'\n')) else raw + term
    data += b''.join(line.encode('ascii') + term for line in lines)
    os.makedirs(tmp_dir, exist_ok=True)
    tmp = os.path.join(tmp_dir, os.path.basename(path) + '.tmp')
    with open(tmp, 'wb') as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _diff(row, cols, cells):
    out = []
    for i, c in enumerate(cols[1:], 1):
        have = row[i] if i < len(row) else ''
        try:
            same = float(have) == float(cells[c])
        except ValueError:
            same = False
        if not same:
            out.append((c, have, cells[c]))
    return out


def _plan(series_dir, cache_dir, upto, today=None, opener=None):
    """update() 的全部读与校验，不写 series。→ dict(der=[行], gua=[行], months=[月], raw=(der, gua))。"""
    today = today or datetime.date.today()
    (der_raw, der, der_m), (gua_raw, gua, gua_m) = _tables(series_dir)
    plan = dict(der=[], gua=[], months=[], raw=(der_raw, gua_raw))
    lo = min(der_m[-1], gua_m[-1])
    if lo < FORMAT_FROM:
        raise Tsm6kError(f'两表末月较小值 {lo} 早于 {FORMAT_FROM} —— 更早的版式没有核准栏（口径坑 h），交人')
    todo = _months_after(lo, upto)
    if len(todo) > MAX_BACKFILL:
        raise Tsm6kError(f'待取月份 {todo[0]}..{todo[-1]} 共 {len(todo)} 个，超过 MAX_BACKFILL={MAX_BACKFILL} —— '
                         '断了这么久先人工看一眼再补')
    if not todo:
        return plan
    subs = submissions(opener)

    # ── 重述体检：两表都有的最近 DRIFT_BACK 个月，与月报逐格比（口径坑 i）────────────
    both = [x for x in sorted(set(der_m) & set(gua_m)) if x >= FORMAT_FROM][-DRIFT_BACK:]
    drift, ok = [], []
    for M in both:
        hit = find(M, cache_dir, today, opener, subs=subs, verbose=False)
        if hit is None:
            print(f'[tsm_6k][warn] 重述体检：{M} 的月报 6-K 定位不到，本月跳过体检')
            continue
        row, p = hit
        cells = _cells(p)
        for c, have, want in _diff(der[M], DER_COLS, cells) + _diff(gua[M], GUA_COLS, cells):
            drift.append(f'{M} {c}: 库内 {have!r} vs 官方 {want} ({row["acc"]})')
        ok.append(M)
    if drift:
        raise Tsm6kError('月报 6-K 与已入库值不一致（疑似重述或解析变形），本次不写入：\n  '
                         + '\n  '.join(drift))
    if ok:
        print(f'[tsm_6k] 重述体检：{"、".join(ok)} 与月报 6-K 逐格相等（6 列）')

    # ── 逐月取新月份：找不到就停，不跳月 ────────────────────────────────────────
    found = []
    for M in todo:
        hit, checked, skipped = _scan(M, cache_dir, today, opener, subs=subs)
        if hit is None:
            print(f'[tsm_6k] 源上 {M} 的月报 6-K 尚未出现（已查 {checked} 份候选'
                  + (f'，另有 {skipped} 份未缓存件本轮没下' if skipped else '') + '）')
            break
        row, p = hit
        print(f'[tsm_6k] {M} ← {row["form"]} {row["acc"]} {row["doc"]}（filed {row["fd"]}）')
        cells = _cells(p)
        for name, have_rows, cols in ((DER_CSV, der, DER_COLS), (GUA_CSV, gua, GUA_COLS)):
            if M in have_rows and _diff(have_rows[M], cols, cells):
                raise Tsm6kError(f'series/{name} 已有 {M} 行但与月报 6-K 不一致：'
                                 f'{_diff(have_rows[M], cols, cells)}（{row["acc"]}），本次不写入')
        mops_crosscheck(M, p, opener)
        found.append((M, p))

    # ── 全部校验通过之后才生成要追加的行；每张表只追加大于它自己末月的月份 ──────────
    for M, p in found:
        d_line, g_line = rows_for(p)
        if M > der_m[-1]:
            plan['der'].append(d_line)
        if M > gua_m[-1]:
            plan['gua'].append(g_line)
        if M > der_m[-1] or M > gua_m[-1]:
            plan['months'].append(M)
    return plan


def update(series_dir, cache_dir, upto, today=None, opener=None):
    """把 (两表末月较小值, upto] 里源上已有的月份追加进两张表，返回新增月份列表（升序）。

    幂等：没有新月份时两表一个字节不动。所有月份都校验通过后才写；tmp 文件落 cache_dir/tsm_6k/。
    """
    plan = _plan(series_dir, cache_dir, upto, today, opener)
    tmp_dir = os.path.join(cache_dir, CACHE_SUB)
    for name, lines, raw in ((DER_CSV, plan['der'], plan['raw'][0]),
                             (GUA_CSV, plan['gua'], plan['raw'][1])):
        if lines:
            _append(os.path.join(series_dir, name), lines, tmp_dir, expect_raw=raw)
            for line in lines:
                print(f'[tsm_6k] 追加 series/{name}: {line}')
    return plan['months']


# ══════════════════════════════════════════════════════════════════════════
# 离线回放
# ══════════════════════════════════════════════════════════════════════════
def _replay(series_dir, cache_dir):
    """cache/tsm_6k 里所有 marker ≥ FORMAT_FROM 的月报逐月严格解析并与两表比。→ 逐月结果列表。"""
    (_, der, der_m), (_, gua, gua_m) = _tables(series_dir)
    by_month = {}
    for p in sorted(glob.glob(os.path.join(cache_dir, CACHE_SUB, '*.htm'))):
        with open(p, 'rb') as f:
            fl = flat(f.read().decode('utf-8', 'replace'))
        try:
            mm = marker_month(fl)
        except Tsm6kError as exc:
            by_month.setdefault('?', []).append((os.path.basename(p), fl, str(exc)))
            continue
        if mm is None or mm < FORMAT_FROM:
            continue
        by_month.setdefault(mm, []).append((os.path.basename(p), fl, None))
    out = []
    for M in sorted(by_month):
        name, fl, err = sorted(by_month[M])[-1]          # 文件名以 filingDate 打头 ⇒ 末个最新
        res = dict(month=M, file=name, n_docs=len(by_month[M]), diffs=[], error=err, pending=False)
        out.append(res)
        if err:
            continue
        try:
            cells = _cells(parse(fl, verbose=False))
        except Tsm6kError as exc:
            res['error'] = str(exc)
            continue
        if M > der_m[-1] and M > gua_m[-1]:
            res['pending'] = True                         # 两表都还没到这个月：待追加，不算差异
            continue
        for rows, cols, last in ((der, DER_COLS, der_m[-1]), (gua, GUA_COLS, gua_m[-1])):
            if M in rows:
                res['diffs'] += _diff(rows[M], cols, cells)
            elif M <= last:
                res['diffs'].append((f'{cols[1]}…（整行缺）', '', ''))
    return out


def audit(series_dir, cache_dir):
    """离线回放并打印逐月结果，返回差异数（差异格 + 解析失败份数）。"""
    res = _replay(series_dir, cache_dir)
    bad = 0
    print(f'{"month":<8} {"cache/tsm_6k 文件":<62} 结果')
    for r in res:
        if r['error']:
            bad += 1
            print(f'{r["month"]:<8} {r["file"]:<62} 解析失败：{r["error"][:160]}')
        elif r['pending']:
            print(f'{r["month"]:<8} {r["file"]:<62} 两表尚无该月（待追加，不计差异）')
        elif r['diffs']:
            bad += len(r['diffs'])
            print(f'{r["month"]:<8} {r["file"]:<62} {len(r["diffs"])} 格不等：{r["diffs"]}')
        else:
            print(f'{r["month"]:<8} {r["file"]:<62} 6 列逐格相等')
    n = sum(1 for r in res if not r['error'] and not r['pending'])
    pend = sum(1 for r in res if r['pending'])
    print(f'[tsm_6k] audit：{n} 个月 × 6 列逐格比对，差异 {bad}'
          + (f'；另有 {pend} 个月两表尚无（待追加）' if pend else ''))
    return bad


def _main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description='TSMC 月报 6-K 第 3/4 项 → series/tsm_guarantees.csv / tsm_derivatives.csv')
    ap.add_argument('cmd', nargs='?', choices=['audit'], help='audit = 离线回放 cache/tsm_6k')
    ap.add_argument('--write', action='store_true', help='真追加（缺省只打印将追加的行）')
    ap.add_argument('--cache', default=os.path.join(ROOT, 'cache'))
    ap.add_argument('--series', default=os.path.join(ROOT, 'series'))
    a = ap.parse_args(argv)
    if a.cmd == 'audit':
        return 1 if audit(a.series, a.cache) else 0
    today = datetime.date.today()
    upto = _shift(f'{today.year}-{today.month:02d}', -1)
    try:
        if a.write:
            print(f'[tsm_6k] added = {update(a.series, a.cache, upto, today)}')
        else:
            plan = _plan(a.series, a.cache, upto, today)
            if not plan['months']:
                print(f'[tsm_6k] dry-run：截至 {upto} 没有要追加的行')
            for name, lines in ((DER_CSV, plan['der']), (GUA_CSV, plan['gua'])):
                if lines:
                    print(f'[tsm_6k] dry-run：将追加到 series/{name}：')
                    for line in lines:
                        print(line)
    except Tsm6kError as exc:
        print(f'[tsm_6k] FAIL {exc}')
        return 1
    return 0


if __name__ == '__main__':                                         # pragma: no cover
    sys.exit(_main())
