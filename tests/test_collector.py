import importlib.util
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location("collector", Path(__file__).parents[1] / "scripts" / "update.py")
collector = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(collector)


class ParserTests(unittest.TestCase):
    def test_pool_lookup_is_by_id_not_position(self):
        pools = [{"id": "orchard"}, {"id": "ironwood", "chainValueZat": 0}]
        self.assertEqual(collector.find_pool(pools, "ironwood")["chainValueZat"], 0)

    def test_absent_value_remains_none(self):
        self.assertIsNone(collector.optional_int(None))

    def test_net_change_uses_closest_prior_snapshot(self):
        history = [
            {"timestamp": 100, "orchard": 10},
            {"timestamp": 200, "orchard": 14},
            {"timestamp": 300, "orchard": 8},
        ]
        self.assertEqual(collector.net_change(history, "orchard", 100), -6)

    def test_activation_change_requires_two_real_points(self):
        history = [{"height": collector.ACTIVATION_HEIGHT, "orchard": 10}]
        self.assertIsNone(collector.change_since_height(history, "orchard", collector.ACTIVATION_HEIGHT))

    def test_history_merge_prefers_denser_source(self):
        merged = collector.merge_history(
            [{"height": 1, "timestamp": 1, "orchard": 10}],
            [{"height": 1, "timestamp": 2, "orchard": 11}, {"height": 2, "timestamp": 3, "orchard": 12}],
        )
        self.assertEqual([row["height"] for row in merged], [1, 2])
        self.assertEqual(merged[0]["orchard"], 11)

    def test_percent_change_uses_interval_opening_balance(self):
        self.assertEqual(collector.change_bps(110, 10), 100_000)
        self.assertIsNone(collector.change_bps(0, 0))


class StateMachineTests(unittest.TestCase):
    def test_pre_activation_without_zebra_is_pending(self):
        state, rows = collector.derive_ironwood(None, collector.ACTIVATION_HEIGHT - 1, {})
        self.assertEqual(state["status"], "pending_activation")
        self.assertIsNone(state["balance_zatoshis"])
        self.assertEqual(rows, [])

    def test_zero_from_public_source_is_supported(self):
        state, _ = collector.derive_ironwood(None, collector.ACTIVATION_HEIGHT - 1, {"ironwood_zatoshis": 0})
        self.assertTrue(state["supported"])
        self.assertEqual(state["balance_zatoshis"], 0)

    def test_post_activation_without_data_waits(self):
        state, _ = collector.derive_ironwood(None, collector.ACTIVATION_HEIGHT, {})
        self.assertEqual(state["status"], "activation_reached_waiting_data")

    def test_zebra_error_does_not_publish_private_url(self):
        class BrokenZebra:
            def call(self, method, params=None):
                raise RuntimeError("https://private-node.example secret")
        state, _ = collector.derive_ironwood(BrokenZebra(), collector.ACTIVATION_HEIGHT, {})
        self.assertEqual(state["status"], "source_error")
        self.assertNotIn("private-node", state["last_error"])

    def test_backfill_replaces_reorged_descendants(self):
        class FakeZebra:
            def call(self, method, params=None):
                height = params[0]
                return {
                    "height": height,
                    "hash": f"canonical-{height}",
                    "time": height,
                    "valuePools": [{
                        "id": "ironwood", "monitored": True,
                        "chainValueZat": height, "valueDeltaZat": 1,
                    }],
                }
        rows = [{
            "height": collector.ACTIVATION_HEIGHT,
            "block_hash": "orphaned",
            "timestamp": 1,
            "balance_zatoshis": 1,
            "value_delta_zatoshis": 1,
        }]
        result = collector.backfill_ironwood(FakeZebra(), collector.ACTIVATION_HEIGHT + 1, rows)
        self.assertEqual(result[0]["block_hash"], f"canonical-{collector.ACTIVATION_HEIGHT}")
        self.assertEqual(len(result), 2)


if __name__ == "__main__":
    unittest.main()
