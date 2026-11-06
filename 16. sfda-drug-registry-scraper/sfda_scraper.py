"""
╔══════════════════════════════════════════════════════════════════════╗
║   SFDA REGISTERED DRUGS SCRAPER — PRODUCTION READY                 ║
║   API: SFDA drugs-list page + Drupal details AJAX endpoint          ║
║                                                                      ║
║   Verified dari audit:                                               ║
║     • Total records : 8,756                                          ║
║     • Total pages   : 876 (pageSize=10)                             ║
║     • Method        : GET                                            ║
║     • Auth required : Tidak                                          ║
║     • WAF           : Tidak terdeteksi                               ║
║                                                                      ║
║   Output: sfda_registered_drugs.xlsx                                ║
║   Usage : python sfda_scraper.py                                    ║
╚══════════════════════════════════════════════════════════════════════╝
"""

import requests
import pandas as pd
import time
import random
import json
import sys
import logging
import re
from html.parser import HTMLParser
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

# ── LOGGING ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("sfda_scraper.log", encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)

# ── KONFIGURASI ───────────────────────────────────────────────────────────────

BASE_URL    = "https://www.sfda.gov.sa"
LIST_URL    = f"{BASE_URL}/en/drugs-list"
DETAIL_PATH = "/en/details_data"
OUTPUT_FILE = "sfda_registered_drugs.xlsx"
CHECKPOINT  = "sfda_checkpoint.jsonl"

# Delay antar request (detik)
DELAY_MIN = 0.8
DELAY_MAX = 2.0

# Retry config
MAX_RETRIES   = 5
BACKOFF_BASE  = 3   # detik, dikali 2^attempt saat retry

# Header untuk halaman daftar; sesi yang sama juga dipakai untuk request AJAX.
HEADERS = {
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Referer":         LIST_URL,
    "Connection":      "keep-alive",
    "DNT":             "1",
}

# Kolom output yang diurutkan (5 utama di depan)
COLUMN_ORDER = [
    "Drug Name",
    "Manufacturing Company",
    "Country of Manufacture",
    "Marketing Company / Saudi Agent",
    "Registration Number",
    "Scientific Name",
    "Drug Domain",
    "Drug Type",
    "Dosage Form",
    "Administration Route",
    "Strength",
    "Strength Unit",
    "Package Type",
    "Package Size",
    "Volume / Size",
    "Size Unit",
    "Price (SAR)",
    "Marketing Status",
    "Authorization Status",
    "Legal Status",
    "Product Control",
    "Distribution Area",
    "Storage Conditions",
    "Shelf Life (months)",
    "Registration Year",
    "ATC Code 1",
    "ATC Code 2",
    "Company Name",
    "Company Country",
    "Additional Manufacturer",
    "Additional Manufacturer Country",
]

# ══════════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════════

class DrugListParser(HTMLParser):
    """Extract list rows, detail links, and pager indices from the SFDA page."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows = []
        self.page_indices = []
        self._table_depth = 0
        self._in_list_table = False
        self._row = None
        self._cell_parts = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "table" and not self._in_list_table:
            classes = attrs.get("class", "").split()
            if "responsive-enabled" in classes:
                self._in_list_table = True
                self._table_depth = 1
        elif tag == "table" and self._in_list_table:
            self._table_depth += 1

        if tag == "a":
            href = attrs.get("href", "")
            page_value = parse_qs(urlsplit(href).query).get("page", [])
            if page_value and page_value[0].isdigit():
                self.page_indices.append(int(page_value[0]))
            if self._row is not None and href.startswith(DETAIL_PATH):
                self._row["detail_href"] = href

        if self._in_list_table and tag == "tr":
            self._row = {"cells": [], "detail_href": ""}
        elif self._row is not None and tag in ("th", "td"):
            self._cell_parts = []
        elif self._cell_parts is not None and tag == "br":
            self._cell_parts.append("\n")

    def handle_data(self, data):
        if self._cell_parts is not None:
            self._cell_parts.append(data)

    def handle_endtag(self, tag):
        if self._row is not None and tag in ("th", "td") and self._cell_parts is not None:
            value = " ".join("".join(self._cell_parts).split())
            self._row["cells"].append(value)
            self._cell_parts = None
        elif self._in_list_table and tag == "tr" and self._row is not None:
            if self._row["cells"]:
                self.rows.append(self._row)
            self._row = None
            self._cell_parts = None
        elif tag == "table" and self._in_list_table:
            self._table_depth -= 1
            if self._table_depth == 0:
                self._in_list_table = False


class DetailTableParser(HTMLParser):
    """Parse label/value rows from the HTML embedded in Drupal's AJAX response."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.fields = {}
        self._in_row = False
        self._cell_tag = None
        self._cell_parts = []
        self._cells = []

    def handle_starttag(self, tag, _attrs):
        if tag == "tr":
            self._in_row = True
            self._cells = []
        elif self._in_row and tag in ("th", "td"):
            self._cell_tag = tag
            self._cell_parts = []
        elif self._cell_tag == "td" and tag == "br":
            self._cell_parts.append("\n")

    def handle_data(self, data):
        if self._cell_tag is not None:
            self._cell_parts.append(data)

    def handle_endtag(self, tag):
        if self._cell_tag == tag and tag in ("th", "td"):
            value = "".join(self._cell_parts).strip()
            self._cells.append(value)
            self._cell_tag = None
        elif tag == "tr" and self._in_row:
            if len(self._cells) >= 2:
                label = " ".join(self._cells[0].split())
                if label:
                    self.fields[label] = self._cells[1].strip()
            self._in_row = False


