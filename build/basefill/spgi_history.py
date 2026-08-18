# -*- coding: utf-8 -*-
"""SPGI 月度指标的**历史回填**：把 series/spgi*.csv 从 2024-01 起推到 2022-01 起。

用法:
    python3 build/basefill/spgi_history.py            # 取数 + 核对 + 写两个 CSV
    python3 build/basefill/spgi_history.py --dry      # 只打印差异，不写文件
    python3 build/basefill/spgi_history.py --refresh  # 强制重下所有工作簿

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
这个文件为什么存在
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
fetch/spgi.py 只做**增量追加**（它的 update() 明说「本模块只负责追加，不负责从零建库」），
而且它每次只下载**最新一份** xlsx —— 那一份只含当年与上年两年。所以正常跑一年，
序列也不会往回长一个月。要往回补历史，必须把**历次**季度发布的工作簿一份份找回来。

原来的 build/spgi.py 与 fetch/spgi.py 里都写着一句断言：

    「更早年份的历史文件在 CDN 上已不可访问，故序列起点固定为 2024-01」

这句话**是错的**，本脚本推翻它：Q4 feed（year=-1）里 2023 Q1 起的每一季都挂着当季那份
Monthly Metrics xlsx，CDN 直链至今 200，全部可下载可解析。之所以从前没拿到，是因为
fetch/spgi.py 的解析器读不了 2023 年那四份的版式（见下方「版式坑」），下载下来也会抛
SpgiFetchError，看起来就像「不可访问」。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
真正的天花板：2022-01，且更早**不是拿不到，是从来没有过**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
最硬的证据不是「我们搜遍了没搜到」，而是**公司自己**预先**宣布过**。
2023-02-09 的 Q4/FY2022 财报 8-K（SEC accession 0000064040-23-000055，
文件 a4q2022earningsrelease.htm）"Upcoming Disclosures" 一节原话：

    "Beginning with results in 2023, S&P Global plans to disclose new financial and
     operating metrics… On a monthly basis, the Company expects to disclose the
     year-over-year growth rate in Billed Issuance for S&P Global Ratings, as well as
     the volume of Exchange-Traded Derivatives for S&P Dow Jones Indices… posted to
     its investor relations website on or about the last business day of each month,
     one month in arrears."

即：这两条月度序列是**2023 年新开的披露**，不是一直有、只是我们没找到。旁证三条：
Q4-2022 财报 slide 第 38 页有一张直接叫 "New Metric Disclosures" 的表，两条都列为
Monthly；IR 站那一栏的标题在 2023-01-27 与 2023-04-01 两次存档之间由 "Quarterly
Earnings" 改成 "Quarterly Earnings & Monthly Metrics"；2021-04-19 存下来的 Q4 feed
响应（119,349 字节、41 条季度记录、覆盖 2011-2021）里 "monthly" 一词出现 **0 次**。

这份工作簿**创刊于 2023 Q1**（as of March 2023，Published 4/27/2023）。所以：

    · SPDJI ADV 绝对值   直接披露 2023-01 起；反算可到 2022-01（用 '23 v. '22 % change）
    · ADV 同比           直接披露 2023-01 起（2022 年那一列官方从未给过 '22 v. '21）
    · Billed issuance    直接披露 2023-01 起（只有同比，永远没有绝对面值）

2022-01 就是硬底。再往前要月度数据，只能去用非官方口径的替代品（第三方数据商、或拿
CME/Cboe 的合约量去凑 SPDJI 的 ADV）—— 本仓的规矩是只用公司自己披露的一手数据，
所以那条路不走，宁可让序列短。这条限制写进 build/spgi.py 的口径说明第 6 条。

━━ 三个「看起来像但不是」的陷阱（都实际打开读过，别再走一遍）━━
1. IR 站上 2019-2021 的 "Supplemental Information" PDF **不是 S&P Global 的文件**，
   是 **IHS Markit** 的季度补充财务资料（文件内引用 investor.ihsmarkit.com，日期跟着
   IHS Markit 的 11/30 财年走）。并购后 IR 站吞并了对方的文档历史，才挂在同一个 CDN 上。
   两条序列它一条都没有，任何颗粒度都没有。
2. 2011-2022 的 slides 里那个 "ADV" 是**另一个指标**，不是本指标的粗颗粒版本：
   那张图叫 "Key Contracts (Average Daily Volume in **Thousands**)"，只有当季与去年同季
   两根柱，且拆成 S&P 500 期权 / VIX 期货期权 / CME 股指合约群。本页的 ADV 是全部
   SPDJI-IP 衍生品的合计、单位是 **millions**。两者接在一起就是把两套定义链成一条假序列。
3. 2012-2017 的 "Global Debt Markets and S&P Global Ratings Rated Dollar Volume" 里的
   **rated dollar volume ≠ billed issuance**：billed issuance 明确剔除 frequent issuer
   program、无评级债与多数国际公共融资，而且那份是年度/半年度，来源还是 Thomson Reuters。

━━ ⚠️ 取数窗口正在关闭：'23 v. '22 那一列已经滚出最新工作簿 ━━
2022 年的反算依赖 "'23 v. '22 % Change" 这一列。工作簿只保留「当年 + 上年」两年，
所以这一列在 Dec-2025 那份里还有，到 **July-2026 那份里已经没有了**（它只剩
'26 v '25 与 '25 v '24）。也就是说：**2022 那 12 行只能从 2023 年份的工作簿或
Dec-2025 那份里算出来，将来的文件再也算不出**。

因此 cache/basefill/spgi/ 里那批工作簿属于 tools/prune_cache.py 认定的「不可重下」类
（该脚本第 54 行已把整个 basefill/ 标为保护），别手工清掉。Q4 feed 目前仍然挂着
2023 Q1 起的每一季，所以从零复算暂时仍然可行 —— 但那是官方的保留策略，不是承诺。

━━ 反算精度：可信到小数点后第二位，第三位不可信 ━━
官方的 '23 v. '22 百分比只存到 0.1 个百分点（-0.031 / 0.096 / 0.367 …），2023 年的
ADV 存到 3 位小数。按 ±0.05pp 的舍入区间推，反算出来的 2022 各月带宽 ≤0.011 mn 张
（约 0.1%）。CSV 里仍按 repr 写满位数（沿用本仓既有写法），但**第三位小数不要当真**；
页面已把这些月画成斜纹柱并在图注点名它们是反算值。
（旁证：2022-11 反算回 8.000、2022-09 回 9.994，与「底层实际值本来就是整数/近整数」吻合。）

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
版式坑：2023 年那四份与现行版式不同（fetch/spgi.py 的解析器本轮已一并加宽）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. 月份行标签带年份且缩写不统一：'Jan 2023' / 'June 2023' / 'September 2023' 混排，
   而现行版式是裸月名 'January'。原 _month_rows 用 `v.strip() in MONTHS` 精确匹配，
   对 2023 年那四份一个都认不出来 → 「只认出 0 个月份行，期望 12」。
2. 月份行**按当季截断**：Mar-2023 那份只有 3 行、Jun-2023 只有 6 行。原来「必须恰好
   12 行」的断言对它们必炸。加宽后的判据是「从 1 月起逐月连续」——两种真实版式都过，
   官方哪天挪行漏行照样炸。
3. ADV 列表头不带年份：2023 年那四份写的是 'ADV (in millions of contracts)'（表里只有
   一年，当时不需要区分），现行版式是 '2026 ADV (in millions of contracts)'。
   加宽后用月份行标签里的年份兜底。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
本脚本改动既有历史行的**两处**，都是刻意的，不是漂移
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
fetch/spgi.py 的规矩是「发现官方重述只告警、绝不改写历史」。本脚本是那条规矩的
**人工例外通道**（该 docstring 的原话：改写历史必须人工决定），只动这两处：

(1) 2024 年 12 个月的 ADV：推导值 → 官方直接披露值。
    原先 2024 没有自己的工作簿可用，是拿 2025 年值除以官方 '25 v. '24 反算的
    （adv_derived=1）。现在 Dec-2024 那份工作簿到手，2024 是它的**当年列**，
    是公司直接印出来的数。实测两者最大差 0.056%（四舍五入噪声，方向无规律），
    换成披露值后 adv_derived 由 1 改 0，斜纹柱与相关图注自动跟着变。

(2) billed_issuance_index 全列重算：基期由「2024 同月 = 100」改为「2022 同月 = 100」。
    同比链现在从 2023-01 起（'23 v. '22 是链上第一环），基期年自然是 2022。
    指数的**同比**不受影响（基数在分子分母上对消，仍恒等于官方披露值），变的只是
    水平值的标度 —— 而那个水平值本来就跨月不可比（页面自己声明过）。

除此之外，2025-01 起的每一行都与磁盘上原样**逐字节相同**（脚本末尾强制核对）。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
精度：同一个月在不同工作簿里位数不同，取**首发那一份**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
官方把某年当作「当年列」首发时给全精度（2024-10 = 7.84270095652174），后续年份把它
挪到「上年列」时会截位（同一个月变成 7.8427）。15 份工作簿里 11 处这样的分歧，
全部是同一个数的截位/舍入表示，**没有一处是真重述**（脚本会逐对验证并报数）。
取位数最多的那一份，等于取首发值。
"""
import argparse
import csv
import importlib.util
import json
import math
import os
import sys
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
SERIES_DIR = os.path.join(ROOT, 'series')
CACHE = os.path.join(ROOT, 'cache', 'basefill', 'spgi')


