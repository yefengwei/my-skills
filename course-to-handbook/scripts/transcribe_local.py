#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
本地转写脚本（course-to-handbook skill 用）
============================================
基于 Faster-Whisper + 本地 whisper small 模型，把音频/视频转写为 SRT。

核心原则（踩坑沉淀）：
  1. 模型必须走本地快照路径直传 —— 传 'small' 字符串会触发联网下载，
     被系统代理拦截时直接 502/超时。
  2. 模型查找顺序（找到即用，全程离线）：
     a) --model 显式指定的快照路径
     b) $HF_HUB_CACHE / $HF_HOME 下的 models--Systran--faster-whisper-small
     c) 默认数据盘 D:/software/ai-models/huggingface/hub/...
     d) 默认用户缓存 C:/Users/ysq/.cache/huggingface/hub/...
     e) 以上都没有 → 退出并提示先用 tools_download_model.py 下载（不自动联网）
  3. 输出 0 字节视为失败，脚本返回非零码（供并行编排判断重跑）。

用法:
    python transcribe_local.py <媒体文件或目录> [-o 输出目录] [--language zh|en|None]
                               [--model 快照路径] [--cpu-threads 8] [--beam 5]

- 输入目录时递归扫描 .mp4/.m4a/.mp3/.wav/.flv/.mkv/.webm/.aac/.flac
- 已存在的同名 .srt 默认跳过（断点续传）；--force 覆盖
- 输出 .srt 与源文件同目录（或 -o 指定目录，保持相对结构）
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

MEDIA_EXTS = {'.mp4', '.m4a', '.mp3', '.wav', '.flv', '.mkv', '.webm', '.aac', '.flac'}
MODEL_REPO = 'models--Systran--faster-whisper-small'

# 候选模型根目录（按序探测）
CANDIDATE_ROOTS = [
    os.environ.get('HF_HUB_CACHE', ''),
    os.path.join(os.environ.get('HF_HOME', ''), 'hub') if os.environ.get('HF_HOME') else '',
    'D:/software/ai-models/huggingface/hub',          # 数据盘（agent-env-policy 纪律）
    'C:/Users/ysq/.cache/huggingface/hub',            # 用户默认缓存
]


def find_model_snapshot(explicit: str = '') -> str:
    """按优先级定位本地 faster-whisper-small 快照路径；找不到返回 ''。"""
    if explicit:
        if Path(explicit, 'model.bin').exists():
            return explicit
        print(f'[错误] --model 指定路径无效（缺 model.bin）: {explicit}', file=sys.stderr)
        sys.exit(2)

    for root in CANDIDATE_ROOTS:
        if not root:
            continue
        snap_dir = Path(root) / MODEL_REPO / 'snapshots'
        if not snap_dir.is_dir():
            continue
        for snap in sorted(snap_dir.iterdir()):
            # 快照目录必须含有效 model.bin（>100MB，排除 0 字节占位/半截文件）
            mb = snap / 'model.bin'
            if mb.exists() and mb.stat().st_size > 100 * 1024 * 1024:
                return str(snap)
    return ''


def fmt_ts(seconds: float) -> str:
    """秒 -> SRT 时间戳 00:00:00,000"""
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f'{h:02d}:{m:02d}:{s:02d},{ms:03d}'


def transcribe_one(model, media: Path, out_srt: Path, language, beam: int) -> dict:
    """转写单个文件，返回结果摘要。"""
    t0 = time.time()
    try:
        segments, info = model.transcribe(
            str(media), language=language, vad_filter=True, beam_size=beam)
        rows = []
        for i, seg in enumerate(segments, 1):
            rows.append(f'{i}\n{fmt_ts(seg.start)} --> {fmt_ts(seg.end)}\n{seg.text.strip()}\n')
        if not rows:
            return {'file': str(media), 'ok': False, 'reason': '转写结果为空（静音或损坏）'}
        out_srt.parent.mkdir(parents=True, exist_ok=True)
        out_srt.write_text('\n'.join(rows), encoding='utf-8')
        size = out_srt.stat().st_size
        if size == 0:
            return {'file': str(media), 'ok': False, 'reason': '输出 0 字节'}
        return {'file': str(media), 'ok': True, 'srt': str(out_srt), 'size': size,
                'lang': info.language, 'dur': round(info.duration, 1),
                'secs': round(time.time() - t0, 1)}
    except Exception as e:
        return {'file': str(media), 'ok': False, 'reason': f'{type(e).__name__}: {e}'[:300]}


