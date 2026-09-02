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

> 💡 **飞书导入最新、最完整的方案已拆为独立 skill `飞书知识库MD导入`**（9/2 新增，原生 Markdown 导入，
> 已 120 篇 / 2870 图实战验证：直接 `docs +create --doc-format markdown` + `@./images/` 语法，
> 不需要 pandoc/docx、不踩下面的 HTML img 坑）。**新项目优先用那个 skill。**
> 本步骤保留基于 `pandoc+docx` 的历史方案，供兼容与离线参考。

> ⚠️ **导入前必须先做图片嵌入（步骤 4.1），否则全部图片会裂图。**

#### 4.1 图片嵌入（强制，不可跳过）

飞书 docx 导入**不支持 webp，也不会抓取远程外链图**。本地 md 里的 `![](https://pic.code-nav.cn/...)` 直接导入必然裂图
（飞书显示“无法导入该图片，请从原文档中保存原图后重新上传”）。必须先转成内嵌 PNG 的 docx：

```bash
# 对本目录所有 md 逐个生成同名 docx（远程图下载→webp 转 PNG→pandoc 嵌入）
python D:/Desktop/temp/.workbuddy/cdp-scraper/embed_images.py "D:/Desktop/temp/课程/子目录/xxx.md"
```

`embed_images.py` 做的事：下载远程图到 `images/`（URL 哈希命名，全局去重）→ 用 Pillow 把 webp 转 PNG →
md 链接改写为本地相对路径 → `pandoc xxx.md -o xxx.docx`（图字节真正写进 `word/media/`）。

> ⚠️ **致命坑（已实战踩过，务必记住）**：pandoc 默认把 Markdown 里的 HTML `<img src="...">` 当 **raw HTML 丢弃**，
> 不会嵌入成图片。若 md 图片是 `<img src="images/x.png" ...>` 形式（codefather 抓下来的绝大部分图片就是这个形式），
> 直接 `pandoc xxx.md -o xxx.docx` 会生成**内嵌 0 张图**的 docx，飞书端整篇裂图。
> **必须在 pandoc 前把 `<img src="x">` 转成行内式 `![](x)`**（`embed_images.py` 内部已做这步；
> 若自己调 pandoc，先过 `scripts/embed_images.py` 里的 `html_img_to_md()`，或加 `-f markdown+raw_html` 但仍不会内嵌本地图字节）。
> 验证方法就是步骤 4.1 末尾的 `zipfile` 计数，必须等于图片数，**为 0 立刻停手重来**。

**校验内嵌是否成功**：
```bash
python -c "import zipfile; z=zipfile.ZipFile('xxx.docx'); print(len([n for n in z.namelist() if n.startswith('word/media/')]))"
```
输出应等于该文档的图片数，为 0 则说明没嵌进去。

#### 4.2 导入（增量模式，幂等可续跑）

先按 references/workflow.md 第 6.1 节用 `lark-cli wiki +node-list` 找到目标父节点 token，再：

```bash
python D:/Desktop/temp/.workbuddy/cdp-scraper/reimport_all.py --run
```

（脚本内 `COURSES` 列表维护「课程标题 + 本地路径」的映射，按需修改。）

**增量模式**逻辑：找现有课程节点（无则建）→ 找/建子目录节点 → 列出已有文档标题 → **只导入缺失的**。
重复跑只会补漏，不会重复创建，可放心断点续跑。

导入后校验：
```bash
python D:/Desktop/temp/.workbuddy/cdp-scraper/verify.py
# 看 verify_out.txt：缺失总数应为 0
```

#### 4.3 md 图片本地化内嵌（可选，反向操作）

> ⚠️ 与「关键机制」里"保持原 md 为 http 外链"的默认约定**相反**。仅当用户明确要求"图片全部内嵌到 md 文档"时执行。

