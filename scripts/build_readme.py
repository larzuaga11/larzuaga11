#!/usr/bin/env python3
"""Build README.md and the banner images from profile.yml and projects.yml.

Run locally:   python scripts/build_readme.py
In CI:         .github/workflows/build-readme.yml runs this on every push.
"""

from __future__ import annotations

import datetime as dt
import re
import sys
from html import escape
from pathlib import Path
from urllib.parse import quote, quote_plus

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = "README.md.j2"

# Tech name -> (Simple Icons slug, brand color). Used for badge logos.
# Anything not listed still gets a badge; it just guesses the logo slug.
# Browse slugs at https://simpleicons.org
TECH_LOGOS: dict[str, tuple[str, str]] = {
    "python": ("python", "3776AB"),
    "typescript": ("typescript", "3178C6"),
    "javascript": ("javascript", "F7DF1E"),
    "java": ("openjdk", "ED8B00"),
    "c": ("c", "A8B9CC"),
    "c++": ("cplusplus", "00599C"),
    "c#": ("dotnet", "512BD4"),
    "go": ("go", "00ADD8"),
    "rust": ("rust", "000000"),
    "kotlin": ("kotlin", "7F52FF"),
    "swift": ("swift", "F05138"),
    "ruby": ("ruby", "CC342D"),
    "php": ("php", "777BB4"),
    "sql": ("postgresql", "4169E1"),
    "html": ("html5", "E34F26"),
    "css": ("css", "663399"),
    "html/css": ("html5", "E34F26"),
    "bash": ("gnubash", "4EAA25"),
    "react": ("react", "61DAFB"),
    "next.js": ("nextdotjs", "000000"),
    "vue": ("vuedotjs", "4FC08D"),
    "angular": ("angular", "0F0F11"),
    "svelte": ("svelte", "FF3E00"),
    "node.js": ("nodedotjs", "5FA04E"),
    "express": ("express", "000000"),
    "fastapi": ("fastapi", "009688"),
    "django": ("django", "092E20"),
    "flask": ("flask", "3BABC3"),
    "spring": ("spring", "6DB33F"),
    "tailwind css": ("tailwindcss", "06B6D4"),
    "tensorflow": ("tensorflow", "FF6F00"),
    "pytorch": ("pytorch", "EE4C2C"),
    "pandas": ("pandas", "150458"),
    "aws": ("amazonwebservices", "FF9900"),
    "azure": ("microsoftazure", "0078D4"),
    "gcp": ("googlecloud", "4285F4"),
    "google cloud": ("googlecloud", "4285F4"),
    "docker": ("docker", "2496ED"),
    "kubernetes": ("kubernetes", "326CE5"),
    "terraform": ("terraform", "844FBA"),
    "github actions": ("githubactions", "2088FF"),
    "git": ("git", "F05032"),
    "linux": ("linux", "FCC624"),
    "postgresql": ("postgresql", "4169E1"),
    "mysql": ("mysql", "4479A1"),
    "mongodb": ("mongodb", "47A248"),
    "redis": ("redis", "FF4438"),
    "firebase": ("firebase", "DD2C00"),
    "figma": ("figma", "F24E1E"),
    "powershell": ("powershell", "5391FE"),
    "sqlite": ("sqlite", "003B57"),
    "react native": ("react", "61DAFB"),
    "electron": ("electron", "47848F"),
    # Security
    "kali linux": ("kalilinux", "557C94"),
    "wireshark": ("wireshark", "1679A7"),
    "burp suite": ("burpsuite", "FF6633"),
    "metasploit": ("metasploit", "2596CD"),
    "nmap": ("nmap", "4682B4"),
    "splunk": ("splunk", "000000"),
    "owasp": ("owasp", "000000"),
    "hack the box": ("hackthebox", "9FEF00"),
    "tryhackme": ("tryhackme", "212C42"),
    "snort": ("snort", "F6A7AA"),
    "elastic": ("elastic", "005571"),
    "suricata": ("suricata", "EF7B23"),
}

