"""Utilities for interacting with YouTube."""

# Expose submodules without importing them at package import time. Importing
# ``jobs`` here created a circular import with ``multi_audio_source`` during
# tests because that module imports ``download`` which pulled in ``jobs`` via
# ``__init__``.  By only defining ``__all__`` and letting consumers import the
# submodules directly, we avoid that cycle while keeping the same public API.

__all__ = [
    "download",
    "jobs",
    "metadata",
    "utils",
]
