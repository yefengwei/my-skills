# -*- coding: utf-8 -*-
"""阶段一：建目录骨架（任意深度递归）。

- 知识库根下建一级节点 easy-vibe知识库（无 parent）
- 递归：每个含 md（直接或子孙）的目录建一个 docx 节点
- md 文件本身不建节点，由 import_docs 导入到其直接父目录节点下
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ev_common import SRC, ROOT_TITLE, SPACE_ID, run, load_state, save_state, natural_key, node_key  # noqa: E402


def node_create(parent_token, title):
    """建节点。parent_token 为 None 表示知识库根（一级节点）。"""
    args = ['wiki', '+node-create',
            '--title', title, '--as', 'user', '--format', 'json']
    if parent_token:
        args += ['--parent-node-token', parent_token]
    else:
        args += ['--space-id', SPACE_ID]
    last = ''
    for attempt in range(4):
        d = run(args, timeout=120)
        if d and d.get('ok'):
            return d['data']['node_token']
        last = json.dumps(d.get('error', {}), ensure_ascii=False)[:200] if d else 'no-json'
        time.sleep(3 * (attempt + 1))
    raise RuntimeError('node_create 失败 %s: %s' % (title, last))


def list_dirs_with_md(root):
    """递归返回所有需要建节点的目录（含 md 文件或子孙含 md），值为 (abs_path, rel_dir)。

    注意：返回顺序为深度优先【后序】（子目录先于父目录），
    建节点前必须先按深度升序排序，保证父目录先建。
    """
    out = []

    def walk(d, rel):
        # 该目录自身是否有 md？或递归子目录中是否有 md？
        has_md_direct = any(f.lower().endswith('.md') for f in os.listdir(d))
        subs = sorted([x for x in os.listdir(d) if os.path.isdir(os.path.join(d, x))],
                      key=natural_key)
        has_md_deep = has_md_direct
        for s in subs:
            if walk(os.path.join(d, s), s if not rel else rel + '|' + s):
                has_md_deep = True
        if has_md_deep:
            out.append((d, rel))
            return True
        return False

    walk(root, '')
    return out


def depth_of(rel):
    return 0 if not rel else rel.count('|') + 1


def main():
    state = load_state()
    nodes = state['nodes']
    root_key = 'root:'
    if root_key not in nodes:
        tok = node_create(None, ROOT_TITLE)
        nodes[root_key] = tok
        print('+ 一级节点 %s %s' % (ROOT_TITLE, tok))
        save_state(state)
    else:
        print('= 一级节点已存在 %s' % nodes[root_key])

    dirs = list_dirs_with_md(SRC)
    # 稳定排序：仅按深度升序（父先子后），同深度保持原自然顺序
    dirs.sort(key=lambda x: depth_of(x[1]))
    for abs_d, rel in dirs:
        if not rel:
            continue  # 根已建
        key = node_key(rel)
        if key in nodes:
            print('= 目录已存在 %s' % rel)
            continue
        parent_rel = rel.rsplit('|', 1)[0] if '|' in rel else ''
        parent_key = node_key(parent_rel)
        parent_tok = nodes[parent_key]
        title = rel.split('|')[-1]
        tok = node_create(parent_tok, title)
        nodes[key] = tok
        print('+ 目录 %s -> %s' % (rel, tok))
        save_state(state)
        time.sleep(0.3)

    print('\n节点总数: %d' % len(nodes))


if __name__ == '__main__':
    main()
