"""Bounded JSON allowance for complete reviewed field inventories."""

import re

REPORT_TEMPLATE_MAX_BYTES = 8 * 1024 * 1024
REPORT_TEMPLATE_PATH = re.compile(
    r"/api/v1/regulatory/engagements/[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}/report-templates"
)


def json_body_limit(path: str, method: str, default: int) -> int:
    if method == "POST" and REPORT_TEMPLATE_PATH.fullmatch(path):
        return max(default, REPORT_TEMPLATE_MAX_BYTES)
    return default
