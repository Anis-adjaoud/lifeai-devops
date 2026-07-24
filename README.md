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
├── requirements.txt
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
├── terraform/                      # Toute l'infra GCP (VM, secrets, Cloud Run, scheduler...)
├── bootstrap/bootstrap_ci.sh       # Bootstrap one-shot : projet GCP + WIF + service account CI
└── .github/workflows/deploy.yml    # CI/CD : build image → terraform apply
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

| Composant | Service GCP | Géré par |
|---|---|---|
| Backend FastAPI + agents ADK + frontend React | Cloud Run (scale-to-zero, `us-central1`) | Terraform |
| PostgreSQL | VM Compute Engine `e2-micro` (Always Free) + Docker, VPC interne uniquement | Terraform |
| Secrets (DSN Postgres, Twilio, OAuth, clés scheduler/session) | Secret Manager | Terraform |
| Sync quotidienne Google Fit | Cloud Scheduler → `POST /internal/sync-all` | Terraform |
| Images Docker | Artifact Registry | Terraform (repo) + CI (build/push) |
| Build & déploiement | GitHub Actions | — |

Le mot de passe Postgres et les clés `SCHEDULER_SECRET`/`SESSION_SECRET` sont
générés aléatoirement par Terraform (`random_password`/`random_id`) — jamais
en clair dans le repo. Les credentials Twilio et le client OAuth Google sont
fournis via des secrets GitHub Actions, jamais committés.

### Pipeline CI/CD

À chaque push sur `main` (voir `.github/workflows/deploy.yml`) :

1. **build** — build l'image Docker (backend + frontend) et la pousse sur Artifact Registry, taggée avec le SHA du commit + `latest`. Cache de layers via GitHub Actions (`docker/build-push-action`, `type=gha`).
2. **deploy** — `terraform apply` (dans `terraform/`) crée/met à jour toute l'infra avec la nouvelle image. State distant dans le bucket GCS `lifeai-devops-tfstate`.

Auth GCP **sans clé de service account** : Workload Identity Federation — le
repo GitHub s'authentifie directement via OIDC auprès du service account
`github-actions-deployer`.

### Bootstrap initial (une seule fois)

```bash
./bootstrap/bootstrap_ci.sh
```

Crée le projet GCP `lifeai-devops`, le lie au compte de facturation, active
les APIs de base, crée le bucket de state Terraform, le Workload Identity
Pool/Provider et le service account `github-actions-deployer` (rôles
granulaires : `run.developer`, `artifactregistry.admin`, `compute.admin`,
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

Une fois les secrets renseignés, tout push sur `main` déploie automatiquement.

### Déploiement / plan manuel (local)

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars   # puis compléter les valeurs sensibles
terraform init
terraform plan
terraform apply
```

### Premier déploiement

Ajouter l'URL Cloud Run (sortie `service_url` de Terraform, au format
`https://lifeai-api-<project_number>.us-central1.run.app`) + `/auth/callback`
aux *Authorized redirect URIs* du client OAuth existant, dans **GCP Console →
APIs & Services → Identifiants** (projet d'origine, le client OAuth est
réutilisé tel quel — un client OAuth n'est pas lié à un seul projet Cloud
Run).

---

## Projet d'origine

Ce repo dérive de [Sara-Ammi/Projet-Annuel-ESGI-4IABD2](https://github.com/Sara-Ammi/Projet-Annuel-ESGI-4IABD2)
(ESGI 4IABD2 — Projet Annuel), qui reste la référence pour l'app elle-même.
