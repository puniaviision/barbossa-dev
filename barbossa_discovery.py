#!/usr/bin/env python3
"""
Barbossa Discovery v5.8 - Autonomous Feature Discovery Agent
Runs 3x daily (06:00, 14:00, 22:00) to find improvements and create Issues.
Keeps the backlog fed so Engineers always have work to pick from.

Part of the Pipeline:
- Discovery (3x daily) → creates Issues in backlog  <-- THIS AGENT
- Engineer (:00) → implements from backlog, creates PRs
- Tech Lead (:35) → reviews PRs, merges or requests changes
- Auditor (daily 06:30) → system health analysis

Discovery Types:
1. Code Analysis - TODOs, FIXMEs, missing tests, accessibility gaps
2. UX Improvements - Loading states, error handling, empty states
3. Cleanup - Console.logs, dead code, inconsistencies

Prompts loaded locally from prompts/ directory.
"""

import json
import logging
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
import uuid

# Local prompt loading and optional analytics/state tracking
from barbossa_prompts import get_system_prompt
from barbossa_firebase import (
    get_client,
    check_version,
    track_run_start,
    track_run_end
)
from issue_tracker import get_issue_tracker, IssueTracker


class BarbossaDiscovery:
    """Autonomous discovery agent that creates issues for the pipeline."""

    VERSION = "1.4.0"  # Bumped for Linear support
    DEFAULT_BACKLOG_THRESHOLD = 20

    def __init__(self, work_dir: Optional[Path] = None):
        default_dir = Path(os.environ.get('BARBOSSA_DIR', '/app'))
        if not default_dir.exists():
            default_dir = Path.home() / 'barbossa-dev'

        self.work_dir = work_dir or default_dir
        self.logs_dir = self.work_dir / 'logs'
        self.projects_dir = self.work_dir / 'projects'
        self.config_file = self.work_dir / 'config' / 'repositories.json'

        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self._setup_logging()

        # Firebase client (analytics + state tracking, never blocks)
        self.firebase = get_client()

        # Soft version check - warn but never block
        update_msg = check_version()
        if update_msg:
            self.logger.info(f"UPDATE AVAILABLE: {update_msg}")

        self.config = self._load_config()
        self.repositories = self.config.get('repositories', [])
        self.owner = self.config.get('owner')
        if not self.owner:
            raise ValueError("'owner' is required in config/repositories.json")

        # Load settings from config
        settings = self.config.get('settings', {}).get('discovery', {})
        self.enabled = settings.get('enabled', True)
        self.BACKLOG_THRESHOLD = settings.get('max_backlog_issues', self.DEFAULT_BACKLOG_THRESHOLD)

        # Issue tracker type for logging
        tracker_type = self.config.get('issue_tracker', {}).get('type', 'github')

        self.logger.info("=" * 60)
        self.logger.info(f"BARBOSSA DISCOVERY v{self.VERSION}")
        self.logger.info(f"Repositories: {len(self.repositories)}")
        self.logger.info(f"Issue Tracker: {tracker_type}")
        self.logger.info(f"Settings: max_backlog_issues={self.BACKLOG_THRESHOLD}")
        self.logger.info("=" * 60)

    def _setup_logging(self):
        log_file = self.logs_dir / f"discovery_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler(sys.stdout)
            ]
        )
        self.logger = logging.getLogger('discovery')

    def _load_config(self) -> Dict:
        if self.config_file.exists():
            with open(self.config_file, 'r') as f:
                return json.load(f)
        return {'repositories': []}

    def _run_cmd(self, cmd: str, cwd: str = None, timeout: int = 60) -> Optional[str]:
        """Run a shell command and return output."""
        try:
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=cwd
            )
            if result.returncode == 0:
                return result.stdout.strip()
            return None
        except Exception as e:
            self.logger.warning(f"Command failed: {cmd} - {e}")
            return None

    def _get_issue_tracker(self, repo_name: str) -> IssueTracker:
        """Get the issue tracker for a repository."""
        return get_issue_tracker(self.config, repo_name, self.logger)

    def _get_backlog_count(self, repo_name: str) -> int:
        """Count open issues labeled 'backlog' for a repo."""
        try:
            tracker = self._get_issue_tracker(repo_name)
            return tracker.get_backlog_count(label="backlog")
        except Exception as e:
            self.logger.warning(f"Failed to get backlog count: {e}")
            return 0

    def _get_existing_issue_titles(self, repo_name: str) -> Optional[List[str]]:
        """Get titles of existing open issues to avoid duplicates.

        Returns None on failure to distinguish from empty list.
        Caller should skip issue creation if None is returned.
        """
        try:
            tracker = self._get_issue_tracker(repo_name)
            titles = tracker.get_existing_titles(limit=50)
            self.logger.info(f"Successfully fetched {len(titles)} existing titles for deduplication")
            return titles
        except Exception as e:
            self.logger.error(f"CRITICAL: Failed to get existing titles - skipping discovery to prevent duplicates: {e}")
            return None  # Return None to signal failure, not empty list

    def _create_issue(self, repo_name: str, title: str, body: str, labels: List[str] = None) -> bool:
        """Create an issue using the configured tracker."""
        labels = labels or ['backlog', 'discovery']
        try:
            tracker = self._get_issue_tracker(repo_name)
            issue = tracker.create_issue(title=title, body=body, labels=labels)
            if issue:
                self.logger.info(f"Created issue: {title}")
                self.logger.info(f"  URL: {issue.url}")
                return True
            return False
        except Exception as e:
            import traceback
            self.logger.error(f"Failed to create issue: {e}")
            # Write full traceback to file
            traceback_file = self.work_dir / 'discovery_create_issue_error.txt'
            with open(traceback_file, 'w') as f:
                f.write(f"Error creating issue: {title}\n")
                f.write(f"Labels: {labels}\n\n")
                f.write(traceback.format_exc())
            self.logger.error(f"Full traceback written to {traceback_file}")
            return False

    def _clone_or_update_repo(self, repo: Dict) -> Optional[Path]:
        """Ensure repo is cloned and up to date."""
        repo_name = repo['name']
        repo_path = self.projects_dir / repo_name

        print(f"DEBUG: Checking repo: {repo_name}")
        print(f"DEBUG: Projects dir: {self.projects_dir}")
        print(f"DEBUG: Repo path: {repo_path}")
        print(f"DEBUG: Repo exists: {repo_path.exists()}")
        self.logger.info(f"Checking repo: {repo_name} at {repo_path}")

        if repo_path.exists():
            print("DEBUG: Repo exists, pulling latest...")
            result = self._run_cmd("git fetch origin && git checkout main && git pull origin main", cwd=str(repo_path))
            print(f"DEBUG: Git pull result: {result is not None}")
        else:
            print("DEBUG: Repo doesn't exist, cloning...")
            result = self._run_cmd(f"git clone {repo['url']} {repo_name}", cwd=str(self.projects_dir))
            print(f"DEBUG: Git clone result: {result is not None}")

        print(f"DEBUG: After git operation, repo exists: {repo_path.exists()}")
        if repo_path.exists():
            print(f"DEBUG: Returning repo path: {repo_path}")
            return repo_path

        print(f"DEBUG: Repo path doesn't exist after clone/update: {repo_path}")
        return None

    def _analyze_todos(self, repo_path: Path) -> List[Dict]:
        """Find TODO, FIXME, HACK, XXX comments."""
        findings = []
        patterns = ['TODO', 'FIXME', 'HACK', 'XXX']

        for pattern in patterns:
            result = self._run_cmd(
                f"grep -rn '{pattern}' --include='*.ts' --include='*.tsx' --include='*.js' --include='*.jsx' --include='*.swift' --include='*.m' --include='*.h' --exclude-dir=node_modules --exclude-dir=.next --exclude-dir=dist --exclude-dir=Pods --exclude-dir=build . | head -20",
                cwd=str(repo_path)
            )
            if result:
                for line in result.split('\n')[:5]:  # Limit to 5 per pattern
                    if line.strip():
                        # Parse grep output: file:linenum:content
                        parts = line.split(':', 2)
                        if len(parts) >= 3:
                            file_path = parts[0]
                            line_num = parts[1]
                            comment_text = parts[2].strip()

                            # Skip feature requests (look for implementation keywords)
                            feature_keywords = ['implement', 'add feature', 'build', 'create feature', 'new feature']
                            is_feature_request = any(keyword in comment_text.lower() for keyword in feature_keywords)

                            if is_feature_request:
                                self.logger.debug(f"Skipping feature-request TODO: {comment_text}")
                                continue

                            findings.append({
                                'type': 'todo',
                                'pattern': pattern,
                                'location': f"{file_path}:{line_num}",
                                'file': file_path,
                                'line': line_num,
                                'comment': comment_text,
                                'content': line
                            })

        return findings[:10]  # Max 10 findings

    def _analyze_missing_loading_states(self, repo_path: Path) -> List[Dict]:
        """Find components that fetch data but have no loading state."""
        findings = []

        # Find files with fetch/useQuery but no loading/isLoading
        result = self._run_cmd(
            "grep -rl 'useQuery\\|useFetch\\|fetch(' --include='*.tsx' --exclude-dir=node_modules --exclude-dir=.next . | head -10",
            cwd=str(repo_path)
        )

        if result:
            for file in result.split('\n'):
                if not file.strip():
                    continue
                # Check if file has loading state handling
                has_loading = self._run_cmd(
                    f"grep -l 'isLoading\\|loading\\|Skeleton\\|Spinner' '{file}'",
                    cwd=str(repo_path)
                )
                if not has_loading:
                    findings.append({
                        'type': 'missing_loading',
                        'file': file,
                        'suggestion': 'Add loading skeleton or spinner'
                    })

        return findings[:5]

    def _analyze_missing_error_handling(self, repo_path: Path) -> List[Dict]:
        """Find components that fetch data but have no error handling."""
        findings = []

        result = self._run_cmd(
            "grep -rl 'useQuery\\|useFetch\\|fetch(' --include='*.tsx' --exclude-dir=node_modules --exclude-dir=.next . | head -10",
            cwd=str(repo_path)
        )

        if result:
            for file in result.split('\n'):
                if not file.strip():
                    continue
                has_error = self._run_cmd(
                    f"grep -l 'isError\\|error\\|catch\\|ErrorBoundary' '{file}'",
                    cwd=str(repo_path)
                )
                if not has_error:
                    findings.append({
                        'type': 'missing_error_handling',
                        'file': file,
                        'suggestion': 'Add error state handling'
                    })

        return findings[:5]

    def _analyze_accessibility(self, repo_path: Path) -> List[Dict]:
        """Find accessibility issues - missing alt, aria labels, etc."""
        findings = []

        # Images without alt
        result = self._run_cmd(
            "grep -rn '<img' --include='*.tsx' --include='*.jsx' --exclude-dir=node_modules --exclude-dir=.next . | grep -v 'alt=' | head -5",
            cwd=str(repo_path)
        )
        if result:
            for line in result.split('\n'):
                if line.strip():
                    findings.append({
                        'type': 'a11y',
                        'issue': 'Image missing alt attribute',
                        'location': line.split(':')[0]
                    })

        # Buttons without aria-label (icon buttons)
        result = self._run_cmd(
            "grep -rn '<button' --include='*.tsx' --exclude-dir=node_modules --exclude-dir=.next . | grep -v 'aria-label' | grep -v '>' | head -5",
            cwd=str(repo_path)
        )
        if result:
            for line in result.split('\n'):
                if line.strip() and 'Icon' in line:
                    findings.append({
                        'type': 'a11y',
                        'issue': 'Icon button missing aria-label',
                        'location': line.split(':')[0]
                    })

        return findings[:5]

    def _analyze_console_logs(self, repo_path: Path) -> List[Dict]:
        """Find console.log/print statements that should be replaced with proper logging."""
        findings = []

        # Check for JavaScript console.log
        js_result = self._run_cmd(
            "grep -rn 'console\\.log' --include='*.ts' --include='*.tsx' --include='*.js' --include='*.jsx' --exclude-dir=node_modules --exclude-dir=.next --exclude-dir=dist . | grep -v '.test.' | head -10",
            cwd=str(repo_path)
        )

        # Check for Swift print statements
        swift_result = self._run_cmd(
            "grep -rn 'print(' --include='*.swift' --exclude-dir=Pods --exclude-dir=build . | grep -v 'Tests.swift' | head -10",
            cwd=str(repo_path)
        )

        # Parse each line to extract file, line number, and actual statement
        if js_result:
            for line in js_result.split('\n'):
                if line.strip():
                    parts = line.split(':', 2)
                    if len(parts) >= 3:
                        findings.append({
                            'type': 'cleanup',
                            'language': 'javascript',
                            'file': parts[0],
                            'line': parts[1],
                            'statement': parts[2].strip()
                        })

        if swift_result:
            for line in swift_result.split('\n'):
                if line.strip():
                    parts = line.split(':', 2)
                    if len(parts) >= 3:
                        findings.append({
                            'type': 'cleanup',
                            'language': 'swift',
                            'file': parts[0],
                            'line': parts[1],
                            'statement': parts[2].strip()
                        })

        return findings[:10]  # Max 10 statements

    def _generate_issue_from_findings(self, repo_name: str, findings: List[Dict], category: str) -> Optional[Dict]:
        """Generate a GitHub Issue from findings."""
        if not findings:
            return None

        if category == 'todo':
            title = f"fix: address {len(findings)} TODO/FIXME comments"
            body = """## Summary
Found TODO/FIXME/HACK comments that should be addressed.

## Findings
"""
            for f in findings:
                body += f"\n**{f['location']}**\n"
                body += f"```\n{f['comment']}\n```\n"

            body += """
## Acceptance Criteria
- [ ] Review each TODO/FIXME comment above
- [ ] Implement the fix or refactoring needed
- [ ] If no longer relevant, remove the comment
- [ ] Run build and tests to verify

## Notes
- Some TODOs may be related and can be addressed together
- If a TODO requires significant work, consider breaking into a separate feature ticket
- Update documentation if the TODO involves architectural changes

---
*Created by Barbossa Discovery Agent*
"""

        elif category == 'loading':
            title = f"feat: add loading states to {len(findings)} components"
            body = """## Summary
Found components that fetch data but don't show loading states.

## Files Missing Loading States
"""
            for f in findings:
                body += f"- `{f['file']}`\n"

            body += """
## Acceptance Criteria
- [ ] Add loading skeletons or spinners to each component
- [ ] Match existing loading patterns in codebase
- [ ] Test loading state appears before data loads

---
*Created by Barbossa Discovery Agent*
"""

        elif category == 'error':
            title = f"feat: add error handling to {len(findings)} components"
            body = """## Summary
Found components that fetch data but don't handle errors gracefully.

## Files Missing Error Handling
"""
            for f in findings:
                body += f"- `{f['file']}`\n"

            body += """
## Acceptance Criteria
- [ ] Add error state UI to each component
- [ ] Show user-friendly error message
- [ ] Add retry functionality where appropriate

---
*Created by Barbossa Discovery Agent*
"""

        elif category == 'a11y':
            title = f"a11y: fix {len(findings)} accessibility issues"
            body = """## Summary
Found accessibility issues that should be fixed for better UX.

## Issues Found
"""
            for f in findings:
                body += f"- `{f['location']}`: {f['issue']}\n"

            body += """
## Acceptance Criteria
- [ ] Add missing alt attributes to images
- [ ] Add aria-labels to icon buttons
- [ ] Run accessibility audit to verify fixes

---
*Created by Barbossa Discovery Agent*
"""

        elif category == 'cleanup':
            # Group findings by language
            swift_statements = [f for f in findings if f.get('language') == 'swift']
            js_statements = [f for f in findings if f.get('language') == 'javascript']

            title = "refactor: replace debug print statements with proper logging"
            body = """## Summary
Found debug print/console.log statements in production code. These should be replaced with proper logging frameworks for better control and observability in production.

"""
            if swift_statements:
                body += f"## Swift print() statements ({len(swift_statements)} found)\n\n"
                body += "Replace with `os.log` or structured logging framework:\n\n"
                for f in swift_statements[:10]:
                    body += f"**{f['file']}:{f['line']}**\n"
                    body += f"```swift\n{f['statement']}\n```\n\n"

                body += """**Recommended approach for Swift:**
```swift
import os.log

// Define logger
private let logger = Logger(subsystem: Bundle.main.bundleIdentifier ?? "app", category: "YourCategory")

// Replace print() with:
logger.error("Failed to load profile: \\(error)")
logger.info("Credits added successfully. New balance: \\(newBalance)")
```

"""

            if js_statements:
                body += f"## JavaScript console.log statements ({len(js_statements)} found)\n\n"
                body += "Replace with proper logging framework (e.g., winston, pino):\n\n"
                for f in js_statements[:10]:
                    body += f"**{f['file']}:{f['line']}**\n"
                    body += f"```javascript\n{f['statement']}\n```\n\n"

            body += """## Acceptance Criteria
- [ ] Replace print()/console.log with appropriate logging framework
- [ ] Use correct log levels (error, warning, info, debug)
- [ ] Verify logging works in production builds
- [ ] Remove or disable debug-only logs for production
- [ ] Test that critical errors are still visible

## Notes
- DO NOT simply remove these statements - many are error logging
- Error logs should be preserved with proper logging framework
- Use log levels to control verbosity in production vs development

---
*Created by Barbossa Discovery Agent*
"""

        else:
            return None

        return {'title': title, 'body': body}

    def discover_for_repo(self, repo: Dict) -> int:
        """Run discovery for a single repository. Returns number of issues created."""
        repo_name = repo['name']
        print(f"DEBUG: discover_for_repo called for {repo_name}")
        self.logger.info(f"\n{'='*60}")
        self.logger.info(f"DISCOVERING: {repo_name}")
        self.logger.info(f"{'='*60}")

        # Check backlog size
        backlog_count = self._get_backlog_count(repo_name)
        print(f"DEBUG: backlog_count = {backlog_count}, threshold = {self.BACKLOG_THRESHOLD}")
        self.logger.info(f"Current backlog: {backlog_count} issues")

        if backlog_count >= self.BACKLOG_THRESHOLD:
            print(f"DEBUG: Backlog full, exiting early")
            self.logger.info(f"Backlog full (>= {self.BACKLOG_THRESHOLD}), skipping discovery")
            return 0

        print(f"DEBUG: Calling _clone_or_update_repo...")
        # Clone/update repo
        repo_path = self._clone_or_update_repo(repo)
        print(f"DEBUG: _clone_or_update_repo returned: {repo_path}")
        if not repo_path:
            self.logger.error(f"Could not access repo: {repo_name}")
            return 0

        print(f"DEBUG: Repo path is valid, continuing with analyses...")
        self.logger.info(f"Repo path: {repo_path}, exists: {repo_path.exists()}")

        try:
            # Get existing issues to avoid duplicates
            # CRITICAL: If this fails, skip discovery entirely to prevent duplicates
            existing_titles = self._get_existing_issue_titles(repo_name)
            if existing_titles is None:
                self.logger.error("Aborting discovery - cannot verify duplicates without existing titles")
                return 0
            self.logger.info(f"Fetched {len(existing_titles)} existing issue titles")

            issues_created = 0
            issues_needed = self.BACKLOG_THRESHOLD - backlog_count

            self.logger.info(f"Running {len(['todo', 'loading', 'error', 'a11y', 'cleanup'])} analyses, need {issues_needed} issues")

            # Run analyses with individual exception handling
            analyses = []

            try:
                self.logger.info("Starting TODO analysis...")
                todo_findings = self._analyze_todos(repo_path)
                analyses.append(('todo', todo_findings))
                self.logger.info(f"TODO analysis complete: {len(todo_findings) if todo_findings else 0} findings")
            except Exception as e:
                self.logger.error(f"TODO analysis failed: {e}")
                import traceback
                self.logger.error(traceback.format_exc())

            try:
                self.logger.info("Starting loading state analysis...")
                loading_findings = self._analyze_missing_loading_states(repo_path)
                analyses.append(('loading', loading_findings))
                self.logger.info(f"Loading analysis complete: {len(loading_findings) if loading_findings else 0} findings")
            except Exception as e:
                self.logger.error(f"Loading analysis failed: {e}")
                import traceback
                self.logger.error(traceback.format_exc())

            try:
                self.logger.info("Starting error handling analysis...")
                error_findings = self._analyze_missing_error_handling(repo_path)
                analyses.append(('error', error_findings))
                self.logger.info(f"Error analysis complete: {len(error_findings) if error_findings else 0} findings")
            except Exception as e:
                self.logger.error(f"Error analysis failed: {e}")
                import traceback
                self.logger.error(traceback.format_exc())

            try:
                self.logger.info("Starting accessibility analysis...")
                a11y_findings = self._analyze_accessibility(repo_path)
                analyses.append(('a11y', a11y_findings))
                self.logger.info(f"A11y analysis complete: {len(a11y_findings) if a11y_findings else 0} findings")
            except Exception as e:
                self.logger.error(f"A11y analysis failed: {e}")
                import traceback
                self.logger.error(traceback.format_exc())

            try:
                self.logger.info("Starting console.log/print analysis...")
                cleanup_findings = self._analyze_console_logs(repo_path)
                analyses.append(('cleanup', cleanup_findings))
                self.logger.info(f"Cleanup analysis complete: {len(cleanup_findings) if cleanup_findings else 0} findings")
            except Exception as e:
                self.logger.error(f"Cleanup analysis failed: {e}")
                import traceback
                self.logger.error(traceback.format_exc())

            self.logger.info(f"All analyses complete, processing {len(analyses)} results")

            for category, findings in analyses:
                self.logger.info(f"Processing '{category}': {len(findings) if findings else 0} findings")

                if issues_created >= issues_needed:
                    self.logger.info(f"Reached issue limit ({issues_needed}), stopping")
                    break

                if not findings:
                    self.logger.info(f"No findings for '{category}', skipping")
                    continue

                try:
                    self.logger.info(f"Generating issue for '{category}' findings...")
                    issue = self._generate_issue_from_findings(repo_name, findings, category)
                    if not issue:
                        self.logger.warning(f"Failed to generate issue for '{category}'")
                        continue

                    # Check for duplicate with normalized comparison
                    normalized_title = issue['title'].lower().strip()
                    is_duplicate = any(
                        normalized_title == existing.strip()
                        for existing in existing_titles
                    )
                    if is_duplicate:
                        self.logger.info(f"Skipping duplicate issue: '{issue['title']}'")
                        continue

                    # Also check for similar titles (fuzzy match for refactor issues)
                    if category == 'cleanup':
                        similar_exists = any(
                            'replace debug print' in existing or
                            'console.log' in existing or
                            'proper logging' in existing
                            for existing in existing_titles
                        )
                        if similar_exists:
                            self.logger.info(f"Skipping similar cleanup issue: '{issue['title']}'")
                            continue

                    # Create the issue
                    self.logger.info(f"Creating issue: {issue['title']}")
                    if self._create_issue(repo_name, issue['title'], issue['body']):
                        issues_created += 1
                        existing_titles.append(issue['title'].lower())
                        self.logger.info(f"Successfully created issue {issues_created}/{issues_needed}")
                    else:
                        self.logger.warning(f"Failed to create issue: {issue['title']}")
                except Exception as e:
                    self.logger.error(f"Error processing findings for '{category}': {e}")
                    import traceback
                    self.logger.error(traceback.format_exc())

            self.logger.info(f"Created {issues_created} issues for {repo_name}")
            return issues_created

        except Exception as e:
            import traceback
            self.logger.error(f"Error in discover_for_repo for {repo_name}: {e}")
            error_file = self.work_dir / f'discovery_error_{repo_name}.txt'
            with open(error_file, 'w') as f:
                f.write(traceback.format_exc())
            self.logger.error(f"Full traceback written to {error_file}")
            return 0

    def _generate_session_id(self) -> str:
        """Generate unique session ID"""
        return datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + str(uuid.uuid4())[:8]

    def run(self):
        """Run discovery for all repositories."""
        run_session_id = self._generate_session_id()

        if not self.enabled:
            self.logger.info("Discovery is disabled in config. Skipping.")
            return 0

        self.logger.info(f"\n{'#'*60}")
        self.logger.info("BARBOSSA DISCOVERY RUN")
        self.logger.info(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.logger.info(f"{'#'*60}\n")

        # Track run start (fire-and-forget, never blocks)
        track_run_start("discovery", run_session_id, len(self.repositories))

        total_issues = 0
        for repo in self.repositories:
            try:
                issues = self.discover_for_repo(repo)
                total_issues += issues
            except Exception as e:
                self.logger.error(f"Error discovering for {repo['name']}: {e}")

        self.logger.info(f"\n{'#'*60}")
        self.logger.info(f"DISCOVERY COMPLETE: {total_issues} issues created")
        self.logger.info(f"{'#'*60}\n")

        # Track run end (fire-and-forget)
        track_run_end("discovery", run_session_id, success=True, pr_created=False)

        return total_issues


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Barbossa Discovery Agent')
    parser.add_argument('--repo', help='Run for specific repo only')
    args = parser.parse_args()

    discovery = BarbossaDiscovery()

    if args.repo:
        repo = next((r for r in discovery.repositories if r['name'] == args.repo), None)
        if repo:
            discovery.discover_for_repo(repo)
        else:
            print(f"Repo not found: {args.repo}")
    else:
        discovery.run()


if __name__ == "__main__":
    main()
