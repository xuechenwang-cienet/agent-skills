---
name: cienet-ppt-style
description: CIeNET 公司 PPT 母版与配色规范。给 CIeNET 制作或改造 .pptx（汇报、方案、培训、客户演示、周报、评审材料）时使用：从 assets/cienet_theme.pptx 的 8 个母版布局起稿，遵守品牌色卡、语义配色一致性和洋红面积限制，用 officecli 落稿并用脚本自检。触发词：CIeNET PPT、公司模板、公司母版、品牌配色、给 CIeNET 写 PPT/汇报/方案/培训、CIeNET deck、CIeNET template、把这份材料套成公司模板。
---

# CIeNET PPT 母版与配色

给 CIeNET 做演示文稿时，本技能是唯一视觉口径。母版装饰、色卡、字号、布局用途都在这里定死；自由发挥只允许在内容组织上。

## 先读什么

| 需要什么 | 读 |
|---|---|
| 色值、洋红限制、语义配色 | `references/palette.md` |
| 8 个布局怎么用、槽位坐标和字号 | `references/layouts.md` |
| 可直接粘贴的 officecli 命令 | `references/recipes.md` |
| 交付前检查什么 | `references/qa.md` |
| 布局长什么样 | `assets/layout-preview.png` |

所有路径都相对技能根目录。下文命令默认在技能根目录执行。

## 不可协商的规则

1. **从母版起稿。** 必须 `cp assets/cienet_theme.pptx <输出>.pptx` 后删掉 3 页样张，禁止新建空白 pptx、禁止套用其它模板。
2. **只用 8 个布局**，按 `references/layouts.md` 的用途映射；不新建、不改名、不改动布局。
3. **不改母版装饰**：右上 CIeNET logo、底部蓝紫渐变条、`CIENET PROPRIETARY` 页脚、页码，一个都不能移动、遮挡、删除或改色。`scripts/check_style.py` 会用哈希校验母版与布局是否被改。
4. **颜色只用色卡**：品牌三色、三个淡色、渐变、中性色，以及母版既有的封面文字色。禁止引入色卡外的颜色（含绿色、橙色、黄色、紫红以外的鲜艳色）。
5. **洋红 `#932193` 只做点缀**：单页面积合计 ≤ 5%，禁止整页背景、大面积色块、表格整行整列底色、面积型图表的大柱/大饼块，禁止作为图表第 1 序列，渐变里只能出现在末端。细则见 `palette.md`。
6. **同一事物始终同色**：开工先写语义色表（实体 → 色值），全篇复用。同一实体在正文、图例、色块、表格里颜色必须一致；换页换色算缺陷。
7. **字体只有 Calibri + 宋体**：每个新建文本框都显式 `font=Calibri`，中文由主题映射到宋体。不要用 Arial、微软雅黑、思源等其它字体。
8. **只用 officecli 改 pptx**。不要写 python-pptx / python-docx 脚本，不要手工解压改 XML。officecli 不可用时停下来告知用户，不允许悄悄换工具。
9. **交付前必须** `scripts/check_style.py` 为 PASS，并看过 `scripts/preview.sh` 出的缩略图。

## 工作流

### 1. 建稿

```bash
bash scripts/new_deck.sh out.pptx --title "项目汇报" --author "姓名"
```

产出 0 页、16:9、母版完整的空稿。`--force` 才允许覆盖已有文件。

### 2. 定语义色表（不能跳）

在 `deck-plan.md` 里先列大纲和语义色表，再动 pptx。固定语义直接用，不固定语义按"面积越大颜色越浅"分配：

| 语义 | 用色 |
|---|---|
| 现状 / As-Is / 基线 | brand-blue `#2453B3` |
| 目标 / To-Be / 新方案 | brand-purple `#5230A2` |
| 风险 / 问题 / 告警 | brand-magenta `#932193`（仅小面积） |
| 中性 / 其他 / 未涉及 | neutral `#5A5A5A` |
| 正向结果 / 达成 | tint-blue 底 + brand-blue 文字 |
| 强调数字 | brand-blue |

多实体示例（完整模板见 `palette.md`）：

| 实体 | 色值 | 出现位置 |
|---|---|---|
| 方案 A | `#2453B3` | 图例、柱、正文标签 |
| 方案 B | `#5230A2` | 图例、柱、正文标签 |
| 风险项 | `#932193` | 仅圆点与图标 |

### 3. 选布局

按内容挑，不按好看挑：

| 页面 | 布局 |
|---|---|
| 封面（首选） | `TITLE PAGE 1` |
| 封面（科技/创新主题备选） | `TITLE` |
| 目录 | `AGENDA 1` |
| 章节过渡 | `TITLE PAGE 1`（只填标题 + 一行说明） |
| 标准内容页 | `Title and Content` |
| 双栏对比 / 并列要点 | `Custom Layout 2` |
| 联系方式 / 结尾信息 | `Contact information` |
| 致谢 | `Acknowledgements` |
| 纯标题页 / 无装饰分隔 | `DEFAULT_1` |

