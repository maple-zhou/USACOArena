from __future__ import annotations

from pathlib import Path

from usacoarena.benchmark.paper_aggregation import aggregate_paper_runs


def test_aggregate_paper_runs_builds_expected_tables(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    runs_root = repo_root / "tests" / "fixtures" / "paper_runs"
    output_dir = tmp_path / "aggregated"

    manifest = aggregate_paper_runs(runs_root, output_dir)

    table_8 = output_dir / "table_8_main.json"
    table_2 = output_dir / "table_2_appendix_b.json"
    table_9 = output_dir / "table_9_appendix_g.json"
    appendix_b_extended = output_dir / "appendix_b_extended.json"
    assert table_8.exists()
    assert table_2.exists()
    assert table_9.exists()
    assert appendix_b_extended.exists()
    assert Path(manifest["manifest"]).exists()

    table_8_payload = __import__("json").loads(table_8.read_text(encoding="utf-8"))
    gemini = next(row for row in table_8_payload["rows"] if row["model"] == "Gemini-2.5-pro")
    codex = next(row for row in table_8_payload["rows"] if row["model"] == "GPT-5-Codex")
    assert round(gemini["avg_score"]["mean"], 2) == 15.00
    assert round(gemini["avg_rank"]["mean"], 2) == 1.00
    assert round(codex["avg_consumed_credit"]["mean"], 2) == 4500000.00
    assert round(codex["hint_credit"]["mean"], 2) == 800.00

    table_2_payload = __import__("json").loads(table_2.read_text(encoding="utf-8"))
    gemini_row = next(row for row in table_2_payload["rows"] if row["model"] == "Gemini-2.5-pro")
    codex_row = next(row for row in table_2_payload["rows"] if row["model"] == "GPT-5-Codex")
    assert gemini_row["main_result"] == 13.2
    assert gemini_row["low_credit_10m"] == 8.3
    assert codex_row["exp_score"] == 4.3

    extended_payload = __import__("json").loads(appendix_b_extended.read_text(encoding="utf-8"))
    gemini_extended = next(row for row in extended_payload["rows"] if row["model"] == "Gemini-2.5-pro")
    assert gemini_extended["free_penalty"] == 10.7
    assert gemini_extended["prompt_p21"] == 10.4

    table_9_payload = __import__("json").loads(table_9.read_text(encoding="utf-8"))
    base_row = next(row for row in table_9_payload["rows"] if row["agent"] == "GPT-5 (Base)")
    cli_row = next(row for row in table_9_payload["rows"] if row["agent"] == "Codex-CLI")
    assert round(base_row["win_rate"], 2) == 100.00
    assert round(cli_row["win_rate"], 2) == 100.00
    assert round(cli_row["avg_score"]["mean"], 2) == 9.50

    warnings = manifest["warnings"]
    assert any("missing_competition_results" in warning for warning in warnings)
