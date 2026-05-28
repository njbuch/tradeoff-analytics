from __future__ import annotations

from math import isfinite
from unittest.mock import patch

import numpy as np
from django.test import Client, SimpleTestCase

from decision.layouts import compute_layout, compute_polygon_layout, compute_som_layout


class LayoutTests(SimpleTestCase):
    def test_som_layout_is_deterministic_for_same_inputs(self):
        scores = self._sample_scores(32, 4)
        option_ids = [f"car_{index}" for index in range(len(scores))]
        keys = ["price", "mpg", "power", "rating"]

        first = compute_layout(option_ids, scores, keys, "som", seed=7)
        second = compute_layout(option_ids, scores, keys, "som", seed=7)

        self.assertEqual(first["mode"], "som")
        self.assertFalse(first["fallback"])
        self.assertEqual(first["positions"], second["positions"])

    def test_som_falls_back_for_too_few_options(self):
        scores = self._sample_scores(9, 3)
        result = compute_som_layout(scores, ["a", "b", "c"], [f"car_{index}" for index in range(9)])

        self.assertEqual(result.mode, "polygon")
        self.assertTrue(result.fallback)
        self.assertIn("at least 10 feasible options", result.warnings[0])

    def test_som_falls_back_for_too_few_objectives(self):
        scores = self._sample_scores(12, 1)
        result = compute_som_layout(scores, ["a"], [f"car_{index}" for index in range(12)])

        self.assertEqual(result.mode, "polygon")
        self.assertTrue(result.fallback)
        self.assertIn("at least 2 active objectives", result.warnings[0])

    def test_som_falls_back_when_training_raises(self):
        scores = self._sample_scores(12, 3)
        with patch("decision.layouts._load_minisom", side_effect=RuntimeError("boom")):
            result = compute_som_layout(scores, ["a", "b", "c"], [f"car_{index}" for index in range(12)])

        self.assertEqual(result.mode, "polygon")
        self.assertTrue(result.fallback)
        self.assertIn("SOM layout failed", result.warnings[0])

    def test_som_positions_are_finite_and_bounded(self):
        scores = self._sample_scores(40, 5)
        result = compute_som_layout(scores, ["a", "b", "c", "d", "e"], [f"car_{index}" for index in range(40)])

        for position in result.positions.values():
            self.assertTrue(isfinite(position["x"]))
            self.assertTrue(isfinite(position["y"]))
            self.assertGreaterEqual(position["x"], -1.05)
            self.assertLessEqual(position["x"], 1.05)
            self.assertGreaterEqual(position["y"], -1.05)
            self.assertLessEqual(position["y"], 1.05)

    def test_semantic_orientation_keeps_objective_winners_near_matching_anchors(self):
        keys = ["a", "b", "c"]
        scores = []
        ids = []
        for index, key in enumerate(keys):
            vector = np.zeros(len(keys))
            vector[index] = 1.0
            scores.append(vector)
            ids.append(f"winner_{key}")
        for index in range(36):
            scores.append(np.array([(index % 7) / 6, ((index * 2) % 7) / 6, ((index * 3) % 7) / 6]))
            ids.append(f"car_{index}")

        result = compute_som_layout(np.array(scores), keys, ids, seed=11)
        self.assertFalse(result.fallback)
        anchors = {anchor["key"]: anchor for anchor in result.anchors}
        for key in keys:
            position = result.positions[f"winner_{key}"]
            own_distance = _distance(position, anchors[key])
            other_distances = [_distance(position, anchor) for anchor_key, anchor in anchors.items() if anchor_key != key]
            self.assertLess(own_distance, max(other_distances))

    def test_som_preserves_neighbors_better_than_random_layout(self):
        scores, ids, _ = _cluster_scores()
        result = compute_som_layout(scores, ["a", "b", "c"], ids, seed=42)
        coords = _coords(result, ids)

        som_overlap = _neighbor_overlap(scores, coords, k=5)
        random_overlap = np.mean(
            [
                _neighbor_overlap(scores, np.random.default_rng(seed).uniform(-1, 1, size=coords.shape), k=5)
                for seed in range(10)
            ]
        )

        self.assertGreater(som_overlap, random_overlap)

    def test_som_trustworthiness_is_useful_on_clustered_data(self):
        scores, ids, _ = _cluster_scores()
        result = compute_som_layout(scores, ["a", "b", "c"], ids, seed=42)
        coords = _coords(result, ids)

        self.assertGreaterEqual(_trustworthiness(scores, coords, k=5), 0.65)

    def test_som_keeps_synthetic_clusters_closer_internally(self):
        scores, ids, labels = _cluster_scores()
        result = compute_som_layout(scores, ["a", "b", "c"], ids, seed=42)
        coords = _coords(result, ids)

        intra: list[float] = []
        inter: list[float] = []
        for left in range(len(coords)):
            for right in range(left + 1, len(coords)):
                distance = float(np.linalg.norm(coords[left] - coords[right]))
                if labels[left] == labels[right]:
                    intra.append(distance)
                else:
                    inter.append(distance)
        self.assertLess(float(np.mean(intra)), float(np.mean(inter)))

    def test_high_objective_scores_tend_toward_matching_anchor(self):
        scores, ids, _ = _cluster_scores()
        result = compute_som_layout(scores, ["a", "b", "c"], ids, seed=42)
        coords = _coords(result, ids)
        anchors = np.array([[anchor["x"], anchor["y"]] for anchor in result.anchors])
        quartile = len(scores) // 4

        for objective_index in range(scores.shape[1]):
            order = np.argsort(scores[:, objective_index])
            low = order[:quartile]
            high = order[-quartile:]
            low_distance = np.mean(np.linalg.norm(coords[low] - anchors[objective_index], axis=1))
            high_distance = np.mean(np.linalg.norm(coords[high] - anchors[objective_index], axis=1))
            self.assertLess(high_distance, low_distance)

    def test_polygon_layout_contract_stays_backward_compatible(self):
        scores = np.array([[1.0, 0.0, 0.0], [0.2, 0.3, 0.5]])
        result = compute_polygon_layout(scores, ["a", "b", "c"], ["one", "two"])

        self.assertEqual(result.mode, "polygon")
        self.assertIn("one", result.positions)
        self.assertIn("x", result.positions["one"])
        self.assertEqual(result.layout_diagnostics["method"], "anchored_polygon")

    def test_api_contract_includes_polygon_and_som_layout_fields(self):
        client = Client()
        body = {
            "objectives": [
                {"key": "price", "goal": "min", "weight": 1},
                {"key": "MPGCombined", "goal": "max", "weight": 1},
                {"key": "averageRating", "goal": "max", "weight": 1},
            ],
            "filters": {"price": {"max": 60000}, "MPGCombined": {"min": 24}},
        }
        polygon = client.post("/api/evaluate/", body, content_type="application/json").json()
        som = client.post("/api/evaluate/", {**body, "layoutMode": "som"}, content_type="application/json").json()

        self.assertIn("position", polygon["options"][0])
        self.assertIn("layout", polygon)
        self.assertEqual(polygon["layout"]["mode"], "polygon")
        self.assertIn(som["layout"]["mode"], {"som", "polygon"})
        self.assertIn("layoutDiagnostics", som["layout"])

    def _sample_scores(self, rows: int, columns: int) -> np.ndarray:
        values = []
        for row in range(rows):
            values.append([((row + 1) * (column + 2) % 17) / 16 for column in range(columns)])
        return np.array(values, dtype=float)


