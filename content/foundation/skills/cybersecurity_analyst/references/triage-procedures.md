# Triage Checklist and Procedures

(from [RSA sessions](https://www.youtube.com/watch?v=W7I-2Nv71PY&))

## The First Questions to Ask

1. **Have I seen this alert before?** This is why it's very important to have a detailed catalog of all your investigations. This is the best way to easily identify a trivial FP and a known TP we've seen before
   - For example, we can have a pattern of alerts that when they happen together they may denote that we have a new Domain Controller starting.

2. **Noisiest alerts are usually the most worthless.** So Inverse Alert Frequency is similar to TF-IDF. The less frequent an alert, the more interesting it usually is.
   - Attackers want to be stealthy, so they will try not generate 1000 or even hundred of alerts a day

3. **Scary words are important.** When an alert says that it is Critical or High, then we should be paying attention. Scary words were added there for a reason.

4. **Multiple sources alerting us together** (or multiple alert-types from the same source) tell us a lot about risky behaviors.
   - When something wrong happens it typically goes really WRONG! So lots of strange things will tend to happen together

5. **(Optional) Low confidence alerts** (if that is documented) can more easily be ignored.

## Suggested Runbook Process

### 1. Understand Why the Alert Was Triggered

In order to perform a better analysis and to determine whether the triggered alert is false positive, it is first necessary to understand why the rule was triggered. Instead of starting the analysis directly, first understand why this rule was triggered.

- **Examine the rule name.** Rule names are usually created specifically for the attack to be detected. By examining the rule name, you can understand which attack you are facing.
- **Find between which two devices the traffic is occurring.** It's a good starting point to understand the situation by learning about the direction of traffic, what protocol is used between devices, etc.

### 2. Collect Data

Gather some information that can be gathered quickly to get a better understanding of the traffic. These can be summarized as follows.

- **Ownership of the IP addresses and devices**
- **If the traffic is coming from outside (Internet):**
  - Ownership of IP address (Static or Pool Address? Who owns it? Is it web hosting?)
  - Reputation of IP Address (Search in VirusTotal, AbuseIPDB, Cisco Talos)
- **If the traffic is coming from company network:**
  - Hostname of the device
  - Who owns the device (username)
  - Last user logon time

### 3. Examine HTTP Traffic

Check the traffic content for any suspicious conditions such as web attack payloads (SQL Injection, XSS, Command Injection, IDOR, RFI/LFI).

Examine all the fields in the HTTP Request. Since the attackers do not only attack through the URL, all the data from the source must be examined to understand whether there is really a cyber attack.

### 4. Check If It Is a Planned Test

Penetration tests or attack simulation products can trigger False Positive alarms if the rules are not set correctly. Check whether the malicious traffic is the result of a planned test.

- Check if there is an email showing that there will be planned work by searching for information such as hostname, username, IP address on the mailbox.
- Check if the device generating malicious traffic belongs to attack simulation products. If the Hostname contains the name of Attack Simulation products (such as Verodin, AttackIQ, Picus…), these devices belong to Attack Simulation products within the framework of companyxyz simulation and it is a planned work.

### 5. Check Whether the Attack Was Successful

Investigate whether the attack was successful. Detection mechanisms vary according to the attack type. Some tips that can help with your investigation:

- In Command Injection attacks, you can understand whether the attack was successful by looking at the "Command History" of the relevant device via Endpoint Security. In SQL Injection attacks, attackers can run commands on the device with the help of functions such as "xp_cmdshell". For this reason, you may need to look at the "Command History" in SQL Injection attacks.
- You can guess by looking at the HTTP Response size in SQL Injection and IDOR attacks

### 6. Do You Need Tier 2 Escalation?

**Tier 2 escalation should be performed in the following situations:**
- In cases where the attack succeeds
- When the attacker compromises a device in the internal network (in cases where the direction of harmful traffic is from inside → inside)

**Tier 2 escalation is NOT required in the following cases:**
- In cases where attacks from the Internet do not succeed

## Alert Classification/Categorization

This is rather broad categorization of alerts from Megan Benoit (see youtube video above)

### Suspicious Connectivity Behavior (from IDS or networking)

- One source (internal) to multiple destinations?
- Multiple sources to 1-2 destinations?
- What's the direction of the connection? N-S, E-W
- Was the connection allowed or denied?
- **If the IP is remote:**
  - What reputation we have for it from external sources (threat intelligence)
  - When was it first seen internally? How many internal sources connect to it. What information do we have about those internal sources (e.g., all windows machines)?
  - When did this activity start? If it has been going on for a while, it's less likely to be bad.
- Sometimes if you run out of sources and the alert is atomic, where we cannot aggregate more activity to it, it's just better to go ahead and close it for now. The signal remains in case it's needed later (in case something additional comes along). But for now, if there is nothing more to do, even if there are unknowns, it's ok to go ahead and close it.

### Malware (Suspicious Process from EDR)

- **Was it behavioral or signature based?**
  - Behavioral usually means communication, so we need to investigate the IPs
- **Where was the file located?**
  - Downloaded folders and later deleted by AV? Less severe, the user tried to do something dump and AV worked for once.
  - Or scanned and found in the downloaded folders?
  - Or even scarier, it was located in the installed apps folder?
  - Or is it found on the browsers or email app cache folder? Maybe a phishing attack
- **What account/user is this process running?** Privileged account? Is it unusual (anomalous)?
- **Document the parent process** is very important
- **Are the executable files signed?**
- **Can you use a file emulator** to figure out what's happening with this file?
- Of course, we need to figure out if something else suspicious happened together. Like lateral movement etc.

### Phishing (Email / or suspicious Login)

Yes, usually suspicious logins are associated with phishing type of attacks.

- Did the receiver actually reply?

## Alert Grouping/Aggregation

1. **Same entity/time** - multiple alerts should be investigated together (one investigation)
2. **Same threat object** - Multiple alerts suggesting that multiple users are accessing the same phishing website.

## Common Sources of False Positives

**This is very important**

- **Is this a new Domain Controller (DC)**
  - It's good to keep a list of the alerts that happen together that denote known behaviors that we know are benign, like a new DC going live.
- **Backups moving through the network** are often a source of FPs!
  - The volume is high (look a lot like exfiltration)
- **A newly productized detections.** Two things can be happening here:
  - 1: The detection needs tuning
  - 2: The detection is detecting something zero-day. Or that has been happening for a while and we are just getting alerted to it.
    - The best way to know this is to use forums (X/Reddit) to figure out what is being discussed for this particular type of detection from vendor X to see if there is known issues with FPs
