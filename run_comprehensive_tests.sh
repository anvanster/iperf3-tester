#!/bin/bash
# Comprehensive iperf3 test script to remote server

REMOTE_SERVER="3.3.3.4"
PORT=52001
TEST_DURATION=5
OUTPUT_DIR="iperf3_results_$(date +%Y%m%d_%H%M%S)"

echo "=== iperf3 Comprehensive Test Suite ==="
echo "Remote server: $REMOTE_SERVER"
echo "Port: $PORT"
echo "Test duration: $TEST_DURATION seconds"
echo

# Create results directory
mkdir -p $OUTPUT_DIR
echo "Results will be saved to: $OUTPUT_DIR/"
echo

# Function to run a test and save results
run_test() {
    local test_name=$1
    local test_cmd=$2
    local output_file="$OUTPUT_DIR/${test_name}.json"
    local log_file="$OUTPUT_DIR/${test_name}.log"
    
    echo "------------------------------------------"
    echo "Running test: $test_name"
    echo "Command: $test_cmd"
    echo
    
    # Run the test and capture both JSON output and log
    eval "$test_cmd -J > $output_file" 2>&1 | tee $log_file
    
    # Extract key metrics
    echo
    echo "Key metrics:"
    if [[ $test_name == *"udp"* ]]; then
        # For UDP tests
        bandwidth=$(grep -oE '"bits_per_second":\s*[0-9.e+]*' $output_file | head -2 | tail -1 | grep -oE '[0-9.e+]*')
        jitter=$(grep -oE '"jitter_ms":\s*[0-9.e+]*' $output_file | tail -1 | grep -oE '[0-9.e+]*')
        loss=$(grep -oE '"lost_percent":\s*[0-9.e+]*' $output_file | tail -1 | grep -oE '[0-9.e+]*')
        
        echo "Bandwidth: $(echo "$bandwidth / 1000000000" | bc -l | xargs printf "%.2f") Gbps"
        echo "Jitter: $jitter ms"
        echo "Packet loss: $loss%"
    else
        # For TCP tests
        sender=$(grep -oE '"bits_per_second":\s*[0-9.e+]*' $output_file | head -1 | grep -oE '[0-9.e+]*')
        receiver=$(grep -oE '"bits_per_second":\s*[0-9.e+]*' $output_file | tail -1 | grep -oE '[0-9.e+]*')
        retrans=$(grep -oE '"retransmits":\s*[0-9]*' $output_file | grep -oE '[0-9]*')
        
        echo "Sender bandwidth: $(echo "$sender / 1000000000" | bc -l | xargs printf "%.2f") Gbps"
        echo "Receiver bandwidth: $(echo "$receiver / 1000000000" | bc -l | xargs printf "%.2f") Gbps" 
        echo "Retransmits: $retrans"
    fi
    
    echo "------------------------------------------"
    echo
}

# Test 1: Basic TCP test
run_test "tcp_basic" "iperf3 -c $REMOTE_SERVER -p $PORT -t $TEST_DURATION"

# Test 2: TCP with multiple parallel streams
run_test "tcp_parallel_4" "iperf3 -c $REMOTE_SERVER -p $PORT -t $TEST_DURATION -P 4"

# Test 3: TCP bidirectional test
run_test "tcp_bidirectional" "iperf3 -c $REMOTE_SERVER -p $PORT -t $TEST_DURATION --bidir"

# Test 4: UDP test at 1Gbps
run_test "udp_1g" "iperf3 -c $REMOTE_SERVER -p $PORT -t $TEST_DURATION -u -b 1G"

# Test 5: UDP test at 10Gbps
run_test "udp_10g" "iperf3 -c $REMOTE_SERVER -p $PORT -t $TEST_DURATION -u -b 10G"

# Test 6: TCP with 128K buffer size
run_test "tcp_128k_buffer" "iperf3 -c $REMOTE_SERVER -p $PORT -t $TEST_DURATION -l 128K"

# Test 7: TCP with window size 1MB
run_test "tcp_window_1m" "iperf3 -c $REMOTE_SERVER -p $PORT -t $TEST_DURATION -w 1M"

# Generate summary report
echo "=== Test Summary Report ===" > $OUTPUT_DIR/summary.txt
echo "Date: $(date)" >> $OUTPUT_DIR/summary.txt
echo "Remote server: $REMOTE_SERVER" >> $OUTPUT_DIR/summary.txt
echo "Port: $PORT" >> $OUTPUT_DIR/summary.txt
echo "Test duration: $TEST_DURATION seconds" >> $OUTPUT_DIR/summary.txt
echo >> $OUTPUT_DIR/summary.txt
echo "Test Results:" >> $OUTPUT_DIR/summary.txt

# Process each test result
for test in tcp_basic tcp_parallel_4 tcp_bidirectional udp_1g udp_10g tcp_128k_buffer tcp_window_1m; do
    json_file="$OUTPUT_DIR/${test}.json"
    if [ -f "$json_file" ]; then
        echo "  $test:" >> $OUTPUT_DIR/summary.txt
        if [[ $test == *"udp"* ]]; then
            # UDP metrics
            bandwidth=$(grep -oE '"bits_per_second":\s*[0-9.e+]*' $json_file | head -2 | tail -1 | grep -oE '[0-9.e+]*')
            jitter=$(grep -oE '"jitter_ms":\s*[0-9.e+]*' $json_file | tail -1 | grep -oE '[0-9.e+]*')
            loss=$(grep -oE '"lost_percent":\s*[0-9.e+]*' $json_file | tail -1 | grep -oE '[0-9.e+]*')
            
            if [ ! -z "$bandwidth" ]; then
                bandwidth=$(echo "$bandwidth / 1000000000" | bc -l | xargs printf "%.2f")
            fi
            
            echo "    Bandwidth: ${bandwidth} Gbps" >> $OUTPUT_DIR/summary.txt
            echo "    Jitter: ${jitter} ms" >> $OUTPUT_DIR/summary.txt 
            echo "    Packet loss: ${loss}%" >> $OUTPUT_DIR/summary.txt
        else
            # TCP metrics
            sender=$(grep -oE '"bits_per_second":\s*[0-9.e+]*' $json_file | head -1 | grep -oE '[0-9.e+]*')
            receiver=$(grep -oE '"bits_per_second":\s*[0-9.e+]*' $json_file | tail -1 | grep -oE '[0-9.e+]*')
            retrans=$(grep -oE '"retransmits":\s*[0-9]*' $json_file | grep -oE '[0-9]*')
            
            if [ ! -z "$sender" ]; then
                sender=$(echo "$sender / 1000000000" | bc -l | xargs printf "%.2f")
            fi
            if [ ! -z "$receiver" ]; then
                receiver=$(echo "$receiver / 1000000000" | bc -l | xargs printf "%.2f")
            fi
            echo "    Sender: ${sender} Gbps" >> $OUTPUT_DIR/summary.txt
            echo "    Receiver: ${receiver} Gbps" >> $OUTPUT_DIR/summary.txt
            echo "    Retransmits: ${retrans}" >> $OUTPUT_DIR/summary.txt
        fi
    else
        echo "  $test: Test results not available" >> $OUTPUT_DIR/summary.txt
    fi
    echo >> $OUTPUT_DIR/summary.txt
done

echo
echo "All tests completed!"
echo "Summary report generated at: $OUTPUT_DIR/summary.txt"
echo
cat $OUTPUT_DIR/summary.txt
