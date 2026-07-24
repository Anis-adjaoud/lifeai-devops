PYTHON := python
PIP    := pip
APP    := app.py
PORT   := 8501
CSV    := data/processed.csv

.PHONY: install run preprocess train demo lint clean help

## Affiche cette aide
help:
	@grep -E '^##' Makefile | sed 's/^## //'

## Installe les dépendances
install:
	$(PIP) install -r requirements.txt

## Lance l'interface Streamlit
run:
	streamlit run $(APP) --server.port $(PORT)

## Prétraitement : fitness_tracker.csv → processed.csv + features_ml.csv
preprocess:
	$(PYTHON) data/preprocess.py

## Entraîne les 3 modèles ML (mood, burnout, health_score)
train:
	$(PYTHON) train_models/train.py

## Lance l'analyse CLI (dernier utilisateur, dernière date)
analyze:
	$(PYTHON) main.py

## Lance l'analyse CLI pour un utilisateur spécifique
## Usage : make analyze-user USER=1042
analyze-user:
	$(PYTHON) main.py --user $(USER)

## Lance les scénarios de démo (sans CSV)
demo:
	$(PYTHON) agents/demo.py

## Vérifie la syntaxe de tous les fichiers Python
lint:
	$(PYTHON) -m py_compile app.py main.py data/adapter.py agents/*.py && echo "✓ Aucune erreur de syntaxe"

## Supprime les fichiers générés (mémoire, cache Python)
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	rm -f memory/user_*_memory.json 2>/dev/null || true
	@echo "✓ Nettoyage terminé"

## Repart de zéro : preprocess + train + run
setup: preprocess train run
