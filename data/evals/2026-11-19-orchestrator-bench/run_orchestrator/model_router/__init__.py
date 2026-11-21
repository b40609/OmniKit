"""Pure-stdlib model catalog and role resolution package."""

from .catalog import diff_catalogs, parse_agy_models, parse_t3_capabilities
from .resolver import resolve_role

__all__ = [
    "parse_t3_capabilities",
    "parse_agy_models",
    "diff_catalogs",
    "resolve_role",
]
