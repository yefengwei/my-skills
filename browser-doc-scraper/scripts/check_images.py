#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""本地 Markdown 图片链接体检与修复（通用版）。

用法:
  python check_images.py --base "D:/Desktop/temp"            # 只体检、输出报告
  python check_images.py --base "D:/Desktop/temp" --apply    # 体检 + 修复本地路径污染
  python check_images.py --base "D:/Desktop/temp" --no-probe # 跳过网络探测

做什么:
  1. 扫描 --base 下所有 .md，把图片引用分成三类:
       http(s) 外链 / 本地相对路径(真实引用) / 代码块内示例(不处理)
  2. 本地相对路径若形如 images/<hash>.<ext>（由 embed_images 类脚本按 md5(url) 命名），
     用「URL 池」反查还原成原始外链（--apply 才写盘，写盘前自动备份）
  3. 对全部外链做 HEAD 探测（403/405/501 自动回退 GET），统计有效/失效

URL 池来源（保证能反查到）:
  - md 中残留的 http 图片链接
  - 同目录下 *.json 抓取产物里的图片链接
  - 本地 images/ 缓存目录无法反查 hash，故池子越大命中率越高

判定规则要点:
  - ``` 围栏内的 picture?.url / ../assets/logo.png 等是教程示例代码，不是真实引用，跳过
  - picsum.photos 这类图床 HEAD 返回 405，必须回退 GET 才不会误判失效
  - 探测用 8 并发，429/5xx 自动退避重试
"""
import os, re, sys, json, time, shutil, hashlib, ssl, collections
import urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed

ssl._create_default_https_context = ssl._create_unverified_context
HDR = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
       'Referer': 'https://www.code-nav.cn/'}
MD_IMG = re.compile(r"!\[[^\]]*\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
HTML_IMG = re.compile(r"<img[^>]+src=[\"']([^\"']+)[\"']", re.I)
IMG_URL_IN_TEXT = re.compile(r'https?://[^\s"\'\\ )\u4e00-\u9fff]+\.(?:png|jpg|jpeg|gif|webp|svg|bmp)', re.I)


def is_temp(fn):
    return '__tmp__' in fn or '__embed__' in fn


def scan(base):
    """返回 {file: {'formal':bool,'http':[],'local':[],'code':[]}}"""
    res = {}
    for dirpath, dirnames, filenames in os.walk(base):
        if '.workbuddy' in dirpath or 'node_modules' in dirpath:
            continue
        for fn in filenames:
            if not fn.lower().endswith('.md'):
                continue
            path = os.path.join(dirpath, fn)
            formal = not is_temp(fn)
            info = {'formal': formal, 'http': [], 'local': [], 'code': []}
            lines = open(path, 'r', encoding='utf-8', errors='ignore').read().split('\n')
            fence = False
            for line in lines:
                if line.lstrip().startswith('```'):
                    fence = not fence
                for u in MD_IMG.findall(line) + HTML_IMG.findall(line):
                    u = u.strip()
                    if not u:
                        continue
                    key = 'code' if fence else ('http' if u.startswith(('http://', 'https://')) else 'local')
                    info[key].append(u)
            res[path] = info
    return res


def build_url_pool(base, scanned):
    pool = set()
    for info in scanned.values():
        pool.update(info['http'])
    for dirpath, _, filenames in os.walk(base):
        if '.workbuddy' in dirpath or 'node_modules' in dirpath:
            continue
        for fn in filenames:
            if fn.lower().endswith('.json'):
                try:
                    pool.update(IMG_URL_IN_TEXT.findall(open(os.path.join(dirpath, fn), encoding='utf-8', errors='ignore').read()))
                except Exception:
                    pass
    return pool


def restore(scanned, h2u, base, backup_root):
    """把 images/<hash>.<ext> 还原成 http 外链。返回 (文件数, 链接数, 未还原样例)"""
    MD_FULL = re.compile(r'(!\[[^\]]*\]\()(\s*<?)([^)\s>]+)(>?(?:\s+"[^"]*")?\s*\))')
    files = links = 0
    unresolved = []
    for path, info in scanned.items():
        if not info['local']:
            continue
        text = open(path, 'r', encoding='utf-8', errors='ignore').read()
        n = [0]

        def repl(m):
            rel = m.group(3)
            if not rel.startswith('images/'):
                return m.group(0)
            h = os.path.basename(rel.split('#')[0]).rsplit('.', 1)[0]
            url = h2u.get(h)
            if not url:
                unresolved.append(rel)
                return m.group(0)
            n[0] += 1
            return f'{m.group(1)}{url}{m.group(4)}'

        new_text = MD_FULL.sub(repl, text)
        if n[0] and new_text != text:
            dst = os.path.join(backup_root, os.path.relpath(path, base))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(path, dst)
            open(path, 'w', encoding='utf-8', newline='').write(new_text)
            files += 1
            links += n[0]
    return files, links, unresolved[:10]


