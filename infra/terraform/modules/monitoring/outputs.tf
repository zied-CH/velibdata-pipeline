output "app_insights_instrumentation_key" {
  value     = azurerm_application_insights.velibdata.instrumentation_key
  sensitive = true
}

output "app_insights_connection_string" {
  value     = azurerm_application_insights.velibdata.connection_string
  sensitive = true
}

output "log_analytics_workspace_id" {
  description = "Workspace ID — share with dbt teammate for cloud logging"
  value       = azurerm_log_analytics_workspace.velibdata.id
}

output "log_analytics_workspace_name" {
  value = azurerm_log_analytics_workspace.velibdata.name
}

output "action_group_id" {
  description = "Action Group ID — pass to Databricks module for job failure alerts"
  value       = azurerm_monitor_action_group.team.id
}
