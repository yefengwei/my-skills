---
name: 浏览器自动化测试（Edge+Chrome）
description: 使用用户本机的真实浏览器（绿色版 Chrome 或 Microsoft Edge）进行前端开发调试和自动化测试。当用户提到"用 Chrome 测试"、"用 Edge 测试"、"用我的浏览器"、"指定浏览器"、"前端自动化"、"浏览器跑一遍"、"截图验证"、"打开页面看看"、或带端口号要求连真实浏览器时触发。用户指定哪个浏览器就用哪个（Chrome→9224，Edge→9225），未指定默认 Chrome。基于 agent-browser skill，封装了本机特有的环境变量修复（NODE_OPTIONS 不能含 --use-system-ca；HTTP_PROXY 需 unset）、双浏览器路径选择、手动启动+CDP 连接模式，避免每次重踩坑。
triggers:
  - "用 Chrome 测试"
  - "用 Edge 测试"
  - "用浏览器测试"
  - "用我的浏览器"
  - "绿色版 Chrome"
  - "指定浏览器"
  - "前端自动化测试"
  - "浏览器验证"
  - "浏览器跑一遍"
  - "截图验证"
  - "打开页面看看"
  - "agent-browser"
  - "CDP 连接"
  - "chrome.exe"
  - "msedge.exe"
  - "edge"
---

# 浏览器自动化测试（Chrome/Edge）

用户本机有两个真实浏览器可用于前端自动化测试。**用户指定哪个浏览器就用哪个**（说话时提到 Chrome/Edge/指定浏览器即触发），未指定时默认 Chrome。不使用 agent-browser 自带的 Chrome for Testing。

## 浏览器与端口速查

| 浏览器 | 可执行文件 | 调试端口 | Profile 目录 |
|---|---|---|---|
| **Chrome（绿色版）** | `D:\software\Chrome\App\Chrome.exe` | **9224** | `D:\yefengwei\wkt\.workbuddy\browser-profile` |
| **Edge** | `C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe` | **9225** | `D:\yefengwei\wkt\.workbuddy\edge-profile` |

> 端口约定：9224=Chrome、9225=Edge，互不冲突；不用 9222（易与系统其他实例冲突）。两个浏览器可同时运行、分别连接。

## 首次环境修复（每条 Bash 命令开头都得带）

```bash
# 1. 修复 NODE_OPTIONS：保留 WorkBuddy 的安全 shim，去掉 --use-system-ca
export NODE_OPTIONS='--require="D:/software/WorkBuddy/resources/app.asar.unpacked/cli/vendor/shim/genie-safe-delete.cjs"'

# 2. 清理无效代理（系统变量指向 127.0.0.1:7890 但代理未运行）
unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy
```

> WorkBuddy 启动时注入的 `NODE_OPTIONS` 同时带 `--use-system-ca`，会在 node 启动时直接报错。**不清理 node 一行命令也跑不了。**

## ⚠️ 沙箱必读：所有命令必须 `dangerouslyDisableSandbox=true`

当前 Bash 工具默认沙箱**禁止 127.0.0.1 本机 loopback 连接**。表现为：curl `http://127.0.0.1:9224/...` 与 `agent-browser connect 9224` 被**静默拦截**——命令返回 `Exit Code: 1` 且 **stdout/stderr 全空**（连前面的 echo 都不输出）。纯外网 curl（如 baidu.com）正常，故不是网络问题。

**解决：凡涉及浏览器进程启动、CDP 端口探测、agent-browser 连接/操作的 Bash 命令，调用时务必传入 `dangerouslyDisableSandbox: true`**。禁用沙箱后 loopback 恢复，curl/connect 正常，命令有正常输出。

## 完整工作流

### A. 启动目标浏览器（用 `run_in_background` 持有进程，禁用沙箱）

