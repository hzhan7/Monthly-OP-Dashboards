# -*- coding: utf-8 -*-
"""LSEG Post Trade 腿 —— LCH 清算量（SwapClear / ForexClear / RepoClear / CDSClear）。

LCH 是 LSEG「Post Trade」分部里出量的那一半。它没有一份「月度统计工作簿」——
四条服务线各自把数挂在自己的 volumes 页上，**四种完全不同的技术形态**，
而且**三种不同的月度深度、三种不同的发布节奏**。这份 docstring 里
「哪条腿能拿到几个月、口径是单边还是双边」比数字本身重要：
数字抓错下个月就露馅，口径写错可以安静地错三年。

━━ 数据源（2026-08-07 实测，全部走 www.lseg.com，无登录墙）━━

lch.com 已整体 301 到 lseg.com：
    https://www.lch.com/services/swapclear/volumes
      → https://www.lseg.com/en/post-trade/clearing/lch-services/swapclear/volumes
四个 volumes 页都是 Adobe AEM 渲染，页面 HTML 里**没有 <table>**，
数据分三种形态藏着：

  1. SwapClear —— AEM 组件 JSON。页面上每个 DataGrid 带一个
     `data-api-url="…/<component>.datatable.json"`，GET 回来是
     `{"Data":[…], "PublishedDate":…, "PeriodDate":…}`。
     四个页签（Notional Registered / Notional Outstanding / Trades Registered /
     Trades Outstanding）里只有第一个随首屏 HTML 一起下来，其余三个是 AjaxPanel，
     要按页面上的 `data-content-location` 再取一次 `<location>.html` 才能拿到它们的
     `data-api-url`。本模块**逐个发现、不写死 jcr 路径**（AEM 的 section_648981893
     这类节点 id 是内容作者拖控件时生成的，改版必变）。

  2. ForexClear —— S3 预签名 CSV。页面上的下载按钮指向
     `…/block_links_*.presignedurl.json?s3FileKey=forexclear_volumes/monthly/
      ForexClear_Monthly_Activity_and_Open_Interest.csv`，
     该端点 302 到 `lseg-lch-s3-forexclear-prod-euwest2.s3.eu-west-2.amazonaws.com`
     的带签名链接（X-Amz-Expires=70，**70 秒过期**，不能存下来复用）。
     ⚠ 预签名 URL 的 s3FileKey **从页面 href 里解析**，不要自己编 key ——
     编 key 的下场是 403 signature 与 404 交替出现，且分不清是哪种。

  3. RepoClear —— 内联静态 JSON。三张月度表的数据直接写死在首屏 HTML 的
     `data-row-data-static="[{…}]"` 属性里（HTML 实体转义过），没有任何 API。
     三张表长得一模一样（字段都是 Month/Year/LTD/SA），**只能靠紧邻其上的
     <h2>/<h3> 标题区分**，本模块按标题锚定并校验标题里的单位字样。

  4. CDSClear —— **只有当日**。见下面「没拿到的字段」。

发布日证据（本模块每次运行都把它们记进 cache/lseg_lch/source_dates.csv）：
  · SwapClear：datatable JSON 自带 `PublishedDate`（如 "Aug 03, 2026 14:10 UTC"）
  · ForexClear：CSV 末行 `Row Count: 24, Creation Date: 01/08/26 01:31:08`（dd/mm/yy）
    ＋ S3 对象的 HTTP `Last-Modified`
  · RepoClear：**页面上没有任何发布日戳**，只能记「本次抓取时最新月是哪个月」

抓取方式：`urllib.request` 裸奔。实测 `server: Apache` + CloudFront，无 Cloudflare /
Akamai 挑战、无 JS 渲染、无 JA3 指纹拦截（与 SA 那类站不同，curl 与浏览器行为一致）。
**满足无人值守。** 依赖只有标准库。

━━ 实测发布节奏（docs/CRON_WIRING.md §2 的 LAG/EARLY 从这里抄）━━

⚠ **样本期数 = 1**，这是本模块最大的诚实缺口。四条腿的页面都只挂「当前这一份」，
没有任何历史发布日留痕（不像 Euronext 有 22 页新闻列表可以逐月回查、
也不像 Deutsche Börse 的 xls 封面写着 "Created on"）。下面每一行都是
**2026-08-07 一次快照里量到的**，不是分布统计。真正的分布只能靠本模块
每月把 PublishedDate 追加进 cache/lseg_lch/source_dates.csv，攒够 12 期再回来改这段。

    腿          数据月    发布/落地时刻（实测）                    次月第几天
    ─────────────────────────────────────────────────────────────────────
    SwapClear   2026-07   PublishedDate = Aug 03, 2026 14:10 UTC        3
    ForexClear  2026-07   CSV 内部 Creation Date = 2026-08-01 01:31     1（生成）
                          S3 Last-Modified   = Aug 03, 2026 17:05 UTC   3（上线）
                          页面文案 "Published on Aug 03, 2026 16:00 UTC" 3
    RepoClear   2026-05   页面无戳；抓取当日（8/7）最新月仍是 2026-05  ≈ +2 个月
    CDSClear    日频      S3 Last-Modified = Aug 06, 2026 21:40:40 UTC  T+0 当晚

  最早：ForexClear 的文件在次月第 1 天凌晨就生成好了（但要到第 3 天才推上 S3）
  最晚：RepoClear —— 2026-08-07 时最新月还是 2026-05，滞后整整两个月

  建议给 build/roster.py：**闸门只绑 SwapClear + ForexClear**，
      LAG = (4, 4)          次月第 4 天（实测第 3 天 + 1 天余量）
      EARLY_BY = (2, 2)     ⇒ 次月第 2 天开闸
  ⚠ EARLY_BY 必须写成**元组**：monthly_run.py 取值处是
    `EARLY_BY.get(t, (EARLY, EARLY))[1 if qe else 0]`，写成裸整数会 TypeError，
    **崩掉的是整轮 monthly_run，不只是这一家**（fetch/enx.py 已踩过）。
  ⚠ **绝不要把闸门绑到 RepoClear 上** —— 那会让 SwapClear/ForexClear 白等两个月。
    RepoClear 的六列就让它空着，靠 update() 的「只填空不覆盖」在后续月份自动回补，
    这正是那个机制存在的理由。

━━ 历史深度：目标 36 个月，实际拿到 24 ━━

    ForexClear   24 个月（月度 CSV 固定滚 24 行，实测 2024-08 → 2026-07）
    SwapClear    12 个月（四张月度表都固定滚 12 行，实测 2025-08 → 2026-07）
    RepoClear    12 个月（三张月度表都固定滚 12 行，实测 2025-06 → 2026-05）
    CDSClear      0 个月

**官方免费口径下不存在更深的月度历史**，本机核过四条路都是死路：
  · LSEG IR「Trading Statistics」页（https://www.lseg.com/en/investor-relations/
    trading-statistics）只是把这三个 volumes 页**链回去**，自己不带任何 LCH 数据文件；
    页上连 CDSClear 都没列。
  · SwapClear 的 "Volume Data Products" 子页（volumes/volume-data-products）确实提供
    "varying history … as far back as 2011"，但那是**收费数据产品**，走 LSEG Workspace
    订阅，不是公开下载。
  · RepoClear 页上唯一的文件 `…/documents/lch/tables/rcl-monthly-nominal.pdf`
    （15 页、797KB）是**按发债国分的图**，x 轴同样只有 12 个月，且图上没有数据标签。
  · web.archive.org 在本机 Claude 层面是硬禁域名（黑名单，历史 15 次 0 成功），
    没有替代路径 —— 所以「翻旧快照补历史」这条路本模块**不试**。

⇒ 结论：**首月落地就是 24 行**（2024-08 起），其中只有最近 12 个月带 SwapClear 列、
最近 12 个月带 RepoClear 列（且 RepoClear 那 12 个月比 SwapClear 晚两个月结束）。
深度靠时间自己长：本模块每月追加一行，跑满 12 个月后 SwapClear 也就有 24 个月了。
**宁可 24 行真的，不要 36 行编的。**

━━ 没拿到的字段与原因 ━━

**1. CDSClear 月度 —— 一列都没有，只能记流水等未来。**
   官方 CDSClear volumes 页（.../cdsclear/volumes）三块内容全是**当日快照**：
     (a) "Daily volumes – updated daily (end-of-day)"：datatable JSON 里 `Data` 只有
         2 行（EUR / USD），`Date` 全等于最近一个交易日；
     (b) "Volumes since inception"：同样 2 行，是**自开业累计**，同样只给当日那一格；
     (c) 三个可下载 CSV，s3FileKey = `processed/volumes/vbc/latest/
         volumes_by_contract_{single_name,index,swaption}.csv` —— key 里写着 `latest/`，
         实测 single_name 6,445 行、index 179 行、swaption 11 行，`Date` 列**全部是同一天**。
   即：官方不发布 CDSClear 的月度合计，也不留日频归档。按月聚合需要一整月的
   逐日数据，而每次运行只能拿到一天 ⇒ **今天无法为任何一个已结束的月份算出月度值**。
   ⚠ 按 README 铁律「缺列一律失败，绝不静默写 NaN」，本模块**不输出任何 cdsclear_* 列**。
     不是「先写个 0 占位」，不是「用日均×交易日估算」——那是编数。

   本模块能做的只有一件事：`snapshot_cdsclear()` 每次运行把当日三个 vbc CSV 按
   (Date, 产品, 币种) 聚合成 6 行，去重追加进 `cache/lseg_lch/cdsclear_daily.csv`。
   跑满一个完整月（且中间没漏跑）之后，未来的人才有资格加 cdsclear_* 列。
   到那时聚合规则必须写死成：**月度 = 该月所有 Date 的 Gross Notional 直接相加**
   （因为 Gross Notional 是当日新清算量，是流量；Open Interest 是当日末存量，
   **绝不能相加**，只能取月末最后一个交易日那一格）。
   这条腿的失败**不会**中断整次抓取 —— 它一列都不产出，让它把三条真腿拖挂没有道理。

**2. SwapClear / RepoClear 的分币种、分产品明细 —— 有，但不是月度。**
   SwapClear 页下半部分那张分币种表（IRS/OIS/Basis/Zero Coupons/FRAs/VNS/Inflation
   × 28 个币种）字段是 `PERIOD ∈ {Daily, MTD, YTD}` + `BUSINESS_DATE`，
   只覆盖**最近一个交易日**；MTD 是当月至今、YTD 是当年至今，都不是「某个已结束的月」。
   拿它反推月度 = 用两个 YTD 相减，而两次快照隔一个月，中间任何一次重述都会
   落进差值里且无法察觉 ⇒ 不做。
   RepoClear 的「Monthly Volumes by Issuer Country」只有 PDF 图，无数据标签 ⇒ 不做。

**3. RepoClear 的 Total Gross Outstanding —— 是图片，不是数据。**
   页上那块用 ICMA 半年度调查口径，渲染成 `Figure`（图片），没有 data-row-data-static。

━━ 口径坑（按踩坑概率排序）━━

**1. 三条腿的「笔数/名义」双边口径各不相同，横向相加毫无意义。**
   官方原文（本机从各自页面正文读的，不是转述）：
     · ForexClear：CSV 末行写死 "Transaction volumes include the two legs of each
       cleared transaction" ⇒ **双边**。
     · RepoClear："\"Nominal\" is the sum of contracts' bond nominal value cleared
       (double counted)" ⇒ **双边**；trade sides 顾名思义也是边数。
     · SwapClear："Trade counts and notional amounts are representative of the
       SwapClear portfolio of trades following novation to the Clearing House.
       Only the client side of each trade is included in the Client Clearing Volumes."
       ⇒ SERVICE 列是**novation 后**的组合口径；CLIENT 列**只算客户那一边**。
     · CDSClear（虽未入表，写在这里防后人踩）：页面定义段明写
       "counted on a single-sided basis … only one leg is counted for reporting
       purposes"，并自己声明 "not directly comparable with traded volume figures
       published by other venues" ⇒ **单边**，与上面三条腿口径相反。
   ⇒ 本模块把 SERVICE 与 CLIENT 两列都写进 CSV，**不做减法、不算「自营 = 总 − 客户」**。
     novation 口径下这个减法没有定义。跨腿求和（"LCH 总清算量"）同样禁止。

**2. RepoClear 的 LTD 与 SA 是两个法人，不是两条产品线，不要加总画一条线。**
   LCH Ltd（伦敦，€tn 量级 4 左右/月）清英国金边债与部分欧债；
   LCH SA（巴黎，€tn 量级 25 左右/月）清欧元区主权债。两者规模差 6 倍，
   加总后的曲线基本就是 SA 自己。官方的年度表里也是分列给的（外加一个 Total）。
   ⇒ CSV 分两列存，画图分两条线；要合计由 build 层显式做并在图上写明。

**3. SwapClear 的 Outstanding 是月末快照（存量），Registered 是当月流量。**
   官方方法论原文："Outstanding notional & trades are a snapshot as at the end of
   the reporting period." ⇒ `*_outstanding_eom_*` 四列**绝不能做滚动 12 个月合计**。
   列名里带 `outstanding`，build/yoy.py 的 classify() 会判成 STOCK，正确。
   ForexClear 的 `*AtMonthEnd` 同理。

**4. ⚠ build/yoy.py 的 classify() 会把 `repoclear_*_cleared_trade_sides_count`
   误判成 STOCK（存量）。** 它的 _FLOW_PAT 认的词根是 `trades`（复数、整段），
   而官方术语是 "trade sides"，切出来的词是 `trade`（单数）＋ `sides`，两个都不在表里,
   于是落到「兜底存量」。这两列是**当月清算的边数，是流量**。
   ⇒ build 层对这两列必须**显式传 kind=FLOW**，别信 classify() 的默认值。
   本模块不为了迁就正则去改官方术语（叫成 `trades` 会让人以为是笔数而不是边数），
   也不去改 build/yoy.py（禁改清单第 3 条）。
   yoy.py 自己的 docstring 说得很清楚：「classify() 只是给个默认建议，不是权威」。
   顺带一提，误判方向是安全的那一侧（少画一条滚动线，而不是把 12 个月末快照加起来）。

**5. SwapClear 的 `NOTIONAL_USD_TRN` 是官方**四舍五入到 1 位小数**的展示值。**
   实测 2025-12：SERVICE = 164,988,136,262,632 而 NOTIONAL_USD_TRN = "165"。
   本模块入表的是 SERVICE 全精度值除以 1e12，`NOTIONAL_USD_TRN` 只当**对表校验**用
   （容差 0.06 万亿）。用展示值入表会在同比里制造 0.03% 量级的假抖动。

**6. 月份标签三条腿三种写法，且都不带时区/日历口径说明。**
   SwapClear `"Aug'25"`、ForexClear `"Jul/2026"`、RepoClear `{"Month":"May","Year":"2026"}`。
   三者都是**自然月**（ForexClear 页面文案自证："Monthly figures as of COB 07/01/26
   to COB 07/31/26"），没有 4-4-5 之类零售日历，可以直接对齐成 YYYY-MM。

**7. ForexClear 的预签名链接 70 秒过期，且每次请求都换签名。**
   `X-Amz-Expires=70`。所以不能「先把 URL 存下来晚点再下」，也不能把它写进任何
   台账当作可复访的证据 —— 台账里记的应当是 s3FileKey 与 S3 对象的 Last-Modified。

**8. 页面走 CloudFront，`cache-control: max-age=900`。**
   实测同一 URL 二次请求返回 `x-cache: Hit from cloudfront`，带 `?nocache=` 参数
   也照样命中（查询串不在缓存键里）。⇒ **最长可能看到 15 分钟前的页面**。
   对月度任务无所谓；但发布日当天连着跑两次、第二次才看到新月份，是正常现象，不是 bug。
"""
import csv
import datetime
import html as _html
import json
import os
import re
import time
import urllib.parse
import urllib.request

