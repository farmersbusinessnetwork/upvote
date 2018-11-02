#!/usr/bin/env python3
import argparse
import subprocess
import enum
import re
import sys
import os
from datetime import datetime, timezone


import plistlib
import psutil
from dateutil.parser import parse as dt_parse
import requests


class State(enum.IntEnum):
    PRE_CHAIN = 0
    SIGNING_CHAIN = 1


chain_num_re = re.compile(r'(?P<num>\d+)\. (?P<key>.*)')


def _now_utc():
    return datetime.utcnow().replace(tzinfo=timezone.utc)


def _get_hardware_uuid():
    plist_data = subprocess.check_output(["ioreg", "-rd1", "-c", "IOPlatformExpertDevice", "-a"])
    hardware_uuid = plistlib.loads(plist_data)[0]["IOPlatformUUID"]
    return hardware_uuid


def _get_fileinfo(path: str):
    # Gather and parse output from santactl fileinfo
    output = subprocess.check_output(['/usr/local/bin/santactl', 'fileinfo', path]).decode(sys.stdout.encoding)

    state = State.PRE_CHAIN
    file_info = dict()
    signing_chain = list()
    cert = dict()
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue

        key, value = map(str.strip, line.split(':', 1))

        if state == State.PRE_CHAIN:
            if key == "Signing Chain":
                state = State.SIGNING_CHAIN
                file_info[key] = signing_chain
            else:
                file_info[key] = value
        elif state == State.SIGNING_CHAIN:
            m = chain_num_re.match(key)
            if m:
                if cert:
                    signing_chain.append(cert)
                    cert = dict()
                assert int(m.group('num')) == len(signing_chain) + 1

                key = m.group('key')

            cert[key] = value

        else:
            assert False

    if cert:
        signing_chain.append(cert)

    return file_info


def _file_info_to_sync_obj(file_info: dict):
    now_utc = _now_utc()

    file_path, file_name = file_info['Path'].rsplit('/', 1)
    current_user = os.getlogin()

    users = psutil.users()

    sync_obj = {
        'parent_name': None,
        'execution_time': now_utc.timestamp(),
        'file_name': file_name,
        'file_path': file_path,
        'file_sha256': file_info['SHA-256'],
        'decision': 'ALLOW_UNKNOWN',
        'pid': -1,
        'ppid': 0,
        'quarantine_timestamp': 0,
        'current_sessions': [f'{user.name}@{user.terminal}' for user in users],
        'logged_in_users': list({user.name for user in users}),
        'executing_user': current_user,
    }

    if file_info.get("Signing Chain"):
        signing_chain = []
        sync_obj['signing_chain'] = signing_chain

        for cert in file_info["Signing Chain"]:
            sync_cert = {
                'valid_from': dt_parse(cert['Valid From']).timestamp(),
                'valid_until': dt_parse(cert['Valid Until']).timestamp(),
                'cn': cert['Common Name'],
                'org': cert['Organization'],
                'ou': cert['Organizational Unit'],
                'sha256': cert['SHA-256']
            }
            signing_chain.append(sync_cert)

    return sync_obj


def _fetch_xsrf_token(session: requests.Session, machine_id: str):
    response = session.post(f'https://santaupvote.appspot.com/api/santa/xsrf/{machine_id}')
    assert response.status_code == 200, f"response failed with code: {response.status_code}"
    return response.headers['X-XSRF-TOKEN']


def main():
    parser = argparse.ArgumentParser(description='Submit sync event for file')
    parser.add_argument('path', type=str, help='File path')
    app_args = parser.parse_args()

    # Gather and parse output from santactl fileinfo
    file_info = _get_fileinfo(app_args.path)

    # Translate to sync object
    sync_info = _file_info_to_sync_obj(file_info)

    # send to upvote
    machine_id = _get_hardware_uuid()
    with requests.Session() as session:
        xsrf_token = _fetch_xsrf_token(session, machine_id)
        response = session.post(f'https://santaupvote.appspot.com/api/santa/eventupload/{machine_id}', json={'events': [sync_info]}, headers={"X-XSRF-TOKEN": xsrf_token})
        assert response.status_code == 200, f"response failed with code: {response.status_code}"
        print(response)


if __name__ == '__main__':
    main()
