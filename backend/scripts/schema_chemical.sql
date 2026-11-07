-- Schema ghi cho module giám sát hóa chất & soát tài liệu.
-- Chạy bằng tài khoản migration, không chạy qua ERP_DATABASE_URL chỉ đọc.
-- SQL Server 2016+; GO cần được tách batch bởi công cụ chạy SQL.

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

IF SCHEMA_ID(N'chem') IS NULL
    EXEC(N'CREATE SCHEMA chem AUTHORIZATION dbo');
GO

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

-- =========================================================================
-- 1. SÁU BẢNG LÕI (DANH MỤC, LÔ NHẬP & DỮ LIỆU ĐO THEO THỜI GIAN)
-- =========================================================================

CREATE TABLE chem.Rooms (
    TenantId int NOT NULL CHECK (TenantId > 0),
    RoomId int IDENTITY(1,1) NOT NULL,
    RoomCode varchar(32) NOT NULL,
    RoomName nvarchar(200) NULL,
    IsActive bit NOT NULL CONSTRAINT DF_ChemRooms_IsActive DEFAULT (1),
    CONSTRAINT PK_ChemRooms PRIMARY KEY (TenantId, RoomId),
    CONSTRAINT UQ_ChemRooms_Code UNIQUE (TenantId, RoomCode)
);

CREATE TABLE chem.Chemicals (
    TenantId int NOT NULL CHECK (TenantId > 0),
    ChemicalId int IDENTITY(1,1) NOT NULL,
    ChemicalCode varchar(32) NOT NULL,
    ChemicalName nvarchar(250) NULL,
    CASNumber varchar(32) NULL,
    IsActive bit NOT NULL CONSTRAINT DF_Chemicals_IsActive DEFAULT (1),
    CONSTRAINT PK_Chemicals PRIMARY KEY (TenantId, ChemicalId),
    CONSTRAINT UQ_Chemicals_Code UNIQUE (TenantId, ChemicalCode)
);

CREATE TABLE chem.RoomChemicals (
    TenantId int NOT NULL,
    RoomId int NOT NULL,
    ChemicalId int NOT NULL,
    IsActive bit NOT NULL CONSTRAINT DF_RoomChemicals_IsActive DEFAULT (1),
    CONSTRAINT PK_RoomChemicals PRIMARY KEY (TenantId, RoomId, ChemicalId),
    CONSTRAINT FK_RC_Room FOREIGN KEY (TenantId, RoomId)
        REFERENCES chem.Rooms (TenantId, RoomId),
    CONSTRAINT FK_RC_Chem FOREIGN KEY (TenantId, ChemicalId)
        REFERENCES chem.Chemicals (TenantId, ChemicalId)
);

CREATE TABLE chem.ImportBatches (
    TenantId int NOT NULL CHECK (TenantId > 0),
    BatchId bigint IDENTITY(1,1) NOT NULL,
    FileName nvarchar(260) NOT NULL,
    FileSha256 char(64) NOT NULL,
    Status varchar(16) NOT NULL CONSTRAINT DF_ChemImport_Status DEFAULT ('Pending'),
    StartedAt datetimeoffset(0) NOT NULL
        CONSTRAINT DF_ChemImport_StartedAt DEFAULT (TODATETIMEOFFSET(SYSUTCDATETIME(), '+00:00')),
    CompletedAt datetimeoffset(0) NULL,
    SourceRowCount int NOT NULL CONSTRAINT DF_ChemImport_SourceCount DEFAULT (0),
    InsertedRowCount int NOT NULL CONSTRAINT DF_ChemImport_InsertedCount DEFAULT (0),
    SkippedRowCount int NOT NULL CONSTRAINT DF_ChemImport_SkippedCount DEFAULT (0),
    RejectedRowCount int NOT NULL CONSTRAINT DF_ChemImport_RejectedCount DEFAULT (0),
    ErrorSummary nvarchar(2000) NULL,
    CONSTRAINT PK_ChemImportBatches PRIMARY KEY (TenantId, BatchId),
    CONSTRAINT UQ_ChemImport_Hash UNIQUE (TenantId, FileSha256),
    CONSTRAINT CK_ChemImport_Status CHECK (Status IN ('Pending','Processing','Completed','Failed')),
    CONSTRAINT CK_ChemImport_Counts CHECK (
        SourceRowCount >= 0 AND InsertedRowCount >= 0
        AND SkippedRowCount >= 0 AND RejectedRowCount >= 0
    )
);

