#!/usr/bin/env python3
"""
Specialized visualization script that focuses specifically on the relationship
between message size and throughput for all protocols and directions.
"""

import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
import argparse
import json

# Set style for more professional visualizations
plt.style.use('ggplot')
sns.set(style="whitegrid", font_scale=1.1)

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
        with open(json_file, 'r') as f:
            data = json.load(f)
        
        results = []
        for item in data:
            try:
                # Extract parameters
                params = item.get('parameters', {})
                protocol = params.get('protocol')
                direction = params.get('direction')
                message_size = params.get('message_size')
                port = params.get('port')
                title = params.get('title', '')
                
                # Get error message if present
                error_message = None
                iperf_result = item.get('iperf_result', {})
                
                row = {
                    'title': title,
                    'protocol': protocol,
                    'direction': direction,
                    'message_size_param': message_size,
                    'port': port,
                    'error_message': None
                }
                
                # Check if this is a failed test
                if not iperf_result or isinstance(iperf_result, str):
                    row['error_message'] = "Client execution failed or returned no data"
                    results.append(row)
                    continue
                
                # Extract timestamp
                if 'start' in iperf_result and 'timestamp' in iperf_result['start']:
                    row['timestamp'] = iperf_result['start']['timestamp'].get('time')
                
                # Extract throughput based on protocol and direction
                if protocol == 'tcp':
                    if direction in ['tx', 'bx']:
                        if 'end' in iperf_result and 'sum_sent' in iperf_result['end']:
                            row['sent_bps'] = iperf_result['end']['sum_sent'].get('bits_per_second', 0)
                    
                    if direction in ['rx', 'bx']:
                        if 'end' in iperf_result and 'sum_received' in iperf_result['end']:
                            row['received_bps'] = iperf_result['end']['sum_received'].get('bits_per_second', 0)
                
                elif protocol == 'udp':
                    # For UDP
                    if 'end' in iperf_result and 'sum' in iperf_result['end']:
                        row['udp_bps'] = iperf_result['end']['sum'].get('bits_per_second', 0)
                        row['udp_jitter_ms'] = iperf_result['end']['sum'].get('jitter_ms', 0)
                        row['udp_lost_packets'] = iperf_result['end']['sum'].get('lost_packets', 0)
                        row['udp_lost_percent'] = iperf_result['end']['sum'].get('lost_percent', 0)
                
                results.append(row)
            except Exception as e:
                print(f"Error processing JSON item: {e}")
                continue
        
        df = pd.DataFrame(results)
        print(f"Successfully read {len(df)} rows from {json_file}")
        return df
    
    except Exception as e:
        print(f"Error reading JSON file {json_file}: {e}")
        return None

def combine_results(csv_data, json_data):
    """Combine results from CSV and JSON files."""
    if csv_data is None and json_data is None:
        return None
    elif csv_data is None:
        return json_data
    elif json_data is None:
        return csv_data
    
    # Ensure we have the same columns in both dataframes
    common_columns = list(set(csv_data.columns).intersection(set(json_data.columns)))
    json_data = json_data[common_columns]
    
    # Concatenate the dataframes
    combined = pd.concat([csv_data, json_data], ignore_index=True)
    print(f"Combined data: {len(combined)} rows")
    
    return combined

def normalize_message_size(message_size):
    """Convert message size strings to numeric values for sorting."""
    if pd.isna(message_size) or message_size == 'def' or message_size == 'default':
        return 131072  # Default is 128KB (131072 bytes)
    
    size = str(message_size).strip()
    if size.endswith('K'):
        return int(size[:-1]) * 1024
    elif size.endswith('M'):
        return int(size[:-1]) * 1024 * 1024
    else:
        try:
            return int(size)  # Assuming bytes
        except:
            return 131072  # Default as fallback

