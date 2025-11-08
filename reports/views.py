from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Sum, Avg, Q
from django.db.models.functions import TruncDate
from django.utils import timezone
from django.http import HttpResponse, HttpResponseBadRequest
from datetime import timedelta, datetime
import csv
from io import BytesIO, StringIO

from campaigns.models import Campaign, Disposition
from calls.models import CallLog
from leads.models import Lead
from django.contrib.auth.models import User

from .models import Dashboard, ReportSchedule

try:
    import pandas as pd
except Exception:  # pragma: no cover
    pd = None

try:
    from reportlab.lib.pagesizes import letter, landscape
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet
except Exception:  # pragma: no cover
    SimpleDocTemplate = None


def _parse_date(value, default):
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return default


def _get_date_range(request):
    """Parse start/end from GET; default last 7 days inclusive."""
    end_default = timezone.now()
    start_default = end_default - timedelta(days=7)
    start_param = request.GET.get('start')
    end_param = request.GET.get('end')
    start = _parse_date(start_param, start_default) if start_param else start_default
    end = _parse_date(end_param, end_default) if end_param else end_default
    # Ensure timezone-aware
    if timezone.is_naive(start):
        start = timezone.make_aware(start)
    if timezone.is_naive(end):
        end = timezone.make_aware(end)
    return start, end


def _common_filters(request):
    start, end = _get_date_range(request)
    campaign_id = request.GET.get('campaign')
    agent_id = request.GET.get('agent')

    filters = Q(start_time__range=(start, end))
    if campaign_id:
        filters &= Q(campaign__id=campaign_id)
    if agent_id:
        filters &= Q(agent__id=agent_id)
    return filters, start, end, campaign_id, agent_id


@login_required
def report_index(request):
    context = {
        'campaigns': Campaign.objects.all()[:50],
        'agents': User.objects.all()[:50],
    }
    return render(request, 'reports/index.html', context)


@login_required
def summary_report(request):
    filters, start, end, campaign_id, agent_id = _common_filters(request)

    base_qs = CallLog.objects.filter(filters)

    totals = base_qs.aggregate(
        total_calls=Count('id'),
        answered=Count('id', filter=Q(disposition__isnull=False)),
        sales=Count('id', filter=Q(disposition__is_sale=True)),
        avg_talk=Avg('talk_duration'),
        total_talk=Sum('talk_duration'),
    )

    contact_rate = (totals['answered'] / totals['total_calls'] * 100) if totals['total_calls'] else 0
    conversion_rate = (totals['sales'] / totals['answered'] * 100) if totals['answered'] else 0

    # Trend data by day
    daily = (
        base_qs.annotate(day=TruncDate('start_time'))
        .values('day')
        .annotate(
            calls=Count('id'),
            answered=Count('id', filter=Q(disposition__isnull=False)),
            sales=Count('id', filter=Q(disposition__is_sale=True)),
        )
        .order_by('day')
    )

    context = {
        'start': start,
        'end': end,
        'campaigns': Campaign.objects.all(),
        'agents': User.objects.all(),
        'totals': totals,
        'contact_rate': round(contact_rate, 1),
        'conversion_rate': round(conversion_rate, 1),
        'daily': list(daily),
    }
    return render(request, 'reports/summary.html', context)


@login_required
def campaign_performance(request):
    filters, start, end, campaign_id, agent_id = _common_filters(request)

    data = (
        CallLog.objects.filter(filters)
        .values('campaign__id', 'campaign__name')
        .annotate(
            calls=Count('id'),
            answered=Count('id', filter=Q(disposition__isnull=False)),
            sales=Count('id', filter=Q(disposition__is_sale=True)),
            avg_talk=Avg('talk_duration'),
            total_talk=Sum('talk_duration'),
        )
        .order_by('-calls')
    )

    # Compute rates for table
    rows = []
    for row in data:
        contact = (row['answered'] / row['calls'] * 100) if row['calls'] else 0
        conv = (row['sales'] / row['answered'] * 100) if row['answered'] else 0
        rows.append({
            'campaign_id': row['campaign__id'],
            'campaign_name': row['campaign__name'] or 'Unassigned',
            'calls': row['calls'],
            'answered': row['answered'],
            'sales': row['sales'],
            'avg_talk': int(row['avg_talk'] or 0),
            'total_talk': int(row['total_talk'] or 0),
            'contact_rate': round(contact, 1),
            'conversion_rate': round(conv, 1),
        })

    context = {
        'start': start,
        'end': end,
        'rows': rows,
        'campaigns': Campaign.objects.all(),
        'agents': User.objects.all(),
    }
    return render(request, 'reports/campaign_performance.html', context)


