output "databricks_workspace_id" {
  value = azurerm_databricks_workspace.velibdata.id
}

output "databricks_workspace_url" {
  description = "URL du workspace Databricks — ouvrir dans le navigateur"
  value       = "https://${azurerm_databricks_workspace.velibdata.workspace_url}"
}
