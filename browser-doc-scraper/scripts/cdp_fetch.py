#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""通过 Chrome DevTools Protocol 抓取指定文章，提取 swagger 图片真实 http 地址。
不依赖 playwright（兼容新版 Chrome）。
"""
import json, time, urllib.request, re
import websocket

CDP = 'http://127.0.0.1:9222'
COURSE_ID = '1826803928691945473'
ARTICLE_ID = '1864221661471145985'
KEY = 'api.codefather.cn/api/course_article/get/vo/safe'


def new_tab(url):
    req = urllib.request.Request(f'{CDP}/json/new?{url}', method='PUT')
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def main():
    tab = new_tab(f'https://www.codefather.cn/course/{COURSE_ID}/section/{ARTICLE_ID}')
    ws_url = tab['webSocketDebuggerUrl']
    print('tab:', tab.get('url'))
    ws = websocket.create_connection(ws_url, timeout=60, suppress_origin=True)
    mid = [0]
    done = [False]

    def send(method, params=None):
        mid[0] += 1
        ws.send(json.dumps({'id': mid[0], 'method': method, 'params': params or {}}))
        while True:
            msg = json.loads(ws.recv())
            if msg.get('id') == mid[0]:
                return msg.get('result', {})

    def handle(data):
        md = data.get('content') or ''
        print('捕获文章内容，长度', len(md))
        pairs = re.findall(r'!\[[^\]]*\]\(([^)]+)\)|<img[^>]+src=["\']([^"\']+)["\']', md)
        flat = [a or b for a, b in pairs]
        print('图片数', len(flat))
        for u in flat:
            print('IMG', u[:200])
        sw = [u for u in flat if 'swagger' in u.lower()]
        print('SWAGGER:', sw)
        json.dump({'md': md}, open(r'D:\Desktop\temp\.workbuddy\cdp-scraper\swagger_article.json', 'w', encoding='utf-8'), ensure_ascii=False)
        done[0] = True

    send('Network.enable')
    send('Page.enable')

    deadline = time.time() + 40
    while time.time() < deadline and not done[0]:
        try:
            ws.settimeout(2)
            msg = json.loads(ws.recv())
        except Exception:
            continue
        if msg.get('method') == 'Network.responseReceived':
            u = msg['params']['response']['url']
            if KEY in u:
                rid = msg['params']['requestId']
                mid[0] += 1
                ws.send(json.dumps({'id': mid[0], 'method': 'Network.getResponseBody',
                                     'params': {'requestId': rid}}))
                while True:
                    m2 = json.loads(ws.recv())
                    if m2.get('id') == mid[0]:
                        body = m2.get('result', {}).get('body', '')
                        try:
                            data = json.loads(body).get('data') or {}
                            if str(data.get('id')) == str(ARTICLE_ID):
                                handle(data)
                            else:
                                print('其他文章 id', data.get('id'))
                        except Exception as e:
                            print('parse err', e)
                        break
    ws.close()
    print('done', done[0])


if __name__ == '__main__':
    main()
