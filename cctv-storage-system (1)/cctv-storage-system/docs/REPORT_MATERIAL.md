# Report material

## Novelty (proposed vs existing)
| # | Proposed novelty | Existing / basic |
|---|---|---|
| 1 | Rule-based lifecycle engine placing each footage record by age, camera priority, importance and storage pressure, with admin-configurable thresholds | NVRs: one global retention + FIFO overwrite; calculators: sizing only |
| 2 | Priority- and incident-aware retention: Incident / Critical Evidence / legal hold are exempt from automatic deletion (also enforced by a DB trigger) | Age-only retention |
| 3 | Pressure-adaptive optimization: hot windows shrink as utilization crosses thresholds; ranked recommendations (compress, tier down, retention, add capacity) with estimated savings | Static "disk full" alarm |
| 4 | Explainable decisions: each move/deletion mark stores the rule and numbers that triggered it (`lifecycle_decisions`) | Opaque or log-only |
| 5 | Retention-aware capacity forecasting: linear trend + steady-state projection (Σ daily GB × retention + protected evidence), feeding alerts and RAID/capacity advice | Simple used/free display |

State clearly: the individual calculators are standard; the contribution is the integration and the explainable decision logic.
It is rule-based and statistical — **not AI/ML**.

## ISM concept mapping
| Feature | ISM concept |
|---|---|
| Storage calculator, bitrate model | Capacity planning, data-growth estimation |
| Overhead + headroom | Provisioning, over-provisioning |
| Compression analysis | Storage optimization / data reduction |
| RAID module, failure simulation | Redundancy, fault tolerance, degraded mode, rebuild |
| Hot/Warm/Cold | Tiered storage, cost–performance trade-off |
| Lifecycle engine, decision log | Information Lifecycle Management (ILM) |
| Retention classes, legal hold | Retention policy, compliance, evidence preservation |
| Cold archive | Archival storage vs backup |
| Full / incremental backup | Data protection |
| RPO / RTO | Business continuity, disaster recovery |
| Forecast + steady state | Capacity management, trend analysis |
| Dashboard, alerts | Storage monitoring, event management |
| Metadata search | Information indexing |
| bcrypt, RBAC, lockout, session timeout | Storage security, access control |
| Audit logs | Accountability, auditing |
| Storage pool | Storage virtualization (conceptual) |
| Cost per tier | Cost optimization, TCO |

## Viva questions (short answers)
1. **ILM?** Managing data from creation to deletion by value/age; our engine does Hot→Warm→Cold→delete with exceptions.
2. **Why RAID is not a backup?** It survives disk failure only; deletion, corruption, fire or ransomware hit all disks.
3. **RPO vs RTO?** RPO = tolerable data loss (age of newest backup); RTO = tolerable downtime (restore size ÷ speed).
4. **Derive 1.8 GB/h for 4 Mbps?** 4 × 3600 ÷ 8 = 1800 MB = 1.8 GB.
5. **Is it AI?** No: rules + least-squares line. Explainability is a feature.
6. **Why RAID 6 for big disks?** Long rebuilds make a second failure likely; dual parity survives it.
7. **Why does linear forecasting fail with retention?** Deletion makes usage plateau; we also compute steady state.
8. **Protecting evidence?** Class rules, never-auto-delete, Admin-only downgrade, DB trigger, audit log.
9. **Archive vs backup?** Archive moves rarely-used data to cheap storage (the only copy); backup is a separate recovery copy.
10. **Passwords?** bcrypt: salted, slow hash; lockout after 5 failures; session timeout.
11. **Why a simulation clock?** To show weeks of lifecycle behaviour in minutes.
12. **Scaling to real video?** Keep the metadata/engine; swap the storage backend for NAS/S3-class tiers.
13. **Thin vs thick provisioning / headroom?** Headroom is planned free space so the pool never runs at 100 %.
14. **What happens at 92 % utilization?** Critical alert, hot windows shrink, ranked recommendations appear.
