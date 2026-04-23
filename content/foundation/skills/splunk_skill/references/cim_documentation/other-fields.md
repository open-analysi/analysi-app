# CIM Other Fields

Field mappings for specialized data models: Email, Interprocess Messaging, Java Virtual Machines (JVM), Splunk Audit Logs, and TicketManagement.

---

## Email

| Field | Description |
|-------|-------------|
| **action** | Email action |
| **delay** | Delivery delay |
| **dest** | Recipient server |
| **dest_bunit** | Destination business unit |
| **dest_category** | Destination category |
| **dest_priority** | Destination priority |
| **duration** | Processing duration |
| **file_hash** | Attachment hash |
| **file_name** | Attachment name |
| **file_size** | Attachment size |
| **filter_action** | Filter action |
| **filter_score** | Spam score |
| **internal_message_id** | Internal message ID |
| **message_id** | Message ID |
| **message_info** | Message info |
| **orig_dest** | Original destination |
| **orig_recipient** | Original recipient |
| **orig_src** | Original source |
| **process** | Mail process |
| **process_id** | Process ID |
| **protocol** | Protocol (SMTP, IMAP) |
| **recipient** | Recipient address |
| **recipient_count** | Recipient count |
| **recipient_domain** | Recipient domain |
| **recipient_status** | Recipient status |
| **response_time** | Response time |
| **retries** | Retry count |
| **return_addr** | Return address |
| **signature** | Email signature/rule |
| **signature_extra** | Additional signature info |
| **signature_id** | Signature ID |
| **size** | Message size |
| **src** | Sender server |
| **src_bunit** | Source business unit |
| **src_category** | Source category |
| **src_priority** | Source priority |
| **src_user** | Sender |
| **src_user_bunit** | Sender business unit |
| **src_user_category** | Sender category |
| **src_user_domain** | Sender domain |
| **src_user_priority** | Sender priority |
| **status_code** | Status code |
| **subject** | Email subject |
| **tag** | Classification tags |
| **url** | URL in email |
| **user** | Associated user |
| **user_bunit** | User business unit |
| **user_category** | User category |
| **user_priority** | User priority |
| **vendor_product** | Vendor product |
| **xdelay** | Extended delay |
| **xref** | External reference |

---

## Interprocess Messaging

| Field | Description |
|-------|-------------|
| **dest** | Destination |
| **dest_bunit** | Destination business unit |
| **dest_category** | Destination category |
| **dest_priority** | Destination priority |
| **duration** | Message duration |
| **endpoint** | Messaging endpoint |
| **endpoint_version** | Endpoint version |
| **message** | Message content |
| **message_consumed_time** | Consumed time |
| **message_correlation_id** | Correlation ID |
| **message_delivered_time** | Delivered time |
| **message_delivery_mode** | Delivery mode |
| **message_expiration_time** | Expiration time |
| **message_id** | Message ID |
| **message_priority** | Message priority |
| **message_properties** | Message properties |
| **message_received_time** | Received time |
| **message_redelivered** | Redelivered flag |
| **message_reply_dest** | Reply destination |
| **message_type** | Message type |
| **parameters** | Parameters |
| **payload** | Message payload |
| **payload_type** | Payload type |
| **request_payload** | Request payload |
| **request_payload_type** | Request payload type |
| **request_sent_time** | Request sent time |
| **response_code** | Response code |
| **response_payload_type** | Response payload type |
| **response_received_time** | Response received time |
| **response_time** | Response time |
| **return_message** | Return message |
| **rpc_protocol** | RPC protocol |
| **status** | Status |
| **tag** | Classification tags |
| **vendor_product** | Vendor product |

---

## Java Virtual Machines (JVM)

