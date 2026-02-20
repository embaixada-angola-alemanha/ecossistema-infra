#!/usr/bin/env python3
"""
Import featured images from botschaftangola.de WordPress to WN MinIO + DB.

Requires: pip install requests minio psycopg2-binary Pillow

Usage:
  python wp_import_images.py                # Full import
  python wp_import_images.py --dry-run      # Preview only
  python wp_import_images.py --limit 10     # Import first 10 only
"""

import argparse
import io
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
from PIL import Image

# ── Configuration ─────────────────────────────────────────────────────────────

WP_BASE = "https://botschaftangola.de/wp-json/wp/v2"

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "wn_db")
DB_USER = os.getenv("DB_USER", "ecossistema")
DB_PASS = os.getenv("DB_PASS", "postgres_dev_2026")

MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "localhost:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minio_admin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minio_dev_2026")
MINIO_BUCKET = "wn-media"

MEDIA_DIR = Path(__file__).parent / "media_cache"
STATE_FILE = Path(__file__).parent / "wp_images_state.json"

MAX_WIDTH = 1200
MAX_HEIGHT = 800

# ── Helpers ───────────────────────────────────────────────────────────────────


def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"imported": {}, "failed": [], "skipped": []}


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False))


def get_db_connection():
    import psycopg2
    return psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
        user=DB_USER, password=DB_PASS
    )


def get_minio_client():
    from minio import Minio
    return Minio(
        MINIO_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=False
    )


def fetch_articles_without_images(conn):
    """Get all articles without featured images."""
    cur = conn.cursor()
    cur.execute("""
        SELECT id, slug, titulo_pt
        FROM articles
        WHERE featured_image_id IS NULL
          AND estado = 'PUBLISHED'
        ORDER BY published_at DESC
    """)
    rows = cur.fetchall()
    cur.close()
    return [{"id": str(r[0]), "slug": r[1], "title": r[2]} for r in rows]


def fetch_wp_featured_image(slug):
    """Get featured image URL and metadata from WordPress."""
    try:
        resp = requests.get(
            f"{WP_BASE}/posts",
            params={"slug": slug, "_embed": "true"},
            timeout=30
        )
        if resp.status_code != 200 or not resp.json():
            return None

        post = resp.json()[0]
        embedded = post.get("_embedded", {})
        media_list = embedded.get("wp:featuredmedia", [])
        if not media_list:
            return None

        media = media_list[0]
        source_url = media.get("source_url")
        if not source_url:
            return None

        # Get best size (prefer medium_large for reasonable quality/size)
        sizes = media.get("media_details", {}).get("sizes", {})
        best_url = source_url  # fallback to full
        for size_key in ["medium_large", "large", "full"]:
            if size_key in sizes:
                best_url = sizes[size_key].get("source_url", best_url)
                break

        return {
            "url": best_url,
            "mime_type": media.get("mime_type", "image/jpeg"),
            "alt_text": media.get("alt_text", ""),
            "width": media.get("media_details", {}).get("width"),
            "height": media.get("media_details", {}).get("height"),
        }
    except Exception as e:
        print(f"  WordPress API error: {e}")
        return None


def download_image(url, slug):
    """Download image to local cache. Returns path or None."""
    MEDIA_DIR.mkdir(exist_ok=True)

    ext = Path(urlparse(url).path).suffix or ".jpg"
    cache_path = MEDIA_DIR / f"{slug}{ext}"

    if cache_path.exists() and cache_path.stat().st_size > 0:
        return cache_path

    try:
        resp = requests.get(url, timeout=60, stream=True)
        resp.raise_for_status()
        with open(cache_path, "wb") as f:
            for chunk in resp.iter_content(8192):
                f.write(chunk)
        return cache_path
    except Exception as e:
        print(f"  Download error: {e}")
        cache_path.unlink(missing_ok=True)
        return None


