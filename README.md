# IQA — Indice de qualité de l'air pour Home Assistant

Intégration personnalisée qui calcule un **indice de qualité de l'air intérieur
de 0 à 100** à partir de vos capteurs existants, et se configure entièrement
depuis l'interface de Home Assistant — sélecteurs d'entités, aucun YAML à
copier-coller.

## Comment ça s'articule

Le projet est fait de **deux briques indépendantes**, distribuées séparément
parce qu'un dépôt HACS ne porte qu'une seule catégorie.

| Dépôt | Rôle | Catégorie HACS |
|---|---|---|
| **`iqa-score`** *(celui-ci)* | **calcule** le score et l'expose comme une entité | Integration |
| **`iqa-card`** *(séparé)* | **affiche** ce score, sans rien recalculer | Dashboard |

Le dépôt s'appelle `iqa-score`, mais le domaine Home Assistant de l'intégration
reste `iqa` — c'est lui qui donne son nom au dossier `custom_components/iqa/`.
Les deux sont indépendants : HACS n'exige la correspondance entre nom de dépôt
et nom de fichier que pour les cartes, pas pour les intégrations.

Pour chaque pièce configurée, l'intégration crée un capteur du type
`sensor.iqa_salon` :

- son **état** est le score, un entier de 0 à 100 — c'est lui qu'on utilise
  dans les automatisations, l'historique et les statistiques ;
- son **attribut `detail`** porte la décomposition complète : score, libellé et
  couleur de chaque facteur, facteur le plus pénalisant, et lequel des deux
  plafonds s'applique.

La carte lit cet attribut et le met en forme. **Elle ne fait aucun calcul.**
C'est délibéré : le barème n'existe qu'à un seul endroit, donc l'affichage ne
peut pas diverger du score. Le corollaire est que le format de `detail` est un
contrat — le changer casse la carte.

**La carte est facultative.** Sans elle, le score fonctionne normalement et
s'affiche avec n'importe quelle carte standard de Home Assistant. Elle n'apporte
que la présentation dédiée et la vue détaillée au clic.

## Quels capteurs faut-il ?

**Deux sont obligatoires : température et humidité.** Tous les autres sont
facultatifs — l'intégration fonctionne avec ce que vous avez déjà.

| Capteur | Statut | Poids de base |
|---|---|---|
| Température | **obligatoire** | 15 % |
| Humidité | **obligatoire** | 10 % |
| CO₂ | optionnel | 30 % |
| PM2.5 | optionnel | 30 % |
| COV | optionnel | 10 % |
| NOx | optionnel | 5 % |
| PM1, PM4, PM10 | optionnels | **hors score** |

### Quand un capteur optionnel manque

Son poids est **redistribué proportionnellement** sur les facteurs présents. Le
score reste donc toujours sur 100, et une mesure absente ne coûte jamais de
points : un capteur que vous n'avez pas ne peut pas vous pénaliser.

| Ce que vous avez | Répartition réelle du score |
|---|---|
| Température + humidité seules | Température 60 % · Humidité 40 % |
| + PM2.5 et COV *(IKEA VINDSTYRKA)* | Température ≈ 23 % · Humidité 15 % · COV 15 % · PM2.5 ≈ 46 % |
| Tout *(SCD41 + SGP41 + SPS30)* | les poids de base ci-dessus, inchangés |

### Pourquoi ces deux-là ne sont jamais redistribuées

Parce que le résultat serait **faux sans le dire**. Si l'humidité manquait et
que son poids était simplement ignoré, le score plafonnerait à 90 au lieu de
100 ; sans la température, à 85 ; sans les deux, à 75. Le tout sans le moindre
signal d'erreur — une valeur plausible et fausse, qui polluerait l'historique
et pourrait déclencher des automatisations à contretemps.

L'intégration fait donc l'inverse : si la température ou l'humidité est
indisponible, le capteur IQA passe lui-même à **`unavailable`**. Pas de score
plutôt qu'un mauvais score.

## Ce que fait le score

Les valeurs ci-dessous sont celles du profil **Salon / Séjour**, pris ici comme
exemple, avec COV et NOx en mode index. Ce ne sont pas des seuils universels :
**chaque type de pièce les décale.**