def request_with_retry(session: requests.Session, method: str, url: str, **kwargs):
    """Run a request with retries for transient network, rate-limit, and server errors."""
    for attempt in range(MAX_RETRIES):
        try:
            response = session.request(method, url, timeout=30, **kwargs)
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
            if attempt == MAX_RETRIES - 1:
                raise RuntimeError(f"{method} {url} failed after {MAX_RETRIES} attempts: {exc}") from exc
            wait = BACKOFF_BASE * (2 ** attempt)
            log.warning(f"Network error: {exc}. Retry {attempt + 1}/{MAX_RETRIES} in {wait}s...")
            time.sleep(wait)
            continue

        if response.status_code == 200:
            return response
        if response.status_code == 429 or response.status_code in (500, 502, 503, 504):
            if attempt == MAX_RETRIES - 1:
                break
            wait = BACKOFF_BASE * (2 ** attempt)
            log.warning(
                f"HTTP {response.status_code}. Retry {attempt + 1}/{MAX_RETRIES} in {wait}s..."
            )
            time.sleep(wait)
            continue

        raise RuntimeError(f"{method} {url} returned HTTP {response.status_code}")

    raise RuntimeError(f"{method} {url} failed after {MAX_RETRIES} attempts")


def parse_drug_list(html: str, current_page: int) -> tuple[list[dict], int, str]:
    """Parse the list page and return its rows, total page count, and Drupal AJAX library state."""
    parser = DrugListParser()
    parser.feed(html)

    settings_match = re.search(
        r'<script[^>]+data-drupal-selector="drupal-settings-json"[^>]*>(.*?)</script>',
        html,
        re.DOTALL,
    )
    if not settings_match:
        raise ValueError("The SFDA page did not include Drupal AJAX settings.")
    settings = json.loads(settings_match.group(1))
    libraries = settings.get("ajaxPageState", {}).get("libraries")
    if not libraries:
        raise ValueError("The SFDA page did not include Drupal AJAX library state.")

    data_rows = [
        row for row in parser.rows
        if len(row["cells"]) >= 5 and row["detail_href"]
    ]
    if not data_rows and not (
        current_page > 0 and re.search(r"\bNo Results Found\b", html, re.IGNORECASE)
    ):
        raise ValueError(
            f"Page {current_page} did not contain the expected drugs table "
            "or an explicit empty-results message."
        )

    records = []
    for row in data_rows:
        cells = row["cells"]
        detail_query = parse_qs(urlsplit(row["detail_href"]).query)
        registration_number = detail_query.get("id", [""])[0]
        records.append({
            "Scientific Name": cells[0],
            "Drug Name": cells[1],
            "Strength": cells[2],
            "Dosage Form": cells[3],
            "Price (SAR)": cells[4],
            "Registration Number": registration_number,
            "detail_href": row["detail_href"],
        })

    last_page_index = max(parser.page_indices, default=current_page)
    return records, last_page_index + 1, libraries


def fetch_list_page(session: requests.Session, page: int) -> str:
    response = request_with_retry(
        session,
        "GET",
        LIST_URL,
        params={"page": page},
        headers={"Accept": HEADERS["Accept"]},
    )
    return response.text


