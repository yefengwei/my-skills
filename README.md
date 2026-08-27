# my-skills

个人 WorkBuddy 自定义技能集合。每个子目录是一个独立 skill。

## 已收录

| Skill | 说明 |
|---|---|
| `Browser自动爬文档` | 复用已登录 Chrome 会话，监听内部 API 抓取 codefather.cn 等课程文档为 Markdown，并可一键导入飞书知识库 |

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
