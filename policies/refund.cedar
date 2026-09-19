permit(
  principal,
  action == AgentCore::Action::"SupportTools___refund_customer",
  resource == AgentCore::Gateway::"${Gateway.GatewayArn}"
)
when {
  context.input.amount_cents > 0 &&
  context.input.amount_cents <= 100000
};
