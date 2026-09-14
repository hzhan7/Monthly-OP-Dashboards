# -*- coding: utf-8 -*-
"""HOOD **上市前**历史回填：IPO 文件里的年末 / 季末时点 KPI 与 9 个季度收入 → 两张**新**表。

    series/hood_ipo_pit.csv  month,funded_accounts_mn,auc_usdmn,source            2014-12 … 2021-06（12 行）
    series/hood_ipo_q.csv    quarter,rev_transaction_usdk,rev_net_interest_usdk,
                             rev_other_usdk,rev_total_usdk,source                  2019Q1 … 2021Q1（9 行）

用法:
    python3 build/basefill/hood_ipo.py                      # 取数 + 核对 + 写两张 CSV
    python3 build/basefill/hood_ipo.py --dry                # 只核对、只打印，不写
    python3 build/basefill/hood_ipo.py --refresh            # 强制重下原件（含 EDGAR 申报索引）
    python3 build/basefill/hood_ipo.py --cache-dir <路径>   # 原件落在哪（默认 cache/basefill/hood_ipo/）

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
这个文件为什么存在，以及为什么是两张新表、而不是把 hood.csv / hood_q.csv 往左推
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
series/hood.csv 从 2021-01 起、series/hood_q.csv 从 2021Q1 起 —— 那是官方月度 / 季度 Supplement 的
天花板（见 build/basefill/hood_2021.py、hood_q_2021.py 文件头）。再往前，公司只在 IPO 前后的申报里印过：
  ① 年末 / 季末的**时点值**：Net Cumulative Funded Accounts（NCFA）与 Assets Under Custody（AUC）；
  ② S-1「Quarterly Results of Operations」里 2019Q1 起 9 个季度的收入（**千**美元）。
① 不是月度粒度（2014~2019 每年一个点，2020 起每季一个点），塞进 hood.csv 就是 25 列只有 2 列、
   且大半月份空着的行；② 是千美元，hood_q.csv 是 Supplement 的百万美元口径，另 10 列（分资产收入、
   季度成交量）2021 年前根本没有 —— 两把尺子混进一列正是仓规要挡的。所以另起两张窄表，
   怎么接到图的左端由 build/hood.py 决定。2021-03 / 2021-06 / 2021Q1 三行是**接缝行**，
   只供看门狗 C 与现有序列对账，页面只画 2021 年以前的行。
IPO 文件不会再出新版，这个洞补完就永远关上 —— 照 hood_2021.py 的先例放 basefill/，不进无人值守链路。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
天花板：每一条都是「官方没印过」，不是「没去找」
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
· 月度：2021-01 之前**任何官方文件都没有**月度数。8-K 0001783879-22-000088（2022-04-28）原文
  "The first report will cover the month of March 2022 (and each of the preceding 12 calendar months)"
  —— 月度披露 2022-04 才开始、回溯到 2021-03；2021-01/02 是后来的 Supplement 补的（hood_2021.py 文件头）。
· NCFA 年末值：2014-12 起。2014~2016 只有 S-1 里 customergrowth.jpg 时间轴图上的**取整标签**
  （40K / 300K / 700K）；2017~2020 由 MD&A 的 Key Performance Metrics 表印到 0.1M。图上 2013 段没有标签。
· AUC：2017-12 起（KPI 表最左一列）。2014~2016 官方没印 → 留空，不补 0、不外推。
· 季末 NCFA / AUC：2020-03 起（S-1 的 Mar-31-2020 列）。2020-06 / 2020-09 只在上市后的文件里以
  「上年同期」印过，出处见下「源」③。2019 年各季末在 S-1 与之后的 10-Q 里都没有。
· 季度收入：2019Q1 起（S-1 季度表最左一列）。
· 季度成交量：2021 年之前**没有任何官方季度成交量**（S-1 / 10-Q 都没有成交量表；Supplement 的
  Quarterly KPIs 页最早从 2021Q1 起，见 hood_q_2021.py）→ take rate（收入 ÷ 成交量）**不能往左延伸**。
· 分资产交易收入（Options / Crypto / Equities）：季度粒度只从 2020Q1 起、且散在不同文件、精度不一 ——
  S-1 印 Q1'20/Q1'21（与 FY2019/FY2020），10-Q Q2'21 / Q3'21 各带出 Q2'20 / Q3'20（千美元），
  Q4'20 研究时只在 Q4'21 业绩稿正文里见到整百万的数（"$142 million"）。拼出来是断的、精度不齐、页面也不画
  → **故意不存**。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
源：取「最早公开印出的那一版」，后来的文件只当证人
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CIK 0001783879，全部读 EDGAR 原件 https://www.sec.gov/Archives/edgar/data/1783879/<accession>/<doc>。
  ① S-1    0001628280-21-013318 robinhoods-1.htm  2021-07-01 —— 公司**第一份公开的有正文申报**
           （之前只有 Form D 私募通知与保密递交的 DRS，看门狗 F 顺手验这一点）。
     · MD&A「Key Performance Metrics」表：YE2017/18/19/20 + Mar-31-2020/2021 六列 → NCFA、AUC
     · 「Quarterly Consolidated Statements of Operations」表：2019Q1…2021Q1 九列 → 四行收入（千美元）
     · customergrowth.jpg：2014~2020 年末 NCFA 的图上标签 —— **人眼读图**写进 GRAPHIC 常量（脚本不 OCR），
       并用 IMG_SHA256 钉住读的就是这一份字节。
  ② 424B4  0001628280-21-015076 robinhood424.htm  2021-07-30 —— 定价后的最终招股书，只当证人（看门狗 B）。
  ③ 2020-06 / 2020-09：扫 EDGAR 索引里从 S-1 到 2021-10-29 的**每一份**公开申报，按 acceptanceDateTime
     排序找第一份印出**精确值**的文件（看门狗 F 每次运行都重扫，不写死结论）。研究时实测：
       2020-06 NCFA  9.8       S-1/A No.1 0001628280-21-013986  2021-07-19  Recent Developments 表 Actual 列 + 正文
       2020-06 AUC   33,421.5  10-Q Q2'21 0001783879-21-000029  2021-08-18  —— S-1/A 那张表只印到整百万（$33,422）、
                               正文只印 "$33 billion"；同日早两分钟的 8-K 业绩稿也只有 "$33 billion"
       2020-09 NCFA  11.4      8-K Q3'21 EX-99.1 0001783879-21-000050  2021-10-26  业绩稿正文
       2020-09 AUC   44,445.6  10-Q Q3'21 0001783879-21-000054  **2021-10-29**（不是 10-26：10-26 交的是 8-K，
                               业绩稿只印 "$44 billion"；10-Q 的 acceptanceDateTime 是 2021-10-29T20:02:11Z）
     「精确」= 与 KPI 表同精度（NCFA 0.1M、AUC 0.1 $M）。整百万 / 十亿级的取整印法只当证人，必须四舍五入对得上。
     S-1/A 那张表里 Jun-30-2021 一列标着 **Estimate**，估计值不算印出。
  ④ 2021-06 接缝行：10-Q Q2'21 的 KPI 表（22.5 / 102,034.8）。接缝行只作对账、出处按任务口径定为 10-Q；
     留个底：同日早两分钟的 8-K 业绩稿正文已印 "22.5 million"（AUC 只有 "$102 billion"），S-1/A 里那一列是 Estimate。

  不扫的申报类型（SKIP_FORMS）：3/4/SC 13D 等持股表（不含公司 KPI）；EFFECT / CERT（无正文）；
  D / D/A（私募通知 XML）；CORRESP / UPLOAD / DRSLTR（审核往来函，落款日 ≠ 公开日 —— SEC 在审核结束
  至少 20 个工作日后才放出，必然晚于上面几份）；DRS / DRS/A（保密递交的草稿，递交时不公开、随 S-1 一起公开）。
  8-K 扫主文档 + 目录里全部 .htm 附件（业绩稿在 EX-99.1）；其余类型只扫主文档（附件是意见书、证书、协议）。
  研究时人工核对、脚本不重跑：2021-03-22 那份 DRS（0001628279-21-000185）印的 AUC 是 2018 $8,144.0、
  2020 $62,977.8，与 S-1 的 8,359.5 / 62,978.5 不同；2021-06-15 的 DRS/A 已与 S-1 一致。首份公开版本是 S-1，入库取 S-1。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
口径坑
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
· **2018-11 之前的 NCFA 是拿第三方清算商的数据算的**。S-1 风险因素「We track certain operational metrics,
  which are subject to inherent challenges in measurement…」原文（CLEARING_QUOTE，看门狗 D 验它仍在 S-1 里）：
    "For example, prior to our becoming self-clearing in November 2018, we relied on a third-party provider for
     our clearing operations, and used data collected by that third party to compute certain metrics, such as
     Net Cumulative Funded Accounts, that, since November 2018, we have calculated based on data sourced and
     processed internally."
  即 2014-12 ~ 2017-12 这几个点（以及 2018 年的大半年）与之后不是同一条数据管道。
· 图上标签是取整的（40K / 300K / 700K），入库成 0.04 / 0.3 / 0.7（只做 K→M 单位换算），source 注明 rounded。
· 名字后来改过：NCFA → Funded Customers、AUC → Total Platform Assets。看门狗 C 在 2021-03 / 2021-06 两个
  接缝月上与 series/hood.csv 逐格对，证明是同一个量。
· 季度收入接缝（2021Q1）差在 **rounding to foot**：后来的 Earnings Supplement 印百万美元，且让分项之和等于
  **取整后的**合计 —— S-1 的 other 39,238 在 Supplement 里印成 40 而不是 39，因为 420 + 62 + 39 = 521 ≠
  round(522.174) = 522。所以 transaction / net interest / total 要求 == round(千÷1000)，other 只要求差在 ±1 以内，
  看门狗 C 把每一格的实际差额都打出来。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
看门狗（任何一道不过就抛 HoodIpoBasefillError，一格都不写）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
A  每季 transaction + net interest + other == total，千美元逐位相等。
B  S-1 与 424B4 的 KPI 表、季度表逐格（原样字符串）相同；不同就把两边都打出来。
C  接缝：hood.csv 2021-03 / 2021-06 的 funded_customers_mn == funded_accounts_mn、total_platform_assets_usdbn ==
   round(auc_usdmn/1000, 1)；hood_q.csv 2021Q1 按上面「rounding to foot」的规则。
D  年末 NCFA 2014→2020 严格递增；图上 2017~2020 标签 == KPI 表；S-1 HTML 引用了 customergrowth.jpg、
   图的 sha256 就是人眼读的那一份；CLEARING_QUOTE 仍在 S-1 正文里。
E  护栏：不写 ≥ 2021-07 的月、≥ 2021Q2 的季；series/hood.csv、hood_q.csv 写前写后 sha256 不变；
   两张输出表若已存在且内容不同，拒绝覆盖（先人工看 diff 再删）。
F  最早印出：见「源」③。第一份精确印出的文件必须就是 FIRST_PRINT 里写的那份；窗口内所有精确印法必须同值、
   取整印法必须对得上；早于它的文件里若出现「指标 + 该季末 + 数字」却没被解析器认出，直接报错
   （宁可停下让人看，也不让没见过的版式漏过去）。
"""
import argparse
import csv
import gzip
import hashlib
import importlib.util
import io
import json
import os
import re
import sys
import time
import urllib.request
from decimal import ROUND_HALF_UP, Decimal

