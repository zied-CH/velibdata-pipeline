# ── Microsoft Purview — Gouvernance & Catalogage des données ──────
# Fournit : Data Lineage, catalogage automatique, classification,
# et traçabilité complète du parcours des données (bronze → silver → gold → Power BI)
resource "azurerm_purview_account" "velibdata" {
  name                = var.purview_account_name
  resource_group_name = var.resource_group_name
  location            = var.location

  identity {
    type = "SystemAssigned"
  }

  public_network_enabled = true
}

# ── RBAC: Purview → ADLS reader pour scanner les données ─────────
# Purview scanne ADLS Gen2 pour construire le catalogue automatiquement
resource "azurerm_role_assignment" "purview_adls_reader" {
  scope                = var.storage_account_id
  role_definition_name = "Storage Blob Data Reader"
  principal_id         = azurerm_purview_account.velibdata.identity[0].principal_id
}
