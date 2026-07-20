{{- define "hammrly-portal.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "hammrly-portal.fullname" -}}
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

{{- define "hammrly-portal.selectorLabels" -}}
app.kubernetes.io/name: {{ include "hammrly-portal.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{- define "hammrly-portal.labels" -}}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version | replace "+" "_" }}
{{ include "hammrly-portal.selectorLabels" . }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Normalized HTTP path prefix (leading slash, no trailing); empty when httpPathPrefix is unset.
*/}}
{{- define "hammrly-portal.httpPathPrefixNormalized" -}}
{{- $p := .Values.httpPathPrefix | default "" | trim -}}
{{- if $p -}}
{{- $p = $p | trimSuffix "/" -}}
{{- if not (hasPrefix "/" $p) -}}
{{- $p = printf "/%s" $p -}}
{{- end -}}
{{- print $p -}}
{{- end -}}
{{- end }}

{{/*
HTTP probe path: prefix root when httpPathPrefix is set, otherwise /.
*/}}
{{- define "hammrly-portal.probePath" -}}
{{- $prefix := include "hammrly-portal.httpPathPrefixNormalized" . -}}
{{- if $prefix -}}
{{- printf "%s/" $prefix -}}
{{- else -}}
/
{{- end -}}
{{- end }}
