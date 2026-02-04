import secrets, json
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from django.core.cache import cache
from django.contrib.auth.models import User

from jwt_auth_app.api.scripts import sendMail
from .serializers import RegistrationSerializer

class RegistrationView(APIView):
    """API view for user registration."""
    
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegistrationSerializer(data=request.data)

        data = {}
        if serializer.is_valid():
            saved_account = serializer.save()
            data = {
                'deatil': 'User created successfully!'
            }
            sendMail(saved_account.email, secrets.token_urlsafe(16))
            return Response(data)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
class TokenRefreshView(APIView):
    """API view to refresh JWT access token using refresh token from cookies."""
    
    permission_classes = [AllowAny]

    def post(self, request):
        refresh_token = request.COOKIES.get('refresh_token')
        if refresh_token is None:
            return Response({'detail': 'Refresh token not provided'}, status=status.HTTP_401_UNAUTHORIZED)

        try:
            refresh = RefreshToken(refresh_token)
            access_token = str(refresh.access_token)

            response = Response({
                'detail': 'Access token refreshed successfully!',
                'access': access_token
            })

            response.set_cookie(key='access_token', value=access_token, httponly=True, path='/', samesite='None', secure=True)

            return response
        except Exception:
            return Response({'detail': 'Invalid refresh token'}, status=status.HTTP_401_UNAUTHORIZED)
        
class LogoutView(APIView):
    """API view to logout user by clearing JWT tokens from cookies."""
    
    def post(self, request):
        response = Response()
        response.delete_cookie('access_token', path='/', samesite='None')
        response.delete_cookie('refresh_token', path='/', samesite='None')
        response.data = {
            'detail': 'Log-Out successfully! All Tokens will be deleted. Refresh token is now invalid.'
        }
        return response
        
class LoginView(TokenObtainPairView):
    """API view for user login with JWT token generation."""
    
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs): 
            request.data['username'] = request.data.get('email')          
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            user = getattr(serializer, 'user', serializer.validated_data.get('user'))
            tokens = get_tokens_for_user(user)

            response = Response({
                'detail': 'Login successfuly!',
                "user": {
                    "id": user.id,
                    "username": user.username,
                }
            })

            cookie_params = dict(httponly=True, path='/', samesite='None', secure=True)
            response.set_cookie(key='access_token', value=tokens['access'], **cookie_params)
            response.set_cookie(key='refresh_token', value=tokens['refresh'], **cookie_params)
        
            if serializer.errors:
                response = Response(serializer.errors, status=status.HTTP_404_NOT_FOUND)
 
            return response

        
def get_tokens_for_user(user):
    """
    Generate JWT access and refresh tokens for a user.
    
    Args:
        user: Django User instance
        
    Returns:
        dict: Dictionary with 'refresh' and 'access' token strings
    """
    refresh = RefreshToken.for_user(user)
        
    return {
        'refresh': str(refresh),
        'access': str(refresh.access_token),
    }

class ActivateAccountView(APIView):
    """API view to activate user account via activation link."""
    
    permission_classes = [AllowAny]

    def get(self, request, activation_key):
        cached_data = cache.get(activation_key)
        if not cached_data:
            return Response({'detail': 'Activation link is invalid or has expired.'}, status=status.HTTP_400_BAD_REQUEST)

        data = json.loads(cached_data)
        try:
            user = User.objects.get(pk=data['uid'])
            user.is_active = True
            user.save()
            cache.delete(activation_key)
            return Response({'detail': 'Account activated successfully!'}, status=status.HTTP_200_OK)
        except User.DoesNotExist:
            return Response({'detail': 'User does not exist.'}, status=status.HTTP_400_BAD_REQUEST)