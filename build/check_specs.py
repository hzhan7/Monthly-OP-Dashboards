# -*- coding: utf-8 -*-
"""series/contract_specs.csv 体检 —— 定基名义额那张常数表的守门员。

用法:
    python3 build/check_specs.py              # 全表体检，全过退 0，有错退 1
    python3 build/check_specs.py --selftest   # 用合成行验证检查逻辑本身是有效的
    python3 build/check_specs.py --coverage   # 额外打印 pools.py 的产品覆盖率

━━ 这张表是什么 ━━
`series/contract_specs.csv` 是全站**定基名义额**的唯一常数源：

    定基名义额 = 张数 × 乘数 × 基期价格        基期锁 2019-01，汇率同样锁基期

乘数与基期价格都是常数，所以每条序列的增长率与它的张数增长率完全相同 ——
名义额只改变「产品之间」与「成员之间」的权重，不引入标的涨跌与汇率波动。
这也意味着：**这张表填错一个数，图上不会有任何异常**。柱子整体高一截或矮一截，
看上去完全像是真的。本脚本查的全部是这一类「错了看不出来」的问题。

━━ 全表统一的两条口径（写死在这里，改这两条等于改全站历史）━━
1. **基期 = 2019-01**（`BASE_MONTH`，与 build/notional.py 同源）。
   一个产品一个基期，跨成员的定基名义额就不可加也不可比。
2. **基期价格的默认基准 = 2019-01 月内全部交易日收盘价的算术平均**
   （`base_price_basis=avg_close`），不是月末最后一个交易日收盘。选月均的理由：
   成交量是整月陆续发生的**流量**，与它相乘的价格也该是整月的代表值；
   series/fx.csv 的流量换算用的同样是月均（fx_avg_*）而不是月末（fx_eom_*），
   两处基准一致，才不会在同一个乘积里混两种时间口径。
   例：SPX 2019-01 月均收盘 2607.3899952380953，月末收盘 2704.1001，差 3.7% ——
   选错基准，全站股指池的水平值就整体偏 3.7%，而图上看不出来。
   `eom_close`（月末收盘）在任何情况下都不是合法取值。

━━ `base_price_basis` 的四个合法取值：各自的含义与何时该用 ━━
这一列回答的是「**基期价格那一跳是怎么来的**」。四个取值按「测得有多实」排：

· `avg_close` —— **单一标的**、月内全部交易日收盘价的算术平均。
  何时用：这一行就是一张具体合约（或一个具体指数），且拿得到官方逐日收盘/结算价。
  这是默认基准，能用它就别用别的。（期货行取官方**结算价**而不是名叫 Close 的那一列
  仍算 avg_close —— 语义是「月内逐日的算术平均」，不是「一定叫 Close」，见 CBOE_VIX_FUT。）

· `basket_vw` —— **篮子按 2019-01 成交量加权**合成的单张名义额：
  常数 = Σ(成员当月张数 × 该成员单张名义额) ÷ Σ(成员当月张数)。
  何时用：这一行（`level=pool_product`）代表的不是某一张合约，而是一整类合约的
  加权平均单张名义额。成员自己的名义额可以是面值、也可以是乘数 × 月均收盘、
  还可以是官方成交额 ÷ 张数 —— 这三种都归 basket_vw，因为**常数依赖权重**这件事
  才是它与 avg_close 的实质差别。
  ⚠ 它与 avg_close 的价格口径**不完全可比**，混在同一个池里要知情：
  EUREX_INDEX 走官方 Capital Volume ÷ Traded Contracts，隐含点位 3077.155，
  比 SX5E 的 2019-01 月均收盘 3088.654 低 0.372%（期权腿差到 4.4%）。
  这个差在图上完全看不出来，所以只能靠这一列标出来，不能抹平。
  用它的行必须在 evidence 里写清**权重来源与覆盖率**（覆盖了该类张数的百分之多少）——
  权重不写清楚，这个常数就是个不可复核的数字。
  ⚠ 不许拿它当「我算不清楚」的兜底：算不出就把 base_price_local 留空 + notes 写 📌，
  留空是诚实的，填一个来路不明的加权数不是。
  📌 权重恰好退化（当月只有一个成员有量、或各成员面值相同）时**仍填 basket_vw**：
  这一列记的是方法，不是这一期的巧合；跟着巧合走会让同一套算法在表里出现两种标注。

· `month_midpoint` —— **月初收盘与月末收盘的中点**：(首个交易日收盘 + 末个交易日收盘) ÷ 2。
  何时用：**只有**在官方只发这两个价格、日频序列拿不到时（典型：ASX 单股期权，
  ASX 的历史日行情是收费产品，官方免费只发月初月末两个点）。
  何时不该用：只要拿得到月内逐日收盘，一律 avg_close —— 中点对月内路径完全不敏感。
  代价必须在 notes 里留痕：ASX_ETO 的实测区间是 月初 2465.9435 / 月末 2618.9303 /
  中点 2542.4369，宽度约 ±3%，这就是用它要付的精度。
  📌 篮子行若价格项只能取到这两个点，填 month_midpoint 而**不是** basket_vw：
  这一列标的是**最弱的那一环** —— 加权方法对不对，重要性比不上「价格只有两个点」。

· `definitional` —— 价格项按定义就是 1，不是一种实测基准。
  何时用：kind=notional 的金额列（源列已经是钱），以及单张合约的面值口径
  （利率/国债期货按面值计名义额、不乘结算价，此时 multiplier 记面值、价格记 1）。

━━ `notional_source`：这个名义额常数是**哪来的**（与上一列正交，别读成一件事）━━
· `official_notional` —— 官方直接发名义额。两种形态：kind=notional 的行（源列本身
  就是交易所发布的成交金额/AUM/募资额）；以及官方发了金额、我们只做一次除法的行
  （Eurex 的 Capital Volume ÷ Traded Contracts、Cboe 的 Total Notional ÷ Total Shares）。
· `definitional` —— 面值定义（国债/利率期货：名义额 = 面值，不乘结算价）。
· `reconstructed` —— 乘数 × 基期价格重建出来的。
**这一列存在的唯一理由**：官方直发的常数可信度远高于重建的，页面上必须能区分。
一个 reconstructed 的常数错了，图上看不出来；一个 official_notional 的常数错了，
通常意味着官方文件被读错了列 —— 两者该被追问的方式不一样。
不确定就别猜：`notional_source` 与 `base_price_local` 同生同灭（C15），
价格还没测出来的行这一列必须留空。

━━ 每条检查对应的失败模式（为什么这条检查存在）━━
C1  必需列齐全           —— 缺列 ⇒ notional.load_specs 直接炸，早查早知道
C2  product_id 唯一非空   —— 重复 id 会让后写的那行静默覆盖前一行（dict 语义），
                            两个产品共用一个乘数，图上完全看不出来
C3  乘数为正             —— 0 或空 ⇒ 整条序列变 0，图上是一次「成交量归零」
C4  基期价格为正或明确空   —— 负价、0 价一律拒；空是合法状态（分批上线），
                            但空行的 notes 必须带 📌，防止「悄悄留空」变成永久留空
C5  冗余列 = 乘数 × 基期价 —— 这一列存在的唯一理由就是被人拿去与官方规格页逐位对账；
                            不校验它，它就只是一列没人看的噪声
C6  base_month 逐行等于基期 —— 见上「口径 1」
C7  base_price_basis 合法且统一 —— 见上「口径 2」。表里同时出现 avg_close 与
                            eom_close 是最危险的一种错：两种基准的产品放进同一个池，
                            占比就是假的，而没有任何一处会报错
C8  kind 与 multiplier 自洽 —— share/notional 的乘数必须是 1（股数与金额本身就是标的量，
                            再乘一次就是重复计数）；notional 的基期价必须是 1
C9  ccy 三字母            —— fx.csv 查不到就整池断，早查早知道
C10 level 合法            —— contract / index_ref / pool_product 三类的语义不同，
                            混了会让下一个人以为 index_ref 也能当合约用
C11 index_ref 不许被引用   —— 指数点位参照行不是合约。它一旦被写进 pools.py 的换算链，
                            算出来的是「张数 × 指数点位」，量纲错了但仍是个正数
C12 effective 区间自洽     —— 同一 spec_group 内不重叠、不断档。规格改过却只留一行，
                            等于用新乘数去乘旧张数；拆了两行但区间有洞，那几个月会静默丢失
C13 pools.py 覆盖率        —— 只报告不判失败：分批上线时缺产品是正常状态，
                            notional.pending_products 会让对应的池整池 skip。
                            ⚠ 报告里「待测」与「⛔ 永久张数口径」分两栏，不许合并：
                            前者是「还没测出来」，后者是 pools.py 用 `contracts_only`
                            声明的终局状态（测出来也不该用，见 pools.py 模块 docstring 六）。
                            两者共用「base_price_local 为空」这一种表示，
                            合并的代价是每一轮都有人去把同一堵墙重新撞一遍
C14 篮子行乘数必须是 1     —— level=pool_product 的常数是「一整类合约的加权平均单张
                            名义额」，成员各自的乘数**已经并进这个常数**；主表再写一个
                            ≠1 的乘数，C5 的恒等式就会把乘数算两遍，柱子整体高一截
C15 notional_source 自洽   —— 取值合法；与 base_price_local 同生同灭；且与
                            base_price_basis 不许互相矛盾（avg_close / month_midpoint
                            按定义就是重建，definitional 按定义就不是重建）
C16 同池基准混用（只报告）—— avg_close 与 basket_vw 的价格口径差实测有 0.4%~4%，
                            混在一个池里是允许的，但必须**知情**：这里把混用打出来，
                            不打就没人知道自己在比两个不同口径的数

━━ 依赖 ━━ 只用标准库 csv。与 build/notional.py 一样刻意不引 pandas ——
本脚本要能在只有标准库的环境里跑起来（它是别的检查跑之前的第一道闸）。
"""

