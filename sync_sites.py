#!/usr/bin/env python3
import os
import sys
import re
import shutil
import subprocess
from urllib.parse import urlparse, urljoin
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# Set paths
KIOSK_DIR = os.path.dirname(os.path.abspath(__file__))
SITES_DIR = os.path.join(KIOSK_DIR, "sites")

# Load environment variables
load_dotenv(os.path.join(KIOSK_DIR, ".env"))

def get_repo_paths():
    """Detect repo paths or prompt user if not set."""
    pave_path = os.getenv("PAVE_REPO_PATH")
    ct_path = os.getenv("CITIZENS_TRACK_REPO_PATH")
    
    # Defaults relative to kiosk
    default_pave = os.path.abspath(os.path.join(KIOSK_DIR, "../CitizensTrack/PAVE"))
    default_ct = os.path.abspath(os.path.join(KIOSK_DIR, "../CitizensTrack/citizens-track"))
    
    # Alternative defaults
    alt_pave = os.path.abspath(os.path.join(KIOSK_DIR, "../PAVE"))
    alt_ct = os.path.abspath(os.path.join(KIOSK_DIR, "../citizens-track"))
    
    if not pave_path:
        if os.path.exists(default_pave):
            pave_path = default_pave
        elif os.path.exists(alt_pave):
            pave_path = alt_pave
            
    if not ct_path:
        if os.path.exists(default_ct):
            ct_path = default_ct
        elif os.path.exists(alt_ct):
            ct_path = alt_ct
            
    # Prompt if still not resolved and running interactively
    if sys.stdin.isatty():
        if not pave_path or not os.path.exists(pave_path):
            print("\n--- PAVE Repository Setup ---")
            pave_path = input(f"Enter absolute path to PAVE repo (default: {default_pave}): ").strip()
            if not pave_path:
                pave_path = default_pave
            pave_path = os.path.abspath(pave_path)
            save_env_var("PAVE_REPO_PATH", pave_path)
            
        if not ct_path or not os.path.exists(ct_path):
            print("\n--- Citizens Track Repository Setup ---")
            ct_path = input(f"Enter absolute path to citizens-track.org repo (default: {default_ct}): ").strip()
            if not ct_path:
                ct_path = default_ct
            ct_path = os.path.abspath(ct_path)
            save_env_var("CITIZENS_TRACK_REPO_PATH", ct_path)
            
    else:
        # Fallbacks for non-interactive
        if not pave_path:
            pave_path = default_pave
        if not ct_path:
            ct_path = default_ct
            
    return pave_path, ct_path

def get_airtable_creds(pave_repo_path):
    """Retrieve Airtable credentials from environment, PAVE's .env, or prompt user."""
    pat = os.getenv("AIRTABLE_PAT")
    base_id = os.getenv("AIRTABLE_BASE_ID")
    
    # Try reading from PAVE repo's .env if present
    pave_env = os.path.join(pave_repo_path, ".env")
    if (not pat or not base_id) and os.path.exists(pave_env):
        try:
            with open(pave_env, "r") as f:
                lines = f.readlines()
            for line in lines:
                if "=" in line:
                    key, val = line.strip().split("=", 1)
                    key = key.strip()
                    val = val.strip().strip("'").strip('"')
                    if key == "AIRTABLE_PAT" and not pat:
                        pat = val
                    elif key == "AIRTABLE_BASE_ID" and not base_id:
                        base_id = val
        except Exception as e:
            print(f"Warning: Could not read PAVE .env file: {e}")
            
    # Prompt if missing and interactive
    if sys.stdin.isatty():
        if not pat:
            pat = input("Enter your AIRTABLE_PAT: ").strip()
            if pat:
                save_env_var("AIRTABLE_PAT", pat)
        if not base_id:
            base_id = input("Enter your AIRTABLE_BASE_ID: ").strip()
            if base_id:
                save_env_var("AIRTABLE_BASE_ID", base_id)
                
    return pat, base_id

def save_env_var(key, value):
    """Write env variable to local .env file."""
    env_path = os.path.join(KIOSK_DIR, ".env")
    lines = []
    exists = False
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            lines = f.readlines()
            
    for i, line in enumerate(lines):
        if line.strip().startswith(f"{key}="):
            lines[i] = f"{key}={value}\n"
            exists = True
            break
            
    if not exists:
        lines.append(f"{key}={value}\n")
        
    with open(env_path, "w") as f:
        f.writelines(lines)
    print(f"Saved {key} to local .env file.")

