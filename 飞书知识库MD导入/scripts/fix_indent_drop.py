# -*- coding: utf-8 -*-
"""修复 2 篇因「列表内嵌表格/代码块后缩进续文被飞书丢弃」的文档。

修复策略（实验验证）：
- 在 lark_md_prep 预处理结果基础上，识别「有序/无序列表项内嵌表格或代码块
  之后、同缩进续接的正文行」，把这类行去缩进抬为独立段落，
  避免飞书把缩进块里的普通段落静默丢弃。

流程：删旧节点 → create 空文档 → append 分片（复用 rebuild_safe 方式）。
"""
import json
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ev_common import SRC, children, load_state, save_state, make_title, node_key  # noqa: E402
from lark_env import LARK_ENTRY, NODE_BIN, clean_env  # noqa: E402
import lark_md_prep  # noqa: E402

CHUNK_CHARS = 1800

# 待修复文档（相对 easy-vibe 根的路径）
TARGETS = [
    r'第二阶段-进阶篇\03-AI能力附录\01-Dify入门与知识库集成.md',
    r'第二阶段-进阶篇\04-综合项目\03-在线考试与管理系统-项目指南.md',
]

# 已知触发丢字的具体句子（校验修复后必须存在）
MUST_KEEP = {
    '01-Dify入门与知识库集成': '启用 USER 提示词参数',
    '03-在线考试与管理系统-项目指南': '要求接口命名清晰',
}


def run_lark(args, cwd=None, stdin_data=None, timeout=600):
    p = subprocess.run([NODE_BIN, LARK_ENTRY] + args,
                       input=stdin_data, capture_output=True, text=True,
                       encoding='utf-8', errors='replace', env=clean_env(), cwd=cwd, timeout=timeout)
    blob = (p.stdout or '') + (p.stderr or '')
    pos = blob.find('{')
    if pos < 0:
        raise RuntimeError('无 JSON: %s' % blob[:200])
    value, _ = json.JSONDecoder().raw_decode(blob[pos:])
    if not value.get('ok'):
        raise RuntimeError(json.dumps(value.get('error', {}), ensure_ascii=False)[:300])
    return value


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


def delete_node(token):
    d = run(['wiki', '+node-delete', '--node-token', token, '--obj-type', 'wiki', '--yes',
             '--as', 'user', '--format', 'json'], timeout=120)
    return bool(d and d.get('ok'))


# ---- 缩进续文抬级修复 ----
BLOCK_END_RE = re.compile(r'^\s*(```|~~~|\||[-+*] )')   # 代码块围栏/表格行/列表项行
# 列表项开始的判定（数字. 或 - / + / *）
LIST_ITEM_RE = re.compile(r'^\s*(?:[-+*]|\d+[.)])\s+\S')
# 代码块围栏（允许任意前导缩进——列表内嵌代码块常见 3~5 空格缩进）
FENCE_ANY_RE = re.compile(r'^\s*(`{3,}|~{3,})')


def fix_indent_continuation(text: str) -> str:
    """把「列表项内嵌表格/代码块后、同缩进续接的正文行」抬为独立段落。

    判定逻辑：某行以 2+ 空格缩进开头，且不是表格行/代码块/列表项本身，
    同时它前面的非空行是代码块围栏或表格行（说明它处于"块结束后的续文"位置）
    → 去掉缩进输出，避免被飞书当作列表缩进子内容而丢弃。
    """
    lines = text.split('\n')
    out = []
    in_fence = False
    fence_marker = ''
    prev_was_block_end = False   # 上一非空行是否表格行或代码块围栏

    for i, line in enumerate(lines):
        m = FENCE_ANY_RE.match(line)
        if m:
            marker = m.group(1)[0]
            if not in_fence:
                in_fence = True
                fence_marker = marker
                prev_was_block_end = False
            elif marker == fence_marker:
                in_fence = False
                fence_marker = ''
                prev_was_block_end = True
            out.append(line)
            continue

        stripped = line.strip()
        if not stripped:
            out.append(line)
            continue

        if in_fence:
            out.append(line)
            continue

        indent = len(line) - len(line.lstrip(' '))
        is_table = stripped.startswith('|')
        is_list_item = bool(LIST_ITEM_RE.match(line))
        is_heading = stripped.startswith('#')
        is_blockquote = stripped.startswith('>')

        if is_table:
            prev_was_block_end = True
            out.append(line)
            continue

        # 关键规则：缩进 >=2 的普通正文行，且前一非空行为表格行/代码块围栏 → 抬级
        if indent >= 2 and not is_list_item and not is_heading and not is_blockquote \
                and not stripped.startswith('```') and prev_was_block_end:
            out.append(line[indent:])     # 去缩进
            prev_was_block_end = False
            continue

        prev_was_block_end = False
        out.append(line)

    return '\n'.join(out)