> **禁止在命令内用 `&` 后台启动 Windows GUI 浏览器**：本环境（Git-Bash/MSYS）在 `&` 启动 `.exe` 时会令整个 shell 崩溃，命令返回 `Exit 1` 且 stdout 全空。必须用 **Bash 工具的 `run_in_background=true`** 来启动浏览器——工具原生持有该进程，命令不会被回收，也不会崩溃。

**做法**：发起两条独立的 Bash 调用（`run_in_background=true` + `dangerouslyDisableSandbox=true`），分别启动 Chrome 与 Edge（各自一条命令，**不要**在同一条消息里并发带前台截图命令）：

```bash
# Chrome（端口 9224）—— 单独一条 run_in_background 调用
export NODE_OPTIONS='--require="D:/software/WorkBuddy/resources/app.asar.unpacked/cli/vendor/shim/genie-safe-delete.cjs"'
unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy
"/d/software/Chrome/App/Chrome.exe" \
  --no-sandbox \
  --user-data-dir="D:/yefengwei/wkt/.workbuddy/browser-profile" \
  --remote-debugging-port=9224 --window-size=1440,900 "https://目标地址.com"
```

```bash
# Edge（端口 9225）—— 另一条 run_in_background 调用，带额外参数
export NODE_OPTIONS='--require="D:/software/WorkBuddy/resources/app.asar.unpacked/cli/vendor/shim/genie-safe-delete.cjs"'
unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy
"/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe" \
  --no-sandbox --no-first-run --no-default-browser-check \
  --user-data-dir="D:/yefengwei/wkt/.workbuddy/edge-profile" \
  --remote-debugging-port=9225 --window-size=1440,900 "https://目标地址.com"
```

> **为什么不用 agent-browser 自动启动**：agent-browser 自动启动用户指定浏览器在本环境会报 `Chrome exited early (exit code: 0) without writing DevToolsActivePort`——疑似与用户日常浏览器实例冲突或 headless 不兼容。改用 `run_in_background` 启动 + CDP 连接是已验证稳定方式。
>
> **Edge 特有坑**：Edge 的"启动助推"（startup boost）后台进程会拦截带独立参数的新实例，导致 profile 未生成、端口不监听。解决：删旧的 edge-profile 目录 + 带 `--no-first-run --no-default-browser-check` 重试。
>
> **Chrome profile 偶发静默启动失败**：`browser-profile` 用久后可能进程退出且无任何日志（端口 000、日志文件空）。此时换一个全新临时目录（如 `D:/yefengwei/wkt/.workbuddy/chrome-tmp`）启动即可；或删除 `browser-profile` 目录让其重建。

### B. 接入 agent-browser（CDP 连接模式）

每次新 Bash 会话**第一次**调用 agent-browser 都要先连接（连 Chrome 用 9224，连 Edge 用 9225）：

```bash
agent-browser connect 9224   # Chrome
# 或
agent-browser connect 9225   # Edge
```

> 必须先 connect。如果跳过会触发 agent-browser 自动启动浏览器失败。

### C. 自动化操作（Daemons 持久）

```bash
agent-browser open <url>          # 导航
agent-browser snapshot           # 页面 a11y 树（带 @eN 引用）
agent-browser snapshot -i        # 仅交互元素
agent-browser click <selector>   # 点击
agent-browser fill <sel> <text> # 填表
agent-browser screenshot <path>  # 截图
agent-browser get url           # 查当前 URL
agent-browser get title         # 查标题
agent-browser wait --load networkidle  # 等页面加载
```

### D. 收尾

```bash
agent-browser close     # 关闭 agent-browser daemon
# 浏览器进程可保留（下次直接 connect 复用），也可按需 taskkill 杀掉
```

## 排障速查

