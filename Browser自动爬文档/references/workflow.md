# 工作流参考：Browser 自动爬文档

本 skill 用于把 codefather.cn（程序员鱼皮）等 Next.js 课程站点的整课文档批量抓取到本地 Markdown，
并可选导入飞书知识库。核心难点（反爬、登录态、内容还原）已用「CDP 复用会话 + 监听内部 API」方案解决。

---

## 0. 前置条件

- 本机已安装 Chrome++ 便携版（或任意 Chrome），路径例：`D:\Softwares\Daily\Chrome\App\Chrome.exe`
- 用户已在 Chrome 中登录 codefather.cn（cookie 有效）
- Node + playwright-core：`npm i playwright-core`（脚本用 `require('playwright-core')`）

---

## 1. 启动 Chrome 调试模式（复用已登录会话）

Chrome 必须带 `--remote-debugging-port` 启动；直接复用用户已登录的 user-data-dir 即可免登录。

### 1.1 先定位 Chrome.exe（首次使用自动查找，找不到才问）

```bash
node scripts/find-chrome.js
```

- 输出 JSON `{ "chrome": "<exe路径>", "userDataDir": "<数据目录>" }` → 取这两个值用即可。
- 输出 `NOT_FOUND` → **询问用户 Chrome.exe 路径**（必要时连同用户数据目录），再写入配置：
  ```bash
  node scripts/find-chrome.js --set "D:/用户给的/Chrome.exe"          # 自动推导 userDataDir
  node scripts/find-chrome.js --set "D:/x/Chrome.exe" --user-data-dir "D:/x/Data"   # 手动指定
  ```
- 配置文件 `scripts/.chrome-config.json` 存在且有效时直接复用，不重复询问。

### 1.2 启动（用上面得到的路径与数据目录）

```powershell
$CHROME = "D:\Softwares\Daily\Chrome\App\Chrome.exe"   # 来自 find-chrome.js 的 chrome
$UDDIR  = "D:/Softwares/Daily/Chrome/Data"              # 来自 find-chrome.js 的 userDataDir

# 先杀干净已有 Chrome（否则参数不生效）
Get-Process -Name chrome -ErrorAction SilentlyContinue | Stop-Process -Force -Confirm:$false
Start-Sleep -Seconds 2
Start-Process -FilePath $CHROME -ArgumentList `
  '--remote-debugging-port=9222', `
  "--user-data-dir=$UDDIR", `
  '--no-first-run', '--no-default-browser-check', 'about:blank'
Start-Sleep -Seconds 5
# 验证
(Invoke-WebRequest -Uri 'http://127.0.0.1:9222/json/version' -UseBasicParsing).Content
```

验证：`curl http://127.0.0.1:9222/json/version` 有返回即就绪。脚本里用 `chromium.connectOverCDP('http://127.0.0.1:9222')` 连接。

> 注意：子集代理（如 127.0.0.1:7890）偶发连接失败会导致单个文件上传/请求失败，**重试即可**。

---

## 2. 抓取流程（推荐两步）

### 步骤 A：先预览目录树
```bash
node scripts/catalog-tree.js --course-id 1948291549923344386
```
确认：
- 课程 ID 正确、目录层级、子章节数
- 要排除的章节名（如 `已废弃` / `♻️ 已废弃`），作为下一步 `--exclude` 参数
- 输出会保存 `catalog.json` 供排查

### 步骤 B：执行抓取
```bash
node scripts/fetch-course.js \
  --course-id 1948291549923344386 \
  --target-dir "D:/Desktop/temp/我的课程" \
  --exclude "已废弃"
```

落盘规则：
- 按 `classifyFolder()` 关键词归类到子目录（项目介绍/大纲/源码/文字教程/简历写法/面试题/面经/答疑…）
- 文件名格式：`标题(程序员鱼皮).md`（与站内署名一致）
- 图片：**保留在线链接**（`<img src="https://pic.code-nav.cn/...">`），不下载本地
- 外部链接项（catalogType=relatedLink）：保存为指向原地址的占位 md
- 已排除章节及其全部子项不抓

---

## 3. 为什么用「监听 API」而非解析 DOM（关键经验）

codefather.cn 检测到 DevTools 后会执行 `window.close()` / `location.replace('about:blank')`，
直接 DOM 抓取极不稳定。方案改为：

1. 在真实浏览器打开 section 页（带登录 cookie），反爬跳转无所谓；
2. 用 `page.on('response', ...)` 监听 `api.codefather.cn/api/course_article/get/vo/safe` 的 XHR 响应；
3. 直接取 `data.content`（原始 Markdown，含 `<img>` 在线链接），最完整、最稳。

**坑**：曾尝试用 `addInitScript` 注入 stealth 覆盖 `navigator.webdriver`、屏蔽 `window.close` 等，
但 DOM/RSC 提取会**截断内容**导致章节缺失；**监听 article API 才是完整解**。
注意：不能拦截 `history.pushState/replaceState`，否则破坏 Next.js SPA 路由。

---

## 4. section URL 要点

打开页面必须用 `courseArticleId`，不是 `catalog.id`：
```
https://www.codefather.cn/course/{COURSE_ID}/section/{courseArticleId}
```
用 catalog.id 时 article API 返回 404。

---

## 5. 文件清洗（cleanMarkdown）

- 去除零宽字符 / BOM：`[\u200B-\u200D\uFEFF]`（站内水印）
- 去除 base64 内嵌图：`!\[.*?\]\(data:image/...` （避免生成垃圾大文件）
- 文件名/目录名去除 Windows 非法字符 `[\\/:*?"<>|]`，统一替换为 `_`

