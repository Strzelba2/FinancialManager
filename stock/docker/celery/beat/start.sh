#!/bin/bash

set -o errexit

set -o nounset

set -o pipefail

exec watchfiles --filter python celery.__main__.main --args '-A app.core.celery_app beat -l INFO'