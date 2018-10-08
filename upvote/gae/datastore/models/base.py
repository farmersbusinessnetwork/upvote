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

"""Model definitions for Upvote."""
import datetime
import hashlib
import logging

from google.appengine.ext import ndb
from google.appengine.ext.ndb import polymodel

from upvote.gae.bigquery import tables
from upvote.gae.datastore import utils as model_utils
from upvote.gae.datastore.models import mixin
from upvote.gae.datastore.models import user as user_models
from upvote.gae.shared.common import settings
from upvote.gae.shared.common import user_map
from upvote.shared import constants


# Done for the sake of brevity.
LOCAL = constants.RULE_SCOPE.LOCAL
GLOBAL = constants.RULE_SCOPE.GLOBAL


class Error(Exception):
  """Base error for models."""


class InvalidArgumentError(Error):
  """The called function received an invalid argument."""


class Event(mixin.Base, polymodel.PolyModel):
  """Blockable Event.

  key = Key(User, user_email) -> Key(Host, host_id) ->
      Key(..., Blockable, hash) -> Key(Event, '1')
  NOTE: The Blockable key may be of any length (e.g. for Bundles).
  NOTE: The Event id is always '1'.

  Attributes:
    blockable_key: key, key to the blockable associated with this event.
    cert_key: key, key to the cert associated with this event.
    host_id: str, unique ID for the host on which this event occurred.
    file_name: str, filename of the blockable on last block.
    file_path: str, path of the blockable on last block.
    publisher: str, publisher of this file.
    version: str, version number of this file.
    executing_user: str, user who executed the binary (may be a system user).
    event_type: str, reason this event was initially created.
    recorded_dt: datetime, when this event was received by the server.
    first_blocked_dt: datetime, time of the first block.
    last_blocked_dt: datetime, time of the last block.
    count: int, the number of times a given event has occurred.
  """
  blockable_key = ndb.KeyProperty()
  cert_key = ndb.KeyProperty()
  file_name = ndb.StringProperty()
  file_path = ndb.StringProperty()
  publisher = ndb.StringProperty()
  version = ndb.StringProperty()

  host_id = ndb.StringProperty()
  executing_user = ndb.StringProperty()
  event_type = ndb.StringProperty(
      choices=constants.EVENT_TYPE.SET_ALL, required=True)

  recorded_dt = ndb.DateTimeProperty(auto_now_add=True)
  first_blocked_dt = ndb.DateTimeProperty()
  last_blocked_dt = ndb.DateTimeProperty()
  count = ndb.IntegerProperty(default=1)

  @property
  def run_by_local_admin(self):
    """Whether the Event was generated by the platform's admin user.

    Due to the platform-specific nature of "admin user," this property should be
    overridden by each platform's derivative models.

    Returns:
      bool, See method description.
    """
    return False

  @property
  def user_key(self):
    if not self.key:
      return None
    return ndb.Key(flat=self.key.pairs()[0])

  def _DedupeEarlierEvent(self, earlier_event):
    """Updates if the related Event occurred earlier than the current one."""
    self.first_blocked_dt = earlier_event.first_blocked_dt
    self.event_type = earlier_event.event_type

  def _DedupeMoreRecentEvent(self, more_recent_event):
    """Updates if the related Event is more recent than the current one."""
    self.last_blocked_dt = more_recent_event.last_blocked_dt
    self.file_name = more_recent_event.file_name
    self.file_path = more_recent_event.file_path
    self.executing_user = more_recent_event.executing_user

  def Dedupe(self, related_event):
    """Updates the current Event state with another, related Event."""
    self.count += related_event.count or 1

    # related_event registered an Event earlier than the earliest recorded date
    if self.first_blocked_dt > related_event.first_blocked_dt:
      self._DedupeEarlierEvent(related_event)

    # related_event registered an Event more recently than the most recent
    # recorded date
    if self.last_blocked_dt < related_event.last_blocked_dt:
      self._DedupeMoreRecentEvent(related_event)

  def GetKeysToInsert(self, logged_in_users, host_owners):
    """Returns the list of keys with which this event should be inserted."""
    if settings.EVENT_CREATION == constants.EVENT_CREATION.EXECUTING_USER:
      if self.run_by_local_admin:
        usernames = logged_in_users
      else:
        usernames = [self.executing_user] if self.executing_user else []
    else:  # HOST_OWNERS
      usernames = host_owners

    emails = [user_map.UsernameToEmail(username) for username in usernames]

    keys = []
    for email in emails:
      key_pairs = [
          (user_models.User, email.lower()), (Host, self.host_id)]
      key_pairs += self.blockable_key.pairs()
      key_pairs += [(Event, '1')]
      keys.append(ndb.Key(pairs=key_pairs))
    return keys

  @classmethod
  def DedupeMultiple(cls, events):
    """Dedupes an iterable of new-style Events.

    Args:
      events: An iterable of new-style Event entities to be deduped.

    Returns:
      A list of deduped Events.
    """
    distinct_events = {}
    for event in events:
      duped_event = distinct_events.get(event.key)
      if duped_event:
        duped_event.Dedupe(event)
      else:
        distinct_events[event.key] = event
    return distinct_events.values()

  def to_dict(self, include=None, exclude=None):  # pylint: disable=g-bad-name
    result = super(Event, self).to_dict(include=include, exclude=exclude)
    result['blockable_id'] = self.blockable_key.id()
    return result


