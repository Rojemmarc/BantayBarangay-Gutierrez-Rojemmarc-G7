"""Core domain models and database integrity rules for BantayBarangay."""
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models, transaction
from django.db.models import Q
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.utils import timezone
from rest_framework.exceptions import ValidationError

ROLES = ['Resident', 'Volunteer', 'Official', 'Staff', 'LGU']
STATUSES = ['Pending', 'Assigned', 'In Progress', 'Resolved', 'Rejected']
PRIORITIES = ['Low', 'Normal', 'High', 'Urgent']
ANNOUNCEMENT_TYPES = ['Announcement', 'Advisory', 'Event']
TRANS = {
    'Pending': ['Assigned', 'Rejected'],
    'Assigned': ['In Progress', 'Rejected'],
    'In Progress': ['Resolved'],
}  # BR-13


def make_choices(values):
    return [(value, value) for value in values]


class Barangay(models.Model):
    name = models.CharField(max_length=100)
    city_municipality = models.CharField(max_length=100)
    province = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['name', 'city_municipality'], name='uq_barangay'),
        ]

    def __str__(self):
        return f'{self.name}, {self.city_municipality}'


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('Email required')
        user = self.model(email=self.normalize_email(email).lower(), **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password, **extra_fields):
        extra_fields.update(is_staff=True, is_superuser=True, role='Official')
        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(max_length=255, unique=True)
    full_name = models.CharField(max_length=150)
    barangay = models.ForeignKey(Barangay, on_delete=models.PROTECT, null=True, blank=True)
    contact_number = models.CharField(max_length=20, blank=True)
    role = models.CharField(max_length=20, choices=make_choices(ROLES), default='Resident')
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    consent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = UserManager()
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['full_name']

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(role__in=ROLES), name='ck_user_role'),
            models.CheckConstraint(
                condition=Q(barangay__isnull=False) | Q(is_superuser=True),
                name='ck_user_barangay',
            ),  # BR-03/04
        ]

    @property
    def is_official(self):
        return self.role in ('Official', 'Staff') or self.is_superuser

    @property
    def is_staff_member(self):
        return self.role == 'Staff' and not self.is_superuser

    @property
    def is_lgu(self):
        return self.role == 'LGU' and not self.is_superuser

    @property
    def can_manage_reports(self):
        return self.role == 'Official' or self.is_superuser

    @property
    def is_reporter(self):
        return self.role in ('Resident', 'Volunteer') and not self.is_superuser

    def __str__(self):
        return self.email


class Department(models.Model):
    barangay = models.ForeignKey(Barangay, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    description = models.CharField(max_length=255, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['barangay', 'name'], name='uq_dept'),
        ]

    def __str__(self):
        return self.name


class Category(models.Model):
    name = models.CharField(max_length=50, unique=True)
    is_emergency = models.BooleanField(default=False)

    def __str__(self):
        return self.name