def fetch_drug_detail(
    session: requests.Session,
    detail_href: str,
    page: int,
    ajax_libraries: str,
) -> dict:
    """Call the same Drupal AJAX detail route used by the SFDA page's Details links."""
    parts = urlsplit(urljoin(BASE_URL, detail_href))
    query = parse_qsl(parts.query, keep_blank_values=True)
    query.append(("_wrapper_format", "drupal_bootstrap4_modal"))
    detail_url = urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
    )
    payload = {
        "js": "true",
        "dialogOptions[dialogClasses]": "modal-lg",
        "_drupal_ajax": "1",
        "ajax_page_state[theme]": "sfda_main",
        "ajax_page_state[theme_token]": "",
        "ajax_page_state[libraries]": ajax_libraries,
    }
    response = request_with_retry(
        session,
        "POST",
        detail_url,
        data=payload,
        headers={
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Referer": f"{LIST_URL}?page={page}",
            "X-Requested-With": "XMLHttpRequest",
        },
    )

    try:
        commands = response.json()
    except requests.exceptions.JSONDecodeError as exc:
        raise ValueError(f"Detail response for {detail_href} was not JSON.") from exc

    detail_html = next(
        (
            command.get("data", "")
            for command in commands
            if command.get("command") == "openBootstrap4Dialog"
        ),
        "",
    )
    if not detail_html:
        raise ValueError(f"Detail response for {detail_href} did not contain drug details.")

    parser = DetailTableParser()
    parser.feed(detail_html)
    if not parser.fields:
        raise ValueError(f"Could not parse drug details from {detail_href}.")
    return parser.fields


def parse_record(summary: dict, details: dict) -> dict:
    """Map the current SFDA detail labels into the existing Excel column schema."""
    manufacturer_names = []
    manufacturer_countries = []
    for line in details.get("Manufacturers", "").splitlines():
        match = re.search(r"Name:\s*(.*?)\s*\|\s*Country:\s*(.*)", line)
        if match:
            manufacturer_names.append(match.group(1).strip())
            manufacturer_countries.append(match.group(2).strip())

    output = {column: "" for column in COLUMN_ORDER}
    output.update({
        "Drug Name": details.get("Trade Name") or summary["Drug Name"],
        "Manufacturing Company": manufacturer_names[0] if manufacturer_names else "",
        "Country of Manufacture": manufacturer_countries[0] if manufacturer_countries else "",
        "Marketing Company / Saudi Agent": details.get("Agents", ""),
        "Registration Number": details.get("Register Number") or summary["Registration Number"],
        "Scientific Name": details.get("Scientific Name") or summary["Scientific Name"],
        "Dosage Form": details.get("Dosage Form") or summary["Dosage Form"],
        "Administration Route": details.get("Route of Administration", ""),
        "Strength": details.get("Strength") or summary["Strength"],
        "Strength Unit": details.get("Strength Unit", ""),
        "Package Type": details.get("Package Type", ""),
        "Package Size": details.get("Package Size", ""),
        "Volume / Size": details.get("Size", ""),
        "Size Unit": details.get("Size Unit", ""),
        "Price (SAR)": details.get("Price") or summary["Price (SAR)"],
        "Marketing Status": details.get("Marketing Status", ""),
        "Authorization Status": details.get("Authorization Status", ""),
        "Legal Status": details.get("Legal Status", ""),
        "Product Control": details.get("Product Control", ""),
        "Distribution Area": details.get("Distribution Site", ""),
        "Storage Conditions": details.get("Storage Conditions", ""),
        "Shelf Life (months)": details.get("Shelf Life", ""),
        "ATC Code 1": details.get("ATC Code 1", ""),
        "ATC Code 2": details.get("ATC Code 2", ""),
        "Company Name": details.get("Marketing Company", ""),
        "Company Country": details.get("Country of marketing company", ""),
        "Additional Manufacturer": "; ".join(manufacturer_names[1:]),
        "Additional Manufacturer Country": "; ".join(manufacturer_countries[1:]),
    })

    for column, value in output.items():
        if isinstance(value, str):
            value = value.strip()
            if detect_arabic(value):
                output[column] = f"[AR_FLAG] {value}"
            else:
                output[column] = value
    return output


def detect_arabic(value) -> bool:
    """True jika string mengandung karakter Arab (Unicode U+0600–U+06FF)."""
    if not isinstance(value, str):
        return False
    return any('\u0600' <= c <= '\u06FF' for c in value)


