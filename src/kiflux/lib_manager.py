import os
import sys
import re
import shutil
import subprocess
import logging
from .jlc_api import fetch_jlcpcb_part_data, search_jlcpcb_components
from .heuristics import clean_name, generate_standardized_name

def run_easyeda2kicad(lcsc, temp_dir):
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)
    os.makedirs(temp_dir, exist_ok=True)
    
    cmd = [
        "easyeda2kicad",
        "--lcsc_id", lcsc,
        "--symbol",
        "--footprint",
        "--3d",
        "--output", os.path.join(temp_dir, "Maker.kicad_sym"),
        "--overwrite"
    ]
    
    print(f"[*] Executing: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"easyeda2kicad failed with code {result.returncode}.\nStderr: {result.stderr}")
    
    print(result.stdout)

def extract_properties_from_temp(temp_dir):
    temp_sym_path = os.path.join(temp_dir, "Maker.kicad_sym")
    if not os.path.exists(temp_sym_path):
        return "", "", ""
    with open(temp_sym_path, "r", encoding="utf-8") as f:
        content = f.read()
        
    value_match = re.search(r'\(property\s+"Value"\s+"([^"]+)"', content)
    mfr_match = re.search(r'\(property\s+"Manufacturer"\s+"([^"]+)"', content)
    fp_match = re.search(r'\(property\s+"Footprint"\s+"Maker:([^"]+)"', content)
    
    value = value_match.group(1) if value_match else ""
    manufacturer = mfr_match.group(1) if mfr_match else ""
    package = fp_match.group(1) if fp_match else ""
    
    return value, manufacturer, package

def extract_symbol_block(content, comp_name):
    symbol_start = content.find(f'(symbol "{comp_name}"')
    if symbol_start == -1:
        return None
        
    open_brackets = 0
    symbol_end = -1
    for i in range(symbol_start, len(content)):
        if content[i] == '(':
            open_brackets += 1
        elif content[i] == ')':
            open_brackets -= 1
            if open_brackets == 0:
                symbol_end = i + 1
                break
                
    if symbol_end == -1:
        return None
        
    return content[symbol_start:symbol_end]

def extract_all_symbol_blocks(content):
    symbols = []
    pos = 0
    while True:
        match = re.search(r'\(symbol "([^"]+)"', content[pos:])
        if not match:
            break
            
        sym_name = match.group(1)
        start_idx = content.find(f'(symbol "{sym_name}"', pos)
        
        open_brackets = 0
        end_idx = -1
        for i in range(start_idx, len(content)):
            if content[i] == '(':
                open_brackets += 1
            elif content[i] == ')':
                open_brackets -= 1
                if open_brackets == 0:
                    end_idx = i + 1
                    break
                    
        if end_idx != -1:
            symbol_block = content[start_idx:end_idx]
            line_start = content.rfind('\n', 0, start_idx) + 1
            prefix = content[line_start:start_idx]
            if prefix.strip() == "":
                symbols.append(symbol_block)
            pos = end_idx
        else:
            pos += 1
            
    return symbols

def get_friendly_value(comp_name):
    parts = comp_name.split("_")
    if not parts:
        return comp_name
        
    prefix = parts[0].upper()
    
    # 1. Resistores: R_<pkg>_<value>_<mfr> -> extrai <value>
    if prefix == "R" and len(parts) >= 3:
        return parts[2]
        
    # 2. Capacitores: C_<pkg>_<value>_<mfr> -> extrai <value>
    if prefix == "C" and len(parts) >= 3:
        return parts[2]
        
    # 3. Indutores: IND_<pkg>_<value>_<mfr> -> extrai <value> se for novo formato, senao extrai parts[1] (modelo)
    if prefix == "IND" and len(parts) >= 3:
        if len(parts) >= 4 and (parts[2].lower().endswith('h') or any(u in parts[2].lower() for u in ['nh', 'uh', 'mh'])):
            return parts[2]
        return parts[1]
        
    # 3. Semicondutores, MCUs, CIs, cristais, displays, etc.
    # PREFIX_MODEL_FOOTPRINT_MANUFACTURER -> extrai MODEL (parts[1])
    if len(parts) >= 4:
        return parts[1]
        
    if len(parts) == 3:
        return parts[1]
        
    if len(parts) > 1 and parts[0].isupper() and len(parts[0]) <= 5:
        return parts[1]
        
    return comp_name

def process_symbol(lcsc, final_name, temp_dir, paths, jlc_info=None):
    temp_sym_path = os.path.join(temp_dir, "Maker.kicad_sym")
    if not os.path.exists(temp_sym_path):
        print("[!] Temporary symbol file was not generated.")
        sys.exit(1)
        
    with open(temp_sym_path, "r", encoding="utf-8") as f:
        content = f.read()
        
    match = re.search(r'\(symbol "([^"]+)"', content)
    if not match:
        print("[!] Could not find symbol definition in temporary file.")
        sys.exit(1)
        
    orig_name = match.group(1)
    comp_name = clean_name(final_name)
    
    print(f"[*] Original Symbol: {orig_name} -> Final Name: {comp_name}")
    
    content = content.replace(f'(symbol "{orig_name}"', f'(symbol "{comp_name}"')
    content = re.sub(r'\(symbol "' + re.escape(orig_name) + r'(_\d+_\d+)"', r'(symbol "' + comp_name + r'\1"', content)
    content = re.sub(r'\(symbol "' + re.escape(orig_name) + r'(_\d+)"', r'(symbol "' + comp_name + r'\1"', content)
    
    content = re.sub(
        r'(\(property\s+"Value"\s+)"[^"]+"',
        f'\\1"{get_friendly_value(comp_name)}"',
        content
    )
    
    content = re.sub(
        r'(\(property\s+"Footprint"\s+)"[^"]+"',
        f'\\1"{paths.name}:{comp_name}"',
        content
    )
    
    # Remove propriedades antigas
    content = re.sub(r'\s*\(property\s+"LCSC Part"[\s\S]*?\n\s*\)', '', content)
    content = re.sub(r'\s*\(property\s+"JLCPCB Part #"\s*[\s\S]*?\n\s*\)', '', content)
    content = re.sub(r'\s*\(property\s+"JLCPCB Stock"[\s\S]*?\n\s*\)', '', content)
    content = re.sub(r'\s*\(property\s+"JLCPCB Prices"[\s\S]*?\n\s*\)', '', content)
    content = re.sub(r'\s*\(property\s+"LCSC Qty"[\s\S]*?\n\s*\)', '', content)
    
    lcsc_properties = (
        f'    (property "LCSC Part" "{lcsc}" (id 6) (at 0 0 0) (effects (font (size 1.27 1.27)) hide))\n'
        f'    (property "JLCPCB Part #" "{lcsc}" (id 7) (at 0 0 0) (effects (font (size 1.27 1.27)) hide))\n'
    )
    
    if jlc_info:
        lib_type = jlc_info.get("library_type", "Extended")
        stock = jlc_info.get("stock", 0)
        pb_list = jlc_info.get("price_breaks", [])
        pb_str = ",".join(f"{p['qty']}:{p['price']}" for p in pb_list)
        
        lcsc_properties += (
            f'    (property "JLCPCB Stock" "{lib_type}" (id 8) (at 0 0 0) (effects (font (size 1.27 1.27)) hide))\n'
            f'    (property "JLCPCB Prices" "{pb_str}" (id 9) (at 0 0 0) (effects (font (size 1.27 1.27)) hide))\n'
            f'    (property "LCSC Qty" "{stock}" (id 10) (at 0 0 0) (effects (font (size 1.27 1.27)) hide))\n'
        )
    
    insert_pos = -1
    for marker in [f'(symbol "{comp_name}_', '(pin ', '(rectangle ', '(text ', '(circle ', '(polyline ']:
        pos = content.find(marker)
        if pos != -1:
            if insert_pos == -1 or pos < insert_pos:
                insert_pos = pos
                
    if insert_pos == -1:
        insert_pos = content.rstrip().rfind(')')
        if insert_pos == -1:
            insert_pos = len(content)
            
    content = content[:insert_pos] + lcsc_properties + content[insert_pos:]
    
    symbol_block = extract_symbol_block(content, comp_name)
    if not symbol_block:
        print("[!] Error extracting symbol block after modification.")
        sys.exit(1)
        
    os.makedirs(paths.sym_individual_dir, exist_ok=True)
    individual_sym_file = os.path.join(paths.sym_individual_dir, f"{comp_name}.kicad_sym")
    
    individual_content = (
        "(kicad_symbol_lib\n"
        "  (version 20231120)\n"
        "  (generator kicad_symbol_editor)\n\n"
        f"  {symbol_block}\n"
        ")\n"
    )
    
    with open(individual_sym_file, "w", encoding="utf-8") as f:
        f.write(individual_content)
        
    print(f"[+] Individual symbol saved to: symbols/{comp_name}.kicad_sym")
    return comp_name, orig_name

def rebuild_consolidated_library(paths):
    print(f"[*] Rebuilding consolidated library {paths.name}.kicad_sym...")
    if not os.path.exists(paths.sym_individual_dir):
        os.makedirs(paths.sym_individual_dir, exist_ok=True)
        
    consolidated_content = (
        "(kicad_symbol_lib\n"
        "  (version 20231120)\n"
        "  (generator kicad_symbol_editor)\n"
    )
    
    files = sorted([f for f in os.listdir(paths.sym_individual_dir) if f.endswith(".kicad_sym")])
    
    for filename in files:
        file_path = os.path.join(paths.sym_individual_dir, filename)
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
            
        blocks = extract_all_symbol_blocks(content)
        for block in blocks:
            indented_block = "\n".join("  " + line if line.strip() else "" for line in block.split("\n"))
            indented_block = indented_block.lstrip()
            consolidated_content += f"\n  {indented_block}\n"
            
    consolidated_content += ")\n"
    
    with open(paths.sym_lib_file, "w", encoding="utf-8") as f:
        f.write(consolidated_content)
        
    print(f"[+] Consolidated library rebuilt with {len(files)} component(s)!")

def process_footprint(lcsc, comp_name, orig_name, temp_dir, paths):
    temp_fp_dir = os.path.join(temp_dir, "Maker.pretty")
    if not os.path.exists(temp_fp_dir):
        print("[!] Temporary footprint directory does not exist.")
        sys.exit(1)
        
    files = [f for f in os.listdir(temp_fp_dir) if f.endswith(".kicad_mod")]
    if not files:
        print("[!] No .kicad_mod footprint file was generated.")
        sys.exit(1)
        
    temp_mod_file = os.path.join(temp_fp_dir, files[0])
    orig_fp_name = files[0].replace(".kicad_mod", "")
    
    with open(temp_mod_file, "r", encoding="utf-8") as f:
        content = f.read()
        
    content = re.sub(
        r'\((module|footprint) [^\s\(]+',
        f'(\\1 {comp_name}',
        content
    )
    
    content = re.sub(
        r'\(fp_text value [^\s\(]+',
        f'(fp_text value {comp_name}',
        content
    )
    
    content = re.sub(r'\(property "LCSC Part"[^\)]*\)\s*', '', content)
    content = re.sub(r'\(property "JLCPCB Part #"[^\)]*\)\s*', '', content)
    
    properties_block = (
        f'\t(property "LCSC Part" "{lcsc}")\n'
        f'\t(property "JLCPCB Part #" "{lcsc}")'
    )
    
    content = re.sub(
        r'(\(fp_text user %R [^\)]*\))',
        r'\1\n' + properties_block,
        content
    )
    
    temp_3d_dir = os.path.join(temp_dir, "Maker.3dshapes")
    has_temp_3d = False
    if os.path.exists(temp_3d_dir):
        for f in os.listdir(temp_3d_dir):
            if f.lower().endswith(('.wrl', '.step')):
                has_temp_3d = True
                break
                
    target_3d_wrl = os.path.join(paths.dir_3d, f"{comp_name}.wrl")
    
    if not has_temp_3d:
        comp_name_upper = comp_name.upper()
        prefix_file = None
        if comp_name_upper.startswith("C_"):
            prefix_file = "c"
        elif comp_name_upper.startswith("R_"):
            prefix_file = "r"
            
        pkg = None
        if "0402" in comp_name_upper:
            pkg = "0402"
        elif "0603" in comp_name_upper:
            pkg = "0603"
        elif "0805" in comp_name_upper:
            pkg = "0805"
        elif "1206" in comp_name_upper:
            pkg = "1206"
            
        if prefix_file and pkg:
            generic_filename = f"{prefix_file}_{pkg}.step"
            generic_path = os.path.join(paths.dir_3d, "generic", generic_filename)
            if os.path.exists(generic_path):
                target_3d_wrl = generic_path
    
    orig_3d_file = None
    model_match = re.search(r'\(model\s+"?([^"\s\)]+)"?', content)
    if model_match:
        orig_3d_file = os.path.basename(model_match.group(1))

    content = re.sub(r'\(model [\s\S]*?\n\t\)', '', content)
    
    model_block = (
        f'\t(model "{target_3d_wrl}"\n'
        f'\t\t(offset (xyz 0.000 0.000 0.000))\n'
        f'\t\t(scale (xyz 1 1 1))\n'
        f'\t\t(rotate (xyz 0 0 0))\n'
        f'\t)'
    )
    
    last_bracket = content.rfind(')')
    if last_bracket != -1:
        content = content[:last_bracket].rstrip() + "\n" + model_block + "\n)"
        
    os.makedirs(paths.fp_dir, exist_ok=True)
    target_mod_file = os.path.join(paths.fp_dir, f"{comp_name}.kicad_mod")
    
    with open(target_mod_file, "w", encoding="utf-8") as f:
        f.write(content)
        
    print(f"[+] Footprint '{comp_name}' successfully saved to {paths.name}.pretty!")
    return orig_fp_name, orig_3d_file

def process_3d(comp_name, orig_3d_file, temp_dir, paths):
    temp_3d_dir = os.path.join(temp_dir, "Maker.3dshapes")
    has_copied = False
    
    if os.path.exists(temp_3d_dir) and orig_3d_file:
        os.makedirs(paths.dir_3d, exist_ok=True)
        wrl_src = os.path.join(temp_3d_dir, orig_3d_file)
        base_name, ext = os.path.splitext(orig_3d_file)
        step_src = os.path.join(temp_3d_dir, f"{base_name}.step")
        
        if os.path.exists(wrl_src):
            shutil.copy(wrl_src, os.path.join(paths.dir_3d, f"{comp_name}.wrl"))
            print(f"[+] WRL 3D Model '{comp_name}.wrl' saved in 3d folder.")
            has_copied = True
            
        if os.path.exists(step_src):
            shutil.copy(step_src, os.path.join(paths.dir_3d, f"{comp_name}.step"))
            print(f"[+] STEP 3D Model '{comp_name}.step' saved in 3d folder.")
            has_copied = True
            
    if not has_copied:
        comp_name_upper = comp_name.upper()
        prefix_file = None
        if comp_name_upper.startswith("C_"):
            prefix_file = "c"
        elif comp_name_upper.startswith("R_"):
            prefix_file = "r"
            
        pkg = None
        if "0402" in comp_name_upper:
            pkg = "0402"
        elif "0603" in comp_name_upper:
            pkg = "0603"
        elif "0805" in comp_name_upper:
            pkg = "0805"
        elif "1206" in comp_name_upper:
            pkg = "1206"
            
        if prefix_file and pkg:
            generic_filename = f"{prefix_file}_{pkg}.step"
            generic_path = os.path.join(paths.dir_3d, "generic", generic_filename)
            if os.path.exists(generic_path):
                print(f"[+] Shared generic 3D model '{generic_filename}' associated to footprint.")
            else:
                print(f"[!] Shared generic 3D model '{generic_filename}' is missing in generic folder.")
        else:
            print("[*] No 3D model files were generated by easyeda2kicad.")

def find_name_by_lcsc(lcsc_id, paths):
    lcsc_id = lcsc_id.upper().strip()
    if not os.path.exists(paths.sym_individual_dir):
        return None
    for filename in os.listdir(paths.sym_individual_dir):
        if filename.endswith(".kicad_sym"):
            filepath = os.path.join(paths.sym_individual_dir, filename)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
                if re.search(r'\(property\s+"(?:LCSC Part|JLCPCB Part #)"\s+"' + re.escape(lcsc_id) + r'"', content):
                    return filename.replace(".kicad_sym", "")
            except Exception as e:
                print(f"[!] Error reading {filename}: {e}")
    return None

def import_single_component(lcsc, custom_name=None, paths=None, temp_dir=None, auto_confirm=False, write_lock=None):
    lcsc = lcsc.upper().strip()
    print(f"\n=== Starting component import: {lcsc} ===")
    
    # Busca informações de preços/estoque da JLCPCB
    print("[*] Querying JLCPCB stock classification & pricing API...")
    jlc_info = fetch_jlcpcb_part_data(lcsc)
    
    try:
        run_easyeda2kicad(lcsc, temp_dir)
    except Exception as e:
        print(f"[!] Error: {e}")
        return False
        
    value, manufacturer, package = extract_properties_from_temp(temp_dir)
    
    if not value:
        print(f"[!] Error: Could not retrieve LCSC metadata for code {lcsc}.")
        return False
        
    temp_sym_path = os.path.join(temp_dir, "Maker.kicad_sym")
    temp_sym_content = ""
    if os.path.exists(temp_sym_path):
        with open(temp_sym_path, "r", encoding="utf-8") as f:
            temp_sym_content = f.read()
            
    jlc_desc = jlc_info.get("describe") if jlc_info else None
    final_name = custom_name if custom_name else generate_standardized_name(value, manufacturer, package, temp_sym_content, jlc_desc)
    if not final_name:
        print("[!] Error: Component name generated is blank.")
        return False
        
    temp_3d_dir = os.path.join(temp_dir, "Maker.3dshapes")
    has_3d = False
    is_fallback = False
    if os.path.exists(temp_3d_dir):
        for f in os.listdir(temp_3d_dir):
            if f.lower().endswith(('.wrl', '.step')):
                has_3d = True
                break
                
    if not has_3d:
        comp_name_upper = final_name.upper()
        is_passive = comp_name_upper.startswith("C_") or comp_name_upper.startswith("R_")
        has_std_pkg = any(pkg in comp_name_upper for pkg in ["0402", "0603", "0805", "1206"])
        if is_passive and has_std_pkg:
            is_fallback = True
            has_3d = True
        
    print(f"\n[+] Component identified on LCSC:")
    print(f"    LCSC Part:      {lcsc}")
    print(f"    Original Value: {value}")
    print(f"    Manufacturer:   {manufacturer}")
    print(f"    Package:        {package}")
    print(f"    Suggested Name: {final_name}")
    
    if jlc_info:
        print(f"    JLCPCB Class:   {jlc_info['library_type']} Part (Stock: {jlc_info['stock']})")
        if jlc_info['price_breaks']:
            print(f"    Sample Price:   ${jlc_info['price_breaks'][0]['price']} USD")
            
    if has_3d:
        if is_fallback:
            print("    3D Model:       [✓] Available (KiCad generic fallback)")
        else:
            print("    3D Model:       [✓] Available")
    else:
        print("    3D Model:       [!] Missing (Not provided by EasyEDA/LCSC)")
            
    if not auto_confirm:
        confirm = input(f"\nDo you want to confirm the import of this component as '{final_name}'? [S(yes) / n(no) / r(type custom name)]: ").strip()
        confirm_lower = confirm.lower()
        
        if confirm_lower.startswith('r'):
            parts = confirm.split(maxsplit=1)
            if len(parts) > 1:
                final_name = clean_name(parts[1])
                print(f"[*] Proceeding with custom name: '{final_name}'")
            else:
                custom_input = input("Enter custom name: ").strip()
                if not custom_input:
                    print("[!] Invalid name. Aborting import.")
                    if os.path.exists(temp_dir):
                        shutil.rmtree(temp_dir)
                    return False
                final_name = clean_name(custom_input)
                print(f"[*] Proceeding with custom name: '{final_name}'")
                
        elif confirm_lower not in ['', 's', 'yes']:
            print(f"[!] Import of {lcsc} canceled by user.")
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
            return False
    else:
        print(f"\n[*] Auto-confirming component name as '{final_name}'")
        
    if write_lock:
        with write_lock:
            comp_name, orig_name = process_symbol(lcsc, final_name, temp_dir, paths, jlc_info)
            orig_fp_name, orig_3d_file = process_footprint(lcsc, comp_name, orig_name, temp_dir, paths)
            process_3d(comp_name, orig_3d_file, temp_dir, paths)
            rebuild_consolidated_library(paths)
    else:
        comp_name, orig_name = process_symbol(lcsc, final_name, temp_dir, paths, jlc_info)
        orig_fp_name, orig_3d_file = process_footprint(lcsc, comp_name, orig_name, temp_dir, paths)
        process_3d(comp_name, orig_3d_file, temp_dir, paths)
        rebuild_consolidated_library(paths)
    
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)
        
    print(f"=== Import completed successfully! Component: {comp_name} ===")
    return True

