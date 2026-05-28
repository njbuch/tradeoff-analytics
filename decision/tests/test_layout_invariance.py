from __future__ import annotations

from copy import deepcopy
from random import Random

from django.test import SimpleTestCase

from decision.catalog import load_catalog
from decision.engine import compute_decision, configure_objectives, evaluate_tradeoffs, merge_decision_layout


class LayoutInvarianceTests(SimpleTestCase):
    def test_full_response_is_invariant_except_layout_fields(self):
        polygon = self._evaluate(["price", "MPGCombined", "averageRating"], layout_mode="polygon")
        som = self._evaluate(["price", "MPGCombined", "averageRating"], layout_mode="som")

        self.assertEqual(_strip_layout(polygon), _strip_layout(som))

    def test_pareto_invariance_across_objective_counts_filters_and_weights(self):
        cases = [
            (["price", "MPGCombined"], {}, {}),
            (["price", "MPGCombined", "averageRating"], {"price": {"max": 60000}}, {}),
            (
                ["price", "MPGCombined", "averageRating", "power", "engineSize"],
                {"price": {"max": 90000}, "MPGCombined": {"min": 20}},
                {"power": 2.5, "engineSize": 0.5},
            ),
        ]
        for keys, filters, weights in cases:
            with self.subTest(keys=keys):
                polygon = self._evaluate(keys, filters=filters, weights=weights, layout_mode="polygon")
                som = self._evaluate(keys, filters=filters, weights=weights, layout_mode="som")
                self.assertEqual(_pareto_ids(polygon), _pareto_ids(som))

    def test_recommendation_invariance_for_every_option(self):
        polygon = self._evaluate(["price", "MPGCombined", "averageRating", "power"], layout_mode="polygon")
        som = self._evaluate(["price", "MPGCombined", "averageRating", "power"], layout_mode="som")

        self.assertEqual(polygon["recommendations"], som["recommendations"])

    def test_score_invariance_for_every_option_and_objective(self):
        polygon = self._evaluate(["price", "MPGCombined", "averageRating", "power"], layout_mode="polygon")
        som = self._evaluate(["price", "MPGCombined", "averageRating", "power"], layout_mode="som")
        polygon_scores = {option["id"]: option["scores"] for option in polygon["options"]}
        som_scores = {option["id"]: option["scores"] for option in som["options"]}

        self.assertEqual(polygon_scores.keys(), som_scores.keys())
        for option_id, scores in polygon_scores.items():
            for key, score in scores.items():
                self.assertAlmostEqual(score, som_scores[option_id][key], places=12)

    def test_randomized_layout_coordinates_do_not_contaminate_decision_payload(self):
        catalog = load_catalog()
        objectives = configure_objectives(
            catalog["objectives"],
            [
                {"key": "price", "goal": "min", "weight": 1},
                {"key": "MPGCombined", "goal": "max", "weight": 1},
                {"key": "averageRating", "goal": "max", "weight": 1},
            ],
        )
        decision = compute_decision(catalog["options"], objectives, filters={"price": {"max": 60000}})
        first = merge_decision_layout(decision, _random_layout(decision, seed=1))
        second = merge_decision_layout(decision, _random_layout(decision, seed=2))

        self.assertEqual(_strip_layout(first), _strip_layout(second))

    def _evaluate(
        self,
        keys: list[str],
        *,
        filters: dict | None = None,
        weights: dict[str, float] | None = None,
        layout_mode: str,
    ) -> dict:
        catalog = load_catalog()
        weights = weights or {}
        requested = [
            {
                "key": key,
                "goal": "min" if key == "price" else "max",
                "weight": weights.get(key, 1),
            }
            for key in keys
        ]
        objectives = configure_objectives(catalog["objectives"], requested)
        return evaluate_tradeoffs(catalog["options"], objectives, filters=filters or {}, layout_mode=layout_mode)


def _strip_layout(response: dict) -> dict:
    cleaned = deepcopy(response)
    cleaned.pop("layout", None)
    cleaned.pop("anchors", None)
    for option in cleaned.get("options", []):
        option.pop("x", None)
        option.pop("y", None)
        option.pop("position", None)
        option.pop("layout", None)
    return cleaned


def _pareto_ids(response: dict) -> list[str]:
    return sorted(option["id"] for option in response["options"] if option["pareto"])


def _random_layout(decision, seed: int) -> dict:
    rng = Random(seed)
    positions = {
        option.id: {
            "x": rng.uniform(-1, 1),
            "y": rng.uniform(-1, 1),
            "semanticX": rng.uniform(-1, 1),
            "semanticY": rng.uniform(-1, 1),
            "source": "random",
        }
        for option in decision.feasible_options
    }
    anchors = [
        {"key": key, "label": key, "x": rng.uniform(-1, 1), "y": rng.uniform(-1, 1)}
        for key in decision.objective_keys
    ]
    return {
        "mode": "random",
        "fallback": False,
        "warnings": [],
        "anchors": anchors,
        "positions": positions,
        "diagnostics": {"method": "random_test_layout"},
        "layoutDiagnostics": {"method": "random_test_layout"},
    }
