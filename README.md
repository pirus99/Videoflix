# Videoflix

A Netflix-style video streaming platform built with Django. Videoflix provides adaptive bitrate video streaming via HLS, JWT-based authentication with email verification, and an admin interface for managing video content with IMDb metadata integration.

## Features

- **Adaptive Bitrate Streaming** — HLS (M3U8) delivery with on-demand FFmpeg transcoding across multiple resolutions (360p–2160p) and codecs (H.264, H.265)
- **Video Previews** — Auto-generated 2-minute looping previews for each video
- **JWT Authentication** — Secure login with access/refresh tokens, email-based account activation, and password reset
- **IMDb Integration** — Auto-fetch video metadata, posters, and thumbnails by IMDb ID
- **Background Processing** — Async transcoding, email sending, and cleanup via Redis Queue (RQ) workers
- **Django Admin** — Custom admin interface with upload progress tracking and bulk actions

## Tech Stack

| Layer | Technology |
|---|---|
| Framework | Django 6.0, Django REST Framework |
| Auth | SimpleJWT (JSON Web Tokens) |
| Database | PostgreSQL |
| Cache / Queue | Redis, django-rq |
| Video Processing | FFmpeg |
| Server | Gunicorn |
| Static Files | WhiteNoise |
| Containerization | Docker, Docker Compose |

## Project Structure

```
├── core/                   # Django project configuration
│   ├── settings.py         # Main settings
│   ├── test_settings.py    # Test-specific settings
│   └── urls.py             # Root URL routing
├── jwt_auth_app/           # Authentication app
│   ├── api/
│   │   ├── views.py        # Register, login, logout, token refresh, password reset
│   │   ├── serializers.py  # User serializers
│   │   ├── authentication.py # Custom JWT backend
│   │   └── urls.py         # Auth routes
│   └── templates/          # Email templates (activation, password reset)
├── video_app/              # Video streaming app
│   ├── models.py           # Video & Preview models
│   ├── api/
│   │   ├── views.py        # HLS playlist & segment delivery
│   │   ├── transcode.py    # FFmpeg transcoding logic
│   │   ├── workers.py      # RQ background job definitions
│   │   └── urls.py         # Video routes
│   └── management/commands/ # Custom management commands
├── docker-compose.yml      # PostgreSQL, Redis, Django services
├── backend.Dockerfile      # Python 3.12 Alpine image with FFmpeg
├── backend.entrypoint.sh   # Container startup script
├── requirements.txt        # Python dependencies
├── .env.template           # Environment variable template
└── pytest.ini              # Test configuration
```

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/)
- An SMTP-capable email account (e.g. Gmail with an [App Password](https://support.google.com/accounts/answer/185833))

For local development without Docker you will also need:

- Python 3.12+
- PostgreSQL
- Redis
- FFmpeg

## Getting Started

### 1. Clone the repository

```bash
git clone https://github.com/pirus99/Videoflix.git
cd Videoflix
```

### 2. Configure environment variables

```bash
cp .env.template .env
```

Open `.env` and update the values — at minimum set:

| Variable | Description |
|---|---|
| `SECRET_KEY` | A unique, unpredictable secret for Django |
| `DB_NAME` / `DB_USER` / `DB_PASSWORD` | PostgreSQL credentials |
| `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD` | SMTP credentials for sending emails |
| `DJANGO_SUPERUSER_USERNAME` / `DJANGO_SUPERUSER_PASSWORD` | Initial admin account |
| `FRONTEND_URL` | URL of the frontend app (default `http://localhost:5500/`) |

See `.env.template` for all available options.

### 3. Start with Docker Compose

```bash
docker compose up --build
```

This will:

1. Start **PostgreSQL** and **Redis** containers
2. Build the Django backend image (Python 3.12 Alpine + FFmpeg)
3. Run database migrations and collect static files
4. Create the superuser from your environment variables
5. Launch **5 RQ workers** for background jobs
6. Start **Gunicorn** on port `8000`

The API will be available at `http://localhost:8000/`.

### 4. Access the admin panel

Navigate to `http://localhost:8000/admin/` and log in with the superuser credentials from your `.env` file.

## Local Development (without Docker)

```bash
# Create and activate a virtual environment
python -m venv venv
source venv/bin/activate  # Linux/macOS
# venv\Scripts\activate   # Windows

# Install dependencies
pip install -r requirements.txt

# Make sure PostgreSQL and Redis are running, then:
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

In a separate terminal, start the background workers:

```bash
python manage.py rqworker high default low
```

> **Note:** When running locally, update `DB_HOST` and `REDIS_HOST` in your `.env` to point to `localhost` instead of the Docker service names (`db` / `redis`).

## API Endpoints

### Authentication (`jwt_auth_app`)

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/register/` | Register a new user (sends activation email) |
| GET | `/api/activate/<token>/` | Activate account via email link |
| POST | `/api/login/` | Log in and receive JWT tokens |
| POST | `/api/logout/` | Log out |
| POST | `/api/token/refresh/` | Refresh the access token |
| POST | `/api/password_reset/` | Request a password reset email |
| POST | `/api/password_confirm/<token>/` | Confirm password reset |

### Video Streaming (`video_app`)

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/video/` | List all videos with metadata |
| GET | `/api/video/<id>/<resolution>/index.m3u8` | HLS playlist for a video at the given resolution |
| GET | `/api/video/<id>/<resolution>/<segment>` | Video segment file |
| GET | `/api/preview/<id>/index.m3u8` | HLS playlist for a video preview |
| GET | `/api/preview/<id>/<segment>` | Preview segment file |

### Admin & Monitoring

| URL | Description |
|---|---|
| `/admin/` | Django admin interface |
| `/django-rq/` | RQ worker dashboard |

## Running Tests

Tests use [pytest](https://docs.pytest.org/) with the settings in `core/test_settings.py`:

```bash
pytest
```

> **Note:** The test suite requires accessible PostgreSQL and Redis instances. If running with Docker, uncomment the port mappings for `db` and `redis` in `docker-compose.yml` and update your test settings to use `localhost`.

## License

This project does not currently specify a license. Contact the repository owner for usage terms.
