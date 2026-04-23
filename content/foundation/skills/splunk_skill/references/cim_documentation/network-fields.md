# CIM Network Fields

Field mappings for network-focused data models: Certificates, Network Resolution (DNS), Network Sessions, Network Traffic, and Web.

---

## Certificates

| Field | Description |
|-------|-------------|
| **dest** | Destination host |
| **dest_bunit** | Destination business unit |
| **dest_category** | Destination category |
| **dest_port** | Destination port |
| **dest_priority** | Destination priority |
| **duration** | Certificate validity duration |
| **response_time** | Response time |
| **src** | Source host |
| **src_bunit** | Source business unit |
| **src_category** | Source category |
| **src_port** | Source port |
| **src_priority** | Source priority |
| **ssl_end_time** | Certificate expiration |
| **ssl_engine** | SSL engine |
| **ssl_hash** | Certificate hash |
| **ssl_is_valid** | Validity flag |
| **ssl_issuer** | Certificate issuer |
| **ssl_issuer_common_name** | Issuer common name |
| **ssl_issuer_email** | Issuer email |
| **ssl_issuer_email_domain** | Issuer email domain |
| **ssl_issuer_locality** | Issuer locality |
| **ssl_issuer_organization** | Issuer organization |
| **ssl_issuer_state** | Issuer state |
| **ssl_issuer_street** | Issuer street |
| **ssl_issuer_unit** | Issuer organizational unit |
| **ssl_name** | Certificate name |
| **ssl_policies** | Certificate policies |
| **ssl_publickey** | Public key |
| **ssl_publickey_algorithm** | Public key algorithm |
| **ssl_serial** | Serial number |
| **ssl_session_id** | Session ID |
| **ssl_signature_algorithm** | Signature algorithm |
| **ssl_start_time** | Certificate start time |
| **ssl_subject** | Certificate subject |
| **ssl_subject_common_name** | Subject common name |
| **ssl_subject_email** | Subject email |
| **ssl_subject_email_domain** | Subject email domain |
| **ssl_subject_locality** | Subject locality |
| **ssl_subject_organization** | Subject organization |
| **ssl_subject_state** | Subject state |
| **ssl_subject_street** | Subject street |
| **ssl_subject_unit** | Subject organizational unit |
| **ssl_validity_window** | Validity window |
| **ssl_version** | SSL/TLS version |
| **tag** | Classification tags |
| **transport** | Transport protocol |

---

## Network Resolution (DNS)

| Field | Description |
|-------|-------------|
| **additional_answer_count** | Additional answer count |
| **answer** | DNS answer |
| **answer_count** | Answer count |
| **authority_answer_count** | Authority answer count |
| **dest** | DNS server |
| **dest_bunit** | Destination business unit |
| **dest_category** | Destination category |
| **dest_port** | Destination port (usually 53) |
| **dest_priority** | Destination priority |
| **duration** | Query duration |
| **message_type** | DNS message type |
| **name** | Queried domain name |
| **query** | DNS query |
| **query_count** | Query count |
| **query_type** | Query type (A, AAAA, MX, etc.) |
| **record_type** | Record type |
| **reply_code** | Reply code |
| **reply_code_id** | Reply code ID |
| **response_time** | Response time |
| **src** | Querying host |
| **src_bunit** | Source business unit |
| **src_category** | Source category |
| **src_port** | Source port |
| **src_priority** | Source priority |
| **tag** | Classification tags |
| **transaction_id** | Transaction ID |
| **transport** | Transport protocol (UDP/TCP) |
| **ttl** | Time to live |
| **vendor_product** | DNS server product |

---

## Network Sessions

| Field | Description |
|-------|-------------|
| **action** | Session action |
| **dest_bunit** | Destination business unit |
| **dest_category** | Destination category |
| **dest_dns** | Destination DNS name |
| **dest_ip** | Destination IP |
| **dest_mac** | Destination MAC |
| **dest_nt_host** | Destination NT host |
| **dest_priority** | Destination priority |
| **duration** | Session duration |
| **lease_duration** | DHCP lease duration |
| **lease_scope** | DHCP lease scope |
| **response_time** | Response time |
| **signature** | Session signature |
| **signature_id** | Signature ID |
| **src_bunit** | Source business unit |
| **src_category** | Source category |
| **src_dns** | Source DNS name |
| **src_ip** | Source IP |
| **src_mac** | Source MAC |
| **src_nt_host** | Source NT host |
| **src_priority** | Source priority |
| **tag** | Classification tags |
| **user** | Associated user |
| **user_bunit** | User business unit |
| **user_category** | User category |
| **user_priority** | User priority |
| **vendor_product** | Vendor product |

