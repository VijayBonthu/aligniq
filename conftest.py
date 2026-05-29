"""Test bootstrap.

The app runs with `src/` on PYTHONPATH (see `python src/main.py`), so modules
inside `src/` import each other as `from config import settings` or
`from utils.X import Y` without the `src.` prefix. Tests would otherwise fail
to import any module that transits the agents package, because
`src/agents/__init__.py` re-exports the legacy pipeline which depends on those
bare imports. Putting `src/` on sys.path here keeps test imports honest with
how the app actually runs.
"""

import sys
from pathlib import Path

_SRC = Path(__file__).parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
