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

"""Écran d'ajout et de modification de l'intégration IQA.

Construit sur `SchemaConfigFlowHandler`, le mécanisme déclaratif qu'emploient
les helpers du cœur de Home Assistant (`min_max`, `group`, `threshold`,
`derivative`). Un seul schéma décrit le formulaire d'ajout ET l'écran d'options,
ce qui garantit qu'ils ne peuvent pas diverger : changer un capteur source après
coup n'oblige jamais à recréer l'entité.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import CONF_NAME
from homeassistant.helpers import selector
from homeassistant.helpers.schema_config_entry_flow import (
    SchemaConfigFlowHandler,
    SchemaFlowFormStep,
)

from .const import (
    CONF_CO2,
    CONF_HUMIDITY,
    CONF_NOX,
    CONF_NOX_UNIT,
    CONF_PM1,
    CONF_PM4,
    CONF_PM10,
    CONF_PM25,
    CONF_ROOM,
    CONF_TEMPERATURE,
    CONF_VOC,
    CONF_VOC_UNIT,
    CONF_WORST_SENSOR,
    DEFAULT_ROOM,
    DOMAIN,
    ROOMS,
    UNIT_INDEX,
    UNITS,
)


def _sensor(device_class: SensorDeviceClass | None = None) -> selector.EntitySelector:
    """Sélecteur d'entité limité au domaine `sensor`.

    Le filtrage par `device_class` raccourcit la liste et évite les erreurs de
    saisie — mais il masque aussi tout capteur dont la classe est mal déclarée,
    et l'utilisateur n'a alors aucun moyen de comprendre pourquoi son capteur
    n'apparaît pas. On ne filtre donc que là où la classe est fiable et
    universelle.

    Non filtrés délibérément :
      · COV et NOx — en mode index (Sensirion SGP41), ces capteurs n'ont aucune
        `device_class` : filtrer les rendrait tout simplement invisibles ;
      · PM4 — Home Assistant ne définit pas de `device_class` pour cette
        fraction.
    """
    config: dict[str, Any] = {"domain": "sensor"}
    if device_class is not None:
        config["device_class"] = device_class
    return selector.EntitySelector(selector.EntitySelectorConfig(**config))


def _unit_selector() -> selector.SelectSelector:
    """Index Sensirion (sans unité) ou concentration en µg/m³."""
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=list(UNITS),
            translation_key="unit",
            mode=selector.SelectSelectorMode.DROPDOWN,
        )
    )


# Le schéma des options est aussi le cœur du schéma d'ajout : une seule
# définition, donc aucune dérive possible entre les deux écrans.
OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_ROOM, default=DEFAULT_ROOM): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=list(ROOMS),
                translation_key="room",
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        ),
        # Obligatoires : sans eux le score serait plausible et faux.
        vol.Required(CONF_TEMPERATURE): _sensor(SensorDeviceClass.TEMPERATURE),
        vol.Required(CONF_HUMIDITY): _sensor(SensorDeviceClass.HUMIDITY),
        # Optionnels comptant dans le score ; leur poids est redistribué.
        vol.Optional(CONF_CO2): _sensor(SensorDeviceClass.CO2),
        vol.Optional(CONF_PM25): _sensor(SensorDeviceClass.PM25),
        vol.Optional(CONF_VOC): _sensor(),
        vol.Required(CONF_VOC_UNIT, default=UNIT_INDEX): _unit_selector(),
        vol.Optional(CONF_NOX): _sensor(),
        vol.Required(CONF_NOX_UNIT, default=UNIT_INDEX): _unit_selector(),
        # Optionnels affichés seuls, hors score.
        vol.Optional(CONF_PM1): _sensor(SensorDeviceClass.PM1),
        vol.Optional(CONF_PM4): _sensor(),
        vol.Optional(CONF_PM10): _sensor(SensorDeviceClass.PM10),
        # Entité de diagnostic supplémentaire, désactivée par défaut.
        vol.Required(CONF_WORST_SENSOR, default=False): selector.BooleanSelector(),
    }
)

CONFIG_SCHEMA = vol.Schema(
    {vol.Required(CONF_NAME): selector.TextSelector()}
).extend(OPTIONS_SCHEMA.schema)

CONFIG_FLOW: dict[str, SchemaFlowFormStep] = {
    "user": SchemaFlowFormStep(CONFIG_SCHEMA)
}
OPTIONS_FLOW: dict[str, SchemaFlowFormStep] = {
    "init": SchemaFlowFormStep(OPTIONS_SCHEMA)
}


class IqaConfigFlowHandler(SchemaConfigFlowHandler, domain=DOMAIN):
    """Ajout et modification d'un capteur IQA depuis l'interface."""

    config_flow = CONFIG_FLOW
    options_flow = OPTIONS_FLOW

    def async_config_entry_title(self, options: Mapping[str, Any]) -> str:
        """Le nom saisi par l'utilisateur sert de titre à l'entrée."""
        return str(options[CONF_NAME])
