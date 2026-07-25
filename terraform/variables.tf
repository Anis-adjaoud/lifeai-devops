variable "environment" {
  description = "Environnement cible : dev ou prod. Détermine le suffixe des noms de ressources, la base de données utilisée et le dimensionnement (voir locals.tf)."
  type        = string

  validation {
    condition     = contains(["dev", "prod"], var.environment)
    error_message = "environment doit valoir \"dev\" ou \"prod\"."
  }
}

variable "manage_shared_infra" {
  description = <<-EOT
    Cet environnement gère-t-il les ressources PARTAGÉES entre environnements
    (activation des APIs, Artifact Registry, règles firewall, VM Postgres) ?

    Une seule ressource ne peut avoir qu'un seul propriétaire : si les deux
    environnements tentaient de les créer, le second échouerait sur « existe
    déjà ». Un seul environnement doit donc avoir ce drapeau à true — c'est
    prod (voir env/prod.tfvars). Les environnements qui l'ont à false lisent
    ces ressources via des data sources au lieu de les créer.
  EOT
  type        = bool
  default     = false
}

variable "shared_dsn_secret" {
  description = "Secret contenant le DSN de l'environnement propriétaire de la VM Postgres. Les environnements non propriétaires y lisent le mot de passe du serveur partagé (voir database.tf)."
  type        = string
  default     = "lifeai-database-url"
}

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
