from django.db import migrations

# BEFORE TRUNCATE (mức statement) chặn cả chủ bảng/superuser và TRUNCATE ... CASCADE từ bảng cha
# (PostgreSQL chạy trigger TRUNCATE trên mọi bảng bị cascade). Cờ `labelx.allow_evidence_truncate`
# chỉ để môi trường test (Django flush) và vận hành có chủ đích đặt 'on' cho phiên làm việc; mặc
# định không đặt nghĩa là CHẶN. REVOKE ... FROM PUBLIC trước đây là no-op (bảng không cấp quyền cho
# PUBLIC), nên được thay bằng trigger này.
BLOCK_SQL = """
CREATE OR REPLACE FUNCTION orchestration_reject_vlmevidence_truncate()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF coalesce(current_setting('labelx.allow_evidence_truncate', true), '') = 'on' THEN
        RETURN NULL;
    END IF;
    RAISE EXCEPTION 'orchestration_vlmevidence is append-only; TRUNCATE is forbidden'
        USING ERRCODE = '42501';
END;
$$;

CREATE TRIGGER orchestration_vlmevidence_no_truncate
BEFORE TRUNCATE ON orchestration_vlmevidence
FOR EACH STATEMENT EXECUTE FUNCTION orchestration_reject_vlmevidence_truncate();
"""

UNBLOCK_SQL = """
DROP TRIGGER IF EXISTS orchestration_vlmevidence_no_truncate ON orchestration_vlmevidence;
DROP FUNCTION IF EXISTS orchestration_reject_vlmevidence_truncate();
"""


class Migration(migrations.Migration):
    dependencies = [("orchestration", "0005_vlm_evidence")]

    operations = [migrations.RunSQL(BLOCK_SQL, UNBLOCK_SQL)]
