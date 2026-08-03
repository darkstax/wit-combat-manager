"""Walk in the Terra v0.3 combat rules.

All dice are supplied by the GM. This module never rolls on the user's behalf.
"""

from decimal import Decimal, ROUND_HALF_UP

from models import (
    CombatState,
    RuleMode,
    Unit,
    V03_ELEMENT_TYPES,
    V03_STATUS_NAMES,
    V03_STATUS_UPGRADE,
)


def _round_half_up(value: float) -> int:
    return int(Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def v03_initiative(
    units: list[Unit],
    tie_roll_values: dict[str, int] | None = None,
) -> CombatState:
    """Order by speed, then raw MOB; exact ties use entered d100 rolls."""
    state = CombatState(
        turn=1,
        initiative_mode="v03_speed",
        active=True,
        rule_mode=RuleMode.V0_3.value,
    )
    rolls = tie_roll_values or {}

    tied: dict[tuple[int, int], list[Unit]] = {}
    for unit in units:
        tied.setdefault((unit.speed, unit.reaction_mobility), []).append(unit)

    tie_priority: dict[str, tuple[int, int]] = {}
    for group in tied.values():
        if len(group) == 1:
            continue
        missing = [unit.name or unit.unit_id for unit in group if unit.unit_id not in rolls]
        if missing:
            raise ValueError(f"同速且反应机动相同，请填写这些单位的 d100 对抗骰: {'、'.join(missing)}")
        outcomes = []
        for unit in group:
            roll = int(rolls[unit.unit_id])
            if not 1 <= roll <= 100:
                raise ValueError(f"{unit.name} 的反应机动骰必须在 1-100 之间")
            success = roll <= max(0, unit.reaction_mobility)
            outcomes.append((unit, success, roll))
        if all(not success for _, success, _ in outcomes):
            raise ValueError("同速单位的反应机动检定均失败，请重投后重新填写")
        for unit, success, roll in outcomes:
            tie_priority[unit.unit_id] = (1 if success else 0, -roll)

    ordered = sorted(
        units,
        key=lambda unit: (
            unit.speed,
            unit.reaction_mobility,
            *tie_priority.get(unit.unit_id, (0, 0)),
        ),
        reverse=True,
    )
    state.turn_order = [unit.unit_id for unit in ordered]
    state.initiative_rolls = {str(uid): int(value) for uid, value in rolls.items()}
    return state


def ranked_initiative(
    players: list[Unit],
    monsters: list[Unit],
    rule_mode: RuleMode | str = RuleMode.V0_3,
) -> CombatState:
    """按各单位 initiative_rank 降序生成行动顺序；
    同顺位按 unit_id 稳定排序，顺位 0（未设置）排最后。"""
    mode = RuleMode.coerce(rule_mode)
    state = CombatState(
        turn=1,
        initiative_mode="ranked",
        active=True,
        rule_mode=mode.value,
    )
    units_by_id = {u.unit_id: u for u in players + monsters}
    state.turn_order = sorted(
        [u.unit_id for u in players + monsters],
        key=lambda uid: (-units_by_id[uid].initiative_rank, uid),
    )
    return state


def _apply_hp_damage(unit: Unit, damage: int) -> tuple[int, list[str]]:
    messages = []
    remaining = max(0, damage)
    if unit.temp_hp > 0 and remaining > 0:
        absorbed = min(unit.temp_hp, remaining)
        unit.temp_hp -= absorbed
        remaining -= absorbed
        messages.append(f"临时HP吸收 {absorbed} 点")

    theoretical_hp = unit.current_hp - remaining
    if theoretical_hp <= -unit.max_hp and remaining > 0:
        unit.current_hp = 0
        unit.max_hp = 0
        unit.remove_status("濒死")
        messages.append("理论HP低于负生命上限，直接死亡")
    elif theoretical_hp <= 0 and remaining > 0:
        unit.current_hp = 0
        if not unit.has_status("濒死"):
            unit.add_status("濒死", 1)
        messages.append("HP归零，进入濒死")
    else:
        unit.current_hp = max(0, theoretical_hp)
    return remaining, messages


def apply_damage_v03(
    unit: Unit,
    amount: int,
    dmg_type: str = "物理",
    is_attack: bool = True,
    attacker: Unit | None = None,
    amount_is_final: bool = False,
    auxiliary_damage: int = 0,
    final_multiplier: float = 1.0,
    attack_roll: int | None = None,
    success_rate: int | None = None,
    dying_save_succeeded: bool | None = None,
    normal_multiplier: float = 1.0,
    final_constant: int = 0,
) -> str:
    if amount <= 0:
        return "[错误] 伤害骰结果必须大于 0"
    if dmg_type not in {"物理", "法术", "真实"}:
        return f"[错误] v0.3 不支持该伤害类型: {dmg_type}"
    if auxiliary_damage < 0 or normal_multiplier < 0 or final_multiplier < 0:
        return "[错误] 常数修正、常规倍率和最终倍率不能为负数"
    if is_attack:
        if attack_roll is None or success_rate is None:
            return "[错误] v0.3 攻击需要填写 d100 命中骰和武器技能成功率"
        if not 1 <= attack_roll <= 100 or not 0 <= success_rate <= 100:
            return "[错误] 命中骰须为 1-100，技能成功率须为 0-100"
        if attack_roll > success_rate:
            cleanup = process_end_attack_v03(attacker)
            result = f"{unit.name} 未被命中（d100={attack_roll} > 成功率{success_rate}）"
            return result + (f"\n{cleanup}" if cleanup else "")

    if unit.is_dying():
        status = unit.get_status("濒死")
        difficulty = max(1, int(status.get("stacks", 1))) if status else 1
        if dying_save_succeeded is None:
            return (
                f"[待填写] {unit.name} 已濒死且再次被命中，请进行第 {difficulty} 级濒死检定，"
                "再选择成功或失败结算"
            )
        if not dying_save_succeeded:
            unit.max_hp = 0
            unit.current_hp = 0
            unit.remove_status("濒死")
            return f"{unit.name} 的濒死检定失败，死亡"
        if status:
            status["stacks"] = min(3, difficulty + 1)
        return f"{unit.name} 的濒死检定成功；下次检定难度提升至 {min(3, difficulty + 1)}"

    normal_constant = auxiliary_damage
    if is_attack and attacker and attacker.has_status("力量"):
        normal_constant += 10

    resistance = 0
    if not amount_is_final and dmg_type == "物理":
        resistance = unit.physical_resist
    elif not amount_is_final and dmg_type == "法术":
        resistance = unit.magic_resist
    if is_attack and attacker and attacker.has_status("穿甲"):
        resistance = _round_half_up(resistance * 0.5)

    sleep_multiplier = 1.5 if unit.has_status("睡眠") else 1.0
    final_damage = max(
        0,
        _round_half_up(
            (
                (amount + normal_constant) * normal_multiplier
                - resistance
                + final_constant
            )
            * final_multiplier
            * sleep_multiplier
        ),
    )
    hp_before = unit.current_hp
    applied, notes = _apply_hp_damage(unit, final_damage)
    if is_attack and unit.has_status("睡眠"):
        unit.remove_status("睡眠")
        notes.append("睡眠因受到攻击而解除")
    process_end_attack_v03(attacker) if attacker else None

    detail = f"{unit.name} 受到 {applied} 点{dmg_type}伤害（HP: {hp_before}->{unit.current_hp}/{unit.max_hp}）"
    if notes:
        detail += "\n" + "；".join(notes)
    return detail


def apply_healing_v03(unit: Unit, amount: int) -> str:
    if amount <= 0:
        return "[错误] 生命回复必须大于 0"
    if unit.is_dying():
        return f"{unit.name} 正处于濒死，普通生命回复不能将其救起"
    if unit.has_status("禁疗"):
        return f"{unit.name} 处于禁疗，本次生命回复无效"
    before = unit.current_hp
    unit.current_hp = min(unit.max_hp, unit.current_hp + amount)
    return f"{unit.name} 恢复 {unit.current_hp - before} 点HP（HP: {before}->{unit.current_hp}/{unit.max_hp}）"


V03_BURST_EFFECTS = {
    "凋亡损伤": {"damage_type": "元素", "statuses": ["虚弱"], "sp_loss": 10},
    "灼燃损伤": {"damage_type": "元素", "statuses": [], "magic_resist": -10},
    "侵蚀损伤": {"damage_type": "元素", "statuses": [], "physical_resist": -10},
    "神经损伤": {"damage_type": "真实", "statuses": ["眩晕"]},
    "组织损伤": {"damage_type": "元素", "statuses": ["禁疗"]},
    "毒性损伤": {"damage_type": "元素", "statuses": ["虚弱", "迟缓"]},
    "结晶损伤": {"damage_type": "元素", "statuses": [], "infection": "2d5/10"},
}


def _apply_v03_burst_side_effects(unit: Unit, element_type: str) -> list[str]:
    effect = V03_BURST_EFFECTS[element_type]
    messages = []
    for status in effect.get("statuses", []):
        messages.append(apply_status_v03(unit, status))
    if effect.get("sp_loss"):
        lost = min(unit.current_sp, int(effect["sp_loss"]))
        unit.current_sp -= lost
        messages.append(f"失去 {lost} SP")
    if effect.get("physical_resist"):
        unit.physical_resist += int(effect["physical_resist"])
        messages.append("物理抗性 -10，持续至战斗结束")
    if effect.get("magic_resist"):
        unit.magic_resist += int(effect["magic_resist"])
        messages.append("法术抗性 -10，持续至战斗结束")
    if effect.get("infection"):
        messages.append("感染值增加 2d5/10，请填写并记录感染骰结果")
    return messages


def _resolve_v03_burst_damage(
    unit: Unit,
    element_type: str,
    burst_total: int,
    element_resistance: int = 0,
) -> str:
    if burst_total < 0 or element_resistance < 0:
        return "[错误] 爆发总值和元素抗性不能为负数"
    is_true = V03_BURST_EFFECTS[element_type]["damage_type"] == "真实"
    damage = burst_total if is_true else max(0, burst_total - element_resistance)
    hp_before = unit.current_hp
    applied, notes = _apply_hp_damage(unit, damage)
    message = (
        f"{element_type}爆发 10d6={burst_total}"
        f"{'（真实伤害）' if is_true else f' - 元素抗性{element_resistance}'}，"
        f"造成 {applied} 点伤害（HP: {hp_before}->{unit.current_hp}/{unit.max_hp}）"
    )
    if notes:
        message += "\n" + "；".join(notes)
    return message


def apply_elemental_damage_v03(
    unit: Unit,
    amount: int,
    element_type: str,
    burst_roll: int | None = None,
    element_resistance: int = 0,
) -> str:
    if amount <= 0:
        return "[错误] 元素损伤必须大于 0"
    if element_type not in V03_ELEMENT_TYPES:
        return f"[错误] v0.3 未知元素损伤类型: {element_type}"

    before = unit.elemental_tenacity_current
    unit.elemental_tenacity_current -= amount
    message = f"{unit.name} 受到 {amount} 点{element_type}（韧性: {before}->{max(0, unit.elemental_tenacity_current)}）"
    if unit.elemental_tenacity_current > 0:
        return message

    unit.elemental_tenacity_current = unit.elemental_tenacity_max or 10
    message += f"\n!!! 触发{element_type}爆发，韧性立即恢复至 {unit.elemental_tenacity_current} !!!"
    side_effects = _apply_v03_burst_side_effects(unit, element_type)
    if side_effects:
        message += "\n" + "\n".join(side_effects)
    if burst_roll is None:
        unit.pending_rolls.append({
            "kind": "v03_elemental_burst",
            "element_type": element_type,
            "instances": 1,
            "rule_mode": RuleMode.V0_3.value,
        })
        return message + "\n[待填写] 请填写本次 10d6 爆发伤害总值"
    return message + "\n" + _resolve_v03_burst_damage(
        unit, element_type, burst_roll, element_resistance
    )


def resolve_pending_elemental_burst_v03(
    unit: Unit,
    burst_roll: int,
    element_resistance: int = 0,
) -> str:
    for index, pending in enumerate(unit.pending_rolls):
        if pending.get("kind") != "v03_elemental_burst":
            continue
        element_type = str(pending.get("element_type", ""))
        if element_type not in V03_BURST_EFFECTS:
            return "[错误] 待处理的 v0.3 元素爆发记录已损坏"
        message = _resolve_v03_burst_damage(
            unit, element_type, burst_roll, element_resistance
        )
        if not message.startswith("[错误]"):
            unit.pending_rolls.pop(index)
        return "[补充结算] " + message
    return f"[错误] {unit.name} 没有待结算的 v0.3 元素爆发"


def apply_status_v03(unit: Unit, status_name: str) -> str:
    status_name = status_name.strip()
    if status_name not in V03_STATUS_NAMES:
        return f"[错误] v0.3 未知状态: {status_name}"

    upgrade = V03_STATUS_UPGRADE.get(status_name)
    if unit.has_status(status_name) and upgrade:
        unit.remove_status(status_name)
        unit.add_status(upgrade)
        return f"{unit.name} 的「{status_name}」再次生效，升级为「{upgrade}」"
    if unit.has_status(status_name):
        return f"{unit.name} 已有「{status_name}」，同名状态不叠加"

    for lower, higher in V03_STATUS_UPGRADE.items():
        if status_name == higher:
            unit.remove_status(lower)
            break
    unit.add_status(status_name, 1 if status_name == "濒死" else 0)
    return f"{unit.name} 获得「{status_name}」"


def process_turn_start_v03(unit: Unit) -> list[str]:
    messages = []
    if unit.has_status("困顿"):
        unit.remove_status("困顿")
        messages.append(f"{unit.name} 的「困顿」生效：本回合失去快速行动")
    if unit.is_dying():
        messages.append(f"{unit.name} 处于濒死，无法行动且被动失效")
    return messages


def process_end_of_turn_v03(unit: Unit) -> list[str]:
    messages = []
    if unit.remove_status("失能后效"):
        messages.append(f"{unit.name} 的「失能后效」结束")
    return messages


def process_end_attack_v03(unit: Unit | None) -> str:
    if unit is None:
        return ""
    removed = [name for name in ("力量", "穿甲") if unit.remove_status(name)]
    return f"{unit.name} 的攻击状态结束: {'、'.join(removed)}" if removed else ""
