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

"""Views related to hosts."""
import abc
import datetime
import httplib
import logging
import re

import webapp2
from webapp2_extras import routes

from google.appengine.ext import ndb

from upvote.gae.bigquery import tables
from upvote.gae.datastore.models import host as host_models
from upvote.gae.datastore.models import user as user_models
from upvote.gae.datastore.models import utils as model_utils
from upvote.gae.modules.upvote_app.api.web import monitoring
from upvote.gae.utils import handler_utils
from upvote.gae.utils import xsrf_utils
from upvote.shared import constants


class HostQueryHandler(handler_utils.UserFacingQueryHandler):
  """Handler for querying hosts."""

  MODEL_CLASS = host_models.Host

  @property
  def RequestCounter(self):
    return monitoring.host_requests

  @handler_utils.RequireCapability(constants.PERMISSIONS.VIEW_OTHER_HOSTS)
  @handler_utils.RecordRequest
  def get(self):
    self._Query()


class SantaHostQueryHandler(HostQueryHandler):
  """Handler for querying santa hosts."""

  MODEL_CLASS = host_models.SantaHost


class HostHandler(handler_utils.UserFacingHandler):
  """Handler for interacting with specific hosts."""

  def get(self, host_id):
    host_id = host_models.Host.NormalizeId(host_id)
    logging.info('Host handler get method called with ID=%s.', host_id)
    host = host_models.Host.get_by_id(host_id)
    if host is None:
      self.abort(httplib.NOT_FOUND, explanation='Host not found')
    elif not model_utils.IsHostAssociatedWithUser(host, self.user):
      self.RequireCapability(constants.PERMISSIONS.VIEW_OTHER_HOSTS)
    self.respond_json(host)

  @handler_utils.RequireCapability(constants.PERMISSIONS.EDIT_HOSTS)
  @xsrf_utils.RequireToken
  def post(self, host_id):
    host_id = host_models.Host.NormalizeId(host_id)
    logging.info('Host handler post method called with ID=%s.', host_id)

    host = host_models.Host.get_by_id(host_id)
    if host is None:
      self.abort(httplib.NOT_FOUND, explanation='Host not found')

    if self.request.get('clientMode'):
      host.client_mode = self.request.get('clientMode')
    if self.request.get('clientModeLock'):
      host.client_mode_lock = (self.request.get('clientModeLock') == 'true')
    if self.request.get('shouldUploadLogs'):
      host.should_upload_logs = (
          self.request.get('shouldUploadLogs') == 'true')
    if self.request.get('transitiveWhitelistingEnabled'):
      host.transitive_whitelisting_enabled = (
          self.request.get('transitiveWhitelistingEnabled') == 'true')

    if isinstance(host, santa_models.SantaHost):
      if self.request.get('directoryWhitelistRegex'):
        host.directory_whitelist_regex = self.request.get('directoryWhitelistRegex')
      if self.request.get('directoryBlacklistRegex'):
        host.directory_blacklist_regex = self.request.get('directoryBlacklistRegex')

    host.put()

    self.respond_json(host)


class AssociatedHostHandler(handler_utils.UserFacingHandler):
  """Handler for interacting with specific hosts."""

  def _GetAssociatedHosts(self, user):

    # Build Keys for the associated Hosts, along with their corresponding
    # Exemptions.
    host_keys = model_utils.GetHostKeysForUser(user)

    # Grab all the Hosts.
    hosts = ndb.get_multi(host_keys)
    hosts = [host for host in hosts if host is not None]

    # Get a mapping of Host Keys to Exemptions.
    exm_dict = model_utils.GetExemptionsForHosts(host_keys)

    # If Santa hosts have never synced rules or Bit9 hosts never reported an
    # event, push them to the end of the list.
    epoch = datetime.datetime.utcfromtimestamp(0)

    def ByFreshness(host):
      if isinstance(host, host_models.Bit9Host):
        return host.last_event_dt or epoch
      elif isinstance(host, host_models.SantaHost):
        return host.rule_sync_dt or epoch

    hosts = sorted(hosts, key=ByFreshness, reverse=True)

    # Convert the Host entities to dicts for the frontend, and stuff each one
    # with its corresponding Exemption (if one exists).
    host_dicts = []
    for host in hosts:
      host_dict = host.to_dict()
      if host.key in exm_dict:
        host_dict['exemption'] = exm_dict[host.key]
      host_dicts.append(host_dict)

    return host_dicts

  @handler_utils.RequireCapability(constants.PERMISSIONS.VIEW_OTHER_HOSTS)
  def GetByUserId(self, user_id):
    logging.info('Getting associated Hosts for user_id=%s', user_id)
    user = user_models.User.GetById(user_id)
    if user is None:
      self.abort(httplib.NOT_FOUND, explanation='User not found')

    hosts = self._GetAssociatedHosts(user)
    self.respond_json(hosts)

  def GetSelf(self):
    logging.info('Getting associated Hosts for self (%s)', self.user.email)
    hosts = self._GetAssociatedHosts(self.user)
    self.respond_json(hosts)


