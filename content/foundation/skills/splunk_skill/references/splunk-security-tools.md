This comprehensive markdown document captures information relating to the Splunk InfoSec App, Splunk Security Essentials (SSE), Splunk Technical Add-ons (TAs), Data Models, and configuration settings for saved searches.

---

# Comprehensive Overview of Splunk Security Tools and Data Management

## I. InfoSec App for Splunk


### Purpose and Audience
The app serves as an initial starting point for organizations new to using Splunk for security, helping those who find the complexity and sheer number of security tools overwhelming. It aims to address common operational gaps by tying many security pieces together.

The InfoSec app is intended to be a **stepping stone toward Splunk Enterprise Security (ES)**. It is described as being in the **"walking stage"** of the crawl, walk, run, (soar/Phantom) security maturity model.

### Core Architecture and Requirements
*   **Core Functionality:** The app uses only core Splunk functionality.
*   **Simplicity:** It is designed for simplicity, currently containing **no JavaScript or lookups**. Users require only a basic understanding of Splunk, and **no SPL knowledge is required** for initial use.
*   **Data Compliance:** The app relies on data being **Common Information Model (CIM) compliant**. If data is not onboarded using CIM-compliant add-ons, the app typically will not work (this accounts for approximately 90% of issues).
*   **Data Shape:** Data used in the InfoSec app is in the same shape and form as data used for Enterprise Security.
*   **Accelerated Data Models:** Accelerated data models are used heavily to ensure fast search results (using `tstats`) when dealing with large volumes of data (millions or billions of events per day).

### Key Data Sources Focused
The app focuses on a handful of security data sources to achieve high value quickly, avoiding the need to "boil the ocean":
*   **Domain Controllers (AD/Active Directory)**.
*   **Perimeter/Next-Generation Firewalls (NGFWs)** (e.g., Palo Alto, Cisco, Fortinet, Checkpoint).
*   **Antivirus (AV)** (e.g., Symantec, McAfee, Trend Micro).
*   **Endpoint data (optional)** (e.g., commercial products like Carbon Black or systems like Microsoft Sysmon).

These sources easily map to Splunk Data Models, including: Authentication, Intrusion Detection, Malware, Change Analysis, Network Traffic, Network Session, and Endpoint data models.

### Prescriptive Menu Structure
The app's menu is structured to guide security workflow:

| Menu Section | Focus |
| :--- | :--- |
| **Security Posture** | A single-page dashboard showing high-severity intrusion alerts, infections, and basic host/account statistics. |
| **Continuous Monitoring** | Looks at security domains like network, authentication, intrusion detection, Windows environments (including locked accounts and privilege escalations). |
| **Advanced Threat Detection** | Presents sophisticated use cases, such as spikes in host access or geographically improbable login access. |
| **Investigation** | Provides capabilities to investigate what a user has done across systems, showing account changes, communications, and recent raw events. |
| **Compliance** | Example dashboards mapped to common regulations (NIST, PCI, HIPAA, NERC, ISO, Critical Security Controls). |
| **Executive Dashboard** | Provides straightforward metrics (attacks stopped, trendlines, users protected, device protected) useful for justifying security spending to executives. |
| **Health and Stats** | Monitors data sources and confirms they are successfully feeding the data models. |

### Implementation Steps
Installation of the app takes about five minutes, though data onboarding takes longer.
1.  Install the InfoSec app.
2.  Install the **Common Information Model (CIM) Add-on**.
3.  Install two visualization add-ons (free from Splunkbase).
4.  Ensure data is being brought in as CIM-compliant using relevant add-ons.
5.  Manually accelerate six data models.

## II. Splunk Security Essentials (SSE)

Splunk Security Essentials (SSE) is described as the **most used app** across all Splunk environments. It is a free app designed to act as a bridge between core Splunk and Splunk Enterprise Security (ES).

### Key Components and Content
*   **Content Library:** SSE comes pre-built with extensive content. It offers **over 900 analytic stories** and close to 1,800 total bits of security content.
*   **Analytic Stories:** These are collections of searches built around the same use case.
*   **Learning and Documentation:** SSE is highly beneficial for learning Splunk fundamentals and security. Most use cases include line-by-line documentation explaining the SPL query, providing context on implementation and remediation.
*   **Security Data Journey:** A framework within SSE showing security maturity progression.
    *   **Stage 1 (Collection):** Where basic Splunk Enterprise users often start.
    *   **Subsequent Stages:** Progress involves normalizing data, enriching data, and eventually moving toward automation and orchestration (SOAR).

