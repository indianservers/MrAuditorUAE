"""Compare explicit domestic component spellings without changing retained source text."""

import re


def india_domestic_component(value):
    return re.sub(r"\s+", "", str(value)).upper().split(":")[0] in {"PF", "ESI", "PT", "TDS", "TCS"}
