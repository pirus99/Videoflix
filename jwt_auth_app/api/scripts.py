import json, os
import uuid
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.core.cache import cache

def sendMail(userEmail, token):
    user = User.objects.get(email=userEmail)
    activation_key = str(uuid.uuid4())[:32]
    data = {'uid': user.pk, 'token': token}
    cache.set(activation_key, json.dumps(data), 900)
    site_url = os.environ.get("SITE_URL", default="http://localhost:8000")
    activation_link = f"{site_url}api/activate/{activation_key}/"
    print(cache.get(activation_key))

    
    send_mail(
        'Welcome to Videoflix!', # Subject
        'Thanks for signing up. Here is your activation link: ' + activation_link, # Message
        'videoflix@example.com', # From email
        [userEmail], # To email
        fail_silently=False, # Raise an error if sending fails
    )
    return True