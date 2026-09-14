# -*- coding: utf-8 -*-
"""monthly_run 慢腿闸门的护栏测试（SLOW_LEGS / slow_pending / _due_month）—— 全部离线，
只用标准库 + 本仓 git 历史。

跑法: python3 test_slow_legs.py

━━ 这套测试守的是哪一件事 ━━
SLOW_LEGS 与 slow_pending 在本文件之前全仓零测试引用；_due_month 只在 build/test_guards.py
的红点对拍里被当算术调用，那组不碰 SLOW_LEGS。本文件是这张登记表的首套测试，分四组：

  · TestDueMonth —— 开闸日算术，钉住 miax 的 (3, 3) 与「季末月取第二位」。
  · TestMiaxReplay —— 2026-09 miax「API 腿先到、IR 腿后到」的现场重放。数据不做夹具，
    取本仓 git 历史里的 3b0ea1d（「更新数据: cost 2026-08, cme 2026-08, miax 2026-08」）：
    那一刻 API 头条腿已进 2026-08，IR 报表腿与历史档案列还停在 2026-07。没登记时 not_due
    从那天起判「追平」，09-04 已发的报表到 09-14 零请求，/exchanges-na/ 钉在 Jul-26。
  · TestFailOpen —— 登记写坏（一列都匹配不上、开闸日不是二元组、条目不是二元组、前缀元组
    漏了逗号成了裸字符串）一律按「欠货」返回 True、打 ⚠，**绝不抛**。2026-09 之前解包在
    try 之外，一条写坏的登记会从 not_due 抛出，带崩整轮 28 家。
  · TestRegistryInvariants —— 读真代码常量（SLOW_LEGS / TICKERS / EARLY / EARLY_BY /
    DEAD_COLS / roster.LAG）与真 series 表头，不变式 a–e 见各方法。

━━ 为什么不进 preflight ━━
  (1) 不变式 b 与现场重放读 series 表头和 git 历史，属于数据；preflight 只查配置与代码
      （monthly_run 模块 docstring 里 preflight 与收尾闸门的那条分界线）。
  (2) slow_pending 已全体 fail-open，这张表任何写错的后果都是「多下载 + 打 WARN」，
      不值得拿「28 家当天全不发」去赌。
  (3) 与 test_commit_label.py 同形：离线、秒级、手工跑。README「改过生成器或引擎之后」
      那节的校验清单里列着本文件 —— 改 SLOW_LEGS 时必跑。
"""

import ast
import contextlib
import csv
import datetime
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

import monthly_run as M                    # noqa: E402

D = datetime.date

#: 2026-09-03 那次数据提交：miax 的 API 头条腿进了 2026-08，登记的 11 列都还停在 2026-07。
REPLAY_COMMIT = '3b0ea1d'

#: SLOW_LEGS['miax'] 应当恰好命中的 11 列（源 A 报表的 10 条非滞后列 + 源 C 历史档案的 1 列）。
#: 写死是刻意的：不变式 e 要同时咬住「多收一列」与「少收一列」两个方向。
MIAX_SLOW = frozenset((
    'trading_days_options', 'industry_adv_options_kcontracts',
    'adv_multilist_options_kcontracts', 'share_multilist_options_pct',
    'industry_adv_equities_mnshares', 'adv_equities_mnshares', 'share_equities_pct',
    'trading_days_futures', 'adv_futures_ag_contracts', 'adv_futures_fin_contracts',
    'vol_futures_ag_contracts',
))
SOURCE_C = 'vol_futures_ag_contracts'


def _git(*args):
    r = subprocess.run(['git'] + list(args), cwd=ROOT, capture_output=True, text=True)
    return r.returncode, r.stdout


def _pdf_lagged():
    """fetch/miax.py 的 _PDF_LAGGED（按设计晚一整期的四条 RPC / capture）。

    用 ast 读模块级字面量，不 import fetch/miax.py —— 与 slow_pending「不 import fetch
    模块」同一个取向：这里只要那几个列名，不该为此执行 fetch 模块的模块级代码。
    """
    path = os.path.join(ROOT, 'fetch', 'miax.py')
    with open(path, encoding='utf-8') as f:
        tree = ast.parse(f.read(), path)
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(x, ast.Name) and x.id == '_PDF_LAGGED' for x in node.targets):
            return frozenset(ast.literal_eval(node.value))
    raise AssertionError('fetch/miax.py 里找不到 _PDF_LAGGED 的模块级字面量赋值')


