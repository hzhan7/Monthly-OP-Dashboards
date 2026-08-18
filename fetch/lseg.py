# -*- coding: utf-8 -*-
"""LSEG（London Stock Exchange Group）月度经营指标 —— 四路 part 的合流层。

这一家跟 DB1 一样是「一家公司缝多个官方源」，但缝的粒度更粗：LSEG 的月度披露
散在**四个互不相干的官方发布物**里，各有各的网站、各有各的格式、各有各的发布节奏，
连「一个月」的历史深度都从 24 个月到 115 个月不等。所以抓取拆成四个独立的
`fetch/lseg_<leg>.py`（下称 part 模块），各自把自己那一摊落到
`series/lseg_part_<leg>.csv`；**本模块不解析任何原始文件**，只做两件事：

  1. 依次驱动四路 part 模块刷新各自的 part CSV（某一路挂了就降级，不牵连其余三路）；
  2. 把四张 part CSV 按 month **外连接**成一张宽表 `series/lseg.csv`。

「本模块不解析原始文件」是刻意的边界：解析逻辑、单位换算、恒等式自检、故障注入，
全部在各自的 part 模块里（它们各有 800–950 行 docstring 记着各自的口径坑）。
这里只要出现一行「把某个数字换算一下」，那个换算就会脱离它所属的那一路的自检，
出错时没人查得到 —— 所以本模块里连一次乘除法都没有。

════════════════════════════════════════════════════════════════════════════
四路分工（列全部为 [A] 公司/交易所原始披露，无第三方转述、无推算、无券商研报）
════════════════════════════════════════════════════════════════════════════
| leg         | 官方源                                   | 列数 | 实测覆盖            |
|-------------|------------------------------------------|------|---------------------|
| `orderbook` | LSEG Monthly Market Report PDF（第 1 页 MTD 表） | 17 | 2021-01 → 2026-06 |
| `primary`   | LSE Main Market / AIM factsheet xlsx      | 24   | 2018-05 → 2026-07（缺 2019-09、2022-12，官方自己的洞）|
| `tradeweb`  | Tradeweb Historical ADV xlsx（monthly activity reports）| 27 | 2017-01 → 2026-07 |
| `lch`       | lseg.com LCH SwapClear / ForexClear / RepoClear volumes 页 | 18 | 2024-08 → 2026-07 |

各路的口径坑、故障注入结果、单位守卫写在各自模块的 docstring 里，本文件不复述。
唯一要在这里说清楚的是**跨路的三件事**：

口径坑 A：四路的历史深度差 8 倍，宽表必然是「左上角空一大片」。
    2017-01 那一行只有 tradeweb 的 27 列，2024-08 起才四路齐全。这是官方档案深度的
    真实形状，不是抓漏。**空格就是空格** —— 本模块永不写 0、永不写 NaN、永不用
    前值/后值/插值填补（README 铁律 2 的直接后果）。build 侧画图时必须按列各自的
    起始月裁窗口，不能拿「宽表有 115 行」当成每列都有 115 个观测。

口径坑 B：四路的发布节奏差一个数量级，**任何一个月都会分几次写全**。
    实测（各路自己量的，见各自 docstring）：lch 的两条快腿次月第 3–4 天、
    tradeweb 次月第 2–8 天、primary 次月第 1–9 天、orderbook 近期中位第 21 天。
    所以正常运行下，某个月的行会先由 tradeweb/primary/lch 建起来（orderbook 那
    17 列留空），两三周后 orderbook 再把空格填上。这正是「只填空不覆盖」要保护的
    场景 —— 见下面的幂等保证。
    ⚠ 由此推出：`monthly_run` 的 `EARLY_BY['lseg']` / roster 的 `LAG['lseg']`
    取决于**哪条腿决定这一页的 data_through**，而那是 build 侧的决定。本模块
    不改 `monthly_run.py`，也不替它拍板；只把四路各自的实测节奏摆在这里。

口径坑 C：`repoclear_*_cleared_trade_sides_count` 会被 `build/yoy.py` 的
    `classify()` 误判成 STOCK（它的 `_FLOW_PAT` 认词根 `trades`，而官方术语是
    "trade sides"）。这两列是**当月流量**，build 层必须显式传 `kind=FLOW`。
    本模块不改 yoy.py（口径唯一实现只能有一处），也不为迁就正则去改官方术语。

════════════════════════════════════════════════════════════════════════════
为什么是外连接，而不是内连接 / 不是各画各的
════════════════════════════════════════════════════════════════════════════
内连接会把宽表砍到 2024-08 起的 24 行 —— 把 tradeweb 那 91 个月真实存在的观测
扔掉，只为了让表看起来是满的。那是拿覆盖度换整齐，README 的数字纪律反过来了。
外连接把「谁有数据谁占格子」如实摊开，代价是表很稀疏 —— 稀疏是事实，藏不得。

════════════════════════════════════════════════════════════════════════════
对外接口（仓库标准，抄 fetch/db1.py）
════════════════════════════════════════════════════════════════════════════
    latest_month(cache_dir) -> 'YYYY-MM'        四路都已发布的最新月；抓不到抛异常
    update(series_dir, cache_dir) -> [months]   刷新四路 + 合流，返回新增月份（升序）

附带的诊断接口（不参与 monthly_run，供人工与将来的 build 接线用）：
    latest_months(cache_dir) -> {leg: 'YYYY-MM' | LsegFetchError}
    release_dates(cache_dir) -> {leg: (month, 'YYYY-MM-DD', 出处) | None}
    leg_columns() -> {leg: [列名…]}             宽表每一列出自哪一路

⚠ 本模块**不写 `series/source_dates.csv`**。页面抬头那句「官方发布于 YYYY-MM-DD」
是一句关于外部世界的事实断言（CONTRACT.md §1），而在四路拼一页的情形下，
「这个月是哪天可以看的」取决于**哪条腿决定 data_through** —— 那条腿还没定。
四路里只有 tradeweb 能给出「最新一期的发布日」（xlsx 目录名 + HTTP Last-Modified
交叉校验），orderbook 能逐月给（PDF 内嵌 CreationDate，但要剔除 `_N.pdf` 重传件），
primary 能逐月给（xlsx `docProps/core.xml` 的 `dcterms:created`），lch 只有当前
快照的一个日期。硬凑一个「四者取最晚」写进台账，等于用一个我说不清含义的日期去
冒充事实断言。宁可让页面缺这半句（页面会自动省掉），等 data_through 政策定了，
再由主线程用 `release_dates()` 一次接上。

════════════════════════════════════════════════════════════════════════════
降级策略（要求 3：某一路缺席时降级而不是崩溃）
════════════════════════════════════════════════════════════════════════════
分两种「缺席」，处理方式相反 —— 混为一谈就会把结构性错误当成临时网络抖动放过去：

  · **源头缺席**（网站挂了 / 官方还没发这一期 / 解析器按铁律 2 主动抛）
      → 降级：这一路本轮不刷新，但它**已经落库的 part CSV 照常参与合流**
        （series/ 是仓库真值，不是缓存），其余三路照跑。屏幕上打一行醒目的
        WARN，`update()` 的返回值里照样有其余三路带来的新月份。
      → 四路**全挂**才抛异常。否则 monthly_run 会看到 added=[] 报 NOCHANGE，
        把一次全站故障伪装成「本月没有新数据」。

  · **结构缺席**（part 模块文件不见了 / part CSV 的表头与该模块的 COLUMNS 对不上）
      → 立刻抛 LsegFetchError，不降级。理由：这两种情况下宽表会**静默少一整列**
        或**静默错位**，正是铁律 2 要挡的事。少一列的宽表照样能写出去、照样能画图，
        没有任何人会发现 —— 所以只能在这里炸。

════════════════════════════════════════════════════════════════════════════
幂等保证（README 铁律 3）
════════════════════════════════════════════════════════════════════════════
  · 已存在的月份不重复追加；
  · **已经有值的单元格永不覆盖** —— 四路的官方源都会重述历史（各自 docstring 有
    实证），重述不由无人值守任务自动吞进序列；不一致写
    `cache/lseg_restatements.csv` 供人工判断；
  · 只在**原本为空**的格子上回补 —— 这正是口径坑 B 的解药：先落下没有 orderbook
    那 17 列的行，两三周后自动填上；
  · 数值以**字符串原样搬运**，不做二次格式化。各 part 模块自己的 `_fmt()` 已经
    保证了「整数写整数、小数用最短往返表示」，这里再 float() 一遍只会引入新的
    表示差异，让「什么都没变」的重跑产生字节差异。仅在**比对是否冲突**时才解析成
    数字（容差 max(1e-9, 1e-12*|old|)），纯格式差异（如 `1.0` vs `1`）不算冲突、
    也不改写已有值。
  · 什么都没变时文件字节级不变，`update()` 返回 []。
"""
import csv
import datetime
import importlib.util
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

