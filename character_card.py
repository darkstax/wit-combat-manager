"""TRPG 战斗管理器 - 角色卡导入模块

支持两种导入方式：
1. xlsx 角色卡 — 读取 Excel 缓存值（需在 Excel 中打开并保存过）
2. 快速导入文本 — 从骰娘导出格式提取关键属性（备用方案，无精英化等级）
"""

import re
import openpyxl
from models import Unit

# ============================================================
# 目标单元格映射
# ============================================================

CELL_MAP = {
    "name": "D3",
    "max_hp": "AI24",
    "physical_resist": "AI25",
    "magic_resist": "AI26",
    "elite_stage": "AR10",
}

ELITE_MAP = {
    "阶级零": 0, "阶级一": 1, "阶级二": 2,
    "精英零": 0, "精英一": 1, "精英二": 2,
    "精零": 0, "精一": 1, "精二": 2,
    "0": 0, "1": 1, "2": 2,
}

# ============================================================
# xlsx 导入
# ============================================================

def _find_target_sheet(wb, refs: list[str]) -> str:
    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        for ref in refs:
            try:
                if ws[ref].value is not None:
                    return sheet_name
            except (ValueError, KeyError):
                pass
    return wb.sheetnames[0]


def import_character_card(filepath: str) -> Unit:
    """从 xlsx 角色卡文件导入（依赖 Excel 保存的缓存值）"""
    target_refs = list(CELL_MAP.values())

    wb = openpyxl.load_workbook(filepath, data_only=True)
    sheet_name = _find_target_sheet(wb, target_refs)
    ws = wb[sheet_name]

    raw = {}
    missing = []
    for field, cell_ref in CELL_MAP.items():
        try:
            raw[field] = ws[cell_ref].value
        except Exception:
            raw[field] = None
        if raw[field] is None:
            missing.append(cell_ref)
    wb.close()

    if missing:
        raise ValueError(
            f"以下单元格无缓存值: {', '.join(missing)}\n"
            f"请在 Excel 中打开此文件并保存 (Ctrl+S)，然后重试导入。"
        )

    name = _extract_name(raw["name"])
    max_hp = _extract_number(raw["max_hp"], "最大生命值")
    phys_res = _extract_number(raw["physical_resist"], "物理抗性")
    magic_res = _extract_number(raw["magic_resist"], "法术抗性")
    elite_stage = _extract_elite(raw["elite_stage"])

    return Unit(
        name=name,
        unit_type="player",
        current_hp=max_hp,
        max_hp=max_hp,
        physical_resist=phys_res,
        magic_resist=magic_res,
        elite_stage=elite_stage,
    )


def _extract_name(val) -> str:
    if val is None:
        return "未命名角色"
    if isinstance(val, str):
        return val.strip() or "未命名角色"
    if isinstance(val, (int, float)):
        return str(int(val)) if val != 0 else "未命名角色"
    return "未命名角色"


def _extract_number(val, label: str) -> int:
    if val is None:
        raise ValueError(f"{label} 单元格为空")
    if isinstance(val, (int, float)):
        return int(round(val))
    s = str(val).strip()
    if s.startswith("/"):
        s = s[1:]
    try:
        return int(float(s))
    except ValueError:
        raise ValueError(f"{label} 无法解析为整数: '{val}'")


def _extract_elite(val) -> int:
    if val is None:
        return 0
    if isinstance(val, (int, float)):
        v = int(val)
        return v if v in (0, 1, 2) else 0
    s = str(val).strip()
    for key, stage in ELITE_MAP.items():
        if key in s:
            return stage
    m = re.search(r"[012]", s)
    if m:
        return int(m.group(0))
    return 0

# ============================================================
# 快速导入（骰娘导出文本）
# ============================================================

# 属性名 → Unit 字段 + 转换函数
QUICK_IMPORT_FIELDS = [
    ("生命值上限", "max_hp", int),
    ("物理抗性", "physical_resist", int),
    ("法术抗性", "magic_resist", int),
    ("元素韧性", "elemental_tenacity_current", int),
    ("速度", "speed", int),
    ("重量等级", "weight", int),
    ("等级", "level", int),
]


def import_from_quick_text(text: str, name: str = "") -> Unit:
    """从骰娘快速导出文本中提取属性（备用导入方案）

    文本格式: 属性名+数值 的紧凑拼接，如 "生命值上限15物理抗性5..."
    此格式不含精英化等级，默认设为 0。
    """
    extracted = {}
    for field_name, key, converter in QUICK_IMPORT_FIELDS:
        m = re.search(rf"{field_name}(\d+)", text)
        if m:
            extracted[key] = converter(m.group(1))

    max_hp = extracted.get("max_hp", 10)
    return Unit(
        name=name.strip() or "导入角色",
        unit_type="player",
        current_hp=max_hp,
        max_hp=max_hp,
        physical_resist=extracted.get("physical_resist", 0),
        magic_resist=extracted.get("magic_resist", 0),
        speed=extracted.get("speed", 10),
        weight=extracted.get("weight", 0),
        elemental_tenacity_current=extracted.get("elemental_tenacity_current", 6),
        elemental_tenacity_max=extracted.get("elemental_tenacity_current", 6),
        elite_stage=0,
    )
