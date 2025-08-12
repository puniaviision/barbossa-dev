# Barbossa Workflow Automation System

## Overview

The Barbossa Workflow Automation System is a comprehensive automation framework that extends the Barbossa Enhanced server management system with powerful workflow capabilities. This system enables you to create, schedule, monitor, and manage complex automation workflows for infrastructure management, project deployments, security audits, and more.

## Features

### 🔄 Workflow Engine
- **Powerful Execution Engine**: Asynchronous workflow execution with dependency management
- **Task Types**: Support for shell commands, Python scripts, file operations, service management, Git operations, API calls, health checks, and more
- **Dependency Management**: Automatic task ordering based on dependencies with circular dependency detection
- **Error Handling**: Comprehensive retry policies, timeouts, and failure handling
- **Variable Substitution**: Dynamic variable substitution in task configurations

### 📅 Scheduling System
- **Cron-like Scheduling**: Schedule workflows using cron expressions
- **Multiple Triggers**: Manual, scheduled, event-based, and webhook triggers
- **Smart Execution**: Automatic execution based on conditions and schedules
- **Conflict Resolution**: Prevent overlapping executions of the same workflow

### 📊 Monitoring & Alerting
- **Real-time Monitoring**: Live monitoring of workflow executions and system metrics
- **Performance Metrics**: Execution time tracking, success rates, and resource utilization
- **Alert System**: Configurable alerts based on performance thresholds and failure rates
- **Dashboard**: Comprehensive web dashboard for visualization and management

### 🌐 Web Portal Integration
- **Workflow Management**: Create, edit, and manage workflows through the web interface
- **Template Library**: Pre-built workflow templates for common tasks
- **Execution History**: Detailed logs and execution history
- **Real-time Status**: Live updates on workflow execution status

### 🔒 Security
- **Access Control**: Integration with Barbossa security system
- **Repository Validation**: Security guard integration for safe repository access
- **Audit Logging**: Comprehensive audit trails for all workflow operations
- **Secure Execution**: Sandboxed task execution with timeout controls

## System Architecture

```
┌─────────────────────────────────────────────────────┐
│                  Web Portal                         │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐   │
│  │ Workflows   │ │ Templates   │ │ Monitoring  │   │
│  │ Dashboard   │ │ Library     │ │ & Alerts    │   │
│  └─────────────┘ └─────────────┘ └─────────────┘   │
└─────────────────────────────────────────────────────┘
                         │
                    [REST API]
                         │
┌─────────────────────────────────────────────────────┐
│              Workflow Engine Core                   │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐   │
│  │ Workflow    │ │ Task        │ │ Dependency  │   │
│  │ Manager     │ │ Executor    │ │ Resolver    │   │
│  └─────────────┘ └─────────────┘ └─────────────┘   │
└─────────────────────────────────────────────────────┘
                         │
        ┌────────────────┼────────────────┐
        │                │                │
┌─────────────┐ ┌─────────────┐ ┌─────────────┐
│ Scheduler   │ │ Monitor     │ │ Security    │
│ Service     │ │ Service     │ │ Guard       │
│             │ │             │ │             │
│ • Cron Jobs │ │ • Metrics   │ │ • Access    │
│ • Triggers  │ │ • Alerts    │ │   Control   │
│ • Queuing   │ │ • Logging   │ │ • Validation│
└─────────────┘ └─────────────┘ └─────────────┘
                         │
                ┌─────────────────┐
                │    Database     │
                │                 │
                │ • Workflows     │
                │ • Executions    │
                │ • Metrics       │
                │ • Schedules     │
                └─────────────────┘
```

## Components

### 1. Workflow Engine (`workflow_automation.py`)
The core engine responsible for workflow execution and management.

**Key Classes:**
- `WorkflowEngine`: Main orchestration engine
- `Workflow`: Workflow definition and state
- `WorkflowTask`: Individual task within a workflow
- `TaskExecutor`: Executes different types of tasks

### 2. Scheduler Service (`workflow_scheduler.py`)
Handles scheduled execution of workflows with cron-like functionality.

**Features:**
- Cron expression parsing and scheduling
- Job queue management
- Execution history tracking
- Conflict prevention

### 3. Monitoring Service (`workflow_monitor.py`)
Provides real-time monitoring, metrics collection, and alerting.

**Components:**
- `WorkflowMonitor`: Main monitoring coordinator
- `MetricsCollector`: Collects and stores performance metrics
- `AlertManager`: Manages alerts and notifications

### 4. Web Portal Integration (`workflow_api.py`, `workflows.html`)
Web-based interface for workflow management.

**Features:**
- RESTful API for workflow operations
- Interactive dashboard
- Template management
- Real-time status updates

## Installation and Setup

### Prerequisites
- Python 3.8+ with asyncio support
- SQLite for data storage
- Access to system commands (bash, systemctl, docker, etc.)

### Installation
The workflow automation system is integrated into the Barbossa Enhanced system. No additional installation is required.