TICKER = 'lseg'
CSV_NAME = 'lseg.csv'
RESTATEMENT_LOG = 'lseg_restatements.csv'

# leg 名 → (part 模块文件名, part CSV 文件名, 一句话口径)
# **列序 = 这里的顺序**：现货成交 → 一级市场 → 固收（Tradeweb）→ 清算（LCH），
# 与 LSEG 自己讲业务的顺序一致，也便于人眼在 86 列里定位。
PARTS = [
    ('orderbook', 'lseg_orderbook', 'lseg_part_orderbook.csv',
     'LSE 主板 + Turquoise 电子订单簿月度成交（Monthly Market Report PDF 第 1 页 MTD 表）'),
    ('primary', 'lseg_primary', 'lseg_part_primary.csv',
     'LSE Main Market / AIM 一级市场：家数、市值、新上市、增发、募资（factsheet xlsx）'),
    ('tradeweb', 'lseg_tradeweb', 'lseg_part_tradeweb.csv',
     'Tradeweb 固收/信用/ETF/货币市场 ADV 与月成交额（Historical ADV xlsx）'),
    ('lch', 'lseg_lch', 'lseg_part_lch.csv',
     'LCH SwapClear / ForexClear / RepoClear 清算量与月末存量（lseg.com volumes 页）'),
]

