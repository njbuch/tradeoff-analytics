from __future__ import annotations

from dataclasses import dataclass, replace
from math import cos, isfinite, pi, sin
from typing import Any, Iterable


EPSILON = 1e-9


@dataclass(frozen=True)
class Objective:
    key: str
    label: str
    type: str = "numeric"
    goal: str = "max"
    weight: float = 1.0
    minimum: float | None = None
    maximum: float | None = None
    target: float | None = None
    formatter: str | None = None


@dataclass(frozen=True)
class Option:
    id: str
    name: str
    description: str
    values: dict[str, Any]


def coerce_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None


def apply_filters(options: list[Option], filters: dict[str, dict[str, Any]]) -> list[Option]:
    if not filters:
        return list(options)

    feasible: list[Option] = []
    for option in options:
        keep = True
        for key, bounds in filters.items():
            if not isinstance(bounds, dict):
                continue
            value = coerce_float(option.values.get(key))
            if value is None:
                keep = False
                break
            minimum = coerce_float(bounds.get("min"))
            maximum = coerce_float(bounds.get("max"))
            if minimum is not None and value < minimum:
                keep = False
                break
            if maximum is not None and value > maximum:
                keep = False
                break
        if keep:
            feasible.append(option)
    return feasible


def objective_ranges(options: list[Option], objectives: list[Objective]) -> dict[str, tuple[float, float]]:
    ranges: dict[str, tuple[float, float]] = {}
    for objective in objectives:
        values = [
            value
            for option in options
            if (value := coerce_float(option.values.get(objective.key))) is not None
        ]
        explicit_min = objective.minimum
        explicit_max = objective.maximum
        minimum = explicit_min if explicit_min is not None else (min(values) if values else 0.0)
        maximum = explicit_max if explicit_max is not None else (max(values) if values else minimum)
        ranges[objective.key] = (float(minimum), float(maximum))
    return ranges


def normalize_value(value: Any, objective: Objective, minimum: float, maximum: float) -> float | None:
    numeric = coerce_float(value)
    if numeric is None:
        return None

    if objective.goal == "target":
        target = objective.target
        if target is None:
            target = (minimum + maximum) / 2.0
        max_distance = max(abs(maximum - target), abs(target - minimum), EPSILON)
        score = 1.0 - abs(numeric - target) / max_distance
    elif objective.goal == "min":
        denominator = maximum - minimum
        score = 1.0 if abs(denominator) < EPSILON else (maximum - numeric) / denominator
    else:
        denominator = maximum - minimum
        score = 1.0 if abs(denominator) < EPSILON else (numeric - minimum) / denominator

    return min(1.0, max(0.0, score))


def normalize_options(
    options: list[Option], objectives: list[Objective]
) -> tuple[dict[str, dict[str, float]], dict[str, dict[str, bool]], dict[str, tuple[float, float]]]:
    ranges = objective_ranges(options, objectives)
    normalized: dict[str, dict[str, float]] = {}
    missing: dict[str, dict[str, bool]] = {}
    for option in options:
        normalized[option.id] = {}
        missing[option.id] = {}
        for objective in objectives:
            minimum, maximum = ranges[objective.key]
            score = normalize_value(option.values.get(objective.key), objective, minimum, maximum)
            missing_value = score is None
            normalized[option.id][objective.key] = 0.0 if score is None else score
            missing[option.id][objective.key] = missing_value
    return normalized, missing, ranges


def dominates(left: dict[str, float], right: dict[str, float], keys: Iterable[str]) -> bool:
    has_strict_gain = False
    for key in keys:
        left_value = left.get(key, 0.0)
        right_value = right.get(key, 0.0)
        if left_value + EPSILON < right_value:
            return False
        if left_value > right_value + EPSILON:
            has_strict_gain = True
    return has_strict_gain


