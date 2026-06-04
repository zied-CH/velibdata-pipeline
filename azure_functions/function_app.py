"""Azure Functions pour le pipeline VelibData."""

import asyncio
import json
import logging

import azure.functions as func

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)


@app.route(route="ingest", methods=["POST", "GET"])
def ingest_velib_data(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("ingest_function_triggered")
    try:
        from ingestion_logic import run_ingestion
        result = asyncio.run(run_ingestion())
        return func.HttpResponse(
            body=json.dumps({"status": "success", "stations": result["stations"]}),
            mimetype="application/json", status_code=200,
        )
    except Exception as e:
        logging.exception("ingest_function_failed")
        return func.HttpResponse(
            body=json.dumps({"status": "error", "message": str(e)[:500]}),
            mimetype="application/json", status_code=500,
        )


@app.route(route="load-bronze", methods=["POST", "GET"])
def load_bronze_to_sql(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("load_bronze_function_triggered")
    try:
        from load_bronze_logic import run_load
        result = run_load()
        return func.HttpResponse(
            body=json.dumps({"status": "success", "loaded": result}),
            mimetype="application/json", status_code=200,
        )
    except Exception as e:
        logging.exception("load_bronze_function_failed")
        return func.HttpResponse(
            body=json.dumps({"status": "error", "message": str(e)[:500]}),
            mimetype="application/json", status_code=500,
        )


@app.route(route="run-dbt", methods=["POST", "GET"])
def run_dbt(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("run_dbt_function_triggered")
    try:
        from dbt_logic import run_dbt_transformations
        result = run_dbt_transformations()
        return func.HttpResponse(
            body=json.dumps({"status": "success", **result}, default=str),
            mimetype="application/json", status_code=200,
        )
    except Exception as e:
        logging.exception("run_dbt_function_failed")
        return func.HttpResponse(
            body=json.dumps({"status": "error", "message": str(e)[:1000]}),
            mimetype="application/json", status_code=500,
        )
