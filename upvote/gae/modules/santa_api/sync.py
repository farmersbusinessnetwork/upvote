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

"""Santa API Module."""

import datetime
import httplib
import itertools
import json
import logging
import zlib

from google.appengine.datastore import datastore_query
from google.appengine.ext import blobstore
from google.appengine.ext import ndb
from google.appengine.ext.webapp import blobstore_handlers

from upvote.gae.bigquery import tables
from upvote.gae.datastore import utils as datastore_utils
from upvote.gae.datastore.models import santa as santa_models
from upvote.gae.datastore.models import user as user_models
from upvote.gae.lib.analysis import metrics
from upvote.gae.modules.santa_api import auth
from upvote.gae.modules.santa_api import constants as santa_const
from upvote.gae.modules.santa_api import monitoring
from upvote.gae.shared.common import big_red
from upvote.gae.shared.common import handlers
from upvote.gae.shared.common import settings
from upvote.gae.shared.common import user_map
from upvote.gae.utils import xsrf_utils
from upvote.shared import constants as common_const

_SANTA_ACTION = 'santa_action'


class XsrfHandler(handlers.UpvoteRequestHandler):
  """Simple handler to provide XSRF tokens to clients."""

  def post(self, uuid):
    token = xsrf_utils.GenerateToken(action_id=_SANTA_ACTION, user_id=uuid)
    self.response.headers[xsrf_utils.DEFAULT_HEADER] = token
    self.response.set_status(httplib.OK)


class BaseSantaApiHandler(handlers.UpvoteRequestHandler):
  """Base class for Santa API handlers.

  Before calling the handler method, does the following:
    + Instantiates the key for the SantaHost entity and stores it in
      self.host_key
    + Validates the supplied XSRF token, returns 403 if invalid.
    + Fetches the host record and stores it in self.host, if it exists.
      If REQUIRE_HOST_OBJECT is True and the host record doesn't exist,
      returns a 403 to the client.
    + If SHOULD_PARSE_JSON is True, the request body is parsed as JSON and the
      result stored in self.parsed_json. If the Content-Encoding header is equal
      to 'zlib' the request body will be decompressed before deserialization.
      If parsing fails a 400 error will be returned.
  """
  # Subclasses should set this to False if they don't want the
  # request body to be parsed as JSON.
  SHOULD_PARSE_JSON = True

  # Subclasses should set this to False if they don't require the
  # syncing host to have checked-in previously.
  REQUIRE_HOST_OBJECT = True

  def dispatch(self):
    """Prepares for the request to be handled.

    Retrieves the SantaHost object for the provided UUID and parses any JSON
    sent in the request.
    """
    uuid = self.request.route_args[0] if self.request.route_args else None
    if not uuid:
      self.abort(httplib.BAD_REQUEST, explanation='No client UUID provided')

    # Validate the connecting client.
    mode = settings.SANTA_CLIENT_VALIDATION
    if mode != common_const.VALIDATION_MODE.NONE:
      try:
        is_valid = auth.ValidateClient(self.request.headers, uuid)
      except Exception as e:  # pylint: disable=broad-except
        logging.warning('Client validation failed: %s', e)
        is_valid = mode == common_const.VALIDATION_MODE.FAIL_OPEN

      if not is_valid:
        self.abort(httplib.FORBIDDEN, explanation='Failed to validate client.')

    # Validate the client's XSRF token.
    if settings.SANTA_REQUIRE_XSRF:
      token = self.request.headers.get(xsrf_utils.DEFAULT_HEADER, '')
      try:
        xsrf_utils.ValidateToken(token, action_id=_SANTA_ACTION, user_id=uuid)
      except xsrf_utils.Error:
        self.abort(httplib.FORBIDDEN, explanation='XSRF token missing/invalid.')

    self.host_key = ndb.Key('Host', uuid)
    self.host = self.host_key.get()
    if not self.host and self.REQUIRE_HOST_OBJECT:
      logging.info('Rejecting client: has not completed preflight')
      self.abort(
          httplib.FORBIDDEN, explanation='Client has not completed preflight')

    if self.SHOULD_PARSE_JSON:
      try:
        if self.request.headers.get('Content-Encoding') == 'zlib':
          body = zlib.decompress(self.request.body)
        else:
          body = self.request.body
        self.parsed_json = json.loads(body)
      except ValueError:
        logging.info('Rejecting client: failed to parse JSON.')
        logging.info('Malformed JSON: "%s"', body)
        self.abort(httplib.BAD_REQUEST, explanation='Bad JSON body')

    super(BaseSantaApiHandler, self).dispatch()


