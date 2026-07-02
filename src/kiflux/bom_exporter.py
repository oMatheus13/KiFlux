import os
import sys
import re
import csv

def extract_symbols_from_sch(sch_path):
    with open(sch_path, "r", encoding="utf-8") as f:
        content = f.read()
        
    symbols = []
    pos = 0
    while True:
        symbol_start = content.find("(symbol ", pos)
        if symbol_start == -1:
            break
            
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
                    
        if symbol_end != -1:
            block = content[symbol_start:symbol_end]
            
            in_bom = True
            if "(in_bom no)" in block:
                in_bom = False
                
            if in_bom:
                ref_match = re.search(r'\(property\s+"Reference"\s+"([^"]+)"', block)
                val_match = re.search(r'\(property\s+"Value"\s+"([^"]+)"', block)
                fp_match = re.search(r'\(property\s+"Footprint"\s+"([^"]+)"', block)
                lcsc_match = re.search(r'\(property\s+"(?:LCSC Part|JLCPCB Part #)"\s+"([^"]+)"', block)
                
                ref = ref_match.group(1) if ref_match else ""
                val = val_match.group(1) if val_match else ""
                fp = fp_match.group(1) if fp_match else ""
                lcsc = lcsc_match.group(1) if lcsc_match else ""
                
                if ref and not ref.startswith("#") and fp:
                    symbols.append({
                        "ref": ref,
                        "value": val,
                        "footprint": fp,
                        "lcsc": lcsc
                    })
            pos = symbol_end
        else:
            pos += 1
            
    return symbols

def extract_placements_from_pcb(pcb_path):
    with open(pcb_path, "r", encoding="utf-8") as f:
        content = f.read()
        
    placements = []
    pos = 0
    while True:
        fp_start = content.find("(footprint ", pos)
        if fp_start == -1:
            break
            
        open_brackets = 0
        fp_end = -1
        for i in range(fp_start, len(content)):
            if content[i] == '(':
                open_brackets += 1
            elif content[i] == ')':
                open_brackets -= 1
                if open_brackets == 0:
                    fp_end = i + 1
                    break
                    
        if fp_end != -1:
            block = content[fp_start:fp_end]
            
            layer = "Top"
            if '(layer "B.Cu")' in block:
                layer = "Bottom"
                
            ref_match = re.search(r'\(property\s+"Reference"\s+"([^"]+)"', block)
            ref = ref_match.group(1) if ref_match else ""
            
            at_match = re.search(r'\(at\s+([\d\.\-]+)\s+([\d\.\-]+)(?:\s+([\d\.\-]+))?\)', block)
            
            if ref and at_match:
                x = float(at_match.group(1))
                y = float(at_match.group(2))
                rot = float(at_match.group(3)) if at_match.group(3) else 0.0
                
                placements.append({
                    "ref": ref,
                    "x": x,
                    "y": y,
                    "rot": rot,
                    "layer": layer
                })
            pos = fp_end
        else:
            pos += 1
            
    return placements

def get_price_for_quantity(prices_str, total_qty):
    if not prices_str or prices_str == "N/A":
        return 0.0
    try:
        price_breaks = []
        for pb in prices_str.split(","):
            if ":" in pb:
                qty, pr = pb.split(":")
                price_breaks.append((int(qty), float(pr)))
        # Ordena as escalas decrescente por quantidade
        price_breaks.sort(key=lambda x: x[0], reverse=True)
        for qty, price in price_breaks:
            if total_qty >= qty:
                return price
        if price_breaks:
            return price_breaks[-1][1]
    except Exception:
        pass
    return 0.0

