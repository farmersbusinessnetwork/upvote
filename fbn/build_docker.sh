#!/bin/bash

this_dir="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

set -xeo pipefail

# NOTE: this does not seem to work with Rosetta2, you get a compile error at the end
docker build --platform linux/amd64 -t upvote ${this_dir}
docker run --platform linux/amd64 --rm -ti upvote