def pareto_frontier(
    options: list[Option], normalized: dict[str, dict[str, float]], objective_keys: list[str]
) -> tuple[dict[str, bool], dict[str, list[str]]]:
    pareto: dict[str, bool] = {option.id: True for option in options}
    dominated_by: dict[str, list[str]] = {option.id: [] for option in options}

    for candidate in options:
        candidate_scores = normalized[candidate.id]
        for option in options:
            if candidate.id == option.id:
                continue
            if dominates(candidate_scores, normalized[option.id], objective_keys):
                pareto[option.id] = False
                dominated_by[option.id].append(candidate.id)

    return pareto, dominated_by


def objective_anchors(objectives: list[Objective]) -> dict[str, dict[str, float]]:
    count = len(objectives)
    if count == 0:
        return {}
    anchors: dict[str, dict[str, float]] = {}
    for index, objective in enumerate(objectives):
        angle = (2 * pi * index / count) - (pi / 2)
        anchors[objective.key] = {
            "x": cos(angle),
            "y": sin(angle),
            "angle": angle,
        }
    return anchors


def option_position(scores: dict[str, float], anchors: dict[str, dict[str, float]]) -> dict[str, float]:
    total = sum(max(0.0, scores.get(key, 0.0)) for key in anchors)
    if total <= EPSILON:
        return {"x": 0.0, "y": 0.0}
    x = sum((scores.get(key, 0.0) / total) * anchor["x"] for key, anchor in anchors.items())
    y = sum((scores.get(key, 0.0) / total) * anchor["y"] for key, anchor in anchors.items())
    return {"x": x, "y": y}


def weighted_delta(
    base: dict[str, float], candidate: dict[str, float], objectives: list[Objective]
) -> tuple[float, float, float]:
    gain = 0.0
    loss = 0.0
    for objective in objectives:
        weight = max(0.0, objective.weight)
        delta = candidate.get(objective.key, 0.0) - base.get(objective.key, 0.0)
        if delta > 0:
            gain += delta * weight
        elif delta < 0:
            loss += abs(delta) * weight
    return gain, loss, gain / (loss + EPSILON)


def explain_delta(
    base: dict[str, float], candidate: dict[str, float], objectives: list[Objective]
) -> str:
    gains: list[str] = []
    losses: list[str] = []
    for objective in objectives:
        delta = candidate.get(objective.key, 0.0) - base.get(objective.key, 0.0)
        if abs(delta) < 0.005:
            continue
        label = objective.label
        phrase = f"{abs(delta) * 100:.0f}% {label}"
        if delta > 0:
            gains.append(f"+{phrase}")
        else:
            losses.append(f"-{phrase}")
    if gains and losses:
        return f"Gains {', '.join(gains)} for {', '.join(losses)}."
    if gains:
        return f"Gains {', '.join(gains)} with no meaningful tradeoff."
    if losses:
        return f"Mostly gives up {', '.join(losses)}."
    return "Scores are effectively tied on the active objectives."


def recommendation_candidates(
    selected_id: str,
    options: list[Option],
    normalized: dict[str, dict[str, float]],
    objectives: list[Objective],
    limit: int = 5,
) -> list[dict[str, Any]]:
    selected_scores = normalized.get(selected_id)
    if selected_scores is None:
        return []

    recommendations: list[dict[str, Any]] = []
    for option in options:
        if option.id == selected_id:
            continue
        gain, loss, ratio = weighted_delta(selected_scores, normalized[option.id], objectives)
        if gain <= EPSILON:
            continue
        recommendations.append(
            {
                "id": option.id,
                "name": option.name,
                "gain": gain,
                "loss": loss,
                "ratio": ratio,
                "explanation": explain_delta(selected_scores, normalized[option.id], objectives),
            }
        )

    recommendations.sort(key=lambda item: (item["ratio"], item["gain"], -item["loss"]), reverse=True)
    return recommendations[:limit]


