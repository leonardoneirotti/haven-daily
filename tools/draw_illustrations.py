"""The 17 line drawings of the newspaper view (#101, spec §7.9): one per "affects" tag, plus a general
port drawing, drawn for Haven Daily (no photo, no real event, ship, company or logo).

    python tools/draw_illustrations.py    # writes static/illustrations/*.svg

Site tokens only: ink #0f2231 (lines), accent #0f6e8c (one detail), water #dbe7ed (tile), land
#efebe3, white #ffffff, water-line #6f97ad. No text, no flag colours. The committed files must be
what this script draws (tests/test_newspaper.py).
"""
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "static" / "illustrations"

INK, ACC, WATER, LAND, WHITE, LINE = "#0f2231", "#0f6e8c", "#dbe7ed", "#efebe3", "#ffffff", "#6f97ad"
HEAD = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 160 100" fill="none" stroke="{INK}" '
        f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        f'<rect width="160" height="100" rx="8" fill="{WATER}" stroke="none"/>')
QUAY = f'<path d="M0 74H160V92a8 8 0 0 1-8 8H8a8 8 0 0 1-8-8Z" fill="{LAND}" stroke="none"/><path d="M0 74H160"/>'
WAVES = f'<path d="M14 86q6-4 12 0t12 0M110 88q6-4 12 0t12 0" stroke="{LINE}"/>'


def crane(x):
    return (f'<path d="M{x} 74V24M{x + 18} 74V24M{x - 30} 22H{x + 30}M{x} 40H{x + 18}"/>'
            f'<rect x="{x - 14}" y="22" width="8" height="5"/><path d="M{x - 10} 27V44"/>')


