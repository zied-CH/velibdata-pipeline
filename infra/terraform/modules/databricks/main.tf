# ── Azure Databricks Workspace ────────────────────────────────────
# Standard tier — suffisant pour MSPR (Premium requis pour Unity Catalog)
resource "azurerm_databricks_workspace" "velibdata" {
  name                = var.databricks_workspace_name
  resource_group_name = var.resource_group_name
  location            = var.location
  sku                 = "standard"

  tags = {
    project     = "velibdata"
    environment = "production"
  }
}

# ── RBAC: Databricks → ADLS Gen2 contributeur ────────────────────
# Permet aux clusters Databricks de lire/écrire dans silver et gold
resource "azurerm_role_assignment" "databricks_adls" {
  scope                = var.storage_account_id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azurerm_databricks_workspace.velibdata.storage_account_identity[0].principal_id
  skip_service_principal_aad_check = true
}

# ── Secret: ADLS account name dans Key Vault pour Databricks ─────
resource "azurerm_key_vault_secret" "databricks_workspace_url" {
  name         = "databricks-workspace-url"
  value        = "https://${azurerm_databricks_workspace.velibdata.workspace_url}"
  key_vault_id = var.key_vault_id
}

# ── Diagnostic Settings → Log Analytics ──────────────────────────
# Route les logs Databricks (jobs, clusters, notebooks) vers Log Analytics
# Permet les alertes KQL et l'audit centralisé
resource "azurerm_monitor_diagnostic_setting" "databricks" {
  name                       = "diag-databricks-logs"
  target_resource_id         = azurerm_databricks_workspace.velibdata.id
  log_analytics_workspace_id = var.log_analytics_workspace_id

  enabled_log { category = "dbfs" }
  enabled_log { category = "clusters" }
  enabled_log { category = "accounts" }
  enabled_log { category = "jobs" }
  enabled_log { category = "notebook" }
  enabled_log { category = "workspace" }
}

# ── Alert: job Databricks échoué ─────────────────────────────────
# KQL query sur DatabricksJobs — détecte les runFailed
resource "azurerm_monitor_scheduled_query_rules_alert_v2" "job_failure" {
  name                 = "alert-databricks-job-failure"
  resource_group_name  = var.resource_group_name
  location             = var.location
  description          = "CRITIQUE: Un job Databricks a echoue"
  severity             = 0
  evaluation_frequency = "PT5M"
  window_duration      = "PT15M"
  scopes               = [var.log_analytics_workspace_id]

  criteria {
    query                   = <<-QUERY
      DatabricksJobs
      | where TimeGenerated > ago(15m)
      | where ActionName == "runFailed"
    QUERY
    time_aggregation_method = "Count"
    threshold               = 0
    operator                = "GreaterThan"

    failing_periods {
      minimum_failing_periods_to_trigger_alert = 1
      number_of_evaluation_periods             = 1
    }
  }

  action {
    action_groups = [var.action_group_id]
  }
}

# ── Alert: cluster Databricks en échec / OOM ─────────────────────
# Détecte cluster supprimé de force ou erreur de resize (souvent OOM)
resource "azurerm_monitor_scheduled_query_rules_alert_v2" "cluster_failure" {
  name                 = "alert-databricks-cluster-failure"
  resource_group_name  = var.resource_group_name
  location             = var.location
  description          = "CRITIQUE: Cluster Databricks en echec — possible OOM ou erreur critique"
  severity             = 0
  evaluation_frequency = "PT5M"
  window_duration      = "PT15M"
  scopes               = [var.log_analytics_workspace_id]

  criteria {
    query                   = <<-QUERY
      DatabricksClusters
      | where TimeGenerated > ago(15m)
      | where ActionName in ("permanentDelete", "resizeFailed")
          or (Response !contains "200" and ActionName != "get")
    QUERY
    time_aggregation_method = "Count"
    threshold               = 0
    operator                = "GreaterThan"

    failing_periods {
      minimum_failing_periods_to_trigger_alert = 1
      number_of_evaluation_periods             = 1
    }
  }

  action {
    action_groups = [var.action_group_id]
  }
}

# ── Alert: utilisation mémoire cluster > 85% ─────────────────────
# Détecte via les logs Spark les erreurs OOM avant crash complet
resource "azurerm_monitor_scheduled_query_rules_alert_v2" "memory_pressure" {
  name                 = "alert-databricks-memory"
  resource_group_name  = var.resource_group_name
  location             = var.location
  description          = "WARNING: Pression mémoire Databricks — risque OOM"
  severity             = 1
  evaluation_frequency = "PT5M"
  window_duration      = "PT15M"
  scopes               = [var.log_analytics_workspace_id]

  criteria {
    query                   = <<-QUERY
      DatabricksClusters
      | where TimeGenerated > ago(15m)
      | where Message has_any ("OutOfMemoryError", "OOM", "GC overhead", "heap space")
    QUERY
    time_aggregation_method = "Count"
    threshold               = 0
    operator                = "GreaterThan"

    failing_periods {
      minimum_failing_periods_to_trigger_alert = 1
      number_of_evaluation_periods             = 1
    }
  }

  action {
    action_groups = [var.action_group_id]
  }
}