| 现象 | 原因 | 解决 |
|---|---|---|
| `node: --use-system-ca is not allowed in NODE_OPTIONS` | WorkBuddy 注入的 NODE_OPTIONS 不兼容 | 按上面"环境修复"export NODE_OPTIONS |
| `npm install ECONNREFUSED 127.0.0.1:7890` | 系统代理指向未运行的代理 | `unset HTTP_PROXY HTTPS_PROXY` |
| `agent-browser: command not found` | npm 全局 bin 未在 PATH | `npm install -g agent-browser` |
| `Chrome exited early (exit code: 0) without writing DevToolsActivePort` | agent-browser 自动启动失败 | 改用本 skill 的手动启动+CDP 方案 |
| `daemon already running` | 状态文件残留 | `rm ~/.agent-browser/default.*` 再重试 |
| Edge 启动后 9225 无响应 / profile 目录为空 | Edge 启动助推拦截新实例 | 删 edge-profile 目录 + `--no-first-run --no-default-browser-check` 重试 |
| `agent-browser doctor` 通过但 `--executable-path` 仍失败 | doctor 用了自带 Chrome，不验证指定路径 | 直接用手动启动方案，不要走 auto-launch |
| `connect` 后 snapshot 空页面 | connect 后 daemon 重启导致连接丢失 | connect 与后续命令放同一条命令链：`agent-browser connect <port> && agent-browser open <url>` |
| 命令返回 `Exit 1` 且 **stdout/stderr 全空**（连 echo 都没有） | ① 沙箱禁 loopback（curl/connect 被静默拦截）；② 命令内用 `&` 启动 Windows GUI 进程致 shell 崩溃 | ① 命令加 `dangerouslyDisableSandbox=true`；② 浏览器改用 `run_in_background=true` 启动，不要 `&` |
| 端口 000、日志文件为空，浏览器没起来 | Chrome `browser-profile` 损坏/锁残留 | 换临时目录（如 `chrome-tmp`）启动，或删除 `browser-profile` 重建 |
| 同一回合同时发 `run_in_background` 启动 + 前台截图 → 前台输出丢失（Exit 1 空） | Bash 工具并发后台+前台处理异常 | **分回合**：先发后台启动，再单独发前台截图命令 |

## 验证案例

- 2026-08-17（下午）Chrome：run_in_background + 禁用沙箱启动 9224（原 `browser-profile` 损坏，临时改用 `chrome-tmp` 目录）+ CDP 连接，成功打开 https://www.baidu.com，截图 `D:/yefengwei/wkt/baidu-chrome.png`
- 2026-08-17（下午）Edge：run_in_background + 禁用沙箱启动 9225 + CDP 连接，成功打开 https://www.baidu.com，截图 `D:/yefengwei/wkt/baidu-edge.png`（Edge/151.0.4129.86）
- **关键结论**：所有 CDP 命令必须 `dangerouslyDisableSandbox=true`；浏览器必须用 `run_in_background` 启动（禁止命令内 `&`）；前后台命令分回合执行避免输出丢失
- 早期（上午）曾用固定 profile 成功：`baidu-test.png`（Chrome）、`edge-baidu-test.png`（Edge）

## 重要约束

- **不要用 agent-browser 自带的 `--executable-path`** 走自动启动——本环境已验证不稳定
- **端口固定**：Chrome=9224、Edge=9225。不要打开第二个实例占用同一端口——端口被占会导致 connect 失败
- **每次新 Bash 会话都要走完整流程**（环境变量 + connect），daemon 状态不跨会话
- **agent-browser close 必做**——避免后台残留进程和 daemon 状态不一致
- **用户指定浏览器优先**：提到 Edge 就用 9225 流程，提到 Chrome 用 9224 流程；未指定默认 Chrome
- **所有 CDP 相关 Bash 命令必须 `dangerouslyDisableSandbox=true`**——沙箱禁本机 loopback，否则 curl/connect 被静默拦截（Exit 1 空输出）
- **启动浏览器必须用 `run_in_background=true`**（工具持有进程），禁止在命令里用 `&` 后台启动 Windows GUI（会令 shell 崩溃、输出全空）
- **不要在同一回并发"后台启动 + 前台截图"**——会丢输出；先发后台启动，再单独发前台截图
- **Chrome profile 偶发损坏可换临时目录**（`chrome-tmp`）绕过，无需删原目录