from lxml import html as LH

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
SERIES_DIR = os.path.join(ROOT, 'series')
PIT_PATH = os.path.join(SERIES_DIR, 'hood_ipo_pit.csv')
Q_PATH = os.path.join(SERIES_DIR, 'hood_ipo_q.csv')
HOOD_M_PATH = os.path.join(SERIES_DIR, 'hood.csv')       # 只读，看门狗 C / E
HOOD_Q_PATH = os.path.join(SERIES_DIR, 'hood_q.csv')     # 只读，看门狗 C / E

CIK = '1783879'
ARCHIVE = f'https://www.sec.gov/Archives/edgar/data/{CIK}'
SUBMISSIONS = f'https://data.sec.gov/submissions/CIK{CIK.zfill(10)}.json'
_MIN_INTERVAL = 0.25          # 秒；≤ 4 req/s（任务上限 5、SEC 上限 10）

# ─────────────────────────── 源 ───────────────────────────
S1 = ('0001628280-21-013318', 'robinhoods-1.htm')
F424B4 = ('0001628280-21-015076', 'robinhood424.htm')
Q2_10Q = ('0001783879-21-000029', 'hood-20210630.htm')
SRC_S1_KPI = 'S-1 0001628280-21-013318 KPI table'
SRC_S1_Q = 'S-1 0001628280-21-013318 Quarterly Consolidated Statements of Operations'
SRC_SEAM_Q2 = "10-Q Q2'21 0001783879-21-000029 KPI table"

IMG = 'customergrowth.jpg'
IMG_SHA256 = '30edc0c3d2eb85759809850fc0e10ccab2012bdeb4f446381891607677b334cd'
# 人眼读 S-1 的 customergrowth.jpg（上面 sha256 那一份）得到的年末 NCFA 标签。脚本不 OCR，只能写死；
# 图里每个年份段左上角的数就是该年年末值（1.9M / 3.3M / 5.1M / 12.5M 与 KPI 表逐个对得上，看门狗 D）。
GRAPHIC = (('2014-12', '40K'), ('2015-12', '300K'), ('2016-12', '700K'), ('2017-12', '1.9M'),
           ('2018-12', '3.3M'), ('2019-12', '5.1M'), ('2020-12', '12.5M'))
GRAPHIC_Q1_2021 = '18M'       # 图右上角 "18M Net Cumulative Funded Accounts"（Q1'21 段），只当证人

CLEARING_QUOTE = ('prior to our becoming self-clearing in November 2018, we relied on a third-party provider '
                  'for our clearing operations, and used data collected by that third party to compute certain '
                  'metrics, such as Net Cumulative Funded Accounts, that, since November 2018, we have calculated '
                  'based on data sourced and processed internally')

# (季末, 指标) → (预期的最早精确印出文件, 写进 source 列的出处)。看门狗 F 每次重扫验证，对不上就停。
FIRST_PRINT = {
    ('2020-06', 'ncfa'): ('0001628280-21-013986',
                          'S-1/A No.1 0001628280-21-013986 Recent Developments (Actual col)'),
    ('2020-06', 'auc'): ('0001783879-21-000029', "10-Q Q2'21 0001783879-21-000029 KPI table"),
    ('2020-09', 'ncfa'): ('0001783879-21-000050', "8-K Q3'21 EX-99.1 0001783879-21-000050 press release"),
    ('2020-09', 'auc'): ('0001783879-21-000054', "10-Q Q3'21 0001783879-21-000054 KPI table"),
}
TARGET_MONTHS = ('2020-06', '2020-09')
SCAN_END = '2021-10-30T00:00:00.000Z'      # 扫到 2021-10-29 收盘（含同日稍晚的 424B3 当证人）

