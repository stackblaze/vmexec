from typing import Optional, List
from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    detail: str


class LoginRequest(BaseModel):
    username: str
    password: str
    mfa_code: Optional[str] = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class SessionLoginRequest(BaseModel):
    username: str
    password: str


class SessionLoginResponse(BaseModel):
    status: str  # ok | mfa_required | mfa_setup_required
    username: Optional[str] = None
    qr_code: Optional[str] = None
    secret: Optional[str] = None
    message: Optional[str] = None


class SessionMfaRequest(BaseModel):
    mfa_code: str


class MfaSetupRequest(BaseModel):
    secret: str
    mfa_code: str


class MfaSetupStartResponse(BaseModel):
    qr_code: str
    secret: str


class ApiKeyCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    username: Optional[str] = None
    password: Optional[str] = None
    mfa_code: Optional[str] = None


class ApiKeyCreateResponse(BaseModel):
    id: int
    name: str
    key: str
    message: str = "Store this key securely; it will not be shown again."


class ApiKeyInfo(BaseModel):
    id: int
    name: str
    created_at: str
    last_used_at: Optional[str] = None


class StorageConfigUpdate(BaseModel):
    storage_type: Optional[str] = None
    nfs_path: Optional[str] = None
    smb_unc_path: Optional[str] = None
    smb_user: Optional[str] = None
    smb_password: Optional[str] = None
    s3_endpoint: Optional[str] = None
    s3_access_key: Optional[str] = None
    s3_secret_key: Optional[str] = None
    s3_bucket: Optional[str] = None
    s3_region: Optional[str] = None
    perf_parallel_threads: Optional[int] = None
    perf_compression_level: Optional[int] = None
    backup_timeout_mins: Optional[int] = None
    max_global_backups: Optional[int] = None
    max_backups_per_host: Optional[int] = None
    max_schedules_per_hour: Optional[int] = None
    datastore_min_free_pct: Optional[int] = None
    datastore_headroom_gb: Optional[int] = None
    datastore_est_multiplier: Optional[float] = None
    backup_transport: Optional[str] = None
    repo_min_free_gb: Optional[int] = None
    exclude_infra_vms: Optional[bool] = None
    vddk_libdir: Optional[str] = None
    cbt_enabled: Optional[bool] = None
    cbt_full_interval: Optional[int] = None
    exclude_disk_patterns: Optional[str] = None
    retention_mode: Optional[str] = None
    gfs_daily_keep: Optional[int] = None
    gfs_weekly_keep: Optional[int] = None
    gfs_monthly_keep: Optional[int] = None
    secondary_copy_enabled: Optional[bool] = None
    secondary_storage_type: Optional[str] = None
    secondary_nfs_path: Optional[str] = None
    secondary_smb_unc_path: Optional[str] = None
    secondary_smb_user: Optional[str] = None
    secondary_smb_password: Optional[str] = None
    secondary_s3_endpoint: Optional[str] = None
    secondary_s3_access_key: Optional[str] = None
    secondary_s3_secret_key: Optional[str] = None
    secondary_s3_bucket: Optional[str] = None
    secondary_s3_region: Optional[str] = None


class ConfigResponse(BaseModel):
    storage_type: str
    nfs_path: str
    smb_unc_path: str
    smb_user: str
    s3_endpoint: str
    s3_bucket: str
    s3_region: str
    perf_parallel_threads: int
    perf_compression_level: int
    backup_timeout_mins: int
    max_global_backups: int
    max_backups_per_host: int
    max_schedules_per_hour: int = 2
    datastore_min_free_pct: int
    datastore_headroom_gb: int
    datastore_est_multiplier: float
    backup_transport: str
    repo_min_free_gb: int
    exclude_infra_vms: bool
    vddk_libdir: str
    cbt_enabled: bool = True
    cbt_full_interval: int = 7
    exclude_disk_patterns: str = "fcd/"
    retention_mode: str = "count"
    gfs_daily_keep: int = 7
    gfs_weekly_keep: int = 4
    gfs_monthly_keep: int = 6
    secondary_copy_enabled: bool = False
    secondary_storage_type: str = "NFS"
    secondary_nfs_path: str = ""
    secondary_smb_unc_path: str = ""
    secondary_smb_user: str = ""
    secondary_s3_endpoint: str = ""
    secondary_s3_bucket: str = ""
    secondary_s3_region: str = "us-east-1"
    smtp_server: str
    smtp_port: int
    smtp_user: str
    smtp_to_email: str
    smtp_use_tls: bool
    smtp_use_ssl: bool
    imap_server: str
    imap_port: int
    imap_user: str
    imap_use_ssl: bool


