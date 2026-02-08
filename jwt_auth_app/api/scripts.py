import json, os
import secrets
import uuid
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.core.cache import cache

def getSiteURL():
    return os.environ.get("SITE_URL", default="http://localhost:8000")

def getSenderEmail():
    return os.environ.get("EMAIL_HOST_USER", default="videoflix@example.com")

def sendActivationEmail(userEmail):
    token = secrets.token_urlsafe(16)
    user = User.objects.get(email=userEmail)
    activation_key = str(uuid.uuid4())[:32]
    activation_link = f"{getSiteURL()}api/activate/{token}"
    
    data = {'uid': user.pk, 'activation_key': activation_key }
    cache.set(token, json.dumps(data), 900)  # Store data in cache for 15 minutes

    send_mail(
        'Welcome to Videoflix!', # Subject
        'Thanks for signing up. Here is your activation link: ' + activation_link, # Message
        getSenderEmail(), # From email
        [userEmail], # To email
        fail_silently=False, # Raise an error if sending fails
    )
    return True

def sendPasswordResetEmail(userEmail):
    user = User.objects.get(email=userEmail)
    reset_token = secrets.token_urlsafe(16)
    cache.set(f'password_reset_{reset_token}', user.pk, 900)  # Store user ID with token in cache

    reset_link = f"{getSiteURL()}api/password_confirm/{reset_token}/"

    send_mail(
        'Videoflix Password Reset Request',
        f'Click the link to reset your password: {reset_link}',
        getSenderEmail(),
        [userEmail],
        fail_silently=False,
    )