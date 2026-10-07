FROM pytorch/pytorch:1.12.1-cuda11.3-cudnn8-runtime

ARG MMCV_VERSION=1.7.1
ARG MMDET_VERSION=2.28.2

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install --yes --no-install-recommends ca-certificates curl libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

ENV \
    PIP_NO_CACHE_DIR=1 \
    PIP_DEFAULT_TIMEOUT=300 \
    PIP_RETRIES=10

RUN python -m pip install --upgrade "pip<25" \
    && python -m pip install \
       "numpy>=1.21,<1.24" \
       "Pillow>=9,<11" \
       "opencv-python-headless>=4.5,<4.9" \
       addict packaging "yapf<0.40.2" \
    && curl --fail --location --continue-at - \
       --retry 10 --retry-delay 2 --connect-timeout 30 --max-time 1800 \
       --output "/tmp/mmcv_full-${MMCV_VERSION}-cp37-cp37m-manylinux1_x86_64.whl" \
       "https://download.openmmlab.com/mmcv/dist/cu113/torch1.12.0/mmcv_full-${MMCV_VERSION}-cp37-cp37m-manylinux1_x86_64.whl" \
    && python -m pip install --no-deps "/tmp/mmcv_full-${MMCV_VERSION}-cp37-cp37m-manylinux1_x86_64.whl" \
    && rm "/tmp/mmcv_full-${MMCV_VERSION}-cp37-cp37m-manylinux1_x86_64.whl" \
    && python -m pip install "mmdet==${MMDET_VERSION}"

WORKDIR /opt/labelx/detector-worker
COPY src/detector_worker/ ./
RUN python -m pip install . \
    && useradd --create-home --uid 10001 detector \
    && mkdir -p /models /input /output \
    && chown -R detector:detector /models /input /output

USER detector
ENTRYPOINT ["labelx-detector"]
CMD ["--help"]
