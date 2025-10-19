# FILE 1: backend/Procfile
# Copy this exactly:

web: gunicorn --worker-class eventlet -w 1 --bind 0.0.0.0:$PORT "wsgi:app"
