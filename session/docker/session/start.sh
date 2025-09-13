#!/bin/bash

set -o errexit
set -o pipefail
set -o nounset

ls -l manage.py

exec gunicorn config.wsgi --bind 0.0.0.0:8000 --chdir=/session_auth --reload

echo "== Gunicorn exited ==