def run_command(args, cwd=None, env=None):
    """Utility to run a system shell command."""
    print(f"Running command: {' '.join(args)} in {cwd or 'current directory'}")
    result = subprocess.run(args, cwd=cwd, env=env, text=True)
    if result.returncode != 0:
        print(f"Error: Command failed with exit code {result.returncode}")
        return False
    return True

def rewrite_offline_links(dest_dir, site_id):
    """Process HTML and CSS files and replace absolute domains with relative local URLs."""
    print(f"Post-processing and rewriting offline links in {dest_dir}...")
    
    # Define rewriting targets
    # Site 1 -> root "/"
    # Site 2 -> "/proxy/site2"
    # Site 3 -> "/proxy/site3"
    
    # Walk through directory
    for root, _, files in os.walk(dest_dir):
        for file in files:
            if file.endswith((".html", ".css", ".js", ".xml")):
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                        
                    # 1. Rewrite Let's Talk AI absolute references
                    content = re.sub(
                        r'(https?:)?//(www\.)?letstalkai\.org\.uk',
                        '/proxy/site2',
                        content
                    )
                    
                    # 2. Rewrite Citizens Track absolute references
                    content = re.sub(
                        r'(https?:)?//(www\.)?citizens-track\.org',
                        '/proxy/site3',
                        content
                    )
                    content = re.sub(
                        r'(https?:)?//(www\.)?citizen-track\.org',
                        '/proxy/site3',
                        content
                    )
                    
                    # 3. Rewrite PAVE Case Book absolute references
                    content = re.sub(
                        r'(https?:)?//pave-live\.pairs\.site',
                        '',  # Maps to root "/"
                        content
                    )
                    
                    # Save modified content
                    with open(file_path, "w", encoding="utf-8") as f:
                        f.write(content)
                except Exception as e:
                    print(f"  Error post-processing file {file_path}: {e}")

def sync_pave():
    """Sync PAVE Case Book (Jekyll build)."""
    pave_path, _ = get_repo_paths()
    if not os.path.exists(pave_path):
        print(f"Error: PAVE repository not found at {pave_path}")
        return False
        
    print(f"\n==========================================")
    print(f"Syncing PAVE Case Book from {pave_path}...")
    print(f"==========================================")
    
    # Get Airtable credentials
    pat, base_id = get_airtable_creds(pave_path)
    
    # 1. Run sync_data.py
    if pat and base_id:
        print("Airtable credentials loaded. Running sync_data.py...")
        env = os.environ.copy()
        env["AIRTABLE_PAT"] = pat
        env["AIRTABLE_BASE_ID"] = base_id
        
        # Check if python dependencies for sync_data are present in current interpreter
        # Since we just installed them in kiosk venv, they are available.
        # We run it using the kiosk python to ensure dependencies are loaded
        py_executable = sys.executable
        run_command([py_executable, "scripts/sync_data.py"], cwd=pave_path, env=env)
    else:
        print("Warning: Airtable credentials not found. Skipping Airtable sync step.")
        print("Will proceed with compiling existing local data files.")
        
    # 2. Build with Jekyll
    dest_dir = os.path.join(SITES_DIR, "site1")
    os.makedirs(dest_dir, exist_ok=True)
    
    print("Installing bundle gems...")
    if not run_command(["bundle", "config", "set", "--local", "path", "vendor/bundle"], cwd=pave_path):
        return False
    if not run_command(["bundle", "install"], cwd=pave_path):
        return False
        
    print("Building PAVE Case Book with Jekyll...")
    if not run_command(["bundle", "exec", "jekyll", "build", "--destination", dest_dir], cwd=pave_path):
        return False
        
    # 3. Post-process URL rewriting
    rewrite_offline_links(dest_dir, "site1")
    print("✓ PAVE Case Book synced successfully.")
    return True

