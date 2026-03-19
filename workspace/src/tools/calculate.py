"""
calculate.py — AST-safe arithmetic calculator with Decimal precision.

Public API:
    calculate(expr)          -> dict  # safe expression evaluation
    pct_change(old, new)     -> dict  # percent change rounded to 2dp
    sum_values(pairs, count) -> dict  # sum with unit-mismatch detection

All functions return a dict on both success and error. Never raise to caller.
All arithmetic uses decimal.Decimal with prec=28 to avoid float contamination.

Agent API:
    calculate, pct_change, sum_values are plain Python functions suitable for
    passing directly to create_deep_agent as callables.
"""

import ast
import re
from decimal import Decimal, getcontext, InvalidOperation
from typing import Optional

getcontext().prec = 28

# Whitelist of safe AST node types. Everything else is rejected.
SAFE_NODES = frozenset({
    ast.Expression,
    ast.BinOp,
    ast.UnaryOp,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.Pow,
    ast.Mod,
    ast.UAdd,
    ast.USub,
    ast.Constant,
})


def _eval_node(node):
    """
    Recursively evaluate a whitelisted AST node using Decimal arithmetic.
    Returns a Decimal on success or a dict error on division-by-zero.
    """
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)

    if isinstance(node, ast.Constant):
        # MUST use str() to avoid float imprecision:
        # Decimal(3.14) -> 3.14000000000000012... but Decimal("3.14") -> 3.14
        return Decimal(str(node.value))

    if isinstance(node, ast.BinOp):
        left = _eval_node(node.left)
        right = _eval_node(node.right)
        # Propagate errors from sub-evaluations
        if isinstance(left, dict):
            return left
        if isinstance(right, dict):
            return right
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            if right == 0:
                return {"error": "DIVISION_BY_ZERO", "reason": "Denominator is zero"}
            return left / right
        if isinstance(node.op, ast.Pow):
            return left ** right
        if isinstance(node.op, ast.Mod):
            return left % right

    if isinstance(node, ast.UnaryOp):
        operand = _eval_node(node.operand)
        if isinstance(operand, dict):
            return operand
        if isinstance(node.op, ast.USub):
            return -operand
        if isinstance(node.op, ast.UAdd):
            return +operand

    return {"error": "UNSUPPORTED_NODE", "reason": f"{type(node).__name__} not handled"}


def calculate(expr: str) -> dict:
    """
    Evaluate an arithmetic expression safely using an AST whitelist.

    Only literals and the operators +, -, *, /, **, % and parentheses are
    permitted. Function calls, attribute access, imports, and any other Python
    construct are rejected with DISALLOWED_NODE.

    All arithmetic uses decimal.Decimal with prec=28.

    Args:
        expr: Arithmetic expression string, e.g. "3.14 * 100"

    Returns:
        {"result": Decimal}                         on success
        {"error": "INVALID_INPUT", "reason": ...}   empty expression
        {"error": "SYNTAX_ERROR",  "reason": ...}   unparseable expression
        {"error": "DISALLOWED_NODE", "reason": ...} forbidden AST node
        {"error": "DIVISION_BY_ZERO", "reason": ...}
    """
    if not expr or not expr.strip():
        return {"error": "INVALID_INPUT", "reason": "Expression is empty"}

    try:
        tree = ast.parse(expr.strip(), mode="eval")
    except SyntaxError as e:
        return {"error": "SYNTAX_ERROR", "reason": str(e)}

    # Walk all nodes and reject any that are not in the whitelist
    for node in ast.walk(tree):
        if type(node) not in SAFE_NODES:
            return {
                "error": "DISALLOWED_NODE",
                "reason": f"AST node {type(node).__name__} not allowed",
            }

    result = _eval_node(tree)

    # _eval_node returns a dict only on error
    if isinstance(result, dict):
        return result

    return {"result": result}


def pct_change(old: float, new: float, unit_old: Optional[str] = None, unit_new: Optional[str] = None) -> dict:
    """
    Calculate (new - old) / old * 100 rounded to 2 decimal places.

    Accepts any numeric type for old and new (str, int, float, Decimal).
    All values are converted internally to Decimal via str() to avoid float
    contamination.

    Unit mismatch check: if unit_old and unit_new are both non-None/non-empty
    and differ after normalization (lowercase, strip trailing 's'), returns
    UNIT_MISMATCH error. If either is None or empty, check is skipped.

    Args:
        old:      Base value (denominator)
        new:      New value (numerator)
        unit_old: Optional unit label for old (e.g. "millions")
        unit_new: Optional unit label for new (e.g. "billions")

    Returns:
        {"result": Decimal}                           on success (2dp)
        {"error": "INVALID_INPUT", "reason": ...}     bad input values
        {"error": "UNIT_MISMATCH", "reason": ...}     incompatible units
        {"error": "DIVISION_BY_ZERO", "reason": ...}  old is zero
    """
    try:
        old_d = Decimal(str(old))
        new_d = Decimal(str(new))
    except InvalidOperation as e:
        return {"error": "INVALID_INPUT", "reason": f"Cannot convert to Decimal: {e}"}

    # Unit mismatch check: only when both units are explicitly provided
    if unit_old is not None and unit_new is not None and unit_old and unit_new:
        norm_old = unit_old.lower().rstrip("s")
        norm_new = unit_new.lower().rstrip("s")
        if norm_old != norm_new:
            return {
                "error": "UNIT_MISMATCH",
                "reason": f"Cannot compute pct_change: {unit_old} vs {unit_new}",
            }

    if old_d == 0:
        return {
            "error": "DIVISION_BY_ZERO",
            "reason": "old value is zero, cannot compute pct_change",
        }

    result = (new_d - old_d) / old_d * Decimal("100")
    return {"result": round(result, 2)}


# Unit word regex for sum_values label scanning
_UNIT_RE = re.compile(r"\b(millions?|billions?|thousands?)\b", re.IGNORECASE)


def sum_values(pairs: list, expected_count: int) -> dict:
    """
    Sum a list of (label, value) pairs, enforcing an expected count.

    If the number of pairs does not match expected_count, returns COUNT_MISMATCH.
    If a value cannot be converted to Decimal, returns INVALID_INPUT.
    If labels contain heterogeneous unit words (e.g. "millions" and "billions"),
    includes a "unit_warning" field in the success result — does NOT reject.

    Args:
        pairs:          List of (label: str, value: any) tuples.
        expected_count: Exact number of pairs expected.

    Returns:
        {"result": Decimal, "pair_count": int}                    on success
        {"result": ..., "pair_count": ..., "unit_warning": str}   with mixed units
        {"error": "COUNT_MISMATCH", "reason": ..., "actual_count": int}
        {"error": "INVALID_INPUT", "reason": ...}
    """
    if len(pairs) != expected_count:
        return {
            "error": "COUNT_MISMATCH",
            "reason": f"Expected {expected_count} pairs, got {len(pairs)}",
            "actual_count": len(pairs),
        }

    total = Decimal("0")
    units: set = set()

    for label, value in pairs:
        try:
            val = Decimal(str(value))
        except InvalidOperation:
            return {
                "error": "INVALID_INPUT",
                "reason": f"Cannot parse value for label {repr(label)}",
            }
        total += val

        # Extract and normalize unit words from label
        match = _UNIT_RE.search(str(label))
        if match:
            # Normalize: lowercase and strip trailing 's' for plural
            units.add(match.group(1).lower().rstrip("s"))

    result: dict = {"result": total, "pair_count": len(pairs)}

    if len(units) > 1:
        result["unit_warning"] = f"Heterogeneous units in labels: {sorted(units)}"

    return result
