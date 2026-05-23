"""TRPG 战斗管理器 - 战斗逻辑"""

import random
from models import (
    Unit, CombatState,
    STATUS_UPGRADE, MARK_SYNONYMS,
    END_OF_TURN_STATUSES, END_OF_ATTACK_BUFFS,
    COUNTER_BUFFS, END_OF_HEAL_BUFFS, END_OF_HEAL_EFFECT_DEBUFFS,
    END_OF_ACTIVATION, END_OF_MOVE_PREP,
    ELITE_TENACITY, ELEMENTAL_BURST_EFFECTS,
    X_STATUSES,
)
from combat_report import DamageReport, HealingReport, StatusReport, ElementalReport

# ============================================================
# 先攻系统
# ============================================================

def team_initiative(players: list[Unit], monsters: list[Unit]) -> CombatState:
    state = CombatState(initiative_mode="team", active=True)

    def team_score(units: list[Unit]) -> int:
        if not units:
            return 0
        speeds = [u.speed for u in units]
        return max(speeds) + min(speeds) if len(speeds) >= 2 else speeds[0] * 2

    player_score = team_score(players)
    monster_score = team_score(monsters)

    players_sorted = sorted(players, key=lambda u: u.speed, reverse=True)
    monsters_sorted = sorted(monsters, key=lambda u: u.speed, reverse=True)

    if player_score >= monster_score:
        state.first_team = "player"
        state.turn_order = [u.unit_id for u in players_sorted + monsters_sorted]
    else:
        state.first_team = "monster"
        state.turn_order = [u.unit_id for u in monsters_sorted + players_sorted]

    return state


def manual_initiative(first_team: str, players: list[Unit], monsters: list[Unit]) -> CombatState:
    state = CombatState(initiative_mode="manual", active=True)
    state.first_team = first_team

    players_sorted = sorted(players, key=lambda u: u.speed, reverse=True)
    monsters_sorted = sorted(monsters, key=lambda u: u.speed, reverse=True)

    if first_team == "player":
        state.turn_order = [u.unit_id for u in players_sorted + monsters_sorted]
    else:
        state.turn_order = [u.unit_id for u in monsters_sorted + players_sorted]

    return state


def traditional_initiative(units: list[Unit], dice_faces: int = 20) -> CombatState:
    state = CombatState(initiative_mode="traditional", active=True)
    rolls: dict[str, int] = {}

    def roll_unit(u: Unit) -> int:
        return random.randint(1, dice_faces) + u.speed

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

def _calc_damage(unit: Unit, amount: int, dmg_type: str, is_attack: bool) -> DamageReport:
    """纯计算：读 unit 状态，返回 DamageReport，不修改 unit"""
    report = DamageReport(raw_amount=amount, hp_before=unit.current_hp, hp_after=unit.current_hp)

    if amount <= 0:
        return report

    # 护盾
    shield = unit.get_status("护盾")
    if shield and shield["stacks"] > 0:
        report.blocked_by_shield = True
        report.shield_remaining = shield["stacks"] - 1
        return report

    # 抗性减免
    resist = unit.physical_resist if dmg_type == "物理" else unit.magic_resist
    report.resist_reduced = resist
    final_dmg = max(0, amount - resist)

    # 伤害强化
    dmg_boost = unit.get_status("伤害强化")
    if dmg_boost and dmg_boost["stacks"] > 0:
        report.dmg_boost_added = dmg_boost["stacks"]
        final_dmg += dmg_boost["stacks"]

    # 脆弱
    vuln = unit.get_status("脆弱")
    if vuln and vuln["stacks"] > 0:
        report.vuln_added = vuln["stacks"]
        final_dmg += vuln["stacks"]

    # 屏障吸收临时HP
    barrier = unit.get_status("屏障")
    if unit.temp_hp > 0:
        absorbed = min(final_dmg, unit.temp_hp)
        report.barrier_absorbed = absorbed
        report.temp_hp_after = unit.temp_hp - absorbed
        final_dmg -= absorbed
        if barrier and barrier["stacks"] > 0:
            if barrier["stacks"] - 1 <= 0:
                report.barrier_depleted = True
    else:
        report.temp_hp_after = unit.temp_hp

    report.final_damage = final_dmg
    report.hp_before = unit.current_hp
    report.hp_after = max(0, unit.current_hp - final_dmg)
    report.is_dying = (report.hp_before > 0 and report.hp_after == 0)

    if is_attack and unit.has_status("睡眠"):
        report.sleep_broken = True

    return report


