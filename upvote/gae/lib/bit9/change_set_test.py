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

"""Tests for RuleChangeSet commitment."""

import datetime
import os

import mock

from google.appengine.ext import deferred

from common import context

from absl.testing import absltest

from upvote.gae.datastore import test_utils
from upvote.gae.datastore.models import bit9
from upvote.gae.lib.bit9 import api
from upvote.gae.lib.bit9 import change_set
from upvote.gae.lib.bit9 import constants as bit9_constants
from upvote.gae.lib.testing import basetest
from upvote.shared import constants


class ChangeLocalStatesTest(basetest.UpvoteTestCase):

  @mock.patch.object(change_set.monitoring, 'local_whitelisting_latency')
  @mock.patch.object(change_set, '_ChangeLocalState', return_value=True)
  def testLatencyRecorded_Whitelist_Fulfilled(
      self, mock_change_local_state, mock_metric):

    binary = test_utils.CreateBit9Binary(file_catalog_id='1234')
    local_rule = test_utils.CreateBit9Rule(
        binary.key, host_id='12345', policy=constants.RULE_POLICY.WHITELIST)

    change_set._ChangeLocalStates(
        binary, [local_rule], bit9_constants.APPROVAL_STATE.APPROVED)

    self.assertTrue(mock_metric.Record.called)

  @mock.patch.object(change_set.monitoring, 'local_whitelisting_latency')
  @mock.patch.object(change_set, '_ChangeLocalState', return_value=False)
  def testLatencyRecorded_Whitelist_NotFulfilled(
      self, mock_change_local_state, mock_metric):

    binary = test_utils.CreateBit9Binary(file_catalog_id='1234')
    local_rule = test_utils.CreateBit9Rule(
        binary.key, host_id='12345', policy=constants.RULE_POLICY.WHITELIST)

    change_set._ChangeLocalStates(
        binary, [local_rule], bit9_constants.APPROVAL_STATE.APPROVED)

    self.assertFalse(mock_metric.Record.called)

  @mock.patch.object(change_set.monitoring, 'local_whitelisting_latency')
  @mock.patch.object(change_set, '_ChangeLocalState', return_value=True)
  def testLatencyRecorded_NonWhitelist(
      self, mock_change_local_state, mock_metric):

    binary = test_utils.CreateBit9Binary(file_catalog_id='1234')
    local_rule = test_utils.CreateBit9Rule(
        binary.key, host_id='12345',
        policy=constants.RULE_POLICY.FORCE_INSTALLER)

    change_set._ChangeLocalStates(
        binary, [local_rule], bit9_constants.APPROVAL_STATE.APPROVED)

    self.assertFalse(mock_metric.Record.called)


