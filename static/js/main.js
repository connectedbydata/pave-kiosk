document.addEventListener("DOMContentLoaded", () => {
    // DOM Elements
    const iframe = document.getElementById("kiosk-iframe");
    const loaderOverlay = document.getElementById("loader-overlay");
    const offlineOverlay = document.getElementById("offline-overlay");
    const connectionStatus = document.getElementById("connection-status");
    const statusText = document.getElementById("status-text");
    
    const btnSite1 = document.getElementById("btn-site-1");
    const btnRefresh = document.getElementById("btn-refresh");
    const btnReset = document.getElementById("btn-reset");
    const btnReconnect = document.getElementById("btn-reconnect");

    // QR Code Modal DOM Elements
    const linkModal = document.getElementById("link-modal");
    const btnCloseModal = document.getElementById("btn-close-modal");
    const qrcodeBox = document.getElementById("qrcode");
    const modalTimer = document.getElementById("modal-timer");
    const modalTargetUrl = document.getElementById("modal-target-url");

    let qrCodeInstance = null;
    let modalTimerInterval = null;
    let modalTimerCountdown = 15;

    // URLs and configuration
    const site1Url = btnSite1 ? btnSite1.getAttribute("data-url") : "/";
    let currentUrl = site1Url;
    let isLoaderTimeoutActive = false;

    // --- IFRAME LOAD MANAGEMENT ---
    
    function showLoader() {
        loaderOverlay.classList.remove("hidden");
        // Safety timeout: hide loader after 12 seconds in case iframe load event fails to fire
        isLoaderTimeoutActive = true;
        setTimeout(() => {
            if (isLoaderTimeoutActive) {
                hideLoader();
            }
        }, 12000);
    }

    function hideLoader() {
        isLoaderTimeoutActive = false;
        loaderOverlay.classList.add("hidden");
    }

    // Bind iframe load listener
    iframe.addEventListener("load", () => {
        // Add a slight transition buffer for a premium visual feel
        setTimeout(hideLoader, 300);
    });

    // --- NAVIGATION LOGIC ---

    function switchSite(selectedButton, url) {
        if (currentUrl === url && !loaderOverlay.classList.contains("hidden")) {
            return; // Already loading/loaded
        }
        
        // Update active class on navigation buttons
        document.querySelectorAll(".nav-button").forEach(btn => btn.classList.remove("active"));
        selectedButton.classList.add("active");
        
        // Show loader and update iframe source
        showLoader();
        currentUrl = url;
        iframe.src = url;
    }

    // Setup click handlers for all navigation buttons
    document.querySelectorAll(".nav-button").forEach(button => {
        const url = button.getAttribute("data-url");
        if (url) {
            button.addEventListener("click", () => switchSite(button, url));
        }
    });

    // --- UTILITIES ---

    // Refresh current iframe
    btnRefresh.addEventListener("click", () => {
        showLoader();
        iframe.src = currentUrl;
    });

    // Reset kiosk to default (Site 1)
    btnReset.addEventListener("click", () => {
        switchSite(btnSite1, site1Url);
    });

    // --- NETWORK/CONNECTIVITY MANAGEMENT ---

    function updateConnectionStatus(isOnline) {
        if (isOnline) {
            connectionStatus.classList.remove("offline");
            connectionStatus.classList.add("online");
            statusText.textContent = "Online";
            offlineOverlay.classList.add("hidden");
        } else {
            connectionStatus.classList.remove("online");
            connectionStatus.classList.add("offline");
            statusText.textContent = "Offline";
            // Kiosk is designed to run from local files offline.
            // Do not show blocking offline screen overlay.
            offlineOverlay.classList.add("hidden");
        }
    }

    // Ping the network using fetch to check actual internet accessibility.
    // We ping one of the target sites with 'no-cors' mode to bypass CORS.
    async function pingInternet() {
        try {
            // Check internet by fetching the target server with a cache-buster
            await fetch("https://pave-live.pairs.site/favicon.ico", {
                mode: "no-cors",
                cache: "no-store",
                method: "HEAD", // lighter request
                signal: AbortSignal.timeout(5000) // 5s timeout
            });
            updateConnectionStatus(true);
        } catch (error) {
            console.warn("Internet ping failed, checking navigator.onLine:", error);
            // Fall back to browser state if ping fails
            updateConnectionStatus(navigator.onLine);
        }
    }

    // Event listeners for offline/online browser changes
    window.addEventListener("online", () => {
        pingInternet();
    });
    
    window.addEventListener("offline", () => {
        updateConnectionStatus(false);
    });

    // Reconnect Button handler
    btnReconnect.addEventListener("click", () => {
        btnReconnect.textContent = "Checking...";
        btnReconnect.disabled = true;
        pingInternet().finally(() => {
            btnReconnect.textContent = "Retry Now";
            btnReconnect.disabled = false;
        });
    });

    // --- EXTERNAL LINK MODAL & QR CODE ---

    // Helper function to truncate long URLs
    function truncateUrl(urlStr, maxLength = 45) {
        if (urlStr.length <= maxLength) return urlStr;
        return urlStr.substring(0, maxLength - 3) + "...";
    }

    function openLinkModal(url) {
        // Clear any existing modal timers
        closeLinkModal();

        // Show the modal
        linkModal.classList.remove("hidden");

        // Display the truncated target URL
        modalTargetUrl.textContent = truncateUrl(url, 45);
        modalTargetUrl.setAttribute("title", url);

        // Clear previous QR code
        qrcodeBox.innerHTML = "";

        // Generate new QR code using the loaded QRCode library
        try {
            qrCodeInstance = new QRCode(qrcodeBox, {
                text: url,
                width: 180,
                height: 180,
                colorDark: "#0f172a",
                colorLight: "#ffffff",
                correctLevel: QRCode.CorrectLevel.H
            });
        } catch (e) {
            console.error("Failed to generate QR Code:", e);
            qrcodeBox.textContent = "Error generating QR Code.";
        }

        // Start countdown timer
        modalTimerCountdown = 15;
        modalTimer.textContent = modalTimerCountdown;

        modalTimerInterval = setInterval(() => {
            modalTimerCountdown--;
            modalTimer.textContent = modalTimerCountdown;

            if (modalTimerCountdown <= 0) {
                closeLinkModal();
            }
        }, 1000);
    }

    function closeLinkModal() {
        linkModal.classList.add("hidden");
        if (modalTimerInterval) {
            clearInterval(modalTimerInterval);
            modalTimerInterval = null;
        }
    }

    btnCloseModal.addEventListener("click", closeLinkModal);

    // Listen to messages from the proxied iframe
    window.addEventListener("message", (event) => {
        // Security check: ensure origin matches kiosk origin
        if (event.origin !== window.location.origin) {
            return;
        }

        if (event.data && event.data.type === "EXTERNAL_NAVIGATION") {
            openLinkModal(event.data.url);
        }
    });

    // Prevent default browser context menu to make it feel like a native kiosk application
    document.addEventListener("contextmenu", event => {
        event.preventDefault();
    });

    // Periodic ping to verify connection status (every 15 seconds)
    setInterval(pingInternet, 15000);

    // Initial load and ping
    showLoader();
    pingInternet();
});
