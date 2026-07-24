output "service_url" {
  value = google_cloud_run_v2_service.lifeai_api.uri
}

output "db_internal_ip" {
  value = google_compute_instance.lifeai_db.network_interface[0].network_ip
}
