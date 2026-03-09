"""
Pagination Utilities for Priya Global Platform

Helper functions for paginating database queries and applying sorting.

USAGE:
    from shared.utils import paginate, apply_sorting
    from shared.models import PaginationParams, SortOrder

    query = query_builder()
    sorted_query = apply_sorting(query, sort_by="created_at", sort_order=SortOrder.DESC)
    total = await db.count(sorted_query)
    results = await db.fetch(sorted_query.limit(params.limit).offset(params.offset))
    paginated = paginate(results, total, params)
"""

from typing import Any, List, Optional, TypeVar

import sqlalchemy
from sqlalchemy import Select, desc, asc
from sqlalchemy.orm import Query

from shared.models import PaginatedResponse, PaginationParams, SortOrder

T = TypeVar("T")


def paginate(
    items: List[T],
    total: int,
    page: int = 1,
    per_page: int = 20,
) -> PaginatedResponse[T]:
    """
    Create a paginated response from items and total count.

    Args:
        items: List of items for current page
        total: Total items across all pages
        page: Current page number (1-indexed)
        per_page: Items per page

    Returns:
        PaginatedResponse with metadata
    """
    return PaginatedResponse.create(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
    )


def apply_sorting(
    query: Any,
    sort_by: Optional[str] = None,
    sort_order: SortOrder = SortOrder.DESC,
) -> Any:
    """
    Apply sorting to a SQLAlchemy query.

    SECURITY:
    - Only sorts by whitelisted columns (must exist on model)
    - Protects against SQL injection via sort_by parameter
    - Always validates column exists before applying

    Args:
        query: SQLAlchemy query or select statement
        sort_by: Column name to sort by (must exist on model)
        sort_order: ASC or DESC

    Returns:
        Query with sorting applied

    Raises:
        ValueError: If sort_by column doesn't exist
    """
    if not sort_by:
        return query

    # For SQLAlchemy ORM Query objects
    if isinstance(query, Query):
        model = query.column_descriptions[0]["entity"]
        if not hasattr(model, sort_by):
            raise ValueError(f"Column '{sort_by}' not found on model")
        column = getattr(model, sort_by)
        order_by = desc(column) if sort_order == SortOrder.DESC else asc(column)
        return query.order_by(order_by)

    # For SQLAlchemy 2.0 Select objects
    if isinstance(query, Select):
        # Get model from select statement
        try:
            model = query.get_final_froms()[0]
        except (IndexError, AttributeError):
            # If we can't extract model, return unsorted
            return query

        if not hasattr(model, sort_by):
            raise ValueError(f"Column '{sort_by}' not found on model")

        column = getattr(model, sort_by)
        order_by = desc(column) if sort_order == SortOrder.DESC else asc(column)
        return query.order_by(order_by)

    # Unknown query type
    return query


def calculate_offset(page: int, per_page: int) -> int:
    """
    Calculate database offset from page number.

    Args:
        page: Page number (1-indexed)
        per_page: Items per page

    Returns:
        Database offset (0-indexed)
    """
    return (max(1, page) - 1) * per_page


def calculate_total_pages(total: int, per_page: int) -> int:
    """
    Calculate total number of pages.

    Args:
        total: Total items
        per_page: Items per page

    Returns:
        Total pages (ceiling division)
    """
    return (total + per_page - 1) // per_page


class PaginationHelper:
    """
    Utility class for common pagination operations.

    USAGE:
        helper = PaginationHelper(params=PaginationParams(page=2, per_page=20))
        offset = helper.offset()
        total_pages = helper.total_pages(total_items=100)
        response = helper.paginated_response(items, total=100)
    """

    def __init__(self, params: PaginationParams):
        self.params = params

    def offset(self) -> int:
        """Get database offset."""
        return self.params.offset

    def limit(self) -> int:
        """Get database limit."""
        return self.params.limit

    def is_first_page(self) -> bool:
        """Check if current page is first."""
        return self.params.page == 1

    def is_last_page(self, total: int) -> bool:
        """Check if current page is last."""
        total_pages = calculate_total_pages(total, self.params.per_page)
        return self.params.page >= total_pages

    def total_pages(self, total: int) -> int:
        """Calculate total pages."""
        return calculate_total_pages(total, self.params.per_page)

    def next_page(self) -> int:
        """Get next page number."""
        return self.params.page + 1

    def previous_page(self) -> int:
        """Get previous page number."""
        return max(1, self.params.page - 1)

    def paginated_response(self, items: List[T], total: int) -> PaginatedResponse[T]:
        """Create paginated response."""
        return paginate(
            items=items,
            total=total,
            page=self.params.page,
            per_page=self.params.per_page,
        )
