from models import DiceGroup, RollInput, Unit


def test_manual_roll_input_sums_groups_and_modifier():
    roll = RollInput(
        groups=(
            DiceGroup(count=3, sides=6, values=(4, 2, 6)),
            DiceGroup(count=1, sides=2, values=(2,), label="辅助骰"),
        ),
        fixed_modifier=7,
    )
    assert roll.validate() == []
    assert roll.total == 21
    assert roll.has_die_detail


def test_manual_roll_rejects_out_of_range_die():
    roll = RollInput(groups=(DiceGroup(count=2, sides=6, values=(3, 7)),))
    assert any("有效范围" in error for error in roll.validate())


def test_gm_total_override_does_not_require_die_detail():
    roll = RollInput(total_override=28)
    assert roll.validate() == []
    assert roll.total == 28
    assert not roll.has_die_detail


def test_injury_levels_follow_initial_max_hp():
    assert Unit(max_hp=10, initial_max_hp=10).injury_level() == 0
    assert Unit(max_hp=9, initial_max_hp=10).injury_level() == 1
    assert Unit(max_hp=4, initial_max_hp=10).injury_level() == 2
    assert Unit(max_hp=0, initial_max_hp=10).injury_level() == 3


def test_pending_rolls_round_trip_with_unit_data():
    unit = Unit(
        name="Pending",
        pending_rolls=[{
            "kind": "elemental_burst",
            "element_type": "组织损伤",
            "instances": 3,
        }],
    )
    loaded = Unit.from_dict(unit.to_dict())
    assert loaded.pending_rolls == unit.pending_rolls
