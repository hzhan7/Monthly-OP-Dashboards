# -*- coding: utf-8 -*-
"""build/payload_guard.py + build/brief.py + build/single.py 三条护栏的单元测试。

跑法: python3 build/test_guards.py        （只用标准库 + numpy，不需要 pytest）

这套测试是为「把 MOPS 官方增减原因原文写进 brief」那次改造建的，守两件事（A、B 组）；
2026-09 加了第三件（H 组，`spike_cap()` 的端点护栏），理由写在那一组的组头上 ——
一句话：**那条缺陷现网一处都没命中，只能靠注入守**，真产出当不了判据。

 (a) **payload_guard 的 nan/inf 正则放宽之后，一个该拦的都没少拦。**
     必须拦的那一组（`$nanbn` / `nan%` / `+naNpp` / `inf` / `infinity` …）是
     模块头注释里逐条列过的既有用例，改正则最容易出的事故就是把它们一起放掉。
     必须放行的那一组是新加的：`NAND` / `info` / `nano` 这类**出现在中文句子里的
     正常英文词**，南亚科（DRAM）与世芯（ASIC）的备注原文里出现它们是常态。

 (b) **brief.render() 的引文豁免不改变不引用时的行为。**
     测法不是造夹具，是把仓库里 19 个 data/*.js 已发布的 brief **原文**取出来
     重新过一遍 render()，逐字节比对。夹具能证明的只是「代码与夹具自洽」
     （build/test_pools.py 的 TestRealFxTable 那一段吃过这个亏），
     只有拿真产出去撞才能证明「代码与仓库自洽」。
"""

import glob
import json
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

import brief as B                # noqa: E402
import payload_guard as PG       # noqa: E402


# ═══════════════════════════════════════════════════════════════════════════
# A. payload_guard —— 必须拦 / 必须放
# ═══════════════════════════════════════════════════════════════════════════
# 必须拦：模块头「字符串匹配的误伤边界」逐条列过的既有用例 + 真实事故串。
MUST_BLOCK = [
    'nan%',                                   # f'{nan:+.1f}%'
    '$nanbn',                                 # f'${nan:,.1f}bn' —— 右侧紧跟单位字母
    'nanmn/日',
    '$nantn',
    'nank',
    '+nanpp',
    '+naNpp',                                 # 大小写混写照样是格式化产物
    'NaN',
    'nan',
    '-inf',
    'inf',
    'infinity',
    'Infinity',
    '客户资产 $nanbn（+nan% y/y）',            # 模块头原样引用的那条 headline
    '南亚科本月营收 NT$nanbn',                 # 中文串里夹坏值
    '南亚科（nanya）本月 NAND 需求回升，营收 $nanbn',  # 放行词在前、坏串在后
    'nanbp',
    'nanx',
]

# 必须放：正常英文词 / 专有名词，出现在中文句子里不许报 FAIL。
MUST_PASS = [
    'NAND',
    'nand',
    '3D NAND 与 DRAM 需求同步回升',
    '受 NAND 与 HBM 需求成长影响。',           # 南亚科式备注
    'info',
    'more info',
    'nano',
    'nanometer',
    '3nm nanosheet 制程',
    'infra',
    'infer',
    'inflection',
    'information',
    'inflows',
    'influence',
    'infrastructure',
    'financial',
    'nanya',                                  # ticker（既有白名单）
    'build/specs/nanya.py',
    '南亚科技（nanya，2408.TW）',
    'HBM',
    'AI',
    'ASIC',
    '本月營收較去年同期增加，係因量產產品增加所致。',   # 世芯備註原文（繁体）
    '海外子公司之營收係以當月平均匯率換算之',           # 联发科備註原文
    '受市場需求成長影響。',                             # 南亚科備註原文
    '主要為晶圓產品收入增加',                           # 创意備註原文
]


def _tripped(s):
    """把串塞进一个 payload 走真 check()，返回是否被拦。"""
    try:
        PG.check({'brief': s})
        return False
    except PG.PayloadGuardError:
        return True


class TestPayloadGuardBlocks(unittest.TestCase):
    def test_must_block(self):
        missed = [s for s in MUST_BLOCK if not _tripped(s)]
        self.assertEqual(missed, [], f'这些坏串被放过了：{missed}')


class TestPayloadGuardPasses(unittest.TestCase):
    def test_must_pass(self):
        hit = [s for s in MUST_PASS if _tripped(s)]
        self.assertEqual(hit, [], f'这些正常串被误伤：{hit}')


class TestPayloadGuardNumeric(unittest.TestCase):
    """数值型 NaN / Inf 与合法 null 的行为不因字符串规则改动而变。"""

    def test_float_nan_blocked(self):
        with self.assertRaises(PG.PayloadGuardError):
            PG.check({'exhibits': [{'n': 3, 'title': 'x', 'v': [1.0, float('nan')]}]})

    def test_float_inf_blocked(self):
        with self.assertRaises(PG.PayloadGuardError):
            PG.check({'v': float('inf')})

    def test_null_is_legal(self):
        PG.check({'v': [1.0, None, 3.0], 'brief': '缺月按规矩 3 断开'})

    def test_later_bad_string_not_masked_by_allowed_word(self):
        """白名单/放行词在前，不能掩盖同一串后段的真问题（finditer + continue 的性质）。"""
        self.assertTrue(_tripped('NAND 需求回升，但客户资产 $nanbn'))
        self.assertTrue(_tripped('nanya 南亚科，同比 +nan%'))


# ═══════════════════════════════════════════════════════════════════════════
# B. brief.render() —— 不引用时逐字节不变
# ═══════════════════════════════════════════════════════════════════════════
def _published_briefs():
    """从 data/*.js 里取出已发布的 brief，拆回 (页名, 标题, body)。"""
    out = []
    for p in sorted(glob.glob(os.path.join(ROOT, 'data', '*.js'))):
        with open(p, encoding='utf-8') as fh:
            m = re.search(r'window\.DASH = (.*);\n?$', fh.read(), re.S)
        if not m:
            continue
        try:
            b = json.loads(m.group(1)).get('brief')
        except ValueError:
            continue
        if not b:
            continue
        mm = re.match(r'^<h4>(.*?)</h4><p>(.*)</p>$', b, re.S)
        if mm:
            out.append((os.path.basename(p), mm.group(1), mm.group(2)))
    return out


def _remark_rows():
    """`series/mops_remarks.csv` → {(ticker, 'YYYY-MM'): remark 原文}。读不到返回 {}。"""
    import csv
    p = os.path.join(ROOT, 'series', 'mops_remarks.csv')
    try:
        with open(p, encoding='utf-8') as fh:
            return {(r['ticker'], r['month']): (r.get('remark') or '').strip()
                    for r in csv.DictReader(fh)}
    except OSError:
        return {}


def _data_through(page):
    """data/<page> 的 `data_through`（'YYYY-MM'）。取不到返回 None。"""
    try:
        with open(os.path.join(ROOT, 'data', page), encoding='utf-8') as fh:
            m = re.search(r'window\.DASH = (.*);\n?$', fh.read(), re.S)
        return json.loads(m.group(1)).get('data_through') if m else None
    except (OSError, ValueError, AttributeError):
        return None


