# Ressource partagée : un seul dépôt d'images pour tous les environnements.
# Une image est identifiée par le SHA du commit, pas par l'environnement —
# c'est précisément ce qui permet de promouvoir en production l'image déjà
# testée en dev, bit pour bit, sans la reconstruire.
resource "google_artifact_registry_repository" "lifeai" {
  #checkov:skip=CKV_GCP_84:Les images sont déjà chiffrées au repos par des clés gérées par Google. Une clé fournie par le client (CSEK) imposerait d'en gérer la rotation et la sauvegarde — sans cela, perdre la clé rend toutes les images illisibles. Le contenu ici n'est pas sensible : c'est du code applicatif public.
  count = var.manage_shared_infra ? 1 : 0

  project       = var.project_id
  location      = var.region
  repository_id = var.artifact_repo
  format        = "DOCKER"
  description   = "Images LifeAI (partagé dev/prod)"

  depends_on = [google_project_service.apis]
}
