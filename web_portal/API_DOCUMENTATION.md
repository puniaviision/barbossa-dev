# Barbossa Enhanced Web Portal - New API Endpoints Documentation

This document describes the new API endpoints implemented for the Barbossa Enhanced Web Portal system. The new APIs significantly expand the system's capabilities with real-time monitoring, analytics, automation, and development tools.

## Overview

The new API implementation introduces three major API modules:

1. **Advanced API (v3)** - `/api/v3/*` - Real-time streaming, analytics, backup/restore, integrations
2. **Monitoring API** - `/api/monitoring/*` - Comprehensive monitoring, alerting, and observability
3. **Development Tools API** - `/api/devtools/*` - Project management, build automation, code analysis

## Advanced API (v3) - `/api/v3/`

### Real-time Streaming Endpoints

#### Stream System Metrics
```http
GET /api/v3/stream/metrics
```
Stream real-time system metrics via Server-Sent Events (SSE).

**Response**: Continuous stream of JSON objects containing system metrics.

**Example Response**:
```json
{
  "cpu_percent": 45.2,
  "memory_percent": 67.8,
  "disk_percent": 23.1,
  "timestamp": "2024-08-14T15:30:45.123Z"
}
```

#### Stream Live Logs
```http
GET /api/v3/stream/logs
```
Stream real-time log entries via Server-Sent Events.

#### Stream Alerts
```http
GET /api/v3/stream/alerts
```
Stream real-time system alerts via Server-Sent Events.

### Analytics Endpoints

#### Performance Trends
```http
GET /api/v3/analytics/trends?metric=cpu_percent&hours=24
```
Get performance trends and predictions for system metrics.

**Parameters**:
- `metric` (string): Metric name to analyze
- `hours` (integer): Time window in hours (default: 24)

**Example Response**:
```json
{
  "metric": "cpu_percent",
  "period_hours": 24,
  "trend": {
    "slope": 0.02,
    "direction": "increasing",
    "confidence": 0.85
  },
  "statistics": {
    "current": 45.2,
    "mean": 42.1,
    "std": 8.3,
    "min": 15.0,
    "max": 89.2
  },
  "predictions": {
    "next_hours": 6,
    "values": [46.1, 47.8, 49.2, 50.1, 51.8, 53.2]
  },
  "anomalies": {
    "count": 3,
    "recent": [89.2, 87.1, 85.6]
  }
}
```

#### Anomaly Detection
```http
GET /api/v3/analytics/anomalies?hours=24&sensitivity=2.0
```
Detect system anomalies using statistical methods.

#### Performance Score
```http
GET /api/v3/analytics/performance-score
```
Calculate overall system performance score (0-100).

### Backup and Restore Endpoints

#### Create Backup
```http
POST /api/v3/backup/create
```

**Request Body**:
```json
{
  "backup_type": "full|config|data",
  "include_logs": false,
  "compress": true
}
```

#### List Backups
```http
GET /api/v3/backup/list
```

#### Restore Backup
```http
POST /api/v3/backup/{backup_id}/restore
```

### Integration Endpoints

#### GitHub Webhook Handler
```http
POST /api/v3/integrations/github/webhook
```
Handle GitHub webhook events for CI/CD integration.

#### Slack Notifications
```http
POST /api/v3/integrations/slack/notify
```

**Request Body**:
```json
{
  "message": "System alert: High CPU usage detected",
  "channel": "#alerts",
  "username": "Barbossa"
}
```

### Automation Workflow Endpoints

#### Get Workflow Templates
```http
GET /api/v3/workflows/templates
```
Get available automation workflow templates.

#### Execute Workflow
```http
POST /api/v3/workflows/execute
```

**Request Body**:
```json
{
  "template_id": "system_maintenance",
  "parameters": {
    "log_retention_days": 30,
    "services": ["docker", "nginx"]
  },
  "dry_run": false
}
```

### Database Management Endpoints

#### Database Information
```http
GET /api/v3/database/info
```
Get database statistics and information.

#### Optimize Database
```http
POST /api/v3/database/optimize
```
Optimize database performance (VACUUM, ANALYZE, REINDEX).

