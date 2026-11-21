"""Gate-local three-valued logic. X means unknown, not don't-care."""

from .model import OPS, VALUES, WirestepError


def gate_value(op, values):
    if not isinstance(op, str) or op not in OPS:
        raise WirestepError("Unknown gate operation")
    if not isinstance(values, (list, tuple)) or any(not isinstance(v, str) or v not in VALUES for v in values):
        raise WirestepError("Gate values must be a list or tuple of 0, 1, or X")
    if (op in {"BUF", "NOT"} and len(values) != 1) or (op not in {"BUF", "NOT"} and not 2 <= len(values) <= 16):
        raise WirestepError(f"Invalid input count for {op}")
    if op == "BUF":
        return values[0]
    if op == "NOT":
        return {"0": "1", "1": "0", "X": "X"}[values[0]]
    if op in {"AND", "NAND"}:
        result = "0" if "0" in values else "X" if "X" in values else "1"
    elif op in {"OR", "NOR"}:
        result = "1" if "1" in values else "X" if "X" in values else "0"
    else:
        result = "X" if "X" in values else str(sum(v == "1" for v in values) % 2)
    if op in {"NAND", "NOR", "XNOR"}:
        return {"0": "1", "1": "0", "X": "X"}[result]
    return result
