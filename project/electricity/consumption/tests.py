from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import AnonymousUser
from django.http import HttpResponse
from django.test import RequestFactory
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from .middleware import JWTAuthenticationMiddleware
from .models import ElectricityConsumption

User = get_user_model()


class JWTAuthenticationTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='jwt_user',
            email='jwt_user@example.com',
            password='StrongPassword123!',
        )
        self.other_user = User.objects.create_user(
            username='other_user',
            email='other@example.com',
            password='StrongPassword123!',
        )

    def _authenticate(self, access_token):
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access_token}')

    def test_register_returns_jwt_tokens(self):
        response = self.client.post(
            reverse('api_register'),
            {
                'username': 'new_jwt_user',
                'email': 'new_jwt@example.com',
                'password': 'StrongPassword123!',
                'password2': 'StrongPassword123!',
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)
        self.assertEqual(response.data['user']['username'], 'new_jwt_user')

    def test_login_obtains_jwt_tokens_and_rejects_bad_password(self):
        bad_resp = self.client.post(
            reverse('api_login'),
            {'username': 'jwt_user', 'password': 'WrongPassword'},
            format='json',
        )
        self.assertEqual(bad_resp.status_code, status.HTTP_401_UNAUTHORIZED)

        good_resp = self.client.post(
            reverse('api_login'),
            {'username': 'jwt_user', 'password': 'StrongPassword123!'},
            format='json',
        )
        self.assertEqual(good_resp.status_code, status.HTTP_200_OK)
        self.assertIn('access', good_resp.data)
        self.assertIn('refresh', good_resp.data)
        self.assertEqual(good_resp.data['user']['username'], 'jwt_user')

    def test_protected_endpoints_require_jwt(self):
        for route_name in (
            'api_profile',
            'api_dashboard',
            'api_consumption_list',
            'api_predictions',
            'api_anomalies',
            'api_waste_analysis',
            'api_recommendations',
        ):
            self.assertEqual(
                self.client.get(reverse(route_name)).status_code,
                status.HTTP_401_UNAUTHORIZED,
            )

    def test_profile_and_consumption_crud_with_jwt_and_user_isolation(self):
        other_record = ElectricityConsumption.objects.create(
            user=self.other_user,
            recorded_at=timezone.now(),
            energy_kwh='3.500',
        )

        login_resp = self.client.post(
            reverse('token_obtain_pair'),
            {'username': 'jwt_user', 'password': 'StrongPassword123!'},
            format='json',
        )
        self._authenticate(login_resp.data['access'])

        profile_resp = self.client.get(reverse('api_profile'))
        self.assertEqual(profile_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(profile_resp.data['username'], 'jwt_user')

        create_resp = self.client.post(
            reverse('api_consumption_list'),
            {
                'recorded_at': timezone.now().isoformat(),
                'energy_kwh': '1.750',
                'temperature': '26.50',
            },
            format='json',
        )
        self.assertEqual(create_resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(float(create_resp.data['energy_kwh']), 1.75)

        list_resp = self.client.get(reverse('api_consumption_list'))
        self.assertEqual(list_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(list_resp.data), 1)

        # User cannot access another user's consumption record
        other_detail = self.client.get(reverse('api_consumption_detail', args=[other_record.id]))
        self.assertEqual(other_detail.status_code, status.HTTP_404_NOT_FOUND)

    def test_protected_analytics_endpoints_with_jwt(self):
        ElectricityConsumption.objects.create(
            user=self.user,
            recorded_at=timezone.now(),
            energy_kwh='2.100',
            temperature='24.00',
        )
        login_resp = self.client.post(
            reverse('api_login'),
            {'username': 'jwt_user', 'password': 'StrongPassword123!'},
            format='json',
        )
        self._authenticate(login_resp.data['access'])

        dash_resp = self.client.get(reverse('api_dashboard'))
        self.assertEqual(dash_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(dash_resp.data['user'], 'jwt_user')
        self.assertEqual(dash_resp.data['total_records'], 1)

        pred_resp = self.client.get(reverse('api_predictions'))
        self.assertEqual(pred_resp.status_code, status.HTTP_200_OK)
        self.assertIn('daily_forecast', pred_resp.data)

        sim_resp = self.client.post(
            reverse('api_predictions'),
            {'hour': 19, 'temperature': 30.0, 'algorithm': 'random_forest'},
            format='json',
        )
        self.assertEqual(sim_resp.status_code, status.HTTP_200_OK)
        self.assertIn('predicted_kwh', sim_resp.data)

        anom_resp = self.client.get(reverse('api_anomalies'))
        self.assertEqual(anom_resp.status_code, status.HTTP_200_OK)
        self.assertIn('results', anom_resp.data)

        waste_resp = self.client.get(reverse('api_waste_analysis'))
        self.assertEqual(waste_resp.status_code, status.HTTP_200_OK)
        self.assertIn('waste', waste_resp.data)

        rec_resp = self.client.get(reverse('api_recommendations'))
        self.assertEqual(rec_resp.status_code, status.HTTP_200_OK)
        self.assertIn('recommendations', rec_resp.data)

    def test_refresh_verify_and_logout_blacklist(self):
        login_resp = self.client.post(
            reverse('api_login'),
            {'username': 'jwt_user', 'password': 'StrongPassword123!'},
            format='json',
        )
        access = login_resp.data['access']
        refresh = login_resp.data['refresh']

        verify_resp = self.client.post(
            reverse('api_token_verify'),
            {'token': access},
            format='json',
        )
        self.assertEqual(verify_resp.status_code, status.HTTP_200_OK)

        refresh_resp = self.client.post(
            reverse('api_token_refresh'),
            {'refresh': refresh},
            format='json',
        )
        self.assertEqual(refresh_resp.status_code, status.HTTP_200_OK)
        self.assertIn('access', refresh_resp.data)
        latest_refresh = refresh_resp.data.get('refresh', refresh)

        # Blacklist refresh token on logout
        self._authenticate(refresh_resp.data['access'])
        logout_resp = self.client.post(
            reverse('api_logout'),
            {'refresh': latest_refresh},
            format='json',
        )
        self.assertEqual(logout_resp.status_code, status.HTTP_200_OK)

        # Reusing blacklisted refresh token must fail
        reuse_resp = self.client.post(
            reverse('api_token_refresh'),
            {'refresh': latest_refresh},
            format='json',
        )
        self.assertEqual(reuse_resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_jwt_middleware_authenticates_standard_django_view(self):
        login_resp = self.client.post(
            reverse('api_login'),
            {'username': 'jwt_user', 'password': 'StrongPassword123!'},
            format='json',
        )
        access_token = login_resp.data['access']

        # Without JWT or session, standard @login_required dashboard redirects to login
        anon_resp = self.client.get(reverse('dashboard'))
        self.assertEqual(anon_resp.status_code, status.HTTP_302_FOUND)

        @login_required
        def protected_django_view(request):
            return HttpResponse(request.user.username)

        factory = RequestFactory()
        middleware = JWTAuthenticationMiddleware(protected_django_view)

        req_with_bearer = factory.get('/', HTTP_AUTHORIZATION=f'Bearer {access_token}')
        req_with_bearer.user = AnonymousUser()
        resp_bearer = middleware(req_with_bearer)
        self.assertEqual(resp_bearer.status_code, 200)
        self.assertEqual(resp_bearer.content.decode(), 'jwt_user')

        req_with_cookie = factory.get('/')
        req_with_cookie.user = AnonymousUser()
        req_with_cookie.COOKIES['access_token'] = access_token
        resp_cookie = middleware(req_with_cookie)
        self.assertEqual(resp_cookie.status_code, 200)
        self.assertEqual(resp_cookie.content.decode(), 'jwt_user')
