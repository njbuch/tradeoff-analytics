from __future__ import annotations

from dataclasses import dataclass
from hashlib import blake2b
from math import ceil, cos, isfinite, pi, sin, sqrt
from typing import Any

import numpy as np


MAX_TRAINING_OPTIONS = 2000


@dataclass(frozen=True)
class LayoutResult:
    mode: str
    fallback: bool
    warnings: list[str]
    anchors: list[dict[str, Any]]
    positions: dict[str, dict[str, float]]
    layout_diagnostics: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "fallback": self.fallback,
            "warnings": self.warnings,
            "anchors": self.anchors,
            "positions": self.positions,
            "diagnostics": self.layout_diagnostics,
            "layoutDiagnostics": self.layout_diagnostics,
        }


def compute_layout(
    option_ids: list[str],
    normalized_scores: np.ndarray,
    objective_keys: list[str],
    layout_mode: str,
    pareto_mask: np.ndarray | None = None,
    seed: int = 42,
    objective_labels: dict[str, str] | None = None,
) -> dict[str, Any]:
    option_ids = [str(option_id) for option_id in option_ids]
    labels = objective_labels or {key: key for key in objective_keys}
    pareto_array = None if pareto_mask is None else np.asarray(pareto_mask, dtype=bool)

    scores = _coerce_scores(normalized_scores, len(option_ids), len(objective_keys))
    requested_mode = layout_mode if layout_mode in {"polygon", "som"} else "polygon"
    if requested_mode == "som":
        result = compute_som_layout(scores, objective_keys, option_ids, labels, pareto_mask=pareto_array, seed=seed)
    else:
        result = compute_polygon_layout(scores, objective_keys, option_ids, labels)
    return result.to_dict()


def compute_polygon_layout(
    normalized_scores: np.ndarray,
    objective_keys: list[str],
    option_ids: list[str],
    labels: dict[str, str] | None = None,
    *,
    fallback: bool = False,
    warnings: list[str] | None = None,
) -> LayoutResult:
    labels = labels or {key: key for key in objective_keys}
    anchors = polygon_anchors(objective_keys, labels)
    anchor_by_key = {anchor["key"]: anchor for anchor in anchors}
    positions: dict[str, dict[str, float]] = {}

    for row, option_id in zip(normalized_scores, option_ids):
        total = float(np.sum(np.maximum(row, 0.0)))
        if total <= 1e-9:
            x = 0.0
            y = 0.0
        else:
            x = 0.0
            y = 0.0
            for index, key in enumerate(objective_keys):
                weight = max(float(row[index]), 0.0) / total
                x += weight * float(anchor_by_key[key]["x"])
                y += weight * float(anchor_by_key[key]["y"])
        positions[str(option_id)] = _position(x, y, "polygon")

    return LayoutResult(
        mode="polygon",
        fallback=fallback,
        warnings=warnings or [],
        anchors=anchors,
        positions=positions,
        layout_diagnostics={
            "method": "anchored_polygon",
            "gridWidth": None,
            "gridHeight": None,
            "iterations": None,
            "quantizationError": None,
            "topographicError": None,
        },
    )


def compute_som_layout(
    normalized_scores: np.ndarray,
    objective_keys: list[str],
    option_ids: list[str],
    labels: dict[str, str] | None = None,
    *,
    pareto_mask: np.ndarray | None = None,
    seed: int = 42,
) -> LayoutResult:
    labels = labels or {key: key for key in objective_keys}
    warnings: list[str] = []
    option_count, objective_count = normalized_scores.shape

    if option_count < 10:
        return compute_polygon_layout(
            normalized_scores,
            objective_keys,
            option_ids,
            labels,
            fallback=True,
            warnings=["SOM layout requires at least 10 feasible options; using polygon layout."],
        )
    if objective_count < 2:
        return compute_polygon_layout(
            normalized_scores,
            objective_keys,
            option_ids,
            labels,
            fallback=True,
            warnings=["SOM layout requires at least 2 active objectives; using polygon layout."],
        )

    try:
        training_scores = normalized_scores
        if option_count > MAX_TRAINING_OPTIONS:
            training_scores = _sample_training_rows(normalized_scores, pareto_mask, seed)
            warnings.append(
                f"SOM trained on a deterministic sample of {len(training_scores)} options out of {option_count}."
            )

        grid_side = max(6, min(24, ceil(sqrt(5 * sqrt(option_count)))))
        iterations = max(500, min(5000, 20 * len(training_scores)))
        som_class = _load_minisom()
        som = som_class(
            grid_side,
            grid_side,
            objective_count,
            sigma=max(1.0, grid_side / 4),
            learning_rate=0.5,
            neighborhood_function="gaussian",
            random_seed=seed,
        )
        som.random_weights_init(training_scores)
        som.train_random(training_scores, iterations)

        raw_positions = np.array([_winner_to_point(som.winner(row), grid_side, grid_side) for row in normalized_scores])
        ideal_positions = np.array(
            [
                _winner_to_point(som.winner(_ideal_vector(index, objective_count)), grid_side, grid_side)
                for index in range(objective_count)
            ]
        )
        target_anchors = np.array([[anchor["x"], anchor["y"]] for anchor in polygon_anchors(objective_keys, labels)])
        oriented_positions = _orient_positions(raw_positions, ideal_positions, target_anchors)
        oriented_positions = _fit_to_unit_square(oriented_positions)
        oriented_positions = _apply_deterministic_jitter(oriented_positions, option_ids, seed)

        positions = {
            str(option_id): _position(float(point[0]), float(point[1]), "som") for option_id, point in zip(option_ids, oriented_positions)
        }
        return LayoutResult(
            mode="som",
            fallback=False,
            warnings=warnings,
            anchors=polygon_anchors(objective_keys, labels),
            positions=positions,
            layout_diagnostics={
                "method": "som_minisom",
                "gridWidth": grid_side,
                "gridHeight": grid_side,
                "iterations": iterations,
                "quantizationError": float(som.quantization_error(normalized_scores)),
                "topographicError": None,
                "orientation": "affine_procrustes",
            },
        )
    except Exception as exc:
        return compute_polygon_layout(
            normalized_scores,
            objective_keys,
            option_ids,
            labels,
            fallback=True,
            warnings=[f"SOM layout failed ({exc.__class__.__name__}); using polygon layout."],
        )


