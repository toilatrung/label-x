#!/usr/bin/env python3
"""Run the pinned VPS CVAT stack in an isolated project; never use existing CVAT data/accounts."""
import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
CVAT = ROOT / 'infrastructure/cvat'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend', required=True)
    args = parser.parse_args()
    project = 'labelx-cvat-test-' + uuid.uuid4().hex[:8]
    service_names = list(json.loads((CVAT / 'resources.json').read_text())['memory_limits_mib'])
    env = os.environ | {'CVAT_POSTGRES_PASSWORD': secrets.token_hex(24), 'CLICKHOUSE_PASSWORD': secrets.token_hex(24)}
    with tempfile.TemporaryDirectory(prefix=project) as directory:
        override = Path(directory, 'isolation.yaml')
        text = 'services:\n'
        for name in service_names:
            text += f'  {name}:\n    container_name: {project}-{name}\n'
            if name == 'traefik':
                text += '    ports: !override\n      - "127.0.0.1::8080"\n'
        override.write_text(text)
        command = ['docker', 'compose', '-p', project, '-f', str(CVAT / 'upstream/docker-compose.yml'),
            '-f', str(CVAT / 'compose.vps.yaml'), '-f', str(override)]

        def compose(*parts, input=None, check=True):
            result = subprocess.run(command + list(parts), input=input, env=env, text=True, capture_output=True)
            if check and result.returncode:
                # Config interpolation and tracebacks may contain generated credentials. Never print them.
                raise RuntimeError('Isolated CVAT command failed: ' + parts[0])
            return result

        try:
            compose('up', '-d')
            for attempt in range(120):
                result = compose('exec', '-T', 'cvat_server', 'python3', '-c',
                    "import urllib.request,json; r=json.load(urllib.request.urlopen('http://127.0.0.1:8080/api/server/about',timeout=3)); assert r['version']=='2.77.0'", check=False)
                if result.returncode == 0:
                    break
                if attempt == 119:
                    raise RuntimeError('Isolated CVAT did not become ready')
                time.sleep(5)
            code = """
import json
from django.contrib.auth import get_user_model
from cvat.apps.access_tokens.models import AccessToken
from cvat.apps.engine.models import Task,Data,Segment,Job
u=get_user_model().objects.create_user(username='labelx_readonly_test')
d=Data.objects.create(chunk_size=1,size=1,image_quality=70)
t=Task.objects.create(name='isolated-pat-test',owner=u,assignee=u,data=d)
s=Segment.objects.create(task=t,start_frame=0,stop_frame=0)
j=Job.objects.create(segment=s,assignee=u)
_,key=AccessToken.objects.create_key(name='labelx-isolated',owner=u,read_only=True)
print('LABELX_TEST_CREDENTIAL:'+json.dumps({'token':key,'job':j.id}))
"""
            result = compose('exec', '-T', 'cvat_server', 'python3', 'manage.py', 'shell', input=code)
            line = next(line for line in result.stdout.splitlines() if line.startswith('LABELX_TEST_CREDENTIAL:'))
            credential = line.split(':', 1)[1]
            test = """
import json,sys,httpx
from cvat_adapter.client import CvatReadClient,CvatWriteBlocked
c=json.load(sys.stdin)
url='http://cvat-server:8080'
with CvatReadClient(url,c['token']) as client:
 jobs=client.list_jobs(); assert any(j['id']==c['job'] for j in jobs)
 data=client._get('api/jobs/'+str(c['job'])+'/annotations'); assert isinstance(data,dict)
 try: client._client.patch(url+'/api/jobs/'+str(c['job'])+'/annotations',json={})
 except CvatWriteBlocked: pass
 else: raise AssertionError('Adapter allowed mutation')
r=httpx.patch(url+'/api/jobs/'+str(c['job'])+'/annotations',headers={'Authorization':'Bearer '+c['token']},json={'version':0,'tags':[],'shapes':[],'tracks':[]})
assert r.status_code==403, r.status_code
print('PASS real CVAT 2.77.0 PAT: jobs/annotations GET, adapter mutation guard, server read-only PATCH denial')
"""
            result = subprocess.run(['docker', 'run', '--rm', '-i', '--network', project + '_cvat', args.backend,
                'python', '-c', test], input=credential, text=True, capture_output=True)
            if result.returncode:
                raise RuntimeError('CVAT read-only adapter integration failed; generated credentials omitted')
            print(result.stdout.strip())
            info = compose('ps', '-a', '--format', 'json').stdout
            rows = [json.loads(line) for line in info.splitlines() if line.strip()]
            failed = [row['Service'] for row in rows if row.get('State') != 'running']
            if failed:
                raise RuntimeError('Isolated CVAT services not running: ' + ','.join(failed))
            print('PASS pinned upstream VPS stack started with resource limits; this is not VPS/load/HTTPS evidence')
        finally:
            # Unique project created by this process only. Never run down -v on an operator deployment.
            compose('down', '--volumes', '--remove-orphans', check=False)


if __name__ == '__main__':
    main()
