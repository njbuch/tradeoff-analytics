from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from django.conf import settings

from .engine import Objective, Option, coerce_float


DEFAULT_OBJECTIVES = {"price", "MPGCombined", "averageRating"}
DEFAULT_GOALS = {
    "price": "min",
    "MPGCombined": "max",
    "averageRating": "max",
    "reviewsCount": "max",
}


@lru_cache(maxsize=1)
def load_catalog() -> dict[str, Any]:
    path = Path(settings.BASE_DIR) / "cars.json"
    with path.open(encoding="utf-8") as handle:
        raw = json.load(handle)

    columns = raw.get("columns", [])
    options = [_adapt_option(item) for item in raw.get("options", [])]
    objectives = [_adapt_objective(column, options) for column in columns if column.get("type") == "numeric"]
    filter_fields = [_filter_field(column, options) for column in columns if column.get("type") == "numeric"]
    return {
        "subject": raw.get("subject", "Cars"),
        "columns": columns,
        "options": options,
        "objectives": objectives,
        "filter_fields": filter_fields,
    }


def _adapt_option(item: dict[str, Any]) -> Option:
    return Option(
        id=str(item.get("key")),
        name=str(item.get("name", "")),
        description=str(item.get("description", "")),
        values=dict(item.get("values", {})),
    )


def _adapt_objective(column: dict[str, Any], options: list[Option]) -> Objective:
    key = str(column["key"])
    range_spec = column.get("range") or {}
    computed_min, computed_max = _numeric_range(key, options)
    return Objective(
        key=key,
        label=str(column.get("full_name", key)),
        type=str(column.get("type", "numeric")),
        goal=str(DEFAULT_GOALS.get(key, column.get("goal", "max"))),
        weight=1.0,
        minimum=coerce_float(range_spec.get("low")) if "low" in range_spec else computed_min,
        maximum=coerce_float(range_spec.get("high")) if "high" in range_spec else computed_max,
        formatter=column.get("format"),
    )


def _filter_field(column: dict[str, Any], options: list[Option]) -> dict[str, Any]:
    key = str(column["key"])
    minimum, maximum = _numeric_range(key, options)
    return {
        "key": key,
        "label": column.get("full_name", key),
        "min": minimum,
        "max": maximum,
        "formatter": column.get("format"),
    }


def _numeric_range(key: str, options: list[Option]) -> tuple[float | None, float | None]:
    values = [value for option in options if (value := coerce_float(option.values.get(key))) is not None]
    if not values:
        return None, None
    return min(values), max(values)


def catalog_payload() -> dict[str, Any]:
    catalog = load_catalog()
    objectives: list[Objective] = catalog["objectives"]
    options: list[Option] = catalog["options"]
    return {
        "subject": catalog["subject"],
        "objectives": [
            {
                "key": objective.key,
                "label": objective.label,
                "goal": objective.goal,
                "weight": objective.weight,
                "min": objective.minimum,
                "max": objective.maximum,
                "formatter": objective.formatter,
                "activeDefault": objective.key in DEFAULT_OBJECTIVES,
            }
            for objective in objectives
        ],
        "filters": catalog["filter_fields"],
        "options": [
            {
                "id": option.id,
                "name": option.name,
                "description": option.description,
                "values": option.values,
            }
            for option in options
        ],
    }
