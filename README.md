# Alledrogo

Projekt na laby z BSiAW (PWr, grupa 4). Prosty sklep internetowy w stylu Allegro.

Django + PostgreSQL + Tailwind. Potem wrzucamy to na AWS.

## Kto co robi

- osoba 1 - konta, logowanie, role, wygląd strony (`accounts`, `core`, `config`)
- osoba 2 - produkty, komentarze, czat (`products`)
- osoba 3 - koszyk, zamówienia, Stripe (`orders`)

## Jak odpalić

Trzeba mieć Pythona, Gita i Docker Desktop.

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
docker compose up -d
python manage.py migrate
python manage.py seed_demo_users
python manage.py runserver
```

Strona: http://127.0.0.1:8000, admin: http://127.0.0.1:8000/admin/

Jak `python` nie działa to zamiast niego `py`.
W `.env` ma być `127.0.0.1`, nie `localhost`, bo inaczej na Windowsie baza się wiesza.

Nieopłacone zamówienia są anulowane po godzinie (`ORDER_PAYMENT_TIMEOUT_MINUTES` w `.env`), a towar wraca na magazyn.
Lokalnie robi to samo middleware przy ruchu na stronie. Na AWS warto dodać cron co 5 minut:
`python manage.py cancel_expired_orders`.

## Konta testowe

Hasło do wszystkich: `Alledrogo!2026`

- `admin` - administrator
- `moderator` - moderator
- `sprzedawca` - sprzedawca
- `klient` - zwykły klient

## Role w kodzie

```python
from accounts.permissions import seller_required

@seller_required
def dodaj_produkt(request):
    ...
```

Jest też `moderator_required` i `admin_required`. W szablonach: `{% if user.is_seller %}`.

Jak robicie model z użytkownikiem to `settings.AUTH_USER_MODEL`, nie `User` z django.

## Zasady

- nie commitujemy do `main`, każdy robi swój branch i potem pull request
- przed pull requestem `python manage.py test`
- po zmianie modeli `makemigrations` i commit migracji
- wszystko co coś zmienia (dodaj, usuń, zapłać) przez formularz POST z `{% csrf_token %}`, nie przez link
- `.env` nie idzie do repo

## Co jest zabezpieczone

- hasła min. 10 znaków, nie mogą być popularne
- nie da się zarejestrować jako admin
- blokada na 15 min: 5 złych haseł na jeden login z jednego IP albo 20 z jednego IP na różne loginy
- każde logowanie zapisuje się w bazie (IP, przeglądarka), widać w adminie i w profilu
- sesja trwa max 2h, cookie HttpOnly, wylogowanie tylko POST
- IP brane z ostatniego wpisu X-Forwarded-For, żeby nie dało się go podrobić (na AWS ustawić `DJANGO_TRUSTED_PROXY_COUNT=1`)
- na produkcji (DEBUG=False): HTTPS, HSTS, secure cookies

## Testy

```
python manage.py test
```
