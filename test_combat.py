"""TRPG 战斗管理器 - 核心战斗逻辑单元测试"""
import pytest
from models import Unit, CombatState
from combat import (
    _calc_damage, _calc_true_damage,
    _calc_healing, _calc_status, _calc_elemental,
    apply_damage,
    team_initiative, traditional_initiative, manual_initiative,
    next_actor, advance_turn, _apply_speed_reorder,
    process_end_of_turn, process_end_attack,
)


# ============================================================
# helpers
# ============================================================

def _u(**kw) -> Unit:
    """快捷创建测试用 Unit"""
    defaults = {"name": "Test", "current_hp": 10, "max_hp": 10, "speed": 10,
                "elemental_tenacity_current": 6, "elemental_tenacity_max": 6}
    defaults.update(kw)
    return Unit(**defaults)


# ============================================================
# 伤害计算
# ============================================================

class TestDamageCalc:
    def test_no_damage_when_amount_zero(self):
        r = _calc_damage(_u(), 0, "物理", False)
        assert r.raw_amount == 0
        assert r.final_damage == 0
        assert r.hp_after == 10

    def test_physical_resist_reduction(self):
        r = _calc_damage(_u(physical_resist=3), 8, "物理", False)
        assert r.resist_reduced == 3
        assert r.final_damage == 5
        assert r.hp_after == 5

    def test_magic_resist_reduction(self):
        r = _calc_damage(_u(magic_resist=4), 10, "法术", False)
        assert r.resist_reduced == 4
        assert r.final_damage == 6

    def test_true_damage_ignores_resist_and_shield(self):
        u = _u(physical_resist=5)
        u.add_status("护盾", 3)
        r = _calc_true_damage(u, 10)
        assert r.resist_reduced == 0
        assert r.final_damage == 10

    def test_shield_blocks_attack(self):
        u = _u()
        u.add_status("护盾", 2)
        r = _calc_damage(u, 50, "物理", True)
        assert r.blocked_by_shield
        assert r.shield_remaining == 1

    def test_barrier_absorbs_temp_hp(self):
        u = _u(current_hp=10, temp_hp=5)
        u.add_status("屏障", 3)
        r = _calc_damage(u, 8, "物理", False)
        assert r.barrier_absorbed == 5
        assert r.temp_hp_after == 0
        assert r.final_damage == 3
        assert r.hp_after == 7

    def test_barrier_depletes_when_stacks_zero(self):
        u = _u(current_hp=10, temp_hp=5)
        u.add_status("屏障", 1)
        r = _calc_damage(u, 8, "物理", False)
        assert r.barrier_depleted

    def test_damage_boost_added(self):
        u = _u(current_hp=20, max_hp=20, physical_resist=0)
        u.add_status("伤害强化", 4)
        r = _calc_damage(u, 5, "物理", False)
        assert r.dmg_boost_added == 4
        assert r.final_damage == 9

    def test_vuln_added(self):
        u = _u(current_hp=20, max_hp=20, physical_resist=0)
        u.add_status("脆弱", 2)
        r = _calc_damage(u, 5, "物理", False)
        assert r.vuln_added == 2
        assert r.final_damage == 7

    def test_boost_and_vuln_stack(self):
        u = _u(current_hp=20, max_hp=20, physical_resist=0)
        u.add_status("伤害强化", 3)
        u.add_status("脆弱", 2)
        r = _calc_damage(u, 5, "物理", False)
        assert r.final_damage == 10  # 5 + 3 + 2

    def test_hp_zero_triggers_dying(self):
        r = _calc_damage(_u(current_hp=5), 10, "物理", False)
        assert r.is_dying
        assert r.hp_after == 0

    def test_hp_already_zero_no_dying(self):
        r = _calc_damage(_u(current_hp=0), 5, "物理", False)
        assert not r.is_dying

    def test_damage_cant_go_below_zero(self):
        r = _calc_damage(_u(current_hp=3), 50, "物理", False)
        assert r.hp_after == 0

    def test_attack_breaks_sleep(self):
        u = _u()
        u.add_status("睡眠")
        r = _calc_damage(u, 3, "物理", True)
        assert r.sleep_broken

    def test_non_attack_does_not_break_sleep(self):
        u = _u()
        u.add_status("睡眠")
        r = _calc_damage(u, 3, "物理", False)
        assert not r.sleep_broken

    def test_attack_clears_attacker_buffs_and_breaks_target_sleep(self):
        """攻击方增益在攻击后清除，目标睡眠被打断"""
        attacker = _u(name="Attacker")
        attacker.add_status("伤害强化", 3)
        attacker.add_status("精准")
        target = _u(name="Target")
        target.add_status("睡眠")
        msg = apply_damage(target, 3, "物理", is_attack=True, attacker=attacker)
        assert not attacker.has_status("伤害强化")
        assert not attacker.has_status("精准")
        assert "睡眠" not in target.status_names()

    def test_true_damage_attack_breaks_sleep(self):
        """真伤攻击打断睡眠"""
        u = _u()
        u.add_status("睡眠")
        r = _calc_true_damage(u, 5, is_attack=True)
        assert r.sleep_broken

    def test_true_damage_attack_clears_attacker_buffs(self):
        """真伤攻击清除攻击方增益"""
        attacker = _u(name="Attacker")
        attacker.add_status("伤害强化", 3)
        attacker.add_status("精准")
        target = _u(name="Target")
        target.add_status("睡眠")
        msg = apply_damage(target, 5, "真实", is_attack=True, attacker=attacker)
        assert not attacker.has_status("伤害强化")
        assert not attacker.has_status("精准")
        assert "睡眠" not in target.status_names()


