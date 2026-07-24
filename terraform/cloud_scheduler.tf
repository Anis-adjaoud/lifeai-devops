resource "google_cloud_scheduler_job" "daily_sync" {
  name      = "lifeai-daily-sync"
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