class Note(polymodel.PolyModel):
  """An entity used for annotating other entities.

  Attributes:
    message: The text of the note.
    author: The username of this note's author.
    changelists: Integer list of relevant changelist IDs.
    bugs: Integer list of relevant bug IDs.
    tickets: Integer list of relevant ticket IDs.
  """
  message = ndb.TextProperty()
  author = ndb.StringProperty()
  changelists = ndb.IntegerProperty(repeated=True)
  bugs = ndb.IntegerProperty(repeated=True)
  tickets = ndb.IntegerProperty(repeated=True)
  recorded_dt = ndb.DateTimeProperty(auto_now_add=True)

  @classmethod
  def GenerateKey(cls, message, parent):
    key_hash = hashlib.sha256(message).hexdigest()
    return ndb.Key(Note, key_hash, parent=parent)


class Blockable(mixin.Base, polymodel.PolyModel):
  """An entity that has been blocked.

  key = id of blockable file

  Attributes:
    id_type: str, type of the id used as the key.
    blockable_hash: str, the hash of the blockable, may also be the id.
    file_name: str, name of the file this blockable represents.
    publisher: str, name of the publisher of the file.
    product_name: str, Product name.
    version: str, Product version.

    occurred_dt: datetime, when the blockable was first seen.
    updated_dt: datetime, when this blockable was last updated.
    recorded_dt: datetime, when this file was first seen.

    score: int, social-voting score for this blockable.

    flagged: bool, True if a user has flagged this file as potentially unsafe.

    notes: str[], list of notes attached to this blockable.
    state: str, state of this blockable
    state_change_dt: datetime, when the state of this blockable changed.
  """

  def _CalculateScore(self):
    # NOTE: Since the 'score' property is a ComputedProperty, it will
    # be re-computed before every put. Consequently, when a Blockable is put for
    # the first time, we won't see a pre-existing value for 'score'. Here, we
    # avoid the score calculation for newly-created Blockables as they shouldn't
    # have any Votes associated with them and, thus, should have a score of 0.
    if not model_utils.HasValue(self, 'score'):
      return 0

    tally = 0
    votes = self.GetVotes()
    for vote in votes:
      if vote.was_yes_vote:
        tally += vote.weight
      else:
        tally -= vote.weight
    return tally

  id_type = ndb.StringProperty(choices=constants.ID_TYPE.SET_ALL, required=True)
  blockable_hash = ndb.StringProperty()
  file_name = ndb.StringProperty()
  publisher = ndb.StringProperty()
  product_name = ndb.StringProperty()
  version = ndb.StringProperty()

  occurred_dt = ndb.DateTimeProperty()
  updated_dt = ndb.DateTimeProperty(auto_now=True)
  recorded_dt = ndb.DateTimeProperty(auto_now_add=True)

  flagged = ndb.BooleanProperty(default=False)

  notes = ndb.KeyProperty(kind=Note, repeated=True)
  state = ndb.StringProperty(
      choices=constants.STATE.SET_ALL,
      required=True,
      default=constants.STATE.UNTRUSTED)
  state_change_dt = ndb.DateTimeProperty(auto_now_add=True)

  score = ndb.ComputedProperty(_CalculateScore)

  def ChangeState(self, new_state):
    """Helper method for changing the state of this Blockable.

    Args:
      new_state: New state value to set.
    """
    self.state = new_state
    self.state_change_dt = datetime.datetime.utcnow()
    self.put()

    self.InsertBigQueryRow(
        constants.BLOCK_ACTION.STATE_CHANGE, timestamp=self.state_change_dt)

  def GetRules(self, in_effect=True):
    """Queries for all Rules associated with blockable.

    Args:
      in_effect: bool, return only rules that are currently in effect.

    Returns:
      A list of Rules.
    """
    query = Rule.query(ancestor=self.key)
    if in_effect:
      # pylint: disable=g-explicit-bool-comparison, singleton-comparison
      query = query.filter(Rule.in_effect == True)
      # pylint: enable=g-explicit-bool-comparison, singleton-comparison
    return query.fetch()

  def GetVotes(self):
    """Queries for all Votes cast for this Blockable.

    Returns:
      A list of cast Votes.
    """
    # pylint: disable=g-explicit-bool-comparison, singleton-comparison
    return Vote.query(Vote.in_effect == True, ancestor=self.key).fetch()
    # pylint: enable=g-explicit-bool-comparison, singleton-comparison

  def GetStrongestVote(self):
    """Retrieves the 'strongest' vote cast for this Blockable.

    Intended to help replace the need for the 'social_tag' property of the
    models.Request class.

    Returns:
      The 'strongest' Vote cast for this Blockable (i.e. the Vote whose value
      has the largest magnitude), or None if no Votes have been cast.
    """
    votes = self.GetVotes()
    return max(votes, key=lambda vote: abs(vote.weight)) if votes else None

  def GetEvents(self):
    """Retrieves all Events for this Blockable.

    Intended to help replace the need for the 'request' property of the
    models.BlockEvent class, since DB ReferenceProperties don't appear to exist
    in NDB.

    Returns:
      A list of all Event entities associated with this Blockable.
    """
    return Event.query(Event.blockable_key == self.key).fetch()

  def IsVotingAllowed(self, current_user=None):
    """Method to check if voting is allowed.

    Args:
      current_user: The optional User whose voting privileges should be
          evaluated against this Blockable. If not provided, the current
          AppEngine user will be used instead.

    Returns:
      A (boolean, string) tuple. The boolean indicates whether voting is
      allowed. The string provides an explanation if the boolean is False, and
      will be None otherwise.
    """
    # Even admins can't vote on banned or globally whitelisted blockables.
    if self.state in constants.VOTING_PROHIBITED_REASONS.PROHIBITED_STATES:
      return (False, self.state)

    current_user = current_user or user_models.User.GetOrInsert()

    if self.state in constants.STATE.SET_VOTING_ALLOWED_ADMIN_ONLY:
      if current_user.is_admin:
        return (True, None)
      else:
        return (False, constants.VOTING_PROHIBITED_REASONS.ADMIN_ONLY)

    if isinstance(self, Certificate) and not current_user.is_admin:
      return (False, constants.VOTING_PROHIBITED_REASONS.ADMIN_ONLY)

    # At this point the state must be in SET_VOTING_ALLOWED, so just check the
    # permissions of the current user.
    if current_user.HasPermissionTo(constants.PERMISSIONS.FLAG):
      return (True, None)
    else:
      return (
          False, constants.VOTING_PROHIBITED_REASONS.INSUFFICIENT_PERMISSION)

  def ResetState(self):
    """Resets blockable to UNTRUSTED with no votes."""
    self.state = constants.STATE.UNTRUSTED
    self.state_change_dt = datetime.datetime.utcnow()
    self.flagged = False
    self.put()

    self.InsertBigQueryRow(
        constants.BLOCK_ACTION.RESET, timestamp=self.state_change_dt)

  def to_dict(self, include=None, exclude=None):  # pylint: disable=g-bad-name
    if exclude is None: exclude = []
    exclude += ['score']
    result = super(Blockable, self).to_dict(include=include, exclude=exclude)

    # NOTE: This is not ideal but it prevents CalculateScore from being
    # called when serializing Blockables. This will return an inaccurate value
    # if a vote was cast after the Blockable was retrieved but this can be
    # avoided by wrapping the call to to_dict in a transaction.
    result['score'] = model_utils.GetLocalComputedPropertyValue(self, 'score')

    allowed, reason = self.IsVotingAllowed()
    result['is_voting_allowed'] = allowed
    result['voting_prohibited_reason'] = reason
    if not allowed:
      logging.info('Voting on this Blockable is not allowed (%s)', reason)
    return result