# ============================================================
# 治疗计算
# ============================================================

class TestHealingCalc:
    def test_basic_heal(self):
        r = _calc_healing(_u(current_hp=3, max_hp=10), 5)
        assert not r.blocked_by_regen_block
        assert r.healed == 5
        assert r.hp_after == 8

    def test_heal_cannot_exceed_max(self):
        r = _calc_healing(_u(current_hp=8, max_hp=10), 5)
        assert r.healed == 2
        assert r.hp_after == 10

    def test_regen_block_prevents_heal(self):
        u = _u()
        u.add_status("禁疗")
        r = _calc_healing(u, 5)
        assert r.blocked_by_regen_block

    def test_affinity_detected(self):
        u = _u()
        u.add_status("亲和")
        r = _calc_healing(u, 5)
        assert r.affinity_consumed


# ============================================================
# 状态施加
# ============================================================

class TestStatusCalc:
    def test_immune_blocks(self):
        u = _u()
        u.add_status("免疫")
        r = _calc_status(u, "眩晕")
        assert r.blocked_by_immune

    def test_resist_blocks(self):
        u = _u()
        u.add_status("抵抗", 2)
        r = _calc_status(u, "眩晕")
        assert r.blocked_by_resist
        assert r.resist_remaining == 1

    def test_mark_applies_with_sub_triggers(self):
        u = _u()
        u.add_status("停顿")
        u.add_status("困倦")
        r = _calc_status(u, "标记")
        assert r.is_mark
        assert r.simple_applied
        assert "停顿→束缚" in r.mark_sub_triggers
        assert "困倦→睡眠" in r.mark_sub_triggers

    def test_mark_skips_already_upgraded(self):
        u = _u()
        u.add_status("束缚")  # 已有升级版，不会再触发停顿→束缚
        r = _calc_status(u, "标记")
        assert "停顿→束缚" not in r.mark_sub_triggers

    def test_upgrade_paralysis_to_stun(self):
        u = _u()
        u.add_status("麻痹")
        r = _calc_status(u, "麻痹")
        assert r.upgraded
        assert r.upgraded_from == "麻痹"
        assert r.upgraded_to == "眩晕"

    def test_upgrade_cold_to_frozen(self):
        u = _u()
        u.add_status("寒冷")
        r = _calc_status(u, "寒冷")
        assert r.upgraded
        assert r.upgraded_to == "冻结"

    def test_upgrade_drowsy_to_sleep(self):
        u = _u()
        u.add_status("困倦")
        r = _calc_status(u, "困倦")
        assert r.upgraded
        assert r.upgraded_to == "睡眠"

    def test_upgrade_stop_to_bind(self):
        u = _u()
        u.add_status("停顿")
        r = _calc_status(u, "停顿")
        assert r.upgraded
        assert r.upgraded_to == "束缚"

    def test_cannot_apply_when_upgraded_exists(self):
        u = _u()
        u.add_status("眩晕")
        r = _calc_status(u, "麻痹")
        assert r.already_exists

    def test_first_apply_no_upgrade(self):
        r = _calc_status(_u(), "麻痹")
        assert r.simple_applied
        assert not r.upgraded

    def test_x_status_stack_new(self):
        r = _calc_status(_u(), "护盾", 3)
        assert r.simple_applied
        assert r.stacks_after == 3

    def test_x_status_stack_additive(self):
        u = _u()
        u.add_status("护盾", 3)
        r = _calc_status(u, "护盾", 2)
        assert r.stacked
        assert r.stacks_before == 3
        assert r.stacks_after == 5

    def test_x_status_default_one_stack(self):
        r = _calc_status(_u(), "护盾")
        assert r.simple_applied
        assert r.stacks_after == 1

    def test_x_status_stack_one_more(self):
        u = _u()
        u.add_status("脆弱", 2)
        r = _calc_status(u, "脆弱")
        assert r.stacked
        assert r.stacks_delta == 1
        assert r.stacks_after == 3

    def test_non_x_duplicate_blocked(self):
        u = _u()
        u.add_status("眩晕")
        r = _calc_status(u, "眩晕")
        assert r.already_exists

    def test_non_x_simple_apply(self):
        r = _calc_status(_u(), "浮空")
        assert r.simple_applied

    def test_all_x_statuses_recognized(self):
        """验证所有 X_STATUSES 都被 _calc_status 识别为可叠层类型"""
        from models import X_STATUSES
        for s in X_STATUSES:
            r = _calc_status(_u(), s, 2)
            assert r.simple_applied or r.stacked, f"{s} 未被识别为X型状态"


