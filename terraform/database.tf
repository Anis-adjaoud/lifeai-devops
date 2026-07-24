resource "random_password" "db" {
  length  = 24
  special = false
}

# VM Postgres (e2-micro, Always Free) — même image/config que l'ancien
# deploy/01_setup_db_vm.sh, désormais géré par Terraform. Pas de service
# account attaché : la VM n'appelle aucune API GCP (juste Docker en local),
# donc pas besoin de credentials dessus (plus restrictif que le défaut
# `gcloud compute instances create`, sans régression fonctionnelle).
resource "google_compute_instance" "lifeai_db" {
  name         = "lifeai-db"
  project      = var.project_id
  zone         = var.zone
  machine_type = "e2-micro"

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
      size  = 30
      type  = "pd-standard"
    }
  }

  network_interface {
    network    = var.network
    subnetwork = var.subnet
    access_config {} # IP externe éphémère : nécessaire pour télécharger Docker
                      # + l'image postgres:16-alpine (pas de Cloud NAT, payant).
                      # N'expose PAS Postgres : voir network.tf (firewall interne only).
  }

  metadata_startup_script = <<-EOF
    #!/bin/bash
    set -e
    if ! command -v docker >/dev/null; then
      curl -fsSL https://get.docker.com | sh
    fi
    docker rm -f lifeai_postgres 2>/dev/null || true
    mkdir -p /var/lib/lifeai-pgdata
    docker run -d --name lifeai_postgres --restart unless-stopped \
      -e POSTGRES_DB=lifeai \
      -e POSTGRES_USER=postgres \
      -e POSTGRES_PASSWORD='${random_password.db.result}' \
      -p 5432:5432 \
      -v /var/lib/lifeai-pgdata:/var/lib/postgresql/data \
      postgres:16-alpine
  EOF

  allow_stopping_for_update = true

  depends_on = [google_project_service.apis]
}

locals {
  database_url = "postgresql://postgres:${random_password.db.result}@${google_compute_instance.lifeai_db.network_interface[0].network_ip}:5432/lifeai"
}
