"""Starting Orders of Battle — plain data constant.

Encodes specs/GameDesign/version1/starting_ob.md as Python dicts consumed
by init_game().  Each entry has:
  species_id    int
  polities      list of polity dicts (name, processing_order, treasury_ru,
                  disposition overrides)
  hulls         list of (hull_type, count) tuples — fleet hulls
  sdbs          int — homeworld SDB count
  armies        int — starting Army formations
  garrisons     int — starting Garrison formations

Species disposition defaults come from the Species table (M12+); for now the
values here are used directly by init_game() via the WorldStub species data.
The overrides dict lets per-polity values differ from the species baseline
(used for Nhaveth courts and Human polities).
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Species IDs (must match seed_species.py and world/names.py)
# ---------------------------------------------------------------------------
KREETH    = 1
VASHORI   = 2
KRAATHI   = 3
NAKHAVI   = 4
SKHARRI   = 5
VAELKHI   = 6
SHEKHARI  = 7
GOLVHAAN  = 8
NHAVETH   = 9
VARDHEK   = 10
HUMAN     = 11


# ---------------------------------------------------------------------------
# OB table
# ---------------------------------------------------------------------------
# hull counts: list of (hull_type, count)
# sdbs, armies, garrisons: homeworld defence units

OB_DATA: list[dict] = [

    # -----------------------------------------------------------------------
    # Kreeth — maximum aggression, capital-heavy, no colony transports
    # -----------------------------------------------------------------------
    {
        "species_id": KREETH,
        "polities": [
            {"name": "Kreeth Dominion", "processing_order": 1,
             "treasury_ru": 25.0,
             "aggression": 0.95, "expansionism": 0.90, "risk_appetite": 0.40},
        ],
        "hulls": [
            ("capital", 2), ("old_capital", 3), ("cruiser", 1),
            ("escort", 3), ("scout", 1),
        ],
        "sdbs": 6, "armies": 4, "garrisons": 6,
    },

    # -----------------------------------------------------------------------
    # Vashori — diplomatic; light combat, heavy logistics
    # -----------------------------------------------------------------------
    {
        "species_id": VASHORI,
        "polities": [
            {"name": "Vashori Compact", "processing_order": 2,
             "treasury_ru": 25.0,
             "aggression": 0.40, "expansionism": 0.30, "risk_appetite": 0.60},
        ],
        "hulls": [
            ("capital", 1), ("old_capital", 1), ("cruiser", 1),
            ("escort", 4), ("transport", 2), ("colony_transport", 2), ("scout", 2),
        ],
        "sdbs": 3, "armies": 1, "garrisons": 4,
    },

    # -----------------------------------------------------------------------
    # Kraathi — G'naak crusade; troop + colony transports
    # -----------------------------------------------------------------------
    {
        "species_id": KRAATHI,
        "polities": [
            {"name": "Kraathi Crusade", "processing_order": 3,
             "treasury_ru": 25.0,
             "aggression": 0.75, "expansionism": 0.95, "risk_appetite": 0.45},
        ],
        "hulls": [
            ("capital", 1), ("old_capital", 2), ("cruiser", 2),
            ("escort", 4), ("troop", 1), ("colony_transport", 2), ("scout", 1),
        ],
        "sdbs": 5, "armies": 3, "garrisons": 4,
    },

    # -----------------------------------------------------------------------
    # Nakhavi — curious, minimal military, many scouts
    # -----------------------------------------------------------------------
    {
        "species_id": NAKHAVI,
        "polities": [
            {"name": "Nakhavi Reach", "processing_order": 4,
             "treasury_ru": 25.0,
             "aggression": 0.45, "expansionism": 0.40, "risk_appetite": 0.80},
        ],
        "hulls": [
            ("capital", 1), ("old_capital", 1), ("cruiser", 2),
            ("escort", 3), ("transport", 1), ("colony_transport", 1), ("scout", 3),
        ],
        "sdbs": 2, "armies": 1, "garrisons": 2,
    },

    # -----------------------------------------------------------------------
    # Skharri — maximum aggression + risk; capital-heavy; honour = offence
    # -----------------------------------------------------------------------
    {
        "species_id": SKHARRI,
        "polities": [
            {"name": "Skharri Pride", "processing_order": 5,
             "treasury_ru": 25.0,
             "aggression": 0.95, "expansionism": 0.90, "risk_appetite": 0.90},
        ],
        "hulls": [
            ("capital", 2), ("old_capital", 3), ("cruiser", 2),
            ("escort", 5), ("troop", 1), ("scout", 1),
        ],
        "sdbs": 2, "armies": 4, "garrisons": 2,
    },

    # -----------------------------------------------------------------------
    # Vaelkhi — territorial; escort-heavy, patient defenders
    # -----------------------------------------------------------------------
    {
        "species_id": VAELKHI,
        "polities": [
            {"name": "Vaelkhi Choth", "processing_order": 6,
             "treasury_ru": 25.0,
             "aggression": 0.55, "expansionism": 0.30, "risk_appetite": 0.70},
        ],
        "hulls": [
            ("capital", 1), ("old_capital", 2), ("cruiser", 2),
            ("escort", 6), ("colony_transport", 1), ("scout", 1),
        ],
        "sdbs": 4, "armies": 2, "garrisons": 4,
    },

    # -----------------------------------------------------------------------
    # Shekhari — traders; most scouts, most transports, light combat
    # -----------------------------------------------------------------------
    {
        "species_id": SHEKHARI,
        "polities": [
            {"name": "Shekhari Exchange", "processing_order": 7,
             "treasury_ru": 25.0,
             "aggression": 0.45, "expansionism": 0.55, "risk_appetite": 0.75},
        ],
        "hulls": [
            ("capital", 1), ("old_capital", 1), ("cruiser", 1),
            ("escort", 3), ("transport", 2), ("colony_transport", 2), ("scout", 3),
        ],
        "sdbs": 2, "armies": 1, "garrisons": 3,
    },

    # -----------------------------------------------------------------------
    # Golvhaan — peaceful; no Capitals, high SDB infrastructure
    # -----------------------------------------------------------------------
    {
        "species_id": GOLVHAAN,
        "polities": [
            {"name": "Golvhaan Reach", "processing_order": 8,
             "treasury_ru": 25.0,
             "aggression": 0.30, "expansionism": 0.35, "risk_appetite": 0.45},
        ],
        "hulls": [
            ("old_capital", 2), ("cruiser", 2),
            ("escort", 4), ("transport", 2), ("colony_transport", 1), ("scout", 1),
        ],
        "sdbs": 6, "armies": 1, "garrisons": 4,
    },

    # -----------------------------------------------------------------------
    # Nhaveth — three courts; faction_tendency 0.90 → multiple polities
    # -----------------------------------------------------------------------
    {
        "species_id": NHAVETH,
        "polities": [
            {"name": "Nhaveth Court A", "processing_order": 9,
             "treasury_ru": 12.0,
             "aggression": 0.85, "expansionism": 0.90, "risk_appetite": 0.65},
            {"name": "Nhaveth Court B", "processing_order": 10,
             "treasury_ru": 8.0,
             "aggression": 0.85, "expansionism": 0.85, "risk_appetite": 0.70},
            {"name": "Nhaveth Court C", "processing_order": 11,
             "treasury_ru": 5.0,
             "aggression": 0.70, "expansionism": 0.70, "risk_appetite": 0.55},
        ],
        # Hulls split across courts at init (Court A gets the lion's share;
        # init_game distributes proportionally by treasury weight)
        "hulls_by_polity": [
            # Court A
            [("capital", 1), ("old_capital", 2), ("cruiser", 2),
             ("escort", 3), ("troop", 1), ("scout", 1)],
            # Court B
            [("old_capital", 1), ("cruiser", 2), ("escort", 3),
             ("troop", 1), ("scout", 1)],
            # Court C
            [("cruiser", 1), ("escort", 2), ("scout", 1)],
        ],
        "sdbs_by_polity": [3, 2, 1],
        "armies_by_polity": [3, 2, 2],
        "garrisons_by_polity": [3, 2, 2],
    },

    # -----------------------------------------------------------------------
    # Vardhek — Long View; most colony transports, high SDB
    # -----------------------------------------------------------------------
    {
        "species_id": VARDHEK,
        "polities": [
            {"name": "Vardhek Roidhunate", "processing_order": 12,
             "treasury_ru": 25.0,
             "aggression": 0.70, "expansionism": 0.95, "risk_appetite": 0.35},
        ],
        "hulls": [
            ("capital", 1), ("old_capital", 2), ("cruiser", 2),
            ("escort", 4), ("transport", 1), ("colony_transport", 3), ("scout", 1),
        ],
        "sdbs": 6, "armies": 2, "garrisons": 4,
    },

    # -----------------------------------------------------------------------
    # Human — three polities from Orwell's 1984:
    #   Oceania   (Ingsoc / English Socialism) — Earth's dominant superstate
    #   Eurasia   (Neo-Bolshevism) — continental Eurasian bloc
    #   Eastasia  (Death-Worship / Obliteration of the Self) — Far Eastern bloc
    # -----------------------------------------------------------------------
    {
        "species_id": HUMAN,
        "polities": [
            {"name": "Oceania", "processing_order": 13,
             "treasury_ru": 14.0,
             "aggression": 0.65, "expansionism": 0.80, "risk_appetite": 0.55},
            {"name": "Eurasia", "processing_order": 14,
             "treasury_ru": 8.0,
             "aggression": 0.60, "expansionism": 0.75, "risk_appetite": 0.60},
            {"name": "Eastasia", "processing_order": 15,
             "treasury_ru": 6.0,
             "aggression": 0.55, "expansionism": 0.70, "risk_appetite": 0.70},
        ],
        "hulls_by_polity": [
            # Oceania — dominant (Earth / inner system)
            [("capital", 1), ("old_capital", 2), ("cruiser", 2),
             ("escort", 4), ("transport", 1), ("colony_transport", 1), ("scout", 1)],
            # Eurasia — mid-weight (Mars / inner colonies)
            [("old_capital", 1), ("cruiser", 2), ("escort", 4),
             ("colony_transport", 1), ("scout", 2)],
            # Eastasia — outer system
            [("cruiser", 1), ("escort", 3), ("transport", 2),
             ("colony_transport", 1), ("scout", 2)],
        ],
        "sdbs_by_polity": [4, 3, 2],
        "armies_by_polity": [3, 2, 1],
        "garrisons_by_polity": [4, 3, 2],
        # Pre-generated names seeded into NamePool at init_game time.
        # All three Human polities share species_id=11 and draw from one pool.
        # Hull names are broadly 1984-themed; colony names follow the same palette.
        "name_pool": {
            "hull": [
                # Ingsoc / Oceania
                "Victory", "Big Brother", "Minitrue", "Minipax", "Miniluv",
                "Miniplenty", "Telescreen", "Thoughtpol", "Doublethink",
                "Newspeak", "Ingsoc", "Room 101", "Unperson", "Prolefeed",
                "Duckspeak", "Crimestop", "Blackwhite", "Hate Week",
                "Two Minutes Hate", "O'Brien", "Parsons", "Ampleforth",
                "Syme", "Charrington", "Brotherhood",
                # Eurasia
                "Volga", "Neva", "Moskva", "Dnieper", "Ural",
                "Sibir", "Tundra", "Steppes", "Taiga", "Baikal",
                "Arkhangelsk", "Leningrad", "Stalingrad", "Kursk",
                "Sevastopol", "Vladivostok", "Kamchatka", "Yenisei",
                "Lena", "Amur", "Kolyma",
                # Eastasia
                "Yangtze", "Huang He", "Pearl River", "Han",
                "Tang", "Ming", "Qin", "Zhou", "Song",
                "Forbidden City", "Dragon Throne", "Jade Gate",
                "Silk Road", "Great Wall", "Gobi", "Sichuan",
                "Yunnan", "Canton", "Nanking", "Peking", "Chungking",
            ],
            "system": [
                "Airstrip Two", "Airstrip Three", "Airstrip Four",
                "Victory Colony", "Ingsoc Reach", "Oceania Prime",
                "Minipax Station", "Thoughtcrime Drift", "Prole World",
                "New Moscow", "Eastern Front", "Siberian Reach",
                "Volga Station", "Ural Outpost", "Red Frontier",
                "Eastern Capital", "Yangtze Outpost", "Great Wall Station",
                "Dragon Reach", "Jade Colony", "Han Frontier",
            ],
            "body": [
                "Airstrip One", "Victory Square", "Ministry World",
                "Hate Plain", "Prole District", "Outer Party Moon",
                "Red Plain", "Volga Shore", "Steppe Moon", "Ural Rock",
                "Dragon Moon", "Jade Plain", "Han Shore", "Ming Rock",
            ],
        },
    },
]
