# -*- coding: utf-8 -*-
"""全量结构校验：本地任意深度目录树 vs 飞书节点，双向清点（正向存在 + 反向无多余）。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ev_common import SRC, run, children, load_state, natural_key, make_title, node_key  # noqa: E402


def list_dirs_with_md(root):
    out = []

    def walk(d, rel):
        has_direct = any(f.lower().endswith('.md') for f in os.listdir(d))
        subs = sorted([x for x in os.listdir(d) if os.path.isdir(os.path.join(d, x))],
                      key=natural_key)
        has_deep = has_direct
        for s in subs:
            if walk(os.path.join(d, s), s if not rel else rel + '|' + s):
                has_deep = True
        if has_deep:
            out.append((rel, has_direct))
        return has_deep

    walk(root, '')
    return out


def main():
    state = load_state()
    nodes = state['nodes']
    problems = []

    # ===== 正向：本地目录树的每个节点/文档在飞书存在 =====
    expected_dirs = [rel for rel, _ in list_dirs_with_md(SRC)]
    # 目录层数统计
    depth = max((rel.count('|') + 1 for rel in expected_dirs), default=0)
    print('本地目录(含根): %d 个，最大深度 %d' % (len(expected_dirs), depth))

    # 每个目录递归看子节点标题是否覆盖本地 md 标题
    total_md = 0
    for rel in expected_dirs:
        key = node_key(rel)
        tok = nodes.get(key)
        if not tok:
            problems.append('缺少目录节点: %s' % (rel or '<root>'))
            continue
        kids = children(tok)
        titles = [k['title'] for k in kids]
        # 本地该目录下直接 md 名
        d = os.path.join(SRC, *([x for x in rel.split('|')] if rel else []))
        want = [make_title(f) for f in os.listdir(d) if f.lower().endswith('.md')]
        total_md += len(want)
        for t in want:
            if t not in titles:
                problems.append('缺少文档: %s / %s' % (rel or '<root>', t))
        # 子目录节点存在性（本地子目录是目录节点的）
        subs = [x for x in os.listdir(d)
                if os.path.isdir(os.path.join(d, x))
                and any(f.lower().endswith('.md') for f in _walk_md(os.path.join(d, x)))]
        for s in subs:
            sub_key = node_key((rel + '|' + s) if rel else s)
            if sub_key not in nodes:
                problems.append('缺少子目录节点登记: %s' % (rel + '|' + s))

    # ===== 反向：父节点下无 state 外多余节点 =====
    def walk_reverse(tok, rel):
        kids = children(tok)
        valid_titles = set()
        d = os.path.join(SRC, *([x for x in rel.split('|')] if rel else []))
        if os.path.isdir(d):
            valid_titles |= {make_title(f) for f in os.listdir(d) if f.lower().endswith('.md')}
            for s in os.listdir(d):
                if os.path.isdir(os.path.join(d, s)):
                    valid_titles.add(s)
        for k in kids:
            t = k['title']
            if t not in valid_titles:
                problems.append('多余节点: %s / %s (%s)' % (rel or '<root>', t, k.get('obj_type')))
            if t in valid_titles and os.path.isdir(os.path.join(d, t)):
                walk_reverse(k['node_token'], (rel + '|' + t) if rel else t)

    walk_reverse(nodes.get('root:'), '')

    print('本地 md 总数: %d' % total_md)
    print('state.docs 记录数: %d' % len(state.get('docs', {})))
    if problems:
        print('\n!!! 差异 %d 处:' % len(problems))
        for p in problems[:50]:
            print('  -', p)
        if len(problems) > 50:
            print('  ... 共 %d 处' % len(problems))
    else:
        print('\n✅ 结构完全一致，无缺失 / 无多余 / 无重复')


def _walk_md(d):
    for root, _dirs, files in os.walk(d):
        for f in files:
            if f.lower().endswith('.md'):
                yield os.path.join(root, f)


if __name__ == '__main__':
    main()
