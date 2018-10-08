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

"""A common monitoring interface."""

import functools
import logging

from upvote.gae.datastore.models import datadog as datadog_model

import datadog

# datadog metric name rules: https://help.datadoghq.com/hc/en-us/articles/203764705-What-are-valid-metric-names-

_dd_stats = None


def _dd_get_stats():
  global _dd_stats

  if not _dd_stats:
    dd_api_key = datadog_model.DataDogApiAuth.GetInstance()
    if not dd_api_key:
      return None

    datadog.initialize(dd_api_key)

    _dd_stats = datadog.ThreadStats()
    _dd_stats.start()

  return _dd_stats


def _dd_get_format(metric, fields):
  stat_format = metric.metric_name
  if not fields:
    return stat_format

  for (field_name, field_type) in fields:
    stat_format += u"." + field_name + u"%s"
  return stat_format


def ContainExceptions(func):

  @functools.wraps(func)
  def Wrapper(self, *args, **kwargs):
    try:
      func(self, *args, **kwargs)
    except Exception:  # pylint: disable=broad-except
      logging.exception('Monitoring error encountered')

  return Wrapper


class Metric(object):
  """Base Upvote metric."""

  def __init__(self, metric, value_type, fields=None):
    self.display_name = metric.display_name
    self.metric_name = metric.metric_name
    self.type_ = value_type
    self.fields = fields
    self._stat_format = _dd_get_format(metric, fields)

  @ContainExceptions
  def Set(self, value, *args):
    stats = _dd_get_stats()
    if stats:
      stats.gauge(self._stat_format % args, value)


class LatencyMetric(object):
  """Upvote metric for tracking latency."""

  def __init__(self, metric, fields=None):
    self.display_name = metric.display_name
    self.metric_name = metric.metric_name
    self.fields = fields
    self._stat_format = _dd_get_format(metric, fields)

  @ContainExceptions
  def Record(self, value, *args):
    stats = _dd_get_stats()
    if stats:
      stats.gauge(self._stat_format % args, value)


class Counter(object):
  """Base Upvote counter."""

  def __init__(self, metric, fields=None):
    self.display_name = metric.display_name
    self.metric_name = metric.metric_name
    self.fields = fields
    self._stat_format = _dd_get_format(metric, fields)

  @ContainExceptions
  def Increment(self, *args):
    stats = _dd_get_stats()
    if stats:
      stats.increment(self._stat_format % args)

  @ContainExceptions
  def IncrementBy(self, inc, *args):
    _dd_get_stats().increment(self._stat_format % args, inc)


class RequestCounter(Counter):
  """Counts HTTP requests and their corresponding status codes."""

  def __init__(self, metric):
    fields = [(u'http_status', int)]
    super(RequestCounter, self).__init__(metric, fields=fields)


class SuccessFailureCounter(Counter):
  """Counts the success/failure rate of a given piece of code."""

  def __init__(self, metric):
    fields = [(u'outcome', str)]
    super(SuccessFailureCounter, self).__init__(metric, fields=fields)

  def Success(self):
    self.Increment('Success')

  def Failure(self):
    self.Increment('Failure')
