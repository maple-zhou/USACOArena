"""Benchmark intelligence metrics for USACOArena."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from ..models.models import Competition, Participant


@dataclass
class IntelligenceWeights:
    solve: float = 0.45
    efficiency: float = 0.20
    reliability: float = 0.15
    speed: float = 0.10
    coverage: float = 0.10

    def normalized(self) -> "IntelligenceWeights":
        total = float(self.solve + self.efficiency + self.reliability + self.speed + self.coverage)
        if total <= 0:
            return IntelligenceWeights()
        return IntelligenceWeights(
            solve=self.solve / total,
            efficiency=self.efficiency / total,
            reliability=self.reliability / total,
            speed=self.speed / total,
            coverage=self.coverage / total,
        )

    def as_dict(self) -> Dict[str, float]:
        return {
            "solve": float(self.solve),
            "efficiency": float(self.efficiency),
            "reliability": float(self.reliability),
            "speed": float(self.speed),
            "coverage": float(self.coverage),
        }


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _safe_div(a: float, b: float) -> float:
    if b == 0:
        return 0.0
    return a / b


def _resolve_weights(
    competition: Competition,
    overrides: Optional[Dict[str, Any]] = None,
) -> IntelligenceWeights:
    base = IntelligenceWeights()
    rules = competition.rules if isinstance(competition.rules, dict) else {}
    from_rules = rules.get("intelligence_weights", {}) if isinstance(rules, dict) else {}

    payload: Dict[str, Any] = {}
    if isinstance(from_rules, dict):
        payload.update(from_rules)
    if isinstance(overrides, dict):
        payload.update(overrides)

    if payload:
        base = IntelligenceWeights(
            solve=_safe_float(payload.get("solve"), base.solve),
            efficiency=_safe_float(payload.get("efficiency"), base.efficiency),
            reliability=_safe_float(payload.get("reliability"), base.reliability),
            speed=_safe_float(payload.get("speed"), base.speed),
            coverage=_safe_float(payload.get("coverage"), base.coverage),
        )

    return base.normalized()


def _extract_problem_stats(problem_stats: Any) -> Dict[str, Dict[str, Any]]:
    if not isinstance(problem_stats, dict):
        return {}
    result: Dict[str, Dict[str, Any]] = {}
    for problem_id, value in problem_stats.items():
        if isinstance(value, dict):
            result[str(problem_id)] = value
    return result


def _normalize_test_points(problem_stats: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for problem_id in sorted(problem_stats.keys()):
        stat = problem_stats.get(problem_id, {})
        rows.append(
            {
                "problem_id": problem_id,
                "submission_count": _safe_int(stat.get("submission_count"), 0),
                "best_score": _safe_int(stat.get("best_score"), 0),
                "solved": bool(stat.get("solved", False)),
                "passed_test_cases": _safe_int(stat.get("passed_test_cases"), 0),
                "total_test_cases": _safe_int(stat.get("total_test_cases"), 0),
                "penalty": _safe_int(stat.get("penalty"), 0),
                "is_first_ac": bool(stat.get("is_first_ac", False)),
            }
        )
    return rows


def build_intelligence_report(
    competition: Competition,
    participants: Iterable[Participant],
    *,
    arena_rank_map: Optional[Dict[str, int]] = None,
    include_test_points: bool = False,
    weight_overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Compute intelligence metrics and return a structured benchmark report."""
    participant_list = list(participants)
    problem_count = max(0, _safe_int(getattr(competition, "problem_count", 0), 0))
    weights = _resolve_weights(competition, weight_overrides)

    raw_rows: List[Dict[str, Any]] = []
    for participant in participant_list:
        problem_stats = _extract_problem_stats(getattr(participant, "problem_stats", {}))
        solved = sum(1 for item in problem_stats.values() if bool(item.get("solved", False)))
        attempted = sum(
            1
            for item in problem_stats.values()
            if _safe_int(item.get("submission_count", 0), 0) > 0
        )

        is_running = bool(getattr(participant, "is_running", True))
        elapsed_seconds = _safe_int(
            getattr(participant, "delivery_time_seconds", 0) if not is_running else participant.get_elapsed_time_seconds(),
            0,
        )

        raw_rows.append(
            {
                "participant_id": str(getattr(participant, "id", "")),
                "name": str(getattr(participant, "name", "")),
                "arena_rank": _safe_int((arena_rank_map or {}).get(str(getattr(participant, "id", ""))), 0),
                "is_running": is_running,
                "termination_reason": getattr(participant, "termination_reason", None),
                "problem_pass_score": _safe_int(getattr(participant, "problem_pass_score", 0), 0),
                "score": _safe_float(getattr(participant, "score", 0.0), 0.0),
                "submission_count": _safe_int(getattr(participant, "submission_count", 0), 0),
                "accepted_count": _safe_int(getattr(participant, "accepted_count", 0), 0),
                "solved_problems": solved,
                "attempted_problems": attempted,
                "consumed_tokens": _safe_int(getattr(participant, "consumed_tokens", 0), 0),
                "consumed_credit": _safe_float(participant.get_consumed_credit(), 0.0),
                "delivery_time_seconds": max(0, elapsed_seconds),
                "agent_profile": getattr(participant, "agent_profile", {})
                if isinstance(getattr(participant, "agent_profile", {}), dict)
                else {},
                "problem_stats": problem_stats,
            }
        )

    if not raw_rows:
        return {
            "competition": {
                "id": competition.id,
                "title": competition.title,
                "description": competition.description,
                "problem_count": problem_count,
            },
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "weights": weights.as_dict(),
            "summary": {
                "participant_count": 0,
                "terminated_count": 0,
                "avg_intelligence_score": 0.0,
                "top_participant": None,
            },
            "rows": [],
        }

    max_pass = max(1, max(row["problem_pass_score"] for row in raw_rows))
    min_credit = min(row["consumed_credit"] for row in raw_rows)
    max_credit = max(row["consumed_credit"] for row in raw_rows)

    min_elapsed = min(row["delivery_time_seconds"] for row in raw_rows)
    max_elapsed = max(row["delivery_time_seconds"] for row in raw_rows)

    rows: List[Dict[str, Any]] = []
    for row in raw_rows:
        solve_component = _clamp01(_safe_div(float(row["problem_pass_score"]), float(max_pass)))

        if max_credit == min_credit:
            efficiency_component = 1.0
        else:
            efficiency_component = _clamp01(
                1.0 - _safe_div(row["consumed_credit"] - min_credit, max_credit - min_credit)
            )

        if max_elapsed == min_elapsed:
            speed_component = 1.0 if row["delivery_time_seconds"] > 0 else 0.0
        else:
            speed_component = _clamp01(
                1.0 - _safe_div(row["delivery_time_seconds"] - min_elapsed, max_elapsed - min_elapsed)
            )

        reliability_component = _clamp01(
            _safe_div(float(row["accepted_count"]), float(max(1, row["submission_count"])))
        )
        coverage_component = _clamp01(
            _safe_div(float(row["attempted_problems"]), float(max(1, problem_count)))
            if problem_count > 0
            else 0.0
        )

        intelligence_0_1 = (
            solve_component * weights.solve
            + efficiency_component * weights.efficiency
            + reliability_component * weights.reliability
            + speed_component * weights.speed
            + coverage_component * weights.coverage
        )

        participant_profile = row["agent_profile"] if isinstance(row["agent_profile"], dict) else {}
        profile_mcp = participant_profile.get("mcp") if isinstance(participant_profile.get("mcp"), dict) else {}

        output_row = {
            "participant_id": row["participant_id"],
            "name": row["name"],
            "arena_rank": row["arena_rank"],
            "is_running": row["is_running"],
            "termination_reason": row["termination_reason"],
            "problem_pass_score": row["problem_pass_score"],
            "score": round(row["score"], 6),
            "submission_count": row["submission_count"],
            "accepted_count": row["accepted_count"],
            "solved_problems": row["solved_problems"],
            "attempted_problems": row["attempted_problems"],
            "consumed_tokens": row["consumed_tokens"],
            "consumed_credit": round(row["consumed_credit"], 4),
            "delivery_time_seconds": row["delivery_time_seconds"],
            "agent_type": str(participant_profile.get("agent_type") or "unknown"),
            "transport": str(participant_profile.get("transport") or "unknown"),
            "mcp_enabled": bool(profile_mcp.get("enabled", False)),
            "capabilities": participant_profile.get("capabilities", []),
            "solve_component": round(100.0 * solve_component, 2),
            "efficiency_component": round(100.0 * efficiency_component, 2),
            "reliability_component": round(100.0 * reliability_component, 2),
            "speed_component": round(100.0 * speed_component, 2),
            "coverage_component": round(100.0 * coverage_component, 2),
            "intelligence_score": round(100.0 * intelligence_0_1, 2),
        }

        if include_test_points:
            output_row["test_points"] = _normalize_test_points(row["problem_stats"])

        rows.append(output_row)

    rows.sort(
        key=lambda item: (
            float(item.get("intelligence_score", 0.0)),
            int(item.get("problem_pass_score", 0)),
            -float(item.get("consumed_credit", 0.0)),
        ),
        reverse=True,
    )

    for idx, row in enumerate(rows, start=1):
        row["intelligence_rank"] = idx

    avg_score = 0.0
    if rows:
        avg_score = round(
            sum(_safe_float(item.get("intelligence_score", 0.0), 0.0) for item in rows)
            / len(rows),
            2,
        )

    top_participant = rows[0]["name"] if rows else None
    terminated_count = sum(1 for row in rows if not bool(row.get("is_running", True)))

    return {
        "competition": {
            "id": competition.id,
            "title": competition.title,
            "description": competition.description,
            "problem_count": problem_count,
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "weights": weights.as_dict(),
        "summary": {
            "participant_count": len(rows),
            "terminated_count": terminated_count,
            "avg_intelligence_score": avg_score,
            "top_participant": top_participant,
        },
        "rows": rows,
    }
