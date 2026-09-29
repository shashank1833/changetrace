# Abandoned experiment; production code never imports this module.
def preview_pause(subscription):
    return subscription.status == "ACTIVE"