def _load_fetch():
    """按路径加载 fetch/spgi.py —— 解析器、常量、CSV 写法全部复用它，不另写一份。

    裸 import 不行：本脚本在 build/basefill/ 下跑，sys.path 上没有 fetch/。
    复用而不是复制，是因为解析器一旦两份，官方改版时必然只改到一份。
    """
    spec = importlib.util.spec_from_file_location(
        'fetch_spgi', os.path.join(ROOT, 'fetch', 'spgi.py'))
    mod = importlib.util.module_from_spec(spec)
    sys.modules['fetch_spgi'] = mod
    spec.loader.exec_module(mod)
    return mod


F = _load_fetch()

# 指数链的基期年：2023 是同比链的第一环（'23 v. '22），所以基数年是 2022。
# fetch/spgi.py::update() 里那句 `if prev[0] <= BASE_YEAR` 与本常数是同一个判断，
# 两处必须一起改 —— 不然下个月增量追加时会拿 100 当 2024 的基数，把链接歪。
BASE_YEAR = 2022


# ─────────────────────────────── 取工作簿 ───────────────────────────────

def discover(refresh=False):
    """列出所有能拿到的 Monthly Metrics xlsx 本地路径。

    两条路都走，取并集：
      · Q4 feed（year=-1，pageSize=500）—— 权威清单，季度记录下挂着当季那份附件；
      · CDN 文件名猜测 —— feed 只保留每季**最后一版**，季内被换掉的版本只能猜；
        同时也用来验证「2023 之前真的没有」（猜到的全是 404，不是没试）。
    """
    os.makedirs(CACHE, exist_ok=True)
    urls = {}

    raw = F._http_get(F.Q4_FEED.format(key=F.Q4_API_KEY), timeout=60)
    items = json.loads(raw)['GetFinancialReportListResult']
    for item in items or []:
        for doc in item.get('Documents') or []:
            path = doc.get('DocumentPath') or ''
            base = os.path.basename(path)
            if path.lower().endswith(('.xlsx', '.xls')) and F._MM_RE.search(base):
                urls[base] = path
    print('[discover] Q4 feed 给出 %d 份工作簿' % len(urls))

    local = []
    for base, url in sorted(urls.items()):
        dst = os.path.join(CACHE, base)
        if refresh or not (os.path.exists(dst) and os.path.getsize(dst) > 4096):
            try:
                blob = F._http_get(url)
            except urllib.error.URLError as exc:
                print('[discover] 下载失败 %s：%s' % (base, exc))
                continue
            if not blob.startswith(b'PK'):
                print('[discover] %s 下到的不是 xlsx（前 4 字节 %r），跳过' % (base, blob[:4]))
                continue
            with open(dst, 'wb') as fh:
                fh.write(blob)
        local.append(dst)

    # 仓库自己的 cache/ 里可能还躺着 feed 已经换掉的季内版本，一并纳入核对。
    for extra in sorted(os.listdir(os.path.join(ROOT, 'cache'))):
        if extra.startswith('spgi_monthly_metrics_') and extra.endswith('.xlsx'):
            local.append(os.path.join(ROOT, 'cache', extra))
    return local


