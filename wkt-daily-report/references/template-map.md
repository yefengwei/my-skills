# 模板单元格地图

源文件：`D:/yefengwei/wkt/公共盘/日报/WKT-工号-Daily-Work-Schedule-2026-模版.xlsx`
（2026-09-03 公司下发的新版空白模板，替代旧 `WKT-22836-…-模版.xlsx`；二者结构完全一致，
仅文件名与 Project Task List 示例行数不同。config.template 失效时脚本自动找目录里
最新的 `*模版*.xlsx` 兜底。）
（从 Apple Numbers 导出，所以带一个 `Export Summary` 说明页）

## Sheet 清单

| Sheet | 用途 | 是否动它 |
|---|---|---|
| Export Summary | Numbers 导出说明 | 不动 |
| Project Task List - Project Tas | 项目任务清单（历史任务，167 行） | 不动 |
| Daily Work Schedule - SUN | 周汇总页，同时是**间隔公式的源头** | 初始化时间列 |
| Monday … Saturday | 每日排期 | 日期 + 时间 + 内容（主战场） |
| Data Settings | 周一日期 + 可选时间点位表 | 只写 H1 |

## 每日 sheet（以 Monday 为例，其余同构）

| 单元格 | 内容 | 说明 |
|---|---|---|
| B1 | `DAILY WORK SCHEDULE TEMPLATE` | 标题 |
| E2 / G2 / I2 | `WEEK BEGINNING` / `SCHEDULED START TIME` / `INTERVALS` | 标签 |
| E3 | `='Data Settings'!H1` | 周一日期，格式 `dddd, mmmm dd, yyyy` |
| G3 | 上班时间（time 或 datetime） | 格式 `h:mm AM/PM`，初始化时写入 |
| I3 / I4 | `60 MIN` / `=--LEFT(I3,3)` | 间隔文本与解析公式 |
| B5 / C5 / E5 / G5 | `TIME` / 当日日期 / `Notes / Remarks / Completion Status` / `WEEKLY OVERVIEW` | 表头行 |
| C5 | `=E3+N` | N=0(周一)…5(周六) |
| B6 | `=G3` | 第一个时间点 |
| B7…B15 | `=B{prev}+TIME(0,'Daily Work Schedule - SUN'!$I$5,0)` | 后续时间点 |
| C6…C15 | **工作内容**（本 skill 的写入目标） | 字体 DengXian 10，左对齐，不自动换行 |
| E6…E15 | 完成状态 / 备注 | 可写 `Done` / `In progress` |
| G7,G10,G13…G25 | `=E3+k` 周概览日期 | 日页显示提示「complete on SUN tab」，通常不管 |

### 行布局（模板原样：9:00 AM 起、60 分钟格，结束点模型：行时间 = 时段结束时刻）

| 行 | B 列时间 | C 列 | 类别 |
|---|---|---|---|
| 6 | 9:00 AM | 内容（含 8:30 到岗后的半小时） | work |
| 7 | 10:00 AM | 内容 | work |
| 8 | 11:00 AM | 内容 | work |
| 9 | 12:00 PM | 内容（上午最后一段） | work |
| 10 | 1:00 PM | `午休`（12:00~13:00） | lunch（保护） |
| 11 | 2:00 PM | 内容 | work |
| 12 | 3:00 PM | 内容 | work |
| 13 | 4:00 PM | 内容 | work |
| 14 | 5:00 PM | 内容（16:00~17:00，最后一段） | work |
| 15 | 6:00 PM | 空（下班后，不填） | off（保护） |

共 8 个可填工作段。模板原本就把公式铺到 B38（日页）/ B39（SUN 页），**初始化完全不碰
B 列**（模板公式原样保留，连"补全"都不需要）；B16 起（7:00 PM 以后）留白不填。
改开始时间这类操作被禁止——config 必须与模板 G3/I3 保持一致。

## SUN 页差异

| 单元格 | 内容 |
|---|---|
| B6 | `TIME`（表头） |
| C6 | `=E4-1` |
| E4 | `='Data Settings'!H1` |
| G4 | 上班时间（B7 引用它） |
| I4 / I5 | `60 MIN` / `=--LEFT(I4,3)` ← **全表间隔源** |
| B7 | `=G4`，之后 `=B{prev}+TIME(0,$I$5,0)`（本页内引用，不带 sheet 名） |
| G6:J6 | 合并单元格 `WEEKLY OVERVIEW` |

→ 改间隔必须改 **SUN!I4**，日页的 I3 只是显示用。

## Data Settings 页

| 单元格 | 内容 |
|---|---|
| G1 | `周一日期：`（用户自己加的中文标签） |
| H1 | 周一日期，格式原为 `mm-dd-yy`，初始化时改为 `yyyy-mm-dd` |
| B3:B26 | 06:00–05:00 的可选时间点位（下拉用） |
| D3:D12 | 可选间隔：10/15/20/30/45/50/60/75/90/120 MIN |

## 字体与格式

- 标题/表头：Century Gothic 12 加粗
- 时间列 B：Century Gothic 11，格式 `h:mm AM/PM`，右对齐
- 内容列 C：DengXian 10，左对齐，**无自动换行**，列宽 55.78，行高 24
- 日期行 C5 / E3：格式 `dddd, mmmm dd, yyyy`

→ C 列不换行 + 行高 24，意味着单条内容控制在 ~110 字符以内才不会看不全。

## 脚本与文件一览

| 文件 | 作用 |
|---|---|
| `scripts/init_week.py` | 按周建工作簿 + 初始化日期/时间列（--dry-run/--force） |
| `scripts/fill_day.py` | 写/追加/预览/清空某日 8 个时段（午休与下班行受保护） |
| `scripts/scan_git.py` | 扫 git_root 下当日提交/暂存（--with-diff 出补丁，--all-authors 不滤作者） |
| `scripts/log_ctx.py` | 追加工作条目到 `output_dir/context/YYYY-MM-DD.md`（跨 agent 共享，--list 回看） |
| `config.json` | 员工号/姓名/路径/上下班/间隔/git 白名单/大小周基准 |
| `SKILL.md` | 触发条件 + 五步流程 + 同义换写词库（agent 直接照着执行） |

### context 共享流水约定

`output_dir/context/YYYY-MM-DD.md`：本机多个 agent / 用户共写的每日工作素材池。
写日报时把「用户清单 + 本文件 + git 扫描 + 当前会话当日产出」合并成工作池再分时段，
避免只凭一句话遗漏产出。追加格式：

```
- [HH:MM] [source: 来源标识] [可选模块tag] 一句话工作内容
```
