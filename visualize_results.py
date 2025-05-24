#!/usr/bin/env python3
"""
Visualization script for iperf3 test results.
Creates plots of throughput vs message size for different protocols and directions.
Handles both CSV and JSON result files.
"""

import os
import json
import csv
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import argparse
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

def normalize_message_size(message_size):
    """Convert message size strings (like '64K') to numeric values in KB."""
    if pd.isna(message_size) or message_size == 'def' or message_size == 'default':
        return 'Default'
    
    size = str(message_size).strip()
    if size.endswith('K'):
        return int(size[:-1])
    elif size.endswith('M'):
        return int(size[:-1]) * 1024
    elif size.endswith('B'):
        return int(size[:-1]) / 1024
    else:
        try:
            return int(size) / 1024  # Assuming bytes if no unit
        except:
            return 'Default'
            
def get_human_readable_size(kb_size):
    """Convert KB size to human readable format (e.g., '64K', '128K')."""
    if kb_size == 'Default':
        return 'Default'
        
    if kb_size >= 1024:
        return f"{int(kb_size / 1024)}M"
    else:
        return f"{int(kb_size)}K"

def calculate_throughput(row):
    """Extract the appropriate throughput value based on protocol and direction."""
    # For TCP TX
    if row['protocol'] == 'tcp' and row['direction'] == 'tx':
        return row['sent_bps'] / 1_000_000_000  # Convert to Gbps
    
    # For TCP RX
    elif row['protocol'] == 'tcp' and row['direction'] == 'rx':
        return row['received_bps'] / 1_000_000_000  # Convert to Gbps
    
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
    
    # For UDP (any direction)
    elif row['protocol'] == 'udp':
        return row.get('udp_bps', 0) / 1_000_000_000  # Convert to Gbps
    
    return 0

