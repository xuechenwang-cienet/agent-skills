#!/usr/bin/env bash
# doc-review 自测（离线，不访问网络）
# 覆盖：脚本语法、声明抽取、闸门正反例、最小 xlsx 的盘点/引用一致性/残留检测/清理幂等、
#       快照 diff 自比、链接核验的错误处理。
set -uo pipefail
cd "$(dirname "$0")/.."
S=scripts
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
PASS=0; FAIL=0
ok()  { echo "  PASS: $1"; PASS=$((PASS+1)); }
bad() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

echo "== 1. 脚本语法 =="
if bash -n "$S/inventory_docx.sh" && bash -n "$S/integrity_gate.sh"; then ok "bash -n"; else bad "bash -n"; fi
if python3 -m py_compile "$S"/*.py; then ok "py_compile"; else bad "py_compile"; fi

echo "== 2. 声明抽取（校准件） =="
N=$(python3 "$S/claim_scan.py" calibration/fixtures/claims.md 2>/dev/null | grep -c '^C-')
if [ "${N:-0}" -ge 10 ]; then ok "claim_scan 抽取 ${N} 条"; else bad "claim_scan 仅 ${N:-0} 条"; fi

echo "== 3. 阶段闸门正反例 =="
D="$TMP/round"; mkdir -p "$D"
if python3 "$S/gate_artifacts.py" "$D" --stage review >/dev/null 2>&1; then bad "缺工件应 FAIL"; else ok "缺工件正确 FAIL"; fi
printf '# findings\n' > "$D/01-findings.md"
printf 'claim_id,verdict\n' > "$D/claims.csv"
printf '{"files":[]}' > "$D/manifest.json"
if python3 "$S/gate_artifacts.py" "$D" --stage review --level L1 >/dev/null 2>&1; then ok "补齐后 PASS（L1）"; else bad "补齐后仍 FAIL"; fi

echo "== 4. 最小 xlsx：盘点 / 引用一致性 / 残留 / 清理幂等 =="
X="$TMP/fixture.xlsx"
python3 - "$X" <<'PY' || { bad "fixture 生成失败"; exit 1; }
import sys, zipfile
ct = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
      '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
      '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
      '<Default Extension="xml" ContentType="application/xml"/>'
      '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
      '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
      '<Override PartName="/docProps/custom.xml" ContentType="application/vnd.openxmlformats-officedocument.custom-properties+xml"/></Types>')
rels = ('<?xml version="1.0"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
wb = ('<?xml version="1.0"?>'
      '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
      'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
      '<sheets><sheet name="S1" sheetId="1" r:id="rId1"/></sheets></workbook>')
wbrels = ('<?xml version="1.0"?>'
          '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
          '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>')
sheet = ('<?xml version="1.0"?>'
         '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
         '<row r="1"><c r="A1" t="inlineStr"><is><t>hello</t></is></c></row>'
         '<row r="2"><c r="B3" t="inlineStr"><is><t>bad</t></is></c></row>'
         '</sheetData></worksheet>')
custom = ('<?xml version="1.0"?>'
          '<op:Properties xmlns:op="http://schemas.openxmlformats.org/officeDocument/2006/custom-properties" '
          'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'
          '<op:property fmtid="{D5CDD505-2E9C-101B-9397-08002B2CF9AE}" pid="2" name="OfficeCLI.Version">'
          '<vt:lpwstr>test</vt:lpwstr></op:property></op:Properties>')
with zipfile.ZipFile(sys.argv[1], 'w', zipfile.ZIP_DEFLATED) as z:
    z.writestr('[Content_Types].xml', ct)
    z.writestr('_rels/.rels', rels)
    z.writestr('xl/workbook.xml', wb)
    z.writestr('xl/_rels/workbook.xml.rels', wbrels)
    z.writestr('xl/worksheets/sheet1.xml', sheet)
    z.writestr('docProps/custom.xml', custom)
PY
python3 - "$X" "$TMP/inv" <<'PY' && ok "盘点：引用不一致+残留被检出" || bad "盘点断言失败"
import json, subprocess, sys
xlsx, out = sys.argv[1], sys.argv[2]
subprocess.run(['python3', 'scripts/inventory_xlsx.py', xlsx, out], check=True,
               capture_output=True)
d = json.load(open(f'{out}/inventory.json'))
s = d['sheets'][0]
assert s['row_count'] == 2, s
mm = s['cell_ref_mismatch']
assert mm and mm[0]['cell'] == 'B3' and mm[0]['row'] == 2, mm
assert 'OfficeCLI.Version' in d['tool_residue'], d['tool_residue']
PY
if python3 "$S/final_clean.py" "$X" | grep -q 'removed=是'; then ok "final_clean 清除残留"; else bad "final_clean 未清除"; fi
if python3 "$S/final_clean.py" "$X" | grep -q '已干净'; then ok "final_clean 幂等"; else bad "final_clean 不幂等"; fi
if python3 "$S/inventory_xlsx.py" "$X" "$TMP/inv2" 2>/dev/null | grep -q 'residue=无'; then ok "清理后残留=无"; else bad "清理后仍有残留"; fi

echo "== 5. 快照 diff 自比 =="
python3 "$S/diff_snapshot.py" snap --out "$TMP/snapA" "$X" >/dev/null 2>&1
if python3 "$S/diff_snapshot.py" diff "$TMP/snapA" "$TMP/snapA" --out "$TMP/d.md" 2>/dev/null | grep -q 'changed=0'; then
  ok "diff 自比 changed=0"
else
  bad "diff 自比异常"
fi

echo "== 6. 链接核验错误处理 =="
if python3 "$S/check_links.py" 'http://127.0.0.1:9/x' 2>/dev/null | grep -q 'ERROR'; then
  ok "不可达 URL 返回 ERROR 不崩溃"
else
  bad "错误处理异常"
fi

echo "==== 结果：PASS=$PASS FAIL=$FAIL ===="
[ "$FAIL" = 0 ]
