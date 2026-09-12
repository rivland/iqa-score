# IQA — Indice de Qualité de l'Air pour Home Assistant
# Copyright (C) 2026 rivland
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""IQA — Constantes du moteur de notation.

SOURCE DE VÉRITÉ UNIQUE des barèmes. Ce module ne contient que des données,
aucune logique : il est lu par le moteur Python (engine.py) et par le
générateur qui produit `iqa.jinja`. Toute évolution d'un barème se fait ici
et nulle part ailleurs — c'est ce qui garantit que la macro Jinja de secours
et l'intégration ne peuvent pas diverger.

Valeurs extraites telles quelles de `iqa.jinja` version 1.0. Ne pas modifier
sans intention explicite : le test différentiel échouera.
"""

DOMAIN = "iqa"

# ── Plafonds par le pire facteur ───────────────────────────────────────────
# CAP_MARGIN : largeur d'un palier de l'échelle IQA. Le score ne peut jamais
# dépasser d'un palier le pire facteur d'AÉRATION.
# CAP_COMFORT : les facteurs de CONFORT (température, humidité basse) comptent
# moins fort — aérer ne les corrige pas — mais restent capables de faire perdre
# un palier complet.
CAP_MARGIN = 20
CAP_COMFORT = 25

# ── Poids des facteurs, en pourcent ────────────────────────────────────────
# Température et humidité sont OBLIGATOIRES : leur poids n'est jamais
# redistribué. Les quatre autres le sont s'ils sont absents.
WEIGHT_TEMP = 15
WEIGHT_HUM = 10
WEIGHT_CO2 = 30
WEIGHT_VOC = 10
WEIGHT_NOX = 5
WEIGHT_PM25 = 30

# ── Profils de pièce ───────────────────────────────────────────────────────
# tmin/tmax : plage idéale de température (le CENTRE de la courbe).
# tspan     : écart en °C au-delà duquel le score température tombe à 0.
#             C'est le vrai levier de largeur — élargir tmin/tmax ne fait que
#             déplacer le centre. 10 pour toute pièce climatisée, beaucoup plus
#             large pour Garage (25) et Combles (20), non climatisés par nature.
# hmin/hmax : plage idéale d'humidité relative.
# co2t      : tolérance CO2 (multiplie tous les seuils du barème CO2).
# pm/voc/nox: multiplicateurs de seuils. Le multiplicateur voc/nox ne
#             s'applique QU'EN mode concentration.
ROOMS: dict[str, dict] = {
    "bedroom":     {"label": "Chambre",          "tmin": 18, "tmax": 20, "tspan": 10, "hmin": 40, "hmax": 60, "co2t": 0.9, "pm": 1.0, "voc": 1.0, "nox": 1.0},
    "living_room": {"label": "Salon / Séjour",   "tmin": 19, "tmax": 22, "tspan": 10, "hmin": 40, "hmax": 60, "co2t": 1.0, "pm": 1.0, "voc": 1.0, "nox": 1.0},
    "office":      {"label": "Bureau",           "tmin": 20, "tmax": 23, "tspan": 10, "hmin": 40, "hmax": 60, "co2t": 0.9, "pm": 1.0, "voc": 1.0, "nox": 1.0},
    "kitchen":     {"label": "Cuisine",          "tmin": 19, "tmax": 22, "tspan": 10, "hmin": 40, "hmax": 60, "co2t": 1.0, "pm": 2.0, "voc": 1.5, "nox": 1.5},
    "bathroom":    {"label": "Salle de bain",    "tmin": 22, "tmax": 24, "tspan": 10, "hmin": 50, "hmax": 60, "co2t": 1.0, "pm": 1.0, "voc": 1.0, "nox": 1.0},
    "basement":    {"label": "Cave / Buanderie", "tmin": 16, "tmax": 20, "tspan": 10, "hmin": 45, "hmax": 65, "co2t": 1.0, "pm": 1.0, "voc": 1.0, "nox": 1.0},
    "garage":      {"label": "Garage",           "tmin": 5,  "tmax": 25, "tspan": 25, "hmin": 35, "hmax": 70, "co2t": 1.2, "pm": 2.0, "voc": 2.0, "nox": 2.0},
    "attic":       {"label": "Combles",          "tmin": 10, "tmax": 28, "tspan": 20, "hmin": 35, "hmax": 60, "co2t": 1.0, "pm": 1.2, "voc": 1.2, "nox": 1.0},
}
DEFAULT_ROOM = "living_room"

# ── Barème CO2, par segments ───────────────────────────────────────────────
# (ppm, score) — tous les seuils ppm sont multipliés par la tolérance co2t.
#   600 → 100  air très bien renouvelé
#   800 →  80  arrêté du 27/12/2022 : renouvellement satisfaisant
#  1200 →  60  NF EN 16798-1 catégorie II
#  1500 →  35  arrêté 2022 : « action immédiate » — volontairement sous 40
#  1750 →  28  NF EN 16798-1 catégorie III
#  2200 →  15  au-delà des références : choix d'ingénierie
#  2600 →   0
# Les scores sont des ENTIERS, pas des flottants : la macro Jinja utilise des
# littéraux entiers, et `100 | round(1)` y vaut 100 (entier), pas 100.0. Le JSON
# de l'attribut « detail » doit rester identique au caractère près.
CO2_SEGMENTS: tuple[tuple[float, int], ...] = (
    (600, 100),
    (800, 80),
    (1200, 60),
    (1500, 35),
    (1750, 28),
    (2200, 15),
    (2600, 0),
)

# ── Barèmes linéaires : (valeur 100 points, valeur 0 point) ────────────────
VOC_INDEX = (100.0, 400.0)          # index Sensirion, sans multiplicateur
VOC_CONCENTRATION = (200.0, 1000.0)  # µg/m³, × multiplicateur de pièce
NOX_INDEX = (5.0, 100.0)             # index Sensirion, sans multiplicateur
NOX_CONCENTRATION = (25.0, 200.0)    # µg/m³ NO2, × multiplicateur de pièce

# Particules, en µg/m³, × multiplicateur de pièce.
PM25_RANGE = (5.0, 35.0)
PM1_RANGE = (5.0, 35.0)
PM4_RANGE = (10.0, 45.0)
PM10_RANGE = (15.0, 45.0)

# ── Échelle IQA à 5 paliers ────────────────────────────────────────────────
# (score plancher, libellé, couleur)
TIERS: tuple[tuple[int, str, str], ...] = (
    (80, "Excellent", "#2f7a3d"),
    (60, "Bon", "#8a6d1f"),
    (40, "Moyen", "#b5651d"),
    (20, "Médiocre", "#c0392b"),
    (0, "Dangereux", "#7d3aa3"),
)

# Libellés des métriques unidirectionnelles (du meilleur au pire).
LABELS_UNIDIRECTIONAL = ("Idéal", "Correct", "Élevé", "Très élevé", "Critique")

FACTOR_NAMES = {
    "temp": "Température",
    "humidity": "Humidité",
    "co2": "CO₂",
    "voc": "COV",
    "nox": "NOx",
    "pm25": "PM2.5",
    "pm1": "PM1",
    "pm4": "PM4",
    "pm10": "PM10",
}

# Facteurs candidats au plafond d'AÉRATION, dans l'ordre d'évaluation.
# L'ordre compte : à égalité stricte, le premier rencontré l'emporte.
AERATION_POOL = ("humidity", "co2", "voc", "nox", "pm25")
# Facteurs candidats au plafond de CONFORT, dans l'ordre d'évaluation.
COMFORT_POOL = ("temp", "humidity")


# ── Clés de configuration (config flow) ────────────────────────────────────
CONF_ROOM = "room"
CONF_TEMPERATURE = "temperature"
CONF_HUMIDITY = "humidity"
CONF_CO2 = "co2"
CONF_VOC = "voc"
CONF_NOX = "nox"
CONF_PM1 = "pm1"
CONF_PM25 = "pm25"
CONF_PM4 = "pm4"
CONF_PM10 = "pm10"
CONF_VOC_UNIT = "voc_unit"
CONF_NOX_UNIT = "nox_unit"
CONF_WORST_SENSOR = "worst_sensor"

UNIT_INDEX = "index"
UNIT_CONCENTRATION = "concentration"
UNITS = (UNIT_INDEX, UNIT_CONCENTRATION)

# Capteurs sources, dans l'ordre d'affichage du formulaire.
# (clé de configuration, clé du moteur)
SOURCE_KEYS: tuple[tuple[str, str], ...] = (
    (CONF_TEMPERATURE, "temp"),
    (CONF_HUMIDITY, "humidity"),
    (CONF_CO2, "co2"),
    (CONF_PM25, "pm25"),
    (CONF_VOC, "voc"),
    (CONF_NOX, "nox"),
    (CONF_PM1, "pm1"),
    (CONF_PM4, "pm4"),
    (CONF_PM10, "pm10"),
)

ATTR_DETAIL = "detail"

# L'unité « points » est reprise du capteur template historique, pour que les
# graphiques d'historique gardent la même allure après migration.
UNIT_SCORE = "points"

# Le détail JSON ne donne que le NOM du facteur pénalisant (« CO₂ »,
# « Température »…). L'entité de diagnostic a besoin de la clé stable
# correspondante, pour que les automatisations ne dépendent pas de la langue.
# On inverse FACTOR_NAMES plutôt que d'ajouter un champ au détail : son format
# est un contrat avec la carte, et le test différentiel le vérifie au type près.
KEY_BY_FACTOR_NAME = {name: key for key, name in FACTOR_NAMES.items()}

# États possibles de l'entité « facteur le plus pénalisant ».
WORST_NONE = "none"
WORST_OPTIONS = (WORST_NONE, "temp", "humidity", "co2", "voc", "nox", "pm25")
