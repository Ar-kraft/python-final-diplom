from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.http import JsonResponse
from django.db import IntegrityError
from django.db.models import Q, Sum, F
from django.db.models.query import Prefetch
from rest_framework import status, viewsets
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.authtoken.models import Token
from yaml import load as load_yaml, Loader
from ujson import loads as load_json
from distutils.util import strtobool
from requests import get
from shop.tasks import import_shop_data
from .signals import new_user_registered
from .models import Category, Shop, ProductInfo, Order, OrderItem, Product, ProductParameter, Parameter

from auth_api.models import Contact, ConfirmEmailToken
from .serializers import UserSerializer
from .serializers import (
    CategorySerializer,
    ShopSerializer,
    UserSerializer,
    ProductInfoSerializer,
    OrderSerializer,
    OrderItemSerializer,
    UserSerializer,
    ContactSerializer,
)

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


class LoginAccount(APIView):
    """
    auth class
    """
    throttle_scope = 'anon'

    def post(self, request, *args, **kwargs):
        if {'email', 'password'}.issubset(request.data):
            user = authenticate(request, username=request.data['email'], password=request.data['password'])

            if user is not None:
                if user.is_active:
                    token, _ = Token.objects.get_or_create(user=user)

                    return Response({'Status': True, 'Token': token.key})

            return Response({'Status': False, 'Errors': 'Not autorized'}, status=status.HTTP_403_FORBIDDEN)

        return Response({'Status': False, 'Errors': 'Not all required parameters are used'},
                        status=status.HTTP_400_BAD_REQUEST)


