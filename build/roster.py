# -*- coding: utf-8 -*-
"""生成 data/roster.js —— 首页总览与各页顶部导航共用的目录。

内容全部从已生成的 data/<t>.js 里读回来（数据月份、一行数据条），不重算任何数值：
首页上的数字如果是首页自己算的，迟早会与子页对不上而没人发现。

三条刻意的设计：

1. **payload 里不写任何日期。** roster.js 在 data/ 下，而 monthly_run 判断「数据是否
   真的变了」是按忽略首行的正文比较。构建日期一旦进 payload，正文就天天不同，
   幂等检查永久失效 —— 每次例行跑都产出一个内容相同、只有日期变了的 no-op commit，
   还把页面新鲜度刷成当天。日期只留在首行注释里。

2. **红点由浏览器按当天算，不由构建时算。** 「几号该发」（DUE）是口径知识，写在
   Python 侧；但「今天有没有超期」必须用**看页面的那一刻**的日期。若在构建时算死，
   这套东西哪天停跑了，页面会永远显示一片绿 —— 恰恰在最该报警的时候不报警。

3. **导航排成几行由这里定，不交给 CSS 自动折行。** 每个 group 带一个 `row`，
   assets/page.js 照它把导航铺成几条独立的行。交易所从 3 家扩到十几家之后，
   靠 `flex-wrap` 折行的断点会随窗口宽度乱跳，谁跟谁一组就读不出来了
   —— 分组标签还在，分组信息没了（详见 GROUPS 的注释）。
"""
import datetime
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, 'data')

