output "purview_account_id" {
  value = azurerm_purview_account.velibdata.id
}

output "purview_catalog_endpoint" {
  description = "URL du catalogue Purview — ouvrir dans le navigateur pour visualiser le Data Lineage"
  value       = azurerm_purview_account.velibdata.catalog_endpoint
}

output "purview_scan_endpoint" {
  value = azurerm_purview_account.velibdata.scan_endpoint
}
