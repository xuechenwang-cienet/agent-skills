# tokenplan-enterprise-bailian

阿里云百炼 **Token Plan** 组织用量分析：一条命令生成部门报告 + 各组报告。

```bash
cd tokenplan-enterprise-bailian
python3 scripts/run.py          # 首次需要确认四项配置
```

约 30 秒后，`output/<今天>/` 下会有 8 份 HTML + 系数表 + 收件人清单。

> 仓库里只带 **sample 配置**。第一次用先复制两份：
> ```bash
> cp config/config.sample.yaml config/config.yaml
> cp config/members.sample.csv config/members.csv
> ```
> 这两个真实文件已被 `.gitignore` 忽略，不会进版本库。

---

## 第一次使用

### 1. 环境

```bash
python3 --version              # 需要 ≥ 3.11
uv pip install pyyaml openpyxl # openpyxl 可选（只影响 xlsx 和名册导入）
bsk status                     # 需要显示浏览器已连接
```

浏览器里打开过一次百炼控制台并保持登录即可，脚本不保存任何凭据。

### 2. 配置

```bash
cp config/config.sample.yaml config/config.yaml
cp config/members.sample.csv config/members.csv
```

| 文件 | 要改什么 | 是否入库 |
|---|---|---|
| `config/config.yaml` | 组织 ID、价格、预测参数 | ✗ 忽略 |
| `config/members.csv` | 人员、邮箱、所属组、席位额度 | ✗ 忽略 |
| `config/holidays.yaml` | 每年更新节假日与调休 | ✓ |
| `config/*.sample.*` | 模板，勿直接使用 | ✓ |

名册可以从 xlsx 一次性导入：

```bash
python3 scripts/tools/import_roster.py --xlsx "../202610_usage.xlsx" --accounts accounts.json
```

`accounts.json` 是 `[{"id":"acc_xxx","name":"Bailian 显示名"}, …]`，用于填充 `bailian_account_ids`。
没有它也能导入，但运行时匹配不到账号会全部落到「未归属」。

### 3. 跑

```bash
python3 scripts/run.py
```

第一次会打印四项确认摘要，按回车确认即可。之后 30 天内（名册没改）不再询问。

---

## 日常用法

```bash
# 每周一次，后台静默
python3 scripts/run.py --non-interactive

# 回补 9 月
python3 scripts/run.py --month 2026-09

# 抓数失败但已有 CSV：只重算和重渲染
python3 scripts/run.py --from s3

# 同一天第二次跑
python3 scripts/run.py --tag evening   # → output/2026-10-20-evening/
```

### 定时任务（示例，未默认启用）

```cron
# 每周一 09:10 生成当月报告
10 9 * * 1 cd /path/to/tokenplan-enterprise-bailian && /usr/bin/env python3 scripts/run.py --non-interactive >> logs/cron.log 2>&1
```

> 后台模式要求四项确认都在有效期内，否则退出码 2。定时任务第一次先手动跑一次确认。

---

## 产出

```
output/2026-10-20/
├── token_credits_report.html      部门报告（12 节）
├── team-高莉.html                  项目组报告（每组一份）
├── team-乐薇.html
├── …
├── token_credits_coefficients.xlsx
├── token_credits_coefficients.md
├── recipients.csv                 发邮件用：group / owner / name / email / role / report
├── manifest.json                  自检结果 + 配置哈希
├── data/analysis.json             结构化数据（可给别的系统消费）
└── raw/usage_detail.csv           全量明细
```

所有 HTML 都是单文件、无外部依赖，可直接当邮件附件。

`recipients.csv` 里 `send_dept=true` 的是组 owner（附部门报告），其余成员只附本组报告。

---

## 常见问题

**Q：提示「未能捕获 sec_token」**
浏览器可能停在登录页。`bsk status` 看连接状态，手动打开一次控制台再重试。

**Q：报告里的「折算 ¥」和账单对不上**
那是用于横向比较的成本口径（席位月费 + 加油包按单价折算），不是财务分摊。

**Q：某个人没出现在报告里**
查 `manifest.json` 的 `unmapped`。通常是名册里没有他的 Bailian 账号，或 `bailian_account_ids` 写错了。

**Q：换月后工作日数不对**
更新 `config/holidays.yaml`，并把新月份加进 `verified_months`。

---

## 目录

```
SKILL.md                  技能说明（含原理、退出码、排查）
README.md                 本文件
config/                   配置（独立于代码）
scripts/
  run.py                  唯一入口
  steps/s0…s5.py          预检 / 抓数 / 抓订阅 / 分析 / 渲染 / 清单
  lib/                    bsk 封装、API、配置、日历、渲染
  tools/import_roster.py  xlsx → members.csv
output/                   按启动日期分目录
logs/                     运行日志
```