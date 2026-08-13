# wit-combat-manager — 项目技术文档

> PySide6 桌面战斗管理器:TRPG 战斗流程管理(先攻、伤害、状态、元素损伤、行动顺序),
> 支持 v0.3 与 v1.2 双规则模式,规则内容完全外置可加载用户规则书。

## 1. 技术栈

| 类别 | 内容 |
|------|------|
| 语言/运行时 | Python + PySide6(桌面 GUI) |
| UI 组件 | qfluentwidgets(Fluent 风格主题、控件),`ui/fluent.py` 提供动画/按钮/对话框 helper |
| 规则引擎 | `models.py` + `combat.py` + `combat_report.py`(纯计算,UI 只渲染报告) |
| 持久化 | 单位数据原子保存 + 备份;战斗状态/战斗日志/GM 日志跨会话持久 |
| 打包 | PyInstaller(产物在 `dist/`、`release/`) |
| 测试 | pytest(约 189 用例,`test_*.py` 于仓库根) |

## 2. 架构概览

```
main.py(QApplication + DPI) ──> ui/(窗口/面板/对话框)
  │                              ├── main_window.py      主窗口
  │                              ├── combat_panel.py     战斗面板(先攻/行动顺序/操作)
  │                              ├── unit_panel.py       单位面板(树/版本切换)
  │                              ├── unit_dialog.py      单位编辑/新建对话框
  │                              ├── rule_browser.py     规则书浏览器
  │                              └── fluent.py           qfw 主题 + 动画 + 危险按钮 + 空态浮层
  ▼
models.py / combat.py / combat_report.py(规则引擎:双规则模式 RuleMode.V0_3 / V1_2)
  ▼
规则书(外置,用户自定义路径)+ 工作资料/(私有规则底稿)
```

- **分层铁律**:战斗规则只进 `models.py`/`combat.py`/`combat_report.py`;widgets 只调公共 API 并渲染返回的报告/消息,禁止把规则搬进 UI。
- **UI 主题**:颜色取 `models.py` 的 `THEME` 常量,禁止散落硬编码色值;`ui/fluent.py` 负责 qfluentwidgets 初始化与亮/暗适配。
- **错误安全**:公共战斗 API 失败时返回用户可见的错误信息,不得让 UI 崩溃。

## 3. 目录结构

```
wit-combat-manager/
├── main.py                # 入口:QApplication + DPI 处理
├── models.py              # 数据模型:Unit、CombatState、RuleMode、THEME、状态/元素定义
├── combat.py              # 战斗计算:先攻、伤害、状态效果(X 计数/升级链/标记/治疗限制/元素爆发溢出)
├── combat_report.py       # 报告 dataclass:伤害/治疗/状态/元素效果结果
├── app_paths.py           # 数据目录解析(可写目录)
├── ui/                    # 全部界面代码(见架构图)
├── 工作资料/              # 私有规则底稿(buff.txt、元素损伤.txt 等;禁止外发)
├── test_*.py              # pytest 测试(战斗规则、UI 冒烟、持久化、导入器等)
├── release/               # 打包产物(每目标最多 3 个历史版本)
└── AGENTS.md / CLAUDE.md  # 本技术文档
```

## 4. 构建与测试

```bash
# 测试(全量)
.venv/bin/python -m pytest -q          # 期望 189 passed
# 运行
python main.py
# 打包(PyInstaller,Windows)
pyinstaller wit-combat-manager.spec    # 产物 dist/,发布件复制到 release/
```

- 规则变更必须**先补 pytest 覆盖**(`test_combat.py` 或对应 `test_*.py`)再提交;纯战斗测试不得要求 GUI 显示。
- 测试注意:UI 动画测试使用条件轮询等待(`_wait_until`),禁止固定 `qWait` 短等待(满负载下曾 flaky)。

## 5. 运行与部署

- 开发运行:`python main.py`(Qt offscreen 平台变量可跑无头测试)。
- 发布:Windows x64 单文件/目录包,当前版本线 v2.2.x;规则书路径由用户在设置中指定。

## 6. 关键约束

- **规则兼容**:状态效果(X 计数器、升级链、标记行为、治疗限制、元素爆发溢出)必须与 `工作资料/buff.txt`、`元素损伤.txt` 规则一致;改前先查 `工作资料/`。
- **先攻与顺序**:顺位变更必须容忍已删除单位、空顺序表、速度重叠;同顺位按添加顺序排序。
- **持久化**:单位数据原子保存 + 备份;战斗状态/战斗日志/GM 日志跨会话;加载路径对缺失/损坏/不可访问文件安全降级,不阻塞退出。
- **双规则模式**:V0_3/V1_2 模式并存,UI 版本切换只改 `RuleMode`,不复制规则逻辑。
- **隐私**:`工作资料/` 不提交、不上传、不打印全文。

## 7. 开发约定

- 提交信息用中文,带 `feat/fix/refactor/test/docs/chore` 前缀,描述实际变更。
- 提交/推送前跑全量 pytest(证据先于断言);推送遇 SSH 限流串行重试。
- 架构/结构变化时同步更新本文件与 `CLAUDE.md`。
