# -*- coding: utf-8 -*-
"""LPL Financial Holdings (LPLA) 月度经营指标抓取。

═══ 数据源 ═══
索引页（唯一入口，必须爬，不能硬编码文件 URL）：
    https://investor.lpl.com/financials/monthly-results
真正要下的文件：该页每月挂两个 PDF，我们只用后者——
    "<Month> <Year> Monthly Metrics"            → 当月新闻稿，2018-05 期起有当月/上月/去年同月
                                                  三列；2017-01…2018-02 那几期只有两列、没有 Y/Y
    "<Month> <Year> Monthly Metrics Historical File" → **滚动 13 个月的全表**，update() 的唯一解析对象
外加**第三类、只用于一次性回补**：
    "Historical Monthly Activity through <Month> <Year>" → 2017-01…2019-05 那 19 期的老挂法
文件本体走 https://investor.lpl.com/static-files/<uuid>，uuid 每期都变且无规律，
所以 latest_month() / update() 每次都要重新爬索引页拿链接——**任何"记住的" URL 都会过期**。

为什么用 Historical File 而不是当月新闻稿：
  · 它一次给 13 个月，断更几个月后自动补齐，不必逐月回溯下载；
  · **它把季末月（3/6/9/12）也一并列出**，而季末月没有独立月度新闻稿。
    也就是说季末月不必去季报里抠——等下一份 Historical File 出来就有官方原值（见下文"口径坑 2"）。

反爬情况：无。普通 urllib + 常规浏览器 UA 即可 200（不带 UA 会被拒）。
无 Cloudflare / Akamai / PerimeterX，不需要登录态、不需要浏览器、不需要验证码 → 可无人值守。

═══ 发布节奏 ═══
月度新闻稿在**次月中旬**发布，实测：
    2025-08 → 2025-09-18   2025-10 → 2025-11-20   2025-11 → 2025-12-16
    2026-01 → 2026-02-19   2026-02 → 2026-03-19   2026-04 → 2026-05-21   2026-05 → 2026-06-16
即"次月第 3 个星期四前后（16–21 日）"。跑批建议放在每月 22 日之后。
季末月（3/6/9/12）**没有**自己的新闻稿，它随下一个月的 Historical File 一起出来，
所以 6 月数据要等 7 月报（≈8 月 20 日）——季末月天然比常规月晚一个发布周期。

上面这串日期不是推算出来的，逐个来自新闻稿自己的电头
"SAN DIEGO – June 16, 2026 – LPL Financial Holdings Inc. … today released its monthly
activity report for May 2026."。发布日经 record() 落进 series/source_dates.csv，
页面抬头「官方发布于 X」读的就是它（见 release_date()）。
**Historical File 本身没有发布日**——它只写 "As of May 31, 2026"（数据截止日，不是发布日），
PDF 元数据里的 CreationDate 是 Workiva 的排版时间（2026-05 那期是 6/12，比实际发布早 4 天），
两者都不能当发布日用，所以发布日一律去同期新闻稿的电头取。

═══ 口径坑（踩过的，别再踩） ═══
1) **series/lpla.csv 的 nna_* 三列是 "Total NNA"，含并购导入，不是 "Organic NNA"。**
   官方同页并排给三组：Organic NNA / Acquired NNA / Total NNA。
   核对锚点：2025-08 total 292.8 = organic 17.8 + acquired 275.0；2025-12 total 10.6 = 8.6 + 2.0。
   build/build_lpla.py 自己再用一张写死的 ACQ 字典把并购部分减掉出"有机"图，
   所以这里**必须存 Total NNA**，存成 Organic 会让 build 二次扣减、把并购月扣成负数。
2) 季末月无独立月报 → 见"发布节奏"。本模块只认 Historical File，**不从季报推算**。
   季报只给季度合计 NNA，要拿季末月得用"季合计 − 前两月"倒挤。
   拿 2024Q2–2026Q1 共 8 个季度回测过：**4 个存量列（advisory/brokerage/total/cash）每季全对**，
   但 **NNA 三列 8 个季度里有 6 个季度存在恰好 ±0.1 的偏差**（官方每列独立四舍五入，倒挤会放大）：
       2026Q1 brk −1.5/−1.6 | 2025Q4 total 10.5/10.6, adv 10.3/10.2, brk 0.5/0.4
       2025Q2 total 7.9/8.0, brk 0.0/0.1 | 2024Q4 total 25.7/25.8, brk 13.1/13.2
       2024Q3 brk 0.4/0.5 | 2024Q2 adv 9.3/9.2 |（2025Q3、2025Q1 全对）
   所以倒挤值**不进唯一真值表**，只在 quarter_end_estimate() 里提供，供"季报出了、下期月报还没出"
   的那 3 周抢先看一眼。
3) **client cash 被官方回溯重述过，重述发生在 Client Cash Account (CCA) 那一行。**
   同一个月在不同期 Historical File 里数值不同：2024-01 在 2024-01 期是 47.3（CCA 2.3），
   在 2025-01 期变成 46.9（CCA 1.9）；sweep 三行完全没动。2021 年底也有一次同类重述。
   → 回补历史时**必须用尽可能新的那期文件**，别拿当月那期。update() 只读最新一期，天然满足；
     重叠月份如有漂移会打印告警（默认不改写，见下）。
4) **PDF 行名 2026 年 4 月期改过版**，两套词表都得认，否则静默取不到值：
   旧（≤2026-02 期）：Advisory Assets / Brokerage Assets / Total Advisory and Brokerage Assets /
                      Net New Advisory Assets / Net New Brokerage Assets / Total Net New Assets
   新（≥2026-04 期）：分节表，节标题 Client Assets / Organic NNA / Acquired NNA / Total NNA，
                      节内行名退化成裸的 "Advisory" / "Brokerage"，必须靠节标题消歧。
   新格式里 "Advisory" 出现 4 次（资产、Organic、Acquired、Total NNA），只按行名匹配一定取错。
5) 表尾脚注区里还有一张 "Organic NNA from Large Institutions" 小表，行名同样是 Advisory/Brokerage。
   解析前必须在第一条脚注 "(1) " 处截断，否则小表会覆盖正表。
6) client_cash_usdbn 取 **Total Client Cash Balances**（含 CCA），不是 Total Bank Sweep、
   也不是 Total Client Cash Sweep Held by Third Parties。三者在表里上下相邻，很容易拿错。
7) 官方会把 sweep 货基转成 purchased money market（2025-11 转 1.6B、2026-02 转 0.5B）。
   这会让 client cash 出现**非资金流动导致的**下降，看图别当成客户提现。
8) 官方原表明写 "Totals may not foot due to rounding"，advisory + brokerage 与 total 差 0.1 属正常，
   所以本模块**不做 total = adv + brk 的硬校验**，只做"列必须存在"的硬校验。
9) 2025 年的 organic NNA 里含 OSJ（misaligned large OSJ）分离造成的流出，官方在脚注里逐月列出。
   本模块不做该调整——真值表存官方口径，调整留给 build 层。
10) **两处历史口径断点，都发生在 2019-2020 年，真值表里都已存在**（本模块只记录，不改写）：
   a) **NNA 定义**：官方在 **2020-04 期**把 Total Net New Assets 拆成两块相加，原文脚注
      "**Total Net New Assets equals the combination of Asset Inflows minus Outflows as well
      as Dividends plus Interest, minus Advisory Fees"。老定义 = 新表里
      "Asset Inflows minus Outflows" 那一行。同一个 2019-06：老册 1.9、新册 3.3。
      官方给得出新定义的最早月份是 2019-04（2020-04 期窗口最左列），而真值表 2019-04
      存的是老定义 0.7（新定义 0.9）、2019-05 起存的是新定义 —— 所以
      **真值表的断点落在 2019-04 | 2019-05 之间**，与本模块的回补无关。
      回补只是把老定义那一段从 2018-07 往前延到 2016-01，不新增断点。
   b) **client cash 口径**：2016-01…2019-03 官方行名是 'Total Cash Sweep Balances'
      （ICA + DCA + MMA）；2019-04 期改名 'Total Client Cash Balances' 并开始计入
      Purchased Money Market Funds（2019-04 是 0.4bn，到 2020-01 涨到 2.5bn）。
      真值表 2019-03=30.7（sweep）、2019-04=29.6（含 purchased MMF），断点同样早就在。
   两条都在 build/lpla.py 的 CAL_BREAKS 里登记并画成竖线，不靠图注一句话带过。
11) 2016-07 DCA 上线时 8.2bn 从 Money Market Account 转入 Deposit Cash Account，
   拆分行有台阶而 Total Cash Sweep 连续 —— 本仓只取合计行，不受影响。

═══ 解析器覆盖范围（实测，2026-08-18 全量回归） ═══
官网索引页共挂 51 期现行标签的 Historical File（2020-02 … 2026-05）+ 19 期老标签的
"Historical Monthly Activity through …"（2017-01 … 2019-05）+ 5 期**标题缺年份**的
"<Month> Monthly Metrics Historical File"（实为 2019-07/08/10/11、2020-01）。
本解析器把 51 期现行标签 **51/51 全部跑通**（此前只跑通 2022-07 起的 32 期，卡点是
两行式表头与单元格星号，已修）；老标签 19 期里 **17 期跑通**，2017-01 / 2017-02
两期原件整张表没有 Net New Assets 三行（官方当年未披露）故跳过 —— 也正因如此，
7 列俱全的最早月份是 **2016-01**（唯一出处是 2017-04 期那份 16 列的册子）。
标题缺年份那 5 期不接进任何通道：period 只能下载后从 PDF 标题反读，而它们覆盖的
2018-07…2020-01 早已在真值表里，接进来只增加取错期的风险。

═══ 真值表已知遗留偏差（本模块不改，只记录）═══
2026-08-18 重测：解析器修好之后现行标签 51 期全部可读，逐月取**覆盖该月的最新一期**
与 series/lpla.csv 全量交叉核对，(月, 列) 不一致共 **13 处**：
  · **7 处 client_cash_usdbn**（2021-07…2021-12 与 2023-04），成因是上面口径坑 3 的
    CCA 回溯重述——series 这些月停在重述前的旧值。要不要跟进由人决定。
  · **3 处 2019-04 的 nna_***（series 0.7/1.6/−1.0，官方 0.9/1.5/−0.6）：那是口径坑 10a
    的老/新定义之差，不是错值。真值表在这里从老定义切到新定义，断点已在 build 层登记。
  · **3 处 2019-08 的 nna_***（series 5.9/4.3/1.6，官方 3.0/3.3/−0.2）：2020-08 期起官方
    把这个月改印成**剔除 Allen & Company 之后**的数（差额正是脚注写的 1.0 advisory +
    1.8 brokerage）。series 存的是 as-reported（口径坑 1 要求如此），build/lpla.py 的
    ACQ['2019-08']=2.9 相减后得到 3.0，与官方那个 ex-Allen 值逐值相等 —— 两边其实一致，
    只是分工不同：真值表存 as-reported，还原留给 build 层。
  · **2024-05 的 brokerage/total 不再是偏差**。旧版这段曾断言「覆盖该月的 8 期官方文件
    无一例外都是 655.0 / 1464.4 → 真值表录入错误」。那个结论是抽样不足造成的：第 9 期
    （**2025-05 期**）已改印 **657.0 / 1466.4**，与真值表逐值相同。所以这是一次官方回溯
    重述，不是录入错误，**不需要改**。

═══ 两个入口 ═══
    python3 fetch/lpla.py --update     增量：下最新一期，往后长一格（monthly_run 走这条）
    python3 fetch/lpla.py --backfill   存量：把老标签那 19 期一次扫完，把 2016-01…2018-06
                                       补进 series（一次性；跑第二遍返回空列表）
两条通道**物理隔离**（_index_entries 的 want='historical' vs want='legacy'），
回补的老册永远不可能被 update() 当成「最新一期」。

═══ 幂等与不写 NaN ═══
update() 只追加 series 里没有的月份；已有月份一律不动（默认 revise=False，
只在数值漂移时打印告警，因为官方确实会重述，例如并购月的 acquired 拆分）。
任一目标列在 PDF 里没解析到 → 直接抛 ParseError，绝不写 NaN / 绝不填 0。
"""
from __future__ import annotations

