import subprocess
import logging
import time
import json
import shlex

# Configure basic logging for the module
# This will be configured by the main application. For direct testing, uncomment:
# logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
logger = logging.getLogger(__name__)

class RemoteServerManager:
    """
    Manages iperf3 servers on a remote machine via SSH.
    """
    def __init__(self, ssh_user, remote_ip, ssh_key_path=None, port_range_start=52001, port_range_end=52016, iperf3_path="iperf3"):
        """
        Initializes the RemoteServerManager.

        Args:
            ssh_user (str): Username for SSH connection.
            remote_ip (str): IP address of the remote server.
            ssh_key_path (str, optional): Path to SSH private key. Defaults to None.
            port_range_start (int, optional): Starting port for iperf3 servers.
            port_range_end (int, optional): Ending port for iperf3 servers.
            iperf3_path (str, optional): Path to the iperf3 executable on the remote server. Defaults to "iperf3".
        """
        self.ssh_user = ssh_user
        self.remote_ip = remote_ip
        self.ssh_key_path = ssh_key_path
        self.port_range_start = port_range_start
        self.port_range_end = port_range_end
        self.iperf3_path = iperf3_path # Store iperf3 path
        self.active_server_pids = {}  # Stores port: pid mapping

    def _execute_remote_command(self, command, check_output=False, timeout=30):
        """
        Executes a command on the remote server via SSH.

        Args:
            command (str): The command to execute.
            check_output (bool, optional): If True, returns stdout. Otherwise, returns CompletedProcess.
                                         Defaults to False.
            timeout (int, optional): Timeout for the command execution. Defaults to 30 seconds.

        Returns:
            str or subprocess.CompletedProcess: stdout if check_output is True, else CompletedProcess.
                                                Returns None on failure if not raising exception.

        Raises:
            subprocess.CalledProcessError: If command fails and check_output is True.
            subprocess.TimeoutExpired: If the command times out.
            Exception: For other underlying errors.
        """
        ssh_base_command = [
            "ssh",
            "-o", "StrictHostKeyChecking=no",
            "-o", "BatchMode=yes",
            "-o", f"ConnectTimeout={min(10, timeout)}" # Ensure connect timeout is reasonable
        ]
        if self.ssh_key_path:
            ssh_base_command.extend(["-i", self.ssh_key_path])
        
        ssh_base_command.append(f"{self.ssh_user}@{self.remote_ip}")
        full_command_list = ssh_base_command + [command]
        
        command_str_for_logging = " ".join(full_command_list)
        # Avoid logging sensitive parts of the command if necessary, though here it's mostly IPs/usernames
        logger.debug(f"Executing remote command: {command_str_for_logging}")

        try:
            process = subprocess.run(
                full_command_list,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False # We will check returncode manually
            )

            if process.returncode != 0:
                logger.error(
                    f"Remote command failed: {' '.join(full_command_list)}\n"
                    f"Return Code: {process.returncode}\n"
                    f"Stdout: {process.stdout.strip()}\n"
                    f"Stderr: {process.stderr.strip()}"
                )
                if check_output: # if we specifically need output, failure is more critical
                    # For pgrep, a non-zero exit code might mean "not found", which isn't always an error
                    # for the caller's logic. So, we don't raise CalledProcessError here universally.
                    # The caller must check the return code or output.
                    return None # Indicate failure or "not found"
                return process # Allow caller to inspect process details
            
            logger.debug(
                f"Remote command successful: {' '.join(full_command_list)}\n"
                f"Stdout: {process.stdout.strip()}"
            )

            if check_output:
                return process.stdout.strip()
            return process

        except subprocess.TimeoutExpired as e:
            logger.error(f"Remote command timed out: {command_str_for_logging}. Error: {e}")
            if check_output:
                return None
            # Re-raise or handle as per policy; for now, let it propagate if not check_output
            # Or, more consistently, return a specific indicator
            # For this implementation, returning None for check_output and letting caller handle is okay.
            # If not check_output, the caller might not expect a return value to check.
            raise  # Re-raise if the caller expects to handle it or it's a critical failure
        except Exception as e: # Catch other potential errors like FileNotFoundError for ssh
            logger.error(f"Error executing remote command '{command_str_for_logging}': {e}")
            if check_output:
                return None
            raise # Re-raise for unexpected errors

    def start_remote_servers(self):
        """
        Starts iperf3 servers on the remote machine for the configured port range.

        Returns:
            dict: A dictionary of port-to-PID mappings for successfully started servers.
                  Returns an empty dict if no servers could be started or PIDs found.
        """
        self.active_server_pids = {} # Clear any previous state
        successfully_started_count = 0
        
        logger.info(f"Attempting to start iperf3 servers on ports {self.port_range_start}-{self.port_range_end} on {self.remote_ip} using executable '{self.iperf3_path}'")

        for port in range(self.port_range_start, self.port_range_end + 1):
            iperf3_start_command = f"{self.iperf3_path} -s -D -p {port}" # Use self.iperf3_path
            logger.info(f"Starting iperf3 server on port {port}: {iperf3_start_command}")
            
            start_process = self._execute_remote_command(iperf3_start_command)
            
            if start_process is None or start_process.returncode != 0:
                logger.error(f"Failed to start iperf3 server on port {port}. Skipping PID check.")
                # Optionally, try to clean up if -D failed and it's somehow running in foreground
                # self._execute_remote_command(f"pkill -f \"iperf3 -s -p {port}\"") # More aggressive
                continue

            # Give server a moment to start before checking PID
            time.sleep(0.5) 

            # PID tracking command - ensure it's specific enough
            # Using -f to match the full command string.
            # Adding a non-greedy match for potential path before iperf3, e.g. /usr/bin/iperf3
            # Ensure pgrep matches the potentially modified iperf3_path
            pid_find_command = f"pgrep -f \"{self.iperf3_path} -s -D -p {port}\"" # Use self.iperf3_path
            logger.info(f"Attempting to find PID for iperf3 server on port {port} using: {pid_find_command}")
            
            pid_output = self._execute_remote_command(pid_find_command, check_output=True)

            if pid_output and pid_output.strip().isdigit():
                pid = pid_output.strip()
                self.active_server_pids[port] = pid
                successfully_started_count += 1
                logger.info(f"Successfully started iperf3 server on port {port} with PID {pid}.")
            else:
                logger.warning(
                    f"Could not find PID for iperf3 server on port {port}. "
                    f"pgrep output: '{pid_output}'. Server might have failed to stay up."
                )
                # Attempt to kill any lingering server on that port if PID not found, as -D might have failed
                # or it might be a zombie. This is a precaution.
                cleanup_command = f"pkill -f \"{self.iperf3_path} -s -D -p {port}\"" # Use self.iperf3_path
                logger.info(f"Attempting cleanup for port {port} due to PID not found: {cleanup_command}")
                self._execute_remote_command(cleanup_command)


        if successfully_started_count > 0:
            logger.info(f"Successfully started {successfully_started_count} iperf3 server(s) with PIDs: {self.active_server_pids}")
        else:
            logger.warning(f"No iperf3 servers were successfully started and verified with PIDs on {self.remote_ip}.")
            
        return self.active_server_pids

    def stop_remote_servers(self):
        """
        Stops all active iperf3 servers on the remote machine based on stored PIDs.
        """
        if not self.active_server_pids:
            logger.info("No active iperf3 server PIDs to stop.")
            return True # Nothing to do, considered successful

        logger.info(f"Attempting to stop iperf3 servers on {self.remote_ip} using PIDs: {list(self.active_server_pids.values())}")
        all_stopped_successfully = True

        for port, pid in self.active_server_pids.items():
            kill_command = f"kill {pid}"
            logger.info(f"Stopping iperf3 server on port {port} with PID {pid} using command: {kill_command}")
            
            kill_process = self._execute_remote_command(kill_command)
            
            if kill_process is None or kill_process.returncode != 0:
                logger.warning(f"Failed to kill iperf3 server with PID {pid} on port {port}. Return code: {kill_process.returncode if kill_process else 'N/A'}. Stderr: {kill_process.stderr.strip() if kill_process else 'N/A'}")
                # Fallback: Try to pkill by port as the PID might be gone or incorrect
                pkill_command = f"pkill -f \"{self.iperf3_path} -s -D -p {port}\"" # Use self.iperf3_path
                logger.info(f"Attempting fallback pkill for port {port}: {pkill_command}")
                fallback_kill_process = self._execute_remote_command(pkill_command)
                if fallback_kill_process is None or fallback_kill_process.returncode != 0:
                     logger.error(f"Fallback pkill also failed for port {port}.")
                     all_stopped_successfully = False
                else:
                    logger.info(f"Fallback pkill for port {port} seems to have worked or found nothing to kill.")
            else:
                logger.info(f"Successfully sent kill signal to PID {pid} for port {port}.")

        # As a final broader cleanup, one might consider pkill for any server in the port range
        # This is more aggressive and should be used if PID management proves unreliable.
        # For now, relying on PID and specific port pkill is preferred.
        # Example:
        # for port in range(self.port_range_start, self.port_range_end + 1):
        #     self._execute_remote_command(f"pkill -f \"{self.iperf3_path} -s -D -p {port}\"") # Use self.iperf3_path
        # logger.info("Performed additional pkill sweep for the port range.")

        self.active_server_pids = {} # Clear PIDs after attempting to stop
        logger.info("Finished stop_remote_servers routine.")
        return all_stopped_successfully