`scripts/embed_md.py`：把正式 md（``` 围栏外的）远程图与 HTML `<img>` 一并改写为本地 `images/<md5(url)>.<ext>` 引用，
图片落盘到各文档同目录的 `images/`（webp 转 PNG），md 不再依赖网络。用法：

```bash
python scripts/embed_md.py              # dry-run，只统计待内嵌
python scripts/embed_md.py --apply      # 实际改写（自动备份原文件）
```

- 同时覆盖**行内式** `![](http...)` 与 **HTML `<img src="http...">`** 两种形式（后者是早期脚本唯一漏掉的形式，
  之前统计「正式 md 2917 处」与行内式 1728 处的口径差，正是这 913 处 HTML img）。
- ``` 围栏内的 `picture?.url`、`<img>` 等教程示例代码**不处理**。
- 改完后用 `verify_embed.py` 校验：本地引用文件必须全部存在、残留远程应为 0（提示词模板里的 picsum 示例除外）。

全量导入 5 门课（本地图已内嵌、直接 pandoc 生成 docx 再上传）用 `scripts/import_all5.py`：
它复用 `reimport_all.py` 的节点操作，但 pandoc 通过 **stdin 传内容 + `--resource-path`**，
不产生临时 md 文件（避免触发安全删除阈值中断），且内置 HTML img → 行内式回退。

```bash
python scripts/import_all5.py           # 后台运行；进度写 ri5_progress.log
```

> 注：若飞书侧要的是"不依赖本地目录"的独立文档，走 `飞书知识库MD导入` skill 的原生 markdown 方案更干净。

### 5.（可选）本地 md 图片链接体检与修复

抓取后、或任何时候怀疑图片失效，跑一次体检：

```bash
python scripts/check_images.py --base "D:/Desktop/temp"          # 只体检出报告
python scripts/check_images.py --base "D:/Desktop/temp" --apply   # 体检 + 修复本地路径污染
python scripts/check_images.py --base "D:/Desktop/temp" --no-probe # 跳过网络探测
```

脚本把图片引用分成三类并分别处理：

| 类别 | 判定 | 处理 |
|---|---|---|
| http(s) 外链 | 不在 ``` 围栏内 | 并发 HEAD 探测（403/405/501 自动回退 GET），统计有效性 |
| 本地相对路径 | `images/<32位hash>.<ext>` | **反查还原**：文件名就是 `md5(url)`，用「URL 池」反查回原始外链（`--apply` 写盘，自动备份） |
| 代码块示例 | ``` 围栏内 | 不处理（`picture?.url`、`../assets/logo.png` 等是教程源码，不是真实引用） |

**URL 池来源**（决定还原命中率）：md 中残留的 http 图片链接 + 同目录 `*.json` 抓取产物里的链接。
实测 5 门课程 1755 处污染链接 **100% 还原成功，hash 零冲突**，抽样 15 张比对像素尺寸 15/15 一致。

**⚠️ 不要就地改写原 md 的图片链接。** 早期版本脚本把原 md 的 http 外链改成了 `images/xxx.png`，
导致 md 本地打开全是裂图。正确做法是只改写副本（`__tmp__.md`）再交给 pandoc，原 md 始终保持 http 外链。
万一已经污染，用上面的 `--apply` 反查还原即可。

## 关键机制（务必理解）

- **绕过反爬靠监听 API，不是改 DOM**：站点检测到 DevTools 会跳 `about:blank`，但 section 页加载时发出的
  `api.codefather.cn/api/course_article/get/vo/safe` XHR 仍可被 `page.on('response')` 捕获，直接取 `data.content`（完整 Markdown）。
