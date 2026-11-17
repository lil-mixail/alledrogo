from django.test import TestCase, override_settings


class HealthCheckTests(TestCase):
    @override_settings(DEBUG=False, SECURE_SSL_REDIRECT=True, ALLOWED_HOSTS=["www.alledroogo.pl"])
    def test_health_ok_for_alb(self):
        # ALB pyta po HTTP na prywatne IP - nie moze byc 400 ani przekierowania na https
        resp = self.client.get("/health/", HTTP_HOST="10.0.1.23:8000")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.content, b"ok")

    @override_settings(DEBUG=False, SECURE_SSL_REDIRECT=True, ALLOWED_HOSTS=["www.alledroogo.pl"])
    def test_other_pages_still_protected(self):
        resp = self.client.get("/", HTTP_HOST="10.0.1.23:8000")
        self.assertEqual(resp.status_code, 400)
