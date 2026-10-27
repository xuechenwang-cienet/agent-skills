#!/usr/bin/env python3
"""diff_snapshot.py — 快照与差异审计（阶段 0 与阶段 5 的基线工具）

用法:
  diff_snapshot.py snap --out DIR FILE [FILE...]     # 建快照（复制 + SHA256 清单）
  diff_snapshot.py diff DIRA DIRB [--out REPORT.md]  # 比对两快照，文本级 diff

diff 输出分类（供终审标注）:
  added / removed / changed
  changed 的文件按内容做文本级 diff:
    .md/.txt/.csv/.tsv/.json/.xml  → 原文 unified diff
    .docx  → 段落文本抽取后 diff（word/document.xml 的 w:p/w:t）
    .xlsx  → 单元格值抽取后 diff（Sheet!Cell=value）
  文本相同但哈希不同 → 标"文本外变更（格式/属性/元数据）"，终审必须解释
另附 docProps/custom.xml 属性名对比（工具残留检测）。
"""

import sys, os, re, json, shutil, hashlib, zipfile, difflib
import xml.etree.ElementTree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
X = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def docx_text(path):
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read("word/document.xml"))
        out = []
        for p in root.iter(W + "p"):
            txt = "".join(t.text or "" for t in p.iter(W + "t"))
            out.append(txt)
        return out


def xlsx_text(path):
    with zipfile.ZipFile(path) as z:
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            root = ET.fromstring(z.read("xl/sharedStrings.xml"))
            shared = ["".join(t.text or "" for t in si.iter(X + "t")) for si in root]
        wb = ET.fromstring(z.read("xl/workbook.xml"))
        rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        rid = {r.get("Id"): r.get("Target") for r in rels}
        out = []
        for s in wb.iter(X + "sheet"):
            t = rid.get(
                s.get(
                    "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
                ),
                "",
            )
            t = (
                t.lstrip("/")
                if t.startswith("/")
                else ("xl/" + t if not t.startswith("xl/") else t)
            )
            out.append(f"### sheet: {s.get('name')}")
            root = ET.fromstring(z.read(t))
            for row in root.iter(X + "row"):
                for c in row:
                    v = c.find(X + "v")
                    val = None
                    if c.get("t") == "s" and v is not None and v.text:
                        i = int(v.text)
                        val = shared[i] if i < len(shared) else f"#SSI{i}"
                    elif v is not None:
                        val = v.text
                    if val is not None:
                        out.append(f"{c.get('r')}\t{val}")
        return out


def custom_props(path):
    try:
        with zipfile.ZipFile(path) as z:
            if "docProps/custom.xml" in z.namelist():
                return re.findall(
                    r'name="([^"]*)"',
                    z.read("docProps/custom.xml").decode("utf-8", "ignore"),
                )
    except Exception:
        pass
    return None


TEXTY = {".md", ".txt", ".csv", ".tsv", ".json", ".xml"}


def extract_lines(path):
    if path.endswith(".docx"):
        return docx_text(path)
    if path.endswith(".xlsx"):
        return xlsx_text(path)
    if os.path.splitext(path)[1] in TEXTY:
        return open(path, encoding="utf-8", errors="ignore").read().splitlines()
    return None


def cmd_snap(args):
    out = args[args.index("--out") + 1]
    files = args[args.index("--out") + 2 :]
    os.makedirs(out, exist_ok=True)
    manifest = {
        "created": __import__("datetime").datetime.now().isoformat(),
        "files": [],
    }
    for f in files:
        dst = os.path.join(out, os.path.basename(f))
        shutil.copy2(f, dst)
        manifest["files"].append(
            {
                "path": os.path.basename(f),
                "sha256": sha256(dst),
                "size": os.path.getsize(dst),
            }
        )
    with open(os.path.join(out, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=1)
    print(f"snapshot: {len(files)} files -> {out}/ (manifest.json written)")


def cmd_diff(args):
    a, b = args[0], args[1]
    out = "diff_report.md"
    if "--out" in args:
        out = args[args.index("--out") + 1]
    ma = json.load(open(os.path.join(a, "manifest.json")))
    mb = json.load(open(os.path.join(b, "manifest.json")))
    fa = {f["path"]: f for f in ma["files"]}
    fb = {f["path"]: f for f in mb["files"]}
    rep = ["# 差异审计报告", f"- A(前): {a}", f"- B(后): {b}", ""]
    added = sorted(set(fb) - set(fa))
    removed = sorted(set(fa) - set(fb))
    changed = sorted(p for p in set(fa) & set(fb) if fa[p]["sha256"] != fb[p]["sha256"])
    same = sorted(p for p in set(fa) & set(fb) if fa[p]["sha256"] == fb[p]["sha256"])
    rep += [
        f"- added: {added or '无'}",
        f"- removed: {removed or '无'}",
        f"- changed: {len(changed)} {changed}",
        f"- unchanged: {len(same)}",
        "",
    ]
    unexplained = []
    for p in changed:
        pa, pb = os.path.join(a, p), os.path.join(b, p)
        la, lb = extract_lines(pa), extract_lines(pb)
        rep.append(f"## {p}")
        props_a, props_b = custom_props(pa), custom_props(pb)
        if props_a is not None and props_b is not None and props_a != props_b:
            rep.append(f"- 自定义属性: {props_a} → {props_b}")
        if la is None or lb is None:
            rep.append("- 非文本可比：仅哈希变更（二进制/格式层）。终审必须解释。")
            unexplained.append(p)
            continue
        diff = list(difflib.unified_diff(la, lb, lineterm="", n=1))
        content_diff = [
            d
            for d in diff
            if d.startswith(("+", "-")) and not d.startswith(("+++", "---"))
        ]
        if not content_diff:
            rep.append(
                "- 文本层无差异但哈希已变：**文本外变更（格式/属性/元数据）**，终审必须解释。"
            )
            unexplained.append(p)
        else:
            rep.append("```diff")
            rep.extend(diff[:400])
            if len(diff) > 400:
                rep.append(f"…（截断，共 {len(diff)} 行 diff）")
            rep.append("```")
        rep.append("")
    rep.append("## 汇总")
    rep.append(f"- 未解释差异（需终审逐项说明）: {unexplained or '无'}")
    open(out, "w", encoding="utf-8").write("\n".join(rep) + "\n")
    print(f"diff report: {out} | changed={len(changed)} unexplained={len(unexplained)}")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    cmd = sys.argv[1]
    if cmd == "snap":
        cmd_snap(sys.argv[2:])
    elif cmd == "diff":
        cmd_diff(sys.argv[2:])
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
