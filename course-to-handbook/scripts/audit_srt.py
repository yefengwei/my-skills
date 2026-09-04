#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
本地字幕损坏审计脚本（course-to-handbook skill 用）
====================================================
扫描目录下所有 .srt 字幕文件，判定每个文件的健康状态：
  - ok       : 内容正常
  - empty    : 0 字节或无有效文本行
  - garbled  : 乱码（不可辨识字符占比过高 / 同一行重复字符刷屏）
  - short    : 有效文本行过少（相对时长可疑，仅提示）

用法:
    python audit_srt.py <字幕目录> [--json 输出.json]

输出: 逐文件状态 + 汇总（总数 / ok / empty / garbled），--json 时写 JSON 供后续流程消费。
仅做只读审计，不修改任何字幕文件。
"""
import argparse
import json
import re
import sys
from pathlib import Path

# ---------- 可辨识字符判定 ----------
# 允许: 中日韩、英文、数字、常见全半角标点、空白、常用符号
_OK_RE = re.compile(
    r'[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af'   # 中/日/韩
    r'a-zA-Z0-9'
    r'\u3000-\u303f\uff00-\uffef'                  # CJK 标点 + 全角符号
    r'\s\.,!?;:\'"()\[\]{}<>/@#%&\*\+=~\-_—–…·“”‘’！？，。：；、]'
)

# 同一字符连刷（如 "哈哈哈哈" 正常，但 "啊啊啊啊啊啊啊啊啊啊啊啊啊啊" 15+ 连刷视为异常）
_REPEAT_RE = re.compile(r'(.)\1{14,}')

# 短语级重复刷屏（真实案例："不经常，没有写出来的写文"整句循环）：
# 同一 8 字以上片段在一行内出现 3+ 次视为异常
def _has_phrase_repeat(line: str) -> bool:
    for n in (12, 10, 8):
        step = len(line) // (n * 3 + 1)
        if step == 0:
            break
        for i in range(0, len(line) - n * 3 + 1, max(step, 1)):
            frag = line[i:i + n]
            if line.count(frag) >= 3:
                return True
    return False

# SRT 时间轴行
_TIME_RE = re.compile(r'\d{1,2}:\d{2}:\d{2}[,.]\d{3}\s*-->\s*\d{1,2}:\d{2}:\d{2}[,.]\d{3}')


def extract_text_lines(srt_path: Path):
    """抽取 SRT 中的有效文本行（去掉序号行与时间轴行）。"""
    try:
        raw = srt_path.read_text(encoding='utf-8', errors='replace')
    except OSError:
        return None  # 读取失败
    lines = []
    for line in raw.splitlines():
        s = line.strip()
        if not s or s.isdigit() or _TIME_RE.search(s):
            continue
        # 去掉 HTML 标签（<i>、<font> 等）
        s = re.sub(r'<[^>]+>', '', s).strip()
        if s:
            lines.append(s)
    return lines


def judge_file(p: Path):
    """判定单个字幕文件状态，返回 (status, detail)。"""
    try:
        size = p.stat().st_size
    except OSError as e:
        return 'unreadable', str(e)

    if size == 0:
        return 'empty', '0 字节'

    lines = extract_text_lines(p)
    if lines is None:
        return 'unreadable', '读取失败'
    if not lines:
        return 'empty', '无有效文本行'

    total_chars = 0
    bad_chars = 0
    repeated_lines = 0
    for ln in lines:
        total_chars += len(ln)
        for ch in ln:
            if not _OK_RE.match(ch):
                bad_chars += 1
        if _REPEAT_RE.search(ln) or _has_phrase_repeat(ln):
            repeated_lines += 1

    if total_chars == 0:
        return 'empty', '有效字符为 0'

    bad_ratio = bad_chars / total_chars
    # 乱码判定：不可辨识字符占比 > 30%，或 30% 以上文本行出现超长重复
    if bad_ratio > 0.30:
        return 'garbled', f'不可辨识字符占比 {bad_ratio:.0%}'
    if repeated_lines >= max(3, int(len(lines) * 0.3)):
        return 'garbled', f'{repeated_lines}/{len(lines)} 行超长重复字符'

    if len(lines) <= 3:
        return 'short', f'仅 {len(lines)} 行有效文本（疑似截断）'
    return 'ok', f'{len(lines)} 行'


def main():
    ap = argparse.ArgumentParser(description='SRT 字幕损坏审计（只读）')
    ap.add_argument('root', help='要扫描的字幕目录（递归）')
    ap.add_argument('--json', dest='json_out', help='审计结果 JSON 输出路径')
    args = ap.parse_args()

    root = Path(args.root)
    if not root.is_dir():
        print(f'[错误] 目录不存在: {root}', file=sys.stderr)
        sys.exit(2)

    results = {}
    counts = {'ok': 0, 'empty': 0, 'garbled': 0, 'short': 0, 'unreadable': 0}
    for p in sorted(root.rglob('*.srt')):
        status, detail = judge_file(p)
        results[str(p)] = {'status': status, 'detail': detail}
        counts[status] += 1
        flag = '' if status == 'ok' else f'  <-- {detail}'
        print(f'[{status:10s}] {p.name}{flag}')

    total = sum(counts.values())
    damaged = total - counts['ok']
    print(f'\n===== 汇总 =====')
    print(f'共 {total} 个字幕: ok={counts["ok"]}  damaged={damaged} '
          f'(empty={counts["empty"]}, garbled={counts["garbled"]}, '
          f'short={counts["short"]}, unreadable={counts["unreadable"]})')

    if args.json_out:
        out = {'root': str(root), 'counts': counts,
               'damaged': {k: v for k, v in results.items() if v['status'] != 'ok'},
               'all': results}
        Path(args.json_out).write_text(json.dumps(out, ensure_ascii=False, indent=2),
                                       encoding='utf-8')
        print(f'JSON 已写入: {args.json_out}')

    # 有损坏时以非零码退出，便于脚本编排判断
    sys.exit(0 if damaged == 0 else 1)


if __name__ == '__main__':
    main()
