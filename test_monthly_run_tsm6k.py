# -*- coding: utf-8 -*-
"""monthly_run.tsm_6k() 与 monthly_run.audit_manual_series() 的离线测试 —— 只用标准库，不联网，不进 cron。

跑法: python3 test_monthly_run_tsm6k.py

━━ 守的是哪几件事 ━━
tsm_6k() 是 fetch/tsm_6k.py 的调用侧。它自己的判断全是「日期 × 状态」的组合，而每一种判错的样子都是安静：
  1. 日历预闸：两表末月追平候选月就一个请求都不打；没追平才调 update(upto=候选月)。
     开闸日与 tsm 营收腿同一格（LAG − EARLY = 月末后第 5 天）。
  2. 逾期黏警报：月末后第 LAG+GRACE+1 = 16 天起两表仍没到 → 'tsm_6k' 进失败清单，
     与 audit_overdue_headline()（= 首页红点）**同一天**开口 —— 早一天是假警报，晚一天是漏报。
  3. 补建戳四个分支：戳相符不建；戳缺失 / 不符就建并写戳（dry-run 不写）；建失败记失败、不写戳；
     本轮 tsm 已在按家循环里 FAIL 时推迟 —— 不建、不写、不另记。
     三个触发条件（新增月份 / 指纹前后有变 / 戳不符）各有一条只靠它自己才触发的用例。
     没有新月份而补建成功时紧跟一行 `tsm_6k REBUILT 补建 /tsm/（原因）`；有新月份、建失败、推迟时都不印。
  4. update() / last_month() 抛异常 → 'tsm_6k'，不建。
  5. 补建失败那行带 build/tsm.py 的 stderr 末行：走真 sh()，命令用生产环境那条 102 字的解释器 + 仓库路径
     （旧写法 str(e)[:100] 在这个长度下只剩命令路径）。stderr 为空时（原因只印在 stdout / 被信号杀掉）冒号后面
     不许空着，必须印兜底「stderr 为空；命令 build/tsm.py」。
  6. 清单外块主体（fetch/tsm_6k.py 口径坑 k）：update() 填了 DEGRADED → 记进 LEG_ALERTS['tsm_6k']（照常建页、返回值不变）；
     闸门关着时不读模块里残留的 DEGRADED。
audit_manual_series() 只打印：两条阈值各测差一天的边界；无陈旧项时 stdout 一个字都没有；自身出错只印 ⚠。
另有一条静态核对：main() 里两处调用的先后（与 cost_sec / mops_remarks、report_restatement_logs /
report_leg_alerts 的相对位置是跨支线定下的，挪了不会有任何别的测试变红）。

━━ 为什么不依赖真 fetch/tsm_6k.py ━━
这里测的是调用侧的判断，不是解析器（解析器归 fetch/test_tsm_6k.py）。M.HERE 指到临时目录，
里面只放一个空的 fetch/tsm_6k.py 占位，让「文件在不在」那一句过去；M.load 返回桩模块，
M.sh / M.builder / M.due_lag 一律替换 —— 不联网、不跑生成器、不碰仓库的 series/ 与 cache/。
LAG / EARLY / GRACE 钉成 tsm 现值 (10, 10) / 5 / 5（EARLY_BY 里剔掉 tsm），边界日期因此是写死的真日子。
"""

import contextlib
import datetime
import inspect
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

import monthly_run as M                    # noqa: E402

REAL_SH = M.sh                             # 夹具把 M.sh 换成记账桩；「FAIL 行带 stderr」那条要走真 sh()
D = datetime.date
LAG, EARLY, GRACE = (10, 10), 5, 5
CMD = ['python3', 'build/tsm.py']
STAMP_REL = os.path.join('tsm_6k', '_last_built.sha256')
# 生产环境实测的 builder('tsm')：调度跑 `python3 monthly_run.py`，sys.executable 解析到 py312 那一份。
# 拼起来恰好 102 字 —— 旧写法 str(e)[:100] 在这个长度下只印得出命令路径，一个字的原因都没有。
PROD_CMD = ['/Users/hainan/.local/share/py312/bin/python3',
            '/Users/hainan/Projects/monthly-op-dashboards/build/tsm.py']