def probe(u):
    for attempt in range(3):
        try:
            req = urllib.request.Request(u, headers=HDR, method='HEAD')
            with urllib.request.urlopen(req, timeout=20) as r:
                ct = r.headers.get('Content-Type', '') or ''
                if r.status == 200 and ct.startswith('image/'):
                    return u, True, r.status
                if r.status in (400, 403, 405, 501):
                    raise urllib.error.HTTPError(u, r.status, 'no-head', r.headers, None)
                return u, False, r.status
        except urllib.error.HTTPError as e:
            if e.code in (400, 403, 405, 501):
                try:
                    with urllib.request.urlopen(urllib.request.Request(u, headers=HDR), timeout=20) as r2:
                        return u, r2.status == 200, r2.status
                except Exception:
                    return u, False, e.code
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(1.5 * (attempt + 1))
                continue
            return u, False, e.code
        except Exception:
            time.sleep(1.0 * (attempt + 1))
            continue
    return u, False, 0


def main():
    args = sys.argv[1:]
    if '--base' not in args:
        print(__doc__)
        sys.exit(1)
    base = args[args.index('--base') + 1]
    apply = '--apply' in args
    do_probe = '--no-probe' not in args

    print('扫描中...', flush=True)
    scanned = scan(base)
    formal = {p: i for p, i in scanned.items() if i['formal']}
    tmp = {p: i for p, i in scanned.items() if not i['formal']}
    g = collections.Counter()
    for p, i in scanned.items():
        g['http'] += len(i['http']); g['local'] += len(i['local']); g['code'] += len(i['code'])
    fg = collections.Counter()
    for i in formal.values():
        fg['http'] += len(i['http']); fg['local'] += len(i['local']); fg['code'] += len(i['code'])
    print(f"md 总数 {len(scanned)}（正式 {len(formal)} / 中间产物 {len(tmp)}）")
    print(f"图片引用: http {g['http']}  本地相对路径 {g['local']}  代码块示例 {g['code']}")
    print(f"其中正式文档: http {fg['http']}  本地 {fg['local']}  代码块 {fg['code']}")

    # 本地路径形态
    shapes = collections.Counter()
    for i in scanned.values():
        for u in i['local']:
            shapes['images/<hash>' if u.startswith('images/') else u.split('/')[0] + '/*'] += 1
    if shapes:
        print('本地路径形态:', dict(shapes))

    if apply and g['local']:
        pool = build_url_pool(base, scanned)
        h2u = {}
        for u in pool:
            h2u.setdefault(hashlib.md5(u.encode('utf-8')).hexdigest(), u)
        ts = time.strftime('%Y%m%d_%H%M%S')
        backup_root = os.path.join(base, '.workbuddy', f'md_backup_{ts}')
        f, n, unres = restore(scanned, h2u, base, backup_root)
        print(f'已还原 {n} 处链接（{f} 个文件），备份: {backup_root}')
        if unres:
            print('无法反查（需人工处理）:', unres)
        scanned = scan(base)

    all_urls = sorted({u for i in scanned.values() for u in i['http']})
    print('待探测去重 URL:', len(all_urls), flush=True)
    bad = []
    if do_probe and all_urls:
        with ThreadPoolExecutor(max_workers=8) as ex:
            futs = [ex.submit(probe, u) for u in all_urls]
            done = 0
            for fu in as_completed(futs):
                u, ok, st = fu.result()
                if not ok:
                    bad.append((u, st))
                done += 1
                if done % 500 == 0:
                    print(f'  {done}/{len(all_urls)} bad={len(bad)}', flush=True)
    print(f'探测结果: {len(all_urls) - len(bad)}/{len(all_urls)} 有效')
    for u, st in bad[:30]:
        print('  BAD', st, u)

    # 报告
    out = os.path.join(base, '.workbuddy', 'check_images_report.md')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    L = ['# 图片链接体检报告', '', f'生成时间：{time.strftime("%Y-%m-%d %H:%M:%S")}',
         f'扫描目录：{base}', '',
         f'- md 总数：{len(scanned)}（正式 {len(formal)}，中间产物 {len(tmp)}）',
         f'- http 外链：{g["http"]} 处，去重 {len(all_urls)} 个',
         f'- 本地相对路径：{g["local"]} 处',
         f'- 代码块示例（不处理）：{g["code"]} 处',
         f'- 探测：{len(all_urls) - len(bad)}/{len(all_urls)} 有效，失效 {len(bad)} 个', '']
    if bad:
        L += ['## 失效链接', ''] + [f'- `{u}` → HTTP {st}' for u, st in bad]
    else:
        L += ['## 失效链接', '', '无。']
    open(out, 'w', encoding='utf-8').write('\n'.join(L))
    print('报告:', out)


if __name__ == '__main__':
    main()