CREATE TABLE chem.RoomMeasurements (
    TenantId int NOT NULL,
    RoomMeasurementId bigint IDENTITY(1,1) NOT NULL,
    RoomId int NOT NULL,
    MeasuredAt datetimeoffset(0) NOT NULL,
    TemperatureC decimal(7,2) NOT NULL,
    HumidityPct decimal(5,2) NOT NULL CHECK (HumidityPct BETWEEN 0 AND 100),
    TVOCPpb decimal(12,2) NOT NULL CHECK (TVOCPpb >= 0),
    BatchId bigint NOT NULL,
    CONSTRAINT PK_RoomMeasurements PRIMARY KEY (TenantId, RoomMeasurementId),
    CONSTRAINT UQ_RM_Time UNIQUE (TenantId, RoomId, MeasuredAt),
    CONSTRAINT UQ_RM_Room UNIQUE (TenantId, RoomMeasurementId, RoomId),
    CONSTRAINT FK_RM_Room FOREIGN KEY (TenantId, RoomId)
        REFERENCES chem.Rooms (TenantId, RoomId),
    CONSTRAINT FK_RM_Batch FOREIGN KEY (TenantId, BatchId)
        REFERENCES chem.ImportBatches (TenantId, BatchId)
);

CREATE TABLE chem.ChemicalMeasurements (
    TenantId int NOT NULL,
    ChemicalMeasurementId bigint IDENTITY(1,1) NOT NULL,
    RoomMeasurementId bigint NOT NULL,
    RoomId int NOT NULL,
    ChemicalId int NOT NULL,
    QuantityRecordedMl decimal(14,2) NOT NULL CHECK (QuantityRecordedMl >= 0),
    SourceAnomalyLabel tinyint NOT NULL CHECK (SourceAnomalyLabel IN (0,1)),
    BatchId bigint NOT NULL,
    SourceRowNumber int NOT NULL CHECK (SourceRowNumber >= 2),
    CONSTRAINT PK_ChemicalMeasurements PRIMARY KEY (TenantId, ChemicalMeasurementId),
    CONSTRAINT UQ_CM_Measurement UNIQUE (TenantId, RoomMeasurementId, ChemicalId),
    CONSTRAINT UQ_CM_Source UNIQUE (TenantId, BatchId, SourceRowNumber),
    CONSTRAINT FK_CM_RM FOREIGN KEY (TenantId, RoomMeasurementId, RoomId)
        REFERENCES chem.RoomMeasurements (TenantId, RoomMeasurementId, RoomId),
    CONSTRAINT FK_CM_RoomChemical FOREIGN KEY (TenantId, RoomId, ChemicalId)
        REFERENCES chem.RoomChemicals (TenantId, RoomId, ChemicalId),
    CONSTRAINT FK_CM_Batch FOREIGN KEY (TenantId, BatchId)
        REFERENCES chem.ImportBatches (TenantId, BatchId)
);

CREATE INDEX IX_RM_Time ON chem.RoomMeasurements (TenantId, MeasuredAt, RoomId)
    INCLUDE (TemperatureC, HumidityPct, TVOCPpb);
CREATE INDEX IX_CM_Chemical ON chem.ChemicalMeasurements
    (TenantId, ChemicalId, RoomMeasurementId)
    INCLUDE (RoomId, QuantityRecordedMl, SourceAnomalyLabel);
CREATE INDEX IX_CM_Anomaly ON chem.ChemicalMeasurements
    (TenantId, RoomMeasurementId, ChemicalId)
    INCLUDE (RoomId, QuantityRecordedMl)
    WHERE SourceAnomalyLabel = 1;
GO

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