# ══════════════════════════════════════════════════════════════════════
# 常量
# ══════════════════════════════════════════════════════════════════════
HOST = 'https://www.lseg.com'
BASE = HOST + '/en/post-trade/clearing/lch-services'
PAGES = {
    'swapclear': BASE + '/swapclear/volumes',
    'forexclear': BASE + '/forexclear/volumes',
    'repoclear': BASE + '/repoclear/volumes',
    'cdsclear': BASE + '/cdsclear/volumes',
}

_UA = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
       '(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36')

PART = 'lch'
CSV_NAME = 'series/lseg_part_%s.csv' % PART
CACHE_SUB = 'lseg_lch'

# 列名自带单位与币种。顺序 = CSV 列序，按「腿 → 流量在前、存量在后」排。
COLUMNS = [
    # ── SwapClear（OTC 利率互换清算，USD 万亿）──
    'swapclear_notional_registered_usd_tn',
    'swapclear_client_notional_registered_usd_tn',
    'swapclear_trades_registered_count',
    'swapclear_client_trades_registered_count',
    'swapclear_notional_outstanding_eom_usd_tn',
    'swapclear_client_notional_outstanding_eom_usd_tn',
    'swapclear_trades_outstanding_eom_count',
    'swapclear_client_trades_outstanding_eom_count',
    # ── ForexClear（外汇衍生品清算，USD 万亿；双边计）──
    'forexclear_notional_registered_usd_tn',
    'forexclear_trades_registered_count',
    'forexclear_notional_outstanding_eom_usd_tn',
    'forexclear_trades_outstanding_eom_count',
    # ── RepoClear（回购清算，EUR 万亿；双边计。LTD = 伦敦，SA = 巴黎）──
    'repoclear_ltd_nominal_value_eur_tn',
    'repoclear_sa_nominal_value_eur_tn',
    'repoclear_ltd_cash_value_eur_tn',
    'repoclear_sa_cash_value_eur_tn',
    'repoclear_ltd_cleared_trade_sides_count',
    'repoclear_sa_cleared_trade_sides_count',
]

