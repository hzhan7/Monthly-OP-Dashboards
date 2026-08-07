# -*- coding: utf-8 -*-
"""build/pools.py + build/notional.py 的单元测试。

跑法: python3 build/test_pools.py        （只用标准库，不需要 pytest / pandas）

这套测试守的是三件「写错了在图上看不出来」的事：

 (a) **每池成员的换算链都能机械执行。** 不是检查字段拼写，而是真的喂一张合成的
     规格表 + 汇率表，把 17 个池的每一条腿从源列一路跑到美元名义额。
     链上任何一跳声明得不对（product 不在清单里、src 与 kind 打架、
     per_day 写成了字符串），这里就炸。
 (b) **一个手算的定基名义额与函数结果一致。** 夹具里的数字是**构造的**，
     不是任何真实合约的规格 —— 它测的是公式，不是世界。
     真实的乘数与基期价格必须实测后写进 series/contract_specs.csv。
 (c) **share='true' 的池，分母列真的存在。** 分母是"真份额"这个词的全部含义；
     分母列名写错了，图上只会显示一个偏掉的百分比，不会报错。
     CSV 还没建的成员不算错（分批上线的正常状态），但已建的 CSV 里缺列一定是错。

另外还有一组「错误必须响」的测试：product 不在表里、基期价格为空、汇率缺月，
三种情况都必须抛出各自的异常，绝不返回 NaN 或 0。

━━ 为什么多了一组「打真表」的测试（TestRealFxTable）━━
上一轮这套测试 33 条全绿，但 notional.load_fx 其实**根本读不了仓里那张 fx.csv**：
夹具按长表（month, ccy, usd_per_unit）写，而 fetch/fx.py 落库的是宽表
（month, obs_days, eom_date, fx_avg_<ccy>usd…）。夹具和被测代码用的是同一套
错误假设，于是测试只证明了「代码与夹具自洽」，没证明「代码与仓库自洽」。
这一类 bug 只有拿**真文件**去撞才撞得出来，所以现在夹具改成宽表之外，
另有一组测试直接加载 series/fx.csv 本身 —— 它不校验数值（那是 fetch/fx.py 的事），
只校验「这张表能被读进来，且定基那一跳要用的币种在基期都取得到」。
"""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import notional        # noqa: E402
import pools           # noqa: E402


# ═══════════════════════════════════════════════════════════════════════════
# 合成夹具 —— 这里的每一个数字都是**编的**，只为让算术可手算
# ═══════════════════════════════════════════════════════════════════════════
# 之所以敢编：本文件测的是「公式对不对」，不是「世界是什么样」。
# 真实的乘数与基期价格是关于外部世界的事实断言，必须实测后写进
# series/contract_specs.csv —— 那张表里一个编的数字都不许有。
# 为了让人一眼看出这是夹具，币种用 ISO 4217 里不存在的 XTS / XTT（保留给测试用）。

FIX_CCY = 'XTS'
FIX_CCY2 = 'XTT'

# 手算用的一条：乘数 50、基期价 2600 ⇒ 单张基期名义额 130,000 XTS；
# 基期汇率 0.5 USD/XTS ⇒ 单张 65,000 USD。
FIX_MULT = 50.0
FIX_BASE_PRICE = 2600.0
FIX_BASE_FX = 0.5            # 基期月均（avg）—— 流量口径
FIX_BASE_FX_EOM = 0.6        # 基期月末（eom）—— 存量口径
FIX_CUR_PRICE = 6000.0
FIX_CUR_FX = 0.4
FIX_CUR_FX_EOM = 0.45
# avg 与 eom 刻意取不同的数：两档若填成同一个值，「拿错档次」这类 bug
# 在测试里就永远表现为通过 —— 那正是 fetch/fx.py 说的「用错了不会报错」。


def _write(path, header, rows):
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(','.join(header) + '\n')
        for r in rows:
            f.write(','.join('' if v is None else str(v) for v in r) + '\n')


def make_fixture_dir():
    """写一套合成的 contract_specs / fx / prices，返回目录路径。

    规格表覆盖 pools.PRODUCTS 的**全部**产品（分批上线时真表只填一部分，
    但测试要一次跑通所有池，所以这里全填），外加两个专门给手算与报错用的产品。
    """
    d = tempfile.mkdtemp(prefix='pools_fixture_')

    rows = []
    ccys = {FIX_CCY, FIX_CCY2}
    for pid, meta in sorted(pools.PRODUCTS.items()):
        kind = meta['kind']
        # 篮子产品的 ccy 在真表里要定死一个记账币；夹具里统一用 XTS
        ccy = FIX_CCY
        ccys.add(ccy)
        if kind == 'notional':
            mult, price = 1.0, 1.0
        elif kind == 'share':
            mult, price = 1.0, 40.0          # 编的"基期平均成交价"
        else:
            mult, price = FIX_MULT, FIX_BASE_PRICE
        rows.append([pid, meta['zh'].replace(',', '，'), meta['exchange'], kind, ccy,
                     mult, 'fixture', notional.BASE_MONTH, price, mult * price,
                     'PX_' + pid, 'fixture', 'fixture', 'fixture'])

    # 手算专用（与上面同规格，但独立一行，改上面的池定义不会影响手算断言）
    rows.append(['FIX_HANDCALC', '手算夹具', 'FIXTURE', 'contract', FIX_CCY,
                 FIX_MULT, 'fixture', notional.BASE_MONTH, FIX_BASE_PRICE,
                 FIX_MULT * FIX_BASE_PRICE, 'PX_FIX_HANDCALC',
                 'fixture', 'fixture', 'fixture'])
    # 基期价格留空 —— 用来验证 MissingBasePrice
    rows.append(['FIX_NOPRICE', '基期价未测', 'FIXTURE', 'contract', FIX_CCY,
                 FIX_MULT, 'fixture', notional.BASE_MONTH, None, None,
                 'PX_FIX_NOPRICE', 'fixture', 'fixture', 'fixture'])
    # 另一个币种 —— 用来验证 MissingFxMonth（fx 表里只给它基期，不给当期）
    rows.append(['FIX_OTHERCCY', '另一币种', 'FIXTURE', 'contract', FIX_CCY2,
                 FIX_MULT, 'fixture', notional.BASE_MONTH, FIX_BASE_PRICE,
                 FIX_MULT * FIX_BASE_PRICE, 'PX_FIX_HANDCALC',
                 'fixture', 'fixture', 'fixture'])

    _write(os.path.join(d, notional.SPECS_CSV),
           ('product_id,zh,exchange,kind,ccy,multiplier,mult_unit,base_month,'
            'base_price_local,base_notional_per_unit_local,price_id,source,'
            'evidence,notes').split(','), rows)

    # 汇率表按 fetch/fx.py 真正落库的**宽表**写：一行一个月，每个币种 avg/eom 两列。
    # 夹具的形状必须与真表一致，否则测试只证明「代码与夹具自洽」——
    # 上一轮就是这么让一个「读不了真表」的 load_fx 拿到 33 条全绿的。
    fx_ccys = sorted(ccys)
    fx_header = (['month', 'obs_days', 'eom_date']
                 + ['fx_avg_%susd' % c.lower() for c in fx_ccys]
                 + ['fx_eom_%susd' % c.lower() for c in fx_ccys])
    # 基期：两档都给，且刻意取不同的数
    fx_rows = [[notional.BASE_MONTH, 22, notional.BASE_MONTH + '-31']
               + [FIX_BASE_FX] * len(fx_ccys)
               + [FIX_BASE_FX_EOM] * len(fx_ccys)]
    # 当期：只给 XTS，XTT 留空 —— 留空的格不入表，用到时才抛 MissingFxMonth，
    # 这正是 test_missing_fx_month 要验的那条路径
    fx_rows.append(['2026-07', 22, '2026-07-31']
                   + [FIX_CUR_FX if c == FIX_CCY else None for c in fx_ccys]
                   + [FIX_CUR_FX_EOM if c == FIX_CCY else None for c in fx_ccys])
    _write(os.path.join(d, notional.FX_CSV), fx_header, fx_rows)

    # 当期价格给两个月：FakeSeries 吐的就是这两个月，缺一个月当期口径就会炸
    # （那正是 MissingPrice 该做的事，但在"全链跑通"这组测试里它是噪声）
    px_rows = [['2026-07', 'PX_FIX_HANDCALC', FIX_CUR_PRICE, 'fixture'],
               [notional.BASE_MONTH, 'PX_FIX_HANDCALC', FIX_BASE_PRICE, 'fixture']]
    for pid, meta in sorted(pools.PRODUCTS.items()):
        if meta['kind'] != 'notional':
            px_rows.append(['2026-07', 'PX_' + pid, FIX_CUR_PRICE, 'fixture'])
            px_rows.append([notional.BASE_MONTH, 'PX_' + pid,
                            FIX_BASE_PRICE, 'fixture'])
    _write(os.path.join(d, notional.PRICES_CSV),
           ['month', 'price_id', 'price_local', 'source'], px_rows)
    return d


