# Enhanced API v2 - New Endpoints Documentation

## Overview

This document details all the new API endpoints implemented in the Enhanced API v2 system. These endpoints provide comprehensive system management, monitoring, analytics, and automation capabilities for the Barbossa Enhanced system.

**Base URL**: `/api/v2`
**Authentication**: HTTP Basic Auth required
**Content-Type**: `application/json`

---

## 📋 Table of Contents

1. [Backup and Restore](#backup-and-restore)
2. [Real-time Monitoring](#real-time-monitoring)
3. [Advanced Search](#advanced-search)
4. [Analytics and Reporting](#analytics-and-reporting)
5. [Database Management](#database-management)
6. [Integration Management](#integration-management)
7. [Performance Monitoring](#performance-monitoring)
8. [Enhanced Logs](#enhanced-logs)
9. [Configuration Management](#configuration-management)
10. [Notifications](#notifications)
11. [Service Management](#service-management)
12. [Metrics History](#metrics-history)
13. [Error Handling](#error-handling)
14. [Usage Examples](#usage-examples)

---

## 🔄 Backup and Restore

### Create Backup
**POST** `/backup/create`

Creates a comprehensive system backup with configurable options.

#### Request Body
```json
{
  "type": "full",           // "full", "config", "data"
  "include_logs": false,    // Include log files in backup
  "compression": "gzip"     // "gzip", "none"
}
```

#### Response
```json
{
  "backup": {
    "id": "uuid",
    "name": "barbossa_backup_full_20241201_120000",
    "type": "full",
    "created_at": "2024-12-01T12:00:00Z",
    "size": 1048576,
    "files": ["config/repository_whitelist.json", "..."],
    "status": "completed"
  },
  "status": "success",
  "message": "Backup created successfully"
}
```

### List Backups
**GET** `/backup/list`

Retrieves all available backups with metadata.

#### Response
```json
{
  "backups": [
    {
      "id": "uuid",
      "name": "backup_name",
      "type": "full",
      "created_at": "2024-12-01T12:00:00Z",
      "size": 1048576,
      "exists": true,
      "status": "completed"
    }
  ],
  "total": 5,
  "status": "success"
}
```

### Restore Backup
**POST** `/backup/{backup_id}/restore`

Restores system from a specific backup.

#### Request Body
```json
{
  "type": "config",     // "config", "data", "full"
  "force": false        // Overwrite existing files without backup
}
```

#### Response
```json
{
  "restored_files": ["config/repository_whitelist.json"],
  "total_files": 5,
  "restore_type": "config",
  "status": "success",
  "message": "Successfully restored 5 files from backup"
}
```

### Delete Backup
**DELETE** `/backup/{backup_id}/delete`

Permanently removes a backup and its associated files.

---

## 📊 Real-time Monitoring

### Real-time System Metrics
**GET** `/monitoring/realtime`

Provides comprehensive real-time system monitoring data.

#### Response
```json
{
  "metrics": {
    "timestamp": "2024-12-01T12:00:00Z",
    "system": {
      "uptime": 86400,
      "cpu": {
        "usage_percent": 45.2,
        "core_count": 8,
        "per_core": [12.5, 45.0, 67.8, 23.1],
        "frequency": {"current": 2400, "max": 3600, "min": 1200}
      },
      "memory": {
        "virtual": {"total": 16777216000, "used": 8388608000, "percent": 50.0},
        "swap": {"total": 4294967296, "used": 0, "percent": 0.0}
      },
      "network": {"bytes_sent": 1000000, "bytes_recv": 2000000},
      "disk_usage": [
        {
          "device": "/dev/sda1",
          "mountpoint": "/",
          "total": 1099511627776,
          "used": 549755813888,
          "free": 549755813888,
          "percent": 50.0
        }
      ]
    },
    "top_processes": [
      {
        "pid": 1234,
        "name": "barbossa",
        "cpu_percent": 15.5,
        "memory_percent": 8.2,
        "username": "barbossa"
      }
    ],
    "barbossa": {
      "active_processes": 3,
      "last_execution": "2024-12-01T11:30:00Z",
      "work_areas": {"infrastructure": 45, "personal_projects": 32}
    }
  },
  "status": "success"
}
```

### Alert Management
**GET** `/monitoring/alerts`

Retrieves system alerts and their current status.

#### Response
```json
{
  "alerts": [
    {
      "id": "uuid",
      "name": "High CPU Usage",
      "metric": "cpu",
      "threshold": 80,
      "severity": "high",
      "enabled": true,
      "created_at": "2024-12-01T10:00:00Z"
    }
  ],
  "active_alerts": [
    {
      "id": "uuid",
      "name": "High CPU Usage",
      "current_value": 85.5,
      "triggered_at": "2024-12-01T12:00:00Z"
    }
  ],
  "total_alerts": 5,
  "active_count": 1,
  "status": "success"
}
```

**POST** `/monitoring/alerts`

Creates a new alert threshold.

#### Request Body
```json
{
  "name": "High Memory Usage",
  "metric": "memory",           // "cpu", "memory", "disk", "load", "network"
  "threshold": 85,              // Threshold percentage
  "severity": "high",           // "low", "medium", "high", "critical"
  "enabled": true,
  "description": "Alert when memory usage exceeds 85%",
  "mountpoint": "/"             // For disk alerts only
}
```

---

## 🔍 Advanced Search

### Multi-Category Search
**GET** `/search`

Performs advanced search across projects, tasks, logs, and configuration files.

#### Query Parameters
- `q`: Search query (required)
- `category`: Search category (`all`, `projects`, `tasks`, `logs`, `config`)
- `limit`: Maximum results (default: 50)
- `include_content`: Include full content in results (`true`/`false`)

#### Example
```
GET /search?q=docker&category=all&limit=20&include_content=false
```

#### Response
```json
{
  "query": "docker",
  "category": "all",
  "results": {
    "projects": [
      {
        "id": "uuid",
        "name": "Docker Migration Project",
        "description": "Migrate services to Docker containers",
        "status": "active"
      }
    ],
    "tasks": [
      {
        "id": "uuid",
        "title": "Setup Docker Compose",
        "project_name": "Infrastructure"
      }
    ],
    "logs": [
      {
        "file": "barbossa_20241201.log",
        "line_number": 145,
        "preview": "Docker container started successfully..."
      }
    ],
    "config": [
      {
        "file": "docker-compose.yml",
        "path": "/home/user/project/docker-compose.yml",
        "matches": [
          {"line_number": 5, "content": "version: '3.8'"}
        ]
      }
    ]
  },
  "total_results": 15,
  "summary": {
    "projects": 1,
    "tasks": 5,
    "logs": 8,
    "config": 1
  },
  "status": "success"
}
```

---

## 📈 Analytics and Reporting

### Analytics Summary
**GET** `/analytics/summary`

Provides comprehensive analytics and insights across the system.

#### Query Parameters
- `period`: Time period for analysis (`7d`, `30d`, `90d`, `1y`)

#### Response
```json
{
  "analytics": {
    "period": "30d",
    "start_date": "2024-11-01T00:00:00Z",
    "end_date": "2024-12-01T00:00:00Z",
    "system": {
      "uptime_days": 45.5,
      "current_load": {
        "cpu_percent": 35.2,
        "memory_percent": 67.8,
        "disk_usage": [{"mountpoint": "/", "percent": 45.2}]
      },
      "process_count": 156
    },
    "projects": {
      "total": 25,
      "by_status": {"active": 15, "completed": 8, "archived": 2},
      "active_percentage": 60.0
    },
    "tasks": {
      "total": 120,
      "by_status": {"completed": 89, "in_progress": 15, "pending": 16},
      "completion_rate": 74.2,
      "active_tasks": 31
    },
    "barbossa": {
      "active_processes": 2,
      "last_execution": "2024-12-01T11:00:00Z",
      "recent_executions": 45
    },
    "security": {
      "total_violations": 3,
      "recent_violations": 0,
      "total_audits": 1250,
      "recent_audits": 156
    }
  },
  "generated_at": "2024-12-01T12:00:00Z",
  "status": "success"
}
```

---

## 🗄️ Database Management

### Database Statistics
**GET** `/database/stats`

Retrieves comprehensive database statistics and health information.

#### Response
```json
{
  "database_stats": {
    "databases": [
      {
        "name": "barbossa.db",
        "path": "/home/user/barbossa-engineer/data/barbossa.db",
        "size": 1048576,
        "modified": "2024-12-01T12:00:00Z",
        "tables": [
          {"name": "projects", "records": 25},
          {"name": "tasks", "records": 120}
        ],
        "total_records": 145
      }
    ],
    "total_size": 5242880,
    "total_tables": 8,
    "total_records": 2500
  },
  "status": "success"
}
```

### Database Optimization
**POST** `/database/optimize`

Optimizes database performance through various maintenance operations.

#### Request Body
```json
{
  "database": "all",                    // "all" or specific database name
  "operations": ["vacuum", "analyze"]   // "vacuum", "analyze", "reindex"
}
```

#### Response
```json
{
  "optimization_results": [
    {
      "database": "barbossa.db",
      "operations": [
        {
          "name": "vacuum",
          "duration": 2.5,
          "status": "completed"
        }
      ],
      "size_before": 1048576,
      "size_after": 524288,
      "space_saved": 524288
    }
  ],
  "total_space_saved": 524288,
  "status": "success",
  "message": "Database optimization completed. Saved 524288 bytes."
}
```

---

## 🔗 Integration Management

### Webhook Management
**GET** `/integration/webhooks`

Lists all configured webhook integrations.

#### Response
```json
{
  "webhooks": [
    {
      "id": "uuid",
      "name": "Slack Notifications",
      "url": "https://hooks.slack.com/services/...",
      "events": ["system.alert", "task.completed"],
      "enabled": true,
      "status": "healthy",
      "last_check": "2024-12-01T12:00:00Z",
      "total_calls": 45,
      "failed_calls": 2
    }
  ],
  "total": 3,
  "active": 2,
  "status": "success"
}
```

**POST** `/integration/webhooks`

Creates a new webhook integration.

#### Request Body
```json
{
  "name": "Discord Alerts",
  "url": "https://discord.com/api/webhooks/...",
  "events": ["system.alert", "backup.created"],
  "enabled": true,
  "secret": "optional_secret_key",
  "headers": {"Authorization": "Bearer token"},
  "retry_count": 3,
  "timeout": 30
}
```

### Integration Testing
**POST** `/integration/test`

Tests external integrations for connectivity and functionality.

#### Request Body
```json
{
  "type": "webhook",
  "url": "https://httpbin.org/post",
  "headers": {"Content-Type": "application/json"},
  "timeout": 30
}
```

#### Response
```json
{
  "test_result": {
    "url": "https://httpbin.org/post",
    "status_code": 200,
    "response_time": 0.45,
    "success": true,
    "response_headers": {"content-type": "application/json"},
    "response_body": "{\"success\": true}"
  },
  "status": "success"
}
```

---

## ⚡ Performance Monitoring

### Performance Profile
**GET** `/performance/profile`

Provides detailed system performance profiling data.

#### Response
```json
{
  "performance_profile": {
    "timestamp": "2024-12-01T12:00:00Z",
    "cpu": {
      "usage_percent": 45.2,
      "core_usage": [12.5, 67.8, 23.1, 45.0],
      "frequency": {"current": 2400, "max": 3600, "min": 1200},
      "load_average": [1.5, 1.2, 0.8],
      "context_switches": 125000,
      "interrupts": 89000
    },
    "memory": {
      "virtual": {"total": 16777216000, "used": 8388608000, "percent": 50.0},
      "swap": {"total": 4294967296, "used": 0, "percent": 0.0},
      "top_consumers": [
        {
          "pid": 1234,
          "name": "barbossa",
          "memory_rss": 104857600,
          "memory_vms": 209715200
        }
      ]
    },
    "disk": {
      "io_stats": {"read_bytes": 1000000, "write_bytes": 2000000},
      "usage_by_partition": [
        {
          "device": "/dev/sda1",
          "mountpoint": "/",
          "total": 1099511627776,
          "percent": 50.0
        }
      ]
    },
    "processes": {
      "total": 156,
      "top_cpu": [
        {"pid": 1234, "name": "barbossa", "cpu_percent": 15.5}
      ],
      "top_memory": [
        {"pid": 1234, "name": "barbossa", "memory_percent": 8.2}
      ]
    }
  },
  "status": "success"
}
```

### Performance Benchmarks
**POST** `/performance/benchmark`

Runs system performance benchmarks.

#### Request Body
```json
{
  "type": "quick",              // "quick", "full", "custom"
  "duration": 30,               // Benchmark duration in seconds
  "tests": ["cpu", "memory"]    // Specific tests to run
}
```

#### Response
```json
{
  "benchmark_results": {
    "type": "quick",
    "duration": 30,
    "started_at": "2024-12-01T12:00:00Z",
    "completed_at": "2024-12-01T12:00:30Z",
    "tests": [
      {
        "name": "CPU Performance",
        "type": "cpu",
        "duration": 10.5,
        "samples": 30,
        "avg_usage": 45.2,
        "max_usage": 67.8,
        "min_usage": 23.1
      },
      {
        "name": "Memory Performance",
        "type": "memory",
        "duration": 5.2,
        "memory_before": 8388608000,
        "memory_after": 8589934592,
        "memory_diff": 201326592
      }
    ],
    "total_duration": 15.7
  },
  "status": "success",
  "message": "Benchmark completed with 2 tests"
}
```

### Performance Recommendations
**GET** `/performance/recommendations`

Generates intelligent performance optimization recommendations.

#### Response
```json
{
  "recommendations": [
    {
      "category": "CPU",
      "severity": "high",
      "title": "High CPU Usage Detected",
      "description": "CPU usage is at 85.5%. Consider optimizing CPU-intensive processes.",
      "current_value": 85.5,
      "threshold": 80,
      "suggestions": [
        "Check top CPU consuming processes",
        "Consider scaling down non-essential services",
        "Review scheduled tasks and cron jobs"
      ]
    },
    {
      "category": "Memory",
      "severity": "medium",
      "title": "Moderate Memory Usage",
      "description": "Memory usage is at 72.3%. Monitor for trends.",
      "current_value": 72.3,
      "threshold": 70,
      "suggestions": [
        "Monitor memory usage patterns",
        "Review running services"
      ]
    }
  ],
  "total_recommendations": 2,
  "by_severity": {
    "critical": 0,
    "high": 1,
    "medium": 1,
    "low": 0
  },
  "generated_at": "2024-12-01T12:00:00Z",
  "status": "success"
}
```

---

## 📄 Enhanced Logs

### Advanced Log Retrieval
**GET** `/logs`

Retrieves system logs with advanced filtering and search capabilities.

#### Query Parameters
- `type`: Log type (`all`, `barbossa`, `security`, `system`)
- `level`: Log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`)
- `limit`: Maximum entries (default: 100)
- `offset`: Pagination offset
- `search`: Search query
- `start_date`: Start date filter (ISO format)
- `end_date`: End date filter (ISO format)

#### Response
```json
{
  "logs": [
    {
      "timestamp": "2024-12-01T12:00:00",
      "level": "INFO",
      "message": "Barbossa execution completed successfully",
      "file": "barbossa_20241201.log",
      "line_number": 145,
      "type": "barbossa"
    }
  ],
  "total": 500,
  "limit": 100,
  "offset": 0,
  "has_more": true,
  "filters": {
    "type": "all",
    "level": null,
    "search": null
  },
  "status": "success"
}
```

### Log File Management
**GET** `/logs/files`

Lists all available log files with metadata.

#### Response
```json
{
  "log_files": [
    {
      "name": "barbossa_20241201.log",
      "path": "/home/user/barbossa-engineer/logs/barbossa_20241201.log",
      "type": "system",
      "size": 1048576,
      "modified": "2024-12-01T12:00:00Z",
      "lines": 1500
    }
  ],
  "total": 15,
  "status": "success"
}
```

**POST** `/logs/clear`

Clears old log files based on criteria.

#### Request Body
```json
{
  "days_older_than": 30,
  "file_types": ["system", "security"],
  "dry_run": true
}
```

---

## ⚙️ Configuration Management

### System Configuration
**GET** `/config`

Retrieves complete system configuration.

#### Response
```json
{
  "configuration": {
    "repository_whitelist": {
      "allowed_repositories": ["https://github.com/user/repo"]
    },
    "work_tally": {
      "infrastructure": 45,
      "personal_projects": 32,
      "davy_jones": 23
    },
    "environment": {
      "PATH": "/usr/local/bin:/usr/bin",
      "ANTHROPIC_API_KEY": "***HIDDEN***"
    }
  },
  "status": "success"
}
```

### Specific Configuration Files
**GET** `/config/{config_name}`

Retrieves a specific configuration file.

**PUT** `/config/{config_name}`

Updates a specific configuration file.

#### Request Body
```json
{
  "config": {
    "new_setting": "value",
    "updated_setting": "new_value"
  }
}
```

---

## 🔔 Notifications

### Notification Management
**GET** `/notifications`

Retrieves system notifications with filtering.

#### Query Parameters
- `limit`: Maximum notifications (default: 50)
- `offset`: Pagination offset
- `severity`: Filter by severity (`info`, `warning`, `error`, `critical`)
- `read`: Filter by read status (`true`/`false`)

#### Response
```json
{
  "notifications": [
    {
      "id": "uuid",
      "title": "System Alert",
      "message": "High CPU usage detected",
      "severity": "warning",
      "category": "system",
      "timestamp": "2024-12-01T12:00:00Z",
      "read": false,
      "metadata": {}
    }
  ],
  "total": 25,
  "unread_count": 5,
  "status": "success"
}
```

**POST** `/notifications`

Creates a new notification.

#### Request Body
```json
{
  "title": "Custom Alert",
  "message": "This is a custom notification message",
  "severity": "info",              // "info", "warning", "error", "critical"
  "category": "custom",
  "metadata": {"source": "api"}
}
```

**PUT** `/notifications/{notification_id}/read`

Marks a notification as read.

---

## 🔧 Service Management

### Service Status
**GET** `/services`

Retrieves system service status and Barbossa processes.

#### Response
```json
{
  "system_services": [
    {
      "name": "docker",
      "status": "active",
      "description": "Docker Application Container Engine",
      "load_state": "loaded",
      "active_state": "active",
      "sub_state": "running"
    }
  ],
  "barbossa_processes": [
    {
      "pid": 12345,
      "name": "python3",
      "cmdline": "python3 barbossa.py",
      "status": "sleeping"
    }
  ],
  "status": "success"
}
```

### Service Control
**POST** `/services/{service_name}/{action}`

Controls system services (limited to allowed services).

#### Path Parameters
- `service_name`: Service name (`docker`, `nginx`, `cloudflared`)
- `action`: Action to perform (`start`, `stop`, `restart`, `reload`)

#### Response
```json
{
  "status": "success",
  "message": "Successfully restarted docker",
  "output": "Service restart completed"
}
```

---

## 📊 Metrics History

### Historical Metrics
**GET** `/metrics/history`

Retrieves historical system metrics for trend analysis.

#### Query Parameters
- `start_date`: Start date (ISO format)
- `end_date`: End date (ISO format)
- `type`: Metric type (`cpu`, `memory`, `disk`, `network`, `all`)
- `interval`: Time interval (`minute`, `hour`, `day`)

#### Response
```json
{
  "metrics": {
    "cpu": [
      {"timestamp": "2024-12-01T00:00:00Z", "value": 45.2},
      {"timestamp": "2024-12-01T01:00:00Z", "value": 52.1}
    ],
    "memory": [
      {"timestamp": "2024-12-01T00:00:00Z", "value": 67.8},
      {"timestamp": "2024-12-01T01:00:00Z", "value": 71.2}
    ]
  },
  "interval": "hour",
  "start_date": "2024-12-01T00:00:00Z",
  "end_date": "2024-12-01T12:00:00Z",
  "status": "success"
}
```

### Store Current Metrics
**POST** `/metrics/store`

Stores current system metrics for historical tracking.

#### Response
```json
{
  "status": "success",
  "message": "Metrics stored successfully",
  "metrics": {
    "timestamp": "2024-12-01T12:00:00Z",
    "cpu_percent": 45.2,
    "memory_percent": 67.8,
    "disk_usage": {"/": {"percent": 50.0}},
    "network_stats": {"bytes_sent": 1000000}
  }
}
```

---

## ❌ Error Handling

All endpoints follow consistent error response format:

```json
{
  "error": "Error description",
  "status": "error",
  "details": "Additional error details",
  "timestamp": "2024-12-01T12:00:00Z"
}
```

### Common HTTP Status Codes
- `200 OK`: Successful operation
- `201 Created`: Resource created successfully
- `400 Bad Request`: Invalid request data
- `401 Unauthorized`: Authentication required
- `403 Forbidden`: Access denied
- `404 Not Found`: Resource not found
- `500 Internal Server Error`: Server error
- `503 Service Unavailable`: Service temporarily unavailable

### Validation Errors
```json
{
  "error": "Validation failed",
  "errors": [
    "Field 'name' is required",
    "Field 'threshold' must be between 0 and 100"
  ],
  "status": "error"
}
```

---

## 📖 Usage Examples

### Example 1: Complete Backup and Restore Workflow

```bash
# Create a full backup
curl -X POST https://localhost:8443/api/v2/backup/create \
  -u admin:admin \
  -H "Content-Type: application/json" \
  -d '{
    "type": "full",
    "include_logs": true,
    "compression": "gzip"
  }'

# List all backups
curl -X GET https://localhost:8443/api/v2/backup/list \
  -u admin:admin

# Restore configuration from backup
curl -X POST https://localhost:8443/api/v2/backup/{backup_id}/restore \
  -u admin:admin \
  -H "Content-Type: application/json" \
  -d '{
    "type": "config",
    "force": false
  }'
```

### Example 2: Performance Monitoring and Optimization

```bash
# Get performance profile
curl -X GET https://localhost:8443/api/v2/performance/profile \
  -u admin:admin

# Run performance benchmark
curl -X POST https://localhost:8443/api/v2/performance/benchmark \
  -u admin:admin \
  -H "Content-Type: application/json" \
  -d '{
    "type": "quick",
    "duration": 30,
    "tests": ["cpu", "memory", "disk"]
  }'

# Get performance recommendations
curl -X GET https://localhost:8443/api/v2/performance/recommendations \
  -u admin:admin
```

### Example 3: Alert Management

```bash
# Create CPU usage alert
curl -X POST https://localhost:8443/api/v2/monitoring/alerts \
  -u admin:admin \
  -H "Content-Type: application/json" \
  -d '{
    "name": "High CPU Usage",
    "metric": "cpu",
    "threshold": 80,
    "severity": "high",
    "description": "Alert when CPU usage exceeds 80%"
  }'

# Get all alerts and active alerts
curl -X GET https://localhost:8443/api/v2/monitoring/alerts \
  -u admin:admin
```

### Example 4: Advanced Search

```bash
# Search across all categories
curl -X GET "https://localhost:8443/api/v2/search?q=docker&category=all&limit=20" \
  -u admin:admin

# Search only in logs with content
curl -X GET "https://localhost:8443/api/v2/search?q=error&category=logs&include_content=true" \
  -u admin:admin
```

### Example 5: Database Management

```bash
# Get database statistics
curl -X GET https://localhost:8443/api/v2/database/stats \
  -u admin:admin

# Optimize all databases
curl -X POST https://localhost:8443/api/v2/database/optimize \
  -u admin:admin \
  -H "Content-Type: application/json" \
  -d '{
    "database": "all",
    "operations": ["vacuum", "analyze"]
  }'
```

---

## 🔄 API Versioning and Compatibility

- **Current Version**: v2.0.0
- **Base Path**: `/api/v2`
- **Backward Compatibility**: Maintained for v1 endpoints
- **Deprecation Policy**: 6-month notice for breaking changes

## 🔐 Security Considerations

- All endpoints require HTTP Basic Authentication
- HTTPS only (self-signed certificates accepted for development)
- Rate limiting applied to prevent abuse
- Input validation and sanitization on all endpoints
- Sensitive data (API keys, passwords) are masked in responses
- Repository access controlled by security whitelist

## 📈 Performance Characteristics

- **Caching**: Implemented for expensive operations (TTL: 30-300 seconds)
- **Pagination**: Available on list endpoints (default limit: 50)
- **Async Operations**: Long-running tasks (backups, benchmarks) return immediately
- **Resource Limits**: File operations limited to prevent system overload

---

This documentation covers all the new Enhanced API v2 endpoints. For additional support or feature requests, please refer to the system logs or contact the development team.

**Last Updated**: December 1, 2024
**API Version**: 2.0.0