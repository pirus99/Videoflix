import json
import secrets

import pytest
from django.core.cache import cache
from django.contrib.auth.models import User
from django.conf import settings
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

"""!!! You need to configure a local PostgreSQL database and Redis instance with local reachable ports for tests to run successfully !!! """

@pytest.fixture
def client():
	return APIClient()


@pytest.mark.django_db
def test_register_creates_inactive_user(client):
	payload = {
		"email": "user@example.com",
		"password": "securepassword",
		"confirmed_password": "securepassword",
	}

	resp = client.post('/api/register/', payload, format='json')
	assert resp.status_code in (200, 201)

	user = User.objects.filter(email=payload['email']).first()
	assert user is not None
	assert user.is_active is False


@pytest.mark.django_db
def test_activate_valid_key_activates_user(client):
	user = User.objects.create_user(username='a@b.com', email='a@b.com', password='pw')
	user.is_active = False
	user.save()

	activation_key = secrets.token_hex(16)
	cache.set(activation_key, json.dumps({'uid': user.pk, 'token': 'tok'}), 900)

	resp = client.get(f'/api/activate/{activation_key}/')
	assert resp.status_code == 200

	user.refresh_from_db()
	assert user.is_active is True


@pytest.mark.django_db
def test_activate_invalid_key_returns_400(client):
	resp = client.get('/api/activate/doesnotexist/')
	assert resp.status_code == 400


@pytest.mark.django_db
def test_login_sets_tokens_and_returns_user(client):
	email = 'login@example.com'
	password = 'secret123'
	user = User.objects.create_user(username=email, email=email, password=password, is_active=True)

	resp = client.post('/api/login/', {'email': email, 'password': password}, format='json')
	assert resp.status_code == 200
	assert 'detail' in resp.data
	assert 'user' in resp.data and resp.data['user']['username'] == email

	# cookies should be set for access_token and refresh_token
	set_cookie_headers = resp.cookies
	assert 'access_token' in set_cookie_headers
	assert 'refresh_token' in set_cookie_headers


@pytest.mark.django_db
def test_logout_clears_tokens(client):
	resp = client.post('/api/logout/')
	assert resp.status_code == 200
	assert 'detail' in resp.data


@pytest.mark.django_db
def test_token_refresh_with_valid_refresh_cookie_sets_access_cookie(client):
	user = User.objects.create_user(username='r@r.com', email='r@r.com', password='p')
	refresh = RefreshToken.for_user(user)

	# attach refresh token as cookie for the request
	client.cookies['refresh_token'] = str(refresh)

	resp = client.post('/api/token/refresh/')
	assert resp.status_code == 200
	assert 'access' in resp.data or 'detail' in resp.data
	# response should set an access_token cookie
	assert 'access_token' in resp.cookies


@pytest.mark.django_db
def test_token_refresh_without_cookie_returns_401(client):
	resp = client.post('/api/token/refresh/')
	assert resp.status_code in (401, 400)


@pytest.mark.django_db
def test_password_reset_request_existing_user_returns_200(client):
	email = 'pwreset@example.com'
	User.objects.create_user(username=email, email=email, password='pw')

	resp = client.post('/api/password-reset/', {'email': email}, format='json')
	assert resp.status_code == 200
	assert 'detail' in resp.data


@pytest.mark.django_db
def test_password_confirm_changes_password(client):
	email = 'confirm@example.com'
	user = User.objects.create_user(username=email, email=email, password='oldpw')

	token = secrets.token_urlsafe(16)
	cache.set(f'password_reset_{token}', user.pk, 900)

	new_pw = 'newsecurepassword'
	resp = client.post(f'/api/password_confirm/{token}/', {'new_password': new_pw, 'confirm_password': new_pw}, format='json')
	assert resp.status_code == 200

	user.refresh_from_db()
	assert user.check_password(new_pw) is True


@pytest.mark.django_db
def test_password_confirm_invalid_token_returns_400(client):
	resp = client.post('/api/password_confirm/invalidtoken/', {'new_password': 'a', 'confirm_password': 'a'}, format='json')
	assert resp.status_code == 400


