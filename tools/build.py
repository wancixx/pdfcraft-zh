#!/usr/bin/env python3
"""从 tools/script_template.py 与 pdfcraft-zh.patch 生成 pdfcraft-zh.py。

模板里有一行 `CODE_PATCH = r'''__CODE_PATCH__'''`；本脚本把占位符替换成补丁内容，
得到单文件、自包含的发布版脚本。改动补丁或模板后重新运行本脚本即可。
"""
from pathlib import Path
import sys

here = Path(__file__).resolve().parent
root = here.parent

tpl = (here / "script_template.py").read_text(encoding="utf-8")
patch = (root / "pdfcraft-zh.patch").read_text(encoding="utf-8")

if "__CODE_PATCH__" not in tpl:
    sys.exit("error: tools/script_template.py 里找不到 __CODE_PATCH__ 占位符")
if "'''" in patch:
    sys.exit("error: 补丁里含三引号，会破坏模板的 raw string")

out = root / "pdfcraft-zh.py"
out.write_text(tpl.replace("__CODE_PATCH__", patch), encoding="utf-8")
print(f"已生成 {out}  ({out.stat().st_size:,} 字节)")
