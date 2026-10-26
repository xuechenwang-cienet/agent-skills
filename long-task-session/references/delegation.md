# 托管监控：把等待交给管道，把判读交给子代理

> 目标：**主会话的上下文成本与任务时长脱钩**。一次 6 小时实验，主会话只应看到一行结论。

## 1. 三层结构

| 层 | 谁来做 | 放在哪 | 主会话成本 |
|---|---|---|---|
| 执行 | `pipeline.sh`（`setsid nohup`，脱离会话存活） | `sessions/<slug>/` | 0（启动时一次） |
| 监视 | `sessionctl watch`（模板 + 上岗自检 + 失速检测） | 每阶段一个，心跳进 `logs/heartbeat.log` | 0（心跳不进上下文） |
| 判读 | 子代理（读结果、算判定、写三张表） | `sessions/<slug>/SESSION_LOG.md` | 一行结论 |

**磁盘状态是唯一事实**：`state.json` + `heartbeat.log` + 阶段 done 标记 + 产物 sha256。
子代理、后台任务、当前会话都可以被回收，任何新上下文用 `reconcile` / `resume --prompt` 接上。

## 2. 为什么不把"等"交给子代理

历史实测（v3 期）：**子代理监控会提前返回**，不能作为"等到结束"的唯一机制。
子代理适合做**判读**（读文件、算阈值、写文档），不适合做**等待**（它自己也活在会被回收的会话里）。

因此：

- 等待 → `pipeline.sh`（脱离会话）+ `sessionctl watch`（心跳文件）
- 判读 → 子代理，且要求它**只回一行**

## 3. 单行通知契约

管道最后一行的格式固定，调用方只取这一行：

```
PIPELINE status=ok stages_done=3 failed_at=- session=/path/to/session 2026-10-26 15:52:10
```

启动方式（stdout 重定向到文件，会话断了也不影响）：

```bash
setsid nohup bash sessions/<slug>/pipeline.sh sessions/<slug> \
  > sessions/<slug>/logs/pipeline.out 2>&1 &
# 之后任何时刻：tail -1 sessions/<slug>/logs/pipeline.out
```

如需"完成时提醒"，再挂一个**只有 3 行**的通知器（这是唯一允许的后台任务）：

```bash
while ! grep -q '^PIPELINE' sessions/<slug>/logs/pipeline.out; do sleep 60; done
tail -1 sessions/<slug>/logs/pipeline.out
```

注意：通知器**不做判读**，只转发那一行；它死掉也不影响管道（状态在文件里）。

## 4. 子代理 prompt 模板（判读型）

```text
你是判读员。只读文件，不要重跑实验，不要改实验数据。

输入：
  1) sessions/<slug>/verdict.json      （管道产出的指标）
  2) sessions/<slug>/state.json        （gates 的阈值）
  3) sessions/<slug>/SESSION_PLAN.md §5（预注册判定规则）

任务：
  - 逐 gate 填 pass/fail/neutral（用 sessionctl state gates.<name>.verdict …）；
  - 把 SESSION_LOG.md 的四个验收小节填满（通过/不通过/中性/Gap 归因）；
  - 跑 status，直到 4/4；
  - 回复**只允许一行**：VERDICT <n>/<N> PASS <三个关键数字>

禁止：修改 SESSION_PLAN.md 的阈值；解释"接近通过"；引用未在 verdict.json 出现的数字。
```

主会话拿到的就是那一行；细节都在文件里，需要时再读。

## 5. 兜底规则

| 情况 | 处理 |
|---|---|
| 会话被回收、管道还在跑 | 重新开会话 → `sessionctl reconcile`（看心跳 mtime 与阶段标记） |
| 通知器死了 | 不影响管道；重挂通知器或直接 `tail -1` |
| 心跳停滞 | `status` 会出现 `⚠ 最近一次失速`；`sessionctl watch` 的自检与 `STALE_LIMIT` 是两层防线 |
| 管道中途失败 | 最后一行 `status=fail failed_at=<stage>`；`.stage-*.done` 标记保证重跑从断点继续 |
| 子代理提前返回 | 以磁盘状态为准：重开子代理只做判读，不重新等待 |

## 6. 反模式

1. 每阶段手写一个 watcher（必写错：写死总量、用百分比判断终态）。
2. 让子代理"盯着直到结束"（会提前返回，且会话回收即失联）。
3. 把心跳内容当作主会话的必读信息（心跳是给机器和排障看的，不是给上下文看的）。
4. 通知器里做判读（判读要读很多文件，正好是最费上下文的部分，应隔离在子代理里）。