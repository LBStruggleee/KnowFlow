"""Shared list-endpoint pagination.

Every list endpoint pages with the same contract: ``limit`` (default 100,
capped at 500) and ``offset`` (default 0). Responses stay bare lists so
clients that omit the parameters keep working with the default page.
"""

from typing import NamedTuple

from fastapi import Query

DEFAULT_PAGE_SIZE = 100
MAX_PAGE_SIZE = 500


class Page(NamedTuple):
    limit: int
    offset: int


def page_params(
    limit: int = Query(
        DEFAULT_PAGE_SIZE,
        ge=1,
        le=MAX_PAGE_SIZE,
        description=f"Maximum number of items to return (1-{MAX_PAGE_SIZE}).",
    ),
    offset: int = Query(0, ge=0, description="Number of items to skip."),
) -> Page:
    return Page(limit=limit, offset=offset)
