"""Azure Functions pour le pipeline VelibData.

Quatre fonctions HTTP triggers appelees par Azure Data Factory :
- /api/ingest      : ingestion des APIs vers ADLS Bronze
- /api/load-bronze : chargement des donnees Bronze vers Azure SQL
- /api/run-dbt     : transformations Bronze -> Silver -> Gold
- /api/test-dbt    : tests de qualite dbt sur les donnees
"""

import asyncio
import json
import logging

import azure.functions as func

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)


@app.route(route="ingest", methods=["POST", "GET"])
def ingest_velib_data(req: func.HttpRequest) -> func.HttpResponse:
    """Lance un cycle d ingestion des APIs Velib vers ADLS Bronze."""
    logging.info("ingest_function_triggered")
    try:
        from ingestion_logic import run_ingestion

        result = asyncio.run(run_ingestion())
        return func.HttpResponse(
            body=json.dumps({"status": "success", "stations": result["stations"]}),
            mimetype="application/json",
            status_code=200,
        )
    except Exception as e:
        logging.exception("ingest_function_failed")
        return func.HttpResponse(
            body=json.dumps({"status": "error", "message": str(e)[:500]}),
            mimetype="application/json",
            status_code=500,
        )


@app.route(route="load-bronze", methods=["POST", "GET"])
def load_bronze_to_sql(req: func.HttpRequest) -> func.HttpResponse:
    """Charge les donnees Bronze depuis ADLS vers Azure SQL Database."""
    logging.info("load_bronze_function_triggered")
    try:
        from load_bronze_logic import run_load

        result = run_load()
        return func.HttpResponse(
            body=json.dumps({"status": "success", "loaded": result}),
            mimetype="application/json",
            status_code=200,
        )
    except Exception as e:
        logging.exception("load_bronze_function_failed")
        return func.HttpResponse(
            body=json.dumps({"status": "error", "message": str(e)[:500]}),
            mimetype="application/json",
            status_code=500,
        )


@app.route(route="run-dbt", methods=["POST", "GET"])
def run_dbt(req: func.HttpRequest) -> func.HttpResponse:
    """Lance les transformations dbt (Bronze -> Silver -> Gold)."""
    logging.info("run_dbt_function_triggered")
    try:
        from dbt_logic import run_dbt_transformations

        result = run_dbt_transformations()
        return func.HttpResponse(
            body=json.dumps({"status": "success", **result}, default=str),
            mimetype="application/json",
            status_code=200,
        )
    except Exception as e:
        logging.exception("run_dbt_function_failed")
        return func.HttpResponse(
            body=json.dumps({"status": "error", "message": str(e)[:1000]}),
            mimetype="application/json",
            status_code=500,
        )


@app.route(route="test-dbt", methods=["POST", "GET"])
def test_dbt(req: func.HttpRequest) -> func.HttpResponse:
    """Lance les tests de qualite dbt (validation des donnees)."""
    logging.info("test_dbt_function_triggered")
    try:
        from dbt_logic import run_dbt_tests

        result = run_dbt_tests()
        return func.HttpResponse(
            body=json.dumps({"status": "success", **result}, default=str),
            mimetype="application/json",
            status_code=200,
        )
    except Exception as e:
        logging.exception("test_dbt_function_failed")
        return func.HttpResponse(
            body=json.dumps({"status": "error", "message": str(e)[:1000]}),
            mimetype="application/json",
            status_code=500,
        )
