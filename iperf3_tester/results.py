import json
import csv
import os
import logging

logger = logging.getLogger(__name__)

class ResultsCollector:
    """
    Collects individual iperf3 test results along with their parameters.
    """
    def __init__(self):
        """
        Initializes the ResultsCollector with an empty list to store test results.
        """
        self.test_results = []
        logger.info("ResultsCollector initialized.")

    def add_test_result(self, result_data, test_params):
        """
        Adds a test result to the collection.

        Args:
            result_data (dict): The JSON object (dictionary) from run_iperf3_client.
            test_params (dict): A dictionary of parameters used for this test.
        """
        if not isinstance(result_data, dict):
            logger.warning(f"Received result_data is not a dict: {type(result_data)}. Skipping.")
            return
        if not isinstance(test_params, dict):
            logger.warning(f"Received test_params is not a dict: {type(test_params)}. Skipping.")
            return
            
        combined_result = {
            "parameters": test_params,
            "iperf_result": result_data
        }
        self.test_results.append(combined_result)
        logger.info(f"Added test result with params: {test_params.get('title', 'N/A')}")

    def get_all_results(self):
        """
        Returns all collected test results.

        Returns:
            list: A list of all test results.
        """
        return self.test_results

class ReportGenerator:
    """
    Generates reports (JSON, CSV) from collected iperf3 test results.
    """
    def __init__(self, results_data, results_directory="./results"):
        """
        Initializes the ReportGenerator.

        Args:
            results_data (list): A list of test results from ResultsCollector.
            results_directory (str): Directory to save report files.
        """
        self.results_data = results_data
        self.results_directory = results_directory
        
        try:
            os.makedirs(self.results_directory, exist_ok=True)
            logger.info(f"ReportGenerator initialized. Results will be saved to: {os.path.abspath(self.results_directory)}")
        except OSError as e:
            logger.error(f"Error creating results directory {self.results_directory}: {e}")
            # Fallback to current directory if creation fails, though this might not be ideal.
            self.results_directory = "." 
            logger.warning(f"Results will be saved to current directory: {os.path.abspath(self.results_directory)}")


    def generate_json_report(self, filename="iperf3_results.json"):
        """
        Generates a JSON report of all test results.

        Args:
            filename (str): Name of the JSON report file.
        """
        if not self.results_data:
            logger.info("No results data to generate JSON report.")
            return

        filepath = os.path.join(self.results_directory, filename)
        try:
            with open(filepath, 'w') as f:
                json.dump(self.results_data, f, indent=4)
            logger.info(f"JSON report successfully generated: {os.path.abspath(filepath)}")
        except IOError as e:
            logger.error(f"Error writing JSON report to {filepath}: {e}")
        except TypeError as e:
            logger.error(f"TypeError during JSON serialization for {filepath}: {e}. Ensure all data is serializable.")


    def generate_csv_report(self, filename="iperf3_results.csv"):
        """
        Generates a CSV report summarizing test results.

        Args:
            filename (str): Name of the CSV report file.
        """
        if not self.results_data:
            logger.info("No results data to generate CSV report.")
            return

        filepath = os.path.join(self.results_directory, filename)
        
        # Define headers - these should cover common and important fields
        # Adjust based on typical iperf3 JSON structure and desired output
        headers = [
            "title", "timestamp", "protocol", "direction", "port", "duration_sec",
            "parallel_streams", "message_size_param", "window_size_param", "target_ip",
            "iperf_version", "system_info", "cpu_utilization_percent",
            "sent_bps", "sent_bytes", "sent_retransmits", # TCP TX
            "received_bps", "received_bytes", # TCP RX
            "udp_bps", "udp_bytes", "udp_jitter_ms", "udp_lost_packets", "udp_lost_percent", # UDP
            "error_message", # If iperf_result contains an "error" key
            "sub_direction" # For BX mode: tx_leg_of_bx, rx_leg_of_bx
        ]

        flat_results = []

        def _process_single_leg(leg_iperf_res, common_params, leg_sub_direction):
            """Helper to process a single leg of a test (either a normal test or one leg of BX)."""
            if not leg_iperf_res or not isinstance(leg_iperf_res, dict): # Ensure leg_iperf_res is a dict
                logger.warning(f"Skipping leg processing for title '{common_params.get('title', 'N/A')}' due to missing or invalid data for sub_direction '{leg_sub_direction}'. Data: {leg_iperf_res}")
                # Create a row with error info if leg_iperf_res is problematic
                error_row = {**common_params} # Start with common parameters
                error_row["sub_direction"] = leg_sub_direction
                error_row["error_message"] = leg_iperf_res.get("error", "Leg data missing or invalid") if isinstance(leg_iperf_res, dict) else "Leg data missing or invalid"
                return error_row

            row = {**common_params} # Start with common parameters
            row["sub_direction"] = leg_sub_direction
            # Override direction for this leg if it's part of BX
            if leg_sub_direction == "tx_leg_of_bx": row["direction"] = "tx"
            elif leg_sub_direction == "rx_leg_of_bx": row["direction"] = "rx"
            
            row["error_message"] = leg_iperf_res.get("error") # Capture leg-specific error

            start_info = leg_iperf_res.get("start", {})
            if isinstance(start_info, dict):
                row["timestamp"] = start_info.get("timestamp", {}).get("time")
                row["iperf_version"] = start_info.get("version")
                row["system_info"] = start_info.get("system_info")
                cpu_util = start_info.get("cpu_utilization_percent", {})
                if isinstance(cpu_util, dict): row["cpu_utilization_percent"] = cpu_util.get("host_total")

            end_info = leg_iperf_res.get("end", {})
            if isinstance(end_info, dict):
                sum_sent = end_info.get("sum_sent", {})
                # For tx_leg_of_bx or normal tx (non-udp)
                if isinstance(sum_sent, dict) and row["direction"] == 'tx' and row["protocol"] != 'udp':
                    row["sent_bps"] = sum_sent.get("bits_per_second")
                    row["sent_bytes"] = sum_sent.get("bytes")
                    row["sent_retransmits"] = sum_sent.get("retransmits")

                sum_received = end_info.get("sum_received", {})
                # For rx_leg_of_bx or normal rx (non-udp)
                if isinstance(sum_received, dict) and row["direction"] == 'rx' and row["protocol"] != 'udp':
                    row["received_bps"] = sum_received.get("bits_per_second")
                    row["received_bytes"] = sum_received.get("bytes")

                # UDP sum (applies to sender for TX, receiver for RX)
                udp_sum = end_info.get("sum", {}) 
                if isinstance(udp_sum, dict) and row["protocol"] == "udp":
                    row["udp_bps"] = udp_sum.get("bits_per_second")
                    row["udp_bytes"] = udp_sum.get("bytes")
                    row["udp_jitter_ms"] = udp_sum.get("jitter_ms")
                    row["udp_lost_packets"] = udp_sum.get("lost_packets")
                    row["udp_lost_percent"] = udp_sum.get("lost_percent")
                    # For UDP TX, sum_sent might also be present and could be preferred by some
                    # but iperf3's own sum block is generally comprehensive for UDP.
            return row

        for res_item in self.results_data:
            params = res_item.get("parameters", {})
            iperf_res = res_item.get("iperf_result", {})

            common_params_for_row = {
                "title": params.get("title", "N/A"), # Use the specific title from params
                "protocol": params.get("protocol"),
                "port": params.get("port"),
                "duration_sec": params.get("duration"),
                "parallel_streams": params.get("parallel_streams"),
                "message_size_param": params.get("message_size"),
                "window_size_param": params.get("window_size"),
                "target_ip": params.get("target_ip"),
                "direction": params.get("direction"), # Original intended direction
            }
            
            if iperf_res and iperf_res.get("is_bidirectional"):
                common_params_for_row["error_message"] = iperf_res.get("error") # Top-level BX error
                
                tx_leg_res = iperf_res.get("tx_result")
                flat_results.append(_process_single_leg(tx_leg_res, common_params_for_row.copy(), "tx_leg_of_bx"))
                
                rx_leg_res = iperf_res.get("rx_result")
                flat_results.append(_process_single_leg(rx_leg_res, common_params_for_row.copy(), "rx_leg_of_bx"))
            else: # Not bidirectional or iperf_res is None/malformed
                # if iperf_res is None or not isinstance(iperf_res, dict), _process_single_leg will handle it.
                flat_results.append(_process_single_leg(iperf_res, common_params_for_row, params.get("direction", "N/A")))

        if not flat_results:
            logger.info("No processable data found to generate CSV report.")
            return

        try:
            with open(filepath, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=headers, extrasaction='ignore')
                writer.writeheader()
                writer.writerows(flat_results)
            logger.info(f"CSV report successfully generated: {os.path.abspath(filepath)}")
        except IOError as e:
            logger.error(f"Error writing CSV report to {filepath}: {e}")
        except Exception as e: # Catch other potential errors during CSV writing
            logger.error(f"An unexpected error occurred while writing CSV to {filepath}: {e}")

