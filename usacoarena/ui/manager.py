"""Competition orchestration manager for the Web UI.

This module provides a lightweight process manager that can:

* Generate per-competition configuration files from repository templates
* Provision dedicated API server and optional OJ processes for each run
* Launch the existing competition organizer in the background without
  modifying the core evaluation logic
* Expose in-memory state that can be queried by the UI blueprint to render
  dashboards, leaderboards, and action histories

It intentionally avoids altering the competition runtime — all operations
are layered on top through subprocess management and HTTP calls.
"""

from __future__ import annotations

import asyncio
import copy
import json
import os
import socket
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from agents import GenericAPIAgent
from scripts.competition_organizer import CompetitionOrganizer
from scripts.competitors import Competitor
from usacoarena.utils.logger_config import get_logger

logger = get_logger("ui_manager")


def _current_timestamp() -> datetime:
    return datetime.utcnow()


def _ensure_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def _deep_merge(base: Dict[str, Any], overrides: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively merge two dictionaries without mutating inputs."""

    result = copy.deepcopy(base)
    for key, value in (overrides or {}).items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Configuration template not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _load_yaml_or_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Configuration template not found: {path}")

    text = path.read_text(encoding="utf-8")

    try:
        import yaml  # type: ignore
    except ImportError:  # pragma: no cover - optional dependency
        yaml = None

    if yaml:
        return yaml.safe_load(text)

    return json.loads(text)


def _find_free_port(start_port: int, limit: int = 200) -> int:
    for port in range(start_port, start_port + limit):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("0.0.0.0", port))
            except OSError:
                continue
        return port
    raise RuntimeError(
        f"Unable to find free port in range {start_port}-{start_port + limit}"
    )


def _wait_for_http(endpoint: str, timeout: float = 30.0, interval: float = 0.5) -> bool:
    """Poll an HTTP endpoint until it responds with success or timeout."""

    start = time.time()
    while time.time() - start <= timeout:
        try:
            response = requests.get(endpoint, timeout=interval)
            if response.status_code < 500:
                return True
        except requests.RequestException:
            time.sleep(interval)
            continue
        time.sleep(interval)
    return False


@dataclass
class CompetitionInstance:
    """In-memory representation of a managed competition run."""

    id: str
    title: str
    description: str
    server_port: int
    server_host: str
    config_dir: Path
    server_config_path: Path
    competition_config_path: Path
    competitors_config_path: Path
    problem_ids: List[str]
    competitor_specs: List[Dict[str, Any]]
    log_dir: Path
    competition_config: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_current_timestamp)
    updated_at: datetime = field(default_factory=_current_timestamp)
    status: str = "initializing"
    server_process: Optional[subprocess.Popen] = None
    oj_process: Optional[subprocess.Popen] = None
    oj_container_name: Optional[str] = None
    oj_endpoint: Optional[str] = None
    competition_id: Optional[str] = None
    runtime_thread: Optional[threading.Thread] = None
    results: Optional[Dict[str, Any]] = None
    last_error: Optional[str] = None

    @property
    def server_base_url(self) -> str:
        host = (
            "localhost"
            if self.server_host in {"0.0.0.0", "127.0.0.1"}
            else self.server_host
        )
        return f"http://{host}:{self.server_port}"


class CompetitionProcessManager:
    """Coordinator responsible for provisioning competition instances."""

    def __init__(
        self,
        base_dir: Optional[Path] = None,
        generated_root: Optional[Path] = None,
    ) -> None:
        self.base_dir = Path(base_dir or Path.cwd())
        self.generated_root = _ensure_directory(
            Path(generated_root or self.base_dir / "config" / "generated")
        )
        self.log_root = _ensure_directory(self.base_dir / "logs" / "ui")
        self.default_prompt_path = (
            Path(
                os.environ.get(
                    "USACOA_UI_DEFAULT_PROMPT",
                    "agents/single_agent/prompts/prompts-single.json",
                )
            )
            .expanduser()
            .resolve()
        )

        defaults_path = self.base_dir / "config" / "competition_main.yaml"
        if defaults_path.exists():
            self.competition_defaults = _load_yaml_or_json(defaults_path)
        else:
            self.competition_defaults = _load_json(
                self.base_dir / "config" / "competition_main.json"
            )

        self.base_competition_template = copy.deepcopy(self.competition_defaults)
        self.base_server_template = _load_json(
            self.base_dir / "config" / "server_config.json"
        )

        competitors_defaults_path = self.base_dir / "config" / "8llm.json"
        self.default_competitors: List[Dict[str, Any]] = []
        if competitors_defaults_path.exists():
            try:
                data = _load_json(competitors_defaults_path)
                competitors = (
                    data.get("competitors", []) if isinstance(data, dict) else []
                )
                if isinstance(competitors, list):
                    self.default_competitors = competitors
            except Exception as exc:  # pylint: disable=broad-except
                logger.warning(
                    "Failed to load default competitors from %s: %s",
                    competitors_defaults_path,
                    exc,
                )

        self.instances: Dict[str, CompetitionInstance] = {}
        self._lock = threading.Lock()

        self.base_server_port = int(
            os.environ.get("USACOA_UI_BASE_SERVER_PORT", "6500")
        )
        self.base_oj_port = int(
            os.environ.get("USACOA_UI_BASE_OJ_PORT", str(self.base_server_port + 3000))
        )

        self.dataset_mount = os.environ.get("USACOA_UI_OJ_DATASET")
        self.oj_image = os.environ.get("USACOA_UI_OJ_IMAGE", "oj-rust")

    # ------------------------------------------------------------------
    # Instance lifecycle helpers
    # ------------------------------------------------------------------
    def list_instances(self) -> List[CompetitionInstance]:
        with self._lock:
            return list(self.instances.values())

    def get_instance(self, instance_id: str) -> Optional[CompetitionInstance]:
        with self._lock:
            return self.instances.get(instance_id)

    def create_instance(self, payload: Dict[str, Any]) -> CompetitionInstance:
        """Create a new competition instance from client payload."""

        title = payload.get("title") or "Untitled Competition"
        description = payload.get("description", "")
        server_host = payload.get("server_host", "0.0.0.0")

        problem_ids = self._resolve_problem_ids(payload)
        if not problem_ids:
            raise ValueError(
                "At least one problem ID is required to create a competition"
            )

        competitor_specs = payload.get("competitors", [])
        if not competitor_specs:
            raise ValueError("At least one competitor must be provided")

        with self._lock:
            instance_id = payload.get("instance_id") or uuid.uuid4().hex[:12]
            if instance_id in self.instances:
                raise ValueError(f"Instance with id {instance_id} already exists")

            requested_server_port = payload.get("server_port")
            server_port = (
                int(requested_server_port)
                if requested_server_port
                else _find_free_port(self.base_server_port)
            )

            requested_oj_port = payload.get("oj_port")
            oj_port = (
                int(requested_oj_port)
                if requested_oj_port
                else _find_free_port(self.base_oj_port)
            )

            configs_dir = _ensure_directory(self.generated_root / instance_id)
            log_dir = _ensure_directory(self.log_root / instance_id)

            server_config_path = configs_dir / "server_config.json"
            competition_config_path = configs_dir / "competition_config.json"
            competitors_config_path = configs_dir / "competitors_config.json"

            server_config = self._build_server_config(
                payload, server_host, server_port, oj_port
            )
            competition_config = self._build_competition_config(
                payload.get("competition_config"),
                title,
                description,
                server_host,
                server_port,
            )
            title = competition_config.get("competition_title", title)
            description = competition_config.get("competition_description", description)
            competitors_config = {"competitors": competitor_specs}

            self._write_json(server_config_path, server_config)
            self._write_json(competition_config_path, competition_config)
            self._write_json(competitors_config_path, competitors_config)

            instance = CompetitionInstance(
                id=instance_id,
                title=title,
                description=description,
                server_port=server_port,
                server_host=server_host,
                config_dir=configs_dir,
                server_config_path=server_config_path,
                competition_config_path=competition_config_path,
                competitors_config_path=competitors_config_path,
                problem_ids=problem_ids,
                competitor_specs=competitor_specs,
                competition_config=competition_config,
                log_dir=log_dir,
            )

            start_oj = bool(payload.get("start_oj", False))
            instance.oj_endpoint = payload.get(
                "oj_endpoint",
                f"http://localhost:{oj_port}/usacoarena/oj/compile-and-execute",
            )

            if start_oj:
                self._launch_oj_instance(instance, oj_port)

            self._launch_server_instance(instance, server_host, server_port)

            # Store before launching runtime to allow polling from UI
            self.instances[instance_id] = instance

        # Launch competition runtime outside lock
        self._launch_runtime(instance)

        return instance

    # ------------------------------------------------------------------
    # Internal builders
    # ------------------------------------------------------------------
    def _resolve_problem_ids(self, payload: Dict[str, Any]) -> List[str]:
        ids = payload.get("problem_ids")
        if ids and isinstance(ids, list):
            return [str(item) for item in ids if item]

        problem_file = payload.get("problem_set_file")
        if problem_file:
            path = Path(problem_file)
            if not path.is_absolute():
                path = (self.base_dir / problem_file).resolve()
            if not path.exists():
                raise FileNotFoundError(f"Problem set file not found: {path}")
            data = _load_json(path)
            if not isinstance(data, list):
                raise ValueError("Problem set file must contain a JSON list of IDs")
            return [str(item) for item in data if item]

        return []

    def _build_server_config(
        self,
        payload: Dict[str, Any],
        host: str,
        port: int,
        oj_port: int,
    ) -> Dict[str, Any]:
        overrides = payload.get("server_config_overrides", {})
        server_config = _deep_merge(self.base_server_template, overrides)

        server_config.setdefault("server", {})
        server_config["server"]["host"] = host
        server_config["server"]["port"] = port

        server_config.setdefault("oj", {})
        server_config["oj"]["endpoint"] = payload.get(
            "oj_endpoint",
            f"http://localhost:{oj_port}/usacoarena/oj/compile-and-execute",
        )

        server_config.setdefault("db", {})
        server_config["db"]["path"] = f"data/competition_{port}.duckdb"

        return server_config

    def _build_competition_config(
        self,
        provided_config: Optional[Dict[str, Any]],
        title: str,
        description: str,
        host: str,
        port: int,
    ) -> Dict[str, Any]:
        base_config = copy.deepcopy(self.competition_defaults)
        competition_config = _deep_merge(base_config, provided_config or {})

        competition_config["api_base"] = (
            f"http://{host if host != '0.0.0.0' else 'localhost'}:{port}"
        )
        max_tokens_default = self.competition_defaults.get(
            "max_tokens_per_participant", 1000000
        )
        max_tokens = competition_config.get("max_tokens_per_participant")
        if max_tokens is None:
            competition_config["max_tokens_per_participant"] = max_tokens_default
        else:
            competition_config["max_tokens_per_participant"] = int(max_tokens)

        competition_config["competition_title"] = (
            competition_config.get("competition_title") or title
        )
        competition_config["competition_description"] = (
            competition_config.get("competition_description") or description
        )

        return competition_config

    def _write_json(self, path: Path, data: Dict[str, Any]) -> None:
        with path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)

    # ------------------------------------------------------------------
    # Launch helpers
    # ------------------------------------------------------------------
    def _launch_server_instance(
        self,
        instance: CompetitionInstance,
        host: str,
        port: int,
    ) -> None:
        log_file = (instance.log_dir / "server.log").open("a", encoding="utf-8")
        command = [
            os.environ.get("USACOA_UI_PYTHON", sys.executable),
            "-m",
            "usacoarena.main",
            "--config",
            str(instance.server_config_path),
            "--host",
            host,
            "--port",
            str(port),
        ]

        env = os.environ.copy()
        env.setdefault("PYTHONUNBUFFERED", "1")

        process = subprocess.Popen(
            command,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            cwd=self.base_dir,
            env=env,
        )
        instance.server_process = process

        health_endpoint = f"{instance.server_base_url}/api/competitions/list"
        if not _wait_for_http(health_endpoint, timeout=45):
            process.terminate()
            instance.status = "failed"
            instance.last_error = "Server failed to start within timeout"
            raise RuntimeError(instance.last_error)

        instance.status = "bootstrapping"
        instance.updated_at = _current_timestamp()

    def _launch_oj_instance(self, instance: CompetitionInstance, oj_port: int) -> None:
        if shutil.which("docker") is None:
            logger.warning(
                "Docker not available; skipping OJ auto-start for %s", instance.id
            )
            instance.last_error = "Docker not available; OJ not started automatically"
            return

        dataset_mount = (
            Path(self.dataset_mount).expanduser().resolve()
            if self.dataset_mount
            else None
        )
        if dataset_mount and not dataset_mount.exists():
            logger.warning(
                "Dataset path %s not found; continuing without mount", dataset_mount
            )
            dataset_mount = None

        container_name = f"usacoarena-oj-{instance.id}"
        command = [
            "docker",
            "run",
            "--platform",
            "linux/amd64",
            "-d",
            "--name",
            container_name,
        ]
        if dataset_mount:
            command.extend(["-v", f"{dataset_mount}:/data/tests"])
        command.extend(["-p", f"{oj_port}:8080", self.oj_image])

        try:
            subprocess.check_output(command, stderr=subprocess.STDOUT)
            instance.oj_container_name = container_name
            instance.updated_at = _current_timestamp()
            logger.info("Started OJ container %s on port %s", container_name, oj_port)
        except subprocess.CalledProcessError as exc:
            instance.last_error = (
                f"Failed to start OJ container: {exc.output.decode(errors='ignore')}"
            )
            logger.error(instance.last_error)

    def _launch_runtime(self, instance: CompetitionInstance) -> None:
        thread = threading.Thread(
            target=self._run_competition_runtime,
            args=(instance,),
            name=f"ui-runtime-{instance.id}",
            daemon=True,
        )
        instance.runtime_thread = thread
        thread.start()

    # ------------------------------------------------------------------
    # Runtime execution
    # ------------------------------------------------------------------
    def _run_competition_runtime(self, instance: CompetitionInstance) -> None:
        try:
            organizer = CompetitionOrganizer(
                api_base=instance.server_base_url,
                log_dir=str(instance.log_dir),
            )

            competitors = self._build_competitors(instance)
            for competitor in competitors:
                organizer.add_competitor(competitor)

            config = instance.competition_config or self.competition_defaults
            competition_id = organizer.create_competition(
                title=config.get("competition_title", instance.title),
                description=config.get("competition_description", instance.description),
                problem_ids=instance.problem_ids,
                max_tokens_per_participant=int(
                    config.get(
                        "max_tokens_per_participant",
                        self.competition_defaults.get(
                            "max_tokens_per_participant", 1000000
                        ),
                    )
                ),
                rules=config.get("rules"),
            )

            if not competition_id:
                raise RuntimeError("Failed to create competition via API")

            with self._lock:
                instance.competition_id = competition_id
                instance.status = "joining"
                instance.updated_at = _current_timestamp()

            # Register participants
            if not organizer.join_competition(competition_id):
                raise RuntimeError("Failed to register competitors")

            with self._lock:
                instance.status = "running"
                instance.updated_at = _current_timestamp()

            results = asyncio.run(organizer.run_llm_competition())

            with self._lock:
                instance.results = results
                instance.status = "completed"
                instance.updated_at = _current_timestamp()

        except Exception as exc:  # pylint: disable=broad-except
            logger.error("Competition runtime failed: %s", exc, exc_info=True)
            with self._lock:
                instance.status = "failed"
                instance.last_error = str(exc)
                instance.updated_at = _current_timestamp()

    def _build_competitors(self, instance: CompetitionInstance) -> List[Competitor]:
        competitors: List[Competitor] = []
        for spec in instance.competitor_specs:
            prompt_path = spec.get("prompt_config_path")
            prompt_config_path = (
                Path(prompt_path).expanduser().resolve()
                if prompt_path
                else self.default_prompt_path
            )

            request_format = spec.get("request_format")
            response_format = spec.get("response_format")

            agent = GenericAPIAgent(
                name=spec.get("name", "anonymous"),
                model_id=spec.get("model_id", ""),
                api_base_url=spec.get("api_base_url", ""),
                api_key=spec.get("api_key", ""),
                prompt_config_path=str(prompt_config_path),
                log_dir=str(instance.log_dir / "agents"),
                session_id=f"{instance.id}-{uuid.uuid4().hex[:6]}",
                request_format=request_format,
                response_format=response_format,
                request_timeout=spec.get("request_timeout"),
            )

            competitor = Competitor(
                name=spec.get("name", "anonymous"),
                agent=agent,
                limit_tokens=int(spec.get("limit_tokens", 10000000)),
            )
            competitors.append(competitor)

        return competitors

    # ------------------------------------------------------------------
    # Introspection helpers for blueprint
    # ------------------------------------------------------------------
    def instance_to_dict(self, instance: CompetitionInstance) -> Dict[str, Any]:
        data = {
            "id": instance.id,
            "title": instance.title,
            "description": instance.description,
            "server_port": instance.server_port,
            "server_host": instance.server_host,
            "server_base_url": instance.server_base_url,
            "status": instance.status,
            "created_at": instance.created_at.isoformat(),
            "updated_at": instance.updated_at.isoformat(),
            "competition_id": instance.competition_id,
            "log_dir": str(instance.log_dir),
            "config_dir": str(instance.config_dir),
            "problem_ids": instance.problem_ids,
            "competitors": [
                spec.get("name", "anonymous") for spec in instance.competitor_specs
            ],
            "oj_endpoint": instance.oj_endpoint,
            "last_error": instance.last_error,
            "competition_config": copy.deepcopy(instance.competition_config),
        }

        if instance.results is not None:
            data["results"] = instance.results

        return data

    def get_competition_defaults(self) -> Dict[str, Any]:
        return copy.deepcopy(self.competition_defaults)

    def get_default_competitors(self) -> List[Dict[str, Any]]:
        return copy.deepcopy(self.default_competitors)

    def collect_runtime_snapshot(self, instance: CompetitionInstance) -> Dict[str, Any]:
        snapshot = self.instance_to_dict(instance)

        if not instance.competition_id:
            snapshot["runtime"] = {"status": instance.status}
            return snapshot

        runtime: Dict[str, Any] = {"status": instance.status}

        try:
            base = instance.server_base_url
            comp_id = instance.competition_id

            rankings = requests.get(
                f"{base}/api/rankings/get/{comp_id}", timeout=5
            ).json()
            participants = requests.get(
                f"{base}/api/participants/list/{comp_id}", timeout=5
            ).json()
            submissions = requests.get(
                f"{base}/api/submissions/list/{comp_id}", timeout=5
            ).json()

            runtime["rankings"] = rankings
            runtime["participants"] = participants
            runtime["submissions"] = submissions

        except Exception as exc:  # pylint: disable=broad-except
            runtime["error"] = str(exc)

        snapshot["runtime"] = runtime
        return snapshot

    # ------------------------------------------------------------------
    # Shutdown helpers
    # ------------------------------------------------------------------
    def stop_instance(self, instance_id: str) -> bool:
        instance = self.get_instance(instance_id)
        if not instance:
            return False

        with self._lock:
            if instance.server_process and instance.server_process.poll() is None:
                instance.server_process.terminate()
            if instance.oj_process and instance.oj_process.poll() is None:
                instance.oj_process.terminate()
            if instance.oj_container_name and shutil.which("docker"):
                subprocess.Popen(
                    ["docker", "rm", "-f", instance.oj_container_name],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            instance.status = "stopped"
            instance.updated_at = _current_timestamp()

        return True


# Import placed at bottom to avoid circular import at module import time
import shutil  # noqa: E402
import sys  # noqa: E402
