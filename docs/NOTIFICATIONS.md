# Optional webhook notifications

Save an HTTPS webhook in Settings and enable notifications. Health provides a test
button and delivery status. Stackarr sends only an event ID, application ID and
state; no media titles, paths, addresses, user identities or credentials are in the
payload. The saved destination is encrypted and never returned to the browser.

State observations and pending messages survive restarts. An initially healthy app
is quiet; failures and later recoveries produce messages. Repeated identical states
do not enqueue duplicates, and newer states replace unsent old states for the same
app. Scheduled backup failures and recovery use the same queue.

Each message gets at most three automatic attempts, with increasing delays. Failed
delivery stays visible in Health and the audit trail. A network timeout can occur
after a recipient accepted a message, so exactly-once delivery is not guaranteed;
receivers can deduplicate using event_id. Turning notifications off cancels pending
messages. Background delivery requires Stackarr to remain running.

This preview supports one generic HTTPS JSON webhook. Provider-specific email,
ntfy/Apprise formatting, event filters, delivery history, quiet hours and explicit
retry of a failed event remain backlog work. The test button queues a new test;
it does not replay old messages.
