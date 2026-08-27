#!/usr/bin/env bash
# import-feishu.sh — 把本地课程目录（含子目录的 .md）自动导入飞书知识库，
# 自动在目标父节点下创建「课程节点 + 各子目录节点」，再逐个 md→docx→移入，严格还原本地结构。
#
# 用法：
#   bash import-feishu.sh --base-dir "D:/Desktop/temp/我的课程" \
#                         --space-id 7493948997678137346 \
#                         --parent-token <父节点token> \
#                         [--course-title "课程名"]   # 默认取 base-dir 目录名
#
# 前置：已连接飞书（lark-cli 可用、--as user 身份），且对目标知识空间有写权限。
unset NODE_OPTIONS

BASE_DIR=""; SPACE_ID=""; PARENT_TOKEN=""; COURSE_TITLE=""
while [ $# -gt 0 ]; do
  case "$1" in
    --base-dir) BASE_DIR="$2"; shift 2;;
    --space-id) SPACE_ID="$2"; shift 2;;
    --parent-token) PARENT_TOKEN="$2"; shift 2;;
    --course-title) COURSE_TITLE="$2"; shift 2;;
    *) shift;;
  esac
done

if [ -z "$BASE_DIR" ] || [ -z "$SPACE_ID" ] || [ -z "$PARENT_TOKEN" ]; then
  echo "用法: bash import-feishu.sh --base-dir <DIR> --space-id <SPACE> --parent-token <PARENT> [--course-title <TITLE>]"
  exit 1
fi
[ -z "$COURSE_TITLE" ] && COURSE_TITLE="$(basename "$BASE_DIR")"

# 解析 lark-cli 输出中 data.<field> 字段（stdout 可能带前缀文本，需截断到首个 {）
get_field() {
  python -c "
import sys, json
raw = sys.stdin.read()
s = raw.find('{')
if s < 0:
    print('')
else:
    try:
        d = json.loads(raw[s:]).get('data') or {}
        print(d.get('$1', '') or '')
    except Exception:
        print('')
"
}

# 创建课程节点
COURSE_TOKEN=$(lark-cli wiki +node-create --parent-node-token "$PARENT_TOKEN" --title "$COURSE_TITLE" --as user --format json 2>&1 | get_field node_token)
if [ -z "$COURSE_TOKEN" ]; then
  echo "FAIL: 创建课程节点失败 ($COURSE_TITLE)"; exit 1
fi
echo "✓ 课程节点: $COURSE_TITLE -> $COURSE_TOKEN"

OK=0; FAIL=0
# 遍历每个子目录
for sub in "$BASE_DIR"/*/; do
  [ -d "$sub" ] || continue
  sub_name=$(basename "$sub")
  SUB_TOKEN=$(lark-cli wiki +node-create --parent-node-token "$COURSE_TOKEN" --title "$sub_name" --as user --format json 2>&1 | get_field node_token)
  if [ -z "$SUB_TOKEN" ]; then
    echo "FAIL: 创建子目录节点失败 ($sub_name)"; FAIL=$((FAIL+1)); continue
  fi
  echo "  ✓ 子目录: $sub_name -> $SUB_TOKEN"
  # 逐个导入 md
  for f in "$sub"*.md; do
    [ -f "$f" ] || continue
    out=$(lark-cli drive +import --file "$f" --type docx --as user --format json 2>&1)
    token=$(echo "$out" | get_field token)
    if [ -z "$token" ]; then
      echo "FAIL(import): $f"; echo "$out" | grep -E 'error|message' | head -2; FAIL=$((FAIL+1)); continue
    fi
    mv_out=$(lark-cli wiki +move --obj-type docx --obj-token "$token" \
      --target-space-id "$SPACE_ID" --target-parent-token "$SUB_TOKEN" --as user --format json 2>&1)
    wiki=$(echo "$mv_out" | get_field wiki_token)
    if [ -z "$wiki" ]; then
      echo "FAIL(move): $f (token=$token)"; echo "$mv_out" | grep -E 'error|message' | head -2; FAIL=$((FAIL+1)); continue
    fi
    echo "  OK: $(basename "$f")"
    OK=$((OK+1))
    sleep 1
  done
done

echo "=================================="
echo "导入完成: 成功 $OK, 失败 $FAIL"
echo "课程节点 token: $COURSE_TOKEN"
