#!/usr/bin/env python3
import asyncio

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


async def main():
    credentials = do_auth(APP_NAME, CLIENT_JSON_PATH, SCOPES)

    client = datastore.Client(project='santaupvote', credentials=credentials)

    for cert_sha256 in CRITICAL_MAC_OS_CERT_HASHES:
        key = client.key('Blockable', cert_sha256)

        items = list(client.query(kind='Rule', ancestor=key).fetch())
        assert len(items) == 1 and items[0]['policy'] == 'WHITELIST', f"Error finding rule for Blockable: {cert_sha256}, items: {items}"

if __name__ == '__main__':
    asyncio.get_event_loop().run_until_complete(main())
