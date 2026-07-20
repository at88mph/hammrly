# Build after desktop-base:
#   docker build -f images/desktop/base/Dockerfile -t hammrly/desktop-base:local .
#   docker build -f images/desktop/astronomy/Dockerfile -t hammrly/desktop-astronomy:local .
#
# Override the base image when publishing:
#   docker build -f images/desktop/astronomy/Dockerfile \
#     --build-arg BASE_IMAGE=registry.example/hammrly/desktop-base:1.0 \
#     -t registry.example/hammrly/desktop-astronomy:1.0 .

ARG BASE_IMAGE=hammrly/desktop-base:local
FROM ${BASE_IMAGE}

USER root

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl \
        firefox \
        openjdk-17-jre-headless \
        python3 \
        python3-astropy \
        python3-matplotlib \
        python3-numpy \
        python3-pip \
        unzip \
        wget \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /opt/topcat/bin \
    && curl -fsSL -o /opt/topcat/topcat-full.jar \
        https://www.star.bristol.ac.uk/mbt/topcat/topcat-full.jar \
    && printf '%s\n' \
        '#!/bin/sh' \
        'exec java -Xmx4096m -jar /opt/topcat/topcat-full.jar "$@"' \
        > /opt/topcat/bin/topcat \
    && chmod 755 /opt/topcat/bin/topcat \
    && ln -sf /opt/topcat/bin/topcat /usr/local/bin/topcat \
    && chown -R desktop:desktop /opt/topcat \
    && chown -R desktop:desktop /var/lib/nginx

USER desktop
