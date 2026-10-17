#!/usr/bin/env python3
"""Run the reduced default VPS CVAT stack in an isolated project and prove it can create a task from an uploaded image, read its frame with the read-only adapter and deny writes; never use existing CVAT data/accounts."""
import argparse
import json
import os
import re
from pathlib import Path
import secrets
import subprocess
import tempfile
import textwrap
import time
import urllib.error
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[2]
CVAT = ROOT / 'infrastructure/cvat'


def tus_location(base_url, token):
    """Start a TUS upload through the published router port, as the K3s ingress does, and return Location."""
    # The router matches Host(`${CVAT_HOST:-localhost}`); the isolated stack keeps the default.
    headers = {'Host': 'localhost', 'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.cvat+json', 'X-Forwarded-Proto': 'https'}
    create = urllib.request.Request(base_url + '/api/tasks', method='POST', headers=headers | {'Content-Type': 'application/json'},
        data=json.dumps({'name': 'isolated-tus-test', 'labels': [{'name': 'car'}]}).encode())
    try:
        with urllib.request.urlopen(create, timeout=30) as response:
            task_id = json.load(response)['id']
        start = urllib.request.Request(f'{base_url}/api/tasks/{task_id}/data', method='POST', data=b'',
            headers=headers | {'Tus-Resumable': '1.0.0', 'Upload-Length': '10', 'Upload-Metadata': 'filename bGl0ZS5wbmc='})
        with urllib.request.urlopen(start, timeout=30) as response:
            return response.headers.get('Location', '')
    except OSError as error:
        # Never surface URLs, headers or bodies: they can carry generated credentials.
        raise RuntimeError('CVAT TUS check request failed with ' + (f'HTTP {error.code}' if isinstance(error, urllib.error.HTTPError) else type(error).__name__)) from None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend', required=True)
    args = parser.parse_args()
    project = 'labelx-cvat-test-' + uuid.uuid4().hex[:8]
    resources = json.loads((CVAT / 'resources.json').read_text())
    service_names = list(resources['memory_limits_mib'])
    default_services = set(resources['profiles']['default'])
    env = os.environ | {'CVAT_POSTGRES_PASSWORD': secrets.token_hex(24), 'CLICKHOUSE_PASSWORD': secrets.token_hex(24), 'CVAT_GRAFANA_ADMIN_PASSWORD': secrets.token_hex(24)}
    with tempfile.TemporaryDirectory(prefix=project) as directory:
        override = Path(directory, 'isolation.yaml')
        text = 'services:\n'
        for name in service_names:
            text += f'  {name}:\n    container_name: {project}-{name}\n'
            if name == 'traefik':
                text += '    ports: !override\n      - "127.0.0.1::8080"\n'
                # Traefik reads the host Docker socket: without this constraint it would also route to any other CVAT on the host.
                text += '    environment:\n      TRAEFIK_PROVIDERS_DOCKER_CONSTRAINTS: "Label(`com.docker.compose.project`,`' + project + '`)"\n'
        override.write_text(text)
        command = ['docker', 'compose', '-p', project, '-f', str(CVAT / 'upstream/docker-compose.yml'),
            '-f', str(CVAT / 'compose.vps.yaml'), '-f', str(override)]

        def compose(*parts, input=None, check=True):
            result = subprocess.run(command + list(parts), input=input, env=env, text=True, capture_output=True)
            if check and result.returncode:
                # Config interpolation and tracebacks may contain generated credentials. Never print them.
                raise RuntimeError('Isolated CVAT command failed: ' + parts[0])
            return result

        def show_server_traceback(*services):
            # Server-side cause of a 5xx: print only traceback frames and exception lines, never env, headers or bodies.
            for service in services:
                logs = compose('logs', '--no-color', '--tail', '400', service, check=False).stdout
                frames = [line.split('|', 1)[-1].strip()[:240] for line in logs.splitlines()
                    if re.search(r'Traceback \(most recent|^\S.*\|\s+File "|\|\s*[A-Za-z_.]+(Error|Exception|DoesNotExist)\b', line)]
                print(f'{service} traceback lines:', *frames[-40:], sep='\n', flush=True)

        try:
            compose('up', '-d')
            for attempt in range(120):
                result = compose('exec', '-T', 'cvat_server', 'python3', '-c',
                    # OPA pulls its policy bundle from the server on a 5-15s poll; permission checks fail until it is active.
                    "import urllib.request,json; r=json.load(urllib.request.urlopen('http://127.0.0.1:8080/api/server/about',timeout=3)); assert r['version']=='2.77.0'; urllib.request.urlopen('http://opa:8181/health?bundles',timeout=3)", check=False)
                if result.returncode == 0:
                    break
                if attempt == 119:
                    raise RuntimeError('Isolated CVAT did not become ready')
                time.sleep(5)
            code = """
import json
from django.contrib.auth import get_user_model
from cvat.apps.access_tokens.models import AccessToken
User=get_user_model()
reader=User.objects.create_user(username='labelx_readonly_test')
admin=User.objects.create_superuser(username='labelx_provisioner_test',password=None)
_,read_key=AccessToken.objects.create_key(name='labelx-isolated',owner=reader,read_only=True)
_,write_key=AccessToken.objects.create_key(name='labelx-isolated-provisioner',owner=admin,read_only=False)
print('LABELX_TEST_CREDENTIAL:'+json.dumps({'token':read_key,'writer':write_key,'reader_id':reader.id}))
"""
            result = compose('exec', '-T', 'cvat_server', 'python3', 'manage.py', 'shell', input=code)
            line = next(line for line in result.stdout.splitlines() if line.startswith('LABELX_TEST_CREDENTIAL:'))
            credential = json.loads(line.split(':', 1)[1])
            # Real task creation exercises the import worker; the frame read below exercises the chunks worker.
            provision = """
import json,struct,sys,time,zlib,httpx
c=json.load(sys.stdin)
url='http://cvat-server:8080'
def chunk(kind,data): return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
rows=b''.join(b'\\x00'+b'\\x40\\x80\\xc0'*4 for _ in range(4))
png=b'\\x89PNG\\r\\n\\x1a\\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',4,4,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(rows))+chunk(b'IEND',b'')
try:
 with httpx.Client(headers={'Authorization':'Bearer '+c['writer'],'Accept':'application/vnd.cvat+json'},timeout=120) as w:
  print('CHECK task create',flush=True)
  task=w.post(url+'/api/tasks',json={'name':'isolated-lite-test','labels':[{'name':'car'}]}); task.raise_for_status(); task_id=task.json()['id']
  d=url+'/api/tasks/'+str(task_id)+'/data'
  w.post(d,headers={'Upload-Start':''}).raise_for_status()
  w.post(d,data={'image_quality':'70'},files=[('client_files[0]',('lite.png',png,'image/png'))],headers={'Upload-Multiple':''}).raise_for_status()
  print('CHECK task import worker',flush=True)
  finish=w.post(d,json={'image_quality':70,'sorting_method':'predefined','upload_file_order':['lite.png']},headers={'Upload-Finish':''}); finish.raise_for_status()
  rq=finish.json().get('rq_id') or finish.json().get('request_id')
  for _ in range(90):
   status=str(w.get(url+'/api/requests/'+str(rq)).json().get('status','')).lower()
   if status=='finished': break
   if status=='failed': raise RuntimeError('import failed')
   time.sleep(2)
  else: raise RuntimeError('import timeout')
  jobs=w.get(url+'/api/jobs',params={'task_id':task_id}).json()['results']; job_id=jobs[0]['id']
  w.patch(url+'/api/jobs/'+str(job_id),json={'assignee':c['reader_id']}).raise_for_status()
  print('LABELX_JOB:'+json.dumps({'job':job_id,'task':task_id}))
except Exception as error:
 print('CHECK_ERROR:'+json.dumps({'type':type(error).__name__,'status':getattr(getattr(error,'response',None),'status_code',None)}),flush=True)
 raise SystemExit(1)
"""
            prepared = subprocess.run(['docker', 'run', '--rm', '-i', '--network', project + '_cvat', args.backend,
                'python', '-c', provision], input=json.dumps(credential), text=True, capture_output=True)
            for row in prepared.stdout.splitlines():
                if row in {'CHECK task create', 'CHECK task import worker'}:
                    print(row, flush=True)
                elif row.startswith('CHECK_ERROR:'):
                    detail = json.loads(row.split(':', 1)[1])
                    kind, status = detail.get('type', ''), detail.get('status')
                    if isinstance(kind, str) and kind.isidentifier() and (status is None or isinstance(status, int)):
                        print(f'CHECK failure type={kind} status={status}', flush=True)
            if prepared.returncode:
                show_server_traceback('cvat_server', 'cvat_worker_import', 'cvat_opa')
                raise RuntimeError('CVAT task provisioning failed; generated credentials omitted')
            created = json.loads(next(row for row in prepared.stdout.splitlines() if row.startswith('LABELX_JOB:')).split(':', 1)[1])
            # The K3s ingress reaches this router through docker-proxy, which appears as the compose network gateway.
            # Untrusted forwarded headers would be rewritten to http and CVAT would hand browsers http:// upload URLs.
            print('CHECK tus location https', flush=True)
            port = compose('port', 'traefik', '8080').stdout.strip().rsplit(':', 1)[1]
            try:
                location = tus_location('http://127.0.0.1:' + port, credential['writer'])
            except RuntimeError:
                # The router access log keeps only status, method, path and client address by configuration.
                logs = compose('logs', '--no-color', '--tail', '25', 'traefik', check=False).stdout
                print('traefik log tail:', *[line.split('|', 1)[-1].strip()[:300] for line in logs.splitlines()], sep='\n', flush=True)
                raise
            if not location.startswith('https://'):
                raise RuntimeError('CVAT upload Location is not https behind the router; CVAT_TRUSTED_PROXY_CIDRS must include the Docker network gateway')
            credential = json.dumps({'token': credential['token'], 'job': created['job']})
            test = """
import json,sys,httpx
from cvat_adapter.client import CvatReadClient,CvatWriteBlocked
c=json.load(sys.stdin)
url='http://cvat-server:8080'
with CvatReadClient(url,c['token']) as client:
 print('CHECK jobs GET',flush=True)
 jobs=client.list_jobs(); assert any(j['id']==c['job'] for j in jobs)
 print('CHECK annotations GET',flush=True)
 data=client._get('api/jobs/'+str(c['job'])+'/annotations'); assert isinstance(data,dict)
 print('CHECK job data meta',flush=True)
 meta=client.get_job_data_meta(c['job']); assert meta.get('size')==1
 print('CHECK frame chunks worker',flush=True)
 body,kind=client.get_job_frame(c['job'],0); assert body and kind.startswith('image/'), kind
 print('CHECK adapter mutation guard',flush=True)
 try: client._client.patch(url+'/api/jobs/'+str(c['job'])+'/annotations',json={})
 except CvatWriteBlocked: pass
 else: raise AssertionError('Adapter allowed mutation')
print('CHECK server mutation denial',flush=True)
r=httpx.patch(url+'/api/jobs/'+str(c['job'])+'/annotations',headers={'Authorization':'Bearer '+c['token']},json={'version':0,'tags':[],'shapes':[],'tracks':[]})
assert r.status_code==403, r.status_code
print('PASS real CVAT 2.77.0 reduced stack: task import, jobs/annotations/meta/frame GET with read-only PAT, adapter mutation guard, server read-only PATCH denial')
"""
            test = "try:\n" + textwrap.indent(test, " ") + "\nexcept Exception as error:\n import json\n print('CHECK_ERROR:'+json.dumps({'type':type(error).__name__,'status':getattr(getattr(error,'response',None),'status_code',None)}),flush=True)\n raise SystemExit(1)\n"
            result = subprocess.run(['docker', 'run', '--rm', '-i', '--network', project + '_cvat', args.backend,
                'python', '-c', test], input=credential, text=True, capture_output=True)
            if result.returncode:
                # Only fixed stage labels are safe; never expose HTTP bodies, URLs or credentials.
                stages = {'CHECK jobs GET', 'CHECK annotations GET', 'CHECK job data meta', 'CHECK frame chunks worker', 'CHECK adapter mutation guard', 'CHECK server mutation denial'}
                for line in result.stdout.splitlines():
                    if line in stages:
                        print(line, flush=True)
                    elif line.startswith('CHECK_ERROR:'):
                        detail = json.loads(line.split(':', 1)[1])
                        kind = detail.get('type', '')
                        status = detail.get('status')
                        if isinstance(kind, str) and kind.isidentifier() and (status is None or isinstance(status, int)):
                            print(f'CHECK failure type={kind} status={status}', flush=True)
                show_server_traceback('cvat_server')
                raise RuntimeError('CVAT read-only adapter integration failed; generated credentials omitted')
            print(result.stdout.strip())
            info = compose('ps', '-a', '--format', 'json').stdout
            rows = [json.loads(line) for line in info.splitlines() if line.strip()]
            failed = [row['Service'] for row in rows if row.get('State') != 'running']
            if failed:
                raise RuntimeError('Isolated CVAT services not running: ' + ','.join(failed))
            started = {row['Service'] for row in rows}
            if started != default_services:
                raise RuntimeError('Isolated CVAT did not start exactly the default profile: ' + ','.join(sorted(started ^ default_services)))
            print('PASS pinned upstream reduced VPS stack (default profile, no ClickHouse/Vector/Grafana, no optional workers) started with resource limits; this is not VPS/load/HTTPS evidence')
        finally:
            # Unique project created by this process only. Never run down -v on an operator deployment.
            compose('down', '--volumes', '--remove-orphans', check=False)


if __name__ == '__main__':
    main()
