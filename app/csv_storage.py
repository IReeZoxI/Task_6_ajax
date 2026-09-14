from __future__ import annotations

import csv
import io
import math

from app.domain import Dependency, LevelData, Position
from app.manager import SalaryManager


FORMAT_NAME = "salary-dependency-manager-web"
FORMAT_VERSION = "1"
CSV_FIELDS = (
    "record_type",
    "position_name",
    "level",
    "base_salary",
    "bonus",
    "from_position",
    "from_level",
    "to_position",
    "to_level",
    "formula_salary",
    "formula_bonus",
)


def _csv_value(value: object | None) -> object:
    return "" if value is None else value


def export_csv(manager: SalaryManager) -> str:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=CSV_FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerow(
        {
            "record_type": "META",
            "position_name": FORMAT_NAME,
            "level": FORMAT_VERSION,
        }
    )

    for position in manager.positions.values():
        for level, level_data in enumerate(position.levels, start=1):
            writer.writerow(
                {
                    "record_type": "POSITION_LEVEL",
                    "position_name": position.name,
                    "level": level,
                    "base_salary": level_data.base_salary,
                    "bonus": level_data.bonus,
                    "from_position": _csv_value(level_data.from_position),
                    "from_level": _csv_value(level_data.from_level),
                    "to_position": "",
                    "to_level": "",
                    "formula_salary": level_data.formula_salary,
                    "formula_bonus": level_data.formula_bonus,
                }
            )

    for dependency in manager.dependencies:
        writer.writerow(
            {
                "record_type": "DEPENDENCY",
                "position_name": "",
                "level": "",
                "base_salary": "",
                "bonus": "",
                "from_position": dependency.from_position,
                "from_level": dependency.from_level,
                "to_position": dependency.to_position,
                "to_level": dependency.to_level,
                "formula_salary": dependency.formula_salary,
                "formula_bonus": dependency.formula_bonus,
            }
        )

    return "\ufeff" + output.getvalue()


def _parse_level(value: str | None, row_number: int, field_name: str) -> int:
    try:
        level = int(value or "")
    except ValueError as error:
        raise ValueError(
            f"Рядок {row_number}: поле '{field_name}' повинно містити цілий рівень 1–4."
        ) from error
    if level not in range(1, 5):
        raise ValueError(f"Рядок {row_number}: рівень повинен бути від 1 до 4.")
    return level


def _parse_number(value: str | None, row_number: int, field_name: str) -> int | float:
    text = (value or "").strip()
    try:
        number: int | float = int(text)
    except ValueError:
        try:
            number = float(text)
        except ValueError as error:
            raise ValueError(
                f"Рядок {row_number}: поле '{field_name}' повинно містити число."
            ) from error
    try:
        is_finite = math.isfinite(float(number))
    except OverflowError as error:
        raise ValueError(
            f"Рядок {row_number}: поле '{field_name}' перевищує допустиму межу."
        ) from error
    if not is_finite:
        raise ValueError(f"Рядок {row_number}: поле '{field_name}' має бути скінченним.")
    return number


def import_csv(content: str) -> SalaryManager:
    reader = csv.DictReader(
        io.StringIO(content.lstrip("\ufeff"), newline=""),
        strict=True,
    )
    if reader.fieldnames is None:
        raise ValueError("CSV-файл порожній або не має заголовка.")
    if tuple(reader.fieldnames) != CSV_FIELDS:
        raise ValueError("Це не CSV-файл Salary Dependency Manager або його формат змінено.")

    rows = [
        (row_number, row)
        for row_number, row in enumerate(reader, start=2)
        if any(value not in (None, "") for value in row.values())
    ]
    if not rows:
        raise ValueError("CSV-файл не містить службового запису формату.")

    meta_row_number, meta = rows[0]
    if None in meta:
        raise ValueError(
            f"Рядок {meta_row_number}: кількість колонок не відповідає заголовку."
        )
    if (
        (meta.get("record_type") or "").strip().upper() != "META"
        or (meta.get("position_name") or "").strip() != FORMAT_NAME
        or (meta.get("level") or "").strip() != FORMAT_VERSION
    ):
        raise ValueError(
            f"Рядок {meta_row_number}: файл не має правильного маркера програми та версії."
        )

    positions: dict[str, Position] = {}
    seen_levels: dict[str, set[int]] = {}
    dependency_rows: list[tuple[int, dict[str, str]]] = []

    for row_number, row in rows[1:]:
        if None in row:
            raise ValueError(f"Рядок {row_number}: кількість колонок не відповідає заголовку.")
        record_type = (row.get("record_type") or "").strip().upper()

        if record_type == "POSITION_LEVEL":
            name = (row.get("position_name") or "").strip()
            if not name:
                raise ValueError(f"Рядок {row_number}: не вказано назву посади.")
            level = _parse_level(row.get("level"), row_number, "level")

            if name not in positions:
                positions[name] = Position(name=name)
                seen_levels[name] = set()
            if level in seen_levels[name]:
                raise ValueError(
                    f"Рядок {row_number}: рівень {level} посади '{name}' повторюється."
                )

            from_position = (row.get("from_position") or "").strip() or None
            from_level_text = (row.get("from_level") or "").strip()
            from_level = (
                _parse_level(from_level_text, row_number, "from_level")
                if from_level_text
                else None
            )
            if (from_position is None) != (from_level is None):
                raise ValueError(
                    f"Рядок {row_number}: стартова посада і рівень заповнюються разом."
                )

            positions[name].levels[level - 1] = LevelData(
                base_salary=_parse_number(row.get("base_salary"), row_number, "base_salary"),
                bonus=_parse_number(row.get("bonus"), row_number, "bonus"),
                formula_salary=(row.get("formula_salary") or "").strip(),
                formula_bonus=(row.get("formula_bonus") or "").strip(),
                from_position=from_position,
                from_level=from_level,
            )
            seen_levels[name].add(level)
        elif record_type == "DEPENDENCY":
            dependency_rows.append((row_number, row))
        elif record_type == "META":
            raise ValueError(f"Рядок {row_number}: службовий запис META повторюється.")
        else:
            raise ValueError(f"Рядок {row_number}: невідомий тип запису '{record_type}'.")

    for name, levels in seen_levels.items():
        missing = sorted(set(range(1, 5)) - levels)
        if missing:
            raise ValueError(
                f"Для посади '{name}' відсутні рівні: "
                + ", ".join(str(level) for level in missing)
            )

    dependencies: list[Dependency] = []
    for row_number, row in dependency_rows:
        from_position = (row.get("from_position") or "").strip()
        to_position = (row.get("to_position") or "").strip()
        if not from_position or not to_position:
            raise ValueError(f"Рядок {row_number}: залежність не має джерела або цілі.")
        dependencies.append(
            Dependency(
                from_position=from_position,
                from_level=_parse_level(row.get("from_level"), row_number, "from_level"),
                to_position=to_position,
                to_level=_parse_level(row.get("to_level"), row_number, "to_level"),
                formula_salary=(row.get("formula_salary") or "").strip(),
                formula_bonus=(row.get("formula_bonus") or "").strip(),
            )
        )

    manager = SalaryManager(positions=positions, dependencies=dependencies)
    manager.validate_loaded_state()
    return manager
