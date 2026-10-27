#!/usr/bin/env python3
"""final_clean.py — 交付前最后一步：zip 级清除 OfficeCLI.* 自定义属性（幂等）

用法: final_clean.py FILE [FILE...]

为什么不用 officecli：officecli 每次保存（包括只读访问触发的驻留刷新）都会
重新写入 OfficeCLI.Version / OfficeCLI.LastModified，清理后随下一次访问即复原；
zip 级重写是唯一可靠的清理方式。执行本脚本后，不要再对交付文件做任何 officecli
写/读操作；如必须验证，用本脚本或 diff_snapshot.py（纯 python）。

处理方式：重写 docProps/custom.xml，删除 name 以 OfficeCLI. 开头的 <property>
元素（兼容 op: 前缀与默认命名空间两种写法），其余字节原样保留。
"""

import sys, re, zipfile, shutil, os

PAT = re.compile(
    r'<(?:\w+:)?[Pp]roperty[^>]*name="OfficeCLI\.[^"]*"[^>]*/>'
    r'|<(?:\w+:)?[Pp]roperty[^>]*name="OfficeCLI\.[^"]*"[^>]*>.*?</(?:\w+:)?[Pp]roperty>',
    re.S,
)
EMPTY = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n'
    '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/custom-properties"/>'
)


def clean(path):
    tmp = path + ".cleaning"
    changed = False
    with (
        zipfile.ZipFile(path) as zin,
        zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout,
    ):
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "docProps/custom.xml":
                xml = data.decode("utf-8", "ignore")
                new = PAT.sub("", xml)
                if new != xml:
                    changed = True
                # 全部属性被删光则写空根，避免空壳元素
                if not re.search(r'name="', new):
                    new = EMPTY
                data = new.encode("utf-8")
            zout.writestr(item, data)
    shutil.move(tmp, path)
    # 复核
    with zipfile.ZipFile(path) as z:
        ok = z.testzip() is None
        names = re.findall(
            r'name="([^"]*)"', z.read("docProps/custom.xml").decode("utf-8", "ignore")
        )
    return changed, ok, names


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    for path in sys.argv[1:]:
        changed, ok, names = clean(path)
        print(
            f"{path}: removed={'是' if changed else '否（已干净）'} zip_ok={ok} 剩余属性={names}"
        )


if __name__ == "__main__":
    main()
