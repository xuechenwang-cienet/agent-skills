# CHANGELOG

`npx skills update` 会整体覆盖安装目录，本文件用于说明每个版本改了什么。

版本号按技能独立演进；标题未标技能名的条目属于 `long-task-session`（早期所有条目都是它）。

## tokenplan-enterprise-bailian 0.1.0 — 2026-10-26

从 `cienet-ai/tokenplan-enterprise-bailian-skills` 导入为 `agent-skills` 的顶层技能目录，功能无改动。

- 新目录 `tokenplan-enterprise-bailian/`（24 个文件）：`SKILL.md` + 说明 + `config/*.sample.*` + `scripts/`
  （含 `lib/`、`steps/`、`tools/`）。
- 目录名由 `tokenplan-enterprise-bailian-skills` 改为 `tokenplan-enterprise-bailian`，与 frontmatter
  `name` 及仓库命名约定一致；`SKILL.md` / `README.md` 中 4 处路径引用同步更新。
- 只导入 git 跟踪文件：`config/config.yaml`、`config/members.csv`、`config/state.json`、`output/`、
  `logs/` 不进仓库（技能自带的 `.gitignore` 继续生效）。
## 0.1.6 — 2026-10-26

补齐"起/停"与"回溯"三个缺口，并把产物校验改成与 cwd 无关（跨会话接手必需）。

- **新增 `sessionctl run --stage <id> --cmd … --log …`**：`setsid` 起一条命令并把 `pid/cmd/log` 登记进
  `state.runs`。**新增 `sessionctl stop-run <id>`**：按登记的 pid 精确停（含进程组），
  避免 `pgrep -f … | xargs kill` 误杀执行者自己（本项目踩过两次）。
  `stop-run --mark-only --state stopped|failed|done|stale` 用于没有 pid 的旧登记（例如被宿主杀掉的 watcher）。
- **新增 `status --expect-stage S3|S4`**：这两期"验收表未判定"是预期状态，只允许第 4 项失败；
  匹配时打印 `status: EXPECTED 3/4` 且退出码 0，不再把"计划已冻结、阈值待测"误报成故障。
- **新增 `new --date YYYY-MM-DD`**：回溯/迁移历史会话时目录名用历史日期（配合已有的四份模板与 state）。
- **修复 `status`/`verify` 的 cwd 依赖**：相对产物路径现在依次按 `session/`、仓库根、`cwd/` 解析，
  在哪个目录执行结果都一样（此前换个目录就报"产物不存在"）。
- 自测 86 → **96 条**（仓库口径；安装副本 95 条，差一条为跳过的 README 检查）（run/stop-run、expect-stage、new --date 各一组）。

## 0.1.5 — 2026-10-26

补齐"agent 在环"模式（观察者唤醒 agent、由 agent 判读并决定推进或请示），修掉 pipeline 模板的两个真实 bug。

- **新增 `sessionctl observe`**：观察者"闹钟"。睡到 `marker` / `checkpoint`（默认 40 分钟）/ `stale` / `timeout`
  就退出并打印一行 `OBSERVE event=…`，**不判读、不写 state.json**；退出即把控制权交回 agent。
  退出码：0=marker、3=checkpoint、5=stale、2=timeout、4=自检失败。
  契约：agent 每次唤醒后先 `status`/`resume` 判读，再按 `next_action.decision` 推进或请示，**然后必须重新挂 observe**。
- **新增 `state.next_action.decision`**（`agent` | `user`）：`status`/`resume` 会打印
  `▶ 推进权：agent` 或 `⏸ 推进权在用户`；`decision=user` 时阶段完成后不自动进入下一阶段。
- **`references/delegation.md` 新增 §7「两种判读模式」**：无人值守（子代理判读）vs agent 在环（主 agent 判读），
  含选择规则与三条硬契约（重挂、观察者死亡是正常事件、执行体与观察者分离）。