# 每条腿自己的列 —— 用于「这条腿返回的每个月必须齐这些列」的校验
LEG_COLUMNS = {
    'swapclear': COLUMNS[0:8],
    'forexclear': COLUMNS[8:12],
    'repoclear': COLUMNS[12:18],
}

# 官方页面上各腿月度表的固定窗口长度（实测 2026-08-07）。
# 少于这个数不一定是错（官方可能缩窗），但一定要吼一声。
EXPECT_WINDOW = {'swapclear': 12, 'forexclear': 24, 'repoclear': 12}

_MONTHS_ABBR = {m: i + 1 for i, m in enumerate(
    ['jan', 'feb', 'mar', 'apr', 'may', 'jun',
     'jul', 'aug', 'sep', 'oct', 'nov', 'dec'])}
_MONTHS_FULL = {m: i + 1 for i, m in enumerate(
    ['january', 'february', 'march', 'april', 'may', 'june', 'july',
     'august', 'september', 'october', 'november', 'december'])}


class LchFetchError(RuntimeError):
    """源站结构变化 / 下载失败 / 解析结果不完整 / 内部恒等式不成立。

    一律炸掉。宁可整月不更新（线上留着自己的旧数据），也绝不静默写空列或 NaN。
    唯一的例外是 CDSClear 日快照：它一列都不产出，没有理由让它把三条真腿拖挂 ——
    那条路径捕获异常、打警告、继续（见 snapshot_cdsclear）。
    """


# ══════════════════════════════════════════════════════════════════════
# 网络
# ══════════════════════════════════════════════════════════════════════
def _http_get(url, timeout=60, tries=3, pause=2.0, headers=None):
    """取一个 URL 的原始字节，返回 (data, headers)。带退避重试。

    www.lseg.com 前面挂 CloudFront，偶发 502/超时；ForexClear 那条还要跟一次
    302 到 S3（urllib 默认会跟随，S3 那一跳的响应头就是最终返回的 headers，
    Last-Modified 从那里读）。
    """
    last = None
    hdr = {'User-Agent': _UA, 'Accept': '*/*', 'Accept-Language': 'en-US,en;q=0.9'}
    if headers:
        hdr.update(headers)
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers=hdr)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read(), dict(r.headers)
        except Exception as e:                            # noqa: BLE001
            last = e
            if k + 1 < tries:
                time.sleep(pause * (k + 1))
    raise LchFetchError('下载失败 %s: %r' % (url, last)) from last