class CommitBlockableChangeSetTest(basetest.UpvoteTestCase):

  def setUp(self):
    super(CommitBlockableChangeSetTest, self).setUp()

    # Set up a fake Bit9ApiAuth entity in Datastore.
    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = os.path.join(
        absltest.get_default_test_srcdir(),
        'upvote/gae/modules/bit9_api',
        'fake_credentials.json')
    self.Patch(
        change_set.bit9_utils.bit9.kms_ndb.EncryptedBlobProperty, '_Encrypt',
        return_value='blah')
    self.Patch(
        change_set.bit9_utils.bit9.kms_ndb.EncryptedBlobProperty, '_Decrypt',
        return_value='blah')
    bit9.Bit9ApiAuth.SetInstance(api_key='blah')

    self.mock_ctx = mock.Mock(
        spec=change_set.bit9_utils.api.Context)
    self.Patch(
        change_set.bit9_utils.api, 'Context',
        return_value=self.mock_ctx)

    self.binary = test_utils.CreateBit9Binary(file_catalog_id='1234')
    self.local_rule = test_utils.CreateBit9Rule(self.binary.key, host_id='5678')
    self.global_rule = test_utils.CreateBit9Rule(self.binary.key)

  def tearDown(self):
    # We have to reset the LazyProxy in utils, otherwise utils.CONTEXT will
    # cache the mock context and break subsequent tests.
    context.ResetLazyProxies()

  def _PatchApiRequests(self, *results):
    requests = []
    for batch in results:
      if isinstance(batch, list):
        requests.append([obj.to_raw_dict() for obj in batch])
      else:
        requests.append(batch.to_raw_dict())
    self.mock_ctx.ExecuteRequest.side_effect = requests

  def testWhitelist_LocalRule_Fulfilled(self):
    change = test_utils.CreateRuleChangeSet(
        self.binary.key,
        rule_keys=[self.local_rule.key],
        change_type=constants.RULE_POLICY.WHITELIST)

    fi = api.FileInstance(
        id=9012,
        file_catalog_id=int(self.binary.file_catalog_id),
        computer_id=int(self.local_rule.host_id),
        local_state=bit9_constants.APPROVAL_STATE.UNAPPROVED)
    self._PatchApiRequests([fi], fi)

    change_set._CommitBlockableChangeSet(self.binary.key)

    self.mock_ctx.ExecuteRequest.assert_has_calls([
        mock.call(
            'GET', api_route='fileInstance',
            query_args=[r'q=computerId:5678', 'q=fileCatalogId:1234']),
        mock.call(
            'POST', api_route='fileInstance',
            data={'id': 9012,
                  'localState': 2,
                  'fileCatalogId': 1234,
                  'computerId': 5678},
            query_args=None)])

    self.assertTrue(self.local_rule.key.get().is_fulfilled)
    self.assertTrue(self.local_rule.key.get().is_committed)
    self.assertIsNone(change.key.get())

  def testWhitelist_LocalRule_NotFulfilled(self):
    change = test_utils.CreateRuleChangeSet(
        self.binary.key,
        rule_keys=[self.local_rule.key],
        change_type=constants.RULE_POLICY.WHITELIST)
    computer = api.Computer(id=5678, sync_percent=100)
    computer.last_poll_date = datetime.datetime.utcnow()
    self._PatchApiRequests([], computer)

    change_set._CommitBlockableChangeSet(self.binary.key)

    self.mock_ctx.ExecuteRequest.assert_has_calls([
        mock.call(
            'GET', api_route='fileInstance',
            query_args=[r'q=computerId:5678', 'q=fileCatalogId:1234'])])

    self.assertIsNotNone(self.local_rule.key.get().is_fulfilled)
    self.assertFalse(self.local_rule.key.get().is_fulfilled)
    self.assertTrue(self.local_rule.key.get().is_committed)
    self.assertIsNone(change.key.get())

  def testWhitelist_LocalRule_Certificate(self):
    cert = test_utils.CreateBit9Certificate()
    local_rule = test_utils.CreateBit9Rule(cert.key, host_id='5678')
    change = test_utils.CreateRuleChangeSet(
        cert.key,
        rule_keys=[local_rule.key],
        change_type=constants.RULE_POLICY.WHITELIST)

    change_set._CommitBlockableChangeSet(cert.key)

    self.assertIsNotNone(self.local_rule.key.get().is_fulfilled)
    self.assertFalse(local_rule.key.get().is_fulfilled)
    self.assertTrue(local_rule.key.get().is_committed)
    self.assertIsNone(change.key.get())

  def testWhitelist_GlobalRule(self):
    change = test_utils.CreateRuleChangeSet(
        self.binary.key,
        rule_keys=[self.global_rule.key],
        change_type=constants.RULE_POLICY.WHITELIST)
    self._PatchApiRequests(api.Computer(id=5678))

    change_set._CommitBlockableChangeSet(self.binary.key)

    self.mock_ctx.ExecuteRequest.assert_has_calls([
        mock.call(
            'POST', api_route='fileRule',
            data={'fileCatalogId': 1234, 'fileState': 2}, query_args=None)])

    self.assertTrue(self.global_rule.key.get().is_committed)
    self.assertIsNone(change.key.get())

  def testWhitelist_GlobalRule_Certificate(self):
    cert = test_utils.CreateBit9Certificate(id='1a2b')
    global_rule = test_utils.CreateBit9Rule(cert.key, host_id='')
    change = test_utils.CreateRuleChangeSet(
        cert.key,
        rule_keys=[global_rule.key],
        change_type=constants.RULE_POLICY.WHITELIST)
    api_cert = api.Certificate(id=9012, thumbprint='1a2b', certificate_state=1)
    self._PatchApiRequests([api_cert], api_cert)

    change_set._CommitBlockableChangeSet(cert.key)

    self.mock_ctx.ExecuteRequest.assert_has_calls([
        mock.call(
            'GET', api_route='certificate',
            query_args=['q=thumbprint:1a2b']),
        mock.call(
            'POST', api_route='certificate',
            data={'id': 9012, 'thumbprint': '1a2b', 'certificateState': 2},
            query_args=None)])

    self.assertTrue(global_rule.key.get().is_committed)
    self.assertIsNone(change.key.get())

  def testWhitelist_MixedRules(self):
    other_local_rule = test_utils.CreateBit9Rule(
        self.binary.key, host_id='9012')
    change = test_utils.CreateRuleChangeSet(
        self.binary.key,
        rule_keys=[
            self.local_rule.key, other_local_rule.key, self.global_rule.key],
        change_type=constants.RULE_POLICY.WHITELIST)
    fi1 = api.FileInstance(
        id=9012,
        file_catalog_id=int(self.binary.file_catalog_id),
        computer_id=int(self.local_rule.host_id),
        local_state=bit9_constants.APPROVAL_STATE.UNAPPROVED)
    fi2 = api.FileInstance(
        id=9012,
        file_catalog_id=int(self.binary.file_catalog_id),
        computer_id=9012,
        local_state=bit9_constants.APPROVAL_STATE.UNAPPROVED)
    rule = api.FileRule(
        file_catalog_id=1234, file_state=bit9_constants.APPROVAL_STATE.APPROVED)
    self._PatchApiRequests([fi1], fi1, [fi2], fi2, rule)

    change_set._CommitBlockableChangeSet(self.binary.key)

    self.mock_ctx.ExecuteRequest.assert_has_calls([
        mock.call(
            'GET', api_route='fileInstance',
            query_args=[r'q=computerId:5678', 'q=fileCatalogId:1234']),
        mock.call(
            'POST', api_route='fileInstance',
            data={'id': 9012,
                  'localState': 2,
                  'fileCatalogId': 1234,
                  'computerId': 5678},
            query_args=None),
        mock.call(
            'GET', api_route='fileInstance',
            query_args=[r'q=computerId:9012', 'q=fileCatalogId:1234']),
        mock.call(
            'POST', api_route='fileInstance',
            data={'id': 9012,
                  'localState': 2,
                  'fileCatalogId': 1234,
                  'computerId': 9012},
            query_args=None),
        mock.call(
            'POST', api_route='fileRule',
            data={'fileCatalogId': 1234, 'fileState': 2}, query_args=None),
    ])

    self.assertTrue(self.local_rule.key.get().is_fulfilled)
    self.assertTrue(self.local_rule.key.get().is_committed)
    self.assertTrue(other_local_rule.key.get().is_fulfilled)
    self.assertTrue(other_local_rule.key.get().is_committed)
    self.assertTrue(self.global_rule.key.get().is_committed)
    self.assertIsNone(change.key.get())

  def testBlacklist_GlobalRule(self):
    change = test_utils.CreateRuleChangeSet(
        self.binary.key,
        rule_keys=[self.global_rule.key],
        change_type=constants.RULE_POLICY.BLACKLIST)
    rule = api.FileRule(
        file_catalog_id=1234,
        file_state=bit9_constants.APPROVAL_STATE.UNAPPROVED)
    self._PatchApiRequests(rule)

    change_set._CommitBlockableChangeSet(self.binary.key)

    self.mock_ctx.ExecuteRequest.assert_has_calls([
        mock.call(
            'POST', api_route='fileRule',
            data={'fileCatalogId': 1234, 'fileState': 3}, query_args=None)])

    self.assertTrue(self.global_rule.key.get().is_committed)
    self.assertIsNone(change.key.get())

  def testBlacklist_GlobalRule_Multiple(self):
    other_global_rule = test_utils.CreateBit9Rule(self.binary.key)
    test_utils.CreateRuleChangeSet(
        self.binary.key,
        rule_keys=[self.global_rule.key, other_global_rule.key],
        change_type=constants.RULE_POLICY.BLACKLIST)

    with self.assertRaises(deferred.PermanentTaskFailure):
      change_set._CommitBlockableChangeSet(self.binary.key)

  def testBlacklist_MixedRules(self):
    test_utils.CreateRuleChangeSet(
        self.binary.key,
        rule_keys=[self.local_rule.key, self.global_rule.key],
        change_type=constants.RULE_POLICY.BLACKLIST)

    with self.assertRaises(deferred.PermanentTaskFailure):
      change_set._CommitBlockableChangeSet(self.binary.key)

  def testRemove_MixedRules(self):
    other_local_rule = test_utils.CreateBit9Rule(
        self.binary.key, host_id='9012')
    change = test_utils.CreateRuleChangeSet(
        self.binary.key,
        rule_keys=[
            self.local_rule.key, other_local_rule.key, self.global_rule.key],
        change_type=constants.RULE_POLICY.REMOVE)
    fi1 = api.FileInstance(
        id=9012,
        file_catalog_id=int(self.binary.file_catalog_id),
        computer_id=int(self.local_rule.host_id),
        local_state=bit9_constants.APPROVAL_STATE.APPROVED)
    fi2 = api.FileInstance(
        id=9012,
        file_catalog_id=int(self.binary.file_catalog_id),
        computer_id=int(other_local_rule.host_id),
        local_state=bit9_constants.APPROVAL_STATE.APPROVED)
    rule = api.FileRule(
        file_catalog_id=1234, file_state=bit9_constants.APPROVAL_STATE.APPROVED)
    self._PatchApiRequests([fi1], fi1, [fi2], fi2, rule)

    change_set._CommitBlockableChangeSet(self.binary.key)

    self.mock_ctx.ExecuteRequest.assert_has_calls([
        mock.call(
            'GET', api_route='fileInstance',
            query_args=[r'q=computerId:5678', 'q=fileCatalogId:1234']),
        mock.call(
            'POST', api_route='fileInstance',
            data={'id': 9012,
                  'localState': 1,
                  'fileCatalogId': 1234,
                  'computerId': 5678},
            query_args=None),
        mock.call(
            'GET', api_route='fileInstance',
            query_args=[r'q=computerId:9012', 'q=fileCatalogId:1234']),
        mock.call(
            'POST', api_route='fileInstance',
            data={'id': 9012,
                  'localState': 1,
                  'fileCatalogId': 1234,
                  'computerId': 9012},
            query_args=None),
        mock.call(
            'POST', api_route='fileRule',
            data={'fileCatalogId': 1234, 'fileState': 1}, query_args=None),
    ])

    self.assertTrue(self.local_rule.key.get().is_fulfilled)
    self.assertTrue(self.local_rule.key.get().is_committed)
    self.assertTrue(other_local_rule.key.get().is_fulfilled)
    self.assertTrue(other_local_rule.key.get().is_committed)
    self.assertTrue(self.global_rule.key.get().is_committed)
    self.assertIsNone(change.key.get())

  def testTailDefer(self):
    test_utils.CreateRuleChangeSet(
        self.binary.key,
        rule_keys=[self.local_rule.key],
        change_type=constants.RULE_POLICY.WHITELIST)
    test_utils.CreateRuleChangeSet(
        self.binary.key,
        rule_keys=[self.global_rule.key],
        change_type=constants.RULE_POLICY.WHITELIST)
    with mock.patch.object(change_set, '_Whitelist'):
      change_set._CommitBlockableChangeSet(self.binary.key)
      # Tail defer should have been added.
      self.assertTaskCount(constants.TASK_QUEUE.BIT9_COMMIT_CHANGE, 1)

      # Only the local rule should have been committed first.
      self.assertTrue(self.local_rule.key.get().is_committed)
      self.assertFalse(self.global_rule.key.get().is_committed)
      self.assertEntityCount(bit9.RuleChangeSet, 1)

      # Run the deferred commit attempt.
      self.RunDeferredTasks(constants.TASK_QUEUE.BIT9_COMMIT_CHANGE)
      # Tail defer should not have been added as there are no more changes.
      self.assertTaskCount(constants.TASK_QUEUE.BIT9_COMMIT_CHANGE, 0)

      # Both rules should now have been committed.
      self.assertTrue(self.local_rule.key.get().is_committed)
      self.assertTrue(self.global_rule.key.get().is_committed)
      self.assertEntityCount(bit9.RuleChangeSet, 0)

  def testNoChange(self):
    with mock.patch.object(change_set, '_CommitChangeSet') as mock_commit:
      change_set._CommitBlockableChangeSet(self.binary.key)

      self.assertFalse(mock_commit.called)