def main():
    ap = argparse.ArgumentParser(description='Faster-Whisper 本地转写（离线）')
    ap.add_argument('input', help='媒体文件或目录')
    ap.add_argument('-o', '--outdir', help='SRT 输出目录（默认与源文件同目录）')
    ap.add_argument('--language', default='None',
                    help="语言代码 zh/en 或 None（自动检测），默认 None")
    ap.add_argument('--model', default='', help='模型快照路径（含 model.bin 的目录）')
    ap.add_argument('--cpu-threads', type=int, default=8)
    ap.add_argument('--beam', type=int, default=5)
    ap.add_argument('--force', action='store_true', help='覆盖已存在的 SRT')
    ap.add_argument('--json', dest='json_out', help='结果摘要 JSON 输出路径')
    args = ap.parse_args()

    src = Path(args.input)
    if src.is_file():
        media_files = [src]
    elif src.is_dir():
        media_files = sorted(p for p in src.rglob('*') if p.suffix.lower() in MEDIA_EXTS)
    else:
        print(f'[错误] 输入不存在: {src}', file=sys.stderr)
        sys.exit(2)
    if not media_files:
        print('[提示] 未找到可转写的媒体文件')
        sys.exit(0)

    snap = find_model_snapshot(args.model)
    if not snap:
        print('[错误] 未找到本地 faster-whisper-small 模型快照。'
              '请先运行 tools_download_model.py 下载，或用 --model 指定快照路径。'
              '（本脚本刻意不自动联网下载）', file=sys.stderr)
        sys.exit(3)
    print(f'[模型] {snap}')

    # 离线双保险：强制走本地
    os.environ.setdefault('HF_HUB_OFFLINE', '1')
    os.environ.setdefault('TRANSFORMERS_OFFLINE', '1')

    from faster_whisper import WhisperModel  # 延迟导入，模型找不到时先报错
    model = WhisperModel(snap, device='cpu', compute_type='int8',
                         cpu_threads=args.cpu_threads)
    language = None if args.language.lower() == 'none' else args.language

    outdir = Path(args.outdir) if args.outdir else None
    results, ok_n = [], 0
    for i, mf in enumerate(media_files, 1):
        srt_out = (outdir / (mf.stem + '.srt')) if outdir else mf.with_suffix('.srt')
        if srt_out.exists() and srt_out.stat().st_size > 0 and not args.force:
            print(f'[{i}/{len(media_files)}] 跳过（已存在）: {mf.name}')
            results.append({'file': str(mf), 'ok': True, 'skipped': True,
                            'srt': str(srt_out)})
            ok_n += 1
            continue
        print(f'[{i}/{len(media_files)}] 转写: {mf.name} ...', flush=True)
        r = transcribe_one(model, mf, srt_out, language, args.beam)
        results.append(r)
        if r['ok']:
            ok_n += 1
            print(f'    -> OK  {r["dur"]}s 音频耗时 {r["secs"]}s  -> {r["srt"]}')
        else:
            print(f'    -> 失败: {r["reason"]}', file=sys.stderr)

    print(f'\n===== 汇总 ===== 成功 {ok_n}/{len(media_files)}')
    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps({'model': snap, 'results': results}, ensure_ascii=False, indent=2),
            encoding='utf-8')
        print(f'JSON 已写入: {args.json_out}')
    sys.exit(0 if ok_n == len(media_files) else 1)


if __name__ == '__main__':
    main()
