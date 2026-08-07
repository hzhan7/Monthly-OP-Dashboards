# -*- coding: utf-8 -*-
"""series/_specs_part_*.csv → series/contract_specs.csv 的合并器（可重复执行）。

用法:
    python3 build/merge_specs.py            # 合并 series/ 下全部 part 文件，然后跑 check_specs
    python3 build/merge_specs.py --dry-run  # 只打印会改什么，不落盘、不跑体检
    python3 build/merge_specs.py --no-check # 落盘但不跑 check_specs（调试用，正常别用）
    python3 build/merge_specs.py --selftest # 用合成表验证合并逻辑本身（完全不碰 series/）
    python3 build/merge_specs.py _specs_part_us.csv _specs_part_asx_mx.csv
                                            # 只合并指定的几份 —— 别的 agent 正在写新 part
                                            # 时用它框住范围，别把写了一半的文件读进来

退出码：0 全过；1 合并本身没问题但 check_specs 没通过；2 合并阶段就被拦下（冲突/校验失败）。

━━ 为什么要有这个脚本 ━━
基期常数是多个 agent **并行**实测出来的：每个 agent 只写自己的
`series/_specs_part_<批次>.csv`，谁都不直接改主表（几个进程写同一个文件会互相覆盖）。
合并这一步若手工做，最典型的两种错恰好都是「错了图上看不出来」的那一类：
  · 把主表里**已经实测过**的值覆盖成新算的 —— 旧值本来是对的，柱子高一截，看着像真的；
  · 两个 part 文件对同一个 product_id 给了**不同**的值，随手取了后读到的那个。
所以本脚本的默认行为是 **只填空、绝不覆盖**，一切冲突当场报错退出（码 2），
不允许任何一种「静默取其一」。

━━ 幂等（硬要求）━━
同一批 part 文件跑一次与跑 N 次，落盘结果**字节一致**。第二轮 part 文件落地后，
主线程会把全部 part（含第一轮）一起再跑一遍，所以：
  · 值已填好且与 part 一致 → 无操作（不是「再填一次」）；不一致 → 报错，不是覆盖
  · source / evidence 是**追加**语义，追加前先查子串，已在里面就不再追加
  · notes 的合并批注带固定标记（MERGE_MARK / RECHECK_MARK），认标记跳过
未改动的单元格原样透传（读进来就是字符串，不做任何数值格式化）——
csv 往返已验证与原文件逐字节相同，所以 git diff 里只会出现真正被改的那几行。

━━ part 文件的约定（agent 侧的输出契约）━━
必需列：product_id, base_price_local, base_ccy, basket_constant, source_url, computed_note
可选列：base_price_basis, notional_source, multiplier —— **给了就以它为准**。
    这三列是给下一批 agent 用的：只要在 part 文件里写清楚，就不需要回来改本脚本。
`base_price_local` 留空 = 这一轮仍没测出来。这种行不填值，但 `source_url` 与
`computed_note` 照样并进 source / evidence —— 「排除过哪些路径」是本轮最贵的产出，
丢了下一个人就得从零重找。

━━ 合并时自动补齐与校验的东西 ━━
1. **篮子行 multiplier = 1**（part 行给了 basket_constant 就算篮子行）。
   篮子常数 = Σ(成员张数 × 成员单张名义额) ÷ Σ张数，**成员各自的乘数已经并进去了**；
   主表再写一个 ≠1 的乘数，check_specs 的 C5 恒等式
   （base_notional_per_unit_local = multiplier × base_price_local）就会把乘数算两遍。
   空 → 补 1；已是 1 → 不动；是别的数 → 报错。
2. `basket_constant` 必须与 `base_price_local` 相等（乘数 1 ⇒ 两者同一个数），
   否则说明 agent 那边这两列不同源，直接拦下。
3. `base_notional_per_unit_local` = multiplier × base_price_local，顺手写上（C5 要用）。
4. `ccy` 与 part 的 `base_ccy` 必须一致（主表空则填）—— 币种错了会在 fx 那一跳
   悄悄换个汇率，量级仍然合理，图上看不出来。
5. `base_price_basis` / `notional_source`：part 显式给了就用；没给就查 CLASSIFY；
   都没有 → **报错**（不猜）。合法取值由 check_specs 定义，本脚本不另立一套。

━━ CLASSIFY 是什么、为什么不做关键词推断 ━━
「这个常数是怎么来的」是**读了整段 computed_note 之后的判断**，不是能从字符串里
正则出来的东西。举个真实的坑：EUREX_RATES 的 note 里出现了 "Capital Volume ÷ 张数"，
但那是作为**对照口径**被写下来的（正文明确说了选面值口径、不选它）——
任何关键词推断都会把它判成 official_notional，而且判错了没人会发现。
所以本脚本对每个 product_id 只认两个来源：part 文件里的显式列，或 CLASSIFY 里
带一句理由的登记。两者都没有就退出码 2，把判断交回给人。
"""

