import pytest
from django.db.backends.signals import connection_created


@pytest.fixture(autouse=True)
def _no_auto_dispatch(settings):
    """Test không có broker: tắt tự xếp shard vào Celery khi tạo run (T-025)."""
    settings.ORCHESTRATION_AUTO_DISPATCH = False
    settings.FINAL_RUN_AUTO_DISPATCH = False


def _allow_evidence_truncate(sender, connection, **kwargs):
    """Test cần Django flush (TRUNCATE) giữa các test; production không đặt cờ này nên bị chặn."""
    if connection.vendor == "postgresql":
        with connection.cursor() as cursor:
            cursor.execute("SET labelx.allow_evidence_truncate = 'on'")


connection_created.connect(_allow_evidence_truncate)