class Binary(Blockable):
  """A binary to be blocked.

  Attributes:
    cert_key: The Key to the Certificate entity of the binary's signing cert.
  """
  cert_key = ndb.KeyProperty()

  @property
  def rule_type(self):
    return constants.RULE_TYPE.BINARY

  @property
  def cert_id(self):
    return self.cert_key and self.cert_key.id()

  @classmethod
  def TranslatePropertyQuery(cls, field, value):
    if field == 'cert_id':
      if value:
        cert_key = ndb.Key(Certificate, value).urlsafe()
      else:
        cert_key = None
      return 'cert_key', cert_key
    return field, value

  def to_dict(self, include=None, exclude=None):  # pylint: disable=g-bad-name
    result = super(Binary, self).to_dict(include=include, exclude=exclude)
    result['cert_id'] = self.cert_id
    return result

  def InsertBigQueryRow(self, action, **kwargs):

    defaults = {
        'sha256': self.key.id(),
        'timestamp': datetime.datetime.utcnow(),
        'action': action,
        'state': self.state,
        'score': self.score,
        'platform': self.GetPlatformName(),
        'client': self.GetClientName(),
        'first_seen_file_name': self.file_name,
        'cert_fingerprint': self.cert_id}
    defaults.update(kwargs.copy())

    tables.BINARY.InsertRow(**defaults)


