# ============================================================
# Outputs — shared with dbt teammate and CI/CD
# Run: terraform output  to see all values after apply
# ============================================================

output "resource_group_name" {
  description = "Resource group containing all VélibData Azure resources"
  value       = var.resource_group_name
}

output "storage_account_name" {
  description = "ADLS Gen2 storage account name — give this to dbt teammate"
  value       = module.storage.storage_account_name
}

output "storage_account_id" {
  description = "ADLS Gen2 storage account resource ID"
  value       = module.storage.storage_account_id
}

output "bronze_container_name" {
  description = "Bronze layer container name"
  value       = "bronze"
}

output "silver_container_name" {
  description = "Silver layer container name — dbt teammate writes here"
  value       = "silver"
}

output "gold_container_name" {
  description = "Gold layer container name — dbt teammate writes here"
  value       = "gold"
}

output "key_vault_name" {
  description = "Key Vault name — all secrets stored here"
  value       = module.foundation.key_vault_name
}

output "key_vault_uri" {
  description = "Key Vault URI — used in Python code and dbt profile"
  value       = module.foundation.key_vault_uri
}

output "eventhub_namespace_name" {
  description = "Event Hubs namespace name"
  value       = var.eventhub_namespace_name
}

output "adf_name" {
  description = "Azure Data Factory name"
  value       = var.adf_name
}

output "app_insights_instrumentation_key" {
  description = "Application Insights key — used in Python logging"
  value       = module.monitoring.app_insights_instrumentation_key
  sensitive   = true
}

output "log_analytics_workspace_id" {
  description = "Log Analytics workspace ID — used for dbt Cloud logging (give to teammate)"
  value       = module.monitoring.log_analytics_workspace_id
}

output "databricks_workspace_url" {
  description = "URL du workspace Databricks — ouvrir dans le navigateur"
  value       = module.databricks.databricks_workspace_url
}

output "purview_catalog_endpoint" {
  description = "URL du catalogue Purview — visualiser le Data Lineage et les datasets"
  value       = module.purview.purview_catalog_endpoint
}
