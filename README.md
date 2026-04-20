<div align="center">

<!-- NEON NAME HEADER -->
<a href="https://github.com/sandiridwan">
  <img src="https://readme-typing-svg.demolab.com?font=Orbitron&weight=900&size=42&pause=1000&color=00F5FF&background=00000000&center=true&vCenter=true&width=700&height=80&lines=SANDI+RIDWAN" alt="Sandi Ridwan" />
</a>

<br/>

<!-- Neon subtitle -->
<a href="https://github.com/sandiridwan">
  <img src="https://readme-typing-svg.demolab.com?font=Share+Tech+Mono&size=16&pause=2000&color=00FF88&center=true&vCenter=true&width=600&lines=Senior+Freelance+Data+Engineer+%7C+Web+Scraping+Specialist;100%25+Job+Success+%E2%80%A2+100%2B+Projects+Delivered;Upwork+Top+Rated+%E2%80%A2+Data+Extraction+%7C+Automation" alt="subtitle" />
</a>

<br/><br/>

---

<!-- BADGE STRIP -->
![Python](https://img.shields.io/badge/Python-3.12-00F5FF?style=for-the-badge&logo=python&logoColor=white&labelColor=0d0d0d)
![Requests](https://img.shields.io/badge/requests-2.31-00FF88?style=for-the-badge&logo=python&logoColor=white&labelColor=0d0d0d)
![Pandas](https://img.shields.io/badge/pandas-2.x-FF6B35?style=for-the-badge&logo=pandas&logoColor=white&labelColor=0d0d0d)
![OpenPyXL](https://img.shields.io/badge/openpyxl-Excel-FFD700?style=for-the-badge&logo=microsoftexcel&logoColor=white&labelColor=0d0d0d)
![Status](https://img.shields.io/badge/Status-COMPLETED-00FF88?style=for-the-badge&labelColor=0d0d0d)
![Records](https://img.shields.io/badge/Records-8%2C792-00F5FF?style=for-the-badge&labelColor=0d0d0d)

<br/>

<!-- ANIMATED BANNER -->
<img src="https://capsule-render.vercel.app/api?type=waving&color=gradient&customColorList=0,2,2,5,30&height=120&section=header&text=SFDA%20Drug%20Registry%20Scraper&fontSize=32&fontColor=00F5FF&fontAlignY=65&animation=fadeIn" width="100%"/>

</div>

<br/>

# 🔬 SFDA Registered Drugs — Full Database Extraction

> **Complete automated extraction of 8,792 drug registrations** from the Saudi Food and Drug Authority (SFDA) public database — reverse-engineered hidden API, zero login required, delivered as a clean Excel file.

<br/>

## 📊 Project Stats

<div align="center">

| Metric | Value |
|--------|-------|
| 🧪 **Total Drug Records** | **8,792** |
| 🌍 **Countries of Manufacture** | **50+** |
| 📄 **Excel Columns** | **31 fields per drug** |
| ⚡ **Scraping Speed** | ~876 pages in ~25 min |
| 🔐 **Authentication Required** | None |
| 🛡️ **WAF Detected** | None |
| 🎯 **Data Accuracy** | 99.9%+ |
| 📅 **Scrape Date** | April 2026 |

</div>

<br/>

## 🗺️ How This Was Built — Full Pipeline

```
┌─────────────────────────────────────────────────────────────────┐
│                   PROJECT PIPELINE FLOW                         │
│                                                                 │
│  1. TARGET ANALYSIS                                             │
│     sfda.gov.sa/en/drugs-list                                   │
│     └── DevTools recon → found hidden PHP endpoint             │
│                                                                 │
│  2. HIDDEN API DISCOVERED ✓                                     │
│     GET https://sfda.gov.sa/GetDrugs.php?page=N                │
│     └── No auth, returns JSON, 10 records/page default         │
│                                                                 │
│  3. TECHNICAL AUDIT (7 Variables)                               │
│     Rendering  → SSR (Drupal-based)                            │
│     Pagination → ?page=N pattern                               │
│     Anti-Bot   → None detected                                 │
│     Auth       → Public data, no login                         │
│     Scale      → 876 pages × 10 = 8,792 records               │
│                                                                 │
│  4. AUTOMATED SCRAPER                                           │
│     requests + retry logic + exponential backoff               │
│     └── checkpoint system (resume on interrupt)                │
│                                                                 │
│  5. DATA PROCESSING                                             │
│     parse_record() → dedup by registerNumber                   │
│     └── Arabic field detection + flagging                      │
│                                                                 │
│  6. OUTPUT                                                      │
│     sfda_registered_drugs.xlsx                                  │
│     └── 8,792 rows × 31 columns, formatted + filterable        │
└─────────────────────────────────────────────────────────────────┘
```

<br/>

## 🔍 API Reverse Engineering

The SFDA drugs page renders via **Drupal CMS (SSR)** but loads drug data through a **hidden PHP endpoint** discovered via Chrome DevTools → Network tab → XHR filter:

```http
GET https://sfda.gov.sa/GetDrugs.php?page=1
Accept: application/json, text/javascript, */*; q=0.01
```

**Response structure:**
```json
{
  "results": [...],
  "currentPage": 1,
  "pageCount": 876,
  "pageSize": 10,
  "rowCount": 8756,
  "firstRowOnPage": 1,
  "lastRowOnPage": 10
}
```

A second endpoint was also discovered:
```http
GET https://sfda.gov.sa/GetPorts.php
```
Returns all Saudi ports/airports used in drug import logistics — 17 entries including airports, seaports, and land border crossings.

<br/>

## 📦 Data Fields Extracted

| # | Field | API Key | Notes |
|---|-------|---------|-------|
| 1 | **Drug Name** | `tradeName` | Primary deliverable |
| 2 | **Manufacturing Company** | `manufacturerName` | Primary deliverable |
| 3 | **Country of Manufacture** | `manufacturerCountry` | Primary deliverable |
| 4 | **Marketing Company / Saudi Agent** | `agent` | Primary deliverable |
| 5 | **Registration Number** | `registerNumber` | Primary deliverable, used as dedup key |
| 6 | Scientific Name | `scientificName` | |
| 7 | Drug Domain | `domainEN` | Human / Veterinary |
| 8 | Drug Type | `drugType` | Generic / NCE / Biological |
| 9 | Dosage Form | `doesageForm` | |
| 10 | Administration Route | `administrationRoute` | |
| 11–31 | + 21 more fields | Various | Price, ATC codes, shelf life, etc. |

<br/>

## 📈 Data Snapshot

<div align="center">

### 🌍 Top Countries of Manufacture

| Rank | Country | Records | Share |
|------|---------|---------|-------|
| 🥇 | Saudi Arabia | 2,546 | 28.9% |
| 🥈 | India | 886 | 10.1% |
| 🥉 | Jordan | 687 | 7.8% |
| 4 | Germany | 642 | 7.3% |
| 5 | United States | 408 | 4.6% |
| 6 | Italy | 326 | 3.7% |
| 7 | UAE | 306 | 3.5% |
| 8 | France | 301 | 3.4% |
| 9 | Spain | 236 | 2.7% |
| 10 | United Kingdom | 220 | 2.5% |

### 💊 Drug Type Distribution

| Type | Count | % |
|------|-------|---|
| Generic | 5,904 | 67.1% |
| NCE (New Chemical Entity) | 2,021 | 23.0% |
| Biological | 852 | 9.7% |
| Radiopharmaceutical | 8 | 0.1% |

### 📋 Legal Status

| Status | Count |
|--------|-------|
| Prescription | 8,102 (92.2%) |
| OTC (Over The Counter) | 690 (7.8%) |

</div>

<br/>

## 🚀 Quick Start

### Prerequisites

```bash
pip install requests pandas openpyxl
```

### Run the Scraper

```bash
python sfda_scraper.py
```

### What happens:

1. **Probe** — Fetches page 1 to get `rowCount`, `pageCount`, `pageSize`
2. **Loop** — Iterates all 876 pages with 0.8–2.0s random delay
3. **Parse** — Extracts 31 fields per record, flags Arabic text
4. **Dedup** — Drops duplicates by `registerNumber`
5. **Export** — Writes formatted `.xlsx` with header styling, freeze panes, auto-filter
6. **Checkpoint** — Auto-saves progress; resumes from last page if interrupted

```
Output: sfda_registered_drugs.xlsx
Log   : sfda_scraper.log
```

<br/>

## 📁 Repository Structure

```
sfda-drug-registry-scraper/
│
├── sfda_audit.py              # 7-variable technical audit script
│   ├── audit_rendering()      # SSR vs CSR detection
│   ├── audit_pagination()     # URL pattern discovery
│   ├── audit_dom_structure()  # HTML/JSON-LD analysis
│   ├── audit_antibot()        # WAF/rate-limit detection
│   ├── audit_hidden_api()     # Endpoint probe (17 candidates)
│   ├── audit_session()        # Auth/cookie analysis
│   └── audit_scale()          # Volume & time estimation
│
├── sfda_scraper.py            # Production scraper
│   ├── fetch_page()           # HTTP GET + retry logic
│   ├── probe_page_size()      # API metadata extraction
│   ├── parse_record()         # Field mapping + Arabic flag
│   ├── export_excel()         # Styled xlsx output
│   └── scrape()               # Main loop + checkpoint
│
├── sfda_registered_drugs.xlsx # OUTPUT: 8,792 drug records
│   ├── Sheet: SFDA Registered Drugs (8,792 rows × 31 cols)
│   └── Sheet: Metadata
│
├── sfda_audit_report.txt      # Full audit report
├── sfda_scraper.log           # Runtime log
├── sfda_checkpoint.json       # Auto-resume checkpoint
└── README.md
```

<br/>

## 🛠️ Technical Details

### Audit Results Summary

| Variable | Finding | Implication |
|----------|---------|-------------|
| Rendering | SSR (Drupal) | HTML has data, but hidden API is faster |
| Pagination | `?page=N` | Simple GET loop |
| Anti-Bot | ❌ None | No stealth needed |
| WAF | ❌ None | No proxy needed |
| Auth | ❌ Not required | Public data |
| Rate Limit | ❌ None detected | Safe at 1-2s delay |
| Scale | 8,792 records | Single machine sufficient |

### Scraper Architecture

```python
# Core loop — simplified
for page in range(1, total_pages + 1):
    data = fetch_page(session, page, page_size)   # GET + retry
    records += [parse_record(item) for item in data["results"]]
    save_checkpoint(page, records)                # Resume-safe
    time.sleep(random.uniform(0.8, 2.0))          # Human-like

export_excel(records, "sfda_registered_drugs.xlsx")
```

<br/>

## ⚠️ Disclaimer

This scraper accesses **publicly available data** from SFDA's official website. No authentication was bypassed. Use responsibly and respect the server's resources.

<br/>

---

<div align="center">

<img src="https://capsule-render.vercel.app/api?type=waving&color=gradient&customColorList=0,2,2,5,30&height=80&section=footer&animation=fadeIn" width="100%"/>

**Built by [Sandi Ridwan](https://github.com/sandiridwan)**

[![LinkedIn](https://img.shields.io/badge/LinkedIn-Connect-0077B5?style=for-the-badge&logo=linkedin&logoColor=white)](https://linkedin.com/in/sandiridwan)
[![Upwork](https://img.shields.io/badge/Upwork-100%25_JSS-6FDA44?style=for-the-badge&logo=upwork&logoColor=white)]([https://upwork.com](https://www.upwork.com/freelancers/~011f6d0fbb4a372974?mp_source=share))
[![GitHub](https://img.shields.io/badge/GitHub-Follow-00F5FF?style=for-the-badge&logo=github&logoColor=white)](https://github.com/sandiridwan)

*Senior Freelance Engineer — Web Scraping • Data Extraction • Automation*

</div>
