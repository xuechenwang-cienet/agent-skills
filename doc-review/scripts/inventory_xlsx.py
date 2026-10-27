#!/usr/bin/env python3
"""inventory_xlsx.py — xlsx 机器盘点（纯 python 只读，不触发 officecli 驻留写入）

用法:
  inventory_xlsx.py FILE OUTDIR

输出:
  OUTDIR/inventory.json   结构盘点：工作表/维度/冻结/合并/数据验证/条件格式/公式/
                          隐藏行/定义名称/自定义属性/结构断言
  OUTDIR/<sheet名>.tsv    每个工作表的列导出（首列 row，后续为各列值），
                          供评审与 claim_scan 使用

为什么用 python 而不用 officecli：officecli 的驻留在只读访问后也会重写文件的
OfficeCLI.* 自定义属性（交付污染）；本脚本用 zipfile 保证零写入。
"""

import sys, os, re, json, zipfile, hashlib
import xml.etree.ElementTree as ET

NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
RNS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def col_of(ref):
    m = re.match(r"([A-Z]+)", ref)
    return m.group(1) if m else "?"


def load_shared_strings(z):
    if "xl/sharedStrings.xml" not in z.namelist():
        return []
    root = ET.fromstring(z.read("xl/sharedStrings.xml"))
    out = []
    for si in root:
        out.append("".join(t.text or "" for t in si.iter(f"{{{NS}}}t")))
    return out


def cell_value(c, shared):
    t = c.get("t")
    v = c.find(f"{{{NS}}}v")
    if t == "s" and v is not None and v.text is not None:
        i = int(v.text)
        return shared[i] if i < len(shared) else f"#SSI{i}"
    if t == "inlineStr":
        return "".join(x.text or "" for x in c.iter(f"{{{NS}}}t"))
    return v.text if (v is not None and v.text is not None) else None


def parse_sheet(z, name, shared):
    root = ET.fromstring(z.read(name))
    inv = {
        "file": name,
        "dimension": None,
        "freeze": None,
        "row_count": 0,
        "hidden_rows": [],
        "cell_ref_mismatch": [],
        "merges": [],
        "validations": [],
        "cf_rules": [],
        "formulas": [],
        "cells": 0,
        "last_data_row": 0,
    }
    dim = root.find(f"{{{NS}}}dimension")
    if dim is not None:
        inv["dimension"] = dim.get("ref")
    pane = root.find(f"{{{NS}}}sheetViews/{{{NS}}}sheetView/{{{NS}}}pane")
    if pane is not None:
        inv["freeze"] = pane.get("topLeftCell")
    sd = root.find(f"{{{NS}}}sheetData")
    rows = []
    if sd is not None:
        for row in sd:
            r = int(row.get("r"))
            rec = {"r": r, "hidden": row.get("hidden") == "1", "cells": {}}
            for c in row:
                ref = c.get("r")
                mref = re.match(r"([A-Z]+)(\d+)$", ref or "")
                if mref and int(mref.group(2)) != r:
                    # ECMA-376: 单元格引用的行号必须与其所在行一致——
                    # 整行移动只改行号不改单元格引用时的典型残留（Excel 修复弹窗风险）
                    inv["cell_ref_mismatch"].append({"cell": ref, "row": r})
                f = c.find(f"{{{NS}}}f")
                val = cell_value(c, shared)
                if f is not None:
                    inv["formulas"].append({"cell": ref, "formula": f.text})
                if val is not None or f is not None:
                    rec["cells"][col_of(ref)] = val
            rows.append(rec)
            if rec["hidden"]:
                inv["hidden_rows"].append(r)
    inv["row_count"] = len(rows)
    inv["cells"] = sum(len(r["cells"]) for r in rows)
    if rows:
        inv["last_data_row"] = rows[-1]["r"]
    # 行号跳跃不在此判断（什么算"数据行被空行切断"依赖具体文档的表格语义，
    # 属评审者按 12 维标准执行的判断——见 references/casebook.md 案例 11）
    for m in root.iter(f"{{{NS}}}mergeCell"):
        inv["merges"].append(m.get("ref"))
    for d in root.iter(f"{{{NS}}}dataValidation"):
        f1 = d.find(f"{{{NS}}}formula1")
        inv["validations"].append(
            {
                "sqref": d.get("sqref"),
                "type": d.get("type"),
                "formula1": (f1.text if f1 is not None else None),
            }
        )
    for cfmt in root.iter(f"{{{NS}}}conditionalFormatting"):
        for rule in cfmt:
            inv["cf_rules"].append(
                {
                    "sqref": cfmt.get("sqref"),
                    "type": rule.get("type"),
                    "priority": rule.get("priority"),
                    "stopIfTrue": rule.get("stopIfTrue"),
                    "text": rule.get("text"),
                }
            )
    return inv, rows


