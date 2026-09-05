# -*- coding: utf-8 -*-
"""Costco (COST) SEC 申报层抓取 —— 分部收入 / 客单与客流 / 财年单店经济 / 开业年份矩阵。

═══ 这个模块存在的理由 ═══
`/cost/` 页原本只有 `series/cost.csv`（GlobeNewswire 月度销售稿，见 fetch/cost.py）。
页面所有者要的三件事**月度稿里一件都没有**，只存在于 SEC 申报里：
  (a) 收入的地区结构（US / Canada / Other International）；
  (b) 把 comp 拆成客单（ticket）与客流（traffic）；
  (c) 单店平均收入 + 新开一家仓的盈亏平衡测算。
所以本模块与 fetch/cost.py **并列**，各写各的 CSV，互不读写对方的文件。

五张表 → 五个函数，一次 update() 全写：
  series/cost_seg_q.csv    季度 / 财年分部收入（10-K/10-Q 的 XBRL instance）
  series/cost_tkt_q.csv    季度 Sales/Ticket/Traffic 分部表（8-K EX-99.2 补充资料）
  series/cost_fy.csv       财年利润表 + 分国家仓数 + 面积（10-K 的 XBRL + Item 2 HTML）
  series/cost_cohort.csv   10-K「Average Sales Per Warehouse」开业年份矩阵（纯 HTML）
  series/cost_fy_be.csv    FY2011–FY2015 合并损益回填，**只喂盈亏平衡两条线**
                           （老一代 XBRL 元素名，见 FY_BE_TAGS / FY_BE_FIRST）

═══ 源与节奏 ═══
· 申报清单 https://data.sec.gov/submissions/CIK0000909832.json
  （2016 年以前的还要再读一份 `...-submissions-001.json`，EDGAR 把老件分页了）
· 10-Q 在季末约 3-4 周后，10-K 在财年结束后约 5-6 周。
· 8-K(Item 2.02) 业绩稿**早于** 10-Q 约一周（实测 FY26Q3：8-K 2026-05-28、10-Q 2026-06-03）。
  所以「拿到 8-K 补充资料的那一刻，同一季的分部收入行还不存在」是常态，不是异常。
· EDGAR 不设 Cloudflare，标准库 urllib + 带邮箱的 User-Agent 即可；UA 里没有联系方式
  整站 403。SEC 限速 <10 req/s，本模块串行 + sleep，远低于上限。

═══ 全局口径坑（各表都要知道）═══
1. **companyfacts API 会静默丢掉所有带维度的事实。** `https://data.sec.gov/api/xbrl/
   companyfacts/CIK0000909832.json` 里 `Revenues` 只有合并口径，分部那三条**一条都没有**
   —— 不是报错，是这个接口的设计就只收无维度事实。用它去做分部会得到一张空表而全程没有
   任何异常。所以本模块**逐篇下载 10-K/10-Q 的 XBRL instance 自己解**，慢一点，但拿得到。
2. **序列从 FY2011 开始，不是能取多早取多早。** Costco 在 2010-08-30（FY2011 第一天）把
   持股 50% 的墨西哥合资公司**从当期起**并表，且**没有重述**之前的年份。跨这条线看
   Other International 会看到一个凭空 +59% 的假跳（FY2010 6,271 → FY2011 9,991），
   而两边各自都是真实披露值。这不是可以「标个断点照画」的事：FY2010 及更早的
   Other International 与之后**不是同一个业务口径**，本模块干脆不出这些行。
3. **分部注释报的是 TOTAL REVENUE（净销售额 + 会员费），不是净销售额。**
   FY2025：200,046 / 36,923 / 38,266 = 275,235，而 total net sales 是 269,912，
   差的 5,323 正是 FY2025 的会员费收入。**画图时不要和 series/cost.csv 的
   `net_sales_bn` 放在同一根轴上**，那是两个口径。
4. **分部轴换过。** FY2025 10-K（2025-10-08，采用 ASU 2023-07）起用
   `us-gaap:StatementBusinessSegmentsAxis`，之前用 `srt:StatementGeographicalAxis`；
   成员名换过三代（`cost:UnitedStatesOperationsMember` → `country:US` →
   `cost:UnitedStatesMember`）。两套轴、三代成员**全部都要认**，只认一套会让序列
   在某个财年整段消失 —— 而「整段消失」在 CSV 里长得就像「公司那年没披露」。
5. **重述政策两张表不一样，别抄串了：**
     · cost_seg_q.csv（分部收入）**冲突即抛**。同一个 (start, end, region) 在两篇申报里
       给出不同的值 = 有人重述了收入，那是必须人来看的事。回溯 2011 年以来 62 篇申报，
       这道护栏一次都没响过 —— 正因为它一次都没响过，它才是有效的哨兵。
     · cost_fy.csv（财年利润表 / 分部经营利润）**取最新申报值**。这里的重述是真实发生过的：
         FY2020 分部经营利润初次申报 3,633 / 860 / 942，FY2022 10-K 重述为
         3,822 / 778 / 835（合计 5,435 不变）；
         FY2020 / FY2021 的 SG&A 被上调了**恰好等于当年开办费**的金额
         （16,332 → 16,387、18,461 → 18,537）。
       取最新值是为了让整条序列**内部可比**；混着取会在 FY2020 处造出一个假台阶。
       **但「取最新值」在分部经营利润上做不到内部可比 —— 见口径坑 6。**

6. **分部经营利润有一条口径断线，而且「取最新值」修不好它。**
   FY2022 10-K（accession `0000909832-22-000021`）原文逐字：

     "Effective for fiscal 2022, stock-based compensation was allocated to the segments
      in this reporting. This change reflected a decision to evaluate the financial
      performance of the segments inclusive of this expense. Operating income was
      restated in each of the segments for all prior periods to reflect this change."

   问题出在 "all prior periods" 这半句上：那篇 10-K **只列示 FY2022 / FY2021 / FY2020
   三年**，所以被真正重述过的历史只有 FY2020 与 FY2021 两年，FY2019 及更早**没有任何
   一篇申报重述过**。2026-09 逐篇 10-K 的 XBRL 实扫（这张表本身没进 `--selftest`：
   它要下载 15 篇 instance；`_SELFTEST_SEG_OI_BASIS` 钉的是**由申报日判口径**那段逻辑，
   用的是这里同一批真实 accession 与申报日）：
     FY2020  0000909832-20-000017 / -21-000014 都是 3,633 / 860 / 942
             → 0000909832-22-000021 改成 3,822 / 778 / 835
     FY2021  0000909832-21-000014 是 4,262 / 1,176 / 1,270
             → 0000909832-22-000021 改成 4,470 / 1,093 / 1,145
     FY2016-FY2019  只出现在 FY2022 10-K 之前的申报里，值从未变过
   于是「取最新值」得到的是**两个口径拼起来的一条线**：FY2016-FY2019 是分部不含股酬，
   FY2020 起是分部含股酬。分部经营利润率画出来就是：
     Other International  3.83%(FY19) → 3.76%(FY20)，一个**假的下滑**
     Canada               4.32%(FY19) → 3.47%(FY20)，一个更大的假下滑
     United States        2.74%(FY19) → 3.13%(FY20)，一个假的跃升
   —— 三条全是股酬重新分摊的影子，跟经营一点关系没有。同一年**换口径重算**才是真相：
   FY2020 老口径 OI 是 942/22,185 = 4.25%，也就是 FY19→FY20 其实是**升**的。

   所以 cost_fy.csv 出一列 `seg_oi_basis`（`pre-sbc-alloc` / `sbc-alloc`），**把断点写进
   数据里**，下游画图可以据此画断线、或直接丢掉断点之前的年份，不必回头翻 10-K。
   这一列不是硬编码年份来的，是按「这一年的分部经营利润最后由哪篇申报供给」与
   `SEG_OI_RESTATE_ACC` 的申报日比出来的（见 `_seg_oi_basis`）。

   **合并口径的 `op_income_mn` 不受影响**，这不是推断而是核过的：逐篇比对 FY2016 起
   每一年的 `us-gaap:OperatingIncomeLoss`（无维度），跨申报**一次都没变过**
   （FY2020 在 3 篇 10-K 里都是 5,435，FY2021 在 3 篇里都是 6,708，
   跨过重述那一篇也没动）—— 股酬只是在三个分部之间挪位置，
   合计不动。`_assert_consolidated_oi_stable` 每次跑都把这句话重验一遍，
   它哪天不成立了这句注释就会当场变成假话并抛异常，而不是留在这里骗人。
   同理，「三个分部合计 = 合并」那条恒等式**两个口径下都成立**（重述前后合计都是 5,435），
   所以它**探测不到这条断线** —— 这正是必须单出一列的理由，别指望恒等式替你把关。

7. **`sga_mn` 这一列每一行都已含开办费（preopening expense），没有例外。**
   这是本表对下游的硬承诺，配套的 `preopen_mn` 是「已经含在 `sga_mn` 里的那一笔是多少」。
   于是 `sga_mn - preopen_mn`（preopen_mn 有值的年份）在整条序列上是同一个口径，
   不用先判断年份、也不用先读某个 flag。三段历史殊途同归：
     FY2016-FY2019  申报里开办费是**单列**的一行，SG&A 不含它 → 本模块加进去
     FY2020-FY2021  Costco 自己在 FY2022 10-K 重述时并了进去（16,332+55=16,387、
                    18,461+76=18,537），XBRL 读到的 `sga_mn` **已经含了**，本模块不动
     FY2022 起      源里根本没有开办费这条线了 → `preopen_mn` 留空
   `preopen_src` 那一列记的是**上面三段里的哪一段**（`loader-folded` / `issuer-folded` /
   `not-disclosed`），它描述的是来路，不是「含没含」—— 含是无条件的。
   （这一列原名 `sga_folded_preopen`，那个名字读起来像在说「sga_mn 含不含开办费」，
   而它记的其实是「这一轮加载器折没折」，FY2020/FY2021 因此挂 0 却又照样有
   `preopen_mn`，下游按 flag 决定减不减就会拿 FY2016 的 12,068 去比 FY2020 的 16,387。
   改名连同 `_write` 的 `renamed` 迁移一起做，见那里的注释。）

═══ 反爬与缓存 ═══
下载全部落在 `cache/cost_sec/`（cache/ 已 gitignore）。命中缓存就不发请求，
所以第二次跑几乎不联网 —— 这也是幂等性测试能跑得动的原因。

═══ 幂等 ═══
五张 CSV 每次**整表重写**（不是追加），内容完全由申报决定，因此没有新申报时
输出逐字节相同。monthly_run.py:937 的 `series_fingerprint` 按内容 hash 触发重建，
且它 glob 的是 `series/cost*.csv` —— 本模块这几张表**都在它的 glob 里**，
输出但凡每次都动一个字节，`/cost/` 就会天天无谓重建。
"""
import csv
import datetime
import html as _html
import io
import json
import os
import re
import sys
import time
import urllib.request
import zipfile
import xml.etree.ElementTree as ET
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SERIES = os.path.join(ROOT, 'series')

CIK = '909832'                                   # Costco Wholesale Corp
CIK10 = CIK.zfill(10)
ARCHIVE = f'https://www.sec.gov/Archives/edgar/data/{CIK}'

#: SEC 要求 UA 里带真实联系方式，否则整站 403。这不是可选项。
USER_AGENT = os.environ.get('SEC_EDGAR_UA', 'hzhan7@gmail.com research')

#: 相邻两次请求的最小间隔（秒）。SEC 的上限是 10 req/s，这里留 ~6 倍余量。
_MIN_INTERVAL = 0.15

XBRLI = '{http://www.xbrl.org/2003/instance}'
XBRLDI = '{http://xbrl.org/2006/xbrldi}'

#: 序列下界。理由见模块 docstring 口径坑 2（墨西哥合资公司 2010-08-30 起并表且未重述）。
FY2011_START = '2010-08-30'

#: 只扫这一天以后申报的件。**不是省流量，是这之前根本没有 XBRL**：
#: Costco 的申报里最早带 instance 的是 2011 年那几篇，再往前的 10-K/10-Q 目录里
#: 一个 .xml 都没有，硬扫只会得到一串「找不到 XBRL instance」。
#: FY2011 Q1（2010-08-30 起）不会因此丢掉 —— 它作为**上年同期**印在 FY2012 Q1 的 10-Q 里。
XBRL_FROM = '2011-01-01'

#: cost_fy.csv 的下界。**不是随便挑的**：`us-gaap:NumberOfStores` 带国家维度、
#: 以及净销售额/会员费的 `ProductOrServiceAxis` 拆分，都是从 FY2016 10-K 才开始打标签的
#: （实测 FY2016..FY2025 共 10 个财年有，FY2015 及更早一个都没有）。
#: 再往前只能拿 `SalesRevenueNet` 硬凑，且仓数那几列必然全空 —— 那种半空的行
#: 正是 README「缺列一律失败」要挡的东西，所以宁可把序列砍短。
FY_FIRST = 2016

#: `cost_fy_be.csv` 的下界。这张**回填表**只装 FY2011–FY{FY_FIRST-1}，且**只装
#: 盈亏平衡算得动的那几列**（合并损益五个数），不装仓数、面积、分部 —— 那几样老年份
#: 确实没有（见 FY_FIRST 的注释，那条仍然成立）。
#: 为什么另起一张表而不是把 `cost_fy.csv` 的左端放宽：`cost_fy.csv` 的家规是
#: 「除 optional 三列外每一列都必须有值」，把 FY2011–FY2015 塞进去就得把二十多列
#: 一起挪进 optional —— 那等于给**所有**年份（含 FY2016 起那十年）的缺列发了长期
#: 许可证，而那条护栏正是 README「缺列一律失败」的执行版。回填另立一张窄表，
#: 两边各自保持满列，是 `cost_tkt_q_ir.csv` 已经走过的同一条路。
#: 左端 2011 不是「能翻多早翻多早」：墨西哥合资公司自 FY2011 第一天（2010-08-30）
#: 起并表且往年不重述（口径坑 2 / FY2011_START），FY2010 与 FY2011 不可比。
FY_BE_FIRST = 2011

#: 老口径（FY2015 及更早）的元素名。**与 FY_TAGS 是两代，不是同一套的别名**：
#:   · 净销售额 FY2015 及更早叫 `SalesRevenueNet`（无维度）；FY2018 10-K 起改叫
#:     `RevenueFromContractWithCustomerExcludingAssessedTax`，而那个名字**无维度时
#:     是总收入不是净销售额**（FY2016 无维度值 118,719 = 总收入），净销售额要靠
#:     `ProductOrServiceAxis` 拆出来 —— 所以两代绝不能并进一个元组「都接受」，
#:     那样 FY2016 会静默拿到总收入当净销售额。两代各走各的 dict，只在 FY2016 那一年
#:     重叠着对过一次账（116,073 / 2,646 / 102,901 两代逐个相等，实测）。
#:   · 会员费老名字长得不像话，是 us-gaap 当年的分类法原样。
#:   · 商品成本 `CostOfGoodsSold` → 新era 的 `CostOfGoodsAndServicesSold`。
#: 全部要求**无维度**（`not dims`）—— `SalesRevenueNet` 同时还带分部轴（SEG_REV_TAGS
#: 就在用它），不卡这一条会把某个地区的数当成合并数。
FY_BE_TAGS = {
    'net_sales_mn': 'SalesRevenueNet',
    'memb_fee_mn': 'RevenueFromEnrollmentAndRegistrationFeesExcludingHospitalityEnterprises',
    'total_rev_mn': 'Revenues',
    'merch_cost_mn': 'CostOfGoodsSold',
    'sga_mn': 'SellingGeneralAndAdministrativeExpense',
    'preopen_mn': 'PreOpeningCosts',
    'op_income_mn': 'OperatingIncomeLoss',
}

#: cost_cohort.csv 的下界：FY2019 10-K **没有**这张图（实测 "Year Opened" 找不到），
#: FY2020 10-K 起才有。别把下界写成「能翻多早翻多早」，会得到一堆解析失败。
COHORT_FIRST = 2020

#: FY2025 10-K 那张图下面的脚注，逐字。给 build/cost.py 当图注用。
#: 措辞逐年变（FY2020 是 "2012 and 2017 were 53-week fiscal years"、FY2021 起
#: 才加上 "but have been normalized for purposes of comparability"），
#: 所以**只有最新那年的这一条**能当页面图注，别把老年份的脚注混着用。
COHORT_FOOTNOTE = ('*First year sales annualized. 2017 and 2023 were 53-week fiscal years '
                   'but have been normalized for purposes of comparability.')


class CostSecError(RuntimeError):
    """本模块所有失败路径统一抛它，调度器只需 catch 一种（照 fetch/cost.py 的 CostFetchError）。"""


# ═══════════════════════════ HTTP + 缓存 ═══════════════════════════

_LAST_REQ = [0.0]


def _fetch(cache_dir, name, url):
    """下载 `url`，缓存成 `cache/cost_sec/<name>`，返回 bytes。命中缓存不发请求。

    缓存是**内容缓存不是时效缓存**：SEC Archives 下的申报文件一旦公开就再也不会变
    （改了就是新的 accession），所以永不过期是对的。会变的只有 submissions 索引，
    它由 `_submissions` 单独处理。
    """
    d = os.path.join(cache_dir or os.path.join(ROOT, 'cache'), 'cost_sec')
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, name)
    if os.path.exists(p) and os.path.getsize(p) > 0:
        with open(p, 'rb') as f:
            return f.read()
    gap = _MIN_INTERVAL - (time.time() - _LAST_REQ[0])
    if gap > 0:
        time.sleep(gap)
    req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT,
                                               'Accept-Encoding': 'gzip, deflate'})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            body = r.read()
            if r.headers.get('Content-Encoding') == 'gzip':
                import gzip
                body = gzip.decompress(body)
    except Exception as e:
        raise CostSecError(f'SEC 取不到 {url}: {type(e).__name__}: {e}') from e
    _LAST_REQ[0] = time.time()
    with open(p, 'wb') as f:
        f.write(body)
    return body


