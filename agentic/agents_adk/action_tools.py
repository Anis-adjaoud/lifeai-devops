"""
LifeAI — Outils des agents d'action.
WhatsApp (Twilio), génération PDF (reportlab), résumé hebdomadaire (DB).
"""

import os
from datetime import datetime
from pathlib import Path

from . import database as db
from .tools import _uid


# ── WhatsApp (Twilio) ─────────────────────────────────────────────────────────

def send_whatsapp(to_phone: str, message: str) -> str:
    """
    Envoie un message WhatsApp via Twilio.

    Args:
        to_phone: Numéro du destinataire au format international sans '+' (ex: "33612345678").
        message: Texte du message (supporte *gras* et _italique_ WhatsApp).

    Returns:
        Confirmation ou message d'erreur.
    """
    account_sid = os.environ.get("TWILIO_ACCOUNT_SID")
    auth_token  = os.environ.get("TWILIO_AUTH_TOKEN")
    from_number = os.environ.get("TWILIO_WHATSAPP_FROM")

    if not account_sid or not auth_token:
        return "WhatsApp non envoyé : TWILIO_ACCOUNT_SID et TWILIO_AUTH_TOKEN manquants dans .env"

    try:
        from twilio.rest import Client
        client = Client(account_sid, auth_token)
        msg = client.messages.create(
            from_=from_number,
            body=message,
            to=f"whatsapp:+{to_phone.lstrip('+')}",
        )
        return f"WhatsApp envoyé (SID: {msg.sid})"
    except ImportError:
        return "Erreur : twilio non installé (pip install twilio)"
    except Exception as e:
        return f"Erreur WhatsApp : {e}"


# ── Formatage messages WhatsApp ───────────────────────────────────────────────

_WA_LIMIT = 1500  # WhatsApp : limite de sécurité (limite réelle : 1600)


def _trunc(text: str, max_chars: int) -> str:
    """Tronque proprement à la dernière phrase complète, sinon coupe au mot."""
    if not text or len(text) <= max_chars:
        return text
    cut = text[:max_chars]
    # Coupe à la dernière phrase complète (.!?)
    for sep in (".", "!", "?"):
        pos = cut.rfind(sep)
        if pos > max_chars // 2:
            return cut[:pos + 1]
    # Sinon coupe au dernier espace
    pos = cut.rfind(" ")
    return (cut[:pos] + "…") if pos > 0 else cut + "…"


def _cap(msg: str) -> str:
    """Filet de sécurité : tronque le message entier si encore trop long."""
    if len(msg) <= _WA_LIMIT:
        return msg
    return msg[:_WA_LIMIT - 40].rsplit("\n", 1)[0] + "\n\n_— LifeAI_"


def format_alert_message(report: dict, name: str) -> str:
    score  = float(report.get("global_score", 0) or 0)
    level  = report.get("health_level") or "N/A"
    alerts = report.get("alerts") or []
    action = report.get("priority_action") or ""

    emoji = {"Excellent": "🟢", "Bon": "🔵", "Attention": "🟡", "Critique": "🔴"}.get(level, "⚪")

    lines = [
        "🏥 *LifeAI — Alerte Santé*",
        "",
        f"Bonjour {name},",
        "",
        f"{emoji} *Score global : {score:.1f}/100 — {level}*",
    ]

    if alerts:
        lines += ["", "⚠️ *Points critiques détectés :*"]
        for a in alerts[:3]:  # max 3 alertes
            lines.append(f"  • {_trunc(a, 100)}")

    if action:
        lines += ["", "✅ *Action prioritaire :*", f"  {_trunc(action, 120)}"]

    lines += ["", "_— LifeAI, ton coach santé IA_"]
    return _cap("\n".join(lines))


def format_report_message(report: dict, name: str) -> str:
    score   = float(report.get("global_score", 0) or 0)
    level   = report.get("health_level") or "N/A"
    synth   = _trunc(report.get("synthesis") or "", 280)
    action  = _trunc(report.get("priority_action") or "", 120)
    weekly  = (report.get("weekly_plan") or [])[:3]  # max 3 jours
    pred    = _trunc(report.get("prediction") or "", 120)
    emoji   = {"Excellent": "🟢", "Bon": "🔵", "Attention": "🟡", "Critique": "🔴"}.get(level, "⚪")
    date_str = datetime.now().strftime("%d/%m/%Y")

    lines = [
        f"📊 *LifeAI — Rapport du {date_str}*",
        "",
        f"Bonjour {name} !",
        "",
        f"{emoji} *Score : {score:.1f}/100 — {level}*",
        "",
        "📝 *Analyse :*",
        synth,
        "",
        "✅ *Action du moment :*",
        f"  {action}",
    ]

    if weekly:
        lines += ["", "📅 *Plan de la semaine :*"]
        for item in weekly:
            lines.append(f"  • {_trunc(item, 80)}")

    if pred:
        lines += ["", f"🔮 *Prédiction à 7 jours :* {pred}"]

    lines += ["", "_Ce message est informatif et ne remplace pas un avis médical._"]
    return _cap("\n".join(lines))