@login_required
def agent_performance(request):
    filters, start, end, campaign_id, agent_id = _common_filters(request)
    data = (
        CallLog.objects.filter(filters)
        .values('agent__id', 'agent__username')
        .annotate(
            calls=Count('id'),
            answered=Count('id', filter=Q(disposition__isnull=False)),
            sales=Count('id', filter=Q(disposition__is_sale=True)),
            avg_talk=Avg('talk_duration'),
            total_talk=Sum('talk_duration'),
        )
        .order_by('-calls')
    )
    rows = []
    for row in data:
        contact = (row['answered'] / row['calls'] * 100) if row['calls'] else 0
        conv = (row['sales'] / row['answered'] * 100) if row['answered'] else 0
        rows.append({
            'agent_id': row['agent__id'],
            'agent_name': row['agent__username'] or 'Unassigned',
            'calls': row['calls'],
            'answered': row['answered'],
            'sales': row['sales'],
            'avg_talk': int(row['avg_talk'] or 0),
            'total_talk': int(row['total_talk'] or 0),
            'contact_rate': round(contact, 1),
            'conversion_rate': round(conv, 1),
        })

    context = {
        'start': start,
        'end': end,
        'rows': rows,
        'campaigns': Campaign.objects.all(),
        'agents': User.objects.all(),
    }
    return render(request, 'reports/agent_performance.html', context)


@login_required
def call_analytics(request):
    filters, start, end, campaign_id, agent_id = _common_filters(request)
    daily = (
        CallLog.objects.filter(filters)
        .annotate(day=TruncDate('start_time'))
        .values('day')
        .annotate(
            calls=Count('id'),
            answered=Count('id', filter=Q(disposition__isnull=False)),
            sales=Count('id', filter=Q(disposition__is_sale=True)),
            avg_talk=Avg('talk_duration'),
        )
        .order_by('day')
    )

    context = {
        'start': start,
        'end': end,
        'daily': list(daily),
        'campaigns': Campaign.objects.all(),
        'agents': User.objects.all(),
    }
    return render(request, 'reports/call_analytics.html', context)


@login_required
def lead_dispositions(request):
    filters, start, end, campaign_id, agent_id = _common_filters(request)
    data = (
        CallLog.objects.filter(filters)
        .values('disposition__id', 'disposition__name', 'disposition__category', 'disposition__color')
        .annotate(count=Count('id'))
        .order_by('-count')
    )

    context = {
        'start': start,
        'end': end,
        'rows': list(data),
        'campaigns': Campaign.objects.all(),
        'agents': User.objects.all(),
    }
    return render(request, 'reports/lead_dispositions.html', context)


@login_required
def dashboard_list(request):
    dashboards = Dashboard.objects.filter(is_active=True)
    return render(request, 'reports/dashboard_list.html', {'dashboards': dashboards})


@login_required
def dashboard_detail(request, dashboard_id: int):
    dashboard = get_object_or_404(Dashboard, pk=dashboard_id)
    # For now, render a simple page; widgets/layout could be handled later
    return render(request, 'reports/dashboard_detail.html', {'dashboard': dashboard})


@login_required
def schedule_list(request):
    schedules = ReportSchedule.objects.all().select_related('report', 'created_by')
    return render(request, 'reports/schedule_list.html', {'schedules': schedules})


