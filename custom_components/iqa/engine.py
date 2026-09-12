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

"""IQA — Moteur de notation, portage Python de `iqa.jinja` version 1.0.

Aucune dépendance à Home Assistant : entrées = des nombres (ou None), sortie =
un dictionnaire. C'est ce qui rend le moteur testable hors HA et comparable
ligne à ligne avec la macro Jinja.

CONTRAT : ce module doit produire, pour toute entrée, EXACTEMENT le même
résultat que `iqa.jinja` 1.0. C'est vérifié par `test_differentiel.py`. Toute
modification de la logique ici sans modification correspondante des constantes
est un bug, pas une évolution.

Note sur les arrondis : la macro utilise le filtre Jinja `round`, dont la
méthode « common » est l'arrondi de Python (`round()`, arrondi au pair le plus
proche pour les demis). On utilise donc `round()` tel quel — surtout pas une
réimplémentation « arrondi commercial », qui divergerait sur les demis.
"""

from __future__ import annotations

from .const import (
    AERATION_POOL,
    CAP_COMFORT,
    CAP_MARGIN,
    CO2_SEGMENTS,
    COMFORT_POOL,
    DEFAULT_ROOM,
    FACTOR_NAMES,
    NOX_CONCENTRATION,
    NOX_INDEX,
    PM1_RANGE,
    PM4_RANGE,
    PM10_RANGE,
    PM25_RANGE,
    ROOMS,
    TIERS,
    VOC_CONCENTRATION,
    VOC_INDEX,
    WEIGHT_CO2,
    WEIGHT_HUM,
    WEIGHT_NOX,
    WEIGHT_PM25,
    WEIGHT_TEMP,
    WEIGHT_VOC,
)

# Ordre d'affichage des métriques unidirectionnelles dans le détail.
# (clé, unité, plage, multiplicateur de pièce, compte dans le score)
_SPECS = (
    ("co2", "ppm", None, None, True),
    ("voc", None, None, "voc", True),
    ("nox", None, None, "nox", True),
    ("pm25", "µg/m³", PM25_RANGE, "pm", True),
    ("pm1", "µg/m³", PM1_RANGE, "pm", False),
    ("pm4", "µg/m³", PM4_RANGE, "pm", False),
    ("pm10", "µg/m³", PM10_RANGE, "pm", False),
)


# ── Briques de notation ────────────────────────────────────────────────────

def _tier(score: float) -> tuple[str, str]:
    """Palier IQA (libellé, couleur) pour un score donné."""
    for floor, label, color in TIERS:
        if score >= floor:
            return label, color
    return TIERS[-1][1], TIERS[-1][2]


def _score_temperature(value: float, room: dict) -> float:
    """100 si l'écart à l'idéal est ≤ 1 °C, 0 au-delà de tspan, linéaire entre."""
    ideal = (room["tmin"] + room["tmax"]) / 2
    span = room["tspan"]
    dev = abs(value - ideal)
    if dev <= 1:
        return 100
    if dev > span:
        return 0
    return max(0, 100 - (dev - 1) * (100 / (span - 1)))


def _score_humidity(value: float, room: dict) -> float:
    """Plateau à 100 dans la plage de la pièce, deux pentes vers 0 aux extrêmes."""
    hmin, hmax = room["hmin"], room["hmax"]
    if value < 20:
        raw = (value / 20) * 50
    elif value > 80:
        raw = ((100 - value) / 20) * 50
    elif value < hmin:
        raw = 50 + (value - 20) / (hmin - 20) * 50
    elif value > hmax:
        raw = 50 + (80 - value) / (80 - hmax) * 50
    else:
        raw = 100
    return min(max(raw, 0), 100)


def _score_co2(value: float, room: dict) -> float:
    """Barème par segments, tous les seuils multipliés par la tolérance co2t."""
    k = room["co2t"]
    first_ppm, first_score = CO2_SEGMENTS[0]
    if value <= first_ppm * k:
        return first_score
    for (lo_ppm, lo_score), (hi_ppm, hi_score) in zip(CO2_SEGMENTS, CO2_SEGMENTS[1:]):
        if value <= hi_ppm * k:
            width = (hi_ppm - lo_ppm) * k
            return lo_score - (value - lo_ppm * k) / width * (lo_score - hi_score)
    return 0


def _score_linear(value: float, best: float, worst: float) -> float:
    """100 jusqu'à `best`, 0 à partir de `worst`, linéaire décroissant entre."""
    if value <= best:
        return 100
    if value >= worst:
        return 0
    return (worst - value) / (worst - best) * 100