#### Database Backup
```http
POST /api/v3/database/backup
```
Create compressed database backup.

### Health and Status Endpoints

#### Health Check
```http
GET /api/v3/health
```
Comprehensive health check of all system components.

#### Status Summary
```http
GET /api/v3/status/summary
```
Get comprehensive system status summary.

#### API Documentation
```http
GET /api/v3/docs
```
Get complete API documentation in JSON format.

## Monitoring API - `/api/monitoring/`

### Monitor Management

#### Create Monitor
```http
POST /api/monitoring/monitors
```

**Request Body**:
```json
{
  "name": "CPU Usage Monitor",
  "type": "metric_threshold",
  "config": {
    "metric": "cpu_percent",
    "threshold": 80,
    "operator": ">",
    "interval": 60
  }
}
```

**Monitor Types**:
- `metric_threshold` - Monitor metric values against thresholds
- `service_health` - Monitor service status
- `process_monitor` - Monitor running processes
- `log_monitor` - Monitor log files for patterns

#### List Monitors
```http
GET /api/monitoring/monitors
```

#### Get Monitor Details
```http
GET /api/monitoring/monitors/{monitor_id}
```

#### Update Monitor
```http
PUT /api/monitoring/monitors/{monitor_id}
```

#### Delete Monitor
```http
DELETE /api/monitoring/monitors/{monitor_id}
```

### Alert Management

#### Get Alerts
```http
GET /api/monitoring/alerts
```

#### Create Alert Rule
```http
POST /api/monitoring/alerts
```

**Request Body**:
```json
{
  "name": "High CPU Alert",
  "condition": "cpu_percent > 90",
  "action": "slack_notify",
  "severity": "critical",
  "cooldown_seconds": 300
}
```

### Live Metrics

#### Get Live Metrics
```http
GET /api/monitoring/metrics/live
```
Get current system metrics with anomaly detection.

#### Get Baseline Metrics
```http
GET /api/monitoring/metrics/baseline
```
Get calculated baseline performance metrics.

#### Update Baselines
```http
POST /api/monitoring/metrics/baseline/update
```
Force recalculation of baseline metrics.

### Observability

#### Get System Traces
```http
GET /api/monitoring/observability/traces
```
Get system process traces and execution information.

#### Get Service Dependencies
```http
GET /api/monitoring/observability/dependencies
```
Get service dependency graph and relationships.

#### Dashboard Summary
```http
GET /api/monitoring/dashboard/summary
```
Get monitoring dashboard summary data.

## Development Tools API - `/api/devtools/`

### Project Management

#### List Projects
```http
GET /api/devtools/projects
```
Get all development projects with analysis.

#### Analyze Project
```http
POST /api/devtools/projects
```

**Request Body**:
```json
{
  "project_path": "/home/user/barbossa-engineer/projects/my-project"
}
```

**Response includes**:
- Project type detection (Node.js, Python, Rust, Go)
- File structure analysis
- Git repository information
- Dependency analysis
- Health score calculation

### Build and Test Management

#### Start Build
```http
POST /api/devtools/build
```

**Request Body**:
```json
{
  "project_path": "/path/to/project",
  "build_command": "npm run build"
}
```

#### Get Build Status
```http
GET /api/devtools/build/{build_id}
```

#### Get Build History
```http
GET /api/devtools/builds
```

#### Run Tests
```http
POST /api/devtools/test
```

**Request Body**:
```json
{
  "project_path": "/path/to/project",
  "test_command": "npm test"
}
```

#### Get Test Results
```http
GET /api/devtools/test/{test_id}
```

### Code Analysis

#### Analyze Code Quality
```http
POST /api/devtools/analyze/code
```

**Request Body**:
```json
{
  "project_path": "/path/to/project"
}
```

**Response includes**:
- File type analysis
- Complexity scoring
- Maintainability assessment
- Security issue detection
- Improvement recommendations

### Dependency Management

#### Check Dependencies
```http
POST /api/devtools/dependencies/check
```

**Request Body**:
```json
{
  "project_path": "/path/to/project"
}
```