def configure_objectives(
    base_objectives: list[Objective], requested: list[dict[str, Any]] | None
) -> list[Objective]:
    by_key = {objective.key: objective for objective in base_objectives}
    if not requested:
        defaults = [objective for objective in base_objectives if objective.key in {"price", "MPGCombined", "averageRating"}]
        return defaults or base_objectives[:3]

    configured: list[Objective] = []
    for item in requested:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key", ""))
        objective = by_key.get(key)
        if objective is None:
            continue
        goal = item.get("goal", objective.goal)
        if goal not in {"min", "max", "target"}:
            goal = objective.goal
        weight = coerce_float(item.get("weight"))
        target = coerce_float(item.get("target"))
        configured.append(
            replace(
                objective,
                goal=goal,
                weight=weight if weight is not None and weight > 0 else objective.weight,
                target=target if target is not None else objective.target,
            )
        )
    return configured


def evaluate_tradeoffs(
    options: list[Option],
    objectives: list[Objective],
    filters: dict[str, dict[str, Any]] | None = None,
    selected_id: str | None = None,
) -> dict[str, Any]:
    filters = filters or {}
    feasible = apply_filters(options, filters)
    normalized, missing, ranges = normalize_options(feasible, objectives)
    objective_keys = [objective.key for objective in objectives]
    pareto, dominated_by = pareto_frontier(feasible, normalized, objective_keys)
    anchors = objective_anchors(objectives)

    response_options: list[dict[str, Any]] = []
    for option in feasible:
        dominators = dominated_by[option.id]
        scores = normalized[option.id]
        response_options.append(
            {
                "id": option.id,
                "name": option.name,
                "description": option.description,
                "values": option.values,
                "scores": scores,
                "missing": missing[option.id],
                "pareto": pareto[option.id],
                "dominated_by": dominators[:5],
                "position": option_position(scores, anchors),
                "reason": pareto_reason(option, pareto[option.id], dominators, feasible),
            }
        )

    if selected_id is None and response_options:
        selected_id = response_options[0]["id"]
    selected = build_selected(selected_id, feasible, normalized, objectives, pareto, dominated_by) if selected_id else None

    return {
        "objectives": [
            {
                "key": objective.key,
                "label": objective.label,
                "goal": objective.goal,
                "weight": objective.weight,
                "min": ranges.get(objective.key, (0.0, 0.0))[0],
                "max": ranges.get(objective.key, (0.0, 0.0))[1],
                "target": objective.target,
                "formatter": objective.formatter,
            }
            for objective in objectives
        ],
        "anchors": anchors,
        "options": response_options,
        "selected": selected,
        "summary": {
            "total": len(options),
            "feasible": len(feasible),
            "pareto": sum(1 for value in pareto.values() if value),
            "dominated": sum(1 for value in pareto.values() if not value),
        },
    }


def pareto_reason(option: Option, is_pareto: bool, dominators: list[str], options: list[Option]) -> str:
    if is_pareto:
        return "On the Pareto frontier because no feasible car is at least as good on every active objective while improving one."
    names = {candidate.id: candidate.name for candidate in options}
    visible = [names.get(option_id, option_id) for option_id in dominators[:3]]
    return f"Dominated by {', '.join(visible)} on the active objectives."


def build_selected(
    selected_id: str,
    options: list[Option],
    normalized: dict[str, dict[str, float]],
    objectives: list[Objective],
    pareto: dict[str, bool],
    dominated_by: dict[str, list[str]],
) -> dict[str, Any] | None:
    selected = next((option for option in options if option.id == selected_id), None)
    if selected is None:
        return None
    return {
        "id": selected.id,
        "name": selected.name,
        "description": selected.description,
        "values": selected.values,
        "scores": normalized[selected.id],
        "pareto": pareto[selected.id],
        "dominated_by": dominated_by[selected.id][:5],
        "reason": pareto_reason(selected, pareto[selected.id], dominated_by[selected.id], options),
        "alternatives": recommendation_candidates(selected.id, options, normalized, objectives),
    }
