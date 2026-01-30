from django.urls import reverse
from rest_framework.test import APIClient
from django.test import TestCase
from accounts.models import User
from .models import PaymentIntent


class PaymentFlowTest(TestCase):
    def setUp(self):
        self.user = User.objects.create(username="tester")
        self.client = APIClient()

    def test_fake_payment_flow(self):
        intent = PaymentIntent.objects.create(user=self.user, amount=10000, gateway="fake")
        url = reverse("payments:start", args=[intent.public_id])
        res = self.client.post(url, {"gateway": "fake"}, format="json")
        self.assertEqual(res.status_code, 200)
        intent.refresh_from_db()
        self.assertEqual(intent.status, "paid")
        self.assertTrue(intent.ref_id.startswith("FAKE-"))
        self.assertEqual(res.data["gateway"], "fake")

    def test_free_payment_flow(self):
        intent = PaymentIntent.objects.create(user=self.user, amount=0, gateway="sadad")
        url = reverse("payments:start", args=[intent.public_id])
        res = self.client.post(url, {"gateway": "sadad"}, format="json")
        self.assertEqual(res.status_code, 200)
        intent.refresh_from_db()
        self.assertEqual(intent.status, "paid")
        self.assertEqual(res.data["gateway"], "free")