class TestRenderRegression(unittest.TestCase):
    """19 个已发布页的 brief 原样重跑 render()，输出必须逐字节相同。"""

    def test_republish_identical(self):
        pages = _published_briefs()
        self.assertGreaterEqual(len(pages), 15, '没读到足够的已发布 brief，测试无效')
        for name, title, body in pages:
            with self.subTest(page=name):
                got = B.render([body], title=title)
                self.assertEqual(got, f'<h4>{title}</h4><p>{body}</p>')

    def test_quote_marker_only_where_the_csv_says_so(self):
        """哪几页带引文标记，必须与 `series/mops_remarks.csv` 逐页对得上。

        这条原来断言的是「今天没有任何一页用引文标记」——那在**接线之前**成立，
        接线之后它每个月都会误报（本轮 alchip / guc / mtk / nanya 四页正当地带上了）。
        直接删掉又会把这条路径变成无人看守的。所以改成断言真正的不变式：

          页面带引文  ⟺  该页 `data_through` 那个月在 CSV 里的 `remark` 非空

        它同时守住两个方向 —— 该有的没有（fetch 断流 / brief 那一支写坏了）
        与不该有的有（引了一个库里没有的字符串）。并且逐字比对引文内容，
        繁体被转成简体、标点被规整、原文被截断，这里都会当场失败。
        """
        rows = _remark_rows()
        if not rows:
            self.skipTest('series/mops_remarks.csv 不可读，跳过')
        pages = {t for t, _ in rows}           # 用这张表的那几页（=七家半导体页）
        newest = max(m for _, m in rows)
        seen, ahead = 0, []
        for name, _, body in _published_briefs():
            t = name[:-3]
            if t not in pages:
                continue                       # 交易所页等，本来就不在这张表里
            month = _data_through(name)
            if (t, month) not in rows:
                # 唯一合法的缺席：这一页跑在了共享 MOPS 表**前面**。
                # 各家自己的申报最早次月第 4 天就到，而 MOPS 全市场汇总要等最后一家
                # 申报完（实测第 13 天，见 monthly_run.mops_remarks 的 docstring）——
                # 中间那十天里，先披露的那一两页本来就比这张表新。
                # 2026-09-05 实测：umc 的 6-K 已到 2026-08，而 CSV 还停在 2026-07。
                # 原来这里写的是无条件 `continue` + 末尾 `seen >= 7`，于是那十天里
                # 每天都会误报一次「测试无效」——而 test_guards 是 preflight 闸门，
                # 误报一次就是整轮不发。
                if month > newest:
                    ahead.append((t, month))
                    continue
                self.fail(f'{name} 的 data_through={month} 不晚于 CSV 最新月 {newest}，'
                          f'却在 CSV 里找不到 ({t}, {month}) —— 接线多半断了'
                          f'（页面路径变了 / CSV 的 ticker 拼写变了）')
            seen += 1
            want = rows[(t, month)]
            with self.subTest(page=name):
                got = re.findall(r'<span class="mops-quote">(.*?)</span>', body)
                if want:
                    self.assertEqual(got, [want],
                                     f'{name} 的引文与 CSV 不符（逐字比对）')
                else:
                    self.assertEqual(got, [],
                                     f'{name} 本月 CSV 里备注为空，页面却印出了引文')
        # 每一页都要有着落：要么逐字对上了，要么明确是「跑在表前面」。
        # 这比原来的 `seen >= 7` 更严 —— 原来某页悄悄消失只会让计数少一个，
        # 而 7 这个数字自己是硬编码的，页数一变就得改。
        self.assertEqual(seen + len(ahead), len(pages),
                         f'用这张表的有 {len(pages)} 页，只扫到 {seen} 页对上 + '
                         f'{len(ahead)} 页跑在表前面 —— 有页面没被扫到，测试无效')


class TestRenderBounds(unittest.TestCase):
    """无引文时的上下限行为。"""

    def test_too_short_fails(self):
        with self.assertRaises(SystemExit):
            B.render(['短' * 229])

    def test_lo_edge_passes(self):
        B.render(['短' * 230])

    def test_hi_edge_passes(self):
        B.render(['长' * 380])

    def test_too_long_fails(self):
        with self.assertRaises(SystemExit):
            B.render(['长' * 381])

    def test_tags_not_counted(self):
        """HTML 标签不计入字数（既有口径）。"""
        B.render(['<b>' + '字' * 230 + '</b>'])


# ═══════════════════════════════════════════════════════════════════════════
# C. brief.quote() —— 引文豁免
# ═══════════════════════════════════════════════════════════════════════════
# 2026-07 期实测的四条 MOPS 備註原文（繁体原值，不转简体）。
REMARKS = {
    'mtk': '海外子公司之營收係以當月平均匯率換算之',
    'nanya': '受市場需求成長影響。',
    'alchip': '本月營收較去年同期增加，係因量產產品增加所致。',
    'guc': '主要為晶圓產品收入增加',
}


class TestQuoteHelper(unittest.TestCase):
    def test_real_remarks_all_fit(self):
        for t, r in REMARKS.items():
            with self.subTest(ticker=t):
                self.assertLessEqual(len(r), B.QUOTE_MAX)
                self.assertIn(r, B.quote(r))       # 原文逐字保留，未转简体、未截断

    def test_whitespace_folded_only(self):
        self.assertEqual(B.quote('  受市場需求\n 成長影響。 '),
                         B.quote('受市場需求 成長影響。'))

    def test_empty_remark_raises(self):
        for bad in ('', '   ', '\n'):
            with self.subTest(v=bad):
                with self.assertRaises(SystemExit):
                    B.quote(bad)

    def test_angle_brackets_raise(self):
        with self.assertRaises(SystemExit):
            B.quote('受<b>市場</b>需求成長影響。')

    def test_over_max_raises(self):
        with self.assertRaises(SystemExit):
            B.quote('原' * (B.QUOTE_MAX + 1))

    def test_quoted_len_matches_plain(self):
        r = REMARKS['alchip']
        self.assertEqual(B.quoted_len(B.quote(r)), len(r))


