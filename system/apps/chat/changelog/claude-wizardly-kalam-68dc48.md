A chat is usable while its agent is still starting or connecting.

- Stop is there as soon as a message is sent, including while the chat connects. Pressing it while the message is still waiting for the agent takes the message back into the composer, unsent; once the agent is up it interrupts as before. This also covers the first message of a new chat.

- A chat that is still starting can be renamed and deleted from the chat list and the phone header. The new name shows at once and the agent takes it when it lands; a deleted chat leaves the list at once and its agent is removed as soon as it exists.

- The provider and model of a chat that is still starting can be changed from its model chip. A new model is applied as the agent comes up; another provider moves the chat to it then, carrying the messages already sent.

- "Connecting…" names what the chat waits for, such as "Connecting to Opus 5.5 on Anthropic…".

- Typing into a chat whose agent is stopped starts the agent in the background, so the message usually finds it up and "Connecting…" is rarely seen.

- The agent's terminal view opens at once for an agent that is already running, instead of saying "Starting agent..." while it checks. It says "Starting agent…" only for a stopped one.