def _calc_true_damage(unit: Unit, amount: int) -> DamageReport:
    """纯计算：真实伤害，不修改 unit"""
    report = DamageReport(raw_amount=amount, resist_reduced=0)
    final_dmg = amount

    barrier = unit.get_status("屏障")
    if unit.temp_hp > 0:
        absorbed = min(final_dmg, unit.temp_hp)
        report.barrier_absorbed = absorbed
        report.temp_hp_after = unit.temp_hp - absorbed
        final_dmg -= absorbed
        if barrier and barrier["stacks"] > 0:
            if barrier["stacks"] - 1 <= 0:
                report.barrier_depleted = True
    else:
        report.temp_hp_after = unit.temp_hp

    report.final_damage = final_dmg
    report.hp_before = unit.current_hp
    report.hp_after = max(0, unit.current_hp - final_dmg)
    report.is_dying = (report.hp_before > 0 and report.hp_after == 0)

    return report


def apply_damage(unit: Unit, amount: int, dmg_type: str = "物理",
                 is_attack: bool = True, attacker: Unit | None = None) -> str:
    """造成伤害。dmg_type: "物理" | "法术" | "真实"。"""
    try:
        if amount <= 0:
            return f"{unit.name} 未受到伤害"

        if dmg_type == "真实":
            report = _calc_true_damage(unit, amount)
            _apply_true_damage_mutations(unit, report)
            return _format_true_damage_result(unit, report)
        else:
            report = _calc_damage(unit, amount, dmg_type, is_attack)
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
    """根据 DamageReport 对 unit 执行状态变更"""
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
            # WIT规则：屏障每层吸收一次攻击（不论伤害量），而非按伤害点数递减
            barrier["stacks"] -= 1
            if r.barrier_depleted:
                unit.remove_status("屏障")
                unit.temp_hp = 0

    unit.current_hp = r.hp_after

    if r.sleep_broken:
        unit.remove_status("睡眠")



def _format_damage_result(unit: Unit, r: DamageReport, dmg_type: str) -> str:
    if r.blocked_by_shield:
        return f"{unit.name} 的护盾抵消了本次攻击（剩余{r.shield_remaining}次）"

    result = f"{unit.name} 受到 {r.final_damage} 点{dmg_type}伤害（HP: {r.hp_after}/{unit.max_hp}"
    if unit.temp_hp > 0:
        result += f", 临时HP: {unit.temp_hp}"
    result += "）"

    if r.is_dying:
        result += f"\n!!! {unit.name} HP归零，陷入濒死状态 !!!"
    if r.sleep_broken:
        result += f"\n{unit.name} 的「睡眠」因受到攻击而解除"

    return result


def _apply_true_damage(unit: Unit, amount: int) -> str:
    """真实伤害：无视护盾和抗性，但屏障仍然吸收（保留兼容，内部委托）"""
    report = _calc_true_damage(unit, amount)
    _apply_true_damage_mutations(unit, report)
    return _format_true_damage_result(unit, report)


def _apply_true_damage_mutations(unit: Unit, r: DamageReport):
    if r.barrier_absorbed > 0:
        unit.temp_hp = r.temp_hp_after
        barrier = unit.get_status("屏障")
        if barrier:
            # WIT规则：屏障每层吸收一次攻击（不论伤害量），而非按伤害点数递减
            barrier["stacks"] -= 1
            if r.barrier_depleted:
                unit.remove_status("屏障")
                unit.temp_hp = 0
    unit.current_hp = r.hp_after


def _format_true_damage_result(unit: Unit, r: DamageReport) -> str:
    msg = f"{unit.name} 受到 {r.final_damage} 点真实伤害（HP: {r.hp_after}/{unit.max_hp}）"
    if r.is_dying:
        msg += f"\n!!! {unit.name} HP归零，陷入濒死状态 !!!"
    return msg


def _calc_healing(unit: Unit, amount: int) -> HealingReport:
    """纯计算：读 unit 状态，不修改 unit"""
    report = HealingReport()

    if unit.has_status("禁疗"):
        report.blocked_by_regen_block = True
        return report

    if unit.has_status("亲和"):
        report.affinity_consumed = True

    report.hp_before = unit.current_hp
    report.hp_after = min(unit.max_hp, unit.current_hp + amount)
    report.healed = report.hp_after - report.hp_before
    report.heal_effect_cleared = [s for s in END_OF_HEAL_EFFECT_DEBUFFS if unit.has_status(s)]

    return report


