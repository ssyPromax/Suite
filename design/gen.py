#!/usr/bin/env python3
"""从 tokens.json 生成各 app 的设计令牌文件。

用法:
    python gen.py            # 生成并写入
    python gen.py --check    # 只校验，不写（有漂移时退出码 1）
    python gen.py --dry-run  # 打印将生成的内容

设计原则:
    tokens.json 是唯一真源；apps.json 只描述"哪个 app 用哪个名字"。
    新增 app：在 apps.json 加一条，跑一次 gen.py。
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOKENS_PATH = HERE / "tokens.json"
APPS_PATH = HERE / "apps.json"

GENERATED_BANNER = (
    "GENERATED FILE - DO NOT EDIT.\n"
    "来源: suite/design/tokens.json\n"
    "重新生成: python D:/.dswork/App/suite/design/gen.py"
)


def _utf8_console() -> None:
    """让 Windows 控制台正确显示中文。"""
    if sys.platform == "win32":
        try:
            os.system("chcp 65001 >nul")
        except Exception:
            pass
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


# ---------------------------------------------------------------- token 解析
def load(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def resolve_color(name: str, scheme: str, tokens: dict, app: dict) -> str:
    """把一个 app 侧颜色名解析成最终色值。

    支持三种写法：
      "bg"          -> tokens.color.<scheme>.bg
      "@accent"     -> 别名，指向另一个 token
      (字符串字面量不需要经过这里)
    """
    seen = set()
    while True:
        key = name
        if key.startswith("@"):
            key = key[1:]
        if key in seen:
            raise ValueError(f"颜色别名出现循环: {name}")
        seen.add(key)
        palette = tokens["color"][scheme]
        if key in palette:
            return palette[key]
        if key in app.get("literals", {}):
            return app["literals"][key][scheme]
        raise KeyError(f"{app['id']}: 颜色 '{name}' 在 tokens.json 的 {scheme} 里找不到")


def xml_escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def banner_comment() -> str:
    lines = "\n".join("    " + line for line in GENERATED_BANNER.splitlines())
    return f"    <!--\n{lines}\n    -->"


# ---------------------------------------------------------------- XML 目标
def render_colors_xml(app: dict, tokens: dict, scheme: str) -> str:
    app = {**app, "literals": app.get("literals", {})}
    entries = []
    for app_name, token_name in app["colors"].items():
        value = resolve_color(token_name, scheme, tokens, app)
        entries.append(f'    <color name="{app_name}">{xml_escape(value)}</color>')
    for literal_name, modes in app.get("literals", {}).items():
        entries.append(f'    <color name="{literal_name}">{xml_escape(modes[scheme])}</color>')

    header = '<?xml version="1.0" encoding="utf-8"?>'
    return "\n".join([header, "<resources>", banner_comment(), "", *entries, "</resources>", ""])


def render_dimens_xml(tokens: dict) -> str:
    entries = []
    for name, value in tokens["radius"].items():
        entries.append(f'    <dimen name="ds_radius_{name}">{value}dp</dimen>')
    entries.append("")
    for name, value in tokens["space"].items():
        entries.append(f'    <dimen name="ds_space_{name}">{value}dp</dimen>')
    entries.append("")
    for name, spec in tokens["type"].items():
        entries.append(f'    <dimen name="ds_text_{name}">{spec["size"]}sp</dimen>')

    header = '<?xml version="1.0" encoding="utf-8"?>'
    return "\n".join([header, "<resources>", banner_comment(), "", *entries, "</resources>", ""])


# ---------------------------------------------------------------- Kotlin 目标
def kotlin_hex(color: str) -> str:
    value = color.lstrip("#").upper()
    if len(value) == 6:
        value = "FF" + value
    return f"0x{value}"


def render_kotlin(app: dict, tokens: dict) -> str:
    pkg = app["package"]

    def palette_block(scheme: str, object_name: str) -> str:
        # 与 XML 目标一致：允许 app 在 tokens 之外用 literals 记录自己的颜色
        # （例如 Inter 的坐标网格和三色曲线），避免绕过生成器手写色值。
        lines = [f"val {object_name} = DsPalette("]
        for prop, token_name in app["colors"].items():
            value = resolve_color(token_name, scheme, tokens, app)
            lines.append(f"    {prop} = Color({kotlin_hex(value)}),")
        lines.append(")")
        return "\n".join(lines)

    radius_lines = "\n".join(
        f"    val {name} = {value}.dp" for name, value in tokens["radius"].items() if value < 500
    )
    space_lines = "\n".join(f"    val {name} = {value}.dp" for name, value in tokens["space"].items())
    type_lines = "\n".join(
        f"    val {name} = DsText({spec['size']}.sp, FontWeight({spec['weight']}))"
        for name, spec in tokens["type"].items()
    )
    palette_props = "\n".join(
        f"    val {prop}: Color," for prop in app["colors"]
    )

    return f"""// {GENERATED_BANNER.replace(chr(10), chr(10) + '// ')}
