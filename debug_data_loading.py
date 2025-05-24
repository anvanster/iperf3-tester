#!/usr/bin/env python3
"""
Simple debug script to test CSV and JSON loading functionality.
"""

import os
import pandas as pd
import json
from pathlib import Path

def read_csv_results(csv_file):
    """Read iperf3 results from CSV file."""
    try:
        data = pd.read_csv(csv_file)
        print(f"Successfully read {len(data)} rows from {csv_file}")
        return data
    except Exception as e:
        print(f"Error reading CSV file {csv_file}: {e}")
        return None

def read_json_results(json_file):
    """Read iperf3 results from JSON file."""
    try:
        print(f"Attempting to read JSON file: {json_file}")
        with open(json_file, 'r') as f:
            data = json.load(f)
        
        print(f"JSON loaded successfully, contains {len(data)} entries")
        
        results = []
        for i, item in enumerate(data):
            try:
                # Extract basic info for debugging
                params = item.get('parameters', {})
                protocol = params.get('protocol')
                direction = params.get('direction')
                
                print(f"Processing item {i}: protocol={protocol}, direction={direction}")
                
                # Create a simple row
                row = {
                    'protocol': protocol,
                    'direction': direction
                }
                results.append(row)
                
            except Exception as e:
                print(f"Error processing JSON item {i}: {e}")
                continue
        
        df = pd.DataFrame(results)
        print(f"Created DataFrame with {len(df)} rows")
        return df
    
    except Exception as e:
        print(f"Error reading JSON file {json_file}: {e}")
        return None

def main():
    # Resolve paths
    script_dir = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(script_dir, 'results/iperf3_results.csv')
    json_path = os.path.join(script_dir, 'results/iperf3_results.json')
    
    print(f"CSV path: {csv_path}")
    print(f"JSON path: {json_path}")
    
    # Check if files exist
    print(f"CSV file exists: {os.path.exists(csv_path)}")
    print(f"JSON file exists: {os.path.exists(json_path)}")
    
    # Read data from CSV and JSON files
    print("\nReading CSV file:")
    csv_data = read_csv_results(csv_path)
    
    print("\nReading JSON file:")
    json_data = read_json_results(json_path)
    
    if csv_data is not None:
        print("\nCSV columns:", csv_data.columns.tolist())
        print("CSV data types:", csv_data.dtypes)
    
    if json_data is not None:
        print("\nJSON columns:", json_data.columns.tolist())
        print("JSON data types:", json_data.dtypes)
    
    print("\nDebug complete!")

if __name__ == "__main__":
    main()