# `latest_month()` 取哪几条腿的最小值。四路全算 = 「四路都发了这个月」，
# 是唯一说得清含义的定义。若将来 build 决定 data_through 只跟快腿（把 orderbook
# 的 17 列留给后续回补，页面早两周更新），**改这一行**即可，别去改 latest_month 的实现。
LATEST_LEGS = ('orderbook', 'primary', 'tradeweb', 'lch')

# orderbook 那一路没有 latest_month()，探测时最多往回翻几个月。
# 6 个月足够宽：实测最慢一期是数据月月末后 +51 天（且那是重传件）。
_PROBE_BACK = 6
_MONTH_NAMES = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
                'August', 'September', 'October', 'November', 'December']


class LsegFetchError(RuntimeError):
    """本模块自己的异常。

    只用于**合流层**的故障（part 模块缺失、表头错位、四路全挂）。各 part 模块
    自己的异常（LsegOrderbookFetchError / LsegPrimaryFetchError / LchFetchError /
    TradewebFetchError）不在这里包装成同一个类型 —— 排障时第一眼要能看出是哪一路。
    """


# ── part 模块加载 ───────────────────────────────────────────────────────────
_MODS = {}


def _mod(leg):
    """按路径加载 part 模块，结果缓存。

    不能裸 import：本模块被 monthly_run 用 spec_from_file_location 加载，那时
    sys.path 上既没有 fetch/ 也没有仓库根（fetch/db1.py 的 _source_dates 同理）。
    模块名加 `_lsegpart_` 前缀是为了不跟真被 import 过的同名模块打架。
    """
    if leg in _MODS:
        return _MODS[leg]
    name = dict((p[0], p[1]) for p in PARTS)[leg]
    path = os.path.join(HERE, name + '.py')
    if not os.path.exists(path):
        # 结构缺席 → 炸。少一个 part 模块 = 宽表静默少一整段列。
        raise LsegFetchError('缺 %s —— 宽表会静默少掉 %s 那一整段列，拒绝继续' % (path, leg))
    spec = importlib.util.spec_from_file_location('_lsegpart_' + leg, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if not hasattr(mod, 'COLUMNS'):
        raise LsegFetchError('%s 没有 COLUMNS —— 无法确定它在宽表里占哪些列' % path)
    _MODS[leg] = mod
    return mod


def _data_columns(leg):
    """part 模块声明的**数据列**（去掉 month）。

    四路的 COLUMNS 约定不统一：orderbook / lch 的 COLUMNS 不含 month（写 CSV 时
    现拼 `['month'] + COLUMNS`），tradeweb / primary 的含。这里统一成「不含」，
    并且不去改任何一路 —— 改它们的常量等于动别人的文件。
    """
    cols = list(_mod(leg).COLUMNS)
    if cols and cols[0] == 'month':
        cols = cols[1:]
    if 'month' in cols:
        raise LsegFetchError('%s 的 COLUMNS 里 month 不在首位：%s' % (leg, cols))
    return cols


def leg_columns():
    """{leg: [列名…]}。宽表每一列出自哪一路，build 侧写 spec 时照它分组。"""
    return dict((leg, _data_columns(leg)) for leg, _n, _c, _d in PARTS)


def _build_columns():
    cols, owner = ['month'], {}
    for leg, _n, _c, _d in PARTS:
        for c in _data_columns(leg):
            if c in owner:
                raise LsegFetchError(
                    '列名 %r 同时出现在 %s 与 %s —— 宽表里会互相盖掉，'
                    '必须先在 part 模块里改名' % (c, owner[c], leg))
            owner[c] = leg
            cols.append(c)
    return cols, owner


COLUMNS, COLUMN_LEG = _build_columns()


# ── 小工具 ──────────────────────────────────────────────────────────────────
def _num(s):
    try:
        return float(str(s).replace(',', ''))
    except (TypeError, ValueError):
        return None


def _prev_month(month):
    y, m = (int(x) for x in month.split('-'))
    return '%04d-%02d' % (y - 1, 12) if m == 1 else '%04d-%02d' % (y, m - 1)


def _this_month():
    t = datetime.date.today()
    return '%04d-%02d' % (t.year, t.month)


def _cache(cache_dir, name):
    os.makedirs(cache_dir, exist_ok=True)
    return os.path.join(cache_dir, name)


# ── 驱动四路刷新 ────────────────────────────────────────────────────────────
def _refresh_orderbook(mod, series_dir, cache_dir):
    # 这一路把缓存目录写死在模块常量 CACHE 里（不收 cache_dir 参数）。这里按传入的
    # cache_dir 重指一次，好让 monthly_run 的 CACHE 与手工调用都落到同一处；
    # 值与它自己的默认相同时是空操作。
    mod.CACHE = os.path.join(cache_dir, 'lseg_orderbook')
    # 把「已入库的月份」告诉它，别再逐月重下一遍（每月一次检索 + 一份 PDF + 0.25s）。
    # 窗口 2016-01 起共 127 个月，不传这个参数每轮要跑三分钟且产出为零 ——
    # write_csv 是「只填空不覆盖」，重抓回来的旧月份会被原样丢掉。
    mod.write_csv(mod.fetch_rows(skip=_read_part(series_dir, 'orderbook').keys()),
                  series_dir)


def _refresh_primary(mod, series_dir, cache_dir):
    mod.write_csv(series_dir, mod.fetch_rows(cache_dir))


def _refresh_tradeweb(mod, series_dir, cache_dir):
    mod.write_csv(series_dir=series_dir, cache_dir=cache_dir)


def _refresh_lch(mod, series_dir, cache_dir):
    mod.update(series_dir, cache_dir)


_REFRESH = {
    'orderbook': _refresh_orderbook,
    'primary': _refresh_primary,
    'tradeweb': _refresh_tradeweb,
    'lch': _refresh_lch,
}


def _part_path(series_dir, leg):
    return os.path.join(series_dir, dict((p[0], p[2]) for p in PARTS)[leg])


def _read_part(series_dir, leg):
    """读一张 part CSV → {month: {列: 字符串}}。

    表头必须与该 part 模块的 COLUMNS 完全一致（含顺序）—— 对不上就是结构缺席，抛。
    文件不存在返回 {}（那一路的列在宽表里整列留空，由调用方打 WARN）。
    值原样保留字符串，空格保持空格。
    """
    path = _part_path(series_dir, leg)
    if not os.path.exists(path):
        return {}
    with open(path, newline='', encoding='utf-8') as f:
        raw = list(csv.reader(f))
    if not raw:
        return {}
    header, body = raw[0], [r for r in raw[1:] if r and r[0].strip()]
    want = ['month'] + _data_columns(leg)
    if header != want:
        raise LsegFetchError(
            '%s 的表头与 %s 模块声明的列不一致，拒绝合流（错位会静默污染整张宽表）：\n'
            '  缺 %s\n  多 %s'
            % (path, leg, [c for c in want if c not in header],
               [c for c in header if c not in want]))
    out = {}
    for r in body:
        if len(r) != len(header):
            raise LsegFetchError('%s 的 %s 行有 %d 格，表头有 %d 格 —— 文件损坏'
                                 % (path, r[0], len(r), len(header)))
        out[r[0]] = dict(zip(header[1:], r[1:]))
    return out


# ── 宽表读写 ────────────────────────────────────────────────────────────────
def _read_csv(path):
    if not os.path.exists(path):
        return list(COLUMNS), []
    with open(path, newline='', encoding='utf-8') as f:
        raw = list(csv.reader(f))
    if not raw:
        return list(COLUMNS), []
    header, body = raw[0], [r for r in raw[1:] if r and r[0].strip()]
    missing = [c for c in COLUMNS if c not in header]
    if missing:
        raise LsegFetchError('series/%s 里没有这些列：%s' % (CSV_NAME, missing))
    return header, body


def _record_conflicts(cache_dir, rows):
    """已有值 vs part CSV 现值不一致 → 写 cache/lseg_restatements.csv，**不覆盖宽表**。

    四路的官方源都会重述历史，而重述有两种可能：官方改了数，或者某一路解析错了。
    机器分不清，所以这里只留证据不做决定。台账落在 cache/（gitignore），
    因为它是过程物不是真值。
    """
    if not rows:
        return
    path = _cache(cache_dir, RESTATEMENT_LOG)
    old = []
    if os.path.exists(path):
        with open(path, newline='', encoding='utf-8') as f:
            old = [r for r in csv.reader(f)][1:]
    seen = set(tuple(r[:3]) for r in old)
    fresh = [r for r in rows if tuple(str(x) for x in r[:3]) not in seen]
    if not fresh:
        return
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f, lineterminator='\n')
        w.writerow(['month', 'column', 'in_csv', 'in_part_csv', 'part', 'seen_on'])
        for r in sorted(old + [[str(x) for x in r] for r in fresh]):
            w.writerow(r)
    print('[lseg] ⚠ %d 处与已入库值冲突（官方重述或解析改动），已记 %s；宽表未覆盖'
          % (len(fresh), path))


