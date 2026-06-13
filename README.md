# OptiFLUX

Application Streamlit d'optimisation logistique hospitalière multi-flux.

OptiFLUX lit un fichier Excel de paramétrage des flux logistiques hospitaliers et produit une proposition opérationnelle complète : tournées véhicules, postes chauffeurs, planning des quais, indicateurs et export Excel détaillé.

## 1. Installation

Prérequis : Python 3.10 ou supérieur.

```bash
python -m venv venv
source venv/bin/activate  # Windows : venv\Scripts\activate
pip install -r requirements.txt
```

## 2. Lancement

```bash
streamlit run app.py
```

## 3. Structure attendue du fichier Excel

Le classeur doit contenir les onglets suivants :

- `param RH` : durée de vacation, pause, heure début mini, heure fin max.
- `param Sites` : sites, adresses, présence de quai, compatibilité par véhicule.
- `param Véhicules` : types de véhicules, dimensions, stationnement initial, compatibilité contenants, temps de quai et manutention.
- `param Contenants` : dimensions et poids des contenants.
- `matrice Durée` : temps inter-sites en minutes.
- `matrice Dist` : distances inter-sites en kilomètres.
- `LISTES` : listes de référence.
- `M flux` : flux à transporter, quantités par jour, fenêtres horaires, statuts propre/sale, mutualisations.

Les horaires Excel peuvent être fournis sous forme de `datetime.time`, fraction de journée ou `HH:MM`. OptiFLUX les convertit en minutes depuis minuit.

## 4. Guide d'utilisation

1. **Import & Contrôles** : charger le fichier Excel et corriger les éventuelles erreurs bloquantes.
2. **Paramètres** : ajuster les paramètres RH, le facteur circulation, la flotte disponible et la capacité des quais.
3. **Simulation** : choisir les jours et fonctions support, puis lancer l'optimisation.
4. **Résultats** : consulter les indicateurs, le Gantt, la timeline et le planning des quais.
5. **Export** : générer un fichier Excel complet de résultats.

## 5. Hypothèses métier retenues

- Modèle de problème : VRPPDTW, c'est-à-dire pickup & delivery avec fenêtres temporelles.
- Plusieurs flux distincts peuvent être groupés dans un même circuit, sous réserve que chaque pickup précède son delivery.
- Les flux de type `Fréquences` sont ignorés ; seuls les flux `Volume` avec quantité strictement positive sont simulés.
- Les formules Excel non calculées dans les colonnes de quantité bloquent l'import.
- Les flux volumineux sont éclatés en voyages partiels lorsque la quantité dépasse la capacité du meilleur véhicule compatible.
- Chaque partie éclatée hérite de la fenêtre horaire du flux d'origine et peut être positionnée librement dans cette fenêtre.
- Les tournées mutualisées imposent que les flux portant le même nom soient insérés dans la même tournée.
- Le calcul de capacité utilise une surface 2D discrète avec rotation des contenants, complétée par une contrainte de poids.
- La hauteur des contenants n'est pas prise en compte, car elle n'est pas renseignée dans le fichier source.
- Les sites côte à côte avec durée et distance nulles conservent une mise à quai distincte.
- La compatibilité sans quai est déterminée par `manu_sans_quai is not None`, et non par la présence d'un hayon.
- Un poste chauffeur commence et finit au stationnement initial, inclut prise de poste, pause et fin de poste.
- Le changement de chauffeur n'est autorisé qu'au stationnement initial.
- La désinfection est modélisée comme une opération au stationnement initial.

## 6. Optimisation : précision et limites

Le problème complet mélange pickup & delivery, fenêtres temporelles, capacités, compatibilités site/véhicule/contenant, propre/sale, quais et RH. C'est un problème combinatoire difficile. OptiFLUX applique donc :

1. des contrôles de faisabilité préalables bloquants ;
2. un éclatement contrôlé des flux volumineux ;
3. une insertion constructive respectant toutes les contraintes dures ;
4. une amélioration locale OR-opt inter-routes ;
5. une validation finale des invariants.

Cette approche vise la meilleure solution opérationnelle valide dans le budget de calcul. Elle ne prétend pas prouver l'optimalité mathématique globale sur de très grands jeux de données, car cela demanderait un solveur exact et des temps de calcul potentiellement incompatibles avec une application métier interactive.

Le dépôt prévoit `ortools` en dépendance optionnelle pour permettre, dans une évolution ultérieure, de résoudre exactement certains sous-problèmes de taille maîtrisée.

## 7. Exports générés

L'export Excel contient :

- `Indicateurs`
- `Synthèse flotte`
- `Synthèse chauffeurs`
- `Tournées véhicules`
- `Planning chauffeurs`
- `Planning quais`
- `Flux transportés`
- `Flux non servis`
- `Contrôles contraintes`

## 8. Procédure de débogage

1. Vérifier l'onglet `Import & Contrôles`.
2. Corriger d'abord les erreurs bloquantes : onglets, colonnes, sites inconnus, contenants inconnus, formules dans les quantités.
3. Si les flux sont infaisables, consulter les détails de `T_min`, de fenêtre disponible et d'incompatibilité véhicule/site.
4. Si des conflits de quai apparaissent, augmenter la capacité quai ou assouplir les fenêtres horaires.
5. Lancer les tests unitaires :

```bash
pytest
```

## 9. Architecture

```text
optiflux/
├── app.py
├── config.py
├── data_loader.py
├── models.py
├── validators.py
├── preprocessing.py
├── compatibility.py
├── time_windows.py
├── capacity.py
├── fleet_generator.py
├── optimizer.py
├── route_builder.py
├── driver_scheduler.py
├── dock_scheduler.py
├── visualization.py
├── outputs.py
├── engine.py
├── tests/
├── requirements.txt
└── README.md
```
