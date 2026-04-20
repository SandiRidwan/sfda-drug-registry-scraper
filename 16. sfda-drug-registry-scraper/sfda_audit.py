"""
╔══════════════════════════════════════════════════════════════════════════╗
║        SFDA DRUGS LIST — TECHNICAL AUDIT SCRIPT                        ║
║        Target: https://www.sfda.gov.sa/en/drugs-list                   ║
║        7 Critical Variables Audit + Stack Recommendation               ║
╚══════════════════════════════════════════════════════════════════════════╝

Usage:
    pip install requests playwright colorama
    playwright install chromium
    python sfda_audit.py

Output:
    - Console report (colored)
    - sfda_audit_report.txt (plain text)
    - sfda_captured_api.json (jika hidden API ditemukan)
"""

import requests
import json
import time
import random
import re
import sys
import os
from datetime import datetime
from urllib.parse import urljoin, urlparse, urlencode
from collections import defaultdict

# ── OPTIONAL: colored output ──────────────────────────────────────────────────
try:
    from colorama import init, Fore, Style, Back
    init(autoreset=True)
    GREEN  = Fore.GREEN + Style.BRIGHT
    YELLOW = Fore.YELLOW + Style.BRIGHT
    RED    = Fore.RED + Style.BRIGHT
    CYAN   = Fore.CYAN + Style.BRIGHT
    WHITE  = Fore.WHITE + Style.BRIGHT
    DIM    = Style.DIM
    RESET  = Style.RESET_ALL
    BOLD   = Style.BRIGHT
except ImportError:
    GREEN = YELLOW = RED = CYAN = WHITE = DIM = RESET = BOLD = ""

# ── CONFIG ────────────────────────────────────────────────────────────────────
TARGET_URL   = "https://www.sfda.gov.sa/en/drugs-list"
BASE_URL     = "https://www.sfda.gov.sa"
REPORT_FILE  = "sfda_audit_report.txt"
API_JSON_OUT = "sfda_captured_api.json"
TIMEOUT      = 20
TEST_PAGES   = [1, 2, 3]   # halaman yang dicoba saat test pagination

HEADERS_BROWSER = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,"
              "image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection":      "keep-alive",
    "DNT":             "1",
    "Upgrade-Insecure-Requests": "1",
}

HEADERS_API = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept":          "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer":         TARGET_URL,
    "Origin":          BASE_URL,
    "DNT":             "1",
    "Connection":      "keep-alive",
}

HEADERS_BOT = {
    "User-Agent": "python-requests/2.31.0",
    "Accept":     "*/*",
}

# ── KANDIDAT HIDDEN API ENDPOINT ──────────────────────────────────────────────
API_CANDIDATES = [
    "/api/drugs",
    "/api/v1/drugs",
    "/api/v2/drugs",
    "/api/drugs/list",
    "/api/drugs/search",
    "/api/drug/list",
    "/api/drug/search",
    "/en/api/drugs",
    "/api/medications",
    "/api/products",
    "/api/registrations",
    "/en/drugs-list/api",
    "/sfda-api/drugs",
    "/api/human-drugs",
    "/api/registered-drugs",
    "/api/drug-registration/list",
    "/api/portal/drugs",
    "/api/portal/drugs/list",
]

PAGINATION_PATTERNS = [
    "?page={}",
    "?pageNumber={}",
    "?pageNo={}",
    "?p={}",
    "?pg={}",
    "?offset={}",
    "?start={}",
]

PAGINATION_SIZES = [
    "&pageSize=10", "&pageSize=20", "&pageSize=50", "&pageSize=100",
    "&size=10", "&size=20", "&size=50", "&size=100",
    "&limit=10", "&limit=20", "&limit=50",
    "&rows=10", "&rows=20", "&rows=50",
    "",
]

# ── HASIL AUDIT (akan diisi saat run) ─────────────────────────────────────────
audit_results = {
    "timestamp":     datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "target":        TARGET_URL,
    "variables":     {},
    "recommendation": {},
    "api_found":     None,
    "sample_data":   None,
}
report_lines = []

# ══════════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════════

def log(msg, color="", level="INFO"):
    """Print ke console dan simpan ke report."""
    prefix = {"INFO": "  ", "OK": "✓ ", "WARN": "⚠ ", "FAIL": "✗ ", "HEAD": "► "}.get(level, "  ")
    console_line = f"{color}{prefix}{msg}{RESET}"
    plain_line   = f"{prefix}{msg}"
    print(console_line)
    report_lines.append(plain_line)

def section(title):
    bar = "═" * 60
    print(f"\n{CYAN}{bar}{RESET}")
    print(f"{CYAN}  {title}{RESET}")
    print(f"{CYAN}{bar}{RESET}")
    report_lines.append(f"\n{'═'*60}")
    report_lines.append(f"  {title}")
    report_lines.append(f"{'═'*60}")

def subsection(title):
    print(f"\n{WHITE}  ▸ {title}{RESET}")
    report_lines.append(f"\n  ▸ {title}")

