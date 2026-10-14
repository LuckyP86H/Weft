"""Small shared types."""

from __future__ import annotations

from typing import Literal

SourceType = Literal[
    "article",
    "news",
    "video",
    "thought",
    "book",
    "seminar",
    "work",
    "conversation",
    "other",
]
