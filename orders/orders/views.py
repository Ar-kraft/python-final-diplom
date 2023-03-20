from rest_framework.decorators import api_view
from rest_framework.response import Response
from datetime import datetime

@api_view(['GET'])
def index(request):
    data = {
        'Initial message': 'REST API Project',
        'URL API link here': 'http://127.0.0.1:8000/api/v1/',
        'Admin panel link here': 'http://127.0.0.1:8000/admin/login/?next=/admin/',
        'Login': 'gauss.ind@gmail.com',
        'Password': '12341234',
    }
    return Response(data)