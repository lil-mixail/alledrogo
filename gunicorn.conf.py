# gunicorn na serwerze EC2 (za load balancerem)
import multiprocessing

bind = "0.0.0.0:8000"
workers = min(multiprocessing.cpu_count() * 2 + 1, 4)
timeout = 30
accesslog = "-"
errorlog = "-"
# ruch przychodzi tylko z ALB (pilnuje tego security group sg-app),
# wiec ufamy jego naglowkom X-Forwarded-*
forwarded_allow_ips = "*"