class TestQuoteExemption(unittest.TestCase):
    """减法语义：豁免只对引文成立，上下限对自撰部分同时成立。"""

    def test_quote_buys_headroom_for_the_quote_only(self):
        """自撰 380（顶格）+ 引文 20 ⇒ 总长 400，通过。"""
        out = B.render(['我' * 380, B.quote(REMARKS['mtk'])])
        self.assertIn(REMARKS['mtk'], out)

    def test_quote_does_not_buy_headroom_for_prose(self):
        """自撰 381 ⇒ 无论引不引，都必须失败。"""
        with self.assertRaises(SystemExit):
            B.render(['我' * 381, B.quote(REMARKS['mtk'])])

    def test_long_quote_thin_prose_fails(self):
        """整条机制的要害：引文 100 字 + 自撰 200 字，总长 300 好看，但必须失败。

        「只把 hi 调大」的做法会放它过关 —— 那正是这条护栏本来要拦的东西。
        """
        with self.assertRaises(SystemExit):
            B.render(['我' * 200, B.quote('原' * 100)])

    def test_floor_rises_with_quote(self):
        """引 100 字，自撰仍须满 230（总长 330）才够格。"""
        with self.assertRaises(SystemExit):
            B.render(['我' * 229, B.quote('原' * 100)])
        B.render(['我' * 230, B.quote('原' * 100)])

    def test_quote_cap_enforced_in_render(self):
        """多段引文合计也要受 QUOTE_MAX 管，不能靠拆成两段绕过。"""
        half = '原' * (B.QUOTE_MAX // 2 + 1)
        with self.assertRaises(SystemExit):
            B.render(['我' * 300, B.quote(half), B.quote(half)])

    def test_lead_in_words_are_ours(self):
        """引号与引导语算我们自己的字（它们在标记外面）。"""
        r = REMARKS['nanya']
        body = '我' * 380 + '公司在备注栏填的是「' + B.quote(r) + '」。'
        with self.assertRaises(SystemExit):
            B.render([body])

    def test_payload_guard_accepts_a_quoted_brief_wired(self):
        """两条护栏串起来跑一遍：带引文、带 NAND 的 brief 能过 payload_guard。"""
        body = ('我' * 300 + '公司在备注栏填的是「'
                + B.quote('受 NAND 與 HBM 需求成長影響。') + '」。')
        PG.check({'brief': B.render([body])})


class TestProseLen(unittest.TestCase):
    """prose_len 与 render 的判据必须是同一个数（render 那两支没改，数法在两处）。"""

    def test_matches_render_at_both_edges(self):
        for q in ('', B.quote(REMARKS['mtk'])):
            with self.subTest(quoted=bool(q)):
                for n in (B.PROSE_LO, B.PROSE_HI):
                    s = ['我' * n, q]
                    self.assertEqual(B.prose_len(s), n)
                    B.render(s)
                for n in (B.PROSE_LO - 1, B.PROSE_HI + 1):
                    s = ['我' * n, q]
                    self.assertEqual(B.prose_len(s), n)
                    with self.assertRaises(SystemExit):
                        B.render(s)

    def test_tags_not_counted(self):
        self.assertEqual(B.prose_len(['<b>我我</b>', '我', '']), 3)


class TestFitOptional(unittest.TestCase):
    """可让位的句子：放得下原样、放不下换精简版、再放不下不写（2026-09-12 tsm 事故）。

    形状照抄事故现场：前文 + 钩子句 + 引文句，引导语「公司填的是「」」。」8 字照常计费。
    """

    LEAD = '公司填的是「' + B.quote('因先進製程產品需求增加所致。') + '」。'

    def test_fits_unchanged_and_compact_not_called(self):
        s = ['我' * 300, '钩' * 50, self.LEAD]            # 358
        called = []
        out = B.fit_optional(s, 1, compact=lambda: called.append(1) or '短')
        self.assertEqual(out, '钩' * 50)
        self.assertEqual(called, [])

    def test_overflow_takes_compact(self):
        s = ['我' * 300, '钩' * 80, self.LEAD]            # 388
        out = B.fit_optional(s, 1, compact=lambda: '钩' * 60)
        self.assertEqual(out, '钩' * 60)                   # 368
        B.render([s[0], out, s[2]])

    def test_compact_still_overflows_drops_sentence(self):
        s = ['我' * 300, '钩' * 80, self.LEAD]
        out = B.fit_optional(s, 1, compact=lambda: '钩' * 79)   # 387，仍超
        self.assertEqual(out, '')
        B.render([s[0], out, s[2]])

    def test_no_compact_drops_sentence(self):
        s = ['我' * 300, '钩' * 80, self.LEAD]
        self.assertEqual(B.fit_optional(s, 1), '')

    def test_does_not_mask_overflow_elsewhere(self):
        """别的句子本身就超额：这一句让掉了，render 照样硬失败。"""
        s = ['我' * 390, '钩' * 10, self.LEAD]
        out = B.fit_optional(s, 1, compact=lambda: '钩')
        self.assertEqual(out, '')
        with self.assertRaises(SystemExit):
            B.render([s[0], out, s[2]])

    def test_input_list_not_mutated(self):
        s = ['我' * 300, '钩' * 80, self.LEAD]
        before = list(s)
        B.fit_optional(s, 1, compact=lambda: '钩' * 60)
        self.assertEqual(s, before)


# ═══════════════════════════════════════════════════════════════════════════
# D. 打真表 —— series/mops_remarks.csv 的每一条备注原文
# ═══════════════════════════════════════════════════════════════════════════
# 上面 A/C 两组是我自己编的串，它们只能证明「代码与我的假设自洽」。
# 这一组把**公司真的填过的**每一条备注原文喂进两条护栏（同 test_pools.py 的
# TestRealFxTable）。实测 168 行里 65 条非空、最长 31 字，且 guc 的原文里真的夹着
# 半角括号与英文（`委託設計(NRE)`、`晶圓產品(Wafer production)`）—— 正是 B 组要防的形状。
REMARKS_CSV = os.path.join(ROOT, 'series', 'mops_remarks.csv')


@unittest.skipUnless(os.path.exists(REMARKS_CSV),
                     'series/mops_remarks.csv 还没落库（fetch/mops_remarks.py 未跑）')
class TestRealRemarks(unittest.TestCase):
    def _rows(self):
        import csv
        with open(REMARKS_CSV, encoding='utf-8') as f:
            return [r for r in csv.DictReader(f) if r.get('remark', '').strip()]

    def test_every_real_remark_survives_both_guards(self):
        rows = self._rows()
        self.assertGreater(len(rows), 20, '非空备注太少，测试无意义')
        for r in rows:
            with self.subTest(month=r['month'], ticker=r['ticker']):
                q = B.quote(r['remark'])                       # 不该被 quote() 拒绝
                body = '我' * 300 + '公司在备注栏填的是「' + q + '」。'
                PG.check({'brief': B.render([body])})          # 不该被 payload_guard 误伤

    def test_real_remarks_are_well_within_quote_max(self):
        longest = max(len(r['remark'].strip()) for r in self._rows())
        self.assertLessEqual(longest, B.QUOTE_MAX,
                             f'最长备注 {longest} 字已超 QUOTE_MAX，该重新审视上限与「不截断」的处理')

    def test_verbatim_not_transcoded(self):
        """原文逐字进出：不转简体、不改标点。"""
        for r in self._rows()[:40]:
            with self.subTest(month=r['month'], ticker=r['ticker']):
                self.assertIn(r['remark'].strip(), B.quote(r['remark']))


# ═══════════════════════════════════════════════════════════════════════════
# E. audit_overdue_headline —— 判据必须与首页红点逐字等价
# ═══════════════════════════════════════════════════════════════════════════
# 这一道守的不是「护栏会不会响」，而是**它和红点会不会各说各话**。两边一旦分家，
# cron 日志与首页就会在同一天给出相反的结论，而那种矛盾没人能一眼判出谁对。
#
# 测法照本文件 (b) 的规矩：不造夹具，拿**真判据**去撞 —— 把 index.html:70-85 的
# stale() 逐行移植成 Python，与 monthly_run.audit_overdue_headline 用的那条算术
# 在 28 家 × 6 个 data_through × 730 天上逐组对拍。
#
# ⚠ 移植时两处最容易写错，都在下面 _js_stale 里标了：
#   · end.getMonth() 是 **0-indexed**，JS 里 `mo = getMonth()===0 ? 12 : getMonth()`
#     算的是「end 的前一个月」= 候选月；
#   · JS 的门槛是 `now >= end + (lag+grace) 天`，而 _due_month(off) 的门槛是
#     `today >= end + (off-1) 天` —— 故 **off = lag + GRACE + 1**。写成 lag+GRACE
#     会让护栏比红点早一天开口。这个 ±1 有实测代价：见 docs/DELIVERY.md 里
#     同一处偏移漏写、让五家闸门整体晚开一天的那条。
import datetime  # noqa: E402

_MR = None
_ROSTER = None


def _load_once():
    global _MR, _ROSTER
    if _MR is None:
        import importlib.util
        for name, path in (('_mr_t', os.path.join(ROOT, 'monthly_run.py')),
                           ('_rost_t', os.path.join(ROOT, 'build', 'roster.py'))):
            spec = importlib.util.spec_from_file_location(name, path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            if name == '_mr_t':
                _MR = mod
            else:
                _ROSTER = mod
    return _MR, _ROSTER


def _js_stale(lag, through, now, grace):
    """index.html:70-85 stale() 的逐行移植。now 为 datetime.date。"""
    for k in range(6):
        n = now.year * 12 + now.month - 1 - k
        ey, em0 = n // 12, n % 12                      # em0 = end.getMonth()，0-indexed
        end = datetime.date(ey, em0 + 1, 1)            # 候选月的下月 1 号 = 月末 + 1
        mo = 12 if em0 == 0 else em0                   # 候选月 1-12
        due = end + datetime.timedelta(
            days=(lag[1] if mo % 3 == 0 else lag[0]) + grace)
        if now >= due:
            y = ey - 1 if em0 == 0 else ey
            return through < f'{y}-{mo:02d}'
    return False


class TestOverdueMatchesRedDot(unittest.TestCase):
    THROUGHS = ('2025-11', '2026-05', '2026-06', '2026-07', '2026-08', '2026-09')
    DAYS = 730

    def _disagreements(self, bump):
        mr, rost = _load_once()
        grace, d0, bad = rost.GRACE, datetime.date(2026, 1, 1), []
        for t, lag in sorted(rost.LAG.items()):
            for through in self.THROUGHS:
                for i in range(self.DAYS):
                    today = d0 + datetime.timedelta(days=i)
                    due = mr._due_month(
                        (lag[0] + grace + bump, lag[1] + grace + bump), today)
                    if _js_stale(lag, through, today, grace) != bool(due and through < due):
                        bad.append((t, through, today))
        return bad

    def test_identical_to_red_dot(self):
        bad = self._disagreements(1)                   # 1 = 生产用的那个偏移
        self.assertEqual(bad, [], f'与首页红点分歧 {len(bad)} 组，前三：{bad[:3]}')

    def test_offset_actually_matters(self):
        """反向验：这个对拍不是空过的 —— 偏移写错一天，它必须抓到。"""
        for bump in (0, 2):
            with self.subTest(bump=bump):
                self.assertNotEqual(
                    self._disagreements(bump), [],
                    f'偏移 lag+GRACE+{bump} 竟无分歧 —— 对拍失去意义，先查 _js_stale')

    def test_no_false_alarm_today(self):
        """今天真跑一遍：仓库当前状态下不该有任何一家逾期（有就是真出事了）。"""
        mr, _ = _load_once()
        self.assertEqual(mr.audit_overdue_headline(), [])



# ═══════════════════════════════════════════════════════════════════════════
# F. fetch/msci.py 的缓存键池 —— 写小了护栏 A 会反过来咬人
# ═══════════════════════════════════════════════════════════════════════════
# 这里只测**纯函数**。护栏 A 的其余部分（render_age 阈值、重定向分支、缺头 WARN）
# 要发真请求才验得了，不进 preflight —— 那三条的实测结果记在提交信息里。
#
# 池长是本模块唯一一个「写错了会让护栏反过来咬人」的常数：边缘 s-maxage 是 30 天，
# 池长若 ≤ 30，键回环时会撞上自己 30 天前钉住的旧副本，于是每天误 FAIL。
class TestMsciCacheKeyPool(unittest.TestCase):
    def setUp(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            '_msci_t', os.path.join(ROOT, 'fetch', 'msci.py'))
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)

    S_MAXAGE_DAYS = 30          # 响应头 s-maxage=2592000，见 fetch/msci.py 文件头

    def test_pool_outlasts_edge_ttl(self):
        self.assertGreater(
            len(self.m._KEY_POOL), self.S_MAXAGE_DAYS * 2,
            '缓存键池必须远大于边缘 TTL 的天数，否则回环会撞上自己钉住的旧副本')

    def test_no_repeat_within_a_full_cycle(self):
        d0 = datetime.date(2026, 1, 1)
        n = len(self.m._KEY_POOL)
        urls = [self.m._cache_key_url(d0 + datetime.timedelta(days=i)) for i in range(n)]
        self.assertEqual(len(set(urls)), n, '一个周期内出现了重复的缓存键')

    def test_retry_key_differs_and_is_long_unused(self):
        d0 = datetime.date(2026, 1, 1)
        shift = len(self.m._KEY_POOL) // 2
        self.assertNotEqual(self.m._cache_key_url(d0),
                            self.m._cache_key_url(d0, shift=shift))
        self.assertGreater(shift, self.S_MAXAGE_DAYS,
                           '重试用的键距上次使用不足一个 TTL，可能仍是热副本')

    def test_variant_differs_from_canonical_only_in_case(self):
        """变体只能改大小写 —— 改出别的字符就不是同一个页面了。"""
        d0 = datetime.date(2026, 1, 1)
        for i in range(0, len(self.m._KEY_POOL), 37):
            u = self.m._cache_key_url(d0 + datetime.timedelta(days=i))
            with self.subTest(i=i):
                self.assertEqual(u.lower(), self.m.URL.lower())
                self.assertNotEqual(u, self.m.URL)      # 必须真的换了键

    def test_max_render_age_is_over_a_day(self):
        """阈值必须大于一天：同一天人工重跑会复用当日键，最坏 24 小时。"""
        self.assertGreater(self.m.MAX_RENDER_AGE, 24 * 3600)
        self.assertLess(self.m.MAX_RENDER_AGE, self.S_MAXAGE_DAYS * 86400)



# ═══════════════════════════════════════════════════════════════════════════
# F2. fetch/sgx.py 的折行行标签 —— 上下两半都要接回数值行
# ═══════════════════════════════════════════════════════════════════════════
# 2025-09 起 SGX 月报把 Lump Premium 改名为
# `SGX Platts Iron Ore CFR China (Lump Premium) Index Futures`，版面上折成两行、数字夹在中间。
# `_parse_page` 当时只接下半截，标签读成 `Index Futures`，"Iron Ore" 在丢掉的上半截里 ——
# vol_iron_ore_contracts 连续 12 个月静默少加一行（fetch/sgx.py 口径坑 19）。
# 这里用**合成页面**复刻那一处的几何（上半截在数值行上方 ~5.5pt、下半截在下方 ~5.5pt、
# 行距 ~17pt），不依赖 cache/（gitignore 且会被 prune）；有原件时再加一道真 PDF 的对账。
class _FakeSgxPage:
    """只实现 `_page_lines()` 用到的两样：`rect` 与 `get_text('dict')`。"""

    def __init__(self, lines, w=595.0, h=842.0):
        self.rect = type('R', (), {'width': w, 'height': h})()
        self._lines = lines                           # [(x0, yc, text)]，行高固定 11.8pt

    def get_text(self, kind):
        assert kind == 'dict'
        return {'blocks': [{'type': 0, 'lines': [
            {'bbox': (x0, yc - 5.9, x0 + 6.0 * len(t), yc + 5.9), 'spans': [{'text': t}]}
            for x0, yc, t in self._lines]}]}


def _sgx_row(yc, label, nums, x0s=(300.0, 360.0, 420.0)):
    out = [(51.0, yc, label)] if label else []
    return out + [(x, yc, n) for x, n in zip(x0s, nums)]


class TestSgxWrappedLabel(unittest.TestCase):
    MON = '2026-08'

    def setUp(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            '_sgx_t', os.path.join(ROOT, 'fetch', 'sgx.py'))
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)

    def _page(self):
        lines = [(51.0, 300.0, 'Metal And Dry Bulk Volume'),
                 (300.0, 330.0, 'Jun 2026'), (360.0, 330.0, 'Jul 2026'), (420.0, 330.0, 'Aug 2026')]
        lines += _sgx_row(360.0, 'SGX IODEX Iron Ore Futures', ('4,774,524', '4,455,532', '4,127,939'))
        lines += _sgx_row(377.0, 'SGX Options On IODEX Iron Ore Swaps', ('0', '0', '0'))
        # 真 PDF（2026-08 期 p24）的排法：上半截、数值行、下半截三条各自独立的文字行
        lines += [(51.0, 388.7, 'SGX Platts Iron Ore CFR China (Lump Premium)')]
        lines += _sgx_row(394.2, '', ('28,774', '29,391', '35,016'))
        lines += [(51.0, 399.5, 'Index Futures')]
        lines += [(51.0, 411.0, 'SGX Platts Iron Ore CFR China (Lump Premium)')]
        lines += _sgx_row(416.5, '', ('0', '0', '0'))
        lines += [(51.0, 422.0, 'Swaps')]
        lines += _sgx_row(439.0, 'Total', ('7,000,000', '6,500,000', '6,000,000'))
        # 紧接着的下一张表：自己没有标题行、直接是表头 —— 它的 title 不许被上面某一行的碎片占掉
        lines += [(300.0, 480.0, 'Jun 2026'), (360.0, 480.0, 'Jul 2026'), (420.0, 480.0, 'Aug 2026')]
        lines += [(51.0, 509.5, 'SGX Platts Iron Ore CFR China (Lump Premium)')]
        lines += _sgx_row(515.0, '', ('1', '2', '3'))
        lines += [(51.0, 520.5, 'Index Futures')]
        return _FakeSgxPage(lines)

    def test_both_halves_rejoined(self):
        b = self.m._parse_page(self._page(), running_head=None)
        labs = [r['lab'] for r in b[0]['rows']]
        self.assertEqual(labs, [
            'SGX IODEX Iron Ore Futures',
            'SGX Options On IODEX Iron Ore Swaps',
            'SGX Platts Iron Ore CFR China (Lump Premium) Index Futures',
            'SGX Platts Iron Ore CFR China (Lump Premium) Swaps',
            'Total'])
        self.assertEqual(b[0]['rows'][2].get('lab_head'),
                         'SGX Platts Iron Ore CFR China (Lump Premium)')
        self.assertIsNone(b[0]['rows'][0].get('lab_head'))

    def test_upper_half_is_not_a_title_candidate(self):
        b = self.m._parse_page(self._page(), running_head=None)
        self.assertEqual(b[0]['title'], 'Metal And Dry Bulk Volume')
        self.assertIsNone(b[1]['title'],
                          '折行上半截被当成了下一张表的标题 —— 它已经补进了行标签，不许再用一次')

    def test_iron_ore_total_counts_the_wrapped_row(self):
        b = self.m._parse_page(self._page(), running_head=None)
        # 4,127,939 + 0 + 35,016 + 0；只修下半截的旧逻辑会得到 4,127,939
        self.assertEqual(self.m._read_iron_ore(b[:1], self.MON), 4127939 + 35016)

    def test_bottom_aligned_wrap(self):
        """第二种排法：数字与最后一行齐平，上半截在上方 ~10.8pt（2024-07 期 p12 实测）。"""
        lines = [(51.0, 250.0, 'Equity Index Futures Volume'),
                 (300.0, 280.0, 'Jun 2024'), (360.0, 280.0, 'Jul 2024')]
        lines += _sgx_row(316.6, 'FTSE Emerging Market Index Futures', ('5', '6'))
        lines += [(51.0, 332.8, 'FTSE Emerging Market inc Korea Net Total Return (USD)')]
        lines += _sgx_row(343.6, 'Index Futures', ('0', '0'))
        lines += _sgx_row(359.8, 'FTSE Emerging Markets ESG Index Futures', ('7', '8'))
        b = self.m._parse_page(_FakeSgxPage(lines), running_head=None)
        self.assertEqual([r['lab'] for r in b[0]['rows']], [
            'FTSE Emerging Market Index Futures',
            'FTSE Emerging Market inc Korea Net Total Return (USD) Index Futures',
            'FTSE Emerging Markets ESG Index Futures'])

    def test_orphan_text_between_rows_goes_to_nearer_row_only(self):
        """离上一行更近（但 ≥ 9pt，不够挂回去）的文字行，不许被下一行抢走。"""
        lines = [(51.0, 250.0, 'Energy Volume'),
                 (300.0, 280.0, 'Jul 2026'), (360.0, 280.0, 'Aug 2026')]
        lines += _sgx_row(310.0, 'Oil Futures', ('1', '2'))
        lines += [(51.0, 320.0, 'stray note')]            # 离上一行 10pt、离下一行 11pt
        lines += _sgx_row(331.0, 'Oil Swaps', ('3', '4'))
        b = self.m._parse_page(_FakeSgxPage(lines), running_head=None)
        self.assertEqual([r['lab'] for r in b[0]['rows']], ['Oil Futures', 'Oil Swaps'])

    def test_lower_half_only_unchanged(self):
        """老路径：标签与数字同一行、续行在下方 —— 修上半截不能把它改坏。"""
        lines = [(51.0, 300.0, 'Interest Rates Futures Volume'),
                 (300.0, 330.0, 'Jul 2026'), (360.0, 330.0, 'Aug 2026')]
        lines += _sgx_row(360.0, 'SGX FTSE 10-Year Indonesia Government', ('10', '20'))
        lines += [(51.0, 365.5, 'Bond Futures')]
        lines += _sgx_row(382.0, 'Total', ('10', '20'))
        b = self.m._parse_page(_FakeSgxPage(lines), running_head=None)
        self.assertEqual([r['lab'] for r in b[0]['rows']],
                         ['SGX FTSE 10-Year Indonesia Government Bond Futures', 'Total'])
        self.assertIsNone(b[0]['rows'][0].get('lab_head'))

    @unittest.skipUnless(os.path.exists(os.path.join(ROOT, 'cache', 'sgx_2026-08.pdf')),
                         'cache/sgx_2026-08.pdf 不在（cache/ gitignore 且会被 prune）')
    def test_real_pdf_2026_08_matches_hand_count(self):
        """所有者拿官方 PDF 手加的数：IODEX 期货 4,127,939 + IODEX 期货期权 552,512
        + Lump Premium 期货 35,016 + 65% 期货 33,740 = 4,749,207。"""
        blocks = self.m._load_blocks(os.path.join(ROOT, 'cache', 'sgx_2026-08.pdf'))
        self.assertEqual(self.m._read_iron_ore(blocks, self.MON), 4749207)