def safe_request(url, headers=None, method="GET", data=None, params=None, timeout=TIMEOUT):
    """Request wrapper dengan error handling."""
    try:
        if method == "POST":
            r = requests.post(url, headers=headers or HEADERS_BROWSER,
                              json=data, params=params, timeout=timeout,
                              allow_redirects=True)
        else:
            r = requests.get(url, headers=headers or HEADERS_BROWSER,
                             params=params, timeout=timeout,
                             allow_redirects=True)
        return r
    except requests.exceptions.SSLError:
        return None
    except requests.exceptions.ConnectionError:
        return None
    except requests.exceptions.Timeout:
        return None
    except Exception:
        return None

def is_json_response(response):
    """Cek apakah response adalah JSON yang valid."""
    ct = response.headers.get("Content-Type", "")
    if "json" in ct:
        try:
            response.json()
            return True
        except Exception:
            return False
    try:
        data = response.json()
        return isinstance(data, (dict, list))
    except Exception:
        return False

def contains_drug_data(data):
    """Cek apakah JSON response kemungkinan berisi data obat."""
    if isinstance(data, list) and len(data) > 0:
        return True
    if isinstance(data, dict):
        # Cari key yang mengindikasikan list data
        for key in ["data", "items", "result", "results", "records",
                    "drugs", "medications", "list", "content", "rows"]:
            if key in data and isinstance(data[key], list):
                return True
        # Cari indikator pagination
        for key in ["total", "totalCount", "totalRecords", "count",
                    "recordCount", "totalElements"]:
            if key in data and isinstance(data[key], (int, float)):
                return True
    return False

def detect_arabic(text):
    """Return True jika string mengandung karakter Arab."""
    if not isinstance(text, str):
        return False
    return any('\u0600' <= c <= '\u06FF' for c in text)

# ══════════════════════════════════════════════════════════════════════════════
# AUDIT VARIABLE 1: RENDERING ARCHITECTURE
# ══════════════════════════════════════════════════════════════════════════════

def audit_rendering():
    section("VAR 1 — RENDERING ARCHITECTURE (Static/SSR vs Dynamic/CSR)")
    result = {"status": "unknown", "type": None, "details": []}

    subsection("Mengambil halaman utama...")
    r = safe_request(TARGET_URL, headers=HEADERS_BROWSER)
    if not r:
        log("Gagal connect ke target URL", RED, "FAIL")
        result["status"] = "unreachable"
        audit_results["variables"]["rendering"] = result
        return result

    log(f"HTTP Status: {r.status_code}", GREEN if r.status_code == 200 else RED,
        "OK" if r.status_code == 200 else "FAIL")
    log(f"Content-Type: {r.headers.get('Content-Type', 'N/A')}", WHITE)
    log(f"Content-Length: {len(r.content):,} bytes", WHITE)
    log(f"Final URL: {r.url}", WHITE)
    result["details"].append(f"status={r.status_code}")
    result["details"].append(f"bytes={len(r.content)}")

    # Analisis HTML
    html = r.text
    subsection("Analisis konten HTML...")

    # Cek tanda-tanda CSR / SPA framework
    csr_signals = {
        "React / Next.js":     ["__NEXT_DATA__", "react-dom", "_app.js", "__react"],
        "Vue.js":              ["__vue__", "Vue.config", "vue.min.js", "nuxt"],
        "Angular":             ["ng-version", "angular.min.js", "ng-app"],
        "Generic SPA":         ["app.js", "bundle.js", "main.chunk.js", "vendors~main"],
        "jQuery AJAX":         ["$.ajax", "$.get(", "$.post(", "XMLHttpRequest"],
        "Axios (API calls)":   ["axios.get", "axios.post", "import axios"],
        "Fetch API":           ["fetch(", "fetch('", 'fetch("'],
    }

    detected_frameworks = []
    for framework, signals in csr_signals.items():
        if any(s.lower() in html.lower() for s in signals):
            detected_frameworks.append(framework)
            log(f"Detected: {framework}", GREEN, "OK")

    if not detected_frameworks:
        log("Tidak ada CSR framework terdeteksi — kemungkinan SSR/server-rendered", YELLOW, "WARN")

    # Cek apakah ada data obat di HTML (indikasi SSR)
    drug_keywords = ["registration", "manufacturer", "drug name", "country of",
                     "Saudi agent", "Marketing company"]
    data_in_html = sum(1 for k in drug_keywords if k.lower() in html.lower())
    log(f"Drug-related keywords ditemukan di HTML: {data_in_html}/{len(drug_keywords)}", WHITE)

    # Cek script tags untuk API hints
    api_hints = re.findall(r'(?:api|endpoint|baseURL|apiUrl)["\s:=]+["\']([^"\']+)["\']',
                           html, re.IGNORECASE)
    if api_hints:
        log(f"API hints di HTML:", CYAN, "OK")
        for hint in api_hints[:5]:
            log(f"    → {hint}", CYAN)
            result["details"].append(f"api_hint={hint}")

    # Cek Next.js data injection
    nextjs_match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
    if nextjs_match:
        try:
            nextjs_data = json.loads(nextjs_match.group(1))
            log("Next.js __NEXT_DATA__ ditemukan — bisa extract data dari sini!", GREEN, "OK")
            result["nextjs_data"] = True
        except Exception:
            pass

    # Kesimpulan
    if detected_frameworks:
        result["type"] = "CSR/SPA"
        result["status"] = "dynamic"
        log(f"\n  KESIMPULAN: Site menggunakan CSR ({', '.join(detected_frameworks)})", GREEN, "HEAD")
        log("  → STRATEGI: Intercept XHR/Fetch requests, cari hidden JSON API", GREEN)
    elif data_in_html >= 3:
        result["type"] = "SSR"
        result["status"] = "static"
        log("\n  KESIMPULAN: Site kemungkinan SSR — data ada di HTML", YELLOW, "HEAD")
        log("  → STRATEGI: Parse HTML dengan BeautifulSoup/lxml", YELLOW)
    else:
        result["type"] = "Unknown"
        result["status"] = "partial"
        log("\n  KESIMPULAN: Tidak bisa dipastikan — perlu Playwright untuk konfirmasi", YELLOW, "HEAD")

    result["details"].append(f"frameworks={detected_frameworks}")
    audit_results["variables"]["rendering"] = result
    return result

