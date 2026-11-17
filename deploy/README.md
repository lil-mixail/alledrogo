# wdrozenie na AWS (czesc 2: AMI, IAM, launch template, TG, ASG)

region: eu-north-1. Najpierw musi byc gotowe to od osoby 1: VPC, sg-app, sg-db, RDS i sekret.

## 1. S3 na zdjecia
- S3 -> Create bucket, np. `alledrogo-media-<cos losowego>`, region eu-north-1
- Block all public access: zostawic WLACZONE (zdjecia ida przez podpisane linki)

## 2. sekret aplikacji
Secrets Manager -> Store a new secret -> Other type, nazwa `alledrogo/app`, klucze:
- `DJANGO_SECRET_KEY` - wygenerowac: `python -c "import secrets; print(secrets.token_urlsafe(50))"`
- `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`

Haslo do bazy jest w osobnym sekrecie, ktory tworzy samo RDS (opcja "Manage master credentials in AWS Secrets Manager"). Przy tworzeniu RDS ustawic "Initial database name" = `alledrogo`.

## 3. rola IAM dla serwerow
IAM -> Roles -> Create role -> EC2, nazwa `alledrogo-ec2`:
- polityka `AmazonSSMManagedInstanceCore` (Session Manager zamiast SSH)
- wlasna polityka z `deploy/iam_policy.json` (podmienic <...>)

## 4. AMI z aplikacja
1. odpalic tymczasowa EC2: Amazon Linux 2023, t3.micro, rola `alledrogo-ec2`, podsiec z dostepem do internetu
2. wejsc przez Session Manager i:
   ```
   cd ~
   sudo dnf install -y git
   git clone https://github.com/lil-mixail/alledrogo.git
   sudo bash alledrogo/deploy/build_ami.sh
   ```
   repo jest prywatne -> git zapyta o login i token (GitHub -> Settings -> Developer settings -> Fine-grained token, tylko odczyt tego repo). Skrypt na koncu kasuje klona, wiec tokena nie ma w obrazie
3. EC2 -> Actions -> Image and templates -> Create image, nazwa `alledrogo-v1`
4. tymczasowa instancje USUNAC

## 5. launch template
- AMI: `alledrogo-v1`, typ t3.micro, bez key pair
- security group: `sg-app`
- IAM instance profile: `alledrogo-ec2`
- Advanced -> User data: zawartosc `deploy/user_data.sh` z uzupelnionymi <...>

## 6. target group
- typ Instances, HTTP, port **8000**
- health check: HTTP, sciezka `/health/`, healthy 5, unhealthy 2, interval 30 s, kod 200

## 7. Auto Scaling Group
- launch template z pkt 5, podsieci w 2 strefach
- podpiac pod target group z pkt 6, wlaczyc ELB health checks
- min 2, max 4, desired 2, target tracking: CPU 50%

## sprawdzenie
- Target group -> Targets: oba serwery `healthy`
- adres ALB w przegladarce -> strona glowna. Dopoki nie ma listenera 443 z certyfikatem, dopisac w user data `DJANGO_SECURE_SSL_REDIRECT=False`, inaczej Django przekieruje na https, ktore jeszcze nie dziala
- jak `unhealthy`: Session Manager na serwer i `sudo journalctl -u alledrogo -n 50`

## pierwsze konto admina
Session Manager na dowolny serwer:
```
sudo bash -c 'set -a; . /etc/alledrogo.env; set +a; cd /opt/alledrogo/app; /opt/alledrogo/venv/bin/python manage.py createsuperuser'
```
(seed_demo_users na produkcji nie dziala, celowo)

## koszty
po labach: ASG desired/min = 0, RDS stop (sam wstaje po 7 dniach!), NAT Gateway usunac
