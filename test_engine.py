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

"""Les assertions de `test_iqa.py`, rejouées contre le moteur Python.

Le test différentiel prouve que le portage est IDENTIQUE à la macro. Celui-ci
prouve qu'il est JUSTE : il reprend, sans en changer une valeur attendue, les
cas de référence validés sur l'installation réelle de l'utilisateur.
"""

import json
import random
import sys

# Le moteur est chargé SANS passer par `custom_components/iqa/__init__.py`,
# qui importe Home Assistant. On fabrique un paquet synthétique pointant sur le
# dossier : les imports relatifs de engine.py fonctionnent, et les tests
# tournent sans installer Home Assistant.
#
# Ce n'est pas qu'une commodité de test : c'est le garde-fou qui garantit que le
# moteur reste indépendant de Home Assistant. Le jour où engine.py importerait
# quoi que ce soit de HA, ce chargement échouerait et la CI le dirait.
import importlib  # noqa: E402
import pathlib  # noqa: E402
import types  # noqa: E402

_PKG = "iqa_engine_sous_test"
_DIR = pathlib.Path(__file__).resolve().parent / "custom_components" / "iqa"
_pkg = types.ModuleType(_PKG)
_pkg.__path__ = [str(_DIR)]
sys.modules[_PKG] = _pkg
engine = importlib.import_module(f"{_PKG}.engine")

KEYS = ("co2", "voc", "nox", "pm1", "pm25", "pm4", "pm10")


def run(room="living_room", voc_unit="index", nox_unit="index", detail=False, **vals):
    present = {k: vals.get(k) for k in KEYS}
    entities = {"temp": "temp", "humidity": "hum"}
    for k in KEYS:
        entities[k] = k if present[k] is not None else None
    d = engine.compute(
        room, temperature=vals.get("temp"), humidity=vals.get("hum"),
        voc_unit=voc_unit, nox_unit=nox_unit, entities=entities, **present,
    )
    return d if detail else d["score"]


ok = True


def check(label, got, expected):
    global ok
    good = got == expected
    ok = ok and good
    print(f"{'OK  ' if good else 'FAIL'}  {label}: {got} (attendu {expected})")


print("=== 1. UltimateSensor complet — valeurs réelles de l'utilisateur ===")
d = run(temp=25.7, hum=54, co2=567, voc=152, nox=1,
        pm1=0.47, pm25=0.49, pm4=0.49, pm10=0.49, detail=True)
check("score", d["score"], 78)
check("moyenne pondérée", d["weighted_mean"], 91.3)
check("facteur limitant", d["worst"], "Température")
check("plafond confort mord (marge resserrée à 25)", d["cap_kind"], "confort")
check("plafond appliqué", d["capped"], True)
check("nb facteurs affichés", len(d["factors"]), 9)
check("PM10 hors score", [f for f in d["factors"] if f["key"] == "pm10"][0]["in_score"], False)
check("PM2.5 dans le score", [f for f in d["factors"] if f["key"] == "pm25"][0]["in_score"], True)

print("\n=== 2. Même capteur, température corrigée à 20,5 °C ===")
d = run(temp=20.5, hum=54, co2=567, voc=152, nox=1,
        pm1=0.47, pm25=0.49, pm4=0.49, pm10=0.49, detail=True)
check("score", d["score"], 98)
check("plafond appliqué", d["capped"], False)

print("\n=== 3. IKEA VINDSTYRKA (temp + hum + PM2.5 + VOC index) ===")
d = run(temp=21, hum=50, voc=95, pm25=3, detail=True)
check("score", d["score"], 100)
check("CO₂ absent du détail", [f for f in d["factors"] if f["key"] == "co2"], [])
check("nb facteurs", len(d["factors"]), 4)

print("\n=== 4. Capteur minimal (temp + hum seuls) ===")
check("score parfait", run(temp=20.5, hum=50), 100)
check("temp mauvaise, capteur minimal", run(temp=32, hum=50), 25)

print("\n=== 5. Plafond par le pire facteur ===")
d = run(temp=20.5, hum=50, co2=750, voc=90, nox=2, pm25=34, detail=True)
check("PM2.5 critique -> pire", d["worst"], "PM2.5")
check("score plafonné", d["score"], 23)
check("moyenne seule aurait donné", d["weighted_mean"], 66.5)

