"""TRPG 战斗管理器 - 数据模型"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import uuid


class RuleMode(str, Enum):
    V0_3 = "0.3"
    V1_2 = "1.2"

    @classmethod
    def coerce(cls, value: "RuleMode | str | None") -> "RuleMode":
        if isinstance(value, cls):
            return value
        if value is None:
            return cls.V1_2
        normalized = str(value).strip().lower().lstrip("v")
        aliases = {
            "0.3": cls.V0_3,
            "03": cls.V0_3,
            "1.2": cls.V1_2,
            "12": cls.V1_2,
        }
        if normalized not in aliases:
            raise ValueError(f"未知规则版本: {value}")
        return aliases[normalized]

    @property
    def display_name(self) -> str:
        return f"行于泰拉 v{self.value}"


RULE_MODES = tuple(mode.value for mode in RuleMode)


@dataclass(frozen=True)
class DiceGroup:
    """A user-entered group of dice. The engine never rolls these automatically."""

    count: int
    sides: int
    values: tuple[int, ...] = ()
    label: str = ""

    def validate(self) -> list[str]:
        errors = []
        if self.count < 0:
            errors.append("骰子数量不能为负数")
        if self.sides < 1:
            errors.append("骰面必须大于 0")
        if self.values and len(self.values) != self.count:
            errors.append(f"需要填写 {self.count} 个骰值，实际填写 {len(self.values)} 个")
        for value in self.values:
            if not 1 <= value <= self.sides:
                errors.append(f"骰值 {value} 不在 d{self.sides} 的有效范围内")
        return errors

    @property
    def total(self) -> int:
        return sum(self.values)


@dataclass(frozen=True)
class RollInput:
    """Manual roll input with an optional GM total override."""

    groups: tuple[DiceGroup, ...] = ()
    fixed_modifier: int = 0
    total_override: Optional[int] = None

    def validate(self) -> list[str]:
        errors = []
        for group in self.groups:
            errors.extend(group.validate())
        if self.total_override is None and not self.groups:
            errors.append("请填写逐骰结果或检定总值")
        if self.total_override is not None and self.total_override < 0:
            errors.append("检定总值不能为负数")
        return errors

    @property
    def total(self) -> int:
        if self.total_override is not None:
            return self.total_override
        return sum(group.total for group in self.groups) + self.fixed_modifier

    @property
    def has_die_detail(self) -> bool:
        return bool(self.groups) and all(group.values for group in self.groups)


@dataclass(frozen=True)
class StatusDefinition:
    name: str
    polarity: str
    end_event: str = "manual"
    counter: bool = False
    upgrade_to: str = ""
    aliases: tuple[str, ...] = ()

# ============================================================
# 状态/BUFF 定义 — 结束条件分类
# ============================================================

# 升级链：低级 → 高级
STATUS_UPGRADE = {
    "麻痹": "眩晕",
    "寒冷": "冻结",
    "困顿": "睡眠",
    "停顿": "束缚",
}

STATUS_ALIASES = {
    "困倦": "困顿",  # 旧数据兼容；v1.2 的规范名称为“困顿”
}

# 标记视为这四个状态（用于升级判断）
MARK_SYNONYMS = ["停顿", "震颤", "寒冷", "困顿"]

# ---- 回合结束一次 (end_of_turn) ----
END_OF_TURN_STATUSES = [
    "脆弱", "失能",
    "麻痹", "眩晕",
    "寒冷", "冻结",
    "困顿",
    "沉默", "战栗",
    "束缚",
    "目盲",
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
    "困顿", "睡眠",
    "停顿", "束缚",
    "失重", "浮空",
    "沉默", "战栗", "禁疗",
    "迟缓", "恐惧", "目盲",
    "濒死",
]

ALL_STATUS_NAMES = POSITIVE_BUFFS + NEGATIVE_BUFFS

# 带X的状态（可在名称后加数字，如 护盾3、脆弱2）
X_STATUSES = ["伤害强化", "护盾", "屏障", "抵抗", "元素屏障", "脆弱", "失重"]

V03_STATUS_UPGRADE = {
    "寒冷": "冻结",
    "震慑": "眩晕",
    "停顿": "束缚",
    "困顿": "睡眠",
    "失重": "浮空",
}
V03_POSITIVE_BUFFS = [
    "力量", "穿甲", "庇护", "迅捷", "免疫", "隐匿", "亲和",
]
V03_NEGATIVE_BUFFS = [
    "易伤", "虚弱", "失能", "失能后效", "标记",
    "寒冷", "冻结", "震慑", "眩晕", "困顿", "睡眠",
    "停顿", "束缚", "失重", "浮空", "禁疗", "迟缓", "濒死",
]
V03_STATUS_NAMES = V03_POSITIVE_BUFFS + V03_NEGATIVE_BUFFS
V03_X_STATUSES: list[str] = []


def normalize_status_name(name: str) -> str:
    return STATUS_ALIASES.get(name.strip(), name.strip())


def status_names_for(rule_mode: RuleMode | str) -> list[str]:
    mode = RuleMode.coerce(rule_mode)
    return list(V03_STATUS_NAMES if mode == RuleMode.V0_3 else ALL_STATUS_NAMES)


def x_statuses_for(rule_mode: RuleMode | str) -> list[str]:
    mode = RuleMode.coerce(rule_mode)
    return list(V03_X_STATUSES if mode == RuleMode.V0_3 else X_STATUSES)


STATUS_DEFINITIONS = {
    name: StatusDefinition(
        name=name,
        polarity="positive",
        end_event=(
            "attack" if name in END_OF_ATTACK_BUFFS else
            "heal_received" if name in END_OF_HEAL_BUFFS else
            "activation" if name in END_OF_ACTIVATION else
            "counter" if name in COUNTER_BUFFS else
            "manual"
        ),
        counter=name in X_STATUSES,
        upgrade_to=STATUS_UPGRADE.get(name, ""),
    )
    for name in POSITIVE_BUFFS
}
STATUS_DEFINITIONS.update({
    name: StatusDefinition(
        name=name,
        polarity="negative",
        end_event=(
            "turn_end" if name in END_OF_TURN_STATUSES else
            "heal_effect" if name in END_OF_HEAL_EFFECT_DEBUFFS else
            "move_prep" if name in END_OF_MOVE_PREP else
            "activation" if name in END_OF_ACTIVATION else
            "counter" if name in X_STATUSES else
            "manual"
        ),
        counter=name in X_STATUSES,
        upgrade_to=STATUS_UPGRADE.get(name, ""),
        aliases=("困倦",) if name == "困顿" else (),
    )
    for name in NEGATIVE_BUFFS
})

# ============================================================
# 元素损伤/爆发定义
# ============================================================

ELITE_TENACITY = {0: 6, 1: 9, 2: 12}  # elite_stage → tenacity cap

ELEMENT_TYPES = ["凋亡损伤", "组织损伤", "毒性损伤", "侵蚀损伤", "灼燃损伤", "神经损伤"]
V03_ELEMENT_TYPES = ELEMENT_TYPES + ["结晶损伤"]


def element_types_for(rule_mode: RuleMode | str) -> list[str]:
    mode = RuleMode.coerce(rule_mode)
    return list(V03_ELEMENT_TYPES if mode == RuleMode.V0_3 else ELEMENT_TYPES)

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

UNIT_TYPES = ("player", "monster", "ally")
UNIT_TYPE_LABELS = {"player": "玩家", "monster": "怪物", "ally": "友方"}


@dataclass
class Unit:
    name: str = ""
    unit_type: str = "player"  # "player" | "monster" | "ally"
    current_hp: int = 10
    max_hp: int = 10
    initial_max_hp: int = 0
    speed: int = 10
    initiative_rank: int = 0  # 指定顺位先攻模式的顺位，0=未设置（排最后）
    reaction_mobility: int = 0
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
    current_sp: int = 0
    max_sp: int = 9
    current_stamina: int = 0
    max_stamina: int = 0
    effect_die: str = ""
    auxiliary_die: str = ""
    profession: str = ""
    subprofession: str = ""
    level: int = 1
    pending_rolls: list[dict] = field(default_factory=list)

    def __post_init__(self):
        if self.unit_type not in UNIT_TYPES:
            self.unit_type = "player"
        if not self.unit_id:
            self.unit_id = uuid.uuid4().hex[:8]
        self.initiative_rank = max(0, int(self.initiative_rank))
        normalized_statuses = []
        for item in self.status_effects:
            if isinstance(item, str):
                normalized_statuses.append({"name": normalize_status_name(item), "stacks": 0})
            elif isinstance(item, dict):
                normalized = dict(item)
                normalized["name"] = normalize_status_name(str(item.get("name", "")))
                normalized["stacks"] = max(0, int(item.get("stacks", 0) or 0))
                if normalized["name"]:
                    normalized_statuses.append(normalized)
        self.status_effects = normalized_statuses
        normalized_rolls = []
        for item in self.pending_rolls:
            if not isinstance(item, dict):
                continue
            kind = str(item.get("kind", ""))
            if kind not in {"elemental_burst", "v03_elemental_burst"}:
                continue
            try:
                instances = max(0, int(item.get("instances", 0)))
            except (TypeError, ValueError, OverflowError):
                continue
            if instances > 0:
                normalized_rolls.append({
                    "kind": kind,
                    "element_type": str(item.get("element_type", "")),
                    "instances": instances,
                    "rule_mode": RuleMode.coerce(item.get("rule_mode", RuleMode.V1_2)).value,
                })
        self.pending_rolls = normalized_rolls
        if self.initial_max_hp <= 0:
            self.initial_max_hp = max(1, self.max_hp)
        self.max_hp = max(0, self.max_hp)
        self.current_hp = max(0, min(self.current_hp, self.max_hp))
        if self.has_status("濒死"):
            self.current_hp = 0
        if self.max_sp == 9 and self.elite_stage in ELITE_TENACITY:
            self.max_sp = 9 + 3 * self.elite_stage
        self.max_sp = max(0, self.max_sp)
        self.current_sp = max(0, min(self.current_sp, self.max_sp))
        self.max_stamina = max(0, self.max_stamina)
        self.current_stamina = max(0, min(self.current_stamina, self.max_stamina))
        self.level = max(1, int(self.level or 1))
        # 根据精英阶段自动设定韧性上限
        if self.elite_stage in ELITE_TENACITY and self.elemental_tenacity_max == 6:
            self.elemental_tenacity_max = ELITE_TENACITY[self.elite_stage]
            if self.elemental_tenacity_current == 6:
                self.elemental_tenacity_current = self.elemental_tenacity_max

    # ---- 状态效果辅助方法 ----
    def has_status(self, name: str) -> bool:
        """检查是否有某个状态（名称完全匹配）"""
        name = normalize_status_name(name)
        return any(s["name"] == name for s in self.status_effects)

    def get_status(self, name: str) -> Optional[dict]:
        """获取某个状态的 dict，没有则返回 None"""
        name = normalize_status_name(name)
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
        name = normalize_status_name(name)
        if not self.has_status(name):
            self.status_effects.append({"name": name, "stacks": stacks})
        if name == "濒死":
            self.current_hp = 0

    def remove_status(self, name: str) -> bool:
        """移除一个状态，返回是否成功"""
        name = normalize_status_name(name)
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

    def effective_resistance(self, damage_type: str) -> int:
        """Return resistance after rule-defined status modifiers."""
        if damage_type == "物理":
            return self.physical_resist + (10 if self.has_status("冻结") else 0)
        if damage_type == "法术":
            return self.magic_resist - (10 if self.has_status("冻结") else 0)
        return 0

    def is_dying(self) -> bool:
        return self.current_hp <= 0 or self.has_status("濒死")

    def is_dead(self) -> bool:
        return self.max_hp <= 0

    def injury_level(self) -> int:
        if self.initial_max_hp <= 0 or self.max_hp >= self.initial_max_hp:
            return 0
        ratio = self.max_hp / self.initial_max_hp
        if ratio < 0.10:
            return 3
        if ratio < 0.50:
            return 2
        return 1

    # ---- 序列化 ----
    def to_dict(self) -> dict:
        return {
            "unit_id": self.unit_id,
            "name": self.name,
            "unit_type": self.unit_type,
            "current_hp": self.current_hp,
            "max_hp": self.max_hp,
            "initial_max_hp": self.initial_max_hp,
            "speed": self.speed,
            "initiative_rank": self.initiative_rank,
            "reaction_mobility": self.reaction_mobility,
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
            "current_sp": self.current_sp,
            "max_sp": self.max_sp,
            "current_stamina": self.current_stamina,
            "max_stamina": self.max_stamina,
            "effect_die": self.effect_die,
            "auxiliary_die": self.auxiliary_die,
            "profession": self.profession,
            "subprofession": self.subprofession,
            "level": self.level,
            "pending_rolls": [dict(item) for item in self.pending_rolls],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Unit":
        # 兼容旧格式：status_effects 可能是 list[str] → 转为 list[dict]
        raw_status = d.get("status_effects", [])
        normalized_status = []
        for item in raw_status:
            if isinstance(item, str):
                normalized_status.append({"name": normalize_status_name(item), "stacks": 0})
            elif isinstance(item, dict):
                normalized = dict(item)
                normalized["name"] = normalize_status_name(str(item.get("name", "")))
                normalized["stacks"] = max(0, int(item.get("stacks", 0) or 0))
                if normalized["name"]:
                    normalized_status.append(normalized)

        return cls(
            unit_id=d.get("unit_id", ""),
            name=d.get("name", ""),
            unit_type=d.get("unit_type", "player"),
            current_hp=d.get("current_hp", 10),
            max_hp=d.get("max_hp", 10),
            initial_max_hp=d.get("initial_max_hp", d.get("max_hp", 10)),
            speed=d.get("speed", 10),
            initiative_rank=d.get("initiative_rank", 0),
            reaction_mobility=d.get("reaction_mobility", d.get("speed", 0)),
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
            current_sp=d.get("current_sp", d.get("sp", 0)),
            max_sp=d.get("max_sp", 9 + 3 * int(d.get("elite_stage", 0) or 0)),
            current_stamina=d.get("current_stamina", 0),
            max_stamina=d.get("max_stamina", 0),
            effect_die=d.get("effect_die", ""),
            auxiliary_die=d.get("auxiliary_die", ""),
            profession=d.get("profession", ""),
            subprofession=d.get("subprofession", ""),
            level=d.get("level", 1),
            pending_rolls=d.get("pending_rolls", []),
        )


# ============================================================
# CombatState
# ============================================================

@dataclass
class CombatState:
    turn: int = 0
    now_index: int = 0
    turn_order: list[str] = field(default_factory=list)  # unit_id 列表
    initiative_mode: str = "traditional"  # "team" | "traditional" | "manual" | "ranked"
    initiative_rolls: dict[str, int] = field(default_factory=dict)
    active: bool = False
    first_team: Optional[str] = None
    rule_mode: str = RuleMode.V1_2.value
    # v2: 迅捷/迟缓 在下一轮重新排序的标记
    pending_reorder: bool = False

    def __post_init__(self):
        self.rule_mode = RuleMode.coerce(self.rule_mode).value

    @property
    def current_unit_id(self) -> Optional[str]:
        if self.turn_order and 0 <= self.now_index < len(self.turn_order):
            return self.turn_order[self.now_index]
        return None


# ============================================================
# 主题颜色（集中管理硬编码颜色）
# ============================================================

THEME = {
    "window_bg": "#f3f3f3",
    "surface": "#ffffff",
    "surface_alt": "#f8f8f8",
    "surface_translucent": "rgba(255, 255, 255, 232)",
    "surface_alt_translucent": "rgba(249, 249, 249, 224)",
    "surface_hover": "rgba(246, 246, 246, 244)",
    "border": "#d6d6d6",
    "border_strong": "#b8b8b8",
    "hover_border": "#8f8f8f",
    "text": "#1a1a1a",
    "muted_text": "#616161",
    "accent": "#0067c0",
    "accent_hover": "#005a9e",
    "accent_pressed": "#004578",
    "accent_text": "#ffffff",
    "danger": "#c42b1c",
    "danger_hover": "#d13438",
    "success": "#0f7b0f",
    "disabled_bg": "#e5e5e5",
    "disabled_text": "#9d9d9d",
    "pressed_bg": "#e8e8e8",
    "scrollbar": "#b8b8b8",
    "subtle_fill": "rgba(0, 0, 0, 8)",
    "subtle_fill_hover": "rgba(0, 0, 0, 12)",
    "current_actor_bg": "#dbeeff",
    "monster_row_bg": "#fde7e9",
    "ally_row_bg": "#e3f4e6",
}
