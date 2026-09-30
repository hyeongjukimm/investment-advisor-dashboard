"""Refresh pure presentation metadata after a Streamlit Cloud hot deploy."""
import importlib


def refresh_presentation_modules():
    # Existing Cloud processes can retain imported modules while app.py is rerun.
    # These modules contain only constants/pure functions, so reload has no I/O.
    sources = importlib.reload(importlib.import_module('data_lineage'))
    guides = importlib.reload(importlib.import_module('dashboard_utils'))
    return sources, guides