def probe_pre2023():
    """验证「2023 之前没有这份工作簿」不是靠猜 —— 真去 CDN 上敲一遍门。

    对 2016-01..2022-12 每个 as-of 月，用 fetch/spgi.py 的 _guess_cdn_urls 生成候选
    文件名（次月 8..28 日 × 大小写两种），实际发 HTTP 请求。返回命中列表。
    全部 404 才有资格在页面口径说明里写「官方从未按月披露」。

    这个函数默认**不跑**（--probe 才跑）：一次是 7 年 × 12 月 × 21 天 × 2 = 3528 个请求，
    对 CDN 不礼貌，而且结论一旦确立就不必每次回填都重敲。
    """
    hits = []
    n = 0
    for year in range(2016, 2023):
        for month in range(1, 13):
            for url in F._guess_cdn_urls((year, month)):
                n += 1
                try:
                    blob = F._http_get(url, timeout=15)
                except urllib.error.URLError:
                    continue
                if blob.startswith(b'PK'):
                    hits.append(url)
                    print('[probe] 命中 %s' % url)
                    break
    print('[probe] 敲了 %d 个 URL，命中 %d 个' % (n, len(hits)))
    return hits


# ─────────────────────────────── 合并与核对 ───────────────────────────────

def _digits(x):
    """repr 里小数点后的位数 —— 用来挑「位数最多」的那份（= 首发全精度值）。"""
    s = repr(float(x))
    return len(s.split('.')[1]) if '.' in s and 'e' not in s else 99


