from django.urls import path, reverse_lazy
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    # Dashboard (Overview & Analytics)
    path('', views.dashboard, name='dashboard'),

    # Data Collection & Management
    path('add/', views.add_consumption, name='add_consumption'),
    path('history/', views.history, name='history'),
    path('edit/<int:pk>/', views.edit_consumption, name='edit_consumption'),
    path('delete/<int:pk>/', views.delete_consumption, name='delete_consumption'),
    path('import-data/', views.import_data_view, name='import_data'),

    # ML Consumption Prediction & Forecasting
    path('predictions/', views.predictions_view, name='predictions'),

    # Anomaly Detection
    path('anomaly-detection/', views.anomaly_detection_view, name='anomaly_detection'),
    path('anomaly-detection/<int:pk>/toggle/', views.toggle_anomaly_resolved, name='toggle_anomaly_resolved'),

    # Energy Waste Analysis
    path('waste-analysis/', views.waste_analysis_view, name='waste_analysis'),

    # Energy-Saving Recommendations & Self-Learning Feedback (Feature 04)
    path('recommendations/', views.recommendations_view, name='recommendations'),
    path('recommendations/<int:pk>/toggle/', views.toggle_recommendation_completed, name='toggle_recommendation_completed'),
    path('recommendations/<int:pk>/feedback/', views.recommendation_feedback_view, name='recommendation_feedback'),

    # Advanced AI Features (Features 01, 02, 03, 05, 06, 07)
    path('digital-twin/', views.digital_twin_view, name='digital_twin'),
    path('waste-detective/', views.waste_detective_view, name='waste_detective'),
    path('energy-fingerprint/', views.energy_fingerprint_view, name='energy_fingerprint'),

    # Smart Meter Dataset Explorer
    path('dataset/', views.dataset_view, name='dataset'),

    # Settings & Support
    path('settings/', views.settings_view, name='settings'),
    path('support/', views.support_view, name='support'),

# Forgot Password
path(
    'forgot-password/',
    auth_views.PasswordResetView.as_view(
        template_name='consumption/password_reset.html',
        email_template_name='consumption/password_reset_email.html',
        subject_template_name='consumption/password_reset_subject.txt',
        success_url=reverse_lazy('energysync_password_reset_done')
    ),
   name='energysync_password_reset'
),

path(
    'forgot-password/sent/',
    auth_views.PasswordResetDoneView.as_view(
        template_name='consumption/password_reset_done.html'
    ),
    name='energysync_password_reset_done'
),

path(
    'reset/<uidb64>/<token>/',
    auth_views.PasswordResetConfirmView.as_view(
        template_name='consumption/password_reset_confirm.html',
        success_url=reverse_lazy('energysync_password_reset_complete')
    ),
    name='energysync_password_reset_confirm'
),

path(
    'reset/complete/',
    auth_views.PasswordResetCompleteView.as_view(
        template_name='consumption/password_reset_complete.html'
    ),
    name='energysync_password_reset_complete'
),

    path(
    'settings/password/',
    auth_views.PasswordChangeView.as_view(
        template_name='consumption/password_change.html',
        success_url='/settings/password/done/'
    ),
    name='password_change'
),

path(
    'settings/password/done/',
    auth_views.PasswordChangeDoneView.as_view(
        template_name='consumption/password_change_done.html'
    ),
    name='password_change_done'
),


    # Authentication
    path(
        'login/',
        auth_views.LoginView.as_view(
            template_name='registration/login.html',
            redirect_authenticated_user=True
        ),
        name='login'
    ),
    path('register/', views.register, name='register'),
    path('logout/', views.logout_view, name='logout'),
]
