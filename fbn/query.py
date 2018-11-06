#!/usr/bin/env python3
import asyncio
from typing import List

import google.oauth2.credentials
from google.oauth2 import service_account
from google_auth_oauthlib.flow import InstalledAppFlow
from google.cloud import bigquery
from google.auth import app_engine
import keyring
import json
import pandas


APP_NAME = 'SantaUpVoteHelper'

CLIENT_JSON_PATH = '/Users/amohr/Downloads/santa_upvote_client_oauth_credentials.json'
SCOPES = ['https://www.googleapis.com/auth/bigquery']


NEEDS_ACTION_QUERY = """SELECT
  e.*,
  b.state as bin_state, b.action as bin_action,
  c.fingerprint as cert_fingerprint, c.action as cert_action, c.state as cert_state
FROM
  gae_streaming.Execution AS e
LEFT JOIN
  gae_streaming.Binary AS b
ON
  e.sha256 = b.sha256
LEFT JOIN gae_streaming.Certificate as c
    ON
      b.cert_fingerprint = c.fingerprint
ORDER BY e.timestamp DESC
LIMIT 10;"""


# Format Parameters: [user]
NEEDS_ACTION_USER_QUERY = """SELECT
  e.*,
  b.state as bin_state, b.action as bin_action,
  c.fingerprint as cert_fingerprint, c.action as cert_action, c.state as cert_state
FROM
  gae_streaming.Execution AS e
LEFT JOIN
  gae_streaming.Binary AS b
ON
  e.sha256 = b.sha256
LEFT JOIN gae_streaming.Certificate as c
    ON
      b.cert_fingerprint = c.fingerprint
WHERE "{user}" IN UNNEST(associated_users) AND cert_fingerprint is not NULL
ORDER BY e.timestamp DESC
LIMIT 10;"""


UNKNOWN_QUERY = """SELECT
  e.*,
  b.state as bin_state, b.action as bin_action,
  c.fingerprint as cert_fingerprint, c.action as cert_action, c.state as cert_state
FROM
  gae_streaming.Execution AS e
LEFT JOIN
  gae_streaming.Binary AS b
ON
  e.sha256 = b.sha256
LEFT JOIN gae_streaming.Certificate as c
    ON
      b.cert_fingerprint = c.fingerprint
WHERE decision IN ('ALLOW_UNKNOWN', 'BLOCK_UNKNOWN') 
ORDER BY e.timestamp DESC
LIMIT 10;"""


# Parameters: [cert_sha256]
EVENTS_WHICH_USE_CERT = """SELECT
  e.*,
  b.state as bin_state, b.action as bin_action,
  c.fingerprint as cert_fingerprint, c.action as cert_action, c.state as cert_state
FROM
  gae_streaming.Execution AS e
LEFT JOIN
  gae_streaming.Binary AS b
ON
  e.sha256 = b.sha256
LEFT JOIN gae_streaming.Certificate as c
    ON
      b.cert_fingerprint = c.fingerprint
WHERE c.fingerprint = "{cert_sha256}"
ORDER BY e.timestamp DESC
LIMIT 10;
"""

# ----- STATES -----
# Initial state. Voting is allowed
# 'UNTRUSTED',

# Trusted without further votes but still requires host-specific
# authorization. Voting is allowed.
# 'APPROVED_FOR_LOCAL_WHITELISTING',

# Blockable can run on hosts with an authorization or hosts in monitor mode.
# Voting is disabled.
# 'LIMITED',

# Allowed globally everywhere without host-specific approval
# Voting is disabled.
# 'GLOBALLY_WHITELISTED',

# Still in an untrusted state, but an administrator has voted 'no'.
# Normal users may not vote until the 'no' vote is removed.
# 'SUSPECT',

# Not allowed to run anywhere, can't be voted on
# Reserved for malware.
# Voting is disabled.
# Users who had voted before the binary was banned are no longer trusted.
# 'BANNED',

# Not allowed to run anywhere and users receive no notification.
# Very limited use.
# Voting is disabled.
# 'SILENT_BANNED',

# Blockable is whitelisted but pending pick-up by syncing system.
# 'PENDING'


def do_auth(app_name: str, client_json_path: str, scopes: List[str]):
    secret = keyring.get_password(APP_NAME, 'token')

    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_JSON_PATH, scopes=scopes)

    if secret:
        flow.oauth2session.token = json.loads(secret)
    else:
        # credentials = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
        flow.run_local_server()  # run_console

        secret = json.dumps(flow.oauth2session.token)
        keyring.set_password(APP_NAME, 'token', secret)

    return flow.credentials


async def main():
    pandas.set_option('display.width', 1000)
    pandas.set_option('display.max_colwidth', 1000)

    credentials = do_auth(APP_NAME, CLIENT_JSON_PATH, SCOPES)

    client = bigquery.Client(project='santaupvote', credentials=credentials)
    query_job = client.query(EVENTS_WHICH_USE_CERT.format(cert_sha256='09d93952b7b31903e1d9b85d5c8b48bbb86ad9830757ee5e75cd114fbb7e7303'))
    result = query_job.result()

    if 1:
        results = result.to_dataframe()
        print(results)
    else:
        for row in result:
            print(row)


if __name__ == '__main__':
    asyncio.get_event_loop().run_until_complete(main())