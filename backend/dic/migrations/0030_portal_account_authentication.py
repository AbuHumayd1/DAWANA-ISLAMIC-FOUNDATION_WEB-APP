"""Source only. Apply this explicit target only after isolated approval."""
import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [('dic', '0029_authorized_tutor_registration'), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    run_before = [('dic', '0027_feedback_welfare')]
    operations = [
        migrations.CreateModel(name='PortalAccount', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('username_key', models.CharField(max_length=40, unique=True)),
            ('login_email', models.EmailField(max_length=254, null=True, blank=True, unique=True)),
            ('contact_channel', models.CharField(max_length=10)),
            ('contact_digest', models.CharField(max_length=64)),
            ('credential_version', models.PositiveIntegerField(default=1)),
            ('created_at', models.DateTimeField(default=django.utils.timezone.now, editable=False)),
            ('user', models.OneToOneField(to=settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.PROTECT)),
        ], options={'default_permissions': (), 'constraints': [models.UniqueConstraint(fields=('contact_channel', 'contact_digest'), name='dic_portal_account_contact')]}),
        migrations.CreateModel(name='PortalAccountBooking', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('verified_at', models.DateTimeField(default=django.utils.timezone.now, editable=False)),
            ('revoked_at', models.DateTimeField(null=True)),
            ('account', models.ForeignKey(to='dic.portalaccount', related_name='bookings', on_delete=django.db.models.deletion.PROTECT)),
            ('order', models.OneToOneField(to='dic.registrationorder', on_delete=django.db.models.deletion.PROTECT)),
        ], options={'default_permissions': ()}),
        migrations.CreateModel(name='PortalAccountSession', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('credential_version', models.PositiveIntegerField()),
            ('method', models.CharField(max_length=10, choices=[('password', 'Password'), ('google', 'Google')])),
            ('account', models.ForeignKey(to='dic.portalaccount', on_delete=django.db.models.deletion.PROTECT)),
            ('grant', models.OneToOneField(to='dic.participantportalgrant', on_delete=django.db.models.deletion.PROTECT)),
        ], options={'default_permissions': ()}),
        migrations.CreateModel(name='PortalGoogleLink', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('subject', models.CharField(max_length=255, unique=True)),
            ('linked_at', models.DateTimeField(default=django.utils.timezone.now, editable=False)),
            ('revoked_at', models.DateTimeField(null=True)),
            ('account', models.OneToOneField(to='dic.portalaccount', on_delete=django.db.models.deletion.PROTECT)),
        ], options={'default_permissions': ()}),
        migrations.CreateModel(name='PortalOAuthAttempt', fields=[
            ('id', models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
            ('state_digest', models.CharField(max_length=64, unique=True)),
            ('nonce_digest', models.CharField(max_length=64)),
            ('browser_digest', models.CharField(max_length=64)),
            ('encrypted_verifier', models.TextField()),
            ('intent', models.CharField(max_length=5, choices=[('login', 'Login'), ('link', 'Link')])),
            ('expires_at', models.DateTimeField()), ('consumed_at', models.DateTimeField(null=True)),
            ('remember_device', models.BooleanField(default=False)),
            ('grant', models.ForeignKey(to='dic.participantportalgrant', null=True, on_delete=django.db.models.deletion.PROTECT)),
        ], options={'default_permissions': ()}),
    ]
