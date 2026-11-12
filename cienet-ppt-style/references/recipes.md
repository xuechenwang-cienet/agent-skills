# officecli 命令配方

约定：`out.pptx` 是输出文件；`N` 是页号（从 1 开始）。所有路径加引号，zsh 会把未加引号的 `[N]` 当通配符。

```bash
FILE=out.pptx
```

## 0. 建稿

```bash
bash scripts/new_deck.sh "$FILE" --title "项目汇报" --author "张三"
```

之后每加一页都先确认页码：

```bash
officecli add "$FILE" / --type slide --prop "layout=Title and Content"
officecli get "$FILE" "/slide[last()]"
```

## 1. 封面（`TITLE PAGE 1`）

```bash
officecli add "$FILE" / --type slide --prop "layout=TITLE PAGE 1"

officecli add "$FILE" "/slide[last()]" --type textbox --prop name=CoverTitle \
  --prop x=4.0cm --prop y=6.6cm --prop w=25.87cm --prop h=2.7cm \
  --prop "text=CIeNET 交付平台改造方案" --prop font=Calibri --prop size=54 --prop bold=true \
  --prop color=#FFFFFF --prop align=center

officecli add "$FILE" "/slide[last()]" --type textbox --prop name=CoverSub \
  --prop x=4.0cm --prop y=9.1cm --prop w=25.87cm --prop h=1.4cm \
  --prop "text=2026 年 Q4 技术路线与投入评估" --prop font=Calibri --prop size=24 \
  --prop color=#FFFFFF --prop align=center

officecli add "$FILE" "/slide[last()]" --type textbox --prop name=CoverMeta \
  --prop x=4.0cm --prop y=15.8cm --prop w=25.87cm --prop h=0.9cm \
  --prop "text=CIeNET · 交付技术部 · 2026-11-10" --prop font=Calibri --prop size=12 \
  --prop color=#D8E2F2 --prop align=center
```

主标题超过 18 个汉字时改 `size=44` 或 `48`，不要靠 autoFit 缩字。

## 2. 目录（`AGENDA 1`）

左面板自带 "AGENDA" 字样，只填右侧。

```bash
officecli add "$FILE" / --type slide --prop "layout=AGENDA 1"

officecli add "$FILE" "/slide[last()]" --type textbox --prop name=AgendaBody \
  --prop x=15.76cm --prop y=2.85cm --prop w=15.36cm --prop h=14.96cm \
  --prop "text=01  现状与问题\n02  改造目标\n03  技术方案\n04  投入与排期\n05  风险与应对" \
  --prop font=Calibri --prop size=22 --prop color=#1A1A1A --prop lineSpacing=1.8x
```

编号用 `01`–`09`，不要用 `•`。条目超过 7 条时改成两列（第二列 `x=25.5cm, w=6.8cm`）。

## 3. 标准内容页（`Title and Content`）

```bash
officecli add "$FILE" / --type slide --prop "layout=Title and Content"

# 标题（结论句）
officecli add "$FILE" "/slide[last()]" --type textbox --prop name=Title \
  --prop x=0.68cm --prop y=0.64cm --prop w=30.62cm --prop h=1.75cm \
  --prop "text=现有构建链路平均等待 42 分钟" --prop font=Calibri --prop size=32 \
  --prop bold=true --prop color=#1A1A1A

# 眉标（可省）
officecli add "$FILE" "/slide[last()]" --type textbox --prop name=Eyebrow \
  --prop x=0.68cm --prop y=2.45cm --prop w=30.62cm --prop h=1.2cm \
  --prop "text=现状分析" --prop font=Calibri --prop size=20 --prop bold=true \
  --prop color=#6D97D2

# 正文（\n 分段）
officecli add "$FILE" "/slide[last()]" --type textbox --prop name=Body \
  --prop x=1.26cm --prop y=4.09cm --prop w=31.39cm --prop h=13.07cm \
  --prop "text=全量构建 38 分钟，其中依赖下载占 21 分钟\n缓存命中率 34%，跨机房重复拉包\n等待期无并行化，CPU 利用率峰值仅 18%" \
  --prop font=Calibri --prop size=22 --prop color=#1A1A1A --prop lineSpacing=1.5x

# 项目符号
for p in 1 2 3; do
  officecli set "$FILE" "/slide[N]/shape[@name=Body]/paragraph[$p]" --prop list=bullet
done

# 演讲备注
officecli add "$FILE" "/slide[N]" --type notes --prop text="先给基线数字，再引出缓存改造。"
```

正文用布局默认 28pt 时最多 3 条；4–5 条用 22pt；超过 5 条拆页。

## 4. 双栏（`Custom Layout 2`）

