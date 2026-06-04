"""Azure Functions pour le pipeline VelibData.

Deux fonctions HTTP triggers appelees par Azure Data Factory :
- /api/ingest : ingestion des APIs vers ADLS Bronze
- /api/load-bronze : chargement des donnees Bronze vers Azure SQL
"""

import asyncio
import logging

import azure.functions as func

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)


@app.route(route="ingest", methods=["POST", "GET"])
def ingest_velib_data(req: func.HttpRequest) -> func.HttpResponse:
    """Lance un cycle d ingestion des APIs Velib vers ADLS Bronze."""
    logging.info("ingest_function_triggered")

    try:
        from ingestion_logic import run_ingestion
        result = asyncio.run(run_ingestion())
        return func.HttpResponse(
            body=f'{{"status": "success", "stations": {result["stations"]}}}',
            mimetype="application/json",
            status_code=200,
        )
    except Exception as e:
        logging.exception("ingest_function_failed")
        return func.HttpResponse(
            body=f'{{"status": "error", "message": "{str(e)}"}}',
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
            body=f'{{"status": "success", "loaded": {result}}}',
            mimetype="application/json",
            status_code=200,
        )
    except Exception as e:
        logging.exception("load_bronze_function_failed")
        return func.HttpResponse(
            body=f'{{"status": "error", "message": "{str(e)}"}}',
            mimetype="application/json",
            status_code=500,
        )
