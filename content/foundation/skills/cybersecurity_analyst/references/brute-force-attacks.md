# Brute Force Attack Investigation Reference

## Overview

Brute force attacks are trial-and-error attempts to crack sensitive data like usernames, passwords, directories, or encryption keys. Duration depends on data complexity - simple passwords crack quickly, complex ones could take years.

## Types of Brute Force Attacks

### 1. Online Brute Force Attacks

Attacker and victim are simultaneously online, may or may not interact directly.

**Passive Online Attacks**
- Attacker and victim on same network, no direct communication
- Attacker passively captures password without direct connection
- Examples:
  - **Man-in-the-Middle (MITM)**: Listening to traffic to capture passwords
  - **Sniffing**: Capturing data packets on network (only effective on networks using hubs, not switches)

**Active Online Attacks**
- Attacker directly communicates with victim's machine
- Attempts to guess login credentials for various services (web, email, SSH, RDP, database)
- Effective for simple passwords
- **Risk**: Can lead to account lockouts or system disablement

### 2. Offline Brute Force Attacks

Target previously captured encrypted or hashed data. No direct connection needed to victim's machine.

**Password Information Sources**:
- Capturing packets on wireless networks
- Man-in-the-middle attacks
- SQL injection vulnerabilities
- System databases (SAM or NTDS.dit on Windows)

**Attack Methods**:

**Dictionary Attacks**
- Exploits use of common passwords
- Attacker uses dictionary of common passwords
- Tests each word against target system

**Brute Force Attacks**
- Systematically tries all possibilities within specified range
- Example: All combinations of uppercase, lowercase, digits, special characters for passwords up to 5 characters
- Time-consuming for complex passwords

**Rainbow Table Attacks**
- Precomputes table of hash values for all possible passwords within range
- Compares precomputed hashes to captured password hash
- Requires significant processing power and storage space

## Common Targets for Brute Force

Protocols/services most frequently attacked:

- Web application login pages
- RDP services
- SSH services
- Mail server login pages
- LDAP services
- Database services (MSSQL, MySQL, PostgreSQL, Oracle, etc.)
- Web application home directories (directory brute force)
- DNS servers (DNS brute force to detect records)

## Common Brute Force Tools

**Aircrack-ng**
- 802.11a/b/g WEP/WPA cracking program
- Recovers 40-bit, 104-bit, 256-bit, or 512-bit WEP keys
- Attacks WPA1/2 networks

**John the Ripper**
- Designed to find weak passwords
- Runs on 15 different platforms (Unix, Windows, OpenVMS)

**L0phtCrack**
- Cracks Windows passwords
- Uses rainbow tables, dictionaries, multiprocessor algorithms

**Hashcat**
- Supports 5 unique attack modes
- Over 300 highly-optimized hashing algorithms
- Supports CPUs, GPUs, hardware accelerators on Linux

**Ncrack**
- Cracks network authentication
- Works on Windows, Linux, BSD
- Tests hosts and networking devices for poor passwords

**Hydra**
- Parallelized login cracker
- Supports numerous protocols
- Very fast and flexible

## Prevention Best Practices

### Strong Password Requirements

- Minimum 8 characters
- Combine letters, numbers, and symbols
- Avoid easily found personal information
- Create unique passwords for each account
- Avoid common patterns

### Administrative Controls

**Lock Policy**
- Lock accounts after set number of failed login attempts
- Unlock requires administrator action

**Progressive Delays**
- Temporarily lock accounts after defined number of failed attempts

**reCAPTCHA**
- Require users to complete simple tasks before logging in

**Strong Password Policy**
- Enforce long, complex passwords
- Require periodic password changes

**Two-Factor Authentication (2FA)**
- Require second form of verification after username/password
- Methods: SMS, email, token, push notification

## Detection Methods

### SIEM Rule-Based Detection

SIEM systems detect brute force by monitoring:
- Number of unsuccessful login attempts
- Time period of attempts
- Source IP patterns
- User account patterns

**Analysis approach**: Examine logs from attempted protocol/application

## SSH Brute Force Detection

### Investigation Commands

**Find failed login attempts by username**:
```bash
cat auth.log.1 | grep "Failed password" | cut -d " " -f10 | sort | uniq -c | sort
```

