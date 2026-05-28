from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from django.conf import settings

from .engine import Objective, Option, coerce_float


@dataclass(frozen=True)
class DatasetDefinition:
    id: str
    label: str
    description: str
    source: str


DATASETS = {
    "cars": DatasetDefinition(
        id="cars",
        label="Gas Cars",
        description="Original Edmunds car tradeoff demo data.",
        source="Local cars.json",
    ),
    "evs": DatasetDefinition(
        id="evs",
        label="Electric Vehicles",
        description="Open EV Data: electric vehicle specs focused on charging capabilities and energy consumption.",
        source="Open EV Data / KilowattApp",
    ),
}

CARS_DEFAULT_OBJECTIVES = {"price", "MPGCombined", "averageRating"}
CARS_DEFAULT_GOALS = {
    "price": "min",
    "MPGCombined": "max",
    "averageRating": "max",
    "reviewsCount": "max",
}

EV_DEFAULT_OBJECTIVES = {"estimated_range_km", "average_consumption", "dc_max_power", "usable_battery_size"}
EV_FIELD_DEFINITIONS = [
    {
        "key": "estimated_range_km",
        "label": "Estimated Range",
        "goal": "max",
        "formatter": "km",
        "description": "Derived from usable battery size and average consumption.",
    },
    {
        "key": "average_consumption",
        "label": "Energy Consumption",
        "goal": "min",
        "formatter": "kWh/100km",
        "description": "Average energy consumption from Open EV Data.",
    },
    {
        "key": "usable_battery_size",
        "label": "Usable Battery",
        "goal": "max",
        "formatter": "kWh",
        "description": "Usable battery size.",
    },
    {
        "key": "dc_max_power",
        "label": "DC Fast Charging",
        "goal": "max",
        "formatter": "kW",
        "description": "Maximum DC charging power when available.",
    },
    {
        "key": "ac_max_power",
        "label": "AC Charging",
        "goal": "max",
        "formatter": "kW",
        "description": "Maximum AC charging power.",
    },
    {
        "key": "release_year",
        "label": "Release Year",
        "goal": "max",
        "formatter": "year",
        "description": "Vehicle release year.",
    },
    {
        "key": "charging_voltage",
        "label": "Charging Voltage",
        "goal": "max",
        "formatter": "V",
        "description": "Charging voltage architecture.",
    },
]


def available_datasets() -> list[dict[str, str]]:
    return [
        {
            "id": definition.id,
            "label": definition.label,
            "description": definition.description,
            "source": definition.source,
        }
        for definition in DATASETS.values()
    ]


def normalize_dataset_id(dataset_id: str | None) -> str:
    return dataset_id if dataset_id in DATASETS else "cars"


@lru_cache(maxsize=4)
def load_catalog(dataset_id: str | None = None) -> dict[str, Any]:
    dataset_id = normalize_dataset_id(dataset_id)
    if dataset_id == "evs":
        return _load_ev_catalog()
    return _load_cars_catalog()


def _load_cars_catalog() -> dict[str, Any]:
    path = Path(settings.BASE_DIR) / "cars.json"
    with path.open(encoding="utf-8") as handle:
        raw = json.load(handle)

    columns = raw.get("columns", [])
    options = [_adapt_car_option(item) for item in raw.get("options", [])]
    objectives = [_adapt_car_objective(column, options) for column in columns if column.get("type") == "numeric"]
    filter_fields = [_filter_field(column["key"], column.get("full_name", column["key"]), column.get("format"), options) for column in columns if column.get("type") == "numeric"]
    return {
        "id": "cars",
        "subject": raw.get("subject", "Cars"),
        "description": DATASETS["cars"].description,
        "source": DATASETS["cars"].source,
        "columns": columns,
        "options": options,
        "objectives": objectives,
        "filter_fields": filter_fields,
        "default_objectives": CARS_DEFAULT_OBJECTIVES,
        "scenarios": [
            {
                "name": "Balanced",
                "objectives": ["price", "MPGCombined", "averageRating", "reviewsCount"],
                "filters": {"price": {"max": 60000}, "MPGCombined": {"min": 24}},
            },
            {
                "name": "Performance",
                "objectives": ["price", "power", "engineSize", "averageRating"],
                "filters": {"price": {"max": 90000}},
            },
            {
                "name": "Efficient",
                "objectives": ["price", "MPGCombined", "averageRating", "reviewsCount"],
                "filters": {"MPGCombined": {"min": 30}, "price": {"max": 50000}},
            },
        ],
    }


