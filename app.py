import os
import re
import requests
from flask import Flask, render_template, redirect, request, Response

app = Flask(__name__)

# Kiosk configuration
app.config.update(
    PORT=int(os.environ.get("KIOSK_PORT", 8080)),
    HOST=os.environ.get("KIOSK_HOST", "0.0.0.0"),
    SITE_1_TITLE="PAVE Case Book",
    SITE_1_URL="https://pave-live.pairs.site/",
    SITE_2_TITLE="Let's Talk AI",
    SITE_2_URL="https://www.letstalkai.org.uk/",
    SITE_3_TITLE="Citizens Track",
    SITE_3_URL="https://www.citizens-track.org/?kiosk",
)

def rewrite_content(content, site_id, content_type):
    if site_id == "site1":
        target_domain = "pave-live.pairs.site"
        proxy_prefix = ""  # Root proxied, no prefix needed
    elif site_id == "site2":
        target_domain = "www.letstalkai.org.uk"
        proxy_prefix = "/proxy/site2"
    elif site_id == "site3":
        target_domain = "www.citizens-track.org"
        proxy_prefix = "/proxy/site3"
    else:
        return content

    if "text/html" in content_type:
        # 1. Rewrite absolute target domains (with or without protocol)
        content = re.sub(
            rf'(https?:)?//({target_domain}|letstalkai.org.uk|citizens-track.org)',
            proxy_prefix,
            content
        )

        # 2. Rewrite root-relative paths in href, src, action attributes
        # (Only if prefix is not empty, since root-relative is already correct for site1)
        if proxy_prefix:
            def replace_html_attr(match):
                attr = match.group("attr")
                path = match.group("path")
                if path.startswith("/proxy/") or path.startswith("http://") or path.startswith("https://") or path.startswith("javascript:") or path.startswith("#"):
                    return match.group(0)
                return f'{attr}="{proxy_prefix}{path}"'

            content = re.sub(
                r'(?P<attr>href|src|action)=\"(?P<path>/[^\"]*)\"',
                replace_html_attr,
                content
            )

            def replace_html_attr_single(match):
                attr = match.group("attr")
                path = match.group("path")
                if path.startswith("/proxy/") or path.startswith("http://") or path.startswith("https://") or path.startswith("javascript:") or path.startswith("#"):
                    return match.group(0)
                return f"{attr}='{proxy_prefix}{path}'"

            content = re.sub(
                r"(?P<attr>href|src|action)=\'(?P<path>/[^\']*)\'",
                replace_html_attr_single,
                content
            )

        return content

    elif "text/css" in content_type:
        # Rewrite root-relative URLs in stylesheets (only if we have a prefix)
        if proxy_prefix:
            def replace_css_url(match):
                path = match.group(1)
                if path.startswith("/proxy/") or path.startswith("http://") or path.startswith("https://") or path.startswith("data:"):
                    return match.group(0)
                return f"url({proxy_prefix}{path})"

            content = re.sub(r'url\([\'\"]?(/[^\'\"]+)[\'\"]?\)', replace_css_url, content)
        return content

    return content

