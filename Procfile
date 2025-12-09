web: python manage.py migrate && python manage.py ensure_default_admin && gunicorn config.wsgi:application --bind 0.0.0.0:$PORT
