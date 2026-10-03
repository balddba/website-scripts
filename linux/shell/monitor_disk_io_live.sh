#!/bin/bash

# Check for iostat
if ! command -v iostat &> /dev/null; then
  echo "Please install sysstat package (iostat)"
  exit 1
fi

# Threshold in MB/s
THRESHOLD=1

# Function to clear the screen and print header
print_header() {
  clear
  echo "Time                Device        MB_Read/s   MB_Written/s"
}

print_header

while true; do
  timestamp=$(date '+%Y-%m-%d %H:%M:%S')

  # Capture devices with activity > threshold
  mapfile -t lines < <(iostat -d -m 1 2 | awk -v th="$THRESHOLD" '
    /^Device:/ {header=1; next}
    header && NF == 6 {
      if ($3 > th || $4 > th) printf "%-19s %-12s %10.2f   %12.2f\n", "'"$timestamp"'", $1, $3, $4
    }
  ')

  # Number of lines to rewrite (header + data lines)
  num_lines=$(( ${#lines[@]} + 1 ))

  # Move cursor up to overwrite previous output (if not the first iteration)
  if [ $prev_lines ]; then
    tput cuu $prev_lines
  fi

  # Print header
  echo "Time                Device        MB_Read/s   MB_Written/s"

  # Print the data lines or a no-activity message
  if [ ${#lines[@]} -eq 0 ]; then
    echo "No devices with >${THRESHOLD} MB/s activity"
  else
    for line in "${lines[@]}"; do
      echo "$line"
    done
  fi

  prev_lines=$num_lines

  sleep 1
done
