"""Additive username uniqueness and audited recovery authority; no identity activation."""
from django.conf import settings
from django.db import migrations, models
from django.db.models.functions import Lower
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('dic', '0039_camper_fulfillment'), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        # Fail on pre-existing case collisions rather than rename or merge identities.
        migrations.AddConstraint(model_name='portalaccount',
            constraint=models.UniqueConstraint(Lower('username_key'), name='dic_portal_username_ci')),
        migrations.CreateModel(name='PortalCredentialTransition', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('credential_version', models.PositiveIntegerField(null=True)),
            ('password_digest', models.CharField(max_length=64, blank=True, default='')),
            ('token_digest', models.CharField(max_length=64, unique=True)),
            ('expires_at', models.DateTimeField()),
            ('consumed_at', models.DateTimeField(null=True)),
            ('account', models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, to='dic.portalaccount')),
            ('order', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='dic.registrationorder')),
            ('issued_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
        ], options={'default_permissions': ()}),
    ]
