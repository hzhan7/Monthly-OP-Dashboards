# -*- coding: utf-8 -*-
"""fetch/schw.py 的 URL 候选机制护栏 —— **全部离线**，一个网络请求都不打。

跑法: python3 test_schw_url_variants.py

━━ 这套测试守的是哪一件事 ━━
Schwab 的 CDN 文件名**不可推导**：七月 2019–2025 用月份全拼（schw_july2023_table.xlsx），
2026 年又改回三字母；前缀 schw_ / schwab_ 也不是按年切换，2025-04 单月冒出一个 schwab_。
模块原来只按「schw_ + 三字母」推一个 URL，于是对历史上每一个七月都拿不到附表与新闻稿。

这个 bug 之所以能活这么久，是因为它**一格数据都没缺**：七月的值由八月那期的 13 个月
滚动表顺手带进来了，CSV 上看不出任何异常。所以这套测试不测「数据对不对」——数据一直
是对的；它测的是**取数路径本身还通不通**，以及几条「修的时候最容易顺手改坏」的东西：

  · TestCandidates     —— 候选串的形状：七月两种写法都在、五月不重复、.XLSX 不进候选。
  · TestMonRemainsFlat —— **_MON 本体不许被元组化**。这是最容易犯的「修法」，而它会让
                          两处解析路径**静默**返回空表、一处 import 就炸（见各条注释）。
  · TestDownloadAny    —— 逐个试、第一个赢、先扫本地、坏格式让位、全落空不静默。
  · TestHitNameIsUsed  —— 写进 series/source_dates.csv 的证据必须是**命中的**文件名，
                          不能是首选那个（否则证据指向一个 404 的名字）。
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fetch import schw                                          # noqa: E402


class TestCandidates(unittest.TestCase):
    def _names(self, kind, ym):
        return [u.rsplit('/', 1)[-1] for u in schw._url_candidates(kind, ym)]

    def test_july_offers_both_spellings(self):
        """七月必须两种写法都试 —— 2019–2025 只有全拼命中，2026 只有三字母命中。"""
        for y in range(2019, 2027):
            names = self._names('monthly', (y, 7))
            self.assertIn(f'schw_jul{y}_table.xlsx', names)
            self.assertIn(f'schw_july{y}_table.xlsx', names)

    def test_three_letter_first(self):
        """三字母在前：它是 12 个月里 11 个月的写法，也是 2026 年七月的写法。

        顺序只影响命中前白打几个 404，不影响结果（一期只有一个名字命中，已实证）。
        """
        self.assertEqual(self._names('monthly', (2023, 7))[0], 'schw_jul2023_table.xlsx')

    def test_other_months_have_no_full_spelling(self):
        """除七月外不试全拼 —— 2018–2026 逐月扫过，全拼变体一律 404。

        给每个月都加全拼 = 每月多打 11 个必 404 的请求去换一个已知不存在的可能。
        """
        for m in (1, 2, 3, 4, 6, 8, 9, 10, 11, 12):
            names = self._names('monthly', (2023, m))
            full = schw._MON_FULL[m - 1].lower()
            self.assertFalse([n for n in names if full in n],
                             f'{m} 月不该有全拼候选，实得 {names}')

    def test_may_does_not_duplicate(self):
        """五月的三字母与全拼同形（may == may），去重后不能出现两条一样的。"""
        names = self._names('monthly', (2024, 5))
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(names, ['schw_may2024_table.xlsx', 'schwab_may2024_table.xlsx'])

    def test_both_prefixes_everywhere(self):
        """两个前缀都要试：2025-04 实测只有 schwab_ 命中，前后各月都是 schw_。"""
        self.assertIn('schwab_apr2025_table.xlsx', self._names('monthly', (2025, 4)))
        self.assertIn('schw_apr2025_table.xlsx', self._names('monthly', (2025, 4)))

    def test_quarterly_pdf_prefers_schwab(self):
        """季报正文 PDF 的常态前缀是 schwab_（月报是 schw_）——官方自己就不一致。"""
        self.assertEqual(self._names('pr_quarterly', (2026, 6))[0],
                         'schwab_q2_2026_earnings_release.pdf')
        self.assertEqual(self._names('pr_monthly', (2026, 8))[0],
                         'schw_aug2026_press_release.pdf')

    def test_uppercase_ext_never_a_candidate(self):
        """**.XLSX 绝不能进候选。**

        官方历史上确实发过 .XLSX（见 _HIST_XLSX），但 macOS 的文件系统大小写不敏感：
        盘上是 schw_q1_2018_earnings_tables.XLSX 时，os.path.exists(…'.xlsx') 也返回 True。
        一旦把它列进候选，_download_any 的「本地已有就用」会把一个**从来没 200 过**的
        名字判成命中，而且从此不再回网络核对 —— 比少一个候选严重得多。
        """
        for kind, ym in [('monthly', (2018, 2)), ('quarterly', (2018, 3)),
                         ('monthly', (2023, 7))]:
            for n in self._names(kind, ym):
                self.assertFalse(n.endswith('.XLSX'), f'{n} 把大写扩展名列进了候选')

    def test_template_url_is_a_string(self):
        """_template_url 仍须返回**一个字符串** —— _crosscheck_due_month 的报错文案用它。"""
        self.assertIsInstance(schw._template_url((2026, 7)), str)
        self.assertIn('q2_2026', schw._template_url((2026, 6)))    # 季末月走季报


class TestMonRemainsFlat(unittest.TestCase):
    """**_MON 不许被元组化。** 这是这个 bug 最容易犯的「修法」，后果分三档：

      · 静默档（最坏）：parse_edgar_monthly 里 `c.lower()[:3] in _MON` 与
        `[_MON[mm-1] for …] != hdr` 两处，元组化后恒不相等 → return {} →
        整条 EDGAR 腿对每一份申报都「查无此表」，**长得和「官方没附表」一模一样**。
        本模块 docstring 开头那段自嘲记的就是这个坑，别再踩一次。
      · 抛异常档：_MON.index(...) 两处 ValueError。
      · import 就炸档：_URL_MONTH_RE 的 '|'.join(... + _MON)。

    月份在 URL 里的写法另开一张 _MON_URL，两者互不相干。
    """

    def test_mon_is_flat_three_letter_strings(self):
        self.assertEqual(len(schw._MON), 12)
        for x in schw._MON:
            self.assertIsInstance(x, str, '_MON 的元素必须是字符串，不能是元组')
            self.assertEqual(len(x), 3)

    def test_mon_reverse_lookup_still_works(self):
        """六处反查用法的代表：靠 .index 把三字母换回月份号。"""
        self.assertEqual(schw._MON.index('jul') + 1, 7)
        self.assertEqual(schw._MON.index('dec') + 1, 12)

    def test_url_month_re_accepts_both_spellings(self):
        """判官侧（_URL_MONTH_RE）**本来就认全拼**，这次一个字都没动。

        这条 bug 的形状正是：认得出的写法，自己拼不出来。
        """
        for name, want in [('schw_july2023_table.xlsx', (2023, 7)),
                           ('schw_jul2026_table.xlsx', (2026, 7)),
                           ('schwab_apr2025_table.xlsx', (2025, 4))]:
            self.assertEqual(schw._url_report_ym(name), want, name)


class _FakeGet:
    """替掉 schw._get 的离线替身。table: {url: bytes | None}，None = 404。"""

    def __init__(self, table):
        self.table, self.asked = table, []

    def __call__(self, url, timeout=60):
        self.asked.append(url)
        return self.table.get(url)


class TestDownloadAny(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._real_get = schw._get
        schw.URL_VARIANTS.clear()

    def tearDown(self):
        schw._get = self._real_get

    @staticmethod
    def _zip(n=20_000):
        return b'PK\x03\x04' + b'x' * n

    def test_first_hit_wins_and_is_logged(self):
        """首选 404、次选 200 → 拿次选，并记进 URL_VARIANTS（官方换写法的唯一明信号）。"""
        urls = schw._url_candidates('monthly', (2023, 7))
        schw._get = _FakeGet({urls[1]: self._zip()})
        path, hit = schw._download_any(urls, self.tmp, what='2023-07')
        self.assertEqual(hit, urls[1])
        self.assertTrue(path.endswith('schw_july2023_table.xlsx'))
        self.assertEqual(len(schw.URL_VARIANTS), 1)

    def test_default_hit_is_not_logged(self):
        """命中首选是**正常**，不该刷日志 —— 否则真正的变体信号会被淹掉。"""
        urls = schw._url_candidates('monthly', (2026, 7))
        schw._get = _FakeGet({urls[0]: self._zip()})
        schw._download_any(urls, self.tmp, what='2026-07')
        self.assertEqual(schw.URL_VARIANTS, [])

    def test_local_scan_covers_every_candidate(self):
        """本地已有**任一**候选就不打网络。

        不先扫全部候选的话，每一轮都会为排在前面的那个 404 候选白打一次请求 ——
        一条本来能全缓存命中、零请求的重放路径会永久退化成网络路径。
        """
        urls = schw._url_candidates('monthly', (2023, 7))
        with open(os.path.join(self.tmp, urls[1].rsplit('/', 1)[-1]), 'wb') as f:
            f.write(self._zip())
        fake = _FakeGet({})
        schw._get = fake
        path, hit = schw._download_any(urls, self.tmp)
        self.assertEqual(hit, urls[1])
        self.assertEqual(fake.asked, [], '本地已有，不该打任何网络请求')

    def test_reuse_false_still_probes_network(self):
        """reuse=False（最近两个月强制重取）时不许走本地那条捷径。"""
        urls = schw._url_candidates('monthly', (2026, 8))
        with open(os.path.join(self.tmp, urls[0].rsplit('/', 1)[-1]), 'wb') as f:
            f.write(self._zip())
        fake = _FakeGet({urls[0]: self._zip(30_000)})
        schw._get = fake
        schw._download_any(urls, self.tmp, reuse=False)
        self.assertEqual(fake.asked, [urls[0]])

    def test_all_404_returns_none_not_raise(self):
        """全 404 是**正常**（季末月的月报本来就不存在），返回 (None, None) 不抛。"""
        urls = schw._url_candidates('monthly', (2026, 3))
        schw._get = _FakeGet({})
        self.assertEqual(schw._download_any(urls, self.tmp), (None, None))

    def test_bad_format_yields_to_next_candidate(self):
        """首选回了一张 200 的 HTML 错误页 → 换下一个，不能把整轮炸掉。

        CDN 偶尔这么干（长度够大、内容全错）。单 URL 时代当场抛是对的；
        候选化之后当场抛会让排在后面的正确名字永远轮不到。
        """
        urls = schw._url_candidates('monthly', (2023, 7))
        schw._get = _FakeGet({urls[0]: b'<html>' + b'x' * 20_000, urls[1]: self._zip()})
        path, hit = schw._download_any(urls, self.tmp)
        self.assertEqual(hit, urls[1])

    def test_bad_format_alone_is_not_silent(self):
        """但如果**只有**坏格式、没有一个好的，必须抛 —— 静默是不能接受的那一档。"""
        urls = schw._url_candidates('monthly', (2023, 7))
        schw._get = _FakeGet({urls[0]: b'<html>' + b'x' * 20_000})
        with self.assertRaises(schw.FetchError):
            schw._download_any(urls, self.tmp)


class TestHitNameIsUsed(unittest.TestCase):
    """release_date 写进 series/source_dates.csv 的证据串必须指向**命中的**文件。

    取首选那个名字会写出一条指向 404 文件名的「证据」，而它看上去完全正常 ——
    下次有人拿它去复核，会得到「这份文件不存在」，然后开始怀疑数据本身。
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._real_get = schw._get

    def tearDown(self):
        schw._get = self._real_get

    def test_evidence_names_the_hit_not_the_first_candidate(self):
        urls = schw._url_candidates('pr_monthly', (2024, 7))
        schw._get = _FakeGet({})                       # 全 404 → 走「都是 404」那条返回
        date, why = schw.release_date('monthly', (2024, 7), self.tmp)
        self.assertIsNone(date)
        # 全 404 的理由里要把试过的名字都列出来，不能只报首选
        self.assertIn('schw_jul2024_press_release.pdf', why)
        self.assertIn('schw_july2024_press_release.pdf', why)


if __name__ == '__main__':
    unittest.main(verbosity=2)