def export_bom_and_cpl(project_dir, output_dir=None, paths=None):
    project_dir = os.path.abspath(os.path.expanduser(project_dir))
    if not os.path.exists(project_dir) or not os.path.isdir(project_dir):
        print(f"[!] Error: Project directory does not exist: {project_dir}")
        sys.exit(1)
        
    if output_dir:
        output_dir = os.path.abspath(os.path.expanduser(output_dir))
        os.makedirs(output_dir, exist_ok=True)
    else:
        output_dir = project_dir
        
    print(f"[*] Scanning project directory: {project_dir}")
    print(f"[*] Output directory for reports: {output_dir}")
    
    sch_files = [os.path.join(project_dir, f) for f in os.listdir(project_dir) if f.endswith(".kicad_sch")]
    pcb_files = [os.path.join(project_dir, f) for f in os.listdir(project_dir) if f.endswith(".kicad_pcb")]
    
    if not sch_files:
        print("[!] Error: No schematic file (.kicad_sch) found in this directory.")
        sys.exit(1)
        
    all_components = []
    for sch_path in sch_files:
        print(f"  [+] Reading schematic: {os.path.basename(sch_path)}")
        all_components.extend(extract_symbols_from_sch(sch_path))
        
    if not all_components:
        print("[!] No valid components for BOM found in schematics.")
        return
        
    # Agrupa por valor, footprint e código LCSC
    grouped = {}
    for comp in all_components:
        key = (comp["value"], comp["footprint"], comp["lcsc"])
        if key not in grouped:
            grouped[key] = []
        grouped[key].append(comp["ref"])
        
    # Escreve BOM_JLCPCB.csv
    bom_path = os.path.join(output_dir, "BOM_JLCPCB.csv")
    with open(bom_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Comment", "Designator", "Footprint", "LCSC Part #"])
        
        for key, refs in sorted(grouped.items(), key=lambda x: x[0][0]):
            val, fp, lcsc = key
            fp_clean = fp.split(":")[-1] if ":" in fp else fp
            refs_sorted = sorted(refs, key=lambda r: (re.sub(r'\d+', '', r), int(re.search(r'\d+', r).group(0)) if re.search(r'\d+', r) else 0))
            designator_str = ", ".join(refs_sorted)
            writer.writerow([val, designator_str, fp_clean, lcsc])
            
    print(f"[+] BOM exported successfully: {os.path.join(os.path.basename(output_dir), 'BOM_JLCPCB.csv')} ({len(all_components)} part(s) grouped into {len(grouped)} lines)")
    
    # 2. Processamento do CPL
    if pcb_files:
        pcb_path = pcb_files[0]
        print(f"  [+] Reading PCB layout: {os.path.basename(pcb_path)}")
        placements = extract_placements_from_pcb(pcb_path)
        
        if placements:
            cpl_path = os.path.join(output_dir, "CPL_JLCPCB.csv")
            with open(cpl_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["Designator", "Mid X", "Mid Y", "Rotation", "Layer"])
                
                for p in sorted(placements, key=lambda x: (re.sub(r'\d+', '', x["ref"]), int(re.search(r'\d+', x["ref"]).group(0)) if re.search(r'\d+', x["ref"]) else 0)):
                    writer.writerow([p["ref"], f"{p['x']:.4f}", f"{p['y']:.4f}", f"{p['rot'] % 360:.2f}", p["layer"]])
                    
            print(f"[+] CPL (Centroid) exported successfully: {os.path.join(os.path.basename(output_dir), 'CPL_JLCPCB.csv')} ({len(placements)} placements registered)")
        else:
            print("  [!] No valid component coordinates found in the layout file.")
    else:
        print("  [~] No .kicad_pcb file found (skipping CPL export).")

    # 3. Estimativa de Custos Offline da JLCPCB
    if not paths:
        return
        
    print("\n--- JLCPCB Cost Estimation Helper ---")
    try:
        ans = input("How many boards do you plan to manufacture? [Default: 5]: ").strip()
        num_boards = int(ans) if ans else 5
    except Exception:
        num_boards = 5
        
    print(f"[*] Calculating estimated costs for {num_boards} boards...")
    
    # Carrega base local da biblioteca
    lib_data = {}
    if os.path.exists(paths.sym_individual_dir):
        for filename in os.listdir(paths.sym_individual_dir):
            if filename.endswith(".kicad_sym"):
                filepath = os.path.join(paths.sym_individual_dir, filename)
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        content = f.read()
                    lcsc_match = re.search(r'\(property\s+"LCSC Part"\s+"([^"]+)"', content)
                    st_match = re.search(r'\(property\s+"JLCPCB Stock"\s+"([^"]+)"', content)
                    pr_match = re.search(r'\(property\s+"JLCPCB Prices"\s+"([^"]+)"', content)
                    if lcsc_match:
                        lcsc = lcsc_match.group(1).upper().strip()
                        lib_data[lcsc] = {
                            "stock_type": st_match.group(1) if st_match else "Extended",
                            "prices_str": pr_match.group(1) if pr_match else ""
                        }
                except Exception:
                    pass

    total_component_cost = 0.0
    basic_types = 0
    extended_types = 0
    unmapped_types = 0
    
    print(f"\n{'Comment':<25} | {'LCSC':<8} | {'Qty (total)':<12} | {'Class':<9} | {'Est. Unit':<10} | {'Subtotal'}")
    print("-" * 85)
    
    for key, refs in sorted(grouped.items(), key=lambda x: x[0][0]):
        val, fp, lcsc = key
        qty_per_board = len(refs)
        total_qty = qty_per_board * num_boards
        
        unit_price = 0.0
        stock_class = "Unknown"
        
        if lcsc in lib_data:
            stock_class = lib_data[lcsc]["stock_type"]
            prices_str = lib_data[lcsc]["prices_str"]
            unit_price = get_price_for_quantity(prices_str, total_qty)
            
            if stock_class == "Basic":
                basic_types += 1
            else:
                extended_types += 1
        else:
            unmapped_types += 1
            
        subtotal = total_qty * unit_price
        total_component_cost += subtotal
        
        price_display = f"${unit_price:.4f}" if unit_price > 0 else "N/A"
        subtotal_display = f"${subtotal:.2f}" if subtotal > 0 else "N/A"
        
        print(f"{val[:25]:<25} | {lcsc:<8} | {qty_per_board:<3} ({total_qty:<3} pcs) | {stock_class:<9} | {price_display:<10} | {subtotal_display}")
        
    extended_setup_fee = extended_types * 3.00
    grand_total = total_component_cost + extended_setup_fee
    
    print("-" * 85)
    print(f"[✓] Classification: {basic_types} Basic type(s), {extended_types} Extended type(s), {unmapped_types} Unmapped type(s).")
    print(f"[💰] Total SMT Components:  ${total_component_cost:.2f} USD")
    print(f"[💰] Extended Parts Setup:   ${extended_setup_fee:.2f} USD (Estimated: {extended_types} x $3.00)")
    print(f"---------------------------------------------------------------------")
    print(f"[🚀] ESTIMATED PARTS & SETUP: ${grand_total:.2f} USD (~${(grand_total / num_boards):.2f} USD per board)")
    print("---------------------------------------------------------------------\n")