def _distance(left: dict, right: dict) -> float:
    return ((left["x"] - right["x"]) ** 2 + (left["y"] - right["y"]) ** 2) ** 0.5


def _cluster_scores() -> tuple[np.ndarray, list[str], list[str]]:
    rng = np.random.default_rng(9)
    centers = {
        "a": np.array([0.9, 0.12, 0.12]),
        "b": np.array([0.12, 0.9, 0.12]),
        "c": np.array([0.12, 0.12, 0.9]),
    }
    rows: list[np.ndarray] = []
    ids: list[str] = []
    labels: list[str] = []
    for label, center in centers.items():
        for index in range(18):
            rows.append(np.clip(center + rng.normal(0, 0.045, size=3), 0, 1))
            ids.append(f"{label}_{index}")
            labels.append(label)
    return np.array(rows), ids, labels


def _coords(result, ids: list[str]) -> np.ndarray:
    return np.array([[result.positions[option_id]["x"], result.positions[option_id]["y"]] for option_id in ids])


def _neighbor_overlap(high: np.ndarray, low: np.ndarray, k: int) -> float:
    high_neighbors = _nearest_neighbors(high, k)
    low_neighbors = _nearest_neighbors(low, k)
    overlaps = []
    for index in range(len(high)):
        overlaps.append(len(set(high_neighbors[index]) & set(low_neighbors[index])) / k)
    return float(np.mean(overlaps))


def _nearest_neighbors(values: np.ndarray, k: int) -> list[list[int]]:
    distances = np.linalg.norm(values[:, None, :] - values[None, :, :], axis=2)
    np.fill_diagonal(distances, np.inf)
    return [list(np.argsort(row)[:k]) for row in distances]


def _trustworthiness(high: np.ndarray, low: np.ndarray, k: int) -> float:
    n = len(high)
    high_distances = np.linalg.norm(high[:, None, :] - high[None, :, :], axis=2)
    low_distances = np.linalg.norm(low[:, None, :] - low[None, :, :], axis=2)
    high_rank_order = np.argsort(high_distances, axis=1)
    low_rank_order = np.argsort(low_distances, axis=1)
    high_ranks = np.empty((n, n), dtype=int)
    for row in range(n):
        high_ranks[row, high_rank_order[row]] = np.arange(n)

    penalty = 0
    for row in range(n):
        high_neighbors = set(high_rank_order[row][1 : k + 1])
        low_neighbors = low_rank_order[row][1 : k + 1]
        for neighbor in low_neighbors:
            if neighbor not in high_neighbors:
                penalty += high_ranks[row, neighbor] - k
    normalizer = n * k * (2 * n - 3 * k - 1)
    return 1.0 - (2.0 / normalizer) * penalty
