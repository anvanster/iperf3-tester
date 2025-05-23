import json
from .utils import ConfigError

class TestConfiguration:
    """
    Manages loading, validation, and access to test configurations
    from a JSON file.
    """
    def __init__(self, config_filepath="iperf3_tester/test_config.json"):
        """
        Initializes the TestConfiguration object.

        Args:
            config_filepath (str): Path to the JSON configuration file.
        """
        self.config_filepath = config_filepath
        self.data = {}
        self.network_config = {}
        self.test_parameters = {}
        self.execution_config = {}
        self.output_config = {}
        self._load_config()

    def _load_config(self):
        """
        Loads and parses the JSON configuration file.
        Populates section attributes and validates the configuration.
        """
        try:
            with open(self.config_filepath, 'r') as f:
                self.data = json.load(f)
        except FileNotFoundError:
            raise ConfigError(f"Configuration file not found: {self.config_filepath}")
        except json.JSONDecodeError as e:
            raise ConfigError(f"Error decoding JSON from {self.config_filepath}: {e}")

        self._validate_config()

        self.network_config = self.data.get("network_config", {})
        self.test_parameters = self.data.get("test_parameters", {})
        self.execution_config = self.data.get("execution_config", {})
        self.output_config = self.data.get("output_config", {})

    def _validate_config(self):
        """
        Validates the presence of main configuration keys and performs
        basic type checks on critical parameters.
        """
        required_main_keys = [
            "network_config",
            "test_parameters",
            "execution_config",
            "output_config"
        ]
        for key in required_main_keys:
            if key not in self.data:
                raise ConfigError(f"Missing required configuration section: '{key}'")

        # Validate network_config
        nc = self.data.get("network_config", {})
        if not isinstance(nc.get("remote_ip"), str):
            raise ConfigError("network_config.remote_ip must be a string.")
        if not isinstance(nc.get("port_range"), dict):
            raise ConfigError("network_config.port_range must be a dictionary.")
        pr = nc.get("port_range", {})
        if "start" not in pr or "end" not in pr:
            raise ConfigError("network_config.port_range must have 'start' and 'end' keys.")
        if not isinstance(pr.get("start"), int) or not isinstance(pr.get("end"), int):
            raise ConfigError("network_config.port_range start and end values must be integers.")

        # Validate test_parameters
        tp = self.data.get("test_parameters", {})
        if not isinstance(tp.get("test_duration"), int):
            raise ConfigError("test_parameters.test_duration must be an integer.")

        # Add more specific validations as needed for other sections

    # --- Network Config Properties ---
    @property
    def remote_ip(self):
        return self.network_config.get("remote_ip")

    @property
    def port_range(self):
        return self.network_config.get("port_range")

    @property
    def protocol(self):
        return self.network_config.get("protocol")

    @property
    def bandwidth(self):
        return self.network_config.get("bandwidth")

    @property
    def packet_size(self):
        return self.network_config.get("packet_size")

    @property
    def tos(self):
        return self.network_config.get("tos")

    # --- Test Parameters Properties ---
    @property
    def test_duration(self):
        return self.test_parameters.get("test_duration")

    @property
    def parallel_streams(self):
        return self.test_parameters.get("parallel_streams")

    @property
    def reverse_mode(self):
        return self.test_parameters.get("reverse_mode")

    @property
    def test_type(self):
        return self.test_parameters.get("test_type")

    @property
    def reporting_interval(self):
        return self.test_parameters.get("reporting_interval")
    
    @property
    def warmup_time(self):
        return self.test_parameters.get("warmup_time")

    # --- Execution Config Properties ---
    @property
    def max_retries(self):
        return self.execution_config.get("max_retries")

    @property
    def retry_delay(self):
        return self.execution_config.get("retry_delay")

    @property
    def timeout_seconds(self):
        return self.execution_config.get("timeout_seconds")

    @property
    def iperf3_path(self):
        return self.execution_config.get("iperf3_path")

    # --- Output Config Properties ---
    @property
    def log_file(self):
        return self.output_config.get("log_file")

    @property
    def results_format(self):
        return self.output_config.get("results_format")

    @property
    def results_directory(self):
        return self.output_config.get("results_directory")

    @property
    def save_to_file(self):
        return self.output_config.get("save_to_file")

    @property
    def verbosity(self):
        return self.output_config.get("verbosity")

if __name__ == '__main__':
    # Example Usage (for testing purposes)
    try:
        # Assuming test_config.json is in the same directory or adjust path
        config = TestConfiguration(config_filepath="test_config.json") 
        print("Configuration loaded successfully!")
        print(f"Remote IP: {config.remote_ip}")
        print(f"Port Range: {config.port_range}")
        print(f"Test Duration: {config.test_duration}s")
        print(f"iPerf3 Path: {config.iperf3_path}")
        print(f"Log File: {config.log_file}")

        # Test validation by temporarily creating a bad config
        bad_config_data = {"bad_key": "value"}
        with open("bad_config.json", "w") as f:
            json.dump(bad_config_data, f)
        try:
            bad_cfg = TestConfiguration(config_filepath="bad_config.json")
        except ConfigError as e:
            print(f"\nCaught expected config error: {e}")
        
        # Test missing critical sub-key
        incomplete_config_data = {
            "network_config": {"remote_ip_missing": "1.2.3.4"}, 
            "test_parameters": {"test_duration": 5},
            "execution_config": {},
            "output_config": {}
        }
        with open("incomplete_config.json", "w") as f:
            json.dump(incomplete_config_data, f)
        try:
            incomplete_cfg = TestConfiguration(config_filepath="incomplete_config.json")
        except ConfigError as e:
            print(f"\nCaught expected config error for incomplete config: {e}")

    except ConfigError as e:
        print(f"Configuration Error: {e}")
    finally:
        # Clean up dummy files
        import os
        if os.path.exists("bad_config.json"):
            os.remove("bad_config.json")
        if os.path.exists("incomplete_config.json"):
            os.remove("incomplete_config.json")