def format_weekly_message(summary: dict) -> str:
    """
    Formate le bilan hebdomadaire en message WhatsApp.

    Args:
        summary: Dict retourné par get_weekly_summary.
    """
    profile  = summary.get("profile", {})
    name     = profile.get("name", profile.get("prenom", ""))
    score    = float(summary.get("avg_global") or 0)
    trend    = summary.get("trend", "")
    n        = summary.get("sessions_count", 0)
    date_str = datetime.now().strftime("%d/%m/%Y")

    score_lines = []
    for label, key, emoji in [
        ("Activité",  "avg_activity",   "🏃"),
        ("Sommeil",   "avg_sleep",      "😴"),
        ("Nutrition", "avg_nutrition",  "🥗"),
        ("Risque",    "avg_risk",       "⚡"),
    ]:
        val = summary.get(key)
        bar = int((val or 0) / 10) * "▓" + (10 - int((val or 0) / 10)) * "░"
        score_lines.append(f"  {emoji} {label}: {val or '—'}/100 {bar}")

    lines = [
        f"📆 *LifeAI — Bilan semaine du {date_str}*",
        f"",
    ]

    if name:
        lines += [f"Bonjour {name} ! Voici ton bilan ({n} session(s)).", ""]

    lines += [
        f"📊 *Score moyen : {score:.1f}/100*",
        f"📈 Tendance : {trend}",
        "",
        "*Détail des domaines :*",
    ] + score_lines

    patterns = summary.get("patterns", [])
    if patterns:
        lines += ["", "🔍 *Patterns détectés :*"]
        for p in patterns[:2]:  # max 2 patterns
            lines.append(f"  • {_trunc(p['description'], 80)}")

    lines += ["", "_— LifeAI, ton coach santé IA_"]
    return _cap("\n".join(lines))


# ── Résumé hebdomadaire (DB) ──────────────────────────────────────────────────

def get_weekly_summary() -> dict:
    """
    Calcule le résumé des 7 derniers jours : scores moyens, tendance, patterns.
    Aucun argument requis.
    """
    user_id = _uid()
    sessions = db.get_sessions(_uid(), days=7)
    if not sessions:
        return {"status": "Aucune session cette semaine", "profile": db.get_profile(_uid())}

    def avg(field):
        vals = [s[field] for s in sessions if s.get(field) is not None]
        return round(sum(vals) / len(vals), 1) if vals else None

    return {
        "sessions_count": len(sessions),
        "avg_global":     avg("global_score"),
        "avg_activity":   avg("activity_score"),
        "avg_sleep":      avg("sleep_score"),
        "avg_nutrition":  avg("nutrition_score"),
        "avg_risk":       avg("risk_score"),
        "trend":          db.get_score_trend(_uid(), window=7) or "Pas assez de données",
        "patterns":       db.get_patterns(_uid(), min_occurrences=2),
        "recent_notes":   db.get_notes(_uid())[:5],
        "profile":        db.get_profile(_uid()),
    }


# ── PDF (optionnel, pour archivage) ──────────────────────────────────────────