- **section URL 用 `courseArticleId`**，不是 `catalog.id`（后者 article API 返回 404）。
- **目录名含 `|` 是 Windows 非法字符**，脚本已自动替换为全角 `｜`。
- **分类函数 `classifyFolder()` 可按需修改**以适配不同课程结构；误分类项抓取后 `mv` 修正即可。
- **playwright-core 连不上新版 Chrome**（Chrome 151 实测 `connectOverCDP` 握手超时 30s）。
  需要 CDP 时改用 Python `websocket-client` 直连：`http://127.0.0.1:9222/json/new?<url>`（PUT 开新标签）
  → 连返回的 `webSocketDebuggerUrl` → `Network.enable` + 监听 `Network.responseReceived` →
  `Network.getResponseBody` 取 API 响应。参考 `scripts/cdp_fetch.py`。
- **探测图片有效性必须回退 GET**：`picsum.photos` 之类图床对 HEAD 返回 405，只看 HEAD 会误判为失效。
- **源站本身也可能有死链**：语雀迁移遗留的 `doc/xxx.png#id=...` 相对路径，源站页面同样渲染不出，
  这类无法还原，只能删除并补说明文字（先看页面 DOM 里有没有真实 src 可捞）。
- **pandoc 把 HTML `<img>` 当 raw HTML 丢弃**：见步骤 4.1 致命坑。这是 120 篇导入踩的最隐蔽的雷——
  导入时 log 显示 `OK`、飞书也能打开文档，但**所有图片 0 张**，肉眼几乎发现不了，必须靠 `zipfile` 数 `word/media/` 兜底。
- **md 本地化内嵌 vs 保持外链是两种相反选择**：默认（爬取→飞书）保持 http 外链、导入时才转内嵌 docx；
  当用户要求"md 图片全部内嵌"时反向操作（`embed_md.py`）。两者不要混用——已内嵌本地图的 md 再跑 `embed_images.py` 会因找不到 http URL 而不生成图。
- **生成 docx 不要落临时 md 文件**：脚本里 `open(tmp_md,'w')` 再 `os.remove` 的模式，在批量（≥50 篇）时
  会触发安全删除批量确认阈值导致进程被杀。改为 pandoc 走 **stdin**（`input=text` + `--resource-path=.` + `cwd=md目录`），
  相对图片路径照常解析，且零落盘。见 `import_all5.py`。

## 参考文件

- `references/workflow.md`：Chrome 启动命令、反爬原理、section URL、清洗规则、飞书导入分步细节、
  **lark-cli API 关键坑与增量导入模式**（第 6.5/6.6 节，导入前必看）、故障表。
- `scripts/find-chrome.js`：首次使用从默认地址定位 Chrome.exe（找不到则 `NOT_FOUND`，由调用方询问用户并 `--set` 写入配置）。
- `scripts/fetch-course.js`：参数化主抓取脚本（`--course-id/--target-dir/--exclude/--chrome-port`）。
- `scripts/catalog-tree.js`：仅拉取并打印目录树（不抓内容，用于预览/确认）。
- `scripts/embed_images.py`：远程图下载 → webp 转 PNG → pandoc 生成内嵌图 docx（**导入飞书前必跑**）。
- `scripts/embed_md.py`：把 md 图片本地化内嵌（行内式 + HTML img 两种形式 → `images/<md5>.<ext>`）。
- `scripts/import_all5.py`：5 门课全量导入飞书（pandoc 走 stdin，内置 HTML img→行内式回退，零临时文件）。
- `scripts/reimport_all.py`：增量导入飞书（幂等，只补缺失文档）。改 `COURSES` 列表后 `python reimport_all.py --run`，**后台运行**。
- `scripts/verify.py`：对比本地 md 与飞书文档，输出缺失清单（正常应为 0）。
- `scripts/verify_embed.py`：校验 md 本地化内嵌结果（本地引用文件存在、残留远程应为 0）。
- `scripts/check_images.py`：本地 md 图片链接体检 + 本地路径污染反查还原（参数 `--base/--apply/--no-probe`）。
- `scripts/cdp_fetch.py`：Python 直连 CDP 抓文章（playwright 连不上新版 Chrome 时的替代方案）。
- `scripts/import-feishu.sh`：早期一次性导入脚本（已过时，保留参考；新场景优先用 `reimport_all.py`）。