# 各家「某个月的数据，通常在该月结束后第几天发布」= (常规月, 季末月)。
# 用「月末后第几天」而不是「次月第几号」，是因为四家公司的**季末月（3/6/9/12）没有独立
# 月报**，数值随当季财报一起出，比常规月晚 2-4 周 —— 用同一个日子判断，每个季度都会
# 误报一次红点。红点每季度假一次，人就学会无视它了，那还不如不做。
# 数值取自各 fetch/<t>.py docstring 里的实测发布日，不是公司承诺；宁可给宽一点。
LAG = {
    'cme':  (2, 2),      # 次月第 1-2 个工作日
    'ibkr': (2, 2),      # 次月首个美股交易日
    'cboe': (4, 4),      # 次月第 3 个美股交易日
    'cost': (7, 7),      # 零售月结束后首个周三
    'tsm':  (10, 10),    # 台湾法定次月 10 日前
    # GUC 的实际节奏比法定上限快得多：官方 IR 财务日历逐条预告「次月 5 日 14:00」，
    # 实测 2025-12→01/05、2026-01→02/05、2026-03→04/07、2026-04→05/05、
    # 2026-05→06/05、2026-06→07/06、2026-07→08/05，遇假日顺延到下一个工作日。
    # 取 7 = 顺延最坏情形（2026-03 那期撞清明连假落到 4/7）。
    'guc':  (7, 7),      # 次月 5 日 14:00（公司财务日历预告值），撞假日顺延
    'hkex': (10, 10),    # 次月上旬
    'hood': (13, 30),    # 常规月次月 9-13 日；季末月随财报（实测 3 月→4/28、6 月→7/29）
    'schw': (14, 21),    # 非季末月次月 12-14 日；季末月取自当季季报
    # SPGI 季末月的 46 天是照**最慢**那次定的（2025-12 → 2026-02-10，第 41 天），
    # 故意不改小。实测三季分别是第 14 / 31 / 41 天（见 fetch/spgi.py docstring），
    # 跨度 27 天：红点必须盖住最慢那次，否则每有一个慢季就假红一次。
    # 快的那一季不会因此漏抓 —— 下载闸门另有 monthly_run.EARLY_BY['spgi']=(5,33)
    # 把开闸日压到第 13 天。两处口径不同是**刻意的**，别为了「一致」把它们并回去。
    'spgi': (16, 46),    # 次月约 15 日；季末月 14-41 天不等
    'axp':  (16, 16),    # 8-K 每月 15 日前后，撞周末顺延
    'msci': (17, 17),    # 次月中旬
    # ── 9 家新增交易所（2026-08 接入）—— 一家一行，删掉一家就删掉它这一行 ──────
    # 数值取自各 fetch/<t>.py docstring 的「发布节奏」实测统计，不是公司承诺。
    # ⚠ **LAG 要跟着「哪条腿决定这一页的 data_through」走，不是跟着最快那条腿走。**
    #    多源的四家（ndaq / tmx / db1 / miax）由 build/specs/<t>.py 的 headline 列
    #    决定 data_through；拿快腿的日子当 LAG，红点会在慢腿到达之前每月假红几天。
    'db1':  (5, 5),      # 头条是 Eurex 快腿，次月 1-5 日（Clearstream 等慢腿在 slow_cols 里）
    'ice':  (6, 6),      # 次月第 3 个美股交易日；124 期实测落在 3-6 号，最晚 6 号无例外
    'tmx':  (6, 6),      # 头条是 MX 腿，次月第 1-4 个工作日（2026 年 7 期实测日历第 1-4 天）
    'miax': (8, 8),      # 次月第 3-5 个工作日；4 期实测日历第 3/5/5/7 天，最坏排列落到第 8 天
    'jpx':  (8, 8),      # 每月第 5 个营业日；1 号撞周六 + 假期时最晚落在 8 号
    'asx':  (8, 8),      # 次月第 3-8 个日历日，众数第 5-6；财年 6 月末**没有**季末月例外
    # LSEG 有四条腿，节奏差一个数量级（LSE 订单簿近期中位 +21 天、Main Market/AIM +1~9、
    # LCH +3~4、Tradeweb +2~8）。头条列在 **Tradeweb 腿**（build/specs/lseg.py），
    # 所以照上面那条「跟决定 data_through 的腿走」的规矩，LAG 只能照 Tradeweb 定：
    # 88 期实测第 2-11 天，2021 起 n=65 收敛到第 2-8 天、中位第 5，8 = 那 65 期的最晚值。
    # 另三条腿在 slow_cols 里，靠下一轮回补，它们的滞后写在页尾口径说明里、不进这里
    # —— 拿 +21 当 LAG 会让整页每月晚 18 天上线，且今天 data_through 就要退回 2026-06。
    # 月度活动报告独立于季报，季末月与常规月无系统差异，两位写同一个值。
    'lseg': (8, 8),      # 头条是 Tradeweb 快腿，次月第 2-8 天（LSE 订单簿等慢腿在 slow_cols 里）
    'enx':  (13, 13),    # 90 期逐月实测第 3-13 天、中位第 7；最晚 2024-04 数据 → 2024-05-13
    'sgx':  (13, 13),    # 95 期实测中位第 9 天；13 覆盖到实测那一档的最晚值
    # NDAQ 的两条腿差一个多星期，而 build/specs/ndaq.py 把头条放在**慢腿**上：
    # share_us_cash_matched_* 来自 Monthly Market Activity（官方自述次月第 10 个工作日，
    # 实测 2026-06 数据 → 2026-07-13）。IR 快腿次月第 2-6 天就出，但它填的不是头条列，
    # 不推进 data_through —— 照快腿填 (6, 9) 会让 NDAQ 每个月假红 2-5 天。
    # 16 = 第 10 个工作日在最坏排列（月末撞周五 + 中间一个假期）下的日历日上界。
    'ndaq': (16, 16),
    # LPLA 的季末月不是「随季报」——fetch/lpla.py 只认 Historical File，**明确不从季报推算**
    # （季报只给季度合计，倒挤 NNA 有 ±0.1 误差，8 个季度里 6 个对不上）。而季末月的官方原值
    # 要等**下一个月**的 Historical File 才出现，所以比常规月整整晚一个发布周期：
    # 6 月数据随 7 月报走，7 月报发在 8 月 16-21 日 → 6/30 + 52 天。
    # 原来写 32（≈随季报的节奏）短了 19 天，代价是每季度红点假红两周、闸门空跑三周。
    'lpla': (21, 52),    # 常规月次月 16-21 日；季末月随**下一个月**的月报，再晚一个月
}
GRACE = 5          # 到期后再宽限几天才判红

