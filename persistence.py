"""TRPG combat manager JSON persistence with backups and migrations."""

import json
import os
import shutil
import tempfile
from dataclasses import asdict, dataclass, fields
from datetime import datetime
from typing import Optional

from app_paths import writable_data_dir
from models import CombatState, RuleMode, Unit


BASE_DIR = str(writable_data_dir())
DEFAULT_PATH = os.path.join(BASE_DIR, "data.json")
COMBAT_STATE_PATH = os.path.join(BASE_DIR, "combat_state.json")
SCHEMA_VERSION = 3


@dataclass
class RosterStore:
    rosters: dict[str, list[Unit]]
    active_rule_mode: str = RuleMode.V1_2.value
    warnings: tuple[str, ...] = ()

    def units_for(self, rule_mode: RuleMode | str) -> list[Unit]:
        mode = RuleMode.coerce(rule_mode).value
        return self.rosters.setdefault(mode, [])


def _atomic_json_write(path: str, data) -> str:
    """Write JSON in the target directory and retain the last good file as .bak."""
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=f".{os.path.basename(path)}.", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        if os.path.exists(path):
            shutil.copy2(path, path + ".bak")
        os.replace(tmp_path, path)
        return path
    except Exception:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise


def save_text(path: str, text: str) -> str:
    """Atomically persist log/settings text while retaining the previous copy."""
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=f".{os.path.basename(path)}.", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        if os.path.exists(path):
            shutil.copy2(path, path + ".bak")
        os.replace(tmp_path, path)
        return path
    except Exception:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise


def load_text(path: str, default: str = "") -> str:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read()
    except (FileNotFoundError, UnicodeDecodeError, OSError):
        return default


def _read_json(path: str):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _quarantine_corrupt_file(path: str) -> None:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = f"{path}.{timestamp}.corrupt.bak"
    try:
        os.replace(path, backup)
    except OSError:
        try:
            shutil.copy2(path, backup)
        except OSError:
            pass


def _load_with_backup(path: str, parser):
    """Parse the primary file, then its last-good backup if needed."""
    for candidate in (path, path + ".bak"):
        if not os.path.exists(candidate):
            continue
        try:
            return parser(_read_json(candidate))
        except (json.JSONDecodeError, UnicodeDecodeError, TypeError, ValueError, AttributeError, OverflowError):
            if candidate == path:
                _quarantine_corrupt_file(path)
        except OSError:
            continue
    return None


def _parse_units(data) -> list[Unit]:
    if isinstance(data, dict):
        if isinstance(data.get("rosters"), dict):
            mode = RuleMode.coerce(data.get("active_rule_mode", RuleMode.V1_2)).value
            raw_units = data["rosters"].get(mode, [])
        else:
            raw_units = data.get("units")
    elif isinstance(data, list):
        raw_units = data
    else:
        raise ValueError("unit payload must be a list or versioned object")
    if not isinstance(raw_units, list):
        raise ValueError("units must be a list")

    units = []
    for item in raw_units:
        if not isinstance(item, dict):
            raise ValueError("each unit must be an object")
        units.append(Unit.from_dict(item))
    return units


def _parse_unit_list(raw_units) -> list[Unit]:
    if not isinstance(raw_units, list):
        raise ValueError("units must be a list")
    units = []
    for item in raw_units:
        if not isinstance(item, dict):
            raise ValueError("each unit must be an object")
        units.append(Unit.from_dict(item))
    return units


def _parse_rosters(data) -> RosterStore:
    warnings = []
    rosters = {mode.value: [] for mode in RuleMode}
    if isinstance(data, dict) and isinstance(data.get("rosters"), dict):
        raw_rosters = data["rosters"]
        for mode in RuleMode:
            rosters[mode.value] = _parse_unit_list(raw_rosters.get(mode.value, []))
        active = RuleMode.coerce(data.get("active_rule_mode", RuleMode.V1_2)).value
    elif isinstance(data, dict) and "units" in data:
        rosters[RuleMode.V1_2.value] = _parse_unit_list(data["units"])
        active = RuleMode.V1_2.value
        warnings.append("旧版单位存档已归入 v1.2 名单")
    elif isinstance(data, list):
        rosters[RuleMode.V1_2.value] = _parse_unit_list(data)
        active = RuleMode.V1_2.value
        warnings.append("旧格式单位列表已归入 v1.2 名单")
    else:
        raise ValueError("unknown roster payload")
    return RosterStore(rosters=rosters, active_rule_mode=active, warnings=tuple(warnings))


