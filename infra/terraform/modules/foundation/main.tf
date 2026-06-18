data "azurerm_client_config" "current" {}

# ── Resource Group ────────────────────────────────────────────
resource "azurerm_resource_group" "velibdata" {
  name     = var.resource_group_name
  location = var.location
}

# ── Key Vault ─────────────────────────────────────────────────
resource "azurerm_key_vault" "velibdata" {
  name                       = var.key_vault_name
  location                   = azurerm_resource_group.velibdata.location
  resource_group_name        = azurerm_resource_group.velibdata.name
  tenant_id                  = data.azurerm_client_config.current.tenant_id
  sku_name                   = "standard"
  soft_delete_retention_days = 7    # immuable après création — ne pas modifier
  purge_protection_enabled   = true # sécurité: empêche suppression définitive accidentelle
}

# Current user (az login session) gets full admin access to Key Vault
resource "azurerm_key_vault_access_policy" "admin" {
  key_vault_id = azurerm_key_vault.velibdata.id
  tenant_id    = data.azurerm_client_config.current.tenant_id
  object_id    = data.azurerm_client_config.current.object_id

  secret_permissions = ["Get", "List", "Set", "Delete", "Purge", "Recover"]
}

resource "azurerm_key_vault_secret" "tenant_id" {
  name         = "azure-tenant-id"
  value        = data.azurerm_client_config.current.tenant_id
  key_vault_id = azurerm_key_vault.velibdata.id
  depends_on   = [azurerm_key_vault_access_policy.admin]
}
