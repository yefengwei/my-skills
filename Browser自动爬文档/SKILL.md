---
name: Browser自动爬文档
description: 批量抓取 codefather.cn（程序员鱼皮）等 Next.js 课程站点的整课文档为本地 Markdown，并可选导入飞书知识库。复用本机已登录的 Chrome 会话（CDP 远程调试），通过监听内部 article API 绕过反爬，按目录结构自动归类、清洗水印与零宽字符，图片保留在线链接。当用户要求“抓取/爬取某课程文档”“把 codefather 课程下载到本地/某文件夹”“导入飞书知识库按目录排列”时使用。
agent_created: true
---

# Browser 自动爬文档

把 codefather.cn 等课程站点的整课文档批量抓成本地 Markdown，并可选导入飞书知识库（严格还原目录结构）。
核心难点——登录态、反爬、内容完整性——已用「**复用已登录 Chrome 会话 + 监听内部 article API**」方案彻底解决，
比解析 DOM 更稳、更完整（DOM/RSC 方式会截断内容）。

## 何时使用

- 用户给出 codefather.cn 课程链接（形如 `https://www.codefather.cn/course/<ID>`），要求抓取文档到本地某文件夹。
- 要求“按规则/原样排列”“排除已废弃章节”。
- 要求把已抓好的本地 md 导入飞书知识库某目录下。

## 前置条件

- 本机已安装 Chrome（标准版或便携版如 Chrome++），且用户已用它登录 codefather.cn。
- Node + `playwright-core` 已安装。
- （飞书导入时）已连接飞书，`lark-cli` 可用。

> 首次使用会自动定位 Chrome.exe（见步骤 1）；定位不到才询问用户，并把结果记到 `scripts/.chrome-config.json` 供后续复用。

## 工作流程

### 1. 定位 Chrome 并启动 / 复用调试会话

**先确认调试端口是否已开**：`curl http://127.0.0.1:9222/json/version` 有返回即直接用，跳到步骤 2。

否则需要（重）启动 Chrome 并开启远程调试，先定位 Chrome.exe：

```bash
node scripts/find-chrome.js
```

- 输出 JSON `{ "chrome": "...", "userDataDir": "..." }` → 记下路径，按 references/workflow.md 第 1 节用它启动 Chrome。
- 输出 `NOT_FOUND` → **用 AskUserQuestion 询问用户 Chrome.exe 的完整路径**（以及若非标准安装、对应的用户数据目录）；
  拿到后执行 `node scripts/find-chrome.js --set "<用户给的路径>" [--user-data-dir "<数据目录>"]` 写入配置，后续不再询问。
- 配置文件 `scripts/.chrome-config.json` 已存在且有效时会直接复用，不重复询问、不重复查找。

**该启动步骤只需做一次**，之后多次抓取可复用同一 9222 端口，无需重启。

### 2. 预览目录树（先确认结构与排除项）

```bash
node scripts/catalog-tree.js --course-id <课程ID>
```

确认课程 ID、目录层级、子章节数，以及要排除的章节名（常见 `已废弃` / `♻️ 已废弃`），作为下一步 `--exclude`。

### 3. 执行抓取

```bash
node scripts/fetch-course.js \
  --course-id <课程ID> \
  --target-dir "D:/Desktop/temp/目标文件夹" \
  --exclude "已废弃"
```

脚本会自动：读 cookie → 拉目录树 → 监听每篇 article API 取原始 Markdown → 按 `classifyFolder()` 归类到子目录 →
清洗零宽字符/水印/base64 内嵌图 → 落盘 `标题(程序员鱼皮).md`（图片保留在线链接）。排除章节及其全部子项不抓。

### 4.（可选）导入飞书知识库

先按 references/workflow.md 第 6.1 节用 `lark-cli wiki +node-list` 找到目标父节点 token，再：

```bash
bash scripts/import-feishu.sh \
  --base-dir "D:/Desktop/temp/目标文件夹" \
  --space-id <知识空间ID> \
  --parent-token <父节点token> \
  --course-title "课程名"   # 可选，默认取文件夹名
```

脚本自动建「课程节点 + 各子目录节点」，逐个 `drive +import --type docx` 再 `wiki +move` 移入，严格还原本地结构。

## 关键机制（务必理解）

- **绕过反爬靠监听 API，不是改 DOM**：站点检测到 DevTools 会跳 `about:blank`，但 section 页加载时发出的
  `api.codefather.cn/api/course_article/get/vo/safe` XHR 仍可被 `page.on('response')` 捕获，直接取 `data.content`（完整 Markdown）。
- **section URL 用 `courseArticleId`**，不是 `catalog.id`（后者 article API 返回 404）。
- **目录名含 `|` 是 Windows 非法字符**，脚本已自动替换为全角 `｜`。
- **分类函数 `classifyFolder()` 可按需修改**以适配不同课程结构；误分类项抓取后 `mv` 修正即可。

## 参考文件

- `references/workflow.md`：Chrome 启动命令、反爬原理、section URL、清洗规则、飞书导入分步细节、故障表。
- `scripts/find-chrome.js`：首次使用从默认地址定位 Chrome.exe（找不到则 `NOT_FOUND`，由调用方询问用户并 `--set` 写入配置）。
- `scripts/fetch-course.js`：参数化主抓取脚本（`--course-id/--target-dir/--exclude/--chrome-port`）。
- `scripts/catalog-tree.js`：仅拉取并打印目录树（不抓内容，用于预览/确认）。
- `scripts/import-feishu.sh`：本地 md 自动导入飞书知识库（自动建节点 + 逐个移动）。
