# -*- coding: utf-8 -*-
"""
通过手动启动 Chrome (--remote-debugging-port) + playwright connectOverCDP 截图 SVG。
本机沙箱下 chromium.launch() 会因 --remote-debugging-pipe 失败，必须走 connectOverCDP 路线。

用法：python svg2png_cdp.py <input.svg> <output.png> [port]
"""
import os
import re
import socket
import subprocess
import sys
import time

from lark_env import CHROME, CDP_PORT, CDP_PROFILE


def wait_port(port, timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        with socket.socket() as s:
            s.settimeout(0.5)
            try:
                s.connect(('127.0.0.1', port))
                return True
            except OSError:
                time.sleep(0.3)
    return False


def port_listening(port):
    with socket.socket() as s:
        s.settimeout(0.3)
        try:
            s.connect(('127.0.0.1', port))
            return True
        except OSError:
            return False


def launch_chrome(port):
    if port_listening(port):
        return
    subprocess.Popen(
        [CHROME, '--headless=new', '--disable-gpu', '--no-sandbox',
         f'--remote-debugging-port={port}', f'--user-data-dir={CDP_PROFILE}',
         'about:blank'],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
    )
    if not wait_port(port, 25):
        raise RuntimeError(f'Chrome CDP 端口 {port} 未起')


def viewbox(svg_text):
    m = re.search(r'<svg\b[^>]*\bviewBox\s*=\s*"([^"]+)"', svg_text)
    if not m:
        m = re.search(r'<svg\b[^>]*\bwidth\s*=\s*"(\d+)"[^>]*\bheight\s*=\s*"(\d+)"', svg_text)
        if m:
            return float(m.group(1)), float(m.group(2))
        return 300.0, 300.0
    parts = m.group(1).split()
    if len(parts) == 4:
        return float(parts[2]), float(parts[3])
    return 300.0, 300.0


def main():
    if len(sys.argv) < 3:
        print('usage: svg2png_cdp.py <input.svg> <output.png> [port]', file=sys.stderr)
        sys.exit(2)
    src, dst = sys.argv[1], sys.argv[2]
    port = int(sys.argv[3]) if len(sys.argv) > 3 else CDP_PORT

    os.makedirs(CDP_PROFILE, exist_ok=True)
    launch_chrome(port)

    from playwright.sync_api import sync_playwright
    w, h = viewbox(open(src, encoding='utf-8', errors='replace').read())
    pad = 8
    vw, vh = int(w) + 2 * pad, int(h) + 2 * pad

    with sync_playwright() as p:
        b = p.chromium.connect_over_cdp(f'http://127.0.0.1:{port}')
        ctx = b.contexts[0] if b.contexts else b.new_context()
        page = ctx.new_page()
        page.set_viewport_size({'width': vw, 'height': vh})
        abs_path = os.path.abspath(src).replace('\\', '/')
        page.goto('file:///' + abs_path.lstrip('/'))
        page.wait_for_load_state('networkidle')
        page.screenshot(path=dst, full_page=False, omit_background=False)
        page.close()
        b.close()
    print('OK', os.path.getsize(dst), dst)


if __name__ == '__main__':
    main()
