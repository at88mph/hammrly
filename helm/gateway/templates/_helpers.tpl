{{/*
Expand the name of the chart.
*/}}
{{- define "hammrly-gateway.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "hammrly-gateway.fullname" -}}
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

{{/*
Selector labels
*/}}
{{- define "hammrly-gateway.selectorLabels" -}}
app.kubernetes.io/name: {{ include "hammrly-gateway.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "hammrly-gateway.labels" -}}
helm.sh/chart: {{ include "hammrly-gateway.chart" . }}
{{ include "hammrly-gateway.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Chart version label
*/}}
{{- define "hammrly-gateway.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Normalized HTTP path prefix (leading slash, no trailing); empty when httpPathPrefix is unset.
*/}}
{{- define "hammrly-gateway.httpPathPrefixNormalized" -}}
{{- $p := .Values.httpPathPrefix | default "" | trim -}}
{{- if $p -}}
{{- $p = $p | trimSuffix "/" -}}
{{- if not (hasPrefix "/" $p) -}}
{{- $p = printf "/%s" $p -}}
{{- end -}}
{{- print $p -}}
{{- end -}}
{{- end }}