CONTACTS = {
    # key in profile.yml: (label, logo, color, href builder)
    "linkedin": ("LinkedIn", "linkedin", "0A66C2", lambda v: v),
    "email": ("Email", "gmail", "EA4335", lambda v: f"mailto:{v}"),
    "portfolio": ("Portfolio", "googlechrome", "4285F4", lambda v: v),
    "resume": ("Resume", "readdotcv", "555555", lambda v: v),
    "twitter": ("X", "x", "000000", lambda v: v),
    "website": ("Website", "googlechrome", "4285F4", lambda v: v),
}

HEX = re.compile(r"^[0-9A-Fa-f]{6}$")


class ConfigError(Exception):
    pass


# ── helpers ──────────────────────────────────────────────────


def load_yaml(name: str) -> dict:
    path = ROOT / name
    if not path.exists():
        raise ConfigError(f"{name} is missing.")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        raise ConfigError(f"{name} isn't valid YAML (check indentation):\n{e}") from e
    if not isinstance(data, dict):
        raise ConfigError(f"{name} should contain key: value pairs at the top level.")
    return data


def shield_text(text: str) -> str:
    """Escape text for a shields.io static badge path."""
    return quote(str(text).replace("-", "--").replace("_", "__"), safe="")


def guess_slug(name: str) -> str:
    s = name.lower().replace("+", "plus").replace("#", "sharp").replace(".", "dot")
    return re.sub(r"[^a-z0-9]", "", s)


def tech_badge(name: str, style: str) -> dict:
    slug, color = TECH_LOGOS.get(name.lower(), (guess_slug(name), "30363D"))
    logo_color = "black" if color.upper() in {"F7DF1E", "61DAFB", "FCC624", "9FEF00", "F6A7AA"} else "white"
    img = (
        f"https://img.shields.io/badge/{shield_text(name)}-{color}"
        f"?style={style}&logo={slug}&logoColor={logo_color}"
    )
    return {"label": name, "img": img}


# ── validation ───────────────────────────────────────────────


def validate_profile(p: dict) -> dict:
    for key in ("username", "name", "role"):
        if not str(p.get(key, "")).strip():
            raise ConfigError(f"profile.yml: '{key}' is required.")
    p.setdefault("typing_lines", [])
    # A bullet like  - Fun fact: x  parses as a dict in YAML; turn it back into text.
    p["about"] = [
        ", ".join(f"{k}: {v}" for k, v in a.items()) if isinstance(a, dict) else str(a)
        for a in (p.get("about") or [])
    ]
    p.setdefault("links", {})
    p.setdefault("tech_stack", {})
    theme = p.setdefault("theme", {}) or {}
    p["theme"] = theme
    accent = str(theme.get("accent", "2F81F7")).lstrip("#")
    if not HEX.match(accent):
        raise ConfigError(f"profile.yml: theme.accent '{accent}' should be a 6-digit hex color like 2F81F7.")
    theme["accent"] = accent.upper()
    theme.setdefault("show_stats", True)
    unknown = set(p["links"] or {}) - set(CONTACTS)
    if unknown:
        raise ConfigError(
            f"profile.yml: unknown link type(s) {sorted(unknown)}. Allowed: {sorted(CONTACTS)}."
        )
    return p


def validate_projects(data: dict) -> list[dict]:
    projects = data.get("projects") or []
    if not isinstance(projects, list):
        raise ConfigError("projects.yml: 'projects' must be a list (each item starts with '- name:').")
    out = []
    for i, p in enumerate(projects, start=1):
        where = f"projects.yml project #{i}"
        if not isinstance(p, dict):
            raise ConfigError(f"{where}: each project must be a block of fields.")
        for key in ("name", "description", "tech"):
            if not p.get(key):
                raise ConfigError(f"{where} ({p.get('name', 'unnamed')}): '{key}' is required.")
        if isinstance(p["tech"], str):
            p["tech"] = [t.strip() for t in p["tech"].split(",")]
        if p.get("image") and not str(p["image"]).startswith("http"):
            if not (ROOT / p["image"]).exists():
                raise ConfigError(f"{where} ({p['name']}): image '{p['image']}' not found in the repo.")
        for key in ("repo", "demo", "image"):
            p[key] = p.get(key) or ""
        p.setdefault("featured", False)
        p.setdefault("order", 100)
        p["primary_link"] = p.get("repo") or p.get("demo") or ""
        out.append(p)
    return sorted(out, key=lambda p: (p["order"], p["name"].lower()))