# ══════════════════════════════════════════════════════════════════════════════
# AUDIT VARIABLE 2: PAGINATION & NAVIGATION
# ══════════════════════════════════════════════════════════════════════════════

def audit_pagination():
    section("VAR 2 — PAGINATION & NAVIGATION")
    result = {"status": "unknown", "pattern": None, "total": None, "details": []}

    subsection("Test URL-based pagination patterns...")

    found_patterns = []
    for pattern in PAGINATION_PATTERNS:
        for size_param in PAGINATION_SIZES[:4]:  # test 4 size variants saja
            test_url = TARGET_URL + pattern.format(2) + size_param
            log(f"Test: {test_url}", DIM)
            r = safe_request(test_url, headers=HEADERS_BROWSER)
            if r and r.status_code == 200:
                if r.url != TARGET_URL:  # URL berubah = pagination diterima
                    log(f"Pattern VALID: {pattern} + {size_param}", GREEN, "OK")
                    found_patterns.append((pattern, size_param, r.url))
                    break
            time.sleep(0.5)

    if found_patterns:
        result["status"] = "found"
        result["pattern"] = found_patterns[0][0]
        log(f"\n  Pattern terbaik: {found_patterns[0][0]}", GREEN)
    else:
        log("Tidak ada URL pagination ditemukan — kemungkinan POST-based atau infinite scroll", YELLOW, "WARN")
        result["status"] = "not_url_based"

    # Cek apakah ada indikator total records di halaman
    subsection("Mencari indikator total records di halaman utama...")
    r = safe_request(TARGET_URL, headers=HEADERS_BROWSER)
    if r and r.status_code == 200:
        html = r.text
        # Cari angka yang bisa jadi total count
        total_patterns = [
            r'total["\s:]+(\d+)',
            r'(\d{4,6})\s*(?:drugs?|records?|results?|items?|registrations?)',
            r'(?:showing|of)\s+(\d{4,6})',
            r'"count"\s*:\s*(\d+)',
            r'"total"\s*:\s*(\d+)',
        ]
        for pat in total_patterns:
            matches = re.findall(pat, html, re.IGNORECASE)
            if matches:
                log(f"Kandidat total records: {matches[:3]}", GREEN, "OK")
                result["total"] = matches[0]
                break

    audit_results["variables"]["pagination"] = result
    return result

# ══════════════════════════════════════════════════════════════════════════════
# AUDIT VARIABLE 3: DOM STRUCTURE & SELECTORS
# ══════════════════════════════════════════════════════════════════════════════

