# CIM Security Fields

Field mappings for security-focused data models: Alerts, Authentication, Data Loss Prevention, Endpoint, Event Signatures, Intrusion Detection, Malware, and Vulnerabilities.

---

## Alerts

| Field | Description |
|-------|-------------|
| **app** | Application context |
| **description** | Alert description |
| **dest** | Destination host |
| **dest_bunit** | Destination business unit |
| **dest_category** | Destination category |
| **dest_priority** | Destination priority |
| **dest_type** | Destination type |
| **id** | Alert ID |
| **mitre_technique_id** | MITRE ATT&CK technique ID |
| **severity** | Alert severity |
| **severity_id** | Severity identifier |
| **signature** | Alert signature |
| **signature_id** | Signature identifier |
| **src** | Source host |
| **src_bunit** | Source business unit |
| **src_category** | Source category |
| **src_priority** | Source priority |
| **src_type** | Source type |
| **tag** | Classification tags |
| **type** | Alert type |
| **user** | Associated user |
| **user_bunit** | User business unit |
| **user_category** | User category |
| **user_name** | User name |
| **user_priority** | User priority |
| **vendor_account** | Vendor account |
| **vendor_product_id** | Vendor product ID |
| **vendor_region** | Vendor region |

---

## Authentication

| Field | Description |
|-------|-------------|
| **action** | Authentication action (success, failure) |
| **app** | Application |
| **authentication_method** | Auth method (password, certificate, MFA) |
| **authentication_service** | Auth service (LDAP, Kerberos, RADIUS) |
| **dest** | Destination system |
| **dest_bunit** | Destination business unit |
| **dest_category** | Destination category |
| **dest_nt_domain** | Destination NT domain |
| **dest_priority** | Destination priority |
| **duration** | Session duration |
| **reason** | Failure reason |
| **response_time** | Response time |
| **signature** | Event signature |
| **signature_id** | Signature ID |
| **src** | Source system |
| **src_bunit** | Source business unit |
| **src_category** | Source category |
| **src_nt_domain** | Source NT domain |
| **src_priority** | Source priority |
| **src_user** | Source user |
| **src_user_bunit** | Source user business unit |
| **src_user_category** | Source user category |
| **src_user_id** | Source user ID |
| **src_user_priority** | Source user priority |
| **src_user_role** | Source user role |
| **src_user_type** | Source user type |
| **tag** | Classification tags |
| **user** | User account |
| **user_agent** | User agent string |
| **user_bunit** | User business unit |
| **user_category** | User category |
| **user_id** | User identifier |
| **user_priority** | User priority |
| **user_role** | User role |
| **user_type** | User type |
| **vendor_product** | Vendor product |

---

## Data Loss Prevention

| Field | Description |
|-------|-------------|
| **action** | DLP action taken |
| **app** | Application |
| **category** | Violation category |
| **dest** | Destination |
| **dest_bunit** | Destination business unit |
| **dest_category** | Destination category |
| **dest_priority** | Destination priority |
| **dest_zone** | Destination network zone |
| **dlp_type** | DLP violation type |
| **dvc** | Device |
| **dvc_bunit** | Device business unit |
| **dvc_category** | Device category |
| **dvc_priority** | Device priority |
| **dvc_zone** | Device zone |
| **object** | Object involved |
| **object_category** | Object category |
| **object_path** | Object path |
| **severity** | Severity level |
| **severity_id** | Severity ID |
| **signature** | DLP signature |
| **signature_id** | Signature ID |
| **src** | Source |
| **src_bunit** | Source business unit |
| **src_category** | Source category |
| **src_priority** | Source priority |
| **src_user** | Source user |
| **src_user_bunit** | Source user business unit |
| **src_user_category** | Source user category |
| **src_user_priority** | Source user priority |
| **src_zone** | Source zone |
| **tag** | Classification tags |
| **user** | User |
| **user_bunit** | User business unit |
| **user_category** | User category |
| **user_priority** | User priority |
| **vendor_product** | Vendor product |

---

## Endpoint

