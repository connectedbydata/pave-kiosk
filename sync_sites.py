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
                    ltai_replacement = '/site4' if site_id == 'site4' else '/proxy/site2'
                    content = re.sub(
                        r'(https?:)?//(www\.)?letstalkai\.org\.uk',
                        ltai_replacement,
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
                        r'(https?:)?//(pave-live|pave)\.pairs\.site',
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
                
            # Remove srcset and sizes from all images to force using local src
            for tag in soup.find_all(["img", "source"]):
                if tag.has_attr("srcset"):
                    del tag["srcset"]
                if tag.has_attr("sizes"):
                    del tag["sizes"]

            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(str(soup))
                
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
    
    # Re-apply customizations to site4
    copy_and_customize_site4()
    
    return True

def copy_and_customize_site4():
    """Copy site2 to site4 and apply custom print takeaway modifications."""
    print(f"\n==========================================")
    print(f"Creating customized Site 4 (Alternative Let's Talk AI)...")
    print(f"==========================================")
    
    site2_dir = os.path.join(SITES_DIR, "site2")
    site4_dir = os.path.join(SITES_DIR, "site4")
    
    if not os.path.exists(site2_dir):
        print("Error: site2 directory does not exist. Please sync Let's Talk AI (site2) first.")
        return False
        
    if os.path.exists(site4_dir):
        print("Removing existing site4 directory...")
        try:
            shutil.rmtree(site4_dir)
        except Exception as e:
            print(f"Warning: Could not remove site4 directory: {e}")
            
    print("Copying site2 to site4...")
    try:
        shutil.copytree(site2_dir, site4_dir)
    except Exception as e:
        print(f"Error copying site2 to site4: {e}")
        return False
        
    # Rewrite proxy/site2 urls to site4 in all files in site4
    print("Rewriting proxy urls in site4 files...")
    for root_dir, _, files in os.walk(site4_dir):
        for file in files:
            if file.endswith((".html", ".css", ".js", ".xml")):
                file_path = os.path.join(root_dir, file)
                try:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        file_content = f.read()
                    
                    # Replace /proxy/site2 with /site4
                    new_file_content = file_content.replace('/proxy/site2', '/site4')
                    
                    if new_file_content != file_content:
                        with open(file_path, "w", encoding="utf-8") as f:
                            f.write(new_file_content)
                except Exception as e:
                    print(f"  Error post-processing file {file_path}: {e}")
                    
    # Inject print takeaway button and modal into site4/index.html
    index_path = os.path.join(site4_dir, "index.html")
    if not os.path.exists(index_path):
        print(f"Error: index.html not found in {site4_dir}")
        return False
        
    try:
        with open(index_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
            
        soup = BeautifulSoup(content, "html.parser")
        
        # Inject print takeaway button above controls and below cartoons by finding #ltai-fan-stage
        stage = soup.find(id="ltai-fan-stage")
        if stage:
            button_markup = """
    <!-- Print Takeaway Button -->
    <div class="ltai-print-takeaway-container">
      <button class="ltai-print-takeaway-btn" id="ltai-print-takeaway-btn">
        <svg class="ltai-print-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="6 9 6 2 18 2 18 9"></polyline>
          <path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"></path>
          <rect x="6" y="14" width="12" height="8"></rect>
        </svg>
        Print takeaway
      </button>
    </div>
"""
            button_soup = BeautifulSoup(button_markup, "html.parser")
            stage.insert_after(button_soup)
            print("✓ Injected Print takeaway button markup using BeautifulSoup.")
        else:
            print("Warning: Could not find element #ltai-fan-stage in index.html to inject button.")
                
        # Inject styles, modal HTML and JS before </body>
        modal_injection = """
<style>
/* Styling for Print takeaway button */
.ltai-print-takeaway-container {
    margin: 2rem 0;
    display: flex;
    justify-content: center;
    width: 100%;
}

.ltai-print-takeaway-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 0.75rem;
    background: linear-gradient(135deg, #7a00df, #9b51e0);
    color: #ffffff !important;
    font-family: "Raleway", sans-serif;
    font-weight: 700;
    font-size: 1.15rem;
    padding: 0.85rem 2.2rem;
    border: none;
    border-radius: 9999px;
    box-shadow: 0 4px 15px rgba(122, 0, 223, 0.3);
    cursor: pointer;
    transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
    outline: none;
    text-decoration: none;
}

.ltai-print-takeaway-btn:hover {
    transform: translateY(-2px) scale(1.03);
    background: linear-gradient(135deg, #8b1ff0, #a862f5);
    box-shadow: 0 8px 25px rgba(122, 0, 223, 0.45);
}

.ltai-print-takeaway-btn:active {
    transform: translateY(1px) scale(0.98);
    box-shadow: 0 2px 8px rgba(122, 0, 223, 0.3);
}

.ltai-print-icon {
    transition: transform 0.3s ease;
}

.ltai-print-takeaway-btn:hover .ltai-print-icon {
    transform: rotate(-10deg) scale(1.1);
}

/* Modal styles */
.ltai-print-modal-overlay {
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background-color: rgba(0, 0, 0, 0.65);
    backdrop-filter: blur(8px);
    -webkit-backdrop-filter: blur(8px);
    z-index: 999999;
    display: flex;
    align-items: center;
    justify-content: center;
    opacity: 0;
    pointer-events: none;
    transition: opacity 0.3s ease;
}

.ltai-print-modal-overlay.active {
    opacity: 1;
    pointer-events: auto;
}

.ltai-print-modal {
    background: #ffffff;
    border: 1px solid rgba(255, 255, 255, 0.8);
    border-radius: 24px;
    width: 90%;
    max-width: 460px;
    padding: 2.5rem;
    box-shadow: 0 24px 50px rgba(0, 0, 0, 0.3);
    text-align: center;
    position: relative;
    transform: scale(0.9) translateY(20px);
    transition: transform 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.ltai-print-modal-overlay.active .ltai-print-modal {
    transform: scale(1) translateY(0);
}

.ltai-print-modal-close {
    position: absolute;
    top: 1.25rem;
    right: 1.25rem;
    background: none;
    border: none;
    font-size: 1.75rem;
    cursor: pointer;
    color: #aaa;
    line-height: 1;
    padding: 0.25rem;
    transition: color 0.2s ease, transform 0.2s ease;
}

.ltai-print-modal-close:hover {
    color: #333;
    transform: scale(1.1);
}

.ltai-print-modal-header h3 {
    margin-top: 0;
    margin-bottom: 0.75rem;
    font-family: "Raleway", sans-serif;
    font-weight: 800;
    color: #111;
    font-size: 1.8rem;
    line-height: 1.2;
}

.ltai-print-modal-desc {
    font-family: "Source Sans 3", sans-serif;
    color: #666;
    margin-bottom: 2rem;
    font-size: 1.05rem;
    line-height: 1.5;
}

.ltai-print-options-grid {
    display: flex;
    flex-direction: column;
    gap: 1rem;
    margin-bottom: 0.5rem;
}

.ltai-print-option-card {
    display: flex;
    align-items: center;
    gap: 1.25rem;
    background: #fcfbfe;
    border: 2px solid #eae6f0;
    border-radius: 16px;
    padding: 1.25rem 1.5rem;
    text-align: left;
    cursor: pointer;
    transition: all 0.25s cubic-bezier(0.25, 0.8, 0.25, 1);
}

.ltai-print-option-card:hover {
    background: #f7f0ff;
    border-color: #7a00df;
    transform: translateY(-2px);
    box-shadow: 0 8px 20px rgba(122, 0, 223, 0.1);
}

.ltai-print-option-card:active {
    transform: translateY(0);
}

.ltai-option-icon-wrapper {
    background: #f0e6fc;
    border-radius: 50%;
    width: 48px;
    height: 48px;
    display: flex;
    align-items: center;
    justify-content: center;
    color: #7a00df;
    flex-shrink: 0;
    transition: background-color 0.25s ease, color 0.25s ease;
}

.ltai-print-option-card:hover .ltai-option-icon-wrapper {
    background: #7a00df;
    color: #ffffff;
}

.ltai-option-details {
    flex-grow: 1;
}

.ltai-option-title {
    display: block;
    font-family: "Raleway", sans-serif;
    font-weight: 700;
    font-size: 1.2rem;
    color: #222;
    margin-bottom: 0.25rem;
}

.ltai-option-subtitle {
    display: block;
    font-family: "Source Sans 3", sans-serif;
    font-size: 0.95rem;
    color: #666;
}

/* Success/Printing state in modal */
.ltai-print-status-view {
    display: none;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 1.5rem 0;
}

.ltai-spinner {
    width: 54px;
    height: 54px;
    border: 5px solid #eae0f7;
    border-top: 5px solid #7a00df;
    border-radius: 50%;
    animation: ltai-spin 1s linear infinite;
    margin-bottom: 1.5rem;
}

@keyframes ltai-spin {
    0% { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
}

.ltai-success-icon {
    width: 54px;
    height: 54px;
    background: #e2f8eb;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    color: #00b050;
    margin-bottom: 1.5rem;
    animation: ltai-scaleIn 0.3s cubic-bezier(0.34, 1.56, 0.64, 1) forwards;
}

@keyframes ltai-scaleIn {
    0% { transform: scale(0); opacity: 0; }
    100% { transform: scale(1); opacity: 1; }
}

.ltai-print-status-text {
    font-family: "Raleway", sans-serif;
    font-weight: 700;
    font-size: 1.4rem;
    color: #111;
    margin-bottom: 0.5rem;
}

.ltai-print-status-subtext {
    font-family: "Source Sans 3", sans-serif;
    color: #666;
    font-size: 1.05rem;
}
</style>

<!-- Modal Overlay -->
<div class="ltai-print-modal-overlay" id="ltai-print-modal-overlay">
  <div class="ltai-print-modal">
    <button class="ltai-print-modal-close" id="ltai-print-modal-close" aria-label="Close modal">&times;</button>
    
    <!-- Primary Options View -->
    <div class="ltai-print-options-view" id="ltai-print-options-view">
      <div class="ltai-print-modal-header">
        <h3>Print takeaway</h3>
      </div>
      <p class="ltai-print-desc">Choose a version of the story scroll to print and take home with you!</p>
      
      <div class="ltai-print-options-grid">
        <div class="ltai-print-option-card" id="ltai-print-teaser-opt">
          <div class="ltai-option-icon-wrapper">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="12" cy="12" r="10"></circle>
              <polyline points="12 6 12 12 16 14"></polyline>
            </svg>
          </div>
          <div class="ltai-option-details">
            <span class="ltai-option-title">Print teaser</span>
            <span class="ltai-option-subtitle">Takes ~5 seconds</span>
          </div>
        </div>
        
        <div class="ltai-print-option-card" id="ltai-print-full-opt">
          <div class="ltai-option-icon-wrapper">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
              <polyline points="14 2 14 8 20 8"></polyline>
              <line x1="16" y1="13" x2="8" y2="13"></line>
              <line x1="16" y1="17" x2="8" y2="17"></line>
              <polyline points="10 9 9 9 8 9"></polyline>
            </svg>
          </div>
          <div class="ltai-option-details">
            <span class="ltai-option-title">Print full scroll</span>
            <span class="ltai-option-subtitle">Takes ~1 minute</span>
          </div>
        </div>
      </div>
    </div>
    
    <!-- Status / Loading View -->
    <div class="ltai-print-status-view" id="ltai-print-status-view">
      <div id="ltai-print-status-graphic">
        <div class="ltai-spinner"></div>
      </div>
      <div class="ltai-print-status-text" id="ltai-print-status-text">Sending to printer...</div>
      <div class="ltai-print-status-subtext" id="ltai-print-status-subtext">Preparing document for print.</div>
    </div>
  </div>
</div>

<script>
(function() {
  var overlay = document.getElementById('ltai-print-modal-overlay');
  var closeBtn = document.getElementById('ltai-print-modal-close');
  var openBtn = document.getElementById('ltai-print-takeaway-btn');
  
  var optionsView = document.getElementById('ltai-print-options-view');
  var statusView = document.getElementById('ltai-print-status-view');
  var statusGraphic = document.getElementById('ltai-print-status-graphic');
  var statusText = document.getElementById('ltai-print-status-text');
  var statusSubtext = document.getElementById('ltai-print-status-subtext');
  
  var teaserOpt = document.getElementById('ltai-print-teaser-opt');
  var fullOpt = document.getElementById('ltai-print-full-opt');
  
  function openModal() {
    overlay.classList.add('active');
    optionsView.style.display = 'block';
    statusView.style.display = 'none';
  }
  
  function closeModal() {
    overlay.classList.remove('active');
  }
  
  if (openBtn) {
    openBtn.addEventListener('click', openModal);
  }
  
  if (closeBtn) {
    closeBtn.addEventListener('click', closeModal);
  }
  
  if (overlay) {
    overlay.addEventListener('click', function(e) {
      if (e.target === overlay) {
        closeModal();
      }
    });
  }
  
  function handlePrintChoice(type, timeEst) {
    optionsView.style.display = 'none';
    statusView.style.display = 'flex';
    
    // Step 1: Show "Sending to printer..."
    statusGraphic.innerHTML = '<div class="ltai-spinner"></div>';
    statusText.innerText = 'Sending to printer...';
    statusSubtext.innerText = 'Connecting to thermal printer...';
    
    // Get active cartoon index
    var activeCard = document.querySelector('.ltai-fan-card[data-pos="0"]');
    var episodeIdx = activeCard ? activeCard.getAttribute('data-idx') : '0';
    
    // Send fetch print request to the kiosk Flask server
    fetch('/site4/api/print', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        type: type,
        episode: parseInt(episodeIdx, 10)
      })
    })
    .then(function(response) {
      if (!response.ok) {
        return response.json().then(function(err) { throw err; });
      }
      return response.json();
    })
    .then(function(data) {
      if (data.status === 'success' && data.job_id) {
        var jobId = data.job_id;
        
        // Start polling the job status
        var pollInterval = setInterval(function() {
          fetch('/site4/api/status/' + jobId)
            .then(function(res) { return res.json(); })
            .then(function(statusData) {
              if (statusData.status === 'completed') {
                clearInterval(pollInterval);
                statusGraphic.innerHTML = '<div class="ltai-success-icon"><svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg></div>';
                statusText.innerText = 'Printed!';
                statusSubtext.innerText = 'Takeaway print completed successfully.';
                setTimeout(function() {
                  closeModal();
                }, 2500);
              } else if (statusData.status === 'failed') {
                clearInterval(pollInterval);
                statusGraphic.innerHTML = '<div style="color: #cf2e2e; font-size: 54px; margin-bottom: 1.5rem; font-weight: bold;">&times;</div>';
                statusText.innerText = 'Print failed';
                statusSubtext.innerText = statusData.error || 'An error occurred while printing.';
                setTimeout(function() {
                  closeModal();
                }, 5000);
              } else if (statusData.status === 'printing') {
                statusText.innerText = 'Printing...';
                statusSubtext.innerText = 'Please wait for your print... (' + timeEst + ')';
              } else if (statusData.status === 'queued') {
                statusText.innerText = 'Queued...';
                statusSubtext.innerText = 'Waiting for printer to become available...';
              }
            })
            .catch(function(err) {
              // Ignore transient polling errors
            });
        }, 1000);
        
      } else {
        throw new Error(data.message || 'Print job failed.');
      }
    })
    .catch(function(error) {
      // Show error
      statusGraphic.innerHTML = '<div style="color: #cf2e2e; font-size: 54px; margin-bottom: 1.5rem; font-weight: bold;">&times;</div>';
      statusText.innerText = 'Print failed';
      statusSubtext.innerText = error.message || 'An error occurred while printing.';
      setTimeout(function() {
        closeModal();
      }, 4000);
    });
  }
  
  if (teaserOpt) {
    teaserOpt.addEventListener('click', function() {
      handlePrintChoice('teaser', '5 seconds');
    });
  }
  
  if (fullOpt) {
    fullOpt.addEventListener('click', function() {
      handlePrintChoice('full scroll', '1 minute');
    });
  }
})();
</script>
</body>"""

        if soup.body:
            modal_soup = BeautifulSoup(modal_injection, "html.parser")
            soup.body.append(modal_soup)
            print("✓ Injected styles, modal HTML and script before </body> using BeautifulSoup.")
        else:
            print("Warning: No body element found in index.html.")
            
        content = str(soup)
            
        with open(index_path, "w", encoding="utf-8") as f:
            f.write(content)
            
        print("✓ Customized site4/index.html successfully.")
        return True
    except Exception as e:
        print(f"Error customizing site4/index.html: {e}")
        return False

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
