#!/usr/bin/env python3
import os
import sys
import shutil
import zipfile
from src.kiflux.kits import KITS
from src.kiflux.config import ensure_config_exists
from src.kiflux.lib_manager import extract_properties_from_temp

def main():
    paths = ensure_config_exists()
    
    # Diretórios de origem
    sym_dir = paths.sym_individual_dir
    pretty_dir = paths.fp_dir
    shapes_3d_dir = paths.dir_3d
    
    if not os.path.exists(sym_dir):
        print(f"[!] Error: Symbols directory '{sym_dir}' not found. Make sure you have installed components first.")
        sys.exit(1)
        
    # Diretório de destino para os pacotes zip
    repo_root = os.path.dirname(os.path.abspath(__file__))
    output_dir = os.path.join(repo_root, "kits_prebuilt")
    os.makedirs(output_dir, exist_ok=True)
    
    print("\n=== KiFlux Kit Prebuilt Packager ===\n")
    print(f"[*] Sourcing libraries from: {paths.root}")
    print(f"[*] Saving ZIP files to: {output_dir}\n")
    
    # Mapeia LCSC para arquivos locais escaneando a pasta symbols
    # Cada arquivo de símbolo individual tem as propriedades de footprint e 3d gravadas
    lcsc_map = {}
    for filename in os.listdir(sym_dir):
        if filename.endswith(".kicad_sym"):
            symbol_name = filename[:-10]
            # Extrai LCSC a partir do nome ou propriedades do arquivo
            # Para simplificar, vamos ler o arquivo para extrair o LCSC Part ID e propriedades do footprint
            file_path = os.path.join(sym_dir, filename)
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                
                # Procura a propriedade LCSC Part
                import re
                lcsc_match = re.search(r'\(property\s+"LCSC Part"\s+"([^"]+)"', content)
                fp_match = re.search(r'\(property\s+"Footprint"\s+"Maker:([^"]+)"', content)
                
                if lcsc_match:
                    lcsc_id = lcsc_match.group(1).upper().strip()
                    fp_name = fp_match.group(1) if fp_match else symbol_name
                    
                    # Procura arquivos 3d associados na pasta 3d
                    wrl_3d = f"{symbol_name}.wrl"
                    step_3d = f"{symbol_name}.step"
                    
                    lcsc_map[lcsc_id] = {
                        "symbol_file": filename,
                        "symbol_name": symbol_name,
                        "footprint_file": f"{fp_name}.kicad_mod" if fp_name else None,
                        "wrl_3d": wrl_3d if os.path.exists(os.path.join(shapes_3d_dir, wrl_3d)) else None,
                        "step_3d": step_3d if os.path.exists(os.path.join(shapes_3d_dir, step_3d)) else None
                    }
            except Exception as e:
                print(f"[~] Warning reading symbol {filename}: {e}")
                
    # Gera os arquivos zip para cada kit
    for kit_name, kit in sorted(KITS.items()):
        zip_path = os.path.join(output_dir, f"{kit_name}.zip")
        print(f"[*] Packaging kit '{kit_name}'...")
        
        # Cria o arquivo ZIP
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            packed_count = 0
            missing_count = 0
            
            for lcsc in kit["components"].keys():
                lcsc = lcsc.upper().strip()
                if lcsc not in lcsc_map:
                    print(f"  [!] Missing physical files for component {lcsc} ({kit['components'][lcsc]})")
                    missing_count += 1
                    continue
                    
                meta = lcsc_map[lcsc]
                
                # 1. Adiciona o símbolo
                sym_src = os.path.join(sym_dir, meta["symbol_file"])
                if os.path.exists(sym_src):
                    zipf.write(sym_src, os.path.join("symbols", meta["symbol_file"]))
                    
                # 2. Adiciona o footprint
                if meta["footprint_file"]:
                    fp_src = os.path.join(pretty_dir, meta["footprint_file"])
                    if os.path.exists(fp_src):
                        zipf.write(fp_src, os.path.join("Maker.pretty", meta["footprint_file"]))
                        
                # 3. Adiciona os modelos 3D
                if meta["wrl_3d"]:
                    wrl_src = os.path.join(shapes_3d_dir, meta["wrl_3d"])
                    if os.path.exists(wrl_src):
                        zipf.write(wrl_src, os.path.join("3d", meta["wrl_3d"]))
                if meta["step_3d"]:
                    step_src = os.path.join(shapes_3d_dir, meta["step_3d"])
                    if os.path.exists(step_src):
                        zipf.write(step_src, os.path.join("3d", meta["step_3d"]))
                        
                packed_count += 1
                
        print(f"  [+] Packaged successfully! {packed_count} components included. (Missing: {missing_count})")
        print(f"  [+] Saved to: {zip_path}\n")

if __name__ == "__main__":
    main()