# ── 对外接口 ────────────────────────────────────────────────────────────────
def _probe_orderbook_latest(mod):
    """orderbook 那一路没有 latest_month()，按标题往回探测最新一期月报。

    借的是它的私有 `_find_doc`（检索接口按标题精确匹配，找不到返回 None 不抛）。
    这是本模块唯一一处伸进别人私有函数的地方 —— 它没有公开的等价物，而
    「用 part CSV 的最大月充当官方最新月」是错的：那是本地真值，不是源头状态。
    将来那一路补上 latest_month()，下面的 getattr 会自动优先用公开接口。
    """
    month = _prev_month(_this_month())          # 当月的月报当然还没出
    for _ in range(_PROBE_BACK):
        y, m = (int(x) for x in month.split('-'))
        if mod._find_doc('LSEG market report %s %d' % (_MONTH_NAMES[m - 1], y)):
            return month
        month = _prev_month(month)
    raise LsegFetchError(
        'orderbook：往回探 %d 期都没找到月报（最新试到 %s）—— 检索接口或标题模板变了'
        % (_PROBE_BACK, _prev_month(_this_month())))


def _leg_latest(leg, cache_dir):
    mod = _mod(leg)
    fn = getattr(mod, 'latest_month', None)
    if fn is not None:
        return fn(cache_dir)
    if leg == 'orderbook':
        return _probe_orderbook_latest(mod)
    raise LsegFetchError('%s 既没有 latest_month() 也没有探测实现' % leg)


