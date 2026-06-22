"""Single source of truth for party-member display names.

All character names live in script/names.tsv (the in-game cast/item table). The battle
HUD names (tools/alshark/hudnames.py) and the battle party-name array (rebuild/build.py
party_array_patch) both derive their 9 names from here, so a translator editing names.tsv
propagates everywhere - no duplicated name lists.

PARTY maps the 9 party members (in HUD / array order) to their short-name str_off in
names.tsv. (Odd entries there are the full "First Last" forms; the HUD/array use shorts.)
"""
import os

PARTY = [0, 2, 4, 5, 6, 8, 10, 12, 14]   # names.tsv str_off of each member's short name


def party_names(root):
    """The 9 party display names, in HUD / battle-array order, from names.tsv."""
    import tsv
    by_id = {r["str_off"]: r["english"].strip()
             for r in tsv.read(os.path.join(root, "script", "names.tsv"))}
    return [by_id[str(i)] for i in PARTY]