package {pkg}

import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/** 各 app 共用的语义配色。字段名由 apps.json 决定，值来自 tokens.json。 */
data class DsPalette(
{palette_props}
)

data class DsText(val size: androidx.compose.ui.unit.TextUnit, val weight: FontWeight)

{palette_block("light", "DsLightPalette")}

{palette_block("dark", "DsDarkPalette")}

object DsRadius {{
{radius_lines}
}}

object DsSpace {{
{space_lines}
}}

object DsType {{
{type_lines}
}}
"""


# ---------------------------------------------------------------- 调度
def render_for_app(app: dict, tokens: dict) -> dict[str, str]:
    """返回 {相对路径: 文件内容}。"""
    kind = app["kind"]
    outputs = app.get("outputs", {})
    files: dict[str, str] = {}

    if kind == "android-xml":
        files[outputs["colorsXml"]] = render_colors_xml(app, tokens, "light")
        files[outputs["colorsXmlDark"]] = render_colors_xml(app, tokens, "dark")
        if "dimensXml" in outputs:
            files[outputs["dimensXml"]] = render_dimens_xml(tokens)
    elif kind == "android-compose":
        files[outputs["kotlin"]] = render_kotlin(app, tokens)
    else:
        raise ValueError(f"{app['id']}: 未知的 kind '{kind}'")

    return files


def main() -> int:
    _utf8_console()
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="只校验不写入")
    parser.add_argument("--dry-run", action="store_true", help="打印内容不写入")
    args = parser.parse_args()

    tokens = load(TOKENS_PATH)
    apps = load(APPS_PATH)["apps"]

    drift = 0
    written = 0

    for app in apps:
        root = Path(app["root"])
        if not root.is_dir():
            print(f"[跳过] {app['id']}: 根目录不存在 {root}")
            continue

        for rel, content in render_for_app(app, tokens).items():
            target = root / rel

            if args.dry_run:
                print(f"===== {target}")
                print(content)
                continue

            existing = target.read_text(encoding="utf-8") if target.exists() else None

            if args.check:
                if existing == content:
                    print(f"[ok]   {app['id']}: {rel}")
                else:
                    drift += 1
                    print(f"[DRIFT] {app['id']}: {rel}")
                    if existing is not None:
                        diff = difflib.unified_diff(
                            existing.splitlines(),
                            content.splitlines(),
                            fromfile="on-disk",
                            tofile="tokens.json",
                            lineterm="",
                        )
                        for line in list(diff)[:40]:
                            print("        " + line)
                    else:
                        print("        (文件不存在)")
                continue

            if existing != content:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8", newline="\n")
                written += 1
                print(f"[写入] {app['id']}: {rel}")
            else:
                print(f"[不变] {app['id']}: {rel}")

    if args.check:
        if drift:
            print(f"\n发现 {drift} 处漂移。运行 gen.py 同步，或改 tokens.json 后重新生成。")
            return 1
        print("\n全部一致。")
        return 0

    if args.dry_run:
        return 0

    if written == 0:
        print("\n无需改动，已是最新。")
    else:
        print(f"\n完成，写入 {written} 个文件。")
    return 0


if __name__ == "__main__":
    sys.exit(main())