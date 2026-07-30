locals {
  # ── Nommage ────────────────────────────────────────────────────────────────
  # La production conserve les noms historiques (suffixe vide). Les renommer
  # en « -prod » détruirait puis recréerait le service Cloud Run, qui
  # changerait alors d'URL — cassant l'URI de redirection enregistrée dans le
  # client OAuth Google. Seuls les environnements non-prod sont suffixés.
  suffixe = var.environment == "prod" ? "" : "-${var.environment}"

  service_name  = "lifeai-api${local.suffixe}"
  scheduler_job = "lifeai-daily-sync${local.suffixe}"
  secret_prefix = "lifeai${local.suffixe}"

  # Même VM Postgres pour tous les environnements (le quota Always Free ne
  # couvre qu'une seule e2-micro par compte de facturation), mais une base
  # distincte par environnement : les données ne se mélangent pas.
  # Prod garde « lifeai », nom créé par le startup-script de la VM.
  db_name = var.environment == "prod" ? "lifeai" : "lifeai_${var.environment}"

  # ── Ce qui diffère entre environnements ────────────────────────────────────
  # Regroupé ici plutôt que dispersé dans les tfvars : d'un coup d'œil on voit
  # en quoi dev et prod se distinguent.
  reglages = {
    dev = {
      max_instances   = 1     # un seul conteneur suffit pour tester
      scheduler_actif = false # pas de sync Google Fit automatique en dev
    }
    prod = {
      max_instances   = 3
      scheduler_actif = true
    }
  }
  env = local.reglages[var.environment]

  # ── Étiquettes ─────────────────────────────────────────────────────────────
  # Permettent de filtrer par environnement dans la console GCP et dans la
  # facturation, là où le nom seul ne suffit pas.
  labels = {
    environment = var.environment
    application = "lifeai"
    managed_by  = "terraform"
    name        = "lifeai-tag"
  }
}
