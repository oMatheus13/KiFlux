import os
import sys
import json
import re
import tempfile
import shutil

CONFIG_DIR = os.path.expanduser("~/.config/kiflux")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
OLD_CONFIG_DIR = os.path.expanduser("~/.config/maker")
OLD_CONFIG_FILE = os.path.join(OLD_CONFIG_DIR, "config.json")
DEFAULT_LIB_ROOT = os.path.expanduser("~/KiCad/KiFlux")
TEMP_DIR = os.path.join(tempfile.gettempdir(), "easyeda_import_temp")

class LibraryPaths:
    """
    Context class to hold physical directory paths for the library.
    Eliminates global mutable variables.
    """
    def __init__(self, lib_root):
        self.root = os.path.abspath(os.path.expanduser(lib_root))
        self.name = os.path.basename(self.root.rstrip("/"))
        if not self.name:
            self.name = "KiFlux"
        self.sym_lib_file = os.path.join(self.root, f"{self.name}.kicad_sym")
        self.sym_individual_dir = os.path.join(self.root, "symbols")
        self.fp_dir = os.path.join(self.root, f"{self.name}.pretty")
        self.dir_3d = os.path.join(self.root, "3d")

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("lib_root", DEFAULT_LIB_ROOT)
        except Exception:
            pass
    # Fallback migration
    if os.path.exists(OLD_CONFIG_FILE):
        try:
            with open(OLD_CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                lib_root = data.get("lib_root", DEFAULT_LIB_ROOT)
                save_config(lib_root)
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
        print(f"[!] Error saving configuration: {e}")

def set_library_path(new_path):
    new_path = os.path.abspath(os.path.expanduser(new_path))
    print(f"[*] Updating library root to: {new_path}")
    
    # Create target directory structure
    paths = LibraryPaths(new_path)
    os.makedirs(paths.root, exist_ok=True)
    os.makedirs(paths.sym_individual_dir, exist_ok=True)
    os.makedirs(paths.fp_dir, exist_ok=True)
    os.makedirs(paths.dir_3d, exist_ok=True)
    
    save_config(new_path)
    print(f"[+] Configuration saved at {CONFIG_FILE}!")
    
    kicad_sym_table = os.path.expanduser("~/.config/kicad/10.0/sym-lib-table")
    kicad_fp_table = os.path.expanduser("~/.config/kicad/10.0/fp-lib-table")
    
    if os.path.exists(kicad_sym_table):
        try:
            with open(kicad_sym_table, "r", encoding="utf-8") as f:
                content = f.read()
            
            if f'(name "{paths.name}")' in content:
                content = re.sub(
                    r'(\(lib\s+\(name\s+"' + re.escape(paths.name) + r'"\)[^\)]*?\(uri\s+")[^"]+(")',
                    rf'\g<1>{paths.sym_lib_file}\g<2>',
                    content
                )
            else:
                entry = f'  (lib (name "{paths.name}")(type "KiCad")(uri "{paths.sym_lib_file}")(options "")(descr ""))\n'
                insert_pos = content.rfind(')')
                if insert_pos != -1:
                    content = content[:insert_pos] + entry + ")"
            
            with open(kicad_sym_table, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"  [~] KiCad global symbol library table updated for '{paths.name}'.")
        except Exception as e:
            print(f"  [!] Error updating global sym-lib-table: {e}")
            
    if os.path.exists(kicad_fp_table):
        try:
            with open(kicad_fp_table, "r", encoding="utf-8") as f:
                content = f.read()
            
            if f'(name "{paths.name}")' in content:
                content = re.sub(
                    r'(\(lib\s+\(name\s+"' + re.escape(paths.name) + r'"\)[^\)]*?\(uri\s+")[^"]+(")',
                    rf'\g<1>{paths.fp_dir}\g<2>',
                    content
                )
            else:
                entry = f'  (lib (name "{paths.name}")(type "KiCad")(uri "{paths.fp_dir}")(options "")(descr ""))\n'
                insert_pos = content.rfind(')')
                if insert_pos != -1:
                    content = content[:insert_pos] + entry + ")"
                    
            with open(kicad_fp_table, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"  [~] KiCad global footprint library table updated for '{paths.name}'.")
        except Exception as e:
            print(f"  [!] Error updating global fp-lib-table: {e}")
            
    print("[+] Paths reconfigured successfully!")
    ensure_generic_3d_models(paths)
    return paths

def init_kiflux(force=False):
    if os.path.exists(CONFIG_FILE) and not force:
        paths = LibraryPaths(load_config())
        ensure_generic_3d_models(paths)
        return paths
        
    print("\n=== KiFlux Interactive Onboarding Helper ===")
    print("This wizard will help you set up your KiCad component library directory.\n")
    
    default_path = os.path.expanduser("~/KiCad/KiFlux")
    print(f"Press [Enter] to accept the default path, or type a custom absolute path.")
    user_path = input(f"Library directory [{default_path}]: ").strip()
    
    if not user_path:
        lib_path = default_path
    else:
        lib_path = os.path.abspath(os.path.expanduser(user_path))
        
    print(f"\n[*] Creating library structure in: {lib_path}")
    
    paths = LibraryPaths(lib_path)
    os.makedirs(paths.root, exist_ok=True)
    os.makedirs(paths.sym_individual_dir, exist_ok=True)
    os.makedirs(paths.fp_dir, exist_ok=True)
    os.makedirs(paths.dir_3d, exist_ok=True)
    
    save_config(lib_path)
    
    confirm_kicad = input("\nDo you want to automatically register this library in KiCad's global tables? [S(yes) / n(no)]: ").strip().lower()
    if confirm_kicad in ['', 's', 'yes']:
        set_library_path(lib_path)
        
    print("\n[+] KiFlux configured successfully! You can now import components.")
    ensure_generic_3d_models(paths)
    return paths

def ensure_config_exists():
    if not os.path.exists(CONFIG_FILE) and not os.path.exists(OLD_CONFIG_FILE):
        print("[!] KiFlux has not been initialized yet.")
        choice = input("Do you want to run the guided setup wizard now? [S(yes) / n(no)]: ").strip().lower()
        if choice in ['', 's', 'yes']:
            return init_kiflux()
        else:
            lib_path = DEFAULT_LIB_ROOT
            print(f"[*] Silently initializing with default path: {lib_path}")
            paths = LibraryPaths(lib_path)
            os.makedirs(paths.root, exist_ok=True)
            os.makedirs(paths.sym_individual_dir, exist_ok=True)
            os.makedirs(paths.fp_dir, exist_ok=True)
            os.makedirs(paths.dir_3d, exist_ok=True)
            save_config(lib_path)
            ensure_generic_3d_models(paths)
            print("[~] Tip: You can run 'kiflux init' at any time to reconfigure and register in KiCad.")
            return paths
    else:
        paths = LibraryPaths(load_config())
        ensure_generic_3d_models(paths)
        return paths

def ensure_generic_3d_models(paths):
    """
    Ensures that generic 3D models (for resistors and capacitors) are copied 
    from the package resources into the user's library under 3d/generic/.
    """
    generic_dir = os.path.join(paths.dir_3d, "generic")
    os.makedirs(generic_dir, exist_ok=True)
    
    resource_dir = os.path.join(os.path.dirname(__file__), "resources", "3d_generic")
    if not os.path.exists(resource_dir):
        return
        
    for filename in os.listdir(resource_dir):
        if filename.endswith(".step") or filename.endswith(".wrl"):
            src_file = os.path.join(resource_dir, filename)
            dest_file = os.path.join(generic_dir, filename)
            if not os.path.exists(dest_file):
                try:
                    shutil.copy(src_file, dest_file)
                except Exception:
                    pass