def audit_dom_structure():
    section("VAR 3 — DOM STRUCTURE & CSS SELECTORS")
    result = {"status": "unknown", "selectors": [], "details": []}

    r = safe_request(TARGET_URL, headers=HEADERS_BROWSER)
    if not r or r.status_code != 200:
        log("Tidak bisa fetch HTML untuk analisis DOM", RED, "FAIL")
        audit_results["variables"]["dom"] = result
        return result

    html = r.text

    # Cek struktur tabel
    subsection("Analisis struktur HTML...")
    table_count = html.lower().count("<table")
    tr_count    = html.lower().count("<tr")
    td_count    = html.lower().count("<td")
    div_count   = html.lower().count("<div")

    log(f"<table> tags: {table_count}", WHITE)
    log(f"<tr> tags: {tr_count}", WHITE)
    log(f"<td> tags: {td_count}", WHITE)
    log(f"<div> tags: {div_count}", WHITE)
    result["details"].append(f"tables={table_count}, rows={tr_count}")

    # Deteksi selector yang stabil
    subsection("Deteksi CSS selectors yang relevan...")
    selectors_to_check = {
        "table":                        "Generic table",
        "table.drug-list":              "Drug list table class",
        ".drug-item":                   "Drug item class",
        ".drug-row":                    "Drug row class",
        "[data-drug]":                  "Data-drug attribute",
        "[data-registration]":          "Data-registration attribute",
        ".registration-number":         "Registration number class",
        ".drug-name":                   "Drug name class",
        ".manufacturer":                "Manufacturer class",
        "tbody tr":                     "Table body rows",
        ".list-item":                   "List item class",
        ".result-item":                 "Result item class",
        ".card":                        "Card component",
        ".medicine-card":               "Medicine card class",
    }

    # Cek JSON-LD structured data
    jsonld_matches = re.findall(
        r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL
    )
    if jsonld_matches:
        log(f"JSON-LD structured data ditemukan: {len(jsonld_matches)} block(s)", GREEN, "OK")
        for i, jld in enumerate(jsonld_matches):
            try:
                data = json.loads(jld)
                log(f"  Block {i+1}: @type={data.get('@type', 'unknown')}", CYAN)
                result["details"].append(f"jsonld_type={data.get('@type')}")
            except Exception:
                pass
    else:
        log("Tidak ada JSON-LD structured data", YELLOW, "WARN")

    # Deteksi data-* attributes
    data_attrs = re.findall(r'data-[\w-]+="[^"]*"', html)
    if data_attrs:
        unique_attrs = list(set(a.split('=')[0] for a in data_attrs))[:10]
        log(f"data-* attributes ditemukan: {', '.join(unique_attrs)}", GREEN, "OK")
        result["details"].append(f"data_attrs={unique_attrs}")
    else:
        log("Tidak ada data-* attributes yang relevan", YELLOW, "WARN")

    # Cek apakah ada data visible di HTML
    if tr_count > 5:
        result["status"] = "html_has_data"
        result["selectors"] = ["table", "tbody tr", "td"]
        log("Data kemungkinan ada di HTML table — BeautifulSoup bisa digunakan", GREEN, "OK")
    else:
        result["status"] = "data_not_in_html"
        log("Data tidak terlihat di HTML — dikonfirmasi CSR/dynamic loading", YELLOW, "WARN")

    audit_results["variables"]["dom"] = result
    return result

# ══════════════════════════════════════════════════════════════════════════════
# AUDIT VARIABLE 4: ANTI-BOT & SECURITY
# ══════════════════════════════════════════════════════════════════════════════

def audit_antibot():
    section("VAR 4 — ANTI-BOT & SECURITY DETECTION")
    result = {"waf": None, "rate_limit": False, "bot_block": False, "details": []}

    # Test 1: Request dengan UA normal
    subsection("Test 1: Request dengan browser User-Agent...")
    r1 = safe_request(TARGET_URL, headers=HEADERS_BROWSER)
    if r1:
        log(f"Browser UA → Status: {r1.status_code}", GREEN if r1.status_code == 200 else RED,
            "OK" if r1.status_code == 200 else "FAIL")
        result["details"].append(f"browser_ua_status={r1.status_code}")
    else:
        log("Browser UA → Request gagal (timeout/connection error)", RED, "FAIL")

    time.sleep(2)

    # Test 2: Request dengan bot UA
    subsection("Test 2: Request dengan Python/bot User-Agent...")
    r2 = safe_request(TARGET_URL, headers=HEADERS_BOT)
    if r2:
        log(f"Bot UA → Status: {r2.status_code}", GREEN if r2.status_code == 200 else RED,
            "OK" if r2.status_code == 200 else "FAIL")
        result["details"].append(f"bot_ua_status={r2.status_code}")
        if r2.status_code in (403, 429, 503, 406):
            result["bot_block"] = True
            log("Bot User-Agent DIBLOK — WAF aktif", RED, "FAIL")
        elif r1 and r2.status_code == r1.status_code:
            log("Bot UA dan Browser UA mendapat response sama — kemungkinan tidak ada UA filtering",
                GREEN, "OK")
    else:
        result["bot_block"] = True
        log("Bot UA → Request gagal — server menolak non-browser", RED, "FAIL")

    # Test 3: Deteksi WAF dari headers
    subsection("Test 3: Analisis security headers...")
    if r1:
        security_headers = {
            "Server":              r1.headers.get("Server", ""),
            "X-Powered-By":       r1.headers.get("X-Powered-By", ""),
            "CF-Ray":             r1.headers.get("CF-Ray", ""),
            "X-Akamai-Session":   r1.headers.get("X-Akamai-Session-Incoming", ""),
            "X-Cache":            r1.headers.get("X-Cache", ""),
            "Via":                r1.headers.get("Via", ""),
            "Strict-Transport":   r1.headers.get("Strict-Transport-Security", ""),
            "X-Frame-Options":    r1.headers.get("X-Frame-Options", ""),
            "Content-Security":   r1.headers.get("Content-Security-Policy", "")[:80] if r1.headers.get("Content-Security-Policy") else "",
        }

        waf_detected = []
        all_headers_str = " ".join(r1.headers.values()).lower()

        if "cloudflare" in all_headers_str or r1.headers.get("CF-Ray"):
            waf_detected.append("Cloudflare")
        if "akamai" in all_headers_str or r1.headers.get("X-Akamai-Session-Incoming"):
            waf_detected.append("Akamai")
        if "incapsula" in all_headers_str:
            waf_detected.append("Imperva Incapsula")
        if "datadome" in all_headers_str:
            waf_detected.append("DataDome")
        if "sucuri" in all_headers_str:
            waf_detected.append("Sucuri")
        if "f5" in all_headers_str or "big-ip" in all_headers_str:
            waf_detected.append("F5 BIG-IP")

        for h, v in security_headers.items():
            if v:
                log(f"{h}: {v}", WHITE)

        if waf_detected:
            result["waf"] = waf_detected
            log(f"\n  WAF Terdeteksi: {', '.join(waf_detected)}", RED, "FAIL")
        else:
            result["waf"] = []
            log("Tidak ada WAF terkenal terdeteksi dari headers", GREEN, "OK")

    # Test 4: Rate limiting
    subsection("Test 4: Rate limit test (3 request cepat)...")
    statuses = []
    for i in range(3):
        r = safe_request(TARGET_URL, headers=HEADERS_BROWSER)
        status = r.status_code if r else 0
        statuses.append(status)
        log(f"Request {i+1}: {status}", GREEN if status == 200 else RED)
        time.sleep(0.5)

    if 429 in statuses:
        result["rate_limit"] = True
        log("Rate limiting AKTIF — perlu delay antar request", RED, "FAIL")
    else:
        log("Tidak ada rate limiting terdeteksi pada 3 request cepat", GREEN, "OK")

    # Deteksi honeypot/trap links
    subsection("Test 5: Honeypot detection...")
    if r1 and r1.status_code == 200:
        hidden_links = re.findall(
            r'<a[^>]+style="[^"]*(?:display:\s*none|visibility:\s*hidden)[^"]*"[^>]*href="([^"]+)"',
            r1.text, re.IGNORECASE
        )
        if hidden_links:
            log(f"PERINGATAN: {len(hidden_links)} hidden link ditemukan — potensi honeypot!", RED, "FAIL")
            result["details"].append(f"honeypot_links={hidden_links[:3]}")
        else:
            log("Tidak ada honeypot links terdeteksi", GREEN, "OK")

    audit_results["variables"]["antibot"] = result
    return result