-- =========================================================================
-- 2. BẢNG MỞ RỘNG: PHIÊN BẢN DỮ LIỆU, SOÁT TÀI LIỆU & PHÁT HIỆN BẤT THƯỜNG
-- =========================================================================

CREATE TABLE chem.DataVersions (
    TenantId int NOT NULL CHECK (TenantId > 0),
    DataVersionId bigint IDENTITY(1,1) NOT NULL,
    VersionCode varchar(64) NOT NULL,
    Status varchar(16) NOT NULL CONSTRAINT DF_ChemDV_Status DEFAULT ('Ready'),
    CreatedAt datetimeoffset(0) NOT NULL
        CONSTRAINT DF_ChemDV_CreatedAt DEFAULT (TODATETIMEOFFSET(SYSUTCDATETIME(), '+00:00')),
    CONSTRAINT PK_ChemDataVersions PRIMARY KEY (TenantId, DataVersionId),
    CONSTRAINT UQ_ChemDataVersions_Code UNIQUE (TenantId, VersionCode),
    CONSTRAINT CK_ChemDV_Status CHECK (Status IN ('Draft','Ready','Archived'))
);

CREATE TABLE chem.DataVersionBatches (
    TenantId int NOT NULL,
    DataVersionId bigint NOT NULL,
    BatchId bigint NOT NULL,
    CONSTRAINT PK_ChemDataVersionBatches PRIMARY KEY (TenantId, DataVersionId, BatchId),
    CONSTRAINT FK_DVB_Version FOREIGN KEY (TenantId, DataVersionId)
        REFERENCES chem.DataVersions (TenantId, DataVersionId),
    CONSTRAINT FK_DVB_Batch FOREIGN KEY (TenantId, BatchId)
        REFERENCES chem.ImportBatches (TenantId, BatchId)
);

CREATE TABLE chem.Reports (
    TenantId int NOT NULL CHECK (TenantId > 0),
    ReportId bigint IDENTITY(1,1) NOT NULL,
    FileName nvarchar(260) NOT NULL,
    FileSha256 char(64) NOT NULL,
    ReportDate datetimeoffset(0) NULL,
    DataPeriodFrom datetimeoffset(0) NULL,
    DataPeriodTo datetimeoffset(0) NULL,
    Status varchar(16) NOT NULL CONSTRAINT DF_ChemReports_Status DEFAULT ('Parsed'),
    CreatedAt datetimeoffset(0) NOT NULL
        CONSTRAINT DF_ChemReports_CreatedAt DEFAULT (TODATETIMEOFFSET(SYSUTCDATETIME(), '+00:00')),
    CONSTRAINT PK_ChemReports PRIMARY KEY (TenantId, ReportId),
    CONSTRAINT CK_ChemReports_Status CHECK (Status IN ('Pending','Parsed','Reviewed','Failed'))
);

CREATE TABLE chem.ReportRows (
    TenantId int NOT NULL,
    ReportRowId bigint IDENTITY(1,1) NOT NULL,
    ReportId bigint NOT NULL,
    ReportRowNumber int NOT NULL CHECK (ReportRowNumber >= 1),
    RoomCode varchar(32) NULL,
    ChemicalCode varchar(32) NULL,
    MeasuredAt datetimeoffset(0) NULL,
    Metric varchar(64) NOT NULL,
    Value decimal(18,4) NULL,
    Unit varchar(32) NULL,
    RawText nvarchar(1000) NULL,
    CONSTRAINT PK_ChemReportRows PRIMARY KEY (TenantId, ReportRowId),
    CONSTRAINT UQ_ChemReportRows_Line UNIQUE (TenantId, ReportId, ReportRowNumber, Metric),
    CONSTRAINT FK_RR_Report FOREIGN KEY (TenantId, ReportId)
        REFERENCES chem.Reports (TenantId, ReportId)
);

