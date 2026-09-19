permit(
  principal,
  action in [AgentCore::Action::"SupportTools___check_order",
             AgentCore::Action::"SupportTools___get_customer"],
  resource == AgentCore::Gateway::"${Gateway.GatewayArn}"
);
