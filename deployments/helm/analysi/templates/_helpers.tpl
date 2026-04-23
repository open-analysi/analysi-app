{{/*
Common labels — pass a dict with .Root (top-level context) and .layer
to tag the compose-equivalent layer (core, deps, integrations, observability).
Usage: include "analysi.labels" (dict "Root" . "layer" "core")
*/}}
{{- define "analysi.labels" -}}
app.kubernetes.io/name: {{ .Root.Chart.Name }}
app.kubernetes.io/instance: {{ .Root.Release.Name }}
app.kubernetes.io/version: {{ .Root.Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Root.Release.Service }}
helm.sh/chart: {{ .Root.Chart.Name }}-{{ .Root.Chart.Version }}
{{- if .layer }}
analysi.io/layer: {{ .layer }}
{{- end }}
{{- end }}

{{/*
Selector labels for a specific component
*/}}
{{- define "analysi.selectorLabels" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/component: {{ .component }}
{{- end }}

{{/*
Full name: release-chart
*/}}
{{- define "analysi.fullname" -}}
{{- printf "%s-%s" .Release.Name .Chart.Name | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Component fullname: release-chart-component
*/}}
{{- define "analysi.componentName" -}}
{{- printf "%s-%s-%s" .Release.Name .Chart.Name .component | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Database URL constructed from values
*/}}
{{- define "analysi.databaseUrl" -}}
postgresql+asyncpg://{{ .Values.global.database.user }}:{{ .Values.global.database.password }}@{{ .Values.global.database.host }}:{{ .Values.global.database.port }}/{{ .Values.global.database.name }}?ssl={{ .Values.global.database.sslmode | default "disable" }}
{{- end }}

{{/*
Common environment variables shared across services
*/}}
{{- define "analysi.commonEnv" -}}
- name: DATABASE_URL
  valueFrom:
    secretKeyRef:
      name: {{ include "analysi.fullname" . }}-secrets
      key: database-url
- name: VALKEY_HOST
  value: {{ .Values.global.valkey.host | quote }}
- name: VALKEY_PORT
  value: {{ .Values.global.valkey.port | quote }}
- name: VALKEY_PASSWORD
  valueFrom:
    secretKeyRef:
      name: {{ include "analysi.fullname" . }}-secrets
      key: valkey-password
- name: MINIO_ENDPOINT
  value: {{ .Values.global.minio.endpoint | quote }}
- name: MINIO_ACCESS_KEY
  valueFrom:
    secretKeyRef:
      name: {{ include "analysi.fullname" . }}-secrets
      key: minio-access-key
- name: MINIO_SECRET_KEY
  valueFrom:
    secretKeyRef:
      name: {{ include "analysi.fullname" . }}-secrets
      key: minio-secret-key
- name: MINIO_BUCKET
  value: {{ .Values.global.minio.bucket | quote }}
- name: VAULT_HOST
  value: {{ .Values.global.vault.host | quote }}
- name: VAULT_PORT
  value: {{ .Values.global.vault.port | quote }}
- name: VAULT_TOKEN
  valueFrom:
    secretKeyRef:
      name: {{ include "analysi.fullname" . }}-secrets
      key: vault-token
- name: LOG_LEVEL
  value: {{ .Values.global.logLevel | quote }}
- name: ANALYSI_LOG_PAYLOADS
  value: {{ .Values.global.logPayloads | quote }}
- name: ANALYSI_SYSTEM_API_KEY
  valueFrom:
    secretKeyRef:
      name: {{ include "analysi.fullname" . }}-secrets
      key: system-api-key
{{- if .Values.global.auth.adminApiKey }}
- name: ANALYSI_ADMIN_API_KEY
  valueFrom:
    secretKeyRef:
      name: {{ include "analysi.fullname" . }}-secrets
      key: admin-api-key
{{- end }}
{{- if .Values.global.auth.ownerApiKey }}
- name: ANALYSI_OWNER_API_KEY
  valueFrom:
    secretKeyRef:
      name: {{ include "analysi.fullname" . }}-secrets
      key: owner-api-key
{{- end }}
{{- if and .Values.global.alertWebhookSecretsRef .Values.global.alertWebhookSecretsRef.name }}
# Optional: per-tenant alert-webhook signing secrets, sourced from an
# operator-managed Kubernetes Secret. Format inside the Secret value is a
# JSON object mapping tenant → secret string, e.g.:
#   {"default": "abc", "acme-prod": "xyz"}
# When unset, alert ingestion accepts unsigned requests (backward compat).
- name: ANALYSI_ALERT_WEBHOOK_SECRETS
  valueFrom:
    secretKeyRef:
      name: {{ .Values.global.alertWebhookSecretsRef.name | quote }}
      key: {{ .Values.global.alertWebhookSecretsRef.key | default "ANALYSI_ALERT_WEBHOOK_SECRETS" | quote }}
{{- end }}
- name: BACKEND_API_HOST
  value: {{ include "analysi.componentName" (dict "Release" .Release "Chart" .Chart "component" "api") }}
- name: BACKEND_API_PORT
  value: {{ .Values.api.service.port | quote }}
{{- end }}
