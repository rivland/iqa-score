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

"""Les entités et le formulaire, testés contre un Home Assistant simulé.

Contrairement aux deux autres fichiers de test, celui-ci **exige Home Assistant
installé** — c'est justement son intérêt : il vérifie ce que le moteur seul ne
peut pas couvrir, à savoir le câblage entre HA et le calcul.

Ce qu'il contrôle :
  · le schéma du formulaire accepte une configuration réaliste ;
  · les entités lisent les états, appellent le moteur et publient le bon score ;
  · un capteur optionnel indisponible voit son poids redistribué ;
  · un capteur OBLIGATOIRE indisponible rend l'entité indisponible, au lieu de
    publier un score amputé et plausible ;
  · l'attribut `detail` est bien une CHAÎNE JSON — le contrat avec la carte ;
  · `detail` est exclu de l'enregistrement en base.

Il ne remplace pas un essai sur une vraie instance, mais il attrape tout ce qui
se casse silencieusement.
"""

from __future__ import annotations

import json
import sys
from types import SimpleNamespace

from homeassistant.core import State

sys.path.insert(0, ".")
from custom_components.iqa import engine  # noqa: E402
from custom_components.iqa.config_flow import (  # noqa: E402
    CONFIG_SCHEMA,
    OPTIONS_SCHEMA,
)
from custom_components.iqa.const import ATTR_DETAIL  # noqa: E402
from custom_components.iqa.sensor import (  # noqa: E402
    IqaScoreSensor,
    IqaWorstFactorSensor,
    async_setup_entry,
)

ok = True


def check(label, got, expected):
    global ok
    good = got == expected
    ok = ok and good
    print(f"{'OK  ' if good else 'FAIL'}  {label}: {got!r} (attendu {expected!r})")


def faux_hass(etats: dict[str, str | None]):
    """Un hass réduit à ce que les entités utilisent : hass.states.get()."""
    table = {
        eid: (None if val is None else State(eid, val))
        for eid, val in etats.items()
    }
    return SimpleNamespace(states=SimpleNamespace(get=table.get))


def entree(options: dict, entry_id: str = "abc123"):
    return SimpleNamespace(options=options, entry_id=entry_id)


# Configuration de référence : celle des captures du README, dont on sait que
# le moteur doit produire 83, plafonné par le confort à cause de la température.
OPTIONS = {
    "name": "IQA Salon",
    "room": "living_room",
    "temperature": "sensor.t",
    "humidity": "sensor.h",
    "co2": "sensor.co2",
    "pm25": "sensor.pm25",
    "voc": "sensor.voc",
    "voc_unit": "index",
    "nox": "sensor.nox",
    "nox_unit": "index",
    "worst_sensor": False,
}
ETATS = {
    "sensor.t": "25.3", "sensor.h": "43", "sensor.co2": "506",
    "sensor.pm25": "0.9", "sensor.voc": "64", "sensor.nox": "1",
}


def monte(options, etats):
    s = IqaScoreSensor(entree(options))
    s.hass = faux_hass(etats)
    s._refresh()
    return s


print("=== 1. Le formulaire accepte une configuration réaliste ===")
valide = CONFIG_SCHEMA(dict(OPTIONS))
check("le nom est conservé", valide["name"], "IQA Salon")
check("l'unité COV a une valeur par défaut", valide["voc_unit"], "index")
sans_options = {k: v for k, v in OPTIONS.items() if k not in ("co2", "pm25", "voc", "nox")}
check("capteur minimal accepté", "temperature" in CONFIG_SCHEMA(sans_options), True)
check("l'écran d'options refuse le champ « name »", "name" in OPTIONS_SCHEMA.schema, False)

print("\n=== 2. Le score publié est celui du moteur ===")
s = monte(OPTIONS, ETATS)
# Les entity_id doivent être repris dans le détail : c'est ce qui permet à la
# carte d'ouvrir l'historique du bon capteur sur un appui long.
ENTITES = {"temp": "sensor.t", "humidity": "sensor.h", "co2": "sensor.co2",
           "voc": "sensor.voc", "nox": "sensor.nox", "pm25": "sensor.pm25",
           "pm1": None, "pm4": None, "pm10": None}