def _thresholds(kind: str, room: dict, is_index: bool) -> tuple[float, float]:
    """Seuils (100 points, 0 point) pour COV ou NOx, selon l'unité choisie.

    Le multiplicateur de pièce ne s'applique QU'EN mode concentration : en mode
    index, la ligne de base Sensirion est déjà calculée sur 24 h, donc déjà
    relative à la pièce. Le multiplier reviendrait à compenser deux fois.
    """
    if kind == "voc":
        if is_index:
            return VOC_INDEX
        mult = room["voc"]
        return VOC_CONCENTRATION[0] * mult, VOC_CONCENTRATION[1] * mult
    if is_index:
        return NOX_INDEX
    mult = room["nox"]
    return NOX_CONCENTRATION[0] * mult, NOX_CONCENTRATION[1] * mult


def _label_bidirectional(score: float, high: bool, kind: str) -> str:
    """Libellé directionnel pour température et humidité."""
    if kind == "temp":
        suffix = "élevée" if high else "basse"
        mid = "Élevée" if high else "Basse"
    else:
        suffix = "humide" if high else "sec"
        mid = "Humide" if high else "Sec"
    if score >= 80:
        return "Idéale"
    if score >= 60:
        return f"Légèrement {suffix}"
    if score >= 40:
        return mid
    if score >= 20:
        return f"Très {suffix}"
    return "Excessive" if high else "Insuffisante"


def _label_unidirectional(score: float) -> str:
    if score >= 80:
        return "Idéal"
    if score >= 60:
        return "Correct"
    if score >= 40:
        return "Élevé"
    if score >= 20:
        return "Très élevé"
    return "Critique"


# ── API publique ───────────────────────────────────────────────────────────

def is_available(temperature: float | None, humidity: float | None) -> bool:
    """Équivalent de `iqa_available()`.

    Température et humidité sont obligatoires et leur poids n'est JAMAIS
    redistribué : sans ce garde-fou, un capteur indisponible produirait un score
    plausible et faux (85/90/75 au lieu de 100) au lieu d'une indisponibilité.
    """
    return temperature is not None and humidity is not None


