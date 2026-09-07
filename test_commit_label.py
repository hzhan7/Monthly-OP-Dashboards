# -*- coding: utf-8 -*-
"""monthly_run.staged_label() 的护栏测试 —— 全部离线，只用标准库 + 本仓 git 历史。

跑法: python3 test_commit_label.py

━━ 这套测试守的是哪一件事 ━━
commit 标题是这个仓库唯一的人读审计线索：28 家无人值守跑，出了事先看 `git log`。
2026-09-05 的 a8f2211 把这条线索写坏了 ——

    标题：更新数据: tsm 2026-08
    改动：data/tsm.js | series/tsm_fx.csv | series/umc.csv     ← **没有 series/tsm.csv**

而 series/tsm.csv 至今停在 2026-07。标题声称的那个月份在真值源里根本不存在，
`git log` 从此说 TSMC 的 8 月已经入库 —— 它没有，那天 TSMC 的 xlsx 还没发。

成因是标题采信了 fetch 模块的**自述**（`update()` 的返回值），而 fetch/tsm.py 维护两张表
（tsm.csv 与六页共享的 tsm_fx.csv），旧 return 是两者的并集：只有汇率推进时，
它照样返回 ['2026-08']，调用方无从分辨那个月份来自哪张表。

━━ 判据是不变式，不是夹具 ━━
夹具只能证明「代码与夹具自洽」（build/test_guards.py 开头那段吃过这个亏），
所以这里拿**本仓真实的每一个「更新数据」提交**去撞同一条不变式：

    标题里写着「T M」且 T 是 TICKERS 里的一家 ⇒ 那个提交里 series/T.csv 必须真的多出
    一行以 M 打头。

这条不变式对 a8f2211 是假的（旧逻辑），对新逻辑必须对每一个历史提交都为真。
它不管标题好不好看，只管标题有没有说仓库里不存在的事。

历史重放跑在 `git diff <h>^ <h>` 上而不是真去 checkout：staged_label 读的
`git diff --cached -U0 -- series` 与它同一种输出格式，而重放不动工作树，
可以在脏树上跑、也不会和别的 worktree 抢文件。
"""

import os
import re
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

import monthly_run as M                    # noqa: E402


