import logging
import time 
import os 
import argparse 
import concurrent.futures # For parallel client execution
import itertools # For parameter combinations if needed, though manual loops are fine

from .config import TestConfiguration, ConfigError
from .iperf3_controller import RemoteServerManager, run_iperf3_client_wrapper # Import wrapper
from .network import check_ssh_connectivity, get_local_ip_address
from .results import ResultsCollector, ReportGenerator 
from .utils import ConfigError as UtilConfigError

# Logger for this module - will be configured by main()
logger = logging.getLogger(__name__)

class IperfTestRunner:
    """
    Orchestrates iperf3 tests based on a provided configuration and CLI arguments.
    Manages remote iperf3 servers and runs client tests.
    """
    def __init__(self, config_filepath, cli_args=None):
        """
        Initializes the IperfTestRunner.

        Args:
            config_filepath (str): Path to the test configuration JSON file.
            cli_args (argparse.Namespace, optional): Parsed CLI arguments.
        """
        logger.info(f"Initializing IperfTestRunner with config: {config_filepath}")
        try:
            self.config = TestConfiguration(config_filepath=config_filepath)
        except ConfigError as e: # This is the ConfigError from .config module
            logger.error(f"Failed to load configuration from {config_filepath}: {e}")
            raise

        self.server_manager = None
        self.local_ip = None
        self.results_collector = ResultsCollector()
        
        if cli_args:
            self._apply_cli_overrides(cli_args)

    def _apply_cli_overrides(self, cli_args):
        """
        Applies CLI arguments to override configuration parameters.
        """
        logger.info("Applying CLI overrides to configuration...")
        if cli_args.duration is not None:
            logger.info(f"Overriding test_duration from {self.config.test_parameters.get('test_duration')} to {cli_args.duration}")
            self.config.test_parameters['test_duration'] = cli_args.duration
        
        if cli_args.output_dir:
            logger.info(f"Overriding results_directory from {self.config.output_config.get('results_directory')} to {cli_args.output_dir}")
            self.config.output_config['results_directory'] = cli_args.output_dir

        # Store iperf3_path from CLI into the config object for consistent access
        # We create a new key or update an existing one in execution_config
        if 'execution_config' not in self.config.data: # Ensure execution_config section exists
            self.config.data['execution_config'] = {}
        
        # Update the iperf3_path in the main config object so it's accessible globally
        # The TestConfiguration properties will also need to be updated or this needs to be accessed via self.config.data
        # For simplicity, we'll store it and ensure it's pulled when needed.
        # A cleaner way might be to have TestConfiguration handle updates.
        
        original_iperf3_path = self.config.iperf3_path # Uses property, might be from default
        if cli_args.iperf3_path:
            logger.info(f"Overriding iperf3_path from {original_iperf3_path} to {cli_args.iperf3_path}")
            # This directly modifies the loaded config's execution_config section.
            # If TestConfiguration properties cache values, this might need TestConfiguration.update_property()
            self.config.execution_config['iperf3_path'] = cli_args.iperf3_path
        elif not original_iperf3_path: # If not in config and not in CLI, set to default "iperf3"
             self.config.execution_config['iperf3_path'] = "iperf3"
        
        # Ensure the property reflects the change if it was made
        # This assumes the property self.config.iperf3_path will now pick up the change from self.config.execution_config
        logger.info(f"Effective iperf3_path after overrides: {self.config.iperf3_path}")


    def _setup_environment(self):
        """
        Sets up the testing environment: gets IPs, checks SSH, starts remote servers.
        Returns True on success, False on failure.
        """
        logger.info("--- Setting up testing environment ---")
        current_iperf3_path = self.config.iperf3_path # Get potentially overridden path

        # Check for client-only mode
        client_only = self.config.network_config.get("client_only", False)
        if client_only:
            logger.info("Client-only mode enabled. Skipping remote server management.")
            try:
                self.local_ip = get_local_ip_address()
                logger.info(f"Auto-detected local IP: {self.local_ip}")
            except RuntimeError as e:
                logger.error(f"Failed to auto-detect local IP: {e}")
                return False
            return True

        # Get local IP
        configured_local_ip = self.config.network_config.get("local_ip", "auto-detect")
        if configured_local_ip and configured_local_ip.lower() != "auto-detect":
            self.local_ip = configured_local_ip
            logger.info(f"Using configured local IP: {self.local_ip}")
        else:
            try:
                self.local_ip = get_local_ip_address()
                logger.info(f"Auto-detected local IP: {self.local_ip}")
            except RuntimeError as e:
                logger.error(f"Failed to auto-detect local IP: {e}")
                return False

        # Check for SSH credentials
        remote_ip = self.config.network_config.get("remote_ip")
        ssh_user = self.config.network_config.get("ssh_user")
        ssh_key = self.config.network_config.get("ssh_key_path")
        ssh_pass = self.config.network_config.get("ssh_password")
        if not remote_ip or not ssh_user:
            logger.error("Remote IP or SSH user not configured. Cannot proceed. If the remote server is already running iperf3, set 'client_only': true in the config.")
            return False

        # Check SSH connectivity
        logger.info(f"Attempting SSH connectivity to {ssh_user}@{remote_ip}...")
        if not check_ssh_connectivity(remote_ip, ssh_user, ssh_key, ssh_pass):
            logger.error("SSH connectivity failed. Cannot proceed.")
            return False
        logger.info("SSH connectivity successful.")

        # Start remote iperf3 servers
        self.server_manager = RemoteServerManager(
            ssh_user=ssh_user,
            remote_ip=remote_ip,
            ssh_key_path=ssh_key,
            port_range_start=self.config.network_config.get("port_range", {}).get("start", 52001),
            port_range_end=self.config.network_config.get("port_range", {}).get("end", 52016),
            iperf3_path=current_iperf3_path,
            ssh_password=ssh_pass
        )
        self.server_manager.start_remote_servers()
        if not self.server_manager.active_server_pids:
            logger.error("Failed to start any iperf3 servers on the remote machine. Aborting.")
            return False
        return True

    def _cleanup_environment(self):
        """
        Cleans up the testing environment by stopping remote servers.
        """
        logger.info("--- Cleaning up testing environment ---")
        if self.server_manager:
            logger.info("Stopping remote iperf3 servers...")
            self.server_manager.stop_remote_servers()
            logger.info("Remote iperf3 servers stop command issued.")
        else:
            logger.info("No server manager initialized, skipping server stop.")
        logger.info("--- Environment cleanup complete ---")

    def execute_tests(self): # Renamed from run_single_test
        """
        Runs the iperf3 test suite based on configuration.
        (Currently runs a single representative test).
        """
        try:
            if not self._setup_environment():
                logger.error("Environment setup failed. Aborting test run.")
                return 

            logger.info("--- Iterating through Test Parameter Matrix ---")

            # Retrieve test parameter lists from config
            tp_config = self.config.test_parameters if isinstance(self.config.test_parameters, dict) else {}
            protocols = tp_config.get('protocols', ['tcp'])
            directions = tp_config.get('directions', ['tx'])
            message_sizes = tp_config.get('message_sizes', [None]) 
            window_sizes = tp_config.get('window_sizes', [None])
            iperf3_P_streams_list = tp_config.get('parallel_streams', [1]) # -P option for iperf3
            base_test_duration = self.config.test_parameters.get('test_duration', 10)
            current_iperf3_path = self.config.iperf3_path

            # Determine ports to use
            if self.server_manager is not None:
                active_ports = list(self.server_manager.active_server_pids.keys())
            else:
                # Client-only mode: use port(s) from config
                port_range = self.config.network_config.get("port_range", {})
                port_start = port_range.get("start", 52001)
                port_end = port_range.get("end", port_start)
                active_ports = list(range(port_start, port_end + 1))
                logger.info(f"Client-only mode: using ports from config: {active_ports}")

            target_ip = self.config.remote_ip # From network_config, accessed via property

            # Max concurrent clients for ThreadPoolExecutor
            # execution_config is accessed via property self.config.execution_config
            exec_conf = self.config.execution_config if isinstance(self.config.execution_config, dict) else {}
            max_workers_config = exec_conf.get('max_concurrent_clients_per_iteration', 0)
            
            if max_workers_config <= 0: # If 0 or not set, use number of active ports
                max_workers = len(active_ports)
            else:
                max_workers = min(max_workers_config, len(active_ports))
            
            logger.info(f"Max concurrent iperf3 clients per iteration: {max_workers}")

            # Main parameter matrix iteration
            for protocol in protocols:
                for direction in directions:
                    for msg_size in message_sizes:
                        current_window_sizes = window_sizes if protocol.lower() == 'tcp' else [None]
                        for window_size in current_window_sizes:
                            for p_streams in iperf3_P_streams_list:
                                test_combination_title = (
                                    f"Proto={protocol}, Dir={direction}, MsgSize={msg_size or 'def'}, "
                                    f"WinSize={window_size or 'def'}, PStreams={p_streams}, Duration={base_test_duration}"
                                )
                                logger.info(f"--- Starting test combination: {test_combination_title} ---")
                                
                                tasks = []
                                with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                                    for port in active_ports:
                                        # Unique title for this specific test run instance
                                        # This title is used for logging and can be part of the iperf3 -T flag
                                        specific_run_title_prefix = (
                                            f"{protocol}_{direction}_P{p_streams}_M{msg_size or 'def'}_W{window_size or 'def'}_D{base_test_duration}"
                                        )
                                        # This title is for reporting and ensuring uniqueness in collected results
                                        reportable_title = f"{specific_run_title_prefix}_port{port}"


                                        full_test_params = {
                                            'target_ip': target_ip,
                                            'port': port,
                                            'protocol': protocol,
                                            'direction': direction,
                                            'message_size': msg_size,
                                            'window_size': window_size,
                                            'duration': base_test_duration,
                                            'parallel_streams': p_streams, # iperf3 -P option
                                            'iperf3_path': current_iperf3_path,
                                            'title': reportable_title, # Specific title for this run for reporting
                                            'title_prefix': specific_run_title_prefix, # Base for iperf3 -T flag
                                            'json_output': True, # Wrapper expects to deal with JSON
                                            'client_options': tp_config.get('client_options', []) # Global client options
                                        }
                                        
                                        logger.debug(f"Submitting task for port {port} with params: {full_test_params}")
                                        tasks.append(executor.submit(run_iperf3_client_wrapper, full_test_params))

                                    for future in concurrent.futures.as_completed(tasks):
                                        try:
                                            original_params, client_json_output = future.result()
                                            if client_json_output:
                                                self.results_collector.add_test_result(client_json_output, original_params)
                                                if isinstance(client_json_output, dict) and client_json_output.get("error"):
                                                    logger.error(f"Test '{original_params.get('title', 'N/A')}' reported an error: {client_json_output['error']}")
                                                else:
                                                    logger.info(f"Test '{original_params.get('title', 'N/A')}' completed.")
                                            else:
                                                logger.error(f"Test '{original_params.get('title', 'N/A')}' failed or produced no JSON output.")
                                                # Store a placeholder for failed tests
                                                self.results_collector.add_test_result(
                                                    {"error": "Client execution failed or returned no data"}, 
                                                    original_params
                                                )
                                        except Exception as e:
                                            # This catches errors from future.result() itself (e.g., if the wrapper function had an unhandled exception)
                                            # or if the task was cancelled, etc.
                                            # We need to know which params failed. This is tricky if future doesn't hold them.
                                            # For now, logging a general error for the combination.
                                            logger.error(f"Exception processing a client result for combination '{test_combination_title}': {e}", exc_info=True)
                                            # Attempt to add a placeholder if we could identify the params.
                                            # This requires the wrapper to be more robust or future to hold params.
                                            # For now, this specific failure might not be directly linked to its params in results.
                                
                                logger.info(f"--- Finished test combination: {test_combination_title} ---")
            
            logger.info("--- All test combinations complete ---")
            self._generate_reports()

        finally:
            self._cleanup_environment()


    def _generate_reports(self):
        """
        Generates reports based on collected results and configuration.
        """
        logger.info("--- Generating reports ---")
        all_results = self.results_collector.get_all_results()
        if not all_results:
            logger.info("No results collected, skipping report generation.")
            return

        output_conf = self.config.output_config
        # results_directory is now potentially overridden by CLI
        results_dir = output_conf.get('results_directory', 'results') 
        logger.info(f"Reports will be saved to: {os.path.abspath(results_dir)}")

        report_generator = ReportGenerator(all_results, results_directory=results_dir)

        if output_conf.get('save_to_file', True):
            json_filename = output_conf.get('json_report_filename', 'iperf3_results.json')
            csv_filename = output_conf.get('csv_report_filename', 'iperf3_results.csv')
            results_format = output_conf.get('results_format', 'all').lower() # Default to 'all'

            if results_format in ['json', 'all']:
                 logger.info(f"Generating JSON report: {os.path.join(results_dir, json_filename)}")
                 report_generator.generate_json_report(filename=json_filename)
            
            if results_format in ['csv', 'all']:
                 logger.info(f"Generating CSV report: {os.path.join(results_dir, csv_filename)}")
                 report_generator.generate_csv_report(filename=csv_filename)
            
            if results_format not in ['json', 'csv', 'all']: # Backward compatibility
                logger.warning(f"Unknown 'results_format': {results_format}. Defaulting to generating all reports if specific toggles are on.")
                if output_conf.get('json_output', True): 
                    report_generator.generate_json_report(filename=json_filename)
                if output_conf.get('csv_export', True): 
                    report_generator.generate_csv_report(filename=csv_filename)
        else:
            logger.info("Report generation to file is disabled in configuration (save_to_file: false).")
        
        logger.info("--- Report generation phase complete ---")
        # Force JSON report generation for debugging
        output_conf = self.config.output_config
        results_dir = output_conf.get('results_directory', 'results')
        json_filename = output_conf.get('json_report_filename', 'iperf3_results.json')
        report_generator = ReportGenerator(self.results_collector.get_all_results(), results_directory=results_dir)
        report_generator.generate_json_report(filename=json_filename)