# ── banner ───────────────────────────────────────────────────


def banner_svg(name: str, role: str, accent: str, dark: bool) -> str:
    bg = "#0D1117" if dark else "#F6F8FA"
    fg = "#E6EDF3" if dark else "#1F2328"
    muted = "#8D96A0" if dark else "#59636E"
    grid = "#21262D" if dark else "#E1E4E8"
    a = f"#{accent}"
    name, role = escape(name), escape(role)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="260" viewBox="0 0 1200 260" role="img" aria-label="{name} — {role}">
  <defs>
    <pattern id="grid" width="28" height="28" patternUnits="userSpaceOnUse">
      <path d="M28 0H0V28" fill="none" stroke="{grid}" stroke-width="1"/>
    </pattern>
    <linearGradient id="fade" x1="0" x2="1">
      <stop offset="0.45" stop-color="{bg}" stop-opacity="1"/>
      <stop offset="1" stop-color="{bg}" stop-opacity="0"/>
    </linearGradient>
  </defs>
  <rect width="1200" height="260" rx="16" fill="{bg}"/>
  <rect width="1200" height="260" rx="16" fill="url(#grid)"/>
  <rect width="1200" height="260" rx="16" fill="url(#fade)"/>
  <g fill="none" stroke="{a}" stroke-width="2">
    <circle cx="1010" cy="130" r="88" opacity="0.9"/>
    <circle cx="1010" cy="130" r="58" opacity="0.5"/>
    <rect x="890" y="40" width="64" height="64" rx="10" opacity="0.35" transform="rotate(12 922 72)"/>
    <path d="M1090 205 l26 -26 l26 26" opacity="0.6"/>
  </g>
  <circle cx="1010" cy="130" r="10" fill="{a}"/>
  <rect x="72" y="78" width="56" height="5" rx="2.5" fill="{a}"/>
  <text x="72" y="148" font-family="-apple-system, 'Segoe UI', Helvetica, Arial, sans-serif" font-size="56" font-weight="700" fill="{fg}">{name}</text>
  <text x="72" y="192" font-family="-apple-system, 'Segoe UI', Helvetica, Arial, sans-serif" font-size="24" fill="{muted}">{role}</text>
