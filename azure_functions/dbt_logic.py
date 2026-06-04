"""Execute dbt run pour Azure Functions."""
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)
DBT_PROJECT_DIR = Path(__file__).parent / "dbt_project"


def run_dbt_transformations() -> dict:
    logger.info("dbt_run_start")

    # Desactive le tracking dbt qui utilise protobuf (source du bug)
    os.environ["DBT_SEND_ANONYMOUS_USAGE_STATS"] = "False"
    os.environ["DO_NOT_TRACK"] = "1"

    diagnostics = {
        "dbt_project_dir": str(DBT_PROJECT_DIR),
        "dbt_project_exists": DBT_PROJECT_DIR.exists(),
    }

    if not DBT_PROJECT_DIR.exists():
        raise FileNotFoundError(f"Projet dbt introuvable : {DBT_PROJECT_DIR}")

    from dbt.cli.main import dbtRunner

    runner = dbtRunner()
    args = [
        "--no-send-anonymous-usage-stats",
        "run",
        "--project-dir", str(DBT_PROJECT_DIR),
        "--profiles-dir", str(DBT_PROJECT_DIR),
        "--no-use-colors",
    ]

    try:
        result = runner.invoke(args)
    except Exception as e:
        msg = str(e)
        diagnostics["exception"] = msg[:500]
        if "MessageToJson" in msg or "always_print_fields" in msg:
            return {"models_executed": -1, "diagnostics": diagnostics, "note": "logging error"}
        raise RuntimeError(f"dbt failed: {msg[:300]}")

    if hasattr(result, 'success') and not result.success:
        exc = getattr(result, 'exception', None)
        msg = str(exc) if exc else "dbt failed"
        diagnostics["dbt_exception"] = msg[:500]
        if "MessageToJson" in msg or "always_print_fields" in msg:
            models_executed = 0
            model_statuses = []
            if result.result is not None:
                for r in result.result.results:
                    model_statuses.append(f"{r.node.name}={r.status}")
                    if r.status == "success":
                        models_executed += 1
            diagnostics["model_statuses"] = model_statuses
            return {"models_executed": models_executed, "diagnostics": diagnostics}
        raise RuntimeError(f"dbt failed: {msg[:300]} | diag: {diagnostics}")

    models_executed = 0
    model_statuses = []
    if hasattr(result, 'result') and result.result is not None:
        for r in result.result.results:
            model_statuses.append(f"{r.node.name}={r.status}")
            if r.status == "success":
                models_executed += 1

    diagnostics["model_statuses"] = model_statuses
    return {"models_executed": models_executed, "diagnostics": diagnostics}
