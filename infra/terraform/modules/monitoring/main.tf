# ── Log Analytics Workspace ───────────────────────────────────
resource "azurerm_log_analytics_workspace" "velibdata" {
  name                = "log-velibdata"
  location            = var.location
  resource_group_name = var.resource_group_name
  sku                 = "PerGB2018"
  retention_in_days   = 90   # CdC §4.3.5 — 90 jours rétention
}

# ── Application Insights ──────────────────────────────────────
resource "azurerm_application_insights" "velibdata" {
  name                = "appi-velibdata"
  location            = var.location
  resource_group_name = var.resource_group_name
  workspace_id        = azurerm_log_analytics_workspace.velibdata.id
  application_type    = "other"
}

# ── Action Group: alerts → email ──────────────────────────────
resource "azurerm_monitor_action_group" "team" {
  name                = "ag-velibdata-team"
  resource_group_name = var.resource_group_name
  short_name          = "velibdata"

  email_receiver {
    name                    = "team-lead"
    email_address           = var.alert_email
    use_common_alert_schema = true
  }

  # Teams webhook — activé uniquement si teams_webhook_url est fourni
  dynamic "webhook_receiver" {
    for_each = var.teams_webhook_url != "" ? [1] : []
    content {
      name                    = "teams-channel"
      service_uri             = var.teams_webhook_url
      use_common_alert_schema = true
    }
  }
}

# ── Alert: aucune transaction ADLS détectée → pipeline down ─────
# Remplace l'ancienne alerte Event Hubs — pipeline écrit maintenant directement dans ADLS
# CdC §4.3.2 — latence ingestion > 15 min → CRITIQUE ────────────
resource "azurerm_monitor_metric_alert" "ingestion_lag" {
  name                = "alert-adls-no-writes"
  resource_group_name = var.resource_group_name
  scopes              = [var.storage_account_id]
  severity            = 0
  frequency           = "PT5M"
  window_size         = "PT15M"
  description         = "CRITIQUE: Aucune transaction ADLS en 15 min — pipeline d'ingestion possiblement arrete"

  criteria {
    metric_namespace = "Microsoft.Storage/storageAccounts"
    metric_name      = "Transactions"
    aggregation      = "Total"
    operator         = "LessThan"
    threshold        = 1
  }

  action {
    action_group_id = azurerm_monitor_action_group.team.id
  }
}

# ── Alert: taux d'erreurs ADLS élevé → problème d'accès ─────────
# CdC §4.3.2 — taux d'erreur > 5 → CRITIQUE ─────────────────────
resource "azurerm_monitor_metric_alert" "storage_errors" {
  name                = "alert-adls-server-errors"
  resource_group_name = var.resource_group_name
  scopes              = [var.storage_account_id]
  severity            = 0
  frequency           = "PT5M"
  window_size         = "PT15M"
  description         = "CRITIQUE: Plus de 5 erreurs serveur ADLS en 15 min"

  criteria {
    metric_namespace = "Microsoft.Storage/storageAccounts"
    metric_name      = "Transactions"
    aggregation      = "Total"
    operator         = "GreaterThan"
    threshold        = 5

    dimension {
      name     = "ResponseType"
      operator = "Include"
      values   = ["ServerOtherError", "ServerBusyError"]
    }
  }

  action {
    action_group_id = azurerm_monitor_action_group.team.id
  }
}

# ── Alert: disponibilité ADLS < 99.9% ───────────────────────────
# SLA cible > 99.9% — CdC §4.3.3 ────────────────────────────────
resource "azurerm_monitor_metric_alert" "storage_availability" {
  name                = "alert-adls-availability"
  resource_group_name = var.resource_group_name
  scopes              = [var.storage_account_id]
  severity            = 1
  frequency           = "PT5M"
  window_size         = "PT15M"
  description         = "WARNING: Disponibilité ADLS Gen2 inférieure à 99.9%"

  criteria {
    metric_namespace = "Microsoft.Storage/storageAccounts"
    metric_name      = "Availability"
    aggregation      = "Average"
    operator         = "LessThan"
    threshold        = 99.9
  }

  action {
    action_group_id = azurerm_monitor_action_group.team.id
  }
}

# ── Budget: $100 Azure for Students — alerts at 50% and 80%
# CdC §13.2 — dépassement budget risque ÉLEVÉ ─────────────────
resource "azurerm_consumption_budget_resource_group" "velibdata" {
  name              = "budget-velibdata"
  resource_group_id = var.resource_group_id
  amount            = var.budget_amount
  time_grain        = "Monthly"

  time_period {
    start_date = var.budget_start_date
  }

  notification {
    enabled        = true
    threshold      = 50
    operator       = "GreaterThan"
    threshold_type = "Actual"
    contact_emails = [var.alert_email]
  }

  notification {
    enabled        = true
    threshold      = 80
    operator       = "GreaterThan"
    threshold_type = "Actual"
    contact_emails = [var.alert_email]
  }

  notification {
    enabled        = true
    threshold      = 95
    operator       = "GreaterThan"
    threshold_type = "Actual"
    contact_emails = [var.alert_email]
  }

  notification {
    enabled        = true
    threshold      = 100
    operator       = "GreaterThan"
    threshold_type = "Actual"
    contact_emails = [var.alert_email]
  }
}

# ── Alert: capacité ADLS > 5 GB — croissance anormale ────────────
# Seuil adapté au projet étudiant Vélib (~50 MB/jour attendu)
resource "azurerm_monitor_metric_alert" "storage_capacity" {
  name                = "alert-adls-capacity"
  resource_group_name = var.resource_group_name
  scopes              = [var.storage_account_id]
  severity            = 2
  frequency           = "PT1H"
  window_size         = "PT1H"
  description         = "WARNING: Volume ADLS Gen2 depasse 5 GB — croissance anormale detectee"

  criteria {
    metric_namespace = "Microsoft.Storage/storageAccounts"
    metric_name      = "UsedCapacity"
    aggregation      = "Average"
    operator         = "GreaterThan"
    threshold        = 5368709120 # 5 GB en octets
  }

  action {
    action_group_id = azurerm_monitor_action_group.team.id
  }
}
