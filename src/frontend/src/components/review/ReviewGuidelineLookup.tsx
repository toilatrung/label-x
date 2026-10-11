'use client';

import React, { useEffect, useState, useRef } from 'react';
import { apiClient } from '@/lib/api/client';
import type { components } from '@/lib/api/contract';

type GuidelineRule = components['schemas']['GuidelineRule'];

export interface ReviewGuidelineLookupProps {
  ruleId?: string | null;
  guidelineVersion?: string | null;
}

export function ReviewGuidelineLookup({
  ruleId,
  guidelineVersion,
}: ReviewGuidelineLookupProps) {
  const trimmedRuleId = ruleId?.trim();
  const trimmedVersion = guidelineVersion?.trim();
  const lookupKey = `${trimmedRuleId || ''}:${trimmedVersion || ''}`;

  const [rule, setRule] = useState<GuidelineRule | null>(null);
  const [loading, setLoading] = useState<boolean>(Boolean(trimmedRuleId && trimmedVersion));
  const [error, setError] = useState<string | null>(null);
  const [prevLookupKey, setPrevLookupKey] = useState<string>(lookupKey);
  const reqSeq = useRef<number>(0);

  // Reset state during render when rule or version props change
  if (lookupKey !== prevLookupKey) {
    setPrevLookupKey(lookupKey);
    setRule(null);
    setError(null);
    setLoading(Boolean(trimmedRuleId && trimmedVersion));
  }

  useEffect(() => {
    // Invalidate any in-flight lookup whenever rule or version changes
    reqSeq.current += 1;
    const currentReqId = reqSeq.current;
    const abortCtrl = new AbortController();

    if (!trimmedRuleId || !trimmedVersion) {
      return () => {
        abortCtrl.abort();
      };
    }

    apiClient
      .GET('/api/guidelines/rules/{rule_id}/', {
        params: {
          path: { rule_id: trimmedRuleId },
          query: { version: trimmedVersion },
        },
        signal: abortCtrl.signal,
      })
      .then(({ data, error: apiErr }) => {
        // Discard stale out-of-order response
        if (currentReqId !== reqSeq.current) return;

        if (apiErr || !data) {
          // Clear rule so no stale rule remains visible after failure
          setRule(null);
          setError(`Không tìm thấy quy tắc ${trimmedRuleId} cho guideline version "${trimmedVersion}".`);
          return;
        }

        // Verify returned rule_id matches requested rule_id
        if (data.rule_id !== trimmedRuleId) {
          setRule(null);
          setError(`Mã quy tắc trả về (${data.rule_id}) không khớp với quy tắc yêu cầu (${trimmedRuleId}).`);
          return;
        }

        // Verify returned version matches the requested pinned snapshot version
        const returnedVersion = data.guideline_version ?? (data as unknown as { version?: string }).version;
        if (returnedVersion !== trimmedVersion) {
          setRule(null);
          setError(`Phiên bản trả về (${returnedVersion}) không khớp với phiên bản snapshot yêu cầu (${trimmedVersion}).`);
          return;
        }

        // Exact GuidelineRule schema fields: rule_id, section, content, guideline_version
        const normalizedRule: GuidelineRule = {
          rule_id: data.rule_id,
          guideline_version: returnedVersion,
          section: data.section ?? (data as unknown as { title?: string }).title ?? '',
          content: data.content ?? (data as unknown as { title?: string }).title ?? '',
        };
        setRule(normalizedRule);
      })
      .catch((err: unknown) => {
        if (abortCtrl.signal.aborted || currentReqId !== reqSeq.current) return;
        setRule(null);
        setError(`Lỗi khi tải hướng dẫn kiểm định: ${err instanceof Error ? err.message : 'Lỗi kết nối'}`);
      })
      .finally(() => {
        if (currentReqId === reqSeq.current) {
          setLoading(false);
        }
      });

    return () => {
      reqSeq.current += 1;
      abortCtrl.abort();
    };
  }, [trimmedRuleId, trimmedVersion]);

  const missingSnapshotVersion = Boolean(trimmedRuleId && !trimmedVersion);
  const activeError = missingSnapshotVersion
    ? 'Snapshot không có guideline_version cố định. Không tải rule để tránh sai lệch phiên bản (fail-closed).'
    : error;

  return (
    <div className="lx-stack" style={{ gap: '10px' }}>
      {/* Guidelines Accordion */}
      <details open={Boolean(ruleId)}>
        <summary style={{ cursor: 'pointer', fontSize: '13px', fontWeight: 600 }}>
          Hướng dẫn liên quan {ruleId ? `· Quy tắc ${ruleId}` : ''}
        </summary>
        <div style={{ marginTop: '8px' }}>
          {loading && <p className="lx-muted" style={{ fontSize: '12px' }}>Đang tải hướng dẫn...</p>}
          {activeError && (
            <div className="lx-callout lx-callout--warning" role="alert" style={{ padding: '6px 10px', fontSize: '12px' }}>
              <span className="lx-callout__text">{activeError}</span>
            </div>
          )}
          {rule && (
            <div>
              <p className="lx-muted" style={{ margin: '4px 0 6px', fontSize: '13px' }}>
                {rule.content}
              </p>
              <span className="lx-subtle" style={{ fontSize: '11px' }}>
                Guideline {rule.guideline_version.startsWith('v') ? rule.guideline_version : `v${rule.guideline_version}`} · Mục {rule.section} · Quy tắc {rule.rule_id}
              </span>
            </div>
          )}
          {!ruleId && !loading && (
            <p className="lx-subtle" style={{ fontSize: '12px', margin: '4px 0' }}>
              Issue không gắn với mã quy tắc guideline cụ thể.
            </p>
          )}
        </div>
      </details>

      {/* Case Lookup Accordion (Approved API check & explicit limitation) */}
      <details>
        <summary style={{ cursor: 'pointer', fontSize: '13px', fontWeight: 600 }}>
          Case tương tự đã phân xử
        </summary>
        <div style={{ marginTop: '8px' }}>
          <p className="lx-muted" style={{ margin: '4px 0', fontSize: '12px' }}>
            Chức năng tra cứu Case tương tự hiện chưa khả dụng (API chưa có endpoint tìm kiếm Case).
          </p>
          <span className="lx-subtle" style={{ fontSize: '11px' }}>
            Hệ thống không giả lập dữ liệu Case khi thiếu API đã được duyệt (DEC-T037).
          </span>
        </div>
      </details>
    </div>
  );
}
