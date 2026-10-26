# CHANGELOG

`npx skills update` 会整体覆盖安装目录，本文件用于说明每个版本改了什么。

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