class BooleanPropertyHandler(handler_utils.UserFacingHandler):
  """Base class for handlers that toggle a BooleanProperty on a Host."""

  __metaclass__ = abc.ABCMeta

  @abc.abstractproperty
  def property_name(self):
    pass

  def _GetHost(self):
    return host_models.Host.get_by_id(self._normalized_host_id)

  @ndb.transactional
  def _UpdateHost(self):
    host = self._GetHost()
    logging.info(
        'Changing %s to %s for %s',
        self.property_name, self._bool_new_value, host.hostname)
    setattr(host, self.property_name, self._bool_new_value)
    host.put()

  def dispatch(self):

    # Make sure a host_id is provided.
    host_id = self.request.route_kwargs.get('host_id')
    if not host_id:
      self.abort(httplib.BAD_REQUEST, explanation='No host_id provided')

    # Make sure the Host actually exists.
    self._normalized_host_id = host_models.Host.NormalizeId(host_id)
    host = self._GetHost()
    if not host:
      self.abort(httplib.NOT_FOUND, explanation='Host %s not found' % host_id)

    # Make sure the Host is associated with the current user.
    if not model_utils.IsHostAssociatedWithUser(host, self.user):
      explanation = 'Host %s not associated with user %s' % (
          host.hostname, self.user.nickname)
      self.abort(httplib.FORBIDDEN, explanation=explanation)

    # Make sure a new_value is provided.
    new_value = self.request.route_kwargs.get('new_value')
    if not new_value:
      self.abort(httplib.BAD_REQUEST, explanation='No new_value provided')

    # Make sure the new_value is an explicit boolean string.
    if re.match('^(true|false)$', new_value, flags=re.IGNORECASE) is None:
      self.abort(
          httplib.BAD_REQUEST, explanation='Invalid new_value: %s' % new_value)

    self._bool_new_value = new_value.lower() == 'true'

    super(BooleanPropertyHandler, self).dispatch()


class VisibilityHandler(BooleanPropertyHandler):
  """Handler for changing the hidden attribute of a host."""

  @property
  def property_name(self):
    return 'hidden'

  @xsrf_utils.RequireToken
  def put(self, host_id, new_value):
    self._UpdateHost()


class TransitiveHandler(BooleanPropertyHandler):
  """Handler for changing the transitive whitelisting status of a macOS host."""

  @property
  def property_name(self):
    return 'transitive_whitelisting_enabled'

  @xsrf_utils.RequireToken
  def put(self, host_id, new_value):

    # Only Santa clients are supported.
    host = self._GetHost()
    if host.GetClientName() != constants.CLIENT.SANTA:
      self.abort(
          httplib.FORBIDDEN,
          explanation='Only Santa clients support transitive whitelisting')

    self._UpdateHost()

    # Note the state change in BigQuery.
    users = model_utils.GetUsersAssociatedWithSantaHost(
        self._normalized_host_id)
    comment = 'Transitive whitelisting %s by %s' % (
        'enabled' if self._bool_new_value else 'disabled', self.user.nickname)
    tables.HOST.InsertRow(
        device_id=host_id,
        timestamp=datetime.datetime.utcnow(),
        action=constants.HOST_ACTION.COMMENT,
        hostname=host.hostname,
        platform=constants.PLATFORM.MACOS,
        users=users,
        mode=host.client_mode,
        comment=comment)


# The Webapp2 routes defined for these handlers.
ROUTES = routes.PathPrefixRoute('/hosts', [
    webapp2.Route(
        '/associated/<user_id>',
        handler=AssociatedHostHandler,
        handler_method='GetByUserId',
        methods=['GET']),
    webapp2.Route(
        '/associated',
        handler=AssociatedHostHandler,
        handler_method='GetSelf',
        methods=['GET']),
    webapp2.Route(
        '/query/santa',
        handler=SantaHostQueryHandler),
    webapp2.Route(
        '/query',
        handler=HostQueryHandler),
    webapp2.Route(
        '/<host_id>',
        handler=HostHandler),
    webapp2.Route(
        '/<host_id>/hidden/<new_value>',
        handler=VisibilityHandler),
    webapp2.Route(
        '/<host_id>/transitive/<new_value>',
        handler=TransitiveHandler),
])