attendu = engine.compute(
    "living_room", temperature=25.3, humidity=43.0, co2=506.0,
    pm25=0.9, voc=64.0, nox=1.0, entities=ENTITES,
)
check("score", s.native_value, 83)
check("identique au moteur appelé directement", s.native_value, attendu["score"])
check("disponible", s.available, True)

print("\n=== 3. L'attribut « detail » est une CHAÎNE JSON ===")
attrs = s.extra_state_attributes
check("clé présente", ATTR_DETAIL in attrs, True)
check("type", type(attrs[ATTR_DETAIL]).__name__, "str")
relu = json.loads(attrs[ATTR_DETAIL])
check("relisible et identique", relu, attendu)
check("les entity_id sont repris dans le détail",
      [f["entity"] for f in relu["factors"] if f["key"] == "temp"], ["sensor.t"])
check("le facteur limitant est la température", relu["worst"], "Température")
check("plafond de confort", relu["cap_kind"], "confort")
check("accents non échappés", "Température" in attrs[ATTR_DETAIL], True)

print("\n=== 4. « detail » est exclu de l'enregistrement en base ===")
check("dans _unrecorded_attributes", ATTR_DETAIL in IqaScoreSensor._unrecorded_attributes, True)

print("\n=== 5. Capteur OPTIONNEL indisponible → poids redistribué ===")
degrade = dict(ETATS, **{"sensor.co2": "unavailable"})
s2 = monte(OPTIONS, degrade)
sans_co2 = engine.compute(
    "living_room", temperature=25.3, humidity=43.0,
    pm25=0.9, voc=64.0, nox=1.0,
)
check("toujours disponible", s2.available, True)
check("score identique à un capteur sans CO₂", s2.native_value, sans_co2["score"])
check("le CO₂ a disparu du détail",
      [f for f in json.loads(s2.extra_state_attributes[ATTR_DETAIL])["factors"]
       if f["key"] == "co2"], [])

print("\n=== 6. Capteur OBLIGATOIRE indisponible → entité indisponible ===")
for panne in ("unavailable", "unknown", "bonjour", None):
    s3 = monte(OPTIONS, dict(ETATS, **{"sensor.h": panne}))
    check(f"humidité = {panne!r}", s3.available, False)
s4 = monte(OPTIONS, dict(ETATS, **{"sensor.t": "unavailable"}))
check("température indisponible", s4.available, False)
check("aucun score publié", s4.native_value, None)
check("aucun attribut publié", s4.extra_state_attributes, None)

print("\n=== 7. Entité « facteur le plus pénalisant » ===")
w = IqaWorstFactorSensor(entree(dict(OPTIONS, worst_sensor=True)))
w.hass = faux_hass(ETATS)
w._refresh()
check("clé stable, pas un libellé", w.native_value, "temp")
check("valeur déclarée dans les options", w.native_value in w._attr_options, True)
check("identifiant distinct du capteur de score", w.unique_id, "abc123_worst")
# Air parfait : aucun plafond ne mord, le moteur ne désigne aucun facteur.
parfait = monte(OPTIONS, dict(ETATS, **{"sensor.t": "20.5"}))
w2 = IqaWorstFactorSensor(entree(dict(OPTIONS, worst_sensor=True)))
w2.hass = faux_hass(dict(ETATS, **{"sensor.t": "20.5"}))
w2._refresh()
check("air parfait → « none »", w2.native_value, "none")
check("score correspondant", parfait.native_value, 100)

print("\n=== 8. L'entité optionnelle n'est créée que si elle est cochée ===")
for coche, attendu_nb in ((False, 1), (True, 2)):
    creees = []
    import asyncio
    asyncio.run(async_setup_entry(
        None, entree(dict(OPTIONS, worst_sensor=coche)), creees.extend))
    check(f"worst_sensor={coche}", len(creees), attendu_nb)

print("\n" + ("=== TOUS LES TESTS PASSENT ===" if ok else "=== DES TESTS ÉCHOUENT ==="))
sys.exit(0 if ok else 1)