META = {
    'cost': ('COST', 'Costco', '零售月结束后首个周三'),
    'ibkr': ('IBKR', 'Interactive Brokers', '次月首个美股交易日'),
    # 这四家季末月（3/6/9/12）没有独立月报，节奏另算 —— 标签里必须写出来。
    # 不写的话，页面显示「次月中下旬」而 LPLA 停在两个月前，看的人只会以为是坏了
    # （实际发生过：用户看到「LPLA 还是 5 月」来问是不是没更新）。
    'schw': ('SCHW', 'Charles Schwab', '次月 12-14 日；季末月随当季季报'),
    'lpla': ('LPLA', 'LPL Financial', '次月 16-21 日；季末月随下一个月的月报，再晚一个月'),
    'hood': ('HOOD', 'Robinhood', '次月 9-13 日；季末月随当季财报'),
    'cme': ('CME', 'CME Group', '次月第 1-2 个工作日'),
    'cboe': ('CBOE', 'Cboe Global Markets', '次月第 3 个工作日'),
    'hkex': ('HKEX', '香港交易所 0388', '次月上旬'),
    'msci': ('MSCI', 'MSCI Inc.', '次月中旬'),
    'spgi': ('SPGI', 'S&P Global', '次月约 15 日；季末月随当季季报'),
    'axp': ('AXP', 'American Express', '次月约 15 日（8-K）'),
    'tsm': ('TSM', 'TSMC 2330.TW', '次月 10 日前'),
    'guc': ('GUC', '创意电子 3443.TW', '次月 5 日（公司日历预告），撞假日顺延'),
    # 9 家新增交易所 —— 一家一行，cadence 与上面 LAG 的实测统计同源
    'ice':  ('ICE', 'Intercontinental Exchange', '次月第 3 个美股交易日'),
    'ndaq': ('NDAQ', 'Nasdaq', '份额腿次月第 10 个工作日（IR 腿第 2-6 天）'),
    'miax': ('MIAX', 'Miami International Holdings', '次月第 3-5 个工作日'),
    'tmx':  ('TMX', 'TMX Group', '次月第 1-4 个工作日（MX 腿）'),
    'enx':  ('ENX', 'Euronext', '次月第 3-13 天，中位第 7'),
    'db1':  ('DB1', 'Deutsche Börse', '次月 1-5 日（Eurex 腿）'),
    'lseg': ('LSEG', 'London Stock Exchange Group', '次月第 2-8 天（Tradeweb 腿）；'
                                                   'LSE 订单簿等腿晚 2-3 周回补'),
    'jpx':  ('JPX', 'Japan Exchange Group', '次月第 5 个营业日'),
    'sgx':  ('SGX', 'Singapore Exchange', '次月第 6-13 天，中位第 9'),
    'asx':  ('ASX', 'ASX Limited', '次月第 3-8 天，众数第 5-6'),
    'wealth': ('财富组', 'SCHW / LPLA / IBKR / HOOD', '成员齐了才生成'),
    'exchanges12': ('12 家总览', '12 家交易所 · 定基名义额', '成员齐了才生成'),
    'exchanges-na': ('北美', 'ICE / Cboe / MIAX / Nasdaq（TMX 对照）', '成员齐了才生成'),
    'exchanges-eu': ('欧洲', 'Euronext / Cboe Europe / Deutsche Börse', '成员齐了才生成'),
    'exchanges-apac': ('亚太', 'HKEX / JPX / SGX / ASX', '成员齐了才生成'),
    'exchanges-products': ('标的轴', '利率 / 股指 / 单股ETF期权 / 能源 / 农产品 / FX 即期',
                           '成员齐了才生成'),
}

# 13 家交易所，**一行一条**。按地理排：北美 6 → 欧洲 3 → 亚太 4，
# 与三张区域横截面页（exchanges-na / -eu / -apac）的分组读法一致。
# 删掉一家 = 删掉这里这一行 + 另外四样东西，完整清单见 docs/CRON_WIRING.md。
EXCH = [
    'cme',     # 美国    CME Group
    'cboe',    # 美国    Cboe Global Markets
    'ice',     # 美国    Intercontinental Exchange（含 NYSE）
    'ndaq',    # 美国    Nasdaq
    'miax',    # 美国    Miami International Holdings
    'tmx',     # 加拿大  TMX Group（TSX + Montréal Exchange）
    'enx',     # 欧洲    Euronext
    'db1',     # 欧洲    Deutsche Börse（Eurex + FWB + Clearstream）
    'lseg',    # 欧洲    London Stock Exchange Group（LSE + Turquoise + Tradeweb + LCH）
    'hkex',    # 亚太    香港交易所 0388
    'jpx',     # 亚太    Japan Exchange Group
    'sgx',     # 亚太    Singapore Exchange
    'asx',     # 亚太    ASX Limited
]

