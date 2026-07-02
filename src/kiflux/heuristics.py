import re

def clean_name(name):
    if not name:
        return ""
    name = re.sub(r'[^\w\-]', '_', name)
    return name.upper().strip().strip('_')

def generate_standardized_name(value, manufacturer, package, temp_sym_content=None, jlc_describe=None):
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
        # Tenta extrair dimensões físicas (ex: L3.2-W1.6 ou L7.0-W7.0) comuns no EasyEDA
        dim_match = re.search(r'L(\d+\.?\d*)_W(\d+\.?\d*)', pkg_clean)
        if dim_match:
            try:
                l_val = float(dim_match.group(1))
                w_val = float(dim_match.group(2))
                # Se forem dimensões pequenas de chip SMD (ex: L3.2 W1.6), formata no padrão clássico (ex: 3216)
                if l_val < 20 and w_val < 20:
                    l_str = f"{int(l_val * 10)}"
                    w_str = f"{int(w_val * 10)}"
                    pkg_dims = f"{l_str}{w_str}"
                else:
                    pkg_dims = f"L{dim_match.group(1)}W{dim_match.group(2)}".replace(".", "")
            except Exception:
                pkg_dims = f"L{dim_match.group(1)}W{dim_match.group(2)}".replace(".", "")
                
            prefix = pkg_clean.split('_')[0]
            if prefix in ["ANT", "SMD", "CONN", "CRYSTAL", "LED", "TH", "PKG"]:
                if "SMD" in pkg_clean and prefix != "SMD":
                    pkg = f"{prefix}_SMD_{pkg_dims}"
                elif "TH" in pkg_clean and prefix != "TH":
                    pkg = f"{prefix}_TH_{pkg_dims}"
                else:
                    pkg = f"{prefix}_{pkg_dims}" if prefix != "SMD" else f"SMD_{pkg_dims}"
            else:
                pkg = f"{prefix}_{pkg_dims}"
        else:
            # Se não tem dimensões, preserva a marcação de Through-Hole (TH) ou Surface-Mount (SMD)
            prefix = pkg_clean.split('_')[0]
            if "TH" in pkg_clean and "TH" not in prefix:
                pkg = f"{prefix}_TH"
            elif "SMD" in pkg_clean and "SMD" not in prefix:
                pkg = f"{prefix}_SMD"
            else:
                pkg = prefix
                
        # Remove caracteres indesejados mantendo sublinhados
        pkg = re.sub(r'[^A-Z0-9_]', '', pkg)
        if not pkg:
            pkg = "GENERIC"

    # Normaliza valor
    val_clean = value.upper().strip()
    val_clean = re.sub(r'_C\d+$', '', val_clean)
    
    # Coleta descrição e palavras-chave
    metadata_text = val_clean
    if jlc_describe:
        metadata_text += " " + jlc_describe.upper()
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

    # Primeiro tenta pelo Value direto
    if re.match(cap_value_pattern, val_clean):
        is_capacitor = True
    elif re.match(res_value_pattern, val_clean) or re.match(res_value_inline_pattern, val_clean):
        is_resistor = True
    else:
        # Se o Value for um Part Number poluído, vasculha a descrição/keywords por valores físicos
        cap_desc_match = re.search(r'\b(\d+(?:\.\d+)?\s*(?:PF|NF|UF|µF|MF|F))\b', metadata_text)
        res_desc_match = re.search(r'\b(\d+(?:\.\d+)?\s*(?:R|K|M|OHM|OHMS|Ω|KΩ|MΩ|RΩ))\b', metadata_text)
        
        if cap_desc_match and any(k in metadata_text for k in ["CAPACITOR", "CAPACITORS", "CAP"]):
            is_capacitor = True
            val_clean = cap_desc_match.group(1)
        elif res_desc_match and any(k in metadata_text for k in ["RESISTOR", "RESISTORS", "RES"]):
            is_resistor = True
            val_clean = res_desc_match.group(1)

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
        val = val.replace("OHM", "").replace("R", "").replace("K", "k").replace("M", "m").replace("Ω", "")
        val = val.lower().strip()
        return f"R_{pkg}_{val}_{mfr}"

    category = "IC"
    mcu_prefixes = [
        "RP2", "ESP32", "ESP8266", "ESP_C", "ESP_S", "STM32", "GD32", "ATMEGA", "ATTINY", 
        "NRF5", "SAMD", "LPC1", "LPC8", "LPC5", "MK2", "MKL", "MSP430", "TMS320", "PIC1", "CH5"
    ]
    
    # 1. Microcontrollers, Processors & FPGAs
    if any(k in metadata_text for k in ["MICROCONTROLLER", "MCU", "PROCESSOR", "FPGA", "CPLD"]) or any(mcu in val_clean for mcu in mcu_prefixes):
        category = "MCU"
        
    # 2. Memories (Flash, EEPROM, SRAM, SDRAM)
    elif any(k in metadata_text for k in ["FLASH", "EEPROM", "SRAM", "SDRAM", "DRAM", "MEMOR"]):
        category = "MEM"
        
    # 3. Regulators, LDOs, PMICs, Buck-Boost & Chargers
    elif any(k in metadata_text for k in ["REGULATOR", "LDO", "VOLTAGE REFERENCE", "PMIC", "BUCK CONVERTER", "BOOST CONVERTER", "POWER CONVERTER", "CHARGER", "DC-DC", "DC/DC"]) or "AMS1117" in val_clean or "LM78" in val_clean:
        category = "REG"
        
    # 4. Diodes, Rectifiers, Zener & ESD Protection
    elif any(k in metadata_text for k in ["DIODE", "RECTIFIER", "ZENER", "TVS", "ESD PROTECTION"]) or val_clean.startswith("1N4"):
        category = "DIODE"
        
    # 5. Transistors, MOSFETs, BJTs & IGBTs
    elif any(k in metadata_text for k in ["TRANSISTOR", "MOSFET", "IGBT", "BJT"]):
        category = "TRANS"
        
    # 6. Connectors, Headers, USBs & Terminals
    elif any(k in metadata_text for k in ["CONNECTOR", "USB", "HEADER", "JACK", "PLUG", "SOCKET", "TERMINAL", "RECEPTACLE"]):
        category = "CONN"
        
    # 7. Crystals, Resonators & Oscillators
    elif any(k in metadata_text for k in ["CRYSTAL", "OSCILLATOR", "RESONATOR"]):
        category = "XTAL"
        
    # 8. Chip & RF Antennas
    elif "ANTENNA" in metadata_text or val_clean.startswith("ANT"):
        category = "ANT"
        
    # 9. Sensors (Temp, Humidity, Accelerometer, Thermistor)
    elif any(k in metadata_text for k in ["SENSOR", "ACCELEROMETER", "GYROSCOPE", "THERMISTOR", "HUMIDITY SENSOR", "PRESSURE SENSOR"]):
        category = "SENS"
        
    # 10. Switches, Tactile Buttons & Slides
    elif any(k in metadata_text for k in ["SWITCH", "BUTTON", "TACTILE"]):
        category = "SW"
        
    # 11. Optocouplers & Isolators
    elif any(k in metadata_text for k in ["OPTOCOUPLER", "OPTOISOLATOR", "ISOLATOR", "DIGITAL ISOLATOR"]):
        category = "OPTO"
        
    # 12. Fuses, Varistors & Resettable Protections
    elif any(k in metadata_text for k in ["FUSE", "VARISTOR", "PPTC", "RESETTABLE FUSE"]):
        category = "FUSE"
        
    # 13. Displays (OLED, LCD, TFT, 7-Segment)
    elif any(k in metadata_text for k in ["DISPLAY", "OLED", "LCD", "TFT", "7-SEGMENT"]):
        category = "DISP"
        
    # 14. Inductors, Chokes, Transformers & Ferrite Beads
    elif any(k in metadata_text for k in ["INDUCTOR", "CHOKE", "TRANSFORMER", "FERRITE BEAD", "FERRITE CHOKE"]):
        category = "IND"

    # 15. LEDs, RGBs and Neopixels (ignoring drivers)
    elif any(k in metadata_text for k in ["LED", "RGB", "WS2812", "NEOPIXEL"]) and not any(k in metadata_text for k in ["DRIVER", "CONTROLLER"]):
        category = "LED"

    # 16. Relays
    elif "RELAY" in metadata_text:
        category = "RELAY"

    # 17. Batteries and Battery Holders
    elif any(k in metadata_text for k in ["BATTERY", "BATTERY HOLDER", "COIN CELL"]):
        category = "BAT"

    # 18. Buzzers and Speakers
    elif any(k in metadata_text for k in ["BUZZER", "SPEAKER", "AUDIO TRANSDUCER"]):
        category = "BUZZ"

    # 19. Potentiometers and Trimpots
    elif any(k in metadata_text for k in ["POTENTIOMETER", "TRIMPOT", "VARIABLE RESISTOR"]):
        category = "POT"

    # 20. Modules (Wireless, Wi-Fi, Bluetooth, LoRa, etc.)
    elif any(k in metadata_text for k in ["WIFI MODULE", "BLUETOOTH MODULE", "RF MODULE", "TRANSCEIVER MODULE", "LORA MODULE", "MODULE"]):
        category = "MODULE"

    # 21. Amplifiers & Comparators (Op-Amps)
    elif any(k in metadata_text for k in ["OPERATIONAL AMPLIFIER", "OPAMP", "COMPARATOR", "DIFFERENTIAL AMPLIFIER"]):
        category = "AMP"

    # 22. Power Drivers (Motors, Gates, Solenoids)
    elif any(k in metadata_text for k in ["MOTOR DRIVER", "GATE DRIVER", "LED DRIVER", "HALF-BRIDGE", "H-BRIDGE", "SOLENOID DRIVER"]):
        category = "DRIVER"

    # 23. Logic ICs (Gates, Shift Registers, Mux/Demux)
    elif any(k in metadata_text for k in ["LOGIC GATE", "SHIFT REGISTER", "MULTIPLEXER", "DEMULTIPLEXER", "DECODER", "FLIP-FLOP", "COUNTER"]) or any(p in val_clean for p in ["74HC", "74HCT", "74LVC"]):
        category = "LOGIC"

    # 24. Dedicated RF ICs (Transceivers, Mixers, Baluns)
    elif any(k in metadata_text for k in ["RF TRANSCEIVER", "BALUN", "RF AMPLIFIER", "MIXER", "MODULATOR", "DEMODULATOR", "ATTENUATOR"]):
        category = "RF"

    # 25. Clock, PLL & Timing Generators
    elif any(k in metadata_text for k in ["CLOCK GENERATOR", "CLOCK BUFFER", "PLL", "FREQUENCY SYNTHESIZER", "REAL-TIME CLOCK", "RTC"]):
        category = "CLK"

    # 26. EMI Filters & RF Passives
    elif any(k in metadata_text for k in ["EMI FILTER", "COMMON MODE CHOKE", "BANDPASS FILTER", "LOWPASS FILTER", "LINE FILTER"]):
        category = "FILT"

    # 27. ADCs and DACs
    elif any(k in metadata_text for k in ["ANALOG-TO-DIGITAL", "DIGITAL-TO-ANALOG", "ADC", "DAC"]) and not any(k in metadata_text for k in ["MCU", "MICROCONTROLLER"]):
        category = "ADC"
        
    model = clean_name(val_clean)
    return f"{category}_{model}_{pkg}_{mfr}"
