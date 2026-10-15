import copy
from typing import Any


def strict_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Strict structured outputs demand every property required and no extra keys."""
    strict = copy.deepcopy(schema)

    def tighten(node: Any) -> None:
        if isinstance(node, dict):
            if isinstance(node.get("properties"), dict):
                node["required"] = list(node["properties"])
                node["additionalProperties"] = False
            for value in node.values():
                tighten(value)
        elif isinstance(node, list):
            for item in node:
                tighten(item)

    tighten(strict)
    return strict
