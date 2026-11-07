IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'AI_DataPartitions')
BEGIN
    CREATE TABLE dbo.AI_DataPartitions (
        Id INT IDENTITY(1,1) PRIMARY KEY,
        TenantId INT NOT NULL,
        PartitionType NVARCHAR(50) NOT NULL DEFAULT 'Personal',
        OwnerUserId INT NULL,
        WorkDepartmentId INT NULL,
        UserGroupId INT NULL,
        Status NVARCHAR(50) NOT NULL DEFAULT 'Active',
        IsActive BIT NOT NULL DEFAULT 1,
        IsDeleted BIT NOT NULL DEFAULT 0,
        CreationTime DATETIMEOFFSET NOT NULL DEFAULT SYSDATETIMEOFFSET(),
        CreatorUserId INT NULL
    );
    INSERT INTO dbo.AI_DataPartitions (TenantId, PartitionType, OwnerUserId, Status, IsActive, IsDeleted)
    VALUES (94, 'Personal', 407, 'Active', 1, 0);
END;

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'AI_KnowledgeDocuments')
BEGIN
    CREATE TABLE dbo.AI_KnowledgeDocuments (
        Id INT IDENTITY(1,1) PRIMARY KEY,
        TenantId INT NOT NULL,
        AiServerDocId NVARCHAR(200) NOT NULL,
        DocumentNumber NVARCHAR(200) NULL,
        PartitionId INT NOT NULL,
        FolderId INT NULL,
        FieldCode NVARCHAR(100) NULL,
        DocumentTypeCode NVARCHAR(100) NULL,
        SecurityLevelCode NVARCHAR(50) NULL,
        Title NVARCHAR(500) NOT NULL,
        FileName NVARCHAR(260) NULL,
        FileUrl NVARCHAR(1000) NULL,
        FileSizeBytes BIGINT NULL DEFAULT 0,
        FileHashSha256 NVARCHAR(128) NULL,
        HasTextLayer BIT NOT NULL DEFAULT 1,
        ProcessingStatus NVARCHAR(50) NOT NULL DEFAULT 'Extracted',
        QualityStatus NVARCHAR(50) NOT NULL DEFAULT 'Approved',
        VersionNo INT NOT NULL DEFAULT 1,
        LifecycleStatus NVARCHAR(50) NOT NULL DEFAULT 'Active',
        ApprovalStatus NVARCHAR(50) NOT NULL DEFAULT 'Published',
        IndexStatus NVARCHAR(50) NOT NULL DEFAULT 'Indexed',
        ChunkCount INT NOT NULL DEFAULT 0,
        IsDeleted BIT NOT NULL DEFAULT 0,
        CreationTime DATETIMEOFFSET NOT NULL DEFAULT SYSDATETIMEOFFSET(),
        CreatorUserId INT NULL,
        LastModificationTime DATETIMEOFFSET NULL,
        LastModifierUserId INT NULL
    );
END;

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'AI_PartitionPermissions')
BEGIN
    CREATE TABLE dbo.AI_PartitionPermissions (
        Id INT IDENTITY(1,1) PRIMARY KEY,
        TenantId INT NOT NULL,
        SubjectType NVARCHAR(50) NOT NULL DEFAULT 'User',
        UserId INT NULL,
        RoleId INT NULL,
        UserGroupId INT NULL,
        WorkDepartmentId INT NULL,
        PartitionId INT NULL,
        FolderId INT NULL,
        DocumentId INT NULL,
        FieldCode NVARCHAR(100) NULL,
        DocumentTypeCode NVARCHAR(100) NULL,
        MaxSecurityLevelCode NVARCHAR(50) NULL,
        PermissionLevel NVARCHAR(50) NOT NULL DEFAULT 'FullAccess',
        IsDeny BIT NOT NULL DEFAULT 0,
        IsDeleted BIT NOT NULL DEFAULT 0,
        CreationTime DATETIMEOFFSET NOT NULL DEFAULT SYSDATETIMEOFFSET(),
        CreatorUserId INT NULL
    );
END;
