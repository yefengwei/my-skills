#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 5 门课程正式 md 中的远程 http 图片链接全部内嵌为本地 images/ 引用。

- 复用各子目录 images/ 已有缓存（命名与 embed_images.py 一致：md5(url).<ext>）
- webp 下载后转 PNG（保持飞书 docx 兼容），其余格式原样保存
- ``` 代码块内的 ![]() 是教程示例代码，不修改
- 用法: python embed_md.py          (dry-run 统计)
        python embed_md.py --apply  (实际改写，先全量备份)
"""
import os, re, sys, hashlib, shutil, time, io, urllib.request

COURSES = [
    "Next.js + Elasticsearch 智能面试刷题平台",
    "Vue3 + SpringBoot + AI + DDD 企业级智能协同云图库项目",
    "SpringAI + RAG + MCP 全栈 ｜ AI 超级智能体企业级实战",
    "Python 全栈 ｜ AI 闯关学习小程序项目教程",
    "LangChain4j + 工作流 + 微服务 AI 零代码应用生成平台",
]
BASE = r"D:/Desktop/temp"
HDR = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
IMG_RE = re.compile(r'!\[([^\]]*)\]\((https?://[^)\s]+)\)', re.I)
HTML_IMG_RE = re.compile(r'(<img[^>]+?src=)(["\'])(https?://[^"\'> ]+)\2', re.I)
IMG_EXT = re.compile(r'\.(webp|png|jpg|jpeg|gif|svg|bmp|avif)(?:[?#].*)?$', re.I)

def is_img_url(u):
    return bool(IMG_EXT.search(u)) or 'pic.code-nav' in u or 'codefather' in u

def url_hash(u):
    return hashlib.md5(u.encode('utf-8')).hexdigest()

def ext_of(u):
    m = IMG_EXT.search(u)
    return m.group(1).lower() if m else 'png'

def split_fences(text):
    """返回 [(start,end,in_fence)] 行区间；用行扫描标记每行是否在 fence 内。"""
    lines = text.split('\n')
    flags = []
    fence = False
    for l in lines:
        if re.match(r'^\s*(```|~~~)', l):
            flags.append(True)      # 本行属于 fence 边界，视为代码行
            fence = not fence
            continue
        flags.append(fence)
    return lines, flags

def download(u, img_dir):
    h = url_hash(u)
    e = ext_of(u)
    if e == 'webp':
        dest = os.path.join(img_dir, f'{h}.png'); rel = f'images/{h}.png'
    else:
        dest = os.path.join(img_dir, f'{h}.{e}'); rel = f'images/{h}.{e}'
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        return rel, 'cached'
    data = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(u, headers=HDR)
            with urllib.request.urlopen(req, timeout=25) as r:
                data = r.read()
            break
        except Exception as ex:
            data = None
            if attempt == 2:
                return None, str(ex)
            time.sleep(1.5 * (attempt + 1))
    try:
        if e == 'webp':
            from PIL import Image
            im = Image.open(io.BytesIO(data)).convert('RGB')
            im.save(dest, 'PNG')
        else:
            with open(dest, 'wb') as f:
                f.write(data)
        if os.path.getsize(dest) > 0:
            return rel, 'downloaded'
        os.remove(dest)
    except Exception as ex:
        return None, 'save:' + str(ex)
    return None, 'empty'

def iter_formal_mds():
    for c in COURSES:
        for dp, dn, fn in os.walk(os.path.join(BASE, c)):
            for f in fn:
                if not f.lower().endswith('.md'): continue
                if f.endswith('.__tmp__.md') or '.__embed__' in f: continue
                yield os.path.join(dp, f)

def main(apply=False):
    total_links = total_missing = total_fail = total_files = 0
    fail_list = []
    if apply:
        ts = time.strftime('%Y%m%d_%H%M%S')
        bdir = os.path.join(BASE, '.workbuddy', f'md_backup_embed_{ts}')
        os.makedirs(bdir, exist_ok=True)
        print(f'备份目录: {bdir}')
    for p in iter_formal_mds():
        with open(p, 'r', encoding='utf-8') as f:
            text = f.read()
        lines, flags = split_fences(text)
        base = os.path.dirname(p)
        img_dir = os.path.join(base, 'images')
        cache, n_link, changed = {}, 0, False
        new_lines = []
        for i, (l, in_fence) in enumerate(zip(lines, flags)):
            if in_fence:
                new_lines.append(l); continue
            def get_rel(u):
                """下载/取缓存，返回 (rel, msg)，并计入链接统计。"""
                nonlocal n_link
                n_link += 1
                if u not in cache:
                    cache[u] = download(u, img_dir)
                return cache[u]

            def repl_md(m):
                nonlocal changed
                alt, u = m.group(1), m.group(2)
                if not is_img_url(u):
                    return m.group(0)
                rel, msg = get_rel(u)
                if rel:
                    changed = True
                    return f'![{alt}]({rel})'
                fail_list.append((os.path.relpath(p, BASE), u, msg))
                return m.group(0)

            def repl_html(m):
                nonlocal changed
                pre, q, u = m.group(1), m.group(2), m.group(3)
                if not is_img_url(u):
                    return m.group(0)
                rel, msg = get_rel(u)
                if rel:
                    changed = True
                    return f'{pre}{q}{rel}{q}'
                fail_list.append((os.path.relpath(p, BASE), u, msg))
                return m.group(0)

            nl = IMG_RE.sub(repl_md, l)
            nl = HTML_IMG_RE.sub(repl_html, nl)
            new_lines.append(nl)
        if n_link == 0:
            continue
        total_files += 1
        total_links += n_link
        total_missing += sum(1 for v in cache.values() if v[1] == 'downloaded')
        total_fail += sum(1 for v in cache.values() if v[0] is None)
        if apply and changed:
            rel = os.path.relpath(p, BASE)
            dst = os.path.join(bdir, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(p, dst)
            with open(p, 'w', encoding='utf-8') as f:
                f.write('\n'.join(new_lines))
        status = '已改写' if (apply and changed) else ('待改写' if changed else '无需改动')
        print(f'[{status}] {os.path.relpath(p, BASE)}: 链接 {n_link}, 需下载 {sum(1 for v in cache.values() if v[1]=="downloaded")}, 失败 {sum(1 for v in cache.values() if v[0] is None)}')
    print(f'\n==== 汇总: 文件 {total_files}, 链接 {total_links}, 需下载 {total_missing}, 失败 {total_fail} ====')
    if fail_list:
        print('失败清单:')
        for fp, u, m in fail_list[:30]:
            print(' ', fp, '|', u[:100], '|', m[:60])

if __name__ == '__main__':
    main(apply='--apply' in sys.argv)
