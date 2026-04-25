"""SentinelOne Threat -> OCSF normalizer.

Produces OCSF Detection Finding v1.8.0 directly from SentinelOne threat
objects (from GET /web/api/v2.1/threats) by mapping S1-specific fields
to OCSF structure.  Direct OCSF output.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from alert_normalizer.base_ocsf import BaseOCSFNormalizer
from alert_normalizer.helpers.ip_classification import is_public_ip
from analysi.schemas.ocsf.detection_finding import OCSF_VERSION, PROFILES

# ── Mapping constants ─────────────────────────────────────────────────

# SentinelOne confidenceLevel -> OCSF severity (id, label)
CONFIDENCE_TO_SEVERITY: dict[str, tuple[int, str]] = {
    "malicious": (5, "Critical"),
    "suspicious": (4, "High"),
    "n/a": (1, "Info"),
}

# SentinelOne classification -> finding_info.types
CLASSIFICATION_TO_TYPES: dict[str, str] = {
    "Malware": "Malware",
    "PUP": "PUP",
    "Ransomware": "Ransomware",
    "Trojan": "Trojan",
    "Worm": "Worm",
    "Backdoor": "Backdoor",
    "Exploit": "Exploit",
    "Adware": "Adware",
    "Hacking Tool": "Hacking Tool",
    "Miner": "Cryptominer",
}

# SentinelOne analystVerdict -> OCSF disposition mapping
VERDICT_TO_DISPOSITION: dict[str, tuple[int, str]] = {
    "true_positive": (10, "True Positive"),
    "false_positive": (11, "False Positive"),
    "suspicious": (14, "Suspicious"),
    "undefined": (0, "Unknown"),
}

# SentinelOne mitigationStatus -> OCSF action mapping
MITIGATION_TO_ACTION: dict[str, tuple[int, str]] = {
    "mitigated": (2, "Denied"),
    "active": (1, "Allowed"),
    "blocked": (2, "Denied"),
    "not_mitigated": (1, "Allowed"),
}


def _build_tactic_from_list(tactics: list[Any]) -> dict[str, Any] | None:
    """Build an OCSF tactic object from the first tactic in the list."""
    if not tactics:
        return None
    tactic = tactics[0] if isinstance(tactics[0], dict) else {}
    if not tactic:
        return None
    tactic_obj: dict[str, Any] = {}
    uid = tactic.get("id") or tactic.get("source")
    if uid:
        tactic_obj["uid"] = uid
    if tactic.get("name"):
        tactic_obj["name"] = tactic["name"]
    return tactic_obj if tactic_obj else None


def _iso_to_epoch_ms(ts: str | datetime) -> int:
    """Convert ISO 8601 string or datetime to epoch milliseconds."""
    if isinstance(ts, datetime):
        return int(ts.timestamp() * 1000)
    dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    return int(dt.timestamp() * 1000)


class SentinelOneOCSFNormalizer(BaseOCSFNormalizer):
    """Normalizer for SentinelOne threats -> OCSF Detection Finding.

    Maps SentinelOne threat objects directly to OCSF Detection Finding
    v1.8.0 structure.
    """

    def to_ocsf(self, data: dict[str, Any]) -> dict[str, Any]:
        """Convert SentinelOne threat to OCSF Detection Finding.

        Args:
            data: Raw SentinelOne threat object.

        Returns:
            OCSF Detection Finding v1.8.0 dict.
        """
        ocsf: dict[str, Any] = {}
        threat_info = data.get("threatInfo", {})
        agent_info = data.get("agentRealtimeInfo", {})

        # ── OCSF scaffold ────────────────────────────────────────────
        ocsf["class_uid"] = 2004
        ocsf["class_name"] = "Detection Finding"
        ocsf["category_uid"] = 2
        ocsf["category_name"] = "Findings"
        ocsf["activity_id"] = 1
        ocsf["activity_name"] = "Create"
        ocsf["type_uid"] = 200401
        ocsf["type_name"] = "Detection Finding: Create"

        # ── Title / message ──────────────────────────────────────────
        threat_name = threat_info.get("threatName", "Unknown Threat")
        classification = threat_info.get("classification", "")
        hostname = agent_info.get("agentComputerName", "")

        message_parts = [threat_name]
        if classification:
            message_parts.append(f"({classification})")
        if hostname:
            message_parts.append(f"on {hostname}")
        ocsf["message"] = " ".join(message_parts)

        # ── Time ─────────────────────────────────────────────────────
        created_at = threat_info.get("createdAt")
        updated_at = threat_info.get("updatedAt")

        if created_at:
            ocsf["time"] = _iso_to_epoch_ms(created_at)
            ocsf["time_dt"] = created_at

        if updated_at:
            ocsf["ocsf_time"] = _iso_to_epoch_ms(updated_at)

        # ── Severity ─────────────────────────────────────────────────
        confidence = threat_info.get("confidenceLevel", "n/a")
        sev_id, sev_label = CONFIDENCE_TO_SEVERITY.get(
            str(confidence).lower(), (1, "Info")
        )
        ocsf["severity_id"] = sev_id
        ocsf["severity"] = sev_label

        # ── Metadata ─────────────────────────────────────────────────
        metadata: dict[str, Any] = {
            "version": OCSF_VERSION,
            "profiles": list(PROFILES),
            "product": {
                "vendor_name": "SentinelOne",
                "name": "Singularity",
            },
        }

        threat_id = data.get("id")
        if threat_id:
            metadata["event_code"] = str(threat_id)

        ocsf["metadata"] = metadata

        # ── Finding Info ─────────────────────────────────────────────
        ocsf["finding_info"] = self._build_finding_info(data, threat_info)

        # ── SentinelOne threats are always alertable findings ────────
        ocsf["is_alert"] = True

        # ── Status — always New for ingested threats ─────────────────
        ocsf["status_id"] = 1
        ocsf["status"] = "New"

        # ── Disposition (from analystVerdict) ────────────────────────
        analyst_verdict = threat_info.get("analystVerdict", "undefined")
        disp_id, disp_label = VERDICT_TO_DISPOSITION.get(
            str(analyst_verdict).lower(), (0, "Unknown")
        )
        ocsf["disposition_id"] = disp_id
        ocsf["disposition"] = disp_label

        # ── Action (from mitigationStatus) ───────────────────────────
        mitigation = threat_info.get("mitigationStatus", "")
        act_id, act_label = MITIGATION_TO_ACTION.get(
            str(mitigation).lower(), (0, "Unknown")
        )
        ocsf["action_id"] = act_id
        ocsf["action"] = act_label

        # ── Raw data ─────────────────────────────────────────────────
        raw_data = json.dumps(data, default=str)
        ocsf["raw_data"] = raw_data
        ocsf["raw_data_hash"] = hashlib.sha256(raw_data.encode()).hexdigest()

        # ── Device ───────────────────────────────────────────────────
        self._build_device(agent_info, ocsf)

        # ── Actor ────────────────────────────────────────────────────
        self._build_actor(threat_info, ocsf)

        # ── Observables ──────────────────────────────────────────────
        self._build_observables(data, ocsf)

        # ── Evidences ────────────────────────────────────────────────
        self._build_evidences(threat_info, ocsf)

        # ── Unmapped fields ──────────────────────────────────────────
        unmapped = self._collect_unmapped(data)
        if unmapped:
            ocsf["unmapped"] = unmapped

        return ocsf

    # ── Private builders ─────────────────────────────────────────────

    def _build_finding_info(
        self,
        data: dict[str, Any],
        threat_info: dict[str, Any],
    ) -> dict[str, Any]:
        """Build the OCSF finding_info object."""
        threat_id = data.get("id")
        threat_name = threat_info.get("threatName", "Unknown Threat")

        finding: dict[str, Any] = {
            "uid": str(threat_id) if threat_id else "",
            "title": threat_name,
        }

        # Analytic (the detection engine)
        analytic: dict[str, Any] = {
            "name": "SentinelOne Threat Detection",
            "type_id": 1,
            "type": "Rule",
        }
        engine = threat_info.get("engines", [])
        if engine and isinstance(engine, list):
            analytic["name"] = f"SentinelOne {', '.join(engine)}"
        finding["analytic"] = analytic

        # Description from classification + confidence
        classification = threat_info.get("classification", "")
        confidence = threat_info.get("confidenceLevel", "")
        desc_parts = []
        if classification:
            desc_parts.append(f"Classification: {classification}")
        if confidence:
            desc_parts.append(f"Confidence: {confidence}")
        if desc_parts:
            finding["desc"] = ". ".join(desc_parts)

        # Types from classification
        if classification:
            mapped_type = CLASSIFICATION_TO_TYPES.get(classification, classification)
            finding["types"] = [mapped_type]
        else:
            finding["types"] = []

        # Created time
        created_at = threat_info.get("createdAt")
        if created_at:
            finding["created_time_dt"] = created_at

        # MITRE ATT&CK from indicators
        attacks = self._build_attacks(data)
        if attacks:
            finding["attacks"] = attacks

        return finding

    @staticmethod
    def _build_attacks(data: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract MITRE ATT&CK from SentinelOne indicators array."""
        indicators = data.get("indicators", [])
        if not indicators or not isinstance(indicators, list):
            return []

        attacks: list[dict[str, Any]] = []
        seen: set[str] = set()

        for indicator in indicators:
            if not isinstance(indicator, dict):
                continue

            tactics = indicator.get("tactics", [])
            techniques = indicator.get("techniques", [])

            if not isinstance(tactics, list):
                tactics = []
            if not isinstance(techniques, list):
                techniques = []

            tactic_obj = _build_tactic_from_list(tactics)

            for technique in techniques:
                if not isinstance(technique, dict):
                    continue
                tech_id = technique.get("id") or technique.get("link", "")
                tech_name = technique.get("name", "")

                dedup_key = f"{tech_id}:{tech_name}"
                if dedup_key in seen:
                    continue
                seen.add(dedup_key)

                entry: dict[str, Any] = {}
                if tactic_obj:
                    entry["tactic"] = tactic_obj

                tech_obj: dict[str, Any] = {}
                if tech_id:
                    tech_obj["uid"] = tech_id
                if tech_name:
                    tech_obj["name"] = tech_name
                if tech_obj:
                    entry["technique"] = tech_obj

                if entry:
                    attacks.append(entry)

        return attacks

    @staticmethod
    def _build_device(agent_info: dict[str, Any], ocsf: dict[str, Any]) -> None:
        """Build OCSF device from SentinelOne agent fields."""
        hostname = agent_info.get("agentComputerName")
        os_name = agent_info.get("agentOsName")
        network_interfaces = agent_info.get("networkInterfaces", [])

        if not hostname and not os_name and not network_interfaces:
            return

        device: dict[str, Any] = {"type_id": 0}

        if hostname:
            device["hostname"] = hostname

        # Extract first IP from network interfaces
        if network_interfaces and isinstance(network_interfaces, list):
            for iface in network_interfaces:
                if isinstance(iface, dict):
                    inet_addrs = iface.get("inet", [])
                    if isinstance(inet_addrs, list) and inet_addrs:
                        device["ip"] = inet_addrs[0]
                        break
                    if isinstance(inet_addrs, str) and inet_addrs:
                        device["ip"] = inet_addrs
                        break

        if os_name:
            device["os"] = {"name": os_name}

        ocsf["device"] = device

    @staticmethod
    def _build_actor(threat_info: dict[str, Any], ocsf: dict[str, Any]) -> None:
        """Build OCSF actor from SentinelOne threat fields."""
        process_user = threat_info.get("processUser")

        if not process_user:
            return

        user: dict[str, Any] = {"name": process_user}
        ocsf["actor"] = {"user": user}

    @staticmethod
    def _build_observables(data: dict[str, Any], ocsf: dict[str, Any]) -> None:
        """Build OCSF observables from SentinelOne threat fields.

        Only public IPs, hashes go into observables. Private IPs go into
        device or evidences, NOT observables.
        """
        threat_info = data.get("threatInfo", {})
        agent_info = data.get("agentRealtimeInfo", {})
        observables: list[dict[str, Any]] = []
        seen_values: set[str] = set()

        def _add_observable(
            value: str, type_id: int, type_name: str, name: str
        ) -> None:
            if not value or value in seen_values:
                return
            seen_values.add(value)
            observables.append(
                {
                    "type_id": type_id,
                    "type": type_name,
                    "value": value,
                    "name": name,
                }
            )

        # File hashes
        sha256 = threat_info.get("sha256")
        if sha256 and isinstance(sha256, str):
            _add_observable(sha256, 8, "Hash", "file.hashes")

        md5 = threat_info.get("md5")
        if md5 and isinstance(md5, str):
            _add_observable(md5, 8, "Hash", "file.hashes")

        sha1 = threat_info.get("sha1")
        if sha1 and isinstance(sha1, str):
            _add_observable(sha1, 8, "Hash", "file.hashes")

        # Public IPs from network interfaces
        network_interfaces = agent_info.get("networkInterfaces", [])
        if isinstance(network_interfaces, list):
            for iface in network_interfaces:
                if isinstance(iface, dict):
                    for ip_val in iface.get("inet", []):
                        if isinstance(ip_val, str) and is_public_ip(ip_val):
                            _add_observable(ip_val, 2, "IP Address", "device.ip")

        if observables:
            ocsf["observables"] = observables

    @staticmethod
    def _build_evidences(threat_info: dict[str, Any], ocsf: dict[str, Any]) -> None:
        """Build OCSF evidences from SentinelOne threat fields."""
        evidence: dict[str, Any] = {}

        # File evidence
        file_name = threat_info.get("fileName")
        file_path = threat_info.get("filePath")
        sha256 = threat_info.get("sha256")
        md5 = threat_info.get("md5")
        sha1 = threat_info.get("sha1")

        if file_name or file_path or sha256 or md5 or sha1:
            file_obj: dict[str, Any] = {}
            if file_name:
                file_obj["name"] = file_name
            if file_path:
                file_obj["path"] = file_path
            hashes: list[dict[str, str]] = []
            if sha256:
                hashes.append({"algorithm": "SHA-256", "value": sha256})
            if md5:
                hashes.append({"algorithm": "MD5", "value": md5})
            if sha1:
                hashes.append({"algorithm": "SHA-1", "value": sha1})
            if hashes:
                file_obj["hashes"] = hashes
            evidence["file"] = file_obj

        # Process evidence
        originator = threat_info.get("originatorProcess")
        originator_pid = threat_info.get("originatorProcessPid")
        if originator or originator_pid is not None:
            process_obj: dict[str, Any] = {}
            if originator:
                process_obj["name"] = originator
            if originator_pid is not None:
                process_obj["pid"] = originator_pid
            evidence["process"] = process_obj

        if evidence:
            ocsf["evidences"] = [evidence]

    @staticmethod
    def _collect_unmapped(data: dict[str, Any]) -> dict[str, Any]:
        """Collect SentinelOne-specific fields not mapped to OCSF."""
        unmapped: dict[str, Any] = {}
        threat_info = data.get("threatInfo", {})
        agent_info = data.get("agentRealtimeInfo", {})

        # SentinelOne-specific threat metadata
        mitigation_status = threat_info.get("mitigationStatus")
        if mitigation_status:
            unmapped["mitigation_status"] = mitigation_status

        analyst_verdict = threat_info.get("analystVerdict")
        if analyst_verdict:
            unmapped["analyst_verdict"] = analyst_verdict

        # Agent version and machine type
        agent_version = agent_info.get("agentVersion")
        if agent_version:
            unmapped["agent_version"] = agent_version

        agent_machine_type = agent_info.get("agentMachineType")
        if agent_machine_type:
            unmapped["agent_machine_type"] = agent_machine_type

        # Account/site context
        account_name = agent_info.get("accountName")
        if account_name:
            unmapped["account_name"] = account_name

        site_name = agent_info.get("siteName")
        if site_name:
            unmapped["site_name"] = site_name

        return unmapped
