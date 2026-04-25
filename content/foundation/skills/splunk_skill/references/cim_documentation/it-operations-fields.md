# CIM IT Operations Fields

Field mappings for IT operations data models: Change, Data Access, Databases, Inventory, Performance, and Updates.

---

## Change

| Field | Description |
|-------|-------------|
| **action** | Change action |
| **change_type** | Type of change |
| **command** | Command executed |
| **dest** | Target system |
| **dest_bunit** | Destination business unit |
| **dest_category** | Destination category |
| **dest_ip_range** | Destination IP range |
| **dest_port_range** | Destination port range |
| **dest_priority** | Destination priority |
| **direction** | Change direction |
| **dvc** | Device |
| **image_id** | Image ID (cloud) |
| **instance_type** | Instance type (cloud) |
| **object** | Changed object |
| **object_attrs** | Object attributes |
| **object_category** | Object category |
| **object_id** | Object ID |
| **object_path** | Object path |
| **protocol** | Protocol |
| **result** | Change result |
| **result_id** | Result ID |
| **rule_action** | Rule action |
| **src** | Source |
| **src_bunit** | Source business unit |
| **src_category** | Source category |
| **src_ip_range** | Source IP range |
| **src_nt_domain** | Source NT domain |
| **src_port_range** | Source port range |
| **src_priority** | Source priority |
| **src_user** | Source user |
| **src_user_bunit** | Source user business unit |
| **src_user_category** | Source user category |
| **src_user_name** | Source user name |
| **src_user_priority** | Source user priority |
| **src_user_type** | Source user type |
| **status** | Status |
| **tag** | Classification tags |
| **user** | User |
| **user_agent** | User agent |
| **user_name** | User name |
| **user_type** | User type |
| **vendor_account** | Vendor account |
| **vendor_product** | Vendor product |
| **vendor_product_id** | Vendor product ID |
| **vendor_region** | Vendor region |

---

## Data Access

| Field | Description |
|-------|-------------|
| **action** | Access action |
| **app** | Application |
| **app_id** | Application ID |
| **dest** | Destination |
| **dest_name** | Destination name |
| **dest_url** | Destination URL |
| **email** | User email |
| **object** | Accessed object |
| **object_category** | Object category |
| **object_id** | Object ID |
| **object_path** | Object path |
| **object_size** | Object size |
| **owner** | Object owner |
| **owner_email** | Owner email |
| **owner_id** | Owner ID |
| **parent_object** | Parent object |
| **parent_object_category** | Parent object category |
| **parent_object_id** | Parent object ID |
| **src** | Source |
| **tag** | Classification tags |
| **user** | User |
| **user_agent** | User agent |
| **user_group** | User group |
| **user_role** | User role |
| **vendor_account** | Vendor account |
| **vendor_product** | Vendor product |

---

## Databases

| Field | Description |
|-------|-------------|
| **availability** | Database availability |
| **avg_executions** | Average executions |
| **buffer_cache_hit_ratio** | Buffer cache hit ratio |
| **commits** | Commit count |
| **cpu_used** | CPU used |
| **cursor** | Database cursor |
| **dest** | Database server |
| **dest_bunit** | Destination business unit |
| **dest_category** | Destination category |
| **dest_priority** | Destination priority |
| **dump_area_used** | Dump area used |
| **duration** | Query duration |
| **elapsed_time** | Elapsed time |
| **free_bytes** | Free bytes |
| **indexes_hit** | Indexes hit |
| **instance_name** | Instance name |
| **instance_reads** | Instance reads |
| **instance_version** | Instance version |
| **instance_writes** | Instance writes |
| **last_call_minute** | Last call minute |
| **lock_mode** | Lock mode |
| **lock_session_id** | Lock session ID |
| **logical_reads** | Logical reads |
| **logon_time** | Logon time |
| **machine** | Machine |
| **memory_sorts** | Memory sorts |
| **number_of_users** | Number of users |
| **obj_name** | Object name |
| **object** | Database object |
| **os_pid** | OS process ID |
| **physical_reads** | Physical reads |
| **process_limit** | Process limit |
| **processes** | Processes |
| **query** | Query text |
| **query_id** | Query ID |
| **query_plan_hit** | Query plan hit |
| **query_time** | Query time |
| **records_affected** | Records affected |
| **response_time** | Response time |
| **seconds_in_wait** | Seconds in wait |
| **serial_num** | Serial number |
| **session_id** | Session ID |
| **session_limit** | Session limit |
| **session_status** | Session status |
| **sessions** | Sessions |
| **sga_*** | SGA metrics (Oracle) |
| **src** | Source |
| **src_bunit** | Source business unit |
| **src_category** | Source category |
| **src_priority** | Source priority |
| **start_time** | Start time |
| **stored_procedures_called** | Stored procedures called |
| **table_scans** | Table scans |
| **tables_hit** | Tables hit |
| **tablespace_*** | Tablespace metrics |
| **tag** | Classification tags |
| **user** | Database user |
| **user_bunit** | User business unit |
| **user_category** | User category |
| **user_priority** | User priority |
| **vendor_product** | Vendor product |
| **wait_state** | Wait state |
| **wait_time** | Wait time |