def main():
    """
    Main function to initialize and run the IperfTestRunner.
    """
    parser = argparse.ArgumentParser(description="iperf3 Test Automation Suite")
    parser.add_argument(
        "--config", 
        type=str, 
        required=True, 
        help="Path to the JSON configuration file."
    )
    parser.add_argument(
        "--dry-run", 
        action="store_true", 
        help="Validate config, check SSH, print planned actions, then exit."
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true", 
        help="Increase logging verbosity to DEBUG."
    )
    parser.add_argument(
        "--log-file", 
        type=str, 
        help="Path to a file where logs should be written."
    )
    parser.add_argument(
        "--duration", 
        type=int, 
        help="Override test_duration from the config file (seconds)."
    )
    parser.add_argument(
        "--output-dir", 
        type=str, 
        help="Override results_directory from the output config."
    )
    parser.add_argument(
        "--iperf3-path", 
        type=str, 
        help="Path to the iperf3 executable (local client and remote server)."
    )
    args = parser.parse_args()

    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    log_format = '%(asctime)s - %(levelname)s - %(name)s - %(module)s.%(funcName)s - %(message)s'
    
    log_handlers = [logging.StreamHandler()] # Log to console by default
    if args.log_file:
        try:
            file_handler = logging.FileHandler(args.log_file, mode='w')
            file_handler.setFormatter(logging.Formatter(log_format))
            log_handlers.append(file_handler)
        except IOError as e:
            logging.error(f"Failed to open log file {args.log_file}: {e}")
            # Continue with console logging only

    logging.basicConfig(level=log_level, format=log_format, handlers=log_handlers, datefmt='%Y-%m-%d %H:%M:%S')

    logger.info("========== Starting iperf3 Test Automation Suite ==========")
    logger.info(f"CLI Arguments: {args}")


    if args.dry_run:
        logger.info("--- Dry Run Mode Activated ---")
        try:
            config = TestConfiguration(config_filepath=args.config)
            logger.info(f"Configuration loaded successfully from {args.config}")
            
            # Apply potential iperf3_path override for dry-run checks if any remote commands were to be shown
            effective_iperf3_path = args.iperf3_path if args.iperf3_path else config.iperf3_path
            logger.info(f"Effective iPerf3 path for dry run: {effective_iperf3_path}")

            logger.info("Attempting to get local IP address...")
            local_ip = get_local_ip_address()
            logger.info(f"Local IP address: {local_ip}")

            remote_ip = config.remote_ip
            ssh_user = config.network_config.get("ssh_user")
            ssh_key = config.network_config.get("ssh_key_path")
            ssh_pass = config.network_config.get("ssh_password") # For paramiko if used by check_ssh

            if remote_ip and ssh_user:
                logger.info(f"Attempting SSH connectivity to {ssh_user}@{remote_ip}...")
                if check_ssh_connectivity(remote_ip, ssh_user, ssh_key, ssh_pass):
                    logger.info("SSH connectivity successful.")
                else:
                    logger.error("SSH connectivity failed.")
            else:
                logger.warning("Remote IP or SSH user not configured. Skipping SSH check.")
            
            logger.info("Dry run summary:")
            logger.info(f"  - Config file: {args.config}")
            logger.info(f"  - Local IP: {local_ip}")
            logger.info(f"  - Remote Target: {remote_ip if remote_ip else 'N/A'}")
            logger.info(f"  - Intended test duration (if not overridden by CLI): {config.test_duration}s")
            logger.info(f"  - CLI duration override: {args.duration if args.duration is not None else 'N/A'}")
            logger.info(f"  - Results directory (if not overridden by CLI): {config.output_config.get('results_directory')}")
            logger.info(f"  - CLI output_dir override: {args.output_dir if args.output_dir else 'N/A'}")
            logger.info(f"  - iPerf3 executable path: {effective_iperf3_path}")
            logger.info("Dry run complete. No tests will be executed.")

        except ConfigError as e:
            logger.error(f"Dry run failed: Configuration error from {args.config}: {e}")
        except RuntimeError as e:
            logger.error(f"Dry run failed: Runtime error: {e}")
        except Exception as e:
            logger.error(f"Dry run failed: An unexpected error: {e}", exc_info=True)
        finally:
            logger.info("========== iperf3 Test Automation Suite Finished (Dry Run) ==========")
            return

    runner = None # Initialize runner to None for robust error handling
    try:
        # Pass cli_args to IperfTestRunner for it to handle overrides
        runner = IperfTestRunner(config_filepath=args.config, cli_args=args)
        runner.execute_tests()
    except ConfigError as e: # This is the ConfigError from .config module
        logger.critical(f"Exiting due to critical configuration error: {e}")
    except Exception as e:
        logger.critical(f"An unexpected critical error occurred: {e}", exc_info=True)
        if runner and hasattr(runner, '_cleanup_environment'): # Check if runner and method exist
            logger.info("Attempting emergency cleanup due to unexpected error...")
            runner._cleanup_environment()
    finally:
        logger.info("========== iperf3 Test Automation Suite Finished ==========")

if __name__ == "__main__":
    main()
