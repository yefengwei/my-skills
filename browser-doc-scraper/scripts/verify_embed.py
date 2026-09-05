#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""校验 5 门课程正式 md：本地图片引用全部存在、无残留远程图片引用（fence 外）。"""
import os, re

COURSES = [
    'Next.js + Elasticsearch 智能面试刷题平台',
    'Vue3 + SpringBoot + AI + DDD 企业级智能协同云图库项目',
    'SpringAI + RAG + MCP 全栈 ｜ AI 超级智能体企业级实战',
    'Python 全栈 ｜ AI 闯关学习小程序项目教程',
    'LangChain4j + 工作流 + 微服务 AI 零代码应用生成平台',
]
IMG_RE = re.compile(r'!\[([^\]]*)\]\(([^)\s]+)\)', re.I)
HTML_IMG_RE = re.compile(r'<img[^>]+?src=["\']([^"\'> ]+)["\']', re.I)

def fence_flags(lines):
    flags, f = [], False
    for l in lines:
        if re.match(r'^\s*(```|~~~)', l):
            flags.append(True); f = not f; continue
        flags.append(f)
    return flags

tot = {'loc': 0, 'miss': 0, 'http': 0}
miss_sample, http_sample = [], []
for c in COURSES:
    c_loc = c_miss = c_http = 0
    for dp, dn, fn in os.walk(c):
        for f in fn:
            if not f.lower().endswith('.md') or f.endswith('.__tmp__.md') or '.__embed__' in f:
                continue
            p = os.path.join(dp, f)
            lines = open(p, encoding='utf-8', errors='ignore').read().split('\n')
            fl = fence_flags(lines)
            for l, inf in zip(lines, fl):
                if inf:
                    continue
                urls = [m.group(2) for m in IMG_RE.finditer(l)] + \
                       [m.group(1) for m in HTML_IMG_RE.finditer(l)]
                for u in urls:
                    if u.startswith(('http://', 'https://')):
                        c_http += 1
                        if len(http_sample) < 5:
                            http_sample.append((p, u[:90]))
                    else:
                        c_loc += 1
                        fp = os.path.join(dp, u.split('#')[0].split('?')[0])
                        if not os.path.exists(fp):
                            c_miss += 1
                            if len(miss_sample) < 5:
                                miss_sample.append((p, u))
    print(f'{c[:24]}: 本地引用 {c_loc}, 文件缺失 {c_miss}, 残留远程 {c_http}')
    tot['loc'] += c_loc; tot['miss'] += c_miss; tot['http'] += c_http
print(f"== 合计: 本地引用 {tot['loc']}, 缺失 {tot['miss']}, 残留远程 {tot['http']} ==")
for s in miss_sample: print('缺失:', s)
for s in http_sample: print('远程:', s)
