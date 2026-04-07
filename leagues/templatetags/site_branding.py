from django import template

from leagues.models import SiteConfig

register = template.Library()


@register.simple_tag
def get_site_config():
    return SiteConfig.get()