def get_display_size(size_bytes):
    """Convert size in bytes to a display format."""
    if size_bytes == 131072:  # Default size
        return "Default (128K)"
    elif size_bytes >= 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.0f}M"
    elif size_bytes >= 1024:
        return f"{size_bytes / 1024:.0f}K"
    else:
        return f"{size_bytes}B"

def calculate_throughput(row):
    """Extract the appropriate throughput value based on protocol and direction."""
    # For TCP TX
    if row['protocol'] == 'tcp' and row['direction'] == 'tx':
        return row.get('sent_bps', 0) / 1_000_000_000  # Convert to Gbps
    
    # For TCP RX
    elif row['protocol'] == 'tcp' and row['direction'] == 'rx':
        return row.get('received_bps', 0) / 1_000_000_000  # Convert to Gbps
    
    # For TCP BX (bidirectional) - use the average of sent and received
    elif row['protocol'] == 'tcp' and row['direction'] == 'bx':
        sent = row.get('sent_bps', 0)
        received = row.get('received_bps', 0)
        if sent > 0 and received > 0:
            return (sent + received) / 2 / 1_000_000_000  # Convert to Gbps
        elif sent > 0:
            return sent / 1_000_000_000
        elif received > 0:
            return received / 1_000_000_000
    
    # For UDP
    elif row['protocol'] == 'udp':
        return row.get('udp_bps', 0) / 1_000_000_000  # Convert to Gbps
    
    return 0

def prepare_data(data):
    """Prepare data for visualization."""
    # Add numeric message size and throughput columns
    data['message_size_bytes'] = data['message_size_param'].apply(normalize_message_size)
    data['throughput_gbps'] = data.apply(calculate_throughput, axis=1)
    data['message_size_display'] = data['message_size_bytes'].apply(get_display_size)
    
    # Mark tests with errors
    data['failed'] = data['error_message'].notna()
    
    # Create protocol_direction combined field for more readable legends
    data['protocol_direction'] = data.apply(
        lambda row: f"{row['protocol'].upper()} {row['direction'].upper()}", axis=1
    )
    
    return data

