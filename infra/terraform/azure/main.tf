terraform {
  required_version = ">= 1.7, < 2.0"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
  }
}

provider "azurerm" {
  features {}
  subscription_id                 = var.subscription_id
  resource_provider_registrations = "none"
}

data "azurerm_subscription" "current" {}

resource "azurerm_resource_group" "demo" {
  name     = "valeosense-demo"
  location = var.location
  lifecycle {
    precondition {
      condition = (
        lower(data.azurerm_subscription.current.spending_limit) == "on" &&
        strcontains(lower(data.azurerm_subscription.current.quota_id), "student")
      )
      error_message = "Only an Azure for Students subscription with spending protection ON is allowed. Do not upgrade or remove the limit."
    }
    precondition {
      condition     = var.credit_and_price_checked
      error_message = "Check remaining student credit, VM quota and the regional VM/disk/IP estimate first."
    }
  }
  tags = { project = "valeosense", purpose = "student-demo" }
}

resource "azurerm_virtual_network" "demo" {
  name                = "valeosense"
  location            = azurerm_resource_group.demo.location
  resource_group_name = azurerm_resource_group.demo.name
  address_space       = ["10.20.0.0/16"]
}

resource "azurerm_subnet" "demo" {
  name                 = "demo"
  resource_group_name  = azurerm_resource_group.demo.name
  virtual_network_name = azurerm_virtual_network.demo.name
  address_prefixes     = ["10.20.1.0/24"]
}

resource "azurerm_public_ip" "demo" {
  name                = "valeosense"
  location            = azurerm_resource_group.demo.location
  resource_group_name = azurerm_resource_group.demo.name
  allocation_method   = "Static"
  sku                 = "Standard"
}

resource "azurerm_network_security_group" "demo" {
  name                = "valeosense-ssh-only"
  location            = azurerm_resource_group.demo.location
  resource_group_name = azurerm_resource_group.demo.name
  security_rule {
    name                       = "SSHFromOwner"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "22"
    source_address_prefix      = var.admin_cidr
    destination_address_prefix = "*"
  }
}

resource "azurerm_network_interface" "demo" {
  name                = "valeosense"
  location            = azurerm_resource_group.demo.location
  resource_group_name = azurerm_resource_group.demo.name
  ip_configuration {
    name                          = "demo"
    subnet_id                     = azurerm_subnet.demo.id
    private_ip_address_allocation = "Dynamic"
    public_ip_address_id          = azurerm_public_ip.demo.id
  }
}

resource "azurerm_network_interface_security_group_association" "demo" {
  network_interface_id      = azurerm_network_interface.demo.id
  network_security_group_id = azurerm_network_security_group.demo.id
}

resource "azurerm_linux_virtual_machine" "demo" {
  name                            = "valeosense"
  location                        = azurerm_resource_group.demo.location
  resource_group_name             = azurerm_resource_group.demo.name
  size                            = var.vm_size
  admin_username                  = "ubuntu"
  disable_password_authentication = true
  network_interface_ids           = [azurerm_network_interface.demo.id]
  custom_data                     = filebase64("${path.module}/../../cloud-init.yaml")
  depends_on                      = [azurerm_network_interface_security_group_association.demo]
  admin_ssh_key {
    username   = "ubuntu"
    public_key = var.ssh_public_key
  }
  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "Standard_LRS"
    disk_size_gb         = 64
  }
  source_image_reference {
    publisher = "Canonical"
    offer     = "ubuntu-24_04-lts"
    sku       = "server"
    version   = "latest"
  }
  lifecycle {
    prevent_destroy = true
  }
}

resource "azurerm_dev_test_global_vm_shutdown_schedule" "demo" {
  virtual_machine_id    = azurerm_linux_virtual_machine.demo.id
  location              = azurerm_resource_group.demo.location
  enabled               = true
  daily_recurrence_time = var.shutdown_time_utc
  timezone              = "UTC"
  notification_settings {
    enabled = false
  }
}
