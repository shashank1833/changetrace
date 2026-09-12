# Dead experiment: this module is never imported by production code.
def preview_return(order):
    if order.status == "RETURNED":
        return "preview-only"
    return None
