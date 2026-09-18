# 本仓工作约定

2026-09-19 所有者定，适用于交互会话。每日定时任务（monthly_run.py，自动提交并推送数据）照它自己的任务书跑，下面「不推送」那条不管它。其余规矩与来龙去脉见 README.md。

## 做事方式
- 不开 ultracode，不起 Workflow。
- 小改动单线程做，不派 agent，包括重排、删图、改刻度、改图注、合并分支。
- 只有彼此独立的活才派 agent（比如几份一手申报同时考古），同时最多 2–3 个。
- 同一页同一时间只让一个会话或 agent 改。
- 开工先 `git merge --ff-only main`，别在过期基线上改。
- 指图用**标题**，不用图号。派工单、memory、提交信息里也一样，因为图号会随重排变。
- **挪图 = 改一张顺序表**：单页生成器改文件头的 `ORDER`；single.py / mrbase 的页改 spec 里的 `order`。
  正文引用图号写 `⟨ex:id⟩`，别写死数字；写法见 build/exhibits.py 文件头。
  动手前可以先用 `python3 tools/exhibit_check.py drill <页> a,b` 在不改文件的情况下预演一遍。
- 图表就是模版加数据。刻度、字体这类不影响阅读的小问题不花大力气；数字错才是大事。
- 页面上的数一律用**官方公布值**。自算值和官方值不一致时，页面用官方值，把差异写进给所有者的总结。

## 做完之后
- 做完**默认合并到本地 main**，不问要不要 commit 或 push。
- **不推远端。**所有者审完自己手动 push；他明说「push up」时才推。
- 合并后先跑 `python3 tools/rebuild.py`。`data/*.js` 是生成物，冲突了不要手挑哪边，重建后再 `git add data/`。
- 再跑 `python3 tools/gate.py`，约 30 秒，末行是 `GATE OK` 才算做完。

## worktree
- `cache/` 不入库，目前只有 build/ibkr.py 读它。新 worktree 里先拷一份：`cp -cR ~/Projects/monthly-op-dashboards/cache/ibkr cache/`
- `.claude/launch.json` 的端口是入库的。为躲端口冲突临时改过的话，提交前改回去。
