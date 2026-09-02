# -*- coding: utf-8 -*-
"""
把鱼皮项目的 Markdown 预处理成 lark-cli `docs +create --doc-format markdown` 可导入的格式。

处理内容：
1. HTML `<img src=...>` 标签 -> Markdown 本地图片语法 `![alt](@./images/xxx.png)`
2. Markdown 图片 `![alt](images/xxx.png "title")` -> `![alt](@./images/xxx.png)`（保留 alt 作为 caption）
3. 正文（非代码块）中非 HTML 格式化标签的裸尖括号做转义，避免被当作 XML 节点吞掉
4. 其他内容原样保留，便于高保真导入

用法：python lark_md_prep.py <md 文件路径>   （输出到 stdout）
"""
import re
import sys
import os

# 允许保留的 HTML/XML 格式化标签（lark XML 支持或有意义的行内格式）
KEEP_TAGS = {
    'img', 'br', 'hr', 'font', 'b', 'i', 'u', 's', 'em', 'strong', 'del',
    'sub', 'sup', 'code', 'p', 'div', 'span', 'a', 'h1', 'h2', 'h3', 'h4',
    'h5', 'h6', 'ul', 'ol', 'li', 'table', 'thead', 'tbody', 'tr', 'td', 'th',
    'blockquote', 'pre', 'callout', 'todo', 'mention', 'source', 'grid',
    'grid-column', 'itemize',
}

# 代码块围栏：``` 或 ~~~
FENCE_RE = re.compile(r'^\s{0,3}(`{3,}|~{3,})')
# Markdown 图片：![alt](path  "title")
MD_IMG_RE = re.compile(r'!\[([^\]]*)\]\(\s*<?([^)\s]+)>?(?:\s+["\'][^"\']*["\'])?\s*\)')
# HTML img 标签
HTML_IMG_RE = re.compile(r'<img\b[^>]*>', re.I)
HTML_IMG_SRC_RE = re.compile(r'\bsrc\s*=\s*["\']([^"\']+)["\']', re.I)
HTML_IMG_ALT_RE = re.compile(r'\balt\s*=\s*["\']([^"\']*)["\']', re.I)
# 任意标签（用于转义判定）
ANY_TAG_RE = re.compile(r'<(/?)([A-Za-z][A-Za-z0-9:-]*)((?:"[^"]*"|\'[^\']*\'|[^>])*?)(/?)>')

HTTP_RE = re.compile(r'^(https?:)?//', re.I)


def is_fence(line: str) -> bool:
    return bool(FENCE_RE.match(line))


def normalize_img_path(path: str) -> str:
    """把图片路径转成 lark 本地图片语法要求的 @./ 相对路径形式。"""
    p = path.strip()
    # 飞书云文档不支持 SVG 格式，遇到 .svg 自动改用同名的 .svg.png（由 svg2png_cdp.py 提前生成）
    if p.lower().endswith('.svg') and not p.lower().endswith('.svg.png'):
        p = p + '.png'
    # 去掉 URL 编码的空格等
    if HTTP_RE.search(p) or p.startswith('data:'):
        return p
    p = p.lstrip('/')
    if not p.startswith('@'):
        p = '@./' + p
    return p


def convert_html_img(match: re.Match) -> str:
    tag = match.group(0)
    src_m = HTML_IMG_SRC_RE.search(tag)
    if not src_m:
        return ''
    alt_m = HTML_IMG_ALT_RE.search(tag)
    alt = (alt_m.group(1) if alt_m else '').strip()
    # alt 里常见 "null"、空串，忽略
    if alt.lower() in ('null', 'image', 'img'):
        alt = ''
    src = normalize_img_path(src_m.group(1))
    return '![{}]({})'.format(alt, src)