def _quiet(fn, *a, **kw):
    """跑 fn，返回 (返回值, stdout 全文)。"""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        got = fn(*a, **kw)
    return got, buf.getvalue()


class _Tsm6kCase(unittest.TestCase):
    """公共夹具：临时 HERE / SERIES / CACHE，桩模块，记账的 sh。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='tsm6k_mr_')
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.here = os.path.join(self.tmp, 'repo')
        os.makedirs(os.path.join(self.here, 'fetch'))
        self.placeholder = os.path.join(self.here, 'fetch', 'tsm_6k.py')
        open(self.placeholder, 'w').close()
        self.series = os.path.join(self.tmp, 'series')
        self.cache = os.path.join(self.tmp, 'cache')          # 刻意不建 cache/tsm_6k：写戳前必须自己 makedirs
        os.makedirs(self.series)
        self.stamp = os.path.join(self.cache, STAMP_REL)
        self.sh_calls, self.sh_exc = [], None
        self.odd_loads = []
        self.stub = None
        patches = [
            mock.patch.object(M, 'HERE', self.here),
            mock.patch.object(M, 'SERIES', self.series),
            mock.patch.object(M, 'CACHE', self.cache),
            mock.patch.object(M, 'EARLY', EARLY),
            mock.patch.dict(M.EARLY_BY, {k: v for k, v in M.EARLY_BY.items() if k != 'tsm'}, clear=True),
            mock.patch.object(M, 'load', self._load),
            mock.patch.object(M, 'sh', self._sh),
            mock.patch.object(M, 'builder', lambda t: list(CMD) if t == 'tsm' else None),
            mock.patch.object(M, 'due_lag', lambda t: LAG if t == 'tsm' else None),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    # ── 桩 ──
    def make_stub(self, have, fp='fp-old', added=(), update_exc=None, last_exc=None, new_fp='fp-new', degraded=None):
        """两表状态只用「末月 + 指纹」两个值表示；update() 返回非空时推进末月并把指纹换成 new_fp。

        new_fp=fp 模拟「指纹没跟着内容变」（fingerprint() 被改坏，例如只哈希文件名）——
        那时能把新月份送上页的只剩 `added` 这一条触发条件。
        """
        state = {'have': have, 'fp': fp}
        calls = []
        degraded_now = {}                  # 模块级 DEGRADED：update() 开头清空、再填本轮的（degraded）

        def last_month(series_dir):
            if last_exc:
                raise last_exc
            return state['have']

        def fingerprint(series_dir):
            return state['fp']

        def update(series_dir, cache_dir, upto, today=None, opener=None):
            calls.append({'series_dir': series_dir, 'cache_dir': cache_dir, 'upto': upto, 'today': today})
            degraded_now.clear()
            degraded_now.update(degraded or {})
            if update_exc:
                raise update_exc
            if added:
                state['have'], state['fp'] = max(added), new_fp
            return list(added)

        self.stub = types.SimpleNamespace(last_month=last_month, fingerprint=fingerprint, update=update,
                                          CACHE_SUB='tsm_6k', STAMP_NAME='_last_built.sha256', DEGRADED=degraded_now,
                                          calls=calls, state=state)
        return self.stub

    def _load(self, path, name):
        if os.path.abspath(path) == os.path.abspath(self.placeholder):
            return self.stub
        if path.endswith(os.path.join('build', 'roster.py')):
            return types.SimpleNamespace(GRACE=GRACE, LAG={'tsm': LAG})
        self.odd_loads.append(path)                            # 断言留到测试里做：这里抛会被 tsm_6k 吞成 FAIL
        raise RuntimeError(f'意外的 load: {path}')

    def _sh(self, cmd, cwd=None, check=True):
        self.sh_calls.append(list(cmd))
        if self.sh_exc:
            raise self.sh_exc
        return ''

    # ── 小工具 ──
    def run6k(self, today, **kw):
        return _quiet(M.tsm_6k, today=today, **kw)

    def write_stamp(self, text):
        os.makedirs(os.path.dirname(self.stamp), exist_ok=True)
        with open(self.stamp, 'w', encoding='utf-8') as f:
            f.write(text + '\n')

    def read_stamp(self):
        if not os.path.exists(self.stamp):
            return None
        with open(self.stamp, encoding='utf-8') as f:
            return f.read().strip()

    def tearDown(self):
        self.assertEqual(self.odd_loads, [], 'tsm_6k() load 了预期之外的文件')


class TestGate(_Tsm6kCase):
    """日历预闸：追平就零请求；开闸日 = 月末后第 LAG − EARLY 天。"""

    def test_caught_up_and_stamp_matches_makes_zero_requests(self):
        self.make_stub('2026-08')
        self.write_stamp('fp-old')
        got, out = self.run6k(D(2026, 9, 20))
        self.assertEqual(got, [])
        self.assertEqual(self.stub.calls, [], '两表已到 2026-08，不该调 update()')
        self.assertEqual(self.sh_calls, [])
        self.assertRegex(out, r'(?m)^tsm_6k\s+NOCHANGE 已追平候选月 2026-08（零请求）$')
        self.assertNotIn('FAIL', out)

    def test_gate_opens_on_day_5_not_day_4(self):
        self.make_stub('2026-08')
        self.write_stamp('fp-old')
        got, out = self.run6k(D(2026, 10, 4))
        self.assertEqual((got, self.stub.calls), ([], []), '10-04 是月末后第 4 天，闸门还不该开')
        self.assertIn('已追平候选月 2026-08（零请求）', out)
        got, out = self.run6k(D(2026, 10, 5))
        self.assertEqual(got, [])
        self.assertEqual(self.stub.calls, [{'series_dir': self.series, 'cache_dir': self.cache,
                                            'upto': '2026-09', 'today': D(2026, 10, 5)}])
        self.assertRegex(out, r'(?m)^tsm_6k\s+NOCHANGE 源上 2026-09 的月报 6-K 尚未入库（逾期线：月末后第 16 天）$')
        self.assertEqual(self.sh_calls, [])

    def test_new_month_rebuilds_and_stamps_even_if_old_stamp_matched(self):
        # 戳预先写成追加**之后**的指纹 fp-new：跑完 stamped == cur，「戳不符」这一条触发不了。
        # 原先写 fp-old 时戳不符本身就会触发重建，把条件砍成 (stamped != cur) 这条照样绿（复核 R04）。
        # 真实形状：页面建成并记下 F(08) 之后，那个数据提交被整体 git revert（series 与 data 都回到 07），
        # cache 里的戳还是 F(08)；下一轮 update() 追加出逐字节相同的行，指纹又等于戳。
        self.make_stub('2026-07', added=('2026-08',))
        self.write_stamp('fp-new')
        got, out = self.run6k(D(2026, 9, 14))
        self.assertEqual(got, [])
        self.assertEqual([c['upto'] for c in self.stub.calls], ['2026-08'])
        self.assertEqual(self.stub.calls[0]['today'], D(2026, 9, 14))
        self.assertEqual(self.sh_calls, [CMD])
        self.assertEqual(self.read_stamp(), 'fp-new', '建成之后戳必须是追加后的指纹')
        self.assertRegex(out, r'(?m)^tsm_6k\s+NEW\s+2026-08$')
        self.assertNotIn('REBUILT', out, '有新月份时状态行已是 NEW，不该再补一行 REBUILT')

    def test_update_raises_counts_and_does_not_build(self):
        self.make_stub('2026-07', update_exc=RuntimeError('SEC 封禁页'))
        got, out = self.run6k(D(2026, 9, 14))
        self.assertEqual(got, ['tsm_6k'])
        self.assertEqual(self.sh_calls, [])
        self.assertIsNone(self.read_stamp())
        self.assertRegex(out, r'(?m)^tsm_6k\s+FAIL\s+RuntimeError: SEC 封禁页')

    def test_last_month_raises_counts_and_does_not_call_update(self):
        self.make_stub('2026-07', last_exc=ValueError('表头不对'))
        got, out = self.run6k(D(2026, 9, 14))
        self.assertEqual(got, ['tsm_6k'])
        self.assertEqual((self.stub.calls, self.sh_calls), ([], []))
        self.assertRegex(out, r'(?m)^tsm_6k\s+FAIL\s+ValueError: 表头不对')

    def test_module_deleted_is_silent(self):
        # §4「删掉 /tsm/ 的 6-K 腿」：只删模块是安全的 —— 第一句就返回空清单，一个字不印
        self.make_stub('2026-07')
        os.remove(self.placeholder)
        got, out = self.run6k(D(2026, 9, 16))
        self.assertEqual((got, out), ([], ''))
        self.assertEqual((self.stub.calls, self.sh_calls), ([], []))


class TestOverdueBoundary(_Tsm6kCase):
    """逾期线 = 月末后第 LAG+GRACE+1 = 16 天，与首页红点同日开口。"""

    def test_day_15_quiet_day_16_sticky(self):
        self.make_stub('2026-07')                              # 源上 8 月一直没出现
        self.write_stamp('fp-old')
        got, out = self.run6k(D(2026, 9, 15))
        self.assertEqual(got, [])
        self.assertRegex(out, r'(?m)^tsm_6k\s+NOCHANGE 源上 2026-08 的月报 6-K 尚未入库')
        self.assertNotIn('FAIL', out)
        got, out = self.run6k(D(2026, 9, 16))
        self.assertEqual(got, ['tsm_6k'])
        self.assertRegex(out, r'(?m)^tsm_6k\s+FAIL\s+逾期：两表止于 2026-07，.*本该已有 2026-08$')
        self.assertEqual(self.sh_calls, [])

    def test_same_day_as_headline_red_dot(self):
        # 同一份 LAG / GRACE 喂给 audit_overdue_headline()：它也必须恰好在 09-16 开口
        data = os.path.join(self.tmp, 'data')
        os.makedirs(data)
        with open(os.path.join(data, 'tsm.js'), 'w', encoding='utf-8') as f:
            f.write('window.DASH = ' + json.dumps({'data_through': '2026-07'}) + ';\n')
        with mock.patch.object(M, 'DATA', data), mock.patch.dict(M._LAG_CACHE, {}, clear=True):
            self.assertEqual(_quiet(M.audit_overdue_headline, today=D(2026, 9, 15))[0], [])
            self.assertEqual(_quiet(M.audit_overdue_headline, today=D(2026, 9, 16))[0], ['tsm'])
        self.make_stub('2026-07')
        self.write_stamp('fp-old')
        self.assertEqual(self.run6k(D(2026, 9, 15))[0], [])
        self.assertEqual(self.run6k(D(2026, 9, 16))[0], ['tsm_6k'])

    def test_rebuild_failure_and_overdue_counted_once(self):
        self.make_stub('2026-07')
        self.sh_exc = RuntimeError('brief 超长')
        got, out = self.run6k(D(2026, 9, 16))
        self.assertEqual(got, ['tsm_6k'], '同一步两种失败只记一次，末行的家数才不虚胖')
        self.assertIn('重建失败', out)
        self.assertIn('逾期', out)


class TestRebuildStamp(_Tsm6kCase):
    """补建戳：CSV 写成了而页面没建成时，下一轮必须自己补上。"""

    def test_stamp_missing_rebuilds_and_writes(self):
        self.make_stub('2026-08')
        got, out = self.run6k(D(2026, 9, 20))
        self.assertEqual(got, [])
        self.assertEqual(self.stub.calls, [])
        self.assertEqual(self.sh_calls, [CMD])
        self.assertEqual(self.read_stamp(), 'fp-old')
        # 状态行是 NOCHANGE（零请求），补建必须紧跟着另起一行说出来 —— 否则 data/tsm.js 变了、进了提交，
        # 日志里却只有一句「已追平」
        self.assertRegex(out, r'(?m)^tsm_6k\s+NOCHANGE 已追平候选月 2026-08（零请求）\n'
                              r'tsm_6k\s+REBUILT\s+补建 /tsm/（补建戳缺失或读不出）$')

    def test_stamp_with_other_content_rebuilds(self):
        self.make_stub('2026-08')
        self.write_stamp('fp-from-some-earlier-build')
        _, out = self.run6k(D(2026, 9, 20))
        self.assertEqual(self.sh_calls, [CMD])
        self.assertEqual(self.read_stamp(), 'fp-old')
        self.assertRegex(out, r'(?m)^tsm_6k\s+REBUILT\s+补建 /tsm/（补建戳不符）$')

    def test_fingerprint_changed_without_new_month_says_so(self):
        # update() 没报新月份、两表内容却变了：照样补建，REBUILT 行说清是这个原因。
        # 戳预先写成变化**之后**的指纹：added 为空、stamped == cur，只剩「指纹前后有变」这一条能触发。
        stub = self.make_stub('2026-07')
        self.write_stamp('fp-rewritten')

        def update(series_dir, cache_dir, upto, today=None, opener=None):
            stub.calls.append({'upto': upto})
            stub.state['fp'] = 'fp-rewritten'
            return []

        stub.update = update
        got, out = self.run6k(D(2026, 9, 14))
        self.assertEqual(got, [])
        self.assertEqual(self.sh_calls, [CMD])
        self.assertEqual(self.read_stamp(), 'fp-rewritten')
        self.assertRegex(out, r'(?m)^tsm_6k\s+REBUILT\s+补建 /tsm/（两表内容有变但无新增月份）$')

    def test_added_alone_triggers_rebuild(self):
        # 指纹没跟着内容变（fingerprint() 被改坏）且戳与之相符：「指纹前后有变」「戳不符」都触发不了，
        # 新月份能上页全靠 `added` —— 把它从触发条件里删掉，这条变红。
        self.make_stub('2026-07', added=('2026-08',), new_fp='fp-old')
        self.write_stamp('fp-old')
        got, out = self.run6k(D(2026, 9, 14))
        self.assertEqual(got, [])
        self.assertEqual(self.sh_calls, [CMD])
        self.assertRegex(out, r'(?m)^tsm_6k\s+NEW\s+2026-08$')
        self.assertNotIn('REBUILT', out)

    def test_dry_run_rebuilds_but_never_stamps(self):
        self.make_stub('2026-08')
        got, out = self.run6k(D(2026, 9, 20), dry_run=True)
        self.assertEqual(got, [])
        self.assertEqual(self.sh_calls, [CMD])
        self.assertIsNone(self.read_stamp())
        self.assertRegex(out, r'(?m)^tsm_6k\s+REBUILT\s+补建 /tsm/')         # 试跑也真建了，照样要说

    def test_rebuild_failure_counts_and_leaves_stamp_alone(self):
        self.make_stub('2026-08')
        self.sh_exc = RuntimeError('build/tsm.py 失败: boom')
        got, out = self.run6k(D(2026, 9, 20))
        self.assertEqual(got, ['tsm_6k'])
        self.assertIsNone(self.read_stamp())
        self.assertRegex(out, r'(?m)^tsm\s+FAIL\s+月报 6-K 腿更新后重建失败（补建戳未更新，下一轮重试）: boom$')
        self.assertNotIn('REBUILT', out, '建失败时不许印补建成功的那一行')

    def test_rebuild_failure_line_carries_stderr_last_line(self):
        # 走真 sh()：subprocess.run 换成返回码 1 + 一段真实形状的 traceback，builder 给生产环境那条 102 字的命令。
        # 旧写法 str(e)[:100] 在这里只印得出 '…/build/tsm.'，一个字的原因都没有。
        last = ("ValueError: 背書保證在外余额在 2011-07 之后出现空月：['2025-01'] —— "
                'gs_line 会把缺口静默接成一条直线，请先补数或把 _GUAR_FROM 往后挪，不要让它自己猜')
        stderr = ('Traceback (most recent call last):\n'
                  '  File "/Users/hainan/Projects/monthly-op-dashboards/build/tsm.py", line 43, in <module>\n'
                  '    sys.exit(main())\n'
                  '             ^^^^^^\n'
                  '  File "/Users/hainan/Projects/monthly-op-dashboards/build/mrspecs/_tsm_extra.py", '
                  'line 145, in _load\n'
                  '    raise ValueError(\n'
                  + last + '\n')
        runs = []

        def fake_run(cmd, cwd=None, capture_output=False, text=False, **kw):
            runs.append(list(cmd))
            return subprocess.CompletedProcess(cmd, 1, stdout='', stderr=stderr)

        self.assertGreaterEqual(len(' '.join(PROD_CMD)), 100, '这条测试的前提：命令本身就比旧截断长')
        self.make_stub('2026-08')
        with mock.patch.object(M, 'sh', REAL_SH), \
                mock.patch.object(M, 'builder', lambda t: list(PROD_CMD) if t == 'tsm' else None), \
                mock.patch.object(M.subprocess, 'run', fake_run):
            got, out = self.run6k(D(2026, 9, 20))
        self.assertEqual(got, ['tsm_6k'])
        self.assertEqual(runs, [PROD_CMD])
        self.assertIsNone(self.read_stamp())
        fail = [ln for ln in out.splitlines() if re.match(r'tsm\s+FAIL\s', ln)]
        self.assertEqual(len(fail), 1, out)                      # traceback 折成了一行
        self.assertTrue(fail[0].endswith(last), fail[0])         # stderr 末行（异常类型 + 消息）完整落在行尾
        self.assertNotIn(PROD_CMD[0], fail[0])                   # 不再印命令路径
        self.assertNotIn('^^^', fail[0])                         # traceback 的纯标记行丢掉了

    def test_rebuild_failure_with_empty_stderr_names_the_command(self):
        # 走真 sh()：子进程把原因印到 stdout 再 exit 1，或被信号杀掉（returncode < 0），stderr 都是空的。
        # 只切 stderr 时 FAIL 行停在「…下一轮重试）: 」，冒号后面什么都没有；兜底必须说出 stderr 为空、是哪条命令。
        # 命令取生产形状（解释器 + 仓库内绝对路径），仓库根就是 M.HERE：印出来应只剩 build/tsm.py。
        cmd = [PROD_CMD[0], os.path.join(self.here, 'build', 'tsm.py')]
        for rc, stdout in ((1, '[tsm] 失败：原因只印在 stdout\n'), (-9, '')):
            with self.subTest(returncode=rc):
                runs = []

                def fake_run(c, cwd=None, capture_output=False, text=False, **kw):
                    runs.append(list(c))
                    return subprocess.CompletedProcess(c, rc, stdout=stdout, stderr='')

                self.make_stub('2026-08')
                with mock.patch.object(M, 'sh', REAL_SH), \
                        mock.patch.object(M, 'builder', lambda t: list(cmd) if t == 'tsm' else None), \
                        mock.patch.object(M.subprocess, 'run', fake_run):
                    got, out = self.run6k(D(2026, 9, 20))
                self.assertEqual(got, ['tsm_6k'])
                self.assertEqual(runs, [cmd])
                self.assertIsNone(self.read_stamp())
                fail = [ln for ln in out.splitlines() if re.match(r'tsm\s+FAIL\s', ln)]
                self.assertEqual(len(fail), 1, out)
                self.assertTrue(fail[0].endswith('（补建戳未更新，下一轮重试）: stderr 为空；命令 build/tsm.py'), fail[0])
                self.assertNotIn(PROD_CMD[0], fail[0])
        # 不是 sh() 抛的、消息又为空：不许谎称「stderr 为空」，印异常类型；冒号后面同样不空
        self.make_stub('2026-08')
        self.sh_exc = RuntimeError()
        got, out = self.run6k(D(2026, 9, 20))
        self.assertEqual(got, ['tsm_6k'])
        self.assertRegex(out, r'(?m)^tsm\s+FAIL\s+.*下一轮重试）: RuntimeError（无消息）；命令 build/tsm\.py$')

    def test_loop_failed_defers_without_building_or_counting(self):
        self.make_stub('2026-08')
        got, out = self.run6k(D(2026, 9, 20), loop_failed=True)
        self.assertEqual(got, [])
        self.assertEqual(self.sh_calls, [])
        self.assertIsNone(self.read_stamp())
        self.assertIn('补建推迟到下一轮', out)
        self.assertNotIn('REBUILT', out)

    def test_deferred_new_month_is_rebuilt_next_round(self):
        # 09-14：6-K 到了、两表写成，但 tsm 本轮在循环里 FAIL → 推迟；09-15：闸门已关、update 不再被调，
        # 只有戳不符这一条还能把页面补上
        self.make_stub('2026-07', added=('2026-08',))
        self.write_stamp('fp-old')
        got, _ = self.run6k(D(2026, 9, 14), loop_failed=True)
        self.assertEqual((got, self.sh_calls, self.read_stamp()), ([], [], 'fp-old'))
        got, out = self.run6k(D(2026, 9, 15))
        self.assertEqual(got, [])
        self.assertEqual(len(self.stub.calls), 1, '09-15 两表已到 2026-08，不该再调 update()')
        self.assertEqual(self.sh_calls, [CMD])
        self.assertEqual(self.read_stamp(), 'fp-new')
        self.assertIn('零请求', out)
        self.assertRegex(out, r'(?m)^tsm_6k\s+REBUILT\s+补建 /tsm/（补建戳不符）$')

    def test_page_deleted_skips_rebuild(self):
        self.make_stub('2026-08')
        with mock.patch.object(M, 'builder', lambda t: None):
            got, _ = self.run6k(D(2026, 9, 20))
        self.assertEqual((got, self.sh_calls), ([], []))


class TestAuditManualSeries(unittest.TestCase):
    """人工表陈旧提示：只打印；两条阈值各差一天；无陈旧项时一个字不印。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='tsm6k_manual_')
        self.addCleanup(shutil.rmtree, self.tmp, True)
        p = mock.patch.object(M, 'SERIES', self.tmp)
        p.start()
        self.addCleanup(p.stop)

    def _write(self, name, text):
        with open(os.path.join(self.tmp, name), 'w', encoding='utf-8', newline='') as f:
            f.write(text)

    def bonds(self, last):
        self._write('tsm_bonds_monthly.csv',
                    'month,issued_twd_k,repaid_twd_k,outstanding_twd_k,n_tranches_outstanding,wavg_coupon_pct\n'
                    f'2026-06,0,6900000,491000000,79,1.2667\n{last},18500000,4350000,505150000,80,1.2983\n')

    def capex(self, *filed):
        rows = ''.join(f'{d[:7]},1000.0,{d},0001046179-26-{i:06d}\n' for i, d in enumerate(filed))
        self._write('tsm_capex_approvals.csv', 'month,approved_usd_mn,filed,accession\n' + rows)

    def audit(self, today):
        got, out = _quiet(M.audit_manual_series, today=today)
        self.assertIsNone(got)
        return out

    def test_bonds_32nd_day(self):
        self.bonds('2026-07')
        self.capex('2026-05-12', '2026-08-11')
        self.assertEqual(self.audit(D(2026, 10, 1)), '')
        out = self.audit(D(2026, 10, 2))
        self.assertEqual(len(out.splitlines()), 1, out)
        self.assertTrue(out.startswith('  ⚠ 人工表陈旧 series/tsm_bonds_monthly.csv 止于 2026-07，'), out)
        self.assertIn('本该已有 2026-08', out)
        self.assertIn('—— 补录 series/tsm_bonds_tranches.csv 后跑 python3 fetch/tsm.py bonds --write', out)

    def test_capex_136th_day(self):
        self.bonds('2026-11')                                  # 让公司債那条在 12 月底保持安静
        self.capex('2026-05-12', '2026-08-11')
        self.assertEqual(self.audit(D(2026, 12, 24)), '')      # 距 08-11 恰 135 天：不超过
        out = self.audit(D(2026, 12, 25))
        self.assertEqual(len(out.splitlines()), 1, out)
        self.assertTrue(out.startswith('  ⚠ 人工表陈旧 series/tsm_capex_approvals.csv 止于 filed 2026-08-11，'), out)
        self.assertIn('136 天', out)

    def test_silent_when_nothing_is_stale(self):
        self.bonds('2026-08')
        self.capex('2026-08-11')
        self.assertEqual(self.audit(D(2026, 9, 14)), '')

    def test_missing_tables_are_silent(self):
        # 整页 /tsm/ 被删时不留残渣：表不在就跳过，不报错
        self.assertEqual(self.audit(D(2027, 6, 1)), '')

    def test_own_error_only_warns(self):
        self.bonds('2026-08')
        self._write('tsm_capex_approvals.csv', 'month,approved_usd_mn,accession\n2026-08,1.0,x\n')  # 没有 filed 列
        out = self.audit(D(2026, 9, 14))
        self.assertIn('⚠', out)
        self.assertIn('自身出错', out)

    def test_registry_shape(self):
        for entry in M.MANUAL_SERIES:
            with self.subTest(entry=entry[0]):
                self.assertEqual(len(entry), 5)
                name, col, rule, why, fix = entry
                self.assertTrue(name.endswith('.csv'))
                self.assertTrue(isinstance(rule, int) or (isinstance(rule, tuple) and len(rule) == 2))


