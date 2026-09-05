#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 5 门课程（md 图片已本地化）生成内嵌 docx 并导入飞书「编程导航」。

与 reimport_all.py 的区别：
  - 不再走 embed_images.py（下载远程图），md 已引用本地 images/，pandoc 直接内嵌；
  - docx 输出到 .workbuddy/docx_out（不污染课程目录）；
  - docx 按 md 时间戳缓存复用。
"""
import os
import sys
import time
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reimport_all as R

BASE = "D:/Desktop/temp"
TMP = os.path.join(BASE, ".workbuddy", "docx_out")
LOG = os.path.join(BASE, "ri5_progress.log")

COURSES = [
    "Next.js + Elasticsearch 智能面试刷题平台",
    "Vue3 + SpringBoot + AI + DDD 企业级智能协同云图库项目",
    "SpringAI + RAG + MCP 全栈 ｜ AI 超级智能体企业级实战",
    "Python 全栈 ｜ AI 闯关学习小程序项目教程",
    "LangChain4j + 工作流 + 微服务 AI 零代码应用生成平台",
]

os.makedirs(TMP, exist_ok=True)
R.LOG = LOG
log = R.log


def build_docx(md_path, out_dir):
    """用 pandoc 把本地化 md 转成内嵌图片的 docx。

    关键点：md 中大量图片是 HTML <img src="images/xxx.png"> 形式，pandoc 会把它当
    raw HTML 丢弃（docx 里 0 张图）。必须先转成行内式 ![](images/xxx.png)。
    临时 md 与原 md 同目录（images/ 相对路径才解析得到），转换后删除。
    """
    import embed_images as E
    stem = os.path.splitext(os.path.basename(md_path))[0]
    md_dir = os.path.dirname(md_path)
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, stem + ".docx")
    if (os.path.exists(out) and os.path.getsize(out) > 0
            and os.path.getmtime(out) >= os.path.getmtime(md_path)):
        return out
    text = open(md_path, encoding="utf-8", errors="ignore").read()
    text, n_html = E.html_img_to_md(text)
    # 走 stdin，不落地临时 md（避免在课程目录里产生垃圾文件）。
    # 相对图片路径以 cwd（= md 所在目录）+ --resource-path 解析。
    p = subprocess.run(
        ["pandoc", "-f", "markdown", "-t", "docx",
         "--resource-path=.", "-o", out],
        input=text, cwd=md_dir, capture_output=True, text=True,
        encoding="utf-8", errors="ignore")
    if not (os.path.exists(out) and os.path.getsize(out) > 0):
        log(f"    [pandoc-err] {stem}: {(p.stderr or '')[:200]}")
        return None
    return out


def count_media(docx):
    import zipfile
    try:
        with zipfile.ZipFile(docx) as z:
            return len([n for n in z.namelist() if n.startswith("word/media/")])
    except Exception:
        return -1


def process(course, base_path):
    log(f"\n>>> {course}")
    subdirs = sorted([d for d in os.listdir(base_path)
                      if os.path.isdir(os.path.join(base_path, d)) and d != "images"])
    c_tok = R.find_course_node(course)
    if not c_tok:
        c_tok = R.create_node(course, R.PARENT, obj_type="docx")
        if not c_tok:
            log("  [FAIL] 建课程节点失败")
            return 0, 0, 0
        log(f"  新建课程节点: {c_tok}")
        time.sleep(1)
    else:
        log(f"  课程节点已存在: {c_tok}")

    ok_n = fail_n = skip_n = 0
    for sd in subdirs:
        sd_path = os.path.join(base_path, sd)
        mds = sorted([f for f in os.listdir(sd_path)
                      if f.lower().endswith(".md") and not f.endswith(".__tmp__.md")
                      and ".__embed__" not in f])
        if not mds:
            continue
        sd_tok = None
        for s in R.list_nodes(c_tok):
            if s.get("title") == sd:
                sd_tok = s.get("node_token")
                break
        if not sd_tok:
            sd_tok = R.create_node(sd, c_tok, obj_type="docx")
            if not sd_tok:
                log(f"  [{sd}] 建子目录节点失败")
                continue
            time.sleep(1)
        existing = {n.get("title") for n in R.list_nodes(sd_tok)}
        pending = [f for f in mds if os.path.splitext(f)[0] not in existing]
        if not pending:
            log(f"  [{sd}] 全部已存在({len(mds)})，跳过")
            skip_n += len(mds)
            continue
        log(f"  [{sd}] {len(pending)}/{len(mds)} 篇待导入")
        out_dir = os.path.join(TMP, course, sd)
        for f in pending:
            stem = os.path.splitext(f)[0]
            fp = os.path.join(sd_path, f)
            try:
                docx = build_docx(fp, out_dir)
                if not docx:
                    log(f"    [FAIL-build] {f}")
                    fail_n += 1
                    continue
                good, msg = R.import_move(docx, sd_tok)
                if good:
                    ok_n += 1
                    log(f"    OK {f} (图 {count_media(docx)})")
                    existing.add(stem)
                else:
                    fail_n += 1
                    log(f"    [FAIL-import] {f} :: {msg[:100]}")
            except Exception as e:
                fail_n += 1
                log(f"    [EXC] {f}: {e}")
            time.sleep(1.5)
    log(f"  课程完成: 成功 {ok_n}, 失败 {fail_n}, 跳过 {skip_n}")
    return ok_n, fail_n, skip_n


def main():
    open(LOG, "w", encoding="utf-8").close()
    log("===== 5 门课程全量导入（本地图直接内嵌）=====")
    tot = [0, 0, 0]
    for c in COURSES:
        p = os.path.join(BASE, c)
        if not os.path.isdir(p):
            log(f"[SKIP] 目录不存在: {p}")
            continue
        a, b, d = process(c, p)
        tot[0] += a
        tot[1] += b
        tot[2] += d
        log(f"--- 累计: 成功 {tot[0]}, 失败 {tot[1]}, 跳过 {tot[2]}")
    log("===== 全部完成 =====")


if __name__ == "__main__":
    main()