### Configuration
1. **Templates Directory**: Create workflow templates in `~/barbossa-engineer/workflow_templates/`
2. **Database**: Workflow data is stored in `~/barbossa-engineer/workflows.db`
3. **Logs**: Execution logs are stored in `~/barbossa-engineer/logs/`

## Usage

### Creating Workflows

#### From Templates
Use pre-built templates for common tasks:

```bash
# Via Python API
from workflow_automation import WorkflowEngine

engine = WorkflowEngine(Path.home() / 'barbossa-engineer')
workflow = engine.create_workflow_from_template('system_maintenance', {
    'backup_dir': '/backup',
    'log_retention_days': 30
})
```

#### From Configuration
Create custom workflows using JSON/YAML configuration:

```python
config = {
    'name': 'Custom Deployment',
    'description': 'Deploy application with tests',
    'tasks': [
        {
            'id': 'build',
            'name': 'Build Application',
            'type': 'shell_command',
            'command': 'npm run build'
        },
        {
            'id': 'test',
            'name': 'Run Tests',
            'type': 'shell_command',
            'command': 'npm test',
            'dependencies': ['build']
        },
        {
            'id': 'deploy',
            'name': 'Deploy to Production',
            'type': 'shell_command',
            'command': 'npm run deploy',
            'dependencies': ['test']
        }
    ]
}

workflow = engine.create_workflow_from_config(config)
```

### Executing Workflows

#### Manual Execution
```python
import asyncio

# Execute workflow
result = asyncio.run(engine.execute_workflow(workflow, TriggerType.MANUAL))
```

#### Scheduled Execution
```python
from workflow_scheduler import WorkflowSchedulerService

scheduler = WorkflowSchedulerService(Path.home() / 'barbossa-engineer')
scheduler.add_scheduled_workflow(
    workflow.workflow_id,
    '0 2 * * 0',  # Every Sunday at 2 AM
    enabled=True
)
```

### Web Interface

Access the workflow dashboard at `https://your-server:8443/workflows`

**Features:**
- View all workflows and their status
- Create workflows from templates
- Execute workflows manually
- View execution history and logs
- Manage scheduled workflows
- Monitor system performance

## Available Task Types

### Shell Command
Execute shell commands with environment control:
```yaml
type: shell_command
command: "echo 'Hello World'"
working_directory: "/path/to/work"
timeout: 300
```

### Python Script
Execute Python scripts inline or from files:
```yaml
type: python_script
script: |
  import os
  print(f"Current directory: {os.getcwd()}")
timeout: 600
```

### File Operations
Perform file system operations:
```yaml
type: file_operation
operation: copy  # copy, move, delete, compress
source: "/source/path"
destination: "/dest/path"
```

### Service Management
Manage system services:
```yaml
type: service_management
action: restart  # start, stop, restart, status
service_name: "nginx"
service_type: "systemd"  # systemd, docker
```

### Git Operations
Perform Git operations with security validation:
```yaml
type: git_operation
operation: pull  # clone, pull, push, checkout, commit
repository_url: "https://github.com/user/repo"
branch: "main"
working_directory: "/path/to/repo"
```

### Health Checks
Perform system and service health checks:
```yaml
type: health_check
check_type: http  # http, tcp, service, disk, memory
url: "http://localhost:8080/health"
expected_status: 200
```

### API Calls
Make HTTP API calls:
```yaml
type: api_call
url: "https://api.example.com/webhook"
method: "POST"
headers:
  Content-Type: "application/json"
data:
  message: "Workflow completed"
```

## Workflow Templates

### System Maintenance (`system_maintenance.yaml`)
Comprehensive system maintenance including:
- Pre-maintenance backup
- Package updates and cleanup
- Docker system cleanup
- Log rotation
- Security audit
- Service verification

### Project Deployment (`project_deployment.yaml`)
Automated deployment with:
- Repository validation and cloning
- Dependency installation
- Testing and building
- Service deployment
- Health checks
- Rollback on failure

### Security Audit (`security_audit.yaml`)
Complete security assessment:
- System information gathering
- User account audit
- File permissions review
- Network security check
- Log analysis
- Vulnerability scanning

### Backup and Recovery (`backup_and_recovery.yaml`)
Data protection workflows:
- System and database backups
- Configuration backup
- Backup verification
- Retention management
- Recovery procedures

## Monitoring and Alerting

### Metrics Collection
The system automatically collects:
- Workflow execution times
- Success/failure rates
- Resource utilization
- System performance metrics
- Error frequencies

### Alert Rules
Configure alerts for:
- High failure rates
- Long execution times
- Resource exhaustion
- Service failures
- Security violations

### Example Alert Configuration
```json
{
  "alert_rules": {
    "high_failure_rate": {
      "condition": {
        "metric_path": "failure_rate",
        "operator": ">",
        "threshold": 50
      },
      "severity": "warning",
      "message": "Workflow failure rate is above 50%"
    }
  },
  "notification_channels": {
    "log": {"type": "log"},
    "email": {
      "type": "email",
      "recipients": ["admin@example.com"]
    }
  }
}
```

