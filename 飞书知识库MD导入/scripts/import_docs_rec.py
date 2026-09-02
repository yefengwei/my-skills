# -*- coding: utf-8 -*-
"""阶段二：把 easy-vibe 全部 md 导入到其直接父目录节点下（任意深度）。

md 挂载规则：md 所在目录 rel 路径 -> node_key -> 父节点 token。
根目录下 md 挂 root: 节点。
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
from ev_common import SRC, run, load_state, save_state, natural_key, make_title, node_key  # noqa: E402
from lark_env import LARK_ENTRY, NODE_BIN, clean_env  # noqa: E402
import lark_md_prep  # noqa: E402

STATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'state.json')
LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'import.log')
WORKERS = 2
MAX_RETRY = 5
_lock = threading.Lock()


def log(msg):
    with _lock:
        line = '[%s] %s' % (time.strftime('%H:%M:%S'), msg)
        print(line, flush=True)
        with open(LOG, 'a', encoding='utf-8') as f:
            f.write(line + '\n')


def run_lark(args, cwd, stdin_data=None, timeout=1800):
    p = subprocess.run([NODE_BIN, LARK_ENTRY] + args,
                       input=stdin_data, capture_output=True, text=True,
                       encoding='utf-8', errors='replace', env=clean_env(),
                       cwd=cwd, timeout=timeout)
    blob = (p.stdout or '') + (p.stderr or '')
    i = blob.find('{')
    if i < 0:
        raise RuntimeError('无 JSON 输出 (exit=%d): %s' % (p.returncode, blob[:300]))
    data = json.loads(blob[i:])
    if not data.get('ok'):
        raise RuntimeError(json.dumps(data.get('error', {}), ensure_ascii=False)[:300])
    return data


def list_md_files(root):
    """返回所有 md 文件 (abs_path, rel_of_dir 用 | 分隔, filename)。"""
    out = []

    def walk(d, rel):
        for f in sorted(os.listdir(d), key=natural_key):
            fp = os.path.join(d, f)
            if os.path.isdir(fp):
                walk(fp, f if not rel else rel + '|' + f)
            elif f.lower().endswith('.md'):
                out.append((fp, rel or '', f))
    walk(root, '')
    return out


def import_one(abs_path, rel_dir, filename, parent_token):
    cwd = os.path.dirname(abs_path)
    title = make_title(filename)
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
    state = load_state()
    nodes, docs = state['nodes'], state.setdefault('docs', {})
    state.setdefault('failed', [])

    tasks = []
    for abs_path, rel_dir, fn in list_md_files(SRC):
        key = 'doc:' + (rel_dir.replace('|', '/') + '/' if rel_dir else '') + fn
        if key in docs:
            continue
        parent_key = node_key(rel_dir)
        parent_tok = nodes.get(parent_key)
        if not parent_tok:
            log('!! 缺父节点 %s (doc %s)' % (parent_key, fn))
            continue
        tasks.append((abs_path, rel_dir, fn, parent_tok, key))

    limit = int(os.environ.get('LIMIT', '0'))
    if limit:
        tasks = tasks[:limit]
    log('待导入 %d 篇（已完成 %d 篇）' % (len(tasks), len(docs)))
    if not tasks:
        return

    done = failed = 0
    t0 = time.time()

    def work(item):
        abs_path, rel_dir, fn, tok, key = item
        last_err = ''
        for attempt in range(MAX_RETRY):
            try:
                doc_id, url, warn = import_one(abs_path, rel_dir, fn, tok)
                with _lock:
                    docs[key] = doc_id
                if warn:
                    log('   warn %s: %s' % (fn, json.dumps(warn, ensure_ascii=False)[:200]))
                return key, doc_id, url, None
            except Exception as e:  # noqa: BLE001
                last_err = str(e)[:300]
                time.sleep(5 * (attempt + 1))
        return key, None, None, last_err

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(work, t): t for t in tasks}
        for fut in as_completed(futs):
            key, doc_id, url, err = fut.result()
            if err:
                failed += 1
                state['failed'].append({'path': key, 'error': err})
                log('FAIL %s | %s' % (key, err))
            else:
                done += 1
                log('OK(%d/%d) %s -> %s' % (done, len(tasks), key, url))
            if (done + failed) % 5 == 0:
                save_state(state)

    save_state(state)
    log('本轮完成: 成功 %d / 失败 %d / 累计 %d，耗时 %.1f 分钟'
        % (done, failed, len(docs), (time.time() - t0) / 60))


if __name__ == '__main__':
    main()
