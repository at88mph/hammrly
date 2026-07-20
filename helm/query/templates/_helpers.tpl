{{- define "hammrly-query.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "hammrly-query.fullname" -}}
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

{{- define "hammrly-query.selectorLabels" -}}
app.kubernetes.io/name: {{ include "hammrly-query.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{- define "hammrly-query.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/* Normalized HTTP path prefix (leading slash, no trailing); empty string when unset */}}
{{- define "hammrly-query.httpPathPrefixNormalized" -}}
{{- $p := .Values.httpPathPrefix | default "" | trim -}}
{{- if $p -}}
{{- $p = $p | trimSuffix "/" -}}
{{- if not (hasPrefix "/" $p) -}}
{{- $p = printf "/%s" $p -}}
{{- end -}}
{{- print $p -}}
{{- end -}}
{{- end }}

{{- define "hammrly-query.labels" -}}
helm.sh/chart: {{ include "hammrly-query.chart" . }}
{{ include "hammrly-query.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/* database: inline | assembled | invalid — url with "://" = full DSN; else with Secret = host:port/db */}}
{{- define "hammrly-query.databaseMode" -}}
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
