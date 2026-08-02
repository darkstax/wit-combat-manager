"""TRPG 战斗管理器 - 战斗逻辑"""

import random
from decimal import Decimal, ROUND_HALF_UP
from models import (
    Unit, CombatState, RuleMode,
    STATUS_UPGRADE, MARK_SYNONYMS, STATUS_DEFINITIONS,
    END_OF_TURN_STATUSES, END_OF_ATTACK_BUFFS,
    COUNTER_BUFFS, END_OF_HEAL_BUFFS, END_OF_HEAL_EFFECT_DEBUFFS,
    END_OF_ACTIVATION, END_OF_MOVE_PREP,
    ELITE_TENACITY, ELEMENTAL_BURST_EFFECTS,
    X_STATUSES, ELEMENT_TYPES, normalize_status_name,
)
from combat_report import DamageReport, HealingReport, StatusReport, ElementalReport
from combat_v03 import (
    apply_damage_v03,
    apply_elemental_damage_v03,
    apply_healing_v03,
    apply_status_v03,
    process_end_attack_v03,
    process_end_of_turn_v03,
    process_turn_start_v03,
    resolve_pending_elemental_burst_v03,
    v03_initiative,
)

# ============================================================
# 先攻系统
# ============================================================

def team_initiative(
    players: list[Unit],
    monsters: list[Unit],
    rule_mode: RuleMode | str = RuleMode.V1_2,
    tie_roll_values: dict[str, int] | None = None,
) -> CombatState:
    mode = RuleMode.coerce(rule_mode)
    if mode == RuleMode.V0_3:
        return v03_initiative(players + monsters, tie_roll_values)
    state = CombatState(
        turn=1,
        initiative_mode="team",
        active=True,
        rule_mode=mode.value,
    )

    def team_score(units: list[Unit]) -> int:
        if not units:
            return 0
        speeds = [u.speed for u in units]
        return max(speeds) + min(speeds) if len(speeds) >= 2 else speeds[0] * 2

    player_score = team_score(players)
    monster_score = team_score(monsters)

    if player_score >= monster_score:
        state.first_team = "player"
        state.turn_order = [u.unit_id for u in players + monsters]
    else:
        state.first_team = "monster"
        state.turn_order = [u.unit_id for u in monsters + players]

    return state


def manual_initiative(
    first_team: str,
    players: list[Unit],
    monsters: list[Unit],
    rule_mode: RuleMode | str = RuleMode.V1_2,
) -> CombatState:
    mode = RuleMode.coerce(rule_mode)
    state = CombatState(
        turn=1,
        initiative_mode="manual",
        active=True,
        rule_mode=mode.value,
    )
    state.first_team = first_team

    if first_team == "player":
        state.turn_order = [u.unit_id for u in players + monsters]
    else:
        state.turn_order = [u.unit_id for u in monsters + players]

    return state


def traditional_initiative(
    units: list[Unit],
    dice_faces: int = 20,
    roll_values: dict[str, int] | None = None,
    rule_mode: RuleMode | str = RuleMode.V1_2,
) -> CombatState:
    """Traditional initiative using user-entered check totals when provided.

    The random fallback is kept for compatibility with older callers. The v1.2 UI
    should always pass ``roll_values`` because reaction-mobility checks are dice pools,
    not d20 + speed rolls.
    """
    mode = RuleMode.coerce(rule_mode)
    if mode == RuleMode.V0_3:
        return v03_initiative(units, roll_values)
    state = CombatState(
        turn=1,
        initiative_mode="traditional",
        active=True,
        rule_mode=mode.value,
    )
    rolls: dict[str, int] = {}

    def roll_unit(u: Unit) -> int:
        return random.randint(1, dice_faces) + u.speed

    if roll_values is not None:
        missing = [u.name or u.unit_id for u in units if u.unit_id not in roll_values]
        if missing:
            raise ValueError(f"缺少先攻检定结果: {', '.join(missing)}")
        for u in units:
            value = int(roll_values[u.unit_id])
            if value < 0:
                raise ValueError(f"{u.name or u.unit_id} 的先攻检定结果不能为负数")
            rolls[u.unit_id] = value
        tied_groups: dict[tuple[int, int], list[str]] = {}
        for unit in units:
            key = (rolls[unit.unit_id], unit.speed)
            tied_groups.setdefault(key, []).append(unit.name or unit.unit_id)
        unresolved = [names for names in tied_groups.values() if len(names) > 1]
        if unresolved:
            names = "、".join(unresolved[0])
            raise ValueError(f"{names} 的检定结果与反应机动均相同，请重投后重新填写")
    else:
        for u in units:
            rolls[u.unit_id] = roll_unit(u)
        _resolve_ties(units, rolls, roll_unit)

    state.initiative_rolls = rolls
    sorted_units = sorted(units, key=lambda u: (rolls[u.unit_id], u.speed), reverse=True)
    state.turn_order = [u.unit_id for u in sorted_units]

    return state