> 目录名若含 `|`（用户常给「A | B」命名），脚本已自动替换为全角 `｜`（Windows 非法字符）。
> 若分类函数把某项误归到错误目录（如「问题答疑」误归「项目面试题」），抓取后手动 `mv` 修正即可。

---

## 6. 导入飞书知识库（可选）

目标：飞书知识空间 → 某节点（如「计算机科学与技术 / 编程导航」）下，严格还原本地目录结构。

### 6.1 创建知识库节点
```bash
# 在目标父节点下建课程节点
lark-cli wiki +node-create --parent-node-token <PARENT> --title "课程名" --as user --format json
# 在其下建各子目录节点（文字教程/项目介绍/...）
lark-cli wiki +node-create --parent-node-token <课程节点> --title "文字教程" --as user --format json
```
记录每个子目录节点返回的 `node_token`，组成「子目录名 -> token」映射表。

### 6.2 ⚠️ 图片必须提前内嵌（最易踩的坑）

**飞书 docx 导入不支持 webp，也不会抓取远程外链图。** 直接导入含 `![](https://...)` 的 md，
结果就是所有图片显示「无法导入该图片，请从原文档中保存原图后重新上传」。

必须先生成内嵌 PNG 的 docx（见 SKILL.md 步骤 4.1），再走下面的 import。

### 6.3 md → docx → 移入知识库
```bash
# 1) 导入为飞书 docx（落到 Drive 根目录）
lark-cli drive +import --file "标题(程序员鱼皮).docx" --type docx --as user --format json
#    返回 data.token（docx 的 file token）

# 2) 移动到知识库子目录（docs_to_wiki 为移动、不残留于 Drive）
lark-cli wiki +move --obj-type docx --obj-token <token> \
  --target-space-id <SPACE_ID> --target-parent-token <子目录node_token> --as user --format json
#    返回 data.wiki_token 即知识库节点
```

> 批量时建议用 Bash 脚本 + 关联数组存「子目录 -> token」映射，逐个导入并移动（参考示例 import-feishu.sh 思路）。
> 脚本里 `lark-cli` 的 stdout 常带前缀文本，JSON 解析需 `raw.find('{')` 截断再 `json.loads`。

### 6.4 清理
- 验证阶段若手动测试产生重复文档：`lark-cli wiki +node-delete --node-token <token> --obj-type wiki --yes`
- 最终用 `lark-cli wiki +node-list --parent-node-token <课程节点>` 核对每项目录文档数与本地一致、Drive 无残留。

---

## 6.5 lark-cli 飞书 API 关键坑（血泪版）

| 坑 | 正确做法 |
|---|---|
| **删节点用错 obj-type** | node-list 返回的 `obj_type` 字段**不可靠**（课程/子目录/文档全显示 `docx`）。删除节点时一律用 `--obj-type wiki`（节点 token 是 wikcn 形式）。用 docx 会报 `node not found`（code 131005）。 |
| **create 返回结构** | `+node-create` 返回 `data.node_token`，**不是** `data.node.node_token`。取错会静默失败（节点建了但拿不到 token）。 |
| **move 参数名** | 是 `--target-parent-token`，不是 `--target-token`；还需 `--target-space-id`。写错报 `validation/invalid`。 |
| **move 偶发 validation 错误** | 连续快速 import+move 时飞书偶发拒绝（单独重试同一文件必成功）。应对：每篇间隔 ≥1.5s，move 失败重试 4 次、间隔递增。**批量导入时 30%+ 失败率是并发问题，不是文件问题**——别去查文件名。 |
| **subprocess 必须加 timeout** | 个别 lark-cli 调用会挂起，不加 `timeout=` 会拖死整个流程。建议 `timeout=120`。 |
| **前台 Bash 会被杀** | 前台对 ~15+ 次 lark-cli 子进程调用会被杀（输出被吞、exit 1）。批量任务**必须 `run_in_background`**，日志写文件再读。 |
| **判断节点类型** | 用 `has_child` 字段（true=有子节点）比 `obj_type` 可靠。但**不要用它做批量清理**——空子目录的 `has_child` 也是 false，会把子目录当文档删掉。 |

### 6.6 推荐：增量导入而非"先删后建"

**不要**先删光课程节点再重建——中途失败会丢整个结构。
正确做法是幂等的增量模式（见 `reimport_all.py`）：

```
找现有课程节点（无则建）→ 找/建子目录节点 → 列已有文档标题 → 只导入缺失的
```

可随时中断、重复跑只会补漏。导入完用 `verify.py` 对比本地 md 与飞书文档，确认缺失为 0。

---

## 7. 常见故障

| 现象 | 原因 | 解决 |
|---|---|---|
| `connectOverCDP` 失败 | Chrome 未开调试端口 | 按第 1 节重启 Chrome |
| catalog status 401 / 空 | cookie 失效或为空 | 浏览器里重新登录 codefather.cn；脚本已对空 cookie 自动访问站点重建 |
| 单文件请求报代理连接失败 | 本机代理偶发 | 重试该文件 |
| 内容被截断/缺失 | 用了 DOM 解析 | 改用监听 article API（本 skill 已内置） |
| 文件名/目录含乱码 emoji | 站点 catalog API 原始返回即如此 | 按原样保留，非抓取造成 |
| `|` 导致目录创建失败 | Windows 非法字符 | 脚本已自动转全角 `｜` |
