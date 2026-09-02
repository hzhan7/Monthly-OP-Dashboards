# -*- coding: utf-8 -*-
"""CONTRACT.md §5 第 5 条「失败要响 …… 绝不静默写 NaN 上线」的**唯一执行点**。

**所有**生成器（各家的 build/<t>.py，以及 build/single.py 与 build/mrbase.py 这两个带
一批页的底座）结尾那段「写首行注释 → 写 window.DASH = → json.dump」全部换成
`payload_guard.write_dash(path, payload, '<ticker>')`，写文件之前先把 payload 递归扫一遍。
这里不写死生成器个数：原文写的是「14 个生成器（12 家 + exchanges + wealth）」，
页数一扩就不成立了，而没有任何东西在守那个数字 —— 要知道有谁在走这条路，
`grep -rl write_dash build/`。

## 为什么护栏放在写出端，而不是读 CSV 那一端

缺值只是众多入口之一：除以 0 基数、窗口不足 12 个月、季度对不齐，都能在派生计算里
凭空造出 NaN。读取端堵不干净，写出端是所有路径的唯一汇合点，一处见效。

## 拦什么、不拦什么

**拦** —— 只拦「算错了」的产物：
  1. float NaN / ±Infinity。json.dump 默认 allow_nan=True，会写出裸 `NaN` 字面量：
     那不是合法 JSON，但 `window.DASH = ` 是 JS 求值，浏览器照单全收，于是坏 payload
     一路上线而退出码仍是 0。
  2. 已经被 f-string 格式化进展示串的 `nan` / `inf`（`f'{float("nan"):+.1f}%'` → `'nan%'`）。
     这一类比 (1) 更常见也更隐蔽 —— 它在 JSON 层面完全合法，headline / hub_line 里
     印出 `客户资产 $nanbn（+nan% y/y）`，还会经 hub_line 传进首页卡片。
     tsm 原来那段大小写敏感的 `'NaN' in txt` 子串检查抓得住 (1)，抓不住 (2)。

**不拦** —— `null` 是这套数据模型的合法值，一刀切禁掉会把现在能跑的好几家直接跑挂：
  · 缺月（序列中间的洞，规矩 3 要求断开而不是直连）
  · 未满季被作废的 y/y / 季度桥
  · Cboe 的 RPC 滞后一个月发布、HKEX 的 new_listings 月中才披露 —— 最新月本来就空
  · year_lines / seasonality 的当年行天然只填到当月（尾部一串 null 是常态；
    spgi Exhibit 6 甚至有一整行全 null 的年份）
  所以这里只管「结果里有没有 NaN」，对走 L()/LN() 转成 null 的合法留空零影响。

**「最新月关键字段为空」怎么办**：不在这里另立一条规则。实测（对 12 家逐列清空最新行
后重跑生成器）表明，任何一个真·关键字段一空，派生计算立刻产出 NaN 或 `nan` 展示串，
被上面两条抓住；而那些清空后仍能干净跑完的列，本来就是页面允许缺的（合法 null）。
再加一条「最新月不许空」的白名单式检查，只会把这些合法留空误伤成 FAIL。

## 字符串匹配的误伤边界（这里是唯一有讲究的地方）

只在**左侧**卡词边界不行：`f'${nan:,.0f}bn'` 出来的是 `$nanbn`，`nan` 右边紧跟单位字母。
两侧都卡词边界也不行 —— 那正是漏掉 `$nanbn` `nanmn` `$nantn` `nank` `+nanpp` 的原因
（实测：全部 26 个「清空最新行某列」的复现场景里，只有 ibkr 少数几处是裸 NaN，
其余都是这种「数字 + 单位」的展示串）。

所以规则是「左边必须是非字母，右边最多再吃 1-2 个字母」：
    (?<![A-Za-z_])(nan|infinity|inf)(?:[A-Za-z]{1,2})?(?![A-Za-z_])
  命中：`nan%` `$nanbn` `nanmn/日` `$nantn` `nank` `+nanpp` `-inf`
  不命中：`inflection` `information` `inflows` `influence` `infrastructure` `nanometer`
          `financial`（左边是字母）
  取 1-2 个字母是因为格式化单位都很短（bn / mn / tn / k / bp / pp / x），
  而英文单词的后续至少 3 个字母。

## 尾字母那 1-2 格：只认**我们自己的单位**，不认「凡是 1-2 个字母」

上面那条规则原样用会误伤一批**正好长成「词干 + 1-2 个字母」的英文短词**：
`nano` `info` `infra` `infer` `NAND`。模块最初的权衡是「宁可误报也不放过」，
那个权衡的前提是这些词**不会**出现在正文里 —— 2026-08 引入「把 MOPS 官方
增减原因原文写进 brief」之后前提没了：南亚科是 DRAM 厂、世芯是 ASIC 厂，
公司自己填的备注原文里出现 `NAND` / `HBM` / `AI` 完全正常，而备注原文
**改不了措辞**（改了就不是原文），误报一次 = 整页发不出去且无解。

放宽的方式不是把尾字母数改小或去掉（那会漏掉 `$nanbn` 这一整类真事故），
而是**把「1-2 个任意字母」换成「1-2 个字母且必须是本仓格式器真的会输出的单位」**：

    尾部为空        → 一律拦。`nan%` `nan（` `-inf` `inf` `infinity` `$nan` 全在这一支，
                      因为坏值右边跟的是 `%`、全角标点、`/日` 这类**非字母**。
    尾部 ∈ _UNITS   → 拦。`$nanbn` `nanmn` `$nantn` `nank` `+naNpp` `nanbp` `nanx`。
    尾部 ∉ _UNITS   → 放。`nano`(o) `info`(o) `infra`(ra) `infer`(er) `nanya`(ya)。

判据换了个方向，这是关键：原来是「英文词的默认命运是被拦，除非它被人工登记成
专有名词」（拒绝清单式，而英文词是**开集**，永远登记不完）；现在是「只有当尾字母
恰好是**我们自己格式器输出的单位**时才拦」—— 而单位是**闭集**，它由本仓的 f-string
决定，不由英语决定。新加一个单位后缀的人必须同步加进 `_UNITS`，那是一条查得到、
管得住的规矩；要求所有人预先登记全世界的英文短词则不是。

_UNITS 的取值是实测出来的：扫 build/ + fetch/ + tools/ 的全部 f-string，取「格式化
占位符 `}` 右边紧跟的 1-2 个 ASCII 字母」，得到 pp / bn / bp / mn / k / px / x / tn /
b / c / m / q / s / d / f / y / yr，全部收进来；另按对称补一个 `t`（b/m 的单字母写法
都在，`t` 现在没人用但迟早有人写）。宁可多收：多收一个单位只是多拦一种不存在的坏串，
漏收一个单位才会放走真事故。

已验证：对当前 35 个 data/*.js 全量重扫命中 0 次；必须拦 / 必须放的两组用例见
build/test_guards.py（`python3 build/test_guards.py`）。
"""
import datetime
import json
import os
import re

