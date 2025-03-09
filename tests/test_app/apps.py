import os

from django.apps import AppConfig


class TestAppConfig(AppConfig):
    name = 'tests.test_app'
    verbose_name = 'Test App'
    path = os.path.dirname(os.path.abspath(__file__))
