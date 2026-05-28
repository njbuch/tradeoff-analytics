from django.test import SimpleTestCase

from decision.engine import (
    Objective,
    Option,
    dominates,
    evaluate_tradeoffs,
    normalize_options,
    normalize_value,
    pareto_frontier,
    recommendation_candidates,
)


class NormalizationTests(SimpleTestCase):
    def test_normalizes_min_max_and_target_objectives(self):
        max_objective = Objective(key="mpg", label="MPG", goal="max")
        min_objective = Objective(key="price", label="Price", goal="min")
        target_objective = Objective(key="comfort", label="Comfort", goal="target", target=7)

        self.assertEqual(normalize_value(30, max_objective, 20, 40), 0.5)
        self.assertEqual(normalize_value(30000, min_objective, 20000, 40000), 0.5)
        self.assertEqual(normalize_value(7, target_objective, 1, 10), 1.0)
        self.assertAlmostEqual(normalize_value(4, target_objective, 1, 10), 0.5)

    def test_missing_values_are_reported_and_scored_as_zero(self):
        options = [Option(id="a", name="A", description="", values={"mpg": None})]
        objective = Objective(key="mpg", label="MPG", goal="max", minimum=0, maximum=50)

        normalized, missing, _ = normalize_options(options, [objective])

        self.assertEqual(normalized["a"]["mpg"], 0.0)
        self.assertTrue(missing["a"]["mpg"])


class ParetoTests(SimpleTestCase):
    def test_dominates_requires_all_scores_at_least_equal_and_one_better(self):
        self.assertTrue(dominates({"a": 1, "b": 0.7}, {"a": 1, "b": 0.4}, ["a", "b"]))
        self.assertFalse(dominates({"a": 1, "b": 0.4}, {"a": 1, "b": 0.7}, ["a", "b"]))
        self.assertFalse(dominates({"a": 1, "b": 0.7}, {"a": 1, "b": 0.7}, ["a", "b"]))

    def test_pareto_frontier_marks_dominated_options(self):
        options = [
            Option(id="a", name="A", description="", values={}),
            Option(id="b", name="B", description="", values={}),
            Option(id="c", name="C", description="", values={}),
        ]
        normalized = {
            "a": {"price": 0.8, "mpg": 0.9},
            "b": {"price": 0.7, "mpg": 0.8},
            "c": {"price": 0.9, "mpg": 0.5},
        }

        pareto, dominated_by = pareto_frontier(options, normalized, ["price", "mpg"])

        self.assertTrue(pareto["a"])
        self.assertFalse(pareto["b"])
        self.assertTrue(pareto["c"])
        self.assertEqual(dominated_by["b"], ["a"])


class RecommendationTests(SimpleTestCase):
    def test_recommendations_rank_high_gain_low_loss_candidates(self):
        objectives = [
            Objective(key="mpg", label="MPG", weight=1),
            Objective(key="power", label="Power", weight=1),
        ]
        options = [
            Option(id="selected", name="Selected", description="", values={}),
            Option(id="balanced", name="Balanced", description="", values={}),
            Option(id="lopsided", name="Lopsided", description="", values={}),
        ]
        normalized = {
            "selected": {"mpg": 0.5, "power": 0.5},
            "balanced": {"mpg": 0.8, "power": 0.45},
            "lopsided": {"mpg": 1.0, "power": 0.0},
        }

        recommendations = recommendation_candidates("selected", options, normalized, objectives)

        self.assertEqual(recommendations[0].id, "balanced")
        self.assertIn("+30% MPG", recommendations[0].explanation)

    def test_evaluate_returns_positions_and_selected_explanations(self):
        objectives = [
            Objective(key="price", label="Price", goal="min", minimum=10000, maximum=30000),
            Objective(key="mpg", label="MPG", goal="max", minimum=20, maximum=40),
            Objective(key="power", label="Power", goal="max", minimum=100, maximum=300),
        ]
        options = [
            Option(id="a", name="A", description="", values={"price": 10000, "mpg": 35, "power": 200}),
            Option(id="b", name="B", description="", values={"price": 20000, "mpg": 25, "power": 150}),
        ]

        result = evaluate_tradeoffs(options, objectives, selected_id="b")

        self.assertEqual(result["summary"]["feasible"], 2)
        self.assertIn("x", result["options"][0]["position"])
        self.assertFalse(result["selected"]["pareto"])
        self.assertTrue(result["selected"]["alternatives"])
