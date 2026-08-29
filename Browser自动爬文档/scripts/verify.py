#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""校验：对比本地 md 与飞书文档，列出缺失。"""
import reimport_all as R
import os, time

OUT = r"D:/Desktop/temp/verify_out.txt"

def w(s):
    with open(OUT, "a", encoding="utf-8") as f:
        f.write(s + "\n")
    print(s, flush=True)

open(OUT, "w", encoding="utf-8").close()
w("=== 校验开始 ===")
grand_missing = []
grand_extra = 0

for course, base in R.COURSES:
    w(f"\n>>> {course}")
    c_tok = R.find_course_node(course)
    if not c_tok:
        w("  [ERR] 课程节点不存在"); continue
    subs = R.list_nodes(c_tok)
    sub_map = {s.get("title"): s.get("node_token") for s in subs}
    local_dirs = sorted([d for d in os.listdir(base)
                         if os.path.isdir(os.path.join(base, d)) and d != "images"])
    for sd in local_dirs:
        sd_path = os.path.join(base, sd)
        mds = sorted([f for f in os.listdir(sd_path)
                      if f.lower().endswith(".md") and not f.endswith(".__tmp__.md")
                      and ".__embed__" not in f])
        if not mds:
            continue
        sd_tok = sub_map.get(sd)
        if not sd_tok:
            w(f"  [{sd}] 子目录节点不存在，缺 {len(mds)} 篇")
            grand_missing += [(course, sd, m) for m in mds]
            continue
        existing = {n.get("title") for n in R.list_nodes(sd_tok)}
        missing = [m for m in mds if os.path.splitext(m)[0] not in existing]
        if missing:
            w(f"  [{sd}] 共{len(mds)}篇，缺{len(missing)}: {missing[:3]}{'...' if len(missing)>3 else ''}")
            grand_missing += [(course, sd, m) for m in missing]
        else:
            w(f"  [{sd}] OK ({len(mds)}篇)")

w(f"\n=== 缺失总数: {len(grand_missing)} ===")
for c, s, m in grand_missing:
    w(f"  {c}/{s}/{m}")
w("=== 校验结束 ===")