---

## Network Traffic

| Field | Description |
|-------|-------------|
| **action** | Traffic action (allow, block) |
| **app** | Application |
| **bytes** | Total bytes |
| **bytes_in** | Bytes inbound |
| **bytes_out** | Bytes outbound |
| **channel** | Network channel |
| **dest** | Destination |
| **dest_bunit** | Destination business unit |
| **dest_category** | Destination category |
| **dest_interface** | Destination interface |
| **dest_ip** | Destination IP |
| **dest_mac** | Destination MAC |
| **dest_port** | Destination port |
| **dest_priority** | Destination priority |
| **dest_translated_ip** | NAT destination IP |
| **dest_translated_port** | NAT destination port |
| **dest_zone** | Destination zone |
| **direction** | Traffic direction |
| **duration** | Connection duration |
| **dvc** | Device (firewall, router) |
| **dvc_bunit** | Device business unit |
| **dvc_category** | Device category |
| **dvc_ip** | Device IP |
| **dvc_mac** | Device MAC |
| **dvc_priority** | Device priority |
| **dvc_zone** | Device zone |
| **flow_id** | Flow identifier |
| **icmp_code** | ICMP code |
| **icmp_type** | ICMP type |
| **packets** | Total packets |
| **packets_in** | Packets inbound |
| **packets_out** | Packets outbound |
| **process_id** | Process ID |
| **protocol** | Protocol |
| **protocol_version** | Protocol version |
| **response_time** | Response time |
| **rule** | Firewall rule |
| **session_id** | Session ID |
| **src** | Source |
| **src_bunit** | Source business unit |
| **src_category** | Source category |
| **src_interface** | Source interface |
| **src_ip** | Source IP |
| **src_mac** | Source MAC |
| **src_port** | Source port |
| **src_priority** | Source priority |
| **src_translated_ip** | NAT source IP |
| **src_translated_port** | NAT source port |
| **src_zone** | Source zone |
| **ssid** | Wireless SSID |
| **tag** | Classification tags |
| **tcp_flag** | TCP flags |
| **tos** | Type of service |
| **transport** | Transport protocol |
| **ttl** | Time to live |
| **user** | Associated user |
| **user_bunit** | User business unit |
| **user_category** | User category |
| **user_priority** | User priority |
| **vendor_account** | Vendor account |
| **vendor_product** | Vendor product |
| **vlan** | VLAN ID |
| **wifi** | WiFi indicator |

---

## Web

| Field | Description |
|-------|-------------|
| **action** | Web action |
| **app** | Application |
| **bytes** | Total bytes |
| **bytes_in** | Bytes received |
| **bytes_out** | Bytes sent |
| **cached** | Cached response flag |
| **category** | URL category |
| **cookie** | Cookie value |
| **dest** | Destination host |
| **dest_bunit** | Destination business unit |
| **dest_category** | Destination category |
| **dest_port** | Destination port |
| **dest_priority** | Destination priority |
| **duration** | Request duration |
| **error_code** | HTTP error code |
| **http_content_type** | Content type |
| **http_method** | HTTP method (GET, POST, etc.) |
| **http_referrer** | Referrer URL |
| **http_referrer_domain** | Referrer domain |
| **http_user_agent** | User agent string |
| **http_user_agent_length** | User agent length |
| **operation** | Web operation |
| **response_time** | Response time |
| **site** | Website |
| **src** | Source host |
| **src_bunit** | Source business unit |
| **src_category** | Source category |
| **src_priority** | Source priority |
| **status** | HTTP status code |
| **storage_name** | Storage name |
| **tag** | Classification tags |
| **uri_path** | URI path |
| **uri_query** | URI query string |
| **url** | Full URL |
| **url_domain** | URL domain |
| **url_length** | URL length |
| **user** | User |
| **user_bunit** | User business unit |
| **user_category** | User category |
| **user_priority** | User priority |
| **vendor_product** | Vendor product |
