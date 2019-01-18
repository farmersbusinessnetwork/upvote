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

"""Tests for voting logic."""

import mock

from google.appengine.ext import ndb

from upvote.gae import settings
from upvote.gae.datastore import test_utils
from upvote.gae.datastore import utils as datastore_utils
from upvote.gae.datastore.models import base
from upvote.gae.datastore.models import bit9
from upvote.gae.datastore.models import host as host_models
from upvote.gae.datastore.models import santa
from upvote.gae.datastore.models import user as user_models
from upvote.gae.datastore.models import vote as vote_models
from upvote.gae.lib.testing import basetest
from upvote.gae.lib.voting import api
from upvote.shared import constants


TABLE = constants.BIGQUERY_TABLE  # Done for the sake of brevity.


def CreateEvent(blockable, host, user):
  return test_utils.CreateSantaEvent(
      blockable, host_id=host.key.id(), executing_user=user.nickname,
      parent=datastore_utils.ConcatenateKeys(user.key, host.key, blockable.key))


class GetBlockableTest(basetest.UpvoteTestCase):

  def testFound(self):
    sha256 = test_utils.RandomSHA256()
    test_utils.CreateSantaBlockable(id=sha256)
    self.assertIsNotNone(api._GetBlockable(sha256))

  def testNotFound(self):
    sha256 = test_utils.RandomSHA256()
    test_utils.CreateSantaBlockable(id=sha256)
    with self.assertRaises(api.BlockableNotFoundError):
      api._GetBlockable('abcdef')


class GetPlatformTest(basetest.UpvoteTestCase):

  def testSupported(self):
    blockable = test_utils.CreateSantaBlockable()
    platform = api._GetPlatform(blockable)
    self.assertEqual(constants.PLATFORM.MACOS, platform)

  def testUnsupported(self):
    blockable = test_utils.CreateBlockable()
    with self.assertRaises(api.UnsupportedPlatformError):
      api._GetPlatform(blockable)


class VoteTest(basetest.UpvoteTestCase):

  def testInvalidVoteWeightError(self):
    sha256 = test_utils.RandomSHA256()
    test_utils.CreateSantaBlockable(id=sha256)
    with self.assertRaises(api.InvalidVoteWeightError):
      with self.LoggedInUser() as user:
        api.Vote(user, sha256, True, -1)


