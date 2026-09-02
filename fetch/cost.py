# -*- coding: utf-8 -*-
"""Costco (COST) 月度销售抓取 —— GlobeNewswire 新闻稿。

═══ 源 ═══
GlobeNewswire 上的 Costco 月度销售新闻稿。查找与解析在 `fetch/cost_release.py`
（`find_release` / `curl` / `parse_release`），那份代码原本在 skill「COST月度销售」的
`monthly_update.py` 里、由 skill 与本看板共用；skill 删除时**逐字搬进了本仓库**，
所以总仓现在自包含，不再读 `~/.claude` 的 skills 目录下的任何东西。
（当初共用是为了避免分叉 —— 分叉的表现是「skill 的 PDF 和网页看板对同一个月给出不同的
comp」，最难发现的那种错。skill 没了，分叉的对象也没了。）

curl 通道，不需要 Chrome。

═══ 数据落在哪 ═══
真值就是本仓库的 `series/cost.csv`（原先是 skill 的 `cost_monthly.csv`，本模块只镜像；
skill 删除后镜像的上游没了，历史内容原样成为真值，逐字节未改）。本模块只往它追加，
不改结构、不重排、不重新格式化已有行。

历史行是 pandas 写出来的（`5.0` / `698.0`），本模块新追加的行是 csv.writer 写 int（`5`）。
两种写法并存是既有状态，**别为了统一而重写整表** —— 那会把「本月新增 1 行」淹没在
128 行改动里，review 时根本看不出这个月的数据是什么。

═══ 发布节奏 ═══
每零售月结束后首个周三美东盘后（≈SGT 次日凌晨）。

═══ 口径坑 ═══
1. **4-4-5 零售日历**：零售月为 4 周或 5 周（周日截止），净销售额绝对值不可直接环比。
2. **53 周财年**造成个别 1 月周数与上年同月不同（2018-01 / 2019-01 / 2024-01 / 2025-01）。
3. `parse_release` 只在净销售额句与 comp 表**整体**缺失时抛异常；单个地区行或电商行
   匹配不上（Costco 已经把 E-commerce 改名成 Digitally-Enabled 一次了）只会让那两列缺席，
   而按列名对齐写入会让缺的列静默变 NaN，一路写到公开页面上而全程没有任何报错。
   所以本模块在写 CSV **之前**做缺列检查，缺一列就抛异常。
4. **「搜索页上找不到」有两种，而它们长得一模一样。** `cost_release.find_release`
   认稿子靠 slug 里的字面量 `-{月份}-sales-results`；只要 Costco 换一次措辞
   （改名 E-commerce 那一次说明它会换）或 GNW 换一次链接形状，它就一律返回 None，
   而 None 在本模块里被读成「本月还没发」—— 干净地 break、返回 []、报 NOCHANGE。
   于是**连续坏十天和连续正常十天在日志里一个样**：没有 FAIL、没有连续失败计数、
   断档检查也看不见（它只看已入库月份之间的洞，管不到表尾少一行）。
   现在由 `_crosscheck_search_page` 用一条**独立于 find_release 的宽判据**
   把同一张搜索页再读一遍，两只眼打架就抛。它只在该月已经逾期时才开口，
   理由见 `_CROSSCHECK_AFTER_DAYS`。
"""
import csv
import datetime
import importlib.util
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SERIES = os.path.join(ROOT, 'series')
CSV_NAME = 'cost.csv'


class CostFetchError(RuntimeError):
    """本模块所有失败路径统一抛它，调度器只需 catch 一种。"""


_MOD = None


