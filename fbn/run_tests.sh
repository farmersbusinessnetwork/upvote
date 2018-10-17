#!/usr/bin/env bash

set -xeo pipefail
shopt -s extglob

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
ROOT="${DIR}/.."

export PYTHONPATH=~/Downloads/google-cloud-sdk/platform/google_appengine/

python -m pipenv run ${ROOT}/run_tests.sh