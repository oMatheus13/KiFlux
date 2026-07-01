#!/usr/bin/env python3
import os
import sys
import re
import shutil
import subprocess
import argparse
import json
import csv

# Configurações de caminhos e arquivo de configuração
CONFIG_DIR = os.path.expanduser("~/.config/kiflux")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
OLD_CONFIG_DIR = os.path.expanduser("~/.config/maker")
OLD_CONFIG_FILE = os.path.join(OLD_CONFIG_DIR, "config.json")
DEFAULT_LIB_ROOT = "/media/omatheus/oMatheusDisk2/KiCad/Maker"

def load_config():
    # Tenta carregar o config do KiFlux
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("lib_root", DEFAULT_LIB_ROOT)
        except Exception:
            pass
    # Fallback de migração caso exista o config antigo
    if os.path.exists(OLD_CONFIG_FILE):
        try:
            with open(OLD_CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                lib_root = data.get("lib_root", DEFAULT_LIB_ROOT)
                save_config(lib_root)  # Migra para a nova pasta
                return lib_root
        except Exception:
            pass
    return DEFAULT_LIB_ROOT

def save_config(lib_root):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump({"lib_root": lib_root}, f, indent=4)
    except Exception as e:
        print(f"[!] Erro ao salvar configuração: {e}")

LIB_ROOT = load_config()
SYM_LIB_FILE = os.path.join(LIB_ROOT, "Maker.kicad_sym")
SYM_INDIVIDUAL_DIR = os.path.join(LIB_ROOT, "symbols")
FP_DIR = os.path.join(LIB_ROOT, "Maker.pretty")
DIR_3D = os.path.join(LIB_ROOT, "3d")
TEMP_DIR = "/tmp/easyeda_import_temp"

def parse_args():
    parser = argparse.ArgumentParser(description="KiFlux: Gerenciador inteligente de componentes e gerador de BOM/CPL para KiCad.")
    
    # Grupo de Importação
    parser.add_argument("--lcsc", help="Part Number da LCSC/JLCPCB (ex: C2040) para importar um novo componente.")
    parser.add_argument("--name", help="Nome personalizado do componente a ser importado. Se omitido, usa o nome gerado automaticamente.")
    
    # Ações Especiais
    parser.add_argument("--remove", help="Nome do componente ou código LCSC (ex: C2040) a ser removido.")
    parser.add_argument("--rename-from", help="Nome do componente atual ou código LCSC (ex: C2040) que deseja renomear.")
    parser.add_argument("--rename-to", help="Novo nome do componente (requer --rename-from).")
    parser.add_argument("--rename", help="Nome do componente ou código LCSC (ex: C2040) a ser renomeado automaticamente com base nos metadados da LCSC.")
    
    parser.add_argument("--rebuild", action="store_true", help="Apenas reconstrói a biblioteca consolidada Maker.kicad_sym a partir dos arquivos individuais.")
    
    # Consultas e Administração
    parser.add_argument("--list", action="store_true", help="Lista todos os componentes cadastrados no inventário da biblioteca.")
    parser.add_argument("--info", help="Exibe informações completas de um componente ou código LCSC (ex: C2040).")
    parser.add_argument("--datasheet", help="Abre o link do datasheet do componente ou código LCSC (ex: C2040) no navegador.")
    parser.add_argument("--check", action="store_true", help="Executa auditoria de integridade da biblioteca.")
    parser.add_argument("--set-path", help="Altera o diretório raiz da biblioteca Maker e reconfigura o KiCad globalmente.")
    
    # Exportação de BOM e CPL
    parser.add_argument("--bom", nargs="?", const=".", help="Gera o arquivo BOM e CPL para a JLCPCB a partir do projeto informado (diretório padrão: atual).")
    parser.add_argument("--bom-output", help="Diretório de destino para salvar os arquivos CSV gerados pela exportação de BOM/CPL.")
    
    # Argumentos posicionais para compatibilidade de uso rápido (kiflux C2040 [NOME])
    parser.add_argument("positional_args", nargs="*", help="Uso rápido: kiflux <LCSC_ID> [NOME_PERSONALIZADO]")
    
    return parser.parse_args()

def clean_name(name):
    if not name:
        return ""
    name = re.sub(r'[^\w\-]', '_', name)
    return name.upper().strip().strip('_')

def run_easyeda2kicad(lcsc):
    if os.path.exists(TEMP_DIR):
        shutil.rmtree(TEMP_DIR)
    os.makedirs(TEMP_DIR, exist_ok=True)
    
    cmd = [
        "easyeda2kicad",
        "--lcsc_id", lcsc,
        "--symbol",
        "--footprint",
        "--3d",
        "--output", os.path.join(TEMP_DIR, "Maker.kicad_sym"),
        "--overwrite"
    ]
    
    print(f"[*] Executando: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print("[!] Erro ao executar easyeda2kicad:")
        print(result.stderr)
        sys.exit(1)
    
    print(result.stdout)

def extract_properties_from_temp():
    temp_sym_path = os.path.join(TEMP_DIR, "Maker.kicad_sym")
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

def process_symbol(lcsc, final_name):
    temp_sym_path = os.path.join(TEMP_DIR, "Maker.kicad_sym")
    if not os.path.exists(temp_sym_path):
        print("[!] Arquivo de símbolo temporário não foi gerado.")
        sys.exit(1)
        
    with open(temp_sym_path, "r", encoding="utf-8") as f:
        content = f.read()
        
    match = re.search(r'\(symbol "([^"]+)"', content)
    if not match:
        print("[!] Não foi possível encontrar a definição do símbolo no arquivo temporário.")
        sys.exit(1)
        
    orig_name = match.group(1)
    comp_name = clean_name(final_name)
    
    print(f"[*] Símbolo original: {orig_name} -> Nome final: {comp_name}")
    
    content = content.replace(f'(symbol "{orig_name}"', f'(symbol "{comp_name}"')
    content = re.sub(r'\(symbol "' + re.escape(orig_name) + r'(_\d+_\d+)"', r'(symbol "' + comp_name + r'\1"', content)
    content = re.sub(r'\(symbol "' + re.escape(orig_name) + r'(_\d+)"', r'(symbol "' + comp_name + r'\1"', content)
    
    content = re.sub(
        r'(\(property\s+"Value"\s+)"[^"]+"',
        f'\\1"{comp_name}"',
        content
    )
    
    content = re.sub(
        r'(\(property\s+"Footprint"\s+)"[^"]+"',
        f'\\1"Maker:{comp_name}"',
        content
    )
    
    content = re.sub(r'\s*\(property\s+"LCSC Part"[\s\S]*?\n\s*\)', '', content)
    content = re.sub(r'\s*\(property\s+"JLCPCB Part #"\s*[\s\S]*?\n\s*\)', '', content)
    
    lcsc_properties = (
        f'    (property "LCSC Part" "{lcsc}" (id 6) (at 0 0 0) (effects (font (size 1.27 1.27)) hide))\n'
        f'    (property "JLCPCB Part #" "{lcsc}" (id 7) (at 0 0 0) (effects (font (size 1.27 1.27)) hide))\n'
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
        print("[!] Erro ao extrair o bloco do símbolo após modificação.")
        sys.exit(1)
        
    os.makedirs(SYM_INDIVIDUAL_DIR, exist_ok=True)
    individual_sym_file = os.path.join(SYM_INDIVIDUAL_DIR, f"{comp_name}.kicad_sym")
    
    individual_content = (
        "(kicad_symbol_lib\n"
        "  (version 20231120)\n"
        "  (generator kicad_symbol_editor)\n\n"
        f"  {symbol_block}\n"
        ")\n"
    )
    
    with open(individual_sym_file, "w", encoding="utf-8") as f:
        f.write(individual_content)
        
    print(f"[+] Símbolo individual salvo em: symbols/{comp_name}.kicad_sym")
    return comp_name, orig_name

def rebuild_consolidated_library():
    print("[*] Reconstruindo biblioteca consolidada Maker.kicad_sym...")
    if not os.path.exists(SYM_INDIVIDUAL_DIR):
        os.makedirs(SYM_INDIVIDUAL_DIR, exist_ok=True)
        
    consolidated_content = (
        "(kicad_symbol_lib\n"
        "  (version 20231120)\n"
        "  (generator kicad_symbol_editor)\n"
    )
    
    files = sorted([f for f in os.listdir(SYM_INDIVIDUAL_DIR) if f.endswith(".kicad_sym")])
    
    for filename in files:
        file_path = os.path.join(SYM_INDIVIDUAL_DIR, filename)
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
            
        blocks = extract_all_symbol_blocks(content)
        for block in blocks:
            indented_block = "\n".join("  " + line if line.strip() else "" for line in block.split("\n"))
            indented_block = indented_block.lstrip()
            consolidated_content += f"\n  {indented_block}\n"
            
    consolidated_content += ")\n"
    
    with open(SYM_LIB_FILE, "w", encoding="utf-8") as f:
        f.write(consolidated_content)
        
    print(f"[+] Biblioteca consolidada reconstruída com {len(files)} componente(s)!")

def process_footprint(lcsc, comp_name, orig_name):
    temp_fp_dir = os.path.join(TEMP_DIR, "Maker.pretty")
    if not os.path.exists(temp_fp_dir):
        print("[!] Pasta de footprints temporária não existe.")
        sys.exit(1)
        
    files = [f for f in os.listdir(temp_fp_dir) if f.endswith(".kicad_mod")]
    if not files:
        print("[!] Nenhum arquivo .kicad_mod gerado.")
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
    
    target_3d_wrl = os.path.join(DIR_3D, f"{comp_name}.wrl")
    
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
        
    os.makedirs(FP_DIR, exist_ok=True)
    target_mod_file = os.path.join(FP_DIR, f"{comp_name}.kicad_mod")
    
    with open(target_mod_file, "w", encoding="utf-8") as f:
        f.write(content)
        
    print(f"[+] Footprint '{comp_name}' salvo com sucesso em Maker.pretty!")
    return orig_fp_name

def process_3d(comp_name, orig_fp_name):
    temp_3d_dir = os.path.join(TEMP_DIR, "Maker.3dshapes")
    if not os.path.exists(temp_3d_dir):
        print("[*] Nenhum modelo 3D foi gerado pelo easyeda2kicad.")
        return
        
    os.makedirs(DIR_3D, exist_ok=True)
    
    wrl_src = os.path.join(temp_3d_dir, f"{orig_fp_name}.wrl")
    step_src = os.path.join(temp_3d_dir, f"{orig_fp_name}.step")
    
    if os.path.exists(wrl_src):
        shutil.copy(wrl_src, os.path.join(DIR_3D, f"{comp_name}.wrl"))
        print(f"[+] Modelo 3D WRL '{comp_name}.wrl' salvo em Maker/3d/")
        
    if os.path.exists(step_src):
        shutil.copy(step_src, os.path.join(DIR_3D, f"{comp_name}.step"))
        print(f"[+] Modelo 3D STEP '{comp_name}.step' salvo em Maker/3d/")

def find_name_by_lcsc(lcsc_id):
    lcsc_id = lcsc_id.upper().strip()
    if not os.path.exists(SYM_INDIVIDUAL_DIR):
        return None
    for filename in os.listdir(SYM_INDIVIDUAL_DIR):
        if filename.endswith(".kicad_sym"):
            filepath = os.path.join(SYM_INDIVIDUAL_DIR, filename)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
                if re.search(r'\(property\s+"(?:LCSC Part|JLCPCB Part #)"\s+"' + re.escape(lcsc_id) + r'"', content):
                    return filename.replace(".kicad_sym", "")
            except Exception as e:
                print(f"[!] Erro ao ler {filename}: {e}")
    return None

def generate_standardized_name(value, manufacturer, package, temp_sym_content=None):
    # Normaliza fabricante
    mfr_clean = manufacturer.upper()
    if "RASPBERRY" in mfr_clean:
        mfr = "RPI"
    elif "SAMSUNG" in mfr_clean:
        mfr = "SAMSUNG"
    elif "YAGEO" in mfr_clean:
        mfr = "YAGEO"
    elif "UNIROYAL" in mfr_clean or "ROYALOHM" in mfr_clean:
        mfr = "UNIROYAL"
    elif "WCH" in mfr_clean or "NANJING QINHENG" in mfr_clean:
        mfr = "WCH"
    elif "JIANGSU CHANGJING" in mfr_clean or "JCET" in mfr_clean or "CHANGDIAN" in mfr_clean:
        mfr = "CJ"
    elif "AMS" in mfr_clean or "ADVANCED MONOLITHIC" in mfr_clean:
        mfr = "AMS"
    else:
        words = re.findall(r'[A-Z0-9]+', mfr_clean)
        mfr = words[0] if words else "GENERIC"
        
    # Normaliza encapsulamento (package)
    pkg_clean = package.upper()
    pkg_clean = pkg_clean.replace("METRIC", "").replace("INCH", "").replace("-", "_")
    pkg_match = re.search(r'(0805|0603|0402|1206|SOT_223|SOT223|QFN_56|QFN56|SOIC_16|SOIC16|TSSOP_8|TSSOP8|LQFP_48|LQFP48|QFN_80|QFN80|QFN_20|QFN20)', pkg_clean)
    if pkg_match:
        pkg = pkg_match.group(1).replace("_", "")
    else:
        pkg = re.sub(r'[^A-Z0-9]', '', pkg_clean.split('_')[0])
        if not pkg:
            pkg = "GENERIC"

    # Normaliza valor
    val_clean = value.upper().strip()
    val_clean = re.sub(r'_C\d+$', '', val_clean)
    
    # Coleta descrição e palavras-chave
    metadata_text = val_clean
    if temp_sym_content:
        keywords_match = re.search(r'\(property\s+"ki_keywords"\s+"([^"]+)"', temp_sym_content)
        desc_match = re.search(r'\(property\s+"ki_description"\s+"([^"]+)"', temp_sym_content)
        if keywords_match: metadata_text += " " + keywords_match.group(1).upper()
        if desc_match: metadata_text += " " + desc_match.group(1).upper()

    # Regex robustas para valores de passivos
    cap_value_pattern = r'^\d+(\.\d+)?\s*(P|N|U|µ|M|F)+F?$'
    res_value_pattern = r'^\d+(\.\d+)?\s*(R|K|M|OHM)+$'
    res_value_inline_pattern = r'^\d+[RKM]\d*$'

    is_capacitor = False
    is_resistor = False

    if "CAPACITOR" in metadata_text:
        is_capacitor = True
    elif "RESISTOR" in metadata_text:
        is_resistor = True
    elif re.match(cap_value_pattern, val_clean):
        is_capacitor = True
    elif re.match(res_value_pattern, val_clean) or re.match(res_value_inline_pattern, val_clean):
        is_resistor = True

    if is_capacitor:
        val = val_clean
        if val.startswith("C") and len(val) > 1 and val[1].isdigit():
            val = val[1:]
        val = val.replace("NF", "n").replace("UF", "u").replace("PF", "p").replace("FF", "f").replace("F", "")
        val = val.lower().strip()
        return f"C_{pkg}_{val}_{mfr}"
        
    if is_resistor:
        val = val_clean
        if val.startswith("R") and len(val) > 1 and val[1].isdigit():
            val = val[1:]
        val = val.replace("OHM", "").replace("R", "").replace("K", "k").replace("M", "m")
        val = val.lower().strip()
        return f"R_{pkg}_{val}_{mfr}"

    category = "IC"
    # Fallback seguro para CIs de microcontroladores conhecidos
    mcu_prefixes = [
        "RP2", "ESP32", "ESP8266", "ESP_C", "ESP_S", "STM32", "GD32", "ATMEGA", "ATTINY", 
        "NRF5", "SAMD", "LPC1", "LPC8", "LPC5", "MK2", "MKL", "MSP430", "TMS320", "PIC1", "CH5"
    ]
    
    if any(k in metadata_text for k in ["MICROCONTROLLER", "MCU", "PROCESSOR"]) or any(mcu in val_clean for mcu in mcu_prefixes):
        category = "MCU"
    elif any(k in metadata_text for k in ["REGULATOR", "LDO", "VOLTAGE REFERENCE"]) or "AMS1117" in val_clean or "LM78" in val_clean:
        category = "REG"
    elif any(k in metadata_text for k in ["DIODE", "RECTIFIER", "ZENER"]) or val_clean.startswith("1N4"):
        category = "DIODE"
    elif any(k in metadata_text for k in ["TRANSISTOR", "MOSFET", "IGBT", "BJT"]):
        category = "TRANS"
        
    model = clean_name(val_clean)
    return f"{category}_{model}_{pkg}_{mfr}"

def import_single_component(lcsc, custom_name=None):
    lcsc = lcsc.upper().strip()
    print(f"\n=== Iniciando importação do componente {lcsc} ===")
    run_easyeda2kicad(lcsc)
    value, manufacturer, package = extract_properties_from_temp()
    
    if not value:
        print(f"[!] Erro: Não foi possível obter os metadados da LCSC para o código {lcsc}.")
        return False
        
    temp_sym_path = os.path.join(TEMP_DIR, "Maker.kicad_sym")
    temp_sym_content = ""
    if os.path.exists(temp_sym_path):
        with open(temp_sym_path, "r", encoding="utf-8") as f:
            temp_sym_content = f.read()
            
    final_name = custom_name if custom_name else generate_standardized_name(value, manufacturer, package, temp_sym_content)
    if not final_name:
        print("[!] Erro: Nome do componente ficou em branco.")
        return False
        
    print(f"\n[+] Componente identificado na LCSC:")
    print(f"    Código LCSC:    {lcsc}")
    print(f"    Valor original: {value}")
    print(f"    Fabricante:     {manufacturer}")
    print(f"    Encapsulamento: {package}")
    print(f"    Nome sugerido:  {final_name}")
    
    confirm = input(f"\nDeseja confirmar a importação do componente como '{final_name}'? [S(sim) / n(não) / r(digitar nome personalizado)]: ").strip()
    confirm_lower = confirm.lower()
    
    if confirm_lower.startswith('r'):
        parts = confirm.split(maxsplit=1)
        if len(parts) > 1:
            final_name = clean_name(parts[1])
            print(f"[*] Prosseguindo com o nome personalizado: '{final_name}'")
        else:
            custom_input = input("Digite o nome personalizado desejado: ").strip()
            if not custom_input:
                print("[!] Nome inválido. Cancelando importação.")
                if os.path.exists(TEMP_DIR):
                    shutil.rmtree(TEMP_DIR)
                return False
            final_name = clean_name(custom_input)
            print(f"[*] Prosseguindo com o nome personalizado: '{final_name}'")
            
    elif confirm_lower not in ['', 's', 'sim']:
        print(f"[!] Importação de {lcsc} cancelada pelo usuário.")
        if os.path.exists(TEMP_DIR):
            shutil.rmtree(TEMP_DIR)
        return False
        
    comp_name, orig_name = process_symbol(lcsc, final_name)
    orig_fp_name = process_footprint(lcsc, comp_name, orig_name)
    process_3d(comp_name, orig_fp_name)
    rebuild_consolidated_library()
    
    if os.path.exists(TEMP_DIR):
        shutil.rmtree(TEMP_DIR)
        
    print(f"=== Importação concluída com sucesso! Componente: {comp_name} ===")
    return True

def remove_component(comp_name):
    comp_name = clean_name(comp_name)
    print(f"[*] Removendo componente '{comp_name}'...")
    
    sym_path = os.path.join(SYM_INDIVIDUAL_DIR, f"{comp_name}.kicad_sym")
    if os.path.exists(sym_path):
        os.remove(sym_path)
        print(f"  [-] Símbolo individual removido: symbols/{comp_name}.kicad_sym")
    else:
        print(f"  [!] Símbolo individual não encontrado em: symbols/{comp_name}.kicad_sym")
        
    fp_path = os.path.join(FP_DIR, f"{comp_name}.kicad_mod")
    if os.path.exists(fp_path):
        os.remove(fp_path)
        print(f"  [-] Footprint removido: Maker.pretty/{comp_name}.kicad_mod")
    else:
        print(f"  [!] Footprint não encontrado em: Maker.pretty/{comp_name}.kicad_mod")
        
    wrl_path = os.path.join(DIR_3D, f"{comp_name}.wrl")
    step_path = os.path.join(DIR_3D, f"{comp_name}.step")
    
    if os.path.exists(wrl_path):
        os.remove(wrl_path)
        print(f"  [-] Modelo 3D WRL removido: 3d/{comp_name}.wrl")
    if os.path.exists(step_path):
        os.remove(step_path)
        print(f"  [-] Modelo 3D STEP removido: 3d/{comp_name}.step")
        
    rebuild_consolidated_library()
    print(f"[+] Componente '{comp_name}' removido com sucesso!")

def rename_component(old_name, new_name):
    old_name = clean_name(old_name)
    new_name = clean_name(new_name)
    
    if old_name == new_name:
        print("[!] Erro: O nome antigo e o novo são idênticos.")
        sys.exit(1)
        
    print(f"[*] Renomeando componente de '{old_name}' para '{new_name}'...")
    
    old_sym_path = os.path.join(SYM_INDIVIDUAL_DIR, f"{old_name}.kicad_sym")
    new_sym_path = os.path.join(SYM_INDIVIDUAL_DIR, f"{new_name}.kicad_sym")
    
    if os.path.exists(old_sym_path):
        with open(old_sym_path, "r", encoding="utf-8") as f:
            content = f.read()
            
        content = content.replace(f'(symbol "{old_name}"', f'(symbol "{new_name}"')
        content = re.sub(r'\(symbol "' + re.escape(old_name) + r'(_\d+_\d+)"', r'(symbol "' + new_name + r'\1"', content)
        content = re.sub(r'\(symbol "' + re.escape(old_name) + r'(_\d+)"', r'(symbol "' + new_name + r'\1"', content)
        
        content = re.sub(
            r'(\(property\s+"Value"\s+)"[^"]+"',
            f'\\1"{new_name}"',
            content
        )
        
        content = re.sub(
            r'(\(property\s+"Footprint"\s+)"[^"]+"',
            f'\\1"Maker:{new_name}"',
            content
        )
        
        with open(new_sym_path, "w", encoding="utf-8") as f:
            f.write(content)
            
        os.remove(old_sym_path)
        print(f"  [~] Símbolo individual atualizado: symbols/{new_name}.kicad_sym")
    else:
        print(f"  [!] Símbolo antigo não encontrado em: symbols/{old_name}.kicad_sym (pulando)")
        
    old_fp_path = os.path.join(FP_DIR, f"{old_name}.kicad_mod")
    new_fp_path = os.path.join(FP_DIR, f"{new_name}.kicad_mod")
    
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
        
        old_3d_wrl = os.path.join(DIR_3D, f"{old_name}.wrl")
        new_3d_wrl = os.path.join(DIR_3D, f"{new_name}.wrl")
        content = content.replace(f'"{old_3d_wrl}"', f'"{new_3d_wrl}"')
        
        with open(new_fp_path, "w", encoding="utf-8") as f:
            f.write(content)
            
        os.remove(old_fp_path)
        print(f"  [~] Footprint atualizado: Maker.pretty/{new_name}.kicad_mod")
    else:
        print(f"  [!] Footprint antigo não encontrado em: Maker.pretty/{old_name}.kicad_mod (pulando)")
        
    old_wrl_path = os.path.join(DIR_3D, f"{old_name}.wrl")
    new_wrl_path = os.path.join(DIR_3D, f"{new_name}.wrl")
    old_step_path = os.path.join(DIR_3D, f"{old_name}.step")
    new_step_path = os.path.join(DIR_3D, f"{new_name}.step")
    
    if os.path.exists(old_wrl_path):
        os.rename(old_wrl_path, new_wrl_path)
        print(f"  [~] Modelo 3D WRL renomeado para: 3d/{new_name}.wrl")
        
    if os.path.exists(old_step_path):
        os.rename(old_step_path, new_step_path)
        print(f"  [~] Modelo 3D STEP renomeado para: 3d/{new_name}.step")
        
    rebuild_consolidated_library()
    print(f"[+] Componente renomeado de '{old_name}' para '{new_name}' com sucesso!")

def list_components():
    print(f"\n=== Inventário da Biblioteca Maker ===\nDiretório: {LIB_ROOT}\n")
    if not os.path.exists(SYM_INDIVIDUAL_DIR):
        print("Nenhum componente cadastrado ainda.")
        return
        
    files = sorted([f for f in os.listdir(SYM_INDIVIDUAL_DIR) if f.endswith(".kicad_sym")])
    if not files:
        print("Nenhum componente cadastrado ainda.")
        return
        
    print(f"{'Nome do Componente':<35} | {'LCSC':<8} | {'Fabricante':<25} | {'3D'}")
    print("-" * 85)
    
    for filename in files:
        filepath = os.path.join(SYM_INDIVIDUAL_DIR, filename)
        comp_name = filename.replace(".kicad_sym", "")
        
        lcsc = "N/A"
        mfr = "N/A"
        
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            lcsc_match = re.search(r'\(property\s+"LCSC Part"\s+"([^"]+)"', content)
            mfr_match = re.search(r'\(property\s+"Manufacturer"\s+"([^"]+)"', content)
            if lcsc_match:
                lcsc = lcsc_match.group(1)
            if mfr_match:
                mfr = mfr_match.group(1).split('(')[0].strip()
        except Exception:
            pass
            
        has_3d = "[✓] wrl/step" if (os.path.exists(os.path.join(DIR_3D, f"{comp_name}.wrl")) or os.path.exists(os.path.join(DIR_3D, f"{comp_name}.step"))) else "[x] Ausente"
        print(f"{comp_name:<35} | {lcsc:<8} | {mfr:<25} | {has_3d}")
    print(f"\nTotal: {len(files)} componente(s)\n")

def show_info(target):
    if re.match(r'^C\d+$', target.upper().strip()):
        resolved = find_name_by_lcsc(target)
        if not resolved:
            print(f"[!] Erro: Nenhum componente encontrado com o código LCSC '{target}'")
            return
        target = resolved
        
    sym_path = os.path.join(SYM_INDIVIDUAL_DIR, f"{target}.kicad_sym")
    if not os.path.exists(sym_path):
        print(f"[!] Erro: Componente '{target}' não cadastrado na biblioteca.")
        return
        
    print(f"\n=== Detalhes do Componente: {target} ===")
    
    lcsc = "N/A"
    mfr = "N/A"
    mpn = "N/A"
    datasheet = "N/A"
    fp_ref = "N/A"
    
    try:
        with open(sym_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        lcsc_match = re.search(r'\(property\s+"LCSC Part"\s+"([^"]+)"', content)
        mfr_match = re.search(r'\(property\s+"Manufacturer"\s+"([^"]+)"', content)
        mpn_match = re.search(r'\(property\s+"MPN"\s+"([^"]+)"', content)
        ds_match = re.search(r'\(property\s+"Datasheet"\s+"([^"]+)"', content)
        fp_match = re.search(r'\(property\s+"Footprint"\s+"([^"]+)"', content)
        
        if lcsc_match: lcsc = lcsc_match.group(1)
        if mfr_match: mfr = mfr_match.group(1)
        if mpn_match: mpn = mpn_match.group(1)
        if ds_match: datasheet = ds_match.group(1)
        if fp_match: fp_ref = fp_match.group(1)
    except Exception as e:
        print(f"[!] Erro ao ler metadados: {e}")
        
    has_wrl = "Sim" if os.path.exists(os.path.join(DIR_3D, f"{target}.wrl")) else "Não"
    has_step = "Sim" if os.path.exists(os.path.join(DIR_3D, f"{target}.step")) else "Não"
    
    print(f"Código LCSC/JLCPCB:  {lcsc}")
    print(f"Fabricante:          {mfr}")
    print(f"Part Number (MPN):   {mpn}")
    print(f"Vínculo Footprint:   {fp_ref}")
    print(f"Modelo 3D WRL:       {has_wrl}")
    print(f"Modelo 3D STEP:      {has_step}")
    print(f"Datasheet:           {datasheet}")
    print(f"Símbolo físico:      symbols/{target}.kicad_sym")
    print(f"Footprint físico:    Maker.pretty/{target}.kicad_mod")
    print()

def open_datasheet(target):
    if re.match(r'^C\d+$', target.upper().strip()):
        resolved = find_name_by_lcsc(target)
        if not resolved:
            print(f"[!] Erro: Nenhum componente encontrado com o código LCSC '{target}'")
            return
        target = resolved
        
    sym_path = os.path.join(SYM_INDIVIDUAL_DIR, f"{target}.kicad_sym")
    if not os.path.exists(sym_path):
        print(f"[!] Erro: Componente '{target}' não cadastrado na biblioteca.")
        return
        
    try:
        with open(sym_path, "r", encoding="utf-8") as f:
            content = f.read()
        ds_match = re.search(r'\(property\s+"Datasheet"\s+"([^"]+)"', content)
        if ds_match and ds_match.group(1).startswith("http"):
            url = ds_match.group(1)
            print(f"[*] Abrindo datasheet: {url}")
            subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            print(f"[!] Link do datasheet não disponível ou inválido para '{target}'")
    except Exception as e:
        print(f"[!] Erro ao abrir datasheet: {e}")

def check_library():
    print(f"\n=== Auditoria de Integridade: Biblioteca Maker ===\n")
    if not os.path.exists(SYM_INDIVIDUAL_DIR):
        print("[✓] Biblioteca vazia e consistente.")
        return
        
    files = sorted([f for f in os.listdir(SYM_INDIVIDUAL_DIR) if f.endswith(".kicad_sym")])
    if not files:
        print("[✓] Biblioteca vazia e consistente.")
        return
        
    warnings = 0
    errors = 0
    
    for filename in files:
        comp_name = filename.replace(".kicad_sym", "")
        sym_path = os.path.join(SYM_INDIVIDUAL_DIR, filename)
        fp_path = os.path.join(FP_DIR, f"{comp_name}.kicad_mod")
        
        if not os.path.exists(fp_path):
            print(f"[ERRO] Footprint ausente para o componente '{comp_name}' (esperado: Maker.pretty/{comp_name}.kicad_mod)")
            errors += 1
            
        try:
            with open(sym_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            lcsc_match = re.search(r'\(property\s+"LCSC Part"\s+"([^"]+)"', content)
            jlc_match = re.search(r'\(property\s+"JLCPCB Part #"\s+"([^"]+)"', content)
            fp_prop_match = re.search(r'\(property\s+"Footprint"\s+"Maker:([^"]+)"', content)
            
            if not lcsc_match:
                print(f"[AVISO] Componente '{comp_name}' não possui a propriedade 'LCSC Part' para o BOM.")
                warnings += 1
            if not jlc_match:
                print(f"[AVISO] Componente '{comp_name}' não possui a propriedade 'JLCPCB Part #' para o BOM.")
                warnings += 1
            if fp_prop_match and fp_prop_match.group(1) != comp_name:
                print(f"[ERRO] Componente '{comp_name}' vincula ao footprint '{fp_prop_match.group(1)}' em vez de 'Maker:{comp_name}' (casamento quebrado!)")
                errors += 1
        except Exception as e:
            print(f"[ERRO] Falha ao ler propriedades do símbolo '{comp_name}': {e}")
            errors += 1
            
        if os.path.exists(fp_path):
            try:
                with open(fp_path, "r", encoding="utf-8") as f:
                    fp_content = f.read()
                model_match = re.search(r'\(model\s+"([^"]+)"', fp_content)
                if model_match:
                    model_path = model_match.group(1)
                    if not os.path.exists(model_path):
                        print(f"[ERRO] Footprint '{comp_name}' vincula ao modelo 3D inexistente: {model_path}")
                        errors += 1
            except Exception as e:
                print(f"[ERRO] Falha ao ler footprint '{comp_name}': {e}")
                errors += 1
                
    print("-" * 60)
    print(f"Auditoria finalizada: {errors} erro(s), {warnings} aviso(s).")
    if errors == 0 and warnings == 0:
        print("[✓] Parabéns! A sua biblioteca está 100% íntegra e sem nenhuma inconsistência!")
    else:
        print("[!] Por favor, corrija as inconsistências acima para evitar falhas de produção.")
    print()

def set_library_path(new_path):
    new_path = os.path.abspath(os.path.expanduser(new_path))
    print(f"[*] Alterando diretório da biblioteca Maker para: {new_path}")
    
    os.makedirs(new_path, exist_ok=True)
    os.makedirs(os.path.join(new_path, "symbols"), exist_ok=True)
    os.makedirs(os.path.join(new_path, "Maker.pretty"), exist_ok=True)
    os.makedirs(os.path.join(new_path, "3d"), exist_ok=True)
    
    save_config(new_path)
    print(f"[+] Configuração salva em {CONFIG_FILE}!")
    
    kicad_sym_table = os.path.expanduser("~/.config/kicad/10.0/sym-lib-table")
    kicad_fp_table = os.path.expanduser("~/.config/kicad/10.0/fp-lib-table")
    
    if os.path.exists(kicad_sym_table):
        try:
            with open(kicad_sym_table, "r", encoding="utf-8") as f:
                content = f.read()
            new_uri = os.path.join(new_path, "Maker.kicad_sym")
            content = re.sub(
                r'(\(lib\s+\(name\s+"Maker"\)[^\)]*?\(uri\s+")[^"]+(")',
                rf'\g<1>{new_uri}\g<2>',
                content
            )
            with open(kicad_sym_table, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"  [~] Tabela de símbolos global do KiCad atualizada.")
        except Exception as e:
            print(f"  [!] Erro ao atualizar sym-lib-table: {e}")
            
    if os.path.exists(kicad_fp_table):
        try:
            with open(kicad_fp_table, "r", encoding="utf-8") as f:
                content = f.read()
            new_uri = os.path.join(new_path, "Maker.pretty")
            content = re.sub(
                r'(\(lib\s+\(name\s+"Maker"\)[^\)]*?\(uri\s+")[^"]+(")',
                rf'\g<1>{new_uri}\g<2>',
                content
            )
            with open(kicad_fp_table, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"  [~] Tabela de footprints global do KiCad atualizada.")
        except Exception as e:
            print(f"  [!] Erro ao atualizar fp-lib-table: {e}")
            
    print("[+] Caminho reconfigurado com sucesso!")

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

def export_bom_and_cpl(project_dir, output_dir=None):
    project_dir = os.path.abspath(os.path.expanduser(project_dir))
    if not os.path.exists(project_dir) or not os.path.isdir(project_dir):
        print(f"[!] Erro: Diretório do projeto não existe: {project_dir}")
        sys.exit(1)
        
    if output_dir:
        output_dir = os.path.abspath(os.path.expanduser(output_dir))
        os.makedirs(output_dir, exist_ok=True)
    else:
        output_dir = project_dir
        
    print(f"[*] Analisando diretório do projeto: {project_dir}")
    print(f"[*] Diretório de saída dos relatórios: {output_dir}")
    
    # Encontra arquivos .kicad_sch
    sch_files = [os.path.join(project_dir, f) for f in os.listdir(project_dir) if f.endswith(".kicad_sch")]
    # Encontra arquivos .kicad_pcb
    pcb_files = [os.path.join(project_dir, f) for f in os.listdir(project_dir) if f.endswith(".kicad_pcb")]
    
    if not sch_files:
        print("[!] Erro: Nenhum arquivo de esquema (.kicad_sch) encontrado neste diretório.")
        sys.exit(1)
        
    # 1. Processamento da BOM
    all_components = []
    for sch_path in sch_files:
        print(f"  [+] Lendo esquema: {os.path.basename(sch_path)}")
        all_components.extend(extract_symbols_from_sch(sch_path))
        
    if not all_components:
        print("[!] Nenhum componente válido para BOM encontrado nos esquemas.")
        sys.exit(0)
        
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
            
    print(f"[+] BOM exportada com sucesso: {os.path.join(os.path.basename(output_dir), 'BOM_JLCPCB.csv')} ({len(all_components)} componente(s) agrupado(s) em {len(grouped)} linha(s))")
    
    # 2. Processamento do CPL (coordenadas)
    if pcb_files:
        pcb_path = pcb_files[0]
        print(f"  [+] Lendo layout da placa: {os.path.basename(pcb_path)}")
        placements = extract_placements_from_pcb(pcb_path)
        
        if placements:
            cpl_path = os.path.join(output_dir, "CPL_JLCPCB.csv")
            with open(cpl_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["Designator", "Mid X", "Mid Y", "Rotation", "Layer"])
                
                for p in sorted(placements, key=lambda x: (re.sub(r'\d+', '', x["ref"]), int(re.search(r'\d+', x["ref"]).group(0)) if re.search(r'\d+', x["ref"]) else 0)):
                    writer.writerow([p["ref"], f"{p['x']:.4f}", f"{p['y']:.4f}", f"{p['rot'] % 360:.2f}", p["layer"]])
                    
            print(f"[+] CPL (Centroid) exportado com sucesso: {os.path.join(os.path.basename(output_dir), 'CPL_JLCPCB.csv')} ({len(placements)} coordenadas registradas)")
        else:
            print("  [!] Nenhum footprint encontrado com coordenadas válidas no layout.")
    else:
        print("  [~] Nenhum arquivo .kicad_pcb encontrado (pulando a geração do CPL).")

def main():
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
        elif cmd == "directory" or cmd == "path":
            if len(args.positional_args) > 1:
                args.set_path = args.positional_args[1]
                args.positional_args = []
            else:
                print("[!] Erro: Você deve fornecer o caminho do diretório. Ex: kiflux directory /novo/caminho")
                sys.exit(1)
        elif cmd == "info":
            if len(args.positional_args) > 1:
                args.info = args.positional_args[1]
                args.positional_args = []
            else:
                print("[!] Erro: Você deve fornecer o componente ou código LCSC. Ex: kiflux info C2040")
                sys.exit(1)
        elif cmd == "datasheet":
            if len(args.positional_args) > 1:
                args.datasheet = args.positional_args[1]
                args.positional_args = []
            else:
                print("[!] Erro: Você deve fornecer o componente ou código LCSC. Ex: kiflux datasheet C2040")
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
    
    # Trata uso rápido posicional padrão
    if args.positional_args:
        if not args.lcsc and not args.remove and not args.rename_from and not args.rebuild and not args.rename and not args.bom:
            pos_args = args.positional_args
            if re.match(r'^C\d+$', pos_args[0].upper().strip()):
                # Caso 1: Apenas 1 argumento posicional (Ex: kiflux C2040)
                if len(pos_args) == 1:
                    import_single_component(pos_args[0])
                    sys.exit(0)
                # Caso 2: 2 argumentos posicionais e o segundo NÃO é um código LCSC (Ex: kiflux C2040 NOME)
                elif len(pos_args) == 2 and not re.match(r'^C\d+$', pos_args[1].upper().strip()):
                    import_single_component(pos_args[0], pos_args[1])
                    sys.exit(0)
                # Caso 3: Múltiplos argumentos e todos ou o segundo são códigos LCSC (Ex: kiflux C2040 C8791)
                else:
                    print(f"[*] Detectada importação em lote de {len(pos_args)} componentes...")
                    success_count = 0
                    for lcsc_code in pos_args:
                        if re.match(r'^C\d+$', lcsc_code.upper().strip()):
                            if import_single_component(lcsc_code):
                                success_count += 1
                        else:
                            print(f"[!] Pulando argumento '{lcsc_code}' pois não é um código LCSC válido em importação em lote.")
                    print(f"\n[+] Importação em lote concluída: {success_count} de {len(pos_args)} componentes importados com sucesso!")
                    sys.exit(0)
            else:
                print(f"[!] Erro: O primeiro argumento '{pos_args[0]}' deve ser um código LCSC válido (ex: C2040).")
                sys.exit(1)
                
    if args.bom:
        export_bom_and_cpl(args.bom, args.bom_output)
        sys.exit(0)
        
    if args.list:
        list_components()
        sys.exit(0)
        
    if args.info:
        show_info(args.info)
        sys.exit(0)
        
    if args.datasheet:
        open_datasheet(args.datasheet)
        sys.exit(0)
        
    if args.check:
        check_library()
        sys.exit(0)
        
    if args.set_path:
        set_library_path(args.set_path)
        sys.exit(0)
        
    if args.rebuild:
        rebuild_consolidated_library()
        sys.exit(0)
        
    if args.remove:
        target = args.remove
        if re.match(r'^C\d+$', target.upper().strip()):
            resolved_name = find_name_by_lcsc(target)
            if resolved_name:
                print(f"[*] Código LCSC '{target}' resolved para o componente '{resolved_name}'")
                target = resolved_name
            else:
                print(f"[!] Não foi possível encontrar nenhum componente cadastrado com o código LCSC '{target}'")
                sys.exit(1)
        remove_component(target)
        sys.exit(0)
        
    if args.rename_from or args.rename_to:
        if not args.rename_from or not args.rename_to:
            print("[!] Erro: Para renomear, você deve passar ambos os parâmetros --rename-from e --rename-to.")
            sys.exit(1)
            
        target_from = args.rename_from
        if re.match(r'^C\d+$', target_from.upper().strip()):
            resolved_name = find_name_by_lcsc(target_from)
            if resolved_name:
                print(f"[*] Código LCSC '{target_from}' resolved para o componente '{resolved_name}'")
                target_from = resolved_name
            else:
                print(f"[!] Não foi possível encontrar nenhum componente cadastrado com o código LCSC '{target_from}'")
                sys.exit(1)
        rename_component(target_from, args.rename_to)
        sys.exit(0)
        
    if args.rename:
        target = args.rename
        lcsc_id = ""
        
        if re.match(r'^C\d+$', target.upper().strip()):
            lcsc_id = target.upper().strip()
            resolved_name = find_name_by_lcsc(lcsc_id)
            if not resolved_name:
                print(f"[!] Erro: Nenhum componente cadastrado localmente com o código LCSC '{lcsc_id}'.")
                sys.exit(1)
            target = resolved_name
        else:
            sym_path = os.path.join(SYM_INDIVIDUAL_DIR, f"{target}.kicad_sym")
            if not os.path.exists(sym_path):
                print(f"[!] Erro: Componente '{target}' não encontrado em symbols/{target}.kicad_sym")
                sys.exit(1)
            with open(sym_path, "r", encoding="utf-8") as f:
                content = f.read()
            lcsc_match = re.search(r'\(property\s+"LCSC Part"\s+"([^"]+)"', content)
            if not lcsc_match:
                print(f"[!] Erro: Não foi possível encontrar o código LCSC no símbolo de '{target}' para buscar metadados.")
                sys.exit(1)
            lcsc_id = lcsc_match.group(1).upper().strip()
            
        print(f"[*] Buscando metadados na LCSC para o código '{lcsc_id}'...")
        run_easyeda2kicad(lcsc_id)
        value, manufacturer, package = extract_properties_from_temp()
        
        if not value:
            print("[!] Erro: Não foi possível obter os metadados da LCSC.")
            sys.exit(1)
            
        temp_sym_path = os.path.join(TEMP_DIR, "Maker.kicad_sym")
        temp_sym_content = ""
        if os.path.exists(temp_sym_path):
            with open(temp_sym_path, "r", encoding="utf-8") as f:
                temp_sym_content = f.read()
                
        new_name = generate_standardized_name(value, manufacturer, package, temp_sym_content)
        print(f"[+] Metadados LCSC: Valor={value}, Fabricante={manufacturer}, Encapsulamento={package}")
        print(f"[+] Nome automático gerado: '{new_name}'")
        
        confirm = input(f"\nDeseja confirmar a renomeação para '{new_name}'? [S/n]: ").strip().lower()
        if confirm not in ['', 's', 'sim']:
            print("[!] Renomeação automática cancelada.")
            if os.path.exists(TEMP_DIR):
                shutil.rmtree(TEMP_DIR)
            sys.exit(0)
            
        rename_component(target, new_name)
        
        if os.path.exists(TEMP_DIR):
            shutil.rmtree(TEMP_DIR)
        sys.exit(0)
        
    if args.lcsc:
        import_single_component(args.lcsc, args.name)
        sys.exit(0)
        
    print("[!] Nenhuma ação válida fornecida. Use --help para ver as opções.")
    sys.exit(1)

if __name__ == "__main__":
    main()
