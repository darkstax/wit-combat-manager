import json

from models import CombatState, Unit
from persistence import (
    load_combat_state,
    load_data,
    save_combat_state,
    save_data,
)


def test_loads_legacy_unit_list_and_normalizes_status(tmp_path):
    path = tmp_path / "data.json"
    path.write_text(
        json.dumps([
            {
                "name": "Legacy",
                "current_hp": 5,
                "max_hp": 10,
                "status_effects": ["困倦"],
            }
        ], ensure_ascii=False),
        encoding="utf-8",
    )
    units = load_data(str(path))
    assert len(units) == 1
    assert units[0].has_status("困顿")
    assert units[0].initial_max_hp == 10


def test_save_data_keeps_previous_good_backup(tmp_path):
    path = tmp_path / "data.json"
    save_data([Unit(name="First")], str(path))
    save_data([Unit(name="Second")], str(path))
    backup = json.loads((tmp_path / "data.json.bak").read_text(encoding="utf-8"))
    assert backup["units"][0]["name"] == "First"
    assert load_data(str(path))[0].name == "Second"


def test_corrupt_unit_file_is_quarantined(tmp_path):
    path = tmp_path / "data.json"
    path.write_text("{broken", encoding="utf-8")
    assert load_data(str(path)) == []
    assert not path.exists()
    assert list(tmp_path.glob("data.json.*.corrupt.bak"))


def test_corrupt_unit_file_recovers_last_good_backup(tmp_path):
    path = tmp_path / "data.json"
    save_data([Unit(name="Backup")], str(path))
    save_data([Unit(name="Primary")], str(path))
    path.write_text("{broken", encoding="utf-8")
    units = load_data(str(path))
    assert [unit.name for unit in units] == ["Backup"]
    assert list(tmp_path.glob("data.json.*.corrupt.bak"))


def test_invalid_single_unit_quarantines_whole_snapshot_instead_of_dropping_it(tmp_path):
    path = tmp_path / "data.json"
    path.write_text(json.dumps({
        "units": [
            Unit(name="Good").to_dict(),
            {"name": "Broken", "status_effects": [{"name": "屏障", "stacks": "bad"}]},
        ],
    }, ensure_ascii=False), encoding="utf-8")
    assert load_data(str(path)) == []
    assert not path.exists()
    assert list(tmp_path.glob("data.json.*.corrupt.bak"))


def test_combat_state_round_trip_and_unknown_fields(tmp_path):
    path = tmp_path / "combat.json"
    state = CombatState(turn=3, now_index=4, turn_order=["a"], active=True)
    save_combat_state(state, str(path))
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["combat_state"]["future_field"] = "ignored"
    path.write_text(json.dumps(payload), encoding="utf-8")
    loaded = load_combat_state(str(path))
    assert loaded is not None
    assert loaded.turn == 3
    assert loaded.now_index == 0
    assert loaded.turn_order == ["a"]


def test_invalid_combat_state_numbers_fail_safely(tmp_path):
    path = tmp_path / "combat.json"
    path.write_text(json.dumps({
        "combat_state": {
            "turn": "bad",
            "now_index": 0,
            "turn_order": [],
            "initiative_rolls": {},
            "active": True,
        },
    }), encoding="utf-8")
    assert load_combat_state(str(path)) is None
    assert list(tmp_path.glob("combat.json.*.corrupt.bak"))
