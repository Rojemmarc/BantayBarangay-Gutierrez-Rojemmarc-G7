"""Django forms and business-rule validation for server-rendered workflows."""
import re
from django import forms
from django.contrib.auth.password_validation import validate_password
from django.utils import timezone
from PIL import Image, UnidentifiedImageError
from .models import (
    ANNOUNCEMENT_TYPES,
    Announcement,
    Barangay,
    Category,
    Department,
    Report,
    STATUSES,
    TRANS,
    User,
)
from .services import strip_image_exif

MAX_PHOTO_BYTES = 5 * 1024 * 1024
ALLOWED_IMAGE_FORMATS = ('JPEG', 'PNG')
PHONE_RE = re.compile(r'^[0-9+\-\s()]{7,20}$')


def validate_uploaded_photos(uploaded_files, existing_count=0, remove_count=0, min_total=1, max_total=3):
    """Validate and EXIF-strip uploaded evidence images (JPG/PNG, <= 5 MB each)."""
    uploaded_files = [f for f in (uploaded_files or []) if f]
    remaining = max(0, existing_count - remove_count)
    total = remaining + len(uploaded_files)
    if total < min_total:
        raise forms.ValidationError(f'At least {min_total} photo is required.')
    if total > max_total:
        raise forms.ValidationError(f'You can attach at most {max_total} photos per report.')

    validated = []
    for f in uploaded_files:
        if f.size > MAX_PHOTO_BYTES:
            raise forms.ValidationError('Photos must be JPG or PNG, up to 5 MB each.')
        try:
            f.seek(0)
            with Image.open(f) as img:
                img.verify()
                fmt = (img.format or '').upper()
            f.seek(0)
        except (UnidentifiedImageError, OSError, ValueError):
            raise forms.ValidationError('Photos must be valid JPG or PNG images.')
        if fmt not in ALLOWED_IMAGE_FORMATS:
            raise forms.ValidationError('Photos must be JPG or PNG, up to 5 MB each.')
        clean_file = strip_image_exif(f, fmt)
        validated.append((clean_file, fmt))
    return validated


class RegisterForm(forms.Form):
    """Public Resident registration form with password strength & privacy consent validation."""

    full_name = forms.CharField(min_length=2, max_length=150)
    email = forms.EmailField(max_length=255)
    password = forms.CharField(min_length=8, widget=forms.PasswordInput)
    password2 = forms.CharField(widget=forms.PasswordInput)
    barangay = forms.ModelChoiceField(queryset=Barangay.objects.all())
    contact_number = forms.CharField(max_length=20, required=False)
    consent = forms.BooleanField(
        required=True,
        error_messages={'required': 'You must accept the Terms and Privacy Policy.'},
    )

    def clean_full_name(self):
        value = (self.cleaned_data.get('full_name') or '').strip()
        if len(value) < 2:
            raise forms.ValidationError('Full name must be at least 2 characters.')
        return value

    def clean_email(self):
        value = (self.cleaned_data.get('email') or '').strip().lower()
        if User.objects.filter(email__iexact=value).exists():
            raise forms.ValidationError('This email is already registered.')  # BR-01
        return value

    def clean_contact_number(self):
        value = (self.cleaned_data.get('contact_number') or '').strip()
        if value and not PHONE_RE.match(value):
            raise forms.ValidationError('Enter a valid contact number (7 to 20 digits/symbols).')
        return value

    def clean(self):
        cleaned = super().clean()
        password = cleaned.get('password')
        password2 = cleaned.get('password2')
        if password and password2 and password != password2:
            self.add_error('password2', 'Passwords do not match.')
        elif password:
            try:
                validate_password(
                    password,
                    User(
                        email=cleaned.get('email', ''),
                        full_name=cleaned.get('full_name', ''),
                    ),
                )
            except forms.ValidationError as exc:
                self.add_error('password', exc)
        return cleaned


class ProfileForm(forms.ModelForm):
    """Form for viewing and editing the logged-in user's own profile."""

    class Meta:
        model = User
        fields = ['full_name', 'email', 'contact_number']

    def clean_full_name(self):
        value = (self.cleaned_data.get('full_name') or '').strip()
        if len(value) < 2:
            raise forms.ValidationError('Full name must be at least 2 characters.')
        return value

    def clean_email(self):
        value = (self.cleaned_data.get('email') or '').strip().lower()
        qs = User.objects.filter(email__iexact=value)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError('This email is already registered.')
        return value

    def clean_contact_number(self):
        value = (self.cleaned_data.get('contact_number') or '').strip()
        if value and not PHONE_RE.match(value):
            raise forms.ValidationError('Enter a valid contact number (7 to 20 digits/symbols).')
        return value