def _get_text(url, **kw):
    data, hdrs = _http_get(url, **kw)
    return data.decode('utf-8', 'replace'), hdrs


def _get_json(url, **kw):
    txt, _h = _get_text(url, headers={'Accept': 'application/json'}, **kw)
    try:
        return json.loads(txt)
    except ValueError as e:
        raise LchFetchError('%s 返回的不是 JSON（前 200 字：%r）' % (url, txt[:200])) from e


def _cache_dir(cache_dir):
    d = os.path.join(cache_dir, CACHE_SUB)
    os.makedirs(d, exist_ok=True)
    return d


def _save(cache_dir, name, text):
    if cache_dir is None:
        return
    path = os.path.join(_cache_dir(cache_dir), name)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)


def _page(leg, cache_dir):
    """取一个 volumes 页的 HTML 并落 cache。"""
    txt, _h = _get_text(PAGES[leg])
    if len(txt) < 20000:
        raise LchFetchError('%s 页只有 %d 字节，不像正常页面' % (leg, len(txt)))
    _save(cache_dir, 'page_%s.html' % leg, txt)
    return txt


# ══════════════════════════════════════════════════════════════════════
# 小工具
# ══════════════════════════════════════════════════════════════════════
def _norm(s):
    return re.sub(r'\s+', ' ', _html.unescape(str(s or ''))).strip()


def _num(v, where):
    """把 "142,897,509,577,020" / "4.04" / "165" 变成 float。空串 → None。

    不接受任何「看着像数」的兜底：源站给了非数字就是结构变了，必须炸。
    """
    s = _norm(v).replace(',', '')
    if s == '' or s in {'-', 'N/A', 'n/a'}:
        return None
    try:
        return float(s)
    except ValueError as e:
        raise LchFetchError('%s 解析不出数字：%r' % (where, v)) from e


def _month_from_apostrophe(label, where):
    """SwapClear 的 "Aug'25" → '2025-08'。"""
    m = re.fullmatch(r"([A-Za-z]{3,9})'(\d{2})", _norm(label))
    if not m:
        raise LchFetchError('%s 的月份标签认不出来：%r' % (where, label))
    mm = _MONTHS_ABBR.get(m.group(1)[:3].lower())
    if not mm:
        raise LchFetchError('%s 的月份名认不出来：%r' % (where, label))
    return '20%s-%02d' % (m.group(2), mm)


def _month_from_slash(label, where):
    """ForexClear 的 "Jul/2026" → '2026-07'。"""
    m = re.fullmatch(r'([A-Za-z]{3,9})/(\d{4})', _norm(label))
    if not m:
        raise LchFetchError('%s 的月份标签认不出来：%r' % (where, label))
    mm = _MONTHS_ABBR.get(m.group(1)[:3].lower())
    if not mm:
        raise LchFetchError('%s 的月份名认不出来：%r' % (where, label))
    return '%s-%02d' % (m.group(2), mm)


def _month_from_pair(month_name, year, where):
    """RepoClear 的 ("May", "2026") → '2026-05'。"""
    nm = _norm(month_name).lower()
    mm = _MONTHS_FULL.get(nm) or _MONTHS_ABBR.get(nm[:3])
    yr = _norm(year)
    if not mm or not re.fullmatch(r'\d{4}', yr):
        raise LchFetchError('%s 的月份认不出来：%r %r' % (where, month_name, year))
    return '%s-%02d' % (yr, mm)


def _require(rec, cols, month, leg):
    """这条腿返回的每个月都必须齐它自己那几列 —— 少一列就炸（README 铁律 2）。"""
    miss = [c for c in cols if rec.get(c) is None]
    if miss:
        raise LchFetchError('%s 的 %s 少了列 %s —— 官方结构变了，本次不写入'
                            % (leg, month, miss))


# ══════════════════════════════════════════════════════════════════════
# 腿 A：SwapClear —— AEM datatable JSON
# ══════════════════════════════════════════════════════════════════════
_API_RE = re.compile(r'data-api-url="([^"]+)"')
_LOC_RE = re.compile(r'data-content-location="([^"]+)"')


def _datatable_urls(page_html):
    return [_html.unescape(u) for u in _API_RE.findall(page_html)
            if u.endswith('.datatable.json')]


def fetch_swapclear(cache_dir=None):
    """SwapClear 四列流量 + 四列月末存量，返回 {'YYYY-MM': {列: 值}} 与发布日。

    页面上四个页签共用两张底表（Registered / Outstanding），每张表里同时带
    notional 与 trade count，所以「四个页签」其实只有两份数据、且各出现两次。
    本模块**按 JSON 里的 EVENT_TYPE 自认**，不按页签顺序认 —— 页签是内容作者
    拖出来的，顺序随时会变；EVENT_TYPE 是数据自己带的。

    返回 (data, published)，published 形如 'Aug 03, 2026 14:10 UTC'（原样字符串）。
    """
    page = _page('swapclear', cache_dir)
    urls = list(dict.fromkeys(_datatable_urls(page)))
    locs = list(dict.fromkeys(_html.unescape(l) for l in _LOC_RE.findall(page)))

    tables, published, seen = {}, None, set()

    def take(url):
        """取一张 datatable，认出它是 Registered 还是 Outstanding，收进 tables。"""
        nonlocal published
        full = url if url.startswith('http') else HOST + url
        if full in seen:
            return
        seen.add(full)
        d = _get_json(full)
        rows = d.get('Data') or []
        if not rows or 'BUSINESS_MONTH' not in rows[0]:
            return                       # 分币种日表（BUSINESS_DATE），不是我们要的
        kinds = {_norm(r.get('EVENT_TYPE')).lower() for r in rows}
        if len(kinds) != 1:
            raise LchFetchError('SwapClear 一张表里混了多种 EVENT_TYPE：%s' % sorted(kinds))
        kind = kinds.pop()
        if kind not in ('registered notional', 'outstanding notional'):
            raise LchFetchError('SwapClear 出现没见过的 EVENT_TYPE：%r' % kind)
        tag = 'registered' if kind.startswith('registered') else 'outstanding'
        if tag not in tables:
            tables[tag] = rows
            _save(cache_dir, 'swapclear_%s.json' % tag, json.dumps(d, ensure_ascii=False))
        if published is None and d.get('PublishedDate'):
            published = _norm(d['PublishedDate'])

    for u in urls:
        take(u)
    # 首屏只带第一个页签，其余是 AjaxPanel：逐个取 <location>.html 再挖 data-api-url。
    # 两种 EVENT_TYPE 都齐了就停，不为凑齐 14 个 location 白打 14 个请求。
    for loc in locs:
        if len(tables) == 2:
            break
        try:
            frag, _h = _get_text(HOST + loc + '.html')
        except LchFetchError:
            continue                      # 单个页签取不到不致命，下面有齐全性校验兜底
        for u in _datatable_urls(frag):
            take(u)
            if len(tables) == 2:
                break

    missing = {'registered', 'outstanding'} - set(tables)
    if missing:
        raise LchFetchError(
            'SwapClear 页上没找到 %s 表（扫了 %d 个 datatable 端点 + %d 个页签片段）；'
            '官方八成改了页面结构' % (sorted(missing), len(urls), len(locs)))

    data = {}
    for tag, rows in tables.items():
        suffix = '_registered' if tag == 'registered' else '_outstanding_eom'
        for r in rows:
            where = 'SwapClear %s %s' % (tag, r.get('BUSINESS_MONTH'))
            mon = _month_from_apostrophe(r.get('BUSINESS_MONTH'), where)
            svc = _num(r.get('SERVICE'), where + ' SERVICE')
            cli = _num(r.get('CLIENT'), where + ' CLIENT')
            svc_t = _num(r.get('SERVICE_TRADE'), where + ' SERVICE_TRADE')
            cli_t = _num(r.get('CLIENT_TRADE'), where + ' CLIENT_TRADE')
            if None in (svc, cli, svc_t, cli_t):
                raise LchFetchError('%s 有空单元格 —— 官方本月没填全，本次不写入' % where)
            if cli > svc:
                raise LchFetchError('%s 的 CLIENT(%.0f) > SERVICE(%.0f)，口径反了' %
                                    (where, cli, svc))
            # 对表：官方展示列 NOTIONAL_USD_TRN 是四舍五入到 1 位的同一个数
            shown = _num(r.get('NOTIONAL_USD_TRN'), where + ' NOTIONAL_USD_TRN')
            if shown is not None and abs(svc / 1e12 - shown) > 0.06:
                raise LchFetchError(
                    '%s 对表失败：SERVICE/1e12 = %.4f 而官方展示值 = %s（差 %.4f 万亿）'
                    % (where, svc / 1e12, shown, abs(svc / 1e12 - shown)))
            rec = data.setdefault(mon, {})
            rec['swapclear_notional%s_usd_tn' % suffix] = svc / 1e12
            rec['swapclear_client_notional%s_usd_tn' % suffix] = cli / 1e12
            rec['swapclear_trades%s_count' % suffix] = svc_t
            rec['swapclear_client_trades%s_count' % suffix] = cli_t

    for mon, rec in data.items():
        _require(rec, LEG_COLUMNS['swapclear'], mon, 'SwapClear')
    _window_check('swapclear', data)
    return data, published