| Field | Description |
|-------|-------------|
| **action** | Endpoint action |
| **cpu_load_percent** | CPU utilization |
| **creation_time** | Process creation time |
| **description** | Description |
| **dest** | Destination/host |
| **dest_bunit** | Destination business unit |
| **dest_category** | Destination category |
| **dest_is_expected** | Expected destination flag |
| **dest_port** | Destination port |
| **dest_priority** | Destination priority |
| **dest_requires_av** | Requires antivirus |
| **dest_should_timesync** | Should time sync |
| **dest_should_update** | Should update |
| **file_access_time** | File access time |
| **file_acl** | File ACL |
| **file_create_time** | File creation time |
| **file_hash** | File hash |
| **file_modify_time** | File modification time |
| **file_name** | File name |
| **file_path** | File path |
| **file_size** | File size |
| **mem_used** | Memory used |
| **original_file_name** | Original file name |
| **os** | Operating system |
| **parent_process** | Parent process |
| **parent_process_exec** | Parent process executable |
| **parent_process_guid** | Parent process GUID |
| **parent_process_id** | Parent process ID |
| **parent_process_name** | Parent process name |
| **parent_process_path** | Parent process path |
| **process** | Process |
| **process_current_directory** | Process working directory |
| **process_exec** | Process executable |
| **process_guid** | Process GUID |
| **process_hash** | Process hash |
| **process_id** | Process ID |
| **process_integrity_level** | Process integrity level |
| **process_name** | Process name |
| **process_path** | Process path |
| **registry_hive** | Registry hive |
| **registry_key_name** | Registry key name |
| **registry_path** | Registry path |
| **registry_value_data** | Registry value data |
| **registry_value_name** | Registry value name |
| **registry_value_text** | Registry value text |
| **registry_value_type** | Registry value type |
| **service** | Service |
| **service_dll** | Service DLL |
| **service_dll_hash** | Service DLL hash |
| **service_dll_path** | Service DLL path |
| **service_dll_signature_exists** | DLL signature exists |
| **service_dll_signature_verified** | DLL signature verified |
| **service_exec** | Service executable |
| **service_hash** | Service hash |
| **service_id** | Service ID |
| **service_name** | Service name |
| **service_path** | Service path |
| **service_signature_exists** | Service signature exists |
| **service_signature_verified** | Service signature verified |
| **src** | Source |
| **src_bunit** | Source business unit |
| **src_category** | Source category |
| **src_port** | Source port |
| **src_priority** | Source priority |
| **src_requires_av** | Source requires AV |
| **src_should_timesync** | Source should time sync |
| **src_should_update** | Source should update |
| **start_mode** | Service start mode |
| **state** | State |
| **status** | Status |
| **tag** | Classification tags |
| **transport** | Transport protocol |
| **transport_dest_port** | Transport destination port |
| **user** | User |
| **user_bunit** | User business unit |
| **user_category** | User category |
| **user_id** | User ID |
| **user_priority** | User priority |
| **vendor_product** | Vendor product |

---

## Event Signatures

| Field | Description |
|-------|-------------|
| **dest** | Destination |
| **dest_bunit** | Destination business unit |
| **dest_category** | Destination category |
| **dest_priority** | Destination priority |
| **signature** | Event signature |
| **signature_id** | Signature ID |
| **tag** | Classification tags |
| **vendor_product** | Vendor product |

---

## Intrusion Detection

| Field | Description |
|-------|-------------|
| **action** | IDS action |
| **category** | Attack category |
| **dest** | Destination |
| **dest_bunit** | Destination business unit |
| **dest_category** | Destination category |
| **dest_port** | Destination port |
| **dest_priority** | Destination priority |
| **dvc** | Device (IDS sensor) |
| **dvc_bunit** | Device business unit |
| **dvc_category** | Device category |
| **dvc_priority** | Device priority |
| **file_hash** | File hash |
| **file_name** | File name |
| **file_path** | File path |
| **ids_type** | IDS type (network, host) |
| **severity** | Severity |
| **severity_id** | Severity ID |
| **signature** | Attack signature |
| **signature_id** | Signature ID |
| **src** | Source |
| **src_bunit** | Source business unit |
| **src_category** | Source category |
| **src_priority** | Source priority |
| **tag** | Classification tags |
| **transport** | Transport protocol |
| **user** | User |
| **user_bunit** | User business unit |
| **user_category** | User category |
| **user_priority** | User priority |
| **vendor_product** | Vendor product |

---

## Malware

| Field | Description |
|-------|-------------|
| **action** | Action taken |
| **category** | Malware category |
| **date** | Detection date |
| **dest** | Destination/infected host |
| **dest_bunit** | Destination business unit |
| **dest_category** | Destination category |
| **dest_nt_domain** | Destination NT domain |
| **dest_priority** | Destination priority |
| **dest_requires_av** | Requires antivirus |
| **file_hash** | File hash |
| **file_name** | Malware file name |
| **file_path** | Malware file path |
| **product_version** | AV product version |
| **sender** | Malware sender |
| **severity_id** | Severity ID |
| **signature** | Malware signature |
| **signature_id** | Signature ID |
| **signature_version** | Signature version |
| **src** | Source |
| **src_bunit** | Source business unit |
| **src_category** | Source category |
| **src_priority** | Source priority |
| **tag** | Classification tags |
| **url** | Associated URL |
| **user** | User |
| **user_bunit** | User business unit |
| **user_category** | User category |
| **user_priority** | User priority |
| **vendor_product** | AV vendor product |

---

## Vulnerabilities

| Field | Description |
|-------|-------------|
| **bugtraq** | Bugtraq ID |
| **category** | Vulnerability category |
| **cert** | CERT advisory |
| **cve** | CVE identifier |
| **cvss** | CVSS score |
| **dest** | Vulnerable host |
| **dest_bunit** | Destination business unit |
| **dest_category** | Destination category |
| **dest_priority** | Destination priority |
| **dvc** | Scanner device |
| **dvc_bunit** | Device business unit |
| **dvc_category** | Device category |
| **dvc_priority** | Device priority |
| **msft** | Microsoft advisory |
| **mskb** | Microsoft KB article |
| **severity** | Severity |
| **severity_id** | Severity ID |
| **signature** | Vulnerability signature |
| **signature_id** | Signature ID |
| **tag** | Classification tags |
| **url** | Reference URL |
| **user** | Associated user |
| **user_bunit** | User business unit |
| **user_category** | User category |
| **user_priority** | User priority |
| **vendor_product** | Scanner vendor product |
| **xref** | External reference |
