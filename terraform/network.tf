# Postgres accessible uniquement depuis le VPC interne (Cloud Run inclus via
# Direct VPC egress) — jamais exposé publiquement.
resource "google_compute_firewall" "allow_postgres_internal" {
  name        = "lifeai-allow-postgres-internal"
  project     = var.project_id
  network     = var.network
  direction   = "INGRESS"
  description = "Postgres LifeAI - VPC interne uniquement"

  allow {
    protocol = "tcp"
    ports    = ["5432"]
  }

  source_ranges = ["10.128.0.0/9"]

  depends_on = [google_project_service.apis]
}

# Plage IAP : accès admin ponctuel à Postgres via `gcloud compute
# start-iap-tunnel` sans exposer le port publiquement — nécessite quand même
# le rôle IAM iap.tunnelResourceAccessor.
resource "google_compute_firewall" "allow_postgres_iap" {
  name        = "lifeai-allow-postgres-iap"
  project     = var.project_id
  network     = var.network
  direction   = "INGRESS"
  description = "Postgres LifeAI - plage IAP uniquement (admin ponctuel)"

  allow {
    protocol = "tcp"
    ports    = ["5432"]
  }

  source_ranges = ["35.235.240.0/20"]

  depends_on = [google_project_service.apis]
}
