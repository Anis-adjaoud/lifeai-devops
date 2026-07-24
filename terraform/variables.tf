variable "project_id" {
  type    = string
  default = "lifeai-devops"
}

variable "region" {
  type    = string
  default = "us-central1"
}

variable "zone" {
  # us-central1-a/b/c/f étaient tous en ZONE_RESOURCE_POOL_EXHAUSTED pour
  # e2-micro au moment du premier apply (vérifié via essais gcloud directs,
  # quota du projet non en cause : 200 CPUs dispo, 0 utilisés). us-west1-b a
  # du stock et reste éligible Always Free. Le VPC (réseau `default`) est
  # global, donc rien n'empêche la VM d'être dans une région différente de
  # `var.region` (Cloud Run/Artifact Registry restent en us-central1).
  type    = string
  default = "us-west1-b"
}

variable "service_name" {
  type    = string
  default = "lifeai-api"
}

variable "artifact_repo" {
  type    = string
  default = "lifeai"
}

variable "image_tag" {
  description = "Tag d'image à déployer — passé par la CI via -var (SHA du commit), défaut 'latest' pour un plan/apply local"
  type        = string
  default     = "latest"
}

variable "network" {
  type    = string
  default = "default"
}

variable "subnet" {
  type    = string
  default = "default"
}

variable "admin_emails" {
  type    = string
  default = "adjaoudanis2021@gmail.com"
}

variable "twilio_whatsapp_from" {
  type    = string
  default = "whatsapp:+14155238886"
}

# Pas de défaut pour les 3 variables sensibles ci-dessous : fournies via
# -var à l'apply (localement) ou via secrets GitHub Actions (CI). Jamais
# committées, jamais de valeur par défaut en clair dans le repo.
variable "twilio_account_sid" {
  type      = string
  sensitive = true
}

variable "twilio_auth_token" {
  type      = string
  sensitive = true
}

variable "oauth_client_json" {
  description = "Contenu complet du client_secret OAuth Google (JSON)"
  type        = string
  sensitive   = true
}
