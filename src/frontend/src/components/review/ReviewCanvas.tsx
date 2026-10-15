'use client';

import React, { useState, useRef, useCallback, useEffect } from 'react';
import type { components } from '@/lib/api/contract';
import { reviewBBox, type WorkspacePrediction } from '@/lib/review/workspace-api';

type FrameSummary = components['schemas']['FrameSummary'];
type Issue = components['schemas']['Issue'];
type BBox = components['schemas']['BBox'];
type ObjectRef = components['schemas']['ObjectRef'];

export interface SnapshotAnnotation {
  id: string;
  label?: string | null;
  label_id?: number;
  color?: string | null;
  bbox: BBox | null;
  rotation?: number;
  occluded?: boolean;
  outside?: boolean;
  z_order?: number;
  source?: { kind: string; id: number };
}

export interface ReviewCanvasProps {
  frame: FrameSummary;
  issues: Issue[];
  snapshotAnnotations?: SnapshotAnnotation[];
  predictions?: WorkspacePrediction[];
  selectedIssueId: number | null;
  onSelectIssue: (issueId: number) => void;
  reviewMode: 'issue' | 'frame';
  showAnnotations: boolean;
  showPredictions: boolean;
  onSelectObjectForManualIssue?: (objectRef: ObjectRef, bbox?: BBox) => void;
  onCreateRegionManualIssue?: (bbox: BBox) => void;
  zoom: number;
  pan: { x: number; y: number };
  onZoomChange: (zoom: number) => void;
  onPanChange: (pan: { x: number; y: number }) => void;
}

/**
 * Calculates inverse transformation from mouse viewport coordinates to SVG viewBox units
 * taking into account preserveAspectRatio="xMidYMid meet" letterbox/pillarbox offsets,
 * pan, and zoom.
 */
export function calculateLetterboxTransform(
  rect: { width: number; height: number; left: number; top: number },
  vbWidth: number,
  vbHeight: number,
  clientX: number,
  clientY: number,
  zoom: number,
  pan: { x: number; y: number }
): { x: number; y: number } {
  if (rect.width <= 0 || rect.height <= 0 || vbWidth <= 0 || vbHeight <= 0) {
    return { x: 0, y: 0 };
  }

  const aspectVb = vbWidth / vbHeight;
  const aspectRect = rect.width / rect.height;
  let scale = 1;
  let offsetX = 0;
  let offsetY = 0;

  if (aspectRect > aspectVb) {
    // Letterbox on left and right (pillarbox)
    scale = rect.height / vbHeight;
    offsetX = (rect.width - vbWidth * scale) / 2;
  } else {
    // Letterbox on top and bottom
    scale = rect.width / vbWidth;
    offsetY = (rect.height - vbHeight * scale) / 2;
  }

  // Position relative to scaled viewBox origin
  const vbX = (clientX - rect.left - offsetX) / scale;
  const vbY = (clientY - rect.top - offsetY) / scale;

  // Invert pan and zoom (pan is expressed in viewBox units)
  const z = zoom > 0 ? zoom : 1;
  const x = (vbX - pan.x) / z;
  const y = (vbY - pan.y) / z;

  return {
    x: Math.max(0, Math.min(vbWidth, Math.round(x))),
    y: Math.max(0, Math.min(vbHeight, Math.round(y))),
  };
}

export function getSvgScale(rect: DOMRect, vbWidth: number, vbHeight: number): number {
  if (rect.width <= 0 || rect.height <= 0 || vbWidth <= 0 || vbHeight <= 0) return 1;
  const aspectVb = vbWidth / vbHeight;
  const aspectRect = rect.width / rect.height;
  return aspectRect > aspectVb ? rect.height / vbHeight : rect.width / vbWidth;
}

