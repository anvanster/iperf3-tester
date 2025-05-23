import socket
import subprocess
import logging

# Configure basic logging for the module
logger = logging.getLogger(__name__)
# If you want to see logs from this module, you'll need to configure the root logger
# e.g., logging.basicConfig(level=logging.INFO) in your main script.

PARAMIKO_AVAILABLE = False
try:
    import paramiko
    PARAMIKO_AVAILABLE = True
    logger.info("paramiko library found. SSH checks will use paramiko.")
except ImportError:
    logger.info("paramiko library not found. SSH checks will use subprocess fallback.")

def get_local_ip_address():
    """
    Attempts to determine a non-loopback local IP address.

    Connects to a public DNS server (Google's 8.8.8.8) to find the
    local IP address associated with the outbound network interface.
    No actual data is sent to the external server.

    Returns:
        str: The detected local IP address.

    Raises:
        RuntimeError: If the local IP address cannot be determined.
    """
    s = None
    try:
        # Connect to a known external server (doesn't send data)
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        return local_ip
    except socket.error as e:
        logger.error(f"Failed to get local IP address: {e}")
        raise RuntimeError(f"Could not determine local IP address: {e}")
    finally:
        if s:
            s.close()

def check_ssh_connectivity(remote_ip, ssh_user, ssh_key_path=None, ssh_password=None, timeout=10):
    """
    Checks SSH connectivity to a remote host.

    Prioritizes using the 'paramiko' library if available. Falls back to
    using the system 'ssh' command via 'subprocess' if 'paramiko' is not found.

    Args:
        remote_ip (str): The IP address of the remote host.
        ssh_user (str): The username for SSH login.
        ssh_key_path (str, optional): Path to the SSH private key. Defaults to None.
        ssh_password (str, optional): SSH password. Defaults to None.
                                      (Note: Using passwords directly is less secure).
        timeout (int, optional): Timeout in seconds for the connection attempt. Defaults to 10.

    Returns:
        bool: True if SSH connection is successful, False otherwise.
    """
    if not remote_ip or not ssh_user:
        logger.error("Remote IP and SSH user must be provided for SSH check.")
        return False

    if PARAMIKO_AVAILABLE:
        logger.info(f"Attempting SSH to {remote_ip} using paramiko.")
        client = None
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy()) # Not for production

            connect_args = {
                "hostname": remote_ip,
                "username": ssh_user,
                "timeout": timeout,
                "allow_agent": False, # Disable SSH agent
                "look_for_keys": False # Disable looking for keys in default locations
            }

            if ssh_key_path:
                logger.info(f"Using SSH key: {ssh_key_path}")
                connect_args["key_filename"] = ssh_key_path
            elif ssh_password:
                logger.info("Using SSH password.")
                connect_args["password"] = ssh_password
            else:
                # No key or password provided, paramiko might try other methods or fail.
                # For non-interactive, this usually means failure if no agent/default key works.
                logger.warning("Attempting SSH without explicit key or password.")


            client.connect(**connect_args)
            
            # Execute a simple command
            stdin, stdout, stderr = client.exec_command("echo SSH_CONNECTION_SUCCESSFUL", timeout=timeout)
            exit_status = stdout.channel.recv_exit_status() # Wait for command to complete
            output = stdout.read().decode().strip()

            if exit_status == 0 and "SSH_CONNECTION_SUCCESSFUL" in output:
                logger.info(f"SSH connection to {remote_ip} successful (paramiko).")
                return True
            else:
                logger.error(f"SSH command execution failed on {remote_ip} (paramiko). Status: {exit_status}, Output: {output}, Stderr: {stderr.read().decode()}")
                return False
        except paramiko.AuthenticationException as e:
            logger.error(f"SSH authentication failed for {ssh_user}@{remote_ip} (paramiko): {e}")
            return False
        except paramiko.SSHException as e:
            logger.error(f"SSH connection error to {remote_ip} (paramiko): {e}")
            return False
        except socket.error as e: # Covers gaierror, timeout, etc.
            logger.error(f"Socket error during SSH connection to {remote_ip} (paramiko): {e}")
            return False
        except Exception as e: # Catch any other unexpected errors
            logger.error(f"An unexpected error occurred with paramiko SSH to {remote_ip}: {e}")
            return False
        finally:
            if client:
                client.close()
    else:
        logger.info(f"Attempting SSH to {remote_ip} using subprocess.")
        try:
            ssh_command = [
                "ssh",
                "-o", "StrictHostKeyChecking=no",  # Not recommended for production
                "-o", "BatchMode=yes",            # Ensure non-interactive
                "-o", f"ConnectTimeout={timeout}"
            ]
            if ssh_key_path:
                ssh_command.extend(["-i", ssh_key_path])
            
            ssh_command.append(f"{ssh_user}@{remote_ip}")
            ssh_command.append("echo SSH_CONNECTION_SUCCESSFUL") # Simple command to test

            process = subprocess.run(
                ssh_command,
                capture_output=True,
                text=True,
                timeout=timeout + 5 # Give subprocess a bit more time than ssh internal timeout
            )
            
            if process.returncode == 0 and "SSH_CONNECTION_SUCCESSFUL" in process.stdout:
                logger.info(f"SSH connection to {remote_ip} successful (subprocess).")
                return True
            else:
                logger.error(
                    f"SSH connection to {remote_ip} failed (subprocess). "
                    f"Return code: {process.returncode}\n"
                    f"Stdout: {process.stdout.strip()}\n"
                    f"Stderr: {process.stderr.strip()}"
                )
                return False
        except subprocess.TimeoutExpired:
            logger.error(f"SSH connection to {remote_ip} timed out (subprocess).")
            return False
        except FileNotFoundError:
            logger.error("SSH command not found. Please ensure 'ssh' is installed and in PATH.")
            # This is a system configuration issue, might be better to raise an exception
            return False
        except Exception as e:
            logger.error(f"An unexpected error occurred with subprocess SSH to {remote_ip}: {e}")
            return False

