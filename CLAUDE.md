# wit-combat-manager — 快捷指南

> 完整技术文档见 `AGENTS.md`;本文件为精简版,与 AGENTS.md 保持同步。

## 速览

- PySide6 桌面战斗管理器(TRPG),支持 v0.3/v1.2 双规则模式,规则书外置。
- 规则引擎:`models.py` + `combat.py` + `combat_report.py`;UI 全部在 `ui/`,入口 `main.py`。

## 常用命令

```bash
.venv/bin/python -m pytest -q    # 全量测试(期望 189 passed)
python main.py                   # 运行
```

## 关键约束

- 规则只进 models/combat/combat_report,widgets 只渲染报告,禁止把规则搬进 UI。
- 状态/元素/先攻/顺位行为改动前先查 `工作资料/`(私有,不提交不外发)。
- 单位数据原子保存 + 备份;战斗状态/双日志跨会话持久;加载失败不阻塞退出。
- 颜色取 `models.THEME`,禁止硬编码;公共战斗 API 失败返回可见错误而非崩溃。
- UI 动画测试用条件轮询等待,禁止固定短 `qWait`(曾 flaky)。

## 开发约定

- 规则变更先补 pytest 覆盖再提交;中文提交信息(feat/fix/refactor/test/docs/chore 前缀)。
- 提交/推送前全量 pytest 全绿。
