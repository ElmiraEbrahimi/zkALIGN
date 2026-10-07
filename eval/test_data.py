import heapq
import itertools
import unittest
import pm4py
from pm4py.objects.log.obj import Trace, Event
from eval.data import align, config_from_export
from scripts.healthcare_pipeline import export_circuit_model, classify_moves


def dijkstra(events, model):
    """Independent explicit product search, used only on tiny bounded nets."""
    im = tuple(model["initial_marking"])
    fm = tuple(model["final_marking"])
    queue = [(0, 0, im)]
    best = {(0, im): 0}
    while queue:
        cost, pos, mark = heapq.heappop(queue)
        if cost != best[(pos, mark)]:
            continue
        if pos == len(events) and mark == fm:
            return cost
        successors = []
        if pos < len(events):
            successors.append((1, pos + 1, mark))
        for t in model["transitions"]:
            pre = t["input_vector"]
            post = t["output_vector"]
            if any(m < x for m, x in zip(mark, pre)):
                continue
            nxt = tuple(m - x + y for m, x, y in zip(mark, pre, post))
            if any(m > 1 for m in nxt):
                raise AssertionError("unsafe fixture")
            successors.append((int(not t["silent"]), pos, nxt))
            if pos < len(events) and t["label"] == events[pos]:
                successors.append((0, pos + 1, nxt))
        for delta, p, m in successors:
            nc = cost + delta
            if nc < best.get((p, m), float("inf")):
                best[(p, m)] = nc
                heapq.heappush(queue, (nc, p, m))
    raise AssertionError("no complete alignment")


class OracleTests(unittest.TestCase):
    def test_unit_cost_against_independent_product_search(self):
        for expression in [
            "->('A','B')",
            "+('A','B')",
            "X('A','B')",
            "*('A','B')",
            "->(tau,'A')",
        ]:
            net, im, fm = pm4py.convert_to_petri_net(
                pm4py.parse_process_tree(expression)
            )
            encoding = {"A": 1, "B": 2, "X": 3}
            model = export_circuit_model(net, im, fm, encoding)
            for length in range(4):
                for events in itertools.product(("A", "B", "X"), repeat=length):
                    trace = Trace([Event({"concept:name": a}) for a in events])
                    result = align(trace, net, im, fm)
                    self.assertIsNotNone(result)
                    self.assertEqual(
                        result["cost"], dijkstra(events, model), (expression, events)
                    )
                    moves, _ = classify_moves(result["alignment"], net, im, encoding)
                    self.assertEqual(
                        sum(m["reference_cost"] for m in moves), result["cost"]
                    )
            self.assertEqual(config_from_export(model, 8, 32)["activity_count"], 3)


if __name__ == "__main__":
    unittest.main()