def _git(*args):
    r = subprocess.run(['git'] + list(args), cwd=ROOT,
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError('git %s 失败: %s' % (' '.join(args), r.stderr[-300:]))
    return r.stdout.rstrip()


def _label_of(h):
    """把提交 h 的改动当成「已暂存」喂给 staged_label()，拿回它会写的标题。"""
    series_diff = _git('diff', '-U0', h + '^', h, '--', 'series')
    data_names = _git('diff', '--name-only', h + '^', h, '--', 'data')

    def fake_sh(cmd, cwd=None, check=True):
        # staged_label 只发两条命令，用末位路径区分即可
        return series_diff if cmd[-1] == 'series' else data_names

    real, M.sh = M.sh, fake_sh
    try:
        return M.staged_label()
    finally:
        M.sh = real


def _update_commits():
    out = _git('log', '--format=%H', '--grep=^更新数据')
    return out.splitlines() if out else []


# 标题里的一项：「<stem> <月>[,<月>...]」；「N 页重建」「<stem> +N 行」不带月份，不受这条约束
_ITEM = re.compile(r'^(\S+) (\d{4}-\d{2}(?:,\d{4}-\d{2})*)$')


class TestLabelNeverInventsAMonth(unittest.TestCase):
    """标题里的「T M」必须在 series/T.csv 里找得到对应的新增行。"""

    def test_every_update_commit(self):
        commits = _update_commits()
        self.assertTrue(commits, '仓库里一个「更新数据」提交都没有，这套重放测不到东西')
        for h in commits:
            label = _label_of(h)
            for item in label.split(', '):
                m = _ITEM.match(item)
                if not m:
                    continue
                stem, months = m.group(1), m.group(2).split(',')
                diff = _git('show', h, '--', 'series/%s.csv' % stem)
                for mo in months:
                    with self.subTest(commit=h[:7], stem=stem, month=mo):
                        self.assertRegex(
                            diff, r'(?m)^\+%s,' % re.escape(mo),
                            '%s 的标题写着「%s %s」，但那个提交里 series/%s.csv '
                            '没有以 %s 打头的新增行 —— 标题声称了真值源里不存在的月份'
                            % (h[:7], stem, mo, stem, mo))


class TestA8f2211Regression(unittest.TestCase):
    """把当初那一次原样重放：新逻辑绝不能再把汇率的月份记到 tsm 头上。"""

    BAD = 'a8f221191235bf9c2ba47e91b3e60e54a3c0521a'

    def setUp(self):
        try:
            _git('cat-file', '-e', self.BAD + '^{commit}')
        except RuntimeError:
            self.skipTest('本 clone 里没有 a8f2211（浅克隆或历史被改写）')

    def test_tsm_not_claimed(self):
        label = _label_of(self.BAD)
        self.assertNotRegex(
            label, r'(^|, )tsm \d{4}-\d{2}',
            '那一轮 series/tsm.csv 一行都没多（TSMC 的 xlsx 还停在 2026-07），'
            '标题里不该出现「tsm <月>」，实际拿到：%r' % label)
        # 该出现的是真正动了的那两张表
        self.assertIn('tsm_fx 2026-08', label)
        self.assertIn('umc 2026-08', label)


class TestSatelliteCollapse(unittest.TestCase):
    """卫星表并回本家的判据是「子集」，不是「前缀像」—— 前缀正是当初出事的地方。"""

    def _label(self, series_diff, data_names=''):
        def fake_sh(cmd, cwd=None, check=True):
            return series_diff if cmd[-1] == 'series' else data_names
        real, M.sh = M.sh, fake_sh
        try:
            return M.staged_label()
        finally:
            M.sh = real

    def test_parent_moved_absorbs_satellite(self):
        # tsm.csv 与 tsm_fx.csv 同时走到 2026-08 ⇒ 可以只说「tsm 2026-08」
        d = ('+++ b/series/tsm.csv\n+2026-08,480000,45.0\n'
             '+++ b/series/tsm_fx.csv\n+2026-08,32.0405\n')
        self.assertEqual(self._label(d), 'tsm 2026-08')

    def test_parent_still_absorbs_when_satellite_lags(self):
        # 卫星表的月份是本家的子集也照并（lseg_part_tradeweb 只补一个月的实况）
        d = ('+++ b/series/lseg.csv\n+2026-07,1\n+2026-08,2\n'
             '+++ b/series/lseg_part_tradeweb.csv\n+2026-08,3\n')
        self.assertEqual(self._label(d), 'lseg 2026-07,2026-08')

    def test_satellite_alone_never_borrows_parent_name(self):
        # a8f2211 的形状：本家没动，只有卫星表动了 ⇒ 绝不能说成「tsm 2026-08」
        d = '+++ b/series/tsm_fx.csv\n+2026-08,32.0405\n'
        self.assertEqual(self._label(d), 'tsm_fx 2026-08')

    def test_satellite_ahead_of_parent_stays_split(self):
        # 卫星表比本家多一个月 ⇒ 不是子集，两项分开列，谁都不替谁说话
        d = ('+++ b/series/tsm.csv\n+2026-08,480000,45.0\n'
             '+++ b/series/tsm_fx.csv\n+2026-08,32.0\n+2026-09,32.1\n')
        self.assertEqual(self._label(d), 'tsm 2026-08, tsm_fx 2026-08,2026-09')

    def test_shared_ledger_excluded(self):
        # source_dates.csv 是全仓共用台账，21 个提交里 11 个动了它，不进标题
        d = ('+++ b/series/cme.csv\n+2026-08,1\n'
             '+++ b/series/source_dates.csv\n+cme,2026-08,2026-09-03,"x"\n')
        self.assertEqual(self._label(d), 'cme 2026-08')

    def test_restatement_is_not_a_new_month(self):
        # 448325a 的形状：TSMC 把 2026-07 从 467581 改成 467580 —— 同一个月既在 - 又在 +，
        # 说成「tsm 2026-07」会被读成「7 月刚入库」
        d = ('+++ b/series/tsm.csv\n-2026-07,467581,44.7\n+2026-07,467580,44.7\n')
        self.assertEqual(self._label(d), 'tsm 2026-07 改数')

    def test_slow_leg_refill_is_not_a_restatement(self):
        # series/lseg.csv 2026-08 的形状：先落地半截行，慢腿到货把空格填满。
        # 那天没有任何一个数被改，说成「改数」同样是假话。
        d = ('+++ b/series/lseg.csv\n-2026-08,155.2,,,\n+2026-08,155.2,61.1,2797.2,1624.2\n')
        self.assertEqual(self._label(d), 'lseg 2026-08 回补')

    def test_refill_and_restatement_told_apart_in_one_file(self):
        d = ('+++ b/series/lseg.csv\n-2026-07,1,,\n+2026-07,1,2,3\n'
             '-2026-06,9,9,9\n+2026-06,8,9,9\n')
        self.assertEqual(self._label(d), 'lseg 2026-07 回补 · 2026-06 改数')

    def test_quoted_column_with_comma_not_missplit(self):
        # 裸 split(',') 会把带引号的证据串切成两列，进而把回补误判成改数
        d = ('+++ b/series/x.csv\n-2026-08,"a, b",\n+2026-08,"a, b",7\n')
        self.assertEqual(self._label(d), 'x 2026-08 回补')

    def test_new_month_and_restatement_split(self):
        d = ('+++ b/series/tsm.csv\n-2026-07,467581,44.7\n'
             '+2026-07,467580,44.7\n+2026-08,480000,45.0\n')
        self.assertEqual(self._label(d), 'tsm 2026-08 · 2026-07 改数')

    def test_no_series_change_falls_back_to_page_count(self):
        self.assertEqual(self._label('', 'data/a.js\ndata/b.js'), '2 页重建')


if __name__ == '__main__':
    unittest.main(verbosity=2)