class ReportForm(forms.ModelForm):
    """Form for creating and editing a community concern / incident report."""

    category = forms.ModelChoiceField(queryset=Category.objects.all(), empty_label='Select…')
    location_note = forms.CharField(max_length=255, required=False)
    is_suspicious_activity = forms.BooleanField(required=False)

    class Meta:
        model = Report
        fields = [
            'category',
            'title',
            'description',
            'latitude',
            'longitude',
            'location_note',
            'is_suspicious_activity',
        ]

    def __init__(self, *args, uploaded_photos=None, remove_photo_ids=None, **kwargs):
        self.uploaded_photos = uploaded_photos or []
        self.remove_photo_ids = set(remove_photo_ids or [])
        super().__init__(*args, **kwargs)
        self.validated_photos = []
        self.photos_to_remove = []

    def clean_title(self):
        value = (self.cleaned_data.get('title') or '').strip()
        if len(value) < 3:
            raise forms.ValidationError('Title must be at least 3 characters.')
        return value

    def clean_description(self):
        value = (self.cleaned_data.get('description') or '').strip()
        if len(value) < 20:
            raise forms.ValidationError('Description must be at least 20 characters.')
        if len(value) > 2000:
            raise forms.ValidationError('Description must be 2000 characters or fewer.')
        return value

    def clean_latitude(self):
        value = self.cleaned_data.get('latitude')
        if value is None or value < -90 or value > 90:
            raise forms.ValidationError('Latitude must be between -90 and 90.')
        return value

    def clean_longitude(self):
        value = self.cleaned_data.get('longitude')
        if value is None or value < -180 or value > 180:
            raise forms.ValidationError('Longitude must be between -180 and 180.')
        return value

    def clean_location_note(self):
        return (self.cleaned_data.get('location_note') or '').strip()

    def clean(self):
        cleaned = super().clean()
        cat = cleaned.get('category')
        if cat:
            cleaned['is_suspicious_activity'] = bool(
                cleaned.get('is_suspicious_activity') and cat.name == 'Safety'
            )

        existing_count = 0
        if self.instance and self.instance.pk:
            existing_photos = list(self.instance.photos.filter(is_resolution_proof=False))
            existing_count = len(existing_photos)
            self.photos_to_remove = [p for p in existing_photos if str(p.pk) in self.remove_photo_ids]

        try:
            self.validated_photos = validate_uploaded_photos(
                self.uploaded_photos,
                existing_count=existing_count,
                remove_count=len(self.photos_to_remove),
            )
        except forms.ValidationError as exc:
            self.add_error(None, exc)

        return cleaned


class ReportTransitionForm(forms.Form):
    """Validates official/staff status transitions, assignment rules, and optional resolution proof."""

    status = forms.ChoiceField(choices=[(s, s) for s in STATUSES])
    department = forms.ModelChoiceField(queryset=Department.objects.none(), required=False)
    assigned_to = forms.ModelChoiceField(queryset=User.objects.none(), required=False)
    comment = forms.CharField(max_length=1000, required=False)

    def __init__(self, *args, report, user, resolution_photos=None, **kwargs):
        self.report = report
        self.user = user
        self.resolution_photos = resolution_photos or []
        self.validated_resolution_photos = []
        super().__init__(*args, **kwargs)
        self.fields['department'].queryset = Department.objects.filter(barangay=report.barangay)
        self.fields['assigned_to'].queryset = User.objects.filter(
            barangay=report.barangay, role='Staff', is_active=True
        )

    def clean(self):
        cleaned = super().clean()
        new_status = cleaned.get('status')
        comment = (cleaned.get('comment') or '').strip()
        cleaned['comment'] = comment

        if not new_status:
            return cleaned
        if new_status not in TRANS.get(self.report.status, []):
            raise forms.ValidationError(f'Cannot change {self.report.status} to {new_status}.')
        if new_status == 'Assigned':
            if not cleaned.get('department'):
                raise forms.ValidationError('Select a department first.')
            if self.user.can_manage_reports and not cleaned.get('assigned_to'):
                raise forms.ValidationError('Select a staff member to assign this report to.')
        if new_status == 'In Progress' and not self.report.department_id:
            raise forms.ValidationError('Assign a department first.')
        if new_status in ('Resolved', 'Rejected') and len(comment) < 5:
            raise forms.ValidationError('A comment explaining the reason is required.')
        if new_status == 'Resolved' and self.resolution_photos:
            try:
                self.validated_resolution_photos = validate_uploaded_photos(
                    self.resolution_photos,
                    existing_count=0,
                    remove_count=0,
                    min_total=0,
                    max_total=2,
                )
            except forms.ValidationError as exc:
                self.add_error(None, exc)
        return cleaned


