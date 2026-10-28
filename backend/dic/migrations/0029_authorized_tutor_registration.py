"""Prepared only: Phase 2 tutors; never includes deferred feedback/welfare."""
import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('dic', '0028_registration_privacy_measurements'), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    run_before = [('dic', '0027_feedback_welfare')]
    operations = [
        migrations.AddField(model_name='campedition', name='tutor_registration_enabled', field=models.BooleanField(default=False)),
        migrations.AddField(model_name='registrationorder', name='registration_basis', field=models.CharField(max_length=16, default='paid', choices=[('paid', 'Paid registration'), ('tutor', 'Complimentary tutor')])),
        migrations.RemoveConstraint(model_name='registrationorder', name='dic_order_payment_status_valid'),
        migrations.AlterField(model_name='registrationorder', name='payment_status', field=models.CharField(max_length=12, default='pending', choices=[('not_required', 'Not required (authorized tutor)'), ('pending', 'Pending'), ('paid', 'Paid'), ('failed', 'Failed'), ('refunded', 'Refunded')])),
        migrations.AddConstraint(model_name='registrationorder', constraint=models.CheckConstraint(condition=models.Q(payment_status__in=('pending', 'paid', 'failed', 'refunded', 'not_required')), name='dic_order_payment_status_valid')),
        migrations.AddConstraint(model_name='registrationorder', constraint=models.CheckConstraint(condition=(models.Q(registration_basis='paid') & ~models.Q(payment_status='not_required')) | models.Q(registration_basis='tutor', payment_status='not_required', current_price_revision__isnull=True), name='dic_order_registration_basis')),
        migrations.CreateModel(name='TutorRegistrationAuthorization', fields=[
            ('id', models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
            ('intended_name', models.CharField(max_length=200)),
            ('email', models.EmailField(max_length=254, help_text='Authorized email; ownership must be verified before registration.')),
            ('authorized_at', models.DateTimeField(editable=False)),
            ('reason', models.TextField()),
            ('invitation_digest', models.CharField(max_length=64, unique=True, null=True, editable=False)),
            ('issued_at', models.DateTimeField(null=True, editable=False)),
            ('expires_at', models.DateTimeField(null=True, editable=False)),
            ('redeemed_at', models.DateTimeField(null=True, editable=False)),
            ('verified_at', models.DateTimeField(null=True, editable=False)),
            ('revoked_at', models.DateTimeField(null=True, editable=False)),
            ('revocation_reason', models.TextField(blank=True, editable=False)),
            ('edition', models.ForeignKey(to='dic.campedition', on_delete=django.db.models.deletion.PROTECT)),
            ('authorized_by', models.ForeignKey(to=settings.AUTH_USER_MODEL, related_name='+', editable=False, on_delete=django.db.models.deletion.PROTECT)),
            ('revoked_by', models.ForeignKey(to=settings.AUTH_USER_MODEL, related_name='+', null=True, editable=False, on_delete=django.db.models.deletion.PROTECT)),
            ('enrollment', models.OneToOneField(to='dic.campenrollment', null=True, blank=True, editable=False, on_delete=django.db.models.deletion.PROTECT)),
        ], options={'default_permissions': (), 'permissions': [('can_authorize_dic_tutors', 'Can authorize, reissue and revoke DIC tutors')],
            'constraints': [models.UniqueConstraint(fields=('edition', 'email'), condition=models.Q(revoked_at__isnull=True), name='dic_tutor_active_contact')]}),
        migrations.CreateModel(name='TutorVerification', fields=[
            ('id', models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
            ('invitation_digest', models.CharField(max_length=64)),
            ('browser_digest', models.CharField(max_length=64)),
            ('code_digest', models.CharField(max_length=64)),
            ('expires_at', models.DateTimeField()),
            ('attempts', models.PositiveSmallIntegerField(default=0)),
            ('verified_at', models.DateTimeField(null=True)),
            ('capability_digest', models.CharField(max_length=64, blank=True)),
            ('request_fingerprint', models.CharField(max_length=64, blank=True)),
            ('authorization', models.ForeignKey(to='dic.tutorregistrationauthorization', on_delete=django.db.models.deletion.PROTECT)),
        ], options={'default_permissions': ()}),
    ]