def append_checkpoint(payload: dict):
    """Append one completed item or page marker for reliable resume."""
    with open(CHECKPOINT, "a", encoding="utf-8") as checkpoint_file:
        checkpoint_file.write(json.dumps(payload, ensure_ascii=False) + "\n")


def load_checkpoint() -> tuple[list[dict], set[tuple[int, str]], set[int]]:
    """Restore scraped rows, completed item keys, and completed list pages."""
    records = []
    completed_items = set()
    completed_pages = set()
    if not Path(CHECKPOINT).exists():
        return records, completed_items, completed_pages

    with open(CHECKPOINT, encoding="utf-8") as checkpoint_file:
        for line_number, line in enumerate(checkpoint_file, start=1):
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                log.warning(f"Ignoring incomplete checkpoint line {line_number}.")
                continue
            if "record" in item:
                page = item["page"]
                registration_number = item["registration_number"]
                records.append(item["record"])
                completed_items.add((page, registration_number))
            elif "page_complete" in item:
                completed_pages.add(item["page_complete"])

    if records or completed_pages:
        log.info(
            f"Checkpoint ditemukan: {len(records):,} records dari "
            f"{len(completed_pages)} halaman selesai."
        )
    return records, completed_items, completed_pages

# ══════════════════════════════════════════════════════════════════════════════
# EXPORT TO EXCEL
# ══════════════════════════════════════════════════════════════════════════════

