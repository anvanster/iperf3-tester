#!/bin/bash
# Simple script to run iperf3 tests to remote server

echo "=== Running iperf3 test to remote server 3.3.3.4 ==="
echo "Test parameters:"
echo "- Protocol: TCP"
echo "- Duration: 5 seconds"
echo "- Port: 52001"
echo

# Run TCP test
echo "Running TCP test..."
iperf3 -c 3.3.3.4 -p 52001 -t 5 -J > iperf3_tcp_result.json
echo "TCP test completed, result saved to iperf3_tcp_result.json"
echo

# Run UDP test with 1G bandwidth limit
echo "Running UDP test..."
iperf3 -c 3.3.3.4 -p 52001 -t 5 -u -b 1G -J > iperf3_udp_result.json
echo "UDP test completed, result saved to iperf3_udp_result.json"
echo

# Print summary
echo "=== Test Summary ==="
echo "TCP test results:"
cat iperf3_tcp_result.json | grep -E '(sender|receiver).*bits_per_second'
echo
echo "UDP test results:"
cat iperf3_udp_result.json | grep -E '(sender|receiver).*bits_per_second'
echo
echo "Tests completed successfully!"
