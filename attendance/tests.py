from django.test import TestCase
from .models import CustomUser, LeaveBalance, LeaveRequest, TripRequest

class CustomUserModelTest(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username='testuser',
            password='testpassword',
            department='IT',
            position='Developer',
            join_date='2023-01-01'
        )

    def test_user_creation(self):
        self.assertEqual(self.user.username, 'testuser')
        self.assertEqual(self.user.department, 'IT')
        self.assertEqual(self.user.position, 'Developer')
        self.assertIsNotNone(self.user.join_date)

class LeaveBalanceModelTest(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username='testuser',
            password='testpassword'
        )
        self.leave_balance = LeaveBalance.objects.create(
            user=self.user,
            total_leave=30.0,
            used_leave=5.0
        )

    def test_remaining_leave(self):
        self.assertEqual(self.leave_balance.remaining_leave, 25.0)

class LeaveRequestModelTest(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username='testuser',
            password='testpassword'
        )
        self.leave_request = LeaveRequest.objects.create(
            user=self.user,
            start_date='2023-01-10',
            end_date='2023-01-15',
            leave_type='annual',
            reason='Family vacation',
            status='대기'
        )

    def test_leave_request_status(self):
        self.assertEqual(self.leave_request.status, '대기')

class TripRequestModelTest(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username='testuser',
            password='testpassword'
        )
        self.trip_request = TripRequest.objects.create(
            user=self.user,
            start_date='2023-02-01',
            end_date='2023-02-05',
            location='Seoul',
            purpose='Business meeting'
        )

    def test_trip_request_location(self):
        self.assertEqual(self.trip_request.location, 'Seoul')