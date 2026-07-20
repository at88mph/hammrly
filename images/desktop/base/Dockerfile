# Build from repository root:
#   docker build -f images/desktop/base/Dockerfile -t hammrly/desktop-base:local .
#
# Hammrly desktop runtime contract:
#   - Listen on port 6080 (override with NOVNC_PORT)
#   - Honor NOVNC_PATH_PREFIX for ingress subpath serving
#   - Run as UID/GID 1000 (HAMMRLY_K8S_JOB_RUN_AS_USER/GROUP default)

FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    HOME=/home/desktop \
    NOVNC_PORT=6080 \
    NOVNC_PATH_PREFIX=/ \
    VNC_DISPLAY=:1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        dbus-x11 \
        nginx \
        novnc \
        python3-websockify \
        tigervnc-common \
        tigervnc-standalone-server \
        tigervnc-tools \
        xfce4 \
        xfce4-terminal \
    && rm -rf /var/lib/apt/lists/* \
    && command -v vncserver >/dev/null \
    && usermod -l desktop -d /home/desktop -m ubuntu \
    && groupmod -n desktop ubuntu \
    && mkdir -p /home/desktop/.vnc \
    && chown -R desktop:desktop /home/desktop \
    && chown -R desktop:desktop /var/lib/nginx

COPY images/desktop/base/entrypoint.sh /usr/local/bin/hammrly-desktop-entrypoint
RUN chmod 755 /usr/local/bin/hammrly-desktop-entrypoint

USER desktop
WORKDIR /home/desktop

EXPOSE 6080

ENTRYPOINT ["/usr/local/bin/hammrly-desktop-entrypoint"]