# 见模块头「字符串匹配的误伤边界」。infinity 必须排在 inf 前面，否则 inf 先匹配上再回溯失败。
# 尾字母仍然按 1-2 个抓（要抓住 `$nanbn`），但抓到之后由 _UNITS 判是不是**我们的单位**，
# 所以单独分组 —— 见模块头「尾字母那 1-2 格」。
_BAD = re.compile(r'(?<![A-Za-z_])(nan|infinity|inf)([A-Za-z]{1,2})?(?![A-Za-z_])', re.I)

# 本仓格式器真的会输出的单位后缀（实测自 build/ + fetch/ + tools/ 的全部 f-string：
# 取格式化占位符 `}` 右边紧跟的 1-2 个 ASCII 字母）。**新增一个单位后缀必须同步加进来**，
# 否则那个单位下的 `nan` 会被当成英文词放行 —— 这是本表唯一的失效方式。
#   bn/mn/tn 十亿/百万/万亿  b/m/t 同上的单字母写法   k 千   pp/bp 百分点/基点
#   x 倍数   px 像素   c 美分   q 季   s 秒   d 天   yr 年   y 年（`3Y %ile`）
#   f 来自 `.{dec}f` 这类格式串本身，一并收
_UNITS = frozenset({'bn', 'mn', 'tn', 'b', 'm', 't', 'k', 'pp', 'bp',
                    'x', 'px', 'c', 'q', 's', 'd', 'yr', 'y', 'f'})