import csv
import datetime
import io
import os
import re
import time
import urllib.error
import urllib.request

BASE = 'https://investor.lpl.com'
INDEX_URL = BASE + '/financials/monthly-results'
QUARTER_INDEX_URL = BASE + '/financials/quarterly-results'
STATIC_URL = BASE + '/static-files/%s'

# 不带 UA 会被站点拒掉；这里用常规桌面 Chrome UA，无需 cookie / 登录态
UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36')

# series/lpla.csv 的列名与顺序，唯一真值，不许改
MONTH_COL = 'month'
VALUE_COLS = [
    'total_assets_usdbn',
    'advisory_assets_usdbn',
    'brokerage_assets_usdbn',
    'nna_total_usdbn',
    'nna_advisory_usdbn',
    'nna_brokerage_usdbn',
    'client_cash_usdbn',
]

_MON = {m: i for i, m in enumerate(
    ['jan', 'feb', 'mar', 'apr', 'may', 'jun',
     'jul', 'aug', 'sep', 'oct', 'nov', 'dec'], 1)}
_MON_FULL = {'january': 1, 'february': 2, 'march': 3, 'april': 4, 'may': 5, 'june': 6,
             'july': 7, 'august': 8, 'september': 9, 'october': 10,
             'november': 11, 'december': 12}


class ParseError(RuntimeError):
    """PDF 结构变了 / 目标行找不到。宁可炸也不能静默写 NaN。"""


class SourceError(RuntimeError):
    """官方源取不到（网络、404、索引页改版）。"""


# ────────────────────────── 网络 ──────────────────────────