```bash
officecli add "$FILE" / --type slide --prop "layout=Custom Layout 2"

officecli add "$FILE" "/slide[last()]" --type textbox --prop name=Title \
  --prop x=0.68cm --prop y=0.64cm --prop w=30.62cm --prop h=1.75cm \
  --prop "text=自建缓存与托管缓存的关键差异" --prop font=Calibri --prop size=32 \
  --prop bold=true --prop color=#1A1A1A

officecli add "$FILE" "/slide[last()]" --type textbox --prop name=LeftCol \
  --prop x=1.26cm --prop y=4.09cm --prop w=15.19cm --prop h=13.04cm \
  --prop "text=自建缓存\n• 一次性投入 12 人日\n• 命中率上限受机房带宽限制\n• 运维责任在我方" \
  --prop font=Calibri --prop size=22 --prop color=#1A1A1A --prop lineSpacing=1.4x

officecli add "$FILE" "/slide[last()]" --type textbox --prop name=RightCol \
  --prop x=17.46cm --prop y=4.09cm --prop w=15.19cm --prop h=13.04cm \
  --prop "text=托管缓存\n• 按量计费，无前置投入\n• 命中率 78%（试点数据）\n• 运维转移给服务商" \
  --prop font=Calibri --prop size=22 --prop color=#1A1A1A --prop lineSpacing=1.4x
```

两栏的小标题前用 `#2453B3` / `#5230A2` 色块做标签时，色块 ≤ 3cm 宽、0.6cm 高，且左右栏色值要和语义色表一致。

## 5. 章节过渡（`TITLE PAGE 1`）

```bash
officecli add "$FILE" / --type slide --prop "layout=TITLE PAGE 1"
officecli add "$FILE" "/slide[last()]" --type textbox \
  --prop x=4.0cm --prop y=6.6cm --prop w=25.87cm --prop h=2.7cm \
  --prop "text=02  技术方案" --prop font=Calibri --prop size=48 --prop bold=true \
  --prop color=#FFFFFF --prop align=center
officecli add "$FILE" "/slide[last()]" --type textbox \
  --prop x=4.0cm --prop y=9.1cm --prop w=25.87cm --prop h=1.4cm \
  --prop "text=缓存层替换与流水线并行化" --prop font=Calibri --prop size=24 \
  --prop color=#FFFFFF --prop align=center
```

## 6. KPI 大数字（`DEFAULT_1` 或内容页）

```bash
officecli add "$FILE" "/slide[N]" --type textbox --prop name=Kpi1 \
  --prop x=1.26cm --prop y=5.0cm --prop w=9.94cm --prop h=2.8cm \
  --prop "text=78%" --prop font=Calibri --prop size=72 --prop bold=true \
  --prop color=#2453B3 --prop align=center
officecli add "$FILE" "/slide[N]" --type textbox --prop name=KpiLabel1 \
  --prop x=1.26cm --prop y=8.0cm --prop w=9.94cm --prop h=0.9cm \
  --prop "text=缓存命中率" --prop font=Calibri --prop size=16 \
  --prop color=#5A5A5A --prop align=center
```

三个 KPI 的 x 坐标：`1.26`、`13.46`、`25.66`（宽 9.94，间距 0.76）。只有"风险"那一个 KPI 可以用洋红，且数字下方短横线 ≤ 3cm。

## 7. 表格

```bash
officecli add "$FILE" "/slide[N]" --type table --prop name=Compare \
  --prop x=1.26cm --prop y=4.5cm --prop w=31.39cm --prop h=8cm \
  --prop cols=4 --prop rows=4 \
  --prop "data=维度,现状,目标,差距;构建耗时,38 min,22 min,-42%;缓存命中率,34%,78%,+44pp;月度成本,1.8 万,2.4 万,+33%" \
  --prop headerFill=#2453B3 --prop bodyFill=#FFFFFF --prop border.horizontal="1pt solid D9D9D9"

# 表头文字改白、正文 14pt
for c in 1 2 3 4; do
  officecli set "$FILE" "/slide[N]/table[@name=Compare]/tr[1]/tc[$c]" --prop font=Calibri --prop size=14 --prop bold=true --prop color=#FFFFFF
done
for r in 2 3 4; do
  for c in 1 2 3 4; do
    officecli set "$FILE" "/slide[N]/table[@name=Compare]/tr[$r]/tc[$c]" --prop font=Calibri --prop size=14 --prop color=#1A1A1A
  done
done
```

- 表头深底白字（`#2453B3`）或浅底深字（`#DAE6FB` + `#1A1A1A`）二选一，整份材料统一。
- 斑马纹用 `#DAE6FB` / 白色交替；不要用洋红做整列高亮。
- 需要强调"变差"时，在单元格文字后加 `▼` 并用 `#932193` 只给这个符号上色，不要整格填色。

## 8. 图表

