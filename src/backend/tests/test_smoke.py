import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_openapi_schema_is_served(client):
    response = client.get(reverse("schema"))
    assert response.status_code == 200
