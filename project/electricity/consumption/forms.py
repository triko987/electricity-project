from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import get_user_model
from .models import ElectricityConsumption

class ElectricityConsumptionForm(forms.ModelForm):

    humidity = forms.FloatField(
        required=False,
        min_value=0,
        max_value=100,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'step': '0.01',
            'placeholder': 'Enter humidity (%)'
        })
    )

    wind_speed = forms.FloatField(
        required=False,
        min_value=0,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'step': '0.01',
            'placeholder': 'Enter wind speed (km/h)'
        })
    )

    avg_past_consumption = forms.FloatField(
        required=False,
        min_value=0,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'step': '0.001',
            'placeholder': 'Enter average past consumption (kWh)'
        })
    )

    class Meta:
        model = ElectricityConsumption
        fields = [
            'recorded_at',
            'energy_kwh',
            'temperature',
        ]
        widgets = {
            'recorded_at': forms.DateTimeInput(
                format='%Y-%m-%dT%H:%M',
                attrs={
                    'type': 'datetime-local',
                    'class': 'form-control'
                }
            ),
            'energy_kwh': forms.NumberInput(
                attrs={
                    'class': 'form-control',
                    'step': '0.001',
                    'min': '0',
                    'placeholder': 'e.g. 1.450'
                }
            ),
            'temperature': forms.NumberInput(
                attrs={
                    'class': 'form-control',
                    'step': '0.01',
                    'placeholder': 'e.g. 24.5'
                }
            ),
        }
        input_formats = ['%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M']


class CSVUploadForm(forms.Form):
    csv_file = forms.FileField(
        label='Select CSV File',
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': '.csv'
        }),
        help_text='File should include date/time and electricity consumption (kWh) columns.'
    )


class PredictionSimulatorForm(forms.Form):
    ALGORITHM_CHOICES = [
        ('random_forest', 'Random Forest Regressor (Recommended)'),
        ('linear_regression', 'Linear Regression'),
    ]

    algorithm = forms.ChoiceField(
        choices=ALGORITHM_CHOICES,
        initial='random_forest',
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    hour = forms.IntegerField(
        min_value=0,
        max_value=23,
        initial=14,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '0 - 23'})
    )

    temperature = forms.FloatField(
        initial=25.0,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1', 'placeholder': '°C'})
    )

    humidity = forms.FloatField(
        min_value=0,
        max_value=100,
        initial=50.0,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.5', 'placeholder': '%'})
    )

    wind_speed = forms.FloatField(
        min_value=0,
        initial=5.0,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.5', 'placeholder': 'km/h'})
    )

    avg_past_consumption = forms.FloatField(
        min_value=0,
        initial=1.5,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.05', 'placeholder': 'kWh'})
    )

    is_weekend = forms.ChoiceField(
        choices=[(0, 'Weekday (Mon - Fri)'), (1, 'Weekend (Sat - Sun)')],
        initial=0,
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    
class RegisterForm(UserCreationForm):

    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your Gmail address'
        })
    )

    class Meta:
        model = get_user_model()
        fields = ('username', 'email', 'password1', 'password2')