"""TRPG 战斗管理器 - 数据模型"""

from dataclasses import dataclass, field
from typing import Optional
import uuid

# ============================================================
# 状态/BUFF 定义 — 结束条件分类
# ============================================================

# 升级链：低级 → 高级
STATUS_UPGRADE = {
    "麻痹": "眩晕",
    "寒冷": "冻结",
    "困倦": "睡眠",
    "停顿": "束缚",
}

# 标记视为这四个状态（用于升级判断）
MARK_SYNONYMS = ["停顿", "震颤", "寒冷", "困倦"]

# ---- 回合结束一次 (end_of_turn) ----
END_OF_TURN_STATUSES = [
    "脆弱", "失能", "失能后效",
    "麻痹", "眩晕",
    "寒冷", "冻结",
    "困倦",
    "沉默", "战栗",
    "束缚",
    "目盲",
    "睡眠",  # 注意：睡眠另有一个条件是 HP因受攻击而减少，但回合结束也会清除
]

# ---- 攻击一次 (end_of_attack) ----
END_OF_ATTACK_BUFFS = [
    "伤害强化", "精准", "暴击", "穿透", "隐匿",
]

# ---- X为0时 (counter_exhaust) ----
COUNTER_BUFFS = [
    "护盾",   # 抵消攻击，每生效一次X-1
    "屏障",   # 临时HP，每生效一次X-1
    "抵抗",   # 无效X次状态施加
    "元素屏障", # 临时元素韧性
]

# ---- 受到一次治疗 (end_of_heal_received) ----
END_OF_HEAL_BUFFS = ["亲和"]

# ---- 受到一次治疗效果 (end_of_heal_effect) ----
END_OF_HEAL_EFFECT_DEBUFFS = ["禁疗"]

# ---- 生效一次 (end_of_activation) ----
END_OF_ACTIVATION = ["迅捷", "迟缓"]

# ---- 无公用结束条件 (no_universal_end) ----
NO_END_BUFFS = ["嘲讽", "被嘲讽", "迷彩", "免疫", "浮空"]

# ---- 特殊 ----
# 魅影: 【完全闪避】一次 → 归入 end_of_activation 类
# 恐惧: 周围8范围有友方 → 无公用结束条件
# 停顿: 执行一次【移动预备】后结束
END_OF_MOVE_PREP = ["停顿"]

# 全部可施加的状态（正面+负面，按buff.txt排序）
POSITIVE_BUFFS = [
    "伤害强化", "精准", "魅影", "嘲讽", "被嘲讽",
    "迅捷", "护盾", "屏障", "隐匿", "迷彩",
    "抵抗", "元素屏障", "暴击", "免疫", "穿透", "亲和",
]

NEGATIVE_BUFFS = [
    "脆弱", "失能", "失能后效", "标记",
    "麻痹", "眩晕",
    "寒冷", "冻结",
    "困倦", "睡眠",
    "停顿", "束缚",
    "失重", "浮空",
    "沉默", "战栗", "禁疗",
    "迟缓", "恐惧", "目盲",
]

ALL_STATUS_NAMES = POSITIVE_BUFFS + NEGATIVE_BUFFS

# 带X的状态（可在名称后加数字，如 护盾3、脆弱2）
X_STATUSES = ["伤害强化", "护盾", "屏障", "抵抗", "元素屏障", "脆弱", "失重"]

# ============================================================
# 元素损伤/爆发定义
# ============================================================

ELITE_TENACITY = {0: 6, 1: 9, 2: 12}  # elite_stage → tenacity cap

ELEMENT_TYPES = ["凋亡损伤", "组织损伤", "毒性损伤", "侵蚀损伤", "灼燃损伤", "神经损伤"]

ELEMENTAL_BURST_EFFECTS = {
    "凋亡损伤": {
        "true_dmg_mult": 2,
        "extra": "失去3SP；若无SP可失去，额外造成1次真实伤害",
        "statuses": ["迟缓"],
    },
    "组织损伤": {
        "true_dmg_mult": 3,
        "extra": "",
        "statuses": ["迟缓"],
    },
    "毒性损伤": {
        "true_dmg_mult": 2,
        "extra": "爆发期间施加[禁疗]",
        "statuses": ["迟缓", "禁疗"],
    },
    "侵蚀损伤": {
        "true_dmg_mult": 2,
        "extra": "爆发期间受物理伤害+1辅助骰",
        "statuses": ["迟缓"],
    },
    "灼燃损伤": {
        "true_dmg_mult": 2,
        "extra": "爆发期间受法术伤害+1辅助骰",
        "statuses": ["迟缓"],
    },
    "神经损伤": {
        "true_dmg_mult": 1,
        "extra": "爆发期间施加[眩晕]",
        "statuses": ["迟缓", "眩晕"],
    },
}


# ============================================================
# Unit 数据模型
# ============================================================

