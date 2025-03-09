import os

# Base directory (assuming settings.py is in the same directory as conftest.py)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Secret key (for testing purposes, can be any string)
SECRET_KEY = 'test-secret-key'

# Debug mode (optional, useful for test output)
DEBUG = True

# Installed apps
INSTALLED_APPS = [
    'django.contrib.contenttypes',
    'django.contrib.auth',
    'tests.test_app.apps.TestAppConfig',  # Reference the AppConfig
]

# Database configuration (in-memory SQLite for testing)
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}

# Middleware (minimal for testing)
MIDDLEWARE = []

# Root URL configuration (empty for testing)
ROOT_URLCONF = []

# Time zone settings (optional, disable to simplify)
USE_TZ = False

# Define the apps module explicitly (optional, for clarity)
TEST_APP_DIR = BASE_DIR