# ══════════════════════════════════════════════════════════════════════════════
# AUDIT VARIABLE 5: HIDDEN API DISCOVERY
# ══════════════════════════════════════════════════════════════════════════════

def audit_hidden_api():
    section("VAR 5 — HIDDEN API DISCOVERY (Critical)")
    result = {"found": False, "endpoint": None, "pagination": None, "sample": None}

    subsection(f"Testing {len(API_CANDIDATES)} kandidat API endpoints...")
    found_apis = []

    session = requests.Session()
    session.headers.update(HEADERS_API)

    for candidate in API_CANDIDATES:
        full_url = BASE_URL + candidate
        log(f"Testing: {full_url}", DIM)

        # Test GET tanpa parameter
        r = safe_request(full_url, headers=HEADERS_API, timeout=8)
        if r and r.status_code == 200 and is_json_response(r):
            try:
                data = r.json()
                if contains_drug_data(data):
                    log(f"  API DITEMUKAN: {full_url}", GREEN, "OK")
                    found_apis.append({"url": full_url, "method": "GET", "data": data})
                    result["found"] = True
                    result["endpoint"] = full_url
                    result["sample"] = data
                    continue
                else:
                    log(f"  JSON tapi bukan drug data: {full_url}", YELLOW, "WARN")
            except Exception:
                pass

        # Test GET dengan page param
        if r and r.status_code in (400, 422):
            # Mungkin butuh parameter
            for pag in ["?page=1&size=10", "?pageNumber=1&pageSize=10", "?start=0&limit=10"]:
                r2 = safe_request(full_url + pag, headers=HEADERS_API, timeout=8)
                if r2 and r2.status_code == 200 and is_json_response(r2):
                    try:
                        data = r2.json()
                        if contains_drug_data(data):
                            log(f"  API DITEMUKAN (dengan params): {full_url + pag}", GREEN, "OK")
                            found_apis.append({"url": full_url + pag, "method": "GET", "data": data})
                            result["found"] = True
                            result["endpoint"] = full_url + pag
                            result["sample"] = data
                            break
                    except Exception:
                        pass

        time.sleep(0.3)

    # Test POST endpoints
    subsection("Testing POST endpoints...")
    post_candidates = [
        "/api/drugs/search",
        "/api/drug/list",
        "/api/v1/drugs/search",
        "/api/portal/drugs",
    ]
    post_bodies = [
        {"pageIndex": 1, "pageSize": 20},
        {"page": 1, "size": 20},
        {"start": 0, "limit": 20},
        {"pageNumber": 1, "pageSize": 20, "keyword": ""},
    ]

    for candidate in post_candidates:
        full_url = BASE_URL + candidate
        for body in post_bodies:
            r = safe_request(full_url, headers=HEADERS_API, method="POST", data=body, timeout=8)
            if r and r.status_code == 200 and is_json_response(r):
                try:
                    data = r.json()
                    if contains_drug_data(data):
                        log(f"  POST API DITEMUKAN: {full_url}", GREEN, "OK")
                        found_apis.append({"url": full_url, "method": "POST", "body": body, "data": data})
                        result["found"] = True
                        result["endpoint"] = full_url
                        result["sample"] = data
                        break
                except Exception:
                    pass
            time.sleep(0.3)

    if found_apis:
        # Simpan hasil ke file
        with open(API_JSON_OUT, "w", encoding="utf-8") as f:
            json.dump(found_apis, f, ensure_ascii=False, indent=2)
        log(f"\n  API response disimpan ke: {API_JSON_OUT}", GREEN, "OK")
        log(f"  Total API endpoints ditemukan: {len(found_apis)}", GREEN)

        # Test pagination pada API pertama
        if found_apis[0].get("method") == "GET":
            subsection("Test pagination pada API yang ditemukan...")
            base_api = found_apis[0]["url"].split("?")[0]
            for pag in ["?page=1", "?page=2"]:
                rp = safe_request(base_api + pag + "&size=5", headers=HEADERS_API)
                if rp and rp.status_code == 200:
                    log(f"  Pagination {pag} → {rp.status_code}", GREEN, "OK")
                time.sleep(1)
    else:
        log("\n  Tidak ada hidden API ditemukan secara otomatis", YELLOW, "WARN")
        log("  → AKSI MANUAL DIPERLUKAN: Buka DevTools → Network → XHR saat browse halaman", YELLOW)
        log("  → Cari request yang return JSON dengan struktur obat", YELLOW)

    audit_results["variables"]["hidden_api"] = result
    audit_results["api_found"] = result["endpoint"]
    return result