def apply_healing(unit: Unit, amount: int) -> str:
    """治疗：受禁疗影响则失效，亲和增加d4"""
    try:
        report = _calc_healing(unit, amount)
        _apply_healing_mutations(unit, report)
        return _format_healing_result(unit, report)
    except Exception as e:
        return f"[错误] 施加治疗时内部错误: {e}，请主持手动处理目标单位的HP。"


def _apply_healing_mutations(unit: Unit, r: HealingReport):
    if r.blocked_by_regen_block:
        return
    if r.affinity_consumed:
        unit.remove_status("亲和")
    unit.current_hp = r.hp_after
    for name in r.heal_effect_cleared:
        unit.remove_status(name)


def _format_healing_result(unit: Unit, r: HealingReport) -> str:
    if r.blocked_by_regen_block:
        return f"{unit.name} 受到「禁疗」影响，治疗失效"
    return f"{unit.name} 恢复了 {r.healed} 点生命（HP: {r.hp_after}/{unit.max_hp}）"


# ============================================================
# 元素损伤系统
# ============================================================

def _calc_elemental(unit: Unit, amount: int, elem_type: str) -> ElementalReport:
    """纯计算：读 unit 状态，不修改 unit"""
    report = ElementalReport()

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


def apply_elemental_damage(unit: Unit, amount: int, elem_type: str) -> str:
    """施加元素损伤"""
    try:
        report = _calc_elemental(unit, amount, elem_type)
        return _apply_elemental_mutations(unit, report, amount, elem_type)
    except Exception as e:
        return f"[错误] 施加元素损伤时内部错误: {e}，请主持手动处理目标单位的元素韧性和爆发状态。"


def _apply_elemental_mutations(unit: Unit, r: ElementalReport, amount: int, elem_type: str) -> str:
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
            burst_msgs = trigger_elemental_burst(unit, elem_type)
            result += "\n" + burst_msgs

            if r.overflow > 0:
                true_dmg = r.overflow * 3
                true_msg = _apply_true_damage(unit, true_dmg)
                result += f"\n[溢出] 超出韧性损伤 {r.overflow} 点转为 {true_dmg} 点真实伤害\n{true_msg}"

    return result.strip()


def trigger_elemental_burst(unit: Unit, elem_type: str) -> str:
    """触发元素爆发：施加状态 + 提示GM手动输入真实伤害"""
    if elem_type not in ELEMENTAL_BURST_EFFECTS:
        return f"未知元素类型: {elem_type}"

    burst_def = ELEMENTAL_BURST_EFFECTS[elem_type]

    unit.elemental_burst = elem_type
    unit.elemental_burst_remaining = 1

    result = f"!!! {unit.name} 触发了{elem_type}爆发 !!!\n"
    result += f"  造成了{elem_type}爆发，请额外输入造成的伤害\n"

    for status_name in burst_def["statuses"]:
        msg2 = apply_status(unit, status_name)
        result += f"  {msg2}\n"

    if burst_def["extra"]:
        result += f"  [{burst_def['extra']}]\n"

    return result


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

def _calc_status(unit: Unit, status_name: str, stacks: int = 0) -> StatusReport:
    """纯计算：读 unit 状态，返回 StatusReport，不修改 unit"""
    report = StatusReport(status_name=status_name, stacks_delta=stacks)

    if unit.has_status("免疫"):
        report.blocked_by_immune = True
        return report

    resist = unit.get_status("抵抗")
    if resist and resist["stacks"] > 0:
        report.blocked_by_resist = True
        report.resist_remaining = resist["stacks"] - 1
        return report

    if status_name == "标记":
        report.is_mark = True
        report.simple_applied = True
        for sub in ["停顿", "寒冷", "困倦"]:
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


def apply_status(unit: Unit, status_name: str, stacks: int = 0) -> str:
    """施加状态效果。带X的状态会叠加层数。"""
    try:
        report = _calc_status(unit, status_name, stacks)
        _apply_status_mutations(unit, report)
        return _format_status_result(unit, report)
    except Exception as e:
        return f"[错误] 施加状态「{status_name}」时内部错误: {e}，请主持手动处理目标单位的状态。"