def _text(raw):
    """HTML → 单空格压平的纯文本。EX-99.2 与 10-K 正文的所有判据都跑在这上面。

    顺序不能换：先剥 script/style（里面可能有像正文的字符串），再剥标签，
    再 unescape（先 unescape 会把 `&lt;td&gt;` 变成真标签，然后被下一步剥掉，
    正文里凡是写了转义尖括号的地方就凭空少一段）。
    """
    t = raw.decode('utf-8', 'replace') if isinstance(raw, bytes) else raw
    t = re.sub(r'(?is)<(script|style)\b.*?</\1>', ' ', t)
    t = re.sub(r'<[^>]+>', ' ', t)
    t = _html.unescape(t)
    return re.sub(r'\s+', ' ', t)


# ═══════════════════════════ 申报清单 ═══════════════════════════

def _submissions(cache_dir):
    """全部申报清单 → [dict(form, filed, report, accession, primary, items)]，按 filed 升序。

    两份 JSON 都要读：`CIK0000909832.json` 只装「recent」（约 1000 条，回溯到 2016 年前后），
    更老的在 `CIK0000909832-submissions-001.json`。只读第一份会让分部序列从 2016 年才开始，
    而**这个错不会报错**，它只是让 CSV 短一截。
    第二份取不到时不抛（EDGAR 对老件的分页文件名不保证），只是序列短一截 ——
    真出这事会被 `build_seg_q` 里「四个季度必须加回财年」那条断言当场抓住，
    因为少一篇 10-Q 就少一个季度。

    **两份都每次重下，一份都不缓存。** recent 每天在动是显然的；-001 也会长 ——
    件从 recent 里滚出去就落进 -001。把 -001 缓存住，几年后那批滚出去的件
    就会**两边都读不到**，序列从中间凭空少掉一截。267KB 的文件不值得冒这个险。
    """
    out = []
    src = [(f'https://data.sec.gov/submissions/CIK{CIK10}.json', 'subs.json', True),
           (f'https://data.sec.gov/submissions/CIK{CIK10}-submissions-001.json',
            'subs-001.json', False)]
    for url, name, required in src:
        p = os.path.join(cache_dir or os.path.join(ROOT, 'cache'), 'cost_sec', name)
        if os.path.exists(p):
            os.remove(p)
        try:
            d = json.loads(_fetch(cache_dir, name, url))
        except CostSecError:
            if required:
                raise
            continue
        r = d['filings']['recent'] if 'filings' in d else d
        items = r.get('items') or [''] * len(r['form'])
        for i in range(len(r['form'])):
            out.append({'form': r['form'][i], 'filed': r['filingDate'][i],
                        'report': r['reportDate'][i], 'accession': r['accessionNumber'][i],
                        'primary': r['primaryDocument'][i], 'items': items[i] or ''})
    out.sort(key=lambda f: (f['filed'], f['accession']))
    return out


def _index_rows(raw):
    """EDGAR 人读版申报索引页 → 逐行 (cells, tr 内层 HTML)。

    `cells[3]` 是 Type 那一格（`EX-99.2` / `EX-101.INS` / `10-Q` …），是**语义**判据；
    文件名那一格是 `cells[2]`。两个调用点都只认 Type，不拼文件名、不猜后缀。
    """
    for tr in re.finditer(r'(?is)<tr[^>]*>(.*?)</tr>', raw):
        body = tr.group(1)
        cells = [re.sub(r'\s+', ' ', _html.unescape(re.sub(r'<[^>]+>', '', c.group(1)))).strip()
                 for c in re.finditer(r'(?is)<t[dh][^>]*>(.*?)</t[dh]>', body)]
        yield cells, body


def _instance(cache_dir, f):
    """一篇申报的 XBRL instance 字节。

    三条路，顺序不能反：
      · 2019-12 起是 inline XBRL，SEC 会额外生成 `<primaryDocument 去掉 .htm>_htm.xml`，
        直接命中；
      · 更早的是独立 instance，文件名没有规律（`cost-20180819.xml` / `d123456d10q.xml`
        都出现过），只能读 `index.json` 挑：`.xml` 结尾、不是 `_cal/_def/_lab/_pre.xml`、
        不是 `FilingSummary.xml`、不是 `*-index.xml`，且开头 4KB 里出现 `xbrl`。
        最后那条是必须的 —— 目录里还躺着 `R*.htm` 的兄弟 xml 和图形附件。
      · **`index.json` 漏列时**改读人读版索引 `<accession>-index.htm`。

    ══ 第三条路是干什么的（2026-09-05 加）══
    `index.json` 会漏列，而且此刻就在漏 —— 这不是新发现，本仓一个月前就为另一个发行人
    写下过同一条结论：见 `fetch/rates_lpla.py:206-214`（四份 LPLA 的 8-K，
    「文档在，只是 index.json 这条索引看不见它」），那里给的处方就是
    「改从 `<acc>-index.html` 取文件名」（rates_lpla.py:284）。

    实测 0000909832-17-000022（10-Q@2017-12-21，FY18Q1）：
      · `index.json` → HTTP 200，**583 字节，只有 4 项**，全是包装文件
        （`-index-headers.html` / `-index.html` / `.txt` / `-xbrl.zip`），一个 `.xml` 都没有；
      · 同一个目录的 HTML 清单 → **73 个文件**，`cost-20171126.xml` 好端端挂着；
      · 直接 GET 那个文件 → HTTP 200，863,287 字节，开头就是
        `<?xml …?><!--XBRL Document Created with Wdesk from Workiva-->`。
    也就是说**申报是完整的，坏的是那份 JSON 清单**。上面第二条路那圈循环因此一个候选都
    遍历不到，直接掉进最后那句 raise，把整个 cost_sec 步打成 FAIL
    （[seg] 挂 → [tkt] 连带「表 1（分部收入）没解」，五张表里两张写不成）。

    在册的 62 篇 10-K/10-Q 里只有这一篇是这样，所以这是「一篇的索引坏了」，
    不是「2017 那一代版式不支持」—— 别拿它去加什么按年份的跳过表。

    人读版索引那一行的 Type 格恰好是 `EX-101.INS`（实测该行 cells =
    ['5', 'XBRL INSTANCE DOCUMENT', 'cost-20171126.xml', 'EX-101.INS', '863287']），
    linkbase 各自是 `EX-101.CAL/DEF/LAB/PRE`、schema 是 `EX-101.SCH`，
    所以这条路认 Type 就够了，不需要第二条路那套后缀排除 —— 与本模块
    `_ex992_url()` 认 `EX-99.2` 是同一个成语。

    第四条路（`<accession>-xbrl.zip`）是兜底：它和人读版索引是**两条独立的索引**，
    JSON 与 HTML 同时坏的日子它还在。zip 里只有 instance + xsd + 四条 linkbase，
    所以沿用第二条路那组后缀排除；⚠ 遍历顺序按 zip 成员名排序，与 `index.json`
    那圈的目录顺序**不同**（判据相同，顺序不同）。
    """
    acc = f['accession'].replace('-', '')
    base = f'{ARCHIVE}/{acc}/'
    tried = []
    try:
        return _fetch(cache_dir, f'inst-{acc}.xml', base + f['primary'][:-4] + '_htm.xml')
    except CostSecError:
        pass

    def _probe(b, url):
        """开头 4KB 有 `xbrl` 才算数；不算数就把缓存删掉，免得下轮当好文件读。"""
        if b'xbrl' in b[:4000]:
            return True
        os.remove(os.path.join(cache_dir or os.path.join(ROOT, 'cache'),
                               'cost_sec', f'inst-{acc}.xml'))
        tried.append(f'{url} 开头 4KB 里没有 xbrl')
        return False

    idx = json.loads(_fetch(cache_dir, f'idx-{acc}.json', base + 'index.json'))
    listed = [it['name'] for it in idx['directory']['item']]
    for n in listed:
        if not n.endswith('.xml') or n == 'FilingSummary.xml':
            continue
        if n.endswith(('_cal.xml', '_def.xml', '_lab.xml', '_pre.xml', '-index.xml')):
            continue
        b = _fetch(cache_dir, f'inst-{acc}.xml', base + n)
        if _probe(b, base + n):
            return b

    # ── 第三条路：index.json 漏列 → 人读版索引 ────────────────────────────────
    tried.append('index.json 只列了 %d 项（%s）'
                 % (len(listed), '、'.join(listed[:4]) or '空'))
    try:
        raw = _fetch(cache_dir, f'idxhtm-{acc}.htm',
                     f'{base}{f["accession"]}-index.htm').decode('utf-8', 'replace')
    except CostSecError as e:
        raw = None
        tried.append(str(e))          # 取不到 ≠ 没有，原因必须带到最后那句里
    if raw:
        for cells, body in _index_rows(raw):
            if len(cells) >= 4 and cells[3] == 'EX-101.INS':
                href = re.search(r'href="([^"]+)"', body)
                if not href:
                    continue
                b = _fetch(cache_dir, f'inst-{acc}.xml', 'https://www.sec.gov' + href.group(1))
                if _probe(b, href.group(1)):
                    return b
        tried.append(f'{f["accession"]}-index.htm 里没有 Type 为 EX-101.INS 的行')

    # ── 第四条路：<accession>-xbrl.zip ───────────────────────────────────────
    try:
        z = _fetch(cache_dir, f'xbrlzip-{acc}.zip', base + f'{f["accession"]}-xbrl.zip')
    except CostSecError as e:
        z = None
        tried.append(str(e))
    if z:
        try:
            with zipfile.ZipFile(io.BytesIO(z)) as zf:
                for n in sorted(zf.namelist()):
                    bn = os.path.basename(n)
                    if not bn.endswith('.xml') or bn == 'FilingSummary.xml':
                        continue
                    if bn.endswith(('_cal.xml', '_def.xml', '_lab.xml',
                                    '_pre.xml', '-index.xml')):
                        continue
                    b = zf.read(n)
                    if b'xbrl' in b[:4000]:
                        return b
            tried.append('-xbrl.zip 里没有像 instance 的成员')
        except zipfile.BadZipFile:
            tried.append('-xbrl.zip 打不开（不是合法 zip）')

    # 四条路都没拿到 —— 把**每条路各自为什么没拿到**写进报错。
    # 不写的话，「SEC 限速取不到」与「这篇真的没有 instance」会长得一模一样，
    # 那正是 README「第四类：不出声的失败」要拦的形状。
    raise CostSecError('%s@%s %s 找不到 XBRL instance：%s'
                       % (f['form'], f['filed'], f['accession'], '；'.join(tried)))


def _facts(raw):
    """instance → [(local_name, start, end, instant, dims, value_text)]。

    `dims` 是 {轴短名: 成员限定名}，只取 `<entity><segment>` 里的 explicitMember。
    只遍历根的**直接子元素**：instance 里事实就在这一层，`root.iter()` 会把 context
    里的元素也扫进来。
    """
    root = ET.fromstring(raw)
    ctx = {}
    for c in root.iter(XBRLI + 'context'):
        per = c.find(XBRLI + 'period')
        if per is None:
            continue
        sd, ed, ins = (per.find(XBRLI + 'startDate'), per.find(XBRLI + 'endDate'),
                       per.find(XBRLI + 'instant'))
        dims = {}
        ent = c.find(XBRLI + 'entity')
        seg = ent.find(XBRLI + 'segment') if ent is not None else None
        if seg is not None:
            for m in seg.iter(XBRLDI + 'explicitMember'):
                dims[(m.get('dimension') or '').split(':')[-1]] = (m.text or '').strip()
        ctx[c.get('id')] = (sd.text if sd is not None else None,
                            ed.text if ed is not None else None,
                            ins.text if ins is not None else None, dims)
    out = []
    for el in root:
        if not el.tag.startswith('{'):
            continue
        cr = el.get('contextRef')
        if cr not in ctx or el.text is None:
            continue
        s, e, i, dims = ctx[cr]
        out.append((el.tag[1:].split('}')[1], s, e, i, dims, el.text.strip()))
    return out


def _num(txt):
    """XBRL 事实文本 → int。取不到就 None（不猜、不填 0）。"""
    try:
        return int(round(float(txt.replace(',', ''))))
    except (TypeError, ValueError):
        return None


def _mn(v, what):
    """美元整数 → 百万美元整数。**不能整除就抛**。

    Costco 在申报里就是按百万列示的，XBRL 里的值全是 10^6 的整数倍，所以
    「除不尽」只可能意味着拿错了标签（比如某个按元披露的口径），
    而 `//` 会把它悄悄截断成一个看上去很正常的数。
    """
    if v % 10 ** 6:
        raise CostSecError(f'{what} 的值 {v} 不是 100 万的整数倍 —— 多半拿错了标签')
    return v // 10 ** 6


def _weeks(start, end):
    """会计期跨几周。Costco 是 4-4-5 零售日历，季度长度只可能是 12 / 16 / 17 / 24 / 36 / 52 / 53。"""
    d0, d1 = datetime.date.fromisoformat(start), datetime.date.fromisoformat(end)
    return round(((d1 - d0).days + 1) / 7)


# ═══════════════════ 表 1：分部收入 series/cost_seg_q.csv ═══════════════════
#
# 单位：百万美元（XBRL 原值是美元整数，除 10^6；Costco 自己在申报里就是按百万列示的，
# 除下来是整数，不存在精度损失）。
#
# 列：fq, period_start, period_end, weeks, scope, us_mn, ca_mn, oi_mn, total_mn,
#     derived, accession
#   fq        财季标签 "FY26Q3" / 财年标签 "FY25"。**刻意不是 Mon-YY**：Costco 的 4-4-5
#             日历里一个季度横跨三个自然月，写成 Mon-YY 会让读者以为那是某个月的数。
#   scope     Q = 季度，FY = 财年
#   derived   1 = 这一行是**推导**的（FY 减同起点的 36 周 YTD），0 = 申报里直接读到的。
#             Costco 的 10-K **不单列 Q4**，所以 Q4 只能这么来 —— 页面必须给这些点加脚注，
#             这是 build/CONTRACT.md §5 第 1 条（推导值必须标 Implied）。
#   accession 值第一次出现在哪篇申报里（最早申报者）。选「最早」而不是「最新」是为了
#             这一列**永不变动**：新申报重复披露老季度时不该让整表的字节动起来。

SEG_AXES = ('StatementBusinessSegmentsAxis', 'StatementGeographicalAxis')

#: 三代成员名 → 三个地区。见口径坑 4。
SEG_MEMBER = {
    'cost:UnitedStatesMember': 'us', 'country:US': 'us',
    'cost:UnitedStatesOperationsMember': 'us',
    'cost:CanadaMember': 'ca', 'country:CA': 'ca',
    'cost:CanadianOperationsMember': 'ca',
    'cost:OtherInternationalMember': 'oi',
    'cost:OtherInternationalOperationsMember': 'oi',
}

#: 同一条「分部总收入」Costco 换过三个元素名，一律接受。
SEG_REV_TAGS = ('RevenueFromContractWithCustomerExcludingAssessedTax', 'Revenues',
                'SalesRevenueNet')

#: 允许与分部轴**同时出现**的唯一一根轴。别放宽这一条 —— 见 `_seg_region` 的注释。
SEG_ALLOWED_EXTRA_AXES = ('ConsolidationItemsAxis',)


def _seg_region(local, dims):
    """这条事实属于哪个地区；不是分部收入就返回 None。

    ⚠️ **第三根轴一票否决**，这是本表最要命的一条。同一篇 10-K 里
    `RevenueFromContractWithCustomerExcludingAssessedTax` 还带着
    `ProductOrServiceAxis`（食品杂货 / 生鲜 / 非食品…）与更细的国别拆分；
    它们**同样挂着分部轴**，不排除就会把「美国 × 生鲜」当成「美国」写进去，
    于是同一个 (start, end, 'us') 被写好几遍、彼此覆盖，最后留下的是哪一条取决于
    XML 里的先后顺序 —— 一个既不报错也不稳定的错。
    只放行 `ConsolidationItemsAxis`（它的成员是 `OperatingSegmentsMember`，
    说的还是同一个分部，不是再切一刀）。
    """
    if local not in SEG_REV_TAGS:
        return None
    region, extra = None, False
    for ax, mem in dims.items():
        if ax in SEG_AXES:
            region = SEG_MEMBER.get(mem)
        elif ax not in SEG_ALLOWED_EXTRA_AXES:
            extra = True
    return None if extra else region


def _collect_segments(cache_dir, filings):
    """扫全部 10-K/10-Q → {(start, end): {'us':…, 'ca':…, 'oi':…, '_acc':…}}（单位：美元）。

    重述护栏：同一个 (start, end, region) 在两篇申报里给出不同的值 → 直接抛。
    见口径坑 5 —— 2011 年以来 62 篇申报一次没响过，正因如此它才有资格当哨兵。
    """
    per = defaultdict(dict)
    first_seen = {}
    for f in filings:
        if f['form'] not in ('10-K', '10-Q') or f['filed'] < XBRL_FROM:
            continue
        raw = _instance(cache_dir, f)
        for local, s, e, _i, dims, txt in _facts(raw):
            if not s or not e:
                continue
            reg = _seg_region(local, dims)
            if not reg:
                continue
            v = _num(txt)
            if v is None:
                continue
            key = (s, e)
            if reg in per[key] and per[key][reg] != v:
                raise CostSecError(
                    f'分部收入重述/冲突：{key} {reg} 先前 {per[key][reg]}，'
                    f'{f["form"]}@{f["filed"]} ({f["accession"]}) 给的是 {v}。'
                    f'这道护栏 2011 年以来一次没响过，响了就必须人来看，不许覆盖。')
            if reg not in per[key]:
                per[key][reg] = v
                first_seen[(key, reg)] = (f['filed'], f['accession'])
    for key in per:
        # 按**申报日**取最早，不是按 accession 字符串排序：申报代理换过
        # （0001193125 / 0001445305 / 0000909832 三个前缀都出现过），
        # 字典序在跨代理时根本不是时间序。
        per[key]['_acc'] = min(first_seen[(key, r)] for r in list(per[key]))[1]
    return per