def per_day_cols():
    """POOLS 里所有被当成"交易日"用的 (csv, col)。测试的假取数器要认得它们。

    含 div_col：隐含交易日是「月度总量 ÷ 官方日均」，两列都是日数那一跳的输入。
    """
    out = set()
    for p in pools.POOLS:
        objs = ([p['denom']] if p.get('denom') else []) + list(p['members'])
        for obj in objs:
            for leg in (obj.get('chain') or []):
                pdx = leg.get('per_day')
                if pdx:
                    days_csv = pdx.get('csv') or leg.get('csv') or obj['csv']
                    out.add((days_csv, pdx['col']))
                    if pdx.get('div_col'):
                        out.add((days_csv, pdx['div_col']))
    return out


def minus_cols():
    """POOLS 里所有被**减掉**的列 (csv, col) —— athex_* 那一类备注列。"""
    out = set()
    for p in pools.POOLS:
        objs = ([p['denom']] if p.get('denom') else []) + list(p['members'])
        for obj in objs:
            for leg in (obj.get('chain') or []):
                if leg.get('sign', 1) < 0:
                    out.add(((leg.get('csv') or obj['csv']), leg['col']))
    return out


class FakeSeries(object):
    """假取数器：交易日列给 20，**被减的备注列**给 100，其余列给 1000。

    值本身不重要 —— 这一组测试问的是「链能不能跑通」，不是「数对不对」。
    但备注列必须给一个**比主列小**的数，否则「主列 − 备注列」会算出 0 或负数，
    而那既不是被测代码的错，也不是它该被夸的对：夹具本身要满足
    「备注列是主列的一个子集」这条现实约束，测试才问得出真问题。
    """

    def __init__(self):
        self.days = per_day_cols()
        self.minus = minus_cols()
        self.asked = []

    def __call__(self, csv_name, col):
        self.asked.append((csv_name, col))
        if (csv_name, col) in self.days:
            v = 20.0
        elif (csv_name, col) in self.minus:
            v = 100.0
        else:
            v = 1000.0
        return {'2019-01': v, '2026-07': v * 2}


# ═══════════════════════════════════════════════════════════════════════════
class TestPoolStructure(unittest.TestCase):
    """池定义本身的自洽性 —— validate() 的每一条都在这里被当成断言。"""

    def test_validate_clean(self):
        errs = pools.validate()
        self.assertEqual(errs, [], '\n'.join(['pools.validate() 有错：'] + errs))

    def test_every_pool_has_head_inside_members(self):
        for p in pools.POOLS:
            keys = {m['key'] for m in p['members']}
            self.assertTrue(p['head'], '池 %s 没有 head' % p['id'])
            for h in p['head']:
                self.assertIn(h, keys, '池 %s 的 head 成员 %r 不在 members 里' % (p['id'], h))

    def test_member_cap_and_palette(self):
        for p in pools.POOLS:
            self.assertLessEqual(len(p['members']), pools.MAX_MEMBERS,
                                 '池 %s 超过每池 ≤5 家' % p['id'])
            colors = [m['color'] for m in p['members']]
            self.assertEqual(len(colors), len(set(colors)),
                             '池 %s 同池内颜色撞车：%s' % (p['id'], colors))
            for c in colors:
                self.assertIn(c, pools.PALETTE, '池 %s 用了非数据色 %s' % (p['id'], c))

    def test_contracts_col_declared_everywhere(self):
        """张数原列必须显式声明（没有就写 []）—— 它是与官方新闻稿对账的唯一入口。"""
        for p in pools.POOLS:
            for m in p['members']:
                self.assertIn('contracts_col', m,
                              '池 %s 成员 %s 没写 contracts_col' % (p['id'], m['key']))
                self.assertIsInstance(m['contracts_col'], list)
                self.assertTrue(pools.recon_cols(m),
                                '池 %s 成员 %s 一个对账列都没有' % (p['id'], m['key']))

    def test_dual_unit_only_on_true_share_pools(self):
        """张数口径份额图只给有官方分母的池 —— 没有分母就没有可对账的外部数字。"""
        duals = [p['id'] for p in pools.POOLS if p.get('dual_unit')]
        self.assertEqual(sorted(duals), ['na_cash', 'na_multilist_opt'],
                         '北美两个真份额池之外不该有 dual_unit')
        for pid in duals:
            p = pools.pool(pid)
            self.assertEqual(p['share'], 'true')
            self.assertTrue(p.get('dual_note'))
            for m in p['members']:
                self.assertTrue(m['contracts_col'],
                                '池 %s 成员 %s 要出张数份额图却没有张数列'
                                % (pid, m['key']))

    def test_no_mixed_price_basis_inside_a_pool(self):
        """金额型与数量型源列不许同池 —— 一个是当期价、一个是定基价，占比会是假的。"""
        for p in pools.POOLS:
            if p['unit_kind'] != 'notional':
                continue
            srcs = {leg['src'] for _l, _c, ch in pools.chains_of(p) for leg in ch}
            self.assertFalse('notional' in srcs and srcs - {'notional'},
                             '池 %s 混了价格基准：%s' % (p['id'], sorted(srcs)))
            want = 'fx_only' if srcs == {'notional'} else 'base_price'
            self.assertEqual(p['deflator'], want,
                             '池 %s 的 deflator 与源列类型对不上' % p['id'])

    def test_products_manifest_is_exactly_what_pools_use(self):
        self.assertEqual(sorted(pools.PRODUCTS), pools.products_used(),
                         'PRODUCTS 清单与池实际引用的产品不是同一套')

    # ── 张数口径成员（contracts_only）——见 pools.py 模块 docstring 六 ────────
    def test_contracts_only_members_are_fully_declared(self):
        """「永久张数口径」这件事必须三处齐全，缺一处它就又变回隐式状态。"""
        found = 0
        for p in pools.POOLS:
            co = pools.contracts_only_members(p)
            if not co:
                continue
            found += len(co)
            self.assertTrue(p.get('contracts_only_note'),
                            '池 %s 有张数口径成员却没有给读者看的 contracts_only_note'
                            % p['id'])
            for m in co:
                self.assertTrue(m.get('contracts_only_why'),
                                '池 %s 成员 %s 没写 contracts_only_why' % (p['id'], m['key']))
                self.assertFalse(m.get('in_share'),
                                 '池 %s 成员 %s 是张数口径却进了份额分子'
                                 % (p['id'], m['key']))
                self.assertTrue(m.get('contracts_col'),
                                '池 %s 成员 %s 是张数口径却没有张数原列'
                                % (p['id'], m['key']))
        self.assertEqual(found, 2,
                         '目前唯一的一组张数口径成员是 rates.ice 与 eu_deriv.ice；'
                         '数量变了说明有人新增或删除了这个状态，'
                         '请连同 pools.py 模块 docstring 六一起更新')

    def test_frozen_products_are_not_counted_as_pending(self):
        """products_needing_specs() 必须把永久张数口径的产品剔出去。

        这条测试拦的是一个具体的回归：若 build 脚本改回用 products_used()，
        ICE_STIR / ICE_MLTIR 的空常数会被当成"待实测"，
        rates 与 eu_deriv 两个池会被 notional.pending_products 判定为未就绪、整池 skip ——
        用一个口径判断毁掉两页本来完全成立的增长图。
        """
        frozen = pools.contracts_only_products()
        self.assertEqual(frozen, ['ICE_MLTIR', 'ICE_STIR'])
        need = pools.products_needing_specs()
        for pid in frozen:
            self.assertNotIn(pid, need)
        self.assertEqual(sorted(set(need) | set(frozen)), pools.products_used(),
                         'products_needing_specs 与永久张数口径两份清单合起来'
                         '必须正好等于 products_used()，不许有产品两边都不在')

    def test_frozen_products_are_only_used_by_contracts_only_members(self):
        """「只被张数口径成员引用」是硬要求 —— 否则别的成员会借这条通道跳过常数。"""
        frozen = set(pools.contracts_only_products())
        for p in pools.POOLS:
            co = {id(m) for m in pools.contracts_only_members(p)}
            for m in p['members']:
                if id(m) in co:
                    continue
                used = {leg['product'] for leg in (m.get('chain') or [])}
                self.assertFalse(used & frozen,
                                 '池 %s 的非张数口径成员 %s 引用了 %s —— '
                                 '那这个产品就必须补齐基期常数'
                                 % (p['id'], m['key'], sorted(used & frozen)))

    def test_ice_energy_leg_is_the_scope_consistent_subset(self):
        """energy 池的 ICE 腿必须是 Brent 单列，且页面上必须写明只含 Brent。

        这条测试拦的是「有人为了提高覆盖率把 adv_energy_kcontracts 换回来」——
        那一列是 ICE 全球口径（IFEU + Endex + IFUS + IFAD + NGX），
        而能拿到的分产品结构只覆盖 IFEU（2019-01 占全球 67.0%），
        拿 67% 的结构套 100% 的量是方向与大小都不可知的系统性偏差。
        见 pools.py 模块 docstring 七。
        """
        p = pools.pool('energy')
        ice = [m for m in p['members'] if m['key'] == 'ice'][0]
        cols = [leg['col'] for leg in ice['chain']]
        self.assertEqual(cols, ['adv_brent_kcontracts'])
        self.assertEqual([leg['product'] for leg in ice['chain']], ['ICE_BRENT_IFEU'])
        # 全能源列只许待在 crosscheck_col（做覆盖率对账），绝不许进 chain
        self.assertIn('adv_energy_kcontracts', ice.get('crosscheck_col') or [])
        self.assertNotIn('adv_energy_kcontracts', cols)
        self.assertNotIn('adv_energy_kcontracts', ice['contracts_col'])
        self.assertTrue(p.get('scope_note'), 'energy 池必须写 scope_note')
        for word in ('Brent', '34.8', '不是 ICE 的全部能源'):
            self.assertIn(word, p['scope_note'],
                          'scope_note 里必须点明 %r —— 少了它读者会把三分之一读成全部' % word)
        self.assertIn('Brent', p['share_caveat'])

    def test_manifest_carries_no_numbers(self):
        """需求清单里不许出现数字 —— 乘数与基期价格必须实测后写进规格表。"""
        for pid, meta in pools.PRODUCTS.items():
            for k in ('multiplier', 'base_price', 'base_notional'):
                self.assertNotIn(k, meta, 'PRODUCTS[%s] 不该带 %s' % (pid, k))
            self.assertTrue(meta['spec_source'],
                            'PRODUCTS[%s] 没写去哪儿取规格' % pid)


