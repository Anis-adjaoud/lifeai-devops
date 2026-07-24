resource "random_id" "scheduler_secret" {
  byte_length = 32
}

resource "random_id" "session_secret" {
  byte_length = 32
}

locals {
  secrets = {
    lifeai-database-url        = local.database_url
    lifeai-twilio-account-sid  = var.twilio_account_sid
    lifeai-twilio-auth-token   = var.twilio_auth_token
    lifeai-scheduler-secret    = random_id.scheduler_secret.hex
    lifeai-session-secret      = random_id.session_secret.hex
    lifeai-oauth-client-json   = var.oauth_client_json
  }
}

resource "google_secret_manager_secret" "this" {
  for_each = local.secrets

  project   = var.project_id
  secret_id = each.key

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
