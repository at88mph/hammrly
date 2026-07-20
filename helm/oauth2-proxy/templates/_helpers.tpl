{{- define "oauth2-proxy.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "oauth2-proxy.fullname" -}}
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

{{- define "oauth2-proxy.selectorLabels" -}}
app.kubernetes.io/name: {{ include "oauth2-proxy.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{- define "oauth2-proxy.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "oauth2-proxy.labels" -}}
helm.sh/chart: {{ include "oauth2-proxy.chart" . }}
{{ include "oauth2-proxy.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{- define "oauth2-proxy.ingressHost" -}}
{{- required "oauth2-proxy.ingressHost is required (set to orchestrator ingress.host)" .Values.ingressHost -}}
{{- end }}

{{- define "oauth2-proxy.redirectUrl" -}}
{{- if .Values.redirectUrl -}}
{{- .Values.redirectUrl -}}
{{- else -}}
{{- printf "https://%s/oauth2/callback" (include "oauth2-proxy.ingressHost" .) -}}
{{- end -}}
{{- end }}

{{- define "oauth2-proxy.cookieDomain" -}}
{{- .Values.cookieDomain | default (include "oauth2-proxy.ingressHost" .) -}}
{{- end }}

{{- define "oauth2-proxy.serviceUrl" -}}
{{- printf "http://%s.%s.svc:%v" (include "oauth2-proxy.fullname" .) .Release.Namespace (.Values.service.port | int) -}}
{{- end }}

{{- define "oauth2-proxy.middlewareErrorsName" -}}
{{- printf "%s-session-oauth-errors" .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- end }}

{{- define "oauth2-proxy.middlewareAuthName" -}}
{{- printf "%s-session-oauth-auth" .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- end }}