import argparse
import csv
import datetime
import glob
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SERIES = os.path.join(ROOT, 'series')

sys.path.insert(0, HERE)
import check_specs                                          # noqa: E402

SPECS_CSV = check_specs.SPECS_CSV
PART_GLOB = '_specs_part_*.csv'

NEW_COL = 'notional_source'
NEW_COL_AFTER = 'base_notional_per_unit_local'

PART_REQUIRED = ('product_id', 'base_price_local', 'base_ccy',
                 'basket_constant', 'source_url', 'computed_note')
PART_OPTIONAL = ('base_price_basis', 'notional_source', 'multiplier')

# 数值相等判据：这些常数是逐位复算出来的，只允许浮点解析的最后一位差
REL_TOL = 1e-12

MERGE_MARK = '✅ 基期常数已合并入表'
RECHECK_MARK = '🔁 基期常数复查'
URL_SEP = ' | '


# ── 每个产品的口径登记 ────────────────────────────────────────────────────
# (base_price_basis, notional_source, 一句话理由)
#
# base_price_basis 与 notional_source 是**两件正交的事**，别把它们读成一件：
#   base_price_basis = 基期价格那一跳是怎么测出来的（avg_close / basket_vw /
#                      month_midpoint / definitional）
#   notional_source  = 这个名义额常数的来源性质（官方直发 / 面值定义 / 乘数×价格重建）
# 所以 CME_RATES 这种「按面值计、但跨 65 个成员按张数加权」的行，
# 两列分别是 basket_vw + definitional —— 合起来才读得出它到底是个什么数。
#
# 为什么篮子行一律 basket_vw、哪怕权重恰好退化：MX_BOND 的成员面值全是 C$100,000，
# 常数与权重无关；MX_STIR 当月只有 BAX 有量。但基准记的是**方法**不是这一期的巧合，
# 跟着巧合走会让「同样的算法」在表里出现两种标注，下一个人无从判断哪个才是惯例。
CLASSIFY = {
    'US_CASH_EQUITY_SHARE': (
        'basket_vw', 'official_notional',
        'Cboe 官方月度市场统计的 Total Notional ÷ Total Shares：名义额是官方直发的，'
        '相除得到的是按成交股数加权的均价，不是收盘价的月内等权平均'),
    'CME_RATES': (
        'basket_vw', 'definitional',
        '65 个成员各按 CME/CBOT 规则手册的**面值**计名义额（不乘结算价），'
        '再按 2019-01 ADV 加权：价格项不存在，但常数依赖权重'),
    'CME_EQUITY_INDEX': (
        'basket_vw', 'reconstructed',
        '成员名义额 = 官方乘数 × 该指数 2019-01 月均收盘，再按 ADV 加权 —— '
        '整条链都是重建的'),
    'CME_FX': (
        'basket_vw', 'reconstructed',
        '成员面值以基础货币计（definitional），但折成美元用的汇率**就是 FX 期货的标的价格**，'
        '这一跳是重建不是记账币换算，所以整行算 reconstructed'),
    'EUREX_RATES': (
        'basket_vw', 'definitional',
        'Eurex 规则书面值（EUR 100,000 / CHF 100,000 / EUR 1,000,000）按 2019-01 张数加权；'
        'CHF 腿折 EUR 只是记账币换算，不是标的价格，故仍是面值口径。'
        '注：agent 在 part 文件里建议 base_price_basis=definitional，但那一列描述的是'
        '价格那一跳，而本行的常数依赖跨成员权重（不是任何一张合约的面值定义），'
        '「面值口径」这件事由 notional_source=definitional 承载'),
    'EUREX_INDEX': (
        'basket_vw', 'official_notional',
        'Eurex 官方月度统计 Capital Volume EUR ÷ Traded Contracts —— 名义额是官方直发的；'
        '隐含的价格项是成交量加权成交价，比 SX5E 的月均收盘低 0.372%（口径差已在 notes 留痕）'),
    'EUREX_EQUITY': (
        'basket_vw', 'official_notional',
        '同 EUREX_INDEX，取「Equity Derivatives」分节的 Capital Volume ÷ Traded Contracts'),
    'MX_STIR': (
        'basket_vw', 'definitional',
        'MX 存档规则书 Rule 15 的面值按 2019-01 张数加权（当月只有 BAX 有量，'
        '权重退化但方法仍是加权）'),
    'MX_BOND': (
        'basket_vw', 'definitional',
        'MX 存档规则书 Rule 15 的面值按 2019-01 张数加权（有量的 CGF/CGB 面值同为 '
        'C$100,000，常数对权重误差免疫）'),
}


class MergeError(RuntimeError):
    """合并阶段就该停下来的问题：冲突、缺登记、形状不对。退出码 2。"""


# ── 小工具 ────────────────────────────────────────────────────────────────
def _s(v):
    return (v or '').strip()


