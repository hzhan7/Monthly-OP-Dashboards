# -*- coding: utf-8 -*-
"""fetch/cost_sec.py 的 XBRL instance 定位测试 —— 全部离线，只用标准库。

跑法: python3 fetch/test_cost_sec.py

━━ 这套测试守的是哪一件事 ━━
`_instance()` 要在一篇 SEC 申报里找出 XBRL instance。它有四条路，前两条是原有的：

  1. 2019-12 起的 inline XBRL —— SEC 额外生成 `<primaryDocument 去 .htm>_htm.xml`；
  2. 更早的独立 instance —— 靠 `index.json` 挑（排除 _cal/_def/_lab/_pre、
     排除 FilingSummary.xml，再要求开头 4KB 里出现 `xbrl`）；
  3. **`index.json` 漏列时** —— 改读人读版索引 `<accession>-index.htm`，认 Type 格
     恰好是 `EX-101.INS` 的那一行（与本模块 `_ex992_url()` 认 `EX-99.2` 同一个成语）；
  4. 兜底 —— `<accession>-xbrl.zip`，与人读版索引是两条独立的索引。

第 3 条是 2026-09-05 补的。**坏的不是申报，是那份 JSON 清单**：
实测 0000909832-17-000022（10-Q@2017-12-21）的 `index.json` 只有 583 字节、4 项，
全是包装文件；而同一个目录的 HTML 清单有 **73 个文件**，`cost-20171126.xml` 好端端挂着，
直接 GET 也是 HTTP 200、863,287 字节。在册 62 篇 10-K/10-Q 里只有这一篇如此 ——
所以这是「一篇的索引坏了」，不是「2017 那一代版式不支持」。

这不是新发现：本仓一个月前就为另一个发行人写下过同一条结论，
见 fetch/rates_lpla.py:206-214（四份 LPLA 的 8-K，「文档在，只是 index.json 这条索引
看不见它」），处方也是那里给的 —— 「改从 `<acc>-index.html` 取文件名」（:284）。

代价不是「少一篇」而是**整个 cost_sec 步 FAIL**：
    [seg] 解析失败：10-Q@2017-12-21 0000909832-17-000022 找不到 XBRL instance；
    [tkt] 跳过：表 1（分部收入）没解        ← [tkt] 是 [seg] 的连带，不是第二个缺陷

━━ 另一半：报错要说清是哪条路怎么断的 ━━
`_fetch` 把超时 / 403 / 5xx 全包成 CostSecError。四条路要是都拿 `except` 一吞，
「SEC 限速取不到」与「这篇真的没有 instance」就长得一模一样 —— README「第四类：
不出声的失败」的判据句正是「它连续失败十天，和成功十天，在日志里长得一样吗？」。
所以 TestFailuresNameTheirCause 钉的是「原因必须带进最后那句 raise」。

━━ 夹具是编的，测的是「挑哪一个」不是「Costco 2017 年赚了多少」━━
instance 是几十字节的假 XML，只保证开头带不带 `xbrl` 这一个特征；索引页与 zip 当场造。
EX-101.* 那六行的 cells 逐格照抄自实测的 -index.htm。
"""

import io
import json
import os
import shutil
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cost_sec        # noqa: E402


ACC = '0000909832-17-000022'
ACCN = ACC.replace('-', '')
FILING = {'form': '10-Q', 'filed': '2017-12-21', 'accession': ACC, 'primary': 'cost10q.htm'}

INSTANCE = b'<?xml version="1.0"?>\n<!--XBRL Document-->\n<xbrli:xbrl>real</xbrli:xbrl>'
LINKBASE = b'<?xml version="1.0"?>\n<linkbase>labels only, no instance marker</linkbase>'


def _index(names):
    return json.dumps({'directory': {'item': [{'name': n} for n in names]}}).encode()


def _zip(members):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        for n, b in members.items():
            z.writestr(n, b)
    return buf.getvalue()


class _Served:
    """把 _fetch 换成夹具路由：{url 尾巴: bytes}。命中不了就抛 CostSecError（同真实行为）。

    仍然照真实 _fetch 把字节写进 cache_dir —— `_instance` 在候选落选时会 os.remove
    那个缓存文件，不写就会 FileNotFoundError，那是夹具的错不是被测代码的错。
    """

    def __init__(self, table):
        self.table = table
        self.asked = []

    def __enter__(self):
        self.tmp = tempfile.mkdtemp()
        self.orig = cost_sec._fetch

        def fake(cache_dir, name, url):
            self.asked.append(url)
            for tail, body in self.table.items():
                if url.endswith(tail):
                    d = os.path.join(cache_dir, 'cost_sec')
                    os.makedirs(d, exist_ok=True)
                    with open(os.path.join(d, name), 'wb') as f:
                        f.write(body)
                    return body
            raise cost_sec.CostSecError(f'SEC 取不到 {url}: HTTPError: 404')

        cost_sec._fetch = fake
        return self

    def __exit__(self, *exc):
        cost_sec._fetch = self.orig
        shutil.rmtree(self.tmp, ignore_errors=True)
        return False

    def run(self):
        return cost_sec._instance(self.tmp, FILING)