# ══════════════════════════════════════════════════════════════════════
# 腿 B：ForexClear —— S3 预签名月度 CSV
# ══════════════════════════════════════════════════════════════════════
_FX_HEADER = ['CalendarMonth', 'OutstandingTradesAtMonthEnd',
              'OutstandingNotionalValueAtMonthEnd(USD)',
              'MonthlyTradesRegistered', 'MonthlyNotionalValue(USD)']


def _presigned_links(page_html):
    """页面上所有 presignedurl.json 链接 → {s3FileKey: 完整 URL}。

    key 一律从 href 里解析出来，**绝不自己编** —— 编 key 只会得到 403/404 交替，
    而且分不清是签名错还是名字错。
    """
    out = {}
    for h in re.findall(r'href="([^"]*presignedurl\.json[^"]*)"', page_html):
        h = _html.unescape(h)
        q = urllib.parse.parse_qs(urllib.parse.urlparse(h).query)
        key = (q.get('s3FileKey') or [None])[0]
        if key:
            out[key] = h if h.startswith('http') else HOST + h
    return out


def fetch_forexclear(cache_dir=None):
    """ForexClear 月度流量 + 月末存量，返回 ({'YYYY-MM': {列: 值}}, 发布日证据 dict)。"""
    page = _page('forexclear', cache_dir)
    links = _presigned_links(page)
    hits = [k for k in links
            if 'monthly' in k.lower() and 'activity' in k.lower() and k.endswith('.csv')]
    if len(hits) != 1:
        raise LchFetchError(
            'ForexClear 页上的月度 CSV 链接找到 %d 条（期望 1 条）；页面上的 s3FileKey 有 %s'
            % (len(hits), sorted(links) or '零个'))
    key = hits[0]
    raw, hdrs = _http_get(links[key])
    txt = raw.decode('utf-8-sig', 'replace')
    _save(cache_dir, 'forexclear_monthly.csv', txt)

    rows = list(csv.reader(txt.splitlines()))
    if not rows or [_norm(c) for c in rows[0]] != _FX_HEADER:
        raise LchFetchError('ForexClear CSV 表头变了：%r' % (rows[0] if rows else None))

    data, trailer_count, created = {}, None, None
    for r in rows[1:]:
        if not r or not _norm(r[0]):
            continue
        joined = ','.join(r)
        m = re.search(r'Row Count:\s*(\d+)', joined)
        if m:
            trailer_count = int(m.group(1))
            c = re.search(r'Creation Date:\s*([\d/]+\s+[\d:]+)', joined)
            created = c.group(1).strip() if c else None
            continue
        if len(r) != len(_FX_HEADER):
            continue                       # 末尾那句「双边计」说明，不是数据行
        where = 'ForexClear %s' % _norm(r[0])
        mon = _month_from_slash(r[0], where)
        out_trades = _num(r[1], where + ' OutstandingTradesAtMonthEnd')
        out_notional = _num(r[2], where + ' OutstandingNotionalValueAtMonthEnd')
        reg_trades = _num(r[3], where + ' MonthlyTradesRegistered')
        reg_notional = _num(r[4], where + ' MonthlyNotionalValue')
        if None in (out_trades, out_notional, reg_trades, reg_notional):
            raise LchFetchError('%s 有空单元格 —— 本次不写入' % where)
        data[mon] = {
            'forexclear_notional_registered_usd_tn': reg_notional / 1e12,
            'forexclear_trades_registered_count': reg_trades,
            'forexclear_notional_outstanding_eom_usd_tn': out_notional / 1e12,
            'forexclear_trades_outstanding_eom_count': out_trades,
        }
    if trailer_count is None:
        raise LchFetchError('ForexClear CSV 末尾没有 "Row Count:" 行 —— 文件结构变了')
    if trailer_count != len(data):
        raise LchFetchError('ForexClear CSV 自述 %d 行，实际解析出 %d 个月'
                            % (trailer_count, len(data)))
    for mon, rec in data.items():
        _require(rec, LEG_COLUMNS['forexclear'], mon, 'ForexClear')
    _window_check('forexclear', data)

    evid = {'s3_file_key': key,
            'csv_creation_date': created,          # dd/mm/yy HH:MM:SS，文件自述
            'http_last_modified': hdrs.get('Last-Modified')}
    return data, evid


# ══════════════════════════════════════════════════════════════════════
# 腿 C：RepoClear —— 内联 data-row-data-static
# ══════════════════════════════════════════════════════════════════════
_HEAD_RE = re.compile(r'<h[1-6][^>]*>(.*?)</h[1-6]>', re.S)
_GRID_RE = re.compile(r'<div[^>]*data-rehydratable="DataGridEnterprise"[^>]*>')
_STATIC_RE = re.compile(r'data-row-data-static="([^"]*)"')