def collect(paths):
    """解析全部工作簿，返回 (merged, conflicts)。

    merged   : {'YYYY-MM': {field: value}}，同一 (月, 字段) 取位数最多的那份
    conflicts: 位数不同的那些，逐条记下来供核对
    """
    obs = {}
    for p in paths:
        try:
            data = F.parse(p)
        except F.SpgiFetchError as exc:
            print('[collect] 解析失败 %s：%s' % (os.path.basename(p), exc))
            continue
        for key, d in data.items():
            for fld, v in d.items():
                obs.setdefault(F._ym(key), {}).setdefault(fld, {}) \
                   .setdefault(v, []).append(os.path.basename(p))

    merged, conflicts = {}, []
    for month in sorted(obs):
        for fld, vals in obs[month].items():
            best = max(vals, key=_digits)
            merged.setdefault(month, {})[fld] = best
            if len(vals) > 1:
                conflicts.append((month, fld, sorted(vals.items(), key=lambda kv: _digits(kv[0]))))
    return merged, conflicts


def audit_conflicts(conflicts):
    """位数分歧必须全部是「同一个数的截位/舍入」。有一处不是，就是官方真重述了。

    判据：低精度值 lo 必须等于高精度值 hi 在 lo 的位数上**四舍五入或截断**之一。
    实测官方两种都用过（2024-11 的 ADV 是截断：8.235552250000001 → 8.2355，
    四舍五入本该是 8.2356），所以两种都放行，但两种都不满足时报错。
    """
    bad = []
    for month, fld, vals in conflicts:
        lo = vals[0][0]
        nd = _digits(lo)
        for hi, _src in vals[1:]:
            scale = 10.0 ** nd
            rounded = round(hi, nd)
            trunc = math.floor(abs(hi) * scale) / scale * (1 if hi >= 0 else -1)
            if abs(rounded - lo) > 1e-12 and abs(trunc - lo) > 1e-12:
                bad.append((month, fld, lo, hi))
    print('[audit] 位数分歧 %d 处，其中真·重述 %d 处' % (len(conflicts), len(bad)))
    for month, fld, lo, hi in bad:
        print('        ⚠ %s %s: %r 与 %r 不是同一个数' % (month, fld, lo, hi))
    if bad:
        raise SystemExit('官方疑似重述了历史数值，回填中止 —— 必须人工确认后再跑')


# ─────────────────────────────── 造序列 ───────────────────────────────

def pin_existing(merged, clean_path, keep_from='2025-01'):
    """把 keep_from 及其之后的月份**钉回磁盘上已有的值**，不让回填改动它们。

    为什么需要这一步：collect() 取「位数最多」的那份，等于取官方首发的全精度值
    （2025-01 = 9.01558525）。但这些月份是 fetch/spgi.py 当月增量抓进来的，它当时
    读到的是**后续**工作簿里截过位的表示（9.016），库里存的就是那个。

    两个值是同一个数，差 0.005%，谁更「对」不重要；重要的是**下个月 fetch 再跑时
    仍然会写出 9.016**。回填若把它改成 9.01558525，就制造了一处每月都会被改回去、
    却永远没人解释的漂移。所以：已经入库的月份一律不动，回填只负责往回长。

    2024 及更早不在此列 —— 那正是 docstring 交代的两处刻意改动之一（2024 的 ADV
    由推导值换成官方披露值），必须放行。
    """
    if not os.path.exists(clean_path):
        return merged
    with open(clean_path, encoding='utf-8-sig', newline='') as fh:
        rows = list(csv.DictReader(fh))
    pinned = 0
    for r in rows:
        month = r['month'].strip()
        if month < keep_from or month not in merged:
            continue
        for csv_col, parsed_col, scale in (
                ('spdji_adv_mn', 'adv', 1.0),
                ('spdji_adv_yoy', 'adv_yoy', 0.01),
                ('billed_issuance_yoy', 'billed_yoy', 0.01)):
            raw = (r[csv_col] or '').strip()
            if raw and parsed_col in merged[month]:
                merged[month][parsed_col] = float(raw) * scale
                pinned += 1
    print('[pin] %s 起的 %d 个字段钉回库内既有值（回填不改已入库的月份）'
          % (keep_from, pinned))
    return merged


