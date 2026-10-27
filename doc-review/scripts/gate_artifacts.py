#!/usr/bin/env python3
"""gate_artifacts.py — 把"阶段闸门"从提示词变成可执行检查

用法: gate_artifacts.py ROUND_DIR [--stage review|fix|final] [--level L3]
  ROUND_DIR = review/round-N/（含 01-findings.md 等工件）
  --stage   review=阶段1-2（初审/复核后）; fix=阶段4（修复后）; final=阶段5（终审后）
            默认 final（完整轮次，全量检查）

各阶段检查:
  review: manifest.json / claims.csv / 01-findings.md（+02 L2/L3）→ G2 声明全有裁定、G3 发现八字段
  fix:    + 04-fix-summary.md → G4 修复映射 1:1（E→F/D；显式拒绝有理由）
  final:  + 05-post-fix-review.md → G5 终审有结论且未解释差异清零
退出码: 0=PASS 1=FAIL（输出逐项判定）
"""

import sys, os, re, csv

FINDING_FIELDS = ["维度", "严重度", "文件", "位置", "观察值", "期望值", "证据", "复现"]


def exists(d, f):
    return os.path.exists(os.path.join(d, f))


def safe_read(d, f):
    try:
        return open(os.path.join(d, f), encoding="utf-8").read()
    except FileNotFoundError:
        return None


def gate_claims(d):
    text = safe_read(d, "claims.csv")
    if text is None:
        return 0, ["claims.csv 不存在"]
    rows = [
        r
        for r in csv.DictReader(text.splitlines())
        if (r.get("claim_id") or "").startswith("C-")
    ]
    problems = []
    for r in rows:
        v = (r.get("verdict") or "").strip().lower()
        if v not in ("true", "false", "unverifiable", "n/a", "待确认"):
            problems.append(f"{r['claim_id']}: verdict='{v or '空'}'")
    return len(rows), problems


def gate_findings(d):
    text = safe_read(d, "01-findings.md")
    if text is None:
        return [], ["01-findings.md 不存在"]
    ids = re.findall(r"^### (F-\d+)", text, re.M)
    problems = []
    for fid in ids:
        block = re.search(rf"^### {fid}\b.*?(?=^### |\Z)", text, re.S | re.M).group(0)
        for field in FINDING_FIELDS:
            if not re.search(rf"[-*]\s*{field}\s*[::]", block):
                problems.append(f"{fid}: 缺字段[{field}]")
        if re.search(r"疑似|大概", block):
            problems.append(f"{fid}: 含无证据措辞（疑似/大概）")
    return ids, problems


def gate_fixmap(d):
    text = safe_read(d, "04-fix-summary.md")
    if text is None:
        return 0, ["04-fix-summary.md 不存在"]
    es = re.findall(r"^### (E-\d+)", text, re.M)
    problems = []
    for eid in es:
        block = re.search(rf"^### {eid}\b.*?(?=^### |\Z)", text, re.S | re.M).group(0)
        if not re.search(r"F-\d+|D-\d+", block):
            problems.append(f"{eid}: 未映射到 F-/D- 编号")
    for fid, reason in re.findall(r"\|\s*(F-\d+)\s*\|\s*([^|\n]*)\|", text):
        if len(reason.strip()) < 4:
            problems.append(f"拒绝项 {fid}: 缺理由")
    return len(es), problems


def gate_final(d):
    text = safe_read(d, "05-post-fix-review.md")
    if text is None:
        return ["05-post-fix-review.md 不存在"]
    problems = []
    if not re.search(r"通过|需回", text):
        problems.append("缺结论（通过/需回阶段4）")
    if not re.search(r"未解释差异[^:：]*[:：]\s*(无|0)", text):
        problems.append("未解释差异未清零或未声明")
    return problems


def main():
    args = sys.argv[1:]
    d = args[0]
    stage = "final"
    if "--stage" in args:
        stage = args[args.index("--stage") + 1]
    level = "L3"
    if "--level" in args:
        level = args[args.index("--level") + 1]
    fails = []

    need = ["manifest.json", "claims.csv", "01-findings.md"]
    if level != "L1" and stage in ("review", "fix", "final"):
        need.append("02-assessment.md")
    if stage in ("fix", "final"):
        need.append("04-fix-summary.md")
    if stage == "final":
        need.append("05-post-fix-review.md")
    missing = [f for f in need if not exists(d, f)]
    print(
        f"G1 工件齐全(stage={stage}): {'PASS' if not missing else 'FAIL ' + str(missing)}"
    )
    if missing:
        fails.append("G1")

    n, p = gate_claims(d)
    print(f"G2 声明裁定({n}条): {'PASS' if not p else 'FAIL ' + str(p[:5])}")
    if p:
        fails.append("G2")
    ids, p = gate_findings(d)
    print(f"G3 发现八字段({len(ids)}条): {'PASS' if not p else 'FAIL ' + str(p[:5])}")
    if p:
        fails.append("G3")
    if stage in ("fix", "final"):
        ne, p = gate_fixmap(d)
        print(f"G4 修复映射({ne}条): {'PASS' if not p else 'FAIL ' + str(p[:5])}")
        if p:
            fails.append("G4")
    if stage == "final":
        p = gate_final(d)
        print(f"G5 终审结论: {'PASS' if not p else 'FAIL ' + str(p)}")
        if p:
            fails.append("G5")
    print(f"GATE: {'PASS' if not fails else 'FAIL(' + ','.join(fails) + ')'}")
    sys.exit(0 if not fails else 1)


if __name__ == "__main__":
    main()