import csv
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SERIES = os.path.join(ROOT, 'series')

SPECS_CSV = 'contract_specs.csv'
TODO_CSV = 'contract_specs_todo.csv'

BASE_MONTH = '2019-01'          # 与 build/notional.py 的 BASE_MONTH 必须一致，C6 会核
PRICE_BASIS = ('avg_close', 'basket_vw', 'month_midpoint', 'definitional')
# 实测基准（definitional 不算：它是「价格项按定义 = 1」，不测任何东西）。
# 表里同时出现多种实测基准是**允许的**（篮子行与单合约行本来就测不出同一种数），
# 但同一个池里混用必须被打印出来 —— 见 C16 与模块 docstring 里 basket_vw 的口径差实测。
MEASURED_BASES = ('avg_close', 'basket_vw', 'month_midpoint')
# 名义额常数的来源性质；页面要靠它区分「官方直发」与「重建」，见模块 docstring
NOTIONAL_SOURCES = ('official_notional', 'definitional', 'reconstructed')
KINDS = ('contract', 'share', 'notional')
LEVELS = ('contract', 'index_ref', 'pool_product')

# notional.load_specs 会读的 14 列，一列都不能少
REQUIRED_BY_NOTIONAL = (
    'product_id', 'zh', 'exchange', 'kind', 'ccy', 'multiplier', 'mult_unit',
    'base_month', 'base_price_local', 'base_notional_per_unit_local',
    'price_id', 'source', 'evidence', 'notes')