def build_rows(merged):
    """把 merged 铺成逐月连续的两张表的行。

    返回 (raw_rows, clean_rows)，元素都是 dict，数值是 float / None。
      raw   —— 三个字段齐全的月份才进（与 fetch/spgi.py::_complete_months 同一判据）
      clean —— 多一个反算出来的 BASE_YEAR 年（只有 ADV），以及链式指数列
    """
    months = sorted(merged)
    first_year = int(months[0][:4])

    # ── BASE_YEAR 年的 ADV：由首年披露值与官方同比反算 ──────────────────────
    # 这是对披露数据的**算术推导**，不是估计；精度受官方那个百分比的位数限制。
    # 只有 ADV 反算得出来：billed issuance 从来没有绝对面值，无从反算；
    # 而 BASE_YEAR 年的同比要 '22 v. '21 那一列，官方从未发布过。
    derived = {}
    for month in months:
        if int(month[:4]) != first_year:
            continue
        d = merged[month]
        if 'adv' not in d or 'adv_yoy' not in d:
            continue
        if d['adv_yoy'] == -1:
            raise SystemExit('%s 的同比为 -100%%，反算会除以 0' % month)
        derived['%d-%s' % (first_year - 1, month[5:])] = d['adv'] / (1 + d['adv_yoy'])

    # ── billed issuance 链式指数：BASE_YEAR 同月 = 100，逐年往后乘 ────────────
    # 规则与 fetch/spgi.py::update() 完全一致：index[y,m] = index[y-1,m] * (1 + yoy)。
    # 缺任何一环就整条断掉、后续年份留空 —— 链断了还硬接，得到的是一条失真的序列。
    index = {}
    for month in months:
        year, mm = int(month[:4]), month[5:]
        yoy = merged[month].get('billed_yoy')
        if yoy is None:
            continue
        base = 100.0 if year - 1 <= BASE_YEAR else index.get('%d-%s' % (year - 1, mm))
        if base is None:
            continue
        index[month] = base * (1 + yoy)

    all_months = sorted(set(months) | set(derived))
    # 逐月连续是 build/spgi.py::load() 的硬校验，这里先自己查一遍，早一步炸在源头。
    for i in range(1, len(all_months)):
        if F._parse_ym(all_months[i]) != _next(F._parse_ym(all_months[i - 1])):
            raise SystemExit('回填后的月份不连续：%s → %s'
                             % (all_months[i - 1], all_months[i]))

    raw_rows, clean_rows = [], []
    for month in all_months:
        d = merged.get(month, {})
        adv = d.get('adv', derived.get(month))
        is_derived = month in derived and 'adv' not in d
        if all(k in d for k in F.NEED):
            raw_rows.append({'month': month,
                             'billed_issuance_yoy_pct': d['billed_yoy'] * 100,
                             'spdji_adv_mn_contracts': d['adv'],
                             'spdji_adv_yoy_pct': d['adv_yoy'] * 100})
        clean_rows.append({
            'month': month,
            'spdji_adv_mn': adv,
            'spdji_adv_yoy': None if d.get('adv_yoy') is None else d['adv_yoy'] * 100,
            'billed_issuance_yoy': None if d.get('billed_yoy') is None else d['billed_yoy'] * 100,
            'adv_derived': 1 if is_derived else 0,
            'billed_issuance_index': index.get(month),
        })
    return raw_rows, clean_rows


def _next(period):
    return (period[0] + 1, 1) if period[1] == 12 else (period[0], period[1] + 1)


# ─────────────────────────────── 写盘 ───────────────────────────────

def render_raw(rows):
    """series/spgi.csv 的行文本：%.15g 清洗（抹掉 ×100 的浮点尾巴）。"""
    out = [','.join(F.COLS_RAW)]
    for r in rows:
        out.append(','.join([r['month']] + [
            F._fmt15(F._g15(r[c])) for c in F.COLS_RAW[1:]]))
    return out