def polygon_anchors(objective_keys: list[str], labels: dict[str, str] | None = None) -> list[dict[str, Any]]:
    labels = labels or {key: key for key in objective_keys}
    count = len(objective_keys)
    anchors: list[dict[str, Any]] = []
    for index, key in enumerate(objective_keys):
        angle = (2 * pi * index / count) - (pi / 2) if count else 0.0
        anchors.append(
            {
                "key": key,
                "label": labels.get(key, key),
                "x": cos(angle),
                "y": sin(angle),
                "angle": angle,
            }
        )
    return anchors


def _load_minisom():
    from minisom import MiniSom

    return MiniSom


def _coerce_scores(scores: np.ndarray, rows: int, columns: int) -> np.ndarray:
    array = np.asarray(scores, dtype=float)
    if array.shape != (rows, columns):
        raise ValueError(f"Expected normalized_scores shape {(rows, columns)}, got {array.shape}.")
    array = np.nan_to_num(array, nan=0.0, posinf=1.0, neginf=0.0)
    return np.clip(array, 0.0, 1.0)


def _winner_to_point(winner: tuple[int, int], width: int, height: int) -> tuple[float, float]:
    x = 0.0 if width <= 1 else 2 * (winner[0] / (width - 1)) - 1
    y = 0.0 if height <= 1 else 2 * (winner[1] / (height - 1)) - 1
    return float(x), float(y)


def _ideal_vector(index: int, length: int) -> np.ndarray:
    vector = np.zeros(length)
    vector[index] = 1.0
    return vector


def _orient_positions(raw_positions: np.ndarray, source_anchors: np.ndarray, target_anchors: np.ndarray) -> np.ndarray:
    source_center = source_anchors.mean(axis=0)
    target_center = target_anchors.mean(axis=0)
    source = source_anchors - source_center
    target = target_anchors - target_center
    if np.linalg.norm(source) <= 1e-9:
        return raw_positions

    covariance = source.T @ target
    u, _, vt = np.linalg.svd(covariance)
    rotation = u @ vt
    if np.linalg.det(rotation) < 0:
        vt[-1, :] *= -1
        rotation = u @ vt
    scale_denominator = np.sum(source**2)
    scale = 1.0 if scale_denominator <= 1e-9 else float(np.trace((source @ rotation).T @ target) / scale_denominator)
    return (raw_positions - source_center) @ rotation * scale + target_center


def _fit_to_unit_square(points: np.ndarray) -> np.ndarray:
    if points.size == 0:
        return points
    centered = points - points.mean(axis=0)
    max_abs = float(np.max(np.abs(centered)))
    if max_abs <= 1e-9:
        return centered
    return np.clip(centered / max_abs, -1.0, 1.0)


def _apply_deterministic_jitter(points: np.ndarray, option_ids: list[str], seed: int) -> np.ndarray:
    result = points.copy()
    buckets: dict[tuple[int, int], list[int]] = {}
    for index, point in enumerate(points):
        key = (round(float(point[0]), 3), round(float(point[1]), 3))
        buckets.setdefault(key, []).append(index)

    for indexes in buckets.values():
        if len(indexes) <= 1:
            continue
        for offset_index, index in enumerate(indexes):
            angle = _stable_unit_float(option_ids[index], seed, "angle") * 2 * pi
            radius = min(0.035, 0.012 * (offset_index + 1))
            result[index, 0] += cos(angle) * radius
            result[index, 1] += sin(angle) * radius
    return np.clip(result, -1.05, 1.05)


def _sample_training_rows(scores: np.ndarray, pareto_mask: np.ndarray | None, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    option_count = len(scores)
    if pareto_mask is None:
        return scores[np.sort(rng.choice(option_count, size=MAX_TRAINING_OPTIONS, replace=False))]

    pareto_indexes = np.flatnonzero(pareto_mask)
    dominated_indexes = np.flatnonzero(~pareto_mask)
    remaining = max(0, MAX_TRAINING_OPTIONS - len(pareto_indexes))
    if len(dominated_indexes) > remaining:
        dominated_indexes = np.sort(rng.choice(dominated_indexes, size=remaining, replace=False))
    indexes = np.sort(np.concatenate([pareto_indexes, dominated_indexes]))[:MAX_TRAINING_OPTIONS]
    return scores[indexes]


def _stable_unit_float(option_id: str, seed: int, salt: str) -> float:
    digest = blake2b(f"{seed}:{salt}:{option_id}".encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big") / float(2**64 - 1)


def _position(x: float, y: float, source: str) -> dict[str, Any]:
    if not isfinite(x):
        x = 0.0
    if not isfinite(y):
        y = 0.0
    x = max(-1.05, min(1.05, x))
    y = max(-1.05, min(1.05, y))
    return {
        "x": x,
        "y": y,
        "semanticX": x,
        "semanticY": y,
        "source": source,
    }
