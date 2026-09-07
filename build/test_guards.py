# -*- coding: utf-8 -*-
"""build/payload_guard.py + build/brief.py + build/single.py 三条护栏的单元测试。

跑法: python3 build/test_guards.py        （只用标准库 + numpy，不需要 pytest）

这套测试是为「把 MOPS 官方增减原因原文写进 brief」那次改造建的，守两件事（A、B 组）；
2026-09 加了第三件（D 组，`spike_cap()` 的端点护栏），理由写在那一组的组头上 ——
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
# D. spike_cap 的端点护栏 —— 盲带哨兵
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


if __name__ == '__main__':
    unittest.main(verbosity=2)