def create_message_size_throughput_plot(data, output_dir):
    """Create a scatter plot showing the relationship between message size and throughput."""
    if data is None or data.empty:
        print("No data available for visualization.")
        return
    
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    # Prepare data
    data = prepare_data(data)
    
    # Get unique message sizes and sort them
    unique_sizes = sorted(data['message_size_bytes'].unique())
    size_display_mapping = {size: get_display_size(size) for size in unique_sizes}
    
    # Create a unified plot showing throughput vs message size for all tests
    plt.figure(figsize=(14, 10))
    
    # Define colors and markers for different protocol/direction combinations
    colors = {
        'TCP TX': 'blue',
        'TCP RX': 'skyblue',
        'TCP BX': 'navy',
        'UDP TX': 'green',
        'UDP RX': 'lightgreen',
        'UDP BX': 'darkgreen'
    }
    
    markers = {
        'TCP TX': 'o',
        'TCP RX': 's',
        'TCP BX': '^',
        'UDP TX': 'D',
        'UDP RX': 'P',
        'UDP BX': 'X'
    }
    
    # Filter to only include successful tests for line plot
    successful_data = data[~data['failed']]
    
    # Group by protocol_direction and message_size
    for protocol_dir, group in successful_data.groupby('protocol_direction'):
        # Sort by message size
        group = group.sort_values('message_size_bytes')
        
        # Group by message size and compute mean throughput
        grouped = group.groupby('message_size_bytes')['throughput_gbps'].agg(['mean', 'std']).reset_index()
        
        # Plot line with error bars
        plt.plot(grouped['message_size_bytes'], grouped['mean'], 
                 marker=markers.get(protocol_dir, 'o'),
                 linestyle='-', 
                 color=colors.get(protocol_dir, 'gray'),
                 label=protocol_dir,
                 linewidth=2,
                 markersize=10)
        
        # Add error bars
        plt.errorbar(grouped['message_size_bytes'], grouped['mean'], 
                    yerr=grouped['std'], 
                    fmt='none', 
                    ecolor=colors.get(protocol_dir, 'gray'),
                    alpha=0.5)
    
    # Add markers for failed tests
    failed_data = data[data['failed']]
    for protocol_dir, group in failed_data.groupby('protocol_direction'):
        plt.scatter(group['message_size_bytes'], 
                   [0] * len(group),  # Place at y=0
                   marker='x',
                   color=colors.get(protocol_dir, 'gray'),
                   s=150,
                   label=f"{protocol_dir} Failed")
    
    # Set x-axis labels to message size names
    tick_positions = unique_sizes
    plt.xticks(tick_positions, [size_display_mapping[x] for x in tick_positions], rotation=45)
    
    plt.title('Network Throughput vs Message Size', fontsize=16)
    plt.xlabel('Message Size', fontsize=14)
    plt.ylabel('Throughput (Gbps)', fontsize=14)
    plt.grid(True, alpha=0.3, linestyle='--')
    
    # Add legend with good positioning
    plt.legend(loc='upper center', bbox_to_anchor=(0.5, -0.15), ncol=3, fontsize=12)
    
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'message_size_vs_throughput.png'), dpi=300, bbox_inches='tight')
    print(f"Saved message size vs throughput plot to {output_dir}/message_size_vs_throughput.png")
    plt.close()
    
    # Create a plot showing TCP vs UDP comparison
    plt.figure(figsize=(12, 8))
    
    # Combine all TCP and UDP data
    tcp_data = successful_data[successful_data['protocol'] == 'tcp']
    udp_data = successful_data[successful_data['protocol'] == 'udp']
    
    # Group by message size
    tcp_grouped = tcp_data.groupby('message_size_bytes')['throughput_gbps'].agg(['mean', 'std']).reset_index()
    udp_grouped = udp_data.groupby('message_size_bytes')['throughput_gbps'].agg(['mean', 'std']).reset_index()
    
    # Plot TCP data
    if not tcp_grouped.empty:
        plt.plot(tcp_grouped['message_size_bytes'], tcp_grouped['mean'], 
                marker='o', 
                linestyle='-', 
                color='blue', 
                label='TCP', 
                linewidth=3,
                markersize=10)
        plt.fill_between(tcp_grouped['message_size_bytes'], 
                         tcp_grouped['mean'] - tcp_grouped['std'],
                         tcp_grouped['mean'] + tcp_grouped['std'],
                         color='blue', alpha=0.2)
    
    # Plot UDP data
    if not udp_grouped.empty:
        plt.plot(udp_grouped['message_size_bytes'], udp_grouped['mean'], 
                marker='s', 
                linestyle='--', 
                color='green', 
                label='UDP', 
                linewidth=3,
                markersize=10)
        plt.fill_between(udp_grouped['message_size_bytes'], 
                         udp_grouped['mean'] - udp_grouped['std'],
                         udp_grouped['mean'] + udp_grouped['std'],
                         color='green', alpha=0.2)
    
    # Set x-axis labels
    plt.xticks(tick_positions, [size_display_mapping[x] for x in tick_positions], rotation=45)
    
    plt.title('TCP vs UDP Throughput by Message Size', fontsize=16)
    plt.xlabel('Message Size', fontsize=14)
    plt.ylabel('Throughput (Gbps)', fontsize=14)
    plt.grid(True, alpha=0.3, linestyle='--')
    plt.legend(loc='best', fontsize=14)
    
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'tcp_vs_udp_throughput.png'), dpi=300)
    print(f"Saved TCP vs UDP comparison plot to {output_dir}/tcp_vs_udp_throughput.png")
    plt.close()
    
    # Create a heatmap showing the relationship between protocol, direction, and message size
    plt.figure(figsize=(12, 8))
    
    # Pivot the data to create a matrix suitable for heatmap
    pivot_data = successful_data.pivot_table(
        values='throughput_gbps',
        index='protocol_direction',
        columns='message_size_display',
        aggfunc='mean'
    )
    
    # Sort the columns by message size (numerically)
    size_order = [get_display_size(size) for size in sorted(unique_sizes)]
    pivot_data = pivot_data.reindex(columns=size_order)
    
    # Create the heatmap
    sns.heatmap(pivot_data, annot=True, fmt='.2f', cmap='YlGnBu', linewidths=.5, cbar_kws={'label': 'Throughput (Gbps)'})
    
    plt.title('Throughput by Protocol, Direction, and Message Size', fontsize=16)
    plt.ylabel('Protocol and Direction', fontsize=14)
    plt.xlabel('Message Size', fontsize=14)
    
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'throughput_heatmap.png'), dpi=300)
    print(f"Saved throughput heatmap to {output_dir}/throughput_heatmap.png")
    plt.close()
    
    # Create a bar chart showing the impact of message size on each protocol/direction combination
    plt.figure(figsize=(14, 10))
    
    # Define protocol/directions to plot
    protocol_dirs = sorted(successful_data['protocol_direction'].unique())
    
    # Number of bars per group
    n_bars = len(protocol_dirs)
    # Width of each group of bars
    group_width = 0.8
    # Width of each individual bar
    bar_width = group_width / n_bars
    
    # Set up positions for groups and bars
    group_positions = np.arange(len(unique_sizes))
    
    # Plot bars for each protocol/direction
    for i, protocol_dir in enumerate(protocol_dirs):
        # Filter data for this protocol/direction
        data_subset = successful_data[successful_data['protocol_direction'] == protocol_dir]
        
        # Calculate mean throughput for each message size
        means = []
        for size in unique_sizes:
            throughput = data_subset[data_subset['message_size_bytes'] == size]['throughput_gbps'].mean()
            means.append(throughput if not np.isnan(throughput) else 0)
        
        # Calculate bar positions
        bar_positions = group_positions + (i - n_bars/2 + 0.5) * bar_width
        
        # Plot bars
        plt.bar(bar_positions, means, width=bar_width, 
                label=protocol_dir, 
                color=colors.get(protocol_dir, 'gray'),
                alpha=0.7)
    
    # Set x-axis labels
    plt.xticks(group_positions, [size_display_mapping[size] for size in unique_sizes], rotation=45)
    
    plt.title('Impact of Message Size on Network Throughput', fontsize=16)
    plt.xlabel('Message Size', fontsize=14)
    plt.ylabel('Throughput (Gbps)', fontsize=14)
    plt.grid(axis='y', linestyle='--', alpha=0.3)
    plt.legend(title='Protocol & Direction', loc='upper center', bbox_to_anchor=(0.5, -0.15), ncol=3, fontsize=12)
    
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'message_size_impact.png'), dpi=300, bbox_inches='tight')
    print(f"Saved message size impact plot to {output_dir}/message_size_impact.png")
    plt.close()

def main():
    parser = argparse.ArgumentParser(description='Generate specialized message size vs throughput visualizations')
    parser.add_argument('--csv', required=False, default='results/iperf3_results.csv', 
                        help='Path to the CSV results file')
    parser.add_argument('--json', required=False, default='results/iperf3_results.json', 
                        help='Path to the JSON results file')
    parser.add_argument('--output-dir', required=False, default='results/plots', 
                        help='Directory to save plots')
    
    args = parser.parse_args()
    
    # Resolve relative paths
    script_dir = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(script_dir, args.csv)
    json_path = os.path.join(script_dir, args.json)
    output_dir = os.path.join(script_dir, args.output_dir)
    
    # Read data from CSV and JSON files
    csv_data = read_csv_results(csv_path)
    json_data = read_json_results(json_path)
    
    # Combine the data
    data = combine_results(csv_data, json_data)
    
    if data is not None:
        create_message_size_throughput_plot(data, output_dir)
        print(f"All plots have been saved to {output_dir}")
    else:
        print("No valid data to plot.")

if __name__ == "__main__":
    main()