def plot_throughput_vs_message_size(data, output_dir):
    """Create plots of throughput vs message size for different protocols and directions."""
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    # Prepare data - make a copy to avoid SettingWithCopyWarning
    data_copy = data.copy()
    data_copy['message_size_kb'] = data_copy['message_size_param'].apply(normalize_message_size)
    
    # Create separate dataframes for successful and failed tests
    failed_data = data_copy[data_copy['error_message'].notna()].copy()
    
    # Calculate throughput based on protocol and direction
    # For each group of protocol/direction/message_size, sum the appropriate throughput column
    # This directly uses the values from the CSV without recalculating
    
    # Group tests by protocol, direction, and message size
    successful_aggregated = []
    
    # Handle TCP TX
    tcp_tx = data_copy[(data_copy['protocol'] == 'tcp') & (data_copy['direction'] == 'tx') & (data_copy['error_message'].isna())].copy()
    if not tcp_tx.empty:
        tcp_tx_grouped = tcp_tx.groupby(['protocol', 'direction', 'message_size_kb'])['sent_bps'].sum().reset_index()
        tcp_tx_grouped['throughput_gbps'] = tcp_tx_grouped['sent_bps'] / 1_000_000_000
        successful_aggregated.append(tcp_tx_grouped[['protocol', 'direction', 'message_size_kb', 'throughput_gbps']])
    
    # Handle TCP RX
    tcp_rx = data_copy[(data_copy['protocol'] == 'tcp') & (data_copy['direction'] == 'rx') & (data_copy['error_message'].isna())].copy()
    if not tcp_rx.empty:
        tcp_rx_grouped = tcp_rx.groupby(['protocol', 'direction', 'message_size_kb'])['received_bps'].sum().reset_index()
        tcp_rx_grouped['throughput_gbps'] = tcp_rx_grouped['received_bps'] / 1_000_000_000
        successful_aggregated.append(tcp_rx_grouped[['protocol', 'direction', 'message_size_kb', 'throughput_gbps']])
    
    # Handle TCP BX (bidirectional)
    tcp_bx = data_copy[(data_copy['protocol'] == 'tcp') & (data_copy['direction'] == 'bx') & (data_copy['error_message'].isna())].copy()
    if not tcp_bx.empty:
        # For BX, we average sent and received bits per second
        tcp_bx_grouped = tcp_bx.groupby(['protocol', 'direction', 'message_size_kb']).agg({
            'sent_bps': 'sum',
            'received_bps': 'sum'
        }).reset_index()
        tcp_bx_grouped['throughput_gbps'] = ((tcp_bx_grouped['sent_bps'] + tcp_bx_grouped['received_bps']) / 2) / 1_000_000_000
        successful_aggregated.append(tcp_bx_grouped[['protocol', 'direction', 'message_size_kb', 'throughput_gbps']])
    
    # Handle UDP (all directions)
    udp_data = data_copy[(data_copy['protocol'] == 'udp') & (data_copy['error_message'].isna())].copy()
    if not udp_data.empty:
        # Calculate UDP throughput based on direction
        for direction in udp_data['direction'].unique():
            udp_dir = udp_data[udp_data['direction'] == direction].copy()
            if 'udp_bps' in udp_dir.columns:
                udp_grouped = udp_dir.groupby(['protocol', 'direction', 'message_size_kb'])['udp_bps'].sum().reset_index()
                udp_grouped['throughput_gbps'] = udp_grouped['udp_bps'] / 1_000_000_000
                successful_aggregated.append(udp_grouped[['protocol', 'direction', 'message_size_kb', 'throughput_gbps']])
    
    # Combine all the aggregated data
    if successful_aggregated:
        successful_aggregated = pd.concat(successful_aggregated, ignore_index=True)
        
        # Print statistics about the aggregated data
        print("\nAfter direct aggregation:")
        print(f"Total successful combinations: {len(successful_aggregated)}")
        
        for (protocol, direction), group in successful_aggregated.groupby(['protocol', 'direction']):
            avg_throughput = group['throughput_gbps'].mean()
            print(f"{protocol.upper()} {direction.upper()} - Average throughput: {avg_throughput:.2f} Gbps")
    
    print(f"After averaging repeated test runs: {len(successful_aggregated)} unique parameter combinations")
    
    # Group by protocol and direction
    grouped = successful_aggregated.groupby(['protocol', 'direction'])
    failed_grouped = failed_data.groupby(['protocol', 'direction'])
    
    # Check the unique values we have for better plotting
    msg_sizes = sorted([ms for ms in data_copy['message_size_kb'].unique() if ms != 'Default'], 
                       key=lambda x: float(x) if isinstance(x, (int, float)) else 0)
    
    # Add 'Default' to the end if it exists
    if 'Default' in data_copy['message_size_kb'].unique():
        msg_sizes.append('Default')
    
    # Plot for each protocol and direction
    for (protocol, direction), group in grouped:
        plt.figure(figsize=(10, 6))
        
        # Group by message size and calculate mean throughput with error bars
        msg_size_groups = group.groupby('message_size_kb')
        
        x_values = []
        y_values = []
        yerr_values = []
        x_labels = []
        
        for msg_size, msg_group in msg_size_groups:
            x_values.append(len(x_labels))
            y_values.append(msg_group['throughput_gbps'].mean())
            yerr_values.append(msg_group['throughput_gbps'].std())
            x_labels.append(str(msg_size))
        
        # Plot successful tests as bars
        plt.bar(x_values, y_values, yerr=yerr_values, capsize=5, alpha=0.7, 
                color='blue' if protocol == 'tcp' else 'green',
                label="Successful Tests")
        
        # Add markers for failed tests if any
        if (protocol, direction) in failed_grouped.groups:
            failed_group = failed_grouped.get_group((protocol, direction))
            failed_msg_sizes = failed_group['message_size_kb'].unique()
            
            for msg_size in failed_msg_sizes:
                if msg_size in x_labels:
                    x_pos = x_labels.index(str(msg_size))
                    plt.scatter(x_pos, 0, color='red', marker='x', s=120, 
                               label="Failed Tests" if msg_size == failed_msg_sizes[0] else "")
        
        plt.xticks(x_values, x_labels)
        plt.title(f'Throughput vs Message Size for {protocol.upper()} {direction.upper()}')
        plt.xlabel('Message Size (KB)')
        plt.ylabel('Throughput (Gbps)')
        plt.grid(axis='y', linestyle='--', alpha=0.7)
        
        # Add throughput values on top of bars
        for i, v in enumerate(y_values):
            plt.text(i, v + 0.5, f'{v:.2f}', ha='center')
        
        # Add legend if there are failed tests
        if (protocol, direction) in failed_grouped.groups:
            plt.legend()
        
        # Save the plot
        plot_filename = os.path.join(output_dir, f'throughput_{protocol}_{direction}.png')
        plt.savefig(plot_filename)
        print(f"Plot saved to {plot_filename}")
        plt.close()
    
    # Aggregate failed tests - make a copy to avoid SettingWithCopyWarning
    if not failed_data.empty:
        failed_data.loc[:, 'message_size_kb'] = failed_data['message_size_param'].apply(normalize_message_size)
        failed_aggregated = failed_data.groupby(['protocol', 'direction', 'message_size_kb']).size().reset_index(name='count')
        failed_grouped = failed_aggregated.groupby(['protocol', 'direction'])
    else:
        failed_grouped = pd.DataFrame(columns=['protocol', 'direction', 'message_size_kb', 'count']).groupby(['protocol', 'direction'])
    
    # Create separate plots for UDP failed tests if no successful tests
    for (protocol, direction), group in failed_grouped:
        if (protocol, direction) not in grouped.groups:
            plt.figure(figsize=(10, 6))
            
            # Get message sizes for failed tests
            failed_msg_sizes = group['message_size_kb'].unique()
            x_values = list(range(len(failed_msg_sizes)))
            
            # Plot red X marks at y=0 for failed tests
            plt.scatter(x_values, [0] * len(failed_msg_sizes), color='red', marker='x', s=120, label="Failed Tests")
            plt.xticks(x_values, [str(ms) for ms in failed_msg_sizes])
            
            plt.title(f'Failed Tests for {protocol.upper()} {direction.upper()}')
            plt.xlabel('Message Size (KB)')
            plt.ylabel('Throughput (Gbps)')
            plt.ylim(0, 1)  # Set y-axis limit to make the X marks visible
            plt.text(len(failed_msg_sizes)/2, 0.5, 'All tests failed', 
                    ha='center', va='center', fontsize=12, color='red')
            plt.legend()
            
            # Save the plot
            plot_filename = os.path.join(output_dir, f'failed_{protocol}_{direction}.png')
            plt.savefig(plot_filename)
            print(f"Failed tests plot saved to {plot_filename}")
            plt.close()
    
    # Create a combined plot for comparing protocols and directions
    plt.figure(figsize=(12, 8))
    bar_width = 0.2
    index = np.arange(len(msg_sizes))
    colors = {'tcp_tx': 'blue', 'tcp_rx': 'skyblue', 'udp_tx': 'green', 'udp_rx': 'lightgreen', 
              'tcp_bx': 'darkblue', 'udp_bx': 'darkgreen'}
    
    i = 0
    legend_handles = []
    
    # Plot successful data
    for (protocol, direction), group in grouped:
        msg_size_groups = group.groupby('message_size_kb')
        
        y_values = []
        x_positions = []
        
        for msg_size in msg_sizes:
            if msg_size in msg_size_groups.groups:
                msg_group = msg_size_groups.get_group(msg_size)
                y_values.append(msg_group['throughput_gbps'].mean())
                x_pos = msg_sizes.index(msg_size)
                x_positions.append(x_pos + i * bar_width)
            else:
                x_pos = msg_sizes.index(msg_size)
                x_positions.append(x_pos + i * bar_width)
                y_values.append(0)  # No data for this combination
        
        label = f"{protocol.upper()} {direction.upper()}"
        color = colors.get(f"{protocol}_{direction}", 'gray')
        bar = plt.bar([x + i * bar_width - bar_width * (len(grouped.groups) / 2) for x in index], 
                     y_values, bar_width, label=label, color=color, alpha=0.7)
        legend_handles.append(bar)
        i += 1
    
    # Add markers for failed tests
    failed_protocols = []
    for (protocol, direction), group in failed_grouped:
        failed_msg_kb = group['message_size_kb'].unique()
        
        # Skip if we've already added this protocol to the legend
        if protocol in failed_protocols:
            continue
        
        failed_x = []
        for msg_size in failed_msg_kb:
            if msg_size in msg_sizes:
                failed_x.append(msg_sizes.index(msg_size))
        
        if failed_x:
            color = 'red' if protocol == 'tcp' else 'darkred'
            marker = plt.scatter(failed_x, [0]*len(failed_x), color=color, marker='x', s=120, 
                               label=f"Failed {protocol.upper()}")
            legend_handles.append(marker)
            failed_protocols.append(protocol)
    
    plt.xlabel('Message Size (KB)')
    plt.ylabel('Throughput (Gbps)')
    plt.title('Throughput Comparison by Protocol, Direction and Message Size')
    plt.xticks(index, [str(s) for s in msg_sizes])
    plt.legend()
    plt.grid(axis='y', linestyle='--', alpha=0.7)
    
    # Save the combined plot
    combined_plot_filename = os.path.join(output_dir, 'throughput_comparison.png')
    plt.savefig(combined_plot_filename)
    print(f"Combined plot saved to {combined_plot_filename}")
    plt.close()

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

def main():
    parser = argparse.ArgumentParser(description='Generate visualizations from iperf3 test results')
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
        # Print some information about the data
        print("\nData analysis:")
        
        # Count unique message sizes
        print(f"Unique message sizes: {data['message_size_param'].nunique()}")
        
        # Count unique protocols
        print(f"Unique protocols: {data['protocol'].nunique()} ({', '.join(data['protocol'].unique())})")
        
        # Count unique directions
        print(f"Unique directions: {data['direction'].nunique()} ({', '.join(data['direction'].unique())})")
        
        # Count unique ports
        print(f"Unique ports: {data['port'].nunique()}")
        
        # Count tests for each message size
        msg_size_counts = data.groupby(['protocol', 'direction', 'message_size_param']).size()
        print("\nTests per message size/protocol/direction:")
        print(msg_size_counts)
        
        # Create the visualizations
        plot_throughput_vs_message_size(data, output_dir)
        print(f"\nAll plots have been saved to {output_dir}")
    else:
        print("No valid data to plot.")
    
if __name__ == "__main__":
    main()