def _f(v, what):
    """字符串 → float。空 → None。不是数字 → MergeError（不是静默跳过）。"""
    s = _s(v)
    if s == '':
        return None
    try:
        return float(s)
    except ValueError:
        raise MergeError('%s=%r 不是数字' % (what, s))


def _same(a, b):
    """两个单元格是不是同一个值：能都解析成数就按相对误差比，否则按去空白字符串比。"""
    sa, sb = _s(a), _s(b)
    if sa == sb:
        return True
    try:
        fa, fb = float(sa), float(sb)
    except ValueError:
        return False
    if fa == fb:
        return True
    scale = max(abs(fa), abs(fb))
    return scale > 0 and abs(fa - fb) / scale <= REL_TOL


def _union_urls(old, new):
    """把 new 里的 URL 并进 old，保持 old 的顺序，只追加缺的那些。"""
    have = [u for u in _s(old).split(URL_SEP) if u.strip()]
    for u in [x.strip() for x in _s(new).split(URL_SEP) if x.strip()]:
        if u not in have:
            have.append(u)
    return URL_SEP.join(have)


# ── 读 part 文件 ──────────────────────────────────────────────────────────
def read_parts(paths):
    """读全部 part 文件 → {product_id: payload}。

    同一个 product_id 出现在多个 part（或同一个 part 里出现两次）时：
      · 值列（价格/币种/篮子常数/口径/乘数）不一致 → MergeError，绝不取其一
      · 文本列（source_url / computed_note）不一致 → 取并集（并集不是「取其一」，
        两边的证据都留着，谁也没被丢掉）
    """
    merged = {}
    for path in paths:
        with open(path, newline='', encoding='utf-8') as f:
            rows = list(csv.DictReader(f))
        if not rows:
            raise MergeError('%s 是空表' % path)
        miss = [c for c in PART_REQUIRED if c not in rows[0]]
        if miss:
            raise MergeError('%s 缺列 %s（拿到 %s）'
                             % (os.path.basename(path), miss, list(rows[0].keys())))
        for i, r in enumerate(rows, start=2):
            pid = _s(r.get('product_id'))
            if not pid:
                raise MergeError('%s 第 %d 行 product_id 为空' % (os.path.basename(path), i))
            cur = {c: _s(r.get(c)) for c in PART_REQUIRED}
            for c in PART_OPTIONAL:
                cur[c] = _s(r.get(c))
            cur['_from'] = [os.path.basename(path)]
            prev = merged.get(pid)
            if prev is None:
                merged[pid] = cur
                continue
            # 同一个 product_id 在多个 part 里出现是**常态**：第一轮写「没测出来」，
            # 第二轮把值补上，两份都在盘上。所以空 = 没意见，让有值的那份赢；
            # 只有两边**都有值且不同**才是真冲突。
            for c in ('base_price_local', 'base_ccy', 'basket_constant',
                      'base_price_basis', 'notional_source', 'multiplier'):
                a, b = prev[c], cur[c]
                if a == '' or b == '' or _same(a, b):
                    prev[c] = a or b
                    continue
                raise MergeError(
                    '%s 在 %s 与 %s 里都出现，且 %s 不一致（%r vs %r）—— '
                    '两个 agent 对同一个产品算出了不同的数，必须先弄清谁对，'
                    '合并器不许静默取其一'
                    % (pid, ' + '.join(prev['_from']), os.path.basename(path),
                       c, a, b))
            prev['source_url'] = _union_urls(prev['source_url'], cur['source_url'])
            if cur['computed_note'] and cur['computed_note'] not in prev['computed_note']:
                prev['computed_note'] = (prev['computed_note'] + ' ‖ '
                                         + cur['computed_note']).strip(' ‖ ')
            prev['_from'].append(os.path.basename(path))
    return merged


# ── notional_source 的回填规则（给主表既有行用）────────────────────────────
def infer_notional_source(row):
    """既有行的 notional_source 回填。只在能确定时返回值，否则返回 ''。

    判据全部来自行本身已经落库的口径，不做关键词猜测：
      · kind=notional  → official_notional：源列本身就是官方发布的金额（成交额/AUM/募资额），
                         名义额没有任何一步是重建的，价格项按定义 = 1
      · base_price_basis=definitional 且 kind≠notional → definitional：面值口径
                         （国债/利率期货按面值计，不乘结算价）
      · base_price_basis=avg_close    → reconstructed：乘数 × 月均收盘，整条链是重建的
      · 其余（basis 为空 = 基期价还没测出来）→ ''，等测出来那天连同值一起写
    """
    kind = _s(row.get('kind'))
    basis = _s(row.get('base_price_basis'))
    px = _s(row.get('base_price_local'))
    if px == '':
        return ''                       # 没有值就不该有来源（check_specs C15 会核）
    if kind == 'notional':
        return 'official_notional'
    if basis == 'definitional':
        return 'definitional'
    if basis in ('avg_close', 'month_midpoint'):
        return 'reconstructed'
    return ''


