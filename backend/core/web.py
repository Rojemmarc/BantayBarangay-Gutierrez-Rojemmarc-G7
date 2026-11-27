"""Server-rendered pages for BantayBarangay. Domain rules live in models.py, forms.py, and services.py."""
import csv
import datetime
import json
import mimetypes
from functools import wraps
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm, PasswordResetForm
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Case, Count, IntegerField, Q, When
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from rest_framework.exceptions import ValidationError
from .forms import (
    AnnouncementForm,
    ProfileForm,
    RegisterForm,
    ReportCommentForm,
    ReportForm,
    ReportRatingForm,
    ReportReassignForm,
    ReportTransitionForm,
)
from .models import (
    Announcement,
    Barangay,
    Category,
    Comment,
    Department,
    Notification,
    Report,
    ReportPhoto,
    STATUSES,
    StatusHistory,
    TRANS,
    User,
)
from .services import (
    ACTIVE_STATUSES,
    barangay_leaderboard,
    bump_rate_limit,
    client_ip,
    is_rate_limited,
    notify_emergency_officials,
    report_stats_for_user,
    reports_for_user,
    reset_rate_limit,
    safe_csv_cell,
    scope_reports,
)

ACTIVE = ACTIVE_STATUSES


def flat(err, key=None, out=None):
    out = [] if out is None else out
    if isinstance(err, dict):
        for k, val in err.items():
            flat(val, k, out)
    elif isinstance(err, (list, tuple)):
        for val in err:
            flat(val, key, out)
    else:
        if key and key not in ('non_field_errors', '__all__'):
            out.append(f"{key.replace('_', ' ').capitalize()}: {err}")
        else:
            out.append(str(err))
    return out


def field_error_map(form):
    """Map form field names to their first inline error message for accessible field-level rendering."""
    return {field: [str(msg) for msg in msgs] for field, msgs in form.errors.items()}


def role(official):
    def decorator(view_func):
        @login_required
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            allowed = request.user.is_official if official else request.user.is_reporter
            if not allowed:
                raise PermissionDenied
            return view_func(request, *args, **kwargs)
        return wrapped
    return decorator


def decorate_report(report, user):
    report.who = (
        'Anonymous'
        if report.reporter_id != user.id and (report.is_suspicious_activity or not user.can_manage_reports)
        else report.reporter.full_name
    )  # BR-29
    report.active = report.is_emergency and report.status in ACTIVE
    return report


def apply_report_filters(queryset, params, user):
    if params.get('mine') == '1' and user.role == 'Volunteer':
        queryset = queryset.filter(reporter=user)
    if params.get('category'):
        queryset = queryset.filter(category__name=params['category'])
    if params.get('status') in STATUSES:
        queryset = queryset.filter(status=params['status'])
    if params.get('emergency') == '1':
        queryset = queryset.filter(is_emergency=True, status__in=ACTIVE)
    if params.get('q'):
        term = params['q'][:100]
        queryset = queryset.filter(
            Q(title__icontains=term) | Q(description__icontains=term) | Q(location_note__icontains=term)
        )
    for param_name, op in (('date_from', 'gte'), ('date_to', 'lte')):
        parsed = parse_date(params.get(param_name, '')) if params.get(param_name) else None
        if parsed:
            queryset = queryset.filter(**{f'created_at__date__{op}': parsed})
    return queryset.annotate(
        emergency_order=Case(
            When(is_emergency=True, status__in=ACTIVE, then=0),
            default=1,
            output_field=IntegerField(),
        )
    ).order_by('emergency_order', '-created_at')


def index(request):
    if not request.user.is_authenticated:
        return redirect('login')
    if request.user.is_lgu:
        return redirect('lgu_dashboard')
    return redirect('official' if request.user.is_official else 'app')


def legal(request):
    return render(request, 'legal.html')


