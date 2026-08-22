"""Embed the signature script font directly into a .docx's own bytes.

Signature-line names (customer_signature_name, provider_representative,
etc.) are printed in "Great Vibes", a cursive font, so a printed name reads
like a real signature. The font must render correctly on every machine that
ever runs this app's LibreOffice conversion step, not just machines that
happen to have it installed system-wide -- so instead of relying on a
system font, the font is embedded straight into each template .docx
(ECMA-376 CT_Fonts / w:embedRegular, unobfuscated -- the same form
LibreOffice itself writes when IT embeds a font on save, confirmed via a
direct docx-to-images.py render: an unmodified system with the font not
installed still renders it correctly once embedded). Embedding happens
once, into the template files committed to the repo; `renderer.py`'s
load-substitute-save round trip preserves the embedded part unchanged (also
verified directly), so nothing at generation time needs to know this
happened.
"""

from __future__ import annotations

from docx import Document
from docx.opc.constants import CONTENT_TYPE as CT
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.opc.packuri import PackURI
from docx.opc.part import Part
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt
from docx.text.run import Run
from lxml import etree

from desktop_app.backend.paths import resource_path

SIGNATURE_FONT_NAME = "Great Vibes"
SIGNATURE_FONT_SIZE = Pt(18)
SIGNATURE_FONT_PATH = resource_path("desktop_app", "data", "source", "fonts", "GreatVibes-Regular.ttf")

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


def embed_signature_font(document: Document) -> None:
    """Embed SIGNATURE_FONT_PATH into `document` and flip on font embedding.

    Safe to call more than once on the same Document -- a second call is a
    no-op if a "Great Vibes" entry is already present in the font table.
    """
    font_table_part = document.part.part_related_by(RT.FONT_TABLE)
    root = etree.fromstring(font_table_part.blob)
    if root.find(f'{_W}font[@{_W}name="{SIGNATURE_FONT_NAME}"]') is not None:
        return

    font_bytes = SIGNATURE_FONT_PATH.read_bytes()
    font_part = Part(
        PackURI(f"/word/fonts/{SIGNATURE_FONT_NAME.replace(' ', '')}.fntdata"),
        CT.X_FONT_TTF,
        font_bytes,
        document.part.package,
    )
    r_id = font_table_part.relate_to(font_part, RT.FONT)

    font_el = etree.SubElement(root, f"{_W}font")
    font_el.set(f"{_W}name", SIGNATURE_FONT_NAME)
    embed_el = etree.SubElement(font_el, f"{_W}embedRegular")
    embed_el.set(f"{_R}id", r_id)
    font_table_part._blob = etree.tostring(  # noqa: SLF001 -- Part.blob has no public setter
        root, xml_declaration=True, encoding="UTF-8", standalone=True,
    )

    settings_el = document.settings.element
    if settings_el.find(qn("w:embedTrueTypeFonts")) is None:
        settings_el.insert(0, OxmlElement("w:embedTrueTypeFonts"))


def apply_signature_font(run: Run) -> None:
    """Style one run as a printed signature name: the embedded script font,
    not bold (script faces already read as distinct; simulated bold on a
    script face looks broken), a bit larger than body text so it reads as
    a real signature rather than a caption."""
    run.font.name = SIGNATURE_FONT_NAME
    run.font.size = SIGNATURE_FONT_SIZE
    run.font.bold = False
    r_pr = run._r.get_or_add_rPr()  # noqa: SLF001 -- matches this codebase's existing rPr/rFonts pattern
    fonts = r_pr.get_or_add_rFonts()
    for key in ("ascii", "hAnsi", "eastAsia", "cs"):
        fonts.set(qn(f"w:{key}"), SIGNATURE_FONT_NAME)