def _header(t):
    with open(os.path.join(M.SERIES, f'{t}.csv'), encoding='utf-8', newline='') as f:
        return next(csv.reader(f))


def _hits(head, prefixes):
    """与 slow_pending 同一条匹配规则：跳过第 0 列 month，按前缀 startswith。"""
    return [c for i, c in enumerate(head)
            if i and any(c.startswith(x) for x in prefixes)]


def _shape_ok(reg):
    """(非空 tuple[str, ...], (int, int))。前缀元组漏了逗号会变成 str，这里单独拦。"""
    return (isinstance(reg, tuple) and len(reg) == 2
            and isinstance(reg[0], tuple) and len(reg[0]) > 0
            and all(isinstance(x, str) for x in reg[0])
            and isinstance(reg[1], tuple) and len(reg[1]) == 2
            and all(isinstance(d, int) for d in reg[1]))


def _entries():
    """形状对的登记 → [(t, 前缀元组, 开闸日)]。

    形状不对的只由不变式 a 报，免得一条坏登记在 b–e 里再刷出一串解包报错。
    """
    return [(t, reg[0], reg[1])
            for t, reg in sorted(M.SLOW_LEGS.items()) if _shape_ok(reg)]


def _call(t, today):
    """调 slow_pending 并截下 stdout —— fail-open 的 True 与真欠货的 True 只能靠这个分开。"""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        got = M.slow_pending(t, today=today)
    return got, buf.getvalue()


class TestDueMonth(unittest.TestCase):
    """开闸日 = 候选月结束后第几天（单位同 LAG）；季末月取第二位。"""

    def test_miax_open_days(self):
        self.assertEqual(M._due_month((3, 3), D(2026, 9, 2)), '2026-07')
        self.assertEqual(M._due_month((3, 3), D(2026, 9, 3)), '2026-08')
        self.assertEqual(M._due_month((3, 3), D(2026, 10, 2)), '2026-08')
        self.assertEqual(M._due_month((3, 3), D(2026, 10, 3)), '2026-09')   # 2026-09 是季末月

    def test_quarter_end_uses_second_slot(self):
        # 第一位若被误用，40 天要到 11 月才开闸，这里就会退回 2026-07
        self.assertEqual(M._due_month((40, 3), D(2026, 10, 3)), '2026-09')


