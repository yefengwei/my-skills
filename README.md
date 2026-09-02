# my-skills

个人 WorkBuddy 自定义技能集合。每个子目录是一个独立 skill。

## 已收录

| Skill | 说明 |
|---|---|
| `Browser自动爬文档` | 复用已登录 Chrome 会话，监听内部 API 抓取 codefather.cn 等课程文档为 Markdown，并可一键导入飞书知识库 |
| `IT业务模块梳理` | 针对具体 IT 项目的业务模块进行「梳理」或「生成」，输出业务流程、前后端调用链路、状态流转、核心接口与数据模型，或完整教程级 Markdown 文档 |
| `browser-automation` | 浏览器自动化测试（Edge+Chrome）：基于本机真实浏览器（绿色版 Chrome:9224 / Edge:9225）做前端调试与自动化测试，手动启动 + CDP 连接模式，内置 NODE_OPTIONS / 代理环境变量修复 |

## 方法论 / 规范文档

| 文档 | 说明 |
|---|---|
| `笔记整理方法论.md` | 把课程（视频+字幕+课件）整理成图文并茂知识手册的可复用工作流：字幕提主干 + PDF 提要点 + 抽关键帧配图 + Mermaid 绘图 |
| `agent-env-policy.md` | Agent 环境限制通用规范：内置运行时只读、指定解释器全路径调用、数据盘纪律、缓存显式重定向、用后还原 |

## 目录规范

```
my-skills/
└── <skill-name>/
    ├── SKILL.md          # 技能主文件（必需）
    ├── scripts/          # 可执行脚本
    ├── references/       # 参考文档
    └── assets/           # 资源文件（可选）
```

## 本地使用

将本仓库的某个 skill 目录复制到 `~/.workbuddy/skills/` 即可被 WorkBuddy 识别。
