from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [('dic', '0038_registration_guardian_declaration'), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [migrations.CreateModel(
        name='CamperFulfillmentJob',
        fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('state', models.CharField(choices=[('pending','Pending'),('processing','Processing'),
                ('completed','Completed'),('held','Staff review needed'),('failed','Processing failed')], default='pending', max_length=12)),
            ('attempts', models.PositiveIntegerField(default=0)),
            ('retry_at', models.DateTimeField(blank=True, null=True)),
            ('reason_code', models.CharField(blank=True, max_length=48)),
            ('created_at', models.DateTimeField(default=django.utils.timezone.now, editable=False)),
            ('updated_at', models.DateTimeField(auto_now=True)),
            ('order', models.OneToOneField(on_delete=django.db.models.deletion.PROTECT,
                related_name='fulfillment_job', to='dic.registrationorder')),
            ('processed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                related_name='+', to=settings.AUTH_USER_MODEL)),
        ],
        options={'default_permissions': (),
            'indexes': [models.Index(fields=['state','created_at'], name='dic_fulfillment_queue_idx')],
            'constraints': [models.CheckConstraint(condition=models.Q(state__in=[
                'pending','processing','completed','held','failed']), name='dic_fulfillment_state_valid')]},
    )]
