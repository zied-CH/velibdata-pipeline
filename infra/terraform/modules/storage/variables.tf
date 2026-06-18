variable "resource_group_name" { type = string }
variable "location" { type = string }
variable "storage_account_name" { type = string }
variable "current_user_object_id" { type = string }
variable "key_vault_id" { type = string }
variable "deployer_ip" {
  type        = string
  description = "IP publique du poste admin (Terraform + Streamlit local)"
}
