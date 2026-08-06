# -*- coding: utf-8 -*-
"""生成 data/roster.js —— 首页总览与各页顶部导航共用的目录。

内容全部从已生成的 data/<t>.js 里读回来（数据月份、一行数据条），不重算任何数值：
首页上的数字如果是首页自己算的，迟早会与子页对不上而没人发现。

两条刻意的设计：

1. **payload 里不写任何日期。** roster.js 在 data/ 下，而 monthly_run 判断「数据是否
   真的变了」是按忽略首行的正文比较。构建日期一旦进 payload，正文就天天不同，
   幂等检查永久失效 —— 每次例行跑都产出一个内容相同、只有日期变了的 no-op commit，
   还把页面新鲜度刷成当天。日期只留在首行注释里。

2. **红点由浏览器按当天算，不由构建时算。** 「几号该发」（DUE）是口径知识，写在
   Python 侧；但「今天有没有超期」必须用**看页面的那一刻**的日期。若在构建时算死，
   这套东西哪天停跑了，页面会永远显示一片绿 —— 恰恰在最该报警的时候不报警。
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
    'hkex': (10, 10),    # 次月上旬
    'hood': (13, 30),    # 常规月次月 9-13 日；季末月随财报（实测 3 月→4/28、6 月→7/29）
    'schw': (14, 21),    # 非季末月次月 12-14 日；季末月取自当季季报
    'spgi': (16, 46),    # 次月约 15 日；季末月随季报（2025-12 的数据 2026-02 才出）
    'axp':  (16, 16),    # 8-K 每月 15 日前后，撞周末顺延
    'msci': (17, 17),    # 次月中旬
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
    'schw': ('SCHW', 'Charles Schwab', '次月 12-14 日'),
    'lpla': ('LPLA', 'LPL Financial', '次月中下旬'),
    'hood': ('HOOD', 'Robinhood', '次月约 10 日'),
    'cme': ('CME', 'CME Group', '次月第 1-2 个工作日'),
    'cboe': ('CBOE', 'Cboe Global Markets', '次月第 3 个工作日'),
    'hkex': ('HKEX', '香港交易所 0388', '次月上旬'),
    'msci': ('MSCI', 'MSCI Inc.', '次月中旬'),
    'spgi': ('SPGI', 'S&P Global', '次月约 15 日'),
    'axp': ('AXP', 'American Express', '次月约 15 日（8-K）'),
    'tsm': ('TSM', 'TSMC 2330.TW', '次月 10 日前'),
    'exchanges': ('交易所组', 'CME / Cboe / HKEX', '成员齐了才生成'),
    'wealth': ('财富组', 'SCHW / LPLA / IBKR / HOOD', '成员齐了才生成'),
}

GROUPS = [
    ('broker', '券商与财富管理', ['ibkr', 'schw', 'lpla', 'hood']),
    ('exch', '交易所', ['cme', 'cboe', 'hkex']),
    ('data', '数据与指数', ['msci', 'spgi']),
    ('cons', '消费与信贷', ['cost', 'axp']),
    ('semi', '半导体', ['tsm']),
    ('cross', '横截面', ['exchanges', 'wealth']),
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
    for key, label, tickers in GROUPS:
        items = []
        for t in tickers:
            d = read(t)
            if d is None:
                missing.append(t)
                continue
            code, name, cadence = META[t]
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
            groups.append({'key': key, 'label': label, 'items': items})

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
