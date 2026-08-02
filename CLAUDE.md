# Technical Constraints

- Canonical rules live in `AGENTS.md`; keep this file synchronized with it.
- Keep rules in `models.py`, `combat.py`, and `combat_report.py`; keep widgets focused on UI.
- Check `工作资料/` before changing status, elemental, initiative, or turn-order behavior.
- Preserve atomic saves, backup handling, combat-state persistence, and dual log persistence.
- Add or update `pytest` coverage in `test_combat.py` for rule changes.
- Public combat APIs should return safe error messages instead of crashing the PySide6 UI.
