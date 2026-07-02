import sys
import os
import contextlib
import io
import time
from .lib_manager import import_single_component
from .config import TEMP_DIR

class ProgressBar:
    def __init__(self, total, prefix="Installing"):
        self.total = total
        self.prefix = prefix
        self.current = 0
        
    def update(self, current, lcsc=""):
        self.current = current
        percent = int(100 * (self.current / self.total))
        bar_length = 30
        filled_length = int(bar_length * self.current // self.total)
        bar = '█' * filled_length + '░' * (bar_length - filled_length)
        
        sys.stdout.write(f"\r\033[K[KiFlux] {self.prefix}: [{bar}] {percent}% | {self.current}/{self.total} ({lcsc})")
        sys.stdout.flush()
        
    def log(self, message):
        sys.stdout.write("\r\033[K")
        sys.stdout.flush()
        print(message)
        self.update(self.current)
        
    def finish(self):
        sys.stdout.write("\n")
        sys.stdout.flush()


KITS = {
    "basic-passives-0402": {
        "description": "Essential SMT basic passives in 0402 package (1k, 10k, 100n, 1u, 10u)",
        "components": {
            "C1525": "Capacitor 0402 100nF 50V X7R (Samsung)",
            "C52923": "Capacitor 0402 1uF 50V X7R (Samsung)",
            "C25076": "Resistor 0402 10k 5% 62.5mW (UNI-ROYAL)",
            "C11702": "Resistor 0402 1k 5% 62.5mW (UNI-ROYAL)",
            "C25087": "Resistor 0402 100R 5% 62.5mW (UNI-ROYAL)"
        }
    },
    "basic-passives-0603": {
        "description": "Essential SMT basic passives in 0603 package (1k, 10k, 100n, 1u, 10u)",
        "components": {
            "C14663": "Capacitor 0603 100nF 50V X7R (Samsung)",
            "C15849": "Capacitor 0603 1uF 50V X7R (Samsung)",
            "C19702": "Capacitor 0603 10uF 10V X7R (Samsung)",
            "C25804": "Resistor 0603 10k 5% 100mW (UNI-ROYAL)",
            "C25890": "Resistor 0603 1k 5% 100mW (UNI-ROYAL)"
        }
    },
    "rp2040-support": {
        "description": "Full support parts kit for Raspberry Pi RP2040 MCU design",
        "components": {
            "C2040": "Raspberry Pi RP2040 MCU (QFN-56)",
            "C347376": "XC6206P332MR LDO Regulator 3.3V SOT-23 (UMW)",
            "C9002": "12MHz Crystal SMD 3225 10pF (YXC)",
            "C1525": "Capacitor 0402 100nF 50V X7R (Samsung)",
            "C52923": "Capacitor 0402 1uF 50V X7R (Samsung)",
            "C11702": "Resistor 0402 1k 5% 62.5mW (UNI-ROYAL)",
            "C25076": "Resistor 0402 10k 5% 62.5mW (UNI-ROYAL)"
        }
    },
    "rp2350b-support": {
        "description": "Full support parts kit for Raspberry Pi RP2350B MCU design",
        "components": {
            "C42415655": "Raspberry Pi RP2350B MCU (QFN-80)",
            "C347376": "XC6206P332MR LDO Regulator 3.3V SOT-23 (UMW)",
            "C9002": "12MHz Crystal SMD 3225 10pF (YXC)",
            "C1525": "Capacitor 0402 100nF 50V X7R (Samsung)",
            "C52923": "Capacitor 0402 1uF 50V X7R (Samsung)",
            "C11702": "Resistor 0402 1k 5% 62.5mW (UNI-ROYAL)",
            "C25076": "Resistor 0402 10k 5% 62.5mW (UNI-ROYAL)"
        }
    },
    "maker-starter-kit": {
        "description": "The Ultimate SMT Maker Starter Kit (Essential Passives, Semiconductors, LDOs & LEDs)",
        "components": {
            "C1525": "Capacitor 0402 100nF 50V X7R (Samsung)",
            "C52923": "Capacitor 0402 1uF 50V X7R (Samsung)",
            "C14663": "Capacitor 0603 100nF 50V X7R (Samsung)",
            "C15849": "Capacitor 0603 1uF 50V X7R (Samsung)",
            "C19702": "Capacitor 0603 10uF 10V X7R (Samsung)",
            "C1612": "Capacitor 0603 22pF 50V C0G (Samsung)",
            "C25076": "Resistor 0402 10k 5% 62.5mW (UNI-ROYAL)",
            "C11702": "Resistor 0402 1k 5% 62.5mW (UNI-ROYAL)",
            "C25091": "Resistor 0402 4.7k 5% 62.5mW (UNI-ROYAL)",
            "C25087": "Resistor 0402 100R 5% 62.5mW (UNI-ROYAL)",
            "C25126": "Resistor 0402 0R 5% 62.5mW (UNI-ROYAL)",
            "C25804": "Resistor 0603 10k 5% 100mW (UNI-ROYAL)",
            "C25890": "Resistor 0603 1k 5% 100mW (UNI-ROYAL)",
            "C25867": "Resistor 0603 4.7k 5% 100mW (UNI-ROYAL)",
            "C25746": "Resistor 0603 100R 5% 100mW (UNI-ROYAL)",
            "C26083": "Resistor 0603 0R 5% 100mW (UNI-ROYAL)",
            "C81598": "SS34 Schottky Diode 40V 3A SMA (Yangjie)",
            "C8489": "2N7002 N-Channel MOSFET 60V 300mA SOT-23 (CJ)",
            "C20917": "AO3401 P-Channel MOSFET -30V -4A SOT-23 (AOS)",
            "C2286": "LED Red 0603 (Everlight)",
            "C2296": "LED Green 0603 (Everlight)",
            "C2297": "LED Blue 0603 (Everlight)",
            "C347376": "XC6206P332MR LDO Regulator 3.3V SOT-23 (UMW)",
            "C6186": "AMS1117-5.0 LDO Regulator 5V 1A SOT-223 (AMS)",
            "C136455": "CONN USB 2.0 Type-A Plug Right Angle TH (Molex)"
        }
    },
    "master-kiflux-catalog": {
        "description": "The Master KiFlux Catalog: Industry-standard curated production hardware components",
        "components": {
            "C2040": "Raspberry Pi RP2040 MCU (QFN-56)",
            "C42415655": "Raspberry Pi RP2350B MCU (QFN-80)",
            "C701342": "ESP32-WROOM-32E-N8 WiFi/BT Module (Espressif)",
            "C2913198": "ESP32-S3-WROOM-1-N8 Module (Espressif - compatible with N4/N8/N16R8)",
            "C82899": "ATTINY85-20SU 8-bit AVR MCU SOIC-8 (Microchip)",
            "C347209": "STM32F411CEU6 ARM Cortex-M4 MCU UFQFPN-48 (STMicroelectronics)",
            "C165948": "CONN USB Type-C Receptacle 16-pin Horizontal (Hualian)",
            "C134092": "CONN Micro USB Type-B Female Shielded SMT (Molex)",
            "C136455": "CONN USB 2.0 Type-A Plug Right Angle TH (Molex)",
            "C5261": "CONN USB 2.0 Type-A Receptacle Female Horizontal TH (XKB)",
            "C160404": "CONN JST SH 4-pin Horizontal SMT P=1mm Qwiic (JST)",
            "C173752": "CONN JST PH 2-pin Right Angle 2.00mm SMT (JST)",
            "C139797": "Tactile Switch SMD 4.2x3.2mm (ALPS)",
            "C16581": "TP4056 Lithium Battery Charger IC ESOP-8 (Nanjing Microone)",
            "C157924": "CONN JST XH 2-pin Vertical 2.50mm TH (JST)",
            "C318884": "Tactile Switch SMD 5.2x5.2mm (HRO)",
            "C157925": "CONN JST XH 3-pin Vertical 2.50mm TH (JST)",
            "C157926": "CONN JST XH 4-pin Vertical 2.50mm TH (JST)",
            "C22548": "CONN Header Male 1x40 2.54mm Straight (Burg)",
            "C84337": "CONN Terminal Block 2-position 5.08mm Blue (Xinya)",
            "C351410": "DW01A Battery Protection IC SOT-23-6 (Fortune Semi)",
            "C2830320": "FS8205A Dual N-Channel MOSFET 20V 6A SOT-23-6 (Fortune Semi)",
            "C347376": "XC6206P332MR LDO Regulator 3.3V SOT-23 (UMW)",
            "C841192": "RT9080-33GJ5 LDO Regulator 3.3V 600mA TSOT-23-5 (Richtek)",
            "C6186": "AMS1117-5.0 LDO Regulator 5V 1A SOT-223 (AMS)",
            "C84817": "MT3608 Boost DC-DC Converter SOT-23-6 (Aerosemi)",
            "C5189958": "CYA0630-10UH Shielded Power Inductor 10uH 4A (Sunlord)",
            "C168241": "Shielded Power Inductor 4.7uH 3.3A SMT (Sunlord)",
            "C168243": "Shielded Power Inductor 2.2uH 4A SMT (Sunlord)",
            "C81598": "SS34 Schottky Diode 40V 3A SMA (Yangjie)",
            "C14992": "1N5819 Schottky Diode 40V 1A SOT-23 (CJ)",
            "C192083": "BZX84C5V1 Zener Diode 5.1V SOT-23 (CJ)",
            "C82942": "MB6S Bridge Rectifier SOP-4 (Yangjie)",
            "C8489": "2N7002 N-Channel MOSFET 60V 300mA SOT-23 (CJ)",
            "C20917": "AO3401 P-Channel MOSFET -30V -4A SOT-23 (AOS)",
            "C11651": "MAX485 RS-485 Transceiver SOIC-8 (Maxim)",
            "C128553": "Tactile Push Button SMD 3x6x2.5mm (HRO)",
            "C918854": "RKJXV122400R 2-Axis Analog Joystick with Switch (ALPS)",
            "C94599": "Active Buzzer 3V/5V SMD (LD)",
            "C79401": "MAX16054AZT+T Push-Button On/Off Controller TSOT-23-6 (Analog Devices)",
            "C8239": "DS1307+ I2C Real Time Clock SOIC-8 (Maxim)",
            "C81458": "L9110S Dual Motor Driver SOP-8 (Guangdong Hottech)",
            "C293767": "2.4GHz Ceramic Chip Antenna SMD 3.2x1.6mm (Yageo)",
            "C8791": "RF nRF24L01P-R Transceiver 2.4GHz QFN-20 (Nordic)",
            "C9002": "12MHz Crystal SMD 3225 10pF (YXC)",
            "C12668": "16MHz Crystal SMD 3225 9pF (YXC)",
            "C101438": "8MHz Crystal SMD 3225 20pF (YXC)",
            "C32346": "32.768kHz Tuning Fork Crystal SMD 3215 12.5pF (YXC)",
            "C70068": "PPTC Resettable Fuse 500mA 16V 1812 (Sart)",
            "C126818": "1206L110THYR PPTC Resettable Fuse 1206 1.1A 8V (Littelfuse)",
            "C2286": "LED Red 0603 (Everlight)",
            "C2296": "LED Green 0603 (Everlight)",
            "C2297": "LED Blue 0603 (Everlight)",
            "C2290": "LED Yellow 0603 (Everlight)",
            "C2293": "LED White 0603 (Everlight)",
            "C965807": "LED Red 0402 (Everlight)",
            "C965799": "LED Green 0402 (Everlight)",
            "C965803": "LED Blue 0402 (Everlight)",
            "C965555": "WS2812B_2020 RGB NeoPixel LED 2.0x2.0mm (Worldsemi)",
            "C114586": "WS2812B_5050 RGB NeoPixel LED 5.0x5.0mm (Worldsemi)",
            "C1525": "Capacitor 0402 100nF 50V X7R (Samsung)",
            "C52923": "Capacitor 0402 1uF 50V X7R (Samsung)",
            "C1547": "Capacitor 0402 22pF 50V C0G (Samsung)",
            "C1540": "Capacitor 0402 10nF 50V X7R (Samsung)",
            "C1531": "Capacitor 0402 2.2nF 50V X7R (FH)",
            "C14663": "Capacitor 0603 100nF 50V X7R (Samsung)",
            "C15849": "Capacitor 0603 1uF 50V X7R (Samsung)",
            "C19702": "Capacitor 0603 10uF 10V X7R (Samsung)",
            "C1612": "Capacitor 0603 22pF 50V C0G (Samsung)",
            "C25076": "Resistor 0402 10k 5% 62.5mW (UNI-ROYAL)",
            "C11702": "Resistor 0402 1k 5% 62.5mW (UNI-ROYAL)",
            "C25091": "Resistor 0402 4.7k 5% 62.5mW (UNI-ROYAL)",
            "C25087": "Resistor 0402 100R 5% 62.5mW (UNI-ROYAL)",
            "C25126": "Resistor 0402 0R 5% 62.5mW (UNI-ROYAL)",
            "C25804": "Resistor 0603 10k 5% 100mW (UNI-ROYAL)",
            "C25890": "Resistor 0603 1k 5% 100mW (UNI-ROYAL)",
            "C25867": "Resistor 0603 4.7k 5% 100mW (UNI-ROYAL)",
            "C25746": "Resistor 0603 100R 5% 100mW (UNI-ROYAL)",
            "C26083": "Resistor 0603 0R 5% 100mW (UNI-ROYAL)"
        }
    }
}


KIT_ALIASES = {
    "all": ["all"],
    "master-kiflux-catalog": ["master", "master-catalog", "catalog", "master-kiflux-catalog"],
    "maker-starter-kit": ["maker", "starter", "starter-kit", "maker-starter-kit"],
    "basic-passives-0603": ["0603", "passives-0603", "basic-passives-0603"],
    "basic-passives-0402": ["0402", "passives-0402", "basic-passives-0402"],
    "rp2040-support": ["rp2040", "rp2040-support"],
    "rp2350b-support": ["rp2350", "rp2350b", "rp2350b-support"]
}

def resolve_kit_name(name):
    name = name.lower().strip()
    for kit_key, aliases in KIT_ALIASES.items():
        if name in aliases:
            return kit_key
    return None

def list_kits():
    print("\n=== KiFlux Component Recipe Kits ===\n")
    print(f"{'Kit Name':<25} | {'Description'}")
    print("-" * 105)
    for name, data in sorted(KITS.items()):
        print(f"{name:<25} | {data['description']}")
    print("\nTip: Run 'kiflux kit show <name>' to view components, or 'kiflux install <name>' to import them.\n")

def show_kit(name):
    resolved_name = resolve_kit_name(name)
    if not resolved_name or resolved_name == "all":
        print(f"[!] Error: Kit '{name}' not found. Run 'kiflux kit list' to see available kits.")
        return
    
    kit = KITS[resolved_name]
    print(f"\n=== Kit: {resolved_name} ===")
    print(f"Description: {kit['description']}\n")
    print(f"{'LCSC Part':<12} | {'Description'}")
    print("-" * 55)
    for lcsc, desc in sorted(kit["components"].items()):
        print(f"{lcsc:<12} | {desc}")
    print("")

def download_and_extract_kit_zip(resolved_name, paths):
    import urllib.request
    import zipfile
    import io
    
    # "all" e o master-kiflux-catalog que contem todos os componentes
    target_zip = "master-kiflux-catalog" if resolved_name == "all" else resolved_name
    cdn_url = f"https://raw.githubusercontent.com/oMatheus13/KiFlux/main/kits_prebuilt/{target_zip}.zip"
    
    print(f"[*] Trying to download prebuilt kit package '{target_zip}' from CDN...")
    
    try:
        req = urllib.request.Request(
            cdn_url, 
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        )
        with urllib.request.urlopen(req, timeout=8) as response:
            zip_data = response.read()
            
        print("[+] Download completed! Extracting package to library...")
        zip_file = zipfile.ZipFile(io.BytesIO(zip_data))
        
        # Extrai tudo para a raiz da biblioteca
        library_root = paths.root
        zip_file.extractall(library_root)
        
        # Reconstroi a biblioteca consolidada
        from .lib_manager import rebuild_consolidated_library
        rebuild_consolidated_library(paths)
        
        print(f"\n[+] Kit '{resolved_name}' installed instantly from CDN in a few seconds!")
        return True
    except Exception as e:
        print(f"[~] CDN package unavailable or offline. Falling back to local/EasyEDA install...")
        return False

def install_kit(name, paths):
    resolved_name = resolve_kit_name(name)
    if not resolved_name:
        print(f"[!] Error: Kit '{name}' not found. Run 'kiflux kit list' to see available kits.")
        return

    # Tenta baixar e instalar direto da CDN
    if download_and_extract_kit_zip(resolved_name, paths):
        return

    if resolved_name == "all":
        print(f"\n[*] Starting installation of ALL kits ({len(KITS)} kits)...")
        confirm = input("Do you want to proceed and import all components from all kits? [S(yes) / n(no)]: ").strip().lower()
        if confirm not in ['', 's', 'yes']:
            print("[*] Installation canceled.")
            return
            
        start_time = time.time()
        success_count = 0
        
        imported_lcscs = set()
        lcsc_list = []
        for kit_name, kit in sorted(KITS.items()):
            for lcsc in kit["components"].keys():
                if lcsc not in imported_lcscs:
                    lcsc_list.append(lcsc)
                    imported_lcscs.add(lcsc)
                    
        total_comps = len(lcsc_list)
        pbar = ProgressBar(total_comps, prefix="All Kits")
        pbar.update(0, "")
        
        failed_imports = []
        
        for idx, lcsc in enumerate(lcsc_list, 1):
            # Cooldown sleep de 1.0s para evitar rate-limits na API do EasyEDA
            # Pula se for passivo básico com footprint genérico pré-otimizado localmente
            is_passive = lcsc in ["C1525", "C52923", "C15529", "C14663", "C15849", "C19702", "C1612", "C25076", "C11702", "C25091", "C25087", "C25126", "C25804", "C25890", "C25867", "C25746", "C26083"]
            if idx > 1 and not is_passive:
                time.sleep(1.0)
                
            f_buf = io.StringIO()
            with contextlib.redirect_stdout(f_buf), contextlib.redirect_stderr(f_buf):
                success = import_single_component(lcsc, paths=paths, temp_dir=TEMP_DIR, auto_confirm=True)
            
            if success:
                success_count += 1
                pbar.update(idx, lcsc)
            else:
                failed_imports.append((lcsc, f_buf.getvalue()))
                pbar.update(idx, lcsc)
                
        pbar.finish()
        elapsed = time.time() - start_time
        print(f"\n[+] All kits installed: {success_count} of {total_comps} unique components imported successfully!")
        print(f"[*] Total time elapsed: {elapsed:.2f} seconds")
        
        if failed_imports:
            print("\n" + "=" * 60)
            print(f"❌  Installation Report: {len(failed_imports)} components failed to import")
            print("=" * 60)
            for idx_err, (lcsc_err, err_log) in enumerate(failed_imports, 1):
                err_lines = [line.strip() for line in err_log.split("\n") if line.strip()]
                last_err = err_lines[-1] if err_lines else "Unknown error"
                if len(last_err) > 80:
                    last_err = last_err[:77] + "..."
                print(f"{idx_err}. {lcsc_err} ➔ {last_err}")
                
            print("\n💡  Tip: You can retry importing these components individually using:")
            for lcsc_err, _ in failed_imports:
                print(f"    kiflux install {lcsc_err}")
            print("=" * 60 + "\n")
        return

    kit = KITS[resolved_name]
    print(f"\n[*] Starting installation of kit '{resolved_name}'...")
    print(f"This kit contains {len(kit['components'])} components. Please confirm installation.\n")
    
    confirm = input("Do you want to proceed and import all components? [S(yes) / n(no)]: ").strip().lower()
    if confirm not in ['', 's', 'yes']:
        print("[*] Installation canceled.")
        return
        
    start_time = time.time()
    success_count = 0
    total = len(kit["components"])
    
    # Carrega os componentes já existentes na biblioteca consolidada
    existing_lcscs = set()
    sym_file = paths.sym_lib_file
    if os.path.exists(sym_file):
        try:
            with open(sym_file, "r", encoding="utf-8") as f:
                content = f.read()
                import re
                for match in re.findall(r'"LCSC Part"\s+"(C\d+)"', content):
                    existing_lcscs.add(match)
        except Exception:
            pass
            
    pbar = ProgressBar(total, prefix=f"Kit {resolved_name}")
    pbar.update(0, "")
    
    failed_imports = []
    
    # Mantém o controle de quantos novos downloads reais foram feitos para saber se precisamos dar cooldown
    network_requests_count = 0
    
    for idx, lcsc in enumerate(kit["components"].keys(), 1):
        if lcsc in existing_lcscs:
            success_count += 1
            pbar.update(idx, lcsc)
            continue
            
        is_passive = lcsc in ["C1525", "C52923", "C15529", "C14663", "C15849", "C19702", "C1612", "C25076", "C11702", "C25091", "C25087", "C25126", "C25804", "C25890", "C25867", "C25746", "C26083"]
        if network_requests_count > 0 and not is_passive:
            time.sleep(1.0)
            
        network_requests_count += 1
        f_buf = io.StringIO()
        with contextlib.redirect_stdout(f_buf), contextlib.redirect_stderr(f_buf):
            success = import_single_component(lcsc, paths=paths, temp_dir=TEMP_DIR, auto_confirm=True)
            
        if success:
            success_count += 1
            pbar.update(idx, lcsc)
        else:
            failed_imports.append((lcsc, f_buf.getvalue()))
            pbar.update(idx, lcsc)
            
    pbar.finish()
    elapsed = time.time() - start_time
    print(f"\n[+] Kit '{resolved_name}' installation completed: {success_count} of {total} components imported successfully!")
    print(f"[*] Total time elapsed: {elapsed:.2f} seconds")
    
    if failed_imports:
        print("\n" + "=" * 60)
        print(f"❌  Installation Report: {len(failed_imports)} components failed to import")
        print("=" * 60)
        for idx_err, (lcsc_err, err_log) in enumerate(failed_imports, 1):
            err_lines = [line.strip() for line in err_log.split("\n") if line.strip()]
            last_err = err_lines[-1] if err_lines else "Unknown error"
            if len(last_err) > 80:
                last_err = last_err[:77] + "..."
            print(f"{idx_err}. {lcsc_err} ➔ {last_err}")
            
        print("\n💡  Tip: You can retry importing these components individually using:")
        for lcsc_err, _ in failed_imports:
            print(f"    kiflux install {lcsc_err}")
        print("=" * 60 + "\n")
