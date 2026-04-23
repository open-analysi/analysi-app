# General Splunk Concepts

Basic Splunk concepts and architecture. **Load this reference only when working with smaller models (e.g., Haiku) that may need foundational context.**

---

## Core Concepts

### Events
A single data entry with an associated timestamp. Events can span multiple lines (e.g., stack traces, multi-line logs). Configure line breaking in `props.conf` using `LINE_BREAKER` and `SHOULD_LINEMERGE` settings.

### Multi-Valued Fields
Fields containing multiple values in a single event. Handle with specialized functions:
- `mvexpand`: Expand into separate events
- `makemv`: Convert delimited strings into multi-valued fields
- `mvcount()`, `mvindex()`, `mvfilter()`, `mvjoin()`: Manipulate values

### Host, Source, and Source Type
- **Host**: The physical or virtual device where an event originates
- **Source**: The file, directory, or data stream from which an event comes
- **Source Type**: Classification of sources into well-known or custom formats

### Fields
Fields are searchable name-value pairs that distinguish events. They're extracted during index-time and search-time processing.

### Tags
Tags enable searching for events with particular field values, grouping related data or assigning descriptive names to abstract values.

### Index-Time and Search-Time
- **Index-time**: Data is parsed into events, timestamps extracted, and data stored in indexes
- **Search-time**: Indexed events are retrieved and fields are extracted from raw text

### Indexes
Data is parsed into events, timestamps extracted, and stored in an index for later retrieval during searches.

---

## Core Features

### Reports
Saved searches that can run ad hoc, on schedules, or trigger alerts. Key capabilities:
- **Scheduling**: Run at specific intervals using cron notation
- **Acceleration**: Enable report acceleration for faster results on large datasets
- **Permissions**: Share with specific roles or make public
- **Export**: Output to CSV, PDF, or email

### Dashboards
Collections of panels with visualizations powered by saved searches or inline SPL:
- **Simple XML**: Legacy dashboard format, still widely used
- **Dashboard Studio**: Modern drag-and-drop builder with JSON-based definitions
- **Post-processing**: Use base searches with post-process searches to reduce load—run one expensive search, then filter/transform results in multiple panels
- **Tokens**: Pass values between panels for interactive filtering
- **Drilldowns**: Link panels to detailed views or other dashboards

### Alerts
Triggered when search results meet conditions. Configure:
- **Trigger conditions**: Per-result, number of results, custom condition
- **Throttling**: Suppress repeated alerts within time window
- **Actions**: Email, webhook, script execution, log event, or custom alert actions
- **Priority**: Set severity levels for alert management

---

## Additional Features

### Datasets
Curated collections including lookups, data models, and table datasets designed for specific business purposes.

### Data Models
Hierarchically-organized collections of datasets that can be referenced in searches and accelerated for improved performance.

### Apps
Collections of configurations, knowledge objects, views, and dashboards extending Splunk for specific organizational needs.

### Distributed Search
Separates search management from indexing and retrieval layers to enable horizontal scaling and improved performance.

---

## System Components

### Forwarders
Splunk instances that forward data to other Splunk instances.

### Indexer
The Splunk instance that indexes data, transforms raw data into events, and searches indexed data.

### Search Head
In distributed environments, directs search requests to search peers and merges results back to users.

---

## Getting Started

### Explore Products
- Splunk Enterprise (on-premises)
- Splunk Cloud (SaaS)
- Security solutions
- Observability solutions

### Free Resources
- [Download Splunk Enterprise](https://www.splunk.com/en_us/download/splunk-enterprise.html)
- [Splunk Community](https://community.splunk.com/)
- [Splunk Documentation](https://help.splunk.com/en)
- [Training & Certification](https://www.splunk.com/en_us/training.html)
