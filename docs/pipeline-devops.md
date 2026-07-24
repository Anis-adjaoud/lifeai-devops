# Pipeline DevOps LifeAI — Terraform + GitHub Actions

Ce document explique en détail ce qui a été mis en place dans **ce repo**
(`lifeai-devops`) pour automatiser l'infrastructure et le déploiement, et en
quoi ça diffère du projet d'origine
([`Sara-Ammi/Projet-Annuel-ESGI-4IABD2`](https://github.com/Sara-Ammi/Projet-Annuel-ESGI-4IABD2)).

## 1. Pourquoi un repo + projet GCP séparés

Le projet d'origine est un projet scolaire partagé (repo GitHub d'une
coéquipière, projet GCP `lifeai-498618` dans une organisation Cloud partagée
avec l'équipe). Y expérimenter un pipeline CI/CD signifiait risquer de casser
le déploiement de prod utilisé par l'équipe/le prof à chaque essai.

Ce repo est donc une **instance totalement isolée** :

| | Projet d'origine | Ce repo (`lifeai-devops`) |
|---|---|---|
| Repo GitHub | `Sara-Ammi/Projet-Annuel-ESGI-4IABD2` (partagé, historique complet) | `Anis-adjaoud/lifeai-devops` (1 seul commit initial, pas d'historique importé) |
| Projet GCP | `lifeai-498618` (organisation Cloud partagée) | `lifeai-devops` (projet standalone, aucune organisation, facturation propre) |
| Base Postgres | VM `lifeai-db` en `us-central1-a` | VM `lifeai-db` en `us-west1-b` (voir §7, incident 3 — pénurie de stock sur `us-central1-*`) |
| Client OAuth Google | Un seul, réutilisé au départ, puis **remplacé par un client dédié** (voir §7, incident 6) | Client OAuth propre au projet `lifeai-devops` |
| Déploiement | Scripts bash manuels (`deploy/00_setup_gcp.sh` → `05_setup_scheduler.sh`) + `gcloud run deploy` lancés à la main | 100% Terraform + GitHub Actions, déclenché par un `git push` |
| Build d'image | `gcloud builds submit` (Cloud Build, cache Docker inline) | `docker buildx` dans GitHub Actions (cache GitHub Actions, `type=gha`) |
| Auth vers GCP | Compte gcloud local de l'utilisateur | Workload Identity Federation (keyless, aucune clé JSON stockée) |

## 2. Terraform — infra 100% as-code

Contrairement à l'ancien repo (qui aurait dû importer des ressources déjà
créées à la main — d'où le choix initial de limiter Terraform à Cloud Run
seul), ce projet est parti de **zéro** : Terraform gère donc **toute**
l'infra, sans aucun `terraform import`.

Fichiers dans `terraform/` :

| Fichier | Contenu |
|---|---|
| `versions.tf` | Providers (`google` ~6.0, `random` ~3.6), backend distant `gcs` (bucket `lifeai-devops-tfstate`) |
| `variables.tf` | `project_id`, `region`, `zone`, `image_tag`, et 3 variables **sensibles sans défaut** : `twilio_account_sid`, `twilio_auth_token`, `oauth_client_json` |
| `apis.tf` | Active les 9 APIs GCP nécessaires (`google_project_service` en `for_each`) |
| `artifact_registry.tf` | Le repo Docker `lifeai` |
| `network.tf` | Les 2 règles firewall Postgres (VPC interne + plage IAP) |
| `database.tf` | VM `e2-micro` (Always Free) + mot de passe Postgres **généré aléatoirement** (`random_password`, jamais en clair dans le repo) |
| `secrets.tf` | Les 6 secrets Secret Manager (voir §5) |
| `iam.tf` | Droits `secretAccessor` par secret + `roles/aiplatform.user` pour le service account runtime |
| `cloud_run.tf` | Le service Cloud Run + le binding IAM public (`allUsers` / `roles/run.invoker`) |
| `cloud_scheduler.tf` | Le job quotidien de sync Google Fit |
| `outputs.tf` | `service_url`, `db_internal_ip` |
| `terraform.tfvars.example` | Modèle pour un `plan`/`apply` local (à copier en `terraform.tfvars`, gitignored) |

**Détail notable — l'URL Cloud Run calculée à l'avance.** L'ancien script
bash (`04_deploy.sh`) devait déployer une première fois avec un placeholder
`localhost` pour `OAUTH_REDIRECT_URI`, car l'URL Cloud Run n'était connue
qu'après coup. Ici, `cloud_run.tf` calcule directement l'URL stable (format
`https://<service>-<project_number>.<region>.run.app`, garanti par Cloud Run
dès la création) via un `local`, donc pas de problème d'œuf et de poule :
`OAUTH_REDIRECT_URI` est correct dès le premier `apply`.

## 3. Pipeline GitHub Actions (`.github/workflows/deploy.yml`)

Déclenché sur chaque push sur `main` touchant le code applicatif ou
`terraform/**` (+ `workflow_dispatch` pour un lancement manuel). 3 jobs, dans
cet ordre :

1. **`prepare-registry`** — `terraform apply -target=...` **ciblé** sur
   `google_project_service.apis` + `google_artifact_registry_repository.lifeai`
   uniquement. Nécessaire car `docker push` (job suivant) a besoin de l'API
   Artifact Registry activée et du repo créé — sinon on a un problème
   d'ordre (voir §7, incident 2).
2. **`build`** — build l'image (`docker/build-push-action`, cache
   `type=gha`) et la pousse taggée `<sha>` + `latest`.
3. **`deploy`** — `terraform apply` complet (toutes les ressources), avec
   `image_tag=<sha>` : c'est ce qui crée/actualise réellement Cloud Run,
   la VM, les secrets, le scheduler.

Aucun de ces jobs n'utilise de clé de service account : l'auth se fait via
**Workload Identity Federation** (`google-github-actions/auth@v2`), qui
échange le jeton OIDC GitHub contre un jeton GCP à la volée.

## 4. Validation et cycle plan/apply Terraform

Étapes suivies pour valider la config avant et pendant la mise en place —
utile si tu dois refaire un `plan`/`apply` local plus tard.

**a. Validation syntaxique, avant même que le bucket de state existe.**
Au tout début, le bucket GCS `lifeai-devops-tfstate` (backend distant,
`versions.tf`) n'existait pas encore. Pour pouvoir quand même valider la
config, un fichier `backend_override.tf` temporaire (`backend "local" {}`)
a été ajouté le temps de lancer :
```bash
terraform init -input=false
terraform validate
```
Puis supprimé (avec l'état local généré) une fois la config validée — le
vrai state ne doit exister que dans le bucket GCS distant, jamais en local.

**b. `terraform init` réel, une fois le bucket créé par
`bootstrap/bootstrap_ci.sh`.** Configure le backend GCS distant définitif.
Depuis ce moment, tout `plan`/`apply` (local ou CI) partage le **même**
state — c'est ce qui permet à la CI et à un lancement local de coexister
sans conflit (avec le risque normal de state lock si les deux tournent en
même temps).

**c. Premier `terraform plan` contre le projet réel, vide.** Comme
`lifeai-devops` partait de zéro (pas de ressources à importer), un simple
`plan` avec des valeurs **placeholder** pour les 3 variables sensibles
(juste pour satisfaire la validation Terraform, jamais utilisées pour un
`apply`) a suffi à valider la forme complète de l'infra :
```
Plan: 38 to add, 0 to change, 0 to destroy.
```
Ce chiffre (38 ressources) couvre : les 9 API, le repo Artifact Registry,
2 règles firewall, la VM + son mot de passe généré, les 6 secrets + leurs
6 versions + leurs 6 bindings IAM, le service Cloud Run + son binding IAM
public, le job Scheduler, et les 2 `random_id`.

**d. Aucun `apply` local avec des valeurs placeholder.** Une fois le
`plan` validé, le tout premier `apply` réel (avec les vraies valeurs
Twilio/OAuth) a été fait **via la CI**, pas en local — les vraies valeurs
Twilio/OAuth n'étaient de toute façon disponibles que côté secrets GitHub,
jamais en clair sur la machine locale.

**e. Corrections en cours de route faites hors Terraform.** Certains
correctifs (rôle IAM `run.admin`, voir §7 incident 4) ont été appliqués
directement via `gcloud` pour débloquer immédiatement le run en cours,
**puis** reportés dans `bootstrap/bootstrap_ci.sh`/`terraform/*.tf` pour
que les prochains `apply` (CI ou local) restent cohérents avec l'état réel
— sinon Terraform aurait fini par vouloir « corriger » ce correctif manuel
au prochain `plan`.

**Pour relancer un `plan`/`apply` en local plus tard :**
```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars   # puis compléter les 3 valeurs sensibles
terraform init      # backend GCS, state partagé avec la CI
terraform plan
terraform apply
```

## 5. Secrets — trois niveaux différents

| Secret | Où | Comment |
|---|---|---|
| `lifeai-database-url` | Secret Manager | Construit par Terraform depuis le mot de passe généré (`random_password`) + l'IP interne de la VM |
| `lifeai-scheduler-secret`, `lifeai-session-secret` | Secret Manager | Générés par Terraform (`random_id`, 32 octets), équivalent de l'ancien `openssl rand -hex 32` |
| `lifeai-twilio-*`, `lifeai-oauth-client-json` | Secret Manager | Valeur fournie en entrée (Twilio existant, client OAuth dédié — voir §7, incident 6), stockée par Terraform |
| `GCP_WORKLOAD_IDENTITY_PROVIDER`, `GCP_SERVICE_ACCOUNT`, `GCP_PROJECT_ID` | **GitHub** Actions secrets | Sortis de `bootstrap/bootstrap_ci.sh`, permettent l'auth CI → GCP |
| `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `OAUTH_CLIENT_JSON` | **GitHub** Actions secrets | Fournis manuellement, transmis à Terraform via `TF_VAR_*` (voir §7, incident 5) |

Aucune valeur sensible n'est committée dans le repo — les secrets GitHub
sont le seul point d'entrée pour les credentials externes.

## 6. `bootstrap/bootstrap_ci.sh` — le seul script bash restant

Remplace tous les scripts `deploy/00-05_*.sh` de l'ancien repo. Un seul
script, à lancer **une fois**, qui crée les prérequis que Terraform ne peut
pas créer lui-même (problème d'œuf et de poule : il faut bien un moyen
d'authentifier la CI *avant* qu'elle puisse lancer Terraform) :

- Le projet GCP `lifeai-devops` + liaison à la facturation
- Le bucket GCS `lifeai-devops-tfstate` (state Terraform)
- Le Workload Identity Pool + Provider OIDC (restreint au repo
  `Anis-adjaoud/lifeai-devops` uniquement, via `attribute-condition`)
- Le service account `github-actions-deployer`, avec des rôles **granulaires**
  (pas `roles/editor`) : `run.admin`, `artifactregistry.admin`,
  `compute.admin`, `secretmanager.admin`, `cloudscheduler.admin`,
  `serviceusage.serviceUsageAdmin`, `resourcemanager.projectIamAdmin`,
  `iam.serviceAccountUser`

Tout le reste (VM, secrets, Cloud Run, scheduler...) est créé par Terraform,
piloté depuis la CI avec ce service account.

## 7. Incidents rencontrés pendant la mise en place (et corrections)

Ces problèmes n'existaient pas sur l'ancien repo — soit parce qu'il ne
partait pas de zéro (les ressources existaient déjà), soit parce que les
scripts bash faisaient les choses dans un ordre différent. Utile pour
comprendre certains choix du code actuel :

1. **Propagation IAM après création du projet** — juste après
   `gcloud projects create`, les permissions du compte owner ne sont pas
   immédiatement effectives partout (création du Workload Identity Pool,
   puis du binding IAM sur le service account fraîchement créé, ont chacun
   échoué une fois avec `PERMISSION_DENIED`/`does not exist`). Résolu en
   relançant le script quelques secondes après — il est idempotent, donc
   sans risque.
2. **Artifact Registry API pas encore activée au moment du `docker push`** —
   le job `build` s'exécutait avant que Terraform (job `deploy`) n'active
   l'API et ne crée le repo. Résolu avec le job `prepare-registry` (apply
   ciblé, voir §3).
3. **`ZONE_RESOURCE_POOL_EXHAUSTED` sur `us-central1-a/b/c/f`** — plus de
   stock e2-micro disponible sur ces zones au moment du premier déploiement
   (vérifié : ce n'était pas un problème de quota projet, 200 CPUs
   disponibles). Résolu en déplaçant la VM vers `us-west1-b` (testé
   disponible), tout en gardant `region = us-central1` pour Cloud Run /
   Artifact Registry (le réseau VPC `default` étant global, une VM peut être
   dans une région différente du reste sans problème).
4. **`roles/run.developer` insuffisant** — ce rôle permet de déployer des
   révisions Cloud Run mais pas de poser une policy IAM dessus
   (`run.services.setIamPolicy`), nécessaire pour le binding
   `allUsers`/`roles/run.invoker` (équivalent de `--allow-unauthenticated`).
   Remplacé par `roles/run.admin`.
5. **JSON du client OAuth corrompu dans Secret Manager** — le secret
   `OAUTH_CLIENT_JSON` était interpolé directement dans une commande shell
   (`-var="oauth_client_json=${{ secrets.OAUTH_CLIENT_JSON }}"`) ; les
   guillemets internes du JSON cassaient le parsing du shell, tronquant la
   valeur avant qu'elle n'atteigne Terraform. Résultat : `JSONDecodeError`
   au runtime sur `/auth/start` (Internal Server Error). Corrigé en passant
   ces 3 secrets via des variables d'environnement `TF_VAR_*`, que Terraform
   lit nativement sans repasser par un argument shell.
6. **Réutilisation du client OAuth existant, puis remise en cause** — pour
   aller plus vite, le client OAuth du projet d'origine (`lifeai-498618`)
   avait d'abord été réutilisé tel quel. En pratique, ça recréait un
   couplage entre les deux projets (accès limité aux comptes ayant un rôle
   actif sur `lifeai-498618`, gestion des redirect URIs à cheval sur deux
   projets). Décision finale : créer un écran de consentement OAuth +
   client dédié dans `lifeai-devops`, complétant l'isolation.
7. **`redirect_uri_mismatch` puis `access_denied`** — attendu lors de la
   création du nouveau client OAuth : l'URI de redirection devait être
   ajoutée explicitement, puis le compte de test ajouté à la liste des
   utilisateurs de test de l'écran de consentement (obligatoire tant que
   l'appli est en mode "Testing", ce qui est le cas ici — pas besoin de
   passer en production/vérifié pour un usage perso).

## 8. Ce qui reste manuel (volontairement — Google ne l'expose pas en API)

- Configuration de l'écran de consentement OAuth (type, utilisateurs de
  test) — pas d'équivalent Terraform/gcloud pour un client OAuth
  "Application Web" classique.
- Création du client OAuth 2.0 lui-même (`client_id`/`client_secret`) —
  idem, aucune API publique.
- Ajout des 6 secrets dans GitHub (Settings → Secrets and variables →
  Actions) — nécessite un accès web au repo.
- Lancement initial de `bootstrap/bootstrap_ci.sh` — one-shot, avant le tout
  premier `terraform apply`.

## 9. Opérations du quotidien

| Tu veux... | Comment |
|---|---|
| Déployer un changement de code | `git push` sur `main` — tout est automatique |
| Voir/changer la conf infra (cpu, secrets référencés, scheduler...) | Éditer `terraform/*.tf`, push sur `main` |
| Tester un `plan` sans déployer | Voir §4.e — `terraform.tfvars` local (gitignored) ou `TF_VAR_*` |
| Changer un secret externe (Twilio, OAuth) | Mettre à jour le secret GitHub correspondant, relancer le workflow |