class BallotBoxTest(basetest.UpvoteTestCase):

  def setUp(self):
    super(BallotBoxTest, self).setUp()

    self.santa_blockable1 = test_utils.CreateSantaBlockable(
        id='aaaabbbbccccddddeeeeffffgggg')

    self.santa_blockable3 = test_utils.CreateSantaBlockable()
    self.santa_blockable4 = test_utils.CreateSantaBlockable()
    self.santa_bundle_blockables = (
        self.santa_blockable3, self.santa_blockable4)
    self.santa_bundle = test_utils.CreateSantaBundle(
        bundle_binaries=self.santa_bundle_blockables)

    self.local_threshold = settings.VOTING_THRESHOLDS[
        constants.STATE.APPROVED_FOR_LOCAL_WHITELISTING]

    self.PatchEnv(settings.ProdEnv, ENABLE_BIGQUERY_STREAMING=True)

  def testRowPersistence_Bit9(self):
    binary = test_utils.CreateBit9Binary()
    user = test_utils.CreateUser()
    test_utils.CreateBit9Host(users=[user.nickname])

    ballot_box = api.Bit9BallotBox(binary.key.id())
    with self.LoggedInUser(user=user):
      ballot_box.Vote(True, user, vote_weight=self.local_threshold)

    self.assertTaskCount(constants.TASK_QUEUE.BIT9_COMMIT_CHANGE, 1)

    # 1 VoteRow, 1 Binary Row for Score Change, 1 Binary Row for State Change
    self.assertBigQueryInsertions([
        TABLE.BINARY, TABLE.BINARY,
        TABLE.VOTE, TABLE.RULE], reset_mock=False)

    # Verify the score change in BigQuery.
    predicate = lambda c: c[1].get('action') == 'SCORE_CHANGE'
    calls = self.GetBigQueryCalls(predicate=predicate)
    self.assertLen(calls, 1)
    self.assertEqual(self.local_threshold, calls[0][1].get('score'))

  def testRowPersistence_Santa(self):

    user = test_utils.CreateUser()
    test_utils.CreateSantaHost(primary_user=user.nickname)
    ballot_box = api.SantaBallotBox(self.santa_blockable1.key.id())

    with self.LoggedInUser(user=user):
      ballot_box.Vote(True, user, vote_weight=self.local_threshold)

    # 1 VoteRow, 1 Binary Row for Score Change, 1 Binary Row for State Change
    self.assertBigQueryInsertions([
        TABLE.BINARY, TABLE.BINARY, TABLE.VOTE, TABLE.RULE], reset_mock=False)

    # Verify the score change in BigQuery.
    predicate = lambda c: c[1].get('action') == 'SCORE_CHANGE'
    calls = self.GetBigQueryCalls(predicate=predicate)
    self.assertLen(calls, 1)
    self.assertEqual(self.local_threshold, calls[0][1].get('score'))

  def testBit9(self):
    binary = test_utils.CreateBit9Binary()
    user = test_utils.CreateUser()
    host = test_utils.CreateBit9Host(users=[user.nickname])

    ballot_box = api.Bit9BallotBox(binary.key.id())
    with self.LoggedInUser(user=user):
      ballot_box.Vote(True, user, vote_weight=self.local_threshold)

    self.assertEqual(self.local_threshold, binary.score)

    rules = binary.GetRules()
    self.assertLen(rules, 1)
    self.assertFalse(rules[0].is_committed)
    self.assertTrue(rules[0].in_effect)
    self.assertEqual(user.key, rules[0].user_key)
    self.assertEqual(host.key.id(), rules[0].host_id)

    changes = bit9.RuleChangeSet.query().fetch()
    self.assertLen(changes, 1)
    self.assertSameElements([rules[0].key], changes[0].rule_keys)
    self.assertEqual(constants.RULE_POLICY.WHITELIST, changes[0].change_type)
    self.assertTrue(datastore_utils.KeyHasAncestor(changes[0].key, binary.key))

    self.assertTaskCount(constants.TASK_QUEUE.BIT9_COMMIT_CHANGE, 1)

    self.assertBigQueryInsertions(
        [TABLE.VOTE, TABLE.BINARY, TABLE.BINARY, TABLE.RULE])

  def testBit9_NoRules(self):
    binary = test_utils.CreateBit9Binary()

    ballot_box = api.Bit9BallotBox(binary.key.id())
    with self.LoggedInUser() as user:
      ballot_box.Vote(True, user, vote_weight=self.local_threshold)

    self.assertEqual(self.local_threshold, binary.score)
    self.assertLen(binary.GetRules(), 0)
    self.assertEqual(0, bit9.RuleChangeSet.query().count())

    self.assertTaskCount(constants.TASK_QUEUE.BIT9_COMMIT_CHANGE, 0)

    self.assertBigQueryInsertions([TABLE.VOTE, TABLE.BINARY, TABLE.BINARY])

  def testYesVote_FromUser(self):
    """Normal vote on normal blockable."""

    ballot_box = api.SantaBallotBox(self.santa_blockable1.key.id())
    with self.LoggedInUser() as user:
      ballot_box.Vote(True, user)

    blockable = self.santa_blockable1.key.get()

    self.assertEqual(blockable.score, 1)

    self.assertBigQueryInsertions([TABLE.VOTE, TABLE.BINARY], reset_mock=False)

    # Verify the score change in BigQuery.
    predicate = lambda c: c[1].get('action') == 'SCORE_CHANGE'
    calls = self.GetBigQueryCalls(predicate=predicate)
    self.assertLen(calls, 1)
    self.assertEqual(1, calls[0][1].get('score'))

  def testNoVote_FromUser(self):
    """Normal no vote on normal blockable."""

    ballot_box = api.SantaBallotBox(self.santa_blockable1.key.id())
    with self.LoggedInUser() as user:
      ballot_box.Vote(False, user)

      blockable = self.santa_blockable1.key.get()

      expectations = {
          'score': -user.vote_weight,
          'flagged': True}
      self.assertDictContainsSubset(expectations, blockable.to_dict())

    self.assertBigQueryInsertions([TABLE.VOTE, TABLE.BINARY], reset_mock=False)

    # Verify the score change in BigQuery.
    predicate = lambda c: c[1].get('action') == 'SCORE_CHANGE'
    calls = self.GetBigQueryCalls(predicate=predicate)
    self.assertLen(calls, 1)
    self.assertEqual(-user.vote_weight, calls[0][1].get('score'))

  def testNoVote_SantaBundle(self):
    """Restrict no vote for bundles."""

    ballot_box = api.SantaBallotBox(self.santa_bundle.key.id())
    with self.assertRaises(api.OperationNotAllowedError):
      with self.LoggedInUser() as user:
        ballot_box.Vote(False, user)

  def testFromUser_WithCert(self):
    """Normal vote on signed blockable."""

    cert = test_utils.CreateSantaCertificate()
    self.santa_blockable1.cert_key = cert.key
    self.santa_blockable1.put()
    user = test_utils.CreateUser()

    ballot_box = api.SantaBallotBox(self.santa_blockable1.key.id())
    with self.LoggedInUser(user=user):
      ballot_box.Vote(True, user)

    blockable = self.santa_blockable1.key.get()

    self.assertEqual(user.vote_weight, blockable.score)

    self.assertBigQueryInsertions([TABLE.VOTE, TABLE.BINARY], reset_mock=False)

    # Verify the score change in BigQuery.
    predicate = lambda c: c[1].get('action') == 'SCORE_CHANGE'
    calls = self.GetBigQueryCalls(predicate=predicate)
    self.assertLen(calls, 1)
    self.assertEqual(user.vote_weight, calls[0][1].get('score'))

  def testFromUser_VoteWeight(self):
    """Normal vote on normal blockable with different vote weight."""

    user = test_utils.CreateUser()
    test_utils.CreateSantaHost(primary_user=user.nickname)
    new_weight = self.local_threshold + 1
    ballot_box = api.SantaBallotBox(self.santa_blockable1.key.id())
    with self.LoggedInUser(user=user):
      ballot_box.Vote(True, user, vote_weight=new_weight)

    blockable = self.santa_blockable1.key.get()

    self.assertEqual(blockable.score, new_weight)

    self.assertBigQueryInsertions(
        [TABLE.VOTE, TABLE.BINARY, TABLE.BINARY, TABLE.RULE], reset_mock=False)

    # Verify the score change in BigQuery.
    predicate = lambda c: c[1].get('action') == 'SCORE_CHANGE'
    calls = self.GetBigQueryCalls(predicate=predicate)
    self.assertLen(calls, 1)
    self.assertEqual(blockable.score, calls[0][1].get('score'))

  def testFromUser_VoteWeight_Zero(self):
    """Normal vote on normal blockable with 0 vote weight."""

    new_weight = 0
    ballot_box = api.SantaBallotBox(self.santa_blockable1.key.id())
    with self.LoggedInUser() as user:
      ballot_box.Vote(True, user, vote_weight=new_weight)

    blockable = self.santa_blockable1.key.get()

    self.assertEqual(blockable.score, new_weight)
    self.assertBigQueryInsertion(TABLE.VOTE)

  def testChangingVotes(self):
    """Normal vote on normal blockable."""

    ballot_box = api.SantaBallotBox(self.santa_blockable1.key.id())
    with self.LoggedInUser() as user:
      ballot_box.Vote(True, user)
      ballot_box.Vote(False, user)
      ballot_box.Vote(True, user)

    blockable = self.santa_blockable1.key.get()

    self.assertEqual(blockable.score, 1)

    # SCORE_CHANGE x3
    self.assertBigQueryInsertions([TABLE.VOTE, TABLE.BINARY] * 3)

  def testFromUser_ArchivedVotes(self):
    """Normal vote on normal blockable with old votes."""

    user = test_utils.CreateUser()

    # Create an active no vote.
    vote = test_utils.CreateVote(
        self.santa_blockable1, user_email=user.email, was_yes_vote=False)
    vote.key.delete()

    # Create several inactive yes votes.
    vote.was_yes_vote = True
    for _ in xrange(10):
      vote.key = vote_models.Vote.GetKey(
          self.santa_blockable1.key, user.key, in_effect=False)
      vote.put()

    # Attempt to change in effect vote to yes.
    ballot_box = api.SantaBallotBox(self.santa_blockable1.key.id())
    with self.LoggedInUser(user=user):
      ballot_box.Vote(True, user)

    blockable = self.santa_blockable1.key.get()

    self.assertEqual(blockable.score, 1)
    self.assertBigQueryInsertions([TABLE.VOTE, TABLE.BINARY], reset_mock=False)

    # Verify the score change in BigQuery.
    predicate = lambda c: c[1].get('action') == 'SCORE_CHANGE'
    calls = self.GetBigQueryCalls(predicate=predicate)
    self.assertLen(calls, 1)
    self.assertEqual(blockable.score, calls[0][1].get('score'))

  def testFromUser_ArchivedVote_NewVoteWeight(self):
    """Normal vote on normal blockable with old votes."""

    user = test_utils.CreateUser()

    # Create an active no vote.
    test_utils.CreateVote(
        self.santa_blockable1, user_email=user.email, was_yes_vote=False)

    # Attempt to change in effect vote to yes.
    new_weight = self.local_threshold + 1
    ballot_box = api.SantaBallotBox(self.santa_blockable1.key.id())
    with self.LoggedInUser(user=user):
      ballot_box.Vote(True, user, vote_weight=new_weight)

    blockable = self.santa_blockable1.key.get()

    self.assertEqual(blockable.score, new_weight)

    votes = vote_models.Vote.query(ancestor=self.santa_blockable1.key).fetch()
    self.assertLen(votes, 2)

    old_vote = next(vote for vote in votes if not vote.in_effect)
    self.assertNotEqual(new_weight, old_vote.weight)

    new_vote = next(vote for vote in votes if vote.in_effect)
    self.assertEqual(new_weight, new_vote.weight)

    self.assertBigQueryInsertions(
        [TABLE.VOTE, TABLE.BINARY, TABLE.BINARY], reset_mock=False)

    # Verify the score change in BigQuery.
    predicate = lambda c: c[1].get('action') == 'SCORE_CHANGE'
    calls = self.GetBigQueryCalls(predicate=predicate)
    self.assertLen(calls, 1)
    self.assertEqual(blockable.score, calls[0][1].get('score'))

  def testNonexistentBlockable(self):
    """Voting on a blockable that doesn't exist in the datastore."""
    ballot_box = api.SantaBallotBox('bbbbllllfffftttt')
    with self.assertRaises(api.BlockableNotFoundError):
      with self.LoggedInUser() as user:
        ballot_box.Vote(True, user)

  def testYesVote_FromAdmin_FlaggedBlockable(self):
    """Admin voting yes on flagged blockable."""

    user = test_utils.CreateUser()
    admin = test_utils.CreateUser(admin=True)

    self.santa_blockable1 = test_utils.CreateSantaBlockable()
    ballot_box = api.SantaBallotBox(self.santa_blockable1.key.id())
    with self.LoggedInUser(user=user):
      ballot_box.Vote(False, user)
    self.assertTrue(self.santa_blockable1.key.get().flagged)

    with self.LoggedInUser(user=admin):
      ballot_box.Vote(True, admin)

      expectations = {
          'score': -user.vote_weight + admin.vote_weight,
          'flagged': False}
      self.assertDictContainsSubset(
          expectations, self.santa_blockable1.key.get().to_dict())

    self.assertBigQueryInsertions([TABLE.VOTE] * 2 + [TABLE.BINARY] * 3)

  def testYesVote_FromUser_FlaggedBlockable_PreviousNoVote(self):
    """A normal user changing their vote from no to yes on flagged blockable."""

    with self.LoggedInUser() as user:
      self.santa_blockable1 = test_utils.CreateSantaBlockable()
      ballot_box = api.SantaBallotBox(self.santa_blockable1.key.id())
      ballot_box.Vote(False, user)
      self.assertTrue(self.santa_blockable1.key.get().flagged)
      ballot_box.Vote(True, user)

      expectations = {
          'score': user.vote_weight,
          'flagged': False}
      self.assertDictContainsSubset(
          expectations, self.santa_blockable1.key.get().to_dict())

    self.assertBigQueryInsertions([TABLE.VOTE] * 2 + [TABLE.BINARY] * 2)

  def testNoVote_FromAdmin_SuspectBlockable(self):
    """Admin votes no on suspect blockable."""

    suspect_blockable = test_utils.CreateSantaBlockable(
        state=constants.STATE.SUSPECT)

    ballot_box = api.SantaBallotBox(suspect_blockable.key.id())
    with self.LoggedInUser(admin=True) as admin:
      ballot_box.Vote(False, admin)

      expectations = {
          'score': -admin.vote_weight,
          'flagged': True}
      self.assertDictContainsSubset(
          expectations, suspect_blockable.key.get().to_dict())

    self.assertBigQueryInsertions(
        [TABLE.VOTE] + [TABLE.BINARY] * 3, reset_mock=False)

    # Verify the score change in BigQuery.
    predicate = lambda c: c[1].get('action') == 'SCORE_CHANGE'
    calls = self.GetBigQueryCalls(predicate=predicate)
    self.assertLen(calls, 1)
    self.assertEqual(-admin.vote_weight, calls[0][1].get('score'))

  def testYesVote_FromAdmin_SuspectBlockable(self):
    """Admin votes yes on suspect blockable."""

    suspect_blockable = test_utils.CreateSantaBlockable(
        state=constants.STATE.SUSPECT)
    with self.LoggedInUser(admin=True) as admin:

      ballot_box = api.SantaBallotBox(suspect_blockable.key.id())
      ballot_box.Vote(True, admin)

      expectations = {
          'score': admin.vote_weight,
          'flagged': False}
      self.assertDictContainsSubset(
          expectations, suspect_blockable.key.get().to_dict())

    self.assertBigQueryInsertions(
        [TABLE.VOTE] + [TABLE.BINARY] * 2, reset_mock=False)

    # Verify the score change in BigQuery.
    predicate = lambda c: c[1].get('action') == 'SCORE_CHANGE'
    calls = self.GetBigQueryCalls(predicate=predicate)
    self.assertLen(calls, 1)
    self.assertEqual(admin.vote_weight, calls[0][1].get('score'))

  def testGlobalWhitelist(self):
    """2 admins' votes make a blockable globally whitelisted."""

    ballot_box = api.SantaBallotBox(self.santa_blockable1.key.id())
    ballot_box.blockable = self.santa_blockable1

    for admin_user in test_utils.CreateUsers(2, admin=True):
      ballot_box.Vote(True, admin_user)

    self.assertEqual(
        self.santa_blockable1.key.get().state,
        constants.STATE.GLOBALLY_WHITELISTED)

    self.assertBigQueryInsertions(
        [TABLE.VOTE] * 2 + [TABLE.BINARY] * 4 + [TABLE.RULE])

  def testGlobalWhitelist_Bundle(self):
    """2 admins' votes make a bundle globally whitelisted."""

    ballot_box = api.SantaBallotBox(self.santa_bundle.key.id())

    for admin_user in test_utils.CreateUsers(2, admin=True):
      ballot_box.Vote(True, admin_user)

    # Verify that global whitelist rule was created for the bundle.
    rules = santa.SantaRule.query(ancestor=self.santa_bundle.key).fetch()
    self.assertLen(rules, 1)
    self.assertEqual(constants.RULE_TYPE.PACKAGE, rules[0].rule_type)
    self.assertEqual(constants.RULE_POLICY.WHITELIST, rules[0].policy)

    self.assertEqual(
        self.santa_bundle.key.get().state,
        constants.STATE.GLOBALLY_WHITELISTED)

    self.assertBigQueryInsertions(
        [TABLE.VOTE] * 2 + [TABLE.BUNDLE] * 4 + [TABLE.RULE])

  def testLocalWhitelist(self):
    ballot_box = api.SantaBallotBox(self.santa_blockable1.key.id())

    users = test_utils.CreateUsers(self.local_threshold)
    for user in users:
      test_utils.CreateSantaHost(primary_user=user.nickname)
      ballot_box.Vote(True, user)

    self.assertEqual(
        self.santa_blockable1.key.get().state,
        constants.STATE.APPROVED_FOR_LOCAL_WHITELISTING)

    num_vote_rows = len(users)
    num_binary_rows = self.local_threshold + 1
    self.assertBigQueryInsertions(
        [TABLE.VOTE] * num_vote_rows +
        [TABLE.BINARY] * num_binary_rows +
        [TABLE.RULE] * num_vote_rows)

  def testLocalWhitelist_Bundle(self):
    ballot_box = api.SantaBallotBox(self.santa_bundle.key.id())

    users = test_utils.CreateUsers(self.local_threshold)
    with mock.patch.object(
        ballot_box, '_GetHostsToWhitelist', return_value={'a_host'}):
      for user in users:
        ballot_box.Vote(True, user)

    # Verify that local whitelist rules were created for the bundle.
    rules = santa.SantaRule.query(ancestor=self.santa_bundle.key).fetch()
    self.assertLen(rules, self.local_threshold)
    self.assertEqual(constants.RULE_TYPE.PACKAGE, rules[0].rule_type)
    self.assertEqual(constants.RULE_POLICY.WHITELIST, rules[0].policy)

    # Verify that votes were only applied to the bundle and not the members.
    bundle = self.santa_bundle.key.get()
    self.assertEqual(
        bundle.state, constants.STATE.APPROVED_FOR_LOCAL_WHITELISTING)

    for blockable in self.santa_bundle_blockables:
      self.assertEqual(blockable.key.get().state, constants.STATE.UNTRUSTED)

    num_vote_rows = len(users)
    num_bundle_rows = self.local_threshold + 1
    self.assertBigQueryInsertions(
        [TABLE.VOTE] * num_vote_rows +
        [TABLE.BUNDLE] * num_bundle_rows +
        [TABLE.RULE] * len(rules))

  def testAlreadyLocallyWhitelisted(self):
    """Test voting when locally whitelistable, without actual state change."""
    # Simulate a Blockable which has been voted to the point where it is
    # available for local whitelisting.
    sha = test_utils.RandomSHA256()
    blockable = test_utils.CreateSantaBlockable(
        id=sha, state=constants.STATE.APPROVED_FOR_LOCAL_WHITELISTING)

    # Create Users
    users = test_utils.CreateUsers(self.local_threshold)
    admin = test_utils.CreateUser(
        roles=[constants.USER_ROLE.ADMINISTRATOR])
    users.append(admin)

    # Create the Votes.
    for user in users[:-1]:
      test_utils.CreateVote(blockable, user_email=user.email, weight=1)

    # Create the Hosts, Events, and Rules (all but the last one).
    for user in users:
      host = test_utils.CreateSantaHost(primary_user=user.nickname)
      if user != users[-1]:
        test_utils.CreateSantaRule(
            blockable.key, host_id=host.key.id(),
            policy=constants.RULE_POLICY.WHITELIST, user_key=user.key)

    # Verify all the entities.
    self.assertIsNotNone(base.Blockable.get_by_id(sha))
    self.assertEqual(len(users) - 1, len(blockable.GetVotes()))
    self.assertLen(users, host_models.Host.query().count())
    self.assertEqual(len(users) - 1, len(blockable.GetRules()))

    # Ensure that even with a yes vote, the voter can't globally whitelist the
    # Blockable, i.e. can't trigger a state change.
    self.assertTrue(blockable.score + users[-1].vote_weight < 50)

    # The new voter casts a yes vote.
    ballot_box = api.SantaBallotBox(sha)
    ballot_box.Vote(True, users[-1])

    # Verify the Blockable, Votes, and Rules.
    blockable = base.Blockable.get_by_id(sha)
    self.assertEqual(
        constants.STATE.APPROVED_FOR_LOCAL_WHITELISTING, blockable.state)
    self.assertLess(blockable.score, 50)
    self.assertEqual(len(users), len(blockable.GetVotes()))
    self.assertEqual(len(users), len(blockable.GetRules()))

    self.assertBigQueryInsertions([TABLE.VOTE, TABLE.BINARY, TABLE.RULE])

  def testToSuspect_ByAdmin(self):
    """Test changing state to untrusted."""
    blockable = test_utils.CreateSantaBlockable(
        state=constants.STATE.APPROVED_FOR_LOCAL_WHITELISTING)

    ballot_box = api.SantaBallotBox(blockable.key.id())
    with self.LoggedInUser(admin=True) as admin:
      ballot_box.Vote(False, admin)

    self.assertEqual(blockable.key.get().state, constants.STATE.SUSPECT)

    self.assertBigQueryInsertions(
        [TABLE.VOTE] + [TABLE.BINARY] * 3, reset_mock=False)

    # Verify the score change in BigQuery.
    predicate = lambda c: c[1].get('action') == 'SCORE_CHANGE'
    calls = self.GetBigQueryCalls(predicate=predicate)
    self.assertLen(calls, 1)
    self.assertEqual(-admin.vote_weight, calls[0][1].get('score'))

  def testGloballyWhitelist_RuleNoRules(self):
    """Change a blockable state to Globally whitelisted."""
    self.rule1 = base.Rule(
        rule_type=constants.RULE_TYPE.BINARY,
        policy=constants.RULE_POLICY.BLACKLIST,
        in_effect=True,
        parent=self.santa_blockable1.key)

    self.rule1.put()

    blockable = santa.SantaBlockable(
        id=self.santa_blockable1.key.id(),
        id_type=constants.ID_TYPE.SHA256,
        file_name='ginger spider 2',
        flagged=False,
        state=constants.STATE.APPROVED_FOR_LOCAL_WHITELISTING)
    blockable.put()
    test_utils.CreateVote(blockable)
    test_utils.CreateVote(blockable)

    ballot_box = api.SantaBallotBox(blockable.key.id())
    ballot_box.blockable = blockable

    ballot_box._GloballyWhitelist().get_result()

    rule_query = base.Rule.query(ancestor=self.santa_blockable1.key)

    self.assertEqual(rule_query.count(), 2)

    # pylint: disable=g-explicit-bool-comparison, singleton-comparison
    rule_query = rule_query.filter(base.Rule.in_effect == True)
    # pylint: enable=g-explicit-bool-comparison, singleton-comparison

    self.assertEqual(rule_query.count(), 1)

    rule = rule_query.get()

    self.assertEqual(rule.policy, constants.RULE_POLICY.WHITELIST)

    self.assertBigQueryInsertions([TABLE.RULE])

  def testLocallyWhitelist_RulesForAllVoters(self):
    """Create rules for users who voted earlier."""

    user = test_utils.CreateUser()
    other_users = [
        test_utils.CreateUser() for _ in xrange(self.local_threshold - 1)]

    blockable = test_utils.CreateSantaBlockable()
    test_utils.CreateSantaHost(primary_user=user.nickname)

    ballot_box = api.SantaBallotBox(blockable.key.id())
    for other_user in other_users:
      with self.LoggedInUser(user=other_user):
        test_utils.CreateSantaHost(primary_user=other_user.nickname)
        ballot_box.Vote(True, other_user)

    self.assertLen(blockable.GetVotes(), self.local_threshold - 1)
    self.assertEqual(constants.STATE.UNTRUSTED, blockable.state)

    with self.LoggedInUser(user=user):
      ballot_box.Vote(True, user)

    self.assertLen(blockable.GetVotes(), self.local_threshold)

    rules = base.Rule.query().fetch()
    self.assertLen(rules, self.local_threshold)
    self.assertEqual(
        set([other.key for other in other_users] + [user.key]),
        set(rule.user_key for rule in rules))

    num_vote_rows = len(other_users) + 1
    num_binary_rows = self.local_threshold + 1
    self.assertBigQueryInsertions(
        [TABLE.VOTE] * num_vote_rows +
        [TABLE.BINARY] * num_binary_rows +
        [TABLE.RULE] * len(rules))

  def testLocallyWhitelist_OnlyRulesForCurrentVoter(self):
    """Create rules for users who voted earlier."""

    user = test_utils.CreateUser()
    other_users = [
        test_utils.CreateUser() for _ in xrange(self.local_threshold)]

    blockable = test_utils.CreateSantaBlockable()
    test_utils.CreateSantaHost(primary_user=user.nickname)

    ballot_box = api.SantaBallotBox(blockable.key.id())
    for other_user in other_users:
      with self.LoggedInUser(user=other_user):
        test_utils.CreateSantaHost(primary_user=other_user.nickname)
        ballot_box.Vote(True, other_user)

    blockable = blockable.key.get()

    self.assertLen(blockable.GetVotes(), self.local_threshold)
    self.assertEqual(self.local_threshold, blockable.score)
    self.assertEqual(
        constants.STATE.APPROVED_FOR_LOCAL_WHITELISTING, blockable.state)

    with self.LoggedInUser(user=user):
      ballot_box.Vote(True, user)

    self.assertLen(blockable.GetVotes(), self.local_threshold + 1)

    rules = base.Rule.query().fetch()
    self.assertLen(rules, self.local_threshold + 1)
    self.assertEqual(
        set([other.key for other in other_users] + [user.key]),
        set(rule.user_key for rule in rules))

    self.assertBigQueryInsertions(
        [TABLE.VOTE] * (self.local_threshold + 1) +
        [TABLE.BINARY] * (self.local_threshold + 2) +
        [TABLE.RULE] * (self.local_threshold + 1))

  def testLocallyWhitelist_OnlyCreateNewRules(self):
    """Add local rules where a couple already exist."""
    blockable = test_utils.CreateSantaBlockable()
    user = test_utils.CreateUser()
    hosts = test_utils.CreateSantaHosts(3, primary_user=user.nickname)

    # Create rules for the first two hosts
    for host in hosts[:2]:
      test_utils.CreateSantaRule(
          blockable.key,
          policy=constants.RULE_POLICY.WHITELIST,
          in_effect=True,
          rule_type=constants.RULE_TYPE.BINARY,
          user_key=user.key,
          host_id=host.key.id())

    rule_query = base.Rule.query(ancestor=blockable.key)

    self.assertEqual(len(hosts) - 1, rule_query.count())

    # Create users not associated with any host.
    other_users = test_utils.CreateUsers(self.local_threshold - 1)

    ballot_box = api.SantaBallotBox(blockable.key.id())
    for other_user in other_users:
      with self.LoggedInUser(user=other_user):
        ballot_box.Vote(True, other_user)

    with self.LoggedInUser(user=user):
      ballot_box.Vote(True, user)

    # Ensure a new rule was created for the existing user's host.
    self.assertEqual(rule_query.count(), len(hosts))

    rules = rule_query.fetch()
    for rule in rules:
      self.assertEqual(rule.policy, constants.RULE_POLICY.WHITELIST)
      self.assertTrue(rule.in_effect)
      self.assertEqual(rule.rule_type, constants.RULE_TYPE.BINARY)

    self.assertSameElements(
        [host.key.id() for host in hosts],
        [rule.host_id for rule in rules])

    num_vote_rows = len(other_users) + 1
    num_binary_rows = self.local_threshold + 1
    self.assertBigQueryInsertions(
        [TABLE.VOTE] * num_vote_rows +
        [TABLE.BINARY] * num_binary_rows +
        [TABLE.RULE])

  def testLocallyWhitelist_AlteredThreshold(self):

    local_threshold = 10
    num_voters = local_threshold
    num_hosts_per_voter = 10

    voting_thresholds = {
        constants.STATE.BANNED: -26,
        constants.STATE.APPROVED_FOR_LOCAL_WHITELISTING: local_threshold,
        constants.STATE.GLOBALLY_WHITELISTED: 50}
    self.PatchSetting('VOTING_THRESHOLDS', voting_thresholds)

    blockable = test_utils.CreateSantaBlockable()
    ballot_box = api.SantaBallotBox(blockable.key.id())

    # Simulate enough users voting that the local threshold is hit.
    voters = test_utils.CreateUsers(num_voters)
    for voter in voters:
      for _ in xrange(num_hosts_per_voter):
        test_utils.CreateSantaHost(primary_user=voter.nickname)
      with self.LoggedInUser(user=voter):
        ballot_box.Vote(True, voter)

    blockable = blockable.key.get()

    # Verify that the blockable reached the local threshold and is available for
    # anyone else who wants to vote for it.
    self.assertLen(blockable.GetVotes(), local_threshold)
    self.assertEqual(local_threshold, blockable.score)
    self.assertEqual(
        constants.STATE.APPROVED_FOR_LOCAL_WHITELISTING, blockable.state)

    # We should expect to see one local rule for each machine.
    rules = base.Rule.query().fetch()
    expected_rule_count = num_voters * num_hosts_per_voter
    self.assertLen(rules, expected_rule_count)
    self.assertEqual(
        set([voter.key for voter in voters]),
        set(rule.user_key for rule in rules))

    self.assertBigQueryInsertions(
        [TABLE.VOTE] * num_voters +
        [TABLE.BINARY] * (num_voters + 1) +
        [TABLE.RULE] * expected_rule_count)

  def testKeyStructure(self):
    ballot_box = api.SantaBallotBox(self.santa_blockable1.key.id())

    self.assertLen(self.santa_blockable1.GetVotes(), 0)

    with self.LoggedInUser() as user:
      ballot_box.Vote(True, user)

      # Use Blockable.GetVotes to ensure our vote counts towards the blockable's
      # score.
      votes = self.santa_blockable1.GetVotes()
      self.assertLen(votes, 1)
      new_vote = votes[0]

      # Verify that the key is in the expected structure.
      expected_key = ndb.Key(
          base.Blockable, self.santa_blockable1.key.id(),
          user_models.User, user.email, vote_models.Vote,
          vote_models._IN_EFFECT_KEY_NAME)
      self.assertEqual(new_vote, expected_key.get())

    self.assertBigQueryInsertions([TABLE.VOTE, TABLE.BINARY])

  def testDuplicateVote(self):
    user = test_utils.CreateUser()

    ballot_box = api.SantaBallotBox(self.santa_blockable1.key.id())
    ballot_box.Vote(True, user)

    with self.assertRaises(api.DuplicateVoteError):
      ballot_box.Vote(True, user)

    self.assertBigQueryInsertions([TABLE.VOTE, TABLE.BINARY])

  def testChangeVote(self):
    user = test_utils.CreateUser()

    ballot_box = api.SantaBallotBox(self.santa_blockable1.key.id())

    # The user upvotes the blockable.
    ballot_box.Vote(True, user)

    orig_score = self.santa_blockable1.key.get().score

    # The user changes their vote on the blockable.
    ballot_box.Vote(False, user)

    votes = vote_models.Vote.query(ancestor=self.santa_blockable1.key).fetch()
    self.assertTrue(any(vote for vote in votes if vote.in_effect))
    self.assertTrue(any(vote for vote in votes if not vote.in_effect))
    self.assertLen(votes, 2)

    old_vote = [vote for vote in votes if not vote.in_effect][0]
    new_vote = [vote for vote in votes if vote.in_effect][0]
    new_score = self.santa_blockable1.key.get().score

    self.assertNotEqual(vote_models._IN_EFFECT_KEY_NAME, old_vote.key.id())
    self.assertEqual(vote_models._IN_EFFECT_KEY_NAME, new_vote.key.id())
    self.assertGreater(new_vote.recorded_dt, old_vote.recorded_dt)
    self.assertEqual(new_score, -1 * orig_score)
    self.assertIsNotNone(new_vote.key.id())

    self.assertBigQueryInsertions([TABLE.VOTE, TABLE.BINARY] * 2)

  def testArchiveAllVote(self):
    user = test_utils.CreateUser()

    ballot_box = api.SantaBallotBox(self.santa_blockable1.key.id())

    existing_count = vote_models.Vote.query().count()

    # The user upvotes the blockable.
    ballot_box.Vote(True, user)

    num_created = vote_models.Vote.query().count() - existing_count

    # New Vote = 1 created
    self.assertEqual(1, num_created)

    # The user changes their vote on the blockable.
    ballot_box.Vote(False, user)

    num_created = vote_models.Vote.query().count() - existing_count

    # New Vote + Saved old Vote = 2 created
    self.assertEqual(2, num_created)

    self.assertBigQueryInsertions([TABLE.VOTE, TABLE.BINARY] * 2)

  def testLookupMetric_WhenBinary(self):
    self.PatchSetting('ENABLE_BINARY_ANALYSIS_PRECACHING', True)

    user = test_utils.CreateUser()

    ballot_box = api.SantaBallotBox(self.santa_blockable1.key.id())
    ballot_box.Vote(False, user)

    self.assertTaskCount(constants.TASK_QUEUE.METRICS, 1)

    self.assertBigQueryInsertions([TABLE.VOTE, TABLE.BINARY])

  def testLookupMetric_SkipWhenBundle(self):
    self.PatchSetting('ENABLE_BINARY_ANALYSIS_PRECACHING', True)

    user = test_utils.CreateUser()

    ballot_box = api.SantaBallotBox(self.santa_bundle.key.id())
    ballot_box.Vote(True, user)

    self.assertTaskCount(constants.TASK_QUEUE.METRICS, 0)

    self.assertBigQueryInsertions([TABLE.VOTE, TABLE.BUNDLE])

  def testFlaggedWithNegativeVote(self):
    """A blockable that is not marked as flagged, but should be."""
    santa_blockable = test_utils.CreateSantaBlockable()
    santa_blockable.flagged = True
    santa_blockable.put()

    with self.LoggedInUser() as user:
      original_blockable_dict = santa_blockable.to_dict()
      test_utils.CreateVote(
          santa_blockable, user_email=user.email, was_yes_vote=False)

      change_made = api._CheckBlockableFlagStatus(santa_blockable)

      self.assertFalse(change_made)
      # Don't compare score because it should be lower due to new vote.
      santa_blockable_dict = santa_blockable.to_dict()
      del original_blockable_dict['score']
      del santa_blockable_dict['score']
      self.assertEqual(original_blockable_dict, santa_blockable_dict)
      self.assertEqual(-1, santa_blockable.score)

  def testUnflaggedWithNegativeVote(self):
    """A blockable that is not marked as flagged, but should be."""
    santa_blockable = test_utils.CreateSantaBlockable()
    santa_blockable.flagged = False
    santa_blockable.put()
    user = test_utils.CreateUser()
    test_utils.CreateVote(
        santa_blockable, user_email=user.email, was_yes_vote=False)

    change_made = api._CheckBlockableFlagStatus(santa_blockable)

    self.assertTrue(change_made)
    self.assertTrue(santa_blockable.flagged)

  def testFlaggedWithYesVote(self):
    """A blockable that is flagged, but shouldn't be."""
    santa_blockable = test_utils.CreateSantaBlockable()
    santa_blockable.flagged = True
    santa_blockable.put()
    user = test_utils.CreateUser()
    test_utils.CreateVote(
        santa_blockable, user_email=user.email, was_yes_vote=True)

    change_made = api._CheckBlockableFlagStatus(santa_blockable)

    self.assertFalse(santa_blockable.flagged)
    self.assertTrue(change_made)

  def testFlaggedWithYesVote_ArchivedVotes(self):
    """A blockable that is flagged, but shouldn't be with archived votes."""

    # Create an active vote.
    santa_blockable = test_utils.CreateSantaBlockable(flagged=True)
    user = test_utils.CreateUser()
    test_utils.CreateVote(
        santa_blockable, user_email=user.email, was_yes_vote=True)

    # Create archived votes.
    archived_vote = test_utils.CreateVote(
        santa_blockable, user_email=user.email, was_yes_vote=False)
    archived_vote.key.delete()
    for _ in xrange(4):
      archived_vote.key = vote_models.Vote.GetKey(
          santa_blockable.key, user.key, in_effect=False)
      archived_vote.put()

    change_made = api._CheckBlockableFlagStatus(santa_blockable)

    self.assertFalse(santa_blockable.flagged)
    self.assertTrue(change_made)

  def testSuspectWithNegativeVote(self):
    """A blockable properly marked as suspect."""

    santa_blockable = test_utils.CreateSantaBlockable()
    santa_blockable.state = constants.STATE.SUSPECT
    santa_blockable.put()

    admin = test_utils.CreateUser(admin=True)
    test_utils.CreateVote(
        santa_blockable, user_email=admin.email, was_yes_vote=False)

    ballot_box = api.SantaBallotBox(santa_blockable.key.id())
    ballot_box.blockable = santa_blockable

    change_made = ballot_box._AuditBlockableState()

    self.assertEqual(vote_models.Vote.query().count(), 1)
    self.assertFalse(change_made)

  def testSuspectWithoutNoVote(self):
    """A blockable improperly marked as suspect."""

    santa_blockable = test_utils.CreateSantaBlockable()
    santa_blockable.state = constants.STATE.SUSPECT
    santa_blockable.put()

    admin1 = test_utils.CreateUser(admin=True)
    admin2 = test_utils.CreateUser(admin=True)

    test_utils.CreateVote(
        santa_blockable, user_email=admin1.email, was_yes_vote=False)
    test_utils.CreateVote(
        santa_blockable, user_email=admin2.email, was_yes_vote=True)

    ballot_box = api.SantaBallotBox(santa_blockable.key.id())
    ballot_box.blockable = santa_blockable

    with mock.patch.object(ballot_box, '_CheckAndSetBlockableState',
                           return_value=True, autospec=True):
      change_made = ballot_box._AuditBlockableState()

    self.assertEqual(vote_models.Vote.query().count(), 2)
    self.assertTrue(change_made)

  def testSuspectWithoutNoVoteFromAppropriateUser(self):
    """A blockable improperly marked as suspect."""
    santa_blockable = test_utils.CreateSantaBlockable()

    user = test_utils.CreateUser()
    test_utils.CreateVote(
        santa_blockable, user_email=user.email, was_yes_vote=False)

    santa_blockable.state = constants.STATE.SUSPECT
    santa_blockable.put()

    ballot_box = api.SantaBallotBox(santa_blockable.key.id())
    ballot_box.blockable = santa_blockable

    with mock.patch.object(ballot_box, '_CheckAndSetBlockableState',
                           return_value='True', autospec=True):
      change_made = ballot_box._AuditBlockableState()
      ballot_box._CheckAndSetBlockableState.assert_called_once_with(-1)

    self.assertEqual(vote_models.Vote.query().count(), 1)
    self.assertTrue(change_made)

  def testBlockableWithLocalWhitelistRulesUntrusted(self):
    """A blockable in untrusted with local whitelist rules."""
    santa_blockable = test_utils.CreateSantaBlockable()
    santa_blockable.state = constants.STATE.UNTRUSTED
    santa_blockable.put()

    test_rule1 = santa.SantaRule(
        parent=santa_blockable.key,
        rule_type=constants.RULE_TYPE.BINARY,
        policy=constants.RULE_POLICY.WHITELIST,
        in_effect=True,
        host_id='aaaaa-1111-bbbbbbbbbb')
    test_rule2 = santa.SantaRule(
        parent=santa_blockable.key,
        rule_type=constants.RULE_TYPE.BINARY,
        policy=constants.RULE_POLICY.WHITELIST,
        in_effect=True,
        host_id='bbbbb-2222-ccccccccc')
    test_rule3 = santa.SantaRule(
        parent=santa_blockable.key,
        rule_type=constants.RULE_TYPE.BINARY,
        policy=constants.RULE_POLICY.WHITELIST,
        in_effect=True,
        host_id='ccccc-1111-dddddddd')
    test_rule1.put()
    test_rule2.put()
    test_rule3.put()

    ballot_box = api.SantaBallotBox(santa_blockable.key.id())
    ballot_box.blockable = santa_blockable

    ballot_box._CheckRules()

    rule_query = santa.SantaRule.query()

    self.assertEqual(rule_query.count(), 3)

    all_in_effect = True
    for rule in rule_query:
      all_in_effect = all_in_effect and rule.in_effect

    self.assertTrue(all_in_effect)

  def testBlockableWithProperLocalWhitelistRules(self):
    """A blockable with correct state and local whitelist rules."""
    santa_blockable = test_utils.CreateSantaBlockable()
    santa_blockable.state = constants.STATE.APPROVED_FOR_LOCAL_WHITELISTING
    santa_blockable.put()

    test_rule1 = santa.SantaRule(
        parent=santa_blockable.key,
        rule_type=constants.RULE_TYPE.BINARY,
        policy=constants.RULE_POLICY.WHITELIST,
        in_effect=True,
        host_id='aaaaa-1111-bbbbbbbbbb')
    test_rule2 = santa.SantaRule(
        parent=santa_blockable.key,
        rule_type=constants.RULE_TYPE.BINARY,
        policy=constants.RULE_POLICY.WHITELIST,
        in_effect=True,
        host_id='bbbbb-2222-ccccccccc')
    test_rule3 = santa.SantaRule(
        parent=santa_blockable.key,
        rule_type=constants.RULE_TYPE.BINARY,
        policy=constants.RULE_POLICY.WHITELIST,
        in_effect=True,
        host_id='ccccc-1111-dddddddd')
    test_rule1.put()
    test_rule2.put()
    test_rule3.put()

    ballot_box = api.SantaBallotBox(santa_blockable.key.id())
    ballot_box.blockable = santa_blockable

    ballot_box._CheckRules()

    rule_query = santa.SantaRule.query()

    self.assertEqual(rule_query.count(), 3)

    all_in_effect = True
    for rule in rule_query:
      all_in_effect = all_in_effect and rule.in_effect

    self.assertTrue(all_in_effect)

  def testBlockableWithProperGlobalWhitelistRules(self):
    """A blockable with correct state and global whitelist rule."""
    santa_blockable = test_utils.CreateSantaBlockable()
    santa_blockable.state = constants.STATE.GLOBALLY_WHITELISTED
    santa_blockable.put()

    test_rule = santa.SantaRule(
        parent=santa_blockable.key,
        rule_type=constants.RULE_TYPE.BINARY,
        policy=constants.RULE_POLICY.WHITELIST,
        in_effect=True)
    test_rule.put()

    ballot_box = api.SantaBallotBox(santa_blockable.key.id())
    ballot_box.blockable = santa_blockable

    ballot_box._CheckRules()

    rule_query = santa.SantaRule.query()

    self.assertEqual(rule_query.count(), 1)

    rule = rule_query.get()

    self.assertEqual(rule, test_rule)

  def testBlockableWithProperBlacklistRules(self):
    """A blockable with correct state and blacklist rule."""
    santa_blockable = test_utils.CreateSantaBlockable()
    santa_blockable.state = constants.STATE.BANNED
    santa_blockable.put()

    test_rule = santa.SantaRule(
        parent=santa_blockable.key,
        rule_type=constants.RULE_TYPE.BINARY,
        policy=constants.RULE_POLICY.BLACKLIST,
        in_effect=True)
    test_rule.put()

    ballot_box = api.SantaBallotBox(santa_blockable.key.id())
    ballot_box.blockable = santa_blockable

    ballot_box._CheckRules()

    rule_query = santa.SantaRule.query()

    self.assertEqual(rule_query.count(), 1)

    rule = rule_query.get()

    self.assertEqual(rule, test_rule)

  def testUntrustedBlockableWithImproperGlobalWhitelistRules(self):
    """A blockable with local whitelist rules that should not have them."""
    santa_blockable = test_utils.CreateSantaBlockable()
    santa_blockable.state = constants.STATE.UNTRUSTED
    santa_blockable.put()

    test_rule = santa.SantaRule(
        parent=santa_blockable.key,
        rule_type=constants.RULE_TYPE.BINARY,
        policy=constants.RULE_POLICY.WHITELIST,
        in_effect=True)
    test_rule.put()

    ballot_box = api.SantaBallotBox(santa_blockable.key.id())
    ballot_box.blockable = santa_blockable

    ballot_box._CheckRules()

    rule_query = santa.SantaRule.query()

    self.assertEqual(rule_query.count(), 1)

    rule = rule_query.get()

    self.assertFalse(rule.in_effect)

  def testBlockableWithImproperLocalWhitelistRules(self):
    """A blockable with local whitelist rules that should not have them."""
    santa_blockable = test_utils.CreateSantaBlockable()
    santa_blockable.state = constants.STATE.BANNED
    santa_blockable.put()

    test_rule1 = santa.SantaRule(
        parent=santa_blockable.key,
        rule_type=constants.RULE_TYPE.BINARY,
        policy=constants.RULE_POLICY.WHITELIST,
        in_effect=True,
        host_id='aaaaa-1111-bbbbbbbbbb')
    test_rule2 = santa.SantaRule(
        parent=santa_blockable.key,
        rule_type=constants.RULE_TYPE.BINARY,
        policy=constants.RULE_POLICY.WHITELIST,
        in_effect=True,
        host_id='bbbbb-2222-ccccccccc')
    test_rule3 = santa.SantaRule(
        parent=santa_blockable.key,
        rule_type=constants.RULE_TYPE.BINARY,
        policy=constants.RULE_POLICY.WHITELIST,
        in_effect=True,
        host_id='ccccc-1111-dddddddd')
    test_rule1.put()
    test_rule2.put()
    test_rule3.put()

    ballot_box = api.SantaBallotBox(santa_blockable.key.id())
    ballot_box.blockable = santa_blockable

    ballot_box._CheckRules()

    rule_query = santa.SantaRule.query()
    self.assertEqual(4, rule_query.count())
    # Exacly one rule (the blacklist one) should be in effect.
    self.assertEqual(1, sum(rule.in_effect for rule in rule_query))

    self.assertBigQueryInsertions([TABLE.RULE])

  def testBlockableWithImproperGlobalWhitelistRule(self):
    """A blockable with a global whitelist rule it shouldn't have."""
    santa_blockable = test_utils.CreateSantaBlockable()
    santa_blockable.state = constants.STATE.UNTRUSTED
    santa_blockable.put()

    test_rule = santa.SantaRule(
        parent=santa_blockable.key,
        rule_type=constants.RULE_TYPE.BINARY,
        policy=constants.RULE_POLICY.WHITELIST,
        in_effect=True)
    test_rule.put()

    ballot_box = api.SantaBallotBox(santa_blockable.key.id())
    ballot_box.blockable = santa_blockable

    ballot_box._CheckRules()

    rule_query = santa.SantaRule.query()

    self.assertEqual(rule_query.count(), 1)

    rule = rule_query.get()

    self.assertFalse(rule.in_effect)

  def testBlockableWithImproperBlacklistRule(self):
    """A blockable with a blacklist rule it doesn't deserve."""
    santa_blockable = test_utils.CreateSantaBlockable()
    santa_blockable.state = constants.STATE.UNTRUSTED
    santa_blockable.put()

    test_rule = santa.SantaRule(
        parent=santa_blockable.key,
        rule_type=constants.RULE_TYPE.BINARY,
        policy=constants.RULE_POLICY.BLACKLIST,
        in_effect=True)
    test_rule.put()

    ballot_box = api.SantaBallotBox(santa_blockable.key.id())
    ballot_box.blockable = santa_blockable

    ballot_box._CheckRules()

    rule_query = santa.SantaRule.query()

    self.assertEqual(rule_query.count(), 1)

    rule = rule_query.get()

    self.assertFalse(rule.in_effect)


