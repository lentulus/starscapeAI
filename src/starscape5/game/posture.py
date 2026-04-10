"""Strategic posture — weighted draw from {Expand, Consolidate, Prepare, Prosecute}.

Posture is not a state machine.  It is redrawn each tick.  The weights are
driven by species disposition parameters and current game state.

Pure functions only; no DB access.  Takes a GameStateSnapshot as input.
"""

from __future__ import annotations

from enum import Enum
from random import Random

from .snapshot import GameStateSnapshot


class Posture(str, Enum):
    EXPAND      = "Expand"
    CONSOLIDATE = "Consolidate"
    PREPARE     = "Prepare"
    PROSECUTE   = "Prosecute"


def posture_weights(snap: GameStateSnapshot) -> dict[Posture, float]:
    """Return un-normalised weights for each posture.

    Rules (all additive from a base):

    Expand:
      base 1.0
      + expansionism × 2.0
      − aggression × 0.5          (aggressive polities spend time preparing)
      + 1.0 if not at war
      − 2.0 if at war              (prosecute war, not expansion)

    Consolidate:
      base 0.5
      + (1 − expansionism) × 1.0  (low expansionism → build at home)
      + 0.5 if treasury < 10 RU   (forced consolidation)

    Prepare:
      base 0.3
      + aggression × 1.5          (aggressive polities arm up)
      + 0.5 per contacted polity  (each contact is a potential war)
      − 1.0 if at war             (already at war; shift to Prosecute)

    Prosecute:
      base 0.0
      + 3.0 per polity at war     (dominating weight when at war)
      + aggression × 1.0
    """
    p = snap.polity
    at_war      = bool(p.at_war_with)
    n_wars      = len(p.at_war_with)
    n_contacts  = len(p.in_contact_with)

    expand_w = (
        1.0
        + p.expansionism * 2.0
        - p.aggression   * 0.5
        + (1.0 if not at_war else -2.0)
    )

    consolidate_w = (
        0.5
        + (1.0 - p.expansionism) * 1.0
        + (0.5 if p.treasury_ru < 10.0 else 0.0)
    )

    prepare_w = (
        0.3
        + p.aggression * 1.5
        + n_contacts * 0.5
        - (1.0 if at_war else 0.0)
    )

    prosecute_w = (
        n_wars * 3.0
        + p.aggression * 1.0
    )

    return {
        Posture.EXPAND:      max(0.0, expand_w),
        Posture.CONSOLIDATE: max(0.0, consolidate_w),
        Posture.PREPARE:     max(0.0, prepare_w),
        Posture.PROSECUTE:   max(0.0, prosecute_w),
    }


def draw_posture(snap: GameStateSnapshot, rng: Random) -> Posture:
    """Draw a posture for this tick by weighted random selection."""
    weights = posture_weights(snap)
    total = sum(weights.values())
    if total <= 0:
        return Posture.CONSOLIDATE

    r = rng.random() * total
    cumulative = 0.0
    for posture, w in weights.items():
        cumulative += w
        if r < cumulative:
            return posture
    return Posture.CONSOLIDATE  # fallback
