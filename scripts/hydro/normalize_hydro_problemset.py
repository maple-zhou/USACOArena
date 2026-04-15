#!/usr/bin/env python3
"""Normalize a Hydro problemset zip for USACOArena release usage.

This script preserves the original Hydro package structure while injecting a
stable tag for each paper-facing long problem id:

    usacoarena-problem-id:<directory_name>

That tag is later consumed by the Hydro plugin to resolve
`1452_platinum_all_pairs_similarity` style IDs to Hydro's internal problem docs.
"""

from __future__ import annotations

import argparse
import os
import shutil
import tempfile
import zipfile
from pathlib import Path


TAG_PREFIX = "usacoarena-problem-id:"


def update_problem_yaml(yaml_text: str, long_problem_id: str) -> str:
    tag_line = f'  - "{TAG_PREFIX}{long_problem_id}"'

    if f"{TAG_PREFIX}{long_problem_id}" in yaml_text:
        return yaml_text

    lines = yaml_text.splitlines()
    for idx, line in enumerate(lines):
        if line.strip() == "tag:":
            insert_at = idx + 1
            while insert_at < len(lines) and lines[insert_at].startswith("  - "):
                insert_at += 1
            lines.insert(insert_at, tag_line)
            return "\n".join(lines) + ("\n" if yaml_text.endswith("\n") else "")

    if lines and lines[-1].strip():
        lines.append("")
    lines.append("tag:")
    lines.append(tag_line)
    return "\n".join(lines) + ("\n" if yaml_text.endswith("\n") or not lines else "\n")


def normalize_problemset(input_zip: Path, output_zip: Path) -> None:
    if not input_zip.exists():
        raise FileNotFoundError(f"Input zip not found: {input_zip}")

    output_zip.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="usacoarena_hydro_norm_") as tmpdir:
        workdir = Path(tmpdir) / "work"
        workdir.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(input_zip, "r") as zf:
            zf.extractall(workdir)

        for problem_yaml in workdir.rglob("problem.yaml"):
            problem_dir = problem_yaml.parent
            long_problem_id = problem_dir.name
            original = problem_yaml.read_text(encoding="utf-8")
            updated = update_problem_yaml(original, long_problem_id)
            if updated != original:
                problem_yaml.write_text(updated, encoding="utf-8")

        if output_zip.exists():
            output_zip.unlink()

        archive_base = output_zip.with_suffix("")
        tmp_archive = shutil.make_archive(
            str(archive_base),
            "zip",
            root_dir=workdir,
        )
        os.replace(tmp_archive, output_zip)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inject USACOArena alias tags into a Hydro problemset zip"
    )
    parser.add_argument(
        "--input-zip",
        default="hydro_problemset.zip",
        help="Path to the original Hydro problemset zip",
    )
    parser.add_argument(
        "--output-zip",
        required=True,
        help="Path to the normalized output zip",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    normalize_problemset(Path(args.input_zip), Path(args.output_zip))
    print(f"Normalized Hydro problemset written to {args.output_zip}")


if __name__ == "__main__":
    main()
