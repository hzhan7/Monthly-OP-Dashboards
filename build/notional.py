# -*- coding: utf-8 -*-
"""定基名义额换算库 —— 把张数 / 股数 / 本币成交额换算成可跨交易所比较的美元名义额。

`build/pools.py` 里每个成员都声明了一条换算链，本模块就是那条链的执行器。
链的每一跳都必须有一张表作证，没有一跳是「代码里拍的」：

    源列（张数 / 股数 / 本币金额）
      └─ unit_scale ─→ 规范单位（张 / 股 / 本币基本单位）
           └─ per_day ─→ 日均（源列本来就是 ADV 时留空）
                └─ product_id ─→ series/contract_specs.csv（乘数、基期价格、计价币种）
                     └─ ccy ─→ series/fx.csv（基期或当期汇率）
                          └─ 美元名义额

━━ 为什么主口径是「定基」而不是「当期」━━
定基名义额 = 张数 × 乘数 × **基期价格**（基期锁 2019-01，汇率同样锁基期）。
价格项与汇率项都是常数 ⇒ 这条序列的**增长率与张数的增长率完全相同**，
名义额只改变「不同产品之间的权重」和「不同成员之间的份额」，不引入标的涨跌与汇率波动。
这正是我们要的：份额变化必须是成交量的变化，不能是标的涨了或欧元贬了。
当期名义额（当期价格 × 当期汇率）另算一列，只回答「这个市场现在多大」，不进任何增长图。

━━ 三种源，一个公式 ━━
| kind      | 源列是什么          | multiplier | base_price_local | 定基化程度 |
|-----------|---------------------|-----------|------------------|-----------|
| contract  | 合约张数            | 单张标的量 | 基期标的价格      | 完全定基（价格与汇率都是常数） |
| share     | 成交股数            | 恒为 1     | 基期平均成交价    | 完全定基 |
| notional  | 本币成交额（已是钱）| 恒为 1     | 恒为 1            | **只锁汇率**，价格是当期 |

`notional` 这一类是必须承认的妥协：源头只给金额（HKEX 的 ADT、Euronext 的 ADNV），
金额 = 股数 × 当期价格，我们拿不到股数就没法把价格项剥出来（📌 未找到：HKEX/Euronext/Xetra
的月度报表都不披露成交股数，检索路径见 pools.py 各成员的 note）。
所以这类成员的池在 pools.py 里标 `deflator='fx_only'`，图注必须写明「已剔汇率、未剔标的涨跌」。
**混了 deflator 的池不许算份额** —— 分子分母的价格基准不同，占比是假的。

━━ 一条必须留痕的告诫：名义额 ≠ 风险敞口 ━━
利率池尤其危险。3 个月 SOFR 期货的面值是 100 万美元、久期 0.25 年；
10 年期国债期货面值 10 万美元、久期约 8 年。按名义额，短端合约的"体量"是长端的 10 倍，
按 DV01（真正的风险敞口）却是长端远大于短端 —— **两者能差一个数量级**。
所以利率池的名义额占比只能读作「名义额占比」，绝不可读作「谁承担了更多利率风险」
或「谁的风险转移生意更大」。要回答后者必须用 DV01 加权，需要各合约的久期数据
（📌 未找到：CME / ICE / Eurex 的月度成交报表都不含久期或 DV01 字段；
若要做，只能另找各交易所的合约规格页逐个合约取到期日与票息再自行计算，
成本远超本仓的无人值守边界）。同样的告诫适用于能源池（不同能源品的热值不同）。

━━ 三张表的契约 ━━
series/contract_specs.csv
    product_id, zh, exchange, kind, ccy, multiplier, mult_unit,
    base_month, base_price_local, base_notional_per_unit_local, price_id,
    source, evidence, notes
    · base_month 必须逐行等于 BASE_MONTH，基期不许一个产品一个样。
    · base_notional_per_unit_local 是 multiplier × base_price_local 的**冗余落库值**，
      加载时校验两者一致（相对误差 1e-9）—— 这一列存在的唯一理由是让人拿它与官方
      合约规格页逐位对账，不校验就等于没存。
    · base_price_local 允许留空：分批上线时（ICE 先上、ASX 最后）规格表也是逐批填的。
      留空的行照常加载，但**一旦被用到就抛 MissingBasePrice**，不会静默变成 NaN。
series/fx.csv        month, obs_days, eom_date, fx_avg_<ccy>usd…, fx_eom_<ccy>usd…
    由 fetch/fx.py 建（ECB SDMX，官方一手），**宽表**：一行一个月，每个币种两列。
    列名里的 usd 后缀写死了方向 —— `fx_avg_eurusd` = 当月 1 欧元平均值多少美元。
    本模块把它读成 {(月份, 币种, 基准): 美元/单位}，币种从表头正则出来，
    不写死币种清单：fetch/fx.py 哪天加一个币种，这里自动认得。
    **两个基准不可混用**（fetch/fx.py 的模块 docstring 立的规矩）：
      · `avg` 配**流量**（成交额、成交量折算、手续费）—— 整月里陆续发生的量；
      · `eom` 配**存量**（AUM、托管、市值、期末未平仓）—— 某一时点的余额。
    拿月末折成交额 = 把整月流量按最后一天记账；拿月均折 AUM = 给时点余额安一个
    不存在的平均价。两种错都不报错，只在同比里多出一段汇率噪声。
    池的 `flow` 字段（per_day / per_month / stock）决定用哪个基准，见 pools.fx_basis()。
    USD 表里没有（它是记账币），隐含 1.0。
series/prices.csv    month, price_id, price_local, source
    只有当期名义额需要它。定基名义额只用 contract_specs 里的基期价格，与本表无关。
    📌 本表尚未建。它不是本模块的产出物 —— 当期名义额是次要口径，
    主口径（定基）缺它照跑，所以 load_prices 的缺表异常应当被调用方单独捕获。

━━ 依赖 ━━ 只用标准库 csv。不引 pandas：本模块被 build 脚本和单元测试同时使用，
测试要能在没有第三方包的环境里跑起来。
"""

