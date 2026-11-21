# -*- coding: utf-8 -*-
"""
Verwaltung: Fachkonfiguration, Farben und Logos einer Wehr, Stichwortkatalog, Benutzer und
(für Superadmins) Verbandsgemeinden und Wehren.

Rechte (rbac.py): Einstellungen, Fahrzeuge, Logos und Bedarfsplan-Freigabe brauchen SETTINGS bzw. PLAN_RELEASE,
der Stichwortkatalog KEYWORDS, die Gebührenordnung VG_FEES. SETTINGS und KEYWORDS in einer Rolle der VG
erlauben die Vorgaben für alle Wehren der VG; in einer Rolle der Wehr die Abweichungen dieser Wehr. Rollen vergibt jeder nur
nach der Verteilung seiner Rollen und nur in seinem Bereich, nie sich selbst; Rollen der VG pflegt, wer
ROLES_MANAGE hat, System- und globale Rollen sowie VGs und Wehren nur der Superadmin.

Aufbau: ein Modul je Thema, jedes mit eigenem Router; hier werden sie zu `router` zusammengesetzt.
- overview: Was darf der Benutzer verwalten (`has_admin`)
- settings: Einstellungen, Bedarfsplan-Freigabe, Farben, Logos einer Wehr
- vg: Gebührenordnung, Vorgaben und Fahrzeuge der VG
- keywords: Stichwortkatalog von Wehr bzw. VG
- people: Personenstamm einer Wehr (Abgleich, Zusammenführen, Wehrwechsel)
- users, roles: Zuordnungen und Rollen
- superadmin: VGs und Wehren (nur Superadmin)
- common: Zugriff, Protokoll, Fehlermeldungen
"""
from fastapi import APIRouter

from app.admin import keywords, overview, people, roles, settings, superadmin, users, vg
from app.admin.overview import has_admin

router = APIRouter()
for _module in (overview, settings, vg, keywords, people, users, roles, superadmin):
    router.include_router(_module.router)

__all__ = ["router", "has_admin"]
