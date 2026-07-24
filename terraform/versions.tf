# Bucket créé par bootstrap/bootstrap_ci.sh avant le premier `terraform init`.
# Nom en dur : un seul environnement (pas de multi-env ici).
terraform {
  required_version = ">= 1.5"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # Configuration partielle : le bloc backend n'accepte aucune variable, mais
  # chaque environnement doit posséder son propre state — sinon un apply sur
  # dev écraserait celui de prod. Le préfixe est donc fourni à l'init :
  #
  #   terraform init -reconfigure -backend-config="prefix=env/dev"
  #   terraform init -reconfigure -backend-config="prefix=env/prod"
  #
  # Le verrouillage est natif au backend GCS (pas de table externe à prévoir,
  # contrairement au couple S3 + DynamoDB) : deux apply simultanés sur le même
  # environnement s'excluent mutuellement.
  backend "gcs" {
    bucket = "lifeai-devops-tfstate"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

data "google_project" "this" {
  project_id = var.project_id
}
