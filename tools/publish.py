#!/usr/bin/env python3
"""把一个目录同步到 GitHub 仓库（Git Data API，不需要 git 命令行）。

用法:
    python publish.py --root D:/.../suite --repo Suite
    python publish.py --root D:/.../ChinGlish --repo ChinGlish

    --dry-run   只列文件，不联网
    --replace   完全镜像（会删掉远端多余的文件）；默认是"合并"，保留远端已有文件

Token 来源（按顺序）:
    1. 环境变量 GITHUB_TOKEN / GH_TOKEN
    2. Windows 用户环境变量（注册表）
    3. 交互输入（不回显）

注意: token 只从上面三处读取，绝不写入任何文件或提交内容。
"""
from __future__ import annotations

import argparse
import base64
import fnmatch
import getpass
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

API = "https://api.github.com"
OWNER = "ssyPromax"
MAX_BLOB = 95 * 1024 * 1024

DESCRIPTIONS = {
    "Suite": "dswork-suite — 多应用共用的设计令牌与生成器（单一真源）",
    "ChinGlish": "ChinGlish — 本地离线中英词典 + DeepSeek 问答 App",
    "ToDoList": "List — 极简安卓待办 / 日程 App（Kotlin + Jetpack Compose）",
}

# 永远不提交的东西（防止令牌、密钥、私货外泄）
SECRET_PATTERNS = [
    ".env", ".env.*", "*.token", "*.secret", "*token*.txt", "secrets/", ".secrets/",
    "*.keystore", "*.jks", "id_rsa*", ".credentials*",
]


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
    return getpass.getpass("GitHub Personal Access Token（输入不回显）: ").strip()