# ── 合并主体 ──────────────────────────────────────────────────────────────
def merge_rows(rows, parts, today):
    """就地改 rows（list of dict），返回 changes 列表。冲突抛 MergeError。"""
    by_id = {}
    for r in rows:
        by_id[_s(r.get('product_id'))] = r
    changes = []
    unregistered = []       # 攒着一起报：一次跑清全部待裁决的行，不要一轮只暴露一个

    def note(pid, what):
        changes.append('%s %s' % (pid, what))

    # 1) 新列回填（既有行）——先做，part 行随后可能覆盖为更精确的值
    for r in rows:
        if _s(r.get(NEW_COL)) == '':
            guess = infer_notional_source(r)
            if guess:
                r[NEW_COL] = guess
                note(_s(r['product_id']), '回填 %s=%s' % (NEW_COL, guess))

    # 2) 逐个 part 行合并
    for pid in sorted(parts):
        p = parts[pid]
        src = ' + '.join(p['_from'])
        row = by_id.get(pid)
        if row is None:
            raise MergeError(
                '%s（来自 %s）在 %s 里没有对应行 —— 本脚本只填既有行的空位，'
                '不凭 part 文件新建产品（zh/pool/level/kind 这些列 part 文件里没有，'
                '猜出来的行会静默进入 pools 的换算链）。请先在主表加行再合并。'
                % (pid, src, SPECS_CSV))

        px_part = _f(p['base_price_local'], '%s.base_price_local' % pid)
        bc_part = _f(p['basket_constant'], '%s.basket_constant' % pid)
        level = _s(row.get('level'))

        # 币种：主表空则填，非空则必须一致
        if p['base_ccy']:
            if _s(row.get('ccy')) == '':
                row['ccy'] = p['base_ccy']
                note(pid, '填 ccy=%s' % p['base_ccy'])
            elif _s(row.get('ccy')) != p['base_ccy']:
                raise MergeError('%s 币种冲突：主表 ccy=%r，%s 给的是 base_ccy=%r —— '
                                 '币种错了只会在 fx 那一跳换个汇率，量级仍然合理，图上看不出来'
                                 % (pid, _s(row.get('ccy')), src, p['base_ccy']))

        # source / evidence 一律追加（不管这一轮有没有测出值：排除过的路径也是产出）
        if p['source_url']:
            new_src = _union_urls(row.get('source'), p['source_url'])
            if new_src != _s(row.get('source')):
                row['source'] = new_src
                note(pid, '追加 source')
        if p['computed_note'] and p['computed_note'] not in _s(row.get('evidence')):
            old = _s(row.get('evidence'))
            row['evidence'] = ((old + ' ——【%s 合并 %s】' % (today, src)) if old
                               else '【%s 合并 %s】' % (today, src)) + p['computed_note']
            note(pid, '追加 evidence')

        if px_part is None:
            # 这一轮仍没测出来：不填值，只在 notes 里留一句「复查过了」
            if bc_part is not None:
                raise MergeError('%s 给了 basket_constant=%r 却没给 base_price_local —— '
                                 '篮子常数就是基期价格（乘数 1），两列不同源说明上游算错了'
                                 % (pid, p['basket_constant']))
            if RECHECK_MARK not in _s(row.get('notes')):
                row['notes'] = ('%s（%s，来源 %s）：仍未取到，本轮实测过的路径与排除项'
                                '已写进 evidence 列。 ' % (RECHECK_MARK, today, src)
                                + _s(row.get('notes')))
                note(pid, '标记复查（仍未取到）')
            continue

        if px_part <= 0:
            raise MergeError('%s base_price_local=%r 必须是正数' % (pid, p['base_price_local']))

        # 篮子行：乘数必须是 1，且 basket_constant == base_price_local
        is_basket = bc_part is not None
        if is_basket:
            if level != 'pool_product':
                raise MergeError('%s 带了 basket_constant，但主表 level=%r —— '
                                 '篮子常数只能出现在 level=pool_product 的行上'
                                 % (pid, level))
            if abs(bc_part - px_part) > REL_TOL * max(abs(bc_part), abs(px_part), 1.0):
                raise MergeError('%s basket_constant=%r 与 base_price_local=%r 对不上 —— '
                                 '篮子行乘数是 1，两者必须是同一个数'
                                 % (pid, p['basket_constant'], p['base_price_local']))
            want_mult = '1'
            if p['multiplier'] and not _same(p['multiplier'], '1'):
                raise MergeError('%s 是篮子行却给了 multiplier=%r —— 成员乘数已经并进'
                                 '篮子常数，再乘一次 check_specs 的 C5 恒等式就会把它算两遍'
                                 % (pid, p['multiplier']))
            cur_mult = _s(row.get('multiplier'))
            if cur_mult == '':
                row['multiplier'] = want_mult
                note(pid, '补 multiplier=1（篮子行）')
            elif not _same(cur_mult, want_mult):
                raise MergeError('%s 是篮子行，主表 multiplier=%r 不是 1 —— '
                                 '篮子常数里已经含各成员的乘数，再乘一次就是重复计数'
                                 % (pid, cur_mult))
        elif p['multiplier']:
            cur_mult = _s(row.get('multiplier'))
            if cur_mult == '':
                row['multiplier'] = p['multiplier']
                note(pid, '填 multiplier=%s' % p['multiplier'])
            elif not _same(cur_mult, p['multiplier']):
                raise MergeError('%s 乘数冲突：主表 %r，%s 给的 %r'
                                 % (pid, cur_mult, src, p['multiplier']))

        mult = _f(row.get('multiplier'), '%s.multiplier(主表)' % pid)
        if mult is None or mult <= 0:
            raise MergeError('%s 主表 multiplier=%r 必须是正数' % (pid, row.get('multiplier')))

        # 口径两列：part 显式 > CLASSIFY > 报错
        basis, nsrc = p['base_price_basis'], p['notional_source']
        if not basis or not nsrc:
            reg = CLASSIFY.get(pid)
            if reg is None:
                unregistered.append((pid, src, p['computed_note'][:220]))
                continue
            basis = basis or reg[0]
            nsrc = nsrc or reg[1]
        if basis not in check_specs.PRICE_BASIS:
            raise MergeError('%s base_price_basis=%r 非法，只能是 %s'
                             % (pid, basis, list(check_specs.PRICE_BASIS)))
        if nsrc not in check_specs.NOTIONAL_SOURCES:
            raise MergeError('%s notional_source=%r 非法，只能是 %s'
                             % (pid, nsrc, list(check_specs.NOTIONAL_SOURCES)))

        # 值：只填空，不覆盖
        filled_now = False
        cur_px = _s(row.get('base_price_local'))
        if cur_px == '':
            row['base_price_local'] = p['base_price_local']
            filled_now = True
            note(pid, '填 base_price_local=%s' % p['base_price_local'])
        elif not _same(cur_px, p['base_price_local']):
            raise MergeError(
                '%s base_price_local 冲突：主表已有 %r，%s 给的是 %r —— '
                '主表的值是先前实测过的，只填空不覆盖。要改必须人工裁决后手改，'
                '并在 notes 里按 CBOE_VIX_FUT 那条的写法留下「⚠ 日期 修：旧值→新值 + 理由」'
                % (pid, cur_px, src, p['base_price_local']))

        want_unit = mult * px_part
        cur_unit = _s(row.get('base_notional_per_unit_local'))
        unit_txt = (p['base_price_local'] if abs(mult - 1.0) <= REL_TOL
                    else repr(want_unit))
        if cur_unit == '':
            row['base_notional_per_unit_local'] = unit_txt
            note(pid, '填 base_notional_per_unit_local=%s' % unit_txt)
        else:
            cu = _f(cur_unit, '%s.base_notional_per_unit_local' % pid)
            if cu is None or abs(cu - want_unit) > REL_TOL * max(abs(want_unit), 1.0):
                raise MergeError('%s base_notional_per_unit_local=%r 与 multiplier × '
                                 'base_price_local=%r 对不上' % (pid, cur_unit, want_unit))

        for col, val in (('base_price_basis', basis), (NEW_COL, nsrc)):
            cur = _s(row.get(col))
            if cur == '':
                row[col] = val
                note(pid, '填 %s=%s' % (col, val))
            elif cur != val:
                raise MergeError('%s %s 冲突：主表 %r，本次要写 %r'
                                 % (pid, col, cur, val))

        if filled_now and MERGE_MARK not in _s(row.get('notes')):
            row['notes'] = (
                '%s（%s，来源 %s；取数代码在 build/basefill/）：base_price_basis=%s、'
                'notional_source=%s，逐位复算记录见 evidence 列。以下是填入前的旧注，'
                '其中「📌 未取到 / 未找到」已被本次实测取代，保留是为了留住当时排除过的路径。 '
                % (MERGE_MARK, today, src, basis, nsrc) + _s(row.get('notes')))
            note(pid, '写入合并批注')

    if unregistered:
        lines = ['%d 个产品带了值但没登记口径，这一轮**什么都没写**（不做半张表）：'
                 % len(unregistered)]
        for pid, src, head in unregistered:
            lines.append('  · %s（%s）base_price_basis / notional_source 都得有人定。'
                         'computed_note 开头：%s…' % (pid, src, head))
        lines.append('这两件事必须有人**读完 computed_note** 才判得了 —— 关键词推断会把'
                     '「作为对照被否掉的口径」判成正选（EUREX_RATES 的 note 里就出现了'
                     ' "Capital Volume ÷ 张数"，而正文明确选的是面值口径），判错了没人会发现。')
        lines.append('二选一：① 让 part 文件多写 base_price_basis / notional_source 两列'
                     '（agent 自己最清楚它算的是什么）；② 在 build/merge_specs.py 的 '
                     'CLASSIFY 里登记并写明理由。合法取值见 build/check_specs.py 的模块 '
                     'docstring（四个基准 / 三种来源各自何时该用）。')
        raise MergeError('\n'.join(lines))

    return changes


