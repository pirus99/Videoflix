import json, os
import secrets
import uuid
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.core.cache import cache
from django.template.loader import render_to_string
from django.utils.html import strip_tags


def getFrontendURL(type='activation'):
    if type == 'activation':
        return os.environ.get("FRONTEND_URL", default="http://localhost:8000") + os.environ.get("ACTIVATION_PATH", default="pages/auth/activate.html")
    if type == 'password_reset':
        return os.environ.get("FRONTEND_URL", default="http://localhost:8000") + os.environ.get("PASSWORD_RESET_PATH", default="pages/auth/confirm_password.html")
    return os.environ.get("FRONTEND_URL", default="http://localhost:8000")

def getSenderEmail():
    return os.environ.get("EMAIL_HOST_USER", default="videoflix@example.com")

def renderEmailTemplate(linkUrl, userName, template_name='register_email.html'):
    html = render_to_string(
        template_name,
        {
            'AppName': os.environ.get("SITE_NAME", default="Videoflix"),
            'LogoUrl': os.environ.get("SITE_LOGO_URL", default="https://example.com/logo.png"),
            'LinkUrl': linkUrl,
            'UserName': userName,
            'LinkActiveDuration': '15'
        }
    ) 

    text = strip_tags(html)

    return text, html

def sendActivationEmail(userEmail):
    user = User.objects.get(email=userEmail)
    if user.is_active or user is None:
        return False
    
    token = secrets.token_urlsafe(16)
    activation_link = f"{getFrontendURL('activation')}?token={token}"

    activation_key = str(uuid.uuid4())[:32]
    data = {'uid': user.pk, 'activation_key': activation_key }
    cache.set(token, json.dumps(data), 900)  # Store data in cache for 15 minutes

    text, html = renderEmailTemplate(activation_link, user.email.split('@')[0], template_name='register_email.html')

    send_mail(
        'Welcome to Videoflix!', # Subject
        text, # Message
        getSenderEmail(), # From email
        [userEmail], # To email
        html_message=html, # HTML message
        fail_silently=False, # Raise an error if sending fails
    )
    return True

def sendPasswordResetEmail(userEmail):
    user = User.objects.get(email=userEmail)
    if user is None:
        return False
    
    reset_token = secrets.token_urlsafe(16)
    cache.set(f'password_reset_{reset_token}', user.pk, 900)  # Store user ID with token in cache

    reset_link = f"{getFrontendURL('password_reset')}?token={reset_token}"

    text, html = renderEmailTemplate(reset_link, user.email.split('@')[0], template_name='password_reset_email.html')

    send_mail(
        'Videoflix Password Reset Request',
        text,
        getSenderEmail(),
        [userEmail],
        html_message=html,
        fail_silently=False,
    )
    return True