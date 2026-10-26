r"""Turns a path typed in the web app into a path the service can open.
In Docker the service sees a Linux filesystem; the Windows installer mounts the chosen drives read-only under /host/<letter>
and passes PREVEDA_PATH_MAP="C:=/host/c,D:=/host/d". So  D:\Hospital\Fundus  ->  /host/d/Hospital/Fundus ."""
from __future__ import annotations
import os, re
from .settings import get_settings

_WIN = re.compile(r"^([A-Za-z]):[\\/]*(.*)$")


def drive_map() -> dict[str, str]:
    out = {}
    for part in get_settings().path_map.split(","):
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip().rstrip(":").upper()] = v.strip().rstrip("/")
    return out


def is_windows_path(p: str) -> bool:
    return bool(_WIN.match(p.strip()))


def to_server_path(p: str) -> tuple[str | None, str]:
    """-> (path the service can use or None, message if it cannot)."""
    p = p.strip().strip('"')
    m = _WIN.match(p)
    if not m or os.name == "nt":
        return p, ""
    letter, rest = m.group(1).upper(), m.group(2)
    dm = drive_map()
    if letter not in dm:
        shared = ", ".join(sorted(k + ":" for k in dm)) or "none"
        return None, (f"Drive {letter}: is not shared with Madhu-DR (shared drives: {shared}). "
                      "Run Install-PreVeda.bat again and include that drive.")
    root = dm[letter]
    parts = [x for x in re.split(r"[\\/]+", rest) if x]
    if ".." in parts:
        return None, "Paths containing '..' are not allowed."
    return "/".join([root] + parts), ""
