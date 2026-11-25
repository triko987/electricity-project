import json
import csv
from pathlib import Path
from decimal import Decimal
from datetime import timedelta

import pandas as pd
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from .forms import RegisterForm
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.views.decorators.http import require_POST
from django.db.models import Sum, Avg, Count
from django.core.paginator import Paginator
from django.conf import settings
from django.utils import timezone

from .models import (
    ElectricityConsumption,
    ConsumptionPrediction,
    EnergyAnomaly,
    EnergyRecommendation,
    EnergyEfficiencyScore,
    RecommendationFeedback
)
from .forms import (
    ElectricityConsumptionForm,
    CSVUploadForm,
    PredictionSimulatorForm
)
from .preprocessing import (
    import_records_from_csv,
    import_sample_dataset_for_user,
    clean_and_preprocess_dataframe
)
from .ml_service import (
    detect_single_anomaly,
    scan_user_anomalies,
    predict_custom_consumption,
    forecast_user_consumption,
    get_ml_algorithms_comparison
)
from .waste_analysis import analyze_energy_waste
from .recommendations import generate_personalized_recommendations
from .efficiency_score import calculate_energy_efficiency_score
from .advanced_features import (
    simulate_digital_twin,
    diagnose_waste_detective,
    compute_energy_fingerprint,
    record_user_feedback,
    get_self_learning_metrics
)


# ========================================================
# 1. DASHBOARD VIEW (Module 8 & Section 6)
# ========================================================

@login_required
def dashboard(request):
    user = request.user
    records = ElectricityConsumption.objects.filter(user=user).order_by('-recorded_at')
    total_records = records.count()

    total_consumption = records.aggregate(total=Sum('energy_kwh'))['total'] or Decimal('0.000')
    total_consumption_float = float(total_consumption)

    # Calculate Energy Efficiency Score
    efficiency_data = calculate_energy_efficiency_score(user)

    # Calculate Energy Waste Analysis
    waste_data = analyze_energy_waste(user)

    # Calculate Time-Series ML Prediction
    forecast_data = forecast_user_consumption(user, days=7)
    tomorrow_prediction = forecast_data.get('tomorrow_predicted_kwh', 0.0)

    # Active Anomaly Alerts
    active_anomalies = EnergyAnomaly.objects.filter(user=user, is_resolved=False).select_related('consumption').order_by('-detected_at')
    active_anomaly_count = active_anomalies.count()

    # Carbon emissions (kg CO2e)
    carbon_emissions = round(total_consumption_float * 0.82, 2)

    # Recent records for table
    recent_records = list(records[:8])

    # Fetch anomaly mapping for recent records
    anomaly_record_ids = set(
        EnergyAnomaly.objects.filter(user=user, consumption__in=recent_records).values_list('consumption_id', flat=True)
    )
    for r in recent_records:
        r.is_anomaly = r.id in anomaly_record_ids

    # ----------------------------------------------------
    # Multi-Period Comparisons: Daily, Weekly, Monthly (Section 6.3)
    # ----------------------------------------------------
    # 1. Daily usage (last 14 days)
    daily_records = records.filter(
        recorded_at__gte=timezone.now() - timedelta(days=14)
    ).order_by('recorded_at')

    daily_dict = {}
    for r in daily_records:
        date_str = r.recorded_at.strftime('%d %b')
        daily_dict[date_str] = daily_dict.get(date_str, 0.0) + float(r.energy_kwh)

    daily_labels = list(daily_dict.keys())
    daily_values = [round(v, 2) for v in daily_dict.values()]

    # Fallback to recent records if less than 2 distinct days
    if len(daily_labels) < 2:
        chart_records = list(reversed(recent_records))
        daily_labels = [r.recorded_at.strftime('%d %b %H:%M') for r in chart_records]
        daily_values = [float(r.energy_kwh) for r in chart_records]

    # 2. Weekly usage (last 6 weeks)
    weekly_dict = {}
    for r in records[:500]:
        week_str = f"Wk {r.recorded_at.isocalendar()[1]} ({r.recorded_at.strftime('%b')})"
        weekly_dict[week_str] = weekly_dict.get(week_str, 0.0) + float(r.energy_kwh)
    weekly_labels = list(reversed(list(weekly_dict.keys())[:6]))
    weekly_values = [round(weekly_dict[k], 2) for k in weekly_labels]

    # 3. Monthly usage
    monthly_dict = {}
    for r in records[:1000]:
        month_str = r.recorded_at.strftime('%b %Y')
        monthly_dict[month_str] = monthly_dict.get(month_str, 0.0) + float(r.energy_kwh)
    monthly_labels = list(reversed(list(monthly_dict.keys())[:6]))
    monthly_values = [round(monthly_dict[k], 2) for k in monthly_labels]

    context = {
        'total_consumption': round(total_consumption_float, 2),
        'total_records': total_records,
        'efficiency': efficiency_data,
        'waste': waste_data,
        'tomorrow_prediction': tomorrow_prediction,
        'carbon_emissions': carbon_emissions,
        'active_anomalies': active_anomalies[:3],
        'active_anomaly_count': active_anomaly_count,
        'recent_records': recent_records,
        # Multi-period chart data
        'chart_labels': daily_labels,
        'chart_values': daily_values,
        'weekly_labels': weekly_labels,
        'weekly_values': weekly_values,
        'monthly_labels': monthly_labels,
        'monthly_values': monthly_values,
        # Period breakdown for pie/doughnut chart
        'period_labels': list(waste_data['period_breakdown'].keys()),
        'period_values': list(waste_data['period_breakdown'].values())
    }

    return render(request, 'consumption/dashboard.html', context)


