
import pytest
from django.urls import reverse
from rest_framework.status import HTTP_200_OK, HTTP_401_UNAUTHORIZED, HTTP_201_CREATED, HTTP_403_FORBIDDEN
from rest_framework.test import APIClient

@pytest.mark.django_db
def test_user_reg():
    client = APIClient()
    rand_user = {
        "first_name": "A",
        "last_name": "aaaa",
        "email": "test@aaaa.com",
        "password": "13213423baaaaf",
        "company": "Rtttttt",
        "position": "Abbbb"
    }

    url = reverse("user-register")
    resp = client.post(url, data=rand_user)

    assert resp.status_code == HTTP_201_CREATED
    assert resp.json().get('Status') is True