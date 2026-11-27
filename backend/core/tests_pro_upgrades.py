import datetime
import io
import os
import tempfile
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from PIL import Image
from core.models import Announcement, Barangay, Category, Comment, Department, Notification, Report, ReportPhoto, User

TMP = tempfile.mkdtemp()


def make_png(name='photo.png'):
    buf = io.BytesIO()
    Image.new('RGB', (32, 32), (30, 58, 95)).save(buf, format='PNG')
    return SimpleUploadedFile(name, buf.getvalue(), content_type='image/png')


def make_jpeg_with_exif(name='exif.jpg'):
    buf = io.BytesIO()
    img = Image.new('RGB', (40, 40), (244, 168, 37))
    exif = img.getexif()
    exif[271] = 'SecretCameraBrand'
    exif[272] = 'PrivateModelX'
    img.save(buf, format='JPEG', exif=exif.tobytes())
    return SimpleUploadedFile(name, buf.getvalue(), content_type='image/jpeg')


@override_settings(
    MEDIA_ROOT=TMP,
    SESSION_COOKIE_SECURE=False,
    CSRF_COOKIE_SECURE=False,
    SECURE_SSL_REDIRECT=False,
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
)
class ProUpgradesTest(TestCase):
    def setUp(self):
        cache.clear()
        self.b = Barangay.objects.create(name='Tisa Pro', city_municipality='Cebu City', province='Cebu')
        for name in ['Infrastructure', 'Safety', 'Sanitation', 'Flooding', 'Noise', 'Emergency']:
            Category.objects.get_or_create(name=name, defaults={'is_emergency': name == 'Emergency'})
        self.d_maint = Department.objects.create(barangay=self.b, name='Maintenance')
        self.d_sanit = Department.objects.create(barangay=self.b, name='Sanitation')
        pw = 'Str0ng#Pass1'
        self.res = User.objects.create_user('res@pro.ph', pw, full_name='Res Pro', barangay=self.b, role='Resident')
        self.vol = User.objects.create_user('vol@pro.ph', pw, full_name='Vol Pro', barangay=self.b, role='Volunteer')
        self.off = User.objects.create_user('off@pro.ph', pw, full_name='Off Pro', barangay=self.b, role='Official')
        self.staff1 = User.objects.create_user('staff1@pro.ph', pw, full_name='Staff One', barangay=self.b, role='Staff')
        self.staff2 = User.objects.create_user('staff2@pro.ph', pw, full_name='Staff Two', barangay=self.b, role='Staff')
        self.lgu = User.objects.create_user('lgu@pro.ph', pw, full_name='LGU Pro', barangay=self.b, role='LGU')
        self.admin = User.objects.create_superuser('admin@pro.ph', pw, full_name='Super Admin')

    def submit_report(self, category='Flooding', title='Street drain issue', photo=None):
        return self.client.post(
            '/app/new/',
            {
                'category': Category.objects.get(name=category).pk,
                'title': title,
                'description': 'Detailed description exceeding twenty characters for testing.',
                'latitude': '10.302500',
                'longitude': '123.867100',
                'location_note': 'Corner Main St',
                'photos': photo or make_png(),
            },
        )

    def test_exif_metadata_stripped_from_uploaded_jpeg(self):
        self.client.force_login(self.res)
        resp = self.submit_report(photo=make_jpeg_with_exif())
        assert resp.status_code == 302
        rp = ReportPhoto.objects.latest('id')
        with Image.open(rp.image.path) as saved:
            assert len(saved.getexif()) == 0

    def test_missing_photo_file_returns_404_not_500(self):
        self.client.force_login(self.res)
        self.submit_report()
        rp = ReportPhoto.objects.latest('id')
        os.remove(rp.image.path)
        assert self.client.get(f'/photos/{rp.pk}/').status_code == 404

    def test_official_receives_emergency_alert_and_can_access_alerts_page(self):
        self.client.force_login(self.res)
        resp = self.submit_report(category='Emergency', title='Fire near public market')
        assert resp.status_code == 302
        assert self.off.notifications.filter(message__contains='EMERGENCY').exists()
        self.client.force_login(self.off)
        alerts_page = self.client.get('/app/alerts/')
        assert alerts_page.status_code == 200 and b'EMERGENCY' in alerts_page.content
        self.client.force_login(self.lgu)
        assert self.client.get('/app/alerts/').status_code == 403

    def test_official_reassign_and_resolution_proof_photo(self):
        self.client.force_login(self.res)
        pk = int(self.submit_report().url.strip('/').split('/')[-1])

        self.client.force_login(self.off)
        self.client.post(
            f'/reports/{pk}/transition/',
            {'status': 'Assigned', 'department': self.d_maint.pk, 'assigned_to': self.staff1.pk},
        )
        # Reassign to staff2 & Sanitation
        reassign = self.client.post(
            f'/reports/{pk}/reassign/',
            {'department': self.d_sanit.pk, 'assigned_to': self.staff2.pk, 'note': 'Routing to sanitation team'},
            follow=True,
        )
        assert reassign.status_code == 200 and b'Reassigned to Staff Two' in reassign.content
        rep = Report.objects.get(pk=pk)
        assert rep.assigned_to == self.staff2 and rep.department == self.d_sanit
        assert self.staff2.notifications.filter(report_id=pk, message__contains='reassigned').exists()

        # Staff2 progresses and resolves with optional resolution proof photo
        self.client.force_login(self.staff2)
        self.client.post(f'/reports/{pk}/transition/', {'status': 'In Progress'})
        resolved = self.client.post(
            f'/reports/{pk}/transition/',
            {'status': 'Resolved', 'comment': 'Cleared and cleaned the area', 'resolution_photos': make_png('after.png')},
            follow=True,
        )
        assert resolved.status_code == 200 and b'Resolution proof' in resolved.content
        assert ReportPhoto.objects.filter(report_id=pk, is_resolution_proof=True).count() == 1

        # Resident cannot reassign
        self.client.force_login(self.res)
        assert self.client.post(f'/reports/{pk}/reassign/', {'department': self.d_maint.pk, 'assigned_to': self.staff1.pk}).status_code == 403

    def test_in_app_password_change_keeps_user_logged_in(self):
        self.client.force_login(self.res)
        assert self.client.get('/profile/password/').status_code == 200
        resp = self.client.post(
            '/profile/password/',
            {
                'old_password': 'Str0ng#Pass1',
                'new_password1': 'N3wStr0ng#Pass2',
                'new_password2': 'N3wStr0ng#Pass2',
            },
            follow=True,
        )
        assert resp.status_code == 200 and b'Password updated.' in resp.content
        self.res.refresh_from_db()
        assert self.res.check_password('N3wStr0ng#Pass2')
        assert self.client.get('/profile/').status_code == 200

    def test_bulletin_edit_expiry_and_superuser_guard(self):
        self.client.force_login(self.admin)
        no_brgy = self.client.post('/bulletin/', {'title': 'Test', 'type': 'Advisory', 'body': 'Hello world'})
        assert no_brgy.status_code == 200 and b'Assign your account to a barangay' in no_brgy.content

        self.client.force_login(self.off)
        future_exp = (timezone.now() + datetime.timedelta(days=5)).strftime('%Y-%m-%dT%H:%M')
        self.client.post(
            '/bulletin/',
            {'title': 'Water Interruption', 'type': 'Advisory', 'expires_at': future_exp, 'body': 'Scheduled maintenance.'},
        )
        ann = Announcement.objects.get(title='Water Interruption')
        assert ann.expires_at is not None
        edit = self.client.post(
            f'/bulletin/{ann.pk}/edit/',
            {'title': 'Updated Water Notice', 'type': 'Advisory', 'expires_at': future_exp, 'body': 'Updated schedule notice.'},
            follow=True,
        )
        assert edit.status_code == 200 and b'Updated Water Notice' in edit.content

    def test_csv_exports_role_isolation_and_formula_escaping(self):
        self.client.force_login(self.res)
        self.submit_report(title='=SUM(A1:A2) Drain Issue')
        assert self.client.get('/official/export.csv').status_code == 403
        assert self.client.get('/lgu/export.csv').status_code == 403

        self.client.force_login(self.off)
        off_csv = self.client.get('/official/export.csv')
        assert off_csv.status_code == 200
        assert off_csv['Content-Type'].startswith('text/csv')
        body = off_csv.content.decode('utf-8')
        assert "'=SUM(A1:A2) Drain Issue" in body

        self.client.force_login(self.lgu)
        assert self.client.get('/official/export.csv').status_code == 403
        lgu_csv = self.client.get('/lgu/export.csv')
        assert lgu_csv.status_code == 200
        lgu_body = lgu_csv.content.decode('utf-8')
        assert 'Total Reports' in lgu_body and 'SUM(A1:A2)' not in lgu_body and 'Res Pro' not in lgu_body

    def test_standard_ux_and_accessibility_elements(self):
        self.client.force_login(self.res)
        res_home = self.client.get('/app/').content
        assert b'class="skip-link"' in res_home
        assert b'with-bottom-nav' in res_home
        assert b'manifest.json' in res_home
        assert b'id="confirmModal"' in res_home
        assert b'Only my reports' not in res_home  # Hidden for Residents

        self.client.force_login(self.vol)
        assert b'Only my reports' in self.client.get('/app/').content  # Visible for Volunteers

        # Inline field-level validation with aria-invalid="true"
        bad = self.client.post('/app/new/', {'title': 'A', 'description': 'short', 'latitude': '999', 'longitude': '123.8'})
        assert bad.status_code == 200 and b'aria-invalid="true"' in bad.content

        # Official map overview & LGU visual bars
        self.client.force_login(self.res)
        self.submit_report()
        self.client.force_login(self.off)
        off_home = self.client.get('/official/').content
        assert b'data-overview-map' in off_home and b'Export CSV' in off_home
        self.client.force_login(self.lgu)
        lgu_page = self.client.get('/lgu/').content
        assert b'role="progressbar"' in lgu_page and b'Export CSV' in lgu_page

    def test_public_landing_page_for_guests_and_redirect_for_authenticated(self):
        guest = self.client.get('/')
        assert guest.status_code == 200
        assert b'Report barangay concerns.' in guest.content
        assert b'href="/register/"' in guest.content and b'href="/login/"' in guest.content
        assert b'Res Pro' not in guest.content

        self.client.force_login(self.res)
        assert self.client.get('/').url == '/app/'
        self.client.force_login(self.off)
        assert self.client.get('/').url == '/official/'
        self.client.force_login(self.lgu)
        assert self.client.get('/').url == '/lgu/'