export function ReviewCanvas({
  frame,
  issues,
  snapshotAnnotations,
  predictions,
  selectedIssueId,
  onSelectIssue,
  reviewMode,
  showAnnotations,
  showPredictions,
  onSelectObjectForManualIssue,
  onCreateRegionManualIssue,
  zoom,
  pan,
  onZoomChange,
  onPanChange,
}: ReviewCanvasProps) {
  const svgRef = useRef<SVGSVGElement | null>(null);
  const [isPanning, setIsPanning] = useState(false);
  const panAnchorRef = useRef<{ clientX: number; clientY: number; panX: number; panY: number } | null>(null);
  const [isDrawingRegion, setIsDrawingRegion] = useState(false);
  const [drawStart, setDrawStart] = useState<{ x: number; y: number } | null>(null);
  const [drawCurrent, setDrawCurrent] = useState<{ x: number; y: number } | null>(null);

  // Trustworthy dimensions check
  const hasTrustworthyDimensions =
    Number.isFinite(frame.width) &&
    Number.isFinite(frame.height) &&
    (frame.width ?? 0) > 0 &&
    (frame.height ?? 0) > 0;

  const imgWidth = hasTrustworthyDimensions ? (frame.width as number) : 960;
  const imgHeight = hasTrustworthyDimensions ? (frame.height as number) : 540;

  // Media loading & error state
  const [mediaError, setMediaError] = useState(false);
  const [retryNonce, setRetryNonce] = useState(0);

  const screenToSvg = useCallback(
    (clientX: number, clientY: number): { x: number; y: number } | null => {
      if (!svgRef.current) return null;
      const rect = svgRef.current.getBoundingClientRect();
      return calculateLetterboxTransform(rect, imgWidth, imgHeight, clientX, clientY, zoom, pan);
    },
    [imgWidth, imgHeight, zoom, pan]
  );

  const handleMouseDown = (e: React.MouseEvent<SVGSVGElement>) => {
    if (e.button === 1 || e.shiftKey) {
      setIsPanning(true);
      panAnchorRef.current = {
        clientX: e.clientX,
        clientY: e.clientY,
        panX: pan.x,
        panY: pan.y,
      };
      e.preventDefault();
      return;
    }

    if (reviewMode === 'frame' && e.button === 0 && !e.altKey && hasTrustworthyDimensions && !mediaError) {
      const pt = screenToSvg(e.clientX, e.clientY);
      if (pt) {
        setIsDrawingRegion(true);
        setDrawStart(pt);
        setDrawCurrent(pt);
      }
    }
  };

  // Global mousemove and mouseup listeners to prevent stuck states and convert pan scale
  useEffect(() => {
    if (!isPanning && !isDrawingRegion) return;

    const handleGlobalMouseMove = (e: MouseEvent) => {
      if (isPanning && panAnchorRef.current && svgRef.current) {
        const rect = svgRef.current.getBoundingClientRect();
        const scale = getSvgScale(rect, imgWidth, imgHeight);
        const deltaClientX = e.clientX - panAnchorRef.current.clientX;
        const deltaClientY = e.clientY - panAnchorRef.current.clientY;
        const deltaVbX = deltaClientX / (scale > 0 ? scale : 1);
        const deltaVbY = deltaClientY / (scale > 0 ? scale : 1);
        onPanChange({
          x: Math.round(panAnchorRef.current.panX + deltaVbX),
          y: Math.round(panAnchorRef.current.panY + deltaVbY),
        });
        return;
      }

      if (isDrawingRegion && drawStart) {
        const pt = screenToSvg(e.clientX, e.clientY);
        if (pt) {
          setDrawCurrent(pt);
        }
      }
    };

    const handleGlobalMouseUp = (e: MouseEvent) => {
      if (isPanning) {
        setIsPanning(false);
        panAnchorRef.current = null;
      }

      if (isDrawingRegion) {
        setIsDrawingRegion(false);

        // Verify if released inside SVG viewport
        const svgEl = svgRef.current;
        let isInsideSvg = false;
        if (svgEl) {
          const rect = svgEl.getBoundingClientRect();
          isInsideSvg =
            e.clientX >= rect.left &&
            e.clientX <= rect.right &&
            e.clientY >= rect.top &&
            e.clientY <= rect.bottom;
        }

        if (isInsideSvg && drawStart && drawCurrent && hasTrustworthyDimensions && onCreateRegionManualIssue) {
          const x1 = Math.min(drawStart.x, drawCurrent.x);
          const y1 = Math.min(drawStart.y, drawCurrent.y);
          const x2 = Math.max(drawStart.x, drawCurrent.x);
          const y2 = Math.max(drawStart.y, drawCurrent.y);

          if (x2 - x1 >= 5 && y2 - y1 >= 5) {
            const clampedX1 = Math.max(0, Math.min(imgWidth, x1));
            const clampedY1 = Math.max(0, Math.min(imgHeight, y1));
            const clampedX2 = Math.max(0, Math.min(imgWidth, x2));
            const clampedY2 = Math.max(0, Math.min(imgHeight, y2));
            if (clampedX2 > clampedX1 && clampedY2 > clampedY1) {
              onCreateRegionManualIssue({ x1: clampedX1, y1: clampedY1, x2: clampedX2, y2: clampedY2 });
            }
          }
        }

        // End drawing state
        setDrawStart(null);
        setDrawCurrent(null);
      }
    };

    window.addEventListener('mousemove', handleGlobalMouseMove);
    window.addEventListener('mouseup', handleGlobalMouseUp);

    return () => {
      window.removeEventListener('mousemove', handleGlobalMouseMove);
      window.removeEventListener('mouseup', handleGlobalMouseUp);
    };
  }, [
    isPanning,
    isDrawingRegion,
    drawStart,
    drawCurrent,
    imgWidth,
    imgHeight,
    hasTrustworthyDimensions,
    onPanChange,
    screenToSvg,
    onCreateRegionManualIssue,
  ]);

  const handleWheel = (e: React.WheelEvent<SVGSVGElement>) => {
    e.preventDefault();
    const zoomFactor = e.deltaY < 0 ? 1.15 : 0.85;
    const newZoom = Math.min(5, Math.max(0.5, zoom * zoomFactor));
    onZoomChange(Number(newZoom.toFixed(2)));
  };

  const activeIssue = issues.find((i) => i.id === selectedIssueId) ?? issues[0] ?? null;

  return (
    <div
      style={{
        width: '100%',
        height: '100%',
        position: 'relative',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: '#1f242c',
        overflow: 'hidden',
        userSelect: 'none',
      }}
    >
      <svg
        ref={svgRef}
        viewBox={`0 0 ${imgWidth} ${imgHeight}`}
        preserveAspectRatio="xMidYMid meet"
        role="img"
        aria-label="Khung hình annotation và prediction"
        style={{
          width: '100%',
          height: '100%',
          maxHeight: '560px',
          display: 'block',
          cursor: isPanning ? 'grabbing' : reviewMode === 'frame' ? 'crosshair' : 'default',
        }}
        onMouseDown={handleMouseDown}
        onWheel={handleWheel}
      >
        <defs>
          <clipPath id="frameBounds">
            <rect x="0" y="0" width={imgWidth} height={imgHeight} />
          </clipPath>
        </defs>

        <g
          clipPath="url(#frameBounds)"
          transform={`translate(${pan.x}, ${pan.y}) scale(${zoom})`}
          style={{ transformOrigin: '0 0' }}
        >
          {/* Real media layer: No fake scenery rendered */}
          {frame.image_url && !mediaError ? (
            <image
              key={`frame-img-${retryNonce}`}
              href={frame.image_url}
              x="0"
              y="0"
              width={imgWidth}
              height={imgHeight}
              preserveAspectRatio="xMidYMid meet"
              onError={() => setMediaError(true)}
            />
          ) : mediaError ? (
            <g>
              <rect width={imgWidth} height={imgHeight} fill="#252a32" />
              <text
                x={imgWidth / 2}
                y={imgHeight / 2 - 10}
                textAnchor="middle"
                fill="#f87171"
                fontFamily="Inter, sans-serif"
                fontSize="14"
                fontWeight="600"
              >
                Lỗi tải ảnh khung hình từ máy chủ
              </text>
              <text
                x={imgWidth / 2}
                y={imgHeight / 2 + 16}
                textAnchor="middle"
                fill="#94a3b8"
                fontFamily="Inter, sans-serif"
                fontSize="12"
              >
                Nhấp nút bên dưới để thử tải lại ảnh
              </text>
            </g>
          ) : (
            <g>
              <rect width={imgWidth} height={imgHeight} fill="#252a32" />
              <text
                x={imgWidth / 2}
                y={imgHeight / 2}
                textAnchor="middle"
                fill="#8892a0"
                fontFamily="Inter, sans-serif"
                fontSize="14"
              >
                Nguồn ảnh hiện không khả dụng
              </text>
            </g>
          )}

          {/* Full Snapshot Annotations (if approved source provided) */}
          {showAnnotations && snapshotAnnotations && (
            <g id="snapshot-annotations-layer">
              {[...snapshotAnnotations].sort((a, b) => (a.z_order ?? 0) - (b.z_order ?? 0)).map(ann => {
                const bbox = reviewBBox(ann.bbox);
                if (ann.outside || !bbox) return null;
                const color = ann.color && /^#[0-9a-f]{6}$/i.test(ann.color) ? ann.color : '#c7ccd4';
                const width = bbox.x2 - bbox.x1;
                const height = bbox.y2 - bbox.y1;
                const label = ann.label || `Nhãn #${ann.label_id ?? '?'}`;
                return <g key={`snap-ann-${ann.id}`} data-annotation-id={ann.id}
                  onMouseDown={e => e.stopPropagation()}
                  onClick={e => {
                    e.stopPropagation();
                    const linked = issues.find(i => i.anchor.objects.some(o =>
                      ['cvat_shape', ann.source?.kind].includes(String(o.namespace)) && o.id === String(ann.source?.id)));
                    if (linked) onSelectIssue(linked.id);
                    if (reviewMode === 'frame' && ann.source?.kind === 'shape') {
                      onSelectObjectForManualIssue?.({ namespace: 'cvat_shape', id: String(ann.source.id) }, bbox);
                    }
                  }}>
                  <rect x={bbox.x1} y={bbox.y1} width={width} height={height}
                    transform={`rotate(${ann.rotation ?? 0} ${(bbox.x1 + bbox.x2) / 2} ${(bbox.y1 + bbox.y2) / 2})`}
                    fill="none" stroke={color} strokeWidth="2" vectorEffect="non-scaling-stroke"
                    strokeDasharray={ann.occluded ? '6 4' : undefined} />
                  <text x={bbox.x1} y={Math.max(14, bbox.y1 - 5)} fill={color} fontSize="13">
                    {label} · {ann.source?.id ?? ann.id}
                  </text>
                </g>;
              })}
            </g>
          )}

          {/* Issue Anchors Layer (solid yellow/white borders) */}
          {showAnnotations && !snapshotAnnotations && (
            <g id="issue-anchors-layer">
              {issues.map((issue) => {
                const isSelected = activeIssue?.id === issue.id;
                const opacity = reviewMode === 'frame' || isSelected ? 1 : 0.3;
                const bbox = issue.anchor?.bbox;
                const obj = issue.anchor?.objects?.[0];
                const objLabel = obj ? `${obj.id}` : `Issue #${issue.id}`;

                if (!bbox) return null;

                const width = Math.max(1, bbox.x2 - bbox.x1);
                const height = Math.max(1, bbox.y2 - bbox.y1);
                const strokeColor = isSelected ? '#f2c14e' : '#c7ccd4';
                const strokeWidth = isSelected ? 3 : 2;

                return (
                  <g
                    key={`ann-${issue.id}`}
                    opacity={opacity}
                    style={{ cursor: 'pointer' }}
                    onClick={(e) => {
                      e.stopPropagation();
                      onSelectIssue(issue.id);
                      if (reviewMode === 'frame' && obj && onSelectObjectForManualIssue) {
                        if (obj.namespace === 'cvat_shape') {
                          onSelectObjectForManualIssue(obj, bbox);
                        }
                      }
                    }}
                  >
                    <rect
                      x={bbox.x1}
                      y={bbox.y1}
                      width={width}
                      height={height}
                      fill="none"
                      stroke={strokeColor}
                      strokeWidth={strokeWidth}
                    />
                    <g fontFamily="Inter, sans-serif" fontSize="13" fontWeight="600">
                      <rect
                        x={bbox.x1}
                        y={Math.max(0, bbox.y1 - 22)}
                        width={Math.min(width + 20, 160)}
                        height="20"
                        fill={strokeColor}
                      />
                      <text
                        x={bbox.x1 + 6}
                        y={Math.max(14, bbox.y1 - 7)}
                        fill="#1f2329"
                      >
                        {isSelected ? `${objLabel} · anchor` : objLabel}
                      </text>
                    </g>
                  </g>
                );
              })}
            </g>
          )}

          {/* Predictions Layer (dashed cyan borders) */}
          {showPredictions && predictions && (
            <g id="model-predictions-layer">
              {predictions.map(prediction => {
                const bbox = prediction.bbox;
                const isSecondModel = prediction.source.startsWith('Qwen');
                const color = isSecondModel ? '#c4a5ff' : '#5fd0c7';
                return <g key={prediction.id} data-prediction-source={prediction.source}
                  opacity={reviewMode === 'frame' || prediction.issueId === null || prediction.issueId === activeIssue?.id ? 1 : 0.3}
                  onClick={() => prediction.issueId !== null && onSelectIssue(prediction.issueId)}>
                  <rect x={bbox.x1} y={bbox.y1} width={bbox.x2 - bbox.x1} height={bbox.y2 - bbox.y1}
                    fill="none" stroke={color} strokeWidth="3" strokeDasharray={isSecondModel ? '4 4' : '10 6'} />
                  <text x={bbox.x1 + 4} y={Math.min(imgHeight - 4, bbox.y2 + (isSecondModel ? 32 : 16))}
                    fill={color} fontSize="13" fontWeight="600">
                    {prediction.source}: {prediction.label}{prediction.confidence !== undefined ? ` · ${prediction.confidence.toFixed(2)}` : ''}
                  </text>
                </g>;
              })}
            </g>
          )}
          {showPredictions && !predictions && (
            <g id="predictions-layer">
              {issues.map((issue) => {
                const isSelected = activeIssue?.id === issue.id;
                const opacity = reviewMode === 'frame' || isSelected ? 1 : 0.3;

                return issue.evidence?.map((ev, idx) => {
                  const pBBox = reviewBBox(ev.prediction_bbox);
                  if (!pBBox) return null;

                  const width = Math.max(1, pBBox.x2 - pBBox.x1);
                  const height = Math.max(1, pBBox.y2 - pBBox.y1);
                  const confStr =
                    ev.confidence !== null && ev.confidence !== undefined
                      ? ` · ${ev.confidence.toFixed(2)}`
                      : '';
                  const predLabel = `đề xuất: ${ev.prediction_class ?? 'object'}${confStr}`;

                  return (
                    <g key={`pred-${issue.id}-${idx}`} opacity={opacity}>
                      <rect
                        x={pBBox.x1}
                        y={pBBox.y1}
                        width={width}
                        height={height}
                        fill="none"
                        stroke="#5fd0c7"
                        strokeWidth="3"
                        strokeDasharray="10 6"
                      />
                      <g fontFamily="Inter, sans-serif" fontSize="13" fontWeight="600">
                        <rect
                          x={pBBox.x1}
                          y={pBBox.y2 + 2}
                          width={Math.min(width + 20, 190)}
                          height="20"
                          fill="#5fd0c7"
                        />
                        <text x={pBBox.x1 + 6} y={pBBox.y2 + 16} fill="#1f2329">
                          {predLabel}
                        </text>
                      </g>
                    </g>
                  );
                });
              })}
            </g>
          )}

          {/* Region drawing preview rectangle */}
          {isDrawingRegion && drawStart && drawCurrent && (
            <rect
              x={Math.min(drawStart.x, drawCurrent.x)}
              y={Math.min(drawStart.y, drawCurrent.y)}
              width={Math.abs(drawCurrent.x - drawStart.x)}
              height={Math.abs(drawCurrent.y - drawStart.y)}
              fill="rgba(95, 208, 199, 0.2)"
              stroke="#5fd0c7"
              strokeWidth="2"
              strokeDasharray="4 4"
            />
          )}
        </g>
      </svg>
      {mediaError && (
        <div
          style={{
            position: 'absolute',
            bottom: '16px',
            zIndex: 10,
          }}
        >
          <button
            type="button"
            className="lx-btn lx-btn--sm"
            onClick={() => {
              setMediaError(false);
              setRetryNonce((n) => n + 1);
            }}
          >
            Thử tải lại ảnh
          </button>
        </div>
      )}
      {!hasTrustworthyDimensions && (
        <div
          style={{
            position: 'absolute',
            top: '12px',
            left: '12px',
            background: 'rgba(0,0,0,0.7)',
            color: '#fbbf24',
            padding: '4px 8px',
            borderRadius: '4px',
            fontSize: '11px',
            zIndex: 10,
          }}
        >
          Chưa xác định kích thước khung hình (vẽ vùng tạo issue tạm khóa)
        </div>
      )}
    </div>
  );
}