# Example Usage (for testing purposes, requires SSH setup)
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
    
    # --- Configuration for testing ---
    # Replace with your actual remote server details and SSH key if needed
    # Ensure the remote server has iperf3 installed and SSH access is configured
    # (e.g., key-based authentication without password prompt).
    
    # IMPORTANT: To test this, you need a remote machine where you can SSH
    # and run iperf3. 'localhost' can work if you SSH to your own machine.
    # Ensure the user specified has permissions to run iperf3 and pgrep/kill.
    
    # Example: ssh your_user@your_remote_ip "iperf3 -s -D -p 5201"
    #          ssh your_user@your_remote_ip "pgrep -f 'iperf3 -s -D -p 5201'"
    #          ssh your_user@your_remote_ip "kill <PID>"

    # Example Usage for RemoteServerManager (requires SSH setup)
    # To test this part, uncomment the following and provide necessary inputs.
    # TEST_SSH_USER = input("Enter SSH username for remote server: ")
    # TEST_REMOTE_IP = input("Enter remote server IP (e.g., localhost or an IP): ")
    # TEST_SSH_KEY_PATH = input("Enter path to SSH private key (optional, press Enter if none): ").strip()
    # if not TEST_SSH_KEY_PATH:
    #     TEST_SSH_KEY_PATH = None # Ensure it's None if empty

    # manager = RemoteServerManager( # Uses default ports from __init__ unless overridden here
    #     ssh_user=TEST_SSH_USER,
    #     remote_ip=TEST_REMOTE_IP,
    #     ssh_key_path=TEST_SSH_KEY_PATH,
    #     iperf3_path="/usr/local/bin/iperf3" # Example if iperf3 is in a non-standard remote path
    #     # To test with specific range for __main__, override here:
    #     # port_range_start=52001,
    #     # port_range_end=52003 
    # )

    # logger.info("--- Starting Remote Servers (Test) ---")
    started_pids = manager.start_remote_servers()
    if started_pids:
        logger.info(f"Servers started with PIDs: {started_pids}")
        logger.info(f"Number of active PIDs: {len(manager.active_server_pids)}")
        
        # Keep servers running for a bit
        logger.info("Servers will run for 15 seconds...")
        time.sleep(15)
        
        logger.info("--- Stopping Remote Servers (Test) ---")
        success_stop = manager.stop_remote_servers()
        logger.info(f"Stopping servers result: {'Successful' if success_stop else 'Issues encountered'}")
        logger.info(f"Number of active PIDs after stopping: {len(manager.active_server_pids)}")
    else:
        logger.error("Failed to start any remote iperf3 servers during test.")

    # Test stopping when no PIDs are stored
    logger.info("--- Test stopping with no active PIDs ---")
    manager.active_server_pids = {} # Ensure it's empty
    success_stop_empty = manager.stop_remote_servers()
    logger.info(f"Stopping servers when none active: {'Successful' if success_stop_empty else 'Issues encountered'}")

    logger.info("--- RemoteServerManager Test Complete ---")