| Facteur | Poids | 100 points | 0 point |
|---|---|---|---|
| CO₂ | 30 % | ≤ 600 ppm | ≥ 2600 ppm |
| PM2.5 | 30 % | ≤ 5 µg/m³ | ≥ 35 µg/m³ |
| Température | 15 % | écart ≤ 1 °C de l'idéal (19-22 °C) | écart > 10 °C |
| Humidité | 10 % | 40-60 % | 0 % ou 100 % |
| COV | 10 % | index ≤ 100 | index ≥ 400 |
| NOx | 5 % | index ≤ 5 | index ≥ 100 |

## Les huit profils de pièce

Chambre, salon, bureau, cuisine, salle de bain, cave, garage, combles. Ce que
chacun change par rapport au salon, et pourquoi :

| Profil | Ce qui change | Pourquoi |
|---|---|---|
| **Chambre** | idéal 18-20 °C · CO₂ ×0,9 (100 points ≤ 540 ppm) | on y dort plusieurs heures porte fermée : le CO₂ y pèse plus lourd |
| **Bureau** | idéal 20-23 °C · CO₂ ×0,9 | la baisse de concentration liée au CO₂ est l'enjeu principal |
| **Cuisine** | PM2.5 ×2 (100 points ≤ 10 µg/m³) | une cuisson provoque un pic bref et normal, qui ne doit pas être noté comme une pollution |
| **Salle de bain** | idéal 22-24 °C · humidité 50-60 % | on y est peu vêtu et l'humidité y est structurellement plus haute |
| **Cave / Buanderie** | idéal 16-20 °C · humidité **45-65 %** | plus humide qu'une pièce de vie sans que ce soit un défaut ; le risque de moisissure commence au-delà de 65 % |
| **Garage** | plage 5-25 °C, tolérance ±25 °C · CO₂ ×1,2 · PM2.5 ×2 | non chauffé, et un moteur ou un pot de peinture y est attendu |
| **Combles** | plage 10-28 °C, tolérance ±20 °C · PM2.5 ×1,2 | suit la température extérieure par nature — y appliquer la pente d'un salon chauffé noterait « pollué » un simple écart saisonnier |

Deux précisions sur ces ajustements :

**La largeur de tolérance en température est un réglage distinct de la plage
idéale.** Élargir 19-22 °C en 15-26 °C ne fait que déplacer le centre de la
courbe, pas son étalement. C'est un paramètre séparé (`tspan`) qui décide à
partir de quel écart le score tombe à zéro : ±10 °C pour une pièce chauffée,
±25 °C pour un garage.

**Le multiplicateur COV / NOx ne s'applique qu'en mode concentration.** En mode
index, la ligne de base des capteurs Sensirion est déjà recalculée sur les
24 dernières heures, donc déjà relative à la pièce : appliquer un
multiplicateur par-dessus reviendrait à compenser deux fois.

Le score n'est pas une simple moyenne. Comme les indices ATMO et AQI, il est
**plafonné par le pire facteur**, pour qu'un relevé propre ne masque jamais un
polluant critique :

```
score = min( moyenne pondérée ,
             pire facteur d'AÉRATION + 20 ,
             pire facteur de CONFORT  + 25 )
```

`PM1`, `PM4` et `PM10` sont affichés mais **ne comptent pas** dans le score :
PM4 et PM10 sont extrapolés par le capteur et non mesurés, PM1 est quasi
redondant avec PM2.5 en air intérieur.

## Ce que le score n'est pas

Il est **instantané**, pas moyenné sur 24 h — un choix assumé qui privilégie la
réactivité (détecter une cuisson) sur la fidélité à l'exposition chronique.
Pour une vue « exposition moyenne », appliquez un helper *Statistics* au
capteur IQA lui-même, pas à ses entrées.

Score indicatif à usage domestique. Les seuils s'inspirent des lignes
directrices OMS 2021, de l'arrêté du 27/12/2022 et de la norme NF EN 16798-1.
Ce n'est **ni un calcul réglementaire certifié, ni un avis médical**.

## Installation via HACS (dépôt personnalisé)

1. HACS → menu ⋮ → **Custom repositories**
2. URL de ce dépôt, catégorie **Integration** → *Add*
3. Installer, puis **redémarrer Home Assistant**
4. *Paramètres → Appareils et services → Ajouter une intégration → IQA*

## Installer la carte

