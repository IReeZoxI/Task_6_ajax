from __future__ import annotations

import copy
import math
import re
from collections.abc import Iterable

from app.domain import Dependency, LevelData, Position
from app.formulas import evaluate_formula, validate_formula


POSITION_NAME_PATTERN = re.compile(r"^[\w ]+$", re.UNICODE)
MAX_POSITION_NAME_LENGTH = 100


class SalaryManager:
    def __init__(
        self,
        positions: dict[str, Position] | None = None,
        dependencies: list[Dependency] | None = None,
    ) -> None:
        self.positions = positions or {}
        self.dependencies = dependencies or []

    @staticmethod
    def _validate_position_name(name: str) -> str:
        name = name.strip()
        if not name:
            raise ValueError("Назва посади не може бути порожньою.")
        if len(name) > MAX_POSITION_NAME_LENGTH:
            raise ValueError(
                f"Назва посади не може бути довшою за {MAX_POSITION_NAME_LENGTH} символів."
            )
        if not POSITION_NAME_PATTERN.fullmatch(name):
            raise ValueError(
                "У назві посади дозволені лише літери, цифри, пробіли та символ _."
            )
        return name

    @staticmethod
    def _validate_level(level: int) -> int:
        if isinstance(level, bool) or level not in range(1, 5):
            raise ValueError("Рівень повинен бути цілим числом від 1 до 4.")
        return level

    @staticmethod
    def _validate_number(value: int | float, field_name: str) -> int | float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"Поле '{field_name}' повинно містити число.")
        try:
            is_finite = math.isfinite(float(value))
        except OverflowError as error:
            raise ValueError(f"Поле '{field_name}' перевищує допустиму межу.") from error
        if not is_finite:
            raise ValueError(f"Поле '{field_name}' повинно містити скінченне число.")
        return value

    def add_position(self, name: str) -> Position:
        name = self._validate_position_name(name)
        if name in self.positions:
            raise ValueError(f"Посада '{name}' вже існує.")
        position = Position(name=name)
        self.positions[name] = position
        return position

    def remove_position(self, name: str) -> None:
        if name not in self.positions:
            raise ValueError(f"Посаду '{name}' не знайдено.")

        del self.positions[name]
        self.dependencies = [
            dependency
            for dependency in self.dependencies
            if dependency.from_position != name and dependency.to_position != name
        ]

        for position in self.positions.values():
            for level_data in position.levels:
                if level_data.from_position == name:
                    level_data.from_position = None
                    level_data.from_level = None
                    level_data.formula_salary = ""
                    level_data.formula_bonus = ""

    def update_rules(self, position_name: str, rules: Iterable[dict]) -> None:
        if position_name not in self.positions:
            raise ValueError(f"Посаду '{position_name}' не знайдено.")

        rules_by_level: dict[int, dict] = {}
        for rule in rules:
            level = self._validate_level(rule["level"])
            if level in rules_by_level:
                raise ValueError(f"Правило рівня {level} повторюється.")
            rules_by_level[level] = rule

        if set(rules_by_level) != set(range(1, 5)):
            raise ValueError("Потрібно передати рівно по одному правилу для рівнів 1–4.")

        current_position = self.positions[position_name]
        prepared_levels: list[LevelData] = []
        prepared_dependencies: list[Dependency] = []

        for level in range(1, 5):
            rule = rules_by_level[level]
            base_salary = self._validate_number(rule["base_salary"], "base_salary")
            bonus = self._validate_number(rule["bonus"], "bonus")
            from_position = (rule.get("from_position") or "").strip() or None
            from_level = rule.get("from_level")

            if from_position is None:
                if from_level is not None:
                    raise ValueError(
                        f"Рівень {level}: стартова посада і рівень повинні бути заповнені разом."
                    )
                prepared_levels.append(LevelData(base_salary=base_salary, bonus=bonus))
                continue

            if from_position not in self.positions:
                raise ValueError(
                    f"Рівень {level}: стартову посаду '{from_position}' не знайдено."
                )
            from_level = self._validate_level(from_level)
            if from_position == position_name and from_level == level:
                raise ValueError(f"Рівень {level} не може залежати сам від себе.")

            formula_salary = (rule.get("formula_salary") or "").strip()
            formula_bonus = (rule.get("formula_bonus") or "").strip()
            validate_formula(formula_salary)
            validate_formula(formula_bonus)

            prepared_levels.append(
                LevelData(
                    base_salary=current_position.levels[level - 1].base_salary,
                    bonus=current_position.levels[level - 1].bonus,
                    formula_salary=formula_salary,
                    formula_bonus=formula_bonus,
                    from_position=from_position,
                    from_level=from_level,
                )
            )
            prepared_dependencies.append(
                Dependency(
                    from_position=from_position,
                    from_level=from_level,
                    to_position=position_name,
                    to_level=level,
                    formula_salary=formula_salary,
                    formula_bonus=formula_bonus,
                )
            )

        candidate_dependencies = [
            dependency
            for dependency in self.dependencies
            if dependency.to_position != position_name
        ] + prepared_dependencies
        candidate_positions = copy.deepcopy(self.positions)
        candidate_positions[position_name].levels = prepared_levels
        candidate_manager = SalaryManager(
            positions=candidate_positions,
            dependencies=candidate_dependencies,
        )
        candidate_manager._validate_dependency_graph(candidate_dependencies)
        candidate_manager.calculate_salaries()

        self.positions = candidate_manager.positions
        self.dependencies = candidate_manager.dependencies

    def _validate_dependency_graph(self, dependencies: list[Dependency]) -> None:
        dependency_by_target: dict[tuple[str, int], Dependency] = {}
        for dependency in dependencies:
            self._validate_level(dependency.from_level)
            self._validate_level(dependency.to_level)
            if dependency.from_position not in self.positions:
                raise ValueError(
                    f"Стартову посаду '{dependency.from_position}' не знайдено."
                )
            if dependency.to_position not in self.positions:
                raise ValueError(f"Цільову посаду '{dependency.to_position}' не знайдено.")
            if dependency.target in dependency_by_target:
                raise ValueError(
                    f"Для рівня {dependency.to_level} посади '{dependency.to_position}' "
                    "задано декілька залежностей."
                )
            validate_formula(dependency.formula_salary)
            validate_formula(dependency.formula_bonus)
            dependency_by_target[dependency.target] = dependency

        visited: set[tuple[str, int]] = set()
        active: set[tuple[str, int]] = set()

        def visit(node: tuple[str, int]) -> None:
            if node in active:
                raise ValueError("Виявлено циклічну залежність між рівнями.")
            if node in visited:
                return
            active.add(node)
            dependency = dependency_by_target.get(node)
            if dependency is not None:
                visit(dependency.source)
            active.remove(node)
            visited.add(node)

        for target in dependency_by_target:
            visit(target)

    def validate_loaded_state(self) -> None:
        for name, position in self.positions.items():
            if self._validate_position_name(name) != position.name:
                raise ValueError("Назва посади не відповідає її ключу.")
            if len(position.levels) != 4:
                raise ValueError(f"Посада '{name}' повинна мати рівно чотири рівні.")
            for level_data in position.levels:
                self._validate_number(level_data.base_salary, "base_salary")
                self._validate_number(level_data.bonus, "bonus")

        self._validate_dependency_graph(self.dependencies)
        dependencies_by_target = {
            dependency.target: dependency for dependency in self.dependencies
        }

        for position in self.positions.values():
            for level, level_data in enumerate(position.levels, start=1):
                dependency = dependencies_by_target.get((position.name, level))
                if level_data.from_position is None:
                    if (
                        level_data.from_level is not None
                        or dependency is not None
                        or level_data.formula_salary
                        or level_data.formula_bonus
                    ):
                        raise ValueError(
                            f"Дані правила для '{position.name}', рівень {level}, не узгоджені."
                        )
                    continue

                if dependency is None:
                    raise ValueError(
                        f"Для '{position.name}', рівень {level}, відсутній запис залежності."
                    )
                if (
                    dependency.from_position != level_data.from_position
                    or dependency.from_level != level_data.from_level
                    or dependency.formula_salary != level_data.formula_salary
                    or dependency.formula_bonus != level_data.formula_bonus
                ):
                    raise ValueError(
                        f"Дані залежності для '{position.name}', рівень {level}, не узгоджені."
                    )

    def calculate_salaries(self) -> None:
        dependencies_by_target = {
            dependency.target: dependency for dependency in self.dependencies
        }
        resolved: set[tuple[str, int]] = set()

        def resolve(node: tuple[str, int]) -> None:
            if node in resolved:
                return
            dependency = dependencies_by_target.get(node)
            if dependency is None:
                resolved.add(node)
                return

            resolve(dependency.source)
            source_data = self.positions[dependency.from_position].levels[
                dependency.from_level - 1
            ]
            target_data = self.positions[dependency.to_position].levels[
                dependency.to_level - 1
            ]
            target_data.base_salary = evaluate_formula(
                dependency.formula_salary,
                source_data.base_salary,
                source_data.bonus,
            )
            target_data.bonus = evaluate_formula(
                dependency.formula_bonus,
                source_data.base_salary,
                source_data.bonus,
            )
            resolved.add(node)

        for target in dependencies_by_target:
            resolve(target)

    def to_dict(self) -> dict:
        return {
            "positions": [position.to_dict() for position in self.positions.values()],
            "dependencies": [
                dependency.to_dict() for dependency in self.dependencies
            ],
        }
