# -*- coding: utf-8 -*-
"""fetch/fx.py 的尾部护栏测试 —— 全部离线，只用标准库。

跑法: python3 fetch/test_fx.py

━━ 这套测试守的是哪一件事 ━━
fx.py 里 `_scope()` 对「10 个币种发布日集合不一致」的月份一律跳过。
这对**头部**是对的（BRL 2008 年以前不在 ECB 参考汇率名单上，是事实不是故障），
对**尾部**却是一个不留任何痕迹的失败：

    · compute_monthly 少算一个月，_validate **一条都不报**（它只体检算出来的那些月）；
    · latest_month 无声退回上一个月；
    · update 因此一行都不写 —— README 的「缺列一律失败」护栏守的是写进去的东西，
      什么都不写恰好绕过它，也不会留下 NaN；
    · fx 不上任何页面，首页没有它的红点。

所以这个 bug 的全部表现就是「序列停在旧月份」，而序列停在旧月份平时也可能是
ECB 还没发 —— 两者在日志上长得一模一样。这类故障只能靠**主动去撞**发现，
本文件就是那一撞。

━━ 夹具是编的，测的是逻辑不是世界 ━━
下面的汇率都是构造值（只保证落在 fx.PLAUSIBLE 的粗筛区间里，好让 _validate 放行），
发布日历用「周一至周五」代替 TARGET2 营业日。它测的是「缺尾会不会被抓住」，
不是「2026 年 7 月的欧元到底值多少」—— 后者是 fetch/fx.py 与 ECB 之间的事。

━━ 修复前 vs 修复后（2026-08-06 实测，同一份测试文件分别打两版 fx.py）━━
    修复前（无 _check_tail）：Ran 9 tests，FAILED (failures=5)
        test_tail_gap_must_raise / test_tail_gap_regression_signature /
        test_tail_gap_one_missing_day_also_caught / test_usd_month_truncated_is_caught /
        test_latest_obs_spread_is_caught
    修复后：Ran 9 tests，OK
两版都绿的 test_head_gap_still_allowed 是**对照组** —— 它证明这次修的是尾部，
头部那条「缺币种照常跳过」的合法行为一个字都没动。
"""

import datetime
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fx        # noqa: E402


# ═══════════════════════════════════════════════════════════════════════════
# 合成夹具
# ═══════════════════════════════════════════════════════════════════════════
# 「1 欧元 = 多少 X」，与 ECB 的报价方向一致（fx._cross 会拿 USD 那条去除它们）。
# 挑数的唯一标准：交叉出来的「1 单位外币 = 多少美元」要落在 fx.PLAUSIBLE 区间内，
# 否则 _validate 会先于尾部检查报错，测试就测不到想测的那条路径。
EUR_PER = {
    'USD': 1.10,     # ⇒ EUR 交叉 = 1.10           ∈ (0.50, 2.50)
    'GBP': 0.85,     # ⇒ 1.294                     ∈ (0.80, 3.00)
    'HKD': 8.60,     # ⇒ 0.1279                    ∈ (0.1265, 0.1300)
    'JPY': 160.0,    # ⇒ 0.006875                  ∈ (0.0020, 0.0300)
    'SGD': 1.48,     # ⇒ 0.7432                    ∈ (0.35, 1.10)
    'AUD': 1.65,     # ⇒ 0.6667                    ∈ (0.30, 1.40)
    'CAD': 1.50,     # ⇒ 0.7333                    ∈ (0.40, 1.30)
    'BRL': 6.00,     # ⇒ 0.1833                    ∈ (0.03, 1.00)
    'CHF': 0.95,     # ⇒ 1.1579                    ∈ (0.40, 2.00)
    'SEK': 11.50,    # ⇒ 0.0957                    ∈ (0.04, 0.30)
}
# daily 的键就是 _fetch_sdmx 返回的那一套：USD + 除 EUR 外的 9 个币种。
# EUR 不是键 —— 它由 USD 那条直接给出（fx._cross）。这一点必须与被测代码一致，
# 否则夹具与代码会像上一轮 test_pools 那样「自洽但与仓库不符」。
KEYS = ['USD'] + [c for c in fx.CURRENCIES if c != 'EUR']

