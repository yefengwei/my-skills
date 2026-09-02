# -*- coding: utf-8 -*-
"""
对丢失图片/正文的文档做最终修复（最可靠方案）。
策略：删旧 → 创建一个空文档 → 反复用 docs +update --command append 追加短片段（每片 ≤ 2000 字符），
在需要插图的位置用 docs +media-insert 插入图片。
所有内容都走小分片，绕开 create 阶段可能存在的块数 / 字符数未知上限。
"""
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from lark_env import BASE, LARK_ENTRY, NODE_BIN, clean_env
from verify import run, children
import lark_md_prep  # noqa: E402

STATE = os.path.join(HERE, 'state.json')
CHUNK_CHARS = 1800   # 每次 append 的字符上限

# 需要修复的文档（相对 BASE 的路径）；新项目按需修改
TARGETS = [
    r'Next.js + Elasticsearch 智能面试刷题平台\项目面试题\面试刷题平台面试题文档(程序员鱼皮).md',
    r'Next.js + Elasticsearch 智能面试刷题平台\万用模板\3. 前端万用项目模板介绍(程序员鱼皮).md',
    r'Python 全栈 ｜ AI 闯关学习小程序项目教程\项目教程\7. 用户系统开发(程序员鱼皮).md',
    r'Python 全栈 ｜ AI 闯关学习小程序项目教程\项目教程\9. AI 生成题目优化（联网搜索）(程序员鱼皮).md',
    r'Vue3 + SpringBoot + AI + DDD 企业级智能协同云图库项目\文字教程\2 - 项目初始化(程序员鱼皮).md',
]


def title_of(fn):
    t = fn[:-3] if fn.lower().endswith('.md') else fn
    return re.sub(r'[（(]\s*程序员鱼皮\s*[)）]\s*$', '', t).strip()


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


def delete_node(token):
    d = run(['wiki', '+node-delete', '--node-token', token, '--obj-type', 'wiki', '--yes',
             '--as', 'user', '--format', 'json'], timeout=120)
    return bool(d and d.get('ok'))


def split_text_by_paragraph(text, max_chars):
    """把一段长文本按段落（双换行）切成不超过 max_chars 的片段。"""
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
    state = json.load(open(STATE, encoding='utf-8'))
    nodes, docs = state['nodes'], state.setdefault('docs', {})

    limit = int(os.environ.get('LIMIT', '0'))
    only = os.environ.get('ONLY', '').strip()
    skip = os.environ.get('SKIP', '').strip()
    targets = TARGETS[:limit] if limit else list(TARGETS)
    if only:
        targets = [t for t in targets if only in t]
    if skip:
        targets = [t for t in targets if skip not in t]

    for rel in targets:
        title = title_of(os.path.basename(rel))
        proj, sub = rel.split('\\')[0], rel.split('\\')[1]
        parent = nodes.get('dir:%s|%s' % (proj, sub))
        if not parent:
            print('!! 无父节点', rel); continue
        print(f'\n========== {title} ==========')

        # 删旧
        for k in children(parent):
            if k.get('title') == title:
                print('  删', 'OK' if delete_node(k['node_token']) else 'FAIL', k['node_token'])
                time.sleep(0.4)
        docs.pop(rel, None)

        # 准备
        abs_md = os.path.join(BASE, rel)
        cwd = os.path.dirname(abs_md)
        full = lark_md_prep.transform_file(abs_md)
        parts = re.split(r'(!\[[^\]]*\]\(@\./[^)]+\))', full)
        n_imgs = (len(parts) - 1) // 2

        # 创建空文档（用一句空格）
        data = run_lark(['docs', '+create', '--doc-format', 'markdown', '--content', '-',
                         '--title', title, '--parent-token', parent,
                         '--as', 'user', '--format', 'json'],
                        cwd=cwd, stdin_data=' ', timeout=300)
        doc_id = data['data']['document']['document_id']
        print(f'  ✓ 创建 {doc_id}')

        # 逐段：text0 → (img1, text1) → (img2, text2) → ...
        # 每段 text 按段落切 ≤ 1800 字符的 chunks
        n_text_appends = n_img_appends = 0
        # text0
        for chunk in split_text_by_paragraph(parts[0], CHUNK_CHARS):
            try:
                run_lark(['docs', '+update', '--doc', doc_id, '--command', 'append',
                          '--doc-format', 'markdown', '--content', '-',
                          '--as', 'user', '--format', 'json'],
                         cwd=cwd, stdin_data=chunk, timeout=180)
                n_text_appends += 1
            except Exception as e:  # noqa: BLE001
                print('  ! text0 chunk FAIL:', str(e)[:120])
            time.sleep(0.2)
        # img/text pairs
        for k in range(1, len(parts), 2):
            img_tag = parts[k]                       # 形如 ![](@./images/xxx.png)
            m = re.match(r'!\[[^\]]*\]\(@\./([^)]+)\)', img_tag)
            img_rel = m.group(1) if m else None      # 纯相对路径 images/xxx.png
            img_path = os.path.join(cwd, img_rel) if img_rel else None
            if img_rel and os.path.exists(img_path):
                d = run_lark(['docs', '+media-insert', '--doc', doc_id,
                              '--file', img_rel, '--as', 'user', '--format', 'json'],
                             cwd=cwd, timeout=180)
                if d.get('ok'):
                    n_img_appends += 1
                else:
                    print(f'  ! img FAIL {os.path.basename(img_rel)}', d.get('error'))
            time.sleep(0.2)
            text_after = parts[k + 1] if k + 1 < len(parts) else ''
            for chunk in split_text_by_paragraph(text_after, CHUNK_CHARS):
                try:
                    run_lark(['docs', '+update', '--doc', doc_id, '--command', 'append',
                              '--doc-format', 'markdown', '--content', '-',
                              '--as', 'user', '--format', 'json'],
                             cwd=cwd, stdin_data=chunk, timeout=180)
                    n_text_appends += 1
                except Exception as e:  # noqa: BLE001
                    print('  ! text chunk FAIL:', str(e)[:120])
                time.sleep(0.2)

        print(f'  ✓ text appends: {n_text_appends}  /  images: {n_img_appends}/{n_imgs}')
        docs[rel] = doc_id
        json.dump(state, open(STATE, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)

    print('\n=== 完成 ===')


if __name__ == '__main__':
    main()
