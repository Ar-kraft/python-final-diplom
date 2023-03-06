from django.contrib.auth.password_validation import validate_password
from django.http import JsonResponse

from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response

from auth_api.models import Contact, ConfirmEmailToken
from .serializers import UserSerializer


class RegisterAccount(APIView):
    """
    Customers registration
    """
    throttle_scope = 'anon'

    # Registration by POST
    def post(self, request, *args, **kwargs):

        # main para check
        if {'first_name', 'last_name', 'email', 'password', 'company', 'position'}.issubset(request.data):
            errors = {}

            # complexity password check

            try:
                validate_password(request.data['password'])
            except Exception as password_error:
                error_array = list(password_error)
                return JsonResponse({'Status': False, 'Errors': {'password': error_array}})
            else:
                return self._extracted_from_post_(request)
        return JsonResponse({'Status': False, 'Errors': 'Not all required parameters are used'})

    def _extracted_from_post_(self, request):
        # Availability login check
        request.data.update({})
        user_serializer = UserSerializer(data=request.data)
        if not user_serializer.is_valid():
            return JsonResponse({'Status': False, 'Errors': user_serializer.errors})

        # Recording of user
        user = user_serializer.save()
        user.set_password(request.data['password'])
        user.save()
        return JsonResponse({'Status': True})


class ConfirmAccount(APIView):
    """
    Confirming mail
    """
    throttle_scope = 'anon'

    def post(self, request, *args, **kwargs):
        # main para check
        if {'email', 'token'}.issubset(request.data):

            token = ConfirmEmailToken.objects.filter(user__email=request.data['email'],
                                                     key=request.data['token']).first()
            if token:
                token.user.is_active = True
                token.user.save()
                token.delete()
                return Response({'Status': True})
            else:
                return Response({'Status': False, 'Errors': 'Error token or email'})
        return Response({'Status': False, 'Errors': 'Not all required parameters are used'},
                        status=status.HTTP_400_BAD_REQUEST)