class TestUnlistedBlockAlert(_Tsm6kCase):
    """清单外块主体（fetch/tsm_6k.py 口径坑 k）：照常写入、照常建页，但进 LEG_ALERTS → 末行（2026-09-14 所有者定）。"""

    ALERT = {'2026-08 清单外块主体': "(2) 节 'Fixture Wafer Co.' Forward 名目 1,000 —— 按子公司不计入、照常写入"}

    def setUp(self):
        super().setUp()
        p = mock.patch.dict(M.LEG_ALERTS, {}, clear=True)
        p.start()
        self.addCleanup(p.stop)

    def test_flagged_update_goes_to_leg_alerts(self):
        self.make_stub('2026-07', added=('2026-08',), degraded=self.ALERT)
        got, out = self.run6k(D(2026, 9, 14))
        self.assertEqual(got, [], '返回值不变：不算本步失败（并入末行在 main() 里做）')
        self.assertEqual(M.LEG_ALERTS, {'tsm_6k': self.ALERT})
        self.assertEqual(self.sh_calls, [CMD], '照常建页')
        self.assertRegex(out, r'(?m)^tsm_6k\s+NEW\s+2026-08\n\s+⚠ 腿级报警：2026-08 清单外块主体（明细见文末「腿级降级/报警」）$')

    def test_clean_update_no_alert(self):
        self.make_stub('2026-07', added=('2026-08',))
        _, out = self.run6k(D(2026, 9, 14))
        self.assertEqual(M.LEG_ALERTS, {})
        self.assertNotIn('腿级报警', out)

    def test_gate_closed_ignores_stale_degraded(self):
        stub = self.make_stub('2026-08')
        stub.DEGRADED['2026-07 清单外块主体'] = '上一轮残留'
        self.write_stamp('fp-old')
        _, out = self.run6k(D(2026, 9, 20))
        self.assertEqual(stub.calls, [])
        self.assertEqual(M.LEG_ALERTS, {})
        self.assertNotIn('腿级报警', out)


