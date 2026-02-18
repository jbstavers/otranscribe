"""
Configure the test environment to locate the package under ``src``.

pytest automatically imports this module before running tests.  Here we
insert the ``src`` directory into ``sys.path`` so that ``import
otranscribe`` in tests resolves to the local source tree without
needing to install the package first.  This mirrors the behaviour of
``python -m pip install -e .`` but works for local test runs.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add the src directory to sys.path at runtime.  Resolve the parent
# directory of this conftest.py file and append its ``src`` sibling.
_SRC = (Path(__file__).resolve().parents[1] / "src").as_posix()
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)