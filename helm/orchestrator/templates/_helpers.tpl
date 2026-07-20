{{- define "hammrly-orchestrator.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "hammrly-orchestrator.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end }}

{{- define "hammrly-orchestrator.selectorLabels" -}}
app.kubernetes.io/name: {{ include "hammrly-orchestrator.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{- define "hammrly-orchestrator.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "hammrly-orchestrator.labels" -}}
helm.sh/chart: {{ include "hammrly-orchestrator.chart" . }}
{{ include "hammrly-orchestrator.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{- define "hammrly-orchestrator.workloadNamespace" -}}
{{- .Values.k8sWorkloadNamespace | default .Release.Namespace }}
{{- end }}

{{- define "hammrly-orchestrator.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{- default (include "hammrly-orchestrator.fullname" .) .Values.serviceAccount.name }}
{{- else if .Values.serviceAccount.name -}}
{{- .Values.serviceAccount.name }}
{{- end -}}
{{- end }}

{{/* database: inline | assembled | invalid — url with "://" = full DSN; else with Secret = host:port/db */}}
{{- define "hammrly-orchestrator.databaseMode" -}}
{{- $db := .Values.database -}}
{{- $sn := $db.existingSecret -}}
{{- $k := $db.secretKeys -}}
{{- $u := $db.url | default "" | toString -}}
{{- if contains "://" $u -}}
{{- printf "inline" -}}
{{- else if and $sn $k.username $k.password $u -}}
{{- printf "assembled" -}}
{{- else -}}
{{- printf "invalid" -}}
{{- end -}}
{{- end }}

{{/* Traefik Middleware CR names (must match helm/oauth2-proxy templates). */}}
{{- define "hammrly-orchestrator.sessionOauthMiddlewareErrorsName" -}}
{{- printf "%s-session-oauth-errors" .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- end }}

{{- define "hammrly-orchestrator.sessionOauthMiddlewareAuthName" -}}
{{- printf "%s-session-oauth-auth" .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- end }}

{{- define "hammrly-orchestrator.sessionOauthMiddlewares" -}}
{{- $ns := .Release.Namespace -}}
{{- $errors := include "hammrly-orchestrator.sessionOauthMiddlewareErrorsName" . -}}
{{- $auth := include "hammrly-orchestrator.sessionOauthMiddlewareAuthName" . -}}
{{- printf "%s-%s@kubernetescrd,%s-%s@kubernetescrd" $ns $errors $ns $auth -}}
{{- end }}

{{/* JSON map applied to every orchestrator-created session Ingress when ingress.auth.enabled. */}}
{{- define "hammrly-orchestrator.sessionAuthAnnotations" -}}
{{- $auth := .Values.ingress.auth | default dict -}}
{{- if not $auth.enabled -}}
{{- "{}" -}}
{{- else -}}
{{- $profile := $auth.profile | default "traefik" -}}
{{- if eq $profile "custom" -}}
{{- $auth.annotations | default dict | toJson -}}
{{- else if eq $profile "nginx" -}}
{{- $host := .Values.ingress.host | required "ingress.host is required when ingress.auth.profile is nginx" -}}
{{- $scheme := .Values.publicUrlScheme | default "https" -}}
{{- $authUrl := $auth.nginx.authUrl | default (printf "%s://%s/oauth2/auth" $scheme $host) -}}
{{- $authSignin := $auth.nginx.authSignin | default (printf "%s://%s/oauth2/start?rd=$escaped_request_uri" $scheme $host) -}}
{{- dict "nginx.ingress.kubernetes.io/auth-url" $authUrl "nginx.ingress.kubernetes.io/auth-signin" $authSignin "nginx.ingress.kubernetes.io/auth-response-headers" "Authorization,X-Auth-Request-User,X-Auth-Request-Email" | toJson -}}
{{- else -}}
{{- $middlewares := $auth.traefik.middlewares | default (include "hammrly-orchestrator.sessionOauthMiddlewares" .) -}}
{{- dict "traefik.ingress.kubernetes.io/router.middlewares" $middlewares | toJson -}}
{{- end -}}
{{- end -}}
{{- end }}
