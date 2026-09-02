# -*- coding: utf-8 -*-
"""
清理阶段：
- 对 4 个因某张图 correlation_failed 而整体 ok=false 的文档，
  实际已在飞书创建（且被重试产生重复副本），现在去重并标记完成
- 每个父节点下，标题相同的多个 node 保留第一个，其余删除
"""
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lark_env import LARK_ENTRY, NODE_BIN, SPACE, clean_env

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, 'state.json')
LOG = os.path.join(HERE, 'cleanup.log')

# (相对 BASE 路径, 父目录 node_token, 去重标题)；新项目按需修改
CASES = [
    (r'Next.js + Elasticsearch 智能面试刷题平台\项目面试题\面试刷题平台面试题文档(程序员鱼皮).md',
     'QpYQwGYnsiEQDbk3F9scnDVCnxc', '面试刷题平台面试题文档'),
    (r'Python 全栈 ｜ AI 闯关学习小程序项目教程\项目教程\7. 用户系统开发(程序员鱼皮).md',
     'DklmwWYtwiUbPUkVMBDcDqLZnGW', '7. 用户系统开发'),
    (r'Python 全栈 ｜ AI 闯关学习小程序项目教程\项目教程\9. AI 生成题目优化（联网搜索）(程序员鱼皮).md',
     'DklmwWYtwiUbPUkVMBDcDqLZnGW', '9. AI 生成题目优化（联网搜索）'),
    (r'Vue3 + SpringBoot + AI + DDD 企业级智能协同云图库项目\文字教程\2 - 项目初始化(程序员鱼皮).md',
     'HQ1xwjSINiTWqIkMnRdcgGFAnd4', '2 - 项目初始化'),
]


def run(args, timeout=120):
    p = subprocess.run(
        [NODE_BIN, LARK_ENTRY] + args,
        capture_output=True, text=True, encoding='utf-8', errors='replace',
        env=clean_env(), timeout=timeout,
    )
    blob = (p.stdout or '') + (p.stderr or '')
    decoder = json.JSONDecoder()
    pos = blob.find('{')
    if pos < 0:
        return None, blob[:200]
    try:
        value, _ = decoder.raw_decode(blob[pos:])
        return value, ''
    except json.JSONDecodeError as e:
        return None, blob[:300]


def list_children(space_id, parent_token):
    d, _ = run([
        'wiki', '+node-list',
        '--space-id', space_id, '--parent-node-token', parent_token,
        '--as', 'user', '--format', 'json',
    ])
    nodes = d['data']['nodes'] if d and d.get('ok') else []
    return nodes


def delete_node(token):
    d, err = run([
        'wiki', '+node-delete',
        '--node-token', token, '--obj-type', 'wiki', '--yes',
        '--as', 'user', '--format', 'json',
    ])
    return bool(d and d.get('ok')), err


def main():
    with open(STATE, encoding='utf-8') as f:
        state = json.load(f)
    nodes = state['nodes']
    docs = state.setdefault('docs', {})

    total_del = 0
    for rel, parent, title in CASES:
        kids = list_children(SPACE, parent)
        matches = [n for n in kids if n.get('title') == title]
        if not matches:
            print(f'!! 未找到: {title} in {parent}')
            continue
        if len(matches) == 1:
            docs[rel] = matches[0]['obj_token']
            print(f'= {title}: 唯一，采纳 {matches[0]["node_token"]}')
            continue
        keep = matches[0]
        rest = matches[1:]
        print(f'+ {title}: 保留 {keep["node_token"]}, 删除 {len(rest)} 个副本')
        for n in rest:
            ok, err = delete_node(n['node_token'])
            print(f'  - {"OK" if ok else "FAIL"} {n["node_token"]} {("" if ok else err[:120])}')
            if ok:
                total_del += 1
            time.sleep(0.4)
        docs[rel] = keep['obj_token']

    # 清掉 state.failed 中指向这 4 个路径的记录
    keep_failed = [f for f in state.get('failed', []) if f.get('path') not in {c[0] for c in CASES}]
    state['failed'] = keep_failed

    with open(STATE, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    print(f'\n清理完成，共删除 {total_del} 个重复节点；state.docs={len(docs)}')


if __name__ == '__main__':
    main()
