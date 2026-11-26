import tempfile
from django.core.management import call_command
from django.test import TestCase, override_settings
from core.models import Barangay, Department, Report, User

TMP = tempfile.mkdtemp()


@override_settings(
    MEDIA_ROOT=TMP,
    SESSION_COOKIE_SECURE=False,
    CSRF_COOKIE_SECURE=False,
    SECURE_SSL_REDIRECT=False,
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
)
class SeedAndProfileTests(TestCase):
    def test_default_departments_seeded_for_tisa(self):
        tisa = Barangay.objects.get(name='Tisa', city_municipality='Cebu City')
        names = set(Department.objects.filter(barangay=tisa).values_list('name', flat=True))
        assert {'Maintenance', 'Sanitation', 'Peace and Order', 'Health'}.issubset(names)

    def test_seed_demo_creates_all_roles_and_sample_reports_idempotently(self):
        call_command('seed', '--demo')
        expected = {
            'resident@demo.ph': 'Resident',
            'volunteer@demo.ph': 'Volunteer',
            'official@demo.ph': 'Official',
            'staff@demo.ph': 'Staff',
            'lgu@demo.ph': 'LGU',
        }
        for email, role in expected.items():
            user = User.objects.get(email=email)
            assert user.role == role
            assert user.check_password('DemoPass#2026x')
        assert Report.objects.count() == 3

        # Calling seed --demo a second time must be idempotent
        call_command('seed', '--demo')
        assert Report.objects.count() == 3

    def test_profile_displays_role_and_barangay(self):
        call_command('seed', '--demo')
        for email, label in [
            ('resident@demo.ph', b'Resident'),
            ('official@demo.ph', b'Official'),
            ('staff@demo.ph', b'Staff'),
            ('volunteer@demo.ph', b'Volunteer'),
            ('lgu@demo.ph', b'LGU'),
        ]:
            user = User.objects.get(email=email)
            self.client.force_login(user)
            response = self.client.get('/profile/')
            assert response.status_code == 200
            assert label in response.content
            assert b'Tisa, Cebu City' in response.content
