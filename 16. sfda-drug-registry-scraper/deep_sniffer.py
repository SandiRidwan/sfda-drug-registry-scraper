import asyncio
import json
import os
from urllib.parse import urlparse
from playwright.async_api import async_playwright

# Konfigurasi Folder Output
OUTPUT_DIR = "api_dumps"
os.makedirs(OUTPUT_DIR, exist_ok=True)

def sanitize_filename(url):
    """Mengubah URL menjadi nama file yang aman untuk Windows/Linux"""
    parsed = urlparse(url)
    # Ambil bagian path URL terakhir, buang karakter aneh
    path = parsed.path.replace('/', '_').strip('_')
    if not path:
        path = "root_endpoint"
    return path[:60] # Batasi nama file maksimal 60 karakter

async def human_auto_scroll(page):
    """Simulasi scroll manusia untuk memicu Lazy-Load API"""
    print("   🚶‍♂️ Menjalankan simulasi scroll manusia...")
    for i in range(5):
        # Scroll ke bawah secara acak
        await page.mouse.wheel(0, 1200)
        await asyncio.sleep(1.5) # Jeda natural
    # Scroll kembali ke atas
    await page.mouse.wheel(0, -5000)
    await asyncio.sleep(2)

async def sniff_and_dump(url):
    # Buat folder khusus untuk domain target ini
    domain = urlparse(url).netloc
    domain_dir = os.path.join(OUTPUT_DIR, domain)
    os.makedirs(domain_dir, exist_ok=True)
    
    captured_apis = []

    async with async_playwright() as p:
        # Gunakan mode non-headless agar Anda bisa melihat jika ada Captcha
        browser = await p.chromium.launch(headless=False) 
        context = await browser.new_context(
            viewport={"width": 1366, "height": 768},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        # 🛡️ STEALTH MODE: Hapus jejak "bot" dari navigator browser
        await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        # --- EVENT LISTENER: Penjaga Gerbang API ---
        async def handle_response(response):
            # Hanya tangkap lalu lintas data (XHR/Fetch)
            if response.request.resource_type in ["fetch", "xhr"]:
                # Hanya ambil yang berstatus sukses (200-299) dan berisi JSON
                if response.ok and "application/json" in response.headers.get("content-type", ""):
                    req = response.request
                    
                    try:
                        # 1. Ekstrak Body Response (Hasil Data)
                        body_bytes = await response.body()
                        json_data = json.loads(body_bytes.decode('utf-8'))
                        
                        # 2. Ambil Headers "Kunci Masuk" (Token, Cookie, API Key)
                        vital_headers = {k: v for k, v in req.headers.items() 
                                         if k.lower() in ['authorization', 'x-api-key', 'cookie', 'accept', 'content-type']}
                        
                        # 3. Format Laporan Penangkapan
                        dump_data = {
                            "1_METADATA": {
                                "url": req.url,
                                "method": req.method,
                                "status_code": response.status,
                            },
                            "2_HOW_TO_REPLAY": {
                                "required_headers": vital_headers,
                                "post_payload": json.loads(req.post_data) if req.post_data else None
                            },
                            "3_DATA_EXTRACTED": json_data
                        }
                        
                        # 4. Simpan ke File JSON
                        filename = f"{req.method}_{sanitize_filename(req.url)}.json"
                        filepath = os.path.join(domain_dir, filename)
                        
                        with open(filepath, 'w', encoding='utf-8') as f:
                            json.dump(dump_data, f, indent=4, ensure_ascii=False)
                        
                        print(f"   ✅ [DUMPED] {req.method} | {filename}")
                        captured_apis.append(filepath)
                        
                    except Exception as e:
                        # Mengabaikan JSON yang cacat atau pre-flight request (OPTIONS)
                        pass

        # Daftarkan penjaga gerbang
        page.on("response", handle_response)

        print(f"\n🚀 [PHASE 1] Memulai Deep Sniffing di: {url}")
        try:
            # Tunggu sampai halaman benar-benar selesai loading data
            await page.goto(url, wait_until="networkidle", timeout=60000)
            
            print(f"\n⚙️ [PHASE 2] Memicu interaksi halaman...")
            await human_auto_scroll(page)
            
            # Beri waktu ekstra jika ada API yang lambat merespons
            await asyncio.sleep(4)
            
        except Exception as e:
            print(f"⚠️ Ada hambatan saat memuat halaman: {e}")
        finally:
            await browser.close()
            print("\n" + "="*50)
            print(f"🎉 Misi Selesai! Berhasil merampas {len(captured_apis)} file API.")
            print(f"📂 Buka folder: {domain_dir}")
            print("="*50 + "\n")

if __name__ == "__main__":
    target = input("🌐 Masukkan URL Target (contoh: https://sfda.gov.sa/en/drugs-list): ").strip()
    
    # 🛡️ Validasi & Auto-Format URL
    if not target:
        print("❌ ERROR: URL tidak boleh kosong! Silakan jalankan ulang skrip.")
    else:
        # Jika user lupa mengetik http/https, kita tambahkan otomatis
        if not target.startswith("http://") and not target.startswith("https://"):
            print("⚠️ Protokol (http/https) tidak ditemukan. Menambahkan 'https://' secara otomatis...")
            target = "https://" + target
            
        asyncio.run(sniff_and_dump(target))