class TestShapeOne(unittest.TestCase):
    """2019-12 起：inline XBRL 的 _htm.xml 直接命中，且**必须最先试**。"""

    def test_inline_htm_xml_wins(self):
        with _Served({'cost10q_htm.xml': INSTANCE,
                      'index.json': _index(['other.xml'])}) as s:
            self.assertEqual(s.run(), INSTANCE)
        self.assertTrue(s.asked[0].endswith('cost10q_htm.xml'),
                        f'第一次请求应该是 _htm.xml，实际 {s.asked[0]}')
        self.assertNotIn('index.json', ' '.join(s.asked),
                         '命中 inline 之后不该再去读 index.json')


class TestShapeTwo(unittest.TestCase):
    """更早的独立 instance：靠 index.json 挑。"""

    def test_picks_the_loose_instance(self):
        with _Served({'index.json': _index(['cost-20171126.xml']),
                      'cost-20171126.xml': INSTANCE}) as s:
            self.assertEqual(s.run(), INSTANCE)

    def test_skips_linkbases_and_filing_summary(self):
        names = ['FilingSummary.xml', 'cost-20171126_cal.xml', 'cost-20171126_lab.xml',
                 'cost-20171126_pre.xml', 'cost-20171126_def.xml', 'cost-20171126.xml']
        table = {'index.json': _index(names), 'cost-20171126.xml': INSTANCE}
        with _Served(table) as s:
            self.assertEqual(s.run(), INSTANCE)
        for bad in ('_cal.xml', '_lab.xml', '_pre.xml', '_def.xml', 'FilingSummary.xml'):
            self.assertNotIn(bad, ' '.join(s.asked), f'不该去下 {bad}')

    def test_xml_without_the_xbrl_marker_is_rejected(self):
        # 目录里还躺着 R*.htm 的兄弟 xml；只有开头 4KB 带 'xbrl' 的才算数。
        with _Served({'index.json': _index(['decoy.xml', 'cost-20171126.xml']),
                      'decoy.xml': LINKBASE, 'cost-20171126.xml': INSTANCE}) as s:
            self.assertEqual(s.run(), INSTANCE)


def _index_htm(rows):
    """人读版申报索引页的最小骨架。rows = [(seq, desc, filename, type, size)]。"""
    trs = ''.join(
        '<tr>'
        f'<td>{seq}</td><td>{desc}</td>'
        f'<td><a href="/Archives/edgar/data/909832/{ACCN}/{fn}">{fn}</a></td>'
        f'<td>{typ}</td><td>{size}</td>'
        '</tr>'
        for seq, desc, fn, typ, size in rows)
    return f'<html><body><table class="tableFile">{trs}</table></body></html>'.encode()


#: 实测那一篇的 EX-101.* 六行（cells 逐格照抄自 -index.htm）。
REAL_ROWS = [
    ('5', 'XBRL INSTANCE DOCUMENT', 'cost-20171126.xml', 'EX-101.INS', '863287'),
    ('6', 'XBRL TAXONOMY EXTENSION SCHEMA DOCUMENT', 'cost-20171126.xsd', 'EX-101.SCH', '30209'),
    ('7', 'XBRL ... CALCULATION LINKBASE', 'cost-20171126_cal.xml', 'EX-101.CAL', '72970'),
    ('8', 'XBRL ... DEFINITION LINKBASE', 'cost-20171126_def.xml', 'EX-101.DEF', '118580'),
    ('9', 'XBRL ... LABEL LINKBASE', 'cost-20171126_lab.xml', 'EX-101.LAB', '465016'),
    ('10', 'XBRL ... PRESENTATION LINKBASE', 'cost-20171126_pre.xml', 'EX-101.PRE', '260239'),
]

#: index.json 漏列时它长这样：只有四个包装文件，一份正文都不列。
#: 与 fetch/rates_lpla.py:252-258 判定 LPLA 那四份 8-K 时用的是同一个签名。
WRAPPERS_ONLY = [f'{ACC}-index-headers.html', f'{ACC}-index.html',
                 f'{ACC}-xbrl.zip', f'{ACC}.txt']


