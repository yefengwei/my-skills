# -*- coding: utf-8 -*-
"""清点并清理编程导航下的重复旧树与测试文档。

⚠️ 注意：本脚本会递归删除节点，务必先跑只读的清点段确认无误，再放开删除段。
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lark_env import SPACE, WIKI_PARENT
from verify import run, children

# state.json 里的好树
state = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'state.json'), encoding='utf-8'))
good = {v for k, v in state['nodes'].items() if k.startswith('proj:')}
good_docs = set(state['docs'].values())

# 旧树（更早会话导入尝试的残留）——新项目按实际残留修改
STALE_PROJECTS = [
    ('LangChain4j 旧树', 'Kt0Qw1OIYiJ1r5kUmWdcXUS4nIe'),
    ('Next.js 旧树', 'ACW2wkiU3iDkxhk2Odecmia7nUd'),
    ('Python 旧树', 'E2QEwVBZbiA6eTkiBY9cVxMEnhc'),
]
STALE_TEST_DOCS = ['深度测试-17KB']

# 只读清点开关：True 只打印不动手，False 执行删除
DRY_RUN = True


def delete_node(token):
    d = run(['wiki', '+node-delete', '--node-token', token, '--obj-type', 'wiki',
             '--yes', '--as', 'user', '--format', 'json'], timeout=120)
    return bool(d and d.get('ok'))


def count_tree(token, depth=0):
    """递归统计子树节点数，并收集 obj_token。"""
    total, objs = 0, []
    for n in children(token):
        total += 1
        objs.append((n.get('title'), n.get('obj_token')))
        t2, o2 = count_tree(n['node_token'], depth + 1)
        total += t2
        objs.extend(o2)
    return total, objs


print('===== 1. 清点旧树 =====')
for name, tok in STALE_PROJECTS:
    total, objs = count_tree(tok)
    overlap = sum(1 for _, o in objs if o in good_docs)
    print(f'{name} {tok}: 节点 {total} 个，其中文档 obj_token 与好树重合 {overlap} 个')
    for n in children(tok)[:12]:
        print('   ', n['title'], n['obj_type'])

print()
print('===== 2. 删除旧树与测试文档 =====')
victims = [(n, t) for n, t in STALE_PROJECTS]
for n in children(WIKI_PARENT):
    if n['title'] in STALE_TEST_DOCS:
        victims.append(('测试文档 ' + n['title'], n['node_token']))

for name, tok in victims:
    if DRY_RUN:
        print(f'  [DRY] 待删 {name} {tok}')
        continue
    ok = delete_node(tok)
    print(f'  删 {name} {tok}: {"OK" if ok else "FAIL"}')
    time.sleep(0.5)

print()
print('===== 3. 复查编程导航一级节点 =====')
rest = children(WIKI_PARENT)
print('剩余节点数:', len(rest))
for n in rest:
    print('  ', n['title'][:50], n['node_token'])
if DRY_RUN:
    print('\n(DRY_RUN=True 未执行删除；确认无误后改为 False 再跑)')
