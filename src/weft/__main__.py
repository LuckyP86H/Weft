"""Entry point for ``python -m weft``: hand off to the CLI and exit."""

from weft.cli import main

raise SystemExit(main())