def max_col(rows):
    letters = [col for r in rows for col in r["cells"]]
    return letters


def col_index(letter):
    n = 0
    for ch in letter:
        n = n * 26 + (ord(ch) - 64)
    return n


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) < 2:
        print(__doc__)
        sys.exit(1)
    path, outdir = args[0], args[1]
    os.makedirs(outdir, exist_ok=True)
    z = zipfile.ZipFile(path)
    shared = load_shared_strings(z)

    # 工作表名 -> 文件映射
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    rid_target = {r.get("Id"): r.get("Target") for r in rels}
    sheets = []
    for s in wb.iter(f"{{{NS}}}sheet"):
        rid = s.get(f"{{{RNS}}}id")
        target = rid_target.get(rid, "")
        if target.startswith("/"):
            target = target[1:]
        elif not target.startswith("xl/"):
            target = "xl/" + target
        sheets.append({"name": s.get("name"), "file": target})

    # 定义名称（#REF! 检查）
    defined = []
    for dn in wb.iter(f"{{{NS}}}definedName"):
        defined.append({"name": dn.get("name"), "value": (dn.text or "")})
    ref_errors = [d["name"] for d in defined if "#REF!" in (d["value"] or "")]

    # 自定义属性（工具残留检查）
    custom_props = []
    if "docProps/custom.xml" in z.namelist():
        cx = z.read("docProps/custom.xml").decode("utf-8", errors="ignore")
        custom_props = re.findall(r'name="([^"]*)"', cx)
    residue = [p for p in custom_props if p.startswith("OfficeCLI")]

    result = {
        "file": os.path.basename(path),
        "sha256": hashlib.sha256(open(path, "rb").read()).hexdigest(),
        "sheets": [],
        "defined_names": defined,
        "defined_name_ref_errors": ref_errors,
        "custom_props": custom_props,
        "tool_residue": residue,
        "assertions": {},
    }

    for sh in sheets:
        inv, rows = parse_sheet(z, sh["file"], shared)
        # 结构断言
        bad = []
        if inv["cell_ref_mismatch"]:
            bad.append(
                f"单元格引用与所在行不一致（ECMA-376 违规，整行移动的典型残留）: {inv['cell_ref_mismatch']}"
            )
        if inv["hidden_rows"]:
            bad.append(f"隐藏行: {inv['hidden_rows']}")
        if ref_errors:
            bad.append(f"#REF! 定义名称: {ref_errors}")
        if residue:
            bad.append(f"工具残留属性: {residue}")
        inv["assertions"] = {"ok": not bad, "problems": bad}
        result["sheets"].append(
            {"name": sh["name"], **{k: v for k, v in inv.items() if k != "file"}}
        )

        # TSV 导出
        letters = sorted({c for r in rows for c in r["cells"]}, key=col_index)
        tsv = os.path.join(
            outdir, re.sub(r"[^\w\-\u4e00-\u9fff]", "_", sh["name"]) + ".tsv"
        )
        with open(tsv, "w", encoding="utf-8") as fh:
            fh.write("row\t" + "\t".join(letters) + "\n")
            for r in rows:
                if r["cells"] or r["hidden"]:
                    fh.write(
                        str(r["r"])
                        + "\t"
                        + "\t".join((r["cells"].get(c) or "") for c in letters)
                        + "\n"
                    )

    with open(os.path.join(outdir, "inventory.json"), "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=1)

    # 控制台摘要
    print(f"inventory: {outdir}/inventory.json")
    for s in result["sheets"]:
        a = s["assertions"]
        print(
            f"  [{s['name']}] rows={s['row_count']} cells={s['cells']} merges={len(s['merges'])} "
            f"dv={len(s['validations'])} cf={len(s['cf_rules'])} formulas={len(s['formulas'])} "
            f"hidden={len(s['hidden_rows'])} assertions={'OK' if a['ok'] else a['problems']}"
        )
    print(
        f"  defined_names={len(defined)} ref_errors={len(ref_errors)} residue={residue or '无'}"
    )


if __name__ == "__main__":
    main()