if __name__ == '__main__':
    # Example Usage (for testing this module directly)
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')

    # 1. Create a ResultsCollector
    collector = ResultsCollector()

    # 2. Add some dummy test results
    # Sample iperf3 JSON output (simplified)
    sample_iperf_output_tcp_tx = {
        "start": {
            "timestamp": {"time": "Sat, 25 May 2024 10:00:00 GMT"},
            "version": "iperf 3.9+",
            "system_info": "Linux example 5.4.0-100-generic x86_64",
            "cpu_utilization_percent": {"host_total": 10.5}
        },
        "end": {
            "sum_sent": {
                "bits_per_second": 938000000, # 938 Mbps
                "bytes": 117250000,
                "retransmits": 120
            }
        }
    }
    sample_params_tcp_tx = {
        "title_prefix": "tcp_tx_highspeed", "port": 5201, "protocol": "tcp", 
        "direction": "tx", "duration": 10, "parallel_streams": 1, 
        "message_size": "128K", "target_ip": "192.168.1.101"
    }
    collector.add_test_result(sample_iperf_output_tcp_tx, sample_params_tcp_tx)

    sample_iperf_output_udp_rx = {
        "start": {
            "timestamp": {"time": "Sat, 25 May 2024 10:01:00 GMT"},
            "version": "iperf 3.9+",
        },
        "end": {
            "sum": { # UDP often just has "sum"
                "bits_per_second": 9800000, # 9.8 Mbps
                "bytes": 1225000,
                "jitter_ms": 0.55,
                "lost_packets": 10,
                "lost_percent": 0.1
            }
        },
        "error": None # Explicitly no error
    }
    sample_params_udp_rx = {
        "title": "udp_rx_test_5202", "port": 5202, "protocol": "udp", 
        "direction": "rx", "duration": 10, "parallel_streams": 1, 
        "message_size": "1400B", "target_ip": "192.168.1.102"
    }
    collector.add_test_result(sample_iperf_output_udp_rx, sample_params_udp_rx)
    
    # Add a result with an error
    error_iperf_output = {"error": "connect failed: Connection refused"}
    error_params = {"title": "tcp_fail_test", "port": 5203, "protocol": "tcp", "direction": "tx"}
    collector.add_test_result(error_iperf_output, error_params)


    # 3. Get all results
    all_collected_results = collector.get_all_results()
    logger.info(f"Collected {len(all_collected_results)} results.")

    # 4. Generate reports
    # Create a temporary directory for testing if it doesn't exist
    test_results_dir = "temp_test_results_delete_me"
    report_gen = ReportGenerator(all_collected_results, results_directory=test_results_dir)
    
    report_gen.generate_json_report(filename="sample_results.json")
    report_gen.generate_csv_report(filename="sample_results.csv")

    logger.info(f"Example reports generated in '{os.path.abspath(test_results_dir)}'. Please review and delete this directory.")
    # To clean up, you might:
    # import shutil
    # if os.path.exists(test_results_dir):
    #     shutil.rmtree(test_results_dir)
    #     logger.info(f"Cleaned up temporary directory: {test_results_dir}")