## API Reference

### REST Endpoints

#### Workflows
- `GET /api/workflows/` - List all workflows
- `POST /api/workflows/create` - Create new workflow
- `GET /api/workflows/{id}/status` - Get workflow status
- `POST /api/workflows/{id}/execute` - Execute workflow
- `POST /api/workflows/{id}/cancel` - Cancel running workflow

#### Templates
- `GET /api/workflows/templates` - List available templates
- `GET /api/workflows/templates/{name}` - Get template details

#### Monitoring
- `GET /api/workflows/stats` - Get workflow statistics
- `GET /api/workflows/history` - Get execution history
- `GET /api/workflows/running` - Get currently running workflows

#### Scheduler
- `GET /api/workflows/scheduler/status` - Get scheduler status
- `POST /api/workflows/scheduler/start` - Start scheduler
- `POST /api/workflows/scheduler/stop` - Stop scheduler

## Security Considerations

### Access Control
- All workflow operations require authentication
- Repository access validated through security guard
- ZKP2P repositories are explicitly blocked
- Audit logging for all operations

### Safe Execution
- Task timeout controls prevent runaway processes
- Working directory restrictions
- Environment variable sanitization
- Resource usage monitoring

### Data Protection
- Sensitive data sanitization in logs
- Secure database storage
- Encrypted communications
- Backup encryption options

## Troubleshooting

### Common Issues

#### Workflow Execution Failures
1. Check task logs in the web interface
2. Verify task configuration and dependencies
3. Ensure required permissions and resources
4. Check system resource availability

#### Scheduler Not Working
1. Verify scheduler service is running
2. Check cron expression syntax
3. Review scheduler logs
4. Ensure workflow exists and is valid

#### Performance Issues
1. Monitor system resource usage
2. Check database performance
3. Review concurrent workflow limits
4. Optimize task configurations

### Log Locations
- **Workflow Engine**: `~/barbossa-engineer/logs/workflow_engine_YYYYMMDD.log`
- **Scheduler**: `~/barbossa-engineer/logs/scheduler_YYYYMMDD.log`
- **Monitor**: `~/barbossa-engineer/logs/monitor_YYYYMMDD.log`
- **Web Portal**: `~/barbossa-engineer/logs/barbossa_enhanced_*.log`

### Debugging Commands
```bash
# Check workflow status
python3 ~/barbossa-engineer/workflow_automation.py --status

# Test security system
python3 ~/barbossa-engineer/barbossa.py --test-security

# View recent logs
tail -f ~/barbossa-engineer/logs/workflow_engine_*.log

# Test workflow execution
python3 ~/barbossa-engineer/test_automation.py
```

## Performance Optimization

### Best Practices
- Use appropriate task timeouts
- Limit concurrent workflow executions
- Optimize task dependencies
- Use efficient task types
- Monitor resource usage

### Scaling Considerations
- Database optimization for large workflows
- Task execution parallelization
- Resource pooling for heavy operations
- Caching for frequently accessed data

## Integration Examples

### CI/CD Integration
```yaml
name: "CI/CD Pipeline"
description: "Continuous integration and deployment"
trigger_type: "webhook"
tasks:
  - id: "checkout"
    name: "Checkout Code"
    type: "git_operation"
    operation: "pull"
    
  - id: "test"
    name: "Run Tests"
    type: "shell_command"
    command: "npm test"
    dependencies: ["checkout"]
    
  - id: "deploy"
    name: "Deploy Application"
    type: "shell_command"
    command: "npm run deploy"
    dependencies: ["test"]
```

### Monitoring Integration
```python
# Custom monitoring hook
def custom_workflow_hook(workflow_id, status, metrics):
    if status == 'failed':
        # Send alert to external monitoring system
        send_alert_to_datadog(workflow_id, metrics)

# Register hook with workflow engine
engine.add_completion_hook(custom_workflow_hook)
```

## Development

### Adding New Task Types
```python
# In TaskExecutor class
async def _execute_custom_task(self, workflow: Workflow, task: WorkflowTask) -> bool:
    """Execute custom task type"""
    # Implementation here
    return True

# Register in task_handlers
self.task_handlers['custom_task'] = self._execute_custom_task
```

### Creating Custom Templates
```yaml
name: "Custom Template"
description: "Template description"
version: "1.0"
variables:
  variable_name: "default_value"
tasks:
  - id: "task1"
    name: "Task Name"
    type: "task_type"
    # Task configuration
```

## License

This workflow automation system is part of the Barbossa Enhanced project and follows the same licensing terms.

## Support

For support and questions:
1. Check the troubleshooting section
2. Review log files for error details
3. Test individual components
4. Consult the API documentation

---

**Barbossa Workflow Automation System** - Bringing powerful automation to your infrastructure management.