def _fy_label(year):
    return f'FY{year % 100:02d}'


def _assign_fq(quarters, years):
    """给每个季度贴 "FY26Q3" 这样的标签。

    **不能按自然月推**：FY2023 结束在 2023-09-03（53 周年），按「9 月起算下一财年」
    会把整个 FY2023 的 Q4 推到 FY2024 去。所以只认财年区间本身。
    还在进行中的财年（本表里就是 FY2026）没有 52/53 周的行，用「最后一个已知财年 + 1」
    往前推一格 —— 这一格必然存在，否则说明 10-K 断更了，那是该被上层发现的事。
    """
    fy = sorted(years, key=lambda k: k[1])
    last_end = fy[-1][1] if fy else None
    last_year = int(fy[-1][1][:4]) if fy else None
    out = {}
    for key in quarters:
        s, e = key
        y = None
        for (fs, fe) in fy:
            if fs <= s and e <= fe:
                y = int(fe[:4])
                break
        if y is None:
            if last_end is None or s <= last_end:
                raise CostSecError(f'季度 {key} 落不进任何财年区间，也不在最后一个财年之后')
            y = last_year + 1
        out[key] = y
    idx = defaultdict(list)
    for key, y in out.items():
        idx[y].append(key)
    lab = {}
    for y, keys in idx.items():
        for n, key in enumerate(sorted(keys), 1):
            if n > 4:
                raise CostSecError(f'FY{y} 数出了 {len(keys)} 个季度：{sorted(keys)}')
            lab[key] = f'{_fy_label(y)}Q{n}'
    return lab, out