class TestChainsResolve(unittest.TestCase):
    """(a) 每池成员的换算链都能从源列一路跑到美元名义额。"""

    @classmethod
    def setUpClass(cls):
        cls.dir = make_fixture_dir()
        cls.specs = notional.load_specs(cls.dir)
        cls.fx = notional.load_fx(cls.dir)
        cls.prices = notional.load_prices(cls.dir)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def test_every_chain_runs_end_to_end(self):
        get = FakeSeries()
        n_legs = 0
        for p in pools.POOLS:
            for label, csv_name, chain in pools.chains_of(p):
                out = notional.resolve_chain(get, chain, csv_name,
                                             self.specs, self.fx, mode='base')
                n_legs += len(chain)
                self.assertTrue(out, '%s 换算结果是空的' % label)
                for mon, v in out.items():
                    self.assertIsNotNone(v, '%s 在 %s 算出 None' % (label, mon))
                    self.assertGreater(v, 0, '%s 在 %s 算出非正数' % (label, mon))
        # 17 个池、61 个成员位；share_pp 池不走链，所以腿数少于成员位数不是错
        self.assertGreater(n_legs, 60, '跑到的腿太少，说明大半个模型没被测到')

    def test_every_chain_runs_with_its_pool_fx_basis(self):
        """按 build 脚本该有的写法跑一遍：basis 取自 pools.fx_basis(p)，不手写字面量。

        test_every_chain_runs_end_to_end 用的是默认 'avg'，跑不到存量池那条路径；
        fn_index_aum 是仓内唯一的 'eom' 池，只有这条测试会碰到它。
        """
        get = FakeSeries()
        seen = set()
        for p in pools.POOLS:
            basis = pools.fx_basis(p)
            for label, csv_name, chain in pools.chains_of(p):
                out = notional.resolve_chain(get, chain, csv_name, self.specs,
                                             self.fx, mode='base', basis=basis)
                seen.add(basis)
                for mon, v in out.items():
                    self.assertIsNotNone(v, '%s（basis=%s）在 %s 算出 None'
                                         % (label, basis, mon))
                    self.assertGreater(v, 0, '%s 在 %s 算出非正数' % (label, mon))
        self.assertEqual(seen, set(notional.FX_BASES),
                         '两档汇率没有都被跑到：%s' % sorted(seen))

    def test_every_chain_runs_in_current_mode(self):
        get = FakeSeries()
        for p in pools.POOLS:
            for label, csv_name, chain in pools.chains_of(p):
                out = notional.resolve_chain(get, chain, csv_name, self.specs,
                                             self.fx, mode='current',
                                             prices=self.prices)
                self.assertTrue(all(v is not None for v in out.values()),
                                '%s 的当期名义额有 None' % label)

    def test_chain_asks_for_exactly_the_declared_columns(self):
        """链上取的列必须落在 cols_used() 声明的范围内 —— 否则门槛检查会漏掉一列。"""
        for p in pools.POOLS:
            get = FakeSeries()
            for _label, csv_name, chain in pools.chains_of(p):
                notional.resolve_chain(get, chain, csv_name, self.specs, self.fx)
            declared = pools.cols_used(p)
            for csv_name, col in get.asked:
                self.assertIn(csv_name, declared,
                              '池 %s 读了未声明的 %s' % (p['id'], csv_name))
                self.assertIn(col, declared[csv_name],
                              '池 %s 读了未声明的 %s.%s' % (p['id'], csv_name, col))

    def test_multi_leg_sums_after_conversion_not_before(self):
        """多腿必须先各自换算再相加。

        构造：两条腿走两个基期名义额不同的产品。若实现是"先加张数再乘一个乘数"，
        结果会等于 (a+b)×k₁ 或 (a+b)×k₂，与正确答案 a×k₁+b×k₂ 不同。
        """
        chain = [
            {'col': 'a', 'src': 'contracts', 'unit_scale': 1.0, 'per_day': None,
             'product': 'FIX_HANDCALC'},
            {'col': 'b', 'src': 'contracts', 'unit_scale': 1.0, 'per_day': None,
             'product': 'CME_RATES'},   # 夹具里同规格，但走的是另一行
        ]

        def get(_csv, col):
            return {'2026-07': 3.0 if col == 'a' else 7.0}

        k1 = notional.base_notional_per_unit_usd('FIX_HANDCALC', self.specs, self.fx)
        k2 = notional.base_notional_per_unit_usd('CME_RATES', self.specs, self.fx)
        out = notional.resolve_chain(get, chain, 'x.csv', self.specs, self.fx)
        self.assertAlmostEqual(out['2026-07'], 3.0 * k1 + 7.0 * k2, places=6)

    def test_missing_leg_makes_the_sum_none_not_zero(self):
        chain = [
            {'col': 'a', 'src': 'contracts', 'unit_scale': 1.0, 'per_day': None,
             'product': 'FIX_HANDCALC'},
            {'col': 'b', 'src': 'contracts', 'unit_scale': 1.0, 'per_day': None,
             'product': 'FIX_HANDCALC'},
        ]

        def get(_csv, col):
            return {'2026-07': 3.0 if col == 'a' else None}

        out = notional.resolve_chain(get, chain, 'x.csv', self.specs, self.fx)
        self.assertIsNone(out['2026-07'],
                          '缺一条腿时合计必须是 None，不能把缺的那条当 0')


