from __future__ import annotations

import json
from pathlib import Path
import sys


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.moment_discovery import (
    DeterministicFixtureAnalyzer,
    SegmentData,
    deduplicate_ranked,
    generate_candidate_windows,
    score_breakdown,
    temporal_iou,
    transcript_similarity,
)


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "moment_evaluation.json"


def _iou_bounds(left: tuple[int, int], right: tuple[int, int]) -> float:
    intersection = max(0, min(left[1], right[1]) - max(left[0], right[0]))
    union = max(left[1], right[1]) - min(left[0], right[0])
    return intersection / union if union else 0.0


def evaluate() -> dict[str, float | int | bool]:
    dataset = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    analyzer = DeterministicFixtureAnalyzer()
    total_candidates = 0
    invalid_boundaries = 0
    duration_violations = 0
    duplicate_pairs = 0
    compared_pairs = 0
    labeled_total = 0
    labeled_matches = 0
    distinct_topics: set[str] = set()
    stability = True

    for case in dataset["cases"]:
        segments = [SegmentData(*item) for item in case["segments"]]
        candidates = generate_candidate_windows(
            segments,
            source_duration_ms=case["duration_ms"],
            min_duration_ms=20_000,
            max_duration_ms=90_000,
            target_duration_ms=55_000,
            max_candidates=24,
        )
        first = analyzer.analyze(
            candidates,
            language=case["language"],
            source_duration_ms=case["duration_ms"],
        )
        second = analyzer.analyze(
            candidates,
            language=case["language"],
            source_duration_ms=case["duration_ms"],
        )
        stability = stability and first == second
        evaluations = {item.candidate_id: item for item in first.evaluations}
        scored = []
        for candidate in candidates:
            total_candidates += 1
            invalid_boundaries += int(
                not (0 <= candidate.start_ms < candidate.end_ms <= case["duration_ms"])
            )
            duration_violations += int(not (20_000 <= candidate.duration_ms <= 90_000))
            evaluation = evaluations[candidate.candidate_id]
            score, breakdown = score_breakdown(evaluation.scores)
            scored.append((candidate, evaluation, score, breakdown))
        selected = deduplicate_ranked(scored, limit=10, minimum_score=55)
        distinct_topics.update(item[1].topic.casefold() for item in selected)
        for index, left in enumerate([item[0] for item in selected]):
            for right in [item[0] for item in selected][index + 1 :]:
                compared_pairs += 1
                if temporal_iou(left, right) >= 0.62 or transcript_similarity(left.text, right.text) >= 0.86:
                    duplicate_pairs += 1
        for good in case["good_windows"]:
            labeled_total += 1
            if any(_iou_bounds(tuple(good), (item[0].start_ms, item[0].end_ms)) >= 0.35 for item in selected):
                labeled_matches += 1

    return {
        "dataset_cases": len(dataset["cases"]),
        "candidate_count": total_candidates,
        "boundary_validity_rate": 1 - invalid_boundaries / max(total_candidates, 1),
        "duration_compliance_rate": 1 - duration_violations / max(total_candidates, 1),
        "duplicate_rate": duplicate_pairs / max(compared_pairs, 1),
        "ranking_stable": stability,
        "distinct_selected_topics": len(distinct_topics),
        "human_label_agreement": labeled_matches / max(labeled_total, 1),
    }


if __name__ == "__main__":
    metrics = evaluate()
    print(json.dumps(metrics, indent=2, sort_keys=True))
    if metrics["boundary_validity_rate"] < 1 or metrics["duration_compliance_rate"] < 1:
        raise SystemExit(1)