# ═══════════════════════════════════════════════════════════════════════════
# G. docs/CRON_WIRING.md 的闸门表 vs 代码真值
# ═══════════════════════════════════════════════════════════════════════════
# 这张表是「下一个人查闸门时会去看的地方」，而它漂过：2026-08-30 给 umc / ase 加
# EARLY_BY 那次没回写，表里那两行的闸门（9 / 10）比真值（4 / 8）晚了 5 与 2 天，
# 直到 2026-09-07 才被撞见。文档漂移的坏处不是「不准」，是**它看起来很准** ——
# 有人照着它算余量，得出的结论全是错的，而表本身不会报错。
#
# 判据就是 monthly_run 自己那条算术：闸门 = max(0, LAG − EARLY)。表里两张（§2.2 的
# 13 家交易所、§2.3 的其余 15 家）列数不同，所以按「最后一列 = 闸门」取，而不是按
# 固定下标 —— 后者正是本测试第一版写错的地方。
class TestCronWiringTableMatchesCode(unittest.TestCase):
    def test_every_gate_cell_matches(self):
        import re
        mr, rost = _load_once()
        doc_path = os.path.join(ROOT, 'docs', 'CRON_WIRING.md')
        with open(doc_path, encoding='utf-8') as f:
            doc = f.read()
        bad = []
        for t, lag in sorted(rost.LAG.items()):
            early = mr.EARLY_BY.get(t, (mr.EARLY, mr.EARLY))
            a, b = max(0, lag[0] - early[0]), max(0, lag[1] - early[1])
            m = re.search(r'^\| `' + t + r'`\s*\|(.*)$', doc, re.M)
            if m is None:
                bad.append(f'{t}: 闸门表里没有这一行')
                continue
            cells = [c.strip() for c in m.group(1).split('|')]
            got = cells[-2] if cells[-1] == '' else cells[-1]
            if t in mr.FACT_GATE:
                ok = '事实闸门' in got      # 不吃日历闸门的家，表里必须这么写
            else:
                nums = re.findall(r'\d+', got)
                ok = nums[:1] == [str(a)] if a == b else nums[:2] == [str(a), str(b)]
            if not ok:
                bad.append(f'{t}: 文档写 {got!r}，代码算出 {a}/{b}')
        self.assertEqual(bad, [], '闸门表与代码不一致：\n  ' + '\n  '.join(bad))



