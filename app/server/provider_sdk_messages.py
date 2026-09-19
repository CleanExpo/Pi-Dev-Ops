"""Read bounded advisory SDK output while always releasing the client."""
async def read_sdk_text(client, prompt: str, separator: str = "") -> str:
    from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock
    parts = []
    try:
        await client.connect()
        await client.query(prompt)
        async for message in client.receive_messages():
            if isinstance(message, AssistantMessage):
                parts.extend(block.text for block in message.content if isinstance(block, TextBlock))
            elif isinstance(message, ResultMessage):
                break
    finally:
        await client.disconnect()
    return separator.join(parts)
