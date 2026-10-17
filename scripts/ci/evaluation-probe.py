#!/usr/bin/env python3
"""Probe explicitly isolated evaluation services; emit credential-free JSON only."""
import argparse
import json
import os
import re
import sys
import uuid


def configuration(env):
    if env.get('LABELX_EVALUATION_ISOLATED') != 'true':
        raise ValueError('Isolation acknowledgement required')
    namespace = env.get('LABELX_TEST_NAMESPACE', '')
    if not re.fullmatch(r'ci-[a-zA-Z0-9-]{1,64}', namespace):
        raise ValueError('Expected ci- namespace with at most 64 suffix characters')
    required = ('DATABASE_URL', 'CELERY_BROKER_URL', 'CELERY_RESULT_BACKEND',
                'OBJECT_STORAGE_ENDPOINT_URL', 'OBJECT_STORAGE_ACCESS_KEY',
                'OBJECT_STORAGE_SECRET_KEY', 'OBJECT_STORAGE_BUCKET')
    if any(not env.get(name) for name in required):
        raise ValueError('Missing evaluation service configuration')
    return namespace


def database(env, token):
    import psycopg
    # Temporary table and uncommitted transaction never touch application rows.
    with psycopg.connect(env['DATABASE_URL'], connect_timeout=5) as connection:
        try:
            connection.execute("SET statement_timeout = '5s'")
            connection.execute('CREATE TEMP TABLE evaluation_probe (value text) ON COMMIT DROP')
            connection.execute('INSERT INTO evaluation_probe VALUES (%s)', (token,))
            if connection.execute('SELECT value FROM evaluation_probe').fetchone() != (token,):
                raise RuntimeError('Database round trip failed')
        finally:
            connection.rollback()


def redis_service(url, token):
    import redis
    client = redis.Redis.from_url(url, socket_connect_timeout=5, socket_timeout=5)
    created = False
    try:
        if not client.ping():
            raise RuntimeError('Redis health failed')
        created = bool(client.set(token, token, nx=True, ex=60))
        if not created or client.get(token) != token.encode():
            raise RuntimeError('Redis round trip failed')
    finally:
        try:
            if created:
                client.delete(token)
        finally:
            client.close()


def storage(env, token):
    import boto3
    from botocore.config import Config
    client = boto3.client('s3', endpoint_url=env['OBJECT_STORAGE_ENDPOINT_URL'],
                          aws_access_key_id=env['OBJECT_STORAGE_ACCESS_KEY'],
                          aws_secret_access_key=env['OBJECT_STORAGE_SECRET_KEY'],
                          region_name=env.get('OBJECT_STORAGE_REGION', 'us-east-1'),
                          config=Config(signature_version='s3v4', connect_timeout=5,
                                        read_timeout=5, retries={'max_attempts': 1},
                                        s3={'addressing_style': 'path'}))
    location = {'Bucket': env['OBJECT_STORAGE_BUCKET'], 'Key': token + '/probe.txt'}
    body = b'labelx-evaluation-isolation-probe'
    try:
        client.head_bucket(Bucket=location['Bucket'])
        client.put_object(**location, Body=body)
        if client.head_object(**location)['ContentLength'] != len(body):
            raise RuntimeError('Object HEAD mismatch')
        response = client.get_object(**location)
        try:
            if response['Body'].read() != body:
                raise RuntimeError('Object GET mismatch')
        finally:
            response['Body'].close()
    finally:
        # Exact unique key only. No prefix listing, bucket deletion or shared flush.
        try:
            client.delete_object(**location)
        finally:
            client.close()


def run(env):
    namespace = configuration(env)
    token = namespace + '/health-' + uuid.uuid4().hex
    checks = {}
    probes = {'postgres': lambda: database(env, token),
              'redis_broker': lambda: redis_service(env['CELERY_BROKER_URL'], token + '-broker'),
              'redis_results': lambda: redis_service(env['CELERY_RESULT_BACKEND'], token + '-results'),
              's3_put_head_get_delete': lambda: storage(env, token)}
    for name, probe in probes.items():
        try:
            probe()
            checks[name] = 'PASS'
        except Exception:
            # SDK exceptions can contain credentials, endpoint URLs or signed query strings.
            checks[name] = 'FAIL'
    return {'schema_version': 1, 'namespace': namespace,
            'status': 'PASS' if all(v == 'PASS' for v in checks.values()) else 'FAIL',
            'checks': checks}


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    try:
        result = run(os.environ)
    except ValueError:
        result = {'schema_version': 1, 'status': 'BLOCKED', 'reason': 'invalid_isolated_configuration'}
    print(json.dumps(result, sort_keys=True))
    return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
