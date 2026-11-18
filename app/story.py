"""The one idea the whole app explains, and the badges of the three roles."""
from __future__ import annotations

IDEA = ("The data owner keeps documents encrypted, yet approved receivers can still search them through the cloud server, "
        "and the server learns almost nothing, even against future quantum computers.")

# name -> (letter, color, short description, role in the system)
CHARACTERS = {
    "Data owner": ("O", "#1f6fb2", "owns the documents",
                   "holds the keys, adds documents, and decides who may search which group"),
    "Receiver A": ("A", "#7a4fb5", "a receiver", "may search and read only the groups the data owner approved"),
    "Receiver B": ("B", "#8a5a9e", "a second receiver", "has their own permissions, separate from Receiver A"),
    "Cloud server": ("S", "#5f6b7a", "rented storage",
                     "stores everything for the data owner but is not trusted: it might peek, lie, drop results or send old data"),
}
TAG_COLORS = {"alice": "#1f6fb2", "receiver": "#7a4fb5", "cloud": "#5f6b7a", "security": "#b5651d"}

ANALOGIES = [
    ("Documents", "letters in locked boxes"),
    ("Keyword search", "asking the cloud server to find boxes without opening them"),
    ("Search token", "a sealed search slip only a receiver can make and only the server can read"),
    ("Signature", "the data owner's tamper-proof stamp"),
    ("Revocation", "changing the locks and telling only the people still allowed in"),
]


def badge(name: str) -> str:
    """Rich text badge: a colored square with the role's letter, then the name as text."""
    letter, color, _, _ = CHARACTERS[name]
    return (f'<span style="background-color:{color}; color:white; font-weight:700;">&nbsp;{letter}&nbsp;</span>'
            f'&nbsp;<b>{name}</b>')


def cast_html() -> str:
    rows = "".join(f"<p>{badge(name)}: {short}. In the system: {role}.</p>"
                   for name, (_, _, short, role) in CHARACTERS.items())
    return rows


def analogies_html() -> str:
    return "<ul>" + "".join(f"<li><b>{real}</b>: {like}</li>" for real, like in ANALOGIES) + "</ul>"
