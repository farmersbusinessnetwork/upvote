# Copyright 2018 FBN Inc. All Rights Reserved.
#
"""NDB models for DataDog interactions."""

from common.cloud_kms import kms_ndb
from upvote.gae.datastore.models import singleton

_KEY_LOC = 'global'
_KEY_RING = 'ring'
_KEY_NAME = 'fbn_santa_sync'


class FBNSantaSyncAuth(singleton.Singleton):
  """The FBN Santa Sync Auth secret key.

  This class is intended to be a singleton as there should only be a single
  FBNSantaSync key associated with a project.
  """
  api_key = kms_ndb.EncryptedBlobProperty(_KEY_NAME, _KEY_RING, _KEY_LOC)
