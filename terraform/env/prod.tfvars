# Production.
#
#   terraform init -reconfigure -backend-config="prefix=env/prod"
#   terraform plan -var-file=env/prod.tfvars
#
# Les noms de ressources de cet environnement ne portent PAS de suffixe : ils
# sont antérieurs à la séparation dev/prod, et les renommer détruirait le
# service Cloud Run, dont l'URL est déclarée dans le client OAuth Google.

environment = "prod"

# Prod possède les ressources partagées entre environnements : activation des
# APIs, Artifact Registry, règles firewall, VM Postgres et rôle Vertex AI.
# Un seul environnement doit porter ce drapeau.
manage_shared_infra = true
