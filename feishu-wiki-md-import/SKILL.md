---
name: feishu-wiki-md-import
description: 用 lark-cli 把本地 Markdown 项目（含图片/SVG/表格）批量导入飞书知识库并做三重保真校验的完整工作流。当用户要求"把 md/文档导入飞书知识库/wiki"、"按目录结构导入飞书"、"迁移文档到飞书"时使用。
---

# 飞书知识库 Markdown 批量导入工作流 (feishu-wiki-md-import)

2026-09-02 实战验证 ×2：① 编程导航 120 篇 md / 2870 张图（1.4GB）/ 5 项目 / 42 子目录（固定两层）；② easy-vibe 195 篇纯 md / 29 目录节点（**任意深度 2~4 层**，根级与目录级混排 md）。结构、图片、文字三重校验全通过。

## 两种目录结构 → 两套脚本

| 形态 | 脚本 | 要点 |
| --- | --- | --- |
| 固定「项目/子目录」两层（md 都在第二层） | `build_tree.py` / `import_docs.py` / `verify.py` | 上一代，两两配对 |
| **任意深度目录树**（根级有 md、目录级也混排 md/子目录） | `build_tree_rec.py` / `import_docs_rec.py` / `verify_rec.py` + `ev_common.py`（公共层） | md 一律挂**直接父目录节点**；目录节点与文档节点可混挂同一父下；**建树按深度升序稳定排序**（父先子后，防 KeyError）；无「(程序员鱼皮)」后缀时标题=去 .md；`fix_indent_drop.py` 修复列表内嵌块后的缩进续文丢字 |

配置：`ev_common.py` 常量走环境变量 `LARK_MD_SRC` / `LARK_SPACE_ID` / `LARK_ROOT_TITLE`（默认 easy-vibe 值）。

## 前置

- 环境：Windows + Git Bash。lark-cli 不能直接解析，必须直调：
  `node "C:\Users\ysq\.workbuddy\binaries\node\cli-connector-packages\node_modules\@larksuite\cli\scripts\run.js"`
- 环境变量前缀（每次新 Bash 会话必带）：
  `export NODE_OPTIONS='--require="D:/software/WorkBuddy/resources/app.asar.unpacked/cli/vendor/shim/genie-safe-delete.cjs"'` + `unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy`
- 定位目标：`wiki +space-list` → `wiki +node-list --space-id <id>` 找父节点 token。
- **换机器 / 换项目**：所有脚本常量集中在 `scripts/lark_env.py`，支持环境变量覆盖（`LARK_MD_BASE` / `LARK_ENTRY` / `LARK_SPACE_ID` / `LARK_WIKI_PARENT` / `LARK_CHROME` 等），不必逐个改脚本。

## 核心流程（5 步）

1. **预处理 md**（`lark_md_prep.py`）：
   - HTML `<img src=...>` → `![alt](@./images/xxx.png)`（飞书只认 `@./` 本地图语法）
   - **剥掉 `<font>/<span>` 标签壳保留内文**——放白名单原样传会被飞书连内文一起静默丢弃（丢字 17%+ 实测）
   - **整篇嵌在有序列表里的 md（`1.` 空项 + 正文缩进 3 空格）必须拍平去缩进**——缩进块里的普通段落会被飞书丢弃（标题/列表/图片保留）
   - **列表项内嵌表格/代码块后、同缩进续接的正文行也会被丢**（如 `2.` 表格后补一句、代码块后 `**关键一步**` 段）——用 `fix_indent_drop.py` 把这些「块结束（表格行/代码围栏）后紧跟的缩进普通行」去缩进抬级。注意列表内嵌代码围栏常有 3~5 空格缩进，判定正则不能限定 `\s{0,3}`
   - 其他裸 `<tag>` 转义为 `\<tag>`（代码块内不动）
2. **SVG**：飞书不支持。唯一可用方案：本地 Chrome `--remote-debugging-port` + playwright `connectOverCDP` 截图成 PNG（`svg2png_cdp.py`）。cairosvg/svglib/PyMuPDF/resvg-py 渲染 Mermaid 全都丢文字或崩溃；`chromium.launch()` 在沙箱下因 `--remote-debugging-pipe` 握手失败不可用。
3. **建目录骨架**（`build_tree.py`）：`wiki +node-create --parent-token <父>` 逐级建项目/目录节点（docx 类型），节点 token 写入 `state.json`。
4. **并发导入**（`import_docs.py`，2 worker，断点续传）：
   - `docs +create --doc-format markdown --content - --parent-token <目录>`，stdin 传内容，**cwd 必须设为 md 所在目录**（`@./` 图片按 cwd 解析）
   - 大段内容必须走 stdin（argv 超 ~8K 字符触发 WinError 206）
