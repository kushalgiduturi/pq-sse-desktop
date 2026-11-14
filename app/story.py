"""The one story the whole app tells, and the badges of its characters."""
from __future__ import annotations

IDEA = ("Alice keeps her files locked, yet Bob can still search them through the cloud, and the cloud learns "
        "almost nothing, even against future quantum computers.")

# name -> (letter, color, role in the story, role in the system)
CHARACTERS = {
    "Alice": ("A", "#1f6fb2", "a hospital records manager", "the Data Owner: she owns the documents and decides who may read what"),
    "Bob": ("B", "#7a4fb5", "a doctor", "a Receiver: he may search and read only the groups Alice approved"),
    "Carol": ("C", "#8a5a9e", "a doctor", "a Receiver, like Bob, with her own permissions"),
    "Cloud": ("S", "#5f6b7a", "a rented storage company",
              "stores everything for Alice but is not trusted: it might peek, lie, drop results or send old data"),
}
TAG_COLORS = {"alice": "#1f6fb2", "receiver": "#7a4fb5", "cloud": "#5f6b7a", "security": "#b5651d"}

ANALOGIES = [
    ("Documents", "letters in locked boxes"),
    ("Keyword search", "asking the cloud to find boxes without opening them"),
    ("Search token", "a sealed search slip only a doctor can make and only the cloud can read"),
    ("Signature", "Alice's tamper-proof stamp"),
    ("Revocation", "changing the locks and telling only the people still allowed in"),
]


def badge(name: str) -> str:
    """Rich text badge: a colored square with the character's letter, then the name as text."""
    letter, color, _, _ = CHARACTERS[name]
    return (f'<span style="background-color:{color}; color:white; font-weight:700;">&nbsp;{letter}&nbsp;</span>'
            f'&nbsp;<b>{name}</b>')


def cast_html() -> str:
    rows = "".join(f"<p>{badge(name)}: {story}. In the system: {role}.</p>"
                   for name, (_, _, story, role) in CHARACTERS.items())
    return rows


def analogies_html() -> str:
    return "<ul>" + "".join(f"<li><b>{real}</b>: {like}</li>" for real, like in ANALOGIES) + "</ul>"
