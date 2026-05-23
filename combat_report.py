"""TRPG 战斗管理器 - 结构化战斗计算结果"""

from dataclasses import dataclass, field


@dataclass
class DamageReport:
    """apply_damage 的计算结果（纯数据，不含格式化）"""
    blocked_by_shield: bool = False
    shield_remaining: int = 0
    raw_amount: int = 0
    resist_reduced: int = 0
    dmg_boost_added: int = 0
    vuln_added: int = 0
    barrier_absorbed: int = 0
    temp_hp_after: int = 0
    barrier_depleted: bool = False
    final_damage: int = 0
    hp_before: int = 0
    hp_after: int = 0
    is_dying: bool = False
    sleep_broken: bool = False


@dataclass
class HealingReport:
    """apply_healing 的计算结果"""
    blocked_by_regen_block: bool = False
    affinity_consumed: bool = False
    hp_before: int = 0
    hp_after: int = 0
    healed: int = 0
    heal_effect_cleared: list[str] = field(default_factory=list)


@dataclass
class StatusReport:
    """apply_status 的计算结果"""
    blocked_by_immune: bool = False
    blocked_by_resist: bool = False
    resist_remaining: int = 0
    is_mark: bool = False
    mark_sub_triggers: list[str] = field(default_factory=list)
    upgraded: bool = False
    upgraded_from: str = ""
    upgraded_to: str = ""
    stacked: bool = False
    stacks_before: int = 0
    stacks_after: int = 0
    simple_applied: bool = False
    already_exists: bool = False
    status_name: str = ""
    stacks_delta: int = 0


@dataclass
class ElementalReport:
    """apply_elemental_damage 的计算结果"""
    is_burst_period: bool = False
    true_dmg_dealt: int = 0
    barrier_absorbed: int = 0
    barrier_depleted: bool = False
    tenacity_reduced: int = 0
    tenacity_before: int = 0
    tenacity_after: int = 0
    burst_triggered: bool = False
    burst_type: str = ""
    burst_statuses: list[str] = field(default_factory=list)
    overflow: int = 0  # 超出韧性的损伤量，应在 mutation 层 ×3 转真伤