def compute(
    room: str,
    temperature: float | None = None,
    humidity: float | None = None,
    co2: float | None = None,
    voc: float | None = None,
    nox: float | None = None,
    pm1: float | None = None,
    pm25: float | None = None,
    pm4: float | None = None,
    pm10: float | None = None,
    voc_unit: str = "index",
    nox_unit: str = "index",
    entities: dict[str, str | None] | None = None,
) -> dict:
    """Calcule le score IQA et son détail. Équivalent de `iqa_detail()`."""
    r = ROOMS.get(room, ROOMS[DEFAULT_ROOM])
    entities = entities or {}

    # La macro lit chaque entrée via `states(...) | float(default=none)` : les
    # valeurs y sont TOUJOURS des flottants. On reproduit cette coercition, sans
    # quoi un entier passé en argument produirait `20` au lieu de `20.0` dans le
    # détail JSON.
    def _f(v):
        return None if v is None else float(v)

    temperature, humidity = _f(temperature), _f(humidity)
    co2, voc, nox = _f(co2), _f(voc), _f(nox)
    pm1, pm25, pm4, pm10 = _f(pm1), _f(pm25), _f(pm4), _f(pm10)

    voc_is_index = str(voc_unit or "index").lower() != "concentration"
    nox_is_index = str(nox_unit or "index").lower() != "concentration"

    values = {
        "temp": temperature, "humidity": humidity, "co2": co2, "voc": voc,
        "nox": nox, "pm1": pm1, "pm25": pm25, "pm4": pm4, "pm10": pm10,
    }

    scores: dict[str, float | None] = {k: None for k in values}
    if temperature is not None:
        scores["temp"] = _score_temperature(temperature, r)
    if humidity is not None:
        scores["humidity"] = _score_humidity(humidity, r)
    if co2 is not None:
        scores["co2"] = _score_co2(co2, r)
    if voc is not None:
        scores["voc"] = _score_linear(voc, *_thresholds("voc", r, voc_is_index))
    if nox is not None:
        scores["nox"] = _score_linear(nox, *_thresholds("nox", r, nox_is_index))
    for key, rng in (("pm25", PM25_RANGE), ("pm1", PM1_RANGE),
                     ("pm4", PM4_RANGE), ("pm10", PM10_RANGE)):
        if values[key] is not None:
            mult = r["pm"]
            scores[key] = _score_linear(values[key], rng[0] * mult, rng[1] * mult)

    # ── Pondération : le poids d'un facteur optionnel absent est redistribué
    #    proportionnellement sur les autres. Température et humidité, jamais.
    weights = {
        "temp": WEIGHT_TEMP, "humidity": WEIGHT_HUM, "co2": WEIGHT_CO2,
        "voc": WEIGHT_VOC, "nox": WEIGHT_NOX, "pm25": WEIGHT_PM25,
    }
    lost = 0
    for key in ("co2", "voc", "nox", "pm25"):
        if scores[key] is None:
            lost += weights[key]
            weights[key] = 0
    rf = 100 / (100 - lost) if lost < 100 else 1

    weighted_mean = 0
    for key in ("temp", "humidity", "co2", "voc", "nox", "pm25"):
        if scores[key] is not None:
            weighted_mean += scores[key] * (weights[key] * rf / 100)

    # ── Double plafond par le pire facteur (approche ATMO / AQI).
    #    L'ordre d'évaluation compte : à égalité stricte, le premier gagne.
    worst_air, name_air = 100, None
    for key in AERATION_POOL:
        s = scores[key]
        if s is None:
            continue
        if key == "humidity" and not humidity > r["hmax"]:
            continue  # aérer n'aide que si l'humidité est EXCESSIVE
        if s < worst_air:
            worst_air, name_air = s, FACTOR_NAMES[key]

    worst_conf, name_conf = 100, None
    for key in COMFORT_POOL:
        s = scores[key]
        if s is None:
            continue
        if key == "humidity" and not humidity <= r["hmax"]:
            continue  # trop humide relève de l'aération, pas du confort
        if s < worst_conf:
            worst_conf, name_conf = s, FACTOR_NAMES[key]

    cap_air = worst_air + CAP_MARGIN
    cap_conf = worst_conf + CAP_COMFORT
    cap = min(cap_air, cap_conf)
    capped = cap < weighted_mean
    air_wins = cap_air <= cap_conf
    cap_kind = None if not capped else ("aeration" if air_wins else "confort")
    limiting_name = name_air if air_wins else name_conf
    limiting_score = worst_air if air_wins else worst_conf

    final = int(round(min(max(min(weighted_mean, cap), 0), 100), 0))
    tier_name, tier_color = _tier(final)

    # ── Détail par facteur, dans l'ordre d'affichage de la carte.
    factors: list[dict] = []
    if scores["temp"] is not None:
        s = scores["temp"]
        high = temperature > (r["tmin"] + r["tmax"]) / 2
        factors.append({
            "key": "temp", "name": FACTOR_NAMES["temp"],
            "value": round(temperature, 1), "unit": "°C", "score": round(s, 1),
            "label": _label_bidirectional(s, high, "temp"), "color": _tier(s)[1],
            "entity": entities.get("temp"), "in_score": True,
        })
    if scores["humidity"] is not None:
        s = scores["humidity"]
        high = humidity > (r["hmin"] + r["hmax"]) / 2
        factors.append({
            "key": "humidity", "name": FACTOR_NAMES["humidity"],
            "value": int(round(humidity, 0)), "unit": "%", "score": round(s, 1),
            "label": _label_bidirectional(s, high, "humidity"), "color": _tier(s)[1],
            "entity": entities.get("humidity"), "in_score": True,
        })
    for key, unit, _rng, _mult, in_score in _SPECS:
        s = scores[key]
        if s is None:
            continue
        if unit is None:  # COV et NOx : pas d'unité affichée en mode index
            is_index = voc_is_index if key == "voc" else nox_is_index
            unit = "" if is_index else "µg/m³"
        factors.append({
            "key": key, "name": FACTOR_NAMES[key],
            "value": round(values[key], 1), "unit": unit, "score": round(s, 1),
            "label": _label_unidirectional(s), "color": _tier(s)[1],
            "entity": entities.get(key), "in_score": in_score,
        })

    return {
        "score": final,
        "tier": tier_name,
        "color": tier_color,
        "room": room,
        "room_label": r["label"],
        "worst": limiting_name,
        "worst_score": round(limiting_score, 1),
        "cap_kind": cap_kind,
        "weighted_mean": round(weighted_mean, 1),
        "capped": capped,
        "cap_margin": CAP_MARGIN,
        "cap_comfort": CAP_COMFORT,
        "voc_unit": "index" if voc_is_index else "concentration",
        "nox_unit": "index" if nox_is_index else "concentration",
        "factors": factors,
    }


def score(*args, **kwargs) -> int:
    """Équivalent de `iqa_score()` : l'entier 0-100 seul."""
    return compute(*args, **kwargs)["score"]
