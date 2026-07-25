#!/usr/bin/env bash
# Migration one-shot du state Terraform vers la séparation dev/prod.
#
# Contexte : avant la séparation, un seul state existait (préfixe
# « lifeai-devops ») et les ressources n'avaient pas d'index. L'introduction de
# `count` (ressources partagées) et le passage à des clés de secrets logiques
# changent leurs ADRESSES dans le state, sans rien changer côté GCP.
#
# Sans ces déplacements, Terraform croirait ces ressources disparues et
# voudrait les détruire puis les recréer — ce qui effacerait le disque de la VM
# Postgres (donc la base) et régénérerait le mot de passe du serveur.
#
# `terraform state mv` ne touche AUCUNE ressource réelle : il ne réécrit que la
# correspondance adresse → ressource dans le fichier de state.
#
# Le script est sûr à relancer : chaque déplacement déjà effectué est ignoré.
set -euo pipefail
cd "$(dirname "$0")/../terraform"

BUCKET="lifeai-devops-tfstate"
ANCIEN_PREFIXE="lifeai-devops"
NOUVEAU_PREFIXE="env/prod"
SAUVEGARDE="../.state-backup-$(date +%Y%m%d-%H%M%S).tfstate"

echo "== Sauvegarde du state actuel =="
gcloud storage cp "gs://${BUCKET}/${ANCIEN_PREFIXE}/default.tfstate" "$SAUVEGARDE"
echo "   -> ${SAUVEGARDE}"
echo "   (le bucket est également versionné : restauration possible côté GCS)"

echo "== Copie du state vers le préfixe de production =="
if gcloud storage ls "gs://${BUCKET}/${NOUVEAU_PREFIXE}/default.tfstate" >/dev/null 2>&1; then
  echo "   déjà présent, on conserve l'existant."
else
  gcloud storage cp "gs://${BUCKET}/${ANCIEN_PREFIXE}/default.tfstate" \
                    "gs://${BUCKET}/${NOUVEAU_PREFIXE}/default.tfstate"
fi

echo "== Init sur le nouveau préfixe =="
terraform init -reconfigure -input=false -backend-config="prefix=${NOUVEAU_PREFIXE}" >/dev/null

# Déplace une adresse si et seulement si la source existe encore.
deplacer() {
  local depuis="$1" vers="$2"
  if terraform state list 2>/dev/null | grep -qxF "$depuis"; then
    terraform state mv "$depuis" "$vers" >/dev/null
    echo "   $depuis  ->  $vers"
  fi
}

echo "== Ressources partagées : ajout de l'index [0] (introduction de count) =="
deplacer 'google_artifact_registry_repository.lifeai'        'google_artifact_registry_repository.lifeai[0]'
deplacer 'google_compute_firewall.allow_postgres_internal'   'google_compute_firewall.allow_postgres_internal[0]'
deplacer 'google_compute_firewall.allow_postgres_iap'        'google_compute_firewall.allow_postgres_iap[0]'
deplacer 'google_compute_instance.lifeai_db'                 'google_compute_instance.lifeai_db[0]'
deplacer 'google_project_iam_member.runtime_vertex_ai'       'google_project_iam_member.runtime_vertex_ai[0]'
deplacer 'random_password.db'                                'random_password.db[0]'
deplacer 'google_cloud_scheduler_job.daily_sync'             'google_cloud_scheduler_job.daily_sync[0]'

echo "== Secrets : passage aux clés logiques (le nom GCP, lui, ne change pas) =="
for cle in database-url oauth-client-json scheduler-secret session-secret \
           twilio-account-sid twilio-auth-token; do
  deplacer "google_secret_manager_secret.this[\"lifeai-${cle}\"]" \
           "google_secret_manager_secret.this[\"${cle}\"]"
  deplacer "google_secret_manager_secret_version.this[\"lifeai-${cle}\"]" \
           "google_secret_manager_secret_version.this[\"${cle}\"]"
  deplacer "google_secret_manager_secret_iam_member.runtime_accessor[\"lifeai-${cle}\"]" \
           "google_secret_manager_secret_iam_member.runtime_accessor[\"${cle}\"]"
done

echo ""
echo "OK — migration terminée."
echo "Vérifie maintenant qu'aucune destruction n'est prévue :"
echo "  terraform plan -var-file=env/prod.tfvars   (attendu : 0 to destroy)"
echo ""
echo "L'ancien state reste en place sous gs://${BUCKET}/${ANCIEN_PREFIXE}/ :"
echo "ne le supprimer qu'après avoir validé le plan de production."
