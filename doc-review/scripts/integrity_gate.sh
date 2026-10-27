#!/usr/bin/env bash
# integrity_gate.sh — 交付门禁：validate + issues + 占位符 + 工具残留
# 用法: integrity_gate.sh FILE [FILE...]
#
# 注意：本脚本使用 officecli（会触发 OfficeCLI.* 属性重写）。
# 正确顺序：integrity_gate → final_clean.py → 交付（此后不再用 officecli 触碰文件）。
set -uo pipefail
FAIL=0
for FILE in "$@"; do
  echo "==== $FILE ===="
  V=$(officecli validate "$FILE" 2>&1 | tail -1)
  echo "validate: $V"
  case "$V" in *passed*|*"no error"*|*通过*) ;; *) FAIL=1 ;; esac

  I=$(officecli view "$FILE" issues 2>&1 | grep -E '^Found' || true)
  echo "issues:   ${I:-（无输出）}"

  P=$(python3 - "$FILE" <<'PY'
import zipfile, re, sys
p = sys.argv[1]
hits, residue = [], []
try:
    z = zipfile.ZipFile(p)
    for n in z.namelist():
        if n.startswith('xl/worksheets/') or n in ('xl/sharedStrings.xml',) or n == 'word/document.xml':
            t = z.read(n).decode('utf-8', 'ignore')
            for m in re.finditer(r'>[^<]*(?:\bTODO\b|\bTBD\b|lorem|\{var\}|\$xxx\$|FILLME)[^<]*<', t, re.I):
                frag = m.group(0)[1:-1].strip()[:60]
                if frag:
                    hits.append(f'{n}: {frag}')
    if 'docProps/custom.xml' in z.namelist():
        residue = [x for x in re.findall(r'name="([^"]*)"', z.read('docProps/custom.xml').decode('utf-8', 'ignore'))
                   if x.startswith('OfficeCLI')]
except Exception as e:
    print(f'检查异常: {e}')
print('placeholders:', '; '.join(hits) if hits else '无')
print('residue:', '; '.join(residue) if residue else '无')
PY
)
  echo "$P" | sed 's/^/  /'
  echo "$P" | grep -q 'placeholders: 无' || FAIL=1
  echo "$P" | grep -q 'residue: 无' || echo "  （残留需 final_clean.py 处理——见输出末尾）"
done
echo "----"
if [ "$FAIL" = 0 ]; then
  echo "GATE: PASS（validate 通过、无占位符）"
else
  echo "GATE: FAIL"
fi
echo "提醒：如上步出现 residue，交付前最后一步执行 scripts/final_clean.py，此后不再用 officecli 触碰文件。"
exit $FAIL
