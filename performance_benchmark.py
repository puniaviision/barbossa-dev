#!/usr/bin/env python3
"""
Performance Benchmark Suite for Barbossa Enhanced System
Tests all optimized components and measures performance improvements
"""

import asyncio
import json
import os
import platform
import psutil
import sqlite3
import subprocess
import sys
import time
import threading
import concurrent.futures
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any
import statistics
import requests

# Add project root to path
sys.path.append(str(Path(__file__).parent))

from barbossa import BarbossaEnhanced, PerformanceProfiler
from server_manager import BarbossaServerManager, MetricsCollector
from security_guard import security_guard


class PerformanceBenchmark:
    """Comprehensive performance testing suite"""
    
    def __init__(self):
        self.work_dir = Path(__file__).parent
        self.results = {
            'timestamp': datetime.now().isoformat(),
            'tests': {},
            'summary': {},
            'hardware': self._get_hardware_info()
        }
        
    def _get_hardware_info(self) -> Dict:
        """Get hardware information for benchmark context"""
        return {
            'cpu_count': os.cpu_count(),
            'memory_total_gb': psutil.virtual_memory().total / (1024**3),
            'disk_total_gb': psutil.disk_usage('/').total / (1024**3),
            'platform': platform.platform()
        }
    
    def benchmark_metrics_collector(self, iterations: int = 100) -> Dict:
        """Benchmark metrics collection performance"""
        print(f"Benchmarking MetricsCollector ({iterations} iterations)...")
        
        db_path = self.work_dir / 'test_metrics.db'
        if db_path.exists():
            db_path.unlink()
        
        collector = MetricsCollector(db_path)
        
        # Warmup
        for _ in range(10):
            collector.collect_metrics()
        
        # Benchmark collection
        times = []
        memory_usage = []
        
        for i in range(iterations):
            start_time = time.time()
            process = psutil.Process()
            start_memory = process.memory_info().rss / 1024 / 1024
            
            metrics = collector.collect_metrics()
            collector.store_metrics(metrics)
            
            end_time = time.time()
            end_memory = process.memory_info().rss / 1024 / 1024
            
            times.append(end_time - start_time)
            memory_usage.append(end_memory - start_memory)
            
            if i % 20 == 0:
                print(f"  Progress: {i}/{iterations}")
        
        # Force flush any buffered metrics
        if hasattr(collector, '_flush_metrics_buffer'):
            collector._flush_metrics_buffer()
        
        # Cleanup
        if db_path.exists():
            db_path.unlink()
        
        return {
            'avg_time_ms': statistics.mean(times) * 1000,
            'min_time_ms': min(times) * 1000,
            'max_time_ms': max(times) * 1000,
            'p95_time_ms': statistics.quantiles(times, n=20)[18] * 1000,
            'avg_memory_mb': statistics.mean(memory_usage),
            'total_iterations': iterations
        }
    
    def benchmark_database_operations(self, batch_sizes: List[int] = [1, 10, 50, 100]) -> Dict:
        """Benchmark database batch operation performance"""
        print("Benchmarking database operations...")
        
        results = {}
        db_path = self.work_dir / 'test_db_bench.db'
        
        for batch_size in batch_sizes:
            print(f"  Testing batch size: {batch_size}")
            
            if db_path.exists():
                db_path.unlink()
            
            collector = MetricsCollector(db_path)
            
            # Generate test metrics
            test_metrics = []
            for i in range(batch_size):
                test_metrics.append({
                    'cpu_percent': 50.0 + i,
                    'memory_percent': 60.0 + i,
                    'memory_used_mb': 1000 + i,
                    'memory_total_mb': 8000,
                    'disk_percent': 30.0,
                    'disk_used_gb': 100.0,
                    'disk_total_gb': 500.0,
                    'network_sent_mb': 10.0,
                    'network_recv_mb': 15.0,
                    'load_1min': 1.0,
                    'load_5min': 1.5,
                    'load_15min': 2.0,
                    'process_count': 200,
                    'docker_containers': 5,
                    'temperature': 45.0
                })
            
            # Benchmark batch insert
            start_time = time.time()
            
            if batch_size == 1:
                for metrics in test_metrics:
                    collector.store_metrics(metrics)
            else:
                collector.store_metrics_batch(test_metrics)
            
            end_time = time.time()
            
            results[f'batch_{batch_size}'] = {
                'time_ms': (end_time - start_time) * 1000,
                'records_per_second': batch_size / (end_time - start_time),
                'time_per_record_ms': ((end_time - start_time) / batch_size) * 1000
            }
            
            # Cleanup
            if db_path.exists():
                db_path.unlink()
        
        return results
    
    def benchmark_caching_performance(self, cache_sizes: List[int] = [10, 50, 100, 500]) -> Dict:
        """Benchmark caching system performance"""
        print("Benchmarking caching performance...")
        
        results = {}
        barbossa = BarbossaEnhanced()
        
        for cache_size in cache_sizes:
            print(f"  Testing cache size: {cache_size}")
            
            # Clear existing cache
            barbossa._cache.clear()
            barbossa._cache_expiry.clear()
            
            # Fill cache
            fill_start = time.time()
            for i in range(cache_size):
                key = f"test_key_{i}"
                value = {"data": f"test_value_{i}", "number": i, "timestamp": time.time()}
                barbossa._set_cache(key, value, ttl=300)
            fill_time = time.time() - fill_start
            
            # Benchmark cache hits
            hit_times = []
            for i in range(min(cache_size, 100)):  # Test up to 100 cache hits
                key = f"test_key_{i}"
                start_time = time.time()
                result = barbossa._get_cached(key)
                end_time = time.time()
                hit_times.append(end_time - start_time)
                assert result is not None, f"Cache miss for key {key}"
            
            # Benchmark cache misses
            miss_times = []
            for i in range(50):  # Test 50 cache misses
                key = f"nonexistent_key_{i}"
                start_time = time.time()
                result = barbossa._get_cached(key)
                end_time = time.time()
                miss_times.append(end_time - start_time)
                assert result is None, f"Unexpected cache hit for key {key}"
            
            results[f'size_{cache_size}'] = {
                'fill_time_ms': fill_time * 1000,
                'avg_hit_time_us': statistics.mean(hit_times) * 1_000_000,
                'avg_miss_time_us': statistics.mean(miss_times) * 1_000_000,
                'cache_entries': len(barbossa._cache)
            }
        
        return results
    
    def benchmark_web_portal_apis(self, base_url: str = "https://localhost:8443") -> Dict:
        """Benchmark web portal API performance"""
        print("Benchmarking web portal APIs...")
        
        # Skip if portal is not running
        try:
            response = requests.get(f"{base_url}/health", verify=False, timeout=5)
            if response.status_code != 200:
                return {"error": "Web portal not available"}
        except:
            return {"error": "Web portal not accessible"}
        
        endpoints = [
            "/api/status",
            "/api/barbossa-status", 
            "/api/services",
            "/api/logs/recent",
            "/api/changelogs"
        ]
        
        results = {}
        session = requests.Session()
        session.verify = False
        session.auth = ("admin", "Galleon6242")  # Default credentials
        
        for endpoint in endpoints:
            print(f"  Testing endpoint: {endpoint}")
            
            times = []
            response_sizes = []
            
            # Test each endpoint 10 times
            for _ in range(10):
                start_time = time.time()
                try:
                    response = session.get(f"{base_url}{endpoint}", timeout=10)
                    end_time = time.time()
                    
                    if response.status_code == 200:
                        times.append(end_time - start_time)
                        response_sizes.append(len(response.content))
                    else:
                        print(f"    Warning: {endpoint} returned status {response.status_code}")
                except Exception as e:
                    print(f"    Error testing {endpoint}: {e}")
            
            if times:
                results[endpoint.replace('/', '_')] = {
                    'avg_response_time_ms': statistics.mean(times) * 1000,
                    'min_response_time_ms': min(times) * 1000,
                    'max_response_time_ms': max(times) * 1000,
                    'avg_response_size_kb': statistics.mean(response_sizes) / 1024,
                    'success_rate': len(times) / 10
                }
            else:
                results[endpoint.replace('/', '_')] = {"error": "No successful responses"}
        
        return results
    
    def benchmark_concurrent_operations(self, max_workers: int = 5) -> Dict:
        """Benchmark concurrent operation performance"""
        print(f"Benchmarking concurrent operations ({max_workers} workers)...")
        
        db_path = self.work_dir / 'test_concurrent.db'
        if db_path.exists():
            db_path.unlink()
        
        collector = MetricsCollector(db_path)
        
        def worker_task(worker_id: int, iterations: int = 20):
            """Task for each worker thread"""
            times = []
            for i in range(iterations):
                start_time = time.time()
                metrics = collector.collect_metrics()
                collector.store_metrics(metrics)
                end_time = time.time()
                times.append(end_time - start_time)
            return {
                'worker_id': worker_id,
                'avg_time_ms': statistics.mean(times) * 1000,
                'total_operations': iterations
            }
        
        # Run concurrent workers
        start_time = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [
                executor.submit(worker_task, i, 20) 
                for i in range(max_workers)
            ]
            worker_results = [future.result() for future in concurrent.futures.as_completed(futures)]
        
        total_time = time.time() - start_time
        
        # Force flush metrics
        if hasattr(collector, '_flush_metrics_buffer'):
            collector._flush_metrics_buffer()
        
        # Get total operations count
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM system_metrics")
            total_records = cursor.fetchone()[0]
        
        # Cleanup
        if db_path.exists():
            db_path.unlink()
        
        return {
            'total_time_seconds': total_time,
            'total_operations': sum(w['total_operations'] for w in worker_results),
            'operations_per_second': sum(w['total_operations'] for w in worker_results) / total_time,
            'total_db_records': total_records,
            'worker_results': worker_results,
            'avg_worker_time_ms': statistics.mean(w['avg_time_ms'] for w in worker_results)
        }
    
    def benchmark_memory_efficiency(self, duration_seconds: int = 60) -> Dict:
        """Benchmark memory usage and efficiency"""
        print(f"Benchmarking memory efficiency ({duration_seconds}s)...")
        
        process = psutil.Process()
        barbossa = BarbossaEnhanced()
        
        memory_samples = []
        start_memory = process.memory_info().rss / 1024 / 1024  # MB
        start_time = time.time()
        
        operations = 0
        while time.time() - start_time < duration_seconds:
            # Simulate typical operations
            barbossa.perform_system_health_check()
            barbossa.get_comprehensive_status()
            
            # Add some cache entries
            for i in range(5):
                barbossa._set_cache(f"temp_{operations}_{i}", {"data": f"value_{i}"}, ttl=30)
            
            operations += 1
            
            # Sample memory every 5 seconds
            if operations % 50 == 0:  
                current_memory = process.memory_info().rss / 1024 / 1024
                memory_samples.append(current_memory)
                print(f"  Memory: {current_memory:.1f} MB, Operations: {operations}")
        
        end_memory = process.memory_info().rss / 1024 / 1024
        
        return {
            'start_memory_mb': start_memory,
            'end_memory_mb': end_memory,
            'memory_growth_mb': end_memory - start_memory,
            'peak_memory_mb': max(memory_samples) if memory_samples else end_memory,
            'avg_memory_mb': statistics.mean(memory_samples) if memory_samples else end_memory,
            'total_operations': operations,
            'operations_per_second': operations / duration_seconds,
            'memory_per_operation_kb': (end_memory - start_memory) * 1024 / operations if operations > 0 else 0
        }
    
    def run_all_benchmarks(self) -> Dict:
        """Run all performance benchmarks"""
        print("=" * 60)
        print("BARBOSSA ENHANCED PERFORMANCE BENCHMARK SUITE")
        print("=" * 60)
        
        # Run all benchmarks
        self.results['tests']['metrics_collector'] = self.benchmark_metrics_collector()
        self.results['tests']['database_operations'] = self.benchmark_database_operations()
        self.results['tests']['caching_performance'] = self.benchmark_caching_performance()
        self.results['tests']['web_portal_apis'] = self.benchmark_web_portal_apis()
        self.results['tests']['concurrent_operations'] = self.benchmark_concurrent_operations()
        self.results['tests']['memory_efficiency'] = self.benchmark_memory_efficiency()
        
        # Generate summary
        self.results['summary'] = {
            'total_tests': len(self.results['tests']),
            'metrics_avg_time_ms': self.results['tests']['metrics_collector']['avg_time_ms'],
            'cache_performance_rating': 'good' if self.results['tests']['caching_performance']['size_100']['avg_hit_time_us'] < 100 else 'needs_improvement',
            'memory_efficiency_rating': 'good' if self.results['tests']['memory_efficiency']['memory_per_operation_kb'] < 10 else 'needs_improvement',
            'concurrent_ops_per_sec': self.results['tests']['concurrent_operations']['operations_per_second']
        }
        
        # Save results
        results_file = self.work_dir / 'performance_benchmark_results.json'
        with open(results_file, 'w') as f:
            json.dump(self.results, f, indent=2)
        
        print("\n" + "=" * 60)
        print("BENCHMARK RESULTS SUMMARY")
        print("=" * 60)
        print(f"Metrics Collection Avg Time: {self.results['tests']['metrics_collector']['avg_time_ms']:.2f} ms")
        print(f"Cache Hit Time: {self.results['tests']['caching_performance']['size_100']['avg_hit_time_us']:.2f} μs")
        print(f"Concurrent Operations/sec: {self.results['tests']['concurrent_operations']['operations_per_second']:.1f}")
        print(f"Memory per Operation: {self.results['tests']['memory_efficiency']['memory_per_operation_kb']:.2f} KB")
        print(f"Results saved to: {results_file}")
        print("=" * 60)
        
        return self.results


def main():
    """Run performance benchmarks"""
    if len(sys.argv) > 1:
        if sys.argv[1] == '--quick':
            print("Running quick benchmark suite...")
            benchmark = PerformanceBenchmark()
            results = {}
            results['metrics_collector'] = benchmark.benchmark_metrics_collector(50)
            results['caching_performance'] = benchmark.benchmark_caching_performance([50, 100])
            results['database_operations'] = benchmark.benchmark_database_operations([1, 10, 50])
            print("\nQuick Benchmark Results:")
            print(json.dumps(results, indent=2))
        else:
            print("Usage: python performance_benchmark.py [--quick]")
    else:
        # Run full benchmark suite
        benchmark = PerformanceBenchmark()
        results = benchmark.run_all_benchmarks()


if __name__ == "__main__":
    main()