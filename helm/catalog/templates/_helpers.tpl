{{- define "hammrly-catalog.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "hammrly-catalog.fullname" -}}
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

{{- define "hammrly-catalog.selectorLabels" -}}
app.kubernetes.io/name: {{ include "hammrly-catalog.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{- define "hammrly-catalog.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "hammrly-catalog.httpPathPrefixNormalized" -}}
{{- $p := .Values.httpPathPrefix | default "" | trim -}}
{{- if $p -}}
{{- $p = $p | trimSuffix "/" -}}
{{- if not (hasPrefix "/" $p) -}}
{{- $p = printf "/%s" $p -}}
{{- end -}}
{{- print $p -}}
{{- end -}}
{{- end }}

{{- define "hammrly-catalog.labels" -}}
helm.sh/chart: {{ include "hammrly-catalog.chart" . }}
{{ include "hammrly-catalog.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}
