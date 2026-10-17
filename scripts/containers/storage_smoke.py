#!/usr/bin/env python3
"""Test actual SeaweedFS scoped credentials, CORS and presigned URLs on an isolated network."""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import uuid
from smoke import docker, wait_until

ROOT = Path(__file__).resolve().parents[2]
S3 = 'chrislusf/seaweedfs:4.48@sha256:4e61d15fd35994cb1e43e1e553dff106794841fd9a99ade2fc8c8bfce4d7872d'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend', required=True)
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location('bootstrap', ROOT / 'scripts/deploy/bootstrap.py')
    bootstrap = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bootstrap)
    data = {item['metadata']['name']: item['stringData'] for item in bootstrap.build_documents({}, {}, set())}
    name = 'labelx-s3-test-' + uuid.uuid4().hex[:8]
    try:
        docker('network', 'create', name)
        docker('volume','create',name+'-data')
        docker('run','--rm','--user','0','--volume',name+'-data:/data','--entrypoint','sh',S3,'-c','chown -R 10001:10001 /data')
        with tempfile.TemporaryDirectory(prefix=name) as directory:
            path = Path(directory, 's3.json'); path.write_text(data['labelx-s3']['s3.json']); path.chmod(0o644)
            docker('run', '-d', '--name', name, '--network', name, '--network-alias', 's3', '--user', '10001:10001',
                '--read-only', '--memory', '512m', '--cpus', '1', '--pids-limit', '128', '--cap-drop', 'ALL', '--volume', name+'-data:/data', '--tmpfs', '/tmp:rw,size=64m',
                '--volume', str(path)+':/etc/s3.json:ro', '--volume', str(ROOT/'infrastructure/k8s/labelx/ops/master.toml')+':/etc/seaweedfs/master.toml:ro', S3, '-telemetry=false', 'server', '-dir=/data', '-s3', '-s3.port=9000',
                '-s3.config=/etc/s3.json', '-master.volumeSizeLimitMB=32', '-volume.max=12', '-s3.allowedOrigins=https://label-x.williamtrinh.online')
            wait_until(lambda: docker('run','--rm','--network',name,args.backend,'python','-c',
                "import socket; socket.create_connection(('s3',9000),timeout=2).close()",check=False).returncode==0,'isolated authenticated SeaweedFS')
            test = """
import boto3,json,sys,urllib.request,urllib.error
from botocore.config import Config
from botocore.exceptions import ClientError
v=json.load(sys.stdin)
def c(access,secret): return boto3.client('s3',endpoint_url='http://s3:9000',aws_access_key_id=access,aws_secret_access_key=secret,region_name='us-east-1',config=Config(signature_version='s3v4',s3={'addressing_style':'path'}))
a=c(v['admin']['ADMIN_ACCESS_KEY'],v['admin']['ADMIN_SECRET_KEY']); app=c(v['app']['OBJECT_STORAGE_ACCESS_KEY'],v['app']['OBJECT_STORAGE_SECRET_KEY'])
for bucket in ('labelx-snapshots','labelx-evidence','labelx-reports','not-an-app-bucket'):
 a.create_bucket(Bucket=bucket)
 a.put_bucket_cors(Bucket=bucket,CORSConfiguration={'CORSRules':[{'AllowedOrigins':['https://label-x.williamtrinh.online'],'AllowedMethods':['GET','HEAD','PUT','POST'],'AllowedHeaders':['*'],'ExposeHeaders':['ETag'],'MaxAgeSeconds':600}]})
for bucket in ('labelx-snapshots','labelx-evidence','labelx-reports'):
 app.put_object(Bucket=bucket,Key='test',Body=b'labelx-storage-test'); assert app.get_object(Bucket=bucket,Key='test')['Body'].read()==b'labelx-storage-test'
 assert app.list_objects_v2(Bucket=bucket)['KeyCount']==1
 url=app.generate_presigned_url('get_object',Params={'Bucket':bucket,'Key':'test'},ExpiresIn=60)
 with urllib.request.urlopen(urllib.request.Request(url,headers={'Origin':'https://label-x.williamtrinh.online'})) as r:
  assert r.read()==b'labelx-storage-test', 'presigned payload'; assert r.headers['Access-Control-Allow-Origin']=='https://label-x.williamtrinh.online', 'CORS='+r.headers.get('Access-Control-Allow-Origin','missing')
 try: urllib.request.urlopen('http://s3:9000/'+bucket+'/test')
 except urllib.error.HTTPError as e: assert e.code==403
 else: raise AssertionError('Unsigned object read allowed')
 # Exercise the real application signing path, including its configured TTL and authorization callback.
 import os,django
 os.environ.update(v['app']); os.environ['OBJECT_STORAGE_ENDPOINT_URL']='http://s3:9000'; os.environ['DJANGO_DEBUG']='False'; os.environ['DJANGO_ALLOWED_HOSTS']='localhost,s3'
 django.setup()
 from storage.client import ObjectStorage
 storage=ObjectStorage.from_django_settings({'labelx-snapshots':'snapshots','labelx-evidence':'evidence','labelx-reports':'reports'}[bucket])
 signed=storage.presigned_get_url('test',is_allowed=lambda _:True,expires_in=60)
 with urllib.request.urlopen(signed) as response: assert response.read()==b'labelx-storage-test', 'product presigning payload'
 app.delete_object(Bucket=bucket,Key='test')
try: app.put_object(Bucket='not-an-app-bucket',Key='forbidden',Body=b'no')
except ClientError as e: assert e.response['ResponseMetadata']['HTTPStatusCode']==403
else: raise AssertionError('App can write outside allowed buckets')
app.put_object(Bucket='labelx-evidence',Key='persistence-marker',Body=b'survives-restart')
print('PASS three application buckets, scoped credentials, unsigned/cross-bucket denial, presigned GET and browser CORS; isolated HTTP only')
"""
            test = 'try:\n' + ''.join(' '+line+'\n' for line in test.splitlines()) + '''except Exception as error:
 import traceback
 print(type(error).__name__, getattr(error,'response',{}).get('Error',{}).get('Code',''), getattr(error,'operation_name',''), str(error) if isinstance(error,AssertionError) else '', [(f.name,f.lineno) for f in traceback.extract_tb(error.__traceback__)[-3:]])
 raise SystemExit(1)
'''
            result = subprocess.run(['docker','run','--rm','-i','--network',name,args.backend,'python','-c',test],
                input=json.dumps({'admin':data['labelx-s3'],'app':data['labelx-runtime']}),capture_output=True,text=True)
            if result.returncode:
                # These are random test credentials; still avoid echoing request URLs/keys from SDK errors.
                raise RuntimeError('S3 isolated integration failed; sanitized diagnostic: ' + result.stdout.strip())
            print(result.stdout.strip())
            docker('restart',name)
            verify="import sys,json,boto3;v=json.load(sys.stdin)['app'];c=boto3.client('s3',endpoint_url='http://s3:9000',aws_access_key_id=v['OBJECT_STORAGE_ACCESS_KEY'],aws_secret_access_key=v['OBJECT_STORAGE_SECRET_KEY']);assert c.get_object(Bucket='labelx-evidence',Key='persistence-marker')['Body'].read()==b'survives-restart';c.delete_object(Bucket='labelx-evidence',Key='persistence-marker')"
            for attempt in range(30):
                result=subprocess.run(['docker','run','--rm','-i','--network',name,args.backend,'python','-c',verify],input=json.dumps({'app':data['labelx-runtime']}),capture_output=True,text=True)
                if result.returncode==0:break
                import time
                time.sleep(2)
            else:raise RuntimeError('S3 metadata/object persistence across container restart failed')
            print('PASS S3 bucket metadata and object bytes preserved across restart with fresh tmpfs')
    except BaseException:
        logs=docker('logs','--tail','25',name,check=False)
        diagnostic=logs.stdout+logs.stderr
        for item in data.values():
            for value in item.values():
                if isinstance(value,str) and len(value)>12:diagnostic=diagnostic.replace(value,'[redacted]')
        print(diagnostic)
        raise
    finally:
        docker('rm','-f',name,check=False);docker('network','rm',name,check=False);docker('volume','rm',name+'-data',check=False)


if __name__=='__main__': main()