def _CopyLocalRules(user_key, dest_host_id):
  """Creates copies of all local rules for the new host."""

  logging.info(
      'Copying rules for user %s to host %s', user_key.id(), dest_host_id)

  # Pick any host owned by the user to copy rules from. Exclude hosts that
  # haven't completed a full sync because they won't have a complete rule set.
  username = user_map.EmailToUsername(user_key.id())
  query = santa_models.SantaHost.query(
      santa_models.SantaHost.primary_user == username,
      santa_models.SantaHost.last_postflight_dt != None)  # pylint: disable=g-equals-none
  src_host = query.get()
  if src_host is None:
    logging.warning('User %s has no hosts to copy from', username)
    return datastore_utils.GetNoOpFuture()

  # Query for all SantaRules for the given user on the chosen host.
  query = santa_models.SantaRule.query(
      santa_models.SantaRule.host_id == src_host.key.id(),
      santa_models.SantaRule.user_key == user_key)

  # Copy the local rules to the new host.
  new_rules = []
  for src_rules in datastore_utils.Paginate(query):
    for src_rule in src_rules:
      new_rule = datastore_utils.CopyEntity(
          src_rule, new_parent=src_rule.key.parent(), host_id=dest_host_id,
          user_key=user_key)
      new_rules.append(new_rule)
      new_rule.InsertBigQueryRow()

  logging.info('Copying %d rule(s) to host %s', len(new_rules), dest_host_id)
  futures = ndb.put_multi_async(new_rules)
  return datastore_utils.GetMultiFuture(futures)


class PreflightHandler(BaseSantaApiHandler):
  """Preflight is the first stage of the sync process for a full sync."""
  REQUIRE_HOST_OBJECT = False

  @property
  def RequestCounter(self):
    return monitoring.preflight_requests

  @handlers.RecordRequest
  def post(self, uuid):
    futures = []

    # Create an User for the primary_user on any preflight if one doesn't
    # already exist.
    primary_user = self.parsed_json.get(santa_const.PREFLIGHT.PRIMARY_USER)
    user = user_models.User.GetOrInsert(
        user_map.UsernameToEmail(primary_user))
    # Ensures the returned username is consistent with the User entity.
    primary_user = user.nickname

    # Create a SantaHost on the first preflight.
    first_preflight = not self.host
    if first_preflight:
      self.host = santa_models.SantaHost(key=self.host_key)
      self.host.client_mode = settings.SANTA_DEFAULT_CLIENT_MODE
      futures.append(_CopyLocalRules(user.key, uuid))

    # Update host entity on every sync.
    self.host.serial_num = self.parsed_json.get(
        santa_const.PREFLIGHT.SERIAL_NUM)
    self.host.hostname = self.parsed_json.get(
        santa_const.PREFLIGHT.HOSTNAME)
    self.host.primary_user = primary_user
    self.host.santa_version = self.parsed_json.get(
        santa_const.PREFLIGHT.SANTA_VERSION)
    self.host.os_version = self.parsed_json.get(
        santa_const.PREFLIGHT.OS_VERSION)
    self.host.os_build = self.parsed_json.get(
        santa_const.PREFLIGHT.OS_BUILD)
    self.host.last_preflight_dt = datetime.datetime.utcnow()
    self.host.last_preflight_ip = self.request.remote_addr

    reported_mode = self.parsed_json.get(santa_const.PREFLIGHT.CLIENT_MODE)
    if reported_mode != self.host.client_mode:

      message = 'Client mode mismatch (Expected: %s, Actual: %s)' % (
          self.host.client_mode, reported_mode)
      logging.info(message)

      # If the client_mode doesn't correspond to a known value, report it as
      # UNKNOWN.
      if reported_mode not in common_const.HOST_MODE.SET_ALL:
        reported_mode = common_const.HOST_MODE.UNKNOWN

      tables.HOST.InsertRow(
          device_id=uuid,
          timestamp=datetime.datetime.utcnow(),
          action=common_const.HOST_ACTION.COMMENT,
          hostname=self.host.hostname,
          platform=common_const.PLATFORM.MACOS,
          users=santa_models.SantaHost.GetAssociatedUsers(uuid),
          mode=reported_mode,
          comment=message)

    if self.parsed_json.get(santa_const.PREFLIGHT.REQUEST_CLEAN_SYNC):
      logging.info('Client requested clean sync')
      self.host.rule_sync_dt = None

    # Save host entity.
    futures.append(self.host.put_async())

    # If the big red button is pressed, override the self.host.client_mode
    # set in datastore with either MONITOR or LOCKDOWN for this response only.
    actual_client_mode = self.host.client_mode
    big_red_button = big_red.BigRedButton()
    if big_red_button.stop_stop_stop:
      actual_client_mode = common_const.SANTA_CLIENT_MODE.MONITOR
    elif big_red_button.go_go_go:
      actual_client_mode = common_const.SANTA_CLIENT_MODE.LOCKDOWN

    # Prepare response.
    response = {
        santa_const.PREFLIGHT.BATCH_SIZE: (
            settings.SANTA_EVENT_BATCH_SIZE),
        santa_const.PREFLIGHT.CLIENT_MODE: actual_client_mode,
        santa_const.PREFLIGHT.WHITELIST_REGEX: (
            self.host.directory_whitelist_regex
            if self.host.directory_whitelist_regex is not None
            else settings.SANTA_DIRECTORY_WHITELIST_REGEX),
        santa_const.PREFLIGHT.BLACKLIST_REGEX: (
            self.host.directory_blacklist_regex
            if self.host.directory_blacklist_regex is not None
            else settings.SANTA_DIRECTORY_BLACKLIST_REGEX),
        santa_const.PREFLIGHT.CLEAN_SYNC: not self.host.rule_sync_dt,
        santa_const.PREFLIGHT.BUNDLES_ENABLED: (
            settings.SANTA_BUNDLES_ENABLED),
        santa_const.PREFLIGHT.TRANSITIVE_WHITELISTING_ENABLED: (
            self.host.transitive_whitelisting_enabled),
    }

    if self.host.should_upload_logs:
      response[santa_const.PREFLIGHT.UPLOAD_LOGS_URL] = (
          blobstore.create_upload_url('/api/santa/logupload/%s' % uuid))

    # Verify all futures resolved successfully.
    for future in futures:
      future.check_success()

    # If this is the first preflight, create a FIRST_SEEN HostRow. This has to
    # occur after the new SantaHost entity is put(), since SantaHost.recorded_dt
    # is an auto_now_add.
    if first_preflight:
      new_host = ndb.Key('Host', uuid).get()
      tables.HOST.InsertRow(
          device_id=uuid,
          timestamp=new_host.recorded_dt,
          action=common_const.HOST_ACTION.FIRST_SEEN,
          hostname=new_host.hostname,
          platform=common_const.PLATFORM.MACOS,
          users=santa_models.SantaHost.GetAssociatedUsers(uuid),
          mode=new_host.client_mode)

    self.respond_json(response)