class ConfigUpdate(BaseModel):
    storage_type: Optional[str] = None
    nfs_path: Optional[str] = None
    smb_unc_path: Optional[str] = None
    smb_user: Optional[str] = None
    smb_password: Optional[str] = None
    s3_endpoint: Optional[str] = None
    s3_access_key: Optional[str] = None
    s3_secret_key: Optional[str] = None
    s3_bucket: Optional[str] = None
    s3_region: Optional[str] = None
    perf_parallel_threads: Optional[int] = None
    perf_compression_level: Optional[int] = None
    backup_timeout_mins: Optional[int] = None
    max_global_backups: Optional[int] = None
    max_backups_per_host: Optional[int] = None
    max_schedules_per_hour: Optional[int] = None
    datastore_min_free_pct: Optional[int] = None
    datastore_headroom_gb: Optional[int] = None
    datastore_est_multiplier: Optional[float] = None
    backup_transport: Optional[str] = None
    repo_min_free_gb: Optional[int] = None
    exclude_infra_vms: Optional[bool] = None
    vddk_libdir: Optional[str] = None
    cbt_enabled: Optional[bool] = None
    cbt_full_interval: Optional[int] = None
    exclude_disk_patterns: Optional[str] = None
    smtp_server: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_to_email: Optional[str] = None
    smtp_use_tls: Optional[bool] = None
    smtp_use_ssl: Optional[bool] = None
    imap_server: Optional[str] = None
    imap_port: Optional[int] = None
    imap_user: Optional[str] = None
    imap_password: Optional[str] = None
    imap_use_ssl: Optional[bool] = None


class TestResult(BaseModel):
    ok: bool
    message: str


class ESXiHostCreate(BaseModel):
    name: str
    host_ip: str
    username: str
    password: str
    connection_type: Optional[str] = "auto"  # auto | standalone | vcenter


class ESXiHostResponse(BaseModel):
    id: int
    name: str
    host_ip: str
    username: str
    connection_type: str = "auto"
    connection_label: str = "Auto-detect"
    vddk_installed: Optional[bool] = None
    vddk_message: Optional[str] = None


class VmUpdate(BaseModel):
    is_selected: Optional[bool] = None
    schedule_hour: Optional[int] = None
    schedule_minute: Optional[int] = None
    retention_count: Optional[int] = None
    is_job_active: Optional[bool] = None
    power_off_for_backup: Optional[bool] = None
    cbt_enabled: Optional[bool] = None
    schedule_frequency: Optional[str] = None
    schedule_days: Optional[str] = None
    interval_hours: Optional[int] = None


class InventorySelectionItem(BaseModel):
    vm_id: int
    is_selected: bool


class InventoryApplyRequest(BaseModel):
    updates: List[InventorySelectionItem] = []
    restagger: bool = False
    # Anchor for the staggered spread; defaults preserved server-side.
    base_hour: Optional[int] = None
    base_minute: Optional[int] = None
    # Gap between staggered jobs; server clamps to 5-180 minutes.
    interval_minutes: Optional[int] = None
    # Evaluate the proposed selection's capacity projection without applying.
    dry_run: bool = False


class VmResponse(BaseModel):
    id: int
    vm_name: str
    esxi_host_id: Optional[int]
    is_selected: bool
    cpu_count: int
    memory_mb: int
    storage_gb: float
    schedule_hour: int
    schedule_minute: int
    retention_count: int
    is_job_active: bool
    schedule_frequency: str
    schedule_days: str
    interval_hours: int = 0
    last_backup: Optional[str]
    last_backup_duration: int = 0
    last_status: str
    progress: int
    current_action: str
    power_state: str
    power_off_for_backup: bool
    cbt_enabled: bool = True
    host_name: str = ""
    last_secondary_copy_status: str = "none"
    last_backup_message: Optional[str] = None


class SyncResult(BaseModel):
    synced_new: List[str]
    total_on_host: int


class UserResponse(BaseModel):
    id: int
    username: str
    role: str
    email: str
    is_mfa_enabled: bool
    notify_subscriptions: str = ""
    created_at: Optional[str] = None


class UserCreateRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    role: str = Field(default="operator", pattern="^(admin|operator|viewer)$")


