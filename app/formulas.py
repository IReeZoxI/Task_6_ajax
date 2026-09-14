from __future__ import annotations

import ast
import math
import operator


MAX_FORMULA_LENGTH = 200
MAX_ABSOLUTE_RESULT = 1_000_000_000_000_000

_BINARY_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}
_UNARY_OPERATORS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


class FormulaError(ValueError):
    """Raised when a salary formula is invalid or unsafe."""


def _ensure_result(value: int | float) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise FormulaError("Формула повинна повертати число.")
    if isinstance(value, float) and not math.isfinite(value):
        raise FormulaError("Результат формули повинен бути скінченним числом.")
    if abs(value) > MAX_ABSOLUTE_RESULT:
        raise FormulaError("Результат формули перевищує допустиму межу.")
    return value


def _evaluate_node(node: ast.AST, variables: dict[str, int | float]) -> int | float:
    if isinstance(node, ast.Expression):
        return _evaluate_node(node.body, variables)

    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise FormulaError("У формулі дозволені лише числові константи.")
        return _ensure_result(node.value)

    if isinstance(node, ast.Name):
        if node.id not in variables:
            raise FormulaError("Дозволені лише змінні S і B.")
        return _ensure_result(variables[node.id])

    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY_OPERATORS:
        left = _evaluate_node(node.left, variables)
        right = _evaluate_node(node.right, variables)
        try:
            result = _BINARY_OPERATORS[type(node.op)](left, right)
        except ZeroDivisionError as error:
            raise FormulaError("Ділення на нуль у формулі.") from error
        return _ensure_result(result)

    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPERATORS:
        value = _evaluate_node(node.operand, variables)
        return _ensure_result(_UNARY_OPERATORS[type(node.op)](value))

    raise FormulaError(
        "Дозволені лише числа, S, B, дужки та оператори +, -, *, /."
    )


def parse_formula(formula: str) -> ast.Expression:
    formula = formula.strip()
    if not formula:
        raise FormulaError("Формула не може бути порожньою.")
    if len(formula) > MAX_FORMULA_LENGTH:
        raise FormulaError(f"Формула не може бути довшою за {MAX_FORMULA_LENGTH} символів.")
    try:
        parsed = ast.parse(formula, mode="eval")
    except SyntaxError as error:
        raise FormulaError("Формула має неправильний синтаксис.") from error
    return parsed


def validate_formula(formula: str) -> None:
    parsed = parse_formula(formula)
    _evaluate_node(parsed, {"S": 1, "B": 1})


def evaluate_formula(formula: str, salary: int | float, bonus: int | float) -> int | float:
    parsed = parse_formula(formula)
    return _evaluate_node(parsed, {"S": salary, "B": bonus})
