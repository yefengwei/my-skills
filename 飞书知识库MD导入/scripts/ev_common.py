# -*- coding: utf-8 -*-
"""任意深度目录树导入的公共工具：lark 调用 / state 读写 / 标题与排序。

供 build_tree_rec.py / import_docs_rec.py / verify_rec.py / fix_indent_drop.py 使用。
机器/项目相关常量走环境变量覆盖（见 lark_env.py 同款约定）：
    LARK_MD_SRC       待导入 md 项目根目录
    LARK_SPACE_ID     目标知识库空间 ID
    LARK_ROOT_TITLE   在知识库根下新建的一级节点标题
"""
import json
import os
import re
import subprocess

from lark_env import LARK_ENTRY, NODE_BIN, SPACE, clean_env

HERE = os.path.dirname(os.path.abspath(__file__))
STATE_PATH = os.path.join(HERE, 'state.json')

# 项目根 / 目标空间 / 一级节点标题（默认 easy-vibe 实战值，可用环境变量覆盖）
SRC = os.environ.get('LARK_MD_SRC') or r'D:\yefengwei\private\ai_play\知识库\my_ai_notion\easy-vibe知识库'
SPACE_ID = os.environ.get('LARK_SPACE_ID') or SPACE
ROOT_TITLE = os.environ.get('LARK_ROOT_TITLE') or 'easy-vibe知识库'


def run(args, timeout=300):
    """调用 lark-cli 返回首个 JSON 对象；失败返回 None。"""
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


def children(parent_token):
    d = run(['wiki', '+node-list', '--space-id', SPACE_ID,
             '--parent-node-token', parent_token, '--as', 'user', '--format', 'json'])
    return d['data']['nodes'] if d and d.get('ok') else []


def load_state():
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH, encoding='utf-8') as f:
            return json.load(f)
    return {'nodes': {}, 'docs': {}, 'failed': []}


def save_state(state):
    with open(STATE_PATH, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def natural_key(s):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r'(\d+)', s)]


def make_title(filename):
    """文件名 -> 飞书标题：去 .md 后缀。easy-vibe 无 (程序员鱼皮) 后缀。"""
    t = filename[:-3] if filename.lower().endswith('.md') else filename
    return t.strip() or filename


def node_key(rel_dir):
    """相对目录路径 -> state key。根目录用 root:，其余用 dir:<以|分隔的层级>。"""
    if not rel_dir:
        return 'root:'
    return 'dir:' + rel_dir.replace('/', '|').replace('\\', '|')
