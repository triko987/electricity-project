from decimal import Decimal
from django.db.models import Sum
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from .efficiency_score import calculate_energy_efficiency_score
from .ml_service import (
    detect_single_anomaly,
    forecast_user_consumption,
    get_ml_algorithms_comparison,
    predict_custom_consumption,
    scan_user_anomalies,
)
from .models import ElectricityConsumption, EnergyAnomaly
from .recommendations import generate_personalized_recommendations
from .serializers import (
    CustomTokenObtainPairSerializer,
    ElectricityConsumptionSerializer,
    EnergyAnomalySerializer,
    EnergyRecommendationSerializer,
    PredictionSimulatorSerializer,
    RegisterSerializer,
    UserProfileSerializer,
)
from .waste_analysis import analyze_energy_waste


class RegisterAPIView(APIView):
    """Register a new user and issue an initial JWT access/refresh token pair."""

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        refresh = RefreshToken.for_user(user)
        refresh['username'] = user.username
        refresh['email'] = user.email

        return Response(
            {
                'user': UserProfileSerializer(user).data,
                'refresh': str(refresh),
                'access': str(refresh.access_token),
            },
            status=status.HTTP_201_CREATED,
        )


class CustomTokenObtainPairView(TokenObtainPairView):
    """Authenticate credentials and return JWT access/refresh tokens with user metadata."""

    permission_classes = [AllowAny]
    serializer_class = CustomTokenObtainPairSerializer


class LogoutAPIView(APIView):
    """Blacklist the provided refresh token to log out a JWT session."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh_token = request.data.get('refresh')
        if not refresh_token:
            return Response(
                {'detail': 'Refresh token is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
        except TokenError:
            return Response(
                {'detail': 'Invalid or expired refresh token.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {'detail': 'Successfully logged out.'},
            status=status.HTTP_200_OK,
        )


class ProfileAPIView(APIView):
    """Retrieve or update the authenticated user's profile."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserProfileSerializer(request.user).data)

    def patch(self, request):
        serializer = UserProfileSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class DashboardSummaryAPIView(APIView):
    """Return JWT-protected analytics summary for the authenticated user's dashboard."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        records = ElectricityConsumption.objects.filter(user=user)
        total_records = records.count()
        total_consumption = records.aggregate(total=Sum('energy_kwh'))['total'] or Decimal('0.000')
        total_consumption_float = round(float(total_consumption), 2)

        efficiency = calculate_energy_efficiency_score(user)
        waste = analyze_energy_waste(user)
        forecast = forecast_user_consumption(user, days=7)
        active_anomaly_count = EnergyAnomaly.objects.filter(user=user, is_resolved=False).count()

        return Response(
            {
                'user': request.user.username,
                'total_consumption_kwh': total_consumption_float,
                'total_records': total_records,
                'carbon_emissions_kg': round(total_consumption_float * 0.82, 2),
                'tomorrow_prediction_kwh': forecast.get('tomorrow_predicted_kwh', 0.0),
                'active_anomaly_count': active_anomaly_count,
                'efficiency': efficiency,
                'waste': waste,
            }
        )


class ConsumptionListCreateAPIView(generics.ListCreateAPIView):
    """List or create electricity consumption records for the authenticated user."""

    permission_classes = [IsAuthenticated]
    serializer_class = ElectricityConsumptionSerializer

    def get_queryset(self):
        qs = ElectricityConsumption.objects.filter(user=self.request.user).order_by('-recorded_at')
        source_filter = self.request.query_params.get('source')
        if source_filter:
            qs = qs.filter(source=source_filter)
        return qs

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        extra_fields = {}
        for field in ('humidity', 'wind_speed', 'avg_past_consumption'):
            if field in serializer.validated_data:
                extra_fields[field] = serializer.validated_data.pop(field)

        consumption = serializer.save(user=request.user, source='manual')

        anomaly_res = detect_single_anomaly(
            energy_kwh=consumption.energy_kwh,
            recorded_at=consumption.recorded_at,
            temperature=consumption.temperature,
            humidity=extra_fields.get('humidity'),
            wind_speed=extra_fields.get('wind_speed'),
            avg_past_consumption=extra_fields.get('avg_past_consumption'),
        )

        if anomaly_res['is_anomaly']:
            EnergyAnomaly.objects.create(
                user=request.user,
                consumption=consumption,
                anomaly_score=anomaly_res['anomaly_score'],
                description=anomaly_res['reason'],
                is_resolved=False,
            )

        response_data = self.get_serializer(consumption).data
        response_data['anomaly_check'] = anomaly_res
        return Response(response_data, status=status.HTTP_201_CREATED)


class ConsumptionDetailAPIView(generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, update, or delete a single consumption record owned by the user."""

    permission_classes = [IsAuthenticated]
    serializer_class = ElectricityConsumptionSerializer

    def get_queryset(self):
        return ElectricityConsumption.objects.filter(user=self.request.user)