---

## Inventory

| Field | Description |
|-------|-------------|
| **array** | Storage array |
| **blocksize** | Block size |
| **cluster** | Cluster |
| **cpu_cores** | CPU cores |
| **cpu_count** | CPU count |
| **cpu_mhz** | CPU speed |
| **description** | Asset description |
| **dest** | Asset |
| **dest_bunit** | Destination business unit |
| **dest_category** | Destination category |
| **dest_ip** | IP address |
| **dest_priority** | Destination priority |
| **dns** | DNS name |
| **enabled** | Enabled flag |
| **family** | Asset family |
| **fd_max** | File descriptor max |
| **hypervisor** | Hypervisor |
| **hypervisor_id** | Hypervisor ID |
| **inline_nat** | Inline NAT |
| **interactive** | Interactive flag |
| **interface** | Network interface |
| **ip** | IP address |
| **latency** | Latency |
| **lb_method** | Load balancing method |
| **mac** | MAC address |
| **mem** | Memory |
| **mount** | Mount point |
| **name** | Asset name |
| **node** | Node |
| **node_port** | Node port |
| **os** | Operating system |
| **parent** | Parent asset |
| **password** | Password (hashed) |
| **read_blocks** | Read blocks |
| **read_latency** | Read latency |
| **read_ops** | Read operations |
| **serial** | Serial number |
| **shell** | Shell |
| **size** | Size |
| **snapshot** | Snapshot |
| **src_ip** | Source IP |
| **status** | Status |
| **storage** | Storage |
| **tag** | Classification tags |
| **time** | Timestamp |
| **user** | Associated user |
| **user_bunit** | User business unit |
| **user_category** | User category |
| **user_id** | User ID |
| **user_priority** | User priority |
| **vendor_product** | Vendor product |
| **version** | Version |
| **vip_port** | VIP port |
| **write_blocks** | Write blocks |
| **write_latency** | Write latency |
| **write_ops** | Write operations |

---

## Performance

| Field | Description |
|-------|-------------|
| **array** | Storage array |
| **blocksize** | Block size |
| **cluster** | Cluster |
| **cpu_load_mhz** | CPU load in MHz |
| **cpu_load_percent** | CPU load percent |
| **cpu_time** | CPU time |
| **cpu_user_percent** | CPU user percent |
| **dest** | System |
| **dest_bunit** | Destination business unit |
| **dest_category** | Destination category |
| **dest_priority** | Destination priority |
| **dest_should_timesync** | Should time sync |
| **dest_should_update** | Should update |
| **fan_speed** | Fan speed |
| **fd_max** | File descriptor max |
| **fd_used** | File descriptors used |
| **hypervisor_id** | Hypervisor ID |
| **latency** | Latency |
| **mem** | Total memory |
| **mem_committed** | Memory committed |
| **mem_free** | Memory free |
| **mem_used** | Memory used |
| **mount** | Mount point |
| **parent** | Parent system |
| **power** | Power consumption |
| **read_blocks** | Read blocks |
| **read_latency** | Read latency |
| **read_ops** | Read operations |
| **resource_type** | Resource type |
| **signature** | Performance signature |
| **signature_id** | Signature ID |
| **storage** | Storage |
| **storage_free** | Storage free |
| **storage_free_percent** | Storage free percent |
| **storage_used** | Storage used |
| **storage_used_percent** | Storage used percent |
| **swap** | Swap total |
| **swap_free** | Swap free |
| **swap_used** | Swap used |
| **tag** | Classification tags |
| **temperature** | Temperature |
| **thruput** | Throughput |
| **thruput_max** | Throughput max |
| **uptime** | Uptime |
| **write_blocks** | Write blocks |
| **write_latency** | Write latency |
| **write_ops** | Write operations |

---

## Updates

| Field | Description |
|-------|-------------|
| **dest** | Target system |
| **dest_bunit** | Destination business unit |
| **dest_category** | Destination category |
| **dest_priority** | Destination priority |
| **dest_should_update** | Should update flag |
| **dvc** | Device |
| **file_hash** | Update file hash |
| **file_name** | Update file name |
| **severity** | Update severity |
| **severity_id** | Severity ID |
| **signature** | Update signature |
| **signature_id** | Signature ID |
| **status** | Update status |
| **tag** | Classification tags |
| **vendor_product** | Vendor product |
