#!/usr/bin/env python3
"""claim_scan.py — 从文本抽取可核验声明，生成声明登记表初稿（claims.csv）

用法:
  claim_scan.py FILE [FILE...]            # 输出 CSV 到 stdout
  officecli view FILE.docx text > t.txt   # docx 先抽文本再扫描
  inventory_xlsx.py 的 TSV 也可以直接扫描

抽取类型:
  number     计数声明（"N 条/项/个/张/段/列/rows/items/tables..."）
  id         文档标识（CNT-XXX-YYY 形式）
  version    版本号（仅出现在版本语境行）
  date       日期
  link       URL
  existence  "新增/删除/移除/改为/替换 X" 的存在性陈述

初稿只填前 5 列；observed/verdict 由评审 agent 补全（见 references/schemas.md）。
"""

import sys, re, csv

CNT = re.compile(
    r"(\d+)\s*(条|项|个|张|处|段|列|rows?\b|items?\b|tables?\b|paragraphs?\b|columns?\b|sheets?\b|issues?\b)"
)
IDENT = re.compile(r"\b[A-Z]{2,}(?:-[A-Za-z0-9_&.]+){2,}\b")
VER = re.compile(r"\b[vV]?\d+\.\d+(?:\.\d+)*\b")
VER_CTX = re.compile(
    r"(?i)version|版本|v\d|asvs|ssdf|sp\s?800|slsa|samm|iso|owasp|top\s?10|rfc|cwe"
)
DATE = re.compile(r"\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b")
LINK = re.compile(r"https?://[^\s)\]、,，。；;）」\']+")
EXIST = re.compile(r"(新增|增加了?|删除|移除|改为|替换|补齐|拆分|合并)[^。；\n]{2,50}")

VERSIONS_OK = {"2025-11-06"}  # 避免把日期误报为版本——先抽日期再抽版本时跳过已命中片段


def scan(path):
    rows = []
    text = open(path, encoding="utf-8", errors="ignore").read()
    lines = text.splitlines()
    for i, line in enumerate(lines, 1):
        if not line.strip():
            continue
        ctx = line.strip()
        for m in CNT.finditer(line):
            rows.append(("number", f"{m.group(0)}", ctx[:80], i))
        for m in IDENT.finditer(line):
            rows.append(("id", m.group(0), ctx[:80], i))
        dates = [d.group(0) for d in DATE.finditer(line)]
        for m in VER.finditer(line):
            if m.group(0) in dates:
                continue
            if VER_CTX.search(line):
                rows.append(("version", m.group(0), ctx[:80], i))
        for m in DATE.finditer(line):
            rows.append(("date", m.group(0), ctx[:80], i))
        for m in LINK.finditer(line):
            rows.append(("link", m.group(0).rstrip(".,;"), ctx[:80], i))
        for m in EXIST.finditer(line):
            rows.append(("existence", m.group(0), ctx[:80], i))
    # 去重（同文件同类型同文本）
    seen, out = set(), []
    for t, txt, ctx, ln in rows:
        key = (t, txt)
        if key in seen:
            continue
        seen.add(key)
        out.append((t, txt, ctx, ln))
    return out


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    w = csv.writer(sys.stdout)
    w.writerow(
        [
            "claim_id",
            "source_file",
            "location",
            "type",
            "claim_text",
            "context",
            "verify_method",
            "observed",
            "verdict",
            "evidence",
            "checked_by",
        ]
    )
    n = 0
    for path in sys.argv[1:]:
        for t, txt, ctx, ln in scan(path):
            n += 1
            w.writerow(
                [f"C-{n:03d}", path, f"line {ln}", t, txt, ctx, "", "", "", "", ""]
            )
    print(
        f"# draft: {n} claims — fill verify_method/observed/verdict/evidence",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
