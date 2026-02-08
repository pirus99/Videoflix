import json, django_rq

from django.core.cache import cache
from django.contrib.auth.models import User

from rest_framework import status
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from .scripts import sendActivationEmail, sendPasswordResetEmail
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
            #sendActivationEmail(saved_account.email) #Call the function directly to send email immediately
            queue = django_rq.get_queue('high', autocommit=True) #Use RQ to send email asynchronously in the background
            queue.enqueue(sendActivationEmail, saved_account.email)
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
        response.status_code = status.HTTP_200_OK
        return response
        
class LoginView(TokenObtainPairView):
    """API view for user login with JWT token generation."""
    
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs): 
            if request.data.get('email'):
                request.data['username'] = request.data.get('email')
            else:
                return Response({'detail': 'Email is required for login.'}, status=status.HTTP_400_BAD_REQUEST)       
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

    def get(self, request, token):
        cached_data = cache.get(token)
        if not cached_data:
            return Response({'detail': 'Activation link is invalid or has expired.'}, status=status.HTTP_400_BAD_REQUEST)

        data = json.loads(cached_data)
        try:
            user = User.objects.get(pk=data['uid'])
            user.is_active = True
            user.save()
            cache.delete(token)
            return Response({'detail': 'Account activated successfully!'}, status=status.HTTP_200_OK)
        except User.DoesNotExist:
            return Response({'detail': 'User does not exist.'}, status=status.HTTP_400_BAD_REQUEST)
        
class PasswordResetRequestView(APIView):
    """API view to obtain password reset token via email."""
    
    permission_classes = [AllowAny]

    def post(self, request):
        email = request.data.get('email')
        if not email:
            return Response({'detail': 'Email is required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            #sendPasswordResetEmail(email) #Call the function directly to send email immediately
            queue = django_rq.get_queue('high', autocommit=True) #Use RQ to send email asynchronously in the background
            queue.enqueue(sendPasswordResetEmail, email)
            return Response({'detail': 'Password reset link sent to email.'}, status=status.HTTP_200_OK)
        except User.DoesNotExist:
            return Response({'detail': 'User with this email does not exist.'}, status=status.HTTP_400_BAD_REQUEST)
        
class PasswordResetConfirmView(APIView):
    """API view to confirm password reset with token and set new password."""
    
    permission_classes = [AllowAny]

    def post(self, request, reset_token):
        cached_user_id = cache.get(f'password_reset_{reset_token}')
        if not cached_user_id:
            return Response({'detail': 'Reset token is invalid or has expired.'}, status=status.HTTP_400_BAD_REQUEST)

        new_password = request.data.get('new_password')
        confirm_password = request.data.get('confirm_password')
        if not new_password or not confirm_password:
            return Response({'detail': 'New password and confirm password are required.'}, status=status.HTTP_400_BAD_REQUEST)

        if new_password != confirm_password:
            return Response({'detail': 'Passwords do not match.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.get(pk=cached_user_id)
            user.set_password(new_password)
            user.save()
            cache.delete(f'password_reset_{reset_token}')
            return Response({'detail': 'Password reset successfully!'}, status=status.HTTP_200_OK)
        except User.DoesNotExist:
            return Response({'detail': 'User does not exist.'}, status=status.HTTP_400_BAD_REQUEST)
        