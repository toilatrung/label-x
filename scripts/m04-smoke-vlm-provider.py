#!/usr/bin/env python3
"""Smoke tối thiểu của VLM provider (M04A-05): client + runner thật, ảnh TỔNG HỢP, 1 lời gọi.

Không qua DB/orchestration. Key CHỈ đọc từ biến môi trường (VLM_API_KEY cho cổng
api.shopaikey.com; DASHSCOPE_API_KEY cho DashScope) và không bao giờ được in hay ghi.

Chạy lại (tốn đúng một lời gọi provider thật):
    VLM_API_KEY="$(cat <file-key-ngoai-repo>)" \\
        python scripts/m04-smoke-vlm-provider.py [--out PATH]

Kết quả in ra dạng JSON một dòng; request_id được rút gọn (giữ 8 ký tự cuối). Với --out, cùng nội
dung được ghi vào PATH kèm sha256 của file ở dòng cuối stderr.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "src" / "backend"
sys.path.insert(0, str(BACKEND))

from PIL import Image, ImageDraw  # noqa: E402

from vlm.client import DashScopeClient  # noqa: E402
from vlm.config import parse_vlm_config  # noqa: E402
from vlm.contract import CandidateContext, CropInput, TaxonomyLabel, VlmRequest  # noqa: E402
from vlm.runner import CounterBudget, run_vlm_unit  # noqa: E402


def synthetic_png() -> bytes:
    image = Image.new("RGB", (224, 224), (200, 200, 200))
    draw = ImageDraw.Draw(image)
    draw.rectangle([40, 90, 184, 150], fill=(200, 30, 30))  # thân xe tổng hợp
    draw.ellipse([55, 135, 85, 165], fill=(20, 20, 20))
    draw.ellipse([140, 135, 170, 165], fill=(20, 20, 20))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def shorten(request_id: str | None) -> str | None:
    return None if not request_id else "…" + request_id[-8:]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="", help="ghi kết quả JSON vào file này")
    args = parser.parse_args()
    config = parse_vlm_config(
        {
            "provider": "openai_compatible",
            "model": "qwen3-vl-plus",
            "base_url": "https://api.shopaikey.com/v1",
            "prompt_version": "vlm-prompt-v0",
            "timeout_seconds": 60,
            "max_attempts": 1,
            "budget": {"max_calls": 1},
        }
    )
    request = VlmRequest(
        crop=CropInput(synthetic_png(), "image/png"),
        taxonomy=(
            TaxonomyLabel("1", "car"),
            TaxonomyLabel("2", "bus"),
            TaxonomyLabel("3", "person"),
        ),
        context=CandidateContext("smoke-synthetic", "none"),
        config=config,
    )
    budget = CounterBudget(1)
    result = run_vlm_unit(request, DashScopeClient(), budget)
    line = json.dumps(
        {
            "status": result.status.value,
            "label": result.label,
            "reason_code": result.reason_code.value if result.reason_code else None,
            "attempts": result.attempts,
            "budget_used": budget.used,
            "provider": result.provider,
            "provider_host": result.provider_host,
            "model": result.model,
            "response_model": result.response_model,
            "request_id": shorten(result.request_id),
            "prompt_version": result.prompt_version,
            "crop_sha256": result.crop_sha256,
            "rationale": (result.rationale or "")[:120],
        },
        ensure_ascii=False,
    )
    print(line)
    if args.out:
        data = (line + "\n").encode()
        Path(args.out).write_bytes(data)
        print(f"sha256({args.out}) = {hashlib.sha256(data).hexdigest()}", file=sys.stderr)
    return 0 if result.status.value in ("checked", "uncertain") else 1


if __name__ == "__main__":
    raise SystemExit(main())