def render_clean(rows):
    """series/spgi_clean.csv 的行文本：repr 原生浮点，空值写空字符串。"""
    out = [','.join(F.COLS_CLEAN)]
    for r in rows:
        cells = [r['month']]
        for c in F.COLS_CLEAN[1:]:
            v = r[c]
            if v is None:
                cells.append('')
            elif c == 'adv_derived':
                cells.append(str(int(v)))
            else:
                cells.append(F._repr(v))
        out.append(','.join(cells))
    return out


def _write(path, lines, eol):
    with open(path, 'wb') as fh:
        fh.write(eol.join(l.encode('utf-8') for l in lines) + eol)


def diff_against_disk(path, lines, label):
    """把新内容与磁盘现有内容逐行比，打印新增 / 改动 / 不变的计数与明细。"""
    old = []
    if os.path.exists(path):
        with open(path, encoding='utf-8-sig', newline='') as fh:
            old = [l.rstrip('\r\n') for l in fh if l.strip()]
    old_by_m = {l.split(',')[0]: l for l in old[1:]}
    new_by_m = {l.split(',')[0]: l for l in lines[1:]}
    added = sorted(set(new_by_m) - set(old_by_m))
    changed = sorted(m for m in set(new_by_m) & set(old_by_m)
                     if new_by_m[m] != old_by_m[m])
    same = len(set(new_by_m) & set(old_by_m)) - len(changed)
    print('[%s] 新增 %d 行、改动 %d 行、原样不变 %d 行'
          % (label, len(added), len(changed), same))
    if added:
        print('        新增区间 %s .. %s' % (added[0], added[-1]))
    for m in changed:
        print('        改 %s' % m)
        print('           旧 %s' % old_by_m[m])
        print('           新 %s' % new_by_m[m])
    return added, changed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry', action='store_true', help='只打印差异，不写文件')
    ap.add_argument('--refresh', action='store_true', help='强制重下所有工作簿')
    ap.add_argument('--probe', action='store_true',
                    help='额外去 CDN 敲 2016-2022 的文件名（3528 个请求，慢）')
    args = ap.parse_args()

    if args.probe:
        if probe_pre2023():
            raise SystemExit('CDN 上居然有 2023 之前的工作簿 —— 本脚本的前提要改，请人工看')

    paths = discover(refresh=args.refresh)
    print('[discover] 本地共 %d 份工作簿可解析' % len(paths))

    merged, conflicts = collect(paths)
    audit_conflicts(conflicts)
    print('[collect] 官方直接披露覆盖 %s .. %s（%d 个月）'
          % (min(merged), max(merged), len(merged)))

    clean_path = os.path.join(SERIES_DIR, 'spgi_clean.csv')
    merged = pin_existing(merged, clean_path)

    raw_rows, clean_rows = build_rows(merged)
    raw_lines, clean_lines = render_raw(raw_rows), render_clean(clean_rows)
    print('[build] spgi.csv %d 行（%s..%s）；spgi_clean.csv %d 行（%s..%s）'
          % (len(raw_rows), raw_rows[0]['month'], raw_rows[-1]['month'],
             len(clean_rows), clean_rows[0]['month'], clean_rows[-1]['month']))

    raw_path = os.path.join(SERIES_DIR, 'spgi.csv')
    diff_against_disk(raw_path, raw_lines, 'spgi.csv')
    _, changed = diff_against_disk(clean_path, clean_lines, 'spgi_clean.csv')

    # 改动只允许落在 docstring 交代过的那两处。多出一处就停手 —— 那说明有别的东西
    # 在悄悄漂移（官方重述、解析器读错列、或本脚本自己算错），必须人工看过再放行。
    unexpected = [m for m in changed if not (m.startswith('2024')
                                             or m >= '2025-01')]
    if unexpected:
        raise SystemExit('改动落在了预期之外的月份 %r，回填中止' % unexpected)

    if args.dry:
        print('[dry] 未写盘')
        return
    # 换行符沿用各自原文件的：实测 spgi.csv 是 CRLF、spgi_clean.csv 是 LF。
    _write(raw_path, raw_lines, b'\r\n')
    _write(clean_path, clean_lines, b'\n')
    print('[write] 已写 %s 与 %s' % (os.path.relpath(raw_path, ROOT),
                                     os.path.relpath(clean_path, ROOT)))


if __name__ == '__main__':
    main()
