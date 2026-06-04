# -*- coding: utf-8 -*-
import json

def extract_keys():
    with open("venv/Upstock_universe.json", "r") as f:
        data = json.load(f)
    
    # Extract only the instrument keys
    keys = []
    for item in data:
        if "instrument_key" in item and item.get("segment") == "NSE_EQ":
            keys.append(item["instrument_key"])

    
    # Save the array to a JSON file
    out_file = "all_instrument_keys.json"
    with open(out_file, "w") as f:
        json.dump(keys, f, indent=2)
        
    print(f"Successfully extracted {len(keys)} instrument keys to {out_file}")

if __name__ == "__main__":
    extract_keys()