def latest_months(cache_dir):
    """{leg: 'YYYY-MM'}；某一路抓不到就把**异常对象**放进值里（不吞、不填 None）。

    诊断用：四路节奏差一个数量级，出问题时第一件事就是看这四个月份分别停在哪。
    """
    out = {}
    for leg, _n, _c, _d in PARTS:
        try:
            out[leg] = _leg_latest(leg, cache_dir)
        except Exception as e:                        # noqa: BLE001
            out[leg] = e
    return out


def latest_month(cache_dir):
    """四路都已发布的最新月 'YYYY-MM' —— 取 `LATEST_LEGS` 各路最新月的最小值。

    为什么是 min 而不是 max：max 会返回一个「只有 tradeweb 有数据」的月份，
    而这一页要讲的是 LSEG 整体，用它当最新月等于宣称一个只填了三成的行是完整的。

    为什么不学 db1 只看快腿：db1 那边的慢腿是明确的补充列（Clearstream / OTC），
    头条指标全在快腿上；这里 orderbook（最慢的一路）恰恰是 LSE 主板成交额，
    是不是头条要由 build 侧的 spec 决定 —— 那份 spec 还没写。在它写出来之前，
    这里给出唯一说得清含义的定义，并把开关留在模块顶部的 `LATEST_LEGS`。

    任一路抓不到一律抛异常，不返回 None、也不悄悄跳过那一路掩盖故障。
    """
    got = latest_months(cache_dir)
    bad = [(leg, got[leg]) for leg in LATEST_LEGS if isinstance(got[leg], Exception)]
    if bad:
        raise LsegFetchError('这几路取不到最新月：%s'
                             % '；'.join('%s → %s: %s' % (l, type(e).__name__, e)
                                         for l, e in bad))
    return min(got[leg] for leg in LATEST_LEGS)