SCAN_FORMS = {'S-1', 'S-1/A', '424B1', '424B3', '424B4', '8-K', '10-Q', 'S-8', 'S-8 POS', '8-A12B', 'FWP'}
_OWN = '持股表，不含公司 KPI'
_LETTER = '审核往来函：落款日≠公开日（审核结束 ≥20 个工作日后才放出）'
SKIP_FORMS = {
    '3': _OWN, '3/A': _OWN, '4': _OWN, '4/A': _OWN, '5': _OWN, '144': _OWN,
    'SC 13D': _OWN, 'SC 13D/A': _OWN, 'SC 13G': _OWN, 'SC 13G/A': _OWN,
    'EFFECT': 'SEC 生效通知，无正文', 'CERT': '交易所上市证书，无正文',
    'D': '私募发行通知 XML，无 KPI', 'D/A': '私募发行通知 XML，无 KPI',
    'CORRESP': _LETTER, 'UPLOAD': _LETTER, 'DRSLTR': _LETTER,
    'DRS': '保密递交草稿，递交时不公开', 'DRS/A': '保密递交草稿，递交时不公开',
}

PIT_HEADER = ['month', 'funded_accounts_mn', 'auc_usdmn', 'source']
Q_HEADER = ['quarter', 'rev_transaction_usdk', 'rev_net_interest_usdk', 'rev_other_usdk',
            'rev_total_usdk', 'source']
PIT_MONTHS = ['2014-12', '2015-12', '2016-12', '2017-12', '2018-12', '2019-12',
              '2020-03', '2020-06', '2020-09', '2020-12', '2021-03', '2021-06']
QUARTERS = ['2019Q1', '2019Q2', '2019Q3', '2019Q4', '2020Q1', '2020Q2', '2020Q3', '2020Q4', '2021Q1']
GUARD_M = '2021-07'           # 本脚本一行都不许写到这个月及以后
GUARD_Q = '2021Q2'            # 同上，季度


class HoodIpoBasefillError(RuntimeError):
    pass


