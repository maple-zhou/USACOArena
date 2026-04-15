"""Blueprint exposing the competition management dashboard APIs and assets."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from flask import (
    Blueprint,
    Response,
    current_app,
    jsonify,
    request,
    send_from_directory,
)

from .manager import CompetitionProcessManager


ui_bp = Blueprint(
    "usacoarena_ui",
    __name__,
    url_prefix="/ui",
    static_folder="static",
    template_folder="templates",
)


def _get_base_dir() -> Path:
    base_dir = current_app.config.get("USACOA_UI_BASE_DIR")
    if base_dir is None:
        base_dir = Path(__file__).resolve().parents[2]
        current_app.config["USACOA_UI_BASE_DIR"] = base_dir
    return Path(base_dir)


def _get_manager() -> CompetitionProcessManager:
    manager: Optional[CompetitionProcessManager] = current_app.extensions.get(
        "ui_manager"
    )
    if manager is None:
        manager = CompetitionProcessManager(base_dir=_get_base_dir())
        current_app.extensions["ui_manager"] = manager
    return manager


@ui_bp.route("/")
def ui_index() -> Response:
    """Serve the main dashboard page."""

    static_dir = Path(ui_bp.static_folder or "static")
    if not static_dir.is_absolute():
        static_dir = Path(__file__).resolve().parent / static_dir
    return send_from_directory(str(static_dir), "index.html")


@ui_bp.route("/api/instances", methods=["GET"])
def list_instances() -> Response:
    manager = _get_manager()
    instances = [
        manager.instance_to_dict(instance) for instance in manager.list_instances()
    ]
    return jsonify({"status": "success", "data": instances})


@ui_bp.route("/api/instances", methods=["POST"])
def create_instance() -> Response:
    payload: Dict[str, Any] = request.get_json(silent=True) or {}
    manager = _get_manager()

    try:
        instance = manager.create_instance(payload)
    except Exception as exc:  # pylint: disable=broad-except
        return jsonify({"status": "error", "message": str(exc)}), 400

    return jsonify({"status": "success", "data": manager.instance_to_dict(instance)})


@ui_bp.route("/api/instances/<instance_id>", methods=["GET"])
def get_instance(instance_id: str) -> Response:
    manager = _get_manager()
    instance = manager.get_instance(instance_id)
    if not instance:
        return jsonify({"status": "error", "message": "Instance not found"}), 404

    return jsonify({"status": "success", "data": manager.instance_to_dict(instance)})


@ui_bp.route("/api/instances/<instance_id>/snapshot", methods=["GET"])
def instance_snapshot(instance_id: str) -> Response:
    manager = _get_manager()
    instance = manager.get_instance(instance_id)
    if not instance:
        return jsonify({"status": "error", "message": "Instance not found"}), 404

    snapshot = manager.collect_runtime_snapshot(instance)
    return jsonify({"status": "success", "data": snapshot})


@ui_bp.route("/api/instances/<instance_id>/stop", methods=["POST"])
def stop_instance(instance_id: str) -> Response:
    manager = _get_manager()
    stopped = manager.stop_instance(instance_id)
    if not stopped:
        return jsonify({"status": "error", "message": "Instance not found"}), 404

    instance = manager.get_instance(instance_id)
    return jsonify({"status": "success", "data": manager.instance_to_dict(instance)})


@ui_bp.route("/api/templates/problem-sets", methods=["GET"])
def list_problem_sets() -> Response:
    root = _get_base_dir() / "config"
    exclude_stems = {"problems_main", "problems_main-old"}
    problem_files = [
        file_path
        for file_path in sorted(root.glob("problems*.json"))
        if file_path.stem not in exclude_stems
    ]

    data = []
    for file_path in problem_files:
        try:
            with file_path.open("r", encoding="utf-8") as handle:
                problems = json.load(handle)
            data.append(
                {
                    "name": file_path.name,
                    "path": str(file_path.relative_to(_get_base_dir())),
                    "count": len(problems) if isinstance(problems, list) else 0,
                }
            )
        except Exception:  # pylint: disable=broad-except
            continue

    return jsonify({"status": "success", "data": data})


@ui_bp.route("/api/templates/competition-configs", methods=["GET"])
def list_competition_templates() -> Response:
    root = _get_base_dir() / "config"
    files = sorted(root.glob("competition_*.json"))

    data = [
        {
            "name": file_path.name,
            "path": str(file_path.relative_to(_get_base_dir())),
        }
        for file_path in files
    ]
    return jsonify({"status": "success", "data": data})


@ui_bp.route("/api/templates/competitor-configs", methods=["GET"])
def list_competitor_templates() -> Response:
    root = _get_base_dir() / "config"
    files = sorted(root.glob("*llm*.json"))

    data = [
        {
            "name": file_path.name,
            "path": str(file_path.relative_to(_get_base_dir())),
        }
        for file_path in files
    ]
    return jsonify({"status": "success", "data": data})


@ui_bp.route("/api/templates/competition-defaults", methods=["GET"])
def get_competition_defaults() -> Response:
    manager = _get_manager()
    defaults = manager.get_competition_defaults()
    return jsonify({"status": "success", "data": defaults})


@ui_bp.route("/api/templates/default-competitors", methods=["GET"])
def get_default_competitors() -> Response:
    manager = _get_manager()
    competitors = manager.get_default_competitors()
    return jsonify({"status": "success", "data": competitors})


def register_ui_blueprint(app, *, base_dir: Optional[Path] = None) -> None:
    """Register the UI blueprint and attach the manager to the Flask app."""

    resolved_base_dir = (
        Path(base_dir) if base_dir else Path(__file__).resolve().parents[2]
    )
    app.config.setdefault("USACOA_UI_BASE_DIR", resolved_base_dir)

    if "ui_manager" not in app.extensions:
        app.extensions["ui_manager"] = CompetitionProcessManager(
            base_dir=resolved_base_dir
        )
    if "usacoarena_ui" not in app.blueprints:
        app.register_blueprint(ui_bp)