def _get(url, tries=3, timeout=60):
    """带 UA 的裸 urllib GET。源站无反爬，失败基本就是网络抖动，退避重试即可。"""
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={
                'User-Agent': UA,
                'Accept': '*/*',
                'Accept-Language': 'en-US,en;q=0.9',
            })
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except (urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
            last = e
            time.sleep(2 * (i + 1))
    raise SourceError('下载失败 %s: %r' % (url, last))


#: 索引页上一条链接文字的可分辨形态。
#: 实测（2026-08-18 抓下整页 161,437 bytes，264 条带文字的 <a> 全量聚类）共四类标签：
#:     'May 2026 Monthly Metrics'                    74 条 → 月度新闻稿（want='monthly'）
#:     'May 2026 Monthly Metrics Historical File'    51 条 → 现行滚动全表（want='historical'）
#:     'May 2026 Monthly Metrics Dashboard'          29 条 → 图表版，本模块不用
#:     'Historical Monthly Activity through May 2019' 19 条 → **2017-01…2019-05 的老版全表**
#: 最后这一类是 2019-05 及更早那 19 期的挂法，标题格式与现行完全不同。原先的正则
#: `^<Mon> <Yr> Monthly Metrics…` 对它一条都不命中，于是这 19 期在索引页上明明挂着、
#: update() 却永远看不见 —— 真值表 2018-07 以前的 30 个月因此一直是空的。
#:
#: **老标签单独一个桶（want='legacy'），不并进 'historical'**：update() 取的是
#: `entries[0]`（按 period 倒序的第一条 = 最新一期）。老标签的 period 都在 2019 年，
#: 并进去今天不会改变 entries[0]，但那是靠「2026 > 2019」这个巧合成立的；
#: 一旦官方哪天补挂一份老格式的新月份，update() 就会拿老版式去当最新期解析。
#: 分桶之后 update() 的取数通道与回补通道物理隔离，这种事不可能发生。
_LEGACY_LABEL = re.compile(
    r'^Historical Monthly Activity through\s+([A-Z][a-z]+)\s+(\d{4})$', re.I)

#: 现行标签的**容错**写法。原先写死 `Monthly Metrics` 与全拼月名，只认已经见过的那一种
#: 写法；标题是官方逐期手打的（同一页上就躺着一条尾巴写成 '062118' 的、还有 5 条整个
#: 年份都漏掉的），所以「下一期换个写法」不是假设而是这个源的既有行为。两处放宽：
#:   · 月份除全拼外也认三字母缩写（_MON 这张表模块里早就有，此前从没被用过）；
#:   · 'Monthly' 与 'Metrics' 之间允许多一个词（'Monthly Activity Metrics' 这类改写）。
#: 放宽只是把**能想到的**变体接住；真正兜住想不到那些的是下面 _index_entries 里的
#: 「未归类对账」——两者分工与 fetch/msci.py 的「容错正则 + 行数对账」完全同构：
#: 正则只认识见过的变体，对账负责在出现没见过的变体时**响亮地失败**。
_CURRENT_LABEL = re.compile(
    r'^([A-Z][a-z]+)\s+(\d{4})\s+Monthly\s+(?:\S+\s+)?Metrics\b(.*)$')

#: 「长得像本模块该管的文件」的判据，只用于未归类对账（见 _index_entries）。
#: 刻意收得很窄：必须是 /static-files/ 的下载直链，且标题里带 'Monthly Metrics' /
#: 'Monthly Activity' 的字面串，还得自报了月份或年份。窄是为了不误伤 ——
#: LPL 在这一页上增删过整个文档族（'… Monthly Metrics Dashboard' 这一族 2019-07 起挂、
#: 2023-01 停），将来再加一族是完全正常的行为，不该让 fetcher 天天 FAIL。
#: 而新加的族只要还是 '<Mon> <Yr> Monthly Metrics <X>' 这个形状，就会被
#: _CURRENT_LABEL 认出来、归进 'monthly' 桶，**根本走不到对账这一步**。
#: 月名两侧都要 \b，否则 'mar' 会命中 'Marketing'、'may' 会命中 'Mayfair'，
#: 把一份跟月度指标无关的文件误判成「该管却没管」的条目 —— 这道对账的每一次误伤
#: 都是一整天的 FAIL，宁可判据窄一点。月名表直接沿用模块里已有的两张，不另抄一份。
_METRICS_DOC = re.compile(r'monthly\s+(?:\S+\s+)?(?:metrics|activity)', re.I)
_HAS_PERIOD = re.compile(
    r'\b(?:19|20)\d{2}\b|\b(?:%s)\b'
    % '|'.join(sorted(set(_MON) | set(_MON_FULL), key=len, reverse=True)), re.I)

#: **标题缺年份的那 5 期**，按设计不接进任何通道（模块头「解析器覆盖范围」有交代：
#: 它们实为 2019-07/08/10/11 与 2020-01，覆盖的月份早就在真值表里，period 只能下载后
#: 从 PDF 标题反读，接进来只增加取错期的风险）。没有这张白名单，下面那道对账第一天
#: 就会把这 5 条判成「认不出的条目」并且天天 FAIL —— 白名单不是补丁，是把
#: 「我们知道它在、并且故意不要」这件事写进代码，好让对账只对**真的没见过**的东西发声。
_YEARLESS_HIST_TITLES = (
    'January Monthly Metrics Historical File',
    'July Monthly Metrics Historical File',
    'August Monthly Metrics Historical File',
    'October Monthly Metrics Historical File',
    'November Monthly Metrics Historical File',
)


def _index_entries(html_text, want='historical'):
    """从索引页 HTML 里抽出 (period 'YYYY-MM', 绝对 URL) 列表，按月份倒序。

    want='historical' 现行滚动全表 / want='monthly' 月度新闻稿 / want='legacy' 老版全表。
    前两者的条目文本形如 'May 2026 Monthly Metrics Historical File' / 'May 2026 Monthly
    Metrics'，只差尾巴，所以必须精确区分，不能只 in 'Monthly Metrics'；
    'legacy' 是完全另一套写法，见上面 _LABELS 的实测统计。

    ═══ 未归类对账（这道闸挡的是「不出声的失败」）═══
    原先的写法是：认不出的 <a> 一律 `continue`，只有**一条都认不出**时才抛。于是只要
    官方把**最新那一期**的标题改个写法（漏个年份、把 'Monthly Metrics' 写成
    'Monthly Activity Metrics'、在年份后面加个破折号），这一条就被静默丢掉，
    entries[0] 顺势变成上上期，update() 拿一份旧 PDF 解析 → 每个月份都已在 series 里
    → 打印「无新增月份」→ 干干净净 NOCHANGE。**连续失败十天和成功十天，日志里一模一样**，
    红点与断档都抓不到（它们只看已入库月份，看不见表尾少了一期）。
    所以这里改成：凡是「长得像本模块该管的文件」（_METRICS_DOC + _HAS_PERIOD +
    /static-files/ 直链）却一个桶都没进的条目，列出来抛 SourceError。
    这与 fetch/msci.py parse() 里的行数对账是同一件事的两个现场：
    **读不到不许不抛错**。判断「认没认出来」与 want 无关 —— want 只决定收进哪个桶。
    """
    if want not in ('historical', 'monthly', 'legacy'):
        raise ValueError('want 只能是 historical / monthly / legacy，给的是 %r' % want)
    out = {}
    stray = []
    yearless = set()
    for m in re.finditer(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', html_text, re.S):
        href = m.group(1)
        txt = re.sub(r'<[^>]+>', ' ', m.group(2))
        txt = re.sub(r'&[a-z]+;', ' ', txt)
        txt = re.sub(r'\s+', ' ', txt).strip()
        if not href.startswith('http'):
            href = BASE + href
        period, known = None, False
        legacy_m = _LEGACY_LABEL.match(txt)
        cur_m = _CURRENT_LABEL.match(txt)
        if legacy_m and _MON_FULL.get(legacy_m.group(1).lower()):
            known = True
            if want == 'legacy':
                period = '%s-%02d' % (legacy_m.group(2), _MON_FULL[legacy_m.group(1).lower()])
        elif cur_m:
            word = cur_m.group(1).lower()
            mon = _MON_FULL.get(word) or _MON.get(word)
            if mon:
                known = True
                # 尾巴用**包含**而不是 startswith 判：官方把它写成 '(Historical File)'
                # 或 '– Historical File' 时 startswith 就不成立，这一期会被错分进
                # 'monthly' 桶，want='historical' 于是静默退回上上期 —— 又是一次
                # 干净的 NOCHANGE。今天全页的尾巴只有 ''／'historical file'／
                # 'dashboard'／'062118' 四种，包含判在这四种上与原判据逐条等价。
                is_hist = 'historical' in cur_m.group(3).strip().lower()
                if want != 'legacy' and (want == 'historical') == is_hist:
                    period = '%s-%02d' % (cur_m.group(2), mon)
        if not known and txt in _YEARLESS_HIST_TITLES:
            known = True                      # 按设计跳过的那 5 期，见 _YEARLESS_HIST_TITLES
            yearless.add(href)
        if not known and '/static-files/' in href \
                and _METRICS_DOC.search(txt) and _HAS_PERIOD.search(txt):
            stray.append(txt)
        if period is None:
            continue
        out.setdefault(period, href)          # 同期重复时保留先出现的（页面按新→旧排）
    if stray:
        raise SourceError(
            '索引页上有 %d 条挂在 /static-files/ 的条目长得像月度指标文件、却一个通道都没归进去：'
            '%r。标题写法多半又变了（缺年份、月份缩写、多一个词、年份后加标点）—— '
            '这种条目被静默丢掉的后果不是报错而是 entries[0] 退回上一期、'
            'update() 干净地报「无新增月份」，所以宁可整次失败。'
            '请对照 cache/lpla_monthly_results_index.html 确认写法后改 _CURRENT_LABEL；'
            '若确认是官方新加的、本模块不要的文档族，让它能被 _CURRENT_LABEL 认出来'
            '（尾巴不含 historical 就自动归进月度新闻稿那个桶），或补一条显式白名单。页面：%s'
            % (len(stray), stray[:5], INDEX_URL))
    if len(yearless) > len(_YEARLESS_HIST_TITLES):
        raise SourceError(
            '索引页上「标题缺年份」的 Historical File 有 %d 条，白名单只登记了 %d 条。'
            '白名单是按标题全等匹配的，所以多出来的必然是**新挂的一期**——而白名单成立的'
            '前提（那 5 期覆盖的月份早已在真值表里）对新的一期不成立，静默跳过它就是漏一期。'
            '请人工确认这一条是哪个月，再决定接进哪个通道。页面：%s'
            % (len(yearless), len(_YEARLESS_HIST_TITLES), INDEX_URL))
    if not out:
        raise SourceError('索引页里没找到任何 %s 条目，页面结构可能改了：%s' % (want, INDEX_URL))
    return sorted(out.items(), key=lambda kv: kv[0], reverse=True)


def _fetch_latest_historical(cache_dir):
    """爬索引页 → 下最新一期 Historical File 到 cache。返回 (索引标称期, 本地路径, url)。"""
    os.makedirs(cache_dir, exist_ok=True)
    html_text = _get(INDEX_URL).decode('utf-8', 'replace')
    with open(os.path.join(cache_dir, 'lpla_monthly_results_index.html'), 'w') as f:
        f.write(html_text)
    entries = _index_entries(html_text, want='historical')
    period, url = entries[0]
    blob = _get(url)
    if not blob.startswith(b'%PDF'):
        raise SourceError('%s 拿回来的不是 PDF（前 16 字节 %r），链接可能变成了落地页' % (url, blob[:16]))
    path = os.path.join(cache_dir, 'lpla_hist_%s.pdf' % period)
    with open(path, 'wb') as f:
        f.write(blob)
    return period, path, url


# ────────────────────────── PDF 解析 ──────────────────────────

def _pdf_text(path):
    try:
        import pdfplumber
    except ImportError as e:                                  # noqa: F841
        raise ParseError('需要 pdfplumber 才能解析 LPL 的 PDF：pip install pdfplumber')
    with pdfplumber.open(path) as pdf:
        return '\n'.join(p.extract_text() or '' for p in pdf.pages)


def _star(tok):
    """去掉单元格上的脚注星号。

    官方在**个别单元格**上直接挂星号而不是角标：'4.0*'（2019-08 那三个 NNA 单元格，
    指向 Allen & Company 那条注）、'34.2**'（2020-02 的客户现金，指向 NNA 定义变更那条注）。
    不剥星号的后果不是报错而是**静默少一列**：'4.0*' 匹配不上数字正则，
    那一行就只剩 12 个值配 13 个月表头，parse_historical 的长度校验会把整期判成解析失败。
    实测这一个字符卡掉了 2019-10…2020-07 共 6 期。
    """
    return tok.strip('*')


def _numbers(s):
    """把一行里的数字取出来。会计负号是括号；千分位逗号要去掉；百分比 / bps 不算数字列。"""
    out = []
    for tok in s.split():
        tok = _star(tok)
        if tok.endswith('%') or tok.endswith('bps') or tok.endswith('bps)'):
            continue
        if not re.fullmatch(r'\(?-?\$?[\d,]+(\.\d+)?\)?', tok):
            continue
        neg = tok.startswith('(')
        t = tok.strip('()').replace(',', '').replace('$', '')
        if t in ('', '-'):
            continue
        try:
            v = float(t)
        except ValueError:
            continue
        out.append(-v if neg else v)
    return out


#: 「影子块」：官方在正表下面再印一遍**同名行、不同数值**的 pro-forma 版本，
#: 用来展示「如果没有这笔并购会是多少」。实测出现过三种写法：
#:     'Assets Served Prior to NPH*' / 'Net New Assets Prior to NPH*' /
#:     'Cash Sweep Balances Prior to NPH*' / 'Client Cash Balances Prior to NPH *'（2018-01…2019-05 期）
#:     'Net New Assets prior to Acquisitions'（2020-10…2021-02 期）
#: 三块与正表**交错排列**（正表资产 → 影子资产 → 正表 NNA → 影子 NNA → …），
#: 所以不能像脚注那样一刀截断，只能逐块跳过。
#: 现行代码靠 `rows.setdefault()`「先出现者胜」侥幸取到正表那份（影子块总在正表之后），
#: 但那是运气不是判据：影子块的值域与正表重叠（2018-04 期正表总资产 652.3、影子 580.1），
#: 一旦官方换个排序就会静默取错一整期。这里改成显式识别、显式跳过。
_SHADOW = re.compile(r'\bprior to\b', re.I)


def _rows(text):
    """把表格文本切成 {(节, 行名小写): [数值...]}。节用来给新格式的裸 Advisory/Brokerage 消歧。

    'Prior to …' 影子块整块跳过（见 _SHADOW）。
    """
    lines = [l.rstrip() for l in text.split('\n')]
    # 口径坑 4：脚注区还有同名行的小表，先截断
    for i, l in enumerate(lines):
        if re.match(r'^\(1\)\s', l.strip()):
            lines = lines[:i]
            break

    section, rows, shadow = None, {}, False
    for raw in lines:
        s = re.sub(r'\(\d+\)', '', raw).strip()      # 去掉行内脚注角标 (1)(2)…
        if not s:
            continue
        vals = _numbers(s)
        low = s.lower()
        if not vals:                                  # 无数字 = 节标题
            # 影子块由它自己的标题开启，由下一个**不带 'prior to' 的**标题关闭。
            shadow = bool(_SHADOW.search(low))
            if shadow:
                continue
            for pat, tag in (('client assets', 'assets'),
                             ('organic net new assets', 'organic'),
                             ('organic nna', 'organic'),
                             ('acquired nna', 'acquired'),
                             ('acquired net new assets', 'acquired'),
                             ('total nna', 'total_nna'),
                             ('client cash balances', 'cash')):
                if low.startswith(pat):
                    section = tag
                    break
            continue
        if shadow:
            continue
        # 行名 = 开头那串"非数值"词。不能用正则从第一个数字处切，
        # 因为季报里金额写成 "Advisory $ 1,548.4"，货币符号和数字之间有空格，会把 "$" 粘进行名。
        head = []
        for tok in s.split():
            # 与 _numbers() 用同一把尺子（含剥星号），否则 'Total Client Cash Balances 34.2**'
            # 会把 '34.2**' 当成行名的一部分，行名对不上 _PICK、整期解析失败。
            t = _star(tok)
            if re.match(r'^\(?-?\$?[\d,]+(\.\d+)?\)?$', t) or t in ('$', '—', '-', '(', 'n/m'):
                break
            head.append(tok)
        label = ' '.join(head).rstrip('$ ').strip().lower()
        rows.setdefault((section, label), vals)       # 只留首次出现（季报里 Brokerage 会重复）
    return rows


def _header_months(text):
    """表头 → ['2026-05', '2026-04', ...]，顺序即数据列顺序。两种版式都认。

    A) 现行（≥2020-10 期）：月份与年份挤在同一行，'May 2026 Apr 2026 …'。
    B) 老版（≤2020-07 期）：**月份一行、年份另一行**，中间还夹着单位说明 ——
           Apr Mar Feb Jan Dec Nov Oct Sep Aug Jul Jun May Apr
           (End of Period $ in billions, unless noted)
           2017 2017 2017 2017 2016 2016 2016 2016 2016 2016 2016 2016 2016
       只认 A 的话这一整代文件全部抛 ParseError，2019-05 及更早一个月都进不来。

    **列数不固定**：绝大多数期是 13 列，但 2017-04 期是 **16 列**（窗口 Jan-2016…Apr-2017）——
    正是这多出来的 3 列让 2016-01…2016-03 有了唯一的官方出处。所以这里返回多少给多少，
    不做「必须 13 列」的假设；长度由调用方与数据行逐一对齐校验。
    """
    lines = text.split('\n')
    for l in lines:
        ms = re.findall(r'\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{4})\b', l)
        if len(ms) >= 6:
            return ['%s-%02d' % (y, _MON[m.lower()]) for m, y in ms]
    # 版式 B：月份行之后 3 行内找一行年份，个数必须**恰好相等**才敢配对。
    # 不等就抛而不是截断对齐 —— 错位一列会让整期数据整体挪一个月，而且看不出来。
    for i, l in enumerate(lines):
        mons = re.findall(r'\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b', l)
        if len(mons) < 6:
            continue
        for j in range(i + 1, min(i + 4, len(lines))):
            yrs = re.findall(r'\b((?:19|20)\d\d)\b', lines[j])
            if not yrs:
                continue
            if len(yrs) != len(mons):
                raise ParseError('两行式表头对不齐：月份 %d 个（%r）、年份 %d 个（%r）'
                                 % (len(mons), l.strip()[:60], len(yrs), lines[j].strip()[:60]))
            return ['%s-%02d' % (y, _MON[m.lower()]) for m, y in zip(mons, yrs)]
    raise ParseError('找不到月份表头行，PDF 版式可能改了')


# 目标列 → 查找规则。两级：
#   strict：(节, 行名)。**新格式（≥2026-04 期）专用**，因为那里行名退化成裸的 Advisory/Brokerage，
#           一个文件里出现 4 次，只能靠节标题消歧。
#   loose ：只按行名找，且要求全表**唯一**命中。旧格式（≤2026-02 期）行名本身就带限定词
#           （Organic / Acquired / 光杆 = Total），全局唯一，反而不能信节标题：
#           旧版式里 "Acquired NNA" 小节标题在前、Total 那组行在后且没有自己的标题，
#           按节匹配会把 Total 那组误判进 acquired 节。
_PICK = {
    'advisory_assets_usdbn':  {'strict': [('assets', 'advisory')],
                               'loose': ['advisory assets']},
    'brokerage_assets_usdbn': {'strict': [('assets', 'brokerage')],
                               'loose': ['brokerage assets']},
    # 'total brokerage and advisory assets' 是 ≤2020-07 期的写法，与现行
    # 'total advisory and brokerage assets' **词序相反**。两条都得列，缺一整代文件取不到值。
    'total_assets_usdbn':     {'strict': [('assets', 'total client assets')],
                               'loose': ['total advisory and brokerage assets',
                                         'total client assets',
                                         'total brokerage and advisory assets']},
    'nna_advisory_usdbn':     {'strict': [('total_nna', 'advisory')],
                               'loose': ['net new advisory assets']},
    'nna_brokerage_usdbn':    {'strict': [('total_nna', 'brokerage')],
                               'loose': ['net new brokerage assets']},
    'nna_total_usdbn':        {'strict': [('total_nna', 'total nna')],
                               'loose': ['total net new assets']},
    # 'total cash sweep balances' 是 ≤2019-03 的行名（ICA + DCA + MMA）。官方在 2019-04 期
    # 把这一行改名 'Total Client Cash Balances' 并开始把 Purchased Money Market Funds 计入
    # （2019-04 是 0.4bn）—— 这是**口径断点**，不是纯改名，见口径坑 10。
    # 排序有意：先认现行行名，两条同时存在的文件目前一份都没有，但真出现时应以现行为准。
    'client_cash_usdbn':      {'strict': [('cash', 'total client cash balances')],
                               'loose': ['total client cash balances',
                                         'total cash sweep balances']},
}


def _lookup(rows, col, rule, path):
    for key in rule['strict']:
        if key in rows:
            return rows[key]
    for label in rule['loose']:
        hits = [v for (_sec, lab), v in rows.items() if lab == label]
        if not hits:
            continue
        # 季报里同一行会在 "Client Assets" 和 "Assets by Platform" 两块各印一次，
        # 数值完全相同——这种重复不算歧义，只有数值不同才是真歧义。
        if all(h == hits[0] for h in hits):
            return hits[0]
        raise ParseError('列 %s 的行名 %r 在 %s 里出现 %d 次且数值不一致，无法消歧'
                         % (col, label, path, len(hits)))
    raise ParseError('PDF 里找不到列 %s 对应的行（strict=%r loose=%r）；'
                     '官方很可能又改行名了，先人工看 %s'
                     % (col, rule['strict'], rule['loose'], path))


def parse_historical(path):
    """解析一期 Historical File → {'YYYY-MM': {列: 值}}。任一目标列缺失直接抛。

    注意 nna_* 取的是 **Total NNA**（含并购导入），见口径坑 1。
    """
    text = _pdf_text(path)
    months = _header_months(text)
    rows = _rows(text)

    picked = {}
    for col, rule in _PICK.items():
        vals = _lookup(rows, col, rule, path)
        if len(vals) < len(months):
            raise ParseError('列 %s 只解析到 %d 个值，表头有 %d 个月（%s）'
                             % (col, len(vals), len(months), path))
        picked[col] = vals[:len(months)]

    out = {}
    for i, mth in enumerate(months):
        out[mth] = {c: picked[c][i] for c in VALUE_COLS}
    return out


def source_month(path):
    """PDF 标题 'Historical Monthly Activity Through May 2026' → '2026-05'。
    以文件自述为准，不信索引页标题（索引页是人工录入的，理论上可能写错）。"""
    text = _pdf_text(path)
    m = re.search(r'Through\s+([A-Z][a-z]+)\s+(\d{4})', text)
    if not m:
        raise ParseError('PDF 标题里读不出 "Through <Month> <Year>"：' + path)
    return '%s-%02d' % (m.group(2), _MON_FULL[m.group(1).lower()])


# ────────────────────────── 发布日 ──────────────────────────
# 电头两种写法都出现过：主锚点是城市，备用锚点是紧跟在日期后面的公司名——
# 官方哪天从 SAN DIEGO 搬走，第二条还能接住；两条都不中就抛，不猜。
_DATELINE = (
    re.compile(r'SAN\s+DIEGO\s*,?\s*[–—-]\s*([A-Z][a-z]+)\s+(\d{1,2}),\s*(\d{4})'),
    re.compile(r'\b([A-Z][a-z]+)\s+(\d{1,2}),\s*(\d{4})\s*[–—-]\s*LPL\s+Financial'),
)


def _source_dates():
    """按路径加载仓库根的 source_dates.py（发布日台账）。

    不能裸 import：本模块被 monthly_run 用 spec_from_file_location 加载，
    那时 sys.path 上既没有 fetch/ 也没有仓库根。
    """
    import importlib.util
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    spec = importlib.util.spec_from_file_location(
        'source_dates', os.path.join(root, 'source_dates.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def release_period(month):
    """数据月 month **第一次被官方发出来**是在哪一期月报里，返回 'YYYY-MM'。

    常规月就是它自己那一期。季末月（3/6/9/12）没有独立新闻稿，它是随下一期的
    Historical File 一起首发的（见"发布节奏"），所以 6 月数据的发布日 = 7 月那期的日期。
    照着"6 月数据就查 6 月那期"去记会有两个后果：6 月那期根本不存在，
    真找到个近似的又会把发布日记早整整一个月。
    """
    y, mo = int(month[:4]), int(month[5:7])
    if mo % 3 == 0:
        y, mo = (y + 1, 1) if mo == 12 else (y, mo + 1)
    return '%04d-%02d' % (y, mo)


def _fetch_release(cache_dir, period):
    """下某一期的**月度新闻稿**（不是 Historical File）到 cache，返回本地路径。

    两个文件挂在索引页同一组条目里、只差标题尾巴，所以复用 _index_entries，
    不为发布日另起一条抓取通道。
    """
    os.makedirs(cache_dir, exist_ok=True)
    idx_path = os.path.join(cache_dir, 'lpla_monthly_results_index.html')
    entries = {}
    if os.path.exists(idx_path):
        try:
            with open(idx_path) as f:
                entries = dict(_index_entries(f.read(), want='monthly'))
        except (SourceError, OSError):
            entries = {}                  # 缓存里躺着的可能是半截文件，重爬即可
    if period not in entries:             # 缓存的索引页也可能是上一轮的，缺这一期就重爬
        html_text = _get(INDEX_URL).decode('utf-8', 'replace')
        with open(idx_path, 'w') as f:
            f.write(html_text)
        entries = dict(_index_entries(html_text, want='monthly'))
    if period not in entries:
        raise SourceError('索引页里没有 %s 那期月度新闻稿；若 %s 是季末月，那它本来就没有'
                          % (period, period))
    blob = _get(entries[period])
    if not blob.startswith(b'%PDF'):
        raise SourceError('%s 拿回来的不是 PDF（前 16 字节 %r）' % (entries[period], blob[:16]))
    path = os.path.join(cache_dir, 'lpla_pr_%s.pdf' % period)
    with open(path, 'wb') as f:
        f.write(blob)
    return path


def release_date(cache_dir, month):
    """数据月 month 的官方发布日，返回 ('YYYY-MM-DD', 出处文字)。

    唯一取值处是新闻稿电头那句 "SAN DIEGO – June 16, 2026 –"，即官方自己写的发布日。
    取不到就抛——页面抬头少半句远好过印一个看不出是假的日期，所以这里没有任何
    "退回今天 / 退回文件 mtime / 按上期节奏推算"的兜底。
    """
    period = release_period(month)
    path = _fetch_release(cache_dir, period)
    text = _pdf_text(path)

    # 先确认这份稿子报的确实是 period 那个月：索引页标题是人工录入的，理论上会挂错文件，
    # 而挂错的后果是把 A 月的发布日安到 B 月头上，页面照样理直气壮地印出来。
    m = re.search(r'Monthly Activity\s+for\s+([A-Za-z]+)\s+(\d{4})', text, re.I)
    if not m or m.group(1).lower() not in _MON_FULL:
        raise ParseError('新闻稿里读不出 "Monthly Activity for <Month> <Year>"：' + path)
    said = '%s-%02d' % (m.group(2), _MON_FULL[m.group(1).lower()])
    if said != period:
        raise ParseError('索引页 %s 那期挂的是 %s 的新闻稿（%s）' % (period, said, path))

    for pat in _DATELINE:
        d = pat.search(text)
        if d:
            break
    else:
        raise ParseError('新闻稿电头里读不出 "<城市> – <Month> <D>, <Year> –"：' + path)
    mon = _MON_FULL.get(d.group(1).lower())
    if not mon:
        raise ParseError('电头月份 %r 不认识：%s' % (d.group(1), path))
    day = '%s-%02d-%02d' % (d.group(3), mon, int(d.group(2)))
    if day[:7] < period:
        # 发布日早于它自己报的那个月 = 匹配到了正文里别的日期（脚注常有 "as of June 30, 2025"）
        raise ParseError('电头日期 %s 早于该期月份 %s，多半匹配错了：%s' % (day, period, path))

    ev = '新闻稿 %s 电头 "%s –"' % (os.path.basename(path), d.group(0))
    if period != month:
        ev = '%s 是季末月、无独立月报，数据随 %s 那期首发；%s' % (month, period, ev)
    return day, ev


# ────────────────────────── 两道哨兵（挡"不出声的失败"）──────────────────────────
# 上面 _index_entries 那道对账是从**页面有什么**这一侧查：认不出的条目要喊。
# 下面两道从另外两侧查，盲区互不重叠 —— 三道一起，索引页那一层才算封住。

def _crosscheck_source_not_regressed(src_month, existing, path, period):
    """源自报的最新月**倒退到已入库月份之前**就炸。便宜的兜底，不需要任何额外请求。

    防的是这一类：索引页最新那条被改了写法 / 被错分了桶，entries[0] 悄悄退回上上期，
    于是我们下回来的是一份旧 PDF。它自己解析得干干净净、七列俱全、覆盖的每个月都已经
    在 series 里，于是 update() 打印「无新增月份」返回 [] —— 缺列护栏、断档检查、
    新鲜度红点全都不响，日志和真正没有新数据的那些天一模一样。
    这道判据独立于解析器：不看 PDF 内容长什么样，只问「源给回来的期次比我们手里的旧吗」。

    不会误伤源的正常前进：这张滚动表只往前走（季末月没有独立期，所以跨季时一次走两格），
    src_month == max(existing) 是新数据出来之前的常态，只有**严格变旧**才抛。
    真正会让它响一次的是官方撤下已发布的一期再重发 —— 那一次响亮的失败正是要的结果，
    monthly_run 按家隔离，只这一家 FAIL。
    """
    if not existing:
        return
    newest_stored = max(existing)
    if src_month < newest_stored:
        raise SourceError(
            '源倒退了：这一期 Historical File 自报最新月是 %s（索引标称 %s），'
            'series/lpla.csv 里却已经有 %s。这张表只会往前走，所以最可能是索引页最新那条'
            '标题改了写法、被 _index_entries 静默丢掉，entries[0] 退回了更早的一期'
            '（后果是 update() 干净地报「无新增月份」，谁都不会发现）；'
            '也可能是官方撤下重发。文件 %s。拒绝写入，请人工看一眼索引页。'
            % (src_month, period, newest_stored, os.path.basename(path)))


#: Historical File 允许比同期月度新闻稿晚出多少天，超过就判成"这一路停了"。
#: 取值依据是模块头「发布节奏」记的两件事：两个 PDF 每期**同一批挂上去**（索引页上
#: 2020-02 以来 52 期逐期成对，无一例外），而两期之间隔约一个月。所以真正的同批时差
#: 是小时级，14 天是它的十几倍余量 —— 留这么宽是因为发布当天的抢跑（新闻稿先挂、
#: Historical File 晚几分钟）绝不该把一整天的批次判 FAIL。同时 14 天又稳稳短于一个
#: 发布周期，所以 Historical File 这一族真要是停更了，哨兵会在下一期新闻稿到来之前
#: 就开始天天喊，不会被下一期"接上"而永远沉默。
_HIST_LAG_TOLERANCE_DAYS = 14


def _press_release_dateline(cache_dir, period):
    """取 period 那一期**月度新闻稿**电头上的日期，返回 'YYYY-MM-DD'。

    不走 release_date()：那个函数收的是**数据月**，会把季末月映射到下一期
    （release_period），而这里手上已经是索引页上的**期次**本身，再映射一次就取错文件。
    只此一处差别，别把两者合并。
    """
    text = _pdf_text(_fetch_release(cache_dir, period))
    for pat in _DATELINE:
        d = pat.search(text)
        if d:
            break
    else:
        raise ParseError('新闻稿电头里读不出 "<城市> – <Month> <D>, <Year> –"：%s 期' % period)
    mon = _MON_FULL.get(d.group(1).lower())
    if not mon:
        raise ParseError('电头月份 %r 不认识：%s 期' % (d.group(1), period))
    return '%s-%02d-%02d' % (d.group(3), mon, int(d.group(2)))


def _crosscheck_press_release_lead(cache_dir, hist_period, verbose=True):
    """拿**月度新闻稿那一路**当独立外部判据，对账 Historical File 这一路的最新期。

    与 fetch/cboe.py 的 _crosscheck_report_month、fetch/ice.py 的
    _crosscheck_workbook_month 同形：判据必须来自解析器之外，否则解析器认不出的东西，
    对账一样认不出。这里的外部判据是同一页上**另一条通道**的最新期 —— 两个标题由官方
    逐期分别手打，一处写错不会同时写错另一处。

    为什么非要它：_crosscheck_source_not_regressed 只在源退到**已入库月份之前**才响，
    而真正的坏法往往是「新那期从没进来过」—— 官方发了 M 月，Historical File 那条标题
    写法一变就被丢掉，我们手里最新的仍是 M-1 期，src_month == max(existing)，
    没有任何东西倒退，NOCHANGE 干干净净。这时新闻稿那一路已经走到 M，一对账就现形。

    两条已知的误伤路径，都按房规处理，不靠"警告一下"糊过去：
      · **发布当天抢跑**：新闻稿先挂、Historical File 晚几分钟。所以拿新闻稿电头上的
        官方发布日算年龄，只有超过 _HIST_LAG_TOLERANCE_DAYS 才抛；抢跑当天只打印一行。
      · **文档族退役**：'… Monthly Metrics Dashboard' 那一族 2019-07 起挂、2023-01 停，
        官方确实会停掉整族。若 Historical File 这一族也停了，这道哨兵会天天 FAIL ——
        那是对的：本模块的取数通道只有它，族没了就等于再也拿不到新数据，
        必须有人来改，而不是让页面安静地挂着旧数字。
    """
    idx_path = os.path.join(cache_dir, 'lpla_monthly_results_index.html')
    if not os.path.exists(idx_path):
        return                                # 索引页还没落盘（只可能出现在直接调用时）
    with open(idx_path) as f:
        pr_period = _index_entries(f.read(), want='monthly')[0][0]
    if pr_period <= hist_period:
        return                                # 常态：两路同期
    day = _press_release_dateline(cache_dir, pr_period)
    age = (datetime.date.today()
           - datetime.date(int(day[:4]), int(day[5:7]), int(day[8:10]))).days
    if age <= _HIST_LAG_TOLERANCE_DAYS:
        if verbose:
            print('[lpla] 新闻稿已到 %s、Historical File 还停在 %s，'
                  '但新闻稿是 %s 才发的（%d 天），在 %d 天容忍期内，先放行'
                  % (pr_period, hist_period, day, age, _HIST_LAG_TOLERANCE_DAYS))
        return
    raise SourceError(
        '月度新闻稿已经出到 %s（官方电头 %s，%d 天前），Historical File 这一路却还停在 %s。'
        '两者每期同批发布，索引页上 2020-02 以来 52 期逐期成对，所以差这么久只有两种可能：'
        'Historical File 那条标题改了写法被 _index_entries 丢掉，或者官方停掉了整个文档族。'
        '本模块的取数通道只有 Historical File，两种情况都意味着**再也长不出新月份**，'
        '而它的表现是每天干净地报「无新增月份」—— 所以这里拒绝写入并抛错。页面：%s'
        % (pr_period, day, age, hist_period, INDEX_URL))


# ────────────────────────── CSV 读写 ──────────────────────────

def _read_series(csv_path):
    """返回 (表头原文, 列位置, {月: 值}, {月: 原始行文本})。

    保留原始行文本是为了让 update() 把**已有行原样搬过去**——
    重新格式化会把历史上写成 '-0.0' 的单元格变成 '0.0'，那就等于动了真值表。
    """
    with open(csv_path, newline='') as f:
        raw = f.read().split('\n')
    raw = [l for l in raw if l.strip()]
    header_line, body = raw[0], raw[1:]
    header = next(csv.reader([header_line]))
    missing = [c for c in [MONTH_COL] + VALUE_COLS if c not in header]
    if missing:
        raise RuntimeError('series/lpla.csv 缺列 %r，列名不许改' % missing)
    idx = {c: header.index(c) for c in [MONTH_COL] + VALUE_COLS}
    data, lines = {}, {}
    for line in body:
        r = next(csv.reader([line]))
        mth = r[idx[MONTH_COL]]
        data[mth] = {c: float(r[idx[c]]) for c in VALUE_COLS}
        lines[mth] = line
    return header_line, idx, data, lines


def _fmt(v):
    """官方就是 1 位小数，直接照抄，不做任何再加工。"""
    s = '%.1f' % v
    return '0.0' if s == '-0.0' else s


# ────────────────────────── 对外 API ──────────────────────────

def latest_month(cache_dir):
    """官方源当前最新月 'YYYY-MM'。抓不到 / 解析不出 → 抛异常，不返回 None。

    返回的是最新一期 Historical File 覆盖到的月份。季末月因为随下一期才出现，
    在季报发布到下一期月报之间会"看起来落后一个月"，这是源本身的节奏，不是 bug。
    """
    _, path, _ = _fetch_latest_historical(cache_dir)
    return source_month(path)


def update(series_dir, cache_dir, revise=False, verbose=True):
    """把官方新月份写进 series/lpla.csv，返回新增月份列表（升序）。

    幂等：series 里已存在的月份不重复追加。
    revise=False（默认）时，重叠月份即使官方重述也**不改动**已有行，只打印告警——
    真值表的历史由人决定何时改。revise=True 才会就地改写重述值。
    """
    csv_path = os.path.join(series_dir, 'lpla.csv')
    header_line, idx, existing, raw_lines = _read_series(csv_path)
    ncol = len(next(csv.reader([header_line])))

    period, path, url = _fetch_latest_historical(cache_dir)
    src_month = source_month(path)
    if verbose:
        print('[lpla] 源文件 %s（索引标称 %s，自述 %s）\n[lpla] %s' % (path, period, src_month, url))

    # 三道哨兵里的后两道（第一道在 _index_entries 里）。都放在解析之前：
    # 它们要挡的正是「解析得干干净净、只是解析的是上一期」这种没有红字的失败。
    _crosscheck_source_not_regressed(src_month, existing, path, period)
    _crosscheck_press_release_lead(cache_dir, period, verbose=verbose)

    parsed = parse_historical(path)
    if src_month not in parsed:
        raise ParseError('PDF 自述最新月 %s 不在解析出的月份里 %r' % (src_month, sorted(parsed)))

    # 重叠月份对账：官方重述（尤其并购月的 acquired 拆分）会在这里现形
    drift = []
    for mth in sorted(set(parsed) & set(existing)):
        for c in VALUE_COLS:
            a, b = existing[mth][c], parsed[mth][c]
            if abs(a - b) > 0.05:
                drift.append((mth, c, a, b))
    if drift and verbose:
        print('[lpla] 官方与 series 不一致 %d 处（%s）：' % (len(drift), '已改写' if revise else '未改写'))
        for mth, c, a, b in drift:
            print('       %s %s: series=%.1f 官方=%.1f' % (mth, c, a, b))

    new_months = sorted(set(parsed) - set(existing))
    if not new_months and not (revise and drift):
        if verbose:
            print('[lpla] 无新增月份，series 已到 %s' % max(existing))
        return []

    def render(mth, vals):
        row = [''] * ncol
        row[idx[MONTH_COL]] = mth
        for c in VALUE_COLS:
            row[idx[c]] = _fmt(vals[c])
        buf = io.StringIO()
        csv.writer(buf, lineterminator='').writerow(row)
        return buf.getvalue()

    out = dict(raw_lines)                       # 已有行原样保留，一个字符都不动
    for mth in new_months:
        out[mth] = render(mth, parsed[mth])
    if revise:
        for mth in sorted({d[0] for d in drift}):
            vals = dict(existing[mth])
            for m2, c, _a, b in drift:
                if m2 == mth:
                    vals[c] = b
            out[mth] = render(mth, vals)

    tmp = csv_path + '.tmp'
    with open(tmp, 'w') as f:
        f.write(header_line + '\n')
        for mth in sorted(out):
            f.write(out[mth] + '\n')
    os.replace(tmp, csv_path)
    if verbose:
        print('[lpla] 新增 %d 个月：%s' % (len(new_months), ', '.join(new_months)))

    # 发布日只对**真的落进 series 的月份**作证，所以放在 os.replace 之后：
    # 解析炸了或写盘没成时，台账上不该多出一行说"这个月官方发过了"。
    # 抓不到发布日不影响数据入库——那是主任务，日期是附加事实，所以这里吞掉异常只告警。
    for mth in new_months:
        try:
            day, ev = release_date(cache_dir, mth)
            _source_dates().record(series_dir, 'lpla', mth, day, ev)
            if verbose:
                print('[lpla] %s 发布日 %s（%s）' % (mth, day, ev))
        except (SourceError, ParseError, ValueError, OSError) as e:
            if verbose:
                print('[lpla] %s 的发布日没拿到，页面抬头会少「官方发布于」半句：%s' % (mth, e))
    return new_months


# ────────────────────────── 存量回补（老版 Historical File） ──────────────────────────

#: 回补时**允许**与既有真值表不一致的格子。每一条都要写清「为什么两边都对」。
#: 不在这张表里的任何一处不一致 → 整次回补失败（宁可不补，也不静默改口径）。
#:
#: 2019-05 三个 NNA 列：官方在 **2020-04 期**把 Total Net New Assets 的定义改了 ——
#: 那一期起表里多出两块（Asset Inflows minus Outflows / Dividends plus Interest minus
#: Advisory Fees），原文脚注写明「**Total Net New Assets equals the combination of Asset
#: Inflows minus Outflows as well as Dividends plus Interest, minus Advisory Fees」。
#: 老定义 = 新表里的「Asset Inflows minus Outflows」那一行。
#: 2019-05 在老册里是 1.4/2.5/(1.1)（老定义），真值表里存的 2.0/2.8/(0.8) 是新定义。
#: 官方能给出新定义的最早月份就是 2019-04（2020-04 期窗口的最左列），而真值表 2019-04
#: 存的又是老定义 0.7/1.6/(1.0) —— 所以**真值表自己的口径断点落在 2019-04|2019-05 之间**，
#: 与本次回补无关，回补只是把老定义那一段从 2018-07 往前延长到 2016-01。
#: 这条断点在 build/lpla.py 的 CAL_BREAKS 里登记、并在图上画出来。
_KNOWN_DRIFT = {
    ('2019-05', 'nna_total_usdbn'),
    ('2019-05', 'nna_advisory_usdbn'),
    ('2019-05', 'nna_brokerage_usdbn'),
}


def _fetch_legacy(cache_dir, period, url):
    """下一期老版 Historical File 到 cache，返回本地路径。已在 cache 里就直接用。"""
    os.makedirs(cache_dir, exist_ok=True)
    path = os.path.join(cache_dir, 'lpla_legacy_%s.pdf' % period)
    if os.path.exists(path) and os.path.getsize(path) > 4096:
        return path
    blob = _get(url)
    if not blob.startswith(b'%PDF'):
        raise SourceError('%s 拿回来的不是 PDF（前 16 字节 %r）' % (url, blob[:16]))
    with open(path, 'wb') as f:
        f.write(blob)
    return path


def backfill(series_dir, cache_dir, verbose=True):
    """把 2016-01…2018-06 的历史月份补进 series/lpla.csv，返回新增月份（升序）。

    ═══ 与 update() 的分工 ═══
    update() 管**增量**：只下最新一期 Historical File，往后长一格。它永远够不到存量，
    因为老月份的唯一出处是**老标签**（'Historical Monthly Activity through …'）那 19 期，
    而 update() 的取数通道（want='historical'）按设计只认现行标签。
    backfill() 管**存量**：把那 19 期一次扫完，谁也不越界。

    ═══ 三道自检，任何一道不过就整次失败（宁可不补）═══
    1) **跨册对账**：19 期两两之间有大量重叠月（每期 13 列、相邻期只差 1–3 个月）。
       同一个月在不同册里必须逐值相等。实测 17 期可解析、41 个月、**0 处冲突** ——
       这是「行名取对了没有、列有没有错位」最硬的一道检验，比任何肉眼核对都强。
    2) **与真值表对账**：老册覆盖到 2018-07…2019-05 共 11 个月，那 11 个月已在 series 里。
       77 个格子必须逐格相等，例外只允许出现在 _KNOWN_DRIFT 里（当前 3 格，见上）。
       实测 74/77 相等。
    3) **逐月连号**：写完之后整张表必须一个月不缺（load() 也会再查一次，这里提前拦）。

    ═══ 取哪一册的值 ═══
    同一个月被多册覆盖时取**最新的那一册**（口径坑 3：官方会回溯重述）。因为第 1 道
    自检要求跨册全等，这条规则今天等于没有分歧，但它是正确的默认。
    **只在老标签这 19 期里选**，不掺现行标签的册子 —— 掺进来就会把 2020-04 期之后的
    NNA 新定义带回 2019 年，那才是真的「拿后期重述值盖历史」。

    ═══ 幂等 ═══
    只追加 series 里没有的月份；已有行一个字符都不动（连重排都不做，沿用 update() 的
    「原始行文本原样搬过去」写法）。跑第二遍返回空列表。

    ═══ 发布日为什么不写 ═══
    2016-01…2016-11 的月度新闻稿根本不在索引页上（最老的一期是 2017-01），
    release_date() 对它们必抛 SourceError；而 series/source_dates.csv 是全站共用台账，
    一次性回补往里塞 30 行「查不到」的记录只会污染它。这些月份的页面抬头不会有
    「官方发布于」半句 —— 数据本身不受影响，抬头只对最新月印那半句。
    """
    csv_path = os.path.join(series_dir, 'lpla.csv')
    header_line, idx, existing, raw_lines = _read_series(csv_path)
    ncol = len(next(csv.reader([header_line])))

    def log(*a):
        if verbose:
            print(*a)

    os.makedirs(cache_dir, exist_ok=True)
    html_text = _get(INDEX_URL).decode('utf-8', 'replace')
    with open(os.path.join(cache_dir, 'lpla_monthly_results_index.html'), 'w') as f:
        f.write(html_text)
    entries = _index_entries(html_text, want='legacy')
    log('[lpla] 索引页上的老版 Historical File %d 期：%s … %s'
        % (len(entries), entries[0][0], entries[-1][0]))

    merged, origin, skipped = {}, {}, []
    conflicts = []
    for period, url in entries:                       # 新 → 旧
        path = _fetch_legacy(cache_dir, period, url)
        try:
            parsed = parse_historical(path)
        except ParseError as e:
            # 只容忍一种已知缺列：2017-02 及更早的册子**整张表没有 NNA 三行**
            # （'Net New' 全文不出现），那是官方当年就没披露，不是解析坏了。
            # 其余任何 ParseError 都是版式变了，必须炸出来。
            if 'nna_' not in str(e):
                raise
            skipped.append((period, '该期原件没有 Net New Assets 三行（官方当年未披露）'))
            continue
        said = source_month(path)
        if said != period:
            raise ParseError('索引页 %s 那期挂的却是 %s 的文件（%s）' % (period, said, path))
        for mth, vals in parsed.items():
            if mth in merged:
                for c in VALUE_COLS:
                    if abs(merged[mth][c] - vals[c]) > 0.05:
                        conflicts.append((mth, c, origin[mth], merged[mth][c], period, vals[c]))
                continue
            merged[mth], origin[mth] = vals, period

    for period, why in skipped:
        log('[lpla] 跳过 %s 期：%s' % (period, why))
    if conflicts:
        for mth, c, p1, v1, p2, v2 in conflicts:
            print('[lpla] 跨册冲突 %s %s：%s 期=%.1f，%s 期=%.1f' % (mth, c, p1, v1, p2, v2))
        raise ParseError('老册之间对不上 %d 处（见上），回补中止 —— '
                         '要么解析取错了行/列，要么官方重述过，两种都得人看' % len(conflicts))
    if not merged:
        raise SourceError('一期老册都没解析成功，回补中止')
    log('[lpla] %d 期解析成功，覆盖 %s … %s（%d 个月），跨册冲突 0 处'
        % (len(entries) - len(skipped), min(merged), max(merged), len(merged)))

    # 自检 2：与真值表逐格对账
    ov = sorted(set(merged) & set(existing))
    bad = []
    for mth in ov:
        for c in VALUE_COLS:
            if abs(merged[mth][c] - existing[mth][c]) <= 0.05:
                continue
            if (mth, c) in _KNOWN_DRIFT:
                log('[lpla] 已登记的口径差异 %s %s：series=%.1f（新定义） 老册=%.1f（老定义）'
                    % (mth, c, existing[mth][c], merged[mth][c]))
            else:
                bad.append((mth, c, existing[mth][c], merged[mth][c]))
    if bad:
        for mth, c, a, b in bad:
            print('[lpla] 重叠月不一致 %s %s：series=%.1f 老册=%.1f' % (mth, c, a, b))
        raise ParseError('老册与 series 在 %d 处对不上且未登记（见上），回补中止' % len(bad))
    log('[lpla] 与真值表重叠 %d 个月 × %d 列 = %d 格，未登记的不一致 0 处'
        % (len(ov), len(VALUE_COLS), len(ov) * len(VALUE_COLS)))

    new_months = sorted(set(merged) - set(existing))
    if not new_months:
        log('[lpla] 没有可补的月份，series 已自 %s 起' % min(existing))
        return []

    def render(mth, vals):
        row = [''] * ncol
        row[idx[MONTH_COL]] = mth
        for c in VALUE_COLS:
            row[idx[c]] = _fmt(vals[c])
        buf = io.StringIO()
        csv.writer(buf, lineterminator='').writerow(row)
        return buf.getvalue()

    out = dict(raw_lines)                       # 已有行原样保留，一个字符都不动
    for mth in new_months:
        out[mth] = render(mth, merged[mth])

    # 自检 3：逐月连号（写盘之前查，别把断档的表写出去再让 build 炸）
    keys = sorted(out)
    for a, b in zip(keys, keys[1:]):
        ya, ma = int(a[:4]), int(a[5:7])
        yb, mb = int(b[:4]), int(b[5:7])
        if (yb * 12 + mb) - (ya * 12 + ma) != 1:
            raise ParseError('回补后月份不连续：%s → %s' % (a, b))

    tmp = csv_path + '.tmp'
    with open(tmp, 'w') as f:
        f.write(header_line + '\n')
        for mth in keys:
            f.write(out[mth] + '\n')
    os.replace(tmp, csv_path)
    log('[lpla] 回补 %d 个月：%s … %s（各月出处：%s）'
        % (len(new_months), new_months[0], new_months[-1],
           '、'.join('%s←%s 期' % (m, origin[m]) for m in new_months[:3]) + ' …'))
    return new_months


# ────────────────────────── 季末月倒挤（默认不用） ──────────────────────────

def quarter_end_estimate(series_dir, cache_dir, quarter=None):
    """用季报把季末月倒挤出来。**默认不接进 update()**，因为有 ±0.1 的四舍五入误差。

    存量三列（advisory / brokerage / total / cash）季报直接给季末时点值，是精确的；
    只有 NNA 三列要靠"季合计 − 季内前两月"倒挤。实测 2026Q1：
        Mar advisory 倒挤 9.7 = 官方 9.7 ✓
        Mar total    倒挤 8.1 = 官方 8.1 ✓
        Mar brokerage倒挤 −1.5 vs 官方 −1.6 ✗（差 0.1，纯四舍五入）
    所以它只适合"季报出了但下一期月报还没出"的那 3 周里抢先看一眼，
    不适合写进唯一真值表。返回 (month, {列: 值}, 说明)。
    """
    html_text = _get(QUARTER_INDEX_URL).decode('utf-8', 'replace')
    rel = {}
    for m in re.finditer(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', html_text, re.S):
        txt = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', m.group(2))).strip()
        mm = re.match(r'^Q([1-4])\s+(\d{4})\s+Press Release$', txt)
        if mm:
            key = '%sQ%s' % (mm.group(2), mm.group(1))
            href = m.group(1)
            rel.setdefault(key, href if href.startswith('http') else BASE + href)
    if not rel:
        raise SourceError('季报索引页里没找到 "Qn YYYY Press Release"：' + QUARTER_INDEX_URL)
    quarter = quarter or max(rel)
    if quarter not in rel:
        raise SourceError('没有 %s 的季报，现有 %r' % (quarter, sorted(rel)))

    os.makedirs(cache_dir, exist_ok=True)
    path = os.path.join(cache_dir, 'lpla_q_%s.pdf' % quarter)
    with open(path, 'wb') as f:
        f.write(_get(rel[quarter]))

    # 季报是 20+ 页，"Advisory assets" 这种行名在多张表里各出现一次（含一张补充的月度表），
    # 列数还不一样。所以先把文本切到 "Operating Metrics" 起、"Interest-Earning Assets" 止
    # 这一段——经营指标三块（资产 / NNA / 客户现金）都在里面，且行名唯一。
    text = _pdf_text(path)
    a = text.find('Operating Metrics')
    c = text.find('Total Client Cash Balances', a if a > 0 else 0)
    if a < 0 or c < 0:
        raise ParseError('季报里定位不到 Operating Metrics … Total Client Cash Balances 区段：' + path)
    b = text.find('\n', c)
    rows = _rows(text[a:b if b > 0 else len(text)])
    yr, q = int(quarter[:4]), int(quarter[-1])
    qend = '%d-%02d' % (yr, q * 3)
    prior = ['%d-%02d' % (yr, q * 3 - 2), '%d-%02d' % (yr, q * 3 - 1)]

    _, _, existing, _ = _read_series(os.path.join(series_dir, 'lpla.csv'))
    if any(p not in existing for p in prior):
        raise RuntimeError('倒挤需要季内前两月 %r 已在 series 里' % prior)

    # 季报的行名和月报同源，新旧两套词表复用 _PICK；每行第一个数字 = 本季
    vals = {}
    for col in ('advisory_assets_usdbn', 'brokerage_assets_usdbn',
                'total_assets_usdbn', 'client_cash_usdbn'):
        vals[col] = _lookup(rows, col, _PICK[col], path)[0]
    for col in ('nna_advisory_usdbn', 'nna_brokerage_usdbn', 'nna_total_usdbn'):
        q_total = _lookup(rows, col, _PICK[col], path)[0]
        vals[col] = round(q_total - sum(existing[p][col] for p in prior), 1)
    note = ('存量列取自季报时点值（精确）；NNA 三列 = 季合计 − %s，存在 ±0.1 四舍五入误差，'
            '等 %s 的 Historical File 出来后应以官方为准' % ('+'.join(prior), qend))
    return qend, vals, note


if __name__ == '__main__':
    import sys
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if '--backfill' in sys.argv:
        # 存量回补是一次性动作，跑它时不必先去探最新月（那是 update() 的事）
        print(backfill(os.path.join(root, 'series'), os.path.join(root, 'cache')))
        sys.exit(0)
    print('latest:', latest_month(os.path.join(root, 'cache')))
    if '--update' in sys.argv:
        print(update(os.path.join(root, 'series'), os.path.join(root, 'cache')))
