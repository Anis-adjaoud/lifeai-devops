# Développement.
#
#   terraform init -reconfigure -backend-config="prefix=env/dev"
#   terraform plan -var-file=env/dev.tfvars
#
# Ressources suffixées « -dev » : service lifeai-api-dev, secrets
# lifeai-dev-*, base lifeai_dev sur le serveur Postgres partagé.

environment = "dev"

# Dev ne crée aucune ressource partagée : il lit la VM Postgres et le DSN de
# référence via des data sources (voir database.tf). Passer ce drapeau à true
# ici ferait échouer l'apply sur des ressources « déjà existantes ».
manage_shared_infra = false
