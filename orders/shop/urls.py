from django.urls import path, include
from rest_framework import routers


app_name = 'shop'

router = routers.SimpleRouter()

urlpatterns = [
    path('', include(router.urls)),
]

urlpatterns += router.urls
