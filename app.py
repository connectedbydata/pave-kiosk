import os
import re
import requests
import queue
import threading
import subprocess
from flask import Flask, render_template, redirect, request, Response, send_from_directory

app = Flask(__name__)

# Kiosk configuration
app.config.update(
    PORT=int(os.environ.get("KIOSK_PORT", 8080)),
    HOST=os.environ.get("KIOSK_HOST", "0.0.0.0"),
    SITE_1_TITLE="PAVE Case Book",
    SITE_1_URL="https://pave.pairs.site/",
    SITE_2_TITLE="Let's Talk AI",
    SITE_2_URL="https://www.letstalkai.org.uk/",
    SITE_3_TITLE="Citizens Track",
    SITE_3_URL="https://citizens-track.org/?kiosk",
)

@app.after_request
def add_header(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

def serve_local(site_id, subpath=""):
    # Normalize paths to prevent path traversal
    if ".." in subpath or subpath.startswith("/"):
        return "Forbidden", 403
        
    sites_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sites")
    
    if site_id == "site1":
        site_dir = os.path.join(sites_dir, "site1")
    elif site_id == "site2":
        site_dir = os.path.join(sites_dir, "site2")
    elif site_id == "site3":
        site_dir = os.path.join(sites_dir, "site3")
    elif site_id == "site4":
        site_dir = os.path.join(sites_dir, "site4")
    else:
        return "Not Found", 404

    # If the local site directory does not exist, return a friendly message
    if not os.path.exists(site_dir):
        return f"Site directory not found. Please run 'python sync_sites.py' to fetch and compile the sites first.", 503

    # Normalize subpath for directories
    if not subpath:
        subpath = "index.html"
    elif subpath.endswith("/"):
        subpath += "index.html"

    full_path = os.path.join(site_dir, subpath)

    # Check if this resolves to a directory without a trailing slash
    if os.path.isdir(full_path):
        # Redirect to ensure proper relative asset resolution in browser
        return redirect(request.path + "/", code=301)

    # If file doesn't exist, return 404
    if not os.path.exists(full_path):
        return "Not Found", 404

    # If it is HTML, we dynamically inject get_injected_js(site_id)
    if full_path.endswith(".html"):
        try:
            with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            
            injection = get_injected_js(site_id)
            if "</body>" in content:
                content = content.replace("</body>", f"{injection}</body>")
            else:
                content += injection
            return Response(content, content_type="text/html")
        except Exception as e:
            return f"Error reading file: {str(e)}", 500

    # Otherwise serve static assets normally
    directory = os.path.dirname(full_path)
    filename = os.path.basename(full_path)
    return send_from_directory(directory, filename)

def get_injected_js(site_id):
    # Interception script injected inside the proxied iframe pages
    return """
    <script>
    (function() {
        // Map local kiosk proxy URLs back to their original public URLs
        function getPublicUrl(urlStr) {
            try {
                var targetUrl = new URL(urlStr, window.location.href);
                if (targetUrl.origin === window.location.origin) {
                    // Determine which site context we are in (based on target URL path first, then current page path)
                    var siteId = null;
                    var subpath = targetUrl.pathname;
                    
                    if (targetUrl.pathname.startsWith('/proxy/site2/')) {
                        siteId = 'site2';
                        subpath = targetUrl.pathname.substring('/proxy/site2'.length);
                    } else if (targetUrl.pathname.startsWith('/site4/')) {
                        siteId = 'site4';
                        subpath = targetUrl.pathname.substring('/site4'.length);
                    } else if (targetUrl.pathname.startsWith('/proxy/site3/')) {
                        siteId = 'site3';
                        subpath = targetUrl.pathname.substring('/proxy/site3'.length);
                    } else if (targetUrl.pathname.startsWith('/kiosk/')) {
                        return targetUrl.href;
                    } else {
                        // Root-absolute path (e.g., /assets/...).
                        // Determine siteId based on current page URL context.
                        if (window.location.pathname.startsWith('/proxy/site2/')) {
                            siteId = 'site2';
                        } else if (window.location.pathname.startsWith('/site4/')) {
                            siteId = 'site4';
                        } else if (window.location.pathname.startsWith('/proxy/site3/')) {
                            siteId = 'site3';
                        } else {
                            siteId = 'site1';
                        }
                    }
                    
                    if (siteId === 'site2' || siteId === 'site4') {
                        return 'https://www.letstalkai.org.uk' + subpath + targetUrl.search + targetUrl.hash;
                    } else if (siteId === 'site3') {
                        return 'https://citizens-track.org' + subpath + targetUrl.search + targetUrl.hash;
                    } else {
                        return 'https://pave.pairs.site' + subpath + targetUrl.search + targetUrl.hash;
                    }
                }
                return targetUrl.href;
            } catch(e) {
                return urlStr;
            }
        }

        // Check if URL is considered "internal" to the kiosk allowed portals
        function getSiteIdForUrl(urlStr) {
            try {
                var targetUrl = new URL(urlStr, window.location.href);
                
                // If it's already a proxied URL on the same origin, determine its siteId
                if (targetUrl.origin === window.location.origin) {
                    if (targetUrl.pathname.startsWith('/proxy/site2/')) return 'site2';
                    if (targetUrl.pathname.startsWith('/site4/')) return 'site4';
                    if (targetUrl.pathname.startsWith('/proxy/site3/')) return 'site3';
                    // The kiosk UI is not a portal site
                    if (targetUrl.pathname.startsWith('/kiosk/')) return null;
                    // Everything else on this origin belongs to site1 (which is at the root)
                    return 'site1';
                }
                
                // Direct domain match mappings
                var host = targetUrl.hostname;
                if (host === "pave.pairs.site" || host.endsWith(".pave.pairs.site")) {
                    return 'site1';
                }
                if (host === "www.letstalkai.org.uk" || host === "letstalkai.org.uk" || host.endsWith(".letstalkai.org.uk")) {
                    if (window.location.pathname.startsWith('/site4/')) {
                        return 'site4';
                    }
                    return 'site2';
                }
                if (host === "citizens-track.org" || host === "www.citizens-track.org" || host.endsWith(".citizens-track.org")) {
                    return 'site3';
                }
            } catch(e) {}
            return null;
        }

        // Intercept all link clicks inside the iframe
        document.addEventListener('click', function(e) {
            var anchor = e.target.closest('a');
            if (anchor && anchor.href) {
                var href = anchor.getAttribute('href');
                
                // Skip internal page anchors or script URIs
                if (!href || href.startsWith('#') || href.startsWith('javascript:')) {
                    return;
                }
                
                // Resolve link relative to current document
                var absoluteUrl = new URL(anchor.href, window.location.href);
                
                // Check if it is a PDF file (even if locally held)
                var isPdf = absoluteUrl.pathname.toLowerCase().endsWith('.pdf');
                if (isPdf) {
                    e.preventDefault();
                    e.stopPropagation();
                    
                    var publicUrl = getPublicUrl(absoluteUrl.href);
                    window.parent.postMessage({
                        type: 'EXTERNAL_NAVIGATION',
                        url: publicUrl
                    }, '*');
                    return;
                }
                
                var siteId = getSiteIdForUrl(absoluteUrl.href);
                
                if (siteId) {
                    // Internal Navigation: rewrite the URL to load through the local proxy
                    e.preventDefault();
                    e.stopPropagation();
                    
                    var pathAndParams = absoluteUrl.pathname + absoluteUrl.search + absoluteUrl.hash;
                    // Avoid double /proxy prefix if already matching local origin
                    if (absoluteUrl.origin === window.location.origin) {
                        window.location.href = absoluteUrl.href;
                    } else {
                        var prefix = siteId === 'site1' ? '' : (siteId === 'site4' ? '/site4' : '/proxy/' + siteId);
                        window.location.href = window.location.origin + prefix + pathAndParams;
                    }
                } else {
                    // External Navigation: Block the link and send a message to the kiosk parent frame
                    e.preventDefault();
                    e.stopPropagation();
                    
                    window.parent.postMessage({
                        type: 'EXTERNAL_NAVIGATION',
                        url: absoluteUrl.href
                    }, '*');
                }
            }
        }, true); // Capture phase click listener
    })();
    </script>
    """

# Serve kiosk UI at /kiosk/
@app.route("/kiosk/")
def kiosk_portal():
    return render_template(
        "index.html",
        site_1_title=app.config["SITE_1_TITLE"],
        site_1_url="/",  # Root maps to PAVE Case Book
        site_2_title=app.config["SITE_2_TITLE"],
        site_2_url="/proxy/site2/",
        site_3_title=app.config["SITE_3_TITLE"],
        site_3_url="/proxy/site3/"
    )

# Redirect /kiosk to /kiosk/
@app.route("/kiosk")
def kiosk_redirect():
    return redirect("/kiosk/", code=301)

# Redirect to ensure proxy path ends with trailing slash
@app.route("/proxy/<site_id>")
def proxy_redirect(site_id):
    if site_id in ["site2", "site3"]:
        return redirect(f"/proxy/{site_id}/", code=301)
    return "Not Found", 404

# Local Site 2 and Site 3 routes
@app.route("/proxy/<site_id>/")
@app.route("/proxy/<site_id>/<path:subpath>")
def proxy_route(site_id, subpath=""):
    if site_id not in ["site2", "site3"]:
        return "Not Found", 404
    return serve_local(site_id, subpath)

# Alternative Let's Talk AI routes (Site 4)
@app.route("/site4")
def site4_redirect():
    return redirect("/site4/", code=301)

@app.route("/site4/")
@app.route("/site4/<path:subpath>")
def site4_route(subpath=""):
    return serve_local("site4", subpath)

# Thread-safe print queue for background printing
print_queue = queue.Queue()
job_states = {}
job_errors = {}

def print_worker():
    """Processes print jobs sequentially in a background thread to prevent blocking Flask."""
    while True:
        job = print_queue.get()
        if job is None:
            break
        print_type, episode, job_id = job
        job_states[job_id] = "printing"
        try:
            print(f"[Print Worker] Starting job {job_id}: type={print_type}, episode={episode}")
            python_exec = "/Users/admin/Documents/ConnectedByData/CitizensTrack/Orgbro/venv/bin/python"
            helper_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "print_helper.py")
            result = subprocess.run([python_exec, helper_script, "--type", print_type, "--episode", str(episode)], capture_output=True, text=True)
            if result.returncode == 0:
                print(f"[Print Worker] Job {job_id} finished successfully. Output:\n{result.stdout}")
                job_states[job_id] = "completed"
            else:
                err_msg = result.stderr.strip() if result.stderr else f"Exit code {result.returncode}"
                print(f"[Print Worker] Job {job_id} failed. Error:\n{err_msg}")
                job_states[job_id] = "failed"
                job_errors[job_id] = err_msg
        except Exception as e:
            print(f"[Print Worker] Exception running print job {job_id}: {e}")
            job_states[job_id] = "failed"
            job_errors[job_id] = str(e)
        finally:
            print_queue.task_done()