# 本表在 notional 的最小集之上多出来的列：池归属、行的性质、常数的两种出处、
# 规格代际与生效区间
REQUIRED_EXTRA = ('pool', 'level', 'contract_name', 'underlying_symbol',
                  'base_price_basis', 'notional_source', 'spec_group',
                  'effective_from', 'effective_to')

TODO_REQUIRED = ('product_id', 'zh', 'exchange', 'pool', 'contract_name',
                 'underlying_symbol', 'want', 'official_url', 'blocker',
                 'next_step', 'last_tried')


class SpecCheckError(RuntimeError):
    """表本身读不进来（文件缺失 / 空表 / 缺列）—— 后面的逐行检查无从谈起。"""


# ── 小工具 ────────────────────────────────────────────────────────────────
def _num(v):
    """单元格 → float 或 None。空串与几种常见的「空」写法都算空，不算 0。

    这里刻意与 notional._num 保持同一套空值词表：两边对「什么算空」的判断若不同，
    体检通过的表在 load_specs 里仍可能炸。
    """
    if v is None:
        return None
    s = str(v).strip()
    if s in ('', '-', '—', 'n/a', 'N/A', 'NA'):
        return None
    try:
        return float(s)
    except ValueError:
        return ('NOT_A_NUMBER', s)


def _month_ok(s):
    """'YYYY-MM' 形状检查。effective 区间用它，随手写成 '2019/01' 会被挡下。"""
    if len(s) != 7 or s[4] != '-':
        return False
    y, m = s[:4], s[5:]
    return y.isdigit() and m.isdigit() and 1 <= int(m) <= 12


def _next_month(s):
    y, m = int(s[:4]), int(s[5:])
    return '%04d-%02d' % (y + 1, 1) if m == 12 else '%04d-%02d' % (y, m + 1)


