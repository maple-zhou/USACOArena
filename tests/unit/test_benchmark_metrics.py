from datetime import datetime

from usacoarena.benchmark.metrics import build_intelligence_report
from usacoarena.models.models import Competition, Participant


def _make_competition() -> Competition:
    return Competition(
        id="comp-1",
        title="Benchmark",
        description="desc",
        start_time=datetime.now(),
        max_tokens_per_participant=100000,
        rules={"intelligence_weights": {"solve": 0.5, "efficiency": 0.2, "reliability": 0.1, "speed": 0.1, "coverage": 0.1}},
        participant_count=2,
        problem_count=2,
    )


def _make_participant(pid: str, name: str) -> Participant:
    return Participant(
        id=pid,
        competition_id="comp-1",
        name=name,
        api_base_url="",
        api_key="",
        limit_tokens=100000,
        lambda_value=100,
        agent_profile={"agent_type": "custom", "transport": "openai_compatible_http"},
    )


def test_build_intelligence_report_ranking_and_components() -> None:
    competition = _make_competition()

    p1 = _make_participant("p1", "agent-a")
    p1.problem_pass_score = 120
    p1.submission_count = 4
    p1.accepted_count = 3
    p1.consumed_tokens = 2000
    p1.submission_penalty = 20
    p1.is_running = False
    p1.delivery_time_seconds = 600
    p1.problem_stats = {
        "prob-1": {"submission_count": 2, "best_score": 60, "solved": True},
        "prob-2": {"submission_count": 2, "best_score": 60, "solved": True},
    }

    p2 = _make_participant("p2", "agent-b")
    p2.problem_pass_score = 80
    p2.submission_count = 6
    p2.accepted_count = 2
    p2.consumed_tokens = 6000
    p2.submission_penalty = 120
    p2.is_running = False
    p2.delivery_time_seconds = 1200
    p2.problem_stats = {
        "prob-1": {"submission_count": 4, "best_score": 80, "solved": True},
    }

    report = build_intelligence_report(
        competition,
        [p1, p2],
        arena_rank_map={"p1": 1, "p2": 2},
        include_test_points=True,
    )

    assert report["summary"]["participant_count"] == 2
    assert report["rows"][0]["name"] == "agent-a"
    assert report["rows"][0]["intelligence_rank"] == 1
    assert report["rows"][1]["intelligence_rank"] == 2
    assert report["rows"][0]["solve_component"] > report["rows"][1]["solve_component"]
    assert "test_points" in report["rows"][0]


def test_build_intelligence_report_empty_participants() -> None:
    competition = _make_competition()
    report = build_intelligence_report(competition, [])

    assert report["rows"] == []
    assert report["summary"]["participant_count"] == 0
    assert report["summary"]["avg_intelligence_score"] == 0.0
