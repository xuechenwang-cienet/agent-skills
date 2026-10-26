# 长任务执行规范

目标：**任务可以无人值守地跑，也可以在任意时刻被一个新上下文接手。**

前提认知：agent 不在场时无法执行任何"每 40 分钟写一次"的规则。所以三条机制分工：

| 层 | 负责 | 机制 |
|---|---|---|
| 长进程 | 不受会话影响 | `setsid`/`nohup` 脱离会话，输出固定日志 |
| watcher | 记录过程 | 每分钟把心跳写进 `logs/heartbeat.log`（纯文本追加，无锁） |
| agent | 同步状态 | 每次交互先 `sessionctl status` / `resume`，再决定下一步 |

**完成判定不看通知，看产物**：终态标记 + 产物哈希 + `state.json` 三方一致。

---

## 1. launcher 规范

`templates/launcher.sh` 提供骨架。硬要求：

1. **幂等**：已在跑就直接退出 0（用 pidfile 或 `pgrep -f` 精确匹配，见反模式 5）。
2. **前置自检**：输入文件/目录存在、配置项齐全、依赖可用、端口空闲、设备空闲；
   任一不满足 → 打印原因并退出非零。
3. **固定日志**：`logs/<run-id>.log`，同时把 `started_at` 与 `terminal_marker` 登记进 `state.json`。
4. **脱离会话**：`setsid nohup <cmd> >> logs/<run-id>.log 2>&1 < /dev/null &`。
5. **失败可见**：启动后 N 秒内做一次"早期信号"检查（进程存活 + 日志非空 + 无已知致命串）。

---

## 2. watcher 规范

`templates/watcher.sh` 提供骨架。**优先用 `sessionctl watch` 启动它**：该命令会先用两份夹具日志
做上岗自检（<10 秒）——正则抓不到 `| 5/207 [...]` 这类通用进度行时直接拒绝启动（exit 4），
避免"心跳一直在写但内容永远错"的假存活。`--selftest-only` 可单独跑自检。

硬要求：

1. **心跳**：每 `INTERVAL`（默认 60s）追加一行到 `logs/heartbeat.log`：

   ```
   <epoch> <本地时间+偏移> run=<id> pid=<pid|-> progress=<当前进度原文或 -> marker=<0|1>
   ```

2. **终态绑定真实标志**：由参数 `TERMINAL_REGEX` 指定（如 `train_runtime`、`全部完成`），
   **不要**用"输出里出现 100%"——别的阶段也会打印同名百分比（权重加载、预处理都会）。
3. **窗口 ≤2 小时**：到点退出码 3 并打印"重新挂载"命令；watcher 是临时工具，可无限次重挂。
   （窗口是**可重挂性**的设计选择，不是宿主强制的上限——见 §2.1。）
4. **死亡判定**：进程消失但终态未出现 → 退出码 2，并写一行 `death` 心跳。
5. **不写 JSON**：心跳只写纯文本，`state.json` 只由 `sessionctl ckpt/state` 更新。
6. **正则只匹配形状**：进度条写 `| [0-9]+/[0-9]+ \[`，**禁止写死总量**（`| [0-9]+/172 \[`）。
   不同批次数据量不同，写死会让心跳 10 分钟停在 `progress=-` 而无人察觉。
7. **失速检测**：`STALE_LIMIT`（默认 3）次心跳进度不变 → 心跳追加 `note=stale_progress`；
   `FAIL_ON_STALE=N` 时以退出码 5 结束。`sessionctl status` 会把"声明了正则但 progress=-"标出来。

---

## 2.1 宿主限制与版本差异（实测）

不同 harness 对后台进程的存活条件不同，写 watcher 前先确认当前宿主属于哪一类：

| 宿主 | 行为 | 对策 |
|---|---|---|
| opencode ≤ 2.0.x | 位置（location）**60 分钟无会话活动**即被驱逐，其托管的后台 shell 收到 SIGTERM（`rc=143`），输出文件被删、完成通知丢失。**与运行时长无关**，只看空闲时间 | 长任务用 `setsid nohup` 脱离会话；心跳落文件；会话保持活跃只能延缓 |
| opencode ≥ 2.1.3 | 有后台任务在跑的位置不再被驱逐（issue #51828 / PR #57416），空闲 TTL 可用 `experimental.location_idle_timeout` 调整 | 可用 `background: true` 直接托管；跨重启仍需脱离会话 |
| 任意 harness | **升级或重启宿主会杀掉全部托管后台 shell** | 长进程与 watcher 一律可重挂；状态只认磁盘 |

由此得到两条不受版本影响的硬规则：

1. **长进程必须 `setsid`**（`nohup` 只挡 SIGHUP，挡不住 SIGTERM）；
2. **状态必须落盘**（`state.json` + 心跳 + 阶段 done 标记），进程与 agent 都是耗材。

## 3. reconciler 规范

接手时按顺序跑，任何一项不符都要写进日志：

```bash
sessionctl list --root ./sessions          # 有没有更新的会话
sessionctl reconcile --root ./sessions     # 上一轮的摘要
sessionctl status --session <dir>          # plan/state/产物/验收四检
sessionctl resume --session <dir> --prompt # 可直接粘贴的开场白
```

手工核对四项：进程是否存活、服务端口是否响应、GPU/磁盘是否被占、输入数据版本是否变化。

---

## 4. 40 分钟检查点

长任务运行期间，**每 40 分钟至少一条记录**（`sessionctl note`），内容可以是：

- 进度（含从日志抓到的原文进度行）
- 资源（显存/磁盘/配额）
- 异常（重试、告警、超时）

不允许"等它跑完再一次性写"：harness 可能在任何时刻切断，事后补写的日志会丢失因果顺序。

---

## 5. 五条反模式

| 反模式 | 后果 | 正确做法 |
|---|---|---|
| 用副作用字符串判完成（如输出里的百分比） | 误报完成，后续步骤基于空产物继续 | 终态锚定真实标志 + 产物哈希 |
| 把"进程还在"当健康 | 空转/死锁无法发现 | 心跳 + 里程碑检查点 |
| watcher 绑死当前对话 | 对话一断就没人看，状态丢失 | 可重挂；状态以文件为准 |
| 进度正则写死总量 | 换批次后心跳恒为 `progress=-`，假存活 | `sessionctl watch` 上岗自检 + 只匹配形状 |
| 直接相信远端/容器时间戳 | 时区/时钟偏移导致误判进度 | 一律 epoch + 产物 mtime |
| `pkill -f "<含自身命令行的串>"` | 杀掉执行命令的 shell 自身 | 用 `pgrep -f '[p]attern'` 取 PID，或只按 PID；且与启动命令分开执行 |

---

## 6. 备份（close 时）

1. `logs/` + `artifacts/` 打包：有 `zstd` 用 `tar.zst`，否则自动降级 `tar.gz`。
2. 生成 `<包名>.sha256`，与包同目录。
3. 备份包路径写回 `ARTIFACTS.md` 的"备份位置"列与 `NEXT_PLAN.md`。
4. 默认落盘 `~/backups/agent-sessions/`；`close --backup`（不带值）用默认目录，`close --backup <dir>`
   或环境变量 `SESSION_BACKUP_DIR` 覆盖；
   `--remote user@host:/path` 时额外 `rsync`，并记录远端路径。
5. 大文件（如模型权重）若不适合打包，用 `ckpt --sha256 <hex>` 登记调用方算好的哈希，
   并在 `ARTIFACTS.md` 里注明"外部存储 + 未本地校验"。