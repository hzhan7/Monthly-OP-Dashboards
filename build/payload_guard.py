# -*- coding: utf-8 -*-
"""CONTRACT.md §5 第 5 条「失败要响 …… 绝不静默写 NaN 上线」的**唯一执行点**。

14 个生成器（12 家 + exchanges + wealth）结尾那段「写首行注释 → 写 window.DASH = →
json.dump」全部换成 `payload_guard.write_dash(path, payload, '<ticker>')`，
写文件之前先把 payload 递归扫一遍。

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
  而英文单词的后续至少 3 个字母 —— 唯二的例外是 `nano` / `info` / `infra` / `infer`
  这类短词，真写进正文会误报一次 FAIL；权衡下宁可误报（响一次、改个措辞）也不放过
  （放过 = 数字错着上线且没人知道）。
已验证：对当前 15 个 data/*.js 命中 0 次。
"""
import datetime
import json
import os
import re

# 见模块头「字符串匹配的误伤边界」。infinity 必须排在 inf 前面，否则 inf 先匹配上再回溯失败。
_BAD = re.compile(r'(?<![A-Za-z_])(?:nan|infinity|inf)(?:[A-Za-z]{1,2})?(?![A-Za-z_])', re.I)


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
        hit = _BAD.search(node)
        if hit:
            i = max(0, hit.start() - 28)
            s = ('…' if i else '') + node[i:hit.end() + 28] + ('…' if hit.end() + 28 < len(node) else '')
            out.append((path, f'展示串里出现 {hit.group(0)!r}：{s}'))


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


def write_dash(path, payload, gen):
    """自检 → 序列化 → 写 data/<gen>.js。14 个生成器写文件一律走这里。

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

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        # 构建日期只写首行注释，不进 payload —— 进了 payload，monthly_run 的
        # 「data 有没有实质变化」检查（忽略首行的正文比较）就永久失效。
        f.write(f'// 由 build/{gen}.py 生成于 {datetime.date.today().isoformat()}，请勿手改\n')
        f.write('window.DASH = ')
        f.write(txt)
        f.write(';\n')
    return path
