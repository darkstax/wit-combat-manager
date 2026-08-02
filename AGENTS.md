# Technical Constraints

## Exploration

- Use `code-review-graph` first for architecture, callers/callees, impact, and review context.
- Consult `工作资料/` for game-rule behavior before changing combat logic.
- Keep `工作资料/` private; do not upload or print full source material unless specifically requested.

## Runtime And Structure

- Runtime: Python with PySide6.
- UI entry: `main.py` creates `QApplication` and applies DPI handling.
- Keep combat logic in `models.py`, `combat.py`, and `combat_report.py`; UI should call public APIs and render returned reports/messages.
- Keep UI code under `ui/`; avoid moving rules into widgets.
- `THEME` constants in `models.py` should be used instead of hard-coded repeated colors.

## Combat Rules

- Preserve pure calculation helpers and report dataclasses for damage, healing, status, and elemental effects.
- Status effects with X counters, upgrade chains, mark behavior, healing restrictions, and element burst overflow must stay rule-compatible with `buff.txt` and `元素损伤.txt`.
- Turn-order mutations must tolerate deleted units, empty orders, and overlapping speed states.
- Public combat APIs should fail safely with user-visible error messages rather than crashing the UI.

## Persistence

- Unit data must save atomically with backup behavior.
- Combat state, combat log, and GM log must remain persistent across sessions.
- Load paths should handle missing, corrupt, or inaccessible files without blocking app close.

## Test

```bash
pytest test_combat.py
python main.py
```

- Add or update pytest coverage for rule changes before UI-only assertions.
- Do not require a GUI display for pure combat tests.
