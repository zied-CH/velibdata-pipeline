"""Execute dbt run et dbt test pour Azure Functions."""
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)
DBT_PROJECT_DIR = Path(__file__).parent / "dbt_project"


def _setup_dbt_env():
    """Configure l environnement dbt pour Azure Functions."""
    os.environ["DBT_SEND_ANONYMOUS_USAGE_STATS"] = "False"
    os.environ["DO_NOT_TRACK"] = "1"
    os.environ["DBT_LOG_PATH"] = "/tmp/dbt_logs"
    os.environ["DBT_TARGET_PATH"] = "/tmp/dbt_target"


def _invoke_dbt(command: str) -> dict:
    """Helper generique pour invoquer une commande dbt (run, test, etc.)."""
    _setup_dbt_env()

    diagnostics = {
        "dbt_project_dir": str(DBT_PROJECT_DIR),
        "dbt_project_exists": DBT_PROJECT_DIR.exists(),
        "command": command,
    }

    if not DBT_PROJECT_DIR.exists():
        raise FileNotFoundError(f"Projet dbt introuvable : {DBT_PROJECT_DIR}")

    from dbt.cli.main import dbtRunner

    runner = dbtRunner()
    args = [
        "--no-send-anonymous-usage-stats",
        "--no-partial-parse",
        "--log-path", "/tmp/dbt_logs",
        command,
        "--project-dir", str(DBT_PROJECT_DIR),
        "--profiles-dir", str(DBT_PROJECT_DIR),
        "--target-path", "/tmp/dbt_target",
        "--no-use-colors",
    ]

    try:
        result = runner.invoke(args)
    except Exception as e:
        msg = str(e)
        diagnostics["exception"] = msg[:500]
        raise RuntimeError(f"dbt {command} failed: {msg[:300]}")

    if hasattr(result, 'success') and not result.success:
        exc = getattr(result, 'exception', None)
        msg = str(exc) if exc else f"dbt {command} failed"
        diagnostics["dbt_exception"] = msg[:500]
        # Pour les tests, on ne raise pas si juste des tests echouent
        if command != "test":
            raise RuntimeError(f"dbt {command} failed: {msg[:300]}")

    nodes_executed = 0
    nodes_passed = 0
    nodes_failed = 0
    statuses = []

    if hasattr(result, 'result') and result.result is not None:
        for r in result.result.results:
            nodes_executed += 1
            statuses.append(f"{r.node.name}={r.status}")
            if r.status in ("success", "pass"):
                nodes_passed += 1
            else:
                nodes_failed += 1

    diagnostics["statuses"] = statuses
    return {
        "nodes_executed": nodes_executed,
        "nodes_passed": nodes_passed,
        "nodes_failed": nodes_failed,
        "diagnostics": diagnostics,
    }


def run_dbt_transformations() -> dict:
    """Execute dbt run (transformations Bronze -> Silver -> Gold)."""
    logger.info("dbt_run_start")
    result = _invoke_dbt("run")
    result["models_executed"] = result["nodes_passed"]
    return result


def run_dbt_tests() -> dict:
    """Execute dbt test (validation des donnees)."""
    logger.info("dbt_test_start")
    return _invoke_dbt("test")
