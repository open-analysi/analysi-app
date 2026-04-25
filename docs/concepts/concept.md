# Concept

Every alert in a SIEM/EDR is produced by a **detection rule** (e.g. Splunk's "Suspicious PowerShell Execution"). Analysi keys its investigation knowledge to the rule, not the individual alert — at most one agentic workflow per rule.

The first time a rule fires, Analysi has no workflow for it and synthesizes one autonomously: slow, token-heavy, multi-tool reasoning. The result is saved against the rule. Every subsequent alert from that same rule reuses the saved workflow — cheap and fast.

```mermaid
flowchart TB
    classDef known fill:#dcfce7,stroke:#15803d,color:#14532d
    classDef new fill:#fee2e2,stroke:#b91c1c,color:#7f1d1d
    classDef terminal fill:#e0e7ff,stroke:#4338ca,color:#312e81

    Alert([Alert arrives]):::terminal
    Q{Do we already know<br/>how to investigate it?}
    Run["Run agentic workflow<br/><b>cheap · fast</b>"]:::known
    Gen["Generate new agentic workflow<br/><b>slow · deep thinking · high tokens</b>"]:::new
    Disp([Disposition]):::terminal

    Alert --> Q
    Q -- yes --> Run
    Q -- no --> Gen --> Run
    Run --> Disp
```

At steady state, the system holds **one agentic workflow per detection rule that has ever fired** in the environment. As rule coverage grows, the rate of expensive synthesis trends toward zero — and the cost of investigating each new alert collapses to the price of replaying a saved workflow.
