#!/usr/bin/env python3
import sys
import re
import argparse

from .config import ensure_config_exists, init_kiflux, set_library_path, TEMP_DIR
from .heuristics import clean_name
from .lib_manager import (
    import_single_component,
    remove_component,
    rename_component,
    list_components,
    show_info,
    open_datasheet,
    check_library,
    rebuild_consolidated_library,
    update_all_components,
    find_name_by_lcsc,
    search_components
)
from .bom_exporter import export_bom_and_cpl

def parse_args():
    parser = argparse.ArgumentParser(description="KiFlux: Smart component manager and BOM/CPL exporter for KiCad.")
    
    # Import Group
    parser.add_argument("--lcsc", help="LCSC/JLCPCB Part Number (e.g. C2040) to import a new component.")
    parser.add_argument("--name", help="Custom name for the component to be imported. If omitted, uses the automatically generated name.")
    
    # Special Actions
    parser.add_argument("--remove", help="Component name or LCSC code (e.g. C2040) to be removed.")
    parser.add_argument("--rename-from", help="Current component name or LCSC code (e.g. C2040) to be renamed.")
    parser.add_argument("--rename-to", help="New name for the component (requires --rename-from).")
    parser.add_argument("--rename", help="Component name or LCSC code (e.g. C2040) to be automatically renamed based on LCSC metadata.")
    
    parser.add_argument("--rebuild", action="store_true", help="Rebuilds the consolidated library file from individual symbols.")
    
    # Batch Updates
    parser.add_argument("--update", action="store_true", help="Run batch update to sync footprints, 3D files, and JLCPCB pricing/stock properties.")
    
    # Administration & Query
    parser.add_argument("--list", action="store_true", help="List all registered components in the library inventory.")
    parser.add_argument("--info", help="Display complete details for a component or LCSC code.")
    parser.add_argument("--datasheet", help="Open the official component datasheet PDF in your default browser.")
    parser.add_argument("--check", action="store_true", help="Run library integrity audit.")
    parser.add_argument("--set-path", help="Change the library root directory and reconfigure KiCad globally.")
    
    # Onboarding Wizard
    parser.add_argument("--init", action="store_true", help="Run the guided interactive setup helper for KiFlux.")
    
    # Busca de componentes
    parser.add_argument("--search", help="Search the JLCPCB SMT Library for components matching the keyword.")
    parser.add_argument("-b", "--basic", action="store_true", help="Filter search results to show only Basic Parts.")
    parser.add_argument("-e", "--extended", action="store_true", help="Filter search results to show only Extended Parts.")
    parser.add_argument("-s", "--in-stock", action="store_true", help="Filter search results to show only in-stock components.")
    
    # BOM & CPL Export
    parser.add_argument("--bom", nargs="?", const=".", help="Generate BOM and CPL files for the project in the specified path (defaults to current folder).")
    parser.add_argument("--bom-output", help="Target directory to save the generated BOM/CPL CSV files.")
    
    # Positional Arguments
    parser.add_argument("positional_args", nargs="*", help="Quickstart: kiflux <LCSC_ID> [CUSTOM_NAME]")
    
    return parser.parse_args()
 
