import pathlib
import re
from functools import lru_cache

_PROMPTS_DIR = pathlib.Path(__file__).parent.parent / "prompts"
# The version is a configuration value, not user input, but it is interpolated into a
# filesystem path — an unconstrained value would resolve outside the prompts directory.
_VERSION_RE = re.compile(r"^v[0-9]+$")


@lru_cache(maxsize=16)
def _load(version: str) -> str:
    if not _VERSION_RE.match(version):
        raise ValueError(f"Invalid prompt version: {version!r}")
    path = _PROMPTS_DIR / f"system_{version}.md"
    if not path.exists():
        raise ValueError(f"Unknown prompt version: {version!r}")
    return path.read_text(encoding="utf-8")


class PromptRegistry:
    def get(self, version: str) -> str:
        return _load(version)
