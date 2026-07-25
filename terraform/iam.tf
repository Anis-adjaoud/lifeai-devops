data "google_compute_default_service_account" "runtime" {
  project = var.project_id

  depends_on = [google_project_service.apis]
}

# Accès en lecture accordé secret par secret, et uniquement à ceux de
# l'environnement courant : le service Cloud Run de dev ne peut pas lire les
# secrets de prod.
resource "google_secret_manager_secret_iam_member" "runtime_accessor" {
  for_each = local.secrets

  project   = var.project_id
  secret_id = google_secret_manager_secret.this[each.key].secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${data.google_compute_default_service_account.runtime.email}"
}

# Rôle au niveau projet : commun aux environnements, donc posé une seule fois
# par l'environnement propriétaire pour éviter que deux states revendiquent la
# même liaison IAM.
resource "google_project_iam_member" "runtime_vertex_ai" {
  count = var.manage_shared_infra ? 1 : 0

  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${data.google_compute_default_service_account.runtime.email}"
}
