"""Local artifact destination; never points at the source research workspace."""
import os
from pathlib import Path
PACKAGE_ROOT = Path(__file__).resolve().parents[1]
ROOT = str(Path(os.environ.get("BLACKBOX_WORKSPACE", PACKAGE_ROOT / "workspace")).resolve())
