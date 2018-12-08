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

"""Stub for santa client auth."""
import hashlib
import hmac
import base64
import logging

from upvote.gae.datastore.models import fbn_santa_sync as fbn_santa_sync_model

_fbn_santa_sync_key = None
_fbn_auth_header = "FBN-Auth"

# We have to use a whitelist as there are many keys which get added between santactl and us
_fbn_lowered_signed_headers = {key.lower() for key in {
  'Content-Encoding',
  # 'Content-Type',  we can't use this because someone is appending: charset="utf-8 after we do the request
  'X-XSRF-TOKEN'
}}


def _get_fbn_santa_sync_key():
  global _fbn_santa_sync_key

  if not _fbn_santa_sync_key:
    fbn_santa_sync_instance = fbn_santa_sync_model.FBNSantaSyncAuth.GetInstance()
    if fbn_santa_sync_instance:
      _fbn_santa_sync_key = fbn_santa_sync_instance.api_key

  return _fbn_santa_sync_key


# TODO: should probably pass the whole request object to this method
def ValidateClient(all_headers, uuid, request):
  """
  Validate
  :param all_headers: headers
  :type all_headers: dict
  :param uuid:
  :param request:
  :return:
  """
  try:
    fbn_santa_sync_key = _get_fbn_santa_sync_key()
    if not fbn_santa_sync_key:
      logging.error("FBN Santa Sync Key is not available")
      return True  # TODO: make this false

    fbn_auth_signature = all_headers.get(_fbn_auth_header)

    if not fbn_auth_signature:
      logging.error("FBN Santa Sync header value was not provided")
      return True  # TODO: make this false

    # HMAC_SHA256 of data:
    # 1. Lower of: METHOD PATH[ ?QUERY][#FRAGMENT]\n
    # 2...n Sorted by name, lower of: HEADER_NAME=VALUE\n
    # 3. BODY

    # 1 (webapp2 apparently doesn't support fragments?)
    data = "{} {}\n".format(request.method, request.path_qs)

    # 2 Get and append sorted header keys/values
    for sorted_header in sorted(all_headers.keys(), key=lambda x: x.lower()):
      if sorted_header.lower() not in _fbn_lowered_signed_headers:
        continue

      data += "{}={}\n".format(sorted_header, all_headers[sorted_header])

    data = data.lower()

    # 3
    data += request.body

    # calculate HMAC SHA256
    calc_signature = base64.b64encode(hmac.new(fbn_santa_sync_key, data, digestmod=hashlib.sha256).digest())

    if calc_signature != fbn_auth_signature:
      logging.error("Invalid FBN Santa Sync signature")
      return True  # TODO: make this false

  except:
    logging.exception("Error performing validation")

  logging.info('No santa client authentication performed')
  return True
