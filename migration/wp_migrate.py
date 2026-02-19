#!/usr/bin/env python3
"""
WordPress → Ecossistema Digital Migration Script
=================================================
Migrates content from botschaftangola.de (WordPress) to:
  - SI Backend (Sistema Institucional): pages, menus, contacts, media
  - WN Backend (Welwitschia Noticias): articles, categories, media

Requirements:
  pip install requests beautifulsoup4 Pillow

Usage:
  python wp_migrate.py                      # Full migration
  python wp_migrate.py --step categories    # Single step
  python wp_migrate.py --dry-run            # Preview without writing
"""

import argparse
import json
import os
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

# ── Configuration ────────────────────────────────────────────────────────────

WP_BASE = "https://botschaftangola.de/wp-json/wp/v2"

KEYCLOAK_URL = os.getenv("KEYCLOAK_URL", "http://localhost:8080")
KEYCLOAK_REALM = os.getenv("KEYCLOAK_REALM", "ecossistema")
KEYCLOAK_CLIENT = os.getenv("KEYCLOAK_CLIENT", "si-frontend")
KEYCLOAK_USER = os.getenv("KEYCLOAK_USER", "admin")
KEYCLOAK_PASSWORD = os.getenv("KEYCLOAK_PASSWORD", "admin123")

SI_BACKEND = os.getenv("SI_BACKEND", "http://localhost:8082")
WN_BACKEND = os.getenv("WN_BACKEND", "http://localhost:8083")

MEDIA_DIR = Path(__file__).parent / "media_cache"
STATE_FILE = Path(__file__).parent / "migration_state.json"

# ── WP Category → WN Category mapping ───────────────────────────────────────

WP_CATEGORY_MAP = {
    "diplomacia": {"nomePt": "Diplomacia", "nomeEn": "Diplomacy", "nomeDe": "Diplomatie", "cor": "#1a237e"},
    "politica": {"nomePt": "Política", "nomeEn": "Politics", "nomeDe": "Politik", "cor": "#b71c1c"},
    "economia": {"nomePt": "Economia", "nomeEn": "Economy", "nomeDe": "Wirtschaft", "cor": "#1b5e20"},
    "cultura": {"nomePt": "Cultura", "nomeEn": "Culture", "nomeDe": "Kultur", "cor": "#e65100"},
    "desporto": {"nomePt": "Desporto", "nomeEn": "Sports", "nomeDe": "Sport", "cor": "#0d47a1"},
    "turismo": {"nomePt": "Turismo", "nomeEn": "Tourism", "nomeDe": "Tourismus", "cor": "#00695c"},
    "diaspora": {"nomePt": "Angolanos na Diáspora", "nomeEn": "Angolans Abroad", "nomeDe": "Angolaner im Ausland", "cor": "#4a148c"},
    "reportagem": {"nomePt": "Reportagem", "nomeEn": "Report", "nomeDe": "Reportage", "cor": "#263238"},
    "responsabilidade-social": {"nomePt": "Responsabilidade Social", "nomeEn": "Social Responsibility", "nomeDe": "Soziale Verantwortung", "cor": "#880e4f"},
    "webinares": {"nomePt": "Webinares", "nomeEn": "Webinars", "nomeDe": "Webinare", "cor": "#311b92"},
    "destaques": {"nomePt": "Destaques", "nomeEn": "Highlights", "nomeDe": "Highlights", "cor": "#cc092f"},
}

# WP Pages → SI Page type+slug mapping
WP_PAGE_MAP = {
    # About Angola subsections (match InstitutionalController slugs)
    3162: {"slug": "presidente", "tipo": "INSTITUTIONAL", "sortOrder": 1},         # O Presidente
    3191: {"slug": "poderes-executivo", "tipo": "INSTITUTIONAL", "sortOrder": 2},  # O Poder Executivo
    3183: {"slug": "poderes-legislativo", "tipo": "INSTITUTIONAL", "sortOrder": 3},# O Poder Legislativo
    3178: {"slug": "poderes-judicial", "tipo": "INSTITUTIONAL", "sortOrder": 4},   # O Poder Judicial
    3200: {"slug": "mirex", "tipo": "INSTITUTIONAL", "sortOrder": 5},              # O MIREX
    1274: {"slug": "sobre-angola", "tipo": "INSTITUTIONAL", "sortOrder": 0},       # Sobre Angola (parent)
    1282: {"slug": "demografia", "tipo": "INSTITUTIONAL", "sortOrder": 6},         # Demografia
    1277: {"slug": "geografia", "tipo": "INSTITUTIONAL", "sortOrder": 7},          # Geografia
    1271: {"slug": "historia", "tipo": "INSTITUTIONAL", "sortOrder": 8},           # História
    1236: {"slug": "simbolos", "tipo": "INSTITUTIONAL", "sortOrder": 9},           # Símbolos Nacionais
    1286: {"slug": "economia", "tipo": "INSTITUTIONAL", "sortOrder": 10},          # Investimentos/Economia
    # Embassy
    71:   {"slug": "embaixada", "tipo": "INSTITUTIONAL", "sortOrder": 0},          # A Embaixada
    # Consular services
    1793: {"slug": "visto-consular", "tipo": "SERVICE", "sortOrder": 1},           # Visto Consular
    1796: {"slug": "visto-territorial", "tipo": "SERVICE", "sortOrder": 2},        # Visto Territorial
    5501: {"slug": "bilhete-identidade", "tipo": "SERVICE", "sortOrder": 3},       # BI e Cert Criminal
    # Legal pages
    1582: {"slug": "impressum", "tipo": "INSTITUTIONAL", "sortOrder": 20},         # Impressum
    1580: {"slug": "politica-privacidade", "tipo": "INSTITUTIONAL", "sortOrder": 21}, # Privacy Statement
    1578: {"slug": "politica-cookies", "tipo": "INSTITUTIONAL", "sortOrder": 22},  # Cookie Policy
}


