# CHANGELOG

`npx skills update` 会整体覆盖安装目录，本文件用于说明每个版本改了什么。

## 0.1.0 — 2026-10-26

首个版本：`long-task-session` 技能。

- 六阶段流程（S0 对账 → S1 定界与量噪 → S2 方案与筛选 → S3 夯实 → S4 执行 → S5 验收与沉淀）
- 四份会话文档（SESSION_PLAN / SESSION_LOG / NEXT_PLAN / ARTIFACTS）+ 机器状态 `state.json`
- `sessionctl`：new / list / status / note / ckpt / state / verify / resume / reconcile / close / doctor
- 长任务三件套模板：幂等 launcher、可重挂 watcher（心跳写纯文本文件）、reconciler
- 12 条抽象模式（`references/patterns.md`），不含任何真实项目数据
- 自测 `tests/selftest.sh`：18 组断言 / 41 个检查点，全部通过