@login_required
def export_report(request, report: str, fmt: str):
    """Export report data in CSV/XLSX/PDF formats."""
    fmt = fmt.lower()
    if report not in {'campaign', 'agent', 'call', 'lead', 'summary'}:
        return HttpResponseBadRequest('Unknown report')

    filters, start, end, campaign_id, agent_id = _common_filters(request)

    # Build dataset based on report
    columns = []
    rows = []

    if report == 'campaign':
        columns = ['Campaign', 'Calls', 'Answered', 'Sales', 'Avg Talk (s)', 'Total Talk (s)', 'Contact %', 'Conversion %']
        data = (
            CallLog.objects.filter(filters)
            .values('campaign__name')
            .annotate(
                calls=Count('id'),
                answered=Count('id', filter=Q(disposition__isnull=False)),
                sales=Count('id', filter=Q(disposition__is_sale=True)),
                avg_talk=Avg('talk_duration'),
                total_talk=Sum('talk_duration'),
            )
        )
        for r in data:
            contact = (r['answered'] / r['calls'] * 100) if r['calls'] else 0
            conv = (r['sales'] / r['answered'] * 100) if r['answered'] else 0
            rows.append([
                r['campaign__name'] or 'Unassigned', r['calls'], r['answered'], r['sales'],
                int(r['avg_talk'] or 0), int(r['total_talk'] or 0), round(contact, 1), round(conv, 1)
            ])
    elif report == 'agent':
        columns = ['Agent', 'Calls', 'Answered', 'Sales', 'Avg Talk (s)', 'Total Talk (s)', 'Contact %', 'Conversion %']
        data = (
            CallLog.objects.filter(filters)
            .values('agent__username')
            .annotate(
                calls=Count('id'),
                answered=Count('id', filter=Q(disposition__isnull=False)),
                sales=Count('id', filter=Q(disposition__is_sale=True)),
                avg_talk=Avg('talk_duration'),
                total_talk=Sum('talk_duration'),
            )
        )
        for r in data:
            contact = (r['answered'] / r['calls'] * 100) if r['calls'] else 0
            conv = (r['sales'] / r['answered'] * 100) if r['answered'] else 0
            rows.append([
                r['agent__username'] or 'Unassigned', r['calls'], r['answered'], r['sales'],
                int(r['avg_talk'] or 0), int(r['total_talk'] or 0), round(contact, 1), round(conv, 1)
            ])
    elif report == 'call':
        columns = ['Date', 'Calls', 'Answered', 'Sales', 'Avg Talk (s)']
        data = (
            CallLog.objects.filter(filters)
            .annotate(day=TruncDate('start_time'))
            .values('day')
            .annotate(
                calls=Count('id'),
                answered=Count('id', filter=Q(disposition__isnull=False)),
                sales=Count('id', filter=Q(disposition__is_sale=True)),
                avg_talk=Avg('talk_duration'),
            )
            .order_by('day')
        )
        for r in data:
            rows.append([r['day'], r['calls'], r['answered'], r['sales'], int(r['avg_talk'] or 0)])
    elif report == 'lead':
        columns = ['Disposition', 'Category', 'Count']
        data = (
            CallLog.objects.filter(filters)
            .values('disposition__name', 'disposition__category')
            .annotate(count=Count('id'))
            .order_by('-count')
        )
        for r in data:
            rows.append([r['disposition__name'] or 'None', r['disposition__category'] or '-', r['count']])
    else:  # summary
        totals = CallLog.objects.filter(filters).aggregate(
            total_calls=Count('id'),
            answered=Count('id', filter=Q(disposition__isnull=False)),
            sales=Count('id', filter=Q(disposition__is_sale=True)),
            avg_talk=Avg('talk_duration'),
            total_talk=Sum('talk_duration'),
        )
        contact_rate = (totals['answered'] / totals['total_calls'] * 100) if totals['total_calls'] else 0
        conversion_rate = (totals['sales'] / totals['answered'] * 100) if totals['answered'] else 0
        columns = ['Metric', 'Value']
        rows = [
            ['Total Calls', totals['total_calls']],
            ['Answered', totals['answered']],
            ['Sales', totals['sales']],
            ['Avg Talk (s)', int(totals['avg_talk'] or 0)],
            ['Total Talk (s)', int(totals['total_talk'] or 0)],
            ['Contact %', round(contact_rate, 1)],
            ['Conversion %', round(conversion_rate, 1)],
        ]

    # Render format
    if fmt == 'csv':
        resp = HttpResponse(content_type='text/csv')
        resp['Content-Disposition'] = f'attachment; filename="{report}_report.csv"'
        writer = csv.writer(resp)
        writer.writerow(columns)
        for r in rows:
            writer.writerow(r)
        return resp
    elif fmt in ('xlsx', 'excel'):
        if pd is None:
            return HttpResponseBadRequest('Excel export requires pandas')
        df = pd.DataFrame(rows, columns=columns)
        bio = BytesIO()
        with pd.ExcelWriter(bio, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Report', index=False)
        resp = HttpResponse(bio.getvalue(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        resp['Content-Disposition'] = f'attachment; filename="{report}_report.xlsx"'
        return resp
    elif fmt == 'pdf':
        if SimpleDocTemplate is None:
            return HttpResponseBadRequest('PDF export requires reportlab')
        bio = BytesIO()
        doc = SimpleDocTemplate(bio, pagesize=landscape(letter))
        elements = []
        styles = getSampleStyleSheet()
        elements.append(Paragraph(f'{report.title()} Report', styles['Title']))
        elements.append(Paragraph(f'Period: {start:%Y-%m-%d} to {end:%Y-%m-%d}', styles['Normal']))
        elements.append(Spacer(1, 12))
        table_data = [columns] + rows
        table = Table(table_data)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#667eea')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
            ('BACKGROUND', (0, 1), (-1, -1), colors.whitesmoke),
            ('GRID', (0, 0), (-1, -1), 0.25, colors.grey),
        ]))
        elements.append(table)
        doc.build(elements)
        resp = HttpResponse(bio.getvalue(), content_type='application/pdf')
        resp['Content-Disposition'] = f'attachment; filename="{report}_report.pdf"'
        return resp
    else:
        return HttpResponseBadRequest('Unsupported format')


@login_required
def realtime(request):
    """Simple realtime-style dashboard with recent calls and quick stats.
    This is a lightweight page intended to satisfy the link from the main dashboard.
    """
    end = timezone.now()
    start = end - timedelta(minutes=30)
    recent_calls = (
        CallLog.objects.filter(start_time__gte=start)
        .select_related('agent', 'campaign', 'disposition')
        .order_by('-start_time')[:50]
    )
    stats = CallLog.objects.filter(start_time__range=(start, end)).aggregate(
        calls=Count('id'),
        answered=Count('id', filter=Q(disposition__isnull=False)),
        sales=Count('id', filter=Q(disposition__is_sale=True)),
        avg_talk=Avg('talk_duration'),
    )
    context = {
        'start': start,
        'end': end,
        'recent_calls': recent_calls,
        'stats': stats,
    }
    return render(request, 'reports/realtime.html', context)