def login_view(request):
    if request.user.is_authenticated:
        return redirect('index')
    err = ''
    if request.method == 'POST':
        email = request.POST.get('email', '').strip().lower()
        ip = client_ip(request)
        email_key = f'lock:{email}'
        ip_key = f'lock_ip:{ip}'
        if is_rate_limited(email_key, 5) or is_rate_limited(ip_key, 20):
            err = 'Too many attempts. Try again in 5 minutes.'
        else:
            user = authenticate(request, username=email, password=request.POST.get('password', ''))
            if user:
                reset_rate_limit(email_key)
                login(request, user)
                next_url = request.POST.get('next', '')
                if next_url and url_has_allowed_host_and_scheme(
                    next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
                ):
                    return redirect(next_url)
                return redirect('index')
            bump_rate_limit(email_key, 300)
            bump_rate_limit(ip_key, 300)
            err = 'Incorrect email or password.'
    return render(request, 'auth/login.html', {'error': err, 'next': request.GET.get('next', ''), 'email_val': request.POST.get('email', '')})


@require_POST
def logout_view(request):
    logout(request)
    return redirect('login')


def register_view(request):
    errs = []
    fe = {}
    if request.method == 'POST':
        ip_key = f'reg_ip:{client_ip(request)}'
        if is_rate_limited(ip_key, 15):
            errs = ['Too many registration attempts. Please try again later.']
        else:
            form = RegisterForm(request.POST)
            if form.is_valid():
                d = form.cleaned_data
                User.objects.create_user(
                    d['email'],
                    d['password'],
                    full_name=d['full_name'],
                    barangay=d['barangay'],
                    contact_number=d.get('contact_number', ''),
                    role='Resident',
                    consent_at=timezone.now(),
                )  # BR-04
                bump_rate_limit(ip_key, 600)
                messages.success(request, 'Account created. Please log in.')
                return redirect('login')
            errs = flat(form.errors)
            fe = field_error_map(form)
    return render(
        request,
        'auth/register.html',
        {'errors': errs, 'fe': fe, 'barangays': Barangay.objects.all(), 'v': request.POST},
    )