if __name__ == '__main__':
    # Basic logging setup for testing the module directly
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')

    print("--- Testing get_local_ip_address ---")
    try:
        local_ip = get_local_ip_address()
        print(f"Detected local IP: {local_ip}")
    except RuntimeError as e:
        print(f"Error: {e}")

    print("\n--- Testing check_ssh_connectivity ---")
    # Replace with your actual test details.
    # This requires a host 'test_host_ip' and user 'test_user' to be accessible.
    # For a real test, you'd mock these or use a dedicated test VM.
    test_remote_ip = "localhost"  # Or a known accessible SSH server
    test_ssh_user = input(f"Enter SSH username for {test_remote_ip} (or press Enter to skip SSH tests): ")

    if test_ssh_user:
        # Test 1: No key, no password (might work if agent or unencrypted key is set up)
        # print(f"\nTesting SSH to {test_remote_ip} as {test_ssh_user} (no key/password)...")
        # status = check_ssh_connectivity(test_remote_ip, test_ssh_user)
        # print(f"SSH status (no key/password): {status}")

        test_ssh_key = input("Enter path to SSH private key (optional, press Enter to skip): ").strip()
        test_ssh_password = ""
        if not test_ssh_key:
            test_ssh_password = input("Enter SSH password (optional, press Enter to skip): ").strip()
        
        if test_ssh_key:
            print(f"\nTesting SSH to {test_remote_ip} as {test_ssh_user} with key {test_ssh_key}...")
            status_key = check_ssh_connectivity(test_remote_ip, test_ssh_user, ssh_key_path=test_ssh_key)
            print(f"SSH status (with key): {status_key}")

        if test_ssh_password: # Only try password if key wasn't provided or to test it specifically
            print(f"\nTesting SSH to {test_remote_ip} as {test_ssh_user} with password...")
            status_pass = check_ssh_connectivity(test_remote_ip, test_ssh_user, ssh_password=test_ssh_password)
            print(f"SSH status (with password): {status_pass}")
        
        # Test with a non-existent host to see failure
        print(f"\nTesting SSH to non_existent_host as {test_ssh_user} (expect failure)...")
        status_fail = check_ssh_connectivity("non_existent_host", test_ssh_user, ssh_key_path=test_ssh_key if test_ssh_key else None)
        print(f"SSH status (non_existent_host): {status_fail}")
    else:
        print("SSH tests skipped as no username was provided.")

    # Example of how to force subprocess for testing (if paramiko is installed)
    # print("\n--- Forcing subprocess SSH test ---")
    # global PARAMIKO_AVAILABLE
    # _original_paramiko_status = PARAMIKO_AVAILABLE
    # PARAMIKO_AVAILABLE = False # Temporarily disable paramiko
    # logger.info("Manually disabled paramiko for this test.")
    # status_subprocess_forced = check_ssh_connectivity(test_remote_ip, test_ssh_user, ssh_key_path=test_ssh_key if test_ssh_key else None)
    # print(f"SSH status (subprocess forced): {status_subprocess_forced}")
    # PARAMIKO_AVAILABLE = _original_paramiko_status # Restore
    # logger.info("Restored paramiko status.")
