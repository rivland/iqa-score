# IQA : indice de qualité de l'air pour Home Assistant

Intégration qui calcule un **indice de qualité de l'air intérieur de 0 à 100**
à partir de vos capteurs existants. Tout se configure depuis l'interface :
sélecteurs d'entités, aucun YAML à copier-coller.

## Les deux briques

Un dépôt HACS ne porte qu'une seule catégorie, d'où deux dépôts :

| Dépôt | Rôle | Catégorie HACS |
|---|---|---|
| **`iqa-score`** *(celui-ci)* | **calcule** le score et l'expose comme entité | Integration |
| **[`iqa-card`](https://github.com/rivland/iqa-card)** | **affiche** ce score, sans rien recalculer | Dashboard |

Pour chaque pièce configurée, l'intégration crée un capteur `sensor.iqa_<pièce>` :

- **son état** est le score, un entier de 0 à 100 ;
- **son attribut `detail`** porte la décomposition : score, libellé et couleur
  de chaque facteur, facteur le plus pénalisant, plafond appliqué.

C'est une entité Home Assistant ordinaire. Elle s'utilise donc partout comme
n'importe quel capteur numérique : dans les automatisations et les scripts,
dans l'historique et les statistiques, sur n'importe quelle carte standard
(jauge, entité, courbe), dans les alertes et les scènes.

**La carte `iqa-card` est facultative.** Elle ne fait que mettre en forme
l'attribut `detail`, elle ne calcule rien. Le barème n'existe donc qu'à un seul
endroit et l'affichage ne peut pas diverger du score. En contrepartie, la carte
dépend de la structure exacte de `detail` : si elle changeait, la carte
cesserait de fonctionner. Cette structure est donc traitée comme figée, et
toute évolution se fait des deux côtés en même temps.

## Installation

1. HACS → menu ⋮ → **Custom repositories** → [URL de ce dépôt](https://github.com/rivland/iqa-score), catégorie
   **Integration** → *Add*
2. Installer, puis **redémarrer Home Assistant**
3. *Paramètres → Appareils et services → Ajouter une intégration → IQA*

La carte [`iqa-card`](https://github.com/rivland/iqa-card) s'ajoute de la même
façon en catégorie **Dashboard**. Elle ne demande pas de redémarrage, un
rechargement du navigateur suffit.

## Quels capteurs faut-il ?

**Température et humidité sont obligatoires.** Tout le reste est facultatif :
l'intégration fonctionne avec ce que vous avez déjà.

| Capteur | Statut | Poids |
|---|---|---|
| Température | **obligatoire** | 15 % |
| Humidité | **obligatoire** | 10 % |
| CO₂ | optionnel | 30 % |
| PM2.5 | optionnel | 30 % |
| COV | optionnel | 10 % |
| NOx | optionnel | 5 % |
| PM1, PM4, PM10 | optionnels | **hors score** |

Le poids d'un capteur optionnel absent est **redistribué proportionnellement**
sur les autres. Le score reste donc sur 100, et un capteur que vous n'avez pas
ne vous pénalise jamais.

| Ce que vous avez | Répartition réelle |
|---|---|
| Température et humidité seules | Temp. 60 % · Hum. 40 % |
| Plus PM2.5 et COV | Temp. ≈ 23 % · Hum. 15 % · COV 15 % · PM2.5 ≈ 46 % |
| Les six capteurs | les poids du tableau, inchangés |

### Pourquoi température et humidité ne sont pas redistribuables

Parce qu'elles sont les deux seules à ne jamais pouvoir être remplacées. Si
l'une venait à manquer, ses points seraient simplement perdus : le score ne
pourrait plus dépasser 90 sans l'humidité, 85 sans la température, 75 sans les
deux. Un score bas, mais parfaitement crédible, et rien pour signaler que
quelque chose cloche. Il finirait dans l'historique et déclencherait des
automatisations pour rien.

L'intégration coupe court : si la température ou l'humidité est indisponible,
le capteur IQA passe à **`unavailable`**. Pas de score plutôt qu'un mauvais
score.

## Le barème

Valeurs du profil **Salon / Séjour**, COV et NOx en mode index. Ce ne sont pas
des seuils universels : chaque type de pièce les décale.

| Facteur | Poids | 100 points | 0 point |
|---|---|---|---|
| CO₂ | 30 % | ≤ 600 ppm | ≥ 2600 ppm |
| PM2.5 | 30 % | ≤ 5 µg/m³ | ≥ 35 µg/m³ |
| Température | 15 % | écart ≤ 1 °C de l'idéal (19-22 °C) | écart > 10 °C |
| Humidité | 10 % | 40-60 % | 0 % ou 100 % |
| COV | 10 % | index ≤ 100 | index ≥ 400 |
| NOx | 5 % | index ≤ 5 | index ≥ 100 |

`PM1`, `PM4` et `PM10` sont affichés mais **ne comptent pas** dans le score :
PM4 et PM10 sont extrapolés par le capteur plutôt que mesurés, et PM1 est quasi
redondant avec PM2.5 en air intérieur.

### Le plafond par le pire facteur

Le score n'est pas une simple moyenne. Comme les indices ATMO et AQI, il est
plafonné, pour qu'un relevé propre ne masque jamais un polluant critique :

```
score = min( moyenne pondérée ,
             pire facteur d'AÉRATION + 20 ,
             pire facteur de CONFORT  + 25 )
```

**Aération** : CO₂, COV, NOx, PM2.5, et l'humidité quand elle est excessive.
Tout ce qu'ouvrir une fenêtre corrige, d'où une marge courte.

**Confort** : température, et humidité basse. Marge plus large, parce qu'aérer
n'y change rien, mais un air trop sec, trop chaud ou trop froid reste un vrai
facteur de santé.

## Les huit profils de pièce

| Profil | Ce qui change par rapport au salon | Pourquoi |
|---|---|---|
| **Chambre** | idéal 18-20 °C · CO₂ ×0,9 | on y dort plusieurs heures porte fermée : le CO₂ y pèse plus lourd |
| **Bureau** | idéal 20-23 °C · CO₂ ×0,9 | la perte de concentration liée au CO₂ est l'enjeu principal |
| **Cuisine** | PM2.5 ×2 · COV et NOx ×1,5 | une cuisson provoque un pic bref et normal, à ne pas noter comme une pollution |
| **Salle de bain** | idéal 22-24 °C · humidité 50-60 % | l'humidité y monte après chaque douche sans que ce soit un défaut |
| **Cave / Buanderie** | idéal 16-20 °C · humidité 45-65 % | plus humide qu'une pièce de vie ; le risque de moisissure commence au-delà de 65 % |
| **Garage** | plage 5-25 °C, tolérance ±25 °C · CO₂ ×1,2 · PM2.5, COV et NOx ×2 | non chauffé, et un moteur ou un pot de peinture y est attendu |
| **Combles** | plage 10-28 °C, tolérance ±20 °C · PM2.5 et COV ×1,2 | suit la température extérieure par nature : la pente d'un salon chauffé y noterait « pollué » un simple écart saisonnier |

### Deux précisions sur ces réglages

**La température a deux réglages distincts.** La *plage idéale* dit où le score
vaut 100. La *tolérance* dit à partir de quel écart il tombe à 0. Élargir la
plage idéale ne rend donc pas la notation plus indulgente, elle ne fait que la
recentrer. Un salon tolère ±10 °C, un garage ±25 °C.

**Les multiplicateurs COV et NOx ne valent qu'en mode concentration**, c'est à
dire quand le capteur donne des µg/m³. Beaucoup de capteurs renvoient à la
place un index, calculé par rapport à leur propre moyenne des dernières 24 h :
cet index est déjà relatif à la pièce où le capteur se trouve. Lui appliquer en
plus un multiplicateur de pièce corrigerait deux fois la même chose.

## Automatisations

```yaml
trigger:
  - platform: numeric_state
    entity_id: sensor.iqa_salon
    below: 60
```

**Piège** : un déclencheur `numeric_state` ne se déclenche pas sur un état
`unavailable`, ce qui arrive dès que la température ou l'humidité décroche. Il
peut en revanche se déclencher sur la transition au retour. Pour une
automatisation critique, ajoutez une condition.

L'entité optionnelle « facteur le plus pénalisant » permet de cibler la cause
plutôt que le symptôme :

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

Son état est une **clé stable** (`temp`, `humidity`, `co2`, `voc`, `nox`,
`pm25`, ou `none`) et non un libellé traduit : une automatisation ne doit pas
dépendre de la langue de l'interface. L'affichage, lui, reste traduit.

## Limites

Le score est **instantané**, pas moyenné sur 24 h. C'est un choix assumé, qui
privilégie la réactivité, par exemple détecter une cuisson, sur la fidélité à
l'exposition chronique. Pour une vue « exposition moyenne », appliquez un
helper *Statistics* au capteur IQA lui-même, pas à ses entrées.

Pour PM2.5 et NOx, un pic d'origine **extérieure** fait chuter le score alors
qu'aérer aggraverait la situation. Un capteur intérieur seul ne permet pas de
distinguer les deux cas.

Les seuils s'inspirent des lignes directrices OMS 2021, de l'arrêté du
27/12/2022 et de la norme NF EN 16798-1. Score indicatif à usage domestique :
ce n'est **ni un calcul réglementaire certifié, ni un avis médical**.

## Licence

**GNU General Public License v3.0 ou ultérieure**, Copyright (C) 2026 rivland.

Le fichier `LICENSE` est le texte de la GPL publié par la Free Software
Foundation : il n'est pas modifiable et ne porte donc pas le nom de l'auteur du
logiciel. Le copyright figure dans l'en-tête de chaque fichier source.

L'icône est l'icône **leaf** de [Lucide](https://lucide.dev), sous licence ISC,
recolorée aux couleurs du projet. Notice dans `LICENSES-THIRD-PARTY.md`.