class PredictionsAPIView(APIView):
    """Retrieve 24h/7d forecasts or simulate custom scenarios via ML models."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        forecast_data = forecast_user_consumption(request.user, days=7)
        return Response(
            {
                'hourly_forecast': [
                    {
                        'time': item['time'],
                        'timestamp': item['timestamp'].isoformat(),
                        'predicted_kwh': item['predicted_kwh'],
                    }
                    for item in forecast_data['hourly_forecast']
                ],
                'daily_forecast': [
                    {
                        'date': item['date'],
                        'iso_date': item['date_obj'].isoformat(),
                        'predicted_kwh': item['predicted_kwh'],
                        'algorithm': item['algorithm'],
                    }
                    for item in forecast_data['daily_forecast']
                ],
                'tomorrow_predicted_kwh': forecast_data['tomorrow_predicted_kwh'],
                'next_7_days_total_kwh': forecast_data['next_7_days_total_kwh'],
                'algorithms_comparison': get_ml_algorithms_comparison(),
            }
        )

    def post(self, request):
        serializer = PredictionSimulatorSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cd = serializer.validated_data
        result = predict_custom_consumption(
            temperature=cd['temperature'],
            humidity=cd['humidity'],
            wind_speed=cd['wind_speed'],
            avg_past_consumption=cd['avg_past_consumption'],
            hour=cd['hour'],
            is_weekend=cd['is_weekend'],
            algorithm=cd['algorithm'],
        )
        return Response(result)


class AnomaliesListAPIView(APIView):
    """List user anomalies and optionally trigger an on-demand ML anomaly scan."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        new_found = 0
        if request.query_params.get('scan') in ('1', 'true', 'yes'):
            new_found = scan_user_anomalies(request.user)

        anomalies = EnergyAnomaly.objects.filter(user=request.user).select_related('consumption').order_by('-detected_at')
        status_filter = request.query_params.get('status')
        if status_filter == 'active':
            anomalies = anomalies.filter(is_resolved=False)
        elif status_filter == 'resolved':
            anomalies = anomalies.filter(is_resolved=True)

        return Response(
            {
                'new_anomalies_found': new_found,
                'count': anomalies.count(),
                'results': EnergyAnomalySerializer(anomalies, many=True).data,
            }
        )


class ToggleAnomalyAPIView(APIView):
    """Toggle resolved status of a user-owned energy anomaly."""

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        anomaly = get_object_or_404(EnergyAnomaly, pk=pk, user=request.user)
        anomaly.is_resolved = not anomaly.is_resolved
        anomaly.save()
        return Response(EnergyAnomalySerializer(anomaly).data)


class WasteAnalysisAPIView(APIView):
    """Return energy waste disaggregation and efficiency score for the authenticated user."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        days = int(request.query_params.get('days', 30))
        return Response(
            {
                'waste': analyze_energy_waste(request.user, days=days),
                'efficiency': calculate_energy_efficiency_score(request.user, days=days),
            }
        )


class RecommendationsAPIView(APIView):
    """Return personalized recommendations and optimal appliance operating schedule."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        data = generate_personalized_recommendations(request.user)
        return Response(
            {
                'recommendations': EnergyRecommendationSerializer(data['recommendations'], many=True).data,
                'total_potential_savings': data['total_potential_savings'],
                'completed_savings': data['completed_savings'],
                'financial_savings': data['financial_savings'],
                'schedule': data['schedule'],
            }
        )
