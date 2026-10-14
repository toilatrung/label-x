"""MBE-00 specifies 400, not DRF's default 404, for malformed cursors."""

from rest_framework.exceptions import NotFound
from rest_framework.pagination import Cursor, CursorPagination
from rest_framework.request import Request

from config.exceptions import ApiError


class SummaryCursorPagination(CursorPagination):
    page_size = 50
    ordering = "-id"

    def decode_cursor(self, request: Request) -> Cursor | None:
        try:
            cursor = super().decode_cursor(request)
        except NotFound:
            raise ApiError(400, "VALIDATION_ERROR", "Cursor không hợp lệ.") from None
        if cursor is not None and cursor.position is not None:
            value = str(cursor.position)
            if (
                not value.isascii()
                or not value.isdigit()
                or len(value) > 19
                or int(value) > 2**63 - 1
            ):
                raise ApiError(400, "VALIDATION_ERROR", "Vị trí cursor không hợp lệ.")
        return cursor
