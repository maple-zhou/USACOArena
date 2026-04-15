"""Minimal Landlock helper used by standalone Codex loop agent."""

from __future__ import annotations

import ctypes
import os
import platform
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional


_LANDLOCK_CREATE_RULESET_VERSION = 1 << 0
_LANDLOCK_RULE_PATH_BENEATH = 1

# linux/landlock.h access rights
_LANDLOCK_ACCESS_FS_WRITE_FILE = 1 << 1
_LANDLOCK_ACCESS_FS_READ_FILE = 1 << 2
_LANDLOCK_ACCESS_FS_READ_DIR = 1 << 3
_LANDLOCK_ACCESS_FS_REMOVE_DIR = 1 << 4
_LANDLOCK_ACCESS_FS_REMOVE_FILE = 1 << 5
_LANDLOCK_ACCESS_FS_MAKE_DIR = 1 << 7
_LANDLOCK_ACCESS_FS_MAKE_REG = 1 << 8
_LANDLOCK_ACCESS_FS_TRUNCATE = 1 << 14

# linux/prctl.h
_PR_SET_NO_NEW_PRIVS = 38


class LandlockError(RuntimeError):
    """Base Landlock error."""


class LandlockUnavailable(LandlockError):
    """Raised when Landlock is unavailable."""


@dataclass(frozen=True, slots=True)
class LandlockPolicy:
    """Allowlist policy for Landlock."""

    ro_paths: tuple[Path, ...] = ()
    rw_paths: tuple[Path, ...] = ()


class _RulesetAttr(ctypes.Structure):
    _fields_ = [
        ("handled_access_fs", ctypes.c_uint64),
        ("handled_access_net", ctypes.c_uint64),
    ]


class _PathBeneathAttr(ctypes.Structure):
    _pack_ = 1
    _fields_ = [
        ("allowed_access", ctypes.c_uint64),
        ("parent_fd", ctypes.c_int32),
    ]


_LIBC: Optional[ctypes.CDLL] = None
_SYSCALL_NR: Optional[dict[str, int]] = None


def _get_libc() -> ctypes.CDLL:
    global _LIBC
    if _LIBC is None:
        libc = ctypes.CDLL("libc.so.6", use_errno=True)
        libc.syscall.restype = ctypes.c_long
        libc.prctl.restype = ctypes.c_int
        _LIBC = libc
    return _LIBC


def _syscall_numbers() -> dict[str, int]:
    names = [
        "landlock_create_ruleset",
        "landlock_add_rule",
        "landlock_restrict_self",
    ]
    header_candidates = [
        Path("/usr/include/asm-generic/unistd.h"),
        Path("/usr/include/x86_64-linux-gnu/asm/unistd_64.h"),
        Path("/usr/include/aarch64-linux-gnu/asm/unistd.h"),
    ]
    pattern = re.compile(r"^#define\\s+__NR_(?P<name>[a-z0-9_]+)\\s+(?P<nr>\\d+)\\s*$")
    found: dict[str, int] = {}
    for header in header_candidates:
        try:
            content = header.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for line in content.splitlines():
            match = pattern.match(line.strip())
            if not match:
                continue
            name = match.group("name")
            if name in names:
                found[name] = int(match.group("nr"))
        if all(name in found for name in names):
            break

    if all(name in found for name in names):
        return found

    arch = platform.machine().lower()
    if arch in {"x86_64", "amd64", "aarch64", "arm64"}:
        return {
            "landlock_create_ruleset": 444,
            "landlock_add_rule": 445,
            "landlock_restrict_self": 446,
        }
    raise LandlockUnavailable(
        "unable to determine Landlock syscall numbers for this architecture"
    )


def _get_syscall_numbers() -> dict[str, int]:
    global _SYSCALL_NR
    if _SYSCALL_NR is None:
        _SYSCALL_NR = _syscall_numbers()
    return _SYSCALL_NR


def _raise_errno(prefix: str) -> None:
    err = ctypes.get_errno()
    raise OSError(err, f"{prefix}: {os.strerror(err)}")


def _syscall(nr: int, *args: object) -> int:
    libc = _get_libc()
    result = libc.syscall(ctypes.c_long(nr), *args)
    if result == -1:
        _raise_errno(f"syscall({nr}) failed")
    return int(result)


def _prctl(option: int, arg2: int, arg3: int = 0, arg4: int = 0, arg5: int = 0) -> None:
    libc = _get_libc()
    result = libc.prctl(option, arg2, arg3, arg4, arg5)
    if result != 0:
        _raise_errno("prctl failed")


