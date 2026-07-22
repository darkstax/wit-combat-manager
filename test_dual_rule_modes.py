import json

import pytest

from combat import (
    apply_damage,
    apply_elemental_damage,
    apply_status,
    resolve_pending_elemental_burst,
    traditional_initiative,
)
from models import CombatState, RuleMode, Unit
from persistence import load_rosters, save_rosters


def _v03_unit(**overrides) -> Unit:
    values = {
        "name": "测试单位",
        "current_hp": 30,
        "max_hp": 30,
        "initial_max_hp": 30,
        "speed": 10,
        "reaction_mobility": 50,
        "elemental_tenacity_current": 10,
        "elemental_tenacity_max": 10,
    }
    values.update(overrides)
    return Unit(**values)


def test_rule_mode_coercion_and_state_normalization():
    assert RuleMode.coerce("v0.3") is RuleMode.V0_3
    assert RuleMode.coerce("12") is RuleMode.V1_2
    assert RuleMode.V0_3.display_name == "行于泰拉 v0.3"
    assert CombatState(rule_mode=RuleMode.V0_3).rule_mode == "0.3"

    with pytest.raises(ValueError, match="未知规则版本"):
        RuleMode.coerce("2.0")


def test_unit_dual_mode_fields_and_pending_roll_round_trip():
    unit = Unit(
        name="先锋",
        reaction_mobility=63,
        current_stamina=4,
        max_stamina=7,
        effect_die="D+",
        auxiliary_die="D2",
        profession="先锋",
        subprofession="冲锋手",
        level=8,
        pending_rolls=[{
            "kind": "v03_elemental_burst",
            "element_type": "灼燃损伤",
            "instances": 1,
            "rule_mode": RuleMode.V0_3.value,
        }],
    )

    loaded = Unit.from_dict(unit.to_dict())

    assert loaded.reaction_mobility == 63
    assert (loaded.current_stamina, loaded.max_stamina) == (4, 7)
    assert (loaded.effect_die, loaded.auxiliary_die) == ("D+", "D2")
    assert (loaded.profession, loaded.subprofession, loaded.level) == ("先锋", "冲锋手", 8)
    assert loaded.pending_rolls == unit.pending_rolls


def test_separate_rosters_round_trip_without_cross_version_leakage(tmp_path):
    path = tmp_path / "units.json"
    rosters = {
        RuleMode.V0_3.value: [Unit(name="旧版角色", reaction_mobility=72)],
        RuleMode.V1_2.value: [Unit(name="新版角色", profession="近卫")],
    }

    save_rosters(rosters, RuleMode.V0_3, str(path))
    store = load_rosters(str(path))

    assert store.active_rule_mode == RuleMode.V0_3.value
    assert [unit.name for unit in store.units_for(RuleMode.V0_3)] == ["旧版角色"]
    assert [unit.name for unit in store.units_for(RuleMode.V1_2)] == ["新版角色"]
    assert store.units_for(RuleMode.V0_3) is not store.units_for(RuleMode.V1_2)

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert set(payload["rosters"]) == {"0.3", "1.2"}


@pytest.mark.parametrize(
    ("legacy_payload", "warning_fragment"),
    [
        ([Unit(name="列表旧档").to_dict()], "旧格式单位列表"),
        ({"units": [Unit(name="对象旧档").to_dict()]}, "旧版单位存档"),
    ],
)
def test_legacy_roster_migrates_to_v12(tmp_path, legacy_payload, warning_fragment):
    path = tmp_path / "legacy.json"
    path.write_text(json.dumps(legacy_payload, ensure_ascii=False), encoding="utf-8")

    store = load_rosters(str(path), default_rule_mode=RuleMode.V0_3)

    assert store.active_rule_mode == RuleMode.V1_2.value
    assert store.units_for(RuleMode.V0_3) == []
    assert len(store.units_for(RuleMode.V1_2)) == 1
    assert warning_fragment in store.warnings[0]


def test_v03_initiative_orders_by_speed_then_raw_reaction_mobility():
    fast = _v03_unit(name="高速", speed=12, reaction_mobility=10)
    agile = _v03_unit(name="高反应", speed=10, reaction_mobility=80)
    slow_reaction = _v03_unit(name="低反应", speed=10, reaction_mobility=30)

    state = traditional_initiative(
        [slow_reaction, agile, fast],
        rule_mode=RuleMode.V0_3,
    )

    assert state.rule_mode == RuleMode.V0_3.value
    assert state.initiative_mode == "v03_speed"
    assert state.turn_order == [fast.unit_id, agile.unit_id, slow_reaction.unit_id]


def test_v03_exact_initiative_tie_uses_entered_d100_and_failures_go_later():
    first = _v03_unit(name="成功且更低", reaction_mobility=60)
    second = _v03_unit(name="成功但更高", reaction_mobility=60)
    failed = _v03_unit(name="失败", reaction_mobility=60)
    rolls = {first.unit_id: 20, second.unit_id: 45, failed.unit_id: 90}

    state = traditional_initiative(
        [failed, second, first],
        roll_values=rolls,
        rule_mode=RuleMode.V0_3,
    )

    assert state.turn_order == [first.unit_id, second.unit_id, failed.unit_id]
    assert state.initiative_rolls == rolls


