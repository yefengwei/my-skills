# -*- coding: utf-8 -*-
"""全量校验：对比本地目录结构与飞书知识库实际节点，输出差异报告。"""
import json
import os
import re
import subprocess

from lark_env import BASE, LARK_ENTRY, NODE_BIN, SPACE, clean_env


def run(args, timeout=120):
    p = subprocess.run([NODE_BIN, LARK_ENTRY] + args, capture_output=True,
                       text=True, encoding='utf-8', errors='replace',
                       env=clean_env(), timeout=timeout)
    blob = (p.stdout or '') + (p.stderr or '')
    pos = blob.find('{')
    if pos < 0:
        return None
    try:
        value, _ = json.JSONDecoder().raw_decode(blob[pos:])
        return value
    except json.JSONDecodeError:
        return None


def children(parent):
    d = run(['wiki', '+node-list', '--space-id', SPACE,
             '--parent-node-token', parent, '--as', 'user', '--format', 'json'])
    return d['data']['nodes'] if d and d.get('ok') else []


def title_of(fn):
    t = fn[:-3] if fn.lower().endswith('.md') else fn
    return re.sub(r'[（(]\s*程序员鱼皮\s*[)）]\s*$', '', t).strip()


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    state = json.load(open(os.path.join(here, 'state.json'), encoding='utf-8'))
    nodes = state['nodes']

    # 本地期望结构
    expected = {}
    for proj in sorted(os.listdir(BASE)):
        pdir = os.path.join(BASE, proj)
        if not os.path.isdir(pdir):
            continue
        for sub in sorted(os.listdir(pdir)):
            sdir = os.path.join(pdir, sub)
            if not os.path.isdir(sdir):
                continue
            mds = sorted(f for f in os.listdir(sdir) if f.lower().endswith('.md'))
            if mds:
                expected[(proj, sub)] = mds

    local_total = sum(len(v) for v in expected.values())
    print('本地 md 总数: %d，分布在 %d 个子目录' % (local_total, len(expected)))

    problems = []
    total_remote = 0
    for (proj, sub), mds in expected.items():
        key = 'dir:%s|%s' % (proj, sub)
        token = nodes.get(key)
        if not token:
            problems.append('缺少目录节点: %s' % key)
            continue
        kids = children(token)
        titles = [k['title'] for k in kids]
        total_remote += len(kids)
        want = [title_of(m) for m in mds]
        missing = [t for t in want if t not in titles]
        extra = [t for t in titles if t not in want]
        dup = len(titles) - len(set(titles))
        if missing or extra or dup:
            problems.append('%s/%s: 缺失=%s 多余=%s 重复=%d (实际%d/期望%d)'
                            % (proj, sub, missing, extra, dup, len(titles), len(want)))
    print('飞书实际文档节点总数: %d' % total_remote)
    print('state.docs 记录数: %d' % len(state.get('docs', {})))
    if problems:
        print('\n!!! 差异 %d 处:' % len(problems))
        for p in problems:
            print('  -', p)
    else:
        print('\n✅ 结构完全一致，无缺失 / 无多余 / 无重复')


if __name__ == '__main__':
    main()
