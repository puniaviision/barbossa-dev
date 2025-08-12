# Barbossa Enhanced API Endpoints Documentation

## Overview

This document details the new API endpoints implemented for the Barbossa Enhanced system. These endpoints provide advanced functionality for task management, performance optimization, system integration, and workflow automation.

## Authentication

All endpoints require authentication via HTTP Basic Auth or session-based authentication. The following HTTP status codes are used:
- `200`: Success
- `400`: Bad Request (missing or invalid parameters)
- `401`: Unauthorized (authentication required)
- `403`: Forbidden (insufficient permissions)
- `404`: Not Found (resource doesn't exist)
- `409`: Conflict (resource already exists or in use)
- `500`: Internal Server Error
- `503`: Service Unavailable (required service not running)

## New API Endpoints

### 1. Task Scheduling and Management

#### GET/POST `/api/tasks/scheduled`
Manage scheduled cron tasks.

**GET** - Retrieve all scheduled tasks
```json
{
  "tasks": [
    {
      "schedule": "0 */4 * * *",
      "command": "python3 /home/dappnode/barbossa-engineer/barbossa.py",
      "description": "Runs at 0:00"
    }
  ]
}
```

**POST** - Create a new scheduled task
```json
{
  "schedule": "0 2 * * *",
  "command": "docker system prune -f",
  "description": "Daily Docker cleanup at 2 AM"
}
```

#### DELETE `/api/tasks/scheduled/<task_id>`
Delete a specific scheduled task by ID.

### 2. Performance Analytics

#### GET `/api/analytics/performance`
Get comprehensive performance analytics and trends (cached for 2 minutes).

```json
{
  "analytics": {
    "avg_cpu": 25.3,
    "avg_memory": 45.7,
    "avg_disk": 62.1,
    "peak_cpu": 89.2,
    "peak_memory": 78.4,
    "avg_load": 1.2,
    "network_peak_in": 45.6,
    "network_peak_out": 23.1
  },
  "trends": {
    "cpu_trend": "increasing",
    "cpu_change": 5.2,
    "memory_trend": "stable"
  },
  "recommendations": [
    "High CPU usage detected. Consider optimizing processes."
  ]
}
```

### 3. Resource Optimization

#### GET `/api/optimization/suggestions`
Get automated resource optimization suggestions (cached for 5 minutes).

```json
{
  "suggestions": [
    {
      "category": "disk",
      "priority": "high",
      "title": "Low Disk Space",
      "description": "Disk usage is 92.3%",
      "actions": [
        "Clean old log files older than 30 days",
        "Remove Docker unused images and containers"
      ]
    }
  ],
  "total_count": 3,
  "priorities": {
    "critical": 1,
    "high": 2,
    "medium": 0,
    "low": 0
  }
}
```

#### POST `/api/optimization/apply`
Apply specific optimization suggestions.

```json
{
  "type": "disk",
  "action": "clean_logs"
}
```

Response:
```json
{
  "success": true,
  "results": [
    {
      "action": "clean_logs",
      "success": true,
      "message": "Cleaned 15 log files (45.2 MB)"
    }
  ],
  "applied_count": 1
}
```

### 4. Integration Management

#### GET `/api/integrations`
List available and active system integrations (cached for 2 minutes).

```json
{
  "integrations": [
    {
      "name": "GitHub",
      "type": "vcs",
      "status": "active",
      "description": "Git repository management and automation",
      "config_required": ["GITHUB_TOKEN"],
      "endpoints": ["/api/integrations/github/repos"]
    }
  ],
  "active_count": 3,
  "total_count": 5
}
```

#### GET `/api/integrations/github/repos`
Get GitHub repository information (requires GITHUB_TOKEN, cached for 5 minutes).

#### GET `/api/integrations/docker/containers`
Get detailed Docker container information (cached for 30 seconds).

```json
{
  "containers": [
    {
      "name": "barbossa_portal",
      "status": "Up 2 hours",
      "image": "python:3.9-alpine",
      "ports": "8443->8443/tcp",
      "running": true
    }
  ],
  "total_containers": 5,
  "running_containers": 3
}
```

### 5. Advanced Monitoring and Analytics

#### GET/POST `/api/monitoring/alerts/rules`
Manage monitoring alert rules.

**GET** - Retrieve alert rules
```json
{
  "rules": {
    "cpu_high": {
      "name": "High CPU Usage",
      "condition": "cpu_percent > 90",
      "duration": 300,
      "severity": "critical",
      "enabled": true
    }
  }
}
```

**POST** - Create or update alert rule
```json
{
  "id": "memory_warning",
  "rule": {
    "name": "Memory Warning",
    "condition": "memory_percent > 80",
    "duration": 180,
    "severity": "warning",
    "enabled": true
  }
}
```

#### GET `/api/monitoring/anomalies`
Detect system anomalies using statistical analysis (cached for 3 minutes).

```json
{
  "anomalies": [
    {
      "metric": "cpu_percent",
      "value": 95.2,
      "expected_range": "15.0-45.0",
      "deviation": 3.2,
      "timestamp": "2024-01-15T14:30:00",
      "severity": "high"
    }
  ],
  "total_count": 5,
  "data_points_analyzed": 500,
  "detection_method": "statistical_deviation"
}
```

### 6. Workflow Automation

#### GET/POST `/api/workflows`
Manage automation workflows.

**GET** - Retrieve workflows
**POST** - Create new workflow

Example workflow:
```json
{
  "id": "daily_cleanup",
  "workflow": {
    "name": "Daily System Cleanup",
    "description": "Automated daily system maintenance",
    "trigger": {
      "type": "schedule",
      "schedule": "0 2 * * *"
    },
    "actions": [
      {
        "type": "run_command",
        "config": {
          "command": "docker system prune -f",
          "timeout": 60
        }
      },
      {
        "type": "trigger_barbossa",
        "config": {
          "work_area": "infrastructure"
        }
      }
    ]
  }
}
```

#### POST `/api/workflows/<workflow_id>/execute`
Execute a specific workflow.

```json
{
  "success": true,
  "workflow_id": "daily_cleanup",
  "execution_results": [
    {
      "action_index": 0,
      "type": "run_command",
      "success": true,
      "output": "Deleted 5 containers, 3 images",
      "return_code": 0
    }
  ],
  "success_rate": 1.0,
  "total_actions": 2,
  "successful_actions": 2
}
```

### 7. Advanced Data Export/Import

#### POST `/api/data/export`
Export system data in various formats.

```json
{
  "type": "complete",
  "format": "json",
  "date_range": 7
}
```

Supported types: `complete`, `logs`, `metrics`, `changelogs`, `configuration`
Supported formats: `json`, `csv` (metrics only)

#### POST `/api/data/import`
Import system data from uploaded files.
- Accepts multipart form data with file upload
- Supports JSON format only
- Can import configuration data, workflows, and alert rules

### 8. API Key/Token Management

#### GET/POST `/api/auth/tokens`
Manage API authentication tokens.

**GET** - List tokens (without revealing actual token values)
```json
{
  "tokens": [
    {
      "id": "abc123def456",
      "name": "Automation Token",
      "created_by": "admin",
      "created_at": "2024-01-15T10:00:00Z",
      "expires_at": "2024-02-15T10:00:00Z",
      "permissions": ["read", "write"],
      "last_used": null,
      "active": true
    }
  ]
}
```

**POST** - Create new token
```json
{
  "name": "CI/CD Token",
  "permissions": ["read", "execute"],
  "expires_days": 90
}
```

#### DELETE/PATCH `/api/auth/tokens/<token_id>`
Delete or update specific tokens.

### 9. Webhook Management

#### GET/POST `/api/webhooks`
Manage webhooks for external integrations.

**POST** - Create webhook
```json
{
  "id": "github_webhook",
  "config": {
    "name": "GitHub Integration",
    "url": "https://api.github.com/webhook",
    "events": ["push", "pull_request"],
    "secret": "webhook_secret",
    "active": true
  }
}
```

## Error Handling

All endpoints include comprehensive error handling with:
- Input validation
- Permission checks
- Resource availability verification
- Graceful degradation when services are unavailable
- Sensitive information sanitization in logs and responses

## Caching Strategy

Endpoints implement intelligent caching:
- **Short-term (10-30s)**: Real-time system metrics
- **Medium-term (2-5min)**: Performance analytics, integrations
- **Long-term (5-10min)**: Configuration data, suggestions

Cache keys include request parameters to ensure accurate responses.

## Security Considerations

- All endpoints require authentication
- Sensitive information is sanitized from responses
- File operations are restricted to safe directories
- Command execution is limited to whitelisted operations
- API tokens use secure hashing and expiration
- Input validation prevents injection attacks

## Rate Limiting

While not explicitly implemented in these endpoints, the existing enhanced security framework provides:
- Brute force protection
- IP-based rate limiting
- Session management
- Request throttling

## Usage Examples

### Create a Workflow
```bash
curl -X POST https://eastindiaonchaincompany.xyz/api/workflows \
  -H "Content-Type: application/json" \
  -u admin:password \
  -d '{
    "id": "backup_workflow",
    "workflow": {
      "name": "Daily Backup",
      "description": "Automated system backup",
      "trigger": {"type": "manual"},
      "actions": [
        {
          "type": "run_command",
          "config": {
            "command": "tar -czf /backup/system_$(date +%Y%m%d).tar.gz /home/dappnode/barbossa-engineer",
            "timeout": 300
          }
        }
      ]
    }
  }'
```

### Get Performance Analytics
```bash
curl -X GET https://eastindiaonchaincompany.xyz/api/analytics/performance \
  -H "Accept: application/json" \
  -u admin:password
```

### Export System Data
```bash
curl -X POST https://eastindiaonchaincompany.xyz/api/data/export \
  -H "Content-Type: application/json" \
  -u admin:password \
  -d '{
    "type": "metrics",
    "format": "csv",
    "date_range": 1
  }' \
  --output metrics_export.csv
```

## Future Enhancements

Planned improvements include:
- Real-time WebSocket endpoints for live monitoring
- Advanced machine learning-based anomaly detection
- Extended integration support (Slack, Discord, Teams)
- Automated workflow triggers based on system events
- Enhanced export formats (Excel, PDF reports)
- Grafana dashboard integration
- API versioning support

## Support and Troubleshooting

For issues with these endpoints:
1. Check the web portal logs: `/home/dappnode/barbossa-engineer/web_portal/web_portal.log`
2. Verify service dependencies are running (Docker, Redis, etc.)
3. Ensure proper authentication credentials
4. Check system resources and permissions
5. Review the security audit logs for authentication issues

---

**Last Updated**: 2025-08-11  
**Version**: 2.3.0  
**Author**: East India Onchain Company - Barbossa Enhanced System