# Start background thread
worker_thread = threading.Thread(target=print_worker, daemon=True)
worker_thread.start()

@app.route("/site4/api/print", methods=["POST"])
def site4_print():
    data = request.get_json() or {}
    print_type = data.get("type")
    episode = data.get("episode")
    
    if print_type == "full scroll":
        print_type = "full"
        
    if print_type not in ["teaser", "full"] or episode not in [0, 1, 2]:
        return {"status": "error", "message": "Invalid print request parameters. Must specify type (teaser/full) and episode (0, 1, 2)."}, 400
        
    import uuid
    job_id = f"{print_type}-{episode}-{str(uuid.uuid4())[:6]}"
    job_states[job_id] = "queued"
    
    print_queue.put((print_type, episode, job_id))
    return {"status": "success", "message": "Print job queued successfully.", "job_id": job_id}

@app.route("/site4/api/status/<job_id>", methods=["GET"])
def site4_status(job_id):
    state = job_states.get(job_id, "completed")
    error_msg = job_errors.get(job_id, "")
    return {
        "job_id": job_id,
        "status": state,
        "error": error_msg
    }

# Core root handler (matches anything that doesn't match other routes)
@app.route("/", defaults={"subpath": ""})
@app.route("/<path:subpath>")
def root_route(subpath=""):
    # Exclude system static assets, proxy routes, health checks, and kiosk portal
    if subpath.startswith("static/") or subpath.startswith("proxy/") or subpath == "health" or subpath == "kiosk" or subpath.startswith("kiosk/") or subpath.startswith("site4") or subpath == "site4":
        return "Not Found", 404
        
    # Check referer to catch escaped assets for site2, site3, and site4
    referer = request.headers.get("Referer", "")
    if "/proxy/site2" in referer:
        return redirect(f"/proxy/site2/{subpath}", code=302)
    elif "/site4" in referer:
        return redirect(f"/site4/{subpath}", code=302)
    elif "/proxy/site3" in referer:
        return redirect(f"/proxy/site3/{subpath}", code=302)

    # Otherwise, it belongs to Site 1 (PAVE Case Book) which is served locally!
    return serve_local("site1", subpath)

@app.route("/health")
def health():
    return {"status": "healthy"}, 200

if __name__ == "__main__":
    app.run(
        host=app.config["HOST"],
        port=app.config["PORT"],
        debug=os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    )