# 残余碰撞的人工放行清单：**整词**既长成「nan/inf + 1-2 个字母」、尾字母又恰好落在
# _UNITS 里的真实词。_UNITS 那条规则已经把 nano / info / infra / infer / nanya 自动放掉了，
# 这里只剩下真正撞车的：
#   · `nand`（NAND 闪存）—— 尾字母 `d` 撞上「天」这个单位。NAND 是存储器类型名，
#     南亚科（DRAM）与世芯（ASIC）的图注、页注、以及**公司自己填的 MOPS 备注原文**里
#     都会出现，而备注原文改了就不是原文，改措辞解决不了。
#     反向确认过它不可能是格式化产物：`d` 这个后缀在本仓只出现在 fetch 侧的一句
#     `print(f'+{lag}d')` 日志里，那条路径根本不进 payload。
#   · `nanya`（南亚科的 ticker，2408.TW）—— _UNITS 规则下 `ya` 不是单位、已自动放行，
#     仍显式留在表里：它出现在 payload.ticker / title / source / footer 等 9 处，
#     是本仓对这条规则依赖最重的一个词，写出来比让它隐式通过更查得到。
#
# 放行判据必须是**整词逐字相等**，不是「包含」：
#   · 反过来，`$nanbn` / `nan%` / `+nanpp` 这些真·坏串一个都不在这张表里，照样被拦。
# 加词的门槛：只有当某个**整词**同时满足「是专有名词或固定术语」「尾字母撞了 _UNITS」
# 与「不可能由 f-string 造出来」时才允许加，并在这里写清是哪一家、为什么改不了措辞。
_ALLOW_WORDS = frozenset({'nanya', 'nand'})


class PayloadGuardError(SystemExit):
    """既是异常也是非零退出 —— raise 出来只打一行原因、exit 1，
    与 cme / tsm / hkex 原有的 `raise SystemExit(...)` 行为一致，
    monthly_run.py 那边看到的仍然是「子进程 returncode != 0 → 记 FAIL」。"""


def _where(payload, path):
    """给路径补一句人话定位：落在 exhibits[i] 里就带上该图的编号与标题。"""
    if not path.startswith('exhibits['):
        return ''
    try:
        i = int(path[len('exhibits['):path.index(']')])
        ex = payload['exhibits'][i]
    except Exception:
        return ''
    n, title = ex.get('n'), ex.get('title', '')
    return f'（Exhibit {n}：{title}）' if n is not None else f'（{title}）'


def _scan(node, path, out):
    """递归扫 payload，把每个非法值记成 (路径, 说明)。"""
    if isinstance(node, dict):
        for k, v in node.items():
            _scan(v, f'{path}.{k}' if path else str(k), out)
    elif isinstance(node, (list, tuple)):
        for i, v in enumerate(node):
            _scan(v, f'{path}[{i}]', out)
    elif isinstance(node, float):
        # bool 是 int 的子类、不是 float，不会误入这一支；np.float64 是 float 子类，会。
        if node != node:
            out.append((path, 'NaN'))
        elif node in (float('inf'), float('-inf')):
            out.append((path, f'{node}'))
    elif isinstance(node, str):
        # finditer 而不是 search：放行了一处还要继续往后扫，
        # 否则 '南亚科…$nanbn'、'NAND 需求回升…$nanbn' 这种「放行词在前、坏串在后」
        # 会被整串放过。**放行是逐匹配的决定，永远不是整串的决定。**
        for hit in _BAD.finditer(node):
            tail = (hit.group(2) or '').lower()
            # 见模块头「尾字母那 1-2 格」：尾部为空 → 一律拦；
            # 尾部不是本仓的单位 → 这是个英文词（nano / info / infra / nanya），放行。
            if tail and tail not in _UNITS:
                continue
            # 尾字母确实撞上了单位，再看它是不是那几个人工登记过的整词（NAND 撞 `d`）。
            if hit.group(0).lower() in _ALLOW_WORDS:
                continue
            i = max(0, hit.start() - 28)
            s = ('…' if i else '') + node[i:hit.end() + 28] + ('…' if hit.end() + 28 < len(node) else '')
            out.append((path, f'展示串里出现 {hit.group(0)!r}：{s}'))
            break


