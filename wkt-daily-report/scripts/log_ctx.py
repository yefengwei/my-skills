#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
WKT 日报 - 工作上下文记录（跨 agent 共用）

把「某个 agent / 某个会话当天做的工作」追加到统一的按日期命名的 context 文件：
    D:/yefengwei/wkt/公共盘/日报/context/YYYY-MM-DD.md

为什么要这个文件：
  同一台机器上可能有多个 agent（主会话、子 agent、其他 AI 工具）分别干了一天的活，
  每个 agent 收尾时把当天实质工作追加一条到这里；之后无论哪个 agent 要填日报，
  读这个文件就能汇总「今天到底做了哪些事」，而不是只凭用户口头清单。

⚠️ 只记什么（用户 2026-09-03 明确，违反会被要求重置）：
  只记围绕 D:/yefengwei/wkt 的【软件开发】工作（业务开发/修复/联调/需求/会议/技术文档）。
  agent 自身的工具搭建（含本日报 skill 的开发迭代）、环境配置、非公司事务一律不记。
  判断标准：写进给主管的日报里，主管会认为"这是在开发公司系统"吗？

格式（纯文本 Markdown，只追加、不改历史，人和 agent 都能读写）：
    # 2026-09-03 工作上下文
    - [17:20] [source: erp-be] 报价管理：完成包装运费计算接口与公式对齐

用法：
  python log_ctx.py --source "workbuddy-main" --msg "完成了 xxx"
  python log_ctx.py --date 2026-09-03 --source "erp-fe" --msg "..." --tag 报价管理
  python log_ctx.py --date 2026-09-03 --list          # 打印当日已记录的上下文
  python log_ctx.py --date 2026-09-03 --clear         # 清空当日文件（慎重）

--msg 较长时可从 stdin 传入：echo "..." | python log_ctx.py --source x --msg -
"""

import argparse
import datetime as dt
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(HERE)
CONFIG_PATH = os.path.join(SKILL_DIR, "config.json")


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def ctx_path(cfg, d):
    outdir = os.path.join(cfg["output_dir"], "context")
    os.makedirs(outdir, exist_ok=True)
    return os.path.join(outdir, f"{d.isoformat()}.md")


def ensure_file(path, d):
    """文件不存在则创建并写入标题行"""
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"# {d.isoformat()} 工作上下文\n\n")
            f.write("<!-- 规则：只追加，不改历史。每人/每 agent 一行：")
            f.write("- [HH:MM] [source: 来源] 工作内容。写日报时会读取本文件参与分析。 -->\n")
            f.write("<!-- ⚠️ 只记围绕 D:/yefengwei/wkt 的【软件开发】工作（业务开发/修复/联调/需求/会议/文档）。")
            f.write("agent 自身工具搭建（含日报 skill）、环境配置、非公司事务一律不记。 -->\n\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="YYYY-MM-DD，默认今天")
    ap.add_argument("--source", default="agent", help="来源标识，如 workbuddy-main / erp-fe / 本人")
    ap.add_argument("--tag", help="可选模块标签，如 报价管理 / IT资产")
    ap.add_argument("--msg", help="工作内容；传 - 则从 stdin 读取")
    ap.add_argument("--file", help="覆盖默认文件路径（一般不需要）")
    ap.add_argument("--list", action="store_true", help="打印当日 context 内容")
    ap.add_argument("--clear", action="store_true", help="清空当日 context（慎重）")
    args = ap.parse_args()

    cfg = load_config()
    d = dt.date.fromisoformat(args.date) if args.date else dt.date.today()
    path = args.file or ctx_path(cfg, d)
    ensure_file(path, d)

    # ---- list / clear ----
    if args.list:
        with open(path, "r", encoding="utf-8") as f:
            print(f.read())
        return
    if args.clear:
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"# {d.isoformat()} 工作上下文\n\n")
        print(json.dumps({"ok": True, "action": "clear", "file": path}, ensure_ascii=False))
        return

    # ---- append ----
    msg = args.msg
    if msg == "-":
        msg = sys.stdin.read().strip()
    if not msg:
        print(json.dumps({"ok": False, "error": "no_msg"}, ensure_ascii=False))
        sys.exit(1)

    now = dt.datetime.now().strftime("%H:%M")
    tag = f"[{args.tag}] " if args.tag else ""
    lines = msg.splitlines()
    entry_lines = [f"- [{now}] [source: {args.source}] {tag}{lines[0]}"]
    entry_lines += [f"    {ln}" for ln in lines[1:]]

    with open(path, "a", encoding="utf-8") as f:
        f.write("\n".join(entry_lines) + "\n")

    print(json.dumps({
        "ok": True, "action": "append", "file": path,
        "source": args.source, "lines": len(lines),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
