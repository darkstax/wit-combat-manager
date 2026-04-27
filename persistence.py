"""TRPG 战斗管理器 - JSON 持久化"""

import json
import os
from typing import Optional
from models import Unit

DEFAULT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.json")


def save_data(units: list[Unit], filepath: Optional[str] = None) -> str:
    """保存单位列表到 JSON 文件，返回保存路径"""
    path = filepath or DEFAULT_PATH
    data = [u.to_dict() for u in units]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path


def load_data(filepath: Optional[str] = None) -> list[Unit]:
    """从 JSON 文件加载单位列表，文件不存在时返回空列表"""
    path = filepath or DEFAULT_PATH
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return [Unit.from_dict(d) for d in data]
