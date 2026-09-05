# -*- coding: utf-8 -*-
"""全量 120 篇 difflib 逐段文字审计：找出真实的正文丢失段落。

归一化策略：
- 去图片标签（本地 @./ 短链 / 飞书 authcode 长链）
- 去转义反斜杠（预处理转义的 \\< 在飞书回读为字面 <）
- 去全部空白（飞书渲染会把多行压一行）
判定：delete 段（本地有、飞书无）累计超过 GAP_CHARS 视为疑似丢失。
"""
import difflib
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from lark_env import BASE
from verify import run
import lark_md_prep  # noqa: E402

STATE = os.path.join(HERE, 'state.json')
GAP_CHARS = 60          # 单篇疑似丢失字符阈值
MIN_SEG = 40            # 单个 delete 段最小长度（忽略渲染微差）

LOCAL_IMG = re.compile(r'!\[[^\]]*\]\(@\./[^)]+\)')
REMOTE_IMG = re.compile(r'!\[[^\]]*\]\(https?://[^)]+\)')


def normalize(t):
    t = LOCAL_IMG.sub('', t)
    t = REMOTE_IMG.sub('', t)
    t = t.replace('\\', '')          # 去转义反斜杠伪差
    t = re.sub(r'\s+', '', t)
    return t


def audit_one(rel):
    did = docs[rel]
    local = lark_md_prep.transform_file(os.path.join(BASE, rel))
    d = run(['docs', '+fetch', '--doc', did, '--doc-format', 'markdown',
             '--as', 'user', '--format', 'json'], timeout=300)
    remote = d['data']['document']['content'] if d and d.get('ok') else ''
    rl = remote.split('\n')
    if rl and rl[0].startswith('# '):
        remote = '\n'.join(rl[1:])
    L, R = normalize(local), normalize(remote)
    if len(R) >= len(L):             # 只可能膨胀（伪影），无丢失
        return (rel, 0, [])
    sm = difflib.SequenceMatcher(None, L, R, autojunk=False)
    lost_segs = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'delete' and (i2 - i1) >= MIN_SEG:
            lost_segs.append(L[i1:i1 + 80])
        elif tag == 'replace' and (i2 - i1) - (j2 - j1) >= MIN_SEG:
            lost_segs.append(L[i1:i1 + 80])
    total = sum(1 for _ in lost_segs)
    return (rel, len(lost_segs), lost_segs[:3])


state = json.load(open(STATE, encoding='utf-8'))
docs = state['docs']
rels = sorted(docs.keys())
print('待审计:', len(rels), '篇', flush=True)

results = []
with ThreadPoolExecutor(max_workers=4) as pool:
    futs = {pool.submit(audit_one, r): r for r in rels}
    done_n = 0
    for f in as_completed(futs):
        try:
            results.append(f.result())
        except Exception as e:  # noqa: BLE001
            results.append((futs[f], -1, [str(e)[:100]]))
        done_n += 1
        if done_n % 20 == 0:
            print(f'  进度 {done_n}/{len(rels)}', flush=True)

bad = [(r, n, segs) for r, n, segs in results if n != 0]
bad.sort(key=lambda x: -x[1])
print()
print('===== 汇总 =====')
print('审计总数:', len(results))
print('疑似丢失文档数:', len(bad))
for r, n, segs in bad:
    print(f'\n--- {r}  丢失段数 {n}')
    for s in segs:
        print('    片段:', s[:70])

print('\n===== 结束 =====')