def check(payload):
    """扫一遍 payload；有问题就抛 PayloadGuardError，报文里逐条给出路径。"""
    bad = []
    _scan(payload, '', bad)
    if bad:
        lines = '\n'.join(f'  · {p}{_where(payload, p)} → {why}' for p, why in bad[:20])
        more = f'\n  …… 另有 {len(bad) - 20} 处' if len(bad) > 20 else ''
        raise PayloadGuardError(
            f'payload 里出现 NaN / Infinity，拒绝写出（CONTRACT.md §5 第 5 条）；'
            f'共 {len(bad)} 处：\n{lines}{more}\n'
            f'  缺值请走 L()/LN() 输出 null（合法），NaN 说明算错了或解析出了问题。')


def body_of(text):
    """去掉 data/*.js 首行的构建日期注释，只留数据正文。

    **全仓唯一实现。** monthly_run.data_changed() 判「data/ 有没有实质变化」、
    本文件的 write_dash() 与 build/roster.py 判「要不要落盘」，必须共用这一套口径。
    两处各写一份，一旦漂移就会造出「构建器认为没变所以不写、data_changed 认为
    变了」（或反之）的夹缝 —— 那是真正的漏发风险，比它要解决的脏文件问题严重得多。
    """
    return text.split('\n', 1)[1].strip() if '\n' in text else ''


def unchanged(path, body):
    """磁盘上已有文件的正文是否与将要写的 `body` 逐字相同。

    读不出 / 不存在 / 编码坏 一律返回 False —— **fail-open，宁可多写一次也不要漏写**。
    """
    try:
        with open(path, encoding='utf-8') as f:
            return body_of(f.read()) == body.strip()
    except Exception:                                # noqa: BLE001 —— 任何异常都当「变了」
        return False


def write_dash(path, payload, gen):
    """自检 → 序列化 → 写 data/<gen>.js。**所有**生成器写文件一律走这里（见模块 docstring）。

    path    输出文件绝对路径（data/<gen>.js）
    payload window.DASH 的内容
    gen     生成器名（= ticker），只用于首行注释与报错前缀
    """
    try:
        check(payload)
    except PayloadGuardError as e:
        raise PayloadGuardError(f'build/{gen}.py: {e}')

    # allow_nan=False 是第二道闸：万一将来 payload 里塞进 _scan 没覆盖的数值类型，
    # 这里也会 ValueError 而不是写出裸 NaN 字面量。
    txt = json.dumps(payload, ensure_ascii=False, separators=(',', ':'), allow_nan=False)

    body = f'window.DASH = {txt};'

    # 正文一个字节都没变就**不落盘** —— 否则每个 NOTHING_TO_DO 日跑完都会留下一批
    # 只有首行日期不同的未提交改动（实测 7 个），它们既发不出去（data_changed() 按
    # 正文比较，正确判定「无实质变化」），又会在第二方推到同名文件时让下一轮的
    # `git merge --ff-only` 以「would be overwritten by merge」失败、整跑 FAILED。
    # 首行日期因此停在「该正文真正生成的那天」，比每天刷成今天更诚实，也与
    # monthly_run.py:482-487 与 README.md「幂等」节写明的设计意图同向。
    if unchanged(path, body):
        return path

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        # 构建日期只写首行注释，不进 payload —— 进了 payload，monthly_run 的
        # 「data 有没有实质变化」检查（忽略首行的正文比较）就永久失效。
        f.write(f'// 由 build/{gen}.py 生成于 {datetime.date.today().isoformat()}，请勿手改\n')
        f.write(body)
        f.write('\n')
    return path
