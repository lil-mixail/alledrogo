#!/bin/bash
# User data do launch template. Uzupelnic wartosci <...> przed zapisaniem template.
# Zadnych hasel tutaj nie ma - aplikacja pobiera je sama z Secrets Manager przez role IAM.
cat > /etc/alledrogo.env <<'ENV'
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=www.alledroogo.pl,alledroogo.pl,.elb.amazonaws.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://www.alledroogo.pl,https://alledroogo.pl
DJANGO_TRUSTED_PROXY_COUNT=1
AWS_REGION=eu-north-1
AWS_SECRET_ID=alledrogo/app
DB_SECRET_ID=<ARN sekretu RDS>
DB_HOST=<endpoint RDS, np. alledrogo-db.xxxx.eu-north-1.rds.amazonaws.com>
DB_NAME=alledrogo
AWS_STORAGE_BUCKET_NAME=<nazwa bucketa S3>
ENV
chmod 600 /etc/alledrogo.env
systemctl enable --now alledrogo