DRAWINGS = {
    "containers.svg": QUAY + crane(112)
    + f'<rect x="28" y="56" width="30" height="18" fill="{WHITE}"/><rect x="58" y="56" width="30" height="18" fill="{ACC}"/>'
    + f'<rect x="43" y="38" width="30" height="18" fill="{WHITE}"/>'
    + '<path d="M36 59v12M44 59v12M51 41v12M59 41v12M66 41v12"/>',

    "dry-bulk.svg": QUAY + f'<path d="M30 74Q62 30 94 74Z" fill="{LAND}"/>'
    + '<path d="M100 36L144 58M108 40v34M134 53v21"/><path d="M98 36l-4 6M96 44l-3 6M94 52l-3 5"/>'
    + f'<path d="M58 6V22"/><path d="M50 22h16l-3 12H53Z" fill="{ACC}"/>',

    "liquid-bulk.svg": QUAY
    + f'<path d="M22 40v34h32V40" fill="{WHITE}"/><ellipse cx="38" cy="40" rx="16" ry="5" fill="{WHITE}"/>'
    + f'<path d="M64 34v40h32V34" fill="{WHITE}"/><ellipse cx="80" cy="34" rx="16" ry="5" fill="{WHITE}"/>'
    + f'<path d="M108 46v28h28V46" fill="{WHITE}"/><ellipse cx="122" cy="46" rx="14" ry="4" fill="{WHITE}"/>'
    + f'<path d="M54 64h10M96 64h12" stroke="{ACC}" stroke-width="3"/>',

    "breakbulk.svg": QUAY + '<path d="M80 4V26"/><path d="M80 26a5 5 0 1 0 5 5" />'
    + '<path d="M80 34L56 52M80 34L104 52"/>'
    + f'<rect x="48" y="52" width="64" height="5" fill="{WHITE}"/><rect x="48" y="57" width="64" height="5" fill="{ACC}"/>'
    + f'<rect x="48" y="62" width="64" height="5" fill="{WHITE}"/>',

    "roro.svg": WAVES + QUAY
    + f'<path d="M92 50H156V72L150 80H98Z" fill="{WHITE}"/><path d="M110 50V36H140V50"/>'
    + '<path d="M96 66L62 74"/>'
    + f'<rect x="64" y="58" width="26" height="10" fill="{ACC}" transform="rotate(-13 77 63)"/>'
    + '<circle cx="70" cy="70" r="2.5"/><circle cx="84" cy="67" r="2.5"/>',

    "shortsea.svg": WAVES
    + f'<path d="M18 60H142L132 76H28Z" fill="{WHITE}"/><path d="M116 60V42H132V60M120 48h8"/>'
    + f'<rect x="32" y="48" width="20" height="12" fill="{ACC}"/><rect x="52" y="48" width="20" height="12" fill="{WHITE}"/>'
    + f'<rect x="72" y="48" width="20" height="12" fill="{WHITE}"/><rect x="42" y="36" width="20" height="12" fill="{WHITE}"/>',

    "ferries.svg": WAVES
    + f'<path d="M16 58H146L136 74H26Z" fill="{WHITE}"/><path d="M34 58V46H124V58M46 46V36H110V46"/>'
    + f'<rect x="84" y="24" width="12" height="12" fill="{ACC}"/>'
    + '<path d="M44 52h8M60 52h8M76 52h8M92 52h8M108 52h8"/>'
    + '<ellipse cx="56" cy="42" rx="6" ry="2.5"/><ellipse cx="100" cy="42" rx="6" ry="2.5"/>',

    "barge.svg": f'<path d="M0 30H160M0 82H160" stroke="{LINE}"/>'
    + f'<path d="M12 56H148L142 68H18Z" fill="{WHITE}"/><path d="M24 56V50H112V56M44 50v6M64 50v6M84 50v6"/>'
    + f'<rect x="120" y="40" width="16" height="16" fill="{ACC}"/><path d="M124 46h8"/>',

    "rail.svg": f'<path d="M0 62H160M0 66H160M0 82H160M0 86H160" stroke="{INK}"/>'
    + f'<rect x="8" y="44" width="42" height="14" fill="{WHITE}"/><rect x="56" y="44" width="42" height="14" fill="{ACC}"/>'
    + f'<rect x="104" y="44" width="42" height="14" fill="{WHITE}"/>'
    + '<circle cx="16" cy="60" r="2"/><circle cx="42" cy="60" r="2"/><circle cx="64" cy="60" r="2"/>'
    + '<circle cx="90" cy="60" r="2"/><circle cx="112" cy="60" r="2"/><circle cx="138" cy="60" r="2"/>',

    "truck-pickups.svg": QUAY
    + f'<rect x="14" y="40" width="58" height="24" fill="{WHITE}"/><path d="M14 64H92"/>'
    + f'<path d="M74 64V46h12l6 8v10" fill="{ACC}"/><circle cx="26" cy="68" r="5" fill="{WHITE}"/>'
    + f'<circle cx="60" cy="68" r="5" fill="{WHITE}"/><circle cx="84" cy="68" r="5" fill="{WHITE}"/>'
    + '<path d="M120 74V40M120 44L154 22M126 74V68h-12v6"/>',

    "rhine.svg": f'<rect width="160" height="100" rx="8" fill="{LAND}" stroke="none"/>'
    + f'<path d="M0 30C50 26 60 70 110 66S150 40 160 42V64C150 64 140 88 104 90S46 52 0 56Z" fill="{WATER}" stroke="none"/>'
    + f'<path d="M0 30C50 26 60 70 110 66S150 40 160 42M0 56C46 52 60 92 104 90S150 64 160 64" stroke="{LINE}"/>'
    + f'<rect x="120" y="10" width="10" height="44" fill="{WHITE}"/><path d="M120 18h4M120 26h4M120 34h4M120 42h4"/>'
    + f'<path d="M121 46h8" stroke="{ACC}" stroke-width="3"/>',

    "hinterland.svg": f'<rect width="160" height="100" rx="8" fill="{LAND}" stroke="none"/>'
    + f'<path d="M8 8H28V92H8Z" fill="{WATER}" stroke="none"/><path d="M28 8V92"/>'
    + '<path d="M30 30H146M138 24l8 6-8 6"/><path d="M58 30h8M86 30h8M114 30h8" stroke-width="1.5"/>'
    + '<path d="M30 52H146M138 46l8 6-8 6M44 48v8M60 48v8M76 48v8M92 48v8M108 48v8"/>'
    + f'<path d="M30 76q14-6 28 0t28 0 28 0 30 0M138 70l8 6-8 6" stroke="{ACC}"/>',

    "sea-access.svg": f'<path d="M10 70q8-4 16 0t16 0M56 82q8-4 16 0t16 0M20 88h20" stroke="{LINE}"/>'
    + f'<path d="M40 66l6-22h8l6 22Z" fill="{WHITE}"/><path d="M50 44V34M44 34h12" stroke="{ACC}" stroke-width="3"/>'
    + f'<path d="M110 74l6-48h12l6 48Z" fill="{WHITE}"/><rect x="114" y="18" width="16" height="8" fill="{ACC}"/>'
    + '<path d="M113 46h18M112 60h20"/><path d="M8 50H28L25 55H11Z"/><path d="M100 74H148"/>',

    "customs.svg": QUAY
    + f'<rect x="16" y="22" width="64" height="52" fill="{WHITE}"/><path d="M48 22v52M30 26v44M66 26v44M24 46h48"/>'
    + f'<circle cx="48" cy="46" r="4" fill="{ACC}"/>'
    + f'<path d="M96 28h36l8 8v38H96Z" fill="{WHITE}"/><path d="M104 40h24M104 48h28M104 56h18"/>'
    + f'<circle cx="124" cy="64" r="7" stroke="{ACC}"/>',

    "labour.svg": QUAY
    + f'<path d="M66 74V56h-6v-8h40v8h-6v18Z" fill="{WHITE}"/>'
    + f'<path d="M62 48a18 14 0 0 1 36 0Z" fill="{ACC}"/><path d="M56 48h48"/>'
    + f'<path d="M104 52l14-6 14 6v22h-28Z" fill="{WHITE}"/><path d="M110 60h16M110 66h16" stroke="{ACC}" stroke-width="3"/>',

    "it-systems.svg": f'<rect x="28" y="12" width="104" height="62" rx="4" fill="{WHITE}"/><path d="M80 74v10M60 86h40"/>'
    + '<path d="M38 22h84v44H38ZM38 36h84M38 50h84M66 22v44M94 22v44" stroke-width="1.5"/>'
    + f'<rect x="68" y="38" width="24" height="10" fill="{ACC}" stroke="none"/>'
    + f'<path d="M140 30l12-8M140 30l12 8M140 30l-8 0" stroke="{ACC}"/><circle cx="152" cy="22" r="2.5" fill="{ACC}"/>'
    + f'<circle cx="152" cy="38" r="2.5" fill="{ACC}"/>',

    "port.svg": WAVES + QUAY + crane(104)
    + f'<path d="M30 74V64h-5v-6h22v6h-5v10Z" fill="{WHITE}"/><path d="M36 58c10-10 22-14 40-16" stroke="{ACC}"/>',
}


def svg(name: str) -> str:
    return HEAD + DRAWINGS[name] + "</svg>\n"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name in DRAWINGS:
        (OUT / name).write_text(svg(name), encoding="utf-8", newline="\n")
        print(f"{name:20} {len(svg(name).encode()):5} bytes")


if __name__ == "__main__":
    main()
