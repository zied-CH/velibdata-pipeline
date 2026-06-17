# ── ADLS Gen2 Storage Account ─────────────────────────────────
resource "azurerm_storage_account" "velibdata" {
  name                     = var.storage_account_name
  resource_group_name      = var.resource_group_name
  location                 = var.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  account_kind             = "StorageV2"
  is_hns_enabled           = true # HNS = Hierarchical Namespace = ADLS Gen2

  # ── Sécurité transport ────────────────────────────────────────
  enable_https_traffic_only        = true    # refuse les requêtes HTTP
  min_tls_version                  = "TLS1_2" # interdit TLS 1.0 et 1.1
  allow_nested_items_to_be_public  = false   # bloque tout accès blob public anonyme

  blob_properties {
    delete_retention_policy {
      days = 7
    }
  }
}

# ── Règles réseau : refuse l'internet public, autorise les services Azure ──
# ADF, Azure Functions et Databricks passent via "AzureServices" bypass.
resource "azurerm_storage_account_network_rules" "velibdata" {
  storage_account_id = azurerm_storage_account.velibdata.id
  default_action     = "Deny"
  bypass             = ["AzureServices", "Logging", "Metrics"]
}

# ── Bronze container — raw JSON from APIs ─────────────────────
resource "azurerm_storage_data_lake_gen2_filesystem" "bronze" {
  name               = "bronze"
  storage_account_id = azurerm_storage_account.velibdata.id
}

# ── Silver container — cleaned Delta Lake (dbt teammate writes here)
resource "azurerm_storage_data_lake_gen2_filesystem" "silver" {
  name               = "silver"
  storage_account_id = azurerm_storage_account.velibdata.id
}

# ── Gold container — aggregated, Power BI ready (dbt teammate writes here)
resource "azurerm_storage_data_lake_gen2_filesystem" "gold" {
  name               = "gold"
  storage_account_id = azurerm_storage_account.velibdata.id
}

# ── RBAC: current user gets contributor on ADLS (CdC §8.6)
resource "azurerm_role_assignment" "current_user_storage" {
  scope                = azurerm_storage_account.velibdata.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = var.current_user_object_id
}

# ── Lifecycle Management: Hot → Cool → Archive ───────────────────
# Bronze : données brutes conservées 1 an, hiérarchisées par coût
# CdC §4.3.4 — optimisation coût stockage ────────────────────────
resource "azurerm_storage_management_policy" "lifecycle" {
  storage_account_id = azurerm_storage_account.velibdata.id

  rule {
    name    = "bronze-tiering"
    enabled = true

    filters {
      prefix_match = ["bronze/"]
      blob_types   = ["blockBlob"]
    }

    actions {
      base_blob {
        tier_to_cool_after_days_since_modification_greater_than    = 90
        tier_to_archive_after_days_since_modification_greater_than = 180
        delete_after_days_since_modification_greater_than          = 365
      }
    }
  }

  rule {
    name    = "silver-tiering"
    enabled = true

    filters {
      prefix_match = ["silver/"]
      blob_types   = ["blockBlob"]
    }

    actions {
      base_blob {
        tier_to_cool_after_days_since_modification_greater_than    = 90
        tier_to_archive_after_days_since_modification_greater_than = 365
      }
    }
  }
}

# ── Store connection string in Key Vault (never hardcode it) ──
resource "azurerm_key_vault_secret" "adls_connection_string" {
  name         = "adls-connection-string"
  value        = azurerm_storage_account.velibdata.primary_connection_string
  key_vault_id = var.key_vault_id
}

resource "azurerm_key_vault_secret" "adls_account_name" {
  name         = "adls-account-name"
  value        = azurerm_storage_account.velibdata.name
  key_vault_id = var.key_vault_id
}
