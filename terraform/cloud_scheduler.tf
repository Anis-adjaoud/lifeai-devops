# La synchronisation quotidienne Google Fit ne tourne qu'en production : en
# dev elle consommerait le quota de l'API Google Fit et enverrait de vraies
# notifications WhatsApp pour des données de test (voir local.reglages).
resource "google_cloud_scheduler_job" "daily_sync" {
  count = local.env.scheduler_actif ? 1 : 0

  name      = local.scheduler_job
  project   = var.project_id
  region    = var.region
  schedule  = "0 7 * * *"
  time_zone = "Europe/Paris"

  http_target {
    uri         = "${google_cloud_run_v2_service.lifeai_api.uri}/internal/sync-all"
    http_method = "POST"

    headers = {
      "X-Scheduler-Key" = random_id.scheduler_secret.hex
    }
  }

  depends_on = [google_project_service.apis]
}
