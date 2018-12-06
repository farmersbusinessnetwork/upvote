#!/usr/bin/env python3

# FBN
from google.cloud import datastore
from query import do_auth


APP_NAME = 'SantaUpVoteHelper'
CLIENT_JSON_PATH = '/Users/amohr/Downloads/santa_upvote_client_oauth_credentials.json'
SCOPES = ['https://www.googleapis.com/auth/datastore']


# from upvote/gae/shared/common/settings.py
CRITICAL_MAC_OS_CERT_HASHES = [

    # Google Certificate for Chrome
    '345a8e098bd04794aaeefda8c9ef56a0bf3d3706d67d35bc0e23f11bb3bffce5',

    # Apple Software Signing for macOS 10.10, 10.11, 10.12, and 10.13
    '2aa4b9973b7ba07add447ee4da8b5337c3ee2c3a991911e80e7282e8a751fc32',

    # Google Certificate for Santa
    '33b9aee3b089c922952c9240a40a0daa271bebf192cf3f7d964722e8f2170e48']


def main():
    credentials = do_auth(APP_NAME, CLIENT_JSON_PATH, SCOPES)

    client = datastore.Client(project='santaupvote', credentials=credentials)

    for cert_sha256 in CRITICAL_MAC_OS_CERT_HASHES:
        key = client.key('Blockable', cert_sha256)

        items = list(client.query(kind='Rule', ancestor=key).fetch())

        # strangely, there can be more than one rule for a binary: https://console.cloud.google.com/datastore/entities;kind=Rule;ns=__$DEFAULT$__/query/kind;filter=%5B%227%2F__key__%7CKEY%7CAN%7C112%2FS2V5KCdCbG9ja2FibGUnLCAnMzQ1YThlMDk4YmQwNDc5NGFhZWVmZGE4YzllZjU2YTBiZjNkMzcwNmQ2N2QzNWJjMGUyM2YxMWJiM2JmZmNlNScp%22%5D?organizationId=485344983296&orgonly=true&project=santaupvote&supportedpurview=organizationId
        for item in items:
            assert item['policy'] == 'WHITELIST' and item['in_effect'] is True, f"Error finding rule for Blockable: {cert_sha256}, items: {items}"


if __name__ == '__main__':
    main()