### The Four Pillars of SSE Value
1.  **Finding Content:** Identify and filter content relevant to the user's environment.
2.  **Learning Splunk Security:** Education on use cases and provided SPL documentation.
3.  **Improving Production:** Detection coverage analysis to strengthen security strategy.
4.  **Measuring Success:** Reporting and auditing tools for the security journey.

### MITRE ATT\&CK Framework and Compliance
*   **Mapping:** SSE is heavily integrated with the **MITRE ATT\&CK framework**. The framework is used to prioritize content implementation based on threats relevant to a specific sector (e.g., financial or transport).
*   **Coverage Analysis:** The MITRE ATT\&CK dashboard (in Analytics Advisor) helps identify gaps in data coverage or activated use cases.
*   **Data Inventory and Compliance:** When first integrating SSE, users must run an **automated introspection scan** to map ingested data (sources, indexes, source types) to the data models.
*   **Custom Data Integration:** Non-standard or custom logs must be **CIM compliant (normalized)** to integrate smoothly with SSE. Manual integration of non-compliant data sources is possible but normalization is the simplest method.

### Advanced Features and Reporting
*   **Content Integration:** Security searches can be enabled easily, cloned into custom content, and tracked using bookmarks.
*   **Custom Content:** Users can create custom security content within SSE, defining the SPL, fields, categories, and tags.
*   **Reporting:** SSE offers various reports, including data source coverage reports (to justify new data sources), proof of concept status reports, and reports that can be exported (Excel or PDF) for auditors.
*   **Custom Commands:** SSE provides specific commands: `ssseanalytics` (tabular output of SSE content), `ssidentityenrichment` (lookup for IDs), and `mitremap` (generates an ATT\&CK map from events).

## III. Splunk Technical Add-on (TA) for Windows

The Splunk Add-on for Microsoft Windows is a widely downloaded Technical Add-on (TA) found on Splunkbase. It handles data collection for Windows servers and clients.

### Windows Data Collection
The Windows TA collects up to 12 items of data:
*   **Event Logs:** Application log, Security log, etc..
*   **Performance Data:** Performance counters retrieved from `$ perfmon.exe$`.
*   **Registry Information:** Including change tracking.
*   **WMI (Windows Management Instrumentation)**.
*   **Scripts:** Such as PowerShell executions.
*   **Text Logs**.

Use cases for this data include troubleshooting, infrastructure monitoring, capacity planning, and tracking application deployments.

### Deployment and Configuration
*   **Data Ingestion:** A **Splunk Forwarder** must be installed directly on the Windows system. Remote WMI collection is possible but is often tough and resource-consuming.
*   **Duplicate Data Warning:** When installing the Forwarder using the UI, avoid selecting event logs or performance metrics. If selected, adding the Windows TA configuration later will result in duplicate data.
*   **Configuration Files:** Data retrieval is controlled by the TA configuration.
    *   **Inputs.conf:** Contains the stanzas (configuration blocks in brackets) that define which data items are retrieved (e.g., `application log`, `WinRegMon`, `WinPerfMon`).
    *   **Enabling Stanzas:** Settings within `inputs.conf` are enabled by setting `disabled = 0`.
    *   **Editing Practice:** Changes to configuration files must be made by copying the file from the `default` directory to the `local` directory.
*   **Knowledge Objects:** The TA must be deployed on search heads because it provides necessary **Knowledge Objects** (such as field extractions and field aliases) for searching Windows data effectively.

## IV. Splunk Data Models and CIM

Data models (DMs) are a crucial platform component for normalizing data across multiple, disparate sources.

### Common Information Model (CIM)
The CIM is a standardized set of guidelines provided by Splunk that defines common field names and data types (e.g., standardizing IP addresses as `dest_ip` or `source_ip`). Organizations should strive to ensure their data is **CIM compliant**.

### Data Model Constraints and Implementation
Implementing a data model involves three key steps:

1.  **Restricting Indexes (Constraints):** DMs should only search relevant indexes to maintain efficiency and improve performance, especially when acceleration is enabled. This is typically managed by configuring the **SIM macro** (e.g., `SIM_network_traffic_indexes`) to whitelist specific indexes.
2.  **Tagging Data (Event Types):**
    *   **Event Types** define a search condition and apply a comma-separated list of **Tags** (e.g., `network, communicate`) to the resulting data.
    *   Event Types simplify queries (e.g., searching for `eventtype=suspicious`) and enhance search redundancy, as dashboards can reference the event type instead of hard-coded indexes.
    *   Event Types can apply visual cues (colors) and utilize a priority system (highest priority wins).
