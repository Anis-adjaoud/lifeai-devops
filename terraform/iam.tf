data "google_compute_default_service_account" "runtime" {
  project = var.project_id

  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_iam_member" "runtime_accessor" {
  for_each = local.secrets

  project   = var.project_id
  secret_id = google_secret_manager_secret.this[each.key].secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${data.google_compute_default_service_account.runtime.email}"
}

resource "google_project_iam_member" "runtime_vertex_ai" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${data.google_compute_default_service_account.runtime.email}"
}
