#!/usr/bin/env python3
"""Coherent encrypted same-VPS CVAT backup with explicit maintenance; no automatic restore."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile
from datetime import datetime,timezone

ROOT=Path(__file__).resolve().parents[2]
CVAT=ROOT/'infrastructure/cvat'
PG='postgres:15-alpine@sha256:f7d23353e1b15400d22ebe31189f4d314b87a4c129cc400c8c2d8d4ca127bf81'


def run(command,**kwargs):
    result=subprocess.run(command,capture_output=True,check=False,**kwargs)
    if result.returncode:raise RuntimeError('CVAT backup command failed; credentials omitted')
    return result.stdout


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file',type=Path,required=True)
    parser.add_argument('--recovery-file',type=Path,required=True)
    parser.add_argument('--destination',type=Path,required=True,help='New private directory outside Git')
    parser.add_argument('--maintenance',action='store_true',required=True)
    args=parser.parse_args()
    if os.geteuid()!=0:raise RuntimeError("Run with sudo for coherent read-only volume archival")
    for path in (args.env_file,args.recovery_file):
        if path.stat().st_mode&0o077:raise RuntimeError('Private files must have mode 0600')
    if args.destination.resolve().is_relative_to(ROOT) or args.destination.exists():
        raise RuntimeError('Use a new backup destination outside Git')
    recovery=json.loads(args.recovery_file.read_text())
    key=next(item['stringData']['BACKUP_ENCRYPTION_KEY'] for item in recovery['items'] if item['metadata']['name']=='labelx-backup')
    receipt=json.loads((ROOT/'infrastructure/k8s/labelx/release.json').read_text())
    backend=receipt['images']['backend']['reference']
    if not re.fullmatch(r'ghcr.io/toilatrung/labelx-backend@sha256:[a-f0-9]{64}',backend):raise RuntimeError('Pinned backend required')
    compose=['docker','compose','--env-file',str(args.env_file),'-p','cvat','-f',str(CVAT/'upstream/docker-compose.yml'),'-f',str(CVAT/'compose.vps.yaml')]
    rows=[json.loads(line) for line in run(compose+['ps','-a','--format','json']).decode().splitlines() if line]
    running=[row['Service'] for row in rows if row.get('State')=='running']
    if 'cvat_server' not in running or 'cvat_db' not in running:raise RuntimeError('Inspect existing CVAT state before backup')
    volumes=set()
    for row in rows:
        mounts=json.loads(run(['docker','inspect','--format','{{json .Mounts}}',row['ID']]))
        volumes.update(m['Name'] for m in mounts if m['Type']=='volume')
    total=0
    for volume in volumes:
        if not re.fullmatch(r'[a-zA-Z0-9_.-]+',volume):raise RuntimeError('Invalid volume name')
        total+=int(run(['docker','run','--rm','--network','none','--volume',volume+':/source:ro',PG,'du','-sk','/source']).split()[0])*1024
    if shutil.disk_usage(args.destination.parent).free < total*3+8*1024**3:
        raise RuntimeError('Insufficient disk for coherent staging + encrypted backup + 8GiB headroom')
    args.destination.mkdir(mode=0o700)
    backup_id='cvat-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    os.umask(0o077)
    try:
        with tempfile.TemporaryDirectory(prefix='.staging-',dir=args.destination) as directory:
            stage=Path(directory)
            # Quiesce all writers and queues before the logical DB dump, then freeze all volumes.
            run(compose+['stop']+[service for service in running if service!='cvat_db'])
            with (stage/'database.dump').open('wb') as dump:
                result=subprocess.run(compose+['exec','-T','cvat_db','pg_dump','-U','root','--format=custom','cvat'],stdout=dump,stderr=subprocess.PIPE)
                if result.returncode:raise RuntimeError('CVAT pg_dump failed; credentials omitted')
            run(compose+['stop','cvat_db'])
            for volume in sorted(volumes):
                run(['docker','run','--rm','--network','none','--read-only','--volume',volume+':/source:ro','--volume',str(stage)+':/backup',PG,'tar','-C','/source','-czf','/backup/'+volume+'.tgz','.'])
            shutil.copyfile(args.env_file,stage/'cvat-private.env')
            metadata={'backup_id':backup_id,'location':'same-vps','disaster_recovery':'unverified','volumes':sorted(volumes),'upstream':json.loads((CVAT/'upstream-lock.json').read_text())['commit']}
            (stage/'manifest.json').write_text(json.dumps(metadata,indent=2))
            plain=stage/'archive.tar'
            with tarfile.open(plain,'w') as archive:
                for path in list(stage.iterdir()):
                    if path!=plain:archive.add(path,arcname=path.name)
            encrypted=args.destination/(backup_id+'.tar.enc')
            run(['docker','run','--rm','--user','0','-i','--network','none','--volume',str(args.destination)+':/backup','--volume',str(ROOT/'scripts/deploy/crypt_backup.py')+':/crypt.py:ro',backend,'python','/crypt.py','--input','/backup/'+stage.name+'/archive.tar','--output','/backup/'+encrypted.name],input=json.dumps({'key':key,'aad':backup_id}).encode())
            with encrypted.open('rb') as file:metadata['encrypted_sha256']=hashlib.file_digest(file,'sha256').hexdigest()
            # Verify authenticated round-trip before accepting the backup file.
            run(['docker','run','--rm','--user','0','-i','--network','none','--volume',str(args.destination)+':/backup','--volume',str(ROOT/'scripts/deploy/crypt_backup.py')+':/crypt.py:ro',backend,'python','/crypt.py','--decrypt','--input','/backup/'+encrypted.name,'--output','/backup/'+stage.name+'/verified.tar'],input=json.dumps({'key':key,'aad':backup_id}).encode())
            with plain.open('rb') as original,(stage/'verified.tar').open('rb') as verified:
                if hashlib.file_digest(original,'sha256').digest()!=hashlib.file_digest(verified,'sha256').digest():raise RuntimeError('CVAT archive round-trip failed')
            (args.destination/(backup_id+'.json')).write_text(json.dumps(metadata,indent=2))
            print('PASS encrypted coherent CVAT archive + authenticated round-trip; same VPS only, database restore/disaster recovery UNVERIFIED')
    finally:
        # Resume only the services that were running before this explicit maintenance operation.
        run(compose+['start']+running)


if __name__=='__main__':
    try:main()
    except Exception as error:
        print('CVAT backup stopped: '+type(error).__name__+'; credentials omitted, inspect service state before proceeding')
        raise SystemExit(1) from None