# ── 读表 ──────────────────────────────────────────────────────────────────
def load_rows(series_dir, fname, required):
    path = os.path.join(series_dir, fname)
    if not os.path.exists(path):
        raise SpecCheckError('缺 %s' % path)
    with open(path, newline='', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise SpecCheckError('%s 是空表' % path)
    miss = [c for c in required if c not in rows[0]]
    if miss:
        raise SpecCheckError('%s 缺列 %s（拿到 %s）'
                             % (path, miss, list(rows[0].keys())))
    return path, rows


# ── 逐行检查 ──────────────────────────────────────────────────────────────
def check_specs(rows, path):
    """返回错误列表。每条错误自带行号 —— 表有 70+ 行，没行号等于没报错。"""
    errs = []
    seen = {}
    groups = {}

    for i, r in enumerate(rows, start=2):       # 2 = CSV 首个数据行的行号
        def bad(msg):
            errs.append('%s 第 %d 行 [%s] %s'
                        % (os.path.basename(path), i,
                           (r.get('product_id') or '?').strip(), msg))

        pid = (r['product_id'] or '').strip()
        # C2
        if not pid:
            bad('product_id 为空')
            continue
        if pid in seen:
            bad('product_id 重复（与第 %d 行撞车）—— 后写的那行会静默覆盖前一行' % seen[pid])
            continue
        seen[pid] = i

        kind = (r['kind'] or '').strip()
        level = (r['level'] or '').strip()
        ccy = (r['ccy'] or '').strip()
        basis = (r['base_price_basis'] or '').strip()
        nsrc = (r.get('notional_source') or '').strip()
        notes = r.get('notes') or ''

        # C10
        if level not in LEVELS:
            bad('level=%r 非法，只能是 %s' % (level, list(LEVELS)))
        # C8（第一半）
        if kind not in KINDS:
            bad('kind=%r 非法，只能是 %s' % (kind, list(KINDS)))
        # C9
        if len(ccy) != 3 or not ccy.isalpha():
            bad('ccy=%r 不是三字母币种码' % ccy)
        # C6
        if (r['base_month'] or '').strip() != BASE_MONTH:
            bad('base_month=%r，全表基期锁死在 %s —— 一个产品一个基期，'
                '跨成员的定基名义额就不可加也不可比'
                % ((r['base_month'] or '').strip(), BASE_MONTH))

        # C3
        mult = _num(r['multiplier'])
        if isinstance(mult, tuple):
            bad('multiplier=%r 不是数字' % mult[1])
            mult = None
        elif mult is None or mult <= 0:
            bad('multiplier=%r 必须是正数 —— 乘数为空或为 0 会让整条序列变成 0，'
                '图上看起来就是一次「成交量归零」' % (r['multiplier'],))
            mult = None

        # C4
        px = _num(r['base_price_local'])
        if isinstance(px, tuple):
            bad('base_price_local=%r 不是数字' % px[1])
            px = None
        elif px is not None and px <= 0:
            bad('base_price_local=%r 必须是正数或明确留空' % (r['base_price_local'],))
            px = None
        elif px is None:
            # 留空是合法状态（分批上线），但必须留痕：没有 📌 就是「悄悄留空」，
            # 而悄悄留空的行永远不会有人回来补
            if '📌' not in notes:
                bad('base_price_local 留空，但 notes 里没有 📌 —— '
                    '基期价格拿不到必须写明「📌 未找到」与检索路径，不许静默留白')
            if basis:
                bad('base_price_local 为空却写了 base_price_basis=%r，'
                    '基准是对某个实测值的描述，没有值就不该有基准' % basis)

        # C7
        if basis and basis not in PRICE_BASIS:
            bad('base_price_basis=%r 非法，只能是 %s（月末收盘等其它基准一律不许出现，'
                '两种基准混在一张表里会让份额悄悄失真）' % (basis, list(PRICE_BASIS)))
        if px is not None and not basis:
            bad('有 base_price_local 却没写 base_price_basis —— '
                '一个没说清是怎么测出来的价格，没法与官方数字对账')

        # C5
        unit_not = _num(r['base_notional_per_unit_local'])
        if isinstance(unit_not, tuple):
            bad('base_notional_per_unit_local=%r 不是数字' % unit_not[1])
        elif px is None and unit_not is not None:
            bad('base_price_local 为空却填了 base_notional_per_unit_local=%r' % unit_not)
        elif px is not None and mult is not None:
            want = mult * px
            if unit_not is None:
                bad('base_price_local 与 multiplier 都有值，却没填 '
                    'base_notional_per_unit_local —— 这一列是给人逐位对账用的，不能省')
            elif want == 0 or abs(unit_not - want) / abs(want) > 1e-9:
                bad('base_notional_per_unit_local=%r 与 multiplier × base_price_local=%r 对不上'
                    % (unit_not, want))

        # C8（第二半）
        if kind in ('share', 'notional') and mult is not None and mult != 1:
            bad('kind=%s 的 multiplier 必须是 1（拿到 %r）—— '
                '股数与金额本身就是标的量，再乘一次就是重复计数' % (kind, mult))
        if kind == 'notional' and px is not None and px != 1:
            bad('kind=notional 的 base_price_local 必须是 1（拿到 %r）—— '
                '源列已经是钱了，不存在「基期价格」这一跳' % px)

        # C11（第一半）：index_ref 的形状
        if level == 'index_ref':
            if kind != 'contract':
                bad('level=index_ref 的 kind 只能是 contract（拿到 %r）' % kind)
            if mult is not None and mult != 1:
                bad('level=index_ref 的 multiplier 必须是 1（拿到 %r）—— '
                    '它记的是「一个指数点」，不是某张合约的规格' % mult)

        # C14：篮子行的乘数必须是 1
        if level == 'pool_product' and mult is not None and mult != 1:
            bad('level=pool_product 的 multiplier 必须是 1（拿到 %r）—— '
                '篮子常数 = Σ(成员张数 × 成员单张名义额) ÷ Σ张数，'
                '**成员各自的乘数已经并进这个常数了**；这里再写一个乘数，'
                'C5 的恒等式就会把它算两遍，那一家的柱子整体高一截，图上看不出来' % mult)

        # C15：notional_source
        if nsrc and nsrc not in NOTIONAL_SOURCES:
            bad('notional_source=%r 非法，只能是 %s' % (nsrc, list(NOTIONAL_SOURCES)))
        elif px is not None and not nsrc:
            bad('有 base_price_local 却没写 notional_source —— '
                '官方直发的名义额与乘数×价格重建出来的，可信度差一个量级，'
                '页面要靠这一列区分；空着就只能一律当成重建的')
        elif px is None and nsrc:
            bad('base_price_local 为空却写了 notional_source=%r —— '
                '这一列描述的是某个已经得到的常数是哪来的，没有常数就不该有来源' % nsrc)
        if nsrc in NOTIONAL_SOURCES and basis in PRICE_BASIS:
            if basis in ('avg_close', 'month_midpoint') and nsrc != 'reconstructed':
                bad('base_price_basis=%s 与 notional_source=%s 矛盾 —— '
                    '名义额是拿乘数去乘一个实测价格算出来的，按定义就是 reconstructed'
                    % (basis, nsrc))
            if basis == 'definitional' and nsrc == 'reconstructed':
                bad('base_price_basis=definitional 与 notional_source=reconstructed 矛盾 —— '
                    '价格项按定义就是 1，没有「乘数 × 基期价格」这一跳可重建')

        # C12 分组
        grp = (r['spec_group'] or '').strip() or pid
        groups.setdefault(grp, []).append((i, pid, (r['effective_from'] or '').strip(),
                                           (r['effective_to'] or '').strip()))

    errs += _check_effective(groups, os.path.basename(path))
    return errs


def _check_effective(groups, fname):
    """C12：同一 spec_group 的规格代际必须首尾相接、不重叠、不断档。

    为什么按 spec_group 而不是 product_id 分组：product_id 必须全表唯一（C2），
    所以「同一个合约的两代规格」只能是两个 id（例如 …_V1 / …_V2），
    把它们认成同一个逻辑产品的唯一线索就是 spec_group。
    """
    errs = []
    for grp, items in sorted(groups.items()):
        if len(items) == 1:
            i, pid, ef, et = items[0]
            # 单行组允许两头都空 = 「本表未见规格变更」。但只写了 to 没写 from
            # 是明确的漏填：它在说「这一代到某月为止」，那之后那一代在哪儿？
            if et and not ef:
                errs.append('%s 第 %d 行 [%s] 写了 effective_to 却没有 effective_from' % (fname, i, pid))
            for lab, v in (('effective_from', ef), ('effective_to', et)):
                if v and not _month_ok(v):
                    errs.append('%s 第 %d 行 [%s] %s=%r 不是 YYYY-MM' % (fname, i, pid, lab, v))
            if et and not _month_ok(et):
                continue
            if ef and et and et < ef:
                errs.append('%s 第 %d 行 [%s] effective_to 早于 effective_from' % (fname, i, pid))
            continue

        # 多行组：每一代都必须说清自己从哪个月开始
        bad_shape = False
        for i, pid, ef, et in items:
            if not ef:
                errs.append('%s 第 %d 行 [%s] 属于多代规格组 %s，必须填 effective_from —— '
                            '规格改过却不标断点，等于用新乘数去乘旧张数' % (fname, i, pid, grp))
                bad_shape = True
            elif not _month_ok(ef):
                errs.append('%s 第 %d 行 [%s] effective_from=%r 不是 YYYY-MM' % (fname, i, pid, ef))
                bad_shape = True
            if et and not _month_ok(et):
                errs.append('%s 第 %d 行 [%s] effective_to=%r 不是 YYYY-MM' % (fname, i, pid, et))
                bad_shape = True
        if bad_shape:
            continue

        ordered = sorted(items, key=lambda x: x[2])
        open_ended = [x for x in ordered if not x[3]]
        if len(open_ended) != 1 or open_ended[0] is not ordered[-1]:
            errs.append('%s 规格组 %s：只有时间上最后的那一代允许 effective_to 留空'
                        '（现在有 %d 行留空）' % (fname, grp, len(open_ended)))
            continue
        for (i1, p1, f1, t1), (i2, p2, f2, _t2) in zip(ordered, ordered[1:]):
            if t1 >= f2:
                errs.append('%s 规格组 %s：%s(至 %s) 与 %s(自 %s) 区间重叠 —— '
                            '重叠月份有两套乘数，取哪一套是随机的'
                            % (fname, grp, p1, t1, p2, f2))
            elif _next_month(t1) != f2:
                errs.append('%s 规格组 %s：%s(至 %s) 与 %s(自 %s) 之间断档 —— '
                            '中间那几个月没有任何一行覆盖，会被静默丢掉'
                            % (fname, grp, p1, t1, p2, f2))
    return errs


def check_todo(spec_rows, todo_rows, todo_path):
    """缺口登记册的自洽性：登记的必须是**还没入库**的产品，且每行要能被下一个人接手。"""
    errs = []
    have = {(r['product_id'] or '').strip() for r in spec_rows}
    seen = set()
    for i, r in enumerate(todo_rows, start=2):
        pid = (r['product_id'] or '').strip()
        if not pid:
            errs.append('%s 第 %d 行 product_id 为空' % (os.path.basename(todo_path), i))
            continue
        if pid in seen:
            errs.append('%s 第 %d 行 product_id 重复：%s' % (os.path.basename(todo_path), i, pid))
        seen.add(pid)
        if pid in have:
            errs.append('%s 第 %d 行 [%s] 已经在 %s 里了 —— 补齐之后要把它从登记册里删掉，'
                        '否则登记册会变成一份永远不缩短的清单'
                        % (os.path.basename(todo_path), i, pid, SPECS_CSV))
        for col in ('official_url', 'blocker', 'next_step'):
            if not (r.get(col) or '').strip():
                errs.append('%s 第 %d 行 [%s] %s 为空 —— 缺口登记册的价值就在这三列，'
                            '少一列下一个人就得从零重找'
                            % (os.path.basename(todo_path), i, pid, col))
        url = (r.get('official_url') or '').strip()
        if url and not url.startswith('https://'):
            errs.append('%s 第 %d 行 [%s] official_url 不是 https 直链：%r'
                        % (os.path.basename(todo_path), i, pid, url))
    return errs


# ── pools.py 覆盖率（只报告，不判失败）────────────────────────────────────
def coverage(spec_rows):
    """返回 {'used','missing','pending','misuse'} —— pools.py 对本表的引用体检。

    分批上线时缺产品是**正常状态** —— notional.pending_products 会让对应的池
    整池 skip 并打印原因（build/exchanges.py 第 3 条规矩），不该记一条 FAIL。
    但 index_ref 被写进换算链是硬错误（C11 的第二半），它会算出量纲错误的正数。

    ⚠ `frozen` 与 `pending` 是**两件事**，不许合成一栏：
      pending = 还没测出来（下一个人应该去测）；
      frozen  = pools.py 声明的**永久张数口径**产品（`contracts_only`），
                基期常数永远留空，下一个人**不应该**去测。
    两者共用「base_price_local 为空」这一种表示，所以只有问过 pools.py 才分得开。
    合成一栏的代价是具体的：ICE_STIR / ICE_MLTIR 会永远挂在待办清单上，
    而每一轮都会有人去把 reCAPTCHA 重新撞一遍。
    """
    sys.path.insert(0, HERE)
    try:
        import pools
    except Exception as e:                                  # noqa: BLE001
        return {'used': [], 'missing': [], 'pending': [], 'frozen': [],
                'misuse': ['无法 import build/pools.py：%r' % (e,)]}
    by_id = {(r['product_id'] or '').strip(): r for r in spec_rows}
    used = pools.products_used()
    frozen = set(pools.contracts_only_products())
    return {
        'used': used,
        'frozen': sorted(frozen),
        'missing': [p for p in used if p not in by_id],
        'pending': [p for p in used
                    if p not in frozen and p in by_id
                    and _num(by_id[p]['base_price_local']) is None],
        'misuse': ['%s 是 level=index_ref 的指数点位参照行，却被 pools.py 的换算链引用 —— '
                   '它不是合约，乘出来的量纲是错的' % p
                   for p in used
                   if p in by_id and (by_id[p]['level'] or '').strip() == 'index_ref'],
    }


# ── C16：同一个池里的实测基准混用（只报告，不判失败）──────────────────────
def basis_mix(rows):
    """返回 {pool: {basis: 张数}}，只收 base_price_local 已实测的行。

    为什么只报告不报错：篮子行（basket_vw）与单合约行（avg_close）本来就测不出
    同一种数，硬要求一个池只用一种基准等于要求「要么全篮子、要么全逐合约」，
    那会逼人把已经测准的行删掉。但**混用必须知情** ——
    实测的口径差：EUREX_INDEX 的成交量加权隐含点位比 SX5E 月均收盘低 0.372%，
    期权腿差到 4.4%。这个差不会让任何一条检查报错，也不会在图上留下痕迹，
    所以唯一能让人知道的办法就是每次体检都把它打出来。
    """
    out = {}
    for r in rows:
        if _num(r['base_price_local']) is None:
            continue
        basis = (r['base_price_basis'] or '').strip()
        if basis not in MEASURED_BASES:
            continue
        for pool in [p.strip() for p in (r.get('pool') or '').split(',') if p.strip()]:
            out.setdefault(pool, {})
            out[pool][basis] = out[pool].get(basis, 0) + 1
    return out


# ── 自检：证明检查逻辑本身有效 ────────────────────────────────────────────
def selftest():
    """用合成行喂 C2 / C12，确认「重复 id」「区间重叠」「区间断档」真的会被抓住。

    为什么需要它：本次入库的 73 行里**没有一个多代规格组**（没查到任何一个合约的
    乘数变更过），于是 _check_effective 的主分支在真实数据上一次都没被执行。
    一段从没跑过的检查代码，与没有这段代码是一回事 —— 等到真有合约改规格那天，
    没人知道它是不是坏的。
    """
    def row(pid, grp, ef='', et='', **kw):
        base = dict(product_id=pid, zh='合成', exchange='X', pool='p', level='contract',
                    contract_name='', underlying_symbol='', kind='contract', ccy='USD',
                    multiplier='10', mult_unit='USD/点', base_month=BASE_MONTH,
                    base_price_basis='avg_close', base_price_local='100',
                    base_notional_per_unit_local='1000',
                    notional_source='reconstructed', price_id='', spec_group=grp,
                    effective_from=ef, effective_to=et, source='s', evidence='e', notes='n')
        base.update(kw)
        return base

    cases = [
        ('区间重叠', [row('A1', 'G', '2019-01', '2020-06'), row('A2', 'G', '2020-06')], '重叠'),
        ('区间断档', [row('B1', 'G', '2019-01', '2020-06'), row('B2', 'G', '2020-09')], '断档'),
        ('两行都开口', [row('C1', 'G', '2019-01'), row('C2', 'G', '2020-09')], '最后的那一代'),
        ('多代缺 from', [row('D1', 'G', '2019-01', '2020-06'), row('D2', 'G')], 'effective_from'),
        ('product_id 重复', [row('E1', 'G1'), row('E1', 'G2')], '重复'),
        ('乘数为 0', [row('F1', 'G1', multiplier='0')], '正数'),
        ('基期价为负', [row('H1', 'G1', base_price_local='-3')], '正数'),
        ('冗余列对不上', [row('I1', 'G1', base_notional_per_unit_local='999')], '对不上'),
        ('留空却无 📌', [row('J1', 'G1', base_price_local='', base_price_basis='',
                             base_notional_per_unit_local='', notional_source='',
                             notes='忘了写')], '📌'),
        ('基准非法', [row('K1', 'G1', base_price_basis='eom_close')], '非法'),
        ('notional 乘数≠1', [row('L1', 'G1', kind='notional', base_price_local='1',
                                 base_price_basis='definitional',
                                 notional_source='official_notional',
                                 base_notional_per_unit_local='10')], '必须是 1'),
        ('index_ref 乘数≠1', [row('M1', 'G1', level='index_ref')], '必须是 1'),
        ('基期月写错', [row('N1', 'G1', base_month='2020-01')], '基期锁死'),
        # ↓ 本轮新增的三条（C14 / C15），合成行同样要证明它们真的会拦
        ('篮子行乘数≠1', [row('O1', 'G1', level='pool_product', multiplier='100',
                              base_price_basis='basket_vw',
                              notional_source='official_notional',
                              base_price_local='100',
                              base_notional_per_unit_local='10000')], '算两遍'),
        ('来源取值非法', [row('P0', 'G1', notional_source='官方')], 'notional_source'),
        ('有价却无来源', [row('Q1', 'G1', notional_source='')], '没写 notional_source'),
        ('留空却写了来源', [row('R1', 'G1', base_price_local='', base_price_basis='',
                                base_notional_per_unit_local='',
                                notional_source='reconstructed', notes='📌')], '不该有来源'),
        ('avg_close 却标面值', [row('S1', 'G1', notional_source='definitional')], '矛盾'),
        ('definitional 却标重建',
         [row('T1', 'G1', base_price_basis='definitional', multiplier='1000',
              base_price_local='1', base_notional_per_unit_local='1000',
              notional_source='reconstructed')], '矛盾'),
    ]
    ok = True
    for name, rows_, want in cases:
        errs = check_specs(rows_, 'selftest.csv')
        hit = [e for e in errs if want in e]
        print('  %-16s %s  %s' % (name, 'PASS' if hit else 'FAIL',
                                  hit[0][:96] if hit else '(没抓住，期望包含 %r)' % want))
        ok = ok and bool(hit)
    # 反向用例 1：一张干净的多代规格表必须一条错都不报
    clean = [row('P1', 'G', '2019-01', '2020-06'), row('P2', 'G', '2020-07')]
    errs = check_specs(clean, 'selftest.csv')
    print('  %-16s %s  %s' % ('干净的两代表', 'PASS' if not errs else 'FAIL',
                              '无错误' if not errs else errs[0][:96]))
    ok = ok and not errs

    # 反向用例 2：本轮新增的两个基准取值必须是**合法**的，别只证明了会拦不证明会放行
    clean2 = [
        row('U1', 'GU', level='pool_product', multiplier='1', base_price_basis='basket_vw',
            base_price_local='709693.1443317888',
            base_notional_per_unit_local='709693.1443317888',
            notional_source='definitional'),
        row('U2', 'GU2', level='pool_product', multiplier='1',
            base_price_basis='month_midpoint', base_price_local='2542.4369',
            base_notional_per_unit_local='2542.4369', notional_source='reconstructed'),
        row('U3', 'GU3', level='pool_product', multiplier='1', base_price_basis='basket_vw',
            base_price_local='45.60788603311065',
            base_notional_per_unit_local='45.60788603311065', kind='share',
            notional_source='official_notional'),
    ]
    errs2 = check_specs(clean2, 'selftest.csv')
    print('  %-16s %s  %s' % ('新基准的合法行', 'PASS' if not errs2 else 'FAIL',
                              '无错误' if not errs2 else errs2[0][:96]))
    return ok and not errs2


# ── 入口 ──────────────────────────────────────────────────────────────────
def main(argv):
    if '--selftest' in argv:
        print('== check_specs 自检（合成行，不读 series/）==')
        ok = selftest()
        print('自检%s' % ('通过' if ok else '未通过'))
        return 0 if ok else 1

    try:
        spec_path, spec_rows = load_rows(
            SERIES, SPECS_CSV, REQUIRED_BY_NOTIONAL + REQUIRED_EXTRA)
    except SpecCheckError as e:
        print('FAIL %s' % e)
        return 1

    errs = check_specs(spec_rows, spec_path)

    todo_rows = []
    try:
        todo_path, todo_rows = load_rows(SERIES, TODO_CSV, TODO_REQUIRED)
        errs += check_todo(spec_rows, todo_rows, todo_path)
    except SpecCheckError as e:
        # 登记册缺席不是错误：所有产品都补齐之后它本来就该消失
        print('注：%s' % e)

    by_level = {}
    for r in spec_rows:
        by_level[(r['level'] or '?').strip()] = by_level.get((r['level'] or '?').strip(), 0) + 1
    priced = sum(1 for r in spec_rows if _num(r['base_price_local']) is not None)
    print('%s：%d 行（%s），基期价格已实测 %d 行、待测 %d 行'
          % (SPECS_CSV, len(spec_rows),
             '，'.join('%s %d' % kv for kv in sorted(by_level.items())),
             priced, len(spec_rows) - priced))
    by_src = {}
    for r in spec_rows:
        s = (r.get('notional_source') or '').strip()
        if s:
            by_src[s] = by_src.get(s, 0) + 1
    if by_src:
        print('  名义额来源：%s'
              % '，'.join('%s %d' % kv for kv in sorted(by_src.items())))
    if todo_rows:
        print('%s：%d 行缺口待补' % (TODO_CSV, len(todo_rows)))

    # C16：同池混用实测基准 —— 只报告。不打出来就没人知道自己在比两个不同口径的数
    mixed = {p: m for p, m in basis_mix(spec_rows).items() if len(m) > 1}
    if mixed:
        print('注：以下池里混用了多种实测基准（允许，但份额是两种口径拼出来的，'
              '实测差 0.4%~4%，见模块 docstring 的 basket_vw 一节）：')
        for pool in sorted(mixed):
            print('  · %s：%s' % (pool, '，'.join('%s %d 行' % kv
                                                 for kv in sorted(mixed[pool].items()))))

    cov = coverage(spec_rows)
    errs += cov['misuse']                # C11 第二半：这条是硬错误
    if cov['used']:
        print('pools.py 引用的 %d 个产品：已入表 %d，缺 %d，其中基期价格待测 %d'
              % (len(cov['used']), len(cov['used']) - len(cov['missing']),
                 len(cov['missing']), len(cov['pending'])))
        if cov['missing']:
            print('  缺（对应的池会被 notional.pending_products 整池 skip）：%s'
                  % ', '.join(cov['missing']))
        if cov.get('frozen'):
            print('  ⛔ 永久张数口径（pools.py 的 contracts_only，**不算待测、不许再去补**）：%s'
                  % ', '.join(cov['frozen']))

    if errs:
        print('\nFAIL %d 条：' % len(errs))
        for e in errs:
            print('  · %s' % e)
        return 1
    print('\nOK 全部检查通过')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
