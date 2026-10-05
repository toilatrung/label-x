---
id: ai-overview
title: Artificial Intelligence
type: reference
domain: ai
module: repository
tags: [ai, models, agents]
priority: 3
---
# Artificial Intelligence

Thành phần AI và phép đo của LabelX (module Quality Control, phạm vi M13). AI trong MVP chỉ **sinh nghi vấn và xếp hạng**; con người quyết định (R-02).

## Phạm vi MVP

| Thành phần | Trạng thái MVP | Nguồn |
|---|---|---|
| Detector baseline (engine Mô hình độc lập) | Bật; một model, freeze artifact/checksum/mapping 10 lớp BDD100K | R B-07; SRS FR-ENG-05 |
| Matching dự đoán–annotation | Bước của Mô hình độc lập; association, không phải accuracy | R B-21 |
| Điểm rủi ro frame `s(f)` | Bật; có version, hiệu chỉnh trên tập hiệu chỉnh | SRS FR-RNK |
| Metric engine | Chỉ tính trên reference đã khoá; reference chưa có ⇒ Not checked | R B-05, B-20 |
| VLM | Đề xuất không bật trong pilot (TBD-08); nếu bật theo B-08 | R B-08; SRS FR-ENG-10 |
| Classifier thứ hai, Guideline RAG, temporal, Diff | Ngoài phạm vi MVP | R B-07, B-09, B-13, B-16 |

## Nội dung

| Tài liệu | Nội dung |
|---|---|
| [detector.md](detector.md) | Detector baseline: artifact/checksum, mapping 10 lớp, giao diện suy luận, sinh candidate E1/E2, không phải Ground Truth, chống leakage AS-03 |
| [risk-scoring.md](risk-scoring.md) | Mô hình `q_i`, `n_i`, `h(f)`, `s(f)`; `score_v0`; hiệu chỉnh ngoài fold và ablation (FR-RNK-10/11) |
| [evaluation.md](evaluation.md) | Reference, Recall@20% (KPI-1), effort và non-inferiority (KPI-2, G-1), Metric engine (B-05), guardrail, pre-registration |
| [vlm.md](vlm.md) | B-08 và đề xuất không bật trong pilot (TBD-08); 400 candidate, 3 lần thử, hết hạn mức không pass/reject |
| [safety-and-data.md](safety-and-data.md) | Con người quyết định, không AI tự xác nhận, dữ liệu không gửi ra ngoài, tách tập, provenance, lưu giữ |

Liên quan: [Domain Model](../03-domain/index.md), [Testing](../09-testing/index.md).