def test_v03_exact_initiative_tie_requires_reroll_when_everyone_fails():
    first = _v03_unit(name="甲", reaction_mobility=20)
    second = _v03_unit(name="乙", reaction_mobility=20)

    with pytest.raises(ValueError, match="均失败.*重投"):
        traditional_initiative(
            [first, second],
            roll_values={first.unit_id: 80, second.unit_id: 90},
            rule_mode=RuleMode.V0_3,
        )


def test_v03_attack_uses_manual_hit_roll_resistance_and_attack_statuses():
    attacker = _v03_unit(name="攻击者")
    attacker.add_status("力量")
    attacker.add_status("穿甲")
    target = _v03_unit(name="目标", physical_resist=8)

    message = apply_damage(
        target,
        10,
        "物理",
        attacker=attacker,
        attack_roll=40,
        success_rate=60,
        rule_mode=RuleMode.V0_3,
    )

    assert target.current_hp == 14
    assert "受到 16 点物理伤害" in message
    assert not attacker.has_status("力量")
    assert not attacker.has_status("穿甲")


def test_v03_damage_applies_each_formula_stage_in_order():
    target = _v03_unit(physical_resist=7)

    message = apply_damage(
        target,
        10,
        "物理",
        is_attack=False,
        auxiliary_damage=2,
        normal_multiplier=1.5,
        final_constant=3,
        final_multiplier=0.5,
        rule_mode=RuleMode.V0_3,
    )

    # [(10 + 2) * 1.5 - 7 + 3] * 0.5 = 7
    assert target.current_hp == 23
    assert "受到 7 点物理伤害" in message


def test_v03_missed_attack_does_not_mutate_target():
    target = _v03_unit()

    message = apply_damage(
        target,
        20,
        "物理",
        attack_roll=75,
        success_rate=50,
        rule_mode=RuleMode.V0_3,
    )

    assert target.current_hp == 30
    assert "未被命中" in message


def test_v03_dying_requires_user_supplied_save_and_does_not_reduce_max_hp():
    target = _v03_unit(current_hp=5, max_hp=10, initial_max_hp=10)
    apply_damage(
        target,
        5,
        "真实",
        is_attack=False,
        rule_mode=RuleMode.V0_3,
    )
    assert target.current_hp == 0
    assert target.max_hp == 10
    assert target.has_status("濒死")

    pending = apply_damage(
        target,
        3,
        "真实",
        attack_roll=20,
        success_rate=80,
        rule_mode=RuleMode.V0_3,
    )
    assert pending.startswith("[待填写]")
    assert target.max_hp == 10

    success = apply_damage(
        target,
        3,
        "真实",
        attack_roll=20,
        success_rate=80,
        dying_save_succeeded=True,
        rule_mode=RuleMode.V0_3,
    )
    assert "检定成功" in success
    assert target.get_status("濒死")["stacks"] == 2
    assert target.max_hp == 10


def test_v03_failed_dying_save_kills_target():
    target = _v03_unit(current_hp=0, max_hp=10, initial_max_hp=10)
    target.add_status("濒死", 1)

    message = apply_damage(
        target,
        3,
        "真实",
        attack_roll=10,
        success_rate=80,
        dying_save_succeeded=False,
        rule_mode=RuleMode.V0_3,
    )

    assert "检定失败" in message
    assert target.max_hp == 0
    assert not target.has_status("濒死")


def test_v03_element_burst_refills_tenacity_and_waits_for_entered_10d6_total():
    target = _v03_unit(
        current_hp=100,
        max_hp=100,
        initial_max_hp=100,
        magic_resist=20,
        elemental_tenacity_current=3,
        elemental_tenacity_max=10,
    )

    trigger = apply_elemental_damage(
        target,
        4,
        "灼燃损伤",
        rule_mode=RuleMode.V0_3,
    )

    assert target.elemental_tenacity_current == 10
    assert target.magic_resist == 10
    assert target.current_hp == 100
    assert target.pending_rolls == [{
        "kind": "v03_elemental_burst",
        "element_type": "灼燃损伤",
        "instances": 1,
        "rule_mode": RuleMode.V0_3.value,
    }]
    assert "待填写" in trigger

    resolved = resolve_pending_elemental_burst(
        target,
        35,
        rule_mode=RuleMode.V0_3,
        element_resistance=5,
    )
    assert target.current_hp == 70
    assert target.pending_rolls == []
    assert "10d6=35 - 元素抗性5" in resolved


def test_v03_status_upgrade_chain_and_mark_has_no_synonym_behavior():
    target = _v03_unit()

    assert "获得「标记」" in apply_status(target, "标记", rule_mode=RuleMode.V0_3)
    assert "获得「停顿」" in apply_status(target, "停顿", rule_mode=RuleMode.V0_3)
    assert target.has_status("标记")
    assert target.has_status("停顿")

    upgraded = apply_status(target, "停顿", rule_mode=RuleMode.V0_3)
    assert "升级为「束缚」" in upgraded
    assert target.has_status("标记")
    assert target.has_status("束缚")
    assert not target.has_status("停顿")
