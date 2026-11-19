from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('dic', '0045_studio_hosted_video'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(
            name='AftercampAssessment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('topic', models.CharField(max_length=20, choices=[
                    ('programme', 'Programme delivery'),
                    ('teaching', 'Teaching and Qur’an learning'),
                    ('catering', 'Catering and food service'),
                    ('competitions', 'Competitions and house championships'),
                    ('operations', 'Camp operations and logistics'),
                    ('achievements', 'Achievements and positive outcomes'),
                    ('challenges', 'Challenges and lessons learned'),
                    ('recommendations', 'Recommendations for the next edition'),
                ])),
                ('findings', models.TextField(blank=True, max_length=10000)),
                ('challenges', models.TextField(blank=True, max_length=6000)),
                ('recommendations', models.TextField(blank=True, max_length=6000)),
                ('evidence_reference', models.TextField(blank=True, max_length=1500)),
                ('status', models.CharField(choices=[('draft','Draft'),('approved','Approved')], default='draft',max_length=12)),
                ('approved_at', models.DateTimeField(blank=True,null=True)),
                ('updated_at',models.DateTimeField(auto_now=True)),
                ('edition', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,related_name='aftercamp_assessments',to='dic.campedition')),
                ('authored_by',models.ForeignKey(on_delete=django.db.models.deletion.SET_NULL,null=True,related_name='+',to=settings.AUTH_USER_MODEL)),
                ('approved_by',models.ForeignKey(on_delete=django.db.models.deletion.SET_NULL,null=True,blank=True,related_name='+',to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering':['topic']},
        ),
        migrations.AddConstraint(
            model_name='aftercampassessment',
            constraint=models.UniqueConstraint(fields=('edition','topic'),name='dic_aftercamp_topic_edition_unique'),
        ),
    ]