**Features**:
- Security vulnerability scanning
- Outdated package detection
- Dependency conflict analysis
- Update recommendations

### Workflow Templates

#### Get Workflow Templates
```http
GET /api/devtools/workflow/templates
```
Get available development workflow templates.

**Available Templates**:
- Basic CI/CD Workflow
- Code Quality Check
- Dependency Update Workflow

## Common Features

### Error Handling

All endpoints use consistent error response format:

```json
{
  "error": "Error message description",
  "details": "Additional error details (optional)",
  "timestamp": "2024-08-14T15:30:45.123Z"
}
```

**HTTP Status Codes**:
- `200` - Success
- `201` - Created
- `202` - Accepted (for async operations)
- `400` - Bad Request
- `401` - Unauthorized
- `403` - Forbidden
- `404` - Not Found
- `429` - Too Many Requests
- `500` - Internal Server Error
- `503` - Service Unavailable

### Authentication

All new APIs inherit authentication from the parent web portal application. Ensure you're authenticated before making requests.

### Rate Limiting

Currently, no rate limiting is implemented, but it's recommended for production deployments.

### Caching

Many endpoints implement intelligent caching:
- Analytics endpoints: 5-minute cache
- System metrics: 10-second cache
- Code analysis: 1-hour cache
- Database info: 30-second cache

### Request Validation

All POST/PUT endpoints validate request data with detailed error messages for missing or invalid fields.

## Usage Examples

### Real-time Monitoring Dashboard

```javascript
// Connect to real-time metrics stream
const eventSource = new EventSource('/api/v3/stream/metrics');
eventSource.onmessage = function(event) {
    const metrics = JSON.parse(event.data);
    updateDashboard(metrics);
};
```

### Automated CI/CD Pipeline

```bash
# Start build
curl -X POST /api/devtools/build \
  -H "Content-Type: application/json" \
  -d '{"project_path": "/path/to/project"}'

# Run tests
curl -X POST /api/devtools/test \
  -H "Content-Type: application/json" \
  -d '{"project_path": "/path/to/project"}'

# Create backup after successful deployment
curl -X POST /api/v3/backup/create \
  -H "Content-Type: application/json" \
  -d '{"backup_type": "config", "compress": true}'
```

### System Health Monitoring

```python
import requests

# Get comprehensive health status
health = requests.get('/api/v3/health').json()
monitoring_health = requests.get('/api/monitoring/health').json()
devtools_health = requests.get('/api/devtools/health').json()

# Check for any unhealthy components
if any(h['status'] != 'healthy' for h in [health, monitoring_health, devtools_health]):
    # Send alert
    requests.post('/api/v3/integrations/slack/notify', json={
        'message': 'System health check failed',
        'channel': '#alerts'
    })
```

## Performance Considerations

1. **Streaming Endpoints**: Use Server-Sent Events efficiently, close connections when not needed
2. **Analytics**: Large time windows may take longer to process
3. **Code Analysis**: Results are cached to improve performance
4. **Concurrent Operations**: Build and test operations are limited to prevent resource exhaustion

## Security Considerations

1. **Path Validation**: All file path inputs are validated against allowed directories
2. **Command Injection**: All shell commands use safe subprocess execution
3. **Access Control**: Security guard validation for repository operations
4. **Input Sanitization**: All user inputs are validated and sanitized

## Future Enhancements

1. **WebSocket Support**: Real-time bidirectional communication
2. **Advanced Analytics**: Machine learning-based predictions
3. **Custom Integrations**: Plugin system for third-party tools
4. **Distributed Monitoring**: Multi-node system monitoring
5. **Advanced Security**: Role-based access control, API keys

## Support

For issues or questions regarding these APIs:
1. Check the health endpoints for system status
2. Review logs at `/api/v3/logs` or monitoring dashboards
3. Consult the built-in documentation at `/api/v3/docs`
4. Submit issues to the Barbossa repository

---

**Version**: 3.0.0  
**Last Updated**: August 14, 2024  
**Compatibility**: Barbossa Enhanced Web Portal v3.0+