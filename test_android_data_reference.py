from dataclasses import fields
from pathlib import Path

from combat_report import DamageReport, ElementalReport, HealingReport, StatusReport
from models import (
    ALL_STATUS_NAMES,
    CombatState,
    ELEMENT_TYPES,
    Unit,
    V03_ELEMENT_TYPES,
    V03_STATUS_NAMES,
)
from persistence import SCHEMA_VERSION


DOCUMENT = Path(__file__).with_name("android") / "DATA_REFERENCE.md"


def _normalized(text: str) -> str:
    return "".join(character.casefold() for character in text if character.isalnum())


def test_android_data_reference_covers_current_models_and_enums():
    content = DOCUMENT.read_text(encoding="utf-8")
    normalized = _normalized(content)

    assert f"schema_version = {SCHEMA_VERSION}" in content
    for model in (Unit, CombatState, DamageReport, HealingReport, StatusReport, ElementalReport):
        for field in fields(model):
            assert _normalized(field.name) in normalized, f"missing {model.__name__}.{field.name}"

    for name in set(ALL_STATUS_NAMES + V03_STATUS_NAMES + ELEMENT_TYPES + V03_ELEMENT_TYPES):
        assert name in content