**Find IP addresses making failed attempts**:
```bash
cat auth.log.1 | grep "Failed password" | cut -d " " -f12 | sort | uniq -c | sort
```

**Find successful logins**:
```bash
cat auth.log.1 | grep "Accepted password"
```

### Analysis Pattern

**Indicators of successful brute force**:
1. Many failed login attempts from same IP
2. Failed attempts using same username
3. Successful login after multiple failures
4. Same source IP for failures and success

**Example findings**:
- User "analyst": Successful login with NO previous failed attempts = **Normal login**
- User "jdoe": Many failed attempts from 188.58.65.203, then successful login = **Successful brute force**

## HTTP Login Brute Force Detection

### Investigation Approach

1. Open relevant log file with text editor
2. Examine HTTP response patterns
3. Look for dictionary attack patterns on login page

### Key Indicators

**Response size differences**:
- Failed login attempts: Small response size (consistent)
- Successful login attempt: Different/larger response size
- Pattern: Multiple small responses, then one different-sized response = successful brute force

## Windows Login Brute Force Detection

### Critical Event IDs

**Event ID 4624** - Successful logon
- Use to find successful login date/time
- Check "Logon Type" field:
  - Type 10 = Remote Desktop Services/RDP

**Event ID 4625** - Failed logon
- Use to track unsuccessful login attempts
- Pattern of multiple 4625 events followed by 4624 = successful brute force

**Reference**: https://www.ultimatewindowssecurity.com/securitylog/encyclopedia/default.aspx

### Windows RDP Brute Force Detection Workflow

1. Open Event Viewer
2. Select "Security" logs
3. Create filter for Event ID 4625 (failed logon)
4. Check for patterns:
   - Multiple 4625 events in sequence
   - Same username across attempts
   - Same source IP
   - Timestamps close together
5. Search for Event ID 4624 (successful logon) after 4625 events
6. Check "Logon Type" field (Type 10 = RDP)

### Investigation Example

**Pattern indicating successful brute force**:
```
Event 4625 - Failed logon (Administrator) - 10:15 PM
Event 4625 - Failed logon (Administrator) - 10:16 PM
Event 4625 - Failed logon (Administrator) - 10:16 PM
Event 4625 - Failed logon (Administrator) - 10:17 PM
Event 4624 - Successful logon (Administrator) - 10:17 PM (Logon Type: 10)
```

**Conclusion**: Attacker successfully brute forced RDP access after 4 failed attempts

## Investigation Best Practices

### Log Analysis Priorities

1. **Identify failed login patterns**:
   - Count of failures per user
   - Count of failures per source IP
   - Time clustering of failures

2. **Correlate with successful logins**:
   - Check if success follows multiple failures
   - Verify same source IP/user combination

3. **Assess impact**:
   - What level of access was gained?
   - What actions occurred after successful login?
   - Lateral movement detected?

### Response Actions

**Confirmed Brute Force - Failed**:
- Block source IP at firewall
- Document attempt for tracking
- Check for attempts against other accounts

**Confirmed Brute Force - Successful**:
- **Immediate**: Disable compromised account
- **Immediate**: Block source IP
- **Immediate**: Check for lateral movement
- Investigate all actions by compromised account post-login
- Force password reset for compromised account
- Check for persistence mechanisms
- Review Event ID 4624 logs for session details
- Escalate to incident response team

### Common Password Storage Locations (for context)

**Windows**:
- SAM (Security Account Manager) database
- NTDS.dit (Active Directory database)

**Linux**:
- /etc/shadow (hashed passwords)
- /etc/passwd (user information)

**Note**: Understanding these locations helps investigate how attackers may have obtained password hashes for offline attacks.

## Key Indicators Summary

**Active brute force in progress**:
- High frequency of failed login attempts
- Same source IP, different passwords
- Sequential timing
- Single or small set of target usernames

**Successful brute force**:
- Pattern of failures followed by success
- Same source IP across attempts
- Same target username
- Success within reasonable timeframe of failures

**Advanced brute force**:
- Distributed across multiple IPs (credential stuffing)
- Slow and low (evades threshold-based detection)
- Successful without many failures (password reuse, leaked credentials)
