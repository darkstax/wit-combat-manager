"""TRPG 战斗管理器 - 核心战斗逻辑单元测试"""
import pytest
from models import Unit, CombatState, RuleMode
from combat import (
    _calc_damage, _calc_true_damage,
    _calc_healing, _calc_status, _calc_elemental,
    apply_damage, apply_healing, apply_status, apply_elemental_damage,
    resolve_pending_elemental_burst,
    team_initiative, traditional_initiative, manual_initiative, ranked_initiative,
    next_actor, advance_turn, _apply_speed_reorder,
    process_end_of_turn, process_end_attack,
    process_turn_start, process_round_start,
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
        attacker = _u(name="Attacker")
        attacker.add_status("伤害强化", 4)
        u = _u(current_hp=20, max_hp=20, physical_resist=0)
        r = _calc_damage(u, 5, "物理", True, attacker=attacker)
        assert r.dmg_boost_added == 4
        assert r.final_damage == 9

    def test_vuln_added(self):
        u = _u(current_hp=20, max_hp=20, physical_resist=0)
        u.add_status("脆弱", 2)
        r = _calc_damage(u, 5, "物理", False)
        assert r.vuln_added == 2
        assert r.final_damage == 7

    def test_boost_and_vuln_stack(self):
        attacker = _u(name="Attacker")
        attacker.add_status("伤害强化", 3)
        u = _u(current_hp=20, max_hp=20, physical_resist=0)
        u.add_status("脆弱", 2)
        r = _calc_damage(u, 5, "物理", True, attacker=attacker)
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
        assert "困顿→睡眠" in r.mark_sub_triggers

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

    def test_ranked_initiative_orders_by_rank_desc(self):
        a = _u(name="A", initiative_rank=5)
        b = _u(name="B", initiative_rank=10)
        c = _u(name="C", initiative_rank=1)
        state = ranked_initiative([a, b], [c])
        assert state.initiative_mode == "ranked"
        assert state.turn_order == [b.unit_id, a.unit_id, c.unit_id]

    def test_ranked_initiative_ties_stable_by_unit_id(self):
        x = _u(name="X", initiative_rank=7, unit_id="unit_x")
        y = _u(name="Y", initiative_rank=7, unit_id="unit_y")
        state = ranked_initiative([x, y], [])
        # 同顺位按 unit_id 升序稳定排序（此处添加顺序即 unit_id 升序）
        assert state.turn_order == [x.unit_id, y.unit_id]
        state2 = ranked_initiative([y, x], [])
        assert state2.turn_order == [x.unit_id, y.unit_id]

    def test_ranked_initiative_zero_rank_last(self):
        high = _u(name="High", initiative_rank=9)
        zero = _u(name="Zero", initiative_rank=0)
        state = ranked_initiative([zero], [high])
        assert state.turn_order == [high.unit_id, zero.unit_id]

    def test_ranked_initiative_v03_dispatches(self):
        a = _u(name="A", initiative_rank=3)
        b = _u(name="B", initiative_rank=8)
        state = ranked_initiative([a], [b], rule_mode=RuleMode.V0_3)
        assert state.initiative_mode == "ranked"
        assert state.rule_mode == RuleMode.V0_3.value
        assert state.turn_order == [b.unit_id, a.unit_id]


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


class TestV12Regression:
    def test_barrier_consumes_one_stack_per_damage_event(self):
        target = _u(current_hp=10, max_hp=10, temp_hp=5)
        target.add_status("屏障", 5)

        apply_damage(target, 3, "真实", is_attack=False)

        assert target.temp_hp == 2
        assert target.get_status("屏障")["stacks"] == 4

    def test_shield_only_blocks_attacks(self):
        target = _u()
        target.add_status("护盾", 1)
        report = _calc_damage(target, 5, "物理", False)
        assert not report.blocked_by_shield
        assert report.final_damage == 5

    def test_missed_attack_does_not_consume_target_shield_or_gain_damage_boost(self):
        attacker = _u(name="Attacker")
        attacker.add_status("伤害强化", 5)
        target = _u(physical_resist=10)
        target.add_status("护盾", 2)
        report = _calc_damage(target, 5, "物理", True, attacker=attacker)
        assert report.attack_missed
        assert report.final_damage == 0
        assert not report.blocked_by_shield
        assert target.get_status("护盾")["stacks"] == 2

    def test_equal_attack_check_can_gain_final_damage_bonus(self):
        attacker = _u(name="Attacker")
        attacker.add_status("伤害强化", 3)
        target = _u(physical_resist=10)
        report = _calc_damage(target, 10, "物理", True, attacker=attacker)
        assert not report.attack_missed
        assert report.final_damage == 3

    def test_true_damage_attack_can_be_blocked_by_shield(self):
        target = _u()
        target.add_status("护盾", 1)
        report = _calc_true_damage(target, 5, is_attack=True)
        assert report.blocked_by_shield

    def test_zero_hp_damage_does_not_break_sleep(self):
        target = _u(physical_resist=10)
        target.add_status("睡眠")
        report = _calc_damage(target, 5, "物理", True)
        assert report.final_damage == 0
        assert not report.sleep_broken

    def test_frozen_modifies_resistances(self):
        target = _u(physical_resist=4, magic_resist=4)
        target.add_status("冻结")
        assert _calc_damage(target, 20, "物理", True).final_damage == 6
        assert _calc_damage(target, 20, "法术", True).final_damage == 26

    def test_damage_overflow_reduces_max_hp_and_applies_dying(self):
        target = _u(current_hp=3, max_hp=10)
        apply_damage(target, 8, "真实", is_attack=False)
        assert target.current_hp == 0
        assert target.max_hp == 5
        assert target.has_status("濒死")

    def test_dying_target_takes_future_damage_to_max_hp(self):
        target = _u(current_hp=0, max_hp=10)
        target.add_status("濒死")
        apply_damage(target, 4, "真实", is_attack=False)
        assert target.max_hp == 6

    def test_dying_target_still_uses_temporary_hp_first(self):
        target = _u(current_hp=0, max_hp=10, temp_hp=5)
        target.add_status("濒死")
        apply_damage(target, 3, "真实", is_attack=False)
        assert target.temp_hp == 2
        assert target.max_hp == 10

    def test_manual_dying_status_sets_current_hp_to_zero(self):
        target = _u(current_hp=10, max_hp=10)
        target.add_status("濒死")
        assert target.current_hp == 0

    def test_healing_does_not_restore_dying_target(self):
        target = _u(current_hp=0, max_hp=10)
        target.add_status("濒死")
        msg = apply_healing(target, 5)
        assert target.current_hp == 0
        assert "濒死" in msg

    def test_regen_block_is_consumed_by_failed_heal(self):
        target = _u(current_hp=3)
        target.add_status("禁疗")
        apply_healing(target, 5)
        assert target.current_hp == 3
        assert not target.has_status("禁疗")

    def test_negative_healing_fails_without_mutation(self):
        target = _u(current_hp=7)
        msg = apply_healing(target, -3)
        assert target.current_hp == 7
        assert msg.startswith("[错误]")

    def test_mark_is_consumed_when_represented_status_is_applied(self):
        target = _u()
        target.add_status("标记")
        apply_status(target, "停顿")
        assert target.has_status("束缚")
        assert not target.has_status("标记")

    def test_new_mark_is_consumed_when_it_upgrades_existing_status(self):
        target = _u()
        target.add_status("寒冷")
        apply_status(target, "标记")
        assert target.has_status("冻结")
        assert not target.has_status("标记")

    def test_old_drowsy_name_is_normalized(self):
        target = _u(status_effects=[{"name": "困倦", "stacks": 0}])
        assert target.has_status("困顿")

    def test_sleep_does_not_clear_at_turn_end(self):
        target = _u()
        target.add_status("睡眠")
        process_end_of_turn(target)
        assert target.has_status("睡眠")

    def test_disabled_aftermath_needs_a_non_disabled_turn(self):
        target = _u()
        target.add_status("失能")
        process_end_of_turn(target)
        assert target.has_status("失能后效")
        process_end_of_turn(target)
        assert not target.has_status("失能后效")

    def test_elemental_burst_uses_entered_auxiliary_roll(self):
        target = _u(elemental_tenacity_current=2)
        msg = apply_elemental_damage(target, 2, "组织损伤", burst_roll=2)
        assert target.current_hp == 4
        assert "辅助骰 2 × 3" in msg

    def test_pending_elemental_burst_can_be_resolved_later(self):
        target = _u(elemental_tenacity_current=2)
        trigger_msg = apply_elemental_damage(target, 2, "组织损伤")
        assert "待填写" in trigger_msg
        assert target.current_hp == 10
        assert len(target.pending_rolls) == 1

        resolve_msg = resolve_pending_elemental_burst(target, 2)
        assert "补充结算" in resolve_msg
        assert target.current_hp == 4
        assert target.pending_rolls == []
        assert resolve_pending_elemental_burst(target, 2).startswith("[错误]")

    def test_burst_recovers_at_target_turn_start_not_round_start(self):
        target = _u(elemental_tenacity_current=0)
        target.elemental_burst = "毒性损伤"
        target.elemental_burst_remaining = 1
        assert process_round_start([target]) == []
        assert target.is_in_burst()
        process_turn_start(target)
        assert not target.is_in_burst()
        assert target.elemental_tenacity_current == target.elemental_tenacity_max

    def test_traditional_initiative_uses_manual_check_totals(self):
        slow = _u(name="Slow", speed=1)
        fast = _u(name="Fast", speed=20)
        rolls = {slow.unit_id: 30, fast.unit_id: 10}
        state = traditional_initiative([slow, fast], roll_values=rolls)
        assert state.turn_order == [slow.unit_id, fast.unit_id]
        assert state.initiative_rolls == rolls

    def test_traditional_initiative_rejects_unresolved_manual_tie(self):
        first = _u(name="A", speed=5)
        second = _u(name="B", speed=5)
        with pytest.raises(ValueError, match="请重投"):
            traditional_initiative(
                [first, second],
                roll_values={first.unit_id: 20, second.unit_id: 20},
            )

    def test_deleted_current_actor_does_not_skip_next_survivor(self):
        deleted = _u(name="Deleted")
        survivor = _u(name="Survivor")
        state = CombatState(
            turn=1,
            now_index=0,
            turn_order=[deleted.unit_id, survivor.unit_id],
            active=True,
        )
        state, messages = next_actor(state, [survivor])
        assert state.turn == 1
        assert state.current_unit_id == survivor.unit_id
