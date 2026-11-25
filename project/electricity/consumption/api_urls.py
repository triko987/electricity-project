from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView, TokenVerifyView

from . import api_views

urlpatterns = [
    # JWT Authentication Endpoints
    path('auth/register/', api_views.RegisterAPIView.as_view(), name='api_register'),
    path('auth/login/', api_views.CustomTokenObtainPairView.as_view(), name='api_login'),
    path('auth/refresh/', TokenRefreshView.as_view(), name='api_token_refresh'),
    path('auth/verify/', TokenVerifyView.as_view(), name='api_token_verify'),
    path('auth/logout/', api_views.LogoutAPIView.as_view(), name='api_logout'),
    path('auth/me/', api_views.ProfileAPIView.as_view(), name='api_profile'),

    # Standard SimpleJWT Token Endpoints (aliases)
    path('token/', api_views.CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('token/verify/', TokenVerifyView.as_view(), name='token_verify'),

    # JWT-Protected EnergySync API Endpoints
    path('dashboard/', api_views.DashboardSummaryAPIView.as_view(), name='api_dashboard'),
    path('consumption/', api_views.ConsumptionListCreateAPIView.as_view(), name='api_consumption_list'),
    path('consumption/<int:pk>/', api_views.ConsumptionDetailAPIView.as_view(), name='api_consumption_detail'),
    path('predictions/', api_views.PredictionsAPIView.as_view(), name='api_predictions'),
    path('anomalies/', api_views.AnomaliesListAPIView.as_view(), name='api_anomalies'),
    path('anomalies/<int:pk>/toggle/', api_views.ToggleAnomalyAPIView.as_view(), name='api_anomaly_toggle'),
    path('waste-analysis/', api_views.WasteAnalysisAPIView.as_view(), name='api_waste_analysis'),
    path('recommendations/', api_views.RecommendationsAPIView.as_view(), name='api_recommendations'),
]