class Certificate(Blockable):
  """A codesigning certificate that has been encountered by Upvote."""

  @property
  def rule_type(self):
    return constants.RULE_TYPE.CERTIFICATE

  def InsertBigQueryRow(self, action, **kwargs):

    defaults = {
        'fingerprint': self.key.id(),
        'timestamp': datetime.datetime.utcnow(),
        'action': action,
        'state': self.state,
        'score': self.score}
    defaults.update(kwargs.copy())

    tables.CERTIFICATE.InsertRow(**defaults)


class Package(Blockable):

  @property
  def rule_type(self):
    return constants.RULE_TYPE.PACKAGE


class Host(mixin.Base, polymodel.PolyModel):
  """A device running client software and has interacted with Upvote.

  key = Device UUID reported by client.

  Attributes:
    hostname: str, the hostname at last preflight.
    recorded_dt: datetime, time of insertion.
    hidden: boolean, whether the host will be hidden from the user by default.
  """
  hostname = ndb.StringProperty()
  recorded_dt = ndb.DateTimeProperty(auto_now_add=True)
  hidden = ndb.BooleanProperty(default=False)

  @classmethod
  def GetAssociatedHostIds(cls, user):
    """Returns the IDs of each host which is associated with the given user.

    NOTE: What consitutes "associated with" is platform-dependent and should be
    defined for each inheriting class.

    Args:
      user: User, The user for which associated hosts should be fetched.

    Returns:
      list of str, A list of host IDs for hosts associated with the provided
          user.
    """
    raise NotImplementedError

  def IsAssociatedWithUser(self, user):
    """Returns whether the given user is associated with this host.

    NOTE: What consitutes "associated with" is platform-dependent and should be
    defined for each inheriting class.

    Args:
      user: User, The user whose association will be tested.

    Returns:
      bool, Whether the user is associated with this host.
    """
    raise NotImplementedError

  @staticmethod
  def NormalizeId(host_id):
    return host_id.upper()


