import sys
from pathlib import Path

# Ensure the har_to_skill package is importable
_har_to_skill_root = Path(__file__).resolve().parent.parent / "har_to_skill"
if str(_har_to_skill_root) not in sys.path:
    sys.path.insert(0, str(_har_to_skill_root))
