module "foundation" {
  source = "./modules/foundation"

  resource_group_name = var.resource_group_name
  location            = var.location
  key_vault_name      = var.key_vault_name
}

module "storage" {
  source = "./modules/storage"

  resource_group_name    = var.resource_group_name
  location               = var.location
  storage_account_name   = var.storage_account_name
  current_user_object_id = module.foundation.current_user_object_id
  key_vault_id           = module.foundation.key_vault_id
  deployer_ip            = var.deployer_ip

  depends_on = [module.foundation]
}

module "eventhubs" {
  source = "./modules/eventhubs"

  resource_group_name     = var.resource_group_name
  location                = var.location
  eventhub_namespace_name = var.eventhub_namespace_name
  key_vault_id            = module.foundation.key_vault_id

  depends_on = [module.foundation]
}

module "adf" {
  source = "./modules/adf"

  resource_group_name   = var.resource_group_name
  location              = var.location
  adf_name              = var.adf_name
  storage_account_id    = module.storage.storage_account_id
  storage_account_name  = var.storage_account_name
  eventhub_namespace_id = module.eventhubs.eventhub_namespace_id
  key_vault_id          = module.foundation.key_vault_id
  key_vault_name        = var.key_vault_name
  tenant_id             = module.foundation.tenant_id

  depends_on = [module.storage, module.eventhubs]
}

module "monitoring" {
  source = "./modules/monitoring"

  resource_group_name   = var.resource_group_name
  resource_group_id     = module.foundation.resource_group_id
  location              = var.location
  eventhub_namespace_id = module.eventhubs.eventhub_namespace_id
  storage_account_id    = module.storage.storage_account_id
  alert_email           = var.alert_email
  teams_webhook_url     = var.teams_webhook_url
  budget_amount         = var.budget_amount
  budget_start_date     = var.budget_start_date

  depends_on = [module.foundation, module.storage]
}

module "databricks" {
  source = "./modules/databricks"

  resource_group_name        = var.resource_group_name
  location                   = var.location
  storage_account_id         = module.storage.storage_account_id
  storage_account_name       = var.storage_account_name
  key_vault_id               = module.foundation.key_vault_id
  databricks_workspace_name  = var.databricks_workspace_name
  log_analytics_workspace_id = module.monitoring.log_analytics_workspace_id
  action_group_id            = module.monitoring.action_group_id

  depends_on = [module.monitoring, module.storage]
}

module "purview" {
  source = "./modules/purview"

  resource_group_name  = var.resource_group_name
  location             = var.location
  storage_account_id   = module.storage.storage_account_id
  purview_account_name = var.purview_account_name

  depends_on = [module.storage]
}

# ══════════════════════════════════════════════════════════════════
# SÉCURITÉ — Logs d'audit centralisés dans Log Analytics
# Toute lecture/écriture/suppression sur Key Vault et ADLS est tracée.
# ══════════════════════════════════════════════════════════════════

# Audit Key Vault : chaque accès à un secret (ADF, Functions, admin) est logué
resource "azurerm_monitor_diagnostic_setting" "keyvault_audit" {
  name                       = "kv-audit-logs"
  target_resource_id         = module.foundation.key_vault_id
  log_analytics_workspace_id = module.monitoring.log_analytics_workspace_id

  enabled_log {
    category = "AuditEvent"
  }

  depends_on = [module.foundation, module.monitoring]
}

# Audit ADLS Gen2 : lecture/écriture/suppression sur les blobs Bronze/Silver/Gold
resource "azurerm_monitor_diagnostic_setting" "storage_audit" {
  name                       = "storage-audit-logs"
  target_resource_id         = "${module.storage.storage_account_id}/blobServices/default"
  log_analytics_workspace_id = module.monitoring.log_analytics_workspace_id

  enabled_log {
    category = "StorageRead"
  }
  enabled_log {
    category = "StorageWrite"
  }
  enabled_log {
    category = "StorageDelete"
  }

  depends_on = [module.storage, module.monitoring]
}