class Vote(mixin.Base, ndb.Model):
  """An individual vote on a blockable cast by a user.

  key = Key(Blockable, hash) -> Key(User, email) -> Key(Vote, 'InEffect')

  Attributes:
    user_email: str, the email of the voting user at the time of the vote.
    was_yes_vote: boolean, True if the vote was "Yes."
    recorded_dt: DateTime, time of vote.
    value: Int, the value of the vote at the time of voting, based on the value
        of the users vote.
    candidate_type: str, the type of blockable being voted on.
    blockable_key: Key, the key of the blockable being voted on.
    in_effect: boolean, True if the vote counts towards the blockable score.
  """
  _IN_EFFECT_KEY_NAME = 'InEffect'

  def _ComputeBlockableKey(self):
    if not self.key:
      return None
    pairs = self.key.pairs()
    if len(pairs) < 3:
      return None
    return ndb.Key(pairs=pairs[:-2])

  user_email = ndb.StringProperty(required=True)
  was_yes_vote = ndb.BooleanProperty(required=True, default=True)
  recorded_dt = ndb.DateTimeProperty(auto_now_add=True)
  weight = ndb.IntegerProperty(default=0)
  candidate_type = ndb.StringProperty(
      choices=constants.RULE_TYPE.SET_ALL, required=True)
  blockable_key = ndb.ComputedProperty(_ComputeBlockableKey)
  in_effect = ndb.ComputedProperty(
      lambda self: self.key and self.key.flat()[-1] == Vote._IN_EFFECT_KEY_NAME)

  @classmethod
  def GetKey(cls, blockable_key, user_key, in_effect=True):
    # In the in_effect == False case, the None ID field of the key will cause
    # NDB to generate a random one when the vote is put.
    vote_id = Vote._IN_EFFECT_KEY_NAME if in_effect else None
    return model_utils.ConcatenateKeys(
        blockable_key, user_key, ndb.Key(Vote, vote_id))

  @property
  def effective_weight(self):
    return self.weight if self.was_yes_vote else -self.weight

  @property
  def user_key(self):
    return ndb.Key(user_models.User, self.user_email.lower())


class Rule(mixin.Base, polymodel.PolyModel):
  """A rule generated from voting or manually inserted by an authorized user.

  Attributes:
    rule_type: string, the type of blockable the rule applies to, ie
        binary, certificate.
    policy: string, the assertion of the rule, ie whitelisted, blacklisted.
    in_effect: bool, is this rule still in effect. Set to False when superceded.
    recorded_dt: datetime, insertion time.
    host_id: str, id of the host or blank for global.
    user_key: key, for locally scoped rules, the user for whom the rule was
        created.
  """
  rule_type = ndb.StringProperty(
      choices=constants.RULE_TYPE.SET_ALL, required=True)
  policy = ndb.StringProperty(
      choices=constants.RULE_POLICY.SET_ALL, required=True)
  in_effect = ndb.BooleanProperty(default=True)
  recorded_dt = ndb.DateTimeProperty(auto_now_add=True)
  updated_dt = ndb.DateTimeProperty(auto_now=True)
  host_id = ndb.StringProperty(default='')
  user_key = ndb.KeyProperty()

  def MarkDisabled(self):
    self.in_effect = False

  def InsertBigQueryRow(self, **kwargs):

    user = (
        user_map.EmailToUsername(self.user_key.id()) if self.user_key else None)

    defaults = {
        'sha256': self.key.parent().id(),
        'timestamp': datetime.datetime.utcnow(),
        'scope': LOCAL if self.host_id or self.user_key else GLOBAL,
        'policy': self.policy,
        'target_type': self.rule_type,
        'device_id': self.host_id if self.host_id else None,
        'user': user}
    defaults.update(kwargs.copy())

    tables.RULE.InsertRow(**defaults)
