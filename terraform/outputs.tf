output "environment" {
  value = var.environment
}

output "service_url" {
  value = google_cloud_run_v2_service.lifeai_api.uri
}

output "service_name" {
  value = local.service_name
}

output "database_name" {
  description = "Base utilisée par cet environnement sur le serveur Postgres partagé."
  value       = local.db_name
}

output "db_internal_ip" {
  value = local.db_host
}
