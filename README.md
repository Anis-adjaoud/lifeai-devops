# LifeAI — Coach de Santé IA (pipeline DevOps)

Plateforme de coaching santé personnalisé propulsée par **Google ADK** et **Gemini 2.5 Flash**.
Elle synchronise vos données Google Fit, analyse 4 domaines de santé via une architecture multi-agents, et expose un dashboard web + chat IA conversationnel.

> Ce repo est une instance **isolée** de [LifeAI](https://github.com/Sara-Ammi/Projet-Annuel-ESGI-4IABD2)
> (projet annuel ESGI 4IABD2), dédiée à l'expérimentation d'un pipeline DevOps
> complet (**Terraform + GitHub Actions**) sur un projet GCP et une base de
> données séparés — aucun déploiement ici ne touche à l'infra du projet
> scolaire d'origine.

---

## Stack technique

| Couche | Technologie |
|---|---|
| LLM | Gemini 2.5 Flash (via Google ADK / litellm) |
| Orchestration agents | Google ADK (`LlmAgent`, `AgentTool`, `Runner`) |
| Backend API | FastAPI (Python) |
| Base de données | PostgreSQL 16 (Docker) |
| Frontend | React 18 + Vite 4.4 + Recharts |
| Source de données | Google Fit API (OAuth2 PKCE) |
| Base nutritionnelle | CIQUAL 2025 (base officielle française, 3 484 aliments) |
| Recherche sémantique | `sentence-transformers` — `paraphrase-multilingual-MiniLM-L12-v2` |
| Notifications | Twilio WhatsApp |
| Scheduler | APScheduler (sync Google Fit quotidienne) |
| Infra | Terraform (GCP) + GitHub Actions (CI/CD, auth keyless via Workload Identity Federation) |

---

## Architecture applicative

```
┌─────────────────────────────────────────────────────────────┐
│                     Frontend React / Vite                    │
│          Dashboard · Chat IA · Auth Google OAuth            │
└───────────────────┬─────────────────────────────────────────┘
                    │ HTTP (proxy Vite → :8000)
┌───────────────────▼─────────────────────────────────────────┐
│                     FastAPI  (api.py)                        │
│   /auth/start  /api/users  /api/chat  /api/analyze  ...     │
└──────┬────────────────────────────────────────┬─────────────┘
       │                                        │
┌──────▼──────────────────────┐    ┌────────────▼────────────┐
│   ADK Pipeline (pipeline.py) │    │  Google Fit API          │
│   chief_agent (LlmAgent)     │    │  (agentic/google_fit.py) │
│   ├─ activity_agent          │    └─────────────────────────┘
│   ├─ sleep_agent             │
│   ├─ nutrition_agent         │    ┌─────────────────────────┐
│   ├─ risk_agent              │    │  Twilio WhatsApp         │
│   ├─ alert_agent             │    │  Rapports + alertes      │
│   ├─ report_agent            │    └─────────────────────────┘
│   └─ weekly_coach_agent      │
└──────────────────────────────┘
       │
┌──────▼──────────────────────┐
│   PostgreSQL  (Docker)       │
│   users · sessions · profil │
│   patterns · health_metrics │
│   conversations · messages  │
└─────────────────────────────┘
```

### Agents spécialisés

| Agent | Rôle |
|---|---|
| `chief_agent` | Point d'entrée. Coordonne les autres agents, produit la synthèse narrative, déclenche les envois |
| `activity_agent` | Score activité (pas, minutes actives, séances, sédentarité) |
| `sleep_agent` | Score sommeil (durée, efficacité, cycles profond/REM, régularité) |
| `nutrition_agent` | Score nutrition (calories, macros, hydratation, fibres) + recherche CIQUAL officielle |
| `risk_agent` | Score risque burn-out (stress, HRV, FC repos, tendances croisées) |
| `alert_agent` | Envoie une alerte WhatsApp si score Critique |
| `report_agent` | Envoie le rapport complet par WhatsApp + génère le PDF |
| `weekly_coach_agent` | Bilan hebdomadaire WhatsApp personnalisé |

---

## Installation locale

### Prérequis

- Python 3.11+
- Node.js 18+
- Docker Desktop

### 1. Cloner et créer l'environnement Python

```bash
git clone https://github.com/Anis-adjaoud/lifeai-devops.git
cd lifeai-devops

python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux / macOS

pip install -r requirements.txt
pip install fastapi uvicorn[standard]
pip install sentence-transformers xlrd
```

> **Première utilisation CIQUAL** : au premier démarrage du serveur, le modèle d'embeddings (`~470 Mo`) est téléchargé automatiquement depuis HuggingFace et les vecteurs de la base CIQUAL sont calculés (~10 s). Le résultat est mis en cache dans `data/.cache_embeddings/` — les démarrages suivants sont instantanés.

### 2. Installer le frontend

```bash
cd frontend_web
npm install
cd ..
```

---

## Configuration locale

Crée un fichier `.env` à la racine :

```env
# LLM — Gemini via Google AI Studio (gratuit)
GEMINI_API_KEY=AIza...

# PostgreSQL (correspond au docker-compose.yml)
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=lifeai
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres

# Google OAuth (Google Cloud Console)
GOOGLE_CLIENT_ID=...apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=...
GOOGLE_REDIRECT_URI=http://localhost:8080

# Twilio WhatsApp (optionnel)
TWILIO_ACCOUNT_SID=AC...
TWILIO_AUTH_TOKEN=...
TWILIO_WHATSAPP_FROM=whatsapp:+14155238886
```

### Clé Gemini

1. Aller sur [aistudio.google.com](https://aistudio.google.com) → *Get API key*
2. Copier la clé dans `GEMINI_API_KEY`

### Google OAuth (Google Fit)

1. [console.cloud.google.com](https://console.cloud.google.com) → créer un projet
2. Activer **Fitness API** et **People API**
3. Créer des identifiants OAuth 2.0 → Application de bureau
4. Ajouter `http://localhost:8080` dans les URI de redirection autorisés
5. Copier `client_id` et `client_secret` dans `.env`

### Twilio WhatsApp (optionnel)

Créer un compte [twilio.com](https://twilio.com) et rejoindre le sandbox WhatsApp.
Sans configuration, les notifications WhatsApp sont désactivées silencieusement.

> **Sandbox opt-in obligatoire** : pour recevoir des messages depuis le sandbox Twilio, chaque numéro destinataire doit d'abord envoyer le message `join <mot-clé>` au numéro `+1 415 523 8886` depuis WhatsApp. Le mot-clé est visible dans la console Twilio sous *Messaging > Try it out > Send a WhatsApp message*.

---

## Démarrage local

Lancer **3 processus** dans des terminaux séparés :

```bash
# Terminal 1 — Base de données
docker-compose up -d

# Terminal 2 — Backend API
uvicorn api:app --reload --port 8000

# Terminal 3 — Frontend
cd frontend_web && npm run dev
```

L'application est accessible sur **http://localhost:5173**

---

## Structure du projet

```
├── api.py                          # FastAPI — routes REST + OAuth flow
├── docker-compose.yml              # PostgreSQL 16 (dev local)
├── Dockerfile                      # Build image prod (backend + frontend)
├── requirements.txt                # Dépendances applicatives (image Docker)
├── requirements-dev.txt            # Dépendances de test / CI uniquement
├── pytest.ini
├── seed_demo_profiles.py           # Génère les profils démo (Lucas Excellent, Emma Critique)
│
├── agentic/
│   ├── agents_adk/                 # Pipeline principal (Google ADK)
│   ├── agents/                     # Agents métier (calcul des scores, sans LLM)
│   ├── google_fit.py               # Client Google Fit API (OAuth PKCE + fetch données)
│   └── scheduler.py                # APScheduler — sync Google Fit quotidienne
│
├── nutrition/                      # Recherche CIQUAL (hybride textuel + sémantique)
├── frontend_web/                   # Application React 18 + Vite
├── data/foods_table.xlsx           # Base nutritionnelle officielle française (CIQUAL 2025)
├── output/models/                  # Modèles XGBoost entraînés (LifeSnaps), embarqués dans l'image
│
├── tests/                          # Tests unitaires (agents de scoring, Nutri-Score)
│
├── terraform/                      # Toute l'infra GCP (VM, secrets, Cloud Run, scheduler...)
│   ├── locals.tf                   # Nommage et réglages dérivés de var.environment
│   └── env/{dev,prod}.tfvars       # Variables propres à chaque environnement
│
├── bootstrap/
│   ├── bootstrap_ci.sh             # One-shot : projet GCP + state + WIF + service account CI
│   └── migrate_state_to_envs.sh    # One-shot : migration vers les states par environnement
│
├── .github/workflows/
│   ├── ci.yml                      # Qualité + plan Terraform (pull request vers main)
│   ├── cd-dev.yml                  # Build + déploiement dev (push sur develop)
│   └── cd-prod.yml                 # Promotion en production (approbation requise)
│
└── docs/                           # Dossier technique, schéma d'architecture, slides
```

---

## Profils de démonstration

Deux profils préchargés permettent de tester l'application sans compte Google Fit :

| Profil | Score | Niveau | Description |
|---|---|---|---|
| **Lucas Martin** (`lucas.martin@lifeai.demo`) | ~92/100 | Excellent | 9 500 pas/jour, 7h30 de sommeil, alimentation équilibrée, FC repos 58 bpm |
| **Emma Rousseau** (`emma.rousseau@lifeai.demo`) | ~31/100 | Critique | 1 200 pas/jour, 4h de sommeil, alimentation très déséquilibrée, FC repos 94 bpm |

Pour régénérer ou réinitialiser ces profils :

```bash
python seed_demo_profiles.py
```

---

## Base CIQUAL — Nutrition officielle

Le `nutrition_agent` interroge la **base CIQUAL 2025** (Institut national de la recherche agronomique, 3 484 aliments) pour répondre aux questions sur la composition des aliments.

**Fonctionnement :**
1. L'utilisateur pose une question (ex: « combien de calories dans un avocat ? »)
2. L'agent appelle `rechercher_aliment_ciqual_tool("avocat")`
3. La recherche hybride (textuelle + sémantique) trouve le meilleur match dans CIQUAL
4. Si score de confiance ≥ 0,8 : réponse basée sur les valeurs officielles, source explicitement citée
5. Si score < 0,8 : réponse depuis la mémoire du LLM, avec indication claire que ce n'est pas CIQUAL

Le fichier `data/foods_table.xlsx` est requis. Les embeddings sont calculés une fois et mis en cache dans `data/.cache_embeddings/`.

---

## Changer de modèle LLM

Éditer `agentic/agents_adk/model_config.py` — une seule ligne à modifier :

```python
MODEL = "gemini-2.5-flash"                                    # Google (défaut)
# MODEL = LiteLlm(model="groq/llama-3.1-8b-instant")         # Groq (gratuit, 6k TPM)
# MODEL = LiteLlm(model="groq/gemma2-9b-it")                 # Groq (gratuit, 15k TPM)
# MODEL = LiteLlm(model="anthropic/claude-haiku-4-5-20251001") # Anthropic
```

---

## Endpoints API

| Méthode | Route | Description |
|---|---|---|
| GET | `/auth/start` | Lance le flow OAuth Google Fit (popup) |
| GET | `/api/users` | Liste les utilisateurs enregistrés |
| GET | `/api/profile/{user_id}` | Profil utilisateur |
| GET | `/api/sessions/{user_id}` | Historique des analyses |
| GET | `/api/metrics/{user_id}` | Métriques brutes Google Fit |
| GET | `/api/trend/{user_id}` | Tendance des scores |
| GET | `/api/patterns/{user_id}` | Patterns de santé détectés |
| POST | `/api/analyze/{user_id}` | Lance une analyse complète (Google Fit → agents → WhatsApp) |
| POST | `/api/chat/{user_id}` | Envoie un message au chief_agent |
| GET | `/api/conversations/{user_id}` | Liste les conversations |
| DELETE | `/api/conversations/{conv_id}` | Supprime une conversation |

---

## Déploiement — Terraform + GitHub Actions

Infra 100% as-code, sur un projet GCP dédié (`lifeai-devops`, isolé du projet
scolaire d'origine) :

| Composant | Service GCP | Portée |
|---|---|---|
| Backend FastAPI + agents ADK + frontend React | Cloud Run (scale-to-zero, `us-central1`) | par environnement |
| Secrets (DSN Postgres, Twilio, OAuth, clés scheduler/session) | Secret Manager | par environnement |
| Sync quotidienne Google Fit | Cloud Scheduler → `POST /internal/sync-all` | prod uniquement |
| PostgreSQL | VM Compute Engine `e2-micro` (Always Free), VPC interne uniquement | partagé (une base par environnement) |
| Images Docker | Artifact Registry | partagé |
| Règles firewall, activation des APIs | VPC / Service Usage | partagé |

Tout est géré par Terraform, à l'exception du build d'image (GitHub Actions)
et des prérequis d'amorçage (`bootstrap/bootstrap_ci.sh`).

Le mot de passe Postgres et les clés `SCHEDULER_SECRET`/`SESSION_SECRET` sont
générés aléatoirement par Terraform (`random_password`/`random_id`) — jamais
en clair dans le repo. Les credentials Twilio et le client OAuth Google sont
fournis via des secrets GitHub Actions, jamais committés.

### Environnements

Deux environnements coexistent dans le même projet GCP, avec des **states
Terraform séparés** : un `apply` sur dev ne peut donc pas modifier la prod.

| | dev | prod |
|---|---|---|
| Service Cloud Run | `lifeai-api-dev` | `lifeai-api` |
| Secrets | `lifeai-dev-*` | `lifeai-*` |
| Base de données | `lifeai_dev` | `lifeai` |
| State | `gs://lifeai-devops-tfstate/env/dev` | `.../env/prod` |
| Instances max | 1 | 3 |
| Sync Google Fit quotidienne | désactivée | activée |
| Fichier de variables | `terraform/env/dev.tfvars` | `terraform/env/prod.tfvars` |

La production ne porte pas de suffixe : ses ressources sont antérieures à la
séparation, et les renommer détruirait le service Cloud Run — dont l'URL est
déclarée dans le client OAuth Google.

Les deux environnements partagent la **même VM Postgres** (le palier Always
Free ne couvre qu'une `e2-micro` par compte de facturation) mais chacun a sa
propre base. Prod possède les ressources partagées — APIs, Artifact Registry,
règles firewall, VM — via `manage_shared_infra = true` ; dev les lit par des
data sources. Ce drapeau ne doit être activé que pour un seul environnement,
sinon le second échouerait sur des ressources « déjà existantes ».

### Modèle de branches

Deux branches, chacune liée à un environnement :

| Branche | Environnement | Comment on y arrive |
|---|---|---|
| `develop` | dev | push direct — c'est la branche de travail |
| `main` | production | **uniquement par pull request** validée |

```
   push                    pull request                merge
develop ──────▶ DEV        develop → main ──────▶  main ──────▶ PRODUCTION
                           revue + plan Terraform
```

`main` reflète donc l'état réel de la production : ce qui y est fusionné est
déployé.

### Pipelines CI/CD

Trois pipelines, séparés par la **revue de pull request**.

**1. `ci.yml` — qualité et plan Terraform**

Déclenché par toute pull request visant `main` (et manuellement via
`workflow_dispatch`).

| Job | Rôle |
|---|---|
| `lint` | `terraform fmt -check`, `terraform validate`, `tflint` |
| `test` | `pytest` — 36 tests sur les agents de scoring et le Nutri-Score |
| `security` | `checkov` sur les fichiers `.tf` |
| `plan` | *(pull request uniquement)* `terraform plan` publié en commentaire de la PR — **rien n'est appliqué** |

Le pipeline s'arrête donc au plan : il montre ce que la fusion changera en
production, sans rien modifier.

**2. `cd-dev.yml` — déploiement dev**

Déclenché par un push sur `develop` — la branche de travail, sans revue de PR.

| Job | Rôle |
|---|---|
| `verifier` | Rejoue lint, tests et scan de sécurité (`checkov` sur `env/dev.tfvars`) |
| `build` | Image Docker taggée par SHA, poussée sur Artifact Registry |
| `deploy-dev` | `terraform apply` sur dev, puis vérification HTTP |

**3. `cd-prod.yml` — déploiement production**

Déclenché par la fusion d'une pull request dans `main`.

| Job | Rôle |
|---|---|
| `verifier` | Rejoue tests, lint et scan de sécurité sur `main` |
| `build` | Reconstruit l'image depuis le commit de `main` |
| `deploy-prod` | `terraform apply` sur prod, puis vérification HTTP |

> **Reconstruction plutôt que promotion.** La fusion crée un nouveau SHA :
> l'image construite depuis `develop` ne porte pas le même identifiant que le
> commit de `main`. La production reçoit donc une image reconstruite, et non
> l'artefact au bit près qui a tourné en dev. C'est le compromis retenu pour
> la lisibilité ; le cache de layers rend les deux builds très proches.
> L'alternative — fusion en rebase, qui conserve le SHA — permettrait une
> promotion stricte.

Auth GCP **sans clé de service account** : Workload Identity Federation — le
dépôt s'authentifie via OIDC auprès du service account
`github-actions-deployer`.

### Configuration requise côté GitHub

La revue de pull request est le garde-fou avant la production. Elle n'a
d'effet que si `main` est protégée : sans cela, un push direct sur `main`
déploierait en production sans aucune revue.

**Settings → Branches → Add branch protection rule**, motif `main` :

- ☑ *Require a pull request before merging* — au minimum
- ☑ *Require status checks to pass* → sélectionner `lint`, `test`,
  `security`, `plan`
- ☑ *Do not allow bypassing the above settings* (sinon la règle ne s'applique
  pas à l'administrateur du dépôt, c'est-à-dire à toi)

Créer également les environnements **Settings → Environments** : `development`
et `production`. Ils ne sont pas obligatoires, mais font apparaître les
déploiements et leurs URL dans l'onglet Deployments.

> Ajouter *Required reviewers* sur l'environnement `production` poserait un
> second garde-fou, au moment du déploiement cette fois. Redondant pour un
> projet solo, où la revue de PR suffit.

### Bootstrap initial (une seule fois)

```bash
./bootstrap/bootstrap_ci.sh
```

Crée le projet GCP `lifeai-devops`, le lie au compte de facturation, active
les APIs de base, crée le bucket de state Terraform, le Workload Identity
Pool/Provider et le service account `github-actions-deployer` (rôles
granulaires : `run.admin`, `artifactregistry.admin`, `compute.admin`,
`secretmanager.admin`, `cloudscheduler.admin`, `serviceusage.serviceUsageAdmin`,
`resourcemanager.projectIamAdmin`, `iam.serviceAccountUser`).

À la fin, le script affiche les valeurs à renseigner dans **GitHub → Settings
→ Secrets and variables → Actions** du repo :

| Secret | Source |
|---|---|
| `GCP_WORKLOAD_IDENTITY_PROVIDER` | Sortie du script |
| `GCP_SERVICE_ACCOUNT` | Sortie du script |
| `GCP_PROJECT_ID` | Sortie du script (`lifeai-devops`) |
| `TWILIO_ACCOUNT_SID` | Console Twilio |
| `TWILIO_AUTH_TOKEN` | Console Twilio |
| `OAUTH_CLIENT_JSON` | Contenu complet du `client_secret_*.json` téléchargé depuis GCP Console → APIs & Services → Identifiants |

**Puis, une seule fois, le premier déploiement de production depuis un poste
local.** Il crée les ressources partagées — dont l'Artifact Registry, sans
lequel la CI ne pourrait pas pousser d'image :

```bash
cd terraform
terraform init -reconfigure -backend-config="prefix=env/prod"
terraform apply -var-file=env/prod.tfvars -var="image_tag=latest"
```

Créer ensuite la base de l'environnement dev (voir plus bas), et déclarer les
environnements GitHub (section précédente).

Une fois ces étapes faites, le cycle normal s'applique : on travaille sur
`develop` (déploiement dev automatique), puis on ouvre une pull request vers
`main` pour passer en production.

### Tests

```bash
pip install -r requirements-dev.txt
pytest
```

36 tests couvrant les quatre agents de scoring et le calcul du Nutri-Score.
Ce sont des fonctions pures : aucun service externe, aucune base, aucun appel
LLM — la suite s'exécute en moins d'une seconde.

`requirements-dev.txt` est volontairement séparé de `requirements.txt` : ce
dernier embarque `torch` et `sentence-transformers` (~2 Go), inutiles aux
tests unitaires et qui feraient passer le job de quelques secondes à plusieurs
minutes.

### Plan / apply manuel (local)

Le préfixe de state **doit** être passé à l'`init` : le bloc `backend`
n'accepte pas de variable, et chaque environnement possède son propre state.

```bash
cd terraform

# Dev
terraform init -reconfigure -backend-config="prefix=env/dev"
terraform plan -var-file=env/dev.tfvars

# Prod
terraform init -reconfigure -backend-config="prefix=env/prod"
terraform plan -var-file=env/prod.tfvars
```

Les trois variables sensibles (`twilio_account_sid`, `twilio_auth_token`,
`oauth_client_json`) n'ont pas de valeur par défaut. Les fournir par
l'environnement plutôt qu'en ligne de commande — le JSON OAuth contient des
guillemets qui cassent le découpage du shell dans un `-var="…"` :

```bash
export TF_VAR_twilio_account_sid=$(gcloud secrets versions access latest --secret=lifeai-twilio-account-sid)
export TF_VAR_twilio_auth_token=$(gcloud secrets versions access latest --secret=lifeai-twilio-auth-token)
export TF_VAR_oauth_client_json=$(gcloud secrets versions access latest --secret=lifeai-oauth-client-json)
```

### Scan de sécurité local

```bash
pip install checkov
checkov -d terraform --var-file terraform/env/prod.tfvars
```

Le `--var-file` est **indispensable**. La moitié des ressources est
conditionnée par `var.manage_shared_infra`, dont la valeur par défaut est
`false` : sans ce fichier, checkov les considère comme non créées et n'exécute
que 2 contrôles au lieu de 28 — en rendant un rapport vert trompeur.

Les constats acceptés sont justifiés par des commentaires
`#checkov:skip=<ID>:<raison>` dans les fichiers `.tf`, pour qu'aucune
exception ne soit muette.

### Créer la base d'un nouvel environnement

Le script de démarrage de la VM ne crée que la base `lifeai`. Il ne faut
**pas** le modifier pour en ajouter d'autres : `metadata_startup_script` est
un attribut *ForceNew*, donc toute modification détruit la VM, son disque, et
donc toutes les bases.

La base d'un nouvel environnement se crée une fois, par un tunnel IAP :

```bash
gcloud compute start-iap-tunnel lifeai-db 5432 \
  --local-host-port=localhost:5433 --zone=us-west1-b &

MDP=$(gcloud secrets versions access latest --secret=lifeai-database-url \
      | sed -E 's#postgresql://postgres:([^@]+)@.*#\1#')
psql "postgresql://postgres:${MDP}@localhost:5433/lifeai" \
     -c 'CREATE DATABASE lifeai_dev'
```

### Premier déploiement

Ajouter l'URL Cloud Run (sortie `service_url` de Terraform, au format
`https://lifeai-api-<numéro_de_projet>.us-central1.run.app`) suivie de
`/auth/callback` aux *Authorized redirect URIs* du client OAuth, dans
**GCP Console → APIs & Services → Identifiants**. Chaque environnement ayant
son propre service, dev et prod ont chacun leur URI de redirection à déclarer.

Tant que l'écran de consentement est en mode *Testing*, chaque compte devant
se connecter doit figurer dans la liste des utilisateurs de test.

---

## Projet d'origine

Ce repo dérive de [Sara-Ammi/Projet-Annuel-ESGI-4IABD2](https://github.com/Sara-Ammi/Projet-Annuel-ESGI-4IABD2)
(ESGI 4IABD2 — Projet Annuel), qui reste la référence pour l'app elle-même.