def sync_citizens_track():
    """Sync Citizens Track (Jekyll build)."""
    _, ct_path = get_repo_paths()
    if not os.path.exists(ct_path):
        print(f"Error: Citizens Track repository not found at {ct_path}")
        return False
        
    print(f"\n==========================================")
    print(f"Syncing Citizens Track from {ct_path}...")
    print(f"==========================================")
    
    dest_dir = os.path.join(SITES_DIR, "site3")
    os.makedirs(dest_dir, exist_ok=True)
    
    # 1. Build with Jekyll
    print("Installing bundle gems...")
    if not run_command(["bundle", "config", "set", "--local", "path", "vendor/bundle"], cwd=ct_path):
        return False
    if not run_command(["bundle", "install"], cwd=ct_path):
        return False
        
    print("Building Citizens Track with Jekyll...")
    if not run_command(["bundle", "exec", "jekyll", "build", "--destination", dest_dir], cwd=ct_path):
        return False
        
    # 2. Post-process URL rewriting
    rewrite_offline_links(dest_dir, "site3")
    print("✓ Citizens Track synced successfully.")
    return True

def sync_lets_talk_ai():
    """Mirror and rewrite Let's Talk AI website."""
    print(f"\n==========================================")
    print(f"Mirroring Let's Talk AI...")
    print(f"==========================================")
    
    dest_dir = os.path.join(SITES_DIR, "site2")
    os.makedirs(dest_dir, exist_ok=True)
    
    start_url = "https://www.letstalkai.org.uk/"
    domain = "www.letstalkai.org.uk"
    
    to_crawl_html = {start_url}
    crawled_html = set()
    assets_to_download = set()
    downloaded_assets = set()
    
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) KioskMirror/1.0"
    })
    
    html_count = 0
    max_html_pages = 150
    
    # Step 1: Crawl HTML pages and identify assets
    while to_crawl_html and html_count < max_html_pages:
        current_url = to_crawl_html.pop()
        clean_url = current_url.split("?")[0].split("#")[0].rstrip("/")
        if clean_url in crawled_html:
            continue
            
        crawled_html.add(clean_url)
        html_count += 1
        
        print(f"[{html_count}] Crawling page: {current_url}")
        try:
            resp = session.get(current_url, timeout=15)
            if resp.status_code != 200:
                print(f"  Warning: status {resp.status_code}")
                continue
                
            content_type = resp.headers.get("Content-Type", "")
            if "text/html" not in content_type:
                continue
                
            html_content = resp.text
            soup = BeautifulSoup(html_content, "html.parser")
            
            # Find subpages
            for a in soup.find_all("a", href=True):
                href = a["href"]
                resolved = urljoin(current_url, href)
                parsed = urlparse(resolved)
                
                if parsed.netloc == domain or parsed.netloc == "letstalkai.org.uk":
                    path = parsed.path.lower()
                    if not any(path.endswith(ext) for ext in [".pdf", ".zip", ".png", ".jpg", ".jpeg", ".gif", ".css", ".js", ".woff", ".woff2", ".ttf"]):
                        url_no_hash = resolved.split("#")[0]
                        clean_resolved = url_no_hash.split("?")[0].rstrip("/")
                        if clean_resolved not in crawled_html:
                            to_crawl_html.add(url_no_hash)
                            
            # Identify assets
            for img in soup.find_all("img", src=True):
                assets_to_download.add(urljoin(current_url, img["src"]))
            for img in soup.find_all("img", getattr(img, "data-src", "")):
                if img.get("data-src"):
                    assets_to_download.add(urljoin(current_url, img["data-src"]))
                    
            for link in soup.find_all("link", href=True):
                rel = link.get("rel", [])
                if any(r in rel for r in ["stylesheet", "icon", "apple-touch-icon", "shortcut icon"]):
                    assets_to_download.add(urljoin(current_url, link["href"]))
                    
            for script in soup.find_all("script", src=True):
                assets_to_download.add(urljoin(current_url, script["src"]))
                
            # Write page to local directory
            parsed_url = urlparse(clean_url)
            path = parsed_url.path.strip("/")
            
            if not path:
                file_path = os.path.join(dest_dir, "index.html")
            else:
                file_path = os.path.join(dest_dir, path, "index.html")
                
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(html_content)
                
        except Exception as e:
            print(f"  Error crawling {current_url}: {e}")
            
    # Step 2: Download assets and search CSS for sub-resources (fonts/backgrounds)
    # We copy the set so we can add to the set dynamically while iterating
    assets_queue = list(assets_to_download)
    print(f"Discovered {len(assets_queue)} initial assets. Downloading...")
    
    asset_count = 0
    while asset_count < len(assets_queue):
        asset_url = assets_queue[asset_count]
        asset_count += 1
        
        parsed_asset = urlparse(asset_url)
        if parsed_asset.netloc not in [domain, "letstalkai.org.uk"] and "wp-content" not in asset_url:
            continue
            
        clean_asset_path = parsed_asset.path.lstrip("/")
        if not clean_asset_path:
            continue
            
        if clean_asset_path in downloaded_assets:
            continue
            
        downloaded_assets.add(clean_asset_path)
        local_asset_path = os.path.join(dest_dir, clean_asset_path)
        os.makedirs(os.path.dirname(local_asset_path), exist_ok=True)
        
        print(f"  [{asset_count}] Downloading asset: {clean_asset_path}")
        try:
            r = session.get(asset_url, stream=True, timeout=15)
            if r.status_code == 200:
                with open(local_asset_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=1024):
                        f.write(chunk)
                
                # Scan CSS for fonts/images
                if clean_asset_path.endswith(".css"):
                    try:
                        with open(local_asset_path, "r", encoding="utf-8", errors="ignore") as f:
                            css_content = f.read()
                        urls = re.findall(r'url\([\'\"]?([^\'\"]+?)[\'\"]?\)', css_content)
                        for u in urls:
                            if u.startswith("data:") or u.startswith("http:") or u.startswith("https:"):
                                if not u.startswith("https://www.letstalkai.org.uk") and not u.startswith("https://letstalkai.org.uk"):
                                    continue
                            resolved_u = urljoin(asset_url, u)
                            if resolved_u not in assets_queue:
                                assets_queue.append(resolved_u)
                    except Exception as e:
                        print(f"    Error scanning CSS {clean_asset_path}: {e}")
                        
                # Scan JS for assets/images
                if clean_asset_path.endswith(".js"):
                    try:
                        with open(local_asset_path, "r", encoding="utf-8", errors="ignore") as f:
                            js_content = f.read()
                        
                        # Find all local assets paths starting with /toons/assets/ or /wp-content/ or /toons/js/
                        urls = re.findall(r'[\'"]((?:/toons/assets/|/wp-content/|/toons/js/)[^\'"]+?\.(?:webp|png|jpg|jpeg|gif|svg|woff2|woff|ttf|eot|css|js))[\'"]', js_content)
                        for u in urls:
                            resolved_u = urljoin(start_url, u)
                            if resolved_u not in assets_queue:
                                assets_queue.append(resolved_u)
                    except Exception as e:
                        print(f"    Error scanning JS {clean_asset_path}: {e}")
            else:
                print(f"    Failed download: status {r.status_code}")
        except Exception as e:
            print(f"    Error downloading {asset_url}: {e}")
            
    # Step 3: Rewrite offline links
    rewrite_offline_links(dest_dir, "site2")
    print("✓ Let's Talk AI mirrored successfully.")
    return True

