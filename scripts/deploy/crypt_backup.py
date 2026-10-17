"""Stream AES-256-GCM backup encryption/decryption; key and AAD arrive only on stdin."""
import argparse
import json
import os
from pathlib import Path
import sys
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--decrypt',action='store_true')
parser.add_argument('--input',type=Path,required=True)
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
config=json.load(sys.stdin)
key=bytes.fromhex(config['key']);aad=config['aad'].encode()
if len(key)!=32: raise ValueError('AES-256 key required')
fd=os.open(args.output,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
try:
    with args.input.open('rb') as source, os.fdopen(fd,'wb') as target:
        if args.decrypt:
            nonce=source.read(12);source.seek(-16,2);tag=source.read(16);remaining=source.tell()-28;source.seek(12)
            cipher=Cipher(algorithms.AES(key),modes.GCM(nonce,tag)).decryptor()
        else:
            nonce=os.urandom(12);target.write(nonce);remaining=args.input.stat().st_size
            cipher=Cipher(algorithms.AES(key),modes.GCM(nonce)).encryptor()
        cipher.authenticate_additional_data(aad)
        while remaining:
            data=source.read(min(remaining,8*1024*1024))
            if not data:raise ValueError('Truncated archive')
            target.write(cipher.update(data));remaining-=len(data)
        target.write(cipher.finalize())
        if not args.decrypt:target.write(cipher.tag)
except BaseException:
    args.output.unlink(missing_ok=True)
    raise
print('PASS authenticated AES-256-GCM archive operation; key omitted')