class TestHandCalc(unittest.TestCase):
    """(b) 手算的定基名义额与函数结果一致。"""

    @classmethod
    def setUpClass(cls):
        cls.dir = make_fixture_dir()
        cls.specs = notional.load_specs(cls.dir)
        cls.fx = notional.load_fx(cls.dir)
        cls.prices = notional.load_prices(cls.dir)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def test_base_notional_hand_computed(self):
        # 手算：1,234 张 × 50 × 2,600 XTS/点 × 0.5 USD/XTS
        #      = 1,234 × 130,000 XTS = 160,420,000 XTS
        #      = 80,210,000 USD
        series = {'2026-07': 1234.0}
        out = notional.to_base_notional(series, 'FIX_HANDCALC', self.specs, self.fx)
        self.assertAlmostEqual(out['2026-07'], 80210000.0, places=4)
        # 显示成 USD bn 时
        self.assertAlmostEqual(out['2026-07'] / notional.USD_BN, 0.08021, places=9)

    def test_base_notional_growth_equals_contract_growth(self):
        """定基口径的全部意义：常数不改变增长率。"""
        series = {'2026-06': 1000.0, '2026-07': 1234.0}
        out = notional.to_base_notional(series, 'FIX_HANDCALC', self.specs, self.fx)
        self.assertAlmostEqual(out['2026-07'] / out['2026-06'], 1.234, places=12)

    def test_current_notional_hand_computed(self):
        # 手算：1,234 张 × 50 × 6,000 XTS × 0.4 USD/XTS = 148,080,000 USD
        series = {'2026-07': 1234.0}
        out = notional.to_current_notional(series, 'FIX_HANDCALC', self.specs,
                                           self.fx, self.prices)
        self.assertAlmostEqual(out['2026-07'], 148080000.0, places=4)

    def test_unit_scale_and_per_day(self):
        # 手算：12.5 千张 → 12,500 张 → ÷ 20 个交易日 = 625 张/日
        canon = notional.apply_unit({'2026-07': 12.5}, pools.K,
                                    days={'2026-07': 20.0})
        self.assertAlmostEqual(canon['2026-07'], 625.0, places=9)
        out = notional.to_base_notional(canon, 'FIX_HANDCALC', self.specs, self.fx)
        self.assertAlmostEqual(out['2026-07'], 625.0 * 65000.0, places=4)

    def test_zero_trading_days_is_none_not_inf(self):
        canon = notional.apply_unit({'2026-07': 12.5}, pools.K,
                                    days={'2026-07': 0.0})
        self.assertIsNone(canon['2026-07'])

    def test_holes_stay_holes(self):
        out = notional.to_base_notional({'2026-06': None, '2026-07': 1.0},
                                        'FIX_HANDCALC', self.specs, self.fx)
        self.assertIsNone(out['2026-06'])
        self.assertIsNotNone(out['2026-07'])

    def test_base_notional_with_eom_basis_hand_computed(self):
        """存量口径走月末汇率，且必须与月均口径**算出不同的数**。

        手算：1,234 张 × 50 × 2,600 XTS × 0.6 USD/XTS（月末）= 96,252,000 USD，
        比月均口径的 80,210,000 高出 0.6/0.5 = 1.2 倍。
        两档若被实现成同一个数，这条断言会当场失败 —— 这正是它存在的理由。
        """
        series = {'2026-07': 1234.0}
        avg = notional.to_base_notional(series, 'FIX_HANDCALC', self.specs,
                                        self.fx, basis='avg')
        eom = notional.to_base_notional(series, 'FIX_HANDCALC', self.specs,
                                        self.fx, basis='eom')
        self.assertAlmostEqual(avg['2026-07'], 80210000.0, places=4)
        self.assertAlmostEqual(eom['2026-07'], 96252000.0, places=4)
        self.assertAlmostEqual(eom['2026-07'] / avg['2026-07'],
                               FIX_BASE_FX_EOM / FIX_BASE_FX, places=12)

    def test_growth_is_basis_independent(self):
        """两档汇率都是常数 ⇒ 换哪一档都不改变增长率。定基口径的核心性质。"""
        series = {'2026-06': 1000.0, '2026-07': 1234.0}
        for basis in notional.FX_BASES:
            out = notional.to_base_notional(series, 'FIX_HANDCALC', self.specs,
                                            self.fx, basis=basis)
            self.assertAlmostEqual(out['2026-07'] / out['2026-06'], 1.234,
                                   places=12, msg='basis=%s 改变了增长率' % basis)


class TestFxBasis(unittest.TestCase):
    """avg 配流量、eom 配存量 —— fetch/fx.py 唯一一个「用错了不会报错」的坑。"""

    def test_flow_maps_to_basis_for_every_pool(self):
        for p in pools.POOLS:
            self.assertIn(pools.fx_basis(p), notional.FX_BASES,
                          '池 %s 推不出汇率基准' % p['id'])

    def test_only_stock_pools_use_eom(self):
        """存量池取月末、流量池取月均。仓内唯一的存量池是 fn_index_aum（AUM）。"""
        eom = sorted(p['id'] for p in pools.POOLS if pools.fx_basis(p) == 'eom')
        self.assertEqual(eom, ['fn_index_aum'],
                         '存量池清单变了 —— 新增存量池要同步确认它该用月末汇率')
        for p in pools.POOLS:
            want = 'eom' if p['flow'] == 'stock' else 'avg'
            self.assertEqual(pools.fx_basis(p), want,
                             '池 %s flow=%s 却推出 %s'
                             % (p['id'], p['flow'], pools.fx_basis(p)))

    def test_pools_does_not_keep_its_own_copy_of_the_mapping(self):
        """映射表只许有一份 —— pools.FLOWS 必须就是 notional 那张表的键。"""
        self.assertEqual(tuple(pools.FLOWS),
                         tuple(notional.FLOW_TO_FX_BASIS))


