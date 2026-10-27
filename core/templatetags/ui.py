from django import template
from django.utils.html import format_html
register = template.Library()
PATHS = {
 'home': 'M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z',
 'predios': 'M3 21V7l9-4 9 4v14M3 11h18M8 11v10M16 11v10M3 16h18',
 'usuarios': 'M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8M22 21v-2a4 4 0 0 0-3-3.9',
 'cuadrilla': 'M9 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6M15 21H3v-2a5 5 0 0 1 10 0v2M17 4a3 3 0 0 1 0 6M21 21v-2a5 5 0 0 0-4-4',
 'asistencia': 'M12 8v4l3 2M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0',
 'kilos': 'M12 3v18M6 21h12M4 7h16M4 7l-3 7h6L4 7ZM20 7l-3 7h6l-3-7',
 'cierre': 'M6 11h12v10H6zM8 11V7a4 4 0 0 1 8 0v4M12 15v2',
 'reportes': 'M3 3v18h18M7 15l4-5 4 3 6-8',
 'auditoria': 'M12 3 3 7v5c0 5 9 10 9 10s9-5 9-10V7l-9-4ZM8 12l3 3 5-6',
 'leaf': 'M20 4c-8-2-16 2-15 9 1 7 10 8 13 1 2-4 2-10 2-10ZM4 21l11-12',
 'plus': 'M12 5v14M5 12h14',
 'arrow': 'M5 12h14M14 7l5 5-5 5',
 'menu': 'M3 6h18M3 12h18M3 18h18',
 'check': 'M5 12l4 4L19 6',
}
@register.simple_tag
def icon(name):
    key = {'mi_asistencia': 'asistencia', 'mi_produccion': 'kilos'}.get(name, name)
    return format_html('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="{}"/></svg>', PATHS.get(key, PATHS['leaf']))
