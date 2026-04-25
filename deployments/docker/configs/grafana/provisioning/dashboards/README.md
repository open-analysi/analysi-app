# Grafana Dashboards

This directory contains pre-configured Grafana dashboards that are automatically provisioned when Grafana starts.

## Available Dashboards

### 1. PostgreSQL Overview (`postgres-overview.json`)
- **Purpose**: Monitor PostgreSQL database performance
- **Metrics Source**: postgres-exporter
- **Key Panels**:
  - Database connections
  - Query performance
  - Table sizes
  - Transaction rates

### 2. Node Exporter - MacBook System Metrics (`node-exporter.json`)
- **Purpose**: Custom dashboard for macOS system monitoring
- **Metrics Source**: node-exporter on host machine
- **Key Panels**:
  - CPU, Memory, and Disk usage gauges
  - Time series for system performance
  - Network and Disk I/O graphs

### 3. Node Exporter - MacOS System Metrics (`node-exporter-macos.json`)
- **Purpose**: macOS-optimized dashboard (imported from Grafana Labs template #15797)
- **Metrics Source**: node-exporter on host machine
- **Key Panels**:
  - CPU usage per core
  - Load average
  - Memory usage (macOS-specific metrics)
  - Disk I/O and space
  - Network traffic

## How to Access Dashboards

1. Open Grafana: http://localhost:3000
2. Login (default: admin/admin)
3. Navigate to Dashboards → Browse
4. Select any of the available dashboards

## Adding New Dashboards

To add a new dashboard:

1. Create or export a dashboard JSON file
2. Place it in this directory
3. Ensure the datasource is set to "Prometheus"
4. Restart Grafana: `docker-compose -f docker-compose.monitoring.yml restart analysi-grafana`

## Importing from Grafana Labs

You can import community dashboards from https://grafana.com/grafana/dashboards/

Popular dashboard IDs:
- **1860**: Node Exporter Full (Linux)
- **15797**: Node Exporter Mac OSX
- **14866**: Mac Prometheus Exporter
- **7362**: PostgreSQL Database

To import:
1. Copy the dashboard ID
2. In Grafana, go to Dashboards → Import
3. Enter the ID and click Load
4. Select "Prometheus" as the data source
5. Click Import

## Dashboard Configuration

All dashboards are configured to:
- Use the local Prometheus datasource
- Auto-refresh every 10 seconds
- Display data from the last hour by default

## Troubleshooting

If dashboards show "No Data":
1. Verify exporters are running:
   - PostgreSQL Exporter: http://localhost:9188/metrics
   - Node Exporter: http://localhost:9100/metrics
2. Check Prometheus targets: http://localhost:9090/targets
3. Restart the monitoring stack: `make restart-monitoring`