# ═══════════════════════════════════════════════════════════════════════════
# H. spike_cap 的端点护栏 —— 盲带哨兵
# ═══════════════════════════════════════════════════════════════════════════
# 这一组守的是一个**潜伏**缺陷：`spike_cap()` 的护栏一度写成 `end_hi > cap`（越界才抬），
# 而引擎真正的失败门槛在**像素**上 —— `assets/charts.js` 的 `spreadY()` 里
# `lo = M.t + 7`，而 `lines_endlabels` 的端点标签落笔在 `Y(值) + 3.2`。末点落在轴顶下方
# 不到 3.8px 时标签跌进 `lo` 之下，触发「从上边界顺排」的兜底：**整列端点标签被重排成
# 一摞**，与各自的线对不上号，而且没有任何东西报错。
# 换算成读数：cap 至少要比末点高约 1.63%（半栏）/ 1.64%（通栏）。`nice_max` 抬完仍落进
# 这条盲带的比例实测 6.37%；末点本身正好是整刻度（150 / 250 / 300 / 400 …）时**必然**触发。
# 现网 9 页一处都没命中，所以这里不能靠真产出当判据 —— 只能注入。
class TestSpikeCapEndGuard(unittest.TestCase):
    """引擎几何复刻 + 盲带注入。判据与 `assets/charts.js` 的行号一一对应。"""

    def setUp(self):
        import single
        self.S = single

    # ── charts.js 的最小复刻（只复刻本条要用的那几行）──
    @staticmethod
    def _spreadY_falls_back(ys, Mt, ph, gap):
        """charts.js:1291 `spreadY()` 的逐行复刻 → 是否走了顶边兜底。"""
        lo, hi = Mt + 7, Mt + ph + 3
        a = sorted(ys)
        for k in range(1, len(a)):
            if a[k] - a[k - 1] < gap:
                a[k] = a[k - 1] + gap
        over = (a[-1] - hi) if a else 0
        if over > 0:
            a = [y - over for y in a]
        return bool(a and a[0] < lo)

    def _endlabels_fall_back(self, ends, cap, y0, fs):
        S = self.S
        Mt = S._fscale(30, fs)                              # charts.js:814（capOn）
        ph = S._plot_h('lines_endlabels', fs, True, None)   # charts.js:783/823
        # charts.js:975 Y(v) + :1517/:1518 的 `+ 3.2`
        ys = [Mt + ph - ((v - y0) / (cap - y0)) * ph + 3.2 for v in ends]
        return self._spreadY_falls_back(ys, Mt, ph, S._fscale(9.6, fs))

    def test_plot_height_matches_engine(self):
        """绘区高：半栏 236.5 / 通栏 235.0（**不是** 268−30=238，FS=1 那一档不存在）。"""
        S = self.S
        self.assertAlmostEqual(S._plot_h('lines_endlabels', S.FS_MIN), 236.5, places=6)
        self.assertAlmostEqual(S._plot_h('lines_endlabels', S.FS_MAX), 235.0, places=6)
        self.assertLess(S._plot_h_min('lines_endlabels'), 235.0)   # 台阶右端更小

    def test_known_blind_band_cases_are_lifted(self):
        """红队实算的四例：末点 149/cap 150、396→400、300→300、250→250。

        判据分两半 —— ① 旧写法（`end_hi > cap`）不抬时引擎**真的**走顶边兜底；
        ② 新护栏解出来的 `need` 高于旧 cap（所以会抬）。
        """
        S = self.S
        head_px = 7 - 3.2
        ph = S._plot_h_min('lines_endlabels')
        for ends, cap in ([149., 20., 8.], 150.), ([396., 120.], 400.), \
                         ([300., 44., 12.], 300.), ([250., 90., 30., 9.], 250.):
            with self.subTest(cap=cap):
                end_hi = max(ends)
                self.assertFalse(end_hi > cap, '这一例本来就不在盲带里，样例选错了')
                for fs in (S.FS_MIN, S.FS_MAX):
                    self.assertTrue(self._endlabels_fall_back(ends, cap, 0.0, fs),
                                    f'cap={cap} FS={fs}：引擎复刻没走顶边兜底，样例失效')
                need = 0.0 + (end_hi - 0.0) / (1 - head_px / ph)
                self.assertGreater(need, cap, f'cap={cap}：新护栏没有抬 —— 盲带回来了')

    def test_integer_tick_endpoint_always_in_band(self):
        """末点本身正好落在 `nice_max` 的整刻度上时，旧写法**必然**留在盲带里。"""
        S = self.S
        ph = S._plot_h_min('lines_endlabels')
        for v in (10, 25, 100, 150, 250, 300, 400, 600, 800, 1000, 2500, 30000):
            with self.subTest(v=v):
                self.assertEqual(float(S.nice_max(v)), float(v))
                self.assertGreater(v / (1 - (7 - 3.2) / ph), float(S.nice_max(v)))

    def test_guard_output_clears_the_band(self):
        """护栏抬完之后，注入的那一批端点全部离顶边够远（引擎复刻不再兜底）。"""
        S = self.S
        head_px, ph = 7 - 3.2, S._plot_h_min('lines_endlabels')
        for end_hi in (149., 250., 298., 396., 1234.5, 98765.):
            with self.subTest(end_hi=end_hi):
                cap = float(S.nice_max(end_hi / (1 - head_px / ph)))
                for fs in (S.FS_MIN, S.FS_MAX):
                    self.assertFalse(
                        self._endlabels_fall_back([end_hi, end_hi * .3, end_hi * .08],
                                                  cap, 0.0, fs),
                        f'end_hi={end_hi} FS={fs}：抬完仍然走顶边兜底')

    def test_real_spike_cap_clears_the_band(self):
        """**注入真的 `spike_cap()`**：末点 298（栅栏内最大值）+ 中段一个 3,000 的尖刺。

        旧护栏给出 `nice_max(298) = 300`，末点离轴顶只剩 0.67% —— 落在盲带里。
        这一条直接把造出来的 exhibit 喂进 `Page.spike_cap()`，拿引擎复刻验它的产出：
        护栏必须把上界抬到兜底门槛之外，而且那一个尖刺仍然是越界点（截轴没白截）。
        """
        S = self.S
        vals = [80 + (i * 7) % 180 for i in range(60)]
        vals[30], vals[-1] = 3000., 298.
        ex = {'n': 4, 'kind': 'lines_endlabels', 'yfloor': 0,
              'xlabels': [f'M{i}' for i in range(60)],
              'series': [{'name': 'A', 'values': [float(v) for v in vals]},
                         {'name': 'B', 'values': [float(40 + (i * 5) % 120)
                                                  for i in range(60)]}]}
        page = S.Page.__new__(S.Page)
        page.ticker, page.cap_ns = 'band', []
        zh = page.spike_cap(4, ex, [{'fmt': 'f0c', 'unit': 'units'}])
        self.assertTrue(zh and ex.get('ycap'), 'spike_cap 没有截轴 —— 样例失效')
        self.assertGreater(ex['ycap'], float(S.nice_max(298.)),
                           '上界停在 nice_max(末点) 上 —— 端点护栏的盲带回来了')
        self.assertEqual([v for s in ex['series'] for v in s['values'] if v > ex['ycap']],
                         [3000.], '越界点不再只是那个尖刺 —— 上界抬过头了')
        ends = [s['values'][0] for s in ex['series']] + \
               [s['values'][-1] for s in ex['series']]
        for fs in (S.FS_MIN, S.FS_MAX):
            self.assertFalse(self._endlabels_fall_back(ends, float(ex['ycap']), 0.0, fs),
                             f'FS={fs}：截完仍然会把整列端点标签重排成一摞')

    def test_spike_cap_rejects_a_third_kind(self):
        """`kind` 不是 lines_endlabels / lines 时必须当场停机（那句 raise 不是死代码）。"""
        S = self.S
        page = S.Page.__new__(S.Page)
        page.ticker = 't'
        with self.assertRaises(S.SpecError):
            page.spike_cap(9, {'kind': 'gs_bar', 'series': [], 'xlabels': []},
                           [{'fmt': 'f0c', 'unit': 'u'}])



