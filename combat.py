"""TRPG 战斗管理器 - 战斗逻辑"""

import random
from models import (
    Unit, CombatState,
    STATUS_UPGRADE, MARK_SYNONYMS,
    END_OF_TURN_STATUSES, END_OF_ATTACK_BUFFS,
    COUNTER_BUFFS, END_OF_HEAL_BUFFS, END_OF_HEAL_EFFECT_DEBUFFS,
    END_OF_ACTIVATION, END_OF_MOVE_PREP,
    ELITE_TENACITY, ELEMENTAL_BURST_EFFECTS,
)

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

def apply_damage(unit: Unit, amount: int, dmg_type: str = "物理",
                 is_attack: bool = True) -> str:
    """造成伤害。dmg_type: "物理" | "法术" | "真实"。辅助骰默认d4。"""
    if amount <= 0:
        return f"{unit.name} 未受到伤害"

    if dmg_type == "真实":
        return _apply_true_damage(unit, amount)

    # 物理/法术 → 先检查护盾
    shield = unit.get_status("护盾")
    if shield and shield["stacks"] > 0:
        shield["stacks"] -= 1
        if shield["stacks"] <= 0:
            unit.remove_status("护盾")
        return f"{unit.name} 的护盾抵消了本次攻击（剩余{shield['stacks']}次）"

    # 计算抗性减免
    resist = unit.physical_resist if dmg_type == "物理" else unit.magic_resist
    # 注意：侵蚀/灼燃爆发额外伤害由骰娘生成后GM手动填入

    final_dmg = max(0, amount - resist)

    # 伤害强化
    dmg_boost = unit.get_status("伤害强化")
    if dmg_boost and dmg_boost["stacks"] > 0:
        final_dmg += dmg_boost["stacks"]

    # 脆弱
    vuln = unit.get_status("脆弱")
    if vuln and vuln["stacks"] > 0:
        final_dmg += vuln["stacks"]

    # 屏障：先扣临时HP，同时减少屏障X计数
    barrier = unit.get_status("屏障")
    if unit.temp_hp > 0:
        absorbed = min(final_dmg, unit.temp_hp)
        unit.temp_hp -= absorbed
        final_dmg -= absorbed
        # 每次屏障生效 → X-1
        if barrier and barrier["stacks"] > 0:
            barrier["stacks"] -= 1
            if barrier["stacks"] <= 0:
                unit.remove_status("屏障")
                unit.temp_hp = 0  # 屏障耗尽，清除剩余临时HP

    unit.current_hp = max(0, unit.current_hp - final_dmg)

    result = f"{unit.name} 受到 {final_dmg} 点{dmg_type}伤害（HP: {unit.current_hp}/{unit.max_hp}"
    if unit.temp_hp > 0:
        result += f", 临时HP: {unit.temp_hp}"
    result += "）"

    # 睡眠因HP受损而结束
    if is_attack and unit.has_status("睡眠"):
        unit.remove_status("睡眠")
        result += f"\n{unit.name} 的「睡眠」因受到攻击而解除"

    # 攻击后处理攻击类BUFF结束
    if is_attack:
        result2 = process_end_attack(unit)
        if result2:
            result += "\n" + result2

    return result


def _apply_true_damage(unit: Unit, amount: int) -> str:
    """真实伤害：无视护盾和抗性，但屏障仍然吸收"""
    if unit.temp_hp > 0:
        absorbed = min(amount, unit.temp_hp)
        unit.temp_hp -= absorbed
        amount -= absorbed
        barrier = unit.get_status("屏障")
        if barrier and barrier["stacks"] > 0:
            barrier["stacks"] -= 1
            if barrier["stacks"] <= 0:
                unit.remove_status("屏障")
                unit.temp_hp = 0

    unit.current_hp = max(0, unit.current_hp - amount)
    return f"{unit.name} 受到 {amount} 点真实伤害（HP: {unit.current_hp}/{unit.max_hp}）"


def apply_healing(unit: Unit, amount: int) -> str:
    """治疗：受禁疗影响则失效，亲和增加d4"""
    if unit.has_status("禁疗"):
        return f"{unit.name} 受到「禁疗」影响，治疗失效"

    # 亲和：治疗来源检定骰面升级（骰娘已计入数值）
    if unit.has_status("亲和"):
        unit.remove_status("亲和")

    old_hp = unit.current_hp
    unit.current_hp = min(unit.max_hp, unit.current_hp + amount)
    healed = unit.current_hp - old_hp

    result = f"{unit.name} 恢复了 {healed} 点生命（HP: {unit.current_hp}/{unit.max_hp}）"

    process_end_heal_effect(unit)

    return result


# ============================================================
# 元素损伤系统
# ============================================================