每个 deck 最多用 1 个封面、1 个目录、1 个致谢；章节页数量 = 章节数。

### 4. 落内容

```bash
officecli add out.pptx / --type slide --prop "layout=Title and Content"
officecli add out.pptx "/slide[last()]" --type textbox \
  --prop x=0.68cm --prop y=0.64cm --prop w=30.62cm --prop h=1.38cm \
  --prop "text=标题写结论，不写主题词" --prop font=Calibri --prop size=32 --prop bold=true --prop color=#1A1A1A
```

- `layout=` **只写元数据，不会生成占位符**：所有文字都要按 `layouts.md` 的坐标自己加 textbox。
- 每个文本框显式给 `font=Calibri`；字号按 `layouts.md` 的层级，不按 officecli 默认的 14pt。
- 内容页保持白底：不要给内容页设置 `background`，白色和装饰由布局提供。
- 需要图时放右侧（`x≥18cm`），不要压 logo 区（`x>31cm 且 y<2cm`）。
- 每页讲一件事；标题是结论句，正文 ≤ 5 条要点。

### 5. 预览

```bash
bash scripts/preview.sh out.pptx --out preview/
```

逐页看：文字有没有溢出/压边、图片有没有盖住 logo、页脚是否完整、洋红有没有变大色块。

### 6. 校验

```bash
python3 scripts/check_style.py out.pptx            # 人读
python3 scripts/check_style.py out.pptx --json     # 机器读
python3 scripts/area_audit.py out.pptx             # 只看洋红与面积
officecli validate out.pptx
officecli view out.pptx issues
```

`check_style.py` 检查 16:9、布局白名单、色值白名单、字体、洋红面积、渐变方向、图表序列一致性、母版完整性、logo 遮挡。FAIL 必须改到 PASS；WARN 逐条判断。

## 配色速查

| token | 色值 | 用途 |
|---|---|---|
| brand-blue | `#2453B3` | 主色：强调、图表第 1 序列、关键数字 |
| brand-purple | `#5230A2` | 次色：图表第 2 序列、章节底 |
| brand-magenta | `#932193` | 点缀：仅小面积（≤5%） |
| tint-blue | `#DAE6FB` | 浅底：卡片、表头、斑马纹 |
| tint-purple | `#E7E6F8` | 浅底：与 tint-blue 交替使用 |
| tint-pink | `#F5E5F5` | 浅底：第三组分类 |
| gradient | `#2453B3 → #932193` | 大面积色块，0° 或 90°，洋红在末端 |
| ink | `#1A1A1A` | 深色背景 / 正文深色文字 |
| neutral | `#5A5A5A` `#D9D9D9` `#FFFFFF` | 次要文字、分隔线、白底 |

模板既有色（只沿用，不新增使用场景）：`#6D97D2` 内容页眉标、`#E8EEF8`/`#D8E2F2` 封面与致谢页的次级文字。

## 常见违规

| 违规 | 正确做法 |
|---|---|
| 用主题 accent 之外的随手蓝色 | 只用 `#2453B3` / `#5230A2` |
| 风险页整块洋红背景 | 白底 + 洋红小圆点/图标标记 |
| 图表里每个系列一个自选色 | 按语义色表取色，跨图表同名同色 |
| 同一方案在第 3 页蓝、第 7 页紫 | 回看语义色表，全篇统一 |
| 正文用 Arial 或微软雅黑 | 统一 `font=Calibri` |
| 内容页手动加背景色 | 保持布局白底 |
| 删掉页脚或 logo "让版面干净" | 保留，靠留白而不是删装饰 |

## 环境依赖与失败处理

- 依赖 `officecli`（`officecli --version` 确认）和 `python3`（仅标准库）。
- 没有 officecli：停止生成，告诉用户安装方式（`curl -fsSL https://d.officecli.ai/install.sh | bash`），**不要**改用 python-pptx。
- `check_style.py` 报"母版被改动"：说明有人动过 master/layout，从 `assets/cienet_theme.pptx` 重新起稿，不要试图只修坏的那一页。
- 渲染以 PowerPoint 为准：officecli 的 HTML 截图与 PowerPoint 在字宽上有差异，文本框一律留 10% 余量、不开 autoFit。

## 文件清单

```
SKILL.md                  本文件
assets/cienet_theme.pptx  唯一母版（3 页样张可作参照，建稿时删除）
assets/cienet_color_style.png  色卡原图
assets/layout-preview.png 8 个布局的缩略总览
references/palette.md     色值、洋红限制、语义配色
references/layouts.md     布局用途与槽位坐标
references/recipes.md     officecli 命令配方
references/qa.md          交付质检清单
scripts/new_deck.sh       建空稿
scripts/preview.sh        出缩略图 / 逐页 PNG
scripts/check_style.py    规范校验
scripts/area_audit.py     洋红与面积审计
tests/selftest.sh         自测
```