</svg>
"""


# ── project covers ───────────────────────────────────────────
# Projects without an `image` get a generated cover in the banner's style.

FONT = "-apple-system, 'Segoe UI', Helvetica, Arial, sans-serif"
MONO = "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"

COVER_MOTIFS = {
    # Shield with keyhole
    "shield": """
    <path d="M640 92 L728 124 V196 C728 258 692 300 640 320 C588 300 552 258 552 196 V124 Z" stroke-width="3"/>
    <path d="M640 124 L700 146 V198 C700 240 676 268 640 284 C604 268 580 240 580 198 V146 Z" opacity="0.4"/>
    <circle cx="640" cy="192" r="16"/><path d="M640 208 V236"/>
    <path d="M728 196 H800 M552 196 H500 M500 196 V120 M500 196 V280" opacity="0.5"/>""",
    # Connected network nodes
    "network": """
    <circle cx="640" cy="200" r="34" stroke-width="3"/>
    <circle cx="540" cy="110" r="14"/><circle cx="740" cy="104" r="14"/>
    <circle cx="530" cy="300" r="14"/><circle cx="752" cy="292" r="14"/><circle cx="640" cy="350" r="10"/>
    <path d="M614 178 L552 120 M666 178 L728 114 M612 222 L542 290 M668 222 L740 282 M640 234 V340" opacity="0.6"/>
    <circle cx="640" cy="200" r="70" opacity="0.25"/>""",
    # Terminal window with prompt
    "terminal": """
    <rect x="520" y="110" width="250" height="190" rx="14" stroke-width="3"/>
    <path d="M520 146 H770" opacity="0.5"/>
    <circle cx="544" cy="128" r="5"/><circle cx="562" cy="128" r="5"/><circle cx="580" cy="128" r="5"/>
    <path d="M548 186 L576 206 L548 226" stroke-width="3"/><path d="M590 230 H640" stroke-width="3"/>
    <path d="M548 262 H700 M548 280 H660" opacity="0.35"/>""",
}


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "project"


def wrap(text: str, width: int, max_lines: int = 2) -> list[str]:
    words, lines, line = text.split(), [], ""
    for w in words:
        if len(line) + len(w) + 1 > width and line:
            lines.append(line)
            line = w
        else:
            line = f"{line} {w}".strip()
    lines.append(line)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1][: width - 1].rstrip() + "…"
    return lines


def cover_svg(p: dict, accent: str, dark: bool) -> str:
    bg = "#0D1117" if dark else "#F6F8FA"
    fg = "#E6EDF3" if dark else "#1F2328"
    muted = "#8D96A0" if dark else "#59636E"
    grid = "#21262D" if dark else "#E1E4E8"
    chip_bg = "#161B22" if dark else "#FFFFFF"
    chip_border = "#30363D" if dark else "#D1D9E0"
    a = f"#{accent}"

    style = p.get("cover_style") or list(COVER_MOTIFS)[sum(map(ord, p["name"])) % len(COVER_MOTIFS)]
    motif = COVER_MOTIFS.get(style, COVER_MOTIFS["shield"])

    name = p["name"]
    size = 52 if len(name) <= 14 else 44 if len(name) <= 18 else 36
    name_lines = wrap(name, 20, 2)
    tagline = wrap(p.get("tagline") or p["description"], 30, 2)

    y = 150
    text = []
    for line in name_lines:
        text.append(f'<text x="48" y="{y}" font-family="{FONT}" font-size="{size}" font-weight="700" fill="{fg}">{escape(line)}</text>')
        y += size + 8
    y += 4
    for line in tagline:
        text.append(f'<text x="48" y="{y}" font-family="{FONT}" font-size="26" fill="{muted}">{escape(line)}</text>')
        y += 36

    chips, x = [], 48
    for t in p["tech"][:4]:
        w = len(t) * 11 + 32
        if x + w > 500:
            break
        chips.append(
            f'<rect x="{x}" y="336" width="{w}" height="40" rx="20" fill="{chip_bg}" stroke="{chip_border}"/>'
            f'<text x="{x + w / 2}" y="362" text-anchor="middle" font-family="{MONO}" font-size="17" fill="{fg}">{escape(t)}</text>'
        )
        x += w + 10

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="800" height="420" viewBox="0 0 800 420" role="img" aria-label="{escape(name)}">
  <defs>
    <pattern id="g" width="24" height="24" patternUnits="userSpaceOnUse"><path d="M24 0H0V24" fill="none" stroke="{grid}" stroke-width="1"/></pattern>
    <linearGradient id="f" x1="0" x2="1"><stop offset="0.4" stop-color="{bg}"/><stop offset="1" stop-color="{bg}" stop-opacity="0"/></linearGradient>
    <clipPath id="c"><rect width="800" height="420" rx="14"/></clipPath>
  </defs>
  <g clip-path="url(#c)">
    <rect width="800" height="420" fill="{bg}"/>
    <rect width="800" height="420" fill="url(#g)"/>
    <rect width="800" height="420" fill="url(#f)"/>
    <g fill="none" stroke="{a}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">{motif}
    </g>
    <rect x="48" y="58" width="44" height="5" rx="2.5" fill="{a}"/>
    <text x="104" y="65" font-family="{MONO}" font-size="16" letter-spacing="2" fill="{a}">PROJECT</text>
    {chr(10).join("    " + t for t in text).strip()}
    {"".join(chips)}
  </g>
  <rect x="0.5" y="0.5" width="799" height="419" rx="14" fill="none" stroke="{chip_border}"/>
</svg>
"""


# ── build ────────────────────────────────────────────────────


