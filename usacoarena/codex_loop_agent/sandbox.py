"""Sandbox and run-local HOME management for standalone Codex loop agent."""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

from .linux_landlock import (
    LandlockPolicy,
    LandlockUnavailable,
    apply_landlock,
    landlock_abi_version,
)


class SandboxError(RuntimeError):
    """Base sandbox error."""


@dataclass(frozen=True, slots=True)
class SandboxLayout:
    """Run-local filesystem layout for Codex."""

    workspace: Path
    home_dir: Path
    codex_home: Path
    tmp_dir: Path
    logs_dir: Path


def _normalize_paths(paths: Iterable[Path]) -> List[Path]:
    normalized: List[Path] = []
    seen: set[str] = set()
    for raw in paths:
        if raw is None:
            continue
        path = Path(raw).expanduser()
        try:
            resolved = path.resolve()
        except OSError:
            resolved = path
        key = str(resolved)
        if not key or key in seen:
            continue
        seen.add(key)
        normalized.append(resolved)
    return normalized


def _existing_paths(paths: Iterable[Path]) -> List[Path]:
    rows: List[Path] = []
    for path in _normalize_paths(paths):
        try:
            if path.exists():
                rows.append(path)
        except OSError:
            continue
    return rows


def _collect_binary_paths(binary_path: str) -> List[Path]:
    rows: List[Path] = []
    normalized = str(binary_path or "").strip()
    if normalized:
        rows.append(Path(normalized))

    if normalized and not os.path.isabs(normalized):
        resolved = shutil.which(normalized)
        if resolved:
            rows.append(Path(resolved))

    if not normalized:
        resolved = shutil.which("codex")
        if resolved:
            rows.append(Path(resolved))

    out: List[Path] = []
    for path in _existing_paths(rows):
        out.append(path)
        out.append(path.parent)
        if path.parent != path.parent.parent:
            out.append(path.parent.parent)
    return _existing_paths(out)


def _default_system_ro_paths() -> List[Path]:
    return _existing_paths(
        [
            Path("/usr"),
            Path("/bin"),
            Path("/sbin"),
            Path("/lib"),
            Path("/lib64"),
            Path("/etc"),
            Path("/run"),
            Path("/var/run"),
        ]
    )


def _default_system_rw_paths() -> List[Path]:
    return _existing_paths([Path("/dev"), Path("/tmp"), Path("/var/tmp")])


def _looks_like_virtualenv_bin(path: Path) -> bool:
    candidate = Path(path).expanduser()
    text = str(candidate).lower()
    if text.endswith("/.venv/bin"):
        return True
    if "/.venv/" in text or "/venv/" in text or "/virtualenv/" in text:
        return True
    try:
        cfg = candidate.parent / "pyvenv.cfg"
        if candidate.name == "bin" and cfg.exists():
            return True
    except OSError:
        return False
    return False


