import uuid

from django.db import models


# Basic model with auto-incrementing integer primary key (default)
class TestModel(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)

    class Meta:
        app_label = 'test_app'

# Model with UUID primary key
class UUIDModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)

    class Meta:
        app_label = 'test_app'

# Model with custom primary key name
class CustomPKModel(models.Model):
    custom_id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100)

    class Meta:
        app_label = 'test_app'

# Model with string primary key
class StringPKModel(models.Model):
    code = models.CharField(max_length=20, primary_key=True)
    name = models.CharField(max_length=100)

    class Meta:
        app_label = 'test_app'

# Model with composite primary key via unique_together. Django still created new ID
# Starting from 5.2, Django introduced composite primary keys.
# pk = models.CompositePrimaryKey("product_id", "order_id")
class CompositePKModel(models.Model):
    first_id = models.IntegerField()
    second_id = models.IntegerField()
    name = models.CharField(max_length=100)

    class Meta:
        app_label = 'test_app'
        unique_together = ('first_id', 'second_id')