@dataclass
class Unit:
    name: str = ""
    unit_type: str = "player"  # "player" | "monster"
    current_hp: int = 10
    max_hp: int = 10
    speed: int = 10
    physical_resist: int = 0
    magic_resist: int = 0
    armor_type: str = "轻甲"
    status_effects: list[dict] = field(default_factory=list)  # [{"name": str, "stacks": int}]
    unit_id: str = ""
    # v2 新增
    temp_hp: int = 0
    weight: int = 0
    elite_stage: int = 0  # 0/1/2 → 6/9/12 韧性上限
    elemental_tenacity_current: int = 6
    elemental_tenacity_max: int = 6
    elemental_burst: str = ""  # 当前爆发类型，空=无
    elemental_burst_remaining: int = 0  # 剩余持续回合数

    def __post_init__(self):
        if not self.unit_id:
            self.unit_id = uuid.uuid4().hex[:8]
        # 根据精英阶段自动设定韧性上限
        if self.elite_stage in ELITE_TENACITY and self.elemental_tenacity_max == 6:
            self.elemental_tenacity_max = ELITE_TENACITY[self.elite_stage]
            if self.elemental_tenacity_current == 6:
                self.elemental_tenacity_current = self.elemental_tenacity_max

    # ---- 状态效果辅助方法 ----
    def has_status(self, name: str) -> bool:
        """检查是否有某个状态（名称完全匹配）"""
        return any(s["name"] == name for s in self.status_effects)

    def get_status(self, name: str) -> Optional[dict]:
        """获取某个状态的 dict，没有则返回 None"""
        for s in self.status_effects:
            if s["name"] == name:
                return s
        return None

    def has_any_status(self, names: list[str]) -> bool:
        """检查是否有列表中任一状态"""
        for s in self.status_effects:
            if s["name"] in names:
                return True
        return False

    def add_status(self, name: str, stacks: int = 0):
        """添加一个状态，不处理升级逻辑"""
        if not self.has_status(name):
            self.status_effects.append({"name": name, "stacks": stacks})

    def remove_status(self, name: str) -> bool:
        """移除一个状态，返回是否成功"""
        for i, s in enumerate(self.status_effects):
            if s["name"] == name:
                self.status_effects.pop(i)
                return True
        return False

    def status_names(self) -> list[str]:
        """返回所有状态名称列表"""
        return [s["name"] for s in self.status_effects]

    # ---- 元素韧性 ----
    def reduce_tenacity(self, amount: int) -> int:
        """减少元素韧性，返回实际减少量。若归零返回负数表示溢出量"""
        actual = min(amount, self.elemental_tenacity_current)
        self.elemental_tenacity_current -= actual
        return amount - actual  # 溢出量

    def recover_tenacity(self):
        """恢复元素韧性至上限，清除爆发状态"""
        self.elemental_tenacity_current = self.elemental_tenacity_max
        self.elemental_burst = ""
        self.elemental_burst_remaining = 0

    def is_in_burst(self) -> bool:
        return bool(self.elemental_burst) and self.elemental_burst_remaining > 0

    def effective_hp(self) -> int:
        """实际血量（含临时HP）"""
        return self.current_hp + self.temp_hp

    # ---- 序列化 ----
    def to_dict(self) -> dict:
        return {
            "unit_id": self.unit_id,
            "name": self.name,
            "unit_type": self.unit_type,
            "current_hp": self.current_hp,
            "max_hp": self.max_hp,
            "speed": self.speed,
            "physical_resist": self.physical_resist,
            "magic_resist": self.magic_resist,
            "armor_type": self.armor_type,
            "status_effects": [dict(s) for s in self.status_effects],
            "temp_hp": self.temp_hp,
            "weight": self.weight,
            "elite_stage": self.elite_stage,
            "elemental_tenacity_current": self.elemental_tenacity_current,
            "elemental_tenacity_max": self.elemental_tenacity_max,
            "elemental_burst": self.elemental_burst,
            "elemental_burst_remaining": self.elemental_burst_remaining,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Unit":
        # 兼容旧格式：status_effects 可能是 list[str] → 转为 list[dict]
        raw_status = d.get("status_effects", [])
        normalized_status = []
        for item in raw_status:
            if isinstance(item, str):
                normalized_status.append({"name": item, "stacks": 0})
            elif isinstance(item, dict):
                normalized_status.append({"name": item.get("name", ""), "stacks": item.get("stacks", 0)})

        return cls(
            unit_id=d.get("unit_id", ""),
            name=d.get("name", ""),
            unit_type=d.get("unit_type", "player"),
            current_hp=d.get("current_hp", 10),
            max_hp=d.get("max_hp", 10),
            speed=d.get("speed", 10),
            physical_resist=d.get("physical_resist", 0),
            magic_resist=d.get("magic_resist", 0),
            armor_type=d.get("armor_type", "轻甲"),
            status_effects=normalized_status,
            temp_hp=d.get("temp_hp", 0),
            weight=d.get("weight", 0),
            elite_stage=d.get("elite_stage", 0),
            elemental_tenacity_current=d.get("elemental_tenacity_current", 6),
            elemental_tenacity_max=d.get("elemental_tenacity_max", 6),
            elemental_burst=d.get("elemental_burst", ""),
            elemental_burst_remaining=d.get("elemental_burst_remaining", 0),
        )


# ============================================================
# CombatState
# ============================================================

@dataclass
class CombatState:
    turn: int = 0
    now_index: int = 0
    turn_order: list[str] = field(default_factory=list)  # unit_id 列表
    initiative_mode: str = "traditional"  # "team" | "traditional" | "manual"
    initiative_rolls: dict[str, int] = field(default_factory=dict)
    active: bool = False
    first_team: Optional[str] = None
    # v2: 迅捷/迟缓 在下一轮重新排序的标记
    pending_reorder: bool = False

    @property
    def current_unit_id(self) -> Optional[str]:
        if self.turn_order and 0 <= self.now_index < len(self.turn_order):
            return self.turn_order[self.now_index]
        return None