class EventUploadHandler(BaseSantaApiHandler):
  """Event Upload is the optional second stage of a full sync.

  Event Upload can also occur outside of a full sync when a client blocks a
  binary.
  """

  @property
  def RequestCounter(self):
    return monitoring.event_upload_requests

  @classmethod
  def _GetPublisherAndCertFingerprintFromJsonEvent(cls, json_event):
    """Returns the publisher and cert fingerprint associated with the event.

    NOTE: The publisher and cert fingerprint are those of the _first_ cert in
    the signing chain.

    Args:
      json_event: A single JSON event uploaded by the client.

    Returns:
      publisher: The organization from the leaf cert in the chain, or None.
      cert_sha256: The SHA-256 of the leaf cert in the chain, or None.
    """
    signing_chain = json_event.get(santa_const.EVENT_UPLOAD.SIGNING_CHAIN)
    if signing_chain:
      first_cert = signing_chain[0]
      publisher = first_cert.get(santa_const.EVENT_UPLOAD.ORG)
      cert_sha256 = first_cert.get(santa_const.EVENT_UPLOAD.SHA256)
    else:
      publisher = None
      cert_sha256 = None
    return publisher, cert_sha256

  @classmethod
  def _GenerateBinaryFromJsonEvent(cls, json_event):
    """Generates the Binary entity associated with the event.

    Args:
      json_event: A single JSON event uploaded by the client.

    Returns:
      The created-but-not-persisted SantaBlockable entity.
    """
    publisher, cert_sha256 = (
        cls._GetPublisherAndCertFingerprintFromJsonEvent(json_event))
    cert_key = cert_sha256 and ndb.Key(
        santa_models.SantaCertificate, cert_sha256)
    return santa_models.SantaBlockable(
        id=json_event.get(santa_const.EVENT_UPLOAD.FILE_SHA256),
        blockable_hash=json_event.get(santa_const.EVENT_UPLOAD.FILE_SHA256),
        id_type=common_const.ID_TYPE.SHA256,
        file_name=json_event.get(santa_const.EVENT_UPLOAD.FILE_NAME),
        publisher=publisher,
        version=json_event.get(
            santa_const.EVENT_UPLOAD.FILE_BUNDLE_VERSION),
        cert_key=cert_key,
        state=common_const.STATE.UNTRUSTED,
        cert_sha256=cert_sha256)

  @classmethod
  def _GenerateCertificatesFromJsonEvent(cls, event):
    """Generates the list of Certificate entities associated with the event.

    Args:
      event: A single JSON event uploaded by the client.

    Returns:
      A list of the created-but-not-persisted SantaCertificate entities.
    """
    signing_chain = event.get(santa_const.EVENT_UPLOAD.SIGNING_CHAIN, [])
    certs = []
    for cert in signing_chain:
      cert_entity = santa_models.SantaCertificate(
          id=cert.get(santa_const.EVENT_UPLOAD.SHA256),
          id_type=common_const.ID_TYPE.SHA256,
          common_name=cert.get(santa_const.EVENT_UPLOAD.CN),
          organization=cert.get(santa_const.EVENT_UPLOAD.ORG),
          organizational_unit=cert.get(santa_const.EVENT_UPLOAD.OU),
          valid_from_dt=datetime.datetime.utcfromtimestamp(
              cert.get(santa_const.EVENT_UPLOAD.VALID_FROM)),
          valid_until_dt=datetime.datetime.utcfromtimestamp(
              cert.get(santa_const.EVENT_UPLOAD.VALID_UNTIL)))
      certs.append(cert_entity)
    return certs

  @classmethod
  def _GenerateBundleFromJsonEvent(cls, json_event):
    bundle_key = cls._GetBundleKeyFromJsonEvent(json_event)
    assert bundle_key

    # Truncate CFBundleName to ensure it fits within the 1500 byte limit imposed
    # by indexed NDB StringProperty fields. Imposing a limit of 200 characters
    # should be more than enough for display purposes, and will ensure that we
    # stay under the 1500 byte limit, even for strings with lots of characters
    # that require multiple bytes in UTF-8.
    name = json_event.get(santa_const.EVENT_UPLOAD.FILE_BUNDLE_NAME)
    name = name if name is None else name[:200]

    return santa_models.SantaBundle(
        key=bundle_key,
        name=name,
        version=json_event.get(
            santa_const.EVENT_UPLOAD.FILE_BUNDLE_VERSION),
        short_version=json_event.get(
            santa_const.EVENT_UPLOAD.FILE_BUNDLE_VERSION_STRING),
        bundle_id=json_event.get(santa_const.EVENT_UPLOAD.FILE_BUNDLE_ID),
        binary_count=json_event.get(
            santa_const.EVENT_UPLOAD.FILE_BUNDLE_BINARY_COUNT),
        main_executable_rel_path=json_event.get(
            santa_const.EVENT_UPLOAD.FILE_BUNDLE_EXECUTABLE_REL_PATH),
        id_type=common_const.ID_TYPE.SANTA_BUNDLE)

  @classmethod
  def _GenerateSantaEventsFromJsonEvent(cls, event, host):
    """Creates all SantaEvent associated with the JSON uploaded from a client.

    Args:
      event: A single JSON event uploaded by the client.
      host: The SantaHost entity corresponding to the syncing client.

    Returns:
      A list of the created-but-not-persisted SantaEvent entities.
    """
    dbevent = santa_models.SantaEvent()
    dbevent.host_id = host.key.id()
    dbevent.file_name = event.get(santa_const.EVENT_UPLOAD.FILE_NAME)
    dbevent.file_path = event.get(santa_const.EVENT_UPLOAD.FILE_PATH)
    dbevent.version = event.get(
        santa_const.EVENT_UPLOAD.FILE_BUNDLE_VERSION)
    dbevent.executing_user = event.get(
        santa_const.EVENT_UPLOAD.EXECUTING_USER)
    dbevent.event_type = event.get(santa_const.EVENT_UPLOAD.DECISION)
    dbevent.bundle_path = event.get(
        santa_const.EVENT_UPLOAD.FILE_BUNDLE_PATH)
    dbevent.bundle_key = cls._GetBundleKeyFromJsonEvent(event)

    blockable_id = event.get(santa_const.EVENT_UPLOAD.FILE_SHA256)
    if blockable_id:
      dbevent.blockable_key = ndb.Key(santa_models.SantaBlockable, blockable_id)

    publisher, cert_sha256 = (
        cls._GetPublisherAndCertFingerprintFromJsonEvent(event))
    dbevent.publisher = publisher
    if cert_sha256:
      dbevent.cert_key = ndb.Key(santa_models.SantaCertificate, cert_sha256)

    occurred_dt = datetime.datetime.utcfromtimestamp(
        event.get(santa_const.EVENT_UPLOAD.EXECUTION_TIME, 0))
    dbevent.first_blocked_dt = occurred_dt
    dbevent.last_blocked_dt = occurred_dt

    quarantine_timestamp = event.get(
        santa_const.EVENT_UPLOAD.QUARANTINE_TIMESTAMP, 0)
    if quarantine_timestamp:
      quarantine_time = datetime.datetime.utcfromtimestamp(quarantine_timestamp)
      dbevent.quarantine = santa_models.QuarantineMetadata(
          data_url=event.get(santa_const.EVENT_UPLOAD.QUARANTINE_DATA_URL),
          referer_url=event.get(
              santa_const.EVENT_UPLOAD.QUARANTINE_REFERER_URL),
          agent_bundle_id=event.get(
              santa_const.EVENT_UPLOAD.QUARANTINE_AGENT_BUNDLE_ID),
          downloaded_dt=quarantine_time)

    usernames = event.get(santa_const.EVENT_UPLOAD.LOGGED_IN_USERS, [])

    tables.EXECUTION.InsertRow(
        sha256=blockable_id,
        device_id=dbevent.host_id,
        timestamp=occurred_dt,
        platform=dbevent.GetPlatformName(),
        client=dbevent.GetClientName(),
        bundle_path=dbevent.bundle_path,
        file_path=dbevent.file_path,
        file_name=dbevent.file_name,
        executing_user=dbevent.executing_user or 'UNKNOWN',
        associated_users=usernames,
        decision=dbevent.event_type)

    return [
        datastore_utils.CopyEntity(dbevent, new_key=key)
        for key in dbevent.GetKeysToInsert(usernames, [host.primary_user])]

  @classmethod
  @ndb.tasklet
  def _CreateCertificatesFromJsonEvents(cls, json_events):
    """Creates Certificate entities associated with an event."""
    certs = itertools.chain.from_iterable(
        cls._GenerateCertificatesFromJsonEvent(event) for event in json_events)
    unique_cert_map = {cert.key: cert for cert in certs}
    existing_certs = yield ndb.get_multi_async(unique_cert_map.keys())
    unknown_certs = [
        cert
        for cert, existing in zip(unique_cert_map.values(), existing_certs)
        if existing is None]

    for cert_entity in unknown_certs:
      # Insert a row into the Certificate table. Allow the timestamp to be
      # generated within InsertBigQueryRow(). The Blockable.recorded_dt Property
      # is set to auto_now_add, but this isn't filled in until persist time.
      cert_entity.InsertBigQueryRow(common_const.BLOCK_ACTION.FIRST_SEEN)

    yield ndb.put_multi_async(unknown_certs)

  @classmethod
  @ndb.transactional_tasklet
  def _DedupeExistingAndPut(cls, events):
    """Dedupes a list of new-style Events with existing Events and puts them."""

    # NOTE: We copy each entity in the input list because this function
    # is transactional and, consequently, may be retried with the same
    # parameters in the event of a failure. If we modify the event objects in
    # place, subsequent retries will see the changes made by previous attempts.
    event_copies = [
        datastore_utils.CopyEntity(event, new_key=event.key)
        for event in events]
    existing_events = yield ndb.get_multi_async(event.key for event in events)
    for event, existing_event in zip(event_copies, existing_events):
      if existing_event:
        event.Dedupe(existing_event)
    yield ndb.put_multi_async(event_copies)

  @classmethod
  def _GetBlockableKeyFromJsonEvent(cls, json_event):
    file_hash = json_event.get(santa_const.EVENT_UPLOAD.FILE_SHA256)
    assert file_hash
    return ndb.Key(santa_models.SantaBundle, file_hash)

  @classmethod
  def _GetBundleKeyFromJsonEvent(cls, json_event):
    bundle_hash = json_event.get(santa_const.EVENT_UPLOAD.FILE_BUNDLE_HASH)
    return (
        ndb.Key(santa_models.SantaBundle, bundle_hash) if bundle_hash else None)

  @classmethod
  def _GetBundleRelPathFromJsonEvent(cls, json_event):
    path_to_bundle = json_event.get(
        santa_const.EVENT_UPLOAD.FILE_BUNDLE_PATH)
    path_to_file = json_event.get(santa_const.EVENT_UPLOAD.FILE_PATH)
    if path_to_bundle:
      if path_to_bundle not in path_to_file:
        logging.error(
            'Bundle path (%s) not prefix of file path (%s)', path_to_bundle,
            path_to_file)
      else:
        _, _, bundle_rel_path = path_to_file.partition(path_to_bundle)
        return bundle_rel_path.lstrip('/')
    return None

  # pylint: disable=g-doc-return-or-yield
  @classmethod
  @ndb.transactional_tasklet
  def _CreateBlockableFromJsonEvent(cls, json_event, now):
    """Creates a SantaBlockable from a JSON event if it does not already exist.

    Will create a SantaBlockable for a given event if necessary, tracking
    whether the blockable was created so clients can be asked
    to upload the binary.

    This is kept in a transaction in order to avoid an interleaving in which one
    call's put clobbers an earlier call's put. Although usually benign, this
    scenario becomes problematic during periods of high datastore contention.
    When these transactions may commit at very different times, potentially
    enough of a difference for state changes (e.g. votes, whitelisting) to take
    place on the clobbered blockable.

    Args:
      json_event: A single JSON event from the client.
      now: A datetime representing the current time. Passed in as an argument to
          ensure that transaction retries use the same timestamp.
    """
    # pylint: enable=g-doc-return-or-yield
    blockable_id = json_event.get(santa_const.EVENT_UPLOAD.FILE_SHA256)
    blockable_key = ndb.Key(santa_models.SantaBlockable, blockable_id)
    blockable = yield blockable_key.get_async()
    if not blockable:
      blockable = cls._GenerateBinaryFromJsonEvent(json_event)
      yield blockable.put_async()

      blockable.InsertBigQueryRow(
          common_const.BLOCK_ACTION.FIRST_SEEN, timestamp=now)

      metrics.DeferLookupMetric(
          blockable_id, common_const.ANALYSIS_REASON.NEW_BLOCKABLE)

  # pylint: disable=g-doc-return-or-yield
  @classmethod
  @ndb.transactional_tasklet
  def _CreateBundleFromJsonEvent(cls, json_event, now):
    """Creates a SantaBundle from a JSON event if it does not already exist.

    Args:
      json_event: A single JSON event from the client.
      now: A datetime representing the current time. Passed in as an argument to
          ensure that transaction retries use the same timestamp.
    """
    # pylint: enable=g-doc-return-or-yield
    bundle_key = cls._GetBundleKeyFromJsonEvent(json_event)
    if bundle_key:
      bundle = yield bundle_key.get_async()
      if not bundle:
        bundle = cls._GenerateBundleFromJsonEvent(json_event)

        bundle.InsertBigQueryRow(
            common_const.BLOCK_ACTION.FIRST_SEEN, timestamp=now)

        yield bundle.put_async()

  @classmethod
  @ndb.tasklet
  def _CreateAllBundlesFromJsonEvents(cls, json_events):
    """Creates all SantaBundle entites from the provided JSON events."""
    bundle_key_map = {
        cls._GetBundleKeyFromJsonEvent(json_event): json_event
        for json_event in json_events
        if cls._GetBundleKeyFromJsonEvent(json_event)}
    all_keys = bundle_key_map.keys()
    existing_bundles = yield ndb.get_multi_async(all_keys)
    now = datetime.datetime.utcnow()
    for key, bundle in zip(all_keys, existing_bundles):
      if bundle is None:
        json_event = bundle_key_map[key]
        yield cls._CreateBundleFromJsonEvent(json_event, now)

  @classmethod
  @ndb.transactional_tasklet
  def _CreateBundleBinaries(cls, bundle_key, bundle_upload_events, now):
    """Create the uploaded binaries associated with a single bundle."""
    logging.info(
        'Uploading %d binaries from bundle %s', len(bundle_upload_events),
        bundle_key.id())

    bundle = yield bundle_key.get_async()
    if not bundle:
      bundle = cls._GenerateBundleFromJsonEvent(bundle_upload_events[0])

      bundle.InsertBigQueryRow(
          common_const.BLOCK_ACTION.FIRST_SEEN, timestamp=now)

      yield bundle.put_async()
    elif bundle and bundle.has_been_uploaded:
      # NOTE: This can occur in a race condition with another upload
      # process's _UpdateBundleUploadStatus.
      logging.error(
          'Received previously unknown binary event for Bundle %s: %s',
          bundle.key.id(), bundle_upload_events)
      return

    bundle_binaries = []
    for json_event in bundle_upload_events:
      blockable = cls._GenerateBinaryFromJsonEvent(json_event)
      certs = cls._GenerateCertificatesFromJsonEvent(json_event)
      signing_cert_key = certs[0].key if certs else None
      if signing_cert_key is None:
        bundle.has_unsigned_contents = True

      rel_path = cls._GetBundleRelPathFromJsonEvent(json_event)
      file_name = json_event.get(santa_const.EVENT_UPLOAD.FILE_NAME)
      if rel_path is None:
        logging.error(
            'Skipping bundle binary %s in bundle %s', blockable.key.id(),
            bundle.key.id())
        continue

      bundle_binary = santa_models.SantaBundleBinary.Generate(
          bundle_key, blockable.key, rel_path=rel_path, file_name=file_name,
          cert_key=signing_cert_key)
      bundle_binaries.append(bundle_binary)

      tables.BUNDLE_BINARY.InsertRow(
          bundle_hash=bundle_key.id(),
          sha256=blockable.key.id(),
          timestamp=datetime.datetime.utcnow(),
          action=common_const.BLOCK_ACTION.UPLOADED,
          cert_fingerprint='' if signing_cert_key is None
          else signing_cert_key.id(),
          relative_path=rel_path,
          file_name=file_name)

      # Calculate the path of the binary relative to the bundle to compare
      # against that of the reported CFBundleExecutable.
      rel_path_with_fname = '/'.join((rel_path, file_name))
      if bundle.main_executable_rel_path == rel_path_with_fname:
        # If this binary is the main executable, record its metadata on the
        # bundle entity.
        bundle.main_cert_key = signing_cert_key
        bundle.main_executable_key = bundle_binary.key

    yield ndb.put_multi_async([bundle] + bundle_binaries)

  @classmethod
  @ndb.transactional_tasklet
  def _UpdateBundleUploadStatus(cls, bundle_key):
    bundle = yield bundle_key.get_async()
    assert bundle is not None

    total_uploaded = yield santa_models.SantaBundleBinary.query(
        ancestor=bundle_key).count_async()
    assert total_uploaded <= bundle.binary_count

    if total_uploaded == bundle.binary_count:
      bundle.uploaded_dt = datetime.datetime.utcnow()
      yield bundle.put_async()
      metrics.DeferLookupMetric(
          bundle.key.id(), common_const.ANALYSIS_REASON.NEW_BLOCKABLE)

  @ndb.tasklet
  def _CreateAllBundleBinaries(self, bundle_upload_events):
    """Create all the bundles' binaries for an event upload."""
    # Arrange the upload events by their associated bundle.
    by_bundle_key = {}
    for json_event in bundle_upload_events:
      bundle_key = self._GetBundleKeyFromJsonEvent(json_event)
      if bundle_key:
        by_bundle_key.setdefault(bundle_key, [])
        by_bundle_key[bundle_key].append(json_event)
      else:
        logging.error(
            'Invalid bundle metadata for BUNDLE_BINARY event: %s', json_event)

    # Save each bundle's group of binaries in its own transaction.
    now = datetime.datetime.utcnow()
    for bundle_key, bundle_events in by_bundle_key.iteritems():
      yield self._CreateBundleBinaries(bundle_key, bundle_events, now)
      yield self._UpdateBundleUploadStatus(bundle_key)

  @classmethod
  def _CreateEvents(cls, events):
    """Create each users' Events asynchronously in their own transactions."""
    futures = []
    distinct_events = santa_models.SantaEvent.DedupeMultiple(events)
    unique_user_keys = {event.user_key for event in events}
    for user_key in unique_user_keys:
      events_for_user = [
          event
          for event in distinct_events
          if event.user_key == user_key]
      futures.append(cls._DedupeExistingAndPut(events_for_user))
    return futures

  @classmethod
  @ndb.tasklet
  def _GetBlockablesToUpload(cls, existing_keys, unknown_keys):
    """Determine which blockables in this event upload require uploading.

    - If we've never seen a Blockable before, we know we'll need to upload it.
    - If the Blockable has an existing entity (i.e. we've seen it), we need to
      do a further check to see whether there's an associated SantaBinaryFile.

    Args:
      existing_keys: set<Key>, The set of blockable keys for which blockable
          entities existed prior to this upload.
      unknown_keys: set<Key>, The set of blockable keys for which no blockable
          entity existed prior to this upload.

    Returns:
      list<Key>, The keys of SantaBlockables that require upload.
    """
    blockable_keys = list(existing_keys)
    binary_files = yield ndb.get_multi_async(
        ndb.Key(santa_models.SantaBinaryFile, blockable_key.id())
        for blockable_key in blockable_keys)
    existing_but_not_uploaded = {
        blockable_key
        for blockable_key, binary_file in zip(blockable_keys, binary_files)
        if not binary_file}
    raise ndb.Return(list(unknown_keys | existing_but_not_uploaded))

  @classmethod
  @ndb.tasklet
  def _GetBundlesToUpload(cls, json_events):
    """Determine which bundles in this event upload require uploading.

    Args:
      json_events: The list of json events provided in this event upload.

    Returns:
      list<Key>, The keys of SantaBundles that require upload.
    """
    all_bundle_keys = [
        cls._GetBundleKeyFromJsonEvent(json_event)
        for json_event in json_events]
    unique_bundle_keys = list(set(filter(None, all_bundle_keys)))

    # NOTE: We're relying on a race condition here. All the Bundle
    # entity creations may not have finished by this point _but_ if we see that
    # some don't exist, we know we're the first to create them. If we're first
    # to create them, we should proactively request that they be uploaded.
    existing_bundles = yield ndb.get_multi_async(unique_bundle_keys)
    bundles_to_upload = [
        bundle_key
        for bundle_key, bundle in zip(unique_bundle_keys, existing_bundles)
        if not bundle or not bundle.has_been_uploaded]
    raise ndb.Return(bundles_to_upload)

  @ndb.toplevel  # ensure all async puts complete before handler returns.
  @handlers.RecordRequest
  def post(self, uuid):
    # If the host doesn't have any rules, ignore all the events it generated.
    if not self.host.last_postflight_dt:
      self.respond_json({})
      return

    all_futures = []
    json_events = self.parsed_json.get(santa_const.EVENT_UPLOAD.EVENTS)
    logging.info('Syncing %d events', len(json_events))

    # Create cert entities for all signing chains if they don't already exist.
    all_futures.append(self._CreateCertificatesFromJsonEvents(json_events))

    # Filter out bundle upload events because they should not be created as
    # conventional SantaEvents.
    bundle_upload_events = []
    normal_events = []
    blockable_event_map = {}  # Maps a blockable key to one of its json events.
    for event in json_events:
      decision = event.get(santa_const.EVENT_UPLOAD.DECISION)
      if decision == common_const.EVENT_TYPE.BUNDLE_BINARY:
        bundle_upload_events.append(event)
      else:
        normal_events.append(event)
      key = self._GetBlockableKeyFromJsonEvent(event)
      blockable_event_map[key] = event

    # Create all SantaBundle entities associated with the non-bundle-upload
    # events to ensures the bundles are present prior to upload.
    all_futures.append(self._CreateAllBundlesFromJsonEvents(normal_events))

    # Create bundle members for bundle upload events.
    bundle_member_future = datastore_utils.GetNoOpFuture()
    if bundle_upload_events:
      logging.info('Syncing %d bundle events', len(bundle_upload_events))
      bundle_member_future = self._CreateAllBundleBinaries(bundle_upload_events)
      all_futures.append(bundle_member_future)

    # Create SantaEvent entites from the uploaded JSON events.
    santa_events = []
    for json_event in normal_events:
      events = self._GenerateSantaEventsFromJsonEvent(json_event, self.host)
      santa_events.extend(events)

    all_futures.extend(self._CreateEvents(santa_events))

    # Determine which blockables are already known to Upvote.
    unique_blockable_keys = set(blockable_event_map.keys())
    existing_blockable_keys = {
        blockable.key
        for blockable in ndb.get_multi(list(unique_blockable_keys))
        if blockable}
    unknown_blockable_keys = unique_blockable_keys - existing_blockable_keys

    # Start tasklet to determine which entities require upload.
    blockables_future = self._GetBlockablesToUpload(
        existing_blockable_keys, unknown_blockable_keys)

    # Create previously unknown blockables.
    now = datetime.datetime.utcnow()
    for blockable_key in list(unknown_blockable_keys):
      json_event = blockable_event_map[blockable_key]

      all_futures.append(self._CreateBlockableFromJsonEvent(json_event, now))

    # Generate and send the response.
    response_dict = {}

    blockables_to_upload = blockables_future.get_result()
    if blockables_to_upload:
      need_upload_ids = [
          blockable_key.id() for blockable_key in blockables_to_upload]
      response_dict.update({
          santa_const.EVENT_UPLOAD.REQUEST_UPLOADS: need_upload_ids,
          santa_const.EVENT_UPLOAD.REQUEST_UPLOADS_URL: (
              blobstore.create_upload_url('/api/santa/binaryupload/%s' % uuid)),
      })

    # NOTE: The bundles-to-upload calculation needs to wait for the
    # bundle members in this upload to be committed and for those bundles'
    # upload statuses to be recalculated.
    bundle_member_future.get_result()
    bundles_to_upload = self._GetBundlesToUpload(json_events).get_result()
    if bundles_to_upload:
      bundle_ids = [bundle_key.id() for bundle_key in bundles_to_upload]
      response_dict.update({
          santa_const.EVENT_UPLOAD.EVENT_UPLOAD_BUNDLE_BINARIES: bundle_ids,
      })

    # Resolve all futures. This will have the side effect of raising the first
    # exception, if any, that a future in the list raised.
    for future in all_futures:
      future.check_success()

    self.respond_json(response_dict)


