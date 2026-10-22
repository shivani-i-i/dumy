# Demo script (about 12–15 minutes)

Preparation: `python -m database.init_db --reset --demo`, start the app, log in as **admin**.
Expected numbers for the 10 demo cameras: **≈ 222 GB/day**, 30-day-style retention need **≈ 9.7 TB**, recommended **≈ 12.7 TB**
(with 10 % overhead + 20 % headroom). The seeded pool is 20 TB (RAID 6, 7 × 4 TB).

| # | Do this | Say / point out |
|---|---|---|
| 1 | **Storage Calculator** → "From registered cameras" | Step-by-step formula: Mbps × 3600 ÷ 8 ÷ 1000 → GB/h → day → retention → overhead → headroom |
| 2 | **Compression analysis** tab | H.265 saves ≈ 45 % vs H.264 *under configurable assumptions*; nothing is re-encoded |
| 3 | **RAID Management → Recommender** (20 TB, 4 TB disks, "High availability") | RAID 6 → 7 disks; compare RAID 5/10; note the "not a backup" banner |
| 4 | **Settings → Simulation**: *Generate history* = 7 days | All footage lands in **Hot**; open **Footage** and filter Tier = Hot |
| 5 | **Dashboard** | KPI cards, tier donut, utilization graph |
| 6 | **Settings → Simulation**: advance **10 days**, *untick* "Auto-run lifecycle" | Hot tier fills (≈ 3.7 TB of 4 TB): shows *why* lifecycle management is needed; tier-capacity alert may appear |
| 7 | **Storage Tiers → Lifecycle engine** | Read the dry run: each row has a plain-English *Why*. Click **Apply** → footage moves to **Warm** |
| 8 | **Footage** → pick a C01 clip about 12 days old → classify **Incident** | Expiry changes from 30 d to **180 d**; clip detail shows the decision history |
| 9 | Advance **40 days**, lifecycle + auto-delete ticked | Old footage → **Cold** (Archive page); expired Normal clips deleted; the **incident clip survives** (Archive → Protected evidence) |
| 10 | Create pressure: **RAID → Change configuration** to RAID 6 with **5 disks** (12 TB), then *Cameras → Add* two 4K continuous cameras and advance 5 days (or shrink further) | Utilization rises past 85–90 % |
| 11 | **Alerts** | Critical/High alert with *recommended action*. **Storage Tiers → Optimization recommendations** shows ranked actions + savings. Apply the compression simulation, watch utilization fall |
| 12 | **Capacity Forecast** | "Reaches 80 % in ≈ X days", exhaustion date, R², and the retention-aware steady-state message |
| 13 | **Backup & Recovery**: Full → advance 30 h (hours) → RPO violated alert → Full again → *Simulate FAILED backup* → critical alert → *Simulate recovery* | RPO = data-loss window, RTO = restore time; edit targets in the Admin expander |
| 14 | **Audit Logs** | login, camera/retention changes, incident flag, archive/delete, backups, RAID, alert resolve |

Role demo (2 min): log in as **viewer** (only Footage + Archive; can *request* an incident) and as **manager**
(no Settings/Audit/camera editing; can run lifecycle and resolve alerts).
Tip: if utilization never reaches the thresholds, lower the RAID size further or raise camera retention.