def _load_ev_catalog() -> dict[str, Any]:
    path = Path(settings.BASE_DIR) / "open-ev-data.json"
    with path.open(encoding="utf-8") as handle:
        raw = json.load(handle)

    brands = {brand.get("id"): brand.get("name") for brand in raw.get("brands", [])}
    options = [_adapt_ev_option(item, brands) for item in raw.get("data", [])]
    objectives = [_adapt_ev_objective(field, options) for field in EV_FIELD_DEFINITIONS]
    filter_fields = [_filter_field(field["key"], field["label"], field["formatter"], options) for field in EV_FIELD_DEFINITIONS]
    return {
        "id": "evs",
        "subject": "Electric Vehicles",
        "description": DATASETS["evs"].description,
        "source": DATASETS["evs"].source,
        "columns": EV_FIELD_DEFINITIONS,
        "options": options,
        "objectives": objectives,
        "filter_fields": filter_fields,
        "default_objectives": EV_DEFAULT_OBJECTIVES,
        "scenarios": [
            {
                "name": "Road Trip",
                "objectives": ["estimated_range_km", "dc_max_power", "average_consumption", "usable_battery_size"],
                "filters": {"estimated_range_km": {"min": 300}, "dc_max_power": {"min": 100}},
            },
            {
                "name": "Efficient",
                "objectives": ["average_consumption", "estimated_range_km", "release_year"],
                "filters": {"average_consumption": {"max": 18}, "release_year": {"min": 2020}},
            },
            {
                "name": "Home Charging",
                "objectives": ["ac_max_power", "average_consumption", "estimated_range_km"],
                "filters": {"ac_max_power": {"min": 11}, "estimated_range_km": {"min": 250}},
            },
        ],
        "meta": raw.get("meta", {}),
    }


def _adapt_car_option(item: dict[str, Any]) -> Option:
    return Option(
        id=str(item.get("key")),
        name=str(item.get("name", "")),
        description=str(item.get("description", "")),
        values=dict(item.get("values", {})),
    )


def _adapt_ev_option(item: dict[str, Any], brands: dict[str, str | None]) -> Option:
    brand = item.get("brand") or brands.get(item.get("brand_id")) or "Unknown"
    model = item.get("model") or "Unknown model"
    variant = item.get("variant")
    year = item.get("release_year")
    battery = coerce_float(item.get("usable_battery_size"))
    consumption = coerce_float((item.get("energy_consumption") or {}).get("average_consumption"))
    estimated_range = None
    if battery is not None and consumption is not None and consumption > 0:
        estimated_range = round((battery / consumption) * 100, 1)
    ac = item.get("ac_charger") or {}
    dc = item.get("dc_charger") or {}
    values = {
        "brand": brand,
        "model": model,
        "variant": variant,
        "vehicle_type": item.get("vehicle_type"),
        "release_year": year,
        "usable_battery_size": battery,
        "average_consumption": consumption,
        "estimated_range_km": estimated_range,
        "ac_max_power": coerce_float(ac.get("max_power")),
        "ac_usable_phases": coerce_float(ac.get("usable_phases")),
        "dc_max_power": coerce_float(dc.get("max_power")),
        "charging_voltage": coerce_float(item.get("charging_voltage")),
    }
    display_name = " ".join(str(part) for part in [brand, model, variant] if part)
    description_parts = [
        str(year) if year else None,
        f"{battery:g} kWh usable battery" if battery is not None else None,
        f"{values['dc_max_power']:g} kW DC" if values["dc_max_power"] is not None else None,
    ]
    return Option(
        id=str(item.get("id")),
        name=display_name,
        description="; ".join(part for part in description_parts if part),
        values=values,
    )


def _adapt_car_objective(column: dict[str, Any], options: list[Option]) -> Objective:
    key = str(column["key"])
    range_spec = column.get("range") or {}
    computed_min, computed_max = _numeric_range(key, options)
    return Objective(
        key=key,
        label=str(column.get("full_name", key)),
        type=str(column.get("type", "numeric")),
        goal=str(CARS_DEFAULT_GOALS.get(key, column.get("goal", "max"))),
        weight=1.0,
        minimum=coerce_float(range_spec.get("low")) if "low" in range_spec else computed_min,
        maximum=coerce_float(range_spec.get("high")) if "high" in range_spec else computed_max,
        formatter=column.get("format"),
    )


def _adapt_ev_objective(field: dict[str, Any], options: list[Option]) -> Objective:
    minimum, maximum = _numeric_range(field["key"], options)
    return Objective(
        key=field["key"],
        label=field["label"],
        type="numeric",
        goal=field["goal"],
        weight=1.0,
        minimum=minimum,
        maximum=maximum,
        formatter=field.get("formatter"),
    )


def _filter_field(key: str, label: str, formatter: str | None, options: list[Option]) -> dict[str, Any]:
    minimum, maximum = _numeric_range(key, options)
    return {
        "key": key,
        "label": label,
        "min": minimum,
        "max": maximum,
        "formatter": formatter,
    }


def _numeric_range(key: str, options: list[Option]) -> tuple[float | None, float | None]:
    values = [value for option in options if (value := coerce_float(option.values.get(key))) is not None]
    if not values:
        return None, None
    return min(values), max(values)


def catalog_payload(dataset_id: str | None = None) -> dict[str, Any]:
    catalog = load_catalog(dataset_id)
    objectives: list[Objective] = catalog["objectives"]
    options: list[Option] = catalog["options"]
    default_objectives: set[str] = catalog["default_objectives"]
    return {
        "datasetId": catalog["id"],
        "datasets": available_datasets(),
        "subject": catalog["subject"],
        "description": catalog["description"],
        "source": catalog["source"],
        "objectives": [
            {
                "key": objective.key,
                "label": objective.label,
                "goal": objective.goal,
                "weight": objective.weight,
                "min": objective.minimum,
                "max": objective.maximum,
                "formatter": objective.formatter,
                "activeDefault": objective.key in default_objectives,
            }
            for objective in objectives
        ],
        "filters": catalog["filter_fields"],
        "scenarios": catalog["scenarios"],
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
