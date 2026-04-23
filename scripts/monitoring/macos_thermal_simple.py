#!/usr/bin/env python3
"""
Simple macOS Thermal Metrics Exporter using ioreg

Exports battery temperature and power metrics that are available without sudo.
"""

import re
import subprocess
from http.server import BaseHTTPRequestHandler, HTTPServer


class ThermalMetricsCollector:
    """Collects thermal metrics from macOS using ioreg"""

    def collect(self):
        """Collect metrics from ioreg"""
        metrics = {}

        try:
            # Get battery info including temperature
            result = subprocess.run(
                ['ioreg', '-r', '-c', 'AppleSmartBattery'],
                capture_output=True, text=True, timeout=2
            )

            if result.returncode == 0:
                output = result.stdout

                # Battery temperature (in 0.1 Kelvin - typical for Apple batteries)
                if '"Temperature" = ' in output:
                    match = re.search(r'"Temperature" = (\d+)', output)
                    if match:
                        # Apple uses 0.1 Kelvin units
                        kelvin = int(match.group(1)) / 10.0
                        celsius = kelvin - 273.15
                        metrics['node_thermal_battery_temperature_celsius'] = round(celsius, 2)

                # Current (in mA)
                if '"InstantAmperage" = ' in output:
                    match = re.search(r'"InstantAmperage" = (-?\d+)', output)
                    if match:
                        amperage = int(match.group(1))
                        metrics['node_thermal_battery_current_amperes'] = round(amperage / 1000.0, 3)

                # Voltage (in mV)
                if '"Voltage" = ' in output:
                    match = re.search(r'"Voltage" = (\d+)', output)
                    if match:
                        voltage = int(match.group(1))
                        metrics['node_thermal_battery_voltage'] = round(voltage / 1000.0, 3)

                # System power from PowerTelemetryData (when available)
                if '"PowerTelemetryData" = ' in output:
                    # Extract SystemLoad (in milliwatts) from the dictionary
                    match = re.search(r'"PowerTelemetryData" = \{[^}]*"SystemLoad"=(\d+)', output)
                    if match:
                        system_load_mw = int(match.group(1))
                        system_power_watts = system_load_mw / 1000.0
                        metrics['node_thermal_power_consumption_watts'] = round(system_power_watts, 2)

                # Calculate power from battery if not on AC or if SystemLoad not available
                if 'node_thermal_power_consumption_watts' not in metrics:
                    if 'node_thermal_battery_current_amperes' in metrics and 'node_thermal_battery_voltage' in metrics:
                        power = abs(metrics['node_thermal_battery_current_amperes'] *
                                   metrics['node_thermal_battery_voltage'])
                        if power > 0:  # Only set if there's actual power draw
                            metrics['node_thermal_power_consumption_watts'] = round(power, 2)

                # Cycle count
                if '"CycleCount" = ' in output:
                    match = re.search(r'"CycleCount" = (\d+)', output)
                    if match:
                        metrics['node_thermal_battery_cycle_count'] = int(match.group(1))

                # Max capacity percentage
                if '"MaxCapacity" = ' in output:
                    match = re.search(r'"MaxCapacity" = (\d+)', output)
                    if match:
                        metrics['node_thermal_battery_health_percent'] = int(match.group(1))

            # Try to get additional thermal data from IOPMPowerSource
            result = subprocess.run(
                ['ioreg', '-r', '-c', 'IOPMPowerSource'],
                capture_output=True, text=True, timeout=2
            )

            if result.returncode == 0:
                output = result.stdout

                # Virtual Temperature (system thermal indicator)
                if '"VirtualTemperature" = ' in output:
                    match = re.search(r'"VirtualTemperature" = (\d+)', output)
                    if match:
                        # VirtualTemperature appears to be in hundredths of degrees Celsius
                        celsius = int(match.group(1)) / 100.0
                        metrics['node_thermal_virtual_temperature_celsius'] = round(celsius, 2)

        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            pass

        # Try to get thermal pressure info
        try:
            result = subprocess.run(
                ['sysctl', 'kern.thermal.primary_zone_cpu'],
                capture_output=True, text=True, timeout=1
            )
            if result.returncode == 0 and ':' in result.stdout:
                value = result.stdout.split(':')[1].strip()
                if value.isdigit():
                    metrics['node_thermal_pressure_state'] = int(value)
        except:
            pass

        # Get open file descriptors count
        try:
            # Get system-wide open files using lsof
            result = subprocess.run(
                ['lsof', '-n'],  # -n for no DNS lookups (faster)
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                # Count lines (each line is an open file)
                open_files = len(result.stdout.strip().split('\n')) - 1  # Subtract header
                metrics['node_system_open_files'] = open_files

            # Also get the system limit using launchctl on macOS
            result = subprocess.run(
                ['launchctl', 'limit', 'maxfiles'],
                capture_output=True, text=True, timeout=1
            )
            if result.returncode == 0:
                # Output format: "maxfiles    256            unlimited"
                parts = result.stdout.strip().split()
                if len(parts) >= 2 and parts[1].isdigit():
                    metrics['node_system_file_descriptor_limit'] = int(parts[1])
        except:
            pass

        # Get open sockets count
        try:
            # Count LISTEN and ESTABLISHED sockets
            result = subprocess.run(
                ['netstat', '-an'],
                capture_output=True, text=True, timeout=3
            )
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')

                # Count different socket states
                listen_count = 0
                established_count = 0
                close_wait_count = 0
                time_wait_count = 0
                total_sockets = 0

                for line in lines:
                    if 'LISTEN' in line:
                        listen_count += 1
                        total_sockets += 1
                    elif 'ESTABLISHED' in line:
                        established_count += 1
                        total_sockets += 1
                    elif 'CLOSE_WAIT' in line:
                        close_wait_count += 1
                        total_sockets += 1
                    elif 'TIME_WAIT' in line:
                        time_wait_count += 1
                        total_sockets += 1

                metrics['node_system_sockets_total'] = total_sockets
                metrics['node_system_sockets_listen'] = listen_count
                metrics['node_system_sockets_established'] = established_count
                metrics['node_system_sockets_close_wait'] = close_wait_count
                metrics['node_system_sockets_time_wait'] = time_wait_count
        except:
            pass

        return metrics


class MetricsHandler(BaseHTTPRequestHandler):
    """HTTP handler for metrics endpoint"""

    collector = ThermalMetricsCollector()

    def do_GET(self):
        if self.path == '/metrics':
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; version=0.0.4')
            self.end_headers()

            metrics = self.collector.collect()
            output = []

            # Add Prometheus format metrics
            if metrics:
                output.append('# HELP node_thermal_battery_temperature_celsius Battery temperature in Celsius')
                output.append('# TYPE node_thermal_battery_temperature_celsius gauge')
                if 'node_thermal_battery_temperature_celsius' in metrics:
                    output.append(f'node_thermal_battery_temperature_celsius {metrics["node_thermal_battery_temperature_celsius"]}')

                output.append('# HELP node_thermal_battery_current_amperes Battery current in amperes')
                output.append('# TYPE node_thermal_battery_current_amperes gauge')
                if 'node_thermal_battery_current_amperes' in metrics:
                    output.append(f'node_thermal_battery_current_amperes {metrics["node_thermal_battery_current_amperes"]}')

                output.append('# HELP node_thermal_power_consumption_watts Power consumption in watts')
                output.append('# TYPE node_thermal_power_consumption_watts gauge')
                if 'node_thermal_power_consumption_watts' in metrics:
                    output.append(f'node_thermal_power_consumption_watts {metrics["node_thermal_power_consumption_watts"]}')

                output.append('# HELP node_thermal_battery_health_percent Battery health percentage')
                output.append('# TYPE node_thermal_battery_health_percent gauge')
                if 'node_thermal_battery_health_percent' in metrics:
                    output.append(f'node_thermal_battery_health_percent {metrics["node_thermal_battery_health_percent"]}')

                output.append('# HELP node_thermal_battery_cycle_count Battery charge cycles')
                output.append('# TYPE node_thermal_battery_cycle_count counter')
                if 'node_thermal_battery_cycle_count' in metrics:
                    output.append(f'node_thermal_battery_cycle_count {metrics["node_thermal_battery_cycle_count"]}')

                output.append('# HELP node_thermal_battery_voltage Battery voltage in volts')
                output.append('# TYPE node_thermal_battery_voltage gauge')
                if 'node_thermal_battery_voltage' in metrics:
                    output.append(f'node_thermal_battery_voltage {metrics["node_thermal_battery_voltage"]}')

                output.append('# HELP node_thermal_virtual_temperature_celsius Virtual/System temperature in Celsius')
                output.append('# TYPE node_thermal_virtual_temperature_celsius gauge')
                if 'node_thermal_virtual_temperature_celsius' in metrics:
                    output.append(f'node_thermal_virtual_temperature_celsius {metrics["node_thermal_virtual_temperature_celsius"]}')

                output.append('# HELP node_thermal_pressure_state System thermal pressure state')
                output.append('# TYPE node_thermal_pressure_state gauge')
                if 'node_thermal_pressure_state' in metrics:
                    output.append(f'node_thermal_pressure_state {metrics["node_thermal_pressure_state"]}')

                # File descriptor metrics
                output.append('# HELP node_system_open_files Total number of open files system-wide')
                output.append('# TYPE node_system_open_files gauge')
                if 'node_system_open_files' in metrics:
                    output.append(f'node_system_open_files {metrics["node_system_open_files"]}')

                output.append('# HELP node_system_file_descriptor_limit System file descriptor limit')
                output.append('# TYPE node_system_file_descriptor_limit gauge')
                if 'node_system_file_descriptor_limit' in metrics:
                    output.append(f'node_system_file_descriptor_limit {metrics["node_system_file_descriptor_limit"]}')

                # Socket metrics
                output.append('# HELP node_system_sockets_total Total number of open sockets')
                output.append('# TYPE node_system_sockets_total gauge')
                if 'node_system_sockets_total' in metrics:
                    output.append(f'node_system_sockets_total {metrics["node_system_sockets_total"]}')

                output.append('# HELP node_system_sockets_listen Number of listening sockets')
                output.append('# TYPE node_system_sockets_listen gauge')
                if 'node_system_sockets_listen' in metrics:
                    output.append(f'node_system_sockets_listen {metrics["node_system_sockets_listen"]}')

                output.append('# HELP node_system_sockets_established Number of established connections')
                output.append('# TYPE node_system_sockets_established gauge')
                if 'node_system_sockets_established' in metrics:
                    output.append(f'node_system_sockets_established {metrics["node_system_sockets_established"]}')

                output.append('# HELP node_system_sockets_close_wait Number of sockets in CLOSE_WAIT state')
                output.append('# TYPE node_system_sockets_close_wait gauge')
                if 'node_system_sockets_close_wait' in metrics:
                    output.append(f'node_system_sockets_close_wait {metrics["node_system_sockets_close_wait"]}')

                output.append('# HELP node_system_sockets_time_wait Number of sockets in TIME_WAIT state')
                output.append('# TYPE node_system_sockets_time_wait gauge')
                if 'node_system_sockets_time_wait' in metrics:
                    output.append(f'node_system_sockets_time_wait {metrics["node_system_sockets_time_wait"]}')

            self.wfile.write('\n'.join(output).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass


def main():
    """Start the thermal metrics exporter"""
    port = 9101
    server = HTTPServer(('', port), MetricsHandler)

    print("macOS Thermal Metrics Exporter")
    print("==============================")
    print(f"Serving metrics at: http://localhost:{port}/metrics")
    print("\nAvailable metrics:")
    print("  - Battery temperature (°C)")
    print("  - Virtual/System temperature (°C)")
    print("  - Power consumption (W)")
    print("  - Battery current (A)")
    print("  - Battery voltage (V)")
    print("  - Battery health (%)")
    print("  - Thermal pressure state")
    print("  - Open file descriptors")
    print("  - Open sockets (by state)")
    print("\nPress Ctrl+C to stop")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()


if __name__ == '__main__':
    main()