```bash
officecli add "$FILE" "/slide[N]" --type chart --prop chartType=column \
  --prop series1.name="现状" --prop series1.values="38,34,1.8" --prop series1.color=2453B3 \
  --prop series2.name="目标" --prop series2.values="22,78,2.4" --prop series2.color=5230A2 \
  --prop categories="构建耗时(min),缓存命中率(%),成本(万)" \
  --prop x=1.26cm --prop y=4.5cm --prop w=19cm --prop h=12cm \
  --prop title="改造前后对比"
```

- 序列顺序固定：`#2453B3` → `#5230A2` → `#932193`（仅细线/小标记）→ `#5A5A5A`。
- 系列名就是语义实体名（"现状"/"目标"/"方案 A"），跨图表同名同色。
- 饼图最多 5 个扇区，洋红扇区最多 1 个且占比 ≤ 10%。
- 图表旁边留 1/3 写结论卡片，不要只放图：

```bash
officecli add "$FILE" "/slide[N]" --type shape --prop preset=roundRect --prop line=none \
  --prop fill=#DAE6FB --prop x=21.5cm --prop y=4.5cm --prop w=11cm --prop h=12cm
officecli add "$FILE" "/slide[N]" --type textbox \
  --prop x=22.3cm --prop y=5.2cm --prop w=9.4cm --prop h=10cm \
  --prop "text=关键结论\n命中率提升到 78%（+44pp）\n构建等待下降 42%\n成本上升 33%，但人均产出覆盖" \
  --prop font=Calibri --prop size=18 --prop color=#1A1A1A --prop lineSpacing=1.4x
```

## 9. 配图

```bash
officecli add "$FILE" "/slide[N]" --type picture --prop src=photo.png \
  --prop x=17.0cm --prop y=4.09cm --prop w=14.3cm --prop h=11.5cm \
  --prop alt="缓存命中率监控面板截图"
```

- 保持纵横比：只给 `w` 或只给 `h`，不要两个都给着硬拉。
- 图不压 logo（`x>31.5 且 y<2.5`）和页脚（`y>17.8`）。
- 截图/流程图用"适应"（不裁切）；照片用"填满"（可裁边）。

## 10. 致谢（`Acknowledgements`）

```bash
officecli add "$FILE" / --type slide --prop "layout=Acknowledgements"
officecli add "$FILE" "/slide[last()]" --type textbox \
  --prop x=4.0cm --prop y=10.2cm --prop w=25.87cm --prop h=1.0cm \
  --prop "text=Questions & Discussion" --prop font=Calibri --prop size=18 \
  --prop color=#E8EEF8 --prop align=center
officecli add "$FILE" "/slide[last()]" --type textbox \
  --prop x=4.0cm --prop y=15.4cm --prop w=25.87cm --prop h=0.9cm \
  --prop "text=CIeNET · 交付技术部" --prop font=Calibri --prop size=14 \
  --prop color=#D8E2F2 --prop align=center
```

## 11. 收尾

```bash
officecli set "$FILE" / --prop title="CIeNET 交付平台改造方案" --prop author="张三"
officecli save "$FILE"
bash scripts/preview.sh "$FILE" --out preview/
python3 scripts/check_style.py "$FILE"
officecli validate "$FILE"
officecli view "$FILE" issues
```

## 命令速查

| 目的 | 命令 |
|---|---|
| 加页 | `officecli add "$FILE" / --type slide --prop "layout=<布局名>"` |
| 定位上一页 | `"/slide[last()]"` |
| 文本框 | `--type textbox --prop x= --prop y= --prop w= --prop h= --prop text= --prop font=Calibri --prop size= --prop color=` |
| 形状 | `--type shape --prop preset=roundRect --prop fill=#DAE6FB --prop line=none` |
| 分段 | 文本里写 `\n`（会被解释为换段） |
| 项目符号 | `set ".../shape[@name=Body]/paragraph[K]" --prop list=bullet` |
| 图表 | `--type chart --prop chartType=column --prop seriesN.name= --prop seriesN.values= --prop seriesN.color=` |
| 表格 | `--type table --prop data="H1,H2;A,B" --prop headerFill= --prop bodyFill=` |
| 图片 | `--type picture --prop src= --prop w= --prop alt=` |
| 备注 | `--type notes --prop text=` |
| 预览单页 | `officecli view "$FILE" screenshot --page N -o p.png` |
| 查所有形状 | `officecli get "$FILE" "/slide[N]" --depth 1` |

## 常见报错

| 现象 | 原因 / 处理 |
|---|---|
| `no matches found: /slide[1]` | 路径没加引号 |
| `layout=xxx` 报了但页面空白 | 布局只给装饰，文字要自己加 textbox |
| 文字跑出页面 | 坐标单位漏了 `cm`，或字号超过槽位容量 |
| 圆点/色块颜色不对 | 用的是 `#` 前缀十六进制；`2453B3` 和 `#2453B3` 都接受，但别写颜色名 |
| `check_style.py` 报色值 | 把该元素的 `color` / `fill` 改成色卡值 |