class UserCreateResponse(BaseModel):
    user: UserResponse
    temporary_password: str
    message: str = "Temporary password shown once. User must set up MFA on first login."


class UserRoleUpdate(BaseModel):
    role: str = Field(..., pattern="^(admin|operator|viewer)$")


class PasswordResetResponse(BaseModel):
    username: str
    temporary_password: str
    message: str = "Temporary password shown once."


class ProfileUpdate(BaseModel):
    email: Optional[str] = None
    notify_subscriptions: Optional[str] = None


class BootstrapResponse(BaseModel):
    user: UserResponse
    setup_wizard_suggested: bool
    notify_events: List[tuple]


class BackupLogEntry(BaseModel):
    id: int
    vm_name: str
    timestamp: Optional[str]
    status: str
    message: str


class SystemLogsResponse(BaseModel):
    service_log: str
    worker_log: str


class RestoreCreateRequest(BaseModel):
    target_esxi_id: int
    source_ova: str
    target_name: str
    datastore: str


class RestoreResponse(BaseModel):
    id: int
    target_name: str
    target_esxi_host: str
    datastore: str
    source_path: str
    status: str
    progress: int
    current_action: str
    is_cancelled: bool
    start_time: Optional[str]
    end_time: Optional[str]
    duration_seconds: Optional[int] = None
    error_message: Optional[str]


class OverviewStorage(BaseModel):
    type: str
    path: str
    total_bytes: Optional[int] = None
    total_human: str = "—"
    version_count: int = 0
    vm_count: int = 0
    disk_total_gb: Optional[float] = None
    disk_used_gb: Optional[float] = None
    disk_free_gb: Optional[float] = None
    disk_free_pct: Optional[float] = None
    scan_error: Optional[str] = None
    # Projected steady-state usage of all configured jobs (see services/capacity.py)
    projected_gb: Optional[float] = None
    projected_pct: Optional[float] = None
    projection_warn: Optional[bool] = None


class OverviewLiveJob(BaseModel):
    vm_id: int
    vm_name: str
    host_name: str
    progress: int
    current_action: str
    speed_mbps: float


class OverviewAttentionItem(BaseModel):
    vm_id: int
    vm_name: str
    host_name: str
    reason: str
    severity: str  # error | warning | info
    last_status: str
    last_backup: Optional[str] = None
    message: Optional[str] = None


class OverviewResponse(BaseModel):
    # False = at least one host registered but the VDDK library is absent, so
    # scheduled jobs will fail; the Overview page surfaces this as a banner.
    vddk_installed: Optional[bool] = None
    protected_count: int
    scheduled_count: int
    running_count: int
    host_count: int
    host_label: str = "Registered hosts"
    inventory_count: int
    status_counts: dict
    log_stats_7d: dict
    success_rate_7d: Optional[float] = None
    storage: OverviewStorage
    worker_online: bool
    worker_last_seen_seconds: Optional[int] = None
    max_global_backups: int
    live_jobs: List[OverviewLiveJob]
    recent_activity: List[BackupLogEntry]
    active_restores: List[RestoreResponse]
    attention: List[OverviewAttentionItem]
    setup_incomplete: bool


class K8sClusterCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    kubeconfig: str
    targets: list = []  # [{name, profile, namespace, selector, ...}]


class K8sClusterUpdate(BaseModel):
    name: Optional[str] = None
    kubeconfig: Optional[str] = None
    targets: Optional[list] = None
    schedule_hour: Optional[int] = None
    schedule_minute: Optional[int] = None
    schedule_frequency: Optional[str] = None
    interval_hours: Optional[int] = None
    retention_count: Optional[int] = None
    is_job_active: Optional[bool] = None


class K8sClusterResponse(BaseModel):
    id: int
    name: str
    targets: list
    schedule_hour: int
    schedule_minute: int
    schedule_frequency: str
    interval_hours: int
    retention_count: int
    is_job_active: bool
    last_backup: Optional[str] = None
    last_status: str = "Never"
    current_action: str = ""


class K3sS3Config(BaseModel):
    endpoint: str
    access_key: str
    secret_key: str
    bucket: str
    folder: Optional[str] = "etcd"
    region: Optional[str] = "us-east-1"
    schedule_cron: Optional[str] = "0 */6 * * *"
    local_retention: Optional[int] = 10
    s3_retention: Optional[int] = 28
