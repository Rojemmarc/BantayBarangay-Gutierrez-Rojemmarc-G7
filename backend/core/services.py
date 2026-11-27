"""Shared domain queries, security helpers, image sanitization, and notification services."""
import datetime
import io
import os
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.core.files.base import ContentFile
from django.db.models import Count, ExpressionWrapper, F, IntegerField, Q
from PIL import Image, ImageOps
from .models import Notification, Report, User

ACTIVE_STATUSES = ['Pending', 'Assigned', 'In Progress']


def scope_reports(user):
    """Return all reports within the user's barangay (or all barangays for global superusers)."""
    qs = Report.objects.all() if user.is_superuser and not user.barangay_id else Report.objects.filter(barangay=user.barangay)
    return qs.select_related('reporter', 'category', 'department', 'assigned_to', 'barangay')  # BR-19/20


def reports_for_user(user):
    """Return reports visible to a given user role, enforcing strict privacy isolation."""
    if user.is_lgu:
        raise PermissionDenied('LGU accounts can only view aggregated report data.')
    if user.is_superuser or user.role == 'Official':
        return scope_reports(user)
    if user.is_staff_member:
        return scope_reports(user).filter(assigned_to=user)
    if user.role == 'Volunteer':
        return scope_reports(user)
    return Report.objects.filter(reporter=user).select_related(
        'reporter', 'category', 'department', 'assigned_to', 'barangay'
    )


def report_stats_for_user(user):
    """Compute dashboard KPI counts for the user's visible report queue."""
    qs = reports_for_user(user)
    total = qs.count()
    data = {
        'total': total,
        'pending': qs.filter(status='Pending').count(),
        'progress': qs.filter(status__in=['Assigned', 'In Progress']).count(),
        'resolved': qs.filter(status='Resolved').count(),
        'rejected': qs.filter(status='Rejected').count(),
        'emergencies': scope_reports(user).filter(is_emergency=True, status__in=ACTIVE_STATUSES).count(),
    }
    if user.can_manage_reports:
        within_7 = qs.filter(
            resolved_at__isnull=False,
            resolved_at__lte=F('created_at') + datetime.timedelta(days=7),
        ).count()
        data['pct7'] = round(within_7 / total * 100) if total else 0  # BR-30
    return data


def barangay_leaderboard(barangay, limit=5):
    """Compute top community reporters in SQL (1 pt valid + 2 pts resolved + 1 pt high quality)."""
    if not barangay:
        return []
    rows = (
        User.objects.filter(barangay=barangay, role__in=['Resident', 'Volunteer'])
        .annotate(
            valid_count=Count('reports', filter=~Q(reports__status='Rejected')),
            resolved_count=Count('reports', filter=Q(reports__status='Resolved')),
            high_quality_count=Count(
                'reports',
                filter=Q(reports__quality_rating__gte=4) & ~Q(reports__status='Rejected'),
            ),
        )
        .annotate(
            points=ExpressionWrapper(
                F('valid_count') + 2 * F('resolved_count') + F('high_quality_count'),
                output_field=IntegerField(),
            )
        )
        .order_by('-points', 'full_name')[:limit]
    )
    return [(row.full_name, row.points) for row in rows]


def notify_emergency_officials(report):
    """Alert all active barangay officials immediately when an Emergency report is submitted."""
    if not report.is_emergency:
        return
    officials = User.objects.filter(
        barangay=report.barangay,
        role='Official',
        is_active=True,
    ).exclude(pk=report.reporter_id)
    notifications = [
        Notification(
            user=official,
            report=report,
            message=f'EMERGENCY report submitted: "{report.title}".',
        )
        for official in officials
    ]
    if notifications:
        Notification.objects.bulk_create(notifications)


def strip_image_exif(uploaded_file, img_format):
    """Re-encode an uploaded JPG/PNG via Pillow to strip EXIF metadata (GPS, camera info)."""
    uploaded_file.seek(0)
    with Image.open(uploaded_file) as raw_img:
        normalized = ImageOps.exif_transpose(raw_img)
        if img_format == 'JPEG':
            clean_img = normalized.convert('RGB')
            ext = '.jpg'
            save_kwargs = {'format': 'JPEG', 'quality': 88, 'optimize': True}
        else:
            clean_img = normalized.convert('RGBA') if normalized.mode in ('RGBA', 'LA', 'P') else normalized.convert('RGB')
            ext = '.png'
            save_kwargs = {'format': 'PNG', 'optimize': True}

        buf = io.BytesIO()
        clean_img.save(buf, **save_kwargs)

    base = os.path.splitext(os.path.basename(getattr(uploaded_file, 'name', 'evidence')))[0][:40] or 'evidence'
    return ContentFile(buf.getvalue(), name=f'{base}{ext}')


def client_ip(request):
    """Extract client IP address safely for rate limiting."""
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', 'unknown')


def is_rate_limited(key, limit):
    try:
        return cache.get(key, 0) >= limit
    except Exception:
        return False


def bump_rate_limit(key, window_seconds=300):
    try:
        cache.set(key, cache.get(key, 0) + 1, window_seconds)
    except Exception:
        pass


def reset_rate_limit(key):
    try:
        cache.delete(key)
    except Exception:
        pass


def safe_csv_cell(value):
    """Prevent CSV formula injection in spreadsheet tools like Excel."""
    text = '' if value is None else str(value)
    if text and text[0] in ('=', '+', '-', '@', '\t', '\r'):
        return f"'{text}"
    return text