class RunnerSandbox:
    """Build run-local HOME and optional Linux Landlock preexec."""

    def __init__(
        self,
        *,
        workspace: Path,
        codex_binary: str,
        enable_landlock: bool,
    ) -> None:
        root = Path(workspace).expanduser().resolve()
        self.layout = SandboxLayout(
            workspace=root,
            home_dir=root / ".runner_home",
            codex_home=root / ".runner_home" / ".codex",
            tmp_dir=root / ".sandbox_tmp",
            logs_dir=root / "logs",
        )
        self.codex_binary = codex_binary
        self.enable_landlock = bool(enable_landlock)

        self.layout.workspace.mkdir(parents=True, exist_ok=True)
        self.layout.home_dir.mkdir(parents=True, exist_ok=True)
        self.layout.codex_home.mkdir(parents=True, exist_ok=True)
        self.layout.tmp_dir.mkdir(parents=True, exist_ok=True)
        self.layout.logs_dir.mkdir(parents=True, exist_ok=True)

        if self.enable_landlock:
            try:
                landlock_abi_version()
            except LandlockUnavailable as exc:
                raise SandboxError(f"Landlock is unavailable: {exc}") from exc

    def seed_codex_home(self) -> None:
        """Best-effort copy of host Codex config/auth into run-local CODEX_HOME."""

        host_codex_home = Path.home() / ".codex"
        for filename in ("config.toml", "auth.json"):
            source = host_codex_home / filename
            target = self.layout.codex_home / filename
            try:
                if not source.is_file() or source.is_symlink():
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
            except OSError:
                continue

    def build_env(self, base_env: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        env = dict(base_env or os.environ)

        env["HOME"] = str(self.layout.home_dir)
        env["CODEX_HOME"] = str(self.layout.codex_home)
        env["TMPDIR"] = str(self.layout.tmp_dir)

        env.pop("VIRTUAL_ENV", None)
        env.pop("CONDA_PREFIX", None)
        env.pop("PYTHONHOME", None)

        env["PATH"] = self._build_path(env.get("PATH", ""))
        shim_bin = self._ensure_python_shim_dir()
        env["PATH"] = f"{shim_bin}:{env['PATH']}"
        return env

    def build_preexec_fn(self, *, workdir: Path, prior: Optional[Callable[[], None]] = None) -> Optional[Callable[[], None]]:
        if not self.enable_landlock:
            return prior

        policy = self._build_landlock_policy(workdir=workdir)

        def _apply() -> None:
            apply_landlock(policy)

        if prior is None:
            return _apply

        def _chained() -> None:
            prior()
            _apply()

        return _chained

    def _build_path(self, inherited: str) -> str:
        parts: List[str] = [
            "/usr/local/sbin",
            "/usr/local/bin",
            "/usr/sbin",
            "/usr/bin",
            "/sbin",
            "/bin",
        ]

        for path in _collect_binary_paths(self.codex_binary):
            if path.is_dir():
                parts.append(str(path))
            else:
                parts.append(str(path.parent))

        for token in str(inherited or "").split(":"):
            normalized = token.strip()
            if normalized:
                if _looks_like_virtualenv_bin(Path(normalized)):
                    continue
                parts.append(normalized)

        deduped: List[str] = []
        seen: set[str] = set()
        for item in parts:
            if item in seen:
                continue
            seen.add(item)
            deduped.append(item)
        return ":".join(deduped)

    def _ensure_python_shim_dir(self) -> str:
        """Provide a stable `python` command that resolves to system `python3`."""

        shim_dir = self.layout.home_dir / "bin"
        shim_path = shim_dir / "python"
        shim_content = "#!/usr/bin/env bash\nexec python3 \"$@\"\n"

        try:
            shim_dir.mkdir(parents=True, exist_ok=True)
            if (not shim_path.exists()) or (shim_path.read_text(encoding="utf-8") != shim_content):
                shim_path.write_text(shim_content, encoding="utf-8")
            shim_path.chmod(0o755)
        except OSError:
            return "/usr/bin"
        return str(shim_dir)

    def _build_landlock_policy(self, *, workdir: Path) -> LandlockPolicy:
        workdir = Path(workdir).resolve()

        ro_paths: List[Path] = []
        ro_paths.extend(_default_system_ro_paths())
        ro_paths.extend(_collect_binary_paths(self.codex_binary))

        rw_paths: List[Path] = [
            self.layout.workspace,
            self.layout.home_dir,
            self.layout.codex_home,
            self.layout.tmp_dir,
            self.layout.logs_dir,
            workdir,
        ]
        rw_paths.extend(_default_system_rw_paths())

        normalized_rw = _normalize_paths(rw_paths)
        rw_set = {str(path) for path in normalized_rw}
        normalized_ro = [path for path in _normalize_paths(ro_paths) if str(path) not in rw_set]

        return LandlockPolicy(
            ro_paths=tuple(normalized_ro),
            rw_paths=tuple(normalized_rw),
        )

    def run_subprocess(
        self,
        *,
        command: List[str],
        cwd: Path,
        env: Dict[str, str],
        stdin: str,
        stdout_path: Path,
        stderr_path: Path,
        on_stdout_line: Optional[Callable[[str], None]] = None,
        on_stderr_line: Optional[Callable[[str], None]] = None,
    ) -> int:
        """Run subprocess and stream output to log files."""

        cwd = Path(cwd).resolve()
        stdout_path.parent.mkdir(parents=True, exist_ok=True)
        stderr_path.parent.mkdir(parents=True, exist_ok=True)

        preexec_fn = self.build_preexec_fn(workdir=cwd)

        with stdout_path.open("w", encoding="utf-8") as out_handle, stderr_path.open(
            "w", encoding="utf-8"
        ) as err_handle:
            process = subprocess.Popen(
                command,
                cwd=str(cwd),
                env=env,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                preexec_fn=preexec_fn,
            )

            assert process.stdin is not None
            assert process.stdout is not None
            assert process.stderr is not None

            if stdin:
                process.stdin.write(stdin)
            process.stdin.close()

            def _pump(
                stream: Any,
                handle: Any,
                callback: Optional[Callable[[str], None]],
            ) -> None:
                try:
                    for line in iter(stream.readline, ""):
                        if not line:
                            break
                        handle.write(line)
                        handle.flush()
                        if callback is not None:
                            callback(line)
                finally:
                    try:
                        stream.close()
                    except Exception:
                        pass

            stdout_thread = threading.Thread(
                target=_pump,
                args=(process.stdout, out_handle, on_stdout_line),
                daemon=True,
            )
            stderr_thread = threading.Thread(
                target=_pump,
                args=(process.stderr, err_handle, on_stderr_line),
                daemon=True,
            )
            stdout_thread.start()
            stderr_thread.start()

            return_code = int(process.wait())
            stdout_thread.join(timeout=5.0)
            stderr_thread.join(timeout=5.0)
            return return_code