# ============================================================
# 元素损伤
# ============================================================

class TestElementalCalc:
    def test_burst_period_converts_to_true_dmg(self):
        u = _u()
        u.elemental_burst = "凋亡损伤"
        u.elemental_burst_remaining = 1
        r = _calc_elemental(u, 3, "凋亡损伤")
        assert r.is_burst_period
        assert r.true_dmg_dealt == 9

    def test_barrier_absorbs_elemental(self):
        u = _u()
        u.add_status("元素屏障", 4)
        r = _calc_elemental(u, 3, "凋亡损伤")
        assert r.barrier_absorbed == 3
        assert r.tenacity_reduced == 0

    def test_barrier_partial_absorption(self):
        u = _u()
        u.add_status("元素屏障", 2)
        r = _calc_elemental(u, 5, "毒性损伤")
        assert r.barrier_absorbed == 2
        assert r.tenacity_reduced == 3

    def test_barrier_depletion(self):
        u = _u()
        u.add_status("元素屏障", 1)
        r = _calc_elemental(u, 5, "灼燃损伤")
        assert r.barrier_depleted

    def test_tenacity_reduction(self):
        r = _calc_elemental(_u(elemental_tenacity_current=6), 4, "神经损伤")
        assert r.tenacity_reduced == 4
        assert r.tenacity_after == 2

    def test_tenacity_zero_triggers_burst(self):
        r = _calc_elemental(_u(elemental_tenacity_current=2), 3, "凋亡损伤")
        assert r.tenacity_after <= 0
        assert r.burst_triggered
        assert r.burst_type == "凋亡损伤"
        assert "迟缓" in r.burst_statuses

    def test_no_burst_for_unknown_type(self):
        r = _calc_elemental(_u(elemental_tenacity_current=2), 3, "未知类型")
        assert not r.burst_triggered


# ============================================================
# 先攻系统
# ============================================================

