from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class LevelData:
    base_salary: float = 0.0
    bonus: float = 0.0
    formula_salary: str = ""
    formula_bonus: str = ""
    from_position: str | None = None
    from_level: int | None = None

    def to_dict(self, level: int) -> dict:
        return {
            "level": level,
            "base_salary": self.base_salary,
            "bonus": self.bonus,
            "total": self.base_salary + self.bonus,
            "formula_salary": self.formula_salary,
            "formula_bonus": self.formula_bonus,
            "from_position": self.from_position,
            "from_level": self.from_level,
        }


@dataclass(slots=True)
class Position:
    name: str
    levels: list[LevelData] = field(
        default_factory=lambda: [LevelData() for _ in range(4)]
    )

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "levels": [
                level_data.to_dict(level=index)
                for index, level_data in enumerate(self.levels, start=1)
            ],
        }


@dataclass(slots=True)
class Dependency:
    from_position: str
    from_level: int
    to_position: str
    to_level: int
    formula_salary: str
    formula_bonus: str

    @property
    def source(self) -> tuple[str, int]:
        return self.from_position, self.from_level

    @property
    def target(self) -> tuple[str, int]:
        return self.to_position, self.to_level

    def to_dict(self) -> dict:
        return {
            "from_position": self.from_position,
            "from_level": self.from_level,
            "to_position": self.to_position,
            "to_level": self.to_level,
            "formula_salary": self.formula_salary,
            "formula_bonus": self.formula_bonus,
        }