class Report(models.Model):
    reporter = models.ForeignKey(User, on_delete=models.PROTECT, related_name='reports')
    barangay = models.ForeignKey(Barangay, on_delete=models.PROTECT)
    category = models.ForeignKey(Category, on_delete=models.PROTECT)
    department = models.ForeignKey(Department, null=True, blank=True, on_delete=models.SET_NULL)
    assigned_to = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='assigned')
    title = models.CharField(max_length=150)
    description = models.TextField()
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    location_note = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=20, choices=make_choices(STATUSES), default='Pending')
    priority = models.CharField(max_length=10, choices=make_choices(PRIORITIES), default='Normal')
    is_emergency = models.BooleanField(default=False)
    is_suspicious_activity = models.BooleanField(default=False)
    quality_rating = models.SmallIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['barangay', 'status']),
            models.Index(fields=['reporter', 'created_at']),
            models.Index(fields=['assigned_to', 'status'], name='core_rep_assigned_status_idx'),
            models.Index(fields=['barangay', 'is_emergency', 'status'], name='core_rep_brgy_em_status_idx'),
        ]
        constraints = [
            models.CheckConstraint(condition=Q(status__in=STATUSES), name='ck_rep_status'),
            models.CheckConstraint(condition=Q(priority__in=PRIORITIES), name='ck_rep_prio'),
            models.CheckConstraint(
                condition=Q(latitude__gte=-90, latitude__lte=90, longitude__gte=-180, longitude__lte=180),
                name='ck_rep_geo',
            ),
            models.CheckConstraint(
                condition=Q(quality_rating__isnull=True) | Q(quality_rating__gte=1, quality_rating__lte=5),
                name='ck_rep_rating',
            ),
        ]

    def change_status(self, new_status, by, comment='', department=None):
        comment = (comment or '').strip()
        if new_status not in TRANS.get(self.status, []):
            raise ValidationError(f'Cannot change {self.status} to {new_status}.')
        if new_status == 'Assigned':
            if not department:
                raise ValidationError('Select a department first.')
            self.department = department  # BR-15
        if new_status == 'In Progress' and not self.department_id:
            raise ValidationError('Assign a department first.')  # BR-14
        if new_status in ('Rejected', 'Resolved') and len(comment) < 5:
            raise ValidationError('A comment explaining the reason is required.')  # BR-16
        with transaction.atomic():
            StatusHistory.objects.create(
                report=self,
                changed_by=by,
                old_status=self.status,
                new_status=new_status,
            )  # BR-17
            self.status = new_status
            if new_status == 'Resolved':
                self.resolved_at = timezone.now()
            self.save()
            if comment:
                Comment.objects.create(report=self, author=by, comment_text=comment, is_official=True)
            Notification.objects.create(
                user=self.reporter,
                report=self,
                message=f'Your report "{self.title}" is now {new_status}.',
            )  # BR-22

    def __str__(self):
        return f'#{self.pk} {self.title}'


class ReportPhoto(models.Model):
    report = models.ForeignKey(Report, on_delete=models.CASCADE, related_name='photos')
    image = models.ImageField(upload_to='reports/%Y/%m/')
    file_type = models.CharField(max_length=10)
    file_size_kb = models.IntegerField()
    is_resolution_proof = models.BooleanField(default=False)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(file_type__in=['JPEG', 'PNG']), name='ck_photo_type'),
            models.CheckConstraint(condition=Q(file_size_kb__lte=5120), name='ck_photo_size'),
        ]


@receiver(post_delete, sender=ReportPhoto)
def delete_report_photo_file(sender, instance, **kwargs):
    """Delete physical image files after the DB transaction commits to prevent orphaned files."""
    if not instance.image:
        return
    storage = instance.image.storage
    file_name = instance.image.name
    if file_name:
        def _cleanup():
            try:
                storage.delete(file_name)
            except Exception:
                pass
        transaction.on_commit(_cleanup)


class StatusHistory(models.Model):
    report = models.ForeignKey(Report, on_delete=models.CASCADE, related_name='history')
    changed_by = models.ForeignKey(User, on_delete=models.PROTECT)
    old_status = models.CharField(max_length=20, null=True, blank=True)
    new_status = models.CharField(max_length=20)
    changed_at = models.DateTimeField(auto_now_add=True)


class Comment(models.Model):
    report = models.ForeignKey(Report, on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(User, on_delete=models.PROTECT)
    comment_text = models.TextField()
    is_official = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)


class Announcement(models.Model):
    barangay = models.ForeignKey(Barangay, on_delete=models.CASCADE)
    posted_by = models.ForeignKey(User, on_delete=models.PROTECT)
    title = models.CharField(max_length=150)
    body = models.TextField()
    type = models.CharField(max_length=15, choices=make_choices(ANNOUNCEMENT_TYPES))
    event_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=~Q(type='Event') | Q(event_date__isnull=False),
                name='ck_ann_event',
            ),
        ]

    def __str__(self):
        return self.title


class Notification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    report = models.ForeignKey(Report, null=True, blank=True, on_delete=models.CASCADE)
    message = models.CharField(max_length=255)
    is_read = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
