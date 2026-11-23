from __future__ import annotations

import sys
from pathlib import Path


def main() -> None:
    """Launch the Streamlit timetable web application."""
    try:
        from streamlit.web import cli
    except ImportError as error:
        raise SystemExit(
            "The web interface requires Streamlit. "
            "Install it with: python -m pip install -e ."
        ) from error

    app_path = Path(__file__).with_name("app.py")
    sys.argv = ["streamlit", "run", str(app_path)]
    cli.main()
