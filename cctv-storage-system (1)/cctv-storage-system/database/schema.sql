-- ICSLOS schema (PostgreSQL 13+)
CREATE TABLE roles (
  role_id SERIAL PRIMARY KEY,
  role_name VARCHAR(30) UNIQUE NOT NULL
);

CREATE TABLE users (
  user_id SERIAL PRIMARY KEY,
  username VARCHAR(50) UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  role_id INT NOT NULL REFERENCES roles(role_id),
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  failed_attempts INT NOT NULL DEFAULT 0,
  locked_until TIMESTAMP,
  created_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE storage_pools (
  pool_id SERIAL PRIMARY KEY,
  name VARCHAR(80) NOT NULL,
  total_capacity_tb NUMERIC(10,2) NOT NULL CHECK (total_capacity_tb > 0)
);

CREATE TABLE storage_tiers (
  tier_id SERIAL PRIMARY KEY,
  pool_id INT NOT NULL REFERENCES storage_pools(pool_id) ON DELETE CASCADE,
  tier_name VARCHAR(10) NOT NULL CHECK (tier_name IN ('Hot','Warm','Cold')),
  capacity_tb NUMERIC(10,2) NOT NULL CHECK (capacity_tb > 0),
  cost_per_tb_month NUMERIC(10,2) NOT NULL CHECK (cost_per_tb_month >= 0),
  access_speed VARCHAR(40),
  UNIQUE (pool_id, tier_name)
);

CREATE TABLE retention_policies (
  policy_id SERIAL PRIMARY KEY,
  name VARCHAR(60) UNIQUE NOT NULL,
  normal_days INT NOT NULL CHECK (normal_days > 0),
  important_days INT NOT NULL CHECK (important_days > 0),
  incident_days INT NOT NULL CHECK (incident_days > 0),
  critical_days INT NOT NULL CHECK (critical_days > 0)
);

CREATE TABLE cameras (
  camera_id SERIAL PRIMARY KEY,
  camera_code VARCHAR(10) UNIQUE NOT NULL,
  name VARCHAR(80) NOT NULL,
  location VARCHAR(80) NOT NULL,
  resolution VARCHAR(10) NOT NULL CHECK (resolution IN ('720p','1080p','4MP','4K')),
  fps INT NOT NULL CHECK (fps BETWEEN 1 AND 60),
  compression VARCHAR(10) NOT NULL CHECK (compression IN ('H.264','H.265','H.265+','MJPEG')),
  bitrate_mbps NUMERIC(7,2) NOT NULL CHECK (bitrate_mbps > 0),
  recording_mode VARCHAR(15) NOT NULL CHECK (recording_mode IN ('Continuous','Motion','Scheduled')),
  recording_hours NUMERIC(4,1) NOT NULL DEFAULT 24 CHECK (recording_hours > 0 AND recording_hours <= 24),
  priority VARCHAR(10) NOT NULL CHECK (priority IN ('Low','Medium','High','Critical')),
  retention_days INT NOT NULL CHECK (retention_days > 0),
  policy_id INT REFERENCES retention_policies(policy_id),
  status VARCHAR(10) NOT NULL DEFAULT 'Active' CHECK (status IN ('Active','Inactive')),
  default_tier_id INT REFERENCES storage_tiers(tier_id),
  created_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE footage (
  footage_id BIGSERIAL PRIMARY KEY,
  camera_id INT NOT NULL REFERENCES cameras(camera_id),
  start_time TIMESTAMP NOT NULL,
  end_time TIMESTAMP NOT NULL,
  size_gb NUMERIC(10,3) NOT NULL CHECK (size_gb >= 0),
  resolution VARCHAR(10) NOT NULL,
  compression VARCHAR(10) NOT NULL,
  tier_id INT NOT NULL REFERENCES storage_tiers(tier_id),
  importance VARCHAR(20) NOT NULL DEFAULT 'Normal'
     CHECK (importance IN ('Normal','Important','Incident','Critical Evidence')),
  retention_expiry TIMESTAMP NOT NULL,
  archive_status VARCHAR(12) NOT NULL DEFAULT 'Active' CHECK (archive_status IN ('Active','Archived')),
  deletion_status VARCHAR(20) NOT NULL DEFAULT 'Retained' CHECK (deletion_status IN ('Retained','Marked','Deleted')),
  created_at TIMESTAMP NOT NULL DEFAULT now(),
  CHECK (end_time > start_time)
);
CREATE INDEX idx_footage_cam_time ON footage(camera_id, start_time);
CREATE INDEX idx_footage_tier ON footage(tier_id);
CREATE INDEX idx_footage_expiry ON footage(retention_expiry);
CREATE INDEX idx_footage_importance ON footage(importance);
CREATE INDEX idx_footage_delstatus ON footage(deletion_status);

CREATE TABLE incidents (
  incident_id SERIAL PRIMARY KEY,
  footage_id BIGINT UNIQUE NOT NULL REFERENCES footage(footage_id),
  severity VARCHAR(20) NOT NULL,
  description TEXT,
  flagged_by INT REFERENCES users(user_id),
  flagged_at TIMESTAMP NOT NULL DEFAULT now(),
  legal_hold BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE raid_configurations (
  raid_id SERIAL PRIMARY KEY,
  pool_id INT NOT NULL REFERENCES storage_pools(pool_id),
  raid_level VARCHAR(8) NOT NULL CHECK (raid_level IN ('RAID0','RAID1','RAID5','RAID6','RAID10')),
  disk_count INT NOT NULL CHECK (disk_count >= 2),
  disk_size_tb NUMERIC(6,2) NOT NULL CHECK (disk_size_tb > 0),
  failed_disks INT NOT NULL DEFAULT 0 CHECK (failed_disks >= 0),
  status VARCHAR(12) NOT NULL DEFAULT 'Healthy' CHECK (status IN ('Healthy','Degraded','Failed','Rebuilding'))
);

CREATE TABLE backups (
  backup_id SERIAL PRIMARY KEY,
  pool_id INT NOT NULL REFERENCES storage_pools(pool_id),
  backup_type VARCHAR(12) NOT NULL CHECK (backup_type IN ('Full','Incremental')),
  started_at TIMESTAMP NOT NULL,
  finished_at TIMESTAMP,
  size_gb NUMERIC(12,2) NOT NULL DEFAULT 0,
  destination VARCHAR(80) NOT NULL,
  status VARCHAR(10) NOT NULL CHECK (status IN ('Success','Failed','Running')),
  recovery_status VARCHAR(80) NOT NULL DEFAULT 'Not tested'
);
CREATE INDEX idx_backups_started ON backups(started_at);

CREATE TABLE alerts (
  alert_id SERIAL PRIMARY KEY,
  created_at TIMESTAMP NOT NULL,
  severity VARCHAR(10) NOT NULL CHECK (severity IN ('Info','Warning','High','Critical')),
  category VARCHAR(30) NOT NULL,
  description TEXT NOT NULL,
  recommended_action TEXT,
  status VARCHAR(10) NOT NULL DEFAULT 'Open' CHECK (status IN ('Open','Resolved')),
  dedup_key VARCHAR(80),
  resolved_by INT REFERENCES users(user_id),
  resolved_at TIMESTAMP
);
CREATE INDEX idx_alerts_status ON alerts(status, severity);
CREATE UNIQUE INDEX uq_alert_open_dedup ON alerts(dedup_key) WHERE status = 'Open';

CREATE TABLE storage_metrics (
  metric_id SERIAL PRIMARY KEY,
  pool_id INT NOT NULL REFERENCES storage_pools(pool_id),
  recorded_on DATE NOT NULL,
  used_gb NUMERIC(12,2) NOT NULL,
  hot_gb NUMERIC(12,2) NOT NULL DEFAULT 0,
  warm_gb NUMERIC(12,2) NOT NULL DEFAULT 0,
  cold_gb NUMERIC(12,2) NOT NULL DEFAULT 0,
  UNIQUE (pool_id, recorded_on)
);

CREATE TABLE lifecycle_decisions (
  decision_id BIGSERIAL PRIMARY KEY,
  footage_id BIGINT NOT NULL REFERENCES footage(footage_id),
  decided_at TIMESTAMP NOT NULL,
  from_tier VARCHAR(10),
  to_tier VARCHAR(10),
  action VARCHAR(30) NOT NULL,
  reason_text TEXT NOT NULL
);
CREATE INDEX idx_decisions_footage ON lifecycle_decisions(footage_id);

CREATE TABLE audit_logs (
  log_id BIGSERIAL PRIMARY KEY,
  user_id INT REFERENCES users(user_id),
  action VARCHAR(40) NOT NULL,
  description TEXT,
  created_at TIMESTAMP NOT NULL DEFAULT now()
);
CREATE INDEX idx_audit_time ON audit_logs(created_at);
CREATE INDEX idx_audit_user ON audit_logs(user_id);

CREATE TABLE system_settings (
  key VARCHAR(50) PRIMARY KEY,
  value TEXT NOT NULL
);

-- Defense in depth: the database itself refuses to hard-delete protected evidence,
-- even if application code has a bug.
CREATE OR REPLACE FUNCTION prevent_protected_delete() RETURNS trigger AS $$
BEGIN
  IF NEW.deletion_status = 'Deleted' AND OLD.deletion_status <> 'Deleted' THEN
    IF NEW.importance IN ('Incident','Critical Evidence')
       OR EXISTS (SELECT 1 FROM incidents i WHERE i.footage_id = NEW.footage_id AND i.legal_hold) THEN
      RAISE EXCEPTION 'Footage % is protected evidence and cannot be deleted', NEW.footage_id;
    END IF;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_protect_footage BEFORE UPDATE ON footage
FOR EACH ROW EXECUTE FUNCTION prevent_protected_delete();
