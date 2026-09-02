# Agent 环境限制通用规范

> 版本 v1.0 · 2026-09-02
> 适用对象：任何带 shell/工具执行能力的 AI Agent（LobsterAI、Claude Code、Cursor、Cline、Codex CLI、Windsurf 等）
> 目的：防止 Agent 污染系统盘、篡改宿主运行环境；把运行时、模型、缓存、临时文件收敛到用户指定位置。

---

## 一、核心原则（5 条）

1. **内置运行时只读**
   Agent 自带的 Python/Node 等运行时仅视为其内部依赖，禁止向其 `pip install` / `npm install -g` 任何包，禁止将其作为任务执行环境。
2. **指定环境全路径调用**
   所有脚本一律用用户指定解释器的**绝对路径**执行。不要信任 PATH 解析——Agent 常把自己的运行时目录插到 PATH 最前面（本机实例：`where python` 第一位是 LobsterAI 内置 python）。
3. **数据盘纪律**
   模型、数据集、音视频中间产物、构建产物一律放指定数据盘目录；系统盘（C:）只允许程序本身。临时文件放任务工作目录的 `.cowork-temp/`，可随时整目录删除。
4. **缓存显式重定向（双保险）**
   会下载资源的库，一律通过环境变量把缓存指到数据盘；且在每次工具调用时**显式传 env**，不赌"Agent 进程已继承用户级变量"（已运行进程读不到新设置的用户级变量）。
5. **用后还原 + 删除须确认**
   误装进错误环境的包必须立即卸载还原，并报告释放空间；任何删除类操作执行前必须获得用户确认。

---

## 二、缓存重定向环境变量清单（按需取用）

| 工具/库 | 变量/配置 | 建议指向 |
|---|---|---|
| Hugging Face | `HF_HOME` | `<数据盘>\ai-models\huggingface` |
| Hugging Face Hub | `HF_HUB_CACHE` | `<数据盘>\ai-models\huggingface\hub` |
| Transformers（旧版兼容） | `TRANSFORMERS_CACHE` | 同 `HF_HUB_CACHE` |
| pip | `PIP_CACHE_DIR` | `<数据盘>\cache\pip` |
| PyTorch | `TORCH_HOME` | `<数据盘>\ai-models\torch` |
| openai-whisper | 转写参数 `download_root=` | `<数据盘>\ai-models\whisper` |
| 通用 XDG 系 | `XDG_CACHE_HOME` | `<数据盘>\cache` |
| npm | `npm config set cache <路径>` | `<数据盘>\cache\npm` |

> 设置方式：用户级设置一次（`setx` 或 PowerShell `[Environment]::SetEnvironmentVariable(...,'User')`）+ Agent 调用时显式注入，双保险。用户级变量只对**之后新启动的进程**生效。

---

## 三、本机现行配置（实例存档）

| 项 | 值 |
|---|---|
| 指定 Python | `D:\software\mise\data\installs\python\3.14.6\python.exe`（shim：`D:\software\mise\data\shims\python.exe`） |
| 禁用运行时 | `C:\Users\ysq\AppData\Roaming\LobsterAI\runtimes\python-win\python.exe`、`D:\software\LobsterAI\resources\python-win\python.exe` |
| 模型库 | `D:\software\ai-models`（已含 `huggingface\`、`smartsub-whisper\`） |
| 已设用户级变量 | `HF_HOME`、`HF_HUB_CACHE`、`TRANSFORMERS_CACHE` → `D:\software\ai-models\huggingface` |
| 临时目录 | `<任务工作目录>\.cowork-temp\` |

---

## 四、落地到其他厂商 Agent 的方法

1. **指令文件注入**：把第五节模板粘贴进对应 Agent 的持久指令文件。
   - LobsterAI → `MEMORY.md` / `TOOLS.md`
   - Claude Code → `CLAUDE.md`
   - Codex / 通用 → `AGENTS.md`
   - Cursor → `.cursor/rules`
   - Cline → `.clinerules`
   - Windsurf → `.windsurfrules`
2. **系统层**：用户级环境变量设置一次即可，Agent 应用需重启才能继承。
3. **PATH 层**：若可控启动方式，把指定运行时目录排到 PATH 最前；不管排不排，执行时坚持绝对路径。
4. **污染巡检**：定期按"创建时间"排查内置运行时的 site-packages 是否被误装（本案例即用 `CreationTime -ge <日期>` 定位全部误装包）。

---

## 五、Agent 指令模板（复制即用，替换 {{占位符}}）

```markdown
## 环境硬性约束（必须遵守）

1. 禁止使用 Agent 内置运行时：不得使用 {{内置解释器路径列表}}，也不得向其安装任何包。
2. Python 一律用绝对路径调用：{{PYTHON_PATH}}（不依赖 PATH 解析）。
3. 模型/缓存重定向：执行任何会下载模型的命令前，显式注入环境变量：
   HF_HOME={{MODEL_DIR}}\huggingface
   HF_HUB_CACHE={{MODEL_DIR}}\huggingface\hub
   TRANSFORMERS_CACHE={{MODEL_DIR}}\huggingface\hub
4. 大文件纪律：模型、数据集、音视频产物一律放 {{MODEL_DIR}}；系统盘只读不改。
5. 临时文件：放当前任务工作目录 .cowork-temp\ 下。
6. 还原义务：误向禁用环境安装了包，必须立即卸载还原，并向用户报告释放的空间。
7. 删除须确认：任何删除操作先列出目标清单，获得用户确认后执行。
```

---

## 六、验证清单

1. `where.exe python` / `Get-Command python -All` → 确认解析顺序，识别内置运行时抢占。
2. `{{PYTHON_PATH}} -c "import sys; print(sys.executable)"` → 确认全路径调用生效。
3. 显式注入 env 后执行 `python -c "import os; print(os.environ['HF_HOME'])"` → 确认重定向生效。
4. 实测下载一个小模型，核对落盘目录是否在数据盘。
5. `Get-ChildItem <内置site-packages> | Where CreationTime -ge <日期>` → 内置环境污染排查。

---

## 七、参考案例（2026-09-02 本机执行记录）

1. 现象：视频转写任务把 faster-whisper 装进了 LobsterAI 内置 Python，模型缓存落在 C 盘 `.cache`（468MB）。
2. 迁移：`robocopy /MOVE` 将 HF 缓存整体移至 `D:\software\ai-models\huggingface`，0 失败。
3. 配置：用户级设置 `HF_HOME` / `HF_HUB_CACHE` / `TRANSFORMERS_CACHE` 三个变量。
4. 重建：指定环境（mise Python 3.14.6，D 盘）重装 faster-whisper 并通过 import 验证。
5. 还原：内置 Python 按创建时间排查出全部 22 个新增条目（含依赖），逐一卸载，共释放 199MB，环境恢复原状。
6. 净效果：C 盘释放约 530MB；后续 Agent 任务全部收敛到 D 盘与工作目录。