@login_required
def profile(request):
    errs = []
    fe = {}
    user = request.user
    if request.method == 'POST':
        form = ProfileForm(request.POST, instance=user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Profile updated.')
            return redirect('profile')
        errs = flat(form.errors)
        fe = field_error_map(form)
    values = (
        request.POST
        if request.method == 'POST'
        else {'full_name': user.full_name, 'email': user.email, 'contact_number': user.contact_number}
    )
    return render(request, 'profile.html', {'errors': errs, 'fe': fe, 'v': values})


@login_required
def change_password(request):
    errs = []
    fe = {}
    if request.method == 'POST':
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            messages.success(request, 'Password updated.')
            return redirect('profile')
        errs = flat(form.errors)
        fe = field_error_map(form)
    return render(request, 'change_password.html', {'errors': errs, 'fe': fe})


def forgot(request):
    sent = False
    if request.method == 'POST':
        ip_key = f'forgot_ip:{client_ip(request)}'
        if not is_rate_limited(ip_key, 10):
            bump_rate_limit(ip_key, 600)
            form = PasswordResetForm({'email': request.POST.get('email', '')})
            if form.is_valid():
                form.save(request=request, use_https=request.is_secure())
        sent = True  # Same answer whether or not the account exists
    return render(request, 'auth/forgot.html', {'sent': sent})


@login_required
def home(request):
    user = request.user
    if user.is_lgu:
        return redirect('lgu_dashboard')
    expected_name = 'official' if user.is_official else 'app'
    if request.resolver_match.url_name != expected_name:
        return redirect('index')

    params = request.GET
    queryset = apply_report_filters(reports_for_user(user), params, user)
    page = Paginator(queryset, 25).get_page(params.get('page'))
    for item in page:
        decorate_report(item, user)

    keep = params.copy()
    keep.pop('page', None)

    map_points = []
    if user.can_manage_reports:
        active_items = queryset.filter(status__in=ACTIVE)[:100]
        map_points = [
            {
                'id': item.pk,
                'title': item.title,
                'category': item.category.name,
                'status': item.status,
                'is_emergency': item.is_emergency,
                'lat': float(item.latitude),
                'lng': float(item.longitude),
                'url': f'/reports/{item.pk}/',
            }
            for item in active_items
        ]

    filter_keys = ('q', 'category', 'status', 'date_from', 'date_to', 'mine', 'emergency')
    return render(
        request,
        'home.html',
        {
            'page': page,
            'stats': report_stats_for_user(user),
            'cats': Category.objects.all(),
            'statuses': STATUSES,
            'g': params,
            'qs': keep.urlencode(),
            'filtered': any(params.get(k) for k in filter_keys),
            'advanced_filtered': any(params.get(k) for k in ('category', 'date_from', 'date_to', 'mine')),
            'map_points_json': json.dumps(map_points),
            'map_points_count': len(map_points),
        },
    )


@login_required
def export_reports_csv(request):
    """Allow barangay Officials to export filtered barangay reports as a safe CSV file."""
    user = request.user
    if not user.can_manage_reports:
        raise PermissionDenied
    queryset = apply_report_filters(reports_for_user(user), request.GET, user)
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    stamp = timezone.localdate().isoformat()
    response['Content-Disposition'] = f'attachment; filename="bantaybarangay-reports-{stamp}.csv"'
    writer = csv.writer(response)
    writer.writerow([
        'ID', 'Title', 'Category', 'Status', 'Priority', 'Emergency',
        'Barangay', 'Department', 'Assigned Staff', 'Reporter',
        'Location Note', 'Latitude', 'Longitude', 'Quality Rating',
        'Created At', 'Resolved At',
    ])
    for item in queryset.iterator():
        writer.writerow([
            item.pk,
            safe_csv_cell(item.title),
            safe_csv_cell(item.category.name),
            safe_csv_cell(item.status),
            safe_csv_cell(item.priority),
            'Yes' if item.is_emergency else 'No',
            safe_csv_cell(str(item.barangay)),
            safe_csv_cell(item.department.name if item.department else ''),
            safe_csv_cell(item.assigned_to.full_name if item.assigned_to else ''),
            safe_csv_cell(item.reporter.full_name),
            safe_csv_cell(item.location_note),
            item.latitude,
            item.longitude,
            item.quality_rating or '',
            timezone.localtime(item.created_at).strftime('%Y-%m-%d %H:%M'),
            timezone.localtime(item.resolved_at).strftime('%Y-%m-%d %H:%M') if item.resolved_at else '',
        ])
    return response


@login_required
def lgu_dashboard(request):
    if not request.user.is_lgu:
        raise PermissionDenied
    total = Report.objects.count()

    def with_pct(rows):
        items = list(rows)
        for row in items:
            row['pct'] = round(row['count'] / total * 100) if total else 0
        return items

    totals = with_pct(Report.objects.values('status').annotate(count=Count('id')).order_by('status'))
    categories = with_pct(
        Report.objects.values('category__name').annotate(count=Count('id')).order_by('-count', 'category__name')
    )
    barangays = with_pct(
        Report.objects.values('barangay__name', 'barangay__city_municipality', 'barangay__province')
        .annotate(count=Count('id'))
        .order_by('-count', 'barangay__name')
    )
    return render(
        request,
        'lgu_dashboard.html',
        {'total': total, 'statuses': totals, 'categories': categories, 'barangays': barangays},
    )


@login_required
def export_lgu_csv(request):
    """Export anonymized cross-barangay aggregate statistics for LGU analysts (zero PII)."""
    if not request.user.is_lgu:
        raise PermissionDenied
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    stamp = timezone.localdate().isoformat()
    response['Content-Disposition'] = f'attachment; filename="bantaybarangay-lgu-summary-{stamp}.csv"'
    writer = csv.writer(response)
    writer.writerow(['Section', 'Label', 'Count'])
    writer.writerow(['Overview', 'Total Reports', Report.objects.count()])
    for row in Report.objects.values('status').annotate(count=Count('id')).order_by('status'):
        writer.writerow(['By Status', safe_csv_cell(row['status']), row['count']])
    for row in Report.objects.values('category__name').annotate(count=Count('id')).order_by('-count', 'category__name'):
        writer.writerow(['By Category', safe_csv_cell(row['category__name']), row['count']])
    for row in (
        Report.objects.values('barangay__name', 'barangay__city_municipality')
        .annotate(count=Count('id'))
        .order_by('-count', 'barangay__name')
    ):
        label = f"{row['barangay__name']}, {row['barangay__city_municipality']}"
        writer.writerow(['By Barangay', safe_csv_cell(label), row['count']])
    return response


@role(False)
def new_report(request):
    errs = []
    fe = {}
    if request.method == 'POST':
        user = request.user
        daily_count = Report.objects.filter(
            reporter=user, created_at__gte=timezone.now() - datetime.timedelta(days=1)
        ).count()
        if daily_count >= 5:
            errs = ['Daily limit reached: 5 reports per day.']  # BR-10
        else:
            form = ReportForm(request.POST, uploaded_photos=request.FILES.getlist('photos'))
            if form.is_valid():
                d = form.cleaned_data
                cat = d['category']
                with transaction.atomic():
                    rep = Report.objects.create(
                        reporter=user,
                        barangay=user.barangay,
                        category=cat,
                        title=d['title'],
                        description=d['description'],
                        latitude=d['latitude'],
                        longitude=d['longitude'],
                        location_note=d.get('location_note', ''),
                        is_suspicious_activity=d.get('is_suspicious_activity', False),
                        is_emergency=cat.is_emergency,
                        priority='Urgent' if cat.is_emergency else 'Normal',
                    )
                    for clean_file, fmt in form.validated_photos:
                        ReportPhoto.objects.create(
                            report=rep,
                            image=clean_file,
                            file_type=fmt,
                            file_size_kb=max(1, clean_file.size // 1024),
                            is_resolution_proof=False,
                        )
                    StatusHistory.objects.create(
                        report=rep, changed_by=user, old_status=None, new_status='Pending'
                    )
                    notify_emergency_officials(rep)
                messages.success(request, 'Report submitted.')
                return redirect('detail', pk=rep.pk)
            errs = flat(form.errors)
            fe = field_error_map(form)
    return render(
        request,
        'new_report.html',
        {'cats': Category.objects.all(), 'errors': errs, 'fe': fe, 'v': request.POST},
    )


@role(False)
def edit_report(request, pk):
    report = get_object_or_404(scope_reports(request.user).prefetch_related('photos'), pk=pk)
    if report.reporter_id != request.user.id or report.status != 'Pending':
        raise PermissionDenied  # BR-18
    errs = []
    fe = {}
    if request.method == 'POST':
        form = ReportForm(
            request.POST,
            instance=report,
            uploaded_photos=request.FILES.getlist('photos'),
            remove_photo_ids=request.POST.getlist('remove_photos'),
        )
        if form.is_valid():
            d = form.cleaned_data
            cat = d['category']
            with transaction.atomic():
                rep = form.save(commit=False)
                rep.is_suspicious_activity = d.get('is_suspicious_activity', False)
                rep.is_emergency = cat.is_emergency
                rep.priority = 'Urgent' if cat.is_emergency else 'Normal'
                rep.save()
                for old_photo in form.photos_to_remove:
                    old_photo.delete()
                for clean_file, fmt in form.validated_photos:
                    ReportPhoto.objects.create(
                        report=rep,
                        image=clean_file,
                        file_type=fmt,
                        file_size_kb=max(1, clean_file.size // 1024),
                        is_resolution_proof=False,
                    )
            messages.success(request, 'Report updated.')
            return redirect('detail', pk=report.pk)
        errs = flat(form.errors)
        fe = field_error_map(form)
        values = request.POST
    else:
        values = {
            'category': str(report.category_id),
            'title': report.title,
            'description': report.description,
            'latitude': str(report.latitude),
            'longitude': str(report.longitude),
            'location_note': report.location_note,
            'is_suspicious_activity': report.is_suspicious_activity,
        }
    return render(
        request,
        'edit_report.html',
        {
            'x': report,
            'evidence_photos': report.photos.filter(is_resolution_proof=False),
            'cats': Category.objects.all(),
            'errors': errs,
            'fe': fe,
            'v': values,
        },
    )


@login_required
def detail(request, pk):
    user = request.user
    report = decorate_report(
        get_object_or_404(reports_for_user(user).prefetch_related('photos'), pk=pk),
        user,
    )
    all_photos = list(report.photos.all())
    evidence_photos = [p for p in all_photos if not p.is_resolution_proof]
    resolution_photos = [p for p in all_photos if p.is_resolution_proof]
    history = [
        (
            h,
            'Anonymous' if report.who == 'Anonymous' and h.changed_by_id == report.reporter_id else h.changed_by.full_name,
        )
        for h in report.history.select_related('changed_by')
    ]
    return render(
        request,
        'detail.html',
        {
            'x': report,
            'evidence_photos': evidence_photos,
            'resolution_photos': resolution_photos,
            'history': history,
            'comments': report.comments.select_related('author'),
            'nx': TRANS.get(report.status, []),
            'depts': Department.objects.filter(barangay=report.barangay) if user.can_manage_reports else [],
            'staff_members': (
                User.objects.filter(barangay=report.barangay, role='Staff', is_active=True)
                if user.can_manage_reports
                else []
            ),
        },
    )


@role(True)
@require_POST
def transition(request, pk):
    user = request.user
    with transaction.atomic():
        report = get_object_or_404(reports_for_user(user).select_for_update(of=('self',)), pk=pk)
        form = ReportTransitionForm(
            request.POST,
            report=report,
            user=user,
            resolution_photos=request.FILES.getlist('resolution_photos'),
        )
        if not form.is_valid():
            messages.error(request, ' '.join(flat(form.errors)))
        else:
            d = form.cleaned_data
            try:
                report.change_status(d['status'], user, d.get('comment', ''), d.get('department'))
                assignee = d.get('assigned_to') if user.can_manage_reports and d['status'] == 'Assigned' else None
                if assignee:
                    report.assigned_to = assignee
                    report.save(update_fields=['assigned_to', 'updated_at'])
                    Notification.objects.create(
                        user=assignee,
                        report=report,
                        message=f'You were assigned report "{report.title}".',
                    )
                if d['status'] == 'Resolved':
                    for clean_file, fmt in form.validated_resolution_photos:
                        ReportPhoto.objects.create(
                            report=report,
                            image=clean_file,
                            file_type=fmt,
                            file_size_kb=max(1, clean_file.size // 1024),
                            is_resolution_proof=True,
                        )
                messages.success(request, f'Status updated to {report.status}.')
            except ValidationError as exc:
                messages.error(request, ' '.join(flat(exc.detail)))
    return redirect('detail', pk=pk)


@login_required
@require_POST
def reassign_report(request, pk):
    """Allow barangay Officials to reassign an active Assigned/In Progress report."""
    user = request.user
    if not user.can_manage_reports:
        raise PermissionDenied
    with transaction.atomic():
        report = get_object_or_404(scope_reports(user).select_for_update(of=('self',)), pk=pk)
        form = ReportReassignForm(request.POST, report=report)
        if not form.is_valid():
            messages.error(request, ' '.join(flat(form.errors)))
        else:
            d = form.cleaned_data
            new_dept = d['department']
            new_staff = d['assigned_to']
            note = d.get('note', '')
            report.department = new_dept
            report.assigned_to = new_staff
            report.save(update_fields=['department', 'assigned_to', 'updated_at'])
            msg = f'Reassigned to {new_dept.name} ({new_staff.full_name}).'
            if note:
                msg = f'{msg} {note}'
            Comment.objects.create(report=report, author=user, comment_text=msg[:1000], is_official=True)
            Notification.objects.create(
                user=new_staff,
                report=report,
                message=f'You were reassigned report "{report.title}".',
            )
            messages.success(request, f'Reassigned to {new_staff.full_name} ({new_dept.name}).')
    return redirect('detail', pk=pk)


@login_required
@require_POST
def comment(request, pk):
    user = request.user
    if not (user.can_manage_reports or user.is_staff_member or user.role == 'Volunteer'):
        raise PermissionDenied
    report = get_object_or_404(reports_for_user(user), pk=pk)
    form = ReportCommentForm(request.POST, report=report, user=user)
    if not form.is_valid():
        messages.error(request, ' '.join(flat(form.errors)))
    else:
        text = form.cleaned_data['comment']
        Comment.objects.create(report=report, author=user, comment_text=text[:1000], is_official=user.is_official)
        label = 'official update' if user.is_official else 'community update'
        if report.reporter_id != user.id:
            Notification.objects.create(
                user=report.reporter, report=report, message=f'New {label} on "{report.title}".'
            )
        if report.assigned_to_id and report.assigned_to_id != user.id:
            Notification.objects.create(
                user=report.assigned_to, report=report, message=f'New {label} on "{report.title}".'
            )
        messages.success(request, 'Comment posted.')
    return redirect('detail', pk=pk)


@login_required
@require_POST
def rate_report(request, pk):
    if not request.user.can_manage_reports:
        raise PermissionDenied
    report = get_object_or_404(scope_reports(request.user), pk=pk)
    form = ReportRatingForm(request.POST, report=report)
    if not form.is_valid():
        messages.error(request, ' '.join(flat(form.errors)))
    else:
        report.quality_rating = form.cleaned_data['rating']
        report.save(update_fields=['quality_rating', 'updated_at'])
        messages.success(request, f'Quality rating saved ({report.quality_rating}/5).')
    return redirect('detail', pk=pk)


@role(False)
@require_POST
def delete_report(request, pk):
    report = get_object_or_404(scope_reports(request.user), pk=pk)
    if report.reporter_id != request.user.id or report.status != 'Pending':
        raise PermissionDenied  # BR-18
    report.delete()
    messages.success(request, 'Report deleted.')
    return redirect('app')


@login_required
def alerts(request):
    if request.user.is_lgu:
        raise PermissionDenied
    items = list(request.user.notifications.select_related('report').order_by('-created_at')[:50])
    request.user.notifications.filter(is_read=False).update(is_read=True)
    return render(request, 'alerts.html', {'items': items})


@login_required
def bulletin(request):
    user = request.user
    errs = []
    fe = {}
    if request.method == 'POST':
        if not user.can_manage_reports:
            raise PermissionDenied  # BR-24
        if not user.barangay_id:
            errs = ['Assign your account to a barangay before posting bulletin announcements.']
        else:
            form = AnnouncementForm(request.POST)
            if form.is_valid():
                ann = form.save(commit=False)
                ann.barangay = user.barangay
                ann.posted_by = user
                ann.save()
                messages.success(request, 'Announcement posted.')
                return redirect('bulletin')
            errs = flat(form.errors)
            fe = field_error_map(form)

    qs = Announcement.objects.filter(
        Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now())
    ).select_related('posted_by').order_by('-created_at')
    if user.barangay_id:
        qs = qs.filter(barangay=user.barangay)
    show_all = request.GET.get('all') == '1'
    total_count = qs.count()
    rank = barangay_leaderboard(user.barangay, limit=5) if not user.is_lgu else []
    return render(
        request,
        'bulletin.html',
        {
            'items': qs if show_all else qs[:5],
            'more': total_count > 5,
            'all': show_all,
            'errors': errs,
            'fe': fe,
            'rank': rank,
            'v': request.POST,
        },
    )


@login_required
def ann_edit(request, pk):
    user = request.user
    if not user.can_manage_reports:
        raise PermissionDenied
    ann_qs = Announcement.objects.all() if user.is_superuser and not user.barangay_id else Announcement.objects.filter(barangay=user.barangay)
    ann = get_object_or_404(ann_qs, pk=pk)
    errs = []
    fe = {}
    if request.method == 'POST':
        form = AnnouncementForm(request.POST, instance=ann)
        if form.is_valid():
            form.save()
            messages.success(request, 'Announcement updated.')
            return redirect('bulletin')
        errs = flat(form.errors)
        fe = field_error_map(form)
        values = request.POST
    else:
        values = {
            'title': ann.title,
            'type': ann.type,
            'event_date': ann.event_date.isoformat() if ann.event_date else '',
            'expires_at': timezone.localtime(ann.expires_at).strftime('%Y-%m-%dT%H:%M') if ann.expires_at else '',
            'body': ann.body,
        }
    return render(request, 'edit_announcement.html', {'a': ann, 'errors': errs, 'fe': fe, 'v': values})


@login_required
@require_POST
def ann_delete(request, pk):
    if not request.user.can_manage_reports:
        raise PermissionDenied
    ann_qs = Announcement.objects.all() if request.user.is_superuser and not request.user.barangay_id else Announcement.objects.filter(barangay=request.user.barangay)
    get_object_or_404(ann_qs, pk=pk).delete()
    messages.success(request, 'Announcement deleted.')
    return redirect('bulletin')


@login_required
def photo(request, pk):
    p = get_object_or_404(
        ReportPhoto.objects.select_related('report', 'report__reporter', 'report__category'), pk=pk
    )
    get_object_or_404(reports_for_user(request.user), pk=p.report_id)
    if not request.user.is_superuser and p.report.barangay_id != request.user.barangay_id:
        raise Http404
    try:
        fh = p.image.open('rb')
    except FileNotFoundError as exc:
        raise Http404('Photo file not found.') from exc
    return FileResponse(fh, content_type=mimetypes.guess_type(p.image.name)[0] or 'application/octet-stream')
