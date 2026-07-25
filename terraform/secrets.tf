resource "random_id" "scheduler_secret" {
  byte_length = 32
}

resource "random_id" "session_secret" {
  byte_length = 32
}

locals {
  # Clés logiques → valeurs. Le nom réel dans Secret Manager est préfixé par
  # l'environnement (local.secret_prefix), afin que dev et prod n'écrivent
  # jamais dans le même secret.
  secrets = {
    "database-url"       = local.database_url
    "twilio-account-sid" = var.twilio_account_sid
    "twilio-auth-token"  = var.twilio_auth_token
    "scheduler-secret"   = random_id.scheduler_secret.hex
    "session-secret"     = random_id.session_secret.hex
    "oauth-client-json"  = var.oauth_client_json
  }

  # prod : lifeai-database-url  ·  dev : lifeai-dev-database-url
  nom_secret = { for cle, _ in local.secrets : cle => "${local.secret_prefix}-${cle}" }
}

resource "google_secret_manager_secret" "this" {
  for_each = local.secrets

  project   = var.project_id
  secret_id = local.nom_secret[each.key]
  labels    = local.labels

  replication {
    auto {}
  }

  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "this" {
  for_each = local.secrets

  secret      = google_secret_manager_secret.this[each.key].id
  secret_data = each.value
}
