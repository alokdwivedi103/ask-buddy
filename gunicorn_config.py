"""Single-worker deployment matches the conversation service's in-process locks."""
bind = '0.0.0.0:8000'
workers = 1
worker_class = 'uvicorn.workers.UvicornWorker'
timeout = 600
graceful_timeout = 600
keepalive = 5
errorlog = '-'
accesslog = '-'
loglevel = 'info'