def _apply_status_mutations(unit: Unit, r: StatusReport):
    if r.blocked_by_immune or r.blocked_by_resist:
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
        return

    if r.upgraded:
        unit.remove_status(r.upgraded_from)
        while unit.has_status(r.upgraded_from):
            unit.remove_status(r.upgraded_from)
        unit.add_status(r.upgraded_to)
        return

    if r.stacked:
        existing = unit.get_status(r.status_name)
        if existing:
            existing["stacks"] = r.stacks_after
        return

    if r.simple_applied:
        unit.add_status(r.status_name, r.stacks_after)
        return

    # already_exists → no mutation needed


def _format_status_result(unit: Unit, r: StatusReport) -> str:
    name = unit.name
    sn = r.status_name

    if r.blocked_by_immune:
        return f"{name} 的「免疫」阻挡了「{sn}」"
    if r.blocked_by_resist:
        return f"{name} 消耗一次「抵抗」无效了「{sn}」（剩余{r.resist_remaining}次）"
    if r.is_mark:
        lines = [f"{name} 获得了「标记」（同时视为停顿/震颤/寒冷/困倦）"]
        for t in r.mark_sub_triggers:
            lines.append(f"  「标记」触发：{t}")
        return "\n".join(lines)
    if r.upgraded:
        return f"{name} 的「{r.upgraded_from}」升级为「{r.upgraded_to}」！"
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


def _apply_mark(unit: Unit) -> str:
    messages = []
    unit.add_status("标记")
    messages.append(f"{unit.name} 获得了「标记」（同时视为停顿/震颤/寒冷/困倦）")

    for sub in ["停顿", "寒冷", "困倦"]:
        if sub in STATUS_UPGRADE:
            upgraded = STATUS_UPGRADE[sub]
            if unit.has_status(upgraded):
                continue
            if unit.has_status(sub):
                unit.remove_status(sub)
                while unit.has_status(sub):
                    unit.remove_status(sub)
                unit.add_status(upgraded)
                messages.append(f"  「标记」触发：{sub} → {upgraded}")

    return "\n".join(messages)


def process_end_of_turn(unit: Unit) -> list[str]:
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

    return msgs


def process_end_attack(unit: Unit) -> str:
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


def clear_all_statuses(unit: Unit) -> list[str]:
    removed = unit.status_names()
    unit.status_effects.clear()
    return removed


def end_turn_cleanup(units: list[Unit]) -> list[str]:
    messages = []
    for u in units:
        msgs = process_end_of_turn(u)
        messages.extend(msgs)
    return messages


def process_round_start(units: list[Unit]) -> list[str]:
    messages = []
    for u in units:
        msgs = recover_burst(u)
        messages.extend(msgs)
    return messages


# ============================================================
# 回合管理
# ============================================================

def advance_turn(state: CombatState, all_units: list[Unit]) -> tuple[CombatState, list[str]]:
    try:
        state.turn += 1
        state.now_index = 0

        msgs = process_round_start(all_units)
        msgs2 = end_turn_cleanup(all_units)

        all_msgs = msgs + msgs2
        all_msgs.append(f"--- 第 {state.turn} 回合开始 ---")

        _apply_speed_reorder(state, all_units)
        return state, all_msgs
    except Exception as e:
        return state, [f"[错误] 回合推进时内部错误: {e}，请主持手动推进回合并调整行动顺序。"]


def _apply_speed_reorder(state: CombatState, units: list[Unit]):
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

    for uid in swifts:
        state.turn_order.remove(uid)
        unit_map[uid].remove_status("迅捷")
    for uid in slows:
        state.turn_order.remove(uid)
        unit_map[uid].remove_status("迟缓")

    state.turn_order = swifts + state.turn_order + slows


def next_actor(state: CombatState, all_units: list[Unit]) -> tuple[CombatState, list[str]]:
    try:
        messages: list[str] = []
        valid_ids = {u.unit_id for u in all_units}
        state.turn_order = [uid for uid in state.turn_order if uid in valid_ids]
        state.now_index += 1

        if state.now_index >= len(state.turn_order):
            state, msgs = advance_turn(state, all_units)
            messages.extend(msgs)
        return state, messages
    except Exception as e:
        return state, [f"[错误] 切换行动时内部错误: {e}，请主持手动切换当前行动单位。"]
