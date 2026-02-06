import email
import json, os
import secrets
import uuid
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.core.cache import cache

def sendActivationEmail(userEmail, token):
    user = User.objects.get(email=userEmail)
    sender_email = os.environ.get("EMAIL_HOST_USER", default="videoflix@example.com")
    activation_key = str(uuid.uuid4())[:32]
    data = {'uid': user.pk, 'token': token}
    cache.set(activation_key, json.dumps(data), 900)
    site_url = os.environ.get("SITE_URL", default="http://localhost:8000")
    activation_link = f"{site_url}api/activate/{activation_key}"
    
    send_mail(
        'Welcome to Videoflix!', # Subject
        'Thanks for signing up. Here is your activation link: ' + activation_link, # Message
        sender_email, # From email
        [userEmail], # To email
        fail_silently=False, # Raise an error if sending fails
    )
    return True

def sendPasswordResetEmail(userEmail):
    user = User.objects.get(email=userEmail)
    sender_email = os.environ.get("EMAIL_HOST_USER", default="videoflix@example.com")
    reset_token = secrets.token_urlsafe(16)
    cache.set(f'password_reset_{reset_token}', user.pk, 900)  # Store user ID with token in cache

    site_url = os.environ.get("SITE_URL", default="http://localhost:8000")
    reset_link = f"{site_url}api/password_confirm/{reset_token}/"

    send_mail(
        'Videoflix Password Reset Request',
        f'Click the link to reset your password: {reset_link}',
        sender_email,
        [userEmail],
        fail_silently=False,
    )