def build() -> None:
    profile = validate_profile(load_yaml("profile.yml"))
    projects = validate_projects(load_yaml("projects.yml"))
    user = profile["username"]
    accent = profile["theme"]["accent"]

    covers = ROOT / "assets" / "projects" / "covers"
    covers.mkdir(parents=True, exist_ok=True)
    for old in covers.glob("*.svg"):  # drop covers of renamed/removed projects
        old.unlink()

    for p in projects:
        p["tech_badges"] = [tech_badge(t, "flat-square") for t in p["tech"]]
        p["cover_light"] = p["cover_dark"] = ""
        if not p["image"]:
            slug = slugify(p["name"])
            for dark in (False, True):
                mode = "dark" if dark else "light"
                (covers / f"{slug}-{mode}.svg").write_text(cover_svg(p, accent, dark), encoding="utf-8")
                p[f"cover_{mode}"] = f"assets/projects/covers/{slug}-{mode}.svg"

    contact_badges = []
    for key, value in (profile["links"] or {}).items():
        if not value:
            continue
        label, logo, color, href = CONTACTS[key]
        contact_badges.append({
            "label": label,
            "href": href(value),
            "img": f"https://img.shields.io/badge/{shield_text(label)}-{color}?style=for-the-badge&logo={logo}&logoColor=white",
        })

    tech_groups = [
        {"name": group, "badges": [tech_badge(t, "for-the-badge") for t in (items or [])]}
        for group, items in (profile["tech_stack"] or {}).items()
    ]

    typing_url = ""
    if profile["typing_lines"]:
        lines = ";".join(quote_plus(str(l)).replace("%3B", ",") for l in profile["typing_lines"])
        typing_url = (
            "https://readme-typing-svg.demolab.com?font=Fira+Code&weight=500&size=20"
            f"&pause=1200&color={accent}&center=true&vCenter=true&width=640&lines={lines}"
        )

    rs = "https://github-readme-stats.vercel.app/api"
    common = "hide_border=true&bg_color=00000000"
    stats = {
        "stats_light": f"{rs}?username={user}&show_icons=true&{common}&title_color={accent}&icon_color={accent}&text_color=1F2328",
        "stats_dark": f"{rs}?username={user}&show_icons=true&{common}&title_color={accent}&icon_color={accent}&text_color=E6EDF3",
        "langs_light": f"{rs}/top-langs/?username={user}&layout=compact&langs_count=8&{common}&title_color={accent}&text_color=1F2328",
        "langs_dark": f"{rs}/top-langs/?username={user}&layout=compact&langs_count=8&{common}&title_color={accent}&text_color=E6EDF3",
        "streak_light": f"https://streak-stats.demolab.com?user={user}&hide_border=true&background=00000000&ring={accent}&fire={accent}&currStreakLabel={accent}",
        "streak_dark": f"https://streak-stats.demolab.com?user={user}&theme=dark&hide_border=true&background=00000000&ring={accent}&fire={accent}&currStreakLabel={accent}",
    }

    env = Environment(
        loader=FileSystemLoader(ROOT / "templates"),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )
    readme = env.get_template(TEMPLATE).render(
        profile=profile,
        featured=[p for p in projects if p["featured"]],
        more=[p for p in projects if not p["featured"]],
        contact_badges=contact_badges,
        tech_groups=tech_groups,
        typing_url=typing_url,
        stats=stats,
        built_on=dt.date.today().isoformat(),
    )
    readme = re.sub(r"\n{3,}", "\n\n", readme)  # tidy blank lines

    (ROOT / "README.md").write_text(readme, encoding="utf-8")
    assets = ROOT / "assets"
    assets.mkdir(exist_ok=True)
    for dark in (False, True):
        out = assets / f"banner-{'dark' if dark else 'light'}.svg"
        out.write_text(banner_svg(profile["name"], profile["role"], accent, dark), encoding="utf-8")

    n_feat = sum(1 for p in projects if p["featured"])
    print(f"README.md built: {n_feat} featured, {len(projects) - n_feat} more projects.")


if __name__ == "__main__":
    try:
        build()
    except ConfigError as e:
        print(f"❌ {e}", file=sys.stderr)
        sys.exit(1)
