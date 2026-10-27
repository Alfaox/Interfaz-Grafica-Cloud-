from .menu import items_for


def menu(request):
    if not request.user.is_authenticated:
        return {}
    actual = request.resolver_match.url_name if request.resolver_match else ""
    return {"menu_items": [
        {"label": l, "url": u, "activo": u == actual} for l, u, _, _ in items_for(request.user.rol)
    ]}