def release_dates(cache_dir):
    """{leg: (数据月, 'YYYY-MM-DD', 出处说明) | None}。

    只有 tradeweb 有现成的公开接口（`release_date()`，xlsx 目录名 + HTTP
    Last-Modified 交叉校验）。其余三路要么只能逐月回算（orderbook 的
    `cadence()`、primary 的 `publish_lags()`），要么只有当前快照（lch 把
    PublishedDate 追进它自己的 cache 台账），公开接口的形状对不上，这里如实给 None
    而不是硬凑一个。

    ⚠ 本函数的返回值**不会**被写进 series/source_dates.csv —— 理由见模块 docstring。
    """
    out = {}
    for leg, _n, _c, _d in PARTS:
        fn = getattr(_mod(leg), 'release_date', None)
        if fn is None:
            out[leg] = None
            continue
        try:
            out[leg] = fn(cache_dir)
        except Exception as e:                        # noqa: BLE001
            print('[lseg] release_date(%s) 失败：%s: %s' % (leg, type(e).__name__, e))
            out[leg] = None
    return out


def update(series_dir, cache_dir):
    """刷新四路 part CSV 并合流成 series/lseg.csv，返回**本轮有变化的月份**（升序）。

    两段式：
      a) 逐路调 part 模块刷新自己的 `series/lseg_part_<leg>.csv`。**顺序无关**，
         各写各的文件、互不读取，一路失败只影响它自己（降级策略见模块 docstring）。
      b) 把四张 part CSV 外连接进宽表。这一段**只读 part CSV，不读 part 模块的
         内存结果** —— 于是「a 全挂、b 照跑」是自然成立的：上一轮落库的
         part CSV 仍然是仓库真值，宽表照样能建全。

    ⚠ 返回值口径与 db1 **刻意不同**，这是本模块唯一一处偏离样板，理由如下。
    db1 的 `update()` 只返回**新建行**的月份，回补既有行的空格不计入（它自己的
    docstring 写着「回补不计入返回值（它不是新月份）」）—— 在那边这没问题，它的慢腿
    是 Clearstream / OTC 那些补充列，头条指标全在快腿上，晚几天填上不影响页面。

    这里不行。口径坑 B：某个月的行会先由 tradeweb / primary / lch 建起来（次月第
    3–9 天），orderbook 的 17 列要到次月第 20 天上下才填得上，而那 17 列里躺着
    LSE 主板成交额。若沿用 db1 的口径，回补那天 `added` 是空的，`monthly_run.one()`
    会 `return 'NOCHANGE'` 直接跳过重生成 —— series 里数据已经到了，页面却要等到
    下个月的新行出现（又是十几天）才把它画出来。整整两周挂着一张缺了主板成交额的
    页，而且没有任何红点会报警，因为抓取「成功」了。

    所以这里返回 **新建行 ∪ 本轮被回补了空格的行**。代价是 monthly_run 会把回补月
    也印成 NEW 的月份列表（措辞略糙），换来的是「series 变了 → 页面一定跟着变」。
    幂等不受影响：格子填过一次就不再是空的，下一轮同样的输入返回 []。

    `refresh=False` 只做 b（不联网）。给排障与本模块自己的幂等测试用。
    """
    return _update(series_dir, cache_dir, refresh=True)


