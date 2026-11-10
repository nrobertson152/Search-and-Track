"""Battle missions: two forces that fight on their own, the player commanding one of them.

The battle layer sits on top of the air-defense simulation. The player's side keeps its
radar network, its track picture and its fighter control (gci): the battle staff commits
interceptors and fires missiles on what the radars have actually found. Everything else —
the enemy's raids, escorts, jammers and reconnaissance, every ship, every anti-ship missile,
and the player's own strike, early-warning and support aircraft — is flown by the battle AI,
which for the enemy works from the enemy's own sensor picture. Radar therefore matters both
ways: a jammed picture costs us intercepts; an emitting fleet gets found.

Modules: core (setup, tick hooks, events, the end), naval (ships, anti-ship missiles, ship
air defense), air (air-group AI), combat (air-to-air shots, evasion, damage), sense (each
side's picture), staff (our battle staff and the commander's decisions), director (phases,
pacing, mission conditions and actions).
"""
from .core import event, mid_step, post_step, pre_step, setup  # noqa: F401
