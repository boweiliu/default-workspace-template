Chat failures without a reason of their own use the workspace's shared sentences instead of "request failed (HTTP 503)", "could not reach the workspace", "unknown error", "The chat list could not open a new chat (503)" or "The chat app answered HTTP 500.".

- A transcript or side conversation that does not load says so plainly ("The workspace didn't answer. Try again in a moment.", or "This chat couldn't be loaded."), without an "Error:" prefix; the model list in the switch dialog says "Couldn't load the list of models." with the reason behind "See details".

- A send the chat refused says your message wasn't delivered, with the reason behind "See details"; a send that got no answer says it may not have been sent, and offers no Retry, which could send it twice. The text is back in the box either way.

- A declined `/compact` carries its sentence as one written for people, so the composer still shows it.

- Creating a chat, the empty chat list's new chat, reading or applying a message sent from the launcher, and the secret card's submit and decline now read failures through the shared reader.
