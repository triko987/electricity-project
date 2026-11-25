from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import ElectricityConsumption, EnergyAnomaly, EnergyRecommendation

User = get_user_model()


class UserProfileSerializer(serializers.ModelSerializer):
    """Serializer for exposing and updating authenticated user profile fields."""

    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'date_joined', 'last_login')
        read_only_fields = ('id', 'date_joined', 'last_login')

    def validate_username(self, value):
        cleaned = value.strip()
        if not cleaned:
            raise serializers.ValidationError('Username cannot be empty.')
        qs = User.objects.filter(username__iexact=cleaned)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError('This username is already taken.')
        return cleaned

    def validate_email(self, value):
        cleaned = value.strip()
        if cleaned:
            qs = User.objects.filter(email__iexact=cleaned)
            if self.instance is not None:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError('This email is already in use.')
        return cleaned


class RegisterSerializer(serializers.ModelSerializer):
    """Serializer for creating a new user account with validated credentials."""

    email = serializers.EmailField(required=True)
    password = serializers.CharField(write_only=True, required=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = User
        fields = ('username', 'email', 'password', 'password2')

    def validate_username(self, value):
        cleaned = value.strip()
        if User.objects.filter(username__iexact=cleaned).exists():
            raise serializers.ValidationError('A user with this username already exists.')
        return cleaned

    def validate_email(self, value):
        cleaned = value.strip()
        if User.objects.filter(email__iexact=cleaned).exists():
            raise serializers.ValidationError('A user with this email already exists.')
        return cleaned

    def validate(self, attrs):
        password2 = attrs.get('password2')
        if password2 is not None and attrs['password'] != password2:
            raise serializers.ValidationError({'password2': 'Password fields did not match.'})
        return attrs

    def create(self, validated_data):
        validated_data.pop('password2', None)
        return User.objects.create_user(
            username=validated_data['username'],
            email=validated_data['email'],
            password=validated_data['password'],
        )


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """JWT token pair serializer adding user claims and returning user metadata."""

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['username'] = user.username
        token['email'] = user.email
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        data['user'] = {
            'id': self.user.id,
            'username': self.user.username,
            'email': self.user.email,
        }
        return data


class ElectricityConsumptionSerializer(serializers.ModelSerializer):
    """Serializer for user electricity consumption readings."""

    humidity = serializers.FloatField(required=False, write_only=True, min_value=0, max_value=100)
    wind_speed = serializers.FloatField(required=False, write_only=True, min_value=0)
    avg_past_consumption = serializers.FloatField(required=False, write_only=True, min_value=0)

    class Meta:
        model = ElectricityConsumption
        fields = (
            'id',
            'recorded_at',
            'energy_kwh',
            'temperature',
            'source',
            'created_at',
            'humidity',
            'wind_speed',
            'avg_past_consumption',
        )
        read_only_fields = ('id', 'source', 'created_at')


class EnergyAnomalySerializer(serializers.ModelSerializer):
    """Serializer for detected electricity consumption anomalies."""

    energy_kwh = serializers.DecimalField(
        source='consumption.energy_kwh',
        max_digits=10,
        decimal_places=3,
        read_only=True,
    )
    recorded_at = serializers.DateTimeField(source='consumption.recorded_at', read_only=True)

    class Meta:
        model = EnergyAnomaly
        fields = (
            'id',
            'consumption',
            'energy_kwh',
            'recorded_at',
            'anomaly_score',
            'description',
            'detected_at',
            'is_resolved',
        )
        read_only_fields = fields


class EnergyRecommendationSerializer(serializers.ModelSerializer):
    """Serializer for personalized energy-saving recommendations."""

    class Meta:
        model = EnergyRecommendation
        fields = (
            'id',
            'title',
            'description',
            'estimated_saving_kwh',
            'is_completed',
            'feedback_status',
            'priority_weight',
            'created_at',
        )
        read_only_fields = fields


class PredictionSimulatorSerializer(serializers.Serializer):
    """Input validator for custom ML consumption simulation via API."""

    algorithm = serializers.ChoiceField(
        choices=[('random_forest', 'Random Forest'), ('linear_regression', 'Linear Regression')],
        default='random_forest',
    )
    hour = serializers.IntegerField(min_value=0, max_value=23, default=14)
    temperature = serializers.FloatField(default=25.0)
    humidity = serializers.FloatField(min_value=0, max_value=100, default=50.0)
    wind_speed = serializers.FloatField(min_value=0, default=5.0)
    avg_past_consumption = serializers.FloatField(min_value=0, default=1.5)
    is_weekend = serializers.IntegerField(min_value=0, max_value=1, default=0)