print("\n=== 6. Mode concentration vs index (COV) ===")
check("VOC 152 en index", run(temp=20.5, hum=50, voc=152), 95)
check("VOC 152 en µg/m³", run(temp=20.5, hum=50, voc=152, voc_unit="concentration"), 100)
check("VOC 600 en µg/m³", run(temp=20.5, hum=50, voc=600, voc_unit="concentration"), 70)

print("\n=== 7. Multiplicateur cuisine : concentration seulement ===")
check("cuisine, VOC 250 index", run(room="kitchen", temp=20.5, hum=50, voc=250), 70)
check("salon,   VOC 250 index", run(room="living_room", temp=20.5, hum=50, voc=250), 70)
check("cuisine, VOC 250 conc.", run(room="kitchen", temp=20.5, hum=50, voc=250, voc_unit="concentration"), 100)
check("salon,   VOC 250 conc.", run(room="living_room", temp=20.5, hum=50, voc=250, voc_unit="concentration"), 98)

print("\n=== 8. Redistribution des poids ===")
check("CO₂ 2400 ppm, capteur minimal", run(temp=20.5, hum=50, co2=2400), 28)
check("CO₂ 2400 ppm, autres parfaits", run(temp=20.5, hum=50, co2=2400, pm25=0, voc=1, nox=1), 28)

print("\n=== 9. Bornes ===")
check("tout au pire", run(temp=60, hum=100, co2=5000, voc=500, nox=500, pm25=999), 0)
check("tout au mieux", run(temp=20.5, hum=50, co2=100, voc=1, nox=1, pm25=0), 100)

print("\n=== 10. Disponibilité ===")
check("les deux OK", engine.is_available(20.0, 50.0), True)
check("humidité indisponible", engine.is_available(20.0, None), False)
check("température indisponible", engine.is_available(None, 50.0), False)

print("\n=== 11. PM1/PM4/PM10 ne plafonnent jamais ===")
d = run(temp=20.5, hum=50, co2=550, voc=50, nox=1, pm25=2, pm1=2, pm4=200, pm10=200, detail=True)
check("PM10 à 0 mais score intact", d["score"], 100)
check("pire facteur ignore PM10", d["worst"], None)

print("\n=== 11b. Cave (plage corrigée), Garage, Combles ===")
check("cave à 50 % HR -> idéale",
      run(room="basement", temp=18, hum=50, co2=600, voc=60, nox=1, pm25=2), 100)
d = run(room="basement", temp=18, hum=50, co2=600, voc=60, nox=1, pm25=2, detail=True)
check("cave 50% HR -> label Idéale",
      [f for f in d["factors"] if f["key"] == "humidity"][0]["label"], "Idéale")
check("garage, PM2.5=15 -> encore correct (mult. 2x)",
      run(room="garage", temp=15, hum=50, co2=600, voc=90, nox=3, pm25=15), 98)
check("bureau, PM2.5=15 -> nettement pénalisé (mult. 1x)",
      run(room="office", temp=21, hum=50, co2=600, voc=60, nox=1, pm25=15), 87)
check("combles à 24°C -> encore correct (plage 10-28, tspan 20)",
      run(room="attic", temp=24, hum=50, co2=600, voc=60, nox=1, pm25=2), 97)
check("garage à 35°C -> pénalisé mais pas nul (tspan 25)",
      run(room="garage", temp=35, hum=50, co2=600, voc=60, nox=1, pm25=2), 46)
check("garage à 45°C -> vraiment extrême",
      run(room="garage", temp=45, hum=50, co2=600, voc=60, nox=1, pm25=2), 25)
check("chambre à 35°C -> tspan=10, déjà nul",
      run(room="bedroom", temp=35, hum=50, co2=600, voc=60, nox=1, pm25=2), 25)

