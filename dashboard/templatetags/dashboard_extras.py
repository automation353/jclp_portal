from django import template
from django.utils.safestring import mark_safe

register = template.Library()

_ICONS = {
    "purchase": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M3 6h2l2.4 10.4A2 2 0 0 0 9.4 18H18a2 2 0 0 0 2-1.6L21 9H6" stroke-linecap="round" stroke-linejoin="round"/><circle cx="10" cy="21" r="1.4"/><circle cx="17" cy="21" r="1.4"/></svg>',
    "hr": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="9" cy="8" r="3.2"/><path d="M3.5 19c.8-3.2 3-4.8 5.5-4.8s4.7 1.6 5.5 4.8" stroke-linecap="round"/><path d="M16.5 8.5a2.6 2.6 0 1 1 0 5.2" stroke-linecap="round"/><path d="M15 14.4c2 .3 3.6 1.7 4.5 4.6" stroke-linecap="round"/></svg>',
    "accounts": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="3.5" y="5" width="17" height="14" rx="1.6"/><path d="M3.5 9.5h17M7.5 14h5" stroke-linecap="round"/></svg>',
    "sales": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 19V9.5L12 4l8 5.5V19" stroke-linejoin="round"/><path d="M9 19v-6h6v6" /></svg>',
    "operations": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="3"/><path d="M19 12a7 7 0 0 0-.14-1.4l2-1.5-1.5-2.6-2.3.9a7 7 0 0 0-2.4-1.4L14.3 3.6h-3l-.36 2.4a7 7 0 0 0-2.4 1.4l-2.3-.9-1.5 2.6 2 1.5a7 7 0 0 0 0 2.8l-2 1.5 1.5 2.6 2.3-.9c.7.6 1.5 1.1 2.4 1.4l.36 2.4h3l.36-2.4a7 7 0 0 0 2.4-1.4l2.3.9 1.5-2.6-2-1.5c.1-.46.14-.93.14-1.4Z" stroke-linejoin="round"/></svg>',
    "design": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 15.5 14.5 5l4.5 4.5L8.5 20H4v-4.5Z" stroke-linejoin="round"/><path d="M12.5 7 17 11.5" /></svg>',
    "sop": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 19V5M4 19h16" stroke-linecap="round"/><path d="M7.5 15.5 11 11l3 2.5L19 7.5" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    "team": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="9" cy="8" r="3"/><path d="M3.5 19c.7-3 2.8-4.6 5.5-4.6s4.8 1.6 5.5 4.6" stroke-linecap="round"/><circle cx="17.5" cy="8.5" r="2.2"/><path d="M15.8 14.6c1.9.4 3.3 1.8 4 4.4" stroke-linecap="round"/></svg>',
    "activity": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
}


@register.simple_tag
def module_icon(key):
    return mark_safe(_ICONS.get(key, ""))