# ═══════════════════════════════════════════════════════════════════════════
# I. 2026-09 给 build/single.py 加的三样东西 —— 它们失败时都**不出声**
# ═══════════════════════════════════════════════════════════════════════════
# 判据照 README「第四类：不出声的失败」那一节：
#     「它连续失败十天，和成功十天，在日志里长得一样吗？一样，就缺一道护栏。」
#
# · `no_yoy` 落点守卫：守卫本身若失效，声明被吞、payload 一字不改、rc=0、
#   五道闸门全绿 —— 正是它写出来要消灭的那个形状。而且它在两轮里**被漏了两次**
#   （先漏 decomp 四个列位，再漏「mix 落空时分项回到桶里」这条路由），
#   两次都是人复核抓到的，没有任何自动判据会响。
# · `prior12()`：verify_pages 只查 gs_bar 有没有 `avg12`，**不查值**。
#   切片从 [-13:-1] 改成 [-12:] 照样返回一个数、照样过闸门，虚线悄悄挪一格。
# · `monthly_total(bucket=)`：分岔的是一句印在图注里的口径断言，没有闸门读它；
#   而它的年度支现在**零活体覆盖**（全仓再没有 spec 传 weight_col / *_total_col）。
class TestNoYoyGuard(unittest.TestCase):
    """`no_yoy` 只有 `ex_single` 读得到 —— 写在别处必须硬失败，写对了必须生效。"""

    @classmethod
    def setUpClass(cls):
        import single
        cls.S = single
        cls.spec = single.load_spec('jpx')

    def _spec(self):
        import copy
        return copy.deepcopy(self.spec)

    def test_norm_col_call_sites_still_seven(self):
        """`_norm_col` 的调用点数量 —— 守卫注释自称「共 7 个」，这是那句话的看门人。

        加了第 8 个调用点却忘了扩守卫，是这道守卫最可能的失效方式（已发生过一次：
        decomp 的四个列位就是这么漏的）。用 AST 数，不用 grep —— 注释里出现
        `_norm_col(` 不算调用。
        """
        import ast
        src = open(os.path.join(ROOT, 'build', 'single.py'), encoding='utf-8').read()
        n = sum(1 for node in ast.walk(ast.parse(src))
                if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == '_norm_col')
        self.assertEqual(n, 7,
                         f'_norm_col 的调用点从 7 个变成了 {n} 个 —— '
                         f'新增/删除一个落点时必须同步改 Page.__init__ 里的 no_yoy 守卫'
                         f'与 docs/SINGLE_SPEC.md §4 那一行的**左右两格**')

    def test_blocks_headline(self):
        sp = self._spec()
        sp['headline'][0]['no_yoy'] = True
        with self.assertRaises(self.S.SpecError) as cm:
            self.S.Page(sp)
        self.assertIn('headline', str(cm.exception))

    def test_blocks_stock_col(self):
        sp = self._spec()
        for g in sp['groups']:
            for c in g['cols']:
                if c['col'] == 'mktcap_eom_jpytn':
                    c['no_yoy'] = True
        with self.assertRaises(self.S.SpecError) as cm:
            self.S.Page(sp)
        self.assertIn('stock=True', str(cm.exception))

    def test_blocks_multi_col_bucket(self):
        """2 列以上的同单位桶走 ex_lines / ex_heat，都不读这个开关。"""
        sp = self._spec()
        for g in sp['groups']:
            for c in g['cols']:
                if c['col'] == 'adv_deriv_index_lgeq_kcontracts':
                    c['no_yoy'] = True
        with self.assertRaises(self.S.SpecError):
            self.S.Page(sp)

    def test_blocks_mix_total_and_parts(self):
        sp = self._spec()
        for g in sp['groups']:
            if g.get('mix'):
                for c in g['cols']:
                    if c['col'] == g['mix']['total']:
                        c['no_yoy'] = True
        with self.assertRaises(self.S.SpecError) as cm:
            self.S.Page(sp)
        self.assertIn('mix', str(cm.exception))

    def test_blocks_decomp_columns(self):
        """decomp 的四个列位也走 _norm_col —— 语法上写得进去，而 ex_decomp 不读它。

        漏了这一条时的实测症状：rc=0、payload 逐字节不变、五道闸门全绿。
        """
        for key in ('value', 'qty'):
            with self.subTest(key=key):
                sp = self._spec()
                sp['decomp'][0][key]['no_yoy'] = True
                with self.assertRaises(self.S.SpecError) as cm:
                    self.S.Page(sp)
                self.assertIn('decomp', str(cm.exception))

    def test_blocks_when_mix_may_fall_through(self):
        """mix 那张图没出成时，被「声明扣掉」的分项会回到桶里 —— 桶一超 MAX_LINES
        就走 ex_heat（画同比）。守卫必须按**最坏情形**分桶，不能照抄 payload()
        那份「按真画出来的图扣列」的算法（两处天生不同源）。
        """
        sp = self._spec()
        unit = 'k contracts/day'
        cols = [{'col': c, 'zh': z, 'unit': unit, 'fmt': 'f1'} for c, z in [
            ('adv_deriv_total_raw_kcontracts', 'T'),
            ('adv_deriv_index_raw_kcontracts', 'P1'),
            ('adv_deriv_rates_raw_kcontracts', 'P2'),
            ('adv_deriv_cmdty_raw_kcontracts', 'P3'),
            ('adv_n225_futures_kcontracts', 'P4'),
            ('adv_n225_mini_kcontracts', 'P5'),
            ('adv_topix_futures_kcontracts', 'F'),
        ]]
        cols[-1]['no_yoy'] = True          # ← 只有它带开关，且它不是 mix 的成员
        drop = {'衍生品分类 ADV（原始张数，仅供口径对照）',
                '迷你化：大型合约 vs mini（原始张数）',
                '衍生品总量：大合约当量 vs 原始张数'}
        sp['groups'] = [g for g in sp['groups'] if g['zh'] not in drop]
        sp['groups'].append({'zh': 'G_fallthrough', 'cols': cols, 'mix': {
            'total': 'adv_deriv_total_raw_kcontracts',
            'parts': [c['col'] for c in cols[1:6]],
            'residual_zh': '其他', 'abs_stack': True}})
        with self.assertRaises(self.S.SpecError) as cm:
            self.S.Page(sp)
        self.assertIn('mix 落空', str(cm.exception))

    def test_allows_and_takes_effect_on_single_bucket(self):
        """写对了必须**生效**：撤掉 yoy 与右轴、改画 avg12。只拦不生效等于白拦。"""
        page = self.S.Page(self._spec())
        pay, why = page.payload()
        self.assertIsNotNone(pay, f'jpx payload 没产出来：{why}')
        # `_cols` 是内部字段，落盘前会被剔掉 —— 按标题认这张图。
        ex = [e for e in pay['exhibits']
              if e.get('title', '').endswith('当月公开募集件数')]
        self.assertEqual(len(ex), 1)
        self.assertIsNone(ex[0].get('yoy'))
        self.assertIsNone(ex[0].get('ylab2'))
        self.assertIsNotNone(ex[0].get('avg12'))

    def test_all_live_specs_still_construct(self):
        """过杀的唯一整页护栏：现网每一页都必须还能构造出来。"""
        import glob as _glob
        for f in sorted(_glob.glob(os.path.join(ROOT, 'build', 'specs', '*.py'))):
            t = os.path.splitext(os.path.basename(f))[0]
            if t.startswith('_'):
                continue
            with self.subTest(ticker=t):
                self.S.Page(self.S.load_spec(t))

    def test_bench_absent_does_not_trip_guard(self):
        """不给 bench 时两键归一化成 None —— 守卫的 isinstance 那半句不是冗余。"""
        d = self.S._norm_decomp(
            {k: v for k, v in self.spec['decomp'][0].items()}, 'decomp[0]')
        self.assertIsNone(d['bench_value'])
        self.assertIsNone(d['bench_qty'])
        self.S.Page(self._spec())          # 不抛 TypeError


