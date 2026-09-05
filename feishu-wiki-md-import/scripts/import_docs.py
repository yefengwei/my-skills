# -*- coding: utf-8 -*-
"""
阶段二：把 120 篇 Markdown（含原图）并发导入已建好的飞书知识库节点下。

- 严格保持本地目录结构：编程导航 / <项目名> / <子目录> / <文档标题>
- 文档标题去掉文件名末尾的「(程序员鱼皮)」
- 支持断点续传：已成功的文档记录在 state.json 中，重跑自动跳过
"""
import json
import os
import re
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lark_env import BASE, LARK_ENTRY, NODE_BIN, clean_env
import lark_md_prep  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, 'state.json')
LOG = os.path.join(HERE, 'import.log')
WORKERS = 2
MAX_RETRY = 5

# 试点阶段已导入的文档（相对 BASE 的路径 -> document_id）；重跑新项目时置空 {}
SEED_DOCS = {
    r'SpringAI + RAG + MCP 全栈 ｜ AI 超级智能体企业级实战\文字教程\1 - 项目总览(程序员鱼皮).md':
        'ZKsXdGD3not89yxolOEcDUwDnff',
}

_lock = threading.Lock()


def log(msg):
    with _lock:
        line = '[%s] %s' % (time.strftime('%H:%M:%S'), msg)
        print(line, flush=True)
        with open(LOG, 'a', encoding='utf-8') as f:
            f.write(line + '\n')


def natural_key(s):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r'(\d+)', s)]


def make_title(filename):
    t = filename[:-3] if filename.lower().endswith('.md') else filename
    t = re.sub(r'[（(]\s*程序员鱼皮\s*[)）]\s*$', '', t)
    return t.strip() or filename


def run_lark(args, cwd, stdin_data=None, timeout=1800):
    p = subprocess.run(
        [NODE_BIN, LARK_ENTRY] + args,
        input=stdin_data, capture_output=True, text=True,
        encoding='utf-8', errors='replace', env=clean_env(), cwd=cwd, timeout=timeout,
    )
    blob = (p.stdout or '') + (p.stderr or '')
    i = blob.find('{')
    if i < 0:
        raise RuntimeError('无 JSON 输出 (exit=%d): %s' % (p.returncode, blob[:300]))
    data = json.loads(blob[i:])
    if not data.get('ok'):
        raise RuntimeError(json.dumps(data.get('error', {}), ensure_ascii=False)[:300])
    return data


def import_one(rel_path, parent_token):
    """导入单篇文档，返回 document_id。"""
    abs_path = os.path.join(BASE, rel_path)
    cwd = os.path.dirname(abs_path)
    title = make_title(os.path.basename(abs_path))
    content = lark_md_prep.transform_file(abs_path)
    data = run_lark([
        'docs', '+create',
        '--doc-format', 'markdown',
        '--content', '-',
        '--title', title,
        '--parent-token', parent_token,
        '--as', 'user', '--format', 'json',
    ], cwd=cwd, stdin_data=content)
    doc = data['data']['document']
    warn = data['data'].get('warnings') or []
    return doc['document_id'], doc.get('url', ''), warn


def main():
    with open(STATE, encoding='utf-8') as f:
        state = json.load(f)
    nodes, docs = state['nodes'], state.setdefault('docs', {})
    docs.update({k: v for k, v in SEED_DOCS.items() if k not in docs})
    state.setdefault('failed', [])

    tasks = []
    for proj in sorted(os.listdir(BASE), key=natural_key):
        pdir = os.path.join(BASE, proj)
        if not os.path.isdir(pdir):
            continue
        for sub in sorted(os.listdir(pdir), key=natural_key):
            sdir = os.path.join(pdir, sub)
            if not os.path.isdir(sdir):
                continue
            key = 'dir:%s|%s' % (proj, sub)
            if key not in nodes:
                log('!! 缺少节点: %s' % key)
                continue
            for fn in sorted(os.listdir(sdir), key=natural_key):
                if not fn.lower().endswith('.md'):
                    continue
                rel = os.path.join(proj, sub, fn)
                if rel in docs:
                    continue
                tasks.append((rel, nodes[key]))

    limit = int(os.environ.get('LIMIT', '0'))
    if limit:
        tasks = tasks[:limit]
    log('待导入 %d 篇（已完成 %d 篇）' % (len(tasks), len(docs)))
    if not tasks:
        return

    done = failed = 0
    t0 = time.time()

    def work(item):
        rel, token = item
        last_err = ''
        for attempt in range(MAX_RETRY):
            try:
                doc_id, url, warn = import_one(rel, token)
                with _lock:
                    docs[rel] = doc_id
                if warn:
                    log('   warn %s: %s' % (os.path.basename(rel), json.dumps(warn, ensure_ascii=False)[:200]))
                return rel, doc_id, url, None
            except Exception as e:  # noqa: BLE001
                last_err = str(e)[:300]
                time.sleep(5 * (attempt + 1))
        return rel, None, None, last_err

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(work, t): t for t in tasks}
        for fut in as_completed(futs):
            rel, doc_id, url, err = fut.result()
            if err:
                failed += 1
                state['failed'].append({'path': rel, 'error': err})
                log('FAIL %s | %s' % (rel, err))
            else:
                done += 1
                log('OK(%d/%d) %s -> %s' % (done, len(tasks), rel, url))
            if (done + failed) % 5 == 0:
                with open(STATE, 'w', encoding='utf-8') as f:
                    json.dump(state, f, ensure_ascii=False, indent=2)

    with open(STATE, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    log('本轮完成: 成功 %d / 失败 %d / 累计 %d，耗时 %.1f 分钟'
        % (done, failed, len(docs), (time.time() - t0) / 60))


if __name__ == '__main__':
    main()