def _release():
    """加载 fetch/cost_release.py（新闻稿的查找与解析）。

    不用 `import cost_release`：本模块会被 monthly_run.py 用
    spec_from_file_location 加载，那时 fetch/ 根本不在 sys.path 上，
    裸 import 会 ModuleNotFoundError。与 fetch/fee_rates.py 的 _load 同规则。
    """
    global _MOD
    if _MOD is not None:
        return _MOD
    p = os.path.join(HERE, 'cost_release.py')
    if not os.path.exists(p):
        raise CostFetchError(f'找不到解析管道: {p}')
    spec = importlib.util.spec_from_file_location('cost_release', p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _MOD = mod
    return mod


_SD = None


def _source_dates():
    """加载仓库根的 source_dates.py（各家发布日的台账）。同 _release 的理由：
    本模块被 spec_from_file_location 加载时，sys.path 上既没有 fetch/ 也没有仓库根。"""
    global _SD
    if _SD is not None:
        return _SD
    p = os.path.join(ROOT, 'source_dates.py')
    if not os.path.exists(p):
        raise CostFetchError(f'找不到发布日台账模块: {p}')
    spec = importlib.util.spec_from_file_location('source_dates', p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _SD = mod
    return mod


# 稿子自己印的发布时刻。取 <time itemprop="datePublished"> 的**渲染文本**
# （"August 05, 2026 16:15 ET"），不取它 datetime 属性里的 UTC（2026-08-05T20:15:00Z）：
# Costco 是美东盘后发稿，本期两者恰好同日，但只要哪一期晚过 20:00 ET，UTC 就跨到次日，
# 抬头那句「官方发布于」会比稿子自己印的日期整整晚一天。
# 正则里硬要 "ET" 后缀：万一 GNW 哪天换成别的时区渲染，宁可这里匹配不上、这半句缺席，
# 也不要把一个不是 ET 的时刻当 ET 读。
_TIME_RE = re.compile(r'itemprop="datePublished"[^>]*>\s*<time[^>]*>\s*'
                      r'([A-Za-z]+)\s+(\d{1,2}),\s*(\d{4})[^<]*?\bET\b')
# 正文电头 "ISSAQUAH, Wash., Aug.  05, 2026  (GLOBE NEWSWIRE) --"，只当交叉核对用。
# 地名段里允许逗号（"ISSAQUAH, Wash.,"），否则只截得到最后一节 "Wash., Aug. 05, 2026"；
# 长度封在 40 字符，免得非贪婪失败后一路回溯把上一段正文吞进 evidence。
_DATELINE_RE = re.compile(r'([A-Z][A-Za-z.,\' ]{0,40}?,\s*([A-Za-z]+)\.?\s+(\d{1,2}),\s*(\d{4}))'
                          r'\s*\(GLOBE NEWSWIRE\)')


def _month_num(name):
    """'Aug' / 'Aug.' / 'Sept' / 'March' → 1-12；认不出返回 None（AP 缩写与全称混用）。"""
    n = name.strip('.').lower()
    if len(n) < 3:
        return None
    for i, full in enumerate(_release().MONTHS):
        if full.lower().startswith(n):
            return i + 1
    return None


def _release_date(html, url):
    """从新闻稿本身读出发布日，返回 (YYYY-MM-DD, evidence)；读不出返回 (None, None)。

    电头必须**从 articleBody 容器往后**找第一条：整页底部还嵌着上两期稿子的电头
    （本期页面里就有 "July 08" 与 "June 03" 两条 featured news），全页搜第一个匹配
    今天碰巧是对的，GNW 改一次版面顺序就会串到上一期的发布日上，而串期后的日期
    看上去完全正常，没人会发现。

    两处对不上就返回 None：那说明页面结构已经变了，这种时候猜哪个对没有意义。
    """
    m = _TIME_RE.search(html)
    if not m:
        print('WARN: 新闻稿里没找到 <time itemprop="datePublished"> 的 ET 文本，本月不记发布日',
              file=sys.stderr)
        return None, None
    mo = _month_num(m.group(1))
    if not mo:
        print(f'WARN: 发布日月份名认不出 {m.group(1)!r}，本月不记发布日', file=sys.stderr)
        return None, None
    date = f'{m.group(3)}-{mo:02d}-{int(m.group(2)):02d}'

    i = html.find('itemprop="articleBody"')
    dl = _DATELINE_RE.search(html[i:]) if i >= 0 else None
    dl_mo = _month_num(dl.group(2)) if dl else None
    if not dl_mo or f'{dl.group(4)}-{dl_mo:02d}-{int(dl.group(3)):02d}' != date:
        print(f'WARN: 正文电头与 datePublished 对不上（电头 {dl.group(1) if dl else "未找到"!r}，'
              f'datePublished {date}），本月不记发布日', file=sys.stderr)
        return None, None

    shown = re.sub(r'\s+', ' ', m.group(0).rsplit('>', 1)[-1]).strip()
    dateline = re.sub(r'\s+', ' ', dl.group(1)).strip()
    return date, (f'GlobeNewswire 稿 {url.rsplit("/", 1)[-1]} 的 '
                  f'<time itemprop="datePublished"> 渲染文本 "{shown}"；'
                  f'正文电头 "{dateline} (GLOBE NEWSWIRE)" 一致')


def _csv(series_dir=None):
    return os.path.join(series_dir or SERIES, CSV_NAME)


def _read_csv(series_dir=None):
    path = _csv(series_dir)
    if not os.path.exists(path):
        raise CostFetchError(f'series/cost.csv 不存在: {path}')
    with open(path, newline='', encoding='utf-8') as f:
        rows = list(csv.reader(f))
    if len(rows) < 2:
        raise CostFetchError('series/cost.csv 没有数据行')
    return rows[0], rows[1:]


# 报告口径 ⇄ 除油汇口径 的五组配对。两套口径同时出现在同一张 comp 表里，
# 解析器要靠「表 1 = 报告、表 2 = 调整」把它们分开。
_CALIBER_PAIRS = [('us_r', 'us_a'), ('ca_r', 'ca_a'), ('oi_r', 'oi_a'),
                  ('tc_r', 'tc_a'), ('ec_r', 'ec_a')]


def _guard_two_calibers(key, rec, url):
    """两套口径完全相同 → 判定解析走错分支，拒绝入库。

    **现有的缺列护栏挡不住这一类**：2026-07 那期 GlobeNewswire 改了表格 markup
    （每个值列重复一遍，(8,4) 变 (8,6)），于是「表 1/表 2」的月表判据全部落空，
    控制流掉进为 2 月合并稿准备的那个分支，从**同一张表**里取 toks[0] 当报告、
    toks[1] 当调整 —— 而那两个 token 是被复制的同一列。
    结果是 16 列一列不缺、只是「除油汇核心 comp」被写成了报告口径，
    Exhibit 里最关键的那条线整条错，而全程不抛异常、静默入库、直接上公开页。

    判据的依据是实测而不是直觉：series/cost.csv 里 103 个有完整两套口径的月份，
    **五个地区同时相等的一次都没有**（最多 3 个地区相等，仅出现过 1 次）。
    所以「全部相等」是解析走错分支的可靠信号，不会误伤真实数据。
    """
    same, avail = [], []
    for a, b in _CALIBER_PAIRS:
        va, vb = rec.get(a), rec.get(b)
        if va is None or vb is None:
            continue
        avail.append(a)
        if va == vb:
            same.append(f'{a}={va}')
    if len(avail) >= 4 and len(same) == len(avail):
        raise CostFetchError(
            f'{key} 的报告口径与除油汇口径逐个相等（{", ".join(same)}）—— '
            f'几乎可以确定是 comp 表解析走错了分支（历史 103 个月里从未出现过全部相等）。'
            f'拒绝入库。请核对新闻稿的表格结构：{url}')


def _next_month(ym):
    y, m = int(ym[:4]), int(ym[5:7])
    return (y + 1, 1) if m == 12 else (y, m + 1)


# ─────────────────── GlobeNewswire 搜索页对账（第二只眼）───────────────────
# 防的是口径坑 4 那个等号：「find_release 返回 None」= 「本月还没发」。
# 形状照 fetch/cboe.py 的 _crosscheck_report_month 与 fetch/ice.py 的
# _crosscheck_workbook_month：拿一条**独立于解析器（这里是发现器）的外部判据**
# 对账，且刻意 raise 而不是 print warn —— warn 之后状态仍是 NOCHANGE，等于没有护栏。

#: 逾期多少天之后，这道对账才允许开口。
#: 节奏取自本文件开头「发布节奏」（零售月结束后首个周三，build/roster.py 的 LAG 也是 7 天），
#: 这里放 3 倍余量。三件事都靠它，少一件这道护栏就会误伤健康的日子：
#:   · 正常发布窗口（月末后 1-7 天）里「搜索页上没有本月的稿」是**最普通的一天**，
#:     在这几天里对页面下任何结论都是抢跑；
#:   · Costco 偶尔会先发一条「将于 X 日公布 Y 月销售」的预告，预告与正稿只差几天。
#:     过了逾期线，正稿要么早就入库了（那就轮不到再探这个月）、要么是真出事了；
#:   · 健康年份里 update() 根本走不到逾期这一天 —— 稿子一入库，monthly_run 的
#:     not_due 闸门就把这一家整个跳过。所以健康年份里这道对账**一个网络请求都不多打**。
_CROSSCHECK_AFTER_DAYS = 21

#: 搜索页要比「已入库最新月的发布日」还往前翻这么多天，哨兵②才敢说「这期在页面上没了」。
#: 一个完整发布周期（月度）再加余量：第一页迟早会把老稿翻下去，那时候「找不到」
#: 说的是分页，不是稿子没了 —— 没有这道日期窗，GNW 改一次每页条数就是每天一条 FAIL。
_PAGE_REACH_MARGIN_DAYS = 31

#: slug 里月份名与 "sales" 最多隔几个词，才算「这条稿说的是那个零售月」。
#: 今天的写法 `...-reports-july-sales-results` 隔 0 个词，改写成
#: `...-reports-retail-sales-for-july` 隔 1 个 —— 3 个词的余量够容忍改写，
#: 又不至于把 slug 里随便哪个位置的月份名都算成零售月。
_MONTH_NEAR_SALES = 3

#: 搜索页上的稿件链接。**刻意比 find_release 那条松**：不要求 `.html` 结尾、
#: 允许语言段与 GNW 的数字 id 段、相对与绝对 URL 都收。
#: 松是这一条的职责决定的 —— 它回答「页面上到底有什么」，不回答「哪一条是我要的」。
_LINK_RE = re.compile(r'href="([^"]*?/news-release/(\d{4})/(\d{2})/(\d{2})/[^"]+)"', re.I)


def _slug_month(slug):
    """这条 slug 说的是哪个零售月（1-12）；不像月度销售稿就返回 None。

    两条判据都刻意不认字面量：slug 里要有 "sales" 那个词，且离它
    `_MONTH_NEAR_SALES` 个词以内的**第一个**月份名就是零售月。月份名走 `_month_num`，
    全称与 AP 缩写（Aug / Sept）都认。

    取第一个而不是全部，是因为一条 slug 里可能出现两个月份名
    （预告稿 `...-august-sales-results-on-september-2`），而 GNW 的 slug 由标题生成，
    零售月总排在前面。取全部会让预告稿同时算作两个月，凭空多出一次误报。
    """
    toks = re.findall(r'[a-z]+', slug.lower())
    sales = [i for i, t in enumerate(toks) if t.startswith('sales')]
    if not sales:
        return None
    for i, t in enumerate(toks):
        if min(abs(i - j) for j in sales) > _MONTH_NEAR_SALES:
            continue
        mo = _month_num(t)
        if mo:
            return mo
    return None


def _search_links(html):
    """搜索页 → [(发布日 'YYYY-MM-DD', 零售月 1-12 或 None, slug)]，按页面顺序，去重。

    去重是必要的：同一条稿在 GNW 的列表里通常出现两次（缩略图一次、标题一次），
    不去重会让下面「页面上有几条」的判据凭空翻倍。
    """
    out, seen = [], set()
    for href, y, m, d in _LINK_RE.findall(html):
        slug = href.split('?')[0].split('#')[0].rstrip('/').rsplit('/', 1)[-1].lower()
        if (y, m, d, slug) in seen:
            continue
        seen.add((y, m, d, slug))
        out.append((f'{y}-{m}-{d}', _slug_month(slug), slug))
    return out


def _first_day_after(ym):
    """零售月 ym 结束之后的第一天 'YYYY-MM-01'。

    与 source_dates.record 里那道「发布日必须严格晚于数据月结束」用的是同一条线，
    所以它不是这里现编的口径，是仓库对「什么样的日期可能是这个月的发布日」的既有断言。
    """
    y, m = _next_month(ym)
    return f'{y}-{m:02d}-01'


def _crosscheck_due(key, today=None):
    """{key} 逾期到可以对搜索页下结论了吗。理由见 `_CROSSCHECK_AFTER_DAYS`。"""
    t = today or datetime.date.today().isoformat()
    return t >= (datetime.date.fromisoformat(_first_day_after(key))
                 + datetime.timedelta(days=_CROSSCHECK_AFTER_DAYS)).isoformat()


def _judge_search_page(links, key, last, pub):
    """三条判据的本体：不碰网络、不碰磁盘、不看日历，因此可以直接喂 fixture 自测。

    参数：`links` 是 `_search_links` 的结果，`key` 是这次没找到的零售月，
    `last` 是已入库的最新月，`pub` 是 `last` 那期的发布日（台账里没有就传 None）。

    ① 页面上一条稿件链接都没有 → 抛。一张 >=3000 字节、curl 拿得回来的搜索页
       却一条 `/news-release/` 都没有，是链接形状变了（换路径、换 JS 壳），
       不是 Costco 不发稿了。
    ② 页面上有链接、却一条月度销售稿都认不出来 → 抛。这一条才是挡住**下一种没见过的
       变体**的那道（① 与 ③ 只认识已经见过的形状）。判据刻意钉死在「一条都没有」，
       **永远不要改成「至少 N 条」或按月份逐个期待** —— GNW 改一次每页条数、或者
       Costco 某个月多发几条别的稿，就会把销售稿挤下第一页，那时「少于 N 条」
       会在完全健康的源上每天 FAIL 一次。
    ③ 目标月的稿子明明在页面上，find_release 却没认出来 → 抛。这是本护栏的正主：
       slug 措辞一改，find_release 的字面量就失效，而这里的宽判据仍认得，两只眼
       打架 = 发现器坏了。日期下限用 `_first_day_after`：预告稿（「将于 X 日公布 Y 月
       销售」）发在零售月结束之前，够不着这条线，不会被当成正稿。
    ④ 已入库的最新月在页面上认不出来 → 抛。这是从**我们已知该有什么**的反侧查，
       与 ①②③ 的盲区不重叠（照 fetch/msci.py update() 哨兵②）。
       但它必须过日期窗：只有当页面还翻得到比 `last` 发布日更早的销售稿时，
       「找不到 last」才说明这期没了；否则说明的只是第一页翻过去了。
    """
    if not links:
        raise CostFetchError(
            f'{key}: GlobeNewswire 搜索页取回来了，页面上却一条 /news-release/ 链接都没有。'
            f'能拿到页面还认不出链接，说明链接形状变了（换路径 / 换成 JS 壳），'
            f'不是 Costco 停发。拒绝当成「本月还没发」静默结束。请人工看一眼 '
            f'{_release().SEARCH}，然后修 cost_release.find_release 与本模块的 _LINK_RE。')
    sales = [(d, mo, s) for d, mo, s in links if mo]
    if not sales:
        raise CostFetchError(
            f'{key}: 搜索页上有 {len(links)} 条稿件链接，却一条月度销售稿都认不出来'
            f'（页面上实际长这样：{[s for _, _, s in links[:3]]}）。'
            f'两种可能，都得人来看一眼、不能静默：slug 的写法整体变了，'
            f'或者 Costco 不再按月发销售稿了。源：{_release().SEARCH}')

    y, m = int(key[:4]), int(key[5:7])
    floor = _first_day_after(key)
    # 发布年校验与 find_release 保持逐字一致（12 月的稿发在次年 1 月，见 cost_release 坑 4），
    # 否则两只眼的口径不同，会为了一条 find_release 本来就该跳过的链接吵起来。
    hit = [(d, s) for d, mo, s in sales
           if mo == m and int(d[:4]) in (y, y + 1) and d >= floor]
    if hit:
        mname = _release().MONTHS[m - 1].lower()
        raise CostFetchError(
            f'{key}: 搜索页上有 {len(hit)} 条像是这个零售月销售稿的链接'
            f'（{hit[0][0]} {hit[0][1]}），find_release 却一条都没认出来。'
            f'它认的是 slug 里的字面量 "-{mname}-sales-results"，所以最可能是措辞改了。'
            f'拒绝报「还没发」—— 那会让 COST 从此每天干净地 NOCHANGE 下去。'
            f'请核对 {_release().SEARCH} 后改 cost_release.find_release。')

    if not pub:
        return                       # 台账里没有 last 的发布日，日期窗立不起来，闭嘴
    if any(mo == int(last[5:7]) and int(d[:4]) in (int(last[:4]), int(last[:4]) + 1)
           for d, mo, _ in sales):
        return                       # 已入库的最新月还在页面上，页面与我们对得上
    reach = (datetime.date.fromisoformat(pub)
             - datetime.timedelta(days=_PAGE_REACH_MARGIN_DAYS)).isoformat()
    if min(d for d, _, _ in sales) > reach:
        return                       # 第一页已经翻过 last 那期了，「找不到」说的是分页
    raise CostFetchError(
        f'我们手里有 {last} 这期（台账记的发布日 {pub}），搜索页却认不出它 —— '
        f'而页面上最老的销售稿是 {min(d for d, _, _ in sales)}，比 {reach} 还早，'
        f'说明第一页还没翻过去。这不是分页，是这期在页面上的形状变了。'
        f'本次不写入，请人工核对 {_release().SEARCH}。')


def _crosscheck_search_page(mu, key, last, series_dir):
    """`find_release` 说「{key} 还没发」时，把同一张搜索页交给第二只眼再读一遍。

    只在 `key` 已经逾期时才真的去读（见 `_CROSSCHECK_AFTER_DAYS`）：正常发布窗口里
    「页面上没有本月的稿」是最普通的一天，那几天里读页面只会制造误报，而且这一层
    还替健康年份省掉了这次多余的请求 —— 健康年份根本走不到逾期那一天。
    """
    if not _crosscheck_due(key):
        return
    try:
        html = mu.curl(mu.SEARCH)
    except Exception as e:
        raise CostFetchError(
            f'{key} 已逾期 {_CROSSCHECK_AFTER_DAYS} 天以上，想再核一遍 GlobeNewswire '
            f'搜索页却取不上来（{mu.SEARCH}）：{e}') from e
    _judge_search_page(_search_links(html), key, last,
                       _source_dates().lookup(series_dir or SERIES, 'cost', last))


def latest_month(cache_dir=None):
    """官方源当前最新的**已发布**零售月 'YYYY-MM'。

    Costco 不提供「最新月是几月」的接口，只能拿下一个月去 GlobeNewswire 试探：
    查得到新闻稿就说明已发布。查不到不是故障，是还没发。
    """
    _, rows = _read_csv()
    last = rows[-1][0]
    mu = _release()
    y, m = _next_month(last)
    try:
        url = mu.find_release((y, m))
    except Exception as e:
        raise CostFetchError(f'GlobeNewswire 查询失败: {e}') from e
    key = f'{y}-{m:02d}'
    if not url:
        # 「查不到 = 还没发」这个等号在这里同样成立不了，理由与判据全在
        # _crosscheck_search_page，别只给 update() 加护栏 —— 两处的洞是同一个。
        _crosscheck_search_page(mu, key, last, SERIES)
        return last
    return key


def update(series_dir, cache_dir=None):
    """把官方还没入库的零售月写进 series/cost.csv，返回新增月份列表。

    幂等：已有的月份不重复追加，重复跑第二遍返回 []。
    解析结果缺任何一个已有列 → 抛异常，绝不静默写 NaN。
    """
    path = _csv(series_dir)
    head, rows = _read_csv(series_dir)
    have = {r[0] for r in rows}
    last = rows[-1][0]
    mu = _release()
    added = []

    # 一次最多补 6 个月：正常只差 1 个月，差很多说明前面漏跑了很久，
    # 与其一口气拉一年不如让它跑几次、每次都能看到进度。
    for _ in range(6):
        y, m = _next_month(last)
        key = f'{y}-{m:02d}'
        if key in have:
            last = key
            continue
        try:
            url = mu.find_release((y, m))
        except Exception as e:
            raise CostFetchError(f'GlobeNewswire 查询 {key} 失败: {e}') from e
        if not url:
            # 「还没发」与「发现机制坏了」在这里长得一模一样（口径坑 4）。
            # break 之前先交给第二只眼分辨一次；分辨不出来的日子它自己会闭嘴。
            _crosscheck_search_page(mu, key, last, series_dir)
            break                                  # 还没发，正常结束
        try:
            html = mu.curl(url)                    # 留住整页：发布日也要从这份 HTML 里读
            rec, ym = mu.parse_release(html)
        except Exception as e:
            raise CostFetchError(f'解析 {key} 失败 ({url}): {e}') from e
        got = f'{ym[0]}-{ym[1]:02d}'
        if got != key:
            raise CostFetchError(f'月份不符: 期望 {key} 实得 {got} ({url})')
        missing = [c for c in head[1:] if c not in rec]
        if missing:
            raise CostFetchError(f'{key} 解析缺列 {missing} ({url})')
        _guard_two_calibers(key, rec, url)
        # 照抄既有行尾：csv.writer 默认写 \r\n，而 cost.csv 是纯 LF，
        # 用默认值会往全 LF 的文件里插一条孤立的 CRLF 行。
        with open(path, 'rb') as f:
            term = '\r\n' if b'\r\n' in f.read(4096) else '\n'
        with open(path, 'a', newline='', encoding='utf-8') as f:
            csv.writer(f, lineterminator=term).writerow([key] + [rec[c] for c in head[1:]])
        added.append(key)
        have.add(key)
        last = key
        # 发布日记在 CSV 那一行**确实写出去之后**：台账是给「已入库的那个月」用的，
        # 记在失败路径上就会出现「页面说官方 X 日发布，而那个月的数据根本不在图上」。
        sdate, ev = _release_date(html, url)
        if sdate:
            _source_dates().record(series_dir or SERIES, 'cost', key, sdate, ev)
        # 读不出来不抛：数据本身已经落库，重跑走不到这里，抛异常只会把一次成功的摄入
        # 记成失败；缺的只是抬头那半句话，页面会自动省掉。_release_date 已经打过 WARN。

    return added


# ─────────────── 自测：python3 fetch/cost.py --selftest（不联网）───────────────
# 只测搜索页对账那三条判据。值得单独测，是因为它们的两种错法都不响：
# 判据太松 → 又回到「静默停更」；判据太紧 → 在完全健康的源上每天 FAIL 一次，
# 而每天假一次的警报，人很快就学会无视了（README 说红点时用的是同一句话）。
#
# **必须离线**，但理由不是「取不到源」——2026-09-02 查明 GNW 一直是通的，从前记的
# 「curl 000」是我们自己顶着假 Chrome UA 招来的（见 cost_release.curl() 上方那段）。
# 离线是**故意**的：判据要盯的恰恰是「源变成了什么样」，拿当天的线上页面当输入，
# 就只能证明「今天这一页能过」，源一改判据就跟着漂，回归测试等于没有。
# 所以这里没有「跑通了就算过」的选项，只能拿 fixture 逐条钉。
# fixture 的来源分两类，标签里写清楚，别混为一谈（沿用 cost_release._SELFTEST 的写法）：
#   [原件]  真实见过的，逐字符照抄
#   [构造]  没见过的变体，按「如果源这么改会怎样」构造 —— 它们证明的是判据的方向，
#           不是「源真的长这样」
_SELFTEST_SLUGS = [
    # (slug, 期望零售月, 说明)
    ('costco-wholesale-corporation-reports-july-sales-results', 7,
     '[原件] 2026-07 那期，slug 在 series/source_dates.csv 的 evidence 里逐字记着'),
    ('costco-wholesale-corporation-reports-retail-sales-for-july', 7,
     '[构造] 措辞改写，月份跑到 sales 后面 —— find_release 的字面量在这里失效，本判据仍认得'),
    ('costco-wholesale-corporation-reports-august-2026-sales-results', 8,
     '[构造] 中间插了年份，字面量 "-august-sales-results" 同样失效'),
    ('costco-wholesale-corporation-to-report-august-sales-results-on-september-2-2026', 8,
     '[构造] 预告稿有两个月份名，取前一个（零售月）；它由日期下限挡住，不由本函数挡'),
    ('costco-wholesale-corporation-reports-fourth-quarter-and-fiscal-year-2026-operating-results',
     None, '[构造] 季报稿：没有 sales 这个词'),
    ('costco-wholesale-corporation-declares-quarterly-cash-dividend', None,
     '[构造] 股息稿'),
    ('costco-wholesale-corporation-announces-sales-reporting-dates-for-fiscal-2027', None,
     '[构造] 全年发布日程稿：有 sales，附近却没有月份名 —— 它不该顶替一条真的销售稿'),
]

_HEALTHY = [('2026-08-05', 'costco-wholesale-corporation-reports-july-sales-results'),
            ('2026-07-16', 'costco-wholesale-corporation-declares-quarterly-cash-dividend'),
            ('2026-07-01', 'costco-wholesale-corporation-reports-june-sales-results'),
            ('2026-06-03', 'costco-wholesale-corporation-reports-may-sales-results')]

_SELFTEST_PAGES = [
    # (items, 路径前缀, key, last, pub, 期望报错里的片段 or None, 说明)
    (_HEALTHY, '/news-release', '2026-08', '2026-07', '2026-08-05', None,
     '**今天的真实状态**：2026-07 已入库、2026-08 还没发 —— 一个字都不许响'),
    (_HEALTHY + [('2026-09-02',
                  'costco-wholesale-corporation-reports-retail-sales-for-august')],
     '/news-release', '2026-08', '2026-07', '2026-08-05', '没认出来',
     '正主：8 月的稿就在页面上，措辞改了所以 find_release 认不出 → 必须响'),
    (_HEALTHY, '/press-release', '2026-08', '2026-07', '2026-08-05', '链接都没有',
     'GNW 换了链接路径 → 页面还在、一条都认不出 → 必须响'),
    ([('2026-07-16', 'costco-wholesale-corporation-declares-quarterly-cash-dividend'),
      ('2026-05-29', 'costco-wholesale-corporation-announces-quarterly-earnings-call')],
     '/news-release', '2026-08', '2026-07', '2026-08-05', '销售稿都认不出来',
     '整页一条月度销售稿都没有 → 要么写法全变、要么 Costco 停发，都得人来看'),
    (_HEALTHY + [('2026-09-02',
                  'costco-wholesale-corporation-reports-august-sales-results')],
     '/news-release', '2026-09', '2026-08', '2026-09-02', None,
     '源真的还没发 9 月（8 月刚发完、老稿都在）→ 不许响'),
    (_HEALTHY + [('2026-08-20',
                  'costco-wholesale-corporation-to-report-august-sales-results-on-september-2')],
     '/news-release', '2026-08', '2026-07', '2026-08-05', None,
     '预告稿发在 8 月内，够不着「发布日不早于零售月结束」那条线 → 不许响'),
    ([('2026-11-04', 'costco-wholesale-corporation-reports-october-sales-results'),
      ('2026-10-01', 'costco-wholesale-corporation-reports-september-sales-results')],
     '/news-release', '2026-08', '2026-07', '2026-08-05', None,
     '第一页已经翻过 2026-07 那期（页面最老的销售稿都比它的发布日新）→ 判不了，闭嘴'),
    ([('2026-07-01', 'costco-wholesale-corporation-reports-june-sales-results'),
      ('2026-06-03', 'costco-wholesale-corporation-reports-may-sales-results')],
     '/news-release', '2026-08', '2026-07', '2026-08-05', '却认不出它',
     '页面还翻得到 6 月、5 月，偏偏 7 月那期不见了 → 不是分页，是形状变了'),
    ([('2026-07-01', 'costco-wholesale-corporation-reports-june-sales-results'),
      ('2026-06-03', 'costco-wholesale-corporation-reports-may-sales-results')],
     '/news-release', '2026-08', '2026-07', None, None,
     '同上，但台账里没有 2026-07 的发布日 → 日期窗立不起来 → 闭嘴'),
]

_SELFTEST_DUE = [
    # (key, 当天, 期望, 说明)
    ('2026-08', '2026-08-26', False, '今天：8 月零售月还没过完，正常窗口都没开始'),
    ('2026-08', '2026-09-02', False, '正稿发布当天：还在正常窗口内，不开口'),
    ('2026-08', '2026-09-21', False, '逾期线前一天'),
    ('2026-08', '2026-09-22', True, '月末后第 21 天：开口'),
    ('2026-12', '2027-01-22', True, '12 月稿发在次年 1 月，跨年也照算'),
]


def _fixture_page(items, prefix):
    """按 GNW 的链接形状拼一张搜索页。每条稿排两遍（缩略图 + 标题），顺带测去重。

    路径中段（数字 id / 语言段）是[形状]，末段 slug 才是判据看的东西。
    """
    out = []
    for i, (d, slug) in enumerate(items):
        href = f'{prefix}/{d[:4]}/{d[5:7]}/{d[8:]}/31284{i:02d}/0/en/{slug}.html'
        out.append(f'<a href="{href}"><img src="x.jpg"></a><a href="{href}">标题</a>')
    return '<html><body>' + ''.join(out) + '</body></html>'


def _selftest():
    bad = 0
    print('── _slug_month：slug → 零售月 ──')
    for slug, want, why in _SELFTEST_SLUGS:
        got = _slug_month(slug)
        ok = got == want
        bad += not ok
        print(f'  {"ok " if ok else "FAIL"} {str(got):>5} (期望 {str(want):>5})  {why}')

    print('── _crosscheck_due：什么时候才允许开口 ──')
    for key, today, want, why in _SELFTEST_DUE:
        got = _crosscheck_due(key, today)
        ok = got == want
        bad += not ok
        print(f'  {"ok " if ok else "FAIL"} {key} @ {today} → {got!s:5} (期望 {want})  {why}')

    print('── _judge_search_page：三条判据 ──')
    for items, prefix, key, last, pub, want, why in _SELFTEST_PAGES:
        links = _search_links(_fixture_page(items, prefix))
        try:
            _judge_search_page(links, key, last, pub)
            got = None
        except CostFetchError as e:
            got = str(e)
        ok = (got is None) if want is None else (got is not None and want in got)
        bad += not ok
        shown = '不响' if got is None else f'响了：{got[:40]}…'
        print(f'  {"ok " if ok else "FAIL"} {shown:<52} {why}')

    total = len(_SELFTEST_SLUGS) + len(_SELFTEST_DUE) + len(_SELFTEST_PAGES)
    print(f'\n{total - bad}/{total} 通过')
    return bad


if __name__ == '__main__':
    if '--selftest' in sys.argv:
        sys.exit(1 if _selftest() else 0)
    print('latest:', latest_month())
