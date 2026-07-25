# ── Serveur Postgres : partagé, une seule VM pour tous les environnements ────
# Le quota Always Free ne couvre qu'une e2-micro par compte de facturation :
# une seconde VM serait facturée. Les environnements se partagent donc le
# serveur mais possèdent chacun leur base (voir local.db_name).

resource "random_password" "db" {
  count = var.manage_shared_infra ? 1 : 0

  length  = 24
  special = false
}

# Pas de service account attaché : la VM n'appelle aucune API GCP (juste
# Docker en local), donc aucun credential n'a besoin d'y résider — plus
# restrictif que le défaut de `gcloud compute instances create`.
resource "google_compute_instance" "lifeai_db" {
  # Constats checkov acceptés, avec leur raison :
  #checkov:skip=CKV_GCP_40:IP externe éphémère indispensable pour installer Docker et tirer l'image postgres. L'alternative (Cloud NAT) est facturée à l'heure. Postgres n'est pas exposé pour autant : le port 5432 n'est ouvert qu'au VPC interne et à la plage IAP (voir network.tf).
  #checkov:skip=CKV_GCP_38:Les disques sont déjà chiffrés au repos par des clés gérées par Google. Passer à des clés fournies par le client (CSEK) imposerait de gérer leur cycle de vie et leur sauvegarde, pour un bénéfice nul face au modèle de menace de ce projet.
  count = var.manage_shared_infra ? 1 : 0

  name         = "lifeai-db"
  project      = var.project_id
  zone         = var.zone
  machine_type = "e2-micro"
  labels       = local.labels

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
    # N'expose PAS Postgres : voir network.tf (firewall interne uniquement).
  }

  # Corrige CKV_GCP_32 : sans cela, toute clé SSH ajoutée au niveau du projet
  # ouvrirait un accès à cette VM, qui héberge la base de données.
  metadata = {
    block-project-ssh-keys = "TRUE"
  }

  # Corrige CKV_GCP_39 : démarrage vérifié (Secure Boot), identité de la VM
  # attestée (vTPM) et surveillance d'intégrité. L'image debian-12 utilisée
  # est compatible UEFI, donc aucun changement d'image n'est nécessaire.
  shielded_instance_config {
    enable_secure_boot          = true
    enable_vtpm                 = true
    enable_integrity_monitoring = true
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
      -e POSTGRES_PASSWORD='${random_password.db[0].result}' \
      -p 5432:5432 \
      -v /var/lib/lifeai-pgdata:/var/lib/postgresql/data \
      postgres:16-alpine
  EOF

  # ATTENTION — `metadata_startup_script` est un attribut ForceNew : toute
  # modification de ce script détruit et recrée la VM, donc son disque de
  # démarrage, donc TOUTES les bases. Ne pas y ajouter la création des bases
  # des autres environnements : elles se créent une fois à la main via un
  # tunnel IAP (voir README, « Créer la base d'un nouvel environnement »).

  allow_stopping_for_update = true

  depends_on = [google_project_service.apis]
}

# ── Environnements non propriétaires ─────────────────────────────────────────
# Ils ne créent ni la VM ni le mot de passe : ils les lisent. Le mot de passe
# est extrait du DSN de l'environnement propriétaire, car c'est le même
# superutilisateur Postgres sur le même serveur — en régénérer un ici ne
# correspondrait à rien de ce que la VM connaît.

data "google_compute_instance" "lifeai_db" {
  count = var.manage_shared_infra ? 0 : 1

  name    = "lifeai-db"
  project = var.project_id
  zone    = var.zone
}

data "google_secret_manager_secret_version" "dsn_reference" {
  count = var.manage_shared_infra ? 0 : 1

  project = var.project_id
  secret  = var.shared_dsn_secret
}

locals {
  db_password = var.manage_shared_infra ? (
    random_password.db[0].result
    ) : (
    regex("^postgresql://postgres:([^@]+)@", data.google_secret_manager_secret_version.dsn_reference[0].secret_data)[0]
  )

  db_host = var.manage_shared_infra ? (
    google_compute_instance.lifeai_db[0].network_interface[0].network_ip
    ) : (
    data.google_compute_instance.lifeai_db[0].network_interface[0].network_ip
  )

  database_url = "postgresql://postgres:${local.db_password}@${local.db_host}:5432/${local.db_name}"
}
