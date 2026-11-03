#!/usr/bin/env bash
# Comando de inicialização do App Service (Linux, Python nativo)
set -e
python manage.py migrate --noinput
exec gunicorn omnifrota.wsgi:application --bind=0.0.0.0:8000 --workers 1 --timeout 600
