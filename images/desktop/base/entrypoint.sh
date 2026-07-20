#!/bin/bash
# Start XFCE over TigerVNC and expose noVNC on NOVNC_PORT, rooted at NOVNC_PATH_PREFIX.
set -euo pipefail

NOVNC_PORT="${NOVNC_PORT:-6080}"
NOVNC_PATH_PREFIX="${NOVNC_PATH_PREFIX:-/}"
VNC_DISPLAY="${VNC_DISPLAY:-:1}"
VNC_GEOMETRY="${VNC_GEOMETRY:-1920x1080}"
export HOME="${HOME:-/home/desktop}"
export USER="${USER:-desktop}"

normalize_prefix() {
  local p="${1:-/}"
  p="${p%/}"
  if [[ -z "${p}" ]]; then
    echo "/"
    return
  fi
  if [[ "${p}" != /* ]]; then
    p="/${p}"
  fi
  echo "${p}"
}

PREFIX="$(normalize_prefix "${NOVNC_PATH_PREFIX}")"
VNC_TCP_PORT=$((5900 + ${VNC_DISPLAY#:}))

mkdir -p "${HOME}/.vnc" "${HOME}/.config"

cat >"${HOME}/.vnc/xstartup" <<'EOF'
#!/bin/sh
unset SESSION_MANAGER
unset DBUS_SESSION_BUS_ADDRESS
exec dbus-launch --exit-with-session startxfce4
EOF
chmod +x "${HOME}/.vnc/xstartup"

vncserver -kill "${VNC_DISPLAY}" >/dev/null 2>&1 || true
vncserver "${VNC_DISPLAY}" \
  -geometry "${VNC_GEOMETRY}" \
  -depth 24 \
  -localhost no \
  -SecurityTypes None

NGINX_CONF="/tmp/hammrly-novnc.conf"
mkdir -p /tmp/nginx-body /tmp/nginx-proxy /tmp/nginx-fastcgi /tmp/nginx-uwsgi /tmp/nginx-scgi
if [[ "${PREFIX}" == "/" ]]; then
  cat >"${NGINX_CONF}" <<EOF
events { worker_connections 1024; }
http {
  include /etc/nginx/mime.types;
  default_type application/octet-stream;
  client_body_temp_path /tmp/nginx-body;
  proxy_temp_path /tmp/nginx-proxy;
  fastcgi_temp_path /tmp/nginx-fastcgi;
  uwsgi_temp_path /tmp/nginx-uwsgi;
  scgi_temp_path /tmp/nginx-scgi;
  access_log /tmp/nginx-access.log;
  error_log /tmp/nginx-error.log;
  server {
    listen ${NOVNC_PORT};
    location / {
      root /usr/share/novnc;
      index vnc.html;
      try_files \$uri \$uri/ =404;
    }
    location /websockify {
      proxy_pass http://127.0.0.1:6081;
      proxy_http_version 1.1;
      proxy_set_header Upgrade \$http_upgrade;
      proxy_set_header Connection "upgrade";
      proxy_read_timeout 86400;
    }
  }
}
EOF
else
  cat >"${NGINX_CONF}" <<EOF
events { worker_connections 1024; }
http {
  include /etc/nginx/mime.types;
  default_type application/octet-stream;
  client_body_temp_path /tmp/nginx-body;
  proxy_temp_path /tmp/nginx-proxy;
  fastcgi_temp_path /tmp/nginx-fastcgi;
  uwsgi_temp_path /tmp/nginx-uwsgi;
  scgi_temp_path /tmp/nginx-scgi;
  access_log /tmp/nginx-access.log;
  error_log /tmp/nginx-error.log;
  server {
    listen ${NOVNC_PORT};
    location = ${PREFIX} {
      return 301 ${PREFIX}/vnc.html?path=${PREFIX}/websockify;
    }
    location = ${PREFIX}/ {
      return 301 ${PREFIX}/vnc.html?path=${PREFIX}/websockify;
    }
    location ${PREFIX}/ {
      alias /usr/share/novnc/;
    }
    location ${PREFIX}/websockify {
      proxy_pass http://127.0.0.1:6081/;
      proxy_http_version 1.1;
      proxy_set_header Upgrade \$http_upgrade;
      proxy_set_header Connection "upgrade";
      proxy_read_timeout 86400;
    }
  }
}
EOF
fi

websockify --web=/usr/share/novnc 6081 "localhost:${VNC_TCP_PORT}" &
WEBSOCKIFY_PID=$!

nginx -c "${NGINX_CONF}" -g 'pid /tmp/nginx.pid; daemon off;' &
NGINX_PID=$!

term_handler() {
  kill "${WEBSOCKIFY_PID}" "${NGINX_PID}" 2>/dev/null || true
  vncserver -kill "${VNC_DISPLAY}" >/dev/null 2>&1 || true
}
trap term_handler TERM INT

wait -n "${WEBSOCKIFY_PID}" "${NGINX_PID}"
