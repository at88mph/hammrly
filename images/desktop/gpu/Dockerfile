# GPU-enabled astronomy desktop. Build after desktop-astronomy:
#   docker build -f images/desktop/astronomy/Dockerfile -t hammrly/desktop-astronomy:local .
#   docker build -f images/desktop/gpu/Dockerfile -t hammrly/desktop-astronomy-gpu:local .
#
# Submit with workload.gpu_count > 0 so Hammrly schedules on GPU worker nodes.
# Override the parent image when publishing:
#   docker build -f images/desktop/gpu/Dockerfile \
#     --build-arg ASTRONOMY_IMAGE=registry.example/hammrly/desktop-astronomy:1.0 \
#     -t registry.example/hammrly/desktop-astronomy-gpu:1.0 .

ARG ASTRONOMY_IMAGE=hammrly/desktop-astronomy:local
FROM ${ASTRONOMY_IMAGE}

USER root

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        clinfo \
        nvidia-cuda-toolkit \
        ocl-icd-libopencl1 \
    && rm -rf /var/lib/apt/lists/* \
    && chown -R desktop:desktop /var/lib/nginx

USER desktop
