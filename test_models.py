from models import DiceGroup, RollInput, Unit, UNIT_TYPES, UNIT_TYPE_LABELS, THEME

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


def test_ally_unit_type_round_trip():
    unit = Unit(name="Lancer", unit_type="ally")
    loaded = Unit.from_dict(unit.to_dict())
    assert loaded.unit_type == "ally"


def test_unknown_unit_type_normalized_to_player():
    assert Unit(name="Weird", unit_type="weird").unit_type == "player"


def test_unit_type_labels_complete():
    for t in UNIT_TYPES:
        assert UNIT_TYPE_LABELS.get(t) is not None
    assert UNIT_TYPE_LABELS["player"] == "玩家"
    assert UNIT_TYPE_LABELS["monster"] == "怪物"
    assert UNIT_TYPE_LABELS["ally"] == "友方"


def test_theme_has_ally_row_bg():
    assert THEME["ally_row_bg"] == "#e3f4e6"


def test_initiative_rank_round_trip():
    unit = Unit(name="Ranked", initiative_rank=7)
    loaded = Unit.from_dict(unit.to_dict())
    assert loaded.initiative_rank == 7
    assert unit.to_dict()["initiative_rank"] == 7


def test_initiative_rank_defaults_to_zero():
    assert Unit(name="Legacy").initiative_rank == 0
    loaded = Unit.from_dict({})
    assert loaded.initiative_rank == 0


def test_initiative_rank_negative_normalized_to_zero():
    unit = Unit(name="Neg", initiative_rank=-3)
    assert unit.initiative_rank == 0