La carte `iqa-card` s'ajoute comme un second dépôt personnalisé, en catégorie
**Dashboard**. Contrairement à l'intégration, elle ne demande pas de
redémarrage : un rechargement du navigateur suffit.

## Automatisations

Le score est un entier de 0 à 100 : il s'utilise tel quel dans un déclencheur
numérique.

```yaml
trigger:
  - platform: numeric_state
    entity_id: sensor.iqa_salon
    below: 60
```

**Un piège à connaître** : un déclencheur `numeric_state` ne se déclenche pas
sur un état `unavailable` — ce qui arrive dès que le capteur de température ou
d'humidité décroche. Et il peut se déclencher sur la transition au retour de la
disponibilité. Si l'automatisation est critique, ajoutez-y une condition.

Avec l'entité « facteur le plus pénalisant » activée, on cible la cause plutôt
que le symptôme :

```yaml
trigger:
  - platform: numeric_state
    entity_id: sensor.iqa_salon
    below: 60
condition:
  - condition: state
    entity_id: sensor.iqa_salon_facteur_penalisant
    state: co2
action:
  - service: fan.turn_on
    target:
      entity_id: fan.vmc
```

L'état de cette entité est une **clé stable** — `temp`, `humidity`, `co2`,
`voc`, `nox`, `pm25`, ou `none` quand aucun plafond ne mord — et non un libellé
traduit. Une automatisation ne doit pas dépendre de la langue de l'interface.
L'affichage, lui, reste traduit.

## Architecture

Le moteur de notation vit dans `custom_components/iqa/engine.py`, et **tous**
ses barèmes dans `custom_components/iqa/const.py` — source de vérité unique.

La macro Jinja `iqa.jinja` reste disponible comme **solution de repli** : elle
donne exactement le même score sans dépendre de l'intégration. C'est
volontaire — si l'intégration casse, le score reste calculable.

`test_differentiel.py` compare les deux implémentations sur des dizaines de
milliers de cas et **exige zéro écart**, y compris sur le type de chaque valeur
du JSON. C'est ce test qui interdit toute dérive entre le Python et le Jinja.

## Icône

L'icône de l'intégration est l'icône **leaf** de [Lucide](https://lucide.dev),
sous licence ISC, recolorée aux couleurs du projet. Notice de copyright dans
`LICENSES-THIRD-PARTY.md`.

Elle est fournie en deux variantes — `icon.png` pour les thèmes clairs,
`dark_icon.png` pour les thèmes sombres — chacune avec sa version `@2x`,
obligatoire selon les exigences des brands Home Assistant.

Deux emplacements, deux consommateurs différents :

| Emplacement | Lu par | Effet |
|---|---|---|
| `custom_components/iqa/brand/` | Home Assistant 2026.3+ | L'icône s'affiche dans l'interface |
| `brand/` (racine) | Validateur HACS | Conformité de la catégorie Integration |

L'icône n'apparaît **pas** sur la carte Lovelace : c'est l'identité de
l'intégration, visible dans *Paramètres → Appareils et services*.

## Licence

Ce projet est distribué sous **GNU General Public License v3.0 ou ultérieure**.
Copyright (C) 2026 rivland.

Le fichier `LICENSE` contient le texte de la GPL tel que publié par la Free
Software Foundation : il n'est pas modifiable et ne porte donc pas le nom de
l'auteur du logiciel. Le copyright de ce projet figure dans **l'en-tête de
chaque fichier source**, conformément à la section « How to Apply These Terms
to Your New Programs » de la licence.

Les icônes proviennent de Lucide et restent sous licence ISC — voir
`LICENSES-THIRD-PARTY.md`.

## Développement

```bash
# Sans Home Assistant — le moteur seul
python3 test_differentiel.py   # Python ≡ Jinja, aucune tolérance, 36 686 cas
python3 test_engine.py         # cas de référence validés en conditions réelles

# Avec Home Assistant installé — le câblage
python3 test_entites.py        # entités, formulaire, disponibilité, attribut detail
```

Les deux premiers tournent **sans Home Assistant** : ils chargent le moteur par
un paquet synthétique qui contourne `__init__.py`. Ce n'est pas qu'une astuce de
test — c'est le garde-fou qui garantit que `engine.py` reste indépendant de Home
Assistant. Le jour où il importerait quoi que ce soit de HA, ces tests
échoueraient et la CI le dirait.