CREATE TABLE chem.AnalysisRuns (
    TenantId int NOT NULL CHECK (TenantId > 0),
    AnalysisRunId bigint IDENTITY(1,1) NOT NULL,
    DataVersionId bigint NULL,
    ReportId bigint NULL,
    RunType varchar(32) NOT NULL,
    MethodVersion nvarchar(100) NOT NULL CONSTRAINT DF_ChemAR_Method DEFAULT (N'v1.0'),
    ParametersJson nvarchar(max) NULL,
    SummaryJson nvarchar(max) NULL,
    Status varchar(16) NOT NULL CONSTRAINT DF_ChemAR_Status DEFAULT ('Completed'),
    StartedAt datetimeoffset(0) NOT NULL
        CONSTRAINT DF_ChemAR_StartedAt DEFAULT (TODATETIMEOFFSET(SYSUTCDATETIME(), '+00:00')),
    FinishedAt datetimeoffset(0) NULL,
    CONSTRAINT PK_ChemAnalysisRuns PRIMARY KEY (TenantId, AnalysisRunId),
    CONSTRAINT FK_AR_DataVersion FOREIGN KEY (TenantId, DataVersionId)
        REFERENCES chem.DataVersions (TenantId, DataVersionId),
    CONSTRAINT FK_AR_Report FOREIGN KEY (TenantId, ReportId)
        REFERENCES chem.Reports (TenantId, ReportId),
    CONSTRAINT CK_ChemAR_Status CHECK (Status IN ('Pending','Running','Completed','Failed'))
);

CREATE TABLE chem.ReconciliationResults (
    TenantId int NOT NULL,
    ResultId bigint IDENTITY(1,1) NOT NULL,
    AnalysisRunId bigint NOT NULL,
    ReportId bigint NOT NULL,
    ReportRowNumber int NULL,
    RoomCode varchar(32) NULL,
    ChemicalCode varchar(32) NULL,
    Metric varchar(64) NOT NULL,
    Status varchar(32) NOT NULL,
    ReportMeasuredAt datetimeoffset(0) NULL,
    DbMeasuredAt datetimeoffset(0) NULL,
    ReportValue decimal(18,4) NULL,
    DbValue decimal(18,4) NULL,
    ReportUnit varchar(32) NULL,
    DbUnit varchar(32) NULL,
    AbsDiff decimal(18,4) NULL,
    RelDiffPct decimal(12,4) NULL,
    EvidenceJson nvarchar(max) NULL,
    CreatedAt datetimeoffset(0) NOT NULL
        CONSTRAINT DF_ChemRec_CreatedAt DEFAULT (TODATETIMEOFFSET(SYSUTCDATETIME(), '+00:00')),
    CONSTRAINT PK_ChemReconciliationResults PRIMARY KEY (TenantId, ResultId),
    CONSTRAINT FK_Rec_Run FOREIGN KEY (TenantId, AnalysisRunId)
        REFERENCES chem.AnalysisRuns (TenantId, AnalysisRunId),
    CONSTRAINT FK_Rec_Report FOREIGN KEY (TenantId, ReportId)
        REFERENCES chem.Reports (TenantId, ReportId)
);

CREATE TABLE chem.MonitoringRuleVersions (
    TenantId int NOT NULL CHECK (TenantId > 0),
    RuleVersionId bigint IDENTITY(1,1) NOT NULL,
    RuleCode varchar(64) NOT NULL,
    VersionNo int NOT NULL CONSTRAINT DF_ChemRule_Version DEFAULT (1),
    RuleType varchar(32) NOT NULL,
    Metric varchar(64) NOT NULL,
    RoomCode varchar(32) NULL,
    ChemicalCode varchar(32) NULL,
    ParametersJson nvarchar(max) NOT NULL,
    Severity varchar(16) NOT NULL CONSTRAINT DF_ChemRule_Severity DEFAULT ('medium'),
    EffectiveFrom datetimeoffset(0) NOT NULL,
    EffectiveTo datetimeoffset(0) NULL,
    Status varchar(16) NOT NULL CONSTRAINT DF_ChemRule_Status DEFAULT ('Approved'),
    ApprovedBy nvarchar(100) NULL,
    CreatedAt datetimeoffset(0) NOT NULL
        CONSTRAINT DF_ChemRule_CreatedAt DEFAULT (TODATETIMEOFFSET(SYSUTCDATETIME(), '+00:00')),
    CONSTRAINT PK_ChemMonitoringRuleVersions PRIMARY KEY (TenantId, RuleVersionId),
    CONSTRAINT UQ_ChemRule_CodeVersion UNIQUE (TenantId, RuleCode, VersionNo)
);

