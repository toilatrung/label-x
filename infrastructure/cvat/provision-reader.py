"""Run interactively inside CVAT. Create an unusable-password reader and a read-only expiring PAT."""
import json
import os
from pathlib import Path
from datetime import timedelta

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cvat.settings.labelx')
import django
django.setup()
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import transaction
from django.utils import timezone
from cvat.apps.access_tokens.models import AccessToken

username = input('Dedicated service username [labelx_reader]: ').strip() or 'labelx_reader'
path = Path('/home/django/keys/labelx-reader-token.json')
if path.exists():
    raise SystemExit('Existing token file preserved. Check expiry/revocation before using; rotate deliberately.')
with transaction.atomic():
    user, created = get_user_model().objects.get_or_create(username=username)
    if user.is_staff or user.is_superuser or user.groups.filter(name='admin').exists():
        raise SystemExit('Refusing a privileged service account')
    if created:
        user.set_unusable_password()
        user.save(update_fields=['password'])
        user.groups.add(Group.objects.get(name='user'))
    _, raw = AccessToken.objects.create_key(name='LabelX read-only', owner=user,
        read_only=True, expiry_date=timezone.now()+timedelta(days=90))
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as file:
        json.dump({'username':username,'read_only':True,'base_url':'https://cvat.williamtrinh.online','token':raw},file)
print('Read-only PAT saved to keys/labelx-reader-token.json, mode 0600; never printed.')
print('Grant this ordinary user access only to the intended CVAT jobs/organization. Do not grant admin role or send its password to LabelX.')