def resize_image(file_path):
    """Resize image to max dimensions, return bytes + dimensions."""
    try:
        img = Image.open(file_path)
        img = img.convert("RGB")

        w, h = img.size
        if w > MAX_WIDTH or h > MAX_HEIGHT:
            ratio = min(MAX_WIDTH / w, MAX_HEIGHT / h)
            new_w, new_h = int(w * ratio), int(h * ratio)
            img = img.resize((new_w, new_h), Image.LANCZOS)
        else:
            new_w, new_h = w, h

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85, optimize=True)
        buf.seek(0)
        return buf, new_w, new_h
    except Exception as e:
        print(f"  Resize error: {e}")
        return None, 0, 0


def upload_to_minio(client, image_buf, object_key, size):
    """Upload image bytes to MinIO."""
    # Ensure bucket exists
    if not client.bucket_exists(MINIO_BUCKET):
        client.make_bucket(MINIO_BUCKET)

    client.put_object(
        MINIO_BUCKET,
        object_key,
        image_buf,
        length=size,
        content_type="image/jpeg"
    )


def insert_media_record(conn, media_id, file_name, object_key, size, width, height, alt_text):
    """Insert media_files record and return the id."""
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO media_files (id, file_name, original_name, mime_type, size,
                                  bucket, object_key, alt_pt, width, height,
                                  created_by, version)
        VALUES (%s, %s, %s, 'image/jpeg', %s, %s, %s, %s, %s, %s, 'wp_import', 0)
    """, (media_id, file_name, file_name, size, MINIO_BUCKET, object_key,
          alt_text or None, width, height))
    cur.close()


def link_article_image(conn, article_id, media_id):
    """Set article's featured_image_id."""
    cur = conn.cursor()
    cur.execute("""
        UPDATE articles SET featured_image_id = %s WHERE id = %s
    """, (media_id, article_id))
    cur.close()


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Import WP featured images to WN")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    parser.add_argument("--limit", type=int, default=0, help="Max articles to process (0=all)")
    args = parser.parse_args()

    state = load_state()
    conn = get_db_connection()
    minio_client = None if args.dry_run else get_minio_client()

    articles = fetch_articles_without_images(conn)
    print(f"Found {len(articles)} articles without images")

    if args.limit > 0:
        articles = articles[:args.limit]

    imported = 0
    skipped = 0
    failed = 0

    for i, art in enumerate(articles, 1):
        slug = art["slug"]
        title = art["title"][:60] if art["title"] else slug

        # Skip if already processed
        if slug in state["imported"]:
            skipped += 1
            continue

        print(f"[{i}/{len(articles)}] {title}...")

        # 1. Fetch from WordPress
        wp_img = fetch_wp_featured_image(slug)
        if not wp_img:
            print(f"  No featured image in WordPress")
            state["skipped"].append(slug)
            skipped += 1
            time.sleep(0.3)
            continue

        if args.dry_run:
            print(f"  Would download: {wp_img['url']}")
            imported += 1
            continue

        # 2. Download image
        local_path = download_image(wp_img["url"], slug)
        if not local_path:
            state["failed"].append(slug)
            failed += 1
            continue

        # 3. Resize
        image_buf, width, height = resize_image(local_path)
        if not image_buf:
            state["failed"].append(slug)
            failed += 1
            continue

        size = image_buf.getbuffer().nbytes
        media_id = str(uuid.uuid4())
        file_name = f"{media_id}.jpg"
        object_key = f"articles/{file_name}"

        # 4. Upload to MinIO
        try:
            upload_to_minio(minio_client, image_buf, object_key, size)
        except Exception as e:
            print(f"  MinIO upload error: {e}")
            state["failed"].append(slug)
            failed += 1
            continue

        # 5. Insert DB records
        try:
            insert_media_record(conn, media_id, file_name, object_key, size,
                                width, height, wp_img.get("alt_text", ""))
            link_article_image(conn, art["id"], media_id)
            conn.commit()
        except Exception as e:
            conn.rollback()
            print(f"  DB error: {e}")
            state["failed"].append(slug)
            failed += 1
            continue

        state["imported"][slug] = media_id
        imported += 1
        print(f"  OK ({width}x{height}, {size // 1024}kB)")

        # Save state periodically
        if imported % 10 == 0:
            save_state(state)

        time.sleep(0.3)  # Be polite to WordPress

    save_state(state)
    conn.close()

    print(f"\nDone: {imported} imported, {skipped} skipped, {failed} failed")


if __name__ == "__main__":
    main()