5. **失败修复**（`rebuild_safe.py`，最可靠方案）：删旧节点 → `docs +create` 纯文本文档 → `docs +update --command append --content -`（stdin）逐段追加 ≤1800 字符片段，图片位置用 `docs +media-insert --file <相对路径>` 逐张插（**--file 不吃 `@./` 前缀**）。图片与正文严格按原顺序交错。

## 脚本一览（scripts/）

| 脚本 | 用途 |
| --- | --- |
| `lark_env.py` | **中央配置**：BASE / lark-cli 入口 / SPACE / 父节点 token / Chrome 路径，全部支持环境变量覆盖 |
| `lark_md_prep.py` | md 预处理（纯文本转换，无机器依赖）：img 转换、样式标签剥离、去列表缩进、尖括号转义 |
| `svg2png_cdp.py` | SVG→PNG（Chrome CDP 截图，`python svg2png_cdp.py in.svg out.png [port]`） |
| `build_tree.py` | 步骤 1：建项目 + 目录节点骨架 → state.json |
| `import_docs.py` | 步骤 2：并发导入全部 md，断点续传（env `LIMIT=n` 可小批量试跑） |
| `rebuild_safe.py` | 步骤 3：单篇修复（删旧重建 + 分片追加），env `ONLY=<关键字>`/`SKIP=`/`LIMIT=` 过滤 |
| `verify.py` | 校验 1：结构比对（同时被 rebuild/audit/cleanup 引用，提供 run/children 工具函数） |
| `audit_images.py` | 校验 2：逐篇比对本地 vs 飞书图片数 |
| `audit_final_text.py` | 校验 3：difflib 逐段文字审计（归一化去伪影） |
| `cleanup_duplicates.py` | 修复后按标题去重重复节点 |
| `cleanup_stale_trees.py` | 清理早期尝试残留的旧树（默认 `DRY_RUN=True`，确认后才放开删除） |

## 关键坑速查

| 坑 | 处理 |
| --- | --- |
| `correlation_failed` 返回 ok:false 但文档已建 | 重试会产生重复节点；按父节点+标题去重（`cleanup_duplicates.py`），或走修复方案 |
| `wiki +node-delete` | 必须显式 `--obj-type wiki`，否则删不掉 |
| wiki 两套 token | 文档比对用 `obj_token`（=document_id），目录用 `node_token`，混用误报 |
| 回读字符数"膨胀" | 伪影：`@./images/x` 短链变 ~200 字符 authcode 长链（每图 +170 字符） |
| 回读"丢失"片段 | 先剔伪影再定性：全 `[-|]` = 表格分隔行；`%hex` = URL 编码；`<br/>`→`\n` = mermaid 图内换行（语义等价）；`[标题](<相对.md>)` = 站内链接被渲染纯文本（链接文字逐条验证在位即可）；去掉后能在回读中找到 = 错位对齐 |
| lark-cli 输出尾部混 stderr | 用 `json.JSONDecoder().raw_decode(blob[blob.find('{'):])` 取首个 JSON |
| Windows 下调 python 触发 mise 自动安装挂起 | 用完整路径直调内置解释器（如 `C:\Users\ysq\.workbuddy\binaries\python\versions\3.13.12\python.exe`） |

## 校验（三重，缺一不可）

1. **结构**（`verify.py`）：`wiki +node-list` 递归 vs 本地目录树。⚠️ 必须做**双向清点**：正向（登记节点都存在）+ 反向（父节点下无 state 外多余节点）——只做正向会漏掉早期尝试留下的重复旧树。
2. **图片**（`audit_images.py`）：`docs +fetch --doc-format markdown` 数 `![`。代码块里的 `![..](http://..)` 教学字符会多算远程，属正常。
3. **文字**（`audit_final_text.py`）：difflib 逐段比对（归一化 = 去图片/去转义反斜杠/去空白），delete 段剔伪影后仍有剩余才算真丢。

## 复用方式（适配新项目）

1. `pip install playwright` 且本机有 Chrome（SVG 转图需要；纯文字项目可跳过）
2. 设环境变量或改 `lark_env.py` 默认值：`LARK_MD_BASE`（本地 md 根目录）、`LARK_SPACE_ID`（目标空间）、`LARK_WIKI_PARENT`（目标父节点 token）
3. 清空/删除 `state.json`（本仓库不含，首次运行自动生成）；`build_tree.py` / `import_docs.py` 里的 `SEED`/`SEED_DOCS` 置空 `{}`
4. 按流程跑：`build_tree.py` → `import_docs.py` → 三重校验 → 必要时 `rebuild_safe.py` + 两个 cleanup
