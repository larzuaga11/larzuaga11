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
    logo_color = "black" if color.upper() in {"F7DF1E", "61DAFB", "FCC624"} else "white"
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


# ── build ────────────────────────────────────────────────────


def build() -> None:
    profile = validate_profile(load_yaml("profile.yml"))
    projects = validate_projects(load_yaml("projects.yml"))
    user = profile["username"]
    accent = profile["theme"]["accent"]

    for p in projects:
        p["tech_badges"] = [tech_badge(t, "flat-square") for t in p["tech"]]

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