# 标题关键字 → (列前缀, 必须在标题里出现的单位字样 或 None)
_RC_TABLES = [
    ('monthly nominal', 'nominal_value', '€tn'),
    ('monthly cash value', 'cash_value', '€tn'),
    ('monthly cleared trade sides', 'cleared_trade_sides', None),
]


def _grids_with_headings(page_html):
    """把页面上每个带内联数据的 DataGrid 与**紧邻其上的标题**配对。

    三张月度表字段完全一样（Month/Year/LTD/SA），页面上没有任何 id 能稳定区分，
    只能靠标题。data-labelled-by-ids 里那串数字是 AEM 生成的，改版必变，不能当锚。
    """
    marks = []
    for m in _HEAD_RE.finditer(page_html):
        marks.append((m.start(), 'H', _norm(re.sub(r'<[^>]+>', ' ', m.group(1)))))
    for m in _GRID_RE.finditer(page_html):
        s = _STATIC_RE.search(m.group(0))
        if s:
            marks.append((m.start(), 'G', _html.unescape(s.group(1))))
    marks.sort()
    out, last_head = [], None
    for _pos, kind, payload in marks:
        if kind == 'H':
            last_head = payload
        else:
            out.append((last_head or '', payload))
    return out


def fetch_repoclear(cache_dir=None):
    """RepoClear LTD/SA 的月度名义、现金额、清算边数，返回 ({'YYYY-MM': {列}}, 证据)。

    额外做一次官方内部恒等式校验：**当年逐月之和 == 年度表里那一年的合计**。
    这既能抓解析错位，也能抓「月表比年表少一个月」的静默滞后（实测 2026-08-07
    月表停在 2026-05，而年表 2026 年 LTD 22.22 / SA 126.67 恰好等于 1-5 月之和，
    说明官方确实只发到 5 月，不是我们漏了）。
    """
    page = _page('repoclear', cache_dir)
    pairs = _grids_with_headings(page)
    if not pairs:
        raise LchFetchError('RepoClear 页上一个内联 DataGrid 都没找到 —— 页面结构变了')

    monthly, yearly = {}, None
    for head, payload in pairs:
        h = head.lower()
        try:
            rows = json.loads(payload)
        except ValueError as e:
            raise LchFetchError('RepoClear「%s」的内联数据不是 JSON' % head) from e
        if not rows:
            continue
        if 'total yearly nominal' in h:
            yearly = rows
            continue
        for keyword, prefix, unit in _RC_TABLES:
            if keyword not in h:
                continue
            if unit and unit.lower() not in h.replace(' ', ''):
                raise LchFetchError(
                    'RepoClear「%s」标题里已经没有单位 %s 了 —— 官方可能换了单位，'
                    '本模块的列名写死 eur_tn，不敢照抓' % (head, unit))
            need = {'Month', 'Year', 'LTD', 'SA'}
            if not need <= set(rows[0]):
                raise LchFetchError('RepoClear「%s」的字段变成 %s' % (head, list(rows[0])))
            for r in rows:
                where = 'RepoClear %s %s %s' % (head, r.get('Month'), r.get('Year'))
                mon = _month_from_pair(r.get('Month'), r.get('Year'), where)
                ltd = _num(r.get('LTD'), where + ' LTD')
                sa = _num(r.get('SA'), where + ' SA')
                if ltd is None or sa is None:
                    raise LchFetchError('%s 有空单元格 —— 本次不写入' % where)
                rec = monthly.setdefault(mon, {})
                unit_sfx = 'eur_tn' if unit else 'count'
                rec['repoclear_ltd_%s_%s' % (prefix, unit_sfx)] = ltd
                rec['repoclear_sa_%s_%s' % (prefix, unit_sfx)] = sa
            break

    if not monthly:
        raise LchFetchError(
            'RepoClear 页上没认出任何一张月度表；页面标题有 %s'
            % [h for h, _p in pairs])
    for mon, rec in monthly.items():
        _require(rec, LEG_COLUMNS['repoclear'], mon, 'RepoClear')
    _window_check('repoclear', monthly)

    note = _yearly_identity(monthly, yearly)
    newest = max(monthly)
    return monthly, {'newest_month_seen': newest, 'yearly_identity': note}


def _yearly_identity(monthly, yearly):
    """当年逐月名义之和 vs 年度表合计。三档：对得上 / 吼一声 / 炸。

    两张表各自四舍五入到 2 位小数，所以允许 0.005×月数 的舍入误差；
    差到「半个月的量」以上说明月表与年表不同步（多半是月表还没更新），
    这时**必须炸**：那意味着我们正准备把一个不完整的最新月当成完整月写进 CSV。
    """
    if not yearly:
        return '年度表没找到，跳过恒等式校验'
    ycol = {}
    for r in yearly:
        yr = _norm(r.get('Year'))
        for k, v in r.items():
            kl = k.lower()
            if 'ltd' in kl:
                ycol.setdefault(yr, {})['ltd'] = _num(v, 'RepoClear 年度表 %s LTD' % yr)
            elif ' sa ' in kl or kl.endswith('sa') or '- sa' in kl:
                ycol.setdefault(yr, {})['sa'] = _num(v, 'RepoClear 年度表 %s SA' % yr)
    year = max(m[:4] for m in monthly)
    if year not in ycol:
        return '年度表里没有 %s 年，跳过恒等式校验' % year
    msgs = []
    for leg in ('ltd', 'sa'):
        col = 'repoclear_%s_nominal_value_eur_tn' % leg
        vals = [monthly[m][col] for m in sorted(monthly) if m.startswith(year)]
        if not vals or ycol[year].get(leg) is None:
            continue
        got, want = sum(vals), ycol[year][leg]
        diff = abs(got - want)
        tol = 0.005 * len(vals) + 0.01
        half = 0.5 * min(vals)
        if diff <= tol:
            msgs.append('%s %s 年 %d 个月合计 %.2f == 年度表 %.2f ✓' %
                        (leg.upper(), year, len(vals), got, want))
        elif diff < half:
            msgs.append('⚠ %s %s 年月合计 %.2f vs 年度表 %.2f（差 %.2f，超舍入容差 %.3f）'
                        % (leg.upper(), year, got, want, diff, tol))
        else:
            raise LchFetchError(
                'RepoClear 恒等式不成立：%s %s 年逐月合计 %.2f，年度表却是 %.2f，'
                '差 %.2f ≥ 半个月的量 %.2f —— 月表与年表不同步，本次不写入'
                % (leg.upper(), year, got, want, diff, half))
    return '；'.join(msgs)