class TestMiaxReplay(unittest.TestCase):
    """2026-09 现场：API 腿 09-03 先到、IR 报表 09-04 已发，本仓到 09-14 零请求。"""

    def setUp(self):
        rc, _ = _git('cat-file', '-e', REPLAY_COMMIT + '^{commit}')
        if rc != 0:
            self.skipTest(f'git 历史里没有 {REPLAY_COMMIT}（浅克隆，或不在本仓里跑）')
        rc, text = _git('show', f'{REPLAY_COMMIT}:series/miax.csv')
        self.assertEqual(rc, 0, f'git show {REPLAY_COMMIT}:series/miax.csv 失败')
        self.rows = list(csv.reader(io.StringIO(text)))
        self.head = self.rows[0]
        self.tmp = tempfile.mkdtemp(prefix='test_slow_legs_')
        self.addCleanup(shutil.rmtree, self.tmp, True)
        patcher = mock.patch.object(M, 'SERIES', self.tmp)
        patcher.start()
        self.addCleanup(patcher.stop)
        self._write()

    def _write(self):
        with open(os.path.join(self.tmp, 'miax.csv'), 'w', encoding='utf-8', newline='') as f:
            csv.writer(f, lineterminator='\n').writerows(self.rows)

    def _row(self, month):
        for r in self.rows[1:]:
            if r[0] == month:
                r.extend([''] * (len(self.head) - len(r)))
                return r
        self.fail(f'{REPLAY_COMMIT} 的 series/miax.csv 里没有 {month} 行')

    def _set(self, month, cols, value):
        r = self._row(month)
        for c in cols:
            r[self.head.index(c)] = value
        self._write()

    def _last(self, col):
        i = self.head.index(col)
        return max((r[0] for r in self.rows[1:] if i < len(r) and r[i].strip()), default='')

    def _pending(self, today):
        got, out = _call('miax', today)
        self.assertNotIn('⚠', out, f'判定走了 fail-open，返回值说明不了问题：{out!r}')
        return got

    def test_snapshot_is_the_incident(self):
        """先钉住重放数据本身：API 腿已到 2026-08，登记的 11 列全停 2026-07。"""
        aug = self._row('2026-08')
        self.assertTrue(any(aug[i].strip() for i, c in enumerate(self.head) if '_api_' in c),
                        '2026-08 行没有任何 _api_ 列有值 —— 这不是 API 腿先到的那一刻')
        for c in sorted(MIAX_SLOW):
            self.assertEqual(self._last(c), '2026-07', c)

    def test_api_leg_landed_ir_leg_owed(self):
        """09-04：头条追平了，但 11 列停在 2026-07 < 2026-08 → 欠货。这就是该开闸而没开的那天。"""
        self.assertIs(self._pending(D(2026, 9, 4)), True)

    def test_before_slow_gate_not_owed(self):
        """09-02：(3, 3) 还没开闸，今天本该有的是 2026-07，登记列都有 → 不欠。"""
        self.assertIs(self._pending(D(2026, 9, 2)), False)

    def test_filled_closes_gate(self):
        """回补后必须关闸，不许天天空打。"""
        self._set('2026-08', MIAX_SLOW, '1')
        self.assertIs(self._pending(D(2026, 9, 15)), False)

    def test_rpc_blank_does_not_hold_gate(self):
        """四条 RPC / capture 最新月空是常态（按设计晚一整期），不许把闸门顶住。"""
        self._set('2026-08', MIAX_SLOW, '1')
        for c in sorted(_pdf_lagged()):       # 前提：它们确实落后于 due，否则本条什么也没证明
            self.assertLess(self._last(c), '2026-08', c)
        self.assertIs(self._pending(D(2026, 9, 15)), False)

    def test_source_c_missing_holds_gate(self):
        """IR 报表已回补、源 C（历史档案 PDF，比报表晚 1-4 天）还没到 → 仍欠货。"""
        self._set('2026-08', MIAX_SLOW - {SOURCE_C}, '1')
        self.assertIs(self._pending(D(2026, 9, 15)), True)


class TestFailOpen(unittest.TestCase):
    """登记写坏一律按欠货处理：返回 True、打 ⚠、绝不抛。用 mock.patch.dict 注入假登记。"""

    TICKER = 'zz_fail_open'
    TODAY = D(2026, 9, 15)                    # (3, 3) 下今天本该有 2026-08

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='test_slow_legs_')
        self.addCleanup(shutil.rmtree, self.tmp, True)
        with open(os.path.join(self.tmp, f'{self.TICKER}.csv'), 'w',
                  encoding='utf-8', newline='') as f:
            # 每一列都填到 2026-08：登记只要写对就必然「不欠」，下面的 True 只能来自 fail-open
            f.write('month,trading_days_options,adv_x\n2026-07,21,1\n2026-08,21,1\n')
        patcher = mock.patch.object(M, 'SERIES', self.tmp)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _run(self, reg):
        with mock.patch.dict(M.SLOW_LEGS, {self.TICKER: reg}):
            return _call(self.TICKER, self.TODAY)

    def test_wellformed_baseline(self):
        """对照组：同一份夹具、登记写对 → False 且一个字不印。"""
        got, out = self._run((('trading_days_options',), (3, 3)))
        self.assertIs(got, False)
        self.assertEqual(out, '')

    def test_no_column_matched(self):
        got, out = self._run((('no_such_prefix_',), (3, 3)))
        self.assertIs(got, True)
        self.assertIn('一列都没匹配上', out)

    def test_open_days_none(self):
        got, out = self._run((('trading_days_options',), None))
        self.assertIs(got, True)
        self.assertIn('慢腿判定出错', out)

    def test_not_a_pair_does_not_raise(self):
        """条目不是二元组（多一项 / 少一层括号）：2026-09 之前这里抛 ValueError，
        从 not_due 一路带崩整轮 28 家。"""
        got, out = self._run(('trading_days_options', 'x', (3, 3)))
        self.assertIs(got, True)
        self.assertIn('慢腿判定出错', out)

    def test_bare_string_prefixes(self):
        """前缀元组漏了逗号成了 str：逐字符 startswith 会静默乱匹配（本夹具下会错判「不欠」）。"""
        got, out = self._run(('trading_days_options', (3, 3)))
        self.assertIs(got, True)
        self.assertIn('裸字符串', out)