# ── 落盘 ──────────────────────────────────────────────────────────────────
def load_specs_table(series_dir):
    path = os.path.join(series_dir, SPECS_CSV)
    if not os.path.exists(path):
        raise MergeError('缺 %s' % path)
    with open(path, newline='', encoding='utf-8') as f:
        rd = csv.DictReader(f)
        rows = list(rd)
        header = list(rd.fieldnames or [])
    if not rows:
        raise MergeError('%s 是空表' % path)
    if NEW_COL not in header:
        if NEW_COL_AFTER not in header:
            raise MergeError('%s 里没有 %s 列，插不进 %s' % (SPECS_CSV, NEW_COL_AFTER, NEW_COL))
        header.insert(header.index(NEW_COL_AFTER) + 1, NEW_COL)
        for r in rows:
            r.setdefault(NEW_COL, '')
    return path, header, rows


def write_specs_table(path, header, rows):
    """原子写：先写同目录临时文件再 rename，中途崩了不会留下半张表。"""
    d = os.path.dirname(path)
    fd, tmp = tempfile.mkstemp(dir=d, prefix='.merge_specs_', suffix='.csv')
    try:
        with os.fdopen(fd, 'w', newline='', encoding='utf-8') as f:
            w = csv.writer(f, lineterminator='\n')
            w.writerow(header)
            for r in rows:
                w.writerow([r.get(c, '') or '' for c in header])
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def run(series_dir, dry_run=False, today=None, quiet=False, only=None):
    """合并一轮。返回 (changes, part_paths)。冲突抛 MergeError。

    only=None 时合并 series/ 下**全部** part 文件（默认，也是第二轮该用的姿势）；
    传一串文件名/路径则只合并这几份 —— 上一轮的 part 还在盘上、这一轮的 agent
    正在写的时候，用它把范围框住，别把写了一半的文件读进来。
    """
    today = today or datetime.date.today().isoformat()
    if only:
        parts_paths = []
        for p in only:
            full = p if os.path.isabs(p) else os.path.join(series_dir, os.path.basename(p))
            if not os.path.exists(full):
                raise MergeError('指定的 part 文件不存在：%s' % full)
            parts_paths.append(full)
        parts_paths = sorted(set(parts_paths))
    else:
        parts_paths = sorted(glob.glob(os.path.join(series_dir, PART_GLOB)))
    if not parts_paths:
        if not quiet:
            print('没有找到 %s —— 无事可做' % os.path.join(series_dir, PART_GLOB))
    path, header, rows = load_specs_table(series_dir)
    parts = read_parts(parts_paths) if parts_paths else {}
    changes = merge_rows(rows, parts, today)

    if not quiet:
        print('part 文件 %d 个：%s'
              % (len(parts_paths), ', '.join(os.path.basename(p) for p in parts_paths)))
        n_val = sum(1 for p in parts.values() if _s(p['base_price_local']))
        print('part 行 %d 条，其中带值的 %d 条' % (len(parts), n_val))
        if changes:
            print('改动 %d 处：' % len(changes))
            for c in changes:
                print('  · %s' % c)
        else:
            print('改动 0 处（幂等：这批 part 已经合并过了）')

    if dry_run:
        if not quiet:
            print('--dry-run：不落盘')
    else:
        write_specs_table(path, header, rows)
        if not quiet:
            print('写入 %s：%d 行、%d 列' % (path, len(rows), len(header)))
    return changes, parts_paths


