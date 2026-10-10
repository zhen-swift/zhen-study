"""Matplotlib settings shared by every figure in the paper.

Three of these are not taste.  `pdf.fonttype 42` embeds TrueType rather than Type 3,
which IEEE's submission checker rejects outright.  Every figure is drawn at the
3.5 in width of a single IEEEtran column, so nothing is scaled in LaTeX and the font
sizes in the figure are the font sizes on the page.  And identity is carried by marker
and dash as well as by hue, so the figures survive greyscale printing and the two
colour-vision cases the palette was validated against.
"""

from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

#: A single IEEEtran column.
COLUMN_IN = 3.5
#: The full two-column text width, for the one figure that needs it.
TEXTWIDTH_IN = 7.16

#: Validated with the dataviz skill's checker at the light surface: lightness band,
#: chroma floor, CVD separation and the normal-vision floor all pass.  Contrast for
#: the aqua slot sits just under 3:1, which obligates the direct labels and the
#: companion tables the paper carries anyway.
BLUE = "#2a78d6"
ORANGE = "#eb6834"
VIOLET = "#4a3aa7"
AQUA = "#1baf7a"

INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#8a8a85"
GRID = "#dcdcd8"

#: Colour by tool family, never by rank: the same condition is the same hue in every
#: figure, and a figure that drops a condition does not repaint the survivors.
FAMILY_COLOR = {
    "netsanity": BLUE,
    "nmap-priv": ORANGE,
    "nmap-unpriv": VIOLET,
    "naming": AQUA,
}

FAMILY_MARKER = {
    "netsanity": "o",
    "nmap-priv": "s",
    "nmap-unpriv": "^",
    "naming": "D",
}


def family(condition_id: str) -> str:
    if condition_id == "nmap.naming.broadcast":
        return "naming"
    if condition_id.startswith("ns."):
        return "netsanity"
    return "nmap-priv" if ".priv." in condition_id else "nmap-unpriv"


def color(condition_id: str) -> str:
    return FAMILY_COLOR[family(condition_id)]


def marker(condition_id: str) -> str:
    return FAMILY_MARKER[family(condition_id)]


def apply() -> None:
    plt.rcParams.update({
        "pdf.fonttype": 42,          # TrueType. IEEE rejects Type 3.
        "ps.fonttype": 42,
        "svg.fonttype": "none",
        "font.family": "serif",
        "font.serif": ["Times New Roman", "Nimbus Roman", "DejaVu Serif"],
        "mathtext.fontset": "stix",
        "font.size": 7.0,
        "axes.labelsize": 7.0,
        "axes.titlesize": 7.5,
        "xtick.labelsize": 6.5,
        "ytick.labelsize": 6.5,
        "legend.fontsize": 6.2,
        "axes.edgecolor": INK_2,
        "axes.labelcolor": INK,
        "text.color": INK,
        "xtick.color": INK_2,
        "ytick.color": INK_2,
        "axes.linewidth": 0.6,
        "xtick.major.width": 0.5,
        "ytick.major.width": 0.5,
        "xtick.major.size": 2.5,
        "ytick.major.size": 2.5,
        "lines.linewidth": 1.0,
        "lines.markersize": 3.2,
        "grid.color": GRID,
        "grid.linewidth": 0.4,
        "legend.frameon": False,
        "legend.handlelength": 1.6,
        "legend.borderaxespad": 0.2,
        "legend.labelspacing": 0.25,
        "legend.columnspacing": 1.0,
        "figure.dpi": 200,
        "savefig.dpi": 200,
        "savefig.bbox": "tight",
        "savefig.pad_inches": 0.01,
    })


def recessive(ax, *, x=False, y=True) -> None:
    """Grid and spines stay behind the data, which is the only thing being read."""
    ax.set_axisbelow(True)
    if y:
        ax.yaxis.grid(True, linestyle="-", linewidth=0.4, color=GRID)
    if x:
        ax.xaxis.grid(True, linestyle="-", linewidth=0.4, color=GRID)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)


def save(fig, stem: str, outdir) -> None:
    from pathlib import Path
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    fig.savefig(outdir / f"{stem}.pdf")
    fig.savefig(outdir / f"{stem}.png")
    print(f"  {stem}.pdf  {stem}.png")