def remove_component(comp_name, paths):
    comp_name = clean_name(comp_name)
    print(f"[*] Removing component '{comp_name}'...")
    
    sym_path = os.path.join(paths.sym_individual_dir, f"{comp_name}.kicad_sym")
    if os.path.exists(sym_path):
        os.remove(sym_path)
        print(f"  [-] Individual symbol removed: symbols/{comp_name}.kicad_sym")
    else:
        print(f"  [!] Symbol not found at symbols/{comp_name}.kicad_sym")
        
    fp_path = os.path.join(paths.fp_dir, f"{comp_name}.kicad_mod")
    if os.path.exists(fp_path):
        os.remove(fp_path)
        print(f"  [-] Footprint removed: {paths.name}.pretty/{comp_name}.kicad_mod")
    else:
        print(f"  [!] Footprint not found at {paths.name}.pretty/{comp_name}.kicad_mod")
        
    wrl_path = os.path.join(paths.dir_3d, f"{comp_name}.wrl")
    step_path = os.path.join(paths.dir_3d, f"{comp_name}.step")
    
    if os.path.exists(wrl_path):
        os.remove(wrl_path)
        print(f"  [-] 3D WRL model removed: 3d/{comp_name}.wrl")
    if os.path.exists(step_path):
        os.remove(step_path)
        print(f"  [-] 3D STEP model removed: 3d/{comp_name}.step")
        
    rebuild_consolidated_library(paths)
    print(f"[+] Component '{comp_name}' removed successfully!")

