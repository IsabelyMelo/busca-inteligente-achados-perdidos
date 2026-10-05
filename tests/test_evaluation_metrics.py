from math import sqrt

import pytest

from evaluation.evaluate import latency_stats, metrics, score


def test_manual_pair_metrics_and_negative_query() -> None:
    # q1: esperado em 2º; q2: esperado em 1º; q3: sem correspondência.
    values = {
        "q1": [(1, 0.9, 0), (2, 0.8, 1), (3, 0.1, 0)],
        "q2": [(1, 0.6, 1), (2, 0.3, 0), (3, 0.2, 0)],
        "q3": [(1, 0.7, 0), (2, 0.1, 0), (3, 0.2, 0)],
    }
    rows = [
        {"query_id": query_id, "item_id": item_id, "is_relevant": relevant,
         "cosine_score": value, "levenshtein_score": value}
        for query_id, candidates in values.items()
        for item_id, value, relevant in candidates
    ]
    result = metrics(rows, "cosine", 1.0, 0.5)

    assert result["confusion_matrix"] == {"tp": 2, "fp": 2, "tn": 5, "fn": 0}
    assert (result["positive_pairs"], result["negative_pairs"]) == (2, 7)
    assert (result["queries"], result["positive_queries"]) == (3, 2)
    assert result["precision"] == 0.5
    assert result["recall"] == 1.0
    assert result["f1"] == pytest.approx(2 / 3)
    assert result["hit_at_1"] == 0.5
    assert result["hit_at_3"] == result["hit_at_5"] == 1.0
    assert result["mrr"] == 0.75

    higher = metrics(rows, "cosine", 1.0, 0.7)
    assert higher["confusion_matrix"] == {"tp": 1, "fp": 2, "tn": 5, "fn": 1}


def test_hybrid_score_and_latency_statistics() -> None:
    row = {"cosine_score": 0.8, "levenshtein_score": 0.2}
    assert score(row, "cosine") == 0.8
    assert score(row, "levenshtein") == 0.2
    assert score(row, "hybrid", 0.25) == pytest.approx(0.35)

    result = latency_stats([1.0, 2.0, 3.0, 4.0])
    assert result["mean_ms"] == result["median_ms"] == 2.5
    assert result["stddev_ms"] == pytest.approx(sqrt(1.25))
    assert result["p95_ms"] == pytest.approx(3.85)
