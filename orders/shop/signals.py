from django.dispatch import receiver, Signal
from django_rest_passwordreset.signals import reset_password_token_created

from auth_api.models import ConfirmEmailToken, User


from .tasks import send_email

new_user_registered = Signal('user_id')

new_order = Signal('user_id')


@receiver(reset_password_token_created)
def password_reset_token_created(sender, instance, reset_password_token, **kwargs):
    """
    Message with reset-pass token
    When a token is created, an e-mail needs to be sent to the user
    :param sender: View Class that sent the signal
    :param instance: View Instance that sent the signal
    :param reset_password_token: Token Model Object
    :param kwargs:
    :return:
    """
    # send an e-mail to the user
    message = f'Token {reset_password_token.key}'
    email = reset_password_token.user
    send_email(message, email)


@receiver(new_user_registered)
def new_user_registered_signal(user_id, **kwargs):
    """
    message confirmation of mail
    """
    # send an e-mail to the user
    token, _ = ConfirmEmailToken.objects.get_or_create(user_id=user_id)
    message = token.key
    email = token.user.email
    send_email(message, email)


@receiver(new_order)
def new_order_signal(user_id, **kwargs):
    """
    message of changing status of order
    """
    # send an e-mail to the user
    user = User.objects.get(id=user_id)
    title = "Refreshing status"
    message = 'Order completed'
    email = user.email
    send_email.apply_async((title, message, email), countdown=5 * 60)