def build_seg_q(cache_dir, filings):
    """→ (header, rows)。见本节顶部的列说明。"""
    per = _collect_segments(cache_dir, filings)
    full = {k: v for k, v in per.items() if len(set(v) - {'_acc'}) == 3}
    years = {k: v for k, v in full.items() if _weeks(*k) in (52, 53)}
    ytd36 = {k: v for k, v in full.items() if _weeks(*k) == 36}
    quarters = {k: dict(v, _derived=0) for k, v in full.items() if _weeks(*k) == 12}

    # Q4 只能推：FY(52/53 周) 减掉**同起点**的 36 周 YTD。同起点是关键 ——
    # 拿别的年份的 YTD 去减会得到一个完全合理、完全错误的数。
    for (fs, fe), fv in years.items():
        y36 = next((v for (s, e), v in ytd36.items() if s == fs), None)
        if y36 is None:
            continue
        y36_end = next(e for (s, e), v in ytd36.items() if s == fs)
        q4s = (datetime.date.fromisoformat(y36_end) + datetime.timedelta(days=1)).isoformat()
        quarters[(q4s, fe)] = {r: fv[r] - y36[r] for r in ('us', 'ca', 'oi')}
        quarters[(q4s, fe)]['_acc'] = fv['_acc']
        quarters[(q4s, fe)]['_derived'] = 1

    # 口径坑 2 那条线在**对账之前**就要切掉：FY2009 / FY2010 只以「上年同期」的身份
    # 出现在 FY2011 10-K 里，它们有财年行、却一个季度行都没有（10-Q 不会印两年前的季度）。
    # 放到写表时再滤，下面那条「四个季度必须加回财年」就会拿一个空手的年份去对账、直接抛。
    years = {k: v for k, v in years.items() if k[0] >= FY2011_START}
    quarters = {k: v for k, v in quarters.items() if k[0] >= FY2011_START}

    lab, fy_of = _assign_fq(quarters, years)

    # 四个季度必须加回财年。这条断言同时盯住两件事：Q1+Q2+Q3 是不是真的等于 36 周 YTD，
    # 以及有没有哪个季度被第三根轴的污染值覆盖过。
    for (fs, fe), fv in years.items():
        y = int(fe[:4])
        qs = [k for k, v in quarters.items() if fy_of[k] == y]
        if len(qs) != 4:
            raise CostSecError(f'FY{y} 只凑出 {len(qs)} 个季度，无法与财年对账：{sorted(qs)}')
        for r in ('us', 'ca', 'oi'):
            got = sum(quarters[k][r] for k in qs)
            if got != fv[r]:
                raise CostSecError(
                    f'FY{y} 的 {r} 四个季度合计 {got} ≠ 财年 {fv[r]}（差 {got - fv[r]}）。'
                    f'季度或财年至少有一个是错的，拒绝写表。')

    head = ['fq', 'period_start', 'period_end', 'weeks', 'scope',
            'us_mn', 'ca_mn', 'oi_mn', 'total_mn', 'derived', 'accession']
    rows = []
    for (s, e), v in sorted(quarters.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        us, ca, oi = (_mn(v[r], f'{lab[(s, e)]} {r}') for r in ('us', 'ca', 'oi'))
        rows.append([lab[(s, e)], s, e, _weeks(s, e), 'Q', us, ca, oi, us + ca + oi,
                     v['_derived'], v['_acc']])
    for (s, e), v in sorted(years.items(), key=lambda kv: kv[0][1]):
        us, ca, oi = (_mn(v[r], f'FY{e[:4]} {r}') for r in ('us', 'ca', 'oi'))
        rows.append([_fy_label(int(e[:4])), s, e, _weeks(s, e), 'FY', us, ca, oi,
                     us + ca + oi, 0, v['_acc']])
    if not rows:
        raise CostSecError('分部收入一行都没解出来 —— 轴名或成员名多半又换了，见口径坑 4')
    return head, rows, years, lab, fy_of


# ═══════════════ 表 2：客单 / 客流 series/cost_tkt_q.csv ═══════════════
#
# 单位：百分比，一位小数（原文就是 "+9.4%"，不做任何换算）。
# 列：fq, filed, accession, basis, us_sales…tc_traffic, mdna_tc_tkt, mdna_tc_frq
#   basis        reported = 报告口径；adjusted = 除油价与汇率口径。
#                **FY24Q3 / FY24Q4 / FY25Q1 只有 reported** —— 那三期的 EX-99.2 里
#                根本没有 "Adjusted Comp Sales" 这张表。缺就是缺，绝不合成。
#   mdna_tc_*    交叉核对用：10-Q MD&A 里那句话自己写的**全公司**客单与购物频次
#                （整数百分比）。它与 deck 的 tc_tkt / tc_trf 是两条独立的腿。

#: 8-K 补充资料这张表的三行标签，后面永远跟着 4 个百分数（US / Canada / OI / Total）。
_DECK_ROW = re.compile(r'(Sales|Ticket|Traffic)\s*((?:[+-]?\d+\.\d%\s*){4})')

#: 分割「报告口径」与「除油汇口径」两张表的字面量。缺它 = 这期只有报告口径。
_DECK_ADJ_MARK = 'Adjusted Comp Sales'

#: 封面上的财季。两种写法都见过："3rd Quarter FY 2024" 与 "Third Quarter FY 2026"。
_DECK_FQ = re.compile(
    r'\b(1st|2nd|3rd|4th|First|Second|Third|Fourth)\s+Quarter\s+FY\s*[’\'`]?\s*(\d{2,4})',
    re.I)
_ORD = {'1st': 1, 'first': 1, '2nd': 2, 'second': 2, '3rd': 3, 'third': 3,
        '4th': 4, 'fourth': 4}

#: ticket × traffic 与印出来的 Sales 之间允许的最大偏差（百分点）。
#: 实测口径见 `_deck_guard` 的 docstring：9 份 deck / 15 张表 / 60 个格子，最大 0.101pp。
#: 0.15 是贴着实测给的余量（约 1.5 倍），够挡住「串一格」（那种偏差是几个 pp 的量级）。
_DECK_TOL = 0.15


def _deck_fq(text, accession):
    """封面 → "FY26Q3"。认不出来直接抛：认不出财季的 deck 写进表里就是一行没有主键的数。"""
    m = _DECK_FQ.search(text)
    if not m:
        raise CostSecError(
            f'{accession} 的 EX-99.2 封面上认不出财季（找的是 "3rd Quarter FY 2024" / '
            f'"Third Quarter FY 2026" 这两种写法）。开头 200 字：{text[:200]!r}')
    q = _ORD[m.group(1).lower()]
    y = int(m.group(2))
    if y < 100:
        y += 2000
    return f'{_fy_label(y)}Q{q}'


def _deck_table(chunk):
    """半张 deck 文本 → {'Sales': [4 个数], 'Ticket': [...], 'Traffic': [...]}。

    每个标签**只取第一次出现**：后面几页还有别的表也叫 Sales。
    """
    out = {}
    for m in _DECK_ROW.finditer(chunk):
        if m.group(1) in out:
            continue
        out[m.group(1)] = [float(x.rstrip('%')) for x in m.group(2).split()]
    return out


def _deck_guard(fq, basis, tbl):
    """强制护栏：(1+ticket)(1+traffic)-1 必须约等于印出来的 Sales，四列都要过。

    这不是「顺手加个校验」，它是**列错位的唯一探测手段**。deck 的表在压平后就是
    12 个裸数字，列一旦左右串一格，数字全都还在、量级也全都合理，
    CSV 里看不出任何异常 —— 与 fetch/cost_release.py 坑 6、坑 9 同一类静默失败。
    所以必须 raise 而不是 warn：warn 之后状态仍是成功，等于没有护栏。

    实测规模（2026-09 逐份重算，别照抄「9×4×2」那种算法 —— **不是每份 deck 都有调整表**）：
      · deck 9 份，其中带 "Adjusted Comp Sales" 的只有 6 份 → 表 9 + 6 = **15 张**；
      · 每张表 4 列（US / Canada / Other International / Total Company）→ **60 个格子**；
      · 60 个格子的 |推算 − 印出来的 Sales|：最大 **0.101pp**（FY26Q3 调整表第 4 列），
        次大 0.090 / 0.087 / 0.079，均值 0.036、中位数 0.032。
    偏差本身是**发布方四舍五入**造成的：ticket 与 traffic 各按 0.1pp 印，
    (1+t)(1+f)−1 的误差量级就在 0.1pp 上，所以 0.101 已经接近这套印法的天花板，
    再宽也没有意义，再窄（比如 0.10）会当场被 FY26Q3 那一格顶掉。
    """
    miss = [k for k in ('Sales', 'Ticket', 'Traffic') if k not in tbl]
    if miss:
        raise CostSecError(f'{fq} {basis} 的 deck 表缺行 {miss}（应有 Sales/Ticket/Traffic 各一行）')
    for i in range(4):
        imp = ((1 + tbl['Ticket'][i] / 100) * (1 + tbl['Traffic'][i] / 100) - 1) * 100
        if abs(imp - tbl['Sales'][i]) > _DECK_TOL:
            raise CostSecError(
                f'{fq} {basis} 第 {i + 1} 列：ticket {tbl["Ticket"][i]}% × traffic '
                f'{tbl["Traffic"][i]}% 推出 {imp:.2f}%，印的 Sales 是 {tbl["Sales"][i]}%，'
                f'差 {abs(imp - tbl["Sales"][i]):.2f}pp > {_DECK_TOL}pp。'
                f'实测 52 个格子最大只差 0.1pp，这么大的偏差只可能是版式改了、列串位了。')


def _deck_parse(text, accession):
    """一份 EX-99.2 → (fq, {'reported': tbl, 'adjusted': tbl or 缺席})。

    ⚠️ **不要解析第 1 页那排大字**。压平后的阅读顺序是「值在标签**后面**」：
    "…+11.6% Comparable Sales +9.8% Adjusted Comparable Sales1 +6.6% Comparable Traffic…"
    实际配对是 Comparable Sales=+9.8%、Adjusted=+6.6%、Comparable Traffic=+2.4%，
    而开头那个 +11.6% 属于最后面的 "Net Sales Growth"。
    朴素地「数字后面跟着的就是它的标签」会得到 Comparable Sales=+11.6%
    —— 那其实是净销售额增速，而它看上去完全像个合理的 comp。
    第 3 页那张分部表没有这个问题（标签在左、四个值在右），所以只解那一张。
    """
    fq = _deck_fq(text, accession)
    parts = text.split(_DECK_ADJ_MARK)
    out = {'reported': _deck_table(parts[0])}
    _deck_guard(fq, 'reported', out['reported'])
    if len(parts) > 1:
        out['adjusted'] = _deck_table(parts[1])
        _deck_guard(fq, 'adjusted', out['adjusted'])
        # 白送的第二道：除油汇只动价（ticket），不动人次（traffic），
        # 所以两张表的 Traffic 行必须逐字相同。不同 = 两张表被切错了。
        if out['reported']['Traffic'] != out['adjusted']['Traffic']:
            raise CostSecError(
                f'{fq}：报告口径 traffic {out["reported"]["Traffic"]} 与除油汇口径 '
                f'{out["adjusted"]["Traffic"]} 不同。除油汇调的是价不是人次，'
                f'两者必须相同 —— 不同说明 "{_DECK_ADJ_MARK}" 这一刀切错了位置。')
    return fq, out


def _ex992_url(cache_dir, accession):
    """8-K 的 EX-99.2 附件 URL。

    **不要拼文件名。** 九期里八期叫 `costex9928-k*.htm`，
    accession 0000909832-24-000075 那期偏偏叫 `costexhibit9928-k121224.htm`。
    只认申报索引页上 Type 那一格**恰好**是 "EX-99.2" 的那一行。
    """
    acc = accession.replace('-', '')
    raw = _fetch(cache_dir, f'idx8k-{acc}.htm',
                 f'{ARCHIVE}/{acc}/{accession}-index.htm').decode('utf-8', 'replace')
    for cells, body in _index_rows(raw):
        if len(cells) >= 4 and cells[3] == 'EX-99.2':
            href = re.search(r'href="([^"]+)"', body)
            if href:
                return 'https://www.sec.gov' + href.group(1)
    return None


#: deck 的申报日距它所报季度末的合理区间（天）。实测 9 份全在 18-25 天。
#: 60 天的上限是给「哪年推迟发布」留的余量，同时仍能挡住「串到上一季」（约 84 天）。
_DECK_LAG = (0, 60)


def build_tkt_q(cache_dir, filings, mdna, q_end=None):
    """→ (header, rows)。逐份 8-K(Item 2.02) 取 EX-99.2。

    只认 items 里带 "2.02" 的 8-K：Costco 的另一批 8-K 是 Item 8.01（月度销售、股息），
    那些件里没有补充资料 deck，逐个去开索引页只是白白多打几十个请求。

    `q_end` 是 {财季标签: 季末日}（来自分部表），用来给封面解出来的财季**对第二只眼**：
    申报日必须落在季末之后 0-60 天内。封面认错一季在 CSV 里看不出任何异常
    —— 一整季的客单客流被贴到隔壁季上，数还是那些数。
    注意它**只在那一季的分部行已经存在时**才管用：8-K 早于 10-Q 约一周，
    最新那一季（以及每年的 Q4）刚发时分部行还没有，那时这只眼闭着，不许因此报错。
    """
    head = ['fq', 'filed', 'accession', 'basis',
            'us_sales', 'ca_sales', 'oi_sales', 'tc_sales',
            'us_tkt', 'ca_tkt', 'oi_tkt', 'tc_tkt',
            'us_trf', 'ca_trf', 'oi_trf', 'tc_trf',
            'mdna_tc_tkt', 'mdna_tc_frq']
    rows = []
    for f in filings:
        if f['form'] != '8-K' or '2.02' not in f['items']:
            continue
        url = _ex992_url(cache_dir, f['accession'])
        if not url:
            continue                       # 早年的业绩 8-K 只有 EX-99.1，没有 deck
        acc = f['accession'].replace('-', '')
        text = _text(_fetch(cache_dir, f'ex992-{acc}.htm', url))
        fq, tables = _deck_parse(text, f['accession'])
        end = (q_end or {}).get(fq)
        if end:
            lag = (datetime.date.fromisoformat(f['filed'])
                   - datetime.date.fromisoformat(end)).days
            if not _DECK_LAG[0] <= lag <= _DECK_LAG[1]:
                raise CostSecError(
                    f'{f["accession"]} 的 EX-99.2 封面说是 {fq}，但那一季在 {end} 就结束了，'
                    f'而这份 8-K 申报于 {f["filed"]}（隔 {lag} 天，合理区间 {_DECK_LAG}）。'
                    f'封面认错一季不会在 CSV 里留下任何痕迹，拒绝写入。')
        for basis in ('reported', 'adjusted'):
            t = tables.get(basis)
            if not t:
                continue                   # FY24Q3 / FY24Q4 / FY25Q1：源里就没有，不合成
            row = [fq, f['filed'], f['accession'], basis]
            for lab in ('Sales', 'Ticket', 'Traffic'):
                row += [f'{v:.1f}' for v in t[lab]]
            m = mdna.get(fq) if basis == 'reported' else None
            row += ['' if not m or m[0] is None else f'{m[0]:g}',
                    '' if not m or m[1] is None else f'{m[1]:g}']
            rows.append(row)
    if not rows:
        raise CostSecError('一份 EX-99.2 都没解出来 —— 8-K 的附件类型或版式多半变了')
    rows.sort(key=lambda r: (r[0], r[3]))
    _tkt_vs_mdna(rows)
    return head, rows


def _tkt_vs_mdna(rows):
    """deck 与 10-Q MD&A 两条腿对账：差 >1pp 就大声 warn（不抛）。

    为什么是 warn 不是 raise：MD&A 那句话是**整数百分比**（"approximately 7%"），
    deck 是一位小数（7.3%），两者本来就只能对到 ±0.5pp 的量级；再加上 MD&A 偶尔
    只说「略高于」而不给数。这条腿的价值在**版式漂移预警**，不在精度，
    所以它不该有权阻断一次成功的摄入。
    真正会咬人的那一类（列串位）由 `_deck_guard` 抛异常挡住，两道分工不重叠。
    """
    for r in rows:
        if r[3] != 'reported':
            continue
        for col, mv, name in ((11, r[16], 'ticket'), (15, r[17], 'traffic/frequency')):
            if mv == '':
                continue
            if abs(float(r[col]) - float(mv)) > 1.0:
                print(f'WARN: {r[0]} 的 {name} 两条腿对不上 —— 8-K deck {r[col]}%，'
                      f'10-Q MD&A {mv}%，差 {abs(float(r[col]) - float(mv)):.1f}pp > 1pp。'
                      f'数据照写，但请核一眼 deck 的版式与 MD&A 那句话的措辞。', file=sys.stderr)


# ════════════ MD&A 里那句「客单 / 购物频次」════════════
#
# 这条腿比 deck **更耐久**：Costco 在 CORRESP 0000909832-25-000025 里向 SEC 承诺
# 会继续量化这两个驱动。但它太短（2025-06-05 的 10-Q 起才有），替代不了 deck，
# 所以只当交叉核对。

#: 样板句（每篇 10-Q/10-K 都有），必须先排除，否则永远匹配到它、永远解不出数。
_MDNA_BOILER = 'is achieved through increasing shopping frequency'
_MDNA_PHRASE = {'average ticket': 'tkt', 'shopping frequency': 'frq'}
#: "less than 1%" / "slightly higher" 这类**没有量化**的写法：识别出来、丢掉、不猜。
_MDNA_VAGUE = re.compile(r'(less than|more than|slightly|approximately less)\s*$', re.I)
_MDNA_PCT = re.compile(r'(\d+(?:\.\d+)?)\s*%')
_MDNA_SENT = re.compile(r'(?<=[a-z0-9%)])\.\s+(?=[A-Z])')
#: 「数在前、短语在后」时中间只允许这几个词（"5% in shopping frequency"）。
_MDNA_BEFORE = re.compile(r'\s*(and\s+)?in\s+(approximately\s+)?', re.I)
#: 「短语在前、数在后」时中间只允许这几个词（"shopping frequency of 5%"）。
_MDNA_AFTER = re.compile(r'\s*(increase\s+)?of\s+(approximately\s+)?', re.I)


def _mdna_sentence(text):
    """从压平正文里挑出**量化**的那一句（没有就 None）。

    切句子用 `(?<=[a-z0-9%)])\\.\\s+(?=[A-Z])`：这条 lookbehind 天然放过 "U.S." 和
    "Inc."（点号前是大写字母），而正常句末（"…of 2026. The remaining"）照切。
    """
    for sent in _MDNA_SENT.split(text):
        if 'shopping frequency' not in sent or _MDNA_BOILER in sent:
            continue
        if 'average ticket' not in sent or not _MDNA_PCT.search(sent):
            continue
        return sent.strip()
    return None


def _mdna_numbers(sent):
    """一句 MD&A → (ticket%, frequency%)，解不出的那一个给 None。

    实测这句话在 5 篇申报里有 5 种形状，所以不用模板、用**连接词**：
      先把句子切成「百分数连串」与「两个关键短语」两种记号，
      再看短语与相邻那一串之间**夹着哪个介词**来决定归属：
        "5% in shopping frequency"          → 串在前，介词 "in"          → 认领前面那串
        "shopping frequency of 5%"          → 串在后，介词 "of"/"increase of" → 认领后面那串
        "3% in shopping frequency and average ticket" → 两个短语之间只有 "and" → 共用
      三条都不成立就**留空**。
    为什么非要看介词而不是「取最近的数」：FY25Q3 那句开头是
    "Comparable sales increased 6% in the third quarter and first thirty-six weeks of 2025
     and were positively impacted by increased shopping frequency of 5%…"
    —— 离 "shopping frequency" 最近的**前面**那个数是 6%（那是 comp sales 本身），
    真正属于它的是后面的 5%。取最近的数会把 comp 抄成客流，而 6 与 5 都完全合理。
    连串取第一个数，是因为 10-Q 常把「本季 / 前 36 周」两个数并排写
    （"increases of approximately 7% and 5% in average ticket"），本表要的是本季。
    """
    toks = []
    for m in re.finditer(r'(\d+(?:\.\d+)?)\s*%|average ticket|shopping frequency', sent):
        if m.group(1) is not None:
            kind = 'vague' if _MDNA_VAGUE.search(sent[max(0, m.start() - 24):m.start()]) else 'pct'
            toks.append((kind, float(m.group(1)), m.start(), m.end()))
        else:
            toks.append(('ph', _MDNA_PHRASE[m.group(0)], m.start(), m.end()))
    groups, cur = [], []
    for t in toks:                                  # 把连续的百分数并成一串
        if t[0] == 'pct':
            cur.append(t)
        else:
            if cur:
                groups.append(cur)
                cur = []
            if t[0] == 'ph':
                groups.append(t)
            # 'vague'（"less than 1%"）只起「切断连串」的作用，本身不进 groups：
            # 没有量化的数一旦进来，下一个短语就会认领它，等于把「小于 1%」当成 1%。
    if cur:
        groups.append(cur)

    out, claimed = {}, set()
    for i, g in enumerate(groups):
        if not isinstance(g, tuple) or g[0] != 'ph':
            continue
        prev = groups[i - 1] if i else None
        nxt = groups[i + 1] if i + 1 < len(groups) else None
        if (isinstance(prev, list) and id(prev) not in claimed
                and _MDNA_BEFORE.fullmatch(sent[prev[-1][3]:g[2]])):
            out[g[1]] = prev[0][1]
            claimed.add(id(prev))
        elif (isinstance(nxt, list) and id(nxt) not in claimed
              and _MDNA_AFTER.fullmatch(sent[g[3]:nxt[0][2]])):
            out[g[1]] = nxt[0][1]
            claimed.add(id(nxt))
        elif (isinstance(prev, tuple) and prev[0] == 'ph'
              and sent[prev[3]:g[2]].strip().lower() == 'and' and prev[1] in out):
            out[g[1]] = out[prev[1]]                # "…% in A and B"：共用同一个数
    return out.get('tkt'), out.get('frq')


def collect_mdna(cache_dir, filings, lab_by_end):
    """{fq: (ticket%, frequency%)} —— 只从 **10-Q** 取。

    10-K 里那句话说的是**整个财年**（"increases of 5% in shopping frequency and
    approximately 1% in average ticket" 讲的是 FY2025 全年），把它挂到 Q4 上
    就是把年度数当季度数用 —— 这正是本仓最不能犯的那类口径错。
    财年那一对数走 `series/cost_fy.csv` 的 `mdna_tkt_pct` / `mdna_frq_pct` 两列。

    只扫 deck 时代（2024-05 起）的 10-Q：更早的申报里这句话不带数
    （2025-03-13 那期写的是 "increased shopping frequency and a slightly higher
    average ticket"，一个数都没有），下载它们只是白花请求。
    """
    out = {}
    for f in filings:
        if f['form'] != '10-Q' or f['filed'] < '2024-05-01':
            continue
        fq = lab_by_end.get(f['report'])
        if not fq:
            continue                        # 该季的分部行还没出来（8-K 早于 10-Q，见节奏）
        acc = f['accession'].replace('-', '')
        text = _text(_fetch(cache_dir, f'doc-{acc}-{f["primary"]}',
                            f'{ARCHIVE}/{acc}/{f["primary"]}'))
        sent = _mdna_sentence(text)
        if not sent:
            continue
        out[fq] = _mdna_numbers(sent)
    return out


# ═══════════ 表 3：财年单店经济 series/cost_fy.csv ═══════════
#
# 单位：金额百万美元（_mn）、面积百万平方英尺（_msf）、家数（整数）、百分比（_pct）。
# 起点 FY2016，理由见 FY_FIRST。
# 除 `preopen_mn`（FY2022 起源里不再单列，见口径坑 7）与 `mdna_*`（FY2025 起才有）
# 之外每一列都必须有值 —— 缺就抛，README「缺列一律失败」。
# 这两列**留空的理由都写在数据里**：preopen_mn 空的那些年 `preopen_src` 是
# `not-disclosed`，mdna_* 空的那些年源里那句话根本不带数。没有哪一列会「空得没有说法」。
#
# 两列口径旗标，画图前必须看：
#   seg_oi_basis  `op_income_us_mn` / `op_income_ca_mn` / `op_income_oi_mn` 三列的口径。
#                 见口径坑 6。
#                 **跨 `pre-sbc-alloc` / `sbc-alloc` 直接连线是错的**，那条线上会多出
#                 一个纯属股酬重新分摊的假拐点。合并口径的 `op_income_mn` 不带这个问题。
#   preopen_src   `sga_mn` 里那笔开办费的来路。见口径坑 7 —— **不是**「含没含」，
#                 含是无条件的。

FY_TAGS = {
    'net_sales_mn': ('RevenueFromContractWithCustomerExcludingAssessedTax',
                     (('ProductOrServiceAxis', 'us-gaap:ProductMember'),)),
    'memb_fee_mn': ('RevenueFromContractWithCustomerExcludingAssessedTax',
                    (('ProductOrServiceAxis', 'us-gaap:MembershipMember'),)),
    'total_rev_mn': ('Revenues', ()),
    'merch_cost_mn': ('CostOfGoodsAndServicesSold', ()),
    'sga_mn': ('SellingGeneralAndAdministrativeExpense', ()),
    'preopen_mn': ('PreOpeningCosts', ()),
    'op_income_mn': ('OperatingIncomeLoss', ()),
    'capex_mn': ('PaymentsToAcquirePropertyPlantAndEquipment', ()),
    'dda_mn': ('DepreciationDepletionAndAmortization', ()),
}

#: 分部经营利润的三代成员名，与 SEG_MEMBER 同一套。
FY_SEG_OI = {'us': 'op_income_us_mn', 'ca': 'op_income_ca_mn', 'oi': 'op_income_oi_mn'}

#: 分部经营利润口径断点所在的那篇申报（FY2022 10-K）。口径坑 6 引了它的原文。
#: 判定规则**不是「年份 >= 2020」**，而是「这一年的分部经营利润最后由哪篇申报供给，
#: 那篇是不是这一篇或更晚」—— 这样 Costco 哪天补重述了 FY2019，本表会自己跟上，
#: 而不需要有人记得回来改一个硬编码的年份。
SEG_OI_RESTATE_ACC = '0000909832-22-000021'
SEG_OI_BASIS_PRE = 'pre-sbc-alloc'      # 分部经营利润**不含**股酬分摊（FY2019 及更早）
SEG_OI_BASIS_POST = 'sbc-alloc'         # 分部经营利润**含**股酬分摊（FY2020 起）

#: `preopen_src` 的三个取值。含义见口径坑 7 —— 它记的是来路，不是「含没含」。
PREOPEN_LOADER = 'loader-folded'        # 申报里开办费单列，本模块把它加进了 sga_mn
PREOPEN_ISSUER = 'issuer-folded'        # Costco 自己重述时并进了 SG&A，本模块没动
PREOPEN_NONE = 'not-disclosed'          # 源里根本没有这条线了（FY2022 起）

#: Item 2 那句面积。FY2016 结尾多一个词（"Other International locations."），
#: 所以最后一段不能钉死在句号上。
_SQFT = re.compile(
    r'warehouses contained approximately ([\d.]+) million square feet[^.]*?:\s*'
    r'([\d.]+) million in the U\.S\.;\s*([\d.]+) million in Canada;\s*and\s*'
    r'([\d.]+) million in Other International', re.I)
#: Item 2 自有 / 租赁表的合计行。用后面那句 "(1) N of the M leases are land-only"
#: 当右锚点，比「表里第几行」稳得多 —— 国家行数逐年在变。
_OWNLEASE = re.compile(r'Total\s+(\d+)\s+(\d+)\s+(\d+)\s*_+\s*\(1\)\s*(\d+) of the (\d+) '
                       r'leases are land-only')

# ── Item 2 的「按财年开业」表：净开店数的**第二条腿**，也是 FY_FIRST 那年的唯一来源 ──
#
# 净开店数平时走 XBRL `NumberOfStores` 的年度差，但**序列第一年没有上一年可减**，
# 于是 FY2016 那四格原本是空的 —— 而同一份 FY2016 10-K 的 Item 2 里就印着
# "2016 | 21 | 2 | 6 | 29"，series/cost_cohort.csv 也从 Costco 自己的图上拿到了 29。
# 「净开店数图第一根柱是空的，旁边队列图同一年是 29」是没法向读者交代的。
#
# 为什么选「解这张表」而不是「把 FY2016 整行砍掉」：
#   1. 这张表在需要它的那几篇里都在。FY2016-FY2019 四份 10-K 各有一张（措辞略有差别：
#      只有 FY2016 那份带 "Openings by Fiscal Year" 这个标题，所以**锚点用
#      "Total Warehouses in Operation"**，四份都有且各只出现一次）。FY2020 起这张表
#      被删了 —— 无所谓，那时 XBRL 年度差早就接上了。
#   2. 它能被独立验。FY2017 / FY2018 / FY2019 三年**两条腿都有值**，实测逐格相等
#      （13/6/7/26、13/3/5/21、16/0/4/20），所以这不是「换个来源凑一个数」，
#      而是一条已经在三年上对过账的路。表的脚注写着 "(1) Net of closings and relocations"，
#      与 XBRL 年度差是同一个口径，这也是它们能对上的原因。
#   3. 那四篇是**冻结的历史 accession**，版式永远不会再变。正则在这里没有漂移风险，
#      这跟「对着每年新出的 10-K 硬解一张表」是两回事。
#   4. 砍掉 FY2016 要扔掉一整行**其它每一列都齐全**的数据，只为了一格 —— 代价不对等。
# 解不出来就**抛**，绝不留空：README「缺列一律失败」，何况这四格现在已经从
# `_write` 的 optional 名单里拿掉了。
_OPEN_ANCHOR = 'Total Warehouses in Operation'
#: 表里的「0」印成破折号（FY2019 那行 Canada 是 "—"），em/en dash 都见过。
_OPEN_NUM = r'\d[\d,]*|—|–'
#: 表尾那行 "Total 546 100 139 785"，用来把匹配范围封在表内。
_OPEN_END = re.compile(r'\bTotal\s+\d[\d,]*\s+\d[\d,]*\s+\d[\d,]*\s+\d[\d,]*')


def _openings_row(text, fy):
    """Item 2 那张表里 `fy` 那一行 → (us, ca, oi, total, 期末在营总数)；没有这张表就 None。

    行形如 "2016 21 2 6 29 715"：四个分国家/合计的开业数，再跟一个**累计在营家数**。
    最后那一格是白送的校验锚 —— 它必须等于 XBRL 的 `NumberOfStores` 合计。

    只在 `_OPEN_ANCHOR` 与表尾 Total 行之间找，不在全文找：正文里
    "2016" 后面跟五个数字的地方多的是（利润表、债务到期表都长这样）。
    "2017 (expected through 12/31/2016)" 那种预告行天然匹配不上（年份后面是括号不是数字），
    "2012 and prior" 那种起始行也是（后面是单词）—— 两种都不该被当成某一年的开业数。
    """
    i = text.find(_OPEN_ANCHOR)
    if i < 0:
        return None
    tail = text[i + len(_OPEN_ANCHOR):]
    end = _OPEN_END.search(tail)
    if not end:
        return None
    seg = tail[:end.end()]
    m = re.search(rf'(?<![\d.,]){fy}\s+({_OPEN_NUM})\s+({_OPEN_NUM})\s+({_OPEN_NUM})\s+'
                  rf'({_OPEN_NUM})\s+(\d[\d,]*)', seg)
    if not m:
        return None
    n = [0 if g in ('—', '–') else int(g.replace(',', '')) for g in m.groups()]
    if n[0] + n[1] + n[2] != n[3]:
        raise CostSecError(
            f'FY{fy} Item 2 开业表那一行三国合计 {n[0]}+{n[1]}+{n[2]}={n[0] + n[1] + n[2]} '
            f'≠ 行末的 Total {n[3]} —— 列串位了，拒绝采信')
    return tuple(n)


def _latest_fy_facts(cache_dir, filings):
    """→ (val, src, stores, consol_oi_hist)。同一年多篇申报时**取最新申报的值**（口径坑 5）。

    `src[(s, e)][列名] = (申报日, accession)` —— 分部经营利润那三列也记，
    `_seg_oi_basis` 靠它判断这一年落在口径断点的哪一侧（口径坑 6）。
    只记 accession 不行：申报代理换过前缀，字典序不是时间序（同 `_collect_segments` 的坑）。

    `consol_oi_hist[(s, e)] = {值: [accession…]}` —— 合并口径经营利润在**每一篇**里的值，
    用来验「合并不受股酬重分摊影响」这句话（见 `_assert_consolidated_oi_stable`）。
    """
    val, src = defaultdict(dict), defaultdict(dict)
    stores = defaultdict(dict)
    store_src = defaultdict(dict)
    beval, besrc = defaultdict(dict), defaultdict(dict)
    consol_oi_hist = defaultdict(lambda: defaultdict(list))
    for f in sorted((x for x in filings if x['form'] == '10-K' and x['filed'] >= XBRL_FROM),
                    key=lambda x: x['filed']):
        raw = _instance(cache_dir, f)
        for local, s, e, i, dims, txt in _facts(raw):
            dk = tuple(sorted(dims.items()))
            v = _num(txt)
            if v is None:
                continue
            if local == 'NumberOfStores' and i:
                cc = dims.get('StatementGeographicalAxis', '')
                if len(dims) == 1 and cc.startswith('country:'):
                    stores[i][cc.split(':')[1]] = v
                    store_src[i][cc.split(':')[1]] = f['accession']
                elif not dims:
                    stores[i]['_total'] = v
                continue
            if not s or not e or _weeks(s, e) not in (52, 53):
                continue
            for col, (tag, want) in FY_TAGS.items():
                if local == tag and dk == want:
                    val[(s, e)][col] = v
                    src[(s, e)][col] = (f['filed'], f['accession'])
            # 老口径（FY2015 及更早）顺手收一份，喂 `build_fy_be`。两代分开装在
            # `beval` 里，不与 `val` 混 —— 理由见 FY_BE_TAGS 的注释（同一个名字在
            # 两代里指的不是同一个数）。这里不按年份筛：筛在 `build_fy_be` 里，
            # 那样 FY2016/FY2017 这两年（老名字仍在印）能当重叠年对一次账。
            for col, tag in FY_BE_TAGS.items():
                if local == tag and not dims:
                    beval[(s, e)][col] = v
                    besrc[(s, e)][col] = (f['filed'], f['accession'])
            if local == 'OperatingIncomeLoss' and not dims:
                consol_oi_hist[(s, e)][v].append(f['accession'])
            reg = _seg_region_oi(local, dims)
            if reg:
                val[(s, e)][FY_SEG_OI[reg]] = v
                src[(s, e)][FY_SEG_OI[reg]] = (f['filed'], f['accession'])
    return val, src, stores, consol_oi_hist, beval, besrc


def _assert_consolidated_oi_stable(consol_oi_hist):
    """合并口径 `op_income_mn` 在跨申报时**必须一字不变**（FY_FIRST 起）。

    这条断言是口径坑 6 那句「合并不受影响」的**执行版**。分部经营利润在 FY2022 10-K 里
    被重述过（股酬改成分摊到分部），而合并数一分钱没动 —— FY2020 在三篇 10-K 里都是
    5,435，FY2021 在两篇里都是 6,708。所以下游可以放心跨 FY2019/FY2020 连 `op_income_mn`
    这条线，只有分部那三列要看 `seg_oi_basis`。

    为什么要真跑一遍而不是写在注释里：README「不出声的失败」那一节的家规是
    **注释里的事实主张必须仍然成立**。哪天 Costco 真重述了合并数，这句话就成了假话，
    而假话不会自己喊 —— 除非有这么一条断言替它喊。
    """
    for (s, e), hist in sorted(consol_oi_hist.items()):
        if int(e[:4]) < FY_FIRST or len(hist) <= 1:
            continue
        detail = '；'.join(f'{v // 10 ** 6} 来自 ' + '/'.join(sorted(set(a)))
                          for v, a in sorted(hist.items()))
        raise CostSecError(
            f'FY{e[:4]} 的合并经营利润跨申报变了：{detail}。'
            f'口径坑 6 声称「股酬只在分部之间挪位置、合并不动」，这条现在不成立了 —— '
            f'`seg_oi_basis` 那一列的前提没了，必须人来看，不许照写。')


def _seg_oi_basis(fy_src, restate_filed):
    """这一年的分部经营利润是哪个口径 → `pre-sbc-alloc` / `sbc-alloc`。口径坑 6。

    判据是「**最后供给**这三列的那篇申报，是不是在重述那篇（含）之后」。
    三列的最新供给方必须是同一篇 —— 分部经营利润三个地区永远同表列示，
    不同就说明解析漂了（比如某一区被第三根轴污染后覆盖成了另一篇的值）。
    """
    got = [fy_src.get(FY_SEG_OI[r]) for r in ('us', 'ca', 'oi')]
    if any(g is None for g in got):
        raise CostSecError(f'分部经营利润三列的来源申报缺了一部分：{got}，判不出口径')
    if len({g[1] for g in got}) != 1:
        raise CostSecError(
            f'分部经营利润三列来自不同申报 {sorted({g[1] for g in got})} —— '
            f'它们在 10-K 里永远同表列示，不同说明解析串了，判不出口径')
    return SEG_OI_BASIS_POST if got[0][0] >= restate_filed else SEG_OI_BASIS_PRE


def _seg_region_oi(local, dims):
    """分部经营利润的地区判定。与 `_seg_region` 同规则，只是换了元素名。"""
    if local != 'OperatingIncomeLoss':
        return None
    region, extra = None, False
    for ax, mem in dims.items():
        if ax in SEG_AXES:
            region = SEG_MEMBER.get(mem)
        elif ax not in SEG_ALLOWED_EXTRA_AXES:
            extra = True
    return None if extra else region


def _tenk_html(cache_dir, f):
    return _text(_fetch(cache_dir, f'doc-{f["accession"].replace("-", "")}-{f["primary"]}',
                        f'{ARCHIVE}/{f["accession"].replace("-", "")}/{f["primary"]}'))


def _reconcile_openings(y, xbrl_op, item2_op, wtot):
    """净开店数两条腿合一 → (us, ca, oi, total)。两条都没有就抛，**绝不返回空格子**。

    · XBRL 腿 = 分国家 `NumberOfStores` 的年度差。序列第一年没有上一年可减，所以它是空的。
    · Item 2 腿 = 10-K 里那张按财年开业的表（见 `_OPEN_ANCHOR` 上面的长注）。
      FY2020 起 Costco 把这张表删了，所以它只在头几年有。
    两条腿的空档**恰好互补**：第一年只有 Item 2，FY2020 起只有 XBRL，中间三年都有。

    都有的年份**必须逐格相等**，不等就抛。这不是「挑一条信」—— 两条腿口径相同：
    那张表自己就写着 net of closings and relocations（FY2016 那份放在脚注 (1) 里，
    FY2017-FY2019 写进了表前那句话），与 XBRL 年度差是同一个定义；
    实测 FY2017/18/19 三年逐格相等，所以不等只可能是某一边的解析漂了，
    属 README「不出声的失败」那一类。
    只有 Item 2 一条腿时，用它自带的期末累计在营家数对一次 XBRL 的合计 —— 白送的第二只眼。
    """
    if xbrl_op and item2_op and tuple(xbrl_op) != item2_op[:4]:
        raise CostSecError(
            f'FY{y} 净开店数两条腿对不上：XBRL 分国家仓数年度差 {tuple(xbrl_op)}，'
            f'10-K Item 2 开业表 {item2_op[:4]}。两者口径相同（表脚注 "Net of closings '
            f'and relocations"），FY2017-FY2019 实测逐格相等 —— 对不上说明有一边解析漂了。')
    if xbrl_op:
        return list(xbrl_op)
    if item2_op:
        if item2_op[4] != wtot:
            raise CostSecError(
                f'FY{y} Item 2 开业表行末的期末在营总数 {item2_op[4]} ≠ XBRL '
                f'NumberOfStores 合计 {wtot} —— 这一行多半不是 FY{y} 那一行，拒绝采信')
        return list(item2_op[:4])
    raise CostSecError(
        f'FY{y} 净开店数两条腿都拿不到：没有上一年的分国家仓数可减，10-K Item 2 里也找不到'
        f'那张按财年开业的表（锚点 "{_OPEN_ANCHOR}"）。这四列不允许留空 —— '
        f'空着的第一根柱旁边就是 cost_cohort.csv 同一年的队列家数，没法向读者交代。')


def build_fy(cache_dir, filings, mdna_fy):
    """→ (header, rows)。XBRL 出利润表与分国家仓数，10-K HTML 出面积与自有/租赁。"""
    val, src, stores, consol_oi_hist, _, _ = _latest_fy_facts(cache_dir, filings)
    _assert_consolidated_oi_stable(consol_oi_hist)
    restate_filed = next((f['filed'] for f in filings
                          if f['accession'] == SEG_OI_RESTATE_ACC), None)
    if not restate_filed:
        raise CostSecError(
            f'申报清单里找不到分部经营利润重述那篇 {SEG_OI_RESTATE_ACC}（FY2022 10-K）。'
            f'`seg_oi_basis` 判不出来，而没有那一列的 cost_fy.csv 会让下游把两个口径连成'
            f'一条线 —— 见口径坑 6，拒绝写表。')
    tenks = {int(f['report'][:4]): f for f in filings
             if f['form'] == '10-K' and f['report']}
    head = ['fy', 'period_start', 'period_end', 'weeks',
            'net_sales_mn', 'memb_fee_mn', 'total_rev_mn', 'merch_cost_mn', 'sga_mn',
            'preopen_mn', 'op_income_mn', 'capex_mn', 'dda_mn',
            'op_income_us_mn', 'op_income_ca_mn', 'op_income_oi_mn', 'seg_oi_basis',
            'wh_us', 'wh_ca', 'wh_oi', 'wh_total',
            'wh_open_us', 'wh_open_ca', 'wh_open_oi', 'wh_open_total',
            'wh_owned', 'wh_leased',
            'sqft_us_msf', 'sqft_ca_msf', 'sqft_oi_msf', 'sqft_total_msf',
            'preopen_src', 'mdna_tkt_pct', 'mdna_frq_pct']
    keys = sorted((k for k in val if int(k[1][:4]) >= FY_FIRST - 1), key=lambda k: k[1])
    rows, prev_wh = [], None
    for (s, e) in keys:
        y = int(e[:4])
        v = val[(s, e)]
        wh = stores.get(e, {})
        wus, wca = wh.get('US'), wh.get('CA')
        wtot = wh.get('_total')
        woi = None if None in (wus, wca, wtot) else wtot - wus - wca
        if y >= FY_FIRST:
            miss = [c for c in ('net_sales_mn', 'memb_fee_mn', 'total_rev_mn',
                                'merch_cost_mn', 'sga_mn', 'op_income_mn', 'capex_mn',
                                'dda_mn') if c not in v]
            if miss:
                raise CostSecError(f'FY{y} 缺 XBRL 标签 {miss}，拒绝写半空的行')
            if None in (wus, wca, wtot):
                raise CostSecError(f'FY{y} 缺分国家 NumberOfStores（US={wus} CA={wca} 合计={wtot}）')

        # ── 硬恒等式（CONTRACT.md §5 第 5 条）──
        # 净销售额 + 会员费 − 商品成本 − SG&A = 经营利润。
        # FY2021 及以前开办费是**单列**的一行，SG&A 里不含它，所以余项会恰好等于开办费；
        # FY2020 / FY2021 已经在 FY2022 10-K 里被重述成「并进 SG&A」，
        # 取最新值就已经含了它 —— 那两年再折一次就会重复扣。
        # 所以判据不是「按年份硬编码折不折」，而是**看余项等于什么**：
        # 余项 ≈ 0 → 已经含了；余项 ≈ 开办费 → 折进去再验一次。这样将来 Costco
        # 再挪一次行也不会静默出错。
        #
        # 出表的那一列叫 `preopen_src`，记的是**上面这三条路里走了哪一条**，
        # 而不是「sga_mn 含不含开办费」—— 含是无条件的（口径坑 7 的硬承诺），
        # 三条路都以「已含」收尾，恒等式就是这个承诺的执行者。
        preopen_src = PREOPEN_NONE
        sga = v.get('sga_mn')
        if y >= FY_FIRST:
            resid = (v['net_sales_mn'] + v['memb_fee_mn'] - v['merch_cost_mn']
                     - sga - v['op_income_mn'])
            pre = v.get('preopen_mn')
            if abs(resid) > 10 ** 6:
                if pre is not None and abs(resid - pre) <= 10 ** 6:
                    sga += pre                       # 申报里单列 → 本模块折进去
                    preopen_src = PREOPEN_LOADER
                else:
                    raise CostSecError(
                        f'FY{y} 恒等式不成立：净销售 {v["net_sales_mn"]} + 会员费 '
                        f'{v["memb_fee_mn"]} − 商品成本 {v["merch_cost_mn"]} − SG&A {sga} '
                        f'− 经营利润 {v["op_income_mn"]} = {resid}，'
                        f'开办费是 {pre}。两者对不上，拒绝写表。')
            elif pre is not None:
                preopen_src = PREOPEN_ISSUER         # 余项已是 0 而源里仍单报开办费
                                                     # → Costco 自己重述时并进去了
            # 口径坑 7 的承诺，就地验一次：preopen_mn 有值 ⇔ 它确实含在 sga_mn 里。
            # `PREOPEN_LOADER` 是本模块刚加的，`PREOPEN_ISSUER` 是余项为 0 反推出来的，
            # 两条都成立才允许 preopen_mn 出现在这一行上。
            if (pre is None) != (preopen_src == PREOPEN_NONE):
                raise CostSecError(
                    f'FY{y} 的 preopen_mn={pre} 与 preopen_src={preopen_src} 自相矛盾 —— '
                    f'口径坑 7 承诺两者同生同灭（有值就一定已含在 sga_mn 里）')
            for r in ('us', 'ca', 'oi'):
                if FY_SEG_OI[r] not in v:
                    raise CostSecError(f'FY{y} 缺分部经营利润 {FY_SEG_OI[r]}')
            # ⚠️ 这条恒等式**跨口径断点照样成立**，所以它探测不到口径坑 6 那条断线：
            # FY2020 重述前 3,633+860+942 = 5,435，重述后 3,822+778+835 也是 5,435。
            # 股酬只在三个分部之间挪位置，合计不动 —— 断点得靠 `seg_oi_basis` 那一列
            # 显式记，指望这条恒等式替你把关就会拿两个口径连成一条线。
            segsum = sum(v[FY_SEG_OI[r]] for r in ('us', 'ca', 'oi'))
            if abs(segsum - v['op_income_mn']) > 10 ** 6:
                raise CostSecError(
                    f'FY{y} 三个分部经营利润合计 {segsum} ≠ 合并 {v["op_income_mn"]}')

        if y < FY_FIRST:
            prev_wh = (wus, wca, woi, wtot)      # 只当净开店数的基期用，不出行
            continue

        # 净开店数的主腿是**分国家仓数的年度差**。**不要去正则 MD&A 那句叙述**：
        # 措辞在「24」与「twenty-four」之间来回换，正则会时灵时不灵。
        # 年度差在 FY2025 上逐字复现了叙述里的 24 / 15 / 2 / 7。
        # 序列第一年没有上一年可减，那一格由 Item 2 的开业表补上（见 `_reconcile_openings`）。
        xbrl_op = None
        if prev_wh and None not in prev_wh:
            xbrl_op = (wus - prev_wh[0], wca - prev_wh[1], woi - prev_wh[2], wtot - prev_wh[3])
        prev_wh = (wus, wca, woi, wtot)

        f10k = tenks.get(y)
        if not f10k:
            raise CostSecError(f'FY{y} 找不到对应的 10-K，取不到 Item 2 的面积与自有/租赁')
        html = _tenk_html(cache_dir, f10k)
        msq = _SQFT.search(html)
        if not msq:
            raise CostSecError(
                f'FY{y} 10-K Item 2 里那句面积没匹配上（找的是 "warehouses contained '
                f'approximately X million square feet … in the U.S.; … Canada; … Other '
                f'International"）。措辞变了就得改 _SQFT，不许留空。')
        mol = _OWNLEASE.search(html)
        if not mol:
            raise CostSecError(f'FY{y} 10-K Item 2 里自有/租赁合计行没匹配上，见 _OWNLEASE')
        owned, leased, tot = int(mol.group(1)), int(mol.group(2)), int(mol.group(3))
        if owned + leased != tot or tot != wtot or leased != int(mol.group(5)):
            raise CostSecError(
                f'FY{y} Item 2 自有/租赁对不上：自有 {owned} + 租赁 {leased} = {owned + leased}，'
                f'表里合计 {tot}，XBRL NumberOfStores {wtot}，脚注里的租赁数 {mol.group(5)}')
        sq = [float(msq.group(i)) for i in (2, 3, 4, 1)]
        if abs(sum(sq[:3]) - sq[3]) > 0.35:
            raise CostSecError(f'FY{y} 面积三地合计 {sum(sq[:3]):.1f} 与总数 {sq[3]} 差太多')

        op = _reconcile_openings(y, xbrl_op, _openings_row(html, y), wtot)
        md = mdna_fy.get(y, (None, None))
        rows.append([
            f'FY{y}', s, e, _weeks(s, e),
            _mn(v['net_sales_mn'], f'FY{y} 净销售'), _mn(v['memb_fee_mn'], f'FY{y} 会员费'),
            _mn(v['total_rev_mn'], f'FY{y} 总收入'), _mn(v['merch_cost_mn'], f'FY{y} 商品成本'),
            _mn(sga, f'FY{y} SG&A'),
            '' if v.get('preopen_mn') is None else _mn(v['preopen_mn'], f'FY{y} 开办费'),
            _mn(v['op_income_mn'], f'FY{y} 经营利润'), _mn(v['capex_mn'], f'FY{y} 资本开支'),
            _mn(v['dda_mn'], f'FY{y} 折旧摊销'),
            _mn(v[FY_SEG_OI['us']], f'FY{y} 美国经营利润'),
            _mn(v[FY_SEG_OI['ca']], f'FY{y} 加拿大经营利润'),
            _mn(v[FY_SEG_OI['oi']], f'FY{y} 其他国际经营利润'),
            _seg_oi_basis(src[(s, e)], restate_filed),
            wus, wca, woi, wtot, op[0], op[1], op[2], op[3], owned, leased,
            f'{sq[0]:g}', f'{sq[1]:g}', f'{sq[2]:g}', f'{sq[3]:g}', preopen_src,
            '' if md[0] is None else f'{md[0]:g}', '' if md[1] is None else f'{md[1]:g}'])
    if not rows:
        raise CostSecError('财年表一行都没解出来')
    _assert_basis_contiguous(head, rows)
    return head, rows


def _assert_basis_contiguous(head, rows):
    """`seg_oi_basis` 必须是「一段 pre 接一段 post」，中间不许交错。

    交错说明「最后供给这一年的申报」这条判据在某一年上失效了（比如某年的分部行只在
    一篇老申报里出现过、而它相邻的两年都被 FY2022 10-K 重述过）。那种序列画出来会是
    一条来回跳口径的线，比整条都是老口径还糟 —— 而它不会报任何错，正是
    README「不出声的失败」那一类。所以在这里当场抓。
    """
    i = head.index('seg_oi_basis')
    seq = [r[i] for r in rows]
    want = [SEG_OI_BASIS_PRE] * seq.count(SEG_OI_BASIS_PRE) + \
           [SEG_OI_BASIS_POST] * seq.count(SEG_OI_BASIS_POST)
    if seq != want:
        raise CostSecError(
            f'seg_oi_basis 交错了：{list(zip((r[0] for r in rows), seq))}。'
            f'口径断点只该有一个，出现交错说明按「最后供给方」判口径这条判据失效了。')


def collect_mdna_fy(cache_dir, filings):
    """{财年: (ticket%, frequency%)} —— 从 **10-K** MD&A 取，口径是**整个财年**。"""
    out = {}
    for f in filings:
        if f['form'] != '10-K' or f['filed'] < '2025-01-01':
            continue
        sent = _mdna_sentence(_tenk_html(cache_dir, f))
        if sent:
            out[int(f['report'][:4])] = _mdna_numbers(sent)
    return out


# ═════ 表 5：盈亏平衡回填 series/cost_fy_be.csv ═════
#
# 单位：百万美元。列：fy, period_start, period_end, weeks, net_sales_mn, memb_fee_mn,
#       total_rev_mn, merch_cost_mn, sga_mn, preopen_mn, op_income_mn, preopen_src, src_acc
#
# ── 这张表存在的理由 ──
# /cost/ Exhibit 16 那张队列矩阵横跨 FY2011–FY2025，而接在它下面的两条「盈亏平衡」线
# 只能从 FY2016 起画 —— 因为它们读 `cost_fy.csv`，而那张表的左端是 FY_FIRST。
# 页面所有者 2026-09-04 的指令是「盈亏平衡也从 FY2011 开始算」。
# 盈亏平衡只需要**四个比率输入**：净销售额、会员费、商品成本、SG&A（金额那一步用的是
# 队列矩阵 Totals 行，不是仓店数），而这四个数 FY2011–FY2015 在 XBRL 里**全都有**，
# 只是元素名是上一代的（FY_BE_TAGS）。`cost_fy.csv` 拿不到的是仓数 / 面积 / 分部那二十
# 多列 —— 那些跟盈亏平衡一点关系都没有。所以：窄表回填，宽表不动。
#
# ── `sga_mn` 是**折进开办费之后**的口径，与 cost_fy.csv 一致 ──
# 这五年开办费都是损益表上单列的一行（46/37/51/63/65），和 FY2016–FY2019 一样，
# 所以走同一条 `loader-folded`：本模块把它加进 `sga_mn`，`preopen_mn` 另存一列备查。
# 不折的后果不是「差一点」，是**恰好在 FY2016 那一列出现一个纯属口径的台阶** ——
# 而那条线在图上是连着画的，读者看到的会是一个假拐点。
#
# ── ⚠️ FY2011 的 SG&A 被重述过，这是本表唯一的雷 ──
# FY2011 10-K 的损益表有第四条费用行 "Provision for impaired assets and closing costs,
# net" = 9，SG&A 印的是 8,682。FY2012 10-K 删掉了那一行、把它并进 SG&A，FY2011 重述成
# 8,691（经营利润两版都是 2,439，一分没动）。本模块「最新申报覆盖旧值」的写法自动落在
# 8,691 上 —— 但这件事**不能只写在注释里**：下面那条恒等式就是它的执行版，
# 万一哪天取到 8,682，恒等式会差 9 而当场抛，不会静默写一个差 9 的 SG&A 率。


def build_fy_be(cache_dir, filings):
    """→ (header, rows)。FY_BE_FIRST..FY_FIRST-1 的合并损益，只喂盈亏平衡两条线。

    自己再解一遍 XBRL（而不是让 update() 把 `_latest_fy_facts` 提到 leg() 外面共用）：
    instance 是**内容缓存永不过期**的，第二遍只有解析开销、一个请求都不会多发；
    而把它提到外面就等于在逐表隔离层之外留一条逃逸路径 —— 那一处抛，
    fy / cohort / 本表三条本来好好的腿会被一起带走。update() 的 docstring
    专门讲过这个形状，别为了省一遍解析把它破掉。
    """
    _val, _src, _stores, _hist, beval, besrc = _latest_fy_facts(cache_dir, filings)
    head = ['fy', 'period_start', 'period_end', 'weeks',
            'net_sales_mn', 'memb_fee_mn', 'total_rev_mn', 'merch_cost_mn', 'sga_mn',
            'preopen_mn', 'op_income_mn', 'preopen_src', 'src_acc']
    cols = ('net_sales_mn', 'memb_fee_mn', 'total_rev_mn', 'merch_cost_mn',
            'sga_mn', 'preopen_mn', 'op_income_mn')
    keys = sorted((k for k in beval if FY_BE_FIRST <= int(k[1][:4]) < FY_FIRST),
                  key=lambda k: k[1])
    rows = []
    for (s, e) in keys:
        y = int(e[:4])
        v = beval[(s, e)]
        miss = [c for c in cols if c not in v]
        if miss:
            raise CostSecError(
                f'FY{y} 缺老口径 XBRL 标签 {miss}（元素名见 FY_BE_TAGS）—— 拒绝写半空的行。'
                f'这张表只有七个数，缺一个盈亏平衡那一年就算不出来，而算不出来的那一格'
                f'在图上与「那年不需要过线」长得一模一样。')
        w = _weeks(s, e)
        if w not in (52, 53):
            raise CostSecError(f'FY{y} 的会计期 {s}→{e} 是 {w} 周，不是 52/53 周')
        ns, mf, tr = (_mn(v[c], f'FY{y} {c}') for c in
                      ('net_sales_mn', 'memb_fee_mn', 'total_rev_mn'))
        mc, sga, po, oi = (_mn(v[c], f'FY{y} {c}') for c in
                           ('merch_cost_mn', 'sga_mn', 'preopen_mn', 'op_income_mn'))
        # ── 恒等式 1：净销售额 + 会员费 = 总收入 ──
        # 老口径的净销售额与会员费是两个**独立**的标签（不像新口径是同一个标签的两个
        # ProductOrServiceAxis 成员），所以这一条是真的在对账，不是同义反复。
        if ns + mf != tr:
            raise CostSecError(
                f'FY{y} 净销售额 {ns} + 会员费 {mf} = {ns + mf} ≠ 总收入 {tr} —— '
                f'三个标签里至少有一个不是我们以为的那个数（老口径元素名见 FY_BE_TAGS）')
        # ── 恒等式 2：总收入 − 商品成本 − SG&A（含开办费） = 经营利润 ──
        # 这一条同时把上面那颗雷（FY2011 的 SG&A 8,682 vs 重述后 8,691）钉死：
        # 取到未重述那一版，这里会差 9 而抛。
        sga_all = sga + po
        if tr - mc - sga_all != oi:
            raise CostSecError(
                f'FY{y} 损益恒等式不成立：总收入 {tr} − 商品成本 {mc} − SG&A(含开办费) '
                f'{sga_all}（= {sga} + {po}）= {tr - mc - sga_all}，而经营利润是 {oi}，'
                f'差 {tr - mc - sga_all - oi}。FY2011 差 9 的话就是拿到了**未重述**的 SG&A '
                f'8,682（见本节注释），说明「最新申报覆盖旧值」这条没生效。')
        acc = max(besrc[(s, e)][c] for c in cols)[1]
        rows.append([f'FY{y}', s, e, w, ns, mf, tr, mc, sga_all, po, oi,
                     PREOPEN_LOADER, acc])
    # ── 财年必须连续且铺满，中间不许有洞 ──
    # 盈亏平衡两条线是逐年现算的：中间缺一年，图上就是两段之间夹一个灰格，
    # 而那个灰格与「那年算不出来」「那年还没开业」在引擎里画成同一个颜色。
    got = [int(r[0][2:]) for r in rows]
    want = list(range(FY_BE_FIRST, FY_FIRST))
    if got != want:
        raise CostSecError(
            f'cost_fy_be.csv 的财年是 {got}，应当是 {want} —— 回填表要么铺满 '
            f'FY{FY_BE_FIRST}–FY{FY_FIRST - 1}，要么整张不写；缺中间某一年会在图上'
            f'留一个说不清的空格。')
    return head, rows


# ═════ 表 4：开业年份矩阵 series/cost_cohort.csv ═════
#
# 单位：avg_sales_musd = 百万美元/店/年。
# 列：vintage, cohort, n_whses, fiscal_year, avg_sales_musd
#   vintage   这一格读自哪一年的 10-K。**必须有这一列**：
#             同一格数字各年 10-K 都印，但 "& Before" 那一行的**含义逐年变**
#             （FY2024 10-K 是 "2015 & Before" 686 家，FY2025 10-K 是
#             "2016 & Before" 715 家），没有 vintage 就分不清哪张矩阵是哪张。
#   cohort    "2019" / "2016 & Before" / "Totals"，逐字照抄 10-K。

def _cohort_cells(raw_html):
    """10-K HTML → 那张表的所有行（每行是去掉空格子与 "$" 之后的文本列表）。

    锚点是 "Year Opened"：往前找最近的 `<table`、往后找最近的 `</table>`。
    **必须丢掉空格子**，右对齐就是靠这个还原的 —— 表里前面那些空列在 HTML 里
    是真的空 `<td>`，留着它们反而对不齐。
    """
    i = raw_html.find('Year Opened')
    if i < 0:
        return None, None
    j, k = raw_html.rfind('<table', 0, i), raw_html.find('</table>', i)
    if j < 0 or k < 0:
        return None, None
    tbl = raw_html[j:k + 8]
    rows = []
    for rm in re.finditer(r'(?is)<tr[^>]*>(.*?)</tr>', tbl):
        cells = [re.sub(r'\s+', ' ', _html.unescape(re.sub(r'<[^>]+>', '', c.group(1)))).strip()
                 for c in re.finditer(r'(?is)<t[dh][^>]*>(.*?)</t[dh]>', rm.group(1))]
        cells = [c for c in cells if c and c != '$']
        if cells:
            rows.append(cells)
    # 脚注**在表格里面**（`</table>` 之前），不在表外 —— 它自己占最后两行 `<tr>`：
    #   ['*First year sales annualized.']
    #   ['2017 and 2023 were 53-week fiscal years but have been normalized for …']
    # 去表外找会一路读进 Item 7 的 MD&A 正文，然后什么都匹配不上、静默返回 None。
    foot = None
    for n, r in enumerate(rows):
        if r[0].startswith('*First year sales annualized'):
            foot = ' '.join(c for rr in rows[n:] for c in rr).strip()
            break
    return rows, foot


#: 「按家数加权的队列均值」与「印出来的 Totals」允许的最大偏差（百万美元/店/年）。
#:
#: **这个数不能贴着实测给，理由和 `_DECK_TOL` 恰好相反。** deck 那边偏差只来自
#: 两个已印出来的百分数相乘，量级封死；这里的偏差来自**十一行队列均值各自四舍五入**
#: 之后再加权，误差是可以累加的：
#:   · 每个队列均值按整数印 → 加权后最坏偏 0.5；
#:   · Totals 自己也按整数印 → 再偏 0.5；
#:   合起来理论上限 ≈ **1.0**，也就是说旧的 `> 1.0` 门槛**一点余量都没有**。
#: 实测（2026-09，FY2020-FY2025 六份 10-K、六张矩阵、共 60 个 (vintage, 财年) 列）：
#:   最大 0.81（FY2022 矩阵的 2017 列：加权 163.81 vs 印的 163）
#:   其后 0.79（FY2020 的 2017 列）、0.74（FY2025 的 2023 列）、0.72（FY2021 的 2017 列）
#:   均值 0.23、中位数 0.18；>0.5 的有 8 个，>0.7 的有 4 个。
#: 四个已经落在 0.72-0.81，离 1.0 只剩 0.2 —— 明年的 10-K 多一行队列、
#: 或者哪一格的四舍五入方向凑巧对齐，就会**在完全没有出错的情况下**把这道护栏顶爆。
#: 所以放到 1.5：比理论上限 1.0 高 50%。
#:
#: ⚠️ 放宽**是有代价的**，别当作白捡的。把 FY2025 那张矩阵逐行左移一格实测，
#: 这道均值检查看到的偏差是：
#:   "2016 & Before"（715 家）26.61  ← 大队列串位，怎么都挡得住
#:   2024(29 家) 3.14、2022(23) 2.52、2023(23) 2.01、2017(26) 2.00、
#:   2018(21) 1.70、2021(20) 1.65、2020(13) 1.29、2019(20) 1.20
#: 也就是说 1.0 → 1.5 会让**最小那两行（13 家、20 家）的串位从「抓得到」变成「抓不到」**。
#: 所以放宽的同时补了 `_cohort_check_widths` 那道**零容差**的结构检查：
#: 队列 Y 的值个数必须恰好是 fy−Y+1（"& Before" 与 Totals 则占满表头宽度），
#: 串一格必然少一个值 —— 六张矩阵 66 行逐行验过，无一例外。
#: 对齐由那道零容差的管，这道均值检查退回它真正擅长的事：**验数值本身没被抄串**。
#: 要重调请把上面两组数都重算一遍再动手，不要凭手感 —— 这些数就是为此留的。
_COHORT_TOL = 1.5


def _cohort_check_widths(fy, years, data, totals):
    """右对齐的**零容差**检查：每行的值个数必须与它该覆盖的财年数完全相等。

    2017 年开的仓在 FY2016 那一栏不存在，所以 FY2025 矩阵里 "2017" 那行只能有
    2025−2017+1 = 9 个值；"& Before" 与 "Totals" 覆盖全部财年，占满表头宽度。
    串一格 = 少一个值 = 当场抓住，不需要任何容差 —— 这正是加权均值那道做不好的事
    （小队列串位只让均值动 1.2，见 `_COHORT_TOL` 的实测表）。
    """
    for cohort, _n, vals in data:
        want = len(years) if '& Before' in cohort else fy - int(cohort[:4]) + 1
        if len(vals) != want:
            raise CostSecError(
                f'FY{fy} 矩阵 "{cohort}" 行有 {len(vals)} 个值，按开业年份右对齐应当是 '
                f'{want} 个（表头 {years[0]}..{years[-1]}）—— 串位了，拒绝采信')
    if len(totals[2]) != len(years):
        raise CostSecError(
            f'FY{fy} 矩阵 Totals 行有 {len(totals[2])} 个值，应当占满表头的 {len(years)} 个')


def _cohort_parse(rows, fy):
    """表格行 → [(cohort, n, {财年: 值})]，并把权重均值对回 Totals 行。

    对齐规则：财年表头**排在数据行下面**（HTML 里就是这个顺序），
    每个数据行的值向**右**对齐 —— 末位那个值属于当前财年，往回数。
    """
    hdr = next((r for r in rows if len(r) >= 5 and all(re.fullmatch(r'\d{4}', c) for c in r)),
               None)
    if not hdr:
        raise CostSecError(f'FY{fy} 的开业年份矩阵找不到财年表头行')
    years = [int(y) for y in hdr]
    if years[-1] != fy:
        raise CostSecError(f'FY{fy} 的矩阵表头末位是 {years[-1]}，应当是当年 {fy}')
    data, totals = [], None
    for r in rows:
        if r is hdr:
            # 表头行第一格也是四位数字（"2016"），不排掉就会被当成一个开业队列，
            # 家数认成 2017，家数合计立刻变成四位数。用对象身份排，不用值排。
            continue
        if re.fullmatch(r'\d{4}( & Before)?', r[0]) and len(r) >= 3:
            vals = [int(x.replace(',', '')) for x in r[2:]]
            data.append((r[0], int(r[1].replace(',', '')), dict(zip(years[-len(vals):], vals))))
        elif r[0] == 'Totals' and len(r) >= 3:
            vals = [int(x.replace(',', '')) for x in r[2:]]
            totals = ('Totals', int(r[1].replace(',', '')),
                      dict(zip(years[-len(vals):], vals)))
    if not data or not totals:
        raise CostSecError(f'FY{fy} 的矩阵没解出数据行或 Totals 行')
    _cohort_check_widths(fy, years, data, totals)
    n = sum(d[1] for d in data)
    if n != totals[1]:
        raise CostSecError(f'FY{fy} 各队列家数合计 {n} ≠ Totals 的 {totals[1]}')
    for y, tv in totals[2].items():
        num = sum(c * v[y] for _c, c, v in data if y in v)
        den = sum(c for _c, c, v in data if y in v)
        if den and abs(num / den - tv) > _COHORT_TOL:
            raise CostSecError(
                f'FY{fy} 矩阵 {y} 列：按家数加权均值 {num / den:.2f} 与印出来的 Totals '
                f'{tv} 差 {abs(num / den - tv):.2f} > {_COHORT_TOL} —— 说明右对齐串位了')
    return data + [totals]


def build_cohort(cache_dir, filings):
    """→ (header, rows)。逐份 10-K（FY2020 起）解那张 "Average Sales Per Warehouse" 图。"""
    head = ['vintage', 'cohort', 'n_whses', 'fiscal_year', 'avg_sales_musd']
    rows, foot = [], {}
    for f in sorted((x for x in filings if x['form'] == '10-K'), key=lambda x: x['report']):
        fy = int(f['report'][:4])
        if fy < COHORT_FIRST:
            continue
        acc = f['accession'].replace('-', '')
        raw = _fetch(cache_dir, f'doc-{acc}-{f["primary"]}',
                     f'{ARCHIVE}/{acc}/{f["primary"]}').decode('utf-8', 'replace')
        cells, fnote = _cohort_cells(raw)
        if cells is None:
            raise CostSecError(f'FY{fy} 10-K 里找不到 "Year Opened" 那张表')
        foot[fy] = fnote
        for cohort, n, vals in _cohort_parse(cells, fy):
            for y in sorted(vals):
                rows.append([f'FY{fy}', cohort, n, y, vals[y]])
    if not rows:
        raise CostSecError('开业年份矩阵一行都没解出来')
    newest = max(foot)
    if foot[newest] != COHORT_FOOTNOTE:
        print(f'WARN: FY{newest} 10-K 那张图的脚注变了 —— 现在是 {foot[newest]!r}，'
              f'模块常量 COHORT_FOOTNOTE 记的是 {COHORT_FOOTNOTE!r}。'
              f'页面图注引的是常量，请核对后同步。', file=sys.stderr)
    return head, rows


# ═══════════════════════════ 写盘 ═══════════════════════════

def _csv_path(series_dir, name):
    return os.path.join(series_dir or SERIES, name)


def _existing(path):
    if not os.path.exists(path):
        return None, []
    with open(path, newline='', encoding='utf-8') as f:
        rows = list(csv.reader(f))
    return (rows[0], rows[1:]) if rows else (None, [])


#: 已发生过的列改名，`旧名: 新名`。**只放真的改过名的列**，它是「缺列一律失败」的唯一豁免口。
#:
#: 为什么要有这么个东西：那道护栏拦的是「解析器坏了，某列悄悄没了」，而**故意改名**
#: 在它眼里长得一模一样 —— 于是任何一次改名都要求有人先手动 `rm` 掉旧 CSV，
#: 而「记得先删文件」这种约定迟早会被忘掉一次，忘掉的那次症状是整轮 FAIL（还算好），
#: 或者有人为了跑通把护栏关掉（那就糟了）。写在这里，改名这件事就**留了痕**：
#: 谁改的、旧名叫什么、为什么改，都在版本历史里，而护栏对未申报的缺列一如既往地严。
#:
#: sga_folded_preopen → preopen_src：旧名读起来像在回答「sga_mn 含不含开办费」，
#: 而它记的其实是「这一轮加载器折没折」。两者在 FY2020/FY2021 上分道扬镳
#: （Costco 自己折的，所以加载器没折，flag=0，可 sga_mn 明明含着），
#: 下游按 flag 决定减不减 preopen_mn 就会拿 FY2016 的 12,068 去比 FY2020 的 16,387。
#: 详见口径坑 7。
RENAMED = {'sga_folded_preopen': 'preopen_src'}


def _write(path, head, rows, keycols, optional=()):
    """整表重写，返回本次**新增**的主键列表。

    两条硬规矩：
    · **缺列一律失败**（README 第 2 条）：新表头但凡少了旧表已有的任何一列 → 抛。
      少一列静默写空 = 那一列在页面上变成一条断掉的线，而没有任何人会收到通知。
      唯一豁免是 `RENAMED` 里**明写过**的改名，见那里的注释。
    · 除 `optional` 外任何格子为空 → 抛。同一个理由。

    行尾固定 `\\n`（全仓 CSV 都是纯 LF），字段顺序、行顺序全部确定，
    因此没有新申报时输出**逐字节相同** —— monthly_run.py 的指纹触发器依赖这一点。
    """
    old_head, old_rows = _existing(path)
    if old_head:
        gone = [c for c in old_head if c not in head and RENAMED.get(c) not in head]
        if gone:
            raise CostSecError(f'{os.path.basename(path)} 解析结果缺列 {gone}（旧表有、新表没有），'
                               f'拒绝写入 —— 缺列一律失败，绝不静默写空')
    ki = [head.index(c) for c in keycols]
    opt = {head.index(c) for c in optional}
    for r in rows:
        if len(r) != len(head):
            raise CostSecError(f'{os.path.basename(path)} 行宽 {len(r)} ≠ 表头 {len(head)}: {r}')
        blank = [head[i] for i, c in enumerate(r) if c == '' and i not in opt]
        if blank:
            raise CostSecError(f'{os.path.basename(path)} 行 {r[:2]} 的 {blank} 为空，'
                               f'而这些列不允许为空')
    okeys = set()
    if old_head:
        oi = [old_head.index(c) for c in keycols if c in old_head]
        if len(oi) == len(keycols):
            okeys = {'|'.join(r[i] for i in oi) for r in old_rows}
    added = []
    seen = set()
    for r in rows:
        k = '|'.join(str(r[i]) for i in ki)
        if k in seen:
            raise CostSecError(f'{os.path.basename(path)} 主键重复: {k}')
        seen.add(k)
        if okeys and k not in okeys:
            added.append(k)
    tmp = path + '.tmp'
    with open(tmp, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f, lineterminator='\n')
        w.writerow(head)
        w.writerows(rows)
    os.replace(tmp, path)
    return added


# ═══════════════════════════ 对外接口 ═══════════════════════════

def latest_quarter(cache_dir=None):
    """官方源当前最新的 10-K/10-Q **报告期末日** 'YYYY-MM-DD'。

    只打一个请求（submissions 索引），是「事实闸门」用得起的探针。
    刻意返回日期而不是 "FY26Q3"：财季标签要靠财年区间才推得出来，
    而财年区间在 `series/cost_seg_q.csv` 里 —— 探针不该依赖库内文件。
    """
    fs = [f for f in _submissions(cache_dir) if f['form'] in ('10-K', '10-Q') and f['report']]
    if not fs:
        raise CostSecError('submissions 索引里一篇 10-K/10-Q 都没有')
    return max(f['report'] for f in fs)


def _crosscheck_openings(fy_head, fy_rows, coh_head, coh_rows):
    """两条独立的路各自算「某一年新开了几家仓」，对不上就大声 warn。

    · cost_fy.csv 的 `wh_open_total` = XBRL `NumberOfStores` 的**年度差**（净开店），
      FY_FIRST 那一年是 10-K Item 2 的开业表（见 `_reconcile_openings`）；
    · cost_cohort.csv 里那一年的 `n_whses` = 10-K 图上按开业年份分的队列家数。
    两者来自完全不同的两份披露（一份是 XBRL 标签，一份是手画的图），FY2016-FY2025
    十年逐年相等（29 / 26 / 21 / 20 / 13 / 20 / 23 / 23 / 29 / 24）。

    队列家数取**最早印出这一队列的那份 10-K**，不是最新那份：队列是「印这份 10-K 时
    还在营业」的家数，越晚的矩阵被关店与搬迁削得越多，而净开店数不会追溯变 ——
    离开业年最近的那张图才是最可比的对手。顺带把 FY_FIRST 也纳进来了：
    最新矩阵里 FY2016 已经被折进 "2016 & Before" 那一行，只有 FY2020-FY2024 五份矩阵
    还单列着 2016 队列（五份都是 29 家），而 29 正是 Item 2 开业表给 FY2016 的那个数
    —— 序列第一年那四格因此不是「换个来源硬凑」，是**两条独立的路对上了账**。

    warn 而不 raise：即使取最早的矩阵，关店/搬迁仍可能让某个队列比当年净开店数少，
    那时两者本就该分家。真出这事需要人看一眼再决定，不该让整条流水线 FAIL。
    """
    fi = {c: i for i, c in enumerate(fy_head)}
    ci = {c: i for i, c in enumerate(coh_head)}
    coh_n, coh_src = {}, {}
    for r in sorted(coh_rows, key=lambda r: str(r[ci['vintage']])):
        c = str(r[ci['cohort']])
        if re.fullmatch(r'\d{4}', c) and int(c) not in coh_n:
            coh_n[int(c)] = int(r[ci['n_whses']])
            coh_src[int(c)] = r[ci['vintage']]
    for r in fy_rows:
        y = int(str(r[fi['fy']])[2:])
        net = r[fi['wh_open_total']]
        if net == '' or y not in coh_n:
            continue
        if int(net) != coh_n[y]:
            print(f'WARN: FY{y} 新开仓数两条路对不上 —— XBRL 分国家仓数年度差 {net} 家，'
                  f'{coh_src[y]} 10-K 那张图上 {y} 年队列 {coh_n[y]} 家。'
                  f'关店/搬迁会让队列缩水，属正常分家；但请核一眼是不是解析漂了。',
                  file=sys.stderr)


#: 五张表各自的写盘参数。`optional` 里放的每一列，**留空的理由都必须能从数据本身看出来**：
#:   mdna_*      源里那句话本来就不带数（写进去就是编）
#:   preopen_mn  FY2022 起源里不再单列开办费 —— 同一行的 `preopen_src` 会是 `not-disclosed`
#: `wh_open_*` **不在这里**：FY2016 那四格现在由 Item 2 的开业表补上（见 `_reconcile_openings`），
#: 从此不允许留空。把它们留在 optional 里等于给「第一根柱是空的」发了长期许可证。
_TABLES = {
    'seg': ('cost_seg_q.csv', ('fq', 'scope'), ()),
    'tkt': ('cost_tkt_q.csv', ('fq', 'basis'), ('mdna_tc_tkt', 'mdna_tc_frq')),
    'fy': ('cost_fy.csv', ('fy',), ('preopen_mn', 'mdna_tkt_pct', 'mdna_frq_pct')),
    'cohort': ('cost_cohort.csv', ('vintage', 'cohort', 'fiscal_year'), ()),
    # 回填表**一列都不许空**：它只有七个数，每一个都是盈亏平衡那两条线的直接输入。
    'fybe': ('cost_fy_be.csv', ('fy',), ()),
}


def update(series_dir, cache_dir=None):
    """把 SEC 侧的五张表全部重算并写盘，返回新增主键列表（形如 `seg:FY26Q3|Q`）。

    幂等：没有新申报时五张 CSV 逐字节不变、返回 []。
    **首次创建五张表时也返回 []**（旧表不存在，谈不上「新增了哪几期」）——
    那一次由 monthly_run.py 的内容指纹变化触发重建，报的是 REBUILT 而不是 NEW。

    ═══ 失败语义：**逐表隔离地写，但整体地报错** ═══
    这是想清楚过的，不是图省事，所以把推理留在这里。

    原先各表串在一条直线上，任何一处 raise 都会让**已经解析成功的其余几张**
    一并写不成。这几张表来自互不相干的披露（10-K/10-Q 的 XBRL、8-K 的 EX-99.2、
    10-K 的 Item 2 HTML、10-K 里那张手画的图），一张的版式变化跟另外三张的正确性
    没有任何关系 —— 让开业年份矩阵的一次解析失败把分部收入序列一起摁住，
    是在为「整齐」付真实的代价。

    但**不能就这么降级完事**。本仓第一条规矩是「宁可不发也不发错」（原话在
    `monthly_run.py` 的发布段注释里，README 那份列的是它派生出来的三条硬护栏）；
    `mops_remarks()` 那种「残缺但诚实」的降级之所以站得住，是因为它掉的那条腿
    只喂一句脚注 —— 少一句脚注的页面仍然自洽。开业年份矩阵**喂的是一整张图**，
    它停更而页面照发，读者看到的是一张没有任何标记的过期图，那正是
    README「不出声的失败」的判据：连续失败十天和成功十天，在页面上长得一样。

    所以两件事拆开办：
      · **写盘**逐表隔离 —— 解析成功的表照写，不被别的表连坐；
      · **报错**整体 —— 只要有任何一条腿失败，最后一定 `raise`，
        错误信息里逐条列清「哪张表、为什么」。调用方（monthly_run 的 `cost_sec()`）
        catch 到 CostSecError 就记 FAIL，整轮不发布 —— 「宁可不发也不发错」在**发布**
        这一层完整保住，而 CSV 这一层不做无谓的牺牲。
    绝不允许的是第三种：静默地只写一部分然后报成功。那才是真正的坑。
    """
    filings = _submissions(cache_dir)
    errs, added, built = [], [], {}

    def leg(tag, fn):
        """跑一条腿：解析 + 写盘，失败记账不抛。返回解析结果（失败时 None）。"""
        try:
            head, rows = fn()
        except CostSecError as e:
            errs.append((tag, f'解析失败：{e}'))
            return None
        name, keys, opt = _TABLES[tag]
        try:
            for k in _write(_csv_path(series_dir, name), head, rows, keys, opt):
                added.append(f'{tag}:{k}')
        except CostSecError as e:
            errs.append((tag, f'写盘被护栏挡下：{e}'))
            return None
        return head, rows

    # 表 1 是表 2 的前置：`lab` 既给 MD&A 那条腿定位财季，也给 deck 封面当第二只眼。
    # 所以表 1 挂了就**不写表 2** —— 少了第二只眼的 tkt 表是「认错一季也看不出来」的，
    # 那不是残缺，是可能发错，与上面的降级理由方向相反。
    try:
        seg_head, seg_rows, _years, lab, _fy_of = build_seg_q(cache_dir, filings)
        built['seg'] = leg('seg', lambda: (seg_head, seg_rows))
    except CostSecError as e:
        errs.append(('seg', f'解析失败：{e}'))
        lab = None
    if lab is None:
        errs.append(('tkt', '跳过：表 1（分部收入）没解出来，deck 封面的财季校验失去第二只眼，'
                            '而缺了那只眼的客单表可能整季贴错而毫无痕迹 —— 不写'))
    else:
        # `collect_mdna` 必须**放在 lambda 里面**跑：它自己也会抛（10-Q 正文取不到、
        # 句式认不出来），放在外面就等于在隔离层之外留了一条逃逸路径，
        # 一抛就把 fy / cohort 两张本来好好的表一起带走 —— 正是这次要修掉的那个形状。
        built['tkt'] = leg('tkt', lambda: build_tkt_q(
            cache_dir, filings,
            collect_mdna(cache_dir, filings, {e: lab[(s, e)] for (s, e) in lab}),
            {v: k[1] for k, v in lab.items()}))

    built['fy'] = leg('fy', lambda: build_fy(cache_dir, filings,
                                             collect_mdna_fy(cache_dir, filings)))
    built['cohort'] = leg('cohort', lambda: build_cohort(cache_dir, filings))
    # 回填表与 `fy` 各自独立成腿：两者读的是**两代**元素名（FY_BE_TAGS vs FY_TAGS），
    # 老 10-K 的版式变化跟 FY2016 起那十年的正确性没有关系，反之亦然。
    built['fybe'] = leg('fybe', lambda: build_fy_be(cache_dir, filings))

    # 净开店数的第三条腿（cost_fy × cost_cohort）。两张表都在才做得成；
    # 少了一张就**明说跳过了**，不许让「没做」和「做了且通过」在日志里长得一样。
    if built.get('fy') and built.get('cohort'):
        _crosscheck_openings(*built['fy'], *built['cohort'])
    elif built.get('fy') or built.get('cohort'):
        print('WARN: cost_fy × cost_cohort 的新开仓数交叉核对本轮**没做** —— '
              '两张表里有一张没写成，见下面的失败清单。', file=sys.stderr)

    if errs:
        raise CostSecError(
            f'五张表里 {len(errs)} 张没写成（其余的已按各自的护栏写盘，是完整且正确的）：'
            + '；'.join(f'[{t}] {m}' for t, m in errs))
    return added


# ═════════════ 自测：python3 fetch/cost_sec.py --selftest（不联网）═════════════
#
# 只测三个**会静默出错**的解析器：EX-99.2 的正则、开业年份矩阵的右对齐、
# 分部轴/成员的切换。它们的共同点是坏掉之后 CSV 里仍然是一张形状完好的表，
# 没有异常、没有空值，只是数错了 —— 与 fetch/cost.py `_selftest` 挡的是同一类东西。
# fixture 来源分两类，逐条标清楚（沿用 fetch/cost_release._SELFTEST 的写法）：
#   [原件] 真实申报里逐字符照抄
#   [构造] 没见过的变体，用来证明**判据的方向**，不是声称源长这样

# [原件] 0000909832-26-000046 的 EX-99.2（2026-05-28，FY26Q3）压平后的第 3 页。
_FX_DECK_FY26Q3 = (
    'Supplemental Information Third Quarter FY 2026 Exhibit 99.2 $69.2B 2 +11.6% '
    'Comparable Sales +9.8% Adjusted Comparable Sales1 +6.6% Comparable Traffic '
    '+2.4% Comparable Ticket Segment Reporting - Sales | Q3 Highlights 3 Comp Sales '
    'US Canada Other International Total Company Sales +9.4% +10.7% +11.2% +9.8% '
    'Ticket +7.5% +6.0% +8.1% +7.3% Traffic +1.8% +4.4% +2.9% +2.4% '
    '1 - Excluding impacts from changes in gasoline prices and foreign exchange '
    'Adjusted Comp Sales1 US Canada Other International Total Company '
    'Sales +6.8% +6.2% +5.9% +6.6% Ticket +5.0% +1.7% +3.0% +4.2% '
    'Traffic +1.8% +4.4% +2.9% +2.4%')

# [原件] 0000909832-24-000026 的 EX-99.2（2024-05-30，FY24Q3）—— 只有报告口径那张表。
_FX_DECK_FY24Q3 = (
    '3rd Quarter FY 2024 Supplemental Information 1 Exhibit 99.2 $57.4B Net Sales '
    '+9.1% Growth +6.6% Comparable Sales Comp Sales US Canada Other International '
    'Total Company Sales +6.2% +7.7% +7.7% +6.6% Ticket +0.7% +0.6% +0.3% +0.5% '
    'Traffic +5.5% +7.1% +7.4% +6.1% 2 Q3 Highlights - Financial Performance')

# [构造] 版式改了、Ticket 那一行整体串位一格（把 Traffic 的数抄了过来）。
# 它是本护栏要挡的正主：12 个数一个不少，量级也全都合理。
_FX_DECK_SHIFTED = _FX_DECK_FY24Q3.replace(
    'Ticket +0.7% +0.6% +0.3% +0.5%', 'Ticket +5.5% +7.1% +7.4% +6.1%')

_SELFTEST_DECKS = [
    (_FX_DECK_FY26Q3, 'FY26Q3', ['reported', 'adjusted'], None,
     '[原件] FY26Q3：两套口径都在，且 traffic 两张表逐字相同'),
    (_FX_DECK_FY24Q3, 'FY24Q3', ['reported'], None,
     '[原件] FY24Q3：源里就没有 "Adjusted Comp Sales"，adjusted 必须缺席而不是补零'),
    (_FX_DECK_SHIFTED, None, None, '列串位',
     '[构造] Ticket 行串位 → ticket×traffic 对不上 Sales → 必须抛'),
]

# [原件] FY2025 10-K 那张 "Average Sales Per Warehouse" 图，逐行手抄自申报。
_FX_COHORT_FY25 = [
    ['Average Sales Per Warehouse*'], ['(Sales In Millions)'], ['Year Opened', '# of Whses'],
    ['2025', '24', '192'],
    ['2024', '29', '170', '192'],
    ['2023', '23', '151', '166', '186'],
    ['2022', '23', '150', '158', '179', '201'],
    ['2021', '20', '140', '158', '172', '187', '210'],
    ['2020', '13', '132', '152', '184', '193', '215', '240'],
    ['2019', '20', '129', '138', '172', '208', '216', '226', '242'],
    ['2018', '21', '116', '119', '141', '172', '202', '214', '231', '245'],
    ['2017', '26', '121', '142', '158', '176', '206', '237', '247', '262', '277'],
    ['2016 & Before', '715', '159', '165', '179', '186', '197', '223', '254', '263',
     '274', '287'],
    ['Totals', '914', '159', '163', '176', '182', '192', '217', '245', '252', '260', '272'],
    ['2016', '2017', '2018', '2019', '2020', '2021', '2022', '2023', '2024', '2025'],
    ['Fiscal Year'],
]

# [构造] 把 2017 那一行整体左移一格（少一个值 = 右对齐落到错误的财年上）。
# 单看这一行完全正常。它同时被两道检查看到：值个数 9→8（零容差，`_cohort_check_widths`），
# 以及加权均值对 Totals 差 2.00（`_COHORT_TOL`）。
_FX_COHORT_SHIFTED = [r[:] for r in _FX_COHORT_FY25]
_FX_COHORT_SHIFTED[11] = ['2017', '26', '121', '142', '158', '176', '206', '237', '247', '262']

# [构造] 把 **2020 那一行**（只有 13 家，全表最小的队列）左移一格。
# 这一个是**放宽 _COHORT_TOL 之后专门补的回归**：它让加权均值只差 1.29，
# 也就是说旧的 `>1.0` 抓得到、放到 1.5 之后**均值那道就抓不到了**。
# 现在必须由 `_cohort_check_widths` 那道零容差的抓住（值个数 6→5）。
# 这条 fixture 存在的意义就是钉死「放宽容差没有把小队列串位放过去」。
_FX_COHORT_SHIFTED_SMALL = [r[:] for r in _FX_COHORT_FY25]
_FX_COHORT_SHIFTED_SMALL[8] = ['2020', '13', '132', '152', '184', '193', '215']

# [原件] FY2016 10-K（0000909832-16-000032）Item 2 那张开业表，压平后逐字照抄。
# 序列第一年的净开店数只有这一条路 —— "2016 21 2 6 29 715"。
_FX_OPEN_FY16 = (
    'The following schedule shows warehouse openings for the past five fiscal years and '
    'expected warehouse openings through December 31, 2016 : Openings by Fiscal Year (1) '
    'United States Canada Other International Total Total Warehouses in Operation '
    '2012 and prior 439 82 87 608 608 2013 12 3 11 26 634 2014 17 3 9 29 663 '
    '2015 12 1 10 23 686 2016 21 2 6 29 715 '
    '2017 (expected through 12/31/2016) 5 3 — 8 723 Total 506 94 123 723 '
    '_______________ (1) Net of closings and relocations.')

# [原件] FY2019 10-K（0000909832-19-000019）同一张表。这一份里 Canada 那格印的是破折号，
# 破折号必须读成 0 而不是「没匹配上」—— 读不出来会让 FY2019 那一行整个失败。
_FX_OPEN_FY19 = (
    'net of closings and relocations, and expected openings through December 31, 2019 : '
    'United States Canada Other International Total Total Warehouses in Operation '
    '2015 and prior 480 89 117 686 686 2016 21 2 6 29 715 2017 13 6 7 26 741 '
    '2018 13 3 5 21 762 2019 16 — 4 20 782 '
    '2020 (expected through 12/31/2019) 3 — — 3 785 Total 546 100 139 785')

_SELFTEST_OPEN = [
    (_FX_OPEN_FY16, 2016, (21, 2, 6, 29, 715),
     '[原件] FY2016：序列第一年，XBRL 没有上一年可减，只能靠这张表'),
    (_FX_OPEN_FY19, 2019, (16, 0, 4, 20, 782),
     '[原件] FY2019：Canada 那格是破折号 → 必须读成 0'),
    (_FX_OPEN_FY19, 2016, (21, 2, 6, 29, 715),
     '[原件] 老年份在后来的 10-K 里照印，逐字相同 → 两篇取哪篇都一样'),
    (_FX_OPEN_FY16, 2017, None,
     '[原件] "2017 (expected through …)" 是预告行 → 不许被当成实际开业数'),
    (_FX_OPEN_FY16, 2012, None,
     '[原件] "2012 and prior" 是起始累计行 → 不是某一年的开业数'),
]

# [原件] 分部经营利润的口径断点。三列的来源申报日决定这一年落在断点哪一侧（口径坑 6）。
# 申报日逐字抄自 EDGAR：FY2021 10-K 2021-10-06、FY2022 10-K（重述那篇）2022-10-05。
_FX_RESTATE_FILED = '2022-10-05'
_SELFTEST_SEG_OI_BASIS = [
    ({'op_income_us_mn': ('2021-10-06', '0000909832-21-000014'),
      'op_income_ca_mn': ('2021-10-06', '0000909832-21-000014'),
      'op_income_oi_mn': ('2021-10-06', '0000909832-21-000014')}, SEG_OI_BASIS_PRE, None,
     '[原件] 最后供给方是 FY2021 10-K（早于重述那篇）→ 分部不含股酬'),
    ({'op_income_us_mn': ('2022-10-05', SEG_OI_RESTATE_ACC),
      'op_income_ca_mn': ('2022-10-05', SEG_OI_RESTATE_ACC),
      'op_income_oi_mn': ('2022-10-05', SEG_OI_RESTATE_ACC)}, SEG_OI_BASIS_POST, None,
     '[原件] 最后供给方就是重述那篇本身 → 已是含股酬口径（边界取「含」）'),
    ({'op_income_us_mn': ('2025-10-08', '0000909832-25-000101'),
      'op_income_ca_mn': ('2025-10-08', '0000909832-25-000101'),
      'op_income_oi_mn': ('2025-10-08', '0000909832-25-000101')}, SEG_OI_BASIS_POST, None,
     '[原件] FY2025 10-K 供给 → 含股酬口径'),
    ({'op_income_us_mn': ('2022-10-05', SEG_OI_RESTATE_ACC),
      'op_income_ca_mn': ('2021-10-06', '0000909832-21-000014'),
      'op_income_oi_mn': ('2022-10-05', SEG_OI_RESTATE_ACC)}, None, '来自不同申报',
     '[构造] 三列来源不同 → 判不出口径，必须抛（它们在 10-K 里永远同表列示）'),
    ({'op_income_us_mn': ('2022-10-05', SEG_OI_RESTATE_ACC)}, None, '缺了一部分',
     '[构造] 只有一列有来源 → 必须抛，不许默认成某个口径'),
]

# [原件] 三代分部成员名，各取一个真实见过的 context。
_SELFTEST_SEG = [
    ('Revenues', {'StatementBusinessSegmentsAxis': 'cost:UnitedStatesMember',
                  'ConsolidationItemsAxis': 'us-gaap:OperatingSegmentsMember'}, 'us',
     '[原件] FY2025 10-K：ASU 2023-07 之后的新轴 + 新成员'),
    ('Revenues', {'StatementGeographicalAxis': 'country:CA',
                  'ConsolidationItemsAxis': 'us-gaap:OperatingSegmentsMember'}, 'ca',
     '[原件] FY2017-FY2024：地理轴 + country 成员'),
    ('Revenues', {'StatementGeographicalAxis': 'cost:OtherInternationalOperationsMember'}, 'oi',
     '[原件] FY2011-FY2016：地理轴 + 老 Operations 成员'),
    ('RevenueFromContractWithCustomerExcludingAssessedTax',
     {'StatementGeographicalAxis': 'country:US', 'ProductOrServiceAxis': 'cost:FreshFoodMember'},
     None, '[原件] 美国 × 生鲜：第三根轴 → 必须拒收，否则会覆盖掉真正的「美国」'),
    ('RevenueFromContractWithCustomerExcludingAssessedTax',
     {'ProductOrServiceAxis': 'us-gaap:MembershipMember'}, None,
     '[原件] 会员费：根本没有分部轴 → 不是分部收入'),
    ('OperatingIncomeLoss', {'StatementGeographicalAxis': 'country:US'}, None,
     '[原件] 分部经营利润：元素名不在 SEG_REV_TAGS 里 → 不该被当成收入'),
]

# [原件] 5 篇申报里那句话的 5 种形状，逐字抄自 EDGAR 正文。
_SELFTEST_MDNA = [
    ('Comparable sales were positively impacted by increases of 5% in shopping frequency '
     'and approximately 1% in average ticket.', (1.0, 5.0),
     '[原件] 2025-10-08 10-K（FY2025 全年）：两个数各自带短语'),
    ('Comparable sales were positively impacted by increases of approximately 3% in '
     'shopping frequency and average ticket.', (3.0, 3.0),
     '[原件] 2025-12-17 10-Q（FY26Q1）：一个数被两个短语共用'),
    ('Comparable sales were positively impacted by increases of approximately 4% in average '
     'ticket and 3% in shopping frequency in both the second quarter and first half of 2026.',
     (4.0, 3.0), '[原件] 2026-03-11 10-Q（FY26Q2）：短语顺序反过来'),
    ('Comparable sales were positively impacted by increases of approximately 7% and 5% in '
     'average ticket and 2% and 3% in shopping frequency in the third quarter and first '
     'thirty-six weeks of 2026.', (7.0, 2.0),
     '[原件] 2026-06-03 10-Q（FY26Q3）：本季与前 36 周并排，取前一个'),
    ('Comparable sales increased 6% in the third quarter and first thirty-six weeks of 2025 '
     'and were positively impacted by increased shopping frequency of 5% and an average '
     'ticket increase of less than 1%.', (None, 5.0),
     '[原件] 2025-06-05 10-Q（FY25Q3）：ticket 写的是 "less than 1%"，'
     '没有量化就必须留空 —— 绝不能把 frequency 的 5% 抄过去'),
]


def _selftest():
    bad = 0
    print('── _deck_parse / _deck_guard：EX-99.2 的三行表 ──')
    for text, want_fq, want_basis, want_err, why in _SELFTEST_DECKS:
        try:
            fq, tables = _deck_parse(text, 'SELFTEST')
            got_err = None
        except CostSecError as e:
            fq, tables, got_err = None, None, str(e)
        if want_err:
            ok = got_err is not None and want_err in got_err
        else:
            ok = got_err is None and fq == want_fq and sorted(tables) == sorted(want_basis)
        bad += not ok
        shown = f'抛：{got_err[:44]}…' if got_err else f'{fq} {sorted(tables)}'
        print(f'  {"ok " if ok else "FAIL"} {shown:<52} {why}')
    # 数值本身也要钉住，否则「解出来了」不等于「解对了」
    _fq, t = _deck_parse(_FX_DECK_FY26Q3, 'SELFTEST')
    ok = (t['reported']['Ticket'] == [7.5, 6.0, 8.1, 7.3]
          and t['adjusted']['Ticket'] == [5.0, 1.7, 3.0, 4.2]
          and t['reported']['Traffic'] == [1.8, 4.4, 2.9, 2.4])
    bad += not ok
    print(f'  {"ok " if ok else "FAIL"} {"FY26Q3 十二个数逐个对上申报原文":<46} [原件] 值不只是能解出来，还要解对')

    print('── _cohort_parse：右对齐与 Totals 加权对账 ──')
    try:
        got = _cohort_parse(_FX_COHORT_FY25, 2025)
        d = {c: v for c, _n, v in got}
        # 2017 那一行只有 9 个值，右对齐后是 FY2017..FY2025 —— FY2016 那一格**本来就该没有**
        # （2017 年开的仓在 FY2016 还不存在）。这条断言同时钉住了「右对齐」与「不补零」。
        ok = (d['2025'] == {2025: 192} and 2016 not in d['2017']
              and d['2017'][2017] == 121 and d['2017'][2025] == 277
              and d['2016 & Before'][2016] == 159 and d['Totals'][2025] == 272
              and dict((c, n) for c, n, _ in got)['Totals'] == 914)
    except CostSecError as e:
        ok = False
        print('   ', e)
    bad += not ok
    print(f'  {"ok " if ok else "FAIL"} {"FY2025 矩阵逐格对上手抄的申报":<46} [原件] 914 家、加权均值 272')
    for fx, why in ((_FX_COHORT_SHIFTED, '[构造] 2017 行左移一格 → 必须抛'),
                    (_FX_COHORT_SHIFTED_SMALL,
                     '[构造] 最小队列(13 家)左移一格 → 均值只差 1.29 < 容差，'
                     '必须由零容差的值个数检查抛')):
        try:
            _cohort_parse(fx, 2025)
            ok, msg = False, '没抛'
        except CostSecError as e:
            ok, msg = '串位' in str(e), str(e)[:44] + '…'
        bad += not ok
        print(f'  {"ok " if ok else "FAIL"} {msg:<52} {why}')

    print('── _openings_row：Item 2 开业表（序列第一年的唯一来源）──')
    for text, y, want, why in _SELFTEST_OPEN:
        try:
            got = _openings_row(text, y)
        except CostSecError as e:
            got = f'抛：{e}'
        ok = got == want
        bad += not ok
        print(f'  {"ok " if ok else "FAIL"} {str(got):<26}(期望 {str(want):<18}) {why}')

    print('── _seg_oi_basis：分部经营利润的口径断点（口径坑 6）──')
    for fy_src, want, want_err, why in _SELFTEST_SEG_OI_BASIS:
        try:
            got, got_err = _seg_oi_basis(fy_src, _FX_RESTATE_FILED), None
        except CostSecError as e:
            got, got_err = None, str(e)
        ok = (want_err in got_err) if want_err else (got_err is None and got == want)
        bad += not ok
        shown = f'抛：{got_err[:30]}…' if got_err else str(got)
        print(f'  {"ok " if ok else "FAIL"} {shown:<40} {why}')

    print('── _seg_region：两套轴 / 三代成员 / 第三根轴一票否决 ──')
    for local, dims, want, why in _SELFTEST_SEG:
        got = _seg_region(local, dims)
        ok = got == want
        bad += not ok
        print(f'  {"ok " if ok else "FAIL"} {str(got):<8}(期望 {str(want):<5})  {why}')

    print('── _mdna_numbers：同一句话的五种形状 ──')
    for sent, want, why in _SELFTEST_MDNA:
        got = _mdna_numbers(_mdna_sentence(sent + ' Next sentence.') or sent)
        ok = got == want
        bad += not ok
        print(f'  {"ok " if ok else "FAIL"} {str(got):<16}(期望 {str(want):<14}) {why}')

    total = (len(_SELFTEST_DECKS) + 1 + 3 + len(_SELFTEST_OPEN)
             + len(_SELFTEST_SEG_OI_BASIS) + len(_SELFTEST_SEG) + len(_SELFTEST_MDNA))
    print(f'\n{total - bad}/{total} 通过')
    return bad


if __name__ == '__main__':
    if '--selftest' in sys.argv:
        sys.exit(1 if _selftest() else 0)
    if '--update' in sys.argv:
        for k in update(SERIES, os.path.join(ROOT, 'cache')):
            print('NEW', k)
    else:
        print('latest 10-K/10-Q report date:', latest_quarter(os.path.join(ROOT, 'cache')))