# ── 自检：证明合并逻辑本身是有效的 ────────────────────────────────────────
def selftest():
    """用合成表喂每一条拦截规则，确认它们真的会拦；再验一遍幂等。

    为什么必须有：本脚本的全部价值就是「该拦的时候拦住」。而正常路径上（把空位填上）
    它跑得对不对一眼就能看出来，被拦的那几条路径**在真实数据上一次都不会被执行**——
    一段从没跑过的拦截代码，与没有这段代码是一回事。
    """
    ok = True
    base_header = ['product_id', 'zh', 'exchange', 'pool', 'level', 'contract_name',
                   'underlying_symbol', 'kind', 'ccy', 'multiplier', 'mult_unit',
                   'base_month', 'base_price_basis', 'base_price_local',
                   'base_notional_per_unit_local', 'price_id', 'spec_group',
                   'effective_from', 'effective_to', 'source', 'evidence', 'notes']

    def spec_row(pid, **kw):
        r = dict.fromkeys(base_header, '')
        r.update(product_id=pid, zh='合成', exchange='X', pool='p', level='pool_product',
                 kind='contract', ccy='USD', multiplier='1',
                 mult_unit='张', base_month=check_specs.BASE_MONTH,
                 spec_group=pid, source='s', evidence='', notes='📌 未取到')
        r.update(kw)
        return r

    def part_row(pid, **kw):
        r = {c: '' for c in PART_REQUIRED + PART_OPTIONAL}
        r['product_id'] = pid
        r.update(kw)
        return r

    def mkdir_with(spec_rows, part_files):
        d = tempfile.mkdtemp(prefix='merge_specs_selftest_')
        with open(os.path.join(d, SPECS_CSV), 'w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, base_header, lineterminator='\n')
            w.writeheader()
            w.writerows(spec_rows)
        for name, prows in part_files.items():
            with open(os.path.join(d, name), 'w', newline='', encoding='utf-8') as f:
                w = csv.DictWriter(f, list(PART_REQUIRED + PART_OPTIONAL),
                                   lineterminator='\n')
                w.writeheader()
                w.writerows(prows)
        return d

    good_part = dict(base_price_local='7.5', base_ccy='USD', basket_constant='7.5',
                     source_url='https://x/a', computed_note='合成',
                     base_price_basis='basket_vw', notional_source='definitional')

    cases = [
        ('两 part 值不同',
         [spec_row('A1')],
         {'_specs_part_1.csv': [part_row('A1', **good_part)],
          '_specs_part_2.csv': [part_row('A1', **dict(good_part, base_price_local='8.5',
                                                      basket_constant='8.5'))]},
         '不一致'),
        ('主表已有值且不同',
         [spec_row('A1', base_price_local='9', base_notional_per_unit_local='9',
                   base_price_basis='basket_vw', notes='x')],
         {'_specs_part_1.csv': [part_row('A1', **good_part)]},
         '冲突'),
        ('篮子行乘数≠1',
         [spec_row('A1', multiplier='100')],
         {'_specs_part_1.csv': [part_row('A1', **good_part)]},
         '重复计数'),
        ('basket_constant 与价格对不上',
         [spec_row('A1')],
         {'_specs_part_1.csv': [part_row('A1', **dict(good_part, basket_constant='7.6'))]},
         '对不上'),
        ('币种冲突',
         [spec_row('A1', ccy='EUR')],
         {'_specs_part_1.csv': [part_row('A1', **good_part)]},
         '币种冲突'),
        ('主表没有这一行',
         [spec_row('A1')],
         {'_specs_part_1.csv': [part_row('ZZ', **good_part)]},
         '没有对应行'),
        ('口径没登记',
         [spec_row('A1')],
         {'_specs_part_1.csv': [part_row('A1', **dict(good_part, base_price_basis='',
                                                      notional_source=''))]},
         '没登记口径'),
        ('口径取值非法',
         [spec_row('A1')],
         {'_specs_part_1.csv': [part_row('A1', **dict(good_part,
                                                      base_price_basis='eom_close'))]},
         '非法'),
        ('篮子常数落在 contract 行上',
         [spec_row('A1', level='contract')],
         {'_specs_part_1.csv': [part_row('A1', **good_part)]},
         'pool_product'),
        ('只给篮子常数不给价格',
         [spec_row('A1')],
         {'_specs_part_1.csv': [part_row('A1', base_ccy='USD', basket_constant='7.5',
                                         source_url='https://x/a', computed_note='n',
                                         base_price_basis='basket_vw',
                                         notional_source='definitional')]},
         '不同源'),
    ]
    for name, srows, pfiles, want in cases:
        d = mkdir_with(srows, pfiles)
        try:
            run(d, dry_run=True, today='2026-01-01', quiet=True)
            hit, msg = False, '(没抓住，期望包含 %r)' % want
        except MergeError as e:
            hit = want in str(e)
            msg = str(e)[:96] if hit else '(抓住了别的：%s)' % str(e)[:80]
        print('  %-24s %s  %s' % (name, 'PASS' if hit else 'FAIL', msg))
        ok = ok and hit

    # 正向 1：两个 part 给同一个产品同一个值 —— 允许，且只填一次
    d = mkdir_with([spec_row('A1')],
                   {'_specs_part_1.csv': [part_row('A1', **good_part)],
                    '_specs_part_2.csv': [part_row('A1', **good_part)]})
    try:
        ch, _ = run(d, today='2026-01-01', quiet=True)
        good = any('base_price_local=7.5' in c for c in ch)
        msg = '填了 %d 处' % len(ch)
    except MergeError as e:
        good, msg = False, str(e)[:80]
    print('  %-24s %s  %s' % ('两 part 值相同', 'PASS' if good else 'FAIL', msg))
    ok = ok and good

    # 正向 1b：第一轮说「没测出来」、第二轮把值补上 —— 这是增量，不是冲突
    d1b = mkdir_with([spec_row('A1')],
                     {'_specs_part_r1.csv': [part_row('A1', base_ccy='USD',
                                                      source_url='https://x/a',
                                                      computed_note='📌 未填：卡在权重')],
                      '_specs_part_r2.csv': [part_row('A1', **good_part)]})
    try:
        run(d1b, today='2026-01-01', quiet=True)
        with open(os.path.join(d1b, SPECS_CSV), encoding='utf-8') as f:
            got = list(csv.DictReader(f))[0]
        good = (got['base_price_local'] == '7.5' and got[NEW_COL] == 'definitional'
                and '卡在权重' in got['evidence'] and '合成' in got['evidence'])
        msg = '取到第二轮的值，两轮的证据都留着' if good else repr(got)[:96]
    except MergeError as e:
        good, msg = False, str(e)[:90]
    print('  %-24s %s  %s' % ('空 + 有值 = 增量', 'PASS' if good else 'FAIL', msg))
    ok = ok and good

    # 正向 2：幂等 —— 同一批 part 再跑一遍，字节不变、改动 0 处
    before = open(os.path.join(d, SPECS_CSV), encoding='utf-8').read()
    ch2, _ = run(d, today='2026-01-02', quiet=True)
    after = open(os.path.join(d, SPECS_CSV), encoding='utf-8').read()
    good = (before == after) and not ch2
    print('  %-24s %s  %s' % ('再跑一遍幂等', 'PASS' if good else 'FAIL',
                              '字节一致、改动 0 处' if good
                              else '第二遍改了 %d 处' % len(ch2)))
    ok = ok and good

    # 正向 3：这一轮没测出来的行 —— 不填值，但 evidence 要拿到排除记录
    d3 = mkdir_with([spec_row('B1')],
                    {'_specs_part_1.csv': [part_row('B1', base_ccy='USD',
                                                    source_url='https://x/b',
                                                    computed_note='📌 未填：卡在权重')]})
    run(d3, today='2026-01-01', quiet=True)
    with open(os.path.join(d3, SPECS_CSV), encoding='utf-8') as f:
        got = list(csv.DictReader(f))[0]
    good = (got['base_price_local'] == '' and '卡在权重' in got['evidence']
            and RECHECK_MARK in got['notes'] and got[NEW_COL] == '')
    print('  %-24s %s  %s' % ('未测出的行只并证据', 'PASS' if good else 'FAIL',
                              'evidence 拿到排除记录、值仍为空' if good else repr(got)[:96]))
    ok = ok and good

    # 正向 4：既有行的 notional_source 回填
    d4 = mkdir_with([spec_row('C1', kind='notional', base_price_basis='definitional',
                              base_price_local='1', base_notional_per_unit_local='1'),
                     spec_row('C2', level='contract', multiplier='100',
                              base_price_basis='avg_close', base_price_local='10',
                              base_notional_per_unit_local='1000'),
                     spec_row('C3')], {})
    run(d4, today='2026-01-01', quiet=True)
    with open(os.path.join(d4, SPECS_CSV), encoding='utf-8') as f:
        got = {r['product_id']: r[NEW_COL] for r in csv.DictReader(f)}
    want = {'C1': 'official_notional', 'C2': 'reconstructed', 'C3': ''}
    good = got == want
    print('  %-24s %s  %s' % ('既有行回填新列', 'PASS' if good else 'FAIL',
                              str(got) if not good else str(want)))
    ok = ok and good
    return ok


# ── 入口 ──────────────────────────────────────────────────────────────────
def main(argv):
    ap = argparse.ArgumentParser(description='把 series/_specs_part_*.csv 合并进 '
                                             'series/contract_specs.csv（可重复执行）')
    ap.add_argument('--dry-run', action='store_true', help='只打印会改什么，不落盘')
    ap.add_argument('--no-check', action='store_true', help='落盘后不跑 check_specs')
    ap.add_argument('--selftest', action='store_true', help='验证合并逻辑本身')
    ap.add_argument('--series', default=SERIES, help='series 目录（默认仓内 series/）')
    ap.add_argument('parts', nargs='*',
                    help='只合并这几份 part 文件（默认全部 %s）。'
                         '别的 agent 正在写新 part 时用它把范围框住' % PART_GLOB)
    a = ap.parse_args(argv)

    if a.selftest:
        print('== merge_specs 自检（合成表，不碰 series/）==')
        ok = selftest()
        print('自检%s' % ('通过' if ok else '未通过'))
        return 0 if ok else 1

    try:
        run(a.series, dry_run=a.dry_run, only=a.parts or None)
    except MergeError as e:
        print('\nFAIL 合并被拦下：%s' % e)
        return 2

    if a.dry_run or a.no_check:
        return 0
    print('\n== 合并后体检 build/check_specs.py ==')
    return check_specs.main([])


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
