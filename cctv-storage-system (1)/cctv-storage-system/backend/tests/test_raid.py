from backend.engines import raid_engine as r


def test_raid6_6x4():
    c = r.calculate("RAID6", 6, 4)
    assert c["usable_tb"] == 16 and c["fault_tolerance"] == 2 and abs(c["efficiency"] - 2 / 3) < 1e-9


def test_raid5_min_disks_rejected():
    assert not r.calculate("RAID5", 2, 4)["valid"]


def test_raid10_odd_rejected():
    assert not r.calculate("RAID10", 5, 4)["valid"]
    c = r.calculate("RAID10", 6, 4)
    assert c["usable_tb"] == 12 and c["efficiency"] == 0.5


def test_raid1_and_raid0():
    assert r.calculate("RAID1", 2, 8)["usable_tb"] == 8
    assert r.calculate("RAID0", 4, 4)["fault_tolerance"] == 0


def test_disks_needed():
    assert r.disks_needed("RAID6", 20, 4) == 7
    assert r.disks_needed("RAID5", 20, 4) == 6
    assert r.disks_needed("RAID10", 20, 4) == 10
    assert r.disks_needed("RAID1", 20, 4) is None


def test_status():
    assert r.array_status("RAID5", 6, 1) == "Degraded"
    assert r.array_status("RAID5", 6, 2) == "Failed"
    assert r.array_status("RAID6", 7, 2) == "Degraded"
    assert r.array_status("RAID6", 7, 3) == "Failed"
    assert r.array_status("RAID0", 4, 1) == "Failed"


def test_recommender():
    assert r.recommend(20, 4, "High availability + fault tolerance")["level"] == "RAID6"
    assert r.recommend(20, 4, "High availability + fault tolerance", True, True)["level"] == "RAID10"
    assert r.recommend(20, 4, "Lowest cost")["level"] == "RAID5"
    assert r.recommend(20, 10, "Lowest cost")["level"] == "RAID6"
    rec = r.recommend(20, 4, "Balanced")
    assert rec["calc"]["usable_tb"] >= 20
