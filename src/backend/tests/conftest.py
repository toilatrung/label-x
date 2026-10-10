import pytest


@pytest.fixture(autouse=True)
def _no_auto_dispatch(settings):
    """Test không có broker: tắt tự xếp shard vào Celery khi tạo run (T-025)."""
    settings.ORCHESTRATION_AUTO_DISPATCH = False