# ========================================================
# 2. ADD & MANAGE CONSUMPTION (Module 2)
# ========================================================

@login_required
def add_consumption(request):
    if request.method == 'POST':
        form = ElectricityConsumptionForm(request.POST)
        if form.is_valid():
            consumption = form.save(commit=False)
            consumption.user = request.user
            consumption.source = 'manual'
            consumption.save()

            # Automatic Anomaly Detection on newly added record
            anomaly_res = detect_single_anomaly(
                energy_kwh=consumption.energy_kwh,
                recorded_at=consumption.recorded_at,
                temperature=consumption.temperature,
                humidity=form.cleaned_data.get('humidity'),
                wind_speed=form.cleaned_data.get('wind_speed'),
                avg_past_consumption=form.cleaned_data.get('avg_past_consumption')
            )

            if anomaly_res['is_anomaly']:
                EnergyAnomaly.objects.create(
                    user=request.user,
                    consumption=consumption,
                    anomaly_score=anomaly_res['anomaly_score'],
                    description=anomaly_res['reason'],
                    is_resolved=False
                )
                messages.warning(
                    request,
                    f"Entry saved! ⚠️ AI Alert: Unusual electricity consumption detected ({consumption.energy_kwh} kWh). Reason: {anomaly_res['reason']}"
                )
            else:
                messages.success(request, f"Electricity consumption ({consumption.energy_kwh} kWh) recorded successfully!")

            return redirect('history')
    else:
        form = ElectricityConsumptionForm(initial={'recorded_at': timezone.now().strftime('%Y-%m-%dT%H:%M')})

    return render(request, 'consumption/add_consumption.html', {'form': form})


@login_required
def edit_consumption(request, pk):
    record = get_object_or_404(ElectricityConsumption, pk=pk, user=request.user)

    if request.method == 'POST':
        form = ElectricityConsumptionForm(request.POST, instance=record)
        if form.is_valid():
            form.save()
            messages.success(request, 'Consumption record updated successfully!')
            return redirect('history')
    else:
        form = ElectricityConsumptionForm(instance=record)

    return render(request, 'consumption/edit_consumption.html', {'form': form, 'record': record})


@login_required
@require_POST
def delete_consumption(request, pk):
    record = get_object_or_404(ElectricityConsumption, pk=pk, user=request.user)
    record.delete()
    messages.success(request, 'Consumption record deleted successfully!')
    return redirect('history')