def export_excel(records: list, filename: str):
    """Export list of dicts ke file Excel yang bersih dan terformat."""
    log.info(f"Exporting {len(records):,} records ke {filename}...")

    df = pd.DataFrame(records)

    # Pastikan kolom urut sesuai COLUMN_ORDER (tambah kolom baru di akhir jika ada)
    existing_ordered = [c for c in COLUMN_ORDER if c in df.columns]
    extra_cols = [c for c in df.columns if c not in COLUMN_ORDER]
    df = df[existing_ordered + extra_cols]

    # Deduplication berdasarkan Registration Number
    before = len(df)
    df = df.drop_duplicates(subset=["Registration Number"], keep="first")
    after  = len(df)
    if before != after:
        log.info(f"Deduplication: {before - after} duplikat dihapus → {after:,} unique records")

    # Drop baris yang 5 field utamanya semua kosong
    key_cols = ["Drug Name", "Manufacturing Company", "Country of Manufacture",
                "Marketing Company / Saudi Agent", "Registration Number"]
    df = df[~(df[key_cols] == "").all(axis=1)]

    with pd.ExcelWriter(filename, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="SFDA Registered Drugs", index=False)

        ws = writer.sheets["SFDA Registered Drugs"]

        # Style header row
        from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
        header_fill   = PatternFill("solid", fgColor="1F4E79")
        header_font   = Font(color="FFFFFF", bold=True, size=10)
        header_align  = Alignment(horizontal="center", vertical="center", wrap_text=True)
        thin_border   = Border(
            bottom=Side(style="thin", color="DDDDDD"),
            right=Side(style="thin", color="DDDDDD"),
        )

        for cell in ws[1]:
            cell.fill      = header_fill
            cell.font      = header_font
            cell.alignment = header_align
            cell.border    = thin_border

        ws.row_dimensions[1].height = 32
        ws.freeze_panes = "A2"   # freeze header row

        # Auto-fit column widths (capped)
        for col_cells in ws.columns:
            max_len = 0
            for cell in col_cells:
                if cell.value:
                    max_len = max(max_len, len(str(cell.value)))
            col_letter = col_cells[0].column_letter
            ws.column_dimensions[col_letter].width = min(max(max_len + 2, 10), 45)

        # Alternate row shading untuk readability
        light_fill = PatternFill("solid", fgColor="EFF3FB")
        for row_idx, row in enumerate(ws.iter_rows(min_row=2, max_row=ws.max_row), start=2):
            if row_idx % 2 == 0:
                for cell in row:
                    cell.fill = light_fill

        # Auto-filter on header
        ws.auto_filter.ref = ws.dimensions

        # Add metadata sheet
        meta_ws = writer.book.create_sheet("Metadata")
        meta_ws["A1"] = "SFDA Registered Drugs — Scrape Metadata"
        meta_ws["A1"].font = Font(bold=True, size=12)
        meta_data = [
            ("Source URL",    f"{LIST_URL} ({DETAIL_PATH} AJAX details)"),
            ("Scrape Date",   datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            ("Total Records", len(df)),
            ("Script",        "sfda_scraper.py"),
            ("Fields Captured", ", ".join(key_cols)),
            ("AR_FLAG Note",  "Fields prefixed [AR_FLAG] contain Arabic text — review manually"),
        ]
        for i, (label, value) in enumerate(meta_data, start=3):
            meta_ws[f"A{i}"] = label
            meta_ws[f"B{i}"] = value
            meta_ws[f"A{i}"].font = Font(bold=True)
        meta_ws.column_dimensions["A"].width = 22
        meta_ws.column_dimensions["B"].width = 60

    log.info(f"✓ Excel tersimpan: {filename} ({df.shape[0]:,} rows × {df.shape[1]} cols)")
    return len(df)

# ══════════════════════════════════════════════════════════════════════════════
# MAIN SCRAPER
# ══════════════════════════════════════════════════════════════════════════════

def scrape() -> list:
    """Fetch list pages and each drug's detail data through the frontend AJAX endpoint."""
    session = requests.Session()
    session.headers.update(HEADERS)

    log.info(f"Checking SFDA list page: {LIST_URL}?page=0")
    first_page_html = fetch_list_page(session, page=0)
    first_page_records, total_pages, ajax_libraries = parse_drug_list(first_page_html, 0)
    log.info(
        f"Frontend confirmed: {total_pages} pages | "
        f"{len(first_page_records)} drugs on the first page"
    )

    all_records, completed_items, completed_pages = load_checkpoint()

    start_time = time.time()
    log.info(f"Starting scrape at page 1/{total_pages}...")
    log.info("Each drug's full details are fetched from the Drupal AJAX endpoint.")
    log.info("-" * 60)

    for page in range(total_pages):
        if page in completed_pages:
            continue

        if page == 0:
            page_records = first_page_records
            page_libraries = ajax_libraries
        else:
            page_html = fetch_list_page(session, page)
            page_records, _, page_libraries = parse_drug_list(page_html, page)

        if not page_records:
            log.warning(f"Page {page + 1}: SFDA explicitly returned no results; continuing.")

        for summary in page_records:
            registration_number = summary["Registration Number"]
            item_key = (page, registration_number)
            if item_key in completed_items:
                continue

            details = fetch_drug_detail(
                session,
                summary["detail_href"],
                page,
                page_libraries,
            )
            record = parse_record(summary, details)
            all_records.append(record)
            completed_items.add(item_key)
            append_checkpoint({
                "page": page,
                "registration_number": registration_number,
                "record": record,
            })
            time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

        append_checkpoint({"page_complete": page})
        completed_pages.add(page)

        if page % 10 == 0 or page == total_pages - 1:
            elapsed = time.time() - start_time
            progress = (page + 1) / total_pages * 100
            log.info(
                f"  Page {page + 1:>4}/{total_pages} | "
                f"{progress:5.1f}% | {len(all_records):>6,} records | "
                f"{elapsed / 60:.1f} min elapsed"
            )

    elapsed_total = time.time() - start_time
    log.info(f"\nScraping completed: {len(all_records):,} records in {elapsed_total/60:.1f} minutes")
    return all_records


# ══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

def main():
    print("=" * 60)
    print("  SFDA DRUGS LIST SCRAPER")
    print(f"  List: {LIST_URL}")
    print(f"  Details: {DETAIL_PATH} (Drupal AJAX POST)")
    print(f"  Target output: {OUTPUT_FILE}")
    print(f"  Waktu mulai: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    try:
        records = scrape()

        if not records:
            log.error("Tidak ada data yang berhasil diextract. Cek log di atas.")
            sys.exit(1)

        final_count = export_excel(records, OUTPUT_FILE)

        # Hapus checkpoint jika berhasil
        if Path(CHECKPOINT).exists():
            Path(CHECKPOINT).unlink()
            log.info("Checkpoint dihapus (scraping berhasil complete).")

        print()
        print("=" * 60)
        print(f"  ✓ SELESAI: {final_count:,} drug registrations")
        print(f"  ✓ File: {OUTPUT_FILE}")
        print(f"  ✓ Log : sfda_scraper.log")
        print("=" * 60)

    except KeyboardInterrupt:
        log.warning("\nDihentikan oleh user (Ctrl+C). Progress tersimpan di checkpoint.")
        sys.exit(0)
    except Exception as e:
        log.exception(f"Fatal error: {e}")
        sys.exit(1)
        sys.exit(1)


if __name__ == "__main__":
    main()