class TestMainWiring(unittest.TestCase):
    """main() 里两处调用的位置是跨支线定下的（docs/CRON_WIRING.md §1），挪了不会有别的测试变红。"""

    def test_call_order(self):
        # 按「整行就是这条语句」定位：注释里也会提到这些函数名（如 LEG_ALERTS 那段写着 report_leg_alerts()），
        # 用子串 find 会先撞上注释
        lines = [ln.strip() for ln in inspect.getsource(M.main).splitlines()]

        def at(s):
            self.assertIn(s, lines, f'main() 里找不到独占一行的 {s!r}')
            return lines.index(s)

        call = "fails += tsm_6k(a.dry_run, loop_failed='tsm' in fails)"
        self.assertLess(at('fails += cost_sec()'), at("if 'tsm' in todo:"))
        self.assertLess(at("if 'tsm' in todo:"), at(call))
        self.assertLess(at(call), at('fails += mops_remarks()'))
        self.assertLess(at(call), at('fails += [t for t in LEG_ALERTS if t not in fails]'))   # 清单外块主体报警要赶得上并入末行
        self.assertLess(at('report_restatement_logs(t_run)'), at('audit_manual_series()'))
        self.assertLess(at('audit_manual_series()'), at('report_leg_alerts()'))
        self.assertLess(at('report_leg_alerts()'), at('if gate_fail:'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