class TestRealFxTable(unittest.TestCase):
    """拿**仓里那张真 fx.csv** 去撞 load_fx。

    上一轮 33 条测试全绿而 load_fx 读不了真表，就是因为没有这一组：
    夹具与被测代码共用了同一个错误假设（长表），互相印证得天衣无缝。
    这里不校验汇率数值本身（那是 fetch/fx.py 的 _validate 的职责），
    只校验「这张表读得进来，且定基那一跳要用的币种在基期取得到」。
    """

    @classmethod
    def setUpClass(cls):
        cls.path = os.path.join(pools.SERIES, notional.FX_CSV)
        cls.fx = notional.load_fx(pools.SERIES) if os.path.exists(cls.path) else None

    def test_repo_fx_csv_loads(self):
        self.assertTrue(os.path.exists(self.path),
                        'series/fx.csv 不在 —— 它是横截面页的公共底座，'
                        '由 fetch/fx.py 建')
        self.assertTrue(self.fx, 'series/fx.csv 读出来是空的')

    def test_base_month_is_covered_in_both_bases(self):
        """基期那一行必须两档俱全 —— 每一个定基常数都要乘它。"""
        ccys = sorted({c for (_m, c, _b) in self.fx})
        for c in ccys:
            for basis in notional.FX_BASES:
                self.assertIn((notional.BASE_MONTH, c, basis), self.fx,
                              'series/fx.csv 缺 %s 的 %s（基准 %s）'
                              % (notional.BASE_MONTH, c, basis))

    def test_every_currency_pools_need_is_in_the_real_table(self):
        """PRODUCTS 里声明的每个币种都要能在基期取到汇率。

        ccy=None 的是跨币种合成篮子，记账币要在 contract_specs.csv 里定死，
        这里查不了 —— 那一条由 check_specs / build 侧在规格表填好后再守。
        """
        want = sorted({m['ccy'] for m in pools.PRODUCTS.values() if m['ccy']})
        self.assertTrue(want)
        missing = []
        for ccy in want:
            for basis in notional.FX_BASES:
                try:
                    notional.fx_rate(self.fx, ccy, notional.BASE_MONTH, basis)
                except notional.MissingFxMonth:
                    missing.append('%s/%s' % (ccy, basis))
        self.assertEqual(missing, [],
                         'POOLS 要用但基期取不到汇率：%s' % missing)
        baskets = sorted(pid for pid, m in pools.PRODUCTS.items() if not m['ccy'])
        print('\n  真 fx.csv：%d 个 (月,币,档) ；池要的币种 %s 基期全在；'
              '跨币种篮子 %d 个待规格表定记账币（%s）'
              % (len(self.fx), ','.join(want), len(baskets), ', '.join(baskets)))

    def test_real_avg_and_eom_actually_differ(self):
        """真表里两档必须是两个不同的数 —— 否则 fetch/fx.py 那边就已经错了。"""
        diff = sum(1 for (m, c, _b) in self.fx
                   if _b == 'avg'
                   and self.fx.get((m, c, 'eom')) not in (None, self.fx[(m, c, 'avg')]))
        total = sum(1 for (_m, _c, b) in self.fx if b == 'avg')
        self.assertGreater(diff, total * 0.9,
                           '真表里 avg 与 eom 几乎处处相等（%d/%d）—— '
                           '两档大概率被写成了同一条序列' % (diff, total))

    def test_usd_is_implicit_one(self):
        """USD 是记账币，表里没有它的列，fx_rate 必须隐含返回 1.0。"""
        for basis in notional.FX_BASES:
            self.assertEqual(
                notional.fx_rate(self.fx, 'USD', notional.BASE_MONTH, basis), 1.0)