def rename_component(old_name, new_name, paths):
    old_name = clean_name(old_name)
    new_name = clean_name(new_name)
    
    if old_name == new_name:
        print("[!] Error: Old name and new name are identical.")
        sys.exit(1)
        
    print(f"[*] Renaming component from '{old_name}' to '{new_name}'...")
    
    old_sym_path = os.path.join(paths.sym_individual_dir, f"{old_name}.kicad_sym")
    new_sym_path = os.path.join(paths.sym_individual_dir, f"{new_name}.kicad_sym")
    
    if os.path.exists(old_sym_path):
        with open(old_sym_path, "r", encoding="utf-8") as f:
            content = f.read()
            
        content = content.replace(f'(symbol "{old_name}"', f'(symbol "{new_name}"')
        content = re.sub(r'\(symbol "' + re.escape(old_name) + r'(_\d+_\d+)"', r'(symbol "' + new_name + r'\1"', content)
        content = re.sub(r'\(symbol "' + re.escape(old_name) + r'(_\d+)"', r'(symbol "' + new_name + r'\1"', content)
        
        content = re.sub(
            r'(\(property\s+"Value"\s+)"[^"]+"',
            f'\\1"{get_friendly_value(new_name)}"',
            content
        )
        
        content = re.sub(
            r'(\(property\s+"Footprint"\s+)"[^"]+"',
            f'\\1"{paths.name}:{new_name}"',
            content
        )
        
        with open(new_sym_path, "w", encoding="utf-8") as f:
            f.write(content)
            
        os.remove(old_sym_path)
        print(f"  [~] Individual symbol updated: symbols/{new_name}.kicad_sym")
    else:
        print(f"  [!] Symbol not found at symbols/{old_name}.kicad_sym (skipping)")
        
    old_fp_path = os.path.join(paths.fp_dir, f"{old_name}.kicad_mod")
    new_fp_path = os.path.join(paths.fp_dir, f"{new_name}.kicad_mod")
    
    if os.path.exists(old_fp_path):
        with open(old_fp_path, "r", encoding="utf-8") as f:
            content = f.read()
            
        content = re.sub(
            r'\((module|footprint) [^\s\(]+',
            f'(\\1 {new_name}',
            content
        )
        
        content = re.sub(
            r'\(fp_text value [^\s\(]+',
            f'(fp_text value {new_name}',
            content
        )
        
        old_3d_wrl = os.path.join(paths.dir_3d, f"{old_name}.wrl")
        new_3d_wrl = os.path.join(paths.dir_3d, f"{new_name}.wrl")
        content = content.replace(f'"{old_3d_wrl}"', f'"{new_3d_wrl}"')
        
        with open(new_fp_path, "w", encoding="utf-8") as f:
            f.write(content)
            
        os.remove(old_fp_path)
        print(f"  [~] Footprint updated: {paths.name}.pretty/{new_name}.kicad_mod")
    else:
        print(f"  [!] Footprint not found at {paths.name}.pretty/{old_name}.kicad_mod (skipping)")
        
    old_wrl_path = os.path.join(paths.dir_3d, f"{old_name}.wrl")
    new_wrl_path = os.path.join(paths.dir_3d, f"{new_name}.wrl")
    old_step_path = os.path.join(paths.dir_3d, f"{old_name}.step")
    new_step_path = os.path.join(paths.dir_3d, f"{new_name}.step")
    
    if os.path.exists(old_wrl_path):
        os.rename(old_wrl_path, new_wrl_path)
        print(f"  [~] 3D WRL model renamed to: 3d/{new_name}.wrl")
        
    if os.path.exists(old_step_path):
        os.rename(old_step_path, new_step_path)
        print(f"  [~] 3D STEP model renamed to: 3d/{new_name}.step")
        
    rebuild_consolidated_library(paths)
    print(f"[+] Component renamed from '{old_name}' to '{new_name}' successfully!")