FIRST_DAY = datetime.date(2026, 5, 1)
# 当前未完月 = 2026-08（5 个工作日：3-7 号），最新完整月 = 2026-07。
# 未完月要留够 5 天，判据二的 3 天容差才有测得出「超了」与「没超」两侧的余地。
LAST_DAY = datetime.date(2026, 8, 7)


def business_days(first=FIRST_DAY, last=LAST_DAY):
    """周一至周五当发布日。不建假日表：夹具不需要真日历，真日历由 ECB 自己给。"""
    out, d = [], first
    while d <= last:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += datetime.timedelta(days=1)
    return out


def make_daily(drop=None):
    """构造 {'CCY': {'YYYY-MM-DD': 1 欧元 = 多少 CCY}}。

    drop = ('SEK', '2026-07')：把 SEK 在 2026-07 及之后的观测**整段删掉**，
    复现验收员实测的那个形态（币种被移出名单 / 响应被截断，尾部一段没有值）。
    """
    days = business_days()
    daily = {c: {d: EUR_PER[c] for d in days} for c in KEYS}
    if drop:
        ccy, since = drop
        daily[ccy] = {d: v for d, v in daily[ccy].items() if d[:7] < since}
    return daily


class TestHealthyBaseline(unittest.TestCase):
    """先证明夹具本身是干净的 —— 否则下面的「必红」测不出是谁红的。"""

    def test_healthy_data_passes(self):
        monthly = fx.compute_monthly(make_daily())
        latest = fx._validate(monthly)
        self.assertEqual(latest, '2026-07',
                         '干净夹具下最新完整月应是 2026-07（2026-08 还没过完）')
        self.assertEqual(sorted(monthly), ['2026-05', '2026-06', '2026-07'])
        # 口径坑 2 的方向检查：外币金额 × fx = 美元金额，JPY 那列必须是 0.006 不是 158
        self.assertAlmostEqual(monthly['2026-07']['fx_avg_jpyusd'], 1.10 / 160.0, places=12)


