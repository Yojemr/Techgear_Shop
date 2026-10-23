from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connections
from django.db.migrations.loader import MigrationLoader
from django.test import SimpleTestCase
from django_mongodb_backend.fields import ObjectIdAutoField


class MongoConfigurationTests(SimpleTestCase):
    def test_persistence_uses_mongodb_and_object_ids(self):
        self.assertEqual(settings.DATABASES["default"]["ENGINE"], "django_mongodb_backend")
        self.assertIsInstance(get_user_model()._meta.pk, ObjectIdAutoField)
        self.assertEqual(settings.SESSION_ENGINE, "django.contrib.sessions.backends.db")

    def test_native_migrations_are_replaced_without_accessing_database(self):
        with patch.object(connections["default"], "ensure_connection", side_effect=AssertionError):
            loader = MigrationLoader(None)
        self.assertIn(("auth", "0001_initial"), loader.disk_migrations)
        for label in ("auth", "admin", "contenttypes"):
            migration = loader.disk_migrations[(label, "0001_initial")]
            self.assertTrue(migration.__module__.startswith("mongo_migrations."))
