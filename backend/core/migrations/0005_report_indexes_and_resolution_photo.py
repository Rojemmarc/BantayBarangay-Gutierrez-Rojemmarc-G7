from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0004_seed_default_departments'),
    ]

    operations = [
        migrations.AddField(
            model_name='reportphoto',
            name='is_resolution_proof',
            field=models.BooleanField(default=False),
        ),
        migrations.AddIndex(
            model_name='report',
            index=models.Index(fields=['assigned_to', 'status'], name='core_rep_assigned_status_idx'),
        ),
        migrations.AddIndex(
            model_name='report',
            index=models.Index(fields=['barangay', 'is_emergency', 'status'], name='core_rep_brgy_em_status_idx'),
        ),
    ]