def list_components(paths):
    print(f"\n=== KiFlux Library Inventory ===\nDirectory: {paths.root}\n")
    if not os.path.exists(paths.sym_individual_dir):
        print("No components registered yet.")
        return
        
    files = sorted([f for f in os.listdir(paths.sym_individual_dir) if f.endswith(".kicad_sym")])
    if not files:
        print("No components registered yet.")
        return
        
    print(f"{'Component Name':<35} | {'LCSC':<8} | {'Type':<8} | {'Manufacturer':<20} | {'3D'}")
    print("-" * 90)
    
    for filename in files:
        filepath = os.path.join(paths.sym_individual_dir, filename)
        comp_name = filename.replace(".kicad_sym", "")
        
        lcsc = "N/A"
        mfr = "N/A"
        stock_type = "N/A"
        
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            lcsc_match = re.search(r'\(property\s+"LCSC Part"\s+"([^"]+)"', content)
            mfr_match = re.search(r'\(property\s+"Manufacturer"\s+"([^"]+)"', content)
            type_match = re.search(r'\(property\s+"JLCPCB Stock"\s+"([^"]+)"', content)
            if lcsc_match:
                lcsc = lcsc_match.group(1)
            if mfr_match:
                mfr = mfr_match.group(1).split('(')[0].strip()
            if type_match:
                stock_type = type_match.group(1)
        except Exception:
            pass
            
        has_3d = "[x] Missing"
        fp_path = os.path.join(paths.fp_dir, f"{comp_name}.kicad_mod")
        if os.path.exists(fp_path):
            try:
                with open(fp_path, "r", encoding="utf-8") as f_fp:
                    fp_content = f_fp.read()
                model_match = re.search(r'\(model\s+"([^"]+)"', fp_content)
                if model_match:
                    model_path = model_match.group(1)
                    if os.path.exists(model_path):
                        has_3d = "[✓] wrl/step"
            except Exception:
                pass
        print(f"{comp_name:<35} | {lcsc:<8} | {stock_type:<8} | {mfr:<20} | {has_3d}")
    print(f"\nTotal: {len(files)} component(s)\n")