class TestDenominators(unittest.TestCase):
    """(c) share='true' 的池，分母列真的存在。"""

    def test_true_share_pools_declare_a_denominator(self):
        true_pools = [p for p in pools.POOLS if p['share'] == 'true']
        self.assertTrue(true_pools)
        for p in true_pools:
            if p['unit_kind'] == 'share_pp':
                # 份额序列自带分母，不需要再声明一个
                for m in p['members']:
                    self.assertTrue(m.get('share_col'),
                                    '池 %s 成员 %s 缺 share_col' % (p['id'], m['key']))
                continue
            d = p.get('denom')
            self.assertIsNotNone(d, '池 %s 声明 share=true 却没有 denom' % p['id'])
            self.assertTrue(d.get('chain'), '池 %s 的 denom 没有换算链' % p['id'])
            self.assertTrue(d.get('evidence'),
                            '池 %s 的 denom 没有 evidence —— 分母是关于外部世界的断言，'
                            '必须留下核对痕迹' % p['id'])

    def test_denominator_columns_exist_in_built_csvs(self):
        """分母列必须在真实的 series/*.csv 表头里。

        CSV 还没建 = 分批上线的正常状态，记成 pending 不算错；
        已建的 CSV 里缺列 = 一定是错。
        """
        import csv as _csv
        checked, pending = [], []
        for p in pools.POOLS:
            d = p.get('denom')
            if not d:
                continue
            path = os.path.join(pools.SERIES, d['csv'])
            if not os.path.exists(path):
                pending.append('%s → series/%s' % (p['id'], d['csv']))
                continue
            with open(path, newline='', encoding='utf-8') as f:
                header = set(next(_csv.reader(f)))
            for leg in d['chain']:
                self.assertIn(leg['col'], header,
                              'series/%s 里没有分母列 %r' % (d['csv'], leg['col']))
                checked.append('%s.%s' % (d['csv'], leg['col']))
        print('\n  分母列：已核对 %d 列；%d 个池的分母 CSV 还没建（%s）'
              % (len(checked), len(pending), '；'.join(pending) or '无'))

    def test_selfreported_share_reconciles_on_real_data(self):
        """自算份额 vs 官方自报份额，**用真 CSV 逐月核**。

        这是全仓唯一一处能拿外部数字验证自己的地方，所以它不是"抽查一个月"，
        而是把两条序列的每一个可比月都比一遍：换算链、分母口径、单位倍数，
        任何一处坏掉都会让偏差从零点零几 pp 跳到几个 pp 甚至几十倍。

        对账走**张数/股数**口径（官方自报的份额本来就是这么算的）。名义额份额与它
        恒等 —— 分子分母同乘一个基期常数 —— 所以核了这一条就等于核了主口径。
        CSV 还没建的成员记成 pending，不算失败（分批上线的正常状态）。
        """
        import csv as _csv

        def load(name):
            path = os.path.join(pools.SERIES, name)
            if not os.path.exists(path):
                return None
            with open(path, newline='', encoding='utf-8') as f:
                return {r['month']: r for r in _csv.DictReader(f)}

        def total(row, cols):
            vals = []
            for c in cols:
                v = (row.get(c) or '').strip()
                if not v:
                    return None
                vals.append(float(v))
            return sum(vals)

        done, pending = [], []
        for p in pools.POOLS:
            checks = pools.selfreport_checks(p)
            if not checks:
                continue
            dtab = load(p['denom']['csv'])
            for m, sr in checks:
                mtab = load(m['csv'])
                if dtab is None or mtab is None:
                    pending.append('%s.%s' % (p['id'], m['key']))
                    continue
                devs = []
                for mon, mrow in sorted(mtab.items()):
                    drow = dtab.get(mon)
                    if drow is None:
                        continue
                    num = total(mrow, m['contracts_col'])
                    den = total(drow, p['denom']['contracts_col'])
                    off = (drow.get(sr['col']) or mrow.get(sr['col']) or '').strip()
                    if num is None or not den or not off:
                        continue
                    devs.append((abs(num / den - float(off) * sr['scale']) * 100, mon))
                self.assertTrue(
                    devs, '%s.%s 一个可比月都没有 —— 对账通道是断的'
                          % (p['id'], m['key']))
                worst, worst_mon = max(devs)
                self.assertLessEqual(
                    worst, sr['tol_pp'],
                    '%s.%s 自算份额与官方自报在 %s 差 %.4f pp，超过容差 %.2f pp —— '
                    '换算链或分母口径坏了（evidence 说的是「%s」）'
                    % (p['id'], m['key'], worst_mon, worst, sr['tol_pp'],
                       sr['evidence']))
                devs.sort()
                done.append('%s.%s %d 月 中位%.3f 最大%.3fpp(%s) 容差%.2f'
                            % (p['id'], m['key'], len(devs),
                               devs[len(devs) // 2][0], worst, worst_mon,
                               sr['tol_pp']))
        print('\n  自报份额对账：')
        for line in done:
            print('    ✓ ' + line)
        if pending:
            print('    待建 CSV：' + ', '.join(pending))

    def test_all_declared_columns_exist_in_built_csvs(self):
        """已建 CSV 的每一列都要对得上。

        ⚠ 这条断言的力量取决于「有多少表真的建好了」。上一版把缺表记成 pending
        就算过，于是 8 张表、三十多个凭空发明的列名一次都没被验证过而测试全绿。
        现在缺表由 test_missing_tables_are_not_a_silent_pass 与 __main__ 的
        SKIPPED-WITH-WARNING 兜底，这里只负责已建表。
        """
        n, errs, missing = pools.check_columns()
        self.assertEqual(errs, [], '\n'.join(['列名对不上：'] + errs))
        self.assertGreater(n, 0, '一列都没核到，说明测试没真的跑起来')
        print('  已建 CSV 核对 %d 个 (表,列) 全对；%d 张表还没建' % (n, len(missing)))
        if missing:
            print(pools.format_missing_demands(missing))

    def test_missing_tables_are_not_a_silent_pass(self):
        """**缺表必须能把自己的列名需求全打出来** —— 修的就是「绿灯说谎」那个洞。

        拿一个空目录当 series/ 跑一遍 check_columns：
        每一张表都该出现在缺表字典里，且每张表都要带着它被引用的全部列名。
        只要这个机制活着，将来任何一张新表在落地之前，都能拿这份清单去对官方报表。
        """
        empty = tempfile.mkdtemp(prefix='pools_noseries_')
        try:
            n, errs, missing = pools.check_columns(empty)
            self.assertEqual(n, 0)
            self.assertEqual(errs, [], '空目录里不该有"列对不上"，只该有"表没建"')
            self.assertEqual(sorted(missing), sorted(pools.column_demands()),
                             '缺表字典漏了表')
            self.assertTrue(missing, '空目录居然没有缺表 —— 检查逻辑坏了')
            for name, cols in missing.items():
                self.assertTrue(cols, '缺表 %s 一个列名需求都没打出来 —— '
                                      '这正是上一版的洞：表名有了、需求没了' % name)
            text = pools.format_missing_demands(missing)
            for name, cols in missing.items():
                self.assertIn('series/' + name, text)
                for c in cols:
                    self.assertIn(c, text)
        finally:
            shutil.rmtree(empty, ignore_errors=True)


class TestErrorsAreLoud(unittest.TestCase):
    """错误必须响：三种断链一律抛异常，绝不返回 NaN 或 0。"""

    @classmethod
    def setUpClass(cls):
        cls.dir = make_fixture_dir()
        cls.specs = notional.load_specs(cls.dir)
        cls.fx = notional.load_fx(cls.dir)
        cls.prices = notional.load_prices(cls.dir)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def test_unknown_product(self):
        with self.assertRaises(notional.UnknownProduct):
            notional.to_base_notional({'2026-07': 1.0}, 'NO_SUCH_PRODUCT',
                                      self.specs, self.fx)

    def test_missing_base_price(self):
        with self.assertRaises(notional.MissingBasePrice):
            notional.to_base_notional({'2026-07': 1.0}, 'FIX_NOPRICE',
                                      self.specs, self.fx)

    def test_missing_fx_month(self):
        # FIX_OTHERCCY 用 XTT，夹具只给了它基期汇率，没给 2026-07
        with self.assertRaises(notional.MissingFxMonth):
            notional.to_current_notional({'2026-07': 1.0}, 'FIX_OTHERCCY',
                                         self.specs, self.fx, self.prices)
        # 但定基口径只用基期汇率，所以它照样算得出来 —— 这个区分是有意的
        out = notional.to_base_notional({'2026-07': 1.0}, 'FIX_OTHERCCY',
                                        self.specs, self.fx)
        self.assertIsNotNone(out['2026-07'])

    def test_missing_price_month(self):
        with self.assertRaises(notional.MissingPrice):
            notional.to_current_notional({'2099-01': 1.0}, 'FIX_HANDCALC',
                                         self.specs, self.fx, self.prices)

    def test_src_kind_must_match_spec_kind(self):
        leg = {'col': 'a', 'src': 'shares', 'unit_scale': 1.0, 'per_day': None,
               'product': 'FIX_HANDCALC'}          # 规格表里它是 contract
        with self.assertRaises(notional.ChainError):
            notional.resolve_leg(lambda c, x: {'2026-07': 1.0}, leg, 'x.csv',
                                 self.specs, self.fx)

    def test_missing_specs_file(self):
        empty = tempfile.mkdtemp(prefix='pools_empty_')
        try:
            with self.assertRaises(notional.SpecMissing):
                notional.load_specs(empty)
            with self.assertRaises(notional.SpecMissing):
                notional.load_fx(empty)
        finally:
            shutil.rmtree(empty, ignore_errors=True)

    def test_fx_direction_guard(self):
        """USD 那一列不是 1.0 = 整张汇率表取了倒数，必须当场炸。"""
        d = tempfile.mkdtemp(prefix='pools_fxbad_')
        try:
            _write(os.path.join(d, notional.FX_CSV),
                   ['month', 'obs_days', 'eom_date',
                    'fx_avg_usdusd', 'fx_eom_usdusd'],
                   [['2019-01', 22, '2019-01-31', 0.92, 0.92]])
            with self.assertRaises(notional.SpecInconsistent):
                notional.load_fx(d)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_fx_half_a_currency_is_rejected(self):
        """只有 avg 没有 eom 的币种必须炸 —— 半张表会让存量口径静默回落到流量汇率。"""
        d = tempfile.mkdtemp(prefix='pools_fxhalf_')
        try:
            _write(os.path.join(d, notional.FX_CSV),
                   ['month', 'obs_days', 'eom_date', 'fx_avg_xtsusd'],
                   [['2019-01', 22, '2019-01-31', 0.5]])
            with self.assertRaises(notional.SpecInconsistent):
                notional.load_fx(d)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_fx_row_misalignment_is_caught(self):
        """eom_date 不在 month 那个月里 = 整张表错位了一行。"""
        d = tempfile.mkdtemp(prefix='pools_fxskew_')
        try:
            _write(os.path.join(d, notional.FX_CSV),
                   ['month', 'obs_days', 'eom_date',
                    'fx_avg_xtsusd', 'fx_eom_xtsusd'],
                   [['2019-01', 22, '2019-02-28', 0.5, 0.6]])
            with self.assertRaises(notional.SpecInconsistent):
                notional.load_fx(d)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_unknown_fx_basis_is_rejected(self):
        with self.assertRaises(notional.ChainError):
            notional.fx_rate(self.fx, FIX_CCY, notional.BASE_MONTH, basis='mid')
        with self.assertRaises(notional.ChainError):
            notional.basis_for_flow('per_quarter')

    def test_spec_redundant_column_guard(self):
        """base_notional_per_unit_local 与 multiplier×base_price 对不上必须炸。"""
        d = tempfile.mkdtemp(prefix='pools_specbad_')
        try:
            _write(os.path.join(d, notional.SPECS_CSV),
                   ('product_id,zh,exchange,kind,ccy,multiplier,mult_unit,'
                    'base_month,base_price_local,base_notional_per_unit_local,'
                    'price_id,source,evidence,notes').split(','),
                   [['X', 'x', 'X', 'contract', FIX_CCY, 50, 'u',
                     notional.BASE_MONTH, 2600, 130001,      # 差 1
                     'PX', 's', 'e', 'n']])
            with self.assertRaises(notional.SpecInconsistent):
                notional.load_specs(d)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_base_month_must_be_locked(self):
        d = tempfile.mkdtemp(prefix='pools_basebad_')
        try:
            _write(os.path.join(d, notional.SPECS_CSV),
                   ('product_id,zh,exchange,kind,ccy,multiplier,mult_unit,'
                    'base_month,base_price_local,base_notional_per_unit_local,'
                    'price_id,source,evidence,notes').split(','),
                   [['X', 'x', 'X', 'contract', FIX_CCY, 50, 'u',
                     '2020-01', 2600, 130000, 'PX', 's', 'e', 'n']])
            with self.assertRaises(notional.SpecInconsistent):
                notional.load_specs(d)
        finally:
            shutil.rmtree(d, ignore_errors=True)


class TestSignedLegs(unittest.TestCase):
    """减法腿（sign=-1）与生效起点（since）—— 口径断点可逆的那套机制。"""

    @classmethod
    def setUpClass(cls):
        cls.dir = make_fixture_dir()
        cls.specs = notional.load_specs(cls.dir)
        cls.fx = notional.load_fx(cls.dir)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def _chain(self, since='2025-11'):
        return [
            {'col': 'main', 'src': 'contracts', 'unit_scale': 1.0, 'per_day': None,
             'product': 'FIX_HANDCALC'},
            {'col': 'memo', 'of_col': 'main', 'src': 'contracts', 'unit_scale': 1.0,
             'per_day': None, 'sign': -1, 'since': since, 'why': '并购口径还原',
             'product': 'FIX_HANDCALC'},
        ]

    def test_minus_leg_subtracts_after_the_since_month(self):
        def get(_csv, col):
            return {'2025-10': 100.0 if col == 'main' else 30.0,
                    '2025-11': 100.0 if col == 'main' else 30.0}

        out = notional.resolve_chain(get, self._chain(), 'x.csv', self.specs, self.fx)
        k = notional.base_notional_per_unit_usd('FIX_HANDCALC', self.specs, self.fx)
        # 2025-10 主列还不含备注列 ⇒ 减法腿贡献 0，结果就是主列本身
        self.assertAlmostEqual(out['2025-10'], 100.0 * k, places=4)
        # 2025-11 起主列已含备注列 ⇒ 减掉它才是 legacy 口径
        self.assertAlmostEqual(out['2025-11'], 70.0 * k, places=4)

    def test_without_since_the_same_data_would_go_negative_and_raise(self):
        """把 since 拿掉（或写早），本该是 30 的月份会变成 −70 —— 必须抛异常。

        这就是 Euronext 的真实形状：2025-08 单股期货主列 0.080k、athex 备注列 28.553k。
        没有护栏时它会静默画出一条掉到 0 以下的线，而堆叠份额带会把负数吃掉。
        """
        def get(_csv, col):
            return {'2025-08': 0.08 if col == 'main' else 28.55}

        with self.assertRaises(notional.ChainError):
            notional.resolve_chain(get, self._chain(since='2019-01'), 'x.csv',
                                   self.specs, self.fx)

    def test_since_makes_a_pre_launch_month_zero_not_none(self):
        """开业前的月份是**零**不是缺 —— 否则 add_series 会把整月置 None。"""
        chain = [
            {'col': 'old', 'src': 'contracts', 'unit_scale': 1.0, 'per_day': None,
             'product': 'FIX_HANDCALC'},
            {'col': 'new', 'src': 'contracts', 'unit_scale': 1.0, 'per_day': None,
             'since': '2024-08', 'product': 'FIX_HANDCALC'},
        ]

        def get(_csv, col):
            if col == 'old':
                return {'2016-01': 10.0, '2026-07': 10.0}
            return {'2016-01': None, '2026-07': 5.0}     # 开业前源列是空的

        out = notional.resolve_chain(get, chain, 'x.csv', self.specs, self.fx)
        k = notional.base_notional_per_unit_usd('FIX_HANDCALC', self.specs, self.fx)
        self.assertAlmostEqual(out['2016-01'], 10.0 * k, places=4)
        self.assertAlmostEqual(out['2026-07'], 15.0 * k, places=4)

    def test_pairwise_guard_catches_what_the_chain_total_hides(self):
        """逐对护栏必须抓住「合计仍为正、但某一对减出负数」的情形。

        这不是假想：Euronext 2025-08 单股期货 0.080 − 28.553 = −28.47，
        而同链的单股期权 233.9 把合计盖成正的 349.7。只有整链护栏时它一声不吭。
        """
        chain = [
            {'col': 'fut', 'src': 'contracts', 'unit_scale': 1.0, 'per_day': None,
             'product': 'FIX_HANDCALC'},
            {'col': 'opt', 'src': 'contracts', 'unit_scale': 1.0, 'per_day': None,
             'product': 'FIX_HANDCALC'},
            {'col': 'athex_fut', 'of_col': 'fut', 'src': 'contracts',
             'unit_scale': 1.0, 'per_day': None, 'sign': -1, 'since': '2019-01',
             'why': 'x', 'product': 'FIX_HANDCALC'},
        ]
        vals = {'fut': 0.080, 'opt': 233.886, 'athex_fut': 28.553}

        def get(_csv, col):
            return {'2025-08': vals[col]}

        # 先确认合计确实是正的 —— 否则这条测试证明不了「逐对比整链更灵敏」
        self.assertGreater(vals['fut'] + vals['opt'] - vals['athex_fut'], 0)
        with self.assertRaises(notional.ChainError) as cm:
            notional.resolve_chain(get, chain, 'x.csv', self.specs, self.fx)
        self.assertIn('athex_fut', str(cm.exception))

    def test_every_minus_leg_declares_why_since_and_of_col(self):
        """池定义里的每一条减法腿都必须交代减的是什么、从哪个月起、修正的是哪条主列。"""
        n = 0
        for p in pools.POOLS:
            for label, _csv, chain in pools.chains_of(p):
                cols = {lg['col'] for lg in chain if lg.get('sign', 1) > 0}
                for leg in chain:
                    if leg.get('sign', 1) < 0:
                        n += 1
                        self.assertTrue(leg.get('why'), '%s 的减法腿没写 why' % label)
                        self.assertTrue(leg.get('since'),
                                        '%s 的减法腿没写 since' % label)
                        self.assertIn(leg.get('of_col'), cols,
                                      '%s 的减法腿 of_col 不指向同链的主列' % label)
                        self.assertTrue(leg['col'].startswith('athex_'),
                                        '%s 减的不是 athex_* 备注列：%s'
                                        % (label, leg['col']))
        self.assertGreaterEqual(n, 8, '减法腿一条都没跑到，说明 Euronext 那几个池'
                                      '又退回了不可逆的口径')

    def test_enx_legacy_chain_against_the_real_csv(self):
        """拿**真 enx.csv** 跑 Euronext 的 legacy 链 —— 夹具证明不了的那一半。

        两件事：(a) legacy 口径下 2025-11 的并表断点消失（主列本身有明显跳升）；
        (b) 把 since 拿掉，真实数据必须触发逐对护栏。
        夹具里的 100 vs 1000 是编的，只有真数据能证明这套机制对得上这张表。
        """
        path = os.path.join(pools.SERIES, 'enx.csv')
        if not os.path.exists(path):
            self.skipTest('series/enx.csv 还没建')
        import csv as _csv
        with open(path, newline='', encoding='utf-8') as f:
            rows = list(_csv.DictReader(f))

        def get(_csv_name, col):
            return {r['month']: (float(r[col]) if (r.get(col) or '').strip() else None)
                    for r in rows}

        m = [x for x in pools.pool('eu_deriv')['members'] if x['key'] == 'enx'][0]
        out = notional.resolve_chain(get, m['chain'], 'enx.csv', self.specs, self.fx)
        k = notional.base_notional_per_unit_usd('ENX_INDEX_DERIV', self.specs, self.fx)
        oct25, nov25 = out['2025-10'] / k, out['2025-11'] / k
        self.assertLess(abs(nov25 / oct25 - 1.0), 0.15,
                        'legacy 口径下 2025-10 → 2025-11 仍有 %.0f%% 的跳变，'
                        '并表断点没被减掉' % ((nov25 / oct25 - 1.0) * 100))
        for mon, v in out.items():
            if v is not None:
                self.assertGreater(v, 0, '%s 算出非正数' % mon)

        stripped = [{k2: v for k2, v in lg.items() if k2 != 'since'}
                    for lg in m['chain']]
        with self.assertRaises(notional.ChainError) as cm:
            notional.resolve_chain(get, stripped, 'enx.csv', self.specs, self.fx)
        self.assertIn('athex_adv_singlestock_futures_kcontracts', str(cm.exception))
        print('\n  真 enx.csv：legacy 口径 2025-10 = %.0f → 2025-11 = %.0f 张/日'
              '（主列本身是 %.0f → %.0f，断点已剔）'
              % (oct25, nov25,
                 sum(get('', c)['2025-10'] for c in m['contracts_col']) * 1000,
                 sum(get('', c)['2025-11'] for c in m['contracts_col']) * 1000))

    def test_implied_days_ratio(self):
        """隐含交易日 = 月度总量 ÷ 官方日均。SGX 是仓内唯一用它的地方。"""
        chain = [{'col': 'vol_fx', 'src': 'contracts', 'unit_scale': 1.0,
                  'per_day': {'col': 'deriv_vol', 'div_col': 'ddav'},
                  'product': 'FIX_HANDCALC'}]
        # 实测形状：34,315,225 ÷ 1,619,444 = 21.19 天
        vals = {'vol_fx': 10268040.0, 'deriv_vol': 34315225.0, 'ddav': 1619444.0}

        def get(_csv, col):
            return {'2026-06': vals[col]}

        out = notional.resolve_chain(get, chain, 'x.csv', self.specs, self.fx)
        k = notional.base_notional_per_unit_usd('FIX_HANDCALC', self.specs, self.fx)
        days = 34315225.0 / 1619444.0
        self.assertAlmostEqual(days, 21.1893, places=3)
        self.assertAlmostEqual(out['2026-06'], 10268040.0 / days * k, places=2)

    def test_dual_unit_identity_is_machine_checked(self):
        """dual_note 承诺的「名义额份额 ≡ 张数份额」必须机器可查。

        恒等只在分母与全部 in_share 成员解析到**同一个 product_id** 时成立。
        这里既验现状（两池都满足），也验护栏真的会响（改坏一条腿就该报错）。
        """
        duals = [p for p in pools.POOLS if p.get('dual_unit')]
        self.assertTrue(duals)
        for p in duals:
            prods = {leg['product'] for leg in p['denom']['chain']}
            prods |= {leg['product'] for m in p['members'] if m.get('in_share')
                      for leg in (m.get('chain') or [])}
            self.assertEqual(len(prods), 1,
                             '池 %s 的分母与 in_share 成员不是同一个 product：%s'
                             % (p['id'], sorted(prods)))

        # 护栏本身：把一个 in_share 成员的产品换掉，validate() 必须报错
        p = pools.pool('na_cash')
        victim = [m for m in p['members'] if m.get('in_share')][1]
        old = victim['chain'][0]['product']
        victim['chain'][0]['product'] = 'CA_CASH_EQUITY_SHARE'
        try:
            errs = [e for e in pools.validate() if 'dual_note' in e or '同一个 ' in e]
            self.assertTrue(errs, 'dual_unit 恒等式护栏没有响 —— '
                                  '换掉一个成员的产品居然体检全过')
        finally:
            victim['chain'][0]['product'] = old
        self.assertEqual(pools.validate(), [], '护栏测试没把池定义改回来')


class TestPendingProducts(unittest.TestCase):
    """分批上线：规格没填齐时，build 脚本要拿得到「差哪些」的清单而不是异常。"""

    def test_pending_products_lists_gaps(self):
        d = make_fixture_dir()
        try:
            specs = notional.load_specs(d)
            todo = notional.pending_products(
                pools.products_used() + ['FIX_NOPRICE', 'NOT_THERE'], specs)
            names = dict(todo)
            self.assertIn('FIX_NOPRICE', names)
            self.assertIn('NOT_THERE', names)
            self.assertNotIn('CME_RATES', names)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_real_repo_state_is_reported_not_crashed(self):
        """规格没填齐不是失败，是分批上线的状态 —— 但要报出来。"""
        try:
            specs = notional.load_specs(pools.SERIES)
            todo = notional.pending_products(pools.products_used(), specs)
            state = '已建（%d 个产品，其中 %d 个待实测）' % (len(specs), len(todo))
        except notional.SpecMissing:
            state = '未建（待另一步实测入库）'
        missing = pools.missing_csvs()
        print('  仓内状态：contract_specs.csv %s；%d 个成员 CSV 待建（%s）'
              % (state, len(missing), ', '.join(missing) or '无'))


class TestContractSpecsClean(unittest.TestCase):
    """把 build/check_specs.py 接进来 —— 在此之前它一个调用方都没有。

    check_specs 查的全是「错了图上看不出来」的问题（乘数为 0、两代规格区间断档、
    冗余列与乘数×基期价对不上、avg_close 与别的基准混表……）。它写得再好，
    只要没人跑，表被改坏时就不会有任何东西报警 —— 一道没人跑的闸门等于没有闸门。

    这里只断言退出码，不复述它的检查项：那些检查的语义归 check_specs 自己维护，
    在这里复制一份，两处迟早会各说各话。它自己的逻辑由 `--selftest` 的合成行守
    （下一条测试），本条守的是「真表现在是干净的」。

    另一处调用方在 monthly_run.py 的 preflight（工作树检查之后、下载之前）。
    两处都要有：这里守「改代码/改表之后手跑测试」，那里守「无人值守的 cron」。
    """

    def test_contract_specs_clean(self):
        import check_specs                                  # noqa: PLC0415
        self.assertEqual(check_specs.main([]), 0,
                         'series/contract_specs.csv 体检未通过 —— '
                         '逐条错误见上面 check_specs 的输出')

    def test_check_specs_selftest_passes(self):
        """check_specs 自己的合成行自检也必须绿。

        为什么连这条也接进来：真表里**没有一个多代规格组**，所以 _check_effective
        的主分支在真实数据上一次都跑不到。一段从没被执行过的检查代码，与没有这段
        代码是一回事 —— 等到真有合约改规格那天，没人知道它是不是坏的。
        """
        import check_specs                                  # noqa: PLC0415
        self.assertEqual(check_specs.main(['--selftest']), 0)


def main():
    """跑测试，然后按「表齐不齐」给出明确的收尾行。

    unittest 的 PASS 只说明「已建表上的断言全过」。缺一张表就意味着有一批列名
    从没被任何真实表头验证过 —— 那种状态下打印 PASS 就是在说谎（上一版正是如此）。
    所以收尾行分三种：FAILED / SKIPPED-WITH-WARNING / PASS，
    且 SKIPPED-WITH-WARNING 会把每张缺表被要求的全部列名打出来。
    """
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)

    _n, cerrs, missing = pools.check_columns()
    print('\n' + '=' * 72)
    if not result.wasSuccessful() or cerrs:
        print('FAILED —— %d 处失败 / %d 处错误 / %d 处列名对不上'
              % (len(result.failures), len(result.errors), len(cerrs)))
        return 1
    if missing:
        print('SKIPPED-WITH-WARNING —— 断言全过，但 %d 张 series/*.csv 还没建，'
              '下面这些列名**一个都没有被真实表头验证过**：' % len(missing))
        print(pools.format_missing_demands(missing))
        print('（表落地之前，请拿这份清单逐条对官方报表的字段名；'
              '上一版就是靠"表没建=不算错"让三十多个凭空发明的列名一路全绿的）')
        return 0
    print('PASS —— 断言全过，且 %d 张 series/*.csv 全部就位，'
          '%d 个 (表,列) 逐个核过真实表头' % (len(pools.column_demands()), _n))
    return 0


if __name__ == '__main__':
    sys.exit(main())
