from asyncio import exceptions
from rest_framework_simplejwt.authentication import JWTAuthentication
from django.conf import settings


class CustomJWTAuthentication(JWTAuthentication):
    """
    Custom JWT authentication that reads tokens from HTTP-only cookies.
    
    Extends the standard JWT authentication to support cookie-based token
    storage for improved security against XSS attacks.
    """
    
    def authenticate(self, request):
        """
        Extract and validate JWT token from cookies.
        
        Args:
            request: HTTP request object
            
        Returns:
            tuple: (user, validated_token) if authentication succeeds
            None: If no token is present in cookies
        """
        raw_token = request.COOKIES.get('access_token') or None
        if raw_token is None:
            return None

        validated_token = self.get_validated_token(raw_token)
        return self.get_user(validated_token), validated_token