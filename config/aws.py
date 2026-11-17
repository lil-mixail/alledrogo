import json
import os
from urllib.parse import quote


def _get_secret(client, secret_id):
    return json.loads(client.get_secret_value(SecretId=secret_id)["SecretString"])


def load_secrets():
    # na AWS hasla sa w Secrets Manager, serwer ma do nich dostep przez role IAM
    # lokalnie te zmienne nie sa ustawione i nic sie nie dzieje
    app_secret = os.getenv("AWS_SECRET_ID")   # nasz sekret: DJANGO_SECRET_KEY, STRIPE_... itd.
    db_secret = os.getenv("DB_SECRET_ID")     # sekret z haslem do RDS (tworzy go samo RDS)
    if not app_secret and not db_secret:
        return

    import boto3

    client = boto3.client("secretsmanager", region_name=os.getenv("AWS_REGION", "eu-north-1"))

    if app_secret:
        for key, value in _get_secret(client, app_secret).items():
            if key.isupper():
                os.environ.setdefault(key, str(value))

    # sekret RDS ma username i password, adres bazy podajemy w DB_HOST
    if db_secret and not os.getenv("DATABASE_URL"):
        data = _get_secret(client, db_secret)
        host = data.get("host") or os.environ["DB_HOST"]
        os.environ["DATABASE_URL"] = "postgres://{}:{}@{}:{}/{}?sslmode=require".format(
            quote(data["username"], safe=""),
            quote(data["password"], safe=""),
            host,
            data.get("port") or os.getenv("DB_PORT", "5432"),
            data.get("dbname") or os.getenv("DB_NAME", "alledrogo"),
        )
