# APIs nécessaires à l'app + à Terraform lui-même (impersonation WIF).
# disable_on_destroy = false : un `terraform destroy` ne doit pas désactiver
# des APIs projet-wide (impacterait d'autres ressources créées manuellement).
locals {
  required_apis = [
    "run.googleapis.com",
    "compute.googleapis.com",
    "secretmanager.googleapis.com",
    "artifactregistry.googleapis.com",
    "cloudscheduler.googleapis.com",
    "aiplatform.googleapis.com",
    "iamcredentials.googleapis.com",
    "sts.googleapis.com",
    "cloudresourcemanager.googleapis.com",
  ]
}

resource "google_project_service" "apis" {
  for_each = toset(local.required_apis)

  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}
