#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
WKT 日报 - 扫描当日 git 提交/暂存 + 当日修改文件，用于补充日报内容

扫描 git_root 下所有 git 仓库（默认深度 3），收集：
  1. 当天的本地提交 —— 扫所有本地分支（--branches），切过分支也不漏（含尚未 push 的）
  2. 暂存区（git add 过但没提交）的文件 —— 只收「文件修改日期在近 N 天内」的
     （N 默认 3：今日+昨天+前天，--mtime-days 可调），更早的遗留不计入
     （beyond_window 里给计数）
  3. 工作区改动 / 新增文件 —— 同样按近 N 天修改过滤
  4. today_modified / recent_modified：全树扫描修改日期在窗口内的代码文件
     （无论有无提交/暂存），标注 git 状态与修改时间。没提交也没 add 的当天
     工作全靠它兜底；今日素材少时用 recent_modified（昨天/前天）扩充。

排除：Markdown 文档、测试代码、锁文件、构建产物、图片字体等。

用法：
  python scan_git.py [--date 2026-09-03] [--root D:/yefengwei/wkt]
                     [--depth 3] [--with-diff] [--max-lines 120]
                     [--all-authors] [--no-tree] [--mtime-days 3]
                     [--out FILE]
"""

import argparse
import datetime as dt
import json
import os
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(HERE)
CONFIG_PATH = os.path.join(SKILL_DIR, "config.json")

REC = "\x1e"
FIELD = "\x1f"

# 视为「文档/测试/噪声」的路径特征
SKIP_EXT = {
    ".md", ".markdown", ".txt", ".lock", ".map", ".log",
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp", ".bmp",
    ".woff", ".woff2", ".ttf", ".eot", ".otf",
    ".pdf", ".xlsx", ".xls", ".docx", ".zip", ".rar", ".7z",
    ".min.js", ".min.css",
}
SKIP_DIR_PARTS = {
    "node_modules", "dist", "build", ".git", ".idea", ".vscode", "coverage",
    "vendor", "target", "out", ".plugin-review", ".workbuddy", "__pycache__",
    "docs", "doc", "public", "assets", "static",
}
TEST_DIR_PARTS = {"test", "tests", "spec", "specs", "__tests__", "e2e", "mock", "mocks", "fixtures"}

# 自动生成的噪声文件（构建/插件产物，mtime 频繁刷新但不是工作量）
SKIP_NAMES = {"auto-imports.d.ts", "components.d.ts", "typed-router.d.ts", "shims-vue.d.ts"}


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def run_git(repo, args, check=False):
    """执行 git 命令，返回 stdout（失败返回空串）

    固定加 -c core.quotepath=false，否则中文路径会被转义成 \\345\\205\\254 这种八进制。
    """
    try:
        p = subprocess.run(
            ["git", "-c", "core.quotepath=false"] + args,
            cwd=repo,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
        if p.returncode != 0 and check:
            return ""
        return p.stdout or ""
    except Exception as e:
        return f"__ERROR__{e}"


def should_skip(path):
    """判断文件是否需要排除（md / 测试 / 资源 / 构建产物）"""
    p = path.replace("\\", "/")
    lower = p.lower()
    base = os.path.basename(lower)

    # 扩展名
    for ext in SKIP_EXT:
        if lower.endswith(ext):
            return True

    parts = set(p.split("/"))
    if parts & SKIP_DIR_PARTS:
        return True
    if parts & TEST_DIR_PARTS:
        return True

    # 测试文件命名：XxxTest.java / XxxTests.java / xxx.test.js / xxx.spec.ts / test_xxx.py / xxx_test.go
    if base.endswith("test.java") or base.endswith("tests.java"):
        return True
    if base.endswith(".test.js") or base.endswith(".test.ts"):
        return True
    if base.endswith(".spec.js") or base.endswith(".spec.ts"):
        return True
    if base.startswith("test_") and base.endswith(".py"):
        return True
    if base.endswith("_test.go") or base.endswith("_test.py"):
        return True
    if base in {"conftest.py", "jest.config.js", "jest.setup.js"}:
        return True

    # 自动生成的声明文件（vite 插件产物，一跑 dev 就刷新，不算工作量）
    if base in SKIP_NAMES:
        return True
    return False


def find_repos(root, max_depth, skip_dirs, skip_repos=()):
    """找出 root 下所有 git 仓库

    wkt 目录本身也是仓库（一个工作区容器），子目录里才是真正的项目仓库，
    所以这里不因为发现 .git 就停止深入，而是继续找嵌套仓库；
    容器仓库可以用 config 的 git_skip_repos 排除。
    """
    repos = []
    root = os.path.abspath(root)
    skip_repos = {os.path.abspath(p).lower().rstrip("\\/") for p in skip_repos}
    for dirpath, dirnames, _filenames in os.walk(root):
        rel = os.path.relpath(dirpath, root)
        depth = 0 if rel == "." else len(rel.split(os.sep))
        # 到达深度上限就不再往下走
        if depth >= max_depth:
            dirnames[:] = []
        # 跳过噪声目录与隐藏目录（.git 本身也被这句过滤掉，避免走进版本库内部）
        dirnames[:] = [d for d in dirnames if d not in skip_dirs and not d.startswith(".")]
        try:
            entries = set(os.listdir(dirpath))
        except OSError:
            continue
        if ".git" in entries:
            if dirpath.lower().rstrip("\\/") not in skip_repos:
                repos.append(dirpath)
    return repos


def prune_nested(repo_results):
    """去掉「另一个仓库目录被父仓库当成未跟踪目录」的噪声"""
    repo_paths = {os.path.abspath(r["path"]).lower().rstrip("\\/") for r in repo_results}
    for r in repo_results:
        base = os.path.abspath(r["path"])

        def keep(entry):
            p = entry if isinstance(entry, str) else entry["path"]
            full = os.path.abspath(os.path.join(base, p.rstrip("/"))).lower().rstrip("\\/")
            return full not in repo_paths

        r["untracked"] = [x for x in r["untracked"] if keep(x)]
        r["unstaged"] = [x for x in r["unstaged"] if keep(x)]
    return repo_results


def parse_numstat(text):
    """git show --numstat 输出 -> [(path, add, del)]"""
    out = []
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) == 3 and parts[0].isdigit():
            out.append((parts[2], int(parts[0]), int(parts[1])))
    return out


def is_in_window_mtime(path, end_date, days):
    """文件 mtime 是否落在 [end_date-(days-1), end_date] 窗口内（本地时区，含 end_date 当天）

    days=1 即仅当天；days=3 即今天+昨天+前天。
    返回 (是否在窗口, 当天日期 iso 或 None)
    """
    try:
        mtime = dt.datetime.fromtimestamp(os.path.getmtime(path)).date()
    except OSError:
        return False, None
    start = end_date - dt.timedelta(days=days - 1)
    if start <= mtime <= end_date:
        return True, mtime.isoformat()
    return False, None


def collect_repo_state(repo):
    """汇总一个仓库里所有 git 感知到变动的文件路径 -> {状态: 路径列表}

    键：staged(已暂存) / unstaged(工作区已跟踪改动) / untracked(未跟踪)
    值元素为 (状态字母对, 相对路径)
    """
    state = {}
    for line in run_git(repo, ["status", "--porcelain"]).splitlines():
        if len(line) < 4:
            continue
        st, path = line[:2], line[3:].strip()
        if st == "??":
            state.setdefault("untracked", []).append((st, path))
        elif st.strip():
            key = "staged" if st[0] not in (" ", "?", "!") else "unstaged"
            # 既有暂存又有工作区改动(如 AM/MM)两边都记
            if st[0] not in (" ", "?", "!") and st[1] not in (" ", "?", "!"):
                state.setdefault("staged", []).append((st, path))
                state.setdefault("unstaged", []).append((st, path))
            else:
                state.setdefault(key, []).append((st, path))
    return state


def scan_repo(repo, date_str, authors, with_diff, max_lines, do_tree, mtime_days):
    """扫描单个仓库"""
    since = f"{date_str} 00:00:00"
    until = f"{date_str} 23:59:59"
    end_date = dt.date.fromisoformat(date_str)

    # 扫所有本地分支的当日提交（用户每个项目有多个本地分支，只扫 HEAD 会漏
    # 切走分支前做的提交）。--all 相比 HEAD 多出的正是本地其他分支。
    fmt = REC + "%H" + FIELD + "%h" + FIELD + "%an" + FIELD + "%ae" + FIELD + "%ad" + FIELD + "%s"
    raw = run_git(repo, [
        "log", "--all", f"--since={since}", f"--until={until}",
        f"--pretty=format:{fmt}",
        "--date=format:%Y-%m-%d %H:%M",
        "--name-only",
    ])

    # 未推送的提交（本地独有）
    unpushed = set(run_git(repo, ["log", "--format=%H", "@{u}..HEAD"]).split())
    branch = run_git(repo, ["rev-parse", "--abbrev-ref", "HEAD"]).strip()

    commits = []
    for chunk in raw.split(REC):
        chunk = chunk.strip("\n")
        if not chunk.strip():
            continue
        head, *rest = chunk.split("\n")
        fields = head.split(FIELD)
        if len(fields) < 6:
            continue
        _h, short, an, ae, ad, subject = fields[:6]
        if authors and an not in authors and ae.split("@")[0] not in authors:
            continue

        files = []
        for line in rest:
            line = line.strip()
            if not line or should_skip(line):
                continue
            files.append({"path": line})

        if not files:
            # 提交里全是 md/测试文件，仍记录提交主题（有信息量），但标记 no_code
            commits.append({
                "hash": short, "time": ad, "author": an, "subject": subject,
                "unpushed": _h in unpushed, "files": [], "no_code": True,
            })
            continue

        # 补充行数统计
        numstat = run_git(repo, ["show", "--numstat", "--format=", _h])
        stat_map = {}
        for path, add, dele in parse_numstat(numstat):
            stat_map[path.replace("\\", "/")] = (add, dele)
        for f in files:
            key = f["path"].replace("\\", "/")
            add, dele = stat_map.get(key, (None, None))
            f["add"], f["del"] = add, dele
            if with_diff:
                patch = run_git(repo, ["show", _h, "--", f["path"]])
                lines = patch.splitlines()
                if len(lines) > max_lines:
                    patch = "\n".join(lines[:max_lines]) + f"\n... [truncated {len(lines) - max_lines} lines]"
                f["patch"] = patch

        commits.append({
            "hash": short, "time": ad, "author": an, "subject": subject,
            "unpushed": _h in unpushed, "files": files,
        })

    # 暂存区 / 工作区改动 —— 只收「文件修改日期在近 N 天内」的条目，
    # 更早的遗留不算素材（beyond_window 只给计数供核对）
    repo_state = collect_repo_state(repo)
    staged, beyond_staged = [], []
    for st, path in repo_state.get("staged", []):
        if not should_skip(path):
            full = os.path.join(repo, path.replace("/", os.sep))
            in_win, mday = is_in_window_mtime(full, end_date, mtime_days)
            if in_win:
                entry = {"status": st, "path": path, "mtime_date": mday}
                if with_diff:
                    patch = run_git(repo, ["diff", "--cached", "--", path])
                    lines = patch.splitlines()
                    if len(lines) > max_lines:
                        patch = "\n".join(lines[:max_lines]) + f"\n... [truncated {len(lines) - max_lines} lines]"
                    entry["patch"] = patch
                staged.append(entry)
            else:
                beyond_staged.append(path)

    unstaged, beyond_unstaged = [], []
    for st, path in repo_state.get("unstaged", []):
        if should_skip(path):
            continue
        full = os.path.join(repo, path.replace("/", os.sep))
        in_win, mday = is_in_window_mtime(full, end_date, mtime_days)
        if in_win:
            unstaged.append({"status": st, "path": path, "mtime_date": mday})
        else:
            beyond_unstaged.append(path)

    # 未跟踪文件：git status 一次拿到，mtime 是文件真实修改时间
    untracked, beyond_untracked = [], []
    for st, path in repo_state.get("untracked", []):
        if should_skip(path):
            continue
        full = os.path.join(repo, path.replace("/", os.sep))
        in_win, mday = is_in_window_mtime(full, end_date, mtime_days)
        if in_win:
            untracked.append({"path": path, "mtime_date": mday})
        else:
            beyond_untracked.append(path)

    # recent_modified：全树扫描「修改日期在近 N 天内」的代码文件（兜底）。
    # 即使没提交、没 add，只要窗口内动过就收进来，并标注 git 状态与修改日期。
    # today_modified 是其中 date==目标日期的子集（日报当天主素材）。
    today_modified = []
    recent_modified = []
    if do_tree:
        skip_dirs = {"node_modules", "dist", "build", ".git", ".idea", ".vscode",
                     "vendor", "target", "out", "coverage", "__pycache__", ".workbuddy"}
        status_map = {}
        for key, items in repo_state.items():
            for st, path in items:
                status_map.setdefault(path.replace("\\", "/"), set()).add(key)
        for dirpath, dirnames, filenames in os.walk(repo):
            dirnames[:] = [d for d in dirnames if d not in skip_dirs and not d.startswith(".")]
            for name in filenames:
                p = os.path.join(dirpath, name)
                in_win, mday = is_in_window_mtime(p, end_date, mtime_days)
                if not in_win:
                    continue
                rel = os.path.relpath(p, repo).replace("\\", "/")
                if should_skip(rel):
                    continue
                entry = {
                    "path": rel,
                    "mtime_date": mday,
                    "mtime": dt.datetime.fromtimestamp(os.path.getmtime(p)).strftime("%H:%M"),
                    "git_state": "/".join(sorted(status_map.get(rel, {"committed-or-clean"}))) or "committed-or-clean",
                }
                recent_modified.append(entry)
                if mday == date_str:
                    today_modified.append(entry)
        recent_modified.sort(key=lambda x: (x["mtime_date"], x["mtime"]), reverse=True)

    if not (commits or staged or unstaged or untracked or recent_modified):
        return None

    result = {
        "repo": os.path.basename(repo),
        "path": repo.replace("\\", "/"),
        "branch": branch,
        "commits": commits,
        "staged": staged,
        "unstaged": unstaged,
        "untracked": untracked,
    }
    if do_tree:
        result["today_modified"] = today_modified
        result["recent_modified"] = recent_modified
        result["beyond_window"] = {
            "staged": len(beyond_staged),
            "unstaged": len(beyond_unstaged),
            "untracked": len(beyond_untracked),
        }
        result["tree_files_recent"] = len(recent_modified)
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="YYYY-MM-DD，默认今天")
    ap.add_argument("--root", help="扫描根目录")
    ap.add_argument("--depth", type=int, help="扫描深度")
    ap.add_argument("--with-diff", action="store_true", help="输出代码补丁")
    ap.add_argument("--max-lines", type=int, default=120, help="单文件补丁最大行数")
    ap.add_argument("--all-authors", action="store_true", help="不过滤作者，收集所有人的提交")
    ap.add_argument("--mtime-days", type=int, default=3,
                    help="暂存/工作区/全树扫描的文件修改日期窗口（天，含目标日，默认 3）")
    ap.add_argument("--no-tree", action="store_true",
                    help="关闭全树「近期修改文件」扫描（默认开启，兜底未提交未暂存的工作）")
    ap.add_argument("--out", help="结果写入文件（同时仍打印到 stdout）")
    args = ap.parse_args()

    cfg = load_config()
    date_str = args.date or dt.date.today().isoformat()
    root = args.root or cfg["git_root"]
    depth = args.depth or cfg["git_max_depth"]
    skip_dirs = set(cfg.get("git_skip_dirs", []))
    authors = None if args.all_authors else set(cfg.get("git_authors", []))
    do_tree = not args.no_tree
    mtime_days = args.mtime_days

    repos = find_repos(root, depth, skip_dirs, cfg.get("git_skip_repos") or [])
    results = []
    for repo in repos:
        r = scan_repo(repo, date_str, authors, args.with_diff, args.max_lines, do_tree, mtime_days)
        if r:
            results.append(r)
    results = prune_nested(results)

    commit_count = sum(len(r["commits"]) for r in results)
    file_count = sum(len(c["files"]) for r in results for c in r["commits"])
    out = {
        "ok": True,
        "date": date_str,
        "mtime_days": mtime_days,
        "root": root,
        "repos_scanned": len(repos),
        "summary": {
            "repo_count": len(results),
            "commit_count": commit_count,
            "changed_files": file_count,
            "staged_files": sum(len(r["staged"]) for r in results),
            "unstaged_files": sum(len(r["unstaged"]) for r in results),
            "untracked_files": sum(len(r["untracked"]) for r in results),
            "today_modified_files": sum(len(r.get("today_modified", [])) for r in results),
            "recent_modified_files": sum(len(r.get("recent_modified", [])) for r in results),
        },
        "repos": results,
    }
    text = json.dumps(out, ensure_ascii=False, indent=2)
    print(text)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)


if __name__ == "__main__":
    main()
