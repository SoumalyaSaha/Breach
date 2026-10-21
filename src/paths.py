"""Project paths.

Everything that must be found regardless of the current working directory
lives relative to the project root: the `.env` file, the shared session file
that the CLI and the web UI talk through, and the `outputs/` directory.
"""

from __future__ import annotations

import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ENV_FILE = os.path.join(PROJECT_ROOT, ".env")
SESSION_FILE = os.path.join(PROJECT_ROOT, ".breach_session.json")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "outputs")