class AccountDetails(APIView):
    """
    Acc data class
    """
    throttle_scope = 'user'

    # return data of user
    def get(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return Response({'Status': False, 'Error': 'Login required'}, status=status.HTTP_403_FORBIDDEN)

        serializer = UserSerializer(request.user)
        return Response(serializer.data)

    # changing data of user
    def post(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return Response({'Status': False, 'Error': 'Login required'}, status=status.HTTP_403_FORBIDDEN)

        # check password if exist and save
        if 'password' in request.data:
            try:
                validate_password(request.data['password'])
            except Exception as password_error:
                return Response({'Status': False, 'Errors': {'password': password_error}})
            else:
                request.user.set_password(request.data['password'])

        # checck additional data
        user_serializer = UserSerializer(request.user, data=request.data, partial=True)
        if user_serializer.is_valid():
            user_serializer.save()
            return Response({'Status': True}, status=status.HTTP_201_CREATED)
        else:
            return Response({'Status': False, 'Errors': user_serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

class CategoryView(viewsets.ModelViewSet):
    """
    viewing category class
    """
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    ordering = ('name',)


class ShopView(viewsets.ModelViewSet):
    """
    viewing shops class
    """

    queryset = Shop.objects.all()
    serializer_class = ShopSerializer
    ordering = ('name',)

class ProductInfoView(viewsets.ReadOnlyModelViewSet):
    """
    finding goods class
    """
    throttle_scope = 'anon'
    serializer_class = ProductInfoSerializer
    ordering = ('product',)

    def get_queryset(self):

        query = Q(shop__state=True)
        shop_id = self.request.query_params.get('shop_id')
        category_id = self.request.query_params.get('category_id')

        if shop_id:
            query = query & Q(shop_id=shop_id)

        if category_id:
            query = query & Q(product__category_id=category_id)

        # sorting & deduplicating
        queryset = ProductInfo.objects.filter(
            query).select_related(
            'shop', 'product__category').prefetch_related(
            'product_parameters__parameter').distinct()

        return queryset


class BasketView(APIView):
    """
    user basket class
    """
    throttle_scope = 'user'

    # получить корзину
    def get(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'}, status=status.HTTP_403_FORBIDDEN)
        basket = Order.objects.filter(
            user_id=request.user.id, status='basket').prefetch_related(
            'ordered_items__product_info__product__category',
            'ordered_items__product_info__product_parameters__parameter').annotate(
            total_sum=Sum(F('ordered_items__quantity') * F('ordered_items__product_info__price'))).distinct()

        serializer = OrderSerializer(basket, many=True)
        return Response(serializer.data)

    # basket editor
    def post(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'}, status=status.HTTP_403_FORBIDDEN)

        items_sting = request.data.get('items')
        if items_sting:
            try:
                items_dict = load_json(items_sting)
            except ValueError:
                JsonResponse({'Status': False, 'Errors': 'wrong query formatt'})
            else:
                basket, _ = Order.objects.get_or_create(user_id=request.user.id, state='basket')
                objects_created = 0
                for order_item in items_dict:
                    order_item.update({'order': basket.id})
                    serializer = OrderItemSerializer(data=order_item)
                    if serializer.is_valid():
                        try:
                            serializer.save()
                        except IntegrityError as error:
                            return JsonResponse({'Status': False, 'Errors': str(error)})
                        else:
                            objects_created += 1
                    else:
                        JsonResponse({'Status': False, 'Errors': serializer.errors})

                return JsonResponse({'Status': True, 'Objects created': objects_created})
        return JsonResponse({'Status': False, 'Errors': 'Not all required parameters are used'})

    # удалить товары из корзины
    def delete(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'}, status=status.HTTP_403_FORBIDDEN)

        items_sting = request.data.get('items')
        if items_sting:
            items_list = items_sting.split(',')
            basket, _ = Order.objects.get_or_create(user_id=request.user.id, state='basket')
            query = Q()
            objects_deleted = False
            for order_item_id in items_list:
                if order_item_id.isdigit():
                    query = query | Q(order_id=basket.id, id=order_item_id)
                    objects_deleted = True

            if objects_deleted:
                deleted_count = OrderItem.objects.filter(query).delete()[0]
                return JsonResponse({'Status': True, 'Deleted objects': deleted_count})
        return JsonResponse({'Status': False, 'Errors': 'Not all required parameters are used'})

    # adding goods to basket
    def put(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'}, status=status.HTTP_403_FORBIDDEN)

        items_sting = request.data.get('items')
        if items_sting:
            try:
                items_dict = load_json(items_sting)
            except ValueError:
                JsonResponse({'Status': False, 'Errors': 'Wrong query formatt'})
            else:
                basket, _ = Order.objects.get_or_create(user_id=request.user.id, state='basket')
                objects_updated = 0
                for order_item in items_dict:
                    if type(order_item['id']) == int and type(order_item['quantity']) == int:
                        objects_updated += OrderItem.objects.filter(order_id=basket.id, id=order_item['id']).update(
                            quantity=order_item['quantity'])

                return JsonResponse({'Status': True, 'Updated objects': objects_updated})
        return JsonResponse({'Status': False, 'Errors': 'Not all required parameters are used'})


class OrderView(APIView):
    """
    Get&post orders custumer's class
    """
    throttle_scope = 'user'

    def get(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return Response({'Status': False, 'Error': 'Log in required'}, status=status.HTTP_403_FORBIDDEN)

        order = Order.objects.filter(
            user_id=request.user.id).exclude(status='basket').select_related('contact').prefetch_related(
            'ordered_items').annotate(
            total_quantity=Sum('ordered_items__quantity'),
            total_sum=Sum('ordered_items__total_amount')).distinct()

        serializer = OrderSerializer(order, many=True)
        return Response(serializer.data)

    # Basket order and mail confirmation
    def post(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return Response({'Status': False, 'Error': 'Log in required'}, status=status.HTTP_403_FORBIDDEN)

        if request.data['id'].isdigit():
            try:
                is_updated = Order.objects.filter(
                    id=request.data['id'], user_id=request.user.id).update(
                    contact_id=request.data['contact'],
                    status='new')
            except IntegrityError as error:
                return Response({'Status': False, 'Errors': 'Not all required parameters are used'},
                                status=status.HTTP_400_BAD_REQUEST)
            else:
                if is_updated:
                    request.user.email_user(
                        'Updating status of order',
                        'Order is completed',
                        from_email=settings.EMAIL_HOST_USER,
                    )
                    return Response({'Status': True})

        return Response({'Status': False, 'Errors': 'Not all required parameters are used'},
                        status=status.HTTP_400_BAD_REQUEST)

class ContactView(APIView):
    """
    Customers contact class
    """
    throttle_scope = 'user'

    # get contacts
    def get(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'}, status=status.HTTP_403_FORBIDDEN)
        contact = Contact.objects.filter(
            user_id=request.user.id)
        serializer = ContactSerializer(contact, many=True)
        return Response(serializer.data)

    # add new contact
    def post(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'}, status=status.HTTP_403_FORBIDDEN)

        if {'city', 'phone'}.issubset(request.data):
            request.data._mutable = True
            request.data.update({'user': request.user.id})
            serializer = ContactSerializer(data=request.data)

            if serializer.is_valid():
                serializer.save()
                return JsonResponse({'Status': True})
            else:
                JsonResponse({'Status': False, 'Errors': serializer.errors})

        return JsonResponse({'Status': False, 'Errors': 'Not all required parameters are used'})

    # delete contact
    def delete(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'}, status=status.HTTP_403_FORBIDDEN)

        items_sting = request.data.get('items')
        if items_sting:
            items_list = items_sting.split(',')
            query = Q()
            objects_deleted = False
            for contact_id in items_list:
                if contact_id.isdigit():
                    query = query | Q(user_id=request.user.id, id=contact_id)
                    objects_deleted = True

            if objects_deleted:
                deleted_count = Contact.objects.filter(query).delete()[0]
                return JsonResponse({'Status': True, 'Deleted objects': deleted_count})
        return JsonResponse({'Status': False, 'Errors': 'Not all required parameters are used'})

    # edit contact
    def put(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'Status': False, 'Error': 'Log in required'}, status=status.HTTP_403_FORBIDDEN)

        if 'id' in request.data:
            if request.data['id'].isdigit():
                contact = Contact.objects.filter(id=request.data['id'], user_id=request.user.id).first()
                print(contact)
                if contact:
                    serializer = ContactSerializer(contact, data=request.data, partial=True)
                    if serializer.is_valid():
                        serializer.save()
                        return JsonResponse({'Status': True})
                    else:
                        JsonResponse({'Status': False, 'Errors': serializer.errors})

        return JsonResponse({'Status': False, 'Errors': 'Not all required parameters are used'})


class PartnerOrders(APIView):
    """
    get orders by supllier class
    """
    throttle_scope = 'user'

    def get(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return Response({'Status': False, 'Error': 'Login required'}, status=status.HTTP_403_FORBIDDEN)

        if request.user.type != 'shop':
            return Response({'Status': False, 'Error': 'Only for shops'}, status=status.HTTP_403_FORBIDDEN)

        pr = Prefetch('ordered_items', queryset=OrderItem.objects.filter(shop__user_id=request.user.id))
        order = Order.objects.filter(
            ordered_items__shop__user_id=request.user.id).exclude(status='basket') \
            .prefetch_related(pr).select_related('contact').annotate(
            total_sum=Sum('ordered_items__total_amount'),
            total_quantity=Sum('ordered_items__quantity'))

        serializer = OrderSerializer(order, many=True)
        return Response(serializer.data)

class PartnerState(APIView):
    """
    supllier status class
    """
    throttle_scope = 'user'

    # get current status of shop's orders
    def get(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return Response({'Status': False, 'Error': 'Login required'}, status=status.HTTP_403_FORBIDDEN)

        if request.user.type != 'shop':
            return Response({'Status': False, 'Error': 'Only for shop'}, status=status.HTTP_403_FORBIDDEN)

        shop = request.user.shop
        serializer = ShopSerializer(shop)
        return Response(serializer.data)

    # change current status of shop's orders
    def post(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return Response({'Status': False, 'Error': 'Log in required'}, status=status.HTTP_403_FORBIDDEN)

        if request.user.type != 'shop':
            return Response({'Status': False, 'Error': 'Only for shop'}, status=status.HTTP_403_FORBIDDEN)

        state = request.data.get('state')
        if state:
            try:
                Shop.objects.filter(user_id=request.user.id).update(state=strtobool(state))
                return Response({'Status': True})
            except ValueError as error:
                return Response({'Status': False, 'Errors': str(error)}, status=status.HTTP_400_BAD_REQUEST)

        return Response({'Status': False, 'Errors': 'Need to define state.'}, status=status.HTTP_400_BAD_REQUEST)


class PartnerUpdate(APIView):
    """
    Update supplier price class
    """
    throttle_scope = 'partner'

    def post(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return Response({'Status': False, 'Error': 'Log in required'}, status=status.HTTP_403_FORBIDDEN)

        if request.user.type != 'shop':
            return Response({'Status': False, 'Error': 'Only for shop'}, status=status.HTTP_403_FORBIDDEN)

        file = request.FILES
        if file:
            user_id = request.user.id
            import_shop_data(file, user_id)

            return Response({'Status': True})

        return Response({'Status': False, 'Errors': 'Not all required parameters are used'},
                        status=status.HTTP_400_BAD_REQUEST)