import csv
import math
import os
import re

# 基期锁死在 2019-01：这是仓内最晚开始的一条主序列（HKEX 自 2019-01）的起点，
# 也就是「全体成员都有数」的最早月份。基期若选得比它早，早期没有数的成员就没法定基；
# 选得比它晚，则白扔掉一段共同历史。这个值一旦发布就不能再改 —— 改了所有历史图的
# 水平值全部平移，而页面上不会有任何提示。
BASE_MONTH = '2019-01'

SPECS_CSV = 'contract_specs.csv'
FX_CSV = 'fx.csv'
PRICES_CSV = 'prices.csv'

USD_BN = 1e9        # 本模块一律返回**美元**；显示成 USD bn 时由调用方除这个数

SPEC_KINDS = ('contract', 'share', 'notional')

# 换算链里的 src 与规格表里的 kind 是同一件事的两种说法：
# src 说的是「这一列装的是什么」（复数，一列有很多张），
# kind 说的是「这个产品是什么」（单数，一个产品一种规格）。
# 两套词表必须由这一张映射表打通 —— 让 pools.py 自己再写一份 {'contracts':'contract'}
# 的话，将来加第四种源就会有一处忘改，而症状是"某一列悄悄没进图"。
SRC_TO_KIND = {'contracts': 'contract', 'shares': 'share', 'notional': 'notional'}
SRC_KINDS = tuple(SRC_TO_KIND)

# 汇率的两档基准。fetch/fx.py 把「用错了不会报错」列为它的头号口径坑，所以这里
# 不给"默认凑合用"的余地：档次由池的 flow 字段机械推出（basis_for_flow），
# build 脚本一律走 pools.fx_basis(p)，不许在调用点手写 'avg' / 'eom' 字面量。
FX_BASES = ('avg', 'eom')
FLOW_TO_FX_BASIS = {
    'per_day': 'avg',      # 日均成交额/量 —— 整月里陆续发生的流量
    'per_month': 'avg',    # 月度募资额 —— 同样是流量
    'stock': 'eom',        # AUM / 托管 / 市值 —— 某一时点的余额
}

_SPEC_COLS = ('product_id', 'zh', 'exchange', 'kind', 'ccy', 'multiplier',
              'mult_unit', 'base_month', 'base_price_local',
              'base_notional_per_unit_local', 'price_id', 'source',
              'evidence', 'notes')
# fx.csv 是 fetch/fx.py 写的**宽表**，币种不写死：列名正则出来，
# 哪天 fetch/fx.py 多加一个币种，这里自动认得（见 load_fx）。
_FX_COL_RE = re.compile(r'^fx_(avg|eom)_([a-z]{3})usd$')
_PRICE_COLS = ('month', 'price_id', 'price_local', 'source')


# ── 异常 ──────────────────────────────────────────────────────────────────
class NotionalError(RuntimeError):
    """换算链断了。一律炸掉 —— 静默返回 NaN 会被 payload_guard 拦在最后一道，
    但那时已经看不出是哪一跳断的了。"""


class SpecMissing(NotionalError):
    """series/ 下缺 contract_specs.csv / fx.csv / prices.csv。"""


class SpecInconsistent(NotionalError):
    """表结构或表内自洽性坏了（缺列、kind 非法、冗余列与乘积对不上、USD≠1）。"""


class UnknownProduct(NotionalError):
    """pools.py 引用了一个 contract_specs.csv 里没有的 product_id。"""


class MissingBasePrice(NotionalError):
    """该产品的基期价格还没实测入库 —— 分批上线时的正常状态，但不许静默跳过。"""


class MissingFxMonth(NotionalError):
    """fx.csv 缺这个 (月份, 币种)。"""


class MissingPrice(NotionalError):
    """prices.csv 缺这个 (月份, price_id)，或该产品根本没声明 price_id。"""


class ChainError(NotionalError):
    """成员的换算链本身声明得不对，或链上引用的 CSV 列取不到。"""