def headers(token: str) -> dict:
    return {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "dswork-publisher",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def call(token, method, url, body=None, raw=False, attempts=3):
    data = None
    hdrs = headers(token)
    if body is not None:
        if raw:
            data = body
        else:
            data = json.dumps(body).encode("utf-8")
            hdrs["Content-Type"] = "application/json"

    last_error = None
    for attempt in range(attempts):
        req = urllib.request.Request(url, data=data, method=method, headers=hdrs)
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                payload = resp.read()
                return resp.status, json.loads(payload) if payload else {}
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")
            if e.code in (500, 502, 503, 504) and attempt + 1 < attempts:
                last_error = f"{e.code} {detail[:120]}"
                time.sleep(1.5 * (attempt + 1))
                continue
            return e.code, {"error": detail}
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as e:
            last_error = str(e)
            if attempt + 1 < attempts:
                print(f"  [重试 {attempt + 1}/{attempts - 1}] {type(e).__name__}: {last_error[:100]}")
                time.sleep(1.5 * (attempt + 1))
                continue
            raise
    return 599, {"error": last_error}


# ------------------------------------------------------------------ gitignore
def load_ignore_rules(root: Path) -> list[str]:
    gi = root / ".gitignore"
    if not gi.is_file():
        return []
    rules = []
    for line in gi.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("!"):
            continue
        rules.append(line)
    return rules


def ignored(rel_posix: str, rules: list[str]) -> bool:
    parts = rel_posix.split("/")
    for pattern in SECRET_PATTERNS:
        for cand in [rel_posix, *parts]:
            if fnmatch.fnmatch(cand, pattern):
                return True
    for rule in rules:
        r = rule.rstrip("/")
        anchored = r.startswith("/")
        r = r.lstrip("/")
        candidates = [rel_posix] if anchored else [rel_posix, *parts]
        patterns = [r] if anchored else [r, f"*/{r}"]
        for cand in candidates:
            for pat in patterns:
                if fnmatch.fnmatch(cand, pat) or fnmatch.fnmatch(cand, pat + "/*"):
                    return True
        if "/" not in r and not anchored:
            for part in parts[:-1]:
                if fnmatch.fnmatch(part, r):
                    return True
    return False


def collect(root: Path, rules: list[str]) -> list[Path]:
    out = []
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(root).as_posix()
        if rel.startswith(".git/"):
            continue
        if ignored(rel, rules):
            continue
        if p.stat().st_size > MAX_BLOB:
            print(f"  [跳过] 超过 95MB: {rel}")
            continue
        out.append(p)
    return out


# ------------------------------------------------------------------ 远端状态
def remote_state(token, owner: str, repo: str):
    """返回 (head_sha, {path: blob_sha})；仓库为空时返回 (None, {})。"""
    status, ref = call(token, "GET", f"{API}/repos/{owner}/{repo}/git/ref/heads/main")
    if status != 200:
        return None, {}
    head = ref["object"]["sha"]
    status, commit = call(token, "GET", f"{API}/repos/{owner}/{repo}/git/commits/{head}")
    if status != 200:
        return head, {}
    status, tree = call(token, "GET",
                        f"{API}/repos/{owner}/{repo}/git/trees/{commit['tree']['sha']}?recursive=1")
    if status != 200:
        return head, {}
    return head, {e["path"]: e["sha"] for e in tree.get("tree", []) if e["type"] == "blob"}


# ------------------------------------------------------------------ 主流程
def main() -> int:
    _utf8_console()
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True, help="要发布的本地目录")
    ap.add_argument("--repo", required=True, help="GitHub 仓库名")
    ap.add_argument("--owner", default=OWNER)
    ap.add_argument("--message", default="", help="提交信息")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--replace", action="store_true", help="完全镜像，删除远端多余文件")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"目录不存在: {root}")
        return 1

    rules = load_ignore_rules(root)
    files = collect(root, rules)
    total_mb = sum(f.stat().st_size for f in files) / 1024 / 1024
    print(f"本地待推: {len(files)} 个文件（{total_mb:.1f} MB）")
    for f in files[:10]:
        print("   ", f.relative_to(root).as_posix())
    if len(files) > 10:
        print(f"    ... 还有 {len(files) - 10} 个")

    if args.dry_run:
        print("\n[DRY RUN] 未联网。")
        return 0

    token = get_token()
    if not token:
        print("没有拿到 token，退出。")
        return 1

    repo_url = f"{API}/repos/{args.owner}/{args.repo}"
    status, repo = call(token, "GET", repo_url)
    if status == 200:
        print(f"仓库已存在: {repo['full_name']}")
    elif status == 404:
        status, repo = call(token, "POST", f"{API}/user/repos", {
            "name": args.repo,
            "description": DESCRIPTIONS.get(args.repo, f"{args.repo} — dswork suite project"),
            "private": False,
            "has_issues": True,
            "has_wiki": False,
            "auto_init": False,
        })
        if status not in (200, 201):
            print("创建仓库失败", status, repo)
            return 1
        print(f"已创建仓库: {repo['full_name']}")
    else:
        print("读取仓库失败", status, repo)
        return 1

    head, existing = remote_state(token, args.owner, args.repo)
    if head is None:
        # 空仓库无法直接创建 blob，先用 Contents API 生成第一个提交
        print("空仓库，先做一次初始化提交 ...")
        status, boot = call(token, "PUT", f"{API}/repos/{args.owner}/{args.repo}/contents/.gitkeep",
                            {"message": "init", "content": ""})
        if status not in (200, 201):
            print("初始化失败", status, boot)
            return 1
        head, existing = remote_state(token, args.owner, args.repo)
    if existing and not args.replace:
        kept = len(set(existing) - {p.relative_to(root).as_posix() for p in files})
        print(f"合并模式：保留远端已有的 {kept} 个未管理文件")

    print("上传 blob ...")
    tree = {path: sha for path, sha in existing.items()} if not args.replace else {}
    for i, p in enumerate(files, 1):
        rel = p.relative_to(root).as_posix()
        status, blob = call(token, "POST", f"{API}/repos/{args.owner}/{args.repo}/git/blobs",
                            {"content": base64.b64encode(p.read_bytes()).decode("ascii"),
                             "encoding": "base64"})
        if status not in (200, 201):
            print(f"  失败 {rel}: {status} {blob}")
            return 1
        tree[rel] = blob["sha"]
        if i % 25 == 0:
            print(f"  {i}/{len(files)}")

    entries = [{"path": path, "mode": "100644", "type": "blob", "sha": sha}
               for path, sha in sorted(tree.items())]
    status, new_tree = call(token, "POST", f"{API}/repos/{args.owner}/{args.repo}/git/trees",
                            {"tree": entries})
    if status not in (200, 201):
        print("创建 tree 失败", status, new_tree)
        return 1

    message = args.message or f"sync: {len(files)} files from {root.name}"
    parents = [head] if head else []
    status, commit = call(token, "POST", f"{API}/repos/{args.owner}/{args.repo}/git/commits",
                          {"message": message, "tree": new_tree["sha"], "parents": parents})
    if status not in (200, 201):
        print("创建 commit 失败", status, commit)
        return 1

    if parents:
        status, _ = call(token, "PATCH", f"{API}/repos/{args.owner}/{args.repo}/git/refs/heads/main",
                         {"sha": commit["sha"], "force": False})
    else:
        status, _ = call(token, "POST", f"{API}/repos/{args.owner}/{args.repo}/git/refs",
                         {"ref": "refs/heads/main", "sha": commit["sha"]})
    if status not in (200, 201):
        print("更新分支失败", status)
        return 1

    print(f"\n完成: https://github.com/{args.owner}/{args.repo}/commit/{commit['sha'][:8]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())