def _resolve_ties(units: list[Unit], rolls: dict[str, int], roll_func, max_attempts: int = 10) -> None:
    unit_map = {u.unit_id: u for u in units}

    for _ in range(max_attempts):
        by_roll: dict[int, list[str]] = {}
        for uid, roll in rolls.items():
            by_roll.setdefault(roll, []).append(uid)

        ties = {roll: uids for roll, uids in by_roll.items() if len(uids) > 1}
        if not ties:
            return

        for roll_val, tied_ids in ties.items():
            speeds = [unit_map[uid].speed for uid in tied_ids]
            if len(set(speeds)) == len(speeds):
                continue

            speed_groups: dict[int, list[str]] = {}
            for uid in tied_ids:
                speed_groups.setdefault(unit_map[uid].speed, []).append(uid)

            for sp, group in speed_groups.items():
                if len(group) > 1:
                    for uid in group:
                        rolls[uid] = roll_func(unit_map[uid])


# ============================================================
# 伤害系统
# ============================================================

def _round_half_up(value: float | Decimal) -> int:
    return int(Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _finish_damage_report(unit: Unit, report: DamageReport, damage: int, is_attack: bool) -> None:
    """Fill HP outcomes without mutating the target."""
    report.hp_before = unit.current_hp
    report.hp_after = unit.current_hp
    report.max_hp_before = unit.max_hp
    report.max_hp_after = unit.max_hp
    report.was_dying = unit.is_dying()

    barrier = unit.get_status("屏障")
    if unit.temp_hp > 0 and damage > 0:
        absorbed = min(damage, unit.temp_hp)
        report.barrier_absorbed = absorbed
        report.temp_hp_after = unit.temp_hp - absorbed
        damage -= absorbed
        if barrier and barrier["stacks"] - 1 <= 0:
            report.barrier_depleted = True
    else:
        report.temp_hp_after = unit.temp_hp

    report.final_damage = max(0, damage)
    if report.was_dying:
        report.max_hp_damage = report.final_damage
        report.max_hp_after = max(0, unit.max_hp - report.max_hp_damage)
    elif report.final_damage >= unit.current_hp and report.final_damage > 0:
        report.hp_after = 0
        report.max_hp_damage = max(0, report.final_damage - unit.current_hp)
        report.max_hp_after = max(0, unit.max_hp - report.max_hp_damage)
        report.is_dying = unit.current_hp > 0
    else:
        report.hp_after = max(0, unit.current_hp - report.final_damage)

    report.is_dead = report.max_hp_after <= 0
    report.sleep_broken = (
        is_attack
        and unit.has_status("睡眠")
        and report.hp_after < report.hp_before
    )


def _calc_damage(
    unit: Unit,
    amount: int,
    dmg_type: str,
    is_attack: bool,
    attacker: Unit | None = None,
    amount_is_final: bool = False,
    auxiliary_damage: int = 0,
    final_multiplier: float = 1.0,
) -> DamageReport:
    """Pure v1.2 damage calculation.

    ``amount`` is the entered attack check total / pre-reduction damage unless
    ``amount_is_final`` is explicitly set by the GM.
    """
    report = DamageReport(
        raw_amount=amount,
        damage_type=dmg_type,
        hp_before=unit.current_hp,
        hp_after=unit.current_hp,
        max_hp_before=unit.max_hp,
        max_hp_after=unit.max_hp,
        final_multiplier=final_multiplier,
    )
    if amount <= 0:
        return report

    resist = 0 if amount_is_final else unit.effective_resistance(dmg_type)
    report.resistance = resist
    report.resist_reduced = resist
    if is_attack and not amount_is_final and amount < resist:
        report.attack_missed = True
        _finish_damage_report(unit, report, 0, is_attack)
        return report

    shield = unit.get_status("护盾")
    if is_attack and shield and shield["stacks"] > 0:
        report.blocked_by_shield = True
        report.shield_remaining = shield["stacks"] - 1
        return report

    final_dmg = max(0, amount - resist)

    if is_attack and attacker is not None:
        dmg_boost = attacker.get_status("伤害强化")
        if dmg_boost and dmg_boost["stacks"] > 0:
            report.dmg_boost_added = dmg_boost["stacks"]
            final_dmg += report.dmg_boost_added

    vuln = unit.get_status("脆弱")
    if vuln and vuln["stacks"] > 0:
        report.vuln_added = vuln["stacks"]
        final_dmg += report.vuln_added

    if auxiliary_damage > 0:
        report.auxiliary_added = auxiliary_damage
        final_dmg += auxiliary_damage

    final_dmg = max(0, _round_half_up(final_dmg * max(0.0, final_multiplier)))
    _finish_damage_report(unit, report, final_dmg, is_attack)
    return report


def _calc_true_damage(unit: Unit, amount: int, is_attack: bool = False) -> DamageReport:
    """Pure true-damage calculation. True damage is not modified or resisted."""
    report = DamageReport(
        raw_amount=amount,
        damage_type="真实",
        resist_reduced=0,
        hp_before=unit.current_hp,
        hp_after=unit.current_hp,
        max_hp_before=unit.max_hp,
        max_hp_after=unit.max_hp,
    )
    if amount <= 0:
        return report

    shield = unit.get_status("护盾")
    if is_attack and shield and shield["stacks"] > 0:
        report.blocked_by_shield = True
        report.shield_remaining = shield["stacks"] - 1
        return report

    _finish_damage_report(unit, report, amount, is_attack)
    return report


def apply_damage(
    unit: Unit,
    amount: int,
    dmg_type: str = "物理",
    is_attack: bool = True,
    attacker: Unit | None = None,
    amount_is_final: bool = False,
    auxiliary_damage: int = 0,
    final_multiplier: float = 1.0,
    rule_mode: RuleMode | str = RuleMode.V1_2,
    attack_roll: int | None = None,
    success_rate: int | None = None,
    dying_save_succeeded: bool | None = None,
    normal_multiplier: float = 1.0,
    final_constant: int = 0,
) -> str:
    """Apply user-entered damage/check totals and return a user-visible result."""
    mode = RuleMode.coerce(rule_mode)
    if mode == RuleMode.V0_3:
        return apply_damage_v03(
            unit,
            amount,
            dmg_type,
            is_attack,
            attacker,
            amount_is_final,
            auxiliary_damage,
            final_multiplier,
            attack_roll,
            success_rate,
            dying_save_succeeded,
            normal_multiplier,
            final_constant,
        )
    try:
        if dmg_type not in {"物理", "法术", "真实"}:
            return f"[错误] 未知伤害类型: {dmg_type}"
        if amount <= 0:
            return f"[错误] 伤害或检定骰值必须大于 0"
        if auxiliary_damage < 0 or final_multiplier < 0:
            return "[错误] 辅助伤害和最终倍率不能为负数"

        if dmg_type == "真实":
            report = _calc_true_damage(unit, amount, is_attack)
        else:
            report = _calc_damage(
                unit,
                amount,
                dmg_type,
                is_attack,
                attacker=attacker,
                amount_is_final=amount_is_final,
                auxiliary_damage=auxiliary_damage,
                final_multiplier=final_multiplier,
            )
        _apply_damage_mutations(unit, report)
        result = _format_damage_result(unit, report, dmg_type)
        if is_attack and attacker is not None:
            end_attack_msg = process_end_attack(attacker)
            if end_attack_msg:
                result += f"\n{end_attack_msg}"
        return result
    except Exception as e:
        return f"[错误] 造成伤害时内部错误: {e}，请主持手动处理目标单位的HP和状态。"


def _apply_damage_mutations(unit: Unit, r: DamageReport):
    if r.blocked_by_shield:
        shield = unit.get_status("护盾")
        if shield:
            shield["stacks"] -= 1
            if shield["stacks"] <= 0:
                unit.remove_status("护盾")
        return

    if r.barrier_absorbed > 0:
        unit.temp_hp = r.temp_hp_after
        barrier = unit.get_status("屏障")
        if barrier:
            # 屏障按一次伤害事件消耗一层，而不是按吸收的伤害点数消耗。
            barrier["stacks"] = max(0, barrier["stacks"] - 1)
            if r.barrier_depleted:
                unit.remove_status("屏障")
                unit.temp_hp = 0

    unit.current_hp = r.hp_after
    unit.max_hp = r.max_hp_after
    if r.is_dying and not unit.has_status("濒死"):
        unit.add_status("濒死")
    if r.sleep_broken:
        unit.remove_status("睡眠")


def _format_damage_result(unit: Unit, r: DamageReport, dmg_type: str) -> str:
    if r.attack_missed:
        return (
            f"{unit.name} 未被命中（攻击检定 {r.raw_amount} < "
            f"{dmg_type}抗性 {r.resistance}）"
        )
    if r.blocked_by_shield:
        return f"{unit.name} 的护盾抵消了本次攻击（剩余{r.shield_remaining}次）"

    result = f"{unit.name} 受到 {r.final_damage} 点{dmg_type}伤害（HP: {r.hp_after}/{r.max_hp_after}"
    if unit.temp_hp > 0:
        result += f", 临时HP: {unit.temp_hp}"
    result += "）"
    if r.max_hp_damage > 0:
        result += f"\n濒死溢出使生命值上限降低 {r.max_hp_damage} 点 → {r.max_hp_after}"
    if r.is_dying:
        result += f"\n!!! {unit.name} HP归零，陷入濒死状态 !!!"
    if r.is_dead:
        result += f"\n!!! {unit.name} 的生命值上限归零，已死亡 !!!"
    if r.sleep_broken:
        result += f"\n{unit.name} 的「睡眠」因攻击使HP降低而解除"
    return result


def _apply_true_damage(unit: Unit, amount: int) -> str:
    report = _calc_true_damage(unit, amount)
    _apply_damage_mutations(unit, report)
    return _format_damage_result(unit, report, "真实")


def _apply_true_damage_mutations(unit: Unit, r: DamageReport):
    _apply_damage_mutations(unit, r)


def _format_true_damage_result(unit: Unit, r: DamageReport) -> str:
    return _format_damage_result(unit, r, "真实")


def _calc_healing(unit: Unit, amount: int) -> HealingReport:
    """纯计算：读 unit 状态，不修改 unit"""
    report = HealingReport(
        hp_before=unit.current_hp,
        hp_after=unit.current_hp,
        heal_effect_cleared=[s for s in END_OF_HEAL_EFFECT_DEBUFFS if unit.has_status(s)],
        affinity_consumed=unit.has_status("亲和"),
    )

    if amount <= 0:
        report.invalid_amount = True
        return report

    if unit.is_dying():
        report.blocked_by_dying = True
        return report

    if unit.has_status("禁疗"):
        report.blocked_by_regen_block = True
        return report

    report.hp_after = min(unit.max_hp, unit.current_hp + amount)
    report.healed = report.hp_after - report.hp_before

    return report


def apply_healing(
    unit: Unit,
    amount: int,
    rule_mode: RuleMode | str = RuleMode.V1_2,
) -> str:
    if RuleMode.coerce(rule_mode) == RuleMode.V0_3:
        return apply_healing_v03(unit, amount)
    """Apply a user-entered healing result."""
    try:
        if amount <= 0:
            return "[错误] 治疗骰值必须大于 0"
        report = _calc_healing(unit, amount)
        _apply_healing_mutations(unit, report)
        return _format_healing_result(unit, report)
    except Exception as e:
        return f"[错误] 施加治疗时内部错误: {e}，请主持手动处理目标单位的HP。"


def _apply_healing_mutations(unit: Unit, r: HealingReport):
    if r.affinity_consumed:
        unit.remove_status("亲和")
    for name in r.heal_effect_cleared:
        unit.remove_status(name)
    if not r.blocked_by_regen_block and not r.blocked_by_dying and not r.invalid_amount:
        unit.current_hp = r.hp_after


def _format_healing_result(unit: Unit, r: HealingReport) -> str:
    if r.invalid_amount:
        return "[错误] 治疗骰值必须大于 0"
    suffix = "（禁疗已在本次治疗效果后结束）" if "禁疗" in r.heal_effect_cleared else ""
    if r.blocked_by_dying:
        return f"{unit.name} 处于濒死状态，无法恢复生命值{suffix}"
    if r.blocked_by_regen_block:
        return f"{unit.name} 受到「禁疗」影响，治疗失效{suffix}"
    return f"{unit.name} 恢复了 {r.healed} 点生命（HP: {r.hp_after}/{unit.max_hp}）"


# ============================================================
# 元素损伤系统
# ============================================================

def _calc_elemental(unit: Unit, amount: int, elem_type: str) -> ElementalReport:
    """纯计算：读 unit 状态，不修改 unit"""
    report = ElementalReport()

    if amount <= 0:
        report.invalid_amount = True
        return report
    if elem_type not in ELEMENT_TYPES:
        report.invalid_type = True
        return report

    if unit.is_in_burst():
        report.is_burst_period = True
        report.true_dmg_dealt = amount * 3
        return report

    remaining = amount
    elem_barrier = unit.get_status("元素屏障")
    if elem_barrier and elem_barrier["stacks"] > 0:
        absorbed = min(remaining, elem_barrier["stacks"])
        report.barrier_absorbed = absorbed
        remaining -= absorbed
        if elem_barrier["stacks"] - absorbed <= 0:
            report.barrier_depleted = True

    if remaining > 0:
        report.tenacity_before = unit.elemental_tenacity_current
        reduced = min(remaining, unit.elemental_tenacity_current)
        report.overflow = max(0, remaining - unit.elemental_tenacity_current)
        report.tenacity_reduced = reduced
        report.tenacity_after = unit.elemental_tenacity_current - reduced
        if report.tenacity_after <= 0 and elem_type in ELEMENTAL_BURST_EFFECTS:
            report.burst_triggered = True
            report.burst_type = elem_type
            report.burst_statuses = list(ELEMENTAL_BURST_EFFECTS[elem_type]["statuses"])
    else:
        report.tenacity_before = unit.elemental_tenacity_current
        report.tenacity_after = unit.elemental_tenacity_current

    return report


def apply_elemental_damage(
    unit: Unit,
    amount: int,
    elem_type: str,
    burst_roll: int | None = None,
    rule_mode: RuleMode | str = RuleMode.V1_2,
    element_resistance: int = 0,
) -> str:
    """Apply elemental damage and an optional user-entered auxiliary die result."""
    if RuleMode.coerce(rule_mode) == RuleMode.V0_3:
        return apply_elemental_damage_v03(
            unit,
            amount,
            elem_type,
            burst_roll,
            element_resistance,
        )
    try:
        if amount <= 0:
            return "[错误] 元素损伤必须大于 0"
        if elem_type not in ELEMENT_TYPES:
            return f"[错误] 未知元素损伤类型: {elem_type}"
        if burst_roll is not None and burst_roll < 0:
            return "[错误] 爆发辅助骰结果不能为负数"
        report = _calc_elemental(unit, amount, elem_type)
        return _apply_elemental_mutations(unit, report, amount, elem_type, burst_roll)
    except Exception as e:
        return f"[错误] 施加元素损伤时内部错误: {e}，请主持手动处理目标单位的元素韧性和爆发状态。"


def _apply_elemental_mutations(
    unit: Unit,
    r: ElementalReport,
    amount: int,
    elem_type: str,
    burst_roll: int | None = None,
) -> str:
    if r.invalid_amount:
        return "[错误] 元素损伤必须大于 0"
    if r.invalid_type:
        return f"[错误] 未知元素损伤类型: {elem_type}"
    if r.is_burst_period:
        true_dmg = amount * 3
        msg = _apply_true_damage(unit, true_dmg)
        return f"[爆发期间] {unit.name} 的元素损伤转为 {true_dmg} 点真实伤害\n{msg}"

    result = ""
    if r.barrier_absorbed > 0:
        elem_barrier = unit.get_status("元素屏障")
        if elem_barrier:
            # WIT规则：元素屏障每层吸收1点元素损伤（与物理屏障"每层吸收一次攻击"语义不同，此为官方规则）
            elem_barrier["stacks"] -= r.barrier_absorbed
        result = f"{unit.name} 的元素屏障吸收了 {r.barrier_absorbed} 点{elem_type}"
        if r.barrier_depleted:
            unit.remove_status("元素屏障")
            result += "（元素屏障耗尽）"
        if r.tenacity_reduced <= 0:
            return result

    if r.tenacity_reduced > 0:
        unit.reduce_tenacity(r.tenacity_reduced)
        result += f"\n{unit.name} 受到 {r.tenacity_reduced} 点{elem_type}（韧性: {unit.elemental_tenacity_current}/{unit.elemental_tenacity_max}）"

        if r.burst_triggered:
            burst_msgs = trigger_elemental_burst(unit, elem_type, burst_roll=burst_roll)
            result += "\n" + burst_msgs

            if r.overflow > 0:
                true_dmg = r.overflow * 3
                true_msg = _apply_true_damage(unit, true_dmg)
                result += f"\n[溢出] 超出韧性损伤 {r.overflow} 点转为 {true_dmg} 点真实伤害\n{true_msg}"

    return result.strip()


def trigger_elemental_burst(unit: Unit, elem_type: str, burst_roll: int | None = None) -> str:
    """Trigger a burst and optionally resolve its user-entered auxiliary die."""
    if elem_type not in ELEMENTAL_BURST_EFFECTS:
        return f"未知元素类型: {elem_type}"

    burst_def = ELEMENTAL_BURST_EFFECTS[elem_type]

    unit.elemental_burst = elem_type
    unit.elemental_burst_remaining = 1

    damage_instances = int(burst_def.get("true_dmg_mult", 0))
    sp_note = ""
    if elem_type == "凋亡损伤":
        if unit.current_sp >= 3:
            unit.current_sp -= 3
            sp_note = "失去 3SP"
        else:
            damage_instances += 1
            sp_note = "没有足够SP可失去，爆发真实伤害额外结算一次"

    result = f"!!! {unit.name} 触发了{elem_type}爆发 !!!\n"

    for status_name in burst_def["statuses"]:
        msg2 = apply_status(unit, status_name)
        result += f"  {msg2}\n"

    if sp_note:
        result += f"  [{sp_note}]\n"
    elif burst_def["extra"]:
        result += f"  [{burst_def['extra']}]\n"

    if burst_roll is None:
        unit.pending_rolls.append({
            "kind": "elemental_burst",
            "element_type": elem_type,
            "instances": damage_instances,
            "rule_mode": RuleMode.V1_2.value,
        })
        result += (
            f"  [待填写] 请输入损伤来源的辅助骰结果；"
            f"本次需要结算 {damage_instances} 次等值真实伤害\n"
        )
    else:
        true_damage = burst_roll * damage_instances
        result += (
            f"  辅助骰 {burst_roll} × {damage_instances} 次 = "
            f"{true_damage} 点真实伤害\n"
        )
        result += f"  {_apply_true_damage(unit, true_damage)}\n"

    return result.rstrip()


def resolve_pending_elemental_burst(
    unit: Unit,
    burst_roll: int,
    rule_mode: RuleMode | str = RuleMode.V1_2,
    element_resistance: int = 0,
) -> str:
    """Resolve the oldest burst auxiliary die that the GM left unfilled."""
    if RuleMode.coerce(rule_mode) == RuleMode.V0_3:
        return resolve_pending_elemental_burst_v03(
            unit, burst_roll, element_resistance
        )
    if burst_roll < 0:
        return "[错误] 爆发辅助骰结果不能为负数"

    pending_index = next(
        (
            index
            for index, item in enumerate(unit.pending_rolls)
            if item.get("kind") == "elemental_burst"
        ),
        None,
    )
    if pending_index is None:
        return f"[错误] {unit.name} 没有待结算的元素爆发辅助骰"

    pending = unit.pending_rolls[pending_index]
    instances = max(0, int(pending.get("instances", 0)))
    if instances <= 0:
        return "[错误] 待结算爆发记录已损坏，请主持手动处理"

    true_damage = burst_roll * instances
    damage_msg = _apply_true_damage(unit, true_damage)
    unit.pending_rolls.pop(pending_index)
    element_type = pending.get("element_type", "元素损伤")
    return (
        f"[补充结算] {unit.name} 的{element_type}爆发："
        f"辅助骰 {burst_roll} × {instances} 次 = {true_damage} 点真实伤害\n"
        f"{damage_msg}"
    )


def recover_burst(unit: Unit) -> list[str]:
    msgs = []
    if unit.is_in_burst():
        msgs.append(f"{unit.name} 的「{unit.elemental_burst}爆发」结束")
    unit.recover_tenacity()
    if msgs:
        msgs.append(f"{unit.name} 的元素韧性恢复至 {unit.elemental_tenacity_max}")
    return msgs


# ============================================================
# 状态系统
# ============================================================

def _calc_status(
    unit: Unit,
    status_name: str,
    stacks: int = 0,
    use_resistance: bool = True,
    external: bool = True,
    save_succeeded: bool = False,
) -> StatusReport:
    """纯计算：读 unit 状态，返回 StatusReport，不修改 unit"""
    requested_name = status_name
    status_name = normalize_status_name(status_name)
    report = StatusReport(
        requested_name=requested_name,
        status_name=status_name,
        stacks_delta=stacks,
    )

    definition = STATUS_DEFINITIONS.get(status_name)
    if definition is None:
        report.invalid_status = True
        return report

    if stacks < 0:
        report.invalid_status = True
        return report

    if external and unit.has_status("免疫"):
        report.blocked_by_immune = True
        return report

    if save_succeeded and definition.polarity == "negative":
        report.blocked_by_save = True
        return report

    resist = unit.get_status("抵抗")
    if (
        use_resistance
        and definition.polarity == "negative"
        and resist
        and resist["stacks"] > 0
    ):
        report.blocked_by_resist = True
        report.resist_remaining = resist["stacks"] - 1
        return report

    if status_name == "标记":
        report.is_mark = True
        report.simple_applied = True
        for sub in ["停顿", "寒冷", "困顿"]:
            if sub in STATUS_UPGRADE:
                upgraded = STATUS_UPGRADE[sub]
                if not unit.has_status(upgraded) and unit.has_status(sub):
                    report.mark_sub_triggers.append(f"{sub}→{upgraded}")
        return report

    if status_name in STATUS_UPGRADE:
        upgraded = STATUS_UPGRADE[status_name]
        if unit.has_status(upgraded):
            report.already_exists = True
            return report
        if status_name in MARK_SYNONYMS and unit.has_status("标记"):
            report.upgraded = True
            report.upgraded_from = status_name
            report.upgraded_to = upgraded
            report.mark_consumed = True
            return report
        if unit.has_status(status_name):
            report.upgraded = True
            report.upgraded_from = status_name
            report.upgraded_to = upgraded
            return report
        report.simple_applied = True
        return report

    if status_name in X_STATUSES:
        existing = unit.get_status(status_name)
        if stacks > 0:
            if existing:
                report.stacked = True
                report.stacks_before = existing["stacks"]
                report.stacks_after = existing["stacks"] + stacks
            else:
                report.simple_applied = True
                report.stacks_after = stacks
        else:
            if existing:
                report.stacked = True
                report.stacks_before = existing["stacks"]
                report.stacks_after = existing["stacks"] + 1
                report.stacks_delta = 1
            else:
                report.simple_applied = True
                report.stacks_after = 1
                report.stacks_delta = 1
        return report

    if unit.has_status(status_name):
        report.already_exists = True
        return report

    report.simple_applied = True
    return report


def apply_status(
    unit: Unit,
    status_name: str,
    stacks: int = 0,
    use_resistance: bool = True,
    external: bool = True,
    save_succeeded: bool = False,
    rule_mode: RuleMode | str = RuleMode.V1_2,
) -> str:
    """施加状态效果。带X的状态会叠加层数。"""
    if RuleMode.coerce(rule_mode) == RuleMode.V0_3:
        return apply_status_v03(unit, status_name)
    try:
        report = _calc_status(
            unit,
            status_name,
            stacks,
            use_resistance=use_resistance,
            external=external,
            save_succeeded=save_succeeded,
        )
        _apply_status_mutations(unit, report)
        return _format_status_result(unit, report)
    except Exception as e:
        return f"[错误] 施加状态「{status_name}」时内部错误: {e}，请主持手动处理目标单位的状态。"


def _apply_status_mutations(unit: Unit, r: StatusReport):
    if r.invalid_status or r.blocked_by_immune or r.blocked_by_resist or r.blocked_by_save:
        if r.blocked_by_resist:
            resist = unit.get_status("抵抗")
            if resist:
                resist["stacks"] -= 1
                if resist["stacks"] <= 0:
                    unit.remove_status("抵抗")
        return

    if r.is_mark:
        unit.add_status("标记")
        for trigger in r.mark_sub_triggers:
            sub = trigger.split("→")[0]
            upgraded = trigger.split("→")[1]
            unit.remove_status(sub)
            while unit.has_status(sub):
                unit.remove_status(sub)
            unit.add_status(upgraded)
        if r.mark_sub_triggers:
            unit.remove_status("标记")
        return

    if r.upgraded:
        if r.mark_consumed:
            unit.remove_status("标记")
        unit.remove_status(r.upgraded_from)
        while unit.has_status(r.upgraded_from):
            unit.remove_status(r.upgraded_from)
        unit.add_status(r.upgraded_to)
        return

    if r.stacked:
        existing = unit.get_status(r.status_name)
        if existing:
            existing["stacks"] = r.stacks_after
            if r.status_name == "屏障":
                unit.temp_hp += max(0, r.stacks_delta)
        return

    if r.simple_applied:
        unit.add_status(r.status_name, r.stacks_after)
        if r.status_name == "屏障":
            unit.temp_hp += max(0, r.stacks_after)
        return

    # already_exists → no mutation needed


def _format_status_result(unit: Unit, r: StatusReport) -> str:
    name = unit.name
    sn = r.status_name

    if r.invalid_status:
        return f"[错误] 未知或非法状态: {r.requested_name}"
    if r.blocked_by_immune:
        return f"{name} 的「免疫」阻挡了「{sn}」"
    if r.blocked_by_save:
        return f"{name} 对「{sn}」的豁免检定成功，状态未施加"
    if r.blocked_by_resist:
        return f"{name} 消耗一次「抵抗」无效了「{sn}」（剩余{r.resist_remaining}次）"
    if r.is_mark:
        lines = [f"{name} 获得了「标记」（同时视为停顿/震颤/寒冷/困顿）"]
        for t in r.mark_sub_triggers:
            lines.append(f"  「标记」触发：{t}")
        if r.mark_sub_triggers:
            lines.append("  「标记」已在触发升级后结束")
        return "\n".join(lines)
    if r.upgraded:
        source = "标记" if r.mark_consumed else r.upgraded_from
        return f"{name} 的「{source}」触发升级为「{r.upgraded_to}」！"
    if r.stacked:
        return f"{name} 的「{sn}」层数 +{r.stacks_delta} → 当前 {r.stacks_after} 层"
    if r.simple_applied:
        stacks_text = str(r.stacks_after) if r.stacks_after > 0 else ""
        return f"{name} 获得了「{sn}{stacks_text}」"
    if r.already_exists:
        upgraded_hint = STATUS_UPGRADE.get(sn, "")
        if upgraded_hint:
            return f"{name} 已有「{upgraded_hint}」，「{sn}」不叠加"
        return f"{name} 已有「{sn}」，不重复添加"
    return ""



def process_end_of_turn(
    unit: Unit,
    rule_mode: RuleMode | str = RuleMode.V1_2,
) -> list[str]:
    if RuleMode.coerce(rule_mode) == RuleMode.V0_3:
        return process_end_of_turn_v03(unit)
    had_aftereffect = unit.has_status("失能后效")
    disabled_at_start = unit.has_any_status(["失能", "眩晕", "冻结", "睡眠", "浮空"])
    removed = []
    for status_name in END_OF_TURN_STATUSES:
        if unit.has_status(status_name):
            unit.remove_status(status_name)
            removed.append(status_name)

    msgs = []
    if removed:
        msgs.append(f"{unit.name} 回合结束清除: {'、'.join(removed)}")

    if "失能" in removed:
        unit.add_status("失能后效")
        msgs.append(f"{unit.name} 获得了「失能后效」")

    if had_aftereffect and not disabled_at_start and unit.remove_status("失能后效"):
        msgs.append(f"{unit.name} 在非失能状态下完成回合，「失能后效」结束")

    return msgs


def process_turn_start(
    unit: Unit,
    rule_mode: RuleMode | str = RuleMode.V1_2,
) -> list[str]:
    """Resolve effects that expire at the start of this unit's own turn."""
    if RuleMode.coerce(rule_mode) == RuleMode.V0_3:
        return process_turn_start_v03(unit)
    return recover_burst(unit) if unit.is_in_burst() else []


def process_end_attack(
    unit: Unit,
    rule_mode: RuleMode | str = RuleMode.V1_2,
) -> str:
    if RuleMode.coerce(rule_mode) == RuleMode.V0_3:
        return process_end_attack_v03(unit)
    removed = []
    for name in END_OF_ATTACK_BUFFS:
        if unit.has_status(name):
            unit.remove_status(name)
            removed.append(name)
    if removed:
        return f"{unit.name} 攻击后清除了: {'、'.join(removed)}"
    return ""


def process_end_heal_effect(unit: Unit) -> str:
    removed = []
    for name in END_OF_HEAL_EFFECT_DEBUFFS:
        if unit.has_status(name):
            unit.remove_status(name)
            removed.append(name)
    if removed:
        return f"{unit.name} 治疗后清除了: {'、'.join(removed)}"
    return ""


def process_move_prep(unit: Unit) -> str:
    removed = []
    for name in END_OF_MOVE_PREP:
        if unit.remove_status(name):
            removed.append(name)
    if removed:
        return f"{unit.name} 执行移动预备后清除了: {'、'.join(removed)}"
    return ""


def clear_all_statuses(unit: Unit) -> list[str]:
    removed = unit.status_names()
    unit.status_effects.clear()
    unit.temp_hp = 0
    return removed


def end_turn_cleanup(
    units: list[Unit],
    rule_mode: RuleMode | str = RuleMode.V1_2,
) -> list[str]:
    messages = []
    for u in units:
        msgs = process_end_of_turn(u, rule_mode)
        messages.extend(msgs)
    return messages


def process_round_start(units: list[Unit]) -> list[str]:
    """Compatibility hook. Burst recovery belongs to process_turn_start in v1.2."""
    return []


# ============================================================
# 回合管理
# ============================================================

def advance_turn(state: CombatState, all_units: list[Unit]) -> tuple[CombatState, list[str]]:
    try:
        messages: list[str] = []
        unit_map = {u.unit_id: u for u in all_units}
        current = unit_map.get(state.current_unit_id or "")
        if current is not None:
            messages.extend(process_end_of_turn(current, state.rule_mode))

        _sanitize_turn_order(state, all_units)
        if not state.turn_order:
            return state, ["[提示] 行动顺序为空，请先添加单位并开始战斗。"]

        state.turn += 1
        state.now_index = 0
        _apply_speed_reorder(state, all_units)
        messages.append(f"--- 第 {state.turn} 轮开始 ---")
        incoming = unit_map.get(state.current_unit_id or "")
        if incoming is not None:
            messages.extend(process_turn_start(incoming, state.rule_mode))
        return state, messages
    except Exception as e:
        return state, [f"[错误] 回合推进时内部错误: {e}，请主持手动推进回合并调整行动顺序。"]


def _sanitize_turn_order(state: CombatState, units: list[Unit]) -> None:
    valid_ids = {u.unit_id for u in units}
    seen = set()
    state.turn_order = [
        uid for uid in state.turn_order
        if uid in valid_ids and not (uid in seen or seen.add(uid))
    ]
    if state.turn_order:
        state.now_index = min(max(0, state.now_index), len(state.turn_order) - 1)
    else:
        state.now_index = 0


def _apply_speed_reorder(state: CombatState, units: list[Unit]):
    _sanitize_turn_order(state, units)
    unit_map = {u.unit_id: u for u in units}
    swifts = [uid for uid in state.turn_order
              if unit_map.get(uid) and unit_map[uid].has_status("迅捷")]
    slows = [uid for uid in state.turn_order
             if unit_map.get(uid) and unit_map[uid].has_status("迟缓")]

    if not swifts and not slows:
        return

    overlap = set(swifts) & set(slows)
    if overlap:
        swifts = [u for u in swifts if u not in overlap]
        slows = [u for u in slows if u not in overlap]
        for uid in overlap:
            unit_map[uid].remove_status("迅捷")
            unit_map[uid].remove_status("迟缓")

    middle = [uid for uid in state.turn_order if uid not in set(swifts + slows)]
    for uid in swifts:
        unit_map[uid].remove_status("迅捷")
    for uid in slows:
        unit_map[uid].remove_status("迟缓")
    state.turn_order = swifts + middle + slows


def next_actor(state: CombatState, all_units: list[Unit]) -> tuple[CombatState, list[str]]:
    try:
        messages: list[str] = []
        unit_map = {u.unit_id: u for u in all_units}
        old_order = list(state.turn_order)
        old_index = state.now_index
        old_current_id = (
            old_order[old_index]
            if old_order and 0 <= old_index < len(old_order)
            else None
        )
        current = unit_map.get(old_current_id or "")
        if current is not None:
            messages.extend(process_end_of_turn(current, state.rule_mode))

        valid_ids = {u.unit_id for u in all_units}
        seen = set()
        state.turn_order = [
            uid for uid in old_order
            if uid in valid_ids and not (uid in seen or seen.add(uid))
        ]

        if not state.turn_order:
            return state, ["[提示] 行动顺序为空，请先添加单位并开始战斗。"]

        if old_current_id in state.turn_order:
            next_index = state.turn_order.index(old_current_id) + 1
        else:
            next_id = next((uid for uid in old_order[old_index + 1:] if uid in valid_ids), None)
            next_index = state.turn_order.index(next_id) if next_id in state.turn_order else len(state.turn_order)

        if next_index >= len(state.turn_order):
            state.turn += 1
            state.now_index = 0
            _apply_speed_reorder(state, all_units)
            messages.append(f"--- 第 {state.turn} 轮开始 ---")
        else:
            state.now_index = next_index

        incoming = unit_map.get(state.current_unit_id or "")
        if incoming is not None:
            messages.extend(process_turn_start(incoming, state.rule_mode))
        return state, messages
    except Exception as e:
        return state, [f"[错误] 切换行动时内部错误: {e}，请主持手动切换当前行动单位。"]