def main():
    os.makedirs(SITES_DIR, exist_ok=True)
    
    # Support command line args (e.g. sync_sites.py --site site1)
    target = None
    if len(sys.argv) > 1:
        arg = sys.argv[1].lower()
        if "pave" in arg or "site1" in arg or arg == "1":
            target = "1"
        elif "talk" in arg or "site2" in arg or arg == "2":
            target = "2"
        elif "citizen" in arg or "site3" in arg or arg == "3":
            target = "3"
        elif "all" in arg or arg == "4":
            target = "4"
            
    if not target:
        print("=" * 45)
        print(" Touchscreen Kiosk Offline Sync Utility")
        print("=" * 45)
        print("1) PAVE Case Book (Jekyll build & Airtable sync)")
        print("2) Let's Talk AI (Web crawl mirror)")
        print("3) Citizens Track (Jekyll build)")
        print("4) All Sites")
        print("5) Exit")
        print("-" * 45)
        target = input("Choose site to sync (1-5): ").strip()
        
    if target == "1":
        sync_pave()
    elif target == "2":
        sync_lets_talk_ai()
    elif target == "3":
        sync_citizens_track()
    elif target == "4":
        s1 = sync_pave()
        s2 = sync_lets_talk_ai()
        s3 = sync_citizens_track()
        if s1 and s2 and s3:
            print("\n✓ All sites synced and compiled successfully!")
        else:
            print("\n⚠ Some sites failed to sync. Review logs above.")
    elif target == "5":
        print("Exited.")
    else:
        print("Invalid choice.")

if __name__ == "__main__":
    main()
