# URL Cloud Run "stable" (basée sur le numéro de projet, pas sur un hash
# aléatoire) — connue avant même que le service existe, donc pas de problème
# poule/œuf pour OAUTH_REDIRECT_URI (contrairement à l'ancien script bash qui
# devait déployer une première fois avec un placeholder localhost).
locals {
  service_url        = "https://${local.service_name}-${data.google_project.this.number}.${var.region}.run.app"
  oauth_redirect_uri = "${local.service_url}/auth/callback"
}

resource "google_cloud_run_v2_service" "lifeai_api" {
  name     = local.service_name
  project  = var.project_id
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"
  labels   = local.labels

  template {
    service_account                  = data.google_compute_default_service_account.runtime.email
    timeout                          = "300s"
    max_instance_request_concurrency = 160

    scaling {
      min_instance_count = 0
      max_instance_count = local.env.max_instances
    }

    vpc_access {
      network_interfaces {
        network    = var.network
        subnetwork = var.subnet
      }
      egress = "PRIVATE_RANGES_ONLY"
    }

    containers {
      image = "${var.region}-docker.pkg.dev/${var.project_id}/${var.artifact_repo}/lifeai-api:${var.image_tag}"

      resources {
        limits = {
          cpu    = "3"
          memory = "3Gi"
        }
        cpu_idle          = true
        startup_cpu_boost = true
      }

      ports {
        name           = "http1"
        container_port = 8080
      }

      startup_probe {
        tcp_socket {
          port = 8080
        }
        failure_threshold = 1
        period_seconds    = 240
        timeout_seconds   = 240
      }

      volume_mounts {
        name       = "oauth-client-json"
        mount_path = "/secrets"
      }

      env {
        name  = "ENVIRONMENT"
        value = var.environment
      }
      env {
        name  = "GOOGLE_CLOUD_PROJECT"
        value = var.project_id
      }
      env {
        name  = "GOOGLE_CLOUD_LOCATION"
        value = var.region
      }
      env {
        name  = "GOOGLE_GENAI_USE_VERTEXAI"
        value = "TRUE"
      }
      env {
        name  = "ENABLE_LOCAL_SCHEDULER"
        value = "false"
      }
      env {
        name  = "TWILIO_WHATSAPP_FROM"
        value = var.twilio_whatsapp_from
      }
      env {
        name  = "OAUTH_REDIRECT_URI"
        value = local.oauth_redirect_uri
      }
      env {
        name  = "GOOGLE_OAUTH_CLIENT_SECRETS_FILE"
        value = "/secrets/google_client_secrets.json"
      }
      env {
        name  = "SESSION_COOKIE_SECURE"
        value = "true"
      }
      env {
        name  = "ADMIN_EMAILS"
        value = var.admin_emails
      }

      env {
        name = "DATABASE_URL"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.this["database-url"].secret_id
            version = "latest"
          }
        }
      }
      env {
        name = "TWILIO_ACCOUNT_SID"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.this["twilio-account-sid"].secret_id
            version = "latest"
          }
        }
      }
      env {
        name = "TWILIO_AUTH_TOKEN"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.this["twilio-auth-token"].secret_id
            version = "latest"
          }
        }
      }
      env {
        name = "SCHEDULER_SECRET"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.this["scheduler-secret"].secret_id
            version = "latest"
          }
        }
      }
      env {
        name = "SESSION_SECRET"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.this["session-secret"].secret_id
            version = "latest"
          }
        }
      }
    }

    volumes {
      name = "oauth-client-json"
      secret {
        secret = google_secret_manager_secret.this["oauth-client-json"].secret_id
        items {
          path    = "google_client_secrets.json"
          version = "latest"
        }
      }
    }
  }

  traffic {
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
    percent = 100
  }

  depends_on = [
    google_project_service.apis,
    google_secret_manager_secret_iam_member.runtime_accessor,
  ]
}

# Équivalent de --allow-unauthenticated sur `gcloud run deploy`.
resource "google_cloud_run_v2_service_iam_member" "public_invoker" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.lifeai_api.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