# Helper function for parallel execution, ensures parameters are returned with results
def run_iperf3_client_wrapper(test_run_params_dict):
    """
    Wrapper for run_iperf3_client to be used with concurrent.futures.
    It takes a dictionary of parameters, calls run_iperf3_client,
    and returns the original parameters along with the client's output.

    Args:
        test_run_params_dict (dict): A dictionary containing all necessary
                                     parameters for run_iperf3_client and for reporting.
                                     Expected keys include: 'target_ip', 'port', 'protocol',
                                     'direction', 'message_size', 'window_size', 'duration',
                                     'parallel_streams', 'iperf3_path', 'title_prefix', 
                                     'client_options' (optional).
    Returns:
        tuple: (dict, dict or str or None)
               The first element is the original test_run_params_dict.
               The second element is the result from run_iperf3_client (JSON dict, string, or None).
    """
    # Extract parameters for run_iperf3_client from the input dictionary
    target_ip = test_run_params_dict['target_ip']
    port = test_run_params_dict['port']
    protocol = test_run_params_dict.get('protocol', 'tcp')
    direction = test_run_params_dict.get('direction', 'tx')
    message_size = test_run_params_dict.get('message_size') 
    window_size = test_run_params_dict.get('window_size')   
    duration = test_run_params_dict.get('duration', 10)
    # 'parallel_streams' in test_run_params_dict is iperf3's -P option
    parallel_streams_iperf_P = test_run_params_dict.get('parallel_streams', 1) 
    client_options = test_run_params_dict.get('client_options') 
    # json_output is True by default in wrapper as collector expects dict
    json_output = test_run_params_dict.get('json_output', True) 
    title_prefix = test_run_params_dict.get('title_prefix', 'test')
    iperf3_path = test_run_params_dict.get('iperf3_path', 'iperf3')

    # The title_prefix passed to run_iperf3_client will be further appended by it.
    # The 'title' key in test_run_params_dict should ideally be the most specific one for reporting.
    # If test_run_params_dict['title'] is already specific, run_iperf3_client's title_prefix argument
    # is more for its internal -T flag structure.
    # Let's assume test_run_params_dict['title'] is the unique identifier for this test combination.
    effective_iperf_title_prefix = test_run_params_dict.get('title', title_prefix)


    logger.debug(f"Wrapper executing run_iperf3_client for port {port} with effective title prefix {effective_iperf_title_prefix}")

    client_json_output = run_iperf3_client(
        target_ip=target_ip,
        port=port,
        protocol=protocol,
        direction=direction,
        message_size=message_size,
        window_size=window_size,
        duration=duration,
        parallel_streams=parallel_streams_iperf_P, # Pass the -P value
        client_options=client_options,
        json_output=json_output, 
        title_prefix=effective_iperf_title_prefix, # Use the specific title prefix
        iperf3_path=iperf3_path
    )
    
    # The original test_run_params_dict (which includes the specific 'title') is returned
    return test_run_params_dict, client_json_output
