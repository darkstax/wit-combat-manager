"""Searchable rule reference built from concise summaries and local workbooks.

The workbook readers intentionally extract small, structured reference records. They
do not copy entire sheets into the application or expose hidden calculation tables.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from threading import RLock
from typing import Iterable, Mapping, Sequence
import os
import re

from models import ELEMENTAL_BURST_EFFECTS, RuleMode


WORKBOOK_FILENAMES = {
    "v03_card": "角色卡 行于泰拉v0.3 (1).xlsx",
    "v12_professions": "v1.2.战斗职业（非法术部分）.xlsx",
    "v12_arts": "v1.2源石技艺.xlsx",
    "v12_card": "v1.2.角色卡.Plus .xlsx",
}

_SPACE_RE = re.compile(r"\s+")
_FORMULA_RE = re.compile(r"^=(?:DISPIMG|_xlfn\.DISPIMG)\(", re.IGNORECASE)
_INLINE_DISPIMG_RE = re.compile(
    r"^=(?:_xlfn\.)?DISPIMG\([^)]*\)\s*[;；,:：-]*\s*",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class RuleEntry:
    """One compact, searchable rule or workbook reference record."""

    version: str
    category: str
    title: str
    body: str
    source: str = "内置规则摘要"
    keywords: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self):
        object.__setattr__(self, "version", RuleMode.coerce(self.version).value)
        object.__setattr__(self, "category", _clean_text(self.category) or "其他")
        object.__setattr__(self, "title", _clean_text(self.title) or "未命名条目")
        object.__setattr__(self, "body", _clean_multiline(self.body))
        object.__setattr__(self, "source", _clean_text(self.source) or "本地资料")

    @property
    def search_text(self) -> str:
        return " ".join(
            (self.title, self.category, self.version, self.source, self.body, *self.keywords)
        ).casefold()


def discover_workbook_paths(download_dir: str | os.PathLike | None = None) -> dict[str, Path]:
    """Find the four supported workbooks without requiring fixed machine paths."""

    roots: list[Path] = []
    if download_dir:
        roots.append(Path(download_dir).expanduser())
    user_profile = os.environ.get("USERPROFILE")
    if user_profile:
        roots.append(Path(user_profile) / "Downloads")
    roots.append(Path.home() / "Downloads")

    unique_roots: list[Path] = []
    for root in roots:
        if root not in unique_roots:
            unique_roots.append(root)

    result: dict[str, Path] = {}
    for key, filename in WORKBOOK_FILENAMES.items():
        for root in unique_roots:
            candidate = root / filename
            if candidate.is_file():
                result[key] = candidate
                break
    return result


def search_entries(
    entries: Iterable[RuleEntry],
    query: str = "",
    version: RuleMode | str | None = None,
    category: str | None = None,
    limit: int | None = 300,
) -> list[RuleEntry]:
    """Filter and rank entries. All query terms must be present."""

    normalized_version = RuleMode.coerce(version).value if version else None
    normalized_category = _clean_text(category) if category else ""
    terms = [part.casefold() for part in _SPACE_RE.split(query.strip()) if part]
    ranked: list[tuple[int, str, RuleEntry]] = []

    for entry in entries:
        if normalized_version and entry.version != normalized_version:
            continue
        if normalized_category and normalized_category not in {"全部", "全部类别"}:
            if entry.category != normalized_category:
                continue
        haystack = entry.search_text
        if terms and not all(term in haystack for term in terms):
            continue

        title = entry.title.casefold()
        score = 0
        for term in terms:
            if title == term:
                score += 100
            elif title.startswith(term):
                score += 50
            elif term in title:
                score += 25
            elif term in entry.category.casefold():
                score += 10
            elif term in " ".join(entry.keywords).casefold():
                score += 6
            else:
                score += 1
        ranked.append((-score, entry.title.casefold(), entry))

    ranked.sort(key=lambda item: (item[0], item[1], item[2].category))
    result = [item[2] for item in ranked]
    return result if limit is None else result[: max(0, limit)]


class RuleCatalog:
    """Thread-safe lazy catalog used by the nonmodal rule browser."""

    def __init__(
        self,
        workbook_paths: Mapping[str, str | os.PathLike] | Sequence[str | os.PathLike] | None = None,
    ):
        self._builtin_entries = tuple(_builtin_entries())
        self._external_entries: tuple[RuleEntry, ...] = ()
        self._workbook_paths = _normalize_workbook_paths(workbook_paths)
        self._external_loaded = False
        self._loading = False
        self._errors: list[str] = []
        self._lock = RLock()

    @property
    def external_loaded(self) -> bool:
        with self._lock:
            return self._external_loaded

    @property
    def errors(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(self._errors)

    @property
    def workbook_paths(self) -> dict[str, Path]:
        return dict(self._workbook_paths)

    def entries(self, include_external: bool = True) -> tuple[RuleEntry, ...]:
        with self._lock:
            if include_external:
                return self._builtin_entries + self._external_entries
            return self._builtin_entries

    def categories(self, version: RuleMode | str | None = None) -> list[str]:
        normalized_version = RuleMode.coerce(version).value if version else None
        values = {
            entry.category
            for entry in self.entries()
            if not normalized_version or entry.version == normalized_version
        }
        return sorted(values, key=lambda value: value.casefold())

    def search(
        self,
        query: str = "",
        version: RuleMode | str | None = None,
        category: str | None = None,
        limit: int | None = 300,
    ) -> list[RuleEntry]:
        return search_entries(self.entries(), query, version, category, limit)

    def load_external(self) -> tuple[RuleEntry, ...]:
        """Read supported XLSX references once. Safe to call from a worker thread."""

        with self._lock:
            if self._external_loaded:
                return self._external_entries
            if self._loading:
                return self._external_entries
            self._loading = True

        loaded: list[RuleEntry] = []
        errors: list[str] = []
        try:
            try:
                from openpyxl import load_workbook
            except ImportError as exc:
                errors.append(f"无法载入工作簿支持: {exc}")
                load_workbook = None

            if load_workbook is not None:
                readers = {
                    "v03_card": _read_v03_card,
                    "v12_professions": _read_v12_professions,
                    "v12_arts": _read_v12_arts,
                    "v12_card": _read_v12_quick_reference,
                }
                for key, reader in readers.items():
                    path = self._workbook_paths.get(key)
                    if path is None:
                        continue
                    try:
                        loaded.extend(reader(path, load_workbook))
                    except Exception as exc:  # Workbook corruption must not break the UI.
                        errors.append(f"{path.name}: {exc}")

            deduplicated = _deduplicate(loaded)
            with self._lock:
                self._external_entries = tuple(deduplicated)
                self._errors = errors
                self._external_loaded = True
                return self._external_entries
        finally:
            with self._lock:
                self._loading = False


def _normalize_workbook_paths(
    paths: Mapping[str, str | os.PathLike] | Sequence[str | os.PathLike] | None,
) -> dict[str, Path]:
    if paths is None:
        return discover_workbook_paths()
    if isinstance(paths, Mapping):
        return {
            key: Path(value).expanduser()
            for key, value in paths.items()
            if key in WORKBOOK_FILENAMES and Path(value).expanduser().is_file()
        }

    by_name = {Path(value).name: Path(value).expanduser() for value in paths}
    return {
        key: by_name[filename]
        for key, filename in WORKBOOK_FILENAMES.items()
        if filename in by_name and by_name[filename].is_file()
    }


def _builtin_entries() -> list[RuleEntry]:
    entries = [
        RuleEntry(
            "0.3", "战斗流程", "先攻顺序",
            "按速度从高到低行动；同速比较反应机动。两项都相同时，由使用者填写反应机动检定结果决定顺序。迅捷与迟缓影响下一轮的首尾位置。",
            keywords=("速度", "反应机动", "迅捷", "迟缓"),
        ),
        RuleEntry(
            "0.3", "攻击与伤害", "攻击检定",
            "使用者填写 d100 结果和武器技能成功率。检定成功后再填写伤害骰结果；管理器不代替玩家或 GM 掷骰。",
            keywords=("d100", "命中", "成功率", "手动骰值"),
        ),
        RuleEntry(
            "0.3", "攻击与伤害", "伤害计算",
            "基础结构为[(攻击力+常数)×倍率-对应抗性+最终常数]×最终倍率。物理与法术伤害扣除对应抗性，真实伤害不受抗性和减伤影响。",
            keywords=("物理抗性", "法术抗性", "真实伤害", "倍率"),
        ),
        RuleEntry(
            "0.3", "生命与治疗", "濒死与死亡",
            "HP降到0时进入濒死；理论HP不高于负的最大HP时死亡。濒死单位不能行动、触发被动或接受治疗；再次受击时由使用者填写濒死检定结果。",
            keywords=("HP", "濒死检定", "死亡", "禁疗"),
        ),
        RuleEntry(
            "0.3", "状态", "状态升级链",
            "寒冷再次施加升级为冻结；震慑升级为眩晕；停顿升级为束缚；困顿升级为睡眠；失重升级为浮空。强状态覆盖弱状态。",
            keywords=("寒冷", "冻结", "震慑", "眩晕", "停顿", "束缚", "困顿", "睡眠", "失重", "浮空"),
        ),
        RuleEntry(
            "0.3", "状态", "标记",
            "标记本身只作为特定技能的触发条件，不自动视为其他状态。",
            keywords=("技能触发",),
        ),
        RuleEntry(
            "0.3", "状态", "力量与穿甲",
            "力量使伤害增加10。穿甲忽略庇护，并忽略目标一半抗性；它与 v1.2 的穿透不是同一效果。",
            keywords=("力量", "穿甲", "庇护", "抗性"),
        ),
        RuleEntry(
            "0.3", "元素损伤", "元素韧性与爆发",
            "元素损伤将韧性降到0时立即爆发，并立刻补满元素韧性。爆发的10d6总值由使用者填写。",
            keywords=("韧性", "10d6", "手动骰值"),
        ),
        RuleEntry(
            "1.2", "使用说明", "手动填写骰值",
            "攻击、辅助、效能与元素爆发等骰值由玩家或 GM 实际投掷后填写；管理器负责校验输入并计算结果。",
            keywords=("骰子", "掷骰", "攻击骰", "辅助骰", "效能骰"),
        ),
        RuleEntry(
            "1.2", "战斗流程", "先攻模式",
            "可使用团队先攻、传统逐人先攻或由 GM 客观指定先动阵营。传统先攻的反应机动检定总值由使用者填写。",
            keywords=("团队先攻", "传统先攻", "反应机动", "客观判断"),
        ),
        RuleEntry(
            "1.2", "攻击与伤害", "攻击与伤害计算",
            "攻击检定总值达到目标抗性 DC 时命中，折前值减去对应 DC 得到最终伤害。多重修正按规则先加算、后乘算；真实伤害不扣抗性。",
            keywords=("抗性DC", "折前伤害", "最终伤害", "真实伤害"),
        ),
        RuleEntry(
            "1.2", "生命与治疗", "濒死、伤残与重振",
            "HP归零后进入濒死；溢出及濒死期间受到的最终伤害会降低生命上限，生命上限归零时死亡。重振消耗1耐力，并按本次回复值救起目标。",
            keywords=("生命上限", "濒死", "死亡", "重振", "耐力"),
        ),
        RuleEntry(
            "1.2", "元素损伤", "元素韧性与爆发",
            "精英阶段零、一、二的基础元素韧性分别为6、9、12。韧性归零后进入元素爆发，爆发持续到目标自己的下个回合开始；爆发骰值由使用者填写。",
            keywords=("精零", "精一", "精二", "爆发骰", "辅助骰"),
        ),
        RuleEntry(
            "1.2", "状态", "标记",
            "标记同时被视为停顿、震颤、寒冷与困顿，可参与相应状态判定和升级。",
            keywords=("停顿", "震颤", "寒冷", "困顿"),
        ),
        RuleEntry(
            "1.2", "状态", "穿透",
            "穿透使攻击忽略掩体效果；它不等同于 v0.3 中忽略部分抗性的穿甲。",
            keywords=("掩体", "穿甲"),
        ),
        RuleEntry(
            "1.2", "状态", "状态升级链",
            "麻痹再次施加升级为眩晕；寒冷升级为冻结；困顿升级为睡眠；停顿升级为束缚。",
            keywords=("麻痹", "眩晕", "寒冷", "冻结", "困顿", "睡眠", "停顿", "束缚"),
        ),
    ]

    v03_bursts = {
        "凋亡损伤": "10d6元素伤害，并施加虚弱、失去10SP。",
        "灼燃损伤": "10d6元素伤害，法术抗性-10，持续到战斗结束。",
        "侵蚀损伤": "10d6元素伤害，物理抗性-10，持续到战斗结束。",
        "神经损伤": "10d6真实伤害，并施加眩晕。",
        "组织损伤": "10d6元素伤害，并施加禁疗。",
        "毒性损伤": "10d6元素伤害，并施加虚弱与迟缓。",
        "结晶损伤": "10d6元素伤害，并增加感染。感染骰值由使用者填写。",
    }
    entries.extend(
        RuleEntry("0.3", "元素爆发", name, description, keywords=("10d6", "元素韧性"))
        for name, description in v03_bursts.items()
    )

    for name, effect in ELEMENTAL_BURST_EFFECTS.items():
        multiplier = effect.get("true_dmg_mult", 0)
        statuses = "、".join(effect.get("statuses", ()))
        details = [f"造成爆发骰值×{multiplier}的真实伤害"]
        if statuses:
            details.append(f"施加{statuses}")
        if effect.get("extra"):
            details.append(str(effect["extra"]))
        entries.append(
            RuleEntry(
                "1.2", "元素爆发", name, "；".join(details) + "。",
                keywords=("元素韧性", "爆发骰"),
            )
        )
    return entries


def _read_v03_card(path: Path, load_workbook) -> list[RuleEntry]:
    wb = load_workbook(path, read_only=True, data_only=True, keep_links=False)
    try:
        if "源石技艺" not in wb.sheetnames:
            return []
        ws = wb["源石技艺"]
        entries: list[RuleEntry] = []
        # The normalized public-facing arts database occupies AT:BC near the top.
        rows = ws.iter_rows(
            min_row=2, max_row=min(ws.max_row, 221), min_col=46, max_col=55,
            values_only=True,
        )
        for values in rows:
            major = _cell_text(values[0])
            minor = _cell_text(values[1])
            title = _cell_text(values[2])
            if not title:
                continue
            fields = [
                ("大类", major), ("小类", minor),
                ("等级", _cell_text(values[3])),
                ("行动", _cell_text(values[4])),
                ("SP", _cell_text(values[5])),
                ("习得", _cell_text(values[6])),
                ("限制", _cell_text(values[7])),
                ("目标", _cell_text(values[8])),
                ("效果", _cell_text(values[9])),
            ]
            entries.append(RuleEntry(
                "0.3", "源石技艺", title, _format_fields(fields), path.name,
                keywords=tuple(value for value in (major, minor) if value),
            ))
        return entries
    finally:
        wb.close()


def _read_v12_professions(path: Path, load_workbook) -> list[RuleEntry]:
    wb = load_workbook(path, read_only=True, data_only=True, keep_links=False)
    try:
        entries: list[RuleEntry] = []
        for ws in wb.worksheets:
            if ws.sheet_state != "visible" or ws.title.startswith("WpsReserved"):
                continue
            if ws.title in {"草稿"}:
                continue
            rows = list(ws.iter_rows(
                min_row=1, max_row=min(ws.max_row, 18), min_col=1, max_col=36,
                values_only=True,
            ))
            main_class = _cell_text(_matrix_value(rows, 1, 2))
            overview = [("主职业", main_class)] if main_class else []
            for values in rows:
                label = _cell_text(values[0])
                value = _cell_text(values[1])
                if label and value and not _is_formula(value):
                    overview.append((label, value))
            if overview:
                entries.append(RuleEntry(
                    "1.2", "职业", ws.title, _format_fields(overview), path.name,
                    keywords=tuple(value for value in ("战斗职业", main_class) if value),
                ))
            entries.extend(_read_v12_stage_sheet(
                rows, ws.title, path.name, "职业技艺", (12, 17, 22, 27), 33,
            ))
        return entries
    finally:
        wb.close()


def _read_v12_arts(path: Path, load_workbook) -> list[RuleEntry]:
    wb = load_workbook(path, read_only=True, data_only=True, keep_links=False)
    try:
        entries: list[RuleEntry] = []
        excluded = {"草稿", "空表格", "法术职业", "v1.2更新记录"}
        for ws in wb.worksheets:
            if ws.sheet_state != "visible" or ws.title in excluded or ws.title.startswith("WpsReserved"):
                continue
            rows = list(ws.iter_rows(
                min_row=1, max_row=ws.max_row, min_col=1, max_col=31,
                values_only=True,
            ))
            entries.extend(_read_v12_stage_sheet(
                rows, ws.title, path.name, "源石技艺", (2, 7, 12, 17), 23,
            ))
            entries.extend(_read_v12_summons(rows, ws.title, path.name))
        return entries
    finally:
        wb.close()


def _read_v12_stage_sheet(
    rows: Sequence[Sequence[object]],
    sheet_title: str,
    source: str,
    category: str,
    starts: Sequence[int],
    passive_value_col: int,
) -> list[RuleEntry]:
    entries: list[RuleEntry] = []
    stages = ((3, "精英化零"), (7, "精英化一"), (11, "精英化二"), (15, "模组"))
    for base_row, stage in stages:
        if base_row > len(rows):
            continue
        for start_col in starts:
            title = _cell_text(_matrix_value(rows, base_row, start_col))
            if not title or _is_formula(title):
                continue
            fields = [
                ("阶段", stage),
                ("主要行动", _cell_text(_matrix_value(rows, base_row + 1, start_col + 1))),
                ("快速行动", _cell_text(_matrix_value(rows, base_row + 1, start_col + 2))),
                ("范围", _cell_text(_matrix_value(rows, base_row + 1, start_col + 4))),
                ("SP", _cell_text(_matrix_value(rows, base_row + 2, start_col + 1))),
                ("耐力", _cell_text(_matrix_value(rows, base_row + 2, start_col + 2))),
                ("目标", _cell_text(_matrix_value(rows, base_row + 2, start_col + 4))),
                ("效果", _cell_text(_matrix_value(rows, base_row + 3, start_col + 1))),
            ]
            entries.append(RuleEntry(
                "1.2", category, title, _format_fields(fields), source,
                keywords=(sheet_title, stage),
            ))

        passive_title = _cell_text(_matrix_value(rows, base_row + 1, passive_value_col))
        passive_effect = _cell_text(_matrix_value(rows, base_row + 2, passive_value_col))
        if passive_title and not _is_formula(passive_title):
            entries.append(RuleEntry(
                "1.2", "被动技艺", passive_title,
                _format_fields((("职业/流派", sheet_title), ("阶段", stage), ("效果", passive_effect))),
                source, keywords=(sheet_title, stage, category),
            ))
    return entries


def _read_v12_summons(
    rows: Sequence[Sequence[object]], sheet_title: str, source: str,
) -> list[RuleEntry]:
    entries: list[RuleEntry] = []
    row = 19
    while row <= len(rows):
        title = _cell_text(_matrix_value(rows, row, 3))
        tag_label = _cell_text(_matrix_value(rows, row, 4))
        if title and tag_label == "标签":
            values: list[tuple[str, str]] = [("流派", sheet_title)]
            tag = _cell_text(_matrix_value(rows, row, 5))
            if tag:
                values.append(("标签", tag))
            next_row = row + 1
            while next_row <= len(rows) and next_row < row + 18:
                if _cell_text(_matrix_value(rows, next_row, 3)) and _cell_text(_matrix_value(rows, next_row, 4)) == "标签":
                    break
                detail = _cell_text(_matrix_value(rows, next_row, 4))
                if detail and not _is_formula(detail):
                    values.append(("属性", detail))
                next_row += 1
            entries.append(RuleEntry(
                "1.2", "召唤物", title, _format_fields(values), source,
                keywords=(sheet_title, tag),
            ))
            row = next_row
            continue
        row += 1
    return entries


def _read_v12_quick_reference(path: Path, load_workbook) -> list[RuleEntry]:
    wb = load_workbook(path, read_only=True, data_only=True, keep_links=False)
    try:
        if "战斗信息速查表" not in wb.sheetnames:
            return []
        ws = wb["战斗信息速查表"]
        entries: list[RuleEntry] = []
        rows = ws.iter_rows(
            min_row=2, max_row=ws.max_row, min_col=1, max_col=8,
            values_only=True,
        )
        for values in rows:
            action = _cell_text(values[0])
            if action:
                entries.append(RuleEntry(
                    "1.2", "战斗动作", action,
                    _format_fields((
                        ("消耗", _cell_text(values[1])),
                        ("条件", _cell_text(values[2])),
                        ("效果", _cell_text(values[3])),
                    )), path.name,
                ))
            positive = _cell_text(values[4])
            if positive:
                entries.append(RuleEntry(
                    "1.2", "正面状态", positive, _cell_text(values[5]), path.name,
                    keywords=("状态", "增益"),
                ))
            negative = _cell_text(values[6])
            if negative:
                entries.append(RuleEntry(
                    "1.2", "负面状态", negative, _cell_text(values[7]), path.name,
                    keywords=("状态", "减益"),
                ))
        return entries
    finally:
        wb.close()


def _deduplicate(entries: Iterable[RuleEntry]) -> list[RuleEntry]:
    unique: dict[tuple[str, str, str, str], RuleEntry] = {}
    for entry in entries:
        key = (entry.version, entry.category, entry.title.casefold(), entry.body.casefold())
        unique.setdefault(key, entry)
    return list(unique.values())


def _matrix_value(rows: Sequence[Sequence[object]], row: int, column: int) -> object:
    if row < 1 or column < 1 or row > len(rows):
        return None
    values = rows[row - 1]
    return values[column - 1] if column <= len(values) else None


def _format_fields(fields: Iterable[tuple[str, object]]) -> str:
    lines = []
    for label, raw_value in fields:
        value = _cell_text(raw_value)
        if not value or _is_formula(value) or value == "/":
            continue
        lines.append(f"{_clean_text(label)}：{value}")
    return "\n".join(lines)


def _cell_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    text = _INLINE_DISPIMG_RE.sub("", str(value).strip())
    return _clean_multiline(text)


def _is_formula(value: str) -> bool:
    return bool(_FORMULA_RE.match(value)) or value.startswith("=")


def _clean_text(value: object) -> str:
    return _SPACE_RE.sub(" ", str(value or "")).strip()


def _clean_multiline(value: object) -> str:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = [_SPACE_RE.sub(" ", line).strip() for line in text.split("\n")]
    return "\n".join(line for line in lines if line)