class TestTailGuard(unittest.TestCase):
    """本文件的正题：尾部缺币种必须炸，头部缺币种必须放行。"""

    def test_tail_gap_must_raise(self):
        """删掉 SEK 的 2026-07 起观测 ⇒ compute_monthly 必须抛 FxFetchError。

        **这条就是修复前红、修复后绿的那条。** 修复前它不抛任何异常。
        """
        with self.assertRaises(fx.FxFetchError) as cm:
            fx.compute_monthly(make_daily(drop=('SEK', '2026-07')))
        msg = str(cm.exception)
        self.assertIn('2026-07', msg, '错误信息必须点名是哪个月，否则排查得从头翻')
        self.assertIn('SEK', msg, '错误信息必须点名是哪个币种缺')
        self.assertIn('只有 0 个', msg, '错误信息必须给出该币种的实际发布日数')

    def test_tail_gap_regression_signature(self):
        """修复前的**具体症状**：latest_month 静默退回，且一条异常都没有。

        这条测试断言的是「症状不再出现」，与上一条互补：上一条查「有没有炸」，
        这条查「炸之前会不会先算出一个看起来正常的旧月份」。修复前，
        下面这行会安静地返回 '2026-06'（少一个月），没有任何异常、没有任何日志。
        """
        daily = make_daily(drop=('SEK', '2026-07'))
        # 先确认「不做尾部检查时确实会静默退回」—— 直接走 _scope，绕开 _check_tail
        scope = fx._scope(daily)
        silent = [m for m in sorted(scope) if m < max(daily['USD'])[:7]]
        self.assertEqual(silent[-1], '2026-06',
                         '前提没成立：_scope 本该把 2026-07 跳掉（这正是 bug 的机理）')
        # 修复后：同一份数据必须炸，而不是返回这个 2026-06
        with self.assertRaises(fx.FxFetchError):
            fx.compute_monthly(daily)

    def test_tail_gap_one_missing_day_also_caught(self):
        """不是整段缺失、只缺一天，同样要抓 —— 21 天里少 1 天只偏千分之几。

        这正是 _scope 的 docstring 说的「错得刚好看不出来」的区间。
        """
        daily = make_daily()
        victim = sorted(d for d in daily['CHF'] if d.startswith('2026-07'))[3]
        del daily['CHF'][victim]
        with self.assertRaises(fx.FxFetchError) as cm:
            fx.compute_monthly(daily)
        self.assertIn('CHF', str(cm.exception))

    def test_head_gap_still_allowed(self):
        """头部合法缺席不受影响 —— BRL 2008 年以前不在名单上是事实不是故障。"""
        daily = make_daily()
        for d in list(daily['BRL']):
            if d[:7] == '2026-05':          # 假装 BRL 是 2026-06 才纳入名单的
                del daily['BRL'][d]
        monthly = fx.compute_monthly(daily)
        self.assertEqual(sorted(monthly), ['2026-06', '2026-07'],
                         '头部缺币种应当只是少算那几个月，不该抛异常')

    def test_usd_month_truncated_is_caught(self):
        """尾部月份连 USD 自己都不全（响应被截断）—— 报的是发布日数不足，不是币种不齐。"""
        daily = make_daily()
        for c in KEYS:
            for d in sorted(x for x in daily[c] if x.startswith('2026-07'))[10:]:
                del daily[c][d]
        with self.assertRaises(fx.FxFetchError) as cm:
            fx.compute_monthly(daily)
        self.assertIn('只有 10 个发布日', str(cm.exception))

    def test_latest_obs_spread_is_caught(self):
        """加固判据：某币种在**当前未完月**中途断掉，当天就要报，不等下个月。

        只删 2026-08 的尾巴 —— 最新完整月 2026-07 仍然齐备，判据一放行，
        全靠判据二（10 个币种最新观测日不许拉开）把它抓住。
        """
        daily = make_daily()
        for d in sorted(x for x in daily['AUD'] if x.startswith('2026-08'))[-4:]:
            del daily['AUD'][d]
        with self.assertRaises(fx.FxFetchError) as cm:
            fx.compute_monthly(daily)
        self.assertIn('AUD', str(cm.exception))
        self.assertIn('落后', str(cm.exception))

    def test_latest_obs_spread_tolerates_one_day(self):
        """个别币种当天未定盘（口径坑 5 提到的空值）不该炸 —— 容差是 3 个发布日。"""
        daily = make_daily()
        del daily['AUD'][max(daily['AUD'])]
        fx.compute_monthly(daily)       # 不抛就是通过


class TestValidateStillWorks(unittest.TestCase):
    """尾部检查不许把既有的粗筛顶掉：取了倒数仍然要被 _validate 抓住。"""

    def test_inverted_rate_still_caught(self):
        daily = make_daily()
        for d in daily['JPY']:
            daily['JPY'][d] = 1.0 / 160.0        # 手滑取了倒数
        with self.assertRaises(fx.FxFetchError) as cm:
            fx._validate(fx.compute_monthly(daily))
        self.assertIn('跑出粗筛区间', str(cm.exception))


def main():
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.TestLoader().loadTestsFromModule(sys.modules[__name__]))
    print('\n' + '=' * 72)
    if not result.wasSuccessful():
        print('FAILED —— %d 处失败 / %d 处错误'
              % (len(result.failures), len(result.errors)))
        return 1
    print('PASS —— 尾部护栏在位。把 fx._check_tail 摘掉，这 9 条里会有 5 条立刻变红'
          '（清单见模块 docstring 末尾），头部那条对照组仍然绿。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
