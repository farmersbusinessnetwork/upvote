# Copyright 2017 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS-IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Application-wide configuration."""

from upvote.gae import settings
from upvote.gae.datastore.models import utils as model_utils

# FBN  This NEEDS to happen at least once to ensure you don't DOS yourself
#      However this is causing slowdowns during warmup: https://github.com/google/upvote/issues/32
model_utils.EnsureCriticalRules(settings.CRITICAL_RULES)
