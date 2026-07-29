"""register-mcp — Swiss register data via MCP."""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _distribution_version

try:
    # Read the version from the installed distribution metadata, which is built
    # from pyproject.toml. There was no version here at all; the only version
    # string lived in the User-Agent (1.0) and had drifted from the packaged
    # 0.5.0. A value nobody has to remember to bump cannot go stale.
    __version__ = _distribution_version("register-mcp")
except PackageNotFoundError:
    # Running from the source tree without an install (e.g. a bare checkout).
    # Deliberately not a plausible-looking number: an obviously non-release
    # marker is better than a wrong version in the User-Agent.
    __version__ = "0.0.0+source"