3.  **Field Aliasing:** The fields within the incoming data must match the expected fields of the data model.
    *   It is generally recommended to **change the incoming data** (e.g., via a tool like Cribl or natively in Splunk using Field Aliases) rather than editing the DM definition itself, in order to preserve reusability.
    *   Field Aliases are created using the original field name on the left and the new CIM-compliant field name on the right. These changes are performed at search time on the search head.

### DM Benefits
*   **Normalization:** Allows searching similar data types (like authentication logs from SSH, Windows Events, SQL servers) using consistent field names.
*   **Pivoting:** Provides a graphical user interface (GUI) to build tables and charts without requiring SPL knowledge.
*   **Dashboard Integration:** Dashboards built using DMs automatically incorporate data from any newly added source that is CIM compliant and correctly tagged.
*   **Introspection:** Allows users to quickly see which required fields are available or blank within their data set.

## V. Creating Test Data for Splunk Environments

For users needing reproducible data sets, especially for following video tutorials, two main methods are provided.

### Recommended Method: BOTS V3 Data Set
The **Bots V3 data set** (Bots the Sock version 3) is the recommended way, as it ensures the test data exactly matches the tutorial environment.
*   **Installation:** Download the data set from GitHub, copy the file to the Splunk instance (e.g., via SCP), untar it into the `$SPLUNK\_HOME/etc/apps/` directory, set ownership to the Splunk user (`chown`), and restart Splunk.
*   **Add-ons:** Technical Add-ons (TAs) are still required to correctly parse the data.

### Alternative Method: Eventgen
Eventgen is an alternative, though it tends to be more difficult to run, and the data it replays is random, so results will be similar but not exact. It seems to be less actively supported than it used to be.

## VI. `savedsearches.conf` Configuration File

The `savedsearches.conf` file is used to define and configure saved searches and alerts within Splunk Enterprise.

### Configuration Details
*   **Location:** Custom settings reside in `$SPLUNK\_HOME/etc/system/local/savedsearches.conf`.
*   **Structure:** Configuration uses stanzas (`[<stanza name>]`). Global settings can be defined in `[default]`.
*   **Enabling/Disabling:** A search is disabled using `disabled = true`. Scheduled searches are enabled using `enableSched = 1`.
*   **Search Definition:** The actual SPL string is defined using the `search = <string>` parameter.

### Scheduling and Priority Options
| Setting | Description |
| :--- | :--- |
| `cron_schedule` | Defines the search interval using cron notation (e.g., `*/5 * * * *` for every 5 minutes). |
| `allow_skew` | Randomly distributes search start times to reduce system load. |
| `max_concurrent` | Maximum number of concurrent instances allowed (Default: 1). |
| `realtime_schedule` | Controls if the next run time is computed based on current time (`true`) or last run time (`false`/continuous scheduling). |
| `schedule_priority` | Sets the priority level (`default`, `higher`, `highest`) for mission-critical searches. |
| `schedule_window` | Specifies a time window (in minutes) during which the search can start, providing scheduler flexibility. |
| `dispatchAs` | Controls whether the search runs as the user requesting dispatch or the search owner (Default: `owner`). |

### Notification and Action Settings
Alerting conditions are defined using combinations of parameters:
*   **Condition:** `<counttype>` (e.g., number of events) `<relation>` (e.g., greater than) `<quantity>` (e.g., 10).
*   **Actions:** Actions such as `email`, `populate_lookup`, `script`, and `summary_index` are enabled using `action.<action_name> = <boolean>`.

Specific settings exist for:
*   **Email Action:** Requires `action.email.to` (comma-delimited list).
*   **Script Action:** Specifies `action.script.filename` (must be in `$SPLUNK\_HOME/bin/scripts/`).
*   **Summary Index Action:** Specifies `action.summary_index._name` (Default: `summary`) and `action.summary_index._type` (event or metric).

### Durable Searches
Durable searches ensure that all results are delivered, even if the search process is slowed or stopped by network bottlenecks or restarts.
*   **Tracking:** Specified by `durable.track_time_type = [ _time | _indextime | none ]`.
*   **Backfill:** If a durable search fails, Splunk reschedules a backfill search job. This cannot be applied to real-time or ad hoc searches.

### Display and UI Settings
The configuration includes extensive parameters for controlling search job execution and how results are displayed in the Splunk Web UI:
*   **Dispatch Options:** Parameters like `dispatch.ttl` (time-to-live for artifacts, e.g., `2p` for 2 times the execution period) and `dispatch.earliest_time`/`latest_time` control job lifespan and time range.
*   **UI Views:** Settings like `displayview` define the default UI view name for loading results.
*   **Display Formatting:** Numerous parameters under `display.events`, `display.statistics`, and `display.visualizations` control row numbers, chart types (`line`, `area`, `column`), axis scales (`linear`, `log`), and table format options.