CREATE TABLE chem.Findings (
    TenantId int NOT NULL,
    FindingId bigint IDENTITY(1,1) NOT NULL,
    AnalysisRunId bigint NOT NULL,
    RuleVersionId bigint NULL,
    RoomId int NULL,
    ChemicalId int NULL,
    ChemicalMeasurementId bigint NULL,
    FindingKey varchar(160) NOT NULL,
    Method varchar(64) NOT NULL,
    RuleVersion varchar(64) NOT NULL,
    Metric varchar(64) NOT NULL,
    ObservedValue decimal(18,4) NULL,
    BaselineValue decimal(18,4) NULL,
    Score decimal(10,6) NULL,
    Severity varchar(16) NOT NULL,
    WindowFrom datetimeoffset(0) NULL,
    WindowTo datetimeoffset(0) NULL,
    Explanation nvarchar(1000) NOT NULL,
    EvidenceJson nvarchar(max) NULL,
    CreatedAt datetimeoffset(0) NOT NULL
        CONSTRAINT DF_ChemFinding_CreatedAt DEFAULT (TODATETIMEOFFSET(SYSUTCDATETIME(), '+00:00')),
    CONSTRAINT PK_ChemFindings PRIMARY KEY (TenantId, FindingId),
    CONSTRAINT UQ_ChemFindings_Key UNIQUE (TenantId, AnalysisRunId, FindingKey),
    CONSTRAINT FK_Finding_Run FOREIGN KEY (TenantId, AnalysisRunId)
        REFERENCES chem.AnalysisRuns (TenantId, AnalysisRunId),
    CONSTRAINT FK_Finding_Rule FOREIGN KEY (TenantId, RuleVersionId)
        REFERENCES chem.MonitoringRuleVersions (TenantId, RuleVersionId)
);

CREATE TABLE chem.Alerts (
    TenantId int NOT NULL,
    AlertId bigint IDENTITY(1,1) NOT NULL,
    FindingId bigint NOT NULL,
    DedupKey varchar(160) NOT NULL,
    Severity varchar(16) NOT NULL,
    Status varchar(16) NOT NULL CONSTRAINT DF_ChemAlerts_Status DEFAULT ('Open'),
    AssignedTo nvarchar(100) NULL,
    CreatedAt datetimeoffset(0) NOT NULL
        CONSTRAINT DF_ChemAlerts_CreatedAt DEFAULT (TODATETIMEOFFSET(SYSUTCDATETIME(), '+00:00')),
    UpdatedAt datetimeoffset(0) NULL,
    CONSTRAINT PK_ChemAlerts PRIMARY KEY (TenantId, AlertId),
    CONSTRAINT UQ_ChemAlerts_Dedup UNIQUE (TenantId, DedupKey),
    CONSTRAINT FK_Alert_Finding FOREIGN KEY (TenantId, FindingId)
        REFERENCES chem.Findings (TenantId, FindingId),
    CONSTRAINT CK_ChemAlerts_Status CHECK (Status IN ('Open','Acknowledged','InReview','Closed','Dismissed'))
);

CREATE TABLE chem.AlertEvents (
    TenantId int NOT NULL,
    AlertEventId bigint IDENTITY(1,1) NOT NULL,
    AlertId bigint NOT NULL,
    EventType varchar(32) NOT NULL,
    ActorRef nvarchar(100) NULL,
    EventAt datetimeoffset(0) NOT NULL
        CONSTRAINT DF_ChemAlertEvents_EventAt DEFAULT (TODATETIMEOFFSET(SYSUTCDATETIME(), '+00:00')),
    Comment nvarchar(1000) NULL,
    CONSTRAINT PK_ChemAlertEvents PRIMARY KEY (TenantId, AlertEventId),
    CONSTRAINT FK_AlertEvent_Alert FOREIGN KEY (TenantId, AlertId)
        REFERENCES chem.Alerts (TenantId, AlertId)
);
GO