class RecountTest(basetest.UpvoteTestCase):

  def testSuccess(self):
    """Check that if score is out of sync it actually gets recalculated."""
    santa_blockable = test_utils.CreateSantaBlockable()
    santa_blockable.put()
    user = test_utils.CreateUser()
    test_utils.CreateVote(
        santa_blockable, user_email=user.email, was_yes_vote=True)
    api.Recount(santa_blockable.key.id())
    santa_blockable = santa_blockable.key.get()
    self.assertEqual(santa_blockable.score, 1)


class ResetTest(basetest.UpvoteTestCase):

  def setUp(self):
    super(ResetTest, self).setUp()

    santa_blockable_1 = test_utils.CreateSantaBlockable()
    santa_blockable_2 = test_utils.CreateSantaBlockable()
    santa_bundle_blockables = (santa_blockable_1, santa_blockable_2)
    self.santa_bundle = test_utils.CreateSantaBundle(
        bundle_binaries=santa_bundle_blockables)

    self.local_threshold = settings.VOTING_THRESHOLDS[
        constants.STATE.APPROVED_FOR_LOCAL_WHITELISTING]

  def testSuccess(self):
    blockable = test_utils.CreateSantaBlockable(state=constants.STATE.SUSPECT)
    test_utils.CreateSantaRule(blockable.key)
    test_utils.CreateVotes(blockable, 11)

    api.Reset(blockable.key.id())

    self.assertEqual(constants.STATE.UNTRUSTED, blockable.key.get().state)

    total_votes = vote_models.Vote.query()
    retrieved_rules = base.Rule.query(ancestor=blockable.key)
    # pylint: disable=g-explicit-bool-comparison, singleton-comparison
    retrieved_in_effect_rules = base.Rule.query(
        base.Rule.in_effect == True, ancestor=blockable.key)
    # pylint: enable=g-explicit-bool-comparison, singleton-comparison

    self.assertEqual(total_votes.count(), 11)
    self.assertLen(blockable.GetVotes(), 0)
    self.assertEqual(retrieved_rules.count(), 2)
    self.assertEqual(retrieved_in_effect_rules.count(), 1)

    self.assertBigQueryInsertions([TABLE.BINARY, TABLE.RULE])

  def testBundles_NotAllowed(self):
    with self.assertRaises(api.OperationNotAllowedError):
      api.Reset(self.santa_bundle.key.id())

  def testBit9(self):
    binary = test_utils.CreateBit9Binary()
    user = test_utils.CreateUser()
    test_utils.CreateBit9Host(users=[user.nickname])

    with self.LoggedInUser(user=user):
      api.Vote(user, binary.key.id(), True, self.local_threshold)

    self.assertEqual(self.local_threshold, binary.score)
    self.assertEntityCount(bit9.Bit9Rule, 1)
    self.assertEntityCount(bit9.RuleChangeSet, 1)

    api.Reset(binary.key.id())

    self.assertEqual(0, binary.score)

    self.assertEntityCount(bit9.Bit9Rule, 2)
    self.assertEntityCount(bit9.RuleChangeSet, 2)

    rules = binary.GetRules()
    self.assertLen(rules, 1)
    self.assertFalse(rules[0].is_committed)
    self.assertTrue(rules[0].in_effect)
    self.assertEqual(constants.RULE_POLICY.REMOVE, rules[0].policy)

    changes = bit9.RuleChangeSet.query().fetch()
    types = [change.change_type for change in changes]
    self.assertSameElements(
        [constants.RULE_POLICY.WHITELIST, constants.RULE_POLICY.REMOVE], types)

    self.assertTaskCount(constants.TASK_QUEUE.BIT9_COMMIT_CHANGE, 2)

    self.assertBigQueryInsertions(
        [TABLE.VOTE] + [TABLE.BINARY] * 3 + [TABLE.RULE] * 2)


if __name__ == '__main__':
  basetest.main()