- **`SKILL.md` 新增「一句话边界」**：明确 Pull（能接上）与 Push（会继续）是两套机制，并写死
  "自动执行到跑完并落盘为止，decision=user 的门仍等交互"。
- **修复 `templates/pipeline.sh` bug A**：阶段表用 `|` 分隔时，进度正则里的 `\|` 会把字段切碎
  （实测 `timeout: invalid time interval ' [0-9]+/[0-9]+ \\[|9000'`）。改为 **制表符分隔**，并在解析阶段对空字段快速失败。
- **修复 `templates/pipeline.sh` bug B**：`wait "$child" 2>/dev/null || true` 会吞掉阶段命令的退出码，
  导致"终态标记已出现但命令失败"的阶段被标 done。改为 `wait` 后检查 `rc`，非零即 `STATUS=fail`。
- 自测从 22 条扩到 **86 条**：新增 observe 的四种事件、写死总量被拒、`decision` 校验与 status 提示、pipeline 阶段表解析。

## 0.1.4 — 2026-10-26

文档修正：把"宿主的后台任务时限"从传闻改成实测事实。无代码改动、无 schema 改动。

- `references/long-running.md` 新增 §2.1「宿主限制与版本差异」：opencode ≤2.0.x 的
  **60 分钟空闲驱逐**（与运行时长无关，SIGTERM + 完成通知丢失，issue #51828）、
  ≥2.1.3 的修复（PR #57416 / `experimental.location_idle_timeout`）、以及
  "升级或重启宿主会杀全部托管后台 shell"这条跨版本规则；并说明 watcher 的
  "窗口 ≤2 小时"是可重挂性设计，不是宿主上限。
- `references/delegation.md` 兜底表补两行：宿主升级/重启、宿主空闲驱逐。
- 结论未变：`setsid` + 状态落盘 + 可重挂 watcher 仍是唯一稳妥做法。

## 0.1.3 — 2026-10-26

监视环节的"自证可用" + 上下文降载。向后兼容（不改 schema、既有会话无需迁移）。

- **`sessionctl watch`（新）**：包装 watcher 模板；启动前用两份夹具日志做**上岗自检**——
  正则必须能抓到与批次无关的 `| 5/207 [...]`，写死总量（如 `/172`）会直接拒绝启动（exit 4）
  并给出定向提示。`--selftest-only` 可单独跑（<10 秒）。
- **`templates/watcher.sh`**：新增失速检测 `STALE_LIMIT`（默认 3）→ 心跳追加
  `note=stale_progress`；`FAIL_ON_STALE=N` 达到阈值以**退出码 5** 结束；头注释明确
  "总步数/总量不要写死"。
- **`sessionctl status`**：心跳行新增"假推进体检"——声明了 `progress_regex` 但最近一次
  `progress=-` 时给出 ⚠ 提示。
- **`sessionctl ckpt --progress-regex`**：把进度正则记进 `runs[]`，供 status 体检。
- **`templates/pipeline.sh`（新）**：多阶段管道模板（幂等 done 标记、失败短路、单行通知契约）。
- **`references/delegation.md`（新）**：托管监控——等待交给管道、判读交给子代理、单行通知契约、
  子代理 prompt 模板与兜底规则。
- **patterns.md**：新增第 16 条"监视器写死总量"（按 16 条同步计数）；
  `long-running.md` / `SKILL.md` 补自检与失速规则。
- 自测：新增 W1–W4（自检通过 / 写死被拒 / 失速记录 / 退出码 5）→ 76 个检查点全绿。

## 0.1.2 — 2026-10-26

两处可用性改进，向后兼容（不改 schema、不改退出码语义）。

- 目录产物：`ckpt` 登记目录时直接打印可复制的打包 + 重新登记命令（含 session 与脚本绝对路径）；
  `status`/`verify` 的提示补上"建议打包后用 ckpt 登记归档文件，才能被校验"。