# 纯样式标签：飞书 markdown 解析器会把 <font>/<span> 标签连同内文一起丢弃，
# 必须先剥掉标签壳、保留内文
STRIP_TAG_RE = re.compile(r'<(/?)(font|span)\b(?:"[^"]*"|\'[^\']*\'|[^>])*>', re.I)
# 「整篇嵌在有序列表里」的结构：1. (空) \n 2. > xxx，正文全部缩进
DOC_LIST_HEAD_RE = re.compile(r'^\s*1\.\s*\r?\n(?:\s*\r?\n)*\s*2\.\s')


def strip_style_tags(line: str) -> str:
    """剥掉 font/span 纯样式标签壳，保留内文。"""
    return STRIP_TAG_RE.sub('', line)


def dedent_doc_list(text: str) -> str:
    """处理「整篇嵌在有序列表里」的 md：去掉 1./2. 列表头并整体去缩进。

    飞书解析器会丢弃缩进列表块中的普通段落文本（保留标题/列表/图片），
    因此把这类文档拍平为普通结构。
    """
    if not DOC_LIST_HEAD_RE.match(text):
        return text
    lines = text.split('\n')
    out = []
    state = 0  # 0=找 1. 行  1=找 2. 行  2=正文去缩进
    for ln in lines:
        ln = ln.rstrip('\r')
        if state == 0:
            if re.match(r'^\s*1\.\s*$', ln):
                state = 1
                continue
            out.append(ln)
        elif state == 1:
            m = re.match(r'^(\s*)2\.\s+(.*)$', ln)
            if m:
                state = 2
                indent = len(m.group(1))
                body = m.group(2)
                out.append(body[indent:] if body[:indent] == ' ' * indent else body)
            elif not ln.strip():
                out.append(ln)
            else:
                return text  # 结构不符，原样返回
        else:
            out.append(ln[3:] if ln.startswith('   ') else ln)
    return '\n'.join(out) if state == 2 else text


def escape_stray_tags(line: str) -> str:
    """转义正文中不在白名单里的标签左尖括号。"""

    def repl(m: re.Match) -> str:
        name = m.group(2).lower()
        if name in KEEP_TAGS:
            return m.group(0)
        return '\\<' + m.group(0)[1:]

    return ANY_TAG_RE.sub(repl, line)


def convert_line(line: str) -> str:
    # 先剥掉 font/span 纯样式标签壳（飞书会连内文一起丢）
    line = strip_style_tags(line)
    # 再处理 HTML img
    line = HTML_IMG_RE.sub(convert_html_img, line)
    # 再处理 Markdown 图片（路径可能带 <> 包裹或带 title）
    def md_repl(m: re.Match) -> str:
        alt, path = m.group(1), m.group(2)
        if alt.lower() in ('null',):
            alt = ''
        return '![{}]({})'.format(alt.strip(), normalize_img_path(path))

    line = MD_IMG_RE.sub(md_repl, line)
    # 最后转义裸尖括号标签
    line = escape_stray_tags(line)
    return line


def transform_file(path: str) -> str:
    """读入 Markdown 文件，返回供 lark-cli 导入的转换后内容。"""
    with open(path, encoding='utf-8', errors='replace') as f:
        return transform_text(f.read())


def transform_text(text: str) -> str:
    text = dedent_doc_list(text)
    out_lines = []
    in_fence = False
    fence_marker = ''
    for line in text.split('\n'):
        m = FENCE_RE.match(line)
        if m:
            marker = m.group(1)[0]
            if not in_fence:
                in_fence = True
                fence_marker = marker
            elif marker == fence_marker:
                in_fence = False
                fence_marker = ''
            out_lines.append(line)
            continue
        out_lines.append(line if in_fence else convert_line(line))
    return '\n'.join(out_lines)


def main() -> None:
    if len(sys.argv) < 2:
        print('usage: lark_md_prep.py <file.md>', file=sys.stderr)
        sys.exit(2)
    sys.stdout.write(transform_file(sys.argv[1]))


if __name__ == '__main__':
    main()