# ── State management ─────────────────────────────────────────────────────────

class MigrationState:
    """Tracks progress to allow resumable migrations."""

    def __init__(self):
        self.data = {
            "wp_categories": {},   # wp_id -> wn_category_id
            "wn_author_id": None,
            "wp_posts": {},        # wp_id -> wn_article_id
            "wp_pages": {},        # wp_id -> si_page_id
            "wp_media_si": {},     # wp_id -> si_media_id
            "wp_media_wn": {},     # wp_id -> wn_media_id
            "si_menus": {},        # location -> menu_id
            "si_contacts": [],
            "completed_steps": [],
        }
        self._load()

    def _load(self):
        if STATE_FILE.exists():
            with open(STATE_FILE) as f:
                saved = json.load(f)
                self.data.update(saved)

    def save(self):
        with open(STATE_FILE, "w") as f:
            json.dump(self.data, f, indent=2)

    def mark_step(self, step: str):
        if step not in self.data["completed_steps"]:
            self.data["completed_steps"].append(step)
            self.save()

    def is_done(self, step: str) -> bool:
        return step in self.data["completed_steps"]


# ── Auth helper ──────────────────────────────────────────────────────────────

def get_keycloak_token() -> str:
    """Get admin JWT token from Keycloak."""
    url = f"{KEYCLOAK_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/token"
    resp = requests.post(url, data={
        "grant_type": "password",
        "client_id": KEYCLOAK_CLIENT,
        "username": KEYCLOAK_USER,
        "password": KEYCLOAK_PASSWORD,
    }, timeout=10)
    if resp.status_code != 200:
        print(f"[ERROR] Keycloak auth failed ({resp.status_code}): {resp.text}")
        sys.exit(1)
    token = resp.json()["access_token"]
    print(f"[OK] Authenticated as {KEYCLOAK_USER}")
    return token


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ── WordPress fetcher ────────────────────────────────────────────────────────

def wp_fetch_all(endpoint: str, params: dict = None) -> list:
    """Fetch all items from a WP REST API endpoint, handling pagination."""
    items = []
    page = 1
    per_page = 100
    while True:
        p = {"per_page": per_page, "page": page}
        if params:
            p.update(params)
        resp = requests.get(f"{WP_BASE}/{endpoint}", params=p, timeout=30)
        if resp.status_code == 400:
            break  # Past last page
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        items.extend(batch)
        total_pages = int(resp.headers.get("X-WP-TotalPages", 1))
        if page >= total_pages:
            break
        page += 1
        time.sleep(0.3)  # Be polite
    return items


def wp_clean_html(html: str) -> str:
    """Clean WordPress HTML content, removing Divi builder artifacts."""
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")

    # Remove Divi builder wrapper divs
    for div in soup.find_all("div", class_=re.compile(r"et_pb_")):
        div.unwrap()

    # Remove empty divs
    for div in soup.find_all("div"):
        if not div.get_text(strip=True) and not div.find("img"):
            div.decompose()

    # Clean up excessive whitespace
    text = str(soup)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def wp_extract_excerpt(content: str, max_len: int = 300) -> str:
    """Extract a plain-text excerpt from HTML content."""
    if not content:
        return ""
    soup = BeautifulSoup(content, "html.parser")
    text = soup.get_text(separator=" ", strip=True)
    if len(text) > max_len:
        text = text[:max_len].rsplit(" ", 1)[0] + "..."
    return text


# ── Media download/upload ────────────────────────────────────────────────────