class TestShapeThree(unittest.TestCase):
    """回归签名：index.json 漏列 → 改读人读版索引 <accession>-index.htm。

    2026-09-05 之前这一形状会把整个 cost_sec 步打成 FAIL（[seg] 挂 → [tkt] 连带）。
    注意坏的是**清单**不是申报：同一个目录的 HTML 清单实测有 73 个文件，
    instance 直接 GET 也是 200。
    """

    def test_falls_back_to_the_human_index(self):
        with _Served({'index.json': _index(WRAPPERS_ONLY),
                      f'{ACC}-index.htm': _index_htm(REAL_ROWS),
                      'cost-20171126.xml': INSTANCE}) as s:
            self.assertEqual(s.run(), INSTANCE)
        self.assertNotIn('-xbrl.zip', ' '.join(s.asked),
                         '人读版索引已经够了，不该再去下 zip')

    def test_picks_EX_101_INS_not_the_linkbases(self):
        # 认的是 Type 那一格，不是文件名后缀 —— linkbase 的 Type 是 EX-101.CAL/DEF/LAB/PRE。
        with _Served({'index.json': _index(WRAPPERS_ONLY),
                      f'{ACC}-index.htm': _index_htm(REAL_ROWS),
                      'cost-20171126.xml': INSTANCE}) as s:
            s.run()
        # 排除第一条路那次 inline 探测（cost10q_htm.xml，必然 404）。
        got = [u for u in s.asked if u.endswith('.xml') and not u.endswith('_htm.xml')]
        self.assertEqual(len(got), 1, f'只该下 instance 那一个，实际 {got}')
        self.assertTrue(got[0].endswith('cost-20171126.xml'))

    def test_zip_is_the_last_resort_when_both_indexes_fail(self):
        # JSON 漏列 + 人读版也取不到 → 还有 -xbrl.zip 这条独立索引。
        with _Served({'index.json': _index(WRAPPERS_ONLY),
                      f'{ACC}-xbrl.zip': _zip({'cost-20171126_lab.xml': LINKBASE,
                                               'cost-20171126.xml': INSTANCE})}) as s:
            self.assertEqual(s.run(), INSTANCE)

    def test_corrupt_zip_still_raises_the_readable_error(self):
        with _Served({'index.json': _index(WRAPPERS_ONLY),
                      f'{ACC}-xbrl.zip': b'not a zip at all'}) as s:
            with self.assertRaises(cost_sec.CostSecError) as cm:
                s.run()
        self.assertIn('找不到 XBRL instance', str(cm.exception))
        self.assertIn('打不开', str(cm.exception))


class TestFailuresNameTheirCause(unittest.TestCase):
    """报错必须说清**每条路各自为什么没拿到**。

    否则「SEC 限速取不到」与「这篇真的没有 instance」在日志里长得一模一样 ——
    README「第四类：不出声的失败」的判据句是「它连续失败十天，和成功十天，
    在日志里长得一样吗？」。
    """

    def test_network_failure_is_not_reported_as_absence(self):
        # 人读版索引与 zip 都 404/限速：报错里必须留下取数失败的痕迹，
        # 而不是干巴巴一句「找不到」。
        with _Served({'index.json': _index(WRAPPERS_ONLY)}) as s:
            with self.assertRaises(cost_sec.CostSecError) as cm:
                s.run()
        msg = str(cm.exception)
        self.assertIn('SEC 取不到', msg, '取数失败的原因被吞掉了，会被误读成「这篇没有」')
        self.assertIn('index.json 只列了 4 项', msg, '要说清 JSON 那条路是怎么空的')

    def test_error_names_the_filing(self):
        with _Served({'index.json': _index(WRAPPERS_ONLY)}) as s:
            with self.assertRaises(cost_sec.CostSecError) as cm:
                s.run()
        msg = str(cm.exception)
        self.assertIn('10-Q', msg)
        self.assertIn('2017-12-21', msg)
        self.assertIn(ACC, msg)


def main():
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.TestLoader().loadTestsFromModule(sys.modules[__name__]))
    print('\n' + '=' * 72)
    if not result.wasSuccessful():
        print('FAILED —— %d 处失败 / %d 处错误'
              % (len(result.failures), len(result.errors)))
        return 1
    print('PASS —— 四条路都认得；index.json 漏列时改读人读版索引，'
          '且报错会说清是哪条路怎么断的。'
          '把人读版索引那段摘掉，TestShapeThree 里当场红 2 条。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
