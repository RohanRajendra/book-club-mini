#!/usr/bin/env python3
"""Generate the two secrets a shared deployment needs.

    python scripts/make_secrets.py

Prints a passphrase to share with the other member, and the two environment
variables to paste into the deployment. The passphrase is generated rather than
chosen: a passphrase someone invents is the weakest part of this whole design,
and the only real defence against guessing is entropy.

Standalone, like verify_notion.py: standard library only, no app imports.
"""

from __future__ import annotations

import math
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.interface.passphrase import hash_passphrase  # noqa: E402

#: Short, common, unambiguous words — the kind that survive being read down a
#: phone line without spelling. A list this size carries about 6.7 bits per
#: word, well under Diceware's 12.9, so the word *count* has to make up for it.
WORDS = """
anchor amber arrow autumn beacon bridge candle canvas cedar cinder cobalt copper
coral cotton crimson crystal dahlia driftwood ember fathom feather fennel ferry
flint garnet ginger glacier granite harbour hazel heather hollow indigo ivory
jasmine juniper kestrel lantern lattice lichen linen marble meadow mercury mica
mineral mistral morrow nectar nettle nimbus opal orchard osprey paddle pebble
pewter pigeon plover pollen quarry quartz quince ramble raven ribbon rosemary
rowan saffron sandal sapphire sable scarlet sequoia shale shingle silver sorrel
spindle sprig starling sterling stipple sumac tamarind tandem teasel thicket
thimble thistle timber tinder topaz trellis tundra umber velvet verbena vessel
walnut wicker willow window winnow yarrow
""".split()

#: Eight words is ~54 bits. Far below a Diceware passphrase, and far above what
#: matters here: each guess costs the server ~90ms of PBKDF2 plus a deliberate
#: delay, so even 2**40 attempts would take longer than the internet has
#: existed. Entropy would matter if the hash leaked — but anyone who can read it
#: can read the Notion token beside it, which is worth more.
WORD_COUNT = 8


def main() -> int:
    passphrase = " ".join(secrets.choice(WORDS) for _ in range(WORD_COUNT))
    entropy = round(WORD_COUNT * math.log2(len(WORDS)))

    print("Passphrase — share this with the other member, and nothing else:\n")
    print(f"    {passphrase}\n")
    print(f"({WORD_COUNT} words from {len(WORDS)}, roughly {entropy} bits.)\n")
    print("Set these in the deployment's environment. Neither belongs in git:\n")
    print(f"    SESSION_SECRET={secrets.token_urlsafe(48)}")
    print(f"    SITE_PASSPHRASE_HASH={hash_passphrase(passphrase)}")
    print(
        "\nChanging SESSION_SECRET signs everyone out, which is how a session "
        "is revoked.\nChanging the passphrase means regenerating both and "
        "re-sharing the first line."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