@override_settings(
    MEDIA_ROOT=TMP,
    SESSION_COOKIE_SECURE=False,
    CSRF_COOKIE_SECURE=False,
    SECURE_SSL_REDIRECT=False,
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
)
class PhotoFileCleanupTransactionTest(TransactionTestCase):
    def test_deleting_report_removes_photo_file_from_disk_on_commit(self):
        b = Barangay.objects.create(name='Cleanup Brgy', city_municipality='Cebu City', province='Cebu')
        cat, _ = Category.objects.get_or_create(name='Flooding', defaults={'is_emergency': False})
        res = User.objects.create_user('clean@pro.ph', 'Str0ng#Pass1', full_name='Clean Res', barangay=b)
        self.client.force_login(res)
        resp = self.client.post(
            '/app/new/',
            {
                'category': cat.pk,
                'title': 'File cleanup test',
                'description': 'Testing that deleted reports also remove files from disk.',
                'latitude': '10.302500',
                'longitude': '123.867100',
                'photos': make_png('cleanup.png'),
            },
        )
        assert resp.status_code == 302
        rp = ReportPhoto.objects.latest('id')
        path = rp.image.path
        assert os.path.exists(path)
        del_resp = self.client.post(f'/reports/{rp.report_id}/delete/')
        assert del_resp.status_code == 302
        assert not os.path.exists(path)
