#!/usr/bin/env python3
"""给 GitHub 仓库批量加 GNU GPL v3 协议。

每个仓库做两件事：
  1. 在默认分支根目录写 LICENSE（GPL-3.0 官方原文，逐字不改）
  2. 在 README 末尾追加「许可证」一节（已存在则跳过）

用法:
    python apply-license.py --repos ChinGlish ToDoList Suite
    python apply-license.py --repos ... --dry-run
    python apply-license.py --repos ... --force   # 覆盖已有 LICENSE

不会碰 STranslate-doc 这类 fork：relicense 别人的代码是无效的。
"""
from __future__ import annotations

import argparse
import base64
import getpass
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

API = "https://api.github.com"
OWNER = "ssyPromax"
LICENSE_FILE = Path(__file__).resolve().parent / "license" / "GPL-3.0.txt"

SPDX = "GPL-3.0"


def _utf8_console() -> None:
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


def get_token() -> str:
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        return token.strip()
    if sys.platform == "win32":
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
                value, _ = winreg.QueryValueEx(key, "GITHUB_TOKEN")
                if value:
                    return str(value).strip()
        except Exception:
            pass
    return getpass.getpass("GitHub Token（不回显）: ").strip()


def headers(token: str) -> dict:
    return {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "dswork-license",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def call(token, method, url, body=None, attempts=3):
    import time

    data = json.dumps(body).encode("utf-8") if body is not None else None
    hdrs = headers(token)
    if body is not None:
        hdrs["Content-Type"] = "application/json"
    last = None
    for attempt in range(attempts):
        req = urllib.request.Request(url, data=data, method=method, headers=hdrs)
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                payload = resp.read()
                return resp.status, json.loads(payload) if payload else {}
        except urllib.error.HTTPError as e:
            return e.code, {"error": e.read().decode("utf-8", "replace")}
        except (urllib.error.URLError, OSError) as e:
            last = str(e)
            if attempt + 1 < attempts:
                time.sleep(1.5 * (attempt + 1))
                continue
            return 599, {"error": last}
    return 599, {"error": last}


def readme_section(year: int) -> str:
    span = f"{year}-2026" if year < 2026 else "2026"
    return f"""

---

## 许可证

本项目采用 [GNU General Public License v3.0](LICENSE)（{SPDX}）。

Copyright (C) {span} ssyPromax

你可以自由使用、修改和分发本项目的代码；如果你分发修改后的版本，
必须以同样的 GPL-3.0 协议公开源代码。
"""


def apply_repo(token, repo: str, license_text: str, created_year: int,
               force: bool, dry: bool) -> str:
    info = call(token, "GET", f"{API}/repos/{OWNER}/{repo}")[1]
    if not info.get("name"):
        return f"[失败] {repo}: 读不到仓库"
    branch = info.get("default_branch", "main")

    # ---- LICENSE ----
    status, existing = call(token, "GET", f"{API}/repos/{OWNER}/{repo}/contents/LICENSE")
    lic_sha = existing.get("sha") if status == 200 else None
    if lic_sha and not force:
        lic_action = "LICENSE 已存在，跳过"
    else:
        payload = {
            "message": ("chore: relicense to GPL-3.0" if lic_sha else "chore: add GNU GPL v3 license"),
            "content": base64.b64encode(license_text.encode("utf-8")).decode("ascii"),
            "branch": branch,
        }
        if lic_sha:
            payload["sha"] = lic_sha
        if dry:
            lic_action = "将写入 LICENSE"
        else:
            st, res = call(token, "PUT", f"{API}/repos/{OWNER}/{repo}/contents/LICENSE", payload)
            lic_action = "LICENSE 已写入" if st in (200, 201) else f"LICENSE 失败 {st} {res}"

    # ---- README ----
    status, rm = call(token, "GET", f"{API}/repos/{OWNER}/{repo}/readme")
    if status != 200:
        return f"{lic_action} | 无 README，未加说明"
    text = base64.b64decode(rm["content"]).decode("utf-8", "replace")
    if "GNU General Public License" in text or "GPL-3.0" in text:
        return f"{lic_action} | README 已包含协议说明"
    new_text = text.rstrip() + readme_section(created_year)
    payload = {
        "message": "docs: add license section",
        "content": base64.b64encode(new_text.encode("utf-8")).decode("ascii"),
        "sha": rm["sha"],
        "branch": branch,
    }
    if dry:
        return f"{lic_action} | 将追加 README 说明"
    st, res = call(token, "PUT", f"{API}/repos/{OWNER}/{repo}/contents/README.md", payload)
    rm_action = "README 已加说明" if st in (200, 201) else f"README 失败 {st} {res}"
    return f"{lic_action} | {rm_action}"


def main() -> int:
    _utf8_console()
    ap = argparse.ArgumentParser()
    ap.add_argument("--repos", nargs="+", required=True)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not LICENSE_FILE.is_file():
        print(f"缺少协议原文: {LICENSE_FILE}")
        return 1
    license_text = LICENSE_FILE.read_text(encoding="utf-8")
    if "GNU GENERAL PUBLIC LICENSE" not in license_text:
        print("协议原文看起来不对，已中止。")
        return 1

    token = get_token()
    if not token:
        print("没有 token")
        return 1

    failures = 0
    for repo in args.repos:
        info = call(token, "GET", f"{API}/repos/{OWNER}/{repo}")[1] if token else {}
        created = info.get("created_at", "2026-01-01T00:00:00Z") if info else "2026-01-01T00:00:00Z"
        year = int(created[:4])
        result = apply_repo(token, repo, license_text, year, args.force, args.dry_run)
        if "失败" in result:
            failures += 1
        print(f"{repo:-<28} {result}")

    print(f"\n完成，失败 {failures} 个。")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())