class TestPrior12(unittest.TestCase):
    """`avg12` 那条虚线的值。verify_pages 只查它在不在，**不查它是多少**。"""

    @classmethod
    def setUpClass(cls):
        import single
        cls.S = single

    def test_slice_is_prior_twelve_not_trailing_twelve(self):
        """口径是「最新月**之前**的 12 个月」= [-13:-1]，不是 [-12:]。

        两种切法都返回一个数、都过闸门，差别只有虚线挪一格 —— 所以这条要同时
        断言「等于前者」与「不等于后者」，把「口径写错也算过」堵死。
        """
        v = [float(i) for i in range(1, 27)]        # 1..26
        got = self.S.prior12(v)
        self.assertAlmostEqual(got, sum(v[-13:-1]) / 12.0, places=9)
        self.assertNotAlmostEqual(got, sum(v[-12:]) / 12.0, places=9)

    def test_excludes_latest_month(self):
        """最新月是 NaN 而之前 12 个月有值 → 仍算得出（定义就是不含最新月）。"""
        import numpy as np
        v = [float(i) for i in range(1, 26)] + [float('nan')]
        self.assertIsNotNone(self.S.prior12(v))
        self.assertTrue(np.isfinite(self.S.prior12(v)))

    def test_all_nan_returns_none(self):
        self.assertIsNone(self.S.prior12([float('nan')] * 20))

    def test_matches_lpla_implementation(self):
        """四处同源：与 build/lpla.py 的 avg_prior12 同口径（同样 round 到 6 位）。"""
        import importlib.util
        sp = importlib.util.spec_from_file_location(
            'lpla_mod', os.path.join(ROOT, 'build', 'lpla.py'))
        try:
            mod = importlib.util.module_from_spec(sp)
            sp.loader.exec_module(mod)
        except Exception:                       # noqa: BLE001
            self.skipTest('build/lpla.py 需要 pandas 之外的依赖，跳过跨实现比对')
        if not hasattr(mod, 'avg_prior12'):
            self.skipTest('build/lpla.py 没有 avg_prior12')
        import pandas as pd
        v = [float(i) * 1.7 for i in range(1, 27)]
        self.assertAlmostEqual(self.S.prior12(v),
                               mod.avg_prior12(pd.Series(v)), places=6)


class TestMonthlyTotalBucket(unittest.TestCase):
    """`monthly_total()` 的口径断言按 bucket 分岔 —— 没有任何闸门读那句话。"""

    @classmethod
    def setUpClass(cls):
        import single
        cls.S = single
        cls.page = single.Page(single.load_spec('jpx'))

    def _how(self, bucket):
        c = {'col': 'adt_cash_dom_stocks_jpytn', 'zh': '内国株成交额',
             'unit': '¥tn/day', 'fmt': 'f1', 'stock': False,
             'scale': 1.0, 'ratio': None, 'no_yoy': False}
        _s, how = self.page.monthly_total(c, None, None, 'daily_avg',
                                          'test', bucket=bucket)
        return how

    def test_monthly_bucket_has_no_equal_weight_warning(self):
        """月度桶一格就是一个月，全程不跨月相加 —— 那句代价在这张图上是假的。"""
        how = self._how('monthly')
        self.assertNotIn('等权', how)          # 年度支那句代价不许出现在月度图上
        self.assertIn('不做任何跨月相加', how)   # 月度支必须把「为什么不需要」说出来
        # 「权重偏差」这四个字在月度支里是被**否定**掉的（「也没有…权重偏差」），
        # 所以不能断言它不出现 —— 只能断言它不是以「带着一个…偏差」的肯定形式出现。
        self.assertNotIn('带一个', how)

    def test_year_bucket_keeps_equal_weight_warning(self):
        """年度桶必须仍然把话说满。两支互斥，否则分岔等于没分。"""
        how = self._how('year')
        self.assertIn('等权', how)

    def test_series_returned_unchanged_in_monthly_bucket(self):
        """月度桶不做任何还原：返回的就是原序列，没乘任何东西。"""
        import numpy as np
        c = {'col': 'adt_cash_dom_stocks_jpytn', 'zh': 'x', 'unit': 'u',
             'fmt': 'f1', 'stock': False, 'scale': 1.0, 'ratio': None,
             'no_yoy': False}
        s, _ = self.page.monthly_total(c, None, None, 'daily_avg',
                                       'test', bucket='monthly')
        base = self.page.ser(c)
        self.assertTrue(np.allclose(s.dropna().values, base.dropna().values))