def split_text_by_paragraph(text, max_chars):
    chunks, buf = [], ''
    for para in re.split(r'\n\s*\n', text):
        piece = (buf + '\n\n' + para) if buf else para
        if len(piece) > max_chars and buf:
            chunks.append(buf)
            buf = para
        else:
            buf = piece
    if buf:
        chunks.append(buf)
    return chunks


def main():
    only = os.environ.get('ONLY', '').strip()
    state = load_state()
    nodes, docs = state['nodes'], state.setdefault('docs', {})

    targets = [t for t in TARGETS if (not only or only in t)]
    for rel in targets:
        title = make_title(os.path.basename(rel))
        parts = rel.split('\\')
        rel_dir = '|'.join(parts[:-1])
        parent = nodes.get(node_key(rel_dir))
        if not parent:
            print('!! 无父节点', rel_dir); continue
        print(f'\n========== {title} ==========')

        # 1. 删旧
        for k in children(parent):
            if k.get('title') == title:
                print('  删', 'OK' if delete_node(k['node_token']) else 'FAIL', k['node_token'])
                time.sleep(0.4)
        key = 'doc:' + rel.replace('\\', '/')
        docs.pop(key, None)

        # 2. 预处理 + 抬级修复
        abs_md = os.path.join(SRC, rel)
        cwd = os.path.dirname(abs_md)
        full = lark_md_prep.transform_file(abs_md)
        full = fix_indent_continuation(full)
        parts2 = re.split(r'(!\[[^\]]*\]\(@\./[^)]+\))', full)
        n_imgs = (len(parts2) - 1) // 2

        # 3. 建空文档
        data = run_lark(['docs', '+create', '--doc-format', 'markdown', '--content', '-',
                         '--title', title, '--parent-token', parent,
                         '--as', 'user', '--format', 'json'],
                        cwd=cwd, stdin_data=' ', timeout=300)
        doc_id = data['data']['document']['document_id']
        print(f'  ✓ 创建 {doc_id}')

        # 4. 分片 append（图片与正文交错）
        n_text = n_img = 0
        for chunk in split_text_by_paragraph(parts2[0], CHUNK_CHARS):
            try:
                run_lark(['docs', '+update', '--doc', doc_id, '--command', 'append',
                          '--doc-format', 'markdown', '--content', '-',
                          '--as', 'user', '--format', 'json'],
                         cwd=cwd, stdin_data=chunk, timeout=180)
                n_text += 1
            except Exception as e:  # noqa: BLE001
                print('  ! chunk FAIL:', str(e)[:120])
            time.sleep(0.2)
        for k in range(1, len(parts2), 2):
            m = re.match(r'!\[[^\]]*\]\(@\./([^)]+)\)', parts2[k])
            img_rel = m.group(1) if m else None
            if img_rel and os.path.exists(os.path.join(cwd, img_rel)):
                try:
                    run_lark(['docs', '+media-insert', '--doc', doc_id,
                              '--file', img_rel, '--as', 'user', '--format', 'json'],
                             cwd=cwd, timeout=180)
                    n_img += 1
                except Exception as e:  # noqa: BLE001
                    print('  ! img FAIL:', str(e)[:120])
            time.sleep(0.2)
            text_after = parts2[k + 1] if k + 1 < len(parts2) else ''
            for chunk in split_text_by_paragraph(text_after, CHUNK_CHARS):
                try:
                    run_lark(['docs', '+update', '--doc', doc_id, '--command', 'append',
                              '--doc-format', 'markdown', '--content', '-',
                              '--as', 'user', '--format', 'json'],
                             cwd=cwd, stdin_data=chunk, timeout=180)
                    n_text += 1
                except Exception as e:  # noqa: BLE001
                    print('  ! chunk FAIL:', str(e)[:120])
                time.sleep(0.2)

        print(f'  ✓ text appends: {n_text} / images: {n_img}/{n_imgs}')
        docs[key] = doc_id
        save_state(state)

    print('\n=== 修复完成 ===')


if __name__ == '__main__':
    main()
