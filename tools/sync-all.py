#!/usr/bin/env python3
"""一条命令完成：生成令牌 -> 校验 -> 推送三个仓库到 GitHub。

用法:
    set GITHUB_TOKEN=ghp_xxx
    python sync-all.py                 # 全流程
    python sync-all.py --no-push       # 只生成 + 校验
    python sync-all.py --dry-run       # 只生成 + 校验 + 列出待推送文件

没设 GITHUB_TOKEN 时会提示你输入（不回显），只问一次，三个仓库复用。
"""
from __future__ import annotations

import argparse
import getpass
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DESIGN = HERE.parent / "design"
APP_ROOT = HERE.parent.parent  # D:/.dswork/App


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

TARGETS = [
    ("Suite",     APP_ROOT / "suite"),
    ("ChinGlish", APP_ROOT / "ChinGlish"),
    ("ToDoList",  APP_ROOT / "ToDoList"),
]


def load_publisher():
    spec = importlib.util.spec_from_file_location("publisher", HERE / "publish.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def run_gen(check: bool) -> int:
    cmd = [sys.executable, str(DESIGN / "gen.py")]
    if check:
        cmd.append("--check")
    print("$", " ".join(cmd))
    return subprocess.call(cmd)


def main() -> int:
    _utf8_console()
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-push", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    print("=== 1/3 生成设计令牌 ===")
    if run_gen(check=False) != 0:
        print("生成失败")
        return 1

    print("\n=== 2/3 校验漂移 ===")
    if run_gen(check=True) != 0:
        print("校验未通过")
        return 1

    if args.no_push:
        print("\n已跳过推送。")
        return 0

    print("\n=== 3/3 推送 GitHub ===")
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        token = getpass.getpass("GitHub Personal Access Token（输入不回显）: ").strip()
    if not token:
        print("没有 token，退出。")
        return 1

    publisher = load_publisher()
    original_environ = os.environ.copy()
    os.environ["GITHUB_TOKEN"] = token
    failures = []
    try:
        for repo, root in TARGETS:
            print(f"\n--- {repo} ({root})")
            argv = ["publish.py", "--root", str(root), "--repo", repo]
            if args.dry_run:
                argv.append("--dry-run")
            saved, sys.argv = sys.argv, argv
            try:
                code = publisher.main()
            finally:
                sys.argv = saved
            if code != 0:
                failures.append(repo)
    finally:
        os.environ.clear()
        os.environ.update(original_environ)

    if failures:
        print(f"\n以下仓库失败: {', '.join(failures)}")
        return 1
    print("\n全部同步完成。")
    return 0


if __name__ == "__main__":
    sys.exit(main())