class TestMixAbsStack(unittest.TestCase):
    """`abs_stack` 的绝对值堆叠：柱高声称等于合计，所以负分项必须硬失败。"""

    @classmethod
    def setUpClass(cls):
        import single
        cls.S = single

    def test_negative_segment_is_rejected(self):
        """引擎把正段自 0 上堆、负段削成零高度不画 ⇒ 柱顶落在正段之和上，
        而「各段之和 = 合计」那道收尾自检**照样通过**（一负一正互相抵消）。
        verify_pages 的负段 ERROR 只覆盖 gs_bar，接不住 stacked_dual。
        """
        page = self.S.Page(self.S.load_spec('jpx'))
        g = [x for x in page.groups if x['zh'] == '东证现货成交'][0]
        i = page.df.index[-1]
        page.df.loc[i, 'adt_cash_etfreit_jpytn'] = \
            -page.df.loc[i, 'adt_cash_etfreit_jpytn']
        page.df.loc[i, 'adt_cash_stocks_jpytn'] = (
            page.df.loc[i, 'adt_cash_total_jpytn']
            - page.df.loc[i, 'adt_cash_etfreit_jpytn'])
        with self.assertRaises(self.S.SpecError) as cm:
            page.mix_pair(9, g)
        self.assertIn('负值', str(cm.exception))

    def test_abs_stack_excludes_rhs_share(self):
        """abs_stack 不出 100% 占比那张 ⇒ rhs_share / share_note 是死配置。"""
        with self.assertRaises(self.S.SpecError):
            self.S._norm_mix({'total': 'a', 'parts': ['b'],
                              'abs_stack': True, 'rhs_share': 'b'}, 'test')


# ═══════════════════════════════════════════════════════════════════════════
# J. exchanges12 的缺月闸门 —— gate_holes()
# ═══════════════════════════════════════════════════════════════════════════
# 2026-09 加。这道闸门原来是「窗口内有洞就整页 raise」，把 /exchanges12/ 从 31c335c
# 起冻了整整四天：ASX 2020-01 的官方印错值被 series/ 那边主动置空，页面却因此再也
# 构建不出来，于是线上那一版**恰好还印着要删掉的那个错值**。改成「登记才放行」之后，
# 放行的口子必须自己有网兜着 —— 它现在是全页唯一能抓到源列损坏的地方。
#
# 四条各守一个方向：未登记的必须炸（口子不能变成默认放行）、登记过的必须放行
#（否则等于没改）、登记但洞已经补上必须炸（页面不能继续解释一个不存在的空格）、
# 病因指错腿必须炸（图注会把空格归给一条其实有值的腿）。
class TestExchanges12HoleGate(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        import pandas as pd
        cls.pd = pd
        import exchanges12 as E
        cls.E = E
        idx = pd.period_range('2019-01', '2019-06', freq='M')
        s = pd.Series(1.0, index=idx)
        holed = s.copy()
        holed[pd.Period('2019-03')] = float('nan')
        # 两个成员各一块；'asx' 的 ASX_ETO 在 2019-03 缺值，'cme' 齐备。
        cls.BLK = {'asx': {'ASX_ETO': holed}, 'cme': {'CME_ALL': s}}
        cls.WHY = ('ASX_ETO', '测试用病因')

    def test_registered_hole_passes(self):
        got = self.E.gate_holes({'asx': ['2019-03']}, self.BLK, 'Jan-19', 'Jun-19',
                                known={('asx', '2019-03'): self.WHY})
        self.assertEqual(got, [('asx', '2019-03')])

    def test_unregistered_hole_raises(self):
        """没登记的洞必须炸 —— 否则这道闸门等于被拆了。"""
        with self.assertRaises(SystemExit) as cm:
            self.E.gate_holes({'asx': ['2019-03']}, self.BLK, 'Jan-19', 'Jun-19', known={})
        self.assertIn('未登记', str(cm.exception))

    def test_stale_registration_raises(self):
        """洞补上了而登记还在 ⇒ 炸，逼人把图注里那句解释一起删掉。"""
        with self.assertRaises(SystemExit) as cm:
            self.E.gate_holes({}, self.BLK, 'Jan-19', 'Jun-19',
                              known={('asx', '2019-03'): self.WHY})
        self.assertIn('已经不是洞', str(cm.exception))

    def test_noncanonical_month_says_format_not_stale(self):
        """月份写成 '2019-3' / Period 时要报格式错，不能报「数据补上了」。

        stale 判据是纯字符串比对，非规范写法会静静落进那个分支，把人指去翻 series/，
        而问题在登记这一行自己的写法上 —— Period 打印出来还和字符串一模一样。
        """
        for bad in ('2019-3', self.pd.Period('2019-03', freq='M')):
            with self.assertRaises(SystemExit) as cm:
                self.E.gate_holes({'asx': ['2019-03']}, self.BLK, 'Jan-19', 'Jun-19',
                                  known={('asx', bad): self.WHY})
            msg = str(cm.exception)
            self.assertIn('YYYY-MM', msg)
            self.assertNotIn('数据补上了', msg)

    def test_reason_pointing_at_a_healthy_block_raises(self):
        """病因指到一条其实有值的腿 ⇒ 炸。图注会照着这个块名点名，指错就是印错话。"""
        BLK = {'asx': {'ASX_ETO': self.BLK['asx']['ASX_ETO'],
                       'ASX_DERIV': self.pd.Series(1.0, index=self.BLK['cme']['CME_ALL'].index)}}
        with self.assertRaises(SystemExit) as cm:
            self.E.gate_holes({'asx': ['2019-03']}, BLK, 'Jan-19', 'Jun-19',
                              known={('asx', '2019-03'): ('ASX_DERIV', '指错腿')})
        self.assertIn('指错了腿', str(cm.exception))


# ═══════════════════════════════════════════════════════════════════════════
# K. exchanges12 的三个同比函数 —— pct_change 不许前向填充
# ═══════════════════════════════════════════════════════════════════════════
# 同一次改动挖出来的真缺陷：pandas ≤ 2.x 的 pct_change 默认 fill_method='pad'，
# 序列中间缺一个月**不会**留空，而是拿上一个月冒充它算出一个假读数 —— 不报错、
# 不留 null。这正是「洞看不出来」的那种坏法，而且它是本页那道 hull 自检
#（加权平均必落在分量 min/max 之间）唯一一次真的被撞响的原因。
# 三个函数各测一次：留空的必须是 null，不能是数。
class TestExchanges12NoPadOnPctChange(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        import pandas as pd
        import exchanges12 as E
        cls.E, cls.pd = E, pd
        idx = pd.period_range('2019-01', '2021-12', freq='M')
        s = pd.Series(range(1, len(idx) + 1), index=idx, dtype=float)
        s[pd.Period('2020-01')] = float('nan')
        cls.s = s

    def test_yoy_leaves_the_hole_empty(self):
        v = self.E.yoy(self.s)
        for m in ('2020-01', '2021-01'):
            self.assertTrue(self.pd.isna(v[self.pd.Period(m)]),
                            f'{m} 被前向填充算出了 {v[self.pd.Period(m)]}')

    def test_mom_leaves_the_hole_empty(self):
        v = self.E.f_mom(self.s)
        for m in ('2020-01', '2020-02'):
            self.assertTrue(self.pd.isna(v[self.pd.Period(m)]),
                            f'{m} 被前向填充算出了 {v[self.pd.Period(m)]}')

    def test_ttm_yoy_leaves_the_hole_empty(self):
        """滚动合计口径上，一格缺值影响其后 12 个月，同比再影响 12 个月。"""
        v = self.E.ttm_yoy(self.s)
        for m in ('2020-12', '2021-01'):
            self.assertTrue(self.pd.isna(v[self.pd.Period(m)]),
                            f'{m} 被前向填充算出了 {v[self.pd.Period(m)]}')


if __name__ == '__main__':
    unittest.main(verbosity=2)