def _update(series_dir, cache_dir, refresh=True):
    os.makedirs(series_dir, exist_ok=True)
    os.makedirs(cache_dir, exist_ok=True)

    # ── a) 逐路刷新 ──
    failed = {}
    if refresh:
        for leg, _n, _c, _d in PARTS:
            before = set(_read_part(series_dir, leg))
            try:
                _REFRESH[leg](_mod(leg), series_dir, cache_dir)
            except Exception as e:                    # noqa: BLE001
                # 源头缺席 → 降级。这一路本轮不前进，但它已落库的 part CSV 照常合流。
                failed[leg] = e
                print('[lseg] ⚠ %s 这一路本轮失败（其余各路照跑）：%s: %s'
                      % (leg, type(e).__name__, e))
                continue
            after = set(_read_part(series_dir, leg))
            new = sorted(after - before)
            print('[lseg] %-9s ok  %d 个月%s'
                  % (leg, len(after), ('，新增 ' + ','.join(new)) if new else ''))
        if len(failed) == len(PARTS):
            # 四路全挂 = 一次全站故障。这里不抛的话 monthly_run 会看到 added=[]
            # 报 NOCHANGE，把故障伪装成「本月没有新数据」。
            raise LsegFetchError(
                '四路全部失败，没有任何一路可用：\n' + '\n'.join(
                    '  %s → %s: %s' % (l, type(e).__name__, e) for l, e in failed.items()))

    # ── b) 外连接合流 ──
    csv_path = os.path.join(series_dir, CSV_NAME)
    header, body = _read_csv(csv_path)
    idx = dict((name, i) for i, name in enumerate(header))
    have = dict((r[0], r) for r in body)
    known = set(have)
    touched = set()                    # 本轮被回补了空格的既有行，见 update() 的返回值口径
    conflicts, today = [], datetime.date.today().isoformat()

    for leg, _n, part_csv, _d in PARTS:
        data = _read_part(series_dir, leg)
        if not data:
            print('[lseg] ⚠ %s：series/%s 不存在或为空，宽表里它那 %d 列整列留空'
                  '（不填 0、不填 NaN、不用前值）'
                  % (leg, part_csv, len(_data_columns(leg))))
            continue
        for month in sorted(data):
            row = have.get(month)
            if row is None:
                row = [''] * len(header)
                row[idx['month']] = month
                have[month] = row
                body.append(row)
            for col, val in data[month].items():
                val = val.strip()
                if not val:
                    continue                          # part CSV 自己就是空 → 保持空
                cur = row[idx[col]].strip()
                if not cur:
                    row[idx[col]] = val               # 只填空
                    touched.add(month)
                    continue
                if cur == val:
                    continue
                a, b = _num(cur), _num(val)
                if a is not None and b is not None and abs(a - b) <= max(1e-9, 1e-12 * abs(a)):
                    continue                          # 纯表示差异（1.0 vs 1），不动已有值
                conflicts.append([month, col, cur, val, leg, today])   # 不覆盖，只记账

    body.sort(key=lambda r: r[idx['month']])
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f, lineterminator='\n')
        w.writerow(header)
        w.writerows(body)

    _record_conflicts(cache_dir, conflicts)
    fresh_rows = set(have) - known
    backfilled = sorted(touched - fresh_rows)
    filled = [c for c in COLUMNS[1:] if any(r[idx[c]].strip() for r in body)]
    print('[lseg] series/%s：%d 行 %s..%s，%d/%d 列有值%s'
          % (CSV_NAME, len(body), body[0][idx['month']], body[-1][idx['month']],
             len(filled), len(COLUMNS) - 1,
             ('；本轮降级的路：' + ','.join(sorted(failed))) if failed else ''))
    if backfilled:
        print('[lseg] 回补既有行的空格：%s（计入返回值，好让 monthly_run 重生成页面）'
              % ','.join(backfilled))
    return sorted(fresh_rows | touched)


def main():
    import sys                                        # noqa: PLC0415
    series = os.path.join(ROOT, 'series')
    cache = os.path.join(ROOT, 'cache')
    if '--latest' in sys.argv:
        for leg, v in latest_months(cache).items():
            print('%-9s %s' % (leg, v if not isinstance(v, Exception)
                               else '%s: %s' % (type(v).__name__, v)))
        print('latest_month =', latest_month(cache))
        return
    if '--merge-only' in sys.argv:                    # 不联网，只做外连接
        print('added:', _update(series, cache, refresh=False))
        return
    print('added:', update(series, cache))


if __name__ == '__main__':
    main()
