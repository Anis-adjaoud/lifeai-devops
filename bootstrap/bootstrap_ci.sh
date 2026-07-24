#!/usr/bin/env bash
# Prérequis GCP pour ce pipeline (Terraform + GitHub Actions) — à lancer UNE
# SEULE FOIS, avant le premier `terraform init`. Crée le projet GCP lui-même,
# le lie à la facturation, puis le bucket de state Terraform, le Workload
# Identity Pool/Provider OIDC (auth GitHub Actions "keyless", sans clé JSON),
# et le service account github-actions-deployer avec les rôles nécessaires
# pour que Terraform puisse créer TOUTE l'infra (VM, secrets, scheduler...).
# Script idempotent : relançable sans effet de bord si les ressources existent déjà.
set -euo pipefail

PROJECT_ID="lifeai-devops"
PROJECT_NAME="LifeAI DevOps"
BILLING_ACCOUNT="01B8EC-A0147C-6015E5"
REGION="us-central1"

GITHUB_REPO="Anis-adjaoud/lifeai-devops"
TFSTATE_BUCKET="${PROJECT_ID}-tfstate"
CI_SA_NAME="github-actions-deployer"
CI_SA_EMAIL="${CI_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
CI_WIF_POOL="github-pool"
CI_WIF_PROVIDER="github-provider"

echo "== Projet GCP (${PROJECT_ID}) =="
if ! gcloud projects describe "$PROJECT_ID" >/dev/null 2>&1; then
  gcloud projects create "$PROJECT_ID" --name="$PROJECT_NAME"
else
  echo "Projet déjà existant, skip la création."
fi
gcloud config set project "$PROJECT_ID"

echo "== Liaison au compte de facturation (${BILLING_ACCOUNT}) =="
CURRENT_BILLING=$(gcloud billing projects describe "$PROJECT_ID" --format='value(billingAccountName)' 2>/dev/null || true)
if [[ "$CURRENT_BILLING" != *"$BILLING_ACCOUNT"* ]]; then
  gcloud billing projects link "$PROJECT_ID" --billing-account="$BILLING_ACCOUNT"
else
  echo "Déjà lié, skip."
fi

echo "== APIs nécessaires à ce bootstrap (le reste est activé par Terraform) =="
gcloud services enable iam.googleapis.com iamcredentials.googleapis.com sts.googleapis.com \
  cloudresourcemanager.googleapis.com serviceusage.googleapis.com storage.googleapis.com

PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')
RUNTIME_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

echo "== Bucket GCS pour le state Terraform (${TFSTATE_BUCKET}) =="
if ! gcloud storage buckets describe "gs://${TFSTATE_BUCKET}" >/dev/null 2>&1; then
  gcloud storage buckets create "gs://${TFSTATE_BUCKET}" \
    --location="$REGION" \
    --uniform-bucket-level-access
  gcloud storage buckets update "gs://${TFSTATE_BUCKET}" --versioning
else
  echo "Bucket déjà existant, skip."
fi

echo "== Workload Identity Pool (${CI_WIF_POOL}) =="
if ! gcloud iam workload-identity-pools describe "$CI_WIF_POOL" --location=global >/dev/null 2>&1; then
  gcloud iam workload-identity-pools create "$CI_WIF_POOL" \
    --location=global \
    --display-name="GitHub Actions"
else
  echo "Pool déjà existant, skip."
fi

echo "== Provider OIDC GitHub (${CI_WIF_PROVIDER}) — restreint au repo ${GITHUB_REPO} =="
if ! gcloud iam workload-identity-pools providers describe "$CI_WIF_PROVIDER" \
    --location=global --workload-identity-pool="$CI_WIF_POOL" >/dev/null 2>&1; then
  gcloud iam workload-identity-pools providers create-oidc "$CI_WIF_PROVIDER" \
    --location=global \
    --workload-identity-pool="$CI_WIF_POOL" \
    --display-name="GitHub OIDC" \
    --issuer-uri="https://token.actions.githubusercontent.com" \
    --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.ref=assertion.ref" \
    --attribute-condition="assertion.repository == '${GITHUB_REPO}'"
else
  echo "Provider déjà existant, skip."
fi

echo "== Service account ${CI_SA_EMAIL} =="
if ! gcloud iam service-accounts describe "$CI_SA_EMAIL" >/dev/null 2>&1; then
  gcloud iam service-accounts create "$CI_SA_NAME" \
    --display-name="GitHub Actions — build & deploy LifeAI (Terraform)"
else
  echo "Service account déjà existant, skip."
fi

# Rôles granulaires (pas roles/editor) : juste ce qu'il faut pour que
# Terraform crée/gère Cloud Run, la VM, les secrets, le scheduler, l'Artifact
# Registry, active les APIs et pose les bindings IAM runtime.
echo "== Rôles IAM (projet) =="
for role in \
  roles/run.admin \
  roles/artifactregistry.admin \
  roles/compute.admin \
  roles/secretmanager.admin \
  roles/cloudscheduler.admin \
  roles/serviceusage.serviceUsageAdmin \
  roles/resourcemanager.projectIamAdmin \
  roles/iam.serviceAccountUser \
; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:${CI_SA_EMAIL}" \
    --role="$role" \
    --condition=None >/dev/null
done

echo "== Rôle storage.objectAdmin sur le bucket tfstate uniquement =="
gcloud storage buckets add-iam-policy-binding "gs://${TFSTATE_BUCKET}" \
  --member="serviceAccount:${CI_SA_EMAIL}" \
  --role="roles/storage.objectAdmin" >/dev/null

echo "== Autorise le repo GitHub (${GITHUB_REPO}) à impersonate ce SA via WIF =="
gcloud iam service-accounts add-iam-policy-binding "$CI_SA_EMAIL" \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${CI_WIF_POOL}/attribute.repository/${GITHUB_REPO}" >/dev/null

WIF_PROVIDER_RESOURCE="projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${CI_WIF_POOL}/providers/${CI_WIF_PROVIDER}"

echo ""
echo "OK — bootstrap terminé. Runtime SA (par défaut compute, utilisé par Cloud Run) : ${RUNTIME_SA}"
echo ""
echo "Ajoute ces secrets dans GitHub → Settings → Secrets and variables → Actions"
echo "(repo ${GITHUB_REPO}) :"
echo ""
echo "  GCP_WORKLOAD_IDENTITY_PROVIDER = ${WIF_PROVIDER_RESOURCE}"
echo "  GCP_SERVICE_ACCOUNT            = ${CI_SA_EMAIL}"
echo "  GCP_PROJECT_ID                 = ${PROJECT_ID}"
echo "  TWILIO_ACCOUNT_SID             = <ton Account SID Twilio>"
echo "  TWILIO_AUTH_TOKEN              = <ton Auth Token Twilio>"
echo "  OAUTH_CLIENT_JSON              = <contenu complet de google_client_secrets.json>"