def landlock_abi_version() -> int:
    if platform.system().lower() != "linux":
        raise LandlockUnavailable("Landlock is only available on Linux")
    syscall_nr = _get_syscall_numbers()
    try:
        abi = _syscall(
            syscall_nr["landlock_create_ruleset"],
            ctypes.c_void_p(0),
            ctypes.c_size_t(0),
            ctypes.c_uint32(_LANDLOCK_CREATE_RULESET_VERSION),
        )
    except OSError as exc:
        raise LandlockUnavailable(
            "Landlock is unavailable (kernel too old or disabled)"
        ) from exc
    if abi <= 0:
        raise LandlockUnavailable(f"invalid Landlock ABI version: {abi}")
    return abi


def _supported_fs_rights_for_abi(abi: int) -> int:
    # v1 up to bit 12, v2 adds bit 13, v3 adds bit 14
    v1 = (1 << 13) - 1
    v2 = (1 << 14) - 1
    v3 = (1 << 15) - 1
    if abi <= 1:
        return v1
    if abi == 2:
        return v2
    return v3


def _normalize_paths(paths: Iterable[Path]) -> list[Path]:
    normalized: list[Path] = []
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


def _add_path_rule(*, ruleset_fd: int, path: Path, allowed_access: int) -> None:
    target = path
    try:
        if target.is_file():
            target = target.parent
    except OSError:
        target = target.parent

    fd = os.open(str(target), os.O_PATH | os.O_CLOEXEC)
    try:
        attr = _PathBeneathAttr()
        attr.allowed_access = ctypes.c_uint64(int(allowed_access))
        attr.parent_fd = ctypes.c_int32(fd)
        syscall_nr = _get_syscall_numbers()
        _syscall(
            syscall_nr["landlock_add_rule"],
            ctypes.c_int(ruleset_fd),
            ctypes.c_int(_LANDLOCK_RULE_PATH_BENEATH),
            ctypes.byref(attr),
            ctypes.c_uint32(0),
        )
    finally:
        os.close(fd)


def _create_ruleset_fd(*, handled_access_fs: int) -> int:
    attr = _RulesetAttr()
    attr.handled_access_fs = ctypes.c_uint64(int(handled_access_fs))
    attr.handled_access_net = ctypes.c_uint64(0)
    syscall_nr = _get_syscall_numbers()
    return _syscall(
        syscall_nr["landlock_create_ruleset"],
        ctypes.byref(attr),
        ctypes.c_size_t(ctypes.sizeof(attr)),
        ctypes.c_uint32(0),
    )


def apply_landlock(policy: LandlockPolicy) -> int:
    """Apply Landlock policy to the current process.

    Returns the detected Landlock ABI version.
    """

    abi = landlock_abi_version()
    supported_rights = _supported_fs_rights_for_abi(abi)

    ro_access = _LANDLOCK_ACCESS_FS_READ_FILE | _LANDLOCK_ACCESS_FS_READ_DIR
    rw_access = (
        ro_access
        | _LANDLOCK_ACCESS_FS_WRITE_FILE
        | _LANDLOCK_ACCESS_FS_TRUNCATE
        | _LANDLOCK_ACCESS_FS_MAKE_DIR
        | _LANDLOCK_ACCESS_FS_MAKE_REG
        | _LANDLOCK_ACCESS_FS_REMOVE_DIR
        | _LANDLOCK_ACCESS_FS_REMOVE_FILE
    )

    ro_access &= supported_rights
    rw_access &= supported_rights
    handled_access_fs = ro_access | rw_access
    if handled_access_fs == 0:
        raise LandlockUnavailable("Landlock supported fs rights are empty")

    ruleset_fd: Optional[int] = None
    try:
        ruleset_fd = _create_ruleset_fd(handled_access_fs=handled_access_fs)

        for path in _normalize_paths(policy.ro_paths):
            if path.exists():
                _add_path_rule(ruleset_fd=ruleset_fd, path=path, allowed_access=ro_access)

        for path in _normalize_paths(policy.rw_paths):
            if path.exists():
                _add_path_rule(ruleset_fd=ruleset_fd, path=path, allowed_access=rw_access)

        _prctl(_PR_SET_NO_NEW_PRIVS, 1)
        syscall_nr = _get_syscall_numbers()
        _syscall(
            syscall_nr["landlock_restrict_self"],
            ctypes.c_int(ruleset_fd),
            ctypes.c_uint32(0),
        )
        return abi
    finally:
        if ruleset_fd is not None:
            try:
                os.close(ruleset_fd)
            except OSError:
                pass


__all__ = [
    "LandlockError",
    "LandlockPolicy",
    "LandlockUnavailable",
    "apply_landlock",
    "landlock_abi_version",
]
