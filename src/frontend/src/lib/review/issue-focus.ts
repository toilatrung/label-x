import type { components } from '@/lib/api/contract';
import type { SnapshotAnnotation } from '@/components/review/ReviewCanvas';
import { reviewBBox } from './workspace-api';

type Issue = components['schemas']['Issue'];

/** Match typed snapshot IDs and legacy engine refs without confusing shapes with tracks. */
export function annotationMatchesObject(annotation: SnapshotAnnotation, object: Issue['anchor']['objects'][number]) {
  if (!annotation.source || !object) return false;
  const { kind, id } = annotation.source;
  const raw = String(object.id);
  const typed = /^(shape|track):(.+)$/.exec(raw);
  const namespace = String(object.namespace);
  if (typed) return ['cvat_shape', 'cvat_track', kind].includes(namespace)
    && typed[1] === kind && typed[2] === String(id);
  return [kind, `cvat_${kind}`].includes(namespace) && raw === String(id);
}

export function resolveIssueFocus(issue: Issue | null, annotations: SnapshotAnnotation[] = [], frame?: { width?: number; height?: number }) {
  const objects = Array.isArray(issue?.anchor?.objects) ? issue.anchor.objects : [];
  const annotationObjects = objects.filter(object => ['shape', 'track', 'cvat_shape', 'cvat_track'].includes(String(object?.namespace)));
  const matched = annotations.filter(annotation => objects.some(object => annotationMatchesObject(annotation, object)));
  const validGeometry = (annotation: SnapshotAnnotation) => {
    const bbox = reviewBBox(annotation.bbox);
    return bbox && !annotation.outside && Number.isFinite(annotation.rotation ?? 0)
      && (!frame?.width || !frame?.height || (bbox.x2 > 0 && bbox.y2 > 0 && bbox.x1 < frame.width && bbox.y1 < frame.height));
  };
  const regions = matched.flatMap(annotation => {
    const bbox = reviewBBox(annotation.bbox);
    return bbox && validGeometry(annotation) ? [{ bbox, rotation: annotation.rotation ?? 0, id: annotation.id }] : [];
  });
  const missing = annotationObjects.filter(object => !matched.some(annotation => annotationMatchesObject(annotation, object)));
  const reasons: string[] = [];
  if (!issue?.anchor) reasons.push('Issue thiếu anchor; không xác định được vùng cần kiểm tra.');
  else {
    if (missing.length) reasons.push(`Không ánh xạ được anchor trong Snapshot của frame: ${missing.map(object => `${object.namespace}:${object.id}`).join(', ')}.`);
    if (matched.some(annotation => !validGeometry(annotation))) reasons.push('Annotation được neo nằm ngoài frame hoặc có tọa độ không hợp lệ.');
    if (issue.anchor.kind === 'annotation_cluster' && (annotationObjects.length < 2 || (!missing.length && matched.length < 2))) reasons.push('Anchor annotation_cluster cần ít nhất hai annotation khác nhau.');
    if (!annotationObjects.length && !reviewBBox(issue.anchor.bbox)) reasons.push('Anchor không có annotation hoặc vùng tọa độ hợp lệ.');
  }
  // Explicit region anchors remain usable; never invent a box for an unresolved annotation.
  if (!annotationObjects.length && reviewBBox(issue?.anchor?.bbox)) regions.push({ bbox: reviewBBox(issue!.anchor.bbox)!, rotation: 0, id: 'anchor-region' });
  return { annotations: matched, regions, reasons };
}
