#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 Markdown 里的远程图片下载到本地 images/，webp 转 PNG，改写为本地相对路径，
并用 pandoc 生成内嵌图片的 docx（与原 md 同名，便于飞书按标题精确替换旧文档）。

用法:
  python embed_images.py <md文件>

- 不改写原 md；生成临时 <原名>.__tmp__.md 与 <原名>.docx
- 图片缓存到 <md所在目录>/images/，按 URL 哈希命名（同目录内去重复用）
- webp 自动转 PNG（飞书 docx 导入不支持 webp，PNG 正常）
"""
import subprocess, sys, os, re, hashlib, time, io, urllib.request, urllib.error
from PIL import Image

IMG_RE = re.compile(r'!\[([^\]]*)\]\((https?://[^\s)]+\.(?:webp|png|jpg|jpeg|gif))\)', re.I)
HDR = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

def url_hash(url):
    return hashlib.md5(url.encode('utf-8')).hexdigest()

def ext_of(url):
    m = re.search(r'\.(webp|png|jpg|jpeg|gif)(?:[?#].*)?$', url, re.I)
    return (m.group(1).lower() if m else 'webp')

def download(url, img_dir):
    """返回 (ok, rel_path, msg)。webp 转 PNG，其余按原格式。"""
    h = url_hash(url)
    ext = ext_of(url)
    if ext == 'webp':
        rel = f"images/{h}.png"
        dest = os.path.join(img_dir, f"{h}.png")
        if os.path.exists(dest) and os.path.getsize(dest) > 0:
            return True, rel, 'cached'
        try:
            req = urllib.request.Request(url, headers=HDR)
            with urllib.request.urlopen(req, timeout=20) as r:
                data = r.read()
            im = Image.open(io.BytesIO(data)).convert('RGB')
            im.save(dest, 'PNG')
            if os.path.getsize(dest) > 0:
                return True, rel, 'downloaded'
            os.remove(dest)
        except Exception as e:
            return False, None, str(e)
    else:
        rel = f"images/{h}.{ext}"
        dest = os.path.join(img_dir, f"{h}.{ext}")
        if os.path.exists(dest) and os.path.getsize(dest) > 0:
            return True, rel, 'cached'
        try:
            req = urllib.request.Request(url, headers=HDR)
            with urllib.request.urlopen(req, timeout=20) as r, open(dest, 'wb') as f:
                f.write(r.read())
            if os.path.getsize(dest) > 0:
                return True, rel, 'downloaded'
            os.remove(dest)
        except Exception as e:
            return False, None, str(e)
    return False, None, 'unknown'

def process(md_path):
    base = os.path.dirname(os.path.abspath(md_path))
    img_dir = os.path.join(base, 'images')
    os.makedirs(img_dir, exist_ok=True)
    with open(md_path, 'r', encoding='utf-8') as f:
        text = f.read()

    urls = sorted(set(m[1] for m in IMG_RE.findall(text)))
    cache = {}
    ok = 0
    for i, url in enumerate(urls, 1):
        ok_dl, rel, msg = download(url, img_dir)
        if ok_dl and rel:
            cache[url] = rel
            ok += 1
        else:
            print(f"  [FAIL {i}/{len(urls)}] {url} :: {msg}")
        if i % 25 == 0:
            print(f"  ... {i}/{len(urls)}")

    def repl(m):
        alt, url = m.group(1), m.group(2)
        if url in cache:
            return f"![{alt}]({cache[url]})"
        return m.group(0)

    new_text = IMG_RE.sub(repl, text)
    stem = os.path.splitext(os.path.basename(md_path))[0]
    tmp_md = os.path.join(base, f"{stem}.__tmp__.md")
    with open(tmp_md, 'w', encoding='utf-8') as f:
        f.write(new_text)
    out_docx = os.path.join(base, f"{stem}.docx")
    try:
        subprocess.run(['pandoc', tmp_md, '-o', out_docx], check=True,
                       cwd=base, capture_output=True, text=True)
        import zipfile
        with zipfile.ZipFile(out_docx) as z:
            media = [n for n in z.namelist() if n.startswith('word/media/')]
        print(f"[*] {stem}: 图片 {ok}/{len(urls)} 成功, docx 内嵌 {len(media)} 张 -> {out_docx}")
        return out_docx, ok, len(urls), len(media)
    except Exception as e:
        print(f"[!] pandoc 失败 {stem}: {e}")
        return None, ok, len(urls), 0

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("用法: python embed_images.py <md>")
        sys.exit(1)
    process(sys.argv[1])