- `list`：默认首行打印 `root: <绝对路径>`（表格保持窄）；新增 `--paths`，只输出绝对路径、一行一个，
  便于 `$(sessionctl list --paths | tail -1)` 取最新会话。
- 文档：`references/documents.md` §4 补"目录产物规则"；`SKILL.md` 快速开始补 `list --paths`。
- 自测：30 组 → 32 组断言 / 71 个检查点（新增目录产物打包命令、list 输出两种模式）。

## 0.1.1 — 2026-10-26

修复实测发现的 4 个 bug + 7 处小问题，并补 5 条健壮性改动。向后兼容：不改 `state.json` schema、
不改命令面、无需迁移既有会话。

**Bug**
- B1 目录产物导致 `verify`/`status`/`resume` 崩（`IsADirectoryError`）：哈希前先判目录，
  目录在 `ARTIFACTS.md` 记为 `dir` 并输出"目录产物"提示；`sha256_file` 对目录显式报错。
- B2 `close --backup`（文档教的用法）因 argparse 必带值而报错：改为 `nargs="?"`，缺值时用
  `SESSION_BACKUP_DIR` 或默认目录。
- B3 `templates/launcher.sh` 在 early-signal 成功路径上因 `${_ }` 报 `bad substitution`：循环变量改名并修正输出。
- B4 `templates/launcher.sh` 的 `STRICT_IDEMPOTENT` 用 `NAME` 做 pgrep，首跑必然自匹配被拒：
  删除该启发式，幂等只信 PIDFILE。

**小问题**
- S1 `ckpt` 同名重复登记会双写 `runs[]` 与 `ARTIFACTS.md`：改为同产物 skip、异产物报错。
- S2 删除 `close` 里创建后从不使用的 `session/backup/`。
- S3 `close` 归档后 `stage` 推进到 `S5`。
- S4 `blockers` 未校验类型，字符串会被逐字拆开渲染：写入端要求字符串数组（`--json`），渲染端兼容历史字符串。
- S5 文档计数与实际不符（12 → 15 条模式：12 主 + 3 变体）。
- S6 `resume --prompt` 恒返回 0：改为与 `verify` 一致（产物校验失败返回 1，文本仍打印）。
- S7 计划正文里合法的 `{{`（如代码示例）被误报占位符：改用 `\{\{[A-Z_][A-Z0-9_]*\}\}` 精确匹配。

**健壮性补充**
- N1 `close` 归档前跑完四项检查（plan/state/产物/验收），任一失败即拒绝；`--force` 可跳过并记入日志。
- N2 watcher 的进度改写为单行并限长 120 字，避免心跳行被多行污染。
- N3 会话创建行与 `note` 记录统一为 `HH:MM:SS+08:00 (epoch)` 短格式。
- N4 自测新增目录产物、`--backup` 无值、launcher 实跑、`ckpt` 去重、stage 推进、blockers、
  `{{` 误报、`close` 全检查、watcher 消毒、`resume --prompt` 退出码等用例。
- N5 发布流程改为 scoped 重装（`npx skills add … -s long-task-session`），避免 `update -g` 连带更新其它技能。

**自测**：18 组 → 30 组断言 / 67 个检查点，全绿。

## 0.1.0 — 2026-10-26

首个版本：`long-task-session` 技能。

- 六阶段流程（S0 对账 → S1 定界与量噪 → S2 方案与筛选 → S3 夯实 → S4 执行 → S5 验收与沉淀）
- 四份会话文档（SESSION_PLAN / SESSION_LOG / NEXT_PLAN / ARTIFACTS）+ 机器状态 `state.json`
- `sessionctl`：new / list / status / note / ckpt / state / verify / resume / reconcile / close / doctor
- 长任务三件套模板：幂等 launcher、可重挂 watcher（心跳写纯文本文件）、reconciler
- 15 条抽象模式（12 主 + 3 变体，`references/patterns.md`），不含任何真实项目数据
- 自测 `tests/selftest.sh`：18 组断言 / 41 个检查点，全部通过
