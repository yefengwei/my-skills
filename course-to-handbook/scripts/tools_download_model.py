#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
模型下载工具（course-to-handbook skill 用）
============================================
一次性把 Systran/faster-whisper-small 下载到数据盘缓存（D:/software/ai-models），
之后所有转写全程离线。仅在模型缺失时手动运行本脚本。

约束（源自 agent-env-policy.md）:
  - 模型一律下到数据盘，不占系统盘
  - 代理环境变量显式传入本进程（不赌系统代理配置）；无代理时 unset 直连
  - 下载完成后把快照目录里的符号链接替换为真实文件副本
    （Windows 非管理员进程建符号链接会静默失败成 0 字节占位 —— 踩过实测）

用法:
    python tools_download_model.py [--proxy http://127.0.0.1:7890] [--dest D:/software/ai-models/huggingface/hub]
"""
import argparse
import os
import shutil
import sys
from pathlib import Path

MODEL_ID = 'Systran/faster-whisper-small'


def fix_symlink_snapshot(snapshot_dir: Path):
    """把快照目录里的（可能是 0 字节的）符号链接替换为 blobs 真实文件副本。"""
    fixed = 0
    blobs = snapshot_dir.parent.parent / 'blobs'
    if not blobs.is_dir():
        return fixed
    for link in snapshot_dir.iterdir():
        # 真实文件直接跳过；坏链接（0 字节或指向不存在目标）替换
        if link.is_symlink():
            target = link.resolve()
            if target.exists() and target.stat().st_size > 0:
                continue  # 好链接，保留
            blob_name = Path(os.readlink(str(link))).name
            blob = blobs / blob_name
            link.unlink()
            if blob.exists() and blob.stat().st_size > 0:
                shutil.copy2(blob, link)
                fixed += 1
    return fixed


def main():
    ap = argparse.ArgumentParser(description='下载 faster-whisper-small 到数据盘（一次性）')
    ap.add_argument('--proxy', default='http://127.0.0.1:7890',
                    help='HTTP 代理；传 none 直连')
    ap.add_argument('--dest', default='D:/software/ai-models/huggingface/hub',
                    help='HF hub 缓存目录（数据盘）')
    args = ap.parse_args()

    if args.proxy.lower() != 'none':
        os.environ['HTTP_PROXY'] = os.environ['HTTPS_PROXY'] = args.proxy
        os.environ.pop('HF_HUB_OFFLINE', None)
    else:
        for k in ('HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy'):
            os.environ.pop(k, None)

    os.environ['HF_HUB_CACHE'] = args.dest
    print(f'[缓存] HF_HUB_CACHE = {args.dest}')
    print(f'[代理] {os.environ.get("HTTPS_PROXY", "直连")}')

    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        print('[错误] 缺 huggingface_hub："<python 绝对路径>" -m pip install huggingface_hub',
              file=sys.stderr)
        sys.exit(2)

    path = snapshot_download(MODEL_ID)
    snap = Path(path)
    print(f'[完成] 快照: {snap}')

    # 校验关键文件
    mb = snap / 'model.bin'
    if not mb.exists() or mb.stat().st_size < 100 * 1024 * 1024:
        print('[错误] model.bin 缺失或过小，下载不完整，请重跑本脚本', file=sys.stderr)
        sys.exit(1)
    print(f'[校验] model.bin {mb.stat().st_size / 1024 / 1024:.0f} MB OK')

    n = fix_symlink_snapshot(snap)
    print(f'[修复] 替换坏符号链接为真实副本: {n} 个' if n else '[检查] 快照无坏链接')

    print('\n后续转写请直接用本快照路径（transcribe_local.py 会自动找到它）:')
    print(f'  {snap}')


if __name__ == '__main__':
    main()
