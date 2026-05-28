from __future__ import annotations

from django.test import Client, SimpleTestCase

from decision.catalog import catalog_payload, load_catalog


class DatasetCatalogTests(SimpleTestCase):
    def test_cars_catalog_remains_available_by_default(self):
        catalog = load_catalog()
        payload = catalog_payload()

        self.assertEqual(catalog["id"], "cars")
        self.assertEqual(payload["datasetId"], "cars")
        self.assertTrue(any(objective.key == "price" for objective in catalog["objectives"]))
        self.assertGreater(len(catalog["options"]), 0)

    def test_ev_catalog_is_loaded_on_demand_with_dataset_specific_fields(self):
        catalog = load_catalog("evs")
        objective_keys = {objective.key for objective in catalog["objectives"]}
        filter_keys = {field["key"] for field in catalog["filter_fields"]}

        self.assertEqual(catalog["id"], "evs")
        self.assertGreater(len(catalog["options"]), 100)
        self.assertIn("estimated_range_km", objective_keys)
        self.assertIn("average_consumption", objective_keys)
        self.assertIn("dc_max_power", objective_keys)
        self.assertIn("usable_battery_size", filter_keys)
        self.assertTrue(catalog["scenarios"])

    def test_catalog_api_can_switch_datasets(self):
        client = Client()

        cars = client.get("/api/catalog/?dataset=cars").json()
        evs = client.get("/api/catalog/?dataset=evs").json()

        self.assertEqual(cars["datasetId"], "cars")
        self.assertEqual(evs["datasetId"], "evs")
        self.assertNotEqual(cars["subject"], evs["subject"])
        self.assertTrue(any(dataset["id"] == "evs" for dataset in cars["datasets"]))

    def test_evaluate_api_uses_requested_ev_dataset(self):
        client = Client()
        response = client.post(
            "/api/evaluate/",
            {
                "datasetId": "evs",
                "layoutMode": "polygon",
                "objectives": [
                    {"key": "estimated_range_km", "goal": "max", "weight": 1},
                    {"key": "average_consumption", "goal": "min", "weight": 1},
                    {"key": "dc_max_power", "goal": "max", "weight": 1},
                ],
                "filters": {"estimated_range_km": {"min": 250}},
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertGreater(payload["summary"]["feasible"], 0)
        self.assertEqual(
            payload["decision"]["objectiveKeys"],
            ["estimated_range_km", "average_consumption", "dc_max_power"],
        )
        self.assertIn("estimated_range_km", payload["options"][0]["scores"])
