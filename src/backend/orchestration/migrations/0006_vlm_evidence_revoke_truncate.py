from django.db import migrations

REVOKE_SQL = "REVOKE TRUNCATE ON TABLE orchestration_vlmevidence FROM PUBLIC;"
# Giữ nguyên: chủ bảng/superuser vẫn TRUNCATE được; runtime role phải không phải owner và được
# cấp quyền bằng `manage.py provision_runtime_db_role` (REVOKE UPDATE/DELETE/TRUNCATE trên bảng này).
GRANT_SQL = "GRANT TRUNCATE ON TABLE orchestration_vlmevidence TO PUBLIC;"


class Migration(migrations.Migration):
    dependencies = [("orchestration", "0005_vlm_evidence")]

    operations = [migrations.RunSQL(REVOKE_SQL, GRANT_SQL)]
