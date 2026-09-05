#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""全量重导（重建模式）：
对每个课程：删除整个课程节点 → 重建课程节点 → 按本地目录重建子目录 → 导入文档。
图片处理：embed_images.py 下载 webp→PNG→pandoc 嵌入 docx。
用法: python reimport_all.py --run   (不加 --run 仅探查)
"""
import os, sys, subprocess, time, json

LARK = r"C:/Users/Hollow2077/.workbuddy/binaries/node/cli-connector-packages/lark-cli.cmd"
SPACE_ID = "7493948997678137346"
PARENT = "L2Eqw2RTcicJYYkMsKucEgcDnXb"
EMBED = r"D:/Desktop/temp/.workbuddy/cdp-scraper/embed_images.py"
LOG = r"D:/Desktop/temp/ri_progress.log"

COURSES = [
    ("Vue3 + SpringBoot + AI + DDD 企业级智能协同云图库项目",
     "D:/Desktop/temp/Vue3 + SpringBoot + AI + DDD 企业级智能协同云图库项目"),
    ("SpringAI + RAG + MCP 全栈 ｜ AI 超级智能体企业级实战",
     "D:/Desktop/temp/SpringAI + RAG + MCP 全栈 ｜ AI 超级智能体企业级实战"),
    ("Python 全栈 ｜ AI 闯关学习小程序项目教程",
     "D:/Desktop/temp/Python 全栈 ｜ AI 闯关学习小程序项目教程"),
    ("LangChain4j + 工作流 + 微服务 AI 零代码应用生成平台",
     "D:/Desktop/temp/LangChain4j + 工作流 + 微服务 AI 零代码应用生成平台"),
    ("Next.js + Elasticsearch 智能面试刷题平台",
     "D:/Desktop/temp/Next.js + Elasticsearch 智能面试刷题平台"),
]

_env = dict(os.environ)
_env.pop("NODE_OPTIONS", None)
_cache = {}

def log(*a):
    s = " ".join(str(x) for x in a)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(time.strftime("%H:%M:%S ") + s + "\n")
    print(s, flush=True)

def run(args, cwd=None):
    try:
        p = subprocess.run([LARK] + args, capture_output=True, text=True,
                           encoding="utf-8", env=_env, cwd=cwd, timeout=120)
        out = p.stdout + p.stderr
    except subprocess.TimeoutExpired:
        return None, "TIMEOUT"
    i = out.find("{")
    if i < 0:
        return None, out
    try:
        d = json.JSONDecoder().raw_decode(out[i:])[0]
    except Exception:
        return None, out
    return d, out

def list_nodes(parent):
    if parent in _cache:
        return _cache[parent]
    for attempt in range(4):
        try:
            d, _ = run(["wiki", "+node-list", "--space-id", SPACE_ID,
                        "--parent-node-token", parent, "--page-all", "--format", "json"])
            nodes = (d or {}).get("data", {}).get("nodes", []) or []
            if nodes or attempt == 3:
                break
            time.sleep(1.5)
        except Exception as e:
            if attempt == 3:
                nodes = []
            time.sleep(1.5)
    _cache[parent] = nodes
    return nodes

def delete_node(token, obj_type="wiki"):
    d, raw = run(["wiki", "+node-delete", "--node-token", token,
                  "--obj-type", obj_type, "--space-id", SPACE_ID,
                  "--yes", "--format", "json"])
    return (d or {}).get("ok") is True, raw[:150]

def create_node(title, parent_token, obj_type="docx"):
    """建子节点。返回 node_token 或 None。"""
    d, raw = run(["wiki", "+node-create", "--space-id", SPACE_ID,
                  "--parent-node-token", parent_token, "--title", title,
                  "--obj-type", obj_type, "--format", "json"])
    tok = (d or {}).get("data", {}).get("node_token")
    return tok

def build_docx(md_path):
    stem = os.path.splitext(os.path.basename(md_path))[0]
    docx = os.path.join(os.path.dirname(md_path), stem + ".docx")
    # 已存在且比 md 新 → 直接复用（跳过图片下载/转换，大幅提速）
    if (os.path.exists(docx)
            and os.path.getmtime(docx) >= os.path.getmtime(md_path)
            and os.path.getsize(docx) > 0):
        return docx
    r = subprocess.run([sys.executable, EMBED, md_path], capture_output=True,
                       text=True, encoding="utf-8", cwd=os.path.dirname(md_path))
    return docx if os.path.exists(docx) else None

def import_move(filepath, parent_token):
    """导入 docx 到 Drive，再 move 到 wiki parent 下。返回 (ok, msg)。
    move 失败时重试 3 次（飞书偶发 validation 错误）。"""
    d, raw = run(["drive", "+import", "--file", os.path.basename(filepath),
                  "--type", "docx", "--as", "user", "--format", "json"],
                 cwd=os.path.dirname(filepath))
    token = (d or {}).get("data", {}).get("token")
    if not token:
        return False, "import:" + raw[:300]
    # move 到 wiki 节点（带重试）
    for attempt in range(4):
        d2, raw2 = run(["wiki", "+move", "--target-space-id", SPACE_ID,
                        "--target-parent-token", parent_token, "--obj-type", "docx",
                        "--obj-token", token, "--format", "json"])
        if (d2 or {}).get("ok") is True:
            return True, token
        time.sleep(3 * (attempt + 1))  # 重试间隔更长
    return False, "move:" + raw2[:400]

def find_course_node(title):
    for n in list_nodes(PARENT):
        if n.get("title") == title:
            return n.get("node_token")
    return None

def process_course(course_title, base_path, do=False):
    """处理一门课（增量模式）：找现有课程节点→找/建子目录→跳过已存在文档→导入缺失文档。"""
    log(f"\n>>> {course_title}")
    if not os.path.isdir(base_path):
        log(f"  [SKIP] 本地目录不存在: {base_path}"); return
    subdirs = sorted([d for d in os.listdir(base_path)
                      if os.path.isdir(os.path.join(base_path, d)) and d != "images"])
    log(f"  本地子目录: {subdirs}")

    if not do:
        log("  (探查模式，不执行)"); return

    # 1) 找现有课程节点（不删除）
    c_tok = find_course_node(course_title)
    if not c_tok:
        # 课程节点不存在，建一个
        c_tok = create_node(course_title, PARENT, obj_type="docx")
        if not c_tok:
            log(f"  [FAIL] 建课程节点失败"); return
        log(f"  新建课程节点: {c_tok}")
        time.sleep(1)
    else:
        log(f"  课程节点: {c_tok}")

    total_ok = 0
    total_fail = 0
    total_skip = 0
    for sd in subdirs:
        sd_path = os.path.join(base_path, sd)
        mds = sorted([f for f in os.listdir(sd_path)
                      if f.lower().endswith(".md") and not f.endswith(".__tmp__.md")
                      and ".__embed__" not in f])
        if not mds:
            continue
        # 找/建子目录节点
        sd_tok = None
        for s in list_nodes(c_tok):
            if s.get("title") == sd:
                sd_tok = s.get("node_token"); break
        if not sd_tok:
            sd_tok = create_node(sd, c_tok, obj_type="docx")
            if not sd_tok:
                log(f"  [{sd}] 建子目录节点失败"); continue
            time.sleep(1)
        # 列出现有文档标题（用于跳过）
        existing = {n.get("title") for n in list_nodes(sd_tok)}
        pending = [f for f in mds if os.path.splitext(f)[0] not in existing]
        if not pending:
            log(f"  [{sd}] 全部已存在({len(mds)})，跳过")
            total_skip += len(mds)
            continue
        log(f"  [{sd}] {len(pending)}/{len(mds)} 篇待导入")
        for f in pending:
            stem = os.path.splitext(f)[0]
            fp = os.path.join(sd_path, f)
            try:
                docx = build_docx(fp)
                if not docx:
                    log(f"    [FAIL-build] {f}"); total_fail += 1; continue
                ok, msg = import_move(docx, sd_tok)
                if ok:
                    total_ok += 1
                    log(f"    OK {f}")
                    existing.add(stem)
                else:
                    total_fail += 1
                    log(f"    [FAIL-import] {f} :: {msg[:80]}")
            except Exception as e:
                total_fail += 1
                log(f"    [EXC] {f}: {e}")
            time.sleep(1.5)
    log(f"  课程完成: 成功 {total_ok}, 失败 {total_fail}, 跳过 {total_skip}")

def main():
    open(LOG, "w", encoding="utf-8").close()
    do = "--run" in sys.argv
    log(f"===== {'执行' if do else '探查'}模式 =====")
    total_ok = 0
    total_fail = 0
    for title, path in COURSES:
        process_course(title, path, do=do)
    log(f"\n===== 全部完成 =====")

if __name__ == "__main__":
    main()
