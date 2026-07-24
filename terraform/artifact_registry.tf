resource "google_artifact_registry_repository" "lifeai" {
  project       = var.project_id
  location      = var.region
  repository_id = var.artifact_repo
  format        = "DOCKER"
  description   = "Images LifeAI"

  depends_on = [google_project_service.apis]
}