def _window_check(leg, data):
    n, want = len(data), EXPECT_WINDOW[leg]
    if n < want:
        print('[lseg_lch] ⚠ %s 只解析出 %d 个月（实测窗口是 %d 个月）—— '
              '官方可能缩了窗口，或解析漏了行，请人工确认' % (leg, n, want))
    months = sorted(data)
    # 窗口内不许有洞：滚动窗口天然连续，出洞一定是解析错
    cur = months[0]
    for m in months[1:]:
        y, mm = int(cur[:4]), int(cur[5:])
        mm += 1
        if mm == 13:
            y, mm = y + 1, 1
        nxt = '%04d-%02d' % (y, mm)
        if m != nxt:
            raise LchFetchError('%s 的月份序列在 %s 之后跳到了 %s —— 中间缺月，解析有问题'
                                % (leg, cur, m))
        cur = m


# ══════════════════════════════════════════════════════════════════════
# 腿 D：CDSClear —— 只有当日，攒流水，一列都不产出
# ══════════════════════════════════════════════════════════════════════
_CDS_PRODUCTS = ('single_name', 'index', 'swaption')


def snapshot_cdsclear(cache_dir):
    """把当日 CDSClear 三个 vbc CSV 聚合成 (日期, 产品, 币种) 6 行，去重追加进 cache。

    **不产出任何 CSV 列**，理由见模块 docstring「没拿到的字段」第 1 条。
    这里做的唯一一件事是给未来留数据：官方只挂 latest 一天、不留归档，
    今天不开始记，一年后还是零个月。

    未来真要加 cdsclear_* 列时，聚合规则必须是：
      · 月度成交 = 该月所有交易日 gross_notional 直接相加（流量，可加）
      · 月末未平仓 = 该月最后一个交易日的 open_interest（存量，**绝不可加**）
      · 币种不折算：EUR 与 USD 分两组，官方就是分币种给的，折算要引外部汇率
        （fetch/fx.py 有，但那是另一个人的文件，不在本次范围）
      · 覆盖率不足的月份一律不出值：交易日缺一天就少一天的量，那是编数

    返回写进流水的行数（0 表示这次没有新的一天）。失败只打警告不抛异常 ——
    它一列都不产出，没有理由让它把三条真腿拖挂。
    """
    page = _page('cdsclear', cache_dir)
    links = _presigned_links(page)
    rows = []
    for prod in _CDS_PRODUCTS:
        hits = [k for k in links if k.endswith('volumes_by_contract_%s.csv' % prod)]
        if len(hits) != 1:
            raise LchFetchError('CDSClear 页上 %s 的下载链接找到 %d 条' % (prod, len(hits)))
        raw, _h = _http_get(links[hits[0]], timeout=90)
        txt = raw.decode('utf-8-sig', 'replace')
        rdr = csv.DictReader(txt.splitlines())
        agg = {}
        for r in rdr:
            need = ('Date', 'Currency', 'Gross Notional', 'Open Interest',
                    'Number of Transactions')
            if any(c not in r for c in need):
                raise LchFetchError('CDSClear %s CSV 字段变了：%s' % (prod, list(r)))
            k = (_norm(r['Date']), _norm(r['Currency']))
            a = agg.setdefault(k, [0.0, 0.0, 0.0])
            a[0] += _num(r['Gross Notional'], 'CDSClear %s gross' % prod) or 0.0
            a[1] += _num(r['Open Interest'], 'CDSClear %s oi' % prod) or 0.0
            a[2] += _num(r['Number of Transactions'], 'CDSClear %s tx' % prod) or 0.0
        for (d, ccy), (gn, oi, tx) in sorted(agg.items()):
            if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', d):
                raise LchFetchError('CDSClear %s 的 Date 不是 YYYY-MM-DD：%r' % (prod, d))
            rows.append([d, prod, ccy, repr(gn), repr(oi), str(int(tx))])

    path = os.path.join(_cache_dir(cache_dir), 'cdsclear_daily.csv')
    head = ['date', 'product', 'currency', 'gross_notional', 'open_interest',
            'transactions']
    old = []
    if os.path.exists(path):
        with open(path, newline='', encoding='utf-8') as f:
            old = [r for r in list(csv.reader(f))[1:] if r]
    have = {(r[0], r[1], r[2]) for r in old}
    fresh = [r for r in rows if (r[0], r[1], r[2]) not in have]
    if fresh:
        with open(path, 'w', newline='', encoding='utf-8') as f:
            w = csv.writer(f, lineterminator='\n')
            w.writerow(head)
            w.writerows(sorted(old + fresh, key=lambda r: (r[0], r[1], r[2])))
    return len(fresh)


# ══════════════════════════════════════════════════════════════════════
# 对外接口
# ══════════════════════════════════════════════════════════════════════
def fetch_rows(cache_dir=None, with_cdsclear=True):
    """三条腿合成 `[{'month': 'YYYY-MM', <COLUMNS 里的列>: 值 或 None}, …]`，升序。

    月份取三条腿的**并集**，不是交集：ForexClear 有 24 个月而另两条只有 12 个月，
    取交集会白扔一年真数据。并集里某条腿没覆盖到的月份，那几列是 None ——
    落 CSV 时写成空串。**空串 = 官方那个月根本没公开这条腿，不是 0、不是 NaN。**

    与之相对，「某条腿覆盖到了这个月、但少给了它自己的某一列」是结构故障，
    在各腿内部就已经 raise 了（_require）。

    cache_dir 给 None 时不落任何原始文件（只用于快速验证解析逻辑）。
    """
    swap, swap_pub = fetch_swapclear(cache_dir)
    fx, fx_evid = fetch_forexclear(cache_dir)
    repo, repo_evid = fetch_repoclear(cache_dir)

    data = {}
    for leg in (swap, fx, repo):
        for mon, rec in leg.items():
            data.setdefault(mon, {}).update(rec)

    unknown = {c for rec in data.values() for c in rec} - set(COLUMNS)
    if unknown:
        raise LchFetchError('解析出了 COLUMNS 里没有的列：%s' % sorted(unknown))
    empty = [c for c in COLUMNS if all(rec.get(c) is None for rec in data.values())]
    if empty:
        raise LchFetchError('这些列一个月都没抓到值：%s —— 按铁律 2 不写入' % empty)

    rows = []
    for mon in sorted(data):
        row = {'month': mon}
        row.update({c: data[mon].get(c) for c in COLUMNS})
        rows.append(row)

    if cache_dir is not None:
        _record_source_dates(cache_dir, swap, swap_pub, fx, fx_evid, repo, repo_evid)
        if with_cdsclear:
            try:
                n = snapshot_cdsclear(cache_dir)
                print('[lseg_lch] CDSClear 日流水 +%d 行（不产出任何 CSV 列，见 docstring）' % n)
            except Exception as e:                       # noqa: BLE001
                print('[lseg_lch] ⚠ CDSClear 日快照失败（%r）—— 不影响三条真腿，继续' % e)

    print('[lseg_lch] SwapClear %s..%s / ForexClear %s..%s / RepoClear %s..%s'
          % (min(swap), max(swap), min(fx), max(fx), min(repo), max(repo)))
    print('[lseg_lch] RepoClear 恒等式：%s' % repo_evid['yearly_identity'])
    return rows


