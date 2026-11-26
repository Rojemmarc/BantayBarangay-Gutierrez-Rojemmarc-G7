from django.db import migrations


DEFAULT_DEPARTMENTS = (
    ('Maintenance', 'Roads, streetlights, drainage, and public infrastructure repairs.'),
    ('Sanitation', 'Waste collection, cleanup drives, and public hygiene concerns.'),
    ('Peace and Order', 'Barangay tanod patrol, safety, and noise concerns.'),
    ('Health', 'Barangay health station and emergency medical coordination.'),
)


def seed_default_departments(apps, schema_editor):
    Barangay = apps.get_model('core', 'Barangay')
    Department = apps.get_model('core', 'Department')
    for barangay in Barangay.objects.all():
        for name, description in DEFAULT_DEPARTMENTS:
            Department.objects.get_or_create(
                barangay=barangay,
                name=name,
                defaults={'description': description},
            )


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0003_seed_report_categories'),
    ]

    operations = [
        migrations.RunPython(seed_default_departments, migrations.RunPython.noop),
    ]
