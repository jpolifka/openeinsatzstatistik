# -*- coding: utf-8 -*-
"""
Übernahme der Einzel-Installation der FF Rheinbrohl in die mandantenfähige Ablage.

rheinbrohl_config() enthält die Fachkonstanten, die bis zur Mandantenfähigkeit fest im Code
standen. Nach der Übernahme liegen sie nur noch in der Datenbank dieser Wehr.
"""
from app.tenant_config import TenantConfig, Vehicle


def rheinbrohl_config():
    return TenantConfig(
        name="Feuerwehr Rheinbrohl",
        # Reihenfolge der Einsatzübersicht; 01/10 fehlt in der Gesamtstärke des Bedarfsplans (Excel-Spalte AU)
        fleet=(Vehicle("02/45"), Vehicle("02/24"), Vehicle("02/71"), Vehicle("02/19"),
               Vehicle("01/10", in_plan_crew=False)),
        substitutes={"01/23": "02/45"},
        unit_prefix="FL NR#.BHÖ ",            # Fahrzeuge der Verbandsgemeinde Bad Hönningen
        own_prefix="02/",                     # Fahrzeuge des Löschzugs Rheinbrohl
        unit_marker="FW NR#.BHÖ 02",
        control_center="FL NR#.LIN",
        places=(("Rheinbrohl", "rhein"), ("Arienheller", "arienh"), ("Hammerstein", "hammer"),
                ("Ariendorf", "ariend"), ("Bad Hönningen", "bad hönn"), ("Leutesdorf", "leutes")),
        # Ausrückebereich laut Feuerwehrbedarfsplan Pos. 8.4
        plan_places=("Rheinbrohl", "Hammerstein", "Arienheller"),
    )