class LogUploadHandler(
    blobstore_handlers.BlobstoreUploadHandler, BaseSantaApiHandler):
  """Handles log uploads."""
  # Clients do not send any JSON with this request.
  SHOULD_PARSE_JSON = False

  @property
  def RequestCounter(self):
    return monitoring.log_upload_requests

  @ndb.toplevel  # ensure all async puts complete before handler returns.
  @handlers.RecordRequest
  def post(self, uuid):
    upload_files = self.get_uploads('files')
    now = datetime.datetime.utcnow()

    logs = [
        santa_models.SantaLogFile(blobkey=f.key(), filename=f.filename,
                                  upload_dt=now, host_id=uuid)
        for f in upload_files]
    ndb.put_multi(logs)

    self.host.should_upload_logs = False
    self.host.put()


class BinaryUploadHandler(
    blobstore_handlers.BlobstoreUploadHandler, BaseSantaApiHandler):
  """Handles binary uploads."""
  # Clients do not send any JSON with this request.
  SHOULD_PARSE_JSON = False

  @property
  def RequestCounter(self):
    return monitoring.binary_upload_requests

  @ndb.toplevel
  @handlers.RecordRequest
  def post(self, uuid):
    upload_files = self.get_uploads('files')

    for f in upload_files:
      santa_models.SantaBinaryFile(
          id=f.filename,
          blobkey=f.key(),
          shasum=f.filename,
          upload_dt=datetime.datetime.utcnow(),
          host_id=uuid).put_async()