def download_media(url: str) -> Path | None:
    """Download a media file from WordPress to local cache."""
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    parsed = urlparse(url)
    filename = Path(parsed.path).name
    local_path = MEDIA_DIR / filename

    if local_path.exists():
        return local_path

    try:
        resp = requests.get(url, timeout=60, stream=True)
        resp.raise_for_status()
        with open(local_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        print(f"  [DL] {filename} ({local_path.stat().st_size // 1024}KB)")
        return local_path
    except Exception as e:
        print(f"  [WARN] Failed to download {url}: {e}")
        return None


def upload_media_si(token: str, file_path: Path, alt_pt: str = "") -> dict | None:
    """Upload a media file to SI backend."""
    headers = {"Authorization": f"Bearer {token}"}
    with open(file_path, "rb") as f:
        files = {"file": (file_path.name, f)}
        data = {}
        if alt_pt:
            data["altPt"] = alt_pt
        resp = requests.post(
            f"{SI_BACKEND}/api/v1/media",
            headers=headers, files=files, data=data, timeout=60,
        )
    if resp.status_code in (200, 201):
        result = resp.json()
        return result.get("data", result)
    print(f"  [WARN] SI media upload failed for {file_path.name}: {resp.status_code} {resp.text[:200]}")
    return None


def upload_media_wn(token: str, file_path: Path, alt_pt: str = "") -> dict | None:
    """Upload a media file to WN backend."""
    headers = {"Authorization": f"Bearer {token}"}
    with open(file_path, "rb") as f:
        files = {"file": (file_path.name, f)}
        data = {}
        if alt_pt:
            data["altPt"] = alt_pt
        resp = requests.post(
            f"{WN_BACKEND}/api/v1/media",
            headers=headers, files=files, data=data, timeout=60,
        )
    if resp.status_code in (200, 201):
        result = resp.json()
        return result.get("data", result)
    print(f"  [WARN] WN media upload failed for {file_path.name}: {resp.status_code} {resp.text[:200]}")
    return None


# ── Step 1: Migrate WP Categories → WN Categories ───────────────────────────

def migrate_categories(token: str, state: MigrationState, dry_run: bool = False):
    step = "categories"
    if state.is_done(step):
        print(f"[SKIP] {step} already done")
        return

    print("\n=== Step 1: WP Categories → WN Categories ===")
    wp_cats = wp_fetch_all("categories")
    print(f"  Found {len(wp_cats)} WP categories")

    headers = auth_headers(token)

    for cat in wp_cats:
        wp_id = cat["id"]
        slug = cat["slug"]

        if slug == "uncategorized":
            continue

        if str(wp_id) in state.data["wp_categories"]:
            print(f"  [SKIP] {slug} (already migrated)")
            continue

        mapping = WP_CATEGORY_MAP.get(slug, {})
        payload = {
            "slug": slug,
            "nomePt": mapping.get("nomePt", cat["name"]),
            "nomeEn": mapping.get("nomeEn", ""),
            "nomeDe": mapping.get("nomeDe", ""),
            "nomeCs": "",
            "descricaoPt": cat.get("description", ""),
            "cor": mapping.get("cor", "#607d8b"),
            "sortOrder": cat.get("count", 0),
        }

        if dry_run:
            print(f"  [DRY] Would create category: {slug}")
            continue

        resp = requests.post(f"{WN_BACKEND}/api/v1/categories", headers=headers, json=payload, timeout=10)
        if resp.status_code in (200, 201):
            result = resp.json()
            data = result.get("data", result)
            wn_id = data.get("id")
            state.data["wp_categories"][str(wp_id)] = wn_id
            state.save()
            print(f"  [OK] {slug} → {wn_id}")
        else:
            print(f"  [ERR] {slug}: {resp.status_code} {resp.text[:200]}")

    if not dry_run:
        state.mark_step(step)
    print(f"  Migrated {len(state.data['wp_categories'])} categories")


# ── Step 2: Create WN Author ────────────────────────────────────────────────

def create_wn_author(token: str, state: MigrationState, dry_run: bool = False):
    step = "author"
    if state.is_done(step):
        print(f"[SKIP] {step} already done")
        return

    print("\n=== Step 2: Create WN Author ===")

    if state.data["wn_author_id"]:
        print(f"  [SKIP] Author already exists: {state.data['wn_author_id']}")
        state.mark_step(step)
        return

    payload = {
        "nome": "Embaixada de Angola na Alemanha",
        "slug": "embaixada-angola-alemanha",
        "bioPt": "Embaixada da República de Angola na República Federal da Alemanha e República Checa",
        "bioEn": "Embassy of the Republic of Angola in the Federal Republic of Germany and Czech Republic",
        "bioDe": "Botschaft der Republik Angola in der Bundesrepublik Deutschland und der Tschechischen Republik",
        "email": "info@embaixada-angola.site",
        "role": "INSTITUTION",
    }

    if dry_run:
        print(f"  [DRY] Would create author: {payload['nome']}")
        return

    headers = auth_headers(token)
    resp = requests.post(f"{WN_BACKEND}/api/v1/authors", headers=headers, json=payload, timeout=10)
    if resp.status_code in (200, 201):
        result = resp.json()
        data = result.get("data", result)
        state.data["wn_author_id"] = data.get("id")
        state.save()
        state.mark_step(step)
        print(f"  [OK] Author created: {state.data['wn_author_id']}")
    else:
        print(f"  [ERR] Author creation failed: {resp.status_code} {resp.text[:200]}")


# ── Step 3: Migrate WP Posts → WN Articles ──────────────────────────────────

def migrate_posts(token: str, state: MigrationState, dry_run: bool = False):
    step = "posts"
    if state.is_done(step):
        print(f"[SKIP] {step} already done")
        return

    print("\n=== Step 3: WP Posts → WN Articles ===")
    wp_posts = wp_fetch_all("posts")
    print(f"  Found {len(wp_posts)} WP posts")

    headers = auth_headers(token)
    author_id = state.data.get("wn_author_id")
    migrated = 0

    for post in wp_posts:
        wp_id = post["id"]
        if str(wp_id) in state.data["wp_posts"]:
            continue

        slug = post["slug"]
        title = BeautifulSoup(post["title"]["rendered"], "html.parser").get_text()
        content = wp_clean_html(post["content"]["rendered"])
        excerpt_html = post.get("excerpt", {}).get("rendered", "")
        excerpt = wp_extract_excerpt(excerpt_html or content, 400)

        # Map first WP category to WN category
        wp_cat_ids = post.get("categories", [])
        wn_category_id = None
        for wc in wp_cat_ids:
            if str(wc) in state.data["wp_categories"]:
                wn_category_id = state.data["wp_categories"][str(wc)]
                break

        # Handle featured media
        featured_image_id = None
        featured_media_wp = post.get("featured_media")
        if featured_media_wp and str(featured_media_wp) in state.data.get("wp_media_wn", {}):
            featured_image_id = state.data["wp_media_wn"][str(featured_media_wp)]

        # Truncate slug to fit 300 char limit
        if len(slug) > 290:
            slug = slug[:290]

        payload = {
            "slug": slug,
            "tituloPt": title[:300],
            "conteudoPt": content,
            "excertoPt": excerpt[:500],
            "metaTituloPt": title[:160],
            "metaDescricaoPt": excerpt[:320],
            "featured": False,
        }

        if wn_category_id:
            payload["categoryId"] = wn_category_id
        if author_id:
            payload["authorId"] = author_id
        if featured_image_id:
            payload["featuredImageId"] = featured_image_id

        if dry_run:
            print(f"  [DRY] Would create article: {slug}")
            continue

        resp = requests.post(f"{WN_BACKEND}/api/v1/articles", headers=headers, json=payload, timeout=15)
        if resp.status_code in (200, 201):
            result = resp.json()
            data = result.get("data", result)
            article_id = data.get("id")
            state.data["wp_posts"][str(wp_id)] = article_id
            state.save()

            # Publish the article via editorial workflow
            requests.patch(
                f"{WN_BACKEND}/api/v1/editorial/articles/{article_id}/submit",
                headers=headers, timeout=10,
            )
            requests.patch(
                f"{WN_BACKEND}/api/v1/editorial/articles/{article_id}/review",
                headers=headers, timeout=10,
            )
            requests.patch(
                f"{WN_BACKEND}/api/v1/editorial/articles/{article_id}/publish",
                headers=headers, timeout=10,
            )

            migrated += 1
            print(f"  [OK] {slug} → {article_id}")
        else:
            print(f"  [ERR] {slug}: {resp.status_code} {resp.text[:200]}")

        time.sleep(0.2)

    if not dry_run:
        state.mark_step(step)
    print(f"  Migrated {migrated} articles")


# ── Step 4: Migrate WP Pages → SI Pages ─────────────────────────────────────

def migrate_pages(token: str, state: MigrationState, dry_run: bool = False):
    step = "pages"
    if state.is_done(step):
        print(f"[SKIP] {step} already done")
        return

    print("\n=== Step 4: WP Pages → SI Pages ===")
    wp_pages = wp_fetch_all("pages")
    print(f"  Found {len(wp_pages)} WP pages")

    headers = auth_headers(token)
    migrated = 0

    for page in wp_pages:
        wp_id = page["id"]
        if str(wp_id) in state.data["wp_pages"]:
            continue

        # Only migrate pages we have explicit mappings for
        mapping = WP_PAGE_MAP.get(wp_id)
        if not mapping:
            title = BeautifulSoup(page["title"]["rendered"], "html.parser").get_text()
            print(f"  [SKIP] No mapping for WP page {wp_id}: {title}")
            continue

        title = BeautifulSoup(page["title"]["rendered"], "html.parser").get_text()
        content = wp_clean_html(page["content"]["rendered"])
        excerpt = wp_extract_excerpt(content, 400)

        # Handle featured media
        featured_image_id = None
        featured_media_wp = page.get("featured_media")
        if featured_media_wp and str(featured_media_wp) in state.data.get("wp_media_si", {}):
            featured_image_id = state.data["wp_media_si"][str(featured_media_wp)]

        payload = {
            "slug": mapping["slug"],
            "tipo": mapping["tipo"],
            "sortOrder": mapping.get("sortOrder", 0),
            "translations": [
                {
                    "idioma": "PT",
                    "titulo": title[:300],
                    "conteudo": content,
                    "excerto": excerpt[:500],
                    "metaTitulo": title[:160],
                    "metaDescricao": excerpt[:320],
                }
            ],
        }

        if featured_image_id:
            payload["featuredImageId"] = featured_image_id

        if dry_run:
            print(f"  [DRY] Would create page: {mapping['slug']} ({title})")
            continue

        resp = requests.post(f"{SI_BACKEND}/api/v1/pages", headers=headers, json=payload, timeout=15)
        if resp.status_code in (200, 201):
            result = resp.json()
            data = result.get("data", result)
            page_id = data.get("id")
            state.data["wp_pages"][str(wp_id)] = page_id
            state.save()

            # Publish the page (estado update)
            requests.patch(
                f"{SI_BACKEND}/api/v1/pages/{page_id}/estado",
                headers=headers, json={"estado": "PUBLISHED"}, timeout=10,
            )

            migrated += 1
            print(f"  [OK] {mapping['slug']} → {page_id}")
        else:
            print(f"  [ERR] {mapping['slug']}: {resp.status_code} {resp.text[:200]}")

        time.sleep(0.2)

    if not dry_run:
        state.mark_step(step)
    print(f"  Migrated {migrated} pages")


# ── Step 5: Migrate Media ───────────────────────────────────────────────────

def migrate_media(token: str, state: MigrationState, dry_run: bool = False):
    step = "media"
    if state.is_done(step):
        print(f"[SKIP] {step} already done")
        return

    print("\n=== Step 5: WP Media → SI + WN Media ===")
    wp_media = wp_fetch_all("media")
    print(f"  Found {len(wp_media)} WP media items")

    # Download media referenced by posts (for WN) and pages (for SI)
    post_media_ids = set()
    page_media_ids = set()

    wp_posts = wp_fetch_all("posts")
    for post in wp_posts:
        fm = post.get("featured_media")
        if fm:
            post_media_ids.add(fm)

    wp_pages = wp_fetch_all("pages")
    for page in wp_pages:
        if page["id"] in WP_PAGE_MAP:
            fm = page.get("featured_media")
            if fm:
                page_media_ids.add(fm)

    uploaded_wn = 0
    uploaded_si = 0

    for media in wp_media:
        wp_mid = media["id"]
        source_url = media.get("source_url", "")
        alt = media.get("alt_text", "")
        title = BeautifulSoup(media.get("title", {}).get("rendered", ""), "html.parser").get_text()

        if not source_url:
            continue

        # Only download images (skip PDFs, videos for now)
        mime = media.get("mime_type", "")
        if not mime.startswith("image/"):
            continue

        # Upload to WN if used by posts
        if wp_mid in post_media_ids and str(wp_mid) not in state.data["wp_media_wn"]:
            local_file = download_media(source_url)
            if local_file and not dry_run:
                result = upload_media_wn(token, local_file, alt or title)
                if result:
                    state.data["wp_media_wn"][str(wp_mid)] = result.get("id")
                    state.save()
                    uploaded_wn += 1
                    print(f"  [OK→WN] {local_file.name} → {result.get('id')}")
            elif dry_run:
                print(f"  [DRY→WN] Would upload {source_url}")

        # Upload to SI if used by pages
        if wp_mid in page_media_ids and str(wp_mid) not in state.data["wp_media_si"]:
            local_file = download_media(source_url)
            if local_file and not dry_run:
                result = upload_media_si(token, local_file, alt or title)
                if result:
                    state.data["wp_media_si"][str(wp_mid)] = result.get("id")
                    state.save()
                    uploaded_si += 1
                    print(f"  [OK→SI] {local_file.name} → {result.get('id')}")
            elif dry_run:
                print(f"  [DRY→SI] Would upload {source_url}")

    if not dry_run:
        state.mark_step(step)
    print(f"  Uploaded {uploaded_wn} to WN, {uploaded_si} to SI")


# ── Step 6: Create SI Menus ─────────────────────────────────────────────────

def create_si_menus(token: str, state: MigrationState, dry_run: bool = False):
    step = "menus"
    if state.is_done(step):
        print(f"[SKIP] {step} already done")
        return

    print("\n=== Step 6: Create SI Menus ===")
    headers = auth_headers(token)

    # ── HEADER menu ──────────────────────────────────────────────────────
    if "HEADER" not in state.data["si_menus"]:
        payload = {"nome": "Menu Principal", "localizacao": "HEADER"}
        if dry_run:
            print("  [DRY] Would create HEADER menu")
        else:
            resp = requests.post(f"{SI_BACKEND}/api/v1/menus", headers=headers, json=payload, timeout=10)
            if resp.status_code in (200, 201):
                result = resp.json()
                data = result.get("data", result)
                menu_id = data.get("id")
                state.data["si_menus"]["HEADER"] = menu_id
                state.save()
                print(f"  [OK] HEADER menu → {menu_id}")
            else:
                print(f"  [ERR] HEADER menu: {resp.status_code} {resp.text[:200]}")

    # Add HEADER menu items
    header_id = state.data["si_menus"].get("HEADER")
    if header_id and not dry_run:
        header_items = [
            {
                "labelPt": "Início",
                "labelEn": "Home",
                "labelDe": "Startseite",
                "url": "/",
                "sortOrder": 0,
                "icon": "home",
            },
            {
                "labelPt": "Sobre Angola",
                "labelEn": "About Angola",
                "labelDe": "Über Angola",
                "url": "/sobre-angola",
                "sortOrder": 1,
                "icon": "public",
            },
            {
                "labelPt": "Embaixador",
                "labelEn": "Ambassador",
                "labelDe": "Botschafter",
                "url": "/embaixador",
                "sortOrder": 2,
                "icon": "person",
            },
            {
                "labelPt": "Serviços Consulares",
                "labelEn": "Consular Services",
                "labelDe": "Konsularische Dienste",
                "url": "/servicos-consulares",
                "sortOrder": 3,
                "icon": "assignment",
            },
            {
                "labelPt": "Relações Bilaterais",
                "labelEn": "Bilateral Relations",
                "labelDe": "Bilaterale Beziehungen",
                "url": "/relacoes-bilaterais",
                "sortOrder": 4,
                "icon": "handshake",
            },
            {
                "labelPt": "Eventos",
                "labelEn": "Events",
                "labelDe": "Veranstaltungen",
                "url": "/eventos",
                "sortOrder": 5,
                "icon": "event",
            },
            {
                "labelPt": "Contactos",
                "labelEn": "Contacts",
                "labelDe": "Kontakte",
                "url": "/contactos",
                "sortOrder": 6,
                "icon": "contact_mail",
            },
        ]

        for item in header_items:
            resp = requests.post(
                f"{SI_BACKEND}/api/v1/menus/{header_id}/items",
                headers=headers, json=item, timeout=10,
            )
            if resp.status_code in (200, 201):
                print(f"    [OK] Header item: {item['labelPt']}")
            else:
                print(f"    [ERR] Header item {item['labelPt']}: {resp.status_code} {resp.text[:100]}")

    # ── FOOTER menu ──────────────────────────────────────────────────────
    if "FOOTER" not in state.data["si_menus"]:
        payload = {"nome": "Menu Rodapé", "localizacao": "FOOTER"}
        if dry_run:
            print("  [DRY] Would create FOOTER menu")
        else:
            resp = requests.post(f"{SI_BACKEND}/api/v1/menus", headers=headers, json=payload, timeout=10)
            if resp.status_code in (200, 201):
                result = resp.json()
                data = result.get("data", result)
                menu_id = data.get("id")
                state.data["si_menus"]["FOOTER"] = menu_id
                state.save()
                print(f"  [OK] FOOTER menu → {menu_id}")
            else:
                print(f"  [ERR] FOOTER menu: {resp.status_code} {resp.text[:200]}")

    footer_id = state.data["si_menus"].get("FOOTER")
    if footer_id and not dry_run:
        footer_items = [
            {
                "labelPt": "Sobre Angola",
                "labelEn": "About Angola",
                "labelDe": "Über Angola",
                "url": "/sobre-angola",
                "sortOrder": 0,
            },
            {
                "labelPt": "Serviços Consulares",
                "labelEn": "Consular Services",
                "labelDe": "Konsularische Dienste",
                "url": "/servicos-consulares",
                "sortOrder": 1,
            },
            {
                "labelPt": "Política de Privacidade",
                "labelEn": "Privacy Policy",
                "labelDe": "Datenschutz",
                "url": "/politica-privacidade",
                "sortOrder": 2,
            },
            {
                "labelPt": "Contactos",
                "labelEn": "Contacts",
                "labelDe": "Kontakte",
                "url": "/contactos",
                "sortOrder": 3,
            },
        ]

        for item in footer_items:
            resp = requests.post(
                f"{SI_BACKEND}/api/v1/menus/{footer_id}/items",
                headers=headers, json=item, timeout=10,
            )
            if resp.status_code in (200, 201):
                print(f"    [OK] Footer item: {item['labelPt']}")
            else:
                print(f"    [ERR] Footer item {item['labelPt']}: {resp.status_code} {resp.text[:100]}")

    if not dry_run:
        state.mark_step(step)


# ── Step 7: Create SI Contacts ──────────────────────────────────────────────

def create_si_contacts(token: str, state: MigrationState, dry_run: bool = False):
    step = "contacts"
    if state.is_done(step):
        print(f"[SKIP] {step} already done")
        return

    print("\n=== Step 7: Create SI Contact Info ===")
    headers = auth_headers(token)

    contacts = [
        {
            "departamento": "Embaixada da República de Angola",
            "endereco": "Wallstraße 58",
            "cidade": "Berlin",
            "codigoPostal": "10179",
            "pais": "Deutschland",
            "telefone": "+49 30 240 897 0",
            "fax": "+49 30 240 897 12",
            "email": "info@botschaftangola.de",
            "horarioPt": "Segunda a Sexta: 09:00 - 17:00",
            "horarioEn": "Monday to Friday: 09:00 - 17:00",
            "horarioDe": "Montag bis Freitag: 09:00 - 17:00",
            "latitude": 52.5128,
            "longitude": 13.4125,
            "sortOrder": 0,
        },
        {
            "departamento": "Secção Consular",
            "endereco": "Wallstraße 58",
            "cidade": "Berlin",
            "codigoPostal": "10179",
            "pais": "Deutschland",
            "telefone": "+49 30 240 897 18",
            "email": "konsulat@botschaftangola.de",
            "horarioPt": "Segunda a Sexta: 09:00 - 13:00 (Atendimento ao público)",
            "horarioEn": "Monday to Friday: 09:00 - 13:00 (Public hours)",
            "horarioDe": "Montag bis Freitag: 09:00 - 13:00 (Publikumsverkehr)",
            "latitude": 52.5128,
            "longitude": 13.4125,
            "sortOrder": 1,
        },
        {
            "departamento": "Secção Consular - Praga (República Checa)",
            "endereco": "Represented from Berlin",
            "cidade": "Praha",
            "pais": "Česká republika",
            "telefone": "+49 30 240 897 0",
            "email": "info@botschaftangola.de",
            "horarioPt": "Atendimento mediante marcação prévia",
            "horarioEn": "By appointment only",
            "horarioDe": "Nur nach Terminvereinbarung",
            "sortOrder": 2,
        },
    ]

    for contact in contacts:
        if dry_run:
            print(f"  [DRY] Would create contact: {contact['departamento']}")
            continue

        resp = requests.post(f"{SI_BACKEND}/api/v1/contacts", headers=headers, json=contact, timeout=10)
        if resp.status_code in (200, 201):
            result = resp.json()
            data = result.get("data", result)
            state.data["si_contacts"].append(data.get("id"))
            state.save()
            print(f"  [OK] {contact['departamento']} → {data.get('id')}")
        else:
            print(f"  [ERR] {contact['departamento']}: {resp.status_code} {resp.text[:200]}")

    if not dry_run:
        state.mark_step(step)


# ── Step 8: Create additional SI pages (About Angola, Embaixador, etc.) ─────

def create_additional_si_pages(token: str, state: MigrationState, dry_run: bool = False):
    step = "additional_pages"
    if state.is_done(step):
        print(f"[SKIP] {step} already done")
        return

    print("\n=== Step 8: Create Additional SI Pages ===")
    headers = auth_headers(token)

    additional_pages = [
        {
            "slug": "sobre-angola",
            "tipo": "INSTITUTIONAL",
            "sortOrder": 0,
            "translations": [{
                "idioma": "PT",
                "titulo": "Sobre Angola",
                "conteudo": "<p>Angola, oficialmente República de Angola, é um país da costa ocidental de África. "
                            "Com uma área de 1.246.700 km², é o sétimo maior país de África. "
                            "Faz fronteira com a Namíbia a sul, a República Democrática do Congo a norte e a leste, "
                            "a República do Congo a noroeste e a Zâmbia a leste. "
                            "A costa de Angola estende-se por 1.650 km ao longo do Oceano Atlântico.</p>",
                "excerto": "Informações gerais sobre a República de Angola",
                "metaTitulo": "Sobre Angola - Embaixada de Angola na Alemanha",
            }],
        },
        {
            "slug": "embaixador",
            "tipo": "INSTITUTIONAL",
            "sortOrder": 0,
            "translations": [{
                "idioma": "PT",
                "titulo": "O Embaixador",
                "conteudo": "<p>Embaixador da República de Angola na República Federal da Alemanha e República Checa.</p>",
                "excerto": "Perfil do Embaixador de Angola na Alemanha",
                "metaTitulo": "Embaixador - Embaixada de Angola na Alemanha",
            }],
        },
        {
            "slug": "relacoes-bilaterais",
            "tipo": "INSTITUTIONAL",
            "sortOrder": 0,
            "translations": [{
                "idioma": "PT",
                "titulo": "Relações Bilaterais Angola-Alemanha",
                "conteudo": "<p>As relações diplomáticas entre Angola e a Alemanha foram estabelecidas em 1975, "
                            "logo após a independência de Angola. Desde então, os dois países têm mantido "
                            "um diálogo construtivo em diversas áreas, incluindo cooperação económica, "
                            "cultural e técnica.</p>",
                "excerto": "Relações bilaterais entre Angola e a Alemanha",
                "metaTitulo": "Relações Bilaterais - Embaixada de Angola na Alemanha",
            }],
        },
        {
            "slug": "servicos-consulares",
            "tipo": "SERVICE",
            "sortOrder": 0,
            "translations": [{
                "idioma": "PT",
                "titulo": "Serviços Consulares",
                "conteudo": "<p>A Secção Consular da Embaixada de Angola na Alemanha presta diversos serviços "
                            "aos cidadãos angolanos residentes na Alemanha e na República Checa, "
                            "bem como a cidadãos estrangeiros que pretendem viajar para Angola.</p>"
                            "<h3>Serviços Disponíveis</h3>"
                            "<ul>"
                            "<li>Vistos de entrada para Angola</li>"
                            "<li>Passaportes</li>"
                            "<li>Bilhete de Identidade</li>"
                            "<li>Registo Civil</li>"
                            "<li>Certificados e Declarações</li>"
                            "<li>Legalizações</li>"
                            "</ul>",
                "excerto": "Serviços consulares da Embaixada de Angola na Alemanha",
                "metaTitulo": "Serviços Consulares - Embaixada de Angola na Alemanha",
            }],
        },
    ]

    for page_data in additional_pages:
        slug = page_data["slug"]
        if any(v for k, v in state.data["wp_pages"].items() if slug in str(v)):
            print(f"  [SKIP] {slug} (possibly exists)")
            continue

        if dry_run:
            print(f"  [DRY] Would create page: {slug}")
            continue

        resp = requests.post(f"{SI_BACKEND}/api/v1/pages", headers=headers, json=page_data, timeout=15)
        if resp.status_code in (200, 201):
            result = resp.json()
            data = result.get("data", result)
            page_id = data.get("id")
            state.data["wp_pages"][f"additional_{slug}"] = page_id
            state.save()

            # Publish the page
            requests.patch(
                f"{SI_BACKEND}/api/v1/pages/{page_id}/estado",
                headers=headers, json={"estado": "PUBLISHED"}, timeout=10,
            )
            print(f"  [OK] {slug} → {page_id}")
        else:
            print(f"  [ERR] {slug}: {resp.status_code} {resp.text[:200]}")

    if not dry_run:
        state.mark_step(step)


# ── Main ─────────────────────────────────────────────────────────────────────

STEPS = {
    "media": migrate_media,
    "categories": migrate_categories,
    "author": create_wn_author,
    "posts": migrate_posts,
    "pages": migrate_pages,
    "menus": create_si_menus,
    "contacts": create_si_contacts,
    "additional_pages": create_additional_si_pages,
}

# Execution order (media first so images are available for posts/pages)
STEP_ORDER = [
    "categories",
    "author",
    "media",
    "posts",
    "pages",
    "additional_pages",
    "menus",
    "contacts",
]


def main():
    parser = argparse.ArgumentParser(description="WordPress → Ecossistema migration")
    parser.add_argument("--step", choices=list(STEPS.keys()), help="Run a single step")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    parser.add_argument("--reset", action="store_true", help="Reset migration state")
    parser.add_argument("--status", action="store_true", help="Show migration status")
    args = parser.parse_args()

    state = MigrationState()

    if args.reset:
        STATE_FILE.unlink(missing_ok=True)
        print("[OK] Migration state reset")
        return

    if args.status:
        print("Migration state:")
        print(f"  Completed steps: {state.data['completed_steps']}")
        print(f"  Categories: {len(state.data['wp_categories'])}")
        print(f"  Posts→Articles: {len(state.data['wp_posts'])}")
        print(f"  Pages: {len(state.data['wp_pages'])}")
        print(f"  WN Media: {len(state.data['wp_media_wn'])}")
        print(f"  SI Media: {len(state.data['wp_media_si'])}")
        print(f"  Menus: {list(state.data['si_menus'].keys())}")
        print(f"  Contacts: {len(state.data['si_contacts'])}")
        return

    print("=" * 60)
    print("WordPress → Ecossistema Digital Migration")
    print("=" * 60)
    print(f"  WP Source:  {WP_BASE}")
    print(f"  SI Backend: {SI_BACKEND}")
    print(f"  WN Backend: {WN_BACKEND}")
    print(f"  Keycloak:   {KEYCLOAK_URL}")
    print(f"  Dry run:    {args.dry_run}")
    print()

    # Authenticate
    if args.dry_run:
        token = "dry-run-token"
        print("[DRY] Skipping Keycloak authentication")
    else:
        token = get_keycloak_token()

    # Run steps
    if args.step:
        STEPS[args.step](token, state, args.dry_run)
    else:
        for step_name in STEP_ORDER:
            STEPS[step_name](token, state, args.dry_run)

    print("\n" + "=" * 60)
    print("Migration complete!")
    print("=" * 60)
    print(f"  Categories: {len(state.data['wp_categories'])}")
    print(f"  Articles:   {len(state.data['wp_posts'])}")
    print(f"  Pages:      {len(state.data['wp_pages'])}")
    print(f"  WN Media:   {len(state.data['wp_media_wn'])}")
    print(f"  SI Media:   {len(state.data['wp_media_si'])}")
    print(f"  Menus:      {list(state.data['si_menus'].keys())}")
    print(f"  Contacts:   {len(state.data['si_contacts'])}")


if __name__ == "__main__":
    main()
