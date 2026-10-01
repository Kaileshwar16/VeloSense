output "public_ip" {
  value = azurerm_public_ip.demo.ip_address
}

output "vm_id" {
  value = azurerm_linux_virtual_machine.demo.id
}

output "ssh_command" {
  value = "ssh ubuntu@${azurerm_public_ip.demo.ip_address}"
}

output "deployment_boundary" {
  value = "VM infrastructure only. Deploy workloads and collect live verification before marking the cloud requirement complete. No public application ingress is enabled."
}