# ══════════════════════════════════════════════════════════════════════════════
# AUDIT VARIABLE 6: SESSION & AUTHENTICATION
# ══════════════════════════════════════════════════════════════════════════════

def audit_session():
    section("VAR 6 — AUTHENTICATION & SESSION MANAGEMENT")
    result = {"auth_required": False, "cookies": [], "csrf": False, "details": []}

    subsection("Analisis cookies dan session...")
    r = safe_request(TARGET_URL, headers=HEADERS_BROWSER)
    if not r:
        audit_results["variables"]["session"] = result
        return result

    # Analisis cookies
    if r.cookies:
        for cookie in r.cookies:
            log(f"Cookie: {cookie.name} = {cookie.value[:30]}...", WHITE)
            result["cookies"].append({
                "name":     cookie.name,
                "secure":   cookie.secure,
                "httponly": cookie.has_nonstandard_attr("HttpOnly"),
            })

        # Cek CSRF token
        csrf_cookies = [c for c in r.cookies if "csrf" in c.name.lower() or "xsrf" in c.name.lower()]
        if csrf_cookies:
            result["csrf"] = True
            log(f"CSRF token ditemukan di cookies: {[c.name for c in csrf_cookies]}", YELLOW, "WARN")
            log("  → Perlu extract dan kirim CSRF token di setiap request", YELLOW)
        else:
            log("Tidak ada CSRF cookie terdeteksi", GREEN, "OK")
    else:
        log("Tidak ada cookies dari initial request", GREEN, "OK")

    # Cek apakah ada login wall
    subsection("Cek login requirement...")
    login_signals = ["login", "signin", "authenticate", "unauthorized", "forbidden",
                     "please log in", "you must be logged in"]
    if r.status_code == 200:
        page_lower = r.text.lower()
        is_login_wall = any(s in page_lower for s in login_signals)
        if is_login_wall:
            result["auth_required"] = True
            log("Login wall terdeteksi — scraping memerlukan autentikasi", RED, "FAIL")
        else:
            log("Tidak ada login wall — data publik dapat diakses tanpa login", GREEN, "OK")
    elif r.status_code in (401, 403):
        result["auth_required"] = True
        log(f"HTTP {r.status_code} — Akses memerlukan autentikasi", RED, "FAIL")

    # Cek CSRF di form HTML
    csrf_inputs = re.findall(
        r'<input[^>]+name="[^"]*(?:csrf|token|_token)[^"]*"[^>]*value="([^"]*)"',
        r.text, re.IGNORECASE
    )
    if csrf_inputs:
        result["csrf"] = True
        log(f"CSRF form token ditemukan: {csrf_inputs[0][:20]}...", YELLOW, "WARN")

    audit_results["variables"]["session"] = result
    return result

# ══════════════════════════════════════════════════════════════════════════════
# AUDIT VARIABLE 7: SCALE & VOLUME ESTIMATION
# ══════════════════════════════════════════════════════════════════════════════