def save_data(units: list[Unit], filepath: Optional[str] = None) -> str:
    path = filepath or DEFAULT_PATH
    payload = {
        "schema_version": SCHEMA_VERSION,
        "units": [unit.to_dict() for unit in units],
    }
    return _atomic_json_write(path, payload)


def load_data(filepath: Optional[str] = None) -> list[Unit]:
    """Load old list files and versioned files without blocking application close."""
    path = filepath or DEFAULT_PATH
    units = _load_with_backup(path, _parse_units)
    return units if units is not None else []


def save_rosters(
    rosters: dict[str, list[Unit]],
    active_rule_mode: RuleMode | str,
    filepath: Optional[str] = None,
) -> str:
    path = filepath or DEFAULT_PATH
    active = RuleMode.coerce(active_rule_mode).value
    payload = {
        "schema_version": SCHEMA_VERSION,
        "active_rule_mode": active,
        "rosters": {
            mode.value: [unit.to_dict() for unit in rosters.get(mode.value, [])]
            for mode in RuleMode
        },
    }
    return _atomic_json_write(path, payload)


def load_rosters(
    filepath: Optional[str] = None,
    default_rule_mode: RuleMode | str = RuleMode.V1_2,
) -> RosterStore:
    path = filepath or DEFAULT_PATH
    store = _load_with_backup(path, _parse_rosters)
    if store is not None:
        return store
    mode = RuleMode.coerce(default_rule_mode).value
    return RosterStore(
        rosters={item.value: [] for item in RuleMode},
        active_rule_mode=mode,
    )


def save_combat_state(state: CombatState, filepath: Optional[str] = None) -> str:
    path = filepath or COMBAT_STATE_PATH
    payload = {
        "schema_version": SCHEMA_VERSION,
        "combat_state": asdict(state),
    }
    return _atomic_json_write(path, payload)


def load_combat_state(filepath: Optional[str] = None) -> Optional[CombatState]:
    path = filepath or COMBAT_STATE_PATH
    return _load_with_backup(path, _parse_combat_state)


def _parse_combat_state(payload) -> CombatState:
    if isinstance(payload, dict) and "combat_state" in payload:
        data = payload.get("combat_state")
    else:
        data = payload
    if not isinstance(data, dict):
        raise ValueError("combat state must be an object")

    allowed = {field.name for field in fields(CombatState)}
    normalized = {key: value for key, value in data.items() if key in allowed}
    state = CombatState(**normalized)

    if not isinstance(state.turn_order, list) or not isinstance(state.initiative_rolls, dict):
        raise ValueError("combat order and rolls have invalid types")
    state.turn = max(0, int(state.turn))
    state.now_index = max(0, int(state.now_index))
    state.turn_order = [str(uid) for uid in state.turn_order if uid]
    rolls = {}
    for uid, value in state.initiative_rolls.items():
        if not uid or not isinstance(value, (int, float)):
            continue
        try:
            rolls[str(uid)] = int(value)
        except (TypeError, ValueError, OverflowError):
            continue
    state.initiative_rolls = rolls
    if not isinstance(state.active, bool):
        raise ValueError("combat active flag must be boolean")
    if not isinstance(state.pending_reorder, bool):
        raise ValueError("pending reorder flag must be boolean")
    if state.turn_order:
        state.now_index = min(state.now_index, len(state.turn_order) - 1)
    else:
        state.now_index = 0
    return state


def delete_combat_state(filepath: Optional[str] = None):
    path = filepath or COMBAT_STATE_PATH
    try:
        if os.path.exists(path):
            os.remove(path)
    except OSError:
        pass
