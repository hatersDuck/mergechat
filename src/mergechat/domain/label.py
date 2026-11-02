"""Manual labelling vocabulary."""

from __future__ import annotations

from enum import StrEnum


class LabelValue(StrEnum):
    ORDER = "order"
    NOT_ORDER = "not_order"
    UNCERTAIN = "uncertain"
