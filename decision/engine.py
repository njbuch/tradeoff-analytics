from __future__ import annotations

from dataclasses import dataclass, replace
from math import isfinite
from typing import Any, Iterable

import numpy as np

from .layouts import compute_layout


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


@dataclass(frozen=True)
class ObjectiveMetadata:
    key: str
    label: str
    goal: str
    weight: float
    minimum: float
    maximum: float
    target: float | None
    formatter: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "goal": self.goal,
            "weight": self.weight,
            "min": self.minimum,
            "max": self.maximum,
            "target": self.target,
            "formatter": self.formatter,
        }


@dataclass(frozen=True)
class AlternativeResult:
    id: str
    name: str
    gain: float
    loss: float
    ratio: float
    explanation: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "gain": self.gain,
            "loss": self.loss,
            "ratio": self.ratio,
            "explanation": self.explanation,
        }


@dataclass(frozen=True)
class OptionResult:
    id: str
    name: str
    description: str
    values: dict[str, Any]
    scores: dict[str, float]
    missing: dict[str, bool]
    pareto: bool
    dominated_by: tuple[str, ...]
    reason: str

    def decision_dict(self) -> dict[str, Any]:
        dominated_by = list(self.dominated_by)
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "values": self.values,
            "scores": self.scores,
            "missing": self.missing,
            "pareto": self.pareto,
            "dominated_by": dominated_by,
            "dominatedBy": dominated_by,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class DecisionResult:
    feasible_options: tuple[OptionResult, ...]
    objective_keys: tuple[str, ...]
    normalized_scores: np.ndarray
    pareto_mask: np.ndarray
    dominated_by: dict[str, list[str]]
    recommendations: dict[str, tuple[AlternativeResult, ...]]
    objective_metadata: tuple[ObjectiveMetadata, ...]
    selected_id: str | None
    total_count: int


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
) -> list[AlternativeResult]:
    selected_scores = normalized.get(selected_id)
    if selected_scores is None:
        return []

    recommendations: list[AlternativeResult] = []
    for option in options:
        if option.id == selected_id:
            continue
        gain, loss, ratio = weighted_delta(selected_scores, normalized[option.id], objectives)
        if gain <= EPSILON:
            continue
        recommendations.append(
            AlternativeResult(
                id=option.id,
                name=option.name,
                gain=gain,
                loss=loss,
                ratio=ratio,
                explanation=explain_delta(selected_scores, normalized[option.id], objectives),
            )
        )

    recommendations.sort(key=lambda item: (item.ratio, item.gain, -item.loss), reverse=True)
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


def compute_decision(
    options: list[Option],
    objectives: list[Objective],
    filters: dict[str, dict[str, Any]] | None = None,
    selected_id: str | None = None,
) -> DecisionResult:
    filters = filters or {}
    feasible = apply_filters(options, filters)
    normalized, missing, ranges = normalize_options(feasible, objectives)
    objective_keys = [objective.key for objective in objectives]
    pareto, dominated_by = pareto_frontier(feasible, normalized, objective_keys)
    normalized_matrix = np.array(
        [[normalized[option.id].get(key, 0.0) for key in objective_keys] for option in feasible],
        dtype=float,
    )
    pareto_mask = np.array([pareto[option.id] for option in feasible], dtype=bool)

    recommendations = {
        option.id: tuple(recommendation_candidates(option.id, feasible, normalized, objectives)) for option in feasible
    }
    if selected_id is None and feasible:
        selected_id = feasible[0].id
    if selected_id is not None and selected_id not in {option.id for option in feasible}:
        selected_id = feasible[0].id if feasible else None

    option_results: list[OptionResult] = []
    for option in feasible:
        dominators = dominated_by[option.id]
        option_results.append(
            OptionResult(
                id=option.id,
                name=option.name,
                description=option.description,
                values=option.values,
                scores=normalized[option.id],
                missing=missing[option.id],
                pareto=pareto[option.id],
                dominated_by=tuple(dominators[:5]),
                reason=pareto_reason(option, pareto[option.id], dominators, feasible),
            )
        )

    metadata = tuple(
        ObjectiveMetadata(
            key=objective.key,
            label=objective.label,
            goal=objective.goal,
            weight=objective.weight,
            minimum=ranges.get(objective.key, (0.0, 0.0))[0],
            maximum=ranges.get(objective.key, (0.0, 0.0))[1],
            target=objective.target,
            formatter=objective.formatter,
        )
        for objective in objectives
    )

    return DecisionResult(
        feasible_options=tuple(option_results),
        objective_keys=tuple(objective_keys),
        normalized_scores=normalized_matrix,
        pareto_mask=pareto_mask,
        dominated_by=dominated_by,
        recommendations=recommendations,
        objective_metadata=metadata,
        selected_id=selected_id,
        total_count=len(options),
    )


