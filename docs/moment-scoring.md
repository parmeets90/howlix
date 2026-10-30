# Moment scoring

HOWLIX scores editorial usefulness, not guaranteed reach, engagement, or virality. The LLM supplies bounded factor judgments and supporting text; deterministic Python owns the total.

## Factors

| Factor | Default weight | Assessed from transcript? |
| --- | ---: | --- |
| Hook strength | 30% | Yes |
| Story completeness and payoff | 25% | Yes |
| Emotional engagement | 15% | Yes |
| Standalone clarity | 15% | Yes |
| Pacing | 10% | Yes |
| Visual quality | 5% | No |

Visual quality is stored as `score: null, assessed: false`. The analyzer is never asked to infer it from text.

## Normalized total

The assessed weights sum to 0.95. For factor scores `sᵢ` and weights `wᵢ`, Python calculates:

```text
overall = Σ(sᵢ × wᵢ) / Σ(wᵢ for assessed factors)
```

The result is rounded to two decimals and clamped naturally by the validated 0–100 factor range. The LLM cannot submit or override `overall_score`.

## Editorial guidance

Analyzers look for strong questions, surprising but supported statements, clear advice, personal stories, useful contrasts, facts, and educational takeaways. Sensational language, loudness, and controversy are not positive signals by themselves. Suggested hooks must be supported by the candidate transcript; invented speech is invalid.

Candidates below `MOMENT_MIN_EDITORIAL_SCORE` are omitted. Temporal intersection-over-union, transcript similarity, and repeated normalized topics then remove near-duplicates. This can produce fewer than five recommendations, including zero.

## Boundary policy

Candidate windows are proposed before analysis from absolute transcript timestamps. After ranking, word timestamps trim unnecessary leading/trailing silence only when the refined result still satisfies configured duration limits. Manual changes are retained separately from `ai_start_ms` and `ai_end_ms`, allowing an exact reset.

