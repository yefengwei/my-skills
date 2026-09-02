# -*- coding: utf-8 -*-
"""全量审计：逐个比对 120 篇文档的本地图片数 vs 飞书图片数。"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from lark_env import BASE
from verify import run
import lark_md_prep  # noqa: E402

STATE = os.path.join(HERE, 'state.json')


def main():
    state = json.load(open(STATE, encoding='utf-8'))
    docs = state['docs']

    rows = []
    for rel, did in sorted(docs.items()):
        try:
            local_imgs = re.findall(r'!\[[^\]]*\]\(@\./([^)]+)\)',
                                    lark_md_prep.transform_file(os.path.join(BASE, rel)))
        except FileNotFoundError:
            rows.append((rel, -1, -1))
            continue
        d = run(['docs', '+fetch', '--doc', did, '--doc-format', 'markdown',
                 '--as', 'user', '--format', 'json'], timeout=300)
        txt = d['data']['document']['content'] if d and d.get('ok') else ''
        remote_n = txt.count('![')
        rows.append((rel, len(local_imgs), remote_n))
        gap = len(local_imgs) - remote_n
        flag = 'OK ' if gap <= 0 else 'GAP'
        print('%-4s %-58s 本地 %3d / 飞书 %3d' %
              (flag, os.path.basename(rel)[:58], len(local_imgs), remote_n), flush=True)

    bad = [r for r in rows if r[1] > r[2]]
    print('\n===== 汇总 =====')
    print('文档总数: %d' % len(rows))
    print('图片完整: %d' % (len(rows) - len(bad)))
    print('图片缺失: %d' % len(bad))
    tot_local = sum(r[1] for r in rows if r[1] > 0)
    tot_remote = sum(r[2] for r in rows if r[2] > 0)
    print('图片总数: 本地 %d / 飞书 %d (保真率 %.1f%%)' %
          (tot_local, tot_remote, 100.0 * tot_remote / tot_local if tot_local else 100))
    if bad:
        print('\n缺失明细:')
        for rel, l, r in bad:
            print('  %-60s 缺 %d 张 (%d->%d)' % (rel, l - r, l, r))


if __name__ == '__main__':
    main()