# ─────────────────────────── HTTP + 缓存 ───────────────────────────
def _user_agent():
    """借 fetch/cost_sec.py 的 USER_AGENT（SEC 要求 UA 带真实联系方式）—— 全仓只维护一个身份。"""
    spec = importlib.util.spec_from_file_location('fetch_cost_sec', os.path.join(ROOT, 'fetch', 'cost_sec.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.USER_AGENT


class Net:
    """原件缓存：SEC Archives 下的文件公开后永不改（改了就是新 accession），所以命中缓存不发请求。

    EDGAR 申报索引（submissions JSON）也缓存：本脚本只看 2021 年那段已关闭的窗口，条目不会再变；
    分页可能变，所以每次都把**所有**分页合并再用。--refresh 时连索引一起重下。
    """

    def __init__(self, cache_dir, refresh=False):
        self.dir, self.refresh = cache_dir, refresh
        self.ua = _user_agent()
        self._mem, self._last = {}, 0.0
        self.n_cache = self.n_net = 0

    def get(self, url, name):
        if name in self._mem:
            return self._mem[name]
        path = os.path.join(self.dir, name)
        if not self.refresh and os.path.exists(path) and os.path.getsize(path) > 0:
            with open(path, 'rb') as f:
                body = f.read()
            self.n_cache += 1
        else:
            gap = _MIN_INTERVAL - (time.time() - self._last)
            if gap > 0:
                time.sleep(gap)
            req = urllib.request.Request(url, headers={'User-Agent': self.ua, 'Accept-Encoding': 'gzip'})
            try:
                with urllib.request.urlopen(req, timeout=90) as r:
                    body = r.read()
                    if r.headers.get('Content-Encoding') == 'gzip':
                        body = gzip.decompress(body)
            except Exception as e:                                   # noqa: BLE001
                raise HoodIpoBasefillError(f'SEC 取不到 {url}: {type(e).__name__}: {e}') from e
            finally:
                self._last = time.time()
            if not body:
                raise HoodIpoBasefillError(f'SEC 返回空文件：{url}')
            os.makedirs(self.dir, exist_ok=True)
            with open(path + '.part', 'wb') as f:
                f.write(body)
            os.replace(path + '.part', path)
            self.n_net += 1
        self._mem[name] = body
        return body

    def doc(self, acc, name):
        nd = acc.replace('-', '')
        return self.get(f'{ARCHIVE}/{nd}/{name}', f'{nd}_{name}')


def edgar_filings(net):
    """EDGAR 全部申报 → [{acc, form, filed, accepted, primary}]，按 acceptanceDateTime 升序。

    recent 那一页只回溯到 2022 年，2021 年的件在 `filings.files` 列出的分页里 —— 不读分页就一份都看不到。
    """
    main = json.loads(net.get(SUBMISSIONS, 'submissions_main.json'))
    pages = [main['filings']['recent']]
    for f in main['filings'].get('files', []):
        pages.append(json.loads(net.get(f"https://data.sec.gov/submissions/{f['name']}",
                                        f"submissions_{f['name']}")))
    out = {}
    for pg in pages:
        for i, acc in enumerate(pg['accessionNumber']):
            out.setdefault(acc, {'acc': acc, 'form': pg['form'][i], 'filed': pg['filingDate'][i],
                                 'accepted': pg['acceptanceDateTime'][i], 'primary': pg['primaryDocument'][i]})
    if not out:
        raise HoodIpoBasefillError('EDGAR 申报索引是空的')
    return sorted(out.values(), key=lambda r: r['accepted'])


def filing_docs(net, filing):
    """一份申报要扫的文档名。8-K 连附件（业绩稿在 EX-99.1），其余只扫主文档。"""
    if filing['form'] != '8-K':
        return [filing['primary']]
    nd = filing['acc'].replace('-', '')
    idx = json.loads(net.get(f'{ARCHIVE}/{nd}/index.json', f'{nd}_index.json'))
    names = [it['name'] for it in idx['directory']['item']]
    extra = sorted(n for n in names if n.lower().endswith('.htm') and n != filing['primary']
                   and not re.fullmatch(r'R\d+\.htm', n) and '-index' not in n)
    return [filing['primary']] + extra


# ─────────────────────────── HTML 解析（lxml）───────────────────────────
_BLOCK = ('p', 'div', 'br', 'tr', 'td', 'th', 'li', 'table', 'hr', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6')
_NUM = re.compile(r'^\(?\$?\s*\(?\d[\d,]*(?:\.\d+)?\)?%?$')
_INT_K = re.compile(r'^\$?\d{1,3}(?:,\d{3})*$')
_MON = {m: i + 1 for i, m in enumerate(
    ('jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'))}
_FULL_DATE = re.compile(r'(?i)^(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s*(\d{1,2})\s*,\s*'
                        r'((?:19|20)\d\d)$')
_MD = re.compile(r'(?i)\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s*(\d{1,2})\b')
_YEAR = re.compile(r'^(?:19|20)\d\d$')
_QEND = {3: 31, 6: 30, 9: 30, 12: 31}


def _root(raw):
    """→ lxml 根节点。去 script/style/注释；块级元素尾部补换行，单元格与段落不会粘成一个词。"""
    root = LH.fromstring(raw)
    for bad in root.xpath('//script|//style|//comment()'):
        if bad.getparent() is not None:          # 文档级注释（<html> 之外）没有父节点，也不进 itertext
            bad.drop_tree()
    for el in root.iter(*_BLOCK):
        el.tail = '\n' + (el.tail or '')
    return root


def _text(root):
    """→ 纯文本，块边界保留为 \\n，行内空白压成单空格。"""
    t = ''.join(root.itertext()).replace('\xa0', ' ')
    t = re.sub(r'[ \t\r\f\v]+', ' ', t)
    return re.sub(r' *\n[\n ]*', '\n', t)


def _flat(s):
    return re.sub(r'\s+', ' ', s.replace('\xa0', ' ')).strip()


def _squash(s):
    return re.sub(r'\s+', '', s).lower()


def _cells(tr):
    """一行 → 非空单元格文本；Workiva 把 '$'、')'、'%' 拆成单独的格，这里并回相邻的数字。"""
    out = []
    for c in (_flat(''.join(td.itertext())) for td in tr.xpath('./td|./th')):
        if not c:
            continue
        if out and out[-1] in ('$', '($') and _NUM.match(c):
            out[-1] += c
        elif out and c in (')', '%', ')%') and _NUM.match(out[-1] + c):
            out[-1] += c
        else:
            out.append(c)
    return out


def _spans(tr):
    """一行 → [(起列, 止列, 文本)]，按 colspan 摊开；空格子也占列（多组表头的对齐全靠它）。"""
    out, col = [], 0
    for td in tr.xpath('./td|./th'):
        span = int(td.get('colspan') or 1)
        out.append((col, col + span, _flat(''.join(td.itertext()))))
        col += span
    return out


def _rows(table):
    """→ [(tr, 非空单元格)]，空行剔掉。"""
    return [(tr, c) for tr, c in ((tr, _cells(tr)) for tr in table.xpath('.//tr')) if c]


def _label(cell):
    """行标签归一：去脚注号 (1)…(9)、压空白、小写。"""
    return _flat(re.sub(r'(?:\s*\(\d\))+\s*$', '', cell)).lower()


def _plain(v):
    """'$4,505.7' → '4505.7'。只去 $ 与千分位，**不动小数位**（仓规：原样入库，不自己取整）。"""
    s = v.replace('$', '').replace(',', '').strip()
    if not re.fullmatch(r'\d+(?:\.\d+)?', s):
        raise HoodIpoBasefillError(f'不是非负数字：{v!r}')
    return s


def _dec(v):
    return Decimal(_plain(v))


def _places(v):
    s = _plain(v)
    return len(s.split('.')[1]) if '.' in s else 0


def _month_of(cell):
    m = _FULL_DATE.match(cell.strip())
    return f'{m.group(3)}-{_MON[m.group(1).lower()[:3]]:02d}' if m else None


def _quarter_of(cell):
    m = _FULL_DATE.match(cell.strip())
    if not m:
        raise HoodIpoBasefillError(f'季度表头「{cell}」不是日期')
    mon, day = _MON[m.group(1).lower()[:3]], int(m.group(2))
    if _QEND.get(mon) != day:
        raise HoodIpoBasefillError(f'季度表头「{cell}」不是季末日')
    return f'{m.group(3)}Q{mon // 3}'


# ─────────────────────────── S-1 / 424B4 的两张表 ───────────────────────────
KPI_GROUPS = ['yearormonthendeddecember31,', 'threemonthsormonthendedmarch31,']
KPI_YEARS = ['2017', '2018', '2019', '2020', '2020', '2021']
KPI_MONTHS = ['2017-12', '2018-12', '2019-12', '2020-12', '2020-03', '2021-03']
KPI_ROWS = {'net cumulative funded accounts': 'ncfa', 'assets under custody (auc)': 'auc'}
Q_ROWS = {'transaction-based revenues': 'rev_transaction_usdk',
          'net interest revenues': 'rev_net_interest_usdk',
          'other revenues': 'rev_other_usdk',
          'total net revenues': 'rev_total_usdk'}


def parse_kpi(root, name):
    """MD&A 六列 KPI 表 → {'ncfa': {月: 原样字符串}, 'auc': {...}}。

    认表要两条同时成立：年份行恰为 2017 2018 2019 2020 2020 2021，其上一行恰为两组表头
    「Year or Month Ended December 31,」「Three Months or Month Ended March 31,」—— 前 4 个年份归年末、
    后 2 个归 3 月末是这两条放在一起的唯一读法。摘要里那张 4 列的同名表因年份行不符自然进不来。
    """
    found = []
    for t in root.xpath('//table'):
        rows = [c for _, c in _rows(t)]
        yi = next((i for i, r in enumerate(rows) if r[1:] == KPI_YEARS), None)
        if yi is None:
            continue
        hit = {}
        for r in rows[yi + 1:]:
            key = KPI_ROWS.get(_label(r[0]))
            if key and key not in hit:
                hit[key] = r
        if not hit:
            continue        # 同样 2017…2021 年份布局的别的表（NCFA 变动表、AUC 分项表…），没有 KPI 行
        groups = [_squash(c) for c in rows[yi - 1]] if yi else []
        if groups != KPI_GROUPS:
            raise HoodIpoBasefillError(
                f'{name}: 六列 KPI 表的分组表头不是预期那两组：{rows[yi - 1] if yi else None}')
        got = {}
        for key, r in hit.items():
            if len(r) != 7 or not all(_NUM.match(v) for v in r[1:]):
                raise HoodIpoBasefillError(f'{name}: KPI 表「{r[0]}」一行不是 6 个数：{r}')
            got[key] = dict(zip(KPI_MONTHS, r[1:]))
        if set(got) != set(KPI_ROWS.values()):
            raise HoodIpoBasefillError(
                f'{name}: 六列 KPI 表缺行 {sorted(set(KPI_ROWS.values()) - set(got))}')
        found.append(got)
    if not found:
        raise HoodIpoBasefillError(f'{name}: 找不到六列 KPI 表（YE2017 … Mar-31-2021）')
    if any(f != found[0] for f in found[1:]):
        raise HoodIpoBasefillError(f'{name}: 找到 {len(found)} 张六列 KPI 表且互不相同')
    return found[0]


def parse_quarterly(root, name):
    """「Quarterly Consolidated Statements of Operations」（千美元）→ {列名: {季: 原样字符串}}。

    认表：某行首格是 '(in thousands)'、后面恰 9 个完整日期。同形的「as a percentage of revenue」那张
    没有 '(in thousands)' 进不来；别的千美元季度表（如调整后 EBITDA 调节表）没有收入行，会被跳过。
    """
    found = []
    for t in root.xpath('//table'):
        rows = [c for _, c in _rows(t)]
        hi = next((i for i, r in enumerate(rows) if _squash(r[0]) == '(inthousands)' and len(r) == 10
                   and all(_FULL_DATE.match(c) for c in r[1:])), None)
        if hi is None:
            continue
        got = {}
        for r in rows[hi + 1:]:
            key = Q_ROWS.get(_label(r[0]))
            if not key or key in got:
                continue
            if len(r) != 10 or not all(_INT_K.match(v) for v in r[1:]):
                raise HoodIpoBasefillError(f'{name}: 季度表「{r[0]}」一行不是 9 个千美元整数：{r}')
            got[key] = r[1:]
        if not got:
            continue
        qs = [_quarter_of(c) for c in rows[hi][1:]]
        if qs != QUARTERS:
            raise HoodIpoBasefillError(f'{name}: 季度表的列是 {qs}，不是 {QUARTERS[0]} … {QUARTERS[-1]}')
        if set(got) != set(Q_ROWS.values()):
            raise HoodIpoBasefillError(f'{name}: 季度表缺行 {sorted(set(Q_ROWS.values()) - set(got))}')
        found.append({k: dict(zip(qs, v)) for k, v in got.items()})
    if not found:
        raise HoodIpoBasefillError(f'{name}: 找不到千美元季度收入表（2019Q1 … 2021Q1）')
    if any(f != found[0] for f in found[1:]):
        raise HoodIpoBasefillError(f'{name}: 找到 {len(found)} 张季度收入表且互不相同')
    return found[0]


# ─────────────────────────── 看门狗 F 的扫描器 ───────────────────────────
_METRIC_LAB = (('net cumulative funded accounts', 'ncfa'), ('assets under custody', 'auc'))


def _metric(cell):
    lab = _label(cell)
    return next((k for p, k in _METRIC_LAB if lab.startswith(p)), None)


def _body(cells):
    """表头行去掉左上角的单位格（'(in millions except ARPU)' 之类）。"""
    return cells[1:] if cells and cells[0].lower().startswith('(in ') else cells


def _header_months(head):
    """表头 [(tr, cells)] → 每个数值列的 'YYYY-MM'；认不出返回 None。三种表头：
      · 一行完整日期（'June 30, 2020' | 'June 30, 2021'）                        S-1/A 的 Recent Developments 表
      · 年份行 + 上方一个月日（'Three Months or Month Ended June 30,'）            10-Q
      · 年份行 + 上方两组月日（'Year or Month Ended December 31,' | '… June 30,'） 转售 S-1/A、424B3
    第三种按 colspan 把每个年份格落进覆盖它的那组表头，落不进唯一一组就报错。
    """
    for _, c in head:
        b = _body(c)
        if len(b) >= 2 and all(_FULL_DATE.match(x) for x in b):
            return [_month_of(x) for x in b]
    yi = next((i for i, (_, c) in enumerate(head)
               if len(_body(c)) >= 2 and all(_YEAR.match(x) for x in _body(c))), None)
    if yi is None:
        return None
    groups = []
    for tr, _ in head[:yi]:
        for s, e, txt in _spans(tr):
            mds = _MD.findall(txt)
            if len(mds) > 1:
                raise HoodIpoBasefillError(f'一个表头格里有多个月日，没见过：{txt!r}')
            if mds:
                groups.append((s, e, _MON[mds[0][0].lower()[:3]]))
    if not groups:
        return None
    years = [(s, txt) for s, _, txt in _spans(head[yi][0]) if _YEAR.match(txt)]
    out = []
    for s, txt in years:
        hit = {m for gs, ge, m in groups if gs <= s < ge} if len({g[2] for g in groups}) > 1 \
            else {groups[0][2]}
        if len(hit) != 1:
            raise HoodIpoBasefillError(f'多组表头里年份格 {txt}（列 {s}）落不进唯一一组：{groups}')
        out.append(f'{txt}-{hit.pop():02d}')
    return out


def _header_flags(head, n):
    """S-1/A 那张表头下有一行 'Actual' | 'Estimate' —— 估计值不算印出。"""
    for _, c in head:
        low = [x.lower() for x in c]
        if len(low) == n and all(x in ('actual', 'estimate', 'estimated') for x in low):
            return ['actual' if x == 'actual' else 'estimate' for x in low]
    return ['actual'] * n


def table_prints(root, name):
    """文档里所有 NCFA / AUC 表格行 → [print]。print = {month, metric, raw, unit, kind, flag}。"""
    out = []
    for t in root.xpath('//table'):
        rows = _rows(t)
        mi = [i for i, (_, c) in enumerate(rows) if _metric(c[0])]
        if not mi:
            continue
        head = rows[:mi[0]]
        months = _header_months(head)
        if not months:
            continue
        flags = _header_flags(head, len(months))
        for i in mi:
            cells = rows[i][1]
            vals = [x for x in cells[1:] if _NUM.match(x)]
            if len(vals) != len(months):
                if set(months) & set(TARGET_MONTHS):
                    raise HoodIpoBasefillError(
                        f'{name}: 「{cells[0]}」有 {len(vals)} 个数、表头 {months} —— 没见过的版式，先人工看：{cells}')
                continue
            for mo, v, fl in zip(months, vals, flags):
                out.append({'month': mo, 'metric': _metric(cells[0]), 'raw': v, 'unit': 'million',
                            'kind': '表', 'flag': fl})
    return out


_PERIOD = (r'(?:(?:for|in|as\s+of)\s+(?:the\s+)?(?:(?:three\s+months|month|quarter)\s+ended\s+)?'
           r'(?P<md>June|September)\s+30\s*,\s*2020|in\s+the\s+(?P<q>second|third)\s+quarter\s+of\s+2020)')
# "…Funded Accounts of 22.5 million, as compared to 9.8 million for the three months ended June 30, 2020"（S-1/A）
# "…Funded Accounts increased 97% to 22.4 million, compared with 11.4 million in the third quarter of 2020"（8-K）
# 句界含「. 」与「.” 」—— 否则 'definition of “AUC.” For the three months …, we expect to report revenue …
# as compared to $244 million …' 会被读成 AUC（S-1/A 实测踩过，看门狗 F 的取整核对当场抓住）。
_SENT_CMP = re.compile(
    r'(?P<metric>Net\s+Cumulative\s+Funded\s+Accounts|Assets\s+Under\s+Custody|\bAUC\b)'
    r'(?:(?![.;][”"’)]?\s)[^•\n]){0,400}?'
    r'\bcompared\s+(?:to|with)\s+(?P<val>\$?\s?\d[\d,]*(?:\.\d+)?)\s*(?P<unit>million|billion)\s*,?\s*' + _PERIOD)
# "As of June 30, 2020, we had 9.8 million Net Cumulative Funded Accounts"（S-1 摘要的句式，窗口内没见到，防着）
_SENT_ASOF = re.compile(
    r'\bAs\s+of\s+(?P<md>June|September)\s+30\s*,\s*2020\s*,\s*we\s+had\s+(?P<val>\d+(?:\.\d+)?)\s*'
    r'(?P<unit>million)\s+(?P<metric>Net\s+Cumulative\s+Funded\s+Accounts)')


def text_prints(text):
    """正文句子里的印法。吃**保留块边界**的文本、句中不许跨 \\n：表格最后一格后面紧跟的段落
    （'… (AUC) $ 33,422 102,035 For the three months … compared to $244 million …'）不会被读成一句。
    NCFA 带 $、AUC 不带 $ 说明抓错了数 —— 直接报错，不悄悄丢掉。"""
    out = []
    for rx in (_SENT_CMP, _SENT_ASOF):
        for m in rx.finditer(text):
            g = m.groupdict()
            metric = 'ncfa' if 'Funded' in g['metric'] else 'auc'
            raw = g['val'].replace(' ', '')
            if (metric == 'ncfa') == raw.startswith('$'):
                raise HoodIpoBasefillError(f'句式解析抓错了数（{metric} {raw}）：{_flat(m.group(0))[:300]}')
            month = '2020-06' if (g.get('md') == 'June' or g.get('q') == 'second') else '2020-09'
            out.append({'month': month, 'metric': metric, 'raw': raw, 'unit': g['unit'],
                        'kind': '文', 'flag': 'actual'})
    return out


_MENTION_PERIOD = {'2020-06': re.compile(r'\bJune\s+30\s*,\s*2020\b|\bsecond\s+quarter\s+of\s+2020\b', re.I),
                   '2020-09': re.compile(r'\bSeptember\s+30\s*,\s*2020\b|\bthird\s+quarter\s+of\s+2020\b', re.I)}
_MENTION_METRIC = {'ncfa': re.compile(r'Funded\s+Accounts', re.I),
                   'auc': re.compile(r'Assets\s+Under\s+Custody|\bAUC\b')}
_MENTION_NUM = {'ncfa': re.compile(r'\b\d+(?:\.\d+)?\s*million\b', re.I), 'auc': re.compile(r'\$\s?\d')}


def mentions(text):
    """→ {(月, 指标): [句子]}：同一句里同时有「指标名 + 该季末 + 数字」。不看数值，专抓解析器没见过的句式。"""
    out = {}
    for line in text.split('\n'):
        for sent in re.split(r'(?<=[.;!?])\s+|(?<=[.;!?][”"])\s+', line):
            for mo, prx in _MENTION_PERIOD.items():
                if not prx.search(sent):
                    continue
                for k in ('ncfa', 'auc'):
                    if _MENTION_METRIC[k].search(sent) and _MENTION_NUM[k].search(sent):
                        out.setdefault((mo, k), []).append(_flat(sent)[:240])
    return out


def _exact(p):
    """精确 = 与 KPI 表同精度：百万为单位、一位小数（NCFA 0.1M；AUC 0.1 $M）。"""
    return p['unit'] == 'million' and _places(p['raw']) == 1


def _round_ok(val, p):
    """取整印法（'$33,422' / '$33 billion'）是否等于精确值按它自己的位数四舍五入。"""
    scale = Decimal(1000) if p['unit'] == 'billion' else Decimal(1)
    q = Decimal(1).scaleb(-_places(p['raw']))
    return (Decimal(val) / scale).quantize(q, rounding=ROUND_HALF_UP) == _dec(p['raw'])


def scan_window(net, filings, keep):
    """S-1 起至 SCAN_END 的每份公开申报 → 文档记录。`keep` 里的 (accession, 文档) 顺手留下 lxml 根节点。"""
    s1 = next((f for f in filings if f['acc'] == S1[0]), None)
    if s1 is None:
        raise HoodIpoBasefillError(f'EDGAR 索引里找不到 S-1 {S1[0]}')
    before = [f for f in filings if f['accepted'] < s1['accepted']]
    loud = sorted({f"{f['form']} {f['acc']}" for f in before if f['form'] not in SKIP_FORMS})
    if loud:
        raise HoodIpoBasefillError(f'S-1 之前就有非草稿、非通知类的申报：{loud} —— 「S-1 是首份公开版本」不成立，先人工看')
    window = [f for f in filings if s1['accepted'] <= f['accepted'] < SCAN_END]
    unknown = sorted({f['form'] for f in window if f['form'] not in SCAN_FORMS and f['form'] not in SKIP_FORMS})
    if unknown:
        raise HoodIpoBasefillError(f'窗口内有没归类的申报类型 {unknown} —— 先决定扫不扫，再补进 SCAN_FORMS / SKIP_FORMS')
    docs, roots = [], {}
    for f in window:
        if f['form'] not in SCAN_FORMS:
            continue
        for name in filing_docs(net, f):
            root = _root(net.doc(f['acc'], name))
            text = _text(root)
            flat = _flat(text)
            docs.append({'filing': f, 'name': name, 'flat': flat, 'mentions': mentions(text),
                         'prints': table_prints(root, f"{f['form']} {f['acc']} {name}") + text_prints(text)})
            if (f['acc'], name) in keep:
                roots[(f['acc'], name)] = root
    skipped = {}
    for f in window:
        if f['form'] not in SCAN_FORMS:
            skipped[f['form']] = skipped.get(f['form'], 0) + 1
    return window, docs, skipped, roots, len(before)


def check_first_prints(window, docs, skipped, n_before):
    """看门狗 F。→ {(月, 指标): (原样值, source 文本)}。"""
    print(f'\n── 看门狗 F：2020-06 / 2020-09 最早精确印出（S-1 起至 2021-10-29：{len(window)} 份申报，'
          f'扫 {len({d["filing"]["acc"] for d in docs})} 份 / {len(docs)} 个文档）──')
    print(f'  S-1 之前 {n_before} 份申报全是 D / DRS / DRSLTR / UPLOAD 类 → S-1 是首份公开的有正文申报')
    print('  窗口内不扫：' + '、'.join(f'{k}×{v}（{SKIP_FORMS[k]}）' for k, v in sorted(skipped.items())))
    for d in docs:
        f = d['filing']
        seen = {}
        for p in d['prints']:
            if p['month'] in TARGET_MONTHS:
                tag = (f"{p['month'][2:]} {p['metric']} {p['raw']}{'' if _exact(p) else ' ' + p['unit'][:1] + '≈'}"
                       f"[{p['kind']}{'·估' if p['flag'] == 'estimate' else ''}]")
                seen[tag] = seen.get(tag, 0) + 1
        desc = '  '.join(t + (f'×{n}' if n > 1 else '') for t, n in seen.items())
        print(f"  {f['accepted'][:19]} {f['form']:<7} {f['acc']} {d['name'][:30]:<30} {desc or '—'}")

    out = {}
    for (mo, k), (want, src) in FIRST_PRINT.items():
        allp = [(d, p) for d in docs for p in d['prints']
                if p['month'] == mo and p['metric'] == k and p['flag'] == 'actual']
        exact = sorted(((d, p) for d, p in allp if _exact(p)), key=lambda dp: dp[0]['filing']['accepted'])
        if not exact:
            raise HoodIpoBasefillError(f'{mo} {k}: 窗口内一处精确印出都没找到')
        first = exact[0][0]
        vals = sorted({_plain(p['raw']) for d, p in exact if d is first})
        if len(vals) != 1:
            raise HoodIpoBasefillError(f'{mo} {k}: 最早那份文档自己就印了不止一个值 {vals}')
        val = vals[0]
        diff = sorted({(d['filing']['acc'], p['raw']) for d, p in exact if _plain(p['raw']) != val})
        if diff:
            raise HoodIpoBasefillError(f'{mo} {k}: 精确印法不同值（最早 {val}）：{diff} —— 有重述，先人工看')
        rounded = [(d, p) for d, p in allp if not _exact(p)]
        bad = [(d['filing']['acc'], p['raw'], p['unit']) for d, p in rounded if not _round_ok(val, p)]
        if bad:
            raise HoodIpoBasefillError(f'{mo} {k}: 取整印法与精确值 {val} 对不上：{bad}')
        earlier = [d for d in docs if d['filing']['accepted'] < first['filing']['accepted']]
        if k == 'auc':
            toks = {p['raw'].replace('$', '') for _, p in exact}
            hits = [(d['filing']['acc'], d['name'], t) for d in earlier for t in toks
                    if re.search(r'(?<![\d,.])' + re.escape(t) + r'(?!\d)', d['flat'])]
            if hits:
                raise HoodIpoBasefillError(f'{mo} {k}: 更早的文档里出现了精确值字样却没被解析出来：{hits}')
        unrec = [(d['filing']['acc'], d['name'], s) for d in earlier for s in d['mentions'].get((mo, k), [])
                 if not any(p['month'] == mo and p['metric'] == k for p in d['prints'])]
        if unrec:
            for acc, name, s in unrec[:6]:
                print(f'    未识别：{acc} {name}: {s}')
            raise HoodIpoBasefillError(f'{mo} {k}: 更早的文档里有「指标 + 季末 + 数字」的句子没被解析器认出 —— 先人工看')
        ff = first['filing']
        if ff['acc'] != want:
            raise HoodIpoBasefillError(
                f'{mo} {k}: 实测最早精确印出是 {ff["form"]} {ff["acc"]}（{ff["accepted"]}），'
                f'FIRST_PRINT 写的是 {want} —— 改 FIRST_PRINT 与 source 文本前先人工核对')
        print(f"  ⇒ {mo} {k.upper():<4} {val:<9} 最早：{ff['form']} {ff['acc']} {first['name']}（{ff['accepted'][:19]}）"
              f"；精确 {len(exact)} 处同值，取整 {len(rounded)} 处对得上，更早 {len(earlier)} 个文档无精确值/无漏识别 ✓")
        out[(mo, k)] = (val, src)
    return out


def seam_2021_06(docs):
    """2021-06 接缝行：10-Q Q2'21 KPI 表的 Jun-30-2021 列（文档里多张表同列必须同值）。"""
    d = next((d for d in docs if (d['filing']['acc'], d['name']) == Q2_10Q), None)
    if d is None:
        raise HoodIpoBasefillError(f'窗口里没扫到 10-Q Q2\'21 {Q2_10Q}')
    out = {}
    for k in ('ncfa', 'auc'):
        vals = {_plain(p['raw']) for p in d['prints']
                if p['month'] == '2021-06' and p['metric'] == k and p['flag'] == 'actual' and _exact(p)}
        if len(vals) != 1:
            raise HoodIpoBasefillError(f"10-Q Q2'21 的 2021-06 {k} 解出 {sorted(vals)}，不是唯一一个值")
        out[k] = vals.pop()
    return out


# ─────────────────────────── 看门狗 A–E ───────────────────────────
def check_sums(q):
    print('\n── 看门狗 A：季度收入 transaction + net interest + other == total（千美元，9 季）──')
    bad = []
    for qq in QUARTERS:
        parts = [int(_plain(q[c][qq])) for c in ('rev_transaction_usdk', 'rev_net_interest_usdk', 'rev_other_usdk')]
        tot = int(_plain(q['rev_total_usdk'][qq]))
        if sum(parts) != tot:
            bad.append((qq, parts, tot))
    print(f'  逐位相等 {len(QUARTERS) - len(bad)} 季；对不上 {len(bad)} 季')
    for qq, parts, tot in bad:
        print(f'    {qq}: {" + ".join(map(str, parts))} = {sum(parts)} ≠ {tot}')
    if bad:
        raise HoodIpoBasefillError('分项加不回合计 —— 行标签或列对齐错了，别写')


def check_424b4(kpi_a, q_a, kpi_b, q_b):
    print('\n── 看门狗 B：S-1 vs 424B4 逐格（原样字符串）──')
    diffs, n = [], 0
    for tbl, a, b in (('KPI 表', kpi_a, kpi_b), ('季度表', q_a, q_b)):
        for col in a:
            for per in a[col]:
                n += 1
                if a[col][per] != b.get(col, {}).get(per):
                    diffs.append((tbl, col, per, a[col][per], b.get(col, {}).get(per)))
    print(f'  逐格相同 {n - len(diffs)} 格；不同 {len(diffs)} 格')
    for tbl, col, per, x, y in diffs:
        print(f'    {tbl} {col} {per}: S-1 {x!r}  424B4 {y!r}')
    if diffs:
        raise HoodIpoBasefillError('S-1 与定价后的 424B4 对不上 —— 先人工看是哪一版改了数')


def check_seam(pit, qrev):
    print('\n── 看门狗 C：接缝行 vs 现有序列（hood.csv 2021-03/06；hood_q.csv 2021Q1）──')
    with open(HOOD_M_PATH, newline='', encoding='utf-8') as f:
        hm = {r['month']: r for r in csv.DictReader(f)}
    with open(HOOD_Q_PATH, newline='', encoding='utf-8') as f:
        hq = {r['quarter']: r for r in csv.DictReader(f)}
    bad = []
    for mo in ('2021-03', '2021-06'):
        row = hm.get(mo) or {}
        fc = (row.get('funded_customers_mn') or '').strip()
        tpa = (row.get('total_platform_assets_usdbn') or '').strip()
        nc, au = pit[mo]['funded_accounts_mn'], pit[mo]['auc_usdmn']
        want = (Decimal(au) / 1000).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)
        ok1 = bool(fc) and Decimal(fc) == Decimal(nc)
        ok2 = bool(tpa) and Decimal(tpa) == want
        gap = f'{Decimal(tpa) - Decimal(au) / 1000:+}' if tpa else '—'
        print(f'  {mo}  funded_customers_mn {fc or "空"} vs NCFA {nc} {"✓" if ok1 else "✗"}   '
              f'total_platform_assets_usdbn {tpa or "空"} vs round({au}/1000, 1) = {want}（实差 {gap}）{"✓" if ok2 else "✗"}')
        if not (ok1 and ok2):
            bad.append(mo)
    row = hq.get('2021Q1') or {}
    got = {}
    for col_k, col_m, tol in (('rev_transaction_usdk', 'rev_transaction_usdmn', 0),
                              ('rev_net_interest_usdk', 'rev_net_interest_usdmn', 0),
                              ('rev_other_usdk', 'rev_other_usdmn', 1),
                              ('rev_total_usdk', 'rev_total_usdmn', 0)):
        txt = (row.get(col_m) or '').strip()
        k = Decimal(_plain(qrev[col_k]['2021Q1']))
        mn = k / 1000
        rnd = mn.quantize(Decimal(1), rounding=ROUND_HALF_UP)
        if not txt:
            ok, m = False, None
        else:
            m = Decimal(txt)
            ok = (m == rnd) if tol == 0 else (abs(m - mn) <= tol)
        got[col_k] = (m, rnd)
        rule = '== round' if tol == 0 else '±1（rounding to foot）'
        print(f'  2021Q1 {col_m:<24} 现 {txt or "空"} vs S-1 {k:,}K = {mn}M，round = {rnd}'
              f'（实差 {m - mn:+}）{rule} {"✓" if ok else "✗"}' if m is not None else
              f'  2021Q1 {col_m:<24} 现 空 ✗')
        if not ok:
            bad.append(f'2021Q1 {col_m}')
    comps = ('rev_transaction_usdk', 'rev_net_interest_usdk', 'rev_other_usdk')
    if all(got[c][0] is not None for c in comps + ('rev_total_usdk',)):
        naive = sum(got[c][1] for c in comps)
        printed = sum(got[c][0] for c in comps)
        print(f'  rounding to foot：分项各自 round 相加 = {naive}、Supplement 印的分项相加 = {printed}、'
              f'合计 round = {got["rev_total_usdk"][1]} → Supplement 让分项加到取整后的合计')
    if bad:
        raise HoodIpoBasefillError(f'接缝对不上：{bad} —— 不是同一个量或同一口径，别写')


def _label_mn(lab):
    """图上标签 '40K' / '1.9M' → 百万（Decimal）。只做 K→M 单位换算。"""
    m = re.fullmatch(r'(\d+(?:\.\d+)?)([KM])', lab)
    if not m:
        raise HoodIpoBasefillError(f'图上标签认不出：{lab!r}')
    return Decimal(m.group(1)) / 1000 if m.group(2) == 'K' else Decimal(m.group(1))


def check_graphic(ye, kpi, s1_root, img, s1_flat):
    print('\n── 看门狗 D：年末 NCFA 单调 + customergrowth.jpg 标签 vs KPI 表 ──')
    refs = s1_root.xpath('//img[@src=$s]', s=IMG)
    sha = hashlib.sha256(img).hexdigest()
    print(f'  S-1 HTML 引用 {IMG} {len(refs)} 处；图 {len(img):,} bytes，sha256 {sha[:16]}…'
          f'{" == 读图那一份 ✓" if sha == IMG_SHA256 else " ≠ 读图那一份 ✗"}')
    bad = [] if refs and sha == IMG_SHA256 else ['图的引用或字节']
    for mo, lab in GRAPHIC:
        if mo in kpi['ncfa']:
            same = _label_mn(lab) == _dec(kpi['ncfa'][mo])
            print(f'  {mo}  图 {lab:<5} vs KPI 表 {kpi["ncfa"][mo]} {"✓" if same else "✗"}')
            if not same:
                bad.append(mo)
    q1 = _dec(kpi['ncfa']['2021-03'])
    ok_q1 = q1.quantize(Decimal(1), rounding=ROUND_HALF_UP) == _label_mn(GRAPHIC_Q1_2021)
    print(f'  2021-03  图 {GRAPHIC_Q1_2021}（取整标签）vs KPI 表 {kpi["ncfa"]["2021-03"]} 四舍五入 {"✓" if ok_q1 else "✗"}')
    seq = [Decimal(v) for _, v in ye]
    mono = len(seq) == 7 and all(b > a for a, b in zip(seq, seq[1:]))
    print(f'  年末 {ye[0][0]}→{ye[-1][0]}：' + ' < '.join(map(str, seq)) + (' 严格递增 ✓' if mono else ' ✗'))
    quote_ok = _squash(CLEARING_QUOTE) in _squash(s1_flat)
    print(f'  S-1 风险因素引文（2018-11 前 NCFA 用第三方清算商数据）{"仍在原文 ✓" if quote_ok else "找不到 ✗"}')
    if bad or not ok_q1 or not mono or not quote_ok:
        raise HoodIpoBasefillError('看门狗 D 不过（见上面 ✗）—— 图、表或引文对不上，别写')


def _sha(path):
    with open(path, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()


class Guard:
    """看门狗 E：只许新建两张表；现有两张序列写前写后逐字节不变。"""

    def __init__(self):
        self.before = {p: _sha(p) for p in (HOOD_M_PATH, HOOD_Q_PATH)}

    def check_rows(self, pit_rows, q_rows):
        print('\n── 看门狗 E：护栏 ──')
        months, quarters = [r[0] for r in pit_rows], [r[0] for r in q_rows]
        over = [m for m in months if m >= GUARD_M] + [q for q in quarters if q >= GUARD_Q]
        comma = [r[0] for r in pit_rows + q_rows if ',' in r[-1]]
        protected = {os.path.realpath(p) for p in self.before}
        clash = [p for p in (PIT_PATH, Q_PATH) if os.path.realpath(p) in protected]
        print(f'  月 {months[0]}…{months[-1]}（{len(months)} 行，< {GUARD_M}）；季 {quarters[0]}…{quarters[-1]}'
              f'（{len(quarters)} 行，< {GUARD_Q}）；越界 {len(over)}；source 含逗号 {len(comma)}；'
              f'输出撞现有序列 {len(clash)}')
        if over or clash or comma or months != PIT_MONTHS or quarters != QUARTERS:
            raise HoodIpoBasefillError(f'护栏不过：越界 {over}、行序 {months} / {quarters}、逗号 {comma}、撞表 {clash}')

    def check_untouched(self):
        changed = [os.path.relpath(p, ROOT) for p, h in self.before.items() if _sha(p) != h]
        print(f'  series/hood.csv、series/hood_q.csv sha256 与开跑时{"相同 ✓" if not changed else "不同 ✗"}')
        if changed:
            raise HoodIpoBasefillError(f'{changed} 在本次运行期间被改动了 —— 本脚本不许碰它们')


# ─────────────────────────── 组装 + 写盘 ───────────────────────────
def build_pit(kpi, first, seam):
    graphic = dict(GRAPHIC)
    rows = []
    for mo in PIT_MONTHS:
        if mo in ('2014-12', '2015-12', '2016-12'):
            lab = graphic[mo]
            rows.append([mo, str(_label_mn(lab)), '', f'S-1 {S1[0]} {IMG} (graphic label {lab}; rounded)'])
        elif mo in TARGET_MONTHS:
            (nv, ns), (av, as_) = first[(mo, 'ncfa')], first[(mo, 'auc')]
            rows.append([mo, nv, av, ns if ns == as_ else f'NCFA: {ns}; AUC: {as_}'])
        elif mo == '2021-06':
            rows.append([mo, seam['ncfa'], seam['auc'], f'{SRC_SEAM_Q2} (seam)'])
        else:
            rows.append([mo, _plain(kpi['ncfa'][mo]), _plain(kpi['auc'][mo]),
                         SRC_S1_KPI + (' (seam)' if mo == '2021-03' else '')])
    return rows


def build_q(q):
    return [[qq] + [_plain(q[c][qq]) for c in Q_HEADER[1:5]] + [SRC_S1_Q + (' (seam)' if qq == '2021Q1' else '')]
            for qq in QUARTERS]


def _csv_text(header, rows):
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator='\n')
    w.writerow(header)
    w.writerows(rows)
    return buf.getvalue()


def write(pit_rows, q_rows, dry, guard):
    outs = [(PIT_PATH, _csv_text(PIT_HEADER, pit_rows)), (Q_PATH, _csv_text(Q_HEADER, q_rows))]
    print('\n── 写盘 ──')
    for path, txt in outs:
        rel = os.path.relpath(path, ROOT)
        if os.path.exists(path):
            with open(path, encoding='utf-8', newline='') as f:
                if f.read() != txt:
                    raise HoodIpoBasefillError(f'{rel} 已存在且内容不同 —— 不覆盖；先人工 diff，确认后删掉旧文件再跑')
            print(f'  {rel} 已存在且内容相同')
        print(f'  {rel}（{len(txt.splitlines()) - 1} 行）：')
        for line in txt.splitlines():
            print('    ' + line)
    if dry:
        guard.check_untouched()
        print('  --dry：**未**写入')
        return 0
    for path, txt in outs:
        with open(path + '.part', 'w', encoding='utf-8', newline='') as f:
            f.write(txt)
        os.replace(path + '.part', path)
        print(f'✓ {os.path.relpath(path, ROOT)}')
    guard.check_untouched()
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description='HOOD 上市前历史回填 → series/hood_ipo_pit.csv、series/hood_ipo_q.csv')
    ap.add_argument('--dry', action='store_true', help='只核对、只打印，不写')
    ap.add_argument('--refresh', action='store_true', help='强制重下原件（含 EDGAR 申报索引）')
    ap.add_argument('--cache-dir', default=os.path.join(ROOT, 'cache', 'basefill', 'hood_ipo'))
    a = ap.parse_args(argv)

    guard = Guard()
    net = Net(a.cache_dir, a.refresh)
    print('── 下载 / 取缓存 ──')
    filings = edgar_filings(net)
    window, docs, skipped, roots, n_before = scan_window(net, filings, keep={S1, F424B4})
    img = net.doc(S1[0], IMG)
    print(f'  EDGAR 索引 {len(filings)} 份申报；原件取自缓存 {net.n_cache} 个、新下载 {net.n_net} 个 → {a.cache_dir}')
    if S1 not in roots or F424B4 not in roots:
        raise HoodIpoBasefillError('窗口扫描没拿到 S-1 或 424B4 的主文档')

    kpi, qrev = parse_kpi(roots[S1], 'S-1'), parse_quarterly(roots[S1], 'S-1')
    kpi_b, q_b = parse_kpi(roots[F424B4], '424B4'), parse_quarterly(roots[F424B4], '424B4')

    check_sums(qrev)
    check_424b4(kpi, qrev, kpi_b, q_b)
    first = check_first_prints(window, docs, skipped, n_before)

    pit_rows = build_pit(kpi, first, seam_2021_06(docs))
    q_rows = build_q(qrev)
    pit = {r[0]: dict(zip(PIT_HEADER, r)) for r in pit_rows}
    check_seam(pit, qrev)
    s1_flat = next(d['flat'] for d in docs if (d['filing']['acc'], d['name']) == S1)
    ye = [(mo, pit[mo]['funded_accounts_mn']) for mo in PIT_MONTHS if mo.endswith('-12') and mo <= '2020-12']
    check_graphic(ye, kpi, roots[S1], img, s1_flat)
    guard.check_rows(pit_rows, q_rows)
    return write(pit_rows, q_rows, a.dry, guard)


if __name__ == '__main__':
    sys.exit(main())
