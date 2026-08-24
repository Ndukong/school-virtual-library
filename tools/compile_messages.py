"""Compile locale catalogs to .mo without GNU gettext.

The project's Windows dev image ships no msgfmt/xgettext, so this Babel-based
replacement keeps the runtime path standard (Django still reads django.mo).
On a machine WITH GNU gettext, `compilemessages` remains equivalent.

    python tools/compile_messages.py

A compile failure must be treated like any other red gate: fix the .po, do
not ship an English-fallback UI silently.
"""

from pathlib import Path

from babel.messages.mofile import write_mo
from babel.messages.pofile import read_po

ROOT = Path(__file__).resolve().parent.parent


def main():
    entries = 0
    for po_path in sorted(ROOT.glob("locale/*/LC_MESSAGES/*.po")):
        with po_path.open("rb") as source:
            catalog = read_po(source)
        mo_path = po_path.with_suffix(".mo")
        with mo_path.open("wb") as target:
            write_mo(target, catalog)
        entries += len(catalog)
        print(f"compiled {po_path.relative_to(ROOT)} -> {mo_path.name} ({len(catalog)} entries)")
    print(f"done, {entries} catalog entries in total")


if __name__ == "__main__":
    main()