def get_injected_js(site_id):
    # Interception script injected inside the proxied iframe pages
    return """
    <script>
    (function() {
        // Check if URL is considered "internal" to the kiosk allowed portals
        function getSiteIdForUrl(urlStr) {
            try {
                var targetUrl = new URL(urlStr, window.location.href);
                
                // If it's already a proxied URL on the same origin, determine its siteId
                if (targetUrl.origin === window.location.origin) {
                    if (targetUrl.pathname.startsWith('/proxy/site2/')) return 'site2';
                    if (targetUrl.pathname.startsWith('/proxy/site3/')) return 'site3';
                    // The kiosk UI is not a portal site
                    if (targetUrl.pathname.startsWith('/kiosk/')) return null;
                    // Everything else on this origin belongs to site1 (which is at the root)
                    return 'site1';
                }
                
                // Direct domain match mappings
                var host = targetUrl.hostname;
                if (host === "pave-live.pairs.site" || host.endsWith(".pave-live.pairs.site")) {
                    return 'site1';
                }
                if (host === "www.letstalkai.org.uk" || host === "letstalkai.org.uk" || host.endsWith(".letstalkai.org.uk")) {
                    return 'site2';
                }
                if (host === "www.citizens-track.org" || host === "citizens-track.org" || host.endsWith(".citizens-track.org")) {
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
                        var prefix = siteId === 'site1' ? '' : '/proxy/' + siteId;
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

# Proxied Site 2 and Site 3 routes
@app.route("/proxy/<site_id>/")
@app.route("/proxy/<site_id>/<path:subpath>")
def proxy_route(site_id, subpath=""):
    if site_id not in ["site2", "site3"]:
        return "Not Found", 404
    return proxy(site_id, subpath)

# Core proxy runner helper
def proxy(site_id, subpath=""):
    if site_id == "site1":
        target_base = app.config["SITE_1_URL"]
    elif site_id == "site2":
        target_base = app.config["SITE_2_URL"]
    elif site_id == "site3":
        target_base = app.config["SITE_3_URL"]
    else:
        return "Not Found", 404

    # Build target URL
    from urllib.parse import urljoin
    target_url = urljoin(target_base, subpath)
    if request.query_string:
        decoded_query = request.query_string.decode('utf-8')
        if "?" in target_url:
            target_url += f"&{decoded_query}"
        else:
            target_url += f"?{decoded_query}"

    # Set headers
    headers = {
        "User-Agent": request.headers.get("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Kiosk/1.0"),
        "Accept": request.headers.get("Accept"),
        "Accept-Language": request.headers.get("Accept-Language")
    }

    try:
        resp = requests.get(target_url, headers=headers, allow_redirects=True, timeout=10)
    except Exception as e:
        return f"Kiosk Proxy Error: Could not load target resource. Details: {str(e)}", 502

    content_type = resp.headers.get("Content-Type", "")

    if "text/html" in content_type:
        # Prevent requests default ISO-8859-1 decoding for UTF-8 pages when charset header is missing
        encoding = resp.encoding
        if not encoding or encoding.lower() == 'iso-8859-1':
            encoding = 'utf-8'
        try:
            html_content = resp.content.decode(encoding, errors='replace')
        except Exception:
            html_content = resp.text

        html_content = rewrite_content(html_content, site_id, content_type)
        
        # Inject script
        injection = get_injected_js(site_id)
        if "</body>" in html_content:
            html_content = html_content.replace("</body>", f"{injection}</body>")
        else:
            html_content += injection
            
        return Response(html_content, status=resp.status_code, content_type=content_type)
        
    elif "text/css" in content_type:
        encoding = resp.encoding
        if not encoding or encoding.lower() == 'iso-8859-1':
            encoding = 'utf-8'
        try:
            css_content = resp.content.decode(encoding, errors='replace')
        except Exception:
            css_content = resp.text

        css_content = rewrite_content(css_content, site_id, content_type)
        return Response(css_content, status=resp.status_code, content_type=content_type)
        
    else:
        # Static binary assets (images, fonts, JS, etc.)
        excluded_headers = ['content-encoding', 'content-length', 'transfer-encoding', 'connection']
        headers_to_forward = [(name, value) for name, value in resp.raw.headers.items()
                              if name.lower() not in excluded_headers]
        
        return Response(resp.content, status=resp.status_code, headers=headers_to_forward, content_type=content_type)

# Core root proxy handler (matches anything that doesn't match other routes)
@app.route("/", defaults={"subpath": ""})
@app.route("/<path:subpath>")
def root_proxy(subpath=""):
    # Exclude system static assets, proxy routes, health checks, and kiosk portal from being proxied to site1
    if subpath.startswith("static/") or subpath.startswith("proxy/") or subpath == "health" or subpath == "kiosk" or subpath.startswith("kiosk/"):
        return "Not Found", 404
        
    # Check referer to catch escaped assets for site2 and site3
    referer = request.headers.get("Referer", "")
    if "/proxy/site2" in referer:
        return redirect(f"/proxy/site2/{subpath}", code=302)
    elif "/proxy/site3" in referer:
        return redirect(f"/proxy/site3/{subpath}", code=302)

    # Otherwise, it belongs to Site 1 (PAVE Case Book) which is at the root!
    return proxy("site1", subpath)

@app.route("/health")
def health():
    return {"status": "healthy"}, 200

if __name__ == "__main__":
    app.run(
        host=app.config["HOST"],
        port=app.config["PORT"],
        debug=os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    )