print("\n=== 12b. Périmètre du plafond = ce que l'aération corrige ===")
check("chaleur 27 °C -> plafond confort", run(temp=27, hum=50, co2=600, voc=40, nox=1, pm25=2), 64)
check("hiver 30 % HR -> pas encore de plafond", run(temp=20.5, hum=30, co2=600, voc=60, nox=1, pm25=2), 98)
check("humidité 85 % -> plafond", run(temp=18, hum=85, co2=700, voc=60, nox=1, pm25=2), 58)
check("CO₂ 1800 -> plafond", run(temp=21, hum=50, co2=1800, voc=60, nox=1, pm25=2), 47)
check("cuisson PM2.5=25 -> plafond", run(temp=21, hum=50, co2=700, voc=60, nox=1, pm25=25), 53)
check("COV 300 -> plafond", run(temp=21, hum=50, co2=700, voc=300, nox=1, pm25=2), 53)
check("CO₂ 1200 (EN cat. II) -> plafond 80", run(temp=21, hum=50, co2=1200, voc=60, nox=1, pm25=2), 80)
check("CO₂ 1400 -> facteur « Moyen »", run(temp=21, hum=50, co2=1400, voc=60, nox=1, pm25=2), 63)
check("CO₂ 1500 -> facteur « Médiocre »", run(temp=21, hum=50, co2=1500, voc=60, nox=1, pm25=2), 55)
check("CO₂ 800 (arrêté 2022) -> sans effet", run(temp=21, hum=50, co2=800, voc=60, nox=1, pm25=2), 94)
d = run(temp=32, hum=50, co2=600, voc=40, nox=1, pm25=2, detail=True)
check("32 °C, air pur -> plafond confort", d["score"], 25)
check("cap_kind", d["cap_kind"], "confort")
check("facteur limitant", d["worst"], "Température")
d = run(temp=20.5, hum=15, co2=600, voc=40, nox=1, pm25=2, detail=True)
check("15 % HR -> plafond confort", d["score"], 62)
check("humidité basse = confort", d["cap_kind"], "confort")
d = run(temp=18, hum=85, co2=700, voc=60, nox=1, pm25=2, detail=True)
check("85 % HR -> plafond aération", d["cap_kind"], "aeration")
d = run(temp=24, hum=50, co2=600, voc=40, nox=1, pm25=2, detail=True)
check("24 °C : encore sous le seuil du plafond confort", d["score"], 96)
check("aucun plafond", d["cap_kind"], None)

print("\n=== 12. Invariants sur 20000 combinaisons aléatoires ===")
random.seed(1)
rooms = ["bedroom", "living_room", "office", "kitchen",
         "bathroom", "basement", "garage", "attic"]
bad = 0
for _ in range(20000):
    kw = dict(temp=round(random.uniform(-5, 45), 1), hum=round(random.uniform(0, 100), 1))
    for k, hi in (("co2", 5000), ("voc", 600), ("nox", 600), ("pm25", 400),
                  ("pm1", 400), ("pm4", 400), ("pm10", 400)):
        if random.random() < 0.6:
            kw[k] = round(random.uniform(0, hi), 1)
    d = run(room=random.choice(rooms),
            voc_unit=random.choice(["index", "concentration"]),
            nox_unit=random.choice(["index", "concentration"]),
            detail=True, **kw)
    if not (0 <= d["score"] <= 100):
        bad += 1
    if d["score"] > round(d["weighted_mean"]) + 1:
        bad += 1
    if d["worst"] and d["score"] > round(d["worst_score"] + d["cap_comfort"]) + 1:
        bad += 1
    for f in d["factors"]:
        if not (0 <= f["score"] <= 100):
            bad += 1
        if f["key"] in ("pm1", "pm4", "pm10") and f["in_score"]:
            bad += 1
check("violations d'invariants", bad, 0)

print("\n=== 13. Sérialisation JSON de l'attribut « detail » ===")
d = run(temp=25.7, hum=54, co2=567, voc=152, nox=1, pm25=0.49, detail=True)
blob = json.dumps(d, ensure_ascii=False)
check("JSON relisible", json.loads(blob)["score"], 78)
check("taille raisonnable (octets)", len(blob.encode()) < 2000, True)

print("\n" + ("=== TOUS LES TESTS PASSENT ===" if ok else "=== DES TESTS ÉCHOUENT ==="))
sys.exit(0 if ok else 1)