def main():
    # Garante a existência do arquivo de configuração e retorna o contexto de paths
    paths = ensure_config_exists()
    
    args = parse_args()
    
    # Mapeamento de termos posicionais amigáveis
    if args.positional_args:
        cmd = args.positional_args[0].lower()
        if cmd == "list":
            args.list = True
            args.positional_args = args.positional_args[1:]
        elif cmd == "check":
            args.check = True
            args.positional_args = args.positional_args[1:]
        elif cmd == "init":
            args.init = True
            args.positional_args = args.positional_args[1:]
        elif cmd == "update":
            args.update = True
            args.positional_args = args.positional_args[1:]
        elif cmd == "search":
            if len(args.positional_args) > 1:
                args.search = " ".join(args.positional_args[1:])
            else:
                print("[!] Error: You must specify a keyword to search. e.g. 'kiflux search capacitor 0402'")
                sys.exit(1)
            args.positional_args = []
        elif cmd == "directory" or cmd == "path":
            if len(args.positional_args) > 1:
                args.set_path = args.positional_args[1]
                args.positional_args = []
            else:
                print("[!] Error: You must specify the directory path. e.g. 'kiflux directory /new/path'")
                sys.exit(1)
        elif cmd == "info":
            if len(args.positional_args) > 1:
                args.info = args.positional_args[1]
                args.positional_args = []
            else:
                print("[!] Error: You must specify a component name or LCSC code. e.g. 'kiflux info C2040'")
                sys.exit(1)
        elif cmd == "datasheet":
            if len(args.positional_args) > 1:
                args.datasheet = args.positional_args[1]
                args.positional_args = []
            else:
                print("[!] Error: You must specify a component name or LCSC code. e.g. 'kiflux datasheet C2040'")
                sys.exit(1)
        elif cmd == "bom":
            if len(args.positional_args) > 1:
                args.bom = args.positional_args[1]
                if len(args.positional_args) > 2:
                    args.bom_output = args.positional_args[2]
                else:
                    args.bom_output = None
                args.positional_args = []
            else:
                args.bom = "."
                args.bom_output = None
                args.positional_args = []
        elif cmd == "install":
            if len(args.positional_args) > 1:
                target = args.positional_args[1]
                # Se o target bater na regex CXXXX, removemos "install" e deixamos seguir o fluxo padrao de importacao individual
                if re.match(r'^C\d+$', target.upper().strip()):
                    args.positional_args = args.positional_args[1:]
                else:
                    # Caso contrario, tratamos como kit
                    from .kits import install_kit
                    install_kit(target, paths)
                    sys.exit(0)
            else:
                print("[!] Error: You must specify a component LCSC code or a kit name to install. e.g. 'kiflux install C2040' or 'kiflux install master'")
                sys.exit(1)
        elif cmd == "kit" or cmd == "kits":
            from .kits import list_kits, show_kit, install_kit
            if len(args.positional_args) > 1:
                subcmd = args.positional_args[1].lower()
                if subcmd == "list":
                    list_kits()
                    sys.exit(0)
                elif subcmd == "install":
                    if len(args.positional_args) > 2:
                        install_kit(args.positional_args[2], paths)
                        sys.exit(0)
                    else:
                        print("[!] Error: You must specify a kit name to install. e.g. 'kiflux kit install rp2040-support'")
                        sys.exit(1)
                elif subcmd == "show":
                    if len(args.positional_args) > 2:
                        show_kit(args.positional_args[2])
                        sys.exit(0)
                    else:
                        print("[!] Error: You must specify a kit name to show. e.g. 'kiflux kit show rp2040-support'")
                        sys.exit(1)
                else:
                    install_kit(args.positional_args[1], paths)
                    sys.exit(0)
            else:
                list_kits()
                sys.exit(0)
                
    if args.init:
        init_kiflux(force=True)
        sys.exit(0)
    
    # Trata uso rápido posicional padrão
    if args.positional_args:
        if not args.lcsc and not args.remove and not args.rename_from and not args.rebuild and not args.rename and not args.bom and not args.update and not args.search:
            pos_args = args.positional_args
            if re.match(r'^C\d+$', pos_args[0].upper().strip()):
                if len(pos_args) == 1:
                    import_single_component(pos_args[0], paths=paths, temp_dir=TEMP_DIR)
                    sys.exit(0)
                elif len(pos_args) == 2 and not re.match(r'^C\d+$', pos_args[1].upper().strip()):
                    import_single_component(pos_args[0], pos_args[1], paths=paths, temp_dir=TEMP_DIR)
                    sys.exit(0)
                else:
                    print(f"[*] Batch importing {len(pos_args)} components...")
                    success_count = 0
                    for lcsc_code in pos_args:
                        if re.match(r'^C\d+$', lcsc_code.upper().strip()):
                            if import_single_component(lcsc_code, paths=paths, temp_dir=TEMP_DIR):
                                success_count += 1
                        else:
                            print(f"[!] Skipping invalid argument '{lcsc_code}' in batch import.")
                    print(f"\n[+] Batch import completed: {success_count} of {len(pos_args)} components imported successfully!")
                    sys.exit(0)
            else:
                print(f"[!] Error: First argument '{pos_args[0]}' must be a valid LCSC Part Number (e.g. C2040).")
                sys.exit(1)
                
    if args.search:
        part_type = "base" if args.basic else ("expand" if args.extended else None)
        search_components(args.search, part_type=part_type, in_stock_only=args.in_stock)
        sys.exit(0)
                
    if args.bom:
        export_bom_and_cpl(args.bom, args.bom_output, paths=paths)
        sys.exit(0)
        
    if args.list:
        list_components(paths)
        sys.exit(0)
        
    if args.info:
        show_info(args.info, paths)
        sys.exit(0)
        
    if args.datasheet:
        open_datasheet(args.datasheet, paths)
        sys.exit(0)
        
    if args.check:
        check_library(paths)
        sys.exit(0)
        
    if args.set_path:
        set_library_path(args.set_path)
        sys.exit(0)
        
    if args.rebuild:
        rebuild_consolidated_library(paths)
        sys.exit(0)
        
    if args.update:
        targets = args.positional_args if args.positional_args else None
        update_all_components(paths, TEMP_DIR, targets)
        sys.exit(0)
        
    if args.remove:
        target = args.remove
        if re.match(r'^C\d+$', target.upper().strip()):
            resolved_name = find_name_by_lcsc(target, paths)
            if resolved_name:
                print(f"[*] LCSC ID '{target}' resolved to component '{resolved_name}'")
                target = resolved_name
            else:
                print(f"[!] Could not find any registered component with LCSC ID '{target}'")
                sys.exit(1)
        remove_component(target, paths)
        sys.exit(0)
        
    if args.rename_from or args.rename_to:
        if not args.rename_from or not args.rename_to:
            print("[!] Error: You must pass both --rename-from and --rename-to parameters.")
            sys.exit(1)
            
        target_from = args.rename_from
        if re.match(r'^C\d+$', target_from.upper().strip()):
            resolved_name = find_name_by_lcsc(target_from, paths)
            if resolved_name:
                print(f"[*] LCSC ID '{target_from}' resolved to component '{resolved_name}'")
                target_from = resolved_name
            else:
                print(f"[!] Could not find any registered component with LCSC ID '{target_from}'")
                sys.exit(1)
        rename_component(target_from, args.rename_to, paths)
        sys.exit(0)
        
    if args.rename:
        target = args.rename
        lcsc_id = ""
        
        if re.match(r'^C\d+$', target.upper().strip()):
            lcsc_id = target.upper().strip()
            resolved_name = find_name_by_lcsc(lcsc_id, paths)
            if not resolved_name:
                print(f"[!] Error: No component registered with LCSC ID '{lcsc_id}'.")
                sys.exit(1)
            target = resolved_name
        else:
            sym_path = os.path.join(paths.sym_individual_dir, f"{target}.kicad_sym")
            if not os.path.exists(sym_path):
                print(f"[!] Error: Component '{target}' not found at symbols/{target}.kicad_sym")
                sys.exit(1)
            with open(sym_path, "r", encoding="utf-8") as f:
                content = f.read()
            lcsc_match = re.search(r'\(property\s+"LCSC Part"\s+"([^"]+)"', content)
            if not lcsc_match:
                print(f"[!] Error: Could not extract LCSC Part number from local symbol metadata.")
                sys.exit(1)
            lcsc_id = lcsc_match.group(1).upper().strip()
            
        print(f"[*] Fetching metadata for LCSC code '{lcsc_id}'...")
        jlc_info = fetch_jlcpcb_part_data(lcsc_id)
        run_easyeda2kicad(lcsc_id, TEMP_DIR)
        value, manufacturer, package = extract_properties_from_temp(TEMP_DIR)
        
        if not value:
            print("[!] Error: Could not obtain metadata from LCSC API.")
            sys.exit(1)
            
        temp_sym_path = os.path.join(TEMP_DIR, "Maker.kicad_sym")
        temp_sym_content = ""
        if os.path.exists(temp_sym_path):
            with open(temp_sym_path, "r", encoding="utf-8") as f:
                temp_sym_content = f.read()
                
        jlc_desc = jlc_info.get("describe") if jlc_info else None
        new_name = generate_standardized_name(value, manufacturer, package, temp_sym_content, jlc_desc)
        print(f"[+] LCSC Metadata: Value={value}, Manufacturer={manufacturer}, Package={package}")
        print(f"[+] Standardized Name generated: '{new_name}'")
        
        confirm = input(f"\nDo you want to confirm the automatic renaming to '{new_name}'? [S(yes) / n(no)]: ").strip().lower()
        if confirm not in ['', 's', 'yes']:
            print("[!] Automatic renaming canceled.")
            if os.path.exists(TEMP_DIR):
                shutil.rmtree(TEMP_DIR)
            sys.exit(0)
            
        # Renomeia gravando dados atualizados do jlc_info
        process_symbol(lcsc_id, new_name, TEMP_DIR, paths, jlc_info)
        process_footprint(lcsc_id, new_name, target, TEMP_DIR, paths)
        rename_component(target, new_name, paths)
        
        if os.path.exists(TEMP_DIR):
            shutil.rmtree(TEMP_DIR)
        sys.exit(0)
        
    if args.lcsc:
        import_single_component(args.lcsc, args.name, paths=paths, temp_dir=TEMP_DIR)
        sys.exit(0)
        
    print("[!] No action specified. Use --help to view available commands.")
    sys.exit(1)

if __name__ == "__main__":
    main()