class RuleDownloadHandler(BaseSantaApiHandler):
  """Rule download handler sends new rules to clients."""

  @property
  def RequestCounter(self):
    return monitoring.rule_download_requests

  @handlers.RecordRequest
  def post(self, uuid):
    # Prepare the query
    cursor = self.parsed_json.get(santa_const.RULE_DOWNLOAD.CURSOR)

    if self.host.rule_sync_dt is None:
      logging.info('%s clean rule sync', 'Continuing' if cursor else 'Starting')

    # pylint:disable=g-explicit-bool-comparison, singleton-comparison
    query = santa_models.SantaRule.query(
        santa_models.SantaRule.in_effect == True,
        santa_models.SantaRule.updated_dt >= self.host.rule_sync_dt,
        santa_models.SantaRule.host_id.IN(['', uuid])
    ).order(santa_models.SantaRule.updated_dt, santa_models.SantaRule.key)
    # pylint:enable=g-explicit-bool-comparison, singleton-comparison

    # Fetch
    rules, next_cursor, more = query.fetch_page(
        settings.SANTA_RULE_BATCH_SIZE,
        start_cursor=datastore_query.Cursor(urlsafe=cursor))

    # Process the received rules.
    response_rules = []
    for rule in rules:
      epoch = datetime.datetime.utcfromtimestamp(0)
      creation_timestamp = (rule.updated_dt - epoch).total_seconds()
      rule_dict = {
          santa_const.RULE_DOWNLOAD.SHA256: rule.key.parent().id(),
          santa_const.RULE_DOWNLOAD.RULE_TYPE: rule.rule_type,
          santa_const.RULE_DOWNLOAD.POLICY: rule.policy,
          santa_const.RULE_DOWNLOAD.CUSTOM_MSG: rule.custom_msg,
          santa_const.RULE_DOWNLOAD.CREATION_TIME: creation_timestamp}

      if rule.rule_type == common_const.RULE_TYPE.PACKAGE:
        # For Bundles, each binary member should have a separate rule generated
        # with a policy type matching that of the PACKAGE rule.
        binary_ids = rule.bundle_binary_ids
        binary_count = len(binary_ids)
        logging.info('Syncing %s bundle rules', binary_ids)
        for id_ in binary_ids:
          dict_ = rule_dict.copy()
          dict_.update({
              santa_const.RULE_DOWNLOAD.SHA256: id_,
              santa_const.RULE_DOWNLOAD.RULE_TYPE:
                  common_const.RULE_TYPE.BINARY,
              santa_const.RULE_DOWNLOAD.FILE_BUNDLE_BINARY_COUNT: binary_count,
              santa_const.RULE_DOWNLOAD.FILE_BUNDLE_HASH: rule.key.parent().id()
          })
          response_rules.append(dict_)
      else:
        response_rules.append(rule_dict)

    # Prepare the response, include the cursor if there are more rules.
    response = {santa_const.RULE_DOWNLOAD.RULES: response_rules}
    if more:
      response[santa_const.RULE_DOWNLOAD.CURSOR] = next_cursor.urlsafe()

    self.respond_json(response)


class PostflightHandler(BaseSantaApiHandler):
  """Postflight handler. Updates the sync timestamp for the next sync."""
  # Client do not send any JSON with this request.
  SHOULD_PARSE_JSON = False

  @property
  def RequestCounter(self):
    return monitoring.postflight_requests

  @handlers.RecordRequest
  def post(self, uuid):
    self.host.last_postflight_dt = datetime.datetime.utcnow()
    self.host.rule_sync_dt = self.host.last_preflight_dt
    self.host.put()

    host_id = self.host.key.id()
    tables.HOST.InsertRow(
        device_id=host_id,
        timestamp=self.host.last_postflight_dt,
        action=common_const.HOST_ACTION.FULL_SYNC,
        hostname=self.host.hostname,
        platform=common_const.PLATFORM.MACOS,
        users=santa_models.SantaHost.GetAssociatedUsers(host_id),
        mode=self.host.client_mode)
