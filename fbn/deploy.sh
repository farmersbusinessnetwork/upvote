#!/usr/bin/env bash
set -xeo pipefail
shopt -s extglob

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
ROOT="${DIR}/.."

RED='\033[0;31m'
NC='\033[0m' # No Color

PROJ_ID="santaupvote"


#XXX add appengine_config.py checks here

if [ $# -eq 0 ]; then
    DEPLOY_PARAMS="app.yaml santa_api.yaml"
else
    DEPLOY_PARAMS="$@"
fi

# https://github.com/bazelbuild/rules_appengine/issues/90#issuecomment-436089606
export TMPDIR=${TMPDIR%/}

# Instructions
# To setup your environment to allow deploys, install google cloud sdk: https://cloud.google.com/sdk/docs/#install_the_latest_cloud_tools_version_cloudsdk_current_version
# and run the following prior to running this script:
# gcloud auth login
# gcloud config set account amohr@farmersbusinessnetwork.com
gcloud config set project santaupvote

# https://github.com/google/upvote/issues/32
python3 "${DIR}/validate_certs.py"

# NOTE: this change is critical, or else for some reason all hosts end up getting reset to LOCKDOWN mode in the database
#        see https://github.com/google/upvote/issues/21
if grep -q "SANTA_DEFAULT_CLIENT_MODE = constants.SANTA_CLIENT_MODE.MONITOR" "${ROOT}/upvote/gae/shared/common/settings.py"; then
    # TODO: we should run unittests before deploy, however several don't pass yet due to our changes
    # ${ROOT}/run_tests.sh
    # NOTE: first run needs to be done w/o anything after PROJ_ID
    # NOTE: in order to do a full clean, run: bazel clean --expunge
    # NOTE: for initial deploy you need to remove app.yaml + santa_api.yaml, when you do this it only deploys app.yaml (upvote)
    bazel run upvote/gae:monolith_binary.deploy -- --project ${PROJ_ID} --version auto ${DEPLOY_PARAMS}
else
    echo -e "${RED}Error: Branch does not contain required FBN changes!!!${NC}"
fi