| Field | Description |
|-------|-------------|
| **cm_enabled** | Class memory enabled |
| **cm_supported** | Class memory supported |
| **committed_memory** | Committed memory |
| **compilation_time** | Compilation time |
| **cpu_time** | CPU time |
| **cpu_time_enabled** | CPU time enabled |
| **cpu_time_supported** | CPU time supported |
| **current_cpu_time** | Current CPU time |
| **current_loaded** | Currently loaded classes |
| **current_user_time** | Current user time |
| **daemon_thread_count** | Daemon thread count |
| **dest_bunit** | Destination business unit |
| **dest_category** | Destination category |
| **dest_priority** | Destination priority |
| **free_physical_memory** | Free physical memory |
| **free_swap** | Free swap |
| **heap_committed** | Heap committed |
| **heap_initial** | Heap initial |
| **heap_max** | Heap max |
| **heap_used** | Heap used |
| **jvm_description** | JVM description |
| **max_file_descriptors** | Max file descriptors |
| **non_heap_committed** | Non-heap committed |
| **non_heap_initial** | Non-heap initial |
| **non_heap_max** | Non-heap max |
| **non_heap_used** | Non-heap used |
| **objects_pending** | Objects pending finalization |
| **omu_supported** | Object monitor usage supported |
| **open_file_descriptors** | Open file descriptors |
| **os** | Operating system |
| **os_architecture** | OS architecture |
| **os_version** | OS version |
| **peak_thread_count** | Peak thread count |
| **physical_memory** | Physical memory |
| **process_name** | Process name |
| **start_time** | JVM start time |
| **swap_space** | Swap space |
| **synch_supported** | Synchronization supported |
| **system_load** | System load |
| **tag** | Classification tags |
| **thread_count** | Thread count |
| **threads_started** | Threads started |
| **total_loaded** | Total classes loaded |
| **total_processors** | Total processors |
| **total_unloaded** | Total classes unloaded |
| **uptime** | JVM uptime |
| **vendor_product** | JVM vendor |
| **version** | JVM version |

---

## Splunk Audit Logs

| Field | Description |
|-------|-------------|
| **access_count** | Access count |
| **access_time** | Access time |
| **action_mode** | Action mode |
| **action_name** | Action name |
| **action_status** | Action status |
| **app** | Splunk app |
| **buckets** | Buckets |
| **buckets_size** | Buckets size |
| **complete** | Complete flag |
| **component** | Splunk component |
| **cron** | Cron schedule |
| **datamodel** | Data model |
| **digest** | Digest |
| **duration** | Duration |
| **earliest** | Earliest time |
| **event_id** | Event ID |
| **host** | Splunk host |
| **info** | Info |
| **is_inprogress** | In progress flag |
| **last_error** | Last error |
| **last_sid** | Last search ID |
| **latest** | Latest time |
| **mod_time** | Modification time |
| **orig_rid** | Original request ID |
| **orig_sid** | Original search ID |
| **retention** | Retention |
| **rid** | Request ID |
| **savedsearch_name** | Saved search name |
| **search** | Search string |
| **search_et** | Search earliest time |
| **search_lt** | Search latest time |
| **search_name** | Search name |
| **search_type** | Search type |
| **sid** | Search ID |
| **signature** | Signature |
| **size** | Size |
| **source** | Source |
| **sourcetype** | Sourcetype |
| **spent** | Time spent |
| **splunk_server** | Splunk server |
| **status** | Status |
| **summary_id** | Summary ID |
| **tag** | Classification tags |
| **uri** | URI |
| **user** | Splunk user |
| **user_bunit** | User business unit |
| **user_category** | User category |
| **user_priority** | User priority |
| **view** | View |

---

## TicketManagement

| Field | Description |
|-------|-------------|
| **affect_dest** | Affected destination |
| **change** | Change reference |
| **comments** | Ticket comments |
| **description** | Ticket description |
| **dest** | Affected system |
| **dest_bunit** | Destination business unit |
| **dest_category** | Destination category |
| **dest_priority** | Destination priority |
| **incident** | Incident reference |
| **priority** | Ticket priority |
| **problem** | Problem reference |
| **severity** | Severity |
| **severity_id** | Severity ID |
| **splunk_id** | Splunk ID |
| **splunk_realm** | Splunk realm |
| **src_user** | Submitting user |
| **src_user_bunit** | Submitting user business unit |
| **src_user_category** | Submitting user category |
| **src_user_priority** | Submitting user priority |
| **status** | Ticket status |
| **tag** | Classification tags |
| **ticket_id** | Ticket ID |
| **time_submitted** | Time submitted |
| **user** | Assigned user |
| **user_bunit** | User business unit |
| **user_category** | User category |
| **user_priority** | User priority |
