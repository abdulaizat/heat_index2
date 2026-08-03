#!/usr/bin/env python3
"""Compatibility wrapper for the Sync Quad agent doc sync."""

from __future__ import annotations

from scripts.sync_quad_agent_docs import (  # noqa: F401
    DEFAULT_TEXT,
    TARGET_FILENAMES,
    choose_source,
    ensure_newline,
    main,
    read_if_exists,
    sync_agent_docs,
)


if __name__ == "__main__":
    raise SystemExit(main())