class TestRegistryInvariants(unittest.TestCase):
    """读真代码常量与真 series 表头。"""

    def test_a_shape(self):
        """a：每个值是 (非空 tuple[str, ...], (int, int))，前缀元组不是 str。"""
        for t, reg in sorted(M.SLOW_LEGS.items()):
            with self.subTest(t=t):
                self.assertTrue(_shape_ok(reg),
                                f'{t}: 登记必须是 (前缀元组, (常规月, 季末月))，实际是 {reg!r}')

    def test_b_ticker_known_and_every_prefix_hits(self):
        """b：t 在 TICKERS 里，且每个前缀在 series/<t>.csv 表头至少命中一列。"""
        for t, prefixes, _ in _entries():
            with self.subTest(t=t):
                self.assertIn(t, M.TICKERS)
                head = _header(t)
                for x in prefixes:
                    self.assertTrue(_hits(head, (x,)),
                                    f'{t}: 前缀 {x!r} 在 series/{t}.csv 表头里一列都没命中')

    def test_c_not_earlier_than_headline_gate(self):
        """c：开闸日不早于本家头条闸门 max(0, LAG − EARLY_BY.get(t, (EARLY, EARLY)))。

        早于它时 slow_pending 为真，one() 整份跑 update()，头条腿当天进库 = 偷偷提前了
        头条闸门，而 docs/CRON_WIRING.md §2.2 的闸门格与 check_doc_gates 都看不见。
        """
        for t, _, open_days in _entries():
            with self.subTest(t=t):
                lag = M.due_lag(t)
                self.assertIsNotNone(lag, f'{t} 不在 build/roster.py 的 LAG 表里')
                early = M.EARLY_BY.get(t, (M.EARLY, M.EARLY))
                for i in (0, 1):
                    gate = max(0, lag[i] - early[i])
                    self.assertGreaterEqual(
                        open_days[i], gate,
                        f'{t}: 开闸日第 {i} 位 {open_days[i]} 早于头条闸门 '
                        f'max(0, LAG {lag[i]} − EARLY {early[i]}) = {gate}')

    def test_d_no_dead_cols(self):
        """d：命中列与 DEAD_COLS 登记的已停发列不相交（登记永久停发的列 = 天天下载）。"""
        for t, prefixes, _ in _entries():
            with self.subTest(t=t):
                hit = set(_hits(_header(t), prefixes))
                self.assertFalse(hit & set(M.DEAD_COLS.get(t, {})),
                                 f'{t}: 慢腿登记命中了 DEAD_COLS 里的列')

    def test_e_miax_exact_columns(self):
        """e（miax 专项）：不收 _api_ 头条列、不收 _PDF_LAGGED，命中集合恰好是那 11 列。"""
        self.assertIn('miax', M.SLOW_LEGS, 'SLOW_LEGS 里没有 miax')
        reg = {t: p for t, p, _ in _entries()}
        self.assertIn('miax', reg, 'SLOW_LEGS["miax"] 形状不对（见不变式 a）')
        hit = set(_hits(_header('miax'), reg['miax']))
        self.assertFalse({c for c in hit if '_api_' in c},
                         '收进了 _api_ 列 —— 那是头条腿，登记它等于让头条闸门永远关不上')
        lagged = _pdf_lagged()
        self.assertFalse(hit & lagged,
                         f'收进了 _PDF_LAGGED 的列 {sorted(hit & lagged)} —— 按设计晚一整期，'
                         f'last < due 恒真，闸门会被顶成天天下载')
        self.assertEqual(hit, MIAX_SLOW)


if __name__ == '__main__':
    unittest.main(verbosity=2)