def _record_source_dates(cache_dir, swap, swap_pub, fx, fx_evid, repo, repo_evid):
    """把这次量到的发布日证据追加进 cache 台账（每腿每个「最新月」一行，去重）。

    刻意**不写 series/source_dates.csv** —— 那是全仓共用的台账，本次 LSEG 是四路
    agent 并行取数，四路同时读改写同一个文件必然互相覆盖。合并由主线程做。
    这份台账同时也是把 docstring 里「样本期数 = 1」变成真分布的唯一途径。
    """
    path = os.path.join(_cache_dir(cache_dir), 'source_dates.csv')
    head = ['leg', 'data_month', 'published', 'evidence', 'observed_on']
    today = datetime.date.today().isoformat()
    new = [
        ['swapclear', max(swap), swap_pub or '',
         'datatable.json 的 PublishedDate 字段', today],
        ['forexclear', max(fx), fx_evid.get('http_last_modified') or '',
         'S3 对象 Last-Modified；CSV 自述 Creation Date=%s；key=%s'
         % (fx_evid.get('csv_creation_date'), fx_evid.get('s3_file_key')), today],
        ['repoclear', max(repo), '',
         '页面无发布日戳；只记本次观测到的最新月。%s' % repo_evid['yearly_identity'], today],
    ]
    old = []
    if os.path.exists(path):
        with open(path, newline='', encoding='utf-8') as f:
            old = [r for r in list(csv.reader(f))[1:] if r]
    have = {(r[0], r[1]) for r in old}
    fresh = [r for r in new if (r[0], r[1]) not in have]
    if not fresh:
        return
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f, lineterminator='\n')
        w.writerow(head)
        w.writerows(old + fresh)
    print('[lseg_lch] 发布日台账 +%d 行 → %s' % (len(fresh), path))


def _fmt(v):
    """写回 CSV。整数写整数，其余用最短往返表示（repr(float)）。

    笔数、边数天生是整数，写成 1023829.0 只会让 CSV 难读；名义额必须保留完整精度 ——
    截成 6 位小数会在跨源核对时制造假差异（enx/db1 同一套写法）。
    """
    if v is None:
        return ''
    f = float(v)
    return str(int(f)) if f.is_integer() and abs(f) < 1e15 else repr(f)


def latest_month(cache_dir=None):
    """官方源当前最新月 'YYYY-MM'，**只看 SwapClear 与 ForexClear**。

    刻意不看 RepoClear：实测它滞后两个月，用它定最新月会让整页白等两个月，
    而 RepoClear 那六列本来就靠「只填空不覆盖」在后续月份自动回补。
    抓不到 / 解析不出来一律抛 LchFetchError，不返回 None 掩盖故障。
    """
    swap, _p = fetch_swapclear(cache_dir)
    fx, _e = fetch_forexclear(cache_dir)
    return min(max(swap), max(fx))


def update(series_dir, cache_dir):
    """把新月份写进 series/lseg_part_lch.csv，返回新增月份列表（升序）。

    幂等保证（README 铁律 3）：
      · 已存在的月份不重复追加；
      · 已经有值的单元格**永不覆盖** —— 官方会重述（RepoClear 的年度表就明显是
        按最新口径重算的），重述不由无人值守任务自动吞进来；
        不一致的格子写进 cache/lseg_lch/restatements.csv 供人工判断；
      · 只在既有行**原本为空**的格子上回补 —— 这正是 RepoClear 滞后两个月的解药：
        先落下只有 SwapClear/ForexClear 的行，两个月后 RepoClear 那六列自动填进去；
      · 什么都没变时未被触碰的单元格是原样字符串搬运 ⇒ 文件字节级不变，重跑返回 []。
    """
    csv_path = os.path.join(series_dir, 'lseg_part_%s.csv' % PART)
    if os.path.exists(csv_path):
        with open(csv_path, newline='', encoding='utf-8') as f:
            raw = list(csv.reader(f))
        header, body = raw[0], [r for r in raw[1:] if r and r[0].strip()]
        if header != ['month'] + COLUMNS:
            raise LchFetchError(
                '%s 的列名与本模块不符；缺 %s，多 %s'
                % (csv_path, [c for c in COLUMNS if c not in header],
                   [c for c in header[1:] if c not in COLUMNS]))
    else:
        header, body = ['month'] + COLUMNS, []
    idx = {name: i for i, name in enumerate(header)}
    have = {r[0]: r for r in body}

    rows = fetch_rows(cache_dir)
    added, filled, restated = [], [], []
    for rec in rows:
        mon = rec['month']
        if mon not in have:
            row = [''] * len(header)
            row[0] = mon
            for c in COLUMNS:
                row[idx[c]] = _fmt(rec.get(c))
            have[mon] = row
            body.append(row)
            added.append(mon)
            continue
        row = have[mon]
        for c in COLUMNS:
            if rec.get(c) is None:
                continue
            new = _fmt(rec[c])
            if not row[idx[c]].strip():
                row[idx[c]] = new
                filled.append((mon, c, new))
            elif row[idx[c]] != new:
                restated.append([mon, c, row[idx[c]], new])

    if restated:
        rp = os.path.join(_cache_dir(cache_dir), 'restatements.csv')
        with open(rp, 'w', newline='', encoding='utf-8') as f:
            w = csv.writer(f, lineterminator='\n')
            w.writerow(['month', 'column', 'in_series_csv', 'on_lseg_site'])
            w.writerows(restated)
        print('[lseg_lch] 官方源与 series 有 %d 处不一致，已写 %s（本模块不覆盖，请人工判断）'
              % (len(restated), rp))

    if not (added or filled):
        return []

    body.sort(key=lambda r: r[0])
    tmp = csv_path + '.tmp'
    with open(tmp, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f, lineterminator='\n')
        w.writerow(header)
        w.writerows(body)
    os.replace(tmp, csv_path)              # 原子替换：中途挂掉不会留下半张表
    if filled:
        print('[lseg_lch] 补空 %d 格：%s' % (len(filled), filled[:12]))
    print('[lseg_lch] %s 现有 %d 行（%s..%s）'
          % (csv_path, len(body), body[0][0], body[-1][0]))
    return sorted(added)


if __name__ == '__main__':
    import sys
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    _series, _cache = os.path.join(_root, 'series'), os.path.join(_root, 'cache')
    if len(sys.argv) > 1 and sys.argv[1] == 'latest':
        print('latest:', latest_month(_cache))
    else:
        _added = update(_series, _cache)
        print('added : %d 个月 %s'
              % (len(_added), (_added[:3] + ['…'] + _added[-3:])
                 if len(_added) > 6 else _added))