# ── 小工具 ────────────────────────────────────────────────────────────────
def _num(v):
    """CSV 单元格 → float 或 None。空串、'-'、'n/a' 都算空，不算 0。"""
    if v is None:
        return None
    s = str(v).strip()
    if s in ('', '-', '—', 'n/a', 'N/A', 'NA'):
        return None
    return float(s)


def _finite(v):
    return v is not None and isinstance(v, (int, float)) and math.isfinite(float(v))


def _require_cols(path, header, want):
    miss = [c for c in want if c not in header]
    if miss:
        raise SpecInconsistent('%s 缺列 %s（拿到 %s）'
                               % (os.path.basename(path), miss, list(header)))


# ── 加载三张表 ────────────────────────────────────────────────────────────
def load_specs(series_dir):
    """series/contract_specs.csv → {product_id: spec dict}。

    表内自洽性在这里一次性查完，因为「乘数 × 基期价 ≠ 落库的单位名义额」这种错
    在图上是看不出来的：它只会让某一家的柱子整体高一截，看上去完全像是真的。
    """
    path = os.path.join(series_dir, SPECS_CSV)
    if not os.path.exists(path):
        raise SpecMissing(
            '缺 %s —— 定基名义额是本批次的主口径，规格表没有就一个池也画不出来。'
            '表结构见 build/notional.py 模块 docstring。' % path)
    with open(path, newline='', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
        header = rows[0].keys() if rows else []
    if not rows:
        raise SpecInconsistent('%s 是空表' % path)
    _require_cols(path, header, _SPEC_COLS)

    out = {}
    for i, r in enumerate(rows, start=2):
        pid = (r['product_id'] or '').strip()
        if not pid:
            raise SpecInconsistent('%s 第 %d 行 product_id 为空' % (path, i))
        if pid in out:
            raise SpecInconsistent('%s product_id 重复：%s' % (path, pid))
        kind = (r['kind'] or '').strip()
        if kind not in SPEC_KINDS:
            raise SpecInconsistent('%s 第 %d 行 kind=%r 非法，只能是 %s'
                                   % (path, i, kind, list(SPEC_KINDS)))
        ccy = (r['ccy'] or '').strip().upper()
        if len(ccy) != 3 or not ccy.isalpha():
            raise SpecInconsistent('%s 第 %d 行 ccy=%r 不是三字母币种码'
                                   % (path, i, r['ccy']))
        base_month = (r['base_month'] or '').strip()
        if base_month != BASE_MONTH:
            raise SpecInconsistent(
                '%s 第 %d 行 base_month=%r，全仓基期锁死在 %s —— '
                '一个产品一个基期，跨成员的定基名义额就不可加也不可比'
                % (path, i, base_month, BASE_MONTH))
        mult = _num(r['multiplier'])
        price = _num(r['base_price_local'])
        unit_not = _num(r['base_notional_per_unit_local'])
        if mult is None or mult <= 0:
            raise SpecInconsistent('%s 第 %d 行 multiplier=%r 必须是正数'
                                   % (path, i, r['multiplier']))
        if kind in ('share', 'notional') and mult != 1:
            raise SpecInconsistent(
                '%s 第 %d 行 kind=%s 的 multiplier 必须是 1（拿到 %r）—— '
                '股数与金额本身就是标的量，再乘一次就是重复计数'
                % (path, i, kind, r['multiplier']))
        if kind == 'notional' and price is not None and price != 1:
            raise SpecInconsistent(
                '%s 第 %d 行 kind=notional 的 base_price_local 必须是 1（拿到 %r）—— '
                '源列已经是钱了，不存在"基期价格"这一跳'
                % (path, i, r['base_price_local']))
        # 冗余列的存在意义就是被校验；不校验就该删掉它
        if price is not None and unit_not is not None:
            want = mult * price
            if want == 0 or abs(unit_not - want) / abs(want) > 1e-9:
                raise SpecInconsistent(
                    '%s 第 %d 行 %s：base_notional_per_unit_local=%r 与 '
                    'multiplier × base_price_local=%r 对不上'
                    % (path, i, pid, unit_not, want))
        out[pid] = {
            'product_id': pid, 'zh': (r['zh'] or '').strip(),
            'exchange': (r['exchange'] or '').strip(), 'kind': kind, 'ccy': ccy,
            'multiplier': mult, 'mult_unit': (r['mult_unit'] or '').strip(),
            'base_month': base_month, 'base_price_local': price,
            'base_notional_per_unit_local': unit_not if unit_not is not None
            else (mult * price if price is not None else None),
            'price_id': (r['price_id'] or '').strip() or None,
            'source': (r['source'] or '').strip(),
            'evidence': (r['evidence'] or '').strip(),
            'notes': (r['notes'] or '').strip(),
        }
    return out


def load_fx(series_dir):
    """series/fx.csv（fetch/fx.py 写的**宽表**）→ {(month, ccy, basis): usd_per_unit}。

    表长这样：month, obs_days, eom_date, fx_avg_<ccy>usd…, fx_eom_<ccy>usd…
    一行一个月，每个币种两列。列名里的 usd 后缀写死了方向 ——
    `fx_avg_eurusd` = 当月 1 欧元平均值多少美元，所以是**乘**不是除。

    币种清单不写死，从表头正则出来：fetch/fx.py 哪天多加一个币种，这里自动认得。
    反过来，谁把某个币种只写了一半（有 avg 没 eom）也当场炸 —— 半张表的症状是
    存量口径悄悄回落到流量汇率，而那是本仓「用错了不会报错」的头号坑。

    **空单元格不在这里报错，只是不入表。** 将来加一个中途才有的币种时，早期月份
    天然为空；在加载期就炸会让整个仓因为一个没人用的币种停摆。真正需要它的那一跳
    会在 fx_rate 里抛 MissingFxMonth，报错点离故障更近，信息也更多。
    """
    path = os.path.join(series_dir, FX_CSV)
    if not os.path.exists(path):
        raise SpecMissing('缺 %s —— 跨币种的定基名义额没有汇率表就无从谈起' % path)
    with open(path, newline='', encoding='utf-8') as f:
        rdr = csv.DictReader(f)
        header = list(rdr.fieldnames or [])
        rows = list(rdr)
    if not rows:
        raise SpecInconsistent('%s 是空表' % path)
    if 'month' not in header:
        raise SpecInconsistent('%s 没有 month 列（拿到 %s）' % (path, header))

    # 表头 → {列名: (币种, 基准)}
    cols = {}
    for h in header:
        m = _FX_COL_RE.match((h or '').strip())
        if m:
            cols[h] = (m.group(2).upper(), m.group(1))
    if not cols:
        raise SpecInconsistent(
            '%s 里一列 fx_(avg|eom)_<ccy>usd 都没有（拿到 %s）—— '
            'fetch/fx.py 的表结构可能变了' % (path, header))
    have_bases = {}
    for ccy, basis in cols.values():
        have_bases.setdefault(ccy, set()).add(basis)
    half = sorted(c for c, b in have_bases.items() if b != set(FX_BASES))
    if half:
        raise SpecInconsistent(
            '%s 里这些币种只有一半基准：%s —— avg 配流量、eom 配存量，'
            '缺一档就意味着某一类口径会静默回落到另一档' % (path, half))

    out = {}
    for i, r in enumerate(rows, start=2):
        mon = (r.get('month') or '').strip()
        if not mon:
            raise SpecInconsistent('%s 第 %d 行 month 为空' % (path, i))
        # 行错位的廉价自检：eom_date 必须落在 month 这个月里
        eom = (r.get('eom_date') or '').strip()
        if eom and eom[:7] != mon:
            raise SpecInconsistent(
                '%s 第 %d 行 month=%s 但 eom_date=%s —— 两者不在同一个月，'
                '整张表可能错位了一行' % (path, i, mon, eom))
        for h, (ccy, basis) in cols.items():
            try:
                rate = _num(r.get(h))
            except ValueError:
                raise SpecInconsistent('%s 第 %d 行 %s=%r 不是数字'
                                       % (path, i, h, r.get(h))) from None
            if rate is None:
                continue                    # 空格不入表，见 docstring
            if rate <= 0 or not math.isfinite(rate):
                raise SpecInconsistent('%s 第 %d 行 %s=%r 必须是正的有限数'
                                       % (path, i, h, r.get(h)))
            if ccy == 'USD' and rate != 1.0:
                raise SpecInconsistent(
                    '%s 第 %d 行 %s=%r —— 列名方向是「1 单位该币值多少美元」，'
                    'USD 只能是 1.0；不是 1.0 说明整张表填反了（取了倒数）'
                    % (path, i, h, rate))
            out[(mon, ccy, basis)] = rate
    if not out:
        raise SpecInconsistent('%s 解析后一个汇率都没有' % path)
    return out


def basis_for_flow(flow):
    """池的 flow → 该用哪一档汇率。avg 配流量、eom 配存量，见 FLOW_TO_FX_BASIS。

    这个映射只有一份，pools.fx_basis() 直接委托到这里 —— 让 pools.py 自己再抄
    一份 {'stock': 'eom'} 的话，将来加第四种 flow 就会有一处忘改，
    而症状是某一条存量序列悄悄用了月均汇率：不报错，只在同比里多一段汇率噪声。
    """
    try:
        return FLOW_TO_FX_BASIS[flow]
    except KeyError:
        raise ChainError(
            'flow=%r 没有对应的汇率基准，只认 %s'
            % (flow, sorted(FLOW_TO_FX_BASIS))) from None


def load_prices(series_dir):
    """series/prices.csv → {(month, price_id): price_local}。只有当期名义额用得到。"""
    path = os.path.join(series_dir, PRICES_CSV)
    if not os.path.exists(path):
        raise SpecMissing(
            '缺 %s —— 只有「当期名义额」需要它；定基名义额不需要，'
            '所以缺它不该拦住主口径，调用方应当单独捕获本异常' % path)
    with open(path, newline='', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
        header = rows[0].keys() if rows else []
    if not rows:
        raise SpecInconsistent('%s 是空表' % path)
    _require_cols(path, header, _PRICE_COLS)
    out = {}
    for i, r in enumerate(rows, start=2):
        mon = (r['month'] or '').strip()
        pid = (r['price_id'] or '').strip()
        px = _num(r['price_local'])
        if not mon or not pid:
            raise SpecInconsistent('%s 第 %d 行 month/price_id 为空' % (path, i))
        if px is None or px <= 0:
            raise SpecInconsistent('%s 第 %d 行 price_local=%r 必须是正数'
                                   % (path, i, r['price_local']))
        out[(mon, pid)] = px
    return out


# ── 单跳查表（每一跳都有独立异常，坏了要能一眼看出坏在哪一跳）────────────────
def _spec(product_id, specs):
    if product_id not in specs:
        raise UnknownProduct(
            'product_id %r 不在 %s 里。pools.py 引用的每个产品都必须先在规格表里'
            '有一行（哪怕基期价格暂时留空）。已有 %d 个产品：%s'
            % (product_id, SPECS_CSV, len(specs),
               ', '.join(sorted(specs)[:12]) + (' …' if len(specs) > 12 else '')))
    return specs[product_id]


def fx_rate(fx, ccy, month, basis='avg'):
    """(币种, 月份, 基准) → 1 单位该币值多少美元。USD 隐含 1.0。

    basis: 'avg' 配流量（成交额、募资额），'eom' 配存量（AUM、托管、市值）。
    默认给 'avg' 是因为仓内 17 个池里 16 个是流量；唯一的存量池 fn_index_aum
    由 pools.fx_basis() 推出 'eom'，调用方不该手写这个字面量。
    """
    if basis not in FX_BASES:
        raise ChainError('basis=%r 只能是 %s' % (basis, list(FX_BASES)))
    if ccy == 'USD' and (month, 'USD', basis) not in fx:
        return 1.0
    try:
        return fx[(month, ccy, basis)]
    except KeyError:
        have = sorted(m for (m, c, b) in fx if c == ccy and b == basis)
        raise MissingFxMonth(
            '%s 缺 %s 的 %s 汇率（基准 %s）。该币种在这一档已有 %d 个月%s —— '
            '汇率缺月一律报错，绝不用相邻月、另一档基准或 1.0 顶上：'
            '那会把一次汇率断档悄悄变成一次"成交量跳变"'
            % (FX_CSV, ccy, month, basis, len(have),
               '（%s – %s）' % (have[0], have[-1]) if have else '（一个月都没有）')
        ) from None


def base_notional_per_unit_usd(product_id, specs, fx, basis='avg'):
    """单位（张 / 股 / 本币元）的**定基**美元名义额 —— 一个与月份无关的常数。

    整套口径的关键就在这个「常数」上：它把张数序列整体乘一个数，
    因此不改变任何一条序列的增长率，只改变成员之间与产品之间的相对权重。

    basis 只影响取哪一档**基期**汇率（2019-01 的月均 vs 2019-01 的月末），
    与月份无关这一点不变 —— 存量池（AUM）取 eom，流量池取 avg。
    """
    sp = _spec(product_id, specs)
    if sp['base_price_local'] is None:
        raise MissingBasePrice(
            '产品 %s（%s）的 base_price_local 在 %s 里是空的。'
            '基期价格必须来自官方一手披露并实测入库；在它填上之前，'
            '任何用到它的池都应当整池 skip 并打印原因，不许拿别的数顶替。'
            % (product_id, sp['zh'] or sp['exchange'], SPECS_CSV))
    return (sp['base_notional_per_unit_local']
            * fx_rate(fx, sp['ccy'], BASE_MONTH, basis))


def current_notional_per_unit_usd(product_id, specs, fx, prices, month,
                                  basis='avg'):
    """单位的**当期**美元名义额（当期价格 × 当期汇率）。只用于"现在多大"。"""
    sp = _spec(product_id, specs)
    if sp['kind'] == 'notional':
        px = 1.0
    else:
        pid = sp['price_id']
        if not pid:
            raise MissingPrice(
                '产品 %s 没有声明 price_id，算不了当期名义额。'
                '定基名义额不受影响（它只用基期价格）—— 若这个产品只需要主口径，'
                '就不要对它调用 to_current_notional。' % product_id)
        try:
            px = prices[(month, pid)]
        except KeyError:
            have = sorted(m for (m, p) in prices if p == pid)
            raise MissingPrice(
                '%s 缺 price_id=%s 的 %s 价格（已有 %d 个月%s）'
                % (PRICES_CSV, pid, month, len(have),
                   '（%s – %s）' % (have[0], have[-1]) if have else '')) from None
    return sp['multiplier'] * px * fx_rate(fx, sp['ccy'], month, basis)


# ── 对外主接口 ────────────────────────────────────────────────────────────
def _items(series):
    """接受 dict 或 pandas Series，一律吐 (month, value) 二元组。

    刻意不 import pandas：本模块要能在只有标准库的环境里被测试跑起来。
    """
    if hasattr(series, 'items'):
        return list(series.items())
    return list(series)


def to_base_notional(series, product_id, specs, fx, basis='avg'):
    """{月份: 规范单位数量} → {月份: 定基美元名义额}。

    规范单位 = 张 / 股 / 本币基本单位，由调用方先用 apply_unit() 换好
    （千张 → 张、百万股 → 股、€bn → €）。为什么要分成两步：
    unit_scale 是「这一列的写法」（口径坑，属于 pools.py），
    乘数与基期价格是「这个产品的规格」（属于 contract_specs.csv），
    两件事混在一个函数里，下次官方把列从千张改成百万张时会有人去改规格表。

    缺月（None / NaN）原样传出去 —— 线在缺口处断开是对的，
    补一个 0 会在图上画出一次"成交量归零"，那是编出来的事实。
    """
    k = base_notional_per_unit_usd(product_id, specs, fx, basis)
    return {m: (float(v) * k if _finite(v) else None) for m, v in _items(series)}


def to_current_notional(series, product_id, specs, fx, prices, basis='avg'):
    """{月份: 规范单位数量} → {月份: 当期美元名义额}（当期价格 × 当期汇率）。

    只用来回答「这个市场现在多大」。**不进任何增长图或份额图** ——
    它的同比里混着标的涨跌与汇率波动，读者会把一轮牛市读成成交量增长。
    """
    out = {}
    for m, v in _items(series):
        if not _finite(v):
            out[m] = None
            continue
        out[m] = float(v) * current_notional_per_unit_usd(
            product_id, specs, fx, prices, m, basis)
    return out


def apply_unit(series, unit_scale, days=None):
    """原始列 → 规范单位（张 / 股 / 本币元），必要时同时除交易日。

    days 给了就是「源列是月度总量不是日均」。这一步不能省也不能猜：
    仓内至少四家（NDAQ 全部、SGX 分产品、TMX 现货、ASX 部分）的原始值是月度总量，
    不除交易日会比同行大二十倍左右，而图上看起来只是"这家特别大"。
    交易日为 0 或缺失时该月置 None —— 除以 0 得 inf，inf 会一路飘到 payload。
    """
    if not _finite(unit_scale) or unit_scale <= 0:
        raise ChainError('unit_scale=%r 必须是正数' % (unit_scale,))
    dmap = dict(_items(days)) if days is not None else None
    out = {}
    for m, v in _items(series):
        if not _finite(v):
            out[m] = None
            continue
        x = float(v) * unit_scale
        if dmap is not None:
            d = dmap.get(m)
            if not _finite(d) or float(d) <= 0:
                out[m] = None
                continue
            x /= float(d)
        out[m] = x
    return out


def add_series(*parts):
    """多条腿相加。任一条腿在某月缺值 ⇒ 该月的合计置 None。

    不用 0 顶替：一个成员有两条腿（比如 Eurex 的利率 + 股指 + 单股），
    某月只到了两条，把第三条当 0 加进去，得到的合计既不是真值也没有任何标记，
    在图上就是一次凭空的下跌。
    """
    if not parts:
        raise ChainError('add_series 至少要一条腿')
    maps = [dict(_items(p)) for p in parts]
    months = set()
    for mp in maps:
        months |= set(mp)
    out = {}
    for m in sorted(months):
        vals = [mp.get(m) for mp in maps]
        out[m] = None if any(not _finite(v) for v in vals) else sum(float(v) for v in vals)
    return out


LEG_SIGNS = (1, -1)


def _ratio(num, den):
    """两列相除，得到一条**隐含交易日**序列。分母缺失或 ≤0 的月置 None。

    只有一个用途：源表给了「月度总量」与「官方自算的日均」两列却**没给交易日数**
    （SGX 就是这样：deriv_vol_contracts 与 ddav_contracts 都在，日数不在）。
    两者相除得到的就是交易所自己记账用的那个日数（实测非整数：2026-06 = 21.19，
    因为官方对 DDAV 做过舍入），拿它去除分产品月总量，才与官方 DDAV 同一套账。
    **不许改用证券市场的 sec_trading_days** —— 那是另一套日历（verify_sgx §口径坑 4/6）。
    """
    dmap = dict(_items(den))
    out = {}
    for m, v in _items(num):
        d = dmap.get(m)
        if not _finite(v) or not _finite(d) or float(d) <= 0:
            out[m] = None
        else:
            out[m] = float(v) / float(d)
    return out


def _apply_sign_and_since(series, leg, where):
    """给一条已换算好的腿加上**符号**与**生效起点**。

    `sign: -1` 是减法腿。它存在的唯一理由是**口径断点可逆**：Euronext 从 2025-11 起
    把 Athens 并进主列，官方同时给了一列「其中属于 Athens 的那块」的备注列，
    主列 − 备注列 = 并购前口径的 Euronext。没有减法腿就只能二选一：
    要么把 20 倍的假跳画上去，要么在 build 里手写一次减法（口径散到两处）。

    `since: 'YYYY-MM'` 是这条腿的**生效起点**，起点之前该腿贡献 **0 而不是 None**。
    两种情形都需要它，且语义是同一个「这一块在那之前不属于本合计」：
      · Athens 备注列 2021-01 就有值，但 2025-10 及以前**主列并不含它**
        ⇒ 减法腿必须从 2025-11 才生效，否则 2021-2025 会减掉一块从没加进来的量
        （实测 2025-08 单股期货主列 0.08k、备注列 28.55k，硬减会得到 −28 千张/日）；
      · MIAX 的 Pearl(2017-02) / Emerald(2019-03) / Sapphire(2024-08) 开业前根本不存在，
        那些月份不是"数据缺失"而是"确实是零"，用 None 会把四所合计砍到 2024-08 起。
    """
    sign = leg.get('sign', 1)
    if sign not in LEG_SIGNS:
        raise ChainError('%s 的 sign=%r 只能是 1 或 -1' % (where, sign))
    since = leg.get('since')
    out = {}
    for m, v in _items(series):
        if since and m < since:
            out[m] = 0.0
            continue
        out[m] = None if not _finite(v) else float(v) * sign
    return out


def resolve_leg(get_col, leg, member_csv, specs, fx, mode='base', prices=None,
                basis='avg'):
    """执行换算链的**一条腿**：源列 → unit_scale → per_day → product → 美元名义额。

    get_col(csv_name, col_name) 由调用方给，返回 {月份: 值}；取不到就抛。
    把取数抽成回调是为了让本模块不依赖 series/ 的目录结构与 pandas，
    单元测试可以直接喂字典。

    basis 由池的 flow 决定，调用方应当传 pools.fx_basis(p) 的结果。

    可选字段：
      · `sign`     ±1，见 _apply_sign_and_since。unit_scale 仍然只能是正数 ——
                   数量级与方向是两件事，混进一个字段就没法在体检里分别拦。
      · `since`    这条腿的生效起点，之前贡献 0。
      · `per_day`  {'col':…, 'csv': 可选, 'div_col': 可选}。给了 div_col 就是
                   「日数 = col ÷ div_col」的隐含交易日，见 _ratio。
    """
    for k in ('col', 'src', 'unit_scale', 'product'):
        if k not in leg:
            raise ChainError('换算链的腿缺字段 %r：%r' % (k, leg))
    csv_name = leg.get('csv') or member_csv
    if not csv_name:
        raise ChainError('换算链的腿没有 csv，成员也没有默认 csv：%r' % (leg,))
    sp = _spec(leg['product'], specs)
    if leg['src'] not in SRC_TO_KIND:
        raise ChainError('腿 %s.%s 的 src=%r 只能是 %s'
                         % (csv_name, leg['col'], leg['src'], list(SRC_KINDS)))
    if SRC_TO_KIND[leg['src']] != sp['kind']:
        raise ChainError(
            '腿 %s.%s 声明 src=%r（⇒ kind=%r），但 %s 在规格表里的 kind=%r —— '
            '两处必须一致，否则乘数会被乘到一个不该乘的量上'
            % (csv_name, leg['col'], leg['src'], SRC_TO_KIND[leg['src']],
               leg['product'], sp['kind']))
    raw = get_col(csv_name, leg['col'])
    days = None
    pd_spec = leg.get('per_day')
    if pd_spec:
        days_csv = pd_spec.get('csv') or csv_name
        days = get_col(days_csv, pd_spec['col'])
        if pd_spec.get('div_col'):
            days = _ratio(days, get_col(days_csv, pd_spec['div_col']))
    canon = apply_unit(raw, leg['unit_scale'], days)
    where = '腿 %s.%s' % (csv_name, leg['col'])
    if mode == 'base':
        out = to_base_notional(canon, leg['product'], specs, fx, basis)
    elif mode == 'current':
        if prices is None:
            raise ChainError('mode="current" 必须传 prices（load_prices 的结果）')
        out = to_current_notional(canon, leg['product'], specs, fx, prices, basis)
    else:
        raise ChainError('mode=%r 只能是 "base" 或 "current"' % (mode,))
    return _apply_sign_and_since(out, leg, where)


def resolve_chain(get_col, chain, member_csv, specs, fx, mode='base', prices=None,
                  basis='avg'):
    """执行整条链：各腿**先各自换算成名义额、再相加**。

    顺序不可颠倒。先把不同乘数的张数加起来再乘一个乘数，等于给这个成员编了一个
    并不存在的"平均合约"——而它的值会随月度品种结构漂移，图上完全看不出来。

    **带 sign=-1 腿的链有两道负值护栏，缺一不可。**
    负的名义额（"每天有负多少美元易手"）在物理上不存在，它只可能来自两种写错：
    减法腿的生效起点写早了（减掉了一块当时还没并进主列的量），或者减错了列。
    两种错都不会让任何一步报错，只会画出一条掉到 0 以下的线，
    而堆叠份额带会把负数悄悄吃掉。

      1. **逐对**：减法腿声明 `of_col` 指向它所修正的那条主列，
         「主列 − 备注列 ≥ 0」必须逐月成立 —— 备注列是主列的一个**子集**，
         这是官方口径本身的断言。
      2. **整链**：合计仍然不许为负。

    只有第 2 道是不够的，而这正是实测出来的：Euronext 2025-08 单股**期货**主列
    0.080 千张/日、Athex 备注列 28.553 —— 硬减是 −28.47，但同一条链里单股**期权**
    有 233.9，合计仍然是正的 349.7，整链护栏一声不吭。逐对护栏才抓得住它。
    """
    if not chain:
        raise ChainError('空的换算链')
    legs = [resolve_leg(get_col, lg, member_csv, specs, fx, mode, prices, basis)
            for lg in chain]

    # ── 护栏 1：逐对（备注列 ⊆ 主列）─────────────────────────────────────
    by_col = {}
    for lg, ser in zip(chain, legs):
        if lg.get('sign', 1) > 0:
            by_col[lg['col']] = ser
    for lg, ser in zip(chain, legs):
        if lg.get('sign', 1) >= 0:
            continue
        base_col = lg.get('of_col')
        if base_col is None:
            continue
        if base_col not in by_col:
            raise ChainError('减法腿 %s 的 of_col=%r 在同一条链里找不到对应的主列'
                             % (lg['col'], base_col))
        pos = dict(_items(by_col[base_col]))
        bad = sorted(m for m, v in _items(ser)
                     if _finite(v) and _finite(pos.get(m))
                     and float(pos[m]) + float(v) < 0)
        if bad:
            raise ChainError(
                '备注列 %s 大于它所修正的主列 %s：%s（共 %d 个月，最早 %s）。'
                '官方备注列本该是主列的一个子集 —— 减出负数只有两种可能：'
                'since 写早了（那些月份主列还不含这一块），或者配错了 of_col'
                % (lg['col'], base_col, ', '.join(bad[:6]), len(bad), bad[0]))

    out = dict(_items(legs[0])) if len(legs) == 1 else add_series(*legs)

    # ── 护栏 2：整链合计 ────────────────────────────────────────────────
    if any(lg.get('sign', 1) < 0 for lg in chain):
        bad = sorted(m for m, v in out.items() if _finite(v) and float(v) < 0)
        if bad:
            minus = [lg['col'] for lg in chain if lg.get('sign', 1) < 0]
            raise ChainError(
                '带减法腿的链算出负值：%s（共 %d 个月，最早 %s）。减掉的列是 %s —— '
                '要么减法腿的 since 写早了（减掉了一块当时还没并进主列的量），'
                '要么减错了列。负的名义额没有任何读法，绝不能静默写进 payload'
                % (', '.join(bad[:6]), len(bad), bad[0], ', '.join(minus)))
    return out


def pending_products(product_ids, specs):
    """哪些产品还没实测入库（不在表里，或基期价格为空）。

    给 build 脚本用：分批上线时某个池的规格还没填齐，应当**整池 skip 并打印原因**
    （照 build/exchanges.py 第 3 条规矩，退出码 0），而不是抛异常天天记一条假 FAIL。
    """
    out = []
    for pid in sorted(set(product_ids)):
        if pid not in specs:
            out.append((pid, '不在 %s 里' % SPECS_CSV))
        elif specs[pid]['base_price_local'] is None:
            out.append((pid, '基期价格未实测入库'))
    return out


if __name__ == '__main__':
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    _series = os.path.join(_root, 'series')
    for _name, _fn in (('规格表', load_specs), ('汇率表', load_fx),
                       ('价格表', load_prices)):
        try:
            _t = _fn(_series)
            print('%s: %d 条' % (_name, len(_t)))
        except NotionalError as _e:
            print('%s: %s' % (_name, _e))

    # 汇率表是三张表里唯一现在就齐的，单独把基期那一行摊开 ——
    # 定基名义额的每一个常数都要乘它，摊开就是让人能拿它与 ECB 逐位核对
    try:
        _fx = load_fx(_series)
        _ccys = sorted({c for (_m, c, _b) in _fx})
        _months = sorted({m for (m, _c, _b) in _fx})
        print('  币种 %d 个：%s' % (len(_ccys), ', '.join(_ccys)))
        print('  月份 %d 个：%s – %s' % (len(_months), _months[0], _months[-1]))
        print('  基期 %s 的汇率（1 单位外币 = 多少美元）：' % BASE_MONTH)
        for _c in _ccys:
            _a = _fx.get((BASE_MONTH, _c, 'avg'))
            _e2 = _fx.get((BASE_MONTH, _c, 'eom'))
            print('    %-4s avg=%-22r eom=%-22r  流量用 avg / 存量用 eom'
                  % (_c, _a, _e2))
    except NotionalError as _e:
        print('  基期汇率摊不开：%s' % _e)
