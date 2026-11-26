from django.test import TestCase


class CiDemoTest(TestCase):
    def test_celowo_czerwony(self):
        # celowo bledny test, zeby pokazac, ze CI blokuje merge
        self.assertEqual(1, 2)
