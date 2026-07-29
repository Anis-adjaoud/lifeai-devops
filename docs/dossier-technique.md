# Dossier technique — Pipeline DevOps LifeAI (Terraform + GitHub Actions)

**Projet** : LifeAI — Coach de santé IA (ESGI 4IABD2 — Projet Annuel)
**Sous-projet** : Industrialisation du déploiement (Infrastructure as Code + CI/CD)
**Repo** : [Anis-adjaoud/lifeai-devops](https://github.com/Anis-adjaoud/lifeai-devops)
**Projet GCP** : `lifeai-devops`
**Schéma d'architecture** : [`architecture-devops.drawio`](./architecture-devops.drawio) — 2 pages : *1. Application & runtime*, *2. CI/CD & Infrastructure as Code*
**Documentation complémentaire** : [`pipeline-devops.md`](./pipeline-devops.md) (détail pas-à-pas de la mise en place et de chaque incident rencontré)

---

## Sommaire

1. [Introduction et contexte](#1-introduction-et-contexte)
2. [Architecture applicative](#2-architecture-applicative-rappel)
3. [Architecture d'infrastructure cloud (GCP)](#3-architecture-dinfrastructure-cloud-gcp)
4. [Choix architecturaux et justifications](#4-choix-architecturaux-et-justifications)
5. [Infrastructure as Code avec Terraform](#5-infrastructure-as-code-avec-terraform)
6. [Pipeline CI/CD avec GitHub Actions](#6-pipeline-cicd-avec-github-actions)
7. [Sécurité](#7-sécurité)
8. [Retour d'expérience — incidents rencontrés](#8-retour-dexpérience--incidents-rencontrés)
9. [Coûts](#9-coûts)
10. [Limites actuelles et pistes d'amélioration](#10-limites-actuelles-et-pistes-damélioration)
11. [Conclusion](#11-conclusion)
12. [Annexes](#12-annexes)

---

## 1. Introduction et contexte

### 1.1 Le projet LifeAI

LifeAI est une plateforme de coaching santé personnalisé (projet annuel ESGI
4IABD2) : synchronisation Google Fit, analyse multi-agents (Google ADK +
Gemini 2.5 Flash) de 4 domaines de santé (activité, sommeil, nutrition,
risque), dashboard web React et notifications WhatsApp.

### 1.2 Objectif de ce sous-projet

Le repo d'origine ([`Sara-Ammi/Projet-Annuel-ESGI-4IABD2`](https://github.com/Sara-Ammi/Projet-Annuel-ESGI-4IABD2))
déployait l'application manuellement : une suite de scripts bash
(`deploy/00_setup_gcp.sh` à `05_setup_scheduler.sh`) exécutés à la main,
appelant `gcloud` de façon impérative, sans état ni source de vérité unique
pour l'infrastructure.

L'objectif de ce sous-projet est de transformer ce déploiement manuel en un
**pipeline DevOps complet** :

- **Infrastructure as Code** avec Terraform : toute l'infrastructure GCP
  décrite dans du code versionné, reproductible, avec un état (state)
  explicite plutôt qu'une suite de commandes impératives.
- **Intégration/déploiement continus** avec GitHub Actions : chaque
  changement de code déployé automatiquement, sans intervention manuelle.

### 1.3 Pourquoi un repo et un projet GCP séparés

Le repo et le projet GCP d'origine sont partagés avec l'équipe (et
potentiellement consultés par un correcteur). Expérimenter un pipeline
CI/CD dessus revenait à risquer de casser un déploiement de démonstration en
cas d'erreur de configuration. Ce sous-projet a donc été construit dans un
**repo et un projet GCP entièrement isolés** :

| | Projet d'origine | Ce projet |
|---|---|---|
| Repo GitHub | `Sara-Ammi/Projet-Annuel-ESGI-4IABD2` (partagé) | `Anis-adjaoud/lifeai-devops` (isolé) |
| Projet GCP | `lifeai-498618` (organisation Cloud partagée avec l'équipe) | `lifeai-devops` (projet standalone, facturation dédiée) |
| Base de données | VM Postgres propre au projet d'origine | VM Postgres propre, données de démo indépendantes |
| Client OAuth | — | Client OAuth dédié (voir §7.3) |
| Déploiement | Scripts bash manuels | Terraform + GitHub Actions, automatique |

Aucune ressource n'est partagée entre les deux projets : un incident, une
erreur de configuration ou un test sur `lifeai-devops` ne peut avoir aucun
impact sur `lifeai-498618`.

---

## 2. Architecture applicative (rappel)

| Couche | Technologie |
|---|---|
| Backend | FastAPI (Python), agents Google ADK, Gemini 2.5 Flash |
| Frontend | React 18 + Vite, servi en fichiers statiques par le même backend |
| Base de données | PostgreSQL 16 |
| Notifications | Twilio (WhatsApp) |
| ML | Modèles XGBoost embarqués (prédiction de risques à J+7) |
| Scheduler applicatif | Synchronisation quotidienne Google Fit |

Le frontend et le backend sont packagés dans **une seule image Docker**
multi-stage (voir `Dockerfile`) et servis par **un seul service Cloud Run**.
Ce choix n'est pas arbitraire : une architecture à deux origines (frontend
sur Firebase Hosting, backend sur Cloud Run) a été testée en premier, mais
les rewrites Firebase Hosting vers Cloud Run ne transmettent pas le header
`Cookie`, ce qui cassait les sessions de connexion. Une seule origine élimine
le problème sans introduire de load balancer (payant).

---

## 3. Architecture d'infrastructure cloud (GCP)

Voir le schéma complet : [`architecture-devops.drawio`](./architecture-devops.drawio) — page 1
détaille l'application dans son conteneur et ses connexions, page 2 la chaîne de déploiement.

### 3.1 Vue d'ensemble

```
GitHub (push) → GitHub Actions (build image → terraform apply)
                        │  auth keyless (Workload Identity Federation)
                        ▼
        ┌───────────────────────────────────────────────┐
        │  Projet GCP lifeai-devops                       │
        │                                                 │
        │  Artifact Registry ──pull image──▶ Cloud Run     │
        │                                     (lifeai-api) │
        │  Secret Manager ──env/secrets────▶      │        │
        │                                          │VPC direct egress
        │  Cloud Scheduler ──POST /internal/sync──▶│        │
        │                                          ▼        │
        │                              Compute Engine VM    │
        │                              (Postgres, e2-micro) │
        └───────────────────────────────────────────────┘
                        │
              OAuth Google · Twilio WhatsApp · Vertex AI (Gemini)
```

### 3.2 Composants

| Composant | Service GCP | Détail |
|---|---|---|
| Backend + frontend | **Cloud Run** (v2) | Service `lifeai-api`, scale-to-zero à scale-3, région `us-central1`, 2 vCPU / 2 Gi, `startup_cpu_boost` activé |
| Base de données | **Compute Engine** e2-micro | VM `lifeai-db`, `us-west1-b`, PostgreSQL 16 dans un conteneur Docker, disque persistant 30 Go |
| Réseau | **VPC** `default` + 2 règles firewall | Postgres accessible uniquement depuis le VPC interne et la plage IAP — jamais exposé publiquement |
| Images Docker | **Artifact Registry** | Repo `lifeai` (format Docker), `us-central1` |
| Secrets | **Secret Manager** | 6 secrets (DSN Postgres, clés session/scheduler générées, credentials Twilio, client OAuth) |
| Tâche planifiée | **Cloud Scheduler** | Job quotidien (07:00 Europe/Paris) déclenchant la synchronisation Google Fit |
| IA | **Vertex AI** | Accès à Gemini 2.5 Flash via IAM (`roles/aiplatform.user`), sans clé API |
| Authentification CI | **IAM Workload Identity Federation** | Fédération d'identité OIDC entre GitHub Actions et GCP, sans clé de service account |
| État Terraform | **Cloud Storage** | Bucket `lifeai-devops-tfstate`, versionné |

---

## 4. Choix architecturaux et justifications

Cette section documente les alternatives envisagées pour chaque décision
structurante, et pourquoi le choix retenu l'a été.

### 4.1 Cloud Run (serverless) plutôt que GKE ou VM pour le backend

- **Alternatives envisagées** : Compute Engine (VM classique), GKE
  (Kubernetes managé).
- **Choix retenu : Cloud Run.** Scale-to-zero (coût nul à l'arrêt d'usage),
  aucune gestion de cluster/nœuds, déploiement d'image Docker directe,
  intégration native avec Secret Manager, IAM et VPC Direct egress.
- **Compromis accepté** : cold start après une période d'inactivité
  (atténué par `startup_cpu_boost=true` et un `startup_probe` dédié).
  GKE aurait apporté plus de contrôle (sidecars, autoscaling fin) mais un
  surcoût de gestion disproportionné pour une charge de ce volume.

### 4.2 VM Postgres (Docker) plutôt que Cloud SQL managé

- **Alternatives envisagées** : Cloud SQL for PostgreSQL (managé, backups
  automatiques, haute disponibilité optionnelle).
- **Choix retenu : VM `e2-micro` + Docker.** Éligible au tier **Always
  Free** de GCP (coût nul tant que les quotas ne sont pas dépassés), alors
  que Cloud SQL, même en version minimale, engendre un coût mensuel
  récurrent (~7-10 $/mois).
- **Compromis accepté** : pas de backups automatiques, pas de failover, et
  Postgres tourne comme conteneur (moins « managé » qu'une instance Cloud
  SQL). Ce choix est explicitement documenté comme un point d'amélioration
  possible (§10) si le projet devait passer en usage réel prolongé.

### 4.3 VPC Direct egress plutôt que Cloud SQL Proxy / connecteur VPC serverless

Cloud Run communique avec la VM Postgres via **Direct VPC egress**
(`vpc_access` avec `egress = PRIVATE_RANGES_ONLY`), une fonctionnalité qui
évite de payer/gérer un connecteur VPC serverless (Serverless VPC Access)
séparé, tout en gardant Postgres totalement privé (aucune IP publique
autorisée sur le port 5432 — voir règles firewall §3.2).

### 4.4 Un secret par credential, dans Secret Manager

Toutes les valeurs sensibles (DSN Postgres, clés session/scheduler,
credentials Twilio, JSON du client OAuth) sont stockées individuellement
dans **Secret Manager** et injectées à l'exécution (variables d'env ou
volume monté), jamais en clair dans le code, l'image Docker ou les
variables d'environnement du service. Deux origines différentes pour ces
secrets :
- **Générés par Terraform** (`random_password`, `random_id`) pour tout ce
  qui n'a pas besoin d'être lisible par un humain (mot de passe DB, clés
  de session/scheduler) — aucune valeur de ce type n'existe en clair
  nulle part, ni dans le repo, ni dans les secrets GitHub.
- **Fournis en entrée** (Twilio, client OAuth) via des secrets GitHub
  Actions, transmis à Terraform par variables d'environnement `TF_VAR_*`.

### 4.5 Workload Identity Federation plutôt qu'une clé de service account JSON

- **Alternative classique** : générer une clé JSON de service account,
  la stocker comme secret GitHub, l'utiliser pour l'authentification.
- **Choix retenu : Workload Identity Federation (WIF).** GitHub Actions
  échange un jeton OIDC (émis par `token.actions.githubusercontent.com`)
  contre un jeton d'accès GCP de courte durée, sans qu'aucune clé
  long-lived ne soit jamais stockée. Le Workload Identity Pool est en
  plus restreint par `attribute-condition` au seul repo
  `Anis-adjaoud/lifeai-devops` : même en cas de fuite du nom du service
  account, aucun autre repo ne peut l'impersonater.
- **Bénéfice** : élimine une classe entière de risques (clé JSON qui fuite,
  qui n'expire jamais, qu'il faut faire tourner manuellement).

### 4.6 Rôles IAM granulaires plutôt que `roles/editor`

Le service account `github-actions-deployer` utilisé par la CI dispose de
rôles **spécifiques** (`run.admin`, `artifactregistry.admin`,
`compute.admin`, `secretmanager.admin`, `cloudscheduler.admin`,
`serviceusage.serviceUsageAdmin`, `resourcemanager.projectIamAdmin`,
`iam.serviceAccountUser` — ce dernier restreint au seul service account
runtime de Cloud Run) plutôt qu'un rôle générique `roles/editor`. Chaque
rôle correspond à un type de ressource réellement géré par Terraform dans
ce projet — principe du moindre privilège appliqué même dans un contexte
de projet personnel à faible enjeu.

### 4.7 Terraform plutôt que scripts bash impératifs

Voir la section dédiée (§5.1).

### 4.8 GCS comme backend d'état Terraform, plutôt qu'un state local

Le state Terraform est stocké dans un bucket **Cloud Storage versionné**
(`lifeai-devops-tfstate`), jamais en local. Bénéfices : le state est
partagé entre les exécutions locales et la CI (une seule source de vérité),
verrouillé pendant les opérations (évite les applies concurrents), et
récupérable en cas de corruption grâce au versioning du bucket.

### 4.9 Zone de la VM : `us-west1-b` plutôt que `us-central1`

Choix contraint par la disponibilité réelle du stock `e2-micro` au moment
du déploiement (voir incident §8.3) plutôt qu'un choix architectural pur —
documenté ici par souci de transparence. Le réseau VPC étant global,
répartir des ressources entre deux régions au sein du même VPC ne pose pas
de problème fonctionnel (seule une latence réseau additionnelle, non
significative pour ce cas d'usage).

---

## 5. Infrastructure as Code avec Terraform

### 5.1 Pourquoi Terraform plutôt que des scripts bash impératifs

Les scripts `deploy/00-05_*.sh` du projet d'origine fonctionnent, mais
présentent des limites structurelles :

- **Pas d'état** : impossible de savoir, sans relire chaque script, quelle
  ressource existe, avec quelle configuration exacte.
- **Idempotence manuelle** : chaque script réimplémente sa propre logique
  de vérification (`if ! gcloud ... describe ...; then create; fi`), source
  d'erreurs et de code dupliqué.
- **Dérive de configuration (drift)** : rien n'empêche une modification
  manuelle via la Console GCP de diverger silencieusement de ce que les
  scripts auraient produit.
- **Revue de code impossible** : un changement d'infrastructure ne peut pas
  être relu sous forme de diff avant application.

Terraform répond à ces quatre limites : état explicite et partagé,
idempotence native (un `apply` répété sans changement ne fait rien),
détection de la dérive (`terraform plan` compare l'état réel à la
configuration), et changements d'infra revus comme n'importe quel diff de
code.

### 5.2 Organisation des fichiers

```
terraform/
├── versions.tf                 # Providers (google ~6.0, random ~3.6), backend GCS
├── variables.tf                # Toutes les variables, dont 3 sensibles sans defaut
├── apis.tf                     # Activation des 9 APIs GCP necessaires (for_each)
├── artifact_registry.tf        # Repo Docker "lifeai"
├── network.tf                  # 2 regles firewall (Postgres interne + IAP)
├── database.tf                 # VM e2-micro + mot de passe genere (random_password)
├── secrets.tf                  # 6 secrets Secret Manager + leurs versions
├── iam.tf                      # Bindings secretAccessor + aiplatform.user (SA runtime)
├── cloud_run.tf                # Service Cloud Run + binding IAM public
├── cloud_scheduler.tf          # Job de sync quotidienne (production uniquement)
├── locals.tf                   # Nommage et reglages derives de var.environment
├── outputs.tf                  # service_url, db_internal_ip, environment...
└── env/
    ├── dev.tfvars              # environment = "dev"
    └── prod.tfvars             # environment = "prod", proprietaire du partage
```

### 5.2 bis Séparation des environnements

Un seul jeu de fichiers sert les deux environnements ; ce qui les distingue
est calculé dans `locals.tf` à partir de `var.environment` :

| | dev | prod |
|---|---|---|
| Service Cloud Run | `lifeai-api-dev` | `lifeai-api` |
| Secrets | `lifeai-dev-*` | `lifeai-*` |
| Base de données | `lifeai_dev` | `lifeai` |
| State | préfixe `env/dev` | préfixe `env/prod` |
| Instances maximum | 1 | 3 |
| Synchronisation quotidienne | désactivée | activée |

Trois décisions méritent d'être explicitées.

**La production ne porte pas de suffixe.** Ses ressources existaient avant la
séparation ; les renommer en `-prod` aurait entraîné la destruction puis la
recréation du service Cloud Run, dont l'URL est déclarée dans le client OAuth
Google. Le suffixe est donc vide pour prod et appliqué aux autres
environnements — un compromis assumé entre pureté du nommage et continuité de
service.

**Les states sont séparés par préfixe de backend.** Le bloc `backend`
n'acceptant aucune variable, le préfixe est fourni à l'initialisation
(`terraform init -backend-config="prefix=env/dev"`). Deux states distincts
garantissent qu'un `apply` sur dev ne peut structurellement pas modifier la
production.

**Les ressources partagées ont un propriétaire unique.** La VM Postgres, les
règles firewall, l'Artifact Registry et l'activation des APIs sont communs aux
deux environnements : si les deux states tentaient de les créer, le second
échouerait sur des ressources « déjà existantes ». Le drapeau
`manage_shared_infra` désigne explicitement l'environnement propriétaire
(prod) ; les autres lisent ces ressources par des *data sources*. Le mot de
passe Postgres relève du même mécanisme : dev l'extrait du DSN de production
au lieu d'en générer un nouveau, puisqu'il s'agit du même superutilisateur sur
le même serveur.

Aucun `terraform import` n'a été nécessaire : le projet `lifeai-devops`
étant créé de zéro pour ce sous-projet, chaque ressource a été créée
directement par Terraform, sans ressource préexistante à réconcilier.

**Pourquoi pas de `main.tf` ?** Terraform charge **tous** les fichiers `.tf`
d'un répertoire et construit son graphe de dépendances à partir des
références entre ressources, pas de l'ordre ou du nom des fichiers :
`main.tf` n'a donc aucune signification technique, c'est une convention
issue de la *Standard Module Structure* de HashiCorp, pensée pour les
modules et les configurations simples. Elle reste pertinente quand
Terraform ne gère qu'une poignée de ressources — c'est d'ailleurs le cas
dans le projet d'origine, où un `main.tf` unique suffit puisque seul le
service Cloud Run y est décrit. Ici, avec 38 ressources réparties sur 9
domaines, un fichier par domaine rend la navigation plus directe : on
trouve la VM dans `database.tf` et le service dans `cloud_run.tf` plutôt
que par défilement dans un fichier d'environ 400 lignes.

### 5.3 Détail notable : calcul de l'URL Cloud Run avant sa création

Un problème classique du déploiement Cloud Run est que `OAUTH_REDIRECT_URI`
dépend de l'URL du service, connue seulement après sa création — l'ancien
script bash gérait ce problème avec un placeholder `localhost` sur le
premier déploiement. Cloud Run garantit un format d'URL stable et
prévisible dès la création (`https://<service>-<project_number>.<region>.run.app`),
calculable dans `cloud_run.tf` via un simple `local` combinant
`data.google_project.this.number` et les variables `service_name`/`region`.
Résultat : `OAUTH_REDIRECT_URI` est correct dès le tout premier `apply`,
sans étape manuelle.

### 5.4 Le problème du bootstrap (« œuf et poule »)

Terraform ne peut pas créer les ressources dont il a lui-même besoin pour
fonctionner : le bucket de state (le backend `gcs` doit exister *avant*
`terraform init`), et l'identité que la CI utilisera pour s'authentifier
(WIF + service account) doivent exister *avant* que la CI puisse lancer le
moindre `terraform apply`.

Ce problème est résolu par **un seul script bash restant**,
`bootstrap/bootstrap_ci.sh`, lancé une fois manuellement, qui crée
uniquement ces prérequis (projet GCP, bucket de state, Workload Identity
Pool/Provider, service account CI + ses rôles) — tout le reste de
l'infrastructure applicative est ensuite entièrement piloté par Terraform.

### 5.5 Cycle de validation suivi

1. Validation syntaxique (`terraform validate`) via un backend local
   temporaire, avant que le bucket de state ne soit créé.
2. `terraform init` réel une fois le bucket créé par le bootstrap.
3. Premier `terraform plan` contre le projet réel (vide) : **38 ressources
   à créer, 0 à modifier, 0 à détruire** — validation complète de la forme
   de l'infrastructure avant tout `apply`.
4. Premier `apply` réel effectué **via la CI** (avec les vraies valeurs de
   secrets), jamais en local avec des valeurs de test.

(Détail complet dans [`pipeline-devops.md` §4](./pipeline-devops.md).)

---

## 6. Pipeline CI/CD avec GitHub Actions

### 6.1 Un environnement par branche

Le déploiement suit le modèle de branches, chacune associée à un
environnement :

| Branche | Environnement | Accès |
|---|---|---|
| `develop` | dev | push direct — branche de travail |
| `main` | production | pull request validée uniquement |

```
   push                    pull request                merge
develop ──────▶ DEV        develop → main ──────▶  main ──────▶ PRODUCTION
                           revue + plan Terraform
```

Deux propriétés en découlent. D'abord `main` **reflète la production** : ce
qui y est fusionné est déployé, rien d'autre. Ensuite le contrôle avant
production est une **pull request**, et non un simple bouton.

C'est le point décisif du modèle. Une approbation de déploiement dans
l'interface Actions n'affiche presque rien — « approuver ce déploiement ? ».
Une pull request affiche le diff du code, le résultat des tests, le plan
Terraform de production en commentaire, et permet la discussion ligne à ligne.
À coût identique, la revue porte sur beaucoup plus d'information.

Avantage secondaire : le garde-fou repose sur la protection de branche, un
mécanisme gratuit sur tout dépôt. Les règles de protection d'environnement,
elles, sont payantes sur dépôt privé — un contrôle qui disparaîtrait
silencieusement si le dépôt changeait de visibilité.

### 6.2 Les trois pipelines

**`ci.yml`** — déclenché par toute pull request visant `main` (et
manuellement via `workflow_dispatch`).

| Job | Rôle |
|---|---|
| `lint` | `terraform fmt -check`, `terraform validate`, `tflint` |
| `test` | `pytest` — 36 tests unitaires |
| `security` | `checkov` sur les fichiers `.tf` |
| `plan` | *(pull request)* `terraform plan` publié en commentaire — rien n'est appliqué |

Les trois portes de qualité s'exécutent en parallèle et bloquent la suite :
`plan` déclare `needs: [lint, test, security]`.

**`cd-dev.yml`** — déclenché par un push sur `develop`, sans revue de PR :
vérifications (lint, tests, `checkov` sur `env/dev.tfvars`), construction de
l'image, `terraform apply` sur dev, vérification HTTP.

**`cd-prod.yml`** — déclenché par la fusion d'une pull request dans `main` :
vérifications rejouées, reconstruction de l'image, `terraform apply` sur
production, vérification HTTP finale.

Rejouer les vérifications sur `develop` et sur `main`, plutôt que de
dépendre du résultat de `ci.yml`, est en principe redondant — le code arrive
le plus souvent d'un état déjà vérifié. C'est peu coûteux, et cela garantit
que chaque branche déployée est vérifiée **pour elle-même** : un push direct
ou un enchaînement inhabituel de commits ne passeraient pas au travers.

### 6.3 Reconstruction plutôt que promotion d'artefact

La fusion d'une pull request crée un **nouveau SHA**. L'image construite
depuis `develop` ne porte donc pas l'identifiant du commit de `main`, et ne
peut pas être retrouvée par ce seul identifiant.

Trois réponses étaient possibles :

| Approche | Effet |
|---|---|
| Fusion en rebase / fast-forward | Le SHA est conservé, promotion stricte de l'artefact — mais impose la stratégie de fusion du dépôt |
| Résoudre l'image via le commit d'origine | Promotion préservée quelle que soit la fusion, au prix de logique supplémentaire dans le workflow |
| **Reconstruire sur `main`** *(retenu)* | Le plus simple à lire et à expliquer |

La contrepartie est réelle et assumée : la production reçoit une image
reconstruite, et non l'artefact au bit près qui a tourné en dev. Deux builds
du même code peuvent différer — dépendances transitives résolues à des
versions distinctes, horodatages, ordre de couches. Le cache de layers limite
l'écart sans le supprimer.

Pour un projet où l'environnement de dev sert de validation fonctionnelle,
c'est acceptable. Dans un contexte où l'artefact déployé doit être exactement
celui qui a été testé — conformité, audit, certification — la fusion en rebase
serait le choix correct.

### 6.3 Authentification

Chaque job s'authentifie via `google-github-actions/auth@v2`, configuré
avec le provider Workload Identity Federation créé par le bootstrap —
aucune clé de service account stockée dans GitHub à aucun moment.

### 6.4 Gestion des secrets dans le workflow

Les 3 variables sensibles Terraform (`twilio_account_sid`,
`twilio_auth_token`, `oauth_client_json`) sont transmises via des variables
d'environnement `TF_VAR_*` plutôt que par interpolation directe dans un
argument `-var="..."` — cette dernière méthode s'est révélée dangereuse
lorsque la valeur contient des guillemets (voir incident §8.5).

---

## 6 bis. Tests automatisés et portes de qualité

### Tests unitaires

Le périmètre testé a été choisi selon un critère simple : ce qui est testable
**sans service externe**. Les quatre agents de scoring et le calcul du
Nutri-Score sont des fonctions pures — `analyze(dict) -> AgentReport` — sans
base de données, sans appel LLM et sans réseau. La suite complète s'exécute en
moins d'une seconde.

Les tests sont paramétrés sur les quatre agents : chaque règle vérifiée vaut
pour tous, ce qui évite quatre fichiers quasi identiques. Ils couvrent le
score attendu sur un profil sain et sur un profil dégradé, l'ordre relatif
entre les deux, le respect des bornes 0-100, la bonne forme du rapport, et la
robustesse aux données absentes ou aberrantes.

**Ces tests ont trouvé deux défauts réels dès leur première exécution** —
détaillés en §8.8. C'est leur meilleure justification.

Un cas est délibérément **non** figé : le score produit quand toutes les
données manquent. Les agents ne s'accordent pas sur la valeur par défaut à
appliquer (`activity` part de zéro, les trois autres de valeurs favorables, si
bien qu'un utilisateur sans aucune donnée est noté « en bonne santé » par
trois agents sur quatre). Écrire un test qui assère ce comportement
reviendrait à l'entériner ; le test vérifie donc seulement l'absence de
plantage, et l'incohérence est documentée dans le code.

### Analyse statique de l'infrastructure

`checkov` analyse les fichiers `.tf` à la recherche de mauvaises pratiques de
sécurité. Sur cette configuration : 25 contrôles réussis, 0 échec,
3 exceptions justifiées.

Deux constats ont été **corrigés** : blocage des clés SSH au niveau du projet
(`CKV_GCP_32`) et activation du démarrage vérifié / vTPM / surveillance
d'intégrité sur la VM (`CKV_GCP_39`).

Trois ont été **acceptés**, chacun avec sa raison inscrite dans le code sous
forme de commentaire `#checkov:skip=<ID>:<raison>` — de sorte qu'aucune
exception ne soit muette et que tout *nouveau* constat fasse échouer la CI :

| Constat | Raison de l'acceptation |
|---|---|
| `CKV_GCP_40` — VM avec IP publique | Nécessaire pour installer Docker et tirer l'image Postgres ; l'alternative (Cloud NAT) est facturée. Le port 5432 reste fermé à l'internet public. |
| `CKV_GCP_38` — disques sans clé client | Chiffrement au repos déjà assuré par des clés gérées par Google ; le CSEK imposerait d'en gérer le cycle de vie sans bénéfice réel ici. |
| `CKV_GCP_84` — registre sans clé client | Même raisonnement ; le contenu est du code applicatif public. |

Un piège mérite d'être signalé, car il rendait le scan **trompeur** : sans
l'option `--var-file`, checkov n'exécutait que 2 contrôles au lieu de 28. La
moitié des ressources est conditionnée par `var.manage_shared_infra`, dont la
valeur par défaut est `false` ; checkov les considérait donc comme non créées
et rendait un rapport vert. Un scan qui ne trouve rien n'est pas
nécessairement un scan qui prouve quelque chose.

---

## 7. Sécurité

Résumé des choix de sécurité appliqués (chacun détaillé dans les sections
précédentes) :

1. **Authentification keyless** (Workload Identity Federation) — aucune
   clé de service account à faire fuiter, tourner ou révoquer.
2. **Restriction du WIF à un seul repo** via `attribute-condition`.
3. **IAM à moindre privilège** pour le service account CI (rôles
   spécifiques, jamais `roles/editor`).
4. **Aucun secret en clair** dans le repo, l'image Docker ou les logs —
   tout transite par Secret Manager ou les secrets GitHub Actions.
5. **Base de données non exposée publiquement** — firewall limité au VPC
   interne et à la plage IAP (accès administrateur ponctuel uniquement).
6. **Client OAuth dédié**, en mode consentement « Testing » (liste
   explicite d'utilisateurs de test) plutôt qu'un client partagé avec un
   autre projet.
7. **State Terraform versionné** dans un bucket dédié, séparé de tout
   autre usage.

---

## 8. Retour d'expérience — incidents rencontrés

Cette section résume les incidents rencontrés pendant la mise en place et
comment chacun a été diagnostiqué et corrigé. Version complète et
chronologique dans [`pipeline-devops.md` §7](./pipeline-devops.md).

### 8.1 Propagation IAM après création du projet
**Symptôme** : `PERMISSION_DENIED` lors de la création du Workload
Identity Pool, alors que le compte a bien `roles/owner`.
**Cause** : latence de propagation IAM normale juste après
`gcloud projects create`.
**Résolution** : script de bootstrap idempotent, relancé après quelques
secondes.

### 8.2 Ordre du pipeline CI et Artifact Registry
**Symptôme** : `Artifact Registry API has not been used ... or it is
disabled` lors du `docker push`.
**Cause** : le job `build` s'exécutait avant que Terraform (job `deploy`)
n'active l'API et ne crée le repo.
**Résolution initiale** : ajout d'un job `prepare-registry` (`terraform apply
-target` ciblé sur les APIs et le dépôt) exécuté avant `build`.

**État actuel** : ce job a été retiré lors du passage à deux pipelines. Le
registre fait partie des ressources partagées, créées par le premier `apply`
de production — lequel relève de l'amorçage et se fait depuis un poste
local, après `bootstrap_ci.sh` (voir README). Faire porter cet amorçage par
la CI revenait à mêler deux préoccupations distinctes : créer
l'infrastructure une première fois, et la maintenir à chaque commit. Sur un
projet vierge, l'ordre reste donc contraint — il est simplement explicite et
documenté plutôt qu'implicite dans le pipeline.

### 8.3 Pénurie de stock `e2-micro`
**Symptôme** : `ZONE_RESOURCE_POOL_EXHAUSTED` sur `us-central1-a`, puis
`-b`, `-c`, `-f`.
**Cause** : indisponibilité réelle et transitoire du stock de VM
`e2-micro` sur ces zones précises (vérifié : ce n'était pas un problème de
quota — 200 CPUs disponibles, 0 utilisés).
**Résolution** : test de disponibilité sur plusieurs zones via `gcloud`,
déplacement de la VM vers `us-west1-b` (toujours éligible Always Free).

### 8.4 Rôle IAM insuffisant pour le binding public
**Symptôme** : `Permission 'run.services.setIamPolicy' denied`.
**Cause** : `roles/run.developer` permet de déployer des révisions mais
pas de poser une policy IAM (nécessaire pour `allUsers`/`roles/run.invoker`,
équivalent de `--allow-unauthenticated`).
**Résolution** : remplacement par `roles/run.admin`.

### 8.5 JSON du client OAuth corrompu par le shell
**Symptôme** : `JSONDecodeError` au runtime, `Internal Server Error` sur
`/auth/start`.
**Cause** : le secret `OAUTH_CLIENT_JSON`, interpolé directement dans
`-var="oauth_client_json=${{ secrets.OAUTH_CLIENT_JSON }}"`, contient des
guillemets qui cassent le parsing du shell — la valeur était tronquée
avant même d'atteindre Terraform.
**Résolution** : passage par des variables d'environnement `TF_VAR_*`,
lues nativement par Terraform sans repasser par un argument shell.

### 8.6 Réutilisation puis abandon du client OAuth partagé
**Contexte** : pour aller plus vite, le client OAuth du projet d'origine
avait d'abord été réutilisé tel quel.
**Problème identifié** : ce choix recréait un couplage entre les deux
projets (accès limité aux comptes ayant un rôle actif sur le projet
d'origine, gestion des redirect URIs à cheval sur deux projets) —
contraire à l'objectif d'isolation complète.
**Décision finale** : création d'un écran de consentement OAuth et d'un
client dédiés à `lifeai-devops`.

### 8.7 `redirect_uri_mismatch` puis `access_denied`
**Symptôme** : deux erreurs successives lors du premier test du nouveau
client OAuth.
**Cause** : attendu — l'URI de redirection doit être ajoutée
explicitement au client, puis le compte de test ajouté à la liste des
utilisateurs autorisés tant que l'écran de consentement est en mode
« Testing ».
**Résolution** : ajout des deux éléments manquants via la Console (aucune
API publique pour ces deux étapes — voir §10).

### 8.8 Deux défauts applicatifs révélés par les premiers tests
**Symptôme** : à leur toute première exécution, 34 tests passent et 2
échouent.
**Causes**, distinctes mais de forme identique :
- `activity_agent` renvoyait un score **négatif** (−1,8) sur des valeurs
  d'entrée négatives. Trois des quatre composantes du score n'étaient bornées
  que par le haut (`min(x, 1.0)`) ; la quatrième, `s_sedent`, était pourtant
  bien encadrée par `max(0, min(100, …))`.
- `nutrition_agent` levait une `ZeroDivisionError` lorsque l'objectif
  calorique valait 0 — atteignable, puisque ce champ est modifiable par
  `PUT /api/profile/{user_id}`. La ligne 102 se protégeait déjà de ce cas
  (`if cal_goal > 0 else 1.0`), mais deux divisions plus loin ne l'étaient
  pas.

Dans les deux cas, le garde-fou avait été posé à un endroit et oublié
ailleurs — le motif classique de la correction partielle, précisément ce
qu'une suite de tests détecte et qu'une relecture manuelle laisse passer.

**Résolution** : bornes appliquées aux trois composantes manquantes, et
pourcentage calculé une seule fois derrière la garde existante. Non-régression
vérifiée : sur les profils normaux, les scores sont inchangés au centième
près, les corrections ne modifiant que le traitement des cas aberrants.

### 8.9 Une modification anodine allait détruire la base de production
**Symptôme** : lors de la séparation dev/prod, le plan annonce
`google_compute_instance.lifeai_db must be replaced`.
**Cause** : pour créer automatiquement la base de dev, la création des bases
avait été ajoutée au script de démarrage de la VM. Or
`metadata_startup_script` est un attribut **ForceNew** dans le provider
Google : toute modification entraîne la destruction et la recréation de
l'instance — donc de son disque de démarrage, donc de toutes les bases. Un
remplacement de secret en cascade suivait d'ailleurs, la nouvelle IP de la VM
changeant le DSN.
**Résolution** : script de démarrage laissé strictement intact, avertissement
inscrit à côté du bloc concerné, et création de la base de dev traitée comme
une opération ponctuelle par tunnel IAP (documentée dans le README).

C'est l'illustration la plus nette de l'intérêt du `plan` : la modification
paraissait anodine, sa conséquence était la perte des données de production.

---

## 9. Coûts

| Ressource | Coût |
|---|---|
| Cloud Run | Gratuit à l'usage nul (scale-to-zero) ; facturé au CPU/mémoire/requêtes au-delà du free tier mensuel |
| VM `e2-micro` (`us-west1-b`) | **Always Free** (1 instance e2-micro/mois dans `us-west1`, `us-central1` ou `us-east1`) |
| Disque persistant 30 Go standard | Inclus dans le quota Always Free (30 Go/mois) |
| Artifact Registry | Quelques centaines de Mo d'images — coût marginal |
| Secret Manager | 6 secrets, quelques accès/jour — largement sous le free tier (10 000 accès/mois gratuits) |
| Cloud Scheduler | 1 job — le free tier couvre 3 jobs gratuits/mois |
| Cloud Storage (state Terraform) | Quelques Ko de state — coût négligeable |
| GitHub Actions | Gratuit pour un repo public (ou inclus dans le quota mensuel d'un repo privé) |

**Coût mensuel estimé : proche de 0 €**, tant que l'usage reste dans les
quotas Always Free et que le trafic Cloud Run reste faible (démo/tests).

---

## 10. Limites actuelles et pistes d'amélioration

| Limite actuelle | Piste d'amélioration |
|---|---|
| Postgres sur VM Docker, sans sauvegarde automatique — et **partagé entre dev et prod** : une panne de la VM affecte les deux environnements | Migration vers Cloud SQL managé (sauvegardes et bascule automatiques, contre un coût récurrent) ; à défaut, un instantané de disque planifié |
| Pas d'alerte de budget configurée | Ajouter une ressource `google_billing_budget` avec seuils d'alerte |
| Rôles IAM du compte de service CI encore larges (administrateur par service) | Resserrer via des rôles personnalisés minimalistes si le projet grandit |
| Couverture de test limitée aux agents de scoring — ni les routes FastAPI, ni la couche base de données, ni le pipeline ADK ne sont testés | Ajouter des tests d'intégration sur l'API (`httpx` + base éphémère) et des doublures pour les appels LLM |
| `checkov` couvre mal `google_cloud_run_v2_service` : ses politiques ciblent surtout la v1 des ressources | Compléter par `trivy config` ou des politiques OPA/Rego maison sur les points non couverts |
| Écran de consentement OAuth en mode *Testing* (liste d'utilisateurs limitée) | Publier l'application si un usage au-delà des testeurs déclarés devient nécessaire |
| Le déploiement dev reste automatique et sans revue — seule la production passe par une pull request | Acceptable par construction : dev sert justement d'environnement de validation avant fusion |
| La production reçoit une image **reconstruite**, pas l'artefact exact validé en dev (voir §6.3) | Passer à une fusion en rebase, qui conserve le SHA et permet une promotion stricte |
| Pas d'alerte sur échec du job Cloud Scheduler quotidien | Notification (courriel ou Slack) via une politique d'alerte Cloud Monitoring |
| Aucun retour arrière automatique : un déploiement dégradé se corrige en promouvant manuellement le commit précédent | Exploiter la répartition du trafic Cloud Run (déploiement progressif, bascule automatique sur erreurs) |

---

## 11. Conclusion

Ce sous-projet transforme un déploiement manuel (scripts bash + commandes
`gcloud` impératives) en une chaîne DevOps reproductible : infrastructure
décrite intégralement en Terraform, environnements dev et production séparés
par des states distincts et par des branches, portes de qualité automatiques
(formatage, lint, tests unitaires, analyse de sécurité), passage en production
conditionné à une pull request revue, authentification sans clé, et secrets
jamais en clair.

Les incidents rencontrés ont tous une cause identifiée et une correction
versionnée : la chaîne reste reproductible pour quiconque relance
`bootstrap/bootstrap_ci.sh` puis pousse sur `main`.

Trois d'entre eux résument bien ce que ce travail a apporté, au-delà de
l'automatisation elle-même.

Les **tests** ont trouvé deux bugs applicatifs à leur première exécution — un
score négatif et un plantage sur division par zéro — que des mois d'usage
manuel n'avaient pas révélés.

Le **`plan`** a intercepté une modification en apparence anodine du script de
démarrage de la VM, dont la conséquence réelle était la destruction de la base
de production.

Le **scan de sécurité** a d'abord menti : il annonçait « aucun problème » en
n'analysant que 2 ressources sur l'ensemble. Un outil qui ne trouve rien ne
prouve rien tant qu'on n'a pas vérifié qu'il a réellement regardé.

C'est peut-être l'enseignement principal : l'automatisation ne dispense pas de
vérifier ce que les outils font réellement, elle rend simplement cette
vérification systématique plutôt qu'occasionnelle.

---

## 12. Annexes

- Diagramme d'architecture : [`architecture-devops.drawio`](./architecture-devops.drawio) — 2 onglets, à ouvrir sur [app.diagrams.net](https://app.diagrams.net)
  - *1. Application & runtime* — le contenu du conteneur déployé et ses connexions
  - *2. CI/CD & Infrastructure as Code* — la chaîne qui l'amène en production
- Documentation pas-à-pas complète : [`pipeline-devops.md`](./pipeline-devops.md)
- Repo : https://github.com/Anis-adjaoud/lifeai-devops
- Projet GCP : `lifeai-devops`
- Projet d'origine (application) : https://github.com/Sara-Ammi/Projet-Annuel-ESGI-4IABD2

### Glossaire

| Terme | Définition |
|---|---|
| **IaC** (Infrastructure as Code) | Décrire l'infrastructure sous forme de code déclaratif plutôt que de commandes manuelles |
| **State Terraform** | Fichier (ici distant, sur GCS) qui associe chaque ressource déclarée à son identifiant réel dans le cloud |
| **WIF** (Workload Identity Federation) | Mécanisme d'authentification fédérée permettant à une identité externe (ici GitHub Actions, via OIDC) d'obtenir un accès temporaire à GCP sans clé stockée |
| **Scale-to-zero** | Capacité d'un service (ici Cloud Run) à réduire son nombre d'instances à 0 en l'absence de trafic, sans coût associé |
| **Direct VPC egress** | Fonctionnalité Cloud Run permettant d'atteindre des ressources privées d'un VPC sans connecteur serverless séparé |
| **Always Free** | Niveau gratuit permanent de certains services GCP (ex. 1 VM e2-micro/mois), par opposition au crédit d'essai limité dans le temps |
