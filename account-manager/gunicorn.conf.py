import os

bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"
workers = int(os.environ.get("GUNICORN_WORKERS", "2"))
threads = int(os.environ.get("GUNICORN_THREADS", "4"))
timeout = 60
graceful_timeout = 20
keepalive = 5
accesslog = "-"
errorlog = "-"
# Do not log query strings or cookies; the default access log format is enough here.
access_log_format = '%(h)s "%(m)s %(U)s" %(s)s %(b)s %(L)ss'
forwarded_allow_ips = os.environ.get("FORWARDED_ALLOW_IPS", "*")
