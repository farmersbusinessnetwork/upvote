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
import datetime

# from google.appengine.api import modules
# from google.cloud import monitoring

from upvote.gae.shared.common import settings

from upvote.gae.datastore.models import datadog as datadog_model

import datadog


# _CUMULATIVE = monitoring.metric.MetricKind.CUMULATIVE
# _CUMULATIVE = monitoring_v3.enums.MetricDescriptor.MetricKind.CUMULATIVE

# _GAUGE = monitoring.metric.MetricKind.GAUGE
# _GAUGE = monitoring_v3.enums.MetricDescriptor.MetricKind.GAUGE

_dd_stats = None


def _dd_get_stats():
  global _dd_stats

  if not _dd_stats:
    dd_api_instance = datadog_model.DataDogApiAuth.GetInstance()
    if not dd_api_instance:
      return None

    datadog.initialize(dd_api_instance.api_key)

    # we can't have background threads
    _dd_stats = datadog.ThreadStats()
    _dd_stats.start(flush_in_thread=False)

    # this requires an agent
    # _dd_stats = datadog.statsd

  return _dd_stats


# datadog metric name rules: https://help.datadoghq.com/hc/en-us/articles/203764705-What-are-valid-metric-names-
def _dd_get_format(metric, fields):
  stat_format = metric.metric_name
  if not fields:
    return str(stat_format)

  for (field_name, field_type) in fields:
    stat_format += u"." + field_name + u".%s"
  return str(stat_format)


# TODO: unfortunately google cloud monitoring requires you to write timeseries data 1 minute apart from another
#       https://cloud.google.com/monitoring/custom-metrics/creating-metrics#writing-ts
#       not sure how this can work, perhaps with a task

# _gmon_client = None
#
#
# def _get_gmon_client():
#   global _gmon_client
#
#   if not _gmon_client:
#     _gmon_client = monitoring.Client(project=settings.ProdEnv.PROJECT_ID)
#
#     # v3
#     # _gmon_client = monitoring.MetricServiceClient()
#
#   return _gmon_client
#
#
# def _write_metric_data(metric, metric_kind, value_type, value, fields, *args):
#   try:
#     client = _get_gmon_client()
#
#     # NOTE: for some reason you get a 400 if you try to use gae_app
#     resource = client.resource(
#       'gce_instance',
#       labels={
#         # 'project_id': settings.ProdEnv.PROJECT_ID,
#         # 'module_id': modules.get_current_module_name(),
#         # 'version_id': modules.get_current_version_name(),
#         'instance_id': modules.get_current_instance_id(),
#         'zone': 'us-west2'  # TODO: how do you get this dynamically?
#       }
#     )
#
#     metric = client.metric(
#       type_='custom.googleapis.com/' + metric.metric_name,
#       labels={field: args[i] for i, (field, field_type) in enumerate(fields or [])}
#     )
#
#     end_time = datetime.datetime.utcnow()
#
#     end_time = monitoring.client._datetime_to_rfc3339(end_time, ignore_zone=False)
#
#     point = monitoring.Point(value=value, start_time=None, end_time=end_time)
#
#     if value_type in {bool}:
#       value_type = monitoring.ValueType.BOOL
#     elif value_type in {int, long}:
#       value_type = monitoring.ValueType.INT64
#     elif value_type in {float}:
#       value_type = monitoring.ValueType.DOUBLE
#     else:
#       assert False, "Unknown type: " + value_type
#
#     timeseries = monitoring.TimeSeries(
#       metric=metric, resource=resource, metric_kind=metric_kind, value_type=value_type, points=[point])
#
#     client.write_time_series([timeseries])
#
#     # series = monitoring_v3.types.TimeSeries()
#     # series.metric_kind = metric_kind
#     # series.metric.type = 'custom.googleapis.com/' + metric.metric_name
#     # series.resource.type = 'gce_instance'
#     #
#     # for idx, (field, field_type) in enumerate(fields or []):
#     #   series.resource.labels[field] = args[idx]
#     #
#     # point = series.points.add()
#     #
#     # if value_type in {bool}:
#     #   point.value.boolean_value = value
#     # elif value_type in {int, long}:
#     #   point.value.integer_value = value
#     # elif value_type in {float}:
#     #   point.value.double_value = value
#     # else:
#     #   assert False, "Unknown type: " + value_type
#     #
#     # # now = time.time()
#     # # point.interval.end_time.seconds = int(now)
#     # # point.interval.end_time.nanos = int(
#     # #   (now - point.interval.end_time.seconds) * 10 ** 9)
#     #
#     # client.create_time_series(project_name, [series])
#   except:
#     logging.exception('Monitoring error encountered')


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
    self.fields = fields
    self.value_type = value_type
    self.metric = metric
    self.fields = fields
    self._stat_format = _dd_get_format(metric, fields)

  @ContainExceptions
  def Set(self, value, *args):
    # _write_metric_data(self.metric, _GAUGE, self.value_type, value, self.fields, *args)

    stats = _dd_get_stats()
    if stats:
      stats.gauge(self._stat_format % args, value)
      stats.flush()


class LatencyMetric(object):
  """Upvote metric for tracking latency."""

  def __init__(self, metric, fields=None):
    self.fields = fields
    self.metric = metric
    self._stat_format = _dd_get_format(metric, fields)

  @ContainExceptions
  def Record(self, value, *args):
    # _write_metric_data(self.metric, _GAUGE, float, value, self.fields, *args)

    stats = _dd_get_stats()
    if stats:
      stats.gauge(self._stat_format % args, value)
      stats.flush()


class Counter(object):
  """Base Upvote counter."""

  def __init__(self, metric, fields=None):
    self.metric = metric
    self.fields = fields
    self._stat_format = _dd_get_format(metric, fields)

  @ContainExceptions
  def Increment(self, *args):
    # _write_metric_data(self.metric, _CUMULATIVE, float, 1, self.fields, *args)
    stats = _dd_get_stats()
    if stats:
      stats.increment(self._stat_format % args)
      stats.flush()

  @ContainExceptions
  def IncrementBy(self, inc, *args):
    # _write_metric_data(self.metric, _CUMULATIVE, float, inc, self.fields, *args)
    stats = _dd_get_stats()
    if stats:
      stats.increment(self._stat_format % args, inc)
      stats.flush()


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
