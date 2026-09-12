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

"""Les entités produites par l'intégration IQA.

Deux entités par pièce configurée :

* le **score** — un entier de 0 à 100, avec le détail complet en attribut ;
* le **facteur le plus pénalisant** — optionnel, désactivé par défaut.

Aucun calcul n'a lieu ici : tout est délégué à `engine.compute()`, dont
l'équivalence avec la macro `iqa.jinja` est prouvée par `test_differentiel.py`.
Ce module ne fait que lire les états, appeler le moteur et publier le résultat.
"""

from __future__ import annotations

import json
from typing import Any

from homeassistant.components.sensor import (
    ENTITY_ID_FORMAT,
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.util import slugify

from . import engine
from .const import (
    ATTR_DETAIL,
    CONF_NOX_UNIT,
    CONF_ROOM,
    CONF_VOC_UNIT,
    CONF_WORST_SENSOR,
    DEFAULT_ROOM,
    KEY_BY_FACTOR_NAME,
    SOURCE_KEYS,
    UNIT_INDEX,
    UNIT_SCORE,
    WORST_NONE,
    WORST_OPTIONS,
)


# Acronymes reconnus comme préfixe déjà posé par l'utilisateur : IQA en
# français, AQI en anglais. Les deux désignent la même chose, et chacun nomme
# ses capteurs selon sa propre habitude.
KNOWN_PREFIXES = ("iqa", "aqi")


def build_object_id(name: str, suffix: str = "") -> str:
    """Fabrique la partie droite de l'entity_id, préfixée sans doublon.

    Home Assistant dérive normalement l'entity_id du nom affiché : « Salon »
    donnerait `sensor.salon`, sans rien qui rattache l'entité à l'intégration.
    On force donc un préfixe, tout en laissant le nom affiché intact.

    La règle est de ne **jamais dupliquer un préfixe déjà présent**. Quelqu'un
    qui nomme ses capteurs « IQA Salon » obtient `sensor.iqa_salon`, pas
    `sensor.iqa_iqa_salon`. Et celui qui préfère l'acronyme anglais garde le
    sien : « AQI Salon » donne `sensor.aqi_salon`.

    Le préfixe n'est reconnu qu'en **tête** de nom et comme **mot entier** :
    « IQAlerte Salon » n'en contient pas, et donne bien `sensor.iqa_iqalerte_salon`.
    Un préfixe placé en fin de nom est ignoré, « Salon IQA » donne
    `sensor.iqa_salon_iqa` : le cas est trop marginal pour justifier une règle
    de plus.

    Les collisions ne sont pas traitées ici. Deux entrées nommées « Salon »
    produisent le même identifiant, et c'est le registre d'entités de Home
    Assistant qui ajoute `_2` à la seconde.
    """
    slug = slugify(name)
    if not any(slug == p or slug.startswith(f"{p}_") for p in KNOWN_PREFIXES):
        slug = f"iqa_{slug}" if slug else "iqa"
    return f"{slug}{suffix}"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Crée les entités d'une entrée de configuration."""
    entities: list[IqaBaseEntity] = [IqaScoreSensor(entry)]
    if entry.options.get(CONF_WORST_SENSOR):
        entities.append(IqaWorstFactorSensor(entry))
    async_add_entities(entities)


class IqaBaseEntity(SensorEntity):
    """Socle commun : suivi des capteurs sources et appel du moteur."""

    _attr_should_poll = False
    _attr_has_entity_name = False

    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry
        self._options = dict(entry.options)
        self._detail: dict[str, Any] | None = None

        # Correspondance clé du moteur → entity_id choisi par l'utilisateur.
        # Une clé absente signifie « capteur non configuré » : son poids sera
        # redistribué sur les autres.
        self._entities: dict[str, str | None] = {
            engine_key: self._options.get(conf_key)
            for conf_key, engine_key in SOURCE_KEYS
        }
        self._tracked = [eid for eid in self._entities.values() if eid]

    # ── Lecture des états ──────────────────────────────────────────────────
    def _read(self, entity_id: str | None) -> float | None:
        """Reproduit `states(x) | float(default=none)` de la macro Jinja.

        Renvoie None pour une entité absente, indisponible, inconnue ou dont
        l'état n'est pas un nombre — exactement les cas que le moteur traite
        comme « capteur non fourni ».
        """
        if not entity_id:
            return None
        state = self.hass.states.get(entity_id)
        if state is None or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            return None
        try:
            return float(state.state)
        except (TypeError, ValueError):
            return None

    def _compute(self) -> dict[str, Any]:
        values = {key: self._read(eid) for key, eid in self._entities.items()}
        return engine.compute(
            self._options.get(CONF_ROOM, DEFAULT_ROOM),
            temperature=values["temp"],
            humidity=values["humidity"],
            co2=values["co2"],
            voc=values["voc"],
            nox=values["nox"],
            pm1=values["pm1"],
            pm25=values["pm25"],
            pm4=values["pm4"],
            pm10=values["pm10"],
            voc_unit=self._options.get(CONF_VOC_UNIT, UNIT_INDEX),
            nox_unit=self._options.get(CONF_NOX_UNIT, UNIT_INDEX),
            entities=self._entities,
        )

    @property
    def available(self) -> bool:
        """Équivalent de `iqa_available()`.

        Température et humidité sont obligatoires et leur poids n'est jamais
        redistribué. Si l'une des deux manque, publier un score reviendrait à
        publier une valeur plausible et fausse — 90, 85 ou 75 au lieu de 100 —
        qui polluerait l'historique et déclencherait des automatisations à
        contretemps. Mieux vaut pas de score qu'un mauvais score.
        """
        return engine.is_available(
            self._read(self._entities["temp"]),
            self._read(self._entities["humidity"]),
        )

    # ── Cycle de vie ───────────────────────────────────────────────────────
    async def async_added_to_hass(self) -> None:
        @callback
        def _source_changed(event: Event) -> None:
            self._refresh()
            self.async_write_ha_state()

        self.async_on_remove(
            async_track_state_change_event(self.hass, self._tracked, _source_changed)
        )
        self._refresh()

    @callback
    def _refresh(self) -> None:
        self._detail = self._compute() if self.available else None


class IqaScoreSensor(IqaBaseEntity):
    """L'indice lui-même : un entier de 0 à 100."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UNIT_SCORE
    _attr_icon = "mdi:leaf"

    # `detail` est réécrit à chaque changement d'état d'un capteur source, soit
    # 1 à 2 ko à chaque relevé. L'enregistrer gonflerait la base de plusieurs
    # centaines de mégaoctets par an sans rien apporter : c'est une vue
    # instantanée, jamais consultée rétrospectivement. Seul l'état — le score —
    # est historisé.
    _unrecorded_attributes = frozenset({ATTR_DETAIL})

    def __init__(self, entry: ConfigEntry) -> None:
        super().__init__(entry)
        self._attr_name = entry.options[CONF_NAME]
        self._attr_unique_id = entry.entry_id
        # Proposé au registre lors du premier enregistrement seulement : un
        # entity_id déjà enregistré, ou renommé à la main, n'est jamais écrasé.
        self.entity_id = ENTITY_ID_FORMAT.format(
            build_object_id(entry.options[CONF_NAME])
        )

    @property
    def native_value(self) -> int | None:
        return None if self._detail is None else self._detail["score"]

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Le détail complet, sérialisé en JSON.

        Une CHAÎNE et non un dictionnaire : c'est le format que produit
        `iqa_detail() | to_json` et que la carte `iqa-card` sait relire. Le
        format de cet attribut est un contrat — le changer casse la carte.
        """
        if self._detail is None:
            return None
        return {ATTR_DETAIL: json.dumps(self._detail, ensure_ascii=False)}


class IqaWorstFactorSensor(IqaBaseEntity):
    """Le facteur qui limite le score, exposé comme un état à part.

    Sans cette entité, une automatisation devrait lire l'attribut `detail` puis
    en analyser le JSON — pénible et fragile. Ici, « si le facteur pénalisant
    est le CO₂ et que le score passe sous 60, ouvrir la VMC » s'écrit sans une
    ligne de template.

    L'état est une **clé stable** (`co2`, `temp`, `pm25`…) et non un libellé :
    une automatisation ne doit pas dépendre de la langue de l'interface. Le
    libellé traduit est fourni par `device_class: enum`.
    """

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = list(WORST_OPTIONS)
    _attr_translation_key = "worst_factor"
    _attr_icon = "mdi:alert-decagram-outline"

    def __init__(self, entry: ConfigEntry) -> None:
        super().__init__(entry)
        self._attr_name = f"{entry.options[CONF_NAME]} : facteur pénalisant"
        self._attr_unique_id = f"{entry.entry_id}_worst"
        self.entity_id = ENTITY_ID_FORMAT.format(
            build_object_id(entry.options[CONF_NAME], "_facteur_penalisant")
        )

    @property
    def native_value(self) -> str | None:
        if self._detail is None:
            return None
        # `worst` porte le NOM du facteur ; on remonte à sa clé stable.
        # Il vaut None quand aucun plafond ne mord — tous les facteurs sont
        # alors à 100 et c'est la moyenne qui pilote.
        name = self._detail.get("worst")
        if not name:
            return WORST_NONE
        return KEY_BY_FACTOR_NAME.get(name, WORST_NONE)