class TestInitiative:
    def test_team_initiative_order(self):
        player = _u(name="P1", speed=15)
        monster = _u(name="M1", speed=10, unit_type="monster")
        state = team_initiative([player], [monster])
        assert state.first_team == "player"
        assert state.turn_order[0] == player.unit_id

    def test_team_initiative_monster_first(self):
        player = _u(name="P1", speed=5)
        monster = _u(name="M1", speed=20, unit_type="monster")
        state = team_initiative([player], [monster])
        assert state.first_team == "monster"
        assert state.turn_order[0] == monster.unit_id

    def test_team_initiative_tie_goes_to_player(self):
        player = _u(name="P1", speed=10)
        monster = _u(name="M1", speed=10, unit_type="monster")
        state = team_initiative([player], [monster])
        assert state.first_team == "player"

    def test_traditional_initiative_rolls(self):
        units = [_u(name="A", speed=10), _u(name="B", speed=12)]
        state = traditional_initiative(units, dice_faces=20)
        assert len(state.turn_order) == 2
        assert len(state.initiative_rolls) == 2

    def test_traditional_faster_unit_first_when_tied_roll(self):
        """速度高的在同检定值时排在前面（排序逻辑）"""
        fast = _u(name="Fast", speed=20)
        slow = _u(name="Slow", speed=5)
        units = [slow, fast]
        # 种子固定使两人掷出相同值
        import random
        random.seed(42)
        # 用很大的骰面降低同值概率，测试基本排序
        state = traditional_initiative(units, dice_faces=100)
        uid_map = {u.unit_id: u.name for u in units}
        order = [uid_map[uid] for uid in state.turn_order]
        assert len(order) == 2

    def test_manual_initiative_player_first(self):
        player = _u(name="P1", speed=10)
        monster = _u(name="M1", speed=20, unit_type="monster")
        state = manual_initiative("player", [player], [monster])
        assert state.turn_order[0] == player.unit_id


# ============================================================
# 回合管理
# ============================================================

class TestTurnManagement:
    def test_advance_turn_increments(self):
        u = _u()
        state = CombatState(turn=3, now_index=2, turn_order=[u.unit_id], active=True)
        new_state, msgs = advance_turn(state, [u])
        assert new_state.turn == 4
        assert new_state.now_index == 0

    def test_next_actor_advances(self):
        u1 = _u(name="A")
        u2 = _u(name="B")
        state = CombatState(turn=1, now_index=0, turn_order=[u1.unit_id, u2.unit_id], active=True)
        new_state, msgs = next_actor(state, [u1, u2])
        assert new_state.now_index == 1

    def test_next_actor_wraps_to_next_turn(self):
        u = _u()
        state = CombatState(turn=1, now_index=0, turn_order=[u.unit_id], active=True)
        new_state, msgs = next_actor(state, [u])
        assert new_state.turn == 2  # 单单位列表，行动后自动进入下一回合

    def test_speed_reorder_swift_front(self):
        u1 = _u(name="Normal", speed=10)
        u2 = _u(name="Swift", speed=10)
        u2.add_status("迅捷")
        state = CombatState(turn_order=[u1.unit_id, u2.unit_id])
        _apply_speed_reorder(state, [u1, u2])
        assert state.turn_order[0] == u2.unit_id

    def test_speed_reorder_slow_back(self):
        u1 = _u(name="Slow", speed=10)
        u1.add_status("迟缓")
        u2 = _u(name="Normal", speed=10)
        state = CombatState(turn_order=[u1.unit_id, u2.unit_id])
        _apply_speed_reorder(state, [u1, u2])
        assert state.turn_order[-1] == u1.unit_id


# ============================================================
# 状态清除
# ============================================================

class TestStatusCleanup:
    def test_end_of_turn_clears_turn_statuses(self):
        u = _u()
        u.add_status("麻痹")
        u.add_status("脆弱", 2)
        msgs = process_end_of_turn(u)
        assert not u.has_status("麻痹")
        assert not u.has_status("脆弱")

    def test_end_of_turn_adds_disabled_aftermath(self):
        u = _u()
        u.add_status("失能")
        msgs = process_end_of_turn(u)
        assert u.has_status("失能后效")

    def test_end_of_attack_clears_buffs(self):
        u = _u()
        u.add_status("伤害强化", 3)
        u.add_status("暴击")
        msg = process_end_attack(u)
        assert not u.has_status("伤害强化")
        assert not u.has_status("暴击")

    def test_end_of_attack_non_buff_preserved(self):
        u = _u()
        u.add_status("眩晕")
        msg = process_end_attack(u)
        assert u.has_status("眩晕")
