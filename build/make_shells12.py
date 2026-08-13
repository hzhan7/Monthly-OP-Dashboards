# -*- coding: utf-8 -*-
"""生成 12 家扩容版新增页面的 index.html 外壳：5 张横截面页 + `build/specs/` 下每一家。

这些页与现有 14 页共用同一份外壳模板 —— 模板**直接从 build/make_shells.py 导入**，
不在这里复制一份：复制出来的第二份模板迟早与第一份分叉（改版式时只改到其中一处），
而两份外壳长得八成像、差异只在某个 div 的 id 上，肉眼比对根本发现不了。

    exchanges12    12 家总览（原设计里的 /exchanges/ 总览，改挂新路径）
    exchanges-na   北美竞争（ICE / Cboe / MIAX / NDAQ，TMX 对照）
    exchanges-eu   欧洲现货竞争（ENX / Cboe-EU / DB1，Nasdaq 北欧只做绝对值对照）
    exchanges-apac 亚太横截面（HKEX / JPX / SGX / ASX）—— **不画跨市场份额**，
                   四家法域隔离、几乎零替代性，分母只能是自己圈的；争夺只在产品级可测

外加 9 家新交易所的单公司页（ice / ndaq / miax / tmx / enx / db1 / jpx / sgx / asx）。
它们的名单**不写死在本文件里**，而是扫 `build/specs/` 得到 —— 理由见 singles()。

`exchanges-eu` 与 `exchanges-apac` 曾是一张合页 `exchanges-intl`（欧洲与亚太）里的两半，
2026-08-06 拆分完成后合页已删除，本脚本不再为它铺壳。拆的理由是口径而不是版面：
欧洲三家争的是同一批订单流，占比有内容；亚太几家法域隔离，占比没有外部指涉。
删除那张页的实际步骤见 docs/DELIVERY.md §4.4。

**/exchanges/（CME / Cboe / HKEX 三家版）已于 2026-08-07 删除。** 老 13 页仍由 make_shells.py
负责，本脚本的 TICKERS 里也没有它 —— 两张页在过渡期并存，等 12 家版跑稳之后再谈迁移。

外壳里没有任何页面专属内容：抬头、标题、口径说明、exhibit 全部由 data/<t>.js 注入，
渲染逻辑在 assets/page.js。所以本脚本的输出只跟目录名有关，重跑幂等（无日期、无计数）。

**规范是「目录名 = data 文件名 = payload 里的 ticker」三者逐字相同** —— roster.py 生成的
导航链接是 `../<ticker>/`，ticker 与目录名一旦分叉，导航就会指向一个不存在的目录。

但本轮实际落地的 build 脚本用的是下划线名（`build/exchanges_na.py` → `data/exchanges_na.js`，
payload 里 `ticker: 'exchanges_na'`），而页面路径按任务规定是连字符的 `/exchanges-na/`。
在两边统一之前，本脚本按「data/ 里真实存在哪个文件」来决定壳里写哪个 src：
连字符版存在就用它，否则回落到下划线版，并在输出里把这次回落打出来。
这样壳不会因为对面改名而静默 404 —— 对面定下来之后重跑一次本脚本即可自愈。

用法: python3 build/make_shells12.py
"""
import importlib.util
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# 横截面页的目录名。顺序即导航顺序，也是本脚本的输出顺序。
CROSS = ['exchanges12', 'exchanges-na', 'exchanges-eu', 'exchanges-apac',
         'exchanges-products']


def singles():
    """9 家新交易所的目录名 = `build/specs/` 下有几份配置就有几个，**不另列清单**。

    单公司页的一家 = 一份 `build/specs/<t>.py`（见 docs/SINGLE_SPEC.md §0）。
    在这里再抄一份名单，等于给「删得干净」这条前提加一个必然被忘掉的同步点：
    删了 spec 却留着这里的名字，本脚本会给一个再也不会有数据的 ticker 铺一张空壳，
    而空壳打开是「缺少 data/*.js」——看上去像是数据坏了，不像是没删干净。

    （壳目录本身要人去 `rm -rf`：本脚本只写不删，不会替人判断一个目录该不该消失。）
    """
    # 枚举源是**两个**目录的并集，不是只有 specs/：
    #   build/specs/<t>.py    → build/single.py 那条路（10 家交易所）
    #   build/mrspecs/<t>.py  → build/mrbase.py 那条路（7 家台湾半导体，TSM 图列）
    # 2026-08 接入 mrbase 之后只扫 specs/ 会漏掉后者。漏掉的后果不是报错而是
    # **静默少铺 6 张壳** —— 已提交的 index.html 不会消失，所以平时看不出来，
    # 只有改版式重铺时才会发现 6 页停在旧版式。tsm 不在这里，它的壳由
    # build/make_shells.py 的硬编码 TICKERS 兜着（历史原因，两处都要在才算齐）。
    out = []
    for sub in ('specs', 'mrspecs'):
        d = os.path.join(HERE, sub)
        if not os.path.isdir(d):
            continue
        out += [f[:-3] for f in os.listdir(d)
                if f.endswith('.py') and not f.startswith('_')]
    return sorted(dict.fromkeys(out))


TICKERS = CROSS + singles()


def shell_template():
    """从 make_shells.py 取同一份 SHELL 模板（按路径 import，不依赖 sys.path）。"""
    spec = importlib.util.spec_from_file_location(
        'make_shells', os.path.join(HERE, 'make_shells.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)          # 模块顶层只有常量与函数定义，import 无副作用
    return mod.SHELL


def data_src(t):
    """→ (壳里要写的 data 文件名, 回落说明或 None)。规则见模块 docstring。"""
    canon, alt = f'{t}.js', t.replace('-', '_') + '.js'
    if canon == alt or os.path.exists(os.path.join(ROOT, 'data', canon)):
        return canon, None
    if os.path.exists(os.path.join(ROOT, 'data', alt)):
        return alt, f'data/{canon} 不存在，回落到 data/{alt}（build 脚本用的是下划线名）'
    return canon, None                       # 两个都没有：仍按规范写，等 payload 生成


def main():
    shell = shell_template()
    print('写出 %d 个页面外壳：' % len(TICKERS))
    for t in TICKERS:
        src, fallback = data_src(t)
        d = os.path.join(ROOT, t)
        os.makedirs(d, exist_ok=True)
        # 模板里 {t} 同时用在 <title> 与 data 的 src 上；src 要能与目录名不同，
        # 所以先按目录名铺开，再单独把那一行的文件名换掉。
        html = shell.format(t=t).replace(f'../data/{t}.js', f'../data/{src}')
        with open(os.path.join(d, 'index.html'), 'w', encoding='utf-8') as f:
            f.write(html)
        exists = os.path.exists(os.path.join(ROOT, 'data', src))
        print('  %-16s → data/%-22s %s%s'
              % (t + '/', src, '已生成' if exists else '⚠️ 尚未生成',
                 '\n      ⚠️ ' + fallback if fallback else ''))


if __name__ == '__main__':
    main()
