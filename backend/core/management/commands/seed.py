import io
from decimal import Decimal
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.utils import timezone
from PIL import Image, ImageDraw
from core.models import (
    Announcement,
    Barangay,
    Category,
    Comment,
    Department,
    Notification,
    Report,
    ReportPhoto,
    StatusHistory,
    User,
)


def _demo_image(filename, bg_color, label):
    buf = io.BytesIO()
    img = Image.new('RGB', (640, 400), bg_color)
    draw = ImageDraw.Draw(img)
    draw.rectangle([(24, 24), (616, 376)], outline=(255, 255, 255), width=4)
    draw.text((48, 180), label, fill=(255, 255, 255))
    img.save(buf, format='PNG')
    return ContentFile(buf.getvalue(), name=filename)


class Command(BaseCommand):
    help = 'Create reference data. --demo adds one test account per role and sample records (never in production).'

    def add_arguments(self, parser):
        parser.add_argument('--demo', action='store_true')
        parser.add_argument('--barangay', default='Tisa')
        parser.add_argument('--city', default='Cebu City')
        parser.add_argument('--province', default='Cebu')

    def handle(self, *args, **options):
        barangay, _ = Barangay.objects.get_or_create(
            name=options['barangay'],
            city_municipality=options['city'],
            defaults={'province': options['province']},
        )
        for name in ['Infrastructure', 'Safety', 'Sanitation', 'Flooding', 'Noise', 'Emergency']:
            Category.objects.get_or_create(name=name, defaults={'is_emergency': name == 'Emergency'})
        for name in ['Maintenance', 'Sanitation', 'Peace and Order', 'Health']:
            Department.objects.get_or_create(barangay=barangay, name=name)

        if options['demo']:
            demo_users = [
                ('resident@demo.ph', 'Maria Santos', 'Resident', '09171234501'),
                ('volunteer@demo.ph', 'Carlo Reyes', 'Volunteer', '09171234502'),
                ('official@demo.ph', 'Juan Dela Cruz', 'Official', '09171234503'),
                ('staff@demo.ph', 'Ana Villanueva', 'Staff', '09171234504'),
                ('lgu@demo.ph', 'LGU Cebu Analyst', 'LGU', '09171234505'),
            ]
            users = {}
            for email, full_name, role, phone in demo_users:
                user, created = User.objects.get_or_create(
                    email=email,
                    defaults={
                        'full_name': full_name,
                        'role': role,
                        'barangay': barangay,
                        'contact_number': phone,
                        'consent_at': timezone.now(),
                    },
                )
                if created:
                    user.set_password('DemoPass#2026x')
                    user.save(update_fields=['password'])
                users[role] = user

            if not Report.objects.filter(reporter=users['Resident']).exists():
                cat_infra = Category.objects.get(name='Infrastructure')
                cat_flood = Category.objects.get(name='Flooding')
                cat_sanit = Category.objects.get(name='Sanitation')
                dept_maint = Department.objects.get(barangay=barangay, name='Maintenance')
                dept_sanit = Department.objects.get(barangay=barangay, name='Sanitation')

                r1 = Report.objects.create(
                    reporter=users['Resident'],
                    barangay=barangay,
                    category=cat_infra,
                    title='Broken streetlight along Katipunan Extension',
                    description='The streetlight near the pedestrian crossing has been out for three nights, making the road dark for commuters.',
                    latitude=Decimal('10.301820'),
                    longitude=Decimal('123.868940'),
                    location_note='Near Tisa Public Market entrance',
                    status='Pending',
                    priority='Normal',
                )
                img1 = _demo_image('streetlight.png', (30, 58, 95), 'BantayBarangay Demo Evidence: Streetlight')
                ReportPhoto.objects.create(report=r1, image=img1, file_type='PNG', file_size_kb=max(1, img1.size // 1024))
                StatusHistory.objects.create(report=r1, changed_by=users['Resident'], old_status=None, new_status='Pending')

                r2 = Report.objects.create(
                    reporter=users['Resident'],
                    barangay=barangay,
                    category=cat_flood,
                    department=dept_maint,
                    assigned_to=users['Staff'],
                    title='Clogged drainage canal causing ankle-deep water',
                    description='Storm drain along Sitio Riva Ridge is blocked with debris and overflows whenever it rains heavily.',
                    latitude=Decimal('10.304110'),
                    longitude=Decimal('123.865220'),
                    location_note='Sitio Riva Ridge corner road',
                    status='Assigned',
                    priority='Normal',
                )
                img2 = _demo_image('drainage.png', (37, 99, 235), 'BantayBarangay Demo Evidence: Drainage')
                ReportPhoto.objects.create(report=r2, image=img2, file_type='PNG', file_size_kb=max(1, img2.size // 1024))
                StatusHistory.objects.create(report=r2, changed_by=users['Resident'], old_status=None, new_status='Pending')
                StatusHistory.objects.create(report=r2, changed_by=users['Official'], old_status='Pending', new_status='Assigned')
                Notification.objects.create(
                    user=users['Staff'],
                    report=r2,
                    message=f'You were assigned report "{r2.title}".',
                )

                r3 = Report.objects.create(
                    reporter=users['Resident'],
                    barangay=barangay,
                    category=cat_sanit,
                    department=dept_sanit,
                    assigned_to=users['Staff'],
                    title='Uncollected garbage bags beside barangay chapel',
                    description='Several uncollected waste sacks have piled up beside the side alley after the weekend schedule was missed.',
                    latitude=Decimal('10.299540'),
                    longitude=Decimal('123.871310'),
                    location_note='Beside San Lorenzo Chapel alley',
                    status='Resolved',
                    priority='Normal',
                    quality_rating=5,
                    resolved_at=timezone.now(),
                )
                img3 = _demo_image('sanitation.png', (22, 163, 74), 'BantayBarangay Demo Evidence: Sanitation')
                ReportPhoto.objects.create(report=r3, image=img3, file_type='PNG', file_size_kb=max(1, img3.size // 1024))
                StatusHistory.objects.create(report=r3, changed_by=users['Resident'], old_status=None, new_status='Pending')
                StatusHistory.objects.create(report=r3, changed_by=users['Official'], old_status='Pending', new_status='Assigned')
                StatusHistory.objects.create(report=r3, changed_by=users['Staff'], old_status='Assigned', new_status='In Progress')
                StatusHistory.objects.create(report=r3, changed_by=users['Staff'], old_status='In Progress', new_status='Resolved')
                Comment.objects.create(
                    report=r3,
                    author=users['Staff'],
                    comment_text='Sanitation crew cleared the alley and disinfected the pickup point.',
                    is_official=True,
                )
                Notification.objects.create(
                    user=users['Resident'],
                    report=r3,
                    message=f'Your report "{r3.title}" is now Resolved.',
                )

            if not Announcement.objects.filter(barangay=barangay).exists():
                Announcement.objects.create(
                    barangay=barangay,
                    posted_by=users['Official'],
                    title='Weekly Drainage Clearing & Clean-Up Drive',
                    body='Barangay maintenance and sanitation teams will clear main drainage canals this Saturday from 7:00 AM to 11:00 AM.',
                    type='Advisory',
                )

        self.stdout.write(self.style.SUCCESS('Seeded.'))