def audit_scale():
    section("VAR 7 — SCALE, VOLUME & TIME ESTIMATION")
    result = {"estimated_records": None, "pages": None, "time_hours": None, "strategy": None}

    subsection("Estimasi volume data dari berbagai sumber...")

    # Cek dari robots.txt
    robots_url = BASE_URL + "/robots.txt"
    r = safe_request(robots_url, headers=HEADERS_BROWSER)
    if r and r.status_code == 200:
        log("robots.txt ditemukan:", CYAN, "OK")
        for line in r.text.split("\n")[:15]:
            if line.strip():
                log(f"  {line.strip()}", WHITE)
        # Cek apakah drugs-list di-disallow
        if "/en/drugs-list" in r.text and "Disallow" in r.text:
            log("PERHATIAN: /en/drugs-list mungkin di-Disallow di robots.txt", YELLOW, "WARN")
        result["robots_txt"] = True
    else:
        log("robots.txt tidak accessible", YELLOW, "WARN")

    # Estimasi berdasarkan konteks
    subsection("Estimasi records...")
    estimates = {
        "Min (conservative)": 10_000,
        "Mid (most likely)":  25_000,
        "Max (all types)":    60_000,
    }

    page_size = 100
    delay_avg = 1.5  # detik

    log("Estimasi berdasarkan data SFDA publik:", WHITE)
    for label, est in estimates.items():
        pages = -(-est // page_size)
        hours = (pages * delay_avg) / 3600
        log(f"  {label}: ~{est:,} records → {pages} pages → {hours:.1f} jam", WHITE)

    result["estimated_records"] = estimates["Mid (most likely)"]
    result["pages"] = -(-estimates["Mid (most likely)"] // page_size)
    result["time_hours"] = (result["pages"] * delay_avg) / 3600

    # Rekomendasi strategi
    subsection("Rekomendasi strategi berdasarkan volume...")
    if estimates["Max (all types)"] < 100_000:
        result["strategy"] = "single_machine_sequential"
        log("Volume < 100K → Single machine sequential scraping (OPTIMAL)", GREEN, "OK")
        log("Tidak perlu Scrapy-Redis atau distributed setup", GREEN)
        log(f"Estimasi waktu selesai: {result['time_hours']:.1f}–{result['time_hours']*2:.1f} jam", GREEN)
    else:
        result["strategy"] = "async_or_distributed"
        log("Volume > 100K → Gunakan asyncio + aiohttp atau Scrapy-Redis", YELLOW, "WARN")

    audit_results["variables"]["scale"] = result
    return result

# ══════════════════════════════════════════════════════════════════════════════
# FINAL RECOMMENDATION
# ══════════════════════════════════════════════════════════════════════════════

def generate_recommendation():
    section("REKOMENDASI STACK & ARSITEKTUR FINAL")

    v = audit_results["variables"]
    rendering  = v.get("rendering",   {})
    antibot    = v.get("antibot",     {})
    hidden_api = v.get("hidden_api",  {})
    session    = v.get("session",     {})
    scale      = v.get("scale",       {})

    waf_found    = bool(antibot.get("waf"))
    api_found    = hidden_api.get("found", False)
    auth_needed  = session.get("auth_required", False)
    csrf_needed  = session.get("csrf", False)
    is_dynamic   = rendering.get("type") in ("CSR/SPA", "Unknown")

    print()

    # Stack decision tree
    if api_found:
        stack = "Python requests + pandas + openpyxl"
        strategy = "Direct API scraping (FASTEST)"
        log(f"PRIMARY STACK: {stack}", GREEN, "OK")
        log(f"STRATEGI: {strategy}", GREEN, "OK")
    elif is_dynamic:
        stack = "Playwright + BeautifulSoup/JSON intercept + pandas + openpyxl"
        strategy = "Headless browser dengan XHR interception"
        log(f"PRIMARY STACK: {stack}", YELLOW, "OK")
        log(f"STRATEGI: {strategy}", YELLOW, "OK")
    else:
        stack = "requests + BeautifulSoup + pandas + openpyxl"
        strategy = "HTML parsing (SSR)"
        log(f"PRIMARY STACK: {stack}", CYAN, "OK")
        log(f"STRATEGI: {strategy}", CYAN, "OK")

    if waf_found:
        log(f"ANTI-BOT: playwright-stealth diperlukan ({', '.join(antibot.get('waf', []))} terdeteksi)", RED, "WARN")
    else:
        log("ANTI-BOT: Header standar cukup + random delay 1-3 detik", GREEN, "OK")

    if csrf_needed:
        log("CSRF: Perlu extract token dari HTML sebelum setiap request", YELLOW, "WARN")

    if auth_needed:
        log("AUTH: Login flow diperlukan — tambahkan session management", RED, "WARN")
    else:
        log("AUTH: Tidak diperlukan — data publik", GREEN, "OK")

    print()
    log("PIPELINE ARSITEKTUR:", WHITE, "HEAD")
    steps = [
        "1. Recon manual 10 menit di DevTools → identifikasi exact API endpoint",
        "2. Test endpoint dengan curl → validasi response JSON",
        "3. Fetch halaman 1 → extract totalCount → hitung total_pages",
        "4. Loop semua halaman dengan delay 1.5s antar request",
        "5. Parse 5 field target per drug record",
        "6. Flag field Arabic, dedup by Registration Number",
        "7. Export ke Excel dengan openpyxl",
    ]
    for step in steps:
        log(f"  {step}", WHITE)

    audit_results["recommendation"] = {
        "stack":    stack,
        "strategy": strategy,
        "waf":      waf_found,
        "csrf":     csrf_needed,
        "auth":     auth_needed,
        "api":      api_found,
    }

# ══════════════════════════════════════════════════════════════════════════════
# SUMMARY TABLE
# ══════════════════════════════════════════════════════════════════════════════

def print_summary():
    section("SUMMARY AUDIT — 7 VARIABEL KRITIS")

    v = audit_results["variables"]
    rows = [
        ("1. Rendering",   v.get("rendering",  {}).get("type",    "?"), v.get("rendering",  {}).get("status",  "?")),
        ("2. Pagination",  v.get("pagination", {}).get("pattern", "?"), v.get("pagination", {}).get("status",  "?")),
        ("3. DOM Structure",v.get("dom",        {}).get("status",  "?"), "-"),
        ("4. Anti-Bot",    str(v.get("antibot", {}).get("waf",    [])), "OK" if not v.get("antibot", {}).get("bot_block") else "BLOCKED"),
        ("5. Hidden API",  v.get("hidden_api", {}).get("endpoint","not found"), "FOUND" if v.get("hidden_api",{}).get("found") else "NOT FOUND"),
        ("6. Auth/Session",str(v.get("session", {}).get("auth_required", False)), "OK" if not v.get("session",{}).get("auth_required") else "REQUIRED"),
        ("7. Scale",       f"~{v.get('scale',{}).get('estimated_records',0):,} records", f"{v.get('scale',{}).get('time_hours',0):.1f}h"),
    ]

    col1, col2, col3 = 22, 32, 14
    header = f"  {'Variable':<{col1}} {'Value':<{col2}} {'Status':<{col3}}"
    sep    = "  " + "-"*(col1+col2+col3+2)
    print(f"\n{WHITE}{header}{RESET}")
    print(f"{WHITE}{sep}{RESET}")
    report_lines.append(f"\n{header}")
    report_lines.append(sep)

    for var, val, status in rows:
        ok_statuses = {"found", "FOUND", "OK", "ok", "dynamic", "False", "not_url_based",
                       "data_not_in_html", "static"}
        if any(s in str(status).upper() for s in ["OK", "FOUND", "FALSE"]):
            color = GREEN
        elif any(s in str(status).upper() for s in ["FAIL", "BLOCKED", "REQUIRED", "NOT FOUND"]):
            color = RED
        else:
            color = YELLOW

        line = f"  {var:<{col1}} {str(val)[:col2-1]:<{col2}} {status:<{col3}}"
        print(f"{color}{line}{RESET}")
        report_lines.append(line)

# ══════════════════════════════════════════════════════════════════════════════
# SAVE REPORT
# ══════════════════════════════════════════════════════════════════════════════

def save_report():
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        f.write(f"SFDA DRUGS LIST — TECHNICAL AUDIT REPORT\n")
        f.write(f"Generated: {audit_results['timestamp']}\n")
        f.write(f"Target:    {audit_results['target']}\n")
        f.write("=" * 60 + "\n\n")
        f.write("\n".join(report_lines))
        f.write("\n\nFULL AUDIT JSON:\n")
        # Remove sample data yang besar sebelum dump
        clean_results = {k: v for k, v in audit_results.items() if k != "sample_data"}
        f.write(json.dumps(clean_results, ensure_ascii=False, indent=2, default=str))

    log(f"\n  Laporan disimpan ke: {REPORT_FILE}", GREEN, "OK")

# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    print(f"\n{CYAN}{'█'*60}{RESET}")
    print(f"{CYAN}  SFDA DRUGS LIST — TECHNICAL AUDIT SCRIPT{RESET}")
    print(f"{CYAN}  Target: {TARGET_URL}{RESET}")
    print(f"{CYAN}  Waktu: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{RESET}")
    print(f"{CYAN}{'█'*60}{RESET}")
    print(f"\n{DIM}  Audit ini akan test 7 variabel kritis dan merekomendasikan")
    print(f"  stack teknologi optimal untuk project scraping ini.{RESET}\n")

    report_lines.append("SFDA DRUGS LIST — TECHNICAL AUDIT REPORT")
    report_lines.append(f"Generated: {audit_results['timestamp']}")
    report_lines.append(f"Target: {audit_results['target']}")
    report_lines.append("=" * 60)

    try:
        audit_rendering()
        time.sleep(1)

        audit_pagination()
        time.sleep(1)

        audit_dom_structure()
        time.sleep(1)

        audit_antibot()
        time.sleep(1)

        audit_hidden_api()
        time.sleep(1)

        audit_session()
        time.sleep(1)

        audit_scale()
        time.sleep(1)

        generate_recommendation()
        print_summary()

        section("OUTPUT FILES")
        log(f"Laporan teks: {REPORT_FILE}", WHITE)
        if audit_results.get("api_found"):
            log(f"API response JSON: {API_JSON_OUT}", WHITE)

        save_report()

        print(f"\n{GREEN}{'═'*60}{RESET}")
        print(f"{GREEN}  AUDIT SELESAI{RESET}")
        print(f"{GREEN}{'═'*60}{RESET}\n")

    except KeyboardInterrupt:
        print(f"\n{YELLOW}  Audit dihentikan oleh user{RESET}")
        save_report()
        sys.exit(0)
    except Exception as e:
        log(f"Error tidak terduga: {e}", RED, "FAIL")
        import traceback
        traceback.print_exc()
        save_report()
        sys.exit(1)

if __name__ == "__main__":
    main()
