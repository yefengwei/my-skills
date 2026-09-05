#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""抽样验证：还原出的 http URL 下载后，与本地 images/<hash>.png 尺寸是否一致。"""
import json, os, io, random, ssl, urllib.request
from PIL import Image

ssl._create_default_https_context = ssl._create_unverified_context
HDR = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
BASE = r'D:\Desktop\temp'

items = json.load(open(r'D:\Desktop\temp\.workbuddy\cdp-scraper\img_items.json', encoding='utf-8'))
h2u = json.load(open(r'D:\Desktop\temp\.workbuddy\cdp-scraper\urlpool.json', encoding='utf-8'))['h2u']

loc = [i for i in items if i['url'].startswith('images/')]
random.seed(7)
sample = random.sample(loc, 15)
ok = bad = 0
for i in sample:
    md_dir = os.path.dirname(i['file'])
    local = os.path.join(md_dir, i['url'].split('#')[0].replace('/', os.sep))
    h = os.path.basename(i['url'].split('#')[0]).rsplit('.', 1)[0]
    url = h2u.get(h)
    if not url:
        print('NO-MAP', local); bad += 1; continue
    try:
        req = urllib.request.Request(url, headers=HDR)
        with urllib.request.urlopen(req, timeout=25) as r:
            data = r.read()
        rim = Image.open(io.BytesIO(data))
        lim = Image.open(local)
        same = rim.size == lim.size
        print(('OK ' if same else 'DIFF'), rim.size, lim.size, '|', os.path.basename(local)[:12], '|', url[-45:])
        ok += same; bad += (not same)
    except Exception as e:
        print('ERR', type(e).__name__, str(e)[:60], url)
        bad += 1
print('抽样一致', ok, '不一致/失败', bad)