class ReportReassignForm(forms.Form):
    """Allows Officials to reassign an active Assigned/In Progress report to another department or staff."""

    department = forms.ModelChoiceField(queryset=Department.objects.none())
    assigned_to = forms.ModelChoiceField(queryset=User.objects.none())
    note = forms.CharField(max_length=500, required=False)

    def __init__(self, *args, report, **kwargs):
        self.report = report
        super().__init__(*args, **kwargs)
        self.fields['department'].queryset = Department.objects.filter(barangay=report.barangay)
        self.fields['assigned_to'].queryset = User.objects.filter(
            barangay=report.barangay, role='Staff', is_active=True
        )

    def clean(self):
        cleaned = super().clean()
        if self.report.status not in ('Assigned', 'In Progress'):
            raise forms.ValidationError('Only Assigned or In Progress reports can be reassigned.')
        cleaned['note'] = (cleaned.get('note') or '').strip()
        return cleaned


class ReportCommentForm(forms.Form):
    """Validates official and volunteer coordination comments."""

    comment = forms.CharField(max_length=1000, required=True)

    def __init__(self, *args, report, user, **kwargs):
        self.report = report
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_comment(self):
        text = (self.cleaned_data.get('comment') or '').strip()
        if len(text) < 2:
            raise forms.ValidationError('Write a comment first.')
        return text

    def clean(self):
        cleaned = super().clean()
        if self.user.role == 'Volunteer' and self.report.status not in ('Pending', 'Assigned', 'In Progress'):
            raise forms.ValidationError('Community updates can only be added to active reports.')
        return cleaned


class ReportRatingForm(forms.Form):
    """Validates quality ratings (1-5) on resolved reports (BR-27)."""

    rating = forms.IntegerField(min_value=1, max_value=5)

    def __init__(self, *args, report, **kwargs):
        self.report = report
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned = super().clean()
        if self.report.status != 'Resolved':
            raise forms.ValidationError('Only Resolved reports can be rated 1 to 5.')
        return cleaned


class AnnouncementForm(forms.ModelForm):
    """Validates barangay bulletin announcements, advisories, and events (create & edit)."""

    type = forms.ChoiceField(choices=[(t, t) for t in ANNOUNCEMENT_TYPES])
    event_date = forms.DateField(required=False)
    expires_at = forms.DateTimeField(
        required=False,
        input_formats=['%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d'],
    )

    class Meta:
        model = Announcement
        fields = ['title', 'type', 'event_date', 'expires_at', 'body']

    def clean_title(self):
        value = (self.cleaned_data.get('title') or '').strip()
        if len(value) < 3:
            raise forms.ValidationError('Title must be at least 3 characters.')
        return value

    def clean_body(self):
        value = (self.cleaned_data.get('body') or '').strip()
        if len(value) < 5:
            raise forms.ValidationError('Message must be at least 5 characters.')
        if len(value) > 2000:
            raise forms.ValidationError('Message must be 2000 characters or fewer.')
        return value

    def clean(self):
        cleaned = super().clean()
        ann_type = cleaned.get('type')
        event_date = cleaned.get('event_date')
        expires_at = cleaned.get('expires_at')

        if ann_type == 'Event' and (not event_date or event_date < timezone.localdate()):
            self.add_error('event_date', 'Events need a date that is not in the past.')  # BR-25
        if ann_type != 'Event':
            cleaned['event_date'] = None
        if expires_at and expires_at <= timezone.now():
            self.add_error('expires_at', 'Expiry date and time must be in the future.')
        return cleaned