class DeferCommitBlockableChangeSetTest(basetest.UpvoteTestCase):

  def setUp(self):
    super(DeferCommitBlockableChangeSetTest, self).setUp()

    self.binary = test_utils.CreateBit9Binary(file_catalog_id='1234')
    self.local_rule = test_utils.CreateBit9Rule(self.binary.key, host_id='5678')
    self.change = test_utils.CreateRuleChangeSet(
        self.binary.key,
        rule_keys=[self.local_rule.key],
        change_type=constants.RULE_POLICY.WHITELIST)

  def testTailDefer_MoreChanges(self):
    test_utils.CreateRuleChangeSet(
        self.binary.key,
        rule_keys=[self.local_rule.key],
        change_type=constants.RULE_POLICY.BLACKLIST)
    with mock.patch.object(change_set, '_CommitChangeSet') as mock_commit:
      change_set.DeferCommitBlockableChangeSet(self.binary.key)

      self.assertTaskCount(constants.TASK_QUEUE.BIT9_COMMIT_CHANGE, 1)
      self.RunDeferredTasks(constants.TASK_QUEUE.BIT9_COMMIT_CHANGE)
      # Tail defer task for remaining change.
      self.assertTaskCount(constants.TASK_QUEUE.BIT9_COMMIT_CHANGE, 1)

      mock_commit.assert_called_once_with(self.change.key)

  def testTailDefer_NoMoreChanges(self):
    with mock.patch.object(change_set, '_CommitChangeSet') as mock_commit:
      change_set.DeferCommitBlockableChangeSet(self.binary.key)

      self.assertTaskCount(constants.TASK_QUEUE.BIT9_COMMIT_CHANGE, 1)
      self.RunDeferredTasks(constants.TASK_QUEUE.BIT9_COMMIT_CHANGE)
      self.assertTaskCount(constants.TASK_QUEUE.BIT9_COMMIT_CHANGE, 0)

      mock_commit.assert_called_once_with(self.change.key)

  def testNoTailDefer(self):
    with mock.patch.object(change_set, '_CommitChangeSet') as mock_commit:
      change_set.DeferCommitBlockableChangeSet(
          self.binary.key, tail_defer=False)

      self.assertTaskCount(constants.TASK_QUEUE.BIT9_COMMIT_CHANGE, 1)
      self.RunDeferredTasks(constants.TASK_QUEUE.BIT9_COMMIT_CHANGE)
      self.assertTaskCount(constants.TASK_QUEUE.BIT9_COMMIT_CHANGE, 0)

      mock_commit.assert_called_once_with(self.change.key)


if __name__ == '__main__':
  absltest.main()
