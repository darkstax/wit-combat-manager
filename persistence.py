"""TRPG 战斗管理器 - JSON 持久化"""

import json
import os
from dataclasses import asdict
from typing import Optional
from models import Unit, CombatState

DEFAULT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.json")
COMBAT_STATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "combat_state.json")


def save_data(units: list[Unit], filepath: Optional[str] = None) -> str:
    """原子保存：先写临时文件再 os.replace，避免写入崩溃损坏数据"""
    path = filepath or DEFAULT_PATH
    data = [u.to_dict() for u in units]
    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)
    return path


def load_data(filepath: Optional[str] = None) -> list[Unit]:
    """加载单位列表，文件不存在返回空列表；JSON 损坏时保留 .bak 并返回空列表"""
    path = filepath or DEFAULT_PATH
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError):
        bak_path = path + ".bak"
        os.replace(path, bak_path)
        return []
    return [Unit.from_dict(d) for d in data]


def save_combat_state(state: CombatState, filepath: Optional[str] = None) -> str:
    """原子保存战斗状态（回合/先攻/行动顺序），用于崩溃恢复"""
    path = filepath or COMBAT_STATE_PATH
    data = asdict(state)
    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)
    return path


def load_combat_state(filepath: Optional[str] = None) -> Optional[CombatState]:
    """加载战斗状态，文件不存在或损坏返回 None"""
    path = filepath or COMBAT_STATE_PATH
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return CombatState(**data)
    except (json.JSONDecodeError, TypeError, KeyError):
        return None


def delete_combat_state(filepath: Optional[str] = None):
    path = filepath or COMBAT_STATE_PATH
    if os.path.exists(path):
        os.remove(path)
