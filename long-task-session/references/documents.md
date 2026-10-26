# 会话文档规范

四份文档 + 一个机器状态文件。`status` 的检查**只认固定小节标题**（不做语义解析），
所以标题必须逐字一致。

---

## 0. 无记忆读者写作要求（最重要）

接手的人可能是一个**完全没有上下文的新模型**。所以：

1. **禁止指代**：不写"上面那个""刚才的问题""如前所述"，每条记录自带主语。
2. **命令完整可粘贴**：写全参数与路径（相对路径以会话目录为基准，或写绝对路径）。
3. **时间双写**：本地时间带偏移 + epoch 秒，例如 `2026-10-26T10:31:02+08:00 (1761445862)`。
   远端与容器时钟可能偏移，epoch 是唯一不会说谎的。
4. **结论可判定**：写"X 从 A 变到 B，阈值 C，判定：通过/不通过/中性"，不写"效果不错"。
5. **只写增量**：不重复前文已有的事实；需要引用时写文件名 + 小节名。

---

## 1. `SESSION_PLAN.md`（冻结；只追加修订）

必须包含以下八个二级标题，逐字一致：

```
## 1. 问题
## 2. 当前证据
## 3. 候选方案与裁决
## 4. 单变量表
## 5. 预注册判定
## 6. 成本与资源
## 7. 回退点
## 8. 决策记录（DECISIONS）
```

### 4. 单变量表（格式固定）

| 维度 | 参考版本 | 本次 | 是否变化 |
|---|---|---|---|
| <维度名> | <值> | <值> | 否 |
| <维度名> | <值> | <值> | **是（唯一）** |

规则：**"是"最多一个**。若必须改两个，把第二个拆到下一轮（或在 `DECISIONS` 里记录为什么接受不可归因）。

### 5. 预注册判定（格式固定）

| 指标 | 阈值 | 判定规则 | 噪声带 | 不达标动作 |
|---|---|---|---|---|
| <指标> | ≥/≤ <值> | 差值在 ±<2×SE> 内记中性并加跑一轮 | n=<n>, SE=<值> | <回退到什么> |

规则：阈值在收数据前写死；事后只允许"通过 / 不通过 / 中性"。

### 8. 决策记录（只追加）

| 编号 | 决定 | 理由 | 被否方案 | 否决依据 |
|---|---|---|---|---|
| D1 | <决定> | <理由> | <方案> | <哪条模式 / 哪个实测> |

已写入的决策不改写；如需推翻，追加一条 `D<n>` 并写"取代 D<k>"。

---

## 2. `SESSION_LOG.md`（追加式）

### 2.1 顶部状态块（由 `sessionctl` 重写，不要手工编辑）

```markdown
<!-- STATE:BEGIN -->
（sessionctl 生成：阶段、模式、进行中 run、最后心跳、下一条命令、阻塞）
<!-- STATE:END -->
```

新上下文只读这一块就能知道"现在在哪、下一步做什么"。

### 2.2 记录格式

```
- 10:31:02 +08:00 (1761445862) · <动作> · 证据: <命令或产物路径> · 结果: <实测> · 决策: <结论> [key:<去重键>]
```

`sessionctl note` 生成的行即为此格式；`--key` 用于重入去重（同一 key 只写一次）。

### 2.3 CKPT 格式（不可再生动作完成后必须写）

```
### CKPT <name> · 2026-10-26T10:31:02+08:00 (1761445862)
- 产物: <路径>
- sha256: <hex>（source: local | caller）
- 大小: <bytes>
- 验证: sha256sum <路径>
```

`source: caller` 表示哈希由调用方提供（例如 root-only 的远端产物），`verify` 对它只做"已记录"检查，不判失败。

### 2.4 结尾四个标题（逐字一致，`close` 会检查非空）

```
## 验收：通过
## 验收：不通过
## 验收：中性
## Gap 归因
```

每个小节要么有表格/条目，要么写"无"。**中性不等于通过**：落在噪声带内的结果必须写进"中性"。

---

## 3. `NEXT_PLAN.md`（交接唯一入口）

必须包含：

```
## 1. 已完成
## 2. 未完成
## 3. 未解问题
## 4. 下阶段候选
## 5. 不要做什么
## 6. 下一条命令
```

- `## 4` 用表格：候选 / 预期收益 / 成本 / 前置条件 / 风险。
- `## 5` 写清"已否决的路线"和"不要动的产物（gold/已验收）"，防止新上下文重复试错。
- `## 6` 必须是**一条可直接执行的命令**（与 `state.json.next_action.cmd` 一致）。

---

## 4. `ARTIFACTS.md`（产物索引）

| 路径 | 类型 | sha256 | 大小 | 说明 | 备份位置 |
|---|---|---|---|---|---|
| `artifacts/<path>` | model/log/table | `<hex>` | `<bytes>` | <一句话> | `<backup path 或 ->` |

- 由 `sessionctl ckpt` 追加；`sessionctl close` 把备份包路径补进 `备份位置` 列。
- `verify` 逐行校验；`source: caller` 的行标注"未本地校验"。

---

## 5. `state.json`（唯一机器状态源）

只允许通过 `sessionctl` 修改（原子写：临时文件 + `os.replace`）。

```json
{
  "schema": 1,
  "session": "2026-10-26-<slug>",
  "slug": "<slug>",
  "mode": "full",
  "created_at": "2026-10-26T10:00:00+08:00 (1761444000)",
  "updated_at": "2026-10-26T10:31:02+08:00 (1761445862)",
  "stage": "S3",
  "status": "idle",
  "runs": [
    {
      "id": "train-x",
      "kind": "long",
      "started_at": "2026-10-26T10:05:00+08:00 (1761444300)",
      "heartbeat_interval_s": 60,
      "terminal_marker": "train_runtime",
      "state": "running",
      "artifact": "artifacts/train-x",
      "sha256": "…",
      "sha256_source": "local"
    }
  ],
  "next_action": {"cmd": "…", "expect": "…", "doc": "NEXT_PLAN §6"},
  "blockers": [],
  "gates": {"<指标>": {"threshold": "≥<值>", "measured": null, "verdict": null}}
}
```

字段约束：

| 字段 | 取值 |
|---|---|
| `schema` | 固定 `1` |
| `stage` | `S0`…`S5` |
| `status` | `idle` / `running` / `blocked` / `done` |
| `mode` | `full` / `lite` |
| `runs[].state` | `running` / `done` / `failed` / `stale` |
| `gates.*.verdict` | `pass` / `fail` / `neutral` / `null` |

`sessionctl state` 的白名单键：

```
stage  status  next_action.cmd  next_action.expect  next_action.doc
blockers  gates.<name>.threshold  gates.<name>.measured  gates.<name>.verdict
```

其他键一律拒绝（退出码 2），避免状态文件长成自由文本。

---

## 6. 目录布局

```
sessions/2026-10-26-<slug>/
├── SESSION_PLAN.md
├── SESSION_LOG.md
├── NEXT_PLAN.md
├── ARTIFACTS.md
├── state.json
├── logs/            # full 模式
│   ├── <run>.log
│   └── heartbeat.log
├── artifacts/       # full 模式
└── backup/          # close 生成的备份包
```