def generate_pdf_report(report: dict, user_profile: dict) -> str:
    """
    Génère un rapport PDF pour archivage ou partage.
    Le fichier est sauvegardé dans reports/ avec un nom horodaté.

    Args:
        report: Dict du rapport complet.
        user_profile: Dict du profil utilisateur.

    Returns:
        Chemin absolu du PDF généré.
    """
    output_path = None
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.platypus import (
            HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
        )
    except ImportError:
        return "Erreur : reportlab non installé (pip install reportlab)"

    if not output_path:
        Path("reports").mkdir(exist_ok=True)
        output_path = f"reports/lifeai_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"

    doc = SimpleDocTemplate(output_path, pagesize=A4,
                            leftMargin=2*cm, rightMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)

    title_style = ParagraphStyle("title", fontSize=22, fontName="Helvetica-Bold",
                                 textColor=colors.HexColor("#1a1a2e"), spaceAfter=6)
    h2_style    = ParagraphStyle("h2", fontSize=13, fontName="Helvetica-Bold",
                                 textColor=colors.HexColor("#16213e"), spaceBefore=14, spaceAfter=4)
    body_style  = ParagraphStyle("body", fontSize=10, fontName="Helvetica",
                                 textColor=colors.HexColor("#333333"), leading=15)
    small_style = ParagraphStyle("small", fontSize=9, fontName="Helvetica",
                                 textColor=colors.HexColor("#666666"))

    score    = float(report.get("global_score", 0) or 0)
    level    = report.get("health_level", "N/A")
    name     = user_profile.get("name", user_profile.get("prenom", "Utilisateur"))
    date_str = datetime.now().strftime("%d/%m/%Y")
    level_color = {"Excellent": "#2ecc71", "Bon": "#3498db",
                   "Attention": "#f39c12", "Critique": "#e74c3c"}.get(level, "#95a5a6")
    bar = "█" * (int(score) // 5) + "░" * (20 - int(score) // 5)

    story = [
        Paragraph("LifeAI — Rapport Santé", title_style),
        Paragraph(f"{name}  •  {date_str}", small_style),
        Spacer(1, 0.3*cm),
        HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e0e0e0")),
        Spacer(1, 0.4*cm),
        Paragraph("Score Global", h2_style),
        Table([[f"{score:.1f} / 100", bar, level]], colWidths=[3*cm, 8*cm, 4*cm],
              style=TableStyle([
                  ("FONTNAME", (0,0), (-1,-1), "Helvetica-Bold"),
                  ("FONTSIZE", (0,0), (0,0), 16), ("FONTSIZE", (1,0), (1,0), 8),
                  ("FONTSIZE", (2,0), (2,0), 11),
                  ("TEXTCOLOR", (2,0), (2,0), colors.HexColor(level_color)),
                  ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
                  ("BOTTOMPADDING", (0,0), (-1,-1), 8),
              ])),
        Spacer(1, 0.3*cm),
        Paragraph("Analyse", h2_style),
        Paragraph(report.get("synthesis", ""), body_style),
        Spacer(1, 0.3*cm),
        Paragraph("Action Prioritaire", h2_style),
        Paragraph(f"→ {report.get('priority_action', '')}", body_style),
    ]

    for a in report.get("alerts", []):
        story += [Paragraph("Alertes", h2_style),
                  Paragraph(f"⚠ {a}", ParagraphStyle("alert", fontSize=10,
                      textColor=colors.HexColor("#e74c3c"), leading=14))]

    if report.get("weekly_plan"):
        story.append(Paragraph("Plan de la Semaine", h2_style))
        for item in report["weekly_plan"]:
            story.append(Paragraph(f"• {item}", body_style))

    if report.get("prediction"):
        story += [Paragraph("Prédiction à 7 Jours", h2_style),
                  Paragraph(report["prediction"], body_style)]

    story += [Spacer(1, 0.6*cm),
              HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e0e0e0")),
              Spacer(1, 0.2*cm),
              Paragraph("Généré par LifeAI · Informatif, ne remplace pas un avis médical.", small_style)]

    doc.build(story)
    return str(Path(output_path).resolve())


def send_report_and_alert(report: dict) -> str:
    """
    Envoie toutes les notifications : alerte WhatsApp si critique, rapport WhatsApp,
    et génère le PDF. Lit le profil (nom, téléphone) automatiquement depuis la base.
    Args:
        report: Dict du rapport complet (global_score, health_level, alerts, etc.).
    """
    profile = db.get_profile(_uid()) or {}
    name    = profile.get("name", profile.get("prenom", ""))
    # Priorité : users.numero_tel (colonne dédiée), sinon user_profiles.phone (legacy)
    phone   = (db.get_user_phone(_uid()) or profile.get("phone", "")).lstrip("+").strip()

    if not phone:
        return "Numéro de téléphone manquant — appelle save_profile avec le champ 'phone' (format : 33612345678)."

    # Robustesse : complète les champs manquants depuis la dernière session
    # (évite un WhatsApp aux sections vides si le report est partiel)
    report = dict(report or {})
    try:
        sessions = db.get_sessions(_uid(), days=1)
        if sessions:
            last = sessions[0]
            for key in ("global_score", "health_level", "synthesis", "priority_action",
                        "weekly_plan", "alerts", "prediction",
                        "activity_score", "sleep_score", "nutrition_score", "risk_score"):
                if not report.get(key) and last.get(key) is not None:
                    report[key] = last.get(key)
    except Exception as e:
        print(f"[send_report_and_alert] backfill session échoué : {e}", flush=True)

    results = []

    if report.get("health_level") == "Critique" or report.get("alerts"):
        alert_msg = format_alert_message(report, name)
        results.append(send_whatsapp(phone, alert_msg))

    report_msg = format_report_message(report, name)
    results.append(send_whatsapp(phone, report_msg))

    try:
        pdf_path = generate_pdf_report(report, profile)
        results.append(f"PDF : {pdf_path}")
    except Exception as e:
        results.append(f"PDF échoué : {e}")

    return " | ".join(results)