def apply_elemental_damage(unit: Unit, amount: int, elem_type: str) -> str:
    """施加元素损伤"""

    # 爆发期间 → 3x真实伤害
    if unit.is_in_burst():
        true_dmg = amount * 3
        msg = _apply_true_damage(unit, true_dmg)
        return f"[爆发期间] {unit.name} 的元素损伤转为 {true_dmg} 点真实伤害\n{msg}"

    # 元素屏障：吸收元素损伤
    elem_barrier = unit.get_status("元素屏障")
    if elem_barrier and elem_barrier["stacks"] > 0:
        absorbed = min(amount, elem_barrier["stacks"])
        elem_barrier["stacks"] -= absorbed
        amount -= absorbed
        result = f"{unit.name} 的元素屏障吸收了 {absorbed} 点{elem_type}"
        if elem_barrier["stacks"] <= 0:
            unit.remove_status("元素屏障")
            result += "（元素屏障耗尽）"
        if amount <= 0:
            return result
    else:
        result = ""

    # 正常：减少元素韧性
    overflow = unit.reduce_tenacity(amount)
    result += f"\n{unit.name} 受到 {amount} 点{elem_type}（韧性: {unit.elemental_tenacity_current}/{unit.elemental_tenacity_max}）"

    if unit.elemental_tenacity_current <= 0:
        burst_msgs = trigger_elemental_burst(unit, elem_type)
        result += "\n" + burst_msgs

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

def apply_status(unit: Unit, status_name: str, stacks: int = 0) -> str:
    """
    施加状态效果。带X的状态会叠加层数（如护盾2+护盾3=护盾5）。
    """
    # 免疫
    if unit.has_status("免疫"):
        return f"{unit.name} 的「免疫」阻挡了「{status_name}」"

    # 抵抗
    resist = unit.get_status("抵抗")
    if resist and resist["stacks"] > 0:
        resist["stacks"] -= 1
        if resist["stacks"] <= 0:
            unit.remove_status("抵抗")
        return f"{unit.name} 消耗一次「抵抗」无效了「{status_name}」（剩余{resist['stacks']}次）"

    # 标记特殊处理
    if status_name == "标记":
        return _apply_mark(unit)

    # 升级链
    if status_name in STATUS_UPGRADE:
        upgraded = STATUS_UPGRADE[status_name]
        if unit.has_status(upgraded):
            return f"{unit.name} 已有「{upgraded}」，「{status_name}」不叠加"
        if unit.has_status(status_name):
            unit.remove_status(status_name)
            while unit.has_status(status_name):
                unit.remove_status(status_name)
            unit.add_status(upgraded)
            return f"{unit.name} 的「{status_name}」升级为「{upgraded}」！"
        else:
            unit.add_status(status_name)
            return f"{unit.name} 获得了「{status_name}」"

    # X型状态：叠层（additive stacking）
    X_STATUSES = ["伤害强化", "护盾", "屏障", "抵抗", "元素屏障", "脆弱", "失重"]
    if status_name in X_STATUSES and stacks > 0:
        existing = unit.get_status(status_name)
        if existing:
            existing["stacks"] += stacks
            return f"{unit.name} 的「{status_name}」层数 +{stacks} → 当前 {existing['stacks']} 层"
        else:
            unit.add_status(status_name, stacks)
            return f"{unit.name} 获得了「{status_name}{stacks}」({stacks}层)"
    elif status_name in X_STATUSES:
        # stacks=0 → 施加1层
        existing = unit.get_status(status_name)
        if existing:
            existing["stacks"] += 1
            return f"{unit.name} 的「{status_name}」层数 +1 → 当前 {existing['stacks']} 层"
        else:
            unit.add_status(status_name, 1)
            return f"{unit.name} 获得了「{status_name}1」(1层)"

    # 非X型状态
    if unit.has_status(status_name):
        return f"{unit.name} 已有「{status_name}」，不重复添加"

    unit.add_status(status_name, stacks)
    stacks_text = str(stacks) if stacks > 0 else ""
    return f"{unit.name} 获得了「{status_name}{stacks_text}」"


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
    state.turn += 1
    state.now_index = 0

    msgs = process_round_start(all_units)
    msgs2 = end_turn_cleanup(all_units)

    all_msgs = msgs + msgs2
    all_msgs.append(f"--- 第 {state.turn} 回合开始 ---")

    _apply_speed_reorder(state, all_units)
    return state, all_msgs


def _apply_speed_reorder(state: CombatState, units: list[Unit]):
    unit_map = {u.unit_id: u for u in units}
    swifts = [uid for uid in state.turn_order
              if unit_map.get(uid) and unit_map[uid].has_status("迅捷")]
    slows = [uid for uid in state.turn_order
             if unit_map.get(uid) and unit_map[uid].has_status("迟缓")]

    if not swifts and not slows:
        return

    for uid in swifts:
        state.turn_order.remove(uid)
        unit_map[uid].remove_status("迅捷")
    for uid in slows:
        state.turn_order.remove(uid)
        unit_map[uid].remove_status("迟缓")

    state.turn_order = swifts + state.turn_order + slows


def next_actor(state: CombatState, all_units: list[Unit]) -> tuple[CombatState, list[str]]:
    messages: list[str] = []
    state.now_index += 1

    if state.now_index >= len(state.turn_order):
        state, msgs = advance_turn(state, all_units)
        messages.extend(msgs)
    return state, messages
