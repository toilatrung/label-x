#!/usr/bin/env python3
"""Copy a privately exported read-only CVAT PAT into the private bootstrap configuration."""
import argparse
import json
from pathlib import Path
import os


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--token-file',type=Path,required=True)
    parser.add_argument('--config',type=Path,required=True)
    args=parser.parse_args()
    for path in (args.token_file,args.config):
        if path.stat().st_mode & 0o077: raise RuntimeError('Private files must be mode 0600')
    token=json.loads(args.token_file.read_text())
    if token.get('read_only') is not True or token.get('base_url')!='https://cvat.williamtrinh.online' or not token.get('token'):
        raise RuntimeError('A genuine read-only CVAT token export is required')
    config=json.loads(args.config.read_text())
    config.update({'CVAT_BASE_URL':token['base_url'],'CVAT_SERVICE_TOKEN':token['token']})
    temporary=args.config.with_name(args.config.name+'.new')
    fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as file: json.dump(config,file,indent=2)
    temporary.replace(args.config)
    print('Private config updated. Bootstrap --update-dependencies preserves DB/Redis/Django/storage keys. No token printed.')


if __name__=='__main__': main()