# (key, nav_row, 标签, 成员)
#
# `nav_row` 决定顶部导航把这一组排在**第几行**；同一行号的组按本表先后排在同一行。
# **交易所独占第 2 行**是用户明确要求的，理由不是审美：这一组从 3 家扩到十几家之后，
# 与别的组挤在同一条 flex 里会折成三四行，而折行位置随窗口宽度变 —— 谁跟谁一组
# 就完全读不出来了，导航的分组信息等于白给。给它单独一行，13 个 ticker 永远整齐成排。
#
# 本表同时是**首页卡片**的分组顺序（首页忽略 nav_row，见 index.html）。两处共用一份
# 清单是刻意的：分成两份的话，加一家页面时必然只改到其中一处。
GROUPS = [
    ('broker', 1, '券商与财富管理', ['ibkr', 'schw', 'lpla', 'hood']),
    ('exch', 2, '交易所', EXCH),
    ('data', 1, '数据与指数', ['msci', 'spgi']),
    ('cons', 1, '消费与信贷', ['cost', 'axp']),
    ('semi', 1, '半导体', ['tsm', 'guc']),
    # 横截面页也独占一行（第 3 行）：6 张页跟在半导体后面同样会把第 1 行撑破。
    # （原本这里还有一个 exchanges-intl 欧亚合页，是 exchanges-eu / -apac 拆分前的旧版。
    #   2026-08-06 已删除，实测的删除步骤见 docs/DELIVERY.md §4.4。）
    ('cross', 3, '横截面', ['exchanges12', 'exchanges-na', 'exchanges-eu',
                            'exchanges-apac',
                            'exchanges-products',
                            'wealth']),
]


def read(t):
    """读回 data/<t>.js 的 payload。文件不存在返回 None（该家还没建好）。"""
    p = os.path.join(DATA, f'{t}.js')
    if not os.path.exists(p):
        return None
    with open(p, encoding='utf-8') as f:
        txt = f.read()
    return json.loads(txt[txt.index('{'):txt.rindex('}') + 1])


def main():
    today = datetime.date.today()
    groups, missing = [], []
    for key, nav_row, label, tickers in GROUPS:
        items = []
        for t in tickers:
            d = read(t)
            if d is None:
                missing.append(t)
                continue
            meta = META.get(t)
            if meta is None:
                # 删一家时只删了 META 那一行、忘了 GROUPS 这一行的典型症状。
                # 裸 KeyError 只会打印一个 'sgx'，看不出该去哪儿补，所以在这里说清楚。
                raise KeyError(f'META 里没有 {t!r} —— GROUPS 与 META 必须同增同删'
                               f'（删一家的完整清单见 docs/CRON_WIRING.md）')
            code, name, cadence = meta
            lag = LAG.get(t)
            items.append({
                'ticker': t, 'label': code, 'name': name, 'cadence': cadence,
                # lag=None 的（横截面页）没有自己的披露节奏，页面一律不判超期
                'lag': list(lag) if lag else None,
                'through': d.get('data_through'),
                'through_label': d.get('through_label') or d.get('data_through'),
                'headline': d.get('hub_line') or d.get('headline', '')[:110],
            })
        if items:
            # row 给顶部导航分行用（assets/page.js 的 nav()）；首页 index.html 忽略它。
            groups.append({'key': key, 'row': nav_row, 'label': label, 'items': items})

    payload = {
        'grace': GRACE,
        'groups': groups,
        # 不要在这里链回 costco-monthly-sales / ibkr-monthly-metrics 两个旧仓：
        # 它们的内容已整体并入本仓，旧仓会被删除，链过去就是 404。
        # 项目名写全称 monthly-op-dashboards（旧稿写成 monthly-op-charts，是笔误）；
        # 也不再提「各 skill 的解析管道」—— 解析全部在本仓 fetch/ 下，那两个 skill 已删除。
        'footer': ('数据与算法源自本机 <code>monthly-op-dashboards</code> 项目 · '
                   '每张图右上角可切「表格」视图逐条核对原值 · '
                   '仅供个人研究，不构成投资建议'),
    }
    os.makedirs(DATA, exist_ok=True)
    with open(os.path.join(DATA, 'roster.js'), 'w', encoding='utf-8') as f:
        # 日期只写首行注释 —— 见模块 docstring 第 1 条。
        f.write(f'// 由 build/roster.py 生成于 {today.isoformat()}，请勿手改\n')
        f.write('window.ROSTER = ')
        json.dump(payload, f, ensure_ascii=False, separators=(',', ':'))
        f.write(';\n')
    n = sum(len(g['items']) for g in groups)
    print(f'roster: {n} 页' + (f'，缺 {missing}' if missing else ''))


if __name__ == '__main__':
    main()
