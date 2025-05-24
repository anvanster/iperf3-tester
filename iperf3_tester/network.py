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
    Uses paramiko for password-based SSH if available, otherwise falls back to sshpass or ssh.
    """
    logger = logging.getLogger(__name__)
    if PARAMIKO_AVAILABLE and ssh_password:
        try:
            logger.info(f"Attempting SSH to {remote_ip} using paramiko.")
            import paramiko
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(
                hostname=remote_ip,
                username=ssh_user,
                password=ssh_password,
                key_filename=ssh_key_path if ssh_key_path else None,
                timeout=timeout,
                allow_agent=False,
                look_for_keys=False
            )
            stdin, stdout, stderr = client.exec_command('echo SSH_OK', timeout=timeout)
            output = stdout.read().decode().strip()
            client.close()
            if output == 'SSH_OK':
                logger.info(f"SSH connection to {remote_ip} successful (paramiko).")
                return True
            else:
                logger.error(f"SSH connection to {remote_ip} failed (paramiko). Output: {output}")
                return False
        except Exception as e:
            logger.error(f"Exception during SSH connectivity check with paramiko: {e}")
            return False
    else:
        # Use sshpass if password is provided
        if ssh_password:
            logger.debug(f"Using sshpass with password length: {len(ssh_password)}")
            ssh_cmd = [
                'sshpass', '-p', ssh_password,
                'ssh',
                '-o', 'StrictHostKeyChecking=no',
                '-o', 'BatchMode=yes',
                '-o', f'ConnectTimeout={min(10, timeout)}',
                f'{ssh_user}@{remote_ip}',
                'echo', 'SSH_OK'
            ]
        else:
            ssh_cmd = [
                'ssh',
                '-o', 'StrictHostKeyChecking=no',
                '-o', 'BatchMode=yes',
                '-o', f'ConnectTimeout={min(10, timeout)}',
            ]
            if ssh_key_path:
                ssh_cmd += ['-i', ssh_key_path]
            ssh_cmd += [f'{ssh_user}@{remote_ip}', 'echo', 'SSH_OK']
        logger.info(f"Attempting SSH to {remote_ip} using subprocess.")
        try:
            result = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=timeout)
            if result.returncode == 0 and 'SSH_OK' in result.stdout:
                logger.info(f"SSH connection to {remote_ip} successful.")
                return True
            else:
                logger.error(f"SSH connection to {remote_ip} failed (subprocess). Return code: {result.returncode}\nStdout: {result.stdout}\nStderr: {result.stderr}")
                return False
        except Exception as e:
            logger.error(f"Exception during SSH connectivity check: {e}")
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
