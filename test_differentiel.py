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

"""Test différentiel : le portage Python doit être IDENTIQUE à `iqa.jinja` 1.0.

Ce test est la preuve du contrat « la logique de calcul ne change pas ».
Il ne vérifie pas que le moteur est *juste* — c'est le rôle de test_iqa.py —
mais qu'il est *identique* à la référence, sur le score ET sur l'intégralité
du détail JSON, champ par champ.

Aucune tolérance numérique : une différence, même sur une décimale, est un
échec. Un écart de virgule flottante silencieux est exactement le genre de
dérive que ce test existe pour interdire.
"""

import json
import random
import sys

from jinja2 import Environment, FileSystemLoader

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

# ── Harnais Jinja, identique à celui de test_iqa.py ────────────────────────
STATES = {}


def states(eid):
    if eid is None:
        return "unknown"
    return str(STATES.get(eid, "unknown"))


def ha_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


env = Environment(loader=FileSystemLoader("."))
env.filters["float"] = ha_float
env.filters["to_json"] = lambda v: json.dumps(v, ensure_ascii=False)
env.globals["states"] = states

TPL_D = env.from_string(
    "{% from 'iqa.jinja' import iqa_detail %}"
    "{{ iqa_detail(room, 'temp', 'hum', co2=co2, voc=voc, nox=nox, "
    "pm1=pm1, pm25=pm25, pm4=pm4, pm10=pm10, "
    "voc_unit=voc_unit, nox_unit=nox_unit) }}"
)

KEYS = ("co2", "voc", "nox", "pm1", "pm25", "pm4", "pm10")
ENTITY_OF = {"temp": "temp", "humidity": "hum", **{k: k for k in KEYS}}


def render_jinja(room, voc_unit, nox_unit, vals):
    """Résultat de référence, produit par la macro Jinja."""
    STATES.clear()
    STATES["temp"] = vals["temp"]
    STATES["hum"] = vals["hum"]
    for k in KEYS:
        if vals.get(k) is not None:
            STATES[k] = vals[k]
    ctx = dict(
        room=room, voc_unit=voc_unit, nox_unit=nox_unit,
        **{k: (k if k in STATES else None) for k in KEYS},
    )
    return json.loads(TPL_D.render(**ctx).strip())


def render_python(room, voc_unit, nox_unit, vals):
    """Résultat du portage Python, avec les mêmes entity_id que la référence."""
    present = {k: vals.get(k) for k in KEYS}
    entities = {"temp": "temp", "humidity": "hum"}
    for k in KEYS:
        entities[k] = k if present[k] is not None else None
    return engine.compute(
        room,
        temperature=vals["temp"], humidity=vals["hum"],
        voc_unit=voc_unit, nox_unit=nox_unit, entities=entities,
        **present,
    )


def diff(a, b, path=""):
    """Liste des différences structurelles entre deux résultats."""
    out = []
    if isinstance(a, dict) and isinstance(b, dict):
        for key in sorted(set(a) | set(b)):
            out += diff(a.get(key, "<absent>"), b.get(key, "<absent>"), f"{path}.{key}")
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out.append(f"{path}: longueur {len(a)} vs {len(b)}")
        else:
            for i, (x, y) in enumerate(zip(a, b)):
                out += diff(x, y, f"{path}[{i}]")
    elif a != b or type(a) is not type(b):
        out.append(f"{path}: Jinja={a!r} ({type(a).__name__}) vs Python={b!r} ({type(b).__name__})")
    return out


ROOMS = ["bedroom", "living_room", "office", "kitchen",
         "bathroom", "basement", "garage", "attic", "inconnu"]
UNITS = ["index", "concentration"]

# ── Cas limites explicites : frontières de segments et de paliers ──────────
EDGE_CASES = []
for room in ROOMS:
    for t in (-5, 0, 5, 10, 15, 18, 19, 20, 20.5, 21, 22, 24, 25, 27, 28, 30, 35, 45, 60):
        EDGE_CASES.append({"temp": t, "hum": 50})
    for h in (0, 5, 19.9, 20, 20.1, 30, 35, 39.9, 40, 45, 50, 55, 60, 60.1,
              65, 70, 79.9, 80, 80.1, 90, 100):
        EDGE_CASES.append({"temp": 20.5, "hum": h})
    for c in (0, 540, 599, 600, 601, 720, 800, 900, 1080, 1200, 1350, 1400,
              1500, 1750, 2000, 2200, 2600, 2601, 3120, 5000):
        EDGE_CASES.append({"temp": 20.5, "hum": 50, "co2": c})
    for v in (0, 1, 5, 99, 100, 101, 152, 200, 250, 300, 399, 400, 401, 600, 1000, 1500):
        EDGE_CASES.append({"temp": 20.5, "hum": 50, "voc": v})
    for n in (0, 1, 4.9, 5, 5.1, 25, 50, 99, 100, 101, 200, 400):
        EDGE_CASES.append({"temp": 20.5, "hum": 50, "nox": n})
    for p in (0, 2, 4.9, 5, 5.1, 10, 15, 20, 25, 34.9, 35, 35.1, 45, 70, 400):
        EDGE_CASES.append({"temp": 20.5, "hum": 50, "pm25": p, "pm1": p, "pm4": p, "pm10": p})

failures = 0
compared = 0

print("=== Cas limites (frontières de segments et de paliers) ===")
for room in ROOMS:
    for unit in UNITS:
        for vals in EDGE_CASES:
            for key in ("temp", "hum"):
                if key not in vals:
                    break
            ref = render_jinja(room, unit, unit, vals)
            got = render_python(room, unit, unit, vals)
            compared += 1
            d = diff(ref, got)
            if d:
                failures += 1
                if failures <= 10:
                    print(f"ÉCART  pièce={room} unit={unit} {vals}")
                    for line in d[:6]:
                        print(f"       {line}")
print(f"{compared} cas limites comparés, {failures} écart(s)")

# ── Tirage aléatoire large, toutes combinaisons de capteurs présents ───────
print("\n=== Tirage aléatoire ===")
random.seed(20260831)
N = 20000
rand_fail = 0
for _ in range(N):
    vals = {
        "temp": round(random.uniform(-10, 50), 1),
        "hum": round(random.uniform(0, 100), 1),
    }
    for k, hi in (("co2", 5000), ("voc", 600), ("nox", 600), ("pm25", 400),
                  ("pm1", 400), ("pm4", 400), ("pm10", 400)):
        if random.random() < 0.6:
            vals[k] = round(random.uniform(0, hi), 1)
    room = random.choice(ROOMS)
    vu, nu = random.choice(UNITS), random.choice(UNITS)
    ref = render_jinja(room, vu, nu, vals)
    got = render_python(room, vu, nu, vals)
    compared += 1
    d = diff(ref, got)
    if d:
        rand_fail += 1
        failures += 1
        if rand_fail <= 10:
            print(f"ÉCART  pièce={room} voc_unit={vu} nox_unit={nu} {vals}")
            for line in d[:6]:
                print(f"       {line}")
print(f"{N} tirages aléatoires comparés, {rand_fail} écart(s)")

print(f"\nTOTAL : {compared} comparaisons, {failures} écart(s)")
print("=== IDENTIQUE À LA RÉFÉRENCE ===" if failures == 0 else "=== DIVERGENCE ===")
sys.exit(1 if failures else 0)
