# -*- coding: utf-8 -*-
"""
把「编程导航项目md」下的 5 个项目按原目录结构导入飞书知识库
「计算机科学与技术 / 编程导航」节点下。

阶段一（本脚本）：创建 5 个项目节点 + 各子目录节点，结果写入 state.json
阶段二（import_docs.py）：并发导入 120 篇 Markdown（含原图上传）

换项目时：优先用环境变量覆盖（见 lark_env.py），或直接改下方 SEED/注释。
"""
import json
import os
import re
import subprocess
import time

from lark_env import BASE, LARK_ENTRY, NODE_BIN, WIKI_PARENT, clean_env

STATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'state.json')

# 已手工试点创建的内容（本项目专用；重跑新项目时置空 {}）
SEED = {
    'proj:SpringAI + RAG + MCP 全栈 ｜ AI 超级智能体企业级实战': 'FXfnwytTAi5GjWkvYtrcuc4wnag',
    'dir:SpringAI + RAG + MCP 全栈 ｜ AI 超级智能体企业级实战|文字教程': 'S67PwZUO5iG71Mk0UuIc0Yptngc',
}


def run_lark(args, retries=4):
    """调用 lark-cli（通过 node 直接执行入口脚本），返回解析后的 JSON；失败重试。"""
    last = ''
    for attempt in range(retries):
        try:
            p = subprocess.run(
                [NODE_BIN, LARK_ENTRY] + args,
                capture_output=True, text=True, encoding='utf-8',
                errors='replace', env=clean_env(), timeout=300,
            )
        except subprocess.TimeoutExpired:
            last = 'timeout'
            time.sleep(5 * (attempt + 1))
            continue
        out = p.stdout or ''
        # lark-cli 会先打印进度行，截取第一个 { 开始的 JSON
        i = out.find('{')
        if i >= 0:
            try:
                data = json.loads(out[i:])
                if data.get('ok'):
                    return data
                last = json.dumps(data.get('error', {}), ensure_ascii=False)[:300]
            except json.JSONDecodeError:
                last = out[:200]
        else:
            last = (out + p.stderr)[:200]
        time.sleep(3 * (attempt + 1))
    raise RuntimeError('lark-cli 调用失败: %s | args=%s' % (last, args[:4]))


def node_create(parent_token, title):
    d = run_lark([
        'wiki', '+node-create',
        '--parent-node-token', parent_token,
        '--title', title,
        '--as', 'user', '--format', 'json',
    ])
    return d['data']['node_token']


def natural_key(s):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r'(\d+)', s)]


def main():
    state = {'nodes': dict(SEED), 'docs': {}, 'failed': []}
    if os.path.exists(STATE):
        with open(STATE, encoding='utf-8') as f:
            state = json.load(f)
    nodes = state['nodes']

    projects = sorted(
        [d for d in os.listdir(BASE) if os.path.isdir(os.path.join(BASE, d))],
        key=natural_key,
    )
    print('项目: %d 个' % len(projects))

    for proj in projects:
        pkey = 'proj:' + proj
        if pkey not in nodes:
            nodes[pkey] = node_create(WIKI_PARENT, proj)
            print('  + 项目节点 %-50s %s' % (proj[:50], nodes[pkey]))
        else:
            print('  = 项目节点已存在 %s' % proj)

        proj_dir = os.path.join(BASE, proj)
        subdirs = sorted(
            [d for d in os.listdir(proj_dir)
             if os.path.isdir(os.path.join(proj_dir, d))
             and any(f.endswith('.md') for f in os.listdir(os.path.join(proj_dir, d)))],
            key=natural_key,
        )
        for sub in subdirs:
            dkey = 'dir:%s|%s' % (proj, sub)
            if dkey not in nodes:
                nodes[dkey] = node_create(nodes[pkey], sub)
                print('      + 目录节点 %-30s %s' % (sub, nodes[dkey]))
            else:
                print('      = 目录节点已存在 %s' % sub)

    with open(STATE, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    print('\n骨架完成，共 %d 个节点，已写入 %s' % (len(nodes), STATE))


if __name__ == '__main__':
    main()
