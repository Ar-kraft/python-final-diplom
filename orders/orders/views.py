from rest_framework.decorators import api_view
from rest_framework.response import Response



# Create your views here.

@api_view(['GET'])
def index(request):

    data = {
        'Init_msg': 'REST API',
        'URL API link here': 'http://127.0.0.1:8000/api/v1/',
        'Admin Panel Here': 'http://127.0.0.1:8000/admin/login/?next=/admin/',
        'Login': 'admin@admin.com',
        'Password': '12341234'
    }
    return Response(data)
