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

"""Handlers related to Settings."""

import httplib
import logging

import webapp2
from webapp2_extras import routes

from upvote.gae import settings
from upvote.gae.datastore.models import bit9
from upvote.gae.datastore.models import virustotal
from upvote.gae.datastore.models import datadog
from upvote.gae.datastore.models import fbn_santa_sync
from upvote.gae.modules.upvote_app.api.web import monitoring
from upvote.gae.utils import handler_utils
from upvote.gae.utils import string_utils
from upvote.gae.utils import xsrf_utils
from upvote.shared import constants


class Settings(handler_utils.UserFacingHandler):
  """Get or set the value of a setting."""

  @property
  def RequestCounter(self):
    return monitoring.setting_requests

  @handler_utils.RecordRequest
  def get(self, setting):  # pylint: disable=g-bad-name
    """Get handler for settings."""
    logging.info('Setting requested: %s', setting)
    try:
      formatted_setting = string_utils.CamelToSnakeCase(setting)
      value = getattr(settings, formatted_setting.upper())
    except AttributeError as e:
      logging.info('Unable to retrieve setting.')
      self.abort(httplib.NOT_FOUND, explanation=str(e))
    else:
      self.respond_json(value)


class ApiKeys(handler_utils.AdminOnlyHandler):
  """Set/update the value of an API key."""

  @xsrf_utils.RequireToken
  @handler_utils.RequireCapability(constants.PERMISSIONS.CHANGE_SETTINGS)
  def post(self, key_name):  # pylint: disable=g-bad-name
    """Post handler for a single API key."""

    value = self.request.get('value', None)
    if value is None:
      self.abort(httplib.BAD_REQUEST, explanation='No value provided')

    if key_name == 'virustotal':
      virustotal.VirusTotalApiAuth.SetInstance(api_key=value)
    elif key_name == 'bit9':
      bit9.Bit9ApiAuth.SetInstance(api_key=value)
    elif key_name == 'datadog':
      datadog.DataDogApiAuth.SetInstance(api_key=value)
    elif key_name == 'fbn_santa_sync':
      fbn_santa_sync.FBNSantaSyncAuth.SetInstance(api_key=value)
    else:
      self.abort(httplib.BAD_REQUEST, explanation='Invalid key name')


# The Webapp2 routes defined for these handlers.
ROUTES = routes.PathPrefixRoute('/settings', [
    webapp2.Route(
        '/api-keys/<key_name>',
        handler=ApiKeys),
    webapp2.Route(
        '/<setting>',
        handler=Settings),
])