@login_required
def history(request):
    query = request.GET.get('q', '').strip()
    source_filter = request.GET.get('source', '')
    anomaly_filter = request.GET.get('anomaly', '')

    records = ElectricityConsumption.objects.filter(user=request.user).order_by('-recorded_at')

    if source_filter:
        records = records.filter(source=source_filter)

    # Anomaly filter
    if anomaly_filter == 'yes':
        anomaly_ids = EnergyAnomaly.objects.filter(user=request.user).values_list('consumption_id', flat=True)
        records = records.filter(id__in=anomaly_ids)

    # Pagination
    paginator = Paginator(records, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Map anomalies for the current page
    current_page_ids = [r.id for r in page_obj]
    anomaly_map = {
        a.consumption_id: a
        for a in EnergyAnomaly.objects.filter(user=request.user, consumption_id__in=current_page_ids)
    }

    for r in page_obj:
        r.anomaly = anomaly_map.get(r.id)

    context = {
        'page_obj': page_obj,
        'total_records': paginator.count,
        'source_filter': source_filter,
        'anomaly_filter': anomaly_filter,
        'query': query
    }
    return render(request, 'consumption/history.html', context)


# ========================================================
# 3. ML CONSUMPTION PREDICTION (Module 4 & Sections 12.1-12.3)
# ========================================================

@login_required
def predictions_view(request):
    user = request.user
    forecast_data = forecast_user_consumption(user, days=7)
    comparison_data = get_ml_algorithms_comparison()

    simulation_result = None
    if request.method == 'POST':
        form = PredictionSimulatorForm(request.POST)
        if form.is_valid():
            cd = form.cleaned_data
            simulation_result = predict_custom_consumption(
                temperature=cd['temperature'],
                humidity=cd['humidity'],
                wind_speed=cd['wind_speed'],
                avg_past_consumption=cd['avg_past_consumption'],
                hour=cd['hour'],
                is_weekend=int(cd['is_weekend']),
                algorithm=cd['algorithm']
            )
    else:
        form = PredictionSimulatorForm()

    hourly = forecast_data['hourly_forecast']
    daily = forecast_data['daily_forecast']

    context = {
        'hourly_labels': [h['time'] for h in hourly],
        'hourly_values': [h['predicted_kwh'] for h in hourly],
        'daily_labels': [d['date'] for d in daily],
        'daily_values': [d['predicted_kwh'] for d in daily],
        'tomorrow_predicted_kwh': forecast_data['tomorrow_predicted_kwh'],
        'next_7_days_total_kwh': forecast_data['next_7_days_total_kwh'],
        'comparison_data': comparison_data,
        'form': form,
        'simulation_result': simulation_result
    }
    return render(request, 'consumption/predictions.html', context)


# ========================================================
# 4. ANOMALY DETECTION VIEW (Module 5 & Section 12.4)
# ========================================================

@login_required
def anomaly_detection_view(request):
    user = request.user

    # Handle on-demand scan action
    if request.GET.get('action') == 'scan':
        new_found = scan_user_anomalies(user)
        messages.success(request, f"Scan complete! {new_found} new anomalous consumption records identified.")
        return redirect('anomaly_detection')

    # User anomalies
    status_filter = request.GET.get('status', 'all')
    anomalies = EnergyAnomaly.objects.filter(user=user).select_related('consumption').order_by('-detected_at')

    if status_filter == 'active':
        anomalies = anomalies.filter(is_resolved=False)
    elif status_filter == 'resolved':
        anomalies = anomalies.filter(is_resolved=True)

    paginator = Paginator(anomalies, 15)
    page_obj = paginator.get_page(request.GET.get('page'))

    total_count = anomalies.count()
    active_count = EnergyAnomaly.objects.filter(user=user, is_resolved=False).count()
    resolved_count = EnergyAnomaly.objects.filter(user=user, is_resolved=True).count()

    context = {
        'page_obj': page_obj,
        'total_count': total_count,
        'active_count': active_count,
        'resolved_count': resolved_count,
        'status_filter': status_filter
    }
    return render(request, 'consumption/anomaly_detection.html', context)


@login_required
@require_POST
def toggle_anomaly_resolved(request, pk):
    anomaly = get_object_or_404(EnergyAnomaly, pk=pk, user=request.user)
    anomaly.is_resolved = not anomaly.is_resolved
    anomaly.save()
    status_str = "resolved" if anomaly.is_resolved else "reopened"
    messages.success(request, f"Anomaly marked as {status_str}.")
    return redirect('anomaly_detection')


# ========================================================
# 5. ENERGY WASTE ANALYSIS VIEW (Module 6 & Section 6.4)
# ========================================================

@login_required
def waste_analysis_view(request):
    user = request.user
    waste_data = analyze_energy_waste(user, days=30)
    efficiency_data = calculate_energy_efficiency_score(user)

    context = {
        'waste': waste_data,
        'efficiency': efficiency_data,
        'period_labels': list(waste_data['period_breakdown'].keys()),
        'period_values': list(waste_data['period_breakdown'].values())
    }
    return render(request, 'consumption/waste_analysis.html', context)


# ========================================================
# 6. RECOMMENDATIONS VIEW (Module 7 & Section 6.5)
# Includes Feature 04: Self-Learning Recommendation Engine
# ========================================================

@login_required
def recommendations_view(request):
    user = request.user
    data = generate_personalized_recommendations(user)
    learning_metrics = get_self_learning_metrics(user)

    context = {
        'recommendations': data['recommendations'],
        'total_potential_savings': data['total_potential_savings'],
        'completed_savings': data['completed_savings'],
        'financial_savings': data['financial_savings'],
        'schedule': data['schedule'],
        'learning_metrics': learning_metrics
    }
    return render(request, 'consumption/recommendations.html', context)


@login_required
@require_POST
def toggle_recommendation_completed(request, pk):
    rec = get_object_or_404(EnergyRecommendation, pk=pk, user=request.user)
    rec.is_completed = not rec.is_completed
    rec.save()
    status_str = "completed" if rec.is_completed else "active"
    messages.success(request, f"Recommendation '{rec.title}' marked as {status_str}!")
    return redirect('recommendations')


@login_required
@require_POST
def recommendation_feedback_view(request, pk):
    """
    Feature 04: Self-Learning Recommendation Engine with Feedback Loop
    Users can vote: 'helpful', 'already_done', or 'not_feasible'
    """
    feedback_type = request.POST.get('feedback_type', 'helpful')
    note = request.POST.get('note', '')

    feedback = record_user_feedback(request.user, pk, feedback_type, note)
    if feedback:
        label = dict(RecommendationFeedback.FEEDBACK_CHOICES).get(feedback_type, feedback_type)
        messages.success(request, f"Thank you! Feedback recorded: '{label}'. AI model adapted future priorities.")
    else:
        messages.error(request, "Unable to record feedback.")

    return redirect('recommendations')


# ========================================================
# ADVANCED FEATURES 01, 03, 06: DIGITAL TWIN & WHAT-IF SIMULATOR
# ========================================================

@login_required
def digital_twin_view(request):
    """
    Combines:
    - 01 AI Energy Digital Twin
    - 03 What-If Energy Simulator
    - 06 Future Lifestyle Impact Predictor
    """
    # Parse query or post parameters
    params = request.POST if request.method == 'POST' else request.GET

    solar_kw = float(params.get('solar_kw', 0.0) or 0.0)
    has_ev = params.get('has_ev', '0') in ['1', 'true', 'on', True]
    ev_charging_window = params.get('ev_charging_window', 'night')
    ac_upgrade = params.get('ac_upgrade', '0') in ['1', 'true', 'on', True]
    temp_setpoint_shift = int(params.get('temp_setpoint_shift', 0) or 0)
    shift_heavy_loads = params.get('shift_heavy_loads', '0') in ['1', 'true', 'on', True]
    baseload_cut = params.get('baseload_cut', '0') in ['1', 'true', 'on', True]

    twin_data = simulate_digital_twin(
        user=request.user,
        solar_kw=solar_kw,
        has_ev=has_ev,
        ev_charging_window=ev_charging_window,
        ac_upgrade=ac_upgrade,
        temp_setpoint_shift=temp_setpoint_shift,
        shift_heavy_loads=shift_heavy_loads,
        baseload_cut=baseload_cut
    )

    context = {
        'twin_data': twin_data,
        'hour_labels_json': json.dumps(twin_data['hour_labels']),
        'baseline_curve_json': json.dumps(twin_data['baseline_curve']),
        'simulated_curve_json': json.dumps(twin_data['simulated_curve']),
        'solar_curve_json': json.dumps(twin_data['solar_curve']),
        'ev_curve_json': json.dumps(twin_data['ev_curve']),
    }
    return render(request, 'consumption/digital_twin.html', context)


# ========================================================
# ADVANCED FEATURES 02 & 07: AI ENERGY WASTE DETECTIVE & XAI
# ========================================================

@login_required
def waste_detective_view(request):
    """
    Combines:
    - 02 AI Energy Waste Detective (Culprit disaggregation)
    - 07 Explainable AI (XAI) (Attribution weights & plain-English reasons)
    """
    anomaly_id = request.GET.get('anomaly_id')
    target_id = int(anomaly_id) if anomaly_id and anomaly_id.isdigit() else None

    detective_data = diagnose_waste_detective(request.user, target_anomaly_id=target_id)

    context = {
        'detective_data': detective_data,
        'selected_incident': detective_data['selected_incident'],
        'investigations': detective_data['investigations'],
    }
    return render(request, 'consumption/waste_detective.html', context)


# ========================================================
# ADVANCED FEATURE 05: PERSONAL ENERGY FINGERPRINT
# ========================================================

@login_required
def energy_fingerprint_view(request):
    """
    Feature 05: Personal Energy Fingerprint
    Generates unique behavioral archetype and radar chart metrics.
    """
    fingerprint_data = compute_energy_fingerprint(request.user)

    context = {
        'fingerprint': fingerprint_data,
        'radar_labels_json': json.dumps(fingerprint_data['radar_labels']),
        'user_radar_json': json.dumps(fingerprint_data['user_radar']),
        'benchmark_radar_json': json.dumps(fingerprint_data['benchmark_radar']),
        'ideal_radar_json': json.dumps(fingerprint_data.get('ideal_radar', [85, 90, 85, 80, 85])),
    }
    return render(request, 'consumption/energy_fingerprint.html', context)
    return redirect('recommendations')


# ========================================================
# 7. IMPORT DATA & SAMPLE DATASET (Modules 2 & 3)
# ========================================================

@login_required
def import_data_view(request):
    upload_summary = None

    if request.method == 'POST':
        if 'import_sample' in request.POST:
            # 1-Click sample dataset importer
            count = import_sample_dataset_for_user(request.user, sample_type='household', limit=168)
            scan_user_anomalies(request.user)
            messages.success(request, f"Successfully loaded {count} hourly household consumption records (UCI dataset) into your account! Anomalies scanned.")
            return redirect('dashboard')

        elif 'upload_csv' in request.POST:
            form = CSVUploadForm(request.POST, request.FILES)
            if form.is_valid():
                try:
                    summary = import_records_from_csv(request.FILES['csv_file'], request.user)
                    scan_user_anomalies(request.user)
                    upload_summary = summary
                    messages.success(
                        request,
                        f"CSV imported successfully! {summary['created_count']} records created, {summary['duplicates_removed']} duplicates removed, {summary['missing_values_handled']} values handled."
                    )
                except Exception as e:
                    messages.error(request, f"Error processing CSV: {str(e)}")
    else:
        form = CSVUploadForm()

    return render(request, 'consumption/import_data.html', {'form': form, 'summary': upload_summary})


# ========================================================
# 8. DATASET EXPLORER VIEW (Kaggle Smart Meter Data)
# ========================================================

@login_required
def dataset_view(request):
    dataset_path = Path(settings.BASE_DIR) / 'datasets' / 'smart_meter_data.csv'

    if not dataset_path.exists():
        return render(request, 'consumption/dataset.html', {
            'error': 'Dataset file was not found. Please check datasets folder.'
        })

    with open(dataset_path, 'r', newline='', encoding='utf-8-sig') as file:
        reader = csv.DictReader(file)
        columns = reader.fieldnames or []
        all_records = list(reader)

    total_records = len(all_records)
    normal_count = sum(1 for row in all_records if row.get('Anomaly_Label', '').strip().lower() == 'normal')
    abnormal_count = sum(1 for row in all_records if row.get('Anomaly_Label', '').strip().lower() == 'abnormal')

    table_records = [
        [record.get(col, '') for col in columns]
        for record in all_records
    ]

    paginator = Paginator(table_records, 20)
    page_obj = paginator.get_page(request.GET.get('page'))

    context = {
        'columns': columns,
        'page_obj': page_obj,
        'total_records': total_records,
        'normal_count': normal_count,
        'abnormal_count': abnormal_count,
    }
    return render(request, 'consumption/dataset.html', context)


# ========================================================
# 9. USER AUTHENTICATION (Module 1)
# ========================================================

def register(request):
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, f"Welcome to EnergySync, {user.username}! Your energy management account has been created.")
            return redirect('dashboard')
    else:
        form = RegisterForm()

    return render(request, 'registration/register.html', {'form': form})


def logout_view(request):
    logout(request)
    messages.info(request, "You have been logged out.")

    response = redirect('login')
    response['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'

    return response



# ========================================================
# 10. SETTINGS & SUPPORT
# ========================================================

@login_required
def settings_view(request):
    User = get_user_model()

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        email = request.POST.get('email', '').strip()

        if not username:
            messages.error(request, "Username cannot be empty.")

        elif User.objects.filter(username__iexact=username).exclude(pk=request.user.pk).exists():
            messages.error(request, "This username is already taken.")

        elif email and User.objects.filter(email__iexact=email).exclude(pk=request.user.pk).exists():
            messages.error(request, "This email is already in use.")

        else:
            request.user.username = username
            request.user.email = email
            request.user.save()

            messages.success(request, "Your profile has been updated successfully!")
            return redirect('settings')

    return render(request, 'consumption/settings.html')


@login_required
def support_view(request):
    return render(request, 'consumption/support.html')