def show_info(target, paths):
    if re.match(r'^C\d+$', target.upper().strip()):
        resolved = find_name_by_lcsc(target, paths)
        if not resolved:
            print(f"[!] Error: No component found with LCSC code '{target}'")
            return
        target = resolved
        
    sym_path = os.path.join(paths.sym_individual_dir, f"{target}.kicad_sym")
    if not os.path.exists(sym_path):
        print(f"[!] Error: Component '{target}' is not registered in the library.")
        return
        
    print(f"\n=== Component Details: {target} ===")
    
    lcsc = "N/A"
    mfr = "N/A"
    mpn = "N/A"
    datasheet = "N/A"
    fp_ref = "N/A"
    stock_type = "N/A"
    prices_str = "N/A"
    lcsc_qty = "N/A"
    
    try:
        with open(sym_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        lcsc_match = re.search(r'\(property\s+"LCSC Part"\s+"([^"]+)"', content)
        mfr_match = re.search(r'\(property\s+"Manufacturer"\s+"([^"]+)"', content)
        mpn_match = re.search(r'\(property\s+"MPN"\s+"([^"]+)"', content)
        ds_match = re.search(r'\(property\s+"Datasheet"\s+"([^"]+)"', content)
        fp_match = re.search(r'\(property\s+"Footprint"\s+"([^"]+)"', content)
        st_match = re.search(r'\(property\s+"JLCPCB Stock"\s+"([^"]+)"', content)
        pr_match = re.search(r'\(property\s+"JLCPCB Prices"\s+"([^"]+)"', content)
        qty_match = re.search(r'\(property\s+"LCSC Qty"\s+"([^"]+)"', content)
        
        if lcsc_match: lcsc = lcsc_match.group(1)
        if mfr_match: mfr = mfr_match.group(1)
        if mpn_match: mpn = mpn_match.group(1)
        if ds_match: datasheet = ds_match.group(1)
        if fp_match: fp_ref = fp_match.group(1)
        if st_match: stock_type = st_match.group(1)
        if pr_match: prices_str = pr_match.group(1)
        if qty_match: lcsc_qty = qty_match.group(1)
    except Exception as e:
        print(f"[!] Error reading metadata: {e}")
        
    has_wrl = "Yes" if os.path.exists(os.path.join(paths.dir_3d, f"{target}.wrl")) else "No"
    has_step = "Yes" if os.path.exists(os.path.join(paths.dir_3d, f"{target}.step")) else "No"
    
    print(f"LCSC/JLCPCB Code:    {lcsc}")
    print(f"Manufacturer:        {mfr}")
    print(f"Part Number (MPN):   {mpn}")
    print(f"Footprint Link:      {fp_ref}")
    print(f"3D WRL Model:        {has_wrl}")
    print(f"3D STEP Model:       {has_step}")
    print(f"Datasheet:           {datasheet}")
    print(f"JLCPCB Stock Class:  {stock_type}")
    print(f"LCSC Quantity Stock: {lcsc_qty}")
    if prices_str and prices_str != "N/A":
        print("JLCPCB Price Breaks:")
        for pb in prices_str.split(","):
            if ":" in pb:
                qty, pr = pb.split(":")
                print(f"  - {qty}+ pcs: ${pr} USD")
    print(f"Physical Symbol:     symbols/{target}.kicad_sym")
    print(f"Physical Footprint:  {paths.name}.pretty/{target}.kicad_mod")
    print()

def open_datasheet(target, paths):
    if re.match(r'^C\d+$', target.upper().strip()):
        resolved = find_name_by_lcsc(target, paths)
        if not resolved:
            print(f"[!] Error: No component found with LCSC code '{target}'")
            return
        target = resolved
        
    sym_path = os.path.join(paths.sym_individual_dir, f"{target}.kicad_sym")
    if not os.path.exists(sym_path):
        print(f"[!] Error: Component '{target}' is not registered in the library.")
        return
        
    try:
        with open(sym_path, "r", encoding="utf-8") as f:
            content = f.read()
        ds_match = re.search(r'\(property\s+"Datasheet"\s+"([^"]+)"', content)
        if ds_match and ds_match.group(1).startswith("http"):
            url = ds_match.group(1)
            print(f"[*] Opening datasheet: {url}")
            subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            print(f"[!] Datasheet URL is not available or invalid for '{target}'")
    except Exception as e:
        print(f"[!] Error opening datasheet: {e}")

def check_library(paths):
    print(f"\n=== KiFlux Integrity Audit ===\n")
    if not os.path.exists(paths.sym_individual_dir):
        print("[✓] Library is empty and consistent.")
        return
        
    files = sorted([f for f in os.listdir(paths.sym_individual_dir) if f.endswith(".kicad_sym")])
    if not files:
        print("[✓] Library is empty and consistent.")
        return
        
    warnings = 0
    errors = 0
    
    for filename in files:
        comp_name = filename.replace(".kicad_sym", "")
        sym_path = os.path.join(paths.sym_individual_dir, filename)
        fp_path = os.path.join(paths.fp_dir, f"{comp_name}.kicad_mod")
        
        if not os.path.exists(fp_path):
            print(f"[ERROR] Missing footprint for component '{comp_name}' (expected: {paths.name}.pretty/{comp_name}.kicad_mod)")
            errors += 1
            
        try:
            with open(sym_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            lcsc_match = re.search(r'\(property\s+"LCSC Part"\s+"([^"]+)"', content)
            jlc_match = re.search(r'\(property\s+"JLCPCB Part #"\s+"([^"]+)"', content)
            fp_prop_match = re.search(r'\(property\s+"Footprint"\s+"([^"]+)"', content)
            
            if not lcsc_match:
                print(f"[WARNING] Component '{comp_name}' lacks 'LCSC Part' property.")
                warnings += 1
            if not jlc_match:
                print(f"[WARNING] Component '{comp_name}' lacks 'JLCPCB Part #' property.")
                warnings += 1
            if fp_prop_match and fp_prop_match.group(1) != f"{paths.name}:{comp_name}":
                print(f"[ERROR] Component '{comp_name}' links to footprint '{fp_prop_match.group(1)}' instead of '{paths.name}:{comp_name}' (broken match!)")
                errors += 1
        except Exception as e:
            print(f"[ERROR] Failed to read properties of symbol '{comp_name}': {e}")
            errors += 1
            
        if os.path.exists(fp_path):
            try:
                with open(fp_path, "r", encoding="utf-8") as f:
                    fp_content = f.read()
                model_match = re.search(r'\(model\s+"([^"]+)"', fp_content)
                if model_match:
                    model_path = model_match.group(1)
                    if not os.path.exists(model_path):
                        print(f"[ERROR] Footprint '{comp_name}' links to missing 3D model: {model_path}")
                        errors += 1
            except Exception as e:
                print(f"[ERROR] Failed to read footprint '{comp_name}': {e}")
                errors += 1
                
    print("-" * 60)
    print(f"Audit completed: {errors} error(s), {warnings} warning(s).")
    if errors == 0 and warnings == 0:
        print("[✓] Library is 100% consistent and intact!")
    else:
        print("[!] Please address the issues listed above to avoid manufacturing defects.")
    print()

def update_all_components(paths, temp_dir):
    print(f"\n=== Starting Library-Wide Update ===")
    if not os.path.exists(paths.sym_individual_dir):
        print("No components registered in the library.")
        return
        
    files = sorted([f for f in os.listdir(paths.sym_individual_dir) if f.endswith(".kicad_sym")])
    if not files:
        print("No components registered in the library.")
        return
        
    print(f"Found {len(files)} components to check.\n")
    updated_count = 0
    
    for filename in files:
        comp_name = filename.replace(".kicad_sym", "")
        filepath = os.path.join(paths.sym_individual_dir, filename)
        
        lcsc = ""
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            lcsc_match = re.search(r'\(property\s+"LCSC Part"\s+"([^"]+)"', content)
            if lcsc_match:
                lcsc = lcsc_match.group(1).upper().strip()
        except Exception:
            pass
            
        if not lcsc:
            print(f"[~] Skipping '{comp_name}' (No LCSC Part ID found in metadata)")
            continue
            
        print(f"[*] Syncing prices & metadata for '{comp_name}' (LCSC: {lcsc})...")
        try:
            # Busca preços atualizados
            jlc_info = fetch_jlcpcb_part_data(lcsc)
            run_easyeda2kicad(lcsc, temp_dir)
            value, manufacturer, package = extract_properties_from_temp(temp_dir)
            if not value:
                print(f"  [!] Failed to fetch metadata for LCSC {lcsc} (skipping)")
                continue
                
            temp_sym_path = os.path.join(temp_dir, "Maker.kicad_sym")
            temp_sym_content = ""
            if os.path.exists(temp_sym_path):
                with open(temp_sym_path, "r", encoding="utf-8") as f:
                    temp_sym_content = f.read()
                    
            jlc_desc = jlc_info.get("describe") if jlc_info else None
            suggested_name = generate_standardized_name(value, manufacturer, package, temp_sym_content, jlc_desc)
            suggested_name_clean = clean_name(suggested_name)
            comp_name_clean = clean_name(comp_name)
            
            if suggested_name_clean == comp_name_clean:
                print(f"  [✓] Component '{comp_name_clean}' updated silently (Prices & files synced).")
                process_symbol(lcsc, comp_name_clean, temp_dir, paths, jlc_info)
                orig_fp_name, orig_3d_file = process_footprint(lcsc, comp_name_clean, comp_name_clean, temp_dir, paths)
                process_3d(comp_name_clean, orig_3d_file, temp_dir, paths)
            else:
                print(f"  [!] Convention change detected! Current: '{comp_name_clean}' -> Suggested: '{suggested_name_clean}'")
                confirm = input(f"  Confirm rename and update to '{suggested_name_clean}'? [S(yes) / n(no)]: ").strip().lower()
                if confirm in ['', 's', 'yes']:
                    orig_fp_name, orig_3d_file = process_footprint(lcsc, suggested_name_clean, comp_name_clean, temp_dir, paths)
                    process_3d(suggested_name_clean, orig_3d_file, temp_dir, paths)
                    process_symbol(lcsc, suggested_name_clean, temp_dir, paths, jlc_info)
                    rename_component(comp_name_clean, suggested_name_clean, paths)
                    updated_count += 1
                else:
                    # Se recusar renomeação, atualiza os preços do atual mesmo
                    print("  [~] Keeping current name, but syncing prices/files.")
                    process_symbol(lcsc, comp_name_clean, temp_dir, paths, jlc_info)
                    orig_fp_name, orig_3d_file = process_footprint(lcsc, comp_name_clean, comp_name_clean, temp_dir, paths)
                    process_3d(comp_name_clean, orig_3d_file, temp_dir, paths)
        except Exception as e:
            print(f"  [!] Error updating '{comp_name}': {e}")
            
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)
        
    rebuild_consolidated_library(paths)
    print(f"\n[+] Library-wide update completed! {updated_count} component(s) renamed.\n")

def search_components(keyword, part_type=None, in_stock_only=False):
    print(f"\n[*] Searching JLCPCB SMT Library for: '{keyword}'...\n")
    results = search_jlcpcb_components(keyword, part_type=part_type)
    
    if in_stock_only:
        results = [r for r in results if r['stock'] > 0]
        
    if not results:
        print("[!] No components found matching the query.")
        return
        
    print(f"{'LCSC Code':<11} | {'Type':<8} | {'Stock':<10} | {'Price (1+)':<10} | {'Brand':<15} | {'Description'}")
    print("-" * 105)
    for r in results:
        price_str = f"${r['price']:.4f} USD" if r['price'] > 0 else "N/A"
        desc = r.get('description', r['name'])
        if len(desc) > 45:
            desc = desc[:42] + "..."
        print(f"{r['lcsc']:<11} | {r['type']:<8} | {r['stock']:<10} | {price_str:<10} | {r['brand'][:15]:<15} | {desc}")
    print(f"\n[+] Tip: Import any component from the list using: 'kiflux <LCSC_CODE>'\n")