def evaluate_tradeoffs(
    options: list[Option],
    objectives: list[Objective],
    filters: dict[str, dict[str, Any]] | None = None,
    selected_id: str | None = None,
    layout_mode: str = "polygon",
) -> dict[str, Any]:
    decision = compute_decision(options, objectives, filters=filters, selected_id=selected_id)
    layout = compute_layout(
        [option.id for option in decision.feasible_options],
        decision.normalized_scores,
        list(decision.objective_keys),
        layout_mode,
        pareto_mask=decision.pareto_mask,
        objective_labels={metadata.key: metadata.label for metadata in decision.objective_metadata},
    )
    return merge_decision_layout(decision, layout)


def merge_decision_layout(decision: DecisionResult, layout: dict[str, Any]) -> dict[str, Any]:
    anchors = {
        anchor["key"]: {
            "x": anchor["x"],
            "y": anchor["y"],
            "angle": anchor.get("angle", 0.0),
            "label": anchor.get("label", anchor["key"]),
        }
        for anchor in layout["anchors"]
    }
    response_options: list[dict[str, Any]] = []
    for option in decision.feasible_options:
        layout_position = layout["positions"].get(
            option.id,
            {"x": 0.0, "y": 0.0, "semanticX": 0.0, "semanticY": 0.0, "source": "polygon"},
        )
        option_payload = option.decision_dict()
        option_payload.update(
            {
                "x": layout_position["x"],
                "y": layout_position["y"],
                "position": {"x": layout_position["x"], "y": layout_position["y"]},
                "layout": layout_position,
            }
        )
        response_options.append(option_payload)

    recommendations = {
        option_id: [alternative.to_dict() for alternative in alternatives]
        for option_id, alternatives in decision.recommendations.items()
    }
    selected = build_selected_from_decision(decision, recommendations)
    pareto_count = int(np.sum(decision.pareto_mask))
    summary = {
        "total": decision.total_count,
        "feasible": len(decision.feasible_options),
        "pareto": pareto_count,
        "dominated": len(decision.feasible_options) - pareto_count,
    }
    layout_diagnostics = layout.get("diagnostics", layout.get("layoutDiagnostics", {}))
    return {
        "decision": {
            "objectiveKeys": list(decision.objective_keys),
            "feasibleCount": len(decision.feasible_options),
            "paretoCount": pareto_count,
        },
        "objectives": [metadata.to_dict() for metadata in decision.objective_metadata],
        "anchors": anchors,
        "layout": {
            "mode": layout["mode"],
            "fallback": layout["fallback"],
            "warnings": layout["warnings"],
            "anchors": layout["anchors"],
            "diagnostics": layout_diagnostics,
            "layoutDiagnostics": layout_diagnostics,
        },
        "options": response_options,
        "recommendations": recommendations,
        "selected": selected,
        "summary": summary,
    }


def pareto_reason(option: Option, is_pareto: bool, dominators: list[str], options: list[Option]) -> str:
    if is_pareto:
        return "On the Pareto frontier because no feasible option is at least as good on every active objective while improving one."
    names = {candidate.id: candidate.name for candidate in options}
    visible = [names.get(option_id, option_id) for option_id in dominators[:3]]
    return f"Dominated by {', '.join(visible)} on the active objectives."


def build_selected_from_decision(
    decision: DecisionResult,
    recommendations: dict[str, list[dict[str, Any]]],
) -> dict[str, Any] | None:
    selected_id = decision.selected_id
    if selected_id is None:
        return None
    selected = next((option for option in decision.feasible_options if option.id == selected_id), None)
    if selected is None:
        return None
    payload = selected.decision_dict()
    payload["alternatives"] = recommendations.get(selected.id, [])
    return payload
