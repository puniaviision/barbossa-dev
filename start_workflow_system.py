#!/usr/bin/env python3
"""
Barbossa Workflow System Startup Script
Simple script to demonstrate and test the workflow automation system
"""

import asyncio
import json
import sys
import time
from pathlib import Path
from datetime import datetime

# Add current directory to path
sys.path.append(str(Path(__file__).parent))

def test_basic_functionality():
    """Test basic workflow functionality without external dependencies"""
    print("🚀 Barbossa Workflow Automation System")
    print("=" * 50)
    
    try:
        # Test 1: Import workflow components
        print("\n📦 Testing imports...")
        from workflow_automation import WorkflowEngine, Workflow, TriggerType
        print("✅ Workflow engine imported successfully")
        
        # Test 2: Initialize workflow engine
        print("\n🔧 Initializing workflow engine...")
        work_dir = Path.home() / 'barbossa-engineer'
        engine = WorkflowEngine(work_dir)
        print(f"✅ Workflow engine initialized in {work_dir}")
        
        # Test 3: Create a simple test workflow
        print("\n📝 Creating test workflow...")
        config = {
            'name': 'System Test Workflow',
            'description': 'Simple test workflow to verify functionality',
            'tasks': [
                {
                    'id': 'hello',
                    'name': 'Hello World',
                    'type': 'shell_command',
                    'command': 'echo "Hello from Barbossa Workflow System!"',
                    'timeout': 30
                },
                {
                    'id': 'date',
                    'name': 'Show Date',
                    'type': 'shell_command',
                    'command': 'date',
                    'dependencies': ['hello'],
                    'timeout': 30
                },
                {
                    'id': 'system_info',
                    'name': 'System Information',
                    'type': 'shell_command',
                    'command': 'uname -a',
                    'dependencies': ['date'],
                    'timeout': 30
                }
            ]
        }
        
        workflow = engine.create_workflow_from_config(config)
        print(f"✅ Test workflow created: {workflow.name}")
        print(f"   Tasks: {len(workflow.tasks)}")
        print(f"   Execution order: {workflow.execution_order}")
        
        # Test 4: Execute the workflow
        print("\n⚡ Executing test workflow...")
        
        async def run_workflow():
            result = await engine.execute_workflow(workflow, TriggerType.MANUAL)
            return result
        
        start_time = time.time()
        success = asyncio.run(run_workflow())
        duration = time.time() - start_time
        
        if success:
            print(f"✅ Workflow completed successfully in {duration:.2f} seconds")
            
            # Show task results
            print("\n📋 Task Results:")
            for task_id, task in workflow.tasks.items():
                print(f"   {task.name}: {task.status.value}")
                if task.outputs.get('stdout'):
                    output = task.outputs['stdout'].strip()
                    if output:
                        print(f"      Output: {output}")
        else:
            print(f"❌ Workflow failed after {duration:.2f} seconds")
            print(f"   Error: {workflow.error_message}")
        
        # Test 5: Check workflow storage
        print("\n💾 Testing workflow storage...")
        workflows = engine.list_workflows()
        print(f"✅ Found {len(workflows)} stored workflow(s)")
        
        # Test 6: Get workflow status
        print("\n📊 Testing workflow status retrieval...")
        status = engine.get_workflow_status(workflow.workflow_id)
        if status:
            print(f"✅ Status retrieved: {status['status']}")
        else:
            print("❌ Could not retrieve workflow status")
        
        return True
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("   Make sure all required modules are available")
        return False
    
    except Exception as e:
        print(f"❌ Error during testing: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_templates():
    """Test workflow templates"""
    print("\n📄 Testing workflow templates...")
    
    try:
        templates_dir = Path.home() / 'barbossa-engineer' / 'workflow_templates'
        
        if not templates_dir.exists():
            print("⚠️  Templates directory not found, creating...")
            templates_dir.mkdir(parents=True, exist_ok=True)
        
        template_files = list(templates_dir.glob('*.yaml'))
        print(f"✅ Found {len(template_files)} template(s):")
        
        for template_file in template_files:
            print(f"   - {template_file.name}")
        
        if len(template_files) > 0:
            print("✅ Templates are available for use")
        else:
            print("⚠️  No templates found - you can create some using the provided examples")
        
        return True
        
    except Exception as e:
        print(f"❌ Error testing templates: {e}")
        return False

def test_web_api():
    """Test if web API components are available"""
    print("\n🌐 Testing web API components...")
    
    try:
        from workflow_api import workflow_api
        print("✅ Workflow API module imported successfully")
        
        # Check if Flask app can be created (basic test)
        from flask import Flask
        test_app = Flask(__name__)
        test_app.register_blueprint(workflow_api)
        print("✅ Workflow API blueprint can be registered")
        
        return True
        
    except ImportError as e:
        print(f"⚠️  Web API components not fully available: {e}")
        print("   Web interface may not work without additional dependencies")
        return False
    
    except Exception as e:
        print(f"❌ Error testing web API: {e}")
        return False

def show_system_info():
    """Show system information"""
    print("\n🖥️  System Information:")
    
    try:
        work_dir = Path.home() / 'barbossa-engineer'
        print(f"   Work directory: {work_dir}")
        print(f"   Directory exists: {work_dir.exists()}")
        
        if work_dir.exists():
            subdirs = ['logs', 'changelogs', 'workflow_templates', 'workflows']
            for subdir in subdirs:
                path = work_dir / subdir
                exists = path.exists()
                print(f"   {subdir}/: {'✅' if exists else '❌'}")
        
        # Check database files
        db_files = ['workflows.db', 'metrics.db', 'monitoring.db']
        for db_file in db_files:
            db_path = work_dir / db_file
            exists = db_path.exists()
            size = db_path.stat().st_size if exists else 0
            print(f"   {db_file}: {'✅' if exists else '❌'} ({size} bytes)")
        
    except Exception as e:
        print(f"❌ Error getting system info: {e}")

def main():
    """Main function"""
    print(f"🕐 Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Show system information
    show_system_info()
    
    # Test basic functionality
    basic_success = test_basic_functionality()
    
    # Test templates
    template_success = test_templates()
    
    # Test web API
    web_success = test_web_api()
    
    # Summary
    print("\n" + "=" * 50)
    print("🏁 Test Summary:")
    print(f"   Basic functionality: {'✅ PASS' if basic_success else '❌ FAIL'}")
    print(f"   Templates: {'✅ PASS' if template_success else '❌ FAIL'}")
    print(f"   Web API: {'✅ PASS' if web_success else '⚠️  PARTIAL'}")
    
    overall_success = basic_success and template_success
    print(f"\n🎯 Overall Status: {'✅ READY' if overall_success else '❌ NEEDS ATTENTION'}")
    
    if overall_success:
        print("\n🎉 Barbossa Workflow Automation System is ready to use!")
        print("\nNext steps:")
        print("   1. Access web dashboard: https://your-server:8443/workflows")
        print("   2. Create workflows from templates")
        print("   3. Schedule automated tasks")
        print("   4. Monitor system performance")
    else:
        print("\n🔧 Some components need attention before full functionality is available.")
        print("   Check the error messages above for details.")
    
    return overall_success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)